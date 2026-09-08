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

    def select(self, _columns: str) -> "_FakeQuery":
        return self

    def eq(self, key: str, value) -> "_FakeQuery":
        self._eq_filters[key] = value
        return self

    def in_(self, key: str, values: list) -> "_FakeQuery":
        self._in_filters[key] = values
        return self

    def execute(self) -> _FakeResponse:
        matches = [
            row
            for row in self._table.rows
            if all(row.get(k) == v for k, v in self._eq_filters.items())
            and all(row.get(k) in values for k, values in self._in_filters.items())
        ]
        return _FakeResponse(matches)


class _FakeTable:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def select(self, columns: str) -> _FakeQuery:
        return _FakeQuery(self).select(columns)


class _FakeClient:
    def __init__(self, data: dict[str, list[dict]]) -> None:
        self._data = data

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self._data.get(name, []))


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


def test_supabase_repository_fail_closed_on_missing_client(monkeypatch):
    def _raise():
        raise RuntimeError("no credentials configured")

    monkeypatch.setattr("supabase_client.get_supabase_client", _raise)
    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert syntax.phrases == ()
    assert not syntax.has_syntax


def test_supabase_repository_fail_closed_on_query_error(monkeypatch):
    class _ExplodingClient:
        def table(self, _name: str):
            raise RuntimeError("network error")

    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _ExplodingClient())
    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.1.1")
    assert not syntax.has_syntax


def test_supabase_repository_empty_verse_returns_empty_syntax_data(monkeypatch):
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _FakeClient({}))
    repository = SupabaseHebrewAnalysisRepository()
    syntax = repository.get_verse_syntax("Ruth.9.9")
    assert syntax.phrases == ()
    assert syntax.clauses == ()
    assert syntax.semantic_roles == ()
