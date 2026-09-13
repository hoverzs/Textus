"""2026-09 runtime retrieval cutover -- illustration_retrieval_ui.py's
backend resolution (`_resolve_data_source`) and the error-vs-empty
distinction (`_is_candidate_fetch_error`). No Streamlit AppTest needed:
both are plain Python functions, no `st.*` calls inside them (the
`@st.cache_resource`-decorated `_get_connection`/`_get_supabase_
repository` are themselves monkeypatched out in every test here, so no
real SQLite file or Supabase client is ever touched)."""

from __future__ import annotations

import pytest

import illustration_retrieval_ui as ui
from illustration_engine.backend_config import IllustrationBackendConfigurationError
from illustration_engine.retrieval import RetrievalDiagnostics, RetrievalIntent


@pytest.fixture(autouse=True)
def _clean_backend_env(monkeypatch):
    for var in ("TEXTUS_ILLUSTRATION_BACKEND", "STREAMLIT_RUNTIME_ENVIRONMENT", "TEXTUS_FORCE_CLOUD"):
        monkeypatch.delenv(var, raising=False)


class _Sentinel:
    """Distinguishable stand-in object -- identity-checked (`is`), never
    a real sqlite3.Connection or Supabase client."""


# ---------------------------------------------------------------------------
# _resolve_data_source -- local backend
# ---------------------------------------------------------------------------


def test_local_backend_still_works_and_uses_sqlite_connection(monkeypatch) -> None:
    """No TEXTUS_ILLUSTRATION_BACKEND set, not a cloud environment ->
    resolves to "local" -> _get_connection() is used, NOT the Supabase
    repository."""
    sqlite_sentinel = _Sentinel()
    monkeypatch.setattr(ui, "_get_connection", lambda: sqlite_sentinel)
    monkeypatch.setattr(
        ui, "_get_supabase_repository",
        lambda: (_ for _ in ()).throw(AssertionError("must not construct a Supabase repository for local backend")),
    )
    monkeypatch.setattr(ui, "_current_mode", lambda: "production")

    connection, mode = ui._resolve_data_source()

    assert connection is sqlite_sentinel
    assert mode == "production"


def test_local_backend_preserves_loopback_dev_mode_detection(monkeypatch) -> None:
    sqlite_sentinel = _Sentinel()
    monkeypatch.setattr(ui, "_get_connection", lambda: sqlite_sentinel)
    monkeypatch.setattr(ui, "_current_mode", lambda: "development")

    connection, mode = ui._resolve_data_source()

    assert mode == "development"


# ---------------------------------------------------------------------------
# _resolve_data_source -- supabase backend
# ---------------------------------------------------------------------------


def test_supabase_backend_uses_repository_and_forces_production_mode(monkeypatch) -> None:
    supabase_sentinel = _Sentinel()
    monkeypatch.setenv("TEXTUS_ILLUSTRATION_BACKEND", "supabase")
    monkeypatch.setattr(ui, "_get_supabase_repository", lambda: supabase_sentinel)
    monkeypatch.setattr(
        ui, "_get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("SQLite must never open when backend=supabase")),
    )
    # Even if this host WOULD be detected as loopback/dev, Supabase has no
    # dev-mode RPC -- mode must still be forced to production.
    monkeypatch.setattr(ui, "_current_mode", lambda: "development")

    connection, mode = ui._resolve_data_source()

    assert connection is supabase_sentinel
    assert mode == "production"


def test_sqlite_never_opens_in_supabase_mode(monkeypatch) -> None:
    """Direct regression test for the exact requirement: SQLITE_FALLBACK_
    IN_PRODUCTION must be false. _get_connection (which calls
    sqlite3.connect(DEFAULT_DATABASE_PATH)) must never be invoked at all
    when the resolved backend is supabase."""
    monkeypatch.setenv("TEXTUS_ILLUSTRATION_BACKEND", "supabase")
    calls = {"sqlite_opened": False}

    def _explode():
        calls["sqlite_opened"] = True
        raise AssertionError("must not happen")

    monkeypatch.setattr(ui, "_get_connection", _explode)
    monkeypatch.setattr(ui, "_get_supabase_repository", lambda: _Sentinel())

    ui._resolve_data_source()

    assert calls["sqlite_opened"] is False


# ---------------------------------------------------------------------------
# _resolve_data_source -- cloud fail-closed propagation
# ---------------------------------------------------------------------------


def test_cloud_missing_config_fail_closed_propagates(monkeypatch) -> None:
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    with pytest.raises(IllustrationBackendConfigurationError):
        ui._resolve_data_source()


def test_cloud_local_fail_closed_propagates(monkeypatch) -> None:
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    monkeypatch.setenv("TEXTUS_ILLUSTRATION_BACKEND", "local")
    with pytest.raises(IllustrationBackendConfigurationError):
        ui._resolve_data_source()


def test_cloud_supabase_explicit_works(monkeypatch) -> None:
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    monkeypatch.setenv("TEXTUS_ILLUSTRATION_BACKEND", "supabase")
    supabase_sentinel = _Sentinel()
    monkeypatch.setattr(ui, "_get_supabase_repository", lambda: supabase_sentinel)

    connection, mode = ui._resolve_data_source()

    assert connection is supabase_sentinel
    assert mode == "production"


def test_cloud_config_error_never_silently_becomes_sqlite(monkeypatch) -> None:
    """The exact incident this whole audit traced: a cloud deployment
    with no backend configured must NEVER fall through to opening a
    local SQLite file. Proven here by making _get_connection explode if
    it's ever reached."""
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    monkeypatch.setattr(
        ui, "_get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("must never reach local SQLite from a cloud config error")),
    )
    with pytest.raises(IllustrationBackendConfigurationError):
        ui._resolve_data_source()


# ---------------------------------------------------------------------------
# _is_candidate_fetch_error -- the empty-vs-error UI branch decision
# ---------------------------------------------------------------------------


def _diag(reason: str) -> RetrievalDiagnostics:
    return RetrievalDiagnostics(
        reason=reason, intent=RetrievalIntent(), stage_a_pool_size=0, stage_a_candidate_count=0,
        stage_a_top_scores=(), stage_b_parsed_count=0, stage_b_accepted_count=0, final_count=0,
    )


def test_candidate_fetch_error_reason_is_flagged_as_error_state() -> None:
    assert ui._is_candidate_fetch_error(_diag("candidate_fetch_error")) is True


def test_supabase_zero_published_is_normal_empty_result_not_error() -> None:
    """A Supabase RPC that legitimately returns 0 published candidates
    (REASON_NO_LOCAL_CANDIDATES) must render as the normal "Nincs
    megfelelő találat" empty state, NEVER as the error banner -- this is
    the exact scenario the 0-published production smoke test exercises."""
    assert ui._is_candidate_fetch_error(_diag("no_local_candidates")) is False


def test_ok_reason_is_not_flagged_as_error() -> None:
    assert ui._is_candidate_fetch_error(_diag("ok")) is False


def test_none_diagnostics_is_not_flagged_as_error() -> None:
    assert ui._is_candidate_fetch_error(None) is False


def test_other_llm_error_reasons_not_flagged_as_candidate_fetch_error() -> None:
    """planner_error/ranking_error are pre-existing, separately-labeled
    reasons (shown via _REASON_LABELS_HU in dev diagnostics) -- this
    boolean is specifically about the NEW candidate_fetch_error reason,
    not a catch-all "any error reason" check."""
    assert ui._is_candidate_fetch_error(_diag("planner_error")) is False
    assert ui._is_candidate_fetch_error(_diag("ranking_error")) is False


# ---------------------------------------------------------------------------
# Reason-label coverage
# ---------------------------------------------------------------------------


def test_candidate_fetch_error_has_a_hungarian_dev_diagnostics_label() -> None:
    assert "candidate_fetch_error" in ui._REASON_LABELS_HU
