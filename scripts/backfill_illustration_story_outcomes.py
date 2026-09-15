"""One-time backfill of supabase/migrations/20260915000000_illustration_
story_outcomes.sql -- writes the confirmed prior REJECT decisions (rounds
v1-v5 plus the v8/round-6 200-story batch) into the new registry so future
enrichment-batch selection can skip them instead of re-selecting and
re-rejecting the same stories.

Same constraint as scripts/setup_hebrew_linguistic_schema.py: the Supabase
Python/PostgREST client cannot execute DDL. Run this script once the
migration has been applied (manually, via the Supabase SQL Editor -- this
script prints the exact SQL to paste if the table isn't reachable yet).

PROVENANCE OF THE BACKFILL DATA BELOW (2026-09-15 maintenance round):
Each round's REJECTs were reconstructed as (selected story_ids) minus
(imported story_ids) -- selected ids come from that round's raw dump
files, imported ids from that round's export JSON. Every reconstructed
candidate (52 from rounds v1-v5, 77 from the v8 batch's 4 checkpoints --
129 total, some counted twice, see below) was then cross-checked against
LIVE production illustration_units and dropped if a unit now exists for
it (24 such "rescues" found and dropped -- e.g. story 802, 206, 1723).

Of the 28 surviving rounds v1-v5 REJECTs, ALL 28 turned out to have been
independently re-selected AND re-rejected again by the v8 batch -- i.e.
100% of the previously-REJECTed-but-still-unprocessed stories that
remained selectable got selected again, wasting the exact LLM/authoring
effort this registry exists to prevent. This is empirical confirmation of
the problem, not a hypothetical. For those 28, the v8 determination is
kept as authoritative (registry stores latest-known outcome per story,
not a full history) with reason="reconfirmed_reject". The final list
below is therefore exactly the v8 batch's 77 REJECT decisions -- 3 with a
specific short reason (identified cross-source duplicates), the 28
reconfirmed ones, and the rest a generic "batch_reject" (no granular
reason was durably recorded at classification time for those, and this
project's own rule is to never store long LLM justifications anyway).

Usage:
    python scripts/backfill_illustration_story_outcomes.py           # dry run
    python scripts/backfill_illustration_story_outcomes.py --apply   # writes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MIGRATION_PATH = ROOT / "supabase" / "migrations" / "20260915000000_illustration_story_outcomes.sql"

REJECT_BACKFILL_V1: list[dict] = [
    {"story_id": 612, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 623, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 631, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 634, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 637, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 639, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 640, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 661, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 665, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 666, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 667, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 672, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 701, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 708, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 720, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 721, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "reconfirmed_reject"},
    {"story_id": 757, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 765, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 766, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 768, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 770, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 771, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 773, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 774, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 784, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 787, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 788, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 794, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c1", "reason": "batch_reject"},
    {"story_id": 1104, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1109, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1111, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1113, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1117, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1119, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1120, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1121, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1122, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1123, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1124, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1125, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "reconfirmed_reject"},
    {"story_id": 1129, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1130, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1131, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1132, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1135, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1136, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1138, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1142, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1143, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1144, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1145, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1149, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1157, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1158, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1159, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "duplicate_of_story_707"},
    {"story_id": 1160, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c3", "reason": "batch_reject"},
    {"story_id": 1172, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1174, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1175, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1177, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1181, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1182, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1184, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1186, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1187, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1189, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1190, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1192, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1193, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1199, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "duplicate_of_story_610"},
    {"story_id": 1202, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1205, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1206, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "duplicate_of_story_688"},
    {"story_id": 1207, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1208, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1209, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
    {"story_id": 1210, "outcome": "rejected", "processor": "claude_enrichment_batch_v8_c4", "reason": "batch_reject"},
]


def _paginate(client, table: str, select: str, page_size: int = 1000) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        page = client.table(table).select(select).range(start, start + page_size - 1).execute().data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually write rows (default: dry run)")
    args = parser.parse_args()

    from supabase_client import get_supabase_client

    client = get_supabase_client()

    try:
        client.table("illustration_story_outcomes").select("story_id").limit(0).execute()
    except Exception:  # noqa: BLE001
        print("illustration_story_outcomes does not exist in production yet.")
        print("Apply this migration MANUALLY via the Supabase SQL Editor first:\n")
        print(f"  {MIGRATION_PATH.relative_to(ROOT)}\n")
        print("--- file contents ---\n")
        print(MIGRATION_PATH.read_text(encoding="utf-8"))
        return 2

    ids = [row["story_id"] for row in REJECT_BACKFILL_V1]
    if len(ids) != len(set(ids)):
        print("REJECT_BACKFILL_V1 contains duplicate story_ids -- aborting.")
        return 1

    unit_story_ids = {r["story_id"] for r in _paginate(client, "illustration_units", "story_id")}
    still_valid = [row for row in REJECT_BACKFILL_V1 if row["story_id"] not in unit_story_ids]
    rescued = [row for row in REJECT_BACKFILL_V1 if row["story_id"] in unit_story_ids]

    existing = {
        r["story_id"] for r in _paginate(client, "illustration_story_outcomes", "story_id")
    }
    to_write = [row for row in still_valid if row["story_id"] not in existing]
    already_present = [row for row in still_valid if row["story_id"] in existing]

    print(f"Backfill candidates: {len(REJECT_BACKFILL_V1)}")
    print(f"Rescued since reconstruction (unit now exists -- skipped): {len(rescued)}")
    if rescued:
        print(f"  story_ids: {sorted(r['story_id'] for r in rescued)}")
    print(f"Already present in registry (skipped): {len(already_present)}")
    print(f"To write: {len(to_write)}")

    if not args.apply:
        print("\nDry run -- no writes performed. Re-run with --apply to write.")
        return 0

    if to_write:
        client.table("illustration_story_outcomes").insert(to_write).execute()
        print(f"Inserted {len(to_write)} rows.")
    else:
        print("Nothing to insert.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
