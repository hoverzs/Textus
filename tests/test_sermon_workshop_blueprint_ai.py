"""RESET 2E-2 — a BELSŐ homiletikai blueprint MI-rétegének tesztjei.

A kétlépcsős vázlatmotor első lépcsője: kanonikus input -> blueprint.
Ebben a fázisban nincs UI és nincs developed-outline generálás.

Minden teszt hálózatmentes, mockolt `generate_fn`-nel dolgozik — valódi
API-kulcs vagy Gemini-hívás egyikben sincs.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sermon_workshop_blueprint_ai as bp_ai  # noqa: E402
from sermon_workshop_data import (  # noqa: E402
    _ARC_POINT_KEYS,
    empty_blueprint,
    empty_blueprint_meta,
    ensure_sermon_workshop_state,
    set_arc_candidate,
    set_developed_outline_candidate,
    set_field_refinement_suggestion,
    update_arc_point,
)
from textus_workshop_data import ensure_text_workshop_state  # noqa: E402

PASSAGE = "Mert kegyelemből van üdvösségetek hit által."


# =============================================================================
# Segédek
# =============================================================================


class _CountingGenerator:
    """Hívásszámláló mock `generate_fn` — sosem hív hálózatot."""

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls: list[dict] = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.response


class _SequenceGenerator:
    """Mock `generate_fn`, ami hívásonként MÁS választ ad — a kontrollált
    retry (LOCAL MANUAL QA FIX, 2.5) teszteléséhez: az első hívás
    érvénytelen JSON-t ad, a második (retry) már érvényeset."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, prompt: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


def _base_state() -> dict:
    state: dict = {}
    ensure_sermon_workshop_state(state)
    ensure_text_workshop_state(state)
    state["last_igehely"] = "Ef 2,4-10"
    state["igehely_input"] = "Ef 2,4-10"
    state["passage_text"] = PASSAGE
    state["bible_translation"] = "RÚF 2014"
    return state


def _approved_summary(state: dict, **overrides) -> None:
    summary = {
        "main_idea": "APPROVED_MAIN_IDEA_SENTINEL",
        "base_tension": "APPROVED_TENSION_SENTINEL",
        "key_exegetical_findings": "APPROVED_EXEG_SENTINEL",
        "theological_emphases": "APPROVED_THEO_SENTINEL",
        "genre_structure_notes": "APPROVED_GENRE_SENTINEL",
        "status": "approved",
    }
    summary.update(overrides)
    state["text_workshop"]["text_summary"] = summary


def _raw_blobs(state: dict) -> None:
    state["overview"] = "RAW_OVERVIEW_SENTINEL"
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["history"] = "RAW_HISTORY_SENTINEL"
    state["theology"] = "RAW_THEOLOGY_SENTINEL"
    state["original_text"] = "RAW_ORIGINAL_SENTINEL"


def _movement(key: str, grounded=()) -> dict:
    return {
        "key": key,
        "function": f"{key} funkció",
        "core_idea": f"{key} mag",
        "grounded_in": list(grounded),
    }


def _valid_payload(*, verdict="strong_fit", mode="seven_point", movements=None) -> dict:
    if movements is None:
        movements = [_movement(k) for k in _ARC_POINT_KEYS]
    return {
        "central_claim": "Isten kegyelemből, nem teljesítményből tart meg.",
        "textual_center": "A »De Isten« fordulat a szakasz szíve.",
        "listener_tension": "Muszáj-e kiérdemelnem az elfogadást?",
        "theological_turn": "A kegyelem megelőzi az embert.",
        "desired_listener_movement": "A teljesítménykényszertől a hálás szabadságig.",
        "arc_fit": {"verdict": verdict, "reason": "A szakasz érvelése ezt hordozza."},
        "recommended_structure": {"mode": mode, "movements": movements},
        "key_support": {
            "exegetical": ["A 4. vers fordulata."],
            "original_language": [],
            "historical_theological": [],
        },
        "illustration_direction": "Teljesítménykényszer a hétköznapokban.",
        "application_direction": "Hálából fakadó cselekvés.",
        "warnings": [],
    }


def _valid_json(**kwargs) -> str:
    return json.dumps(_valid_payload(**kwargs), ensure_ascii=False)


def _context(state: dict) -> bp_ai.BlueprintContext:
    return bp_ai.build_blueprint_generation_context(state)


def _prompt(state: dict) -> str:
    return bp_ai.build_blueprint_prompt(_context(state))


# =============================================================================
# A. Approved summary priority
# =============================================================================


def test_a_approved_summary_becomes_the_context_and_excludes_raw_blobs():
    state = _base_state()
    _approved_summary(state)
    _raw_blobs(state)

    context = _context(state)
    assert context.summary_source == "approved_summary"
    assert context.has_approved_summary() is True
    assert dict(context.text_summary)["main_idea"] == "APPROVED_MAIN_IDEA_SENTINEL"
    # A nyers blobok EGYÁLTALÁN nem kerülnek a kontextusba.
    assert context.raw_fallback == ()

    prompt = bp_ai.build_blueprint_prompt(context)
    assert "APPROVED_MAIN_IDEA_SENTINEL" in prompt
    assert "APPROVED_GENRE_SENTINEL" in prompt
    for sentinel in (
        "RAW_OVERVIEW_SENTINEL",
        "RAW_EXEGESIS_SENTINEL",
        "RAW_HISTORY_SENTINEL",
        "RAW_THEOLOGY_SENTINEL",
        "RAW_ORIGINAL_SENTINEL",
    ):
        assert sentinel not in prompt, sentinel


def test_a_approved_summary_prompt_labels_it_as_approved():
    state = _base_state()
    _approved_summary(state)
    prompt = _prompt(state)
    assert "JÓVÁHAGYOTT TEXTUSÖSSZEGZÉS" in prompt
    assert "NYERS, NEM JÓVÁHAGYOTT" not in prompt


def test_a_approved_summary_with_only_some_fields_filled():
    state = _base_state()
    state["text_workshop"]["text_summary"] = {
        "main_idea": "CSAK_EZ_VAN",
        "base_tension": "",
        "key_exegetical_findings": "",
        "theological_emphases": "",
        "genre_structure_notes": "",
        "status": "approved",
    }
    _raw_blobs(state)
    context = _context(state)
    assert context.summary_source == "approved_summary"
    assert dict(context.text_summary) == {"main_idea": "CSAK_EZ_VAN"}
    assert context.raw_fallback == ()


# =============================================================================
# B. Draft / unapproved summary -> kontrollált fallback
# =============================================================================


def test_b_draft_summary_is_not_used_and_fallback_kicks_in():
    state = _base_state()
    _approved_summary(state, status="draft")
    _raw_blobs(state)

    context = _context(state)
    assert context.summary_source == "raw_fallback"
    assert context.text_summary == ()
    assert dict(context.raw_fallback)["exegesis"] == "RAW_EXEGESIS_SENTINEL"

    prompt = bp_ai.build_blueprint_prompt(context)
    # A draft összegzés tartalma SEHOL nem jelenik meg.
    assert "APPROVED_MAIN_IDEA_SENTINEL" not in prompt
    assert "RAW_EXEGESIS_SENTINEL" in prompt
    assert "NYERS, NEM JÓVÁHAGYOTT" in prompt


def test_b_fallback_labels_each_source_and_skips_empty_ones():
    state = _base_state()
    state["overview"] = "RAW_OVERVIEW_SENTINEL"
    state["theology"] = "RAW_THEOLOGY_SENTINEL"
    # `exegesis`, `history`, `original_text` szándékosan üres.

    context = _context(state)
    assert [field for field, _ in context.raw_fallback] == ["overview", "theology"]
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "[`raw.overview`]" in prompt
    assert "[`raw.theology`]" in prompt
    assert "[`raw.exegesis`]" not in prompt


def test_b_exegesis_support_warnings_are_surfaced_only_with_raw_exegesis():
    state = _base_state()
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["exegesis_support_warnings"] = ["Teológiai hangsúly", "Prédikációs irányok"]

    context = _context(state)
    assert context.exegesis_warnings == ("Teológiai hangsúly", "Prédikációs irányok")
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "FIGYELMEZTETÉS" in prompt
    assert "Teológiai hangsúly" in prompt

    # Jóváhagyott összegzésnél nincs nyers exegézis -> a figyelmeztetés sem releváns.
    state2 = _base_state()
    _approved_summary(state2)
    state2["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state2["exegesis_support_warnings"] = ["Teológiai hangsúly"]
    assert _context(state2).exegesis_warnings == ()


def test_b_exegesis_grounding_warnings_are_surfaced_only_with_raw_exegesis():
    """RESET 3D-3, 1-2. teszt: a RESET 3B-6-ban bevezetett `exegesis_
    grounding_warnings` UGYANÚGY becsatolódik, mint a régi `exegesis_
    support_warnings` -- csak akkor, ha a nyers exegézis ténylegesen
    bekerül a kontextusba."""
    state = _base_state()
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["exegesis_grounding_warnings"] = ['"λόγος" — más szakaszból való.']

    context = _context(state)
    assert context.exegesis_warnings == ('"λόγος" — más szakaszból való.',)
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "FIGYELMEZTETÉS" in prompt
    assert '"λόγος" — más szakaszból való.' in prompt

    # Jóváhagyott összegzésnél nincs nyers exegézis -> a grounding-
    # figyelmeztetés sem releváns (6. teszt: approved-summary ág
    # változatlan -- nincs külön párhuzamos csatorna).
    state2 = _base_state()
    _approved_summary(state2)
    state2["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state2["exegesis_grounding_warnings"] = ['"λόγος" — más szakaszból való.']
    context2 = _context(state2)
    assert context2.exegesis_warnings == ()
    prompt2 = bp_ai.build_blueprint_prompt(context2)
    assert '"λόγος" — más szakaszból való.' not in prompt2


def test_b_both_support_and_grounding_warnings_are_combined_in_deterministic_order():
    """RESET 3D-3, 3. teszt: mindkét figyelmeztetés-forrás jelen van ->
    mindkettő bekerül, MINDIG a support előbb, grounding utána."""
    state = _base_state()
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["exegesis_support_warnings"] = ["Teológiai hangsúly", "Prédikációs irányok"]
    state["exegesis_grounding_warnings"] = [
        '"λόγος" — más szakaszból való.',
        '"ξψζθφ" — nem azonosítható.',
    ]

    context = _context(state)
    assert context.exegesis_warnings == (
        "Teológiai hangsúly",
        "Prédikációs irányok",
        '"λόγος" — más szakaszból való.',
        '"ξψζθφ" — nem azonosítható.',
    )
    prompt = bp_ai.build_blueprint_prompt(context)
    # A sorrend a promptban is megőrződik.
    idx_support = prompt.index("Teológiai hangsúly")
    idx_grounding = prompt.index('"λόγος" — más szakaszból való.')
    assert idx_support < idx_grounding


def test_b_stale_exegesis_excludes_both_warning_kinds():
    """RESET 3D-3, 4. teszt: stale exegézis esetén sem a support-, sem a
    grounding-figyelmeztetés nem kerül be -- mert maga az exegézis sem
    kerül be a raw_fallback-be."""
    state = _base_state()
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["exegesis_approved_context_hash"] = "STALE_HASH_MISMATCH"
    state["exegesis_support_warnings"] = ["Teológiai hangsúly"]
    state["exegesis_grounding_warnings"] = ['"λόγος" — más szakaszból való.']

    context = _context(state)
    assert "exegesis" not in dict(context.raw_fallback)
    assert context.exegesis_warnings == ()
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "Teológiai hangsúly" not in prompt
    assert '"λόγος" — más szakaszból való.' not in prompt


def test_b_no_exegesis_at_all_excludes_both_warning_kinds():
    """RESET 3D-3, 5. teszt: ha nincs nyers exegézis-tartalom, a
    warning-kulcsok jelenléte önmagában sem elég."""
    state = _base_state()
    state["exegesis_support_warnings"] = ["Teológiai hangsúly"]
    state["exegesis_grounding_warnings"] = ['"λόγος" — más szakaszból való.']

    context = _context(state)
    assert "exegesis" not in dict(context.raw_fallback)
    assert context.exegesis_warnings == ()


def test_b_warnings_do_not_affect_blueprint_context_hash():
    """RESET 3D-3, 7. teszt: a figyelmeztetések (sem a régi support-, sem
    az új grounding-lista) nem befolyásolják a `context_hash`-t -- ez már
    a RESET 3D-3 előtt sem volt a hash része (`compute_blueprint_context_
    hash` payloadja sosem tartalmazta az `exegesis_warnings`-ot)."""
    state_no_warnings = _base_state()
    state_no_warnings["exegesis"] = "RAW_EXEGESIS_SENTINEL"

    state_with_warnings = _base_state()
    state_with_warnings["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state_with_warnings["exegesis_support_warnings"] = ["Teológiai hangsúly"]
    state_with_warnings["exegesis_grounding_warnings"] = [
        '"λόγος" — más szakaszból való.'
    ]

    hash_without = _context(state_no_warnings).context_hash
    hash_with = _context(state_with_warnings).context_hash
    assert hash_without == hash_with
    assert hash_without  # nem üres -- valódi hash-ek hasonlítva


def test_b_no_material_at_all_is_handled_explicitly():
    state = _base_state()
    context = _context(state)
    assert context.summary_source == "none"
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "Nincs mellékelt Textusműhely-anyag" in prompt


# =============================================================================
# C. Candidate isolation — el nem fogadott javaslat SOHA nem kerül be
# =============================================================================


def test_c_no_unapproved_suggestion_ever_enters_context_or_prompt():
    state = _base_state()
    update_arc_point(state, "entry", "KANONIKUS_ENTRY_SENTINEL")

    # 1. arc_candidate
    set_arc_candidate(
        state,
        points={k: {"text": f"ARC_CANDIDATE_SENTINEL_{k}"} for k in _ARC_POINT_KEYS},
        reference="Ef 2,4-10",
        context_hash="H1",
    )
    # 2. field_refinements
    set_field_refinement_suggestion(
        state,
        "starting_point",
        text="FIELD_REFINEMENT_SENTINEL",
        reference="Ef 2,4-10",
        context_hash="H1",
    )
    # 3. text_summary.suggestions
    state["text_workshop"]["text_summary"] = {
        "main_idea": "",
        "base_tension": "",
        "key_exegetical_findings": "",
        "theological_emphases": "",
        "genre_structure_notes": "",
        "status": "draft",
        "suggestions": {"main_idea": "SUMMARY_SUGGESTION_SENTINEL"},
    }
    # 4. developed_outline_candidate
    set_developed_outline_candidate(
        state,
        outline={"movements": [{"key": "entry", "main_claim": "DEV_CANDIDATE_SENTINEL"}]},
        reference="Ef 2,4-10",
        context_hash="H1",
    )
    # 5. legacy arc.*.ai_suggestion
    state["sermon_workshop"]["arc"]["deepening"]["ai_suggestion"] = (
        "LEGACY_AI_SUGGESTION_SENTINEL"
    )

    prompt = _prompt(state)
    for sentinel in (
        "ARC_CANDIDATE_SENTINEL",
        "FIELD_REFINEMENT_SENTINEL",
        "SUMMARY_SUGGESTION_SENTINEL",
        "DEV_CANDIDATE_SENTINEL",
        "LEGACY_AI_SUGGESTION_SENTINEL",
    ):
        assert sentinel not in prompt, sentinel
    # A kanonikus tartalom viszont bekerül.
    assert "KANONIKUS_ENTRY_SENTINEL" in prompt


# =============================================================================
# D. User arc preservation
# =============================================================================


def test_d_nonempty_arc_points_enter_context_in_canonical_order():
    state = _base_state()
    update_arc_point(state, "arrival", "ARRIVAL_SENTINEL")
    update_arc_point(state, "entry", "ENTRY_SENTINEL")

    context = _context(state)
    assert [key for key, _ in context.arc_points] == ["entry", "arrival"]
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "[`arc.entry`]" in prompt
    assert "ENTRY_SENTINEL" in prompt
    assert "ARRIVAL_SENTINEL" in prompt
    # Az üres pontok nem generálnak zajos, üres bejegyzést.
    assert "[`arc.deepening`]" not in prompt


def test_d_empty_arc_is_stated_explicitly():
    state = _base_state()
    prompt = _prompt(state)
    assert "még egyetlen vázlatpontot sem töltött ki" in prompt


def test_d_prompt_marks_user_content_as_primary_and_not_replaceable():
    state = _base_state()
    update_arc_point(state, "entry", "ENTRY_SENTINEL")
    prompt = _prompt(state)
    assert "NE cseréld le önkényesen" in prompt
    assert "A FELHASZNÁLÓ TARTALMA ELSŐDLEGES" in bp_ai.BLUEPRINT_SYSTEM_PROMPT
    assert "warnings" in bp_ai.BLUEPRINT_SYSTEM_PROMPT


# =============================================================================
# E-F. Context hash determinizmus és relevancia
# =============================================================================


def test_e_identical_input_produces_identical_hash():
    a = _base_state()
    b = _base_state()
    for state in (a, b):
        _approved_summary(state)
        update_arc_point(state, "entry", "ENTRY_SENTINEL")
    assert _context(a).context_hash == _context(b).context_hash
    assert _context(a).context_hash != ""


def test_f_changed_used_input_changes_hash():
    base = _base_state()
    baseline = _context(base).context_hash

    mutations = [
        ("last_igehely", "Jn 3,16"),
        ("passage_text", "Más bibliai szöveg."),
        ("bible_translation", "Károli"),
    ]
    for key, value in mutations:
        state = _base_state()
        state[key] = value
        assert _context(state).context_hash != baseline, key

    # A két főgondolat és egy arc-pont is számít.
    state = _base_state()
    state["text_workshop"]["text_main_idea"] = "Új fő gondolat."
    assert _context(state).context_hash != baseline

    state = _base_state()
    state["sermon_workshop"]["sermon_main_idea"] = "Új fókuszmondat."
    assert _context(state).context_hash != baseline

    state = _base_state()
    update_arc_point(state, "entry", "ENTRY_SENTINEL")
    assert _context(state).context_hash != baseline


def test_f_approved_summary_content_change_changes_hash():
    a = _base_state()
    _approved_summary(a)
    b = _base_state()
    _approved_summary(b, base_tension="MÁS FESZÜLTSÉG")
    assert _context(a).context_hash != _context(b).context_hash


def test_f_used_raw_fallback_change_changes_hash():
    a = _base_state()
    a["exegesis"] = "RAW_A"
    b = _base_state()
    b["exegesis"] = "RAW_B"
    assert _context(a).context_hash != _context(b).context_hash


def test_f_unused_candidate_and_ui_state_do_not_change_hash():
    base = _base_state()
    baseline = _context(base).context_hash

    state = _base_state()
    set_arc_candidate(
        state,
        points={k: {"text": "X"} for k in _ARC_POINT_KEYS},
        reference="Ef 2,4-10",
        context_hash="H1",
    )
    set_field_refinement_suggestion(
        state, "entry", text="Y", reference="Ef 2,4-10", context_hash="H1"
    )
    set_developed_outline_candidate(
        state, outline={"movements": [{"key": "entry"}]}, reference="Ef 2,4-10", context_hash="H1"
    )
    state["_sw_ui_resync"] = True
    state["ui_mode"] = "workshop"
    state["quick_tools_active_tab"] = 3
    assert _context(state).context_hash == baseline


def test_f_raw_blobs_do_not_affect_hash_when_approved_summary_exists():
    """A hash azt követi, amit a modell TÉNYLEGESEN lát — jóváhagyott
    összegzésnél a nyers blobok be sem kerülnek, ezért nem is
    változtathatják meg az identitást."""
    a = _base_state()
    _approved_summary(a)
    b = _base_state()
    _approved_summary(b)
    _raw_blobs(b)
    assert _context(a).context_hash == _context(b).context_hash


# =============================================================================
# G-I. Érvényes válaszok: strong / partial / weak fit
# =============================================================================


def test_g_strong_fit_seven_canonical_movements_is_accepted():
    result = bp_ai.validate_blueprint_response(_valid_json())
    assert result.ok is True
    structure = result.blueprint["recommended_structure"]
    assert structure["mode"] == "seven_point"
    assert [m["key"] for m in structure["movements"]] == list(_ARC_POINT_KEYS)
    assert result.blueprint["arc_fit"]["verdict"] == "strong_fit"


def test_h_partial_fit_merged_movements_are_accepted():
    """RESET 2E-2A: a `merged` mód V1-ben KIZÁRÓLAG 5 vagy 6 mozgást fogad
    el — 2-4 már más szerkezet (`weak_fit`/`custom`), 7 pedig nem is
    összevonás (`strong_fit`/`seven_point`)."""
    for keys in (
        ["entry", "starting_point", "deepening", "second_shift", "arrival"],  # 5
        ["entry", "starting_point", "first_shift", "deepening", "reinterpretation", "arrival"],  # 6
    ):
        payload = _valid_json(
            verdict="partial_fit",
            mode="merged",
            movements=[_movement(k) for k in keys],
        )
        result = bp_ai.validate_blueprint_response(payload)
        assert result.ok is True, keys
        assert [m["key"] for m in result.blueprint["recommended_structure"]["movements"]] == keys


def test_h_merged_movement_count_boundaries():
    """RESET 2E-2A pontos határértékek: 5 és 6 valid; 4 és 7 invalid."""
    all_keys = list(_ARC_POINT_KEYS)

    for count, expect_ok, expect_reason in (
        (4, False, "merged_too_few_movements"),
        (5, True, None),
        (6, True, None),
        (7, False, "merged_not_actually_merged"),
    ):
        keys = all_keys[:count]
        payload = _valid_json(
            verdict="partial_fit", mode="merged", movements=[_movement(k) for k in keys]
        )
        result = bp_ai.validate_blueprint_response(payload)
        assert result.ok is expect_ok, count
        if not expect_ok:
            assert result.reason == expect_reason, count


def test_h_merged_movement_may_ground_in_multiple_arc_points():
    payload = _valid_json(
        verdict="partial_fit",
        mode="merged",
        movements=[
            _movement("entry", grounded=["arc.entry"]),
            _movement("starting_point", grounded=["arc.starting_point"]),
            _movement("first_shift", grounded=["arc.first_shift", "arc.deepening"]),
            _movement("second_shift", grounded=["arc.second_shift"]),
            _movement("arrival", grounded=["arc.arrival"]),
        ],
    )
    result = bp_ai.validate_blueprint_response(payload)
    assert result.ok is True
    merged = result.blueprint["recommended_structure"]["movements"][2]
    assert merged["grounded_in"] == ["arc.first_shift", "arc.deepening"]


def test_i_weak_fit_custom_movements_are_accepted():
    """RESET 2E-2A: a `custom` mód V1-ben KIZÁRÓLAG 3-5 mozgást fogad el."""
    for count in (3, 4, 5):
        keys = [f"custom_{i}" for i in range(1, count + 1)]
        payload = _valid_json(
            verdict="weak_fit", mode="custom", movements=[_movement(k) for k in keys]
        )
        result = bp_ai.validate_blueprint_response(payload)
        assert result.ok is True, count
        assert [
            m["key"] for m in result.blueprint["recommended_structure"]["movements"]
        ] == keys


def test_i_custom_movement_count_boundaries():
    """RESET 2E-2A pontos határértékek: 3-5 valid; 2 és 6 invalid."""
    for count, expect_ok, expect_reason in (
        (2, False, "custom_too_few_movements"),
        (3, True, None),
        (5, True, None),
        (6, False, "custom_too_many_movements"),
    ):
        keys = [f"custom_{i}" for i in range(1, count + 1)]
        payload = _valid_json(
            verdict="weak_fit", mode="custom", movements=[_movement(k) for k in keys]
        )
        result = bp_ai.validate_blueprint_response(payload)
        assert result.ok is expect_ok, count
        if not expect_ok:
            assert result.reason == expect_reason, count


# =============================================================================
# J-M. Elutasítási szabályok
# =============================================================================


def test_j_invalid_arc_fit_verdict_is_rejected():
    for verdict in ("", "kitalált_verdikt", "STRONG_FIT", None):
        payload = _valid_payload()
        payload["arc_fit"]["verdict"] = verdict
        result = bp_ai.validate_blueprint_response(json.dumps(payload, ensure_ascii=False))
        assert result.ok is False
        assert result.reason == "invalid_verdict"

    payload = _valid_payload()
    payload["arc_fit"] = "nem dict"
    result = bp_ai.validate_blueprint_response(json.dumps(payload, ensure_ascii=False))
    assert result.reason == "invalid_arc_fit"


def test_k_verdict_and_mode_must_be_consistent():
    bad_pairs = [
        ("strong_fit", "merged"),
        ("strong_fit", "custom"),
        ("partial_fit", "seven_point"),
        ("partial_fit", "custom"),
        ("weak_fit", "seven_point"),
        ("weak_fit", "merged"),
    ]
    for verdict, mode in bad_pairs:
        payload = _valid_json(verdict=verdict, mode=mode)
        result = bp_ai.validate_blueprint_response(payload)
        assert result.ok is False, (verdict, mode)
        assert result.reason == "verdict_mode_mismatch"

    payload = _valid_payload()
    payload["recommended_structure"]["mode"] = "kitalált_mód"
    result = bp_ai.validate_blueprint_response(json.dumps(payload, ensure_ascii=False))
    assert result.reason == "invalid_mode"


def test_l_seven_point_requires_exact_keys_in_exact_order():
    # Hiányzó pont.
    payload = _valid_json(movements=[_movement(k) for k in _ARC_POINT_KEYS[:6]])
    assert bp_ai.validate_blueprint_response(payload).reason == "seven_point_keys_mismatch"

    # Rossz sorrend.
    shuffled = list(_ARC_POINT_KEYS)
    shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
    payload = _valid_json(movements=[_movement(k) for k in shuffled])
    assert bp_ai.validate_blueprint_response(payload).reason == "seven_point_keys_mismatch"

    # Kitalált kulcs.
    bogus = list(_ARC_POINT_KEYS[:6]) + ["kitalalt_kulcs"]
    payload = _valid_json(movements=[_movement(k) for k in bogus])
    assert bp_ai.validate_blueprint_response(payload).reason == "seven_point_keys_mismatch"


def test_l_merged_and_custom_key_rules_are_enforced():
    # merged: nem kanonikus kulcs.
    payload = _valid_json(
        verdict="partial_fit", mode="merged", movements=[_movement("custom_1"), _movement("entry")]
    )
    assert bp_ai.validate_blueprint_response(payload).reason == "merged_keys_not_canonical"

    # merged: rossz relatív sorrend (5 mozgás, hogy a darabszám-korlátot
    # ne érintse — RESET 2E-2A óta a merged pontosan 5-6 mozgást vár).
    payload = _valid_json(
        verdict="partial_fit",
        mode="merged",
        movements=[
            _movement("starting_point"),
            _movement("entry"),
            _movement("deepening"),
            _movement("second_shift"),
            _movement("arrival"),
        ],
    )
    assert bp_ai.validate_blueprint_response(payload).reason == "merged_keys_out_of_order"

    # merged: mind a hét -> valójában nincs összevonás.
    payload = _valid_json(
        verdict="partial_fit", mode="merged", movements=[_movement(k) for k in _ARC_POINT_KEYS]
    )
    assert bp_ai.validate_blueprint_response(payload).reason == "merged_not_actually_merged"

    # custom: nem folytonos sorszámozás.
    payload = _valid_json(
        verdict="weak_fit",
        mode="custom",
        movements=[_movement("custom_1"), _movement("custom_3")],
    )
    assert bp_ai.validate_blueprint_response(payload).reason == "custom_keys_not_sequential"

    # custom: kanonikus kulcs custom módban.
    payload = _valid_json(
        verdict="weak_fit", mode="custom", movements=[_movement("entry"), _movement("arrival")]
    )
    assert bp_ai.validate_blueprint_response(payload).reason == "custom_keys_not_sequential"


def test_l_movement_list_bounds_are_enforced():
    payload = _valid_json(movements=[])
    assert bp_ai.validate_blueprint_response(payload).reason == "empty_movements"

    too_many = [_movement(f"custom_{i}") for i in range(1, 14)]
    payload = _valid_json(verdict="weak_fit", mode="custom", movements=too_many)
    assert bp_ai.validate_blueprint_response(payload).reason == "too_many_movements"


def test_m_grounded_in_must_use_the_fixed_provenance_vocabulary():
    for bad in (
        "a textus fő gondolatából",  # természetes nyelvű, kitalált
        "arc.turn_1",  # nem létező arc-kulcs
        "arc.entry.text",  # túlspecifikált
        "summary.main_idea",  # rossz prefix
        "raw.illustrations",  # nem engedélyezett forrás
    ):
        payload = _valid_json(
            movements=[
                _movement(k, grounded=[bad] if k == "entry" else [])
                for k in _ARC_POINT_KEYS
            ]
        )
        result = bp_ai.validate_blueprint_response(payload)
        assert result.ok is False, bad
        assert result.reason == "invalid_grounded_in"


def test_m_all_allowed_provenance_tokens_are_accepted():
    payload = _valid_json(
        movements=[
            _movement(k, grounded=sorted(bp_ai.ALLOWED_GROUNDED_IN) if k == "entry" else [])
            for k in _ARC_POINT_KEYS
        ]
    )
    assert bp_ai.validate_blueprint_response(payload).ok is True


def test_j_required_text_fields_must_not_be_empty():
    for field, reason in (
        ("central_claim", "empty_central_claim"),
        ("textual_center", "empty_textual_center"),
        ("desired_listener_movement", "empty_desired_listener_movement"),
    ):
        payload = _valid_payload()
        payload[field] = "   "
        result = bp_ai.validate_blueprint_response(json.dumps(payload, ensure_ascii=False))
        assert result.ok is False
        assert result.reason == reason


def test_j_non_json_responses_are_rejected():
    # LOCAL MANUAL QA FIX: a `reason` mostantól `not_json:<ok>` alakú,
    # részletesebb debug-diagnózissal (ld. `_diagnose_invalid_json_
    # response`) -- minden nem-JSON eset a közös `not_json:` előtaggal
    # kezdődik, a konkrét al-ok külön tesztelt lentebb.
    for raw in (None, "", "   ", "nem json", "[]", "{{{"):
        assert bp_ai.validate_blueprint_response(raw).reason.startswith("not_json:")


def test_validation_accepts_markdown_fenced_json():
    fenced = "```json\n" + _valid_json() + "\n```"
    assert bp_ai.validate_blueprint_response(fenced).ok is True


def test_validation_accepts_a_single_trailing_comma():
    """LOCAL MANUAL QA FIX, 2.3 — a záró vessző (trailing comma) az
    objektum/lista végén biztonságosan levágható, NEM utasítjuk el emiatt
    egy egyébként érvényes választ."""
    payload = _valid_json()
    with_trailing_comma = payload[:-1] + ",}"  # a záró `}` elé vessző
    result = bp_ai.validate_blueprint_response(with_trailing_comma)
    assert result.ok is True


# =============================================================================
# LOCAL MANUAL QA FIX, Phase C — a nem-JSON válasz OKÁNAK részletes,
# fejlesztői célú diagnózisa (`_diagnose_invalid_json_response`).
# =============================================================================


def test_diagnose_empty_or_api_error_response():
    for raw in (None, "", "   ", "⚠️ Hiba történt a generálás közben."):
        assert bp_ai._diagnose_invalid_json_response(raw) == "not_json:empty_or_api_error"


def test_diagnose_no_json_object_found():
    for raw in ("csak sima próza, semmi JSON", "[]", "1234"):
        assert bp_ai._diagnose_invalid_json_response(raw) == "not_json:no_json_object_found"


def test_diagnose_prose_before_json():
    raw = "Íme a válaszom:\n" + _valid_json()
    assert bp_ai._diagnose_invalid_json_response(raw) == "not_json:prose_before_json"


def test_diagnose_prose_after_json():
    raw = _valid_json() + "\nRemélem, ez segít!"
    assert bp_ai._diagnose_invalid_json_response(raw) == "not_json:prose_after_json"


def test_diagnose_truncated_response():
    # A JSON nyílik, de a kimeneti korlát miatt sosem zárul le -- a
    # levágott résznek NINCS egyetlen záró kapcsos zárójele sem, ahogy
    # egy valódi MAX_TOKENS-csonkulásnál is jellemzően egy mező érték
    # közepén szakad meg a válasz.
    cut_off = (
        '{"central_claim": "Isten kegyelemből, nem teljesítményből tart '
        'meg.", "textual_center": "A »De Isten« fordulat a szakasz'
    )
    assert "}" not in cut_off
    assert bp_ai._diagnose_invalid_json_response(cut_off) == "not_json:truncated_response"


def test_diagnose_trailing_comma_unrecoverable_alongside_other_error():
    # Trailing comma MELLETT egy másik, önmagában is végzetes hiba
    # (idézőjel nélküli kulcsnév) -- a kettő együtt már nem javítható a
    # szűk, biztonságos normalizálással.
    raw = '{"central_claim": "x", b: 2,}'
    assert (
        bp_ai._diagnose_invalid_json_response(raw)
        == "not_json:trailing_comma_unrecoverable"
    )


def test_diagnose_unparseable_structurally_broken_json():
    raw = '{"a": 1 "b": 2}'  # hianyzo vesszo a mezok kozott
    assert bp_ai._diagnose_invalid_json_response(raw) == "not_json:unparseable"


def test_diagnose_reason_surfaces_through_full_validation():
    result = bp_ai.validate_blueprint_response("Sajnálom, nem tudok segíteni.")
    assert result.ok is False
    assert result.reason == "not_json:no_json_object_found"


# =============================================================================
# LOCAL MANUAL QA FIX, Phase C — token-plafon és csonkítás-kezelés.
# Élesben reprodukálva: a "Homiletikai blueprint" fül a generikus 4096-os
# alapértékre esett vissza (nem szerepelt `DEFAULT_MAX_OUTPUT_TOKENS_BY_
# TAB`-ban), ami `finishReason=MAX_TOKENS`-hez (csonka JSON) vezetett.
# =============================================================================


def test_blueprint_tab_has_a_dedicated_evidence_based_token_budget():
    """A budget NEM találgatás: 4 valódi Gemini-hívás `usageMetadata`-ja
    (thoughtsTokenCount + candidatesTokenCount) 4038-5120 közé esett egy
    teljes, 7-mozgásos blueprintnél (1Móz 32,23-32 kontextussal) — a
    12000-es érték kb. 2x tartalékot ad a MEGFIGYELT maximum fölé, NEM
    egy vakon nagyra állított plafon."""
    import app

    assert "Igehirdetési tervrajz" in app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB
    budget = app.DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB["Igehirdetési tervrajz"]
    observed_max = 5120
    assert budget >= observed_max * 1.5  # ésszerű tartalék
    assert budget <= observed_max * 3  # NE legyen indokolatlanul túlméretezett
    assert app._default_max_output_tokens("Igehirdetési tervrajz") == budget


def test_retry_recovers_from_a_truncated_first_response():
    state = _base_state()
    gen = _SequenceGenerator(["{\"central_claim\": \"csonka", _valid_json()])

    outcome = bp_ai.generate_sermon_blueprint(state, generate_fn=gen)

    assert outcome.ok is True
    assert len(gen.calls) == 2
    # A retry-prompt röviden jelzi az előző hibát, de NEM generálja újra
    # a teljes upstream kontextust -- ugyanaz az igehely/textus a
    # második prompt alapjában is.
    assert "KORREKCIÓ" in gen.calls[1]["prompt"]
    assert "Ef 2,4-10" in gen.calls[1]["prompt"]


def test_retry_gives_up_after_one_attempt_if_still_invalid():
    state = _base_state()
    gen = _CountingGenerator("{\"central_claim\": \"még mindig csonka")

    outcome = bp_ai.generate_sermon_blueprint(state, generate_fn=gen)

    assert outcome.ok is False
    assert outcome.reason.startswith("not_json:")
    assert len(gen.calls) == 2


def test_only_the_internal_repair_retry_bypasses_cooldown_not_the_first_call():
    """2026-09 audit fix regression test. Root cause: the internal JSON-
    repair retry re-called generate_fn milliseconds after the first call
    with the SAME `bypass_cooldown` value as the caller's outer flag
    (which defaults to False for a standalone blueprint generation) — so
    the repair retry was routinely swallowed by the shared gateway's
    global cooldown window. Required behavior: a standalone (non-chained)
    call's FIRST attempt stays cooldown-protected, and ONLY the internal
    repair attempt (attempt > 0) bypasses cooldown."""
    state = _base_state()
    gen = _SequenceGenerator(["{\"central_claim\": \"csonka", _valid_json()])

    outcome = bp_ai.generate_sermon_blueprint(state, generate_fn=gen)

    assert outcome.ok is True
    assert len(gen.calls) == 2
    assert gen.calls[0]["kwargs"].get("bypass_cooldown") is False
    assert gen.calls[1]["kwargs"].get("bypass_cooldown") is True


def test_standalone_call_with_no_retry_never_bypasses_cooldown():
    state = _base_state()
    gen = _CountingGenerator(_valid_json())

    outcome = bp_ai.generate_sermon_blueprint(state, generate_fn=gen)

    assert outcome.ok is True
    assert len(gen.calls) == 1
    assert gen.calls[0]["kwargs"].get("bypass_cooldown") is False


def test_chained_call_still_bypasses_cooldown_on_first_attempt_unaffected_by_fix():
    """The pre-existing, correct chaining behavior (the caller passes
    bypass_cooldown=True when this blueprint generation is itself part of
    a single click that also triggers a developed-outline generation)
    must be unchanged by this fix — the first attempt still honors the
    caller's explicit bypass_cooldown=True."""
    state = _base_state()
    gen = _CountingGenerator(_valid_json())

    outcome = bp_ai.generate_sermon_blueprint(state, generate_fn=gen, bypass_cooldown=True)

    assert outcome.ok is True
    assert len(gen.calls) == 1
    assert gen.calls[0]["kwargs"].get("bypass_cooldown") is True


def test_semantic_failure_does_not_trigger_a_retry():
    """Tartalmi/sémahiba (pl. üres `textual_center`) esetén NINCS retry —
    ez a modell valódi tartalmi hibája, amit egy néma újrapróbálkozás
    csak elfedne."""
    state = _base_state()
    gen = _CountingGenerator(json.dumps({"central_claim": "x"}))

    outcome = bp_ai.generate_sermon_blueprint(state, generate_fn=gen)

    assert outcome.ok is False
    assert not outcome.reason.startswith("not_json:")
    assert len(gen.calls) == 1


def test_generation_disables_the_appended_truncation_note():
    """A generálás `truncation_notice_mode="never"`-t ad át, hogy egy
    csonka válaszhoz NE fűződjön ember-olvasható magyar figyelmeztető
    mondat -- az garantáltan érvénytelenné tenné a JSON-t a szintaktikai
    csonkaság mellett is, elfedve a valódi (csonkulási) okot."""
    state = _base_state()
    gen = _CountingGenerator(_valid_json())
    bp_ai.generate_sermon_blueprint(state, generate_fn=gen)

    kwargs = gen.calls[0]["kwargs"]
    assert kwargs["truncation_notice_mode"] == "never"


def test_validation_safely_normalizes_without_semantic_repair():
    """Biztonságos tisztítás megengedett (trimmelés, nem-string
    listaelemek kihagyása), szemantikai javítás NEM."""
    payload = _valid_payload()
    payload["central_claim"] = "  Trimmelendő állítás.  "
    payload["warnings"] = ["  valódi  ", "", 42, None]
    payload["key_support"]["exegetical"] = ["  megfigyelés  ", 7]
    result = bp_ai.validate_blueprint_response(json.dumps(payload, ensure_ascii=False))
    assert result.ok is True
    assert result.blueprint["central_claim"] == "Trimmelendő állítás."
    assert result.blueprint["warnings"] == ["valódi"]
    assert result.blueprint["key_support"]["exegetical"] == ["megfigyelés"]


# =============================================================================
# N-O. State write lifecycle
# =============================================================================


def test_o_valid_generation_writes_blueprint_and_meta():
    state = _base_state()
    gen = _CountingGenerator(_valid_json())

    outcome = bp_ai.generate_sermon_blueprint(state, generate_fn=gen)

    assert outcome.ok is True
    assert outcome.status == "generated"
    assert len(gen.calls) == 1

    sw = state["sermon_workshop"]
    assert sw["blueprint"]["central_claim"] == (
        "Isten kegyelemből, nem teljesítményből tart meg."
    )
    assert [
        m["key"] for m in sw["blueprint"]["recommended_structure"]["movements"]
    ] == list(_ARC_POINT_KEYS)
    assert sw["blueprint_meta"]["context_hash"] == _context(state).context_hash
    assert sw["blueprint_meta"]["context_hash"] != ""
    assert sw["blueprint_meta"]["generated_at"] != ""


def test_o_generation_uses_structured_json_schema_and_own_system_prompt():
    state = _base_state()
    gen = _CountingGenerator(_valid_json())
    bp_ai.generate_sermon_blueprint(state, generate_fn=gen)

    kwargs = gen.calls[0]["kwargs"]
    assert kwargs["response_mime_type"] == "application/json"
    assert kwargs["response_schema"] is bp_ai.BLUEPRINT_RESPONSE_SCHEMA
    assert kwargs["system_bundle"] is bp_ai.BLUEPRINT_SYSTEM_PROMPT
    assert kwargs["include_brevity_directive"] is False
    assert kwargs["use_cache"] is False


def test_n_invalid_response_never_overwrites_existing_blueprint():
    state = _base_state()
    bp_ai.generate_sermon_blueprint(state, generate_fn=_CountingGenerator(_valid_json()))
    before_bp = copy.deepcopy(state["sermon_workshop"]["blueprint"])
    before_meta = copy.deepcopy(state["sermon_workshop"]["blueprint_meta"])

    for bad in (
        "nem json",
        json.dumps({"central_claim": "x"}),
        _valid_json(verdict="weak_fit", mode="seven_point"),
        _valid_json(movements=[_movement("kitalalt")]),
    ):
        outcome = bp_ai.generate_sermon_blueprint(
            state, generate_fn=_CountingGenerator(bad)
        )
        assert outcome.ok is False
        assert state["sermon_workshop"]["blueprint"] == before_bp
        assert state["sermon_workshop"]["blueprint_meta"] == before_meta


def test_n_invalid_first_response_leaves_blueprint_at_empty_default():
    state = _base_state()
    outcome = bp_ai.generate_sermon_blueprint(
        state, generate_fn=_CountingGenerator("érvénytelen")
    )
    assert outcome.ok is False
    assert state["sermon_workshop"]["blueprint"] == empty_blueprint()
    assert state["sermon_workshop"]["blueprint_meta"] == empty_blueprint_meta()


def test_n_api_error_and_exception_cause_zero_mutation():
    state = _base_state()
    for response in ("⚠️ Hiba történt a generálás közben.", "⏳ Túl sok kérés."):
        outcome = bp_ai.generate_sermon_blueprint(
            state, generate_fn=_CountingGenerator(response)
        )
        assert outcome.ok is False
        assert outcome.reason == "api_error"
        assert state["sermon_workshop"]["blueprint"] == empty_blueprint()

    def raising(prompt, **kwargs):
        raise RuntimeError("hálózati hiba")

    outcome = bp_ai.generate_sermon_blueprint(state, generate_fn=raising)
    assert outcome.ok is False
    assert outcome.reason == "generate_failed"
    assert state["sermon_workshop"]["blueprint"] == empty_blueprint()


def test_n_missing_context_blocks_generation_with_zero_ai_calls():
    for missing_key in ("last_igehely", "passage_text"):
        state = _base_state()
        state[missing_key] = ""
        if missing_key == "last_igehely":
            state["igehely_input"] = ""
        else:
            state["passage_text_input"] = ""
        gen = _CountingGenerator(_valid_json())
        outcome = bp_ai.generate_sermon_blueprint(state, generate_fn=gen)
        assert outcome.ok is False
        assert outcome.reason == "missing_context"
        assert len(gen.calls) == 0
        assert state["sermon_workshop"]["blueprint"] == empty_blueprint()


def test_blueprint_has_no_candidate_lifecycle():
    """A blueprint belső artefaktum — nincs candidate mezője, és a
    generálás közvetlenül a kanonikus mezőbe ír (validálás után)."""
    state = _base_state()
    bp_ai.generate_sermon_blueprint(state, generate_fn=_CountingGenerator(_valid_json()))
    assert "blueprint_candidate" not in state["sermon_workshop"]


def test_generation_does_not_disturb_arc_or_developed_outline():
    state = _base_state()
    update_arc_point(state, "entry", "ENTRY_SENTINEL")
    before_arc = copy.deepcopy(state["sermon_workshop"]["arc"])
    before_outline = copy.deepcopy(state["sermon_workshop"]["developed_outline"])

    bp_ai.generate_sermon_blueprint(state, generate_fn=_CountingGenerator(_valid_json()))

    assert state["sermon_workshop"]["arc"] == before_arc
    assert state["sermon_workshop"]["developed_outline"] == before_outline
    assert state["sermon_workshop"]["developed_outline_candidate"] is None


# =============================================================================
# P. Eredeti nyelvi visszafogottság
# =============================================================================


def test_p_prompt_forbids_decorative_original_language_use():
    prompt = bp_ai.BLUEPRINT_SYSTEM_PROMPT
    assert "EREDETI NYELVI ADAT" in prompt
    assert "soha ne díszítésként" in prompt
    assert "Strong-szám" in prompt
    assert "hagyd üresen a listát" in prompt


def test_p_no_automatic_original_language_dump_is_required():
    """Az `original_language` lista ÜRESEN is teljesen érvényes — a
    rendszer sehol nem követeli meg a nyers szóalak/Strong dumpot."""
    payload = _valid_payload()
    payload["key_support"]["original_language"] = []
    result = bp_ai.validate_blueprint_response(json.dumps(payload, ensure_ascii=False))
    assert result.ok is True
    assert result.blueprint["key_support"]["original_language"] == []


def test_p_raw_original_text_is_excluded_when_approved_summary_exists():
    """A 2D-F1 eredeti nyelvi zaj fő forrása a nyers `original_text` blob
    volt — jóváhagyott összegzésnél ez be sem kerül a promptba."""
    state = _base_state()
    _approved_summary(state)
    state["original_text"] = "ἀσώτως RAW_ORIGINAL_SENTINEL G4998"
    prompt = _prompt(state)
    assert "RAW_ORIGINAL_SENTINEL" not in prompt
    assert "ἀσώτως" not in prompt


# =============================================================================
# Modul-izoláció
# =============================================================================


def test_blueprint_module_is_independent_of_other_ai_modules():
    """A függetlenséget a TÉNYLEGES import-utasításokból ellenőrizzük
    (AST), nem nyers szövegkereséssel — a modul docstringje ugyanis
    szándékosan MEGNEVEZI azokat a modulokat, amelyekből NEM importál."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(bp_ai))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = {
        "sermon_workshop_arc_ai",
        "sermon_workshop_refinement_ai",
        "textus_summary_ai",
        "sermon_outline_engine",
        "app",
        "streamlit",
    }
    assert not (imported & forbidden), imported & forbidden
    # Az EGYETLEN megengedett belső függés az adatmodell.
    assert "sermon_workshop_data" in imported


def test_blueprint_module_never_calls_generate_text_directly():
    """Az AI-hívó függvényt a hívó adja át (`generate_fn`) — a modul
    sosem importálja vagy hívja közvetlenül az `app.generate_text`-et."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(bp_ai))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "generate_text" not in called_names


def test_blueprint_system_prompt_is_standalone():
    """Saját, önálló rendszerprompt — nem örököl megosztott
    `BASE_SYSTEM_PROMPT`-ot, amely más modulok utasításait áthozhatná."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(bp_ai))
    assigned = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "BLUEPRINT_SYSTEM_PROMPT" in assigned
    # A prompt egyetlen önálló string-literál, nem összefűzés más modul
    # promptjából.
    assert isinstance(bp_ai.BLUEPRINT_SYSTEM_PROMPT, str)
    assert bp_ai.BLUEPRINT_SYSTEM_PROMPT.startswith("SZEREP:")


def test_arc_point_keys_come_from_the_data_model_not_duplicated():
    """A provenance-készlet a KÓDBÁZIS tényleges arc-kulcsaiból épül —
    így sosem hivatkozhat nem létező mezőre."""
    for key in _ARC_POINT_KEYS:
        assert f"arc.{key}" in bp_ai.ALLOWED_GROUNDED_IN
    assert len([t for t in bp_ai.ALLOWED_GROUNDED_IN if t.startswith("arc.")]) == len(
        _ARC_POINT_KEYS
    )


# =============================================================================
# RESET 3B-1 — Textusműhely-forrás frissesség ("szűk igehely-ujjlenyomat")
#
# A `*_approved_context_hash` mezőket a Textusműhely MÁR MOST is
# bélyegzi mentéskor/generáláskor (`textus_workshop_data.py`, `app.py`) —
# ezek a tesztek NEM azt tesztelik, HOGYAN keletkeznek ezek a hash-ek
# (az egy másik modul felelőssége), hanem hogy `build_blueprint_
# generation_context` HELYESEN veti-e össze őket az aktuális igehely/
# textus szűk ujjlenyomatával, és HELYESEN zárja-e ki a stale forrásokat
# — csendes állapot-módosítás nélkül (a session_state-et sosem törli/
# írja át, csak SZŰR).
# =============================================================================


def _fresh_hash(state: dict) -> str:
    """A `state` JELENLEGI igehely/fordítás/textus alapján számított
    szűk ujjlenyomat — pontosan az, amit egy a `_base_state()` felállítás
    idején "most" mentett Textusműhely-forrás kapna."""
    return bp_ai._narrow_passage_identity_hash(
        reference=state["last_igehely"],
        bible_translation=state["bible_translation"],
        passage_text=state["passage_text"],
    )


# -----------------------------------------------------------------------
# 1-3. Approved text_summary frissesség
# -----------------------------------------------------------------------


def test_o1_fresh_approved_summary_is_used():
    state = _base_state()
    _approved_summary(state, approved_context_hash=_fresh_hash(state))
    context = _context(state)
    assert context.summary_source == "approved_summary"
    assert dict(context.text_summary)["main_idea"] == "APPROVED_MAIN_IDEA_SENTINEL"


def test_o2_stale_approved_summary_is_not_used_as_approved_source():
    state = _base_state()
    _approved_summary(state, approved_context_hash="STALE_HASH_MISMATCH")
    context = _context(state)
    assert context.summary_source != "approved_summary"


def test_o3_stale_summary_never_enters_context_or_prompt():
    state = _base_state()
    _approved_summary(state, approved_context_hash="STALE_HASH_MISMATCH")
    context = _context(state)
    assert context.text_summary == ()
    prompt = bp_ai.build_blueprint_prompt(context)
    for sentinel in (
        "APPROVED_MAIN_IDEA_SENTINEL",
        "APPROVED_TENSION_SENTINEL",
        "APPROVED_EXEG_SENTINEL",
        "APPROVED_THEO_SENTINEL",
        "APPROVED_GENRE_SENTINEL",
    ):
        assert sentinel not in prompt, sentinel


# -----------------------------------------------------------------------
# 4-9. Raw fallback mezők frissessége (exegesis / history / original_text)
# -----------------------------------------------------------------------


def test_o4_fresh_raw_exegesis_enters_fallback():
    state = _base_state()
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["exegesis_approved_context_hash"] = _fresh_hash(state)
    context = _context(state)
    assert dict(context.raw_fallback).get("exegesis") == "RAW_EXEGESIS_SENTINEL"


def test_o5_stale_raw_exegesis_is_excluded():
    state = _base_state()
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["exegesis_approved_context_hash"] = "STALE_HASH_MISMATCH"
    context = _context(state)
    assert "exegesis" not in dict(context.raw_fallback)
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "RAW_EXEGESIS_SENTINEL" not in prompt
    # A session_state-ben a tartalom VÁLTOZATLANUL megmarad — csak a
    # kontextusból marad ki.
    assert state["exegesis"] == "RAW_EXEGESIS_SENTINEL"


def test_o6_fresh_raw_history_enters_fallback():
    state = _base_state()
    state["history"] = "RAW_HISTORY_SENTINEL"
    state["history_approved_context_hash"] = _fresh_hash(state)
    context = _context(state)
    assert dict(context.raw_fallback).get("history") == "RAW_HISTORY_SENTINEL"


def test_o7_stale_raw_history_is_excluded():
    state = _base_state()
    state["history"] = "RAW_HISTORY_SENTINEL"
    state["history_approved_context_hash"] = "STALE_HASH_MISMATCH"
    context = _context(state)
    assert "history" not in dict(context.raw_fallback)
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "RAW_HISTORY_SENTINEL" not in prompt


def test_o8_fresh_raw_original_text_enters_fallback():
    state = _base_state()
    state["original_text"] = "RAW_ORIGINAL_SENTINEL"
    state["original_text_approved_context_hash"] = _fresh_hash(state)
    context = _context(state)
    assert dict(context.raw_fallback).get("original_text") == "RAW_ORIGINAL_SENTINEL"


def test_o9_stale_raw_original_text_is_excluded():
    state = _base_state()
    state["original_text"] = "RAW_ORIGINAL_SENTINEL"
    state["original_text_approved_context_hash"] = "STALE_HASH_MISMATCH"
    context = _context(state)
    assert "original_text" not in dict(context.raw_fallback)
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "RAW_ORIGINAL_SENTINEL" not in prompt


# -----------------------------------------------------------------------
# 10-11. Reference / passage_text változás stale-lé teszi a korábbi
#         forrásokat
# -----------------------------------------------------------------------


def test_o10_reference_change_makes_previously_fresh_source_stale():
    state = _base_state()
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["exegesis_approved_context_hash"] = _fresh_hash(state)

    # A mentett hash a RÉGI igehelyhez tartozik -- most megváltozik.
    state["last_igehely"] = "Róm 8,28"
    state["igehely_input"] = "Róm 8,28"

    context = _context(state)
    assert "exegesis" not in dict(context.raw_fallback)


def test_o11_passage_text_change_makes_previously_fresh_source_stale():
    state = _base_state()
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["exegesis_approved_context_hash"] = _fresh_hash(state)

    state["passage_text"] = "Egy teljesen más bibliai szöveg."

    context = _context(state)
    assert "exegesis" not in dict(context.raw_fallback)


# -----------------------------------------------------------------------
# 12-13. Regresszió: hiányzó hash (visszafelé-kompatibilitás) és
#         irreleváns state nem befolyásolja a döntést
# -----------------------------------------------------------------------


def test_o12_missing_freshness_hash_is_treated_as_fresh_for_backward_compatibility():
    """Régi projekt / a mechanizmus bevezetése előtti mentés — nincs
    `approved_context_hash` -- ez NEM minősül stale-nek, a meglévő
    viselkedés (RESET 2E-2) változatlan marad."""
    state = _base_state()
    _approved_summary(state)  # nincs approved_context_hash override
    context = _context(state)
    assert context.summary_source == "approved_summary"

    state2 = _base_state()
    state2["exegesis"] = "RAW_EXEGESIS_SENTINEL"  # nincs *_approved_context_hash
    context2 = _context(state2)
    assert dict(context2.raw_fallback).get("exegesis") == "RAW_EXEGESIS_SENTINEL"


def test_o13_candidate_and_ui_state_do_not_affect_freshness_decision():
    state = _base_state()
    state["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state["exegesis_approved_context_hash"] = _fresh_hash(state)

    set_arc_candidate(
        state,
        points={k: {"text": "X"} for k in _ARC_POINT_KEYS},
        reference="Ef 2,4-10",
        context_hash="H1",
    )
    state["_sw_ui_resync"] = True
    state["ui_mode"] = "workshop"
    state["quick_tools_active_tab"] = 3

    context = _context(state)
    assert dict(context.raw_fallback).get("exegesis") == "RAW_EXEGESIS_SENTINEL"


# =============================================================================
# RESET 3F — `text_main_idea` freshness a blueprint context-builderben,
# UGYANAZZAL a `_is_narrow_context_fresh`/`text_main_idea_approved_
# context_hash` mechanizmussal, mint a raw-fallback mezőknél (ld. fent az
# O-szekció, 4-9. teszt).
# =============================================================================


def test_q1_fresh_text_main_idea_enters_context():
    state = _base_state()
    state["text_workshop"]["text_main_idea"] = "FRESH_MAIN_IDEA_SENTINEL"
    state["text_workshop"]["text_main_idea_approved_context_hash"] = _fresh_hash(state)

    context = _context(state)
    assert context.text_main_idea == "FRESH_MAIN_IDEA_SENTINEL"
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "FRESH_MAIN_IDEA_SENTINEL" in prompt


def test_q2_stale_text_main_idea_is_excluded_from_context():
    state = _base_state()
    state["text_workshop"]["text_main_idea"] = "STALE_MAIN_IDEA_SENTINEL"
    state["text_workshop"]["text_main_idea_approved_context_hash"] = "STALE_HASH_MISMATCH"

    context = _context(state)
    assert context.text_main_idea == ""
    prompt = bp_ai.build_blueprint_prompt(context)
    assert "STALE_MAIN_IDEA_SENTINEL" not in prompt


def test_q3_missing_hash_is_backward_compatible_and_treated_as_fresh():
    state = _base_state()
    state["text_workshop"]["text_main_idea"] = "NO_HASH_MAIN_IDEA_SENTINEL"
    # Nincs `text_main_idea_approved_context_hash` -- régi projekt / a
    # mechanizmus bevezetése előtti mentés. A globális visszafelé-
    # kompatibilis szabály szerint ez NEM minősül stale-nek.
    context = _context(state)
    assert context.text_main_idea == "NO_HASH_MAIN_IDEA_SENTINEL"


def test_q4_stale_text_main_idea_is_preserved_in_session_state():
    state = _base_state()
    state["text_workshop"]["text_main_idea"] = "STALE_MAIN_IDEA_SENTINEL"
    state["text_workshop"]["text_main_idea_approved_context_hash"] = "STALE_HASH_MISMATCH"

    _context(state)
    # A `build_blueprint_generation_context` tisztán OLVASÁSI/szűrési
    # döntés -- a Textusműhely state-et sosem törli vagy írja át.
    assert state["text_workshop"]["text_main_idea"] == "STALE_MAIN_IDEA_SENTINEL"
    assert (
        state["text_workshop"]["text_main_idea_approved_context_hash"]
        == "STALE_HASH_MISMATCH"
    )


def test_q5_passage_change_without_regeneration_makes_text_main_idea_stale():
    state = _base_state()
    state["text_workshop"]["text_main_idea"] = "OLD_PASSAGE_MAIN_IDEA_SENTINEL"
    # A hash a RÉGI igehelyhez készült.
    state["text_workshop"]["text_main_idea_approved_context_hash"] = _fresh_hash(state)

    # Igehely-váltás, újragenerálás nélkül.
    state["last_igehely"] = "Jn 3,16"
    state["igehely_input"] = "Jn 3,16"
    state["passage_text"] = "Mert úgy szerette Isten a világot."

    context = _context(state)
    assert context.text_main_idea == ""


def test_q6_context_hash_reacts_to_text_main_idea_freshness_via_existing_mechanism():
    """A `text_main_idea` MÁR RÉSZE volt a `compute_blueprint_context_
    hash` payloadjának (RESET 2E-2 óta) -- nincs szükség külön hash-
    logikára: a stale-szűrés a MEGLÉVŐ mechanizmuson keresztül
    automatikusan a `context_hash`-re is hat."""
    fresh_state = _base_state()
    fresh_state["text_workshop"]["text_main_idea"] = "MAIN_IDEA_SENTINEL"
    fresh_state["text_workshop"]["text_main_idea_approved_context_hash"] = _fresh_hash(
        fresh_state
    )
    fresh_hash_value = _context(fresh_state).context_hash

    stale_state = _base_state()
    stale_state["text_workshop"]["text_main_idea"] = "MAIN_IDEA_SENTINEL"
    stale_state["text_workshop"][
        "text_main_idea_approved_context_hash"
    ] = "STALE_HASH_MISMATCH"
    stale_hash_value = _context(stale_state).context_hash

    baseline_state = _base_state()  # nincs text_main_idea egyáltalán
    baseline_hash_value = _context(baseline_state).context_hash

    assert fresh_hash_value != baseline_hash_value
    # A stale eset ÚGY viselkedik a hash szempontjából, mintha a mező
    # üres lenne -- megegyezik a baseline (nincs main idea) hash-sel.
    assert stale_hash_value == baseline_hash_value


def test_q7_approved_summary_and_raw_fallback_behavior_is_unchanged():
    """Regresszió: az approved-summary/raw-fallback logika a `text_main_
    idea` freshness-szűrés bevezetése UTÁN is pontosan úgy működik, mint
    előtte -- a `text_main_idea` mindkét ágban FÜGGETLENÜL, saját maga
    szerint szűrődik, nem befolyásolja a `summary_source` döntést."""
    state = _base_state()
    _approved_summary(state)
    state["text_workshop"]["text_main_idea"] = "FRESH_MAIN_IDEA_SENTINEL"
    state["text_workshop"]["text_main_idea_approved_context_hash"] = _fresh_hash(state)

    context = _context(state)
    assert context.summary_source == "approved_summary"
    assert context.text_main_idea == "FRESH_MAIN_IDEA_SENTINEL"

    state2 = _base_state()
    state2["exegesis"] = "RAW_EXEGESIS_SENTINEL"
    state2["exegesis_approved_context_hash"] = _fresh_hash(state2)
    state2["text_workshop"]["text_main_idea"] = "STALE_MAIN_IDEA_SENTINEL"
    state2["text_workshop"]["text_main_idea_approved_context_hash"] = "STALE_HASH_MISMATCH"

    context2 = _context(state2)
    assert context2.summary_source == "raw_fallback"
    assert dict(context2.raw_fallback).get("exegesis") == "RAW_EXEGESIS_SENTINEL"
    assert context2.text_main_idea == ""
