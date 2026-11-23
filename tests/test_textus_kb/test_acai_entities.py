"""Tests for ACAI entity linking Phase 4A pilot integration."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from textus_kb.adapters.acai_entities import AcaiEntitiesAdapter
from textus_kb.canonical_reference import CanonicalReference
from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.entity_models import MAPPING_EXTERNAL_ID, textus_entity_id_from_acai
from textus_kb.evidence import PILOT_BUILD_ID_PHASE4D, PILOT_BUILD_ID_PHASE4E
from textus_kb.importers.acai_entities import (
    ACAI_LICENSE,
    ACAI_SOURCE_ID,
    GENERIC_ACAI_IDS,
    import_john_4_pilot,
    load_pilot_bundle,
)
from textus_kb.manifest import load_manifest
from textus_kb.retrieval import retrieve, retrieve_to_json
from tests.local_data import requires_any_aquifer_db

PILOT_BUNDLE = Path("data/kb/acai/john_4_1_42_entities.json")
PACKET_WITH_ENTITIES = Path("tests/fixtures/kb/john_4_1_42_packet_with_entities.json")
EXEGESIS_PHASE4B = Path("tests/fixtures/kb/john_4_1_42_exegesis_context_phase4b.json")
HISTORICAL_PHASE4B = Path("tests/fixtures/kb/john_4_1_42_historical_context_phase4b.json")
EXPANSION_PHASE4B = Path("tests/fixtures/kb/john_4_1_42_entity_expansion_phase4b.json")


def test_acai_manifest_source_valid() -> None:
    manifest = load_manifest()
    source = manifest.source_by_id(ACAI_SOURCE_ID)
    assert source is not None
    assert source.license == "CC-BY-SA-4.0"
    assert source.source_type == "sqlite"
    assert source.enabled is True
    assert source.required is False


def test_pilot_bundle_preserves_license_and_provenance() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    assert bundle["license"] == ACAI_LICENSE
    assert bundle["source_id"] == ACAI_SOURCE_ID
    assert bundle["upstream_commit"]
    assert bundle["attribution"]
    entity = bundle["entities"][0]
    assert entity["provenance"]["license"] == ACAI_LICENSE
    assert entity["provenance"]["upstream_commit"]


def test_deterministic_entity_ids() -> None:
    assert textus_entity_id_from_acai("place:Sychar") == "acai-place-Sychar"
    assert textus_entity_id_from_acai("person:Jesus.2") == "acai-person-Jesus.2"


def test_entity_ids_stable_across_imports(tmp_path: Path) -> None:
    first = import_john_4_pilot(
        upstream_root=Path("_upstream_audit/ACAI"),
        output_path=tmp_path / "a.json",
    )
    second = import_john_4_pilot(
        upstream_root=Path("_upstream_audit/ACAI"),
        output_path=tmp_path / "b.json",
    )
    ids_a = [item["entity_id"] for item in load_pilot_bundle(first.output_path)["entities"]]
    ids_b = [item["entity_id"] for item in load_pilot_bundle(second.output_path)["entities"]]
    assert ids_a == ids_b


def test_passage_entity_query() -> None:
    source = load_manifest().source_by_id(ACAI_SOURCE_ID)
    adapter = AcaiEntitiesAdapter(source)
    entities = adapter.entities_for_passage(CanonicalReference.parse("John.4.1-42"))
    assert entities
    assert any(entity.external_id == "place:Sychar" for entity in entities)
    assert any(entity.external_id == "group:Samaritan" for entity in entities)


def test_dictionary_entity_link_from_upstream_acai() -> None:
    source = load_manifest().source_by_id(ACAI_SOURCE_ID)
    adapter = AcaiEntitiesAdapter(source)
    linked = adapter.entities_for_dictionary_article("8121")
    assert linked
    assert linked[0].external_id == "group:Samaritan"
    assert linked[0].dictionary_relations[0]["match_method"] == "content_id"


def test_duplicate_primary_merge() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    external_ids = [entity["external_ids"]["acai"] for entity in bundle["entities"]]
    assert external_ids.count("person:Jacob.2") <= 1
    jacob = next(item for item in bundle["entities"] if item["external_ids"]["acai"].startswith("person:Jacob"))
    assert jacob["dictionary_relations"]


def test_aliases_preserved() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    sychar = next(item for item in bundle["entities"] if item["external_ids"]["acai"] == "place:Sychar")
    assert sychar["aliases"]
    assert any(alias.get("language") == "eng" for alias in sychar["aliases"])


def test_place_crosswalk_external_id() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    sychar = next(item for item in bundle["entities"] if item["external_ids"]["acai"] == "place:Sychar")
    crosswalk = sychar["place_crosswalk"]
    assert crosswalk["textus_place_id"] == "sychar"
    assert crosswalk["mapping_method"] == MAPPING_EXTERNAL_ID
    assert crosswalk["openbible_id"] == "a27b472"


def test_uncertain_place_crosswalk_not_auto_linked() -> None:
    bundle = load_pilot_bundle(PILOT_BUNDLE)
    unresolved_ids = {item["textus_place_id"] for item in bundle["unresolved_crosswalks"]}
    assert "galilee_1" in unresolved_ids
    assert "samaria_2" in unresolved_ids
    linked_place_ids = {
        entity["place_crosswalk"]["textus_place_id"]
        for entity in bundle["entities"]
        if entity.get("place_crosswalk")
    }
    assert "galilee_1" not in linked_place_ids


def test_generic_entities_flagged_not_in_context_summaries() -> None:
    packet = retrieve("Jn 4,1-42")
    context = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    entity_items = [
        item for section in context.sections if section.type == "entities" for item in section.items
    ]
    for item in entity_items:
        external_id = item.metadata.get("external_id")
        assert external_id not in GENERIC_ACAI_IDS


@requires_any_aquifer_db
def test_disabled_acai_graceful(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    base = json.loads(Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8"))
    payload = deepcopy(base)
    for source in payload["sources"]:
        if source["id"] == ACAI_SOURCE_ID:
            source["enabled"] = False
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    packet = retrieve("Jn 4,1-42", manifest=manifest)
    assert packet.entities == []
    assert packet.build_id == PILOT_BUILD_ID_PHASE4D


def test_evidence_packet_entities_populated() -> None:
    packet = retrieve("Jn 4,1-42")
    assert 19 <= len(packet.entities) <= 40
    assert packet.build_id == PILOT_BUILD_ID_PHASE4E
    first = json.loads(retrieve_to_json("Jn 4,1-42"))
    second = json.loads(retrieve_to_json("Jn 4,1-42"))
    assert first["entities"] == second["entities"]


def test_context_entity_summary_token_impact_minimal() -> None:
    packet = retrieve("Jn 4,1-42")
    exegesis = build_context_from_evidence(packet, PROFILE_EXEGESIS)
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    assert exegesis.estimated_tokens <= 4500
    assert historical.estimated_tokens <= 3500


def test_provenance_chain_complete() -> None:
    entity = retrieve("Jn 4,1-42").entities[0]
    provenance = entity["provenance"]
    assert provenance["source_id"] == ACAI_SOURCE_ID
    assert provenance["external_id"]
    assert provenance["upstream_commit"]
    assert provenance["license"] == ACAI_LICENSE


def test_phase4b_golden_fixtures() -> None:
    assert PACKET_WITH_ENTITIES.exists()
    assert EXEGESIS_PHASE4B.exists()
    assert HISTORICAL_PHASE4B.exists()
    assert EXPANSION_PHASE4B.exists()
    golden = json.loads(PACKET_WITH_ENTITIES.read_text(encoding="utf-8"))
    packet = json.loads(retrieve_to_json("Jn 4,1-42"))
    assert packet["build"]["build_id"] == PILOT_BUILD_ID_PHASE4E
    assert len(packet["entities"]) >= golden["entity_count"]

    ex = build_context_from_evidence(retrieve("Jn 4,1-42"), PROFILE_EXEGESIS).to_dict()
    hi = build_context_from_evidence(retrieve("Jn 4,1-42"), PROFILE_HISTORICAL).to_dict()
    assert ex["estimated_tokens"] <= 4500
    assert hi["estimated_tokens"] <= 3500
    expansion = json.loads(EXPANSION_PHASE4B.read_text(encoding="utf-8"))
    live_debug = retrieve("Jn 4,1-42").retrieval_debug
    assert live_debug["entity_mode"] == expansion.get("entity_mode", "direct_plus_entities")
    assert "expansion_delta" in live_debug
    delta = live_debug["expansion_delta"]
    assert isinstance(delta.get("direct_candidates"), int)
    assert isinstance(delta.get("entity_candidates"), int)
    assert isinstance(delta.get("duplicate_with_direct"), int)
    assert isinstance(delta.get("unique_entity_candidates"), int)
    assert delta["direct_candidates"] > 0
