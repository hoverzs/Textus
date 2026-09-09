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
    build_hebrew_contextual_analysis_prompt,
    construction_note_evidence,
)

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_INVALID_RESPONSE = "invalid_response"

_MAX_LIST_ITEMS = 10


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


def _string_list(value: object, limit: int = _MAX_LIST_ITEMS) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out = [str(item).strip() for item in value if str(item or "").strip()]
    return tuple(out[:limit])


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
    for raw in raw_notes[:_MAX_LIST_ITEMS]:
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

        notes.append(
            WordNote(
                token_id=token_id,
                lexical_basic_meaning_hu=str(raw.get("lexical_basic_meaning_hu") or "").strip(),
                contextual_meaning_hu=str(raw.get("contextual_meaning_hu") or "").strip(),
                grammar_explanation_hu=str(raw.get("grammar_explanation_hu") or "").strip(),
                syntax_explanation_hu=syntax_explanation,
                translation_note_hu=str(raw.get("translation_note_hu") or "").strip(),
                confidence=_normalize_confidence(raw.get("confidence")),
            )
        )
    return tuple(notes)


def _build_construction_notes(
    raw_notes: object,
    *,
    valid_token_ids: set[str],
    verse: VerseAnalysis,
    warnings: list[str],
) -> tuple[ConstructionNote, ...]:
    """Every construction note must be grounded in real deterministic
    structure — a Phase 2C ``DetectedPattern`` or an existing MACULA
    phrase/clause/relation/role/participant grouping — checked via
    ``construction_note_evidence()``. This is the mandatory structural
    enforcement the Phase 2E architecture requires: the AI may EXPLAIN a
    supplied construction, but must never independently ASSERT that one
    exists. A note failing this check is dropped unconditionally,
    regardless of syntax-grounding status or how plausible its wording —
    grounding for a construction note is never inferred from
    ``syntax_grounding`` alone (a NO_GROUNDED_SYNTAX verse can still ground
    a morphology-only detected pattern, e.g. double negation or Ketiv/Qere;
    a FULLY_GROUNDED_SYNTAX verse still rejects a note whose tokens don't
    actually co-occur in any real structure)."""
    if not isinstance(raw_notes, list):
        return ()
    notes: list[ConstructionNote] = []
    for raw in raw_notes[:_MAX_LIST_ITEMS]:
        if not isinstance(raw, dict):
            continue
        raw_token_ids = raw.get("token_ids")
        token_ids = tuple(str(t).strip() for t in raw_token_ids) if isinstance(raw_token_ids, list) else ()
        if not token_ids or any(t not in valid_token_ids for t in token_ids):
            warnings.append(f"Szerkezet-megfigyelés eldobva (ismeretlen token_id): {token_ids}")
            continue

        title = str(raw.get("title_hu") or "").strip()
        explanation = str(raw.get("explanation_hu") or "").strip()
        construction_type = str(raw.get("construction_type") or "").strip()
        if not title or not explanation:
            continue

        grounded, evidence_pattern_ids = construction_note_evidence(token_ids, verse)
        if not grounded:
            warnings.append(
                f"Szerkezet-megfigyelés eldobva (nincs determinisztikus alátámasztás — se felismert "
                f"minta, se frázis/tagmondat/mondattani viszony/szerep nem fedi le ezeket a tokeneket): "
                f"{construction_type} {token_ids}"
            )
            continue

        notes.append(
            ConstructionNote(
                token_ids=token_ids,
                construction_type=construction_type,
                title_hu=title,
                explanation_hu=explanation,
                translation_significance_hu=str(raw.get("translation_significance_hu") or "").strip(),
                confidence=_normalize_confidence(raw.get("confidence")),
                evidence_pattern_ids=evidence_pattern_ids,
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
        summary_hu=str(raw_summary.get("summary_hu") or "").strip(),
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
        valid_token_ids=valid_token_ids,
        verse=verse,
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
