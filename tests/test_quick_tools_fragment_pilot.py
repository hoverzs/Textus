"""Checkpoint 3 pilot — Énekajánló + Teológia run inside keyed ``st.fragment``s.

Goal being protected: a long-running AI action in these two modules must not
trigger an app-scope ``st.rerun()`` (the mechanism that dimmed / ghosted the
whole page, header and Gyorseszközök selector included).

What these tests can and cannot prove
-------------------------------------
``AppTest`` always starts a widget interaction as a FULL script run — it cannot
scope a click to a single fragment. So here we prove, against the real
``app.py``:

* generation works and every piece of underlying state is correct (result,
  status, freshness hash, running flag, project fingerprint);
* which ``st.rerun`` scopes are requested: none for Énekajánló; only
  ``scope="fragment"`` for the Teológia pilot; the app-scope rerun is
  deliberately PRESERVED for the not-yet-migrated modules;
* the two keys really are registered keyed fragments (and nothing else is).

The runtime half — a fragment-only interaction leaves the full-script counter
untouched and does not rerun sibling fragments — was measured in a real
browser session against a live server (see the Checkpoint 3 report); it cannot
be expressed in AppTest.

No test performs a real AI / network call: the Gemini entry points are stubbed.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
import streamlit as st
from streamlit.errors import StreamlitAPIException
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_PATH = ROOT / "app.py"
APP_SRC = APP_PATH.read_text(encoding="utf-8")

THEOLOGY_TEXT = "Teológiai elemzés (próba)."
SONGS_MD = "### Ajánlott énekek (próba)\n\n1. Teszt ének"


@pytest.fixture
def rerun_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every ``st.rerun`` scope requested by the app, then delegate."""
    # Streamlit's own function, NOT ``st.rerun`` as found at fixture time:
    # other tests in the suite leave a scope-less fake ``st.rerun`` behind.
    from streamlit.commands.execution_control import rerun as original

    calls: list[str] = []

    def recording_rerun(scope="app"):
        calls.append(str(scope))
        return original(scope=scope)

    monkeypatch.setattr(st, "rerun", recording_rerun)
    return calls


@pytest.fixture
def stubbed_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub every Gemini entry point the two pilot modules reach."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    import hymn_recommendation_ai as hr
    import textus_kb.shadow_integration as si

    monkeypatch.setattr(
        hr,
        "recommend_hymns",
        lambda **kw: types.SimpleNamespace(markdown=SONGS_MD, status="ok"),
    )
    monkeypatch.setattr(
        si,
        "run_production_with_optional_shadow",
        lambda **kw: si.SectionRunResult(
            production_output=THEOLOGY_TEXT,
            generation_duration_ms=1,
            shadow_event=None,
        ),
    )


def _fresh_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _fingerprint(at: AppTest) -> str:
    from workspace_data import project_content_fingerprint

    return project_content_fingerprint(
        {k: at.session_state[k] for k in at.session_state}
    )


# --- Énekajánló --------------------------------------------------------------


def test_songs_generation_requests_no_rerun_and_updates_state(stubbed_ai, rerun_calls):
    at = _fresh_app()
    before = _fingerprint(at)
    at.text_input(key="songs_verse").input("Jn 3,16").run()
    rerun_calls.clear()

    at.button(key="songs_run").click().run()

    assert not at.exception, [e.value for e in at.exception]
    assert rerun_calls == [], "Énekajánló generation must not call st.rerun at all"
    assert at.session_state["songs"] == SONGS_MD
    assert at.session_state["_songs_repository_status"] == "ok"
    assert at.session_state["_songs_running"] is False
    assert _fingerprint(at) != before, "project must become dirty after generation"
    # The generated result is rendered in the SAME run, right below the button.
    assert any("Ajánlott énekek (próba)" in m.value for m in at.markdown)


def test_songs_blocked_validation_still_warns_and_does_not_generate(stubbed_ai, rerun_calls):
    at = _fresh_app()
    at.text_input(key="songs_verse").input("").run()
    rerun_calls.clear()

    at.button(key="songs_run").click().run()

    assert rerun_calls == []
    assert not at.session_state["songs"]
    assert any("Add meg az igeszakaszt" in w.value for w in at.warning)


# --- Teológia (representative render_section_tab module) --------------------


def test_theology_generation_uses_only_fragment_scope_and_updates_state(
    stubbed_ai, rerun_calls
):
    at = _fresh_app()
    at.text_input(key="igehely_input").input("Jn 3,16").run()
    before = _fingerprint(at)
    rerun_calls.clear()

    at.button(key="theology_generate_btn").click().run()

    assert not at.exception, [e.value for e in at.exception]
    assert rerun_calls, "the pilot still needs its own fragment-scope refresh"
    assert set(rerun_calls) == {"fragment"}, rerun_calls  # never an app-scope rerun
    assert at.session_state["theology"] == THEOLOGY_TEXT
    assert at.session_state["theology_status"] == "draft"
    assert at.session_state["theology_approved_context_hash"]
    assert at.session_state["_theology_running"] is False
    assert _fingerprint(at) != before
    # Result visible even though AppTest cannot deliver the fragment rerun
    # (the fallback in _rerun_current_fragment swallows the API exception).
    assert any("Teológiai elemzés (próba)" in m.value for m in at.markdown)


def test_non_pilot_section_still_uses_the_app_scope_rerun(stubbed_ai, rerun_calls):
    """Deliberately preserved: only the pilot module lost its app-scope rerun."""
    at = _fresh_app()
    at.text_input(key="igehely_input").input("Jn 3,16").run()
    rerun_calls.clear()

    at.button(key="history_generate_btn").click().run()

    assert not at.exception, [e.value for e in at.exception]
    assert "app" in rerun_calls
    assert at.session_state["history"] == THEOLOGY_TEXT


# --- structure -----------------------------------------------------------------


def test_only_the_two_pilot_fragments_are_registered_by_key(stubbed_ai):
    at = _fresh_app()
    storage = at._fragment_storage
    assert storage.resolve_target("qt_songs")
    assert storage.resolve_target("qt_section_theology")
    assert storage.resolve_target(["qt_songs", "qt_section_theology"])
    for other in ("exegesis", "history", "actualization"):
        with pytest.raises(StreamlitAPIException):
            storage.resolve_target(f"qt_section_{other}")


def test_pilot_scope_guard_only_theology_opts_in():
    assert APP_SRC.count("isolate_fragment=True") == 1
    start = APP_SRC.index('key="theology",')
    assert "isolate_fragment=True" in APP_SRC[start : start + 600]


def test_songs_fragment_body_has_no_rerun_call():
    import ast
    import inspect
    import textwrap

    import app

    tree = ast.parse(textwrap.dedent(inspect.getsource(app._render_songs_panel)))
    rerun_calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "rerun"
    ]
    assert rerun_calls == []


def test_songs_fragment_still_owns_the_module_header():
    """Moved here from the tabs[8] source-marker test (the body left the
    ``with tabs[8]:`` block when it became a fragment)."""
    import inspect

    import app

    assert 'st.header("Énekajánló")' in inspect.getsource(app._render_songs_panel)


# --- helper --------------------------------------------------------------------


def test_rerun_current_fragment_swallows_only_the_api_exception():
    import app as app_mod
    from unittest.mock import patch

    with patch.object(app_mod, "st") as st_mock:
        st_mock.rerun.side_effect = StreamlitAPIException("not in a fragment rerun")
        app_mod._rerun_current_fragment()  # must not raise
        st_mock.rerun.assert_called_once_with(scope="fragment")

    with patch.object(app_mod, "st") as st_mock:
        st_mock.rerun.side_effect = RuntimeError("unrelated bug")
        with pytest.raises(RuntimeError):
            app_mod._rerun_current_fragment()
