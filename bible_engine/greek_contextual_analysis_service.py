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

from bible_engine.greek_analysis_bundle import SYNTAX_GROUNDING_NONE, GreekVerseAnalysis
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


def _truncate(text: str, limit: int, *, warnings: list[str], label: str) -> str:
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
        if verse.syntax_grounding == SYNTAX_GROUNDING_NONE and syntax_role:
            warnings.append(f"{token_id}: mondattani állítás eldobva (NO_GROUNDED_SYNTAX)")
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
        if forbidden:
            warnings.append(f"{token_id}: tiltott, túláltalánosító megfogalmazás eldobva ({forbidden!r})")
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


def _build_construction_notes(
    raw_notes: object,
    *,
    evidence_index: dict[str, tuple[str, ...]],
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
        if forbidden:
            warnings.append(f"konstrukció-megjegyzés eldobva: tiltott megfogalmazás ({forbidden!r})")
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
    return tuple(notes)


def _build_syntax_summary(raw: object, *, grounding_status: str, warnings: list[str]) -> GreekSyntaxSummary:
    if grounding_status == SYNTAX_GROUNDING_NONE:
        return GreekSyntaxSummary()
    if not isinstance(raw, dict):
        return GreekSyntaxSummary()
    summary_hu = _truncate(
        str(raw.get("summary_hu") or "").strip(), _MAX_SYNTAX_SUMMARY_CHARS, warnings=warnings, label="syntax_summary"
    )
    if _text_uses_forbidden_phrase(summary_hu):
        warnings.append("syntax_summary eldobva: tiltott megfogalmazás")
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

    word_notes = _build_word_notes(
        parsed.get("word_notes"), verse=verse, tokens_by_id=tokens_by_id, covered_token_ids=covered,
        warnings=warnings,
    )
    construction_notes = _build_construction_notes(
        parsed.get("construction_notes"), evidence_index=evidence_index, warnings=warnings
    )
    syntax_summary = _build_syntax_summary(
        parsed.get("syntax_summary"), grounding_status=verse.syntax_grounding, warnings=warnings
    )

    translation_notes = tuple(
        _truncate(t, _MAX_FIELD_CHARS, warnings=warnings, label="translation_note")
        for t in _string_list(parsed.get("translation_notes"))
        if not _text_uses_forbidden_phrase(t)
    )
    exegetical_notes = tuple(
        _truncate(t, _MAX_FIELD_CHARS, warnings=warnings, label="exegetical_note")
        for t in _string_list(parsed.get("exegetical_notes"))
        if not _text_uses_forbidden_phrase(t)
    )
    model_warnings = _string_list(parsed.get("warnings"), limit=10)

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
    lifetime."""
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
