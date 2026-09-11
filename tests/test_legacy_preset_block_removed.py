"""LEGACY PRESET CLEANUP (2026-08-21): a "Felhasználási cél" /
"Homiletikai stílus" / "Saját szempont vagy kérdés" / "Korábbi igehelyek"
legacy UI-blokk eltávolítása az Igehely panelről.

Indoklás: az új munkafolyamatban (közvetlen igehely-bevitel, alkalom-alapú
keresés az "Igehely keresése" funkción belül, vagy Konkordancia) a
kiválasztott textus feldolgozását nem torzíthatja el egy külön beállított
globális szolgálattípus/homiletikai stílus/saját fókusz — ezt a blokkot
ezért a felület szintjén véglegesen eltávolítottuk.

Forrás- és adatszintű ellenőrzés (a `test_textus_workshop_outline_card_
removed.py` mintáját követve) — nem Streamlit AppTest-alapú renderelés,
az app.py mérete miatt ez a gyors, stabil, karbantartható mód.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = (ROOT / "app.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. A négy legacy UI-elem eltűnt az Igehely panelről
# ---------------------------------------------------------------------------


def test_legacy_widgets_removed_from_app_source():
    for marker in (
        '"Felhasználási cél"',
        '"Homiletikai stílus"',
        '"Saját szempont vagy kérdés"',
        '"Korábbi igehelyek (utolsó 5)"',
        'key="alkalom_input"',
        'key="stilus_input"',
        'key="sajat_input"',
        'work_surface("igehely_context")',
    ):
        assert marker not in APP_SRC, marker


def test_verse_history_expander_button_removed():
    assert 'key=f"verse_hist_{v_idx}"' not in APP_SRC


# ---------------------------------------------------------------------------
# 2. A szomszédos "Bibliai háttér összegzése" blokk (igehely_overview)
# érintetlen maradt — funkciója változatlan, önálló marad.
# ---------------------------------------------------------------------------


def test_overview_button_and_surface_still_present_and_standalone():
    assert 'work_surface("igehely_overview")' in APP_SRC
    assert '"Bibliai háttér összegzése"' in APP_SRC
    assert 'key="overview_generate_btn"' in APP_SRC
    assert 'generate_section("overview")' in APP_SRC


def test_direct_entry_search_and_concordance_still_present():
    assert 'key="igehely_input"' in APP_SRC
    assert "render_passage_search_expander(" in APP_SRC
    assert "render_concordance_expander()" in APP_SRC
    assert "render_bible_text_editor(" in APP_SRC


# ---------------------------------------------------------------------------
# 3. A `_sync_inputs_to_last` már nem olvassa/írja a törölt widgetek
# session-kulcsait, és a puszta `verse_history` write-oldal (aminek egyetlen
# olvasója a törölt expander volt) is megszűnt.
# ---------------------------------------------------------------------------


def test_sync_inputs_to_last_no_longer_touches_legacy_keys():
    start = APP_SRC.index("def _sync_inputs_to_last()")
    end = APP_SRC.index("\ndef ", start + 1)
    body = APP_SRC[start:end]
    for marker in (
        "alkalom_input",
        "stilus_input",
        "sajat_input",
        "verse_history",
    ):
        assert marker not in body, marker
    # Az igehely-szinkron maga megmaradt.
    assert '"igehely_input"' in body
    assert '"last_igehely"' in body


def test_project_widget_restore_no_longer_seeds_legacy_widget_keys():
    start = APP_SRC.index("def _queue_project_widget_sync_from_state()")
    end = APP_SRC.index("\ndef ", start + 1)
    body = APP_SRC[start:end]
    for marker in ('"alkalom_input"', '"stilus_input"', '"sajat_input"'):
        assert marker not in body, marker
    assert '"igehely_input"' in body


# ---------------------------------------------------------------------------
# 4. Visszafelé kompatibilitás: a `last_alkalom`/`last_stilus`/`last_sajat`/
# `verse_history` mezők a workspace_data szinten VÁLTOZATLANUL megmaradnak
# (régi mentett projektek betöltése ne törjön el, és e mezők downstream
# fogyasztói — occasion/user_focus paraméterek — továbbra is működjenek,
# ha egy régi projektből örökölt nem-üres értéket kapnak).
# ---------------------------------------------------------------------------


def test_legacy_state_keys_remain_in_workspace_serialization_for_backward_compat():
    import workspace_data as wd

    for key in ("last_alkalom", "last_stilus", "last_sajat"):
        assert key in wd.WORKSPACE_STR_KEYS, key
        assert key in wd.PROJECT_DATA_KEYS, key
    assert "verse_history" in wd.WORKSPACE_LIST_KEYS
    assert "verse_history" in wd.PROJECT_DATA_KEYS

    for widget_key in ("alkalom_input", "stilus_input", "sajat_input", "igehely_input"):
        assert widget_key in wd.EXCLUDED_SESSION_KEYS, widget_key


def test_default_state_still_initializes_legacy_keys_to_empty():
    assert '"last_alkalom": ""' in APP_SRC
    assert '"last_stilus": ""' in APP_SRC
    assert '"last_sajat": ""' in APP_SRC
    assert '"verse_history": []' in APP_SRC


def test_old_project_with_legacy_fields_loads_without_error():
    """Régi mentett projekt, amely még tartalmazza a törölt widgetek
    perzisztens párját — a sanitizálás/normalizálás ne dobjon hibát, és az
    értékek megmaradjanak (semmi nem olvassa aktívan a widget-oldalt
    többé, de az adat maga tolerált)."""
    from workspace_data import sanitize_project_data

    old_project_data = {
        "last_igehely": "1Móz 32,23-32",
        "last_alkalom": "temetés",
        "last_stilus": "pasztorális",
        "last_sajat": "Régi, mentett saját szempont",
        "verse_history": ["1Móz 32,23-32", "Jn 3,16-21"],
        "passage_text": "23. Jákób tusakodása...",
        "bible_translation": "RÚF 2014",
    }

    cleaned = sanitize_project_data(old_project_data)

    assert cleaned["last_alkalom"] == "temetés"
    assert cleaned["last_stilus"] == "pasztorális"
    assert cleaned["last_sajat"] == "Régi, mentett saját szempont"
    assert cleaned["verse_history"] == ["1Móz 32,23-32", "Jn 3,16-21"]


# ---------------------------------------------------------------------------
# 5. A "occasion"/"user_focus" downstream fogyasztók (a legacy widgettől
# függetlenül) továbbra is a `last_alkalom`/`last_sajat` (majd
# `alkalom_input`/`sajat_input` üres fallback) forrásból dolgoznak — ez a
# plumbing szándékosan VÁLTOZATLAN maradt, csak az UI tűnt el felette.
# ---------------------------------------------------------------------------


def test_downstream_occasion_and_user_focus_plumbing_still_reads_last_alkalom_sajat():
    for module_name in (
        "textus_workshop_ui",
        "sermon_workshop_ui",
        "sermon_workshop_outline_ai",
    ):
        src = (ROOT / f"{module_name}.py").read_text(encoding="utf-8")
        assert "last_alkalom" in src, module_name
        assert "last_sajat" in src, module_name
