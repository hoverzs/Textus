"""Phase 2B §6 — attaches deterministic syntax data (from the normalized
local store, ``bible_engine.greek_syntax_sqlite``) onto an existing
``GreekAnalysisBundle`` (Phase 2A, morphology/lexical only).

Never overrides a Phase 2A token/morphology/lexical field — only adds new
verse-level phrase/clause/semantic-role/coreference facts, and only for
tokens with a resolved MACULA alignment. An unresolved TAGNT token
contributes no syntax fact, by construction (its ``macula_xml_id`` is
absent from ``token_alignments``, so no group/role/coreference lookup can
ever find it).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from bible_engine.greek_analysis_bundle import (
    GreekAnalysisBundle,
    GreekClauseAnalysis,
    GreekCoreferenceLink,
    GreekParticipantMention,
    GreekPhraseAnalysis,
    GreekSemanticRole,
    GreekVerseAnalysis,
    SYNTAX_GROUNDING_FULL,
    SYNTAX_GROUNDING_NONE,
    SYNTAX_GROUNDING_PARTIAL,
)
from bible_engine.macula_greek_parser import CLAUSE_CLASS, PHRASE_CLASSES


def attach_syntax(bundle: GreekAnalysisBundle, database_path: str | Path) -> GreekAnalysisBundle:
    path = Path(database_path)
    if not path.exists():
        return bundle

    with sqlite3.connect(path) as connection:
        new_verses = tuple(_attach_verse_syntax(verse, connection) for verse in bundle.verses)

    return replace(bundle, verses=new_verses)


def _attach_verse_syntax(verse: GreekVerseAnalysis, connection: sqlite3.Connection) -> GreekVerseAnalysis:
    token_ids = [t.token_id for t in verse.tokens]
    if not token_ids:
        return verse

    placeholders = ",".join("?" for _ in token_ids)
    alignment_rows = connection.execute(
        f"SELECT tagnt_token_id, macula_xml_id, status FROM token_alignments "
        f"WHERE tagnt_token_id IN ({placeholders})",
        token_ids,
    ).fetchall()
    if not alignment_rows:
        return verse

    macula_to_tagnt: dict[str, str] = {}
    status_by_token: dict[str, str] = {}
    resolved_count = 0
    for tagnt_id, macula_xml_id, status in alignment_rows:
        status_by_token[tagnt_id] = status
        if macula_xml_id:
            macula_to_tagnt[macula_xml_id] = tagnt_id
            resolved_count += 1

    verse = replace(
        verse,
        tokens=tuple(
            replace(t, alignment_status=status_by_token.get(t.token_id, t.alignment_status))
            for t in verse.tokens
        ),
    )

    if resolved_count == 0:
        return verse

    group_rows = connection.execute(
        "SELECT group_id, group_class, rule, role, predication, token_ids_json, parent_group_id "
        "FROM macula_groups WHERE book=? AND chapter=? AND verse=?",
        (verse.book.upper(), verse.chapter, verse.verse),
    ).fetchall()

    # A role belongs to its PREDICATE's own verse (the argument is a
    # pointer that may legitimately reach into a different verse — same
    # convention as coreference below, where the source owns the link and
    # the target can be anywhere). Previously this also matched when only
    # the ARGUMENT was in-verse (``OR argument_xml_id IN (...)``), which
    # both double-counted roles under two different "owning" verses and
    # diverged from bible_engine.greek_analysis_repository's predicate-only
    # scoping and the Supabase import's own verse_ref convention — found
    # via real Local<->Supabase parity testing.
    role_rows = connection.execute(
        "SELECT predicate_xml_id, role_code, argument_xml_id FROM semantic_role_assignments "
        "WHERE predicate_xml_id IN (SELECT xml_id FROM macula_source_nodes WHERE book=? AND chapter=? AND verse=?)",
        (verse.book.upper(), verse.chapter, verse.verse),
    ).fetchall()

    # A clause/phrase can span a verse boundary (e.g. Mt 28:19-20's single
    # long sentence), and a role's argument can lie in a different verse
    # too — ``macula_to_tagnt`` above is scoped to only this verse's own
    # tokens, so any such "other side" xml_id needs a narrowly-targeted
    # extra lookup rather than being dropped (found via real Supabase-
    # parity testing, where the import path already resolves these
    # globally, exposing this local-only gap; see
    # bible_engine.greek_analysis_repository's identical fix).
    #
    # Kept in a SEPARATE ``combined_map`` rather than merged into
    # ``macula_to_tagnt`` itself: a predicate/source xml_id must resolve
    # ONLY via the strict per-verse map — merging would let an xml_id
    # resolved here for one row's "other side" (e.g. an argument) leak
    # into and silently override another row's predicate/source lookup,
    # which can point to a genuinely different verse (a real bug hit and
    # fixed during this same investigation).
    other_side_ids = {xid for row in role_rows for xid in (row[0], row[2])}
    for group_id, group_class, rule, role, predication, token_ids_json, parent_group_id in group_rows:
        other_side_ids.update(json.loads(token_ids_json))
    other_side_ids -= set(macula_to_tagnt)
    combined_map = dict(macula_to_tagnt)
    if other_side_ids:
        placeholders = ",".join("?" for _ in other_side_ids)
        extra_rows = connection.execute(
            f"SELECT tagnt_token_id, macula_xml_id FROM token_alignments "
            f"WHERE macula_xml_id IN ({placeholders})",
            tuple(other_side_ids),
        ).fetchall()
        for tagnt_id, macula_xml_id in extra_rows:
            combined_map[macula_xml_id] = tagnt_id

    # A group's own parent is not always the SAME constituent type (a
    # phrase's parent can be a clause and vice versa). Determine each
    # referenced parent's class: first from this verse's own group_rows,
    # then a narrowly-targeted extra lookup for any parent lying in a
    # different verse — see bible_engine.greek_analysis_repository's
    # identical fix.
    is_clause_by_group_id = {row[0]: row[1] == CLAUSE_CLASS for row in group_rows}
    unknown_parent_ids = {row[6] for row in group_rows if row[6] is not None} - set(is_clause_by_group_id)
    if unknown_parent_ids:
        placeholders = ",".join("?" for _ in unknown_parent_ids)
        parent_class_rows = connection.execute(
            f"SELECT group_id, group_class FROM macula_groups WHERE group_id IN ({placeholders})",
            tuple(unknown_parent_ids),
        ).fetchall()
        for pgid, pclass in parent_class_rows:
            is_clause_by_group_id[pgid] = pclass == CLAUSE_CLASS

    phrases: list[GreekPhraseAnalysis] = []
    clauses: list[GreekClauseAnalysis] = []
    has_group_data = False
    for group_id, group_class, rule, role, predication, token_ids_json, parent_group_id in group_rows:
        has_group_data = True
        macula_token_ids = json.loads(token_ids_json)
        mapped_token_ids = tuple(
            combined_map[mid] for mid in macula_token_ids if mid in combined_map
        )
        if not mapped_token_ids:
            continue
        parent_is_clause = is_clause_by_group_id.get(parent_group_id) if parent_group_id is not None else None
        if group_class == CLAUSE_CLASS:
            clauses.append(
                GreekClauseAnalysis(
                    clause_id=group_id,
                    clause_type=rule or "",
                    token_ids=mapped_token_ids,
                    predicate_id=None,
                    parent_clause_id=parent_group_id if parent_is_clause else None,
                    parent_phrase_id=parent_group_id if parent_is_clause is False else None,
                    relation_to_parent=predication or "",
                )
            )
        elif group_class in PHRASE_CLASSES:
            phrases.append(
                GreekPhraseAnalysis(
                    phrase_id=group_id,
                    phrase_type=group_class,
                    token_ids=mapped_token_ids,
                    head_token_id=None,
                    parent_phrase_id=parent_group_id if parent_is_clause is False else None,
                    parent_clause_id=parent_group_id if parent_is_clause else None,
                    function=role or "",
                )
            )

    coref_rows = connection.execute(
        "SELECT source_xml_id, link_type, target_xml_id FROM coreference_links "
        "WHERE source_xml_id IN ({})".format(",".join("?" for _ in macula_to_tagnt) or "''"),
        list(macula_to_tagnt) if macula_to_tagnt else [],
    ).fetchall() if macula_to_tagnt else []

    # A coreference target commonly lies in an EARLIER verse too (an
    # antecedent named several verses back) — resolve via the SAME
    # combined_map built above (source stays strict via macula_to_tagnt).
    coref_other_ids = {row[2] for row in coref_rows} - set(combined_map)
    if coref_other_ids:
        placeholders = ",".join("?" for _ in coref_other_ids)
        extra_rows = connection.execute(
            f"SELECT tagnt_token_id, macula_xml_id FROM token_alignments "
            f"WHERE macula_xml_id IN ({placeholders})",
            tuple(coref_other_ids),
        ).fetchall()
        for tagnt_id, macula_xml_id in extra_rows:
            combined_map[macula_xml_id] = tagnt_id

    semantic_roles: list[GreekSemanticRole] = []
    seen_role_keys: set[tuple[str, str]] = set()
    for predicate_xml_id, role_code, argument_xml_id in role_rows:
        predicate_token = macula_to_tagnt.get(predicate_xml_id)
        argument_token = combined_map.get(argument_xml_id)
        if predicate_token is None or argument_token is None:
            continue
        key = (predicate_token, argument_token)
        if key in seen_role_keys:
            continue
        seen_role_keys.add(key)
        semantic_roles.append(
            GreekSemanticRole(
                role_id=f"{predicate_token}.{role_code}.{argument_token}",
                role_type=role_code,
                predicate_id=predicate_token,
                token_ids=(argument_token,),
            )
        )

    coreference_by_source: dict[tuple[str, str], list[str]] = {}
    for source_xml_id, link_type, target_xml_id in coref_rows:
        source_token = macula_to_tagnt.get(source_xml_id)
        target_token = combined_map.get(target_xml_id)
        if source_token is None or target_token is None:
            # Genuinely unresolvable anywhere in TAGNT — matches the
            # Supabase importer's own skip behavior; never fall back to
            # the raw MACULA xml_id, which would be a differently-typed,
            # inconsistent value.
            continue
        coreference_by_source.setdefault((source_token, link_type), []).append(target_token)

    coreference = tuple(
        GreekCoreferenceLink(source_token_id=src, link_type=lt, target_token_ids=tuple(targets))
        for (src, lt), targets in coreference_by_source.items()
    )

    total_tokens = len(token_ids)
    if resolved_count == total_tokens and has_group_data:
        grounding = SYNTAX_GROUNDING_FULL
    elif resolved_count > 0 and (has_group_data or semantic_roles or coreference):
        grounding = SYNTAX_GROUNDING_PARTIAL
    else:
        grounding = SYNTAX_GROUNDING_NONE

    return replace(
        verse,
        phrases=tuple(phrases),
        clauses=tuple(clauses),
        semantic_roles=tuple(semantic_roles),
        coreference=coreference,
        syntax_grounding=grounding,
    )
