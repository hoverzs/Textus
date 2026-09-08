"""Phase 2D tests — MACULA parsing, TAHOT/MACULA alignment, the offline
importer, the repository abstraction, and the extended
``HebrewAnalysisBundle``. Uses only the small, real, committed MACULA
fixtures under ``tests/fixtures/macula_lowfat/`` (trimmed real excerpts,
not the full corpus) — no network access anywhere in this file.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import bible_engine.hebrew_analysis_repository as repository_module
import bible_engine.hebrew_macula_alignment as alignment_module
import bible_engine.hebrew_macula_importer as importer_module
import bible_engine.macula_lowfat_parser as parser_module
from bible_engine.hebrew_analysis_bundle import BUNDLE_SCHEMA_VERSION
from bible_engine.hebrew_analysis_repository import LocalHebrewAnalysisRepository, VerseSyntaxData
from bible_engine.hebrew_analysis_service import HebrewAnalysisService
from bible_engine.hebrew_component_repository import restore_component_fidelity
from bible_engine.hebrew_linguistic_sqlite import open_store
from bible_engine.hebrew_macula_alignment import align_token
from bible_engine.hebrew_macula_importer import ensure_dataset_version, import_chapter
from bible_engine.hebrew_token_identity import build_token_id
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.macula_lowfat_parser import parse_macula_lowfat_chapter, strip_hebrew_points

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "macula_lowfat"
RUTH_FIXTURE = FIXTURES / "ruth_1_excerpt-lowfat.xml"
GENESIS_FIXTURE = FIXTURES / "genesis_excerpt-lowfat.xml"
EZRA_FIXTURE = FIXTURES / "ezra_4_excerpt-lowfat.xml"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parses_ordinary_and_multicomponent_tokens():
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    sentence = next(s for s in chapter.sentences if s.sentence_id == "RUT 1:1")
    buckets = sentence.leaves_by_ref_word()
    # Compared consonants-only (strip_hebrew_points): the source XML's
    # combining-mark codepoint ORDER can legitimately differ from a
    # hand-typed literal while remaining canonically/visually identical
    # (verified: NFC-equivalent, just a different combining-class order for
    # the same rendered word) — comparing full-precision here would make
    # the test depend on an accidental typing artifact, not a real fact.
    assert [strip_hebrew_points(leaf.surface) for leaf in buckets[3]] == ["שפט"]  # ordinary, 1 leaf
    assert [strip_hebrew_points(leaf.surface) for leaf in buckets[1]] == ["ו", "יהי"]  # multi-component, 2 leaves


def test_parses_phrase_and_clause_groups():
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    sentence = next(s for s in chapter.sentences if s.sentence_id == "RUT 1:1")
    assert any(g.macula_class == "cl" for g in sentence.groups)
    assert any(g.macula_class in {"pp", "np"} for g in sentence.groups)


def test_parses_subject_predicate_role_codes():
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    sentence = next(s for s in chapter.sentences if s.sentence_id == "RUT 1:1")
    roles = {leaf.role for leaf in sentence.leaves if leaf.role}
    assert "v" in roles  # predicate
    assert "s" in roles  # subject


def test_parses_semantic_role_frame_attribute():
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    sentence = next(s for s in chapter.sentences if s.sentence_id == "RUT 1:1")
    assert any(leaf.frame for leaf in sentence.leaves)


def test_parses_coreference_subjref_participantref():
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    sentence = next(s for s in chapter.sentences if s.sentence_id == "RUT 1:16")
    assert any(leaf.participantref or leaf.subjref for leaf in sentence.leaves)


def test_parses_aramaic_chapter_excerpt():
    chapter = parse_macula_lowfat_chapter(EZRA_FIXTURE)
    sentence = next(s for s in chapter.sentences if s.sentence_id == "EZR 4:8")
    assert sentence.leaves
    assert all(leaf.ref_book == "EZR" for leaf in sentence.leaves if leaf.ref_book)


def test_strip_hebrew_points_removes_cantillation_and_niqqud():
    assert strip_hebrew_points("יְהִ֗י") == "יהי"


def test_compound_lexical_item_leaf_surface_uses_text_content_not_shared_unicode_attr():
    """Regression: 'בֵּית לֶחֶם' (Bethlehem) is stored as two <w> leaves,
    each carrying the FULL two-word compound as its "unicode" attribute —
    only the element's own text content gives the correct per-leaf surface
    (see macula_lowfat_parser's _append_leaf docstring note)."""
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    sentence = next(s for s in chapter.sentences if s.sentence_id == "RUT 1:1")
    buckets = sentence.leaves_by_ref_word()
    assert [strip_hebrew_points(leaf.surface) for leaf in buckets[10]] == ["מ", "בית"]
    assert [strip_hebrew_points(leaf.surface) for leaf in buckets[11]] == ["לחם"]


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------


def _aligned_tokens(tahot_book_code: str, chapter: int, verse: int, fixture_path: Path, sentence_id: str):
    repo = HebrewTokenRepository()
    result = repo.passage(tahot_book_code, chapter, verse, verse)
    restored, _ = restore_component_fidelity(list(result.tokens))
    macula_chapter = parse_macula_lowfat_chapter(fixture_path)
    sentence = next(s for s in macula_chapter.sentences if s.sentence_id == sentence_id)
    out = []
    for token in result.tokens:
        enriched = restored.get(token.stable_key, token)
        token_id = build_token_id(token.book, token.chapter, token.verse, token.word_index)
        out.append((enriched, align_token(enriched, token_id, sentence)))
    return out


def test_alignment_exact_and_composite_ruth_1_1():
    aligned = _aligned_tokens("Rut", 1, 1, RUTH_FIXTURE, "RUT 1:1")
    types = {token.word_index: alignment.alignment_type for token, alignment in aligned}
    assert types[1] == "COMPOSITE"  # וַ/יְהִ֗י — 2 components
    assert types[3] == "EXACT"  # שְׁפֹ֣ט — 1 component
    assert all(t in {"EXACT", "COMPOSITE"} for t in types.values())


def test_alignment_handles_bethlehem_compound_as_exact_pair():
    aligned = _aligned_tokens("Rut", 1, 1, RUTH_FIXTURE, "RUT 1:1")
    by_word = {token.word_index: alignment for token, alignment in aligned}
    assert by_word[10].alignment_type == "COMPOSITE"  # מִ/בֵּ֧ית
    assert by_word[11].alignment_type == "EXACT"  # לֶ֣חֶם


def test_alignment_ketiv_qere_gap_reported_not_silently_shifted():
    """Ruth 1:8 word_index 10 is a genuine Ketiv/Qere case (Ketiv
    יַעֲשֶׂה, Qere יַ֣עַשׂ) that MACULA's own ref-numbering skips entirely
    — see docs/hebrew_analysis_v2_phase2d.md §5. The aligner must report
    this honestly (UNRESOLVED with a clear reason), never silently guess
    a shifted position."""
    aligned = _aligned_tokens("Rut", 1, 8, RUTH_FIXTURE, "RUT 1:8")
    by_word = {token.word_index: alignment for token, alignment in aligned}
    assert by_word[10].alignment_type == "UNRESOLVED"
    assert "no MACULA leaves found" in by_word[10].evidence


def test_alignment_no_fuzzy_matching_when_sentence_missing():
    aligned = _aligned_tokens("Rut", 1, 1, RUTH_FIXTURE, "RUT 1:1")
    token, _ = aligned[0]
    result = align_token(token, "Ruth.1.1:1", None)
    assert result.alignment_type == "UNRESOLVED"
    assert result.confidence == "none"


# ---------------------------------------------------------------------------
# Importer -> local linguistic store -> repository -> bundle
# ---------------------------------------------------------------------------


@pytest.fixture
def ruth_linguistic_store(tmp_path):
    store_path = tmp_path / "linguistic.sqlite3"
    store = open_store(store_path)
    textus_dv = ensure_dataset_version(store, dataset_id="tahot", display_name="TAHOT", revision="test")
    macula_dv = ensure_dataset_version(
        store, dataset_id="macula_hebrew_lowfat", display_name="MACULA Hebrew lowfat", revision="test"
    )
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    repo = HebrewTokenRepository()
    stats = import_chapter(
        chapter, tahot_book_code="Rut", chapter_number=1, store=store, token_repository=repo,
        textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv,
    )
    store.close()
    return store_path, stats


def test_importer_produces_phrases_clauses_roles_coreference(ruth_linguistic_store):
    store_path, stats = ruth_linguistic_store
    assert stats.verses_processed == 4  # RUT 1:1, 1:3, 1:8, 1:16
    assert stats.phrases > 0
    assert stats.clauses > 0
    assert stats.semantic_roles > 0
    assert stats.participants > 0
    assert stats.coreference > 0
    assert stats.exact > 0
    assert stats.composite > 0
    assert stats.unresolved >= 1  # the Ruth 1:8 Ketiv/Qere gap


def test_importer_is_idempotent_rerun_same_counts(tmp_path):
    store_path = tmp_path / "linguistic.sqlite3"
    store = open_store(store_path)
    textus_dv = ensure_dataset_version(store, dataset_id="tahot", display_name="TAHOT", revision="test")
    macula_dv = ensure_dataset_version(store, dataset_id="macula_hebrew_lowfat", display_name="MACULA", revision="test")
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    repo = HebrewTokenRepository()
    first = import_chapter(chapter, tahot_book_code="Rut", chapter_number=1, store=store, token_repository=repo,
                            textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv)
    second = import_chapter(chapter, tahot_book_code="Rut", chapter_number=1, store=store, token_repository=repo,
                             textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv)
    store.close()
    assert first.phrases == second.phrases
    assert first.clauses == second.clauses


def test_local_repository_reads_verse_syntax(ruth_linguistic_store):
    store_path, _ = ruth_linguistic_store
    repository = LocalHebrewAnalysisRepository(store_path)
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert syntax.has_syntax
    assert syntax.has_semantic_roles


def test_local_repository_missing_store_returns_empty(tmp_path):
    repository = LocalHebrewAnalysisRepository(tmp_path / "does_not_exist.sqlite3")
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert syntax == VerseSyntaxData()
    assert not syntax.has_syntax


def test_bundle_populates_phrases_clauses_roles_coreference(ruth_linguistic_store):
    store_path, _ = ruth_linguistic_store
    service = HebrewAnalysisService(linguistic_repository=LocalHebrewAnalysisRepository(store_path))
    bundle = service.get_hebrew_analysis("Rut 1,1")
    assert bundle.bundle_schema_version == BUNDLE_SCHEMA_VERSION
    verse = bundle.verses[0]
    assert verse.verse_id == "Ruth.1.1"
    assert verse.phrases
    assert verse.clauses
    assert verse.semantic_roles
    assert bundle.coverage.has_syntax
    assert bundle.coverage.has_semantic_roles


def test_bundle_coreference_ruth_1_16_resolves_pronoun_to_participant(ruth_linguistic_store):
    """'הִיא' (she) in Ruth 1:16 corefers to a participant established
    earlier — this is the deterministic 'which participant does this
    pronoun refer to' capability the coreference layer exists for."""
    store_path, _ = ruth_linguistic_store
    service = HebrewAnalysisService(linguistic_repository=LocalHebrewAnalysisRepository(store_path))
    bundle = service.get_hebrew_analysis("Rut 1,16")
    verse = bundle.verses[0]
    assert verse.coreference
    assert verse.participants


def test_token_morphology_unchanged_by_syntax_layer(ruth_linguistic_store):
    """Authority rule: attaching MACULA syntax data must never alter the
    TAHOT/TEHMC-decoded token morphology already established in Phase 2C."""
    store_path, _ = ruth_linguistic_store
    without_syntax = HebrewAnalysisService().get_hebrew_analysis("Rut 1,1")
    with_syntax = HebrewAnalysisService(
        linguistic_repository=LocalHebrewAnalysisRepository(store_path)
    ).get_hebrew_analysis("Rut 1,1")
    tokens_a = without_syntax.verses[0].tokens
    tokens_b = with_syntax.verses[0].tokens
    assert [t.morphology for t in tokens_a] == [t.morphology for t in tokens_b]
    assert [t.lexical_sense for t in tokens_a] == [t.lexical_sense for t in tokens_b]
    assert [t.root for t in tokens_a] == [t.root for t in tokens_b]


# ---------------------------------------------------------------------------
# No LLM / no network in any Phase 2D module (static import check)
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_MODULES = (
    "openai", "google.generativeai", "anthropic", "requests", "urllib.request", "httpx", "streamlit",
)


def _imported_module_names(module) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", [parser_module, alignment_module, importer_module, repository_module])
def test_phase2d_modules_have_no_llm_or_direct_network_dependency(module):
    imported = _imported_module_names(module)
    for forbidden in _FORBIDDEN_IMPORT_MODULES:
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported), (
            f"forbidden import found in {module.__name__}: {forbidden}"
        )


def test_supabase_repository_only_imports_client_lazily_inside_method():
    """SupabaseHebrewAnalysisRepository must not import the supabase client
    at module import time — only inside its methods, so importing this
    module never requires the `supabase` package or any credentials."""
    source = inspect.getsource(repository_module)
    assert "from supabase_client import get_supabase_client" in source
    tree = ast.parse(source)
    module_level_imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "get_supabase_client" not in module_level_imports
