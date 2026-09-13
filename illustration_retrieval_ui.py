"""Phase 3I / 3I.1 / 3I.2 / 3I.3: user-facing illustration retrieval UI.

Lives OUTSIDE `illustration_review_ui.py` -- that module is the
internal reviewer/QA tool (gated to the owner email or localhost);
THIS module is the normal, public "Illusztrációk" tab's SOLE content.

Phase 3I.1: the tab previously also ran a free-form LLM story-generation
block (SECTION_PROMPTS["illustrations"] in app.py -- "Klasszikus
tanmesék" / "Valós anekdoták és esetek" / "Mai, hétköznapi történet" /
"Bevezető illusztráció") that produced source-less, fabricated stories.
That block has been REMOVED from app.py entirely (the prompt no longer
exists, the tab no longer calls it) because it violated the Phase 3I
"NO GENERATED FAKE STORIES" principle. This module's retrieval action
is now the ONLY illustration content the "Illusztrációk" tab renders --
every story a user sees here is read verbatim from `illustration_units`
in the DB; the LLM only ranks/explains, never authors story content.

Its own access boundary is not about WHO the user is --
it is entirely about which retrieval MODE applies:

- non-loopback host (production/Cloud): `mode="production"` --
  `illustration_engine.retrieval.find_candidates` restricts to
  `published_illustration_units` only.
- strict loopback host (localhost/127.0.0.1/::1, reusing
  `illustration_review_ui.is_local_loopback_request` -- the SAME
  narrow check the reviewer panel uses, not a new heuristic):
  `mode="development"` -- unpublished but `qa_status='passed'` units
  become visible too, for internal QA testing. A discreet banner makes
  this explicit whenever it is active (see `_DEV_MODE_BANNER`).

Same dependency-injection pattern as `textus_workshop_ui.py`/
`sermon_workshop_ui.py`: `app.py` supplies `generate_fn=generate_text`;
this module never touches Gemini/HTTP itself.

NEVER shown to the end user: the ranking prompt, raw JSON, qa_status/
qa_issues internals, or any other reviewer-facing technical detail --
see `_render_result_card`.

Phase 3I.3: root-caused a live-vs-diagnostic-script discrepancy where
the deployed UI returned 0 results for every tested passage while a
standalone read-only diagnostic script (Phase 3I.2's audit) found real
matches on the same corpus. Root cause: `retrieve_illustrations` makes
TWO sequential logical Gemini calls per search (Stage 0 planner, then
Stage B ranker) via `app.py`'s `generate_text`, which enforces an
8-second GLOBAL cooldown between ANY two calls and returns a Hungarian
"please wait" warning STRING (not an exception, not JSON) when a call
lands inside that window -- which the second call always did, since a
single Gemini call rarely takes 8+ seconds. `parse_ranking_response`
correctly fails closed on that non-JSON string, so the symptom was 0
results on every search, deterministically, regardless of passage --
exactly what was observed. Fix: `bypass_cooldown=True` on the injected
`_llm` callback, mirroring `generate_text`'s own documented convention
for "ugyanazon gombnyomás fill/repair hívásai" (multiple logical calls
within one click). This module's two Gemini calls per click are
structurally the same case.

Also added (Phase 3I.3 point 4, fail-closed observability): in
development mode only, a "Fejlesztői diagnosztika" expander shows the
structured `RetrievalDiagnostics` from `illustration_engine.retrieval.
retrieve_illustrations_with_diagnostics` -- reason code (`ok` /
`no_intent` / `no_local_candidates` / `ranker_rejected_all` /
`planner_error` / `ranking_error`), intent field counts, Stage-A pool/
candidate counts, top local scores, Stage-B parsed/accepted counts.
Never raw LLM prompt/response text, never shown in production.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

import streamlit as st

from illustration_engine.backend_config import (
    IllustrationBackendConfigurationError,
    resolve_illustration_backend,
)
from illustration_engine.illustration_sqlite import DEFAULT_DATABASE_PATH, migrate_schema
from illustration_engine.retrieval import (
    IllustrationRetrievalResult,
    RetrievalDiagnostics,
    SupabaseIllustrationRepository,
    retrieve_illustrations_with_diagnostics,
)
from illustration_review_ui import is_local_loopback_request
from ui_components import action_row, render_info_panel, render_work_section, work_surface

_RESULTS_KEY = "ill_retrieval_results"
_MODE_KEY = "ill_retrieval_mode"
_SEARCHED_KEY = "ill_retrieval_searched"
_DIAGNOSTICS_KEY = "ill_retrieval_diagnostics"

_REASON_LABELS_HU = {
    "ok": "OK -- volt elfogadott találat",
    "no_intent": "A tervező (Stage 0) nem adott használható kulcsszót/koncepciót",
    "no_local_candidates": "Egyetlen jelölt sem érte el a helyi relevancia-küszöböt",
    "ranker_rejected_all": "A rangsoroló lefutott, de egyik jelöltet sem tartotta elég relevánsnak",
    "planner_error": "A tervező LLM-hívás hibát dobott (pl. hálózat, cooldown, API-kulcs)",
    "ranking_error": "A rangsoroló LLM-hívás hibát dobott (pl. hálózat, cooldown, API-kulcs)",
    "candidate_fetch_error": "Az illusztráció-adatbázis elérése hibát dobott (pl. hálózat, backend)",
}

_DEV_MODE_BANNER = "⚠️ Belső QA corpus — még nem publikált tételek."
_EMPTY_RESULT_MESSAGE = "A tudástárban most nem találtam megfelelő, ellenőrzött illusztrációt."
# 2026-09 runtime retrieval cutover: DELIBERATELY a different message and a
# different `tone` (see _resolve_repository_and_mode's call site) from
# _EMPTY_RESULT_MESSAGE -- a misconfigured/unreachable backend must never
# read to the user as "nincs találat" (a normal, expected outcome most of
# the time by design). This is the direct fix for the exact 2026-09
# provenance-audit incident that started this whole investigation: a
# production deployment silently querying an empty database produced a
# message indistinguishable from "genuinely found nothing."
_BACKEND_ERROR_MESSAGE = (
    "Az illusztráció-keresés jelenleg nem elérhető ezen a környezeten "
    "(konfigurációs hiba). Ez NEM azt jelenti, hogy nincs megfelelő "
    "illusztráció -- a keresés meg sem tudott indulni."
)
_CANDIDATE_FETCH_ERROR_MESSAGE = (
    "Az illusztráció-adatbázis elérése most hibát adott (pl. hálózati "
    "probléma). Ez NEM azt jelenti, hogy nincs megfelelő illusztráció -- "
    "próbáld újra egy kicsit később."
)


@st.cache_resource(show_spinner=False)
def _get_connection() -> sqlite3.Connection:
    """Local SQLite path -- used only when `resolve_illustration_backend()`
    returns `"local"`. Deliberately a SEPARATE connection/cache from
    `illustration_review_ui._get_connection()` -- two independent UI
    surfaces (internal reviewer tool vs. public retrieval feature) with
    no reason to share private internals, even though both point at the
    same physical DB file (SQLite supports multiple connections to one
    file). `migrate_schema()` is idempotent/additive-only (Phase 3H) --
    self-healing here too, same reasoning as the reviewer panel."""
    connection = sqlite3.connect(str(DEFAULT_DATABASE_PATH), check_same_thread=False)
    connection.execute("PRAGMA foreign_keys = ON")
    migrate_schema(connection)
    return connection


@st.cache_resource(show_spinner=False)
def _get_supabase_repository() -> SupabaseIllustrationRepository:
    """Cached the same way `_get_connection()` already is -- one
    `SupabaseIllustrationRepository` (and, inside it, one lazily-
    resolved anon-keyed `supabase.Client`) per Streamlit process, not
    reconstructed on every search."""
    return SupabaseIllustrationRepository()


def _current_mode() -> str:
    return "development" if is_local_loopback_request() else "production"


def _is_candidate_fetch_error(diagnostics: RetrievalDiagnostics | None) -> bool:
    """Pure, independently-testable extraction of the empty-vs-error
    branch decision at the results-rendering call site -- a backend/
    network failure during a search (RetrievalDiagnostics.reason ==
    "candidate_fetch_error") must render as a distinct error state, never
    merged into the "Nincs megfelelő találat" empty-result message."""
    return diagnostics is not None and diagnostics.reason == "candidate_fetch_error"


def _resolve_data_source():
    """Resolves BOTH which backend to use (`TEXTUS_ILLUSTRATION_BACKEND`,
    fail-closed in cloud -- see `illustration_engine.backend_config`) and
    the effective retrieval `mode`.

    Returns `(connection_or_repository, mode)`. Raises
    `IllustrationBackendConfigurationError` if the backend is
    misconfigured -- the caller MUST catch this SEPARATELY from any
    retrieval-outcome branch (see `_BACKEND_ERROR_MESSAGE`'s docstring
    note) and must never let it reach the "nincs találat" UI path.

    `SupabaseIllustrationRepository` only supports `mode="production"`
    (no Supabase-side development/QA-preview RPC exists yet) -- so when
    the resolved backend is `"supabase"`, the effective mode is always
    forced to `"production"` regardless of loopback-host detection. A
    developer who explicitly opts into `TEXTUS_ILLUSTRATION_BACKEND=
    supabase` locally sees exactly what a real anon user would see, by
    design; the SQLite dev-mode QA-preview path is unaffected and
    continues to work exactly as before whenever the backend is
    `"local"` (the unset-in-non-cloud default)."""
    backend = resolve_illustration_backend()
    if backend == "supabase":
        return _get_supabase_repository(), "production"
    return _get_connection(), _current_mode()


def _render_result_card(item: IllustrationRetrievalResult) -> None:
    with st.container(border=True):
        st.markdown(f"**{item.title_hu}**")
        st.write(item.summary_hu)
        with st.expander("Teljes történet elolvasása"):
            st.write(item.modern_hu_text)
            if item.moral_hu:
                st.caption(f"Tanulság: {item.moral_hu}")
        caption_parts = [f"Forrás: {item.source_attribution}"]
        if item.homiletic_functions:
            caption_parts.append(f"Homiletikai irány: {', '.join(item.homiletic_functions)}")
        st.caption(" · ".join(caption_parts))


def _render_dev_diagnostics(diag: RetrievalDiagnostics) -> None:
    """Phase 3I.3 point 4 -- structured, content-free diagnosis, dev/
    localhost mode only. Never called in production (see the `mode ==
    "development"` guard at the call site)."""
    with st.expander("🔧 Fejlesztői diagnosztika (csak localhoston látható)", expanded=False):
        st.caption(_REASON_LABELS_HU.get(diag.reason, diag.reason))
        st.code(
            "\n".join([
                f"reason: {diag.reason}",
                f"intent.keywords_hu: {len(diag.intent.keywords_hu)} db",
                f"intent.concepts_hu: {len(diag.intent.concepts_hu)} db",
                f"intent.topics: {list(diag.intent.topics)}",
                f"intent.preferred_homiletic_functions: {list(diag.intent.preferred_homiletic_functions)}",
                f"stage_a_pool_size: {diag.stage_a_pool_size}",
                f"stage_a_candidate_count: {diag.stage_a_candidate_count}",
                f"stage_a_top_scores: {list(diag.stage_a_top_scores)}",
                f"stage_b_parsed_count: {diag.stage_b_parsed_count}",
                f"stage_b_accepted_count: {diag.stage_b_accepted_count}",
                f"final_count: {diag.final_count}",
            ]),
            language="text",
        )


def render_illustration_search_action(*, generate_fn: Callable[..., str] | None = None) -> None:
    """Renders the "Illusztrációk" tab's entire content.

    Phase 3I.1: this is no longer a supplementary action bolted onto a
    free-form generative block -- it IS the tab. Call this once, directly
    inside `with tabs[5]:` in `app.py`, with nothing else alongside it."""
    render_work_section(
        title="Illusztrációk",
        body=(
            "A meglévő textus alapján keres a Textus saját, ember és gép "
            "által ellenőrzött illusztráció-adatbázisában. A történet "
            "mindig az adatbázisból származik -- az AI csak rangsorol és "
            "magyarázza a kapcsolódást, sosem talál ki új történetet."
        ),
        context="Textusműhely",
    )

    try:
        connection, mode = _resolve_data_source()
    except IllustrationBackendConfigurationError:
        # Deliberately its OWN branch, checked BEFORE the search button is
        # even rendered -- a misconfigured backend must never be reachable
        # via the same code path as "search ran, found nothing" (see
        # _BACKEND_ERROR_MESSAGE's docstring note for why this distinction
        # exists).
        render_info_panel(title="Konfigurációs hiba", body=_BACKEND_ERROR_MESSAGE, tone="danger")
        return

    if mode == "development":
        st.info(_DEV_MODE_BANNER)

    passage = (st.session_state.get("last_igehely") or "").strip()

    with work_surface("illustration_retrieval"):
        with action_row("illustration_retrieval_search"):
            if st.button("Illusztrációk keresése", key="ill_retrieval_search_btn", type="primary"):
                if not passage:
                    st.warning("Add meg az igeszakaszt az „Igehely” fülön, mielőtt keresel.")
                elif generate_fn is None:
                    st.warning("Nincs elérhető AI-hívás ehhez a funkcióhoz.")
                else:
                    with st.spinner("Illusztrációk keresése…"):
                        passage_text = str(st.session_state.get("passage_text") or "")
                        occasion = str(st.session_state.get("occasion_label") or "").strip()

                        def _llm(prompt: str) -> str:
                            return generate_fn(
                                prompt,
                                enable_google_search=False,
                                tab_label="Illusztrációk",
                                use_cache=False,
                                include_brevity_directive=False,
                                # Phase 3I.3 fix: retrieve_illustrations makes TWO
                                # sequential logical calls per search (planner,
                                # then ranker). Without this, generate_text's
                                # global 8s cooldown blocked the second call on
                                # (almost) every search, returning a "please
                                # wait" warning string instead of JSON -- which
                                # parse_ranking_response correctly, silently,
                                # failed closed on, yielding 0 results EVERY
                                # time regardless of passage. Mirrors generate_
                                # text's own documented convention for multiple
                                # logical calls within one click ("ugyanazon
                                # gombnyomás fill/repair hívásai").
                                bypass_cooldown=True,
                            )

                        results, diagnostics = retrieve_illustrations_with_diagnostics(
                            connection,
                            mode=mode,
                            passage_reference=passage,
                            passage_text=passage_text,
                            theme="",
                            occasion=occasion,
                            llm_generate=_llm,
                        )
                        st.session_state[_RESULTS_KEY] = results
                        st.session_state[_MODE_KEY] = mode
                        st.session_state[_SEARCHED_KEY] = True
                        st.session_state[_DIAGNOSTICS_KEY] = diagnostics

        if st.session_state.get(_SEARCHED_KEY):
            results: list[IllustrationRetrievalResult] = st.session_state.get(_RESULTS_KEY) or []
            diag_for_empty_check: RetrievalDiagnostics | None = st.session_state.get(_DIAGNOSTICS_KEY)
            if not results and _is_candidate_fetch_error(diag_for_empty_check):
                # A backend/network failure DURING a search attempt -- distinct
                # from a genuine 0-candidate outcome; never rendered as "nincs
                # találat" (see _CANDIDATE_FETCH_ERROR_MESSAGE's docstring note).
                render_info_panel(title="Átmeneti hiba", body=_CANDIDATE_FETCH_ERROR_MESSAGE, tone="danger")
            elif not results:
                render_info_panel(
                    title="Nincs megfelelő találat",
                    body=_EMPTY_RESULT_MESSAGE,
                    tone="neutral",
                )
            else:
                for item in results:
                    _render_result_card(item)
            # Phase 3I.3: development/localhost only -- never in production.
            diag: RetrievalDiagnostics | None = st.session_state.get(_DIAGNOSTICS_KEY)
            if mode == "development" and diag is not None:
                _render_dev_diagnostics(diag)
        else:
            render_info_panel(
                title="Még nincs keresés",
                body="Kattints az „Illusztrációk keresése” gombra az igeszakaszhoz illő, ellenőrzött történetekért.",
                tone="neutral",
            )


__all__ = ["render_illustration_search_action"]
