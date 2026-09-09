"""Phase 2E — the grounded Hungarian contextual-grammar/syntax AI contract.

This module defines the STRUCTURED output contract an AI model returns when
asked to interpret one verse's already-deterministic ``HebrewAnalysisBundle``
facts (Phase 2C/2D/2D.1/2D.2), plus the compact bundle-to-prompt-payload
serializer and the grounded prompt instructions themselves.

Boundary (see the module docstring in ``bible_engine.hebrew_analysis_bundle``
for the deterministic side of this same rule): the AI receives every
deterministic fact it is allowed to talk about — surface form, lemma,
morphology (stem/conjugation/person/gender/number/state kept as SEPARATE
fields, never merged), components, lexical sense, phrase/clause membership,
syntax relations, semantic roles, participants/coreference, syntax-grounding
status, Ketiv/Qere — and is instructed, repeatedly and structurally, never to
re-derive, invent, or override any of it. It is asked only to INTERPRET what
it was given: contextual sense selection, what a stem contributes to THIS
lexeme here, what a supplied construction means, and a plain-language syntax
summary of what was actually supplied — nothing invented, nothing supplied
being silently promoted to a stronger claim than the bundle itself makes.

No network call, no LLM call, no Streamlit dependency happens in this
module — it only builds prompts/schemas and defines the response
dataclasses. The actual model call is dependency-injected by the caller
(``bible_engine.hebrew_contextual_analysis_service``), exactly the same
convention ``bible_engine.original_language_analysis`` already uses for
``generate_text_fn``.
"""

from __future__ import annotations

from dataclasses import dataclass

from bible_engine.hebrew_analysis_bundle import VerseAnalysis
from bible_engine.hebrew_analysis_repository import (
    SYNTAX_GROUNDING_FULL,
    SYNTAX_GROUNDING_NONE,
    SYNTAX_GROUNDING_PARTIAL,
)
from bible_engine.hebrew_morphology_hu import (
    GENDER_HU,
    NUMBER_HU,
    PART_OF_SPEECH_HU,
    PERSON_HU,
    STATE_HU,
    STEM_HU,
    VERB_FORM_HU,
)

CONTEXTUAL_ANALYSIS_SCHEMA_VERSION = "2e.0.0"
CONTEXTUAL_ANALYSIS_PROMPT_VERSION = "2e.0.0"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
_VALID_CONFIDENCE = frozenset({CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW})


# ---------------------------------------------------------------------------
# Structured output contract.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WordNote:
    """One token's contextual-grammar explanation.

    ``lexical_basic_meaning_hu`` and ``contextual_meaning_hu`` are always
    kept as SEPARATE fields — the mandatory distinction §8 of the Phase 2E
    brief requires (the ``אֲשֶׁר`` regression: a context-specific rendering
    must never be presented as though it were the lexeme's universal
    meaning). Either may be empty; both empty is a valid ("nothing notable
    to add beyond the deterministic word card") result.
    """

    token_id: str
    lexical_basic_meaning_hu: str = ""
    contextual_meaning_hu: str = ""
    grammar_explanation_hu: str = ""
    syntax_explanation_hu: str = ""
    translation_note_hu: str = ""
    confidence: str = CONFIDENCE_LOW


@dataclass(frozen=True)
class ConstructionNote:
    """One multi-token construction observation (§5B of the brief) —
    e.g. a construct chain, double negation, infinitive absolute + finite
    verb, a multi-component preposition/article fusion.

    Grounding is mandatory, not just prompted: the service layer
    (``hebrew_contextual_analysis_service.validate_and_build_contextual_
    analysis``) accepts a note ONLY when its ``token_ids`` are covered by
    real deterministic structure — a Phase 2C ``DetectedPattern``, or an
    existing MACULA phrase/clause/syntax-relation/semantic-role/
    participant grouping. A note the model invented with no such backing
    is dropped, never displayed, regardless of how plausible it reads.

    ``evidence_pattern_ids`` is set by the SERVICE, never read from the
    model's own output (the model is never trusted to self-report its own
    grounding — same rule ``grounding_status`` already follows) — it names
    the ``DetectedPattern.pattern_id`` values that grounded this note when
    grounding came from a detected pattern; empty when grounding instead
    came directly from phrase/clause/relation/role/participant structure.
    """

    token_ids: tuple[str, ...]
    construction_type: str
    title_hu: str
    explanation_hu: str
    translation_significance_hu: str = ""
    confidence: str = CONFIDENCE_LOW
    evidence_pattern_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyntaxSummary:
    """A concise, non-technical-tree Hungarian sentence/clause structure
    summary (§5C). Always present (never ``None``) — an empty
    ``summary_hu`` with empty ``clause_ids`` is the valid "nothing
    supplied to summarize" result, e.g. under ``NO_GROUNDED_SYNTAX``."""

    summary_hu: str = ""
    clause_ids: tuple[str, ...] = ()
    confidence: str = CONFIDENCE_LOW


@dataclass(frozen=True)
class HebrewContextualAnalysis:
    """The full structured Phase 2E result for one verse.

    ``grounding_status`` always mirrors the bundle's own
    ``VerseAnalysis.syntax_grounding`` — the service layer OVERWRITES
    whatever the model reported here with the bundle's real value (the
    bundle is authoritative, never the model's self-report; see
    ``hebrew_contextual_analysis_service.validate_contextual_analysis``).
    """

    schema_version: str
    reference: str
    grounding_status: str
    word_notes: tuple[WordNote, ...] = ()
    construction_notes: tuple[ConstructionNote, ...] = ()
    syntax_summary: SyntaxSummary = SyntaxSummary()
    translation_notes: tuple[str, ...] = ()
    exegetical_notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# JSON schema for the model's structured (``response_schema``) output.
# ---------------------------------------------------------------------------

_STRING = {"type": "string"}
_STRING_ARRAY = {"type": "array", "items": _STRING}
_CONFIDENCE_ENUM = {"type": "string", "enum": [CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW]}

HEBREW_CONTEXTUAL_ANALYSIS_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "word_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "token_id": _STRING,
                    "lexical_basic_meaning_hu": _STRING,
                    "contextual_meaning_hu": _STRING,
                    "grammar_explanation_hu": _STRING,
                    "syntax_explanation_hu": _STRING,
                    "translation_note_hu": _STRING,
                    "confidence": _CONFIDENCE_ENUM,
                },
                "required": ["token_id"],
            },
        },
        "construction_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "token_ids": _STRING_ARRAY,
                    "construction_type": _STRING,
                    "title_hu": _STRING,
                    "explanation_hu": _STRING,
                    "translation_significance_hu": _STRING,
                    "confidence": _CONFIDENCE_ENUM,
                },
                "required": ["token_ids", "construction_type", "title_hu", "explanation_hu"],
            },
        },
        "syntax_summary": {
            "type": "object",
            "properties": {
                "summary_hu": _STRING,
                "clause_ids": _STRING_ARRAY,
                "confidence": _CONFIDENCE_ENUM,
            },
        },
        "translation_notes": _STRING_ARRAY,
        "exegetical_notes": _STRING_ARRAY,
        "warnings": _STRING_ARRAY,
    },
    "required": ["word_notes", "construction_notes", "syntax_summary"],
}


# ---------------------------------------------------------------------------
# Prompt: fixed instructions.
# ---------------------------------------------------------------------------

HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS = """
Héber/arámi nyelvi kontextuális elemző vagy, aki lelkészeknek és
teológushallgatóknak segít megérteni egy már ELEMZETT, determinisztikus
héber/arámi vershez tartozó nyelvtani és mondattani tényeket. TILOS bármely
héber/arámi nyelvtani tényt saját magadtól újraelemezni — az alábbi
DETERMINISZTIKUS ADATOK blokk az EGYETLEN forrás minden nyelvtani, lexikai
és mondattani tényre nézve.

SZIGORÚAN TILOS:
- lemmát, gyököt, morfológiát, igetörzset, igealakot, személyt/nemet/számot/
  állapotot, prefixum/suffixum-felosztást, frázis/tagmondat-tagságot,
  mondattani viszonyt, szemantikai szerepet, résztvevő/koreferencia-adatot
  KITALÁLNI, MEGVÁLTOZTATNI vagy FELÜLBÍRÁLNI — mindezt kizárólag az
  alább mellékelt adat közli;
- "gyök"-öt (héber triliterális gyököt) említeni vagy kitalálni — ez az
  adat NINCS jelen ebben az adatkészletben (lásd DETERMINISZTIKUS ADATOK);
  ha nincs gyök megadva egy szónál, egyáltalán ne beszélj gyökről annál a
  szónál;
- szövegkritikai (kéziratos) adatot kitalálni — LXX, holt-tengeri tekercsek,
  szamaritánus Pentateuchus vagy BHS/BHQ-apparátus NEM áll rendelkezésre;
  Ketív/Qeré esetén KIZÁRÓLAG a mellékelt determinisztikus Ketív/Qeré-adatot
  magyarázhatod (mi az írott és mi az olvasott alak) — más kéziratos
  variánst SOHA ne állíts;
- szórendből ÖNMAGÁBAN hangsúlyt vagy kiemelést állítani — ehhez az
  adatkészlethez jelenleg NINCS determinisztikus szórendi adat mellékelve,
  ezért szórendi kiemelésről egyáltalán ne nyilatkozz megalapozott
  tényként; legfeljebb óvatos, feltételes megfogalmazást használhatsz
  (pl. "kiemelt helyzetben állhat", "figyelemre méltó elhelyezés"), SOHA
  nem kategorikus kijelentést;
- vitatott identitási kérdést (pl. egy szereplő isteni/emberi volta)
  nyelvi eszközzel eldönteni;
- prédikációt, homiletikai alkalmazást vagy a nyelvtani tényből messze
  túlmutató teológiai következtetést írni (pl. TILOS: "a Piel Isten
  egyedülálló hatalmas cselekvését tárja fel" — csak akkor írhatsz
  teológiai/exegetikai megjegyzést, ha az KÖZVETLENÜL, nyelvileg
  alátámasztott a mellékelt adatból);
- univerzális, sablonos igetörzs-magyarázatot adni (pl. "a Hitpael mindig
  reflexív", "a Piel mindig intenzív") — helyette azt írd le, mit tesz EZ
  az igetörzs EZZEL a lexémával, EBBEN a szerkezetben, ha ehhez elég adat
  áll rendelkezésre; ha nem elég, adj rövidebb, óvatosabb, általánosabb
  magyarázatot ahelyett, hogy lexéma-specifikus árnyalatot találnál ki;
- kötelező mondattani állítást tenni olyan tokenre, amely NEM szerepel
  egyetlen mellékelt frázis/tagmondat/mondattani viszony/szemantikai
  szerep listában sem — az ilyen token "mondattani szerepe" mezője
  maradjon üres, vagy jelezd, hogy ehhez a szóhoz nincs mondattani adat;
- "construction_notes"-ban OLYAN nyelvtani szerkezet létezését állítani
  (pl. kettős tagadás, szerkezetes állapotú láncolat, abszolút infinitivus
  + véges igealak, bármilyen más szerkezet), amelyet az alábbi
  FELISMERT SZERKEZETEK blokk NEM sorol fel, ÉS amelynek tokenjei nem
  alkotnak együtt egyetlen mellékelt frázist/tagmondatot/mondattani
  viszonyt/szemantikai szerepet/résztvevőt sem — egy ilyen, alátámasztás
  nélküli szerkezet-megfigyelést a rendszer automatikusan eldob, akkor is,
  ha egyébként nyelvileg valószínűnek tűnik. A szerkezet MEGLÉTÉT mindig a
  determinisztikus adat állapítja meg; a te feladatod csak az, hogy
  MAGYARÁZD, mit jelent egy már felismert/adott szerkezet — sose te
  fedezd fel a szerkezet létezését.

FELISMERT SZERKEZETEK (a "FELISMERT SZERKEZETEK" blokk, ha a mellékelt
adatban szerepel) a Fázis 2C determinisztikus mintafelismerőjének kimenete
— minden odalistázott tétel már bizonyítottan létező, valós strukturális
tény (pl. hogy két tagadószó fordul elő, hogy egy szó szerkezetes
állapotban áll egy másik előtt). Ezekhez fűzhetsz kontextuális
magyarázatot ("construction_notes"-ban) — DE további, a listán NEM
szereplő szerkezet létezését ne állítsd, KIVÉVE ha az közvetlenül
levezethető a mellékelt frázis/tagmondat/mondattani viszony/szemantikai
szerep/résztvevő adatból (pl. egy mellékelt tagmondat vagy frázis maga
mutatja a szerkezetet, még ha a Fázis 2C mintafelismerő nem is nevezte
külön néven).

A "syntax_grounding" mező jelzi, mennyire teljes a mondattani lefedettség:
- FULLY_GROUNDED_SYNTAX: az adott vers minden tokenjéhez van megerősített
  igazítás — a mellékelt frázis/tagmondat/viszony-adat teljes körűen
  magyarázható.
- PARTIALLY_GROUNDED_SYNTAX: csak EGY RÉSZ tokenhez van mondattani adat —
  az alábbi adatban kifejezetten fel van sorolva, mely tokenekhez NINCS
  mondattani adat ebben a versben; ezekhez a tokenekhez NE állíts
  mondattani szerepet, csak azt, amit a lexikai/morfológiai adat közöl.
- NO_GROUNDED_SYNTAX: ehhez a vershez EGYÁLTALÁN nincs mondattani adat —
  "syntax_summary" és "construction_notes" mondattani jellegű elemei
  maradjanak üresek; csak morfológiai/lexikai szinten (pl. kettős tagadás
  két tagadószó jelenlétéből, prefixum+suffixum-szerkezet) tehetsz
  megfigyelést, ha ehhez elég a mellékelt komponens-adat.

KÖTELEZŐ:
- a lexikai alapjelentést (ha van) és a kontextuális jelentést MINDIG
  külön mezőben add meg, sose keverd össze — a kontextuális jelentés
  csak akkor térhet el az alapjelentéstől, ha ezt a mellékelt szerkezet/
  kontextus ténylegesen alátámasztja;
- ha egy mezőhöz nincs érdemi mondanivalód, hagyd üresen (üres string)
  vagy hagyd ki a listaelemet — ÜRES LISTA/MEZŐ ÉRVÉNYES, ELVÁRT
  eredmény, ha nincs valóban figyelemre méltó megfigyelés; SOHA ne
  gyárts mesterségesen tartalmat egy mező kitöltésére;
- KIZÁRÓLAG a mellékelt "token_id"/"clause_id" azonosítókra hivatkozz —
  új azonosítót ne generálj;
- kizárólag magyarul írj, elfogadott magyar teológiai héber
  terminológiával (igetörzs, igealak, alapszó, státusz stb. — az alábbi
  DETERMINISZTIKUS ADATOK blokk már ezekkel a magyar terminusokkal közli
  a tényeket, ezeket használd);
- légy tömör — egy szóhoz néhány rövid mondat elég, ne írj nyelvészeti
  disszertációt.
"""


def _hu(value: str, mapping: dict[str, str]) -> str:
    value = (value or "").strip()
    return mapping.get(value, value)


def _token_syntax_coverage(verse: VerseAnalysis) -> set[str]:
    """Every token_id that appears in at least one syntax structure
    (phrase/clause membership, a syntax edge, a semantic role, a
    participant mention, or a coreference link) for this verse — i.e. the
    set of tokens the deterministic layer actually has SOME mondattani
    fact about. Used both to build the "no syntax data for these tokens"
    prompt line and, in the service layer, to null out an over-claiming
    ``syntax_explanation_hu`` on an uncovered token under partial
    grounding."""
    covered: set[str] = set()
    for phrase in verse.phrases:
        covered.update(phrase.token_ids)
    for clause in verse.clauses:
        covered.update(clause.token_ids)
    for relation in verse.syntax_relations:
        if relation.parent_token_id:
            covered.add(relation.parent_token_id)
        if relation.child_token_id:
            covered.add(relation.child_token_id)
    for role in verse.semantic_roles:
        covered.update(role.token_ids)
        if role.predicate_id:
            covered.add(role.predicate_id)
    for participant in verse.participants:
        covered.update(participant.token_ids)
    for coref in verse.coreference:
        if coref.referring_token_id:
            covered.add(coref.referring_token_id)
    return covered


def construction_note_evidence(token_ids: tuple[str, ...], verse: VerseAnalysis) -> tuple[bool, tuple[str, ...]]:
    """The structural-grounding check the Phase 2E brief requires: a
    candidate ``ConstructionNote`` is admissible only when its
    ``token_ids`` are covered by REAL deterministic structure, never on
    the model's say-so alone (see ``ConstructionNote``'s docstring).

    Returns ``(grounded, evidence_pattern_ids)``:
    - ``token_ids`` a subset of some ``DetectedPattern.token_ids`` (Phase
      2C's deterministic structural detector, see
      ``bible_engine.hebrew_pattern_detection``) → grounded, with that
      pattern's id(s) as evidence — this is the ONLY case
      ``evidence_pattern_ids`` is non-empty;
    - otherwise, ``token_ids`` a subset of a single existing phrase's,
      clause's, syntax-relation's (parent/child pair), semantic role's
      (its tokens plus predicate), or participant's token set → grounded,
      no specific pattern id (the evidence IS that MACULA structure
      itself, already visible in the prompt payload);
    - neither → not grounded; the caller must reject the note.

    Deliberately does NOT match against ``DetectedPattern.evidence_token_ids``
    — that field mixes token- and component-level ids across detector
    types (see ``multicomponent_prefix_structure``), while ``token_ids`` is
    uniformly token-level on every detector and on every bundle structure
    this function checks.
    """
    ids = frozenset(t for t in token_ids if t)
    if not ids:
        return False, ()

    matching_patterns = tuple(
        pattern.pattern_id for pattern in verse.detected_patterns if ids <= frozenset(pattern.token_ids)
    )
    if matching_patterns:
        return True, matching_patterns

    for phrase in verse.phrases:
        if ids <= frozenset(phrase.token_ids):
            return True, ()
    for clause in verse.clauses:
        if ids <= frozenset(clause.token_ids):
            return True, ()
    for relation in verse.syntax_relations:
        pair = frozenset(t for t in (relation.parent_token_id, relation.child_token_id) if t)
        if pair and ids <= pair:
            return True, ()
    for role in verse.semantic_roles:
        role_ids = frozenset(role.token_ids)
        if role.predicate_id:
            role_ids = role_ids | {role.predicate_id}
        if ids <= role_ids:
            return True, ()
    for participant in verse.participants:
        if ids <= frozenset(participant.token_ids):
            return True, ()

    return False, ()


def _format_token_block(token, covered: set[str]) -> str:
    lines: list[str] = [f"TOKEN {token.token_id}"]
    lines.append(f"  alak: {token.surface}")
    if token.lemma:
        lines.append(f"  lemma: {token.lemma}")
    if token.root is not None:
        lines.append(f"  gyök: {token.root.consonants}")
    lines.append(f"  szófaj: {_hu(token.part_of_speech, PART_OF_SPEECH_HU) or token.part_of_speech or '—'}")

    morphology = token.morphology
    if morphology.verb_stem:
        lines.append(f"  igetörzs: {_hu(morphology.verb_stem, STEM_HU)}")
    if morphology.verb_form:
        lines.append(f"  igealak: {_hu(morphology.verb_form, VERB_FORM_HU)}")
    agreement = [
        _hu(morphology.person, PERSON_HU),
        _hu(morphology.gender, GENDER_HU),
        _hu(morphology.number, NUMBER_HU),
        _hu(morphology.state, STATE_HU),
    ]
    agreement = [part for part in agreement if part]
    if agreement:
        lines.append(f"  személy/nem/szám/állapot: {', '.join(agreement)}")

    for component in token.components:
        comp_bits = [component.role_label_hu, component.surface]
        if component.gloss_hu:
            comp_bits.append(component.gloss_hu)
        elif component.gloss_en:
            comp_bits.append(component.gloss_en)
        lines.append(f"  komponens[{component.component_index}]: {' · '.join(bit for bit in comp_bits if bit)}")

    if token.lexical_sense is not None:
        sense = token.lexical_sense
        lines.append(f"  lexikai alapjelentés: {sense.base_meaning_hu or '—'}")
        if sense.possible_meanings_hu:
            lines.append(f"  lehetséges jelentések: {' | '.join(sense.possible_meanings_hu)}")
    else:
        lines.append("  lexikai alapjelentés: nincs magyar lexikai adat ehhez a szóhoz")

    if token.ketiv and token.qere and token.ketiv != token.qere:
        lines.append(f"  ketív/qeré: írott={token.ketiv} / olvasott={token.qere}")

    if token.token_id not in covered:
        lines.append("  mondattani adat: NINCS ehhez a tokenhez ebben a versben")

    return "\n".join(lines)


def build_hebrew_contextual_analysis_payload(verse: VerseAnalysis) -> str:
    """The compact bundle-to-prompt serializer — one ``VerseAnalysis``,
    never the raw database object, never other verses. See the module
    docstring for the deterministic/AI boundary this enforces."""
    covered = _token_syntax_coverage(verse)
    lines: list[str] = [
        "==================================================",
        "DETERMINISZTIKUS ADATOK (kizárólagos forrás)",
        "==================================================",
        f"vers: {verse.verse_id}",
        f"szöveg: {verse.hebrew_text}",
        f"mondattani lefedettség (syntax_grounding): {verse.syntax_grounding}",
    ]
    if verse.syntax_grounding == SYNTAX_GROUNDING_PARTIAL:
        uncovered = [token.token_id for token in verse.tokens if token.token_id not in covered]
        if uncovered:
            lines.append(f"mondattani adat NÉLKÜLI tokenek ebben a versben: {', '.join(uncovered)}")
    lines.append("")

    for token in verse.tokens:
        lines.append(_format_token_block(token, covered))
        lines.append("")

    if verse.detected_patterns:
        lines.append("FELISMERT SZERKEZETEK (Fázis 2C determinisztikus mintafelismerő):")
        for pattern in verse.detected_patterns:
            lines.append(
                f"  {pattern.pattern_id} [{pattern.pattern_type}] "
                f"tokenek: {', '.join(pattern.token_ids)} — {pattern.explanation_hu}"
            )
        lines.append("")

    if verse.phrases:
        lines.append("FRÁZISOK:")
        for phrase in verse.phrases:
            lines.append(
                f"  {phrase.phrase_id} [{phrase.phrase_type}] tokenek: {', '.join(phrase.token_ids)}"
            )
        lines.append("")

    if verse.clauses:
        lines.append("TAGMONDATOK:")
        for clause in verse.clauses:
            bits = [f"{clause.clause_id} [{clause.clause_type or 'ismeretlen típus'}]"]
            if clause.predicate_id:
                bits.append(f"állítmány={clause.predicate_id}")
            if clause.subject_id:
                bits.append(f"alany={clause.subject_id}")
            if clause.object_ids:
                bits.append(f"tárgy={', '.join(clause.object_ids)}")
            lines.append("  " + " · ".join(bits))
        lines.append("")

    if verse.syntax_relations:
        lines.append("MONDATTANI VISZONYOK:")
        for relation in verse.syntax_relations:
            lines.append(
                f"  {relation.relation_id} [{relation.relation_type}] "
                f"{relation.parent_token_id or '—'} -> {relation.child_token_id or '—'}"
            )
        lines.append("")

    if verse.semantic_roles:
        lines.append("SZEMANTIKAI SZEREPEK:")
        for role in verse.semantic_roles:
            lines.append(
                f"  {role.role_id} [{role.role_type or role.role_code}] "
                f"állítmány={role.predicate_id or '—'} tokenek={', '.join(role.token_ids)}"
            )
        lines.append("")

    if verse.participants:
        lines.append("RÉSZTVEVŐK:")
        for participant in verse.participants:
            lines.append(f"  {participant.participant_id} tokenek={', '.join(participant.token_ids)}")
        lines.append("")

    if verse.coreference:
        lines.append("KOREFERENCIA:")
        for coref in verse.coreference:
            lines.append(
                f"  {coref.link_id} [{coref.relation_type}] "
                f"{coref.referring_token_id or '—'} -> {coref.participant_id}"
            )
        lines.append("")

    return "\n".join(lines)


def build_hebrew_contextual_analysis_prompt(verse: VerseAnalysis) -> str:
    payload = build_hebrew_contextual_analysis_payload(verse)
    return (
        f"{HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS}\n"
        "==================================================\n"
        "FELADAT\n"
        "==================================================\n\n"
        f"{payload}\n"
        "Add vissza a fenti sémának megfelelő, kizárólag a fenti adatra "
        "épülő strukturált elemzést erről a versről.\n"
    )


__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "CONTEXTUAL_ANALYSIS_PROMPT_VERSION",
    "CONTEXTUAL_ANALYSIS_SCHEMA_VERSION",
    "HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS",
    "HEBREW_CONTEXTUAL_ANALYSIS_RESPONSE_SCHEMA",
    "ConstructionNote",
    "HebrewContextualAnalysis",
    "SyntaxSummary",
    "WordNote",
    "build_hebrew_contextual_analysis_payload",
    "build_hebrew_contextual_analysis_prompt",
    "construction_note_evidence",
]
