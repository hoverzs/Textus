"""2026-09 audit fix — production-fallback visibility for
``get_default_greek_analysis_repository()``.

Mirrors ``tests/test_hebrew_analysis_backend_selection.py``: an unset/
unrecognized ``TEXTUS_GREEK_ANALYSIS_BACKEND`` silently serves the bundled
local dataset instead of the Supabase-backed one — harmless in local dev
(no cloud signal), but a real deployment that forgot to set the env var
previously got zero indication anything was wrong. This adds a runtime
warning log, ONLY when a detected-cloud environment also resolves to
"local" — local development stays completely silent. No network access
anywhere in this file; "supabase" selection is checked by TYPE only
(never actually calling out).
"""

from __future__ import annotations

import pytest

from bible_engine.greek_analysis_repository import (
    LocalGreekAnalysisRepository,
    SupabaseGreekAnalysisRepository,
    get_default_greek_analysis_repository,
)

BACKEND_ENV_VAR = "TEXTUS_GREEK_ANALYSIS_BACKEND"


def test_default_backend_is_local_when_env_var_unset(monkeypatch):
    monkeypatch.delenv(BACKEND_ENV_VAR, raising=False)
    assert isinstance(get_default_greek_analysis_repository(), LocalGreekAnalysisRepository)


@pytest.mark.parametrize("value", ["supabase", "SUPABASE", " Supabase "])
def test_supabase_value_selects_supabase_repository(monkeypatch, value):
    monkeypatch.setenv(BACKEND_ENV_VAR, value)
    assert isinstance(get_default_greek_analysis_repository(), SupabaseGreekAnalysisRepository)


def test_local_fallback_in_cloud_environment_logs_a_warning(monkeypatch, caplog):
    monkeypatch.delenv(BACKEND_ENV_VAR, raising=False)
    monkeypatch.setenv("TEXTUS_FORCE_CLOUD", "1")
    with caplog.at_level("WARNING", logger="bible_engine.greek_analysis_repository"):
        repo = get_default_greek_analysis_repository()
    assert isinstance(repo, LocalGreekAnalysisRepository)
    assert any("TEXTUS_GREEK_ANALYSIS_BACKEND" in r.message for r in caplog.records)


def test_local_fallback_in_local_dev_does_not_log_a_warning(monkeypatch, caplog):
    monkeypatch.delenv(BACKEND_ENV_VAR, raising=False)
    monkeypatch.delenv("TEXTUS_FORCE_CLOUD", raising=False)
    monkeypatch.delenv("STREAMLIT_RUNTIME_ENVIRONMENT", raising=False)
    with caplog.at_level("WARNING", logger="bible_engine.greek_analysis_repository"):
        repo = get_default_greek_analysis_repository()
    assert isinstance(repo, LocalGreekAnalysisRepository)
    assert caplog.records == []


def test_explicit_supabase_backend_in_cloud_does_not_log_a_warning(monkeypatch, caplog):
    monkeypatch.setenv(BACKEND_ENV_VAR, "supabase")
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    with caplog.at_level("WARNING", logger="bible_engine.greek_analysis_repository"):
        repo = get_default_greek_analysis_repository()
    assert isinstance(repo, SupabaseGreekAnalysisRepository)
    assert caplog.records == []
