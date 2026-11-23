"""Textus 2.0 Textusműhely — kézi UI + főgondolat MI-segéd bekötés.

A textus fő gondolata és a továbbvihető felismerések felülete.
A Gemini-hívást a hívó által átadott `generate_fn` végzi
(általában az app.py `generate_text` függvénye).
Nem importál az app.py-ból (nincs körkörös import).
"""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from textus_main_idea_ai import (
    MainIdeaAssessmentResult,
    MainIdeaSuggestionResult,
    assess_user_main_idea,
    suggest_text_main_idea,
)
from textus_summary_ai import (
    TextSummarySuggestionResult,
    suggest_text_summary,
)
from textus_workshop_data import (
    add_approved_insight,
    ensure_text_workshop_state,
    remove_approved_insight,
    save_main_idea_assessment,
    save_main_idea_suggestions,
    save_text_summary_suggestions,
    update_text_main_idea,
    update_text_summary_fields,
)
from ui_components import (
    action_row,
    mi_helper_zone,
    render_work_section,
    work_surface,
)

GenerateFn = Callable[..., str]

_STATUS_LABELS = {
    "draft": "Vázlat",
    "approved": "Jóváhagyva",
}

_INSIGHT_SOURCES = [
    "Saját megfigyelés",
    "Áttekintés",
    "Eredeti szöveg",
    "Exegézis",
    "Kortörténet",
    "Teológia",
]

_INSIGHT_CATEGORIES = [
    "Fő gondolat",
    "Szerkezet",
    "Kulcsszó vagy kifejezés",
    "Teológiai hangsúly",
    "Emberi helyzet",
    "Isten cselekvése és kegyelme",
    "Krisztus-kapcsolat",
    "Kép vagy kontraszt",
    "Nyitott kérdés",
    "Egyéb",
]

_SOURCE_REVIEW = [
    ("overview", "Áttekintés"),
    ("original_text", "Eredeti szöveg"),
    ("exegesis", "Exegézis"),
    ("history", "Kortörténet"),
    ("theology", "Teológia"),
]

_ASSESSMENT_FIELD_LABELS = [
    ("text_fidelity", "Szöveghűség"),
    ("clarity", "Világosság"),
    ("unity", "Egység"),
    ("theological_accuracy", "Teológiai pontosság"),
    ("scope", "Terjedelem"),
    ("statement_quality", "Állítás minősége"),
    ("application_confusion", "Alkalmazással való keveredés"),
]

_MAIN_IDEA_SOURCE = "A textus fő gondolata"
_MAIN_IDEA_CATEGORY = "Fő gondolat"

# Widget / technikai kulcsok — csak session UI, nem project_data
_KEY_IDEA_INPUT = "tw_main_idea_input"
_RESYNC_FLAG = "_tw_ui_resync"
_ADOPT_PENDING = "_tw_main_idea_adopt_pending"


def _session_str(*keys: str) -> str:
    for key in keys:
        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if val is not None and not isinstance(val, str):
            text = str(val).strip()
            if text:
                return text
    return ""


def _session_passage_text() -> str:
    for key in ("passage_text", "passage_text_input"):
        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.replace("\r\n", "\n").replace("\r", "\n")
    return ""


def _apply_pending_adopt_if_needed() -> None:
    """Átvétel: widget ELŐTT alkalmazza a pending mondatot (pending + rerun).

    Csak a szerkeszthető mezőbe másol; nem hagyja jóvá automatikusan.
    """
    pending = st.session_state.pop(_ADOPT_PENDING, None)
    if pending is None:
        return
    text = str(pending).strip()
    st.session_state[_KEY_IDEA_INPUT] = text
    update_text_main_idea(st.session_state, text, "draft")


def _apply_tw_ui_resync_if_needed() -> None:
    """Widgetkulcsok szinkronja a tartós text_workshop adatokkal (widget előtt)."""
    tw = ensure_text_workshop_state(st.session_state)
    force = bool(st.session_state.pop(_RESYNC_FLAG, False))
    idea = tw.get("text_main_idea") or ""

    if force or _KEY_IDEA_INPUT not in st.session_state:
        st.session_state[_KEY_IDEA_INPUT] = idea


def flush_textus_workshop_from_widgets() -> None:
    """Élő Streamlit widgetek → tartós `text_workshop` (ha a widget létezik).

    A fejléc Mentés / autosave előtt hívandó, hogy a még nem „Mentés
    vázlatként” gombbal elmentett fő gondolat se vesszen el — ugyanaz a
    minta, mint a Bibliai szöveg és az Igehirdetési műhely flush.
    Nem változtatja a jóváhagyási státuszokat (draft/approved).
    Projektváltás után, ha a UI-resync még nem futott, előbb a tartós
    adatból frissíti a widgetet, hogy régi session-érték ne írjon felül.
    """
    ensure_text_workshop_state(st.session_state)
    _apply_tw_ui_resync_if_needed()

    if _KEY_IDEA_INPUT in st.session_state:
        tw = ensure_text_workshop_state(st.session_state)
        tw["text_main_idea"] = (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()

    flush_text_summary_from_widgets()


def _request_adopt_sentence(sentence: str) -> None:
    """Mondat átvétele a kézi mezőbe — következő futásban, widget előtt."""
    st.session_state[_ADOPT_PENDING] = str(sentence or "").strip()
    st.rerun()


def _suggestion_payload_from_result(result: MainIdeaSuggestionResult) -> dict[str, Any]:
    return {
        "recommended": result.recommended,
        "expanded_summary": result.expanded_summary or "",
        "alternatives": list(result.alternatives),
        "reasoning_summary": result.reasoning_summary,
        "textual_basis": list(result.textual_basis),
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _assessment_payload_from_result(result: MainIdeaAssessmentResult) -> dict[str, Any]:
    return {
        "assessment": result.assessment.to_dict(),
        "strengths": list(result.strengths),
        "revision_priorities": list(result.revision_priorities),
        "revised_version": result.revised_version,
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _collect_ai_kwargs(*, user_main_idea: str) -> dict[str, Any]:
    """Sessionből MI-bemenet; illusztráció / aktualizálás / ének / vázlat nélkül."""
    history = _session_str("history")
    return {
        "passage": _session_str("last_igehely", "igehely_input"),
        "passage_text": _session_passage_text(),
        "occasion": _session_str("last_alkalom", "alkalom_input"),
        "user_focus": _session_str("last_sajat", "sajat_input"),
        "approved_insights": (
            ensure_text_workshop_state(st.session_state).get("approved_insights") or []
        ),
        "exegesis": _session_str("exegesis"),
        "original_text": _session_str("original_text"),
        "theology": _session_str("theology"),
        "overview": _session_str("overview"),
        "historical_context": history,
        "user_main_idea": (user_main_idea or "").strip(),
        "include_historical_context": bool(history),
    }


def _user_facing_error(result_ok: bool, error_message: str, *, fallback: str) -> str:
    if result_ok:
        return ""
    msg = (error_message or "").strip()
    if not msg:
        return fallback
    # Ne szivárogtassunk hosszú technikai dumpot / kulcsot
    if len(msg) > 280:
        return fallback
    lower = msg.casefold()
    if "api key" in lower or "apikey" in lower or "x-goog-api-key" in lower:
        return fallback
    return msg


def _render_source_materials_expander() -> None:
    """Csak olvasható áttekintés a már elkészült műhelyanyagokról."""
    with st.expander("Korábbi műhelyanyagok áttekintése", expanded=False):
        any_content = False
        for key, label in _SOURCE_REVIEW:
            text = (st.session_state.get(key) or "").strip()
            if not text:
                continue
            any_content = True
            with st.expander(label, expanded=False):
                st.markdown(text)

        if not any_content:
            st.info(
                "Még nincs áttekinthető műhelyanyag. "
                "Ha az előző szakaszokban generálsz tartalmat, itt fog megjelenni."
            )


def _render_suggestion_results() -> None:
    tw = ensure_text_workshop_state(st.session_state)
    sugs = tw.get("main_idea_suggestions")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslatok")
    generated_at = (tw.get("main_idea_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    recommended = (sugs.get("recommended") or "").strip()
    expanded = (sugs.get("expanded_summary") or "").strip()
    alternatives = sugs.get("alternatives") or []
    if not isinstance(alternatives, list):
        alternatives = []

    # Elsődleges: ajánlott mondat + rövid kifejtés + átvétel (csak főmondat)
    if recommended:
        with st.container(border=True):
            st.markdown("**Ajánlott fő gondolat**")
            st.markdown(recommended)
            if expanded:
                st.caption("Rövid kifejtés")
                st.markdown(expanded)
            if st.button("Átveszem", key="tw_mi_adopt_recommended"):
                _request_adopt_sentence(recommended)
    else:
        st.info(
            "Nincs ajánlott fő gondolat (elégtelen adat vagy a modell üresen hagyta). "
            "A részletek a „Mi alapján készült?” részben vannak."
        )

    # Alternatívák — alapból összecsukva
    alt_items: list[str] = []
    for alt in alternatives[:2]:
        text = (alt or "").strip() if isinstance(alt, str) else str(alt or "").strip()
        if text:
            alt_items.append(text)
    if alt_items:
        with st.expander("További javaslatok", expanded=False):
            for idx, text in enumerate(alt_items):
                with st.container(border=True):
                    st.markdown(f"**Alternatíva {idx + 1}**")
                    st.markdown(text)
                    if st.button("Átveszem", key=f"tw_mi_adopt_alt_{idx}"):
                        _request_adopt_sentence(text)

    reasoning = (sugs.get("reasoning_summary") or "").strip()
    basis = sugs.get("textual_basis") or []
    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    has_basis = isinstance(basis, list) and any(str(x).strip() for x in basis)
    has_warnings = isinstance(warnings, list) and any(str(x).strip() for x in warnings)
    has_missing = isinstance(missing, list) and any(str(x).strip() for x in missing)

    if reasoning or has_basis or has_warnings or has_missing:
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.markdown("**Indoklás**")
                st.markdown(reasoning)
            if has_basis:
                st.markdown("**Szövegbeli alapok**")
                for item in basis:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")
            if has_warnings:
                st.markdown("**Figyelmeztetések**")
                for item in warnings:
                    line = str(item or "").strip()
                    if line:
                        st.warning(line)
            if has_missing:
                st.markdown("**Hiányzó információk**")
                for item in missing:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")


def _render_assessment_results() -> None:
    tw = ensure_text_workshop_state(st.session_state)
    assessment_payload = tw.get("main_idea_assessment")
    if not isinstance(assessment_payload, dict):
        return

    fields = assessment_payload.get("assessment") or {}
    if not isinstance(fields, dict):
        fields = {}
    strengths = assessment_payload.get("strengths") or []
    priorities = assessment_payload.get("revision_priorities") or []
    revised = (assessment_payload.get("revised_version") or "").strip()
    warnings = assessment_payload.get("warnings") or []

    with st.expander("Szakmai értékelés részletei", expanded=False):
        if any(str(fields.get(k) or "").strip() for k, _ in _ASSESSMENT_FIELD_LABELS):
            st.markdown("**Szempontok**")
            for key, label in _ASSESSMENT_FIELD_LABELS:
                text = str(fields.get(key) or "").strip()
                if text:
                    st.markdown(f"**{label}:** {text}")

        if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
            st.markdown("**Erősségek**")
            for item in strengths[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        if isinstance(priorities, list) and any(str(x).strip() for x in priorities):
            st.markdown("**Javítási szempontok**")
            for item in priorities[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        if revised:
            st.markdown("**Átdolgozott javaslat**")
            st.markdown(revised)
            if st.button(
                "Átdolgozott változat átvétele",
                key="tw_mi_adopt_revised",
            ):
                _request_adopt_sentence(revised)
        else:
            st.caption(
                "Nincs átdolgozott javaslat (üres mező vagy elégtelen elemzési alap)."
            )

        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            st.markdown("**Figyelmeztetések**")
            for item in warnings:
                line = str(item or "").strip()
                if line:
                    st.warning(line)


def _run_suggest(generate_fn: GenerateFn) -> None:
    idea_draft = (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()
    kwargs = _collect_ai_kwargs(user_main_idea=idea_draft)
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt javaslatot kérsz."
        )
        return

    with st.spinner(
        "A textus fő gondolatának lehetséges megfogalmazásait vizsgálom…"
    ):
        result = suggest_text_main_idea(**kwargs, generate_fn=generate_fn)

    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
            )
        )
        return

    save_main_idea_suggestions(
        st.session_state,
        _suggestion_payload_from_result(result),
    )
    if not (result.recommended or "").strip():
        st.info(
            "A rendelkezésre álló anyag alapján nem készült felelős ajánlott "
            "fő gondolat. Nézd meg a hiányzó információkat és figyelmeztetéseket."
        )
    else:
        st.success("A javaslatok elkészültek.")


def _run_assess(generate_fn: GenerateFn) -> None:
    idea = (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()
    if not idea:
        st.warning("Nincs megfogalmazás az értékeléshez.")
        return

    kwargs = _collect_ai_kwargs(user_main_idea=idea)
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt értékelést kérsz."
        )
        return

    with st.spinner(
        "A megfogalmazást textushűségi és szakmai szempontból vizsgálom…"
    ):
        result = assess_user_main_idea(**kwargs, generate_fn=generate_fn)

    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="Az értékelés nem sikerült. Próbáld újra később.",
            )
        )
        return

    save_main_idea_assessment(
        st.session_state,
        _assessment_payload_from_result(result),
    )
    st.success("Az értékelés elkészült.")


def render_text_main_idea_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """A textus fő gondolata: kézi szerkesztő + opcionális MI-segéd."""
    _apply_pending_adopt_if_needed()
    _apply_tw_ui_resync_if_needed()
    ensure_text_workshop_state(st.session_state)

    render_work_section(
        title="A textus fő gondolata",
        context="Textusműhely",
    )

    with work_surface("tw_main_idea"):
        # Látható mezőcímke és egymás melletti, balra zárt műveleti gombok
        # (UI/UX-audit 2026-11-23, V15). A kulcsok és a műveletek változatlanok.
        st.text_area(
            "Fogalmazd meg a textus fő gondolatát egy mondatban",
            key=_KEY_IDEA_INPUT,
            height=90,
            placeholder="Egyetlen, világos mondat…",
        )

        with action_row("tw_main_idea"):
            with st.container(horizontal=True, gap="small"):
                if st.button("Mentés vázlatként", key="tw_main_idea_save_draft_btn"):
                    _save_main_idea_as_draft()
                if st.button(
                    "Jóváhagyom és átadom",
                    type="primary",
                    key="tw_main_idea_approve_forward_btn",
                ):
                    _approve_main_idea_and_forward()

        tw = ensure_text_workshop_state(st.session_state)
        saved = (tw.get("text_main_idea") or "").strip()
        saved_status = tw.get("text_main_idea_status") or ""
        if saved or saved_status:
            label = _STATUS_LABELS.get(saved_status, saved_status or "—")
            st.caption(f"Elmentett állapot: **{label}**")

    idea_now = (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()
    ai_ready = generate_fn is not None
    with mi_helper_zone(
        "tw_main_idea",
        title="MI-segéd",
        body="Javaslat a már jóváhagyott anyag alapján.",
    ):
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Javaslatok készítése",
                key="tw_mi_suggest_btn",
                disabled=not ai_ready,
            ):
                if generate_fn is None:
                    st.warning("A javaslatkészítés jelenleg nem érhető el.")
                else:
                    _run_suggest(generate_fn)
        with c2:
            if st.button(
                "Saját megfogalmazás értékelése",
                key="tw_mi_assess_btn",
                disabled=(not ai_ready) or (not idea_now),
            ):
                if generate_fn is None:
                    st.warning("Az értékelés jelenleg nem érhető el.")
                else:
                    _run_assess(generate_fn)

        if not ai_ready:
            st.caption("Az MI-segéd nincs bekötve ehhez a nézethez.")

    _render_suggestion_results()
    _render_assessment_results()
    _render_source_materials_expander()


def _current_main_idea_text() -> str:
    return (st.session_state.get(_KEY_IDEA_INPUT) or "").strip()


def _insight_is_duplicate_main_idea(content: str) -> bool:
    tw = ensure_text_workshop_state(st.session_state)
    needle = (content or "").strip()
    for item in tw.get("approved_insights") or []:
        if not isinstance(item, dict):
            continue
        if (
            (item.get("source") or "") == _MAIN_IDEA_SOURCE
            and (item.get("category") or "") == _MAIN_IDEA_CATEGORY
            and (item.get("content") or "").strip() == needle
        ):
            return True
    return False


def _save_main_idea_as_draft() -> None:
    """Mező mentése vázlatként — nem kerül az approved_insights listába."""
    content = _current_main_idea_text()
    if not content:
        st.warning("Üres fő gondolatot nem lehet menteni. Írj egy mondatot.")
        return
    update_text_main_idea(st.session_state, content, "draft")
    st.success("Vázlatként elmentve.")


def _approve_main_idea_and_forward() -> None:
    """Jóváhagyás + továbbvitel a felismerésekhez (duplikáció nélkül)."""
    content = _current_main_idea_text()
    if not content:
        st.warning(
            "Üres fő gondolatot nem lehet jóváhagyni. Írj egy mondatot."
        )
        return

    update_text_main_idea(st.session_state, content, "approved")

    if _insight_is_duplicate_main_idea(content):
        st.success(
            "Jóváhagyva. Ez a fő gondolat már szerepel a továbbvihető "
            "felismerések között."
        )
        return

    add_approved_insight(
        st.session_state,
        _MAIN_IDEA_SOURCE,
        _MAIN_IDEA_CATEGORY,
        content,
    )
    st.success("Jóváhagyva és továbbvíve a felismerésekhez.")


def _render_insight_cards() -> None:
    tw = ensure_text_workshop_state(st.session_state)
    insights = list(tw.get("approved_insights") or [])
    if not insights:
        st.info(
            "Még nincs jóváhagyott felismerés. "
            "Add hozzá az elsőt az „Új felismerés hozzáadása” résznél, "
            "vagy használd a „Jóváhagyom és átadom” gombot "
            "a fő gondolat szakaszban."
        )
        return

    for item in insights:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id") or "")
        if not iid:
            continue
        source = item.get("source") or "—"
        category = item.get("category") or "—"
        content = item.get("content") or ""
        created = item.get("created_at") or ""

        with st.container(border=True):
            st.markdown(f"**Forrás:** {source}  \n**Kategória:** {category}")
            if created:
                st.caption(f"Létrehozva: {created}")
            st.markdown(content)

            confirm_key = f"tw_insight_del_confirm_{iid}"
            if st.session_state.get(confirm_key):
                st.warning("Biztosan törölni szeretnéd ezt a felismerést?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(
                        "Igen, törlés",
                        key=f"tw_insight_del_yes_{iid}",
                        type="primary",
                    ):
                        remove_approved_insight(st.session_state, iid)
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                with c2:
                    if st.button("Mégse", key=f"tw_insight_del_no_{iid}"):
                        st.session_state[confirm_key] = False
                        st.rerun()
            else:
                if st.button(
                    "Felismerés eltávolítása",
                    key=f"tw_insight_del_{iid}",
                ):
                    st.session_state[confirm_key] = True
                    st.rerun()


def render_approved_insights_section() -> None:
    """Jóváhagyott, továbbvihető felismerések gyűjtése (Gemini nélkül)."""
    ensure_text_workshop_state(st.session_state)

    render_work_section(
        title="Mit viszünk tovább?",
        context="Textusműhely",
    )

    with work_surface("tw_insights"):
        st.markdown("**Jóváhagyott felismerések**")
        _render_insight_cards()

        with st.expander("Új felismerés hozzáadása", expanded=False):
            with st.form("tw_add_insight_form", clear_on_submit=True):
                source = st.selectbox("Forrás", options=_INSIGHT_SOURCES)
                category = st.selectbox("Kategória", options=_INSIGHT_CATEGORIES)
                content = st.text_area(
                    "Tartalom",
                    placeholder="Fogalmazd meg röviden a továbbvihető felismerést…",
                    height=100,
                )
                submitted = st.form_submit_button(
                    "Jóváhagyott felismerés hozzáadása",
                    type="primary",
                )

            if submitted:
                text = (content or "").strip()
                if not text:
                    st.warning("Üres felismerést nem lehet hozzáadni.")
                else:
                    add_approved_insight(st.session_state, source, category, text)
                    st.success("Felismerés hozzáadva.")
                    st.rerun()

        with action_row("tw_insights_next"):
            if st.button(
                "Tovább az Igehirdetési műhelybe",
                key="tw_goto_sermon_workshop_btn",
            ):
                st.session_state["ui_mode"] = "sermon_workshop"
                st.rerun()


# ---------------------------------------------------------------------------
# Textusösszegzés — a Textusműhely záró, jóváhagyandó bundle-ja
# ---------------------------------------------------------------------------

_KEY_SUMMARY_BASE_TENSION = "tw_summary_base_tension_input"
_KEY_SUMMARY_FINDINGS = "tw_summary_findings_input"
_KEY_SUMMARY_THEOLOGY = "tw_summary_theology_input"
_KEY_SUMMARY_GENRE = "tw_summary_genre_input"
_SUMMARY_RESYNC_FLAG = "_tw_summary_ui_resync"
_SUMMARY_ADOPT_PENDING = "_tw_summary_adopt_pending"

_SUMMARY_FIELD_KEYS = {
    "base_tension": _KEY_SUMMARY_BASE_TENSION,
    "key_exegetical_findings": _KEY_SUMMARY_FINDINGS,
    "theological_emphases": _KEY_SUMMARY_THEOLOGY,
    "genre_structure_notes": _KEY_SUMMARY_GENRE,
}

_SUMMARY_FIELD_LABELS = [
    ("base_tension", "Alapfeszültség"),
    ("key_exegetical_findings", "Legfontosabb exegetikai felismerések"),
    ("theological_emphases", "Teológiai hangsúlyok"),
    ("genre_structure_notes", "Műfaji és szerkezeti sajátosságok"),
]


def _apply_tw_summary_ui_resync_if_needed() -> None:
    """Widgetkulcsok szinkronja a tartós text_summary adatokkal (widget előtt)."""
    tw = ensure_text_workshop_state(st.session_state)
    summary = tw.get("text_summary") or {}
    force = bool(st.session_state.pop(_SUMMARY_RESYNC_FLAG, False))
    for field_key, widget_key in _SUMMARY_FIELD_KEYS.items():
        if force or widget_key not in st.session_state:
            st.session_state[widget_key] = summary.get(field_key) or ""


def _current_summary_widget_values() -> dict[str, str]:
    return {
        field_key: (st.session_state.get(widget_key) or "").strip()
        for field_key, widget_key in _SUMMARY_FIELD_KEYS.items()
    }


def flush_text_summary_from_widgets() -> None:
    """Élő Streamlit widgetek → tartós text_summary (ha a widget létezik).

    A Mentés / autosave előtt hívandó, hogy a még nem gombbal elmentett
    szerkesztés se vesszen el — ugyanaz a minta, mint a fő gondolat flush.
    """
    ensure_text_workshop_state(st.session_state)
    _apply_tw_summary_ui_resync_if_needed()
    if any(k in st.session_state for k in _SUMMARY_FIELD_KEYS.values()):
        update_text_summary_fields(st.session_state, _current_summary_widget_values())


def _request_adopt_summary_field(field_key: str, text: str) -> None:
    """MI-javaslat mező átvétele a kézi mezőbe — következő futásban, widget előtt."""
    pending = dict(st.session_state.get(_SUMMARY_ADOPT_PENDING) or {})
    pending[field_key] = str(text or "").strip()
    st.session_state[_SUMMARY_ADOPT_PENDING] = pending
    st.rerun()


def _apply_pending_summary_adopt_if_needed() -> None:
    pending = st.session_state.pop(_SUMMARY_ADOPT_PENDING, None)
    if not isinstance(pending, dict) or not pending:
        return
    for field_key, text in pending.items():
        widget_key = _SUMMARY_FIELD_KEYS.get(field_key)
        if widget_key:
            st.session_state[widget_key] = text
    update_text_summary_fields(st.session_state, pending)


def _save_summary(*, status: str) -> None:
    fields = _current_summary_widget_values()
    if status == "approved" and not any(fields.values()):
        st.warning("Üres összegzést nem lehet jóváhagyni. Tölts ki legalább egy mezőt.")
        return
    tw = ensure_text_workshop_state(st.session_state)
    fields["main_idea"] = (tw.get("text_main_idea") or "").strip()
    update_text_summary_fields(st.session_state, fields, status=status)
    if status == "approved":
        st.success("Textusösszegzés jóváhagyva.")
    else:
        st.success("Vázlatként elmentve.")


def _stored_context_hash_is_fresh(stored_hash: str) -> bool:
    """RESET 3D-1: a RESET 3B-2-ben bevezetett `_original_text_is_fresh_
    for_summary()` mintájának ÁLTALÁNOSÍTOTT magja — egy MÁR TÁROLT
    `*_approved_context_hash` értéket vet össze az aktuális igehely/
    fordítás/bibliai szöveg szűk ujjlenyomatával, UGYANAZZAL a függvénnyel
    (`sermon_outline_engine.compute_current_passage_context_hash`), amit
    a szekciók generáláskori bélyegzése is használ (ld. `app.py::render_
    section_tab`, `app.py::render_original_text_panel`,
    `textus_workshop_data.update_text_main_idea`). Hiányzó mentett hash
    NEM minősül stale-nek (visszafelé-kompatibilitás, ugyanaz a döntés,
    mint a legacy motorban és minden korábbi RESET fázisban). Nem
    törli/módosítja a mentett tartalmat — csak eldönti, bekerülhet-e a
    textusösszegzés kontextusába."""
    stored = (stored_hash or "").strip()
    if not stored:
        return True
    try:
        from sermon_outline_engine import compute_current_passage_context_hash

        return stored == compute_current_passage_context_hash(st.session_state)
    except Exception:  # noqa: BLE001 — a javaslatkérés ne dőljön el emiatt
        return True


def _original_text_is_fresh_for_summary() -> bool:
    """RESET 3B-2: az "Eredeti szöveg" modul kimenete friss-e a
    textusösszegzés szempontjából — ld. `_stored_context_hash_is_fresh()`."""
    return _stored_context_hash_is_fresh(
        _session_str("original_text_approved_context_hash")
    )


def _exegesis_is_fresh_for_summary() -> bool:
    """RESET 3D-1: az exegézis kimenete friss-e a textusösszegzés
    szempontjából — ld. `_stored_context_hash_is_fresh()`."""
    return _stored_context_hash_is_fresh(_session_str("exegesis_approved_context_hash"))


def _theology_is_fresh_for_summary() -> bool:
    """RESET 3D-1: a teológia kimenete friss-e a textusösszegzés
    szempontjából — ld. `_stored_context_hash_is_fresh()`."""
    return _stored_context_hash_is_fresh(_session_str("theology_approved_context_hash"))


def _historical_context_is_fresh_for_summary() -> bool:
    """RESET 3D-1: a kortörténet kimenete friss-e a textusösszegzés
    szempontjából — ld. `_stored_context_hash_is_fresh()`."""
    return _stored_context_hash_is_fresh(_session_str("history_approved_context_hash"))


def _text_main_idea_is_fresh_for_summary() -> bool:
    """RESET 3D-1: a fő gondolat friss-e a textusösszegzés szempontjából
    — a hash a `text_workshop.text_main_idea_approved_context_hash`
    mezőben él (ld. `textus_workshop_data.update_text_main_idea`), nem
    egy lapos session-kulcsban."""
    tw = ensure_text_workshop_state(st.session_state)
    return _stored_context_hash_is_fresh(
        str(tw.get("text_main_idea_approved_context_hash") or "")
    )


def _run_suggest_summary(generate_fn: GenerateFn) -> None:
    tw = ensure_text_workshop_state(st.session_state)
    kwargs = {
        "passage": _session_str("last_igehely", "igehely_input"),
        "passage_text": _session_passage_text(),
        "text_main_idea": tw.get("text_main_idea") or "",
        "approved_insights": tw.get("approved_insights") or [],
        "exegesis": _session_str("exegesis"),
        "theology": _session_str("theology"),
        "historical_context": _session_str("history"),
        "original_text": _session_str("original_text"),
        "original_text_is_fresh": _original_text_is_fresh_for_summary(),
        # RESET 3D-1: ugyanaz az elv, mint az original_text-nél (RESET
        # 3B-2) — stale mező NEM kerül a szintézis kontextusába, de a
        # session-state tartalma változatlan marad.
        "exegesis_is_fresh": _exegesis_is_fresh_for_summary(),
        "theology_is_fresh": _theology_is_fresh_for_summary(),
        "historical_context_is_fresh": _historical_context_is_fresh_for_summary(),
        "text_main_idea_is_fresh": _text_main_idea_is_fresh_for_summary(),
    }
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt javaslatot kérsz."
        )
        return

    with st.spinner("A textusösszegzés mezőinek javaslatai készülnek…"):
        result: TextSummarySuggestionResult = suggest_text_summary(
            **kwargs, generate_fn=generate_fn
        )

    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
            )
        )
        return

    save_text_summary_suggestions(st.session_state, result.to_dict())
    if not any(
        (result.base_tension, result.key_exegetical_findings, result.theological_emphases)
    ):
        st.info(
            "A rendelkezésre álló anyag alapján nem készült érdemi javaslat. "
            "Nézd meg a hiányzó információkat és figyelmeztetéseket."
        )
    else:
        st.success("A javaslatok elkészültek.")


def _render_summary_suggestion_results() -> None:
    tw = ensure_text_workshop_state(st.session_state)
    summary = tw.get("text_summary") or {}
    sugs = summary.get("suggestions")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslatok")
    generated_at = (summary.get("last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    any_content = False
    for field_key, label in _SUMMARY_FIELD_LABELS:
        text = (sugs.get(field_key) or "").strip()
        if not text:
            continue
        any_content = True
        with st.container(border=True):
            st.markdown(f"**{label}**")
            st.markdown(text)
            if st.button("Átveszem", key=f"tw_summary_adopt_{field_key}"):
                _request_adopt_summary_field(field_key, text)

    if not any_content:
        st.info(
            "Nincs javaslat (elégtelen adat vagy a modell üresen hagyta). "
            "A részletek a „Mi alapján készült?” részben vannak."
        )

    reasoning = (sugs.get("reasoning_summary") or "").strip()
    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    has_warnings = isinstance(warnings, list) and any(str(x).strip() for x in warnings)
    has_missing = isinstance(missing, list) and any(str(x).strip() for x in missing)

    if reasoning or has_warnings or has_missing:
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.markdown("**Indoklás**")
                st.markdown(reasoning)
            if has_warnings:
                st.markdown("**Figyelmeztetések**")
                for item in warnings:
                    line = str(item or "").strip()
                    if line:
                        st.warning(line)
            if has_missing:
                st.markdown("**Hiányzó információk**")
                for item in missing:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")


def render_text_summary_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Textusösszegzés: a Textusműhely záró, jóváhagyandó kontextus-bundle-ja.

    Jóváhagyás után az Igehirdetési műhely ebből a bundle-ból dolgozik
    elsődleges/kizárólagos exegetikai kontextusként (nem futtat saját
    exegézist). A „Mit viszünk tovább?” jóváhagyott felismerések listája
    támogató bizonyítékként ugyanezen a felületen jelenik meg.
    """
    _apply_pending_summary_adopt_if_needed()
    _apply_tw_summary_ui_resync_if_needed()
    tw = ensure_text_workshop_state(st.session_state)
    summary = tw.get("text_summary") or {}

    render_work_section(
        title="Textusösszegzés",
        context="Textusműhely",
    )

    main_idea = (tw.get("text_main_idea") or "").strip()
    main_idea_status = tw.get("text_main_idea_status") or ""
    with work_surface("tw_summary_main_idea"):
        st.markdown("**A textus fő gondolata**")
        if main_idea:
            st.markdown(main_idea)
            if main_idea_status != "approved":
                st.caption(
                    "Még nincs jóváhagyva — érdemes előbb az „A textus fő "
                    "gondolata” szakaszon jóváhagyni."
                )
        else:
            st.info(
                "Még nincs megfogalmazva a textus fő gondolata. Töltsd ki "
                "az „A textus fő gondolata” szakaszt, mielőtt jóváhagyod "
                "az összegzést."
            )

    with work_surface("tw_summary_fields"):
        st.text_area(
            "A textus alapfeszültsége",
            key=_KEY_SUMMARY_BASE_TENSION,
            height=90,
            placeholder=(
                "Milyen belső feszültséget, kérdést vagy ellentétet hordoz "
                "maga a szakasz?"
            ),
        )
        st.text_area(
            "Legfontosabb exegetikai felismerések",
            key=_KEY_SUMMARY_FINDINGS,
            height=110,
        )
        st.text_area(
            "Teológiai hangsúlyok",
            key=_KEY_SUMMARY_THEOLOGY,
            height=110,
        )
        st.text_area(
            "Műfaji és szerkezeti sajátosságok",
            key=_KEY_SUMMARY_GENRE,
            height=90,
        )

        with action_row("tw_summary"):
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Mentés vázlatként", key="tw_summary_save_draft_btn"):
                    _save_summary(status="draft")
            with b2:
                if st.button(
                    "Jóváhagyom",
                    type="primary",
                    key="tw_summary_approve_btn",
                ):
                    _save_summary(status="approved")

        status = summary.get("status") or "draft"
        st.caption(f"Elmentett állapot: **{_STATUS_LABELS.get(status, status)}**")

    ai_ready = generate_fn is not None
    with mi_helper_zone(
        "tw_summary",
        title="MI-segéd",
        body=(
            "Egy hívással javaslatot ad az alapfeszültségre és a három "
            "kísérő mezőre a már elkészült műhelyanyag alapján. A végső "
            "megfogalmazás és jóváhagyás a prédikátor döntése."
        ),
    ):
        if st.button(
            "Javaslatok készítése",
            key="tw_summary_suggest_btn",
            disabled=not ai_ready,
        ):
            if generate_fn is None:
                st.warning("A javaslatkészítés jelenleg nem érhető el.")
            else:
                _run_suggest_summary(generate_fn)
        if not ai_ready:
            st.caption("Az MI-segéd nincs bekötve ehhez a nézethez.")

    _render_summary_suggestion_results()

    st.divider()
    render_approved_insights_section()


__all__ = [
    "flush_textus_workshop_from_widgets",
    "flush_text_summary_from_widgets",
    "render_text_main_idea_section",
    "render_approved_insights_section",
    "render_text_summary_section",
]
