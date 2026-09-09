"""Phase 2E §23 — expert-regression fixture FRAMEWORK integrity tests.

These fixtures (``tests/fixtures/hebrew_contextual_golden/``) are developer
regression candidates, not professor-approved goldens — every entry is
``reviewed_by: null`` until a real Hebrew expert reviews it (see the
manifest's own ``purpose`` field and
``docs/hebrew_analysis_v2_phase2e.md``). This test file only verifies the
framework itself is well-formed and internally consistent; it does not (and
must not) assert any AI-generated content, since none has been reviewed.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "hebrew_contextual_golden"
REQUIRED_CATEGORIES = {
    "asher_relative_particle",
    "imperative",
    "cohortative",
    "piel_hitpael_semantic_contribution",
    "construct_chain",
    "infinitive_absolute_plus_finite_verb",
    "double_negation",
    "word_order_observation",
    "ketiv_qere",
    "aramaic",
    "multi_component_structure",
    "partial_syntax_grounding",
}


def test_manifest_exists_and_lists_every_fixture_file():
    manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "unreviewed_developer_candidates"
    listed = set(manifest["fixtures"])
    on_disk = {p.name for p in FIXTURES_DIR.glob("*.json") if p.name != "manifest.json"}
    assert listed == on_disk


def test_manifest_covers_every_required_category_from_the_brief():
    manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    covered = set(manifest["categories_covered"])
    missing = REQUIRED_CATEGORIES - covered
    assert not missing, f"fixture framework is missing required categories: {missing}"


def test_every_fixture_is_marked_unreviewed_with_no_fabricated_review():
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        if path.name == "manifest.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["status"] == "unreviewed_developer_candidate", path.name
        assert data["reviewed_by"] is None, path.name
        assert data["reviewed_at"] is None, path.name
        assert data["review_notes_hu"] == "", path.name


def test_every_fixture_has_required_fields_and_non_empty_rationale():
    required_keys = {
        "fixture_version", "reference", "reference_hu", "category", "rationale",
        "covers", "fixture_backed", "fixture_path", "status", "reviewed_by",
        "reviewed_at", "review_notes_hu", "ai_constraints",
    }
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        if path.name == "manifest.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        assert required_keys.issubset(data.keys()), path.name
        assert data["rationale"].strip(), path.name
        assert data["covers"], path.name


def test_fixture_backed_entries_point_at_real_committed_fixture_files():
    repo_root = Path(__file__).resolve().parents[1]
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        if path.name == "manifest.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["fixture_backed"]:
            fixture_path = repo_root / data["fixture_path"]
            assert fixture_path.exists(), f"{path.name} claims fixture_backed but {fixture_path} is missing"
        else:
            assert data["fixture_path"] is None, path.name


def test_at_least_one_fixture_covers_partial_grounding_and_is_fixture_backed():
    """Phase 2E's most important structural regression case (§7/§22) must
    be backed by a real, importable fixture — not just a planned reference —
    so a future service-level golden test can run it without new data."""
    manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    partial_entries = [
        json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
        for name in manifest["fixtures"]
        if "partial_syntax_grounding" in json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))["covers"]
    ]
    assert partial_entries
    assert any(entry["fixture_backed"] for entry in partial_entries)
