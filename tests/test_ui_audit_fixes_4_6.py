"""UI/UX-audit (2026-11-23) — az elfogadott javítási terv 4–6. pontja.

4. Fejlesztői üzenetek és beállítások: a kommentárfül nem ad buildparancsot,
   a vendégsáv és a Fiók rész nem ad konfigurációs utasítást a felhasználói
   felületen (csak helyi fejlesztői futtatáskor), a technikai beállítások
   (alapprompt, cache, debugnapló) külön haladó részbe kerülnek.
5. Feliratok: nyers Markdown a modellmezőben, MI/AI-terminológia, a
   „Tabonkénti generálás / Áttekintés” utalás, „Beállítások fülön”, a kézi
   beillesztés „RÚF 2014” jelölése, a vendégmunka tárolási tájékoztatója.
6. Kontraszt: „Bibliai térkép” lenyitó és „Visszajelzés küldése” gomb.

Valódi MI- vagy hálózati hívás nincs; a kommentár-adatbázis állapota kém.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_PATH = ROOT / "app.py"
APP_SRC = APP_PATH.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_commentary_download(monkeypatch: pytest.MonkeyPatch) -> None:
    import commentary_ui
    from textus_kb import commentary_runtime

    monkeypatch.setattr(
        commentary_ui,
        "_get_status",
        lambda: commentary_runtime.CommentaryRuntimeStatus(
            available=False, reason="storage_not_configured", database_path="", detail=""
        ),
    )


def _ok(at: AppTest) -> AppTest:
    assert not at.exception, [e.value for e in at.exception]
    return at


def _app(monkeypatch: pytest.MonkeyPatch, *, local: bool) -> AppTest:
    import auth_config

    monkeypatch.setattr(auth_config, "is_local_runtime", lambda **_: local)
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    return _ok(at.run())


def _all_text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [i.value for i in at.info] + [w.value for w in at.warning]
    return "\n".join(str(p) for p in parts)


def _settings(at: AppTest) -> AppTest:
    at.session_state["shell_panel"] = "settings"
    return _ok(at.run())


# --- 4. Fejlesztői üzenetek --------------------------------------------------


def _render_missing_db_app() -> None:
    import commentary_ui
    from textus_kb import commentary_runtime

    commentary_ui._render_missing_db(
        commentary_runtime.CommentaryRuntimeStatus(
            available=False, reason="storage_not_configured", database_path="", detail=""
        )
    )


@pytest.mark.parametrize("local", [False, True])
def test_commentary_unavailable_message_is_plain_for_users(monkeypatch, local):
    import commentary_ui

    monkeypatch.setattr(commentary_ui, "_is_developer_environment", lambda: local)
    at = _ok(AppTest.from_function(_render_missing_db_app).run())
    text = _all_text(at)
    assert "A kommentárgyűjtemény most nem érhető el" in text
    assert ("build_commentary_database.py" in text) is local
    assert ("Commentary adatbázis" in text) is local


def test_commentary_developer_check_is_fail_closed(monkeypatch):
    import auth_config
    import commentary_ui

    def boom(**_):
        raise RuntimeError("nincs kérés")

    monkeypatch.setattr(auth_config, "is_local_runtime", boom)
    assert commentary_ui._is_developer_environment() is False


@pytest.mark.parametrize("local", [False, True])
def test_guest_strip_config_hint_only_in_developer_runtime(monkeypatch, local):
    at = _app(monkeypatch, local=local)
    assert ("Streamlit Secrets" in _all_text(at)) is local


@pytest.mark.parametrize("local", [False, True])
def test_account_section_hides_oauth_instructions_from_users(monkeypatch, local):
    at = _settings(_app(monkeypatch, local=local))
    text = _all_text(at)
    assert "A bejelentkezés ezen a példányon nem érhető el." in text
    for dev_word in ("client_secret", "redirect_uri", "cookie_secret"):
        assert (dev_word in text) is local, dev_word


def test_technical_settings_are_in_a_closed_advanced_section(monkeypatch):
    at = _settings(_app(monkeypatch, local=False))
    labels = [e.label for e in at.expander]
    buttons = [b.label for b in at.button]
    assert "Aktív közös alap prompt" not in labels
    assert not any(label.startswith("Gemini debug log") for label in labels)
    assert "Cache törlése" not in buttons
    assert "API kapcsolat tesztelése" in buttons  # felhasználói ellenőrzés: látható marad
    assert at.toggle(key="settings_show_advanced").value is False

    at.toggle(key="settings_show_advanced").set_value(True).run()
    _ok(at)
    labels = [e.label for e in at.expander]
    assert "Aktív közös alap prompt" in labels
    assert any(label.startswith("Gemini debug log") for label in labels)
    assert "Cache törlése" in [b.label for b in at.button]
    assert at.checkbox(key="enable_cache").value is True


def test_cache_setting_survives_closing_advanced_and_leaving_settings(monkeypatch):
    at = _settings(_app(monkeypatch, local=False))
    at.toggle(key="settings_show_advanced").set_value(True).run()
    at.checkbox(key="enable_cache").uncheck().run()
    _ok(at)
    at.toggle(key="settings_show_advanced").set_value(False).run()
    _ok(at.run())
    assert at.session_state["enable_cache"] is False
    at.session_state["shell_panel"] = None
    _ok(at.run())
    _ok(at.run())
    assert at.session_state["enable_cache"] is False
    _settings(at)
    at.toggle(key="settings_show_advanced").set_value(True).run()
    _ok(at)
    assert at.checkbox(key="enable_cache").value is False
    assert not [w for w in at.warning if "Session State" in str(w.value)]


# --- 5. Feliratok ----------------------------------------------------------------


def test_model_row_is_html_not_raw_markdown(monkeypatch):
    at = _settings(_app(monkeypatch, local=False))
    rows = [m.value for m in at.markdown if '<div class="locked-model-row">' in str(m.value)]
    assert len(rows) == 1
    row = rows[0]
    assert "**" not in row and "`" not in row
    assert "<strong>Gemini 2.5 Flash</strong>" in row
    assert "<code>gemini-2.5-flash</code>" in row


def test_model_summary_html_escapes_and_joins():
    import importlib

    # A segédfüggvény önálló, ezért a forrásból kiemelve is ellenőrizhető.
    tree = ast.parse(APP_SRC)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_model_summary_html")
    ns: dict = {"html": importlib.import_module("html")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "app.py", "exec"), ns)
    out = ns["_model_summary_html"]([("A<b>", "x&y"), ("B", "")], prefix="P ", suffix=" S")
    assert out == "P <strong>A&lt;b&gt;</strong> (<code>x&amp;y</code>) vagy <strong>B</strong> S"


def _ui_string_constants(path: Path) -> list[str]:
    """A modul string-konstansai, a docstringek nélkül."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                docstrings.add(id(node.body[0].value))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
    ]


@pytest.mark.parametrize(
    "rel_path",
    [
        "workshop_nav_ui.py",
        "commentary_ui.py",
        "commentary_compare.py",
        "commentary_translation_service.py",
        "sermon_workshop_ui.py",
        "illustration_retrieval_ui.py",
        "bible_engine/greek_contextual_analysis_ui.py",
        "hebrew_text_demo.py",
        "hymn_recommendation_ai.py",
        "sermon_outline_engine.py",
    ],
)
def test_user_facing_strings_use_mi_not_ai(rel_path):
    import re

    pattern = re.compile(r"\bAI(-|\b)(?! Studio)")
    offenders = [s for s in _ui_string_constants(ROOT / rel_path) if pattern.search(s)]
    assert offenders == [], offenders


def test_step_labels_use_mi():
    from workshop_nav_ui import _STEP_STATE_LABEL

    assert _STEP_STATE_LABEL["ai_suggested"] == "MI-javaslat elkészült"
    assert _STEP_STATE_LABEL["ai_ready"] == "MI által kidolgozható"


def test_summary_info_panel_names_the_real_button():
    strings = _ui_string_constants(APP_PATH)
    assert not any("Tabonkénti" in s for s in strings)
    assert not any("Áttekintést" in s for s in strings)
    assert "Bibliai háttér összegzése" in strings


def test_no_beallitasok_ful_wording_in_ui_strings():
    offenders = [s for s in _ui_string_constants(APP_PATH) if "Beállítások fül" in s or "Beállítások</strong> fül" in s]
    assert offenders == [], offenders


def test_guest_projects_text_does_not_promise_persistence():
    strings = _ui_string_constants(APP_PATH)
    assert not any("böngészőben marad" in s for s in strings)
    assert any("csak ebben a munkamenetben él" in s for s in strings)


def _snap(source: str, text: str = "16 Mert úgy szerette Isten a világot.") -> dict:
    return {
        "passage_text_source": source,
        "passage_text": text,
        "bible_translation": "RÚF 2014",
    }


def test_manual_text_is_not_labelled_as_ruf_translation():
    from bible_text_ui import SOURCE_TYPE_USER_OVERRIDE, _passage_header_markdown

    manual = _passage_header_markdown("Jn 3,16", _snap(SOURCE_TYPE_USER_OVERRIDE))
    assert "RÚF" not in manual
    assert "**Forrás:** kézi beillesztés" in manual

    ruf = _passage_header_markdown("Jn 3,16", _snap("external_api"))
    assert ruf == "**Igehely:** Jn 3,16  ·  **Fordítás:** RÚF 2014"

    # üres kézi szövegnél nincs mit „kézi beillesztésnek” nevezni
    empty_manual = _passage_header_markdown("Jn 3,16", _snap(SOURCE_TYPE_USER_OVERRIDE, text=""))
    assert "**Fordítás:** RÚF 2014" in empty_manual


def _preview_with_manual_text() -> None:
    import streamlit as st

    import bible_text_ui

    st.session_state["last_igehely"] = "Jn 3,16"
    st.session_state["passage_text"] = "16 Mert úgy szerette Isten a világot."
    st.session_state["passage_text_source"] = bible_text_ui.SOURCE_TYPE_USER_OVERRIDE
    st.session_state["bible_translation"] = "RÚF 2014"  # a tárolt adat nem változik
    bible_text_ui.render_bible_text_preview(expanded=True)


def test_preview_shows_manual_source_and_keeps_stored_translation():
    at = _ok(AppTest.from_function(_preview_with_manual_text).run())
    text = _all_text(at)
    assert "**Forrás:** kézi beillesztés" in text
    assert "**Fordítás:** RÚF 2014" not in text
    assert at.session_state["bible_translation"] == "RÚF 2014"


# --- 6. Kontraszt ------------------------------------------------------------------


def test_map_expander_header_is_white_and_content_stays_dark():
    src = (ROOT / "biblical_map_ui.py").read_text(encoding="utf-8")
    header_rule = src[src.index(".st-key-biblical_map_cta [data-testid=\"stExpander\"] summary span,"):]
    header_rule = header_rule[: header_rule.index("}")]
    assert "color: #ffffff !important" in header_rule
    # a lenyitó tartalmának sötét szövegszíne megmarad (világos háttér)
    assert 'color: #2a2117 !important' in src


def test_feedback_submit_button_text_is_white():
    rule_start = APP_SRC.index('[data-testid="stForm"] button[kind="primaryFormSubmit"] p,')
    rule = APP_SRC[rule_start: APP_SRC.index("}}", rule_start)]
    assert "color: #ffffff !important" in rule
