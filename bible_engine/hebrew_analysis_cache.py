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
from bible_engine.hebrew_analysis_service import HebrewAnalysisService

DEFAULT_MAX_ENTRIES = 256


class CachedHebrewAnalysisService:
    """Wraps a ``HebrewAnalysisService`` with a version-keyed LRU cache.

    Only successful lookups are cached — a raised ``HebrewAnalysisUnavailable``
    propagates straight through and is never stored, so a transiently
    unavailable reference is retried on the next call rather than being
    "cached" as a failure.

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
