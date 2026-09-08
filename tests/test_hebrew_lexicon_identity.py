"""Phase 2A regression tests for Strong-id identity and the AI boundary.

Covers:

* TBESH ``uStrong`` is a cross-reference, not an identity — derived records must
  never claim (or overwrite) the base lexeme's key. This is the root cause of
  the אֲשֶׁר defect and of 1056 further hijacked keys.
* אֲשֶׁר no longer presents a minority temporal rendering as its base meaning.
* Already-decoded morphology survives into the AI prompt instead of the model
  being handed a raw TEHMC code to re-parse.

No test here calls an LLM.
"""

from __future__ import annotations

import sqlite3

import pytest

from bible_engine.hebrew_lexicon_hu import (
    DEFAULT_HEBREW_LEXICON_HU_PATH,
    HebrewHungarianLexiconRepository,
    load_hebrew_hungarian_lexicon,
)
from bible_engine.hebrew_sqlite import (
    DEFAULT_TAHOT_DATABASE_PATH,
    DEFAULT_TBESH_DATABASE_PATH,
    create_tbesh_schema,
    import_tbesh_lexicon,
)
from bible_engine.tbesh_parser import HebrewLexiconEntry, parse_tbesh_row

requires_corpus = pytest.mark.skipif(
    not DEFAULT_TAHOT_DATABASE_PATH.exists(),
    reason="production TAHOT database not available",
)
requires_tbesh = pytest.mark.skipif(
    not DEFAULT_TBESH_DATABASE_PATH.exists(),
    reason="production TBESH database not available",
)


# --------------------------------------------------------------------------
# A. Identity vs cross-reference.
# --------------------------------------------------------------------------


def _entry(estrong: str, dstrong: str, ustrong: str, hebrew: str, gloss: str) -> HebrewLexiconEntry:
    return HebrewLexiconEntry(
        estrong=estrong,
        dstrong=dstrong,
        ustrong=ustrong,
        hebrew=hebrew,
        transliteration="",
        morph="H:N",
        gloss=gloss,
        meaning="",
    )


def test_ustrong_is_not_treated_as_identity() -> None:
    # The real TBESH row for כַּאֲשֶׁר: it *is* H0834D, and merely points at H0834A.
    compound = _entry("H0834d", "H0834D = combination of", "H0834A (H9004+H0834A)", "כַּאֲשֶׁר", "as which")

    assert "H0834D" in compound.identity_strong_ids
    assert "H0834A" not in compound.identity_strong_ids
    assert "H0834A" in compound.reference_strong_ids
    assert compound.claims_strong_id("H0834D")
    assert not compound.claims_strong_id("H0834A")
    # strong_ids keeps the full closure for coverage audits.
    assert {"H0834D", "H0834A"} <= set(compound.strong_ids)


def test_cross_reference_record_cannot_overwrite_the_base_lexeme(tmp_path) -> None:
    """The import must keep the genuine entry even when a pointer row follows it."""
    base = "H0834A\tH0834A\tH0834A\tאֲשֶׁר\ta.sher\tH:T\twhich\trelative particle"
    compound = (
        "H0834d\tH0834D = combination of\tH0834A (H9004+H0834A)\t"
        "כַּאֲשֶׁר\tka.a.sher\tH:T\tas which\tconj"
    )
    source = tmp_path / "tbesh.txt"
    source.write_text(
        "eStrong#\tdStrong\tuStrong\tHebrew\tTransliteration\tMorph\tGloss\tMeaning\n"
        f"{base}\n{compound}\n",
        encoding="utf-8",
    )

    database = tmp_path / "lex.sqlite3"
    with sqlite3.connect(database) as connection:
        create_tbesh_schema(connection)
        import_tbesh_lexicon(source, connection=connection)

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = {
            row["strong_id"]: row["hebrew"]
            for row in connection.execute("SELECT strong_id, hebrew FROM lexicon_entries")
        }

    assert rows["H0834A"] == "אֲשֶׁר", "the compound row must not hijack the base lexeme"
    assert rows["H0834D"] == "כַּאֲשֶׁר"


def test_reference_id_is_still_available_as_a_last_resort(tmp_path) -> None:
    """A uStrong-only id is filled in when nothing genuine claims it."""
    compound = (
        "H0834d\tH0834D = combination of\tH0834A (H9004+H0834A)\t"
        "כַּאֲשֶׁר\tka.a.sher\tH:T\tas which\tconj"
    )
    source = tmp_path / "tbesh.txt"
    source.write_text(
        "eStrong#\tdStrong\tuStrong\tHebrew\tTransliteration\tMorph\tGloss\tMeaning\n"
        f"{compound}\n",
        encoding="utf-8",
    )
    database = tmp_path / "lex.sqlite3"
    with sqlite3.connect(database) as connection:
        create_tbesh_schema(connection)
        import_tbesh_lexicon(source, connection=connection)
        found = connection.execute(
            "SELECT hebrew FROM lexicon_entries WHERE strong_id='H0834A'"
        ).fetchone()

    assert found is not None and found[0] == "כַּאֲשֶׁר"


def test_parse_and_identity_round_trip() -> None:
    # The real shipped TBESH row for the Aramaic יָת: it *is* H3487 and merely
    # notes that it is "in Aramaic of" the Hebrew object marker H0853. Indexing
    # it under H0853 is what made אֵת display יָת for 21890 tokens.
    row = "H3487\tH3487 = in Aramaic of\tH0853\tיָת\tyat\tA:Part\twhom\tAramaic of et"
    entry = parse_tbesh_row(row)

    assert entry.claims_strong_id("H3487")
    assert not entry.claims_strong_id("H0853")
    assert "H0853" in entry.reference_strong_ids


# --------------------------------------------------------------------------
# B. אֲשֶׁר lexical/basic meaning.
# --------------------------------------------------------------------------


def test_asher_base_meaning_is_the_relative_function_not_a_temporal_gloss() -> None:
    entries = load_hebrew_hungarian_lexicon(DEFAULT_HEBREW_LEXICON_HU_PATH)
    asher = entries["H0834A"]

    # The record must describe אֲשֶׁר, not the compound כַּאֲשֶׁר.
    assert asher.lemma == "אֲשֶׁר"

    # "amint"/"amikor" are minority contextual renderings ("when" is 49 of 4805
    # STEPBible glosses); they must not be the base meaning.
    assert "amint" not in asher.base_meaning_hu
    assert "amikor" not in asher.base_meaning_hu
    for expected in ("aki", "amely", "ami"):
        assert expected in asher.base_meaning_hu

    # The contextual renderings may still be listed as possibilities...
    assert "amikor" in asher.possible_meanings_hu
    # ...but never first.
    assert asher.possible_meanings_hu[0] == "aki"


@requires_corpus
def test_asher_lookup_matches_the_corpus_lemma() -> None:
    repository = HebrewHungarianLexiconRepository()
    resolution = repository.lookup("H0834A", expected_lemma="אֲשֶׁר")

    assert resolution.entry is not None
    assert resolution.resolution_type == "direct"
    # No lemma-mismatch warning: the record now describes the right word.
    assert not any("MÁSIK szóalakhoz" in warning for warning in resolution.warnings)


def test_lemma_mismatch_is_reported() -> None:
    """A record describing another word must say so rather than pose as fact.

    Phase 2C fully remediated the Phase-2B-flagged records (H3068G included —
    it now correctly resolves to יהוה, see
    test_h0853_is_no_longer_hijacked_after_the_phase2b_rebuild's sibling
    regression anchors), so the guard is exercised here with a deliberately
    wrong ``expected_lemma`` instead of depending on a specific record
    remaining broken.
    """
    repository = HebrewHungarianLexiconRepository()
    resolution = repository.lookup("H0834A", expected_lemma="לֹא־מֻגְדָּר")

    assert resolution.entry is not None
    assert any("MÁSIK szóalakhoz" in warning for warning in resolution.warnings)


def test_lemma_mismatch_ignores_pointing_only_differences() -> None:
    repository = HebrewHungarianLexiconRepository()
    resolution = repository.lookup("H1254A", expected_lemma="ברא")

    assert not any("MÁSIK szóalakhoz" in warning for warning in resolution.warnings)


@requires_tbesh
def test_h0853_is_no_longer_hijacked_after_the_phase2b_rebuild() -> None:
    """Regression anchor. Before Phase 2B's TBESH rebuild, H0853 (the object
    marker אֵת) resolved to the Aramaic יָת via a cross-reference row that
    had overwritten it — 21,890 corpus token references affected, the single
    largest instance of the hijack. The production database was rebuilt from
    the authoritative STEPBible TBESH source with the two-pass importer; this
    key must now be a genuine "direct" hit for its own lexeme.
    """
    from bible_engine.hebrew_lexicon_repository import HebrewLexiconRepository

    repository = HebrewLexiconRepository(DEFAULT_TBESH_DATABASE_PATH)
    resolved = repository.lookup("H0853")

    assert resolved.entry is not None
    assert resolved.resolution_type == "direct"
    assert resolved.entry.hebrew == "אֵת"


def test_cross_reference_rows_are_labelled_when_they_do_occur() -> None:
    """Unit-level guard test, independent of any specific database's current
    contents: a lookup whose stored row does not claim the requested id must
    report resolution_type="cross_reference", never "direct"."""
    from bible_engine.hebrew_lexicon_repository import HebrewLexiconRepository

    repository = HebrewLexiconRepository.__new__(HebrewLexiconRepository)
    repository.database_path = None  # type: ignore[assignment]
    repository.aliases = {}
    repository._entry = lambda strong_id: (  # type: ignore[method-assign]
        HebrewLexiconEntry(
            estrong="H3487",
            dstrong="H3487 = in Aramaic of",
            ustrong="H0853",
            hebrew="יָת",
            transliteration="yat",
            morph="A:Part",
            gloss="whom",
            meaning="",
        )
        if strong_id == "H0853"
        else None
    )

    hijacked = repository.lookup("H0853")

    assert hijacked.entry is not None
    assert hijacked.resolution_type == "cross_reference"


# --------------------------------------------------------------------------
# C. Decoded morphology must survive into the AI prompt.
# --------------------------------------------------------------------------


@requires_corpus
def test_token_block_supplies_decoded_grammar_not_only_raw_codes() -> None:
    from bible_engine.original_language_analysis import build_original_language_token_block

    block = build_original_language_token_block("1Móz 22,2")
    imperative_line = next(line for line in block.splitlines() if "קַח" in line)

    # The decoded facts Textus already knows are handed over explicitly...
    assert "igetörzs: qal" in imperative_line
    assert "igealak: imperativus" in imperative_line
    assert "személy: második személy" in imperative_line
    # ...and the raw code is kept only for traceability.
    assert "morf-kód: HVqv2ms" in imperative_line


@requires_corpus
def test_token_block_keeps_stem_and_form_separate() -> None:
    from bible_engine.original_language_analysis import build_original_language_token_block

    block = build_original_language_token_block("1Móz 1,1-3")
    wayyiqtol = next(line for line in block.splitlines() if "וַ/יֹּ֥אמֶר" in line)

    assert "igetörzs: qal" in wayyiqtol
    assert "igealak: wayyiqtol" in wayyiqtol
    assert "igetörzs: qal, wayyiqtol" not in wayyiqtol


@requires_corpus
def test_token_block_does_not_leak_english_grammar_terms() -> None:
    from bible_engine.original_language_analysis import build_original_language_token_block

    block = build_original_language_token_block("1Móz 1,1-3")

    for leaked in ("Conjunction + Verb", "Noun", "Preposition", "Perfect", "Participle"):
        assert leaked not in block, leaked


# --------------------------------------------------------------------------
# D. Phase 2B — TBESH rebuild regression anchors.
#
# Each of these was a real, corpus-verified failure mode of the pre-Phase-2B
# database (see docs/hebrew_analysis_v2_phase2a.md §6.4 and
# docs/hebrew_analysis_v2_phase2b.md). All are now rebuilt from the
# authoritative STEPBible TBESH source with the two-pass identity-first
# importer; none may regress to a cross-reference hijack.
# --------------------------------------------------------------------------


@requires_tbesh
@pytest.mark.parametrize(
    "strong_id,expected_hebrew,expected_gloss_substring",
    [
        ("H0834A", "אֲשֶׁר", "which"),  # the relative particle, not the compound כַּאֲשֶׁר
        ("H0834D", "כַּאֲשֶׁר", "which"),  # the compound keeps its own separate identity
        ("H3068G", "יְהֹוָה", "LORD"),  # the divine name, not שָׁלוֹם "peace"
        ("H0853", "אֵת", "Obj"),  # the object marker, not the Aramaic יָת
        ("H3478", "יִשְׂרָאֵל", "Israel"),  # not יְשֻׁרוּן "Jeshurun"
        ("H3484", "יְשֻׁרוּן", "Jeshurun"),  # Jeshurun keeps its own separate identity
    ],
)
def test_tbesh_identity_regression_anchors(strong_id, expected_hebrew, expected_gloss_substring) -> None:
    import unicodedata

    from bible_engine.hebrew_lexicon_repository import HebrewLexiconRepository

    repository = HebrewLexiconRepository(DEFAULT_TBESH_DATABASE_PATH)
    resolved = repository.lookup(strong_id)

    assert resolved.entry is not None, strong_id
    assert resolved.resolution_type == "direct", strong_id
    # NFC-normalize before comparing: combining-mark ORDER can legitimately
    # differ between a source-typed literal and the stored value while
    # representing the identical Hebrew text.
    assert unicodedata.normalize("NFC", resolved.entry.hebrew) == unicodedata.normalize(
        "NFC", expected_hebrew
    ), strong_id
    assert expected_gloss_substring in resolved.entry.gloss, strong_id


@requires_tbesh
def test_tbesh_rebuild_has_zero_cross_reference_keys() -> None:
    """No key in the production TBESH database may be held by a record that
    does not claim it — the exact defect class that caused the H0834A/H3068/
    Israel-Jeshurun corruption (see HebrewLexiconEntry.identity_strong_ids).
    """
    import sqlite3

    with sqlite3.connect(DEFAULT_TBESH_DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        hijacked = 0
        for row in connection.execute("SELECT strong_id, estrong, dstrong, ustrong FROM lexicon_entries"):
            entry = HebrewLexiconEntry(
                estrong=row["estrong"] or "",
                dstrong=row["dstrong"] or "",
                ustrong=row["ustrong"] or "",
                hebrew="",
                transliteration="",
                morph="",
                gloss="",
                meaning="",
            )
            if not entry.claims_strong_id(row["strong_id"]):
                hijacked += 1

    assert hijacked == 0


def test_source_corrected_records_are_fully_remediated() -> None:
    """Phase 2B flagged 443 Hungarian records translated from the then-
    contaminated TBESH data with "source_corrected_pending_retranslation".
    Phase 2C completed the remediation: every flagged record was either
    retranslated from the corrected TBESH source (347 records — 345 whose
    English gloss had genuinely changed, plus 2 more found to be wrong
    during verification despite a superficially matching gloss) or confirmed
    content-equivalent and had its deterministic fields refreshed (96
    records). None remain flagged.
    """
    entries = load_hebrew_hungarian_lexicon(DEFAULT_HEBREW_LEXICON_HU_PATH)

    flagged = [e for e in entries.values() if "source_corrected_pending_retranslation" in e.warnings]
    assert flagged == []

    # Retranslated records stay "ai_assisted" — a fresh AI translation, never
    # silently promoted to "human" merely because the source was fixed.
    # Only a genuinely hand-verified correction (H0834A, Phase 2A) is "human".
    retranslated_sample = entries["H0001G"]  # "father" — retranslated in Phase 2C batch 2
    assert retranslated_sample.translation_method == "ai_assisted"
    assert retranslated_sample.review_status == "draft"

    h0834a = entries["H0834A"]
    assert "source_corrected_pending_retranslation" not in h0834a.warnings
    assert h0834a.translation_method == "human"


def test_lemma_mismatch_guard_still_works_after_remediation() -> None:
    """The flag was metadata for remediation tracking; the thing that
    actually protects a live lookup is the lemma-mismatch guard (Phase 2A),
    which fires on ANY disagreement between a record's lemma and the
    requested word's actual corpus lemma — independent of whether the
    record ever carried the flag. Verified generically with a deliberately
    wrong ``expected_lemma`` against several now-remediated records, so the
    mechanism is proven without depending on any record remaining broken."""
    repository = HebrewHungarianLexiconRepository()
    entries = load_hebrew_hungarian_lexicon(DEFAULT_HEBREW_LEXICON_HU_PATH)
    sample = [entries[sid] for sid in ("H0001G", "H3068G", "H0853", "H3478") if sid in entries]
    assert sample

    for entry in sample:
        mismatched = repository.lookup(entry.strong_id, expected_lemma="לֹא־מֻגְדָּר")
        assert any("MÁSIK" in w for w in mismatched.warnings), entry.strong_id
