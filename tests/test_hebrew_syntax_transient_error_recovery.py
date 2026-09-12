"""2026-09 audit fix — regression coverage for the Hebrew syntax-repository
result-state bug: a transient Supabase/RPC failure on
``SupabaseHebrewAnalysisRepository.get_verse_syntax`` used to be
indistinguishable from a verse that genuinely has no MACULA syntax data,
and the degraded ``HebrewAnalysisBundle`` this produced was cached by
``CachedHebrewAnalysisService`` exactly like a normal successful result —
so a single momentary outage silently and permanently (for the rest of the
Streamlit session) hid syntax data for that verse, even after the backend
recovered.

This file proves the fix end to end:

1. dataset/version lookup succeeds (``dataset_version_signature()``);
2. the first ``get_verse_syntax`` RPC call fails transiently;
3. the resulting bundle is NOT cached as a success;
4. the backend "recovers" (the fake client answers normally again);
5. the very next request reaches the repository again (not a stale hit);
6. that request succeeds and IS cached.

No real network access or Supabase credentials anywhere in this file — same
fake-Postgrest-client convention as
``tests/test_hebrew_analysis_repository_supabase.py``.
"""

from __future__ import annotations

import bible_engine.hebrew_analysis_repository as repo_module
from bible_engine.hebrew_analysis_cache import CachedHebrewAnalysisService
from bible_engine.hebrew_analysis_repository import SupabaseHebrewAnalysisRepository
from bible_engine.hebrew_analysis_service import HebrewAnalysisService


class _FakeResponse:
    def __init__(self, data) -> None:
        self.data = data


class _FakeVersionQuery:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def select(self, _columns: str) -> "_FakeVersionQuery":
        return self

    def eq(self, _key: str, _value: object) -> "_FakeVersionQuery":
        return self

    def execute(self) -> _FakeResponse:
        return _FakeResponse(self._rows)


class _FakeRpcQuery:
    """Mirrors the real client's ``.rpc(name, params)`` return shape — a
    builder object with its own ``.execute()``, not the response itself
    (the real chain is ``client.rpc(...).execute().data``)."""

    def __init__(self, client: "_FlakyThenHealthyClient") -> None:
        self._client = client

    def execute(self) -> _FakeResponse:
        self._client.rpc_call_count += 1
        if self._client._remaining_failures > 0:
            self._client._remaining_failures -= 1
            raise RuntimeError("simulated transient Supabase/RPC outage")
        return _FakeResponse(self._client._healthy_payload)


class _FlakyThenHealthyClient:
    """A Supabase project whose dataset/version metadata is always
    reachable (step 1), but whose verse-syntax RPC fails transiently on its
    first ``fail_times`` calls before recovering (steps 2 and 4)."""

    def __init__(self, *, fail_times: int, healthy_payload: dict) -> None:
        self._remaining_failures = fail_times
        self._healthy_payload = healthy_payload
        self.rpc_call_count = 0

    def table(self, name: str):
        assert name == "original_language_dataset_versions"
        return _FakeVersionQuery([{"dataset_id": "tahot", "revision": "test-rev-1"}])

    def rpc(self, name: str, params: dict) -> _FakeRpcQuery:
        assert name == "get_verse_syntax_bundle"
        return _FakeRpcQuery(self)


def _ruth_1_1_payload() -> dict:
    return {
        "phrases": [
            {"id": 1, "phrase_type": "np", "head_token_id": None, "parent_phrase_id": None},
        ],
        "clauses": [],
        "membership": [{"token_id": "Ruth.1.1:4", "phrase_id": 1, "clause_id": None}],
        "edges": [],
        "roles": [],
        "participants": [],
        "coreference": [],
        "grounding_status": "FULLY_GROUNDED_SYNTAX",
    }


def test_hebrew_repository_distinguishes_transient_error_from_recovered_success(monkeypatch):
    """Repository-level: the core distinction the whole fix hinges on — a
    transient RPC failure must carry a different status AND a different
    syntax_grounding than a genuinely empty verse, and a subsequent call
    (backend recovered) must reach the RPC again and succeed."""
    client = _FlakyThenHealthyClient(fail_times=1, healthy_payload=_ruth_1_1_payload())
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    repository = SupabaseHebrewAnalysisRepository()

    # Step 1: dataset/version lookup succeeds.
    assert repository.dataset_version_signature() == "tahot:test-rev-1"

    # Step 2: first verse-syntax RPC call hits a transient failure.
    transient = repository.get_verse_syntax("Ruth.1.1")
    assert transient.status == repo_module.RESULT_TRANSIENT_ERROR
    assert transient.syntax_grounding == repo_module.SYNTAX_GROUNDING_UNAVAILABLE
    assert not transient.has_syntax

    # Steps 4-5: backend has recovered, next call reaches the repository
    # again (nothing here is cached at the repository layer) and succeeds.
    recovered = repository.get_verse_syntax("Ruth.1.1")
    assert recovered.status == repo_module.RESULT_SUCCESS_WITH_DATA
    assert recovered.syntax_grounding == repo_module.SYNTAX_GROUNDING_FULL
    assert recovered.has_syntax
    assert client.rpc_call_count == 2


def test_hebrew_bundle_cache_never_poisons_on_transient_error_then_recovers(monkeypatch):
    """Full steps 1-6 at the CachedHebrewAnalysisService boundary: a
    transient failure must never be cached, so the very next request for
    the same reference reaches the repository again instead of replaying a
    stale, degraded result — and once the backend has recovered, THAT
    request succeeds and is cached normally."""
    client = _FlakyThenHealthyClient(fail_times=1, healthy_payload=_ruth_1_1_payload())
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: client)

    service = HebrewAnalysisService(linguistic_repository=SupabaseHebrewAnalysisRepository())
    cache = CachedHebrewAnalysisService(service)

    # Step 2: first request hits the transient RPC failure for Ruth 1:1.
    degraded = cache.get_hebrew_analysis("Rut 1,1")
    degraded_verse = next(v for v in degraded.verses if v.verse_id == "Ruth.1.1")
    assert degraded_verse.syntax_grounding == repo_module.SYNTAX_GROUNDING_UNAVAILABLE

    # Step 3: the degraded bundle must never be cached as a success.
    assert cache.cache_size() == 0

    # Steps 4-5: backend has "recovered" (the flaky client now answers
    # normally); because nothing was cached, this call reaches the
    # repository again rather than replaying the degraded bundle.
    recovered = cache.get_hebrew_analysis("Rut 1,1")
    recovered_verse = next(v for v in recovered.verses if v.verse_id == "Ruth.1.1")

    # Step 6: the successful, recovered syntax data is now processed and
    # cached — same-session recovery, no restart needed.
    assert recovered_verse.syntax_grounding == repo_module.SYNTAX_GROUNDING_FULL
    assert recovered_verse.phrases
    assert cache.cache_size() == 1
    assert client.rpc_call_count == 2

    # A third call must be a pure cache hit — no further RPC calls.
    cache.get_hebrew_analysis("Rut 1,1")
    assert client.rpc_call_count == 2
