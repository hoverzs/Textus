"""A Textusműhely önálló vázlatkészítő belépési pontjának megszüntetése
(célarchitektúra-terv, 2. fázis, 1. lépés, 2026-08-13).

Kizárólag a felületi duplikáció szűnt meg — a közös `sermon_outline_engine.
generate_sermon_outline()` motor, a `sermon_workshop.sermon_outline` adat,
a korábbi mentett vázlatok, a Word-export képesség, a Vázlatkosár és az
Igehirdetési műhely vázlatfelülete változatlan.

Ez a modul forrás- és adatszintű ellenőrzéseket végez (a meglévő
`tests/test_quick_tools_grid.py` mintáját követve) — nem Streamlit AppTest-
alapú UI-renderelést, mert az app.py mérete miatt ez lenne a gyors, stabil,
karbantartható ellenőrzési mód, összhangban a projekt eddigi tesztstílusával.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sermon_workshop_data import (
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    normalize_sermon_workshop,
)
from workshop_nav_ui import QUICK_TOOLS_TAB_LABELS

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = (ROOT / "app.py").read_text(encoding="utf-8")


def _tab_blocks() -> dict[int, str]:
    """`{index: forráskód a "with tabs[index]:" sortól a következő
    "with tabs[" sorig (vagy fájlvégéig)}` — az app.py Gyorseszközök
    blokkjának tényleges, futásidejű index->tartalom leképezése."""
    matches = list(re.finditer(r"^with tabs\[(\d+)\]:", APP_SRC, flags=re.MULTILINE))
    blocks: dict[int, str] = {}
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(APP_SRC)
        blocks[int(m.group(1))] = APP_SRC[start:end]
    return blocks


# ---------------------------------------------------------------------------
# 1-2. Nincs "Vázlat" kártya, nincs "Gyors vázlat" felület
# ---------------------------------------------------------------------------


def test_quick_tools_grid_has_no_standalone_outline_card():
    assert not any(
        label.strip().endswith(": Vázlat") for label in QUICK_TOOLS_TAB_LABELS
    )


def test_quick_tools_grid_has_no_basket_card():
    """RESET 1A-UI (2026-08-18): a Vázlatkosár mint önálló Gyorseszköz-kártya
    megszűnt — a kutatási tartalmak automatikusan elérhetők a vázlatmotor
    számára, nincs szükség köztes gyűjtő-fülre."""
    assert not any(
        label.strip().endswith(": Vázlatkosár") for label in QUICK_TOOLS_TAB_LABELS
    )
    assert len(QUICK_TOOLS_TAB_LABELS) == 12


def test_no_quick_outline_ui_remnants_in_app_py():
    assert "Gyors vázlat" not in APP_SRC
    assert 'mode="quick"' not in APP_SRC
    assert "outline_run" not in APP_SRC
    assert "_qt_outline_running" not in APP_SRC


# ---------------------------------------------------------------------------
# 3. Az indexváltozás után minden megmaradó kártya a helyes funkciót nyitja
# ---------------------------------------------------------------------------

_EXPECTED_MARKERS: dict[int, str] = {
    0: "render_igehely_panel()",
    1: "render_original_text_panel()",
    # Commentary UI phase (2026-09-03): új, retrieval-only "Kommentárok"
    # fül az Eredeti szöveg és az Exegézis között -- ld.
    # tests/test_commentary_ui.py a részletes wiring-ellenőrzésért. Ugyanebben
    # a fázisban a "Textusösszegzés" Gyorseszközök-belépési pont megszűnt (a
    # rács pontosan 12 elemű, 3×4-es marad) -- ld. lentebb. A grounded-
    # compare fázis (2026-09-03, ld. tests/test_commentary_compare.py) óta a
    # hívás generate_fn-t is átad a "Kommentárok összehasonlítása" gombhoz.
    # A magyar kommentárfordítás fázis (2026-09-03, ld. tests/test_
    # commentary_translation.py) óta resolve_model_fn-t is átad (a fordítás
    # provenance-metaadatához).
    2: "render_commentary_panel(generate_fn=generate_text, resolve_model_fn=resolve_gemini_model_for_tab)",
    3: 'key="exegesis"',
    4: 'key="history"',
    5: 'key="theology"',
    # Phase 3I.1 (2026-08-28): a korábbi `render_section_tab(key=
    # "illustrations", ...)` szabad LLM-generálású story-blokkot
    # eltávolítottuk -- ld. tests/test_illustration_legacy_generation_
    # removed.py. Ez a fül tartalma mostantól kizárólag a DB-alapú
    # retrieval UI.
    6: "render_illustration_search_action(generate_fn=generate_text)",
    7: 'key="actualization"',
    8: 'st.header("Énekajánló")',
    9: '"Igehirdetési sorozat tervező"',
    10: "render_text_main_idea_section(",
    11: 'st.header("📖 Útmutatás")',
}


def test_tab_indices_are_contiguous_without_gaps_or_duplicates():
    blocks = _tab_blocks()
    assert sorted(blocks.keys()) == list(range(12))


@pytest.mark.parametrize("index", sorted(_EXPECTED_MARKERS))
def test_each_tab_index_opens_the_expected_function(index: int):
    blocks = _tab_blocks()
    assert index in blocks, f"Hiányzó with tabs[{index}]: blokk"
    assert _EXPECTED_MARKERS[index] in blocks[index], (
        f"tabs[{index}] nem a várt tartalmat nyitja: {_EXPECTED_MARKERS[index]!r}"
    )


def test_no_stray_quick_outline_marker_in_any_remaining_block():
    """A megmaradó egyetlen blokkban se maradjon a törölt Vázlat-fül
    jellegzetes szövege (pl. véletlen index-eltolási hiba esetén)."""
    for index, block in _tab_blocks().items():
        assert "Gyors vázlat" not in block, index
        assert "outline_run" not in block, index


# ---------------------------------------------------------------------------
# 4. "A textus fő gondolata" elérhető marad; a "Textusösszegzés"
#    Gyorseszközök-belépési pontja megszűnt (Commentary UI fázis,
#    2026-09-03), de a mögötte álló implementáció (render_text_summary_
#    section, textus_workshop_ui.py, text_summary adatmodell) VÁLTOZATLAN
#    -- csak a főmenü-hívási hely tűnt el, ld. app.py-beli megjegyzés.
# ---------------------------------------------------------------------------


def test_text_main_idea_still_in_quick_tools_summary_nav_entry_removed():
    assert any(
        "fő gondolata" in label for label in QUICK_TOOLS_TAB_LABELS
    )
    assert not any("Textusösszegzés" in label for label in QUICK_TOOLS_TAB_LABELS)
    blocks = _tab_blocks()
    assert "render_text_main_idea_section(" in blocks[10]
    # No tab block calls it any more (a source-code comment nearby
    # mentioning the function name by design does not count).
    assert not any("render_text_summary_section(" in block for block in blocks.values())


def test_text_summary_implementation_untouched_outside_nav():
    """A user explicit kérése: az implementáció NE törlődjön automatikusan
    -- csak a belépési pont. A render_text_summary_section funkció, a
    textus_workshop_ui modul és a text_summary adatmodell továbbra is
    elérhető és importálható, csak app.py már nem hívja meg."""
    import textus_workshop_ui

    assert hasattr(textus_workshop_ui, "render_text_summary_section")
    assert callable(textus_workshop_ui.render_text_summary_section)


# ---------------------------------------------------------------------------
# 5-6. Az Igehirdetési műhely "Igehirdetési vázlat" felülete változatlan;
# a vázlatmotor a felhasználó felől kizárólag onnan hívható.
# ---------------------------------------------------------------------------


def test_sermon_workshop_outline_section_untouched():
    import sermon_workshop_ui

    assert hasattr(sermon_workshop_ui, "render_outline_section")
    assert callable(sermon_workshop_ui.render_outline_section)
    src = Path(sermon_workshop_ui.__file__).read_text(encoding="utf-8")
    assert 'def render_outline_section(' in src
    assert '"Igehirdetési vázlat"' in src


def test_generate_sermon_outline_has_exactly_one_user_facing_caller_left():
    """A `generate_sermon_outline(` / `assemble_sermon_outline(` tényleges
    felhasználói (UI-oldali) hívása kizárólag a sermon_workshop_ui.py-ban
    maradt — app.py-ban egy sincs többé."""
    assert "generate_sermon_outline(" not in APP_SRC
    assert "assemble_sermon_outline(" not in APP_SRC

    sw_ui_src = Path(ROOT / "sermon_workshop_ui.py").read_text(encoding="utf-8")
    assert "assemble_sermon_outline(" in sw_ui_src


def test_outline_engine_signature_and_contract_unchanged():
    """Ez a fázis (2A — Textusműhely-kártya eltávolítása) nem nyúlhat a
    motor szerződéséhez — csak a UI-belépési pont szűnt meg.

    MEGJEGYZÉS (2026-08-13, célarchitektúra-terv 2. fázis, 2. rész — külön
    kör): a `_heuristic_structured_from_bundle` mechanikus fallback ekkor,
    egy KÉSŐBBI, önálló jóváhagyott lépésben szűnt meg — ld.
    tests/test_outline_no_mechanical_fallback.py. Ez a teszt csak azt
    őrzi, amit ez a (2A) fázis ígért: a `generate_sermon_outline` alap-
    szignatúrája (mode/generate_fn) nem változott."""
    import inspect

    import sermon_outline_engine as engine

    params = inspect.signature(engine.generate_sermon_outline).parameters
    assert "mode" in params, "A generate_sermon_outline szerződése nem változhatott"
    assert "generate_fn" in params


# ---------------------------------------------------------------------------
# 7. Régi projekt mentett vázlata megmarad és megjelenik; nincs automatikus
# újragenerálás vagy tartalommódosítás.
# ---------------------------------------------------------------------------


def test_old_project_saved_outline_survives_normalize_without_regeneration():
    """A `content` (a ténylegesen megjelenített vázlatszöveg) és a
    `sermon_workshop`-szintű (nem a beágyazott outline-dict szintű)
    `sermon_outline_status` — amit az Igehirdetési műhely UI-ja ténylegesen
    kiolvas (ld. `sermon_workshop_ui.render_outline_section`,
    `status = sw.get("sermon_outline_status") or outline.get("status")`) —
    érintetlenül megmarad normalizáláskor, nincs automatikus újragenerálás.

    MEGJEGYZÉS (nem ennek a fázisnak a hatóköre, nem javítva): a beágyazott
    `sermon_outline.status` mezőt a `normalize_sermon_outline`
    (sermon_workshop_data.py:504-514) "needs_refresh"-re állítja, ha van
    tartalom, de a `schema_version` nem "pulpit_outline_v7" — ez egy
    ELŐZETESEN LÉTEZŐ, e fázistól teljesen független eltérés a motor
    tényleges aktuális sémaverziójától (`sermon_outline_engine.
    SCHEMA_VERSION = "pulpit_outline_v8"`, ld. sermon_outline_engine.py:41).
    Nem ez a fázis vezette be (ellenőrizve: `git diff 7b7cf53 --
    sermon_workshop_data.py` nulla változást mutat), és nem tartozik a
    Textusműhely-vázlatkártya eltávolításának hatóköréhez."""
    sw = get_default_sermon_workshop()
    sw["sermon_outline"]["content"] = "Korábban elkészült, mentett vázlatszöveg."
    sw["sermon_outline"]["status"] = "approved"
    sw["sermon_outline"]["schema_version"] = "pulpit_outline_v8"
    sw["sermon_outline"]["source"] = "quick"  # régi, "Gyors vázlat"-ból származó jelölés
    sw["sermon_outline_status"] = "approved"

    normalized = normalize_sermon_workshop(sw)

    assert normalized["sermon_outline"]["content"] == "Korábban elkészült, mentett vázlatszöveg."
    # A UI ténylegesen ezt a (sermon_workshop-szintű) mezőt olvassa elsőként.
    assert normalized["sermon_outline_status"] == "approved"
    # A régi "quick" forráscímke önmagában érvényes marad — nincs migráció/elutasítás.
    assert normalized["sermon_outline"]["source"] == "quick"


def test_ensure_sermon_workshop_state_does_not_touch_existing_outline_content():
    state = {"sermon_workshop": get_default_sermon_workshop()}
    state["sermon_workshop"]["sermon_outline"]["content"] = "Változatlanul megőrzendő szöveg."
    state["sermon_workshop"]["sermon_outline"]["schema_version"] = "pulpit_outline_v8"
    state["sermon_workshop"]["sermon_outline"]["status"] = "approved"
    state["sermon_workshop"]["sermon_outline_status"] = "approved"

    ensure_sermon_workshop_state(state)

    assert state["sermon_workshop"]["sermon_outline"]["content"] == "Változatlanul megőrzendő szöveg."
    assert state["sermon_workshop"]["sermon_outline_status"] == "approved"


# ---------------------------------------------------------------------------
# 8. A Vázlatkosár aktív felülete megszűnt (RESET 1A-UI, 2026-08-18)
# ---------------------------------------------------------------------------


def test_no_basket_tab_or_active_basket_ui_remains():
    """A korábbi `test_basket_tab_block_functionally_unchanged` elvárását
    tudatosan megfordítottuk: a Vázlatkosár többé nem önálló fő UI-elem —
    sem panel, sem hozzáadás-gomb nem maradt aktív hívási úton. A `basket`
    projektadat és az `_append_basket_item` segédfüggvény változatlanul
    megmarad legacy, holt kódként (nincs aktív hívója)."""
    for marker in (
        'st.header("Vázlatkosár")',
        'key=f"basket_save_{idx}"',
        'key=f"basket_up_{idx}"',
        'key=f"basket_down_{idx}"',
        'key=f"delete_{idx}"',
        "Kosár ürítése",
        "Hozzáadás a vázlatkosárhoz",
    ):
        assert marker not in APP_SRC, marker
    for block in _tab_blocks().values():
        assert 'st.header("Vázlatkosár")' not in block


# ---------------------------------------------------------------------------
# 10. Az analitikai navigáció csak a két fő műhelyt / ténylegesen elérhető
# kártyákat rögzíti (nem kártyánkénti eseményt a Textusműhelyben).
# ---------------------------------------------------------------------------


def test_navigation_analytics_does_not_reference_removed_outline_card():
    import textus_analytics

    src = Path(textus_analytics.__file__).read_text(encoding="utf-8")
    assert "Gyors vázlat" not in src
    assert '"quick"' not in src
