"""TEXTUS_ILLUSTRATION_BACKEND resolution — "local" | "supabase".

Mirrors `bible_engine.greek_analysis_repository`'s
`_configured_greek_analysis_backend()`/`_looks_like_cloud_environment()`
pattern (same env-var name shape, same cloud-environment detection), with
ONE deliberate divergence (2026-09-13 architecture decision, provenance
audit follow-up): where the Greek/Hebrew precedent only LOGS A WARNING
and still silently falls back to the local backend when misconfigured in
a cloud environment, illustration HARD-FAILS instead.

This is not inconsistency for its own sake — it is a direct, evidenced
response to the actual incident that started this audit: a production
deployment silently querying an empty, freshly-autocreated local SQLite
file (because nothing had ever pointed it at real data, and
`sqlite3.connect()` auto-creates a missing file rather than erroring)
produced a 0-result search for every single passage, indistinguishable
from "the retrieval worked correctly and genuinely found nothing." A
loud, distinct configuration error is the only thing that would have
caught that immediately instead of it going unnoticed indefinitely.
"""

from __future__ import annotations

import os

ALLOWED_ILLUSTRATION_BACKENDS = frozenset({"local", "supabase"})


class IllustrationBackendConfigurationError(RuntimeError):
    """Raised when a cloud/production environment has not explicitly
    configured `TEXTUS_ILLUSTRATION_BACKEND=supabase`.

    Deliberately a DISTINCT exception type from any
    `illustration_engine.retrieval.RetrievalDiagnostics` reason code —
    this is a DEPLOYMENT MISCONFIGURATION, not a retrieval outcome, and
    must never be silently absorbed into `REASON_NO_LOCAL_CANDIDATES` or
    any other retrieval-level reason. A caller (the illustration UI
    modules) is expected to catch this specifically and render a
    distinct "not configured" state, never conflated with "no results"."""


def _looks_like_cloud_environment() -> bool:
    """Pure env-var check, deliberately duplicated from (not imported
    from) `bible_engine.greek_analysis_repository._looks_like_cloud_
    environment` — same "small helper, independently owned per module"
    convention already established across this codebase (see e.g.
    `illustration_engine.retrieval._fold_diacritics`'s own docstring for
    the identical reasoning: this module stays free of a dependency on
    `bible_engine` for a 3-line check)."""
    if (os.environ.get("TEXTUS_FORCE_CLOUD") or "").strip().lower() in ("1", "true", "yes"):
        return True
    return (os.environ.get("STREAMLIT_RUNTIME_ENVIRONMENT") or "").strip().lower() == "cloud"


def resolve_illustration_backend() -> str:
    """Returns `"local"` or `"supabase"`.

    Raises `IllustrationBackendConfigurationError` in a cloud environment
    when `TEXTUS_ILLUSTRATION_BACKEND` is not explicitly `"supabase"` —
    NEVER silently falls back to `"local"` there.

    In a non-cloud (local development) environment, an unset or
    unrecognized value defaults to `"local"` — exactly today's zero-
    configuration developer experience, unchanged. An explicit
    `TEXTUS_ILLUSTRATION_BACKEND=supabase` also works locally (e.g. for a
    developer deliberately testing against the real Supabase project)."""
    raw = (os.environ.get("TEXTUS_ILLUSTRATION_BACKEND", "") or "").strip().lower()

    if _looks_like_cloud_environment():
        if raw != "supabase":
            raise IllustrationBackendConfigurationError(
                "TEXTUS_ILLUSTRATION_BACKEND must be explicitly set to 'supabase' in a "
                f"cloud environment (STREAMLIT_RUNTIME_ENVIRONMENT=cloud) -- got {raw!r}. "
                "Refusing to silently fall back to an empty local SQLite database -- this "
                "is exactly the failure mode the 2026-09 provenance audit traced as the "
                "root cause of every illustration search returning 0 results in production."
            )
        return "supabase"

    if raw not in ALLOWED_ILLUSTRATION_BACKENDS:
        return "local"
    return raw


__all__ = [
    "ALLOWED_ILLUSTRATION_BACKENDS",
    "IllustrationBackendConfigurationError",
    "resolve_illustration_backend",
]
