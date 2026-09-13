"""SupabaseIllustrationReviewRepository — Phase 1 skeleton, exercised
against a minimal fake Postgrest client (same pattern as
tests/test_hebrew_analysis_repository_supabase.py). No real network
access anywhere in this file, no production credentials needed or used.

NOT exercised against a real Supabase project yet -- the DDL migration
has not been applied. These tests pin the repository's OWN logic
(precondition checks, review-protection gate, controlled-vocabulary
validation, the exact update/delete/insert calls it issues) against a
faithful-enough fake, matching the same "structurally review the Python
layer, don't require a live Postgres" approach the rest of this Phase 1
round uses."""

from __future__ import annotations

import pytest

from illustration_engine.supabase_review_repository import (
    IllustrationUnitNotEligibleError,
    IllustrationUnitNotFoundError,
    IllustrationUnitReviewProtectionError,
    SupabaseIllustrationReviewRepository,
)


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, table: "_FakeTable", *, op: str, payload: dict | None = None) -> None:
        self._table = table
        self._op = op  # "select" | "update" | "delete" | "insert"
        self._payload = payload
        self._eq_filters: dict[str, object] = {}

    def eq(self, key: str, value) -> "_FakeQuery":
        self._eq_filters[key] = value
        return self

    def _matches(self, row: dict) -> bool:
        return all(row.get(k) == v for k, v in self._eq_filters.items())

    def execute(self) -> _FakeResponse:
        rows = self._table.rows
        if self._op == "select":
            matched = [dict(r) for r in rows if self._matches(r)]
            return _FakeResponse(matched)
        if self._op == "update":
            matched = [r for r in rows if self._matches(r)]
            for r in matched:
                r.update(self._payload)
            return _FakeResponse([dict(r) for r in matched])
        if self._op == "delete":
            matched = [r for r in rows if self._matches(r)]
            for r in matched:
                rows.remove(r)
            return _FakeResponse([dict(r) for r in matched])
        if self._op == "insert":
            payload_rows = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = []
            for row in payload_rows:
                new_row = dict(row)
                if "id" not in new_row:
                    new_row["id"] = self._table.next_id()
                rows.append(new_row)
                inserted.append(dict(new_row))
            return _FakeResponse(inserted)
        raise AssertionError(f"unsupported op: {self._op}")


class _FakeTable:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self._id_seq = max((r.get("id", 0) for r in rows), default=0)

    def next_id(self) -> int:
        self._id_seq += 1
        return self._id_seq

    def select(self, _columns: str) -> _FakeQuery:
        return _FakeQuery(self, op="select")

    def update(self, payload: dict) -> _FakeQuery:
        return _FakeQuery(self, op="update", payload=payload)

    def delete(self) -> _FakeQuery:
        return _FakeQuery(self, op="delete")

    def insert(self, payload) -> _FakeQuery:
        return _FakeQuery(self, op="insert", payload=payload)


class _FakeClient:
    def __init__(self, tables: dict[str, list[dict]]) -> None:
        self._tables = {name: _FakeTable(rows) for name, rows in tables.items()}

    def table(self, name: str) -> _FakeTable:
        return self._tables.setdefault(name, _FakeTable([]))


def _needs_review_unit(**overrides) -> dict:
    base = {
        "id": 1,
        "status": "needs_review",
        "title_hu": "Cím",
        "modern_hu_text": "Szöveg",
        "summary_hu": "Összefoglaló " * 10,
        "human_reviewed_at": None,
        "reviewed_by_email": None,
    }
    base.update(overrides)
    return base


def _client_with_unit(**overrides) -> _FakeClient:
    return _FakeClient({"illustration_units": [_needs_review_unit(**overrides)]})


# ---------------------------------------------------------------------------
# approve_unit
# ---------------------------------------------------------------------------


def test_approve_unit_sets_status_and_reviewer_email() -> None:
    client = _client_with_unit()
    repo = SupabaseIllustrationReviewRepository(client=client)

    repo.approve_unit(1, reviewer_email="hoverzsolt@gmail.com")

    row = client.table("illustration_units").rows[0]
    assert row["status"] == "approved"
    assert row["reviewed_by_email"] == "hoverzsolt@gmail.com"
    assert row["human_reviewed_at"] is not None


def test_approve_unit_rejects_empty_reviewer_email() -> None:
    client = _client_with_unit()
    repo = SupabaseIllustrationReviewRepository(client=client)

    with pytest.raises(ValueError):
        repo.approve_unit(1, reviewer_email="")

    assert client.table("illustration_units").rows[0]["status"] == "needs_review"


def test_approve_unit_rejects_missing_content() -> None:
    client = _client_with_unit(title_hu=None)
    repo = SupabaseIllustrationReviewRepository(client=client)

    with pytest.raises(IllustrationUnitNotEligibleError):
        repo.approve_unit(1, reviewer_email="hoverzsolt@gmail.com")


def test_approve_unit_not_found_raises() -> None:
    client = _FakeClient({"illustration_units": []})
    repo = SupabaseIllustrationReviewRepository(client=client)

    with pytest.raises(IllustrationUnitNotFoundError):
        repo.approve_unit(999, reviewer_email="hoverzsolt@gmail.com")


def test_approve_unit_not_needs_review_raises() -> None:
    client = _client_with_unit(status="approved", human_reviewed_at="2026-09-13T00:00:00Z")
    repo = SupabaseIllustrationReviewRepository(client=client)

    with pytest.raises(IllustrationUnitNotEligibleError):
        repo.approve_unit(1, reviewer_email="hoverzsolt@gmail.com")


# ---------------------------------------------------------------------------
# publish_unit
# ---------------------------------------------------------------------------


def test_publish_unit_from_approved_succeeds() -> None:
    client = _client_with_unit(status="approved", human_reviewed_at="2026-09-13T00:00:00Z")
    repo = SupabaseIllustrationReviewRepository(client=client)

    repo.publish_unit(1)

    assert client.table("illustration_units").rows[0]["status"] == "published"


def test_publish_unit_from_needs_review_rejected() -> None:
    client = _client_with_unit(status="needs_review")
    repo = SupabaseIllustrationReviewRepository(client=client)

    with pytest.raises(IllustrationUnitNotEligibleError):
        repo.publish_unit(1)


# ---------------------------------------------------------------------------
# send_back_for_rework
# ---------------------------------------------------------------------------


def test_send_back_for_rework_clears_review_metadata() -> None:
    client = _client_with_unit(
        status="published", human_reviewed_at="2026-09-13T00:00:00Z",
        reviewed_by_email="hoverzsolt@gmail.com",
    )
    repo = SupabaseIllustrationReviewRepository(client=client)

    repo.send_back_for_rework(1)

    row = client.table("illustration_units").rows[0]
    assert row["status"] == "needs_review"
    assert row["human_reviewed_at"] is None
    assert row["reviewed_by_email"] is None


def test_send_back_for_rework_not_found_raises() -> None:
    client = _FakeClient({"illustration_units": []})
    repo = SupabaseIllustrationReviewRepository(client=client)

    with pytest.raises(IllustrationUnitNotFoundError):
        repo.send_back_for_rework(999)


# ---------------------------------------------------------------------------
# replace_review_tags -- the audit-fix gate, ported alongside the skeleton
# ---------------------------------------------------------------------------


def test_replace_review_tags_allowed_when_needs_review() -> None:
    client = _client_with_unit()
    repo = SupabaseIllustrationReviewRepository(client=client)

    repo.replace_review_tags(1, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])

    links = client.table("illustration_unit_tags").rows
    assert len(links) == 3  # topic + tone + function


def test_replace_review_tags_rejected_when_human_reviewed_at_set() -> None:
    client = _client_with_unit(status="approved", human_reviewed_at="2026-09-13T00:00:00Z")
    repo = SupabaseIllustrationReviewRepository(client=client)

    with pytest.raises(IllustrationUnitReviewProtectionError):
        repo.replace_review_tags(1, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])

    assert client.table("illustration_unit_tags").rows == []


def test_replace_review_tags_rejected_when_published() -> None:
    client = _client_with_unit(status="published", human_reviewed_at="2026-09-13T00:00:00Z")
    repo = SupabaseIllustrationReviewRepository(client=client)

    with pytest.raises(IllustrationUnitReviewProtectionError):
        repo.replace_review_tags(1, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])


def test_replace_review_tags_invalid_slug_writes_nothing() -> None:
    client = _client_with_unit()
    repo = SupabaseIllustrationReviewRepository(client=client)

    with pytest.raises(ValueError):
        repo.replace_review_tags(
            1, topics=["nonexistent_topic"], tone="komoly", homiletic_functions=["ellenpelda"]
        )

    assert client.table("illustration_unit_tags").rows == []


def test_replace_review_tags_allowed_again_after_send_back_for_rework() -> None:
    client = _client_with_unit(status="approved", human_reviewed_at="2026-09-13T00:00:00Z")
    repo = SupabaseIllustrationReviewRepository(client=client)

    repo.send_back_for_rework(1)
    repo.replace_review_tags(1, topics=["alazat"], tone="komoly", homiletic_functions=["ellenpelda"])

    assert len(client.table("illustration_unit_tags").rows) == 3
