"""RESET 2C — a hétpontos igehirdetési vázlat candidate-alapú MI-generálása.

Két rétegben tesztel:
  - a `sermon_workshop_arc_ai` modul tiszta motorlogikáját, hálózatmentes,
    mockolt `generate_fn`-nel (nincs valódi API-hívás, nincs API-kulcs);
  - a `sermon_workshop_ui` gomb-/panel-bekötését valódi Streamlit-
    renderelésen keresztül (`streamlit.testing.v1.AppTest`), szintén
    mindig mockolt `generate_fn`-nel.

A RESET 2A-ban elkészült, itt VÁLTOZATLANUL újrafelhasznált adatmodell-
függvények (`store_generated_arc_result`, `accept_arc_candidate`,
`discard_arc_candidate`, `arc_has_content`) saját, kimerítő tesztjei a
`tests/test_arc_data_model.py`-ban vannak — ez a fájl kifejezetten az ÚJ,
RESET 2C-s réteget (kontextus-összeállítás, prompt/séma, validálás,
orchestráció, UI-bekötés) fedi le, a 18 pontos célzott lista szerint.
"""

from __future__ import annotations

import copy
import inspect
import json
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sermon_workshop_arc_ai as arc_ai  # noqa: E402
import sermon_workshop_ui as sw_ui  # noqa: E402
from sermon_workshop_data import (  # noqa: E402
    _ARC_POINT_KEYS,
    accept_arc_candidate,
    discard_arc_candidate,
    ensure_sermon_workshop_state,
    get_default_sermon_workshop,
    update_arc_point,
)
from textus_workshop_data import ensure_text_workshop_state  # noqa: E402
from workspace_data import build_project_data  # noqa: E402

VALID_POINTS: dict[str, str] = {
    "entry": "Belépés szöveg.",
    "starting_point": "Alaphelyzet szöveg.",
    "first_shift": "Első fordulópont szöveg.",
    "deepening": "Mélyítés szöveg.",
    "reinterpretation": "Átértelmezés szöveg.",
    "second_shift": "Második fordulópont szöveg.",
    "arrival": "Megérkezés szöveg.",
}


def _valid_response_json() -> str:
    return json.dumps(VALID_POINTS, ensure_ascii=False)


def _base_state() -> dict:
    state: dict = {}
    ensure_sermon_workshop_state(state)
    ensure_text_workshop_state(state)
    state["last_igehely"] = "Jn 3,16"
    state["igehely_input"] = "Jn 3,16"
    state["passage_text"] = "Mert úgy szerette Isten a világot."
    state["bible_translation"] = "RÚF 2014"
    return state


class _CountingGenerator:
    """Hívásszámláló mock `generate_fn` — sosem hív hálózatot."""

    def __init__(self, response: str = "") -> None:
        self.response = response or _valid_response_json()
        self.calls: list[dict] = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.response


class _SequenceGenerator:
    """Mock `generate_fn`, ami hívásonként MÁS választ ad — a kontrollált
    retry (LOCAL MANUAL QA FIX, 2.5) teszteléséhez."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


# =============================================================================
# 1. A generálási bemenet nem használ legacy outline/basket adatot.
# =============================================================================


def test_context_ignores_legacy_sermon_outline_and_basket_content():
    state = _base_state()
    state["sermon_workshop"]["sermon_outline"]["content"] = "LEGACY_OUTLINE_SENTINEL"
    state["outline_basket"] = ["BASKET_SENTINEL"]

    context = arc_ai.build_arc_generation_context(state)
    assert "sermon_outline" not in {f.name for f in context.__dataclass_fields__.values()}
    prompt = arc_ai.build_arc_generation_prompt(context)
    assert "LEGACY_OUTLINE_SENTINEL" not in prompt
    assert "BASKET_SENTINEL" not in prompt


# =============================================================================
# 2. Hiányzó referencia/szöveg/hash esetén nincs AI-hívás és nincs mutáció.
# =============================================================================


def test_missing_reference_blocks_generation_with_zero_ai_calls_and_zero_mutation():
    state = _base_state()
    state["last_igehely"] = ""
    state["igehely_input"] = ""
    gen = _CountingGenerator()
    before = copy.deepcopy(state["sermon_workshop"]["arc"])

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert outcome.status == "error"
    assert gen.calls == []
    assert state["sermon_workshop"]["arc"] == before
    assert state["sermon_workshop"]["arc_candidate"] is None


def test_missing_passage_text_blocks_generation_with_zero_ai_calls_and_zero_mutation():
    state = _base_state()
    state["passage_text"] = ""
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert gen.calls == []
    assert state["sermon_workshop"]["arc_candidate"] is None


def test_missing_everything_reports_clear_error_with_zero_ai_calls():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert gen.calls == []
    assert outcome.error_message  # rövid, világos hibaüzenet


# =============================================================================
# 3. A generáló prompt/séma kizárólag a hét engedélyezett kulcsot kéri.
# =============================================================================


def test_response_schema_requires_exactly_the_seven_allowed_keys_in_order():
    assert tuple(arc_ai.ARC_RESPONSE_SCHEMA["required"]) == tuple(_ARC_POINT_KEYS)
    assert set(arc_ai.ARC_RESPONSE_SCHEMA["properties"].keys()) == set(_ARC_POINT_KEYS)


def test_generate_fn_invoked_with_structured_json_schema_and_single_call():
    state = _base_state()
    gen = _CountingGenerator()
    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    assert outcome.ok is True
    assert len(gen.calls) == 1
    kwargs = gen.calls[0]["kwargs"]
    assert kwargs["response_mime_type"] == "application/json"
    assert kwargs["response_schema"] is arc_ai.ARC_RESPONSE_SCHEMA


# =============================================================================
# 4. Helyes strukturált eredmény érvényesen normalizálódik.
# =============================================================================


def test_valid_json_response_normalizes_to_exact_seven_points():
    points = arc_ai.validate_and_normalize_arc_response(_valid_response_json())
    assert points == VALID_POINTS


def test_valid_response_wrapped_in_markdown_fence_still_normalizes():
    fenced = "```json\n" + _valid_response_json() + "\n```"
    points = arc_ai.validate_and_normalize_arc_response(fenced)
    assert points == VALID_POINTS


# =============================================================================
# 5. Hibás/hiányos MI-kimenet: nulla kanonikus és candidate mutáció.
# =============================================================================


def test_missing_key_in_response_is_rejected():
    broken = dict(VALID_POINTS)
    del broken["arrival"]
    assert arc_ai.validate_and_normalize_arc_response(json.dumps(broken)) is None


def test_extra_unknown_key_in_response_is_rejected():
    broken = dict(VALID_POINTS)
    broken["extra_unexpected_key"] = "x"
    assert arc_ai.validate_and_normalize_arc_response(json.dumps(broken)) is None


def test_empty_string_value_in_response_is_rejected():
    broken = dict(VALID_POINTS)
    broken["entry"] = "   "
    assert arc_ai.validate_and_normalize_arc_response(json.dumps(broken)) is None


def test_non_string_value_in_response_is_rejected():
    broken = dict(VALID_POINTS)
    broken["entry"] = 123
    assert arc_ai.validate_and_normalize_arc_response(json.dumps(broken)) is None


def test_malformed_json_is_rejected():
    assert arc_ai.validate_and_normalize_arc_response("nem JSON szöveg {{{") is None


def test_invalid_response_causes_zero_mutation_end_to_end():
    # LOCAL MANUAL QA FIX, 2.5: nem-JSON válasz esetén 1 kontrollált
    # retry indul (ld. lentebb a retry-specifikus tesztblokkot) — mivel a
    # mock generátor MINDKÉT hívásra ugyanazt az érvénytelen szöveget
    # adja vissza, a végeredmény változatlanul sikertelen, de a hívás
    # 2-szer történik meg.
    state = _base_state()
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    gen = _CountingGenerator(response="nem JSON szöveg {{{")

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert len(gen.calls) == 2  # 1 eredeti hívás + 1 retry, egyik sem hasznosult
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_candidate"] is None


def test_api_error_string_response_causes_zero_mutation():
    state = _base_state()
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    gen = _CountingGenerator(response="⚠️ Hiba történt a generálás közben.")

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_candidate"] is None


# =============================================================================
# 6-7. Üres arc -> applied (közvetlen írás); nem üres arc -> csak candidate.
# =============================================================================


def test_empty_arc_successful_generation_applies_directly():
    state = _base_state()
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is True
    assert outcome.status == "applied"
    arc = state["sermon_workshop"]["arc"]
    for key, text in VALID_POINTS.items():
        assert arc[key]["text"] == text
    assert state["sermon_workshop"]["arc_candidate"] is None
    assert state["sermon_workshop"]["arc_meta"]["reference"] == "Jn 3,16"
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == ""


def test_non_empty_arc_successful_generation_creates_candidate_only():
    state = _base_state()
    update_arc_point(state, "entry", "Már van kézzel írt tartalom.")
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is True
    assert outcome.status == "candidate"
    assert state["sermon_workshop"]["arc"]["entry"]["text"] == "Már van kézzel írt tartalom."
    candidate = state["sermon_workshop"]["arc_candidate"]
    assert candidate is not None
    assert candidate["points"]["entry"]["text"] == VALID_POINTS["entry"]


# =============================================================================
# 8. A candidate létrehozása a régi hét pontot bit-pontosan érintetlenül
#    hagyja.
# =============================================================================


def test_candidate_creation_leaves_existing_arc_bit_for_bit_unchanged():
    state = _base_state()
    for key in _ARC_POINT_KEYS:
        update_arc_point(state, key, f"Kézi {key} szöveg.")
    before = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])
    gen = _CountingGenerator()

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.status == "candidate"
    assert state["sermon_workshop"]["arc"] == before
    assert state["sermon_workshop"]["arc_meta"] == before_meta


# =============================================================================
# 9-13. Candidate elfogadása/elvetése — a RESET 2A-s tiszta függvényeken
#       keresztül, a RESET 2C-s bemenettel/kontextussal összekötve.
# =============================================================================


def test_accepting_candidate_triggers_zero_ai_calls():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    assert len(gen.calls) == 1

    context = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )

    assert result["accepted"] is True
    assert len(gen.calls) == 1  # elfogadás nem indított új hívást


def test_accept_requires_exact_nonempty_reference_and_context_hash_match():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    # A bibliai szöveg megváltozik a generálás óta -> más context_hash.
    state["passage_text"] = "Egy teljesen más bibliai szöveg."
    context = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )

    assert result["accepted"] is False
    assert result["reason"] == "context_hash_mismatch"


def test_context_mismatch_leaves_candidate_and_canonical_arc_unchanged():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_candidate = copy.deepcopy(state["sermon_workshop"]["arc_candidate"])

    result = accept_arc_candidate(state, reference="Róm 8,28", context_hash="STALE-HASH")

    assert result["accepted"] is False
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_candidate"] == before_candidate


def test_discard_only_clears_candidate_arc_and_meta_untouched():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["arc_meta"])

    discard_arc_candidate(state)

    assert state["sermon_workshop"]["arc_candidate"] is None
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_meta"] == before_meta


def test_manually_updated_at_resets_to_empty_after_accepting_candidate():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom.")
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] != ""

    gen = _CountingGenerator()
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    context = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )

    assert result["accepted"] is True
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] == ""


# =============================================================================
# 14-16. A candidate panel csak valós candidate esetén jelenik meg; applied
#        után nincs panel; candidate esetén readonly előnézet + pontosan
#        két gomb.
# =============================================================================


def _render_no_candidate() -> None:
    import streamlit as st

    import sermon_workshop_ui as sw_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"

    def fake_gen(prompt, **kwargs):
        return "{}"  # sosem hívjuk meg ebben a tesztben

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def test_no_candidate_panel_when_no_candidate_present():
    app = AppTest.from_function(_render_no_candidate).run(timeout=60)
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Új vázlatjavaslat" not in body
    labels = [b.label for b in app.button]
    assert "Javaslat átvétele" not in labels
    assert "Javaslat elvetése" not in labels


def _render_and_generate_twice() -> None:
    import json

    import streamlit as st

    import sermon_workshop_ui as sw_ui

    valid_points = {
        "entry": "Belépés szöveg.",
        "starting_point": "Alaphelyzet szöveg.",
        "first_shift": "Első fordulópont szöveg.",
        "deepening": "Mélyítés szöveg.",
        "reinterpretation": "Átértelmezés szöveg.",
        "second_shift": "Második fordulópont szöveg.",
        "arrival": "Megérkezés szöveg.",
    }

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["igehely_input"] = "Jn 3,16"
    st.session_state["passage_text"] = "Mert úgy szerette Isten a világot."
    st.session_state["bible_translation"] = "RÚF 2014"
    if "_arc_ai_call_count" not in st.session_state:
        # Csak az ELSŐ (script-indító) futáson nullázunk — a script minden
        # rerunon újrafut a tetejétől, egy feltétlen nullázás elveszítené a
        # korábbi futások számlálóját.
        st.session_state["_arc_ai_call_count"] = 0

    def fake_gen(prompt, **kwargs):
        st.session_state["_arc_ai_call_count"] += 1
        return json.dumps(valid_points, ensure_ascii=False)

    sw_ui.render_sermon_workshop_shell(generate_fn=fake_gen)


def test_applied_result_shows_no_candidate_panel():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()  # üres arc -> applied
    assert not app.exception
    body = "\n".join(md.value for md in app.markdown)
    assert "Új vázlatjavaslat" not in body


def test_candidate_shows_readonly_preview_and_exactly_two_action_buttons():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()  # 1. hívás -> applied (üres arc)
    idx2 = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx2].click().run()  # 2. hívás -> candidate (már nem üres arc)
    assert not app.exception

    labels = [b.label for b in app.button]
    assert labels.count("Javaslat átvétele") == 1
    assert labels.count("Javaslat elvetése") == 1
    # 9 kanonikus tartalommező + 9 RESET 2D-B1 pontosítási instrukciós mező —
    # a readonly candidate-előnézet önmagában nem ad hozzá text_area-t.
    assert len(app.text_area) == 18

    body = "\n".join(md.value for md in app.markdown)
    for text in VALID_POINTS.values():
        assert text in body


def test_accepting_candidate_via_ui_does_not_trigger_extra_ai_call():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()
    idx2 = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx2].click().run()
    assert app.session_state["_arc_ai_call_count"] == 2

    accept_idx = next(i for i, b in enumerate(app.button) if b.label == "Javaslat átvétele")
    app.button[accept_idx].click().run()
    assert not app.exception
    assert app.session_state["_arc_ai_call_count"] == 2  # elfogadás nem hívott generálást
    assert app.session_state["sermon_workshop"]["arc_candidate"] is None

    # A gombkezelő `st.rerun()`-t hív — az AppTest a lezajlott mutációt
    # azonnal a session_state-ben tükrözi, de a renderelt fát csak egy
    # további `.run()` rendezi a végleges (candidate nélküli) állapotra.
    app.run()
    labels = [b.label for b in app.button]
    assert "Javaslat átvétele" not in labels
    body = "\n".join(md.value for md in app.markdown)
    assert "Új vázlatjavaslat" not in body


def test_discarding_candidate_via_ui_leaves_arc_untouched_and_removes_panel():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()
    idx2 = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx2].click().run()
    values_before = sorted(ta.value for ta in app.text_area)

    discard_idx = next(i for i, b in enumerate(app.button) if b.label == "Javaslat elvetése")
    app.button[discard_idx].click().run()
    assert not app.exception
    assert app.session_state["sermon_workshop"]["arc_candidate"] is None

    values_after = sorted(ta.value for ta in app.text_area)
    assert values_after == values_before

    # Lásd a fenti megjegyzést: a `st.rerun()`-t hívó gombkezelő után egy
    # további `.run()` szükséges a végleges, candidate nélküli fa
    # ellenőrzéséhez.
    app.run()
    body = "\n".join(md.value for md in app.markdown)
    assert "Új vázlatjavaslat" not in body
    labels = [b.label for b in app.button]
    assert "Javaslat elvetése" not in labels


# =============================================================================
# RESET 2D-F2 — a teljes generálógomb saját, bekeretezett blokkot kap, és a
# pending candidate-panel közvetlenül e blokk ALATT jelenik meg, MÉG a hét
# arc-kártya ELŐTT — nem a kártyák után, elszakítva a kattintástól. Az
# átvétel visszajelzése konkrétabb. Adatmodellt, promptot vagy generálási
# logikát nem érint egyik teszt sem.
# =============================================================================


def _classify_top_level_blocks(app) -> list[tuple[int, str]]:
    """A `render_flat_seven_point_outline_section` top-level blokkjainak
    sorrendjét és fajtáját adja vissza — a `sermon_workshop_arc_ai`
    logikától teljesen független, kizárólag renderelési sorrend teszt."""
    classified: list[tuple[int, str]] = []
    for i in sorted(app.main.children):
        node = app.main.children[i]
        if type(node).__name__ != "Block":
            continue
        labels = {b.label for b in node.button}
        if "MI-javaslat mind a hét ponthoz" in labels:
            classified.append((i, "trigger_button_block"))
        elif "Javaslat átvétele" in labels:
            classified.append((i, "candidate_block"))
        elif len(node.text_area) > 0:
            classified.append((i, "arc_card_block"))
    return classified


def test_trigger_button_has_its_own_bordered_container():
    """RESET 2D-F2, 1. pont: a teljes generálógomb saját, bekeretezett
    blokkot kap — nem hoz létre új generáló gombot vagy második
    útvonalat, csak vizuálisan kiemeli a meglévőt."""
    app = AppTest.from_function(_render_no_candidate).run(timeout=60)
    blocks = _classify_top_level_blocks(app)
    trigger_positions = [i for i, kind in blocks if kind == "trigger_button_block"]
    assert len(trigger_positions) == 1
    trigger_block = app.main.children[trigger_positions[0]]
    assert trigger_block.proto.flex_container.border is True
    # Változatlanul az EGYETLEN "MI-javaslat mind a hét ponthoz" gomb van a lapon.
    assert [b.label for b in app.button].count("MI-javaslat mind a hét ponthoz") == 1


def test_candidate_panel_renders_between_trigger_button_and_arc_cards():
    """RESET 2D-F2, 2. pont: pending candidate esetén a panel a
    generálógomb blokkja UTÁN, de a hét arc-kártya ELŐTT renderelődik."""
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()  # 1. hívás -> applied (üres arc)
    idx2 = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx2].click().run()  # 2. hívás -> candidate (már nem üres arc)
    assert not app.exception

    blocks = _classify_top_level_blocks(app)
    kinds_in_order = [kind for _, kind in blocks]
    trigger_pos = next(i for i, kind in blocks if kind == "trigger_button_block")
    candidate_pos = next(i for i, kind in blocks if kind == "candidate_block")
    card_positions = [i for i, kind in blocks if kind == "arc_card_block"]

    assert len(card_positions) == 7, "mind a hét arc-kártya blokkja megtalálható legyen"
    assert trigger_pos < candidate_pos < min(card_positions), (
        "a candidate-panelnek a gombblokk UTÁN, de az ÖSSZES arc-kártya ELŐTT kell lennie",
        kinds_in_order,
    )


def test_no_candidate_panel_still_renders_only_trigger_and_cards_in_order():
    """Pending candidate NÉLKÜL a top-level blokksorrend csak a gombblokk,
    majd a hét kártya — a candidate-panel hívása üres candidate esetén
    változatlanul nem renderel semmit."""
    app = AppTest.from_function(_render_no_candidate).run(timeout=60)
    blocks = _classify_top_level_blocks(app)
    kinds_in_order = [kind for _, kind in blocks]
    assert kinds_in_order == ["trigger_button_block"] + ["arc_card_block"] * 7


def test_accept_feedback_is_concrete_about_all_seven_fields():
    """RESET 2D-F2, 4. pont: az átvétel visszajelzése konkrétan jelzi,
    hogy mind a hét pont frissült, és hogy alább, a kártyákban kell
    keresni — nem az általános "bekerült a szerkesztőbe" szöveg."""
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()
    idx2 = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx2].click().run()

    accept_idx = next(i for i, b in enumerate(app.button) if b.label == "Javaslat átvétele")
    app.button[accept_idx].click().run()
    assert not app.exception

    toast_values = [t.value for t in app.toast]
    assert toast_values == [
        "A javaslat mind a hét pontba bekerült — ellenőrizd és alakítsd "
        "tovább az alábbi kártyákban."
    ]


def test_accept_still_only_writes_via_accept_arc_candidate_route(monkeypatch):
    """RESET 2D-F2, 3. pont: az átvétel forráskód-szinten is bizonyítottan
    kizárólag a meglévő `accept_arc_candidate()` útvonalon írhat a
    kanonikus `arc`-ba — nincs második, közvetlen írás bevezetve."""
    src = inspect.getsource(sw_ui.render_flat_seven_point_outline_section)
    assert "accept_arc_candidate(" not in src
    src_panel = inspect.getsource(sw_ui._render_arc_candidate_panel)
    assert src_panel.count("accept_arc_candidate(") == 1
    assert "update_arc_point(" not in src_panel


# =============================================================================
# 17. Nincs régi outline-generálás, export vagy section-szintű MI-gomb ezen
#     az útvonalon; az arc_ai modul nem függ a régi motortól/segédektől.
# =============================================================================


def test_arc_ai_module_does_not_import_old_engine_prompt_or_section_helpers():
    src = inspect.getsource(arc_ai)
    for forbidden in (
        "sermon_workshop_outline_ai",
        "sermon_workshop_m4_ai",
        "sermon_workshop_entry_point_ai",
        "sermon_workshop_engagement_ai",
        "import extract_json_object",  # a régi M4 segéd — ez a modul saját, önálló másolatot ír
        "from sermon_workshop_m4_ai",
    ):
        assert forbidden not in src, forbidden
    # Saját, önálló JSON-kinyerő van definiálva, nem importálva a régi modulból.
    assert "def _extract_json_object(" in src
    # Szűk szemantikai korrekció (2026-08-19): a `context_hash` mostantól
    # ennek a modulnak saját, teljes-kontextus hash-függvényéből származik
    # — a korábbi, kizárólag olvasó `sermon_outline_engine` kapcsolat
    # (`compute_current_passage_context_hash`) megszűnt, a modul funkcionális
    # kódja innentől SEMMIT nem importál a régi motorból.
    assert "from sermon_outline_engine import" not in src
    assert "import sermon_outline_engine" not in src
    assert "def compute_arc_generation_context_hash(" in src


def test_generated_route_has_no_legacy_or_export_buttons():
    app = AppTest.from_function(_render_and_generate_twice).run(timeout=60)
    idx = next(
        i for i, b in enumerate(app.button) if b.label == "MI-javaslat mind a hét ponthoz"
    )
    app.button[idx].click().run()
    labels = {b.label for b in app.button}
    for forbidden in (
        "Hétpontos vázlat generálása",
        "Word-export",
        "Vázlat exportálása",
        "Letöltés Word (.docx)",
        "Átveszem",
        "MI-javaslat",
    ):
        assert forbidden not in labels, forbidden


# =============================================================================
# 18. Projektmentési körben az arc, arc_meta és arc_candidate helyesen
#     megmarad (a RESET 2C motor által ténylegesen előállított alakban).
# =============================================================================


def test_project_round_trip_preserves_arc_arc_meta_and_arc_candidate_from_engine():
    state = _base_state()
    update_arc_point(state, "entry", "Kézi tartalom, ami candidate-et vált ki.")
    gen = _CountingGenerator()
    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    assert outcome.status == "candidate"

    project = build_project_data(state)
    reloaded: dict = dict(project)
    ensure_sermon_workshop_state(reloaded)

    assert reloaded["sermon_workshop"]["arc"]["entry"]["text"] == (
        "Kézi tartalom, ami candidate-et vált ki."
    )
    candidate = reloaded["sermon_workshop"]["arc_candidate"]
    assert candidate is not None
    for key, text in VALID_POINTS.items():
        assert candidate["points"][key]["text"] == text
    assert candidate["reference"] == "Jn 3,16"
    assert reloaded["sermon_workshop"]["arc_meta"]["reference"] == ""  # nem íródott felül


# =============================================================================
# SZŰK SZEMANTIKAI KORREKCIÓ (2026-08-19): a candidate `context_hash`-e a
# TELJES, ténylegesen felhasznált generálási bemenet azonosítója legyen,
# ne csak a szűk igehely/szöveg/fordítás hármas. Az alábbi 12 teszt a
# felhasználói korrekciós kérés kötelező listáját fedi le pontról pontra.
# =============================================================================


def _set_text_main_idea(state: dict, value: str) -> None:
    state["text_workshop"]["text_main_idea"] = value


def _set_sermon_main_idea(state: dict, value: str) -> None:
    state["sermon_workshop"]["sermon_main_idea"] = value


# 1. Azonos teljes kontextus -> azonos hash.


def test_identical_full_context_produces_identical_hash():
    state = _base_state()
    ctx1 = arc_ai.build_arc_generation_context(state)
    ctx2 = arc_ai.build_arc_generation_context(state)
    assert ctx1.context_hash == ctx2.context_hash
    assert ctx1.context_hash != ""


# 2-6. Az egyes generálási bemenetek megváltozása eltérő hash-t eredményez.


def test_reference_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["last_igehely"] = "Róm 8,28"
    state["igehely_input"] = "Róm 8,28"
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_passage_text_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["passage_text"] = "Egy teljesen más bibliai szöveg."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_bible_translation_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["bible_translation"] = "KAR"
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_text_main_idea_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    _set_text_main_idea(state, "A textus fő gondolata SENTINEL.")
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_sermon_main_idea_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    _set_sermon_main_idea(state, "Fókuszmondat SENTINEL.")
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


# 7. overview / exegesis / original_text / history / theology egyenként.


def test_overview_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["overview"] = "Bibliai áttekintés SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_exegesis_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["exegesis"] = "Exegézis SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_original_text_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["original_text"] = "Eredeti nyelvi anyag SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_history_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["history"] = "Kortörténet SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


def test_theology_change_alters_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash
    state["theology"] = "Teológia SENTINEL."
    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after != before


# 8. Nem generálási adat (generated_at, candidate tartalma) nem befolyásolja
#    a hash-t.


def test_generated_at_and_candidate_content_do_not_affect_hash():
    state = _base_state()
    before = arc_ai.build_arc_generation_context(state).context_hash

    state["sermon_workshop"]["arc_candidate"] = {
        "points": {"entry": {"text": "Valami candidate tartalom."}},
        "reference": "Más igehely",
        "context_hash": "MASIK-HASH",
        "generated_at": "2000-01-01T00:00:00",
    }
    state["sermon_workshop"]["arc_meta"]["generated_at"] = "2000-01-01T00:00:00"
    state["sermon_workshop"]["arc"]["entry"]["text"] = "Kanonikus arc tartalom."

    after = arc_ai.build_arc_generation_context(state).context_hash
    assert after == before


# 9. Candidate generálása után MINDEN felsorolt kontextusváltozás blokkolja
#    az átvételt, nulla kanonikus mutációval.


def _generate_candidate(state: dict) -> None:
    """Kézi tartalommal tölti fel az arcot, majd egy sikeres generálással
    candidate-et hoz létre — innen tesztelhető minden context-mutáció."""
    update_arc_point(state, "entry", "Már van kézzel írt tartalom.")
    gen = _CountingGenerator()
    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)
    assert outcome.status == "candidate"


def _assert_accept_blocked_with_zero_mutation(
    state: dict, *, expected_reason: str = "context_hash_mismatch"
) -> None:
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_candidate = copy.deepcopy(state["sermon_workshop"]["arc_candidate"])

    context = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )

    assert result["accepted"] is False
    assert result["reason"] == expected_reason
    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["arc_candidate"] == before_candidate


def test_reference_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["last_igehely"] = "Róm 8,28"
    state["igehely_input"] = "Róm 8,28"
    # A referencia-eltérést `accept_arc_candidate` a hash-egyeztetés előtt
    # ellenőrzi (RESET 2A, változatlan sorrend) — a reason itt
    # "reference_mismatch", nem "context_hash_mismatch". A candidate
    # identitásának VÉDELME (nulla mutáció) ettől függetlenül azonos.
    _assert_accept_blocked_with_zero_mutation(state, expected_reason="reference_mismatch")


def test_passage_text_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["passage_text"] = "Egy teljesen más bibliai szöveg."
    _assert_accept_blocked_with_zero_mutation(state)


def test_bible_translation_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["bible_translation"] = "KAR"
    _assert_accept_blocked_with_zero_mutation(state)


def test_text_main_idea_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    _set_text_main_idea(state, "A textus fő gondolata SENTINEL.")
    _assert_accept_blocked_with_zero_mutation(state)


def test_sermon_main_idea_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    _set_sermon_main_idea(state, "Fókuszmondat SENTINEL.")
    _assert_accept_blocked_with_zero_mutation(state)


def test_overview_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["overview"] = "Bibliai áttekintés SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_exegesis_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["exegesis"] = "Exegézis SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_original_text_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["original_text"] = "Eredeti nyelvi anyag SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_history_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["history"] = "Kortörténet SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_theology_change_after_candidate_blocks_acceptance():
    state = _base_state()
    _generate_candidate(state)
    state["theology"] = "Teológia SENTINEL."
    _assert_accept_blocked_with_zero_mutation(state)


def test_accept_after_candidate_blocked_by_mutation_triggers_zero_ai_calls():
    state = _base_state()
    _generate_candidate(state)
    state["overview"] = "Bibliai áttekintés SENTINEL."
    context = arc_ai.build_arc_generation_context(state)
    accept_arc_candidate(state, reference=context.reference, context_hash=context.context_hash)
    # Az elutasított átvétel sem hívhat AI-t — a candidate generálásához
    # használt `gen`-en kívül nincs újabb hívás (itt csak a mutáció-mentes
    # elutasítást ellenőrizzük, AI-hívás nélkül, ami már a fenti helper
    # `accept_arc_candidate` szignatúrájából is következik: nincs
    # `generate_fn` paramétere).
    assert "generate_fn" not in inspect.signature(accept_arc_candidate).parameters


# 10. Az eredeti teljes kontextus visszaállítása után a candidate átvehető.


def test_restoring_original_context_makes_candidate_acceptable_again():
    state = _base_state()
    _generate_candidate(state)

    state["overview"] = "Ideiglenes módosítás."
    context = arc_ai.build_arc_generation_context(state)
    blocked = accept_arc_candidate(
        state, reference=context.reference, context_hash=context.context_hash
    )
    assert blocked["accepted"] is False

    state["overview"] = ""  # vissza az eredeti (üres) állapotra
    context2 = arc_ai.build_arc_generation_context(state)
    result = accept_arc_candidate(
        state, reference=context2.reference, context_hash=context2.context_hash
    )
    assert result["accepted"] is True
    assert state["sermon_workshop"]["arc_candidate"] is None
    for key, text in VALID_POINTS.items():
        assert state["sermon_workshop"]["arc"][key]["text"] == text


# 11. Kézi arc-szerkesztés a lapos UI-n az aktuális teljes context_hash-t
#     írja az `arc_meta` mezőbe.


def test_manual_edit_via_flat_ui_writes_full_context_hash_into_arc_meta(monkeypatch):
    import streamlit as st

    state = _base_state()
    monkeypatch.setattr(st, "session_state", state)

    expected_hash = arc_ai.build_arc_generation_context(state).context_hash
    assert expected_hash != ""

    state[sw_ui._KEY_FLAT_ARC["arrival"]] = "Megérkezés élő szerkesztés."
    sw_ui._flat_save_arc_point("arrival")

    assert state["sermon_workshop"]["arc_meta"]["context_hash"] == expected_hash
    assert state["sermon_workshop"]["arc"]["arrival"]["context_hash"] == expected_hash


def test_manual_edit_via_flat_ui_arc_meta_hash_changes_when_context_changes(monkeypatch):
    import streamlit as st

    state = _base_state()
    monkeypatch.setattr(st, "session_state", state)

    state[sw_ui._KEY_FLAT_ARC["entry"]] = "Belépés első verzió."
    sw_ui._flat_save_arc_point("entry")
    first_hash = state["sermon_workshop"]["arc_meta"]["context_hash"]

    state["passage_text"] = "Megváltozott bibliai szöveg."
    state[sw_ui._KEY_FLAT_ARC["entry"]] = "Belépés második verzió."
    sw_ui._flat_save_arc_point("entry")
    second_hash = state["sermon_workshop"]["arc_meta"]["context_hash"]

    assert second_hash != first_hash


# 12. A régi, nem hétpontos hívók (közvetlen `update_arc_point()` hívás
#     `context_hash` nélkül) visszafelé kompatibilisek maradnak.


def test_update_arc_point_without_context_hash_param_is_fully_backward_compatible():
    state: dict = {}
    ensure_sermon_workshop_state(state)
    assert state["sermon_workshop"]["arc_meta"]["context_hash"] == ""

    point = update_arc_point(state, "deepening", "Régi hívó, nincs context_hash átadva.")

    # A pont saját mezője a régi, szűk (lusta importos) hash-elvet kapja,
    # az `arc_meta.context_hash` pedig — pontosan mint a korrekció előtt —
    # ÉRINTETLEN marad, mert a hívó nem adott át semmit.
    assert point["text"] == "Régi hívó, nincs context_hash átadva."
    assert state["sermon_workshop"]["arc_meta"]["context_hash"] == ""
    assert state["sermon_workshop"]["arc_meta"]["manually_updated_at"] != ""


def test_update_arc_point_signature_gained_only_an_optional_keyword_param():
    sig = inspect.signature(update_arc_point)
    params = sig.parameters
    assert "context_hash" in params
    assert params["context_hash"].default is None
    assert params["context_hash"].kind == inspect.Parameter.KEYWORD_ONLY
    # A pozicionális paraméterek sorrendje/száma változatlan.
    positional = [
        name
        for name, p in params.items()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    assert positional == ["session_state", "point_key", "text"]


# =============================================================================
# RESET 2D-F1 — a hétpontos generáló promptjának TARTALMI szerződése
# (hossz, eredeti nyelvi tiltás, 5–6. pont megkülönböztetése). Ezek a
# tesztek KIZÁRÓLAG a promptszöveget ellenőrzik — nem tudják és nem is
# állítják, hogy egy valódi modellválasz minőségét bizonyítanák; azt csak
# élő, kézi próbával lehet ellenőrizni (ld. a fázis auditját).
# =============================================================================


def test_arc_system_prompt_specifies_per_point_length_guidance():
    prompt = arc_ai.ARC_SYSTEM_PROMPT
    assert "3–4 mondat" in prompt or "3-4 mondat" in prompt
    assert "50–80 szó" in prompt or "50-80 szó" in prompt


def test_arc_system_prompt_allows_longer_deepening_point_only():
    prompt = arc_ai.ARC_SYSTEM_PROMPT
    assert "legfeljebb 5 mondat" in prompt
    # a hosszabb kivétel kifejezetten a "Mélyítés és fokozás" ponthoz kötött
    assert "Mélyítés és fokozás" in prompt


def test_arc_system_prompt_specifies_total_length_target():
    prompt = arc_ai.ARC_SYSTEM_PROMPT
    assert "350–450 szó" in prompt or "350-450 szó" in prompt


def test_arc_system_prompt_forbids_original_language_forms_in_output():
    prompt = arc_ai.ARC_SYSTEM_PROMPT
    assert "TILOS" in prompt
    for keyword in ("görög", "héber", "átírás", "Strong-szám", "nyelvtani szakkifejezés"):
        assert keyword in prompt, keyword


def test_arc_system_prompt_distinguishes_reinterpretation_from_second_shift():
    prompt = arc_ai.ARC_SYSTEM_PROMPT
    assert "NE ismételd meg az 5. pont" in prompt
    # az 5. pont a felismerés csúcsa, a 6. annak következménye — a két
    # szerep szövegesen is külön kulcsszóval jelenjen meg a promptban
    assert "KÖVETKEZMÉNYE" in prompt
    assert "FELISMERÉS maga" in prompt


def test_arc_system_prompt_forbids_retelling_and_spoiling_later_points():
    prompt = arc_ai.ARC_SYSTEM_PROMPT
    assert "se mesélje újra a teljes textust" in prompt
    assert "se árulja el előre egy KÉSŐBBI pont felismerését" in prompt


def test_arc_response_schema_and_point_keys_unchanged_by_prompt_edit():
    """RESET 2D-F1 kizárólag promptszöveget módosít — a séma és a
    kanonikus kulcssorrend bit-pontosan változatlan marad."""
    assert arc_ai.ARC_RESPONSE_SCHEMA == {
        "type": "object",
        "properties": {key: {"type": "string"} for key in _ARC_POINT_KEYS},
        "required": list(_ARC_POINT_KEYS),
    }
    assert tuple(_ARC_POINT_KEYS) == (
        "entry",
        "starting_point",
        "first_shift",
        "deepening",
        "reinterpretation",
        "second_shift",
        "arrival",
    )


# =============================================================================
# LOCAL MANUAL QA FIX, Phase B — JSON-kinyerés robusztussága, diagnózis,
# token-plafon és kontrollált retry. Ugyanaz a minta, mint a
# `sermon_workshop_blueprint_ai.py`-nál (Phase C).
# =============================================================================


def test_extraction_accepts_a_single_trailing_comma():
    payload = _valid_response_json()
    with_trailing_comma = payload[:-1] + ",}"
    assert arc_ai._extract_json_object(with_trailing_comma) is not None
    assert arc_ai.validate_and_normalize_arc_response(with_trailing_comma) is not None


def test_diagnose_empty_or_api_error_response():
    for raw in (None, "", "   ", "⚠️ Hiba történt a generálás közben."):
        assert (
            arc_ai._diagnose_invalid_json_response(raw)
            == "not_json:empty_or_api_error"
        )


def test_diagnose_no_json_object_found():
    for raw in ("csak sima próza, semmi JSON", "[]", "1234"):
        assert (
            arc_ai._diagnose_invalid_json_response(raw)
            == "not_json:no_json_object_found"
        )


def test_diagnose_prose_before_and_after_json():
    before = "Íme a válaszom:\n" + _valid_response_json()
    assert arc_ai._diagnose_invalid_json_response(before) == "not_json:prose_before_json"

    after = _valid_response_json() + "\nRemélem, ez segít!"
    assert arc_ai._diagnose_invalid_json_response(after) == "not_json:prose_after_json"


def test_diagnose_truncated_response():
    cut_off = '{"entry": "Természetes belépés a textus'
    assert "}" not in cut_off
    assert (
        arc_ai._diagnose_invalid_json_response(cut_off) == "not_json:truncated_response"
    )


def test_arc_tab_has_a_dedicated_evidence_based_token_budget():
    """A budget NEM találgatás: 2 valódi Gemini-hívás `usageMetadata`-ja
    (thoughtsTokenCount + candidatesTokenCount) 4803-5486 közé esett — a
    10000-es érték ésszerű tartalékot ad a MEGFIGYELT maximum fölé, NEM
    egy vakon nagyra állított plafon."""
    import app

    assert "Hétpontos vázlatjavaslat" in app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB
    budget = app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB["Hétpontos vázlatjavaslat"]
    observed_max = 5486
    assert budget >= observed_max * 1.5
    assert budget <= observed_max * 3


def test_generation_disables_the_appended_truncation_note():
    state = _base_state()
    gen = _CountingGenerator(_valid_response_json())
    arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    kwargs = gen.calls[0]["kwargs"]
    assert kwargs["truncation_notice_mode"] == "never"


def test_retry_recovers_from_a_truncated_first_response():
    state = _base_state()
    gen = _SequenceGenerator(
        ['{"entry": "csonka', _valid_response_json()]
    )

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is True
    assert len(gen.calls) == 2
    assert "KORREKCIÓ" in gen.calls[1]["prompt"]


def test_only_the_internal_repair_retry_bypasses_cooldown_not_the_first_call():
    """2026-09 audit fix regression test. Root cause: the internal JSON-
    repair retry re-called generate_fn milliseconds after the first call,
    with no bypass_cooldown at all — so it was routinely swallowed by the
    shared gateway's global cooldown window, making the designed recovery
    from a truncated/malformed first response effectively non-functional.

    Required behavior: the FIRST, user-initiated call stays cooldown-
    protected (bypass_cooldown must be False/absent), and ONLY the
    second, same-click internal repair call passes bypass_cooldown=True."""
    state = _base_state()
    gen = _SequenceGenerator(
        ['{"entry": "csonka', _valid_response_json()]
    )

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is True
    assert len(gen.calls) == 2
    assert gen.calls[0]["kwargs"].get("bypass_cooldown") is False
    assert gen.calls[1]["kwargs"].get("bypass_cooldown") is True


def test_standalone_call_with_no_retry_never_bypasses_cooldown():
    """A normal, single-shot user-initiated call (no repair needed) must
    never bypass the cooldown — only the internal retry path may."""
    state = _base_state()
    gen = _CountingGenerator(_valid_response_json())

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is True
    assert len(gen.calls) == 1
    assert gen.calls[0]["kwargs"].get("bypass_cooldown") is False


def test_retry_gives_up_after_one_attempt_if_still_invalid():
    state = _base_state()
    gen = _CountingGenerator("{\"entry\": \"még mindig csonka")

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert outcome.reason.startswith("not_json:")
    assert len(gen.calls) == 2


def test_semantic_shape_failure_does_not_trigger_a_retry():
    """A JSON szintaktikailag rendben van, de a séma hibás (hiányzó
    kulcs) -- ez a modell TARTALMI hibája, NEM ismételjük."""
    state = _base_state()
    bad_shape = json.dumps({"entry": "csak egy pont"}, ensure_ascii=False)
    gen = _CountingGenerator(bad_shape)

    outcome = arc_ai.generate_seven_point_arc(state, generate_fn=gen)

    assert outcome.ok is False
    assert outcome.reason == "invalid_shape"
    assert len(gen.calls) == 1
