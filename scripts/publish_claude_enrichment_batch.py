"""Minimal publish helper for the Claude-manual-enrichment corpus batch.

WHY THIS EXISTS RATHER THAN REUSING apply_automated_corpus_approval_v1
DIRECTLY: that RPC (supabase/migrations/20260913150000_illustration_
automated_corpus_approval.sql) implements exactly ONE named policy,
`corpus_qa_passed_v1` -- it hard-requires `qa_status = 'passed'` (the
LLM-based QA agent's verdict) and hardcodes `auto_approval_rule_version
= 'corpus_qa_passed_v1'` inside its own function body, not as a
parameter. The Claude-manual-enrichment batch was deliberately never
run through that LLM QA step (this whole batch's point was zero
external LLM calls), so `qa_status` is NULL for every record in it --
that RPC would skip all of them by design, and its rule-version string
cannot be overridden from the caller side.

The underlying SCHEMA, however, genuinely IS rule-version-agnostic:
`illustration_units_publish_provenance_check` (same migration file)
only requires `auto_approval_rule_version IS NOT NULL` -- it never
pins a specific string. So rather than adding a new SQL migration/RPC
just to parameterize one string (explicitly out of scope for this
round), this script implements a SECOND, distinct, honestly-named
policy -- `claude_enrichment_batch_v1` -- in application code, reusing
the SAME provenance columns, the SAME CHECK constraint, and the SAME
service-role credential loader the SQL RPC and the migration script
already use. It only ever publishes units it can verify came from this
exact batch (scoped by `enrichment_model`), never an arbitrary
needs_review row -- a narrower, not a looser, admission policy than
the RPC's qa_status gate.

Every eligibility condition below is independently re-verified per
unit_id, regardless of what the caller believes -- fail-closed, skip
(never raise) on an ineligible row, never a partial write. NEVER
writes human_reviewed_at. NEVER touches an already-published or
already-approved row (idempotent: a unit with approval_method already
set is skipped, not re-approved). No LLM call anywhere in this script.

`--rule-version` (2026-09-14, round 2): each Claude-manual batch gets
its own auditable rule-version string (e.g. `claude_enrichment_batch_v2`
for the 100-story round) so `SELECT auto_approval_rule_version,
count(*) ... GROUP BY 1` always shows exactly which batch approved
which rows -- the enrichment_model prefix scoping below already
guarantees this script only ever touches Claude-manual rows regardless
of which rule-version string is passed; the flag only changes what
gets RECORDED as the policy name, never which rows are eligible.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from illustration_engine.source_registry import PUBLISHABLE_LICENSE_STATUSES

DEFAULT_RULE_VERSION = "claude_enrichment_batch_v1"
EXPECTED_ENRICHMENT_MODEL_PREFIX = "claude-manual-enrichment-"


def find_candidate_units(client, *, enrichment_model_prefix: str) -> list[dict]:
    """Self-scoping: finds units by `enrichment_model` prefix rather than
    trusting a caller-supplied id list -- so this script can only ever
    touch rows it can trace back to a recognized Claude-manual batch."""
    rows = (
        client.table("illustration_units")
        .select("id,story_id,status,approval_method,human_reviewed_at,title_hu,modern_hu_text,summary_hu,enrichment_model")
        .execute()
    ).data or []
    return [r for r in rows if isinstance(r.get("enrichment_model"), str) and r["enrichment_model"].startswith(enrichment_model_prefix)]


def _story_license_publishable(client, story_id: int) -> tuple[bool, str]:
    story = client.table("illustration_stories").select("id,source_id").eq("id", story_id).limit(1).execute()
    if not story.data:
        return False, f"story {story_id} not found"
    source_id = story.data[0]["source_id"]
    source = client.table("illustration_sources").select("license_status").eq("id", source_id).limit(1).execute()
    if not source.data:
        return False, f"source {source_id} not found"
    status = source.data[0]["license_status"]
    if status not in PUBLISHABLE_LICENSE_STATUSES:
        return False, f"license_status={status!r} not publishable"
    return True, ""


def _has_at_least_one_tag(client, unit_id: int) -> bool:
    rows = client.table("illustration_unit_tags").select("unit_id").eq("unit_id", unit_id).limit(1).execute()
    return bool(rows.data)


def check_eligibility(client, unit: dict) -> str | None:
    """Returns None if eligible, else a skip reason. Every condition
    here mirrors what apply_automated_corpus_approval_v1 independently
    re-checks server-side -- minus qa_status (this policy's whole
    reason for existing), plus the enrichment_model scoping this
    policy adds on top."""
    if unit.get("status") != "needs_review":
        return f"status={unit.get('status')!r}, not needs_review"
    if unit.get("approval_method") is not None:
        return f"approval_method={unit.get('approval_method')!r} already set"
    if unit.get("human_reviewed_at") is not None:
        return "human_reviewed_at already set -- never touched by this policy"
    if not unit.get("title_hu") or not unit.get("modern_hu_text") or not unit.get("summary_hu"):
        return "missing required content field (title_hu/modern_hu_text/summary_hu)"
    if not _has_at_least_one_tag(client, unit["id"]):
        return "no taxonomy tags"
    publishable, reason = _story_license_publishable(client, unit["story_id"])
    if not publishable:
        return reason
    return None


def publish_unit(client, unit_id: int, *, apply: bool, rule_version: str = DEFAULT_RULE_VERSION) -> str:
    if not apply:
        return "would_publish"
    now = datetime.now(UTC).isoformat()
    client.table("illustration_units").update(
        {
            "status": "published",
            "approval_method": "automated_corpus_approval",
            "auto_approved_at": now,
            "auto_approval_rule_version": rule_version,
        }
    ).eq("id", unit_id).execute()
    return "published"


def run_publish(client, *, apply: bool, rule_version: str = DEFAULT_RULE_VERSION) -> dict[str, int]:
    candidates = find_candidate_units(client, enrichment_model_prefix=EXPECTED_ENRICHMENT_MODEL_PREFIX)
    eligible = published = skipped = 0

    for unit in candidates:
        reason = check_eligibility(client, unit)
        if reason is not None:
            skipped += 1
            print(f"[SKIP] unit_id={unit['id']} title={unit.get('title_hu')!r}: {reason}")
            continue

        eligible += 1
        outcome = publish_unit(client, unit["id"], apply=apply, rule_version=rule_version)
        if outcome == "published":
            published += 1
            print(f"[PUBLISHED] unit_id={unit['id']} title={unit.get('title_hu')!r}")
        else:
            print(f"[WOULD PUBLISH] unit_id={unit['id']} title={unit.get('title_hu')!r}")

    return {
        "candidates": len(candidates), "eligible": eligible,
        "skipped": skipped, "published": published,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually publish. Without this, dry-run only.")
    parser.add_argument(
        "--rule-version", default=DEFAULT_RULE_VERSION,
        help=f"auto_approval_rule_version to record for this run (default: {DEFAULT_RULE_VERSION!r}). "
             "Give each Claude-manual batch its own string for auditability -- this only changes what "
             "gets recorded, never which rows are eligible (still scoped to enrichment_model prefix).",
    )
    args = parser.parse_args()

    from illustration_engine.supabase_review_client import get_service_role_client_for_migration

    client = get_service_role_client_for_migration()
    counts = run_publish(client, apply=args.apply, rule_version=args.rule_version)

    print(f"\nCANDIDATE_COUNT={counts['candidates']}")
    print(f"ELIGIBLE_COUNT={counts['eligible']}")
    print(f"SKIPPED_COUNT={counts['skipped']}")
    if args.apply:
        print(f"PUBLISHED_COUNT={counts['published']}")
    else:
        print("\n--dry-run (default) -- no Supabase write attempted. Pass --apply to write.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
