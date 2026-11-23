"""Phase 1 quality gate regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from textus_kb.canonical_reference import CanonicalReference
from textus_kb.health import run_health_check
from textus_kb.manifest import ManifestValidationError, load_manifest
from tests.local_data import requires_aquifer_dictionary_db, requires_aquifer_study_notes_db


@pytest.mark.parametrize(
    ("raw", "book_id"),
    [
        ("Jn 4,1", "John"),
        ("1Jn 4,7", "1John"),
        ("2Jn 1,3", "2John"),
        ("3Jn 1,2", "3John"),
        ("1Kor 13,1", "1Cor"),
        ("2Kor 3,4", "2Cor"),
        ("1Jn.4.7", "1John"),
        ("Jn.4.1", "John"),
    ],
)
def test_numbered_books_resolve_unambiguously(raw: str, book_id: str) -> None:
    ref = CanonicalReference.parse(raw)
    assert ref.book_id == book_id


def test_jn_and_1jn_are_not_interchangeable() -> None:
    gospel = CanonicalReference.parse("Jn 4,1")
    epistle = CanonicalReference.parse("1Jn 4,1")
    assert gospel.book_id == "John"
    assert epistle.book_id == "1John"
    assert gospel.canonical_string() != epistle.canonical_string()


def test_psalms_hungarian_and_english() -> None:
    assert CanonicalReference.parse("Zsolt 23,1-6").canonical_string() == "Ps.23.1-6"
    assert CanonicalReference.parse("Psalm 119,1").canonical_string() == "Ps.119.1"


def test_health_paths_are_repo_relative_not_absolute() -> None:
    report = run_health_check()
    for source in report.sources:
        assert not source.path.startswith("C:\\")
        assert not source.path.startswith("/Users/")
        assert "\\" not in source.path
        assert not Path(source.path).is_absolute()


@requires_aquifer_dictionary_db
@requires_aquifer_study_notes_db
def test_disabled_ruf_missing_does_not_degrade_health(tmp_path: Path) -> None:
    manifest_path = tmp_path / "kb_manifest.json"
    base = json.loads(
        Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8")
    )
    for source in base["sources"]:
        if source["id"] == "ruf_2014_local":
            source["enabled"] = False
            source["local_path"] = "data/generated/absent_ruf.sqlite3"
    manifest_path.write_text(json.dumps(base), encoding="utf-8")

    report = run_health_check(manifest_path)
    ruf = next(item for item in report.sources if item.id == "ruf_2014_local")
    assert ruf.enabled is False
    assert ruf.available is False
    assert ruf.errors == []
    assert ruf.warnings == []
    assert report.overall_status == "ok"


def test_optional_tbesg_missing_is_degraded_not_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / "kb_manifest.json"
    base = json.loads(
        Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8")
    )
    for source in base["sources"]:
        if source["id"] == "stepbible_tbesg":
            source["local_path"] = "data/generated/missing_tbesg.sqlite3"
    manifest_path.write_text(json.dumps(base), encoding="utf-8")

    report = run_health_check(manifest_path)
    assert report.overall_status == "degraded"
    assert not report.errors
    tbesg = next(item for item in report.sources if item.id == "stepbible_tbesg")
    assert tbesg.warnings


def test_required_source_missing_is_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / "kb_manifest.json"
    base = json.loads(
        Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8")
    )
    for source in base["sources"]:
        if source["id"] == "stepbible_tagnt":
            source["local_path"] = "data/generated/missing_tagnt.sqlite3"
    manifest_path.write_text(json.dumps(base), encoding="utf-8")

    report = run_health_check(manifest_path)
    assert report.overall_status == "error"
    assert report.errors


def test_ruf_manifest_metadata_contractual() -> None:
    manifest = load_manifest()
    ruf = manifest.source_by_id("ruf_2014_local")
    assert ruf is not None
    assert ruf.enabled is False
    assert ruf.restricted is True
    assert ruf.license == "contractual-restricted"
    assert ruf.usage_note is not None


def test_malformed_manifest_json_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ManifestValidationError, match="Invalid manifest JSON"):
        load_manifest(bad)


def test_resolve_project_path_accepts_forward_slashes() -> None:
    from textus_kb.paths import resolve_project_path

    path = resolve_project_path("data/generated/tagnt_nt.sqlite3")
    assert path.name == "tagnt_nt.sqlite3"
