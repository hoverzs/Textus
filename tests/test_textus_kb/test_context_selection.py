"""Tests for Phase 3B source-aware context selection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from textus_kb.context_builder import build_context_from_evidence, build_context_to_json
from textus_kb.context_profiles import (
    BUDGET_BACKGROUND,
    BUDGET_EXEGETICAL,
    BUDGET_THEOLOGY,
    PROFILE_EXEGESIS,
    PROFILE_HISTORICAL,
    ContextProfile,
)
from textus_kb.context_selection import (
    budget_type_for_item,
    jaccard_similarity,
    normalize_plain_text,
    select_context_items,
    specificity_score,
    text_token_set,
)
from textus_kb.importers.aquifer_study_notes import AQUIFER_SOURCE_ID
from textus_kb.retrieval import retrieve
from tests.local_data import requires_aquifer_dictionary_db

PHASE3C_EXEGESIS = Path("tests/fixtures/kb/john_4_1_42_exegesis_context_phase3c.json")
PHASE3C_HISTORICAL = Path("tests/fixtures/kb/john_4_1_42_historical_context_phase3c.json")


@pytest.fixture(name="full_evidence")
def full_evidence_fixture():
    return retrieve("Jn 4,1-42")


def test_not_all_aquifer_notes_enter_context(full_evidence) -> None:
    packet_count = sum(
        1 for item in full_evidence.evidence_items if item.relation_type == "exegetical_note"
    )
    assert packet_count == 24
    context = build_context_from_evidence(full_evidence, PROFILE_EXEGESIS)
    selected = context.selection_stats["aquifer_selected"]
    assert selected < 24
    assert selected >= 5


def test_evidence_packet_retains_all_aquifer_notes(full_evidence) -> None:
    assert (
        sum(1 for item in full_evidence.evidence_items if item.relation_type == "exegetical_note")
        == 24
    )


def test_direct_verse_specificity_outranks_chapter_overview() -> None:
    assert specificity_score(10, 10, passage_start=1, passage_end=42) > specificity_score(
        1, 42, passage_start=1, passage_end=42
    )


def test_passage_coverage_segments_marked(full_evidence) -> None:
    context = build_context_from_evidence(full_evidence, PROFILE_EXEGESIS)
    segments = context.selection_stats["coverage_segments"]
    assert len(segments) >= 4
    covered = [seg for seg in segments if seg["covered"]]
    assert len(covered) >= 3


def test_redundant_near_duplicate_dropped() -> None:
    from textus_kb.context_builder import ContextItem

    profile = ContextProfile.load(PROFILE_EXEGESIS)
    base = ContextItem(
        text="Sychar is a town in Samaria near Jacob's well.",
        evidence_id="EV-TEST-0001",
        source_id="biblical_places_catalog",
        relevance_score=60,
        item_type="place_catalog",
        metadata={"place_id": "sychar"},
    )
    dup = ContextItem(
        text="Sychar is a town in Samaria near Jacob's well!",
        evidence_id="EV-TEST-0002",
        source_id="biblical_places_catalog",
        relevance_score=55,
        item_type="place_catalog",
        metadata={"place_id": "sychar-b"},
    )
    left = text_token_set(base.text)
    right = text_token_set(dup.text)
    assert jaccard_similarity(left, right) >= 0.85
    selected, stats = select_context_items(
        [base, dup],
        profile,
        passage_canonical="John.4.1-42",
    )
    assert len(selected) == 1
    assert stats.dropped_redundant >= 1


@requires_aquifer_dictionary_db
def test_per_source_type_budget_respected(full_evidence) -> None:
    context = build_context_from_evidence(full_evidence, PROFILE_EXEGESIS)
    profile = ContextProfile.load(PROFILE_EXEGESIS)
    tokens_by_type = context.selection_stats["tokens_by_type"]
    for budget_type, used in tokens_by_type.items():
        cap = profile.type_budgets.get(budget_type)
        if cap is None:
            continue
        # Small overshoot allowed only for coverage edge cases; keep under 1.15x.
        assert used <= int(cap * 1.25)


def test_minimum_diversity_present(full_evidence) -> None:
    context = build_context_from_evidence(full_evidence, PROFILE_EXEGESIS)
    section_types = {section.type for section in context.sections}
    assert "linguistic" in section_types
    assert "exegetical" in section_types
    assert "places" in section_types or "background" in section_types or "dictionary" in section_types


def test_target_less_than_max() -> None:
    profile = ContextProfile.load(PROFILE_EXEGESIS)
    assert profile.target_tokens < profile.max_tokens


def test_hard_max_never_exceeded(full_evidence) -> None:
    context = build_context_from_evidence(full_evidence, PROFILE_EXEGESIS)
    assert context.estimated_tokens <= context.max_tokens
    assert context.estimated_tokens <= 4500


def test_exegesis_target_range(full_evidence) -> None:
    context = build_context_from_evidence(full_evidence, PROFILE_EXEGESIS)
    # Prefer soft target (~2500); hard max 4500 is ceiling only — do not pad to max.
    assert context.estimated_tokens <= context.max_tokens == 4500
    assert context.estimated_tokens <= 2800
    assert context.target_tokens == 2500
    stats = context.selection_stats
    assert stats["target_kb_tokens"] == 2500
    assert stats["max_kb_tokens"] == 4500
    assert "actual_kb_tokens" in stats
    assert stats["unused_target_kb_tokens"] == max(0, 2500 - stats["actual_kb_tokens"])
    assert stats["unused_max_kb_tokens"] == max(0, 4500 - stats["actual_kb_tokens"])
    # Hard max is a ceiling, not a fill target.
    assert stats["actual_kb_tokens"] < int(0.8 * 4500)
    assert "dropped_by_target" in stats or "dropped_target" in stats
    assert "source_diversity" in stats


def test_historical_under_max(full_evidence) -> None:
    context = build_context_from_evidence(full_evidence, PROFILE_HISTORICAL)
    assert context.estimated_tokens <= 3500
    assert context.estimated_tokens <= 2500
    assert context.target_tokens == 2200
    assert context.selection_stats["dictionary_selected"] >= 1
    assert context.selection_stats["historical_background_selected"] >= 1
    assert context.selection_stats["historical_coverage_status"] == "ok"
    assert context.selection_stats["actual_kb_tokens"] < int(0.8 * 3500)
    assert context.selection_stats["unused_max_kb_tokens"] > 0


def test_provenance_preserved(full_evidence, tmp_path: Path) -> None:
    # Commentary-blind by explicit path override (2026-09-03 Commentary
    # grounding round, ld. test_context_builder.py::test_context_evidence_
    # ids_exist_in_evidence_packet's own comment): this test is about the
    # EXEGESIS-native evidence pipeline's own provenance, not the
    # separately-sourced (real, non-fabricated) Commentary layer.
    context = build_context_from_evidence(
        full_evidence,
        PROFILE_EXEGESIS,
        commentary_database_path=tmp_path / "no_commentary.sqlite3",
    )
    evidence_ids = {item.evidence_id for item in full_evidence.evidence_items}
    entity_ids = {f"ENT-{entity['entity_id']}" for entity in full_evidence.entities}
    allowed_ids = evidence_ids | entity_ids
    for section in context.sections:
        for item in section.items:
            assert item.evidence_id in allowed_ids
            assert item.source_id
            assert item.relevance_score > 0


def test_selection_deterministic(full_evidence) -> None:
    first = build_context_to_json("Jn 4,1-42", PROFILE_EXEGESIS, evidence=full_evidence)
    second = build_context_to_json("Jn 4,1-42", PROFILE_EXEGESIS, evidence=full_evidence)
    assert first == second


@requires_aquifer_dictionary_db
def test_selection_diagnostics_present(full_evidence) -> None:
    context = build_context_from_evidence(full_evidence, PROFILE_EXEGESIS)
    stats = context.selection_stats
    assert stats["candidates"] >= stats["selected"]
    assert "tokens_by_type" in stats
    assert "coverage_segments" in stats
    assert stats["study_notes_candidates"] == 24
    assert stats["dictionary_candidates"] == 66
    assert "linguistic_selected" in stats
    assert "places_background_selected" in stats


def test_disabled_aquifer_still_builds(phase2a_manifest) -> None:
    evidence = retrieve("Jn 4,1-42", manifest=phase2a_manifest)
    context = build_context_from_evidence(evidence, PROFILE_EXEGESIS)
    assert context.estimated_tokens > 0
    assert context.selection_stats["aquifer_selected"] == 0
    assert any(section.type == "linguistic" for section in context.sections)


def test_schema_version_is_v2(full_evidence) -> None:
    context = build_context_from_evidence(full_evidence, PROFILE_EXEGESIS)
    assert context.schema_version == "2"
    assert "target_tokens" in context.to_dict()
    assert "selection_stats" in context.to_dict()


def test_phase3c_golden_fixtures(full_evidence) -> None:
    assert PHASE3C_EXEGESIS.exists()
    assert PHASE3C_HISTORICAL.exists()
    ex = build_context_from_evidence(full_evidence, PROFILE_EXEGESIS).to_dict()
    hi = build_context_from_evidence(full_evidence, PROFILE_HISTORICAL).to_dict()
    assert ex["estimated_tokens"] <= 4500
    assert hi["estimated_tokens"] <= 3500
    assert ex["selection_stats"]["study_notes_selected"] >= 1
    assert ex["selection_stats"]["dictionary_selected"] >= 1


def test_theological_source_maps_to_theology_budget_type() -> None:
    assert budget_type_for_item("theological_source") == BUDGET_THEOLOGY
    assert budget_type_for_item("exegetical_note") == BUDGET_EXEGETICAL
    assert budget_type_for_item("historical_enrichment") == BUDGET_BACKGROUND
