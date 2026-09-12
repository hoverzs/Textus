"""Phase 2C §8-§15 — structured, evidence-grounded Hungarian contextual
analysis for Greek verses. Mirrors ``bible_engine.hebrew_contextual_analysis``'s
architecture (dataclasses, evidence-id grounding, one-call-per-verse
contract) closely, but the safety-rule prose is entirely Greek-specific —
see §10 below, built directly from the Phase 2A/2B terminology-rule
findings (aorist/imperfect/middle/passive/perfect/participle/genitive/
article/preposition+case), not copied from Hebrew's construct-state rules,
which have no Greek equivalent.
"""

from __future__ import annotations

from dataclasses import dataclass

from bible_engine.greek_analysis_bundle import GreekVerseAnalysis

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

CONTEXTUAL_ANALYSIS_SCHEMA_VERSION = "greek-2c.1.0"
CONTEXTUAL_ANALYSIS_PROMPT_VERSION = "greek-2c.1.1"


@dataclass(frozen=True)
class GreekWordNote:
    """One token's contextual-grammar explanation. ``lexical_basic_meaning_hu``
    (server-authoritative, §11 lexical authority model) and
    ``contextual_meaning_hu`` (model-generated) are always kept SEPARATE —
    a context-specific rendering must never be presented as the lexeme's
    universal meaning."""

    token_id: str
    lexical_basic_meaning_hu: str = ""
    lexical_provenance: str = ""  # "reviewed" | "draft" | "english_fallback" | "" — set server-side, never by the model
    contextual_meaning_hu: str = ""
    morphological_explanation_hu: str = ""
    syntax_role_hu: str = ""  # only ever populated when the token's own alignment status is resolved (§9/§15)
    translation_note_hu: str = ""
    confidence: str = CONFIDENCE_LOW


@dataclass(frozen=True)
class GreekConstructionNote:
    """One multi-token construction observation. Grounding is mandatory
    and evidence-id-based (§12) — the model cites ``evidence_ids`` naming
    identifiers actually printed in the prompt payload (a
    ``GreekDetectedPattern.pattern_id``, ``GreekPhraseAnalysis.phrase_id``,
    ``GreekClauseAnalysis.clause_id``, or a semantic-role/coreference id);
    the service independently re-validates every cited id and computes
    ``token_ids`` itself from the resolved evidence — never trusted from
    the model. A note with zero valid ``evidence_ids`` is dropped
    entirely."""

    token_ids: tuple[str, ...]
    construction_type: str
    title_hu: str
    explanation_hu: str
    translation_significance_hu: str = ""
    confidence: str = CONFIDENCE_LOW
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GreekSyntaxSummary:
    summary_hu: str = ""
    clause_ids: tuple[str, ...] = ()
    confidence: str = CONFIDENCE_LOW


@dataclass(frozen=True)
class GreekContextualAnalysis:
    """The full structured Phase 2C result for one verse.
    ``grounding_status`` always mirrors the bundle's own
    ``GreekVerseAnalysis.syntax_grounding`` — the service OVERWRITES
    whatever the model reported here with the bundle's real value."""

    schema_version: str
    reference: str
    grounding_status: str
    word_notes: tuple[GreekWordNote, ...] = ()
    construction_notes: tuple[GreekConstructionNote, ...] = ()
    syntax_summary: GreekSyntaxSummary = GreekSyntaxSummary()
    translation_notes: tuple[str, ...] = ()
    exegetical_notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# JSON schema for the model's structured (response_schema) output.
# ---------------------------------------------------------------------------

_STRING = {"type": "string"}
_STRING_ARRAY = {"type": "array", "items": _STRING}
_CONFIDENCE_ENUM = {"type": "string", "enum": [CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW]}

GREEK_CONTEXTUAL_ANALYSIS_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "word_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "token_id": _STRING,
                    "contextual_meaning_hu": _STRING,
                    "morphological_explanation_hu": _STRING,
                    "syntax_role_hu": _STRING,
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
                    "evidence_ids": _STRING_ARRAY,
                    "construction_type": _STRING,
                    "title_hu": _STRING,
                    "explanation_hu": _STRING,
                    "translation_significance_hu": _STRING,
                    "confidence": _CONFIDENCE_ENUM,
                },
                "required": ["evidence_ids", "construction_type", "title_hu", "explanation_hu"],
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
# Prompt: fixed instructions. Note lexical_basic_meaning_hu is deliberately
# NOT in the model's response schema at all (unlike Hebrew's, which asks
# the model to also RETURN it) — §11's lexical authority model means the
# server ALWAYS supplies it (with its own provenance), so asking the model
# to also generate a version it will never be allowed to override is pure
# waste and an invitation to drift; the model receives it as READ-ONLY
# context in the payload instead (see build_greek_contextual_analysis_payload).
# ---------------------------------------------------------------------------

GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS = """
Görög nyelvi kontextuális elemző vagy, aki lelkészeknek és
teológushallgatóknak segít megérteni egy már ELEMZETT, determinisztikus
görög újszövetségi vershez tartozó nyelvtani és mondattani tényeket. TILOS
bármely görög nyelvtani tényt saját magadtól újraelemezni — az alábbi
DETERMINISZTIKUS ADATOK blokk az EGYETLEN forrás minden nyelvtani,
alaktani, mondattani és lexikai tényre nézve. Ha egy adat hiányzik vagy
üres a blokkban, az azt jelenti, hogy a rendszer nem rendelkezik ezzel az
adattal — ilyenkor NEM szabad kitalálnod vagy "logikusan" kikövetkeztetned,
egyszerűen hagyd ki vagy jelezd bizonytalanként.

KÖTELEZŐ — SOSE VÁLTOZTASD MEG EZEKET (a rendszer determinisztikusan adja):
lemma, szófaj, eset (case), szám (number), nem (gender), személy (person),
igeidő-alak (tense-form), igenem (voice), mód (mood), fok (degree),
névmás/névelő altípus. Ha ezek közül bármelyiket a saját szavaiddal
megismétled, PONTOSAN a megadott értéket használd — SOSE írj mást, még
"finomítás" céljából sem.

A "lexikai alapjelentés" mezőt a rendszer TÖLTI KI, neked NEM kell (és nem
is szabad) megadnod — csak a "kontextuális jelentés" mezőt te generálod, a
vers konkrét szövegkörnyezetére vonatkozóan, MINDIG külön a lexikai
alapjelentéstől.

==================================================
GÖRÖG-SPECIFIKUS SZEMANTIKAI BIZTONSÁGI SZABÁLYOK
==================================================

FONTOS: az alábbi szabályok NEM egy tiltólistán szereplő szó szerinti
kifejezésre vonatkoznak, hanem a MÖGÖTTES, túláltalánosító ÁLLÍTÁSRA — akkor
is megsértve vannak, ha más szavakkal, körülírással vagy szinonimával
fogalmazod meg ugyanazt a tartalmat. A "pontszerű cselekvés" tiltása
ugyanúgy vonatkozik a "pontszerű esemény", "egyszer megtörtént esemény"
vagy "lezárt, meg nem ismételhető cselekvés" megfogalmazásra is — a
kifejezés szó szerinti elkerülése önmagában NEM elég, ha a mondat
tartalmilag ugyanazt az alaktanilag alá nem támasztott, univerzális
állítást teszi.

Egy konkrét (aoristos) példán a három szint, amit SOSE keverj össze:

  DETERMINISZTIKUS TÉNY: "Az ige aoristos indicativus."
  LEHETSÉGES KONTEXTUÁLIS MAGYARÁZAT (óvatos, nem univerzális): "Ebben a
  mondatban elbeszélő funkcióban jelenik meg."
  ALÁTÁMASZTATLAN ÁLTALÁNOS ÁLLÍTÁS (TILOS, bármely megfogalmazásban):
  "Az aoristos azt jelenti, hogy ez egyszeri/pontszerű esemény."

Ugyanez a három szint minden alábbi kategóriára érvényes (imperfektum,
mediális igenem, passzív igenem, perfectum, igenév, genitivus, névelő) —
az alaktani tény mindig szabadon leírható, a kontextuális magyarázat
mindig óvatos és nem-univerzális, az alátámasztatlan általános állítás
pedig minden megfogalmazásban tilos, nem csak a lenti konkrét
példamondatokban.

AORISZTOSZ: a morfológiai aoristos SOSE válik automatikusan "egyszerű
múlt", "egyszeri cselekvés" vagy "pontszerű cselekvés" kijelentéssé — sem
szó szerint, sem körülírva (pl. "pontszerű esemény", "egyszer megtörtént
cselekvés", "lezárt egyszeri esemény", "once-for-all action"). Az
aoristos egy alaktani forma; időbeli vagy Aktionsart-jellegű értelmezés
csak akkor engedhető meg, ha EXPLICIT módon értelmezésként jelölöd (ld.
alább TÉNY vs. ÉRTELMEZÉS).

IMPERFEKTUM: SOSE válik automatikusan egyetemesen "folyamatos múlt"
kijelentéssé — az imperfektum alaki tulajdonságait írd le, ne állíts
univerzális aspektuális jelentést.

MEDIÁLIS IGENEM: SOSE válik automatikusan "visszaható" jelentéssé. Ha a
deterministikus adat deponens igenemet jelez, ezt a tényt írd le
("mediális/passzív deponens alak"), de NE állíts ebből visszaható vagy más
szemantikai funkciót.

PASSZÍV IGENEM: a morfológiai passzívum NEM jelenti automatikusan, hogy a
mondat szemantikailag is egyszerű szenvedő szerkezet — a cselekvő
megnevezésének hiánya vagy jelenléte, illetve a kontextus dönti el ezt, amit
csak akkor említhetsz, ha a determinisztikus adat ezt ténylegesen
alátámasztja (pl. egy ὑπό + genitivus ágens-kifejezés jelen van a
tokenlistában).

PERFECTUM: NE redukáld egyetemesen erre a sablonra: "befejezett múlt,
amelynek eredménye fennáll" — ez sokszor helytálló, de nem minden esetben;
csak akkor fogalmazd meg ilyen erősen, ha a kontextus ezt ténylegesen
alátámasztja, egyébként elégedj meg az alaktani ténnyel (perfectum alak).

IGENÉV (participium): az alaktani adat (idő, igenem, eset, szám, nem) SOSE
határozza meg önmagában, hogy az igenév időhatározói, okhatározói,
megengedő, feltételes, eszközhatározói vagy körülményhatározói funkciójú —
ezt csak akkor állíthatod, ha a mondattani adat (pl. a tagmondat típusa
vagy egy determinisztikus konstrukció-jelölés) ezt kifejezetten
alátámasztja. Egyébként semleges leírást adj: "igenévi alak, funkciója a
mondattani szerkezetből nem egyértelműen determinisztikus."

GENITIVUS: az eset önmagában SOSE határozza meg, hogy birtokos, alanyi
(subjective), tárgyi (objective), részelő (partitive) vagy más genitivus-
altípusról van szó — ehhez konkrét mondattani vagy lexikai evidencia kell,
amit csak akkor nevezhetsz meg, ha ténylegesen rendelkezésre áll.

NÉVELŐ: a határozott névelő puszta jelenléte SOSE indokol
hangsúly-/határozottság-teológiai következtetést (pl. "ez kiemeli, hogy
EZ az egyetlen igaz..."). A névelőt csak alaktani tényként írd le, hacsak a
mondattani adat kifejezetten mást nem támaszt alá.

ELÖLJÁRÓSZÓ + ESET: az alapvető lexikai/esetjelentés (pl. "ἐν + dativus:
hely- vagy eszközhatározói jelentés") determinisztikus és közölhető. A
kontextuális, finomabb jelentésárnyalatot mindig VILÁGOSAN magyarázó,
nem kánoni jellegű megfogalmazásban add meg (ld. TÉNY vs. ÉRTELMEZÉS).

==================================================
TÉNY vs. KONTEXTUÁLIS MAGYARÁZAT vs. ÉRTELMEZÉS — HÁROM SZINT, SOSE KEVERD ÖSSZE
==================================================

1. DETERMINISZTIKUS TÉNY (a rendszer adja, te csak megismételheted
   pontosan): "Az ige aoristos indicativus alakban áll."
2. KONTEXTUÁLIS MAGYARÁZAT (a te feladatod, óvatos, a tényre épülő):
   "Az aoristos itt az eseményt egészében szemlélő elbeszélő alak része
   lehet."
3. ÉRTELMEZÉS (csak világosan jelölve, sose alaktani tényként): "A szerző
   ezzel retorikai nyomatékot ad..." — az ilyen szintű állítást MINDIG
   egyértelműen értelmezésként kell megjelölnöd (pl. "ez összefügghet
   azzal, hogy…", "egyes magyarázók szerint…"), SOSE úgy, mintha
   nyelvtani tény volna.

Ha a rendelkezésre álló adat nem elegendő egy állításhoz, használj
óvatos, bizonytalanságot jelző magyar megfogalmazást ("a rendelkezésre
álló adat alapján nem egyértelmű…"), NE egészítsd ki saját tudásból.

==================================================
MONDATTANI GROUNDING — SOSE JAVÍTSD KI A HIÁNYZÓ ILLESZTÉST
==================================================

Minden szó rendelkezik egy "alignment_status" mezővel. Ha egy szó
UNRESOLVED_TEXTUAL_VARIANT vagy UNRESOLVED_OTHER státuszú, ez azt jelenti,
hogy a determinisztikus mondattani (MACULA) adat NEM ÉRHETŐ EL ehhez a
szóhoz — ilyenkor TILOS mondattani szerepet (syntax_role_hu) megadnod
ehhez a szóhoz, akkor is, ha "logikusnak" tűnne egy hasonló szó alapján.
Ha egy vers teljes egészében "grounding_status": "NO_GROUNDED_SYNTAX",
akkor a teljes versre nézve TILOS bármilyen mondattani szerepet vagy
szerkezetet állítanod — csak alaktani és lexikai magyarázatot adhatsz.
Ha "PARTIALLY_GROUNDED_SYNTAX", csak azokhoz a szavakhoz/szerkezetekhez
adhatsz mondattani magyarázatot, amelyekhez ténylegesen van
determinisztikus adat a payloadban.

==================================================
KONSTRUKCIÓ-MEGJEGYZÉSEK — CSAK EVIDENCIA-ALAPÚ
==================================================

Minden construction_notes tételhez KÖTELEZŐ megadnod legalább egy valós
evidence_id-t (a payloadban ténylegesen szereplő pattern_id, phrase_id,
clause_id vagy szerep-azonosító). Új szócsoportosítást vagy szerkezetet
NEM találhatsz ki — csak a payloadban ténylegesen jelölt mintákra
(FELISMERT SZERKEZETEK blokk) hivatkozhatsz. A token_ids mezőt NEM kell
megadnod — a rendszer ezt magától az evidenciából számolja.

TÖMÖRSÉG: legfeljebb 5 word_notes tételt emelj ki részletesen (a
legfontosabbakat); construction_notes csak annyi, amennyi a payloadban
ténylegesen jelölt mintaszámhoz igazodik. syntax_summary legfeljebb 2-3
mondat. translation_notes/exegetical_notes összesen legfeljebb 3-3 rövid
tétel.
"""


def build_greek_contextual_analysis_payload(verse: GreekVerseAnalysis, lexicon_lookup=None) -> str:
    """Formats the verse's deterministic bundle into the exact text block
    the model receives. ``lexicon_lookup`` (optional) maps token_id ->
    (base_meaning_hu, provenance_label) — when omitted, lexical context is
    read directly from each token's own ``lexical_sense``."""
    lines: list[str] = ["DETERMINISZTIKUS ADATOK", "=" * 24, f"Hivatkozás: {verse.verse_id}", f"Görög szöveg: {verse.greek_text}", ""]

    lines.append("SZAVAK (token_id | alak | lemma | szófaj | alaktan | alignment_status | lexikai alapjelentés [forrás]):")
    for token in verse.tokens:
        m = token.morphology
        morph_parts = [p for p in (m.case, m.number, m.gender, m.person, m.tense, m.voice, m.mood, m.verb_form, m.degree) if p]
        morph_str = ", ".join(morph_parts) if morph_parts else "—"
        lex = token.lexical_sense
        if lex is not None:
            provenance = "ellenőrzött" if lex.review_status == "reviewed" else "AI-draft"
            lex_str = f"{lex.base_meaning_hu or '(nincs)'} [{provenance}]"
        else:
            lex_str = "(nincs lexikai adat)"
        lines.append(
            f"  [{token.token_id}] {token.surface} | {token.lemma} | {token.part_of_speech} | "
            f"{morph_str} | {token.morphology.confidence} | alignment={token.alignment_status or 'unknown'} | {lex_str}"
        )
    lines.append("")

    if verse.clauses:
        lines.append("TAGMONDATOK (clause_id | típus | token_id-k):")
        for clause in verse.clauses:
            lines.append(f"  {clause.clause_id} [{clause.clause_type or '—'}] tokenek: {', '.join(clause.token_ids)}")
        lines.append("")

    if verse.phrases:
        lines.append("SZÓCSOPORTOK (phrase_id | típus | szerep | token_id-k):")
        for phrase in verse.phrases:
            lines.append(f"  {phrase.phrase_id} [{phrase.phrase_type}/{phrase.function or '—'}] tokenek: {', '.join(phrase.token_ids)}")
        lines.append("")

    if verse.semantic_roles:
        lines.append("SZEMANTIKAI SZEREPEK (role_id | kód | állítmány -> argumentum):")
        for role in verse.semantic_roles:
            lines.append(f"  {role.role_id} [{role.role_type}] {role.predicate_id} -> {', '.join(role.token_ids)}")
        lines.append("")

    if verse.detected_patterns:
        lines.append("FELISMERT SZERKEZETEK (pattern_id | típus | tokenek | tény):")
        for pattern in verse.detected_patterns:
            lines.append(f"  {pattern.pattern_id} [{pattern.pattern_type}] tokenek: {', '.join(pattern.token_ids)} — {pattern.explanation_hu}")
        lines.append("")

    lines.append(f"Mondattani lefedettség (grounding_status): {verse.syntax_grounding}")
    return "\n".join(lines)


def token_syntax_coverage(verse: GreekVerseAnalysis) -> set[str]:
    """Every token_id with SOME deterministic syntax fact attached (phrase/
    clause membership, a semantic role, a coreference link) — used to null
    out an over-claiming ``syntax_role_hu`` on an uncovered token."""
    covered: set[str] = set()
    for phrase in verse.phrases:
        covered.update(phrase.token_ids)
    for clause in verse.clauses:
        covered.update(clause.token_ids)
    for role in verse.semantic_roles:
        covered.update(role.token_ids)
        if role.predicate_id:
            covered.add(role.predicate_id)
    for coref in verse.coreference:
        covered.add(coref.source_token_id)
    return covered


def build_construction_evidence_index(verse: GreekVerseAnalysis) -> dict[str, tuple[str, ...]]:
    """Maps every citable evidence id actually printed in the prompt
    payload to the token_ids it covers — mirrors
    ``bible_engine.hebrew_contextual_analysis.build_construction_evidence_index``'s
    contract exactly (§12). No new ids are invented here."""
    index: dict[str, tuple[str, ...]] = {}
    for pattern in verse.detected_patterns:
        index[pattern.pattern_id] = tuple(pattern.token_ids)
    for phrase in verse.phrases:
        index[phrase.phrase_id] = tuple(phrase.token_ids)
    for clause in verse.clauses:
        index[clause.clause_id] = tuple(clause.token_ids)
    for role in verse.semantic_roles:
        role_ids = list(role.token_ids)
        if role.predicate_id and role.predicate_id not in role_ids:
            role_ids.append(role.predicate_id)
        if role_ids:
            index[role.role_id] = tuple(role_ids)
    return index


def resolve_construction_evidence(
    evidence_ids: tuple[str, ...], index: dict[str, tuple[str, ...]]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Returns ``(resolved_evidence_ids, resolved_token_ids, invalid_ids)``
    — mirrors the Hebrew function of the same contract exactly. An empty
    ``resolved_evidence_ids`` means the caller must reject the note
    outright."""
    resolved_evidence: list[str] = []
    resolved_tokens: list[str] = []
    invalid: list[str] = []
    seen_evidence: set[str] = set()
    seen_tokens: set[str] = set()
    for evidence_id in evidence_ids:
        if evidence_id not in index:
            invalid.append(evidence_id)
            continue
        if evidence_id not in seen_evidence:
            seen_evidence.add(evidence_id)
            resolved_evidence.append(evidence_id)
        for token_id in index[evidence_id]:
            if token_id not in seen_tokens:
                seen_tokens.add(token_id)
                resolved_tokens.append(token_id)
    return tuple(resolved_evidence), tuple(resolved_tokens), tuple(invalid)


def build_greek_contextual_analysis_prompt(verse: GreekVerseAnalysis) -> str:
    payload = build_greek_contextual_analysis_payload(verse)
    return f"{GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS}\n\n{payload}"


__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "CONTEXTUAL_ANALYSIS_SCHEMA_VERSION",
    "CONTEXTUAL_ANALYSIS_PROMPT_VERSION",
    "GreekWordNote",
    "GreekConstructionNote",
    "GreekSyntaxSummary",
    "GreekContextualAnalysis",
    "GREEK_CONTEXTUAL_ANALYSIS_RESPONSE_SCHEMA",
    "GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS",
    "build_greek_contextual_analysis_payload",
    "build_greek_contextual_analysis_prompt",
    "token_syntax_coverage",
    "build_construction_evidence_index",
    "resolve_construction_evidence",
]
