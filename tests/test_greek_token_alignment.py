"""Phase 2B §2/§3/§12 — TAGNT ↔ MACULA alignment: determinism, ambiguity
handling, and the two concrete cases this phase's investigation uncovered
(a K/O-only textual variant, and a genuine word-order transposition)."""

from __future__ import annotations

from bible_engine.greek_token_alignment import align_verse_tokens
from bible_engine.macula_greek_parser import MaculaGreekToken
from bible_engine.tagnt_parser import GreekToken


def _tagnt(word_index: int, form: str, lemma: str, strong: str, edition_flags: str = "NKO") -> GreekToken:
    return GreekToken(
        book="Jhn", chapter=3, verse=16, word_index=word_index,
        greek_form=form, lemma=lemma, morph_code="N-NSM", strong_id=strong, edition_flags=edition_flags,
    )


def _macula(xml_id: str, word_index: int, text: str, lemma: str, strong: str, case: str = "") -> MaculaGreekToken:
    return MaculaGreekToken(
        xml_id=xml_id, book="JHN", chapter=3, verse=16, word_index=word_index,
        role="", word_class="", word_type="", text=text, after=" ", lemma=lemma, normalized=text,
        strong=strong, morph="", person="", number="", gender="", case=case, tense="", voice="",
        mood="", degree="", domain="", ln="", frame="", subjref="", referent="",
    )


def test_alignment_is_deterministic_across_repeated_runs() -> None:
    tagnt = [_tagnt(1, "λόγος", "λόγος", "G3056"), _tagnt(2, "θεοῦ", "θεός", "G2316")]
    macula = [_macula("n1", 1, "λόγος", "λόγος", "3056"), _macula("n2", 2, "θεοῦ", "θεός", "2316")]

    first = align_verse_tokens(tagnt, macula)
    second = align_verse_tokens(tagnt, macula)

    assert first == second


def test_every_tagnt_token_receives_exactly_one_alignment_record() -> None:
    tagnt = [_tagnt(i, f"w{i}", f"lemma{i}", f"G{i:04d}") for i in range(1, 6)]
    macula = [_macula(f"n{i}", i, f"w{i}", f"lemma{i}", str(i)) for i in range(1, 4)]  # fewer MACULA tokens

    results = align_verse_tokens(tagnt, macula)

    assert len(results) == len(tagnt)
    assert [r.tagnt_token_id for r in results] == [f"Jhn.3.16:{i}" for i in range(1, 6)]


def test_exact_surface_match() -> None:
    tagnt = [_tagnt(1, "θεὸς", "θεός", "G2316")]
    macula = [_macula("n1", 1, "θεὸς", "θεός", "2316")]

    result = align_verse_tokens(tagnt, macula)[0]

    assert result.status == "EXACT"
    assert result.macula_xml_id == "n1"


def test_composite_match_on_elision_spelling_variant() -> None:
    tagnt = [_tagnt(1, "ἀλλ᾽", "ἀλλά", "G0235")]
    macula = [_macula("n1", 1, "ἀλλὰ", "ἀλλά", "235")]

    result = align_verse_tokens(tagnt, macula)[0]

    assert result.status == "COMPOSITE"
    assert result.macula_xml_id == "n1"


def test_textual_variant_absent_from_target_edition_is_classified_not_dropped() -> None:
    """The real Jn 3:16 case this phase's investigation found: "αὐτοῦ"
    (edition_flags="ko" — present in K/Traditional and O/Other, absent
    from N/Ancient) has no SBLGNT counterpart (SBLGNT follows the N/
    Ancient tradition) — an EXPECTED absence, not a failure."""
    tagnt = [
        _tagnt(1, "υἱὸν", "υἱός", "G5207", edition_flags="NKO"),
        _tagnt(2, "αὐτοῦ", "αὐτός", "G0846", edition_flags="ko"),
        _tagnt(3, "τὸν", "ὁ", "G3588", edition_flags="NKO"),
    ]
    object.__setattr__(tagnt[1], "morph_code", "P-GSM")  # genitive — real TAGNT data always carries case here
    macula = [
        _macula("n1", 1, "υἱὸν", "υἱός", "5207", case="accusative"),
        _macula("n2", 2, "τὸν", "ὁ", "3588", case="accusative"),
    ]

    results = align_verse_tokens(tagnt, macula)

    assert results[0].status == "EXACT"
    assert results[1].status == "UNRESOLVED_TEXTUAL_VARIANT"
    assert results[1].macula_xml_id is None
    assert "edition_flags=ko" in results[1].evidence[0]
    assert results[2].status == "EXACT"
    assert results[2].macula_xml_id == "n2"


def test_ancient_tradition_token_with_no_counterpart_is_unresolved_other() -> None:
    tagnt = [_tagnt(1, "ξένον", "ξένος", "G3581", edition_flags="NKO")]
    macula: list[MaculaGreekToken] = []

    result = align_verse_tokens(tagnt, macula)[0]

    assert result.status == "UNRESOLVED_OTHER"
    assert result.macula_xml_id is None


def test_word_order_transposition_resolves_correctly_not_as_a_cascade_failure() -> None:
    """1 Cor 1:2's well-documented clause-order variant: TAGNT places
    "τῇ οὔσῃ ἐν Κορίνθῳ" before "ἡγιασμένοις ἐν Χριστῷ Ἰησοῦ"; SBLGNT has
    them swapped. Both four-word chunks are fully intact — this must
    resolve via the whole-verse fallback tier, not cascade into a run of
    UNRESOLVED_OTHER for every token after the first mismatch."""
    tagnt = [
        _tagnt(1, "τῇ", "ὁ", "G3588"),
        _tagnt(2, "οὔσῃ", "εἰμί", "G1510"),
        _tagnt(3, "ἐν", "ἐν", "G1722"),
        _tagnt(4, "Κορίνθῳ", "Κόρινθος", "G2882"),
        _tagnt(5, "ἡγιασμένοις", "ἁγιάζω", "G0037"),
        _tagnt(6, "ἐν", "ἐν", "G1722"),
        _tagnt(7, "Χριστῷ", "Χριστός", "G5547"),
    ]
    macula = [
        _macula("n5", 1, "ἡγιασμένοις", "ἁγιάζω", "37"),
        _macula("n6", 2, "ἐν", "ἐν", "1722"),
        _macula("n7", 3, "Χριστῷ", "Χριστός", "5547"),
        _macula("n1", 4, "τῇ", "ὁ", "3588"),
        _macula("n2", 5, "οὔσῃ", "εἰμί", "1510"),
        _macula("n3", 6, "ἐν", "ἐν", "1722"),
        _macula("n4", 7, "Κορίνθῳ", "Κόρινθος", "2882"),
    ]

    results = align_verse_tokens(tagnt, macula)

    resolved = {r.tagnt_token_id: r.status for r in results}
    assert all(status in ("EXACT",) for status in resolved.values())
    by_id = {r.tagnt_token_id: r.macula_xml_id for r in results}
    assert by_id["Jhn.3.16:1"] == "n1"
    assert by_id["Jhn.3.16:5"] == "n5"
    assert by_id["Jhn.3.16:7"] == "n7"


def test_repeated_common_lemma_does_not_cross_match_wrong_occurrence() -> None:
    """Regression for the bug this phase's own alignment work found and
    fixed: a lemma+Strong-only match (no morphology check) let a genitive
    αὐτοῦ falsely match a distant, unrelated accusative αὐτὸν sharing the
    same lemma. The whole-verse fallback tier must require morphological
    (case) agreement, not lemma+Strong alone, once local matching fails."""
    tagnt = [
        _tagnt(1, "αὐτοῦ", "αὐτός", "G0846"),  # genitive, morph_code encodes GSM below
        _tagnt(2, "λόγος", "λόγος", "G3056"),
        _tagnt(3, "αὐτὸν", "αὐτός", "G0846"),  # accusative
    ]
    # Force genitive morph on token 1 and accusative on token 3.
    tagnt[0] = _tagnt(1, "αὐτοῦ", "αὐτός", "G0846")
    object.__setattr__(tagnt[0], "morph_code", "P-GSM")
    tagnt[2] = _tagnt(3, "αὐτὸν", "αὐτός", "G0846")
    object.__setattr__(tagnt[2], "morph_code", "P-ASM")

    macula = [
        # No token 1 counterpart at all (simulates a local-window miss).
        _macula("n2", 1, "λόγος", "λόγος", "3056"),
        _macula("n3", 2, "αὐτὸν", "αὐτός", "846", case="accusative"),
    ]

    results = align_verse_tokens(tagnt, macula)
    # Token 1 (genitive) must NOT be matched to n3 (accusative) — either
    # unresolved or matched to a genuine genitive candidate, never to a
    # morphology-incompatible one.
    assert results[0].macula_xml_id != "n3"
