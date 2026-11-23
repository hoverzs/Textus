"""4. fázis, 2. lépés — a közös JSON-kinyerők azonossági és jellemzőtesztjei.

A két ``_ORIG_*`` függvény SZÓ SZERINTI másolat a 2026-11-23-i refaktor
előtti állapotból (a3e0e15): ``textus_summary_ai.extract_json_object``
(engedékeny; az entry_point, m4, main_idea és engagement modulban AST-szinten
azonos) és ``sermon_workshop_blueprint_ai._extract_json_object`` (szigorú
gyökerű; az arc modulban AST-szinten azonos). Ezek az orákulumok — ne
módosítsd őket.
"""

from __future__ import annotations

import ast
import importlib
import json
import random
import re
from pathlib import Path
from typing import Any

import pytest

import llm_text_utils
from llm_text_utils import extract_json_object_lenient, extract_json_object_strict_root

ROOT = Path(__file__).resolve().parents[1]


# --- Eredeti implementációk (orákulumok), változtatás nélkül ----------------

def _ORIG_extract_json_object(raw: str) -> dict[str, Any] | None:
    """Nyers modellválaszból JSON-objektum kinyerése (markdown fence tűréssel)."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        candidate_fixed = re.sub(r",\s*}", "}", candidate)
        candidate_fixed = re.sub(r",\s*]", "]", candidate_fixed)
        for attempt in (candidate, candidate_fixed):
            try:
                obj = json.loads(attempt)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _ORIG__extract_json_object(raw: Any) -> dict[str, Any] | None:
    """Önálló, kis JSON-kinyerő — szándékosan NEM importál más
    MI-modulokból, hogy ez a modul teljesen független maradjon.

    Megengedett, szűk tűrés: whitespace trim, markdown code-fence
    eltávolítás, egyetlen jól azonosítható JSON-object kibontása a
    szövegből, és a záró vessző (trailing comma) levágása objektum/lista
    végén — ez utóbbi UGYANAZ a szűk, biztonságos normalizálás, mint a
    `textus_summary_ai.extract_json_object`-ben. Nem próbál tetszőleges
    prózából JSON-t kitalálni, és nem fogad el sémán kívüli tartalmat."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        candidate_fixed = re.sub(r",\s*}", "}", candidate)
        candidate_fixed = re.sub(r",\s*]", "]", candidate_fixed)
        for attempt in (candidate, candidate_fixed):
            try:
                obj = json.loads(attempt)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


# --- Bemeneti tábla ----------------------------------------------------------

_OBJ = '{"recommended": "Isten megtart", "warnings": []}'
INPUTS: list[Any] = [
    None, "", "   ", "\n\t", "x", "null", "true", "0", "42", '"szöveg"',
    # tiszta objektum, üres objektum, egymásba ágyazott, ékezetes
    _OBJ, "{}", '{"a": {"b": [1, 2, {"c": null}]}}', '{"á": "őű", "Ő": ["é"]}',
    "  " + _OBJ + "  \n",
    # kódkerítés változatai
    "```json\n" + _OBJ + "\n```", "```\n" + _OBJ + "\n```", "```JSON\n" + _OBJ + "```",
    "Íme:\n```json\n" + _OBJ + "\n```\nKöszönöm.", "```json\n```", "```json\n[1,2]\n```",
    "```json\n{\"a\": 1,}\n```", "```json\n{\"a\": 1}\n``` és ```json\n{\"b\": 2}\n```",
    "```json\n{\"a\": 1}", "{\"a\": \"```\"}",
    # lista gyökér — itt tér el a két változat
    "[]", "[1, 2]", '[{"a": 1}]', '[{"a": 1}, {"b": 2}]', '[ {"a": [1,2]} ]',
    '[{"a": 1},]', '[[{"a": 1}]]', '["{", "}"]', '"{\\"a\\": 1}"',
    # próza előtte/utána
    "A válasz: " + _OBJ, _OBJ + " — ennyi.", "Előtte " + _OBJ + " utána", "{ nem json }",
    # záró vessző
    '{"a": 1,}', '{"a": [1, 2,],}', '{"a": [1, 2, ],\n}', '{"a": "x,}"}', '{"a": ",]",}',
    "Szöveg {\"a\": 1,} szöveg",
    # csonka / hibás
    '{"a": 1', '{"a": ', '"a": 1}', "}{", "{}}", "{{}}", '{"a": 1} {"b": 2}',
    '{"a": 1}\n{"b": 2}', "{'a': 1}", '{"a": NaN}', '{"a": Infinity}', '{"a": 1e999}',
    '{"a": 1, "a": 2}', '{"a": "\\ud800"}',
    # LLM-hibaszövegek és szentinelek
    "⚠️ Hiba: kvóta", "⏳ Túl sok kérés", "__OUTLINE_TRUNCATED__",
    _OBJ + "\n\n⚠️ A válasz csonkolva lehet.",
]
NON_STR_INPUTS: list[Any] = [0, 5, 3.5, False, True, [], {}, {"a": 1}, ["{}"], (1,), b"{}", b'{"a": 1}']


def _random_inputs(n: int = 400) -> list[str]:
    """Determinisztikus, véletlenszerűen összerakott szövegek a fenti
    építőelemekből (kerítés, próza, lista, záró vessző, csonkolás)."""
    rnd = random.Random(20261123)
    parts = ["{", "}", "[", "]", ",", " ", "\n", '"a"', ":", "1", '"x"', "```", "```json",
             "null", "Szöveg", "á", "{}", "[]", '{"k": [1,]}', '{"k": 2}', ",}", ",]"]
    out = []
    for _ in range(n):
        out.append("".join(rnd.choice(parts) for _ in range(rnd.randint(1, 14))))
    return out


def _outcome(fn, raw):
    try:
        return ("ok", fn(raw))
    except Exception as exc:  # noqa: BLE001 — a kivétel típusa is a viselkedés része
        return ("exc", type(exc).__name__)


ALL_STR = INPUTS + _random_inputs()


# --- 1. A közös függvények azonosak az eredetiekkel -------------------------

@pytest.mark.parametrize("raw", INPUTS + NON_STR_INPUTS, ids=repr)
def test_lenient_matches_original(raw):
    assert _outcome(extract_json_object_lenient, raw) == _outcome(_ORIG_extract_json_object, raw)


@pytest.mark.parametrize("raw", INPUTS + NON_STR_INPUTS, ids=repr)
def test_strict_root_matches_original(raw):
    assert _outcome(extract_json_object_strict_root, raw) == _outcome(_ORIG__extract_json_object, raw)


def test_random_inputs_match_originals():
    for raw in _random_inputs():
        assert _outcome(extract_json_object_lenient, raw) == _outcome(_ORIG_extract_json_object, raw), raw
        assert _outcome(extract_json_object_strict_root, raw) == _outcome(_ORIG__extract_json_object, raw), raw


# --- 2. A modulok a régi néven, azonos viselkedéssel érik el -----------------

LENIENT_MODULES = [
    "textus_summary_ai", "sermon_workshop_entry_point_ai", "sermon_workshop_m4_ai",
    "textus_main_idea_ai", "sermon_workshop_engagement_ai",
]
STRICT_MODULES = ["sermon_workshop_arc_ai", "sermon_workshop_blueprint_ai"]


@pytest.mark.parametrize("module_name", LENIENT_MODULES)
def test_lenient_modules_alias_the_shared_function(module_name):
    mod = importlib.import_module(module_name)
    assert mod.extract_json_object is llm_text_utils.extract_json_object_lenient


@pytest.mark.parametrize("module_name", STRICT_MODULES)
def test_strict_modules_keep_own_entry_point_with_identical_results(module_name):
    mod = importlib.import_module(module_name)
    for raw in ALL_STR + NON_STR_INPUTS:
        assert _outcome(mod._extract_json_object, raw) == _outcome(_ORIG__extract_json_object, raw), raw


@pytest.mark.parametrize("module_name", STRICT_MODULES)
def test_strict_entry_point_only_delegates(module_name):
    tree = ast.parse((ROOT / f"{module_name}.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_extract_json_object")
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    assert len(body) == 1 and isinstance(body[0], ast.Return)
    call = body[0].value
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert call.func.id == "extract_json_object_strict_root"


def test_m4_public_name_still_importable_for_dependants():
    from sermon_workshop_m4_ai import __all__ as m4_all, extract_json_object

    assert "extract_json_object" in m4_all
    assert extract_json_object is extract_json_object_lenient


@pytest.mark.parametrize("module_name", LENIENT_MODULES)
def test_no_private_lenient_copy_left(module_name):
    tree = ast.parse((ROOT / f"{module_name}.py").read_text(encoding="utf-8"))
    assert not [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "extract_json_object"]


# --- 3. Jellemzőtesztek: a jelenlegi szabályok rögzítése (nem változtatunk) --

def test_list_root_is_where_the_two_variants_differ():
    assert extract_json_object_lenient('[{"a": 1}]') == {"a": 1}
    assert extract_json_object_strict_root('[{"a": 1}]') is None
    assert extract_json_object_lenient('[{"a": 1}, {"b": 2}]') is None
    assert extract_json_object_strict_root('[{"a": 1}, {"b": 2}]') is None
    assert extract_json_object_lenient("[1, 2]") is None
    assert extract_json_object_strict_root("[1, 2]") is None


def test_input_guard_differs_for_non_string_inputs():
    """Az engedékeny változat `not raw` ellenőrzéssel kezd, a szigorú csak a
    None-t szűri, és `str(raw)`-t dolgoz fel. A modellválasz mindig szöveg,
    ezért ez a gyakorlatban nem számít; csak rögzítjük."""
    assert extract_json_object_lenient({}) is None
    assert extract_json_object_strict_root({}) == {}  # str({}) == "{}"
    # str(b"{}") == "b'{}'" — mindkettő kibontja belőle a "{}"-t
    assert extract_json_object_lenient(b"{}") == {}
    assert extract_json_object_strict_root(b"{}") == {}
    # str({"a": 1}) == "{'a': 1}" — nem érvényes JSON
    assert extract_json_object_lenient({"a": 1}) is None
    assert extract_json_object_strict_root({"a": 1}) is None
    for falsy in (0, [], False):
        assert extract_json_object_lenient(falsy) is None
        assert extract_json_object_strict_root(falsy) is None


@pytest.mark.parametrize("fn", [extract_json_object_lenient, extract_json_object_strict_root])
def test_shared_tolerances(fn):
    obj = {"recommended": "Isten megtart", "warnings": []}
    assert fn("```json\n" + _OBJ + "\n```") == obj
    assert fn("Íme:\n```\n" + _OBJ + "\n```") == obj
    assert fn("A válasz: " + _OBJ + " — ennyi.") == obj
    assert fn('{"a": [1, 2,],}') == {"a": [1, 2]}
    assert fn('{"a": 1') is None
    assert fn("") is None and fn("   ") is None and fn(None) is None
    assert fn('{"a": 1} {"b": 2}') is None
    # a hibaszöveghez fűzött csonkolási megjegyzés nem akadályozza a kinyerést
    assert fn(_OBJ + "\n\n⚠️ A válasz csonkolva lehet.") == obj


@pytest.mark.parametrize("fn", [extract_json_object_lenient, extract_json_object_strict_root])
def test_first_fence_wins(fn):
    assert fn('```json\n{"a": 1}\n``` és ```json\n{"b": 2}\n```') == {"a": 1}


def test_developed_outline_extractor_is_a_different_variant_and_untouched():
    """A fejlesztett vázlat saját kinyerője nem javítja a záró vesszőt,
    ezért szándékosan kimaradt az összevonásból."""
    import sermon_workshop_developed_outline_ai as dev

    assert dev._extract_json_object('{"a": 1,}') is None
    assert extract_json_object_strict_root('{"a": 1,}') == {"a": 1}
    tree = ast.parse((ROOT / "sermon_workshop_developed_outline_ai.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_extract_json_object")
    assert "json.loads" in ast.unparse(fn)
