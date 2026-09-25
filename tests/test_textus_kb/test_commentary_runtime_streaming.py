"""2026-09 production hotfix — streamed, single-flight Commentary DB install.

The ~534 MB artifact used to be downloaded with storage3's ``download()``
(the whole object as one ``bytes`` value), hashed in memory, then written;
every concurrent caller did the same into ONE shared ``.part`` path. A local
benchmark with the real artifact measured ~1.2 GB peak for one caller and
~4.0 GB for four concurrent callers (3 of them ``write_failed``) — above the
3 GB Streamlit Cloud limit. These tests pin the fix:

* the production path (a bucket with ``create_signed_url``) streams the object
  in chunks via ``httpx.stream`` and never calls ``download()``;
* the SHA-256 / strict invariant checks still gate the atomic install;
* concurrent first callers download exactly once and all get the database;
* an installed database is reused without any network call;
* error details never contain the signed URL.
"""

from __future__ import annotations

import contextlib
import hashlib
import threading
import time
from pathlib import Path

import pytest

import textus_kb.commentary_runtime as runtime
from tests.test_textus_kb.test_commentary_runtime import (  # noqa: F401 - autouse fixture
    _import_sample,
    _isolate_storage_config,
    _pin_to_database,
)

SIGNED_URL = "https://example.supabase.co/storage/v1/object/sign/b/commentary.sqlite3?token=SECRET-TOKEN"


class _StreamingBucket:
    """storage3-like bucket: signed URL API, and a download() that must NOT be used."""

    def __init__(self) -> None:
        self.signed: list[tuple[str, int]] = []

    def create_signed_url(self, path: str, expires_in: int, options=None):  # noqa: ANN001
        self.signed.append((path, expires_in))
        return {"signedURL": SIGNED_URL, "signedUrl": SIGNED_URL}

    def download(self, path: str) -> bytes:  # pragma: no cover - asserting it is never reached
        raise AssertionError("production path must stream, not download() into memory")


class _Client:
    def __init__(self, bucket) -> None:  # noqa: ANN001
        self.storage = type("S", (), {"from_": lambda _s, _b: bucket})()


class _FakeResponse:
    def __init__(self, payload: bytes, chunk_log: list[int], delay_s: float, status: int) -> None:
        self._payload, self._log, self._delay, self.status_code = payload, chunk_log, delay_s, status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("GET", SIGNED_URL)
            raise httpx.HTTPStatusError(
                f"Client error '{self.status_code}' for url '{SIGNED_URL}'",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )

    def iter_bytes(self, chunk_size: int):
        for offset in range(0, len(self._payload), 4096):
            time.sleep(self._delay)
            chunk = self._payload[offset : offset + 4096]
            self._log.append(len(chunk))
            yield chunk


def _install_fake_stream(monkeypatch, payload: bytes, *, delay_s: float = 0.0, status: int = 200):
    import httpx

    calls: list[str] = []
    chunks: list[int] = []

    @contextlib.contextmanager
    def fake_stream(method, url, **kwargs):  # noqa: ANN001
        calls.append(url)
        yield _FakeResponse(payload, chunks, delay_s, status)

    monkeypatch.setattr(httpx, "stream", fake_stream)
    return calls, chunks


def _kwargs(target: Path, sha: str) -> dict:
    return dict(
        database_path=target,
        storage_bucket_id="test-commentary-private",
        storage_object_path="commentary.sqlite3",
        expected_database_sha256=sha,
    )


def test_first_install_streams_in_chunks_and_never_calls_download(tmp_path, monkeypatch):
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    payload = source.read_bytes()
    bucket = _StreamingBucket()
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _Client(bucket))
    calls, chunks = _install_fake_stream(monkeypatch, payload)
    target = tmp_path / "dst" / "commentary.sqlite3"

    status = runtime.ensure_status(**_kwargs(target, hashlib.sha256(payload).hexdigest()))

    assert status.available is True and status.reason == "ok"
    assert target.read_bytes() == payload
    assert calls == [SIGNED_URL] and bucket.signed == [("commentary.sqlite3", runtime._SIGNED_URL_TTL_S)]
    assert len(chunks) > 1  # really consumed as a stream
    assert not list(target.parent.glob("*.part"))


def test_streamed_checksum_mismatch_is_fail_closed(tmp_path, monkeypatch):
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _Client(_StreamingBucket()))
    _install_fake_stream(monkeypatch, source.read_bytes())
    target = tmp_path / "dst" / "commentary.sqlite3"

    status = runtime.ensure_status(**_kwargs(target, "0" * 64))

    assert status.available is False and status.reason == "database_checksum_mismatch"
    assert not target.exists()
    assert not list(target.parent.glob("*.part"))


def test_concurrent_first_callers_download_exactly_once(tmp_path, monkeypatch):
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    payload = source.read_bytes()
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _Client(_StreamingBucket()))
    calls, _ = _install_fake_stream(monkeypatch, payload, delay_s=0.002)
    target = tmp_path / "dst" / "commentary.sqlite3"
    kwargs = _kwargs(target, hashlib.sha256(payload).hexdigest())

    results = []
    threads = [threading.Thread(target=lambda: results.append(runtime.ensure_status(**kwargs))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert [r.reason for r in results] == ["ok"] * 4
    assert len(calls) == 1, f"{len(calls)} downloads for 4 concurrent callers"
    assert not list(target.parent.glob("*.part"))


def test_installed_database_is_reused_without_network(tmp_path, monkeypatch):
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    payload = source.read_bytes()
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _Client(_StreamingBucket()))
    calls, _ = _install_fake_stream(monkeypatch, payload)
    target = tmp_path / "dst" / "commentary.sqlite3"
    kwargs = _kwargs(target, hashlib.sha256(payload).hexdigest())

    assert runtime.ensure_status(**kwargs).available
    assert runtime.ensure_status(**kwargs).available
    assert len(calls) == 1


def test_http_error_detail_never_contains_the_signed_url(tmp_path, monkeypatch):
    source = _import_sample(tmp_path / "src")
    _pin_to_database(monkeypatch, source)
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _Client(_StreamingBucket()))
    _install_fake_stream(monkeypatch, b"", status=403)
    target = tmp_path / "dst" / "commentary.sqlite3"

    status = runtime.ensure_status(**_kwargs(target, "0" * 64))

    assert status.reason == "download_failed"
    assert "HTTP 403" in status.detail
    assert "SECRET-TOKEN" not in status.detail and "example.supabase.co" not in status.detail
    assert not target.exists() and not list(target.parent.glob("*.part"))


def test_safe_error_redacts_urls_in_plain_exceptions():
    detail = runtime._safe_error(RuntimeError(f"boom at {SIGNED_URL} now"))
    assert "SECRET-TOKEN" not in detail and "<url>" in detail


def test_lock_timeout_returns_in_progress_instead_of_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "_INSTALL_LOCK_WAIT_S", 0.05)
    monkeypatch.setattr(
        "supabase_client.get_supabase_client",
        lambda: (_ for _ in ()).throw(AssertionError("must not download while locked")),
    )
    runtime._INSTALL_LOCK.acquire()
    try:
        status = runtime.ensure_status(**_kwargs(tmp_path / "commentary.sqlite3", ""))
    finally:
        runtime._INSTALL_LOCK.release()
    assert status.reason == "download_in_progress" and status.available is False
