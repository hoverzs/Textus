from __future__ import annotations

import pytest

import original_language_concordance as olc
from ruf_bible_local_db import DEFAULT_DATABASE_PATH as RUF_DATABASE_PATH

# Phase 2B — this is a genuinely optional external artifact, not a test
# infrastructure gap: the RÚF 2014 Hungarian Bible text is under a
# contractual licence with the Hungarian Bible Society that explicitly
# forbids committing it to version control (see .gitignore's dedicated
# warning next to `data/generated/ruf_bible.sqlite3`). A clean checkout
# correctly does not have it; only a local production/dev environment with
# its own licensed copy does.
requires_ruf_database = pytest.mark.skipif(
    not RUF_DATABASE_PATH.exists(),
    reason="RÚF 2014 Hungarian Bible text is licensed and intentionally not committed to git",
)


def test_detect_query_kind_hebrew_strong() -> None:
    assert olc.detect_query_kind("H3467") == "strong_hebrew"
    assert olc.detect_query_kind("h3467") == "strong_hebrew"
    assert olc.detect_query_kind("H1234A") == "strong_hebrew"


def test_detect_query_kind_greek_strong() -> None:
    assert olc.detect_query_kind("G2316") == "strong_greek"
    assert olc.detect_query_kind("g2316") == "strong_greek"


def test_detect_query_kind_hebrew_script() -> None:
    assert olc.detect_query_kind("יָשַׁע") == "hebrew_lemma"


def test_detect_query_kind_greek_script() -> None:
    assert olc.detect_query_kind("θεός") == "greek_lemma"


def test_detect_query_kind_hungarian_text_is_unknown() -> None:
    assert olc.detect_query_kind("szeretet") == "unknown"
    assert olc.detect_query_kind("örök élet") == "unknown"
    assert olc.detect_query_kind("") == "unknown"


def test_is_original_language_query() -> None:
    assert olc.is_original_language_query("H3467") is True
    assert olc.is_original_language_query("G2316") is True
    assert olc.is_original_language_query("szeretet") is False


def test_search_original_unknown_query_returns_empty() -> None:
    assert olc.search_original("szeretet") == []


def test_search_original_hebrew_strong_is_deduplicated_and_ordered() -> None:
    from bible_engine.hebrew_token_repository import HebrewTokenRepository

    hits = olc.search_original("H3467", with_hungarian_context=False)
    raw_tokens = HebrewTokenRepository().by_strong_id("H3467")
    unique_stable_keys = {t.stable_key for t in raw_tokens}

    assert len(hits) > 0
    # A nyers lekérdezés (komponens- + flat 'token'-szerep sor miatt)
    # kétszerezi a találatokat — a modulnak pontosan az egyedi token-ök
    # számára kell csökkentenie, NEM (book,chapter,verse,strong_id)
    # szerint (egy versben jogosan előfordulhat ugyanaz a szó kétszer).
    assert len(hits) == len(unique_stable_keys)
    assert len(hits) < len(raw_tokens)
    ordinals = [h.ordinal for h in hits]
    assert ordinals == sorted(ordinals), "a találatoknak kanonikus sorrendben kell lenniük"
    assert all(h.language == "héber" for h in hits)


def test_search_original_greek_lemma_strips_pilcrow_annotation() -> None:
    """A TAGNT forrás bekezdésjelet (¶) fűz néhány szóalak végéhez (pl.
    Jn 15,10-ben az "ἀγάπῃ" második előfordulása "ἀγάπῃ.¶"-ként volt
    tárolva) — élő tesztelés során ez látszólagos, "szennyezett"
    duplikátumként jelent meg a keresési találatok között. A ¶-t a
    `surface` mezőből el kell távolítani; a versen belüli valódi, kétszeri
    előfordulás (más szópozíción) továbbra is két külön találat marad."""
    hits = olc.search_original("ἀγάπη", with_hungarian_context=False)
    jn15_hits = [h for h in hits if h.book_abbr == "Jn" and h.chapter == 15 and h.verse == 10]
    assert len(jn15_hits) == 2, "Jn 15,10-ben a szó valóban kétszer fordul elő (más szópozíción)"
    assert all("¶" not in h.surface for h in jn15_hits)


def test_search_original_greek_strong_returns_hits() -> None:
    hits = olc.search_original("G2316", with_hungarian_context=False)

    assert len(hits) > 0
    assert all(h.language == "görög" for h in hits)
    assert all(h.strong_id == "G2316" for h in hits)


@requires_ruf_database
def test_search_original_attaches_hungarian_context_by_default() -> None:
    hits = olc.search_original("G2316")

    assert len(hits) > 0
    assert any(h.hungarian_context for h in hits), (
        "legalább néhány találatnak legyen magyar kontextusa (a helyi RÚF-DB-ből)"
    )


def test_search_original_hebrew_strong_bare_number_matches_lettered_variant() -> None:
    """A STEPBible TAHOT-adatban sok Strong-szám kizárólag betű-
    suffixummal ellátott változatként létezik (pl. "H2617A"/"H2617B"
    a "H2617" helyett) — a felhasználó viszont a szokásos, suffixum
    nélküli formát írja be. Élő tesztelés során ez H2617-re (חֶסֶד)
    0 találatot adott, holott a szónak sok előfordulása van."""
    hits = olc.search_original("H2617", with_hungarian_context=False)
    assert len(hits) > 0
    assert all(h.language == "héber" for h in hits)


def test_search_original_hebrew_lemma_ignores_cantillation_marks() -> None:
    """A TAHOT lemma-mező gyakran tartalmaz kantillációs (te'amim)
    jeleket (pl. "חֶ֫סֶד"), amit egy felhasználó normál begépeléssel/
    beillesztéssel szinte sosem ír be (pl. "חֶסֶד") — a pontos
    egyezés emiatt adott 0 találatot élő tesztelés során, holott a
    szó valójában sokszor előfordul."""
    hits = olc.search_original("חֶסֶד", with_hungarian_context=False)
    assert len(hits) > 0
    assert all(h.language == "héber" for h in hits)


def test_search_original_hebrew_lemma_matches_strong_lookup_book() -> None:
    strong_hits = olc.search_original("H3467", with_hungarian_context=False)
    lemma = None
    from bible_engine.hebrew_token_repository import HebrewTokenRepository

    repo = HebrewTokenRepository()
    tokens = repo.by_strong_id("H3467")
    if tokens:
        lemma = tokens[0].lemma
    if not lemma:
        pytest.skip("nincs elérhető lemma a tesztkörnyezetben")

    lemma_hits = olc.search_original(lemma, with_hungarian_context=False)
    assert len(lemma_hits) > 0
    assert all(h.language == "héber" for h in lemma_hits)
