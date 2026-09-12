"""Phase 2C §7 — LocalGreekAnalysisRepository ↔ SupabaseGreekAnalysisRepository
parity.

No real Supabase project is reachable from this environment (no
credentials — see docs/greek_analysis_v2_phase2c_contextual.md §22), so
"Supabase" here is exercised via ``SupabaseGreekAnalysisRepository._parse_
bundle_payload`` fed a payload BUILT FROM THE SAME underlying local-store
data the RPC's own SQL would select from (mirroring the exact jsonb shape
``get_greek_verse_syntax_bundle`` produces) — this proves the two
repositories' RESULT-ASSEMBLY logic is equivalent given equivalent input,
which is the part that can regress independently of network/credentials.
True end-to-end parity against a live Supabase project remains a
deployment-time verification step (§22)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from bible_engine.greek_analysis_repository import (
    LocalGreekAnalysisRepository,
    _parse_bundle_payload,
)
from bible_engine.greek_analysis_service import get_greek_analysis_with_syntax
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

DB_PATH = resolve_default_syntax_database_path()
requires_syntax_store = pytest.mark.skipif(not DB_PATH.exists(), reason="greek_syntax_dev.sqlite3 not built locally")

REGRESSION_REFERENCES = [
    "Jn 3,16", "Jn 1,1", "Jn 1,14", "Jn 19,30", "Mt 28,19-20", "Mt 9,18",
    "Fil 1,21", "1Kor 15,13-14", "Róm 5,1", "1Tim 3,1", "Mk 1,9-11",
    "Róm 5,12", "2Pt 1,1", "Róm 3,24-25", "Lk 10,25-37",
]


def _simulated_rpc_payload(verse_ref: str) -> dict:
    """Builds the SAME jsonb shape ``get_greek_verse_syntax_bundle(verse_ref)``
    would return, directly from the local store — i.e. simulates "what
    Supabase would say" using the identical underlying data the local
    repository also reads, so a diff between the two proves an assembly
    bug, not a data difference."""
    book, rest = verse_ref.split(".", 1)
    chapter_str, verse_str = rest.split(".", 1)
    book, chapter, verse = book.upper(), int(chapter_str), int(verse_str)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    align_rows = conn.execute(
        "SELECT tagnt_token_id, macula_xml_id, status FROM token_alignments WHERE tagnt_token_id LIKE ?",
        (f"{book}.{chapter}.{verse}:%",),
    ).fetchall()
    align_rows = [r for r in align_rows if r["tagnt_token_id"].split(".", 1)[0].upper() == book]
    macula_to_tagnt = {r["macula_xml_id"]: r["tagnt_token_id"] for r in align_rows if r["macula_xml_id"]}
    status_by_token = {r["tagnt_token_id"]: r["status"] for r in align_rows}

    from bible_engine.macula_greek_parser import CLAUSE_CLASS, PHRASE_CLASSES

    group_rows = conn.execute(
        "SELECT group_id, group_class, rule, role, token_ids_json FROM macula_groups "
        "WHERE book=? AND chapter=? AND verse=?",
        (book, chapter, verse),
    ).fetchall()
    group_rows = [r for r in group_rows if r["group_class"] == CLAUSE_CLASS or r["group_class"] in PHRASE_CLASSES]

    gid_map: dict[str, int] = {}
    phrases_payload, clauses_payload, membership_payload = [], [], []
    next_id = 1
    for row in group_rows:
        gid_map[row["group_id"]] = next_id
        if row["group_class"] == CLAUSE_CLASS:
            clauses_payload.append({
                "id": next_id, "clause_type": row["rule"], "predicate_token_id": None,
                "parent_clause_id": None, "relation_to_parent": "",
            })
        else:
            phrases_payload.append({
                "id": next_id, "phrase_type": row["group_class"], "role": row["role"],
                "head_token_id": None, "parent_phrase_id": None, "parent_clause_id": None,
            })
        next_id += 1
    for row in group_rows:
        gid = gid_map[row["group_id"]]
        is_clause = row["group_class"] == CLAUSE_CLASS
        for mid in json.loads(row["token_ids_json"]):
            tid = macula_to_tagnt.get(mid)
            if tid:
                membership_payload.append({
                    "token_id": tid, "phrase_id": None if is_clause else gid, "clause_id": gid if is_clause else None,
                })

    role_rows = conn.execute(
        "SELECT predicate_xml_id, role_code, argument_xml_id FROM semantic_role_assignments "
        "WHERE predicate_xml_id IN (SELECT xml_id FROM macula_source_nodes WHERE book=? AND chapter=? AND verse=?)",
        (book, chapter, verse),
    ).fetchall()
    roles_payload = []
    for r in role_rows:
        pt, at = macula_to_tagnt.get(r["predicate_xml_id"]), macula_to_tagnt.get(r["argument_xml_id"])
        if pt and at:
            roles_payload.append({"id": len(roles_payload) + 1, "role_code": r["role_code"], "predicate_token_id": pt, "argument_token_id": at})

    coref_rows = conn.execute(
        "SELECT source_xml_id, link_type, target_xml_id FROM coreference_links "
        "WHERE source_xml_id IN (SELECT xml_id FROM macula_source_nodes WHERE book=? AND chapter=? AND verse=?)",
        (book, chapter, verse),
    ).fetchall()
    coref_payload = []
    for r in coref_rows:
        st_ = macula_to_tagnt.get(r["source_xml_id"])
        if st_:
            coref_payload.append({
                "id": len(coref_payload) + 1, "link_type": r["link_type"], "source_token_id": st_,
                "target_token_id": macula_to_tagnt.get(r["target_xml_id"], r["target_xml_id"]),
            })

    tokens_payload = [
        {"token_id": tid, "alignment_status": status} for tid, status in status_by_token.items()
    ]

    conn.close()
    return {
        "phrases": phrases_payload, "clauses": clauses_payload, "membership": membership_payload,
        "semantic_roles": roles_payload, "coreference": coref_payload, "tokens": tokens_payload,
    }


@requires_syntax_store
@pytest.mark.parametrize("reference", REGRESSION_REFERENCES)
def test_local_and_simulated_supabase_agree_on_every_regression_verse(reference: str) -> None:
    bundle = get_greek_analysis_with_syntax(reference)
    local_repo = LocalGreekAnalysisRepository()

    for verse in bundle.verses:
        local_data = local_repo.get_verse_syntax(verse.verse_id)
        supabase_data = _parse_bundle_payload(_simulated_rpc_payload(verse.verse_id))

        local_phrase_sets = {frozenset(p.token_ids) for p in local_data.phrases}
        supabase_phrase_sets = {frozenset(p.token_ids) for p in supabase_data.phrases}
        assert local_phrase_sets == supabase_phrase_sets, f"{verse.verse_id}: phrase token sets differ"

        local_clause_sets = {frozenset(c.token_ids) for c in local_data.clauses}
        supabase_clause_sets = {frozenset(c.token_ids) for c in supabase_data.clauses}
        assert local_clause_sets == supabase_clause_sets, f"{verse.verse_id}: clause token sets differ"

        local_roles = {(r.role_type, r.predicate_id, r.token_ids) for r in local_data.semantic_roles}
        supabase_roles = {(r.role_type, r.predicate_id, r.token_ids) for r in supabase_data.semantic_roles}
        assert local_roles == supabase_roles, f"{verse.verse_id}: semantic roles differ"

        local_coref = {(c.link_type, c.source_token_id, c.target_token_ids) for c in local_data.coreference}
        supabase_coref = {(c.link_type, c.source_token_id, c.target_token_ids) for c in supabase_data.coreference}
        assert local_coref == supabase_coref, f"{verse.verse_id}: coreference differs"


@requires_syntax_store
@pytest.mark.parametrize("reference", REGRESSION_REFERENCES)
def test_local_and_simulated_supabase_agree_on_alignment_status(reference: str) -> None:
    bundle = get_greek_analysis_with_syntax(reference)
    for verse in bundle.verses:
        supabase_payload = _simulated_rpc_payload(verse.verse_id)
        supabase_status = {row["token_id"]: row["alignment_status"] for row in supabase_payload["tokens"]}
        for token in verse.tokens:
            assert token.alignment_status == supabase_status.get(token.token_id, ""), (
                f"{token.token_id}: local alignment_status={token.alignment_status!r} "
                f"vs simulated-Supabase={supabase_status.get(token.token_id)!r}"
            )


@requires_syntax_store
@pytest.mark.parametrize("reference", REGRESSION_REFERENCES)
def test_local_and_simulated_supabase_agree_on_grounding_status(reference: str) -> None:
    """PARTIAL/NO grounding must also match — not just FULLY_GROUNDED
    verses (task §7)."""
    from bible_engine.greek_analysis_repository import attach_syntax_via_repository
    from bible_engine.greek_analysis_service import get_greek_analysis

    class _SimulatedSupabaseRepository:
        def dataset_version_signature(self) -> str:
            return "simulated"

        def get_verse_syntax(self, verse_ref: str):
            return _parse_bundle_payload(_simulated_rpc_payload(verse_ref))

    local_bundle = get_greek_analysis_with_syntax(reference)
    supabase_bundle = attach_syntax_via_repository(get_greek_analysis(reference), _SimulatedSupabaseRepository())

    for local_verse, supabase_verse in zip(local_bundle.verses, supabase_bundle.verses):
        assert local_verse.verse_id == supabase_verse.verse_id
        assert local_verse.syntax_grounding == supabase_verse.syntax_grounding, (
            f"{local_verse.verse_id}: local={local_verse.syntax_grounding} "
            f"vs simulated-Supabase={supabase_verse.syntax_grounding}"
        )
