"""Phase 2D.2 — optional read-through cache for ``HebrewAnalysisBundle``.

The linguistic dataset behind ``HebrewAnalysisService`` is essentially
immutable within one active dataset version (Phase 2D.1 established the
whole MACULA alignment layer as a deterministic, versioned build). That
makes ``(reference, dataset_version_signature)`` a safe, minimal cache key:
a fresh dataset version simply never matches an old key, so no explicit
invalidation logic is needed — see
``HebrewAnalysisRepository.dataset_version_signature`` and
``HebrewAnalysisService.dataset_version_signature``.

This module is deliberately NOT wired into ``HebrewAnalysisService`` itself
— caching stays opt-in at the call site (e.g. a Streamlit UI holding one
``CachedHebrewAnalysisService`` in session state) rather than baked into the
core deterministic builder. No runtime AI caching, no TTL, no network I/O
here — this is a pure in-process memoization layer over an already-pure
function.
"""

from __future__ import annotations

from collections import OrderedDict

from bible_engine.hebrew_analysis_bundle import HebrewAnalysisBundle
from bible_engine.hebrew_analysis_repository import SYNTAX_GROUNDING_UNAVAILABLE
from bible_engine.hebrew_analysis_service import HebrewAnalysisService

DEFAULT_MAX_ENTRIES = 256


def _bundle_has_unavailable_syntax(bundle: HebrewAnalysisBundle) -> bool:
    """True if any verse's syntax fetch hit a transient backend error
    (2026-09 audit fix) — such a bundle must never be cached: caching it
    would keep serving the degraded result for the rest of the session even
    after the backend recovers, since nothing would ever invalidate it.

    ``getattr(..., "verses", ())`` rather than a direct attribute access
    deliberately: this cache is only ever exercised in tests against real
    ``HebrewAnalysisBundle`` instances OR a minimal fake double standing in
    for one (see ``tests/test_hebrew_analysis_cache.py``) — a fake with no
    ``verses`` attribute at all is simply never degraded."""
    return any(v.syntax_grounding == SYNTAX_GROUNDING_UNAVAILABLE for v in getattr(bundle, "verses", ()))


class CachedHebrewAnalysisService:
    """Wraps a ``HebrewAnalysisService`` with a version-keyed LRU cache.

    Only successful lookups are cached — a raised ``HebrewAnalysisUnavailable``
    propagates straight through and is never stored, so a transiently
    unavailable reference is retried on the next call rather than being
    "cached" as a failure. Likewise, a bundle whose syntax layer degraded to
    ``SYNTAX_GROUNDING_UNAVAILABLE`` (a transient repository-level error,
    not genuine absence of MACULA data — see ``hebrew_analysis_repository``)
    is returned to the caller but never stored, so the very next call for
    that reference retries the repository instead of replaying the same
    degraded result for the rest of the session.

    When the underlying repository cannot report a dataset-version signature
    (``dataset_version_signature()`` returns ``""`` — e.g. no local store
    reachable), caching is skipped entirely for that call rather than caching
    under a placeholder key that could silently span two different, unrelated
    dataset states.
    """

    def __init__(self, service: HebrewAnalysisService | None = None, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._service = service or HebrewAnalysisService()
        self._max_entries = max_entries
        self._cache: OrderedDict[tuple[str, str], HebrewAnalysisBundle] = OrderedDict()

    def dataset_version_signature(self) -> str:
        """Passthrough — lets a caller that only holds this cache (e.g. the
        Phase 2E UI, which keys ITS OWN separate AI-result cache on the
        same signature) avoid constructing a second, possibly differently
        configured ``HebrewAnalysisService``."""
        return self._service.dataset_version_signature()

    def get_hebrew_analysis(self, reference: str) -> HebrewAnalysisBundle:
        signature = self._service.dataset_version_signature()
        if not signature:
            return self._service.get_hebrew_analysis(reference)

        key = (reference, signature)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        bundle = self._service.get_hebrew_analysis(reference)
        if _bundle_has_unavailable_syntax(bundle):
            return bundle
        self._cache[key] = bundle
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)
        return bundle

    def cache_size(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()


__all__ = ["CachedHebrewAnalysisService", "DEFAULT_MAX_ENTRIES"]
