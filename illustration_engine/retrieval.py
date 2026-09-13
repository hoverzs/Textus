"""Phase 3I / 3I.1 / 3I.2: user-facing illustration retrieval.

A provider-independent, THREE-stage retrieval layer over the same
`illustration_units` corpus the reviewer/QA tooling already governs.
Same dependency-injection pattern as `enrichment_pipeline.py`/
`qa_agent.py`: the caller supplies `llm_generate: Callable[[str], str]`;
this module owns candidate selection, prompt construction, and
fail-closed response parsing -- no Streamlit dependency, no network
code of its own.

TWO RETRIEVAL MODES -- never conflated, never user-toggleable from this
module (the caller decides which one applies, see `RetrievalMode`):

- PRODUCTION: only `published_illustration_units` (status='published'
  AND source license publishable) -- the SAME fail-closed gate the rest
  of the app already trusts for public retrieval.
- DEVELOPMENT: `qa_status='passed'` units regardless of human-review
  status, for internal QA testing -- source rights must STILL be
  publishable, checksum STILL verified. Deliberately does NOT touch
  `human_reviewed_at`, `status`, `approved`, or `published` -- this
  module has no write path to `illustration_units` at all.

THREE-STAGE PIPELINE (Phase 3I.2 -- see PHASE_3I2_ROOT_CAUSE below for
why Stage A gained a planning step and lost its old fallback):

  Stage 0 (`plan_retrieval_intent`) -- Gemini call, but NOT the ranker.
  Turns (Bible reference, RÚF passage text, optional theme/occasion)
  into a structured `RetrievalIntent` (free-text Hungarian
  keywords/concepts + controlled-vocabulary topic/homiletic-function
  slugs). This step CANNOT return a candidate/story id and cannot write
  story content -- `RetrievalIntent` has no field for either, so there
  is no way for a malformed or adversarial planner response to leak
  fabricated content past this stage even in principle.

  Stage A (`find_candidates`) -- deterministic, local, no LLM call:
  scores every mode-eligible, provenance-verified unit against the
  `RetrievalIntent` with `local_relevance_score` (title/summary/
  moral/text lexical overlap + controlled-taxonomy topic/function
  match) and keeps only candidates clearing `MIN_LOCAL_RELEVANCE_SCORE`.
  Candidates below threshold are DROPPED, not backfilled -- if nothing
  clears the bar, Stage A returns an empty list and Stage B is never
  called (`retrieve_illustrations` short-circuits, exactly like the
  existing "no candidates" case did before this phase).

  Stage B (`rank_candidates` via `build_ranking_prompt`/
  `parse_ranking_response`) -- Gemini sees ONLY the candidate list (not
  the whole corpus) and may ONLY select `unit_id`s FROM that list, and
  MAY reject all of them. A malformed response, one naming an ID
  outside the candidate set, or one whose score falls below
  `MIN_RANK_SCORE`, is dropped/ignored -- see `parse_ranking_response`
  and the filtering in `retrieve_illustrations`. THE MODEL NEVER
  GENERATES A STORY -- there is no field in the ranking response
  contract for one; the actual `modern_hu_text` shown to the end user
  always comes verbatim from the candidate's own DB row, never from the
  model's ranking response.

PHASE_3I2_ROOT_CAUSE: manual local QA on Phase 3I found the ranker
surfacing obviously unrelated candidates (period-piece English
anecdotes with no thematic link to the searched passage). Root cause,
confirmed by re-reading the Phase 3I code: `retrieve_illustrations`
built its FTS query from `" ".join([theme, passage_reference,
occasion])` -- for a typical search this was JUST the bare Bible
reference ("Lk 15,11-24"), tokenizing to ["Lk", "15", "11", "24"],
which essentially never matches real Hungarian story text. `passage_
text` (the actual RÚF verses) was accepted as a parameter but was NEVER
included in the Stage-A query -- only used later, as Stage-B context.
When FTS found zero rows (the near-universal case), `find_candidates`
fell back to an UNFILTERED "most recently added" window so the ranker
would have "something to rank" -- a semantically random candidate pool
that a ranker forced to reason over 20-30 unrelated stories cannot
reliably resist choosing from. This phase removes that fallback
entirely and replaces the raw-reference FTS query with the
planner+hybrid-scoring pipeline described above. See `tests/test_retrieval.py` for the regression coverage. This phase's
audit also ran a one-off, read-only diagnostic script against the real
corpus (not part of the shipped codebase) to sanity-check and tune the
weights/thresholds below against real data rather than synthetic
fixtures alone.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Protocol

from illustration_engine.illustration_sqlite import (
    PILOT_HOMILETIC_FUNCTIONS,
    PILOT_TOPICS,
)
from illustration_engine.source_registry import PUBLISHABLE_LICENSE_STATUSES

logger = logging.getLogger(__name__)

RetrievalMode = str  # "production" | "development"
ALLOWED_RETRIEVAL_MODES = frozenset({"production", "development"})

DEFAULT_CANDIDATE_LIMIT = 30
DEFAULT_TOP_N = 5
MIN_TOP_N = 3
MAX_TOP_N = 5

# Phase 3I.2 tuning constants. Deliberately conservative (biased toward
# 0 results over a weak result) -- tuned against the real 157-unit
# QA-passed corpus during this phase's audit, not against a synthetic
# benchmark. See the module docstring's PHASE_3I2_ROOT_CAUSE note.
_MAX_PLANNER_LIST_ITEMS = 12
_MAX_PLANNER_ITEM_LEN = 80
_MIN_TOKEN_LEN = 3

_TITLE_MATCH_WEIGHT = 2.0
_SUMMARY_MATCH_WEIGHT = 1.5
_MORAL_MATCH_WEIGHT = 1.5
_STORY_TEXT_MATCH_WEIGHT = 0.4
_STORY_TEXT_MATCH_CAP = 5  # story text is long/noisy; cap its raw token-overlap count before weighting
_TOPIC_MATCH_WEIGHT = 4.0
_FUNCTION_MATCH_WEIGHT = 2.0

MIN_LOCAL_RELEVANCE_SCORE = 3.0
# Tuned from 0.5 to 0.6 after this phase's real-corpus diagnostic
# (6 named passages against the real 157-unit QA-passed corpus): 0.5
# still let through a small number of visibly weaker/more tenuous
# matches at the bottom of an otherwise strong 5-result list (e.g. a
# 0.55-0.60-scored candidate whose connection was real but thin,
# alongside 0.80-0.95-scored candidates with concrete, specific textual
# parallels). 0.6 trims that thin tail without touching any of the
# genuinely strong matches observed in that run.
MIN_RANK_SCORE = 0.6

# A small, deliberately coarse Hungarian function-word list -- purely to
# stop trivially common words (articles, conjunctions, auxiliary verbs)
# from inflating lexical overlap scores. NOT a real NLP stopword list or
# stemmer; same "coarse heuristic, not a linguistics system" spirit as
# `enrichment_pipeline._hallucination_guard`.
_HU_STOPWORDS = frozenset(
    {
        "a", "az", "és", "hogy", "nem", "meg", "egy", "is", "de", "mint",
        "volt", "van", "lesz", "ez", "az", "ő", "ők", "mi", "ti", "azt",
        "ezt", "akkor", "majd", "már", "még", "csak", "vagy", "mert",
        "aki", "ami", "amely", "ahogy", "amikor", "ahol", "amit", "ha",
        "igen", "nagyon", "úgy", "így", "el", "ki", "be", "fel", "le",
        "oda", "ide", "ott", "itt", "egyik", "másik", "minden", "sok",
        "kevés", "volna", "lehet", "kell", "által", "után", "előtt",
    }
)


@dataclass(frozen=True)
class RetrievalIntent:
    """Stage 0's output. Pure retrieval-intent data -- structurally
    incapable of carrying a candidate/story id or story content (no
    field exists for either), so a malformed or adversarial planner
    response can never smuggle fabricated content past this stage."""

    keywords_hu: tuple[str, ...] = ()
    concepts_hu: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    preferred_homiletic_functions: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (
            self.keywords_hu or self.concepts_hu or self.topics
            or self.preferred_homiletic_functions
        )


# Phase 3I.3: fail-closed observability reason codes -- WHY an empty
# result happened, distinct from THAT it happened. Never shown as
# technical detail in the production end-user UI (see
# `illustration_retrieval_ui.py`); available in development/localhost
# mode for audits like the one that found the Phase 3I.3 root cause.
REASON_OK = "ok"
REASON_NO_INTENT = "no_intent"
REASON_NO_LOCAL_CANDIDATES = "no_local_candidates"
REASON_RANKER_REJECTED_ALL = "ranker_rejected_all"
REASON_PLANNER_ERROR = "planner_error"
REASON_RANKING_ERROR = "ranking_error"
# 2026-09 runtime retrieval cutover: Stage A's candidate fetch (now
# potentially a real network call -- SupabaseIllustrationRepository's RPC
# -- not just a local file read) was UNGUARDED, unlike the planner/ranker
# LLM stages either side of it. A genuine RPC/network failure there would
# have propagated as an unhandled exception straight into the Streamlit
# callback, instead of failing closed into a distinguishable diagnostics
# reason the way every other stage already does. Distinct from
# REASON_NO_LOCAL_CANDIDATES on purpose: that means "the fetch succeeded
# and genuinely found nothing above threshold" (a normal, expected
# outcome); this means "the fetch itself could not complete" (an
# infrastructure problem the end-user UI must show differently -- never
# as "nincs találat").
REASON_CANDIDATE_FETCH_ERROR = "candidate_fetch_error"

_DIAGNOSTIC_TOP_SCORES_LIMIT = 8


@dataclass(frozen=True)
class RetrievalDiagnostics:
    """Structured, content-free diagnosis of one `retrieve_illustrations`
    run -- counts, scores, and a `reason` code, NEVER raw LLM prompt/
    response text. `reason` is one of the `REASON_*` constants above."""

    reason: str
    intent: RetrievalIntent
    stage_a_pool_size: int
    stage_a_candidate_count: int
    stage_a_top_scores: tuple[tuple[int, float], ...]
    stage_b_parsed_count: int
    stage_b_accepted_count: int
    final_count: int


@dataclass(frozen=True)
class RetrievalCandidate:
    unit_id: int
    title_hu: str
    modern_hu_text: str
    summary_hu: str
    moral_hu: str | None
    topics: tuple[str, ...]
    tone: str | None
    homiletic_functions: tuple[str, ...]
    source_title: str
    source_code: str
    tradition: str | None
    license_status: str
    provenance_status: str  # "published" | "development_qa_passed"


#: Stage B match-tier classification, ordered highest-priority first.
#: A DIRECT_ANALOGY candidate is always ranked above a THEMATIC_SUPPORT
#: one, which is always ranked above ADJACENT_THEME, etc, regardless of
#: how close their raw relevance scores are -- see the tier-aware sort
#: in `_run_retrieval_pipeline_impl`. "WEAK" is both a valid LLM-chosen
#: tier AND the fail-closed default when `match_tier` is missing/invalid
#: in the ranker's JSON response (never guess a higher tier).
MATCH_TIER_ORDER: dict[str, int] = {
    "DIRECT_ANALOGY": 0,
    "THEMATIC_SUPPORT": 1,
    "ADJACENT_THEME": 2,
    "WEAK": 3,
}


@dataclass(frozen=True)
class RankedIllustration:
    unit_id: int
    reason: str
    score: float
    match_tier: str = "WEAK"
    #: Stage B's explicit admission gate (2026-09-13, round 2) -- a
    #: candidate only reaches the final results if `keep` is True.
    #: Fail-closed default is False: an explicit JSON `"keep": true` is
    #: required, missing/non-bool/False all mean "drop". `match_tier ==
    #: "WEAK"` additionally HARD-forces `keep = False` regardless of what
    #: the model wrote for `keep` -- a tier alone (especially
    #: DIRECT_ANALOGY) must never be trusted to imply admission; see
    #: `parse_ranking_response`.
    keep: bool = False


@dataclass(frozen=True)
class IllustrationRetrievalResult:
    unit_id: int
    title_hu: str
    modern_hu_text: str
    summary_hu: str
    moral_hu: str | None
    topics: tuple[str, ...]
    tone: str | None
    homiletic_functions: tuple[str, ...]
    source_title: str
    source_attribution: str
    provenance_status: str
    rank_reason: str
    rank_score: float
    match_tier: str = "WEAK"
    #: The SAME text as `rank_reason` -- Stage B's ranker prompt was
    #: tightened (2026-09-13) so that one field now serves both purposes
    #: (an audit-trail reason AND UI-facing copy), rather than asking the
    #: LLM for two overlapping explanations in one call. Exposed under
    #: its own name so `illustration_retrieval_ui` can display it
    #: ("Kapcsolódás az igéhez: ...") without the UI layer needing to
    #: know it's literally `rank_reason`.
    relation_hu: str = ""


def _fold_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _canonicalize_slug(raw: object, vocabulary: frozenset[str]) -> str | None:
    """Same safe pattern as `enrichment_pipeline._canonicalize_slug`
    (Phase 3H.1), duplicated locally rather than cross-imported -- this
    module already keeps its own small `_fold_diacritics` copy for the
    same reason. Exact diacritic-folded match against EXACTLY ONE
    vocabulary member, never fuzzy/semantic matching, never invents a
    new slug. Returns None (drop) when `raw` isn't a recognizable member
    of `vocabulary`."""
    if not isinstance(raw, str):
        return None
    if raw in vocabulary:
        return raw
    folded = _fold_diacritics(raw.strip().lower())
    matches = [slug for slug in vocabulary if _fold_diacritics(slug.lower()) == folded]
    return matches[0] if len(matches) == 1 else None


def _canonicalize_slug_list(raw: object, vocabulary: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    seen: list[str] = []
    for item in raw:
        resolved = _canonicalize_slug(item, vocabulary)
        if resolved and resolved not in seen:
            seen.append(resolved)
    return tuple(seen)


def _clean_free_text_list(raw: object) -> tuple[str, ...]:
    """For `keywords_hu`/`concepts_hu`: free Hungarian text, NOT
    controlled vocabulary -- only bounded (count + length) and
    deduplicated, never validated against a fixed slug set."""
    if not isinstance(raw, list):
        return ()
    seen: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or len(cleaned) > _MAX_PLANNER_ITEM_LEN:
            continue
        folded = cleaned.lower()
        if folded not in {s.lower() for s in seen}:
            seen.append(cleaned)
        if len(seen) >= _MAX_PLANNER_LIST_ITEMS:
            break
    return tuple(seen)


def _tokenize_hu(text: str) -> frozenset[str]:
    """Coarse, deterministic Hungarian tokenizer for local relevance
    scoring: lowercase, diacritic-fold, split on non-word boundaries,
    drop very short tokens and the small `_HU_STOPWORDS` set. Not a
    stemmer -- inflected forms of the same root are NOT unified, which
    biases scoring toward precision (fewer, more deliberate matches)
    over recall, matching this phase's stated goal ("0 találat legyen
    jobb, mint irreleváns találat")."""
    words = re.findall(r"\w+", text or "", flags=re.UNICODE)
    return frozenset(
        folded
        for w in words
        if len(w) >= _MIN_TOKEN_LEN
        and (folded := _fold_diacritics(w.lower())) not in _HU_STOPWORDS
    )


def _intent_tokens(intent: RetrievalIntent) -> frozenset[str]:
    combined = " ".join((*intent.keywords_hu, *intent.concepts_hu))
    return _tokenize_hu(combined)


def local_relevance_score(candidate: RetrievalCandidate, intent: RetrievalIntent) -> float:
    """Stage A's deterministic hybrid score -- PUBLIC so both
    `find_candidates` and the real-corpus diagnostic (Phase 3I.2 point 7
    of the audit) can report it directly. Combines:

    - lexical overlap between the intent's keywords/concepts and the
      candidate's title_hu / summary_hu / moral_hu / modern_hu_text
      (title/summary/moral weighted higher -- they are curated and
      concise; the full story text is long and noisy, so its
      contribution is both down-weighted and capped);
    - controlled-taxonomy overlap: intent.topics vs candidate.topics,
      intent.preferred_homiletic_functions vs candidate.
      homiletic_functions.

    Returns 0.0 for an empty intent (no keywords/concepts/topics/
    functions at all) -- deliberately: an empty intent must never look
    "neutral enough to pass," it must fail every candidate, so a
    planner failure degrades to an empty result exactly like a
    genuinely irrelevant corpus does."""
    if intent.is_empty():
        return 0.0

    intent_tok = _intent_tokens(intent)
    score = 0.0
    if intent_tok:
        title_overlap = len(_tokenize_hu(candidate.title_hu) & intent_tok)
        summary_overlap = len(_tokenize_hu(candidate.summary_hu) & intent_tok)
        moral_overlap = len(_tokenize_hu(candidate.moral_hu or "") & intent_tok)
        text_overlap = min(
            len(_tokenize_hu(candidate.modern_hu_text) & intent_tok), _STORY_TEXT_MATCH_CAP
        )
        score += title_overlap * _TITLE_MATCH_WEIGHT
        score += summary_overlap * _SUMMARY_MATCH_WEIGHT
        score += moral_overlap * _MORAL_MATCH_WEIGHT
        score += text_overlap * _STORY_TEXT_MATCH_WEIGHT

    if intent.topics:
        topic_overlap = len(set(candidate.topics) & set(intent.topics))
        score += topic_overlap * _TOPIC_MATCH_WEIGHT
    if intent.preferred_homiletic_functions:
        function_overlap = len(
            set(candidate.homiletic_functions) & set(intent.preferred_homiletic_functions)
        )
        score += function_overlap * _FUNCTION_MATCH_WEIGHT

    return score


def _fetch_taxonomy(connection, unit_id: int) -> tuple[tuple[str, ...], str | None, tuple[str, ...]]:
    rows = connection.execute(
        "SELECT t.category, t.slug FROM illustration_unit_tags ut JOIN tags t ON t.id = ut.tag_id "
        "WHERE ut.unit_id = ? ORDER BY t.category, t.slug",
        (unit_id,),
    ).fetchall()
    topics = tuple(slug for category, slug in rows if category == "topic")
    tones = [slug for category, slug in rows if category == "tone"]
    functions = tuple(slug for category, slug in rows if category == "function")
    return topics, (tones[0] if tones else None), functions


def _verify_checksum(connection, unit_id: int) -> bool:
    """Fail-closed provenance check: recompute the story's original_text
    checksum and compare against the stored one. A mismatch excludes the
    candidate entirely -- retrieval never surfaces a unit whose source
    integrity cannot be confirmed, in EITHER mode."""
    row = connection.execute(
        """
        SELECT st.original_text, st.original_text_checksum
        FROM illustration_units u JOIN stories st ON st.id = u.story_id
        WHERE u.id = ?
        """,
        (unit_id,),
    ).fetchone()
    if row is None:
        return False
    original_text, checksum = row
    if not checksum:
        return False
    return hashlib.sha256(original_text.encode("utf-8")).hexdigest() == checksum


class IllustrationCandidateRepository(Protocol):
    """Data-access boundary for Stage A -- everything ABOVE this line in
    the module (Stage 0 planner, `local_relevance_score`, thresholds,
    Stage B ranker/prompt/parsing, diagnostics, logging) is completely
    backend-agnostic and untouched by which implementation of this
    Protocol a caller supplies. Added 2026-09 (runtime retrieval cutover)
    specifically so introducing a Supabase-backed production read path
    required zero changes to scoring/ranking semantics -- only a new
    class implementing this one method."""

    def fetch_eligible_units(self, *, mode: RetrievalMode) -> list[RetrievalCandidate]:
        """Returns every mode-eligible, provenance-verified candidate,
        UNSCORED and UNFILTERED by relevance -- scoring/threshold
        application happens uniformly in `_fetch_and_score_candidates`
        regardless of which backend produced the list."""
        ...


class LocalSqliteIllustrationRepository:
    """The pre-2026-09 SQLite query logic, unchanged, just moved into
    its own class so it can implement `IllustrationCandidateRepository`
    alongside `SupabaseIllustrationRepository`. Behavior is byte-
    identical to what `_fetch_and_score_candidates` used to do inline:
    same two mode-gated queries, same per-row `_verify_checksum`/
    `_fetch_taxonomy` calls."""

    def __init__(self, connection) -> None:
        self.connection = connection

    def fetch_eligible_units(self, *, mode: RetrievalMode) -> list[RetrievalCandidate]:
        connection = self.connection
        publishable_list = ", ".join(f"'{s}'" for s in sorted(PUBLISHABLE_LICENSE_STATUSES))

        if mode == "production":
            query = """
                SELECT p.id, p.title_hu, p.modern_hu_text, p.summary_hu, p.moral_hu,
                       s.title, s.code, s.tradition, s.license_status
                FROM published_illustration_units p
                JOIN stories st ON st.id = p.story_id
                JOIN sources s ON s.id = st.source_id
                ORDER BY p.id
            """
            provenance_status = "published"
        else:
            query = f"""
                SELECT u.id, u.title_hu, u.modern_hu_text, u.summary_hu, u.moral_hu,
                       s.title, s.code, s.tradition, s.license_status
                FROM illustration_units u
                JOIN stories st ON st.id = u.story_id
                JOIN sources s ON s.id = st.source_id
                WHERE u.qa_status = 'passed'
                  AND s.license_status IN ({publishable_list})
                ORDER BY u.id
            """
            provenance_status = "development_qa_passed"

        rows = connection.execute(query).fetchall()

        candidates: list[RetrievalCandidate] = []
        for row in rows:
            (
                unit_id, title_hu, modern_hu_text, summary_hu, moral_hu,
                source_title, source_code, tradition, license_status,
            ) = row
            if not _verify_checksum(connection, unit_id):
                continue
            topics, tone, functions = _fetch_taxonomy(connection, unit_id)
            candidates.append(
                RetrievalCandidate(
                    unit_id=unit_id, title_hu=title_hu, modern_hu_text=modern_hu_text,
                    summary_hu=summary_hu, moral_hu=moral_hu, topics=topics, tone=tone,
                    homiletic_functions=functions, source_title=source_title, source_code=source_code,
                    tradition=tradition, license_status=license_status,
                    provenance_status=provenance_status,
                )
            )
        return candidates


class SupabaseIllustrationRepository:
    """Production read path (2026-09 runtime cutover) -- a SINGLE
    PostgREST RPC call (`get_published_illustration_candidates()`, see
    `supabase/migrations/20260913120000_illustration_corpus_layer.sql`),
    no N+1: the RPC itself joins/aggregates tags and source fields
    server-side, so this class issues exactly one HTTP request per
    `fetch_eligible_units` call, regardless of corpus size.

    Uses the ANON/PUBLISHABLE client (`supabase_client.get_supabase_
    client()`) -- NEVER service_role. The RPC is SECURITY DEFINER and
    already independently re-derives `status='published' AND source
    license publishable` on every call (see the migration's own
    comment), so the anon key is genuinely safe here, and no elevated
    credential is needed or used for retrieval.

    Only supports `mode="production"` -- there is no Supabase-side
    equivalent of the SQLite development view (`qa_status='passed'`,
    pre-publish preview) yet; that remains local-SQLite-only until a
    dedicated dev-mode RPC is built as a separate, later change."""

    def __init__(self, client=None) -> None:
        self._client = client

    def _resolve_client(self):
        if self._client is not None:
            return self._client
        from supabase_client import get_supabase_client

        return get_supabase_client()

    def fetch_eligible_units(self, *, mode: RetrievalMode) -> list[RetrievalCandidate]:
        if mode != "production":
            raise NotImplementedError(
                f"SupabaseIllustrationRepository only supports mode='production' "
                f"(got {mode!r}) -- there is no Supabase-side development-mode RPC yet."
            )
        client = self._resolve_client()
        result = client.rpc("get_published_illustration_candidates", {}).execute()
        rows = result.data or []
        return [
            RetrievalCandidate(
                unit_id=row["unit_id"], title_hu=row["title_hu"],
                modern_hu_text=row["modern_hu_text"], summary_hu=row["summary_hu"],
                moral_hu=row.get("moral_hu"), topics=tuple(row.get("topics") or ()),
                tone=row.get("tone"), homiletic_functions=tuple(row.get("homiletic_functions") or ()),
                source_title=row["source_title"], source_code=row["source_code"],
                tradition=row.get("tradition"), license_status=row["license_status"],
                provenance_status="published",
            )
            for row in rows
        ]


def _as_repository(connection_or_repository) -> IllustrationCandidateRepository:
    """Backward-compatible dispatch: every public entry point in this
    module (`find_candidates`, `retrieve_illustrations`, etc.) accepted
    a raw `sqlite3.Connection` as its first positional argument before
    the 2026-09 runtime cutover -- every existing caller and every
    existing test in `tests/test_retrieval.py` still does. Rather than
    change that call shape (and every call site), this dispatches on
    duck-typed shape: an object that already implements `fetch_eligible_
    units` (a repository) is used as-is; anything else is assumed to be
    a DB-API connection and wrapped in `LocalSqliteIllustrationRepository`,
    exactly reproducing this module's pre-cutover behavior."""
    if hasattr(connection_or_repository, "fetch_eligible_units"):
        return connection_or_repository
    return LocalSqliteIllustrationRepository(connection_or_repository)


def _fetch_and_score_candidates(
    connection, *, intent: RetrievalIntent, mode: RetrievalMode
) -> list[tuple[RetrievalCandidate, float]]:
    """The mode-gated, checksum-verified, fully-scored candidate pool --
    UNFILTERED by any relevance threshold, sorted by score descending.
    Shared by `find_candidates` (which applies threshold+limit) and the
    diagnostics pipeline (`retrieve_illustrations_with_diagnostics`,
    which needs the raw pool size and top scores even when nothing
    clears the threshold).

    `connection` accepts EITHER a raw `sqlite3.Connection` (wrapped in
    `LocalSqliteIllustrationRepository`) OR an already-constructed
    `IllustrationCandidateRepository` (e.g. `SupabaseIllustrationRepository`)
    -- see `_as_repository`. `local_relevance_score` itself never knows
    or cares which backend produced a `RetrievalCandidate`."""
    if mode not in ALLOWED_RETRIEVAL_MODES:
        raise ValueError(f"mode must be one of {sorted(ALLOWED_RETRIEVAL_MODES)}, got {mode!r}")

    repository = _as_repository(connection)
    candidates = repository.fetch_eligible_units(mode=mode)
    scored = [(c, local_relevance_score(c, intent)) for c in candidates]
    scored.sort(key=lambda pair: -pair[1])
    return scored


def find_candidates(
    connection,
    *,
    intent: RetrievalIntent,
    mode: RetrievalMode,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    min_relevance: float = MIN_LOCAL_RELEVANCE_SCORE,
) -> list[RetrievalCandidate]:
    """Stage A: deterministic, local candidate retrieval. No LLM call.

    Phase 3I.2: no longer an FTS-narrowed query with an unfiltered
    fallback (see module docstring, PHASE_3I2_ROOT_CAUSE) -- fetches
    every mode-eligible, provenance-verified unit, scores each with
    `local_relevance_score(candidate, intent)`, drops anything below
    `min_relevance`, and returns the top `limit` by score. The corpus
    is small enough (low hundreds of units) that a full scan is cheap;
    this is a deliberate simplification for the current corpus size,
    not a claim that it will always be the right approach -- worth
    revisiting with a DB-side pre-filter if the corpus grows by orders
    of magnitude.

    `mode="production"`: rows from `published_illustration_units` only
    (status='published' AND source license publishable -- the view
    itself already enforces this).
    `mode="development"`: rows with `qa_status='passed'` AND source
    license publishable, REGARDLESS of human-review `status` -- never
    touches or reads `human_reviewed_at`/`approved`/`published` as a
    gate, purely `qa_status`.

    Both modes additionally verify each candidate's raw-story checksum
    before inclusion (`_verify_checksum`) -- a provenance failure
    excludes the candidate silently, it is never surfaced as an error to
    the end user (this is expected to be rare/never in practice; the
    fail-closed behavior is the point)."""
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit!r}")
    scored = _fetch_and_score_candidates(connection, intent=intent, mode=mode)
    return [c for c, s in scored if s >= min_relevance][:limit]


def build_query_planner_prompt(
    *, passage_reference: str, passage_text: str, theme: str, occasion: str
) -> str:
    """Stage 0's prompt. Explicitly forbidden from proposing a candidate/
    story id or writing any story content -- the requested JSON shape
    has no field for either. `topics`/`preferred_homiletic_functions`
    are asked for from a CLOSED list (shown in the prompt); the real
    safety boundary is `parse_planner_response`'s post-hoc
    canonicalization against `PILOT_TOPICS`/`PILOT_HOMILETIC_FUNCTIONS`,
    never trust in the model following the closed-list instruction
    alone."""
    context_lines = [f"Igehely: {passage_reference or 'nincs megadva'}"]
    if passage_text.strip():
        context_lines.append(f"Bibliai szöveg (RÚF): {passage_text.strip()[:2000]}")
    if theme.strip():
        context_lines.append(f"Téma/kulcsszavak: {theme.strip()}")
    if occasion.strip():
        context_lines.append(f"Alkalom: {occasion.strip()}")
    context_block = "\n".join(context_lines)

    topics_list = ", ".join(sorted(PILOT_TOPICS))
    functions_list = ", ".join(sorted(PILOT_HOMILETIC_FUNCTIONS))

    return f"""\
RETRIEVAL INTENT TERVEZÉS

Te egy retrieval-előkészítő lépés vagy egy magyar református prédikációs \
illusztráció-kereső rendszerben. A FELADATOD KIZÁRÓLAG az, hogy az alábbi \
textushoz kereséshez használható kulcsszavakat/fogalmakat állíts elő -- \
NEM választasz illusztrációt, NEM írsz történetet, NEM adsz vissza \
azonosítót. A kimeneted csak arra szolgál, hogy egy KÜLÖN, determinisztikus \
lépés ez alapján pontszámozza a már meglévő, adatbázisban tárolt \
illusztráció-jelölteket.

KONTEXTUS:
{context_block}

FELADAT:
- adj 4-10 rövid, magyar KULCSSZÓT a "keywords_hu" mezőbe (konkrét \
  szavak/kifejezések, amik szó szerint előfordulhatnak egy ehhez a \
  textushoz illő illusztráció címében/összefoglalójában/tanulságában);
- adj 3-8 rövid FOGALMAT/TÉMÁT a "concepts_hu" mezőbe (a textus \
  központi mozgása/feszültsége/üzenete, pl. "hazatérés", "elveszettség", \
  "megbocsátás", "apa és fiú" egy tékozló fiú textusnál);
- a "topics" mezőbe KIZÁRÓLAG az alábbi zárt listából válassz (0-3 \
  elem, üres lista is helyes, ha egyik sem illik pontosan):
  {topics_list}
- a "preferred_homiletic_functions" mezőbe KIZÁRÓLAG az alábbi zárt \
  listából válassz (0-2 elem, üres lista is helyes):
  {functions_list}

KIMENET -- KIZÁRÓLAG ezt a JSON alakot add vissza, más szöveg nélkül:
{{
  "keywords_hu": ["..."],
  "concepts_hu": ["..."],
  "topics": ["..."],
  "preferred_homiletic_functions": ["..."]
}}"""


def _extract_json_object(raw: str) -> dict | None:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    candidate = text[start : end + 1]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_planner_response(raw: str) -> RetrievalIntent:
    """Fail-closed: unparseable JSON, or a payload with no usable
    fields, yields an EMPTY `RetrievalIntent` -- never an exception,
    never a guess. `topics`/`preferred_homiletic_functions` are
    canonicalized against the closed controlled vocabulary (exact
    diacritic-folded match only, same rigor as Phase 3H.1's taxonomy
    canonicalization); anything not uniquely resolvable is DROPPED, not
    passed through. `keywords_hu`/`concepts_hu` are free text, only
    bounded/deduplicated."""
    payload = _extract_json_object(raw)
    if payload is None:
        return RetrievalIntent()
    return RetrievalIntent(
        keywords_hu=_clean_free_text_list(payload.get("keywords_hu")),
        concepts_hu=_clean_free_text_list(payload.get("concepts_hu")),
        topics=_canonicalize_slug_list(payload.get("topics"), PILOT_TOPICS),
        preferred_homiletic_functions=_canonicalize_slug_list(
            payload.get("preferred_homiletic_functions"), PILOT_HOMILETIC_FUNCTIONS
        ),
    )


def plan_retrieval_intent(
    *,
    passage_reference: str,
    passage_text: str = "",
    theme: str = "",
    occasion: str = "",
    llm_generate: Callable[[str], str],
) -> RetrievalIntent:
    """Stage 0: the only LLM call that ever sees the raw passage text
    before candidate scoring. Returns an empty `RetrievalIntent` (never
    raises) if the call itself raises or returns something unparseable
    -- an empty intent makes every candidate score 0.0 in Stage A (see
    `local_relevance_score`), which naturally yields an empty final
    result rather than falling back to any kind of unfiltered pool."""
    prompt = build_query_planner_prompt(
        passage_reference=passage_reference, passage_text=passage_text,
        theme=theme, occasion=occasion,
    )
    try:
        raw = llm_generate(prompt)
    except Exception:  # noqa: BLE001 -- fail-closed, never propagate a planner error to the user
        return RetrievalIntent()
    return parse_planner_response(raw)


def build_ranking_prompt(
    *,
    passage_reference: str,
    passage_text: str,
    theme: str,
    occasion: str,
    candidates: list[RetrievalCandidate],
) -> str:
    candidate_blocks = "\n".join(
        f"[{c.unit_id}] title_hu: {c.title_hu} | summary_hu: {c.summary_hu} | "
        f"topics: {', '.join(c.topics) or '—'} | tone: {c.tone or '—'} | "
        f"homiletic_functions: {', '.join(c.homiletic_functions) or '—'}"
        for c in candidates
    )
    context_lines = [f"Igehely: {passage_reference or 'nincs megadva'}"]
    if passage_text.strip():
        context_lines.append(f"Bibliai szöveg (részlet): {passage_text.strip()[:800]}")
    if theme.strip():
        context_lines.append(f"Téma/kulcsszavak: {theme.strip()}")
    if occasion.strip():
        context_lines.append(f"Alkalom: {occasion.strip()}")
    context_block = "\n".join(context_lines)

    return f"""\
Te egy magyar református prédikációs illusztráció-ajánló asszisztens \
vagy. Az alábbi, MÁR ELKÉSZÜLT és ellenőrzött illusztráció-jelöltek \
közül kell kiválasztanod és rangsorolnod a VALÓBAN relevánsakat -- TE \
MAGAD NEM ÍRSZ, NEM TALÁLSZ KI TÖRTÉNETET, kizárólag a megadott \
jelöltek közül választhatsz.

FONTOS: ne érezd kényszerítve magad, hogy 3-5 találatot adj vissza. Egy \
jelölt CSAK akkor kerülhet a válaszba, ha ténylegesen, tartalmilag \
kapcsolódik a lenti kontextushoz -- ha egy jelölt csak témájában \
véletlenszerűen hasonlít, vagy csak azért került a listára, mert nem \
volt jobb találat, azt NE add vissza. Ha egyetlen jelölt sem eléggé \
releváns, adj vissza teljesen üres listát -- ez helyes és elvárt \
válasz, nem hiba.

KONTEXTUS:
{context_block}

JELÖLTEK (kizárólag ezek közül választhatsz, az azonosítójuk szögletes \
zárójelben áll):
{candidate_blocks}

MINDEN visszaadott jelöltet sorolj be EGY, pontosan az alábbi négy \
kategória közül a legjobban illőbe (ez a "match_tier" mező):
- "DIRECT_ANALOGY": a jelölt cselekménye/szerkezete KÖZVETLENÜL \
  megfelel a textus fő motívumának vagy konfliktusának -- pl. Lk \
  10,25-37 (irgalmas samaritánus) esetén egy olyan történet, ahol \
  valaki konkrét, kockázatot/áldozatot vállaló segítséget nyújt egy \
  rászorulónak/idegennek, miközben mások elmennek mellette;
- "THEMATIC_SUPPORT": a jelölt ugyanazt a fő üzenetet/tanulságot \
  hordozza, de más cselekményszerkezettel vagy más helyzetben;
- "ADJACENT_THEME": a jelölt csak rokon témát érint, a textus fő \
  üzenetét nem közvetlenül, csak érintőlegesen támasztja alá;
- "WEAK": a kapcsolat felszínes vagy erőltetett -- ilyen jelöltet \
  inkább ne is adj vissza a results listában.
A "DIRECT_ANALOGY" jelölteket MINDIG magasabbra rangsorold (a lista \
elejére), mint egy gyengébb kategóriájú jelöltet, még akkor is, ha a \
puszta relevance score-juk közel esik egymáshoz -- a kategória \
elsőbbséget élvez a score-ral szemben.

MINDEN visszaadott jelölthöz add meg, hogy ténylegesen MEGTARTHATÓ-e \
(ez a "keep" mező, true vagy false). "keep": true KIZÁRÓLAG akkor, ha \
a jelölt és a bibliai textus között konkrét, homiletikailag használható \
kapcsolat mutatható ki -- ehhez LEGALÁBB EGY az alábbiak közül \
ténylegesen fennáll:
- ugyanaz vagy nagyon hasonló konfliktus;
- ugyanaz a magatartási dinamika;
- hasonló döntés és annak következménye;
- hasonló fordulat vagy felismerés;
- olyan konkrét kép, amely valóban megvilágítja a textus központi \
  feszültségét.
NEM elég "keep": true-hoz:
- közös általános erkölcsi szó (pl. mindkettő "irgalomról" szól, de \
  másképp);
- távoli asszociáció;
- ugyanahhoz a nagy témához tartozás önmagában;
- egy teológiai fogalom (pl. megigazulás) moralizáló, leegyszerűsített \
  átfordítása egy erénytörténetre;
- olyan kapcsolat, amit hosszú magyarázat nélkül a hallgató nem értene \
  meg.
KÜLÖNÖSEN SZIGORÚAN alkalmazd ezeket a kritériumokat, ha a textus maga \
NEM elbeszélés, hanem tanító/érvelő szövegrész (pl. egy tanítás \
kifejtése) vagy felsorolás/nemzetségtábla: ilyenkor egy jelölt attól \
még, hogy UGYANARRÓL AZ ELVONT FOGALOMRÓL (pl. kegyelem, irgalom, \
igazságosság) szól, mint a textus egyik mondata, NEM kap "keep": \
true-t -- csak akkor, ha a jelölt konkrét cselekménye/helyzete valóban \
tükrözi a textus fő logikai szerkezetét (pl. ugyanazt a döntés-\
következmény vagy ok-okozat mintázatot), nem csupán ugyanazt az \
elvont szót emlegeti.
Ha a fenti kritériumok egyikét sem teljesíti egy jelölt, "keep": \
false -- EZ NEM HIBA, hanem a helyes válasz. Neked EXPLICIT JOGOD van \
azt mondani, hogy "Ehhez a textushoz a rendelkezésre álló jelöltek \
között nincs elég erős illusztráció" -- ha egyetlen jelölt sem felel \
meg, minden jelölt "keep" értéke legyen false, ez teljesen legitim és \
elvárt kimenet, a NULLA találat is helyes válasz lehet.
A "match_tier" önmagában SOHA nem dönti el a "keep" értékét -- \
különösen a "DIRECT_ANALOGY" címke NEM garantálja automatikusan a \
"keep": true értéket, a fenti konkrét kritériumokat FÜGGETLENÜL, külön \
kell megvizsgálnod minden jelöltnél. Iránymutatásként: "WEAK" jelölt \
esetén szinte mindig "keep": false a helyes válasz; "ADJACENT_THEME" \
jelölt csak KIVÉTELESEN, valóban prédikációsan használható esetben \
kaphat "keep": true-t.

FELADAT:
- válaszd ki LEGFELJEBB {MAX_TOP_N} jelöltet, amelyek ténylegesen, \
  tartalmilag kapcsolódnak a fenti kontextushoz (textus, téma, alkalom) \
  -- homiletikai használhatóság alapján;
- minden visszaadott jelölthez adj 0.0-1.0 közötti relevance score-t \
  -- csak akkor adj 0.5-nél magasabb score-t, ha a kapcsolat valóban \
  konkrét és indokolható, ne csak témarokonság alapján;
- add meg a fent leírt "match_tier" besorolást is minden visszaadott \
  jelölthöz;
- add meg a fent leírt "keep" (true/false) döntést is minden \
  visszaadott jelölthöz -- a végső listában csak "keep": true jelöltek \
  jelennek meg a felhasználónak;
- a "reason" mező szövege közvetlenül megjelenik majd a felhasználónak \
  "Kapcsolódás az igéhez: ..." formában, ezért legyen KONKRÉT és \
  LEGFELJEBB 2 rövid mondat, a textus/jelölt tartalmára hivatkozó \
  magyarázat. SOHA ne írj általános, semmitmondó indoklást mint \
  "kapcsolódik a textushoz" vagy "releváns téma". SOHA ne csak a \
  témacímkéket (topics) sorold fel más szavakkal -- konkrét \
  cselekményre/mozzanatra hivatkozz. SOHA ne állítsd vagy sugalld, hogy \
  a jelölt ugyanaz a történet, mint a bibliai szöveg, vagy hogy abból \
  szó szerint megtörtént esemény lenne -- ez egy ANALÓGIA/illusztráció, \
  nem azonosság a bibliai szöveggel. Helyette pl.: "Az apa feltétel \
  nélküli visszafogadása miatt kapcsolódik a tékozló fiú történetének \
  kegyelem-motívumához.";
- KIZÁRÓLAG a fenti [ID] azonosítók egyikét használhatod -- SOHA ne adj \
  vissza olyan ID-t, ami nem szerepel a listában, és SOHA ne írj le új \
  történetet vagy tartalmat.

KIMENET -- KIZÁRÓLAG ezt a JSON alakot add vissza, más szöveg nélkül:
{{
  "results": [
    {{"unit_id": <a jelöltek közül választott egész szám>, "score": <0.0-1.0>, \
"match_tier": "DIRECT_ANALOGY|THEMATIC_SUPPORT|ADJACENT_THEME|WEAK", \
"keep": true|false, \
"reason": "legfeljebb 2 mondatos, konkrét magyarázat"}}
  ]
}}"""


def parse_ranking_response(raw: str, *, valid_ids: set[int]) -> list[RankedIllustration]:
    """Fail-closed: unparseable JSON, a missing/non-list `results` field,
    or a malformed entry all yield an EMPTY list (never a guess, never a
    replacement story). An entry naming an `unit_id` outside `valid_ids`
    is silently DROPPED -- the rest of a partially-valid response is
    still honored, but that one entry is never trusted."""
    payload = _extract_json_object(raw)
    if payload is None:
        return []
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return []
    ranked: list[RankedIllustration] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        unit_id = item.get("unit_id")
        if not isinstance(unit_id, int) or unit_id not in valid_ids:
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        reason = str(item.get("reason", "")).strip()
        raw_tier = item.get("match_tier")
        match_tier = raw_tier if isinstance(raw_tier, str) and raw_tier in MATCH_TIER_ORDER else "WEAK"
        # Fail-closed admission gate: only an explicit JSON `"keep": true`
        # counts -- missing/non-bool/false all mean "drop". A WEAK tier
        # additionally HARD-forces keep=False regardless of what the
        # model wrote for `keep`, so a mislabeled/defaulted-WEAK entry can
        # never sneak through via a stray `"keep": true`.
        keep = item.get("keep") is True and match_tier != "WEAK"
        ranked.append(
            RankedIllustration(unit_id=unit_id, reason=reason, score=score, match_tier=match_tier, keep=keep)
        )
    return ranked


def _source_attribution(candidate: RetrievalCandidate) -> str:
    parts = [candidate.source_title]
    if candidate.tradition:
        parts.append(candidate.tradition)
    return " · ".join(parts)


def _log_diagnostics(
    *, mode: RetrievalMode, passage_reference: str, diagnostics: RetrievalDiagnostics
) -> None:
    """Audit finding (illustration retrieval observability gap): before
    this, a `reason != REASON_OK` outcome in PRODUCTION was invisible
    outside the dev-only Streamlit diagnostics expander (see
    `illustration_retrieval_ui._render_dev_diagnostics`) -- a real user
    hitting 0 results left no trace anywhere a developer could later
    inspect. This closes that gap with one structured, content-free log
    line per search, for every mode.

    Deliberately logs the SAME fields `RetrievalDiagnostics` already
    exposes to the dev UI -- counts and a reason code -- plus `mode` and
    `passage_reference` (a Bible citation, not user PII). NEVER logs
    `intent.keywords_hu`/`concepts_hu` (free text an LLM derived from the
    passage) or any candidate/story content -- same "structured counts
    only, no raw text" boundary `RetrievalDiagnostics` itself already
    enforces (see its docstring and `test_diagnostics_dataclass_has_no_
    raw_text_field`)."""
    logger.info(
        "illustration_retrieval mode=%s reference=%s reason=%s pool=%d "
        "stage_a_candidates=%d stage_b_parsed=%d stage_b_accepted=%d final=%d",
        mode,
        passage_reference,
        diagnostics.reason,
        diagnostics.stage_a_pool_size,
        diagnostics.stage_a_candidate_count,
        diagnostics.stage_b_parsed_count,
        diagnostics.stage_b_accepted_count,
        diagnostics.final_count,
    )


def _run_retrieval_pipeline(
    connection,
    *,
    mode: RetrievalMode,
    passage_reference: str,
    llm_generate: Callable[[str], str],
    passage_text: str = "",
    theme: str = "",
    occasion: str = "",
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    top_n: int = DEFAULT_TOP_N,
    min_local_relevance: float = MIN_LOCAL_RELEVANCE_SCORE,
    min_rank_score: float = MIN_RANK_SCORE,
) -> tuple[list[IllustrationRetrievalResult], RetrievalDiagnostics]:
    """Thin logging wrapper around `_run_retrieval_pipeline_impl` -- a
    single funnel point so every caller (`retrieve_illustrations` and
    `retrieve_illustrations_with_diagnostics` alike) gets one `_log_
    diagnostics` call per search, regardless of which of the impl's
    several early-return branches fired."""
    results, diagnostics = _run_retrieval_pipeline_impl(
        connection, mode=mode, passage_reference=passage_reference, llm_generate=llm_generate,
        passage_text=passage_text, theme=theme, occasion=occasion, candidate_limit=candidate_limit,
        top_n=top_n, min_local_relevance=min_local_relevance, min_rank_score=min_rank_score,
    )
    _log_diagnostics(mode=mode, passage_reference=passage_reference, diagnostics=diagnostics)
    return results, diagnostics


def _run_retrieval_pipeline_impl(
    connection,
    *,
    mode: RetrievalMode,
    passage_reference: str,
    llm_generate: Callable[[str], str],
    passage_text: str = "",
    theme: str = "",
    occasion: str = "",
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    top_n: int = DEFAULT_TOP_N,
    min_local_relevance: float = MIN_LOCAL_RELEVANCE_SCORE,
    min_rank_score: float = MIN_RANK_SCORE,
) -> tuple[list[IllustrationRetrievalResult], RetrievalDiagnostics]:
    """The full three-stage pipeline, always returning BOTH the final
    results and a `RetrievalDiagnostics` explaining why (Phase 3I.3).
    `retrieve_illustrations`/`retrieve_illustrations_with_diagnostics`
    are thin wrappers over this single implementation -- never
    duplicated logic between the two public entry points."""
    planner_prompt = build_query_planner_prompt(
        passage_reference=passage_reference, passage_text=passage_text,
        theme=theme, occasion=occasion,
    )
    try:
        planner_raw = llm_generate(planner_prompt)
    except Exception:  # noqa: BLE001 -- fail-closed: never propagate an LLM-layer exception to the caller
        return [], RetrievalDiagnostics(
            reason=REASON_PLANNER_ERROR, intent=RetrievalIntent(), stage_a_pool_size=0,
            stage_a_candidate_count=0, stage_a_top_scores=(), stage_b_parsed_count=0,
            stage_b_accepted_count=0, final_count=0,
        )
    intent = parse_planner_response(planner_raw)

    if intent.is_empty():
        return [], RetrievalDiagnostics(
            reason=REASON_NO_INTENT, intent=intent, stage_a_pool_size=0,
            stage_a_candidate_count=0, stage_a_top_scores=(), stage_b_parsed_count=0,
            stage_b_accepted_count=0, final_count=0,
        )

    try:
        scored_pool = _fetch_and_score_candidates(connection, intent=intent, mode=mode)
    except Exception:  # noqa: BLE001 -- fail-closed: a backend/network fetch failure must never propagate as an unhandled exception, and must never be indistinguishable from "genuinely found nothing"
        return [], RetrievalDiagnostics(
            reason=REASON_CANDIDATE_FETCH_ERROR, intent=intent, stage_a_pool_size=0,
            stage_a_candidate_count=0, stage_a_top_scores=(), stage_b_parsed_count=0,
            stage_b_accepted_count=0, final_count=0,
        )
    candidates = [c for c, s in scored_pool if s >= min_local_relevance][:candidate_limit]
    top_scores = tuple((c.unit_id, s) for c, s in scored_pool[:_DIAGNOSTIC_TOP_SCORES_LIMIT])

    if not candidates:
        return [], RetrievalDiagnostics(
            reason=REASON_NO_LOCAL_CANDIDATES, intent=intent, stage_a_pool_size=len(scored_pool),
            stage_a_candidate_count=0, stage_a_top_scores=top_scores, stage_b_parsed_count=0,
            stage_b_accepted_count=0, final_count=0,
        )

    ranking_prompt = build_ranking_prompt(
        passage_reference=passage_reference, passage_text=passage_text,
        theme=theme, occasion=occasion, candidates=candidates,
    )
    try:
        raw_response = llm_generate(ranking_prompt)
    except Exception:  # noqa: BLE001 -- fail-closed: never propagate an LLM-layer exception to the caller
        return [], RetrievalDiagnostics(
            reason=REASON_RANKING_ERROR, intent=intent, stage_a_pool_size=len(scored_pool),
            stage_a_candidate_count=len(candidates), stage_a_top_scores=top_scores,
            stage_b_parsed_count=0, stage_b_accepted_count=0, final_count=0,
        )

    parsed = parse_ranking_response(raw_response, valid_ids={c.unit_id for c in candidates})
    accepted = [r for r in parsed if r.score >= min_rank_score and r.keep]

    if not accepted:
        return [], RetrievalDiagnostics(
            reason=REASON_RANKER_REJECTED_ALL, intent=intent, stage_a_pool_size=len(scored_pool),
            stage_a_candidate_count=len(candidates), stage_a_top_scores=top_scores,
            stage_b_parsed_count=len(parsed), stage_b_accepted_count=0, final_count=0,
        )

    candidates_by_id = {c.unit_id: c for c in candidates}
    results: list[IllustrationRetrievalResult] = []
    # Tier-aware ordering: a DIRECT_ANALOGY candidate always sorts before
    # a THEMATIC_SUPPORT/ADJACENT_THEME/WEAK one, regardless of how close
    # the raw scores are -- score is only the tiebreaker WITHIN a tier.
    for r in sorted(accepted, key=lambda x: (MATCH_TIER_ORDER.get(x.match_tier, 3), -x.score))[:top_n]:
        c = candidates_by_id.get(r.unit_id)
        if c is None:
            continue
        results.append(
            IllustrationRetrievalResult(
                unit_id=c.unit_id, title_hu=c.title_hu, modern_hu_text=c.modern_hu_text,
                summary_hu=c.summary_hu, moral_hu=c.moral_hu, topics=c.topics, tone=c.tone,
                homiletic_functions=c.homiletic_functions, source_title=c.source_title,
                source_attribution=_source_attribution(c), provenance_status=c.provenance_status,
                rank_reason=r.reason, rank_score=r.score,
                match_tier=r.match_tier, relation_hu=r.reason,
            )
        )
    diagnostics = RetrievalDiagnostics(
        reason=REASON_OK, intent=intent, stage_a_pool_size=len(scored_pool),
        stage_a_candidate_count=len(candidates), stage_a_top_scores=top_scores,
        stage_b_parsed_count=len(parsed), stage_b_accepted_count=len(accepted),
        final_count=len(results),
    )
    return results, diagnostics


def retrieve_illustrations(
    connection,
    *,
    mode: RetrievalMode,
    passage_reference: str,
    llm_generate: Callable[[str], str],
    passage_text: str = "",
    theme: str = "",
    occasion: str = "",
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    top_n: int = DEFAULT_TOP_N,
    min_local_relevance: float = MIN_LOCAL_RELEVANCE_SCORE,
    min_rank_score: float = MIN_RANK_SCORE,
) -> list[IllustrationRetrievalResult]:
    """The full three-stage pipeline. Returns an EMPTY list (never an
    exception, never a fabricated result) when: the planner produces
    nothing usable, no candidate clears the local relevance threshold,
    the ranking response fails to parse, or the ranker finds nothing
    above `min_rank_score`. The caller is responsible for showing the
    user-facing "nem találtam megfelelő illusztrációt" message in that
    case -- and Phase 3I.2's explicit goal is that this is the CORRECT,
    expected outcome far more often than Phase 3I's fallback allowed.

    See `retrieve_illustrations_with_diagnostics` for a variant that
    also explains WHY an empty result happened."""
    results, _diagnostics = _run_retrieval_pipeline(
        connection, mode=mode, passage_reference=passage_reference, llm_generate=llm_generate,
        passage_text=passage_text, theme=theme, occasion=occasion, candidate_limit=candidate_limit,
        top_n=top_n, min_local_relevance=min_local_relevance, min_rank_score=min_rank_score,
    )
    return results


def retrieve_illustrations_with_diagnostics(
    connection,
    *,
    mode: RetrievalMode,
    passage_reference: str,
    llm_generate: Callable[[str], str],
    passage_text: str = "",
    theme: str = "",
    occasion: str = "",
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    top_n: int = DEFAULT_TOP_N,
    min_local_relevance: float = MIN_LOCAL_RELEVANCE_SCORE,
    min_rank_score: float = MIN_RANK_SCORE,
) -> tuple[list[IllustrationRetrievalResult], RetrievalDiagnostics]:
    """Same pipeline as `retrieve_illustrations`, but ALSO returns a
    `RetrievalDiagnostics` (Phase 3I.3) describing WHY an empty result
    happened -- `no_intent` (planner produced nothing usable),
    `no_local_candidates` (Stage A found nothing above threshold),
    `ranker_rejected_all` (Stage B ran but nothing cleared
    `min_rank_score`), `planner_error`/`ranking_error` (the LLM call
    itself raised), or `ok`. Never exposes raw LLM prompt/response text
    -- only structured counts/scores/reason codes. Intended for
    development-mode UI surfaces and audits; the production end-user UI
    must never show this as technical detail."""
    return _run_retrieval_pipeline(
        connection, mode=mode, passage_reference=passage_reference, llm_generate=llm_generate,
        passage_text=passage_text, theme=theme, occasion=occasion, candidate_limit=candidate_limit,
        top_n=top_n, min_local_relevance=min_local_relevance, min_rank_score=min_rank_score,
    )


__all__ = [
    "ALLOWED_RETRIEVAL_MODES",
    "DEFAULT_CANDIDATE_LIMIT",
    "DEFAULT_TOP_N",
    "MATCH_TIER_ORDER",
    "MIN_LOCAL_RELEVANCE_SCORE",
    "MIN_RANK_SCORE",
    "REASON_CANDIDATE_FETCH_ERROR",
    "REASON_NO_INTENT",
    "REASON_NO_LOCAL_CANDIDATES",
    "REASON_OK",
    "REASON_PLANNER_ERROR",
    "REASON_RANKER_REJECTED_ALL",
    "REASON_RANKING_ERROR",
    "IllustrationCandidateRepository",
    "IllustrationRetrievalResult",
    "LocalSqliteIllustrationRepository",
    "RankedIllustration",
    "RetrievalCandidate",
    "RetrievalDiagnostics",
    "RetrievalIntent",
    "SupabaseIllustrationRepository",
    "build_query_planner_prompt",
    "build_ranking_prompt",
    "find_candidates",
    "local_relevance_score",
    "parse_planner_response",
    "parse_ranking_response",
    "plan_retrieval_intent",
    "retrieve_illustrations",
    "retrieve_illustrations_with_diagnostics",
]
