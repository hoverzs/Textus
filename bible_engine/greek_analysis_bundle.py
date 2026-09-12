"""Greek Analysis v2 — Phase 2A normalized data model.

Mirrors the SHAPE of ``bible_engine.hebrew_analysis_bundle`` (dataset
provenance, per-token morphology/lexical facts, verse-level container with
forward-compatible-but-empty syntax fields) without copying Hebrew-specific
linguistic categories — Greek morphology has its own fields (see
``GreekMorphologyFacts``), and nothing here synthesizes syntax data that
does not exist yet (``GreekVerseAnalysis.phrases``/``clauses``/
``syntax_relations``/``semantic_roles``/``participants``/``coreference`` are
always empty in Phase 2A — see the audit's §7/§8 findings:
``docs/greek_analysis_v2_inventory.md``).

Every field here is populated from a genuinely available deterministic
source (TAGNT tokens + the shared ``morphology_hu`` decoder + the Hungarian
lexicon + the TBESG English fallback). No field is inferred, guessed, or
AI-generated. See ``bible_engine.greek_analysis_service`` for the sole
builder function.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Dataset-level provenance.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GreekDatasetProvenance:
    dataset_id: str  # "tagnt" | "tbesg" | "lexicon_hu" | "tegmc"
    display_name: str
    source_repository: str
    source_commit: str
    license: str
    attribution: str


@dataclass(frozen=True)
class GreekCoverageReport:
    has_morphology: bool
    has_lexical_sense: bool
    has_syntax: bool
    has_semantic_roles: bool
    has_participants: bool
    token_count: int
    fully_decoded_token_count: int
    notes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Token-level.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GreekMorphologyFacts:
    """Normalized morphology for one Greek token, derived from
    ``bible_engine.morphology_hu.parse_morphology_hu`` — never re-decoded or
    reinterpreted here. Every field is either a value the source (TAGNT's
    Robinson/STEPBible-style code, cross-checked against TEGMC — see the
    Phase 2A foundation doc) genuinely encodes, or an explicit empty string.

    ``aspect`` is deliberately ALWAYS empty: neither TAGNT's morph codes nor
    TEGMC represent verbal aspect as a field distinct from tense-form (see
    the audit's §4.1/§7 terminology findings) — inventing an aspect value
    here would be exactly the kind of unsupported inference this bundle
    exists to prevent downstream AI from making.
    """

    raw_code: str
    code_system: str = "TAGNT/Robinson (TEGMC-verified)"
    part_of_speech: str = ""
    case: str = ""
    number: str = ""
    gender: str = ""
    person: str = ""
    tense: str = ""
    aspect: str = ""  # never populated in Phase 2A — see docstring
    voice: str = ""
    mood: str = ""
    verb_form: str = ""  # "participle" | "infinitive" | ""
    degree: str = ""
    pronoun_type: str = ""
    name_type: str = ""
    extra: tuple[str, ...] = ()
    summary_hu: str = ""
    # "fully_decoded" | "unresolved" — mirrors the Hebrew MorphologyFacts
    # confidence taxonomy's meaningful subset (Greek has no
    # "partially_decoded"/"malformed"/"not_applicable" case today: the
    # corpus-wide audit found 0 unresolved codes across all 142,096 tokens).
    confidence: str = "unresolved"
    unresolved_parts: tuple[str, ...] = ()


@dataclass(frozen=True)
class GreekLexicalSense:
    """One Hungarian lexical record for a canonical (disambiguated) Strong
    id. Mirrors Hebrew's ``LexicalSense`` shape; ``review_status``/
    ``translation_method``/``source_name``/``source_version`` are the exact
    provenance fields the Phase 2A audit found missing from runtime
    visibility (see ``bible_engine.lexicon_hu.HungarianLexiconEntry``,
    fixed in this same phase) — NEVER omit or default these away, since
    "coverage" and "quality" are explicitly different questions (the audit's
    central finding: 99.98% effective token coverage, 0% human-reviewed).
    """

    strong_id: str
    lemma: str
    base_meaning_hu: str
    possible_meanings_hu: tuple[str, ...]
    note_hu: str
    review_status: str  # "draft" | "reviewed"
    translation_method: str  # "ai_assisted" | "human"
    source_name: str
    source_version: str
    resolved_via_alias: bool = False
    alias_target_strong_id: str = ""


@dataclass(frozen=True)
class GreekTokenProvenance:
    text_source: str = "tagnt"
    morphology_source: str = "tagnt"
    lemma_source: str = "tagnt"
    lexical_source: str = "lexicon_hu"
    syntax_source: str = ""  # empty until a future MACULA Greek phase


@dataclass(frozen=True)
class GreekTokenAnalysis:
    """One deterministic Greek surface token.

    ``token_id`` is the Phase 2A stable identity — see
    ``docs/greek_analysis_v2_phase2a_foundation.md`` §8 for the full
    identity contract (format, why ``word_index`` alone is not future-proof
    against a later MACULA Greek import, and what normalization a future
    alignment step will need to do).
    """

    token_id: str  # "{book}.{chapter}.{verse}:{word_index}", e.g. "Jhn.3.16:5"
    book: str
    chapter: int
    verse: int
    word_index: int

    surface: str  # TAGNT greek_form (pilcrow-stripped, bracket-preserved — see tagnt_sqlite._clean_greek_form)
    lemma: str

    # The DISAMBIGUATED identity (GreekLexiconEntry.canonical_strong_id
    # shape, e.g. "G0007G") — always what TAGNT's own strong_id column
    # already is; never the bare undisambiguated eStrong.
    strong_id: str
    edition_flags: str

    part_of_speech: str
    morphology: GreekMorphologyFacts

    lexical_sense: GreekLexicalSense | None
    contextual_sense: None = None  # reserved for a future AI-interpretation layer — never populated deterministically

    provenance: GreekTokenProvenance = field(default_factory=GreekTokenProvenance)

    # Phase 2C addition — additive only, no Phase 2A field's meaning
    # changed. "" until a syntax-attachment step (attach_syntax /
    # attach_syntax_via_repository) sets it; one of EXACT/COMPOSITE/
    # VALIDATED_FALLBACK/UNRESOLVED_TEXTUAL_VARIANT/UNRESOLVED_OTHER
    # afterward. The contextual-analysis prompt builder uses this to
    # forbid the model from asserting a syntax role for an unresolved
    # token (Phase 2C §9/§15).
    alignment_status: str = ""


# ---------------------------------------------------------------------------
# Verse level. Syntax-shaped fields are structurally present (forward-
# compatible with a future MACULA Greek import) but ALWAYS empty in Phase
# 2A — no deterministic local source supplies them yet (audit §7/§8).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GreekPhraseAnalysis:
    phrase_id: str
    phrase_type: str
    token_ids: tuple[str, ...]
    head_token_id: str | None
    parent_phrase_id: str | None
    function: str


@dataclass(frozen=True)
class GreekClauseAnalysis:
    clause_id: str
    clause_type: str
    token_ids: tuple[str, ...]
    predicate_id: str | None
    parent_clause_id: str | None
    relation_to_parent: str


@dataclass(frozen=True)
class GreekSyntaxRelation:
    relation_id: str
    relation_type: str
    head_token_id: str
    dependent_token_id: str
    role_code: str


@dataclass(frozen=True)
class GreekSemanticRole:
    role_id: str
    role_type: str
    predicate_id: str | None
    token_ids: tuple[str, ...]


@dataclass(frozen=True)
class GreekParticipantMention:
    participant_id: str
    token_ids: tuple[str, ...]
    referent: str


@dataclass(frozen=True)
class GreekCoreferenceLink:
    """One MACULA-supplied referential link — kept as source data, not an
    interpretive claim. ``link_type`` distinguishes the two genuinely
    different kinds MACULA provides (never conflated): ``"referent"``
    (a pronoun pointing at its antecedent token(s)) and ``"subjref"`` (a
    participle/infinitive pointing at its implicit subject's token) — see
    ``bible_engine.greek_syntax_sqlite`` module docstring."""

    source_token_id: str
    link_type: str  # "referent" | "subjref"
    target_token_ids: tuple[str, ...]


@dataclass(frozen=True)
class GreekDetectedPattern:
    """Deterministically detected structural fact — none exist in Phase
    2A (no construction detection has been built yet; the audit's §8
    ranked candidate list is planning only). Kept present, always empty,
    so a future phase's ``VerseAnalysis`` shape does not need to change."""

    pattern_id: str
    pattern_type: str
    token_ids: tuple[str, ...]
    evidence_token_ids: tuple[str, ...]
    detector_version: str
    confidence: str
    explanation_hu: str


SYNTAX_GROUNDING_NONE = "NO_GROUNDED_SYNTAX"
SYNTAX_GROUNDING_PARTIAL = "PARTIALLY_GROUNDED_SYNTAX"
SYNTAX_GROUNDING_FULL = "FULLY_GROUNDED_SYNTAX"


@dataclass(frozen=True)
class GreekVerseAnalysis:
    verse_id: str  # "Jhn.3.16"
    book: str
    chapter: int
    verse: int
    greek_text: str
    tokens: tuple[GreekTokenAnalysis, ...]
    phrases: tuple[GreekPhraseAnalysis, ...] = ()
    clauses: tuple[GreekClauseAnalysis, ...] = ()
    syntax_relations: tuple[GreekSyntaxRelation, ...] = ()
    semantic_roles: tuple[GreekSemanticRole, ...] = ()
    participants: tuple[GreekParticipantMention, ...] = ()
    coreference: tuple[GreekCoreferenceLink, ...] = ()
    detected_patterns: tuple[GreekDetectedPattern, ...] = ()
    syntax_grounding: str = SYNTAX_GROUNDING_NONE


# ---------------------------------------------------------------------------
# Bundle root.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GreekAnalysisBundle:
    """The full deterministic analysis for one canonical NT reference span.

    Serializable, versioned, and free of any AI-generated content — see
    ``bible_engine.greek_analysis_service`` for the sole constructor. Token
    order within each verse is guaranteed to match ``word_index`` ascending
    (TAGNT's own storage order; see the corpus-wide ordering invariant test
    in ``tests/test_greek_analysis_bundle.py``).
    """

    bundle_schema_version: str
    reference: str
    reference_hu: str
    book: str
    verses: tuple[GreekVerseAnalysis, ...]
    datasets: tuple[GreekDatasetProvenance, ...]
    coverage: GreekCoverageReport


__all__ = [
    "GreekDatasetProvenance",
    "GreekCoverageReport",
    "GreekMorphologyFacts",
    "GreekLexicalSense",
    "GreekTokenProvenance",
    "GreekTokenAnalysis",
    "GreekPhraseAnalysis",
    "GreekClauseAnalysis",
    "GreekSyntaxRelation",
    "GreekSemanticRole",
    "GreekParticipantMention",
    "GreekCoreferenceLink",
    "GreekDetectedPattern",
    "GreekVerseAnalysis",
    "GreekAnalysisBundle",
    "SYNTAX_GROUNDING_NONE",
    "SYNTAX_GROUNDING_PARTIAL",
    "SYNTAX_GROUNDING_FULL",
]
