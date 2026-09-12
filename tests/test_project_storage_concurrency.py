"""2026-09 audit fix — regression coverage for optimistic concurrency on
the `projects` table (see ``supabase/migrations/
20260912150000_projects_revision_optimistic_lock.sql`` and
``project_storage.update_project``/``UpdateProjectResult``).

Before this fix, ``update_project`` was a blind
``UPDATE ... WHERE id = ? AND owner_sub = ?`` with no version check: two
browser tabs (or a stale autosave racing a manual save) editing the same
project both "succeed", and whichever write lands last silently overwrites
the other's changes with no signal to either user. This file proves the
fix for exactly that scenario (spec item "E"): two clients load the same
revision, one saves, the other's save (from the now-stale revision) must
be rejected as a CONFLICT, never silently overwriting the first save.

No real network access or Supabase credentials — a minimal fake Postgrest
client backed by a single in-memory row, same convention as
``tests/test_hebrew_analysis_repository_supabase.py``.
"""

from __future__ import annotations

import project_storage as ps


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeQuery:
    """One in-flight `.table(...).select(...)`/`.update(...)` builder,
    backed directly by the single shared `table` dict below."""

    def __init__(self, table: dict, *, op: str, payload: dict | None = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload or {}
        self._filters: dict[str, object] = {}

    def select(self, _columns: str) -> "_FakeQuery":
        return self

    def eq(self, key: str, value: object) -> "_FakeQuery":
        self._filters[key] = value
        return self

    def limit(self, _n: int) -> "_FakeQuery":
        return self

    def _matches(self) -> bool:
        return all(self._table.get(k) == v for k, v in self._filters.items())

    def execute(self) -> _FakeResponse:
        if not self._matches():
            return _FakeResponse([])
        if self._op == "update":
            self._table.update(self._payload)
        return _FakeResponse([dict(self._table)])


class _FakeTable:
    def __init__(self, table: dict) -> None:
        self._table = table

    def select(self, _columns: str) -> _FakeQuery:
        return _FakeQuery(self._table, op="select")

    def update(self, payload: dict) -> _FakeQuery:
        return _FakeQuery(self._table, op="update", payload=payload)


class _FakeClient:
    def __init__(self, table: dict) -> None:
        self._table = table

    def table(self, name: str) -> _FakeTable:
        assert name == ps.PROJECTS_TABLE
        return _FakeTable(self._table)


def _seed_project() -> dict:
    return {
        "id": "proj-1",
        "owner_sub": "user-1",
        "title": "Eredeti cím",
        "passage": "Jn 3,16",
        "project_data": {},
        "revision": 1,
        "created_at": "2026-09-01T00:00:00Z",
        "updated_at": "2026-09-01T00:00:00Z",
    }


def test_concurrent_clients_second_stale_writer_gets_conflict_not_overwrite(monkeypatch):
    table = _seed_project()
    monkeypatch.setattr(ps, "get_supabase_client", lambda: _FakeClient(table))

    # Both "clients" (two browser tabs) load the project at revision 1.
    client_a_view = ps.get_project("proj-1", "user-1")
    client_b_view = ps.get_project("proj-1", "user-1")
    assert client_a_view["revision"] == client_b_view["revision"] == 1

    # Client A saves first — succeeds, bumps the stored revision to 2.
    result_a = ps.update_project(
        "proj-1", "user-1", "A verziója", "Jn 3,16", {"overview": "A szövege"}, expected_revision=1,
    )
    assert result_a.outcome == ps.SaveOutcome.OK
    assert result_a.row["revision"] == 2
    assert table["title"] == "A verziója"

    # Client B still believes it's at revision 1 (it never saw A's write).
    # Its save must be rejected as a conflict, and A's data must survive
    # completely untouched — no silent last-write-wins overwrite.
    result_b = ps.update_project(
        "proj-1", "user-1", "B verziója", "Jn 3,16", {"overview": "B szövege"}, expected_revision=1,
    )
    assert result_b.outcome == ps.SaveOutcome.CONFLICT
    assert result_b.current_revision == 2
    assert table["title"] == "A verziója"
    # sanitize_project_data fills in the full schema with defaults, so
    # compare only the field the two clients actually disagree on.
    assert table["project_data"]["overview"] == "A szövege"

    # If B reloads (picks up the current revision) and saves again, that
    # now succeeds normally — conflict is not a permanent lockout.
    result_b_retry = ps.update_project(
        "proj-1", "user-1", "B verziója (újratöltve)", "Jn 3,16", {"overview": "B szövege"},
        expected_revision=result_b.current_revision,
    )
    assert result_b_retry.outcome == ps.SaveOutcome.OK
    assert table["title"] == "B verziója (újratöltve)"


def test_update_missing_project_reports_not_found_not_conflict(monkeypatch):
    table = _seed_project()
    monkeypatch.setattr(ps, "get_supabase_client", lambda: _FakeClient(table))

    result = ps.update_project(
        "does-not-exist", "user-1", "Cím", "Jn 3,16", {}, expected_revision=1,
    )
    assert result.outcome == ps.SaveOutcome.NOT_FOUND


def test_update_wrong_owner_reports_not_found_not_conflict(monkeypatch):
    """A different user's id must never be distinguishable from a
    revision conflict — ownership failures are NOT_FOUND, matching the
    existing 'projekt nem található, vagy nem a tied' UI copy."""
    table = _seed_project()
    monkeypatch.setattr(ps, "get_supabase_client", lambda: _FakeClient(table))

    result = ps.update_project(
        "proj-1", "someone-else", "Cím", "Jn 3,16", {}, expected_revision=1,
    )
    assert result.outcome == ps.SaveOutcome.NOT_FOUND
    assert table["title"] == "Eredeti cím"  # untouched
