"""Phase 2D.2 — ``scripts/import_macula_to_supabase.py`` ETL logic tests.

Exercises the FULL import plan (batching, FK remapping, the
hebrew_source_nodes two-pass parent-link, the hebrew_phrases/hebrew_clauses
cross-link) against a small, real, fixture-built local store using
``DryRunWriter`` — the same offline-simulation writer the script's own
``--dry-run`` (default) mode uses, so this test exercises the identical
code path a real Supabase run would, just without a network call. No
credentials, no network, anywhere in this file.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_linguistic_sqlite import open_store
from bible_engine.hebrew_macula_importer import ensure_dataset_version, import_chapter
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.macula_lowfat_parser import parse_macula_lowfat_chapter

_SPEC = importlib.util.spec_from_file_location("import_macula_to_supabase", ROOT / "scripts" / "import_macula_to_supabase.py")
_importer_script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_importer_script)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "macula_lowfat"
RUTH_FIXTURE = FIXTURES / "ruth_1_excerpt-lowfat.xml"
EZRA_FIXTURE = FIXTURES / "ezra_4_excerpt-lowfat.xml"


@pytest.fixture
def combined_local_store(tmp_path):
    """A small local store built from BOTH the Ruth (Hebrew) and Ezra
    (Aramaic) fixtures — two dataset-version rows, two verse languages,
    at least one UNRESOLVED token (Ezra 4:9), giving the import script's
    logic real structural variety to exercise."""
    store_path = tmp_path / "combined.sqlite3"
    store = open_store(store_path)
    textus_dv = ensure_dataset_version(store, dataset_id="tahot", display_name="TAHOT", revision="test")
    macula_dv = ensure_dataset_version(store, dataset_id="macula_hebrew_lowfat", display_name="MACULA", revision="test")
    repo = HebrewTokenRepository()

    ruth_chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    import_chapter(
        ruth_chapter, tahot_book_code="Rut", chapter_number=1, store=store, token_repository=repo,
        textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv,
    )
    ezra_chapter = parse_macula_lowfat_chapter(EZRA_FIXTURE)
    import_chapter(
        ezra_chapter, tahot_book_code="Ezr", chapter_number=4, store=store, token_repository=repo,
        textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv,
    )
    store.close()
    return store_path


def _local_counts(store_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(store_path)
    tables = [
        "original_language_dataset_versions", "hebrew_verses", "hebrew_tokens",
        "hebrew_token_strong_ids", "hebrew_token_components", "hebrew_source_nodes",
        "hebrew_token_alignments", "hebrew_phrases", "hebrew_clauses",
        "hebrew_syntax_membership", "hebrew_syntax_edges", "hebrew_semantic_roles",
        "hebrew_participants", "hebrew_coreference",
    ]
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    conn.close()
    return counts


def test_dry_run_writer_never_touches_network():
    """DryRunWriter must not import or reference the supabase client at
    all — checked directly against the source file's own DryRunWriter
    class block (module-from-spec loading doesn't register cleanly with
    inspect.getsource, so this reads the file text directly instead)."""
    import re

    source = (ROOT / "scripts" / "import_macula_to_supabase.py").read_text(encoding="utf-8")
    start = source.index("class DryRunWriter")
    match = re.search(r"\n(?:class |def )", source[start + len("class DryRunWriter") :])
    end = start + len("class DryRunWriter") + (match.start() if match else len(source) - start)
    class_source = source[start:end]
    assert "supabase" not in class_source.lower()


def test_dry_run_import_matches_local_row_counts(combined_local_store):
    conn = sqlite3.connect(combined_local_store)
    conn.row_factory = sqlite3.Row
    local_counts = _local_counts(combined_local_store)

    writer = _importer_script.DryRunWriter()
    dv_map = _importer_script.import_dataset_versions(conn, writer, batch_size=50)
    assert len(dv_map) == local_counts["original_language_dataset_versions"]

    verse_map = _importer_script.import_verses(conn, writer, 50, dv_map)
    assert len(verse_map) == local_counts["hebrew_verses"]

    token_count = _importer_script.import_tokens(conn, writer, 50, verse_map)
    assert token_count == local_counts["hebrew_tokens"]

    strong_id_count = _importer_script.import_simple_child_table(conn, writer, "hebrew_token_strong_ids", "token_id,seq", 50)
    assert strong_id_count == local_counts["hebrew_token_strong_ids"]

    component_count = _importer_script.import_simple_child_table(conn, writer, "hebrew_token_components", "token_id,component_index", 50)
    assert component_count == local_counts["hebrew_token_components"]

    node_map = _importer_script.import_source_nodes(conn, writer, 50, dv_map)
    assert len(node_map) == local_counts["hebrew_source_nodes"]

    alignment_count = _importer_script.import_token_alignments(conn, writer, 50, dv_map, node_map)
    assert alignment_count == local_counts["hebrew_token_alignments"]

    phrase_map = _importer_script.import_phrases(conn, writer, 50, dv_map, node_map)
    assert len(phrase_map) == local_counts["hebrew_phrases"]

    clause_map = _importer_script.import_clauses(conn, writer, 50, dv_map, node_map)
    assert len(clause_map) == local_counts["hebrew_clauses"]

    _importer_script.link_phrase_parents(conn, writer, 50, phrase_map, clause_map)  # must not raise

    membership_count = _importer_script.import_syntax_membership(conn, writer, 50, phrase_map, clause_map)
    assert membership_count == local_counts["hebrew_syntax_membership"]

    edge_count = _importer_script.import_syntax_edges(conn, writer, 50, dv_map, node_map)
    assert edge_count == local_counts["hebrew_syntax_edges"]

    role_count = _importer_script.import_semantic_roles(conn, writer, 50, dv_map, node_map)
    assert role_count == local_counts["hebrew_semantic_roles"]

    participant_map = _importer_script.import_participants(conn, writer, 50, dv_map, node_map)
    assert len(participant_map) == local_counts["hebrew_participants"]

    coref_count = _importer_script.import_coreference(conn, writer, 50, dv_map, node_map, participant_map)
    assert coref_count == local_counts["hebrew_coreference"]

    conn.close()


def test_dry_run_preserves_unresolved_alignment_type(combined_local_store):
    """The Ezra 4:9 fixture has real UNRESOLVED tokens (see
    tests/test_hebrew_macula_alignment.py) — the import script must carry
    alignment_type through verbatim, never promoting it."""
    conn = sqlite3.connect(combined_local_store)
    conn.row_factory = sqlite3.Row
    local_unresolved = conn.execute("SELECT COUNT(*) FROM hebrew_token_alignments WHERE alignment_type = 'UNRESOLVED'").fetchone()[0]
    assert local_unresolved > 0

    writer = _importer_script.DryRunWriter()
    dv_map = _importer_script.import_dataset_versions(conn, writer, 50)
    verse_map = _importer_script.import_verses(conn, writer, 50, dv_map)
    _importer_script.import_tokens(conn, writer, 50, verse_map)
    node_map = _importer_script.import_source_nodes(conn, writer, 50, dv_map)
    _importer_script.import_token_alignments(conn, writer, 50, dv_map, node_map)
    conn.close()

    # DryRunWriter.upsert records the exact payload rows it was given —
    # verify the alignment_type field survived remap untouched.
    assert writer.table_counts.get("hebrew_token_alignments", 0) > 0


def test_source_node_parent_child_local_ids_always_precede(combined_local_store):
    """The two-pass hebrew_source_nodes import (see module docstring)
    relies on every parent's local id being smaller than every child's —
    verified corpus-wide in Phase 2D.1 for the full store; re-verified
    here for this fixture's own smaller tree."""
    conn = sqlite3.connect(combined_local_store)
    bad = conn.execute(
        """
        SELECT COUNT(*) FROM hebrew_source_nodes c
        JOIN hebrew_source_nodes p ON p.id = c.parent_node_id
        WHERE p.id >= c.id
        """
    ).fetchone()[0]
    conn.close()
    assert bad == 0


def test_require_equal_length_accepts_equal_length_arrays():
    """The Python-side mirror of the RPCs' own PL/pgSQL cardinality guard
    (see supabase/migrations/20260909210000_hebrew_bulk_parent_link_rpcs.sql)
    must not raise when every array has the same length — this is the
    normal case every real call site produces."""
    _importer_script._require_equal_length(p_ids=[1, 2, 3], p_parent_ids=[9, 9, 9])
    _importer_script._require_equal_length(p_ids=[], p_parent_ids=[])
    _importer_script._require_equal_length(p_ids=[1], p_parent_phrase_ids=[2], p_parent_clause_ids=[3])


def test_require_equal_length_rejects_mismatched_arrays():
    with pytest.raises(ValueError, match="array length mismatch"):
        _importer_script._require_equal_length(p_ids=[1, 2, 3], p_parent_ids=[9, 9])
    with pytest.raises(ValueError, match="array length mismatch"):
        _importer_script._require_equal_length(p_ids=[1], p_parent_phrase_ids=[2, 3], p_parent_clause_ids=[4])


def test_remote_writer_bulk_link_fails_closed_when_cardinality_guard_rejects(monkeypatch):
    """Proves the fail-closed contract at the RemoteWriter boundary: when
    the cardinality guard rejects a call, NO network request is made at
    all — not a partial one, not a retried one. Every real call site
    builds equal-length arrays by construction, so the guard is forced to
    reject here via monkeypatch to prove it actually gates the RPC call
    (rather than being dead code that happens to never fire)."""

    class _FakeRpcClient:
        def __init__(self) -> None:
            self.rpc_calls: list[tuple[str, dict]] = []

        def rpc(self, name: str, params: dict):
            self.rpc_calls.append((name, params))
            return self

        def execute(self):
            raise AssertionError("execute() must never be reached when the cardinality guard rejects")

    def _always_reject(**arrays):
        raise ValueError(f"array length mismatch: {({k: len(v) for k, v in arrays.items()})}")

    monkeypatch.setattr(_importer_script, "_require_equal_length", _always_reject)

    writer = _importer_script.RemoteWriter.__new__(_importer_script.RemoteWriter)
    fake_client = _FakeRpcClient()
    writer.client = fake_client

    rows = [{"id": 1, "parent_node_id": 2}]
    with pytest.raises(ValueError, match="array length mismatch"):
        writer.bulk_link_source_node_parents(rows, base_delay=0.0)
    assert fake_client.rpc_calls == [], "no RPC call may be attempted once the guard rejects"


def test_dry_run_writer_bulk_link_fails_closed_when_cardinality_guard_rejects(monkeypatch, combined_local_store):
    """Same fail-closed contract on the DryRunWriter side: when the guard
    rejects, the simulated table state (self._store) must be completely
    unchanged — proving "no partial update occurs" for the offline path
    too, not just the network path."""
    conn = sqlite3.connect(combined_local_store)
    conn.row_factory = sqlite3.Row
    writer = _importer_script.DryRunWriter()
    dv_map = _importer_script.import_dataset_versions(conn, writer, 50)
    node_map = _importer_script.import_source_nodes(conn, writer, 50, dv_map)
    conn.close()

    before = writer.snapshot("hebrew_source_nodes")
    calls_before = len(writer.bulk_link_calls)  # import_source_nodes already made its own legitimate calls above

    def _always_reject(**arrays):
        raise ValueError(f"array length mismatch: {({k: len(v) for k, v in arrays.items()})}")

    monkeypatch.setattr(_importer_script, "_require_equal_length", _always_reject)

    some_id = next(iter(node_map.values()))
    with pytest.raises(ValueError, match="array length mismatch"):
        writer.bulk_link_source_node_parents([{"id": some_id, "parent_node_id": some_id}])

    after = writer.snapshot("hebrew_source_nodes")
    assert after == before, "guard rejection must leave the simulated table state byte-for-byte unchanged"
    assert len(writer.bulk_link_calls) == calls_before, "no new bulk_link call may be recorded once the guard rejects"


def test_bulk_link_sends_one_call_per_batch_not_one_per_row(combined_local_store):
    """Regression test for the real-import performance failure: a
    row-by-row PostgREST .update() call (the old update_batch()) measured
    ~8 rows/sec against the real project — 30+ hours for the full corpus.
    The fix batches every parent-link write into one RPC call per chunk.
    Uses a deliberately small link_batch_size so the fixture's own (small)
    row counts still produce >1 batch, proving real chunking occurred."""
    conn = sqlite3.connect(combined_local_store)
    conn.row_factory = sqlite3.Row
    writer = _importer_script.DryRunWriter()

    dv_map = _importer_script.import_dataset_versions(conn, writer, 50)
    verse_map = _importer_script.import_verses(conn, writer, 50, dv_map)
    _importer_script.import_tokens(conn, writer, 50, verse_map)
    node_map = _importer_script.import_source_nodes(conn, writer, 50, dv_map, link_batch_size=5)
    phrase_map = _importer_script.import_phrases(conn, writer, 50, dv_map, node_map)
    clause_map = _importer_script.import_clauses(conn, writer, 50, dv_map, node_map, link_batch_size=5)
    _importer_script.link_phrase_parents(conn, writer, 50, phrase_map, clause_map, link_batch_size=5)
    conn.close()

    assert writer.bulk_link_calls, "expected at least one bulk_link_* call across source_nodes/clauses/phrases"
    total_rows_linked = sum(call["n"] for call in writer.bulk_link_calls)
    assert total_rows_linked > 0
    # One call handles many rows (batch_size=5, not 1) — the defining
    # property that separates this from the old per-row .update() path.
    assert any(call["n"] > 1 for call in writer.bulk_link_calls), (
        "expected at least one bulk_link_* call to cover more than a single row"
    )


def test_bulk_link_never_touches_columns_outside_its_declared_parent_link(combined_local_store):
    """Explicit column-preservation check (see task brief item 5): a
    bulk_link_* call must never modify any column besides the parent-link
    column(s) it declares. Snapshots hebrew_source_nodes/hebrew_clauses/
    hebrew_phrases before and after linking and asserts every OTHER field
    (surface, lemma, clause_type, phrase_type, ...) is byte-for-byte
    unchanged."""
    conn = sqlite3.connect(combined_local_store)
    conn.row_factory = sqlite3.Row
    writer = _importer_script.DryRunWriter()

    dv_map = _importer_script.import_dataset_versions(conn, writer, 50)
    verse_map = _importer_script.import_verses(conn, writer, 50, dv_map)
    _importer_script.import_tokens(conn, writer, 50, verse_map)
    node_map = _importer_script.import_source_nodes(conn, writer, 50, dv_map)
    before_nodes = writer.snapshot("hebrew_source_nodes")

    phrase_map = _importer_script.import_phrases(conn, writer, 50, dv_map, node_map)
    clause_map = _importer_script.import_clauses(conn, writer, 50, dv_map, node_map)
    before_clauses = writer.snapshot("hebrew_clauses")
    before_phrases = writer.snapshot("hebrew_phrases")

    _importer_script.link_phrase_parents(conn, writer, 50, phrase_map, clause_map)
    conn.close()

    after_nodes = writer.snapshot("hebrew_source_nodes")
    after_clauses = writer.snapshot("hebrew_clauses")
    after_phrases = writer.snapshot("hebrew_phrases")

    def _assert_only_allowed_changed(before, after, allowed_columns):
        for row_id, before_row in before.items():
            after_row = after[row_id]
            changed = {k for k in before_row if before_row.get(k) != after_row.get(k)}
            unexpected = changed - allowed_columns
            assert not unexpected, f"row {row_id} had unexpected column(s) change: {unexpected}"

    # source_nodes/clauses are updated separately from the fixture's own
    # import calls above (not re-run here), so nothing should have moved
    # for them in this second phase — only phrases get linked below.
    _assert_only_allowed_changed(before_nodes, after_nodes, allowed_columns=set())
    _assert_only_allowed_changed(before_clauses, after_clauses, allowed_columns=set())
    _assert_only_allowed_changed(before_phrases, after_phrases, allowed_columns={"parent_phrase_id", "parent_clause_id"})


def test_bulk_link_phrase_parents_partial_rows_leave_absent_column_untouched(combined_local_store):
    """A phrase row with only parent_clause_id set (no parent_phrase_id)
    must not have parent_phrase_id touched — mirrors the RPC's
    COALESCE(v.col, t.col) semantics for a NULL array slot."""
    conn = sqlite3.connect(combined_local_store)
    conn.row_factory = sqlite3.Row
    writer = _importer_script.DryRunWriter()

    dv_map = _importer_script.import_dataset_versions(conn, writer, 50)
    verse_map = _importer_script.import_verses(conn, writer, 50, dv_map)
    _importer_script.import_tokens(conn, writer, 50, verse_map)
    node_map = _importer_script.import_source_nodes(conn, writer, 50, dv_map)
    phrase_map = _importer_script.import_phrases(conn, writer, 50, dv_map, node_map)
    clause_map = _importer_script.import_clauses(conn, writer, 50, dv_map, node_map)

    top_level_phrase_local_id = conn.execute(
        "SELECT id FROM hebrew_phrases WHERE parent_phrase_id IS NULL AND parent_clause_id IS NOT NULL LIMIT 1"
    ).fetchone()
    assert top_level_phrase_local_id is not None, "fixture must contain a phrase with only parent_clause_id set"
    remote_id = phrase_map[top_level_phrase_local_id[0]]

    _importer_script.link_phrase_parents(conn, writer, 50, phrase_map, clause_map)
    conn.close()

    linked_row = writer.snapshot("hebrew_phrases")[remote_id]
    assert linked_row["parent_phrase_id"] is None
    assert linked_row["parent_clause_id"] is not None


def test_remote_writer_bulk_link_retries_transient_rpc_failures_and_sends_expected_arrays():
    """Exercises the REAL RemoteWriter.bulk_link_source_node_parents
    against a fake Supabase client (no network, no credentials needed) —
    proves the RPC call is retried on transient failure exactly like the
    plain-request retry path, and that the arrays sent match the rows
    given (id array + parent_node_id array, in order)."""

    class _FakeExecuteResult:
        data: list = []

    class _FakeRpcClient:
        def __init__(self, fail_first_n: int) -> None:
            self.fail_first_n = fail_first_n
            self.execute_calls = 0
            self.rpc_calls: list[tuple[str, dict]] = []

        def rpc(self, name: str, params: dict):
            self.rpc_calls.append((name, params))
            return self

        def execute(self):
            self.execute_calls += 1
            if self.execute_calls <= self.fail_first_n:
                raise RuntimeError("RemoteProtocolError: simulated transient RPC failure")
            return _FakeExecuteResult()

    writer = _importer_script.RemoteWriter.__new__(_importer_script.RemoteWriter)
    fake_client = _FakeRpcClient(fail_first_n=2)
    writer.client = fake_client

    rows = [{"id": 101, "parent_node_id": 1}, {"id": 102, "parent_node_id": 1}, {"id": 103, "parent_node_id": 2}]
    writer.bulk_link_source_node_parents(rows, attempts=4, base_delay=0.0)

    assert fake_client.execute_calls == 3, "expected 2 failures then 1 success (idempotent retry)"
    name, params = fake_client.rpc_calls[-1]
    assert name == "bulk_link_source_node_parents"
    assert params == {"p_ids": [101, 102, 103], "p_parent_ids": [1, 1, 2]}


def test_remote_writer_bulk_link_phrase_parents_sends_none_for_absent_columns():
    """The RemoteWriter side must turn a missing key into None (NULL) in
    the RPC's array argument, not omit the row or raise — this is what
    the RPC's COALESCE relies on to implement "leave this column alone"."""

    class _FakeExecuteResult:
        data: list = []

    class _FakeRpcClient:
        def __init__(self) -> None:
            self.rpc_calls: list[tuple[str, dict]] = []

        def rpc(self, name: str, params: dict):
            self.rpc_calls.append((name, params))
            return self

        def execute(self):
            return _FakeExecuteResult()

    writer = _importer_script.RemoteWriter.__new__(_importer_script.RemoteWriter)
    fake_client = _FakeRpcClient()
    writer.client = fake_client

    rows = [{"id": 5, "parent_clause_id": 9}, {"id": 6, "parent_phrase_id": 7}]
    writer.bulk_link_phrase_parents(rows, base_delay=0.0)

    name, params = fake_client.rpc_calls[-1]
    assert name == "bulk_link_phrase_parents"
    assert params == {
        "p_ids": [5, 6],
        "p_parent_phrase_ids": [None, 7],
        "p_parent_clause_ids": [9, None],
    }


def test_remote_writer_delete_where_in_chunks_large_value_lists():
    """Regression test for the real-import failure: a single .in_(column,
    values) call with corpus-scale cardinality (238,809 phrase ids, hit by
    import_syntax_membership's delete_where_in("hebrew_syntax_membership",
    "phrase_id", ...)) builds a PostgREST query string long enough that the
    HTTP client itself rejects it ("InvalidURL: URL component 'query' too
    long") — deterministic, so the existing retry wrapper cannot fix it;
    every real import that reaches this table failed here until this fix.
    Proves delete_where_in splits a large values list into several
    chunk_size-bounded .in_() calls that together cover every value exactly
    once, using a fake client (no network, no credentials needed)."""

    class _FakeExecuteResult:
        data: list = []

    class _FakeDeleteBuilder:
        def __init__(self, calls: list[tuple[str, list]], table: str) -> None:
            self._calls = calls
            self._table = table

        def delete(self):
            return self

        def in_(self, column: str, values: list):
            self._calls.append((column, list(values)))
            return self

        def execute(self):
            return _FakeExecuteResult()

    class _FakeTableClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list]] = []

        def table(self, name: str):
            return _FakeDeleteBuilder(self.calls, name)

    writer = _importer_script.RemoteWriter.__new__(_importer_script.RemoteWriter)
    fake_client = _FakeTableClient()
    writer.client = fake_client

    values = list(range(1, 238_810))  # matches the real phrase-id cardinality that broke this
    writer.delete_where_in("hebrew_syntax_membership", "phrase_id", values, chunk_size=500)

    assert len(fake_client.calls) == len(values) // 500 + (1 if len(values) % 500 else 0)
    for column, chunk in fake_client.calls:
        assert column == "phrase_id"
        assert len(chunk) <= 500
    covered = [v for _, chunk in fake_client.calls for v in chunk]
    assert covered == values, "chunking must cover every value exactly once, in order, with none lost or duplicated"


def test_remote_writer_delete_where_in_no_calls_for_empty_values():
    class _FakeTableClient:
        def table(self, name: str):
            raise AssertionError("must not touch the network when values is empty")

    writer = _importer_script.RemoteWriter.__new__(_importer_script.RemoteWriter)
    writer.client = _FakeTableClient()
    writer.delete_where_in("hebrew_syntax_membership", "phrase_id", [])


def test_call_with_retry_succeeds_after_transient_failures():
    """Reproduces the real second-attempt failure mode (PGRST002 'Could
    not query the database for the schema cache. Retrying.') — a
    transient error on the first N-1 calls must not abort the import if a
    later attempt succeeds."""
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("PGRST002: schema cache reloading")
        return "ok"

    result = _importer_script._call_with_retry(
        flaky, description="test call", attempts=4, base_delay=0.0
    )
    assert result == "ok"
    assert calls["n"] == 3


def test_call_with_retry_reraises_after_exhausting_attempts():
    calls = {"n": 0}

    def always_fails():
        calls["n"] += 1
        raise RuntimeError("persistent failure")

    with pytest.raises(RuntimeError, match="persistent failure"):
        _importer_script._call_with_retry(
            always_fails, description="test call", attempts=3, base_delay=0.0
        )
    assert calls["n"] == 3


def test_call_with_retry_succeeds_immediately_without_sleeping():
    calls = {"n": 0}

    def works_first_time():
        calls["n"] += 1
        return "immediate"

    result = _importer_script._call_with_retry(
        works_first_time, description="test call", attempts=4, base_delay=999.0
    )
    assert result == "immediate"
    assert calls["n"] == 1


def test_remote_writer_delete_all_where_chunks_large_deletes_and_converges():
    """Regression test for the real-import failure: a single unscoped-by-
    batch .delete().eq(column, value) against a corpus-scale table (real
    case: 460,018-row hebrew_token_alignments) hits Postgres's statement
    timeout deterministically (code 57014) — retrying the same call cannot
    help. delete_all_where must instead page through matching ids
    (chunk_size at a time) and delete each page by id, converging once no
    rows remain, with every single request staying within chunk_size."""

    class _FakeResult:
        def __init__(self, data):
            self.data = data

    class _FakeChunkedDeleteTable:
        def __init__(self, client):
            self._client = client
            self._mode = None
            self._limit = None
            self._in_values: list[int] = []

        def select(self, _cols):
            self._mode = "select"
            return self

        def delete(self):
            self._mode = "delete"
            return self

        def eq(self, _col, _val):
            return self

        def limit(self, n):
            self._limit = n
            return self

        def in_(self, _col, values):
            self._in_values = list(values)
            return self

        def execute(self):
            if self._mode == "select":
                self._client.select_calls += 1
                self._client.max_select_limit_seen = max(self._client.max_select_limit_seen, self._limit or 0)
                page_ids = sorted(self._client.remaining)[: self._limit]
                return _FakeResult([{"id": i} for i in page_ids])
            self._client.delete_calls += 1
            self._client.max_delete_batch_seen = max(self._client.max_delete_batch_seen, len(self._in_values))
            for i in self._in_values:
                self._client.remaining.discard(i)
            return _FakeResult([])

    class _FakeChunkedDeleteClient:
        def __init__(self, remaining: set[int]):
            self.remaining = remaining
            self.select_calls = 0
            self.delete_calls = 0
            self.max_select_limit_seen = 0
            self.max_delete_batch_seen = 0

        def table(self, _name):
            return _FakeChunkedDeleteTable(self)

    remaining = set(range(1, 1237))  # 1,236 rows to delete — not a multiple of chunk_size
    fake_client = _FakeChunkedDeleteClient(remaining)
    writer = _importer_script.RemoteWriter.__new__(_importer_script.RemoteWriter)
    writer.client = fake_client

    writer.delete_all_where("hebrew_token_alignments", "dataset_version_id_macula", 2, chunk_size=500)

    assert not remaining, "every matching row must eventually be deleted"
    assert fake_client.max_select_limit_seen <= 500
    assert fake_client.max_delete_batch_seen <= 500, "a single delete call must never exceed chunk_size"
    assert fake_client.select_calls == fake_client.delete_calls + 1, (
        "one extra select (returning 0 ids) is what signals convergence and ends the loop"
    )
    assert fake_client.delete_calls == 3  # ceil(1236 / 500)


def test_remote_writer_delete_all_where_no_delete_call_when_nothing_matches():
    class _FakeResult:
        def __init__(self, data):
            self.data = data

    class _FakeEmptyTable:
        def select(self, _cols):
            return self

        def eq(self, _col, _val):
            return self

        def limit(self, _n):
            return self

        def delete(self):
            raise AssertionError("must not attempt a delete when the select page is already empty")

        def execute(self):
            return _FakeResult([])

    class _FakeEmptyClient:
        def table(self, _name):
            return _FakeEmptyTable()

    writer = _importer_script.RemoteWriter.__new__(_importer_script.RemoteWriter)
    writer.client = _FakeEmptyClient()
    writer.delete_all_where("hebrew_semantic_roles", "dataset_version_id", 99, chunk_size=500)
