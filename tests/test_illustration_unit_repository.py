from __future__ import annotations

import sqlite3

import pytest

from illustration_engine.illustration_sqlite import (
    PILOT_HOMILETIC_FUNCTIONS,
    PILOT_TONES,
    PILOT_TOPICS,
    IllustrationUnitReviewProtectionError,
    create_schema,
    insert_source,
    insert_story,
    update_unit_machine_qa,
)
from illustration_engine.illustration_unit_repository import (
    IllustrationReviewItem,
    approve_unit,
    attach_tag_to_unit,
    create_draft_unit,
    get_or_create_tag,
    get_review_item,
    get_unit,
    list_review_items,
    list_units_for_story,
    mark_needs_review,
    publish_unit,
    replace_review_tags,
    search_units,
    send_back_for_rework,
    update_draft_unit,
    validate_approve_ready,
    validate_publish_ready,
)


def _fresh_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def _make_source(conn: sqlite3.Connection, *, license_status: str = "public_domain_confirmed") -> int:
    return insert_source(
        conn,
        code="SRC",
        title="Test Source",
        orig_language="en",
        license_status=license_status,
        license_basis_hu="test basis",
        reliability_tier="high",
    )


def _make_story(conn: sqlite3.Connection, source_id: int) -> int:
    return insert_story(
        conn,
        source_id=source_id,
        external_ref="1",
        canonical_key="001",
        title_original="Original Title",
        adaptation_status="verbatim_transcription",
        original_text="Once upon a time, a wise man taught his students a lesson about patience.",
    )


def test_full_lifecycle_draft_to_published() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    conn.commit()
    unit = get_unit(conn, unit_id)
    assert unit.status == "draft"
    assert unit.title_hu is None

    ready, reasons = validate_publish_ready(conn, unit_id)
    assert ready is False
    assert "title_hu is missing" in reasons

    update_draft_unit(
        conn,
        unit_id=unit_id,
        title_hu="A türelmes tanító",
        modern_hu_text="Egyszer egy bölcs ember türelemre tanította tanítványait.",
        summary_hu="Rövid tanmese a türelemről.",
        enrichment_model="test-model-v1",
        enrichment_prompt_version="hu_enrichment_v1",
    )
    conn.commit()

    mark_needs_review(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "needs_review"

    approve_unit(conn, unit_id)
    conn.commit()
    approved = get_unit(conn, unit_id)
    assert approved.status == "approved"
    assert approved.human_reviewed_at is not None

    ready, reasons = validate_publish_ready(conn, unit_id)
    assert ready is True
    assert reasons == []

    publish_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "published"


def test_list_units_for_story_ordered_by_unit_index() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    third = create_draft_unit(conn, story_id=story_id, unit_index=3, derivation_type="condensed_story")
    first = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="condensed_story")
    second = create_draft_unit(conn, story_id=story_id, unit_index=2, derivation_type="condensed_story")
    conn.commit()

    units = list_units_for_story(conn, story_id)
    conn.close()
    assert [u.id for u in units] == [first, second, third]
    assert [u.unit_index for u in units] == [1, 2, 3]


def test_get_unit_returns_none_for_missing_id() -> None:
    conn = _fresh_connection()
    result = get_unit(conn, 999999)
    conn.close()
    assert result is None


def test_update_draft_unit_refuses_silent_overwrite_of_reviewed_content() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Cím", modern_hu_text="Szöveg", summary_hu="Összefoglaló"
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()

    with pytest.raises(IllustrationUnitReviewProtectionError):
        update_draft_unit(conn, unit_id=unit_id, title_hu="AI re-run overwrite attempt")
    conn.close()


def test_update_draft_unit_refuses_enrichment_provenance_only_change_on_reviewed_unit() -> None:
    """Schema v4/Phase 3C-c: enrichment_model/_prompt_version/
    _generated_at/warnings are protected the same way as title_hu etc.
    -- a call that touches ONLY provenance fields (no visible content at
    all) on an already-reviewed unit must still be refused, not slip
    through because it doesn't mention title_hu/modern_hu_text."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Cím", modern_hu_text="Szöveg", summary_hu="Összefoglaló",
        enrichment_model="claude-sonnet-5",
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()

    with pytest.raises(IllustrationUnitReviewProtectionError):
        update_draft_unit(conn, unit_id=unit_id, enrichment_model="a-different-model")
    with pytest.raises(IllustrationUnitReviewProtectionError):
        update_draft_unit(conn, unit_id=unit_id, enrichment_warnings=("a new warning",))
    conn.close()


def test_explicit_overwrite_of_enrichment_provenance_demotes_unit() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Cím", modern_hu_text="Szöveg", summary_hu="Összefoglaló",
        enrichment_model="claude-sonnet-5",
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()

    update_draft_unit(
        conn, unit_id=unit_id, enrichment_model="a-different-model", allow_overwrite_reviewed=True
    )
    conn.commit()
    updated = get_unit(conn, unit_id)
    conn.close()
    assert updated.enrichment_model == "a-different-model"
    assert updated.human_reviewed_at is None
    assert updated.status == "needs_review"


def test_approve_and_publish_leave_all_enrichment_provenance_fields_unchanged() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Cím", modern_hu_text="Szöveg", summary_hu="Összefoglaló",
        enrichment_model="claude-sonnet-5",
        enrichment_prompt_version="hu_illustration_enrichment_pilot_v1",
        enrichment_generated_at="2026-01-01T00:00:00+00:00",
        enrichment_warnings=("a real finding",),
    )
    conn.commit()
    before = get_unit(conn, unit_id)

    approve_unit(conn, unit_id)
    conn.commit()
    after_approve = get_unit(conn, unit_id)

    publish_unit(conn, unit_id)
    conn.commit()
    after_publish = get_unit(conn, unit_id)
    conn.close()

    for field in ("enrichment_model", "enrichment_prompt_version", "enrichment_generated_at", "enrichment_warnings"):
        before_value = getattr(before, field)
        assert getattr(after_approve, field) == before_value
        assert getattr(after_publish, field) == before_value
    assert after_publish.status == "published"


def test_approved_unit_explicit_overwrite_demotes_to_needs_review() -> None:
    """An explicit override on an APPROVED (not yet published) unit
    succeeds, but must actually demote it: human_reviewed_at cleared
    AND status forced back to needs_review — not left at 'approved'."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Eredeti", modern_hu_text="Szöveg", summary_hu="Összefoglaló"
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    before = get_unit(conn, unit_id)
    assert before.status == "approved"
    assert before.human_reviewed_at is not None

    update_draft_unit(conn, unit_id=unit_id, title_hu="Explicit felülírás", allow_overwrite_reviewed=True)
    conn.commit()
    updated = get_unit(conn, unit_id)
    assert updated.title_hu == "Explicit felülírás"
    assert updated.human_reviewed_at is None
    assert updated.status == "needs_review"
    conn.close()


def test_published_unit_explicit_overwrite_demotes_to_needs_review() -> None:
    """Same guarantee, but starting from an actually PUBLISHED unit —
    the overwrite must demote it out of 'published' entirely."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Eredeti", modern_hu_text="Szöveg", summary_hu="Összefoglaló"
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    publish_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "published"

    update_draft_unit(
        conn, unit_id=unit_id, modern_hu_text="Felülírt szöveg", allow_overwrite_reviewed=True
    )
    conn.commit()
    updated = get_unit(conn, unit_id)
    assert updated.modern_hu_text == "Felülírt szöveg"
    assert updated.human_reviewed_at is None
    assert updated.status == "needs_review"
    conn.close()


def test_overwritten_previously_published_unit_disappears_from_search() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=unit_id,
        title_hu="Cím",
        modern_hu_text="Egyedi kulcsszó: villamosfarkas.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    publish_unit(conn, unit_id)
    conn.commit()
    assert [r.id for r in search_units(conn, "villamosfarkas")] == [unit_id]

    update_draft_unit(
        conn,
        unit_id=unit_id,
        modern_hu_text="Még mindig villamosfarkas, de módosítva.",
        allow_overwrite_reviewed=True,
    )
    conn.commit()
    assert get_unit(conn, unit_id).status == "needs_review"
    assert search_units(conn, "villamosfarkas") == []
    conn.close()


def test_demoted_unit_searchable_again_after_fresh_review_and_republish() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=unit_id,
        title_hu="Cím",
        modern_hu_text="Egyedi kulcsszó: napórakagyló.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    publish_unit(conn, unit_id)
    conn.commit()

    update_draft_unit(
        conn, unit_id=unit_id, modern_hu_text="Frissített napórakagyló szöveg.", allow_overwrite_reviewed=True
    )
    conn.commit()
    assert search_units(conn, "napórakagyló") == []

    # fresh human review + re-publish
    approve_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "approved"
    publish_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "published"
    assert [r.id for r in search_units(conn, "napórakagyló")] == [unit_id]
    conn.close()


def test_publish_unit_raises_on_non_publishable_source() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn, license_status="restricted")
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn, unit_id=unit_id, title_hu="Cím", modern_hu_text="Szöveg", summary_hu="Összefoglaló"
    )
    conn.commit()

    ready, reasons = validate_publish_ready(conn, unit_id)
    assert ready is False
    assert any("license_status" in r for r in reasons)

    with pytest.raises(sqlite3.IntegrityError):
        publish_unit(conn, unit_id)
    conn.close()


def test_search_returns_only_published_and_license_publishable_units() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)

    published_unit = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=published_unit,
        title_hu="Türelem",
        modern_hu_text="A türelemről szóló egyedi kulcsszó: zsiráfmadár.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, published_unit)
    conn.commit()
    publish_unit(conn, published_unit)

    draft_unit = create_draft_unit(conn, story_id=story_id, unit_index=2, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=draft_unit,
        title_hu="Draft cím",
        modern_hu_text="Ugyanaz az egyedi kulcsszó: zsiráfmadár, de draft állapotban.",
        summary_hu="Draft összefoglaló.",
    )
    conn.commit()

    approved_not_published = create_draft_unit(
        conn, story_id=story_id, unit_index=3, derivation_type="full_story_translation"
    )
    update_draft_unit(
        conn,
        unit_id=approved_not_published,
        title_hu="Jóváhagyott, de nem publikált",
        modern_hu_text="Egyedi kulcsszó: zsiráfmadár, jóváhagyva, de nem publikálva.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, approved_not_published)
    conn.commit()

    results = search_units(conn, "zsiráfmadár")
    conn.close()
    assert [r.id for r in results] == [published_unit]


def test_search_excludes_published_unit_from_non_publishable_source() -> None:
    """Even a unit whose OWN status is 'published' must not surface if
    its source's license status changes after the fact — the read path
    re-checks the source, it doesn't trust the unit's own status alone."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    update_draft_unit(
        conn,
        unit_id=unit_id,
        title_hu="Cím",
        modern_hu_text="Egyedi kulcsszó: hódfarkas.",
        summary_hu="Összefoglaló.",
    )
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    publish_unit(conn, unit_id)
    conn.commit()
    assert [r.id for r in search_units(conn, "hódfarkas")] == [unit_id]

    # simulate the source's license being revoked after the fact
    conn.execute("UPDATE sources SET license_status = 'restricted' WHERE id = ?", (source_id,))
    conn.commit()
    assert search_units(conn, "hódfarkas") == []
    conn.close()


def test_get_or_create_tag_is_idempotent() -> None:
    conn = _fresh_connection()
    first = get_or_create_tag(conn, category="topic", slug="irgalom", label_hu="irgalom")
    second = get_or_create_tag(conn, category="topic", slug="irgalom", label_hu="irgalom")
    conn.close()
    assert first == second


def test_attach_tag_to_unit_and_query() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="condensed_story")
    tag_id = get_or_create_tag(conn, category="function", slug="bevezeto", label_hu="bevezető illusztráció")
    attach_tag_to_unit(conn, unit_id=unit_id, tag_id=tag_id)
    conn.commit()

    row = conn.execute(
        "SELECT COUNT(*) FROM illustration_unit_tags WHERE unit_id = ? AND tag_id = ?",
        (unit_id, tag_id),
    ).fetchone()
    conn.close()
    assert row[0] == 1


# ---------------------------------------------------------------------------
# Phase 3G-A: Human Review Backend Contract
# ---------------------------------------------------------------------------

_VALID_SUMMARY = " ".join(["szo"] * 45)


def _make_full_source(conn: sqlite3.Connection, *, license_status: str = "public_domain_confirmed") -> int:
    return insert_source(
        conn,
        code="SRC",
        title="Test Source",
        orig_language="en",
        license_status=license_status,
        license_basis_hu="test basis",
        reliability_tier="high",
        tradition="test tradition",
        source_url="http://example.org/src",
    )


def _make_numbered_story(conn: sqlite3.Connection, source_id: int, n: int, *, original_text: str | None = None) -> int:
    return insert_story(
        conn,
        source_id=source_id,
        external_ref=str(n),
        canonical_key=f"key-{n}",
        title_original=f"Original Title {n}",
        adaptation_status="verbatim_transcription",
        original_text=original_text or f"Original text number {n}.",
        source_reference=f"p. {n}",
    )


def _make_needs_review_unit(
    conn: sqlite3.Connection, story_id: int, *, unit_index: int = 1, warnings: tuple[str, ...] | None = None, **overrides
) -> int:
    unit_id = create_draft_unit(
        conn, story_id=story_id, unit_index=unit_index, derivation_type="full_story_translation"
    )
    fields = dict(
        title_hu="Cím",
        modern_hu_text="Szöveg",
        summary_hu=_VALID_SUMMARY,
        moral_hu="Tanulság",
        enrichment_model="claude-sonnet-5",
        enrichment_prompt_version="v1",
    )
    fields.update(overrides)
    update_draft_unit(conn, unit_id=unit_id, enrichment_warnings=warnings, **fields)
    mark_needs_review(conn, unit_id)
    replace_review_tags(conn, unit_id, topics=["eszesseg"], tone="humoros", homiletic_functions=["szemlelteto_pelda"])
    return unit_id


def test_get_review_item_returns_full_aggregate() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id, warnings=("suspicious: Test",))
    conn.commit()

    item = get_review_item(conn, unit_id)
    conn.close()

    assert isinstance(item, IllustrationReviewItem)
    # UNIT
    assert item.unit_id == unit_id
    assert item.story_id == story_id
    assert item.status == "needs_review"
    assert item.derivation_type == "full_story_translation"
    assert item.title_hu == "Cím"
    assert item.modern_hu_text == "Szöveg"
    assert item.summary_hu == _VALID_SUMMARY
    assert item.moral_hu == "Tanulság"
    assert item.human_reviewed_at is None
    # ENRICHMENT PROVENANCE
    assert item.enrichment_model == "claude-sonnet-5"
    assert item.enrichment_prompt_version == "v1"
    assert item.enrichment_warnings == ("suspicious: Test",)
    # RAW STORY
    assert item.title_original == "Original Title 1"
    assert item.original_text == "Original text number 1."
    assert item.source_reference == "p. 1"
    # SOURCE
    assert item.source_code == "SRC"
    assert item.source_title == "Test Source"
    assert item.tradition == "test tradition"
    assert item.license_status == "public_domain_confirmed"
    assert item.source_url == "http://example.org/src"
    # TAXONOMY
    assert item.topics == ("eszesseg",)
    assert item.tone == "humoros"
    assert item.homiletic_functions == ("szemlelteto_pelda",)


def test_get_review_item_returns_none_for_missing_unit() -> None:
    conn = _fresh_connection()
    result = get_review_item(conn, 999999)
    conn.close()
    assert result is None


def test_list_review_items_only_returns_matching_status() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_1 = _make_numbered_story(conn, source_id, 1)
    story_2 = _make_numbered_story(conn, source_id, 2)
    needs_review_id = _make_needs_review_unit(conn, story_1)
    approved_id = _make_needs_review_unit(conn, story_2)
    approve_unit(conn, approved_id)
    conn.commit()

    items = list_review_items(conn, status="needs_review")
    conn.close()

    assert [item.unit_id for item in items] == [needs_review_id]


def test_list_review_items_excludes_published_units() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_1 = _make_numbered_story(conn, source_id, 1)
    story_2 = _make_numbered_story(conn, source_id, 2)
    needs_review_id = _make_needs_review_unit(conn, story_1)
    published_id = _make_needs_review_unit(conn, story_2)
    approve_unit(conn, published_id)
    publish_unit(conn, published_id)
    conn.commit()

    items = list_review_items(conn, status="needs_review")
    conn.close()

    assert [item.unit_id for item in items] == [needs_review_id]
    assert published_id not in [item.unit_id for item in items]


def test_list_review_items_source_code_filter() -> None:
    conn = _fresh_connection()
    source_a = insert_source(
        conn, code="SRC-A", title="A", orig_language="en", license_status="public_domain_confirmed",
        license_basis_hu="x", reliability_tier="high",
    )
    source_b = insert_source(
        conn, code="SRC-B", title="B", orig_language="en", license_status="public_domain_confirmed",
        license_basis_hu="x", reliability_tier="high",
    )
    story_a = _make_numbered_story(conn, source_a, 1)
    story_b = _make_numbered_story(conn, source_b, 2)
    unit_a = _make_needs_review_unit(conn, story_a)
    _make_needs_review_unit(conn, story_b)
    conn.commit()

    items = list_review_items(conn, status="needs_review", source_code="SRC-A")
    conn.close()

    assert [item.unit_id for item in items] == [unit_a]
    assert items[0].source_code == "SRC-A"


def test_list_review_items_warnings_only_filter() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_1 = _make_numbered_story(conn, source_id, 1)
    story_2 = _make_numbered_story(conn, source_id, 2)
    clean_id = _make_needs_review_unit(conn, story_1)
    warned_id = _make_needs_review_unit(conn, story_2, warnings=("finding",))
    conn.commit()

    items = list_review_items(conn, status="needs_review", warnings_only=True)
    conn.close()

    assert [item.unit_id for item in items] == [warned_id]
    assert clean_id not in [item.unit_id for item in items]


def test_list_review_items_deterministic_order() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    # Create out of story_id order to prove the query itself sorts.
    story_3 = _make_numbered_story(conn, source_id, 3)
    story_1 = _make_numbered_story(conn, source_id, 1)
    story_2 = _make_numbered_story(conn, source_id, 2)
    unit_3 = _make_needs_review_unit(conn, story_3)
    unit_1 = _make_needs_review_unit(conn, story_1)
    unit_2 = _make_needs_review_unit(conn, story_2)
    conn.commit()

    items = list_review_items(conn, status="needs_review")
    conn.close()

    assert [item.story_id for item in items] == sorted([story_1, story_2, story_3])


def test_list_review_items_respects_limit() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    for n in range(5):
        story_id = _make_numbered_story(conn, source_id, n)
        _make_needs_review_unit(conn, story_id)
    conn.commit()

    items = list_review_items(conn, status="needs_review", limit=2)
    conn.close()

    assert len(items) == 2


def test_list_review_items_rejects_invalid_status() -> None:
    conn = _fresh_connection()
    with pytest.raises(ValueError):
        list_review_items(conn, status="not_a_real_status")
    conn.close()


# --- reviewer edit workflow -------------------------------------------------


def test_reviewer_edit_keeps_needs_review_status() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()

    update_draft_unit(conn, unit_id=unit_id, title_hu="Szerkesztett cím", modern_hu_text="Szerkesztett szöveg")
    conn.commit()
    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.title_hu == "Szerkesztett cím"
    assert item.modern_hu_text == "Szerkesztett szöveg"
    assert item.status == "needs_review"
    assert item.human_reviewed_at is None


# --- tag replacement atomicity ----------------------------------------------


def test_replace_review_tags_atomic_replace_not_accumulate() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)  # eszesseg/humoros/szemlelteto_pelda
    conn.commit()

    replace_review_tags(conn, unit_id, topics=["alazat", "irgalom"], tone="komoly", homiletic_functions=["ellenpelda"])
    conn.commit()
    item = get_review_item(conn, unit_id)
    conn.close()

    assert set(item.topics) == {"alazat", "irgalom"}
    assert "eszesseg" not in item.topics  # old topic replaced, not accumulated
    assert item.tone == "komoly"
    assert item.homiletic_functions == ("ellenpelda",)


def test_replace_review_tags_invalid_slug_raises_no_partial_change() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)  # eszesseg/humoros/szemlelteto_pelda
    conn.commit()

    with pytest.raises(ValueError):
        replace_review_tags(
            conn, unit_id, topics=["alazat", "nonexistent_topic"], tone="komoly",
            homiletic_functions=["ellenpelda"],
        )
    item = get_review_item(conn, unit_id)
    conn.close()

    # Completely unchanged -- not even the valid parts of the request applied.
    assert item.topics == ("eszesseg",)
    assert item.tone == "humoros"
    assert item.homiletic_functions == ("szemlelteto_pelda",)


def test_replace_review_tags_rejects_cross_category_slug() -> None:
    """A slug from the wrong controlled-vocabulary category (e.g. a tone
    slug submitted inside the topics list) must be rejected exactly like
    any other invalid slug -- and must not partially apply."""
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)  # eszesseg/humoros/szemlelteto_pelda
    conn.commit()

    with pytest.raises(ValueError):
        replace_review_tags(
            conn, unit_id, topics=["alazat", "humoros"],  # "humoros" is a TONE slug, not a topic
            tone="komoly", homiletic_functions=["ellenpelda"],
        )
    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.topics == ("eszesseg",)
    assert item.tone == "humoros"
    assert item.homiletic_functions == ("szemlelteto_pelda",)


def test_pilot_taxonomy_categories_are_pairwise_disjoint() -> None:
    """Sanity net for the cross-category rejection above: it only works
    because the three controlled-vocabulary sets never share a slug."""
    assert PILOT_TOPICS.isdisjoint(PILOT_TONES)
    assert PILOT_TOPICS.isdisjoint(PILOT_HOMILETIC_FUNCTIONS)
    assert PILOT_TONES.isdisjoint(PILOT_HOMILETIC_FUNCTIONS)


# ---------------------------------------------------------------------------
# Audit fix (2026-09-13): replace_review_tags() had NO human_reviewed_at
# check at all -- a taxonomy edit is a content edit (it drives retrieval
# matching exactly like title_hu/modern_hu_text do), but unlike every other
# content field it was reachable, unprotected, on an already-approved/
# published unit. These regression tests pin the fix: needs_review stays
# freely editable, approved/published/any-human-reviewed unit rejects the
# call outright (no partial write), and the only way back in is the same
# explicit send_back_for_rework() demotion every other content field
# already requires.
# ---------------------------------------------------------------------------


def test_replace_review_tags_allowed_when_needs_review() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)  # eszesseg/humoros/szemlelteto_pelda
    conn.commit()
    assert get_unit(conn, unit_id).status == "needs_review"

    replace_review_tags(conn, unit_id, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])
    conn.commit()
    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.topics == ("alazat",)
    assert item.tone == "komoly"


def test_replace_review_tags_rejected_when_approved() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    approve_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "approved"

    with pytest.raises(IllustrationUnitReviewProtectionError):
        replace_review_tags(conn, unit_id, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])
    item = get_review_item(conn, unit_id)
    conn.close()

    # Nothing changed -- still the original needs_review-era tags.
    assert item.topics == ("eszesseg",)
    assert item.tone == "humoros"
    assert item.status == "approved"


def test_replace_review_tags_rejected_when_published() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    approve_unit(conn, unit_id)
    publish_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "published"

    with pytest.raises(IllustrationUnitReviewProtectionError):
        replace_review_tags(conn, unit_id, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])
    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.topics == ("eszesseg",)
    assert item.status == "published"


def test_replace_review_tags_rejected_whenever_human_reviewed_at_is_set() -> None:
    """The gate is on human_reviewed_at, not on a hardcoded status list --
    matches the exact invariant update_illustration_unit_fields()/the SQL
    trigger already use for every other content field."""
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    approve_unit(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).human_reviewed_at is not None

    with pytest.raises(IllustrationUnitReviewProtectionError):
        replace_review_tags(conn, unit_id, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])
    conn.close()


def test_replace_review_tags_allowed_again_after_send_back_for_rework() -> None:
    """The prescribed recovery path -- explicit demotion first -- actually
    works, restoring editability without needing a second bypass."""
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    approve_unit(conn, unit_id)
    conn.commit()

    send_back_for_rework(conn, unit_id)
    conn.commit()
    assert get_unit(conn, unit_id).status == "needs_review"
    assert get_unit(conn, unit_id).human_reviewed_at is None

    replace_review_tags(conn, unit_id, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])
    conn.commit()
    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.topics == ("alazat",)


# --- approve/publish semantics ----------------------------------------------


def test_approve_unit_sets_human_reviewed_at() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()

    approve_unit(conn, unit_id)
    conn.commit()
    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.status == "approved"
    assert item.human_reviewed_at is not None


def test_approve_unit_does_not_publish() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()

    approve_unit(conn, unit_id)
    conn.commit()
    published_count = conn.execute("SELECT COUNT(*) FROM published_illustration_units WHERE id = ?", (unit_id,)).fetchone()[0]
    conn.close()

    assert published_count == 0


def test_approve_unit_raises_when_content_incomplete() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = create_draft_unit(conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation")
    conn.commit()  # never filled in -- title_hu/modern_hu_text/summary_hu all NULL

    ready, reasons = validate_approve_ready(conn, unit_id)
    assert ready is False
    assert "title_hu is missing" in reasons

    with pytest.raises(ValueError):
        approve_unit(conn, unit_id)
    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.status == "draft"
    assert item.human_reviewed_at is None


def test_approve_unit_succeeds_on_non_publishable_source_but_publish_still_blocked() -> None:
    """approve_unit() is the editorial gate (is the Hungarian content
    reviewed and correct?), publish_unit() is the separate legal gate
    (may this source's content go out at all?). A reviewer must be able
    to approve a unit's content as editorially finished even when its
    source's legal publishability is unresolved or negative -- but
    publish must still refuse it."""
    conn = _fresh_connection()
    source_id = _make_full_source(conn, license_status="restricted")
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()

    ready, reasons = validate_approve_ready(conn, unit_id)
    assert ready is True
    assert reasons == []

    approve_unit(conn, unit_id)  # must NOT raise
    conn.commit()
    item = get_review_item(conn, unit_id)
    assert item.status == "approved"
    assert item.human_reviewed_at is not None

    publish_ready, publish_reasons = validate_publish_ready(conn, unit_id)
    assert publish_ready is False
    assert any("license_status" in r for r in publish_reasons)

    with pytest.raises(sqlite3.IntegrityError):
        publish_unit(conn, unit_id)
    conn.close()


def test_publish_unit_requires_approved() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)  # needs_review, not approved
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        publish_unit(conn, unit_id)
    conn.close()


# --- published -> send_back_for_rework: the key regression -----------------


def test_published_unit_send_back_for_rework_full_invariant_check() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id, warnings=("finding: X",))
    conn.commit()
    approve_unit(conn, unit_id)
    publish_unit(conn, unit_id)
    conn.commit()
    before = get_review_item(conn, unit_id)
    assert before.status == "published"

    send_back_for_rework(conn, unit_id)
    conn.commit()
    after = get_review_item(conn, unit_id)
    published_view_count = conn.execute(
        "SELECT COUNT(*) FROM published_illustration_units WHERE id = ?", (unit_id,)
    ).fetchone()[0]
    search_results = search_units(conn, "Szöveg")
    conn.close()

    assert after.status == "needs_review"
    assert after.human_reviewed_at is None
    assert published_view_count == 0
    assert unit_id not in [r.id for r in search_results]
    # content, provenance, and warnings all survive the demotion untouched
    assert after.title_hu == before.title_hu
    assert after.modern_hu_text == before.modern_hu_text
    assert after.enrichment_model == before.enrichment_model
    assert after.enrichment_warnings == before.enrichment_warnings == ("finding: X",)
    assert after.original_text == before.original_text
    assert after.title_original == before.title_original


def test_approved_unit_send_back_for_rework() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id, warnings=("finding: Y",))
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()
    before = get_review_item(conn, unit_id)
    assert before.status == "approved"

    send_back_for_rework(conn, unit_id)
    conn.commit()
    after = get_review_item(conn, unit_id)
    conn.close()

    assert after.status == "needs_review"
    assert after.human_reviewed_at is None
    # content, provenance, warnings, and tags all survive the demotion
    assert after.title_hu == before.title_hu
    assert after.modern_hu_text == before.modern_hu_text
    assert after.summary_hu == before.summary_hu
    assert after.enrichment_model == before.enrichment_model
    assert after.enrichment_prompt_version == before.enrichment_prompt_version
    assert after.enrichment_warnings == before.enrichment_warnings == ("finding: Y",)
    assert after.topics == before.topics
    assert after.tone == before.tone
    assert after.homiletic_functions == before.homiletic_functions
    assert after.original_text == before.original_text
    assert after.title_original == before.title_original


def test_silent_content_edit_blocked_on_approved_unit_without_rework() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()

    with pytest.raises(IllustrationUnitReviewProtectionError):
        update_draft_unit(conn, unit_id=unit_id, title_hu="Csendes felülírás")
    conn.close()


def test_edit_allowed_after_send_back_for_rework() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()
    approve_unit(conn, unit_id)
    conn.commit()

    send_back_for_rework(conn, unit_id)
    conn.commit()
    update_draft_unit(conn, unit_id=unit_id, title_hu="Rework után szerkesztve")  # must NOT raise
    conn.commit()
    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.title_hu == "Rework után szerkesztve"
    assert item.status == "needs_review"
    assert item.human_reviewed_at is None  # still needs a fresh approve


def test_warning_provenance_survives_approve_publish_rework_cycle() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id, warnings=("suspicious finding",))
    conn.commit()

    warnings_at_start = get_review_item(conn, unit_id).enrichment_warnings
    approve_unit(conn, unit_id)
    conn.commit()
    warnings_after_approve = get_review_item(conn, unit_id).enrichment_warnings
    publish_unit(conn, unit_id)
    conn.commit()
    warnings_after_publish = get_review_item(conn, unit_id).enrichment_warnings
    send_back_for_rework(conn, unit_id)
    conn.commit()
    warnings_after_rework = get_review_item(conn, unit_id).enrichment_warnings
    conn.close()

    assert warnings_at_start == warnings_after_approve == warnings_after_publish == warnings_after_rework == ("suspicious finding",)


# --- raw provenance immutability --------------------------------------------


def test_review_workflow_never_touches_raw_story_or_checksum() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()

    before_story = conn.execute(
        "SELECT title_original, original_text, original_text_checksum FROM stories WHERE id = ?", (story_id,)
    ).fetchone()

    update_draft_unit(conn, unit_id=unit_id, title_hu="Edited")
    approve_unit(conn, unit_id)
    publish_unit(conn, unit_id)
    conn.commit()
    send_back_for_rework(conn, unit_id)
    replace_review_tags(conn, unit_id, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])
    conn.commit()

    after_story = conn.execute(
        "SELECT title_original, original_text, original_text_checksum FROM stories WHERE id = ?", (story_id,)
    ).fetchone()
    conn.close()

    assert before_story == after_story


# --- Phase 3F ledger separation ---------------------------------------------


def test_review_operations_do_not_modify_batch_ledger() -> None:
    """The review lifecycle (approve/publish/rework/edit) must never
    reach back and rewrite what an enrichment_run_items row already
    recorded -- that row is a frozen account of what happened DURING the
    enrichment run, not a live mirror of the unit's current review
    state. Two entirely separate audit layers (Phase 3F vs Phase 3G-A)."""
    from illustration_engine.illustration_sqlite import (
        insert_enrichment_run,
        insert_enrichment_run_item,
    )

    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id, warnings=("finding",))
    conn.commit()

    run_id = insert_enrichment_run(
        conn, model_identifier="claude-sonnet-5", prompt_version="v1", source_code="SRC",
        strategy_band="A", requested_limit=1,
    )
    item_id = insert_enrichment_run_item(conn, run_id=run_id, story_id=story_id, expected_mode="direct_unit")
    from illustration_engine.illustration_sqlite import update_enrichment_run_item
    update_enrichment_run_item(
        conn, item_id=item_id, status="warning", illustration_unit_id=unit_id,
        warnings_json='["finding"]',
    )
    conn.commit()
    ledger_before = conn.execute(
        "SELECT status, illustration_unit_id, warnings_json, error_message FROM enrichment_run_items WHERE id = ?",
        (item_id,),
    ).fetchone()

    update_draft_unit(conn, unit_id=unit_id, title_hu="Reviewer edited this")
    approve_unit(conn, unit_id)
    publish_unit(conn, unit_id)
    conn.commit()
    send_back_for_rework(conn, unit_id)
    conn.commit()

    ledger_after = conn.execute(
        "SELECT status, illustration_unit_id, warnings_json, error_message FROM enrichment_run_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    conn.close()

    assert ledger_before == ledger_after == ("warning", unit_id, '["finding"]', None)


# ---------------------------------------------------------------------------
# Phase 3H: machine QA fields exposed on IllustrationReviewItem + qa_status
# filter on list_review_items -- reviewer-facing, no lifecycle coupling.
# ---------------------------------------------------------------------------


def test_review_item_exposes_qa_fields_default_none() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()

    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.qa_status is None
    assert item.qa_confidence is None
    assert item.qa_issues_json is None


def test_review_item_exposes_qa_fields_after_machine_qa() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()

    update_unit_machine_qa(
        conn, unit_id=unit_id, qa_status="needs_attention", qa_model="qa-m", qa_prompt_version="qa_v1",
        qa_confidence=0.55, qa_issues_json='[{"code":"POOR_HUNGARIAN","detail":"x"}]',
    )
    conn.commit()
    item = get_review_item(conn, unit_id)
    conn.close()

    assert item.qa_status == "needs_attention"
    assert item.qa_model == "qa-m"
    assert item.qa_confidence == 0.55
    assert "POOR_HUNGARIAN" in item.qa_issues_json


def test_list_review_items_qa_status_filter() -> None:
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_1 = _make_numbered_story(conn, source_id, 1)
    story_2 = _make_numbered_story(conn, source_id, 2)
    passed_id = _make_needs_review_unit(conn, story_1)
    pending_id = _make_needs_review_unit(conn, story_2)
    update_unit_machine_qa(conn, unit_id=passed_id, qa_status="passed", qa_model="m", qa_prompt_version="v1")
    conn.commit()

    passed_items = list_review_items(conn, status="needs_review", qa_status="passed")
    pending_items = list_review_items(conn, status="needs_review", qa_status="pending")
    conn.close()

    assert [i.unit_id for i in passed_items] == [passed_id]
    assert [i.unit_id for i in pending_items] == [pending_id]


def test_list_review_items_qa_status_pending_matches_null() -> None:
    """qa_status='pending' must match units that were NEVER machine-QA'd
    (qa_status IS NULL in the DB), not just an explicit 'pending' value."""
    conn = _fresh_connection()
    source_id = _make_full_source(conn)
    story_id = _make_numbered_story(conn, source_id, 1)
    unit_id = _make_needs_review_unit(conn, story_id)
    conn.commit()

    raw_qa_status = conn.execute("SELECT qa_status FROM illustration_units WHERE id=?", (unit_id,)).fetchone()[0]
    assert raw_qa_status is None

    items = list_review_items(conn, status="needs_review", qa_status="pending")
    conn.close()
    assert [i.unit_id for i in items] == [unit_id]


def test_list_review_items_rejects_invalid_qa_status() -> None:
    conn = _fresh_connection()
    with pytest.raises(ValueError):
        list_review_items(conn, qa_status="not_a_real_qa_status")
    conn.close()
