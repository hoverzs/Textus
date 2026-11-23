from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pytest

from bible_engine.hymn_repository import HymnRecord, HymnRepositoryStatus
from bible_engine.hymn_repository import get_hymn_candidates as repo_get_hymn_candidates
from bible_engine.hymn_repository import get_status, validate_hymn_ids
from bible_engine.hymn_sqlite import HymnalSourceConfig, import_dtx_hymnal_database, import_hymnals_database
from hymn_recommendation_ai import (
    ERE_BOOK_LABEL,
    RE21_BOOK_LABEL,
    RE48_BOOK_LABEL,
    build_hymn_ranking_prompt,
    build_topic_search_profile,
    _collect_candidates,
    recommend_hymns,
)


ROOT = Path(__file__).resolve().parents[1]
ERE_SOURCE = ROOT / "data" / "raw" / "hymnals" / "ERE.dtx"
RE21_SOURCE = ROOT / "data" / "raw" / "hymnals" / "RE21_master.docx"
RE48_SOURCE = ROOT / "data" / "raw" / "hymnals" / "REF48_reformatus.dtx"


H1 = HymnRecord(
    hymn_id="ERE:1",
    hymnal_code="ERE",
    number=1,
    variant="",
    display_number="1",
    first_line="DB first line 1",
    title="DB title 1",
    section="",
    parent_section="",
)
H254A = HymnRecord(
    hymn_id="ERE:254a",
    hymnal_code="ERE",
    number=254,
    variant="a",
    display_number="254a",
    first_line="DB first line 254a",
    title="DB title 254a",
    section="Reformáció",
    parent_section="",
)
H254B = HymnRecord(
    hymn_id="ERE:254b",
    hymnal_code="ERE",
    number=254,
    variant="b",
    display_number="254b",
    first_line="DB first line 254b",
    title="DB title 254b",
    section="Reformáció",
    parent_section="",
)
H504 = HymnRecord(
    hymn_id="ERE:504",
    hymnal_code="ERE",
    number=504,
    variant="",
    display_number="504",
    first_line="DB first line 504",
    title="DB title 504",
    section="Kánonok",
    parent_section="Bibliaórák",
)
R1 = HymnRecord(
    hymn_id="RE21:1",
    hymnal_code="RE21",
    number=1,
    variant="",
    display_number="1",
    first_line="RE21 DB first line 1",
    title="RE21 DB title 1",
    section="Genfi zsoltárok",
    parent_section="ZSOLTÁROK",
)
R360 = HymnRecord(
    hymn_id="RE21:360",
    hymnal_code="RE21",
    number=360,
    variant="",
    display_number="360",
    first_line="Jer, lássuk az Úr keresztjét,",
    title="Jer, lássuk az Úr keresztjét,",
    section="Úrvacsora",
    parent_section="Hitünk alapjai",
)
R846 = HymnRecord(
    hymn_id="RE21:846",
    hymnal_code="RE21",
    number=846,
    variant="",
    display_number="846",
    first_line="Áldjon meg téged, áldjon az Úr",
    title="Áldjon meg téged, áldjon az Úr",
    section="Áldás",
    parent_section="Keresztyén élet",
)
R48_23 = HymnRecord(
    hymn_id="RE48:23",
    hymnal_code="RE48",
    number=23,
    variant="",
    display_number="23",
    first_line="Az Úr énnékem őriző pásztorom,",
    title="A jó Pásztor",
    section="",
    parent_section="",
)
R48_341 = HymnRecord(
    hymn_id="RE48:341",
    hymnal_code="RE48",
    number=341,
    variant="",
    display_number="341",
    first_line="Ó, Krisztusfő, te zúzott,",
    title="",
    section="",
    parent_section="",
)
R48_512 = HymnRecord(
    hymn_id="RE48:512",
    hymnal_code="RE48",
    number=512,
    variant="",
    display_number="512",
    first_line="„Szólj, szólj hozzám, Uram, mert szolgád hallja szódat!”",
    title="",
    section="",
    parent_section="",
)


class FakeRepository:
    def __init__(
        self,
        *,
        available: bool = True,
        candidates: list[HymnRecord] | None = None,
        validation_records: list[HymnRecord] | None = None,
    ) -> None:
        self.status = HymnRepositoryStatus(
            available=available,
            reason="ok" if available else "database_missing",
            database_path="fake.sqlite3",
        )
        self.candidates = candidates if candidates is not None else [H1, H254A, H254B, H504]
        self.validation_records = validation_records if validation_records is not None else self.candidates
        self.candidate_queries: list[str] = []
        self.candidate_hymnal_codes: list[tuple[str, ...]] = []
        self.validated_ids: list[str] = []

    def ensure_hymn_database(self) -> HymnRepositoryStatus:
        return self.status

    def get_status(self) -> HymnRepositoryStatus:
        return self.status

    def get_hymn_candidates(
        self,
        query: str,
        hymnal_codes: Iterable[str] | None = None,
        *,
        limit: int = 36,
    ) -> list[HymnRecord]:
        self.candidate_queries.append(query)
        codes = tuple(hymnal_codes or ())
        self.candidate_hymnal_codes.append(codes)
        if codes:
            return [h for h in self.candidates if h.hymnal_code in codes][:limit]
        return self.candidates[:limit]

    def validate_hymn_ids(self, hymn_ids: Iterable[str]) -> dict[str, HymnRecord]:
        self.validated_ids.extend(hymn_ids)
        by_id = {h.hymn_id: h for h in self.validation_records}
        return {hymn_id: by_id[hymn_id] for hymn_id in self.validated_ids if hymn_id in by_id}


class LocalDatabaseRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def ensure_hymn_database(self) -> HymnRepositoryStatus:
        return get_status(self.database_path)

    def get_status(self) -> HymnRepositoryStatus:
        return get_status(self.database_path)

    def get_hymn_candidates(
        self,
        query: str,
        hymnal_codes: Iterable[str] | None = None,
        *,
        limit: int = 36,
    ) -> list[HymnRecord]:
        return repo_get_hymn_candidates(
            query,
            hymnal_codes,
            limit=limit,
            database_path=self.database_path,
        )

    def validate_hymn_ids(self, hymn_ids: Iterable[str]) -> dict[str, HymnRecord]:
        return validate_hymn_ids(hymn_ids, database_path=self.database_path)


@pytest.fixture(scope="module")
def ere_repository(tmp_path_factory: pytest.TempPathFactory) -> LocalDatabaseRepository:
    if not ERE_SOURCE.exists():
        pytest.skip("Full ERE.dtx is local raw data")
    database = tmp_path_factory.mktemp("hymn_recommendation_quality") / "hymns.sqlite3"
    import_dtx_hymnal_database(ERE_SOURCE, database, hymnal_code="ERE")
    return LocalDatabaseRepository(database)


@pytest.fixture(scope="module")
def combined_repository(tmp_path_factory: pytest.TempPathFactory) -> LocalDatabaseRepository:
    if not (ERE_SOURCE.exists() and RE21_SOURCE.exists() and RE48_SOURCE.exists()):
        pytest.skip("Full ERE.dtx, RÉ21 DOCX, and RÉ48 DTX are local raw data")
    database = tmp_path_factory.mktemp("hymn_recommendation_re21") / "hymns.sqlite3"
    import_hymnals_database(
        (
            HymnalSourceConfig(code="ERE", source_path=ERE_SOURCE, source_format="dtx"),
            HymnalSourceConfig(
                code="RE21",
                source_path=RE21_SOURCE,
                source_format="docx",
                title="Református Énekeskönyv 2021",
            ),
            HymnalSourceConfig(
                code="RE48",
                source_path=RE48_SOURCE,
                source_format="dtx",
                title="Református Énekeskönyv (1948)",
            ),
        ),
        database,
    )
    return LocalDatabaseRepository(database)


def test_valid_candidate_ranking_uses_database_fields() -> None:
    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        hangsuly="Isten oltalma",
        repository=FakeRepository(),
        llm_generate=lambda prompt: _ranking(["ERE:254a", "ERE:1"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["ERE:254a", "ERE:1"]
    assert "ERE 254a" in result.markdown
    assert "DB first line 254a" in result.markdown
    assert "LLM invented first line" not in result.markdown


def test_false_hymn_id_is_filtered_out() -> None:
    repo = FakeRepository()

    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: _ranking(["ERE:999", "ERE:254a"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["ERE:254a"]
    assert "ERE 999" not in result.markdown
    assert "ERE:999" in repo.validated_ids


def test_display_number_and_first_line_come_from_database_not_llm() -> None:
    db_hymn = replace(H254A, display_number="254a", first_line="Canonical DB line")
    repo = FakeRepository(candidates=[db_hymn])

    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: json.dumps(
            {
                "ranked": [
                    {
                        "slot": "opening",
                        "hymn_id": "ERE:254a",
                        "number": "999",
                        "first_line": "LLM invented first line",
                        "reason": "ok",
                        "connection": "ok",
                    }
                ]
            }
        ),
    )

    assert result.status == "ok"
    assert "ERE 254a" in result.markdown
    assert "Canonical DB line" in result.markdown
    assert "999" not in result.markdown
    assert "LLM invented first line" not in result.markdown


def test_unavailable_database_returns_unavailable_without_llm_call() -> None:
    called = False

    def llm(_prompt: str) -> str:
        nonlocal called
        called = True
        return _ranking(["ERE:1"])

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(available=False),
        llm_generate=llm,
    )

    assert result.status == "database_unavailable"
    assert called is False
    assert "Nem készítek szabad LLM-alapú éneklistát" in result.markdown


def test_valid_re48_recommendation_uses_grounded_flow() -> None:
    repo = FakeRepository(candidates=[H1, R48_23, R48_341])

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=RE48_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: _ranking(["RE48:23", "RE48:341"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["RE48:23", "RE48:341"]
    assert "RE48 23" in result.markdown
    assert "Az Úr énnékem őriző pásztorom," in result.markdown
    assert all(codes == ("RE48",) for codes in repo.candidate_hymnal_codes)


def test_re48_false_hymn_id_is_filtered_out() -> None:
    repo = FakeRepository(candidates=[R48_23, R48_341])

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=RE48_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: _ranking(["RE48:999", "RE48:23"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["RE48:23"]
    assert "RE48 999" not in result.markdown
    assert "RE48:999" in repo.validated_ids


def test_re48_existing_hymn_outside_candidate_pool_is_rejected() -> None:
    repo = FakeRepository(
        candidates=[R48_23],
        validation_records=[R48_23, R48_512],
    )

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=RE48_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: _ranking(["RE48:512", "RE48:23"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["RE48:23"]
    assert "RE48 512" not in result.markdown


def test_re48_flow_rejects_ere_id_even_when_database_knows_it() -> None:
    repo = FakeRepository(
        candidates=[R48_23],
        validation_records=[H1, R48_23],
    )

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=RE48_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: _ranking(["ERE:1", "RE48:23"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["RE48:23"]
    assert "ERE 1" not in result.markdown


def test_re48_display_number_and_first_line_come_from_database_not_llm() -> None:
    repo = FakeRepository(candidates=[R48_341])

    result = recommend_hymns(
        igehely="Ézs 53,3-7",
        alkalom="Nagypénteki istentisztelet",
        enekeskonyv=RE48_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: json.dumps(
            {
                "ranked": [
                    {
                        "slot": "main",
                        "hymn_id": "RE48:341",
                        "number": "999",
                        "first_line": "LLM invented RE48 first line",
                        "title": "LLM invented title",
                        "reason": "ok",
                        "connection": "ok",
                    }
                ]
            }
        ),
    )

    assert result.status == "ok"
    assert "RE48 341" in result.markdown
    assert "Ó, Krisztusfő, te zúzott," in result.markdown
    assert "LLM invented RE48 first line" not in result.markdown
    assert "LLM invented title" not in result.markdown
    assert "999" not in result.markdown


def test_unknown_hymnal_value_remains_unavailable_without_hallucinated_fallback() -> None:
    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv="Nem létező énekeskönyv",
        repository=FakeRepository(),
        llm_generate=lambda prompt: _ranking(["ERE:1"]),
    )

    assert result.status == "unsupported_hymnal"
    assert result.recommendations == ()
    assert "még nincs validált helyi hymn adatbázis" in result.markdown


def test_valid_re21_recommendation_uses_grounded_flow() -> None:
    repo = FakeRepository(candidates=[H1, R1, R360, R846])

    result = recommend_hymns(
        igehely="1Kor 11,23-26",
        alkalom="Úrvacsorás istentisztelet",
        enekeskonyv=RE21_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: _ranking(["RE21:360", "RE21:846"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["RE21:360", "RE21:846"]
    assert "RE21 360" in result.markdown
    assert "Jer, lássuk az Úr keresztjét," in result.markdown
    assert all(codes == ("RE21",) for codes in repo.candidate_hymnal_codes)


def test_re21_false_hymn_id_is_filtered_out() -> None:
    repo = FakeRepository(candidates=[R360, R846])

    result = recommend_hymns(
        igehely="1Kor 11,23-26",
        alkalom="Úrvacsorás istentisztelet",
        enekeskonyv=RE21_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: _ranking(["RE21:999", "RE21:360"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["RE21:360"]
    assert "RE21 999" not in result.markdown
    assert "RE21:999" in repo.validated_ids


def test_re21_display_number_and_first_line_come_from_database_not_llm() -> None:
    repo = FakeRepository(candidates=[R360])

    result = recommend_hymns(
        igehely="1Kor 11,23-26",
        alkalom="Úrvacsorás istentisztelet",
        enekeskonyv=RE21_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: json.dumps(
            {
                "ranked": [
                    {
                        "slot": "main",
                        "hymn_id": "RE21:360",
                        "number": "999",
                        "first_line": "LLM invented RE21 first line",
                        "reason": "ok",
                        "connection": "ok",
                    }
                ]
            }
        ),
    )

    assert result.status == "ok"
    assert "RE21 360" in result.markdown
    assert "Jer, lássuk az Úr keresztjét," in result.markdown
    assert "LLM invented RE21 first line" not in result.markdown
    assert "999" not in result.markdown


def test_re21_hymnal_filter_excludes_ere_candidates() -> None:
    repo = FakeRepository(candidates=[H254A, R360])

    result = recommend_hymns(
        igehely="1Kor 11,23-26",
        alkalom="Úrvacsorás istentisztelet",
        enekeskonyv=RE21_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: _ranking(["ERE:254a", "RE21:360"]),
    )

    assert result.status == "ok"
    assert [item.hymn.hymn_id for item in result.recommendations] == ["RE21:360"]
    assert all(codes == ("RE21",) for codes in repo.candidate_hymnal_codes)
    assert "ERE 254a" not in result.markdown


def test_empty_candidate_list_does_not_call_llm() -> None:
    called = False

    def llm(_prompt: str) -> str:
        nonlocal called
        called = True
        return _ranking(["ERE:1"])

    result = recommend_hymns(
        igehely="semmi",
        alkalom="Egyéb",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(candidates=[]),
        llm_generate=llm,
    )

    assert result.status == "no_candidates"
    assert called is False
    assert "Nem készítek szabad LLM-alapú éneklistát" in result.markdown


def test_no_valid_ranked_hymns_does_not_fallback_to_generated_song() -> None:
    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(),
        llm_generate=lambda prompt: json.dumps(
            {
                "ranked": [
                    {
                        "slot": "opening",
                        "hymn_id": "ERE:999",
                        "reason": "Invented",
                        "connection": "Invented",
                    }
                ]
            }
        ),
    )

    assert result.status == "no_valid_ranked_hymns"
    assert result.recommendations == ()
    assert "szabad, adatbázison kívüli énekajánlást" in result.markdown
    assert "jelenleg nem elérhető" not in result.markdown


def test_llm_network_error_message_returns_ranking_unavailable() -> None:
    repo = FakeRepository()

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: "⚠️ **Nincs internetkapcsolat.** Nem sikerült elérni a Gemini API-t.",
    )

    assert result.status == "ranking_unavailable"
    assert result.recommendations == ()
    assert repo.validated_ids == []
    assert "MI-rangsorolás jelenleg nem elérhető" in result.markdown  # UI/UX-audit 2026-11-23: egységes MI-terminológia
    assert "nem adott vissza ellenőrzött hymn_id-t" not in result.markdown


def test_malformed_json_returns_ranking_unavailable_without_crash() -> None:
    repo = FakeRepository()

    result = recommend_hymns(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=repo,
        llm_generate=lambda prompt: "{not valid json",
    )

    assert result.status == "ranking_unavailable"
    assert result.recommendations == ()
    assert repo.validated_ids == []
    assert "malformed_json" in result.markdown


def test_variant_handling_keeps_ranked_variant() -> None:
    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(),
        llm_generate=lambda prompt: _ranking(["ERE:254b"]),
    )

    assert result.status == "ok"
    assert result.recommendations[0].hymn.hymn_id == "ERE:254b"
    assert result.recommendations[0].hymn.display_number == "254b"
    assert "DB first line 254b" in result.markdown


def test_mocked_llm_response_can_be_json_fenced() -> None:
    result = recommend_hymns(
        igehely="Zsolt 46",
        alkalom="Reformáció ünnepe",
        enekeskonyv=ERE_BOOK_LABEL,
        repository=FakeRepository(),
        llm_generate=lambda prompt: "```json\n" + _ranking(["ERE:254a"]) + "\n```",
    )

    assert result.status == "ok"
    assert result.recommendations[0].hymn.hymn_id == "ERE:254a"


def test_candidate_prompt_uses_unambiguous_hymn_id_fields() -> None:
    prompt = build_hymn_ranking_prompt(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        candidates=[H254A],
    )

    assert 'hymn_id="ERE:254a"' in prompt
    assert 'display_number="254a"' in prompt
    assert 'first_line="DB first line 254a"' in prompt
    assert "- ERE:254a:" not in prompt


def test_re21_candidate_prompt_uses_re21_namespace() -> None:
    prompt = build_hymn_ranking_prompt(
        igehely="1Kor 11,23-26",
        alkalom="Úrvacsorás istentisztelet",
        hangsuly="",
        candidates=[R360],
        hymnal_code="RE21",
    )

    assert "adatbázisból kapott RE21 hymn_id-k" in prompt
    assert 'hymn_id="RE21:360"' in prompt
    assert 'display_number="360"' in prompt
    assert '"hymn_id": "RE21:254a"' in prompt


def test_re48_candidate_prompt_uses_re48_namespace() -> None:
    prompt = build_hymn_ranking_prompt(
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        candidates=[R48_23],
        hymnal_code="RE48",
    )

    assert "adatbázisból kapott RE48 hymn_id-k" in prompt
    assert 'hymn_id="RE48:23"' in prompt
    assert 'display_number="23"' in prompt
    assert '"hymn_id": "RE48:254a"' in prompt


def test_topic_profile_extracts_psalm_51_repentance() -> None:
    profile = build_topic_search_profile(
        igehely="Zsolt 51,3-14",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
    )

    assert "bűnbánat" in profile.themes
    assert "Bűnbánati énekek" in profile.section_hints
    assert "Megtérés" in profile.section_hints


def test_psalm_51_candidates_are_repentance_weighted(
    ere_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        ere_repository,
        igehely="Zsolt 51,3-14",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        limit=12,
    )
    sections = [h.section for h in candidates]

    assert _count_sections(sections, {"Bűnbánati énekek", "Megtérés"}) >= 9
    assert "Karácsony" not in sections[:8]
    assert any(h.section == "Bűnbánati énekek" for h in candidates[:6])


def test_isaiah_53_candidates_prioritize_passion_sections(
    ere_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        ere_repository,
        igehely="Ézs 53,3-7",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        limit=12,
    )
    sections = [h.section for h in candidates]

    assert sections[:8] == ["Nagypéntek"] * 8
    assert _count_sections(sections[:10], {"Nagypéntek", "Nagyszombat"}) >= 9
    assert "Isten dicsérete" not in sections[:10]


def test_first_corinthians_11_candidates_prioritize_communion_section(
    ere_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        ere_repository,
        igehely="1Kor 11,23-26",
        alkalom="Úrvacsorás istentisztelet",
        hangsuly="",
        limit=12,
    )
    sections = [h.section for h in candidates]

    assert sections[:8] == ["Úrvacsorai énekek"] * 8
    assert _count_sections(sections[:10], {"Úrvacsorai énekek"}) >= 8


def test_re21_first_corinthians_11_candidates_use_re21_filter(
    combined_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        combined_repository,
        igehely="1Kor 11,23-26",
        alkalom="Úrvacsorás istentisztelet",
        hangsuly="",
        hymnal_code="RE21",
        limit=12,
    )
    sections = [h.section for h in candidates]

    assert candidates
    assert all(h.hymnal_code == "RE21" for h in candidates)
    assert sections[:8] == ["Úrvacsora"] * 8


def test_re48_psalm_23_candidates_use_re48_filter_and_lexical_trust_terms(
    combined_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        combined_repository,
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        hymnal_code="RE48",
        limit=12,
    )
    ids = [h.hymn_id for h in candidates]
    text = " ".join(h.first_line + " " + h.title for h in candidates).casefold()

    assert candidates
    assert all(h.hymnal_code == "RE48" for h in candidates)
    assert "RE48:23" in ids[:8]
    assert any(term in text for term in ("pásztor", "bizodalom", "bíznak", "őriz"))


def test_re48_psalm_51_candidates_use_repentance_lexical_terms(
    combined_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        combined_repository,
        igehely="Zsolt 51,3-14",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        hymnal_code="RE48",
        limit=12,
    )
    ids = [h.hymn_id for h in candidates]
    text = " ".join(h.first_line + " " + h.title for h in candidates).casefold()

    assert candidates
    assert all(h.hymnal_code == "RE48" for h in candidates)
    assert {"RE48:32", "RE48:51"}.intersection(ids[:8])
    assert any(term in text for term in ("bűn", "bűnbocsánat", "könyörülj", "irgalmazz"))


def test_re48_isaiah_53_candidates_use_passion_lexical_terms(
    combined_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        combined_repository,
        igehely="Ézs 53,3-7",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        hymnal_code="RE48",
        limit=12,
    )
    ids = [h.hymn_id for h in candidates]
    text = " ".join(h.first_line + " " + h.title for h in candidates).casefold()

    assert candidates
    assert all(h.hymnal_code == "RE48" for h in candidates)
    assert {"RE48:184", "RE48:230", "RE48:341"}.intersection(ids[:8])
    assert any(term in text for term in ("bárány", "kereszt", "krisztusfő"))


def test_re48_first_corinthians_11_candidates_use_communion_lexical_terms(
    combined_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        combined_repository,
        igehely="1Kor 11,23-26",
        alkalom="Úrvacsorás istentisztelet",
        hangsuly="",
        hymnal_code="RE48",
        limit=12,
    )
    ids = [h.hymn_id for h in candidates]
    text = " ".join(h.first_line + " " + h.title for h in candidates).casefold()

    assert candidates
    assert all(h.hymnal_code == "RE48" for h in candidates)
    assert {"RE48:436", "RE48:440"}.intersection(ids[:8])
    assert any(term in text for term in ("vacsora", "vér", "kenyér", "test"))


def test_re48_john_20_candidates_use_easter_lexical_terms(
    combined_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        combined_repository,
        igehely="Jn 20,1-18",
        alkalom="Húsvéti istentisztelet",
        hangsuly="",
        hymnal_code="RE48",
        limit=12,
    )
    ids = [h.hymn_id for h in candidates]
    text = " ".join(h.first_line + " " + h.title for h in candidates).casefold()

    assert candidates
    assert all(h.hymnal_code == "RE48" for h in candidates)
    assert {"RE48:185", "RE48:186", "RE48:187", "RE48:347", "RE48:353"}.intersection(ids[:8])
    assert any(term in text for term in ("húsvét", "feltámad", "sír"))


def test_psalm_23_candidates_prioritize_providence_and_trust(
    ere_repository: LocalDatabaseRepository,
) -> None:
    candidates = _collect_candidates(
        ere_repository,
        igehely="Zsolt 23",
        alkalom="Vasárnapi istentisztelet",
        hangsuly="",
        limit=12,
    )
    sections = [h.section for h in candidates]

    assert _count_sections(sections, {"Gondviselés", "Bizodalom Istenben"}) >= 10
    assert any(h.section == "Gondviselés" for h in candidates[:5])
    assert "Keresztyén élet" not in sections[:8]


def _ranking(ids: list[str]) -> str:
    slots = ["opening", "before_sermon", "main", "closing"]
    return json.dumps(
        {
            "ranked": [
                {
                    "slot": slot,
                    "hymn_id": hymn_id,
                    "reason": f"Reason for {hymn_id}",
                    "connection": f"Connection for {hymn_id}",
                }
                for slot, hymn_id in zip(slots, ids)
            ],
            "liturgical_note": "Rövid liturgiai megjegyzés.",
        }
    )


def _count_sections(sections: list[str], expected: set[str]) -> int:
    return sum(1 for section in sections if section in expected)
