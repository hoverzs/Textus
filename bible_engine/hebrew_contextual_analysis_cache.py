"""Phase 2E — version-keyed cache for AI-generated
``HebrewContextualAnalysis`` results.

Deliberately a SEPARATE cache from
``bible_engine.hebrew_analysis_cache.CachedHebrewAnalysisService`` (Phase
2D.2), which caches the deterministic ``HebrewAnalysisBundle`` — the two
have different versioning semantics (a deterministic bundle depends only on
the dataset version; an AI interpretation additionally depends on the
prompt/schema version and the model that produced it), so mixing them into
one cache would either over-invalidate the cheap deterministic data on a
prompt tweak, or under-invalidate the AI data on a dataset bump. See the
Phase 2E brief's caching section for this explicit split.

Cache key: ``(verse_id, dataset_version_signature, prompt_version,
model_id)``. Only successful (``STATUS_OK``) results are cached — a
transient failure must be retried on the next call, never "cached" as a
failure. When ``dataset_version_signature`` is unknown (``""``), caching is
skipped entirely, exactly like the Phase 2D.2 bundle cache's own rule.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

from bible_engine.hebrew_analysis_bundle import VerseAnalysis
from bible_engine.hebrew_contextual_analysis import CONTEXTUAL_ANALYSIS_PROMPT_VERSION
from bible_engine.hebrew_contextual_analysis_service import (
    STATUS_OK,
    HebrewContextualAnalysisResult,
    request_hebrew_contextual_analysis,
)

DEFAULT_MAX_ENTRIES = 256

_CacheKey = tuple[str, str, str, str]


class HebrewContextualAnalysisCache:
    def __init__(self, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._cache: "OrderedDict[_CacheKey, HebrewContextualAnalysisResult]" = OrderedDict()

    def get(
        self,
        *,
        verse_id: str,
        dataset_version_signature: str,
        prompt_version: str,
        model_id: str,
    ) -> HebrewContextualAnalysisResult | None:
        if not dataset_version_signature:
            return None
        key = (verse_id, dataset_version_signature, prompt_version, model_id)
        result = self._cache.get(key)
        if result is not None:
            self._cache.move_to_end(key)
        return result

    def set(
        self,
        *,
        verse_id: str,
        dataset_version_signature: str,
        prompt_version: str,
        model_id: str,
        result: HebrewContextualAnalysisResult,
    ) -> None:
        if not dataset_version_signature or result.status != STATUS_OK:
            return
        key = (verse_id, dataset_version_signature, prompt_version, model_id)
        self._cache[key] = result
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)

    def cache_size(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()


def get_or_request_hebrew_contextual_analysis(
    verse: VerseAnalysis,
    *,
    dataset_version_signature: str,
    model_id: str,
    generate_fn: Callable[..., str],
    cache: HebrewContextualAnalysisCache,
    generate_kwargs: dict[str, Any] | None = None,
    prompt_version: str = CONTEXTUAL_ANALYSIS_PROMPT_VERSION,
) -> HebrewContextualAnalysisResult:
    """The single entry point UI code should call: reuses a cached result
    for ``(verse, dataset_version_signature, prompt_version, model_id)``
    when one exists, otherwise makes exactly ONE AI call and caches the
    result on success. This is what makes "one verse-level AI call serves
    both word-click and verse-summary UI" (Phase 2E §14) actually true —
    every token click within the same verse hits this same cache entry."""
    cached = cache.get(
        verse_id=verse.verse_id,
        dataset_version_signature=dataset_version_signature,
        prompt_version=prompt_version,
        model_id=model_id,
    )
    if cached is not None:
        return cached

    result = request_hebrew_contextual_analysis(
        verse, generate_fn=generate_fn, generate_kwargs=generate_kwargs
    )
    cache.set(
        verse_id=verse.verse_id,
        dataset_version_signature=dataset_version_signature,
        prompt_version=prompt_version,
        model_id=model_id,
        result=result,
    )
    return result


__all__ = [
    "DEFAULT_MAX_ENTRIES",
    "HebrewContextualAnalysisCache",
    "get_or_request_hebrew_contextual_analysis",
]
