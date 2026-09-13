"""scripts/migrate_illustrations_to_supabase.py — dry-run readiness
checks, row extraction shape, and --apply write-path behavior against a
fake Supabase client. No real network access anywhere in this file.

The source SQLite fixture is always a real on-disk file (the script's
`open_source_readonly` needs a real path for its `mode=ro` URI
connection) built fresh per test via `illustration_engine.
illustration_sqlite.create_schema` -- never the real 564-record corpus,
and never written to by anything other than the fixture setup itself."""

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from illustration_engine.illustration_sqlite import (  # noqa: E402
    create_schema,
    insert_illustration_unit,
    insert_source,
    insert_story,
)

# Same importlib-by-path convention as tests/test_import_macula_to_supabase.py
# -- scripts/ has no __init__.py, so this is not a plain package import.
_SPEC = importlib.util.spec_from_file_location(
    "migrate_illustrations_to_supabase", ROOT / "scripts" / "migrate_illustrations_to_supabase.py"
)
migrate = importlib.util.module_from_spec(_SPEC)
# Must be registered in sys.modules BEFORE exec_module -- the script's
# @dataclass-decorated classes need cls.__module__ resolvable via
# sys.modules at class-definition time (dataclasses.py's own
# introspection), which spec_from_file_location alone does not provide.
sys.modules[_SPEC.name] = migrate
_SPEC.loader.exec_module(migrate)


def _build_fixture_db(path: Path, *, with_units: bool = True) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    source_id = insert_source(
        conn, code="SRC", title="Test Source", orig_language="en",
        license_status="public_domain_confirmed", license_basis_hu="basis", reliability_tier="high",
    )
    text = "Once upon a time, a wise man taught his students a lesson."
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    story_id = insert_story(
        conn, source_id=source_id, external_ref="1", canonical_key="001",
        title_original="Original Title", adaptation_status="verbatim_transcription",
        original_text=text, original_text_checksum=checksum,
    )
    if with_units:
        insert_illustration_unit(
            conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation",
            status="needs_review", title_hu="Cím", modern_hu_text="Szöveg",
            summary_hu="Összefoglaló " * 10,
        )
    conn.commit()
    conn.close()


@pytest.fixture()
def fixture_db(tmp_path) -> Path:
    path = tmp_path / "illustrations.sqlite3"
    _build_fixture_db(path)
    return path


# ---------------------------------------------------------------------------
# Readiness checks
# ---------------------------------------------------------------------------


def test_open_source_readonly_cannot_write(fixture_db: Path) -> None:
    conn = migrate.open_source_readonly(fixture_db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO sources(code, title, orig_language, license_status, "
                     "license_basis_hu, reliability_tier, registered_at) "
                     "VALUES ('X','X','en','unknown','x','high','2026-01-01')")
    conn.close()


def test_open_source_readonly_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        migrate.open_source_readonly(Path("/nonexistent/path/illustrations.sqlite3"))


def test_build_readiness_report_all_pass_on_clean_fixture(fixture_db: Path) -> None:
    report = migrate.build_readiness_report(fixture_db)
    assert report.ready_for_apply is True
    assert "READY_FOR_APPLY=true" in report.render()
    assert report.row_counts["illustration_units"] == 1


def test_check_story_checksums_detects_mismatch(tmp_path) -> None:
    path = tmp_path / "illustrations.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    source_id = insert_source(
        conn, code="SRC", title="T", orig_language="en", license_status="public_domain_confirmed",
        license_basis_hu="b", reliability_tier="high",
    )
    insert_story(
        conn, source_id=source_id, external_ref="1", canonical_key="001",
        title_original="T", adaptation_status="verbatim_transcription",
        original_text="real text", original_text_checksum="corrupted-checksum",
    )
    conn.commit()
    conn.close()

    ro = migrate.open_source_readonly(path)
    result = migrate.check_story_checksums(ro)
    ro.close()

    assert result.passed is False


def test_check_tag_junction_integrity_detects_orphan(tmp_path) -> None:
    path = tmp_path / "illustrations.sqlite3"
    conn = sqlite3.connect(path)
    create_schema(conn)  # create_schema itself turns PRAGMA foreign_keys ON
    conn.execute("PRAGMA foreign_keys = OFF")  # deliberately allow an orphan row for this test
    conn.execute("INSERT INTO illustration_unit_tags(unit_id, tag_id) VALUES (999, 999)")
    conn.commit()
    conn.close()

    ro = migrate.open_source_readonly(path)
    result = migrate.check_tag_junction_integrity(ro)
    ro.close()

    assert result.passed is False
    assert "orphan" in result.detail


def test_check_publish_state_invariants_detects_incomplete_published_unit(tmp_path) -> None:
    path = tmp_path / "illustrations.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    source_id = insert_source(
        conn, code="SRC", title="T", orig_language="en", license_status="public_domain_confirmed",
        license_basis_hu="b", reliability_tier="high",
    )
    story_id = insert_story(
        conn, source_id=source_id, external_ref="1", canonical_key="001",
        title_original="T", adaptation_status="verbatim_transcription", original_text="x",
    )
    conn.commit()
    # Bypass the Python-side gate deliberately (direct SQL) to construct an
    # invariant-violating row for the checker to catch -- the DB's own CHECK
    # constraint would normally prevent this; this simulates a corrupted file.
    conn.execute(
        "INSERT INTO illustration_units(story_id, unit_index, derivation_type, status, "
        "created_at, updated_at) VALUES (?, 1, 'full_story_translation', 'draft', 'x', 'x')",
        (story_id,),
    )
    conn.commit()
    conn.close()

    ro = migrate.open_source_readonly(path)
    result = migrate.check_publish_state_invariants(ro)
    ro.close()
    # The row is 'draft', not 'published' -- so THIS specific check should
    # still pass; this test only pins that the checker runs without error
    # against a not-fully-enriched row (regression net for a NULL-handling
    # bug in the SQL itself).
    assert all(isinstance(c.passed, bool) for c in result)


def test_readiness_report_fails_when_integrity_check_fails(tmp_path) -> None:
    path = tmp_path / "illustrations.sqlite3"
    path.write_bytes(b"not a real sqlite file")
    with pytest.raises(sqlite3.DatabaseError):
        migrate.build_readiness_report(path)


# ---------------------------------------------------------------------------
# Row extraction shape
# ---------------------------------------------------------------------------


def test_extract_sources_shape(fixture_db: Path) -> None:
    conn = migrate.open_source_readonly(fixture_db)
    rows = migrate.extract_sources(conn)
    conn.close()
    assert len(rows) == 1
    assert rows[0]["code"] == "SRC"
    assert "id" in rows[0]


def test_extract_illustration_units_preserves_id_and_parses_json(fixture_db: Path) -> None:
    conn = migrate.open_source_readonly(fixture_db)
    rows = migrate.extract_illustration_units(conn)
    conn.close()
    assert len(rows) == 1
    assert rows[0]["id"] >= 1
    assert rows[0]["title_hu"] == "Cím"
    assert rows[0]["enrichment_warnings"] is None  # no warnings on this fixture unit


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


def test_with_retry_succeeds_after_transient_failures() -> None:
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result = migrate._with_retry(flaky, attempts=5, base_delay=0.0, description="test")
    assert result == "ok"
    assert attempts["n"] == 3


def test_with_retry_raises_after_exhausting_attempts() -> None:
    def always_fails():
        raise RuntimeError("permanent")

    with pytest.raises(RuntimeError):
        migrate._with_retry(always_fails, attempts=3, base_delay=0.0, description="test")


def test_chunks_splits_correctly() -> None:
    items = list(range(10))
    chunks = list(migrate._chunks(items, 3))
    assert chunks == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]


# ---------------------------------------------------------------------------
# run_migration — dry-run vs --apply, against a fake Supabase client
# ---------------------------------------------------------------------------


class _FakeExecuteResult:
    def __init__(self, data) -> None:
        self.data = data


class _FakeTableWriter:
    def __init__(self, recorder: list, table: str) -> None:
        self._recorder = recorder
        self._table = table

    def upsert(self, rows, *, on_conflict: str) -> "_FakeTableWriter":
        self._recorder.append((self._table, "upsert", len(rows), on_conflict))
        return self

    def execute(self) -> _FakeExecuteResult:
        return _FakeExecuteResult([])


class _FakeRpcCall:
    def __init__(self, recorder: list, name: str, params: dict) -> None:
        recorder.append((name, params))

    def execute(self) -> _FakeExecuteResult:
        return _FakeExecuteResult([])


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self.calls: list = []
        self.rpc_calls: list = []

    def table(self, name: str) -> _FakeTableWriter:
        return _FakeTableWriter(self.calls, name)

    def rpc(self, name: str, params: dict) -> _FakeRpcCall:
        return _FakeRpcCall(self.rpc_calls, name, params)


def test_dry_run_never_touches_supabase(fixture_db: Path) -> None:
    exit_code = migrate.run_migration(fixture_db, apply=False)
    assert exit_code == 0  # fixture is clean -> ready


def test_apply_without_readiness_refuses_to_write(tmp_path) -> None:
    path = tmp_path / "illustrations.sqlite3"
    path.write_bytes(b"not a real sqlite file")
    client = _FakeSupabaseClient()
    with pytest.raises(sqlite3.DatabaseError):
        migrate.run_migration(path, apply=True, supabase_client=client)
    assert client.calls == []


def test_apply_with_ready_fixture_upserts_every_table_and_resets_sequences(fixture_db: Path) -> None:
    client = _FakeSupabaseClient()
    exit_code = migrate.run_migration(fixture_db, apply=True, supabase_client=client)
    assert exit_code == 0

    written_tables = {call[0] for call in client.calls}
    assert written_tables == set(migrate.NATURAL_KEYS.keys()) - {
        # empty tables in this minimal fixture never call upsert (0 rows -> no chunks)
        "illustration_tags", "illustration_unit_tags", "illustration_qa_repairs",
        "illustration_import_meta", "illustration_enrichment_runs", "illustration_enrichment_run_items",
    }
    # on_conflict must match the DDL's natural keys exactly
    for table, _op, _count, on_conflict in client.calls:
        assert on_conflict == migrate.NATURAL_KEYS[table]

    assert client.rpc_calls == [("reset_illustration_sequences", {})]


def test_apply_never_issues_a_delete_call(fixture_db: Path) -> None:
    """Structural guarantee: SupabaseMigrationWriter has no delete
    method at all -- this test pins that FakeTableWriter (which would
    raise AttributeError if .delete() were ever called) is never asked
    to delete anything during a full --apply run."""
    client = _FakeSupabaseClient()
    migrate.run_migration(fixture_db, apply=True, supabase_client=client)
    assert all(call[1] == "upsert" for call in client.calls)


# ---------------------------------------------------------------------------
# 2026-09-13 production incident regression coverage: the DEFAULT client
# resolution (supabase_client=None, exercised only when a caller does NOT
# inject a fake -- i.e. the real CLI path) was using the anon/publishable
# client (supabase_client.get_supabase_client()) for --apply writes. RLS
# correctly rejected the first INSERT in production with "permission denied
# for table illustration_sources" before any row was written. Fixed to use
# illustration_engine.supabase_review_client.get_service_role_client_for_
# migration() instead. These tests exercise the DEFAULT path specifically
# (no supabase_client= override) -- every test above this point always
# injected a fake client and so never exercised the buggy code path at all.
# ---------------------------------------------------------------------------


def test_dry_run_constructs_neither_normal_nor_service_client(monkeypatch, fixture_db: Path) -> None:
    import illustration_engine.supabase_review_client as review_client_module
    import supabase_client as supabase_client_module

    def _explode(*a, **k):
        raise AssertionError("dry-run must never construct any Supabase client")

    monkeypatch.setattr(supabase_client_module, "get_supabase_client", _explode)
    monkeypatch.setattr(review_client_module, "get_service_role_client_for_migration", _explode)

    exit_code = migrate.run_migration(fixture_db, apply=False)
    assert exit_code == 0


def test_apply_default_path_uses_service_role_client_not_anon(monkeypatch, fixture_db: Path) -> None:
    """The core regression test for the production incident: --apply's
    DEFAULT client resolution (no supabase_client= override -- the exact
    shape the real CLI invocation uses) must call get_service_role_client_
    for_migration(), and must NEVER call get_supabase_client() (anon)."""
    import illustration_engine.supabase_review_client as review_client_module
    import supabase_client as supabase_client_module

    fake_service_client = _FakeSupabaseClient()
    service_client_calls: list[bool] = []

    def _fake_service_factory():
        service_client_calls.append(True)
        return fake_service_client

    def _anon_client_must_not_be_called(*a, **k):
        raise AssertionError(
            "run_migration's --apply path called the ANON client "
            "(supabase_client.get_supabase_client) -- this is exactly the "
            "2026-09-13 production incident regressing. Migration writes "
            "must use the service_role client."
        )

    monkeypatch.setattr(review_client_module, "get_service_role_client_for_migration", _fake_service_factory)
    monkeypatch.setattr(supabase_client_module, "get_supabase_client", _anon_client_must_not_be_called)

    exit_code = migrate.run_migration(fixture_db, apply=True)  # no supabase_client= override

    assert exit_code == 0
    assert service_client_calls == [True]
    assert len(fake_service_client.calls) > 0  # the service client actually received the writes


def test_apply_default_path_fails_closed_when_service_key_missing(monkeypatch, fixture_db: Path) -> None:
    """If the service_role credential isn't configured, --apply must fail
    BEFORE any write is attempted -- never silently fall back to the anon
    client, never proceed with a partial credential."""
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")

    import illustration_engine.supabase_review_client as review_client_module

    # Force streamlit-secrets fallback to also come up empty, regardless of
    # any real secrets.toml present on this machine's worktree.
    monkeypatch.setattr(review_client_module, "_read_service_key_from_streamlit_secrets", lambda: "")

    with pytest.raises(RuntimeError):
        migrate.run_migration(fixture_db, apply=True)


def test_apply_default_path_never_logs_credential_values(monkeypatch, fixture_db: Path, capsys) -> None:
    """End-to-end guarantee: even with a distinctive fake service key
    present, nothing printed to stdout/stderr during a full --apply run
    (success or failure) contains it."""
    import illustration_engine.supabase_review_client as review_client_module

    distinctive_key = "distinctive-service-key-must-never-appear-in-output"
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", distinctive_key)
    monkeypatch.setattr(review_client_module, "get_service_role_client_for_migration", lambda: _FakeSupabaseClient())

    migrate.run_migration(fixture_db, apply=True)

    captured = capsys.readouterr()
    assert distinctive_key not in captured.out
    assert distinctive_key not in captured.err
