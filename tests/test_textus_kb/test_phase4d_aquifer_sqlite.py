"""Phase 4D: full Aquifer SQLite retrieval tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from textus_kb.adapters.aquifer_bible_dictionary import AquiferBibleDictionaryAdapter
from textus_kb.adapters.aquifer_study_notes import AquiferStudyNotesAdapter
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.evidence import PILOT_BUILD_ID_PHASE4E
from textus_kb.health import run_health_check
from textus_kb.importers.aquifer_bible_dictionary import load_pilot_bundle as load_dict_bundle
from textus_kb.importers.aquifer_bible_dictionary_sqlite import (
    DEFAULT_DATABASE_PATH as DICT_DB,
    import_dictionary_sqlite,
    validate_dictionary_database,
)
from textus_kb.importers.aquifer_study_notes import load_pilot_bundle as load_sn_bundle
from textus_kb.importers.aquifer_study_notes_sqlite import (
    DEFAULT_DATABASE_PATH as SN_DB,
    import_study_notes_sqlite,
    validate_study_notes_database,
)
from textus_kb.manifest import load_manifest
from textus_kb.pilot_registry import JOHN_4_PILOT, LUKE_10_PILOT, find_pilot
from textus_kb.repositories.aquifer_dictionary_repository import AquiferDictionaryRepository
from textus_kb.repositories.aquifer_study_notes_repository import AquiferStudyNotesRepository
from textus_kb.retrieval import retrieve
from tests.local_data import requires_aquifer_dictionary_db, requires_aquifer_study_notes_db

THIRD_PASSAGE = "Acts.2.1-13"
NO_DATA_PASSAGE = "3John.1.15"
JOHN_SN_BUNDLE = Path("data/kb/aquifer/john_4_1_42_study_notes.json")
JOHN_DICT_BUNDLE = Path("data/kb/aquifer/john_4_1_42_bible_dictionary.json")
LUKE_SN_BUNDLE = Path("data/kb/aquifer/luke_10_25_37_study_notes.json")
LUKE_DICT_BUNDLE = Path("data/kb/aquifer/luke_10_25_37_bible_dictionary.json")


@requires_aquifer_study_notes_db
def test_study_notes_sqlite_store_exists() -> None:
    assert SN_DB.is_file()
    validation = validate_study_notes_database(SN_DB)
    assert validation.article_count > 10000
    assert validation.chunk_count > validation.article_count


@requires_aquifer_dictionary_db
def test_dictionary_sqlite_store_exists() -> None:
    assert DICT_DB.is_file()
    validation = validate_dictionary_database(DICT_DB)
    assert validation.article_count > 5000
    assert validation.chunk_count > validation.article_count


def test_manifest_points_to_sqlite_stores() -> None:
    manifest = load_manifest()
    sn = manifest.source_by_id("aquifer_open_study_notes")
    di = manifest.source_by_id("aquifer_open_bible_dictionary")
    assert sn is not None and sn.source_type == "sqlite"
    assert di is not None and di.source_type == "sqlite"
    assert sn.resolved_path.suffix == ".sqlite3"
    assert di.resolved_path.suffix == ".sqlite3"


@requires_aquifer_dictionary_db
@requires_aquifer_study_notes_db
def test_adapters_use_sqlite_backend() -> None:
    manifest = load_manifest()
    sn = AquiferStudyNotesAdapter(manifest.source_by_id("aquifer_open_study_notes"))
    di = AquiferBibleDictionaryAdapter(manifest.source_by_id("aquifer_open_bible_dictionary"))
    assert sn.backend == "sqlite"
    assert di.backend == "sqlite"


@requires_aquifer_study_notes_db
def test_john4_parity_study_notes_article_ids() -> None:
    bundle = load_sn_bundle(JOHN_SN_BUNDLE)
    pilot_ids = {note["article_id"] for note in bundle["notes"]}
    repo = AquiferStudyNotesRepository(SN_DB)
    sqlite_ids = {row["article_id"] for row in repo.notes_for_passage(JOHN_4_PILOT.canonical)}
    assert pilot_ids.issubset(sqlite_ids)


@requires_aquifer_dictionary_db
def test_john4_parity_dictionary_article_ids() -> None:
    bundle = load_dict_bundle(JOHN_DICT_BUNDLE)
    pilot_ids = {entry["article_id"] for entry in bundle["entries"]}
    repo = AquiferDictionaryRepository(DICT_DB)
    for article_id in pilot_ids:
        assert repo.article_by_id(article_id) is not None


@requires_aquifer_study_notes_db
def test_luke10_parity_study_notes_article_ids() -> None:
    bundle = load_sn_bundle(LUKE_SN_BUNDLE)
    pilot_ids = {note["article_id"] for note in bundle["notes"]}
    repo = AquiferStudyNotesRepository(SN_DB)
    for article_id in pilot_ids:
        assert repo.article_by_id(article_id) is not None


@requires_aquifer_dictionary_db
def test_luke10_parity_dictionary_article_ids() -> None:
    bundle = load_dict_bundle(LUKE_DICT_BUNDLE)
    pilot_ids = {entry["article_id"] for entry in bundle["entries"]}
    repo = AquiferDictionaryRepository(DICT_DB)
    for article_id in pilot_ids:
        assert repo.article_by_id(article_id) is not None


@requires_aquifer_study_notes_db
def test_third_passage_without_pilot_registry() -> None:
    assert find_pilot(THIRD_PASSAGE) is None
    packet = retrieve(THIRD_PASSAGE)
    assert packet.build_id == PILOT_BUILD_ID_PHASE4E
    notes = sum(1 for item in packet.evidence_items if item.relation_type == "exegetical_note")
    dictionary = sum(1 for item in packet.evidence_items if item.relation_type == "dictionary_background")
    assert notes > 0
    assert dictionary > 0


def test_no_data_passage_graceful() -> None:
    packet = retrieve(NO_DATA_PASSAGE)
    assert any("no data for this passage" in w.lower() for w in packet.warnings)
    direct_dictionary = [
        item
        for item in packet.evidence_items
        if item.relation_type == "dictionary_background"
        and not item.metadata.get("entity_expansion")
    ]
    assert not direct_dictionary
    assert packet.passage_canonical == "3John.1.15"


@requires_aquifer_dictionary_db
def test_stable_dictionary_evidence_ids() -> None:
    packet = retrieve("Jn 4,1-42")
    dict_items = [item for item in packet.evidence_items if item.relation_type == "dictionary_background"]
    assert dict_items
    for item in dict_items:
        chunk_id = item.metadata.get("chunk_id")
        assert chunk_id
        assert item.evidence_id == f"EV-DICT-{chunk_id}"


def test_retrieval_candidate_limits_applied() -> None:
    packet = retrieve("Jn 4,1-42")
    notes = sum(1 for item in packet.evidence_items if item.relation_type == "exegetical_note")
    direct_dictionary = sum(
        1
        for item in packet.evidence_items
        if item.relation_type == "dictionary_background"
        and not item.metadata.get("entity_expansion")
    )
    assert notes <= 24
    assert direct_dictionary <= 48


def test_john4_regression_entities_and_budget() -> None:
    packet = retrieve("Jn 4,1-42")
    assert len(packet.entities) >= 19
    assert packet.build_id == PILOT_BUILD_ID_PHASE4E
    exegesis = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert exegesis.estimated_tokens <= 4500
    assert historical.estimated_tokens <= 3500


@requires_aquifer_dictionary_db
@requires_aquifer_study_notes_db
def test_health_includes_aquifer_stores() -> None:
    report = run_health_check()
    assert report.aquifer_study_notes_store is not None
    assert report.aquifer_dictionary_store is not None
    assert report.aquifer_study_notes_store.store_available is True
    assert report.aquifer_dictionary_store.store_available is True
    assert report.aquifer_study_notes_store.article_count > 0
    assert report.aquifer_dictionary_store.article_count > 0


def test_import_idempotent_dictionary(tmp_path: Path) -> None:
    target = tmp_path / "dict.sqlite3"
    first = import_dictionary_sqlite(database_path=target)
    second = import_dictionary_sqlite(database_path=target)
    assert first.article_count == second.article_count
    assert first.content_hash == second.content_hash


def test_import_idempotent_study_notes(tmp_path: Path) -> None:
    target = tmp_path / "sn.sqlite3"
    first = import_study_notes_sqlite(database_path=target)
    second = import_study_notes_sqlite(database_path=target)
    assert first.article_count == second.article_count
    assert first.content_hash == second.content_hash


@requires_aquifer_dictionary_db
@requires_aquifer_study_notes_db
def test_passage_query_performance_smoke() -> None:
    repo_sn = AquiferStudyNotesRepository(SN_DB)
    repo_di = AquiferDictionaryRepository(DICT_DB)
    t0 = time.perf_counter()
    repo_sn.chunks_for_passage(JOHN_4_PILOT.canonical)
    sn_ms = int((time.perf_counter() - t0) * 1000)
    t1 = time.perf_counter()
    repo_di.chunks_for_passage(JOHN_4_PILOT.canonical)
    di_ms = int((time.perf_counter() - t1) * 1000)
    assert sn_ms < 5000
    assert di_ms < 5000
