"""Phase 2D — ``SupabaseHebrewAnalysisRepository`` backend tests.

Same fake-Postgrest-client pattern as
``tests/test_textus_kb/test_commentary_translation_store_supabase.py`` — a
minimal fake stands in for the real ``supabase`` package. No real network
access anywhere in this file, and no production credentials are needed or
used: ``bible_engine.hebrew_analysis_repository.SupabaseHebrewAnalysisRepository``
has NOT been exercised against any real Supabase project from this
environment — see docs/hebrew_analysis_v2_phase2d.md §15/§16 for what
still needs to run against the real project.
"""

from __future__ import annotations

import bible_engine.hebrew_analysis_repository as repository_module
from bible_engine.hebrew_analysis_repository import SupabaseHebrewAnalysisRepository


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, table: "_FakeTable") -> None:
        self._table = table
        self._eq_filters: dict[str, object] = {}
        self._in_filters: dict[str, list] = {}
        self._limit: int | None = None

    def select(self, _columns: str) -> "_FakeQuery":
        return self

    def eq(self, key: str, value) -> "_FakeQuery":
        self._eq_filters[key] = value
        return self

    def in_(self, key: str, values: list) -> "_FakeQuery":
        self._in_filters[key] = values
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def execute(self) -> _FakeResponse:
        matches = [
            row
            for row in self._table.rows
            if all(row.get(k) == v for k, v in self._eq_filters.items())
            and all(row.get(k) in values for k, values in self._in_filters.items())
        ]
        if self._limit is not None:
            matches = matches[: self._limit]
        return _FakeResponse(matches)


class _FakeTable:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def select(self, columns: str) -> _FakeQuery:
        return _FakeQuery(self).select(columns)


def _fake_verse_syntax_bundle(tables: dict[str, list[dict]], verse_ref: str) -> dict:
    """Pure-Python mirror of get_verse_syntax_bundle's SQL (see
    supabase/migrations/20260910120000_hebrew_verse_syntax_bundle_rpc.sql)
    — same filtering/column-shape logic, computed from the fake tables
    instead of a real Postgres query, so these tests still need no
    network/credentials."""
    # Sorted to mirror the RPC's own explicit ORDER BY inside each
    # jsonb_agg (deterministic output) — not required for correctness
    # (_assemble_from_rows is order-independent) but keeps this fake
    # faithful to the real SQL.
    phrases = sorted((r for r in tables.get("hebrew_phrases", []) if r.get("verse_ref") == verse_ref), key=lambda r: r["id"])
    clauses = sorted((r for r in tables.get("hebrew_clauses", []) if r.get("verse_ref") == verse_ref), key=lambda r: r["id"])
    phrase_ids = {r["id"] for r in phrases}
    clause_ids = {r["id"] for r in clauses}
    # No sort key here (unlike the others): the real SQL orders membership
    # by its own `id` column (insertion order) — see the migration's
    # comment on why token_id (a "verse:word" TEXT column) sorts wrong
    # lexicographically. These hand-written fixtures don't carry an `id`
    # field, so preserving the literal list order IS the fixture's
    # intended (already-correct) insertion order.
    membership = [
        r for r in tables.get("hebrew_syntax_membership", [])
        if r.get("phrase_id") in phrase_ids or r.get("clause_id") in clause_ids
    ]
    edges = sorted((r for r in tables.get("hebrew_syntax_edges", []) if r.get("verse_ref") == verse_ref), key=lambda r: r["id"])
    roles = sorted((r for r in tables.get("hebrew_semantic_roles", []) if r.get("verse_ref") == verse_ref), key=lambda r: r["id"])
    participants = sorted((r for r in tables.get("hebrew_participants", []) if r.get("verse_ref") == verse_ref), key=lambda r: r["id"])
    coreference = sorted((r for r in tables.get("hebrew_coreference", []) if r.get("verse_ref") == verse_ref), key=lambda r: r["id"])
    grounding_rows = [r for r in tables.get("hebrew_verse_syntax_grounding", []) if r.get("verse_ref") == verse_ref]
    return {
        "phrases": [
            {"id": r["id"], "phrase_type": r.get("phrase_type"), "head_token_id": r.get("head_token_id"), "parent_phrase_id": r.get("parent_phrase_id")}
            for r in phrases
        ],
        "clauses": [
            {"id": r["id"], "clause_type": r.get("clause_type"), "predicate_token_id": r.get("predicate_token_id"), "subject_token_id": r.get("subject_token_id"), "parent_clause_id": r.get("parent_clause_id")}
            for r in clauses
        ],
        "membership": [{"token_id": r["token_id"], "phrase_id": r.get("phrase_id"), "clause_id": r.get("clause_id")} for r in membership],
        "edges": [
            {"id": r["id"], "relation_type": r.get("relation_type"), "source_role_code": r.get("source_role_code"), "parent_token_id": r.get("parent_token_id"), "child_token_id": r.get("child_token_id")}
            for r in edges
        ],
        "roles": [
            {"id": r["id"], "role_code": r.get("role_code"), "role_label": r.get("role_label"), "predicate_token_id": r.get("predicate_token_id"), "participant_token_id": r.get("participant_token_id")}
            for r in roles
        ],
        "participants": [{"id": r["id"], "token_id": r.get("token_id")} for r in participants],
        "coreference": [
            {"id": r["id"], "referring_token_id": r.get("referring_token_id"), "participant_id": r.get("participant_id"), "relation_type": r.get("relation_type")}
            for r in coreference
        ],
        "grounding_status": grounding_rows[0]["grounding_status"] if grounding_rows else None,
    }


class _FakeRpcResponse:
    def __init__(self, data: dict) -> None:
        self.data = data


class _FakeRpcQuery:
    """Mirrors the real client's ``.rpc(name, params)`` return shape —
    a builder object with its own ``.execute()``, not the response itself
    (matching every other fake query builder in this file)."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def execute(self) -> _FakeRpcResponse:
        return _FakeRpcResponse(self._data)


class _FakeClient:
    def __init__(self, data: dict[str, list[dict]]) -> None:
        self._data = data

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self._data.get(name, []))

    def rpc(self, name: str, params: dict) -> _FakeRpcQuery:
        assert name == "get_verse_syntax_bundle", f"unexpected RPC: {name}"
        return _FakeRpcQuery(_fake_verse_syntax_bundle(self._data, params["p_verse_ref"]))


def _seed_ruth_1_1_data() -> dict[str, list[dict]]:
    return {
        "hebrew_phrases": [
            {"id": 1, "phrase_type": "np", "head_token_id": None, "parent_phrase_id": None, "verse_ref": "Ruth.1.1"},
        ],
        "hebrew_clauses": [
            {"id": 1, "clause_type": "", "predicate_token_id": "Ruth.1.1:3", "subject_token_id": None, "parent_clause_id": None, "verse_ref": "Ruth.1.1"},
        ],
        "hebrew_syntax_membership": [
            {"token_id": "Ruth.1.1:4", "phrase_id": 1, "clause_id": None},
            {"token_id": "Ruth.1.1:3", "phrase_id": None, "clause_id": 1},
        ],
        "hebrew_syntax_edges": [
            {"id": 1, "relation_type": "predicate", "source_role_code": "v", "parent_token_id": None, "child_token_id": "Ruth.1.1:3", "verse_ref": "Ruth.1.1"},
        ],
        "hebrew_semantic_roles": [
            {"id": 1, "role_code": "A0", "role_label": "agent", "predicate_token_id": "Ruth.1.1:3", "participant_token_id": "Ruth.1.1:4", "verse_ref": "Ruth.1.1"},
        ],
        "hebrew_participants": [
            {"id": 1, "token_id": "Ruth.1.1:9", "verse_ref": "Ruth.1.1"},
        ],
        "hebrew_coreference": [
            {"id": 1, "referring_token_id": "Ruth.1.1:16", "participant_id": 1, "relation_type": "participantref", "verse_ref": "Ruth.1.1"},
        ],
        "hebrew_verses": [
            {"id": 100, "verse_ref": "Ruth.1.1"},
        ],
        "hebrew_tokens": [
            {"token_id": "Ruth.1.1:3", "verse_id": 100},
            {"token_id": "Ruth.1.1:4", "verse_id": 100},
        ],
        "hebrew_token_alignments": [
            {"token_id": "Ruth.1.1:3", "alignment_type": "EXACT"},
            {"token_id": "Ruth.1.1:4", "alignment_type": "COMPOSITE"},
        ],
    }


def test_supabase_repository_assembles_verse_syntax_from_fake_client(monkeypatch):
    fake_client = _FakeClient(_seed_ruth_1_1_data())
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: fake_client)

    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.1.1")

    assert len(syntax.phrases) == 1
    assert syntax.phrases[0].token_ids == ("Ruth.1.1:4",)
    assert len(syntax.clauses) == 1
    assert syntax.clauses[0].predicate_id == "Ruth.1.1:3"
    assert len(syntax.syntax_relations) == 1
    assert syntax.syntax_relations[0].relation_type == "predicate"
    assert len(syntax.semantic_roles) == 1
    assert syntax.semantic_roles[0].role_code == "A0"
    assert len(syntax.participants) == 1
    assert len(syntax.coreference) == 1
    assert syntax.has_syntax
    assert syntax.has_semantic_roles
    assert syntax.has_participants
    assert syntax.syntax_grounding == repository_module.SYNTAX_GROUNDING_FULL


def test_supabase_repository_partial_grounding_when_verse_has_an_unresolved_token(monkeypatch):
    """Phase 2D.1 §12: if even one token in the verse is UNRESOLVED, the
    verse's syntax_grounding must report PARTIALLY_GROUNDED_SYNTAX, not
    FULLY_GROUNDED_SYNTAX — even though the syntax facts that ARE present
    (for the confirmed tokens) are still returned."""
    data = _seed_ruth_1_1_data()
    data["hebrew_tokens"].append({"token_id": "Ruth.1.1:5", "verse_id": 100})
    data["hebrew_token_alignments"].append({"token_id": "Ruth.1.1:5", "alignment_type": "UNRESOLVED"})
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _FakeClient(data))

    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert syntax.has_syntax
    assert syntax.syntax_grounding == repository_module.SYNTAX_GROUNDING_PARTIAL


def test_supabase_repository_uses_grounding_view_when_available(monkeypatch):
    """Phase 2D.2: when the optional hebrew_verse_syntax_grounding view
    (migration 20260908223000) is present, its single-query result is used
    directly instead of the three-query fallback — verified here by
    seeding ONLY the view's own row, with hebrew_verses/hebrew_tokens/
    hebrew_token_alignments deliberately left empty so the fallback path
    would return the wrong answer (NO_GROUNDED_SYNTAX) if it were used
    instead of the view."""
    data = _seed_ruth_1_1_data()
    data["hebrew_verses"] = []
    data["hebrew_tokens"] = []
    data["hebrew_token_alignments"] = []
    data["hebrew_verse_syntax_grounding"] = [
        {"verse_ref": "Ruth.1.1", "grounding_status": "FULLY_GROUNDED_SYNTAX"},
    ]
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _FakeClient(data))

    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert syntax.syntax_grounding == repository_module.SYNTAX_GROUNDING_FULL


def test_supabase_repository_falls_back_when_grounding_view_absent(monkeypatch):
    """When the view is not present (e.g. only the base Phase 2D
    migration has been applied), the repository must fall back to the
    three-query path and still produce the correct answer — not fail
    closed just because the optional optimization is unavailable."""
    data = _seed_ruth_1_1_data()
    # no "hebrew_verse_syntax_grounding" key at all -> _FakeClient.table()
    # returns an empty table for it, exactly like querying a view that
    # doesn't exist yet would (Postgrest returns no rows / an error the
    # repository already treats the same way via its own try/except).
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _FakeClient(data))

    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert syntax.syntax_grounding == repository_module.SYNTAX_GROUNDING_FULL


def test_supabase_repository_fail_closed_on_missing_client(monkeypatch):
    def _raise():
        raise RuntimeError("no credentials configured")

    monkeypatch.setattr("supabase_client.get_supabase_client", _raise)
    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert syntax.phrases == ()
    assert not syntax.has_syntax
    # 2026-09 audit fix: "backend unreachable" is a TRANSIENT_ERROR, never a
    # normal (cacheable) empty result — see test_supabase_repository_
    # empty_verse_returns_empty_syntax_data below for the contrasting,
    # genuinely-empty case that must NOT carry this status.
    assert syntax.status == repository_module.RESULT_TRANSIENT_ERROR
    assert syntax.syntax_grounding == repository_module.SYNTAX_GROUNDING_UNAVAILABLE


def test_supabase_repository_fail_closed_on_query_error(monkeypatch):
    class _ExplodingClient:
        def table(self, _name: str):
            raise RuntimeError("network error")

        def rpc(self, _name: str, _params: dict):
            raise RuntimeError("network error")

    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _ExplodingClient())
    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert not syntax.has_syntax
    # 2026-09 audit fix: this is the exact case the prior audit flagged —
    # an RPC error must never be indistinguishable from a genuinely empty
    # verse (contrast with the "empty_verse" test below, which must NOT
    # carry TRANSIENT_ERROR even though both return zero phrases/clauses).
    assert syntax.status == repository_module.RESULT_TRANSIENT_ERROR
    assert syntax.syntax_grounding == repository_module.SYNTAX_GROUNDING_UNAVAILABLE


def test_supabase_repository_empty_verse_returns_empty_syntax_data(monkeypatch):
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _FakeClient({}))
    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.9.9")
    assert syntax.phrases == ()
    assert syntax.clauses == ()
    assert syntax.semantic_roles == ()
    # 2026-09 audit fix: a genuinely empty (but successfully queried) verse
    # must be SUCCESS_NO_DATA, never TRANSIENT_ERROR — this is the
    # distinction the two tests above depend on existing at all.
    assert syntax.status == repository_module.RESULT_SUCCESS_NO_DATA
    assert syntax.syntax_grounding == repository_module.SYNTAX_GROUNDING_NONE
