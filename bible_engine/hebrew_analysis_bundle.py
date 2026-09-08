"""Phase 2C — the deterministic HebrewAnalysisBundle data contract.

This is the stable boundary between the deterministic Hebrew data layer
(TAHOT text/morphology, TEHMC-verified decoding, TBESH-derived lexicon,
Ketiv/Qere, component fidelity) and any future consumer — the current UI,
a future AI interpretation layer, or Phase 2D's MACULA syntax integration.

Design rules, enforced by construction rather than by convention:

* **Every field is either a verified deterministic fact or explicitly
  absent.** Nothing here is inferred, guessed, or AI-generated. See
  ``docs/hebrew_analysis_v2_phase2c.md`` for the full provenance policy.
* **Root is genuinely absent, not fabricated.** ``TokenAnalysis.root`` is
  ``None`` in Phase 2C — neither TEHMC nor TBESH contains a reliable Hebrew
  triliteral-root field (verified in Phase 2B), and heuristic derivation is
  explicitly out of scope. ``root`` stays a real field so a future phase can
  populate it (from OSHB/MorphHB or MACULA) without a breaking schema change.
* **"core" is never conflated with "root".** A token's core component is the
  lexeme-bearing surface segment (see ``bible_engine.hebrew_parser``'s
  ``_core_index``), not the triliteral root — the same distinction Phase 2A
  established when renaming the misleading "lexikai mag" label.
* **Phrases, clauses, semantic roles and coreference are structurally
  present but always empty in Phase 2C.** No deterministic local source
  supplies them yet (that is Phase 2D's MACULA work); returning an empty
  tuple rather than omitting the field means a future consumer's code does
  not need a schema migration, only a data migration.
* **Stem and conjugation are always separate fields**, never merged into one
  label — the exact bug class Phase 1's audit flagged in the UI.
* **Every fact carries its own provenance** (``TokenProvenance``), so a
  future MACULA-derived syntax fact is never confused with a STEPBible
  morphology fact.

No field here is populated by an LLM. See
``bible_engine.hebrew_analysis_service`` for the pure, deterministic builder.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Passage-level provenance and metadata.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetProvenance:
    """One deterministic data source's identity and licence, verbatim."""

    dataset_id: str  # "tahot" | "tehmc" | "tbesh" | "hebrew_component_fidelity" | "textus_hu_lexicon"
    display_name: str
    source_repository: str
    source_commit: str
    license: str
    attribution: str


@dataclass(frozen=True)
class TextCriticalNote:
    """A single deterministic Ketiv/Qere (or spelling/meaning variant) record."""

    token_id: str
    ketiv: str
    qere: str
    source_edition: str  # "L" | "Q(K)" | "Q(k)" | "X" | ...
    raw_meaning_variant: str
    raw_spelling_variant: str
    source_dataset: str = "tahot"


@dataclass(frozen=True)
class DetectedPattern:
    """One mechanically-detected structural fact — see
    ``bible_engine.hebrew_pattern_detection`` for the detectors.

    ``explanation_hu`` is a deterministic, templated sentence stating the
    STRUCTURAL fact only (e.g. "két tagadószó szerepel ebben a mondatban")
    — never an interpretation of what the fact means. Interpretation is a
    later AI-layer responsibility, grounded on this field, not a
    replacement for it.
    """

    pattern_id: str
    pattern_type: str
    token_ids: tuple[str, ...]
    evidence_token_ids: tuple[str, ...]
    detector_version: str
    confidence: str  # "certain" | "probable"
    explanation_hu: str


@dataclass(frozen=True)
class BundleWarning:
    scope: str  # "token" | "bundle"
    target_id: str
    code: str
    message_hu: str


@dataclass(frozen=True)
class CoverageReport:
    has_morphology: bool
    has_component_fidelity: bool
    has_syntax: bool
    has_semantic_roles: bool
    has_participants: bool
    has_roots: bool
    token_count: int
    fully_decoded_token_count: int
    notes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Token level.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MorphologyFacts:
    """Deterministic morphology for one token or token component.

    Verb ``stem`` (binyan) and ``form`` (conjugation) are always separate
    fields — see the module docstring.
    """

    raw_code: str
    code_system: str = "TEHMC"
    language: str = ""  # "hebrew" | "aramaic"
    part_of_speech: str = ""
    verb_stem: str = ""
    verb_form: str = ""
    person: str = ""
    gender: str = ""
    number: str = ""
    state: str = ""
    noun_type: str = ""
    adjective_type: str = ""
    pronoun_type: str = ""
    proper_name_type: str = ""
    particle_type: str = ""
    preposition_type: str = ""
    conjunction_type: str = ""
    suffix_type: str = ""
    suffix_person: str = ""
    suffix_gender: str = ""
    suffix_number: str = ""
    summary_hu: str = ""
    confidence: str = "unresolved"  # fully_decoded | partially_decoded | unresolved | malformed | not_applicable
    unresolved_parts: tuple[str, ...] = ()

    @property
    def fully_decoded(self) -> bool:
        return self.confidence == "fully_decoded"


@dataclass(frozen=True)
class RootInfo:
    """Explicitly NOT populated in Phase 2C — see the module docstring.

    Kept as a real (nullable) field for forward compatibility with a future
    phase that imports OSHB/MorphHB or MACULA root data. Never heuristically
    derived.
    """

    consonants: str
    display_hu: str  # uses "gyök", once a real source exists — never "core"/"alapszó"
    root_type: str  # "triliteral" | "biliteral" | "quadriliteral" | "unknown"
    source_dataset: str


@dataclass(frozen=True)
class ComponentAnalysis:
    """One prefix/core/suffix component of a (possibly multi-component)
    Hebrew surface token. Restored in Phase 2C from the compact component-
    fidelity store — see ``bible_engine.hebrew_component_repository``.
    """

    component_id: str  # f"{token_id}.{component_index}" — sub-word addressable
    component_index: int
    role: str  # "prefix" | "core" | "suffix"
    role_label_hu: str  # never "lexikai mag" / never "gyök" for a non-root role
    surface: str
    strong_id: str
    morphology: MorphologyFacts
    gloss_en: str = ""
    gloss_hu: str = ""
    is_grammar_marker: bool = False  # STEPBible H9xxx pseudo-Strongs (waw, maqaf, punctuation, ...)


@dataclass(frozen=True)
class LexicalSense:
    """The deterministic, curated lexical/base meaning — kept separate from
    any future contextual-sense field an AI layer might populate. Never
    contains a context-specific gloss presented as the general meaning (the
    exact defect class Phase 2A/2B found and fixed for אֲשֶׁר/H0834A)."""

    strong_id: str
    lemma: str
    transliteration: str
    base_meaning_hu: str
    possible_meanings_hu: tuple[str, ...]
    lexical_note_hu: str
    review_status: str  # "draft" | "reviewed"
    translation_method: str  # "ai_assisted" | "human"
    source: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TokenProvenance:
    text_source: str = "tahot"
    morphology_source: str = "tahot"
    lemma_source: str = "tahot"
    root_source: str = ""  # empty — see RootInfo
    lexical_source: str = "tbesh"
    component_source: str = "hebrew_component_fidelity"
    syntax_source: str = ""  # empty until Phase 2D (MACULA)


@dataclass(frozen=True)
class TokenAnalysis:
    """One deterministic Hebrew/Aramaic surface token.

    ``token_id`` is the Phase 2C stable identity
    (``{book}.{chapter}.{verse}:{word_index}``, canonical-reference based —
    see ``bible_engine.hebrew_token_identity`` for the full contract).
    ``legacy_stable_key`` keeps the Phase 1 ``book:chapter:verse:word_index``
    form for backward compatibility with existing UI/cache code.
    """

    token_id: str
    legacy_stable_key: str
    source_token_id: str  # e.g. "Rut.1.1#01=L" — the Phase 2D MACULA/OSHB alignment anchor
    word_index: int

    surface: str
    surface_plain: str
    transliteration: str
    transliteration_hu: str

    lemma: str
    root: RootInfo | None  # always None in Phase 2C — see RootInfo
    strong_ids: tuple[str, ...]

    part_of_speech: str
    morphology: MorphologyFacts
    components: tuple[ComponentAnalysis, ...]

    lexical_sense: LexicalSense | None
    contextual_sense: None = None  # reserved for a future AI-interpretation layer

    ketiv: str = ""
    qere: str = ""
    source_edition: str = ""
    maqaf: bool = False
    punctuation: str = ""

    provenance: TokenProvenance = field(default_factory=TokenProvenance)


# ---------------------------------------------------------------------------
# Verse / passage level.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhraseAnalysis:
    """Reserved for Phase 2D (MACULA). Never populated in Phase 2C."""

    phrase_id: str
    phrase_type: str
    token_ids: tuple[str, ...]
    head_token_id: str | None
    parent_phrase_id: str | None
    function: str
    source_dataset: str


@dataclass(frozen=True)
class ClauseAnalysis:
    """Reserved for Phase 2D (MACULA). Never populated in Phase 2C."""

    clause_id: str
    clause_type: str
    token_ids: tuple[str, ...]
    predicate_id: str | None
    subject_id: str | None
    object_ids: tuple[str, ...]
    complement_ids: tuple[str, ...]
    modifier_ids: tuple[str, ...]
    parent_clause_id: str | None
    relation_to_parent: str
    word_order: str
    source_dataset: str


@dataclass(frozen=True)
class SemanticRole:
    """Reserved for Phase 2D (MACULA). Never populated in Phase 2C."""

    role_id: str
    role_type: str  # "agent" | "patient" | "theme" | "experiencer" | "recipient" | "location" | ...
    token_ids: tuple[str, ...]
    predicate_id: str
    source_dataset: str


@dataclass(frozen=True)
class ParticipantMention:
    """Reserved for a future coreference source (e.g. ACAI). Never
    populated in Phase 2C."""

    mention_id: str
    token_ids: tuple[str, ...]
    participant_id: str
    entity_id: str | None
    entity_label_hu: str
    mention_type: str
    source_dataset: str


@dataclass(frozen=True)
class VerseAnalysis:
    verse_id: str  # "Gen.1.1"
    chapter: int
    verse: int
    hebrew_text: str
    hebrew_text_plain: str
    versification_note: str
    tokens: tuple[TokenAnalysis, ...]
    phrases: tuple[PhraseAnalysis, ...] = ()
    clauses: tuple[ClauseAnalysis, ...] = ()
    semantic_roles: tuple[SemanticRole, ...] = ()
    participants: tuple[ParticipantMention, ...] = ()
    detected_patterns: tuple[DetectedPattern, ...] = ()
    text_critical: tuple[TextCriticalNote, ...] = ()


# ---------------------------------------------------------------------------
# Bundle root.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HebrewAnalysisBundle:
    """The full deterministic analysis for one canonical reference span.

    Serializable, versioned, and — per the module docstring — free of any
    AI-generated content. See ``bible_engine.hebrew_analysis_service`` for
    the sole constructor.
    """

    bundle_schema_version: str
    reference: str  # canonical string form, e.g. "Gen.1.1-3"
    reference_hu: str  # e.g. "1 Mózes 1,1-3"
    book_id: str  # TAHOT book code, e.g. "Gen"
    language: str  # "hebrew" | "aramaic" | "mixed"
    verses: tuple[VerseAnalysis, ...]
    datasets: tuple[DatasetProvenance, ...]
    coverage: CoverageReport
    warnings: tuple[BundleWarning, ...] = ()


BUNDLE_SCHEMA_VERSION = "2c.0.0"

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "BundleWarning",
    "ClauseAnalysis",
    "ComponentAnalysis",
    "CoverageReport",
    "DatasetProvenance",
    "DetectedPattern",
    "HebrewAnalysisBundle",
    "LexicalSense",
    "MorphologyFacts",
    "ParticipantMention",
    "PhraseAnalysis",
    "RootInfo",
    "SemanticRole",
    "TextCriticalNote",
    "TokenAnalysis",
    "TokenProvenance",
    "VerseAnalysis",
]
