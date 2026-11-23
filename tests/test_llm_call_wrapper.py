"""4. fázis, 3. lépés — a közös LLM-hívásburok regressziós tesztjei.

Az ``_ORIG_call_generate`` SZÓ SZERINTI másolat a refaktor előtti
``textus_summary_ai._call_generate`` törzséből (d04b550). Az öt modul
(summary, entry_point, m4, m5, engagement) ``_call_generate`` függvénye a
refaktor előtt AST-szinten azonos volt, egyetlen eltéréssel: a modul saját
``*_SYSTEM_BUNDLE`` konstansa. Ezt az orákulum a ``_bundle`` paraméterben
kapja; a modul alapértelmezett hőmérsékletét a hívó adja át. Az orákulum
változtatás nélküli másolat — ne módosítsd.

A Streamlit helyett egy hamis ``streamlit`` modul áll be a ``sys.modules``-ba,
amelynek ``session_state``-je minden olvasást, írást és törlést naplóz; így a
hőmérséklet ideiglenes beállítása és visszaállítása lépésről lépésre
összevethető.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
import types
from pathlib import Path
from typing import Any

import pytest

import llm_text_utils
from llm_text_utils import call_generate_with_session_temperature

ROOT = Path(__file__).resolve().parents[1]


# --- Eredeti implementáció (orákulum), változtatás nélkül --------------------

def _ORIG_call_generate(
    generate_fn: Any,
    prompt: str,
    *,
    tab_label: str,
    temperature: float | None,
    _bundle: str,
) -> str:
    prev_temp = None
    touched_temp = False
    if temperature is not None:
        try:
            import streamlit as st

            prev_temp = st.session_state.get("temperature")
            st.session_state["temperature"] = float(temperature)
            touched_temp = True
        except Exception:
            touched_temp = False
    try:
        return generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=tab_label,
            use_cache=False,
            system_bundle=_bundle,
            include_brevity_directive=False,
        )
    finally:
        if touched_temp:
            try:
                import streamlit as st

                if prev_temp is None:
                    st.session_state.pop("temperature", None)
                else:
                    st.session_state["temperature"] = prev_temp
            except Exception:
                pass


# --- Megfigyelő segédek ------------------------------------------------------

_MISSING = object()


class _LoggingState(dict):
    def __init__(self, *a, fail_on: str | None = None, **kw):
        super().__init__(*a, **kw)
        self.log: list[tuple] = []
        self.fail_on = fail_on

    def get(self, key, default=None):
        self.log.append(("get", key))
        if self.fail_on == "get":
            raise RuntimeError("get")
        return super().get(key, default)

    def __setitem__(self, key, value):
        self.log.append(("set", key, value, type(value).__name__))
        if self.fail_on == "set" or (self.fail_on == "restore" and len(self.log) > 2):
            raise RuntimeError("set")
        super().__setitem__(key, value)

    def pop(self, key, *default):
        self.log.append(("pop", key))
        if self.fail_on == "pop":
            raise RuntimeError("pop")
        return super().pop(key, *default)


def _install_fake_streamlit(monkeypatch, *, prev=_MISSING, fail_on=None, unavailable=False):
    if unavailable:
        monkeypatch.setitem(sys.modules, "streamlit", None)  # import → ImportError
        return None
    state = _LoggingState(fail_on=fail_on)
    if prev is not _MISSING:
        dict.__setitem__(state, "temperature", prev)
    fake = types.ModuleType("streamlit")
    fake.session_state = state
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    return state


class _Recorder:
    def __init__(self, *, result: Any = "VÁLASZ", raises: BaseException | None = None):
        self.calls: list[tuple] = []
        self.result = result
        self.raises = raises

    def __call__(self, *args, **kwargs):
        st = sys.modules.get("streamlit")
        seen = dict.get(st.session_state, "temperature", "<nincs>") if st else "<nincs st>"
        self.calls.append((args, dict(kwargs), seen))
        if self.raises is not None:
            raise self.raises
        return self.result


def _run(fn, monkeypatch, *, temperature, bundle, setup: dict, **fn_kwargs):
    state = _install_fake_streamlit(monkeypatch, **setup)
    rec = _Recorder(**{k: v for k, v in fn_kwargs.items() if k in ("result", "raises")})
    try:
        out = ("ok", fn(rec, "PROMPT", tab_label="Fül", temperature=temperature, **bundle))
    except BaseException as exc:  # noqa: BLE001 — a kivétel is a viselkedés része
        out = ("exc", type(exc).__name__, str(exc))
    final = dict(state) if state is not None else None
    log = list(state.log) if state is not None else None
    return out, rec.calls, final, log


TEMPERATURES = [None, 0.15, 0.25, 0.3, 0, 0.0, 1, "0.4", "abc", float("inf")]
SETUPS = [
    {},  # nincs korábbi érték
    {"prev": 0.7},
    {"prev": None},  # kifejezett None: a visszaállítás törli a kulcsot
    {"prev": "szöveg"},
    {"prev": 0},
    {"fail_on": "get"},
    {"fail_on": "set"},
    {"fail_on": "restore", "prev": 0.7},
    {"fail_on": "pop"},
    {"unavailable": True},
]
OUTCOMES = [{}, {"result": ""}, {"result": None}, {"result": "⚠️ Hiba"},
            {"raises": RuntimeError("hálózat")}, {"raises": KeyboardInterrupt()}]


def _compare(monkeypatch, temperature, setup, outcome, bundle="BUNDLE-X"):
    new = _run(call_generate_with_session_temperature, monkeypatch, temperature=temperature,
               bundle={"system_bundle": bundle}, setup=setup, **outcome)
    old = _run(_ORIG_call_generate, monkeypatch, temperature=temperature,
               bundle={"_bundle": bundle}, setup=setup, **outcome)
    return new, old


# --- 1. A közös függvény lépésről lépésre azonos az eredetivel ---------------

@pytest.mark.parametrize("outcome", OUTCOMES, ids=repr)
@pytest.mark.parametrize("setup", SETUPS, ids=repr)
@pytest.mark.parametrize("temperature", TEMPERATURES, ids=repr)
def test_shared_wrapper_matches_original(monkeypatch, temperature, setup, outcome):
    new, old = _compare(monkeypatch, temperature, setup, outcome)
    assert new == old


def test_generate_fn_receives_exactly_the_original_arguments(monkeypatch):
    (_, calls, _, _), _ = _compare(monkeypatch, 0.15, {}, {})
    assert calls == [(
        ("PROMPT",),
        {
            "enable_google_search": False,
            "tab_label": "Fül",
            "use_cache": False,
            "system_bundle": "BUNDLE-X",
            "include_brevity_directive": False,
        },
        0.15,
    )]


# --- 2. Jellemzőtesztek: a session-hőmérséklet kezelése ----------------------

def test_temperature_is_set_during_call_and_restored(monkeypatch):
    out, calls, final, _ = _run(call_generate_with_session_temperature, monkeypatch,
                                temperature=0.25, bundle={"system_bundle": "B"}, setup={"prev": 0.7})
    assert out == ("ok", "VÁLASZ")
    assert calls[0][2] == 0.25
    assert final == {"temperature": 0.7}


def test_absent_or_none_previous_value_removes_the_key(monkeypatch):
    for setup in ({}, {"prev": None}):
        _, calls, final, _ = _run(call_generate_with_session_temperature, monkeypatch,
                                  temperature=1, bundle={"system_bundle": "B"}, setup=setup)
        assert calls[0][2] == 1.0 and isinstance(calls[0][2], float)
        assert final == {}


def test_none_temperature_leaves_session_untouched(monkeypatch):
    _, calls, final, log = _run(call_generate_with_session_temperature, monkeypatch,
                                temperature=None, bundle={"system_bundle": "B"}, setup={"prev": 0.7})
    assert log == [] and final == {"temperature": 0.7} and calls[0][2] == 0.7


def test_restore_happens_even_if_generate_fn_raises(monkeypatch):
    out, _, final, _ = _run(call_generate_with_session_temperature, monkeypatch,
                            temperature=0.15, bundle={"system_bundle": "B"}, setup={"prev": 0.9},
                            raises=RuntimeError("hálózat"))
    assert out == ("exc", "RuntimeError", "hálózat")
    assert final == {"temperature": 0.9}


def test_missing_streamlit_or_failing_session_is_silent(monkeypatch):
    for setup in ({"unavailable": True}, {"fail_on": "get"}, {"fail_on": "set"}):
        out, calls, _, _ = _run(call_generate_with_session_temperature, monkeypatch,
                                temperature=0.15, bundle={"system_bundle": "B"}, setup=setup)
        assert out == ("ok", "VÁLASZ") and len(calls) == 1


def test_unconvertible_temperature_is_skipped_silently(monkeypatch):
    out, calls, final, _ = _run(call_generate_with_session_temperature, monkeypatch,
                                temperature="abc", bundle={"system_bundle": "B"}, setup={"prev": 0.7})
    assert out == ("ok", "VÁLASZ") and calls[0][2] == 0.7 and final == {"temperature": 0.7}


# --- 3. Az öt modul: régi név, saját alapérték, saját system_bundle ---------

MODULES = {
    "textus_summary_ai": ("SUMMARY_SYSTEM_BUNDLE", 0.15),
    "sermon_workshop_entry_point_ai": ("ENTRY_POINT_SYSTEM_BUNDLE", 0.25),
    "sermon_workshop_m4_ai": ("M4_SYSTEM_BUNDLE", 0.15),
    "sermon_workshop_m5_ai": ("M5_SYSTEM_BUNDLE", 0.15),
    "sermon_workshop_engagement_ai": ("ENGAGEMENT_SYSTEM_BUNDLE", 0.3),
}


@pytest.mark.parametrize("module_name", sorted(MODULES))
def test_module_signature_and_default_temperature_unchanged(module_name):
    mod = importlib.import_module(module_name)
    bundle_name, default = MODULES[module_name]
    assert mod.DEFAULT_TEMPERATURE == default
    sig = inspect.signature(mod._call_generate)
    assert list(sig.parameters) == ["generate_fn", "prompt", "tab_label", "temperature"]
    assert sig.parameters["tab_label"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["temperature"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["temperature"].default == default


@pytest.mark.parametrize("setup", SETUPS, ids=repr)
@pytest.mark.parametrize("module_name", sorted(MODULES))
def test_module_wrapper_matches_original_with_its_own_bundle(monkeypatch, module_name, setup):
    mod = importlib.import_module(module_name)
    bundle_name, default = MODULES[module_name]
    bundle = getattr(mod, bundle_name)
    for outcome in OUTCOMES:
        # alapértelmezett hőmérséklettel (a modul saját DEFAULT_TEMPERATURE-e)
        state = _install_fake_streamlit(monkeypatch, **setup)
        rec = _Recorder(**outcome)
        try:
            got = ("ok", mod._call_generate(rec, "PROMPT", tab_label="Fül"))
        except BaseException as exc:  # noqa: BLE001
            got = ("exc", type(exc).__name__, str(exc))
        new = (got, rec.calls, dict(state) if state is not None else None,
               list(state.log) if state is not None else None)
        old = _run(_ORIG_call_generate, monkeypatch, temperature=default,
                   bundle={"_bundle": bundle}, setup=setup, **outcome)
        assert new == old
        # és kifejezett hőmérséklettel
        for t in (None, 0.9):
            state = _install_fake_streamlit(monkeypatch, **setup)
            rec = _Recorder(**outcome)
            try:
                got = ("ok", mod._call_generate(rec, "PROMPT", tab_label="Fül", temperature=t))
            except BaseException as exc:  # noqa: BLE001
                got = ("exc", type(exc).__name__, str(exc))
            new = (got, rec.calls, dict(state) if state is not None else None,
                   list(state.log) if state is not None else None)
            old = _run(_ORIG_call_generate, monkeypatch, temperature=t,
                       bundle={"_bundle": bundle}, setup=setup, **outcome)
            assert new == old


@pytest.mark.parametrize("module_name", sorted(MODULES))
def test_module_bundle_is_read_at_call_time(monkeypatch, module_name):
    """A modul a bundle-t hívásidőben olvassa — egy teszt általi felülírás
    (monkeypatch) ugyanúgy érvényesül, mint a refaktor előtt."""
    mod = importlib.import_module(module_name)
    bundle_name, _ = MODULES[module_name]
    monkeypatch.setattr(mod, bundle_name, "FELÜLÍRT BUNDLE")
    _install_fake_streamlit(monkeypatch)
    rec = _Recorder()
    mod._call_generate(rec, "PROMPT", tab_label="Fül")
    assert rec.calls[0][1]["system_bundle"] == "FELÜLÍRT BUNDLE"


@pytest.mark.parametrize("module_name", sorted(MODULES))
def test_module_wrapper_only_delegates(module_name):
    bundle_name, _ = MODULES[module_name]
    tree = ast.parse((ROOT / f"{module_name}.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_call_generate")
    assert len(fn.body) == 1 and isinstance(fn.body[0], ast.Return)
    call = fn.body[0].value
    assert isinstance(call.func, ast.Name) and call.func.id == "call_generate_with_session_temperature"
    assert [ast.unparse(a) for a in call.args] == ["generate_fn", "prompt"]
    kw = {k.arg: ast.unparse(k.value) for k in call.keywords}
    assert kw == {"tab_label": "tab_label", "temperature": "temperature", "system_bundle": bundle_name}


def test_bundles_stay_distinct():
    values = {name: getattr(importlib.import_module(name), b) for name, (b, _) in MODULES.items()}
    assert len(set(values.values())) == len(values)
