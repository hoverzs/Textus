"""Narrow service API over the derived, cache-only Hungarian Commentary
translation layer -- ``get_translation`` (cache-only) and
``get_or_create_translation`` (cache-or-generate), sitting on top of
``textus_kb.commentary_translation_store`` (SQLite cache) and
``textus_kb.commentary_translation_policy`` (prompt + glossary).

No Streamlit dependency here, mirroring ``commentary_compare.py``'s own
split between orchestration and UI -- the UI layer (the "Eredeti" /
"Magyar fordítás" toggle in ``commentary_ui.py``) is a thin caller on
top of this module, and receives ``generate_fn`` from ``app.py`` exactly
like the compare feature does.

Fail-closed throughout: any failure here (missing/corrupt translation
DB, missing/failing provider, missing section) degrades to "no Hungarian
translation available right now" -- it NEVER touches or blocks the
original, read-only Commentary browsing
(``textus_kb.repositories.commentary_repository``, ``commentary.sqlite3``).
A translation is always DERIVED content: its provenance is traceable
through ``section_id`` back to the exact original section (work/edition/
contributors/upstream source), the same metadata the retrieval-only
cards already display -- never treated as, or displayed as, an original
quotation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from textus_kb.commentary_translation_policy import (
    TRANSLATION_POLICY_VERSION,
    build_translation_prompt,
)
from textus_kb.commentary_translation_store import (
    TranslationRecord,
    compute_source_fingerprint,
    get_translation as _store_get_translation,
    save_translation as _store_save_translation,
)
from textus_kb.repositories.commentary_repository import CommentaryRepository
from llm_text_utils import is_provider_failure_text

DEFAULT_LANGUAGE = "hu"
TRANSLATION_TAB_LABEL = "Kommentár fordítás (HU)"

# Safety margin under the tab's own output-token ceiling (app.py's
# DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB["Kommentár fordítás (HU)"] = 16000) --
# a real production section (Matthew Henry / Rom.8.1-9, a single 14281-
# char chunk) truncated mid-sentence at that ceiling. Rather than raising
# the ceiling further, a section this size is split into several smaller
# translation batches (ld. split_section_for_translation) so no single
# provider call is ever asked to produce anywhere near the full budget.
# Not yet tuned from real usageMetadata per-batch measurements -- a
# conservative first value, safe to revisit once real batch-level
# thoughts+candidates counts are observed.
DEFAULT_TRANSLATION_BATCH_MAX_CHARS = 3000


@dataclass(frozen=True)
class TranslationOutcome:
    # "cached" | "missing" | "generated" | "unavailable"
    # | "provider_error" | "no_generate_fn"
    status: str
    message: str = ""
    text: str = ""
    provider_model: str = ""
    created_at: str = ""


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos is_provider_failure_text (llm_text_utils.py; azonosság: tests/test_llm_text_utils.py).
_looks_like_provider_failure = is_provider_failure_text


# --- Long-section translation batching (task: 2026-09-03 hardening) -------
#
# A canonical section's chunks (the SAME chunks CommentaryRepository.
# section_detail already returns, ld. textus_kb.repositories.commentary_
# repository) are the PRIMARY batching unit -- most sections have several
# chunks or one chunk well within budget, so this changes nothing for the
# common case (one batch == today's single-call behavior, byte-identical
# prompt). Only a single chunk that is ITSELF too large to translate
# safely in one call gets split further, at paragraph boundaries first,
# falling back to sentence- then word-boundaries only for an oversized
# single paragraph -- never a new artificial segmentation system, and
# never a mid-word cut.


def _split_oversized_unit(text: str, max_chars: int) -> list[str]:
    """Last-resort split of a single unit (paragraph, or a chunk with no
    paragraph breaks) that alone exceeds ``max_chars`` -- prefers a
    sentence boundary, falls back to a word boundary, never mid-word."""
    remaining = text.strip()
    pieces: list[str] = []
    while len(remaining) > max_chars:
        cut = remaining.rfind(". ", 0, max_chars)
        if cut != -1:
            cut += 1  # keep the period with the piece that ends the sentence
        else:
            cut = remaining.rfind(" ", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _split_chunk_into_units(chunk_text: str, max_chars: int) -> list[str]:
    """One chunk -> one or more ordered translation units, each safely
    under ``max_chars``. Splits at the chunk's own paragraph breaks
    first (a real structural boundary already present in the source
    text); only a single oversized paragraph is split further."""
    if len(chunk_text) <= max_chars:
        return [chunk_text] if chunk_text.strip() else []
    paragraphs = [p for p in chunk_text.split("\n\n") if p.strip()]
    if not paragraphs:
        return _split_oversized_unit(chunk_text, max_chars)
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
        else:
            units.extend(_split_oversized_unit(paragraph, max_chars))
    return units


def _pack_units_into_batches(units: Sequence[str], max_chars: int) -> list[str]:
    """Greedily combines consecutive small units into as few translation
    batches as possible, each still under ``max_chars`` and in original
    order -- so a section whose chunks collectively still fit in one
    batch produces exactly ONE batch (unchanged, single-call behavior)."""
    batches: list[str] = []
    current: list[str] = []
    current_len = 0
    for unit in units:
        added_len = len(unit) + (2 if current else 0)  # "\n\n" join separator
        if current and current_len + added_len > max_chars:
            batches.append("\n\n".join(current))
            current = [unit]
            current_len = len(unit)
        else:
            current.append(unit)
            current_len += added_len
    if current:
        batches.append("\n\n".join(current))
    return batches


def split_section_for_translation(
    chunk_texts: Sequence[str],
    *,
    max_chars: int = DEFAULT_TRANSLATION_BATCH_MAX_CHARS,
) -> list[str]:
    """Deterministically splits a section's FULL ordered chunk texts into
    one or more translation batches, each safely under ``max_chars``,
    preserving original order throughout -- never drops content, never
    reorders. Existing chunk boundaries are the primary unit; only a
    single chunk that alone exceeds ``max_chars`` is split further (at
    paragraph, then sentence/word boundaries -- never mid-word). Pure and
    deterministic: same input always yields the same batches, directly
    testable without any provider call."""
    units: list[str] = []
    for chunk_text in chunk_texts:
        if chunk_text and chunk_text.strip():
            units.extend(_split_chunk_into_units(chunk_text, max_chars))
    return _pack_units_into_batches(units, max_chars)


_LEADING_HEADING_MAX_CONTENT_CHARS = 30
_LEADING_HEADING_MAX_LETTER_CHARS = 10


def _fold_to_ascii_letters(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z]", "", without_marks)


def _strip_redundant_passage_heading(text: str, canonical_passages: Sequence[str]) -> str:
    """Some provider responses prepend a short markdown heading that just
    echoes the passage reference (e.g. "## Róm 8:1") despite the
    translation prompt explicitly forbidding any added heading/intro --
    redundant with the reader's own passage heading rendered right above
    it (ld. commentary_ui._render_reader_section), and would otherwise
    visually duplicate it. Strips ONLY a genuine leading passage-echo
    heading: short, carrying digits that numerically match this
    section's own canonical passage, with no more than a short
    abbreviation-length label. A real structural/content heading from
    the source commentary (e.g. an outline point like "## I.", which
    carries no digits at all) is never touched -- and this only ever
    looks at each batch's own FIRST line, never mid-text. Generic: keyed
    off ``canonical_passages`` (whatever section is actually being
    translated), never a specific hardcoded passage string."""
    stripped = text.lstrip()
    first_line, sep, rest = stripped.partition("\n")
    if not sep:
        return text
    match = re.match(r"^#{1,6}\s+(.+?)\s*$", first_line)
    if not match:
        return text
    content = match.group(1)
    if len(content) > _LEADING_HEADING_MAX_CONTENT_CHARS:
        return text
    digits = "".join(re.findall(r"\d+", content))
    if not digits:
        return text
    letters = _fold_to_ascii_letters(content)
    if len(letters) > _LEADING_HEADING_MAX_LETTER_CHARS:
        return text
    for passage in canonical_passages:
        passage_digits = "".join(re.findall(r"\d+", passage))
        if not passage_digits:
            continue
        if digits == passage_digits or passage_digits.endswith(digits):
            return rest.lstrip("\n")
    return text


# --- Invalid-output rejection (task: 2026-09-03 placeholder hardening) ----
#
# A real Calvin / Rom.8.6 batch response was found cached as
# "## Kommentár-szakasz fordítása (John Calvin: Commentary on Romans, Róm
# 8:6)\n\n6. A test gondolkodása, ...<full genuine translation>" -- in THAT
# specific case the heading was followed by a complete, valid translation
# (harmless once read in full; the earlier live smoke observation that
# looked like a bare placeholder was an artifact of the reader's own
# progressive-disclosure preview cutting right after the heading's
# paragraph break, not a real service-layer failure). But the same
# self-referential "meta-description of the task" heading COULD, in a less
# fortunate call, appear with nothing real after it -- a genuine placeholder
# that `_looks_like_provider_failure` would NOT catch (non-empty, no
# "⚠️"/"⏳" prefix). The checks below guard against exactly that failure
# class: never a semantic/LLM-based quality judgment, only narrow,
# deterministic structural checks.

# A small, curated set of KNOWN self-referential "this is a translation of
# section X" meta-descriptions observed (or directly analogous to what was
# observed) in real provider output -- matched case-insensitively, and only
# ever treated as disqualifying when the ENTIRE response is short (ld.
# _looks_like_placeholder_translation), so a long, genuine translation that
# happens to legitimately use similar wording is never rejected.
_KNOWN_PLACEHOLDER_MARKERS = (
    "kommentár-szakasz fordítása",
    "ez a szakasz fordítása",
    "translation of this section",
    "translation of the commentary section",
)

# Above this length a response is never treated as a "known placeholder"
# purely by marker wording (only by the heading-with-nothing-after-it
# check below it) -- the real Calvin/Rom.8.6 case (3185 chars, genuine
# content) must never be rejected just because it happens to mention this
# phrasing in its own opening heading.
_PLACEHOLDER_MARKER_MAX_RESPONSE_CHARS = 400

_LEADING_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+.+$")


def _looks_like_placeholder_translation(text: str) -> bool:
    """Deterministic, narrow rejection of a batch response that is clearly
    not a real translation result -- never a semantic quality score, just
    two structural checks:

    1. The response is JUST a markdown heading line with nothing (or only
       blank lines) after it. A title on its own is never a translation,
       regardless of what it says -- this deliberately does NOT judge how
       much content follows a heading (any real, non-blank content after
       one is accepted as-is, exactly like a response with no heading at
       all), only whether there is a real body at all.
    2. The ENTIRE (short) response matches a KNOWN self-referential
       "meta-description of the task" placeholder pattern (ld.
       _KNOWN_PLACEHOLDER_MARKERS) -- a fixed, curated marker list, never
       a fuzzy/semantic match, and only applied to short responses so a
       long genuine translation is never caught by it.
    """
    stripped = (text or "").strip()
    if not stripped:
        return True
    first_line, sep, rest = stripped.partition("\n")
    if _LEADING_HEADING_LINE_RE.match(first_line) and (not sep or not rest.strip()):
        return True
    if len(stripped) < _PLACEHOLDER_MARKER_MAX_RESPONSE_CHARS:
        lowered = stripped.lower()
        if any(marker in lowered for marker in _KNOWN_PLACEHOLDER_MARKERS):
            return True
    return False


def _record_to_outcome(record: TranslationRecord) -> TranslationOutcome:
    return TranslationOutcome(
        status="cached",
        text=record.translated_text,
        provider_model=record.provider_model,
        created_at=record.created_at,
    )


def get_translation(
    section_id: str,
    *,
    language: str = DEFAULT_LANGUAGE,
    repository: CommentaryRepository | None = None,
    database_path: str | Path | None = None,
) -> TranslationOutcome:
    """Cache-only lookup -- never calls a provider. Fail-closed: a
    missing section, a missing translation DB, or a corrupt translation
    DB all resolve to a plain "missing"/"unavailable" outcome, never an
    exception."""
    repo = repository if repository is not None else CommentaryRepository()
    detail = repo.section_detail(section_id)
    if detail is None:
        return TranslationOutcome(status="unavailable", message="A szakasz nem érhető el.")
    fingerprint = compute_source_fingerprint([c.plain_text for c in detail.chunks])
    record = _store_get_translation(
        section_id,
        fingerprint,
        language=language,
        policy_version=TRANSLATION_POLICY_VERSION,
        database_path=database_path,
    )
    if record is None:
        return TranslationOutcome(status="missing")
    return _record_to_outcome(record)


def get_or_create_translation(
    section_id: str,
    *,
    language: str = DEFAULT_LANGUAGE,
    generate_fn: Callable[..., str] | None,
    provider_model: str = "",
    repository: CommentaryRepository | None = None,
    database_path: str | Path | None = None,
    bypass_cooldown: bool = False,
) -> TranslationOutcome:
    """Cache-hit -> immediate return, zero provider calls. Cache-miss ->
    translates the FULL canonical section (every chunk, in order -- never
    just a UI preview), automatically split into several smaller provider
    calls when the section is too large to translate safely in one (ld.
    split_section_for_translation), then persists on success. A failure
    on ANY batch aborts the whole section -- nothing partial, and no
    provider warning/error string, is ever cached; the original English
    stays fully available regardless. Provider unavailability or failure
    never touches the original English Commentary, which this function
    never touches either way.

    ``bypass_cooldown`` forwards straight to ``generate_fn`` (matches
    ``generate_text``'s own "same button press" convention for multiple
    calls back-to-back, ld. its docstring in app.py) -- callers that
    translate SEVERAL sections from one user action (ld. commentary_ui.
    _translate_missing_sections) must set this for every call after the
    first, or app.py's own inter-call cooldown makes every call but the
    first fail as a false "provider unavailable". Every INTERNAL batch
    after the section's own first one always bypasses the cooldown too
    (same already-authorized action) -- this internal route exists only
    for this controlled multi-call-per-section workflow, never a general
    "skip the cooldown" escape hatch for other callers."""
    repo = repository if repository is not None else CommentaryRepository()
    detail = repo.section_detail(section_id)
    if detail is None:
        return TranslationOutcome(status="unavailable", message="A szakasz nem érhető el.")

    chunk_texts = [c.plain_text for c in detail.chunks]
    fingerprint = compute_source_fingerprint(chunk_texts)
    cached = _store_get_translation(
        section_id,
        fingerprint,
        language=language,
        policy_version=TRANSLATION_POLICY_VERSION,
        database_path=database_path,
    )
    if cached is not None:
        return _record_to_outcome(cached)

    if not chunk_texts:
        return TranslationOutcome(
            status="unavailable", message="Ehhez a szakaszhoz nem tartozik önálló szöveg."
        )
    if generate_fn is None:
        return TranslationOutcome(
            status="no_generate_fn", message="Nincs elérhető MI-hívás a fordításhoz."
        )

    work_title = detail.work_title
    contributors = ", ".join(detail.contributors) or "—"
    passage_display = ", ".join(detail.primary_passages or detail.canonical_passages) or "—"
    canonical_passages = detail.primary_passages or detail.canonical_passages

    # A real production section (Matthew Henry / Rom.8.1-9, one 14281-char
    # chunk) truncated mid-sentence at the model's output-token ceiling in
    # a single call. split_section_for_translation batches the section
    # (primarily along its own existing chunk boundaries -- unchanged,
    # single-batch behavior for the vast majority of sections that
    # already fit) so no single call is ever asked to produce anywhere
    # near that budget. Batches translate in order and are joined back in
    # that SAME order below; a failure on ANY batch aborts the whole
    # section -- nothing partial is ever cached (ld. the early return in
    # the loop) and the original English stays fully available regardless.
    # Reads the module-level constant by name at call time (not baked in
    # as a default parameter value) specifically so tests can monkeypatch
    # DEFAULT_TRANSLATION_BATCH_MAX_CHARS to force multi-batch behavior
    # deterministically, without needing a giant fixture section.
    batches = split_section_for_translation(chunk_texts, max_chars=DEFAULT_TRANSLATION_BATCH_MAX_CHARS)
    translated_parts: list[str] = []
    for index, batch_text in enumerate(batches):
        prompt = build_translation_prompt(
            section_text=batch_text,
            work_title=work_title,
            contributors=contributors,
            passage_display=passage_display,
        )
        raw = generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=TRANSLATION_TAB_LABEL,
            use_cache=False,
            include_brevity_directive=False,
            # The FIRST batch of this section respects the caller's own
            # cooldown decision (e.g. it may be the very first provider
            # call of this button press); every batch AFTER it is part of
            # the SAME already-authorized, controlled multi-call
            # translation of one section, so it always bypasses the
            # cooldown -- this internal route is never exposed for any
            # other multi-call use (ld. this function's own docstring).
            bypass_cooldown=bypass_cooldown or index > 0,
        )
        batch_result = str(raw or "")
        if _looks_like_provider_failure(batch_result):
            return TranslationOutcome(status="provider_error", message=batch_result)
        if _looks_like_placeholder_translation(batch_result):
            return TranslationOutcome(
                status="provider_error",
                message="A modell válasza nem tekinthető valódi fordításnak.",
            )
        translated_parts.append(
            _strip_redundant_passage_heading(batch_result, canonical_passages)
        )

    text = "\n\n".join(translated_parts)
    saved = _store_save_translation(
        section_id=section_id,
        source_fingerprint=fingerprint,
        language=language,
        policy_version=TRANSLATION_POLICY_VERSION,
        translated_text=text,
        provider_model=provider_model,
        database_path=database_path,
    )
    if saved is not None:
        return TranslationOutcome(
            status="generated",
            text=saved.translated_text,
            provider_model=saved.provider_model,
            created_at=saved.created_at,
        )
    # Store write failed (e.g. translation DB unavailable/corrupt) -- the
    # text itself is still a valid, real translation and safe to show
    # once; it just won't be cached this time (next open re-generates).
    return TranslationOutcome(status="generated", text=text, provider_model=provider_model)


__all__ = [
    "DEFAULT_LANGUAGE",
    "DEFAULT_TRANSLATION_BATCH_MAX_CHARS",
    "TRANSLATION_TAB_LABEL",
    "TranslationOutcome",
    "get_or_create_translation",
    "get_translation",
    "split_section_for_translation",
]
