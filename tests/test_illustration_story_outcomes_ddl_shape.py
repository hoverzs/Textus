"""Structural checks on supabase/migrations/20260915000000_illustration_
story_outcomes.sql -- same source-string-assertion convention as
tests/test_illustration_automated_approval_ddl_shape.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DDL_PATH = ROOT / "supabase" / "migrations" / "20260915000000_illustration_story_outcomes.sql"
DDL_SQL = DDL_PATH.read_text(encoding="utf-8")


def test_migration_file_exists() -> None:
    assert DDL_PATH.is_file()


def test_table_created() -> None:
    assert "create table if not exists illustration_story_outcomes" in DDL_SQL


def test_story_id_references_illustration_stories() -> None:
    assert "story_id bigint not null references illustration_stories(id)" in DDL_SQL


def test_outcome_constrained_to_exactly_two_values() -> None:
    assert "outcome text not null check (outcome in ('unit_created', 'rejected'))" in DDL_SQL


def test_one_row_per_story_enforced() -> None:
    """The registry stores the story's latest known outcome, not a full
    history log -- a duplicate story_id must be structurally impossible."""
    assert "unique (story_id)" in DDL_SQL


def test_reason_is_length_capped_to_stay_short() -> None:
    """Regression guard for the explicit requirement that this field never
    hold a long LLM justification -- only a short REJECT category."""
    assert "reason text check (reason is null or char_length(reason) <= 200)" in DDL_SQL


def test_processed_at_defaults_to_now() -> None:
    assert "processed_at timestamptz not null default now()" in DDL_SQL


def test_outcome_index_present() -> None:
    assert "idx_illustration_story_outcomes_outcome" in DDL_SQL
