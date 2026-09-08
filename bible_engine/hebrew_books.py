from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class HebrewBook:
    ruf_code: str
    tahot_code: str
    abbr_hu: str
    name_hu: str
    aliases: tuple[str, ...] = ()


OT_BOOKS: tuple[HebrewBook, ...] = (
    HebrewBook("GEN", "Gen", "1Móz", "1 Mózes", ("1Moz", "1 Mózes", "Genesis", "Ter")),
    HebrewBook("EXO", "Exo", "2Móz", "2 Mózes", ("2Moz", "2 Mózes", "Exodus", "Kiv")),
    HebrewBook("LEV", "Lev", "3Móz", "3 Mózes", ("3Moz", "3 Mózes", "Leviticus")),
    HebrewBook("NUM", "Num", "4Móz", "4 Mózes", ("4Moz", "4 Mózes", "Numeri", "Szám")),
    HebrewBook("DEU", "Deu", "5Móz", "5 Mózes", ("5Moz", "5 Mózes", "Deuteronomium", "Törv")),
    HebrewBook("JOS", "Jos", "Józs", "Józsué", ("Jozs", "Jozsue", "Joshua")),
    HebrewBook("JDG", "Jdg", "Bír", "Bírák", ("Bir", "Birak", "Judges")),
    HebrewBook("RUT", "Rut", "Ruth", "Ruth", ("Rut",)),
    HebrewBook("1SA", "1Sa", "1Sám", "1 Sámuel", ("1Sam", "1 Sámuel")),
    HebrewBook("2SA", "2Sa", "2Sám", "2 Sámuel", ("2Sam", "2 Sámuel")),
    HebrewBook("1KI", "1Ki", "1Kir", "1 Királyok", ("1 Kir", "1Kiralyok", "1 Kings")),
    HebrewBook("2KI", "2Ki", "2Kir", "2 Királyok", ("2 Kir", "2Kiralyok", "2 Kings")),
    HebrewBook("1CH", "1Ch", "1Krón", "1 Krónikák", ("1Kron", "1 Krón", "1 Kronikak")),
    HebrewBook("2CH", "2Ch", "2Krón", "2 Krónikák", ("2Kron", "2 Krón", "2 Kronikak")),
    HebrewBook("EZR", "Ezr", "Ezsd", "Ezsdrás", ("Ezd", "Ezra", "Ezsdras")),
    HebrewBook("NEH", "Neh", "Neh", "Nehémiás", ("Nehemias",)),
    HebrewBook("EST", "Est", "Eszt", "Eszter", ("Esther",)),
    HebrewBook("JOB", "Job", "Jób", "Jób", ("Job",)),
    HebrewBook("PSA", "Psa", "Zsolt", "Zsoltárok", ("Zsol", "Zsoltar", "Psalms", "Psalm")),
    HebrewBook("PRO", "Pro", "Péld", "Példabeszédek", ("Peld", "Peldabeszedek", "Proverbs")),
    HebrewBook("ECC", "Ecc", "Préd", "Prédikátor", ("Pred", "Predikator", "Ecclesiastes")),
    HebrewBook("SNG", "Sng", "Énekek", "Énekek éneke", ("Enekek", "En", "Song")),
    HebrewBook("ISA", "Isa", "Ézs", "Ézsaiás", ("Ezs", "Ezsaias", "Isaiah")),
    HebrewBook("JER", "Jer", "Jer", "Jeremiás", ("Jeremias",)),
    HebrewBook("LAM", "Lam", "JSir", "Jeremiás siralmai", ("Jsir", "Siralmak", "Lamentations")),
    HebrewBook("EZK", "Ezk", "Ez", "Ezékiel", ("Ezekiel",)),
    HebrewBook("DAN", "Dan", "Dán", "Dániel", ("Dan", "Daniel")),
    HebrewBook("HOS", "Hos", "Hós", "Hóseás", ("Hos", "Hoseas")),
    HebrewBook("JOL", "Jol", "Jóel", "Jóel", ("Joel",)),
    HebrewBook("AMO", "Amo", "Ám", "Ámós", ("Am", "Amos")),
    HebrewBook("OBA", "Oba", "Abd", "Abdiás", ("Abdias", "Obad")),
    HebrewBook("JON", "Jon", "Jón", "Jónás", ("Jonas",)),
    HebrewBook("MIC", "Mic", "Mik", "Mikeás", ("Mikeas",)),
    HebrewBook("NAM", "Nam", "Náh", "Náhum", ("Nah", "Nahum")),
    HebrewBook("HAB", "Hab", "Hab", "Habakuk", ("Habakkuk",)),
    HebrewBook("ZEP", "Zep", "Zof", "Zofóniás", ("Sofonias", "Zofonias")),
    HebrewBook("HAG", "Hag", "Hag", "Haggeus", ("Agg", "Haggai")),
    HebrewBook("ZEC", "Zec", "Zak", "Zakariás", ("Zakarias", "Zechariah")),
    HebrewBook("MAL", "Mal", "Mal", "Malakiás", ("Malakias",)),
)

OT_BOOK_ORDER: tuple[str, ...] = tuple(book.tahot_code for book in OT_BOOKS)


class HebrewReferenceError(ValueError):
    def __init__(self, message: str, *, book_token: str = "", technical_detail: str = "") -> None:
        super().__init__(message)
        self.book_token = book_token
        self.technical_detail = technical_detail or message


def tahot_book_code_from_ruf_code(ruf_code: str) -> str | None:
    return _RUF_TO_TAHOT.get((ruf_code or "").upper())


def ruf_code_from_tahot_code(tahot_code: str) -> str | None:
    """Bridge for ``HebrewAnalysisBundle.passage`` — TAHOT's own book code
    (e.g. ``"1Sa"``) to the RUF code shared with ``textus_kb.books``
    (e.g. ``"1SA"``), which in turn resolves to the canonical OSIS-like
    book id via ``textus_kb.books.RUF_TO_OSIS`` (e.g. ``"1Sam"``). TAHOT
    codes are not always identical to OSIS ids (``"1Sa"``/``"2Sa"`` vs
    ``"1Sam"``/``"2Sam"``, ``"Exo"`` vs ``"Exod"``), so this indirection
    through the RUF code both modules already share is required rather
    than assuming identity.
    """
    book = _BOOK_BY_TAHOT_CODE.get(tahot_code or "")
    return book.ruf_code if book else None


def tahot_book_code_from_alias(alias: str) -> str | None:
    book = _BOOK_BY_ALIAS.get(_fold_book_alias(alias))
    return book.tahot_code if book else None


def parse_hebrew_reference(reference: str) -> tuple[str, int, int, int]:
    text = _normalize_reference_text(reference)
    match = re.match(
        r"^\s*(?P<book>.+?)\s+(?P<chapter>\d+)\s*(?:(?:,|:)\s*(?P<start>\d+)(?:\s*-\s*(?P<end>\d+))?)?\s*$",
        text,
    )
    if not match:
        raise HebrewReferenceError(
            f"Nem értelmezhető ószövetségi hivatkozás: {reference}",
            technical_detail=f"Invalid Hebrew reference: {reference!r}",
        )
    book_token = (match.group("book") or "").strip()
    tahot_book = tahot_book_code_from_alias(book_token)
    if tahot_book is None:
        raise HebrewReferenceError(
            f"Az ószövetségi könyv rövidítése nem azonosítható: {book_token}",
            book_token=book_token,
            technical_detail=f"Unknown Hebrew book: {reference!r}",
        )
    verse_start = match.group("start")
    if verse_start is None:
        raise HebrewReferenceError(
            f"Adj meg versszámot is az ószövetségi elemzéshez: {reference}",
            book_token=book_token,
            technical_detail=f"Missing verse in Hebrew reference: {reference!r}",
        )
    chapter = int(match.group("chapter"))
    start = int(verse_start)
    end = int(match.group("end") or start)
    if start > end:
        raise HebrewReferenceError(
            f"Fordított verstartomány: {start}-{end}",
            book_token=book_token,
            technical_detail=f"Invalid reversed Hebrew verse range: {reference!r}",
        )
    return tahot_book, chapter, start, end


def _normalize_reference_text(reference: str) -> str:
    text = unicodedata.normalize("NFKC", reference or "")
    return (
        text.replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )


def _fold_book_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    asciiish = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^0-9a-z]+", "", asciiish.casefold())


def _build_book_aliases() -> dict[str, HebrewBook]:
    aliases: dict[str, HebrewBook] = {}
    for book in OT_BOOKS:
        candidates = (
            book.ruf_code,
            book.tahot_code,
            book.abbr_hu,
            book.name_hu,
            *book.aliases,
        )
        for candidate in candidates:
            folded = _fold_book_alias(candidate)
            if folded:
                aliases[folded] = book
    return aliases


_BOOK_BY_ALIAS = _build_book_aliases()
_RUF_TO_TAHOT = {book.ruf_code: book.tahot_code for book in OT_BOOKS}
_BOOK_BY_TAHOT_CODE = {book.tahot_code: book for book in OT_BOOKS}
