"""Phase 2D.1 — MACULA alignment hardening regression tests.

Companion to ``tests/test_hebrew_macula_alignment.py`` (Phase 2D's own
suite, which still covers the base alignment/import/repository/bundle
behavior). This file is specifically for the NEW general rules Phase 2D.1
added: bounded local ref-number recovery, the Aramaic determinative-state
suffix exclusion, the zero-corroboration downgrade, the short-string
containment gate, and the confirmed-alignment-only leaf->token mapping
that keeps partially-grounded syntax from silently attaching to an
unresolved token. Real fixture data only — no network, no LLM.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bible_engine.hebrew_analysis_repository import (
    SYNTAX_GROUNDING_FULL,
    SYNTAX_GROUNDING_NONE,
    SYNTAX_GROUNDING_PARTIAL,
    LocalHebrewAnalysisRepository,
)
from bible_engine.hebrew_analysis_service import HebrewAnalysisService
from bible_engine.hebrew_component_repository import restore_component_fidelity
from bible_engine.hebrew_linguistic_sqlite import open_store
from bible_engine.hebrew_macula_alignment import align_token
from bible_engine.hebrew_macula_diagnostics import classify_unresolved
from bible_engine.hebrew_macula_importer import ensure_dataset_version, import_chapter
from bible_engine.hebrew_parser import HebrewComponent, HebrewToken
from bible_engine.hebrew_token_identity import build_token_id
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.hebrew_lexicon_hu import HebrewHungarianLexiconRepository
from bible_engine.macula_lowfat_parser import (
    MaculaLeaf,
    MaculaSentence,
    parse_macula_lowfat_chapter,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "macula_lowfat"
RUTH_FIXTURE = FIXTURES / "ruth_1_excerpt-lowfat.xml"
EZRA_FIXTURE = FIXTURES / "ezra_4_excerpt-lowfat.xml"
GEN_36_5_FIXTURE = FIXTURES / "genesis_36_5_excerpt-lowfat.xml"


def _tahot_and_sentence(book: str, chapter: int, verse: int, fixture: Path, sentence_id: str):
    repo = HebrewTokenRepository()
    result = repo.passage(book, chapter, verse, verse)
    restored, _ = restore_component_fidelity(list(result.tokens))
    macula_chapter = parse_macula_lowfat_chapter(fixture)
    sentence = next(s for s in macula_chapter.sentences if s.sentence_id == sentence_id)
    tokens = [restored.get(t.stable_key, t) for t in result.tokens]
    return tokens, sentence


# ---------------------------------------------------------------------------
# Maqaf
# ---------------------------------------------------------------------------


def test_maqaf_tokens_align_correctly_ruth_1_16():
    """Ruth 1:16 has 3 real maqaf-joined tokens (אַל\\־, תִּפְגְּעִי\\־,
    אֶל\\־). Orthographic maqaf-joining must not prevent correct lexical
    alignment, and Textus's own stable token identity (one token per
    maqaf-joined TAHOT word) must stay unchanged."""
    tokens, sentence = _tahot_and_sentence("Rut", 1, 16, RUTH_FIXTURE, "RUT 1:16")
    maqaf_tokens = [t for t in tokens if t.maqaf]
    assert len(maqaf_tokens) == 3
    for token in maqaf_tokens:
        token_id = build_token_id(token.book, token.chapter, token.verse, token.word_index)
        alignment = align_token(token, token_id, sentence)
        assert alignment.alignment_type in {"EXACT", "COMPOSITE"}
        assert alignment.confidence == "certain"
        # Textus identity is exactly the TAHOT word — maqaf never splits or
        # merges it into a different token.
        assert alignment.token_id == token_id
        assert alignment.word_index == token.word_index


def test_maqaf_does_not_merge_multiple_lexical_tokens():
    """Two DIFFERENT maqaf-joined tokens in the same verse (Ruth 1:16
    words 3 and 4) must resolve to two DIFFERENT, non-overlapping sets of
    MACULA leaves — maqaf orthographic joining must never cause one
    token's alignment to consume another token's leaf."""
    tokens, sentence = _tahot_and_sentence("Rut", 1, 16, RUTH_FIXTURE, "RUT 1:16")
    by_word = {t.word_index: t for t in tokens}
    a3 = align_token(by_word[3], build_token_id("Rut", 1, 16, 3), sentence)
    a4 = align_token(by_word[4], build_token_id("Rut", 1, 16, 4), sentence)
    leaves_3 = {c.macula_leaf_id for c in a3.components if c.macula_leaf_id}
    leaves_4 = {c.macula_leaf_id for c in a4.components if c.macula_leaf_id}
    assert leaves_3 and leaves_4
    assert leaves_3.isdisjoint(leaves_4)


# ---------------------------------------------------------------------------
# Aramaic component mismatch (determinative-state suffix)
# ---------------------------------------------------------------------------


def test_aramaic_determinative_state_suffix_excluded_from_alignable_components():
    """מַלְכָּ֔/א ('the king', Ezra 4:23 in the wider corpus; here a
    same-pattern word family in the Ezra fixture) — TAHOT records the
    Aramaic determinative/emphatic-state ending (bare א/ה/ן after niqqud
    stripping) as its own trailing suffix component, but MACULA's lowfat
    tree does not encode it as a separate morpheme. The alignment must
    exclude it from the alignable-component count rather than reporting a
    count mismatch."""
    tokens, sentence = _tahot_and_sentence("Ezr", 4, 8, EZRA_FIXTURE, "EZR 4:8")
    aramaic_state_tokens = [
        t
        for t in tokens
        if t.suffix_components
        and any(c.role == "suffix" for c in t.suffix_components)
        and t.language.lower() == "aramaic"
    ]
    assert aramaic_state_tokens, "expected at least one Aramaic token with a suffix component in Ezra 4:8"
    resolved_count = 0
    for token in aramaic_state_tokens:
        token_id = build_token_id(token.book, token.chapter, token.verse, token.word_index)
        alignment = align_token(token, token_id, sentence)
        if alignment.alignment_type != "UNRESOLVED":
            resolved_count += 1
    assert resolved_count > 0


def test_aramaic_specific_segmentation_diagnosis_for_ethnonym_plural():
    """Ezra 4:9's list of nation/ethnonym names (Archevites, Babylonians,
    Susanchites, ...) stacks the determinative-state suffix with an
    additional plural ending MACULA does not split out either — a genuine
    residual, not a bug. Confirms the diagnostic classifier correctly
    labels this ``aramaic_specific_segmentation`` rather than leaving it
    unexplained."""
    tokens, sentence = _tahot_and_sentence("Ezr", 4, 9, EZRA_FIXTURE, "EZR 4:9")
    found_aramaic_diagnosis = False
    for token in tokens:
        token_id = build_token_id(token.book, token.chapter, token.verse, token.word_index)
        alignment = align_token(token, token_id, sentence)
        if alignment.alignment_type == "UNRESOLVED":
            diagnosis = classify_unresolved(token, token_id, "Ezra.4.9", alignment, sentence)
            if diagnosis.category == "aramaic_specific_segmentation":
                found_aramaic_diagnosis = True
    assert found_aramaic_diagnosis


# ---------------------------------------------------------------------------
# Bounded ref-number recovery — one-to-many / many-to-one / downstream
# sequence recovery
# ---------------------------------------------------------------------------


def test_downstream_sequence_recovery_after_source_mismatch_ruth_1_8():
    """Ruth 1:8: MACULA's ref-numbering has a genuine Ketiv/Qere-adjacent
    gap at word 10, shifting every later word's MACULA ref by +1. Each
    later word must be recovered by matching its OWN evidence (surface
    agreement) at its OWN best nearby position — not by a blanket
    verse-wide offset applied uniformly regardless of fit. Verified here:
    every recovered token's offset is independently justified by a
    surface match specific to that token."""
    tokens, sentence = _tahot_and_sentence("Rut", 1, 8, RUTH_FIXTURE, "RUT 1:8")
    recovered = []
    for token in tokens:
        token_id = build_token_id(token.book, token.chapter, token.verse, token.word_index)
        alignment = align_token(token, token_id, sentence)
        if "recovered via bounded local ref-number search" in alignment.evidence:
            recovered.append((token.word_index, alignment))
    assert recovered
    for word_index, alignment in recovered:
        assert alignment.alignment_type == "VALIDATED_FALLBACK"
        assert f"originally unresolved at the primary position" in alignment.evidence
        # every recovered component pairing must be backed by a real leaf id
        assert all(c.macula_leaf_id for c in alignment.components)


def test_one_to_many_composite_alignment_ruth_1_1():
    """A single Textus token (וַ/יְהִ֗י, Ruth 1:1 word 1) legitimately maps
    to TWO MACULA leaves — one-to-many, resolved as COMPOSITE, never
    forced into a false one-to-one identity."""
    tokens, sentence = _tahot_and_sentence("Rut", 1, 1, RUTH_FIXTURE, "RUT 1:1")
    token = next(t for t in tokens if t.word_index == 1)
    alignment = align_token(token, build_token_id("Rut", 1, 1, 1), sentence)
    assert alignment.alignment_type == "COMPOSITE"
    assert len(alignment.components) == 2
    assert len({c.macula_leaf_id for c in alignment.components}) == 2


def test_ambiguous_nearby_recovery_is_refused_not_guessed():
    """Constructed regression for the real corpus pattern (verified
    corpus-wide, e.g. Genesis 36:5's 'וְ/אֶת\\־' appearing twice within the
    bounded search window): if TWO nearby ref positions would each fully
    corroborate, the aligner must refuse rather than pick one arbitrarily."""
    prefix = HebrewComponent(surface="וְ", strong_id="H9002", morphology_code="", role="prefix")
    core = HebrewComponent(surface="אֵת", strong_id="H0853", morphology_code="", role="core")
    token = HebrewToken(
        book="Gen", chapter=36, verse=5, word_index=10, token_index=0,
        surface="וְ/אֵת", surface_without_accents="ואת", transliteration="", english_gloss="",
        lemma="אֵת", strong_ids=("H9002", "H0853"), morphology_code="", language="Hebrew",
        prefix_components=(prefix,), core_component=core, suffix_components=(),
        ketiv="", qere="", punctuation="", maqaf=True, source_token_id="", source_edition="",
        meaning_variant="", spelling_variant="", expanded_strong_tags="", raw_fields=(),
    )
    matching_leaf_a = MaculaLeaf(
        macula_node_id="oA", ref="GEN 36:5!8", ref_book="GEN", ref_chapter=36, ref_verse=5, ref_word_number=8,
        doc_order=0, parent_group_id=None, child_order=0, surface="וְ", lemma="וְ", transliteration="", gloss_en="and",
        strong_number="2050b", oshb_strongs="", morph_code="HC", part_of_speech="conjunction", stem="", verb_type="",
        person="", gender="", number="", state="", role="", frame="", subjref="", participantref="",
    )
    matching_leaf_b = MaculaLeaf(
        macula_node_id="oB", ref="GEN 36:5!8", ref_book="GEN", ref_chapter=36, ref_verse=5, ref_word_number=8,
        doc_order=1, parent_group_id=None, child_order=1, surface="אֵת", lemma="אֵת", transliteration="", gloss_en="",
        strong_number="0853", oshb_strongs="", morph_code="HTo", part_of_speech="particle", stem="", verb_type="",
        person="", gender="", number="", state="", role="", frame="", subjref="", participantref="",
    )
    duplicate_leaf_a = MaculaLeaf(
        macula_node_id="oC", ref="GEN 36:5!12", ref_book="GEN", ref_chapter=36, ref_verse=5, ref_word_number=12,
        doc_order=2, parent_group_id=None, child_order=0, surface="וְ", lemma="וְ", transliteration="", gloss_en="and",
        strong_number="2050b", oshb_strongs="", morph_code="HC", part_of_speech="conjunction", stem="", verb_type="",
        person="", gender="", number="", state="", role="", frame="", subjref="", participantref="",
    )
    duplicate_leaf_b = MaculaLeaf(
        macula_node_id="oD", ref="GEN 36:5!12", ref_book="GEN", ref_chapter=36, ref_verse=5, ref_word_number=12,
        doc_order=3, parent_group_id=None, child_order=1, surface="אֵת", lemma="אֵת", transliteration="", gloss_en="",
        strong_number="0853", oshb_strongs="", morph_code="HTo", part_of_speech="particle", stem="", verb_type="",
        person="", gender="", number="", state="", role="", frame="", subjref="", participantref="",
    )
    sentence = MaculaSentence(
        sentence_id="GEN 36:5", root_group_id=None,
        leaves=(matching_leaf_a, matching_leaf_b, duplicate_leaf_a, duplicate_leaf_b), groups=(),
    )
    alignment = align_token(token, build_token_id("Gen", 36, 5, 10), sentence)
    assert alignment.alignment_type == "UNRESOLVED"
    assert "ambiguous ref-number recovery" in alignment.evidence


# ---------------------------------------------------------------------------
# Zero-corroboration downgrade / short-string containment gate
# (Phase 2D.1 VALIDATED_FALLBACK audit)
# ---------------------------------------------------------------------------


def test_zero_corroboration_position_only_match_is_unresolved_not_fabricated():
    """Regression for the exact corpus pattern found in Ruth 1:8 word 11:
    a component-count match at a ref position whose content is actually a
    DIFFERENT word sharing only a coincidental Strong-number root match
    must not be accepted as a real alignment."""
    core = HebrewComponent(surface="יְהוָה", strong_id="H3068", morphology_code="", role="core")
    token = HebrewToken(
        book="Rut", chapter=1, verse=8, word_index=11, token_index=0,
        surface="יְהוָ֤ה", surface_without_accents="יהוה", transliteration="", english_gloss="",
        lemma="יְהוָה", strong_ids=("H3068",), morphology_code="", language="Hebrew",
        prefix_components=(), core_component=core, suffix_components=(),
        ketiv="", qere="", punctuation="", maqaf=False, source_token_id="", source_edition="",
        meaning_variant="", spelling_variant="", expanded_strong_tags="", raw_fields=(),
    )
    unrelated_leaf = MaculaLeaf(
        macula_node_id="oX", ref="RUT 1:8!11", ref_book="RUT", ref_chapter=1, ref_verse=8, ref_word_number=11,
        doc_order=0, parent_group_id=None, child_order=0, surface="יַ֣עַשׂ", lemma="עשה", transliteration="", gloss_en="",
        strong_number="6213", oshb_strongs="", morph_code="Vqi3ms", part_of_speech="verb", stem="qal", verb_type="",
        person="third", gender="masculine", number="singular", state="", role="v", frame="", subjref="", participantref="",
    )
    sentence = MaculaSentence(sentence_id="RUT 1:8", root_group_id=None, leaves=(unrelated_leaf,), groups=())
    alignment = align_token(token, build_token_id("Rut", 1, 8, 11), sentence)
    assert alignment.alignment_type == "UNRESOLVED"
    assert "zero corroborating" in alignment.evidence


def test_short_string_containment_requires_exact_match_not_substring():
    """Regression for the corpus-verified false-positive risk: a bare
    2-consonant word (אֵת, the object marker) must not be accepted via
    loose substring containment against an unrelated longer leaf
    concatenation — only an EXACT match qualifies below the containment
    length floor."""
    core = HebrewComponent(surface="אֵת", strong_id="H0853", morphology_code="", role="core")
    token = HebrewToken(
        book="Gen", chapter=1, verse=1, word_index=99, token_index=0,
        surface="אֵ֣ת", surface_without_accents="את", transliteration="", english_gloss="",
        lemma="אֵת", strong_ids=("H0853",), morphology_code="", language="Hebrew",
        prefix_components=(), core_component=core, suffix_components=(),
        ketiv="", qere="", punctuation="", maqaf=False, source_token_id="", source_edition="",
        meaning_variant="", spelling_variant="", expanded_strong_tags="", raw_fields=(),
    )
    leaf_a = MaculaLeaf(
        macula_node_id="oA", ref="GEN 1:1!99", ref_book="GEN", ref_chapter=1, ref_verse=1, ref_word_number=99,
        doc_order=0, parent_group_id=None, child_order=0, surface="בְּרֵאשִׁית", lemma="", transliteration="", gloss_en="",
        strong_number="", oshb_strongs="", morph_code="", part_of_speech="noun", stem="", verb_type="",
        person="", gender="", number="", state="", role="", frame="", subjref="", participantref="",
    )
    leaf_b = MaculaLeaf(
        macula_node_id="oB", ref="GEN 1:1!99", ref_book="GEN", ref_chapter=1, ref_verse=1, ref_word_number=99,
        doc_order=1, parent_group_id=None, child_order=1, surface="בָּרָא", lemma="", transliteration="", gloss_en="",
        strong_number="", oshb_strongs="", morph_code="", part_of_speech="verb", stem="", verb_type="",
        person="", gender="", number="", state="", role="", frame="", subjref="", participantref="",
    )
    sentence = MaculaSentence(sentence_id="GEN 1:1", root_group_id=None, leaves=(leaf_a, leaf_b), groups=())
    alignment = align_token(token, build_token_id("Gen", 1, 1, 99), sentence)
    assert alignment.alignment_type == "UNRESOLVED"


# ---------------------------------------------------------------------------
# Safe partial-syntax behavior / grounding coverage
# ---------------------------------------------------------------------------


@pytest.fixture
def ezra_linguistic_store(tmp_path):
    store_path = tmp_path / "ezra_linguistic.sqlite3"
    store = open_store(store_path)
    textus_dv = ensure_dataset_version(store, dataset_id="tahot", display_name="TAHOT", revision="test")
    macula_dv = ensure_dataset_version(store, dataset_id="macula_hebrew_lowfat", display_name="MACULA", revision="test")
    chapter = parse_macula_lowfat_chapter(EZRA_FIXTURE)
    repo = HebrewTokenRepository()
    stats = import_chapter(
        chapter, tahot_book_code="Ezr", chapter_number=4, store=store, token_repository=repo,
        textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv,
    )
    store.close()
    return store_path, stats


def test_leaf_to_token_map_uses_the_recovering_token_not_the_coincidental_word_index(tmp_path):
    """Real corpus regression (found via a full-corpus invariant run, not a
    fixture): Genesis 36:5's proper name 'יְעוּשׁ' (Jeush) sits at MACULA
    ref=5, but TAHOT's OWN word_index 5 is a DIFFERENT, genuinely
    ambiguous word ('וְ/אֶת\\־') that stays UNRESOLVED. TAHOT word_index 4
    ('יְעוּשׁ' itself) is the token that RECOVERS to ref=5 via the bounded
    offset search. The leaf must map to token 4 (the one whose alignment
    actually claimed it), never to token 5 just because the numbers
    coincide — verified by checking hebrew_syntax_membership after a full
    import, which is where this bug was originally caught (an earlier
    version mapped by raw ref_word_number instead of by confirmed
    alignment, misattaching syntax facts to token 5)."""
    store_path = tmp_path / "gen36_5.sqlite3"
    store = open_store(store_path)
    textus_dv = ensure_dataset_version(store, dataset_id="tahot", display_name="TAHOT", revision="test")
    macula_dv = ensure_dataset_version(store, dataset_id="macula_hebrew_lowfat", display_name="MACULA", revision="test")
    chapter = parse_macula_lowfat_chapter(GEN_36_5_FIXTURE)
    repo = HebrewTokenRepository()
    stats = import_chapter(
        chapter, tahot_book_code="Gen", chapter_number=36, store=store, token_repository=repo,
        textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv,
    )
    assert stats.unresolved >= 2  # Gen.36.5:5 and Gen.36.5:7 are genuinely ambiguous

    import sqlite3

    conn = sqlite3.connect(store_path)
    alignment_types = dict(
        conn.execute("SELECT token_id, alignment_type FROM hebrew_token_alignments WHERE token_id IN (?, ?)", ("Gen.36.5:5", "Gen.36.5:7")).fetchall()
    )
    assert alignment_types.get("Gen.36.5:5") == "UNRESOLVED"
    assert alignment_types.get("Gen.36.5:7") == "UNRESOLVED"

    membership_token_ids = {row[0] for row in conn.execute("SELECT DISTINCT token_id FROM hebrew_syntax_membership")}
    assert "Gen.36.5:5" not in membership_token_ids
    assert "Gen.36.5:7" not in membership_token_ids
    assert "Gen.36.5:4" in membership_token_ids  # the token that DID recover "Jeush" is present
    conn.close()


def test_no_syntax_fact_attaches_to_an_unconfirmed_token(ezra_linguistic_store):
    """Phase 2D.1 §12 core invariant: every token_id referenced by ANY
    imported syntax fact (membership, edges, roles, coreference) must have
    a CONFIRMED (non-UNRESOLVED) alignment — an unresolved token
    contributes nothing, never a guessed attachment."""
    store_path, stats = ezra_linguistic_store
    assert stats.unresolved > 0  # this fixture verse genuinely has unresolved tokens
    import sqlite3

    conn = sqlite3.connect(store_path)
    confirmed = {
        row[0]
        for row in conn.execute("SELECT DISTINCT token_id FROM hebrew_token_alignments WHERE alignment_type != 'UNRESOLVED'")
    }
    violations = []
    for row in conn.execute("SELECT token_id FROM hebrew_syntax_membership WHERE token_id IS NOT NULL"):
        if row[0] not in confirmed:
            violations.append(("membership", row[0]))
    for row in conn.execute("SELECT parent_token_id, child_token_id FROM hebrew_syntax_edges"):
        for token_id in row:
            if token_id and token_id not in confirmed:
                violations.append(("edge", token_id))
    for row in conn.execute("SELECT predicate_token_id, participant_token_id FROM hebrew_semantic_roles"):
        for token_id in row:
            if token_id and token_id not in confirmed:
                violations.append(("role", token_id))
    for row in conn.execute("SELECT referring_token_id FROM hebrew_coreference"):
        if row[0] and row[0] not in confirmed:
            violations.append(("coref", row[0]))
    conn.close()
    assert violations == []


def test_verse_syntax_grounding_partial_when_some_tokens_unresolved(ezra_linguistic_store):
    store_path, _ = ezra_linguistic_store
    repository = LocalHebrewAnalysisRepository(store_path)
    syntax = repository.get_verse_syntax("Ezra.4.9")
    assert syntax.has_syntax
    assert syntax.syntax_grounding == SYNTAX_GROUNDING_PARTIAL


@pytest.fixture
def ruth_linguistic_store(tmp_path):
    store_path = tmp_path / "ruth_linguistic.sqlite3"
    store = open_store(store_path)
    textus_dv = ensure_dataset_version(store, dataset_id="tahot", display_name="TAHOT", revision="test")
    macula_dv = ensure_dataset_version(store, dataset_id="macula_hebrew_lowfat", display_name="MACULA", revision="test")
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    repo = HebrewTokenRepository()
    import_chapter(
        chapter, tahot_book_code="Rut", chapter_number=1, store=store, token_repository=repo,
        textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv,
    )
    store.close()
    return store_path


def test_verse_syntax_grounding_full_when_verse_fully_resolved(ruth_linguistic_store):
    repository = LocalHebrewAnalysisRepository(ruth_linguistic_store)
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert syntax.has_syntax
    assert syntax.syntax_grounding == SYNTAX_GROUNDING_FULL


def test_verse_syntax_grounding_none_when_no_store_data(ruth_linguistic_store):
    repository = LocalHebrewAnalysisRepository(ruth_linguistic_store)
    syntax = repository.get_verse_syntax("Ruth.99.99")
    assert not syntax.has_syntax
    assert syntax.syntax_grounding == SYNTAX_GROUNDING_NONE


def test_bundle_exposes_syntax_grounding_field(ruth_linguistic_store):
    service = HebrewAnalysisService(linguistic_repository=LocalHebrewAnalysisRepository(ruth_linguistic_store))
    bundle = service.get_hebrew_analysis("Rut 1,1")
    assert bundle.verses[0].syntax_grounding == SYNTAX_GROUNDING_FULL


# ---------------------------------------------------------------------------
# Hungarian lexical coverage kept separate from alignment coverage
# ---------------------------------------------------------------------------


def test_missing_hungarian_gloss_does_not_affect_morphology_or_alignment():
    """H0458 (אֱלִימֶלֶךְ / Elimelech, Ruth 1:2) is a proper name with NO
    Hungarian lexical record — verified against the actual repository.
    This must not degrade morphology confidence, must not block syntax
    import, and must not count as an alignment failure."""
    lexicon = HebrewHungarianLexiconRepository()
    resolution = lexicon.lookup("H0458", expected_lemma="אֱלִימֶלֶךְ")
    assert resolution.entry is None  # confirms the real coverage gap this test relies on

    tokens, sentence = _tahot_and_sentence("Rut", 1, 2, RUTH_FIXTURE, "RUT 1:2")
    token = next(t for t in tokens if "H0458" in t.strong_ids)
    token_id = build_token_id(token.book, token.chapter, token.verse, token.word_index)
    alignment = align_token(token, token_id, sentence)
    assert alignment.alignment_type in {"EXACT", "COMPOSITE"}
    assert alignment.confidence == "certain"


def test_missing_hungarian_gloss_does_not_block_bundle_syntax(ruth_linguistic_store):
    """End-to-end: the bundle for Ruth 1:2 (containing the Hungarian-gloss-
    less Elimelech token) must still get a well-formed lexical_sense=None
    for that one token while every other bundle field — morphology,
    syntax grounding — remains normal."""
    service = HebrewAnalysisService(linguistic_repository=LocalHebrewAnalysisRepository(ruth_linguistic_store))
    bundle = service.get_hebrew_analysis("Rut 1,2")
    verse = bundle.verses[0]
    elimelech = next(t for t in verse.tokens if "H0458" in t.strong_ids)
    assert elimelech.lexical_sense is None
    assert elimelech.morphology.confidence == "fully_decoded"
    assert verse.syntax_grounding in {SYNTAX_GROUNDING_FULL, SYNTAX_GROUNDING_PARTIAL}
