"""Phase 2C §16 — version-keyed cache for AI-generated
``GreekContextualAnalysis`` results. Mirrors
``bible_engine.hebrew_contextual_analysis_cache`` exactly (same key shape,
same "only successful results are cached" rule, same "unknown dataset
signature skips caching" rule) — see that module's docstring for the full
reasoning.

Cache key: ``(verse_id, dataset_version_signature, prompt_version,
model_id)``. This is what makes "one verse-level AI call serves every word
click within that verse" (task §16) actually true.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

from bible_engine.greek_analysis_bundle import GreekVerseAnalysis
from bible_engine.greek_contextual_analysis import CONTEXTUAL_ANALYSIS_PROMPT_VERSION
from bible_engine.greek_contextual_analysis_service import (
    STATUS_OK,
    GreekContextualAnalysisResult,
    request_greek_contextual_analysis,
)

DEFAULT_MAX_ENTRIES = 256

_CacheKey = tuple[str, str, str, str]


class GreekContextualAnalysisCache:
    def __init__(self, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._cache: "OrderedDict[_CacheKey, GreekContextualAnalysisResult]" = OrderedDict()

    def get(
        self, *, verse_id: str, dataset_version_signature: str, prompt_version: str, model_id: str,
    ) -> GreekContextualAnalysisResult | None:
        if not dataset_version_signature:
            return None
        key = (verse_id, dataset_version_signature, prompt_version, model_id)
        result = self._cache.get(key)
        if result is not None:
            self._cache.move_to_end(key)
        return result

    def set(
        self, *, verse_id: str, dataset_version_signature: str, prompt_version: str, model_id: str,
        result: GreekContextualAnalysisResult,
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


def get_or_request_greek_contextual_analysis(
    verse: GreekVerseAnalysis,
    *,
    dataset_version_signature: str,
    model_id: str,
    generate_fn: Callable[..., str],
    cache: GreekContextualAnalysisCache,
    generate_kwargs: dict[str, Any] | None = None,
    prompt_version: str = CONTEXTUAL_ANALYSIS_PROMPT_VERSION,
) -> GreekContextualAnalysisResult:
    """The single entry point UI code should call."""
    cached = cache.get(
        verse_id=verse.verse_id, dataset_version_signature=dataset_version_signature,
        prompt_version=prompt_version, model_id=model_id,
    )
    if cached is not None:
        return cached

    result = request_greek_contextual_analysis(verse, generate_fn=generate_fn, generate_kwargs=generate_kwargs)
    cache.set(
        verse_id=verse.verse_id, dataset_version_signature=dataset_version_signature,
        prompt_version=prompt_version, model_id=model_id, result=result,
    )
    return result


__all__ = [
    "DEFAULT_MAX_ENTRIES",
    "GreekContextualAnalysisCache",
    "get_or_request_greek_contextual_analysis",
]
