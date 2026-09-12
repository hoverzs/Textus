"""Greek Analysis v2 — Phase 2A. Builds a ``GreekAnalysisBundle`` from the
local, deterministic TAGNT + Hungarian-lexicon + TBESG sources. No network
access, no AI/Gemini call, no Supabase dependency — see the corpus-wide
"no AI/network dependency" invariant test in
``tests/test_greek_analysis_bundle.py``.
"""

from __future__ import annotations

from pathlib import Path

from bible_engine.greek_analysis_bundle import (
    GreekAnalysisBundle,
    GreekCoverageReport,
    GreekDatasetProvenance,
    GreekLexicalSense,
    GreekMorphologyFacts,
    GreekTokenAnalysis,
    GreekTokenProvenance,
    GreekVerseAnalysis,
)
from bible_engine.greek_lexicon_repository import (
    TBESGDatabaseUnavailableError,
    get_tbesg_lexicon_entry,
)
from bible_engine.greek_token_repository import GreekVerseTokens, load_greek_passage_tokens
from bible_engine.lexicon_hu import (
    DEFAULT_HUNGARIAN_LEXICON_PATH,
    DEFAULT_STRONG_ALIASES_PATH,
    HungarianLexiconEntry,
    load_default_hungarian_lexicon,
    load_strong_aliases,
    resolve_hungarian_lexicon_entry,
)
from bible_engine.morphology_hu import HungarianMorphology, parse_morphology_hu
from bible_engine.tagnt_books import parse_tagnt_bible_reference
from bible_engine.tagnt_parser import GreekToken, render_greek_text

BUNDLE_SCHEMA_VERSION = "greek-2a"

_DATASETS = (
    GreekDatasetProvenance(
        dataset_id="tagnt",
        display_name="STEPBible TAGNT (Translators Amalgamated Greek NT)",
        source_repository="STEPBible/STEPBible-Data",
        source_commit="ae39711d7843b2902d54993e432de9c12d6a4b9a",
        license="CC BY 4.0",
        attribution="Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)",
    ),
    GreekDatasetProvenance(
        dataset_id="tbesg",
        display_name="STEPBible TBESG (Translators Brief lexicon of Extended Strongs for Greek)",
        source_repository="STEPBible/STEPBible-Data",
        source_commit="ae39711d7843b2902d54993e432de9c12d6a4b9a",
        license="CC BY 4.0",
        attribution="Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)",
    ),
    GreekDatasetProvenance(
        dataset_id="tegmc",
        display_name="STEPBible TEGMC (Translators Expansion of Greek Morphology Codes)",
        source_repository="STEPBible/STEPBible-Data",
        source_commit="ae39711d7843b2902d54993e432de9c12d6a4b9a",
        license="CC BY 4.0",
        attribution="Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)",
    ),
    GreekDatasetProvenance(
        dataset_id="lexicon_hu",
        display_name="Textus Hungarian Greek lexicon (TBESG-derived)",
        source_repository="internal",
        source_commit="",
        license="Internal (derivative of CC BY 4.0 TBESG)",
        attribution="Textus",
    ),
)


def greek_token_id(book: str, chapter: int, verse: int, word_index: int) -> str:
    """The Phase 2A stable token identity — see
    ``docs/greek_analysis_v2_phase2a_foundation.md`` §8."""
    return f"{book}.{chapter}.{verse}:{word_index}"


def _morphology_facts(morph_code: str, hungarian: HungarianMorphology) -> GreekMorphologyFacts:
    confidence = "fully_decoded" if hungarian.is_fully_resolved else "unresolved"
    return GreekMorphologyFacts(
        raw_code=morph_code or "",
        part_of_speech=hungarian.part_of_speech or "",
        case=hungarian.case or "",
        number=hungarian.number or "",
        gender=hungarian.gender or "",
        person=hungarian.person or "",
        tense=hungarian.tense or "",
        voice=hungarian.voice or "",
        mood=hungarian.mood or "",
        verb_form=hungarian.verb_form or "",
        degree=hungarian.degree or "",
        pronoun_type=hungarian.pronoun_type or "",
        name_type=hungarian.name_type or "",
        extra=tuple(hungarian.extra or ()),
        summary_hu=_summary_hu(hungarian),
        confidence=confidence,
        unresolved_parts=tuple(hungarian.unresolved or ()),
    )


def _summary_hu(hungarian: HungarianMorphology) -> str:
    from bible_engine.morphology_hu import format_morphology_hu

    return format_morphology_hu(hungarian)


def _lexical_sense(
    strong_id: str,
    entries: dict[str, HungarianLexiconEntry],
    aliases: dict,
) -> GreekLexicalSense | None:
    resolution = None
    try:
        resolution = resolve_hungarian_lexicon_entry(entries, strong_id, aliases)
    except ValueError:
        return None
    if resolution is not None:
        entry = resolution.entry
        return GreekLexicalSense(
            strong_id=strong_id,
            lemma=entry.lemma,
            base_meaning_hu=entry.primary_gloss,
            possible_meanings_hu=tuple(entry.senses),
            note_hu=entry.note or "",
            review_status=entry.review_status,
            translation_method=entry.translation_method,
            source_name=entry.source_name,
            source_version=entry.source_version,
            resolved_via_alias=resolution.alias is not None,
            alias_target_strong_id=resolution.resolved_strong_id if resolution.alias is not None else "",
        )

    try:
        tbesg_entry = get_tbesg_lexicon_entry(strong_id)
    except (TBESGDatabaseUnavailableError, ValueError, FileNotFoundError):
        return None
    if tbesg_entry is None:
        return None
    return GreekLexicalSense(
        strong_id=strong_id,
        lemma=tbesg_entry.lemma,
        base_meaning_hu="",  # TBESG is English-only — never fabricate a Hungarian gloss from it
        possible_meanings_hu=(),
        note_hu=tbesg_entry.gloss or "",
        review_status="draft",
        translation_method="",  # not a Hungarian translation at all — English source, unresolved
        source_name="STEPBible TBESG (English fallback — no Hungarian entry exists)",
        source_version="",
    )


def _token_analysis(
    token: GreekToken,
    entries: dict[str, HungarianLexiconEntry],
    aliases: dict,
) -> GreekTokenAnalysis:
    hungarian = parse_morphology_hu(token.morph_code or "")
    morphology = _morphology_facts(token.morph_code or "", hungarian)
    lexical_sense = _lexical_sense(token.strong_id, entries, aliases) if token.strong_id else None
    return GreekTokenAnalysis(
        token_id=greek_token_id(token.book, token.chapter, token.verse, token.word_index),
        book=token.book,
        chapter=token.chapter,
        verse=token.verse,
        word_index=token.word_index,
        surface=token.greek_form,
        lemma=token.lemma,
        strong_id=token.strong_id,
        edition_flags=token.edition_flags,
        part_of_speech=morphology.part_of_speech,
        morphology=morphology,
        lexical_sense=lexical_sense,
        provenance=GreekTokenProvenance(),
    )


def _verse_analysis(book: str, chapter: int, verse: int, tokens: tuple[GreekToken, ...],
                     entries: dict[str, HungarianLexiconEntry], aliases: dict) -> GreekVerseAnalysis:
    ordered = tuple(sorted(tokens, key=lambda t: t.word_index))
    token_analyses = tuple(_token_analysis(t, entries, aliases) for t in ordered)
    return GreekVerseAnalysis(
        verse_id=f"{book}.{chapter}.{verse}",
        book=book,
        chapter=chapter,
        verse=verse,
        greek_text=render_greek_text(list(ordered)),
        tokens=token_analyses,
    )


def get_greek_analysis_with_syntax(
    reference: str, syntax_database_path: str | None = None
) -> GreekAnalysisBundle:
    """Phase 2B convenience wrapper: builds the Phase 2A deterministic
    bundle, then attaches syntax data from the local normalized store when
    available (silently falls back to the Phase 2A-only bundle — with
    every verse's ``syntax_grounding`` left at ``NO_GROUNDED_SYNTAX`` —
    when the store does not exist, e.g. a fresh checkout that has not run
    ``scripts/build_greek_syntax_store.py``)."""
    from bible_engine.greek_construction_detection import attach_detected_patterns
    from bible_engine.greek_syntax_service import attach_syntax
    from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

    bundle = get_greek_analysis(reference)
    path = Path(syntax_database_path) if syntax_database_path else resolve_default_syntax_database_path()
    bundle = attach_syntax(bundle, path)
    # Phase 2C — construction detection needs to run AFTER syntax
    # attachment (clause-dependent detectors like genitive absolute read
    # verse.clauses) so the AI contextual-analysis payload/evidence index
    # actually sees pattern-based evidence, not just phrase/clause/role
    # evidence (see attach_detected_patterns's own docstring).
    return attach_detected_patterns(bundle)


def get_greek_analysis(reference: str) -> GreekAnalysisBundle:
    """Build a full deterministic ``GreekAnalysisBundle`` for ``reference``.

    Raises the same exceptions as ``load_greek_passage_tokens`` (FileNotFoundError
    if the TAGNT database is not built; ValueError for an invalid reference)
    — callers already handle these for the existing UI path
    (``bible_engine.greek_analysis_ui``)."""
    verse_groups: list[GreekVerseTokens] = load_greek_passage_tokens(reference)

    entries = load_default_hungarian_lexicon(DEFAULT_HUNGARIAN_LEXICON_PATH) or {}
    aliases = load_strong_aliases(DEFAULT_STRONG_ALIASES_PATH)

    verses = tuple(
        _verse_analysis(vg.book, vg.chapter, vg.verse, vg.tokens, entries, aliases)
        for vg in verse_groups
    )

    total_tokens = sum(len(v.tokens) for v in verses)
    fully_decoded = sum(
        1 for v in verses for t in v.tokens if t.morphology.confidence == "fully_decoded"
    )

    parsed = parse_tagnt_bible_reference(reference)
    return GreekAnalysisBundle(
        bundle_schema_version=BUNDLE_SCHEMA_VERSION,
        reference=parsed.normalized_reference,
        reference_hu=parsed.normalized_reference,
        book=parsed.book.code,
        verses=verses,
        datasets=_DATASETS,
        coverage=GreekCoverageReport(
            has_morphology=True,
            has_lexical_sense=any(t.lexical_sense is not None for v in verses for t in v.tokens),
            has_syntax=False,
            has_semantic_roles=False,
            has_participants=False,
            token_count=total_tokens,
            fully_decoded_token_count=fully_decoded,
        ),
    )
