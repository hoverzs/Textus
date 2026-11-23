"""Regressziós tesztek a 3. stabilizációs munkafázishoz (2026-11-23).

1. A Bibliai szöveg, a diagnosztikai chipek és a munkatérkép CSS-e minden
   Streamlit-futásban kirajzolódik (korábban egy session-flag miatt csak az
   elsőben, így az első újrafuttatás után elveszett).
2. A Bibliai szöveg tipográfiája: ~18 px-es szöveg, lábjegyzetszerű forrás, a
   jogi tájékoztatás szövege változatlan.
3. A PASSAGE_TRACE alapértelmezésben ki van kapcsolva, de bekapcsolható.
4. A sermon_workshop_data elnyelt kivételei naplózódnak, a fallback-értékek
   nem változnak, és a naplóba nem kerül a kivétel üzenete (benne esetleges
   prédikációszöveg vagy kulcs).
"""

from __future__ import annotations

import html
import logging
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def _style_blocks(app: AppTest, marker: str) -> int:
    return sum(1 for m in app.markdown if "<style>" in m.value and marker in m.value)


# ---------------------------------------------------------------- 1. CSS / rerun


def _bible_editor_page() -> None:
    import streamlit as st

    import bible_text_ui

    st.session_state.setdefault("igehely_input", "Jn 3,16")
    st.session_state.setdefault("passage_text", "16. Mert úgy szerette Isten a világot.")
    bible_text_ui.render_bible_text_editor()
    st.button("újrafuttatás", key="phase3_rerun_btn")


def test_bible_text_styles_survive_reruns() -> None:
    app = AppTest.from_function(_bible_editor_page).run()
    assert not app.exception
    assert _style_blocks(app, ".bible-reader") >= 1
    app.button(key="phase3_rerun_btn").click().run()
    assert _style_blocks(app, ".bible-reader") >= 1, "a 2. futásban elveszett a Bibliai szöveg CSS-e"
    app.run()
    assert _style_blocks(app, ".bible-reader") >= 1, "a 3. futásban elveszett a Bibliai szöveg CSS-e"


def _diag_styles_page() -> None:
    import streamlit as st

    import sermon_workshop_ui

    sermon_workshop_ui._ensure_diag_styles()
    st.button("újrafuttatás", key="phase3_diag_rerun_btn")


def test_sermon_workshop_diag_styles_survive_reruns() -> None:
    app = AppTest.from_function(_diag_styles_page, default_timeout=60).run()
    assert not app.exception
    assert _style_blocks(app, ".sw-diag-chip") == 1
    app.button(key="phase3_diag_rerun_btn").click().run()
    assert _style_blocks(app, ".sw-diag-chip") == 1


def _dashboard_styles_page() -> None:
    import streamlit as st

    import diagnostics_dashboard_ui

    diagnostics_dashboard_ui.ensure_dashboard_styles()
    st.button("újrafuttatás", key="phase3_dash_rerun_btn")


def test_dashboard_styles_survive_reruns() -> None:
    app = AppTest.from_function(_dashboard_styles_page).run()
    assert not app.exception
    assert _style_blocks(app, ".tx-wmap-wrap") == 1
    app.button(key="phase3_dash_rerun_btn").click().run()
    assert _style_blocks(app, ".tx-wmap-wrap") == 1


# ---------------------------------------------------------------- 2. tipográfia


def _css_rule(css: str, selector_fragment: str) -> str:
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if selector_fragment in match.group(1):
            return match.group(2)
    raise AssertionError(f"nincs ilyen szabály: {selector_fragment}")


def _rem_to_px(body: str, prop: str) -> float:
    value = re.search(rf"(?<![-\w]){prop}:\s*([\d.]+)rem", body)
    assert value, f"{prop} nem rem-ben megadott"
    return float(value.group(1)) * 16


def test_bible_text_typography_is_readable_and_beats_global_paragraph_rule() -> None:
    import bible_text_ui

    css = bible_text_ui._BIBLE_TEXT_CSS
    for selector in (".bible-reader .bible-verse-text", ".bible-reader .bible-para", ".bible-reader.bible-reader-continuous"):
        body = _css_rule(css, selector)
        assert 18.0 <= _rem_to_px(body, "font-size") <= 19.0, selector
        line_height = float(re.search(r"line-height:\s*([\d.]+)", body).group(1))
        assert 1.55 <= line_height <= 1.75, selector


def test_bible_source_note_is_footnote_sized() -> None:
    import bible_text_ui

    body = _css_rule(bible_text_ui._BIBLE_TEXT_CSS, ".stMarkdown p.bible-source-note")
    assert 12.0 <= _rem_to_px(body, "font-size") <= 13.0


def _source_caption_page() -> None:
    import bible_text_ui

    bible_text_ui.get_bible_text_snapshot = lambda _state: {
        "passage_text": "16. Mert úgy szerette Isten a világot.",
        "passage_text_source": "ruf_2014",
        "passage_text_source_url": "https://szentiras.eu/RUF/Jn3,16",
    }
    bible_text_ui._render_source_caption({})


def test_source_attribution_text_and_link_unchanged() -> None:
    from ruf_bible_service import SOURCE_ATTRIBUTION

    import bible_text_ui

    real_snapshot = bible_text_ui.get_bible_text_snapshot
    try:
        app = AppTest.from_function(_source_caption_page).run()
    finally:
        bible_text_ui.get_bible_text_snapshot = real_snapshot
    notes = [m.value for m in app.markdown if 'class="bible-source-note"' in m.value]
    assert len(notes) == 1
    assert html.escape(SOURCE_ATTRIBUTION, quote=True) in notes[0]
    assert 'href="https://szentiras.eu/RUF/Jn3,16"' in notes[0]


# ---------------------------------------------------------------- 3. PASSAGE_TRACE


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ("0", False), ("", False), ("1", True), ("true", True), ("ON", True)],
)
def test_passage_trace_is_off_by_default_and_switchable(value: str | None, expected: bool) -> None:
    env = {k: v for k, v in os.environ.items() if k != "TEXTUS_PASSAGE_TRACE"}
    if value is not None:
        env["TEXTUS_PASSAGE_TRACE"] = value
    result = subprocess.run(
        [sys.executable, "-c", "import passage_trace; print(passage_trace._ENABLED)"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert result.stdout.strip() == str(expected)


# ---------------------------------------------------------------- 4. naplózás

_SECRET_PAYLOAD = "TELJES PRÉDIKÁCIÓSZÖVEG — api_key=AIzaFAKE-NOT-REAL"


def _assert_logged_without_payload(caplog: pytest.LogCaptureFixture, context: str, exc_name: str) -> None:
    records = [r for r in caplog.records if r.name == "sermon_workshop_data"]
    assert records, "nem keletkezett napló a fallback ágon"
    text = "\n".join(r.getMessage() for r in records)
    assert context in text and exc_name in text
    assert all(r.levelno == logging.WARNING for r in records)
    assert "PRÉDIKÁCIÓ" not in text and "api_key" not in text and "AIza" not in text
    assert all(r.exc_info is None for r in records), "traceback nem kerülhet a naplóba"


def test_schema_version_fallback_unchanged_and_logged(monkeypatch, caplog) -> None:
    import sermon_workshop_data as swd

    monkeypatch.setitem(sys.modules, "sermon_outline_engine", types.ModuleType("sermon_outline_engine"))
    with caplog.at_level(logging.WARNING, logger="sermon_workshop_data"):
        assert swd._canonical_outline_schema_version() == swd._SCHEMA_VERSION_IMPORT_FAILURE_FALLBACK
    _assert_logged_without_payload(caplog, "canonical_outline_schema_version", "ImportError")


def test_context_hash_fallback_unchanged_and_message_not_logged(monkeypatch, caplog) -> None:
    import sermon_workshop_data as swd

    fake = types.ModuleType("sermon_outline_engine")

    def boom(_state):
        raise ValueError(_SECRET_PAYLOAD)

    fake.compute_current_passage_context_hash = boom
    monkeypatch.setitem(sys.modules, "sermon_outline_engine", fake)
    with caplog.at_level(logging.WARNING, logger="sermon_workshop_data"):
        assert swd._current_passage_context_hash({}) == ""
    _assert_logged_without_payload(caplog, "current_passage_context_hash", "ValueError")


def test_lection_analysis_import_fallback_unchanged_and_logged(monkeypatch, caplog) -> None:
    import sermon_workshop_data as swd

    monkeypatch.setitem(sys.modules, "sermon_workshop_lection_link_ai", types.ModuleType("sermon_workshop_lection_link_ai"))
    with caplog.at_level(logging.WARNING, logger="sermon_workshop_data"):
        assert swd._normalize_lection_connection_analysis_field("nem dict") is None
    _assert_logged_without_payload(caplog, "lection_connection_analysis_import", "ImportError")


def test_save_outline_mirror_fallback_unchanged_and_message_not_logged(monkeypatch, caplog) -> None:
    import sermon_workshop_data as swd

    fake = types.ModuleType("sermon_outline_engine")

    def boom(_state, _outline):
        raise RuntimeError(_SECRET_PAYLOAD)

    fake.mirror_outline_to_session_strings = boom
    monkeypatch.setitem(sys.modules, "sermon_outline_engine", fake)
    state: dict = {}
    with caplog.at_level(logging.WARNING, logger="sermon_workshop_data"):
        swd.save_sermon_outline(state, {"content": "I. Bevezetés"})
    # A korábbi fallback változatlan: a kanonikus tartalom a legacy kulcsokra kerül.
    assert state["outline"] == "I. Bevezetés"
    assert state["outline_draft"] == "I. Bevezetés"
    _assert_logged_without_payload(caplog, "save_sermon_outline.mirror_to_session", "RuntimeError")


def test_happy_path_logs_nothing(caplog) -> None:
    import sermon_workshop_data as swd

    with caplog.at_level(logging.WARNING, logger="sermon_workshop_data"):
        swd._canonical_outline_schema_version()
    assert not [r for r in caplog.records if r.name == "sermon_workshop_data"]
