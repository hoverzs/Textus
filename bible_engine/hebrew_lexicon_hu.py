from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bible_engine.hebrew_lexicon_repository import (
    DEFAULT_HEBREW_ALIAS_PATH,
    HebrewLexiconLookup,
    HebrewLexiconRepository,
    normalize_hebrew_strong_id,
)


DATA_DIR = Path(__file__).parent / "data"
DEFAULT_HEBREW_LEXICON_HU_PATH = DATA_DIR / "hebrew_lexicon_hu.json"
VALID_REVIEW_STATUSES = frozenset({"draft", "reviewed"})
VALID_TRANSLATION_METHODS = frozenset({"ai_assisted", "human"})


@dataclass(frozen=True)
class HebrewHungarianLexiconEntry:
    strong_id: str
    lemma: str
    transliteration: str
    language: str
    base_meaning_hu: str
    possible_meanings_hu: tuple[str, ...]
    lexical_note_hu: str
    source_gloss_en: str
    source_note_en: str
    translation_method: str
    review_status: str
    source: str
    source_record_id: str
    aliases: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HebrewHungarianLexiconResolution:
    resolution_type: str
    requested_strong_id: str
    resolved_strong_id: str
    entry: HebrewHungarianLexiconEntry | None
    tbesh_fallback: HebrewLexiconLookup | None
    review_status: str = ""
    translation_method: str = ""
    source: str = ""
    warnings: tuple[str, ...] = ()


def load_hebrew_hungarian_lexicon(
    path: str | Path = DEFAULT_HEBREW_LEXICON_HU_PATH,
) -> dict[str, HebrewHungarianLexiconEntry]:
    source = Path(path)
    if not source.exists():
        return {}
    raw_data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw_data, list):
        raise ValueError("Invalid Hebrew Hungarian lexicon JSON: root value must be a list.")

    entries: dict[str, HebrewHungarianLexiconEntry] = {}
    for index, raw_entry in enumerate(raw_data, start=1):
        entry = _entry_from_json(raw_entry, index)
        validate_hebrew_hungarian_lexicon_entry(entry)
        if entry.strong_id in entries:
            raise ValueError(f"Duplicate Hebrew Hungarian lexicon strong_id: {entry.strong_id}")
        entries[entry.strong_id] = entry
    return entries


def validate_hebrew_hungarian_lexicon_entry(entry: HebrewHungarianLexiconEntry) -> None:
    if normalize_hebrew_strong_id(entry.strong_id) != entry.strong_id:
        raise ValueError(f"Hebrew Hungarian lexicon strong_id is not normalized: {entry.strong_id}")
    for field_name in ("lemma", "base_meaning_hu", "source", "source_record_id"):
        if not getattr(entry, field_name).strip():
            raise ValueError(f"{field_name} must not be empty")
    if entry.language not in {"hebrew", "aramaic", "mixed", ""}:
        raise ValueError("language must be 'hebrew', 'aramaic', 'mixed', or empty")
    if not entry.possible_meanings_hu:
        raise ValueError("possible_meanings_hu must contain at least one value")
    if len(set(entry.possible_meanings_hu)) != len(entry.possible_meanings_hu):
        raise ValueError("possible_meanings_hu must not contain duplicates")
    if entry.review_status not in VALID_REVIEW_STATUSES:
        raise ValueError("review_status must be 'draft' or 'reviewed'")
    if entry.translation_method not in VALID_TRANSLATION_METHODS:
        raise ValueError("translation_method must be 'ai_assisted' or 'human'")


class HebrewHungarianLexiconRepository:
    def __init__(
        self,
        lexicon_path: str | Path = DEFAULT_HEBREW_LEXICON_HU_PATH,
        *,
        tbesh_database_path: str | Path | None = None,
        alias_path: str | Path = DEFAULT_HEBREW_ALIAS_PATH,
    ) -> None:
        self.lexicon_path = Path(lexicon_path)
        self.entries = load_hebrew_hungarian_lexicon(self.lexicon_path)
        self.tbesh_repository = HebrewLexiconRepository(
            *(tuple() if tbesh_database_path is None else (tbesh_database_path,)),
            alias_path=alias_path,
        )
        self.aliases = self.tbesh_repository.aliases

    def lookup(
        self, strong_id: str, *, expected_lemma: str = ""
    ) -> HebrewHungarianLexiconResolution:
        """Resolve a Hungarian lexical record for ``strong_id``.

        ``expected_lemma`` is the lemma TAHOT assigns to the token being looked
        up. When supplied and it disagrees consonantally with the stored record,
        a warning is attached: the record then describes a *different word*.

        Phase 2A — this is not hypothetical. The Hungarian lexicon was generated
        from a TBESH import that indexed cross-reference rows under the Strong id
        of the lexeme they point at, so 299 records (134232 corpus tokens)
        currently describe the wrong word — e.g. H3068G (יהוה) carrying
        שָׁלוֹם "béke". ``scripts/audit_hebrew_lexicon_lemma_consistency.py``
        enumerates them. Until those records are regenerated, the deterministic
        layer must not present them as this word's meaning without saying so.
        """
        requested = normalize_hebrew_strong_id(strong_id)
        direct = self.entries.get(requested)
        if direct is not None:
            return _hu_resolution(
                "direct",
                requested,
                requested,
                direct,
                None,
                warnings=_lemma_mismatch_warnings(direct, expected_lemma),
            )

        alias = self.aliases.get(requested)
        if alias:
            target = alias["target_id"]
            target_entry = self.entries.get(target)
            if target_entry is not None:
                return _hu_resolution(
                    "alias",
                    requested,
                    target,
                    target_entry,
                    None,
                    warnings=(f"Magyar lexikai rekord alias alapján: {requested} → {target}",)
                    + _lemma_mismatch_warnings(target_entry, expected_lemma),
                )

        fallback = self.tbesh_repository.lookup(requested)
        if fallback.entry is not None:
            # Phase 2A — a cross-reference row is NOT this lexeme's definition
            # (see HebrewLexiconRepository.lookup). Surface it as such instead
            # of presenting another word's gloss as this word's base meaning.
            if fallback.resolution_type == "cross_reference":
                return HebrewHungarianLexiconResolution(
                    resolution_type="tbesh_cross_reference",
                    requested_strong_id=requested,
                    resolved_strong_id=fallback.resolved_strong_id or fallback.matched_strong_id,
                    entry=None,
                    tbesh_fallback=fallback,
                    source=fallback.entry.source_name,
                    warnings=(
                        "Ehhez a Strong/STEP azonosítóhoz még nincs magyar lexikai rekord.",
                        "A megjelenített angol szótári rekord nem ennek a szónak a saját "
                        "szócikke, hanem egy rá hivatkozó (arámi megfelelő / névváltozat / "
                        "összetétel) rekord — az alapjelentés megállapításához nem elegendő.",
                    ),
                )
            return HebrewHungarianLexiconResolution(
                resolution_type="tbesh_fallback",
                requested_strong_id=requested,
                resolved_strong_id=fallback.resolved_strong_id or fallback.matched_strong_id,
                entry=None,
                tbesh_fallback=fallback,
                source=fallback.entry.source_name,
                warnings=("Ehhez a Strong/STEP azonosítóhoz még nincs magyar lexikai rekord.",),
            )
        return HebrewHungarianLexiconResolution(
            resolution_type="missing",
            requested_strong_id=requested,
            resolved_strong_id="",
            entry=None,
            tbesh_fallback=fallback,
            warnings=("Nincs lexikai adat ehhez a Strong/STEP azonosítóhoz.",),
        )


def _consonants(text: str) -> str:
    """Consonantal skeleton, so pointing differences alone never trigger a warning."""
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).replace("־", "").strip()


LEMMA_MISMATCH_WARNING = (
    "A magyar lexikai rekord egy MÁSIK szóalakhoz tartozik ({record}), mint amit "
    "a szövegben kiválasztottál ({token}) — az itt látható alapjelentés ezért "
    "nem megbízható ehhez a szóhoz."
)


def _lemma_mismatch_warnings(
    entry: HebrewHungarianLexiconEntry, expected_lemma: str
) -> tuple[str, ...]:
    if not expected_lemma or not entry.lemma:
        return ()
    if _consonants(entry.lemma) == _consonants(expected_lemma):
        return ()
    return (LEMMA_MISMATCH_WARNING.format(record=entry.lemma, token=expected_lemma),)


def _hu_resolution(
    resolution_type: str,
    requested: str,
    resolved: str,
    entry: HebrewHungarianLexiconEntry,
    fallback: HebrewLexiconLookup | None,
    *,
    warnings: tuple[str, ...] = (),
) -> HebrewHungarianLexiconResolution:
    return HebrewHungarianLexiconResolution(
        resolution_type=resolution_type,
        requested_strong_id=requested,
        resolved_strong_id=resolved,
        entry=entry,
        tbesh_fallback=fallback,
        review_status=entry.review_status,
        translation_method=entry.translation_method,
        source=entry.source,
        warnings=warnings + entry.warnings,
    )


def _entry_from_json(raw_entry: Any, index: int) -> HebrewHungarianLexiconEntry:
    if not isinstance(raw_entry, dict):
        raise ValueError(f"Invalid Hebrew Hungarian lexicon record #{index}: expected object.")
    try:
        return HebrewHungarianLexiconEntry(
            strong_id=normalize_hebrew_strong_id(str(raw_entry["strong_id"])),
            lemma=str(raw_entry["lemma"]).strip(),
            transliteration=str(raw_entry.get("transliteration", "")).strip(),
            language=str(raw_entry.get("language", "")).strip(),
            base_meaning_hu=str(raw_entry["base_meaning_hu"]).strip(),
            possible_meanings_hu=tuple(str(item).strip() for item in raw_entry["possible_meanings_hu"]),
            lexical_note_hu=str(raw_entry.get("lexical_note_hu", "")).strip(),
            source_gloss_en=str(raw_entry.get("source_gloss_en", "")).strip(),
            source_note_en=str(raw_entry.get("source_note_en", "")).strip(),
            translation_method=str(raw_entry["translation_method"]).strip(),
            review_status=str(raw_entry["review_status"]).strip(),
            source=str(raw_entry["source"]).strip(),
            source_record_id=str(raw_entry["source_record_id"]).strip(),
            aliases=tuple(str(item).strip() for item in raw_entry.get("aliases", ())),
            warnings=tuple(str(item).strip() for item in raw_entry.get("warnings", ())),
        )
    except KeyError as exc:
        raise ValueError(f"Invalid Hebrew Hungarian lexicon record #{index}: missing field {exc.args[0]!r}.") from exc
    except TypeError as exc:
        raise ValueError(f"Invalid Hebrew Hungarian lexicon record #{index}: invalid list field.") from exc
