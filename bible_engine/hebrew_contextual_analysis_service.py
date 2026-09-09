"""Phase 2E — orchestrates one verse-level grounded contextual-analysis AI
call and enforces the deterministic/AI boundary on the way back.

This is the ONLY place a raw model response is trusted, and even here it is
trusted only after every id reference has been checked against the bundle
that was actually sent, and after ``grounding_status``/syntax claims have
been forced back into agreement with the bundle's own
``VerseAnalysis.syntax_grounding``. See
``bible_engine.hebrew_contextual_analysis`` for the contract this validates
against and the reasoning behind each rule.

Streamlit-free, network-free: the caller supplies ``generate_fn`` (same
dependency-injection convention ``bible_engine.original_language_analysis``
already uses for ``generate_text_fn``), so this module never imports
``app.py`` and is fully unit-testable with a mocked callable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from bible_engine.hebrew_analysis_bundle import VerseAnalysis
from bible_engine.hebrew_analysis_repository import SYNTAX_GROUNDING_NONE
from bible_engine.hebrew_contextual_analysis import (
    CONFIDENCE_LOW,
    CONTEXTUAL_ANALYSIS_SCHEMA_VERSION,
    ConstructionNote,
    HebrewContextualAnalysis,
    SyntaxSummary,
    WordNote,
    _VALID_CONFIDENCE,
    _token_syntax_coverage,
    build_construction_evidence_index,
    build_hebrew_contextual_analysis_prompt,
    resolve_construction_evidence,
)

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_INVALID_RESPONSE = "invalid_response"

# Phase 2E hardening pass (prompt version 2e.1.0) — differentiated, tighter
# ceilings than the original single 10-item cap. word_notes may reasonably
# run a bit longer than construction/translation/exegetical notes (a rich
# verse can have many tokens worth a short remark), but every OTHER list
# stays intentionally small: the brief's own quality goal is "shorter, more
# evidence-directed, less repetitive," not "cap raised everywhere."
_MAX_WORD_NOTES = 15
_MAX_CONSTRUCTION_NOTES = 6
_MAX_STRING_LIST_ITEMS = 5

# Soft per-field length backstops (characters, not tokens — a rough proxy).
# These are NOT the primary fix (the primary fix is prompt-level brevity
# instructions + making word_notes genuinely selective) — they are a
# mechanical safety net against a single runaway field, applied by
# truncation (with a recorded warning), never by rejecting the whole note.
_MAX_WORD_NOTE_FIELD_CHARS = 320
_MAX_CONSTRUCTION_FIELD_CHARS = 320
_MAX_SYNTAX_SUMMARY_CHARS = 700


@dataclass
class HebrewContextualAnalysisResult:
    status: str
    analysis: HebrewContextualAnalysis | None = None
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
    if not isinstance(parsed, dict):
        return None
    return parsed


def _normalize_confidence(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in _VALID_CONFIDENCE else CONFIDENCE_LOW


def _string_list(value: object, limit: int = _MAX_STRING_LIST_ITEMS) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out = [str(item).strip() for item in value if str(item or "").strip()]
    return tuple(out[:limit])


def _truncate(text: str, limit: int, *, warnings: list[str] | None = None, label: str = "") -> str:
    """Soft mechanical backstop against a single runaway field — cuts at a
    word boundary near ``limit`` chars and records a warning (never raises,
    never drops the whole note). Not the primary brevity mechanism — see
    the module docstring and HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS'
    TÖMÖRSÉG section, which is where actual conciseness is expected to
    come from."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_space = cut.rfind(" ")
    if last_space > limit * 0.6:
        cut = cut[:last_space]
    if warnings is not None:
        warnings.append(f"Túl hosszú mező rövidítve ({label}, {len(text)} -> {len(cut)} karakter)")
    return cut.rstrip(" ,.;:") + "…"


def _build_word_notes(
    raw_notes: object,
    *,
    valid_token_ids: set[str],
    covered_token_ids: set[str],
    grounding_status: str,
    warnings: list[str],
) -> tuple[WordNote, ...]:
    if not isinstance(raw_notes, list):
        return ()
    notes: list[WordNote] = []
    for raw in raw_notes[:_MAX_WORD_NOTES]:
        if not isinstance(raw, dict):
            continue
        token_id = str(raw.get("token_id") or "").strip()
        if token_id not in valid_token_ids:
            if token_id:
                warnings.append(f"AI ismeretlen token_id-t hivatkozott, eldobva: {token_id}")
            continue

        syntax_explanation = str(raw.get("syntax_explanation_hu") or "").strip()
        if grounding_status == SYNTAX_GROUNDING_NONE and syntax_explanation:
            warnings.append(f"{token_id}: mondattani állítás eldobva (NO_GROUNDED_SYNTAX)")
            syntax_explanation = ""
        elif token_id not in covered_token_ids and syntax_explanation:
            warnings.append(f"{token_id}: mondattani állítás eldobva (nincs mondattani adat ehhez a tokenhez)")
            syntax_explanation = ""
        elif syntax_explanation:
            syntax_explanation = _truncate(
                syntax_explanation, _MAX_WORD_NOTE_FIELD_CHARS, warnings=warnings,
                label=f"{token_id}.syntax_explanation_hu",
            )

        notes.append(
            WordNote(
                token_id=token_id,
                lexical_basic_meaning_hu=_truncate(
                    str(raw.get("lexical_basic_meaning_hu") or "").strip(), _MAX_WORD_NOTE_FIELD_CHARS,
                    warnings=warnings, label=f"{token_id}.lexical_basic_meaning_hu",
                ),
                contextual_meaning_hu=_truncate(
                    str(raw.get("contextual_meaning_hu") or "").strip(), _MAX_WORD_NOTE_FIELD_CHARS,
                    warnings=warnings, label=f"{token_id}.contextual_meaning_hu",
                ),
                grammar_explanation_hu=_truncate(
                    str(raw.get("grammar_explanation_hu") or "").strip(), _MAX_WORD_NOTE_FIELD_CHARS,
                    warnings=warnings, label=f"{token_id}.grammar_explanation_hu",
                ),
                syntax_explanation_hu=syntax_explanation,
                translation_note_hu=_truncate(
                    str(raw.get("translation_note_hu") or "").strip(), _MAX_WORD_NOTE_FIELD_CHARS,
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
) -> tuple[ConstructionNote, ...]:
    """Every construction note must cite ``evidence_ids`` that actually
    exist in ``evidence_index`` (Phase 2E hardening pass, prompt version
    2e.1.0 — see ``build_construction_evidence_index`` /
    ``resolve_construction_evidence`` in ``hebrew_contextual_analysis``).
    This is the mandatory structural enforcement the Phase 2E architecture
    requires: the AI may EXPLAIN a supplied construction, but must never
    independently ASSERT that one exists — it can only point at evidence
    ids already printed in the prompt, never invent a token grouping of
    its own. A note with zero resolvable evidence ids is dropped
    unconditionally, regardless of how plausible its wording reads;
    ``token_ids`` on the returned dataclass is always SERVER-COMPUTED from
    the resolved evidence, never taken from the model."""
    if not isinstance(raw_notes, list):
        return ()
    notes: list[ConstructionNote] = []
    for raw in raw_notes[:_MAX_CONSTRUCTION_NOTES]:
        if not isinstance(raw, dict):
            continue
        raw_evidence_ids = raw.get("evidence_ids")
        cited = tuple(str(e).strip() for e in raw_evidence_ids) if isinstance(raw_evidence_ids, list) else ()

        title = str(raw.get("title_hu") or "").strip()
        explanation = str(raw.get("explanation_hu") or "").strip()
        construction_type = str(raw.get("construction_type") or "").strip()
        if not title or not explanation:
            continue

        resolved_evidence, resolved_tokens, invalid_ids = resolve_construction_evidence(cited, evidence_index)
        if invalid_ids:
            warnings.append(f"Ismeretlen evidence_id(k) eldobva ({construction_type}): {invalid_ids}")
        if not resolved_evidence:
            warnings.append(
                f"Szerkezet-megfigyelés eldobva (nincs érvényes evidence_id — a modell nem hivatkozott "
                f"valós determinisztikus adatra): {construction_type} {cited}"
            )
            continue

        notes.append(
            ConstructionNote(
                token_ids=resolved_tokens,
                construction_type=construction_type,
                title_hu=_truncate(title, _MAX_CONSTRUCTION_FIELD_CHARS, warnings=warnings, label="title_hu"),
                explanation_hu=_truncate(
                    explanation, _MAX_CONSTRUCTION_FIELD_CHARS, warnings=warnings, label="explanation_hu"
                ),
                translation_significance_hu=_truncate(
                    str(raw.get("translation_significance_hu") or "").strip(), _MAX_CONSTRUCTION_FIELD_CHARS,
                    warnings=warnings, label="translation_significance_hu",
                ),
                confidence=_normalize_confidence(raw.get("confidence")),
                evidence_ids=resolved_evidence,
            )
        )
    return tuple(notes)


def _build_syntax_summary(
    raw_summary: object,
    *,
    valid_clause_ids: set[str],
    grounding_status: str,
    warnings: list[str],
) -> SyntaxSummary:
    if grounding_status == SYNTAX_GROUNDING_NONE:
        if isinstance(raw_summary, dict) and (
            str(raw_summary.get("summary_hu") or "").strip() or raw_summary.get("clause_ids")
        ):
            warnings.append("Mondatelemzés eldobva (NO_GROUNDED_SYNTAX — nincs mondattani adat ehhez a vershez)")
        return SyntaxSummary()

    if not isinstance(raw_summary, dict):
        return SyntaxSummary()

    raw_clause_ids = raw_summary.get("clause_ids")
    clause_ids = tuple(str(c).strip() for c in raw_clause_ids) if isinstance(raw_clause_ids, list) else ()
    resolved = tuple(c for c in clause_ids if c in valid_clause_ids)
    if len(resolved) != len(clause_ids):
        warnings.append("Mondatelemzésből ismeretlen tagmondat-azonosító(k) eldobva")

    return SyntaxSummary(
        summary_hu=_truncate(
            str(raw_summary.get("summary_hu") or "").strip(), _MAX_SYNTAX_SUMMARY_CHARS,
            warnings=warnings, label="syntax_summary.summary_hu",
        ),
        clause_ids=resolved,
        confidence=_normalize_confidence(raw_summary.get("confidence")),
    )


def validate_and_build_contextual_analysis(
    parsed: dict[str, Any], verse: VerseAnalysis
) -> tuple[HebrewContextualAnalysis, tuple[str, ...]]:
    """Turn a raw parsed-JSON model response into a validated
    ``HebrewContextualAnalysis``, enforcing every structural rule in the
    module docstring. Never raises on malformed sub-fields — a missing or
    wrong-shaped field is treated as "the model supplied nothing here",
    never as a fatal error (fail toward less information, not a crash)."""
    warnings: list[str] = []
    valid_token_ids = {token.token_id for token in verse.tokens}
    valid_clause_ids = {clause.clause_id for clause in verse.clauses}
    covered_token_ids = _token_syntax_coverage(verse)
    evidence_index = build_construction_evidence_index(verse)
    grounding_status = verse.syntax_grounding  # bundle-authoritative — never the model's self-report

    word_notes = _build_word_notes(
        parsed.get("word_notes"),
        valid_token_ids=valid_token_ids,
        covered_token_ids=covered_token_ids,
        grounding_status=grounding_status,
        warnings=warnings,
    )
    construction_notes = _build_construction_notes(
        parsed.get("construction_notes"),
        evidence_index=evidence_index,
        warnings=warnings,
    )
    syntax_summary = _build_syntax_summary(
        parsed.get("syntax_summary"),
        valid_clause_ids=valid_clause_ids,
        grounding_status=grounding_status,
        warnings=warnings,
    )
    translation_notes = _string_list(parsed.get("translation_notes"))
    exegetical_notes = _string_list(parsed.get("exegetical_notes"))

    analysis = HebrewContextualAnalysis(
        schema_version=CONTEXTUAL_ANALYSIS_SCHEMA_VERSION,
        reference=verse.verse_id,
        grounding_status=grounding_status,
        word_notes=word_notes,
        construction_notes=construction_notes,
        syntax_summary=syntax_summary,
        translation_notes=translation_notes,
        exegetical_notes=exegetical_notes,
        warnings=tuple(warnings),
    )
    return analysis, tuple(warnings)


def request_hebrew_contextual_analysis(
    verse: VerseAnalysis,
    *,
    generate_fn: Callable[..., str],
    generate_kwargs: dict[str, Any] | None = None,
) -> HebrewContextualAnalysisResult:
    """Build the grounded prompt for ``verse``, call ``generate_fn`` once,
    and return a validated result. Never makes more than one call. Never
    raises — any failure (network, malformed JSON, provider error text)
    degrades to ``STATUS_UNAVAILABLE``/``STATUS_INVALID_RESPONSE`` with no
    fabricated content, per the Phase 2E fallback contract."""
    prompt = build_hebrew_contextual_analysis_prompt(verse)
    call_kwargs = dict(generate_kwargs or {})

    try:
        raw = generate_fn(prompt, **call_kwargs)
    except TypeError:
        try:
            raw = generate_fn(prompt)
        except Exception:  # noqa: BLE001 — fail-closed, see module docstring
            return HebrewContextualAnalysisResult(status=STATUS_UNAVAILABLE)
    except Exception:  # noqa: BLE001 — fail-closed, see module docstring
        return HebrewContextualAnalysisResult(status=STATUS_UNAVAILABLE)

    if _looks_like_provider_failure(str(raw or "")):
        return HebrewContextualAnalysisResult(status=STATUS_UNAVAILABLE)

    parsed = _parse_json_response(str(raw))
    if parsed is None:
        return HebrewContextualAnalysisResult(status=STATUS_INVALID_RESPONSE)

    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    return HebrewContextualAnalysisResult(status=STATUS_OK, analysis=analysis, warnings=warnings)


__all__ = [
    "STATUS_INVALID_RESPONSE",
    "STATUS_OK",
    "STATUS_UNAVAILABLE",
    "HebrewContextualAnalysisResult",
    "request_hebrew_contextual_analysis",
    "validate_and_build_contextual_analysis",
]
