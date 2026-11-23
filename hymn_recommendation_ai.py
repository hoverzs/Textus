"""Database-grounded hymn recommendation flow.

The LLM may rank known hymn IDs and write pastoral reasons, but hymn numbers,
display numbers, first lines, and titles always come from `hymn_repository`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol
import unicodedata

from bible_engine.hymn_repository import (
    HymnRecord,
    HymnRepositoryStatus,
    ensure_hymn_database,
    get_hymn_candidates,
    get_status,
    validate_hymn_ids,
)


ERE_BOOK_LABEL = "Erdélyi Református Énekeskönyv"
RE21_BOOK_LABEL = "Református Énekeskönyv (2021)"
RE48_BOOK_LABEL = "Református Énekeskönyv (1948)"
ERE_HYMNAL_CODE = "ERE"
RE21_HYMNAL_CODE = "RE21"
RE48_HYMNAL_CODE = "RE48"
SUPPORTED_HYMNAL_LABELS = {ERE_BOOK_LABEL, RE21_BOOK_LABEL, RE48_BOOK_LABEL}
HYMNAL_CODE_BY_LABEL = {
    ERE_BOOK_LABEL: ERE_HYMNAL_CODE,
    RE21_BOOK_LABEL: RE21_HYMNAL_CODE,
    RE48_BOOK_LABEL: RE48_HYMNAL_CODE,
}
DEFAULT_CANDIDATE_LIMIT = 36

SECTION_EXACT_WEIGHT = 120
SECTION_FUZZY_WEIGHT = 90
TITLE_OR_FIRST_LINE_WEIGHT = 60
THEME_WEIGHT = 40
KEYWORD_WEIGHT = 30
GENERIC_WEIGHT = 8
MAX_PER_SECTION_IN_POOL = 8

LITURGICAL_SLOTS = (
    ("opening", "Kezdőének"),
    ("before_sermon", "Prédikáció előtti ének"),
    ("main", "Főének"),
    ("closing", "Záróének"),
)

_OCCASION_KEYWORDS = {
    "Úrvacsorás istentisztelet": ("úrvacsora", "Krisztus vére", "bűnbocsánat", "asztal"),
    "Adventi istentisztelet": ("advent", "eljövetel", "várakozás", "reménység"),
    "Karácsonyi istentisztelet": ("karácsony", "született", "Betlehem", "testté lett"),
    "Nagyhét": ("szenvedés", "kereszt", "Krisztus", "megváltás"),
    "Nagypénteki istentisztelet": ("kereszt", "szenvedés", "halál", "vére"),
    "Húsvéti istentisztelet": ("feltámadás", "él", "győzelem", "húsvét"),
    "Pünkösdi istentisztelet": ("Szentlélek", "Lélek", "pünkösd", "tűz"),
    "Reformáció ünnepe": ("erős vár", "ige", "hit", "kegyelem"),
    "Temetés": ("vigasztalás", "feltámadás", "örök élet", "reménység"),
    "Esküvő": ("szeretet", "áldás", "hűség", "szövetség"),
    "Keresztelő": ("szövetség", "gyermek", "áldás", "kegyelem"),
    "Konfirmáció": ("hit", "követés", "fogadás", "Szentlélek"),
    "Bűnbánati istentisztelet": ("bűnbánat", "irgalom", "kegyelem", "megtérés"),
    "Hétközi alkalom / Bibliaóra": ("ige", "tanítás", "követés", "hit"),
    "Ifjúsági istentisztelet": ("követés", "hit", "öröm", "ifjúság"),
}

_LEXICAL_EXPANSIONS = {
    "úrvacsora": ("vacsora", "kenyér", "bor", "test", "vér", "asztal"),
    "urvacsora": ("vacsora", "kenyér", "bor", "test", "vér", "asztal"),
    "úrvacsorai énekek": ("vacsora", "kenyér", "bor", "test", "vér", "asztal"),
    "krisztus vére": ("vér", "véred", "vére", "bűnbocsánat"),
    "krisztus teste": ("test", "kenyér"),
    "nagypéntek": ("kereszt", "szenvedés", "szenved", "halál", "bárány", "vér"),
    "passió": ("kereszt", "szenvedés", "szenved", "halál", "bárány", "vér"),
    "krisztus szenvedése": ("kereszt", "szenvedés", "szenved", "halál", "bárány"),
    "szenvedő szolga": ("szenvedés", "szenved", "bárány", "halál"),
    "bűnbánat": ("bűn", "vétkét", "vétkem", "irgalom", "könyörülj", "bocsásd", "kegyelmezz"),
    "bunbanat": ("bűn", "vétkét", "vétkem", "irgalom", "könyörülj", "bocsásd", "kegyelmezz"),
    "bűnbocsánat": ("bűn", "bocsánat", "bocsásd", "irgalom", "könyörülj"),
    "megtérés": ("térj", "téríts", "új szív", "bűn", "kegyelem"),
    "bizalom": ("pásztor", "őriz", "őriző", "bíznak", "bíztunk", "bizodalom", "oltalom"),
    "gondviselés": ("pásztor", "őriz", "vezet", "oltalom", "nyugalom", "bizodalom"),
    "húsvét": ("húsvét", "feltámad", "feltámadott", "feltámadás", "él", "sír", "halál"),
    "feltámadás": ("feltámad", "feltámadott", "él", "sír", "halál", "győzelem"),
}


@dataclass(frozen=True)
class HymnTopicSearchProfile:
    themes: tuple[str, ...] = ()
    liturgical_tags: tuple[str, ...] = ()
    christological_tags: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    section_hints: tuple[str, ...] = ()


class HymnRepositoryPort(Protocol):
    def ensure_hymn_database(self) -> HymnRepositoryStatus: ...
    def get_status(self) -> HymnRepositoryStatus: ...
    def get_hymn_candidates(
        self,
        query: str,
        hymnal_codes: Iterable[str] | None = None,
        *,
        limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> list[HymnRecord]: ...
    def validate_hymn_ids(self, hymn_ids: Iterable[str]) -> dict[str, HymnRecord]: ...


@dataclass(frozen=True)
class RecommendedHymn:
    slot_key: str
    slot_label: str
    hymn: HymnRecord
    reason: str
    connection: str


@dataclass(frozen=True)
class HymnRecommendationResult:
    status: str
    markdown: str
    recommendations: tuple[RecommendedHymn, ...] = ()
    repository_status: HymnRepositoryStatus | None = None
    candidate_count: int = 0

    @property
    def available(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class _RankingParseResult:
    status: str
    items: tuple["_RankedItem", ...] = ()
    reason: str = ""


class DefaultHymnRepositoryAdapter:
    def ensure_hymn_database(self) -> HymnRepositoryStatus:
        return ensure_hymn_database()

    def get_status(self) -> HymnRepositoryStatus:
        return get_status()

    def get_hymn_candidates(
        self,
        query: str,
        hymnal_codes: Iterable[str] | None = None,
        *,
        limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> list[HymnRecord]:
        return get_hymn_candidates(query, hymnal_codes, limit=limit)

    def validate_hymn_ids(self, hymn_ids: Iterable[str]) -> dict[str, HymnRecord]:
        return validate_hymn_ids(hymn_ids)


def recommend_hymns(
    *,
    igehely: str,
    alkalom: str,
    enekeskonyv: str,
    hangsuly: str = "",
    llm_generate: Callable[[str], str],
    repository: HymnRepositoryPort | None = None,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> HymnRecommendationResult:
    book = (enekeskonyv or "").strip()
    hymnal_code = HYMNAL_CODE_BY_LABEL.get(book)
    if hymnal_code is None:
        return HymnRecommendationResult(
            status="unsupported_hymnal",
            markdown=_unsupported_hymnal_markdown(book),
        )

    repo = repository or DefaultHymnRepositoryAdapter()
    status = repo.ensure_hymn_database()
    if not status.available:
        return HymnRecommendationResult(
            status="database_unavailable",
            markdown=_unavailable_markdown(status),
            repository_status=status,
        )

    candidates = _collect_candidates(
        repo,
        igehely=igehely,
        alkalom=alkalom,
        hangsuly=hangsuly,
        hymnal_code=hymnal_code,
        limit=candidate_limit,
    )
    if not candidates:
        return HymnRecommendationResult(
            status="no_candidates",
            markdown=(
                f"⚠️ **Nem találtam ellenőrzött {hymnal_code} énekjelöltet a helyi énekadatbázisban.**\n\n"
                "Nem készítek szabad LLM-alapú éneklistát, mert az énekszám és a kezdősor "
                "csak validált adatbázisrekordból származhat."
            ),
            repository_status=status,
        )

    prompt = build_hymn_ranking_prompt(
        igehely=igehely,
        alkalom=alkalom,
        hangsuly=hangsuly,
        candidates=candidates,
        hymnal_code=hymnal_code,
    )
    raw = llm_generate(prompt)
    parsed = _parse_ranked_response(raw)
    if parsed.status != "ok":
        return HymnRecommendationResult(
            status="ranking_unavailable",
            markdown=_ranking_unavailable_markdown(parsed.reason),
            repository_status=status,
            candidate_count=len(candidates),
        )

    ranked = list(parsed.items)
    valid_by_id = repo.validate_hymn_ids(item.hymn_id for item in ranked)
    recommendations = _compose_recommendations(ranked, valid_by_id, candidates)
    if not recommendations:
        return HymnRecommendationResult(
            status="no_valid_ranked_hymns",
            markdown=(
                "⚠️ **Az MI-rangsorolás nem adott vissza ellenőrzött hymn_id-t.**\n\n"
                "A hibás vagy nem létező azonosítókat eldobtam, és nem készítek "
                "szabad, adatbázison kívüli énekajánlást."
            ),
            repository_status=status,
            candidate_count=len(candidates),
        )

    return HymnRecommendationResult(
        status="ok",
        markdown=_format_recommendations_markdown(recommendations, _liturgical_note(raw)),
        recommendations=tuple(recommendations),
        repository_status=status,
        candidate_count=len(candidates),
    )


def build_hymn_ranking_prompt(
    *,
    igehely: str,
    alkalom: str,
    hangsuly: str,
    candidates: list[HymnRecord],
    hymnal_code: str = ERE_HYMNAL_CODE,
) -> str:
    candidate_lines = "\n".join(
        f'- hymn_id="{h.hymn_id}"'
        f' | display_number="{h.display_number}"'
        f' | first_line="{h.first_line}"'
        + (f' | title="{h.title}"' if h.title and h.title != h.first_line else "")
        + (f' | section="{h.section}"' if h.section else "")
        for h in candidates
    )
    return f"""\
Te református liturgiai szerkesztő vagy. Nem adhatsz meg énekszámot,
kezdősort vagy címet saját tudásból.

Feladat: az alábbi, adatbázisból kapott {hymnal_code} hymn_id-k közül válassz ki
legfeljebb négyet a liturgiai ívre. Csak a felsorolt hymn_id-kat használhatod.
Ha egy hymn_id nincs a listában, tilos szerepeltetni.

Igeszakasz: {igehely}
Alkalom: {alkalom}
Prédikációs / teológiai hangsúly: {hangsuly.strip() or "nincs külön megadva"}

Jelöltek:
{candidate_lines}

Válaszolj kizárólag JSON objektummal, ebben az alakban:
{{
  "ranked": [
    {{
      "slot": "opening|before_sermon|main|closing",
      "hymn_id": "{hymnal_code}:254a",
      "reason": "1-2 magyar mondat",
      "connection": "1 magyar mondat"
    }}
  ],
  "liturgical_note": "opcionális, rövid magyar megjegyzés"
}}

Ne írj markdown-t. Ne írj énekszámot. Ne írj kezdősort. Csak hymn_id-t
rangsorolj és indoklást adj.
"""


@dataclass(frozen=True)
class _WeightedQuery:
    term: str
    role: str
    weight: int


@dataclass(frozen=True)
class _RankedItem:
    slot: str
    hymn_id: str
    reason: str
    connection: str


def _collect_candidates(
    repo: HymnRepositoryPort,
    *,
    igehely: str,
    alkalom: str,
    hangsuly: str,
    limit: int,
    hymnal_code: str = ERE_HYMNAL_CODE,
) -> list[HymnRecord]:
    profile = build_topic_search_profile(igehely=igehely, alkalom=alkalom, hangsuly=hangsuly)
    return _collect_weighted_candidates(repo, profile, hymnal_code=hymnal_code, limit=limit)


def build_topic_search_profile(
    *,
    igehely: str,
    alkalom: str,
    hangsuly: str = "",
) -> HymnTopicSearchProfile:
    text = " ".join([igehely or "", alkalom or "", hangsuly or ""])
    folded = _fold(text)
    themes: list[str] = []
    liturgical: list[str] = []
    christological: list[str] = []
    keywords: list[str] = []
    sections: list[str] = []

    def add(
        *,
        theme: Iterable[str] = (),
        liturgy: Iterable[str] = (),
        christology: Iterable[str] = (),
        keyword: Iterable[str] = (),
        section: Iterable[str] = (),
    ) -> None:
        themes.extend(theme)
        liturgical.extend(liturgy)
        christological.extend(christology)
        keywords.extend(keyword)
        sections.extend(section)

    if _has_any(folded, ("zsolt51", "zsolt 51", "psalm51", "psa51")):
        add(
            theme=("bűnbánat", "bűnbocsánat", "megtérés", "megtisztulás"),
            liturgy=("bűnbánat",),
            keyword=("irgalom", "tisztíts meg", "új szív", "bűneim", "könyörülj"),
            section=("Bűnbánati énekek", "Megtérés", "Könyörgések"),
        )
    if _has_any(folded, ("ezs53", "ezs 53", "ézs53", "ézs 53", "isa53", "isa 53")):
        add(
            theme=("szenvedés", "engesztelés", "megváltás", "bűnhordozás"),
            liturgy=("nagypéntek", "passió"),
            christology=("szenvedő Szolga", "Krisztus szenvedése"),
            keyword=("megsebesíttetett", "bárány", "kereszt", "szenvedés", "váltság"),
            section=("Nagypéntek", "Nagyszombat"),
        )
    if _has_any(folded, ("1kor11", "1kor 11", "ikor11", "i kor 11", "1cor11", "1cor 11")):
        add(
            theme=("úrvacsora", "Krisztus halála", "szövetség", "közösség"),
            liturgy=("úrvacsora",),
            christology=("Krisztus vére", "Krisztus teste"),
            keyword=("úrvacsora", "Krisztus vére", "asztal", "bűnbocsánat", "szövetség"),
            section=("Úrvacsorai énekek",),
        )
    if _has_any(folded, ("jn20", "jn 20", "janos20", "janos 20", "jános20", "jános 20", "john20", "john 20")):
        add(
            theme=("feltámadás", "húsvét", "győzelem", "élet"),
            liturgy=("húsvét",),
            christology=("feltámadott Krisztus",),
            keyword=("feltámad", "feltámadott", "sír", "él", "halál", "győzelem"),
            section=("Húsvét",),
        )
    if _has_any(folded, ("zsolt23", "zsolt 23", "psalm23", "psa23")):
        add(
            theme=("gondviselés", "bizalom", "vezetés", "oltalom"),
            liturgy=(),
            keyword=("pásztor", "juh", "vezet", "nyugalom", "oltalom", "bizodalom"),
            section=("Gondviselés", "Bizodalom Istenben", "Könyörgések"),
        )

    occasion_keywords = _OCCASION_KEYWORDS.get(alkalom, ())
    if occasion_keywords:
        keywords.extend(occasion_keywords)
        if "Úrvacsorás" in alkalom:
            sections.append("Úrvacsorai énekek")
            liturgical.append("úrvacsora")
        elif "Nagypéntek" in alkalom or "Nagyhét" in alkalom:
            sections.append("Nagypéntek")
            liturgical.append("nagypéntek")
        elif "Húsvét" in alkalom:
            sections.append("Húsvét")
            liturgical.append("húsvét")
        elif "Pünkösd" in alkalom:
            sections.append("Pünkösd, könyörgés Szentlélekért")
            liturgical.append("pünkösd")
        elif "Reformáció" in alkalom:
            sections.append("Reformáció")
            liturgical.append("reformáció")
        elif "Temetés" in alkalom:
            sections.extend(("Temetési énekek", "Élet, halál, örök élet"))
            liturgical.append("temetés")

    keywords.extend(_meaningful_phrases(hangsuly))
    keywords.extend(_meaningful_phrases(igehely))
    if not any((themes, liturgical, christological, sections)):
        keywords.extend(("kegyelem", "hit", "Krisztus", "irgalom", "dicsőség", "reménység"))

    return HymnTopicSearchProfile(
        themes=tuple(_unique_terms(themes)),
        liturgical_tags=tuple(_unique_terms(liturgical)),
        christological_tags=tuple(_unique_terms(christological)),
        keywords=tuple(_unique_terms(keywords)),
        section_hints=tuple(_unique_terms(sections)),
    )


def _collect_weighted_candidates(
    repo: HymnRepositoryPort,
    profile: HymnTopicSearchProfile,
    *,
    hymnal_code: str = ERE_HYMNAL_CODE,
    limit: int,
) -> list[HymnRecord]:
    records: dict[str, HymnRecord] = {}
    scores: dict[str, int] = {}
    matched_roles: dict[str, set[str]] = {}
    queries = _weighted_queries(profile)
    per_query_limit = max(12, min(limit, 24))
    for query in queries:
        for index, hymn in enumerate(
            repo.get_hymn_candidates(query.term, [hymnal_code], limit=per_query_limit)
        ):
            records.setdefault(hymn.hymn_id, hymn)
            score = query.weight + max(0, 12 - index)
            score += _field_match_bonus(hymn, query.term, query.role)
            scores[hymn.hymn_id] = scores.get(hymn.hymn_id, 0) + score
            matched_roles.setdefault(hymn.hymn_id, set()).add(query.role)

    ordered = sorted(
        records.values(),
        key=lambda hymn: (
            -_section_match_priority(hymn, matched_roles),
            -scores.get(hymn.hymn_id, 0),
            hymn.section,
            hymn.number,
            hymn.variant,
        ),
    )
    return _diversify_candidates(ordered, limit=limit)


def _section_match_priority(hymn: HymnRecord, matched_roles: dict[str, set[str]]) -> int:
    roles = matched_roles.get(hymn.hymn_id, set())
    if hymn.section and roles.intersection({"section_exact", "section_fuzzy"}):
        return 1
    return 0


def _weighted_queries(profile: HymnTopicSearchProfile) -> list[_WeightedQuery]:
    queries: list[_WeightedQuery] = []
    for term in profile.section_hints:
        queries.append(_WeightedQuery(term, "section_exact", SECTION_EXACT_WEIGHT))
        queries.extend(_expanded_queries(term, "keyword", TITLE_OR_FIRST_LINE_WEIGHT))
    for term in profile.liturgical_tags:
        queries.append(_WeightedQuery(term, "section_fuzzy", SECTION_FUZZY_WEIGHT))
        queries.extend(_expanded_queries(term, "keyword", TITLE_OR_FIRST_LINE_WEIGHT))
    for term in profile.themes:
        queries.append(_WeightedQuery(term, "theme", THEME_WEIGHT))
        queries.extend(_expanded_queries(term, "keyword", KEYWORD_WEIGHT))
    for term in profile.christological_tags:
        queries.append(_WeightedQuery(term, "theme", THEME_WEIGHT))
        queries.extend(_expanded_queries(term, "keyword", KEYWORD_WEIGHT))
    for term in profile.keywords:
        queries.append(_WeightedQuery(term, "keyword", KEYWORD_WEIGHT))
        queries.extend(_expanded_queries(term, "keyword", max(KEYWORD_WEIGHT - 5, GENERIC_WEIGHT)))
    queries.extend(
        _WeightedQuery(term, "generic", GENERIC_WEIGHT)
        for term in ("kegyelem", "hit", "Krisztus", "irgalom", "dicsőség", "reménység")
    )
    unique: list[_WeightedQuery] = []
    seen: set[tuple[str, str]] = set()
    for query in queries:
        clean = re.sub(r"\s+", " ", query.term or "").strip()
        if len(clean) < 3:
            continue
        key = (_fold(clean), query.role)
        if key not in seen:
            seen.add(key)
            unique.append(_WeightedQuery(clean, query.role, query.weight))
    return unique


def _expanded_queries(term: str, role: str, weight: int) -> list[_WeightedQuery]:
    folded = _fold(term)
    expanded: list[_WeightedQuery] = []
    for key, values in _LEXICAL_EXPANSIONS.items():
        folded_key = _fold(key)
        if folded_key and (folded == folded_key or folded_key in folded or folded in folded_key):
            expanded.extend(_WeightedQuery(value, role, weight) for value in values)
    return expanded


def _field_match_bonus(hymn: HymnRecord, term: str, role: str) -> int:
    folded_term = _fold(term)
    section = _fold(hymn.section)
    title = _fold(hymn.title)
    first_line = _fold(hymn.first_line)
    if role == "section_exact" and section == folded_term:
        return SECTION_EXACT_WEIGHT
    if role in {"section_exact", "section_fuzzy"} and folded_term and folded_term in section:
        return SECTION_FUZZY_WEIGHT
    if folded_term and (folded_term in title or folded_term in first_line):
        return TITLE_OR_FIRST_LINE_WEIGHT
    return 0


def _diversify_candidates(candidates: list[HymnRecord], *, limit: int) -> list[HymnRecord]:
    selected: list[HymnRecord] = []
    section_counts: dict[str, int] = {}
    deferred: list[HymnRecord] = []
    for hymn in candidates:
        section_key = hymn.section or "<no-section>"
        if section_counts.get(section_key, 0) < MAX_PER_SECTION_IN_POOL:
            selected.append(hymn)
            section_counts[section_key] = section_counts.get(section_key, 0) + 1
        else:
            deferred.append(hymn)
        if len(selected) >= limit:
            return selected
    for hymn in deferred:
        if len(selected) >= limit:
            break
        selected.append(hymn)
    return selected


def _search_terms(*, igehely: str, alkalom: str, hangsuly: str) -> list[str]:
    terms: list[str] = []
    terms.extend(_OCCASION_KEYWORDS.get(alkalom, ()))
    terms.extend(_meaningful_phrases(hangsuly))
    terms.extend(_meaningful_phrases(igehely))
    terms.extend(("kegyelem", "hit", "Krisztus", "irgalom", "dicsőség", "reménység"))
    unique: list[str] = []
    for term in terms:
        clean = re.sub(r"\s+", " ", term or "").strip()
        if len(clean) >= 3 and clean.casefold() not in {t.casefold() for t in unique}:
            unique.append(clean)
    return unique


def _unique_terms(terms: Iterable[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean = re.sub(r"\s+", " ", term or "").strip()
        folded = _fold(clean)
        if len(clean) >= 3 and folded not in seen:
            seen.add(folded)
            unique.append(clean)
    return unique


def _has_any(folded_text: str, needles: Iterable[str]) -> bool:
    return any(_fold(needle) in folded_text for needle in needles)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", without_marks.casefold())


def _meaningful_phrases(text: str) -> list[str]:
    clean = re.sub(r"[^\w\sáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]", " ", text or "", flags=re.UNICODE)
    words = [w for w in clean.split() if len(w) >= 4 and not any(ch.isdigit() for ch in w)]
    phrases: list[str] = []
    if text.strip():
        phrases.append(text.strip())
    phrases.extend(words[:8])
    return phrases


def _parse_ranked_response(raw: str) -> _RankingParseResult:
    data = _load_json_object(raw)
    if not data:
        return _RankingParseResult(status="unavailable", reason=_ranking_failure_reason(raw))
    ranked = data.get("ranked", []) if isinstance(data, dict) else []
    items: list[_RankedItem] = []
    if not isinstance(ranked, list):
        return _RankingParseResult(status="unavailable", reason="missing_ranked_list")
    for entry in ranked:
        if not isinstance(entry, dict):
            continue
        slot = str(entry.get("slot") or "").strip()
        hymn_id = str(entry.get("hymn_id") or "").strip()
        if slot not in {key for key, _label in LITURGICAL_SLOTS} or not hymn_id:
            continue
        items.append(
            _RankedItem(
                slot=slot,
                hymn_id=hymn_id,
                reason=_clean_reason(entry.get("reason")),
                connection=_clean_reason(entry.get("connection")),
            )
        )
    return _RankingParseResult(status="ok", items=tuple(items))


def _load_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def _ranking_failure_reason(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "empty_response"
    folded = text.casefold()
    known_error_markers = (
        "nincs internetkapcsolat",
        "nem sikerült elérni a gemini api-t",
        "kérlek várj",
        "időtúllépés",
        "hibás api válasz",
        "api kulcs",
        "quota",
        "rate limit",
        "connection",
        "conn_error",
        "timeout",
        "cooldown",
        "429",
        "500",
        "502",
        "503",
        "504",
    )
    if any(marker in folded for marker in known_error_markers):
        return "llm_call_unavailable"
    return "malformed_json"


def _compose_recommendations(
    ranked: list[_RankedItem],
    valid_by_id: dict[str, HymnRecord],
    candidates: list[HymnRecord],
) -> list[RecommendedHymn]:
    used_ids: set[str] = set()
    used_slots: set[str] = set()
    recommendations: list[RecommendedHymn] = []
    slot_labels = dict(LITURGICAL_SLOTS)
    candidate_ids = {hymn.hymn_id for hymn in candidates}
    for item in ranked:
        if item.hymn_id not in candidate_ids:
            continue
        hymn = valid_by_id.get(item.hymn_id)
        if hymn is None or hymn.hymn_id in used_ids or item.slot in used_slots:
            continue
        recommendations.append(
            RecommendedHymn(
                slot_key=item.slot,
                slot_label=slot_labels[item.slot],
                hymn=hymn,
                reason=item.reason or "Az ének a megadott textus és alkalom fényében illeszkedő jelölt.",
                connection=item.connection or "A kapcsolatot a prédikáció hangsúlyához kell tovább pontosítani.",
            )
        )
        used_ids.add(hymn.hymn_id)
        used_slots.add(item.slot)
        if len(recommendations) >= len(LITURGICAL_SLOTS):
            break
    return recommendations


def _format_recommendations_markdown(
    recommendations: list[RecommendedHymn],
    liturgical_note: str,
) -> str:
    blocks: list[str] = []
    for index, item in enumerate(recommendations, start=1):
        hymn = item.hymn
        blocks.append(
            f"### {index}. {item.slot_label} — *{hymn.hymnal_code} {hymn.display_number}*\n"
            f"**Cím / kezdősor:** {hymn.first_line}\n"
            f"**Indoklás:** {item.reason}\n"
            f"**Kapcsolat az igével:** {item.connection}"
        )
    if liturgical_note:
        blocks.append(f"---\n\n## Liturgiai megjegyzés\n{liturgical_note}")
    return "\n\n".join(blocks)


def _liturgical_note(raw: str) -> str:
    data = _load_json_object(raw)
    note = data.get("liturgical_note", "") if isinstance(data, dict) else ""
    return _clean_reason(note)


def _clean_reason(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:700]


def _unsupported_hymnal_markdown(book: str) -> str:
    label = book or "a választott énekeskönyv"
    return (
        f"⚠️ **A(z) {label} énekeskönyvhöz még nincs validált helyi hymn adatbázis.**\n\n"
        "Ebben az átmeneti állapotban nem készítek szabad LLM-alapú énekajánlást, "
        "mert az énekszám és a kezdősor csak ellenőrzött adatbázisrekordból "
        "származhat. Jelenleg adatbázis-alapon az Erdélyi Református Énekeskönyv, "
        "a Református Énekeskönyv (2021) és a Református Énekeskönyv (1948) támogatott."
    )


def _unavailable_markdown(status: HymnRepositoryStatus) -> str:
    detail = f" (`{status.reason}`)" if status.reason else ""
    return (
        f"⚠️ **Az ellenőrzött énekadatbázis jelenleg nem elérhető{detail}.**\n\n"
        "Nem készítek szabad LLM-alapú éneklistát, mert az énekszám és a kezdősor "
        "csak validált SQLite rekordból származhat."
    )


def _ranking_unavailable_markdown(reason: str) -> str:
    detail = f" (`{reason}`)" if reason else ""
    return (
        f"⚠️ **Az MI-rangsorolás jelenleg nem elérhető{detail}.**\n\n"
        "Az ellenőrzött énekjelöltek megvannak a helyi adatbázisból, "
        "de a rangsorolási MI-hívás nem adott feldolgozható JSON választ. "
        "Nem készítek szabad LLM-alapú éneklistát, mert az énekszám és a "
        "kezdősor csak validált adatbázisrekordból származhat."
    )


__all__ = [
    "ERE_BOOK_LABEL",
    "RE21_BOOK_LABEL",
    "RE48_BOOK_LABEL",
    "HymnRecommendationResult",
    "HymnTopicSearchProfile",
    "RecommendedHymn",
    "build_hymn_ranking_prompt",
    "build_topic_search_profile",
    "recommend_hymns",
]
