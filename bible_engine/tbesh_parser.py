from __future__ import annotations

import csv
import re
from dataclasses import dataclass


_HEBREW_STRONG_RE = re.compile(r"H\d{4}[A-Z]?", re.IGNORECASE)

TBESH_HEADERS = (
    "eStrong#",
    "dStrong",
    "uStrong",
    "Hebrew",
    "Transliteration",
    "Morph",
    "Gloss",
    "Meaning",
)


@dataclass(frozen=True)
class HebrewLexiconEntry:
    estrong: str
    dstrong: str
    ustrong: str
    hebrew: str
    transliteration: str
    morph: str
    gloss: str
    meaning: str
    source_name: str = "STEPBible TBESH"

    @property
    def strong_ids(self) -> tuple[str, ...]:
        """Every Strong id mentioned anywhere on the record.

        Kept for callers that need the full reference closure (coverage audits,
        alias candidate generation). It deliberately mixes identity with
        cross-reference, so it must NOT be used to key the lexicon — see
        ``identity_strong_ids``.
        """
        strong_ids: list[str] = []
        for item in (self.estrong, self.dstrong, self.ustrong):
            strong_ids.extend(match.group(0).upper() for match in _HEBREW_STRONG_RE.finditer(item or ""))
        return tuple(dict.fromkeys(strong_ids))

    @property
    def identity_strong_ids(self) -> tuple[str, ...]:
        """Strong ids this record actually *is* (eStrong + dStrong).

        Phase 2A. TBESH's ``uStrong`` column is a CROSS-REFERENCE to the base
        lexeme a record is derived from — "in Aramaic of", "a Name of",
        "a Spelling of", "a Meaning of", "combination of" — never the record's
        own identity. Indexing by it let derived records claim, and (via
        INSERT OR REPLACE) destroy, the entry of the word they merely point at.

        Measured on the shipped TBESH database: 1056 of 12521 keys were held by
        a record that is not that lexeme, covering 292282 of 540437 corpus token
        references. Examples: H0853 (the object marker אֵת) resolved to the
        Aramaic יָת; H3068G (the divine name) resolved to שָׁלוֹם "Peace";
        H0834A (the relative particle אֲשֶׁר) resolved to כַּאֲשֶׁר "as which".
        """
        strong_ids: list[str] = []
        for item in (self.estrong, self.dstrong):
            strong_ids.extend(match.group(0).upper() for match in _HEBREW_STRONG_RE.finditer(item or ""))
        return tuple(dict.fromkeys(strong_ids))

    @property
    def reference_strong_ids(self) -> tuple[str, ...]:
        """Strong ids this record only points at (uStrong minus own identity)."""
        identity = set(self.identity_strong_ids)
        return tuple(
            strong_id
            for strong_id in dict.fromkeys(
                match.group(0).upper() for match in _HEBREW_STRONG_RE.finditer(self.ustrong or "")
            )
            if strong_id not in identity
        )

    def claims_strong_id(self, strong_id: str) -> bool:
        """True when this record is the lexeme for ``strong_id`` (not a pointer)."""
        return (strong_id or "").upper() in set(self.identity_strong_ids)


def parse_tbesh_row(row: str) -> HebrewLexiconEntry:
    fields = next(csv.reader([row.rstrip("\n")], delimiter="\t"))
    if len(fields) < len(TBESH_HEADERS):
        raise ValueError(f"Invalid TBESH row: expected {len(TBESH_HEADERS)} columns")
    return HebrewLexiconEntry(
        estrong=fields[0].strip(),
        dstrong=fields[1].strip(),
        ustrong=fields[2].strip(),
        hebrew=fields[3].strip(),
        transliteration=fields[4].strip(),
        morph=fields[5].strip(),
        gloss=fields[6].strip(),
        meaning=fields[7].strip(),
    )


def parse_tbesh_rows(text: str) -> list[HebrewLexiconEntry]:
    entries: list[HebrewLexiconEntry] = []
    data_started = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("eStrong#"):
            data_started = True
            continue
        if not data_started:
            continue
        if line.startswith("$") or line.startswith("="):
            continue
        try:
            entries.append(parse_tbesh_row(line))
        except ValueError:
            continue
    return entries
