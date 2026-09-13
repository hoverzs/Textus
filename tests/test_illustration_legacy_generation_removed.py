"""PHASE 3I.1 (2026-08-28): eltávolítottuk a normál, user-facing
"Illusztrációk" tab korábbi, szabad LLM-generálású story-blokkját
(SECTION_PROMPTS["illustrations"] -- "Klasszikus tanmesék" / "Valós
anekdoták és esetek" / "Mai, hétköznapi történet" / "Bevezető
illusztráció"). Ez a blokk forrás és provenance nélküli, kitalált
történeteket adott a felhasználónak -- sérti a Phase 3I "NO GENERATED
FAKE STORIES" elvét.

A tab EGYETLEN tartalma mostantól `illustration_retrieval_ui.
render_illustration_search_action` -- a történet mindig
`illustration_engine.retrieval`-ből, a DB-ből jön; az LLM csak
rangsorol/magyaráz, sosem ír történetet.

Forrás- és adatszintű ellenőrzés (a `test_legacy_preset_block_removed.py`
mintáját követve) -- nem Streamlit AppTest-alapú renderelés, az app.py
mérete miatt ez a gyors, stabil, karbantartható mód.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from illustration_engine.illustration_sqlite import (
    create_schema,
    insert_illustration_unit,
    insert_source,
    insert_story,
    update_unit_machine_qa,
)
from illustration_engine.retrieval import retrieve_illustrations

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = (ROOT / "app.py").read_text(encoding="utf-8")
RETRIEVAL_UI_SRC = (ROOT / "illustration_retrieval_ui.py").read_text(encoding="utf-8")
RETRIEVAL_ENGINE_SRC = (ROOT / "illustration_engine" / "retrieval.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. A legacy story-generation prompt és a rá mutató hívási pontok eltűntek
#    app.py-ból.
# ---------------------------------------------------------------------------


def test_legacy_illustration_prompt_headings_removed_from_app_source():
    for marker in (
        "## Klasszikus tanmesék",
        "## Valós anekdoták és esetek",
        "## Mai, hétköznapi történet",
        "## Bevezető illusztráció",
        "ILLUSZTRÁCIÓK — ELMESÉLHETŐ TÖRTÉNETEK",
    ):
        assert marker not in APP_SRC, marker


def test_illustrations_key_no_longer_wired_into_section_prompts_or_labels():
    assert '"illustrations": """{alap}' not in APP_SRC
    assert '"illustrations": "Illusztrációk",' not in APP_SRC


def test_illustrations_tab_no_longer_calls_render_section_tab():
    start = APP_SRC.index("with tabs[6]:")
    end = APP_SRC.index("with tabs[7]:")
    body = APP_SRC[start:end]
    assert 'key="illustrations"' not in body
    assert "render_section_tab(" not in body
    assert "render_illustration_search_action(generate_fn=generate_text)" in body


def test_generate_section_would_fail_closed_if_ever_called_for_illustrations():
    """Nincs élő hívási pont, de védekező jelleggel: ha valami mégis
    meghívná `generate_section("illustrations")`-t, a hiányzó
    SECTION_PROMPTS kulcs miatt azonnal KeyError-ral bukjon el -- ne
    generáljon csendben történetet."""
    start = APP_SRC.index("SECTION_PROMPTS = {")
    end = APP_SRC.index("\nSECTION_LABELS = {")
    section_prompts_src = APP_SRC[start:end]
    assert '"illustrations": """' not in section_prompts_src
    assert '\n    "illustrations":' not in section_prompts_src


def test_refinement_chat_no_longer_reachable_for_illustrations():
    """A generic "Finomítás" chatet (`refinement_chat`) korábban a most
    törölt `render_section_tab(key="illustrations", ...)` hívás kötötte
    az "illustrations" session-kulcshoz. Mivel az egyetlen hívási pont
    megszűnt, ez a chat-instancia strukturálisan elérhetetlen -- nem
    csak szűkítve, hanem teljesen megszűnt."""
    assert 'refinement_chat("Illusztrációk"' not in APP_SRC
    assert 'refinement_chat(chat_title or header, key, f"{key}_chat")' in APP_SRC


# ---------------------------------------------------------------------------
# 2. A retrieval UI modul forrása sem tartalmaz legacy story-generation
#    promptot vagy közvetlen `generate_text` hívást -- kizárólag a
#    retrieval enginen (injektált `llm_generate` callback) keresztül
#    érhető el az LLM.
# ---------------------------------------------------------------------------


def test_retrieval_ui_source_has_no_legacy_story_prompt_markers():
    for marker in (
        "## Klasszikus tanmesék",
        "## Valós anekdoták és esetek",
        "## Mai, hétköznapi történet",
        "## Bevezető illusztráció",
        "haszid",
    ):
        assert marker not in RETRIEVAL_UI_SRC, marker


def test_retrieval_ui_never_calls_generate_text_directly():
    """A modul kizárólag az injektált `generate_fn`-en (a `_llm` wrapperen
    keresztül) hívja az LLM-et, közvetlenül sosem a `generate_text`
    globális függvényt -- ez a dependency-injection minta zárja ki, hogy
    a modul saját maga indítson egy szabad story-generation promptot."""
    assert "generate_text(" not in RETRIEVAL_UI_SRC


def test_retrieval_engine_source_has_no_legacy_story_prompt_markers():
    for marker in (
        "## Klasszikus tanmesék",
        "## Valós anekdoták és esetek",
        "## Mai, hétköznapi történet",
        "## Bevezető illusztráció",
    ):
        assert marker not in RETRIEVAL_ENGINE_SRC, marker


# ---------------------------------------------------------------------------
# 3. Engine-szintű viselkedési szerződés a user-facing modulra nézve:
#    DB találat -> csak DB story; nincs találat -> fail-closed; nincs
#    generative fallback; a megjelenő modern_hu_text pontosan a DB
#    rekordból jön; a rangsorolási indoklás lehet LLM-output, a történet
#    szövege sosem.
# ---------------------------------------------------------------------------

_VALID_SUMMARY = " ".join(["szo"] * 45)


def _fresh_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def _seed_published_unit(conn: sqlite3.Connection) -> tuple[int, str]:
    source_id = insert_source(
        conn, code="SRC", title="Test Source", orig_language="en",
        license_status="public_domain_confirmed", license_basis_hu="x",
        reliability_tier="high", tradition="tradition",
    )
    original_text = "Az irgalmas atya története a tékozló fiúról."
    story_id = insert_story(
        conn, source_id=source_id, external_ref="1", canonical_key="key-1",
        title_original="Original Title", adaptation_status="verbatim_transcription",
        original_text=original_text,
        original_text_checksum=hashlib.sha256(original_text.encode("utf-8")).hexdigest(),
    )
    exact_db_text = "Ez a DB-ben tárolt, ellenőrzött, szó szerinti szöveg -- ez jelenhet meg a felhasználónak."
    unit_id = insert_illustration_unit(
        conn, story_id=story_id, unit_index=1, derivation_type="full_story_translation",
        status="published", title_hu="Tékozló fiú", modern_hu_text=exact_db_text,
        summary_hu=_VALID_SUMMARY,
        human_reviewed_at="2026-08-28T00:00:00+00:00",
    )
    update_unit_machine_qa(conn, unit_id=unit_id, qa_status="passed", qa_model="m", qa_prompt_version="v1")
    conn.commit()
    return unit_id, exact_db_text


_RANKER_MARKER = "JELÖLTEK (kizárólag ezek közül"


def _dispatch_llm(planner_response: dict, ranker_response) -> callable:
    """Phase 3I.2: `retrieve_illustrations` now makes TWO LLM calls
    (Stage 0 planner, then Stage B ranker) -- dispatches on
    `_RANKER_MARKER`, which only the ranking prompt contains."""
    ranker_text = json.dumps(ranker_response) if isinstance(ranker_response, dict) else ranker_response

    def _llm(prompt: str) -> str:
        if _RANKER_MARKER in prompt:
            return ranker_text
        return json.dumps(planner_response)

    return _llm


def test_db_hit_shows_only_db_sourced_story_never_llm_authored_text():
    conn = _fresh_connection()
    unit_id, exact_db_text = _seed_published_unit(conn)

    llm_invented_story = "Ez egy KITALÁLT, az LLM által írt sztori -- ha ez jelenne meg, az hiba lenne."

    fake_llm = _dispatch_llm(
        {"keywords_hu": ["tékozló", "fiú"]},
        {"results": [{"unit_id": unit_id, "score": 0.9, "reason": llm_invented_story, "match_tier": "DIRECT_ANALOGY", "keep": True}]},
    )

    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24",
        llm_generate=fake_llm,
    )

    assert len(results) == 1
    # A megjelenített történet PONTOSAN a DB rekordból jön.
    assert results[0].modern_hu_text == exact_db_text
    # Az LLM "story-szerű" kitalációja legfeljebb a rank_reason mezőbe
    # kerülhet (rangsorolási indoklásként) -- a modern_hu_text mezőbe soha.
    assert results[0].modern_hu_text != llm_invented_story
    assert results[0].rank_reason == llm_invented_story


def test_no_db_hit_yields_fail_closed_empty_result_not_generated_fallback():
    conn = _fresh_connection()
    create_schema(conn)  # üres DB, nincs unit

    ranker_calls = []

    def fake_llm(prompt: str) -> str:
        if _RANKER_MARKER in prompt:
            ranker_calls.append(prompt)
            return json.dumps({"results": []})
        # Stage 0 (planner) mindig lefut -- ehhez kell tudnia, mihez
        # pontozzon; ez önmagában sosem tud story-t vagy candidate ID-t
        # visszaadni (ld. RetrievalIntent mezői).
        return json.dumps({"keywords_hu": ["bármi"]})

    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Jak 3,2-12",
        llm_generate=fake_llm,
    )

    assert results == []
    # Üres jelölthalmaznál a rangsoroló (Stage B) NEM is fut le -- nincs
    # esély rá, hogy bármi "kitaláljon" egy pótlástörténetet.
    assert ranker_calls == []


def test_malformed_ranker_output_still_yields_fail_closed_not_fabricated_story():
    conn = _fresh_connection()
    _seed_published_unit(conn)

    def broken_llm(prompt: str) -> str:
        return "ez nem JSON, és nem is történet -- csak egy hibás válasz"

    results = retrieve_illustrations(
        conn, mode="production", passage_reference="Lk 15,11-24",
        llm_generate=broken_llm,
    )

    assert results == []
