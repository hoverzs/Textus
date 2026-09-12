"""Phase 2C §20 — Greek contextual-analysis panel, wired directly into the
REAL production Greek word-detail renderer (``bible_engine.greek_analysis_ui
._render_analysis_panel``), never a separate demo/alternate path — the
explicit lesson from the Hebrew Phase 2E wiring bug (task instruction:
"Avoid the Hebrew mistake where Phase 2E existed but was only connected to
a demo/alternate renderer").

Purely additive: when ``generate_text_fn`` is ``None`` (every existing call
site that does not pass it), this renders nothing — every other part of the
Greek word panel is byte-identical to before this phase. Generation is
strictly button-gated (never on initial render or word selection — task
§17/§21); one cached AI call serves every word click within the same verse
(task §16).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import streamlit as st

from bible_engine.greek_analysis_bundle import SYNTAX_GROUNDING_NONE, GreekAnalysisBundle, GreekVerseAnalysis
from bible_engine.greek_analysis_repository import attach_syntax_via_repository, get_default_greek_analysis_repository
from bible_engine.greek_analysis_service import get_greek_analysis
from bible_engine.greek_contextual_analysis import CONTEXTUAL_ANALYSIS_PROMPT_VERSION, GreekContextualAnalysis
from bible_engine.greek_contextual_analysis_cache import (
    GreekContextualAnalysisCache,
    get_or_request_greek_contextual_analysis,
)
from bible_engine.greek_contextual_analysis_service import STATUS_OK
from bible_engine.tagnt_parser import GreekToken


def _greek_contextual_analysis_cache() -> GreekContextualAnalysisCache:
    # session_state, NOT st.cache_resource — cache_resource is PROCESS-
    # global (persists across every Streamlit session, including every
    # AppTest.from_function() run within one pytest process), which would
    # silently leak cached AI results between independent test sessions.
    # session_state is per-session, matching hebrew_text_demo.py's own
    # ``_hebrew_contextual_analysis_cache`` exactly.
    return st.session_state.setdefault("_greek_contextual_analysis_cache", GreekContextualAnalysisCache())


def _greek_bundle_for_token(reference: str, selected: GreekToken) -> GreekAnalysisBundle | None:
    from bible_engine.greek_construction_detection import attach_detected_patterns

    try:
        bundle = get_greek_analysis(reference)
    except (FileNotFoundError, ValueError):
        return None
    repository = get_default_greek_analysis_repository()
    try:
        bundle = attach_syntax_via_repository(bundle, repository)
    except Exception:  # noqa: BLE001 — syntax attachment failure must never block the deterministic panel
        return bundle
    try:
        return attach_detected_patterns(bundle)
    except Exception:  # noqa: BLE001 — pattern detection failure must never block the panel
        return bundle


def render_greek_contextual_analysis_panel(
    selected: GreekToken,
    reference: str,
    *,
    generate_text_fn: Callable[..., str] | None,
    key_prefix: str = "greek_original",
    model_id: str = "gemini-2.5-flash",
    generate_kwargs: dict[str, object] | None = None,
) -> None:
    """Additive contextual-grammar/syntax interpretation for the SAME
    token the deterministic card above already shows, grounded on the
    ``GreekAnalysisBundle``, never on raw text. Degrades to a small notice
    on any failure — the deterministic card above is never affected."""
    if generate_text_fn is None:
        return

    bundle = _greek_bundle_for_token(reference, selected)
    if bundle is None:
        return
    verse: GreekVerseAnalysis | None = next(
        (v for v in bundle.verses if v.chapter == selected.chapter and v.verse == selected.verse), None
    )
    if verse is None:
        return

    st.markdown("#### Nyelvtani és mondattani elemzés (AI)")

    from bible_engine.greek_dataset_version import greek_dataset_version_signature

    dataset_signature = greek_dataset_version_signature()
    contextual_cache = _greek_contextual_analysis_cache()
    cached = contextual_cache.get(
        verse_id=verse.verse_id, dataset_version_signature=dataset_signature,
        prompt_version=CONTEXTUAL_ANALYSIS_PROMPT_VERSION, model_id=model_id,
    )

    button_key = f"{key_prefix}_contextual_analysis_run_{verse.verse_id}"
    if cached is None:
        st.caption("Ehhez a vershez még nincs legenerálva kontextuális nyelvtani/mondattani elemzés.")
        if st.button("Kontextuális elemzés generálása", key=button_key):
            with st.spinner("Kontextuális nyelvtani elemzés készül..."):
                result = get_or_request_greek_contextual_analysis(
                    verse, dataset_version_signature=dataset_signature, model_id=model_id,
                    generate_fn=generate_text_fn, cache=contextual_cache, generate_kwargs=generate_kwargs,
                )
            if result.status != STATUS_OK:
                st.warning(
                    "A kontextuális elemzés jelenleg nem érhető el (időtúllépés vagy hiba történt). "
                    "A determinisztikus szó- és mondattani adatok fent továbbra is elérhetők."
                )
                return
            st.rerun()
        return

    analysis: GreekContextualAnalysis = cached.analysis  # type: ignore[assignment]
    token_analysis = next((t for t in verse.tokens if t.word_index == selected.word_index), None)
    shown_construction_ids = _render_greek_contextual_word_note(
        analysis, token_analysis.token_id if token_analysis else None
    )
    _render_greek_contextual_verse_sections(analysis, already_shown_construction_ids=shown_construction_ids)


def _render_greek_contextual_word_note(analysis: GreekContextualAnalysis, token_id: str | None) -> frozenset[int]:
    if token_id is None:
        return frozenset()
    note = next((n for n in analysis.word_notes if n.token_id == token_id), None)
    if note is None:
        return frozenset()
    if note.lexical_basic_meaning_hu:
        st.markdown(f"**Lexikai alapjelentés:** {note.lexical_basic_meaning_hu}")
    if note.contextual_meaning_hu:
        st.markdown(f"**Kontextuális jelentés:** {note.contextual_meaning_hu}")
    if note.morphological_explanation_hu:
        st.markdown(f"**Nyelvtani magyarázat:** {note.morphological_explanation_hu}")
    if note.syntax_role_hu:
        st.markdown(f"**Mondattani szerep:** {note.syntax_role_hu}")
    if note.translation_note_hu:
        st.caption(f"Fordítási megjegyzés: {note.translation_note_hu}")

    related_constructions = [c for c in analysis.construction_notes if token_id in c.token_ids]
    if related_constructions:
        st.markdown("**Kapcsolódó konstrukciók:**")
        for construction in related_constructions:
            st.markdown(f"- **{construction.title_hu}** — {construction.explanation_hu}")
    return frozenset(id(c) for c in related_constructions)


def _render_greek_contextual_verse_sections(
    analysis: GreekContextualAnalysis, *, already_shown_construction_ids: frozenset[int] = frozenset()
) -> None:
    remaining_constructions = [
        c for c in analysis.construction_notes if id(c) not in already_shown_construction_ids
    ]
    if remaining_constructions:
        with st.expander("Mondattani összefoglalás — kapcsolódó konstrukciók", expanded=False):
            for construction in remaining_constructions:
                st.markdown(f"**{construction.title_hu}**")
                st.markdown(construction.explanation_hu)
                if construction.translation_significance_hu:
                    st.caption(construction.translation_significance_hu)

    if analysis.syntax_summary.summary_hu:
        with st.expander("Mondattani összefoglalás", expanded=False):
            st.markdown(analysis.syntax_summary.summary_hu)

    if analysis.translation_notes:
        with st.expander("Fordítási megjegyzések", expanded=False):
            for note in analysis.translation_notes:
                st.markdown(f"- {note}")

    if analysis.exegetical_notes:
        with st.expander("Exegetikai megjegyzések", expanded=False):
            for note in analysis.exegetical_notes:
                st.markdown(f"- {note}")

    if analysis.warnings:
        with st.expander("Figyelmeztetések", expanded=False):
            for warning in analysis.warnings:
                st.markdown(f"- {warning}")

    if analysis.grounding_status == SYNTAX_GROUNDING_NONE:
        st.caption("Ehhez a vershez nincs determinisztikus mondattani adat — csak alaktani/lexikai magyarázat.")


__all__ = ["render_greek_contextual_analysis_panel"]
