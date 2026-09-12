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

import logging
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
    SYNTAX_GROUNDING_UNAVAILABLE,
)
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

logger = logging.getLogger(__name__)

MACULA_DATASET_ID = "macula_greek_sblgnt"

# Repository-call result classification (2026-09 audit fix) — mirrors
# bible_engine.hebrew_analysis_repository's RESULT_* constants exactly: a
# transient network/RPC failure must never be indistinguishable from a verse
# that genuinely has no MACULA syntax data. See that module's docstring for
# the full rationale (same bug, same fix, both languages).
RESULT_SUCCESS_WITH_DATA = "SUCCESS_WITH_DATA"
RESULT_SUCCESS_NO_DATA = "SUCCESS_NO_DATA"
RESULT_TRANSIENT_ERROR = "TRANSIENT_ERROR"
RESULT_PERMANENT_ERROR = "PERMANENT_ERROR"  # not raised anywhere yet — see hebrew_analysis_repository docstring


@dataclass(frozen=True)
class GreekVerseSyntaxData:
    phrases: tuple[GreekPhraseAnalysis, ...] = ()
    clauses: tuple[GreekClauseAnalysis, ...] = ()
    semantic_roles: tuple[GreekSemanticRole, ...] = ()
    coreference: tuple[GreekCoreferenceLink, ...] = ()
    alignment_status_by_token: dict[str, str] | None = None
    status: str = RESULT_SUCCESS_NO_DATA

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
            return GreekVerseSyntaxData(status=RESULT_SUCCESS_NO_DATA)
        try:
            connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
        except sqlite3.Error:
            return GreekVerseSyntaxData(status=RESULT_TRANSIENT_ERROR)
        try:
            return _read_local_verse_syntax(connection, verse_ref)
        except sqlite3.Error:
            return GreekVerseSyntaxData(status=RESULT_TRANSIENT_ERROR)
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
        return GreekVerseSyntaxData(status=RESULT_SUCCESS_NO_DATA)

    group_rows = connection.execute(
        "SELECT group_id, group_class, rule, role, predication, token_ids_json, parent_group_id "
        "FROM macula_groups WHERE book=? AND chapter=? AND verse=?",
        (book, chapter, verse),
    ).fetchall()

    import json as _json

    from bible_engine.macula_greek_parser import CLAUSE_CLASS, PHRASE_CLASSES

    role_rows = connection.execute(
        "SELECT predicate_xml_id, role_code, argument_xml_id FROM semantic_role_assignments "
        "WHERE predicate_xml_id IN (SELECT xml_id FROM macula_source_nodes WHERE book=? AND chapter=? AND verse=?)",
        (book, chapter, verse),
    ).fetchall()
    coref_rows = connection.execute(
        "SELECT source_xml_id, link_type, target_xml_id FROM coreference_links "
        "WHERE source_xml_id IN (SELECT xml_id FROM macula_source_nodes WHERE book=? AND chapter=? AND verse=?)",
        (book, chapter, verse),
    ).fetchall()

    # A group's own constituent tokens (a clause/phrase can span a verse
    # boundary — e.g. Mt 28:19-20's single long sentence), a role's
    # argument (often an elided/implicit subject named earlier), or a
    # coreference link's target/referent very commonly lie OUTSIDE this
    # verse's own token set — genuinely real MACULA-supplied cross-verse
    # facts, not an error. ``macula_to_tagnt`` above is scoped to only this
    # verse's own tokens, so any such "other side" xml_id needs a separate,
    # narrowly-targeted lookup rather than silently dropping the whole
    # group member/role/link (which the Supabase import path already
    # resolves globally — this keeps the two backends in real parity, not
    # just verse-local parity).
    #
    # Kept in a SEPARATE ``combined_map`` rather than merged into
    # ``macula_to_tagnt`` itself: a predicate/source xml_id must resolve
    # ONLY via the strict per-verse map — merging would let an xml_id
    # resolved here for one row's "other side" (e.g. a target) leak into
    # and silently override another row's predicate/source lookup, which
    # can point to a genuinely different verse (a real bug hit and fixed
    # during this same investigation).
    other_side_ids = {row["argument_xml_id"] for row in role_rows} | {row["target_xml_id"] for row in coref_rows}
    for row in group_rows:
        other_side_ids.update(_json.loads(row["token_ids_json"]))
    other_side_ids -= set(macula_to_tagnt)
    combined_map = dict(macula_to_tagnt)
    if other_side_ids:
        placeholders = ",".join("?" for _ in other_side_ids)
        extra_rows = connection.execute(
            f"SELECT tagnt_token_id, macula_xml_id FROM token_alignments "
            f"WHERE macula_xml_id IN ({placeholders})",
            tuple(other_side_ids),
        ).fetchall()
        for row in extra_rows:
            combined_map[row["macula_xml_id"]] = row["tagnt_token_id"]

    # A group's own parent is not always the SAME constituent type (a
    # phrase's parent can be a clause and vice versa — see
    # GreekPhraseAnalysis.parent_clause_id / GreekClauseAnalysis.
    # parent_phrase_id's own docstrings). Determine each referenced
    # parent's class: first from this verse's own group_rows, and for any
    # parent not found there (it can lie in a different verse, same as
    # group membership above), a narrowly-targeted extra lookup.
    is_clause_by_group_id = {row["group_id"]: row["group_class"] == CLAUSE_CLASS for row in group_rows}
    unknown_parent_ids = {
        row["parent_group_id"] for row in group_rows if row["parent_group_id"] is not None
    } - set(is_clause_by_group_id)
    if unknown_parent_ids:
        placeholders = ",".join("?" for _ in unknown_parent_ids)
        parent_class_rows = connection.execute(
            f"SELECT group_id, group_class FROM macula_groups WHERE group_id IN ({placeholders})",
            tuple(unknown_parent_ids),
        ).fetchall()
        for prow in parent_class_rows:
            is_clause_by_group_id[prow["group_id"]] = prow["group_class"] == CLAUSE_CLASS

    phrases: list[GreekPhraseAnalysis] = []
    clauses: list[GreekClauseAnalysis] = []
    for row in group_rows:
        macula_token_ids = _json.loads(row["token_ids_json"])
        mapped = tuple(combined_map[mid] for mid in macula_token_ids if mid in combined_map)
        if not mapped:
            continue
        parent_id = row["parent_group_id"]
        parent_is_clause = is_clause_by_group_id.get(parent_id) if parent_id is not None else None
        if row["group_class"] == CLAUSE_CLASS:
            clauses.append(
                GreekClauseAnalysis(
                    clause_id=row["group_id"], clause_type=row["rule"] or "", token_ids=mapped,
                    predicate_id=None,
                    parent_clause_id=parent_id if parent_is_clause else None,
                    parent_phrase_id=parent_id if parent_is_clause is False else None,
                    relation_to_parent=row["predication"] or "",
                )
            )
        elif row["group_class"] in PHRASE_CLASSES:
            phrases.append(
                GreekPhraseAnalysis(
                    phrase_id=row["group_id"], phrase_type=row["group_class"], token_ids=mapped,
                    head_token_id=None,
                    parent_phrase_id=parent_id if parent_is_clause is False else None,
                    parent_clause_id=parent_id if parent_is_clause else None,
                    function=row["role"] or "",
                )
            )

    semantic_roles: list[GreekSemanticRole] = []
    for row in role_rows:
        predicate_token = macula_to_tagnt.get(row["predicate_xml_id"])
        argument_token = combined_map.get(row["argument_xml_id"])
        if predicate_token is None or argument_token is None:
            continue
        semantic_roles.append(
            GreekSemanticRole(
                role_id=f"{predicate_token}.{row['role_code']}.{argument_token}",
                role_type=row["role_code"], predicate_id=predicate_token, token_ids=(argument_token,),
            )
        )

    coreference_by_source: dict[tuple[str, str], list[str]] = {}
    for row in coref_rows:
        source_token = macula_to_tagnt.get(row["source_xml_id"])
        target_token = combined_map.get(row["target_xml_id"])
        if source_token is None or target_token is None:
            # Genuinely unresolvable anywhere in TAGNT (not just outside
            # this verse) — matches the Supabase importer's own skip
            # behavior; never fall back to the raw MACULA xml_id, which
            # would be a differently-typed, inconsistent value.
            continue
        coreference_by_source.setdefault((source_token, row["link_type"]), []).append(target_token)
    coreference = tuple(
        GreekCoreferenceLink(source_token_id=src, link_type=lt, target_token_ids=tuple(targets))
        for (src, lt), targets in coreference_by_source.items()
    )

    has_data = bool(phrases or clauses or semantic_roles or coreference)
    return GreekVerseSyntaxData(
        phrases=tuple(phrases), clauses=tuple(clauses), semantic_roles=tuple(semantic_roles),
        coreference=coreference, alignment_status_by_token=alignment_status_by_token,
        status=RESULT_SUCCESS_WITH_DATA if has_data else RESULT_SUCCESS_NO_DATA,
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
        except Exception:  # noqa: BLE001 - transient: backend unreachable is not "no data"
            return GreekVerseSyntaxData(status=RESULT_TRANSIENT_ERROR)
        try:
            result = client.rpc("get_greek_verse_syntax_bundle", {"p_verse_ref": verse_ref}).execute()
        except Exception:  # noqa: BLE001 - transient: the RPC call itself failed
            return GreekVerseSyntaxData(status=RESULT_TRANSIENT_ERROR)
        payload = result.data or {}
        return _parse_bundle_payload(payload)


def _parse_bundle_payload(payload: dict) -> GreekVerseSyntaxData:
    phrases = tuple(
        GreekPhraseAnalysis(
            phrase_id=str(row["id"]), phrase_type=row["phrase_type"], token_ids=(),
            head_token_id=row.get("head_token_id"), parent_phrase_id=_stringify(row.get("parent_phrase_id")),
            function=row.get("role") or "", parent_clause_id=_stringify(row.get("parent_clause_id")),
        )
        for row in payload.get("phrases", [])
    )
    clauses = tuple(
        GreekClauseAnalysis(
            clause_id=str(row["id"]), clause_type=row.get("clause_type") or "", token_ids=(),
            predicate_id=row.get("predicate_token_id"), parent_clause_id=_stringify(row.get("parent_clause_id")),
            relation_to_parent=row.get("relation_to_parent") or "",
            parent_phrase_id=_stringify(row.get("parent_phrase_id")),
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

    has_data = bool(phrases or clauses or semantic_roles or coreference)
    return GreekVerseSyntaxData(
        phrases=phrases, clauses=clauses, semantic_roles=semantic_roles, coreference=coreference,
        alignment_status_by_token=alignment_status_by_token or None,
        status=RESULT_SUCCESS_WITH_DATA if has_data else RESULT_SUCCESS_NO_DATA,
    )


def _stringify(value: object) -> str | None:
    return str(value) if value is not None else None


# ---------------------------------------------------------------------------
# Backend selection + shared attach logic.
# ---------------------------------------------------------------------------


def _configured_greek_analysis_backend() -> str:
    return (os.environ.get("TEXTUS_GREEK_ANALYSIS_BACKEND", "local") or "local").strip().lower()


def _looks_like_cloud_environment() -> bool:
    """Pure env-var check, deliberately independent of ``auth_config.
    is_local_runtime()`` (which needs a live Streamlit request context and
    would violate this module's zero-Streamlit-dependency invariant — see
    ``tests/test_hebrew_macula_alignment.py::
    test_phase2d_modules_have_no_llm_or_direct_network_dependency``).
    Mirrors only the two unambiguous "definitely cloud" signals
    ``is_local_runtime()`` also short-circuits on."""
    if (os.environ.get("TEXTUS_FORCE_CLOUD") or "").strip().lower() in ("1", "true", "yes"):
        return True
    return (os.environ.get("STREAMLIT_RUNTIME_ENVIRONMENT") or "").strip().lower() == "cloud"


def get_default_greek_analysis_repository() -> GreekAnalysisRepository:
    backend = _configured_greek_analysis_backend()
    if backend == "supabase":
        return SupabaseGreekAnalysisRepository()
    # 2026-09 audit fix: an unset/unrecognized TEXTUS_GREEK_ANALYSIS_BACKEND
    # silently serves the bundled local SQLite dataset instead of the
    # Supabase-backed one — safe (no crash, no data leak) but potentially
    # stale/incomplete in a real deployment that simply forgot to set the
    # env var. Local development/tests are unaffected (no cloud signal),
    # but a detected-cloud runtime gets a loud, one-time warning so the
    # misconfiguration is at least visible to whoever reads the logs.
    if _looks_like_cloud_environment():
        logger.warning(
            "TEXTUS_GREEK_ANALYSIS_BACKEND is '%s' (not 'supabase') in a "
            "detected cloud runtime — serving the bundled local Greek "
            "dataset instead of the Supabase-backed one. If this is "
            "unintentional, set TEXTUS_GREEK_ANALYSIS_BACKEND=supabase.",
            backend,
        )
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
    if data.status in (RESULT_TRANSIENT_ERROR, RESULT_PERMANENT_ERROR):
        # 2026-09 audit fix: never let a failed repository call look like a
        # verse that genuinely has no MACULA syntax data — SYNTAX_GROUNDING_
        # UNAVAILABLE is a distinct value so downstream AI-analysis code
        # (bible_engine.greek_contextual_analysis_service) can refuse to
        # produce/cache a STATUS_OK result built on this degraded input.
        return replace(verse, tokens=new_tokens, syntax_grounding=SYNTAX_GROUNDING_UNAVAILABLE)
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
    "RESULT_PERMANENT_ERROR",
    "RESULT_SUCCESS_NO_DATA",
    "RESULT_SUCCESS_WITH_DATA",
    "RESULT_TRANSIENT_ERROR",
    "GreekVerseSyntaxData",
    "GreekAnalysisRepository",
    "LocalGreekAnalysisRepository",
    "SupabaseGreekAnalysisRepository",
    "get_default_greek_analysis_repository",
    "attach_syntax_via_repository",
]
