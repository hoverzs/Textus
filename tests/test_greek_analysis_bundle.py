"""Phase 2A — GreekAnalysisBundle: construction, identity, and corpus-wide
deterministic invariants (§12 of the phase brief)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bible_engine.greek_analysis_bundle import GreekAnalysisBundle
from bible_engine.greek_analysis_service import get_greek_analysis, greek_token_id
from bible_engine.greek_token_repository import DEFAULT_TAGNT_DATABASE_PATH
from bible_engine.morphology_hu import parse_morphology_hu

TAGNT_AVAILABLE = DEFAULT_TAGNT_DATABASE_PATH.exists()
requires_tagnt = pytest.mark.skipif(not TAGNT_AVAILABLE, reason="TAGNT database not built locally")


@requires_tagnt
def test_builds_a_full_bundle_for_john_3_16() -> None:
    bundle = get_greek_analysis("Jn 3,16")

    assert isinstance(bundle, GreekAnalysisBundle)
    assert bundle.book == "JHN"
    assert len(bundle.verses) == 1
    verse = bundle.verses[0]
    assert verse.verse_id == "Jhn.3.16"
    assert len(verse.tokens) == 26
    assert verse.tokens[0].surface  # non-empty Greek text
    assert bundle.coverage.token_count == 26
    assert bundle.coverage.fully_decoded_token_count == 26


@requires_tagnt
def test_token_order_matches_word_index_ascending() -> None:
    bundle = get_greek_analysis("Rom 3,24-25")

    for verse in bundle.verses:
        indexes = [token.word_index for token in verse.tokens]
        assert indexes == sorted(indexes)
        assert indexes == list(range(1, len(indexes) + 1))


@requires_tagnt
def test_token_ids_are_unique_within_and_across_verses() -> None:
    bundle = get_greek_analysis("Mat 28,19-20")

    all_ids = [token.token_id for verse in bundle.verses for token in verse.tokens]
    assert len(all_ids) == len(set(all_ids))


def test_greek_token_id_format() -> None:
    assert greek_token_id("Jhn", 3, 16, 5) == "Jhn.3.16:5"


@requires_tagnt
def test_syntax_fields_are_structurally_present_but_empty_in_phase_2a() -> None:
    """Forward-compatible with a future MACULA Greek phase — never
    synthesized in Phase 2A (audit §7/§8; phase brief §9)."""
    bundle = get_greek_analysis("Jn 3,16")
    verse = bundle.verses[0]

    assert verse.phrases == ()
    assert verse.clauses == ()
    assert verse.syntax_relations == ()
    assert verse.semantic_roles == ()
    assert verse.participants == ()
    assert verse.detected_patterns == ()
    assert bundle.coverage.has_syntax is False


@requires_tagnt
def test_missing_hungarian_gloss_is_not_treated_as_a_morphology_failure() -> None:
    """A token whose Strong id has no Hungarian lexical coverage must still
    report its OWN morphology confidence independently — lexical coverage
    and morphological decoding are unrelated axes (phase brief §12)."""
    bundle = get_greek_analysis("Jn 3,16")
    verse = bundle.verses[0]

    # Every token in this verse morphologically resolves regardless of
    # whether lexical_sense is populated.
    for token in verse.tokens:
        assert token.morphology.confidence == "fully_decoded"
        assert token.morphology.unresolved_parts == ()


@requires_tagnt
def test_no_ai_or_network_dependency_in_deterministic_bundle_build() -> None:
    """The builder module must not import any Gemini/requests/streamlit-
    secrets-network path — a static import check, since actually building
    the bundle above already ran with zero network access available in
    this sandbox and succeeded."""
    import bible_engine.greek_analysis_service as service

    source = Path(service.__file__).read_text(encoding="utf-8")
    assert "import requests" not in source
    assert "import gemini" not in source.lower()
    assert "generate_text(" not in source
    assert "st.secrets" not in source
    assert "import supabase" not in source.lower()
    assert "supabase_client" not in source.lower()


# ---------------------------------------------------------------------------
# Corpus-wide invariants (raw, not through the full bundle builder, to keep
# this fast — see the morphology decode timing note in the phase doc).
# ---------------------------------------------------------------------------

EXPECTED_TOTAL_TOKENS = 142096
EXPECTED_BOOK_COUNT = 27


@requires_tagnt
def test_corpus_wide_142096_tokens_remain_accounted_for() -> None:
    with sqlite3.connect(DEFAULT_TAGNT_DATABASE_PATH) as connection:
        total = connection.execute("SELECT COUNT(*) FROM greek_tokens").fetchone()[0]
        books = connection.execute("SELECT COUNT(DISTINCT book) FROM greek_tokens").fetchone()[0]

    assert total == EXPECTED_TOTAL_TOKENS
    assert books == EXPECTED_BOOK_COUNT


@requires_tagnt
def test_corpus_wide_zero_previously_resolved_morphology_codes_become_unresolved() -> None:
    """Regression anchor for the audit's central positive finding: 0 of
    142,096 tokens have any unresolved morphology component. If a future
    decoder change regresses even one code, this must fail loudly."""
    with sqlite3.connect(DEFAULT_TAGNT_DATABASE_PATH) as connection:
        rows = connection.execute("SELECT morph_code FROM greek_tokens").fetchall()

    assert len(rows) == EXPECTED_TOTAL_TOKENS
    unresolved_count = sum(
        1 for (morph_code,) in rows if not parse_morphology_hu(morph_code or "").is_fully_resolved
    )
    assert unresolved_count == 0


@requires_tagnt
def test_corpus_wide_token_identity_is_unique() -> None:
    with sqlite3.connect(DEFAULT_TAGNT_DATABASE_PATH) as connection:
        rows = connection.execute(
            "SELECT book, chapter, verse, word_index FROM greek_tokens"
        ).fetchall()

    ids = [greek_token_id(book, chapter, verse, word_index) for book, chapter, verse, word_index in rows]
    assert len(ids) == EXPECTED_TOTAL_TOKENS
    assert len(set(ids)) == EXPECTED_TOTAL_TOKENS
