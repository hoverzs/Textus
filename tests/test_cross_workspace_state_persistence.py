"""RESET 2D-H — `text_workshop.text_main_idea` state-persistence javítás.

A RESET 2D-G audit determinisztikus `AppTest`-tel bizonyította, hogy a
kanonikus `text_workshop.text_main_idea` mezőt KÉT, EGYMÁSTÓL FÜGGETLEN
widget-kulcs kezelte:
  - a lapos Igehirdetési műhely UI (`sermon_workshop_ui.py`);
  - a Textusműhely „A textus fő gondolata” gyorseszköz-tab
    (`textus_workshop_ui.render_text_main_idea_section`).

Az `app.py` fejléc-eszköztára (`_render_project_status_bar` ->
`_is_project_dirty` -> `_sync_inputs_to_last`) MINDEN scriptfuttatáson,
MINDKÉT munkaterületen, a `ui_mode`-elágazás ELŐTT lefuttatja mindkét
`flush_*_from_widgets()` függvényt. A régi, soha nem frissülő widget-
kulcsból (`tw_main_idea_input`) a flush feltétel nélkül visszaírt a
kanonikus mezőbe, ezért a frissen beírt érték elveszett — munkaterület-
váltás NÉLKÜL is, már a szerkesztés utáni legelső rerunon.

A javítás — pontosan a `sermon_main_idea`-nál (`_KEY_SERMON_IDEA`) már
bevált „widget-kulcs újrahasznosítás” mintát követve — megszünteti a
két divergens forrást: a `sermon_workshop_ui._KEY_FLAT_TEXT_MAIN_IDEA`
mostantól import-alias, szó szerint UGYANAZ a string, mint a
`textus_workshop_ui._KEY_IDEA_INPUT` — egyetlen aktív widget-state
forrás táplálja mindkét felületet.

Ez a tesztfájl a KÉT ÉRINTETT MODUL (`sermon_workshop_ui.py` és
`textus_workshop_ui.py`) együttes viselkedését teszteli, az `app.py`
valódi hívási sorrendjét (flush a `ui_mode`-elágazás előtt, mindkét
munkaterületen) híven szimulálva — hálózatmentesen, mockolt
`generate_fn`-nel.
"""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sermon_workshop_ui as sw_ui  # noqa: E402
import textus_workshop_ui as tw_ui  # noqa: E402
from sermon_workshop_data import _ARC_POINT_KEYS  # noqa: E402

TEXT_MAIN_IDEA_LABEL = "A textus fő gondolata"
SERMON_MAIN_IDEA_LABEL = "Az igehirdetés fő gondolata – fókuszmondat"


def _render_cross_workspace() -> None:
    """Önálló, `AppTest`-kompatibilis fixture, amely az `app.py` ehhez a
    hibához releváns valódi vezérlési folyamát tükrözi:
      - a fejléc-eszköztár MINDKÉT flush-t lefuttatja, MINDKÉT
        munkaterületen, a `ui_mode`-elágazás ELŐTT (app.py:7141
        `_render_project_status_bar()` mintája);
      - a lapos Igehirdetési műhely shell a `sermon_workshop` ágon;
      - a Textusműhely „A textus fő gondolata” gyorseszköz-tab a
        `workshop` ágon (app.py `st.tabs()`-a minden tab TESTÉT
        lefuttatja, függetlenül attól, melyik van vizuálisan kiválasztva)."""
    import streamlit as st

    import sermon_workshop_ui as sw_ui
    import textus_workshop_ui as tw_ui

    st.session_state["last_igehely"] = "Zsolt 23"
    st.session_state["igehely_input"] = "Zsolt 23"
    st.session_state["passage_text"] = "Az ÚR az én pásztorom, nem szűkölködöm."
    st.session_state["bible_translation"] = "RÚF 2014"

    tw_ui.flush_textus_workshop_from_widgets()
    sw_ui.flush_sermon_workshop_from_widgets()

    ui_mode = st.session_state.get("ui_mode", "sermon_workshop")

    def fake_gen(prompt, **kwargs):
        return "{}"

    if ui_mode == "sermon_workshop":
        sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)
    else:
        tw_ui.render_text_main_idea_section(generate_fn=fake_gen)


def _idx_by_label(app, label: str) -> int:
    return next(i for i, ta in enumerate(app.text_area) if ta.label == label)


def _idx_by_key(app, key: str) -> int:
    return next(i for i, ta in enumerate(app.text_area) if ta.key == key)


# =============================================================================
# Invariáns: EGYETLEN widget-state forrás — nincs két divergens kulcs.
# =============================================================================


def test_widget_key_is_unified_not_divergent():
    """RESET 2D-H fő invariánsa: a lapos UI és a Textusműhely gyorseszköz
    UGYANAZT a widget-kulcsot használja a `text_main_idea`-hoz — nincs
    két külön, egymástól elszakadható forrás."""
    assert sw_ui._KEY_FLAT_TEXT_MAIN_IDEA == tw_ui._KEY_IDEA_INPUT


# =============================================================================
# A. text_main_idea — egyszerű rerun (workspace-váltás NÉLKÜL is elveszett
#    a RESET 2D-G auditban dokumentált hiba szerint).
# =============================================================================


def test_a_text_main_idea_survives_simple_rerun():
    app = AppTest.from_function(_render_cross_workspace).run(timeout=60)
    idx = _idx_by_label(app, TEXT_MAIN_IDEA_LABEL)
    app.text_area[idx].input("A textus arról szól, hogy az Úr gondoskodik.").run()
    assert (
        app.session_state["text_workshop"]["text_main_idea"]
        == "A textus arról szól, hogy az Úr gondoskodik."
    )

    # Egy TOVÁBBI, tiszta rerun (a flush-lánc újra lefut) — workspace-váltás nélkül.
    app.run()
    assert (
        app.session_state["text_workshop"]["text_main_idea"]
        == "A textus arról szól, hogy az Úr gondoskodik."
    )
    idx2 = _idx_by_label(app, TEXT_MAIN_IDEA_LABEL)
    assert app.text_area[idx2].value == "A textus arról szól, hogy az Úr gondoskodik."


# =============================================================================
# B. text_main_idea — teljes workspace oda-vissza váltás.
# =============================================================================


def test_b_text_main_idea_survives_workspace_round_trip():
    app = AppTest.from_function(_render_cross_workspace).run(timeout=60)
    idx = _idx_by_label(app, TEXT_MAIN_IDEA_LABEL)
    app.text_area[idx].input("A textus arról szól, hogy az Úr gondoskodik.").run()

    app.session_state["ui_mode"] = "workshop"
    app.run()
    assert (
        app.session_state["text_workshop"]["text_main_idea"]
        == "A textus arról szól, hogy az Úr gondoskodik."
    )

    app.session_state["ui_mode"] = "sermon_workshop"
    app.run()
    assert (
        app.session_state["text_workshop"]["text_main_idea"]
        == "A textus arról szól, hogy az Úr gondoskodik."
    )
    idx2 = _idx_by_label(app, TEXT_MAIN_IDEA_LABEL)
    assert app.text_area[idx2].value == "A textus arról szól, hogy az Úr gondoskodik."


# =============================================================================
# C. A két UI ugyanazt az adatot látja — mindkét irányból szerkesztve is.
# =============================================================================


def test_c_both_uis_see_the_same_canonical_value():
    app = AppTest.from_function(_render_cross_workspace).run(timeout=60)

    # 1. Módosítás az Igehirdetési műhely (lapos) UI-ban.
    idx_sw = _idx_by_label(app, TEXT_MAIN_IDEA_LABEL)
    app.text_area[idx_sw].input("Első verzió — Igehirdetési műhelyből.").run()

    # 2. A MÁSIK UI (Textusműhely) renderelése.
    app.session_state["ui_mode"] = "workshop"
    app.run()

    # 3. Ugyanaz az érték jelenik meg a Textusműhely widgetjében.
    # UI/UX-audit 2026-11-23 (V15): a Textusműhely mezője látható, pontosabb
    # címkét kapott, ezért itt a kulcsa alapján keressük.
    idx_tw = _idx_by_key(app, "tw_main_idea_input")
    assert app.text_area[idx_tw].value == "Első verzió — Igehirdetési műhelyből."

    # 4. Módosítás a MÁSIK (Textusműhely) UI-ban.
    app.text_area[idx_tw].input("Második verzió — Textusműhelyből.").run()

    # 5. A kanonikus state ÉS az első UI is az új értéket látja.
    assert (
        app.session_state["text_workshop"]["text_main_idea"]
        == "Második verzió — Textusműhelyből."
    )
    app.session_state["ui_mode"] = "sermon_workshop"
    app.run()
    idx_sw2 = _idx_by_label(app, TEXT_MAIN_IDEA_LABEL)
    assert app.text_area[idx_sw2].value == "Második verzió — Textusműhelyből."


# =============================================================================
# D. sermon_main_idea regressziós zár — a már működő fókuszmondat-
#    perzisztencia nem tört el.
# =============================================================================


def test_d_sermon_main_idea_regression_lock():
    app = AppTest.from_function(_render_cross_workspace).run(timeout=60)
    idx = _idx_by_label(app, SERMON_MAIN_IDEA_LABEL)
    app.text_area[idx].input("Az Úr a pásztorunk, aki gondoskodik rólunk.").run()

    app.session_state["ui_mode"] = "workshop"
    app.run()
    app.session_state["ui_mode"] = "sermon_workshop"
    app.run()

    assert (
        app.session_state["sermon_workshop"]["sermon_main_idea"]
        == "Az Úr a pásztorunk, aki gondoskodik rólunk."
    )
    idx2 = _idx_by_label(app, SERMON_MAIN_IDEA_LABEL)
    assert app.text_area[idx2].value == "Az Úr a pásztorunk, aki gondoskodik rólunk."


# =============================================================================
# E. Hét arc-pont regressziós zár — a javítás nem érintette az arc
#    state-kezelését (a flush függvények egyike sem ismeri a
#    `_KEY_FLAT_ARC` kulcsokat).
# =============================================================================


def test_e_arc_points_regression_lock():
    app = AppTest.from_function(_render_cross_workspace).run(timeout=60)
    idx = _idx_by_key(app, sw_ui._KEY_FLAT_ARC["entry"])
    app.text_area[idx].input("Belépés SENTINEL szöveg.").run()

    app.session_state["ui_mode"] = "workshop"
    app.run()
    app.session_state["ui_mode"] = "sermon_workshop"
    app.run()

    assert (
        app.session_state["sermon_workshop"]["arc"]["entry"]["text"]
        == "Belépés SENTINEL szöveg."
    )
    idx2 = _idx_by_key(app, sw_ui._KEY_FLAT_ARC["entry"])
    assert app.text_area[idx2].value == "Belépés SENTINEL szöveg."
    # A többi hat pont érintetlen maradt.
    for point_key in _ARC_POINT_KEYS:
        if point_key == "entry":
            continue
        assert app.session_state["sermon_workshop"]["arc"][point_key]["text"] == ""
