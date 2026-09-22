# ruff: noqa: E402
"""`_strip_full_response_duplicate` — konzervatív guard a `generate_text`
válaszban előforduló teljes önismétlés (a modell a saját válaszát szó
szerint megismétli) ellen.

Nem hív API-t / retry-t; pusztán a már megkapott szöveget vágja.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


EXEGESIS_BODY = """## Műfaj és szerkezet

A szakasz egy narratív dialógus része, amely bemutatja a szereplők közötti
feszültséget és annak teológiai jelentőségét egy hosszabb, összefüggő
bekezdésben, amely kellően hosszú ahhoz, hogy a duplikáció-detektor
biztonságosan tudjon dönteni a hasonlóság alapján.

## Kontextus

A közvetlen szövegkörnyezet és a tágabb kánoni ív egyaránt fontos ehhez a
szakaszhoz — ez a bekezdés is kellően hosszú, hogy ne essen a rövid
válaszokra vonatkozó biztonsági küszöb alá, amely megakadályozná a téves
pozitív találatokat rövid szövegeknél.

## Prédikációs haszon

A szakasz gazdag forrása az igehirdetésnek, és több gyakorlati alkalmazási
pontot is kínál a gyülekezeti élet és a személyes kegyesség számára,
lezárva ezzel a válasz első, teljes és önmagában koherens példányát."""


def test_a_full_response_repeated_twice_keeps_only_first_copy():
    import app as app_mod

    duplicated = EXEGESIS_BODY + "\n\n" + EXEGESIS_BODY
    result = app_mod._strip_full_response_duplicate(duplicated)
    assert result.strip() == EXEGESIS_BODY.strip()
    assert result.count("## Műfaj és szerkezet") == 1
    assert result.count("## Prédikációs haszon") == 1


def test_b_response_dashes_separator_then_same_response_keeps_only_first_copy():
    import app as app_mod

    duplicated = (
        EXEGESIS_BODY
        + "\n\n---\n\n# Exegézis — Szövegelemzés\n\n"
        + EXEGESIS_BODY
    )
    result = app_mod._strip_full_response_duplicate(duplicated)
    assert result.count("## Műfaj és szerkezet") == 1
    assert result.count("## Prédikációs haszon") == 1
    # A törött újrakezdés maradékai (elárvult "---" / "# ..." fejléc)
    # se maradjanak a végeredményben.
    assert not result.rstrip().endswith("---")
    assert "# Exegézis — Szövegelemzés" not in result


def test_c_partial_legitimate_repetition_is_left_untouched():
    import app as app_mod

    text = (
        EXEGESIS_BODY
        + "\n\n## Értelmezési kérdések\n\n"
        + "Mint fentebb, a Kontextus alcím alatt említettük, a szakasz "
        "szorosan kapcsolódik az előzményekhez, de ez itt csak egy rövid "
        "visszautalás, nem a teljes válasz megismétlése, és jelentősen "
        "más tartalmat is hozzátesz a korábbiakhoz képest, amivel a "
        "válasz érdemben bővül."
    )
    result = app_mod._strip_full_response_duplicate(text)
    assert result == text


def test_d_normal_non_repeating_response_is_left_untouched():
    import app as app_mod

    result = app_mod._strip_full_response_duplicate(EXEGESIS_BODY)
    assert result == EXEGESIS_BODY


def test_short_response_below_min_length_is_never_touched_even_if_literally_duplicated():
    import app as app_mod

    short = "## Cím\n\nRövid válasz."
    duplicated = short + "\n\n" + short
    result = app_mod._strip_full_response_duplicate(duplicated)
    assert result == duplicated


def test_non_string_or_empty_input_is_returned_unchanged():
    import app as app_mod

    assert app_mod._strip_full_response_duplicate("") == ""
    assert app_mod._strip_full_response_duplicate(None) is None


def test_regression_real_captured_gemini_duplicate_is_trimmed_to_single_copy():
    """A/B benchmark (2026-09-22, Exegézis fül, gemini-3-flash-preview, Mt
    5,14-16, r2 kör) — a modell a teljes válaszát megismételte, `---` +
    egy elárvult feladat-fejléc beékelésével a két példány között. Ez a
    fixture a valódi, rögzített API-választ tartalmazza."""
    import app as app_mod

    fixture_path = (
        ROOT / "tests" / "fixtures" / "gemini_full_response_duplicate_sample.md"
    )
    real_duplicate = fixture_path.read_text(encoding="utf-8")

    result = app_mod._strip_full_response_duplicate(real_duplicate)

    assert len(result) < len(real_duplicate)
    assert result.count("## Prédikációs haszon") == 1
    assert result.count("## Műfaj és szerkezet") == 1
    assert "# Exegézis — Szövegelemzés" not in result
    assert not result.rstrip().endswith("---")
