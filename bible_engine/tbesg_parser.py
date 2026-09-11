from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


_FIELD_COUNT = 8
_GREEK_STRONG_RE = re.compile(r"^G(?P<number>\d{1,5})(?P<suffix>[A-Z]?)$")
_MAX_GREEK_STRONG_NUMBER = 21502

# Unanchored scan for a Greek Strong id embedded anywhere in a raw TBESG
# text field (dStrong/uStrong carry annotation prose around the id, e.g.
# "G0001G =" or "G0002 = the Greek of") — mirrors the Hebrew TBESH
# ``_HEBREW_STRONG_RE`` scan used for the same eStrong/dStrong-vs-uStrong
# identity/cross-reference split.
_GREEK_STRONG_SCAN_RE = re.compile(r"G\d{4,5}[A-Z]?")


@dataclass(frozen=True)
class GreekLexiconEntry:
    strong_id: str
    dstrong_id: str | None
    ustrong_id: str | None
    greek: str
    transliteration: str | None
    morph: str | None
    gloss: str | None
    meaning_raw: str | None

    @property
    def canonical_strong_id(self) -> str:
        """The disambiguated identity this record's OWN row must be keyed
        under — never the bare eStrong alone when a more specific sense
        exists.

        TBESG's ``eStrong`` (``strong_id``) is a BASE number shared by every
        disambiguated sense of a word (e.g. ``G0001`` for both "Alpha" and
        the interjection "ah!"). The actual disambiguated identity — the
        one that matches the Strong id format TAGNT tokens and the
        Hungarian lexicon (``lexicon_hu.json``) actually key on — is
        embedded as the LEADING id in the ``dStrong`` field (e.g.
        ``"G0001G ="``, ``"G0007H = the Greek of"``). Keying the lexicon
        table by bare eStrong made ``UNIQUE(strong_id)`` collide across
        every sense of a shared base number: only the first-encountered
        sense survived, and every suffixed lookup (which is the ONLY kind
        real callers ever perform) missed entirely. Verified against the
        full vendored TBESG source: this derivation produces a distinct,
        collision-free key for all 11,035 rows.
        """
        for candidate in _GREEK_STRONG_SCAN_RE.findall(self.dstrong_id or ""):
            if candidate != self.strong_id:
                return candidate
        return self.strong_id

    @property
    def reference_strong_ids(self) -> tuple[str, ...]:
        """Strong ids this record only POINTS AT (uStrong), never its own
        identity. ``uStrong`` sometimes repeats the canonical id and
        sometimes cross-references an entirely different lexeme (including
        a Hebrew Strong id, for Greek transliterations of Hebrew names) —
        it must never be used to key this record's own row. Kept for
        parity with the Hebrew ``HebrewLexiconEntry.reference_strong_ids``
        cross-reference/hijack-prevention pattern, and to give a future
        importer an explicit place to look up "does another record already
        own this id" before ever writing under it."""
        canonical = {self.strong_id, self.canonical_strong_id}
        return tuple(
            dict.fromkeys(
                candidate
                for candidate in _GREEK_STRONG_SCAN_RE.findall(self.ustrong_id or "")
                if candidate not in canonical
            )
        )

    def claims_strong_id(self, strong_id: str) -> bool:
        """True when this record IS the lexeme for ``strong_id`` (not a
        cross-reference pointer to it)."""
        normalized = (strong_id or "").strip().upper()
        return normalized in {self.strong_id, self.canonical_strong_id}


def parse_tbesg_line(line: str) -> GreekLexiconEntry:
    fields = line.rstrip("\r\n").split("\t")
    if len(fields) != _FIELD_COUNT:
        raise ValueError(
            f"Invalid TBESG record: expected {_FIELD_COUNT} tab-separated fields, "
            f"got {len(fields)}."
        )

    (
        strong_id,
        dstrong_id,
        ustrong_id,
        greek,
        transliteration,
        morph,
        gloss,
        meaning_raw,
    ) = fields

    if not strong_id.strip():
        raise ValueError("Invalid TBESG record: missing eStrong value.")
    return GreekLexiconEntry(
        strong_id=normalize_greek_strong_id(strong_id),
        dstrong_id=_optional(dstrong_id),
        ustrong_id=_optional(ustrong_id),
        greek=unicodedata.normalize("NFC", greek.strip()),
        transliteration=_optional(transliteration),
        morph=_optional(morph),
        gloss=_optional(gloss),
        meaning_raw=_optional_raw(meaning_raw),
    )


def normalize_greek_strong_id(value: str) -> str:
    raw = (value or "").strip().upper()
    if raw.startswith("H"):
        raise ValueError(f"Invalid Greek Strong identifier: Hebrew id is not supported: {value!r}.")

    match = _GREEK_STRONG_RE.fullmatch(raw)
    if not match:
        raise ValueError(f"Invalid Greek Strong identifier: {value!r}.")

    number = int(match.group("number"))
    if number < 1 or number > _MAX_GREEK_STRONG_NUMBER:
        raise ValueError(f"Invalid Greek Strong identifier range: {value!r}.")

    width = 4 if number < 10000 else len(str(number))
    return f"G{number:0{width}d}{match.group('suffix')}"


def _optional(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _optional_raw(value: str) -> str | None:
    return value if value else None
