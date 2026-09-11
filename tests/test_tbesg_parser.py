from __future__ import annotations

from pathlib import Path
import unicodedata

import pytest

from bible_engine.tagnt_parser import get_verse_tokens
from bible_engine.tbesg_parser import (
    GreekLexiconEntry,
    normalize_greek_strong_id,
    parse_tbesg_line,
)


ROOT = Path(__file__).parents[1]
TBESG_FIXTURE = ROOT / "tests" / "fixtures" / "tbesg_sample.tsv"
JHN_FIXTURE = ROOT / "tests" / "fixtures" / "tagnt_jhn_3_16_sample.tsv"
EXPECTED_HEADER = (
    "eStrong",
    "dStrong",
    "uStrong",
    "Greek",
    "Transliteration",
    "Morph",
    "Gloss",
    "Abbott-Smith lexicon (AS), with gaps occationally filled from edited versions of  Middle LSJ ",
)


def test_fixture_preserves_actual_tbesg_header() -> None:
    header = TBESG_FIXTURE.read_text(encoding="utf-8").splitlines()[0].split("\t")

    assert tuple(header) == EXPECTED_HEADER


def test_parse_g0025_agapao_entry() -> None:
    entry = _entries_by_strong()["G0025"]

    assert entry == GreekLexiconEntry(
        strong_id="G0025",
        dstrong_id="G0025 =",
        ustrong_id="G0025",
        greek=unicodedata.normalize("NFC", "ἀγαπάω"),
        transliteration="agapaō",
        morph="G:V",
        gloss="to love",
        meaning_raw=entry.meaning_raw,
    )
    assert entry.meaning_raw
    assert "<b>to love</b>" in entry.meaning_raw
    assert "<BR />" in entry.meaning_raw


def test_parse_g2889_kosmos_entry() -> None:
    entry = _entries_by_strong()["G2889"]

    assert entry.strong_id == "G2889"
    assert entry.greek == unicodedata.normalize("NFC", "κόσμος")
    assert entry.transliteration == "kosmos"
    assert entry.morph == "G:N-M"
    assert entry.gloss == "world"
    assert entry.meaning_raw
    assert "ornament, adornment" in entry.meaning_raw
    assert "human inhabitants of the world" in entry.meaning_raw


def test_parse_g3779_houtos_entry() -> None:
    entry = _entries_by_strong()["G3779"]

    assert entry.strong_id == "G3779"
    assert entry.greek == "οὕτως"
    assert entry.transliteration == "ohutō, ohutōs"
    assert entry.morph == "G:ADV"
    assert entry.gloss == "thus(-ly)"
    assert entry.meaning_raw
    assert "in this way, so, thus" in entry.meaning_raw


def test_greek_field_is_normalized_to_unicode_nfc() -> None:
    entry = parse_tbesg_line("G25\t\t\tἀγαπάω\t\t\t\t")

    assert entry.strong_id == "G0025"
    assert entry.greek == unicodedata.normalize("NFC", "ἀγαπάω")
    assert unicodedata.is_normalized("NFC", entry.greek)


def test_empty_optional_fields_are_none() -> None:
    entry = parse_tbesg_line("G25\t\t\tἀγαπάω\t\t\t\t")

    assert entry.dstrong_id is None
    assert entry.ustrong_id is None
    assert entry.transliteration is None
    assert entry.morph is None
    assert entry.gloss is None
    assert entry.meaning_raw is None


def test_meaning_raw_is_preserved_without_html_cleanup() -> None:
    entry = _entries_by_strong()["G0025"]

    assert entry.meaning_raw is not None
    assert "<ref='Jhn.3.35'>Jhn.3:35;</ref>" in entry.meaning_raw
    assert entry.meaning_raw.startswith(" <b>ἀγαπ")
    assert entry.meaning_raw.endswith("(AS)")


def test_normalize_greek_strong_id_pads_and_preserves_suffixes() -> None:
    assert normalize_greek_strong_id("G25") == "G0025"
    assert normalize_greek_strong_id("G0025") == "G0025"
    assert normalize_greek_strong_id("G2264G") == "G2264G"
    assert normalize_greek_strong_id("G10005") == "G10005"
    assert normalize_greek_strong_id("G20200") == "G20200"


def test_normalize_greek_strong_id_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Invalid Greek Strong identifier"):
        normalize_greek_strong_id("not-a-strong-id")

    with pytest.raises(ValueError, match="range"):
        normalize_greek_strong_id("G0000")


def test_normalize_greek_strong_id_rejects_hebrew_ids() -> None:
    with pytest.raises(ValueError, match="Hebrew id is not supported"):
        normalize_greek_strong_id("H0157")


def test_parse_tbesg_line_rejects_bad_or_incomplete_records() -> None:
    with pytest.raises(ValueError, match="expected 8 tab-separated fields"):
        parse_tbesg_line("G0025\tG0025")

    with pytest.raises(ValueError, match="missing eStrong"):
        parse_tbesg_line("\tG0025 =\tG0025\tἀγαπάω\tagapaō\tG:V\tto love\tmeaning")


def test_parse_tbesg_line_preserves_record_with_missing_greek_lemma() -> None:
    entry = parse_tbesg_line(
        "G2199\tG2199H =\tG2199H\t\tZebedaios\tN:N-M-P\t[wife of Zebedee]\tmeaning"
    )

    assert entry.strong_id == "G2199"
    assert entry.greek == ""
    assert entry.transliteration == "Zebedaios"


def test_john_3_16_tagnt_strong_ids_match_sample_lexicon_entries() -> None:
    token_strong_ids = {
        normalize_greek_strong_id(token.strong_id)
        for token in get_verse_tokens(JHN_FIXTURE, book="Jhn", chapter=3, verse=16)
    }
    lexicon_strong_ids = set(_entries_by_strong())

    assert {"G0025", "G2889", "G3779"} <= token_strong_ids
    assert {"G0025", "G2889", "G3779"} == lexicon_strong_ids
    assert {"G0025", "G2889", "G3779"} <= token_strong_ids & lexicon_strong_ids


# ---------------------------------------------------------------------------
# Phase 2A — canonical identity vs. eStrong collision. TBESG's eStrong (the
# raw first column) is shared by every disambiguated sense of a base number
# (e.g. G0001 = both "Alpha" and the interjection "ah!"); the disambiguated
# identity that TAGNT tokens and lexicon_hu.json actually key on lives in the
# dStrong field. Regression for the fix that keys lexicon rows by
# canonical_strong_id instead of bare eStrong.
# ---------------------------------------------------------------------------


def test_canonical_strong_id_prefers_disambiguated_dstrong_sense() -> None:
    alpha = parse_tbesg_line("G0001\tG0001G =\tG0001G\tα, Ἀλφα\tAlpha\tG:N-LI\tAlpha\tmeaning")
    ah = parse_tbesg_line("G0001\tG0001H =\tG0001H\tἆ\ta\tG:INJ\tah!\tmeaning")

    assert alpha.strong_id == "G0001"
    assert ah.strong_id == "G0001"
    assert alpha.canonical_strong_id == "G0001G"
    assert ah.canonical_strong_id == "G0001H"
    assert alpha.canonical_strong_id != ah.canonical_strong_id


def test_canonical_strong_id_falls_back_to_estrong_when_no_suffix() -> None:
    entry = parse_tbesg_line("G0025\tG0025 =\tG0025\tἀγαπάω\tagapaō\tG:V\tto love\tmeaning")

    assert entry.canonical_strong_id == "G0025"


def test_claims_strong_id_recognizes_own_identity_not_cross_reference() -> None:
    # uStrong pointing at a Hebrew Strong id (the "the Greek of" cross-
    # language transliteration case) must never be claimed as this row's
    # own Greek identity, and must not be reported as a Greek reference_
    # strong_id either (out of namespace — it is not a Greek Strong id).
    abia_g = parse_tbesg_line("G0007\tG0007G = the Greek of\tH0029I\tἈβιά\tAbia\tN:N-M-P\tAbijah\tmeaning")

    assert abia_g.claims_strong_id("G0007")
    assert abia_g.claims_strong_id("G0007G")
    assert not abia_g.claims_strong_id("H0029I")
    assert abia_g.reference_strong_ids == ()


def test_reference_strong_ids_captures_greek_cross_reference() -> None:
    entry = parse_tbesg_line("G0009\tG0009 =\tG2264G\tἈβιληνή\tAbilēnē\tN:N-F-L\tAbilene\tmeaning")

    assert entry.reference_strong_ids == ("G2264G",)


def _fixture_records() -> list[str]:
    return TBESG_FIXTURE.read_text(encoding="utf-8").splitlines()[1:]


def _entries_by_strong() -> dict[str, GreekLexiconEntry]:
    entries = [parse_tbesg_line(line) for line in _fixture_records() if line.strip()]
    return {entry.strong_id: entry for entry in entries}
