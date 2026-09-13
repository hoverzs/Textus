"""Gated service_role client factory — SERVER-TRUST model regression
coverage. The single most important guarantee this module provides:
NO caller can ever obtain a service_role-keyed Supabase client for
illustration review writes without first passing `is_authorized=True`
explicitly -- there is no bypass, no default, no "just this once"."""

from __future__ import annotations

import pytest

import illustration_engine.supabase_review_client as supabase_review_client
from illustration_engine.supabase_review_client import (
    IllustrationReviewNotAuthorizedError,
    get_illustration_review_client,
    get_service_role_client_for_migration,
)


@pytest.fixture(autouse=True)
def _isolate_from_ambient_secrets_toml(monkeypatch):
    """This worktree's `.streamlit/secrets.toml` is a HARD LINK to the
    real production secrets file (see the 2026-09-13 provenance-audit
    session) -- a `delenv(...)` alone is NOT enough to simulate "no
    credential configured" here, because `_load_supabase_url`/`_load_
    service_role_key` would silently fall back to reading the REAL
    production URL/key/service_key straight off disk, masking exactly
    the "missing credential" scenario these tests exist to check. This
    autouse fixture blocks the streamlit-secrets fallback for every test
    in this file; no current test relies on that fallback actually
    resolving a real value."""
    monkeypatch.setattr(supabase_review_client, "_read_url_from_streamlit_secrets", lambda: "")
    monkeypatch.setattr(supabase_review_client, "_read_service_key_from_streamlit_secrets", lambda: "")


class _FakeClient:
    def __init__(self, url: str, key: str) -> None:
        self.url = url
        self.key = key


def test_unauthorized_call_raises_and_never_constructs_a_client(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def _factory(url: str, key: str):
        calls.append((url, key))
        return _FakeClient(url, key)

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-secret")

    with pytest.raises(IllustrationReviewNotAuthorizedError):
        get_illustration_review_client(is_authorized=False, client_factory=_factory)

    assert calls == []  # the factory must never even be invoked


def test_authorized_call_with_credentials_returns_client(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-secret")

    client = get_illustration_review_client(is_authorized=True, client_factory=_FakeClient)

    assert isinstance(client, _FakeClient)
    assert client.url == "https://example.supabase.co"
    assert client.key == "service-secret"


def test_authorized_call_without_url_raises(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-secret")

    with pytest.raises(RuntimeError):
        get_illustration_review_client(is_authorized=True, client_factory=_FakeClient)


def test_authorized_call_without_service_key_raises(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    with pytest.raises(RuntimeError):
        get_illustration_review_client(is_authorized=True, client_factory=_FakeClient)


def test_service_key_is_a_separate_credential_from_the_anon_key(monkeypatch) -> None:
    """The anon/publishable key (SUPABASE_KEY, used by supabase_client.
    get_supabase_client()) must never be silently reused here -- a
    deployment that only configured the anon key must fail closed, not
    accidentally grant review-write access with the wrong key."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon-key-not-service-role")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    with pytest.raises(RuntimeError):
        get_illustration_review_client(is_authorized=True, client_factory=_FakeClient)


# ---------------------------------------------------------------------------
# get_service_role_client_for_migration -- 2026-09-13 production incident fix:
# the migration script's --apply path was using the anon/publishable client
# by accident (RLS correctly rejected the write). This is the dedicated
# service-role factory for that ONE script, deliberately separate from the
# reviewer-gated function above (no is_authorized param -- a CLI script's
# own --apply flag + human operator is its authorization, not a Streamlit
# request-context check that doesn't exist in a script).
# ---------------------------------------------------------------------------


def test_migration_client_constructs_with_valid_credentials(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-secret")

    client = get_service_role_client_for_migration(client_factory=_FakeClient)

    assert isinstance(client, _FakeClient)
    assert client.url == "https://example.supabase.co"
    assert client.key == "service-secret"


def test_migration_client_has_no_is_authorized_parameter() -> None:
    """Structural guarantee: this function's signature has no
    is_authorized flag at all -- a caller cannot pass True to skip a
    check that doesn't apply to a CLI script's authorization model,
    because there is no such parameter to pass."""
    import inspect

    params = inspect.signature(get_service_role_client_for_migration).parameters
    assert "is_authorized" not in params


def test_migration_client_missing_url_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-secret")

    with pytest.raises(RuntimeError):
        get_service_role_client_for_migration(client_factory=_FakeClient)


def test_migration_client_missing_service_key_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    with pytest.raises(RuntimeError):
        get_service_role_client_for_migration(client_factory=_FakeClient)


def test_migration_client_never_reuses_anon_key(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon-key-not-service-role")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    with pytest.raises(RuntimeError):
        get_service_role_client_for_migration(client_factory=_FakeClient)


def test_migration_client_error_message_never_contains_the_key_value(monkeypatch) -> None:
    """A distinctive, obviously-fake 'secret' value must never leak into
    the exception's string form -- the error message is static text,
    never an interpolation of the actual url/key values."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    # Also plant a distinctive value the anon key path might read, to make
    # sure THAT never leaks into a service-role-path error either.
    monkeypatch.setenv("SUPABASE_KEY", "distinctive-anon-value-must-not-leak-anywhere")

    with pytest.raises(RuntimeError) as excinfo:
        get_service_role_client_for_migration(client_factory=_FakeClient)

    assert "distinctive-anon-value-must-not-leak-anywhere" not in str(excinfo.value)
