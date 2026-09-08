"""Parse the authoritative STEPBible TEHMC file into a code -> fields table.

Phase 2B. TEHMC ("Translators Expansion of Hebrew Morphology Codes") is the
STEPBible source that authoritatively defines what every Hebrew/Aramaic TAHOT
morphology code means. Phase 2A had to infer mappings from the corpus alone
because this file was not available; Phase 2B obtains it (see
docs/hebrew_analysis_v2_phase2b.md for provenance: exact upstream path,
commit SHA, checksum) and this module turns it into a structured table other
scripts can validate against.

Format (both the BRIEF lexical codes and FULL morphology codes sections use
the same block shape):

    <CODE>\tFunction=<f> [; Stem=<s> (...)] [; Form=<form> (...)] [; Person=<p>; Gender=<g>; Number=<n>] [; State=<st>]
    \t"<short label>"
    \t<long explanation>
    \t<usage example>
    <blank line>

This module extracts, per code, the structured key=value pairs from the first
line only — the free-text explanation lines are not parsed, since every
grammatical fact Textus needs (function, stem, form, person, gender, number,
state) is already present in that structured line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_CODE_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+]*)\t(.+)$")
# Only break on ";" immediately followed by one of TEHMC's known top-level
# field names — a bare "\w+=" is not enough, because the "(hence ...)"
# annotation after Stem/Form values itself contains "Voice=" / "Action="
# separated by ";", which would otherwise be mistaken for a new top-level field.
_KNOWN_FIELDS = "Function|Stem|Form|Person|Gender|Number|State"
_FIELD_RE = re.compile(rf"(\w+)=([^;]*(?:;(?!\s*(?:{_KNOWN_FIELDS})=)[^;]*)*)")


@dataclass(frozen=True)
class TehmcEntry:
    code: str
    function: str = ""
    stem: str = ""
    form: str = ""
    person: str = ""
    gender: str = ""
    number: str = ""
    state: str = ""
    raw_fields: str = ""


def _strip_parenthetical(value: str) -> str:
    """Drop a trailing "(hence ...)" annotation, keeping the bare term."""
    return re.sub(r"\s*\(.*\)\s*$", "", value).strip()


def parse_field_line(fields_text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for match in _FIELD_RE.finditer(fields_text):
        key = match.group(1).strip().lower()
        value = _strip_parenthetical(match.group(2).strip())
        parsed[key] = value
    return parsed


def parse_tehmc(source_path: str | Path) -> dict[str, TehmcEntry]:
    """Return every TEHMC code (brief lexical + full morphology) as an entry.

    Later occurrences of the same code overwrite earlier ones — TEHMC lists a
    code only once per section in practice, but this keeps the parser
    forgiving rather than raising on an unexpected duplicate.
    """
    entries: dict[str, TehmcEntry] = {}
    text = Path(source_path).read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        match = _CODE_LINE_RE.match(line)
        if not match:
            continue
        code, fields_text = match.group(1), match.group(2)
        if "=" not in fields_text:
            continue
        parsed = parse_field_line(fields_text)
        entries[code] = TehmcEntry(
            code=code,
            function=parsed.get("function", ""),
            stem=parsed.get("stem", ""),
            form=parsed.get("form", ""),
            person=parsed.get("person", ""),
            gender=parsed.get("gender", ""),
            number=parsed.get("number", ""),
            state=parsed.get("state", ""),
            raw_fields=fields_text,
        )
    return entries


def stem_letter_map(entries: dict[str, TehmcEntry]) -> dict[str, dict[str, str]]:
    """Return {language_prefix: {stem_letter: stem_name}} from full verb codes.

    Full verb codes look like ``HVqp3ms`` (language H/A, function V, stem
    letter, form letter, then person/gender/number). Stem letters are
    genuinely language-dependent in TEHMC (e.g. Hebrew ``u`` = Hothpaal,
    Aramaic ``u`` = Hitpael), so the map is keyed by language too.
    """
    result: dict[str, dict[str, str]] = {"H": {}, "A": {}}
    for code, entry in entries.items():
        if len(code) < 3 or code[1:2] != "V" or not entry.stem:
            continue
        language = code[:1]
        if language not in result:
            continue
        stem_letter = code[2:3]
        result[language].setdefault(stem_letter, entry.stem)
    return result


def form_letter_map(entries: dict[str, TehmcEntry]) -> dict[str, set[str]]:
    """Return {form_letter: {form_names_seen}} from full verb codes."""
    result: dict[str, set[str]] = {}
    for code, entry in entries.items():
        if len(code) < 4 or code[1:2] != "V" or not entry.form:
            continue
        form_letter = code[3:4]
        result.setdefault(form_letter, set()).add(entry.form)
    return result


def particle_letter_map(entries: dict[str, TehmcEntry]) -> dict[str, dict[str, str]]:
    """Return {language_prefix: {particle_letter: form_name}} for T-codes."""
    result: dict[str, dict[str, str]] = {"H": {}, "A": {}}
    for code, entry in entries.items():
        if len(code) < 3 or code[1:2] != "T" or not entry.form:
            continue
        language = code[:1]
        if language not in result:
            continue
        letter = code[2:3]
        result[language].setdefault(letter, entry.form)
    return result


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "data/stepbible_sources/TEHMC.txt"
    entries = parse_tehmc(path)
    print(f"parsed {len(entries)} TEHMC codes")
    stems = stem_letter_map(entries)
    print("Hebrew stem letters:", stems["H"])
    print("Aramaic stem letters:", stems["A"])
    print("Form letters:", form_letter_map(entries))
    particles = particle_letter_map(entries)
    print("Hebrew particle letters:", particles["H"])
    print("Aramaic particle letters:", particles["A"])
