from __future__ import annotations

import json
from pathlib import Path

import pytest

from bible_engine.lexicon_hu import (
    DEFAULT_HUNGARIAN_LEXICON_PATH,
    HungarianLexiconEntry,
    SAMPLE_HUNGARIAN_LEXICON_PATH,
    StrongAlias,
    VALID_TRANSLATION_METHODS,
    get_hungarian_lexicon_entry,
    load_default_hungarian_lexicon,
    load_hungarian_lexicon,
    load_strong_aliases,
    resolve_hungarian_lexicon_entry,
    validate_hungarian_lexicon_entry,
)
from bible_engine.tagnt_parser import get_verse_tokens


ROOT = Path(__file__).parents[1]
LEXICON_FIXTURE = ROOT / "bible_engine" / "data" / "lexicon_hu_sample.json"
FULL_LEXICON = ROOT / "bible_engine" / "data" / "lexicon_hu.json"
JHN_FIXTURE = ROOT / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv"


def test_loads_three_sample_hungarian_lexicon_entries() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    assert set(entries) == {"G0025", "G2889", "G3779"}
    assert all(entry.review_status == "draft" for entry in entries.values())


def test_default_hungarian_lexicon_path_is_full_json() -> None:
    assert DEFAULT_HUNGARIAN_LEXICON_PATH == FULL_LEXICON
    assert SAMPLE_HUNGARIAN_LEXICON_PATH == LEXICON_FIXTURE


def test_missing_default_hungarian_lexicon_returns_none(tmp_path: Path) -> None:
    assert load_default_hungarian_lexicon(tmp_path / "missing.json") is None


def test_full_hungarian_lexicon_loads_imported_records_when_available() -> None:
    if not FULL_LEXICON.exists():
        pytest.skip("The full Hungarian lexicon has not been imported locally.")

    entries = load_default_hungarian_lexicon(FULL_LEXICON)

    assert entries is not None
    assert get_hungarian_lexicon_entry(entries, "G2316").primary_gloss == "Isten"
    assert get_hungarian_lexicon_entry(entries, "G1063").primary_gloss == "mert"
    assert get_hungarian_lexicon_entry(entries, "G3779").primary_gloss == "így"


def test_full_hungarian_lexicon_exposes_provenance_fields_on_every_entry() -> None:
    """Phase 2A: translation_method/source_name/source_version were already
    present on 5,956 of 5,959 production records in the JSON file, but the
    dataclass/loader silently dropped them — no runtime code could see them.
    This proves the loader now exposes them, and that no production record
    is missing translation_method (every entry has a determinable
    provenance, even the 3 handful backfilled by
    scripts/backfill_greek_lexicon_provenance.py)."""
    if not FULL_LEXICON.exists():
        pytest.skip("The full Hungarian lexicon has not been imported locally.")

    entries = load_default_hungarian_lexicon(FULL_LEXICON)
    assert entries is not None
    assert len(entries) > 5000

    missing_translation_method = [
        entry for entry in entries.values() if not entry.translation_method
    ]
    assert missing_translation_method == []
    assert all(entry.translation_method in VALID_TRANSLATION_METHODS for entry in entries.values())
    # As of Phase 2A, every production record is machine-translated draft —
    # no record claims human review. If this ever changes, this assertion
    # (not the code) should be updated to reflect the new true count.
    human_reviewed = [e for e in entries.values() if e.translation_method == "human"]
    assert human_reviewed == []


def test_get_g0025_entry_by_normalized_and_short_strong_id() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    direct = get_hungarian_lexicon_entry(entries, "G0025")
    normalized = get_hungarian_lexicon_entry(entries, "G25")

    assert direct is not None
    assert normalized == direct
    assert direct.lemma == "ἀγαπάω"
    assert direct.primary_gloss == "szeret"
    assert direct.senses == (
        "szeret",
        "megbecsül",
        "jóindulattal viszonyul valakihez",
    )


def test_get_g2889_and_g3779_entries() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    kosmos = get_hungarian_lexicon_entry(entries, "G2889")
    houtos = get_hungarian_lexicon_entry(entries, "G3779")

    assert kosmos is not None
    assert kosmos.lemma == "κόσμος"
    assert kosmos.primary_gloss == "világ"
    assert "világegyetem" in kosmos.senses
    assert "dísz vagy ékesség" in kosmos.senses

    assert houtos is not None
    assert houtos.lemma == "οὕτως"
    assert houtos.primary_gloss == "így"
    assert "ennyire vagy ilyen mértékben" in houtos.senses


def test_utf8_characters_are_preserved() -> None:
    text = LEXICON_FIXTURE.read_text(encoding="utf-8")
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    assert "ἀγαπάω" in text
    assert "κόσμος" in text
    assert "οὕτως" in text
    assert entries["G2889"].note
    assert "teremtett világra" in entries["G2889"].note
    assert "szövegkörnyezettől" in entries["G0025"].note


def test_unknown_strong_id_returns_none() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)

    assert get_hungarian_lexicon_entry(entries, "G9999") is None


def test_direct_hungarian_entry_has_priority_over_alias() -> None:
    entries = {
        "G0032G": _valid_entry(strong_id="G0032G", lemma="direct", primary_gloss="direct"),
        "G0032": _valid_entry(strong_id="G0032", lemma="target", primary_gloss="target"),
    }
    aliases = {
        "G0032G": StrongAlias("G0032G", "G0032", 0.99, "test", 1),
    }

    resolution = resolve_hungarian_lexicon_entry(entries, "G0032G", aliases)

    assert resolution is not None
    assert resolution.entry.strong_id == "G0032G"
    assert resolution.alias is None


def test_alias_resolves_suffix_id_to_target_hungarian_entry() -> None:
    entries = {"G0032": _valid_entry(strong_id="G0032", lemma="ἄγγελος")}
    aliases = {
        "G0032G": StrongAlias("G0032G", "G0032", 0.99, "same lemma", 176),
        "G0032H": StrongAlias("G0032H", "G0032", 0.99, "same lemma", 8),
    }

    g_variant = resolve_hungarian_lexicon_entry(entries, "G32G", aliases)
    h_variant = resolve_hungarian_lexicon_entry(entries, "G0032H", aliases)

    assert g_variant is not None
    assert g_variant.entry.strong_id == "G0032"
    assert g_variant.requested_strong_id == "G0032G"
    assert g_variant.resolved_strong_id == "G0032"
    assert g_variant.alias.token_frequency == 176
    assert h_variant is not None
    assert h_variant.alias.source_strong_id == "G0032H"


def test_manual_final_suffix_aliases_resolve_to_base_entries() -> None:
    entries = {
        "G0001": _valid_entry(strong_id="G0001", lemma="α, Ἀλφα"),
        "G1086": _valid_entry(strong_id="G1086", lemma="Γερασηνός"),
        "G2857": _valid_entry(strong_id="G2857", lemma="Κολοσσαί"),
    }
    aliases = {
        "G0001G": StrongAlias(
            "G0001G",
            "G0001",
            0.98,
            "manual Alpha letter/name variant",
            4,
        ),
        "G1086G": StrongAlias(
            "G1086G",
            "G1086",
            0.97,
            "manual Gerasene spelling variant",
            3,
        ),
        "G2857G": StrongAlias(
            "G2857G",
            "G2857",
            0.97,
            "manual Colossae spelling variant",
            1,
        ),
    }

    assert resolve_hungarian_lexicon_entry(entries, "G0001G", aliases).resolved_strong_id == "G0001"
    assert resolve_hungarian_lexicon_entry(entries, "G1086G", aliases).resolved_strong_id == "G1086"
    assert resolve_hungarian_lexicon_entry(entries, "G2857G", aliases).resolved_strong_id == "G2857"


def test_bad_alias_target_and_alias_cycle_return_none_without_traceback() -> None:
    entries = {"G0032": _valid_entry(strong_id="G0032", lemma="ἄγγελος")}
    bad_target = {"G0032G": StrongAlias("G0032G", "G9999", 0.99, "bad", 1)}
    cycle = {
        "G0032G": StrongAlias("G0032G", "G0032H", 0.99, "cycle", 1),
        "G0032H": StrongAlias("G0032H", "G0032G", 0.99, "cycle", 1),
    }

    assert resolve_hungarian_lexicon_entry(entries, "G0032G", bad_target) is None
    assert resolve_hungarian_lexicon_entry(entries, "G0032G", cycle) is None


def test_load_strong_aliases_normalizes_source_and_target(tmp_path: Path) -> None:
    path = tmp_path / "aliases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "source_strong_id": "G32G",
                    "target_strong_id": "G32",
                    "confidence": 0.99,
                    "evidence": "same lemma",
                    "token_frequency": 3,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    aliases = load_strong_aliases(path)

    assert set(aliases) == {"G0032G"}
    assert aliases["G0032G"].target_strong_id == "G0032"


def test_duplicate_strong_id_is_rejected(tmp_path: Path) -> None:
    data = _sample_json_records()
    data.append(dict(data[0]))
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate Hungarian lexicon strong_id"):
        load_hungarian_lexicon(path)


def test_empty_primary_gloss_is_rejected() -> None:
    entry = _valid_entry(primary_gloss=" ")

    with pytest.raises(ValueError, match="primary_gloss"):
        validate_hungarian_lexicon_entry(entry)


def test_empty_or_duplicate_senses_are_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_hungarian_lexicon_entry(_valid_entry(senses=("szeret", " ")))

    with pytest.raises(ValueError, match="duplicates"):
        validate_hungarian_lexicon_entry(_valid_entry(senses=("szeret", "szeret")))


def test_invalid_review_status_is_rejected() -> None:
    entry = _valid_entry(review_status="needs-review")

    with pytest.raises(ValueError, match="review_status"):
        validate_hungarian_lexicon_entry(entry)


def test_invalid_strong_id_and_empty_source_are_rejected() -> None:
    with pytest.raises(ValueError, match="not normalized"):
        validate_hungarian_lexicon_entry(_valid_entry(strong_id="G25"))

    with pytest.raises(ValueError, match="source"):
        validate_hungarian_lexicon_entry(_valid_entry(source=" "))


def test_missing_file_raises_file_not_found_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        load_hungarian_lexicon(missing)


def test_invalid_json_has_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid Hungarian lexicon JSON"):
        load_hungarian_lexicon(path)


def test_missing_required_json_field_has_clear_error(tmp_path: Path) -> None:
    data = _sample_json_records()
    del data[0]["primary_gloss"]
    path = tmp_path / "missing-field.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="missing field 'primary_gloss'"):
        load_hungarian_lexicon(path)


def test_john_3_16_tokens_can_find_sample_hungarian_entries() -> None:
    entries = load_hungarian_lexicon(LEXICON_FIXTURE)
    tokens = get_verse_tokens(JHN_FIXTURE, book="Jhn", chapter=3, verse=16)
    tokens_by_strong = {token.strong_id: token for token in tokens}

    for strong_id in ("G0025", "G2889", "G3779"):
        token = tokens_by_strong[strong_id]
        entry = get_hungarian_lexicon_entry(entries, token.strong_id)

        assert entry is not None
        assert entry.strong_id == strong_id
        assert entry.lemma
        assert entry.senses


def _valid_entry(**overrides: object) -> HungarianLexiconEntry:
    values = {
        "strong_id": "G0025",
        "lemma": "ἀγαπάω",
        "primary_gloss": "szeret",
        "senses": ("szeret", "megbecsül"),
        "note": None,
        "source": "STEPBible TBESG alapján készített magyar munkaváltozat",
        "review_status": "draft",
    }
    values.update(overrides)
    return HungarianLexiconEntry(**values)


def _sample_json_records() -> list[dict[str, object]]:
    return json.loads(LEXICON_FIXTURE.read_text(encoding="utf-8"))
