""""Kommentárok" fül -- valódi, magyar-first kommentárolvasó a Commentary
Knowledge Base fölött (jelenleg Calvin + JFB + Matthew Henry, de a UI
semmit nem tételez fel a forrásszámról vagy -nevekről -- ld. lentebb).

READER-ELVŰ ÚJRATERVEZÉS (2026-09-03): a korábbi, section-szintű
kártyalista (minden verselem külön nagy kártya, ismétlődő mű/szerző/
relation sorokkal) helyett EGYSZERRE EGY kommentárforrás olvasási
felülete nyílik meg, ahol a forráshoz tartozó összes releváns canonical
section egyetlen összefüggő, passage-sorrendbe rendezett szövegfolyamként
jelenik meg -- ld. ``_render_family_reader``. A retrieval maga
(``CommentaryRepository.sections_for_passage``, mindig exact/range-
overlap, sosem FTS/semantic) és a section/chunk-modell VÁLTOZATLAN; csak
a megjelenítési réteg lett olvasóközpontú. Egy section a readerben sem
olvad össze mesterségesen mással -- mindegyik továbbra is a saját
section_id-jával azonosítható, és a fordítási cache is section-szintű
marad (ld. ``commentary_translation_service``).

Magyar-first: a reader nyelvi módja alapértelmezetten magyar. Cache-elt
fordítású sectionök azonnal magyarul jelennek meg; a hiányzókhoz a reader
tetején egyetlen, jól látható "lefordítás" gomb van (SOHA nem generál
automatikusan oldalmegnyitáskor) -- ez az EGYETLEN generatív AI-hívási
pont ezen a fülön a "Kommentárok összehasonlítása" mellett. "Eredeti
angol" módban mindig a kanonikus forrásszöveg jelenik meg, provider-hívás
nélkül.

Forrásközpontú UI: a kommentárforrások ("family"-k) egy kompakt
segmented-control-lal választhatók (John Calvin / Jamieson–Fausset–Brown
/ Matthew Henry), egyszerre csak egy reader nyitva. A csoportosítás
KULCSA mindig metaadatból (``work_id`` névtér-előtag) származik, sosem
egy adott könyv aktuális contributorjából -- egy jövőbeli negyedik
korpusz importálásakor módosítás nélkül megjelenik, saját csoportjában.
A megjelenítendő NÉV egy kis, kurált táblázatból jön a már ismert
forrásokhoz (``_SOURCE_FAMILY_DISPLAY_NAMES_HU``), egyébként a
ténylegesen jelenlévő contributor-nevekből származtatva -- sosem
összeomlik egy ismeretlen forrásnál. A könyv-szintű, bibliográfiailag
pontos contributor attribúció (pl. "David Brown" a JFB
"Jamieson–Fausset–Brown" család alatt) megmarad, de csak akkor jelenik
meg külön, ha ténylegesen eltér a family megjelenítendő nevétől.

A "Kommentárok összehasonlítása" (compare) egy külön, explicit
AI-szintézis funkció, vizuálisan és funkcionálisan elkülönítve a fenti
közvetlen olvasótól -- saját, könyv-szintű, több-forrásos kijelölővel
(ld. ``_render_source_filter``), amelynek ``enabled_sources`` szerződése
(book-level contributor nevek halmaza) változatlan, így a
``commentary_compare.py`` grounding-logikáját ez a kör egyáltalán nem
érinti.
"""

from __future__ import annotations

from typing import Any, Callable, MutableMapping, Sequence

import streamlit as st

import commentary_translation_service
from commentary_compare import render_commentary_compare_section
from textus_kb import commentary_runtime
from textus_kb.canonical_reference import CanonicalReference, CanonicalReferenceError
from textus_kb.repositories.commentary_repository import (
    CommentaryRepository,
    CommentarySectionDetail,
    CommentarySectionResult,
    primary_contributor_name,
)
from ui_components import (
    action_row,
    render_context_summary,
    render_info_panel,
    render_work_section,
    work_surface,
)

# Full, technical relation-tier labels -- used ONLY inside the demoted
# "Forrásadatok" provenance block (task item 9), never in the main
# reading flow any more (ld. _reader_badge_text for the reading-flow-
# level, deliberately much quieter badge concept).
_RELATION_TIER_LABELS_HU: dict[str, str] = {
    "exact_passage": "pontos találat",
    "containing_section": "tágabb szakasz tartalmazza",
    "partial_overlap": "részleges átfedés",
    "broader_context": "tágabb kontextus",
}

# Subtle in-flow badges -- shown ONLY when genuinely worth flagging
# (task item 10): a section covering a WIDER span than the query, or an
# explicitly parallel (not primary) passage link. The common, expected
# case (exact/partial-overlap + primary) gets no badge at all.
_READER_BADGE_LABELS_HU: dict[str, str] = {
    "containing_section": "Tágabb kommentált szakasz",
    "broader_context": "Tágabb kommentált szakasz",
}
_READER_PARALLEL_BADGE_HU = "Párhuzamos hely"

_STATUS_REASON_LABELS_HU: dict[str, str] = {
    "database_missing": "A Commentary adatbázis (commentary.sqlite3) még nincs legenerálva.",
    "database_unopenable": "A Commentary adatbázis nem nyitható meg.",
    "schema_incompatible": "A Commentary adatbázis sémája nem kompatibilis a jelenlegi verzióval.",
    "storage_not_configured": "A Commentary adatbázis nincs helyben, és a távoli tárhely sincs beállítva.",
    "download_failed": "A Commentary adatbázis letöltése a távoli tárhelyről nem sikerült.",
    "download_empty": "A Commentary adatbázis letöltése üres választ adott.",
    "database_checksum_mismatch": "A letöltött Commentary adatbázis ellenőrzőösszege nem egyezik.",
    "write_failed": "A Commentary adatbázis helyi mentése nem sikerült.",
    "metadata_validation_failed": "A letöltött Commentary adatbázis tartalma nem egyezik a várt éles verzióval.",
}

_BUILD_HINT = (
    "Build parancs: `python scripts/build_commentary_database.py "
    "--combined-fetch --qa` (vagy `--combined`, ha a nyers forrásfájlok "
    "már helyben vannak a `data/raw/` alatt)."
)

_CACHE_PASSAGE_KEY = "_commentary_ui_cached_passage"
_CACHE_RESULTS_KEY = "_commentary_ui_cached_results"
_FILTER_STATE_KEY = "_commentary_ui_source_filter"  # compare's own multi-select only
_READER_FAMILY_KEY = "_commentary_ui_reader_family"
_READER_LANG_KEY_PREFIX = "_commentary_ui_reader_lang_"
_READER_LANG_HU = "Magyar"
_READER_LANG_EN = "Eredeti angol"
_READER_VISIBLE_CHARS = 1200
_MAX_SECTIONS_PER_READER = 10

# Curated display names for the currently-known source families (keyed by
# the metadata-derived family key, ld. _source_family_key) -- a plain
# presentation-layer lookup. NOT the grouping mechanism itself (that's
# pure work_id metadata, scales to any future family automatically) --
# only the cosmetic label for the three sources this corpus happens to
# have today. Any family key NOT listed here still groups and displays
# correctly via _source_family_display_name's generic, data-derived
# fallback.
_SOURCE_FAMILY_DISPLAY_NAMES_HU: dict[str, str] = {
    "ccel.calvin": "John Calvin",
    "ccel.jfb": "Jamieson–Fausset–Brown",
    "ccel.henry": "Matthew Henry",
}

# OSIS-style canonical book id (ld. textus_kb.books.BOOKS) -> standard
# Hungarian (RÚF-style) abbreviation. Display-only: never touches the
# canonical reference system itself (CanonicalReference / textus_kb.books
# stay completely unmodified) -- ld. _format_passage_hu.
_OSIS_TO_RUF_ABBR_HU: dict[str, str] = {
    "Gen": "1Móz", "Exod": "2Móz", "Lev": "3Móz", "Num": "4Móz", "Deut": "5Móz",
    "Josh": "Józs", "Judg": "Bír", "Ruth": "Ruth", "1Sam": "1Sám", "2Sam": "2Sám",
    "1Kgs": "1Kir", "2Kgs": "2Kir", "1Chr": "1Krón", "2Chr": "2Krón", "Ezra": "Ezsd",
    "Neh": "Neh", "Esth": "Eszt", "Job": "Jób", "Ps": "Zsolt", "Prov": "Péld",
    "Eccl": "Préd", "Song": "Én", "Isa": "Ézs", "Jer": "Jer", "Lam": "JSir",
    "Ezek": "Ez", "Dan": "Dán", "Hos": "Hós", "Joel": "Jóel", "Amos": "Ámós",
    "Obad": "Abd", "Jonah": "Jón", "Mic": "Mik", "Nah": "Náh", "Hab": "Hab",
    "Zeph": "Zof", "Hag": "Hag", "Zech": "Zak", "Mal": "Mal",
    "Matt": "Mt", "Mark": "Mk", "Luke": "Lk", "John": "Jn", "Acts": "ApCsel",
    "Rom": "Róm", "1Cor": "1Kor", "2Cor": "2Kor", "Gal": "Gal", "Eph": "Ef",
    "Phil": "Fil", "Col": "Kol", "1Thess": "1Thessz", "2Thess": "2Thessz",
    "1Tim": "1Tim", "2Tim": "2Tim", "Titus": "Tit", "Phlm": "Filem", "Heb": "Zsid",
    "Jas": "Jak", "1Pet": "1Pt", "2Pet": "2Pt", "1John": "1Jn", "2John": "2Jn",
    "3John": "3Jn", "Jude": "Júd", "Rev": "Jel",
}

# OSIS-style canonical book id -> full, spelled-out Hungarian book title
# (standard RÚF/Károli-style naming) -- used ONLY for the "A {book}
# kommentárjának szerzője: {contributor}" note (task item 8), which needs
# a readable name rather than the terse abbreviation above. Display-only,
# same non-authoritative-fallback contract as _OSIS_TO_RUF_ABBR_HU.
_OSIS_TO_FULL_TITLE_HU: dict[str, str] = {
    "Gen": "1Mózes", "Exod": "2Mózes", "Lev": "3Mózes", "Num": "4Mózes", "Deut": "5Mózes",
    "Josh": "Józsué könyve", "Judg": "Bírák könyve", "Ruth": "Ruth könyve",
    "1Sam": "1Sámuel könyve", "2Sam": "2Sámuel könyve", "1Kgs": "1Királyok könyve",
    "2Kgs": "2Királyok könyve", "1Chr": "1Krónikák könyve", "2Chr": "2Krónikák könyve",
    "Ezra": "Ezsdrás könyve", "Neh": "Nehémiás könyve", "Esth": "Eszter könyve",
    "Job": "Jób könyve", "Ps": "Zsoltárok könyve", "Prov": "Példabeszédek könyve",
    "Eccl": "Prédikátor könyve", "Song": "Énekek éneke", "Isa": "Ézsaiás könyve",
    "Jer": "Jeremiás könyve", "Lam": "Jeremiás siralmai", "Ezek": "Ezékiel könyve",
    "Dan": "Dániel könyve", "Hos": "Hóseás könyve", "Joel": "Jóel könyve",
    "Amos": "Ámós könyve", "Obad": "Abdiás könyve", "Jonah": "Jónás könyve",
    "Mic": "Mikeás könyve", "Nah": "Náhum könyve", "Hab": "Habakuk könyve",
    "Zeph": "Zofóniás könyve", "Hag": "Aggeus könyve", "Zech": "Zakariás könyve",
    "Mal": "Malakiás könyve",
    "Matt": "Máté evangéliuma", "Mark": "Márk evangéliuma", "Luke": "Lukács evangéliuma",
    "John": "János evangéliuma", "Acts": "Apostolok cselekedetei",
    "Rom": "Rómaiakhoz írt levél", "1Cor": "1Korinthusi levél", "2Cor": "2Korinthusi levél",
    "Gal": "Galatákhoz írt levél", "Eph": "Efezusiakhoz írt levél",
    "Phil": "Filippiekhez írt levél", "Col": "Kolosséiakhoz írt levél",
    "1Thess": "1Thesszalonikaiakhoz írt levél", "2Thess": "2Thesszalonikaiakhoz írt levél",
    "1Tim": "1Timóteushoz írt levél", "2Tim": "2Timóteushoz írt levél",
    "Titus": "Tituszhoz írt levél", "Phlm": "Filemonhoz írt levél",
    "Heb": "Zsidókhoz írt levél", "Jas": "Jakab levele", "1Pet": "1Péter levele",
    "2Pet": "2Péter levele", "1John": "1János levele", "2John": "2János levele",
    "3John": "3János levele", "Jude": "Júdás levele", "Rev": "Jelenések könyve",
}


def _primary_contributor(contributors: tuple[str, ...]) -> str:
    """UI-facing wrapper around ``commentary_repository.
    primary_contributor_name`` (shared with ``commentary_compare.py``, so
    the compare source-selection groups results the exact same way this
    module does) — adds this module's own "unknown author" fallback label."""
    return primary_contributor_name(contributors) or "Ismeretlen szerző"


def _query_canonical(passage: str) -> str | None:
    try:
        return CanonicalReference.parse(passage).canonical_string()
    except CanonicalReferenceError:
        return None


def _format_passage_hu(canonical: str) -> str:
    """Human-friendly Hungarian passage display (e.g. ``Mt 5,1–12``) for a
    single canonical/OSIS-style reference string -- display-only, never
    changes what's stored/matched internally (still plain ``canonical``
    everywhere else: provenance, retrieval, compare). Falls back to the
    raw canonical string for any book id not in the abbreviation table,
    so nothing is ever hidden -- just less prettily formatted."""
    try:
        ref = CanonicalReference.parse(canonical)
    except CanonicalReferenceError:
        return canonical
    abbr = _OSIS_TO_RUF_ABBR_HU.get(ref.book_id)
    if not abbr:
        return canonical
    if ref.start_chapter == ref.end_chapter:
        if ref.start_verse == ref.end_verse:
            return f"{abbr} {ref.start_chapter},{ref.start_verse}"
        return f"{abbr} {ref.start_chapter},{ref.start_verse}–{ref.end_verse}"
    return (
        f"{abbr} {ref.start_chapter},{ref.start_verse}"
        f"–{ref.end_chapter},{ref.end_verse}"
    )


def _format_passage_list_hu(passages: Sequence[str]) -> str:
    formatted = [_format_passage_hu(p) for p in passages if p]
    return ", ".join(formatted) if formatted else "—"


def _source_family_key(work_id: str) -> str:
    """Metadata-derived source-family grouping key: the shared namespace
    prefix of ``work_id`` (e.g. ``ccel.calvin``, ``ccel.jfb``,
    ``ccel.henry`` for the real corpus -- ld. ``commentary_sqlite``
    import's ``<namespace>.<family>.work.<book>`` convention, verified
    identical across every book from one source and distinct across
    sources). Never a per-book contributor name -- a future 4th corpus
    following the same import convention groups itself automatically,
    with zero code changes here."""
    parts = (work_id or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else (work_id or "")


def _source_family_display_name(
    family_key: str, contributor_names: Sequence[str]
) -> str:
    """Primary, human-facing source name for a family (task requirement:
    "fő forrásnév", e.g. "Jamieson–Fausset–Brown" instead of whichever
    single book's contributor happens to be showing). Curated for the
    currently-known families; for anything else, derives a reasonable
    name straight from the real contributor(s) actually present -- never
    crashes or falls back to a raw internal key."""
    curated = _SOURCE_FAMILY_DISPLAY_NAMES_HU.get(family_key)
    if curated:
        return curated
    names = [n for n in contributor_names if n]
    if not names:
        return "Ismeretlen forrás"
    if len(names) == 1:
        return names[0]
    return " – ".join(names)


def _book_display_name_hu(sections: Sequence[CommentarySectionResult]) -> str:
    """Full Hungarian book name derived from the first parseable
    canonical passage among ``sections`` -- falls back to the corpus's
    own (English) work_title when no passage parses, so nothing is ever
    hidden."""
    for s in sections:
        for p in (s.primary_passages or s.canonical_passages):
            try:
                ref = CanonicalReference.parse(p)
            except CanonicalReferenceError:
                continue
            name = _OSIS_TO_FULL_TITLE_HU.get(ref.book_id)
            if name:
                return name
    return sections[0].work_title if sections else ""


def _book_contributor_note(
    book_name_hu: str, family_display: str, contributor: str
) -> str | None:
    """"A {book} kommentárjának szerzője: {contributor}" -- but only when
    the book-level contributor actually differs from the family's own
    display name (task item 8: Calvin must never show "John Calvin /
    John Calvin"); returns None when there's nothing worth adding."""
    if not contributor or contributor == family_display or not book_name_hu:
        return None
    return f"A {book_name_hu} kommentárjának szerzője: {contributor}"


def _passage_relation_key(
    result: CommentarySectionResult, query_canonical: str | None
) -> str | None:
    """Which relation label applies to THIS query passage specifically --
    a section can carry both primary and parallel links, so this is
    resolved per query, never as a blanket "this section is primary"."""
    if query_canonical and query_canonical in result.primary_passages:
        return "primary"
    if query_canonical and query_canonical in result.parallel_passages:
        return "parallel"
    if result.primary_passages and not result.parallel_passages:
        return "primary"
    if result.parallel_passages and not result.primary_passages:
        return "parallel"
    return None


def _reader_badge_text(
    result: CommentarySectionResult, relation_key: str | None
) -> str | None:
    """A single, subtle in-flow badge -- ``None`` in the common/expected
    case (exact or partial-overlap match on the primary passage), so the
    reading flow isn't interrupted by technical relevance-tier noise on
    every paragraph (task item 10)."""
    if relation_key == "parallel":
        return _READER_PARALLEL_BADGE_HU
    return _READER_BADGE_LABELS_HU.get(result.relation_type)


def interleave_by_source(
    results: list[CommentarySectionResult],
) -> list[CommentarySectionResult]:
    """Diversity pass on top of the repository's already tier/primary-
    sorted list.

    ``CommentaryRepository.sections_for_passage`` already returns results
    ordered by (relevance tier, span, primary-before-parallel, document
    order) -- that ordering is fully preserved here. Within each tier this
    additionally round-robins across distinct sources so one commentator
    with many overlapping same-tier hits never crowds the others out of
    the family-selector ordering. Structurally mirrors ``context_builder.
    _interleave_commentary_by_work`` / ``_round_robin_by_work``'s two-level
    (tier, then per-tier round-robin) approach.

    This RELEVANCE order feeds the family-selector's own ordering and the
    compare filter -- the reader's actual READING order within one
    selected family is a separate, later pass (ld.
    ``_sort_sections_for_reading``), sorted by chapter/verse instead.
    """
    tier_order: list[str] = []
    tiers: dict[str, list[CommentarySectionResult]] = {}
    for item in results:
        tier = item.relation_type
        if tier not in tiers:
            tiers[tier] = []
            tier_order.append(tier)
        tiers[tier].append(item)

    interleaved: list[CommentarySectionResult] = []
    for tier in tier_order:
        source_order: list[str] = []
        by_source: dict[str, list[CommentarySectionResult]] = {}
        for item in tiers[tier]:
            source = _primary_contributor(item.contributors)
            if source not in by_source:
                by_source[source] = []
                source_order.append(source)
            by_source[source].append(item)
        while any(by_source[s] for s in source_order):
            for source in source_order:
                bucket = by_source[source]
                if bucket:
                    interleaved.append(bucket.pop(0))
    return interleaved


def _group_book_sources_by_family(
    results: list[CommentarySectionResult],
) -> list[tuple[str, str, list[str]]]:
    """Ordered ``(family_key, family_display_name, book_contributor_
    names)`` groups for the COMPARE source filter -- purely derived from
    ``results`` metadata (work_id namespace + contributors), never a
    hardcoded source list. Each family may list more than one book-level
    contributor name when the current passage spans multiple books from
    the same source family."""
    family_order: list[str] = []
    family_names: dict[str, list[str]] = {}
    for r in results:
        key = _source_family_key(r.work_id)
        name = _primary_contributor(r.contributors)
        bucket = family_names.setdefault(key, [])
        if key not in family_order:
            family_order.append(key)
        if name not in bucket:
            bucket.append(name)
    return [
        (key, _source_family_display_name(key, family_names[key]), family_names[key])
        for key in family_order
    ]


def _group_results_by_family(
    results: list[CommentarySectionResult],
) -> list[tuple[str, str, list[CommentarySectionResult]]]:
    """Ordered ``(family_key, family_display_name, sections)`` groups --
    drives the reader's family selector options. First-appearance order
    preserved from the already relevance-sorted/interleaved input, never
    re-sorted by family name."""
    family_order: list[str] = []
    buckets: dict[str, list[CommentarySectionResult]] = {}
    for r in results:
        key = _source_family_key(r.work_id)
        if key not in buckets:
            buckets[key] = []
            family_order.append(key)
        buckets[key].append(r)
    groups: list[tuple[str, str, list[CommentarySectionResult]]] = []
    for key in family_order:
        items = buckets[key]
        names: list[str] = []
        for item in items:
            name = _primary_contributor(item.contributors)
            if name not in names:
                names.append(name)
        groups.append((key, _source_family_display_name(key, names), items))
    return groups


def _select_reader_family(available_keys: Sequence[str], requested: str | None) -> str:
    """Pure fallback logic for the reader's family selection: returns
    ``requested`` if it's still a valid, currently-available family key,
    else the first available one (e.g. right after a passage change that
    made the previously-open family disappear). Returns "" only when
    there are no available families at all."""
    if not available_keys:
        return ""
    if requested in available_keys:
        return requested
    return available_keys[0]


def _reading_sort_key(result: CommentarySectionResult) -> tuple[int, int, int, int, int]:
    passages = result.primary_passages or result.canonical_passages
    if not passages:
        return (1, 0, 0, 0, 0)
    try:
        ref = CanonicalReference.parse(passages[0])
    except CanonicalReferenceError:
        return (1, 0, 0, 0, 0)
    return (0, ref.start_chapter, ref.start_verse, ref.end_chapter, ref.end_verse)


def _sort_sections_for_reading(
    sections: list[CommentarySectionResult],
) -> list[CommentarySectionResult]:
    """Stable chapter/verse-ascending READING order within one selected
    family -- distinct from the relevance-tier RETRIEVAL order
    (``interleave_by_source``), which stays used for family-selector
    ordering and the compare filter. Ties (e.g. an exact whole-range hit
    and a same-start per-verse hit) keep their original relative order."""
    return sorted(sections, key=_reading_sort_key)


def _sections_with_text(
    sections: Sequence[CommentarySectionResult],
) -> list[CommentarySectionResult]:
    """Drops structural, zero-chunk parent sections (e.g. a chapter-level
    container whose actual commentary text lives entirely in its
    per-verse child sections) -- nothing to read there, so nothing to
    show in the reader."""
    return [s for s in sections if s.chunk_count > 0]


def _group_family_sections_by_book(
    sections: Sequence[CommentarySectionResult],
) -> list[tuple[str, str, list[CommentarySectionResult]]]:
    """Ordered ``(work_id, work_title, sections)`` groups within one
    family's reader -- almost always a single book for a normal passage
    query; a wide multi-book query can still show more than one, each
    with its own book-level heading (task item 3/7: never repeat the
    work title per section, only once per book group)."""
    order: list[str] = []
    buckets: dict[str, list[CommentarySectionResult]] = {}
    titles: dict[str, str] = {}
    for s in sections:
        if s.work_id not in buckets:
            buckets[s.work_id] = []
            order.append(s.work_id)
            titles[s.work_id] = s.work_title
        buckets[s.work_id].append(s)
    return [(wid, titles[wid], buckets[wid]) for wid in order]


def _split_for_progressive_disclosure(text: str, max_chars: int) -> tuple[str, str]:
    """(visible, rest) -- splits at the last paragraph break at/before
    ``max_chars``, falling back to a sentence- then word-boundary, so
    nothing is ever cut mid-word. Returns ``(text, "")`` when it already
    fits (task item 4: short sections show in full, nothing is
    artificially truncated after a few lines)."""
    stripped = (text or "").strip()
    if len(stripped) <= max_chars:
        return stripped, ""
    cut = stripped.rfind("\n\n", 0, max_chars)
    if cut == -1:
        period_cut = stripped.rfind(". ", 0, max_chars)
        if period_cut != -1:
            cut = period_cut + 1
    if cut == -1:
        cut = stripped.rfind(" ", 0, max_chars)
    if cut <= 0:
        cut = max_chars
    return stripped[:cut].rstrip(), stripped[cut:].strip()


def _translate_missing_sections(
    sections: Sequence[CommentarySectionResult],
    *,
    generate_fn: Callable[..., str],
    provider_model: str,
    repository: CommentaryRepository,
    database_path: str | None,
) -> tuple[int, int]:
    """Translates only the sections in ``sections`` that don't already
    have a cached Hungarian translation, reusing the EXISTING per-section
    ``commentary_translation_service.get_or_create_translation`` (cache
    key/policy/store all unchanged this round) -- an already-cached
    section is never re-requested from the provider. Returns
    ``(succeeded, failed)`` counts; a section that turns out to already be
    cached counts toward neither.

    Real bug found via manual smoke test (2026-09-03, Róm 8,1-4, 4
    missing Calvin sections translated in one click): every call after
    the first failed with a false "provider unavailable" because
    ``generate_text`` (app.py) enforces a cooldown BETWEEN calls by
    default. ``bypass_cooldown=True`` for every call after the first
    fixes this -- matches ``generate_text``'s own documented "same
    button press" convention (see its docstring)."""
    succeeded = 0
    failed = 0
    for index, section in enumerate(sections):
        outcome = commentary_translation_service.get_or_create_translation(
            section.section_id,
            generate_fn=generate_fn,
            provider_model=provider_model,
            repository=repository,
            database_path=database_path,
            bypass_cooldown=index > 0,
        )
        if outcome.status == "generated":
            succeeded += 1
        elif outcome.status != "cached":
            failed += 1
    return succeeded, failed


def _get_repository() -> CommentaryRepository:
    """Single, monkeypatchable seam for DB access -- production always uses
    the default (production) path; tests point this at an isolated store."""
    return CommentaryRepository()


def _translation_database_path() -> str | None:
    """Single, monkeypatchable seam mirroring ``_get_repository`` for the
    (separate, derived) translation cache -- ``None`` means "use
    ``commentary_translation_service``'s own default production path";
    tests point this at an isolated store so they never touch the real
    ``data/generated/commentary_translations.sqlite3``."""
    return None


def _get_status() -> commentary_runtime.CommentaryRuntimeStatus:
    """Single, monkeypatchable seam mirroring ``_get_repository`` for the
    runtime availability check. Uses ``ensure_status`` (not the plain
    ``get_status``) -- the same single production choke point Exegézis /
    Eredeti szöveg / Kortörténet also call (ld. ``grounded_generation.py``,
    ``bible_engine/original_language_analysis.py``) -- so whichever
    module the user reaches FIRST on a freshly deployed instance
    transparently provisions the production DB from private Supabase
    Storage if it isn't on the local filesystem yet; opening this tab is
    never a precondition. After that first successful download it
    persists locally for the lifetime of the running instance, so every
    subsequent call from any module is a pure local hit, no further
    network I/O."""
    return commentary_runtime.ensure_status()


def _fetch_results(passage: str) -> list[CommentarySectionResult]:
    repo = _get_repository()
    return interleave_by_source(repo.sections_for_passage(passage))


def _sources_present(results: list[CommentarySectionResult]) -> list[str]:
    """Distinct BOOK-LEVEL source (contributor) names in first-seen order
    -- purely data-derived, never a hardcoded corpus list. Unchanged
    granularity (still book-level, not family-level): this is exactly
    the identity ``commentary_compare.py`` groups evidence by, so the
    compare integration's ``enabled_sources`` contract stays untouched
    by the reader redesign above it."""
    seen: set[str] = set()
    ordered: list[str] = []
    for r in results:
        name = _primary_contributor(r.contributors)
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _ensure_results(
    passage: str,
    *,
    session: MutableMapping[str, Any] | None = None,
    force: bool = False,
) -> list[CommentarySectionResult]:
    """Per-passage cached retrieval. ``session`` defaults to the real
    ``st.session_state`` in production; tests may inject a plain dict to
    exercise the caching logic without a live Streamlit context."""
    store: MutableMapping[str, Any] = st.session_state if session is None else session
    if (
        force
        or store.get(_CACHE_PASSAGE_KEY) != passage
        or _CACHE_RESULTS_KEY not in store
    ):
        store[_CACHE_RESULTS_KEY] = _fetch_results(passage)
        store[_CACHE_PASSAGE_KEY] = passage
    return store[_CACHE_RESULTS_KEY]


_UNAVAILABLE_USER_TITLE = "A kommentárgyűjtemény most nem érhető el"
_UNAVAILABLE_USER_BODY = (
    "A klasszikus kommentárok jelenleg nem tölthetők be. Próbáld újra "
    "később; a Textus többi része addig is zavartalanul használható."
)


def _is_developer_environment() -> bool:
    """Helyi fejlesztői futtatás-e (fail-closed: kétes esetben nem)."""
    try:
        from auth_config import is_local_runtime

        return bool(is_local_runtime())
    except Exception:  # noqa: BLE001
        return False


def _render_missing_db(status: commentary_runtime.CommentaryRuntimeStatus) -> None:
    """Az adatbázis elérhetetlensége — közérthető tájékoztatás.

    A felhasználó nem kap buildparancsot vagy belső okot (UI/UX-audit
    2026-11-23, V4). A technikai ok és a buildparancs csak helyi fejlesztői
    futtatáskor jelenik meg, külön feliratban."""
    render_info_panel(
        title=_UNAVAILABLE_USER_TITLE,
        body=_UNAVAILABLE_USER_BODY,
        tone="warning",
    )
    if _is_developer_environment():
        reason = _STATUS_REASON_LABELS_HU.get(status.reason, status.reason)
        st.caption(f"Fejlesztői részletek: {reason} {_BUILD_HINT}")


def _render_no_passage() -> None:
    render_info_panel(
        title="Nincs kiválasztva igeszakasz",
        body="Add meg az igeszakaszt az „Igehely” fülön, mielőtt a kommentárokat böngészed.",
        tone="neutral",
    )


def _render_no_match(passage: str) -> None:
    render_info_panel(
        title="Nincs kommentár-találat",
        body=(
            f"A jelenleg elérhető kommentárforrások egyike sem tartalmaz közvetlen "
            f"kommentárt erre a helyre: {passage}. A rendszer nem tér át szövegkeresésre "
            "vagy MI-pótlásra — csak a valódi, hozzárendelt kommentárszakaszokat mutatja."
        ),
        tone="neutral",
    )


def _render_source_filter(results: list[CommentarySectionResult]) -> set[str]:
    """Renders the COMPARE feature's own multi-select: one checkbox per
    source FAMILY, labeled with the family's primary display name; the
    concrete book-level contributor(s) actually present for the current
    passage show as a small caption underneath. Returns the set of
    enabled BOOK-LEVEL contributor names -- ``commentary_compare.py``
    groups evidence by exactly this identity, so its grounding logic is
    untouched by this round's reader redesign. Deliberately separate from
    the reader's own single-select family tab above (task item 11: the
    two are visually and functionally distinct features)."""
    groups = _group_book_sources_by_family(results)
    filter_state: dict[str, bool] = st.session_state.setdefault(_FILTER_STATE_KEY, {})
    if groups:
        cols = st.columns(len(groups))
        for col, (family_key, family_display, book_names) in zip(cols, groups):
            with col:
                filter_state[family_key] = st.checkbox(
                    family_display,
                    value=filter_state.get(family_key, True),
                    key=f"commentary_source_filter_{family_key}",
                )
                st.caption(", ".join(book_names))
    enabled_families = {key for key, enabled in filter_state.items() if enabled}
    enabled_book_names: set[str] = set()
    for family_key, _display, book_names in groups:
        if family_key in enabled_families:
            enabled_book_names.update(book_names)
    return enabled_book_names


def _render_reader_family_selector(family_options: list[tuple[str, str]]) -> str:
    """Compact segmented-control family picker (task item 2) -- exactly
    one open at a time. Persists the user's choice across reruns via
    session_state, but only overrides it when the previously-selected
    family is no longer available (e.g. right after a passage change) --
    ld. ``_select_reader_family`` for the pure fallback logic."""
    keys = [key for key, _display in family_options]
    labels = dict(family_options)
    requested = st.session_state.get(_READER_FAMILY_KEY)
    if requested not in keys:
        st.session_state[_READER_FAMILY_KEY] = _select_reader_family(keys, requested)
    chosen = st.segmented_control(
        "Kommentárforrás",
        options=keys,
        format_func=lambda key: labels.get(key, key),
        key=_READER_FAMILY_KEY,
        label_visibility="collapsed",
    )
    return chosen if chosen in keys else _select_reader_family(keys, None)


def _render_reader_section(
    result: CommentarySectionResult,
    *,
    detail: CommentarySectionDetail | None,
    query_canonical: str | None,
    lang: str,
    translation_cache: dict[str, "commentary_translation_service.TranslationOutcome"],
) -> None:
    """One passage's worth of reading content inside an open family
    reader -- a light passage heading (+ a subtle badge only when the
    relation genuinely deserves flagging), then the actual text (HU or
    EN per the reader's own language mode), long text truncated at a
    paragraph boundary behind a "Teljes kommentárszakasz megnyitása"
    expander -- the label names what's actually behind it (the complete
    canonical section, never shortened/summarized), since "Tovább
    olvasom" read as misleadingly casual for what can be a very long
    source text. No card border, no repeated work/contributor/relation
    caption per section (task item 7) -- those live at the book/reader
    level instead."""
    passages = result.primary_passages or result.canonical_passages
    passage_display = _format_passage_list_hu(passages)
    relation_key = _passage_relation_key(result, query_canonical)
    badge = _reader_badge_text(result, relation_key)

    heading = f"**{passage_display}**"
    if badge:
        heading += f"   ·  _{badge}_"
    st.markdown(heading)

    if lang == _READER_LANG_HU:
        outcome = translation_cache.get(result.section_id)
        if outcome is not None and outcome.status == "cached":
            visible, rest = _split_for_progressive_disclosure(outcome.text, _READER_VISIBLE_CHARS)
            st.write(visible)
            if rest:
                with st.expander("Teljes kommentárszakasz megnyitása"):
                    st.write(rest)
        else:
            st.caption(
                "Ehhez a szakaszhoz még nincs magyar fordítás -- a fenti "
                "gombbal elkészíthető."
            )
        return

    if detail is None or not detail.chunks:
        st.caption("A szakasz szövege jelenleg nem érhető el.")
        return
    text = "\n\n".join(chunk.plain_text for chunk in detail.chunks)
    visible, rest = _split_for_progressive_disclosure(text, _READER_VISIBLE_CHARS)
    st.write(visible)
    if rest:
        with st.expander("Teljes kommentárszakasz megnyitása"):
            st.write(rest)


def _render_family_provenance(
    sections: Sequence[CommentarySectionResult],
    details: dict[str, CommentarySectionDetail | None],
) -> None:
    """Single, demoted "Forrásadatok" expander for the whole reader (task
    item 9) -- structured per-section provenance (work, edition, section,
    canonical reference, source locator, upstream URL, rights, external
    id, relation type), nothing lost, just not competing with the actual
    reading surface above."""
    if not sections:
        return
    with st.expander("Forrásadatok"):
        for section in sections:
            detail = details.get(section.section_id)
            passages = section.primary_passages or section.canonical_passages
            st.markdown(f"**{_format_passage_list_hu(passages)}**")
            source_locator = (
                detail.chunks[0].source_locator if detail and detail.chunks else "—"
            )
            rights = (section.rights_status or "—") + (
                f" ({section.license})" if section.license else ""
            )
            render_context_summary(
                [
                    ("Mű", section.work_title),
                    ("Kiadás (edition)", section.edition_id),
                    ("Szakasz (section)", section.section_id),
                    ("Kanonikus hely", ", ".join(section.canonical_passages) or "—"),
                    ("Forrás locator", source_locator),
                    ("Upstream forrás", section.source_url or "—"),
                    ("Azonosító", section.external_id or "—"),
                    ("Jogi státusz", rights),
                    (
                        "Kapcsolat típusa",
                        _RELATION_TIER_LABELS_HU.get(section.relation_type, section.relation_type),
                    ),
                ]
            )
            if section.rights_note:
                st.caption(section.rights_note)


@st.fragment
def _render_family_reader(
    family_key: str,
    family_display: str,
    sections: list[CommentarySectionResult],
    *,
    query_canonical: str | None,
    generate_fn: Callable[..., str] | None,
    resolve_model_fn: Callable[[str], str] | None,
) -> None:
    """The whole reading surface for ONE selected source family: a
    reader-level HU/EN language toggle, an optional single "translate the
    missing parts" action, then every relevant section rendered as one
    continuous, passage-ordered flow grouped by book -- never one giant
    card per verse (task items 3/4/5/6).

    ``@st.fragment`` (2026-09-04, translation-rerun UI fix): the HU/EN
    radio and the "translate the missing parts" button live INSIDE this
    function, so without fragment isolation, either one triggers
    Streamlit's default FULL app.py rerun -- during which Streamlit dims
    the entire page and briefly shows the previous frame's stale DOM
    (every other tab's leftover elements included) until the whole
    script finishes re-executing. Wrapping this function is enough to
    scope both the rerun AND the dim/stale-frame effect to just this
    reader surface: a click on either widget now only re-executes THIS
    function body, in place, inside the same ``work_surface`` container
    it was already rendered in -- the rest of the page (other tabs'
    already-rendered content, scroll position, the family/source
    selector and the "Kommentárok összehasonlítása" section below,
    both OUTSIDE this fragment) never re-renders and never dims. No
    other behavior changes: retrieval, the translation cache/policy, and
    every session_state key used here (the per-family language radio,
    the translation-cache dict) are read/written exactly as before --
    fragments share the full script's session_state, they only isolate
    which DOM subtree reruns."""
    repo = _get_repository()
    db_path = _translation_database_path()

    readable = _sort_sections_for_reading(_sections_with_text(sections))
    shown, hidden = readable[:_MAX_SECTIONS_PER_READER], readable[_MAX_SECTIONS_PER_READER:]

    st.markdown(f"### {family_display}")

    if not shown:
        render_info_panel(
            title="Nincs önálló szöveg ehhez a forráshoz",
            body="A visszakapott szakaszok csak szerkezeti elemek, saját szöveg nélkül.",
            tone="neutral",
        )
        return

    lang_key = f"{_READER_LANG_KEY_PREFIX}{family_key}"
    if lang_key not in st.session_state:
        st.session_state[lang_key] = _READER_LANG_HU
    # Language radio + its explanatory caption share one row (radio on the
    # left) instead of stacking, so the reader header takes less vertical
    # space -- st.columns already collapses back to stacked full-width on
    # a narrow viewport (Streamlit's own responsive breakpoint), so this
    # needs no extra layout handling for small screens.
    lang_col, lang_caption_col = st.columns([1, 2], vertical_alignment="center", gap="small")
    with lang_col:
        lang = st.radio(
            "Nyelv",
            options=(_READER_LANG_HU, _READER_LANG_EN),
            key=lang_key,
            horizontal=True,
            label_visibility="collapsed",
        )
    with lang_caption_col:
        if lang == _READER_LANG_HU:
            st.caption(
                "MI által készített magyar fordítás — az eredeti angol szöveg gépi "
                "fordítása, nem összefoglalás."
            )

    # Cache-only lookup per shown section, once -- feeds both the
    # missing-translation action and each section's own HU rendering, so
    # nothing is queried twice per section in the common case.
    translation_cache: dict[str, commentary_translation_service.TranslationOutcome] = {
        s.section_id: commentary_translation_service.get_translation(
            s.section_id, repository=repo, database_path=db_path
        )
        for s in shown
    }
    missing = [s for s in shown if translation_cache[s.section_id].status != "cached"]

    if lang == _READER_LANG_HU and missing:
        label = (
            "Magyar fordítás elkészítése"
            if len(shown) == 1
            else f"A releváns részek lefordítása magyarra ({len(missing)} hiányzik)"
        )
        if st.button(
            label,
            key=f"commentary_translate_family_{family_key}",
            disabled=generate_fn is None,
            # Same primary CTA look as the compare section's own
            # "Összehasonlítás készítése" button (ld. commentary_compare.
            # render_commentary_compare_section) -- Streamlit's built-in
            # `type="primary"` is the shared styling mechanism already
            # used there, so this is visual-only: no new CSS, no change
            # to the click handling, spinner, or disabled logic below.
            type="primary",
        ):
            provider_model = (
                resolve_model_fn(commentary_translation_service.TRANSLATION_TAB_LABEL)
                if resolve_model_fn is not None
                else ""
            )
            with st.spinner("Fordítás készítése…"):
                _succeeded, failed = _translate_missing_sections(
                    missing,
                    generate_fn=generate_fn,
                    provider_model=provider_model,
                    repository=repo,
                    database_path=db_path,
                )
            # Refresh the cache-only lookups so the render below picks
            # up newly-generated translations within this same run --
            # an already-cached section was never re-requested above.
            translation_cache = {
                s.section_id: commentary_translation_service.get_translation(
                    s.section_id, repository=repo, database_path=db_path
                )
                for s in shown
            }
            if failed:
                st.warning(
                    f"{failed} szakasz fordítása nem sikerült; ezek egyelőre "
                    "angolul érhetők el."
                )

    details: dict[str, CommentarySectionDetail | None] = {
        s.section_id: repo.section_detail(s.section_id) for s in shown
    }

    for _work_id, work_title, book_sections in _group_family_sections_by_book(shown):
        st.caption(work_title)
        contributor = _primary_contributor(book_sections[0].contributors) if book_sections else ""
        note = _book_contributor_note(
            _book_display_name_hu(book_sections), family_display, contributor
        )
        if note:
            st.caption(note)
        for section in book_sections:
            _render_reader_section(
                section,
                detail=details.get(section.section_id),
                query_canonical=query_canonical,
                lang=lang,
                translation_cache=translation_cache,
            )

    if hidden:
        st.caption(
            f"+ {len(hidden)} további, kevésbé releváns {family_display} szakasz "
            "nem jelenik meg."
        )

    _render_family_provenance(shown, details)


def render_commentary_panel(
    *,
    generate_fn: Callable[..., str] | None = None,
    resolve_model_fn: Callable[[str], str] | None = None,
) -> None:
    """Renders the "Kommentárok" tab's entire content.

    ``generate_fn`` powers two independent, explicit-click-only generative
    actions: the "Kommentárok összehasonlítása" section at the bottom, and
    the reader's own single "lefordítás" action (ld.
    ``_render_family_reader``) -- never auto-triggered on page load or
    passage change. ``resolve_model_fn`` (app.py's own tab-based
    model-routing lookup) is optional, translation-only provenance
    metadata -- when omitted, translations are still generated and cached
    normally, just without a recorded provider/model name.
    """
    render_work_section(
        title="Kommentárok",
        body=(
            "Klasszikus kommentárok az aktuális igeszakaszhoz -- forrásonként "
            "kiválasztva olvashatók. Az eredeti angol szöveg mindig közvetlenül "
            "a forrásból származik; a magyar szöveg MI-fordítás (nem "
            "összefoglalás) ugyanarról a szövegről."
        ),
        context="Textusműhely",
    )

    status = _get_status()
    if not status.available:
        with work_surface("commentary_unavailable"):
            _render_missing_db(status)
        return

    passage = (st.session_state.get("last_igehely") or "").strip()
    if not passage:
        with work_surface("commentary_no_passage"):
            _render_no_passage()
        return

    with work_surface("commentary_results"):
        with action_row("commentary_refresh"):
            if st.button("Frissítés", key="commentary_refresh_btn"):
                _ensure_results(passage, force=True)
                st.rerun()

        results = _ensure_results(passage)
        if not results:
            _render_no_match(passage)
            return

        query_canonical = _query_canonical(passage)
        st.caption(
            f"Aktuális textus: {_format_passage_hu(query_canonical) if query_canonical else passage}"
        )

        family_groups = _group_results_by_family(results)
        family_options = [(key, display) for key, display, _items in family_groups]
        selected_key = _render_reader_family_selector(family_options)
        selected_items = next(
            (items for key, _display, items in family_groups if key == selected_key), []
        )
        selected_display = dict(family_options).get(selected_key, selected_key)

        if selected_items:
            _render_family_reader(
                selected_key,
                selected_display,
                selected_items,
                query_canonical=query_canonical,
                generate_fn=generate_fn,
                resolve_model_fn=resolve_model_fn,
            )

    with work_surface("commentary_compare_section"):
        st.caption(
            "Ez a fenti közvetlen olvasótól elkülönülő funkció: a kiválasztott "
            "forrásokból MI-szintézist készít, nem a nyers forrásszöveget mutatja."
        )
        enabled_sources = _render_source_filter(results)
        ordered_enabled_sources = [s for s in _sources_present(results) if s in enabled_sources]
        render_commentary_compare_section(
            passage=passage,
            passage_display=passage,
            enabled_sources=ordered_enabled_sources,
            generate_fn=generate_fn,
        )


__all__ = ["render_commentary_panel", "interleave_by_source"]

# NOTE: the underscored helpers below are intentionally still
# module-private (no public API contract) but are imported directly by
# tests/test_commentary_ui.py -- consistent with this repo's existing
# pattern of testing Streamlit UI modules via their pure helper functions
# rather than full rendering: `_get_repository`, `_get_status`,
# `_fetch_results`, `_ensure_results`, `_sources_present`,
# `_primary_contributor`, `_passage_relation_key`, `_query_canonical`,
# `_source_family_key`, `_source_family_display_name`,
# `_group_results_by_family`, `_group_book_sources_by_family`,
# `_format_passage_hu`, `_format_passage_list_hu`, `_select_reader_family`,
# `_sort_sections_for_reading`, `_sections_with_text`,
# `_group_family_sections_by_book`, `_book_display_name_hu`,
# `_book_contributor_note`, `_split_for_progressive_disclosure`,
# `_translate_missing_sections`, `_reader_badge_text`.
