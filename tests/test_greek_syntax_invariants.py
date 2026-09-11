"""Phase 2B §4/§12 — corpus-wide invariants for the Greek syntax store.

Run against the actual built store (``data/generated/greek_syntax_dev.sqlite3``)
when present; skipped entirely in a checkout that hasn't run
``scripts/build_greek_syntax_store.py`` (the store is large and not
necessarily committed — see the phase doc §5).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

DB_PATH = resolve_default_syntax_database_path()
requires_syntax_store = pytest.mark.skipif(
    not DB_PATH.exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)


@pytest.fixture(scope="module")
def connection():
    conn = sqlite3.connect(DB_PATH)
    yield conn
    conn.close()


@requires_syntax_store
def test_total_tagnt_tokens_covered_by_exactly_one_alignment_row(connection) -> None:
    count = connection.execute("SELECT COUNT(*) FROM token_alignments").fetchone()[0]
    distinct = connection.execute("SELECT COUNT(DISTINCT tagnt_token_id) FROM token_alignments").fetchone()[0]
    assert count == 142096
    assert distinct == count  # no TAGNT token aligned twice


@requires_syntax_store
def test_unresolved_alignments_never_carry_a_macula_xml_id(connection) -> None:
    """Unresolved alignments must never silently receive syntax facts —
    verified at the source: an UNRESOLVED row's macula_xml_id is NULL."""
    rows = connection.execute(
        "SELECT COUNT(*) FROM token_alignments "
        "WHERE status IN ('UNRESOLVED_TEXTUAL_VARIANT', 'UNRESOLVED_OTHER') AND macula_xml_id IS NOT NULL"
    ).fetchone()[0]
    assert rows == 0


@requires_syntax_store
def test_resolved_alignments_always_carry_a_macula_xml_id(connection) -> None:
    rows = connection.execute(
        "SELECT COUNT(*) FROM token_alignments "
        "WHERE status IN ('EXACT', 'COMPOSITE', 'VALIDATED_FALLBACK') AND macula_xml_id IS NULL"
    ).fetchone()[0]
    assert rows == 0


@requires_syntax_store
def test_every_resolved_alignment_points_at_a_real_macula_node(connection) -> None:
    """No relation may be attached through coincidental numeric-id equality
    — every non-null macula_xml_id must exist in macula_source_nodes."""
    missing = connection.execute(
        "SELECT COUNT(*) FROM token_alignments a "
        "WHERE a.macula_xml_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM macula_source_nodes n WHERE n.xml_id = a.macula_xml_id)"
    ).fetchone()[0]
    assert missing == 0


@requires_syntax_store
def test_no_two_tagnt_tokens_share_the_same_macula_xml_id(connection) -> None:
    """Each MACULA node is claimed by at most one TAGNT token — a real
    duplicate here would mean the alignment algorithm double-consumed a
    pool entry."""
    rows = connection.execute(
        "SELECT macula_xml_id, COUNT(*) c FROM token_alignments "
        "WHERE macula_xml_id IS NOT NULL GROUP BY macula_xml_id HAVING c > 1"
    ).fetchall()
    assert rows == []


@requires_syntax_store
def test_every_group_member_token_exists_in_source_nodes(connection) -> None:
    rows = connection.execute("SELECT group_id, token_ids_json FROM macula_groups").fetchall()
    assert rows, "expected at least one phrase/clause group"
    node_ids = {row[0] for row in connection.execute("SELECT xml_id FROM macula_source_nodes")}
    bad = []
    for group_id, token_ids_json in rows:
        for tid in json.loads(token_ids_json):
            if tid not in node_ids:
                bad.append((group_id, tid))
    assert bad == []


@requires_syntax_store
def test_group_members_from_other_verses_stay_within_the_same_book_and_nearby_chapter(connection) -> None:
    """Task §4: "parent/child relations do not cross verses UNLESS the
    source explicitly models discourse across verse boundaries." It does:
    MACULA's ``<sentence>`` groups are SENTENCE-scoped, not verse-scoped —
    a single Greek sentence (e.g. Matthew's genealogy, Mat 1:2-1:17) can
    span many verses, so a group "anchored" to its first token's verse
    legitimately contains member tokens from following verses. This is
    real source structure, not a bug (see the phase doc §1.3 for the
    measured extent: 44,810 of ~200k group-membership pairs). The
    meaningful invariant is narrower: cross-verse membership must never
    cross a BOOK boundary or land in a wildly distant chapter (which WOULD
    indicate a real id-collision bug)."""
    rows = connection.execute(
        "SELECT g.group_id, g.book, g.chapter, g.verse, g.token_ids_json FROM macula_groups g"
    ).fetchall()
    node_verse = {
        row[0]: (row[1], row[2], row[3])
        for row in connection.execute("SELECT xml_id, book, chapter, verse FROM macula_source_nodes")
    }
    bad = []
    cross_verse_count = 0
    for group_id, book, chapter, verse, token_ids_json in rows:
        for tid in json.loads(token_ids_json):
            member_verse = node_verse.get(tid)
            if member_verse is None or member_verse == (book, chapter, verse):
                continue
            cross_verse_count += 1
            member_book, member_chapter, _ = member_verse
            if member_book != book or abs(member_chapter - chapter) > 1:
                bad.append((group_id, tid, member_verse, (book, chapter, verse)))
    assert bad == []
    assert cross_verse_count > 0  # confirms the sentence-spans-verses case is genuinely exercised


@requires_syntax_store
def test_parent_child_group_relations_stay_within_the_same_book_and_nearby_chapter(connection) -> None:
    """Same rationale as the member-verse test above — a parent and its
    child group can legitimately anchor to different (adjacent) verses
    within one multi-verse sentence, but never a different book or a
    distant chapter."""
    rows = connection.execute(
        "SELECT group_id, book, chapter, verse, parent_group_id FROM macula_groups "
        "WHERE parent_group_id IS NOT NULL"
    ).fetchall()
    group_verse = {
        row[0]: (row[1], row[2], row[3])
        for row in connection.execute("SELECT group_id, book, chapter, verse FROM macula_groups")
    }
    bad = []
    for group_id, book, chapter, verse, parent_group_id in rows:
        parent_verse = group_verse.get(parent_group_id)
        if parent_verse is None:
            continue
        parent_book, parent_chapter, _ = parent_verse
        if parent_book != book or abs(parent_chapter - chapter) > 1:
            bad.append((group_id, (book, chapter, verse), parent_group_id, parent_verse))
    assert bad == []


@requires_syntax_store
def test_semantic_role_assignments_reference_real_nodes(connection) -> None:
    node_ids = {row[0] for row in connection.execute("SELECT xml_id FROM macula_source_nodes")}
    rows = connection.execute(
        "SELECT predicate_xml_id, argument_xml_id FROM semantic_role_assignments"
    ).fetchall()
    assert rows
    bad = [r for r in rows if r[0] not in node_ids or r[1] not in node_ids]
    assert bad == []


@requires_syntax_store
def test_coreference_links_source_references_a_real_node(connection) -> None:
    node_ids = {row[0] for row in connection.execute("SELECT xml_id FROM macula_source_nodes")}
    rows = connection.execute("SELECT source_xml_id FROM coreference_links").fetchall()
    assert rows
    bad = [r for r in rows if r[0] not in node_ids]
    assert bad == []


@requires_syntax_store
def test_alignment_resolved_rate_is_at_least_95_percent(connection) -> None:
    total = connection.execute("SELECT COUNT(*) FROM token_alignments").fetchone()[0]
    resolved = connection.execute(
        "SELECT COUNT(*) FROM token_alignments WHERE status IN ('EXACT','COMPOSITE','VALIDATED_FALLBACK')"
    ).fetchone()[0]
    assert resolved / total >= 0.95


@requires_syntax_store
def test_every_book_has_a_reasonable_resolved_rate(connection) -> None:
    """No single book's alignment quality silently collapses (a bug that
    only affects a subset of books would not show up in an aggregate-only
    check)."""
    rows = connection.execute(
        "SELECT substr(tagnt_token_id, 1, instr(tagnt_token_id, '.') - 1) AS book, status, COUNT(*) "
        "FROM token_alignments GROUP BY book, status"
    ).fetchall()
    by_book: dict[str, dict[str, int]] = {}
    for book, status, count in rows:
        by_book.setdefault(book, {})[status] = count
    assert len(by_book) == 27
    for book, counts in by_book.items():
        total = sum(counts.values())
        resolved = sum(counts.get(s, 0) for s in ("EXACT", "COMPOSITE", "VALIDATED_FALLBACK"))
        assert resolved / total >= 0.90, f"{book}: resolved rate {resolved / total:.2%} below floor"
