"""Phase 2C §5/§6 — repository abstraction for Greek SYNTAX data (phrases/
clauses/semantic-roles/coreference/alignment status). Mirrors
``bible_engine.hebrew_analysis_repository``'s Protocol shape closely, but
independent: Greek's local store schema (Phase 2B/2B.1,
``bible_engine.greek_syntax_sqlite``) and Supabase schema
(``supabase/migrations/20260911220000_greek_linguistic_layer.sql``) are
both Greek-specific.

``GreekAnalysisService`` (the base-token/morphology/lexicon builder,
Phase 2A, unchanged) does not depend on this module at all — a repository
here only ever supplies the SYNTAX overlay attached on top via
``attach_syntax_via_repository()``. TAGNT/TEGMC/TBESG remain authoritative
regardless of which repository backend is selected.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from bible_engine.greek_analysis_bundle import (
    GreekAnalysisBundle,
    GreekClauseAnalysis,
    GreekCoreferenceLink,
    GreekPhraseAnalysis,
    GreekSemanticRole,
    SYNTAX_GROUNDING_FULL,
    SYNTAX_GROUNDING_NONE,
    SYNTAX_GROUNDING_PARTIAL,
)
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

MACULA_DATASET_ID = "macula_greek_sblgnt"


@dataclass(frozen=True)
class GreekVerseSyntaxData:
    phrases: tuple[GreekPhraseAnalysis, ...] = ()
    clauses: tuple[GreekClauseAnalysis, ...] = ()
    semantic_roles: tuple[GreekSemanticRole, ...] = ()
    coreference: tuple[GreekCoreferenceLink, ...] = ()
    alignment_status_by_token: dict[str, str] | None = None

    @property
    def has_syntax(self) -> bool:
        return bool(self.phrases or self.clauses)


class GreekAnalysisRepository(Protocol):
    def get_verse_syntax(self, verse_ref: str) -> GreekVerseSyntaxData: ...

    def dataset_version_signature(self) -> str:
        """See ``bible_engine.hebrew_analysis_repository.HebrewAnalysisRepository
        .dataset_version_signature`` — identical contract: a short, stable
        string identifying exactly which dataset revisions are active,
        used as the cache-invalidation key (Phase 2C §1/§16). Returns
        ``""`` when unknown — callers must never cache under that."""
        ...


# ---------------------------------------------------------------------------
# Local (Phase 2B/2B.1 SQLite store).
# ---------------------------------------------------------------------------


class LocalGreekAnalysisRepository:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = (
            Path(database_path) if database_path is not None else resolve_default_syntax_database_path()
        )

    def dataset_version_signature(self) -> str:
        # The local dev store (bible_engine/greek_syntax_sqlite.py) does not
        # carry its own dataset_versions table (unlike the Supabase schema,
        # which reuses original_language_dataset_versions) — its identity is
        # the pinned MACULA commit + TAGNT/TBESG/TEGMC versions, which are
        # static per Phase 2A/2B/2B.1 doc, not queried at runtime here. See
        # bible_engine.greek_dataset_version.greek_dataset_version_signature
        # for the actual signature builder this repository's caller uses.
        if not self.database_path.exists():
            return ""
        return "local-store-present"

    def get_verse_syntax(self, verse_ref: str) -> GreekVerseSyntaxData:
        if not self.database_path.exists():
            return GreekVerseSyntaxData()
        try:
            connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
        except sqlite3.Error:
            return GreekVerseSyntaxData()
        try:
            return _read_local_verse_syntax(connection, verse_ref)
        except sqlite3.Error:
            return GreekVerseSyntaxData()
        finally:
            connection.close()


def _parse_verse_ref(verse_ref: str) -> tuple[str, int, int]:
    book, rest = verse_ref.split(".", 1)
    chapter_str, verse_str = rest.split(".", 1)
    return book.upper(), int(chapter_str), int(verse_str)


def _read_local_verse_syntax(connection: sqlite3.Connection, verse_ref: str) -> GreekVerseSyntaxData:
    book, chapter, verse = _parse_verse_ref(verse_ref)

    alignment_rows = connection.execute(
        "SELECT tagnt_token_id, macula_xml_id, status FROM token_alignments "
        "WHERE tagnt_token_id LIKE ?",
        (f"%.{chapter}.{verse}:%",),
    ).fetchall()
    # LIKE on chapter/verse alone can over-match across books that share a
    # chapter/verse number — filter precisely by book prefix too.
    alignment_rows = [row for row in alignment_rows if row["tagnt_token_id"].split(".", 1)[0].upper() == book]

    macula_to_tagnt: dict[str, str] = {}
    alignment_status_by_token: dict[str, str] = {}
    for row in alignment_rows:
        alignment_status_by_token[row["tagnt_token_id"]] = row["status"]
        if row["macula_xml_id"]:
            macula_to_tagnt[row["macula_xml_id"]] = row["tagnt_token_id"]

    if not alignment_rows:
        return GreekVerseSyntaxData()

    group_rows = connection.execute(
        "SELECT group_id, group_class, rule, role, predication, token_ids_json, parent_group_id "
        "FROM macula_groups WHERE book=? AND chapter=? AND verse=?",
        (book, chapter, verse),
    ).fetchall()

    import json as _json

    from bible_engine.macula_greek_parser import CLAUSE_CLASS, PHRASE_CLASSES

    phrases: list[GreekPhraseAnalysis] = []
    clauses: list[GreekClauseAnalysis] = []
    for row in group_rows:
        macula_token_ids = _json.loads(row["token_ids_json"])
        mapped = tuple(macula_to_tagnt[mid] for mid in macula_token_ids if mid in macula_to_tagnt)
        if not mapped:
            continue
        if row["group_class"] == CLAUSE_CLASS:
            clauses.append(
                GreekClauseAnalysis(
                    clause_id=row["group_id"], clause_type=row["rule"] or "", token_ids=mapped,
                    predicate_id=None, parent_clause_id=row["parent_group_id"],
                    relation_to_parent=row["predication"] or "",
                )
            )
        elif row["group_class"] in PHRASE_CLASSES:
            phrases.append(
                GreekPhraseAnalysis(
                    phrase_id=row["group_id"], phrase_type=row["group_class"], token_ids=mapped,
                    head_token_id=None, parent_phrase_id=row["parent_group_id"], function=row["role"] or "",
                )
            )

    role_rows = connection.execute(
        "SELECT predicate_xml_id, role_code, argument_xml_id FROM semantic_role_assignments "
        "WHERE predicate_xml_id IN (SELECT xml_id FROM macula_source_nodes WHERE book=? AND chapter=? AND verse=?)",
        (book, chapter, verse),
    ).fetchall()
    semantic_roles: list[GreekSemanticRole] = []
    for row in role_rows:
        predicate_token = macula_to_tagnt.get(row["predicate_xml_id"])
        argument_token = macula_to_tagnt.get(row["argument_xml_id"])
        if predicate_token is None or argument_token is None:
            continue
        semantic_roles.append(
            GreekSemanticRole(
                role_id=f"{predicate_token}.{row['role_code']}.{argument_token}",
                role_type=row["role_code"], predicate_id=predicate_token, token_ids=(argument_token,),
            )
        )

    coref_rows = connection.execute(
        "SELECT source_xml_id, link_type, target_xml_id FROM coreference_links "
        "WHERE source_xml_id IN (SELECT xml_id FROM macula_source_nodes WHERE book=? AND chapter=? AND verse=?)",
        (book, chapter, verse),
    ).fetchall()
    coreference_by_source: dict[tuple[str, str], list[str]] = {}
    for row in coref_rows:
        source_token = macula_to_tagnt.get(row["source_xml_id"])
        if source_token is None:
            continue
        target_token = macula_to_tagnt.get(row["target_xml_id"], row["target_xml_id"])
        coreference_by_source.setdefault((source_token, row["link_type"]), []).append(target_token)
    coreference = tuple(
        GreekCoreferenceLink(source_token_id=src, link_type=lt, target_token_ids=tuple(targets))
        for (src, lt), targets in coreference_by_source.items()
    )

    return GreekVerseSyntaxData(
        phrases=tuple(phrases), clauses=tuple(clauses), semantic_roles=tuple(semantic_roles),
        coreference=coreference, alignment_status_by_token=alignment_status_by_token,
    )


# ---------------------------------------------------------------------------
# Supabase (Phase 2C — get_greek_verse_syntax_bundle RPC).
# ---------------------------------------------------------------------------


class SupabaseGreekAnalysisRepository:
    def __init__(self, client=None) -> None:
        self._client = client

    def _resolve_client(self):
        if self._client is not None:
            return self._client
        from supabase_client import get_supabase_client

        return get_supabase_client()

    def dataset_version_signature(self) -> str:
        try:
            client = self._resolve_client()
        except Exception:
            return ""
        try:
            result = (
                client.table("original_language_dataset_versions")
                .select("dataset_id,revision")
                .eq("is_active", True)
                .in_("dataset_id", ["tagnt", "tegmc", "tbesg", "greek_hu_lexicon", "macula_greek_sblgnt"])
                .order("dataset_id")
                .execute()
            )
        except Exception:
            return ""
        rows = result.data or []
        return ",".join(f"{row['dataset_id']}:{row['revision']}" for row in rows)

    def get_verse_syntax(self, verse_ref: str) -> GreekVerseSyntaxData:
        try:
            client = self._resolve_client()
        except Exception:
            return GreekVerseSyntaxData()
        try:
            result = client.rpc("get_greek_verse_syntax_bundle", {"p_verse_ref": verse_ref}).execute()
        except Exception:
            return GreekVerseSyntaxData()
        payload = result.data or {}
        return _parse_bundle_payload(payload)


def _parse_bundle_payload(payload: dict) -> GreekVerseSyntaxData:
    phrases = tuple(
        GreekPhraseAnalysis(
            phrase_id=str(row["id"]), phrase_type=row["phrase_type"], token_ids=(),
            head_token_id=row.get("head_token_id"), parent_phrase_id=_stringify(row.get("parent_phrase_id")),
            function=row.get("role") or "",
        )
        for row in payload.get("phrases", [])
    )
    clauses = tuple(
        GreekClauseAnalysis(
            clause_id=str(row["id"]), clause_type=row.get("clause_type") or "", token_ids=(),
            predicate_id=row.get("predicate_token_id"), parent_clause_id=_stringify(row.get("parent_clause_id")),
            relation_to_parent=row.get("relation_to_parent") or "",
        )
        for row in payload.get("clauses", [])
    )
    tokens_by_phrase: dict[str, list[str]] = {}
    tokens_by_clause: dict[str, list[str]] = {}
    for row in payload.get("membership", []):
        if row.get("phrase_id") is not None:
            tokens_by_phrase.setdefault(str(row["phrase_id"]), []).append(row["token_id"])
        if row.get("clause_id") is not None:
            tokens_by_clause.setdefault(str(row["clause_id"]), []).append(row["token_id"])
    phrases = tuple(replace(p, token_ids=tuple(tokens_by_phrase.get(p.phrase_id, ()))) for p in phrases)
    clauses = tuple(replace(c, token_ids=tuple(tokens_by_clause.get(c.clause_id, ()))) for c in clauses)

    semantic_roles = tuple(
        GreekSemanticRole(
            role_id=f"{row['predicate_token_id']}.{row['role_code']}.{row['argument_token_id']}",
            role_type=row["role_code"], predicate_id=row["predicate_token_id"],
            token_ids=(row["argument_token_id"],),
        )
        for row in payload.get("semantic_roles", [])
    )
    coreference_by_source: dict[tuple[str, str], list[str]] = {}
    for row in payload.get("coreference", []):
        coreference_by_source.setdefault((row["source_token_id"], row["link_type"]), []).append(
            row["target_token_id"]
        )
    coreference = tuple(
        GreekCoreferenceLink(source_token_id=src, link_type=lt, target_token_ids=tuple(targets))
        for (src, lt), targets in coreference_by_source.items()
    )

    alignment_status_by_token = {
        row["token_id"]: row["alignment_status"] for row in payload.get("tokens", []) if row.get("alignment_status")
    }

    return GreekVerseSyntaxData(
        phrases=phrases, clauses=clauses, semantic_roles=semantic_roles, coreference=coreference,
        alignment_status_by_token=alignment_status_by_token or None,
    )


def _stringify(value: object) -> str | None:
    return str(value) if value is not None else None


# ---------------------------------------------------------------------------
# Backend selection + shared attach logic.
# ---------------------------------------------------------------------------


def _configured_greek_analysis_backend() -> str:
    return (os.environ.get("TEXTUS_GREEK_ANALYSIS_BACKEND", "local") or "local").strip().lower()


def get_default_greek_analysis_repository() -> GreekAnalysisRepository:
    backend = _configured_greek_analysis_backend()
    if backend == "supabase":
        return SupabaseGreekAnalysisRepository()
    return LocalGreekAnalysisRepository()


def attach_syntax_via_repository(
    bundle: GreekAnalysisBundle, repository: GreekAnalysisRepository
) -> GreekAnalysisBundle:
    """Backend-agnostic syntax attachment — ``GreekAnalysisService`` code
    calling this never knows or cares whether ``repository`` is local
    SQLite or Supabase (task §5)."""
    new_verses = tuple(_attach_verse(verse, repository) for verse in bundle.verses)
    return replace(bundle, verses=new_verses)


def _attach_verse(verse, repository: GreekAnalysisRepository):
    data = repository.get_verse_syntax(verse.verse_id)
    status_by_token = data.alignment_status_by_token or {}
    new_tokens = tuple(
        replace(t, alignment_status=status_by_token.get(t.token_id, t.alignment_status)) for t in verse.tokens
    )
    if not data.phrases and not data.clauses and not data.semantic_roles and not data.coreference:
        return replace(verse, tokens=new_tokens) if status_by_token else verse

    token_ids = {t.token_id for t in verse.tokens}
    resolved_count = sum(
        1
        for tid in token_ids
        if status_by_token.get(tid, "").startswith(("EXACT", "COMPOSITE", "VALIDATED"))
    )
    total = len(token_ids)
    has_group_data = bool(data.phrases or data.clauses)
    if resolved_count == total and has_group_data:
        grounding = SYNTAX_GROUNDING_FULL
    elif resolved_count > 0 and (has_group_data or data.semantic_roles or data.coreference):
        grounding = SYNTAX_GROUNDING_PARTIAL
    else:
        grounding = SYNTAX_GROUNDING_NONE

    return replace(
        verse,
        tokens=new_tokens,
        phrases=data.phrases,
        clauses=data.clauses,
        semantic_roles=data.semantic_roles,
        coreference=data.coreference,
        syntax_grounding=grounding,
    )


__all__ = [
    "MACULA_DATASET_ID",
    "GreekVerseSyntaxData",
    "GreekAnalysisRepository",
    "LocalGreekAnalysisRepository",
    "SupabaseGreekAnalysisRepository",
    "get_default_greek_analysis_repository",
    "attach_syntax_via_repository",
]
