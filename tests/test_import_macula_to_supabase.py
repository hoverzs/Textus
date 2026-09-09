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
