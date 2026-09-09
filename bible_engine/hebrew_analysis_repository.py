"""Phase 2D — repository abstraction for the normalized MACULA-sourced
linguistic layer (phrases/clauses/syntax relations/semantic roles/
participants/coreference).

``HebrewAnalysisService`` (Phase 2C, unchanged in its own token-building
logic — see that module's docstring on why) asks a
``HebrewAnalysisRepository`` for one verse's syntax data and attaches the
result to the ``VerseAnalysis`` it already builds from TAHOT/TEHMC/the
Hungarian lexicon. The repository never touches token/morphology/lexical
data — that stays exactly the Phase 2C path, per the Phase 2D authority
rule (MACULA adds syntax, it does not replace the verified foundation).

Two implementations:

* ``LocalHebrewAnalysisRepository`` — reads
  ``bible_engine.hebrew_linguistic_sqlite``, the local SQLite mirror. Used
  for offline development, the deterministic importer's own verification,
  fixtures, and as the default in tests (no network).
* ``SupabaseHebrewAnalysisRepository`` — reads the same normalized shape
  from Supabase Postgres (``supabase/migrations/20260908190000_hebrew_linguistic_layer.sql``),
  via the existing shared ``supabase_client.get_supabase_client()`` — the
  same client/secrets convention every other Supabase-backed module in
  this repo already uses (see ``textus_kb.commentary_translation_store``).
  Fail-closed: any network/auth/query error degrades to "no syntax data
  for this verse" (an empty ``VerseSyntaxData``), never an exception — a
  syntax-layer outage must never break the deterministic token/morphology
  path the rest of the bundle depends on.

Neither implementation is a Streamlit dependency, and neither calls an
LLM.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bible_engine.hebrew_analysis_bundle import (
    ClauseAnalysis,
    CoreferenceLink,
    ParticipantMention,
    PhraseAnalysis,
    SemanticRole,
    SyntaxRelation,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_LINGUISTIC_STORE_PATH = ROOT / "data" / "generated" / "hebrew_linguistic_dev.sqlite3"

MACULA_DATASET_ID = "macula_hebrew_lowfat"

# Phase 2D.1 §12 — the future AI-interpretation layer must be able to tell
# how much of a verse's syntax data is actually grounded in a CONFIRMED
# token alignment before treating it as reliable:
#   FULLY_GROUNDED_SYNTAX    — syntax data exists and every token in the
#                               verse has a confirmed (non-UNRESOLVED)
#                               alignment.
#   PARTIALLY_GROUNDED_SYNTAX — syntax data exists, but at least one token
#                               in the verse is UNRESOLVED (that token
#                               contributes no syntax fact at all — see
#                               hebrew_macula_importer._resolve_leaf_to_token_map
#                               — but OTHER tokens' facts are still present).
#   NO_GROUNDED_SYNTAX        — no syntax data was imported for this verse
#                               at all (e.g. no local/Supabase store
#                               configured, or MACULA had nothing for it).
SYNTAX_GROUNDING_FULL = "FULLY_GROUNDED_SYNTAX"
SYNTAX_GROUNDING_PARTIAL = "PARTIALLY_GROUNDED_SYNTAX"
SYNTAX_GROUNDING_NONE = "NO_GROUNDED_SYNTAX"


@dataclass(frozen=True)
class VerseSyntaxData:
    phrases: tuple[PhraseAnalysis, ...] = ()
    clauses: tuple[ClauseAnalysis, ...] = ()
    syntax_relations: tuple[SyntaxRelation, ...] = ()
    semantic_roles: tuple[SemanticRole, ...] = ()
    participants: tuple[ParticipantMention, ...] = ()
    coreference: tuple[CoreferenceLink, ...] = ()
    syntax_grounding: str = SYNTAX_GROUNDING_NONE

    @property
    def has_syntax(self) -> bool:
        return bool(self.phrases or self.clauses or self.syntax_relations)

    @property
    def has_semantic_roles(self) -> bool:
        return bool(self.semantic_roles)

    @property
    def has_participants(self) -> bool:
        return bool(self.participants)


class HebrewAnalysisRepository(Protocol):
    def get_verse_syntax(self, verse_ref: str) -> VerseSyntaxData: ...

    def dataset_version_signature(self) -> str:
        """A short, stable string identifying exactly which dataset
        revisions are currently active (e.g. ``"macula_hebrew_lowfat:26.04.13,tahot:phase2b"``,
        sorted for determinism). Phase 2D.2's cache layer
        (``bible_engine.hebrew_analysis_cache``) keys cached bundles on
        ``(reference, this signature)`` — since the linguistic dataset is
        immutable within one version, this is the natural, minimal cache
        invalidation key (a version bump changes the signature, which
        changes the cache key, which naturally "invalidates" every old
        entry by simply never being looked up again — no explicit
        invalidation logic needed). Returns ``""`` when unknown (e.g. no
        store reachable) — callers must treat that as "do not cache,
        recompute every time" rather than caching under a placeholder key.
        """
        ...


class LocalHebrewAnalysisRepository:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else DEFAULT_LOCAL_LINGUISTIC_STORE_PATH

    def dataset_version_signature(self) -> str:
        if not self.database_path.exists():
            return ""
        try:
            connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT dataset_id, revision FROM original_language_dataset_versions WHERE is_active = 1 ORDER BY dataset_id"
            ).fetchall()
            connection.close()
        except sqlite3.Error:
            return ""
        return ",".join(f"{row['dataset_id']}:{row['revision']}" for row in rows)

    def get_verse_syntax(self, verse_ref: str) -> VerseSyntaxData:
        if not self.database_path.exists():
            return VerseSyntaxData()
        try:
            connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
        except sqlite3.Error:
            return VerseSyntaxData()
        try:
            return _read_verse_syntax(connection, verse_ref)
        except sqlite3.Error:
            return VerseSyntaxData()
        finally:
            connection.close()


def _read_verse_syntax(connection: sqlite3.Connection, verse_ref: str) -> VerseSyntaxData:
    phrase_rows = connection.execute(
        "SELECT id, phrase_type, head_token_id, parent_phrase_id FROM hebrew_phrases WHERE verse_ref = ?",
        (verse_ref,),
    ).fetchall()
    clause_rows = connection.execute(
        "SELECT id, clause_type, predicate_token_id, subject_token_id, parent_clause_id FROM hebrew_clauses WHERE verse_ref = ?",
        (verse_ref,),
    ).fetchall()
    membership_rows = connection.execute(
        """
        SELECT token_id, phrase_id, clause_id FROM hebrew_syntax_membership
        WHERE phrase_id IN (SELECT id FROM hebrew_phrases WHERE verse_ref = ?)
           OR clause_id IN (SELECT id FROM hebrew_clauses WHERE verse_ref = ?)
        """,
        (verse_ref, verse_ref),
    ).fetchall()
    tokens_by_phrase: dict[int, list[str]] = {}
    tokens_by_clause: dict[int, list[str]] = {}
    for row in membership_rows:
        if row["phrase_id"] is not None:
            tokens_by_phrase.setdefault(row["phrase_id"], []).append(row["token_id"])
        if row["clause_id"] is not None:
            tokens_by_clause.setdefault(row["clause_id"], []).append(row["token_id"])

    phrases = tuple(
        PhraseAnalysis(
            phrase_id=f"macula:phrase:{row['id']}",
            phrase_type=row["phrase_type"],
            token_ids=tuple(dict.fromkeys(tokens_by_phrase.get(row["id"], ()))),
            head_token_id=row["head_token_id"],
            parent_phrase_id=(f"macula:phrase:{row['parent_phrase_id']}" if row["parent_phrase_id"] else None),
            function="",
            source_dataset=MACULA_DATASET_ID,
        )
        for row in phrase_rows
    )
    clauses = tuple(
        ClauseAnalysis(
            clause_id=f"macula:clause:{row['id']}",
            clause_type=row["clause_type"] or "",
            token_ids=tuple(dict.fromkeys(tokens_by_clause.get(row["id"], ()))),
            predicate_id=row["predicate_token_id"],
            subject_id=row["subject_token_id"],
            object_ids=(),
            complement_ids=(),
            modifier_ids=(),
            parent_clause_id=(f"macula:clause:{row['parent_clause_id']}" if row["parent_clause_id"] else None),
            relation_to_parent="",
            word_order="",
            source_dataset=MACULA_DATASET_ID,
        )
        for row in clause_rows
    )

    edge_rows = connection.execute(
        "SELECT id, relation_type, source_role_code, parent_token_id, child_token_id FROM hebrew_syntax_edges WHERE verse_ref = ?",
        (verse_ref,),
    ).fetchall()
    syntax_relations = tuple(
        SyntaxRelation(
            relation_id=f"macula:edge:{row['id']}",
            relation_type=row["relation_type"],
            source_role_code=row["source_role_code"] or "",
            parent_token_id=row["parent_token_id"],
            child_token_id=row["child_token_id"],
            source_dataset=MACULA_DATASET_ID,
        )
        for row in edge_rows
    )

    role_rows = connection.execute(
        "SELECT id, role_code, role_label, predicate_token_id, participant_token_id FROM hebrew_semantic_roles WHERE verse_ref = ?",
        (verse_ref,),
    ).fetchall()
    semantic_roles = tuple(
        SemanticRole(
            role_id=f"macula:role:{row['id']}",
            role_type=row["role_label"] or "",
            token_ids=tuple(tid for tid in (row["participant_token_id"],) if tid),
            predicate_id=row["predicate_token_id"] or "",
            source_dataset=MACULA_DATASET_ID,
            role_code=row["role_code"],
        )
        for row in role_rows
    )

    participant_rows = connection.execute(
        "SELECT id, token_id FROM hebrew_participants WHERE verse_ref = ?", (verse_ref,)
    ).fetchall()
    coref_rows = connection.execute(
        "SELECT id, referring_token_id, participant_id, relation_type FROM hebrew_coreference WHERE verse_ref = ?",
        (verse_ref,),
    ).fetchall()
    referring_by_participant: dict[int, list[str]] = {}
    for row in coref_rows:
        if row["referring_token_id"]:
            referring_by_participant.setdefault(row["participant_id"], []).append(row["referring_token_id"])

    participants = tuple(
        ParticipantMention(
            mention_id=f"macula:participant:{row['id']}",
            token_ids=tuple([row["token_id"]] if row["token_id"] else []) + tuple(referring_by_participant.get(row["id"], ())),
            participant_id=f"macula:participant:{row['id']}",
            entity_id=None,
            entity_label_hu="",
            mention_type="",
            source_dataset=MACULA_DATASET_ID,
        )
        for row in participant_rows
    )
    coreference = tuple(
        CoreferenceLink(
            link_id=f"macula:coref:{row['id']}",
            referring_token_id=row["referring_token_id"],
            participant_id=f"macula:participant:{row['participant_id']}",
            relation_type=row["relation_type"],
            source_dataset=MACULA_DATASET_ID,
        )
        for row in coref_rows
    )

    has_syntax = bool(phrases or clauses or syntax_relations)
    grounding = SYNTAX_GROUNDING_NONE
    if has_syntax:
        alignment_counts = connection.execute(
            """
            SELECT a.alignment_type, COUNT(*) c
            FROM hebrew_token_alignments a
            JOIN hebrew_tokens t ON t.token_id = a.token_id
            JOIN hebrew_verses v ON v.id = t.verse_id
            WHERE v.verse_ref = ?
            GROUP BY a.alignment_type
            """,
            (verse_ref,),
        ).fetchall()
        grounding = _grounding_from_counts({row["alignment_type"]: row["c"] for row in alignment_counts})

    return VerseSyntaxData(
        phrases=phrases,
        clauses=clauses,
        syntax_relations=syntax_relations,
        semantic_roles=semantic_roles,
        participants=participants,
        coreference=coreference,
        syntax_grounding=grounding,
    )


def _grounding_from_counts(counts: dict[str, int]) -> str:
    unresolved = counts.get("UNRESOLVED", 0)
    confirmed = sum(v for k, v in counts.items() if k != "UNRESOLVED")
    if confirmed == 0 and unresolved == 0:
        return SYNTAX_GROUNDING_NONE
    return SYNTAX_GROUNDING_PARTIAL if unresolved > 0 else SYNTAX_GROUNDING_FULL


class SupabaseHebrewAnalysisRepository:
    """Production-capable read path — see the module docstring for the
    fail-closed contract. NOT exercised against a real Supabase project
    from this environment (no credentials available here); see
    docs/hebrew_analysis_v2_phase2d.md §15/§16 for what still needs to run
    against the real project, and
    ``tests/test_hebrew_analysis_repository.py`` for the fake-client test
    coverage this class does have (same pattern as
    ``tests/test_textus_kb/test_commentary_translation_store_supabase.py``)."""

    def dataset_version_signature(self) -> str:
        try:
            from supabase_client import get_supabase_client

            client = get_supabase_client()
            rows = (
                client.table("original_language_dataset_versions")
                .select("dataset_id, revision")
                .eq("is_active", True)
                .execute()
                .data
                or []
            )
        except Exception:  # noqa: BLE001 - fail-closed, see module docstring
            return ""
        return ",".join(f"{row['dataset_id']}:{row['revision']}" for row in sorted(rows, key=lambda r: r["dataset_id"]))

    def get_verse_syntax(self, verse_ref: str) -> VerseSyntaxData:
        try:
            from supabase_client import get_supabase_client

            client = get_supabase_client()
        except Exception:  # noqa: BLE001 - fail-closed, see module docstring
            return VerseSyntaxData()

        try:
            phrase_rows = client.table("hebrew_phrases").select(
                "id, phrase_type, head_token_id, parent_phrase_id"
            ).eq("verse_ref", verse_ref).execute().data or []
            clause_rows = client.table("hebrew_clauses").select(
                "id, clause_type, predicate_token_id, subject_token_id, parent_clause_id"
            ).eq("verse_ref", verse_ref).execute().data or []
            phrase_ids = [row["id"] for row in phrase_rows]
            clause_ids = [row["id"] for row in clause_rows]
            membership_rows: list[dict] = []
            if phrase_ids:
                membership_rows += client.table("hebrew_syntax_membership").select(
                    "token_id, phrase_id, clause_id"
                ).in_("phrase_id", phrase_ids).execute().data or []
            if clause_ids:
                membership_rows += client.table("hebrew_syntax_membership").select(
                    "token_id, phrase_id, clause_id"
                ).in_("clause_id", clause_ids).execute().data or []
            edge_rows = client.table("hebrew_syntax_edges").select(
                "id, relation_type, source_role_code, parent_token_id, child_token_id"
            ).eq("verse_ref", verse_ref).execute().data or []
            role_rows = client.table("hebrew_semantic_roles").select(
                "id, role_code, role_label, predicate_token_id, participant_token_id"
            ).eq("verse_ref", verse_ref).execute().data or []
            participant_rows = client.table("hebrew_participants").select("id, token_id").eq(
                "verse_ref", verse_ref
            ).execute().data or []
            coref_rows = client.table("hebrew_coreference").select(
                "id, referring_token_id, participant_id, relation_type"
            ).eq("verse_ref", verse_ref).execute().data or []

            grounding = SYNTAX_GROUNDING_NONE
            has_syntax = bool(phrase_rows or clause_rows or edge_rows)
            if has_syntax:
                # Phase 2D.2: hebrew_verse_syntax_grounding (migration
                # 20260908223000) computes this server-side in one query,
                # replacing what previously took three round trips (verse
                # id -> its tokens -> their alignment types). Falls back to
                # the old three-query path if the view is not present
                # (e.g. only the base Phase 2D migration has been applied
                # so far) — never a hard dependency on the new migration.
                try:
                    grounding_rows = client.table("hebrew_verse_syntax_grounding").select(
                        "grounding_status"
                    ).eq("verse_ref", verse_ref).limit(1).execute().data or []
                    if grounding_rows:
                        grounding = grounding_rows[0]["grounding_status"]
                    else:
                        grounding = _fetch_grounding_via_fallback_queries(client, verse_ref)
                except Exception:  # noqa: BLE001 - view may not exist yet on this project
                    grounding = _fetch_grounding_via_fallback_queries(client, verse_ref)
        except Exception:  # noqa: BLE001 - fail-closed, see module docstring
            return VerseSyntaxData()

        return _assemble_from_rows(
            phrase_rows, clause_rows, membership_rows, edge_rows, role_rows, participant_rows, coref_rows, grounding
        )


def _fetch_grounding_via_fallback_queries(client, verse_ref: str) -> str:
    """Pre-Phase-2D.2 three-query path, kept as a fallback for a Supabase
    project that only has the base Phase 2D migration applied (the
    hebrew_verse_syntax_grounding view added in
    20260908223000_hebrew_verse_syntax_grounding_view.sql is optional
    infrastructure, not a hard requirement of the base schema)."""
    verse_rows = client.table("hebrew_verses").select("id").eq("verse_ref", verse_ref).limit(1).execute().data or []
    if not verse_rows:
        return SYNTAX_GROUNDING_NONE
    token_rows = client.table("hebrew_tokens").select("token_id").eq("verse_id", verse_rows[0]["id"]).execute().data or []
    token_ids = [row["token_id"] for row in token_rows]
    if not token_ids:
        return SYNTAX_GROUNDING_NONE
    alignment_rows = client.table("hebrew_token_alignments").select("token_id, alignment_type").in_(
        "token_id", token_ids
    ).execute().data or []
    seen: dict[str, str] = {}
    for row in alignment_rows:
        if row["token_id"] not in seen or row["alignment_type"] != "UNRESOLVED":
            seen[row["token_id"]] = row["alignment_type"]
    alignment_counts: dict[str, int] = {}
    for alignment_type in seen.values():
        alignment_counts[alignment_type] = alignment_counts.get(alignment_type, 0) + 1
    return _grounding_from_counts(alignment_counts)


def _assemble_from_rows(
    phrase_rows, clause_rows, membership_rows, edge_rows, role_rows, participant_rows, coref_rows,
    grounding: str = SYNTAX_GROUNDING_NONE,
) -> VerseSyntaxData:
    tokens_by_phrase: dict[int, list[str]] = {}
    tokens_by_clause: dict[int, list[str]] = {}
    for row in membership_rows:
        if row.get("phrase_id") is not None:
            tokens_by_phrase.setdefault(row["phrase_id"], []).append(row["token_id"])
        if row.get("clause_id") is not None:
            tokens_by_clause.setdefault(row["clause_id"], []).append(row["token_id"])

    phrases = tuple(
        PhraseAnalysis(
            phrase_id=f"macula:phrase:{row['id']}",
            phrase_type=row["phrase_type"],
            token_ids=tuple(dict.fromkeys(tokens_by_phrase.get(row["id"], ()))),
            head_token_id=row.get("head_token_id"),
            parent_phrase_id=(f"macula:phrase:{row['parent_phrase_id']}" if row.get("parent_phrase_id") else None),
            function="",
            source_dataset=MACULA_DATASET_ID,
        )
        for row in phrase_rows
    )
    clauses = tuple(
        ClauseAnalysis(
            clause_id=f"macula:clause:{row['id']}",
            clause_type=row.get("clause_type") or "",
            token_ids=tuple(dict.fromkeys(tokens_by_clause.get(row["id"], ()))),
            predicate_id=row.get("predicate_token_id"),
            subject_id=row.get("subject_token_id"),
            object_ids=(),
            complement_ids=(),
            modifier_ids=(),
            parent_clause_id=(f"macula:clause:{row['parent_clause_id']}" if row.get("parent_clause_id") else None),
            relation_to_parent="",
            word_order="",
            source_dataset=MACULA_DATASET_ID,
        )
        for row in clause_rows
    )
    syntax_relations = tuple(
        SyntaxRelation(
            relation_id=f"macula:edge:{row['id']}",
            relation_type=row["relation_type"],
            source_role_code=row.get("source_role_code") or "",
            parent_token_id=row.get("parent_token_id"),
            child_token_id=row.get("child_token_id"),
            source_dataset=MACULA_DATASET_ID,
        )
        for row in edge_rows
    )
    semantic_roles = tuple(
        SemanticRole(
            role_id=f"macula:role:{row['id']}",
            role_type=row.get("role_label") or "",
            token_ids=tuple(tid for tid in (row.get("participant_token_id"),) if tid),
            predicate_id=row.get("predicate_token_id") or "",
            source_dataset=MACULA_DATASET_ID,
            role_code=row["role_code"],
        )
        for row in role_rows
    )
    referring_by_participant: dict[int, list[str]] = {}
    for row in coref_rows:
        if row.get("referring_token_id"):
            referring_by_participant.setdefault(row["participant_id"], []).append(row["referring_token_id"])
    participants = tuple(
        ParticipantMention(
            mention_id=f"macula:participant:{row['id']}",
            token_ids=tuple([row["token_id"]] if row.get("token_id") else []) + tuple(referring_by_participant.get(row["id"], ())),
            participant_id=f"macula:participant:{row['id']}",
            entity_id=None,
            entity_label_hu="",
            mention_type="",
            source_dataset=MACULA_DATASET_ID,
        )
        for row in participant_rows
    )
    coreference = tuple(
        CoreferenceLink(
            link_id=f"macula:coref:{row['id']}",
            referring_token_id=row.get("referring_token_id"),
            participant_id=f"macula:participant:{row['participant_id']}",
            relation_type=row["relation_type"],
            source_dataset=MACULA_DATASET_ID,
        )
        for row in coref_rows
    )
    return VerseSyntaxData(
        phrases=phrases, clauses=clauses, syntax_relations=syntax_relations,
        semantic_roles=semantic_roles, participants=participants, coreference=coreference,
        syntax_grounding=grounding,
    )


# ---------------------------------------------------------------------------
# Phase 2D.2 — backend selection (same env-var/secrets convention as
# textus_kb.commentary_translation_store's TRANSLATION_BACKEND_ENV_VAR;
# default stays "local" so existing callers, tests, and offline
# development are completely unaffected unless this is explicitly
# configured).
# ---------------------------------------------------------------------------

HEBREW_ANALYSIS_BACKEND_ENV_VAR = "TEXTUS_HEBREW_ANALYSIS_BACKEND"


def _configured_hebrew_analysis_backend() -> str:
    """Env-var only, deliberately — unlike
    ``textus_kb.commentary_translation_store``'s dual env-var/Streamlit-
    secrets lookup, this module has an established, tested invariant of
    zero Streamlit dependency at any import depth (see the module
    docstring and ``tests/test_hebrew_macula_alignment.py::
    test_phase2d_modules_have_no_llm_or_direct_network_dependency``, which
    walks the FULL AST including nested/lazy imports). A backend-selection
    flag is a deployment-time setting (container/CI env var), not
    something that needs interactive Streamlit-secrets configuration —
    if that changes later, add it deliberately, with the test's
    expectations updated in the same commit."""
    return os.environ.get(HEBREW_ANALYSIS_BACKEND_ENV_VAR, "").strip().lower() or "local"


def get_default_hebrew_analysis_repository(
    *, local_store_path: str | Path | None = None
) -> "HebrewAnalysisRepository":
    """The single place backend selection happens — ``HebrewAnalysisService``
    calls this for its default so no UI or service code ever branches on
    the backend itself. Configured via the ``TEXTUS_HEBREW_ANALYSIS_BACKEND``
    env var — default ``"local"`` (``LocalHebrewAnalysisRepository``),
    matching the existing dev/test-safe default every current caller
    already relies on. An explicit ``linguistic_repository=`` argument to
    ``HebrewAnalysisService`` always overrides this, exactly like an
    explicit ``database_path`` overrides backend selection in
    ``textus_kb.commentary_translation_store``."""
    if _configured_hebrew_analysis_backend() == "supabase":
        return SupabaseHebrewAnalysisRepository()
    return LocalHebrewAnalysisRepository(local_store_path)


__all__ = [
    "DEFAULT_LOCAL_LINGUISTIC_STORE_PATH",
    "HEBREW_ANALYSIS_BACKEND_ENV_VAR",
    "HebrewAnalysisRepository",
    "LocalHebrewAnalysisRepository",
    "MACULA_DATASET_ID",
    "SYNTAX_GROUNDING_FULL",
    "SYNTAX_GROUNDING_NONE",
    "SYNTAX_GROUNDING_PARTIAL",
    "SupabaseHebrewAnalysisRepository",
    "VerseSyntaxData",
    "get_default_hebrew_analysis_repository",
]
