from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

import pytest

from bible_engine.hebrew_lexicon_translation_workflow import (
    _appears_to_be_english_sentence,
    audit_tbesh_database,
    build_tbesh_language_normalization_audit,
    build_hebrew_lexicon_priority_audit,
    export_hebrew_lexicon_batch,
    import_hebrew_lexicon_batch,
)
from bible_engine.hebrew_lexicon_hu import load_hebrew_hungarian_lexicon
from bible_engine.hebrew_sqlite import import_hebrew_fixture_database


FIXTURES = Path(__file__).parent / "fixtures"
TAHOT = FIXTURES / "tahot_ruth_psa_sample.tsv"
TBESH = FIXTURES / "tbesh_ruth_psa_sample.tsv"

BATCH_DIR = Path("data/hebrew_translation_batches")

# Phase 2B — the tests below read process journals from the one-time
# historical campaign (batches 0001-0005) that built the 6,493-entry
# production lexicon: `export_hebrew_lexicon_batch()` snapshots of what still
# needed translation AT THAT POINT IN THE SEQUENCE. They were never
# committed to git (not gitignored — simply never staged), so a clean
# checkout has always lacked them; confirmed pre-existing by running the
# identical tests against a clean `git worktree` at the pre-Phase-2A commit,
# where they fail identically.
#
# They cannot be meaningfully regenerated: production is now essentially
# complete (6,493 entries, close to TBESH's full ~12,500-entry corpus), so
# re-running the exporter today no longer reproduces the "batch N excludes
# batch N-1, batch sizes 100/500/500/...” narrative these process artifacts
# recorded — it would just re-export whatever the (now much smaller) residual
# untranslated set happens to be. Regenerating fake batches to force a green
# run would fabricate history rather than testing anything real.
#
# The properties that ARE still meaningful and are actually about current
# production correctness — e.g. that specific records resolve directly, that
# Hungarian notes pass the English-sentence detector — are covered directly
# against the committed `hebrew_lexicon_hu.json` in
# test_hebrew_lexicon_hu.py and by the rewritten
# test_english_sentence_detector_accepts_current_pilot_hungarian_notes below.
requires_historical_batch_artifacts = pytest.mark.skipif(
    not BATCH_DIR.exists(),
    reason=(
        "data/hebrew_translation_batches/ holds one-time historical process "
        "journals from the lexicon translation campaign, never committed to "
        "git; not reproducible from current state (production is now "
        "essentially complete). See docs/hebrew_analysis_v2_phase2b.md."
    ),
)


def test_tbesh_audit_reports_counts_and_language_split(tmp_path: Path) -> None:
    database = _fixture_database(tmp_path)
    audit = audit_tbesh_database(database)

    assert audit["total_records"] > 0
    assert "hebrew" in audit["language_counts"]
    assert audit["duplicate_strong_records"] == 0
    assert "gloss" in audit["short_gloss_fields"]
    assert "meaning" in audit["long_guidance_fields"]


def test_priority_audit_is_deterministic_and_frequency_driven(tmp_path: Path) -> None:
    database = _fixture_database(tmp_path)
    out1 = tmp_path / "priority1.json"
    out2 = tmp_path / "priority2.json"

    first = build_hebrew_lexicon_priority_audit(out1, tahot_database_path=database, tbesh_database_path=database)
    second = build_hebrew_lexicon_priority_audit(out2, tahot_database_path=database, tbesh_database_path=database)

    first_records = [(item["strong_id"], item["priority_score"]) for item in first["records"]]
    second_records = [(item["strong_id"], item["priority_score"]) for item in second["records"]]
    assert first_records == second_records
    assert first["records"][0]["token_frequency"] >= first["records"][-1]["token_frequency"]


def test_priority_flags_proper_name_hebrew_and_aramaic(tmp_path: Path) -> None:
    database = _fixture_database(tmp_path)
    audit = build_hebrew_lexicon_priority_audit(tmp_path / "priority.json", tahot_database_path=database, tbesh_database_path=database)
    records = audit["records"]

    assert any(item["proper_name_flag"] for item in records)
    assert any(item["language"] == "hebrew" for item in records)
    # Phase 2A: this used to assert that some record is Aramaic. The fixture
    # corpus is Ruth + Psalms — 178 tokens, all Hebrew, zero Aramaic — so that
    # could only ever be satisfied because Aramaic TBESH rows ("in Aramaic of
    # H....") were indexed under the HEBREW lexeme's Strong id and hijacked it.
    # With the two-pass importer that no longer happens, and an all-Hebrew
    # passage must classify as Hebrew throughout.
    assert not any(item["language"] == "aramaic" for item in records)


def test_language_normalization_preserves_explicit_language(tmp_path: Path) -> None:
    database = _language_database(tmp_path)

    audit = build_tbesh_language_normalization_audit(tmp_path / "language.json", tahot_database_path=database, tbesh_database_path=database)
    records = {item["strong_id"]: item for item in audit["records"]}

    assert records["H0001"]["resolved_language"] == "hebrew"
    assert records["H0001"]["evidence"] == "explicit_tbesh_language"


def test_language_normalization_uses_tahot_core_occurrences_and_mixed(tmp_path: Path) -> None:
    database = _language_database(tmp_path)

    audit = build_tbesh_language_normalization_audit(tmp_path / "language.json", tahot_database_path=database, tbesh_database_path=database)
    records = {item["strong_id"]: item for item in audit["records"]}

    assert records["H0002"]["resolved_language"] == "hebrew"
    assert records["H0002"]["evidence"] == "tahot_core_token_language"
    assert records["H0002"]["hebrew_token_count"] == 1
    assert records["H0003"]["resolved_language"] == "mixed"
    assert records["H0003"]["hebrew_token_count"] == 1
    assert records["H0003"]["aramaic_token_count"] == 1


def test_language_normalization_leaves_uncertain_record_unspecified(tmp_path: Path) -> None:
    database = _language_database(tmp_path)

    audit = build_tbesh_language_normalization_audit(tmp_path / "language.json", tahot_database_path=database, tbesh_database_path=database)
    records = {item["strong_id"]: item for item in audit["records"]}

    assert records["H0004"]["resolved_language"] == "unspecified"
    assert records["H0004"]["confidence"] == "low"


def test_batch_export_contains_import_schema_and_frequency_order(tmp_path: Path) -> None:
    database = _fixture_database(tmp_path)
    output = tmp_path / "batch.json"

    report = export_hebrew_lexicon_batch(output, limit=10, tahot_database_path=database, tbesh_database_path=database)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert report.records_exported == len(data["records"])
    assert report.records_exported > 0
    assert report.records_exported <= 10
    assert data["schema_version"] == "1.0"
    assert data["translation_guidelines"]
    assert data["records"][0]["token_frequency"] >= data["records"][-1]["token_frequency"]
    assert {"strong_id", "base_meaning_hu", "possible_meanings_hu", "source_note_en"} <= set(data["records"][0])


@requires_historical_batch_artifacts
def test_pilot_batch_composition_limits_are_enforced() -> None:
    data = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0001.json").read_text(encoding="utf-8"))
    records = data["records"]
    language_counts = Counter(record.get("language") or "unspecified" for record in records)

    assert len(records) == 100
    assert language_counts["hebrew"] >= 85
    assert language_counts["aramaic"] <= 10
    assert language_counts["mixed"] + language_counts["unspecified"] <= 5
    assert sum(1 for record in records if record.get("proper_name_flag")) <= 5
    assert sum(1 for record in records if record.get("ambiguity_flag")) <= 25
    assert sum(1 for record in records if record.get("simple_lexical_flag")) >= 60
    assert all(record["source_gloss_en"] or record["source_note_en"] for record in records)
    assert all(record["token_frequency"] > 0 for record in records)


@requires_historical_batch_artifacts
def test_pilot_priority_result_is_deterministic() -> None:
    first = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0001.json").read_text(encoding="utf-8"))["records"]
    second = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0001.json").read_text(encoding="utf-8"))["records"]

    assert [record["strong_id"] for record in first] == [record["strong_id"] for record in second]


@requires_historical_batch_artifacts
def test_second_batch_excludes_first_batch_and_matches_import_state() -> None:
    first = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0001.json").read_text(encoding="utf-8"))["records"]
    second = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0002.json").read_text(encoding="utf-8"))["records"]
    production = load_hebrew_hungarian_lexicon()
    second_ids = {record["strong_id"] for record in second}

    assert len(second) == 500
    assert not (second_ids & {record["strong_id"] for record in first})
    if len(production) <= 100:
        assert not (second_ids & set(production))
    else:
        assert second_ids <= set(production)


@requires_historical_batch_artifacts
def test_second_batch_composition_and_source_quality() -> None:
    second = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0002.json").read_text(encoding="utf-8"))["records"]
    language_counts = Counter(record.get("language") or "unspecified" for record in second)

    assert len({record["strong_id"] for record in second}) == 500
    assert language_counts["hebrew"] >= 420
    assert language_counts["aramaic"] <= 50
    assert language_counts["mixed"] + language_counts["unspecified"] <= 30
    assert sum(1 for record in second if record.get("proper_name_flag")) <= 20
    assert sum(1 for record in second if record.get("ambiguity_flag")) <= 150
    assert sum(1 for record in second if record.get("simple_lexical_flag")) >= 300
    assert all(record["lemma"] for record in second)
    assert all(record["source_gloss_en"] or record["source_note_en"] for record in second)
    assert all(record["token_frequency"] > 0 for record in second)
    assert not any(record.get("technical_record_flag") for record in second)


def test_second_batch_order_is_deterministic_and_frequency_driven(tmp_path: Path) -> None:
    out1 = tmp_path / "batch2a.json"
    out2 = tmp_path / "batch2b.json"

    first = export_hebrew_lexicon_batch(out1, limit=500)
    second = export_hebrew_lexicon_batch(out2, limit=500)
    first_records = json.loads(Path(first.output_path).read_text(encoding="utf-8"))["records"]
    second_records = json.loads(Path(second.output_path).read_text(encoding="utf-8"))["records"]
    frequencies = [record["token_frequency"] for record in first_records]

    assert [record["strong_id"] for record in first_records] == [record["strong_id"] for record in second_records]
    assert frequencies == sorted(frequencies, reverse=True)


@requires_historical_batch_artifacts
def test_third_batch_excludes_previous_batches_and_matches_import_state() -> None:
    first = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0001.json").read_text(encoding="utf-8"))["records"]
    second = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0002.json").read_text(encoding="utf-8"))["records"]
    third = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0003.json").read_text(encoding="utf-8"))["records"]
    production = load_hebrew_hungarian_lexicon()
    third_ids = {record["strong_id"] for record in third}
    previous_ids = {record["strong_id"] for record in first} | {record["strong_id"] for record in second}

    assert len(third) == 1000
    assert not (third_ids & previous_ids)
    if len(production) <= 600:
        assert not (third_ids & set(production))
    else:
        assert third_ids <= set(production)


@requires_historical_batch_artifacts
def test_third_batch_composition_and_source_quality() -> None:
    third = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0003.json").read_text(encoding="utf-8"))["records"]
    language_counts = Counter(record.get("language") or "unspecified" for record in third)

    assert len({record["strong_id"] for record in third}) == 1000
    assert language_counts["hebrew"] >= 850
    assert language_counts["aramaic"] <= 100
    assert language_counts["mixed"] + language_counts["unspecified"] <= 50
    assert sum(1 for record in third if record.get("proper_name_flag")) <= 40
    assert sum(1 for record in third if record.get("ambiguity_flag")) <= 250
    assert sum(1 for record in third if record.get("simple_lexical_flag")) >= 700
    assert all(record["lemma"] for record in third)
    assert all(record["source_gloss_en"] or record["source_note_en"] for record in third)
    assert all(record["token_frequency"] > 0 for record in third)
    assert not any(record.get("technical_record_flag") for record in third)


def test_third_batch_order_is_deterministic_and_frequency_driven(tmp_path: Path) -> None:
    out1 = tmp_path / "batch3a.json"
    out2 = tmp_path / "batch3b.json"

    first = export_hebrew_lexicon_batch(out1, limit=1000)
    second = export_hebrew_lexicon_batch(out2, limit=1000)
    first_records = json.loads(Path(first.output_path).read_text(encoding="utf-8"))["records"]
    second_records = json.loads(Path(second.output_path).read_text(encoding="utf-8"))["records"]
    frequencies = [record["token_frequency"] for record in first_records]

    assert [record["strong_id"] for record in first_records] == [record["strong_id"] for record in second_records]
    assert frequencies == sorted(frequencies, reverse=True)


@requires_historical_batch_artifacts
def test_fourth_batch_excludes_previous_batches_and_production_lexicon() -> None:
    previous_records = []
    for number in ("0001", "0002", "0003"):
        previous_records.extend(json.loads(Path(f"data/hebrew_translation_batches/hebrew_lexicon_batch_{number}.json").read_text(encoding="utf-8"))["records"])
    fourth = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0004.json").read_text(encoding="utf-8"))["records"]
    production = load_hebrew_hungarian_lexicon()
    fourth_ids = {record["strong_id"] for record in fourth}
    previous_ids = {record["strong_id"] for record in previous_records}

    assert len(fourth) == 1000
    assert not (fourth_ids & previous_ids)
    if len(production) <= 1600:
        assert not (fourth_ids & set(production))
    else:
        assert fourth_ids <= set(production)


@requires_historical_batch_artifacts
def test_fourth_batch_composition_source_quality_and_preaudit_classes() -> None:
    fourth = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0004.json").read_text(encoding="utf-8"))["records"]
    language_counts = Counter(record.get("language") or "unspecified" for record in fourth)
    class_counts = Counter(record.get("preaudit_class") for record in fourth)

    assert len({record["strong_id"] for record in fourth}) == 1000
    assert language_counts["hebrew"] >= 850
    assert language_counts["aramaic"] <= 100
    assert language_counts["mixed"] + language_counts["unspecified"] <= 50
    assert sum(1 for record in fourth if record.get("proper_name_flag")) <= 50
    assert sum(1 for record in fourth if record.get("ambiguity_flag")) <= 250
    assert sum(1 for record in fourth if record.get("simple_lexical_flag")) >= 650
    assert all(record["lemma"] for record in fourth)
    assert all(record["source_gloss_en"] or record["source_note_en"] for record in fourth)
    assert all(record["token_frequency"] > 0 for record in fourth)
    assert not any(record.get("technical_record_flag") for record in fourth)
    assert not ({"technical_risk", "insufficient_source"} & set(class_counts))
    assert set(class_counts) <= {"straightforward", "contextual", "proper_name", "ambiguous"}


@requires_historical_batch_artifacts
def test_fourth_review_candidates_match_review_required_records() -> None:
    fourth = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0004.json").read_text(encoding="utf-8"))["records"]
    review = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0004_review_candidates.json").read_text(encoding="utf-8"))["records"]
    review_ids = [record["strong_id"] for record in review]
    expected_ids = [record["strong_id"] for record in fourth if record.get("review_required")]

    assert review_ids == expected_ids
    assert all(record.get("review_required") for record in review)
    assert not any(record.get("preaudit_class") in {"technical_risk", "insufficient_source"} for record in review)


def test_fourth_batch_order_is_deterministic_and_frequency_driven(tmp_path: Path) -> None:
    out1 = tmp_path / "batch4a.json"
    out2 = tmp_path / "batch4b.json"

    first = export_hebrew_lexicon_batch(out1, limit=1000)
    second = export_hebrew_lexicon_batch(out2, limit=1000)
    first_records = json.loads(Path(first.output_path).read_text(encoding="utf-8"))["records"]
    second_records = json.loads(Path(second.output_path).read_text(encoding="utf-8"))["records"]
    frequencies = [record["token_frequency"] for record in first_records]

    assert [record["strong_id"] for record in first_records] == [record["strong_id"] for record in second_records]
    assert frequencies == sorted(frequencies, reverse=True)


@requires_historical_batch_artifacts
def test_fifth_batch_excludes_previous_batches_and_production_lexicon(tmp_path: Path) -> None:
    previous_records = []
    for number in ("0001", "0002", "0003", "0004"):
        previous_records.extend(json.loads(Path(f"data/hebrew_translation_batches/hebrew_lexicon_batch_{number}.json").read_text(encoding="utf-8"))["records"])
    fifth = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0005.json").read_text(encoding="utf-8"))["records"]
    production = load_hebrew_hungarian_lexicon()
    next_export = export_hebrew_lexicon_batch(tmp_path / "batch_after_0005.json", limit=1000)
    next_records = json.loads(Path(next_export.output_path).read_text(encoding="utf-8"))["records"]
    fifth_ids = {record["strong_id"] for record in fifth}
    previous_ids = {record["strong_id"] for record in previous_records}
    next_ids = {record["strong_id"] for record in next_records}

    assert len(fifth) == 1000
    assert not (fifth_ids & previous_ids)
    assert fifth_ids <= set(production)
    assert not (fifth_ids & next_ids)


@requires_historical_batch_artifacts
def test_fifth_batch_composition_source_quality_and_preaudit_classes() -> None:
    fifth = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0005.json").read_text(encoding="utf-8"))["records"]
    language_counts = Counter(record.get("language") or "unspecified" for record in fifth)
    class_counts = Counter(record.get("preaudit_class") for record in fifth)

    assert len({record["strong_id"] for record in fifth}) == 1000
    assert language_counts["hebrew"] >= 850
    assert language_counts["aramaic"] <= 120
    assert language_counts["mixed"] + language_counts["unspecified"] <= 30
    assert sum(1 for record in fifth if record.get("proper_name_flag")) <= 70
    assert sum(1 for record in fifth if record.get("review_required")) <= 300
    assert class_counts["straightforward"] >= 600
    assert all(record["lemma"] for record in fifth)
    assert all(record["source_gloss_en"] or record["source_note_en"] for record in fifth)
    assert all(record["token_frequency"] > 0 for record in fifth)
    assert not any(record.get("technical_record_flag") for record in fifth)
    assert not ({"technical_risk", "insufficient_source"} & set(class_counts))
    assert set(class_counts) <= {"straightforward", "contextual", "proper_name", "ambiguous"}


@requires_historical_batch_artifacts
def test_fifth_review_candidates_match_review_required_records() -> None:
    fifth = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0005.json").read_text(encoding="utf-8"))["records"]
    review = json.loads(Path("data/hebrew_translation_batches/hebrew_lexicon_batch_0005_review_candidates.json").read_text(encoding="utf-8"))["records"]
    review_ids = [record["strong_id"] for record in review]
    expected_ids = [record["strong_id"] for record in fifth if record.get("review_required")]

    assert review_ids == expected_ids
    assert all(record.get("review_required") for record in review)
    assert not any(record.get("preaudit_class") in {"technical_risk", "insufficient_source"} for record in review)


def test_fifth_batch_order_is_deterministic_and_frequency_driven(tmp_path: Path) -> None:
    out1 = tmp_path / "batch5a.json"
    out2 = tmp_path / "batch5b.json"

    first = export_hebrew_lexicon_batch(out1, limit=1000)
    second = export_hebrew_lexicon_batch(out2, limit=1000)
    first_records = json.loads(Path(first.output_path).read_text(encoding="utf-8"))["records"]
    second_records = json.loads(Path(second.output_path).read_text(encoding="utf-8"))["records"]
    frequencies = [record["token_frequency"] for record in first_records]

    assert [record["strong_id"] for record in first_records] == [record["strong_id"] for record in second_records]
    assert frequencies == sorted(frequencies, reverse=True)


def test_import_accepts_valid_translated_record(tmp_path: Path) -> None:
    database = _fixture_database(tmp_path)
    batch = tmp_path / "batch.json"
    data = _batch_data(database, "H1961")
    data["records"][0]["base_meaning_hu"] = "lenni"
    data["records"][0]["possible_meanings_hu"] = ["lenni", "létezni"]
    data["records"][0]["lexical_note_hu"] = "Alapvető létigeként fordítható."
    batch.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    report = import_hebrew_lexicon_batch(batch, output_path=tmp_path / "hu.json", tbesh_database_path=database)

    assert report.records_imported == 1
    assert report.errors == ()
    output = json.loads((tmp_path / "hu.json").read_text(encoding="utf-8"))
    assert output[0]["strong_id"] == "H1961"
    assert output[0]["review_status"] == "draft"


def test_import_rejects_duplicate_mismatched_empty_english_html_and_long_fields(tmp_path: Path) -> None:
    database = _fixture_database(tmp_path)
    records = []
    good = _batch_data(database, "H1961")["records"][0]
    translated = dict(good, base_meaning_hu="lenni", possible_meanings_hu=["lenni"], lexical_note_hu="Magyar lexikai megjegyzés.")
    records.append(translated)
    records.append(dict(translated))
    records.append(dict(translated, strong_id="H9999"))
    records.append(dict(translated, base_meaning_hu=""))
    records.append(dict(translated, base_meaning_hu="the king is here"))
    records.append(dict(translated, base_meaning_hu="<b>lenni</b>"))
    records.append(dict(translated, base_meaning_hu="x" * 501))
    batch = tmp_path / "bad.json"
    batch.write_text(json.dumps({"schema_version": "1.0", "records": records}, ensure_ascii=False), encoding="utf-8")

    report = import_hebrew_lexicon_batch(batch, output_path=tmp_path / "hu.json", tbesh_database_path=database)

    assert report.records_imported == 1
    assert report.records_skipped == 6
    assert any("duplicate strong_id" in error for error in report.errors)
    assert any("not found" in error for error in report.errors)
    assert any("must not be empty" in error for error in report.errors)
    assert any("English" in error for error in report.errors)
    assert any("HTML" in error for error in report.errors)
    assert any("too long" in error for error in report.errors)


def test_import_rejects_empty_required_lexical_note(tmp_path: Path) -> None:
    database = _fixture_database(tmp_path)
    record = _batch_data(database, "H1961")["records"][0]
    record.update(base_meaning_hu="lenni", possible_meanings_hu=["lenni"], lexical_note_hu="")
    batch = tmp_path / "bad_note.json"
    batch.write_text(json.dumps({"schema_version": "1.0", "records": [record]}, ensure_ascii=False), encoding="utf-8")

    report = import_hebrew_lexicon_batch(batch, output_path=tmp_path / "hu.json", tbesh_database_path=database)

    assert report.records_imported == 0
    assert any("lexical_note_hu must not be empty" in error for error in report.errors)


def test_english_sentence_detector_accepts_current_pilot_hungarian_notes() -> None:
    # Phase 2B: rewritten against the committed production lexicon — the
    # original read the (never-committed) historical batch export
    # `hebrew_lexicon_batch_0001_hu.json`; every Strong id it referenced is
    # present in the shipped `hebrew_lexicon_hu.json` with the same field
    # shape, so the same regression check holds against the real artifact.
    production_lexicon = load_hebrew_hungarian_lexicon()
    previously_flagged = {
        "H1121G",
        "H6440G",
        "H7200G",
        "H1696G",
        "H0259",
        "H1980G",
        "H1697G",
        "H0369",
        "H4325G",
        "H6680",
        "H4672",
        "H4725",
        "H6440H",
        "H1818",
        "H1980I",
        "H1697I",
        "H7218A",
        "H0376I",
        "H3966",
        "H5439G",
        "H7272",
        "H2398",
    }

    notes = {
        strong_id: entry.lexical_note_hu
        for strong_id, entry in production_lexicon.items()
        if strong_id in previously_flagged
    }

    assert set(notes) == previously_flagged
    assert all(not _appears_to_be_english_sentence(note, "lexical_note_hu") for note in notes.values())


def test_english_sentence_detector_rejects_real_english_sentence() -> None:
    assert _appears_to_be_english_sentence("This is a Hebrew verb that means to walk.", "lexical_note_hu")
    assert _appears_to_be_english_sentence("to be", "possible_meanings_hu")


def test_english_sentence_detector_accepts_hungarian_with_technical_terms() -> None:
    text = "A qal és piel alakok szakmai jelölések; a Strong H1961 önmagában nem angol mondat."

    assert not _appears_to_be_english_sentence(text, "lexical_note_hu")


def _fixture_database(tmp_path: Path) -> Path:
    database = tmp_path / "hebrew.sqlite3"
    import_hebrew_fixture_database(TAHOT, TBESH, database)
    return database


def _batch_data(database: Path, strong_id: str) -> dict[str, object]:
    empty_hu = database.parent / "empty_hu.json"
    empty_hu.write_text("[]", encoding="utf-8")
    report = export_hebrew_lexicon_batch(
        database.parent / "export.json",
        limit=100,
        tahot_database_path=database,
        tbesh_database_path=database,
        hungarian_lexicon_path=empty_hu,
    )
    data = json.loads(Path(report.output_path).read_text(encoding="utf-8"))
    record = next(item for item in data["records"] if item["strong_id"] == strong_id)
    return {"schema_version": "1.0", "records": [record]}


def _language_database(tmp_path: Path) -> Path:
    database = tmp_path / "language.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE lexicon_entries (
                strong_id TEXT PRIMARY KEY,
                estrong TEXT,
                dstrong TEXT,
                ustrong TEXT,
                hebrew TEXT,
                transliteration TEXT,
                morph TEXT,
                gloss TEXT,
                meaning TEXT,
                language TEXT,
                source_name TEXT,
                raw_fields_json TEXT
            );
            CREATE TABLE tokens (
                stable_token_key TEXT PRIMARY KEY,
                book TEXT,
                chapter INTEGER,
                verse INTEGER,
                language TEXT
            );
            CREATE TABLE token_components (
                stable_token_key TEXT,
                component_index INTEGER,
                role TEXT,
                surface TEXT,
                strong_id TEXT,
                morphology_code TEXT,
                gloss TEXT
            );
            """
        )
        entries = [
            ("H0001", "H0001 =", "H0001", "H0001", "אָב", "av", "N:N-M", "father", "father", "hebrew"),
            ("H0002", "H0002 =", "H0002", "H0002", "בֵּן", "ben", "N:N-M", "son", "son", ""),
            ("H0003", "H0003 =", "H0003", "H0003", "מלך", "melek", "N:N-M", "king", "king", ""),
            ("H0004", "H0004 =", "H0004", "H0004", "טסט", "test", "N:N-M", "test", "test", ""),
        ]
        connection.executemany(
            """
            INSERT INTO lexicon_entries (
                strong_id, estrong, dstrong, ustrong, hebrew, transliteration, morph,
                gloss, meaning, language, source_name, raw_fields_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'fixture', '{}')
            """,
            entries,
        )
        tokens = [
            ("tok1", "Gen", 1, 1, "hebrew"),
            ("tok2", "Dan", 2, 1, "aramaic"),
            ("tok3", "Gen", 1, 2, "hebrew"),
        ]
        connection.executemany("INSERT INTO tokens VALUES (?, ?, ?, ?, ?)", tokens)
        components = [
            ("tok1", 1, "core", "בֵּן", "H0002", "HNcmsa", "son"),
            ("tok2", 1, "core", "מלך", "H0003", "ANcmsa", "king"),
            ("tok3", 1, "core", "מלך", "H0003", "HNcmsa", "king"),
        ]
        connection.executemany("INSERT INTO token_components VALUES (?, ?, ?, ?, ?, ?, ?)", components)
    return database
