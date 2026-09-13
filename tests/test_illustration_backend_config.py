"""TEXTUS_ILLUSTRATION_BACKEND resolution — see illustration_engine/
backend_config.py's own docstring for the full rationale (deliberately
diverges from bible_engine.greek_analysis_repository's soft-warning
precedent: hard-fails in a cloud environment instead of silently falling
back to local, because that silent fallback is exactly the traced root
cause of the 2026-09 "every illustration search returns 0 results in
production" incident)."""

from __future__ import annotations

import pytest

from illustration_engine.backend_config import (
    IllustrationBackendConfigurationError,
    resolve_illustration_backend,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("TEXTUS_ILLUSTRATION_BACKEND", "STREAMLIT_RUNTIME_ENVIRONMENT", "TEXTUS_FORCE_CLOUD"):
        monkeypatch.delenv(var, raising=False)


def test_defaults_to_local_when_unset_and_not_cloud(monkeypatch) -> None:
    assert resolve_illustration_backend() == "local"


def test_defaults_to_local_on_unrecognized_value_when_not_cloud(monkeypatch) -> None:
    monkeypatch.setenv("TEXTUS_ILLUSTRATION_BACKEND", "postgres")
    assert resolve_illustration_backend() == "local"


def test_explicit_supabase_honored_locally(monkeypatch) -> None:
    monkeypatch.setenv("TEXTUS_ILLUSTRATION_BACKEND", "supabase")
    assert resolve_illustration_backend() == "supabase"


def test_explicit_local_honored_locally(monkeypatch) -> None:
    monkeypatch.setenv("TEXTUS_ILLUSTRATION_BACKEND", "local")
    assert resolve_illustration_backend() == "local"


def test_cloud_without_explicit_supabase_hard_fails(monkeypatch) -> None:
    """The core regression this module exists to prevent: a cloud
    deployment with no (or the wrong) backend configured must NEVER
    silently resolve to "local" -- that is exactly how production ended
    up querying an empty, auto-created SQLite file for every search."""
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    with pytest.raises(IllustrationBackendConfigurationError):
        resolve_illustration_backend()


def test_cloud_with_unset_backend_hard_fails(monkeypatch) -> None:
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    monkeypatch.delenv("TEXTUS_ILLUSTRATION_BACKEND", raising=False)
    with pytest.raises(IllustrationBackendConfigurationError):
        resolve_illustration_backend()


def test_cloud_with_local_explicitly_set_still_hard_fails(monkeypatch) -> None:
    """Even an EXPLICIT 'local' in a cloud environment must fail -- the
    rule is "must be supabase in the cloud," not "must be non-empty."""
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    monkeypatch.setenv("TEXTUS_ILLUSTRATION_BACKEND", "local")
    with pytest.raises(IllustrationBackendConfigurationError):
        resolve_illustration_backend()


def test_cloud_with_explicit_supabase_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    monkeypatch.setenv("TEXTUS_ILLUSTRATION_BACKEND", "supabase")
    assert resolve_illustration_backend() == "supabase"


def test_force_cloud_override_also_triggers_hard_fail(monkeypatch) -> None:
    monkeypatch.setenv("TEXTUS_FORCE_CLOUD", "true")
    with pytest.raises(IllustrationBackendConfigurationError):
        resolve_illustration_backend()


def test_configuration_error_is_not_a_retrieval_diagnostics_reason() -> None:
    """Structural guarantee: this exception type must stay independent
    of illustration_engine.retrieval's REASON_* constants -- a caller
    must never be able to accidentally treat a deployment
    misconfiguration as "the search ran and found nothing"."""
    from illustration_engine import retrieval

    reason_values = {
        getattr(retrieval, name)
        for name in dir(retrieval)
        if name.startswith("REASON_")
    }
    assert IllustrationBackendConfigurationError.__name__ not in reason_values
