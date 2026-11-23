from __future__ import annotations

import json
import sys
from unittest.mock import patch

import concept_concordance as cc
from tests.local_data import requires_ruf_bible_db


def test_extract_json_plain() -> None:
    assert cc._extract_json('{"references": [], "keywords": []}') == {
        "references": [],
        "keywords": [],
    }


def test_extract_json_with_surrounding_noise() -> None:
    assert cc._extract_json('  {"a": 1}  \nextra text') == {"a": 1}


def test_extract_json_invalid_returns_none() -> None:
    assert cc._extract_json("not json at all") is None


@requires_ruf_bible_db
def test_validate_reference_valid() -> None:
    validated = cc._validate_reference("Lk 17,3-4")
    assert validated is not None
    book_abbr, chapter, verse_start, verse_end, context_text = validated
    assert book_abbr == "Lk"
    assert chapter == 17
    assert verse_start == 3
    assert verse_end == 4
    assert context_text


def test_validate_reference_unknown_book_returns_none() -> None:
    assert cc._validate_reference("Nemlétező könyv 1,1") is None


def test_validate_reference_out_of_range_verse_returns_none() -> None:
    assert cc._validate_reference("Jn 3,9999") is None


def test_app_module_falls_back_to_import_app_without_generate_text() -> None:
    """Teszt-/parancssori kontextusban a `__main__` (pl. pytest futtató)
    NEM rendelkezik `generate_text`-tel — ilyenkor a normál `import app`
    útvonalra kell esnie. (A `__main__`-t preferáló ágat — élő Streamlit-
    munkamenet esete, lásd `_app_module` docstringje — szándékosan NEM
    teszteljük `sys.modules["__main__"]` átírásával: ez a többi,
    AppTest-alapú teszt globális ScriptRunContext-állapotát rontja el.
    Az élő Streamlit-viselkedést a fejlesztés során böngészőn keresztül,
    valós renderelt oldalon ellenőriztük.)"""
    import app as app_mod

    main_module = sys.modules.get("__main__")
    assert main_module is None or not hasattr(main_module, "generate_text")
    assert cc._app_module() is app_mod


def test_search_concept_empty_question_returns_error() -> None:
    result = cc.search_concept("   ")
    assert result.error is not None
    assert result.references == []


def test_search_concept_propagates_api_error() -> None:
    import app as app_mod

    with patch.object(app_mod, "generate_text", return_value="⚠️ **Hiányzó API kulcs.**"):
        result = cc.search_concept("hol beszél a Biblia a megbocsátásról?")
    assert result.error == "⚠️ **Hiányzó API kulcs.**"


def test_search_concept_invalid_json_returns_error() -> None:
    import app as app_mod

    with patch.object(app_mod, "generate_text", return_value="nem JSON válasz"):
        result = cc.search_concept("hol beszél a Biblia a megbocsátásról?")
    assert result.error is not None
    assert result.references == []


@requires_ruf_bible_db
def test_search_concept_validates_and_dedupes_references() -> None:
    import app as app_mod

    payload = {
        "references": [
            {
                "reference": "Lk 17,3-4",
                "relation": "arnyalja",
                "reasoning": "A megbocsátás feltétele a megtérés.",
            },
            {
                "reference": "Lk 17,3-4",  # duplikátum — csak egyszer szabad megjelennie
                "relation": "megerosit",
                "reasoning": "Ismétlődő javaslat.",
            },
            {
                "reference": "Kitalált könyv 99,99",  # hallucinált — el kell dobni
                "relation": "megerosit",
                "reasoning": "Nem létezik.",
            },
        ],
        "keywords": ["megbocsát"],
        "original_language_terms": [],
    }

    with patch.object(app_mod, "generate_text", return_value=json.dumps(payload, ensure_ascii=False)):
        result = cc.search_concept("hol feltételes a megbocsátás?")

    assert result.error is None
    assert len(result.references) == 1
    assert result.references[0].book_abbr == "Lk"
    assert result.references[0].relation == "arnyalja"
    assert result.references[0].relation_label == "árnyalja a fogalmat"


@requires_ruf_bible_db
def test_search_concept_unknown_relation_defaults_to_megerosit() -> None:
    import app as app_mod

    payload = {
        "references": [
            {
                "reference": "Jn 16,33",
                "relation": "ismeretlen_ertek",
                "reasoning": "Békesség a bajok közepette.",
            }
        ],
        "keywords": [],
    }

    with patch.object(app_mod, "generate_text", return_value=json.dumps(payload, ensure_ascii=False)):
        result = cc.search_concept("van békességünk a bajok közben is?")

    assert len(result.references) == 1
    assert result.references[0].relation == "megerosit"


@requires_ruf_bible_db
def test_search_concept_keyword_hits_exclude_already_shown_verses() -> None:
    import app as app_mod

    payload = {
        "references": [
            {
                "reference": "Jn 3,16",
                "relation": "megerosit",
                "reasoning": "Isten szeretete.",
            }
        ],
        "keywords": ["szeretet"],
    }

    with patch.object(app_mod, "generate_text", return_value=json.dumps(payload, ensure_ascii=False)):
        result = cc.search_concept("hol beszél a Biblia Isten szeretetéről?")

    assert len(result.references) == 1
    for hit in result.keyword_hits:
        assert not (hit.book_abbr == "Jn" and hit.chapter == 3 and hit.verse == 16)


def test_search_concept_caps_keyword_and_term_counts() -> None:
    import app as app_mod

    payload = {
        "references": [],
        "keywords": [f"kulcsszo{i}" for i in range(10)],
        "original_language_terms": [{"term": f"G{1000 + i}"} for i in range(10)],
    }

    with patch.object(app_mod, "generate_text", return_value=json.dumps(payload, ensure_ascii=False)):
        result = cc.search_concept("teszt kérdés sok kulcsszóval")

    assert result.raw_keywords == [f"kulcsszo{i}" for i in range(10)]
    assert result.raw_terms == [f"G{1000 + i}" for i in range(10)]
