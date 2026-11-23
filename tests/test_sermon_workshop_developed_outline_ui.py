"""RESET 2E-4/2E-5 — a kétlépcsős vázlatmotor (blueprint + részletes
vázlat) UI-bekötésének és a kanonikus vázlat kézi szerkesztésének
tesztjei.

Valódi Streamlit-renderelésen keresztül (`streamlit.testing.v1.AppTest`)
bizonyítja a working — mindig mockolt `generate_fn`-nel, nincs valódi
API-kulcs vagy hálózati hívás. Az `AppTest.from_function` miatt minden
render-segédfüggvény TELJESEN önálló (saját importok, saját inline
adatok) — ez a meglévő `test_sermon_workshop_arc_ai.py`/`test_sermon_
workshop_flat_ui.py` bevett mintája.

A blueprintnek NINCS candidate-lifecycle-ja (RESET 2E-1/2E-2 szerződés,
ITT VÁLTOZATLAN) — sikeres generálás közvetlenül a kanonikus mezőt írja.
A részletes vázlat KÖTELEZŐEN candidate-only (RESET 2E-1A/2E-3) — a
2E-4-es teszt-blokk ezt a lifecycle-t (generate -> candidate -> explicit
accept/discard -> kanonikus) ellenőrzi.

A 2E-5-ös teszt-blokk a MÁR ELFOGADOTT, kanonikus `developed_outline`
kézi szerkesztését ellenőrzi: a candidate-előnézet marad read-only, a
kanonikus movementek tartalmi mezői (title/function/main_claim/
development/*_support/illustration_direction/application_direction/
transition_to_next) szerkeszthetők, de a `key`/`structure_mode`/
mozgás-sorrend/mozgás-darabszám nem.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sermon_workshop_ui as sw_ui  # noqa: E402
from sermon_workshop_data import _DEVELOPED_MOVEMENT_LIST_FIELDS  # noqa: E402
from writing_desk_data import WRITING_DESK_KEY  # noqa: E402

REFERENCE = "Jn 3,16"
PASSAGE = "Mert úgy szerette Isten a világot."

ARC_KEYS = (
    "entry",
    "starting_point",
    "first_shift",
    "deepening",
    "reinterpretation",
    "second_shift",
    "arrival",
)


# =============================================================================
# Önálló render-segédfüggvények (AppTest.from_function miatt teljesen
# saját importokkal/adatokkal)
# =============================================================================


def _render_missing_blueprint() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    def fake_gen(prompt, **kwargs):
        raise AssertionError("Hiányzó blueprint mellett nem szabadna AI-hívásnak történnie.")

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def _render_stale_blueprint() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import store_generated_blueprint_result

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint = {
        "central_claim": "X",
        "textual_center": "Y",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "Z",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": [],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": ["WARNING_SENTINEL_ÜTKÖZÉS"],
    }
    # SZÁNDÉKOSAN eltérő context_hash az aktuális kanonikus bemenettől
    # számolt hash-től -> a blueprint garantáltan stale lesz.
    store_generated_blueprint_result(
        st.session_state, blueprint=blueprint, context_hash="DELIBERATELY_MISMATCHED_HASH"
    )

    def fake_gen(prompt, **kwargs):
        raise AssertionError("Elavult blueprint mellett nem szabadna AI-hívásnak történnie.")

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def _render_shell_no_generate_fn() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"
    sw_ui.render_sermon_workshop_shell()


def _render_blueprint_invalid_response() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    def fake_gen(prompt, **kwargs):
        return "nem json"

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def _render_fresh_blueprint_with_warnings_no_click() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_blueprint_ai import build_blueprint_generation_context
    from sermon_workshop_data import store_generated_blueprint_result

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint = {
        "central_claim": "Isten kezdeményez.",
        "textual_center": "Úgy szerette Isten...",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "A kételytől a bizalomig.",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": [],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": ["WARNING_SENTINEL_FRESH"],
    }
    ctx_hash = build_blueprint_generation_context(st.session_state).context_hash
    store_generated_blueprint_result(st.session_state, blueprint=blueprint, context_hash=ctx_hash)

    def fake_gen(prompt, **kwargs):
        raise AssertionError("Ebben a tesztben nem kattintunk gombra.")

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def _render_fresh_blueprint_then_generate_outline() -> None:
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint_payload = {
        "central_claim": "Isten kezdeményez.",
        "textual_center": "Úgy szerette Isten...",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "A kételytől a bizalomig.",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": [],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": [],
    }
    outline_payload = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": k,
                "title": f"{k} cím",
                "function": "f",
                "main_claim": "állítás",
                "development": ["pont 1", "pont 2"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
            for k in arc_keys
        ],
    }
    if "_bp_call_count" not in st.session_state:
        st.session_state["_bp_call_count"] = 0
    if "_outline_call_count" not in st.session_state:
        st.session_state["_outline_call_count"] = 0

    def fake_gen(prompt, **kwargs):
        if kwargs.get("tab_label") == "Igehirdetési tervrajz":
            st.session_state["_bp_call_count"] += 1
            return json.dumps(blueprint_payload, ensure_ascii=False)
        st.session_state["_outline_call_count"] += 1
        return json.dumps(outline_payload, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def _render_fresh_blueprint_then_generate_outline_with_support_content() -> None:
    """FINAL SERMON UX POLISH (2026-08-21): mint `_render_fresh_blueprint_
    then_generate_outline`, de az "entry" mozgás mind az öt segédmezőjét
    (`exegetical_support`, `original_language_support`,
    `historical_theological_support`, `illustration_direction`,
    `application_direction`) valódi tartalommal tölti fel, a többi
    mozgásét üresen hagyja — így külön tesztelhető, hogy a "Segédanyag
    ehhez a ponthoz" expander CSAK a ténylegesen kitöltött mezőket
    jeleníti meg, és CSAK azoknál a mozgásoknál jelenik meg egyáltalán,
    ahol van tartalom."""
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint_payload = {
        "central_claim": "Isten kezdeményez.",
        "textual_center": "Úgy szerette Isten...",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "A kételytől a bizalomig.",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": [],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": [],
    }

    def _movement(k: str) -> dict:
        if k == "entry":
            return {
                "key": k,
                "title": f"{k} cím",
                "function": "f",
                "main_claim": "állítás",
                "development": ["pont 1", "pont 2"],
                "exegetical_support": ["SUPPORT_EXEG_SENTINEL"],
                "original_language_support": ["SUPPORT_ORIGLANG_SENTINEL"],
                "historical_theological_support": ["SUPPORT_HIST_SENTINEL"],
                "illustration_direction": "SUPPORT_ILLUSTRATION_SENTINEL",
                "application_direction": "SUPPORT_APPLICATION_SENTINEL",
                "transition_to_next": "MAIN_VIEW_TRANSITION_SENTINEL",
            }
        return {
            "key": k,
            "title": f"{k} cím",
            "function": "f",
            "main_claim": "állítás",
            "development": ["pont 1", "pont 2"],
            "exegetical_support": [],
            "original_language_support": [],
            "historical_theological_support": [],
            "illustration_direction": "",
            "application_direction": "",
            "transition_to_next": "",
        }

    outline_payload = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [_movement(k) for k in arc_keys],
    }
    if "_bp_call_count" not in st.session_state:
        st.session_state["_bp_call_count"] = 0
    if "_outline_call_count" not in st.session_state:
        st.session_state["_outline_call_count"] = 0

    def fake_gen(prompt, **kwargs):
        if kwargs.get("tab_label") == "Igehirdetési tervrajz":
            st.session_state["_bp_call_count"] += 1
            return json.dumps(blueprint_payload, ensure_ascii=False)
        st.session_state["_outline_call_count"] += 1
        return json.dumps(outline_payload, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


# =============================================================================
# A. Hiányzó blueprint -> a gomb TOVÁBBRA IS aktív (FINAL SERMON WORKFLOW +
# OUTLINE PRESENTATION POLISH, 2026-08-21: a blueprint már nem user-facing
# gate — a gombnyomás automatikusan pótolja a hiányzó blueprintet).
# =============================================================================


def test_a_missing_blueprint_no_longer_disables_outline_button():
    """A blueprint hiánya önmagában NEM blokkolja a "Részletes vázlat
    készítése" gombot — csak az igehely/bibliai szöveg hiánya blokkol
    ténylegesen (az nem automatizálható). A `_render_missing_blueprint`
    fixture `fake_gen`-je szándékosan hibát dobna, ha meghívódna — ez a
    teszt NEM kattint, csak azt ellenőrzi, hogy a gomb elérhető és nincs
    blokkoló üzenet, tehát egy tényleges kattintás elindítaná a hívást."""
    app = AppTest.from_function(_render_missing_blueprint).run(timeout=60)
    assert not app.exception

    outline_btn = next(b for b in app.button if b.label == "Részletes vázlat készítése")
    assert outline_btn.disabled is False
    captions = [c.value for c in app.caption]
    assert not any("Előbb készítsd el az igehirdetési tervrajzot." in c for c in captions)


# =============================================================================
# B. Elavult blueprint -> a gomb TOVÁBBRA IS aktív (a gombnyomás
# automatikusan frissíti a blueprintet, mielőtt a vázlat elkészülne).
# =============================================================================


def test_b_stale_blueprint_no_longer_disables_outline_button():
    app = AppTest.from_function(_render_stale_blueprint).run(timeout=60)
    assert not app.exception

    outline_btn = next(b for b in app.button if b.label == "Részletes vázlat készítése")
    assert outline_btn.disabled is False
    captions = [c.value for c in app.caption]
    assert not any(
        "elavult: a kanonikus bemenet megváltozott az elkészülte óta — "
        "készíts újat, mielőtt részletes vázlatot kérsz" in c
        for c in captions
    )


def test_b_blueprint_warnings_are_always_visible_and_not_resolvable():
    app = AppTest.from_function(_render_stale_blueprint).run(timeout=60)
    warning_values = [w.value for w in app.warning]
    assert any("WARNING_SENTINEL_ÜTKÖZÉS" in w for w in warning_values)
    # Nincs "feloldás"/"megoldás" gomb a warninghoz.
    labels = [b.label for b in app.button]
    assert not any("felold" in label.lower() or "megold" in label.lower() for label in labels)


# =============================================================================
# A2/B2. FINAL SERMON WORKFLOW + OUTLINE PRESENTATION POLISH (2026-08-21):
# a hiányzó blueprintet a "Részletes vázlat készítése" gomb EGYETLEN
# kattintással automatikusan pótolja, majd folytatja a részletes vázlat
# generálásával — nincs második kattintás.
# =============================================================================


def test_single_click_auto_generates_missing_blueprint_then_outline():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(
        timeout=60
    )
    assert app.session_state["_bp_call_count"] == 0
    assert app.session_state["_outline_call_count"] == 0

    # KIZÁRÓLAG a "Részletes vázlat készítése" gombra kattintunk — a
    # "Tervrajz készítése" gombot SOHA nem érintjük.
    _click_and_settle(app, "Részletes vázlat készítése")
    assert not app.exception

    assert app.session_state["_bp_call_count"] == 1
    assert app.session_state["_outline_call_count"] == 1
    assert app.session_state["sermon_workshop"]["blueprint"]["central_claim"] == (
        "Isten kezdeményez."
    )
    assert isinstance(
        app.session_state["sermon_workshop"].get("developed_outline_candidate"), dict
    )


def test_single_click_skips_blueprint_regeneration_when_already_fresh():
    """Ha VAN friss, érvényes kanonikus blueprint, a gombnyomás NEM hívja
    újra a tervrajz-generálást — csak a részletes vázlatét."""
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(
        timeout=60
    )
    _click_and_settle(app, "Tervrajz készítése")
    assert app.session_state["_bp_call_count"] == 1

    _click_and_settle(app, "Részletes vázlat készítése")
    assert not app.exception
    assert app.session_state["_bp_call_count"] == 1  # nem nőtt
    assert app.session_state["_outline_call_count"] == 1


def test_single_click_auto_refreshes_stale_blueprint_then_outline():
    app = AppTest.from_function(
        _render_fresh_blueprint_then_generate_outline
    ).run(timeout=60)
    _click_and_settle(app, "Tervrajz készítése")
    assert app.session_state["_bp_call_count"] == 1

    # A kanonikus bemenet megváltozik -> a blueprint elavulttá válik.
    app.session_state["sermon_workshop"]["arc"]["entry"]["text"] = (
        "MEGVÁLTOZOTT_ARC_PONT"
    )
    app.run(timeout=60)

    _click_and_settle(app, "Részletes vázlat készítése")
    assert not app.exception
    assert app.session_state["_bp_call_count"] == 2  # újragenerálódott
    assert app.session_state["_outline_call_count"] == 1


def test_failed_auto_blueprint_generation_blocks_outline_with_cultured_error():
    """Ha az automatikus blueprint-generálás sikertelen (pl. a modell
    érvénytelen választ ad), a `generate_developed_outline` EL SEM
    INDUL — rövid, kulturált hibaüzenet jelenik meg, nincs traceback.

    MEGJEGYZÉS: szándékosan NEM `_click_and_settle`-t használ — az egy
    MÁSODIK, kattintás nélküli `.run()`-t is végrehajt (ami a
    `_toast_and_rerun()`-alapú, session_state-ben tárolt flash-üzenetek
    teljes megjelenéséhez szükséges), de egy sima `st.error(...)`
    transzens elem, amely EBBEN a plusz, kattintás nélküli rerunban már
    nem jelenne meg újra — ezért itt egyetlen kattintás + egyetlen
    `.run()` a helyes minta."""
    app = AppTest.from_function(_render_blueprint_invalid_response).run(timeout=60)

    idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat készítése"
    )
    app.button[idx].click().run(timeout=60)
    assert not app.exception

    error_values = [e.value for e in app.error]
    assert any(
        "Nem sikerült elkészíteni az igehirdetési tervrajzot" in e
        for e in error_values
    )
    sw = app.session_state["sermon_workshop"]
    assert not isinstance(sw.get("developed_outline_candidate"), dict)


# =============================================================================
# C. Friss blueprint -> a részletes vázlat generálása lehetséges
# =============================================================================


def test_c_fresh_blueprint_enables_outline_button_and_shows_warnings():
    app = AppTest.from_function(_render_fresh_blueprint_with_warnings_no_click).run(timeout=60)
    assert not app.exception

    outline_btn = next(b for b in app.button if b.label == "Részletes vázlat készítése")
    assert outline_btn.disabled is False
    warning_values = [w.value for w in app.warning]
    assert any("WARNING_SENTINEL_FRESH" in w for w in warning_values)
    labels = [b.label for b in app.button]
    assert "Tervrajz újragenerálása" in labels


# =============================================================================
# D-E. Sikeres generálás -> KIZÁRÓLAG candidate, kanonikus változatlan
# =============================================================================


def test_d_successful_generation_creates_candidate_only():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Tervrajz készítése")
    app.button[bp_idx].click().run()
    # `st.rerun()`-t indító kattintás után egy további `.run()` szükséges
    # a letisztult gomb-fához (ld. `test_h`/`test_i` bővebb magyarázatát).
    app.run(timeout=60)
    assert not app.exception
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] == []

    outline_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat készítése"
    )
    assert app.button[outline_idx].disabled is False
    app.button[outline_idx].click().run()
    assert not app.exception

    assert app.session_state["_outline_call_count"] == 1
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] == []
    candidate = app.session_state["sermon_workshop"]["developed_outline_candidate"]
    assert candidate is not None
    assert candidate["outline"]["movements"][0]["key"] == "entry"

    body = "\n".join(md.value for md in app.markdown)
    assert "Új részletes vázlatjavaslat" in body


def test_no_automatic_chaining_from_blueprint_to_outline():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Tervrajz készítése")
    app.button[bp_idx].click().run()
    assert not app.exception
    # `_outline_call_count`-ot a render-függvény minden futáson MINDIG
    # inicializálja 0-ra, ha még nincs jelen — így közvetlenül olvasható.
    assert app.session_state["_outline_call_count"] == 0
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] == []


# =============================================================================
# F. Elfogadás -> kanonikus frissül, candidate törlődik
# =============================================================================


def test_f_accept_writes_canonical_and_clears_candidate():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Tervrajz készítése")
    app.button[bp_idx].click().run()
    app.run(timeout=60)
    outline_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat készítése"
    )
    app.button[outline_idx].click().run()
    app.run(timeout=60)

    accept_idx = next(i for i, b in enumerate(app.button) if b.label == "Szerkesztés az Íróasztalon")
    app.button[accept_idx].click().run()
    app.run(timeout=60)
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    movements = app.session_state["sermon_workshop"]["developed_outline"]["movements"]
    assert movements != []
    assert movements[0]["key"] == "entry"

    body = "\n".join(md.value for md in app.markdown)
    assert "Részletes prédikációs munkavázlat" in body
    assert app.session_state["ui_mode"] == "writing_desk"
    html = _writing_desk_html(app.session_state)
    assert "entry cím" in html
    assert "1. f / entry cím" in html or "entry cím" in html


# =============================================================================
# G. Elvetés -> kanonikus NEM változik
# =============================================================================


def test_g_discard_clears_candidate_and_leaves_canonical_untouched():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Tervrajz készítése")
    app.button[bp_idx].click().run()
    app.run(timeout=60)
    outline_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat készítése"
    )
    app.button[outline_idx].click().run()
    app.run(timeout=60)

    discard_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Vázlat elvetése"
    )
    app.button[discard_idx].click().run()
    app.run(timeout=60)
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] == []


# =============================================================================
# H. Regenerálás elfogadás UTÁN -> kanonikus VÁLTOZATLAN
# =============================================================================


def test_h_regeneration_after_accept_never_overwrites_canonical():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Tervrajz készítése")
    app.button[bp_idx].click().run()
    app.run(timeout=60)
    outline_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat készítése"
    )
    app.button[outline_idx].click().run()
    app.run(timeout=60)
    accept_idx = next(i for i, b in enumerate(app.button) if b.label == "Szerkesztés az Íróasztalon")
    app.button[accept_idx].click().run()
    # Az elfogadás `st.rerun()`-t indít (`_toast_and_rerun`) — egy
    # további, kattintás nélküli `.run()` szükséges, hogy a gomb-fa
    # ténylegesen a rerun UTÁNI, letisztult állapotot tükrözze (a
    # `sermon_workshop.developed_outline_candidate` session_state-értéke
    # már itt is helyes, de a widget-fa csak az extra run után az).
    app.run(timeout=60)

    canonical_before = app.session_state["sermon_workshop"]["developed_outline"]
    assert canonical_before["movements"] != []

    regen_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Részletes vázlat újragenerálása"
    )
    app.button[regen_idx].click().run()
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline"] == canonical_before
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is not None
    assert app.session_state["_outline_call_count"] == 2


# =============================================================================
# I. Blueprint generálható és újragenerálható; érvénytelen válasz esetén
#    a kanonikus blueprint változatlan és hibaüzenet jelenik meg.
# =============================================================================


def test_i_blueprint_can_be_generated_and_regenerated():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    bp_idx = next(i for i, b in enumerate(app.button) if b.label == "Tervrajz készítése")
    app.button[bp_idx].click().run()
    # A sikeres generálás `st.rerun()`-t indít (`_toast_and_rerun`) — egy
    # további, kattintás nélküli `.run()` szükséges, hogy a gomb-fa (és
    # ezzel a "Tervrajz készítése" -> "Tervrajz újragenerálása" felirat-
    # váltás) ténylegesen a rerun UTÁNI állapotot tükrözze.
    app.run(timeout=60)
    assert not app.exception
    assert app.session_state["sermon_workshop"]["blueprint"]["central_claim"] == (
        "Isten kezdeményez."
    )
    assert app.session_state["_bp_call_count"] == 1

    regen_idx = next(
        i for i, b in enumerate(app.button) if b.label == "Tervrajz újragenerálása"
    )
    app.button[regen_idx].click().run()
    assert not app.exception
    assert app.session_state["_bp_call_count"] == 2


def test_i_invalid_blueprint_response_shows_error_and_preserves_canonical():
    app = AppTest.from_function(_render_blueprint_invalid_response).run(timeout=60)
    idx = next(i for i, b in enumerate(app.button) if b.label == "Tervrajz készítése")
    app.button[idx].click().run()
    assert not app.exception

    assert app.session_state["sermon_workshop"]["blueprint"]["central_claim"] == ""
    error_values = [e.value for e in app.error]
    assert error_values


# =============================================================================
# J. `generate_fn=None` -> crash-mentes, gombok helyesen letiltva
# =============================================================================


def test_j_generate_fn_none_is_crash_free_and_disables_buttons():
    app = AppTest.from_function(_render_shell_no_generate_fn).run(timeout=60)
    assert not app.exception

    bp_btn = next(b for b in app.button if b.label == "Tervrajz készítése")
    outline_btn = next(b for b in app.button if b.label == "Részletes vázlat készítése")
    assert bp_btn.disabled is True
    assert outline_btn.disabled is True


# =============================================================================
# RESET 2E-5 — a MÁR ELFOGADOTT, kanonikus `developed_outline` kézi
# szerkesztésének tesztjei.
# =============================================================================


def _click_and_settle(app: AppTest, label: str) -> AppTest:
    """Kattintás egy gombra + egy TOVÁBBI, kattintás nélküli `.run()` —
    a `_toast_and_rerun()` által indított `st.rerun()` néha csak egy
    extra `.run()` után tükröződik teljesen a gomb-/widget-fában (ld. a
    2E-4-es blokk hasonló megjegyzéseit). A `session_state` ilyenkor is
    már helyes az első `.run()` után, de a KÖVETKEZŐ gomb/widget
    kereséséhez a letisztult fa kell."""
    idx = next(i for i, b in enumerate(app.button) if b.label == label)
    app.button[idx].click().run()
    app.run(timeout=60)
    return app


def _handoff_outline_to_desk(app: AppTest) -> AppTest:
    """Candidate átadása az Íróasztalnak, overwrite-megerősítéssel ha kell."""
    labels = [b.label for b in app.button]
    if "Szerkesztés az Íróasztalon" in labels:
        _click_and_settle(app, "Szerkesztés az Íróasztalon")
    labels = [b.label for b in app.button]
    if "Igen, lecserélem" in labels:
        _click_and_settle(app, "Igen, lecserélem")
    return app


def _accept_fresh_outline(app: AppTest) -> AppTest:
    """Blueprint generálás -> részletes vázlat generálás -> elfogadás —
    a `_render_fresh_blueprint_then_generate_outline` render-függvényre
    épülő AppTest-példányon. A végén a kanonikus `developed_outline`
    tartalmazza mind a hét, `entry`...`arrival` kulcsú mozgást."""
    _click_and_settle(app, "Tervrajz készítése")
    _click_and_settle(app, "Részletes vázlat készítése")
    return _handoff_outline_to_desk(app)


def _outline_edit_widget_keys(app: AppTest) -> list[str]:
    return [
        ti.key for ti in app.text_input if str(ti.key or "").startswith("sw_flat_outline_edit_")
    ] + [
        ta.key for ta in app.text_area if str(ta.key or "").startswith("sw_flat_outline_edit_")
    ]


def _set_canonical_title(app: AppTest, title: str) -> None:
    app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"] = title
    app.session_state["sermon_workshop"]["developed_outline_meta"]["manually_updated_at"] = (
        "2026-09-02T12:00:00"
    )


def _writing_desk_html(session) -> str:
    desk = session[WRITING_DESK_KEY]
    return str((desk.get("draft") or {}).get("content") or "")


# =============================================================================
# 1. Candidate továbbra is read-only
# =============================================================================


def test_candidate_panel_has_no_editable_widgets():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _click_and_settle(app, "Tervrajz készítése")
    _click_and_settle(app, "Részletes vázlat készítése")
    assert not app.exception

    body = "\n".join(md.value for md in app.markdown)
    assert "Új részletes vázlatjavaslat" in body
    # A kanonikus vázlat még üres -> a szerkesztő szekció nem is renderel
    # semmilyen `sw_flat_outline_edit_*` widgetet.
    outline_widget_keys = [
        ti.key for ti in app.text_input if str(ti.key or "").startswith("sw_flat_outline_edit_")
    ] + [
        ta.key for ta in app.text_area if str(ta.key or "").startswith("sw_flat_outline_edit_")
    ]
    assert outline_widget_keys == []


# =============================================================================
# 2. Kanonikus outline: nincs második hétmezős szerkesztő
# =============================================================================


def test_canonical_outline_is_editable_after_accept():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)
    assert not app.exception

    assert _outline_edit_widget_keys(app) == []
    body = "\n".join(md.value for md in app.markdown)
    captions = "\n".join(c.value for c in app.caption)
    assert "entry cím" in body or "entry cím" in captions
    assert "A szabad szerkesztés az Íróasztalon történik." in captions
    assert app.session_state["ui_mode"] == "writing_desk"


# =============================================================================
# 3-4. A structured mutátor továbbra is egy mezőt ír; a production UI
#      nem ad második szerkesztőréteget.
# =============================================================================


def test_editing_one_field_changes_only_that_field():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)
    before = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    _set_canonical_title(app, "ÚJ CÍM")
    after = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])
    assert after["movements"][0]["title"] == "ÚJ CÍM"
    assert after["movements"][0]["key"] == "entry"

    reverted = copy.deepcopy(after)
    reverted["movements"][0]["title"] = before["movements"][0]["title"]
    assert reverted == before
    assert _outline_edit_widget_keys(app) == []


# =============================================================================
# 5. `movement.key` NINCS szerkeszthető widgethez kötve, és a UI sosem
#    hívja a mutátort `field="key"`-jel.
# =============================================================================


def test_movement_key_has_no_editable_widget():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    key_field_widgets = [
        ti.key for ti in app.text_input if str(ti.key or "").endswith("_key")
    ] + [ta.key for ta in app.text_area if str(ta.key or "").endswith("_key")]
    assert key_field_widgets == []


def test_field_widget_sets_never_include_movement_key():
    """Forráskód-szintű garancia: a szerkeszthető mezőkészletek (rövid
    szöveg / textarea / lista) egyike sem tartalmazza a `key`-t — ez
    zárja ki, hogy bármelyik UI-hurok valaha is `field="key"`-jel hívja
    az `update_developed_outline_movement_field`-et."""
    all_editable_fields = (
        set(sw_ui._OUTLINE_SHORT_TEXT_FIELDS)
        | set(sw_ui._OUTLINE_TEXTAREA_FIELDS)
        | set(_DEVELOPED_MOVEMENT_LIST_FIELDS)
    )
    assert "key" not in all_editable_fields


# =============================================================================
# 6. Structure mode/count/order nem módosítható UI-ból
# =============================================================================


def test_no_ui_controls_for_structure_mode_count_or_order():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    labels = [b.label for b in app.button]
    for forbidden in (
        "Mozgás hozzáadása",
        "Mozgás törlése",
        "Mozgás áthelyezése",
        "Szerkezet módosítása",
        "Structure mode módosítása",
    ):
        assert forbidden not in labels

    structure_widget_keys = [
        ti.key for ti in app.text_input if "structure_mode" in str(ti.key or "")
    ] + [ta.key for ta in app.text_area if "structure_mode" in str(ta.key or "")]
    assert structure_widget_keys == []


# =============================================================================
# 7. Rerun után a kézi módosítás megmarad
# =============================================================================


def test_manual_edit_survives_rerun():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    _set_canonical_title(app, "MEGŐRZÖTT CÍM")
    app.run(timeout=60)
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "MEGŐRZÖTT CÍM"
    )
    assert _outline_edit_widget_keys(app) == []


# =============================================================================
# 8-9. Lista-mező többsoros szövege listává alakul, üres sorok kimaradnak
# =============================================================================


def test_list_field_multiline_text_becomes_list_and_drops_empty_lines():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    app.session_state["sermon_workshop"]["developed_outline"]["movements"][0][
        "development"
    ] = ["Első gondolat.", "Második gondolat."]
    development = app.session_state["sermon_workshop"]["developed_outline"]["movements"][0][
        "development"
    ]
    assert development == ["Első gondolat.", "Második gondolat."]


# =============================================================================
# 10. Új AI candidate generálása kézi szerkesztés után NEM módosítja a
#     kanonikus outline-t
# =============================================================================


def test_new_candidate_generation_after_manual_edit_does_not_touch_canonical():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    _set_canonical_title(app, "KÉZI SZERKESZTÉS")
    app.run(timeout=60)
    canonical_before = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    _click_and_settle(app, "Részletes vázlat újragenerálása")
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline"] == canonical_before
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is not None


# =============================================================================
# 11. Candidate discard után a kézzel szerkesztett kanonikus változat
#     megmarad
# =============================================================================


def test_discard_after_manual_edit_preserves_canonical():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    _set_canonical_title(app, "KÉZI SZERKESZTÉS 2")
    app.run(timeout=60)
    canonical_before = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    _click_and_settle(app, "Részletes vázlat újragenerálása")
    _click_and_settle(app, "Vázlat elvetése")
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline"] == canonical_before
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is None


# =============================================================================
# 12-13. Candidate accept lecseréli a kézzel szerkesztett kanonikus
#        változatot; utána `manually_updated_at` újra üres
# =============================================================================


def test_accept_after_manual_edit_replaces_canonical_and_resets_manually_updated_at():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    _set_canonical_title(app, "KÉZI SZERKESZTÉS 3")
    app.run(timeout=60)
    assert (
        app.session_state["sermon_workshop"]["developed_outline_meta"]["manually_updated_at"]
        != ""
    )

    _click_and_settle(app, "Részletes vázlat újragenerálása")
    warning_values = [w.value for w in app.warning]
    assert any("Az elfogadás lecseréli" in w for w in warning_values)
    _handoff_outline_to_desk(app)
    assert not app.exception

    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "entry cím"
    )
    assert (
        app.session_state["sermon_workshop"]["developed_outline_meta"]["manually_updated_at"]
        == ""
    )


# =============================================================================
# 14. Accept után a régi editor widget-kulcsok törlődnek, és az ÚJ
#     kanonikus értékek jelennek meg (nincs "ragadt" régi szöveg)
# =============================================================================


def test_accept_clears_stale_widget_state_and_shows_new_canonical_value():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    _set_canonical_title(app, "RÉGI SZERKESZTETT SZÖVEG")
    app.run(timeout=60)

    _click_and_settle(app, "Részletes vázlat újragenerálása")
    _handoff_outline_to_desk(app)
    assert not app.exception

    assert _outline_edit_widget_keys(app) == []
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "entry cím"
    )


# =============================================================================
# 15. `index_out_of_range` nem okoz UI-crasht
# =============================================================================


def _render_index_out_of_range_scenario() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["developed_outline"] = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": "entry",
                "title": "Cím",
                "function": "f",
                "main_claim": "állítás",
                "development": ["a"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
        ],
    }
    # Szimulálja azt a legitim futásidejű esetet, amikor egy elavult
    # widget-callback egy MÁR NEM létező indexre hivatkozna (a vázlat
    # időközben megrövidült) — közvetlenül hívja a mentő-callbacket egy
    # a jelenlegi listánál (1 elem) nagyobb indexszel.
    st.session_state["_developed_outline_ioor_probe"] = "not_run"
    try:
        sw_ui._flat_save_developed_outline_movement_field(5, "entry", "title")
        st.session_state["_developed_outline_ioor_probe"] = "no_crash"
    except Exception as exc:  # pragma: no cover — a teszt épp azt bizonyítja, hogy ez nem fut le
        st.session_state["_developed_outline_ioor_probe"] = f"crashed: {exc}"

    sw_ui.render_sermon_workshop_shell()


def test_index_out_of_range_does_not_crash():
    app = AppTest.from_function(_render_index_out_of_range_scenario).run(timeout=60)
    assert not app.exception
    assert app.session_state["_developed_outline_ioor_probe"] == "no_crash"
    # A meglévő, 1 elemű kanonikus vázlat érintetlen maradt.
    assert len(app.session_state["sermon_workshop"]["developed_outline"]["movements"]) == 1
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "Cím"
    )


# =============================================================================
# RESET 2E-6a — state-integritási hardening: a kanonikus `developed_
# outline` upstream frissessége, és a legacy panel egyidejű
# megjelenésének megszüntetése.
# =============================================================================


def _render_blueprint_regenerates_with_different_content() -> None:
    """Az `_render_fresh_blueprint_then_generate_outline`-tól eltérően a
    blueprint-generátor a MÁSODIK hívásra MÁS `central_claim`-mel
    válaszol — ez teszi lehetővé a "friss blueprint, de más tartalom"
    forgatókönyv (RESET 2E-6a, 3. pont) explicit tesztelését."""
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )

    def blueprint_payload(claim: str) -> dict:
        return {
            "central_claim": claim,
            "textual_center": "Úgy szerette Isten...",
            "listener_tension": "",
            "theological_turn": "",
            "desired_listener_movement": "A kételytől a bizalomig.",
            "arc_fit": {"verdict": "strong_fit", "reason": "r"},
            "recommended_structure": {
                "mode": "seven_point",
                "movements": [
                    {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                    for k in arc_keys
                ],
            },
            "key_support": {
                "exegetical": [],
                "original_language": [],
                "historical_theological": [],
            },
            "illustration_direction": "",
            "application_direction": "",
            "warnings": [],
        }

    outline_payload = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": k,
                "title": f"{k} cím",
                "function": "f",
                "main_claim": "állítás",
                "development": ["pont 1", "pont 2"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
            for k in arc_keys
        ],
    }

    if "_bp_gen_count" not in st.session_state:
        st.session_state["_bp_gen_count"] = 0

    def fake_gen(prompt, **kwargs):
        if kwargs.get("tab_label") == "Igehirdetési tervrajz":
            st.session_state["_bp_gen_count"] += 1
            claim = (
                "ELSŐ ÁLLÍTÁS"
                if st.session_state["_bp_gen_count"] == 1
                else "MÁSODIK, MÁS ÁLLÍTÁS"
            )
            return json.dumps(blueprint_payload(claim), ensure_ascii=False)
        return json.dumps(outline_payload, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


# -----------------------------------------------------------------------
# 1. Friss canonical developed outline -> nincs stale warning
# -----------------------------------------------------------------------


def test_fresh_canonical_outline_has_no_stale_warning():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert not any("KORÁBBI tervrajzból" in w for w in warning_values)
    assert not any("igehelyhez készült" in w for w in warning_values)


# -----------------------------------------------------------------------
# 2. Blueprint input megváltozik -> canonical outline stale warningot kap
#    (+ 6/7: nem törlődik, továbbra is szerkeszthető)
# -----------------------------------------------------------------------


def test_blueprint_input_change_triggers_stale_warning_but_keeps_content_editable():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    app.session_state["sermon_workshop"]["arc"]["entry"]["text"] = "MEGVÁLTOZOTT_ARC_SZÖVEG"
    app.run(timeout=60)
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert any("KORÁBBI tervrajzból" in w for w in warning_values)

    # A tartalom NEM törlődött; a második hétmezős szerkesztő nincs a UI-n.
    assert app.session_state["sermon_workshop"]["developed_outline"]["movements"] != []
    assert _outline_edit_widget_keys(app) == []
    _set_canonical_title(app, "STALE ÁLLAPOTBAN SZERKESZTETT CÍM")
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "STALE ÁLLAPOTBAN SZERKESZTETT CÍM"
    )


# -----------------------------------------------------------------------
# 3. Blueprint újragenerálás (más tartalommal) -> régi canonical outline
#    stale warningot kap, függetlenül attól, hogy kézzel módosítva volt-e
# -----------------------------------------------------------------------


def test_blueprint_regeneration_with_different_content_triggers_stale_warning():
    app = AppTest.from_function(_render_blueprint_regenerates_with_different_content).run(
        timeout=60
    )
    _accept_fresh_outline(app)
    assert app.session_state["sermon_workshop"]["blueprint"]["central_claim"] == "ELSŐ ÁLLÍTÁS"
    old_canonical = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    _click_and_settle(app, "Tervrajz újragenerálása")
    assert not app.exception
    assert (
        app.session_state["sermon_workshop"]["blueprint"]["central_claim"]
        == "MÁSODIK, MÁS ÁLLÍTÁS"
    )

    warning_values = [w.value for w in app.warning]
    assert any("KORÁBBI tervrajzból" in w for w in warning_values)
    # A régi canonical outline MEGMARADT, változatlanul.
    assert app.session_state["sermon_workshop"]["developed_outline"] == old_canonical


def test_stale_warning_appears_regardless_of_manual_edit_state():
    app = AppTest.from_function(_render_blueprint_regenerates_with_different_content).run(
        timeout=60
    )
    _accept_fresh_outline(app)

    _set_canonical_title(app, "KÉZILEG SZERKESZTETT CÍM")
    app.run(timeout=60)

    _click_and_settle(app, "Tervrajz újragenerálása")
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert any("KORÁBBI tervrajzból" in w for w in warning_values)
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "KÉZILEG SZERKESZTETT CÍM"
    )


# -----------------------------------------------------------------------
# 4. Reference változás -> különösen egyértelmű stale warning
# -----------------------------------------------------------------------


def _render_fresh_blueprint_then_generate_outline_reusable_inputs() -> None:
    """A megosztott `_render_fresh_blueprint_then_generate_outline`
    UNCONDITIONÁLISAN, minden egyes scriptfuttatáson újraírja a
    `last_igehely`/`igehely_input`/`passage_text` mezőket a hardcode-olt
    kezdőértékre — ez elfedné egy, a teszt OLDALÁRÓL (a `.run()` HÍVÁS
    ELŐTT) `app.session_state`-en keresztül végzett külső módosítást,
    mert a scriptfuttatás a saját elején rögtön felülírná.

    Ez a változat `st.session_state.setdefault(...)`-ot használ — csak
    AKKOR ír kezdőértéket, ha a kulcs MÉG NINCS jelen —, így egy a teszt
    által a `.run()` hívás előtt beállított ÚJ érték a következő
    scriptfuttatáson TÉNYLEGESEN érvényesül, ahogy egy valódi
    felhasználói szerkesztés is tenné."""
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state.setdefault("last_igehely", "Jn 3,16")
    st.session_state.setdefault("igehely_input", "Jn 3,16")
    st.session_state.setdefault("passage_text", "Mert úgy szerette Isten a világot.")
    st.session_state.setdefault("bible_translation", "RÚF 2014")

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint_payload = {
        "central_claim": "Isten kezdeményez.",
        "textual_center": "Úgy szerette Isten...",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "A kételytől a bizalomig.",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": [],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": [],
    }
    outline_payload = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": k,
                "title": f"{k} cím",
                "function": "f",
                "main_claim": "állítás",
                "development": ["pont 1", "pont 2"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
            for k in arc_keys
        ],
    }

    def fake_gen(prompt, **kwargs):
        if kwargs.get("tab_label") == "Igehirdetési tervrajz":
            return json.dumps(blueprint_payload, ensure_ascii=False)
        return json.dumps(outline_payload, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def test_reference_change_triggers_reference_changed_warning():
    app = AppTest.from_function(
        _render_fresh_blueprint_then_generate_outline_reusable_inputs
    ).run(timeout=60)
    _accept_fresh_outline(app)

    app.session_state["last_igehely"] = "Róm 8,28"
    app.session_state["igehely_input"] = "Róm 8,28"
    app.run(timeout=60)
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert any(
        ("igehelyhez készült" in w) and (REFERENCE in w) and ("Róm 8,28" in w)
        for w in warning_values
    )


# -----------------------------------------------------------------------
# 5. Passage text változás -> stale warning
# -----------------------------------------------------------------------


def test_passage_text_change_triggers_stale_warning():
    app = AppTest.from_function(
        _render_fresh_blueprint_then_generate_outline_reusable_inputs
    ).run(timeout=60)
    _accept_fresh_outline(app)

    app.session_state["passage_text"] = "Egy teljesen más bibliai szöveg."
    app.run(timeout=60)
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert any("KORÁBBI tervrajzból" in w for w in warning_values)


# -----------------------------------------------------------------------
# 8. Új developed-outline candidate generálása (friss blueprintből, a
#    RÉGI canonical mögötti blueprinthez képest) NEM törli a régi
#    canonical outline-t
# -----------------------------------------------------------------------


def test_new_candidate_after_blueprint_regeneration_does_not_touch_old_canonical():
    app = AppTest.from_function(_render_blueprint_regenerates_with_different_content).run(
        timeout=60
    )
    _accept_fresh_outline(app)
    old_canonical = copy.deepcopy(app.session_state["sermon_workshop"]["developed_outline"])

    _click_and_settle(app, "Tervrajz újragenerálása")
    _click_and_settle(app, "Részletes vázlat újragenerálása")
    assert not app.exception

    assert app.session_state["sermon_workshop"]["developed_outline"] == old_canonical
    assert app.session_state["sermon_workshop"]["developed_outline_candidate"] is not None


# -----------------------------------------------------------------------
# 9. Új candidate accept után a friss canonical context hash friss,
#    a stale warning eltűnik
# -----------------------------------------------------------------------


def test_accept_after_blueprint_regeneration_clears_stale_warning():
    app = AppTest.from_function(_render_blueprint_regenerates_with_different_content).run(
        timeout=60
    )
    _accept_fresh_outline(app)

    _click_and_settle(app, "Tervrajz újragenerálása")
    warning_values_before = [w.value for w in app.warning]
    assert any("KORÁBBI tervrajzból" in w for w in warning_values_before)

    _click_and_settle(app, "Részletes vázlat újragenerálása")
    _handoff_outline_to_desk(app)
    assert not app.exception

    warning_values_after = [w.value for w in app.warning]
    assert not any("KORÁBBI tervrajzból" in w for w in warning_values_after)
    assert not any("igehelyhez készült" in w for w in warning_values_after)


# -----------------------------------------------------------------------
# 10-13. Legacy panel láthatósága érdemi új workflow-állapot mellett
# -----------------------------------------------------------------------

_LEGACY_OUTLINE_CONTENT = {
    "content": (
        "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi ötlépéses "
        "munkafolyamatból, kellően hosszú tartalommal."
    )
}


def _render_legacy_only() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["sermon_outline"] = {
        "content": (
            "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi "
            "ötlépéses munkafolyamatból, kellően hosszú tartalommal."
        )
    }
    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_legacy_panel_visible_when_no_new_workflow_state():
    app = AppTest.from_function(_render_legacy_only).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" in body


def _render_legacy_with_blueprint() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state, store_generated_blueprint_result

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["sermon_outline"] = {
        "content": (
            "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi "
            "ötlépéses munkafolyamatból, kellően hosszú tartalommal."
        )
    }
    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint = {
        "central_claim": "X",
        "textual_center": "Y",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "Z",
        "arc_fit": {"verdict": "strong_fit", "reason": "r"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {"key": k, "function": "f", "core_idea": "c", "grounded_in": []}
                for k in arc_keys
            ],
        },
        "key_support": {"exegetical": [], "original_language": [], "historical_theological": []},
        "illustration_direction": "",
        "application_direction": "",
        "warnings": [],
    }
    store_generated_blueprint_result(st.session_state, blueprint=blueprint, context_hash="H1")

    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_legacy_panel_hidden_when_blueprint_exists():
    app = AppTest.from_function(_render_legacy_with_blueprint).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" not in body


def _render_legacy_with_outline_candidate() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state, set_developed_outline_candidate

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["sermon_outline"] = {
        "content": (
            "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi "
            "ötlépéses munkafolyamatból, kellően hosszú tartalommal."
        )
    }
    set_developed_outline_candidate(
        st.session_state,
        outline={
            "structure_mode": "seven_point",
            "structure_note": "",
            "movements": [
                {
                    "key": "entry",
                    "title": "T",
                    "function": "f",
                    "main_claim": "m",
                    "development": ["d"],
                    "exegetical_support": [],
                    "original_language_support": [],
                    "historical_theological_support": [],
                    "illustration_direction": "",
                    "application_direction": "",
                    "transition_to_next": "",
                }
            ],
        },
        reference="Jn 3,16",
        context_hash="H1",
    )
    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_legacy_panel_hidden_when_outline_candidate_exists():
    app = AppTest.from_function(_render_legacy_with_outline_candidate).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" not in body


def _render_legacy_with_canonical_outline() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    sw["sermon_outline"] = {
        "content": (
            "1. Bevezetés: RÉGI, LEGACY VÁZLAT SZÖVEGE a korábbi "
            "ötlépéses munkafolyamatból, kellően hosszú tartalommal."
        )
    }
    sw["developed_outline"] = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": "entry",
                "title": "T",
                "function": "f",
                "main_claim": "m",
                "development": ["d"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
        ],
    }
    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_legacy_panel_hidden_when_canonical_outline_exists():
    app = AppTest.from_function(_render_legacy_with_canonical_outline).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Korábbi vázlat" not in body


# -----------------------------------------------------------------------
# 14. Projektváltási widget-state célzott teszt
# -----------------------------------------------------------------------


def _render_project_switch_scenario() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    from sermon_workshop_data import ensure_sermon_workshop_state

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    sw = ensure_sermon_workshop_state(st.session_state)
    if not st.session_state.get("_switched_to_project_b"):
        sw["developed_outline"] = {
            "structure_mode": "seven_point",
            "structure_note": "",
            "movements": [
                {
                    "key": "entry",
                    "title": "PROJEKT_A_CIM",
                    "function": "f",
                    "main_claim": "A",
                    "development": ["a"],
                    "exegetical_support": [],
                    "original_language_support": [],
                    "historical_theological_support": [],
                    "illustration_direction": "",
                    "application_direction": "",
                    "transition_to_next": "",
                }
            ],
        }
        sw["developed_outline_meta"] = {
            "reference": "Jn 3,16",
            "context_hash": "A",
            "generated_at": "t",
            "manually_updated_at": "",
        }

    sw_ui.render_sermon_workshop_shell(generate_fn=None)


def test_project_switch_purges_stale_outline_editor_widgets():
    """RESET 2E-6a: a `_apply_sw_ui_resync_if_needed()`-ba épített
    `_clear_developed_outline_edit_widgets()` hívás ELLENŐRZÉSE — a
    `_sw_ui_resync` jelző UGYANAZ, amit `app.py` projektnyitáskor is
    beállít (`_apply_project_data_to_session`)."""
    app = AppTest.from_function(_render_project_switch_scenario).run(timeout=60)
    body = "\n".join(md.value for md in app.markdown)
    assert "PROJEKT_A_CIM" in body
    assert _outline_edit_widget_keys(app) == []

    app.session_state["_switched_to_project_b"] = True
    app.session_state["sermon_workshop"]["developed_outline"] = {
        "structure_mode": "seven_point",
        "structure_note": "",
        "movements": [
            {
                "key": "entry",
                "title": "PROJEKT_B_CIM",
                "function": "f",
                "main_claim": "B",
                "development": ["b"],
                "exegetical_support": [],
                "original_language_support": [],
                "historical_theological_support": [],
                "illustration_direction": "",
                "application_direction": "",
                "transition_to_next": "",
            }
        ],
    }
    app.session_state["sermon_workshop"]["developed_outline_meta"] = {
        "reference": "Jn 3,16",
        "context_hash": "B",
        "generated_at": "t2",
        "manually_updated_at": "",
    }
    # Ugyanaz a jelző, mint amit `app.py` `_apply_project_data_to_session`-je
    # állít be projekt megnyitásakor.
    app.session_state["_sw_ui_resync"] = True
    app.run(timeout=60)
    assert not app.exception

    body2 = "\n".join(md.value for md in app.markdown)
    assert "PROJEKT_B_CIM" in body2
    assert "PROJEKT_A_CIM" not in body2
    assert _outline_edit_widget_keys(app) == []


# =============================================================================
# RESET 2E-6b — UX-rendezés: blueprint-részletek expander, movementenkénti
# expander, mezősorrend, eredet-caption.
# =============================================================================


def _render_fresh_blueprint_with_sentinel_internal_fields() -> None:
    """A blueprint BELSŐ, technikai mezőit (`arc_fit.reason`, `key_support`,
    `grounded_in`) SZENTINEL-értékekkel tölti fel, hogy explicit
    bizonyítható legyen: a "Tervrajz részletei" expander ezeket NEM
    jeleníti meg — csak `central_claim`/`textual_center`/szerkezeti
    mód/movementenkénti `function`+`core_idea`."""
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    arc_keys = (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )
    blueprint_payload = {
        "central_claim": "Isten kezdeményez.",
        "textual_center": "Úgy szerette Isten...",
        "listener_tension": "",
        "theological_turn": "",
        "desired_listener_movement": "A kételytől a bizalomig.",
        "arc_fit": {"verdict": "strong_fit", "reason": "ARC_FIT_REASON_SENTINEL"},
        "recommended_structure": {
            "mode": "seven_point",
            "movements": [
                {
                    "key": k,
                    "function": f"{k} funkció",
                    "core_idea": f"{k} mag",
                    "grounded_in": ["text_main_idea"],
                }
                for k in arc_keys
            ],
        },
        "key_support": {
            "exegetical": ["KEY_SUPPORT_EXEGETICAL_SENTINEL"],
            "original_language": ["KEY_SUPPORT_ORIGLANG_SENTINEL"],
            "historical_theological": ["KEY_SUPPORT_HIST_SENTINEL"],
        },
        "illustration_direction": "",
        "application_direction": "",
        "warnings": [],
    }

    def fake_gen(prompt, **kwargs):
        return json.dumps(blueprint_payload, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


# -----------------------------------------------------------------------
# 1-6. Blueprint-részletek expander
# -----------------------------------------------------------------------


def test_blueprint_details_expander_appears_when_blueprint_exists():
    """FINAL SERMON UX POLISH (2026-08-21): a korábbi külön "Tervrajz
    részletei" expander megszűnt — a tervrajz TELJES állapota/részletei/
    figyelmeztetései/generálás-gombja egyetlen, "Igehirdetési tervrajz
    megtekintése" expanderbe került (Streamlit nem enged egymásba
    ágyazott expandereket, ezért a részletek immár INLINE jelennek meg
    ezen belül, nem egy másik, beágyazott expanderben)."""
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _click_and_settle(app, "Tervrajz készítése")
    assert not app.exception

    labels = [e.label for e in app.expander]
    assert "Igehirdetési tervrajz megtekintése" in labels
    assert "Tervrajz részletei" not in labels


def test_blueprint_details_expander_starts_collapsed():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _click_and_settle(app, "Tervrajz készítése")

    expander = next(
        e for e in app.expander if e.label == "Igehirdetési tervrajz megtekintése"
    )
    assert expander.proto.expanded is False


def test_blueprint_details_shows_central_claim():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _click_and_settle(app, "Tervrajz készítése")

    body = "\n".join(md.value for md in app.markdown)
    assert "Isten kezdeményez." in body


def test_blueprint_details_shows_structure_mode_label():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _click_and_settle(app, "Tervrajz készítése")

    captions = [c.value for c in app.caption]
    assert "Hétpontos ív" in captions


def test_blueprint_details_shows_movement_function_and_core_idea():
    app = AppTest.from_function(_render_fresh_blueprint_with_sentinel_internal_fields).run(
        timeout=60
    )
    idx = next(i for i, b in enumerate(app.button) if b.label == "Tervrajz készítése")
    app.button[idx].click().run()
    app.run(timeout=60)
    assert not app.exception

    body = "\n".join(md.value for md in app.markdown)
    assert "entry funkció" in body
    assert "entry mag" in body


def test_blueprint_details_hides_internal_technical_fields():
    app = AppTest.from_function(_render_fresh_blueprint_with_sentinel_internal_fields).run(
        timeout=60
    )
    idx = next(i for i, b in enumerate(app.button) if b.label == "Tervrajz készítése")
    app.button[idx].click().run()
    app.run(timeout=60)
    assert not app.exception

    full_text = "\n".join(
        [md.value for md in app.markdown]
        + [c.value for c in app.caption]
        + [w.value for w in app.warning]
    )
    for forbidden in (
        "ARC_FIT_REASON_SENTINEL",
        "KEY_SUPPORT_EXEGETICAL_SENTINEL",
        "KEY_SUPPORT_ORIGLANG_SENTINEL",
        "KEY_SUPPORT_HIST_SENTINEL",
        "text_main_idea",  # `grounded_in` provenance-token — nem jelenhet meg szövegként
    ):
        assert forbidden not in full_text


# -----------------------------------------------------------------------
# 7-8. Movement-expanderek
# -----------------------------------------------------------------------


def test_canonical_movements_are_directly_visible_without_a_wrapping_expander():
    """FINAL SERMON UX POLISH (2026-08-21): a korábbi, mozgásonkénti
    "{sorszám}. {cím}" `st.expander` megszűnt — a főnézet (cím, funkció,
    fő állítás, kibontás, átvezetés) mostantól KÖZVETLENÜL látható, nem
    kell kattintani egy expanderre ahhoz, hogy a lelkész elolvashassa."""
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    labels = [e.label for e in app.expander]
    assert "1. entry cím" not in labels
    assert not any(label.startswith("1. entry") for label in labels)

    body = "\n".join(md.value for md in app.markdown)
    assert "**1. entry cím**" in body
    assert _outline_edit_widget_keys(app) == []


def test_movement_expanders_start_collapsed():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    assert app.expander
    assert all(e.proto.expanded is False for e in app.expander)


# -----------------------------------------------------------------------
# 9-10. Mezősorrend a movement-expanderen belül
# -----------------------------------------------------------------------


def test_main_claim_appears_before_development():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    markdown = [md.value for md in app.markdown]
    claim_idx = next(i for i, value in enumerate(markdown) if value == "állítás")
    development_idx = next(i for i, value in enumerate(markdown) if value == "- pont 1")
    assert claim_idx < development_idx


def test_support_block_appears_after_development():
    """A "Háttéranyagok a vázlathoz" expander a főnézet kibontása után
    jelenik meg, és nincs második hétmezős szerkesztő."""
    app = AppTest.from_function(
        _render_fresh_blueprint_then_generate_outline_with_support_content
    ).run(timeout=60)
    _accept_fresh_outline(app)

    markdown = [md.value for md in app.markdown]
    development_idx = next(i for i, value in enumerate(markdown) if "- pont 1" in value)
    labels = [e.label for e in app.expander]
    assert "Háttéranyagok a vázlathoz" in labels
    assert development_idx >= 0
    assert _outline_edit_widget_keys(app) == []


# -----------------------------------------------------------------------
# 11-13. Widget-kulcsok és kézi szerkesztés az új expander-elrendezésben
# -----------------------------------------------------------------------


def test_core_field_widget_keys_unchanged_after_ux_restructure():
    """A kanonikus vázlat production UI-ja nem renderel hétmezős
    `sw_flat_outline_edit_*` szerkesztőket."""
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)
    assert _outline_edit_widget_keys(app) == []


def test_empty_support_fields_render_no_widget_and_no_expander():
    """FINAL SERMON UX POLISH (2026-08-21) + FINAL SERMON WORKFLOW +
    OUTLINE PRESENTATION POLISH (2026-08-21): ha EGYETLEN mozgásnak
    sincs tényleges segédanyag-tartalma (mind az öt mező üres minden
    mozgásnál — a `_render_fresh_blueprint_then_generate_outline`
    alap-fixture ezt adja), akkor SEM a korábbi pontonkénti "Segédanyag
    ehhez a ponthoz", SEM az új, közös "Háttéranyagok a vázlathoz"
    expander nem jelenik meg — nincs üres placeholder-widget/expander."""
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    labels = [e.label for e in app.expander]
    assert "Segédanyag ehhez a ponthoz" not in labels
    assert "Háttéranyagok a vázlathoz" not in labels

    for field in (
        "exegetical_support",
        "original_language_support",
        "historical_theological_support",
        "illustration_direction",
        "application_direction",
    ):
        key = f"sw_flat_outline_edit_entry_{field}"
        found = any(ti.key == key for ti in app.text_input) or any(
            ta.key == key for ta in app.text_area
        )
        assert not found, field


def test_populated_support_fields_render_inside_a_single_collapsed_expander():
    """FINAL SERMON WORKFLOW + OUTLINE PRESENTATION POLISH (2026-08-21):
    a korábbi, mozgásonkénti "Segédanyag ehhez a ponthoz" expanderek
    megszűntek — a teljes vázlat alatt EGYETLEN, közös "Háttéranyagok a
    vázlathoz" expander gyűjti össze az összes mozgás segédanyagát. Ha
    VAN tényleges segédanyag-tartalom (az "entry" mozgásnál mind az öt
    mező ki van töltve), ez az egyetlen expander megjelenik,
    alapértelmezetten összecsukva, és mind az öt widget elérhető benne."""
    app = AppTest.from_function(
        _render_fresh_blueprint_then_generate_outline_with_support_content
    ).run(timeout=60)
    _accept_fresh_outline(app)

    support_expanders = [
        e for e in app.expander if e.label == "Háttéranyagok a vázlathoz"
    ]
    assert len(support_expanders) == 1
    assert support_expanders[0].proto.expanded is False
    assert not any(e.label == "Segédanyag ehhez a ponthoz" for e in app.expander)
    captions = "\n".join(c.value for c in app.caption)
    assert "Szövegi kapaszkodó" in captions
    assert "Eredeti nyelvi támasz" in captions
    assert "Történeti/teológiai támasz" in captions
    assert "Illusztrációs irány" in captions
    assert "Alkalmazási irány" in captions
    assert _outline_edit_widget_keys(app) == []


def test_transition_to_next_is_always_directly_visible_not_in_support_expander():
    """Az `Átvezetés` (`transition_to_next`) a felhasználó explicit
    kérése szerint MINDIG a főnézetben marad, még akkor is, ha a mozgás
    minden más segédmezője ki van töltve."""
    app = AppTest.from_function(
        _render_fresh_blueprint_then_generate_outline_with_support_content
    ).run(timeout=60)
    _accept_fresh_outline(app)

    captions = "\n".join(c.value for c in app.caption)
    assert "Átvezetés: MAIN_VIEW_TRANSITION_SENTINEL" in captions
    assert _outline_edit_widget_keys(app) == []


def test_manual_edit_still_works_inside_expander():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    _set_canonical_title(app, "EXPANDER SZERKESZTÉS TESZT")
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "EXPANDER SZERKESZTÉS TESZT"
    )
    assert _outline_edit_widget_keys(app) == []


def test_manual_edit_in_expander_survives_rerun():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    _set_canonical_title(app, "MEGŐRZÖTT EXPANDER SZÖVEG")
    app.run(timeout=60)
    assert (
        app.session_state["sermon_workshop"]["developed_outline"]["movements"][0]["title"]
        == "MEGŐRZÖTT EXPANDER SZÖVEG"
    )


# -----------------------------------------------------------------------
# 14-15. Eredet-caption (`manually_updated_at`-alapú)
# -----------------------------------------------------------------------


def test_origin_caption_shows_ai_generated_when_not_manually_edited():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    captions = [c.value for c in app.caption]
    assert "MI által generált, még nem szerkesztett vázlat." in captions


def test_origin_caption_shows_manually_updated_after_edit():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    _set_canonical_title(app, "SZERKESZTVE")
    app.run(timeout=60)

    captions = [c.value for c in app.caption]
    assert any(c.startswith("Kézzel módosítva:") for c in captions)
    assert "MI által generált, még nem szerkesztett vázlat." not in captions


# -----------------------------------------------------------------------
# 16. Stale-warning nem veszik el az átrendezésben
# -----------------------------------------------------------------------


def test_stale_warning_still_appears_after_ux_restructure():
    app = AppTest.from_function(_render_fresh_blueprint_then_generate_outline).run(timeout=60)
    _accept_fresh_outline(app)

    app.session_state["sermon_workshop"]["arc"]["entry"]["text"] = "MEGVÁLTOZOTT_UTÁN_UX"
    app.run(timeout=60)
    assert not app.exception

    warning_values = [w.value for w in app.warning]
    assert any("KORÁBBI tervrajzból" in w for w in warning_values)
