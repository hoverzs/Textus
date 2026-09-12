"""2026-09 audit fix — regression coverage for the Greek syntax-repository
result-state bug: a transient Supabase/RPC failure on
``SupabaseGreekAnalysisRepository.get_verse_syntax`` used to be
indistinguishable from a verse that genuinely has no MACULA syntax data,
and ``_attach_verse``/``request_greek_contextual_analysis`` would happily
build (and the AI cache would happily store) a normal ``STATUS_OK`` result
on top of that silently degraded input.

This mirrors ``tests/test_hebrew_syntax_transient_error_recovery.py``
exactly, adapted to Greek's actual architecture (no deterministic-bundle
cache on the Greek side — ``attach_syntax_via_repository`` runs fresh on
every call — so the "must not cache a transient failure" requirement lands
entirely on ``GreekContextualAnalysisCache``/``request_greek_contextual_
analysis``, which is what the third test below proves):

1. the verse-syntax RPC succeeds normally today (baseline real data);
2. the first RPC call fails transiently;
3. neither the attached bundle nor any AI result is cached as a success;
4. the backend "recovers" (the fake client answers normally again);
5. the very next request reaches the repository/model again;
6. that request succeeds and, at the AI layer, IS cached.

No real network access, Supabase credentials, or paid AI calls anywhere in
this file — ``SupabaseGreekAnalysisRepository`` takes an injectable
``client=`` here, and ``generate_fn`` is a local fake.
"""

from __future__ import annotations

from bible_engine.greek_analysis_bundle import SYNTAX_GROUNDING_FULL, SYNTAX_GROUNDING_UNAVAILABLE
from bible_engine.greek_analysis_repository import (
    RESULT_SUCCESS_WITH_DATA,
    RESULT_TRANSIENT_ERROR,
    SupabaseGreekAnalysisRepository,
    attach_syntax_via_repository,
)
from bible_engine.greek_analysis_service import get_greek_analysis
from bible_engine.greek_contextual_analysis_cache import (
    GreekContextualAnalysisCache,
    get_or_request_greek_contextual_analysis,
)
from bible_engine.greek_contextual_analysis_service import STATUS_OK, STATUS_UNAVAILABLE

_VERSE_REF = "Jhn.3.16"
_REFERENCE = "Jn 3,16"


class _FakeResponse:
    def __init__(self, data: dict) -> None:
        self.data = data


class _FakeRpcQuery:
    """Mirrors the real client's ``.rpc(name, params)`` return shape — a
    builder object with its own ``.execute()`` (the real chain is
    ``client.rpc(...).execute().data``)."""

    def __init__(self, client: "_FlakyThenHealthyClient") -> None:
        self._client = client

    def execute(self) -> _FakeResponse:
        self._client.rpc_call_count += 1
        if self._client._remaining_failures > 0:
            self._client._remaining_failures -= 1
            raise RuntimeError("simulated transient Supabase/RPC outage")
        return _FakeResponse(self._client._healthy_payload)


class _FlakyThenHealthyClient:
    """The verse-syntax RPC fails transiently on its first ``fail_times``
    calls before recovering (steps 2 and 4/5)."""

    def __init__(self, *, fail_times: int, healthy_payload: dict) -> None:
        self._remaining_failures = fail_times
        self._healthy_payload = healthy_payload
        self.rpc_call_count = 0

    def rpc(self, name: str, params: dict) -> _FakeRpcQuery:
        assert name == "get_greek_verse_syntax_bundle"
        return _FakeRpcQuery(self)


def _healthy_payload_for(token_ids: list[str]) -> dict:
    """A minimal, fully-resolved syntax bundle for every real token of the
    verse — enough for ``_attach_verse`` to compute SYNTAX_GROUNDING_FULL,
    mirroring what a genuinely successful RPC response looks like."""
    return {
        "phrases": [
            {"id": 1, "phrase_type": "np", "head_token_id": None, "parent_phrase_id": None, "role": None, "parent_clause_id": None},
        ],
        "clauses": [],
        "membership": [{"phrase_id": 1, "clause_id": None, "token_id": token_ids[0]}],
        "semantic_roles": [],
        "coreference": [],
        "tokens": [{"token_id": tid, "alignment_status": "EXACT"} for tid in token_ids],
    }


def test_greek_repository_distinguishes_transient_error_from_recovered_success():
    """Repository-level: the core distinction the fix hinges on."""
    bare_bundle = get_greek_analysis(_REFERENCE)
    token_ids = [t.token_id for t in bare_bundle.verses[0].tokens]
    client = _FlakyThenHealthyClient(fail_times=1, healthy_payload=_healthy_payload_for(token_ids))
    repository = SupabaseGreekAnalysisRepository(client=client)

    # Step 2: first verse-syntax RPC call hits a transient failure.
    transient = repository.get_verse_syntax(_VERSE_REF)
    assert transient.status == RESULT_TRANSIENT_ERROR
    assert not transient.has_syntax

    # Steps 4-5: backend has recovered, next call reaches the RPC again and
    # succeeds (nothing here is cached at the repository layer).
    recovered = repository.get_verse_syntax(_VERSE_REF)
    assert recovered.status == RESULT_SUCCESS_WITH_DATA
    assert recovered.has_syntax
    assert client.rpc_call_count == 2


def test_greek_attach_syntax_marks_unavailable_then_recovers_to_full_grounding():
    """``attach_syntax_via_repository`` must never present a transient
    failure as SYNTAX_GROUNDING_NONE (indistinguishable from genuine
    absence) — and once the backend recovers, grounding must reflect the
    real, fully-resolved data."""
    bundle = get_greek_analysis(_REFERENCE)
    token_ids = [t.token_id for t in bundle.verses[0].tokens]
    client = _FlakyThenHealthyClient(fail_times=1, healthy_payload=_healthy_payload_for(token_ids))
    repository = SupabaseGreekAnalysisRepository(client=client)

    degraded = attach_syntax_via_repository(bundle, repository)
    assert degraded.verses[0].syntax_grounding == SYNTAX_GROUNDING_UNAVAILABLE

    recovered = attach_syntax_via_repository(bundle, repository)
    assert recovered.verses[0].syntax_grounding == SYNTAX_GROUNDING_FULL
    assert client.rpc_call_count == 2


def test_greek_contextual_analysis_never_calls_model_or_caches_on_transient_error_then_recovers():
    """Full steps 1-6 at the AI-contextual-analysis boundary: a verse whose
    syntax fetch failed transiently must never reach the model (wasted AI
    cost on a known-degraded input) and must never be cached as
    STATUS_OK — the next request for the same verse must retry and, once
    the backend has recovered, succeed and be cached normally."""
    bundle = get_greek_analysis(_REFERENCE)
    token_ids = [t.token_id for t in bundle.verses[0].tokens]
    client = _FlakyThenHealthyClient(fail_times=1, healthy_payload=_healthy_payload_for(token_ids))
    repository = SupabaseGreekAnalysisRepository(client=client)

    cache = GreekContextualAnalysisCache()
    model_calls: list[str] = []

    def fake_generate(prompt: str, **_kwargs) -> str:
        model_calls.append(prompt)
        return (
            '{"word_notes": [], "construction_notes": [], "syntax_summary": {}, '
            '"translation_notes": [], "exegetical_notes": [], "warnings": []}'
        )

    # Step 2: syntax attachment hits the transient RPC failure.
    degraded_verse = attach_syntax_via_repository(bundle, repository).verses[0]
    result = get_or_request_greek_contextual_analysis(
        degraded_verse, dataset_version_signature="test-sig", model_id="test-model",
        generate_fn=fake_generate, cache=cache,
    )
    assert result.status == STATUS_UNAVAILABLE
    assert model_calls == []  # never wastes an AI call on a known-degraded verse
    assert cache.cache_size() == 0  # step 3: never cached as a success

    # Steps 4-5: backend has "recovered"; nothing was cached, so this
    # request reaches syntax attachment (and, since grounding is now real,
    # the model) again rather than replaying the degraded result.
    recovered_verse = attach_syntax_via_repository(bundle, repository).verses[0]
    result2 = get_or_request_greek_contextual_analysis(
        recovered_verse, dataset_version_signature="test-sig", model_id="test-model",
        generate_fn=fake_generate, cache=cache,
    )

    # Step 6: the successful, recovered analysis is processed and cached.
    assert result2.status == STATUS_OK
    assert len(model_calls) == 1
    assert cache.cache_size() == 1
    assert client.rpc_call_count == 2

    # A third call for the same verse must be a pure cache hit.
    get_or_request_greek_contextual_analysis(
        recovered_verse, dataset_version_signature="test-sig", model_id="test-model",
        generate_fn=fake_generate, cache=cache,
    )
    assert len(model_calls) == 1
