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
    resolved_count = 0
    for tagnt_id, macula_xml_id, status in alignment_rows:
        if macula_xml_id:
            macula_to_tagnt[macula_xml_id] = tagnt_id
            resolved_count += 1

    if resolved_count == 0:
        return verse

    group_rows = connection.execute(
        "SELECT group_id, group_class, rule, role, predication, token_ids_json, parent_group_id "
        "FROM macula_groups WHERE book=? AND chapter=? AND verse=?",
        (verse.book.upper(), verse.chapter, verse.verse),
    ).fetchall()

    phrases: list[GreekPhraseAnalysis] = []
    clauses: list[GreekClauseAnalysis] = []
    has_group_data = False
    for group_id, group_class, rule, role, predication, token_ids_json, parent_group_id in group_rows:
        has_group_data = True
        macula_token_ids = json.loads(token_ids_json)
        mapped_token_ids = tuple(
            macula_to_tagnt[mid] for mid in macula_token_ids if mid in macula_to_tagnt
        )
        if not mapped_token_ids:
            continue
        if group_class == CLAUSE_CLASS:
            clauses.append(
                GreekClauseAnalysis(
                    clause_id=group_id,
                    clause_type=rule or "",
                    token_ids=mapped_token_ids,
                    predicate_id=None,
                    parent_clause_id=parent_group_id,
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
                    parent_phrase_id=parent_group_id,
                    function=role or "",
                )
            )

    role_rows = connection.execute(
        "SELECT predicate_xml_id, role_code, argument_xml_id FROM semantic_role_assignments "
        "WHERE predicate_xml_id IN ({}) OR argument_xml_id IN ({})".format(
            ",".join("?" for mid in macula_to_tagnt) or "''",
            ",".join("?" for mid in macula_to_tagnt) or "''",
        ),
        list(macula_to_tagnt) + list(macula_to_tagnt) if macula_to_tagnt else [],
    ).fetchall() if macula_to_tagnt else []

    semantic_roles: list[GreekSemanticRole] = []
    seen_role_keys: set[tuple[str, str]] = set()
    for predicate_xml_id, role_code, argument_xml_id in role_rows:
        predicate_token = macula_to_tagnt.get(predicate_xml_id)
        argument_token = macula_to_tagnt.get(argument_xml_id)
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

    coref_rows = connection.execute(
        "SELECT source_xml_id, link_type, target_xml_id FROM coreference_links "
        "WHERE source_xml_id IN ({})".format(",".join("?" for _ in macula_to_tagnt) or "''"),
        list(macula_to_tagnt) if macula_to_tagnt else [],
    ).fetchall() if macula_to_tagnt else []

    coreference_by_source: dict[tuple[str, str], list[str]] = {}
    for source_xml_id, link_type, target_xml_id in coref_rows:
        source_token = macula_to_tagnt.get(source_xml_id)
        if source_token is None:
            continue
        # target may or may not be within THIS verse's aligned tokens (an
        # antecedent can be in an earlier verse) — record the raw MACULA id
        # when we cannot map it locally, rather than dropping the link.
        target_token = macula_to_tagnt.get(target_xml_id, target_xml_id)
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
