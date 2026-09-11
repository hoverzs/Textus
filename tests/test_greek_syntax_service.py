"""Phase 2B §6/§10/§12 — syntax attachment, construction detection over
the 15 regression verses, and basic performance sanity checks."""

from __future__ import annotations

import time

import pytest

from bible_engine.greek_analysis_bundle import SYNTAX_GROUNDING_NONE
from bible_engine.greek_analysis_service import get_greek_analysis, get_greek_analysis_with_syntax
from bible_engine.greek_construction_detection import detect_patterns
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

requires_syntax_store = pytest.mark.skipif(
    not resolve_default_syntax_database_path().exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)

REGRESSION_REFERENCES = [
    "Jn 3,16", "Jn 1,1", "Jn 1,14", "Jn 19,30", "Mt 28,19-20", "Mt 9,18",
    "Fil 1,21", "1Kor 15,13-14", "Róm 5,1", "1Tim 3,1", "Mk 1,9-11",
    "Róm 5,12", "2Pt 1,1", "Róm 3,24-25", "Lk 10,25-37",
]


@requires_syntax_store
def test_attach_syntax_never_changes_phase_2a_token_morphology_fields() -> None:
    bare = get_greek_analysis("Jn 3,16")
    enriched = get_greek_analysis_with_syntax("Jn 3,16")

    bare_tokens = bare.verses[0].tokens
    enriched_tokens = enriched.verses[0].tokens
    assert len(bare_tokens) == len(enriched_tokens)
    for b, e in zip(bare_tokens, enriched_tokens):
        assert b.token_id == e.token_id
        assert b.surface == e.surface
        assert b.lemma == e.lemma
        assert b.strong_id == e.strong_id
        assert b.morphology == e.morphology
        assert b.lexical_sense == e.lexical_sense


def test_missing_syntax_store_degrades_to_phase_2a_bundle_unchanged() -> None:
    bundle = get_greek_analysis_with_syntax("Jn 3,16", syntax_database_path="/nonexistent/path.sqlite3")
    for verse in bundle.verses:
        assert verse.syntax_grounding == SYNTAX_GROUNDING_NONE
        assert verse.phrases == ()
        assert verse.clauses == ()


@requires_syntax_store
def test_syntax_never_attaches_to_an_unresolved_token() -> None:
    """No relation may be attached through coincidental id equality, and
    unresolved alignments must never silently receive syntax facts — the
    end-to-end version of the corpus-wide store invariant."""
    bundle = get_greek_analysis_with_syntax("Jn 3,16")
    verse = bundle.verses[0]
    aligned_token_ids = {
        tid for c in verse.clauses for tid in c.token_ids
    } | {
        tid for p in verse.phrases for tid in p.token_ids
    }
    # Jn 3:16 word 11 ("αὐτοῦ") is the known K/O-only textual variant with
    # no MACULA counterpart — it must never appear as a syntax participant.
    assert "Jhn.3.16:11" not in aligned_token_ids


@requires_syntax_store
@pytest.mark.parametrize("reference", REGRESSION_REFERENCES)
def test_all_15_regression_verses_build_without_error(reference: str) -> None:
    bundle = get_greek_analysis_with_syntax(reference)
    assert bundle.verses
    for verse in bundle.verses:
        assert verse.tokens
        patterns = detect_patterns(verse)
        # detect_patterns must never raise and must return a tuple.
        assert isinstance(patterns, tuple)


@requires_syntax_store
def test_genitive_absolute_detected_in_its_regression_verse() -> None:
    bundle = get_greek_analysis_with_syntax("Mt 9,18")
    verse = bundle.verses[0]
    patterns = detect_patterns(verse)
    assert any(p.pattern_type == "genitive_absolute_candidate" for p in patterns)


@requires_syntax_store
def test_hina_clause_detected_in_its_regression_verse() -> None:
    bundle = get_greek_analysis_with_syntax("Jn 3,16")
    verse = bundle.verses[0]
    patterns = detect_patterns(verse)
    assert any(p.pattern_type == "hina_clause_marker" for p in patterns)


@requires_syntax_store
def test_hoti_clause_detected_in_its_regression_verse() -> None:
    bundle = get_greek_analysis_with_syntax("Mt 9,18")
    verse = bundle.verses[0]
    patterns = detect_patterns(verse)
    assert any(p.pattern_type == "hoti_clause_marker" for p in patterns)


@requires_syntax_store
def test_conditional_marker_detected_in_its_regression_verse() -> None:
    bundle = get_greek_analysis_with_syntax("1Kor 15,13-14")
    for verse in bundle.verses:
        patterns = detect_patterns(verse)
        if any(p.pattern_type == "conditional_clause_marker" for p in patterns):
            return
    pytest.fail("no conditional_clause_marker found across 1Cor 15:13-14")


# ---------------------------------------------------------------------------
# §11 — performance sanity (not a strict benchmark; catches obviously
# pathological N+1 access patterns before a future Supabase backend design).
# ---------------------------------------------------------------------------


@requires_syntax_store
def test_single_verse_performance_is_well_under_one_second() -> None:
    t0 = time.perf_counter()
    get_greek_analysis_with_syntax("Jn 3,16")
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"single verse took {elapsed:.3f}s"


@requires_syntax_store
def test_ten_verse_performance_scales_roughly_linearly() -> None:
    t0 = time.perf_counter()
    for reference in REGRESSION_REFERENCES[:10]:
        get_greek_analysis_with_syntax(reference)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"10 verses took {elapsed:.3f}s"


@requires_syntax_store
def test_one_chapter_performance() -> None:
    t0 = time.perf_counter()
    get_greek_analysis_with_syntax("Jn 3,1-36")
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"one chapter took {elapsed:.3f}s"
