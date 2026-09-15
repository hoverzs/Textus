"""scripts/apply_automated_corpus_approval.py -- pilot-selection logic
(pure function, no I/O) and the script's client-usage pattern (fake
Supabase client, no real network). Same importlib-by-path convention as
tests/test_migrate_illustrations_to_supabase.py -- scripts/ has no
__init__.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SPEC = importlib.util.spec_from_file_location(
    "apply_automated_corpus_approval", ROOT / "scripts" / "apply_automated_corpus_approval.py"
)
approval_script = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = approval_script
_SPEC.loader.exec_module(approval_script)


# ---------------------------------------------------------------------------
# select_diverse_batch -- pure function
# ---------------------------------------------------------------------------


def _cand(id_, source_code):
    return {"id": id_, "source_code": source_code}


def test_diverse_batch_round_robins_across_sources() -> None:
    candidates = [
        _cand(1, "A"), _cand(2, "A"), _cand(3, "A"),
        _cand(4, "B"), _cand(5, "B"),
        _cand(6, "C"),
    ]
    selected = approval_script.select_diverse_batch(candidates, limit=4)
    # Round-robin order: A(1), B(4), C(6), A(2) -- one from each source in
    # turn before returning to a source for a second pick.
    assert selected == [1, 4, 6, 2]


def test_diverse_batch_never_all_one_source_when_others_available() -> None:
    candidates = [_cand(i, "DOMINANT") for i in range(1, 101)] + [_cand(101, "TINY")]
    selected = approval_script.select_diverse_batch(candidates, limit=5)
    sources_selected = {c["source_code"] for c in candidates if c["id"] in selected}
    assert "TINY" in sources_selected  # the single tiny-source candidate must be picked, not starved


def test_diverse_batch_respects_limit() -> None:
    candidates = [_cand(i, "A") for i in range(1, 51)]
    selected = approval_script.select_diverse_batch(candidates, limit=25)
    assert len(selected) == 25


def test_diverse_batch_returns_all_when_fewer_than_limit() -> None:
    candidates = [_cand(1, "A"), _cand(2, "B")]
    selected = approval_script.select_diverse_batch(candidates, limit=25)
    assert sorted(selected) == [1, 2]


def test_diverse_batch_empty_candidates_returns_empty() -> None:
    assert approval_script.select_diverse_batch([], limit=25) == []


def test_diverse_batch_deterministic() -> None:
    candidates = [_cand(3, "B"), _cand(1, "A"), _cand(2, "A"), _cand(5, "C"), _cand(4, "B")]
    first = approval_script.select_diverse_batch(list(candidates), limit=3)
    second = approval_script.select_diverse_batch(list(candidates), limit=3)
    assert first == second


def test_diverse_batch_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError):
        approval_script.select_diverse_batch([_cand(1, "A")], limit=0)


def test_diverse_batch_no_duplicate_ids() -> None:
    candidates = [_cand(i, "A" if i % 2 == 0 else "B") for i in range(1, 21)]
    selected = approval_script.select_diverse_batch(candidates, limit=15)
    assert len(selected) == len(set(selected))


# ---------------------------------------------------------------------------
# fetch_eligible_candidates + main() -- fake Supabase client, no network
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, table, rows) -> None:
        self._table = table
        self._rows = rows
        self._eq: dict = {}
        self._is_null: set = set()
        self._in: dict = {}

    def select(self, _cols):
        return self

    def eq(self, key, value):
        self._eq[key] = value
        return self

    def is_(self, key, _value):
        self._is_null.add(key)
        return self

    def in_(self, key, values):
        self._in[key] = set(values)
        return self

    def execute(self):
        rows = self._rows
        rows = [r for r in rows if all(r.get(k) == v for k, v in self._eq.items())]
        rows = [r for r in rows if all(r.get(k) is None for k in self._is_null)]
        rows = [r for r in rows if all(r.get(k) in v for k, v in self._in.items())]
        return _FakeResponse(rows)


class _FakeRpcCall:
    def __init__(self, recorder, name, params, response_rows) -> None:
        recorder.append((name, params))
        self._response_rows = response_rows

    def execute(self):
        return _FakeResponse(self._response_rows)


class _FakeClient:
    def __init__(self, tables: dict[str, list[dict]], rpc_response_rows=None) -> None:
        self._tables = tables
        self.rpc_calls: list = []
        self._rpc_response_rows = rpc_response_rows or []

    def table(self, name):
        return _FakeQuery(name, self._tables.get(name, []))

    def rpc(self, name, params):
        return _FakeRpcCall(self.rpc_calls, name, params, self._rpc_response_rows)


def _make_fixture_tables():
    units = [
        {"id": 1, "status": "needs_review", "qa_status": "passed", "title_hu": "T1",
         "modern_hu_text": "M1", "summary_hu": "S1", "human_reviewed_at": None, "story_id": 10},
        {"id": 2, "status": "needs_review", "qa_status": "passed", "title_hu": "T2",
         "modern_hu_text": "M2", "summary_hu": "S2", "human_reviewed_at": None, "story_id": 11},
        # ineligible: needs_attention
        {"id": 3, "status": "needs_review", "qa_status": "needs_attention", "title_hu": "T3",
         "modern_hu_text": "M3", "summary_hu": "S3", "human_reviewed_at": None, "story_id": 12},
        # ineligible: already human reviewed
        {"id": 4, "status": "approved", "qa_status": "passed", "title_hu": "T4",
         "modern_hu_text": "M4", "summary_hu": "S4", "human_reviewed_at": "2026-01-01T00:00:00Z", "story_id": 13},
    ]
    stories = [
        {"id": 10, "source_id": 100}, {"id": 11, "source_id": 101},
        {"id": 12, "source_id": 100}, {"id": 13, "source_id": 100},
    ]
    sources = [
        {"id": 100, "code": "SRC_A", "license_status": "public_domain_confirmed"},
        {"id": 101, "code": "SRC_B", "license_status": "public_domain_confirmed"},
    ]
    return {"illustration_units": units, "illustration_stories": stories, "illustration_sources": sources}


def test_fetch_eligible_candidates_filters_correctly() -> None:
    client = _FakeClient(_make_fixture_tables())
    candidates = approval_script.fetch_eligible_candidates(client)
    ids = sorted(c["id"] for c in candidates)
    assert ids == [1, 2]  # units 3 (needs_attention) and 4 (already human-reviewed / not needs_review) excluded


def test_fetch_eligible_candidates_excludes_non_publishable_license() -> None:
    tables = _make_fixture_tables()
    tables["illustration_sources"][0]["license_status"] = "restricted"
    client = _FakeClient(tables)
    candidates = approval_script.fetch_eligible_candidates(client)
    ids = sorted(c["id"] for c in candidates)
    assert 1 not in ids  # unit 1's source is now restricted
    assert 2 in ids


def test_main_dry_run_never_calls_rpc(monkeypatch, capsys) -> None:
    client = _FakeClient(_make_fixture_tables())
    monkeypatch.setattr(
        "illustration_engine.supabase_review_client.get_service_role_client_for_migration",
        lambda: client,
    )
    monkeypatch.setattr(sys, "argv", ["apply_automated_corpus_approval.py"])

    exit_code = approval_script.main()

    assert exit_code == 0
    assert client.rpc_calls == []
    captured = capsys.readouterr()
    assert "dry-run" in captured.out.lower()


def test_main_apply_calls_rpc_with_selected_batch(monkeypatch) -> None:
    rpc_response = [
        {"unit_id": 1, "outcome": "published", "detail": "corpus_qa_passed_v1"},
        {"unit_id": 2, "outcome": "published", "detail": "corpus_qa_passed_v1"},
    ]
    client = _FakeClient(_make_fixture_tables(), rpc_response_rows=rpc_response)
    monkeypatch.setattr(
        "illustration_engine.supabase_review_client.get_service_role_client_for_migration",
        lambda: client,
    )
    monkeypatch.setattr(sys, "argv", ["apply_automated_corpus_approval.py", "--apply", "--limit", "10"])

    exit_code = approval_script.main()

    assert exit_code == 0
    assert len(client.rpc_calls) == 1
    rpc_name, rpc_params = client.rpc_calls[0]
    assert rpc_name == "apply_automated_corpus_approval_v1"
    assert sorted(rpc_params["p_unit_ids"]) == [1, 2]


def test_main_apply_respects_limit(monkeypatch) -> None:
    tables = _make_fixture_tables()
    # add more eligible units across more sources
    for i in range(5, 15):
        tables["illustration_units"].append({
            "id": i, "status": "needs_review", "qa_status": "passed", "title_hu": f"T{i}",
            "modern_hu_text": f"M{i}", "summary_hu": f"S{i}", "human_reviewed_at": None, "story_id": 10,
        })
    client = _FakeClient(tables, rpc_response_rows=[])
    monkeypatch.setattr(
        "illustration_engine.supabase_review_client.get_service_role_client_for_migration",
        lambda: client,
    )
    monkeypatch.setattr(sys, "argv", ["apply_automated_corpus_approval.py", "--apply", "--limit", "3"])

    approval_script.main()

    rpc_name, rpc_params = client.rpc_calls[0]
    assert len(rpc_params["p_unit_ids"]) == 3
