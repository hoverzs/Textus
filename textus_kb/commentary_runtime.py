"""Runtime bootstrap for the gitignored Commentary SQLite artifact.

Three layers:

- ``get_status`` / ``_validate_database``: fail-closed, LOCAL-ONLY
  validation (file exists, opens, schema-compatible) — never touches the
  network. Cheap and lenient (schema-version-only, no content/count
  check), unchanged since before this module had any download
  capability, and still what a large pre-existing test suite calls
  directly (and monkeypatches wholesale) — kept byte-for-byte identical.
- ``ensure_status``: the SINGLE production choke point every real
  Commentary-evidence consumer should call (the reader UI, Exegézis,
  Eredeti szöveg, Kortörténet — commentary_compare.py has no separate
  runtime path of its own, it is rendered from inside the same reader
  flow that already calls this). Cheap local check first (``get_status``,
  lenient, no network — so a process that already has *any*
  schema-valid local file, however it got there, never re-downloads);
  only when that reports unavailable does it fall through to remote
  provisioning. This is what makes "first Commentary need, from ANY
  module" trigger provisioning without requiring the reader tab to be
  opened first, while staying idempotent (one successful download makes
  every subsequent call from any module, in the same or a later
  process, a pure local no-network hit).
- ``ensure_commentary_database``: the STRICT explicit-verification entry
  point (used by ``scripts/setup_commentary_database_storage.py`` and
  the runtime's own test suite) — same remote-provisioning machinery as
  ``ensure_status``, but its LOCAL short-circuit check is the full
  strict one (schema + the exact pinned production counts/content_hash)
  even before attempting a download, so it always converges on exactly
  the pinned production artifact rather than "whatever schema-valid file
  happens to be there".

Both ``ensure_status`` and ``ensure_commentary_database`` share the same
download-and-install primitive, modeled directly on
``theology_runtime.ensure_theology_database`` (and, before it,
``bible_engine.hymn_repository.ensure_hymn_database`` /
``ruf_bible_local_db.ensure_local_database``) — the SAME established
pattern this codebase already uses for every other large, gitignored,
locally-built-but-remotely-mirrored SQLite artifact: download from a
PRIVATE Supabase Storage bucket, stream it to a unique ``.part`` temp file
while computing its SHA-256 (if configured; 2026-09: no longer buffered in
RAM), run
the FULL strict validation (schema + the exact pinned production
counts/content_hash) on that temp file, and only THEN atomically
``.replace()`` it onto the real path — a corrupt, wrong-schema, or
wrong-hash download is discarded and the existing (or missing) local
file is left untouched either way. Never raises: any network/auth/
storage failure degrades to the same fail-closed "Commentary
unavailable" status the app already shows when the DB is simply
missing.

Production never re-runs the ~15-45 minute Calvin/JFB/Henry corpus
build on startup: ``scripts/build_commentary_database.py --combined
--qa`` is a one-time (or on-demand, post-fix) LOCAL build step whose
output is uploaded ONCE to private storage (``scripts/
setup_commentary_database_storage.py``) and then fetched in seconds by
every subsequent deploy, from whichever module first needs Commentary
evidence, via ``ensure_status``.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from textus_kb.importers.commentary_sqlite import (
    DEFAULT_DATABASE_PATH,
    SCHEMA_VERSION,
    CommentaryImportError,
    validate_commentary_database,
)

COMMENTARY_DATABASE_PATH_ENV_VAR = "TEXTUS_COMMENTARY_DATABASE_PATH"

# Pinned production artifact metadata (2026-09-04, post multi-table-citation
# fix — verified directly against the actual built store, NOT copied from an
# earlier round's report: ``python -c "from textus_kb.importers.
# commentary_sqlite import validate_commentary_database as v; print(v(...))"``
# on the freshly rebuilt combined DB). Used only by the STRICT post-download
# validation inside ``ensure_commentary_database`` — never by the lenient
# ``get_status``/``_validate_database`` pair above, so a small local/test
# synthetic DB (schema-valid, but nowhere near these counts) keeps working
# exactly as it always has.
EXPECTED_IMPORT_MODE = "combined_commentary_thml"
EXPECTED_CONTENT_HASH = (
    "93fd30c7533a7da7af506b1047135ac30256212eca4cfad3df4bc4b942acbeb7"
)
EXPECTED_CONTRIBUTOR_COUNT = 27
EXPECTED_WORK_COUNT = 155
EXPECTED_EDITION_COUNT = 177
EXPECTED_SECTION_COUNT = 57331
EXPECTED_CHUNK_COUNT = 41955
EXPECTED_PASSAGE_LINK_COUNT = 54162

COMMENTARY_STORAGE_BUCKET_ENV_VAR = "TEXTUS_COMMENTARY_DB_STORAGE_BUCKET"
COMMENTARY_STORAGE_OBJECT_ENV_VAR = "TEXTUS_COMMENTARY_DB_STORAGE_OBJECT"
COMMENTARY_DATABASE_SHA256_ENV_VAR = "TEXTUS_COMMENTARY_DB_SHA256"

# 2026-09 production hotfix: the ~534 MB artifact is STREAMED to a temp file
# (never held in RAM as one ``bytes`` object), and only one thread per process
# may download/install at a time (Streamlit sessions and overlapping reruns are
# threads of the same process) -- a waiting caller re-checks the local file
# after acquiring the lock and reuses the freshly installed database.
_INSTALL_LOCK = threading.Lock()
_INSTALL_LOCK_WAIT_S = 600
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_SIGNED_URL_TTL_S = 600
_DIAG_MARK = "[COMMENTARY_DB]"
_diag_state = {"reported_available": False}


@dataclass(frozen=True)
class CommentaryRuntimeStatus:
    available: bool
    reason: str
    database_path: str
    detail: str = ""


def get_status(database_path: str | Path | None = None) -> CommentaryRuntimeStatus:
    """Validate a local Commentary DB without downloading or building it.

    ``database_path`` takes precedence; otherwise ``TEXTUS_COMMENTARY_DATABASE_PATH``;
    otherwise the default ``data/generated/commentary.sqlite3`` path.
    """
    path = _resolve_database_path(database_path)
    return _validate_database(path)


def ensure_status(
    database_path: str | Path | None = None,
    *,
    storage_bucket_id: str | None = None,
    storage_object_path: str | None = None,
    expected_database_sha256: str | None = None,
) -> CommentaryRuntimeStatus:
    """Single production choke point for every real Commentary-evidence
    consumer (the reader UI, Exegézis, Eredeti szöveg, Kortörténet — and
    transitively commentary_compare.py, which has no runtime path of its
    own and is only ever rendered from inside the reader flow that
    already calls this).

    Cheap LOCAL check first, via the same lenient, mockable ``get_status``
    every existing caller/test already uses — a process that already has
    *any* schema-valid local file (however it got there) returns
    immediately, no network call at all, matching every module's prior
    "just call get_status" behavior exactly when a DB is already present.
    Only when that reports unavailable does this fall through to the
    SAME remote-provisioning machinery as ``ensure_commentary_database``
    (download from private Supabase Storage, strict-validate the
    downloaded bytes, atomic install) — so the FIRST Commentary need from
    ANY module (not just the reader tab) provisions the DB, and every
    later call, from any module, in the same running process, is a pure
    local hit.

    Same safety guard as ``ensure_commentary_database``: an EXPLICIT
    ``database_path`` (or the ``TEXTUS_COMMENTARY_DATABASE_PATH`` env
    override), passed with no storage kwargs, never touches the network.
    """
    explicit_path = database_path is not None
    env_override = bool(os.environ.get(COMMENTARY_DATABASE_PATH_ENV_VAR, "").strip())
    path = _resolve_database_path(database_path)
    status = get_status(database_path=database_path)
    _diag_local_status(path, status)
    if status.available:
        return status

    allow_download = (not explicit_path and not env_override) or (
        storage_bucket_id is not None or storage_object_path is not None
    )
    if not allow_download:
        return status

    return _download_and_install(
        path,
        storage_bucket_id=storage_bucket_id,
        storage_object_path=storage_object_path,
        expected_database_sha256=_resolve_expected_sha256(expected_database_sha256),
        fallback_reason=status.reason,
        local_recheck=lambda: get_status(database_path=database_path),
    )


def ensure_commentary_database(
    database_path: str | Path | None = None,
    *,
    storage_bucket_id: str | None = None,
    storage_object_path: str | None = None,
    expected_database_sha256: str | None = None,
) -> CommentaryRuntimeStatus:
    """Strict explicit-verification entry point: ensures a local Commentary
    SQLite file that matches the EXACT pinned production artifact
    (schema + counts + content_hash), downloading it from private
    Supabase Storage if the local file is missing OR merely
    schema-valid-but-not-the-real-thing — never rebuilding the corpus
    itself. Used by ``scripts/setup_commentary_database_storage.py``
    (to confirm what it's about to upload) and this module's own test
    suite; real application consumers should use ``ensure_status``
    instead (lenient local short-circuit, same download machinery).

    Mirrors ``theology_runtime.ensure_theology_database`` exactly,
    including its safety guard: an EXPLICIT ``database_path`` (or the
    ``TEXTUS_COMMENTARY_DATABASE_PATH`` env override), passed with no
    storage kwargs, never touches the network — this is what keeps every
    test/tmp-path caller network-free. Passing storage kwargs explicitly
    opts into download even for an explicit target path.

    Idempotent: a local file that already passes the SAME strict
    validation used on a fresh download (schema + the exact pinned
    production counts/content_hash) short-circuits immediately, no
    network call at all.
    """
    explicit_path = database_path is not None
    env_override = bool(os.environ.get(COMMENTARY_DATABASE_PATH_ENV_VAR, "").strip())
    path = _resolve_database_path(database_path)
    expected_sha256 = _resolve_expected_sha256(expected_database_sha256)
    status = _validate_downloaded_database(path, expected_database_sha256=expected_sha256)
    if status.available:
        return status

    allow_download = (not explicit_path and not env_override) or (
        storage_bucket_id is not None or storage_object_path is not None
    )
    if not allow_download:
        return status

    return _download_and_install(
        path,
        storage_bucket_id=storage_bucket_id,
        storage_object_path=storage_object_path,
        expected_database_sha256=expected_sha256,
        fallback_reason=status.reason,
        local_recheck=lambda: _validate_downloaded_database(
            path, expected_database_sha256=expected_sha256
        ),
    )


def _download_and_install(
    path: Path,
    *,
    storage_bucket_id: str | None,
    storage_object_path: str | None,
    expected_database_sha256: str,
    fallback_reason: str = "",
    local_recheck: Callable[[], CommentaryRuntimeStatus] | None = None,
) -> CommentaryRuntimeStatus:
    """Shared download/verify/atomic-install primitive behind both
    ``ensure_status`` and ``ensure_commentary_database`` — the ONLY place
    that touches Supabase Storage or writes the local file. Never raises:
    any network/auth/storage/disk failure degrades to a fail-closed
    status, and a corrupt/wrong-hash/wrong-invariant download is
    discarded (the unique ``.part`` temp file is removed) without ever
    touching the existing (or missing) local file at ``path``.

    2026-09 hotfix: the object is streamed in 1 MiB chunks straight into the
    temp file while its SHA-256 is computed incrementally (the old
    ``bytes`` download held the whole ~534 MB artifact in memory, once per
    concurrent caller). One install at a time per process (``_INSTALL_LOCK``);
    a caller that waited re-runs ``local_recheck`` first and returns the
    database another thread has just installed, without downloading again."""
    bucket_id = storage_bucket_id or _configured_storage_bucket_id()
    object_path = storage_object_path or _configured_storage_object_path()
    if not bucket_id or not object_path:
        _diag(f"download skipped: storage not configured (local status={fallback_reason or '?'})")
        return CommentaryRuntimeStatus(
            available=False,
            reason="storage_not_configured",
            database_path=str(path),
            detail=fallback_reason,
        )

    waited = time.monotonic()
    if not _INSTALL_LOCK.acquire(timeout=_INSTALL_LOCK_WAIT_S):
        _diag(f"install lock busy for {_INSTALL_LOCK_WAIT_S}s -> not downloading in parallel")
        return CommentaryRuntimeStatus(
            available=False,
            reason="download_in_progress",
            database_path=str(path),
            detail=fallback_reason,
        )
    try:
        waited_s = time.monotonic() - waited
        if local_recheck is not None:
            rechecked = local_recheck()
            if rechecked.available:
                _diag(f"reusing database installed by another caller (waited {waited_s:.1f}s)")
                return rechecked
        return _download_and_install_locked(
            path,
            bucket_id=bucket_id,
            object_path=object_path,
            expected_database_sha256=expected_database_sha256,
        )
    finally:
        _INSTALL_LOCK.release()


def _download_and_install_locked(
    path: Path,
    *,
    bucket_id: str,
    object_path: str,
    expected_database_sha256: str,
) -> CommentaryRuntimeStatus:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _diag(f"install failed: cannot create {path.parent} ({type(exc).__name__})")
        return CommentaryRuntimeStatus(
            available=False, reason="write_failed", database_path=str(path), detail=str(exc)
        )
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.part")
    started = time.monotonic()
    _diag(
        f"download start -> {tmp_path.name} (dir writable={os.access(path.parent, os.W_OK)}, "
        f"sha256 pinned={bool(expected_database_sha256)}, rss={_rss_mb()})"
    )
    try:
        try:
            from supabase_client import get_supabase_client

            bucket = get_supabase_client().storage.from_(bucket_id)
            size, digest = _fetch_object_to_file(bucket, object_path, tmp_path)
        except Exception as exc:  # noqa: BLE001 - runtime bootstrap must fail closed
            _diag(f"download failed after {time.monotonic() - started:.1f}s: {_safe_error(exc)}")
            return CommentaryRuntimeStatus(
                available=False,
                reason="download_failed",
                database_path=str(path),
                detail=_safe_error(exc),
            )
        _diag(
            f"download end: {size / 1048576:.1f} MB in {time.monotonic() - started:.1f}s "
            f"(rss={_rss_mb()})"
        )
        if not size:
            return CommentaryRuntimeStatus(
                available=False,
                reason="download_empty",
                database_path=str(path),
            )

        if expected_database_sha256 and digest != expected_database_sha256:
            _diag("validation: sha256 MISMATCH -> discarded")
            return CommentaryRuntimeStatus(
                available=False,
                reason="database_checksum_mismatch",
                database_path=str(path),
            )

        downloaded_status = _validate_downloaded_database(
            tmp_path, expected_database_sha256=expected_database_sha256
        )
        _diag(f"validation: {downloaded_status.reason} {downloaded_status.detail}".rstrip())
        if not downloaded_status.available:
            return CommentaryRuntimeStatus(
                available=False,
                reason=downloaded_status.reason,
                database_path=str(path),
                detail=downloaded_status.detail,
            )
        tmp_path.replace(path)
    except OSError as exc:
        _diag(f"install failed: {type(exc).__name__}")
        return CommentaryRuntimeStatus(
            available=False,
            reason="write_failed",
            database_path=str(path),
            detail=str(exc),
        )
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    final = _validate_database(path)
    _diag(f"install done: sqlite open/schema -> {final.reason} (size={_file_mb(path)})")
    return final


def _fetch_object_to_file(bucket, object_path: str, dest: Path) -> tuple[int, str]:  # noqa: ANN001
    """Write the storage object to ``dest`` in chunks; return (bytes, sha256 hex).

    Production path: a short-lived signed URL (public storage3 API, same
    SELECT permission as ``download``) fetched with a streaming ``httpx``
    GET, so memory stays at one chunk. A bucket object without
    ``create_signed_url`` (injected test doubles) keeps the old ``download``
    bytes API; it is still written to disk in chunks."""
    digest = hashlib.sha256()
    total = 0
    signer = getattr(bucket, "create_signed_url", None)
    with dest.open("wb") as handle:
        if signer is None:
            data = bucket.download(object_path) or b""
            view = memoryview(data)
            for offset in range(0, len(view), _DOWNLOAD_CHUNK_BYTES):
                chunk = view[offset : offset + _DOWNLOAD_CHUNK_BYTES]
                handle.write(chunk)
                digest.update(chunk)
            total = len(data)
        else:
            import httpx

            signed = signer(object_path, _SIGNED_URL_TTL_S) or {}
            url = signed.get("signedURL") or signed.get("signedUrl")
            if not url:
                raise RuntimeError("storage did not return a signed URL")
            timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
            with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(_DOWNLOAD_CHUNK_BYTES):
                    handle.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    return total, digest.hexdigest()


def _safe_error(exc: BaseException) -> str:
    """Error text without the signed URL / token (httpx puts URLs in messages)."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return f"{type(exc).__name__}: HTTP {status}"
    text = re.sub(r"https?://\S+", "<url>", str(exc))
    return f"{type(exc).__name__}: {text}"[:300]


def _diag(message: str) -> None:
    """One flushed stderr line for the Streamlit Cloud log (no secrets/URLs)."""
    try:
        print(f"{_DIAG_MARK} {message}", file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001 - diagnostics must never break the app
        pass


def _diag_local_status(path: Path, status: CommentaryRuntimeStatus) -> None:
    if status.available:
        if _diag_state["reported_available"]:
            return  # once per process -- ensure_status runs on every tab render
        _diag_state["reported_available"] = True
    _diag(
        f"local status: {status.reason} path={path} exists={path.is_file()} "
        f"size={_file_mb(path)}"
    )


def _file_mb(path: Path) -> str:
    try:
        return f"{path.stat().st_size / 1048576:.1f}MB"
    except OSError:
        return "-"


def _rss_mb() -> str:
    try:
        with open("/proc/self/status", encoding="ascii", errors="ignore") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return f"{int(line.split()[1]) // 1024}MB"
    except Exception:  # noqa: BLE001
        pass
    return "?"


def _resolve_database_path(database_path: str | Path | None) -> Path:
    if database_path is not None:
        return Path(database_path)
    env_value = os.environ.get(COMMENTARY_DATABASE_PATH_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value)
    return DEFAULT_DATABASE_PATH


def _resolve_expected_sha256(expected_database_sha256: str | None) -> str:
    if expected_database_sha256 is not None:
        return expected_database_sha256.strip().lower()
    return _configured_database_sha256()


def _validate_database(path: Path) -> CommentaryRuntimeStatus:
    if not path.is_file():
        return CommentaryRuntimeStatus(False, "database_missing", str(path))
    try:
        validation = validate_commentary_database(path)
    except FileNotFoundError:
        return CommentaryRuntimeStatus(False, "database_missing", str(path))
    except (OSError, sqlite3.Error) as exc:
        return CommentaryRuntimeStatus(False, "database_unopenable", str(path), str(exc))
    except CommentaryImportError as exc:
        return CommentaryRuntimeStatus(False, "schema_incompatible", str(path), str(exc))
    if validation.schema_version != SCHEMA_VERSION:
        return CommentaryRuntimeStatus(
            False,
            "schema_incompatible",
            str(path),
            f"schema_version={validation.schema_version or '<missing>'}",
        )
    return CommentaryRuntimeStatus(True, "ok", str(path))


def _validate_downloaded_database(
    path: Path, *, expected_database_sha256: str = ""
) -> CommentaryRuntimeStatus:
    """Strict validation used ONLY for a file about to become (or that
    already is) the production artifact ``ensure_commentary_database``
    installs: everything ``_validate_database`` already checks, PLUS the
    raw-file SHA-256 (when configured) and the exact pinned production
    counts/content_hash. A local dev/test DB that only needs to pass the
    lenient ``get_status`` check is never subjected to this — it is only
    reached from inside ``ensure_commentary_database``."""
    if expected_database_sha256:
        if not path.is_file():
            return CommentaryRuntimeStatus(False, "database_missing", str(path))
        try:
            digest = _sha256_file(path)
        except OSError as exc:
            return CommentaryRuntimeStatus(False, "database_unopenable", str(path), str(exc))
        if digest != expected_database_sha256:
            return CommentaryRuntimeStatus(False, "database_checksum_mismatch", str(path))
    base = _validate_database(path)
    if not base.available:
        return base
    try:
        validation = validate_commentary_database(path)
    except (FileNotFoundError, OSError, sqlite3.Error, CommentaryImportError) as exc:
        return CommentaryRuntimeStatus(False, "database_unopenable", str(path), str(exc))
    mismatches = _invariant_mismatches(validation)
    if mismatches:
        return CommentaryRuntimeStatus(
            False, "metadata_validation_failed", str(path), "; ".join(mismatches)
        )
    return CommentaryRuntimeStatus(True, "ok", str(path))


def _invariant_mismatches(validation) -> list[str]:  # noqa: ANN001 - CommentaryStoreValidation
    expected = {
        "import_mode": (validation.import_mode, EXPECTED_IMPORT_MODE),
        "content_hash": (validation.content_hash, EXPECTED_CONTENT_HASH),
        "contributor_count": (validation.contributor_count, EXPECTED_CONTRIBUTOR_COUNT),
        "work_count": (validation.work_count, EXPECTED_WORK_COUNT),
        "edition_count": (validation.edition_count, EXPECTED_EDITION_COUNT),
        "section_count": (validation.section_count, EXPECTED_SECTION_COUNT),
        "chunk_count": (validation.chunk_count, EXPECTED_CHUNK_COUNT),
        "passage_link_count": (validation.passage_link_count, EXPECTED_PASSAGE_LINK_COUNT),
    }
    return [
        f"{name}={actual} expected={want}"
        for name, (actual, want) in expected.items()
        if actual != want
    ]


def _configured_storage_bucket_id() -> str:
    env_value = os.environ.get(COMMENTARY_STORAGE_BUCKET_ENV_VAR, "").strip()
    if env_value:
        return env_value
    return _commentary_secret_value("storage_bucket")


def _configured_storage_object_path() -> str:
    env_value = os.environ.get(COMMENTARY_STORAGE_OBJECT_ENV_VAR, "").strip()
    if env_value:
        return env_value
    return _commentary_secret_value("storage_object")


def _configured_database_sha256() -> str:
    env_value = os.environ.get(COMMENTARY_DATABASE_SHA256_ENV_VAR, "").strip()
    if env_value:
        return env_value.strip().lower()
    return _commentary_secret_value("database_sha256").strip().lower()


def _commentary_secret_value(key: str) -> str:
    try:
        import streamlit as st

        cfg = st.secrets.get("commentary_database", {})
        if isinstance(cfg, dict):
            value = cfg.get(key)
        else:
            value = getattr(cfg, key, "")
        return str(value or "").strip()
    except Exception:
        return ""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "COMMENTARY_DATABASE_PATH_ENV_VAR",
    "COMMENTARY_DATABASE_SHA256_ENV_VAR",
    "COMMENTARY_STORAGE_BUCKET_ENV_VAR",
    "COMMENTARY_STORAGE_OBJECT_ENV_VAR",
    "EXPECTED_CHUNK_COUNT",
    "EXPECTED_CONTENT_HASH",
    "EXPECTED_CONTRIBUTOR_COUNT",
    "EXPECTED_EDITION_COUNT",
    "EXPECTED_IMPORT_MODE",
    "EXPECTED_PASSAGE_LINK_COUNT",
    "EXPECTED_SECTION_COUNT",
    "EXPECTED_WORK_COUNT",
    "CommentaryRuntimeStatus",
    "ensure_commentary_database",
    "ensure_status",
    "get_status",
]
