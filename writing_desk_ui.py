"""Íróasztal fő munkafelület — RÚF / eredeti nyelvi olvasóblokk + munkakivonatok.

A jobb oldali jegyzet/vázlat 4B-től szűkített HTML-t szerkesztő CCv2 mező.
"""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from bible_text_ui import render_bible_text_reading_block
from components.writing_desk_draft_editor import writing_desk_draft_editor
from ui_components import (
    render_info_panel,
    render_page_intro,
    render_work_section,
    work_surface,
)
from writing_desk_chat import (
    WRITING_DESK_CHAT_INPUT_KEY,
    WRITING_DESK_CHAT_KEY,
    ensure_writing_desk_chat_state,
    send_writing_desk_chat_message,
    writing_desk_chat_messages,
)
from writing_desk_data import (
    WRITING_DESK_EXTRACT_KEYS,
    draft_content_from_widget,
    draft_html_for_editor,
    ensure_writing_desk_state,
    set_writing_desk_draft,
    writing_desk_draft_content,
    writing_desk_draft_widget_html,
    writing_desk_draft_widget_state,
)
from writing_desk_docx import (
    build_writing_desk_docx_bytes,
    writing_desk_docx_filename,
)
from writing_desk_extracts import (
    EXTRACT_LABELS,
    STATUS_MISSING_SOURCE,
    STATUS_READY,
    STATUS_STALE,
    STATUS_VALID,
    extract_error_session_key,
    generate_writing_desk_extract,
    inspect_writing_desk_extract,
)


WRITING_DESK_MODE = "writing_desk"
WRITING_DESK_LABEL = "Íróasztal"
WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX = "writing_desk_original_language"
WRITING_DESK_BIBLE_VIEW_KEY = "writing_desk_bible_text_view_mode"
WRITING_DESK_DRAFT_WIDGET_KEY = "writing_desk_draft_input"
WRITING_DESK_DRAFT_RESYNC_FLAG = "_wd_draft_resync"
WRITING_DESK_DRAFT_RESYNC_BUMPED_KEY = "_wd_draft_resync_bumped"
WRITING_DESK_DRAFT_REVISION_KEY = "_wd_draft_revision"
_DRAFT_TEXT_AREA_HEIGHT_PX = 700
WORK_MATERIAL_SECTIONS: tuple[str, ...] = tuple(
    EXTRACT_LABELS[key] for key in WRITING_DESK_EXTRACT_KEYS
)

GenerateFn = Callable[..., str]


def writing_desk_draft_revision() -> int:
    raw = st.session_state.get(WRITING_DESK_DRAFT_REVISION_KEY) or 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def bump_writing_desk_draft_revision() -> int:
    """Projektváltás / import / 4C inject: a frontend DOM-ot újra kell tölteni."""
    nxt = writing_desk_draft_revision() + 1
    st.session_state[WRITING_DESK_DRAFT_REVISION_KEY] = nxt
    return nxt


def _seed_writing_desk_draft_widget(content: Any, *, bump_revision: bool) -> None:
    st.session_state[WRITING_DESK_DRAFT_WIDGET_KEY] = writing_desk_draft_widget_state(
        content
    )
    if bump_revision:
        bump_writing_desk_draft_revision()


def begin_writing_desk_draft_resync() -> None:
    """Új munka / projektváltás / import: durable a forrás a következő editor-mountig.

    A widgetkulcsot azonnal a tartós draftból tölti. A revisiont az első
    `apply_writing_desk_draft_resync_if_needed` emeli, hogy a CCv2 DOM
    cserélődjön. A flag addig él, amíg az editor a durable HTML-lel
    mountol — addig widget→durable tiltott.
    """
    desk = ensure_writing_desk_state(st.session_state)
    st.session_state[WRITING_DESK_DRAFT_RESYNC_FLAG] = True
    st.session_state.pop(WRITING_DESK_DRAFT_RESYNC_BUMPED_KEY, None)
    _seed_writing_desk_draft_widget(
        writing_desk_draft_content(desk),
        bump_revision=False,
    )


def consume_writing_desk_draft_resync_flag() -> None:
    st.session_state.pop(WRITING_DESK_DRAFT_RESYNC_FLAG, None)
    st.session_state.pop(WRITING_DESK_DRAFT_RESYNC_BUMPED_KEY, None)


def apply_writing_desk_draft_resync_if_needed() -> None:
    """Widgetkulcs szinkronja a tartós writing_desk.draft adattal (widget előtt).

    A resync flaget nem fogyasztja: a widget→durable tiltás az editor
    durable-mountjáig éljen, különben a status-bar flush / CCv2 callback
    a régi html state-et visszaírná.
    """
    desk = ensure_writing_desk_state(st.session_state)
    force = bool(st.session_state.get(WRITING_DESK_DRAFT_RESYNC_FLAG))
    content = writing_desk_draft_content(desk)
    current = st.session_state.get(WRITING_DESK_DRAFT_WIDGET_KEY)
    missing = WRITING_DESK_DRAFT_WIDGET_KEY not in st.session_state
    if force or missing:
        bump = force and not bool(st.session_state.get(WRITING_DESK_DRAFT_RESYNC_BUMPED_KEY))
        _seed_writing_desk_draft_widget(content, bump_revision=bump)
        if force:
            st.session_state[WRITING_DESK_DRAFT_RESYNC_BUMPED_KEY] = True
        return
    if isinstance(current, str):
        st.session_state[WRITING_DESK_DRAFT_WIDGET_KEY] = writing_desk_draft_widget_state(
            current
        )


def _writing_desk_draft_project_sync_pending() -> bool:
    """Projektváltás / import / új munka: a durable draft a forrás, ne a widget."""
    return bool(
        st.session_state.get(WRITING_DESK_DRAFT_RESYNC_FLAG)
        or st.session_state.get("_pending_project_widget_sync")
    )


def commit_writing_desk_draft_from_widget() -> None:
    """Jegyzetmező → tartós `writing_desk.draft.content`.

    Normál szerkesztés és `on_html_change` út. Projektváltáskor / importnál /
    új munkánál nem ír, hogy a régi widgetérték ne írja felül az új draftot.
    """
    if _writing_desk_draft_project_sync_pending():
        return
    if WRITING_DESK_DRAFT_WIDGET_KEY not in st.session_state:
        return
    desk = ensure_writing_desk_state(st.session_state)
    set_writing_desk_draft(
        st.session_state,
        draft_content_from_widget(
            st.session_state.get(WRITING_DESK_DRAFT_WIDGET_KEY),
            writing_desk_draft_content(desk),
        ),
    )


def flush_writing_desk_draft_from_widget() -> None:
    """Élő jegyzetmező → tartós `writing_desk.draft` (ha a widget létezik).

    Mentés / dirty-check előtt hívandó, hogy a gépelés a projekt fingerprintbe
    kerüljön. Resync / pending alatt csak durable→widget seed, commit nincs:
    a régi CCv2 html state nem írhatja felül az új durable draftot.
    """
    ensure_writing_desk_state(st.session_state)
    apply_writing_desk_draft_resync_if_needed()
    if _writing_desk_draft_project_sync_pending():
        return
    commit_writing_desk_draft_from_widget()


def _on_writing_desk_draft_change() -> None:
    """A CCv2 html state a widget unmountja előtt a tartós draftba kerül.

    A főnézet-váltó gomb `st.rerun()`-t hív, mielőtt az Íróasztal shell
    újra létrehozná a mezőt. Az `on_html_change` a Streamlit callback-fázisában
    fut (az előző futtatás widget-metaadataiból), ezért a draft akkor is
    durable marad, ha ezen a futáson az editor már nem mountolódik.
    """
    commit_writing_desk_draft_from_widget()


def replace_writing_desk_draft_content(content: str) -> None:
    """Durable draft csere + editor resync (későbbi 4C vázlatátadás).

    A következő Íróasztal-render (`apply_writing_desk_draft_resync_if_needed`)
    tölti az editort, és a `revision` nő, hogy a frontend cserélje a DOM-ot.
    """
    set_writing_desk_draft(st.session_state, content)
    begin_writing_desk_draft_resync()


def _render_notes_editor() -> None:
    blocking = _writing_desk_draft_project_sync_pending()
    apply_writing_desk_draft_resync_if_needed()
    desk = ensure_writing_desk_state(st.session_state)
    if blocking:
        html = draft_html_for_editor(writing_desk_draft_content(desk))
    else:
        raw_widget = st.session_state.get(WRITING_DESK_DRAFT_WIDGET_KEY)
        html = draft_html_for_editor(writing_desk_draft_widget_html(raw_widget))
    writing_desk_draft_editor(
        html=html,
        revision=writing_desk_draft_revision(),
        key=WRITING_DESK_DRAFT_WIDGET_KEY,
        on_html_change=_on_writing_desk_draft_change,
        height=_DRAFT_TEXT_AREA_HEIGHT_PX,
    )
    if blocking:
        consume_writing_desk_draft_resync_flag()
        return
    commit_writing_desk_draft_from_widget()


def writing_desk_docx_export_payload() -> tuple[bytes | None, str]:
    """Flush után a tartós draft DOCX-bytejai. Üres draft → (None, filename)."""
    flush_writing_desk_draft_from_widget()
    desk = ensure_writing_desk_state(st.session_state)
    html = writing_desk_draft_content(desk)
    blob = build_writing_desk_docx_bytes(html)
    name = writing_desk_docx_filename(str(st.session_state.get("last_igehely") or ""))
    return blob, name


def send_writing_desk_chat_after_flush(
    question: str,
    *,
    generate_fn: GenerateFn | None,
):
    """CCv2 widget → durable draft, majd chat. A resync/pending őröket nem kerüli meg."""
    flush_writing_desk_draft_from_widget()
    return send_writing_desk_chat_message(
        st.session_state,
        question,
        generate_fn=generate_fn,
    )


DOCX_EMPTY_NOTICE = (
    "A DOCX-letöltés még nem használható: a Jegyzet / vázlat mező üres. "
    "Amint írsz bele szöveget, letöltheted Word-dokumentumként."
)
DOCX_EMPTY_HELP = "Üres vázlatból nem készül dokumentum."

# A letiltott gomb eddig aktívnak látszott (teljes átlátszóság, sötét felirat).
# A stílus minden futásban kirajzolódik, és csak a letiltott állapotra hat
# (UI/UX-audit 2026-11-23, V16).
_DOCX_DISABLED_STYLE = """
<style>
.st-key-writing_desk_docx_download button:disabled {
    opacity: 0.6 !important;
    border-style: dashed !important;
    background: rgba(47, 42, 36, 0.04) !important;
    box-shadow: none !important;
}
.st-key-writing_desk_docx_download button:disabled p {
    color: #6f6457 !important;
}
</style>
"""


def _render_docx_export() -> None:
    blob, filename = writing_desk_docx_export_payload()
    empty = blob is None
    st.markdown(_DOCX_DISABLED_STYLE, unsafe_allow_html=True)
    if empty:
        st.caption(DOCX_EMPTY_NOTICE)
    st.download_button(
        label="Letöltés DOCX",
        data=blob or b"",
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key="writing_desk_docx_download",
        disabled=empty,
        help=DOCX_EMPTY_HELP if empty else None,
        width="stretch",
    )


def _render_helper_chat(*, generate_fn: GenerateFn | None) -> None:
    ensure_writing_desk_chat_state(st.session_state)
    for msg in writing_desk_chat_messages(st.session_state):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    question = st.chat_input(
        "Kérdés a vázlathoz…",
        key=WRITING_DESK_CHAT_INPUT_KEY,
    )
    if not question:
        return
    with st.spinner("Válasz készül…"):
        send_writing_desk_chat_after_flush(question, generate_fn=generate_fn)
    st.rerun()


def _render_scripture_block() -> None:
    """RÚF + görög/héber token UI; hiba esetén nem állítja le a shellt."""
    try:
        render_bible_text_reading_block(
            original_language_key_prefix=WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX,
            bible_view_key=WRITING_DESK_BIBLE_VIEW_KEY,
            display_mode="compact",
        )
    except Exception as exc:
        from streamlit.errors import Error as StreamlitError

        if isinstance(exc, StreamlitError):
            raise
        render_info_panel(
            title="A bibliai szöveg most nem jeleníthető meg",
            body=(
                "A jegyzetelés ettől függetlenül folytatható. "
                "A RÚF és az eredeti szöveg a Textusműhelyből tölthető be."
            ),
            tone="neutral",
        )


def _run_extract_generation(extract_key: str, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Kivonat készítése…"):
        result = generate_writing_desk_extract(
            st.session_state,
            extract_key,
            generate_fn=generate_fn,
        )
    error_key = extract_error_session_key(extract_key)
    if result.ok:
        st.session_state.pop(error_key, None)
    else:
        st.session_state[error_key] = result.error_message
    st.rerun()


def _render_extract_card(
    extract_key: str,
    *,
    generate_fn: GenerateFn | None,
) -> None:
    view = inspect_writing_desk_extract(st.session_state, extract_key)
    error_key = extract_error_session_key(extract_key)
    if view.status == STATUS_VALID:
        st.session_state.pop(error_key, None)
    error_text = str(st.session_state.get(error_key) or "").strip()
    needs_action = view.status in {STATUS_READY, STATUS_STALE}
    with st.container(border=True, key=f"writing_desk_extract_card_{extract_key}"):
        if needs_action:
            title_col, action_col = st.columns([1.6, 1], gap="small")
        else:
            title_col = st.container()
            action_col = None
        with title_col:
            st.markdown(f"**{view.label}**")
        if error_text:
            render_info_panel(
                title="A kivonat most nem készült el",
                body=error_text,
                tone="warning",
            )
        if view.status == STATUS_MISSING_SOURCE:
            st.caption(view.missing_message)
            return
        if view.status == STATUS_VALID:
            st.markdown(view.content)
            return
        if view.status == STATUS_STALE:
            with action_col:
                if st.button(
                    "Kivonat frissítése",
                    key=f"writing_desk_extract_refresh_{extract_key}",
                    width="stretch",
                ):
                    _run_extract_generation(extract_key, generate_fn)
            st.caption("A forrásanyag megváltozott")
            return
        if view.status == STATUS_READY:
            with action_col:
                if st.button(
                    "Kivonat készítése",
                    key=f"writing_desk_extract_generate_{extract_key}",
                    width="stretch",
                ):
                    _run_extract_generation(extract_key, generate_fn)


def _ensure_writing_desk_extract_row_styles() -> None:
    """Csak a Munkaanyag három kártyájának törése — nem globális spacing."""
    st.markdown(
        """
        <style>
        .writing-desk-extract-row-marker {
            display: none !important;
            height: 0 !important;
            overflow: hidden !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .element-container:has(.writing-desk-extract-row-marker) {
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .element-container:has(.writing-desk-extract-row-marker)
            + .element-container [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap;
            gap: 0.55rem !important;
        }
        .element-container:has(.writing-desk-extract-row-marker)
            + .element-container [data-testid="stColumn"] [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 12px 14px !important;
            background:
                linear-gradient(
                    180deg,
                    rgba(255, 253, 248, 0.97) 0%,
                    rgba(247, 239, 226, 0.92) 100%
                ) !important;
            border: 1px solid rgba(170, 145, 112, 0.32) !important;
            box-shadow:
                0 1px 0 rgba(255, 255, 255, 0.88) inset,
                0 4px 10px rgba(58, 40, 22, 0.08) !important;
        }
        .element-container:has(.writing-desk-extract-row-marker)
            + .element-container [data-testid="stColumn"] [data-testid="stVerticalBlock"] {
            gap: 0.35rem !important;
        }
        @media (max-width: 900px) {
            .element-container:has(.writing-desk-extract-row-marker)
                + .element-container [data-testid="stColumn"] {
                min-width: calc(50% - 0.5rem) !important;
                flex: 1 1 calc(50% - 0.5rem) !important;
            }
        }
        @media (max-width: 640px) {
            .element-container:has(.writing-desk-extract-row-marker)
                + .element-container [data-testid="stColumn"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_writing_desk_shell(*, generate_fn: GenerateFn | None = None) -> None:
    """Rendereli az Íróasztal munkafelületét."""
    ensure_writing_desk_state(st.session_state)
    render_page_intro(
        title=WRITING_DESK_LABEL,
        body="",
        workspace_scope=True,
    )

    render_work_section(
        title="Bibliai szöveg és eredeti nyelv",
        context=WRITING_DESK_LABEL,
    )
    with work_surface("writing_desk_scripture"):
        _render_scripture_block()

    render_work_section(
        title="Jegyzet / vázlat",
        context=WRITING_DESK_LABEL,
    )
    with work_surface("writing_desk_notes"):
        _render_notes_editor()
        _render_docx_export()

    render_work_section(
        title="Munkaanyag",
        context=WRITING_DESK_LABEL,
    )
    with work_surface("writing_desk_work_material"):
        _ensure_writing_desk_extract_row_styles()
        st.markdown(
            '<div class="writing-desk-extract-row-marker"></div>',
            unsafe_allow_html=True,
        )
        extract_cols = st.columns(3, gap="small")
        for column, extract_key in zip(
            extract_cols, WRITING_DESK_EXTRACT_KEYS, strict=True
        ):
            with column:
                _render_extract_card(extract_key, generate_fn=generate_fn)

    render_work_section(
        title="Segítő chat",
        body="A vázlatról, megfogalmazásról vagy szerkezetről.",
        context=WRITING_DESK_LABEL,
    )
    with work_surface("writing_desk_helper_chat"):
        _render_helper_chat(generate_fn=generate_fn)


__all__ = [
    "WORK_MATERIAL_SECTIONS",
    "WRITING_DESK_BIBLE_VIEW_KEY",
    "WRITING_DESK_DRAFT_RESYNC_FLAG",
    "WRITING_DESK_DRAFT_REVISION_KEY",
    "WRITING_DESK_DRAFT_WIDGET_KEY",
    "WRITING_DESK_LABEL",
    "WRITING_DESK_MODE",
    "WRITING_DESK_ORIGINAL_LANGUAGE_KEY_PREFIX",
    "apply_writing_desk_draft_resync_if_needed",
    "begin_writing_desk_draft_resync",
    "bump_writing_desk_draft_revision",
    "commit_writing_desk_draft_from_widget",
    "consume_writing_desk_draft_resync_flag",
    "flush_writing_desk_draft_from_widget",
    "render_writing_desk_shell",
    "replace_writing_desk_draft_content",
    "send_writing_desk_chat_after_flush",
    "writing_desk_docx_export_payload",
    "writing_desk_draft_revision",
    "WRITING_DESK_CHAT_INPUT_KEY",
    "WRITING_DESK_CHAT_KEY",
]
