from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from bible_engine.hebrew_lexicon_hu import HebrewHungarianLexiconRepository, load_hebrew_hungarian_lexicon
from bible_engine.hebrew_sqlite import DEFAULT_TBESH_DATABASE_PATH
from bible_engine.hebrew_sqlite import import_hebrew_fixture_database


FIXTURES = Path(__file__).parent / "fixtures"
TAHOT = FIXTURES / "tahot_ruth_psa_sample.tsv"
TBESH = FIXTURES / "tbesh_ruth_psa_sample.tsv"


def test_loads_direct_hungarian_record(tmp_path: Path) -> None:
    database = tmp_path / "hebrew.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    lexicon = _write_hu(tmp_path, "H1961", "lenni")

    repo = HebrewHungarianLexiconRepository(lexicon, tbesh_database_path=database, alias_path=tmp_path / "missing.json")
    result = repo.lookup("H1961")

    assert result.resolution_type == "direct"
    assert result.entry is not None
    assert result.entry.base_meaning_hu == "lenni"
    assert result.review_status == "draft"
    assert result.translation_method == "ai_assisted"


def test_resolves_hungarian_alias_and_preserves_status(tmp_path: Path) -> None:
    database = tmp_path / "hebrew.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    lexicon = _write_hu(tmp_path, "H1961", "lenni", review_status="reviewed")
    aliases = tmp_path / "aliases.json"
    aliases.write_text(
        json.dumps({"H1961Z": "H1961"}),
        encoding="utf-8",
    )

    result = HebrewHungarianLexiconRepository(lexicon, tbesh_database_path=database, alias_path=aliases).lookup("H1961Z")

    assert result.resolution_type == "alias"
    assert result.resolved_strong_id == "H1961"
    assert result.review_status == "reviewed"
    assert result.warnings


def test_direct_hungarian_record_has_priority_over_alias(tmp_path: Path) -> None:
    database = tmp_path / "hebrew.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    lexicon = tmp_path / "hebrew_lexicon_hu.json"
    lexicon.write_text(
        json.dumps([_record("H1961", "lenni"), _record("H1961Z", "közvetlen")], ensure_ascii=False),
        encoding="utf-8",
    )
    aliases = tmp_path / "aliases.json"
    aliases.write_text(json.dumps({"H1961Z": "H1961"}), encoding="utf-8")

    result = HebrewHungarianLexiconRepository(lexicon, tbesh_database_path=database, alias_path=aliases).lookup("H1961Z")

    assert result.resolution_type == "direct"
    assert result.resolved_strong_id == "H1961Z"
    assert result.entry is not None
    assert result.entry.base_meaning_hu == "közvetlen"
    assert not result.warnings


def test_uses_tbesh_fallback_and_missing_state(tmp_path: Path) -> None:
    database = tmp_path / "hebrew.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    repo = HebrewHungarianLexiconRepository(empty, tbesh_database_path=database, alias_path=tmp_path / "missing.json")

    fallback = repo.lookup("H1961")
    missing = repo.lookup("H9999")

    assert fallback.resolution_type == "tbesh_fallback"
    assert fallback.tbesh_fallback is not None
    assert fallback.tbesh_fallback.entry is not None
    assert fallback.warnings
    assert missing.resolution_type == "missing"


def test_rejects_duplicate_or_invalid_production_entries(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    records = [_record("H1961", "lenni"), _record("H1961", "létezni")]
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    try:
        load_hebrew_hungarian_lexicon(path)
    except ValueError as exc:
        assert "Duplicate" in str(exc)
    else:
        raise AssertionError("duplicate Strong ID must be rejected")


def test_accepts_documented_mixed_language_record(tmp_path: Path) -> None:
    path = tmp_path / "mixed.json"
    record = _record("H1961", "lenni")
    record["language"] = "mixed"
    path.write_text(json.dumps([record], ensure_ascii=False), encoding="utf-8")

    entries = load_hebrew_hungarian_lexicon(path)

    assert entries["H1961"].language == "mixed"


# Phase 2B — the four tests below originally read development-time process
# artifacts under data/hebrew_translation_batches/ and
# data/generated/hebrew_*_audit.json: point-in-time exports and audits from
# the one-time historical campaign that built the 6,493-entry production
# lexicon. Those files were never committed (not excluded by .gitignore —
# simply never `git add`ed), so a clean checkout always lacked them; the
# resulting FileNotFoundError was a pre-existing failure unrelated to any
# Hebrew Analysis v2 change (verified against a clean `git worktree` at the
# pre-Phase-2A commit, which fails identically).
#
# Rebuilding that exact historical batch sequence is not meaningfully
# possible: production is now essentially complete (6,493 entries), so
# re-running the batch exporter no longer reproduces the same "batch N
# excludes batch N-1" narrative the original process artifacts recorded.
#
# What IS still meaningful, deterministic, and fully derivable from
# currently-committed data is the underlying CLAIM each test was ultimately
# checking: that specific production records resolve correctly at runtime.
# Rewritten below against the committed `hebrew_lexicon_hu.json` and
# `hebrew_strong_aliases.json` directly — a stronger anchor than the
# original, since those are the actual shipped artifacts, not a snapshot of
# an intermediate build step.


def test_runtime_loads_imported_pilot_records_without_fallback() -> None:
    entries = load_hebrew_hungarian_lexicon()
    aramaic_id = next(e.strong_id for e in entries.values() if e.language == "aramaic")
    mixed_id = next(e.strong_id for e in entries.values() if e.language == "mixed")
    repo = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)

    required = ["H1961", "H0776G", "H1696G", "H1697G", "H5650", "H6944G", aramaic_id, mixed_id]
    results = {strong_id: repo.lookup(strong_id) for strong_id in required}

    assert all(result.resolution_type == "direct" for result in results.values())
    assert all(result.entry is not None for result in results.values())
    assert results[aramaic_id].entry.language == "aramaic"
    assert results[mixed_id].entry.language == "mixed"


def test_all_imported_pilot_records_are_runtime_direct_hits() -> None:
    """Every committed production Hungarian record must resolve directly —
    none may silently fall back to the bare TBESH English entry or resolve
    as missing. Stronger than the original (which sampled one 100-record
    historical batch): this checks the entire shipped lexicon."""
    entries = load_hebrew_hungarian_lexicon()
    repo = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)
    results = [repo.lookup(strong_id) for strong_id in entries]

    assert len(results) == 6493
    assert sum(result.resolution_type == "direct" for result in results) == 6493
    assert not any(result.resolution_type == "tbesh_fallback" for result in results)
    assert not any(result.resolution_type == "missing" for result in results)


def test_post_0008_missing_id_audit_promotes_only_safe_alias() -> None:
    """Regression anchor for the specific H0430J alias the original
    "post-0008 missing id" audit run promoted, verified directly against the
    committed alias file and a live lookup rather than the (uncommitted)
    historical audit snapshot."""
    aliases = json.loads(Path("bible_engine/data/hebrew_strong_aliases.json").read_text(encoding="utf-8"))
    assert aliases["H0430J"] == "H0430G"

    repo = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)
    resolved = repo.lookup("H0430J")
    assert resolved.resolution_type == "alias"
    assert resolved.resolved_strong_id == "H0430G"
    assert resolved.entry is not None


def test_missing_id_translation_import_resolves_all_remaining_missing_ids() -> None:
    repo = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)
    expected = {
        "H1247G": "leszármazott",
        "H1247H": "fiatal állat",
        "H1247I": "valaminek a fia",
        "H1247J": "fiú",
        "H1940G": "Hódijjá",
        "H3243G": "szopik",
        "H3243H": "szoptat",
        "H3243I": "dajka",
        "H3243J": "csecsemő",
        "H3431G": "Jisbáh",
        "H5892I": "város",
        "H7417I": "Rimmón",
    }

    results = {strong_id: repo.lookup(strong_id) for strong_id in expected}
    aliases = json.loads(Path("bible_engine/data/hebrew_strong_aliases.json").read_text(encoding="utf-8"))
    production_lexicon = load_hebrew_hungarian_lexicon()

    assert len(production_lexicon) == 6493
    assert len(aliases) == 127
    assert all(result.resolution_type == "direct" for result in results.values())
    assert all(result.entry is not None for result in results.values())
    assert {strong_id: result.entry.base_meaning_hu for strong_id, result in results.items() if result.entry} == expected


def test_demo_lexical_panel_uses_hungarian_record_without_english_fallback(monkeypatch) -> None:
    import hebrew_text_demo

    calls: list[tuple[str, str]] = []

    class FakeStreamlit:
        def markdown(self, text: str) -> None:
            calls.append(("markdown", text))

        def caption(self, text: str) -> None:
            calls.append(("caption", text))

        def info(self, text: str) -> None:
            calls.append(("info", text))

        def warning(self, text: str) -> None:
            calls.append(("warning", text))

    hu_entry = SimpleNamespace(
        base_meaning_hu="lenni",
        possible_meanings_hu=("lenni", "válni"),
        lexical_note_hu="Magyar lexikai megjegyzés.",
        review_status="draft",
        translation_method="ai_assisted",
        source="STEPBible TBESH alapján készített magyar munkaváltozat",
    )
    hu_lookup = SimpleNamespace(entry=hu_entry, warnings=())
    tbesh_lookup = SimpleNamespace(core=SimpleNamespace(entry=SimpleNamespace(gloss="to be", meaning="English fallback")))
    monkeypatch.setattr(hebrew_text_demo, "st", FakeStreamlit())

    hebrew_text_demo.render_lexical_panel(hu_lookup, tbesh_lookup)
    rendered = "\n".join(text for _, text in calls)

    assert "Alapjelentés" in rendered
    assert "Lehetséges jelentések" in rendered
    assert "Lexikai megjegyzés" in rendered
    assert "Ellenőrzési állapot" in rendered
    assert "Forrás" in rendered
    assert "angol TBESH fallback" not in rendered
    assert "English fallback" not in rendered


def test_demo_lexical_panel_shows_hungarian_alias_warning(monkeypatch) -> None:
    import hebrew_text_demo

    calls: list[tuple[str, str]] = []

    class FakeStreamlit:
        def markdown(self, text: str) -> None:
            calls.append(("markdown", text))

        def caption(self, text: str) -> None:
            calls.append(("caption", text))

        def info(self, text: str) -> None:
            calls.append(("info", text))

        def warning(self, text: str) -> None:
            calls.append(("warning", text))

    hu_entry = SimpleNamespace(
        base_meaning_hu="lenni",
        possible_meanings_hu=("lenni",),
        lexical_note_hu="",
        review_status="draft",
        translation_method="ai_assisted",
        source="STEPBible TBESH alapján készített magyar munkaváltozat",
    )
    hu_lookup = SimpleNamespace(
        entry=hu_entry,
        warnings=("Magyar lexikai rekord alias alapján: H1961Z → H1961",),
    )
    tbesh_lookup = SimpleNamespace(core=SimpleNamespace(entry=None))
    monkeypatch.setattr(hebrew_text_demo, "st", FakeStreamlit())

    hebrew_text_demo.render_lexical_panel(hu_lookup, tbesh_lookup)
    rendered = "\n".join(text for _, text in calls)

    assert "Magyar lexikai rekord alias alapján: H1961Z → H1961" in rendered


def _write_hu(tmp_path: Path, strong_id: str, base: str, *, review_status: str = "draft") -> Path:
    path = tmp_path / "hebrew_lexicon_hu.json"
    path.write_text(
        json.dumps([_record(strong_id, base, review_status=review_status)], ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _record(strong_id: str, base: str, *, review_status: str = "draft") -> dict[str, object]:
    return {
        "strong_id": strong_id,
        "lemma": "הָיָה",
        "transliteration": "ha.yah",
        "language": "hebrew",
        "base_meaning_hu": base,
        "possible_meanings_hu": [base],
        "lexical_note_hu": "",
        "source_gloss_en": "to be",
        "source_note_en": "to be",
        "translation_method": "ai_assisted",
        "review_status": review_status,
        "source": "STEPBible TBESH alapján készített magyar munkaváltozat",
        "source_record_id": strong_id,
        "aliases": [],
        "warnings": [],
    }
