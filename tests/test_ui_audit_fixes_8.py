"""UI/UX-audit (2026-11-23) — az elfogadott javítási terv 8. pontja: mobilnézet.

Csak keskeny képernyőre szóló CSS változott (asztali nézet változatlan):

* csemperács (≤560 px): a hosszabb címkék két sorba törnek a levágás helyett;
* nézetváltó (≤520 px, ≤400 px): az „Igehirdetési műhely” szóhatáron két
  sorba törik, az egyszavas címkék szó közben nem törhetnek;
* projekt-eszköztár (≤759 px): a „…” menü nem kap saját, harmadik sort.

A tényleges megjelenést böngészőben 320–1440 px között ellenőriztük; ezek a
tesztek a szabályokat és azok helyét rögzítik.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UI_THEME = (ROOT / "ui_theme.py").read_text(encoding="utf-8")
NAV_SRC = (ROOT / "workshop_nav_ui.py").read_text(encoding="utf-8")


def _media_blocks(css: str, query: str) -> list[str]:
    """Az adott `@media` lekérdezés blokkjainak törzse (zárójel-egyensúllyal)."""
    blocks = []
    for m in re.finditer(re.escape(query) + r"\s*\{", css):
        depth, i = 1, m.end()
        while depth and i < len(css):
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        blocks.append(css[m.end(): i - 1])
    return blocks


def _rule(block: str, selector: str) -> str:
    """Az első olyan szabály deklarációi, amelynek szelektorlistájában a
    megadott szelektor pontosan (nem csak részletként) szerepel."""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", block):
        selectors = [re.sub(r"\s+", " ", sel).strip() for sel in m.group(1).split(",")]
        selectors = [re.sub(r"^/\*.*?\*/\s*", "", sel, flags=re.S) for sel in selectors]
        if selector in selectors:
            return m.group(2)
    raise AssertionError(f"nincs szabály: {selector}")


def _base_css(css: str) -> str:
    """A CSS `@media` blokkok nélkül (asztali / alapszabályok)."""
    out, i = [], 0
    for m in re.finditer(r"@media[^{]*\{", css):
        if m.start() < i:
            continue
        out.append(css[i: m.start()])
        depth, j = 1, m.end()
        while depth and j < len(css):
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        i = j
    out.append(css[i:])
    return "".join(out)


# --- csemperács ----------------------------------------------------------------


def test_tiles_wrap_instead_of_ellipsis_on_narrow_screens():
    (block,) = _media_blocks(UI_THEME, "@media (max-width: 560px)")[:1]
    decl = _rule(block, '.st-key-quick_tools_grid [data-testid="stTab"] p')
    assert "white-space: normal !important" in decl
    assert "text-overflow: clip !important" in decl
    assert "overflow: visible !important" in decl
    # szót nem vágunk
    assert "word-break" not in decl and "overflow-wrap: anywhere" not in decl


def test_tile_labels_keep_single_line_ellipsis_on_desktop():
    base = _base_css(UI_THEME)
    decl = _rule(base, '.st-key-quick_tools_grid [data-testid="stTab"] p')
    assert "white-space: nowrap !important" in decl
    assert "text-overflow: ellipsis !important" in decl
    assert "grid-template-columns: repeat(4, minmax(0, 1fr)) !important" in _rule(
        base, '.st-key-quick_tools_grid [role="tablist"]'
    )


# --- projekt-eszköztár ------------------------------------------------------------


def test_toolbar_overflow_menu_shares_the_second_row_on_mobile():
    (block,) = _media_blocks(UI_THEME, "@media (max-width: 759px)")[:1]
    decl = _rule(block, ".st-key-tx_toolbar_actions")
    assert "flex: 0 0 auto !important" in decl
    assert "margin-left: auto !important" in decl
    assert "flex: 1 1 100%" not in decl
    # a fő sor (ikon, projektnév, szerkesztés) továbbra is teljes szélességű
    assert "flex: 1 1 100% !important" in _rule(block, ".st-key-tx_toolbar_main")
    # a kis képernyőn rejtett gombok a „…” menüben maradnak elérhetők
    assert "display: none !important" in _rule(block, ".st-key-textus_app_toolbar .st-key-bar_new_work")
    assert "display: flex !important" in _rule(block, ".st-key-textus_app_toolbar .st-key-bar_overflow_more")


def test_hidden_toolbar_actions_still_exist_in_the_overflow_menu():
    import inspect

    from workshop_nav_ui import render_app_toolbar

    src = inspect.getsource(render_app_toolbar)
    assert 'key="bar_overflow_more"' in src
    assert 'key="bar_overflow_new_work"' in src
    assert 'key="bar_overflow_settings"' in src


# --- nézetváltó ------------------------------------------------------------------


def _switcher_css() -> str:
    """A nézetváltó tényleges, kirajzolt <style> blokkja (AppTest)."""
    from streamlit.testing.v1 import AppTest

    def _app() -> None:
        from workshop_nav_ui import render_workspace_switcher

        render_workspace_switcher(
            options=["workshop", "sermon_workshop", "writing_desk"],
            labels={
                "workshop": "Textusműhely",
                "sermon_workshop": "Igehirdetési műhely",
                "writing_desk": "Íróasztal",
            },
            key="ui_mode",
        )

    at = AppTest.from_function(_app).run()
    assert not at.exception, [e.value for e in at.exception]
    styles = [m.value for m in at.markdown if "st-key-workspace_switcher" in str(m.value)]
    assert len(styles) == 1
    return styles[0]


def test_switcher_labels_wrap_on_word_boundaries_on_narrow_screens():
    css = _switcher_css()
    (narrow,) = _media_blocks(css, "@media (max-width:520px)")
    assert "white-space:normal!important" in narrow
    assert "text-overflow:clip!important" in narrow
    assert "word-break:normal!important" in narrow
    assert "overflow-wrap:normal!important" in narrow
    (tiny,) = _media_blocks(css, "@media (max-width:400px)")
    assert "font-size:0.78rem!important" in tiny


def test_switcher_desktop_rules_unchanged():
    css = _switcher_css()
    base = _base_css(css)
    assert "font-size:1rem!important;font-weight:600!important;" in base
    assert "min-height:52px!important;" in base
    assert "grid-template-columns:repeat(3,minmax(0,1fr))!important;" in base
    assert "white-space:normal" not in base


@pytest.mark.parametrize(
    "query", ["@media (max-width: 560px)", "@media (max-width: 759px)"]
)
def test_mobile_blocks_do_not_force_horizontal_scroll(query):
    for block in _media_blocks(UI_THEME, query):
        assert "overflow-x: scroll" not in block
        assert "min-width: 100vw" not in block
