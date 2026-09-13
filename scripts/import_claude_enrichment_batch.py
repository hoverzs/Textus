"""Minimal, reusable, idempotent importer: validated Claude-authored
enrichment JSON (the flat shape exported from a local `enrich_story()`
run) -> production Supabase `illustration_units` + `illustration_unit_
tags`, always as `status='needs_review'`, never published.

Deliberately NOT a new enrichment system and NOT a copy of `scripts/
migrate_illustrations_to_supabase.py`'s full-corpus writer -- this
script only ever touches the two child tables (`illustration_units`,
`illustration_unit_tags`); `illustration_sources`/`illustration_stories`
are assumed to already exist in production (true for every story this
script has been used for so far -- the full raw corpus, 1771 stories,
was already migrated even though only a subset had units).

REUSES rather than reimplements:
- `illustration_engine.enrichment_pipeline._validate_common_fields` --
  the SAME deterministic validator `enrich_story()` itself calls, so
  there is exactly one place the field rules live, never two drifting
  copies. No LLM call anywhere in this module or its imports.
- `illustration_engine.enrichment_pipeline.derive_enrichment_strategy`
  -- the same length-based derivation_type authority `enrich_story()`
  uses, so a record can't claim a derivation_type its own original
  story length wouldn't allow.
- `illustration_engine.supabase_review_client.
  get_service_role_client_for_migration` -- the SAME service-role
  credential loader the corpus migration script uses. NEVER the anon
  client (illustration_* tables have zero anon/authenticated grants).

FAIL-CLOSED, NEVER-OVERWRITE idempotency: a record is looked up by the
SAME natural keys the rest of this corpus already relies on --
`(illustration_sources.code, illustration_stories.canonical_key)` to
resolve the production story_id (the record's own `story_id` is a
LOCAL id, from `--local-db`, used ONLY for that lookup and for reading
`original_text` for the hallucination-guard check -- it is NEVER
written to Supabase or assumed to equal a production id), then
`(story_id, unit_index)` to check whether a unit already exists. If it
does, this script SKIPS it -- unlike migrate_illustrations_to_
supabase.py's UPSERT (insert-or-update), this is strictly
insert-or-skip, so a re-run can never silently overwrite content a
human reviewer may have since started editing.

Usage:
    python scripts/import_claude_enrichment_batch.py --json <export.json> --local-db <path.sqlite3>
    python scripts/import_claude_enrichment_batch.py --json <export.json> --local-db <path.sqlite3> --apply
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from illustration_engine.enrichment_pipeline import (
    _DIRECT_UNIT_REQUIRED_TEXT_FIELDS,
    _validate_common_fields,
    derive_enrichment_strategy,
)

UNIT_INDEX = 1  # every record this script has ever been used for is a single-unit-per-story draft


def load_local_story_context(local_db_path: str, story_id: int) -> dict | None:
    """Read-only: pulls the natural key (source code + canonical_key)
    and original_text for ONE local story, for natural-key resolution
    and hallucination-guard validation only. Never writes to this DB."""
    conn = sqlite3.connect(local_db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT st.original_text, st.canonical_key, s.code AS source_code
            FROM stories st JOIN sources s ON s.id = st.source_id
            WHERE st.id = ?
            """,
            (story_id,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


def _record_to_validator_payload(record: dict) -> dict:
    """Reshapes the flat export record's `tags` list back into the
    topics/tone/homiletic_functions fields `_validate_common_fields`
    expects -- pure reshaping, no content is invented or altered."""
    tags = record.get("tags") or []
    topics = [t["slug"] for t in tags if t.get("category") == "topic"]
    tones = [t["slug"] for t in tags if t.get("category") == "tone"]
    functions = [t["slug"] for t in tags if t.get("category") == "function"]
    return {
        "title_hu": record.get("title_hu"),
        "modern_hu_text": record.get("modern_hu_text"),
        "summary_hu": record.get("summary_hu"),
        "moral_hu": record.get("moral_hu"),
        "topics": topics,
        "tone": tones[0] if len(tones) == 1 else None,
        "homiletic_functions": functions,
        "narrative_status": record.get("narrative_status"),
        "narrative_status_confidence": record.get("narrative_status_confidence"),
    }


def validate_record(record: dict, *, local_db_path: str) -> tuple[list[str], list[str], dict | None]:
    """Returns (errors, warnings, local_story_context). errors is
    non-empty iff the record must be rejected -- fail-closed, no
    partial/guessed import of a record that fails any check here."""
    errors: list[str] = []
    warnings: list[str] = []

    story_id = record.get("story_id")
    if not isinstance(story_id, int) or isinstance(story_id, bool):
        errors.append("story_id must be an int")
        return errors, warnings, None

    ctx = load_local_story_context(local_db_path, story_id)
    if ctx is None:
        errors.append(f"local story_id={story_id} not found in {local_db_path}")
        return errors, warnings, None

    payload = _record_to_validator_payload(record)
    _validate_common_fields(
        payload, errors, warnings,
        source_text=ctx["original_text"] or "",
        required_text_fields=_DIRECT_UNIT_REQUIRED_TEXT_FIELDS,
    )

    strategy = derive_enrichment_strategy(len(ctx["original_text"] or ""))
    if record.get("derivation_type") != strategy.expected_derivation_type:
        errors.append(
            f"derivation_type must be {strategy.expected_derivation_type!r} for this story's "
            f"length ({len(ctx['original_text'] or '')} chars), got {record.get('derivation_type')!r}"
        )

    if record.get("status") != "needs_review":
        errors.append(f"status must be 'needs_review' for an importable draft, got {record.get('status')!r}")
    if record.get("human_reviewed_at") is not None:
        errors.append("human_reviewed_at must be null -- this importer never claims human review")

    return errors, warnings, ctx


def resolve_production_story_id(client, *, source_code: str, canonical_key: str) -> int | None:
    src = client.table("illustration_sources").select("id").eq("code", source_code).limit(1).execute()
    if not src.data:
        return None
    source_id = src.data[0]["id"]
    story = (
        client.table("illustration_stories").select("id")
        .eq("source_id", source_id).eq("canonical_key", canonical_key).limit(1).execute()
    )
    return story.data[0]["id"] if story.data else None


def unit_already_exists(client, *, story_id: int, unit_index: int) -> bool:
    existing = (
        client.table("illustration_units").select("id")
        .eq("story_id", story_id).eq("unit_index", unit_index).limit(1).execute()
    )
    return bool(existing.data)


def resolve_tag_ids(client, tags: list[dict]) -> tuple[list[int], list[str]]:
    """An unresolvable (category, slug) is a hard error -- never
    silently dropped, never a newly-invented tag row."""
    ids: list[int] = []
    errors: list[str] = []
    for t in tags:
        row = (
            client.table("illustration_tags").select("id")
            .eq("category", t["category"]).eq("slug", t["slug"]).limit(1).execute()
        )
        if row.data:
            ids.append(row.data[0]["id"])
        else:
            errors.append(f"unknown tag ({t['category']}, {t['slug']}) not in illustration_tags")
    return ids, errors


def import_record(client, record: dict, ctx: dict, *, apply: bool) -> str:
    """Returns "would_import" (dry-run), "imported", "duplicate_skipped",
    or "error:<reason>". NEVER updates an existing (story_id, unit_index)
    row -- always a no-op skip, never an overwrite."""
    story_id = resolve_production_story_id(client, source_code=ctx["source_code"], canonical_key=ctx["canonical_key"])
    if story_id is None:
        return (
            f"error:story not found in production for source={ctx['source_code']!r} "
            f"canonical_key={ctx['canonical_key']!r}"
        )

    if unit_already_exists(client, story_id=story_id, unit_index=UNIT_INDEX):
        return "duplicate_skipped"

    tag_ids, tag_errors = resolve_tag_ids(client, record.get("tags") or [])
    if tag_errors:
        return "error:" + "; ".join(tag_errors)

    if not apply:
        return "would_import"

    raw_warnings = record.get("enrichment_warnings_json")
    warnings_value = json.loads(raw_warnings) if raw_warnings else None

    unit_row = {
        "story_id": story_id, "unit_index": UNIT_INDEX,
        "derivation_type": record["derivation_type"],
        "title_hu": record["title_hu"], "modern_hu_text": record["modern_hu_text"],
        "summary_hu": record["summary_hu"], "moral_hu": record.get("moral_hu"),
        "narrative_status": record.get("narrative_status"),
        "narrative_status_confidence": record.get("narrative_status_confidence"),
        "status": "needs_review",
        "enrichment_model": record.get("enrichment_model"),
        "enrichment_prompt_version": record.get("enrichment_prompt_version"),
        "enrichment_generated_at": record.get("enrichment_generated_at"),
        "enrichment_warnings": warnings_value,
    }
    result = client.table("illustration_units").insert(unit_row).execute()
    new_unit_id = result.data[0]["id"]

    if tag_ids:
        tag_rows = [{"unit_id": new_unit_id, "tag_id": tid} for tid in tag_ids]
        client.table("illustration_unit_tags").insert(tag_rows).execute()

    return "imported"


def run_import(records: list[dict], *, local_db_path: str, client, apply: bool) -> dict[str, int]:
    """Pure(ish) orchestration over an already-constructed client --
    factored out so tests can pass a fake client instead of a real
    Supabase one. Returns the summary counts the caller prints/reports."""
    importable = duplicates = validation_errors = imported = 0

    for record in records:
        errors, _warnings, ctx = validate_record(record, local_db_path=local_db_path)
        if errors:
            validation_errors += 1
            print(f"[INVALID] story_id={record.get('story_id')} title={record.get('title_hu')!r}: {errors}")
            continue

        outcome = import_record(client, record, ctx, apply=apply)
        if outcome == "duplicate_skipped":
            duplicates += 1
            print(f"[DUPLICATE] story_id={record.get('story_id')} title={record.get('title_hu')!r} -- already in production, skipped")
        elif outcome == "would_import":
            importable += 1
            print(f"[WOULD IMPORT] story_id={record.get('story_id')} title={record.get('title_hu')!r}")
        elif outcome == "imported":
            importable += 1
            imported += 1
            print(f"[IMPORTED] story_id={record.get('story_id')} title={record.get('title_hu')!r}")
        else:
            validation_errors += 1
            print(f"[ERROR] story_id={record.get('story_id')} title={record.get('title_hu')!r}: {outcome}")

    return {
        "importable": importable, "duplicates": duplicates,
        "validation_errors": validation_errors, "imported": imported,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, help="Path to the Claude enrichment export JSON (flat list of records).")
    parser.add_argument("--local-db", required=True, help="Path to the local SQLite DB the export's story_id values refer to.")
    parser.add_argument("--apply", action="store_true", help="Actually write. Without this, dry-run only -- no Supabase write attempted.")
    args = parser.parse_args()

    with open(args.json, "r", encoding="utf-8") as f:
        records = json.load(f)

    from illustration_engine.supabase_review_client import get_service_role_client_for_migration

    client = get_service_role_client_for_migration()
    counts = run_import(records, local_db_path=args.local_db, client=client, apply=args.apply)

    print(f"\nIMPORTABLE_COUNT={counts['importable']}")
    print(f"DUPLICATE_COUNT={counts['duplicates']}")
    print(f"VALIDATION_ERRORS={counts['validation_errors']}")
    if args.apply:
        print(f"INSERTED_COUNT={counts['imported']}")
    else:
        print("\n--dry-run (default) -- no Supabase write attempted. Pass --apply to write.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
