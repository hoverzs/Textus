"""Phase 2C §9-§15 — orchestrates one verse-level grounded contextual-
analysis AI call and enforces the deterministic/AI boundary on the way
back. Mirrors ``bible_engine.hebrew_contextual_analysis_service``'s
architecture; the closed-world checks are Greek-specific (§10), and the
lexical field is never even asked of the model (§11 — see the prompt
module's docstring on why ``lexical_basic_meaning_hu`` is server-only for
Greek, a deliberate simplification versus Hebrew's override-and-warn
approach).

Streamlit-free, network-free: the caller supplies ``generate_fn``, so this
module never imports ``app.py`` and is fully unit-testable with a mocked
callable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from bible_engine.greek_analysis_bundle import SYNTAX_GROUNDING_NONE, SYNTAX_GROUNDING_UNAVAILABLE, GreekVerseAnalysis
from bible_engine.greek_contextual_analysis import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONTEXTUAL_ANALYSIS_SCHEMA_VERSION,
    GreekConstructionNote,
    GreekContextualAnalysis,
    GreekSyntaxSummary,
    GreekWordNote,
    build_construction_evidence_index,
    build_greek_contextual_analysis_prompt,
    resolve_construction_evidence,
    token_syntax_coverage,
)

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_INVALID_RESPONSE = "invalid_response"

_VALID_CONFIDENCE = {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW}

_MAX_WORD_NOTES = 15
_MAX_CONSTRUCTION_NOTES = 6
_MAX_STRING_LIST_ITEMS = 5
_MAX_FIELD_CHARS = 320
_MAX_SYNTAX_SUMMARY_CHARS = 700

_RESOLVED_STATUSES = ("EXACT", "COMPOSITE", "VALIDATED_FALLBACK")

# Task §10 — exact forbidden phrasings, checked as a mechanical (not just
# prompt-level) safety net. Kept intentionally narrow and literal: this is
# a backstop against the clearest violations, not an attempt to catch
# every possible paraphrase (that is the prompt's job, tested separately —
# see tests/test_greek_contextual_analysis_grounding.py).
_FORBIDDEN_AORIST_PHRASES = ("egyszerű múlt", "egyszeri cselekvés", "pontszerű cselekvés")
_FORBIDDEN_IMPERFECT_PHRASES = ("folyamatos múlt",)
_FORBIDDEN_MIDDLE_PHRASES = ("visszaható",)
_FORBIDDEN_PERFECT_PHRASES = ("befejezett múlt, amelynek eredménye fennáll",)
_ALL_FORBIDDEN_PHRASES = (
    _FORBIDDEN_AORIST_PHRASES + _FORBIDDEN_IMPERFECT_PHRASES + _FORBIDDEN_MIDDLE_PHRASES + _FORBIDDEN_PERFECT_PHRASES
)

# --- Paraphrase-resistant categorical-overclaim detection ------------------
#
# The literal-phrase screen above catches only exact strings and was found
# (via the live Gemini quality test — see docs/greek_analysis_v2_production_
# validation.md §8) to miss close paraphrases of the same forbidden claim:
# "pontszerű eseményt" instead of the banned "pontszerű cselekvés", and a
# perfect-tense explanation that echoed the banned formula's structure
# almost word for word without matching it literally.
#
# This second layer is deliberately NOT a bigger word blacklist. It is
# CONTEXT-AWARE in two ways, both required by the task:
#   1. Grammatical-category-conditioned: a rule only ever runs against a
#      word note whose TOKEN actually has the matching deterministic
#      morphology (e.g. the aorist rule only screens text describing a
#      token whose own tense IS aorist) — so a word like "egyszeri" used
#      in an unrelated sentence, or describing a token of a different
#      category, is never even evaluated.
#   2. Co-occurrence, not single-keyword: most rules require a "qualifier"
#      word/phrase (the overclaiming adjective) to occur near an "anchor"
#      word/phrase (what is being overclaimed about) WITHIN THE SAME
#      SENTENCE — catching phrasing variants ("pontszerű esemény" as well
#      as "pontszerű cselekvés") without banning either word in isolation.
#   3. Hedge-aware: a sentence that explicitly disclaims the categorical
#      reading (e.g. "...de önmagában nem mondja meg, hogy...") is exempt
#      — this is exactly the cautious wording the prompt asks for and must
#      never be rejected.
_HEDGE_MARKER_RE = re.compile(
    r"nem\s+mondja\s+meg|önmagában\s+nem|nem\s+feltétlenül|nem\s+szükségszerűen|"
    r"nem\s+határozza\s+meg\s+egyértelműen|nem\s+következik\s+egyértelműen|"
    r"kontextustól\s+függ|nem\s+minden\s+esetben|nem\s+kizárólag|nem\s+automatikusan",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+")


def _split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


def _sentence_has_overclaim(
    sentence: str, qualifier_re: str, anchor_re: str | None, extra_hedge_re: str | None = None
) -> bool:
    if _HEDGE_MARKER_RE.search(sentence):
        return False
    if extra_hedge_re and re.search(extra_hedge_re, sentence, re.IGNORECASE):
        return False
    if not re.search(qualifier_re, sentence, re.IGNORECASE):
        return False
    if anchor_re is None:
        return True
    return bool(re.search(anchor_re, sentence, re.IGNORECASE))


def _text_has_overclaim(
    text: str, qualifier_re: str, anchor_re: str | None, extra_hedge_re: str | None = None
) -> bool:
    return any(
        _sentence_has_overclaim(s, qualifier_re, anchor_re, extra_hedge_re) for s in _split_sentences(text)
    )


def _tense_is(token: Any, *values: str) -> bool:
    return token.morphology.tense in values


def _voice_is(token: Any, *values: str) -> bool:
    return token.morphology.voice in values


def _case_is(token: Any, *values: str) -> bool:
    return token.morphology.case in values


def _verb_form_is(token: Any, value: str) -> bool:
    return token.morphology.verb_form == value


def _pos_is(token: Any, value: str) -> bool:
    return token.part_of_speech == value


@dataclass(frozen=True)
class _CategoricalOverclaimRule:
    name: str
    token_matches: Callable[[Any], bool]
    qualifier_re: str
    anchor_re: str | None = None
    # Rule-specific additional hedge pattern, OR'd with the global
    # ``_HEDGE_MARKER_RE`` — e.g. the participle rule treats an explicit
    # "X vagy Y" alternative as the recommended safe phrasing (task's own
    # established example), which is too broad a hedge to apply to every
    # category (most categories' overclaims are not meaningfully softened
    # by a bare "vagy" elsewhere in the sentence).
    extra_hedge_re: str | None = None


# Each rule fires only for a word note whose token's OWN deterministic
# morphology matches ``token_matches`` — see module note above.
_CATEGORICAL_OVERCLAIM_RULES: tuple[_CategoricalOverclaimRule, ...] = (
    _CategoricalOverclaimRule(
        name="aorist",
        # "lezárt"/"befejezett" (closed/completed) conflate the aorist's
        # PERFECTIVE ASPECT (a viewpoint — the event presented as a single
        # whole) with an ontological claim that the event itself was
        # completed/telic — the exact Aktionsart-vs-aspect conflation the
        # rule exists to prevent. Found via a live-test re-check: "Az
        # aoristos itt egy lezárt, múltbeli eseményt rögzít..." slipped
        # past the original qualifier list (which only caught "lezárt
        # egyszeli", not bare "lezárt"). The recommended safe vocabulary
        # ("perfektív aspektus", "...nézőpont", "...szemlélete") never
        # uses "lezárt"/"befejezett" to describe the event, so this does
        # not need a viewpoint-framing exemption.
        token_matches=lambda t: _tense_is(t, "aorisztoszi", "második aorisztoszi"),
        qualifier_re=r"pontszerű|egyszeri|egyszer\s+megtörtént|lezárt\s+egyszeri|"
                     r"megismételhetetlen|once[\s-]for[\s-]all|one[\s-]time|"
                     r"lezárt|befejezett|telikus|visszafordíthatatlan",
        anchor_re=r"cselekvés|esemény|action|event",
    ),
    _CategoricalOverclaimRule(
        name="imperfect",
        token_matches=lambda t: _tense_is(t, "imperfektum"),
        qualifier_re=r"folyamatos\w*|tartós\w*",
        anchor_re=r"múlt\w*",
    ),
    _CategoricalOverclaimRule(
        name="middle",
        token_matches=lambda t: _voice_is(t, "mediális igenem", "mediális deponens"),
        qualifier_re=r"visszaható",
    ),
    _CategoricalOverclaimRule(
        name="passive",
        token_matches=lambda t: _voice_is(
            t, "passzív igenem", "passzív deponens", "mediális vagy passzív igenem", "mediális vagy passzív deponens"
        ),
        qualifier_re=r"szenvedő\s+(?:jelentés|értelem|igealak)|passzív\s+jelentés|valódi\s+szenvedő",
    ),
    _CategoricalOverclaimRule(
        name="perfect",
        token_matches=lambda t: _tense_is(t, "perfectum", "második perfectum"),
        qualifier_re=r"befejezett\s+múlt|eredménye\s+(?:a\s+jelenben\s+is\s+)?fennáll|"
                     r"hatása\s+(?:a\s+jelenben\s+is\s+)?fennáll|eredménye\s+ma\s+is",
    ),
    _CategoricalOverclaimRule(
        name="participle",
        # Broadened beyond the original "X funkciót tölt be" phrasing to
        # also catch the specific temporal-relation SYNONYMS morphology
        # alone can never license: "előidejű"/"utóidejű"/"egyidejű"
        # (anterior/posterior/simultaneous). Found via a live-test
        # re-check: "Az aoristos participium itt egy előidejű cselekvést
        # fejez ki a főige... cselekvéséhez képest" asserted anteriority
        # from tense-form alone — this verse's bundle has no clause/role/
        # construction evidence encoding relative temporal sequence for
        # this participle, so the claim is unsupported. An explicit "X
        # vagy Y" alternative (the established safe pattern for this
        # category) remains allowed via ``extra_hedge_re``.
        token_matches=lambda t: _verb_form_is(t, "participle"),
        qualifier_re=r"okhatározói|ok-okozati|okot\s+fejez\s+ki|feltételes|feltételt\s+fejez\s+ki|"
                     r"megengedő|megengedést\s+fejez\s+ki|időhatározói|eszközhatározói|"
                     r"körülményhatározói|célhatározói|előidejű|utóidejű|egyidejű|megelőző\s+cselekvést",
        anchor_re=r"funkci\w*|fejez(?:i)?\s+ki|tölt(?:i)?\s+be|viszonyt",
        extra_hedge_re=r"\bvagy\b",
    ),
    _CategoricalOverclaimRule(
        name="genitive",
        token_matches=lambda t: _case_is(t, "birtokos eset"),
        qualifier_re=r"birtokos\s+(?:genitivus|jelentés)|birtok\s*viszonyt\s+(?:jelöl|fejez\s+ki)|"
                     r"birtoklást\s+fejez\s+ki",
    ),
    _CategoricalOverclaimRule(
        name="article",
        token_matches=lambda t: _pos_is(t, "határozott névelő"),
        qualifier_re=r"hangsúly\w*|teológiai\s+jelentőség|kiemel\w*\s+(?:jelentőség|szerep)",
    ),
    _CategoricalOverclaimRule(
        name="present_participle_duration",
        # Live-test finding: "ὁ πιστεύων" (present participle) described
        # as "folyamatos, aktív cselekvés" — present-tense morphology
        # alone does not license a claim about the DURATION or repetition
        # of the underlying believing event (continuous/persistent/
        # repeated/lifelong faith); only that article+participle forms a
        # substantival expression ("aki hisz" / "a hívő"). Distinct from
        # the general "participle" rule above (which targets FUNCTION —
        # causal/temporal/concessive relation to the main verb): this one
        # targets DURATIVITY/ASPECT claims about the event itself, and
        # only for PRESENT-tense participles specifically (imperfect-style
        # durative readings are even less licensed for an unaugmented
        # present-stem participle than for a genuinely imperfect verb).
        token_matches=lambda t: _verb_form_is(t, "participle") and _tense_is(t, "jelen idő"),
        qualifier_re=r"folyamatos\w*|állandó\w*|tartós\w*|ismétlődő\w*|kitartó\w*|"
                     r"élethosszig|szüntelen\w*|megszakítás\s+nélküli",
        anchor_re=r"hit\w*|hívő\w*|cselekvés|élet\w*",
    ),
)


# --- Coordinated-predicate clause-count overclaim (task: apply to ALL
# generated fields, not only ConstructionNote) --------------------------
#
# Complements ``_collapse_coordinated_clause_inflation`` below (a
# STRUCTURAL check: two construction_notes each citing one real sibling
# clause as if independent). This is a TEXT-PATTERN check that runs
# whenever the verse has ANY coordinated-sibling-clause situation
# (regardless of which evidence a given field cites, or whether it cites
# any at all) — catching prose anywhere ("A két koordinált tagmondat...")
# that numerically calls the coordination "két tagmondat"/"két
# mellékmondat" (two CLAUSES) instead of "két koordinált állítmány" (two
# coordinated PREDICATES). A short negative lookbehind exempts the
# correctly-hedged negated form ("nem két tagmondatról van szó...").
_CLAUSE_COUNT_OVERCLAIM_RE = re.compile(
    r"(?<!nem\s)két\s+(?:külön\s+)?(?:tagmondat|mellékmondat)|"
    r"(?<!nem\s)kettő\s+(?:tagmondat|mellékmondat)",
    re.IGNORECASE,
)


def _verse_has_coordinated_sibling_clauses(clauses: tuple[Any, ...]) -> bool:
    children_by_parent: dict[str, int] = {}
    for c in clauses:
        if c.parent_clause_id:
            children_by_parent[c.parent_clause_id] = children_by_parent.get(c.parent_clause_id, 0) + 1
    return any(count >= 2 for count in children_by_parent.values())


def _text_wrongly_counts_coordinated_clauses(text: str) -> bool:
    if not text:
        return False
    for sentence in _split_sentences(text):
        if _HEDGE_MARKER_RE.search(sentence):
            continue
        if _CLAUSE_COUNT_OVERCLAIM_RE.search(sentence):
            return True
    return False


# --- Exegetical fact vs. interpretation (task §3) -----------------------
#
# exegetical_notes exist to carry theological/doctrinal readings — that is
# their purpose, and this check never removes the field. It rejects only
# entries that assert a categorical theological claim (identity/nature/
# salvation-condition language) WITHOUT any of the required interpretive-
# framing markers the prompt now asks for, so a claim beyond the linguistic
# evidence is never presented as if it were as certain as a lexical fact.
_INTERPRETIVE_FRAMING_MARKERS_RE = re.compile(
    r"értelmezhető\s+úgy|egyik\s+lehetséges\s+olvasat|lehetséges\s+értelmezés|"
    r"jánosi\s+\w*\s*teológiá|tágabb\s+teológiá|egyes\s+(?:magyarázók|értelmezők)\s+szerint|"
    r"teológiai\s+szempontból\s+értelmezve|hagyományosan\s+úgy\s+értik|"
    r"exegetikai\s+hagyomány",
    re.IGNORECASE,
)

_THEOLOGICAL_CATEGORICAL_CLAIM_RE = re.compile(
    r"isteni\s+(?:mivolt|identitás|természet|eredet|származás)|"
    r"üdvösség\s+(?:egyetlen\s+)?feltétele|az\s+üdvösség\s+(?:egyetlen\s+)?(?:útja|módja)|"
    r"bűnös\s+emberiség|bűnbe\s+esett\s+világ",
    re.IGNORECASE,
)


def _exegetical_note_needs_interpretive_framing(text: str) -> bool:
    if not text:
        return False
    if not _THEOLOGICAL_CATEGORICAL_CLAIM_RE.search(text):
        return False
    return not _INTERPRETIVE_FRAMING_MARKERS_RE.search(text)


def _token_categorical_overclaim(text: str, token: Any) -> str | None:
    """Returns the offending rule's name if `text` (describing `token`)
    makes an unsupported categorical claim tied to that token's own
    deterministic morphology, else None."""
    if not text:
        return None
    for rule in _CATEGORICAL_OVERCLAIM_RULES:
        if rule.token_matches(token) and _text_has_overclaim(
            text, rule.qualifier_re, rule.anchor_re, rule.extra_hedge_re
        ):
            return rule.name
    return None


def _construction_categorical_overclaim(text: str, tokens: tuple[Any, ...]) -> str | None:
    """Same check as ``_token_categorical_overclaim`` but for a construction
    note, which is anchored to a SET of evidence tokens rather than one —
    fires if the text overclaims about ANY category actually present among
    those tokens' own morphology."""
    if not text:
        return None
    applicable = {rule.name: rule for rule in _CATEGORICAL_OVERCLAIM_RULES if any(rule.token_matches(t) for t in tokens)}
    for rule in applicable.values():
        if _text_has_overclaim(text, rule.qualifier_re, rule.anchor_re, rule.extra_hedge_re):
            return rule.name
    return None


@dataclass
class GreekContextualAnalysisResult:
    status: str
    analysis: GreekContextualAnalysis | None = None
    warnings: tuple[str, ...] = ()


def _looks_like_provider_failure(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    return raw.startswith(("⚠️", "⏳"))


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _parse_json_response(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = _FENCE_RE.sub("", text).strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_confidence(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_CONFIDENCE else CONFIDENCE_LOW


def _string_list(value: object, limit: int = _MAX_STRING_LIST_ITEMS) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value[:limit] if str(item or "").strip())


# Generated Hungarian/Greek prose never legitimately contains a literal
# backslash — no markdown/regex/escape syntax is intended in this output.
# A stray backslash occasionally surfaces in raw model text around a
# quoted Greek word or elision mark; this sanitizer strips it before
# rendering. It runs ONLY on AI-generated text fields (routed through
# ``_truncate``, the common funnel every such field passes through) —
# never on deterministic Greek token data (``token.surface``,
# ``verse.greek_text``), which this module never touches.
_STRAY_BACKSLASH_RE = re.compile(r"\\")


def _sanitize_generated_text(text: str) -> str:
    return _STRAY_BACKSLASH_RE.sub("", text or "")


def _truncate(text: str, limit: int, *, warnings: list[str], label: str) -> str:
    text = _sanitize_generated_text(text)
    if len(text) <= limit:
        return text
    warnings.append(f"{label}: szöveg levágva ({len(text)} -> {limit} karakter)")
    return text[:limit].rstrip() + "…"


def _text_uses_forbidden_phrase(text: str) -> str | None:
    lowered = (text or "").lower()
    for phrase in _ALL_FORBIDDEN_PHRASES:
        if phrase in lowered:
            return phrase
    return None


def _build_word_notes(
    raw_notes: object,
    *,
    verse: GreekVerseAnalysis,
    tokens_by_id: dict[str, Any],
    covered_token_ids: set[str],
    has_coordination: bool,
    warnings: list[str],
) -> tuple[GreekWordNote, ...]:
    if not isinstance(raw_notes, list):
        return ()
    notes: list[GreekWordNote] = []
    for raw in raw_notes[:_MAX_WORD_NOTES]:
        if not isinstance(raw, dict):
            continue
        token_id = str(raw.get("token_id") or "").strip()
        token = tokens_by_id.get(token_id)
        if token is None:
            if token_id:
                warnings.append(f"AI ismeretlen token_id-t hivatkozott, eldobva: {token_id}")
            continue

        # §11 lexical authority model — server-supplied, never asked of the
        # model at all (see the prompt module's schema, which has no
        # lexical_basic_meaning_hu field).
        lex = token.lexical_sense
        if lex is not None and lex.review_status == "reviewed":
            lexical_basic_meaning_hu = lex.base_meaning_hu
            lexical_provenance = "reviewed"
        elif lex is not None and lex.base_meaning_hu:
            lexical_basic_meaning_hu = lex.base_meaning_hu
            lexical_provenance = "draft"
        elif lex is not None and lex.note_hu and not lex.base_meaning_hu:
            # TBESG English-fallback case (Phase 2A: lexical_sense with an
            # empty base_meaning_hu and an English note) — grounding
            # exists, but never in Hungarian; no Hungarian canonical value
            # to present.
            lexical_basic_meaning_hu = ""
            lexical_provenance = "english_fallback"
        else:
            lexical_basic_meaning_hu = ""
            lexical_provenance = ""

        syntax_role = str(raw.get("syntax_role_hu") or "").strip()
        if verse.syntax_grounding in (SYNTAX_GROUNDING_NONE, SYNTAX_GROUNDING_UNAVAILABLE) and syntax_role:
            warnings.append(f"{token_id}: mondattani állítás eldobva ({verse.syntax_grounding})")
            syntax_role = ""
        elif token_id not in covered_token_ids and syntax_role:
            warnings.append(f"{token_id}: mondattani állítás eldobva (nincs mondattani adat ehhez a tokenhez)")
            syntax_role = ""
        elif token.alignment_status and not token.alignment_status.startswith(_RESOLVED_STATUSES) and syntax_role:
            warnings.append(f"{token_id}: mondattani állítás eldobva (nem illesztett token — {token.alignment_status})")
            syntax_role = ""
        elif syntax_role:
            syntax_role = _truncate(syntax_role, _MAX_FIELD_CHARS, warnings=warnings, label=f"{token_id}.syntax_role_hu")

        morphological_explanation = str(raw.get("morphological_explanation_hu") or "").strip()
        contextual_meaning = str(raw.get("contextual_meaning_hu") or "").strip()
        forbidden = _text_uses_forbidden_phrase(morphological_explanation) or _text_uses_forbidden_phrase(
            contextual_meaning
        ) or _text_uses_forbidden_phrase(syntax_role)
        overclaim_category = (
            _token_categorical_overclaim(morphological_explanation, token)
            or _token_categorical_overclaim(contextual_meaning, token)
            or _token_categorical_overclaim(syntax_role, token)
        )
        clause_count_overclaim = has_coordination and (
            _text_wrongly_counts_coordinated_clauses(morphological_explanation)
            or _text_wrongly_counts_coordinated_clauses(contextual_meaning)
            or _text_wrongly_counts_coordinated_clauses(syntax_role)
        )
        if forbidden or overclaim_category or clause_count_overclaim:
            if forbidden:
                warnings.append(f"{token_id}: tiltott, túláltalánosító megfogalmazás eldobva ({forbidden!r})")
            elif overclaim_category:
                warnings.append(
                    f"{token_id}: alátámasztatlan, túláltalánosító paraphrase eldobva ({overclaim_category})"
                )
            else:
                warnings.append(
                    f"{token_id}: 'két tagmondat' megfogalmazás eldobva — a determinisztikus adat egy "
                    "tagmondaton belüli koordinált állítmányokat mutat"
                )
            morphological_explanation = ""
            contextual_meaning = ""
            syntax_role = ""

        notes.append(
            GreekWordNote(
                token_id=token_id,
                lexical_basic_meaning_hu=lexical_basic_meaning_hu,
                lexical_provenance=lexical_provenance,
                contextual_meaning_hu=_truncate(
                    contextual_meaning, _MAX_FIELD_CHARS, warnings=warnings, label=f"{token_id}.contextual_meaning_hu"
                ),
                morphological_explanation_hu=_truncate(
                    morphological_explanation, _MAX_FIELD_CHARS, warnings=warnings,
                    label=f"{token_id}.morphological_explanation_hu",
                ),
                syntax_role_hu=syntax_role,
                translation_note_hu=_truncate(
                    str(raw.get("translation_note_hu") or "").strip(), _MAX_FIELD_CHARS,
                    warnings=warnings, label=f"{token_id}.translation_note_hu",
                ),
                confidence=_normalize_confidence(raw.get("confidence")),
            )
        )
    return tuple(notes)


def _collapse_coordinated_clause_inflation(
    notes: list[GreekConstructionNote], clauses: tuple[Any, ...], warnings: list[str]
) -> list[GreekConstructionNote]:
    """Rejects presenting COORDINATED PREDICATES within one deterministic
    clause (e.g. Jn 3:16's single ἵνα-clause internally coordinating
    "μὴ ἀπόληται" and "ἀλλ᾽ ἔχῃ" as sibling constituents under one shared
    parent clause) as if they were two independent subordinate/purpose
    clauses. Each half individually cites REAL clause evidence (so the
    existing evidence-id check alone does not catch this — the problem is
    the model choosing to split ONE governing clause into two notes, not
    inventing evidence), so this is a separate, narrow structural check:
    if 2+ construction_notes each exactly match one SIBLING clause (same
    parent_clause_id, 2+ siblings exist), that pair is dropped entirely —
    fail-closed, since silently keeping one half would itself misrepresent
    the coordination as an independent, self-sufficient clause."""
    clause_by_id = {c.clause_id: c for c in clauses}
    children_by_parent: dict[str, list[str]] = {}
    for c in clauses:
        if c.parent_clause_id:
            children_by_parent.setdefault(c.parent_clause_id, []).append(c.clause_id)

    def _matching_clause_id(note: GreekConstructionNote) -> str | None:
        token_set = frozenset(note.token_ids)
        for cid, c in clause_by_id.items():
            if frozenset(c.token_ids) == token_set:
                return cid
        return None

    notes_by_parent: dict[str, list[int]] = {}
    matched_clause_id: dict[int, str] = {}
    for i, note in enumerate(notes):
        if "clause" not in note.construction_type.lower():
            continue
        cid = _matching_clause_id(note)
        if cid is None:
            continue
        clause = clause_by_id[cid]
        if clause.parent_clause_id and len(children_by_parent.get(clause.parent_clause_id, [])) >= 2:
            notes_by_parent.setdefault(clause.parent_clause_id, []).append(i)
            matched_clause_id[i] = cid

    to_drop: set[int] = set()
    for parent_id, indices in notes_by_parent.items():
        if len(indices) >= 2:
            cited = ", ".join(matched_clause_id[i] for i in indices)
            warnings.append(
                f"konstrukció-megjegyzés(ek) eldobva: koordinált testvér tagmondatok ({cited}) "
                f"külön mellékmondatokként lettek bemutatva egy közös ('{parent_id}') szerkezet helyett"
            )
            to_drop.update(indices)

    return [n for i, n in enumerate(notes) if i not in to_drop]


def _build_construction_notes(
    raw_notes: object,
    *,
    evidence_index: dict[str, tuple[str, ...]],
    tokens_by_id: dict[str, Any],
    clauses: tuple[Any, ...],
    has_coordination: bool,
    warnings: list[str],
) -> tuple[GreekConstructionNote, ...]:
    if not isinstance(raw_notes, list):
        return ()
    notes: list[GreekConstructionNote] = []
    seen_token_sets: set[frozenset[str]] = set()
    for raw in raw_notes[:_MAX_CONSTRUCTION_NOTES]:
        if not isinstance(raw, dict):
            continue
        raw_evidence_ids = tuple(str(e).strip() for e in (raw.get("evidence_ids") or []) if str(e or "").strip())
        resolved_evidence, resolved_tokens, invalid = resolve_construction_evidence(raw_evidence_ids, evidence_index)
        if invalid:
            warnings.append(f"konstrukció-megjegyzés: érvénytelen evidence_id(k) eldobva: {', '.join(invalid)}")
        if not resolved_evidence:
            warnings.append("konstrukció-megjegyzés eldobva: nincs érvényes evidence_id")
            continue

        token_set = frozenset(resolved_tokens)
        if token_set in seen_token_sets:
            continue
        seen_token_sets.add(token_set)

        explanation = str(raw.get("explanation_hu") or "").strip()
        title = str(raw.get("title_hu") or "").strip()
        forbidden = _text_uses_forbidden_phrase(explanation) or _text_uses_forbidden_phrase(title)
        evidence_tokens = tuple(tokens_by_id[tid] for tid in resolved_tokens if tid in tokens_by_id)
        overclaim_category = _construction_categorical_overclaim(
            explanation, evidence_tokens
        ) or _construction_categorical_overclaim(title, evidence_tokens)
        clause_count_overclaim = has_coordination and (
            _text_wrongly_counts_coordinated_clauses(explanation)
            or _text_wrongly_counts_coordinated_clauses(title)
        )
        if forbidden or overclaim_category or clause_count_overclaim:
            if forbidden:
                warnings.append(f"konstrukció-megjegyzés eldobva: tiltott megfogalmazás ({forbidden!r})")
            elif overclaim_category:
                warnings.append(
                    f"konstrukció-megjegyzés eldobva: alátámasztatlan, túláltalánosító paraphrase ({overclaim_category})"
                )
            else:
                warnings.append(
                    "konstrukció-megjegyzés eldobva: 'két tagmondat' megfogalmazás — a determinisztikus adat "
                    "egy tagmondaton belüli koordinált állítmányokat mutat"
                )
            continue

        notes.append(
            GreekConstructionNote(
                token_ids=resolved_tokens,
                construction_type=str(raw.get("construction_type") or "").strip(),
                title_hu=_truncate(title, _MAX_FIELD_CHARS, warnings=warnings, label="construction.title_hu"),
                explanation_hu=_truncate(
                    explanation, _MAX_FIELD_CHARS, warnings=warnings, label="construction.explanation_hu"
                ),
                translation_significance_hu=_truncate(
                    str(raw.get("translation_significance_hu") or "").strip(), _MAX_FIELD_CHARS,
                    warnings=warnings, label="construction.translation_significance_hu",
                ),
                confidence=_normalize_confidence(raw.get("confidence")),
                evidence_ids=resolved_evidence,
            )
        )
    notes = _collapse_coordinated_clause_inflation(notes, clauses, warnings)
    return tuple(notes)


def _build_syntax_summary(
    raw: object, *, grounding_status: str, has_coordination: bool, warnings: list[str]
) -> GreekSyntaxSummary:
    if grounding_status in (SYNTAX_GROUNDING_NONE, SYNTAX_GROUNDING_UNAVAILABLE):
        return GreekSyntaxSummary()
    if not isinstance(raw, dict):
        return GreekSyntaxSummary()
    summary_hu = _truncate(
        str(raw.get("summary_hu") or "").strip(), _MAX_SYNTAX_SUMMARY_CHARS, warnings=warnings, label="syntax_summary"
    )
    if _text_uses_forbidden_phrase(summary_hu):
        warnings.append("syntax_summary eldobva: tiltott megfogalmazás")
        return GreekSyntaxSummary()
    if has_coordination and _text_wrongly_counts_coordinated_clauses(summary_hu):
        warnings.append(
            "syntax_summary eldobva: 'két tagmondat' megfogalmazás — a determinisztikus adat egy "
            "tagmondaton belüli koordinált állítmányokat mutat"
        )
        return GreekSyntaxSummary()
    return GreekSyntaxSummary(
        summary_hu=summary_hu,
        clause_ids=_string_list(raw.get("clause_ids")),
        confidence=_normalize_confidence(raw.get("confidence")),
    )


def validate_and_build_contextual_analysis(
    parsed: dict[str, Any], verse: GreekVerseAnalysis
) -> tuple[GreekContextualAnalysis, tuple[str, ...]]:
    """The ONLY place a raw model response is trusted, and even here only
    after every id has been checked and every semantic-overreach phrase
    screened. ``grounding_status`` is ALWAYS the bundle's own
    ``syntax_grounding`` — never the model's self-report (§15)."""
    warnings: list[str] = []
    tokens_by_id = {t.token_id: t for t in verse.tokens}
    covered = token_syntax_coverage(verse)
    evidence_index = build_construction_evidence_index(verse)
    has_coordination = _verse_has_coordinated_sibling_clauses(verse.clauses)

    word_notes = _build_word_notes(
        parsed.get("word_notes"), verse=verse, tokens_by_id=tokens_by_id, covered_token_ids=covered,
        has_coordination=has_coordination, warnings=warnings,
    )
    construction_notes = _build_construction_notes(
        parsed.get("construction_notes"), evidence_index=evidence_index, tokens_by_id=tokens_by_id,
        clauses=verse.clauses, has_coordination=has_coordination, warnings=warnings,
    )
    syntax_summary = _build_syntax_summary(
        parsed.get("syntax_summary"), grounding_status=verse.syntax_grounding,
        has_coordination=has_coordination, warnings=warnings,
    )

    translation_notes = []
    for t in _string_list(parsed.get("translation_notes")):
        if _text_uses_forbidden_phrase(t):
            continue
        if has_coordination and _text_wrongly_counts_coordinated_clauses(t):
            warnings.append("translation_note eldobva: 'két tagmondat' megfogalmazás")
            continue
        translation_notes.append(_truncate(t, _MAX_FIELD_CHARS, warnings=warnings, label="translation_note"))
    translation_notes = tuple(translation_notes)

    exegetical_notes = []
    for t in _string_list(parsed.get("exegetical_notes")):
        if _text_uses_forbidden_phrase(t):
            continue
        if has_coordination and _text_wrongly_counts_coordinated_clauses(t):
            warnings.append("exegetical_note eldobva: 'két tagmondat' megfogalmazás")
            continue
        if _exegetical_note_needs_interpretive_framing(t):
            warnings.append(
                "exegetical_note eldobva: teológiai állítás explicit értelmezés-jelölés nélkül "
                "(pl. 'értelmezhető úgy…', 'egyik lehetséges olvasat…')"
            )
            continue
        exegetical_notes.append(_truncate(t, _MAX_FIELD_CHARS, warnings=warnings, label="exegetical_note"))
    exegetical_notes = tuple(exegetical_notes)

    model_warnings = []
    for w in _string_list(parsed.get("warnings"), limit=10):
        if has_coordination and _text_wrongly_counts_coordinated_clauses(w):
            warnings.append("modell-figyelmeztetés eldobva: 'két tagmondat' megfogalmazás")
            continue
        model_warnings.append(_truncate(w, _MAX_FIELD_CHARS, warnings=warnings, label="model_warning"))
    model_warnings = tuple(model_warnings)

    analysis = GreekContextualAnalysis(
        schema_version=CONTEXTUAL_ANALYSIS_SCHEMA_VERSION,
        reference=verse.verse_id,
        grounding_status=verse.syntax_grounding,
        word_notes=word_notes,
        construction_notes=construction_notes,
        syntax_summary=syntax_summary,
        translation_notes=translation_notes,
        exegetical_notes=exegetical_notes,
        warnings=model_warnings,
    )
    return analysis, tuple(warnings)


def request_greek_contextual_analysis(
    verse: GreekVerseAnalysis,
    *,
    generate_fn: Callable[..., str],
    generate_kwargs: dict[str, Any] | None = None,
) -> GreekContextualAnalysisResult:
    """Orchestrates exactly ONE model call for this verse — the caller
    (``bible_engine.greek_contextual_analysis_cache``) is responsible for
    never calling this twice for the same verse within one cache
    lifetime.

    2026-09 audit fix: if the deterministic bundle's own syntax fetch hit a
    transient backend error (``verse.syntax_grounding ==
    SYNTAX_GROUNDING_UNAVAILABLE`` — see ``greek_analysis_repository.
    _attach_verse``), this returns ``STATUS_UNAVAILABLE`` immediately
    without calling the model: an AI call built on a known-degraded input is
    wasted cost, and the caller's cache only stores ``STATUS_OK`` results,
    so this guarantees the degraded case is never cached — the next request
    for the same verse re-attaches syntax from the repository from scratch,
    picking up a recovered backend automatically."""
    if verse.syntax_grounding == SYNTAX_GROUNDING_UNAVAILABLE:
        return GreekContextualAnalysisResult(status=STATUS_UNAVAILABLE)
    prompt = build_greek_contextual_analysis_prompt(verse)
    try:
        raw = generate_fn(prompt, **(generate_kwargs or {}))
    except Exception as exc:  # noqa: BLE001 — any provider failure must degrade gracefully, never raise past this point
        return GreekContextualAnalysisResult(status=STATUS_UNAVAILABLE, warnings=(str(exc),))

    if _looks_like_provider_failure(raw):
        return GreekContextualAnalysisResult(status=STATUS_UNAVAILABLE)

    parsed = _parse_json_response(raw)
    if parsed is None:
        return GreekContextualAnalysisResult(status=STATUS_INVALID_RESPONSE)

    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    return GreekContextualAnalysisResult(status=STATUS_OK, analysis=analysis, warnings=warnings)


__all__ = [
    "STATUS_OK",
    "STATUS_UNAVAILABLE",
    "STATUS_INVALID_RESPONSE",
    "GreekContextualAnalysisResult",
    "validate_and_build_contextual_analysis",
    "request_greek_contextual_analysis",
]
