"""OAuth publikus URL / redirect biztonság."""

from __future__ import annotations

import pytest

from auth_config import (
    DEFAULT_CLOUD_APP_URL,
    DEFAULT_LOCAL_APP_URL,
    is_localhost_url,
    is_local_runtime,
    oauth_redirect_uri_for,
    resolve_public_app_url,
    validate_oauth_redirect_safe,
)


def test_localhost_detection():
    assert is_localhost_url("http://localhost:8501/oauth2callback")
    assert is_localhost_url("http://127.0.0.1:8501/oauth2callback")
    assert not is_localhost_url("https://emmaus.streamlit.app/oauth2callback")


def test_resolve_local_vs_cloud_host():
    assert (
        resolve_public_app_url(secrets={}, host="localhost")
        == DEFAULT_LOCAL_APP_URL
    )
    assert (
        resolve_public_app_url(secrets={}, host="emmaus.streamlit.app")
        == "https://emmaus.streamlit.app"
    )


def test_configured_app_public_url_wins_on_local():
    secrets = {"TEXTUS_PUBLIC_URL": "http://localhost:8501"}
    assert (
        resolve_public_app_url(secrets=secrets, host="localhost")
        == "http://localhost:8501"
    )


def test_textus_public_url_preferred_over_app_public_url():
    secrets = {
        "TEXTUS_PUBLIC_URL": "https://emmaus.streamlit.app",
        "APP_PUBLIC_URL": "http://localhost:8501",
    }
    assert (
        resolve_public_app_url(secrets=secrets, host="emmaus.streamlit.app")
        == "https://emmaus.streamlit.app"
    )


def test_app_public_url_alias_still_works():
    secrets = {"APP_PUBLIC_URL": "https://emmaus.streamlit.app"}
    assert (
        resolve_public_app_url(secrets=secrets, host="localhost")
        == "https://emmaus.streamlit.app"
    )


def test_cloud_rejects_localhost_configured_url():
    secrets = {"TEXTUS_PUBLIC_URL": "http://localhost:8501"}
    url = resolve_public_app_url(secrets=secrets, host="emmaus.streamlit.app")
    assert url == "https://emmaus.streamlit.app"
    assert not is_localhost_url(url)


def test_oauth_callback_path():
    assert (
        oauth_redirect_uri_for(DEFAULT_CLOUD_APP_URL)
        == "https://emmaus.streamlit.app/oauth2callback"
    )
    assert (
        oauth_redirect_uri_for(DEFAULT_LOCAL_APP_URL)
        == "http://localhost:8501/oauth2callback"
    )


def test_validate_blocks_localhost_on_cloud_host():
    ok, msg = validate_oauth_redirect_safe(
        redirect_uri="http://localhost:8501/oauth2callback",
        host="emmaus.streamlit.app",
    )
    assert not ok
    assert "localhost" in msg.casefold() or "localhostra" in msg.casefold()


def test_validate_allows_localhost_on_local_host():
    ok, _msg = validate_oauth_redirect_safe(
        redirect_uri="http://localhost:8501/oauth2callback",
        host="localhost",
    )
    assert ok


def test_is_local_runtime_streamlit_app_host():
    assert not is_local_runtime(host="emmaus.streamlit.app")
    assert is_local_runtime(host="localhost")


# --- 2026-09 audit fix: fail-CLOSED regression tests -----------------------
#
# Root cause of the bug these guard against: is_local_runtime() used to
# fall through to `return True` whenever the host could not be determined
# (empty/missing/unparseable Host header), which is a fail-OPEN default for
# a security-sensitive decision (it gates validate_oauth_redirect_safe's
# production localhost-redirect check). The fix makes every "we don't know"
# case resolve to False (not local / treat as production), matching the
# existing convention in illustration_review_ui.is_local_loopback_request().

def test_is_local_runtime_proven_localhost_is_local():
    assert is_local_runtime(host="localhost")
    assert is_local_runtime(host="127.0.0.1")
    assert is_local_runtime(host="::1")


def test_is_local_runtime_proven_private_network_is_local():
    assert is_local_runtime(host="192.168.1.50")
    assert is_local_runtime(host="10.0.0.5")


def test_is_local_runtime_known_cloud_host_is_not_local():
    assert not is_local_runtime(host="emmaus.streamlit.app")
    assert not is_local_runtime(host="some-other-app.streamlit.app")


def test_is_local_runtime_missing_host_fails_closed():
    """The core regression: an empty/unresolved host must NOT be treated
    as local — previously this fell through to `return True`."""
    assert not is_local_runtime(host="")


def test_is_local_runtime_malformed_host_fails_closed():
    """A garbage/unparseable host string matches none of the known
    local/cloud patterns and must resolve to "not local", not crash and
    not default to local."""
    assert not is_local_runtime(host="not a valid host!! \x00")
    assert not is_local_runtime(host="something.internal.example.com")


def test_is_local_runtime_request_host_failure_fails_closed(monkeypatch):
    """When the underlying Host-header lookup itself fails (e.g. a proxy
    stripped it, or the request context is unavailable), request_host()
    already degrades to "" — confirm is_local_runtime() (with no explicit
    host= override, i.e. going through request_host() itself) still fails
    closed rather than defaulting to local."""
    import auth_config

    monkeypatch.setattr(auth_config, "request_host", lambda: "")
    assert auth_config.is_local_runtime() is False


def test_is_local_runtime_force_cloud_still_wins_over_localhost_host(monkeypatch):
    """TEXTUS_FORCE_CLOUD behavior must be unchanged by this fix — it
    still overrides even a genuinely local-looking host."""
    monkeypatch.setenv("TEXTUS_FORCE_CLOUD", "1")
    assert is_local_runtime(host="localhost") is False


def test_is_local_runtime_streamlit_runtime_environment_cloud_still_wins(monkeypatch):
    monkeypatch.setenv("STREAMLIT_RUNTIME_ENVIRONMENT", "cloud")
    assert is_local_runtime(host="localhost") is False


def test_dev_seed_does_not_activate_on_uncertain_runtime_detection(monkeypatch):
    """TEXTUS_DEV_SEED must never activate just because runtime detection
    was inconclusive — it needs a PROVEN local runtime, which the
    fail-closed is_local_runtime() now guarantees when the host lookup
    itself fails."""
    import auth_config
    from writing_desk_dev_seed import maybe_apply_writing_desk_dev_seed

    monkeypatch.setattr(auth_config, "request_host", lambda: "")
    session: dict = {}
    applied = maybe_apply_writing_desk_dev_seed(
        session, env={"TEXTUS_DEV_SEED": "writing_desk"}
    )
    assert applied is False
    assert session == {}
