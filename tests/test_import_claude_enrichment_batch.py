"""Targeted tests for scripts/import_claude_enrichment_batch.py -- the
minimal, insert-or-skip importer that moves validated Claude-authored
enrichment records from a local SQLite export into production Supabase.
A fake Supabase client (same pattern as tests/test_retrieval.py's
_FakeSupabaseClient) stands in for the real one -- no network access,
no LLM call anywhere in this file or the module under test."""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import import_claude_enrichment_batch as importer  # noqa: E402

from illustration_engine.illustration_sqlite import create_schema, insert_source, insert_story  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: a real local SQLite story (via the real schema helpers, not a
# hand-rolled parallel schema) + a valid enrichment record for it.
# ---------------------------------------------------------------------------


def _make_local_db(tmp_path: Path, *, original_text: str = "Egy rövid teszt sztori szövege.") -> tuple[str, int]:
    db_path = tmp_path / "local.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    source_id = insert_source(
        conn, code="TEST_SOURCE", title="Test Source", orig_language="en",
        license_status="public_domain_confirmed", license_basis_hu="x",
        reliability_tier="high", tradition="tradition",
    )
    story_id = insert_story(
        conn, source_id=source_id, external_ref="1", canonical_key="001",
        title_original="Test Story", adaptation_status="verbatim_transcription",
        original_text=original_text,
        original_text_checksum=hashlib.sha256(original_text.encode("utf-8")).hexdigest(),
    )
    conn.commit()
    conn.close()
    return str(db_path), story_id


def _valid_record(story_id: int) -> dict:
    return {
        "story_id": story_id,
        "title_hu": "Teszt cím",
        "modern_hu_text": "Ez egy teszt magyar szöveg, elég hosszú ahhoz, hogy érvényes legyen.",
        "summary_hu": " ".join(["szo"] * 45),
        "moral_hu": "Teszt tanulság.",
        "derivation_type": "full_story_translation",
        "narrative_status": "traditional_anecdote",
        "narrative_status_confidence": "medium",
        "status": "needs_review",
        "human_reviewed_at": None,
        "enrichment_model": "claude-manual-enrichment-test",
        "enrichment_prompt_version": "hu_illustration_enrichment_pilot_v1",
        "enrichment_generated_at": "2026-09-13T00:00:00+00:00",
        "enrichment_warnings_json": None,
        "tags": [
            {"category": "topic", "slug": "buszkeseg"},
            {"category": "tone", "slug": "ironikus"},
            {"category": "function", "slug": "ellenpelda"},
        ],
    }


# ---------------------------------------------------------------------------
# Fake Supabase client -- same table().select().eq().limit().execute() /
# table().insert().execute() shape the real script calls.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, client: "_FakeSupabaseClient", name: str) -> None:
        self._client = client
        self._name = name
        self._filters: dict[str, object] = {}
        self._limit: int | None = None
        self._pending_insert: list[dict] | None = None

    def select(self, _cols: str) -> "_FakeTable":
        return self

    def eq(self, col: str, val: object) -> "_FakeTable":
        self._filters[col] = val
        return self

    def limit(self, n: int) -> "_FakeTable":
        self._limit = n
        return self

    def insert(self, rows: dict | list[dict]) -> "_FakeTable":
        self._client.mutations.append(("insert", self._name, rows))
        self._pending_insert = [rows] if isinstance(rows, dict) else list(rows)
        return self

    def execute(self) -> _FakeResponse:
        if self._pending_insert is not None:
            inserted = []
            for row in self._pending_insert:
                row = dict(row)
                if "id" not in row:
                    self._client.next_id += 1
                    row["id"] = self._client.next_id
                self._client.data.setdefault(self._name, []).append(row)
                inserted.append(row)
            return _FakeResponse(inserted)

        rows = self._client.data.get(self._name, [])
        matched = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
        if self._limit is not None:
            matched = matched[: self._limit]
        return _FakeResponse(matched)


class _FakeSupabaseClient:
    def __init__(self, initial_data: dict[str, list[dict]] | None = None) -> None:
        self.data: dict[str, list[dict]] = {k: list(v) for k, v in (initial_data or {}).items()}
        self.mutations: list[tuple] = []
        self.next_id = 10_000

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self, name)


def _seeded_client(*, with_existing_unit: bool = False) -> _FakeSupabaseClient:
    data = {
        "illustration_sources": [{"id": 1, "code": "TEST_SOURCE"}],
        "illustration_stories": [{"id": 501, "source_id": 1, "canonical_key": "001"}],
        "illustration_tags": [
            {"id": 1, "category": "topic", "slug": "buszkeseg"},
            {"id": 2, "category": "tone", "slug": "ironikus"},
            {"id": 3, "category": "function", "slug": "ellenpelda"},
        ],
        "illustration_units": [],
    }
    if with_existing_unit:
        data["illustration_units"] = [{"id": 999, "story_id": 501, "unit_index": 1}]
    return _FakeSupabaseClient(data)


# ---------------------------------------------------------------------------
# 1. valid JSON importálható
# ---------------------------------------------------------------------------


def test_valid_record_is_importable_in_dry_run(tmp_path) -> None:
    db_path, story_id = _make_local_db(tmp_path)
    client = _seeded_client()

    counts = importer.run_import([_valid_record(story_id)], local_db_path=db_path, client=client, apply=False)

    assert counts == {"importable": 1, "duplicates": 0, "validation_errors": 0, "imported": 0}


def test_apply_actually_inserts_unit_and_tags(tmp_path) -> None:
    db_path, story_id = _make_local_db(tmp_path)
    client = _seeded_client()

    counts = importer.run_import([_valid_record(story_id)], local_db_path=db_path, client=client, apply=True)

    assert counts == {"importable": 1, "duplicates": 0, "validation_errors": 0, "imported": 1}
    units = client.data["illustration_units"]
    assert len(units) == 1
    assert units[0]["status"] == "needs_review"
    assert units[0].get("human_reviewed_at") is None
    assert units[0]["story_id"] == 501
    tag_links = client.data["illustration_unit_tags"]
    assert {t["tag_id"] for t in tag_links} == {1, 2, 3}
    assert all(t["unit_id"] == units[0]["id"] for t in tag_links)


# ---------------------------------------------------------------------------
# 2. invalid rekordot elutasít
# ---------------------------------------------------------------------------


def test_invalid_record_missing_modern_hu_text_is_rejected(tmp_path) -> None:
    db_path, story_id = _make_local_db(tmp_path)
    client = _seeded_client()
    record = _valid_record(story_id)
    record["modern_hu_text"] = ""

    counts = importer.run_import([record], local_db_path=db_path, client=client, apply=True)

    assert counts["validation_errors"] == 1
    assert counts["imported"] == 0
    assert client.mutations == []  # never even reached the write path


def test_invalid_record_bad_taxonomy_topic_is_rejected(tmp_path) -> None:
    db_path, story_id = _make_local_db(tmp_path)
    client = _seeded_client()
    record = _valid_record(story_id)
    record["tags"] = [{"category": "topic", "slug": "nem_letezo_temacimke"}]

    counts = importer.run_import([record], local_db_path=db_path, client=client, apply=True)

    assert counts["validation_errors"] == 1
    assert counts["imported"] == 0


def test_record_with_unresolvable_tag_in_production_is_rejected_not_silently_dropped(tmp_path) -> None:
    """A tag that passes local taxonomy validation but has no matching
    row in production illustration_tags must fail closed, never be
    silently skipped from the tag list."""
    db_path, story_id = _make_local_db(tmp_path)
    client = _seeded_client()
    client.data["illustration_tags"] = []  # production has no tags at all
    record = _valid_record(story_id)

    counts = importer.run_import([record], local_db_path=db_path, client=client, apply=True)

    assert counts["validation_errors"] == 1
    assert counts["imported"] == 0
    assert client.data["illustration_units"] == []


def test_story_not_found_in_production_is_rejected(tmp_path) -> None:
    db_path, story_id = _make_local_db(tmp_path)
    client = _seeded_client()
    client.data["illustration_stories"] = []  # production has no matching story

    counts = importer.run_import([_valid_record(story_id)], local_db_path=db_path, client=client, apply=True)

    assert counts["validation_errors"] == 1
    assert client.data["illustration_units"] == []


# ---------------------------------------------------------------------------
# 3. duplicate import idempotens / nem duplikál
# ---------------------------------------------------------------------------


def test_duplicate_story_unit_is_skipped_never_reimported(tmp_path) -> None:
    db_path, story_id = _make_local_db(tmp_path)
    client = _seeded_client(with_existing_unit=True)

    counts = importer.run_import([_valid_record(story_id)], local_db_path=db_path, client=client, apply=True)

    assert counts == {"importable": 0, "duplicates": 1, "validation_errors": 0, "imported": 0}
    assert len(client.data["illustration_units"]) == 1  # still just the pre-existing row
    assert client.mutations == []  # no insert attempted at all


def test_running_import_twice_is_idempotent(tmp_path) -> None:
    db_path, story_id = _make_local_db(tmp_path)
    client = _seeded_client()

    first = importer.run_import([_valid_record(story_id)], local_db_path=db_path, client=client, apply=True)
    second = importer.run_import([_valid_record(story_id)], local_db_path=db_path, client=client, apply=True)

    assert first["imported"] == 1
    assert second["imported"] == 0
    assert second["duplicates"] == 1
    assert len(client.data["illustration_units"]) == 1


# ---------------------------------------------------------------------------
# 4. dry-run nem ír
# ---------------------------------------------------------------------------


def test_dry_run_never_writes_to_supabase(tmp_path) -> None:
    db_path, story_id = _make_local_db(tmp_path)
    client = _seeded_client()

    importer.run_import([_valid_record(story_id)], local_db_path=db_path, client=client, apply=False)

    assert client.mutations == []
    assert client.data["illustration_units"] == []
    assert "illustration_unit_tags" not in client.data


# ---------------------------------------------------------------------------
# 5. service-role kliens használata
# ---------------------------------------------------------------------------


def test_main_uses_service_role_client_not_anon(tmp_path, monkeypatch) -> None:
    db_path, story_id = _make_local_db(tmp_path)
    export_path = tmp_path / "export.json"
    import json as _json

    export_path.write_text(_json.dumps([_valid_record(story_id)]), encoding="utf-8")

    calls: list[str] = []

    def fake_service_role_client() -> _FakeSupabaseClient:
        calls.append("service_role")
        return _seeded_client()

    def fake_anon_client() -> None:
        calls.append("anon")
        raise AssertionError("must never use the anon client for a write path")

    import illustration_engine.supabase_review_client as review_client_module

    monkeypatch.setattr(review_client_module, "get_service_role_client_for_migration", fake_service_role_client)
    monkeypatch.setattr("supabase_client.get_supabase_client", fake_anon_client, raising=False)
    monkeypatch.setattr(sys, "argv", ["import_claude_enrichment_batch.py", "--json", str(export_path), "--local-db", db_path])

    importer.main()

    assert calls == ["service_role"]


# ---------------------------------------------------------------------------
# 6. Gemini/API hívás nincs
# ---------------------------------------------------------------------------


def test_importer_source_never_references_gemini_or_other_llm_apis() -> None:
    source = (REPO_ROOT / "scripts" / "import_claude_enrichment_batch.py").read_text(encoding="utf-8")
    forbidden = (
        "generativelanguage.googleapis", "GEMINI_API_KEY", "genai",
        "anthropic.Anthropic", "llm_generate", "openai",
    )
    for token in forbidden:
        assert token not in source, f"importer script must never reference {token!r}"
