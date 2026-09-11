from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from bible_engine.tbesg_parser import normalize_greek_strong_id


VALID_REVIEW_STATUSES = frozenset({"draft", "reviewed"})
VALID_TRANSLATION_METHODS = frozenset({"ai_assisted", "human"})
DATA_DIR = Path(__file__).parent / "data"
DEFAULT_HUNGARIAN_LEXICON_PATH = DATA_DIR / "lexicon_hu.json"
SAMPLE_HUNGARIAN_LEXICON_PATH = DATA_DIR / "lexicon_hu_sample.json"
DEFAULT_STRONG_ALIASES_PATH = DATA_DIR / "strong_aliases.json"


@dataclass(frozen=True)
class HungarianLexiconEntry:
    strong_id: str
    lemma: str
    primary_gloss: str
    senses: tuple[str, ...]
    note: str | None
    source: str
    review_status: str
    # Phase 2A — provenance fields. Optional/defaulted so the minimal
    # illustrative sample lexicon (``lexicon_hu_sample.json``) need not
    # carry them; the production lexicon (``lexicon_hu.json``) has them on
    # every record after the Phase 2A backfill migration
    # (``scripts/backfill_greek_lexicon_provenance.py``).
    translation_method: str = "ai_assisted"
    source_name: str = ""
    source_version: str = ""


@dataclass(frozen=True)
class StrongAlias:
    source_strong_id: str
    target_strong_id: str
    confidence: float
    evidence: str
    token_frequency: int


@dataclass(frozen=True)
class HungarianLexiconResolution:
    entry: HungarianLexiconEntry
    requested_strong_id: str
    resolved_strong_id: str
    alias: StrongAlias | None = None


def validate_hungarian_lexicon_entry(entry: HungarianLexiconEntry) -> None:
    if normalize_greek_strong_id(entry.strong_id) != entry.strong_id:
        raise ValueError(
            f"Hungarian lexicon entry strong_id is not normalized: {entry.strong_id!r}."
        )
    if not entry.lemma.strip():
        raise ValueError("Hungarian lexicon entry lemma must not be empty.")
    if not entry.primary_gloss.strip():
        raise ValueError("Hungarian lexicon entry primary_gloss must not be empty.")
    if not entry.senses:
        raise ValueError("Hungarian lexicon entry must contain at least one sense.")

    normalized_senses = []
    for sense in entry.senses:
        if not isinstance(sense, str) or not sense.strip():
            raise ValueError("Hungarian lexicon entry senses must not contain empty values.")
        normalized_senses.append(sense.strip())

    if len(set(normalized_senses)) != len(normalized_senses):
        raise ValueError("Hungarian lexicon entry senses must not contain duplicates.")
    if entry.review_status not in VALID_REVIEW_STATUSES:
        raise ValueError(
            "Hungarian lexicon entry review_status must be 'draft' or 'reviewed'."
        )
    if not entry.source.strip():
        raise ValueError("Hungarian lexicon entry source must not be empty.")
    if entry.translation_method not in VALID_TRANSLATION_METHODS:
        raise ValueError(
            "Hungarian lexicon entry translation_method must be 'ai_assisted' or 'human'."
        )


def load_hungarian_lexicon(path: str | Path) -> dict[str, HungarianLexiconEntry]:
    source_path = Path(path)
    try:
        raw_data = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Hungarian lexicon JSON: {exc.msg}.") from exc

    if not isinstance(raw_data, list):
        raise ValueError("Invalid Hungarian lexicon JSON: root value must be a list.")

    entries: dict[str, HungarianLexiconEntry] = {}
    for index, raw_entry in enumerate(raw_data, start=1):
        entry = _entry_from_json(raw_entry, index)
        validate_hungarian_lexicon_entry(entry)
        if entry.strong_id in entries:
            raise ValueError(
                f"Duplicate Hungarian lexicon strong_id: {entry.strong_id!r}."
            )
        entries[entry.strong_id] = entry
    return entries


def load_default_hungarian_lexicon(
    path: str | Path = DEFAULT_HUNGARIAN_LEXICON_PATH,
) -> dict[str, HungarianLexiconEntry] | None:
    source_path = Path(path)
    if not source_path.exists():
        return None
    return load_hungarian_lexicon(source_path)


def load_strong_aliases(path: str | Path = DEFAULT_STRONG_ALIASES_PATH) -> dict[str, StrongAlias]:
    source_path = Path(path)
    if not source_path.exists():
        return {}
    try:
        raw_data = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Strong aliases JSON: {exc.msg}.") from exc

    if not isinstance(raw_data, list):
        raise ValueError("Invalid Strong aliases JSON: root value must be a list.")

    aliases: dict[str, StrongAlias] = {}
    for index, raw_alias in enumerate(raw_data, start=1):
        alias = _alias_from_json(raw_alias, index)
        if alias.source_strong_id in aliases:
            raise ValueError(f"Duplicate Strong alias source: {alias.source_strong_id!r}.")
        aliases[alias.source_strong_id] = alias
    return aliases


def get_hungarian_lexicon_entry(
    entries: dict[str, HungarianLexiconEntry],
    strong_id: str,
    aliases: dict[str, StrongAlias] | None = None,
) -> HungarianLexiconEntry | None:
    resolution = resolve_hungarian_lexicon_entry(entries, strong_id, aliases)
    return resolution.entry if resolution is not None else None


def resolve_hungarian_lexicon_entry(
    entries: dict[str, HungarianLexiconEntry],
    strong_id: str,
    aliases: dict[str, StrongAlias] | None = None,
) -> HungarianLexiconResolution | None:
    normalized = normalize_greek_strong_id(strong_id)
    direct = entries.get(normalized)
    if direct is not None:
        return HungarianLexiconResolution(
            entry=direct,
            requested_strong_id=normalized,
            resolved_strong_id=normalized,
        )

    alias = (aliases or {}).get(normalized)
    if alias is None:
        return None
    if alias.target_strong_id == normalized:
        return None
    target_alias = (aliases or {}).get(alias.target_strong_id)
    if target_alias is not None and target_alias.target_strong_id == normalized:
        return None

    target = entries.get(alias.target_strong_id)
    if target is None:
        return None
    return HungarianLexiconResolution(
        entry=target,
        requested_strong_id=normalized,
        resolved_strong_id=alias.target_strong_id,
        alias=alias,
    )


def _entry_from_json(raw_entry: Any, index: int) -> HungarianLexiconEntry:
    if not isinstance(raw_entry, dict):
        raise ValueError(f"Invalid Hungarian lexicon record #{index}: expected object.")

    try:
        senses = raw_entry["senses"]
        note = raw_entry.get("note")
        entry = HungarianLexiconEntry(
            strong_id=str(raw_entry["strong_id"]).strip(),
            lemma=str(raw_entry["lemma"]).strip(),
            primary_gloss=str(raw_entry["primary_gloss"]).strip(),
            senses=tuple(senses),
            note=str(note).strip() if note is not None and str(note).strip() else None,
            source=str(raw_entry["source"]).strip(),
            review_status=str(raw_entry["review_status"]).strip(),
            translation_method=str(raw_entry.get("translation_method") or "ai_assisted").strip(),
            source_name=str(raw_entry.get("source_name") or "").strip(),
            source_version=str(raw_entry.get("source_version") or "").strip(),
        )
    except KeyError as exc:
        raise ValueError(
            f"Invalid Hungarian lexicon record #{index}: missing field {exc.args[0]!r}."
        ) from exc
    except TypeError as exc:
        raise ValueError(
            f"Invalid Hungarian lexicon record #{index}: senses must be a list."
        ) from exc

    return entry


def _alias_from_json(raw_alias: Any, index: int) -> StrongAlias:
    if not isinstance(raw_alias, dict):
        raise ValueError(f"Invalid Strong alias record #{index}: expected object.")
    try:
        source = normalize_greek_strong_id(str(raw_alias["source_strong_id"]))
        target = normalize_greek_strong_id(str(raw_alias["target_strong_id"]))
        confidence = float(raw_alias["confidence"])
        evidence = str(raw_alias["evidence"]).strip()
        token_frequency = int(raw_alias["token_frequency"])
    except KeyError as exc:
        raise ValueError(
            f"Invalid Strong alias record #{index}: missing field {exc.args[0]!r}."
        ) from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Strong alias record #{index}.") from exc

    if not evidence:
        raise ValueError(f"Invalid Strong alias record #{index}: evidence must not be empty.")
    if confidence < 0 or confidence > 1:
        raise ValueError(f"Invalid Strong alias record #{index}: confidence must be 0..1.")
    if token_frequency < 0:
        raise ValueError(
            f"Invalid Strong alias record #{index}: token_frequency must not be negative."
        )
    return StrongAlias(
        source_strong_id=source,
        target_strong_id=target,
        confidence=confidence,
        evidence=evidence,
        token_frequency=token_frequency,
    )
