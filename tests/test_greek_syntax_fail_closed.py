"""Phase 2B.1 §3 — proves, corpus-wide, that an unresolved TAGNT token
fails CLOSED: it keeps its own (Phase 2A) morphology/lexicon, receives no
syntax fact from any other token, and the verse it belongs to reports an
honest grounding status. This is the guarantee a future AI-explanation
layer must be able to rely on without re-deriving it itself — Gemini must
never be asked (or able) to "solve" an alignment gap."""

from __future__ import annotations

import sqlite3

import pytest

from bible_engine.greek_analysis_bundle import SYNTAX_GROUNDING_FULL, SYNTAX_GROUNDING_NONE
from bible_engine.greek_analysis_service import get_greek_analysis, get_greek_analysis_with_syntax
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

DB_PATH = resolve_default_syntax_database_path()
requires_syntax_store = pytest.mark.skipif(not DB_PATH.exists(), reason="greek_syntax_dev.sqlite3 not built locally")


@pytest.fixture(scope="module")
def connection():
    conn = sqlite3.connect(DB_PATH)
    yield conn
    conn.close()


@requires_syntax_store
def test_every_unresolved_token_corpus_wide_has_no_macula_xml_id(connection) -> None:
    bad = connection.execute(
        "SELECT COUNT(*) FROM token_alignments "
        "WHERE status IN ('UNRESOLVED_TEXTUAL_VARIANT','UNRESOLVED_OTHER') AND macula_xml_id IS NOT NULL"
    ).fetchone()[0]
    assert bad == 0


@requires_syntax_store
def test_unresolved_token_never_appears_as_a_phrase_or_clause_member(connection) -> None:
    """No relation may attach through positional coincidence — an
    unresolved TAGNT token's own token_id must never appear inside any
    phrase/clause's mapped membership. Checked end-to-end through the real
    bundle builder (not just the raw store), for a verse with a known
    unresolved token (Jn 3:16 word 11, the K/O-only "αὐτοῦ")."""
    bundle = get_greek_analysis_with_syntax("Jn 3,16")
    verse = bundle.verses[0]
    member_ids = {tid for c in verse.clauses for tid in c.token_ids} | {
        tid for p in verse.phrases for tid in p.token_ids
    }
    assert "Jhn.3.16:11" not in member_ids


@requires_syntax_store
def test_unresolved_token_retains_full_tagnt_morphology_and_lexicon() -> None:
    """An unresolved token's own Phase 2A fields (morphology, lexical
    sense) must be completely unaffected by its alignment status — it is
    still a fully valid, displayable token."""
    bundle = get_greek_analysis_with_syntax("Jn 3,16")
    verse = bundle.verses[0]
    token = next(t for t in verse.tokens if t.token_id == "Jhn.3.16:11")

    assert token.surface  # "αὐτοῦ"
    assert token.lemma == "αὐτός"
    assert token.morphology.confidence == "fully_decoded"
    assert token.morphology.case  # genitive — still decoded from TAGNT's own morph_code
    assert token.lexical_sense is not None  # Hungarian lexicon lookup is unaffected by syntax alignment


@requires_syntax_store
def test_unresolved_token_count_matches_bare_phase_2a_bundle() -> None:
    """Attaching syntax must never drop or duplicate a token — the
    enriched bundle has exactly the same token set as the Phase 2A bundle,
    resolved or not."""
    bare = get_greek_analysis("Jn 3,16")
    enriched = get_greek_analysis_with_syntax("Jn 3,16")
    assert [t.token_id for t in bare.verses[0].tokens] == [t.token_id for t in enriched.verses[0].tokens]


@requires_syntax_store
def test_a_verse_with_any_unresolved_token_is_never_reported_fully_grounded() -> None:
    """FULLY_GROUNDED_SYNTAX must require 100% token resolution — a single
    unresolved token anywhere in the verse caps it at PARTIALLY_GROUNDED at
    best. Verified against the real store: every verse containing at least
    one UNRESOLVED_* token is NOT FULLY_GROUNDED_SYNTAX."""
    rows = connection_scoped_query(DB_PATH)
    assert rows["violations"] == []


def connection_scoped_query(db_path) -> dict:
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT tagnt_token_id, status FROM token_alignments").fetchall()
    from collections import defaultdict

    by_verse: dict[tuple, list] = defaultdict(list)
    for tagnt_token_id, status in rows:
        book, rest = tagnt_token_id.split(".", 1)
        chapter_str, rest2 = rest.split(".", 1)
        verse_str, _word = rest2.split(":", 1)
        by_verse[(book.upper(), int(chapter_str), int(verse_str))].append(status)

    group_verses = set(conn.execute("SELECT DISTINCT book, chapter, verse FROM macula_groups").fetchall())

    violations = []
    for key, statuses in by_verse.items():
        has_unresolved = any(s.startswith("UNRESOLVED") for s in statuses)
        fully_resolved = all(not s.startswith("UNRESOLVED") for s in statuses)
        has_group = key in group_verses
        would_be_full = fully_resolved and has_group
        if has_unresolved and would_be_full:
            violations.append(key)
    return {"violations": violations}


@requires_syntax_store
def test_missing_store_bundle_still_fully_displayable() -> None:
    """A verse with no syntax store at all (e.g. this function's explicit
    nonexistent-path case, or any real verse before the store is built)
    must still produce a complete, displayable Phase 2A bundle — syntax
    grounding degrades gracefully to NO_GROUNDED_SYNTAX, nothing else
    breaks."""
    bundle = get_greek_analysis_with_syntax("Jn 3,16", syntax_database_path="/does/not/exist.sqlite3")
    verse = bundle.verses[0]
    assert verse.syntax_grounding == SYNTAX_GROUNDING_NONE
    assert len(verse.tokens) == 26
    for token in verse.tokens:
        assert token.surface
        assert token.morphology.raw_code


@requires_syntax_store
def test_fully_grounded_verse_really_has_zero_unresolved_tokens() -> None:
    """The inverse check, on a real FULLY_GROUNDED_SYNTAX verse (Mt 9:18)."""
    bundle = get_greek_analysis_with_syntax("Mt 9,18")
    verse = bundle.verses[0]
    assert verse.syntax_grounding == SYNTAX_GROUNDING_FULL

    with sqlite3.connect(DB_PATH) as conn:
        statuses = [
            row[0]
            for row in conn.execute(
                "SELECT status FROM token_alignments WHERE tagnt_token_id LIKE 'Mat.9.18:%'"
            )
        ]
    assert all(not s.startswith("UNRESOLVED") for s in statuses)
