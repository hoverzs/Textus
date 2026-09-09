"""Phase 2D.2 — dataset-version-signature and ``CachedHebrewAnalysisService``
tests.

Covers:
* ``LocalHebrewAnalysisRepository.dataset_version_signature()`` against a
  real fixture-built local store (same pattern as
  ``tests/test_hebrew_macula_alignment.py``'s ``ruth_linguistic_store``).
* ``SupabaseHebrewAnalysisRepository.dataset_version_signature()`` against
  the fake-Postgrest-client pattern from
  ``tests/test_hebrew_analysis_repository_supabase.py``.
* ``CachedHebrewAnalysisService`` — cache hits, version-keyed invalidation,
  no caching when the signature is unavailable, and exceptions never being
  cached — all against a small fake ``HebrewAnalysisService`` stand-in so
  these tests need no real Hebrew corpus and make no network calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bible_engine.hebrew_analysis_cache import CachedHebrewAnalysisService
from bible_engine.hebrew_analysis_repository import LocalHebrewAnalysisRepository, SupabaseHebrewAnalysisRepository
from bible_engine.hebrew_linguistic_sqlite import open_store
from bible_engine.hebrew_macula_importer import ensure_dataset_version, import_chapter
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.macula_lowfat_parser import parse_macula_lowfat_chapter

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "macula_lowfat"
RUTH_FIXTURE = FIXTURES / "ruth_1_excerpt-lowfat.xml"


@pytest.fixture
def ruth_linguistic_store_path(tmp_path):
    store_path = tmp_path / "linguistic.sqlite3"
    store = open_store(store_path)
    textus_dv = ensure_dataset_version(store, dataset_id="tahot", display_name="TAHOT", revision="rev-a")
    macula_dv = ensure_dataset_version(store, dataset_id="macula_hebrew_lowfat", display_name="MACULA", revision="rev-b")
    chapter = parse_macula_lowfat_chapter(RUTH_FIXTURE)
    repo = HebrewTokenRepository()
    import_chapter(
        chapter, tahot_book_code="Rut", chapter_number=1, store=store, token_repository=repo,
        textus_dataset_version_id=textus_dv, macula_dataset_version_id=macula_dv,
    )
    store.close()
    return store_path


def test_local_repository_dataset_version_signature_is_stable_and_sorted(ruth_linguistic_store_path):
    repository = LocalHebrewAnalysisRepository(ruth_linguistic_store_path)
    signature = repository.dataset_version_signature()
    assert signature == "macula_hebrew_lowfat:rev-b,tahot:rev-a"
    # Deterministic: calling again must produce byte-identical output.
    assert repository.dataset_version_signature() == signature


def test_local_repository_dataset_version_signature_empty_when_store_missing(tmp_path):
    repository = LocalHebrewAnalysisRepository(tmp_path / "does_not_exist.sqlite3")
    assert repository.dataset_version_signature() == ""


class _FakeVersionResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeVersionQuery:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self._eq_filters: dict[str, object] = {}

    def select(self, _columns: str) -> "_FakeVersionQuery":
        return self

    def eq(self, key: str, value) -> "_FakeVersionQuery":
        self._eq_filters[key] = value
        return self

    def execute(self) -> _FakeVersionResponse:
        matches = [row for row in self._rows if all(row.get(k) == v for k, v in self._eq_filters.items())]
        return _FakeVersionResponse(matches)


class _FakeVersionClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def table(self, name: str):
        assert name == "original_language_dataset_versions"
        return _FakeVersionQuery(self._rows)


def test_supabase_repository_dataset_version_signature_from_fake_client(monkeypatch):
    rows = [
        {"dataset_id": "tahot", "revision": "rev-a", "is_active": True},
        {"dataset_id": "macula_hebrew_lowfat", "revision": "rev-b", "is_active": True},
        {"dataset_id": "tahot", "revision": "old-rev", "is_active": False},
    ]
    monkeypatch.setattr("supabase_client.get_supabase_client", lambda: _FakeVersionClient(rows))
    repository = SupabaseHebrewAnalysisRepository()
    assert repository.dataset_version_signature() == "macula_hebrew_lowfat:rev-b,tahot:rev-a"


def test_supabase_repository_dataset_version_signature_empty_on_error(monkeypatch):
    def _raise():
        raise RuntimeError("no credentials configured")

    monkeypatch.setattr("supabase_client.get_supabase_client", _raise)
    repository = SupabaseHebrewAnalysisRepository()
    assert repository.dataset_version_signature() == ""


# ---------------------------------------------------------------------------
# CachedHebrewAnalysisService
# ---------------------------------------------------------------------------


class _FakeBundle:
    def __init__(self, reference: str, build_id: int) -> None:
        self.reference = reference
        self.build_id = build_id


class _FakeService:
    """Stands in for HebrewAnalysisService — records every real build, lets
    the test control the reported dataset-version signature."""

    def __init__(self, signature: str = "tahot:rev-a") -> None:
        self._signature = signature
        self.build_calls: list[str] = []
        self._raise_for: set[str] = set()

    def dataset_version_signature(self) -> str:
        return self._signature

    def get_hebrew_analysis(self, reference: str) -> _FakeBundle:
        self.build_calls.append(reference)
        if reference in self._raise_for:
            raise RuntimeError(f"unavailable: {reference}")
        return _FakeBundle(reference, len(self.build_calls))


def test_cache_hit_avoids_rebuilding_bundle():
    fake = _FakeService()
    cache = CachedHebrewAnalysisService(fake)

    first = cache.get_hebrew_analysis("Gen.1.1")
    second = cache.get_hebrew_analysis("Gen.1.1")

    assert first is second
    assert fake.build_calls == ["Gen.1.1"]
    assert cache.cache_size() == 1


def test_cache_miss_for_different_reference():
    fake = _FakeService()
    cache = CachedHebrewAnalysisService(fake)

    cache.get_hebrew_analysis("Gen.1.1")
    cache.get_hebrew_analysis("Gen.1.2")

    assert fake.build_calls == ["Gen.1.1", "Gen.1.2"]
    assert cache.cache_size() == 2


def test_cache_invalidated_by_dataset_version_change():
    fake = _FakeService(signature="tahot:rev-a")
    cache = CachedHebrewAnalysisService(fake)

    cache.get_hebrew_analysis("Gen.1.1")
    fake._signature = "tahot:rev-b"
    bundle_after_bump = cache.get_hebrew_analysis("Gen.1.1")

    assert fake.build_calls == ["Gen.1.1", "Gen.1.1"]
    assert bundle_after_bump.build_id == 2
    # Both the old- and new-version entries are retained (no explicit
    # eviction of stale versions — see module docstring) but the old one is
    # simply never looked up again.
    assert cache.cache_size() == 2


def test_no_caching_when_signature_unavailable():
    fake = _FakeService(signature="")
    cache = CachedHebrewAnalysisService(fake)

    cache.get_hebrew_analysis("Gen.1.1")
    cache.get_hebrew_analysis("Gen.1.1")

    assert fake.build_calls == ["Gen.1.1", "Gen.1.1"]
    assert cache.cache_size() == 0


def test_exception_is_never_cached():
    fake = _FakeService()
    fake._raise_for.add("Gen.99.99")
    cache = CachedHebrewAnalysisService(fake)

    with pytest.raises(RuntimeError):
        cache.get_hebrew_analysis("Gen.99.99")
    with pytest.raises(RuntimeError):
        cache.get_hebrew_analysis("Gen.99.99")

    assert fake.build_calls == ["Gen.99.99", "Gen.99.99"]
    assert cache.cache_size() == 0


def test_max_entries_evicts_least_recently_used():
    fake = _FakeService()
    cache = CachedHebrewAnalysisService(fake, max_entries=2)

    cache.get_hebrew_analysis("Gen.1.1")
    cache.get_hebrew_analysis("Gen.1.2")
    cache.get_hebrew_analysis("Gen.1.1")  # touch -> Gen.1.2 becomes LRU
    cache.get_hebrew_analysis("Gen.1.3")  # evicts Gen.1.2

    assert cache.cache_size() == 2
    cache.get_hebrew_analysis("Gen.1.2")  # Gen.1.2 was evicted above -> rebuilt
    assert fake.build_calls == ["Gen.1.1", "Gen.1.2", "Gen.1.3", "Gen.1.2"]


def test_clear_empties_cache():
    fake = _FakeService()
    cache = CachedHebrewAnalysisService(fake)
    cache.get_hebrew_analysis("Gen.1.1")
    cache.clear()
    assert cache.cache_size() == 0
    cache.get_hebrew_analysis("Gen.1.1")
    assert fake.build_calls == ["Gen.1.1", "Gen.1.1"]


def test_dataset_version_signature_passthrough():
    """Phase 2E: the UI's separate AI-result cache keys on this same
    signature without needing its own HebrewAnalysisService instance."""
    fake = _FakeService(signature="tahot:rev-z")
    cache = CachedHebrewAnalysisService(fake)
    assert cache.dataset_version_signature() == "tahot:rev-z"
