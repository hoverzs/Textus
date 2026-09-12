"""OAuth / publikus alkalmazás-URL — központi konfiguráció.

A Streamlit natív `st.login()` az `[auth].redirect_uri` értéket használja.
Éles környezetben ez SOHA nem lehet localhost.
"""

from __future__ import annotations

import os
from typing import Any, Mapping
from urllib.parse import urlparse

# Kanonikus címek
DEFAULT_LOCAL_APP_URL = "http://localhost:8501"
# Éles Streamlit Cloud app (textus.ro ide irányít)
DEFAULT_CLOUD_APP_URL = "https://emmaus.streamlit.app"
OAUTH_CALLBACK_PATH = "/oauth2callback"

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _s(value: Any) -> str:
    return str(value or "").strip()


def _strip_trailing_slash(url: str) -> str:
    return _s(url).rstrip("/")


def is_localhost_url(url: str) -> bool:
    try:
        host = (urlparse(_s(url)).hostname or "").lower()
    except Exception:
        return "localhost" in _s(url).casefold()
    return host in _LOCAL_HOSTS


def request_host() -> str:
    """Aktuális kérés Host fejléce (ha elérhető)."""
    try:
        import streamlit as st

        headers = st.context.headers
        raw = _s(headers.get("Host") or headers.get("host") or "")
        return raw.split(":")[0].lower()
    except Exception:
        return ""


def is_local_runtime(*, host: str | None = None) -> bool:
    """True, ha BIZONYÍTOTTAN fejlesztői localhoston/loopback- vagy
    privát-hálózati címen futunk.

    2026-09 audit fix — fail-CLOSED: korábban egy sikertelen host-
    detektálás (üres, hiányzó vagy nem értelmezhető ``Host`` fejléc) is
    ``True``-t (local) adott vissza, ami egy production biztonsági
    ellenőrzést (``validate_oauth_redirect_safe``) csendben kikapcsolhatott,
    ha pl. egy proxy/CDN eltüntette a fejlécet. Mostantól csak a
    BIZONYÍTOTTAN localhost/loopback/privát-IP eset ad ``True``-t; minden
    más eset — ismert cloud host, VAGY hiányzó/hibás/nem értelmezhető
    host információ — ``False`` (nem local). Ugyanaz a fail-closed
    konvenció, mint ``illustration_review_ui.is_local_loopback_request()``-
    nél, amely már eddig is explicit dokumentálta ezt az irányt ugyanerre
    a hibaesetre."""
    if _s(os.environ.get("TEXTUS_FORCE_CLOUD")).lower() in ("1", "true", "yes"):
        return False
    if _s(os.environ.get("STREAMLIT_RUNTIME_ENVIRONMENT")).lower() == "cloud":
        return False
    h = (host if host is not None else request_host()).lower()
    if h.endswith(".streamlit.app"):
        return False
    return h in _LOCAL_HOSTS or h.startswith("192.168.") or h.startswith("10.")


def _secret_get(mapping: Any, key: str, default: str = "") -> str:
    if mapping is None:
        return default
    try:
        if hasattr(mapping, "get"):
            return _s(mapping.get(key, default))
    except Exception:
        pass
    try:
        return _s(getattr(mapping, key, default))
    except Exception:
        return default


def read_configured_public_app_url(secrets: Mapping[str, Any] | None = None) -> str:
    """Secretsből olvasott publikus URL (üres, ha nincs megadva).

    Kanonikus kulcs: ``TEXTUS_PUBLIC_URL``.
    Alias (visszafelé kompatibilis): ``APP_PUBLIC_URL``,
    valamint ``[auth].public_app_url``.
    """
    try:
        import streamlit as st

        sec = secrets if secrets is not None else st.secrets
    except Exception:
        sec = secrets
    if sec is None:
        return ""
    for key in ("TEXTUS_PUBLIC_URL", "APP_PUBLIC_URL"):
        top = _secret_get(sec, key)
        if top:
            return _strip_trailing_slash(top)
    try:
        auth = sec.get("auth", None) if hasattr(sec, "get") else None
    except Exception:
        auth = None
    nested = _secret_get(auth, "public_app_url")
    return _strip_trailing_slash(nested)


def resolve_public_app_url(
    *,
    secrets: Mapping[str, Any] | None = None,
    host: str | None = None,
) -> str:
    """Egyetlen kanonikus publikus alkalmazás-URL (séma + host, path nélkül)."""
    configured = read_configured_public_app_url(secrets)
    h = (host if host is not None else request_host()).lower()

    if configured:
        if (not is_local_runtime(host=h)) and is_localhost_url(configured):
            if h.endswith(".streamlit.app") or h:
                return f"https://{h}" if h else DEFAULT_CLOUD_APP_URL
            return DEFAULT_CLOUD_APP_URL
        return configured

    if is_local_runtime(host=h):
        try:
            import streamlit as st

            raw = _s(st.context.headers.get("Host") or "")
            if ":" in raw and raw.split(":")[0].lower() in _LOCAL_HOSTS:
                return f"http://{raw}"
        except Exception:
            pass
        return DEFAULT_LOCAL_APP_URL

    if h.endswith(".streamlit.app") or h == "emmaus.streamlit.app":
        return f"https://{h}"
    if h:
        return f"https://{h}"
    return DEFAULT_CLOUD_APP_URL


def oauth_redirect_uri_for(public_app_url: str) -> str:
    base = _strip_trailing_slash(public_app_url)
    return f"{base}{OAUTH_CALLBACK_PATH}"


def current_auth_redirect_uri(secrets: Mapping[str, Any] | None = None) -> str:
    try:
        import streamlit as st

        sec = secrets if secrets is not None else st.secrets
        auth = sec.get("auth", {}) if hasattr(sec, "get") else {}
        return _secret_get(auth, "redirect_uri")
    except Exception:
        return ""


def apply_oauth_redirect_uri(
    *,
    secrets: Mapping[str, Any] | None = None,
    host: str | None = None,
) -> str:
    """Beállítja / felülírja az `[auth].redirect_uri`-t a kanonikus publikus URL alapján."""
    public = resolve_public_app_url(secrets=secrets, host=host)
    desired = oauth_redirect_uri_for(public)
    h = host if host is not None else request_host()

    current = current_auth_redirect_uri(secrets)
    must_fix = False
    if desired and desired != current:
        must_fix = True
    if (not is_local_runtime(host=h)) and is_localhost_url(current):
        must_fix = True
        desired = oauth_redirect_uri_for(
            resolve_public_app_url(secrets=secrets, host=h)
        )

    if not must_fix:
        return current or desired

    try:
        import streamlit as st
        from streamlit.runtime.secrets import secrets_singleton

        try:
            auth_raw = st.secrets.get("auth", {}) or {}
            auth: dict[str, Any] = dict(auth_raw)
        except Exception:
            auth = {}
        auth["redirect_uri"] = desired
        secrets_singleton.merge_programmatic_secrets({"auth": auth})
    except Exception:
        pass
    return desired


def validate_oauth_redirect_safe(
    *,
    redirect_uri: str | None = None,
    host: str | None = None,
) -> tuple[bool, str]:
    """Éles környezetben localhost redirect → hibaüzenet."""
    h = host if host is not None else request_host()
    uri = _s(redirect_uri) or current_auth_redirect_uri()
    if (not is_local_runtime(host=h)) and is_localhost_url(uri):
        return (
            False,
            "Az OAuth `redirect_uri` localhostra mutat éles környezetben. "
            "A Streamlit Cloud **Secrets** felületén állítsd be: "
            f'`TEXTUS_PUBLIC_URL = "{DEFAULT_CLOUD_APP_URL}"` és '
            f'`[auth] redirect_uri = "{oauth_redirect_uri_for(DEFAULT_CLOUD_APP_URL)}"`. '
            "A Google Cloud OAuth kliensben is engedd ugyanezt a callback URL-t.",
        )
    if not uri:
        return (
            False,
            "Hiányzik az `[auth].redirect_uri`. "
            f"Lokálisan: `{oauth_redirect_uri_for(DEFAULT_LOCAL_APP_URL)}`; "
            f"élesen: `{oauth_redirect_uri_for(DEFAULT_CLOUD_APP_URL)}`.",
        )
    return True, ""


def safe_streamlit_login() -> None:
    """`st.login()` localhost-safe burkoló."""
    import streamlit as st

    apply_oauth_redirect_uri()
    ok, msg = validate_oauth_redirect_safe()
    if not ok:
        st.error(msg)
        return
    st.login()


SECRETS_DOC_SNIPPET = f"""
# --- Publikus alkalmazás URL (kötelező élesen) ---
TEXTUS_PUBLIC_URL = "{DEFAULT_CLOUD_APP_URL}"
# Alias (opcionális): APP_PUBLIC_URL = "{DEFAULT_CLOUD_APP_URL}"

[auth]
# Lokál:  {oauth_redirect_uri_for(DEFAULT_LOCAL_APP_URL)}
# Éles:   {oauth_redirect_uri_for(DEFAULT_CLOUD_APP_URL)}
redirect_uri = "{oauth_redirect_uri_for(DEFAULT_CLOUD_APP_URL)}"
""".strip()


__all__ = [
    "DEFAULT_LOCAL_APP_URL",
    "DEFAULT_CLOUD_APP_URL",
    "OAUTH_CALLBACK_PATH",
    "SECRETS_DOC_SNIPPET",
    "is_localhost_url",
    "is_local_runtime",
    "resolve_public_app_url",
    "oauth_redirect_uri_for",
    "apply_oauth_redirect_uri",
    "validate_oauth_redirect_safe",
    "safe_streamlit_login",
    "current_auth_redirect_uri",
]
