"""2026-09 memory hotfix — inactive heavy quick-tool bodies must not execute.

Production problem: Streamlit Cloud reached its 3 GB memory limit because a
full rerun executed ALL 12 quick-tool bodies, including
* Kommentárok — whose body calls ``commentary_runtime.ensure_status()`` (a
  whole-file commentary DB download) before it even checks for a passage, and
* the Greek/Hebrew analysis, rendered once in Igehely AND again in
  Eredeti szöveg on every run.

Fix under test: ``st.tabs(..., on_change="rerun")`` exposes ``.open``; the
Kommentárok and Eredeti szöveg bodies run only when their tab is open, and the
Igehely tab skips its heavy analysis / map / search expanders when it is not
open (its passage input always renders, so the typed passage is never lost).

No test performs a real AI / network call; the commentary status seam is a spy.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_PATH = ROOT / "app.py"

from workshop_nav_ui import (  # noqa: E402
    QUICK_TOOLS_ACTIVE_TAB_KEY,
    QUICK_TOOLS_TAB_LABELS,
)

IGEHELY, ORIGINAL, COMMENTARY = 0, 1, 2


@pytest.fixture
def commentary_spy(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Spy on the commentary runtime seam (the heavy, download-triggering call)."""
    import commentary_ui
    from textus_kb import commentary_runtime

    calls: list[int] = []

    def fake_status():
        calls.append(1)
        return commentary_runtime.CommentaryRuntimeStatus(
            available=False, reason="test_spy", database_path="", detail=""
        )

    monkeypatch.setattr(commentary_ui, "_get_status", fake_status)
    return calls


@pytest.fixture
def greek_block_counter(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every entry into the Greek analysis block (via the trace seam)."""
    import passage_trace

    entered: list[str] = []
    real_emit = passage_trace.emit

    def recording_emit(message: str) -> None:
        if message == "entering: greek_analysis_block":
            entered.append(message)
        real_emit(message)

    monkeypatch.setattr(passage_trace, "emit", recording_emit)
    return entered


def _app_with_passage(passage: str = "Jn 3,16") -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    at.text_input(key="igehely_input").input(passage).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _open_tab(at: AppTest, index: int) -> None:
    at.session_state[QUICK_TOOLS_ACTIVE_TAB_KEY] = QUICK_TOOLS_TAB_LABELS[index]
    at.run()
    assert not at.exception, [e.value for e in at.exception]


# --- the actual regression: nothing heavy runs on ordinary reruns -------------


def test_initial_load_does_not_run_the_commentary_body(commentary_spy):
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert commentary_spy == []


def test_committing_a_passage_does_not_run_the_commentary_body(commentary_spy):
    _app_with_passage()
    assert commentary_spy == [], "commentary provisioning ran on a passage commit"


def test_commentary_body_runs_only_when_its_tab_is_open(commentary_spy):
    at = _app_with_passage()
    assert commentary_spy == []
    _open_tab(at, COMMENTARY)
    assert commentary_spy, "the open Kommentárok tab must still run its body"
    ran = len(commentary_spy)
    _open_tab(at, IGEHELY)
    assert len(commentary_spy) == ran, "commentary body ran while another tab was open"


def test_greek_analysis_renders_once_per_run_never_twice(greek_block_counter):
    at = _app_with_passage()

    greek_block_counter.clear()
    at.run()  # Igehely open (default)
    igehely_open = len(greek_block_counter)

    greek_block_counter.clear()
    _open_tab(at, ORIGINAL)
    original_open = len(greek_block_counter)

    assert igehely_open == 1, igehely_open
    assert original_open == 1, original_open  # previously 2 (Igehely + Eredeti szöveg)


def test_original_text_tab_still_renders_its_content_when_open(commentary_spy):
    at = _app_with_passage()
    _open_tab(at, ORIGINAL)
    rendered = "\n".join(m.value for m in at.markdown)
    assert "Jn 3,16" in rendered  # the passage line of the Eredeti szöveg body


def test_passage_input_survives_switching_away_and_back(commentary_spy):
    at = _app_with_passage("Jn 3,16")
    _open_tab(at, COMMENTARY)
    _open_tab(at, IGEHELY)
    assert at.text_input(key="igehely_input").value == "Jn 3,16"


# --- helper + wiring ---------------------------------------------------------------


def test_quick_tab_open_is_fail_open():
    import app

    class Tab:
        def __init__(self, open_value):
            self.open = open_value

    class Broken:
        @property
        def open(self):
            raise RuntimeError("boom")

    assert app._quick_tab_open([Tab(True)], 0) is True
    assert app._quick_tab_open([Tab(False)], 0) is False
    assert app._quick_tab_open([Tab(None)], 0) is True  # tracking unavailable -> old behaviour
    assert app._quick_tab_open([Broken()], 0) is True
    assert app._quick_tab_open([], 0) is True  # IndexError -> old behaviour


def test_quick_tools_tabs_track_the_open_state():
    from workshop_nav_ui import render_quick_tools_tabs

    assert 'on_change="rerun"' in inspect.getsource(render_quick_tools_tabs)


def test_only_the_intended_bodies_are_gated():
    src = APP_PATH.read_text(encoding="utf-8")
    assert src.count("_quick_tab_open(tabs,") == 3  # Igehely (arg), Original, Commentary
    for other in ("exegesis", "history", "theology", "actualization"):
        assert f'key="{other}"' in src  # untouched section tabs still render unconditionally
