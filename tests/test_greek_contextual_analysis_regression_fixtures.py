"""Phase 2C §18 — confirms the 15 existing Phase 2A developer regression
fixtures (``tests/fixtures/greek_analysis_v2_regression_verses.json``,
``reviewed: false`` — regression aids, NOT expert linguistic goldens) still
work correctly when run through the full Phase 2C contract: syntax
attachment + construction detection + the contextual-analysis validator,
not just the Phase 2A deterministic bundle those fixtures were originally
captured against.

This does not re-capture or compare against the fixture file's stored
Phase 2A-only bundle (that is what tests/test_greek_analysis_bundle.py's
own reproducibility check already does) — it uses the fixture file only as
the canonical list of 15 references, then builds each one fresh through
``get_greek_analysis_with_syntax`` (Phase 2B/2C) and pushes an empty model
response through the real validator, proving every one of the 15 survives
the full pipeline without error and produces a well-formed
``GreekContextualAnalysis`` whose ``grounding_status`` is one of the three
known values."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bible_engine.greek_analysis_bundle import (
    SYNTAX_GROUNDING_FULL,
    SYNTAX_GROUNDING_NONE,
    SYNTAX_GROUNDING_PARTIAL,
)
from bible_engine.greek_analysis_service import get_greek_analysis_with_syntax
from bible_engine.greek_contextual_analysis_service import validate_and_build_contextual_analysis
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

requires_syntax_store = pytest.mark.skipif(
    not resolve_default_syntax_database_path().exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "greek_analysis_v2_regression_verses.json"


def _fixture_references() -> list[str]:
    with FIXTURES_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return [v["reference"] for v in data["verses"]]


REGRESSION_REFERENCES = _fixture_references()


def test_fixture_file_still_has_exactly_15_unreviewed_developer_verses() -> None:
    with FIXTURES_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["verses"]) == 15
    assert all(v["reviewed"] is False for v in data["verses"])


@requires_syntax_store
@pytest.mark.parametrize("reference", REGRESSION_REFERENCES)
def test_fixture_reference_survives_the_full_phase2c_contract(reference: str) -> None:
    bundle = get_greek_analysis_with_syntax(reference)
    assert bundle.verses, f"{reference}: no verses produced"

    for verse in bundle.verses:
        assert verse.syntax_grounding in (
            SYNTAX_GROUNDING_FULL, SYNTAX_GROUNDING_PARTIAL, SYNTAX_GROUNDING_NONE,
        )
        # An empty model response is the minimal valid input the validator
        # must survive for every grounding status, including NONE (where a
        # real Gemini response would have nothing groundable to say).
        analysis, warnings = validate_and_build_contextual_analysis(
            {"word_notes": [], "construction_notes": [], "syntax_summary": {}}, verse
        )
        assert analysis.grounding_status == verse.syntax_grounding
        assert analysis.reference == verse.verse_id
        assert isinstance(warnings, tuple)
