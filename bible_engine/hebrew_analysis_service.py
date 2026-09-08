"""Phase 2C — ``get_hebrew_analysis``: the sole constructor of a
``HebrewAnalysisBundle``.

Deterministic, local, offline. This module makes exactly zero network calls
and zero LLM calls, and has no Streamlit/UI dependency — it reads only the
production TAHOT database, the compact component-fidelity store, and the
Hungarian lexicon JSON, all already committed to (or generated within) the
repository. Any AI consumer of Hebrew data must be built ON TOP of this
service's output, never by re-parsing raw morphology codes itself — see the
module docstring in ``bible_engine.hebrew_analysis_bundle`` for the
architectural rule this establishes.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from bible_engine.hebrew_analysis_bundle import (
    BUNDLE_SCHEMA_VERSION,
    BundleWarning,
    ComponentAnalysis,
    CoverageReport,
    DatasetProvenance,
    HebrewAnalysisBundle,
    LexicalSense,
    MorphologyFacts,
    TextCriticalNote,
    TokenAnalysis,
    TokenProvenance,
    VerseAnalysis,
)
from bible_engine.hebrew_analysis_repository import (
    HebrewAnalysisRepository,
    LocalHebrewAnalysisRepository,
    VerseSyntaxData,
)
from bible_engine.hebrew_books import HebrewReferenceError, parse_hebrew_reference
from bible_engine.hebrew_component_repository import (
    ComponentFidelityUnavailable,
    restore_component_fidelity,
)
from bible_engine.hebrew_lexicon_hu import HebrewHungarianLexiconRepository
from bible_engine.hebrew_morphology import decode_hebrew_morphology
from bible_engine.hebrew_morphology_hu import COMPONENT_ROLE_HU, format_hebrew_morphology_hu
from bible_engine.hebrew_parser import HebrewToken
from bible_engine.hebrew_pattern_detection import detect_patterns
from bible_engine.hebrew_token_identity import build_component_id, build_token_id, canonical_book_id_from_tahot_code
from bible_engine.hebrew_token_repository import HebrewTokenRepository

STEPBIBLE_SOURCE_COMMIT = "ea47bd4c7eab7375f2dca07086ccc356e95a4128"
STEPBIBLE_ATTRIBUTION = "STEP Bible; www.STEPBible.org"
STEPBIBLE_LICENSE = "CC BY 4.0"
MACULA_SOURCE_COMMIT = "09f8ea9e25025841ec45e2b6e7fc01595a080568"  # tag 26.04.13

_GRAMMAR_MARKER_STRONG_PREFIX = "H9"


class HebrewAnalysisUnavailable(RuntimeError):
    """The requested reference has no deterministic Hebrew analysis
    available (unknown reference, passage not found in TAHOT, or the
    production database is not usable) — see ``status`` for the reason."""

    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


class HebrewAnalysisService:
    """Pure, deterministic. Construct once and reuse — the underlying
    repositories cache their own small diagnostics, but this class holds no
    per-call mutable state."""

    def __init__(
        self,
        *,
        production_db_path: str | Path | None = None,
        component_fidelity_db_path: str | Path | None = None,
        hungarian_lexicon_path: str | Path | None = None,
        linguistic_repository: HebrewAnalysisRepository | None = None,
    ) -> None:
        self._token_repository = HebrewTokenRepository(production_db_path)
        self._component_fidelity_db_path = component_fidelity_db_path
        self._lexicon_repository = HebrewHungarianLexiconRepository(
            *(() if hungarian_lexicon_path is None else (hungarian_lexicon_path,))
        )
        # Phase 2D: syntax/phrase/clause/semantic-role/coreference data —
        # NEVER token/morphology/lexical data, which stays on the Phase 2C
        # path above unchanged (see this module's docstring). Defaults to
        # the local SQLite mirror; pass a SupabaseHebrewAnalysisRepository
        # for the production-capable read path.
        self._linguistic_repository: HebrewAnalysisRepository = linguistic_repository or LocalHebrewAnalysisRepository()

    def get_hebrew_analysis(self, reference: str) -> HebrewAnalysisBundle:
        """``reference`` is a Hungarian-style Old Testament reference
        string, e.g. ``"1Móz 1,1"`` or ``"Rut 1,1-5"`` — see
        ``bible_engine.hebrew_books.parse_hebrew_reference``. Verse ranges
        within a single chapter are already supported; cross-chapter ranges
        are Phase 2D scope (the same limit ``HebrewTokenRepository.passage``
        already has).
        """
        try:
            book_code, chapter, verse_start, verse_end = parse_hebrew_reference(reference)
        except HebrewReferenceError as exc:
            raise HebrewAnalysisUnavailable("invalid_reference", str(exc)) from exc

        result = self._token_repository.passage(book_code, chapter, verse_start, verse_end)
        if result.status != "ok":
            raise HebrewAnalysisUnavailable(result.status, f"Hebrew passage unavailable: {reference} ({result.status})")

        # book_code was already validated against OT_BOOKS by
        # parse_hebrew_reference above, so this bridge cannot fail here.
        canonical_book_id = canonical_book_id_from_tahot_code(book_code)

        tokens = list(result.tokens)
        has_component_fidelity = True
        try:
            restored, source_ids = restore_component_fidelity(
                tokens, production_db_path=self._token_repository.database_path,
                fidelity_db_path=self._component_fidelity_db_path,
            )
        except ComponentFidelityUnavailable:
            has_component_fidelity = False
            restored, source_ids = {t.stable_key: t for t in tokens}, {}

        verses_map: dict[tuple[int, int], list[TokenAnalysis]] = {}
        text_by_verse: dict[tuple[int, int], list[str]] = {}
        fully_decoded_count = 0
        warnings: list[BundleWarning] = []

        for token in tokens:
            enriched = restored.get(token.stable_key, token)
            source_token_id = source_ids.get(token.stable_key, token.source_token_id)
            token_analysis = self._build_token_analysis(enriched, source_token_id)
            if token_analysis.morphology.fully_decoded:
                fully_decoded_count += 1
            verse_key = (token.chapter, token.verse)
            verses_map.setdefault(verse_key, []).append(token_analysis)
            text_by_verse.setdefault(verse_key, []).append(enriched.surface)

        languages = {ta.morphology.language for verse in verses_map.values() for ta in verse if ta.morphology.language}
        language = "mixed" if len(languages) > 1 else (next(iter(languages), "hebrew"))

        verses = tuple(
            self._build_verse_analysis(canonical_book_id, chapter_num, verse_num, verses_map, text_by_verse)
            for chapter_num, verse_num in sorted(verses_map)
        )

        reference_str = (
            f"{canonical_book_id}.{chapter}.{verse_start}"
            if verse_start == verse_end
            else f"{canonical_book_id}.{chapter}.{verse_start}-{verse_end}"
        )

        if not has_component_fidelity:
            warnings.append(
                BundleWarning(
                    scope="bundle",
                    target_id=reference_str,
                    code="component_fidelity_unavailable",
                    message_hu="A prefixum/suffixum komponensek saját felszíni alakja és angol glossza "
                    "nem elérhető (hiányzó adatbázis) — csak a szótő és a szerep ismert.",
                )
            )

        has_syntax = any(v.phrases or v.clauses or v.syntax_relations for v in verses)
        has_semantic_roles = any(v.semantic_roles for v in verses)
        has_participants = any(v.participants for v in verses)
        notes = ["Nincs gyök-adat (Fázis 2C/2D-ben nem elérhető deterministikus héber gyök-forrás)."]
        if not has_syntax:
            notes.append("Ehhez a szakaszhoz nincs importált MACULA mondattani (frázis/mellékmondat) adat.")

        coverage = CoverageReport(
            has_morphology=True,
            has_component_fidelity=has_component_fidelity,
            has_syntax=has_syntax,
            has_semantic_roles=has_semantic_roles,
            has_participants=has_participants,
            has_roots=False,
            token_count=len(tokens),
            fully_decoded_token_count=fully_decoded_count,
            notes=tuple(notes),
        )

        return HebrewAnalysisBundle(
            bundle_schema_version=BUNDLE_SCHEMA_VERSION,
            reference=reference_str,
            reference_hu=reference,
            book_id=book_code,
            language=language,
            verses=verses,
            datasets=self._dataset_provenance(),
            coverage=coverage,
            warnings=tuple(warnings),
        )

    def _build_verse_analysis(
        self,
        canonical_book_id: str,
        chapter_num: int,
        verse_num: int,
        verses_map: dict[tuple[int, int], list[TokenAnalysis]],
        text_by_verse: dict[tuple[int, int], list[str]],
    ) -> VerseAnalysis:
        verse_id = f"{canonical_book_id}.{chapter_num}.{verse_num}"
        verse_tokens = verses_map[(chapter_num, verse_num)]
        syntax: VerseSyntaxData = self._linguistic_repository.get_verse_syntax(verse_id)
        verse = VerseAnalysis(
            verse_id=verse_id,
            chapter=chapter_num,
            verse=verse_num,
            hebrew_text=" ".join(text_by_verse[(chapter_num, verse_num)]),
            hebrew_text_plain=" ".join(text_by_verse[(chapter_num, verse_num)]),
            versification_note="",
            tokens=tuple(verse_tokens),
            phrases=syntax.phrases,
            clauses=syntax.clauses,
            syntax_relations=syntax.syntax_relations,
            semantic_roles=syntax.semantic_roles,
            participants=syntax.participants,
            coreference=syntax.coreference,
            syntax_grounding=syntax.syntax_grounding,
            text_critical=tuple(self._text_critical_notes(verse_tokens)),
        )
        return replace(verse, detected_patterns=detect_patterns(verse))

    # -- token/component construction -----------------------------------

    def _build_token_analysis(self, token: HebrewToken, source_token_id: str) -> TokenAnalysis:
        token_id = build_token_id(token.book, token.chapter, token.verse, token.word_index)
        composite = decode_hebrew_morphology(token.morphology_code)
        morphology = _morphology_facts_from_decoded(composite)

        ordered = list(token.prefix_components) + (
            [token.core_component] if token.core_component is not None else []
        ) + list(token.suffix_components)
        component_payloads = _align_component_payloads(ordered, composite)

        components = tuple(
            self._build_component_analysis(token_id, index, component, payload)
            for index, (component, payload) in enumerate(zip(ordered, component_payloads))
        )

        lexical_sense = None
        if token.strong_ids:
            resolution = self._lexicon_repository.lookup(token.strong_ids[0], expected_lemma=token.lemma)
            if resolution.entry is not None:
                entry = resolution.entry
                lexical_sense = LexicalSense(
                    strong_id=entry.strong_id,
                    lemma=entry.lemma,
                    transliteration=entry.transliteration,
                    base_meaning_hu=entry.base_meaning_hu,
                    possible_meanings_hu=entry.possible_meanings_hu,
                    lexical_note_hu=entry.lexical_note_hu,
                    review_status=entry.review_status,
                    translation_method=entry.translation_method,
                    source=entry.source,
                    warnings=resolution.warnings,
                )

        return TokenAnalysis(
            token_id=token_id,
            legacy_stable_key=token.stable_key,
            source_token_id=source_token_id,
            word_index=token.word_index,
            surface=token.surface,
            surface_plain=token.surface_without_accents,
            transliteration=token.transliteration,
            transliteration_hu=token.transliteration,
            lemma=token.lemma,
            root=None,
            strong_ids=token.strong_ids,
            part_of_speech=morphology.part_of_speech,
            morphology=morphology,
            components=components,
            lexical_sense=lexical_sense,
            ketiv=token.ketiv,
            qere=token.qere,
            source_edition=token.source_edition,
            maqaf=token.maqaf,
            punctuation=token.punctuation,
            provenance=TokenProvenance(),
        )

    def _build_component_analysis(
        self, token_id: str, index: int, component, payload
    ) -> ComponentAnalysis:
        if payload is None:
            morphology = MorphologyFacts(raw_code=component.morphology_code, confidence="not_applicable")
        elif isinstance(payload, dict):
            morphology = _morphology_facts_from_payload(payload, component.morphology_code)
        else:
            morphology = _morphology_facts_from_decoded(payload)
        return ComponentAnalysis(
            component_id=build_component_id(token_id, index),
            component_index=index,
            role=component.role,
            role_label_hu=COMPONENT_ROLE_HU.get(component.role, component.role),
            surface=component.surface,
            strong_id=component.strong_id,
            morphology=morphology,
            gloss_en=component.gloss,
            is_grammar_marker=component.strong_id.upper().startswith(_GRAMMAR_MARKER_STRONG_PREFIX),
        )

    def _text_critical_notes(self, verse_tokens: list[TokenAnalysis]) -> list[TextCriticalNote]:
        notes = []
        for token_analysis in verse_tokens:
            if token_analysis.ketiv or token_analysis.qere:
                notes.append(
                    TextCriticalNote(
                        token_id=token_analysis.token_id,
                        ketiv=token_analysis.ketiv,
                        qere=token_analysis.qere,
                        source_edition=token_analysis.source_edition,
                        raw_meaning_variant="",
                        raw_spelling_variant="",
                    )
                )
        return notes

    def _dataset_provenance(self) -> tuple[DatasetProvenance, ...]:
        return (
            DatasetProvenance(
                dataset_id="tahot",
                display_name="Translators Amalgamated Hebrew OT (TAHOT)",
                source_repository="STEPBible/STEPBible-Data",
                source_commit=STEPBIBLE_SOURCE_COMMIT,
                license=STEPBIBLE_LICENSE,
                attribution=STEPBIBLE_ATTRIBUTION,
            ),
            DatasetProvenance(
                dataset_id="tehmc",
                display_name="Translators Expansion of Hebrew Morphology Codes (TEHMC)",
                source_repository="STEPBible/STEPBible-Data",
                source_commit=STEPBIBLE_SOURCE_COMMIT,
                license=STEPBIBLE_LICENSE,
                attribution=STEPBIBLE_ATTRIBUTION,
            ),
            DatasetProvenance(
                dataset_id="tbesh",
                display_name="Translators Brief lexicon of Extended Strongs for Hebrew (TBESH)",
                source_repository="STEPBible/STEPBible-Data",
                source_commit=STEPBIBLE_SOURCE_COMMIT,
                license=STEPBIBLE_LICENSE,
                attribution=STEPBIBLE_ATTRIBUTION,
            ),
            DatasetProvenance(
                dataset_id="hebrew_component_fidelity",
                display_name="Textus Hebrew component-fidelity store (Phase 2C)",
                source_repository="STEPBible/STEPBible-Data",
                source_commit=STEPBIBLE_SOURCE_COMMIT,
                license=STEPBIBLE_LICENSE,
                attribution=STEPBIBLE_ATTRIBUTION,
            ),
            DatasetProvenance(
                dataset_id="textus_hu_lexicon",
                display_name="Textus magyar héber lexikon (Phase 2B/2C remediáció)",
                source_repository="Textus",
                source_commit="",
                license="",
                attribution="Textus",
            ),
            DatasetProvenance(
                dataset_id="macula_hebrew_lowfat",
                display_name="MACULA Hebrew Linguistic Datasets (lowfat)",
                source_repository="Clear-Bible/macula-hebrew",
                source_commit=MACULA_SOURCE_COMMIT,
                license="CC BY 4.0",
                attribution="MACULA Hebrew Linguistic Datasets, available at https://github.com/Clear-Bible/macula-hebrew/",
            ),
        )


def get_hebrew_analysis(
    reference: str,
    *,
    production_db_path: str | Path | None = None,
    component_fidelity_db_path: str | Path | None = None,
    hungarian_lexicon_path: str | Path | None = None,
    linguistic_repository: HebrewAnalysisRepository | None = None,
) -> HebrewAnalysisBundle:
    """Module-level convenience wrapper — builds a fresh
    ``HebrewAnalysisService`` per call. For repeated lookups within one
    process, construct ``HebrewAnalysisService`` once and reuse it instead.
    """
    service = HebrewAnalysisService(
        production_db_path=production_db_path,
        component_fidelity_db_path=component_fidelity_db_path,
        hungarian_lexicon_path=hungarian_lexicon_path,
        linguistic_repository=linguistic_repository,
    )
    return service.get_hebrew_analysis(reference)


def _align_component_payloads(ordered: list, composite) -> list:
    """Match each surface component (in prefix→core→suffix order) to its
    own decoded morphology segment.

    Two shapes need handling, both real corpus cases:

    * **Single-component tokens** (no prefix/suffix) — ``decode_hebrew_
      morphology`` returns the ONE decoded ``HebrewMorphology`` directly
      rather than a composite with a ``.components`` list (see that
      function's ``if len(decoded) == 1`` branch). Here the single ordered
      component IS the whole decoded token, so it is returned as-is (not a
      dict — ``_build_component_analysis`` handles both shapes).

    * **A structural component with no morphology-code segment of its own**
      — e.g. sentence-final punctuation stored as a trailing "suffix" role
      component (Strong id ``H9016``, gloss "verseEnd") is not encoded as a
      letter in the token's composite morphology code at all, so
      ``composite.components`` is shorter than ``ordered``. A naive
      positional zip would then also break the WELL-decoded prefix/core
      segments that precede it. Matching by role (``payload
      ["component_type"]`` against ``component.role``) instead of raw
      position keeps every segment that does have its own code, and only
      the parts genuinely outside TEHMC's coverage fall back to ``None``.
    """
    if len(ordered) == 1:
        return [composite]
    payloads = list(composite.components)
    aligned: list = []
    payload_index = 0
    for component in ordered:
        if payload_index < len(payloads) and payloads[payload_index].get("component_type") == component.role:
            aligned.append(payloads[payload_index])
            payload_index += 1
        else:
            aligned.append(None)
    return aligned


def _morphology_facts_from_decoded(morph) -> MorphologyFacts:
    return MorphologyFacts(
        raw_code=morph.code,
        language=morph.language.lower() if morph.language else "",
        part_of_speech=morph.part_of_speech,
        verb_stem=morph.verb_stem,
        verb_form=morph.verb_conjugation,
        person=morph.person,
        gender=morph.gender,
        number=morph.number,
        state=morph.state,
        noun_type=morph.noun_type,
        adjective_type=morph.adjective_type,
        pronoun_type=morph.pronoun_type,
        proper_name_type=morph.proper_name_type,
        particle_type=morph.particle_type,
        preposition_type=morph.preposition_type,
        conjunction_type=morph.conjunction_type,
        suffix_type=morph.suffix_type,
        suffix_person=morph.suffix_person,
        suffix_gender=morph.suffix_gender,
        suffix_number=morph.suffix_number,
        summary_hu=format_hebrew_morphology_hu(morph),
        confidence=morph.status,
        unresolved_parts=morph.unresolved_parts,
    )


def _morphology_facts_from_payload(payload: dict, raw_code: str) -> MorphologyFacts:
    return MorphologyFacts(
        raw_code=payload.get("original_code") or raw_code,
        language=str(payload.get("language") or "").lower(),
        part_of_speech=str(payload.get("part_of_speech") or ""),
        verb_stem=str(payload.get("verb_stem") or ""),
        verb_form=str(payload.get("verb_conjugation") or ""),
        person=str(payload.get("person") or ""),
        gender=str(payload.get("gender") or ""),
        number=str(payload.get("number") or ""),
        state=str(payload.get("state") or ""),
        noun_type=str(payload.get("noun_type") or ""),
        adjective_type=str(payload.get("adjective_type") or ""),
        pronoun_type=str(payload.get("pronoun_type") or ""),
        proper_name_type=str(payload.get("proper_name_type") or ""),
        particle_type=str(payload.get("particle_type") or ""),
        preposition_type=str(payload.get("preposition_type") or ""),
        conjunction_type=str(payload.get("conjunction_type") or ""),
        suffix_type=str(payload.get("suffix_type") or ""),
        suffix_person=str(payload.get("suffix_person") or ""),
        suffix_gender=str(payload.get("suffix_gender") or ""),
        suffix_number=str(payload.get("suffix_number") or ""),
        confidence=str(payload.get("status") or "unresolved"),
    )


__all__ = [
    "HebrewAnalysisService",
    "HebrewAnalysisUnavailable",
    "get_hebrew_analysis",
]
