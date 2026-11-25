"""UI/UX-audit (2026-11-23) — az elfogadott javítási terv 1–3. pontja.

1. A beírt igehely nézetváltáskor nem vész el, akkor sem, ha a bibliai
   szöveget még nem töltöttük be (audit V1/K1). Projektbetöltés és „Új munka”
   nem okozhat hibás állapotátvitelt.
2. A görög/héber szótanulmányozó panel nem jelenik meg az Igehely fülön, csak
   az „Eredeti szöveg tanulmányozása” fülön (audit V2).
3. A felvillanó üzenet rögzített helyőrzőben jelenik meg, így az utána
   következő projekt-eszköztár pozíciója nem tolódik el — „Új munka” után nem
   látszik dupla eszköztár (audit V3/K3).

A tesztek a teljes alkalmazást futtatják AppTesttel, valódi MI- vagy
hálózati hívás nélkül (a kommentár-adatbázis állapotlekérése kémfüggvény).
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

from workshop_nav_ui import QUICK_TOOLS_ACTIVE_TAB_KEY, QUICK_TOOLS_TAB_LABELS  # noqa: E402
from writing_desk_ui import WRITING_DESK_MODE  # noqa: E402

IGEHELY, ORIGINAL = 0, 1
TOOLBAR_KEY = "textus_app_toolbar"


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


def _fresh_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    return _ok(at.run())


def _app_with_passage(passage: str = "Jn 3,16-21") -> AppTest:
    at = _fresh_app()
    at.text_input(key="igehely_input").input(passage).run()
    return _ok(at)


def _new_work(at: AppTest) -> AppTest:
    """„Új munka”, szükség esetén a megerősítéssel. Az `_start_new_work`
    `st.rerun()`-nal zárul; a böngésző ezt mindig egy új futással követi, az
    AppTest viszont tesztsorrendtől függően nem mindig — ilyenkor a még
    függő üzenet jelzi, hogy a következő futást nekünk kell elindítani."""
    at.button(key="bar_new_work").click().run()
    _ok(at)
    if "project_new_work_yes" in [b.key for b in at.button]:
        at.button(key="project_new_work_yes").click().run()
        _ok(at)
    if "_flash_message" in at.session_state:
        _ok(at.run())
    return at


def _switch_view(at: AppTest, mode: str) -> AppTest:
    at.session_state["ui_mode"] = mode
    _ok(at.run())
    return _ok(at.run())  # egy további futás: itt törölné a Streamlit a nem kirajzolt widget állapotát


def _state(at: AppTest, key: str, default: object = None) -> object:
    return at.session_state[key] if key in at.session_state else default


# --- 1. Igehely megőrzése nézetváltáskor --------------------------------------


@pytest.mark.parametrize("mode", ["sermon_workshop", WRITING_DESK_MODE])
def test_typed_passage_survives_a_view_switch_without_bible_text(mode):
    at = _app_with_passage("Jn 3,16-21")
    assert not str(_state(at, "passage_text", "") or "").strip()  # szöveg nincs betöltve

    _switch_view(at, mode)
    assert _state(at, "igehely_input") == "Jn 3,16-21"
    assert _state(at, "last_igehely") == "Jn 3,16-21"

    _switch_view(at, "workshop")
    assert at.text_input(key="igehely_input").value == "Jn 3,16-21"


def test_other_views_see_the_typed_passage():
    from bible_text_ui import get_bible_text_snapshot
    from sermon_workshop_developed_outline_ai import build_developed_outline_context

    at = _app_with_passage("Jn 3,16-21")
    _switch_view(at, "sermon_workshop")
    snapshot_state = {k: at.session_state[k] for k in ("igehely_input", "last_igehely")}
    assert get_bible_text_snapshot(snapshot_state)["passage"] == "Jn 3,16-21"
    assert build_developed_outline_context(snapshot_state).reference == "Jn 3,16-21"
    rendered = "\n".join(m.value for m in at.markdown)
    assert "**Igehely:** Jn 3,16-21" in rendered


def test_changed_passage_replaces_the_previous_one_everywhere():
    at = _app_with_passage("Jn 3,16-21")
    at.text_input(key="igehely_input").input("Mk 1,1-8").run()
    _ok(at)
    _switch_view(at, WRITING_DESK_MODE)
    assert _state(at, "last_igehely") == "Mk 1,1-8"
    assert _state(at, "igehely_input") == "Mk 1,1-8"


def test_cleared_field_stays_cleared_after_switching():
    """Az üres mező nem törli a `last_igehely`-t (a `_sync_inputs_to_last`
    eddigi szabálya), de a mezőt sem tölti vissza a régi értékkel."""
    at = _app_with_passage("Jn 3,16-21")
    at.text_input(key="igehely_input").input("").run()
    _ok(at)
    _switch_view(at, "sermon_workshop")
    _switch_view(at, "workshop")
    assert at.text_input(key="igehely_input").value == ""


def test_project_load_pending_sync_wins_over_the_old_field_value():
    """Projektbetöltéskor a `last_igehely` már az új projekté, a mező pedig a
    következő futás elején, pending szinkronnal kapja meg ugyanezt. A
    megőrzés nem írhatja vissza a régi mezőértéket."""
    at = _app_with_passage("Jn 3,16-21")
    at.session_state["last_igehely"] = "Mk 1,1-8"
    at.session_state["_pending_project_widget_sync"] = {"igehely_input": "Mk 1,1-8"}
    _ok(at.run())
    assert _state(at, "igehely_input") == "Mk 1,1-8"
    assert _state(at, "last_igehely") == "Mk 1,1-8"
    assert at.text_input(key="igehely_input").value == "Mk 1,1-8"


def test_new_work_clears_the_passage_and_it_does_not_come_back():
    at = _app_with_passage("Jn 3,16-21")
    _new_work(at)
    assert _state(at, "igehely_input") == ""
    assert _state(at, "last_igehely") == ""
    _switch_view(at, "sermon_workshop")
    _switch_view(at, "workshop")
    assert at.text_input(key="igehely_input").value == ""
    assert _state(at, "last_igehely") == ""


def test_persistence_helper_is_called_after_pending_sync_and_before_widgets():
    src = APP_PATH.read_text(encoding="utf-8")
    pending = src.index("\n_apply_pending_project_widget_sync()\n")
    persist = src.index("\n_persist_passage_input_across_views()\n")
    status_bar = src.index("\n_render_project_status_bar()\n")
    widget = src.index('key="igehely_input"')
    assert pending < persist < status_bar
    assert persist < widget


# --- 2. A görög panel csak az Eredeti szöveg fülön -----------------------------


@pytest.fixture
def greek_block_counter(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import passage_trace

    entered: list[str] = []
    real_emit = passage_trace.emit

    def recording_emit(message: str) -> None:
        if message == "entering: greek_analysis_block":
            entered.append(message)
        real_emit(message)

    monkeypatch.setattr(passage_trace, "emit", recording_emit)
    monkeypatch.setattr(passage_trace, "_ENABLED", True)
    return entered


def _open_tab(at: AppTest, index: int) -> AppTest:
    at.session_state[QUICK_TOOLS_ACTIVE_TAB_KEY] = QUICK_TOOLS_TAB_LABELS[index]
    return _ok(at.run())


def test_igehely_tab_renders_the_original_language_panel_under_the_text(greek_block_counter):
    at = _app_with_passage("Jn 3,16")
    greek_block_counter.clear()
    _open_tab(at, IGEHELY)
    assert len(greek_block_counter) == 1
    captions = " ".join(c.value for c in at.caption)
    assert "fülön található" not in captions


def test_original_text_tab_still_renders_the_greek_panel(greek_block_counter):
    at = _app_with_passage("Jn 3,16")
    greek_block_counter.clear()
    _open_tab(at, ORIGINAL)
    assert len(greek_block_counter) == 1


def test_igehely_tab_keeps_text_loading_without_manual_paste():
    at = _app_with_passage("Jn 3,16")
    _open_tab(at, IGEHELY)
    labels = [b.label for b in at.button]
    assert "RÚF-szöveg betöltése" in labels
    assert "Bibliai szöveg kézi beillesztése" not in [e.label for e in at.expander]


# --- 3. Felvillanó üzenet: nem tolja el a projekt-eszköztárat -------------------


def _toolbar_index(at: AppTest) -> int:
    children = list(at.main.children.values())
    hits = [
        i
        for i, child in enumerate(children)
        if TOOLBAR_KEY in str(getattr(getattr(child, "proto", None), "id", ""))
    ]
    assert len(hits) == 1, hits  # pontosan egy eszköztár
    return hits[0]


def test_flash_message_does_not_shift_the_toolbar():
    """Az első futásban a lista elején egy egyszeri, inicializáló elem is van
    (a második futástól nincs ott), ezért az alapállapot a második futás.
    A javítás előtt az üzenet az eszköztárat egy hellyel lejjebb tolta
    (4 → 5 → 4), a rögzített helyőrzővel a pozíció nem változik."""
    at = _fresh_app()
    _ok(at.run())
    without_flash = _toolbar_index(at)

    at.session_state["_flash_message"] = {"type": "info", "text": "Új üres munka indítva."}
    _ok(at.run())
    assert "Új üres munka indítva." in [i.value for i in at.info]
    with_flash = _toolbar_index(at)

    _ok(at.run())  # a következő futásban az üzenet eltűnik
    assert "Új üres munka indítva." not in [i.value for i in at.info]
    after = _toolbar_index(at)

    assert without_flash == with_flash == after


def test_new_work_shows_flash_once_with_a_single_toolbar():
    at = _app_with_passage("Jn 3,16-21")
    baseline = _toolbar_index(at)
    _new_work(at)
    assert "Új üres munka indítva." in [i.value for i in at.info]
    assert _toolbar_index(at) == baseline


@pytest.mark.parametrize("kind,attr", [("success", "success"), ("warning", "warning"), ("error", "error"), ("info", "info")])
def test_every_flash_kind_still_renders(kind, attr):
    at = _fresh_app()
    at.session_state["_flash_message"] = {"type": kind, "text": f"üzenet-{kind}"}
    _ok(at.run())
    assert f"üzenet-{kind}" in [e.value for e in getattr(at, attr)]
