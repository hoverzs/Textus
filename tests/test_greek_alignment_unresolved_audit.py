"""Phase 2B.1 §2/§4 — locks in the unresolved-alignment categorization and
full-corpus grounding-status reports produced by
scripts/audit_greek_alignment_unresolved.py and
scripts/report_greek_syntax_grounding.py, using their already-committed
JSON output (not requiring the MACULA TSV to re-run the audit itself)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
UNRESOLVED_REPORT = ROOT / "data" / "generated" / "greek_alignment_unresolved_audit.json"
GROUNDING_REPORT = ROOT / "data" / "generated" / "greek_syntax_grounding_report.json"

requires_unresolved_report = pytest.mark.skipif(
    not UNRESOLVED_REPORT.exists(), reason="greek_alignment_unresolved_audit.json not generated locally"
)
requires_grounding_report = pytest.mark.skipif(
    not GROUNDING_REPORT.exists(), reason="greek_syntax_grounding_report.json not generated locally"
)


@requires_unresolved_report
def test_unresolved_categories_sum_to_the_reported_total() -> None:
    report = json.loads(UNRESOLVED_REPORT.read_text(encoding="utf-8"))
    assert sum(report["category_counts"].values()) == report["total_unresolved"]


@requires_unresolved_report
def test_no_unexplained_category_exceeds_one_percent_of_unresolved() -> None:
    """Task requirement: "There should be no unexplained 'unknown'
    bucket." The residual "other_unexplained" category must stay small —
    this phase's own investigation drove it from 5.55% to 0.30% of
    unresolved tokens by adding the "candidate already claimed by another
    TAGNT token" category; this test locks in that it does not regress."""
    report = json.loads(UNRESOLVED_REPORT.read_text(encoding="utf-8"))
    total = report["total_unresolved"]
    unexplained = report["category_counts"].get("other_unexplained", 0)
    assert unexplained / total < 0.01


@requires_unresolved_report
def test_textual_variant_edition_difference_is_the_dominant_category() -> None:
    """The well-understood, evidence-backed category (edition_flags
    predicting absence from SBLGNT) should account for the majority of all
    unresolved tokens — confirms the alignment design's core hypothesis
    (§1.1 of the Phase 2B doc) generalizes across the whole corpus, not
    just the Jn 3:16 example it was built from."""
    report = json.loads(UNRESOLVED_REPORT.read_text(encoding="utf-8"))
    total = report["total_unresolved"]
    dominant = report["category_counts"]["textual_variant_edition_difference"]
    assert dominant / total > 0.5


@requires_grounding_report
def test_grounding_counts_sum_to_reported_total_verses() -> None:
    report = json.loads(GROUNDING_REPORT.read_text(encoding="utf-8"))
    assert sum(report["grounding_counts"].values()) == report["total_verses"]


@requires_grounding_report
def test_no_grounded_syntax_is_a_small_minority_of_verses() -> None:
    report = json.loads(GROUNDING_REPORT.read_text(encoding="utf-8"))
    total = report["total_verses"]
    none_count = report["grounding_counts"].get("NO_GROUNDED_SYNTAX", 0)
    assert none_count / total < 0.02


@requires_grounding_report
def test_all_27_books_appear_in_the_grounding_report() -> None:
    report = json.loads(GROUNDING_REPORT.read_text(encoding="utf-8"))
    assert len(report["book_grounding"]) == 27


@requires_grounding_report
def test_every_book_has_at_least_some_fully_grounded_verses() -> None:
    """Sanity check that phrase/clause coverage genuinely reached all 27
    books, not just token alignment — a book with zero FULLY_GROUNDED_
    SYNTAX verses would indicate its lowfat XML failed to parse/ingest."""
    report = json.loads(GROUNDING_REPORT.read_text(encoding="utf-8"))
    missing = [
        book for book, counts in report["book_grounding"].items()
        if counts.get("FULLY_GROUNDED_SYNTAX", 0) == 0
    ]
    assert missing == []
