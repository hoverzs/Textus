"""Phase 2D.2 §15/§17 — ``get_default_hebrew_analysis_repository()`` backend
selection.

Env-var only (``TEXTUS_HEBREW_ANALYSIS_BACKEND``), deliberately without a
Streamlit-secrets fallback — see that function's docstring in
``bible_engine.hebrew_analysis_repository`` for why. No network access
anywhere in this file; ``"supabase"`` selection is checked by TYPE only
(never actually calling out).
"""

from __future__ import annotations

import pytest

from bible_engine.hebrew_analysis_repository import (
    HEBREW_ANALYSIS_BACKEND_ENV_VAR,
    LocalHebrewAnalysisRepository,
    SupabaseHebrewAnalysisRepository,
    get_default_hebrew_analysis_repository,
)


def test_default_backend_is_local_when_env_var_unset(monkeypatch):
    monkeypatch.delenv(HEBREW_ANALYSIS_BACKEND_ENV_VAR, raising=False)
    assert isinstance(get_default_hebrew_analysis_repository(), LocalHebrewAnalysisRepository)


@pytest.mark.parametrize("value", ["", "  ", "unknown", "local", "LOCAL"])
def test_unrecognized_or_local_values_select_local(monkeypatch, value):
    monkeypatch.setenv(HEBREW_ANALYSIS_BACKEND_ENV_VAR, value)
    assert isinstance(get_default_hebrew_analysis_repository(), LocalHebrewAnalysisRepository)


@pytest.mark.parametrize("value", ["supabase", "SUPABASE", " Supabase "])
def test_supabase_value_selects_supabase_repository_case_and_whitespace_insensitive(monkeypatch, value):
    monkeypatch.setenv(HEBREW_ANALYSIS_BACKEND_ENV_VAR, value)
    assert isinstance(get_default_hebrew_analysis_repository(), SupabaseHebrewAnalysisRepository)


def test_local_store_path_override_is_honored_regardless_of_backend_env(monkeypatch, tmp_path):
    monkeypatch.delenv(HEBREW_ANALYSIS_BACKEND_ENV_VAR, raising=False)
    custom_path = tmp_path / "custom.sqlite3"
    repository = get_default_hebrew_analysis_repository(local_store_path=custom_path)
    assert isinstance(repository, LocalHebrewAnalysisRepository)
    assert repository.database_path == custom_path
