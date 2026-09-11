"""Phase 2A — one-time backfill of translation_method/source_name/
source_version onto the FEW production Hungarian Greek lexicon records that
are still missing them (``bible_engine/data/lexicon_hu.json``).

Measured directly against the shipped file: 5,956 of the 5,959 records
ALREADY carry ``translation_method: "ai_assisted"``, ``source_name``, and
``source_version: "STEPBible GitHub raw"`` — this data existed in the file
all along; the actual gap (closed in this same phase) was that
``bible_engine.lexicon_hu.HungarianLexiconEntry`` never declared these
fields, so the loader silently dropped them and no runtime code could see
them. Only 3 records (G0025, G2889, G3779 — the hand-added illustrative
examples that appear throughout this codebase's test fixtures, predating the
bulk batch-import workflow) are missing the fields. This script backfills
only those, deriving ``source_name`` from the existing free-text ``source``
field (see ``_SOURCE_NAME_BY_TEXT``) and matching the ``source_version``
value every other record already uses, rather than inventing a new one. It
does NOT change ``lemma``, ``primary_gloss``, ``senses``, ``note``,
``review_status``, or ``source`` on any record.

Usage:
    python scripts/backfill_greek_lexicon_provenance.py [--apply]

Dry-run by default; --apply writes the file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PATH = ROOT / "bible_engine" / "data" / "lexicon_hu.json"

# Matches the value already present on all 5,956 other production records —
# see module docstring. Not re-derived from the fresh Phase 2A pin (commit
# ae39711d..., docs/greek_analysis_v2_phase2a_foundation.md) because these
# 3 records predate that pin and their actual historical source snapshot is
# unknown; recording the SAME label the rest of the file already uses is
# more honest than fabricating a distinct value for just these three.
DEFAULT_SOURCE_VERSION = "STEPBible GitHub raw"

_SOURCE_NAME_BY_TEXT = {
    "STEPBible TBESG alapján készített magyar munkaváltozat": "STEPBible TBESG",
    "STEPBible TBESG via TAGNT alias targets alapján készített magyar munkaváltozat": (
        "STEPBible TBESG via TAGNT alias targets"
    ),
    "STEPBible TBESG via final unresolved TAGNT audit alapján készített magyar munkaváltozat": (
        "STEPBible TBESG via final unresolved TAGNT audit"
    ),
}


def backfill(entries: list[dict]) -> tuple[list[dict], dict[str, int]]:
    stats = {"already_had_all_fields": 0, "backfilled": 0, "unrecognized_source_text": 0}
    updated: list[dict] = []
    for entry in entries:
        if {"translation_method", "source_name", "source_version"} <= set(entry):
            stats["already_had_all_fields"] += 1
            updated.append(entry)
            continue

        source_text = str(entry.get("source", ""))
        source_name = _SOURCE_NAME_BY_TEXT.get(source_text)
        if source_name is None:
            stats["unrecognized_source_text"] += 1
            source_name = source_text

        new_entry = dict(entry)
        new_entry.setdefault("translation_method", "ai_assisted")
        new_entry.setdefault("source_name", source_name)
        new_entry.setdefault("source_version", DEFAULT_SOURCE_VERSION)
        stats["backfilled"] += 1
        updated.append(new_entry)
    return updated, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    entries = json.loads(args.path.read_text(encoding="utf-8"))
    updated, stats = backfill(entries)

    print(f"total entries              : {len(entries)}")
    print(f"already had all 3 fields   : {stats['already_had_all_fields']}")
    print(f"backfilled                 : {stats['backfilled']}")
    print(f"unrecognized source text   : {stats['unrecognized_source_text']}")

    if args.apply:
        args.path.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nAPPLIED: {args.path} rewritten.")
    else:
        print("\nDry run — file NOT modified. Pass --apply to write.")
        if stats["unrecognized_source_text"]:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
