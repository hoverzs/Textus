"""Applies the `corpus_qa_passed_v1` automated-approval policy to a
BOUNDED, explicitly-selected batch of eligible `illustration_units` rows
in Supabase -- never "publish everything," always an explicit unit_id
list, always re-verified server-side by `apply_automated_corpus_
approval_v1()` (see `supabase/migrations/
20260913150000_illustration_automated_corpus_approval.sql`) regardless
of what this script itself believes is eligible.

NEVER writes `human_reviewed_at`, `reviewed_by`, or `reviewed_by_email`
-- those remain exclusively the human-review workflow's fields. Every
unit this script's `--apply` publishes gets `approval_method=
'automated_corpus_approval'`, `auto_approved_at=<server-side now()>`,
`auto_approval_rule_version='corpus_qa_passed_v1'`, and `human_
reviewed_at` stays NULL, enforced by the DB CHECK constraint itself, not
just this script's intent.

SAFETY:
- `--dry-run` (the default) only SELECTs eligible candidates and reports
  what a batch WOULD contain -- it never calls the write RPC.
- `--apply` is required, explicitly, to actually write anything, and
  still only ever calls `apply_automated_corpus_approval_v1()` -- there
  is no other write path in this script, and that RPC itself re-checks
  every eligibility condition per unit_id before touching a row.
- `--limit N` (default 25) bounds how many units a single run can
  publish -- deliberately small by default, for a controlled pilot
  rather than an all-at-once cutover. Raise it explicitly for a larger
  batch once a pilot has been reviewed against the live corpus.
- `--diverse` (default true) spreads the selected batch across as many
  distinct sources as possible (round-robin), rather than picking the
  first N candidates (which could otherwise all come from one source).
"""

from __future__ import annotations

import argparse
import sys

DEFAULT_LIMIT = 25


def select_diverse_batch(candidates: list[dict], *, limit: int) -> list[int]:
    """Round-robins across distinct `source_code` groups so a capped
    batch is never dominated by a single source. `candidates`: a list of
    `{"id": int, "source_code": str}` dicts (order within/across sources
    doesn't matter going in -- this function sorts deterministically so
    the same candidate pool always produces the same selection).

    Pure function, no I/O -- independently testable without touching
    Supabase or any fake client."""
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit!r}")

    by_source: dict[str, list[int]] = {}
    for c in candidates:
        by_source.setdefault(c["source_code"], []).append(c["id"])
    for ids in by_source.values():
        ids.sort()

    sources = sorted(by_source.keys())
    selected: list[int] = []
    if not sources:
        return selected

    idx = 0
    guard = 0
    max_guard = (len(candidates) + len(sources)) * 2 + 10
    while len(selected) < limit and any(by_source[s] for s in sources) and guard < max_guard:
        source = sources[idx % len(sources)]
        if by_source[source]:
            selected.append(by_source[source].pop(0))
        idx += 1
        guard += 1
    return selected


def fetch_eligible_candidates(client) -> list[dict]:
    """Read-only: a best-effort candidate list for REPORTING and batch
    SELECTION only -- the authoritative eligibility check is always
    `apply_automated_corpus_approval_v1()` itself, server-side, per
    unit_id, at apply time. This mirrors the same conditions but is not
    trusted as the final word; a candidate listed here that the RPC
    later skips (e.g. a race with a concurrent human review) is reported
    by the RPC's own per-row outcome, never silently treated as
    published."""
    units = (
        client.table("illustration_units")
        .select("id,status,qa_status,title_hu,modern_hu_text,summary_hu,human_reviewed_at,story_id")
        .eq("qa_status", "passed")
        .eq("status", "needs_review")
        .is_("human_reviewed_at", "null")
        .execute()
        .data
    )
    if not units:
        return []

    story_ids = sorted({u["story_id"] for u in units})
    stories = {}
    for chunk_start in range(0, len(story_ids), 200):
        chunk = story_ids[chunk_start : chunk_start + 200]
        rows = client.table("illustration_stories").select("id,source_id").in_("id", chunk).execute().data
        for r in rows:
            stories[r["id"]] = r["source_id"]

    source_ids = sorted(set(stories.values()))
    sources = {}
    for chunk_start in range(0, len(source_ids), 200):
        chunk = source_ids[chunk_start : chunk_start + 200]
        rows = client.table("illustration_sources").select("id,code,license_status").in_("id", chunk).execute().data
        for r in rows:
            sources[r["id"]] = r

    publishable = {"public_domain_confirmed", "public_domain_assumed_by_age", "permission_granted"}
    candidates = []
    for u in units:
        if not (u["title_hu"] and u["modern_hu_text"] and u["summary_hu"]):
            continue
        source_id = stories.get(u["story_id"])
        source = sources.get(source_id) if source_id is not None else None
        if source is None or source["license_status"] not in publishable:
            continue
        candidates.append({"id": u["id"], "source_code": source["code"]})
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually call the write RPC. Without this, dry-run only.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"Max units to publish this run (default {DEFAULT_LIMIT}).")
    parser.add_argument("--no-diverse", action="store_true", help="Disable round-robin source diversity (not recommended).")
    args = parser.parse_args()

    from illustration_engine.supabase_review_client import get_service_role_client_for_migration

    client = get_service_role_client_for_migration()

    print("=== Fetching eligible candidates (read-only) ===")
    candidates = fetch_eligible_candidates(client)
    print(f"Candidates matching qa_status=passed, needs_review, complete content, publishable license: {len(candidates)}")

    by_source: dict[str, int] = {}
    for c in candidates:
        by_source[c["source_code"]] = by_source.get(c["source_code"], 0) + 1
    print("By source:")
    for code, n in sorted(by_source.items()):
        print(f"  {code}: {n}")

    if args.no_diverse:
        selected = sorted(c["id"] for c in candidates)[: args.limit]
    else:
        selected = select_diverse_batch(candidates, limit=args.limit)

    selected_by_source: dict[str, int] = {}
    id_to_source = {c["id"]: c["source_code"] for c in candidates}
    for uid in selected:
        code = id_to_source.get(uid, "?")
        selected_by_source[code] = selected_by_source.get(code, 0) + 1
    print(f"\nSelected batch for this run: {len(selected)} unit(s)")
    print("Selected by source:")
    for code, n in sorted(selected_by_source.items()):
        print(f"  {code}: {n}")
    print(f"Selected unit_ids: {selected}")

    if not args.apply:
        print("\n--dry-run (default) -- no RPC call made, nothing published.")
        return 0

    if not selected:
        print("\nNothing eligible to apply.")
        return 0

    print(f"\n=== Applying corpus_qa_passed_v1 to {len(selected)} unit(s) via apply_automated_corpus_approval_v1() ===")
    result = client.rpc("apply_automated_corpus_approval_v1", {"p_unit_ids": selected}).execute()
    rows = result.data or []

    published = [r for r in rows if r["outcome"] == "published"]
    skipped = [r for r in rows if r["outcome"] == "skipped"]

    print(f"\npublished: {len(published)}")
    print(f"skipped: {len(skipped)}")
    for r in skipped:
        print(f"  SKIPPED unit_id={r['unit_id']}: {r['detail']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
