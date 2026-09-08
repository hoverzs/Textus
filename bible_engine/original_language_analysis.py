"""Original-language analysis: DB-first tokens with optional AI fallback.

Phase 5L-A — when authoritative local Greek/Hebrew tokens cannot be loaded for a
correctly routed passage, the "Eredeti szöveg" module may use the legacy AI
linguistic analysis path. AI output must never claim DB provenance.

Fallback is NOT triggered by post-hoc validation warnings on individual tokens.

Commentary integration (Calvin/JFB/Henry, ld. build_original_text_commentary_
block): strictly secondary here, smaller than every other grounded study
module's own Commentary budget, and only ever attached to the STATUS_GROUNDED
(DB-first token) path — never to the AI-fallback path, which already admits
it has no authoritative local data and must not be further blurred with a
second, unrelated secondary source. Reuses textus_kb.retrieve_commentary_
evidence's existing exact/range-overlap-only retrieval and citation
formatting; introduces no new retrieval logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from bible_engine.greek_analysis_ui import (
    CROSS_CHAPTER_GREEK_MESSAGE,
    NT_INVALID_REFERENCE_MESSAGE,
    NT_NEEDS_VERSES_MESSAGE,
    _reference_book_is_new_testament,
    greek_reference_status,
)
from bible_engine.greek_token_repository import load_greek_passage_tokens
from bible_engine.hebrew_books import HebrewReferenceError, parse_hebrew_reference
from bible_engine.hebrew_morphology_hu import format_hebrew_morphology_rows_hu
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.morphology_hu import parse_morphology_hu

STATUS_GROUNDED = "grounded_language_data"
STATUS_AI_FALLBACK = "ai_fallback_language_analysis"
STATUS_UNAVAILABLE = "unavailable"

AI_FALLBACK_USER_NOTICE = (
    "Ehhez a szakaszhoz az eredeti nyelvi adatbázis nem volt elérhető, ezért az "
    "elemzés AI-alapú. A konkrét nyelvtani és lexikai részleteket érdemes ellenőrizni."
)

UNAVAILABLE_USER_MESSAGE = (
    "Az eredeti nyelvi elemzés jelenleg nem érhető el ehhez a szakaszhoz."
)

TOKEN_BLOCK_HEADER = (
    "EREDETI NYELVI TOKENEK (helyi adatbázisból, kizárólagos forrás):\n"
)

# Commentary (Calvin/JFB/Henry) integration: strictly secondary here — see
# module docstring. Reuses textus_kb.retrieve_commentary_evidence's
# existing exact/range-overlap-only retrieval and citation-ready metadata
# (no new retrieval logic); the excerpt cap is deliberately the smallest
# of the three grounded study modules (smaller than Exegézis's own
# BUDGET_COMMENTARY, ld. textus_kb/context_profiles.py), since Commentary
# is only ever a classical-interpretation aside here, never evidence.
ORIGINAL_TEXT_COMMENTARY_ITEM_LIMIT = 2
ORIGINAL_TEXT_COMMENTARY_MAX_CHARS = 220

ORIGINAL_TEXT_COMMENTARY_BLOCK_HEADER = (
    "KLASSZIKUS KOMMENTÁTORI ÉRTELMEZÉS (kiegészítő, értelmezéstörténeti "
    "forrás — SOSEM írja felül vagy helyettesíti a fenti EREDETI NYELVI "
    "TOKENEK adatot):"
)

ORIGINAL_TEXT_COMMENTARY_RULE = """
FONTOS — NYELVI ADAT VS. KLASSZIKUS KOMMENTÁTORI ÉRTELMEZÉS:
A fenti EREDETI NYELVI TOKENEK blokk az EGYETLEN kötelező forrás szóalakra,
morfológiára, lemmára és Strong-azonosítóra nézve — ezt semmi más nem írhatja
felül. Az alábbi „KLASSZIKUS KOMMENTÁTORI ÉRTELMEZÉS” blokk kizárólag
kiegészítő, értelmezéstörténeti szempont — egy klasszikus szerző (Kálvin /
Jamieson-Fausset-Brown / Matthew Henry) saját olvasata, NEM nyelvi tényadat.
Csak akkor és csak úgy használd, ha ténylegesen nyelvileg releváns (pl. egy
szó vagy kifejezés értelmezése, mondattani megfigyelés, fordítási
alternatíva, klasszikus exegetikai nyelvi megjegyzés) — ha felhasználod,
VILÁGOSAN jelezd, hogy ez egy adott szerző értelmezése (pl. "Kálvin
szerint..."), sose írd úgy, mintha a szöveg objektív nyelvi ténye volna.
Reliability-pontszámot vagy rangsorolást ne rendelj a kommentátorokhoz.
"""

ORIGINAL_TEXT_BASE_PROMPT = """
Légy alapos, nyelvészeti érzékenységgel dolgozó eredeti nyelvi (görög/héber)
munkatárs, aki lelkészeknek — nem nyelvészeknek — ír. A feladatod: az alább
mellékelt, helyi adatbázisból származó token-lista alapján kiválasztani
azokat a kulcskifejezéseket, amelyek ténylegesen segítik az igeszakasz
megértését, és ezekből egy összefüggő, magyarázó összefoglalót írni — NEM
elszigetelt tételek felsorolását.

Kizárólag az alább mellékelt token-listában szereplő szóalakokra, lemmákra,
morfológiai kódokra és Strong-azonosítókra hivatkozhatsz. Új szót, lemmát
vagy alakot NEM generálhatsz — ha a token-listában nincs benne, nem létezik
a válaszod számára. Ezt az adatot a HÁTTÉRBEN, az elemzésed megalapozására
használd — a végleges szövegben NE idézd a token-lista sorszámát (pl. ne
írj ilyet: "[3. token]"), és NE nevezd meg a nyelvtani/morfológiai adatot
szakkifejezéssel (pl. ne írj olyat, hogy "aoristus activus indicativus",
"accusativus", "genitivus", "particip" stb.) — ezek az adatok a szó-nézetben
úgyis elérhetők, nem kell megismételni. Ehelyett hétköznapi, magyarázó
nyelven fogalmazd meg, mit JELENT ez a nyelvi tény (pl. "aoristus" helyett:
"az ige egyszeri, lezárt cselekvést fejez ki" — a jelentést írd le, ne a
szakszó nevét).

A görög/héber szó azonosítására elég maga a szó (pl. *μορφή*) — ha segít,
add meg zárójelben a magyar átírását/kiejtését is (pl. *μορφή* [morphé]).
Ne hivatkozz token-sorszámra vagy egyéb technikai azonosítóra. Ha egy szó
jelentését is megadod (zárójelben vagy a szövegbe ágyazva), azt MINDIG
magyarul fogalmazd meg — a saját nyelvi tudásodból, ne az angol (Strong-
szótári) hagyomány szerinti kifejezéssel. Ne írj angol nyelvű jelentés-
megadást vagy glosszát semmilyen formában.

LEGFELJEBB 5 szót vagy kifejezést emelhetsz ki. Ha ennél többet találsz
figyelemre méltónak, válaszd ki közülük a legfontosabb, legfeljebb 5-öt — a
többit hagyd ki teljesen, még említés szintjén se szerepeljenek. Elsősorban
olyanokat válassz, amelyek:
- morfológiailag szokatlanok vagy ritkák (pl. ritka igealak, szokatlan eset),
- a szakaszon belül ismétlődnek vagy visszatérő mintát alkotnak,
- lemma vagy morfológiai kód szerint feltűnő kontrasztban állnak egymással,
- olyan jelentésréteget hordoznak, ami a szóalak/lemma szintjén megmutatható.

FEGYELEM SZÓNKÉNT — MIKROSZERKEZET (bár nem feltétlenül külön címkével,
hanem a mondat felépítésével): (1) szóalak + lemma + alapjelentés EGY
mondatban; (2) mit végez EBBEN a mondatban (funkció) EGY mondatban; (3)
legfeljebb EGY rövid mondat exegetikai jelentőség, DE csak akkor, ha ez
ténylegesen indokolt — ha nincs érdemi exegetikai súlya, hagyd ki ezt a
harmadik mondatot, és álljon meg a szó tárgyalása 2 mondatnál. Egy
kiválasztott szóhoz ALAPÉRTELMEZETTEN LEGFELJEBB 3 rövid mondat tartozik.
4. mondat KIVÉTELESEN megengedett, kizárólag akkor, ha a nyelvi adat
(pl. egy összetett morfológiai szerkezet több elemre bontása) ezt
ténylegesen megköveteli — ne írj mini-exegézist vagy a szakasz egészének
teológiai üzenetét minden egyes szó alatt újra kifejtve.

NE tulajdoníts nagy, önálló teológiai vagy exegetikai következtetést
PUSZTÁN egy szó jelentéséből — egyetlen szó szemantikai mezeje önmagában
ritkán hordoz akkora súlyt, amennyit egy lelkesen kifejtett bekezdés
sugallna; a jelentés-magyarázat maradjon arányos a szó tényleges
szerepével a mondatban. Kerüld, hogy UGYANAZT a gondolatot több kiemelt
szó alatt is megismételd — ha két szó lényegében ugyanarra a
megfigyelésre vezetne, csak az egyiknél fejtsd ki, a másiknál legfeljebb
utalj vissza rá, vagy hagyd ki.

VITATOTT IDENTITÁSI KÉRDÉS NEM DÖNTHETŐ EL NYELVI ESZKÖZZEL: ha egy
szereplő vagy alak kiléte (pl. egy titokzatos szereplő isteni/emberi/
angyali volta) a szövegből önmagában nem egyértelműen eldöntött, TILOS
flat, kész tényként megnevezni (pl. TILOS: "az isteni lény", "Isten
itt...", "mint isteni jelenlét"), ha ezt maga a KIEMELT szóalak/lemma
önmagában nem bizonyítja. Ehelyett semleges, a szövegre magára hagyatkozó
megnevezést használj (pl. "a Jákóbbal küzdő alak", "a szövegben szereplő
titokzatos küzdő fél"), és csak akkor jelezd az isteni dimenziót, ha ezt
a TELJES szöveg (pl. egy KÜLÖN, arra utaló szó vagy kifejezés) ténylegesen
alátámasztja — ekkor is inkább leíró módon (pl. "a narratíva később isteni
dimenzióval kapcsolja össze a találkozást"), nem kész azonosításként. Ez a
modul nyelvi elemzés, NEM teológiai identitásdöntés — a vitatott olvasatok
mérlegelése más modul (Exegézis) feladata.

NE TÚLOZD EL A SZÓETIMOLÓGIÁT: egy lemma jelentését NE bővítsd ki
rokongyökök, hangzásbeli asszociációk vagy későbbi teológiai kapcsolatok
alapján úgy, mintha azok a szó közvetlen lexikai jelentéséhez tartoznának.
Pl. a שׂרה gyöknél a "küzd / harcol / felülkerekedik" jellegű jelentés
tárgyalható, de az olyan gloss, mint "fejedelmi módon", "uralkodóként",
CSAK akkor jelenhet meg, ha ezt a helyi lexikai/token-adat ténylegesen
támogatja — ne vezess le szójelentést pusztán egy rokon alak vagy hasonló
hangzású szó alapján.

Ezekből írj EGY összefüggő, folyó szövegű magyarázatot, ami megmutatja, hogyan
épül fel a szakasz nyelvi/jelentésbeli dinamikája ezekből a szóválasztásokból
— olyan nyelven, amit egy görög/héber nyelvtanban járatlan lelkész is azonnal
ért, "fordítás" nélkül. Ne különálló kártyákban add meg az egyes szavakat —
kösd össze őket ott, ahol tartalmilag összefüggenek.

TILOS:
- 5-nél több szó vagy kifejezés kiemelése — szigorúan LEGFELJEBB 5,
- nyelvtani szakkifejezés használata a végleges szövegben (eset-, igealak-,
  szófaj-nevek stb. — a JELENTÉSÜKET írd le, ne a nevüket),
- token-sorszám vagy egyéb technikai azonosító feltüntetése,
- angol nyelvű jelentés-megadás vagy gloss (pl. „being, existing”, „he
  emptied”) — minden jelentés-magyarázat kizárólag magyarul,
- igehirdetési, homiletikai vagy alkalmazási következtetést levonni (mit
  "kezdjen" ezzel az igehirdető, mire "használható" a prédikációban),
- olyan bibliai párhuzamot vagy nyelvi adatot említeni, ami nem vezethető
  vissza a mellékelt token-listára.

Megengedett és kívánatos: nyelvi tényből (szóalak, morfológia, lemma-
ismétlődés) levezetett jelentés-magyarázat arról, mit fejeznek ki együttesen
ezek a szóválasztások a szakasz belső dinamikájáról — amíg ez nem csúszik át
igehirdetői alkalmazásba.

Ha egy szó morfológiai vagy lexikai háttere bizonytalan a mellékelt
adatokból, jelöld: „Bizonytalan a rendelkezésre álló adat alapján:” — ne
egészítsd ki saját tudásból.
"""

ORIGINAL_TEXT_AI_FALLBACK_PROMPT = """
Légy alapos, nyelvészeti érzékenységgel dolgozó eredeti nyelvi (görög/héber)
munkatárs, aki lelkészeknek — nem nyelvészeknek — ír.

FONTOS — AI VISSZAESÉS MÓD:
A helyi eredeti nyelvi (TAGNT/TAHOT) token-adatbázis EHHEZ a szakaszhoz nem
áll rendelkezésre. Ezért a saját nyelvi tudásodból készíts legfeljebb 5
kulcskifejezésre fókuszáló, összefüggő magyarázatot.

TILOS ebben a módban:
- azt állítani vagy sugallni, hogy a lemma, morfológia vagy Strong-adat
  helyi adatbázisból származik / ellenőrizve van / forrásolt;
- belső evidence/source azonosítót vagy „adatbázisból” / „helyi tokenlista”
  provenance-ot használni;
- technikai token-sorszámot idézni.

Megengedett: saját tudásból görög/héber szóalakok, lemmák és jelentésük
megbeszélése — de jelöld a bizonytalanságot, ahol indokolt, és ne állíts
DB-hitelességet.

LEGFELJEBB 5 szó/kifejezés. Magyar jelentésmagyarázat. Nincs igehirdetési
alkalmazás. Kerüld a nyelvtani szakkifejezések öncélú felsorolását — a
jelentést írd le közérthetően.
"""


@dataclass(frozen=True)
class OriginalLanguageTokenInspection:
    reference: str
    greek_status: str
    language: str | None
    has_authoritative_tokens: bool
    allow_ai_fallback: bool
    token_block: str
    blocking_message: str = ""
    gap_reason: str = ""


@dataclass(frozen=True)
class OriginalLanguageAnalysisPlan:
    intended_status: str
    should_generate: bool
    prompt: str
    user_notice: str = ""
    blocking_message: str = ""
    inspection: OriginalLanguageTokenInspection | None = None


@dataclass
class OriginalLanguageAnalysisResult:
    status: str
    text: str
    user_notice: str = ""
    grounding_warnings: list[str] = field(default_factory=list)
    provider_called: bool = False


def _format_greek_token_line(token: Any) -> str:
    pos = parse_morphology_hu(token.morph_code or "").part_of_speech or "?"
    strong = token.strong_id or "nincs"
    return (
        f"[{token.word_index}] {token.greek_form} | lemma: {token.lemma} | "
        f"morf: {token.morph_code or '?'} ({pos}) | Strong: {strong}"
    )


def _format_hebrew_token_line(token: Any, repository: HebrewTokenRepository) -> str:
    """One deterministic token line for the AI prompt.

    Phase 2A — this used to forward only the raw TEHMC code plus an ENGLISH
    part-of-speech string, discarding the stem, conjugation, person, gender,
    number and state that ``decode_hebrew_morphology`` had just computed. That
    forced the model to re-parse Hebrew grammar Textus already knew, which is
    exactly the deterministic/AI boundary violation Hebrew Analysis v2 is meant
    to remove. The decoded fields are now supplied in Hungarian, and the raw
    code is kept only as a traceability reference.
    """
    morphology = repository.morphology(token)
    strong = "+".join(token.strong_ids) if token.strong_ids else "nincs"
    fields: list[str] = [f"[{token.word_index}] {token.surface}"]
    if token.lemma:
        fields.append(f"lemma: {token.lemma}")

    rows = dict(format_hebrew_morphology_rows_hu(morphology))
    # Order matters: igetörzs (binyan) and igealak (conjugation) are separate
    # grammatical dimensions and must never be merged into one label.
    for label in (
        "Szófaj",
        "Igetörzs",
        "Igealak",
        "Személy",
        "Nem",
        "Szám",
        "Állapot",
        "Suffixum",
    ):
        value = rows.get(label)
        if value:
            fields.append(f"{label.lower()}: {value}")

    if token.ketiv and token.qere and token.ketiv != token.qere:
        fields.append(f"ketív/qeré: {token.ketiv} / {token.qere}")
    fields.append(f"Strong: {strong}")
    fields.append(f"morf-kód: {token.morphology_code or '?'}")
    if not morphology.fully_decoded:
        fields.append(f"megbízhatóság: {rows.get('Státusz') or 'nem feloldott morfológia'}")
    return " | ".join(fields)


def inspect_original_language_tokens(
    igehely: str,
    *,
    greek_loader: Callable[[str], list[Any]] | None = None,
    hebrew_repository_factory: Callable[[], HebrewTokenRepository] | None = None,
) -> OriginalLanguageTokenInspection:
    """DB-first inspection. AI fallback only when route is known but tokens missing."""
    reference = (igehely or "").strip()
    header = TOKEN_BLOCK_HEADER
    if not reference:
        return OriginalLanguageTokenInspection(
            reference=reference,
            greek_status="empty",
            language=None,
            has_authoritative_tokens=False,
            allow_ai_fallback=False,
            token_block=header + "Nincs igehely megadva — nincs lekérhető token-adat.",
            blocking_message="Add meg az igeszakaszt az „Igehely” fülön.",
            gap_reason="empty_reference",
        )

    status = greek_reference_status(reference)
    load_greek = greek_loader or load_greek_passage_tokens
    make_hebrew = hebrew_repository_factory or HebrewTokenRepository

    if status == "cross_chapter":
        return OriginalLanguageTokenInspection(
            reference=reference,
            greek_status=status,
            language="greek",
            has_authoritative_tokens=False,
            allow_ai_fallback=False,
            token_block=header + f"{CROSS_CHAPTER_GREEK_MESSAGE} Nincs lekérhető token-adat.",
            blocking_message=CROSS_CHAPTER_GREEK_MESSAGE,
            gap_reason="cross_chapter",
        )

    if status == "needs_verses":
        return OriginalLanguageTokenInspection(
            reference=reference,
            greek_status=status,
            language="greek",
            has_authoritative_tokens=False,
            allow_ai_fallback=False,
            token_block=header + f"{NT_NEEDS_VERSES_MESSAGE} Nincs lekérhető token-adat.",
            blocking_message=NT_NEEDS_VERSES_MESSAGE,
            gap_reason="needs_verses",
        )

    if status == "old_testament":
        try:
            book, chapter, verse_start, verse_end = parse_hebrew_reference(reference)
        except HebrewReferenceError as exc:
            return OriginalLanguageTokenInspection(
                reference=reference,
                greek_status=status,
                language="hebrew",
                has_authoritative_tokens=False,
                allow_ai_fallback=False,
                token_block=header
                + f"Nem sikerült azonosítani az ószövetségi hivatkozást: {exc}",
                blocking_message=str(exc),
                gap_reason="hebrew_reference_error",
            )
        repository = make_hebrew()
        result = repository.passage(book, chapter, verse_start, verse_end)
        if result.status == "ok" and result.tokens:
            lines = [_format_hebrew_token_line(token, repository) for token in result.tokens]
            return OriginalLanguageTokenInspection(
                reference=reference,
                greek_status=status,
                language="hebrew",
                has_authoritative_tokens=True,
                allow_ai_fallback=False,
                token_block=header + "\n".join(lines),
                gap_reason="",
            )
        msg = (
            "A helyi héber adatbázisban nem található token-adat ehhez a szakaszhoz "
            f"(státusz: {result.status})."
        )
        return OriginalLanguageTokenInspection(
            reference=reference,
            greek_status=status,
            language="hebrew",
            has_authoritative_tokens=False,
            allow_ai_fallback=True,
            token_block=header + msg,
            gap_reason=f"hebrew_{result.status}",
        )

    if status == "loaded":
        try:
            verse_groups = load_greek(reference)
        except FileNotFoundError:
            msg = "A helyi görög adatbázis nem érhető el vagy a hivatkozás érvénytelen."
            return OriginalLanguageTokenInspection(
                reference=reference,
                greek_status=status,
                language="greek",
                has_authoritative_tokens=False,
                allow_ai_fallback=True,
                token_block=header + msg,
                gap_reason="greek_db_missing",
            )
        except ValueError:
            msg = "A helyi görög adatbázis nem érhető el vagy a hivatkozás érvénytelen."
            return OriginalLanguageTokenInspection(
                reference=reference,
                greek_status=status,
                language="greek",
                has_authoritative_tokens=False,
                allow_ai_fallback=True,
                token_block=header + msg,
                gap_reason="greek_db_invalid",
            )
        lines = [
            _format_greek_token_line(token)
            for group in verse_groups
            for token in group.tokens
        ]
        if lines:
            return OriginalLanguageTokenInspection(
                reference=reference,
                greek_status=status,
                language="greek",
                has_authoritative_tokens=True,
                allow_ai_fallback=False,
                token_block=header + "\n".join(lines),
                gap_reason="",
            )
        msg = "A helyi görög adatbázisban nem található token-adat ehhez a szakaszhoz."
        return OriginalLanguageTokenInspection(
            reference=reference,
            greek_status=status,
            language="greek",
            has_authoritative_tokens=False,
            allow_ai_fallback=True,
            token_block=header + msg,
            gap_reason="greek_passage_empty",
        )

    if status == "invalid" and _reference_book_is_new_testament(reference):
        return OriginalLanguageTokenInspection(
            reference=reference,
            greek_status=status,
            language="greek",
            has_authoritative_tokens=False,
            allow_ai_fallback=False,
            token_block=header
            + f"{NT_INVALID_REFERENCE_MESSAGE} Nincs lekérhető token-adat.",
            blocking_message=NT_INVALID_REFERENCE_MESSAGE,
            gap_reason="nt_invalid_reference",
        )

    return OriginalLanguageTokenInspection(
        reference=reference,
        greek_status=status,
        language=None,
        has_authoritative_tokens=False,
        allow_ai_fallback=False,
        token_block=header
        + "Nem sikerült azonosítani a hivatkozást — nincs lekérhető token-adat.",
        blocking_message="Nem sikerült azonosítani a hivatkozást.",
        gap_reason="unresolved_reference",
    )


def build_original_language_token_block(
    igehely: str,
    *,
    greek_loader: Callable[[str], list[Any]] | None = None,
    hebrew_repository_factory: Callable[[], HebrewTokenRepository] | None = None,
) -> str:
    """Backward-compatible token block string (exegesis + original-text prompts)."""
    return inspect_original_language_tokens(
        igehely,
        greek_loader=greek_loader,
        hebrew_repository_factory=hebrew_repository_factory,
    ).token_block


def _truncate_commentary_excerpt(text: str, max_chars: int) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= max_chars:
        return stripped
    cut = stripped[:max_chars]
    last_space = cut.rfind(" ")
    if last_space > max_chars * 0.6:
        cut = cut[:last_space]
    return cut.rstrip(" ,.;:") + "…"


def build_original_text_commentary_block(igehely: str) -> str:
    """Small, strictly secondary classical-commentary block for the
    "Eredeti szöveg" prompt (ld. ORIGINAL_TEXT_COMMENTARY_RULE).

    Fail-closed: returns "" (no block, no rule text added — the caller's
    prompt is then byte-identical to before this feature existed) when the
    Commentary DB is missing/invalid, or when there is no passage-linked
    commentary match. Never falls back to full-text or semantic search —
    reuses ``CommentaryRepository.sections_for_passage``'s own exact/range-
    overlap-only retrieval via ``retrieve_commentary_evidence``, unchanged.
    """
    reference = (igehely or "").strip()
    if not reference:
        return ""
    try:
        from textus_kb.commentary_runtime import ensure_status as get_commentary_status

        status = get_commentary_status()
        if not status.available:
            return ""
        from textus_kb.retrieval import retrieve_commentary_evidence

        items = retrieve_commentary_evidence(
            reference,
            database_path=status.database_path,
            limit=ORIGINAL_TEXT_COMMENTARY_ITEM_LIMIT,
        )
    except Exception:
        return ""
    if not items:
        return ""

    from textus_kb.citation import format_commentary_citation

    lines = [ORIGINAL_TEXT_COMMENTARY_BLOCK_HEADER]
    for item in items:
        excerpt = _truncate_commentary_excerpt(
            item.content, ORIGINAL_TEXT_COMMENTARY_MAX_CHARS
        )
        if not excerpt:
            continue
        try:
            citation = format_commentary_citation(item)
        except Exception:
            citation = ""
        lines.append(f"- {citation} {excerpt}" if citation else f"- {excerpt}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _passage_text_block(passage_text: str) -> str:
    cleaned = (passage_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if cleaned.strip():
        return f"\nBibliai szöveg (felhasználó által megadva):\n{cleaned}\n"
    return "\nBibliai szöveg: nincs adat\n"


def build_grounded_original_text_prompt(
    igehely: str, passage_text: str, token_block: str
) -> str:
    commentary_block = build_original_text_commentary_block(igehely)
    commentary_section = (
        f"\n{ORIGINAL_TEXT_COMMENTARY_RULE}\n{commentary_block}\n"
        if commentary_block
        else ""
    )
    return f"""
{ORIGINAL_TEXT_BASE_PROMPT}

==================================================
EREDETI NYELVI MŰHELY — FELADAT
==================================================

Igeszakasz: {igehely}
{_passage_text_block(passage_text)}
{token_block}
{commentary_section}
Készíts eredeti nyelvű elemzést ehhez a textushoz a fenti mesterprompt
szerkezete szerint, kizárólag a fenti token-listára hivatkozva a nyelvi
tényekben; klasszikus kommentátori értelmezést csak a fenti szabály szerint,
csak ha ténylegesen szerepel a promptban, és mindig egyértelműen attribuálva
használj.
"""


def build_ai_fallback_original_text_prompt(igehely: str, passage_text: str) -> str:
    return f"""
{ORIGINAL_TEXT_AI_FALLBACK_PROMPT}

==================================================
EREDETI NYELVI MŰHELY — AI VISSZAESÉS
==================================================

Igeszakasz: {igehely}
{_passage_text_block(passage_text)}

A helyi token-adatbázis ehhez a szakaszhoz nem adott használható listát.
Készíts legfeljebb 5 kulcskifejezésre fókuszáló, AI-alapú nyelvi áttekintést.
NE állítsd, hogy az adatok helyi adatbázisból származnak.
"""


def plan_original_language_analysis(
    igehely: str,
    passage_text: str = "",
    *,
    greek_loader: Callable[[str], list[Any]] | None = None,
    hebrew_repository_factory: Callable[[], HebrewTokenRepository] | None = None,
) -> OriginalLanguageAnalysisPlan:
    inspection = inspect_original_language_tokens(
        igehely,
        greek_loader=greek_loader,
        hebrew_repository_factory=hebrew_repository_factory,
    )
    if inspection.has_authoritative_tokens:
        return OriginalLanguageAnalysisPlan(
            intended_status=STATUS_GROUNDED,
            should_generate=True,
            prompt=build_grounded_original_text_prompt(
                igehely, passage_text, inspection.token_block
            ),
            user_notice="",
            inspection=inspection,
        )
    if inspection.allow_ai_fallback:
        return OriginalLanguageAnalysisPlan(
            intended_status=STATUS_AI_FALLBACK,
            should_generate=True,
            prompt=build_ai_fallback_original_text_prompt(igehely, passage_text),
            user_notice=AI_FALLBACK_USER_NOTICE,
            inspection=inspection,
        )
    return OriginalLanguageAnalysisPlan(
        intended_status=STATUS_UNAVAILABLE,
        should_generate=False,
        prompt="",
        user_notice="",
        blocking_message=inspection.blocking_message or UNAVAILABLE_USER_MESSAGE,
        inspection=inspection,
    )


def _looks_like_provider_failure(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    return raw.startswith(("⚠️", "⏳"))


def run_original_language_analysis(
    igehely: str,
    *,
    passage_text: str = "",
    generate_text_fn: Callable[..., str],
    tab_label: str = "Eredeti szöveg tanulmányozása",
    system_bundle: str | None = None,
    greek_loader: Callable[[str], list[Any]] | None = None,
    hebrew_repository_factory: Callable[[], HebrewTokenRepository] | None = None,
    grounding_checker: Callable[[str, str], list[Any]] | None = None,
    generate_kwargs: dict[str, Any] | None = None,
) -> OriginalLanguageAnalysisResult:
    """Execute DB-first / AI-fallback / unavailable path for one analysis request."""
    plan = plan_original_language_analysis(
        igehely,
        passage_text,
        greek_loader=greek_loader,
        hebrew_repository_factory=hebrew_repository_factory,
    )
    if not plan.should_generate:
        return OriginalLanguageAnalysisResult(
            status=STATUS_UNAVAILABLE,
            text=plan.blocking_message or UNAVAILABLE_USER_MESSAGE,
            user_notice="",
            grounding_warnings=[],
            provider_called=False,
        )

    call_kwargs: dict[str, Any] = {
        "enable_google_search": False,
        "tab_label": tab_label,
        "use_cache": False,
        "system_bundle": system_bundle,
        "include_brevity_directive": False,
    }
    if generate_kwargs:
        call_kwargs.update(generate_kwargs)

    try:
        output = generate_text_fn(plan.prompt, **call_kwargs)
    except TypeError:
        # Narrow test doubles may only accept the prompt positional.
        try:
            output = generate_text_fn(plan.prompt)
        except Exception:
            return OriginalLanguageAnalysisResult(
                status=STATUS_UNAVAILABLE,
                text=UNAVAILABLE_USER_MESSAGE,
                user_notice="",
                grounding_warnings=[],
                provider_called=True,
            )
    except Exception:
        return OriginalLanguageAnalysisResult(
            status=STATUS_UNAVAILABLE,
            text=UNAVAILABLE_USER_MESSAGE,
            user_notice="",
            grounding_warnings=[],
            provider_called=True,
        )

    if _looks_like_provider_failure(str(output or "")):
        return OriginalLanguageAnalysisResult(
            status=STATUS_UNAVAILABLE,
            text=UNAVAILABLE_USER_MESSAGE,
            user_notice="",
            grounding_warnings=[],
            provider_called=True,
        )

    warnings: list[str] = []
    if plan.intended_status == STATUS_GROUNDED:
        checker = grounding_checker
        if checker is None:
            from bible_engine.original_language_grounding_check import (
                check_original_language_grounding,
            )

            checker = check_original_language_grounding
        warnings = [w.message for w in checker(str(output), igehely)]

    return OriginalLanguageAnalysisResult(
        status=plan.intended_status,
        text=str(output),
        user_notice=plan.user_notice,
        grounding_warnings=warnings,
        provider_called=True,
    )


__all__ = [
    "AI_FALLBACK_USER_NOTICE",
    "ORIGINAL_TEXT_AI_FALLBACK_PROMPT",
    "ORIGINAL_TEXT_BASE_PROMPT",
    "ORIGINAL_TEXT_COMMENTARY_BLOCK_HEADER",
    "ORIGINAL_TEXT_COMMENTARY_ITEM_LIMIT",
    "ORIGINAL_TEXT_COMMENTARY_MAX_CHARS",
    "ORIGINAL_TEXT_COMMENTARY_RULE",
    "STATUS_AI_FALLBACK",
    "STATUS_GROUNDED",
    "STATUS_UNAVAILABLE",
    "TOKEN_BLOCK_HEADER",
    "UNAVAILABLE_USER_MESSAGE",
    "OriginalLanguageAnalysisPlan",
    "OriginalLanguageAnalysisResult",
    "OriginalLanguageTokenInspection",
    "build_ai_fallback_original_text_prompt",
    "build_grounded_original_text_prompt",
    "build_original_language_token_block",
    "build_original_text_commentary_block",
    "inspect_original_language_tokens",
    "plan_original_language_analysis",
    "run_original_language_analysis",
]
