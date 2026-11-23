"""Tests for Aquifer Open Bible Dictionary Phase 3C pilot integration."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from textus_kb.adapters.aquifer_bible_dictionary import AquiferBibleDictionaryAdapter
from textus_kb.canonical_reference import CanonicalReference
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.evidence import PILOT_BUILD_ID_PHASE4E, RELATION_DICTIONARY_BACKGROUND
from textus_kb.importers.aquifer_bible_dictionary import (
    AQUIFER_DICTIONARY_SOURCE_ID,
    AQUIFER_LICENSE,
    PILOT_INDEX_REFERENCES,
    import_john_4_pilot,
    load_pilot_bundle,
)
from textus_kb.manifest import load_manifest
from textus_kb.retrieval import retrieve, retrieve_to_json
from tests.local_data import requires_aquifer_dictionary_db

PILOT_BUNDLE = Path("data/kb/aquifer/john_4_1_42_bible_dictionary.json")
PACKET_WITH_DICTIONARY = Path("tests/fixtures/kb/john_4_1_42_packet_with_dictionary.json")
EXEGESIS_PHASE3C = Path("tests/fixtures/kb/john_4_1_42_exegesis_context_phase3c.json")
HISTORICAL_PHASE3C = Path("tests/fixtures/kb/john_4_1_42_historical_context_phase3c.json")


def test_dictionary_manifest_source_valid() -> None:
    manifest = load_manifest()
    source = manifest.source_by_id(AQUIFER_DICTIONARY_SOURCE_ID)
    assert source is not None
    assert source.license == "CC-BY-SA-4.0"
    assert source.source_type == "sqlite"
    assert source.language == "en"
    assert source.enabled is True
    assert source.required is False


def test_pilot_bundle_preserves_license_and_provenance() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    assert bundle["license"] == AQUIFER_LICENSE
    assert bundle["source_id"] == AQUIFER_DICTIONARY_SOURCE_ID
    assert bundle["upstream_commit"]
    assert bundle["attribution"]
    entry = bundle["entries"][0]
    assert entry["content_html"]
    assert entry["license"] == AQUIFER_LICENSE
    assert entry["attribution"]


def test_john_4_dictionary_entries_imported() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    assert bundle["pilot_scope"] == "John.4.1-42"
    assert len(bundle["entries"]) == len(PILOT_INDEX_REFERENCES)
    titles = {entry["title"] for entry in bundle["entries"]}
    assert "Samaritans" in titles
    assert "Sychar" in titles
    assert "Mount Gerizim" in titles


def test_irrelevant_dictionary_entry_excluded() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    index_refs = {entry["index_reference"] for entry in bundle["entries"]}
    assert "dragons well" not in index_refs
    assert index_refs.issubset(PILOT_INDEX_REFERENCES)


def test_chunk_ids_stable() -> None:
    first = import_john_4_pilot(
        upstream_root=Path("_upstream_audit/AquiferOpenBibleDictionary"),
        output_path=Path("tests/fixtures/kb/tmp_dictionary_bundle_a.json"),
    )
    second = import_john_4_pilot(
        upstream_root=Path("_upstream_audit/AquiferOpenBibleDictionary"),
        output_path=Path("tests/fixtures/kb/tmp_dictionary_bundle_b.json"),
    )
    bundle_a = load_pilot_bundle(first.output_path)
    bundle_b = load_pilot_bundle(second.output_path)
    ids_a = [chunk["chunk_id"] for entry in bundle_a["entries"] for chunk in entry["chunks"]]
    ids_b = [chunk["chunk_id"] for entry in bundle_b["entries"] for chunk in entry["chunks"]]
    assert ids_a == ids_b
    assert len(ids_a) == first.chunk_count


def test_original_english_content_unchanged() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    adapter_source = load_manifest().source_by_id(AQUIFER_DICTIONARY_SOURCE_ID)
    adapter = AquiferBibleDictionaryAdapter(adapter_source)
    chunks = adapter.load_chunks_for_article("8676")
    entry = next(item for item in bundle["entries"] if item["article_id"] == "8676")
    chunk = chunks[0]
    assert entry["content_html"] in chunk.content_html or chunk.content_html in entry["content_html"]
    assert "sychar" in chunk.content_plain.lower()


@requires_aquifer_dictionary_db
def test_retrieval_includes_dictionary_evidence_deterministically() -> None:
    first = json.loads(retrieve_to_json("Jn 4,1-42"))
    second = json.loads(retrieve_to_json("Jn 4,1-42"))
    assert first == second
    dictionary_items = [
        item
        for item in first["evidence_items"]
        if item["relation_type"] == RELATION_DICTIONARY_BACKGROUND
    ]
    assert len(dictionary_items) == 66
    assert first["build"]["build_id"] == PILOT_BUILD_ID_PHASE4E
    titles = {item["metadata"].get("title") for item in dictionary_items}
    assert "Abba" not in titles
    assert "Aegean Sea" not in titles
    assert "Samaritans" in titles or "Sychar" in titles


def test_dictionary_evidence_type_distinct() -> None:
    packet = retrieve("Jn 4,1-42")
    dictionary_items = [
        item for item in packet.evidence_items if item.relation_type == RELATION_DICTIONARY_BACKGROUND
    ]
    assert dictionary_items
    assert all(item.source_type == "bible_dictionary" for item in dictionary_items)
    assert all(item.relation_type != "exegetical_note" for item in dictionary_items)


def test_historical_context_uses_dictionary_evidence() -> None:
    packet = retrieve("Jn 4,1-42")
    context = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert context.selection_stats["dictionary_selected"] >= 1
    assert context.selection_stats["historical_background_selected"] >= 1
    dictionary_sections = [
        item
        for section in context.sections
        if section.type == "dictionary"
        for item in section.items
    ]
    assert dictionary_sections
    assert all(item.item_type == "dictionary_background" for item in dictionary_sections)


def test_exegesis_retains_multi_source_diversity() -> None:
    packet = retrieve("Jn 4,1-42")
    context = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    section_types = {section.type for section in context.sections}
    assert "linguistic" in section_types
    assert "exegetical" in section_types
    stats = context.selection_stats
    assert stats["study_notes_selected"] >= 5
    assert stats["linguistic_selected"] >= 1


def test_dictionary_disabled_falls_back_to_phase3b_behavior(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    base = json.loads(Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8"))
    payload = deepcopy(base)
    for source in payload["sources"]:
        if source["id"] == AQUIFER_DICTIONARY_SOURCE_ID:
            source["enabled"] = False
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    packet = retrieve("Jn 4,1-42", manifest=manifest)
    assert not any(
        item.relation_type == RELATION_DICTIONARY_BACKGROUND for item in packet.evidence_items
    )
    assert packet.build_id == PILOT_BUILD_ID_PHASE4E


def test_missing_dictionary_bundle_graceful(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    base = json.loads(Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8"))
    payload = deepcopy(base)
    for source in payload["sources"]:
        if source["id"] == AQUIFER_DICTIONARY_SOURCE_ID:
            source["enabled"] = False
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    packet = retrieve("Jn 4,1-42", manifest=manifest, entity_mode="direct_only")
    assert not any(
        item.relation_type == RELATION_DICTIONARY_BACKGROUND for item in packet.evidence_items
    )
    assert any("aquifer_open_bible_dictionary is disabled" in w for w in packet.warnings)


def test_provenance_chain_complete() -> None:
    packet = retrieve("Jn 4,1-42")
    item = next(
        entry for entry in packet.evidence_items if entry.relation_type == RELATION_DICTIONARY_BACKGROUND
    )
    meta = item.metadata
    assert meta.get("article_id")
    assert meta.get("chunk_id")
    assert meta.get("license") == AQUIFER_LICENSE
    assert meta.get("license_url")
    assert meta.get("attribution")
    assert meta.get("upstream_commit")
    assert meta.get("upstream_resource_version")


def test_hard_token_max_not_exceeded() -> None:
    packet = retrieve("Jn 4,1-42")
    exegesis = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert exegesis.estimated_tokens <= 4500
    assert historical.estimated_tokens <= 3500


@requires_aquifer_dictionary_db
def test_phase3c_golden_fixtures() -> None:
    assert PACKET_WITH_DICTIONARY.exists()
    assert EXEGESIS_PHASE3C.exists()
    assert HISTORICAL_PHASE3C.exists()
    packet = json.loads(retrieve_to_json("Jn 4,1-42"))
    assert packet["build"]["build_id"] == PILOT_BUILD_ID_PHASE4E
    dictionary_count = sum(
        1 for item in packet["evidence_items"] if item["relation_type"] == RELATION_DICTIONARY_BACKGROUND
    )
    assert dictionary_count == 66
    titles = {
        item["metadata"].get("title")
        for item in packet["evidence_items"]
        if item["relation_type"] == RELATION_DICTIONARY_BACKGROUND
    }
    assert "Abba" not in titles
    assert "Aegean Sea" not in titles

    ex = build_context_from_evidence(retrieve("Jn 4,1-42"), PROFILE_EXEGESIS).to_dict()
    hi = build_context_from_evidence(retrieve("Jn 4,1-42"), PROFILE_HISTORICAL).to_dict()
    assert ex["estimated_tokens"] <= 4500
    assert hi["estimated_tokens"] <= 3500
    assert ex["selection_stats"]["dictionary_selected"] >= 1
    assert hi["selection_stats"]["dictionary_selected"] >= 1
