"""TEMPORARY production diagnostics — passage-selected crash investigation.

Purpose: a Streamlit Cloud session dies ("Oh no. Error running app.") right
after a passage is committed in Igehely, with no Python traceback in the
visible log. This module makes the log show the LAST STAGE reached, plus native
crash stacks and memory, so the failing stage can be identified. It changes no
behaviour: every helper swallows its own errors, decorators re-raise the
original exception unchanged, and nothing here is persisted.

Every line starts with the marker ``[PASSAGE_TRACE]`` (grep for it in the
Cloud "Manage app" logs). Only stage names, timings, memory and the passage
REFERENCE (e.g. "Jn 3,16", sanitised, max 40 chars) are logged — never
secrets, tokens, user data or generated content.

Switch off without a code change: set env ``TEXTUS_PASSAGE_TRACE=0``.
Remove entirely with ``git revert`` of the commit that added this file.
"""

from __future__ import annotations

import contextlib
import functools
import os
import re
import sys
import threading
import time
from typing import Any, Callable, Iterator

_ENABLED = os.environ.get("TEXTUS_PASSAGE_TRACE", "1").strip() not in {"0", "false", "off", ""}
_MARK = "[PASSAGE_TRACE]"
_state = {"run": 0, "banner": False, "faulthandler": False}
_lock = threading.Lock()
_WATCHDOG_S = 120  # dump all thread stacks if ONE script run exceeds this
_PASSAGE_SAFE = re.compile(r"[^\w\s.,:;\-–—]")


def _rss_mb() -> str:
    """Resident memory of this process (Linux /proc; '?' elsewhere)."""
    try:
        with open("/proc/self/status", encoding="ascii", errors="ignore") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return f"{int(line.split()[1]) // 1024}MB"
    except Exception:
        pass
    return "?"


def _read_int(path: str) -> int | None:
    try:
        with open(path, encoding="ascii") as fh:
            raw = fh.read().strip()
        return None if raw in {"max", ""} else int(raw)
    except Exception:
        return None


def _cgroup_mem() -> str:
    """Container memory usage / limit (cgroup v2, then v1)."""
    for cur_p, max_p in (
        ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
        ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        cur, lim = _read_int(cur_p), _read_int(max_p)
        if cur is not None:
            lim_s = f"{lim // 1048576}MB" if lim and lim < 1 << 50 else "unlimited"
            return f"cgroup={cur // 1048576}MB/{lim_s}"
    return "cgroup=?"


def emit(message: str) -> None:
    """One diagnostic line to stderr, flushed (so it survives a hard crash)."""
    if not _ENABLED:
        return
    try:
        print(
            f"{_MARK} {message} | run={_state['run']} rss={_rss_mb()} {_cgroup_mem()} "
            f"thr={threading.current_thread().name[:24]}",
            file=sys.stderr,
            flush=True,
        )
    except Exception:
        pass


def _banner_once() -> None:
    with _lock:
        if _state["banner"]:
            return
        _state["banner"] = True
    try:
        import platform
        import sqlite3

        try:
            import streamlit

            st_ver = streamlit.__version__
        except Exception:
            st_ver = "?"
        emit(
            f"process banner: python={platform.python_version()} platform={platform.platform()} "
            f"sqlite3_lib={sqlite3.sqlite_version} streamlit={st_ver} pid={os.getpid()} cwd={os.getcwd()}"
        )
    except Exception:
        pass


def _enable_faulthandler() -> None:
    """Native crash (segfault/abort) -> Python stack of every thread on stderr."""
    if not _ENABLED or _state["faulthandler"]:
        return
    try:
        import faulthandler

        faulthandler.enable(file=sys.stderr, all_threads=True)
        _state["faulthandler"] = True
        emit("faulthandler enabled (native crashes will print a Python stack)")
    except Exception:
        pass


def _clean_passage(value: Any) -> str:
    try:
        return _PASSAGE_SAFE.sub("", str(value or "")).strip()[:40]
    except Exception:
        return ""


def run_start(session_state: Any) -> None:
    """Call once at the top of every full script run."""
    if not _ENABLED:
        return
    try:
        _enable_faulthandler()
        _banner_once()
        with _lock:
            _state["run"] += 1
        try:
            import faulthandler

            faulthandler.dump_traceback_later(_WATCHDOG_S, repeat=False, file=sys.stderr)
        except Exception:
            pass
        emit("run start")
        try:
            typed = _clean_passage(session_state.get("igehely_input"))
            saved = _clean_passage(session_state.get("last_igehely"))
            emit(f"passage = {typed or '<empty>'} (last_igehely = {saved or '<empty>'})")
            emit(f"ui_mode = {_clean_passage(session_state.get('ui_mode'))}")
        except Exception:
            pass
    except Exception:
        pass


def run_end() -> None:
    """Call at the very end of a completed script run."""
    if not _ENABLED:
        return
    try:
        import faulthandler

        faulthandler.cancel_dump_traceback_later()
    except Exception:
        pass
    emit("run end (script completed)")


@contextlib.contextmanager
def stage(name: str) -> Iterator[None]:
    """Log entering/leaving a stage; an exception is logged, then re-raised unchanged."""
    if not _ENABLED:
        yield
        return
    emit(f"entering: {name}")
    started = time.time()
    try:
        yield
    except BaseException as exc:  # noqa: BLE001 - re-raised below, purely observational
        emit(f"EXCEPTION in {name}: {type(exc).__name__}")
        raise
    finally:
        emit(f"leaving: {name} ({(time.time() - started) * 1000:.0f} ms)")


def traced(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator form of :func:`stage` (signature and behaviour preserved)."""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with stage(name):
                return fn(*args, **kwargs)

        return wrapper

    return decorate


class _TracedTab:
    """Wrap one ``st.tabs`` container so ``with tabs[i]:`` logs its stage."""

    def __init__(self, real: Any, name: str) -> None:
        self._real = real
        self._name = name
        self._stage: Any = None

    def __enter__(self) -> Any:
        self._stage = stage(f"TAB[{self._name}]")
        self._stage.__enter__()
        try:
            return self._real.__enter__()
        except BaseException:
            self._stage.__exit__(*sys.exc_info())
            raise

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        try:
            return self._real.__exit__(exc_type, exc, tb)
        finally:
            self._stage.__exit__(exc_type, exc, tb)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._real, item)


def trace_tabs(tabs: Any, labels: Any) -> Any:
    """Return ``tabs`` with per-tab stage logging; on any problem return it untouched."""
    if not _ENABLED:
        return tabs
    try:
        names = [re.sub(r":material/\w+:\s*", "", str(label)).strip()[:40] for label in labels]
        wrapped = [_TracedTab(tab, names[i] if i < len(names) else str(i)) for i, tab in enumerate(tabs)]
        return wrapped
    except Exception:
        return tabs
