"""Read/write repository API for `illustration_units` (schema v4,
Phase 3A/3C-c) — the layer a future controlled enrichment pilot (and,
eventually, `app.py`-side retrieval — NOT wired up here) is meant to
call, instead of every caller hand-rolling its own SQL against
`illustration_sqlite.py`'s low-level primitives.

Nothing here calls an LLM, generates Hungarian text, or writes to any
`stories` provenance field — this module only moves already-produced
enrichment field values into/through the schema v4 gates. Every
transition function relies on the two independent DB-layer gates
(content-completeness CHECK + license trigger for `published`, the
human-review-protection trigger for content updates) to actually be
fail-closed; the Python-side checks here exist for clearer error
messages and cheaper pre-flight validation, not as the sole guarantee.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from illustration_engine.illustration_sqlite import (
    ALLOWED_QA_STATUSES,
    ALLOWED_UNIT_STATUSES,
    PILOT_HOMILETIC_FUNCTIONS,
    PILOT_TONES,
    PILOT_TOPICS,
    IllustrationUnitReviewProtectionError,
    insert_illustration_unit,
    update_illustration_unit_fields,
)


@dataclass(frozen=True)
class IllustrationUnitView:
    id: int
    story_id: int
    unit_index: int
    derivation_type: str
    source_span_start: int | None
    source_span_end: int | None
    title_hu: str | None
    modern_hu_text: str | None
    summary_hu: str | None
    moral_hu: str | None
    narrative_status: str | None
    narrative_status_confidence: str | None
    status: str
    enrichment_model: str | None
    enrichment_prompt_version: str | None
    enrichment_generated_at: str | None
    # Parsed from the DB's `enrichment_warnings_json` TEXT column so no
    # caller (least of all a future review UI) ever has to hand-parse raw
    # JSON — () means the last enrichment run produced no warnings, same
    # meaning as a NULL column value.
    enrichment_warnings: tuple[str, ...]
    human_reviewed_at: str | None
    created_at: str
    updated_at: str


_UNIT_COLUMNS = (
    "id",
    "story_id",
    "unit_index",
    "derivation_type",
    "source_span_start",
    "source_span_end",
    "title_hu",
    "modern_hu_text",
    "summary_hu",
    "moral_hu",
    "narrative_status",
    "narrative_status_confidence",
    "status",
    "enrichment_model",
    "enrichment_prompt_version",
    "enrichment_generated_at",
    "enrichment_warnings_json",
    "human_reviewed_at",
    "created_at",
    "updated_at",
)


def _row_to_view(row: tuple) -> IllustrationUnitView:
    values = dict(zip(_UNIT_COLUMNS, row))
    raw_warnings_json = values.pop("enrichment_warnings_json")
    values["enrichment_warnings"] = tuple(json.loads(raw_warnings_json)) if raw_warnings_json else ()
    return IllustrationUnitView(**values)


def create_draft_unit(
    connection: sqlite3.Connection,
    *,
    story_id: int,
    unit_index: int,
    derivation_type: str,
    source_span_start: int | None = None,
    source_span_end: int | None = None,
) -> int:
    """Creates an empty draft unit — a placeholder the enrichment
    pipeline then fills in via `update_draft_unit`. Never sets any
    content field itself (no field defaults to anything but NULL)."""
    return insert_illustration_unit(
        connection,
        story_id=story_id,
        unit_index=unit_index,
        derivation_type=derivation_type,
        source_span_start=source_span_start,
        source_span_end=source_span_end,
        status="draft",
    )


def update_draft_unit(
    connection: sqlite3.Connection,
    *,
    unit_id: int,
    title_hu: str | None = None,
    modern_hu_text: str | None = None,
    summary_hu: str | None = None,
    moral_hu: str | None = None,
    narrative_status: str | None = None,
    narrative_status_confidence: str | None = None,
    enrichment_model: str | None = None,
    enrichment_prompt_version: str | None = None,
    enrichment_generated_at: str | None = None,
    enrichment_warnings: tuple[str, ...] | None = None,
    allow_overwrite_reviewed: bool = False,
) -> None:
    """Writes enrichment output onto an existing unit. Refuses (via
    `update_illustration_unit_fields`'s guard) to silently overwrite a
    unit that already has `human_reviewed_at` set, unless
    `allow_overwrite_reviewed=True` — this is the enforcement point an
    AI re-run pipeline must go through; it cannot accidentally clobber
    approved content by simply calling this function again. Passing
    `allow_overwrite_reviewed=True` on an already-reviewed unit demotes
    it: `human_reviewed_at` is cleared and `status` is forced back to
    `needs_review` in the same write, so it immediately drops out of
    `published_illustration_units`/`search_units()` results — a fresh
    `approve_unit()`/`publish_unit()` pass is required to make it
    retrieval-ready again.

    `enrichment_warnings` uses REPLACE, not accumulate-or-omit,
    semantics, unlike every other parameter here: passing the Python
    default `None` means "not specified, leave the column untouched"
    (same as every other field), but passing `()` (an explicitly EMPTY
    tuple — a real run that found nothing to warn about) SETS the column
    to NULL rather than being filtered out like every other falsy-or-None
    value would be. This is what makes a clean re-run correctly erase a
    stale warning left over from an earlier, warning-producing run,
    rather than leaving it to look like it still applies."""
    fields = {
        name: value
        for name, value in (
            ("title_hu", title_hu),
            ("modern_hu_text", modern_hu_text),
            ("summary_hu", summary_hu),
            ("moral_hu", moral_hu),
            ("narrative_status", narrative_status),
            ("narrative_status_confidence", narrative_status_confidence),
            ("enrichment_model", enrichment_model),
            ("enrichment_prompt_version", enrichment_prompt_version),
            ("enrichment_generated_at", enrichment_generated_at),
        )
        if value is not None
    }
    if enrichment_warnings is not None:
        fields["enrichment_warnings_json"] = (
            json.dumps(list(enrichment_warnings)) if enrichment_warnings else None
        )
    if not fields:
        return
    update_illustration_unit_fields(
        connection,
        unit_id=unit_id,
        allow_overwrite_reviewed=allow_overwrite_reviewed,
        **fields,
    )


def list_units_for_story(connection: sqlite3.Connection, story_id: int) -> list[IllustrationUnitView]:
    rows = connection.execute(
        f"SELECT {', '.join(_UNIT_COLUMNS)} FROM illustration_units "
        "WHERE story_id = ? ORDER BY unit_index",
        (story_id,),
    ).fetchall()
    return [_row_to_view(row) for row in rows]


def get_unit(connection: sqlite3.Connection, unit_id: int) -> IllustrationUnitView | None:
    row = connection.execute(
        f"SELECT {', '.join(_UNIT_COLUMNS)} FROM illustration_units WHERE id = ?",
        (unit_id,),
    ).fetchone()
    return _row_to_view(row) if row else None


@dataclass(frozen=True)
class IllustrationReviewItem:
    """Phase 3G-A: the single, reviewer-facing aggregate read model — a
    future review UI assembles a full screen for one unit from ONE
    `get_review_item()` call (or one entry from `list_review_items()`),
    never five separate repository calls of its own. Pure JOIN/query
    over EXISTING tables; nothing here is duplicated into a new table."""

    # UNIT
    unit_id: int
    story_id: int
    unit_index: int
    status: str
    derivation_type: str
    title_hu: str | None
    modern_hu_text: str | None
    summary_hu: str | None
    moral_hu: str | None
    narrative_status: str | None
    narrative_status_confidence: str | None
    human_reviewed_at: str | None
    # ENRICHMENT PROVENANCE
    enrichment_model: str | None
    enrichment_prompt_version: str | None
    enrichment_generated_at: str | None
    enrichment_warnings: tuple[str, ...]
    # MACHINE QA PROVENANCE (Phase 3H) -- a THIRD, independent provenance
    # layer, never conflated with enrichment_* (what the enrichment
    # pipeline itself produced) or human_reviewed_at (the human lifecycle
    # gate). qa_status is None for a unit no machine QA run has ever
    # touched (treat the same as "pending"). qa_issues_json is the raw
    # JSON string as stored -- kept unparsed here (no qa_agent import in
    # this module) so a caller that wants structured QAIssue objects
    # parses it itself.
    qa_status: str | None
    qa_model: str | None
    qa_prompt_version: str | None
    qa_checked_at: str | None
    qa_confidence: float | None
    qa_issues_json: str | None
    # RAW STORY -- read-only here; the review workflow has no write path
    # to any of these (see the Phase 3G-A raw-provenance-immutability
    # regression test).
    title_original: str
    original_text: str
    source_reference: str | None
    # SOURCE
    source_code: str
    source_title: str
    tradition: str | None
    license_status: str
    source_url: str | None
    # TAXONOMY
    topics: tuple[str, ...]
    tone: str | None
    homiletic_functions: tuple[str, ...]


_REVIEW_ITEM_SELECT = """
    SELECT
        u.id, u.story_id, u.unit_index, u.status, u.derivation_type,
        u.title_hu, u.modern_hu_text, u.summary_hu, u.moral_hu,
        u.narrative_status, u.narrative_status_confidence, u.human_reviewed_at,
        u.enrichment_model, u.enrichment_prompt_version, u.enrichment_generated_at,
        u.enrichment_warnings_json,
        u.qa_status, u.qa_model, u.qa_prompt_version, u.qa_checked_at,
        u.qa_confidence, u.qa_issues_json,
        st.title_original, st.original_text, st.source_reference,
        s.code, s.title, s.tradition, s.license_status, s.source_url
    FROM illustration_units u
    JOIN stories st ON st.id = u.story_id
    JOIN sources s ON s.id = st.source_id
"""


def _fetch_unit_taxonomy(
    connection: sqlite3.Connection, unit_id: int
) -> tuple[tuple[str, ...], str | None, tuple[str, ...]]:
    rows = connection.execute(
        "SELECT t.category, t.slug FROM illustration_unit_tags ut JOIN tags t ON t.id = ut.tag_id "
        "WHERE ut.unit_id = ? ORDER BY t.category, t.slug",
        (unit_id,),
    ).fetchall()
    topics = tuple(slug for category, slug in rows if category == "topic")
    tones = [slug for category, slug in rows if category == "tone"]
    homiletic_functions = tuple(slug for category, slug in rows if category == "function")
    return topics, (tones[0] if tones else None), homiletic_functions


def _row_to_review_item(row: tuple, *, taxonomy: tuple[tuple[str, ...], str | None, tuple[str, ...]]) -> IllustrationReviewItem:
    (
        unit_id, story_id, unit_index, status, derivation_type,
        title_hu, modern_hu_text, summary_hu, moral_hu,
        narrative_status, narrative_status_confidence, human_reviewed_at,
        enrichment_model, enrichment_prompt_version, enrichment_generated_at,
        enrichment_warnings_json,
        qa_status, qa_model, qa_prompt_version, qa_checked_at, qa_confidence, qa_issues_json,
        title_original, original_text, source_reference,
        source_code, source_title, tradition, license_status, source_url,
    ) = row
    topics, tone, homiletic_functions = taxonomy
    return IllustrationReviewItem(
        unit_id=unit_id, story_id=story_id, unit_index=unit_index, status=status,
        derivation_type=derivation_type, title_hu=title_hu, modern_hu_text=modern_hu_text,
        summary_hu=summary_hu, moral_hu=moral_hu, narrative_status=narrative_status,
        narrative_status_confidence=narrative_status_confidence, human_reviewed_at=human_reviewed_at,
        enrichment_model=enrichment_model, enrichment_prompt_version=enrichment_prompt_version,
        enrichment_generated_at=enrichment_generated_at,
        enrichment_warnings=tuple(json.loads(enrichment_warnings_json)) if enrichment_warnings_json else (),
        qa_status=qa_status, qa_model=qa_model, qa_prompt_version=qa_prompt_version,
        qa_checked_at=qa_checked_at, qa_confidence=qa_confidence, qa_issues_json=qa_issues_json,
        title_original=title_original, original_text=original_text, source_reference=source_reference,
        source_code=source_code, source_title=source_title, tradition=tradition,
        license_status=license_status, source_url=source_url,
        topics=topics, tone=tone, homiletic_functions=homiletic_functions,
    )


def get_review_item(connection: sqlite3.Connection, unit_id: int) -> IllustrationReviewItem | None:
    """Returns `None` only if the unit itself does not exist (matching
    `get_unit()`'s own convention). If the unit exists but its story/
    source provenance cannot be resolved (a foreign-key integrity
    problem that should never happen given this schema's FK
    constraints, but is not something to silently paper over), this
    FAILS CLOSED with `ValueError` instead of assembling a partial or
    fabricated review item — a human reviewer must never be shown a
    unit whose provenance is unknown."""
    unit = get_unit(connection, unit_id)
    if unit is None:
        return None
    row = connection.execute(_REVIEW_ITEM_SELECT + " WHERE u.id = ?", (unit_id,)).fetchone()
    if row is None:
        raise ValueError(
            f"illustration unit id={unit_id} exists but its story/source provenance could not be "
            "resolved -- refusing to assemble a review item without full provenance"
        )
    return _row_to_review_item(row, taxonomy=_fetch_unit_taxonomy(connection, unit_id))


def list_review_items(
    connection: sqlite3.Connection,
    *,
    status: str = "needs_review",
    source_code: str | None = None,
    warnings_only: bool = False,
    qa_status: str | None = None,
    limit: int = 50,
) -> list[IllustrationReviewItem]:
    """The review QUEUE, not a general search engine (see `search_units`
    for retrieval-ready full-text search): a small, fixed set of filters
    a review UI actually needs. Deterministic order: `story_id ASC,
    unit_index ASC` — the same reproducible-ordering convention as
    `enrichment_batch.create_run`'s selection query.

    `qa_status` (Phase 3H) filters on the machine-QA verdict column,
    independent of `status`/`warnings_only` (human-review lifecycle vs.
    enrichment warnings vs. machine QA are three separate axes — see
    `IllustrationReviewItem`'s own field-grouping comments).
    `qa_status="pending"` matches BOTH `qa_status IS NULL` (never
    QA-checked) and the literal `'pending'` value, since the two mean
    the same thing to a caller."""
    if status not in ALLOWED_UNIT_STATUSES:
        raise ValueError(f"status must be one of {sorted(ALLOWED_UNIT_STATUSES)}, got {status!r}")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit!r}")
    if qa_status is not None and qa_status not in ALLOWED_QA_STATUSES:
        raise ValueError(f"qa_status must be one of {sorted(ALLOWED_QA_STATUSES)}, got {qa_status!r}")

    where_clauses = ["u.status = ?"]
    params: list[object] = [status]
    if source_code is not None:
        where_clauses.append("s.code = ?")
        params.append(source_code)
    if warnings_only:
        where_clauses.append("u.enrichment_warnings_json IS NOT NULL")
    if qa_status == "pending":
        where_clauses.append("(u.qa_status IS NULL OR u.qa_status = 'pending')")
    elif qa_status is not None:
        where_clauses.append("u.qa_status = ?")
        params.append(qa_status)

    query = (
        _REVIEW_ITEM_SELECT
        + " WHERE "
        + " AND ".join(where_clauses)
        + " ORDER BY u.story_id ASC, u.unit_index ASC LIMIT ?"
    )
    rows = connection.execute(query, (*params, limit)).fetchall()
    return [
        _row_to_review_item(row, taxonomy=_fetch_unit_taxonomy(connection, row[0]))
        for row in rows
    ]


def send_back_for_rework(connection: sqlite3.Connection, unit_id: int) -> None:
    """Phase 3G-A: the ONE correct, explicit way to demote an
    `approved`/`published` unit back to `needs_review` WITHOUT touching
    its content — atomically setting `status='needs_review'` AND
    `human_reviewed_at=NULL` in the same write, regardless of the unit's
    current status. Neither `status` nor `human_reviewed_at` is itself a
    member of `_UNIT_CONTENT_FIELDS` (see `illustration_sqlite.py`), so
    `trg_units_protect_human_reviewed_content`'s content-change WHEN
    clause never fires for this call — no `allow_overwrite_reviewed`
    escape hatch is needed or accepted here, because nothing "reviewed"
    is being overwritten, only the workflow/review-provenance fields
    themselves.

    A `published` unit sent back for rework immediately disappears from
    `published_illustration_units` (the view's own WHERE clause requires
    `status='published'`) and from `search_units()` (which joins against
    that same view) — no separate step is needed to "unpublish" it.

    A later `approve_unit()` (after any edits via `update_draft_unit`)
    is required to make the unit reviewed again; this call never
    approves or edits anything by itself."""
    update_illustration_unit_fields(
        connection, unit_id=unit_id, status="needs_review", human_reviewed_at=None
    )


def mark_needs_review(connection: sqlite3.Connection, unit_id: int) -> None:
    """Delegates to `send_back_for_rework()` — Phase 3G-A hardening. The
    original implementation only ever set `status`, leaving a PREVIOUSLY
    `approved`/`published` unit's `human_reviewed_at` untouched if this
    were ever called directly on one — an inconsistent state (demoted-
    looking `status` with a stale review timestamp still attached),
    though never actually reachable through this module's own
    enrichment-pipeline call site (which always clears
    `human_reviewed_at` itself first, via `update_draft_unit`, before
    this function ever runs). Delegating closes the gap for ANY caller,
    including a future one, without changing behavior for the existing
    one — `human_reviewed_at` is already `NULL` by the time the
    enrichment pipeline calls this, so setting it to `NULL` again is a
    no-op there."""
    send_back_for_rework(connection, unit_id)


def validate_approve_ready(connection: sqlite3.Connection, unit_id: int) -> tuple[bool, list[str]]:
    """Pure pre-check (no mutation) for `approve_unit()`.

    `approve_unit()` is the EDITORIAL/human-review gate: is the Hungarian
    content itself finished and reviewable? It is deliberately narrower
    than `publish_unit()`'s LEGAL gate (source `license_status`) — a
    reviewer must be able to approve a unit's editorial content as
    correct and complete even when its source's legal publishability
    hasn't been resolved yet (or never will be). Legal publishability is
    checked once, at `publish_unit()` time, via `validate_publish_ready`
    and the DB-level trigger; it is intentionally NOT re-checked here.
    Approve and publish stay two independent gates for two independent
    questions.

    Deliberately does NOT require any taxonomy tag to be attached —
    "valid taxonomy" here means only that whatever tags ARE attached
    are drawn from the controlled vocabulary (already guaranteed
    structurally: the only writers of `illustration_unit_tags` are the
    enrichment pipeline's own validated tag-sync and this module's
    `replace_review_tags`, both of which already reject an invalid slug
    before writing anything). Tag-completeness is a review-quality
    signal a future review UI can surface, not an approval blocker."""
    unit = get_unit(connection, unit_id)
    if unit is None:
        return False, [f"illustration unit not found: id={unit_id}"]

    reasons: list[str] = []
    if not unit.title_hu:
        reasons.append("title_hu is missing")
    if not unit.modern_hu_text:
        reasons.append("modern_hu_text is missing")
    if not unit.summary_hu:
        reasons.append("summary_hu is missing")

    return (not reasons), reasons


def approve_unit(
    connection: sqlite3.Connection, unit_id: int, *, human_reviewed_at: str | None = None
) -> None:
    """Moves a unit to `approved` and stamps `human_reviewed_at` (the
    Phase 3A brief's review-provenance signal — distinct from the
    workflow `status`) — but only after `validate_approve_ready()`
    confirms the unit is actually ready (Phase 3G-A: raises `ValueError`
    otherwise, zero DB writes). Stamping the review timestamp here is
    what makes the human-review-protection trigger start guarding this
    unit's content from here on. Never publishes by itself — `publish_
    unit()` remains a separate, explicit human decision."""
    ready, reasons = validate_approve_ready(connection, unit_id)
    if not ready:
        raise ValueError(f"cannot approve illustration unit id={unit_id}: {'; '.join(reasons)}")
    update_illustration_unit_fields(
        connection,
        unit_id=unit_id,
        status="approved",
        human_reviewed_at=human_reviewed_at or datetime.now(UTC).isoformat(),
    )


def validate_publish_ready(connection: sqlite3.Connection, unit_id: int) -> tuple[bool, list[str]]:
    """Pure pre-check (no mutation) mirroring the DB-level publish
    gates, for pilot/UI tooling that wants a reason list before
    attempting the real transition (which the DB enforces regardless)."""
    unit = get_unit(connection, unit_id)
    if unit is None:
        return False, [f"illustration unit not found: id={unit_id}"]

    reasons: list[str] = []
    if unit.title_hu is None:
        reasons.append("title_hu is missing")
    if unit.modern_hu_text is None:
        reasons.append("modern_hu_text is missing")
    if unit.summary_hu is None:
        reasons.append("summary_hu is missing")
    if unit.human_reviewed_at is None:
        reasons.append("human_reviewed_at is missing (no human review recorded)")

    license_row = connection.execute(
        """
        SELECT s.license_status FROM stories st JOIN sources s ON s.id = st.source_id
        WHERE st.id = ?
        """,
        (unit.story_id,),
    ).fetchone()
    if license_row is None or license_row[0] not in ("public_domain_confirmed", "permission_granted"):
        reasons.append(
            f"source license_status {license_row[0] if license_row else None!r} does not "
            "permit publishing"
        )

    return (not reasons), reasons


def publish_unit(connection: sqlite3.Connection, unit_id: int) -> None:
    """Transitions a unit to `published`. Relies on the DB-level
    content-completeness CHECK and `trg_units_publish_requires_license_*`
    trigger as the actual fail-closed gate — this call raises
    `sqlite3.IntegrityError` (not a custom exception) if either is
    violated, exactly like every other publish-gated write in this
    schema. Call `validate_publish_ready` first for a friendlier reason
    list."""
    update_illustration_unit_fields(connection, unit_id=unit_id, status="published")


def get_or_create_tag(
    connection: sqlite3.Connection, *, category: str, slug: str, label_hu: str
) -> int:
    row = connection.execute(
        "SELECT id FROM tags WHERE category = ? AND slug = ?", (category, slug)
    ).fetchone()
    if row is not None:
        return int(row[0])
    cursor = connection.execute(
        "INSERT INTO tags(category, slug, label_hu) VALUES (?, ?, ?)",
        (category, slug, label_hu),
    )
    return int(cursor.lastrowid)


def attach_tag_to_unit(connection: sqlite3.Connection, *, unit_id: int, tag_id: int) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO illustration_unit_tags(unit_id, tag_id) VALUES (?, ?)",
        (unit_id, tag_id),
    )


def detach_tag_from_unit(connection: sqlite3.Connection, *, unit_id: int, tag_id: int) -> None:
    """Symmetric counterpart to `attach_tag_to_unit` — used by callers
    (e.g. the enrichment pipeline's tag-sync step) that need to REPLACE
    a unit's tag set rather than only ever add to it."""
    connection.execute(
        "DELETE FROM illustration_unit_tags WHERE unit_id = ? AND tag_id = ?",
        (unit_id, tag_id),
    )


def replace_review_tags(
    connection: sqlite3.Connection,
    unit_id: int,
    *,
    topics: list[str],
    tone: str,
    homiletic_functions: list[str],
) -> None:
    """Phase 3G-A: the public, reviewer-facing counterpart to the
    enrichment pipeline's private `_sync_pilot_tags` — same REPLACE (not
    accumulate) semantics: after this call, the unit's `topic`/`tone`/
    `function` tags are EXACTLY the given sets, nothing old left
    dangling. Deliberately does not exist in `enrichment_pipeline.py`
    (that module is LLM/enrichment-run-scoped) nor does this module
    import that one (would be circular) — both pull the SAME controlled
    vocabulary from `illustration_sqlite.py` instead.

    ALL-OR-NOTHING validation: every slug is checked against the
    controlled vocabulary BEFORE any DB write happens — an invalid slug
    anywhere in the request raises `ValueError` with zero partial
    modification, never a half-replaced tag set.

    REVIEW PROTECTION (audit fix, 2026-09-13): taxonomy is content too —
    a unit's topics/tone/homiletic_functions directly drive retrieval
    matching, exactly like title_hu/modern_hu_text do. Before this fix,
    this function had NO `human_reviewed_at` check at all, unlike
    `update_illustration_unit_fields()` (guarded by both the Python-side
    `_UNIT_CONTENT_FIELDS` check and the SQL `trg_units_protect_human_
    reviewed_content` trigger) — an already-approved/published unit's
    tags could be silently rewritten with no demotion, no cleared
    timestamp, no trace. Fails closed now: any unit with
    `human_reviewed_at IS NOT NULL` (approved or published) raises
    `IllustrationUnitReviewProtectionError` and writes NOTHING — the
    caller must call `send_back_for_rework()` first, exactly the same
    explicit-demotion-before-edit contract `update_illustration_unit_
    fields()` already enforces for every other content field."""
    unit = get_unit(connection, unit_id)
    if unit is None:
        raise ValueError(f"illustration unit not found: id={unit_id}")
    if unit.human_reviewed_at is not None:
        raise IllustrationUnitReviewProtectionError(
            f"illustration unit id={unit_id} was human-reviewed at {unit.human_reviewed_at!r} — "
            "refusing to silently change its taxonomy tags. Call send_back_for_rework() first."
        )

    invalid: list[str] = []
    if not topics or not (1 <= len(topics) <= 3):
        invalid.append("topics must be a list of 1-3 items")
    else:
        invalid.extend(f"invalid topic slug: {t!r}" for t in topics if t not in PILOT_TOPICS)
    if tone not in PILOT_TONES:
        invalid.append(f"invalid tone slug: {tone!r}")
    if not homiletic_functions or not (1 <= len(homiletic_functions) <= 2):
        invalid.append("homiletic_functions must be a list of 1-2 items")
    else:
        invalid.extend(
            f"invalid homiletic_function slug: {f!r}"
            for f in homiletic_functions
            if f not in PILOT_HOMILETIC_FUNCTIONS
        )
    if invalid:
        raise ValueError(f"cannot replace tags for unit id={unit_id}: {'; '.join(invalid)}")

    desired: set[tuple[str, str]] = {("topic", slug) for slug in topics}
    desired.add(("tone", tone))
    desired.update(("function", slug) for slug in homiletic_functions)

    existing = connection.execute(
        "SELECT ut.tag_id, t.category, t.slug FROM illustration_unit_tags ut "
        "JOIN tags t ON t.id = ut.tag_id WHERE ut.unit_id = ?",
        (unit_id,),
    ).fetchall()
    for tag_id, category, slug in existing:
        pair = (category, slug)
        if pair in desired:
            desired.discard(pair)
        elif category in ("topic", "tone", "function"):
            detach_tag_from_unit(connection, unit_id=unit_id, tag_id=tag_id)

    for category, slug in desired:
        tag_id = get_or_create_tag(connection, category=category, slug=slug, label_hu=slug)
        attach_tag_to_unit(connection, unit_id=unit_id, tag_id=tag_id)


def search_units(
    connection: sqlite3.Connection, query_text: str, *, limit: int = 20
) -> list[IllustrationUnitView]:
    """Full-text search restricted to retrieval-ready units: published
    AND the parent story's source license publishable — enforced by
    joining the FTS5 match back to `published_illustration_units`, not
    by trusting the FTS index's own contents (which includes drafts —
    see the schema module docstring for why)."""
    rows = connection.execute(
        f"""
        SELECT {', '.join('u.' + c for c in _UNIT_COLUMNS)}
        FROM illustration_units_fts fts
        JOIN illustration_units u ON u.id = fts.rowid
        JOIN published_illustration_units p ON p.id = u.id
        WHERE illustration_units_fts MATCH ?
        ORDER BY bm25(illustration_units_fts)
        LIMIT ?
        """,
        (query_text, limit),
    ).fetchall()
    return [_row_to_view(row) for row in rows]


__all__ = [
    "IllustrationReviewItem",
    "IllustrationUnitView",
    "approve_unit",
    "attach_tag_to_unit",
    "create_draft_unit",
    "detach_tag_from_unit",
    "get_or_create_tag",
    "get_review_item",
    "get_unit",
    "list_review_items",
    "list_units_for_story",
    "mark_needs_review",
    "publish_unit",
    "replace_review_tags",
    "search_units",
    "send_back_for_rework",
    "update_draft_unit",
    "validate_approve_ready",
    "validate_publish_ready",
]
