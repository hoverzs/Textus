"""Production validation — REAL Local <-> Supabase parity (not the
simulated-payload proof in tests/test_greek_analysis_repository_parity.py).

Hits the live, deployed ``get_greek_verse_syntax_bundle`` RPC against the
production Textus Supabase project via ``SupabaseGreekAnalysisRepository``'s
default client, for all 15 regression verses, and compares every
deterministic field against ``LocalGreekAnalysisRepository`` reading the
same local store the production data was imported from.

Skipped automatically wherever Supabase credentials or the local syntax
store are not available (this is not a CI-portable test — it depends on a
real, already-imported production project)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bible_engine.greek_analysis_repository import (
    LocalGreekAnalysisRepository,
    SupabaseGreekAnalysisRepository,
    attach_syntax_via_repository,
)
from bible_engine.greek_analysis_service import get_greek_analysis, get_greek_analysis_with_syntax
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "greek_analysis_v2_regression_verses.json"


def _fixture_references() -> list[str]:
    with FIXTURES_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return [v["reference"] for v in data["verses"]]


def _supabase_available() -> bool:
    try:
        from supabase_client import get_supabase_client

        get_supabase_client()
        return True
    except Exception:
        return False


requires_local_store = pytest.mark.skipif(
    not resolve_default_syntax_database_path().exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)
requires_supabase = pytest.mark.skipif(not _supabase_available(), reason="no Supabase credentials available")

REGRESSION_REFERENCES = _fixture_references()


@requires_local_store
@requires_supabase
@pytest.mark.parametrize("reference", REGRESSION_REFERENCES)
def test_real_local_and_real_supabase_agree_on_every_field(reference: str) -> None:
    local_bundle = get_greek_analysis_with_syntax(reference)
    supabase_bundle = attach_syntax_via_repository(get_greek_analysis(reference), SupabaseGreekAnalysisRepository())

    assert len(local_bundle.verses) == len(supabase_bundle.verses)

    for local_verse, supabase_verse in zip(local_bundle.verses, supabase_bundle.verses):
        assert local_verse.verse_id == supabase_verse.verse_id

        # token order/ids, lemma, morphology, lexical identity, provenance, alignment
        assert len(local_verse.tokens) == len(supabase_verse.tokens)
        for lt, st in zip(local_verse.tokens, supabase_verse.tokens):
            assert lt.token_id == st.token_id, f"{reference}: token id order mismatch"
            assert lt.lemma == st.lemma
            assert lt.morphology.raw_code == st.morphology.raw_code
            local_lex = lt.lexical_sense.base_meaning_hu if lt.lexical_sense else ""
            supabase_lex = st.lexical_sense.base_meaning_hu if st.lexical_sense else ""
            assert local_lex == supabase_lex, f"{lt.token_id}: lexical base meaning differs"
            local_prov = lt.lexical_sense.review_status if lt.lexical_sense else ""
            supabase_prov = st.lexical_sense.review_status if st.lexical_sense else ""
            assert local_prov == supabase_prov, f"{lt.token_id}: lexical review_status differs"
            assert lt.alignment_status == st.alignment_status, f"{lt.token_id}: alignment_status differs"

        # phrases / clauses / syntax membership (via token_ids sets)
        local_phrase_sets = {frozenset(p.token_ids) for p in local_verse.phrases}
        supabase_phrase_sets = {frozenset(p.token_ids) for p in supabase_verse.phrases}
        assert local_phrase_sets == supabase_phrase_sets, f"{reference}: phrase token sets differ"

        local_clause_sets = {frozenset(c.token_ids) for c in local_verse.clauses}
        supabase_clause_sets = {frozenset(c.token_ids) for c in supabase_verse.clauses}
        assert local_clause_sets == supabase_clause_sets, f"{reference}: clause token sets differ"

        # semantic roles
        local_roles = {(r.role_type, r.predicate_id, r.token_ids) for r in local_verse.semantic_roles}
        supabase_roles = {(r.role_type, r.predicate_id, r.token_ids) for r in supabase_verse.semantic_roles}
        assert local_roles == supabase_roles, f"{reference}: semantic roles differ"

        # coreference
        local_coref = {(c.link_type, c.source_token_id, c.target_token_ids) for c in local_verse.coreference}
        supabase_coref = {(c.link_type, c.source_token_id, c.target_token_ids) for c in supabase_verse.coreference}
        assert local_coref == supabase_coref, f"{reference}: coreference differs"

        # grounding status — the field every other check ultimately gates on
        assert local_verse.syntax_grounding == supabase_verse.syntax_grounding, (
            f"{reference}: grounding status differs (local={local_verse.syntax_grounding}, "
            f"supabase={supabase_verse.syntax_grounding})"
        )


@requires_local_store
@requires_supabase
@pytest.mark.parametrize("reference", REGRESSION_REFERENCES)
def test_real_supabase_detected_constructions_match_local(reference: str) -> None:
    """Detected constructions (§13) run client-side on the attached
    bundle, not stored remotely — this proves they produce identical
    results whichever repository supplied the underlying syntax facts."""
    from bible_engine.greek_construction_detection import detect_patterns

    local_bundle = get_greek_analysis_with_syntax(reference)
    supabase_bundle = attach_syntax_via_repository(get_greek_analysis(reference), SupabaseGreekAnalysisRepository())

    for local_verse, supabase_verse in zip(local_bundle.verses, supabase_bundle.verses):
        local_patterns = {(p.pattern_type, p.token_ids) for p in detect_patterns(local_verse)}
        supabase_patterns = {(p.pattern_type, p.token_ids) for p in detect_patterns(supabase_verse)}
        assert local_patterns == supabase_patterns, f"{reference}: detected constructions differ"
