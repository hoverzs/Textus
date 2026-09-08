"""One-shot Phase 2B discovery script: compare the current decoder's output
against authoritative TEHMC for every code segment in the shipped corpus.

Not part of the production/test path — this is how the Phase 2B corrections
in hebrew_morphology.py were derived and verified. Kept for future TEHMC
version bumps.
"""

from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_morphology import _split_morphology_components, decode_hebrew_morphology
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH
from scripts.parse_tehmc import parse_tehmc


def main() -> None:
    tehmc = parse_tehmc(ROOT / "data" / "stepbible_sources" / "TEHMC.txt")
    connection = sqlite3.connect(DEFAULT_TAHOT_DATABASE_PATH)
    codes = Counter(row[0] or "" for row in connection.execute("SELECT morphology_code FROM tokens"))

    segment_counts: Counter[str] = Counter()
    for code, count in codes.items():
        for _raw, normalized in _split_morphology_components(code):
            segment_counts[normalized] += count

    _FORM_ALIASES = {
        "Infinitive Construct": "Infinitive",
        "Infinitive Absolute": "Infinitive",
        "Passive Participle": "Participle passive",
        # TEHMC models Jussive/Cohortative/Conjunction-Imperfect as
        # Form=Imperfect + a separate Mood/spelling field, not as distinct
        # top-level Forms. This decoder promotes them to distinct Form NAMES
        # to match traditional Hebrew-grammar pedagogy (the Hungarian terms
        # "jussivus"/"cohortativus" name their own paradigm in every seminary
        # textbook) — verified against TEHMC's own Mood field, not a
        # disagreement with it. See docs/hebrew_analysis_v2_phase2b.md.
        "Jussive": "Imperfect",
        "Cohortative": "Imperfect",
        "Conjunction Imperfect": "Conjunction+Imperfect",
    }
    # Documented TEHMC internal inconsistencies (not decoder bugs) — see
    # docs/hebrew_analysis_v2_phase2b.md "TEHMC anomalies". Kept as an
    # explicit allow-list so a real future regression cannot hide behind them.
    _KNOWN_TEHMC_ANOMALIES = {
        "AVvi3mp",  # TEHMC form=Perfect; corpus gloss ("they will be finished") and every other "i"-form code say Imperfect.
        "AVPp3ms", "AVPp3mp", "AVPj3mp",  # TEHMC stem=Pual; contradicts TEHMC's own AVPi* = Hitpeel for the identical ת-prefixed (אֶשְׁתַּ/יִשְׁתַּ) surface pattern.
    }

    mismatches: dict[str, dict[str, object]] = {}
    known_anomalies: dict[str, dict[str, object]] = {}
    not_in_tehmc: Counter[str] = Counter()
    for segment, count in segment_counts.items():
        # Suffix codes are bare in this corpus (e.g. "Sp3ms") but TEHMC lists
        # them per-language (HSp3ms/ASp3ms) — verified identical, so try the
        # language-prefixed form as a fallback rather than reporting a gap.
        tehmc_entry = tehmc.get(segment)
        if tehmc_entry is None and segment.startswith("S"):
            tehmc_entry = tehmc.get("H" + segment) or tehmc.get("A" + segment)
        if tehmc_entry is None:
            not_in_tehmc[segment] = count
            continue
        decoded = decode_hebrew_morphology(segment)
        problems: list[str] = []

        if tehmc_entry.function == "Verb":
            current_stem = decoded.verb_stem
            current_form = _FORM_ALIASES.get(decoded.verb_conjugation, decoded.verb_conjugation)
            tehmc_stem = tehmc_entry.stem
            tehmc_form = tehmc_entry.form
            if tehmc_stem and current_stem != tehmc_stem:
                problems.append(f"stem: current={current_stem!r} tehmc={tehmc_stem!r}")
            if tehmc_form and current_form != tehmc_form:
                problems.append(f"form: current={current_form!r} tehmc={tehmc_form!r}")
        elif tehmc_entry.function == "Particle":
            current_type = decoded.particle_type
            if tehmc_entry.form and current_type != tehmc_entry.form:
                problems.append(f"particle_type: current={current_type!r} tehmc={tehmc_entry.form!r}")
        elif tehmc_entry.function == "Preposition" and len(segment) >= 3:
            current_type = decoded.preposition_type
            if tehmc_entry.form and current_type != tehmc_entry.form:
                problems.append(f"preposition_type: current={current_type!r} tehmc={tehmc_entry.form!r}")

        if problems:
            target = known_anomalies if segment in _KNOWN_TEHMC_ANOMALIES else mismatches
            target[segment] = {"count": count, "problems": problems, "tehmc": tehmc_entry}

    print(f"total distinct code segments in corpus: {len(segment_counts)}")
    print(f"segments not found in TEHMC (brief+full, {len(tehmc)} entries): {len(not_in_tehmc)}")
    print(f"  affected tokens: {sum(not_in_tehmc.values())}")
    for seg, count in not_in_tehmc.most_common(30):
        print(f"    {seg:<12} {count}")
    print()
    print(f"UNEXPLAINED stem/form/particle/preposition mismatches vs TEHMC: {len(mismatches)}")
    total_mismatch_tokens = sum(m["count"] for m in mismatches.values())
    print(f"  affected tokens: {total_mismatch_tokens}")
    for seg, info in sorted(mismatches.items(), key=lambda kv: -kv[1]["count"]):
        print(f"    {seg:<14} n={info['count']:>6}  {info['problems']}")
    print()
    print(f"documented TEHMC-internal anomalies (allow-listed, corpus-resolved): {len(known_anomalies)}")
    for seg, info in sorted(known_anomalies.items(), key=lambda kv: -kv[1]["count"]):
        print(f"    {seg:<14} n={info['count']:>6}  {info['problems']}")


if __name__ == "__main__":
    main()
