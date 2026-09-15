"""Structural checks on supabase/migrations/20260913150000_illustration_
automated_corpus_approval.sql -- same source-string-assertion convention
as tests/test_illustration_supabase_ddl_shape.py. Real-PostgreSQL
behavior of this exact file was independently verified via a disposable
local Postgres instance before this migration was applied to production
(19/19 checks, including the NULL-three-valued-logic CHECK bug this file
pins a regression test for) -- see the round's own report for that run's
output; this file only guards against a future edit silently dropping
one of these architectural decisions."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DDL_PATH = ROOT / "supabase" / "migrations" / "20260913150000_illustration_automated_corpus_approval.sql"
DDL_SQL = DDL_PATH.read_text(encoding="utf-8")


def test_migration_file_exists() -> None:
    assert DDL_PATH.is_file()


def test_new_provenance_columns_added() -> None:
    assert "add column if not exists approval_method text" in DDL_SQL
    assert "add column if not exists auto_approved_at timestamptz" in DDL_SQL
    assert "add column if not exists auto_approval_rule_version text" in DDL_SQL


def test_approval_method_constrained_to_exactly_two_values() -> None:
    assert "approval_method in ('human_review', 'automated_corpus_approval')" in DDL_SQL


def test_old_publish_check_dropped_by_definition_match_not_hardcoded_name() -> None:
    """The migration must find the old constraint dynamically (pg_get_
    constraintdef match) rather than assuming a specific auto-generated
    name -- Postgres names unnamed CHECK constraints positionally, which
    is fragile to guess across an ALTER-only migration."""
    assert "pg_get_constraintdef(oid) ilike" in DDL_SQL
    assert "drop constraint %I" in DDL_SQL


def test_new_publish_check_requires_approval_method_not_null() -> None:
    """Regression test for the exact bug the local real-Postgres
    validation caught: without an explicit `approval_method is not null`
    guard, SQL three-valued logic lets a NULL approval_method slip past
    the CHECK (a NULL result is treated as PASSING, not failing) even
    with human_reviewed_at set and no approval_method recorded at all."""
    assert "and approval_method is not null" in DDL_SQL


def test_new_publish_check_covers_both_provenance_shapes() -> None:
    assert "approval_method = 'human_review' and human_reviewed_at is not null" in DDL_SQL
    assert "approval_method = 'automated_corpus_approval'" in DDL_SQL
    assert "auto_approved_at is not null" in DDL_SQL
    assert "auto_approval_rule_version is not null" in DDL_SQL


def test_automated_branch_structurally_forbids_human_reviewed_at() -> None:
    """The automated_corpus_approval branch of the CHECK requires
    human_reviewed_at IS NULL -- structurally impossible to satisfy both
    provenance shapes at once, so a row can never claim to be BOTH
    automated- and human-approved simultaneously."""
    check_start = DDL_SQL.index("illustration_units_publish_provenance_check check")
    check_end = DDL_SQL.index(");", check_start)
    check_body = DDL_SQL[check_start:check_end]
    assert "and human_reviewed_at is null" in check_body


def test_content_protection_trigger_extended_to_automated_approval() -> None:
    """The reviewed-content-protection trigger's WHEN condition must
    cover approval_method IS NOT NULL too -- otherwise an automated-
    approved published unit (human_reviewed_at always NULL by design)
    would have zero protection against silent content rewriting."""
    trigger_fn_start = DDL_SQL.index("create or replace function trg_illustration_units_protect_reviewed_content")
    trigger_fn_end = DDL_SQL.index("$$ language plpgsql;", trigger_fn_start)
    trigger_body = DDL_SQL[trigger_fn_start:trigger_fn_end]
    assert "old.human_reviewed_at is not null or old.approval_method is not null" in trigger_body
    # the reset escape hatch must require ALL provenance fields cleared together
    assert "new.approval_method is null" in trigger_body
    assert "new.auto_approved_at is null" in trigger_body
    assert "new.auto_approval_rule_version is null" in trigger_body


def test_no_create_or_replace_trigger_needed_only_function() -> None:
    """CREATE OR REPLACE FUNCTION alone is sufficient to update the
    existing trigger's behavior (the trigger already references the
    function by name from the original migration) -- this file must NOT
    contain a redundant CREATE TRIGGER for illustration_units_protect_
    reviewed_content, which would either fail (duplicate trigger name)
    or be dead weight."""
    assert "create trigger illustration_units_protect_reviewed_content" not in DDL_SQL


def test_automated_approval_rpc_exists_and_is_security_definer() -> None:
    assert "create or replace function apply_automated_corpus_approval_v1(p_unit_ids bigint[])" in DDL_SQL
    rpc_start = DDL_SQL.index("create or replace function apply_automated_corpus_approval_v1")
    rpc_end = DDL_SQL.index("$$;", rpc_start)
    rpc_body = DDL_SQL[rpc_start:rpc_end]
    assert "security definer" in rpc_body
    assert "set search_path = public" in rpc_body


def test_automated_approval_rpc_is_service_role_only() -> None:
    assert (
        "revoke all on function apply_automated_corpus_approval_v1(bigint[]) from public, anon, authenticated"
        in DDL_SQL
    )
    assert "grant execute on function apply_automated_corpus_approval_v1(bigint[]) to service_role" in DDL_SQL


def test_automated_approval_rpc_checks_qa_status_passed() -> None:
    rpc_start = DDL_SQL.index("create or replace function apply_automated_corpus_approval_v1")
    rpc_end = DDL_SQL.index("$$;", rpc_start)
    rpc_body = DDL_SQL[rpc_start:rpc_end]
    assert "v_unit.qa_status is distinct from 'passed'" in rpc_body


def test_automated_approval_rpc_never_touches_already_human_reviewed_units() -> None:
    rpc_start = DDL_SQL.index("create or replace function apply_automated_corpus_approval_v1")
    rpc_end = DDL_SQL.index("$$;", rpc_start)
    rpc_body = DDL_SQL[rpc_start:rpc_end]
    assert "v_unit.human_reviewed_at is not null" in rpc_body


def test_automated_approval_rpc_never_writes_human_reviewed_at() -> None:
    """The RPC's actual UPDATE statement must set approval_method/
    auto_approved_at/auto_approval_rule_version/status ONLY -- never
    human_reviewed_at, never reviewed_by, never reviewed_by_email."""
    rpc_start = DDL_SQL.index("create or replace function apply_automated_corpus_approval_v1")
    rpc_end = DDL_SQL.index("$$;", rpc_start)
    rpc_body = DDL_SQL[rpc_start:rpc_end]
    update_start = rpc_body.index("update illustration_units")
    update_end = rpc_body.index("where id = v_id", update_start)
    update_clause = rpc_body[update_start:update_end]
    assert "human_reviewed_at" not in update_clause
    assert "reviewed_by" not in update_clause
    assert "approval_method = 'automated_corpus_approval'" in update_clause
    assert "auto_approval_rule_version = 'corpus_qa_passed_v1'" in update_clause


def test_automated_approval_rpc_checks_taxonomy_tags() -> None:
    rpc_start = DDL_SQL.index("create or replace function apply_automated_corpus_approval_v1")
    rpc_end = DDL_SQL.index("$$;", rpc_start)
    rpc_body = DDL_SQL[rpc_start:rpc_end]
    assert "v_tag_count = 0" in rpc_body


def test_automated_approval_rpc_checks_license_publishable() -> None:
    rpc_start = DDL_SQL.index("create or replace function apply_automated_corpus_approval_v1")
    rpc_end = DDL_SQL.index("$$;", rpc_start)
    rpc_body = DDL_SQL[rpc_start:rpc_end]
    assert "'public_domain_confirmed', 'public_domain_assumed_by_age', 'permission_granted'" in rpc_body


def test_automated_approval_rpc_checks_strategy_mismatch_with_correct_thresholds() -> None:
    """Regression test pinning the exact thresholds (1500/3000) verified
    against illustration_engine.enrichment_pipeline's real constants
    (_MAX_FULL_TRANSLATION_CHARS/_MAX_CONDENSED_DIRECT_CHARS) during the
    read-only production audit -- an earlier draft of the equivalent
    Python mirror used a wrong value (4000) that would have silently
    under-counted mismatches."""
    rpc_start = DDL_SQL.index("create or replace function apply_automated_corpus_approval_v1")
    rpc_end = DDL_SQL.index("$$;", rpc_start)
    rpc_body = DDL_SQL[rpc_start:rpc_end]
    assert "v_original_length <= 1500" in rpc_body
    assert "v_original_length <= 3000" in rpc_body


def test_automated_approval_rpc_returns_per_row_outcome_never_errors_whole_batch() -> None:
    assert "returns table(unit_id bigint, outcome text, detail text)" in DDL_SQL
    rpc_start = DDL_SQL.index("create or replace function apply_automated_corpus_approval_v1")
    rpc_end = DDL_SQL.index("$$;", rpc_start)
    rpc_body = DDL_SQL[rpc_start:rpc_end]
    assert "outcome := 'skipped'" in rpc_body
    assert "outcome := 'published'" in rpc_body
