from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from bible_engine.hebrew_parser import HebrewToken
from bible_engine.hebrew_sqlite import DEFAULT_TBESH_DATABASE_PATH
from bible_engine.tbesh_parser import HebrewLexiconEntry


DEFAULT_HEBREW_ALIAS_PATH = Path(__file__).resolve().parent / "data" / "hebrew_strong_aliases.json"
_HEBREW_STRONG_RE = re.compile(r"^H\d{4}[A-Z]?$", re.IGNORECASE)


@dataclass(frozen=True)
class HebrewLexiconLookup:
    status: str
    entry: HebrewLexiconEntry | None
    matched_strong_id: str
    source_strong_id: str
    via_alias: bool = False
    alias_target: str = ""
    requested_strong_id: str = ""
    resolved_strong_id: str = ""
    resolution_type: str = "missing"
    alias_confidence: str = ""
    lexicon_entry: HebrewLexiconEntry | None = None
    source_component: str = ""


@dataclass(frozen=True)
class HebrewTokenLexiconLookup:
    core: HebrewLexiconLookup
    prefixes: tuple[HebrewLexiconLookup, ...]
    suffixes: tuple[HebrewLexiconLookup, ...]
    all_strong_ids: tuple[str, ...]


class HebrewLexiconRepository:
    def __init__(
        self,
        database_path: str | Path = DEFAULT_TBESH_DATABASE_PATH,
        alias_path: str | Path = DEFAULT_HEBREW_ALIAS_PATH,
    ) -> None:
        self.database_path = Path(database_path)
        self.alias_path = Path(alias_path)
        self.aliases = _load_aliases(self.alias_path)

    def lookup(self, strong_id: str, *, source_component: str = "") -> HebrewLexiconLookup:
        normalized = normalize_hebrew_strong_id(strong_id)
        direct = self._entry(normalized)
        if direct:
            # Phase 2A — a row may be present under this key while actually
            # being a CROSS-REFERENCE record ("in Aramaic of", "a Name of",
            # "combination of", ...) that only points at this lexeme. Databases
            # built before the two-pass importer fix contain 1056 such keys.
            # Returning it as "direct" is what made אֲשֶׁר (H0834A) display
            # כַּאֲשֶׁר's gloss, so label it instead of silently trusting it.
            if not direct.claims_strong_id(normalized):
                return _lookup(
                    status="cross_reference",
                    entry=direct,
                    matched_strong_id=normalized,
                    source_strong_id=normalized,
                    requested_strong_id=normalized,
                    resolved_strong_id=normalized,
                    resolution_type="cross_reference",
                    source_component=source_component,
                )
            return _lookup(
                status="direct",
                entry=direct,
                matched_strong_id=normalized,
                source_strong_id=normalized,
                requested_strong_id=normalized,
                resolved_strong_id=normalized,
                resolution_type="direct",
                source_component=source_component,
            )
        alias = self.aliases.get(normalized)
        target = alias["target_id"] if alias else ""
        if target and target != normalized:
            alias_entry = self._entry(target)
            if alias_entry:
                return _lookup(
                    status="alias",
                    entry=alias_entry,
                    matched_strong_id=target,
                    source_strong_id=normalized,
                    requested_strong_id=normalized,
                    resolved_strong_id=target,
                    resolution_type="alias",
                    via_alias=True,
                    alias_target=target,
                    alias_confidence=alias["confidence"],
                    source_component=source_component,
                )
            return _lookup(
                status="partial_lexicon_match",
                entry=None,
                matched_strong_id=target,
                source_strong_id=normalized,
                requested_strong_id=normalized,
                resolved_strong_id=target,
                resolution_type="partial",
                via_alias=True,
                alias_target=target,
                alias_confidence=alias["confidence"],
                source_component=source_component,
            )
        return _lookup(
            status="lexicon_not_found",
            entry=None,
            matched_strong_id=normalized,
            source_strong_id=normalized,
            requested_strong_id=normalized,
            resolved_strong_id="",
            resolution_type="missing",
            source_component=source_component,
        )

    def lookup_token(self, token: HebrewToken) -> HebrewTokenLexiconLookup:
        prefixes = tuple(
            self.lookup(component.strong_id, source_component="prefix")
            for component in token.prefix_components
        )
        suffixes = tuple(
            self.lookup(component.strong_id, source_component="suffix")
            for component in token.suffix_components
        )
        if token.core_component:
            core = self.lookup(token.core_component.strong_id, source_component="core")
        else:
            core = _lookup(
                status="lexicon_not_found",
                entry=None,
                matched_strong_id="",
                source_strong_id="",
                requested_strong_id="",
                resolved_strong_id="",
                resolution_type="missing",
                source_component="core",
            )
        return HebrewTokenLexiconLookup(
            core=core,
            prefixes=prefixes,
            suffixes=suffixes,
            all_strong_ids=token.strong_ids,
        )

    def _entry(self, strong_id: str) -> HebrewLexiconEntry | None:
        if not self.database_path.exists():
            return None
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT estrong, dstrong, ustrong, hebrew, transliteration, morph, gloss, meaning, source_name
                FROM lexicon_entries
                WHERE strong_id = ?
                """,
                (strong_id,),
            ).fetchone()
        if row is None:
            return None
        return HebrewLexiconEntry(
            estrong=row[0] or "",
            dstrong=row[1] or "",
            ustrong=row[2] or "",
            hebrew=row[3] or "",
            transliteration=row[4] or "",
            morph=row[5] or "",
            gloss=row[6] or "",
            meaning=row[7] or "",
            source_name=row[8] or "STEPBible TBESH",
        )


def normalize_hebrew_strong_id(value: str) -> str:
    candidate = (value or "").strip().upper()
    if not _HEBREW_STRONG_RE.match(candidate):
        raise ValueError(f"Invalid Hebrew Strong/STEP identifier: {value!r}")
    return candidate


def _load_aliases(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    aliases: dict[str, dict[str, str]] = {}
    if isinstance(data, dict):
        items = [
            {"source_id": source, "target_id": target, "confidence": "high"}
            for source, target in data.items()
        ]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("Hebrew Strong alias JSON must be an object map or a list.")

    for item in items:
        source = normalize_hebrew_strong_id(item["source_id"])
        target = normalize_hebrew_strong_id(item["target_id"])
        if source == target:
            raise ValueError(f"Self-referential Hebrew Strong alias: {source}")
        if source in aliases:
            raise ValueError(f"Duplicate Hebrew Strong alias source: {source}")
        aliases[source] = {"target_id": target, "confidence": item.get("confidence", "")}
    chained = [source for source, item in aliases.items() if item["target_id"] in aliases]
    if chained:
        raise ValueError(f"Chained or cyclic Hebrew Strong aliases: {', '.join(sorted(chained))}")
    return aliases


def _lookup(
    *,
    status: str,
    entry: HebrewLexiconEntry | None,
    matched_strong_id: str,
    source_strong_id: str,
    requested_strong_id: str,
    resolved_strong_id: str,
    resolution_type: str,
    via_alias: bool = False,
    alias_target: str = "",
    alias_confidence: str = "",
    source_component: str = "",
) -> HebrewLexiconLookup:
    return HebrewLexiconLookup(
        status=status,
        entry=entry,
        matched_strong_id=matched_strong_id,
        source_strong_id=source_strong_id,
        via_alias=via_alias,
        alias_target=alias_target,
        requested_strong_id=requested_strong_id,
        resolved_strong_id=resolved_strong_id,
        resolution_type=resolution_type,
        alias_confidence=alias_confidence,
        lexicon_entry=entry,
        source_component=source_component,
    )
