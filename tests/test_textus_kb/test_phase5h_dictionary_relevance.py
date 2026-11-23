"""Phase 5H-B: dictionary retrieval relevance + passage-scope containment."""

from __future__ import annotations

from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS, PROFILE_HISTORICAL
from textus_kb.dictionary_relevance import (
    article_matches_passage_terms,
    associations_overlapping_request,
    format_source_scope,
    is_direct_dictionary_relevant,
    is_expanded_dictionary_relevant,
    labels_match,
)
from textus_kb.canonical_reference import CanonicalReference
from textus_kb.manifest import load_manifest
from textus_kb.retrieval import retrieve
from tests.local_data import requires_aquifer_dictionary_db

NOISE_TITLES = ("Abba", "Aegean Sea", "Adam (Person)")


def _dictionary_titles(packet) -> set[str]:
    return {
        str(item.metadata.get("title") or "")
        for item in packet.evidence_items
        if item.source_type == "bible_dictionary"
    }


def _selected_dictionary_titles(context) -> set[str]:
    titles: set[str] = set()
    for section in context.sections:
        if section.type != "dictionary":
            continue
        for item in section.items:
            text = item.text or ""
            title = text.split(":", 1)[0].split(" — ", 1)[0].strip()
            if title:
                titles.add(title)
    return titles


def test_labels_match_primary_headword_not_comma_alias() -> None:
    assert labels_match("Samaritans", "Samaritans")
    assert labels_match("Jew", "Jews")
    assert article_matches_passage_terms(
        title="Jacob’s Well",
        index_reference="jacobs well",
        passage_terms=["Jacob's Well"],
    )
    assert not article_matches_passage_terms(
        title="Ben Sirach, Jesus",
        index_reference="ben sirach jesus",
        passage_terms=["Jesus"],
    )


def test_rom815_association_does_not_overlap_rom828_30() -> None:
    ref = CanonicalReference.parse("Rom.8.28-30")
    overlapping = associations_overlapping_request(
        [
            {
                "start_ref": "45008015",
                "end_ref": "45008015",
                "start_ref_usfm": "ROM 8:15",
                "end_ref_usfm": "ROM 8:15",
            }
        ],
        ref,
    )
    assert overlapping == []
    assert format_source_scope(
        [
            {
                "start_ref": "45008015",
                "end_ref": "45008015",
                "start_ref_usfm": "ROM 8:15",
                "end_ref_usfm": "ROM 8:15",
            }
        ]
    ) == "Rom.8.15"


def test_john4_excludes_abba_and_aegean_from_evidence_and_selection() -> None:
    packet = retrieve("John.4.1-42")
    titles = _dictionary_titles(packet)
    assert "Abba" not in titles
    assert "Aegean Sea" not in titles
    for profile in (PROFILE_EXEGESIS, PROFILE_HISTORICAL):
        selected = _selected_dictionary_titles(build_context_from_evidence(packet, profile))
        assert "Abba" not in selected
        assert "Aegean Sea" not in selected


def test_luke10_excludes_abba_from_selected_evidence() -> None:
    packet = retrieve("Luke.10.25-37")
    titles = _dictionary_titles(packet)
    assert "Abba" not in titles
    selected = _selected_dictionary_titles(
        build_context_from_evidence(packet, PROFILE_HISTORICAL)
    )
    assert "Abba" not in selected


def test_acts2_excludes_abba_from_selected_evidence() -> None:
    packet = retrieve("Acts.2.1-13")
    titles = _dictionary_titles(packet)
    assert "Abba" not in titles
    selected = _selected_dictionary_titles(
        build_context_from_evidence(packet, PROFILE_HISTORICAL)
    )
    assert "Abba" not in selected


def test_rom8_28_30_excludes_abba_and_adam_without_relevance() -> None:
    packet = retrieve("Rom.8.28-30")
    titles = _dictionary_titles(packet)
    assert "Abba" not in titles
    assert "Adam (Person)" not in titles
    for profile in (PROFILE_EXEGESIS, PROFILE_HISTORICAL):
        selected = _selected_dictionary_titles(build_context_from_evidence(packet, profile))
        assert "Abba" not in selected
        assert "Adam (Person)" not in selected


def test_relevant_dictionary_still_selected_for_john4() -> None:
    packet = retrieve("John.4.1-42")
    titles = _dictionary_titles(packet)
    assert "Samaritans" in titles or "Sychar" in titles or "Mount Gerizim" in titles
    historical = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    selected = _selected_dictionary_titles(historical)
    assert selected
    assert not any(title in NOISE_TITLES for title in selected)


def test_exact_entity_match_still_works() -> None:
    ref = CanonicalReference.parse("John.4.1-42")
    assert is_direct_dictionary_relevant(
        reference=ref,
        title="Samaritans",
        index_reference="samaritans",
        passage_associations=[
            {
                "start_ref": "43004009",
                "end_ref": "43004009",
                "start_ref_usfm": "JHN 4:9",
                "end_ref_usfm": "JHN 4:9",
            }
        ],
        passage_terms=["Samaritans", "Sychar"],
    )
    assert is_expanded_dictionary_relevant(
        reference=ref,
        title="Lord",
        index_reference="lord",
        passage_associations=[],
        entity_name="LORD",
        match_method="content_id",
        match_confidence=1.0,
        passage_terms=["LORD"],
    )
    assert not is_expanded_dictionary_relevant(
        reference=ref,
        title="Abba",
        index_reference="abba",
        passage_associations=[
            {
                "start_ref": "45008015",
                "end_ref": "45008015",
                "start_ref_usfm": "ROM 8:15",
                "end_ref_usfm": "ROM 8:15",
            }
        ],
        entity_name="LORD",
        match_method="content_id",
        match_confidence=1.0,
        passage_terms=["LORD"],
    )


@requires_aquifer_dictionary_db
def test_source_trace_scope_is_not_rewritten_to_request() -> None:
    packet = retrieve("Rom.8.28-30")
    dict_items = [
        item for item in packet.evidence_items if item.source_type == "bible_dictionary"
    ]
    assert dict_items
    for item in dict_items:
        assert item.metadata.get("request_scope") == "Rom.8.28-30"
        source_scope = item.metadata.get("source_scope")
        if source_scope:
            assert "8.15" not in str(source_scope)
            # Source scope is derived from overlapping associations, not stamped as request.
            if item.metadata.get("overlapping_passage_associations"):
                assert item.passage == source_scope

    context = build_context_from_evidence(packet, PROFILE_HISTORICAL)
    for section in context.sections:
        if section.type != "dictionary":
            continue
        for ctx_item in section.items:
            assert ctx_item.metadata.get("request_scope") == "Rom.8.28-30"
            assert ctx_item.metadata.get("canonical_scope") == ctx_item.metadata.get(
                "source_scope"
            )

def test_empty_dictionary_path_does_not_invent_content(tmp_path) -> None:
    manifest = load_manifest()
    # Unsupported/narrow reference with no dictionary overlap should not fabricate entries.
    packet = retrieve("3John.1.1", manifest=manifest)
    titles = _dictionary_titles(packet)
    assert "Abba" not in titles
    assert all(
        item.source_type != "bible_dictionary" or item.content.strip()
        for item in packet.evidence_items
    )
    # Fail-closed: never invent LLM dictionary prose when store has nothing usable.
    invented = [
        item
        for item in packet.evidence_items
        if item.source_type == "bible_dictionary"
        and not item.metadata.get("article_id")
    ]
    assert invented == []
