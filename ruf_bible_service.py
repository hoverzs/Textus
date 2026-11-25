"""RUF 2014 passage loading through the official Szentiras.eu REST API.

Ez a modul KIZÁRÓLAG az élő, szakaszonkénti API-útvonalat adja (a
munkamenet-szintű `_PASSAGE_CACHE`-szel) — nem nyúl a helyi, teljes Biblia
szintű RÚF-szövegtárhoz. A helyi szövegtárat a `ruf_bible_local_db.py`
modul kezeli, önálló, a Konkordancia funkcióhoz szánt olvasási API-val
(`lookup_local`, `search_literal`); ez a modul szándékosan NEM hívja azt,
hogy a meglévő "Igehely keresése" / szakaszonkénti betöltés funkció
mindig a friss, élő API-válasz szerint működjön.

JOGI MEGJEGYZÉS — FELHASZNÁLÁSI ALAP
-------------------------------------
A RÚF 2014 fordítás szövegének megjelenítése (ez a modul) és — a
`ruf_bible_local_db` modulon keresztül — teljes szövegű helyi tárolása a
TEXTUS üzemeltetője és a Magyar Bibliatársulat között fennálló, érvényes
szerződés/engedély alapján történik (lásd `COPYRIGHT_NOTICE` /
`SOURCE_ATTRIBUTION` lent). Lásd bővebben `ruf_bible_local_db.py`
modul-docstringjét.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

import requests


TRANSLATION_NAME = "RÚF 2014"
TRANSLATION_CODE = "RUF"
SOURCE_NAME = "Szentírás.eu"
COPYRIGHT_NOTICE = "Revideált új fordítás, © Magyar Bibliatársulat, 2014."
SOURCE_ATTRIBUTION = "Forrás: Szentírás.eu, RÚF 2015 © Magyar Bibliatársulat. Felhasználás engedéllyel."
BASE_URL = "https://szentiras.eu/api/idezet"
SZENTIRAS_EU_API_KEY_NAME = "SZENTIRAS_EU_API_KEY"
USER_AGENT = "TextusHomiletics/2.2 (+https://textus.ro; Szentiras.eu REST RUF loader)"
DEFAULT_CONNECT_TIMEOUT_S = 6.0
DEFAULT_READ_TIMEOUT_S = 20.0
DEFAULT_TIMEOUT = (DEFAULT_CONNECT_TIMEOUT_S, DEFAULT_READ_TIMEOUT_S)
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_RETRY_DELAYS_S = (0.5,)
CACHE_TTL_S = 24 * 60 * 60
PASSAGE_CACHE_SCHEMA_VERSION = 2
STALE_CACHE_WARNING = (
    "A Szentírás.eu jelenleg nem érhető el; a korábban eltárolt szöveget jelenítjük meg."
)
API_NOT_CONFIGURED_MESSAGE = (
    "A RÚF automatikus betöltése nincs beállítva."
)

RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}
FINAL_HTTP_ERRORS = {
    401: "A Szentírás.eu API-kulcs hiányzik vagy érvénytelen.",
    403: "A Szentírás.eu API-kulcs jelenleg nem használható.",
    404: "A megadott igehely nem található.",
    429: "A szolgáltatás sebességkorlátja ideiglenesen aktiválódott.",
}

_PASSAGE_CACHE: dict[tuple[str, str, int, int | None, int | None], dict[str, Any]] = {}


@dataclass(frozen=True)
class BookInfo:
    code: str
    abbr: str
    single_chapter: bool = False


@dataclass(frozen=True)
class ParsedReference:
    book: BookInfo
    chapter: int
    verse_start: int | None
    verse_end: int | None
    requested_reference: str

    @property
    def normalized_reference(self) -> str:
        abbr = self.book.abbr
        dash = "–"
        if self.book.single_chapter:
            if self.verse_start is None:
                return abbr
            if self.verse_end is None or self.verse_end == self.verse_start:
                return f"{abbr} {self.verse_start}"
            return f"{abbr} {self.verse_start}{dash}{self.verse_end}"
        if self.verse_start is None:
            return f"{abbr} {self.chapter}"
        if self.verse_end is None or self.verse_end == self.verse_start:
            return f"{abbr} {self.chapter},{self.verse_start}"
        return f"{abbr} {self.chapter},{self.verse_start}{dash}{self.verse_end}"

    @property
    def api_reference(self) -> str:
        return self.normalized_reference.replace("–", "-")


@dataclass(frozen=True)
class SzentirasEuHttpError(ConnectionError):
    status_code: int
    message: str
    transient: bool = False
    retry_after_s: float | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class PassageFetchResult:
    verses: list[dict[str, Any]]
    source_url: str
    fetched_reference: str
    warnings: list[str]
    cache_status: str


class RufPermanentFetchFailure(ValueError):
    pass


def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text or "")
    ascii_ish = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return re.sub(r"[\s.]+", "", ascii_ish.casefold())


_BOOK_DEFS: list[tuple[BookInfo, tuple[str, ...]]] = [
    (BookInfo("GEN", "1Móz"), ("1Moz", "1Móz", "IMoz", "Mózes1", "Mozes1", "Genesis", "Ter")),
    (BookInfo("EXO", "2Móz"), ("2Moz", "2Móz", "IIMoz", "Exodus", "Kiv")),
    (BookInfo("LEV", "3Móz"), ("3Moz", "3Móz", "IIIMoz", "Leviticus", "Lev")),
    (BookInfo("NUM", "4Móz"), ("4Moz", "4Móz", "IVMoz", "Numeri", "Szám", "Szam")),
    (BookInfo("DEU", "5Móz"), ("5Moz", "5Móz", "VMoz", "Deuteronomium", "Törv", "Torv")),
    (BookInfo("JOS", "Józs"), ("Jozs", "Józs", "Józsué", "Jozsue", "Joshua")),
    (BookInfo("JDG", "Bír"), ("Bir", "Bír", "Bírák", "Birak", "Judges")),
    (BookInfo("RUT", "Ruth"), ("Ruth", "Rut")),
    (BookInfo("1SA", "1Sám"), ("1Sam", "1Sám", "ISam", "1Samuel")),
    (BookInfo("2SA", "2Sám"), ("2Sam", "2Sám", "IISam", "2Samuel")),
    (BookInfo("1KI", "1Kir"), ("1Kir", "IKir", "1Királyok", "1Kiralyok")),
    (BookInfo("2KI", "2Kir"), ("2Kir", "IIKir", "2Királyok", "2Kiralyok")),
    (BookInfo("1CH", "1Krón"), ("1Kron", "1Krón", "IKron", "1Krónika", "1Kronika")),
    (BookInfo("2CH", "2Krón"), ("2Kron", "2Krón", "IIKron", "2Krónika", "2Kronika")),
    (BookInfo("EZR", "Ezd"), ("Ezd", "Ezra", "Ezsdrás", "Ezsdras")),
    (BookInfo("NEH", "Neh"), ("Neh", "Nehémiás", "Nehemias")),
    (BookInfo("EST", "Eszt"), ("Eszt", "Eszter", "Esther")),
    (BookInfo("JOB", "Jób"), ("Job", "Jób")),
    (BookInfo("PSA", "Zsolt"), ("Zsolt", "Zsoltár", "Zsoltar", "Zsoltárok", "Psalms", "Zsol")),
    (BookInfo("PRO", "Péld"), ("Peld", "Péld", "Példabeszédek", "Peldabeszedek")),
    (BookInfo("ECC", "Préd"), ("Pred", "Préd", "Prédikátor", "Predikator")),
    (BookInfo("SNG", "Énekek"), ("Enekek", "Énekek", "Én", "En", "Énekek éneke")),
    (BookInfo("ISA", "Ézs"), ("Ezs", "Ézs", "Ézsaiás", "Ezsaias", "Isaiah")),
    (BookInfo("JER", "Jer"), ("Jer", "Jeremiás", "Jeremias")),
    (BookInfo("LAM", "JSir"), ("Jsir", "Siralmak", "Lamentations")),
    (BookInfo("EZK", "Ez"), ("Ez", "Ezékiel", "Ezekiel")),
    (BookInfo("DAN", "Dán"), ("Dan", "Dán", "Dániel", "Daniel")),
    (BookInfo("HOS", "Hós"), ("Hos", "Hós", "Hóseás", "Hoseas")),
    (BookInfo("JOL", "Jóel"), ("Joel", "Jóel")),
    (BookInfo("AMO", "Ám"), ("Am", "Ám", "Ámós", "Amos")),
    (BookInfo("OBA", "Abd", True), ("Abd", "Abdiás", "Abdias", "Obad")),
    (BookInfo("JON", "Jón"), ("Jon", "Jón", "Jónás", "Jonas")),
    (BookInfo("MIC", "Mik"), ("Mik", "Mikeás", "Mikeas")),
    (BookInfo("NAM", "Náh"), ("Nah", "Náh", "Náhum", "Nahum")),
    (BookInfo("HAB", "Hab"), ("Hab", "Habakkuk")),
    (BookInfo("ZEP", "Zof"), ("Zof", "Zofóniás", "Zofonias", "Sofonias")),
    (BookInfo("HAG", "Agg"), ("Agg", "Aggeus", "Haggai")),
    (BookInfo("ZEC", "Zak"), ("Zak", "Zakariás", "Zakarias")),
    (BookInfo("MAL", "Mal"), ("Mal", "Malakiás", "Malakias")),
    (BookInfo("MAT", "Mt"), ("Mt", "Mat", "Máté", "Mate", "Matthew")),
    (BookInfo("MRK", "Mk"), ("Mk", "Márk", "Mark", "Mar")),
    (BookInfo("LUK", "Lk"), ("Lk", "Luk", "Lukács", "Luka", "Luke")),
    (BookInfo("JHN", "Jn"), ("Jn", "János", "Janos", "John", "Jhn")),
    (BookInfo("ACT", "ApCsel"), ("ApCsel", "Apcsel", "Csel", "Apostolok", "Act", "Acts")),
    (BookInfo("ROM", "Róm"), ("Rom", "Róm", "Róma", "Roma", "Rómaiak", "Romaiak", "Romans")),
    (BookInfo("1CO", "1Kor"), ("1Kor", "IKor", "1Cor", "1Korinthus", "1Korinthusiak")),
    (BookInfo("2CO", "2Kor"), ("2Kor", "IIKor", "2Cor", "2Korinthus", "2Korinthusiak")),
    (BookInfo("GAL", "Gal"), ("Gal", "Galata", "Galaták", "Galatak")),
    (BookInfo("EPH", "Ef"), ("Ef", "Eph", "Efezus", "Efezusiak")),
    (BookInfo("PHP", "Fil"), ("Fil", "Phil", "Filippi", "Filippiek")),
    (BookInfo("COL", "Kol"), ("Kol", "Col", "Kolossé", "Kolosse", "Kolosséiak")),
    (BookInfo("1TH", "1Thess"), ("1Thess", "1Tess", "IThess", "1Thesszalonika")),
    (BookInfo("2TH", "2Thess"), ("2Thess", "2Tess", "IIThess", "2Thesszalonika")),
    (BookInfo("1TI", "1Tim"), ("1Tim", "ITim", "1Timóteus", "1Timoteus")),
    (BookInfo("2TI", "2Tim"), ("2Tim", "IITim", "2Timóteus", "2Timoteus")),
    (BookInfo("TIT", "Tit"), ("Tit", "Titusz", "Titus")),
    (BookInfo("PHM", "Filem", True), ("Filem", "Phm", "Filemon", "Philemon")),
    (BookInfo("HEB", "Zsid"), ("Zsid", "Zsidók", "Zsidok", "Hebrews", "Heb")),
    (BookInfo("JAS", "Jak"), ("Jak", "Jakab", "James")),
    (BookInfo("1PE", "1Pt"), ("1Pt", "1Pet", "IPt", "1Péter", "1Peter")),
    (BookInfo("2PE", "2Pt"), ("2Pt", "2Pet", "IIPt", "2Péter", "2Peter")),
    (BookInfo("1JN", "1Jn"), ("1Jn", "1János", "1Janos", "IJn")),
    (BookInfo("2JN", "2Jn", True), ("2Jn", "2János", "2Janos", "IIJn")),
    (BookInfo("3JN", "3Jn", True), ("3Jn", "3János", "3Janos", "IIIJn")),
    (BookInfo("JUD", "Júd", True), ("Jud", "Júd", "Júdás", "Judas", "Jude")),
    (BookInfo("REV", "Jel"), ("Jel", "Jelenések", "Jelenesek", "Rev", "Revelation")),
]


def _build_book_lookup() -> dict[str, BookInfo]:
    lookup: dict[str, BookInfo] = {}
    for info, aliases in _BOOK_DEFS:
        for name in (info.code, info.abbr, *aliases):
            key = _fold(name)
            if key:
                lookup[key] = info
    return lookup


BOOK_LOOKUP = _build_book_lookup()

# Kanonikus, 66 könyvet tartalmazó sorrend (1Móz..Jel) — a helyi DB-importhoz
# és bármely olyan felhasználáshoz, ahol a teljes könyvlistára van szükség
# a `BOOK_LOOKUP` alias-dict helyett (ami csak név→BookInfo feloldásra jó).
CANONICAL_BOOKS: tuple[BookInfo, ...] = tuple(info for info, _aliases in _BOOK_DEFS)


def parse_bible_reference(reference: str) -> ParsedReference:
    raw = (reference or "").strip()
    if not raw:
        raise ValueError("Add meg az igehelyet (pl. Júd 24–25 vagy Jn 3,16).")
    cleaned = (
        raw.replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace("‐", "-")
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    match = re.match(
        r"^((?:[1-5]|I{1,3}|IV|V)\s*)?([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű.]+)\s*(.*)$",
        cleaned,
    )
    if not match:
        raise ValueError(f"Nem értelmezhető igehely: {raw!r}")
    num_prefix = (match.group(1) or "").strip()
    name = (match.group(2) or "").strip().rstrip(".")
    rest = (match.group(3) or "").strip()
    book_token = f"{num_prefix}{name}".strip()
    info = BOOK_LOOKUP.get(_fold(book_token))
    if info is None:
        raise ValueError(
            f"Ismeretlen könyv: {book_token!r}. Használj gyakori rövidítést (pl. Jn, Róm, 1Móz, Júd)."
        )
    if not rest:
        if info.single_chapter:
            return ParsedReference(info, 1, None, None, raw)
        raise ValueError(f"Add meg a fejezetet is (pl. {info.abbr} 3 vagy {info.abbr} 3,16).")
    rest_norm = re.sub(r"\s+", "", rest.replace(":", ","))
    # English-style chapter.verse(-verse) → chapter,verse(-verse)
    rest_norm = re.sub(r"^(\d+)\.(\d+)", r"\1,\2", rest_norm)
    if not re.fullmatch(r"[\d,\-]+", rest_norm):
        raise ValueError(f"Hibás fejezet/vers rész: {rest!r}")
    if "," in rest_norm:
        chapter_s, verse_part = rest_norm.split(",", 1)
        if not chapter_s.isdigit():
            raise ValueError(f"Hibás fejezet: {chapter_s!r}")
        chapter = int(chapter_s)
        verse_start, verse_end = _parse_verse_span(verse_part)
        if info.single_chapter and chapter != 1:
            raise ValueError(f"A(z) {info.abbr} egyfejezetes könyv; a fejezet mindig 1.")
        return ParsedReference(info, 1 if info.single_chapter else chapter, verse_start, verse_end, raw)
    if "-" in rest_norm:
        start_s, end_s = rest_norm.split("-", 1)
        if not start_s.isdigit() or not end_s.isdigit():
            raise ValueError(f"Hibás tartomány: {rest!r}")
        start, end = int(start_s), int(end_s)
        if not info.single_chapter:
            raise ValueError(
                f"Fejezettartomány nem támogatott. Adj meg egy fejezetet vagy verseket vesszővel."
            )
        if start > end:
            raise ValueError(f"Fordított verstartomány: {start}–{end}.")
        return ParsedReference(info, 1, start, end, raw)
    if not rest_norm.isdigit():
        raise ValueError(f"Hibás fejezet/vers: {rest!r}")
    value = int(rest_norm)
    if value < 1:
        raise ValueError("A szám legalább 1 legyen.")
    if info.single_chapter:
        return ParsedReference(info, 1, value, value, raw)
    return ParsedReference(info, value, None, None, raw)


def _parse_verse_span(part: str) -> tuple[int, int | None]:
    if not part:
        raise ValueError("Hiányzik a versszám a vessző után.")
    if "-" in part:
        start_s, end_s = part.split("-", 1)
        if not start_s.isdigit() or not end_s.isdigit():
            raise ValueError(f"Hibás verstartomány: {part!r}")
        start, end = int(start_s), int(end_s)
        if start < 1 or end < 1:
            raise ValueError("A versszám legalább 1 legyen.")
        if start > end:
            raise ValueError(f"Fordított verstartomány: {start}–{end}.")
        return start, end
    if not part.isdigit():
        raise ValueError(f"Hibás versszám: {part!r}")
    verse = int(part)
    if verse < 1:
        raise ValueError("A versszám legalább 1 legyen.")
    return verse, verse


def build_api_url(reference: str, translation: str = TRANSLATION_CODE) -> str:
    return f"{BASE_URL}/{quote(reference, safe='')}/{quote(translation, safe='')}"


def get_szentiras_eu_api_key() -> str:
    value = _streamlit_secret(SZENTIRAS_EU_API_KEY_NAME)
    if value:
        return value
    return os.getenv(SZENTIRAS_EU_API_KEY_NAME, "").strip()


def _streamlit_secret(name: str) -> str:
    try:
        import streamlit as st  # type: ignore

        value = st.secrets.get(name, "")
    except Exception:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip() if value else ""


def clear_ruf_cache() -> None:
    _PASSAGE_CACHE.clear()


def format_structured_verses(verses: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for verse in verses:
        number = str(verse.get("number") or verse.get("verse_number") or "").strip()
        text = _clean_verse_text(str(verse.get("text") or ""))
        if number and text:
            lines.append(f"{number}. {text}")
    return "\n".join(lines)


def format_passage_text(verses: dict[int, str]) -> str:
    return "\n".join(f"{number}. {_clean_verse_text(verses[number])}" for number in sorted(verses))


def _clean_verse_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _empty_result(
    *,
    requested_reference: str,
    error: str,
    normalized_reference: str = "",
    source_url: str = "",
    cache_status: str = "miss",
) -> dict[str, Any]:
    return {
        "success": False,
        "requested_reference": requested_reference or "",
        "reference": normalized_reference,
        "normalized_reference": normalized_reference,
        "translation": TRANSLATION_NAME,
        "text": "",
        "verses": [],
        "source_name": SOURCE_NAME,
        "source_url": source_url,
        "copyright_notice": COPYRIGHT_NOTICE,
        "source_attribution": SOURCE_ATTRIBUTION,
        "fetched_at": "",
        "from_cache": False,
        "is_stale": False,
        "warnings": [],
        "error": error,
        "cache_status": cache_status,
    }


def _ok_result(
    *,
    requested_reference: str,
    normalized_reference: str,
    verses: list[dict[str, Any]],
    source_url: str,
    fetched_at: float | None = None,
    cache_status: str = "live",
    warnings: list[str] | None = None,
    from_cache: bool | None = None,
    is_stale: bool | None = None,
) -> dict[str, Any]:
    ts = time.time() if fetched_at is None else float(fetched_at)
    text = format_structured_verses(verses)
    return {
        "success": True,
        "requested_reference": requested_reference,
        "reference": normalized_reference,
        "normalized_reference": normalized_reference,
        "translation": TRANSLATION_NAME,
        "text": text,
        "verses": verses,
        "source_name": SOURCE_NAME,
        "source_url": source_url,
        "copyright_notice": COPYRIGHT_NOTICE,
        "source_attribution": SOURCE_ATTRIBUTION,
        "fetched_at": ts,
        "from_cache": bool(cache_status != "live" if from_cache is None else from_cache),
        "is_stale": bool(cache_status == "stale_fallback" if is_stale is None else is_stale),
        "warnings": list(warnings or []),
        "error": "",
        "cache_status": cache_status,
    }


class SzentirasEuApiProvider:
    name = "szentiras.eu-api"
    source_name = SOURCE_NAME

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def fetch(
        self,
        parsed: ParsedReference,
        *,
        timeout: Any = DEFAULT_TIMEOUT,
        http_get: Callable[..., Any] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_delays_s: tuple[float, ...] = DEFAULT_RETRY_DELAYS_S,
        sleep: Callable[[float], None] = time.sleep,
    ) -> PassageFetchResult:
        api_key = (self.api_key or get_szentiras_eu_api_key()).strip()
        url = build_api_url(parsed.api_reference)
        if not api_key:
            raise RufPermanentFetchFailure(API_NOT_CONFIGURED_MESSAGE)
        attempts = max(1, int(max_attempts))
        getter = http_get or _default_http_get
        last_exc: BaseException | None = None
        for attempt in range(1, attempts + 1):
            try:
                payload = _call_http_get(
                    getter,
                    url,
                    headers={
                        "X-API-Key": api_key,
                        "Accept": "application/json",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=_normalize_timeout(timeout),
                )
                _raise_for_response_status(payload)
                verses, fetched_reference = parse_szentiras_eu_response(payload, parsed)
                return PassageFetchResult(
                    verses=verses,
                    source_url=url,
                    fetched_reference=fetched_reference,
                    warnings=[],
                    cache_status="live",
                )
            except Exception as exc:
                last_exc = exc
                transient = _is_transient_error(exc)
                if not transient or attempt >= attempts:
                    if isinstance(exc, SzentirasEuHttpError) and not transient:
                        raise RufPermanentFetchFailure(str(exc)) from exc
                    if transient:
                        raise _transient_exception(str(exc)) from exc
                    raise
                delay = _retry_delay(exc, retry_delays_s, attempt)
                if delay > 0:
                    sleep(delay)
        assert last_exc is not None
        raise last_exc


def parse_szentiras_eu_response(payload: Any, parsed: ParsedReference) -> tuple[list[dict[str, Any]], str]:
    data = _json_payload(payload)
    if not isinstance(data, dict):
        raise ValueError("A Szentírás.eu API válasza nem JSON objektum.")
    response = data.get("valasz")
    if not isinstance(response, dict):
        raise ValueError("A Szentírás.eu API válasza nem tartalmaz valasz objektumot.")
    translation = response.get("forditas")
    if isinstance(translation, dict):
        code = str(translation.get("rov") or "").strip().upper()
        if code and code != TRANSLATION_CODE:
            raise ValueError(f"A Szentírás.eu API nem RUF fordítást adott vissza: {code}.")
    raw_verses = response.get("versek")
    if not isinstance(raw_verses, list) or not raw_verses:
        raise ValueError("Üres találat: a Szentírás.eu API nem adott vissza verseket.")
    verses: list[dict[str, Any]] = []
    for item in raw_verses:
        verse = _verse_from_api_item(item)
        if verse is not None:
            verses.append(verse)
    if not verses:
        raise ValueError("Üres találat: a Szentírás.eu API versei nem tartalmaznak szöveget.")
    _validate_requested_passage_returned(parsed, verses)
    fetched_reference = _fetched_reference(data, verses) or parsed.normalized_reference
    return verses, fetched_reference


def _json_payload(payload: Any) -> Any:
    if isinstance(payload, (dict, list)):
        return payload
    if hasattr(payload, "json"):
        return payload.json()
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("A Szentírás.eu API válasza nem valid JSON.") from exc
    raise ValueError("A Szentírás.eu API válasza nem feldolgozható.")


def _verse_from_api_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    text = _clean_verse_text(str(item.get("szoveg") or item.get("text") or ""))
    if not text:
        return None
    place = item.get("hely") if isinstance(item.get("hely"), dict) else {}
    pretty = str(place.get("szep") or item.get("hely") or "").strip()
    machine = str(place.get("gepi") or "").strip()
    number = _verse_number_from_place(pretty, machine, item)
    if number is None:
        return None
    return {
        "verse_number": number,
        "number": number,
        "text": text,
        "reference": pretty,
        "machine_reference": machine,
    }


def _verse_number_from_place(pretty: str, machine: str, item: dict[str, Any]) -> int | None:
    for value in (item.get("vers"), item.get("verse"), item.get("verse_number")):
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    match = re.search(r"_(\d+)$", machine)
    if match:
        return int(match.group(1))
    match = re.search(r"[, ](\d+)$", pretty)
    if match:
        return int(match.group(1))
    return None


def _validate_requested_passage_returned(parsed: ParsedReference, verses: list[dict[str, Any]]) -> None:
    numbers = {int(verse["verse_number"]) for verse in verses}
    if parsed.verse_start is None:
        return
    end = parsed.verse_end if parsed.verse_end is not None else parsed.verse_start
    expected = set(range(parsed.verse_start, end + 1))
    missing = sorted(expected - numbers)
    if missing:
        raise ValueError("A Szentírás.eu API nem a teljes kért igehelyet adta vissza.")


def _fetched_reference(data: dict[str, Any], verses: list[dict[str, Any]]) -> str:
    requested = data.get("keres")
    if isinstance(requested, dict):
        value = str(requested.get("hivatkozas") or "").strip()
        if value:
            return value
    refs = [str(verse.get("reference") or "").strip() for verse in verses if verse.get("reference")]
    if len(refs) == 1:
        return refs[0]
    return ""


def _default_http_get(url: str, *, headers: dict[str, str], timeout: Any = DEFAULT_TIMEOUT) -> requests.Response:
    try:
        response = requests.get(url, headers=headers, timeout=_normalize_timeout(timeout))
    except requests.Timeout as exc:
        raise TimeoutError("A Szentírás.eu szolgáltatás jelenleg nem érhető el.") from exc
    except requests.ConnectionError as exc:
        raise ConnectionError("A Szentírás.eu szolgáltatás jelenleg nem érhető el.") from exc
    _raise_for_response_status(response)
    return response


def _raise_for_response_status(response: Any) -> None:
    if not hasattr(response, "status_code"):
        return
    status = int(response.status_code)
    if status in RETRYABLE_HTTP_STATUS:
        raise SzentirasEuHttpError(
            status,
            FINAL_HTTP_ERRORS.get(status, "A Szentírás.eu szolgáltatás jelenleg nem érhető el."),
            transient=True,
            retry_after_s=_retry_after(response.headers.get("Retry-After")),
        )
    if status in FINAL_HTTP_ERRORS:
        raise SzentirasEuHttpError(status, FINAL_HTTP_ERRORS[status], transient=False)
    if 400 <= status < 500:
        raise SzentirasEuHttpError(status, "A megadott igehely nem található.", transient=False)
    if status >= 500:
        raise SzentirasEuHttpError(
            status,
            "A Szentírás.eu szolgáltatás jelenleg nem érhető el.",
            transient=True,
        )


def _call_http_get(
    getter: Callable[..., Any],
    url: str,
    *,
    headers: dict[str, str],
    timeout: Any,
) -> Any:
    try:
        return getter(url, headers=headers, timeout=timeout)
    except TypeError:
        try:
            return getter(url, timeout=timeout)
        except TypeError:
            return getter(url)


def _normalize_timeout(timeout: Any) -> tuple[float, float]:
    if isinstance(timeout, tuple) and len(timeout) == 2:
        return (float(timeout[0]), float(timeout[1]))
    if isinstance(timeout, list) and len(timeout) == 2:
        return (float(timeout[0]), float(timeout[1]))
    if timeout is None:
        return DEFAULT_TIMEOUT
    value = float(timeout)
    return (min(value, DEFAULT_CONNECT_TIMEOUT_S), value)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, min(5.0, float(value)))
    except ValueError:
        return None


def _retry_delay(exc: BaseException, retry_delays_s: tuple[float, ...], attempt: int) -> float:
    if isinstance(exc, SzentirasEuHttpError) and exc.retry_after_s is not None:
        return exc.retry_after_s
    if not retry_delays_s:
        return 0.0
    return retry_delays_s[min(attempt - 1, len(retry_delays_s) - 1)]


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, SzentirasEuHttpError):
        return exc.transient
    if isinstance(exc, (TimeoutError, ConnectionError, requests.Timeout, requests.ConnectionError)):
        return True
    return False


def _transient_exception(message: str) -> ConnectionError:
    if "sebességkorlát" in message:
        return ConnectionError(FINAL_HTTP_ERRORS[429])
    return ConnectionError("A Szentírás.eu szolgáltatás jelenleg nem érhető el.")


def _cache_is_fresh(entry: dict[str, Any], *, ttl_s: float) -> bool:
    if ttl_s <= 0:
        return False
    try:
        fetched_at = float(entry.get("fetched_at") or 0.0)
    except (TypeError, ValueError):
        return False
    return (time.time() - fetched_at) <= ttl_s


def _cache_entry_has_current_schema(entry: dict[str, Any]) -> bool:
    return entry.get("schema_version") == PASSAGE_CACHE_SCHEMA_VERSION


def _result_has_renderable_text(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    verses = result.get("verses")
    if isinstance(verses, list):
        for verse in verses:
            if not isinstance(verse, dict):
                continue
            number = str(verse.get("number") or verse.get("verse_number") or "").strip()
            text = _clean_verse_text(str(verse.get("text") or ""))
            if number and text:
                return True
    return bool(_clean_verse_text(str(result.get("text") or "")))


def _cache_entry_is_usable(entry: dict[str, Any], *, ttl_s: float | None = None) -> bool:
    if not _cache_entry_has_current_schema(entry):
        return False
    if ttl_s is not None and not _cache_is_fresh(entry, ttl_s=ttl_s):
        return False
    return _result_has_renderable_text(entry.get("result"))


def _passage_key(parsed: ParsedReference) -> tuple[str, str, int, int | None, int | None]:
    return (
        TRANSLATION_CODE,
        parsed.book.code.upper(),
        int(parsed.chapter),
        parsed.verse_start,
        parsed.verse_end,
    )


def fetch_ruf_passage(
    reference: str,
    *,
    timeout: Any = DEFAULT_TIMEOUT,
    http_get: Callable[..., Any] | None = None,
    use_cache: bool = True,
    cache_ttl_s: float = CACHE_TTL_S,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delays_s: tuple[float, ...] = DEFAULT_RETRY_DELAYS_S,
    sleep: Callable[[float], None] = time.sleep,
    providers: tuple[SzentirasEuApiProvider, ...] | None = None,
) -> dict[str, Any]:
    requested = (reference or "").strip()
    try:
        parsed = parse_bible_reference(requested)
    except ValueError as exc:
        return _empty_result(requested_reference=requested, error=str(exc))

    key = _passage_key(parsed)
    source_url = build_api_url(parsed.api_reference)
    if use_cache and key in _PASSAGE_CACHE and _cache_entry_is_usable(_PASSAGE_CACHE[key], ttl_s=cache_ttl_s):
        cached = dict(_PASSAGE_CACHE[key]["result"])
        cached["cache_status"] = "fresh"
        cached["from_cache"] = True
        cached["is_stale"] = False
        return cached

    provider = (providers or (SzentirasEuApiProvider(),))[0]
    try:
        fetched = provider.fetch(
            parsed,
            timeout=timeout,
            http_get=http_get,
            max_attempts=max_attempts,
            retry_delays_s=retry_delays_s,
            sleep=sleep,
        )
    except RufPermanentFetchFailure as exc:
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            source_url=source_url,
            error=str(exc),
        )
    except ValueError as exc:
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            source_url=source_url,
            error=str(exc),
        )
    except (TimeoutError, ConnectionError, requests.Timeout, requests.ConnectionError) as exc:
        stale = _PASSAGE_CACHE.get(key) if use_cache else None
        if stale and _cache_entry_is_usable(stale):
            stale_result = dict(stale["result"])
            stale_result["warnings"] = [*stale_result.get("warnings", []), STALE_CACHE_WARNING]
            stale_result["cache_status"] = "stale_fallback"
            stale_result["from_cache"] = True
            stale_result["is_stale"] = True
            return stale_result
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            source_url=source_url,
            error=str(exc) or "A Szentírás.eu szolgáltatás jelenleg nem érhető el.",
        )

    result = _ok_result(
        requested_reference=requested,
        normalized_reference=parsed.normalized_reference,
        verses=fetched.verses,
        source_url=fetched.source_url,
        cache_status=fetched.cache_status,
        warnings=fetched.warnings,
    )
    if not result["text"].strip() or not result["verses"]:
        return _empty_result(
            requested_reference=requested,
            normalized_reference=parsed.normalized_reference,
            source_url=fetched.source_url,
            error="Üres találat: a kért szakasz szövege üres.",
        )
    if use_cache:
        _PASSAGE_CACHE[key] = {
            "schema_version": PASSAGE_CACHE_SCHEMA_VERSION,
            "fetched_at": time.time(),
            "result": dict(result),
        }
    return result


__all__ = [
    "TRANSLATION_NAME",
    "TRANSLATION_CODE",
    "SOURCE_NAME",
    "COPYRIGHT_NOTICE",
    "SOURCE_ATTRIBUTION",
    "BASE_URL",
    "SZENTIRAS_EU_API_KEY_NAME",
    "USER_AGENT",
    "DEFAULT_CONNECT_TIMEOUT_S",
    "DEFAULT_READ_TIMEOUT_S",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_RETRY_DELAYS_S",
    "CACHE_TTL_S",
    "PASSAGE_CACHE_SCHEMA_VERSION",
    "STALE_CACHE_WARNING",
    "API_NOT_CONFIGURED_MESSAGE",
    "SzentirasEuHttpError",
    "SzentirasEuApiProvider",
    "RufPermanentFetchFailure",
    "ParsedReference",
    "BookInfo",
    "BOOK_LOOKUP",
    "CANONICAL_BOOKS",
    "parse_bible_reference",
    "build_api_url",
    "get_szentiras_eu_api_key",
    "parse_szentiras_eu_response",
    "format_passage_text",
    "format_structured_verses",
    "fetch_ruf_passage",
    "clear_ruf_cache",
]
