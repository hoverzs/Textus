"""Targeted tests for scripts/backfill_illustration_story_outcomes.py --
fake Supabase client, no network access, no LLM call anywhere. Covers:
the embedded backfill dataset's own integrity, the missing-table guidance
path, and the rescue/already-present exclusion logic that keeps the
backfill idempotent and safe to re-run."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SPEC = importlib.util.spec_from_file_location(
    "backfill_illustration_story_outcomes", ROOT / "scripts" / "backfill_illustration_story_outcomes.py"
)
backfill_script = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = backfill_script
_SPEC.loader.exec_module(backfill_script)


# ---------------------------------------------------------------------------
# REJECT_BACKFILL_V1 -- embedded dataset integrity
# ---------------------------------------------------------------------------


def test_backfill_v1_has_no_duplicate_story_ids() -> None:
    ids = [row["story_id"] for row in backfill_script.REJECT_BACKFILL_V1]
    assert len(ids) == len(set(ids))


def test_backfill_v1_all_outcomes_rejected() -> None:
    assert all(row["outcome"] == "rejected" for row in backfill_script.REJECT_BACKFILL_V1)


def test_backfill_v1_reasons_short_and_present() -> None:
    for row in backfill_script.REJECT_BACKFILL_V1:
        assert row["reason"]
        assert len(row["reason"]) <= 200


def test_backfill_v1_expected_count() -> None:
    # 77 REJECT decisions from the v8/round-6 batch (see script docstring for
    # the reconstruction methodology and why this is the full, deduplicated set).
    assert len(backfill_script.REJECT_BACKFILL_V1) == 77


# ---------------------------------------------------------------------------
# Fake Supabase client
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, client: "_FakeClient", name: str) -> None:
        self._client = client
        self._name = name
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None
        self._pending_insert: list[dict] | None = None

    def select(self, _cols: str) -> "_FakeTable":
        if self._name not in self._client.data:
            raise RuntimeError(f"relation \"{self._name}\" does not exist")
        return self

    def limit(self, n: int) -> "_FakeTable":
        self._limit = n
        return self

    def range(self, start: int, end: int) -> "_FakeTable":
        self._range = (start, end)
        return self

    def insert(self, rows: list[dict]) -> "_FakeTable":
        self._pending_insert = rows
        return self

    def execute(self) -> _FakeResponse:
        if self._pending_insert is not None:
            self._client.data.setdefault(self._name, []).extend(self._pending_insert)
            self._client.inserted.extend(self._pending_insert)
            return _FakeResponse(self._pending_insert)

        rows = self._client.data.get(self._name, [])
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        return _FakeResponse(rows)


class _FakeClient:
    def __init__(self, initial_data: dict[str, list[dict]]) -> None:
        self.data: dict[str, list[dict]] = {k: list(v) for k, v in initial_data.items()}
        self.inserted: list[dict] = []

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self, name)


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def test_main_reports_missing_table(monkeypatch, capsys) -> None:
    client = _FakeClient({"illustration_units": []})  # no illustration_story_outcomes key
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)
    monkeypatch.setattr(sys, "argv", ["backfill_illustration_story_outcomes.py"])

    exit_code = backfill_script.main()

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "does not exist" in captured.out
    assert "create table if not exists illustration_story_outcomes" in captured.out


def test_main_dry_run_excludes_rescued_and_already_present(monkeypatch, capsys) -> None:
    rescued_id = backfill_script.REJECT_BACKFILL_V1[0]["story_id"]
    already_present_id = backfill_script.REJECT_BACKFILL_V1[1]["story_id"]

    client = _FakeClient({
        "illustration_story_outcomes": [{"story_id": already_present_id}],
        "illustration_units": [{"story_id": rescued_id}],
    })
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)
    monkeypatch.setattr(sys, "argv", ["backfill_illustration_story_outcomes.py"])

    exit_code = backfill_script.main()

    assert exit_code == 0
    assert client.inserted == []  # dry run: no writes
    captured = capsys.readouterr()
    assert f"To write: {len(backfill_script.REJECT_BACKFILL_V1) - 2}" in captured.out


def test_main_apply_inserts_only_the_still_valid_new_rows(monkeypatch) -> None:
    rescued_id = backfill_script.REJECT_BACKFILL_V1[0]["story_id"]
    already_present_id = backfill_script.REJECT_BACKFILL_V1[1]["story_id"]

    client = _FakeClient({
        "illustration_story_outcomes": [{"story_id": already_present_id}],
        "illustration_units": [{"story_id": rescued_id}],
    })
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)
    monkeypatch.setattr(sys, "argv", ["backfill_illustration_story_outcomes.py", "--apply"])

    exit_code = backfill_script.main()

    assert exit_code == 0
    inserted_ids = {row["story_id"] for row in client.inserted}
    assert rescued_id not in inserted_ids
    assert already_present_id not in inserted_ids
    assert len(client.inserted) == len(backfill_script.REJECT_BACKFILL_V1) - 2


def test_main_apply_never_writes_a_story_that_already_has_a_unit(monkeypatch) -> None:
    """Regression test for the explicit rule: a story that has since gotten
    a unit must never be (re-)marked as rejected in the registry."""
    all_ids = [row["story_id"] for row in backfill_script.REJECT_BACKFILL_V1]
    client = _FakeClient({
        "illustration_story_outcomes": [],
        "illustration_units": [{"story_id": sid} for sid in all_ids],  # every candidate "rescued"
    })
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)
    monkeypatch.setattr(sys, "argv", ["backfill_illustration_story_outcomes.py", "--apply"])

    exit_code = backfill_script.main()

    assert exit_code == 0
    assert client.inserted == []
