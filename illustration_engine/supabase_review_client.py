"""Gated factory for the Supabase `service_role` client used by the
illustration review WRITE path — Phase 1 skeleton, not yet wired into
`illustration_review_ui.py`.

SERVER-TRUST MODEL, NOT RLS USER-AUTH — see `supabase/migrations/
20260913120000_illustration_corpus_layer.sql`'s header note for the full
rationale. Short version: Textus's Google login goes through Streamlit's
native `st.login()` + Google OIDC, which does NOT establish a Supabase
Auth session — `auth.uid()` is not populated for a logged-in reviewer.
Trusting a client-supplied identity (an email parameter, a header) at
the database layer would be trivially forgeable. So authorization for
illustration review writes happens ONCE, server-side, in Python
(`illustration_review_ui.is_authorized_reviewer()`) — and ONLY after
that check passes does this module hand out a `service_role`-keyed
client. `service_role` bypasses Postgres RLS by design, so the tables'
RLS policies are NOT this write path's security boundary; the boundary
is: (1) this is the ONLY function in the codebase allowed to construct
that client, (2) it refuses unconditionally unless told authorization
already passed, (3) the key itself lives only in Streamlit Secrets/env,
never sent to a browser (structurally true for a server-rendered
Streamlit app — there is no client-side JS that could leak it).

This module never imports `streamlit` for the authorization check
itself — the caller (eventually `illustration_review_ui.py`) is
responsible for calling `is_authorized_reviewer()` and passing its
result in explicitly. That keeps there being exactly ONE authorization
check in the whole write path, never two that could silently drift
apart from each other.
"""

from __future__ import annotations

import os


class IllustrationReviewNotAuthorizedError(PermissionError):
    """Raised by `get_illustration_review_client()` when the caller has
    not already confirmed `is_authorized_reviewer()` passed."""


def _read_service_key_from_env() -> str:
    return (os.environ.get("SUPABASE_SERVICE_KEY", "") or "").strip()


def _read_service_key_from_streamlit_secrets() -> str:
    """`st.secrets["supabase"]["service_key"]` — a SEPARATE key from the
    existing `[supabase].key` used by `supabase_client.get_supabase_
    client()` (which is meant for the anon/publishable key). Never read
    the same secret two different ways; a deployment that only ever
    configured the anon key must fail closed here, not silently reuse
    it for review writes."""
    try:
        import streamlit as st

        return str(st.secrets.get("supabase", {}).get("service_key") or "").strip()
    except Exception:
        return ""


def _load_service_role_key() -> str:
    for loader in (_read_service_key_from_env, _read_service_key_from_streamlit_secrets):
        key = loader()
        if key:
            return key
    return ""


def _read_url_from_env() -> str:
    return (os.environ.get("SUPABASE_URL", "") or "").strip()


def _read_url_from_streamlit_secrets() -> str:
    try:
        import streamlit as st

        return str(st.secrets.get("supabase", {}).get("url") or "").strip()
    except Exception:
        return ""


def _load_supabase_url() -> str:
    """Reuses the SAME `SUPABASE_URL` every other Supabase-backed module
    in this repo already reads (`supabase_client.py`) — the project URL
    is not a secret, only the key is; no reason to duplicate its
    resolution logic beyond the env-var fallback. Split into named
    per-source functions (mirroring `_load_service_role_key`'s own
    shape) specifically so tests can monkeypatch the streamlit-secrets
    fallback in isolation -- otherwise a real `.streamlit/secrets.toml`
    present on whatever machine runs the test suite would silently
    defeat a test's attempt to simulate "no URL configured"."""
    for loader in (_read_url_from_env, _read_url_from_streamlit_secrets):
        url = loader()
        if url:
            return url
    return ""


def _build_service_role_client(client_factory=None, *, context: str):
    """Shared credential-loading + client-construction core for BOTH
    service-role factories below. `context` is only used in the error
    message (which table/caller wanted a service-role client) — it never
    carries the credential itself. Never logs, prints, or embeds `url`/
    `key` in any exception message beyond this function's own explicit,
    static text; a missing credential fails closed here, before either
    caller does anything else."""
    url = _load_supabase_url()
    key = _load_service_role_key()
    if not url or not key:
        raise RuntimeError(
            f"SUPABASE_URL and SUPABASE_SERVICE_KEY (or [supabase].service_key in "
            f"secrets.toml) are both required to construct a service_role Supabase client "
            f"for {context} -- this is intentionally a SEPARATE credential from the anon/"
            f"publishable key supabase_client.get_supabase_client() uses."
        )

    if client_factory is None:
        from supabase import create_client as client_factory

    return client_factory(url, key)


def get_illustration_review_client(*, is_authorized: bool, client_factory=None):
    """Returns a `service_role`-keyed Supabase client for illustration
    review writes — ONLY if `is_authorized` is `True`.

    The caller MUST have already evaluated `illustration_review_ui.
    is_authorized_reviewer()` and passed its result in explicitly — this
    function does not, and must never, re-derive authorization itself.

    Raises `IllustrationReviewNotAuthorizedError` if `is_authorized` is
    `False` — never returns a client, never falls back to a weaker key,
    never proceeds "just this once."

    `client_factory` is an injection point for tests only (defaults to
    the real `supabase.create_client`) — production callers never pass
    it."""
    if not is_authorized:
        raise IllustrationReviewNotAuthorizedError(
            "illustration review write access requires is_authorized_reviewer() to have "
            "passed first -- refusing to construct a service_role client."
        )
    return _build_service_role_client(client_factory, context="the illustration review UI")


def get_service_role_client_for_migration(client_factory=None):
    """Returns a `service_role`-keyed Supabase client for the ONE-TIME
    illustration migration script (`scripts/migrate_illustrations_to_
    supabase.py`), and ONLY that script.

    DIFFERENT authorization model from `get_illustration_review_client`
    above, deliberately -- there is no Streamlit request context or
    `is_authorized_reviewer()` check to gate on here; this is a manually-
    invoked, human-operated CLI script whose own `--apply` flag plus the
    person running it locally with access to the production secrets file
    IS the authorization. Reuses the SAME credential-loading helpers
    (`_load_supabase_url`/`_load_service_role_key`) as the reviewer path
    -- one source of truth for how the service_role credential is found,
    never duplicated -- but is its own function, never routed through
    `get_illustration_review_client`, so an `is_authorized=True` there
    can never be misread as meaning "the Streamlit reviewer gate passed"
    when it did not.

    The migration script's dry-run path (`--source` without `--apply`)
    NEVER calls this function at all -- see `scripts/migrate_
    illustrations_to_supabase.py::run_migration`, which returns before
    reaching any client construction when `apply=False`. The anon/
    publishable client (`supabase_client.get_supabase_client()`) is NEVER
    used for migration writes -- RLS correctly rejects it (see the
    2026-09-13 production incident this function was added to fix:
    the migration script's --apply path was, until this fix, using the
    anon-tier client by accident, and RLS correctly blocked every write)."""
    return _build_service_role_client(client_factory, context="the illustration migration script")


__all__ = [
    "IllustrationReviewNotAuthorizedError",
    "get_illustration_review_client",
    "get_service_role_client_for_migration",
]
