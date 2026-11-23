"""UI/UX-audit (2026-11-23) — az elfogadott javítási terv 7. pontja.

1. Az Énekajánló és a Sorozattervező a többi Textusműhely-fül egységes
   `render_work_section` fejlécét használja (V7).
2. MI-generálás előtti üres állapotban nem jelenik meg a „Finomítás” rész és
   az ismétlődő figyelmeztetés; generált tartalomnál minden marad (V8).
3. „A textus fő gondolata”: látható mezőcímke, egymás melletti gombok (V15).
4. Íróasztal: üres vázlatnál a DOCX-letöltés letiltott, és látszik is,
   miért (V16).

Valódi MI- vagy hálózati hívás nincs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_PATH = ROOT / "app.py"
APP_SRC = APP_PATH.read_text(encoding="utf-8")

from workshop_nav_ui import QUICK_TOOLS_ACTIVE_TAB_KEY, QUICK_TOOLS_TAB_LABELS  # noqa: E402

EXEGESIS, HISTORY, THEOLOGY, ACTUALIZATION, HYMN, SERIES, MAIN_IDEA = 3, 4, 5, 7, 8, 9, 10


@pytest.fixture(autouse=True)
def _no_commentary_download(monkeypatch: pytest.MonkeyPatch) -> None:
    import commentary_ui
    from textus_kb import commentary_runtime

    monkeypatch.setattr(
        commentary_ui,
        "_get_status",
        lambda: commentary_runtime.CommentaryRuntimeStatus(
            available=False, reason="test_spy", database_path="", detail=""
        ),
    )


def _ok(at: AppTest) -> AppTest:
    assert not at.exception, [e.value for e in at.exception]
    return at


def _app_on_tab(index: int, **state) -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    _ok(at.run())
    for key, value in state.items():
        at.session_state[key] = value
    at.session_state[QUICK_TOOLS_ACTIVE_TAB_KEY] = QUICK_TOOLS_TAB_LABELS[index]
    return _ok(at.run())


def _markdown(at: AppTest) -> str:
    return "\n".join(str(m.value) for m in at.markdown)


def _subheaders(at: AppTest) -> list[str]:
    return [str(s.value) for s in at.subheader]


# --- 1. Egységes fejléc ---------------------------------------------------------


@pytest.mark.parametrize(
    "index,title",
    [(HYMN, "Énekajánló"), (SERIES, "Igehirdetési sorozat tervező")],
)
def test_hymn_and_series_use_the_shared_section_header(index, title):
    at = _app_on_tab(index)
    md = _markdown(at)
    assert f'<div class="tx-work-section-title" role="heading" aria-level="2">{title}</div>' in md
    assert '<div class="tx-work-section-context">Textusműhely</div>' in md
    assert title not in [str(h.value) for h in at.header]
    assert not any("📅" in s for s in _subheaders(at))


def test_series_independence_note_is_kept_in_the_header_text():
    at = _app_on_tab(SERIES)
    assert "az igehely-alapú elemzéstől függetlenül működik" in _markdown(at)
    assert "Tervezzünk meg egy új sorozatot!" in _subheaders(at)


# --- 2. Finomítás csak generált tartalomnál ---------------------------------------


@pytest.mark.parametrize("index", [EXEGESIS, HISTORY, THEOLOGY, ACTUALIZATION, HYMN])
def test_empty_tab_has_no_refinement_section(index):
    at = _app_on_tab(index)
    assert not any(s.startswith("💬 Finomítás") for s in _subheaders(at))
    assert "Előbb generálj tartalmat ehhez a részhez." not in [str(i.value) for i in at.info]


@pytest.mark.parametrize(
    "index,result_key,chat_key,title",
    [
        (EXEGESIS, "exegesis", "exegesis_chat", "Exegézis"),
        (HYMN, "songs", "songs_chat", "Énekajánló"),
    ],
)
def test_generated_content_keeps_the_full_refinement_section(index, result_key, chat_key, title):
    at = _app_on_tab(
        index,
        **{
            result_key: "Generált tartalom a teszthez.",
            chat_key: [{"role": "assistant", "content": "Korábbi finomító válasz."}],
        },
    )
    assert any(s.startswith("💬 Finomítás:") and title in s for s in _subheaders(at))
    assert at.chat_input(key=f"chat_{chat_key}") is not None
    assert "Korábbi finomító válasz." in _markdown(at)


def test_refinement_logic_after_the_guard_is_unchanged():
    start = APP_SRC.index("def refinement_chat(title, result_key, chat_key):")
    body = APP_SRC[start: APP_SRC.index("\ndef ", start + 10)]
    guard = body.index("if not st.session_state.get(result_key):\n        return")
    assert guard < body.index("st.divider()") < body.index('st.subheader(f"💬 Finomítás: {title}")')
    assert "st.chat_input(" in body and "wrap_untrusted_content(" in body


# --- 3. A textus fő gondolata ------------------------------------------------------


def test_main_idea_editor_has_a_visible_label_and_adjacent_buttons():
    at = _app_on_tab(MAIN_IDEA)
    area = at.text_area(key="tw_main_idea_input")
    assert area.label == "Fogalmazd meg a textus fő gondolatát egy mondatban"
    assert area.proto.label_visibility.value == 0  # VISIBLE
    assert at.button(key="tw_main_idea_save_draft_btn").label == "Mentés vázlatként"
    assert at.button(key="tw_main_idea_approve_forward_btn").label == "Jóváhagyom és átadom"

    import textus_workshop_ui

    src = Path(textus_workshop_ui.__file__).read_text(encoding="utf-8")
    block = src[src.index('with action_row("tw_main_idea"):'):]
    block = block[: block.index("tw = ensure_text_workshop_state")]
    assert "st.container(horizontal=True" in block
    assert "st.columns(" not in block


def test_main_idea_buttons_still_save_and_approve():
    at = _app_on_tab(MAIN_IDEA)
    at.text_area(key="tw_main_idea_input").input("Isten szeretete megelőz.").run()
    _ok(at)
    at.button(key="tw_main_idea_save_draft_btn").click().run()
    _ok(at)
    tw = at.session_state["text_workshop"]
    assert tw["text_main_idea"] == "Isten szeretete megelőz."
    assert tw["text_main_idea_status"] == "draft"


# --- 4. Íróasztal: DOCX -------------------------------------------------------------


def _desk_app(**state) -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    _ok(at.run())
    for key, value in state.items():
        at.session_state[key] = value
    at.session_state["ui_mode"] = "writing_desk"
    return _ok(at.run())


def _docx_button(at: AppTest):
    hits = [
        el
        for el in at.get("download_button")
        if getattr(el.proto, "label", "") == "Letöltés DOCX"
    ]
    assert len(hits) == 1, hits
    return hits[0]


def test_empty_draft_disables_docx_with_a_plain_explanation():
    import writing_desk_ui

    at = _desk_app()
    button = _docx_button(at)
    assert button.proto.disabled is True
    assert button.proto.help == writing_desk_ui.DOCX_EMPTY_HELP
    assert writing_desk_ui.DOCX_EMPTY_NOTICE in [str(c.value) for c in at.caption]
    assert ".st-key-writing_desk_docx_download button:disabled" in _markdown(at)


def test_draft_with_text_enables_docx_without_the_notice():
    import writing_desk_ui
    from writing_desk_data import WRITING_DESK_KEY, get_default_writing_desk, set_writing_desk_draft

    desk_state: dict = {WRITING_DESK_KEY: get_default_writing_desk()}
    set_writing_desk_draft(desk_state, "<p>Vázlat szövege</p>")
    at = _desk_app(**desk_state)
    button = _docx_button(at)
    assert button.proto.disabled is False
    assert not button.proto.help
    assert writing_desk_ui.DOCX_EMPTY_NOTICE not in [str(c.value) for c in at.caption]
