"""Phase 2D — one-time Supabase setup for the normalized Hebrew linguistic
layer (MACULA syntax/phrase/clause/semantic-role/coreference data on top of
the Phase 2A/2B/2C TAHOT/TEHMC/TBESH deterministic foundation).

Same constraint as ``scripts/setup_commentary_translation_table.py``: the
Supabase Python client cannot execute DDL. The versioned migration lives at
``supabase/migrations/20260908190000_hebrew_linguistic_layer.sql`` — this
script only (1) prints that file's exact contents for a manual paste into
the Supabase project's SQL Editor, and (2) if already applied, verifies
every expected table is reachable with a read-only ``SELECT ... LIMIT 0``
(never writes anything).

This script has NOT been run against any real Supabase project from this
environment — no production credentials are available here. See
docs/hebrew_analysis_v2_phase2d.md §6/§16 for the exact manual deployment
steps and current status.

Usage:
    python scripts/setup_hebrew_linguistic_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MIGRATION_PATH = ROOT / "supabase" / "migrations" / "20260908190000_hebrew_linguistic_layer.sql"

EXPECTED_TABLES = (
    "original_language_dataset_versions",
    "hebrew_verses",
    "hebrew_tokens",
    "hebrew_token_strong_ids",
    "hebrew_token_components",
    "hebrew_source_nodes",
    "hebrew_token_alignments",
    "hebrew_phrases",
    "hebrew_clauses",
    "hebrew_syntax_membership",
    "hebrew_syntax_edges",
    "hebrew_semantic_roles",
    "hebrew_participants",
    "hebrew_coreference",
    "hebrew_detected_patterns",
    "hebrew_detected_pattern_tokens",
)


def main() -> int:
    if not MIGRATION_PATH.exists():
        print(f"Migration file not found: {MIGRATION_PATH}")
        return 2

    print("Ezt a migraciot futtasd le MANUALISAN a Supabase projekt SQL Editor-jaban:\n")
    print(f"  {MIGRATION_PATH.relative_to(ROOT)}\n")
    print("--- fajl tartalma ---\n")
    print(MIGRATION_PATH.read_text(encoding="utf-8"))

    print("\nEllenorzes: mind a 16 tabla mar elerheto-e (csak olvasas, LIMIT 0)...")
    try:
        from supabase_client import get_supabase_client

        client = get_supabase_client()
    except Exception as exc:  # noqa: BLE001
        print(f"  Nem sikerult Supabase klienst letrehozni (varhato, ha nincs hitelesito adat): {exc}")
        return 1

    missing = []
    for table in EXPECTED_TABLES:
        try:
            client.table(table).select("*").limit(0).execute()
        except Exception:  # noqa: BLE001
            missing.append(table)

    if missing:
        print(f"  Meg nem erhetok el (ez varhato, ha a migraciot meg nem futtattad le): {missing}")
        return 1

    print(f"  OK -- mind a {len(EXPECTED_TABLES)} tabla elerheto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
