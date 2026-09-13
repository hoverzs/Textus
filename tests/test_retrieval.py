from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3

import pytest

from illustration_engine.illustration_sqlite import (
    IllustrationLicenseGateError,
    create_schema,
    insert_illustration_unit,
    insert_source,
    insert_story,
    update_illustration_unit_fields,
    update_unit_machine_qa,
)
from illustration_engine.retrieval import (
    MATCH_TIER_ORDER,
    MIN_LOCAL_RELEVANCE_SCORE,
    MIN_RANK_SCORE,
    REASON_CANDIDATE_FETCH_ERROR,
    REASON_NO_INTENT,
    REASON_NO_LOCAL_CANDIDATES,
    REASON_OK,
    REASON_PLANNER_ERROR,
    REASON_RANKER_REJECTED_ALL,
    REASON_RANKING_ERROR,
    LocalSqliteIllustrationRepository,
    RankedIllustration,
    RetrievalCandidate,
    RetrievalDiagnostics,
    RetrievalIntent,
    SupabaseIllustrationRepository,
    build_query_planner_prompt,
    build_ranking_prompt,
    find_candidates,
    local_relevance_score,
    parse_planner_response,
    parse_ranking_response,
    plan_retrieval_intent,
    retrieve_illustrations,
    retrieve_illustrations_with_diagnostics,
)

_VALID_SUMMARY = " ".join(["szo"] * 45)

# A prompt fragment that only ever appears in the Stage-B ranking prompt
# (the candidate-list header) -- used by `_llm_dispatch` below to tell
# apart the two different LLM calls `retrieve_illustrations` now makes
# (Stage 0 planner, then Stage B ranker) without any call-order tracking.
_RANKER_MARKER = "JELÖLTEK (kizárólag ezek közül"


def _fresh_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def _make_source(conn: sqlite3.Connection, *, code: str = "SRC", license_status: str = "public_domain_confirmed") -> int:
    return insert_source(
        conn, code=code, title="Test Source", orig_language="en",
        license_status=license_status, license_basis_hu="x", reliability_tier="high", tradition="tradition",
    )


def _make_story(conn: sqlite3.Connection, source_id: int, *, external_ref: str = "1", original_text: str = "Az irgalmas atya története a fiaknak.") -> int:
    return insert_story(
        conn, source_id=source_id, external_ref=external_ref, canonical_key=f"key-{external_ref}",
        title_original="Original Title", adaptation_status="verbatim_transcription", original_text=original_text,
        original_text_checksum=hashlib.sha256(original_text.encode("utf-8")).hexdigest(),
    )


def _make_unit(
    conn: sqlite3.Connection, story_id: int, *, unit_index: int = 1, status: str = "needs_review",
    qa_status: str | None = None, title_hu: str = "Cím", modern_hu_text: str = "Az irgalmas atya elfogadta vissza a fiát.",
    summary_hu: str = _VALID_SUMMARY, moral_hu: str | None = None,
) -> int:
    unit_id = insert_illustration_unit(
        conn, story_id=story_id, unit_index=unit_index, derivation_type="full_story_translation",
        status=status, title_hu=title_hu, modern_hu_text=modern_hu_text, summary_hu=summary_hu,
        moral_hu=moral_hu,
        human_reviewed_at="2026-08-28T00:00:00+00:00" if status in ("approved", "published") else None,
    )
    if qa_status:
        update_unit_machine_qa(conn, unit_id=unit_id, qa_status=qa_status, qa_model="m", qa_prompt_version="v1")
    return unit_id


def _make_published_unit(conn: sqlite3.Connection, story_id: int, **kwargs) -> int:
    unit_id = _make_unit(conn, story_id, status="published", qa_status="passed", **kwargs)
    return unit_id


def _llm(response) -> callable:
    if isinstance(response, dict):
        return lambda prompt: json.dumps(response)
    return lambda prompt: response


def _llm_dispatch(planner_response, ranker_response) -> callable:
    """Most `retrieve_illustrations` tests now need two different canned
    responses -- one for Stage 0's planner call, one for Stage B's
    ranker call. Dispatches on `_RANKER_MARKER`, which only the ranking
    prompt contains, rather than tracking call order."""
    planner_text = json.dumps(planner_response) if isinstance(planner_response, dict) else planner_response
    ranker_text = json.dumps(ranker_response) if isinstance(ranker_response, dict) else ranker_response

    def _dispatch(prompt: str) -> str:
        return ranker_text if _RANKER_MARKER in prompt else planner_text

    return _dispatch


def _intent(**kwargs) -> RetrievalIntent:
    return RetrievalIntent(**kwargs)


# ---------------------------------------------------------------------------
# Mode gating (decoupled from relevance scoring via min_relevance=0.0 and a
# keyword-matching intent, so these tests only exercise the mode/rights gate)
# ---------------------------------------------------------------------------

_ANY_INTENT = RetrievalIntent(keywords_hu=("atya",))


def test_production_mode_returns_only_published() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_1 = _make_story(conn, source_id, external_ref="1")
    story_2 = _make_story(conn, source_id, external_ref="2")
    published_id = _make_published_unit(conn, story_1, title_hu="Publikált")
    _make_unit(conn, story_2, status="needs_review", qa_status="passed", title_hu="Nem publikált")
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="production", limit=10, min_relevance=0.0)
    conn.close()

    assert [c.unit_id for c in candidates] == [published_id]
    assert candidates[0].provenance_status == "published"


def test_development_mode_returns_qa_passed_regardless_of_review_status() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="development", limit=10, min_relevance=0.0)
    conn.close()

    assert [c.unit_id for c in candidates] == [unit_id]
    assert candidates[0].provenance_status == "development_qa_passed"


def test_development_mode_excludes_needs_attention() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, qa_status="needs_attention")
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="development", limit=10, min_relevance=0.0)
    conn.close()
    assert candidates == []


def test_development_mode_excludes_failed() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, qa_status="failed")
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="development", limit=10, min_relevance=0.0)
    conn.close()
    assert candidates == []


def test_development_mode_excludes_pending_qa() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, qa_status=None)  # never QA'd
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="development", limit=10, min_relevance=0.0)
    conn.close()
    assert candidates == []


def test_production_mode_excludes_approved_but_not_published() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, status="approved", qa_status="passed")
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="production", limit=10, min_relevance=0.0)
    conn.close()
    assert candidates == []


def test_invalid_mode_rejected() -> None:
    conn = _fresh_connection()
    with pytest.raises(ValueError):
        find_candidates(conn, intent=_ANY_INTENT, mode="staging", limit=10)
    conn.close()


def test_invalid_limit_rejected() -> None:
    conn = _fresh_connection()
    with pytest.raises(ValueError):
        find_candidates(conn, intent=_ANY_INTENT, mode="production", limit=0)
    conn.close()


# ---------------------------------------------------------------------------
# Rights fail-closed
# ---------------------------------------------------------------------------


def test_non_publishable_license_structurally_cannot_reach_production() -> None:
    """A 'published' unit on a non-publishable-license source cannot
    exist at all -- Python-level (IllustrationLicenseGateError) AND
    DB-level (trigger) both block it. Production-mode retrieval's rights
    guarantee is therefore structural (enforced by published_
    illustration_units' own WHERE clause + this two-layer gate), not
    merely a Python-side filter that could be bypassed."""
    conn = _fresh_connection()
    source_id = _make_source(conn, license_status="restricted")
    story_id = _make_story(conn, source_id)
    with pytest.raises(IllustrationLicenseGateError):
        insert_illustration_unit(
            conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation",
            status="published", title_hu="T", modern_hu_text="M", summary_hu=_VALID_SUMMARY,
            human_reviewed_at="2026-08-28T00:00:00+00:00",
        )
    conn.close()


def test_non_publishable_license_excluded_in_development() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn, license_status="restricted")
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="development", limit=10, min_relevance=0.0)
    conn.close()
    assert candidates == []  # qa_status=passed alone is NOT enough -- rights still required


# ---------------------------------------------------------------------------
# Provenance / checksum fail-closed
# ---------------------------------------------------------------------------


def test_checksum_mismatch_excludes_candidate() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()
    # Corrupt the checksum directly -- simulates an integrity breach.
    conn.execute("UPDATE stories SET original_text_checksum = 'corrupted' WHERE id = ?", (story_id,))
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="development", limit=10, min_relevance=0.0)
    conn.close()
    assert candidates == []


def test_missing_checksum_excludes_candidate() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_unit(conn, story_id, status="needs_review", qa_status="passed")
    conn.commit()
    conn.execute("UPDATE stories SET original_text_checksum = NULL WHERE id = ?", (story_id,))
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="development", limit=10, min_relevance=0.0)
    conn.close()
    assert candidates == []


# ---------------------------------------------------------------------------
# Local relevance scoring / candidate limit (Phase 3I.2)
# ---------------------------------------------------------------------------


def test_local_relevance_score_rewards_title_and_summary_keyword_overlap() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="A tékozló fiú hazatérése", modern_hu_text="Egy hosszú történet.",
        summary_hu="Egy apa irgalommal fogadja vissza elveszett fiát.", moral_hu=None,
        topics=(), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    unrelated = RetrievalCandidate(
        unit_id=2, title_hu="Egy angol úriember és a kalapja", modern_hu_text="Semmi köze a textushoz.",
        summary_hu="Viktoriánus kori anekdota egy kalapról.", moral_hu=None,
        topics=(), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    intent = RetrievalIntent(keywords_hu=("hazatérés", "irgalom"), concepts_hu=("elveszettség", "apa és fiú"))

    assert local_relevance_score(candidate, intent) > local_relevance_score(unrelated, intent)
    assert local_relevance_score(unrelated, intent) == 0.0


def test_local_relevance_score_rewards_topic_match() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="Cím", modern_hu_text="Szöveg.", summary_hu=_VALID_SUMMARY, moral_hu=None,
        topics=("irgalom",), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    without_topic = dataclasses.replace(candidate, unit_id=2, topics=())
    intent = RetrievalIntent(topics=("irgalom",))

    assert local_relevance_score(candidate, intent) > local_relevance_score(without_topic, intent)


def test_local_relevance_score_rewards_homiletic_function_match() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="Cím", modern_hu_text="Szöveg.", summary_hu=_VALID_SUMMARY, moral_hu=None,
        topics=(), tone=None, homiletic_functions=("bevezeto_illusztracio",), source_title="Src",
        source_code="SRC", tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    without_function = dataclasses.replace(candidate, unit_id=2, homiletic_functions=())
    intent = RetrievalIntent(preferred_homiletic_functions=("bevezeto_illusztracio",))

    assert local_relevance_score(candidate, intent) > local_relevance_score(without_function, intent)


def test_empty_intent_scores_every_candidate_zero() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="Bármi", modern_hu_text="Bármi", summary_hu=_VALID_SUMMARY, moral_hu=None,
        topics=("irgalom",), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    assert local_relevance_score(candidate, RetrievalIntent()) == 0.0


def test_no_candidate_meets_threshold_returns_empty_not_unfiltered_pool() -> None:
    """Phase 3I.2 root-cause fix: a passage whose intent shares nothing
    with the corpus must yield an EMPTY candidate list -- never a
    recent-first/unfiltered backfill (that was the old, removed
    behavior; see the module docstring's PHASE_3I2_ROOT_CAUSE note)."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(
        conn, story_id, title_hu="Egy teljesen más témájú anekdota",
        modern_hu_text="Egy viktoriánus kori úriember és egy kalap.",
        summary_hu=_VALID_SUMMARY,
    )
    conn.commit()

    intent = RetrievalIntent(keywords_hu=("teljesen_ismeretlen_szokombinacio_xyz",))
    candidates = find_candidates(conn, intent=intent, mode="production", limit=10)
    conn.close()
    assert candidates == []


def test_min_relevance_threshold_excludes_weak_candidate() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(
        conn, story_id, title_hu="Egy irgalmas apa története", summary_hu=_VALID_SUMMARY,
    )
    conn.commit()

    intent = RetrievalIntent(keywords_hu=("irgalmas",))
    below_threshold = find_candidates(conn, intent=intent, mode="production", limit=10, min_relevance=999.0)
    above_threshold = find_candidates(conn, intent=intent, mode="production", limit=10, min_relevance=0.0)
    conn.close()
    assert below_threshold == []
    assert unit_id in [c.unit_id for c in above_threshold]


def test_candidate_limit_respected_after_scoring() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    for i in range(5):
        story_id = _make_story(conn, source_id, external_ref=str(i))
        _make_published_unit(conn, story_id, unit_index=1, title_hu=f"Irgalmas történet {i}")
    conn.commit()

    intent = RetrievalIntent(keywords_hu=("irgalmas",))
    candidates = find_candidates(conn, intent=intent, mode="production", limit=3, min_relevance=0.0)
    conn.close()
    assert len(candidates) == 3


def test_candidates_sorted_by_score_descending() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_1 = _make_story(conn, source_id, external_ref="1")
    story_2 = _make_story(conn, source_id, external_ref="2")
    weak_id = _make_published_unit(conn, story_1, title_hu="Irgalom egyszer említve", summary_hu=_VALID_SUMMARY)
    strong_id = _make_published_unit(
        conn, story_2, title_hu="Irgalom és megbocsátás", summary_hu="Az irgalom és a megbocsátás áll a történet középpontjában."
    )
    conn.commit()

    intent = RetrievalIntent(keywords_hu=("irgalom", "megbocsátás"))
    candidates = find_candidates(conn, intent=intent, mode="production", limit=10, min_relevance=0.0)
    conn.close()
    assert [c.unit_id for c in candidates][:2] == [strong_id, weak_id] or strong_id == candidates[0].unit_id


def test_candidate_includes_taxonomy_and_attribution_fields() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id)
    conn.commit()
    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="production", limit=10, min_relevance=0.0)
    conn.close()
    c = next(c for c in candidates if c.unit_id == unit_id)
    assert c.source_title == "Test Source"
    assert c.license_status == "public_domain_confirmed"


# ---------------------------------------------------------------------------
# Stage 0: query planner
# ---------------------------------------------------------------------------


def test_planner_cannot_produce_candidate_id_or_story_content() -> None:
    """Structural guarantee: `RetrievalIntent` has no field that could
    carry a unit id or story text -- there is no way for the planner
    stage to smuggle either past this point, regardless of prompt
    wording."""
    field_names = {f.name for f in dataclasses.fields(RetrievalIntent)}
    assert field_names == {"keywords_hu", "concepts_hu", "topics", "preferred_homiletic_functions"}


def test_planner_parses_valid_response() -> None:
    raw = json.dumps({
        "keywords_hu": ["hazatérés", "irgalom"],
        "concepts_hu": ["elveszettség", "apa és fiú"],
        "topics": ["irgalom"],
        "preferred_homiletic_functions": ["bevezeto_illusztracio"],
    })
    intent = parse_planner_response(raw)
    assert intent.keywords_hu == ("hazatérés", "irgalom")
    assert intent.concepts_hu == ("elveszettség", "apa és fiú")
    assert intent.topics == ("irgalom",)
    assert intent.preferred_homiletic_functions == ("bevezeto_illusztracio",)


def test_planner_malformed_json_yields_empty_intent() -> None:
    intent = parse_planner_response("this is not json")
    assert intent == RetrievalIntent()
    assert intent.is_empty()


def test_planner_missing_fields_yield_empty_intent() -> None:
    intent = parse_planner_response(json.dumps({"unrelated": "stuff"}))
    assert intent.is_empty()


def test_planner_topic_diacritic_variant_canonicalized() -> None:
    """Same rigor as Phase 3H.1's taxonomy canonicalization: an accented
    spelling of an existing slug resolves to the canonical one."""
    intent = parse_planner_response(json.dumps({"topics": ["eszesség"]}))  # canonical: "eszesseg"
    assert intent.topics == ("eszesseg",)


def test_planner_topic_outside_controlled_vocabulary_dropped() -> None:
    intent = parse_planner_response(json.dumps({"topics": ["hazateres_nem_letezo_topic"]}))
    assert intent.topics == ()


def test_planner_homiletic_function_outside_vocabulary_dropped() -> None:
    intent = parse_planner_response(json.dumps({"preferred_homiletic_functions": ["nem_letezo_funkcio"]}))
    assert intent.preferred_homiletic_functions == ()


def test_planner_keyword_list_bounded_in_count_and_length() -> None:
    raw = json.dumps({"keywords_hu": [f"szo{i}" for i in range(50)] + ["x" * 500]})
    intent = parse_planner_response(raw)
    assert len(intent.keywords_hu) <= 12
    assert all(len(k) <= 80 for k in intent.keywords_hu)


def test_planner_prompt_forbids_candidate_selection_and_story_writing() -> None:
    prompt = build_query_planner_prompt(passage_reference="Lk 15,11-24", passage_text="", theme="", occasion="")
    assert "NEM választasz illusztrációt" in prompt or "NEM írsz történetet" in prompt


def test_plan_retrieval_intent_uses_llm_generate_callback() -> None:
    seen_prompts = []

    def llm(prompt: str) -> str:
        seen_prompts.append(prompt)
        return json.dumps({"keywords_hu": ["irgalom"]})

    intent = plan_retrieval_intent(passage_reference="Lk 15,11-24", llm_generate=llm)
    assert intent.keywords_hu == ("irgalom",)
    assert len(seen_prompts) == 1


def test_plan_retrieval_intent_llm_exception_yields_empty_intent() -> None:
    def broken_llm(prompt: str) -> str:
        raise RuntimeError("network down")

    intent = plan_retrieval_intent(passage_reference="Lk 15,11-24", llm_generate=broken_llm)
    assert intent == RetrievalIntent()


# ---------------------------------------------------------------------------
# Stage B: ranker fail-closed parsing
# ---------------------------------------------------------------------------


def test_ranker_only_returns_known_ids() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x"}, {"unit_id": 999, "score": 0.8, "reason": "y"}]}),
        valid_ids={1, 2, 3},
    )
    assert [r.unit_id for r in ranked] == [1]  # 999 silently dropped, not replaced


def test_ranker_malformed_json_fails_closed() -> None:
    ranked = parse_ranking_response("this is not json", valid_ids={1, 2, 3})
    assert ranked == []


def test_ranker_missing_results_field_fails_closed() -> None:
    ranked = parse_ranking_response(json.dumps({"other": "stuff"}), valid_ids={1, 2, 3})
    assert ranked == []


def test_ranker_results_not_a_list_fails_closed() -> None:
    ranked = parse_ranking_response(json.dumps({"results": "not a list"}), valid_ids={1, 2, 3})
    assert ranked == []


def test_ranker_empty_results_is_valid_empty_answer() -> None:
    ranked = parse_ranking_response(json.dumps({"results": []}), valid_ids={1, 2, 3})
    assert ranked == []


def test_ranker_score_clamped_to_0_1() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 5.0, "reason": "x"}]}), valid_ids={1},
    )
    assert ranked[0].score == 1.0


def test_ranker_non_int_unit_id_dropped() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": "1", "score": 0.9, "reason": "x"}]}), valid_ids={1},
    )
    assert ranked == []  # string "1" is not accepted as int 1 -- fail closed, no type coercion guessing


def test_ranker_parses_valid_match_tier() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY"}]}),
        valid_ids={1},
    )
    assert ranked[0].match_tier == "DIRECT_ANALOGY"


def test_ranker_missing_match_tier_fails_closed_to_weak() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x"}]}), valid_ids={1},
    )
    assert ranked[0].match_tier == "WEAK"


def test_ranker_invalid_match_tier_fails_closed_to_weak() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x", "match_tier": "SUPER_STRONG_MATCH"}]}),
        valid_ids={1},
    )
    assert ranked[0].match_tier == "WEAK"


def test_ranker_non_string_match_tier_fails_closed_to_weak() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x", "match_tier": 3}]}), valid_ids={1},
    )
    assert ranked[0].match_tier == "WEAK"


# ---------------------------------------------------------------------------
# Stage B: the "keep" admission gate (round 2, 2026-09-13) -- a tier
# alone (however strong) must never be trusted to imply admission; only
# an explicit JSON `"keep": true` does, and WEAK hard-overrides it.
# ---------------------------------------------------------------------------


def test_ranker_parses_explicit_keep_true_on_non_weak_tier() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY", "keep": True}]}),
        valid_ids={1},
    )
    assert ranked[0].keep is True


def test_ranker_keep_missing_fails_closed_to_false() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY"}]}),
        valid_ids={1},
    )
    assert ranked[0].keep is False


def test_ranker_keep_non_bool_fails_closed_to_false() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY", "keep": "true"}]}),
        valid_ids={1},
    )
    assert ranked[0].keep is False


def test_ranker_keep_false_is_respected() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY", "keep": False}]}),
        valid_ids={1},
    )
    assert ranked[0].keep is False


def test_ranker_weak_tier_hard_overrides_keep_true() -> None:
    """The core defense-in-depth rule: even if the model explicitly
    writes `"keep": true` for a candidate it also labeled WEAK, the
    parser must still force keep=False -- a WEAK label must never be
    surfaced, regardless of what else the model claims."""
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.9, "reason": "x", "match_tier": "WEAK", "keep": True}]}),
        valid_ids={1},
    )
    assert ranked[0].keep is False


def test_ranker_adjacent_theme_can_have_keep_true() -> None:
    ranked = parse_ranking_response(
        json.dumps({"results": [{"unit_id": 1, "score": 0.7, "reason": "x", "match_tier": "ADJACENT_THEME", "keep": True}]}),
        valid_ids={1},
    )
    assert ranked[0].keep is True


def test_ranking_prompt_forbids_new_story_generation() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="T", modern_hu_text="M", summary_hu="S", moral_hu=None,
        topics=(), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    prompt = build_ranking_prompt(passage_reference="Lk 15,11-24", passage_text="", theme="", occasion="", candidates=[candidate])
    assert "NEM ÍRSZ" in prompt or "NEM TALÁLSZ KI" in prompt
    assert "[1]" in prompt


def test_ranking_prompt_allows_rejecting_all_candidates() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="T", modern_hu_text="M", summary_hu="S", moral_hu=None,
        topics=(), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    prompt = build_ranking_prompt(passage_reference="Lk 15,11-24", passage_text="", theme="", occasion="", candidates=[candidate])
    assert "üres list" in prompt.lower()


def test_ranking_prompt_requires_concrete_reason_not_generic() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="T", modern_hu_text="M", summary_hu="S", moral_hu=None,
        topics=(), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    prompt = build_ranking_prompt(passage_reference="Lk 15,11-24", passage_text="", theme="", occasion="", candidates=[candidate])
    assert "kapcsolódik a textushoz" in prompt  # cited as the forbidden example
    assert "KONKRÉT" in prompt


def test_ranking_prompt_explains_match_tiers_with_priority() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="T", modern_hu_text="M", summary_hu="S", moral_hu=None,
        topics=(), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    prompt = build_ranking_prompt(passage_reference="Lk 15,11-24", passage_text="", theme="", occasion="", candidates=[candidate])
    for tier in MATCH_TIER_ORDER:
        assert tier in prompt
    assert "match_tier" in prompt


def test_ranking_prompt_forbids_topic_label_restating_and_false_identity() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="T", modern_hu_text="M", summary_hu="S", moral_hu=None,
        topics=(), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    prompt = build_ranking_prompt(passage_reference="Lk 15,11-24", passage_text="", theme="", occasion="", candidates=[candidate])
    assert "témacímkéket" in prompt
    assert "ANALÓGIA" in prompt
    assert "Kapcsolódás az igéhez" in prompt


def test_ranking_prompt_explains_keep_gate_with_criteria_and_zero_result_permission() -> None:
    candidate = RetrievalCandidate(
        unit_id=1, title_hu="T", modern_hu_text="M", summary_hu="S", moral_hu=None,
        topics=(), tone=None, homiletic_functions=(), source_title="Src", source_code="SRC",
        tradition=None, license_status="public_domain_confirmed", provenance_status="published",
    )
    prompt = build_ranking_prompt(passage_reference="Lk 15,11-24", passage_text="", theme="", occasion="", candidates=[candidate])
    assert '"keep"' in prompt
    # positive criteria (at least one must hold for keep=true)
    assert "magatartási dinamika" in prompt
    assert "fordulat vagy felismerés" in prompt
    # explicit anti-patterns (not enough for keep=true)
    assert "közös általános erkölcsi szó" in prompt
    assert "moralizáló" in prompt
    # explicit permission for a legitimate empty answer
    assert "nincs elég erős illusztráció" in prompt
    assert "NULLA találat" in prompt
    # tier must never substitute for the independent keep judgment
    assert "NEM garantálja automatikusan" in prompt


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline_returns_result_with_verbatim_db_text() -> None:
    """The critical no-hallucination guarantee: modern_hu_text in the
    result is EXACTLY the candidate's DB row, never anything from the
    LLM's own response text."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(
        conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története a hazatérésről.",
        modern_hu_text="Az eredeti, adatbázisban tárolt szöveg.",
    )
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas", "hazatérés"]},
        {"results": [{"unit_id": unit_id, "score": 0.95, "reason": "Nagyon releváns.", "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )
    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )
    conn.close()

    assert len(results) == 1
    assert results[0].modern_hu_text == "Az eredeti, adatbázisban tárolt szöveg."
    assert results[0].unit_id == unit_id
    assert results[0].rank_reason == "Nagyon releváns."


def test_relation_hu_survives_into_final_result_reusing_reason() -> None:
    """`relation_hu` must carry the SAME text as `rank_reason` all the
    way through the pipeline -- the ranker prompt was tightened rather
    than a second field/second LLM call being added (Phase 14)."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(
        conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története a hazatérésről.",
    )
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas", "hazatérés"]},
        {"results": [{"unit_id": unit_id, "score": 0.95, "reason": "Konkrét kapcsolódás.", "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )
    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()

    assert len(results) == 1
    assert results[0].relation_hu == "Konkrét kapcsolódás."
    assert results[0].relation_hu == results[0].rank_reason
    assert results[0].match_tier == "DIRECT_ANALOGY"


def test_missing_match_tier_and_keep_fails_closed_to_empty_not_a_crash() -> None:
    """A response with neither `match_tier` nor `keep` at all: match_tier
    defaults to WEAK (round 1's fail-closed default), and WEAK then
    HARD-forces keep=False (round 2) -- so the candidate is dropped
    entirely, the pipeline returns an empty (not a crashing) result."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": 0.9, "reason": "x"}]},  # no match_tier, no keep key at all
    )
    results, diag = retrieve_illustrations_with_diagnostics(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )
    conn.close()

    assert results == []
    assert diag.reason == REASON_RANKER_REJECTED_ALL


def test_missing_match_tier_forces_weak_which_hard_overrides_explicit_keep_true() -> None:
    """Defense in depth: a missing `match_tier` defaults to WEAK, and
    that defaulted WEAK must still hard-force keep=False even when the
    model's JSON separately claims `"keep": true` -- a malformed/omitted
    tier can never accidentally grant admission via a stray keep."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": 0.9, "reason": "x", "keep": True}]},  # no match_tier key
    )
    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()

    assert results == []


def test_weak_tier_never_survives_even_with_higher_score_than_a_kept_direct_analogy() -> None:
    """The core round-2 goal: a WEAK-tier candidate must NEVER reach the
    final results -- not even when it has a higher raw score than a
    genuinely kept DIRECT_ANALOGY candidate. Only the kept candidate
    survives."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id_weak = _make_story(conn, source_id, external_ref="weak")
    story_id_strong = _make_story(conn, source_id, external_ref="strong")
    weak_id = _make_published_unit(conn, story_id_weak, title_hu="Gyenge találat", summary_hu=_VALID_SUMMARY)
    strong_id = _make_published_unit(conn, story_id_strong, title_hu="Erős analógia", summary_hu=_VALID_SUMMARY)
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [
            {"unit_id": weak_id, "score": 0.95, "reason": "Gyenge.", "match_tier": "WEAK", "keep": True},
            {"unit_id": strong_id, "score": 0.65, "reason": "Erős.", "match_tier": "DIRECT_ANALOGY", "keep": True},
        ]},
    )
    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm, min_local_relevance=0.0,
    )
    conn.close()

    assert [r.unit_id for r in results] == [strong_id]


def test_tier_ties_broken_by_score() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id_a = _make_story(conn, source_id, external_ref="a")
    story_id_b = _make_story(conn, source_id, external_ref="b")
    lower_id = _make_published_unit(conn, story_id_a, title_hu="Alacsonyabb", summary_hu=_VALID_SUMMARY)
    higher_id = _make_published_unit(conn, story_id_b, title_hu="Magasabb", summary_hu=_VALID_SUMMARY)
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [
            {"unit_id": lower_id, "score": 0.7, "reason": "x", "match_tier": "THEMATIC_SUPPORT", "keep": True},
            {"unit_id": higher_id, "score": 0.9, "reason": "y", "match_tier": "THEMATIC_SUPPORT", "keep": True},
        ]},
    )
    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm, min_local_relevance=0.0,
    )
    conn.close()

    assert [r.unit_id for r in results] == [higher_id, lower_id]


def test_keep_false_candidate_dropped_even_with_direct_analogy_tier_and_high_score() -> None:
    """DIRECT_ANALOGY + a high score must NOT be enough on their own --
    the model can still explicitly withhold admission via keep=False,
    and that must be honored."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": 0.95, "reason": "x", "match_tier": "DIRECT_ANALOGY", "keep": False}]},
    )
    results, diag = retrieve_illustrations_with_diagnostics(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )
    conn.close()

    assert results == []
    assert diag.reason == REASON_RANKER_REJECTED_ALL


def test_adjacent_theme_keep_true_survives_exceptionally() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas rokon téma", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": 0.7, "reason": "x", "match_tier": "ADJACENT_THEME", "keep": True}]},
    )
    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()

    assert len(results) == 1
    assert results[0].unit_id == unit_id


def test_all_candidates_rejected_is_a_legitimate_empty_result_end_to_end() -> None:
    """The explicit "0 results is legitimate" outcome the round-2 spec
    requires: several plausible-looking candidates, all keep=False (a
    stand-in for the Róm 3,21-26 / Mt 1,1-17 negative-control case) --
    the pipeline must return an empty list with REASON_RANKER_REJECTED_ALL,
    never a forced/best-effort result."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    unit_ids = []
    for i in range(3):
        story_id = _make_story(conn, source_id, external_ref=f"nc{i}")
        unit_ids.append(_make_published_unit(conn, story_id, title_hu=f"Jelölt {i}", summary_hu=_VALID_SUMMARY))
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["igazsagossag"]},
        {"results": [
            {"unit_id": uid, "score": 0.8, "reason": "Csak távoli asszociáció.", "match_tier": "ADJACENT_THEME", "keep": False}
            for uid in unit_ids
        ]},
    )
    results, diag = retrieve_illustrations_with_diagnostics(
        conn, mode="production", passage_reference="Róm 3,21-26", llm_generate=llm, min_local_relevance=0.0,
    )
    conn.close()

    assert results == []
    assert diag.reason == REASON_RANKER_REJECTED_ALL
    assert diag.stage_b_parsed_count == 3
    assert diag.stage_b_accepted_count == 0


def test_no_candidates_above_threshold_never_calls_ranker() -> None:
    """Stage 0 (planner) always runs -- it has to, to know what to score
    candidates against. But if Stage A finds nothing above threshold,
    Stage B's ranker prompt must never be built/sent."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(conn, story_id, title_hu="Teljesen más témájú anekdota", summary_hu=_VALID_SUMMARY)
    conn.commit()

    ranker_prompts_seen = []

    def llm(prompt: str) -> str:
        if _RANKER_MARKER in prompt:
            ranker_prompts_seen.append(prompt)
            return json.dumps({"results": []})
        return json.dumps({"keywords_hu": ["teljesen_ismeretlen_szokombinacio_xyz"]})

    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()
    assert results == []
    assert ranker_prompts_seen == []  # Stage B never reached


def test_planner_failure_yields_empty_result_not_fallback_pool() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(conn, story_id)
    conn.commit()

    def broken_llm(prompt: str) -> str:
        return "not json at all"

    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=broken_llm)
    conn.close()
    assert results == []


def test_malformed_ranker_response_yields_empty_result_not_exception() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa és a hazatérés.")
    conn.commit()

    llm = _llm_dispatch({"keywords_hu": ["irgalmas", "hazatérés"]}, "garbage, not json")
    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )
    conn.close()
    assert results == []


def test_low_rank_score_filtered_out_of_final_results() -> None:
    """Point 5 of the Phase 3I.2 spec: the ranker may score a candidate
    low without dropping it from `results` entirely -- `retrieve_
    illustrations` itself must still filter anything below
    `MIN_RANK_SCORE` out of what the user sees."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": 0.1, "reason": "Gyenge kapcsolat.", "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )
    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()
    assert results == []


def test_rank_score_at_or_above_minimum_is_kept() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": MIN_RANK_SCORE, "reason": "Elég erős kapcsolat.", "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )
    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()
    assert len(results) == 1


def test_ranker_may_reject_all_end_to_end() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch({"keywords_hu": ["irgalmas"]}, {"results": []})
    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()
    assert results == []


def test_top_n_limits_result_count() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    unit_ids = []
    for i in range(6):
        story_id = _make_story(conn, source_id, external_ref=str(i))
        unit_ids.append(_make_published_unit(conn, story_id, title_hu=f"Irgalmas történet {i}", summary_hu=_VALID_SUMMARY))
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": uid, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY", "keep": True} for uid in unit_ids]},
    )
    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm, top_n=3,
        min_local_relevance=0.0,
    )
    conn.close()
    assert len(results) == 3


def test_development_mode_result_marks_provenance_status() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id, status="needs_review", qa_status="passed", title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch({"keywords_hu": ["irgalmas"]}, {"results": [{"unit_id": unit_id, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY", "keep": True}]})
    results = retrieve_illustrations(conn, mode="development", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()

    assert results[0].provenance_status == "development_qa_passed"


def test_retrieval_never_writes_to_db() -> None:
    """Retrieval is READ-ONLY -- human_reviewed_at, status, qa_status must
    all be unchanged after a full retrieval call."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_unit(conn, story_id, status="needs_review", qa_status="passed", title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()
    before = conn.execute("SELECT status, human_reviewed_at, qa_status FROM illustration_units WHERE id=?", (unit_id,)).fetchone()

    llm = _llm_dispatch({"keywords_hu": ["irgalmas"]}, {"results": [{"unit_id": unit_id, "score": 0.9, "reason": "x"}]})
    retrieve_illustrations(conn, mode="development", passage_reference="Lk 15,11-24", llm_generate=llm)

    after = conn.execute("SELECT status, human_reviewed_at, qa_status FROM illustration_units WHERE id=?", (unit_id,)).fetchone()
    conn.close()
    assert before == after


# ---------------------------------------------------------------------------
# Regression: manual-QA weak-match cases (Phase 3I.2 point 8) -- a
# thematically unrelated period-piece anecdote must not outrank/replace
# a genuinely on-topic candidate just because the corpus has few good
# matches. Synthetic fixtures standing in for the real corpus's "Beau
# Brummell" / "Trumpington" / "C---- tanácsos" class of weak matches.
# ---------------------------------------------------------------------------


def test_thematically_unrelated_anecdote_does_not_pass_threshold_for_unrelated_passage() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id, original_text="An English anecdote about hats and manners.")
    _make_published_unit(
        conn, story_id, title_hu="C---- tanácsos és Trumpington",
        summary_hu="Egy angol úriember különc viselkedéséről szóló anekdota egy kalapbolt előtt.",
        modern_hu_text="Egy hosszú, viktoriánus kori anekdota illemről és társasági szokásokról.",
    )
    conn.commit()

    intent = RetrievalIntent(
        keywords_hu=("hazatérés", "irgalom", "megbocsátás"),
        concepts_hu=("elveszettség", "apa és fiú"),
        topics=("irgalom",),
    )
    candidates = find_candidates(conn, intent=intent, mode="production", limit=10)
    conn.close()
    assert candidates == []


# ---------------------------------------------------------------------------
# Phase 3I.3: fail-closed observability (`RetrievalDiagnostics`). Root cause
# of the live-vs-diagnostic-script discrepancy this phase found was a
# GLOBAL COOLDOWN inside app.py's `generate_text` -- outside this module's
# reach and not something illustration_engine can unit-test directly (it
# lives in the Streamlit-coupled caller, see tests/test_illustration_
# retrieval_ui_cooldown.py for that regression). What IS this module's
# responsibility, and what these tests cover, is that a caller can always
# tell OK apart from every distinct failure mode without any raw LLM
# content leaking into the diagnosis.
# ---------------------------------------------------------------------------


def test_diagnostics_reason_ok_when_results_found() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )
    results, diag = retrieve_illustrations_with_diagnostics(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )
    conn.close()

    assert len(results) == 1
    assert diag.reason == REASON_OK
    assert diag.final_count == 1
    assert diag.stage_a_candidate_count == 1
    assert diag.stage_b_accepted_count == 1


def test_diagnostics_reason_planner_error_on_llm_exception() -> None:
    conn = _fresh_connection()

    def broken_llm(prompt: str) -> str:
        raise RuntimeError("network down")

    results, diag = retrieve_illustrations_with_diagnostics(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=broken_llm,
    )
    conn.close()

    assert results == []
    assert diag.reason == REASON_PLANNER_ERROR
    assert diag.intent == RetrievalIntent()


def test_diagnostics_reason_no_intent_on_malformed_planner_response() -> None:
    conn = _fresh_connection()
    llm = _llm_dispatch("not json at all", {"results": []})
    results, diag = retrieve_illustrations_with_diagnostics(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )
    conn.close()

    assert results == []
    assert diag.reason == REASON_NO_INTENT


def test_diagnostics_reason_no_local_candidates_when_nothing_clears_threshold() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(conn, story_id, title_hu="Teljesen más témájú anekdota", summary_hu=_VALID_SUMMARY)
    conn.commit()

    llm = _llm_dispatch({"keywords_hu": ["teljesen_ismeretlen_szokombinacio_xyz"]}, {"results": []})
    results, diag = retrieve_illustrations_with_diagnostics(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )
    conn.close()

    assert results == []
    assert diag.reason == REASON_NO_LOCAL_CANDIDATES
    assert diag.stage_a_pool_size == 1
    assert diag.stage_a_candidate_count == 0
    assert len(diag.stage_a_top_scores) == 1  # visible even though nothing cleared threshold


def test_diagnostics_reason_ranking_error_on_llm_exception() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    def flaky_llm(prompt: str) -> str:
        if _RANKER_MARKER in prompt:
            raise RuntimeError("network down mid-ranking")
        return json.dumps({"keywords_hu": ["irgalmas"]})

    results, diag = retrieve_illustrations_with_diagnostics(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=flaky_llm,
    )
    conn.close()

    assert results == []
    assert diag.reason == REASON_RANKING_ERROR
    assert diag.stage_a_candidate_count == 1


def test_diagnostics_reason_ranker_rejected_all_when_nothing_clears_rank_threshold() -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": 0.1, "reason": "Gyenge kapcsolat.", "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )
    results, diag = retrieve_illustrations_with_diagnostics(
        conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )
    conn.close()

    assert results == []
    assert diag.reason == REASON_RANKER_REJECTED_ALL
    assert diag.stage_b_parsed_count == 1
    assert diag.stage_b_accepted_count == 0


def test_diagnostics_dataclass_has_no_raw_text_field() -> None:
    """Structural check: `RetrievalDiagnostics`'s fields are all counts/
    scores/reason codes/the parsed `RetrievalIntent` -- there is no
    field that could hold a raw prompt or response string."""
    field_names = {f.name for f in dataclasses.fields(RetrievalDiagnostics)}
    assert field_names == {
        "reason", "intent", "stage_a_pool_size", "stage_a_candidate_count",
        "stage_a_top_scores", "stage_b_parsed_count", "stage_b_accepted_count", "final_count",
    }


def test_retrieve_illustrations_plain_still_returns_only_results_list() -> None:
    """Backward compatibility: the plain entry point's return type/
    behavior is unchanged by adding the diagnostics variant."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )
    results = retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()
    assert isinstance(results, list)
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Audit finding: production searches had NO trace anywhere once a search
# returned 0 results -- `RetrievalDiagnostics` existed but was only ever
# rendered in the dev-only Streamlit expander (see
# `illustration_retrieval_ui._render_dev_diagnostics`), never logged. These
# tests cover the fix: one structured `illustration_retrieval` log line per
# search, for every mode and every `REASON_*` outcome, content-free.
# ---------------------------------------------------------------------------


def test_retrieval_logs_structured_diagnostics_on_success(caplog) -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története.")
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas"]},
        {"results": [{"unit_id": unit_id, "score": 0.9, "reason": "x", "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )
    with caplog.at_level("INFO", logger="illustration_engine.retrieval"):
        retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()

    records = [r for r in caplog.records if "illustration_retrieval" in r.message]
    assert len(records) == 1
    assert "mode=production" in records[0].message
    assert "reference=Lk 15,11-24" in records[0].message
    assert f"reason={REASON_OK}" in records[0].message
    assert "final=1" in records[0].message


def test_retrieval_logs_exactly_once_via_plain_and_diagnostics_entry_points(caplog) -> None:
    """Both public entry points share the same underlying pipeline call --
    neither must log twice, and both must log."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(conn, story_id, title_hu="Teljesen más témájú anekdota", summary_hu=_VALID_SUMMARY)
    conn.commit()

    llm = _llm_dispatch({"keywords_hu": ["teljesen_ismeretlen_szokombinacio_xyz"]}, {"results": []})
    with caplog.at_level("INFO", logger="illustration_engine.retrieval"):
        retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    plain_records = [r for r in caplog.records if "illustration_retrieval" in r.message]
    assert len(plain_records) == 1

    caplog.clear()
    with caplog.at_level("INFO", logger="illustration_engine.retrieval"):
        retrieve_illustrations_with_diagnostics(
            conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
        )
    conn.close()
    diag_records = [r for r in caplog.records if "illustration_retrieval" in r.message]
    assert len(diag_records) == 1


def test_retrieval_log_line_reflects_no_local_candidates_reason(caplog) -> None:
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(conn, story_id, title_hu="Teljesen más témájú anekdota", summary_hu=_VALID_SUMMARY)
    conn.commit()

    llm = _llm_dispatch({"keywords_hu": ["teljesen_ismeretlen_szokombinacio_xyz"]}, {"results": []})
    with caplog.at_level("INFO", logger="illustration_engine.retrieval"):
        retrieve_illustrations(conn, mode="production", passage_reference="Zsolt 23", llm_generate=llm)
    conn.close()

    records = [r for r in caplog.records if "illustration_retrieval" in r.message]
    assert len(records) == 1
    assert f"reason={REASON_NO_LOCAL_CANDIDATES}" in records[0].message
    assert "pool=1" in records[0].message
    assert "final=0" in records[0].message


def test_retrieval_log_line_reflects_planner_error_reason(caplog) -> None:
    conn = _fresh_connection()

    def broken_llm(prompt: str) -> str:
        raise RuntimeError("network down")

    with caplog.at_level("INFO", logger="illustration_engine.retrieval"):
        retrieve_illustrations(conn, mode="production", passage_reference="Jn 3,16", llm_generate=broken_llm)
    conn.close()

    records = [r for r in caplog.records if "illustration_retrieval" in r.message]
    assert len(records) == 1
    assert f"reason={REASON_PLANNER_ERROR}" in records[0].message


def test_retrieval_log_line_never_contains_free_text_keywords_or_story_content(caplog) -> None:
    """Same content-free boundary `RetrievalDiagnostics` itself enforces
    (see `test_diagnostics_dataclass_has_no_raw_text_field`) must hold for
    the log line too -- a distinctive keyword/story string must never
    leak into the log even though it drove the (rejected) match."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    _make_published_unit(
        conn, story_id, title_hu="Irgalmas apa és a tékozló fiú konkrét egyedi cím",
        modern_hu_text="Ez a sztori szövege, aminek soha nem szabad logba kerülnie.",
        summary_hu=_VALID_SUMMARY,
    )
    conn.commit()

    llm = _llm_dispatch(
        {"keywords_hu": ["egyedi_kulcsszo_amit_soha_nem_szabad_logolni"]},
        {"results": []},
    )
    with caplog.at_level("INFO", logger="illustration_engine.retrieval"):
        retrieve_illustrations(conn, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)
    conn.close()

    combined = "\n".join(r.message for r in caplog.records)
    assert "egyedi_kulcsszo_amit_soha_nem_szabad_logolni" not in combined
    assert "tékozló fiú konkrét egyedi cím" not in combined
    assert "soha nem szabad logba kerülnie" not in combined


# ---------------------------------------------------------------------------
# 2026-09 runtime retrieval cutover: SupabaseIllustrationRepository +
# LocalSqliteIllustrationRepository, and the connection/repository dispatch
# every public entry point (find_candidates, retrieve_illustrations, ...)
# now goes through. Same fake-Postgrest-client pattern as tests/
# test_hebrew_analysis_repository_supabase.py -- no real network access.
# ---------------------------------------------------------------------------


class _FakeRpcResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeRpcCall:
    def __init__(self, recorder: list, name: str, params: dict, response_data: list[dict]) -> None:
        recorder.append((name, params))
        self._response_data = response_data

    def execute(self) -> _FakeRpcResponse:
        return _FakeRpcResponse(self._response_data)


class _FakeSupabaseClient:
    def __init__(self, rpc_response_data: list[dict]) -> None:
        self.rpc_calls: list[tuple[str, dict]] = []
        self._rpc_response_data = rpc_response_data

    def rpc(self, name: str, params: dict) -> _FakeRpcCall:
        return _FakeRpcCall(self.rpc_calls, name, params, self._rpc_response_data)


def _rpc_row(**overrides) -> dict:
    base = {
        "unit_id": 1, "title_hu": "Irgalmas apa", "modern_hu_text": "Szöveg.",
        "summary_hu": "Egy irgalmas apa története.", "moral_hu": None,
        "topics": ["irgalom"], "tone": "komoly", "homiletic_functions": ["szemlelteto_pelda"],
        "source_title": "Test Source", "source_code": "SRC", "tradition": "test tradition",
        "license_status": "public_domain_confirmed",
    }
    base.update(overrides)
    return base


def test_supabase_repository_fetch_eligible_units_maps_rpc_rows() -> None:
    client = _FakeSupabaseClient([_rpc_row()])
    repo = SupabaseIllustrationRepository(client=client)

    candidates = repo.fetch_eligible_units(mode="production")

    assert len(candidates) == 1
    c = candidates[0]
    assert c.unit_id == 1
    assert c.title_hu == "Irgalmas apa"
    assert c.topics == ("irgalom",)
    assert c.homiletic_functions == ("szemlelteto_pelda",)
    assert c.provenance_status == "published"


def test_supabase_repository_issues_exactly_one_rpc_call_no_n_plus_1() -> None:
    """The core no-N+1 guarantee: regardless of how many candidates the
    RPC returns, fetch_eligible_units must call the RPC exactly once."""
    client = _FakeSupabaseClient([_rpc_row(unit_id=i) for i in range(1, 51)])
    repo = SupabaseIllustrationRepository(client=client)

    candidates = repo.fetch_eligible_units(mode="production")

    assert len(candidates) == 50
    assert client.rpc_calls == [("get_published_illustration_candidates", {})]


def test_supabase_repository_empty_result_is_empty_list_not_error() -> None:
    client = _FakeSupabaseClient([])
    repo = SupabaseIllustrationRepository(client=client)

    candidates = repo.fetch_eligible_units(mode="production")

    assert candidates == []


def test_supabase_repository_development_mode_not_implemented() -> None:
    """No Supabase-side dev-mode RPC exists yet -- must fail loudly and
    explicitly, never silently fall back to production-mode data or an
    empty list that could be misread as 'no candidates'."""
    client = _FakeSupabaseClient([])
    repo = SupabaseIllustrationRepository(client=client)

    with pytest.raises(NotImplementedError):
        repo.fetch_eligible_units(mode="development")


def test_as_repository_dispatch_wraps_raw_connection() -> None:
    """find_candidates/retrieve_illustrations still accept a raw
    sqlite3.Connection directly (backward compatibility with every
    existing call site and every test above this point in this file)."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Publikált")
    conn.commit()

    candidates = find_candidates(conn, intent=_ANY_INTENT, mode="production", limit=10, min_relevance=0.0)
    conn.close()

    assert [c.unit_id for c in candidates] == [unit_id]


def test_find_candidates_accepts_supabase_repository_directly() -> None:
    """The SAME find_candidates() entry point, given a
    SupabaseIllustrationRepository instead of a sqlite3.Connection,
    applies the EXACT SAME threshold/scoring logic -- no code path
    difference beyond which object produced the candidate list."""
    client = _FakeSupabaseClient([_rpc_row(unit_id=42, title_hu="Irgalmas apa és a tékozló fiú")])
    repo = SupabaseIllustrationRepository(client=client)

    intent = RetrievalIntent(keywords_hu=("irgalmas",))
    candidates = find_candidates(repo, intent=intent, mode="production", limit=10)

    assert [c.unit_id for c in candidates] == [42]


def test_full_pipeline_end_to_end_with_supabase_repository() -> None:
    """Stage 0 (planner) / Stage A (local_relevance_score, threshold) /
    Stage B (ranker prompt/parse) are ALL exercised, completely
    unmodified, with a SupabaseIllustrationRepository standing in for
    the SQLite connection every other end-to-end test in this file
    uses. This is the direct regression test for 'Stage 0/A/B logic
    unchanged' under the runtime retrieval cutover."""
    client = _FakeSupabaseClient([
        _rpc_row(unit_id=7, title_hu="Irgalmas apa", summary_hu="Egy irgalmas apa története a hazatérésről.")
    ])
    repo = SupabaseIllustrationRepository(client=client)

    llm = _llm_dispatch(
        {"keywords_hu": ["irgalmas", "hazatérés"]},
        {"results": [{"unit_id": 7, "score": 0.95, "reason": "Nagyon releváns.", "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )
    results = retrieve_illustrations(repo, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm)

    assert len(results) == 1
    assert results[0].unit_id == 7
    assert results[0].modern_hu_text == "Szöveg."  # verbatim from the RPC row, never from the ranker
    assert client.rpc_calls == [("get_published_illustration_candidates", {})]  # one RPC call total


def test_supabase_repository_never_used_for_development_mode_via_public_entry_point() -> None:
    client = _FakeSupabaseClient([])
    repo = SupabaseIllustrationRepository(client=client)

    with pytest.raises(NotImplementedError):
        find_candidates(repo, intent=_ANY_INTENT, mode="development", limit=10)


def test_local_sqlite_repository_class_matches_prior_inline_behavior() -> None:
    """LocalSqliteIllustrationRepository, used explicitly rather than via
    the connection-dispatch shortcut, produces the identical result --
    pins that extracting it out of _fetch_and_score_candidates changed
    nothing behaviorally."""
    conn = _fresh_connection()
    source_id = _make_source(conn)
    story_id = _make_story(conn, source_id)
    unit_id = _make_published_unit(conn, story_id, title_hu="Publikált")
    conn.commit()

    repo = LocalSqliteIllustrationRepository(conn)
    candidates = repo.fetch_eligible_units(mode="production")
    conn.close()

    assert [c.unit_id for c in candidates] == [unit_id]
    assert candidates[0].provenance_status == "published"


def test_candidate_fetch_error_fails_closed_never_propagates_exception() -> None:
    """The core regression test for the runtime retrieval cutover's
    fail-closed gap fix: a repository whose fetch_eligible_units raises
    (e.g. a real Supabase RPC/network failure) must NEVER propagate an
    exception up through retrieve_illustrations_with_diagnostics -- and
    must be reported as a DISTINCT reason from REASON_NO_LOCAL_CANDIDATES
    (a genuinely empty, successfully-fetched pool)."""

    class _BrokenRepository:
        def fetch_eligible_units(self, *, mode):
            raise RuntimeError("simulated Supabase network failure")

    llm = _llm_dispatch({"keywords_hu": ["irgalmas"]}, {"results": []})
    results, diag = retrieve_illustrations_with_diagnostics(
        _BrokenRepository(), mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )

    assert results == []
    assert diag.reason == REASON_CANDIDATE_FETCH_ERROR
    assert diag.reason != REASON_NO_LOCAL_CANDIDATES


def test_candidate_fetch_error_via_supabase_repository_rpc_failure() -> None:
    """End-to-end version of the above, specifically through
    SupabaseIllustrationRepository -- a failing RPC call must surface as
    REASON_CANDIDATE_FETCH_ERROR, not crash the caller."""

    class _FailingRpcClient:
        def rpc(self, name, params):
            raise ConnectionError("simulated network outage")

    repo = SupabaseIllustrationRepository(client=_FailingRpcClient())
    llm = _llm_dispatch({"keywords_hu": ["irgalmas"]}, {"results": []})
    results, diag = retrieve_illustrations_with_diagnostics(
        repo, mode="production", passage_reference="Lk 15,11-24", llm_generate=llm,
    )

    assert results == []
    assert diag.reason == REASON_CANDIDATE_FETCH_ERROR
