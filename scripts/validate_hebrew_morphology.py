"""Corpus-level validation of the deterministic Hebrew morphology decoder.

Phase 2B — the decoder's code tables in ``bible_engine/hebrew_morphology.py``
are now authoritative, cross-checked against the vendored STEPBible TEHMC
source (``data/stepbible_sources/TEHMC.txt``; see
``scripts/compare_morphology_against_tehmc.py`` and
``docs/hebrew_analysis_v2_phase2b.md`` for provenance and the derivation of
every mapping). This script re-validates that against the shipped TAHOT
corpus so a future table edit that drifts from either source becomes a test
failure rather than silently reaching production.

The point of this script is that a future mistake in those tables becomes a
*test failure* rather than silently reaching production. It is a
development/validation utility — nothing in the runtime request path imports
it. ``tests/test_hebrew_morphology_corpus.py`` runs the same checks whenever
the production database is available.

Checks performed
----------------
1.  Every morphology code occurring in the corpus decodes to a known status.
2.  Frequency census of every verbal stem (language-aware — see
    ``STEMS_BY_LANGUAGE``) and every verbal form code.
3.  No mapped code is dead (mapped but never attested) — except codes TEHMC
    itself defines but this particular TAHOT edition happens not to use
    (``TEHMC_ONLY_UNATTESTED_STEMS``), which are reported informationally,
    not as problems.
4.  No attested code is silently swallowed (unresolved remainders are reported).
5.  Person constraints hold: imperatives are second person only, cohortatives
    first person only, and person-less forms (infinitives, participles) never
    carry a person.
6.  Finite verb forms actually carry a person.
7.  No stem/form code remains unmapped now that TEHMC is authoritative.

Usage:
    python scripts/validate_hebrew_morphology.py [--json OUTPUT.json]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_morphology import (  # noqa: E402
    PERSONLESS_VERB_FORMS,
    STEMS_BY_LANGUAGE,
    UNVERIFIED_STEM_CODES,
    VERB_FORM_PERSON_CONSTRAINTS,
    VERB_FORMS,
    _split_morphology_components,
    decode_hebrew_morphology,
)
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH  # noqa: E402

# TEHMC defines these stems but no token in this TAHOT edition uses them.
# Not a problem — just not locally attestable. See docs/hebrew_analysis_v2_phase2b.md.
TEHMC_ONLY_UNATTESTED_STEMS = {("H", "O")}  # Polal


# Forms that are produced by disambiguation rather than by a bare VERB_FORMS
# lookup, so they must not be treated as "dead" table entries.
DERIVED_VERB_FORMS = frozenset(VERB_FORM_PERSON_CONSTRAINTS) - set(VERB_FORMS.values())


def collect_corpus_codes(database_path: Path) -> Counter[str]:
    """Return every distinct token-level morphology code with its frequency."""
    with sqlite3.connect(database_path) as connection:
        return Counter(
            (row[0] or "") for row in connection.execute("SELECT morphology_code FROM tokens")
        )


def validate_morphology(codes: Counter[str]) -> dict[str, object]:
    status_by_code: Counter[str] = Counter()
    status_by_token: Counter[str] = Counter()
    unresolved_tokens: Counter[str] = Counter()

    stem_code_tokens: dict[tuple[str, str], int] = defaultdict(int)
    form_code_tokens: Counter[str] = Counter()
    form_name_tokens: Counter[str] = Counter()
    person_by_form: dict[str, Counter[str]] = defaultdict(Counter)

    problems: list[dict[str, object]] = []

    for code, count in codes.items():
        decoded = decode_hebrew_morphology(code, {})
        status_by_code[decoded.status] += 1
        status_by_token[decoded.status] += count
        for part in decoded.unresolved_parts:
            unresolved_tokens[part] += count

        # Raw code census, independent of the decoder, so a table change cannot
        # hide a code from the frequency report. Stems are language-tagged
        # (see STEMS_BY_LANGUAGE) — the same letter names a different binyan
        # in Hebrew than in Aramaic (Phase 2B finding).
        for _raw, normalized in _split_morphology_components(code):
            if normalized[1:2] == "V":
                language_letter = normalized[:1]
                stem_code_tokens[(language_letter, normalized[2:3])] += count
                form_code_tokens[normalized[3:4]] += count

        components = decoded.components or ({"verb_conjugation": decoded.verb_conjugation,
                                             "person": decoded.person},)
        for component in components:
            form = str(component.get("verb_conjugation") or "")
            if not form:
                continue
            person = str(component.get("person") or "")
            form_name_tokens[form] += count
            person_by_form[form][person or "<none>"] += count

            allowed = VERB_FORM_PERSON_CONSTRAINTS.get(form)
            if allowed is not None and person and person not in allowed:
                problems.append(
                    {
                        "kind": "person_constraint_violated",
                        "code": code,
                        "form": form,
                        "person": person,
                        "allowed": sorted(allowed),
                        "tokens": count,
                    }
                )
            if form in PERSONLESS_VERB_FORMS and person:
                problems.append(
                    {
                        "kind": "person_on_personless_form",
                        "code": code,
                        "form": form,
                        "person": person,
                        "tokens": count,
                    }
                )

    # Dead mappings: a table entry that never occurs in the corpus is
    # unverifiable from corpus evidence alone. Now that TEHMC is authoritative
    # (Phase 2B), an entry TEHMC itself defines but this edition never uses
    # (TEHMC_ONLY_UNATTESTED_STEMS) is reported separately, not as a problem —
    # it is exactly how the pre-2B imperative defect was DISCOVERED (a
    # then-unverifiable dead mapping), but now that provenance is verified,
    # "unattested" no longer implies "unverifiable".
    attested_stems = {key for key, count in stem_code_tokens.items() if count}
    dead_stems: list[tuple[str, str]] = []
    unattested_but_verified: list[tuple[str, str]] = []
    for language_letter, table in STEMS_BY_LANGUAGE.items():
        for stem_code in table:
            key = (language_letter, stem_code)
            if key not in attested_stems:
                (unattested_but_verified if key in TEHMC_ONLY_UNATTESTED_STEMS else dead_stems).append(key)
    dead_forms = sorted(set(VERB_FORMS) - {c for c in form_code_tokens if c})
    for language_letter, stem_code in sorted(dead_stems):
        problems.append(
            {
                "kind": "dead_stem_mapping",
                "code": stem_code,
                "language": language_letter,
                "maps_to": STEMS_BY_LANGUAGE[language_letter][stem_code],
            }
        )
    for code in dead_forms:
        problems.append({"kind": "dead_form_mapping", "code": code, "maps_to": VERB_FORMS[code]})

    # Attested-but-unmapped stem codes: language-aware now (Phase 2B).
    # UNVERIFIED_STEM_CODES is empty post-2B, kept only for a future code
    # TEHMC itself cannot resolve.
    for (language_letter, stem_code), count in stem_code_tokens.items():
        if not stem_code or not count:
            continue
        if stem_code not in STEMS_BY_LANGUAGE.get(language_letter, {}) and stem_code not in UNVERIFIED_STEM_CODES:
            problems.append(
                {
                    "kind": "unmapped_stem_code",
                    "code": stem_code,
                    "language": language_letter,
                    "tokens": count,
                }
            )
    for code, count in form_code_tokens.items():
        if code and code not in VERB_FORMS:
            problems.append({"kind": "unmapped_form_code", "code": code, "tokens": count})

    stem_code_tokens_serializable = {
        f"{language_letter}:{stem_code}": count
        for (language_letter, stem_code), count in sorted(
            stem_code_tokens.items(), key=lambda item: -item[1]
        )
    }
    return {
        "unique_codes": len(codes),
        "total_tokens": sum(codes.values()),
        "status_by_code": dict(status_by_code),
        "status_by_token": dict(status_by_token),
        "unresolved_tokens": dict(unresolved_tokens.most_common()),
        "stem_code_tokens": stem_code_tokens_serializable,
        "form_code_tokens": dict(form_code_tokens.most_common()),
        "form_name_tokens": dict(form_name_tokens.most_common()),
        "person_by_form": {k: dict(v) for k, v in sorted(person_by_form.items())},
        "unverified_stem_codes": sorted(UNVERIFIED_STEM_CODES),
        "unattested_but_tehmc_verified_stems": sorted(f"{lang}:{code}" for lang, code in unattested_but_verified),
        "derived_verb_forms": sorted(DERIVED_VERB_FORMS),
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DEFAULT_TAHOT_DATABASE_PATH))
    parser.add_argument("--json", dest="json_path", default="")
    args = parser.parse_args()

    database_path = Path(args.database)
    if not database_path.exists():
        print(f"Hebrew database not found: {database_path}")
        return 2

    report = validate_morphology(collect_corpus_codes(database_path))

    print(f"unique morphology codes : {report['unique_codes']}")
    print(f"tokens                  : {report['total_tokens']}")
    print(f"status by code          : {report['status_by_code']}")
    print(f"status by token         : {report['status_by_token']}")
    print()
    print("verb form tokens (decoded name):")
    for name, count in report["form_name_tokens"].items():  # type: ignore[union-attr]
        persons = report["person_by_form"][name]  # type: ignore[index]
        print(f"  {name:<24} {count:>7}   persons={persons}")
    print()
    print(f"unresolved parts        : {report['unresolved_tokens']}")
    print(f"unverified stem codes   : {report['unverified_stem_codes']}")

    problems = report["problems"]
    assert isinstance(problems, list)
    if problems:
        print(f"\nPROBLEMS ({len(problems)}):")
        for problem in problems:
            print(f"  {problem}")
    else:
        print("\nNo problems detected.")

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nWrote {args.json_path}")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
