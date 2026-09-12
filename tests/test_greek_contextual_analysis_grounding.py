"""Phase 2C §9/§10/§12/§14/§15/§21 — closed-world morphology, Greek-
specific semantic safety rules, evidence-grounded construction notes, and
grounding-status enforcement for the AI contextual-analysis validator.

Uses the real Jn 3:16 bundle (syntax-attached from the local store when
available) — hand-building a fixture here would risk testing against
invented data; the real deterministic bundle is the actual contract any
future Gemini response must satisfy.
"""

from __future__ import annotations

import pytest

from bible_engine.greek_analysis_bundle import SYNTAX_GROUNDING_NONE
from bible_engine.greek_analysis_service import get_greek_analysis, get_greek_analysis_with_syntax
from bible_engine.greek_contextual_analysis_service import validate_and_build_contextual_analysis
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

requires_syntax_store = pytest.mark.skipif(
    not resolve_default_syntax_database_path().exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)


@requires_syntax_store
def _jn316_verse():
    return get_greek_analysis_with_syntax("Jn 3,16").verses[0]


@requires_syntax_store
def test_grounding_status_always_mirrors_the_bundle_never_the_model() -> None:
    verse = _jn316_verse()
    parsed = {"word_notes": [], "construction_notes": [], "syntax_summary": {}, "warnings": [
        "grounding_status: FULLY_GROUNDED_SYNTAX (a modell hamis önjelentése)"
    ]}
    analysis, _ = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.grounding_status == verse.syntax_grounding
    assert analysis.grounding_status != "FULLY_GROUNDED_SYNTAX" or verse.syntax_grounding == "FULLY_GROUNDED_SYNTAX"


@requires_syntax_store
def test_unresolved_token_never_receives_a_syntax_role() -> None:
    """Jn 3:16 word 11 ("αὐτοῦ") is the known UNRESOLVED_TEXTUAL_VARIANT —
    a model claiming a syntax role for it must be rejected."""
    verse = _jn316_verse()
    parsed = {
        "word_notes": [{"token_id": "Jhn.3.16:11", "syntax_role_hu": "alany"}],
        "construction_notes": [], "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Jhn.3.16:11")
    assert note.syntax_role_hu == ""
    assert any("mondattani állítás eldobva" in w for w in warnings)


@requires_syntax_store
def test_lexical_basic_meaning_is_always_server_supplied_never_from_model() -> None:
    """§11 — the model's response schema has no lexical_basic_meaning_hu
    field at all; even if a raw payload smuggled one in, it must be
    ignored — the server value (from token.lexical_sense) always wins."""
    verse = _jn316_verse()
    token = next(t for t in verse.tokens if t.token_id == "Jhn.3.16:3")
    parsed = {
        "word_notes": [{"token_id": "Jhn.3.16:3", "lexical_basic_meaning_hu": "HALLUCINATED WRONG MEANING"}],
        "construction_notes": [], "syntax_summary": {},
    }
    analysis, _ = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Jhn.3.16:3")
    assert note.lexical_basic_meaning_hu != "HALLUCINATED WRONG MEANING"
    assert note.lexical_basic_meaning_hu == (token.lexical_sense.base_meaning_hu if token.lexical_sense else "")


@requires_syntax_store
def test_lexical_provenance_reflects_review_status() -> None:
    verse = _jn316_verse()
    parsed = {"word_notes": [{"token_id": "Jhn.3.16:3"}], "construction_notes": [], "syntax_summary": {}}
    analysis, _ = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Jhn.3.16:3")
    assert note.lexical_provenance in ("draft", "reviewed", "english_fallback", "")


@requires_syntax_store
@pytest.mark.parametrize(
    "forbidden_phrase",
    ["egyszerű múlt", "egyszeri cselekvés", "pontszerű cselekvés", "folyamatos múlt", "visszaható",
     "befejezett múlt, amelynek eredménye fennáll"],
)
def test_forbidden_overgeneralized_phrase_is_rejected(forbidden_phrase: str) -> None:
    verse = _jn316_verse()
    parsed = {
        "word_notes": [{
            "token_id": "Jhn.3.16:3",
            "morphological_explanation_hu": f"Ez a {forbidden_phrase} egy tesztmondatban.",
        }],
        "construction_notes": [], "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Jhn.3.16:3")
    assert note.morphological_explanation_hu == ""
    assert any("tiltott" in w for w in warnings)


@requires_syntax_store
def test_construction_note_with_valid_evidence_id_is_accepted_and_token_ids_server_computed() -> None:
    verse = _jn316_verse()
    from bible_engine.greek_construction_detection import detect_patterns

    patterns = detect_patterns(verse)
    hina = next((p for p in patterns if p.pattern_type == "hina_clause_marker"), None)
    assert hina is not None
    parsed = {
        "word_notes": [],
        "construction_notes": [{
            "evidence_ids": [hina.pattern_id],
            "construction_type": "hina_clause",
            "title_hu": "ἵνα célhatározói mellékmondat",
            "explanation_hu": "Az ἵνα kötőszó egy célhatározói tagmondatot vezet be.",
        }],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    note = analysis.construction_notes[0]
    assert note.evidence_ids == (hina.pattern_id,)
    assert set(note.token_ids) == set(hina.token_ids)  # server-computed from evidence, not trusted from model


@requires_syntax_store
def test_construction_note_with_invalid_evidence_id_is_rejected() -> None:
    verse = _jn316_verse()
    parsed = {
        "word_notes": [],
        "construction_notes": [{
            "evidence_ids": ["totally_made_up_id_12345"],
            "construction_type": "fake", "title_hu": "x", "explanation_hu": "y",
        }],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.construction_notes == ()
    assert any("nincs érvényes evidence_id" in w for w in warnings)


@requires_syntax_store
def test_no_grounded_syntax_verse_rejects_any_syntax_summary() -> None:
    """A verse with NO_GROUNDED_SYNTAX must receive no syntax_summary at
    all, regardless of what the model returns."""
    from dataclasses import replace

    verse = replace(_jn316_verse(), syntax_grounding=SYNTAX_GROUNDING_NONE, clauses=(), phrases=())
    parsed = {
        "word_notes": [], "construction_notes": [],
        "syntax_summary": {"summary_hu": "Ez egy mondattani összefoglaló, amit nem szabadna elfogadni."},
    }
    analysis, _ = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.syntax_summary.summary_hu == ""


@requires_syntax_store
def test_unknown_token_id_in_word_notes_is_dropped_with_warning() -> None:
    verse = _jn316_verse()
    parsed = {"word_notes": [{"token_id": "Jhn.3.16:999"}], "construction_notes": [], "syntax_summary": {}}
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.word_notes == ()
    assert any("ismeretlen token_id" in w for w in warnings)


@requires_syntax_store
def test_unsupported_morphology_claim_is_rejected() -> None:
    """Task §21 — a standalone, explicitly-named test for the closed-world
    morphology rule (§9/§10): the model may not restate a deterministic
    tense/voice/mood fact using one of the forbidden over-generalized
    Hungarian glosses (e.g. presenting an aorist as "egyszeri cselekvés").
    Distinct from ``test_forbidden_overgeneralized_phrase_is_rejected``
    (which sweeps every forbidden phrase) — this test exists specifically
    to name and prove the "unsupported morphology claim" failure mode by
    itself, per the task's explicit test list."""
    verse = _jn316_verse()
    token = verse.tokens[0]
    parsed = {
        "word_notes": [{
            "token_id": token.token_id,
            "morphological_explanation_hu": "Ez egy aorisztosz alak, ami egyszeri cselekvést fejez ki.",
        }],
        "construction_notes": [], "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == token.token_id)
    assert note.morphological_explanation_hu == ""
    assert any("tiltott" in w for w in warnings)
    # the deterministic morphology fact itself is never touched by this
    # rejection — it lives on the bundle, not on the AI response at all.
    assert token.morphology.raw_code


@requires_syntax_store
def test_unsupported_syntax_claim_is_rejected_for_token_without_syntax_coverage() -> None:
    """Task §21 — a standalone, explicitly-named test for the "no
    deterministic syntax evidence for this token" gate (§15), distinct
    from ``test_unresolved_token_never_receives_a_syntax_role`` (which
    exercises the alignment-status gate instead). Picks a resolved token
    that has no phrase/clause/role/coreference membership and asserts the
    model cannot invent a syntax role for it anyway."""
    from bible_engine.greek_contextual_analysis import token_syntax_coverage

    bundle = get_greek_analysis_with_syntax("Lk 10,25-37")
    verse = next(v for v in bundle.verses if v.verse_id == "Luk.10.34")
    covered = token_syntax_coverage(verse)
    uncovered_resolved = next(
        (t for t in verse.tokens if t.token_id not in covered and t.alignment_status.startswith(
            ("EXACT", "COMPOSITE", "VALIDATED_FALLBACK")
        )),
        None,
    )
    if uncovered_resolved is None:
        pytest.skip("Jn 3:16 has no resolved-but-uncovered token to exercise this gate against")

    parsed = {
        "word_notes": [{"token_id": uncovered_resolved.token_id, "syntax_role_hu": "állítmány"}],
        "construction_notes": [], "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == uncovered_resolved.token_id)
    assert note.syntax_role_hu == ""
    assert any("nincs mondattani adat" in w for w in warnings)

