"""RESET 2C — a hétpontos igehirdetési vázlat MI-generálása (candidate-alapú).

Ennek a modulnak KIZÁRÓLAG egy feladata van: a kanonikus, ellenőrizhető
bemenetből (igehely, bibliai szöveg, fordítás, opcionálisan a textus fő
gondolata / fókuszmondat / Textusműhely háttéranyagok) egyetlen AI-hívással
hét, szigorúan validált strukturált pontot előállítani, majd az eredményt a
RESET 2A-ban elkészült adatmodell-függvényeken (`store_generated_arc_
result`, `accept_arc_candidate`, `discard_arc_candidate`, `arc_has_content`)
keresztül eltárolni.

Szándékosan TELJESEN FÜGGETLEN a régi vázlatmotortól és a régi section-
szintű MI-segédektől:
  - nem importál `sermon_outline_engine`-ből semmit (a korábbi, kizárólag
    olvasó `compute_current_passage_context_hash` kapcsolat megszűnt —
    ld. lent, "candidate-identitás" szakasz: a `context_hash` mostantól
    ennek a modulnak SAJÁT, a teljes generálási bemenetet lefedő
    hash-függvényéből származik);
  - nem olvassa és nem írja a régi `sermon_outline`/`basket` mezőket;
  - nem hívja a régi `sermon_workshop_*_ai.py` modulok `suggest_*`/
    `build_*_context`/`has_sufficient_*_material` függvényeit;
  - saját, önálló JSON-kinyerő segédfüggvénnyel dolgozik (nem importálja a
    régi M4 modul hasonló segédjét), hogy ne kösse magát semmilyen régi
    section-szintű MI-segédhez.

Az AI-hívó függvényt (`generate_fn`) a hívó (UI) adja át — ez a modul maga
sosem importálja `app.generate_text`-et, és sosem hív valódi hálózatot a
saját tesztjeiben.

CANDIDATE-IDENTITÁS (szűk szemantikai korrekció, 2026-08-19): a
`context_hash` a ténylegesen a MI-motornak elküldött, a generálási
eredményt érdemben befolyásoló TELJES bemenet determinisztikus
azonosítója — ld. `compute_arc_generation_context_hash()`. Ez az EGYETLEN
kanonikus candidate-identitás: ha a generálás után BÁRMELYIK felhasznált
bemenet megváltozik (igehely, bibliai szöveg, fordítás, a két
főgondolat-mező, vagy bármelyik Textusműhely háttéranyag-mező), a hash
megváltozik, és egy függőben lévő candidate `context_hash_mismatch`
okkal elutasításra kerül elfogadáskor. Korábban (RESET 2C első
változata) a `context_hash` csak a szűk igehely/szöveg/fordítás hármast
azonosította (`sermon_outline_engine.compute_passage_context_hash`) — ez
gyengébb védelem volt, mert egy candidate elfogadható maradt akkor is,
ha időközben pl. a fókuszmondat vagy egy Textusműhely-mező megváltozott,
noha azt a generálás ténylegesen felhasználta.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, MutableMapping

from sermon_workshop_data import _ARC_POINT_KEYS, store_generated_arc_result

GenerateFn = Callable[..., str]

# A hash-payload verziója — ha a figyelembe vett mezők köre valaha bővül/
# szűkül, ezt kötelező növelni, hogy a régi candidate-ek automatikusan
# összemérhetetlenné (context_hash_mismatch) váljanak az új sémával.
ARC_GENERATION_CONTEXT_VERSION = "arc_gen_ctx_v1"


# =============================================================================
# Generálási kontextus — kizárólag ellenőrizhető, aktuális kanonikus bemenet
# =============================================================================


@dataclass(frozen=True)
class ArcGenerationContext:
    reference: str
    passage_text: str
    bible_translation: str
    context_hash: str
    text_main_idea: str = ""
    sermon_main_idea: str = ""
    overview: str = ""
    exegesis: str = ""
    original_text: str = ""
    history: str = ""
    theology: str = ""

    def missing_required_fields(self) -> list[str]:
        """A generáláshoz elengedhetetlen mezők közül melyik hiányzik —
        üres lista, ha minden megvan. A két főgondolat-mező szándékosan
        NEM szerepel itt: hasznos, de nem kötelező bemenet."""
        missing: list[str] = []
        if not self.reference.strip():
            missing.append("igehely")
        if not self.passage_text.strip():
            missing.append("bibliai szöveg")
        if not self.context_hash.strip():
            missing.append("kontextusazonosító")
        return missing

    def is_valid(self) -> bool:
        return not self.missing_required_fields()


def compute_arc_generation_context_hash(context: ArcGenerationContext) -> str:
    """A ténylegesen a MI-motornak elküldött, a generálási eredményt
    érdemben befolyásoló bemenet determinisztikus azonosítója — ez az
    EGYETLEN kanonikus candidate-identitás (ld. modul docstring).

    Kizárólag azokat a mezőket veszi figyelembe, amelyek ténylegesen
    bekerülnek a generálási promptba (`build_arc_generation_prompt`):
    igehely, bibliai szöveg, fordítás, a két opcionális fő gondolat-mező,
    és az öt Textusműhely háttéranyag-mező. SOSEM tartalmaz `generated_
    at`-ot, session-specifikus vagy véletlenszerű adatot, `arc`/
    `arc_meta`/`arc_candidate` tartalmat, legacy `sermon_outline`/basket
    adatot, vagy a válaszból származó bármilyen adatot — ezek egyike sem
    befolyásolja a generálás bemenetét, ezért egyik sem lehet része a
    candidate-identitásnak.

    Stabil: normalizált (`.strip()`-elt) stringek, rögzített kulcssorrendű
    (`sort_keys=True`) JSON-szerializálás, SHA-256. Egy rögzített
    `ARC_GENERATION_CONTEXT_VERSION` is a payload része, hogy a mezőkör
    jövőbeli bővítése ne okozzon hamis egyezést egy régi candidate-tel."""
    payload = {
        "version": ARC_GENERATION_CONTEXT_VERSION,
        "reference": context.reference,
        "passage_text": context.passage_text,
        "bible_translation": context.bible_translation,
        "text_main_idea": context.text_main_idea,
        "sermon_main_idea": context.sermon_main_idea,
        "overview": context.overview,
        "exegesis": context.exegesis,
        "original_text": context.original_text,
        "history": context.history,
        "theology": context.theology,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _first_nonempty_str(session_state: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        val = session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def build_arc_generation_context(
    session_state: Mapping[str, Any],
) -> ArcGenerationContext:
    """A kanonikus generálási bemenet összeállítása.

    Kizárólag a már meglévő, éles adatfolyamban is használt flat session-
    kulcsokból dolgozik (`last_igehely`/`igehely_input`, `passage_text`,
    `bible_translation`, a Textusműhely `overview`/`exegesis`/
    `original_text`/`history`/`theology` mezői) — a régi `sermon_outline`
    és `basket` mezőket EGYÁLTALÁN nem olvassa.

    A `context_hash`-t `compute_arc_generation_context_hash()` állítja
    elő, kizárólag akkor, ha az igehely ÉS a bibliai szöveg is jelen van
    (enélkül a generálás úgysem indulhat) — üres referencia/szöveg esetén
    a `context_hash` is üres marad, hogy `missing_required_fields()`
    helyesen jelezze a hiányt."""
    reference = _first_nonempty_str(session_state, "last_igehely", "igehely_input")
    passage_text = _first_nonempty_str(session_state, "passage_text", "passage_text_input")
    bible_translation = _first_nonempty_str(session_state, "bible_translation") or "RÚF 2014"

    tw = session_state.get("text_workshop")
    tw = tw if isinstance(tw, dict) else {}
    sw = session_state.get("sermon_workshop")
    sw = sw if isinstance(sw, dict) else {}

    def _s(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    context = ArcGenerationContext(
        reference=reference,
        passage_text=passage_text,
        bible_translation=bible_translation,
        context_hash="",
        text_main_idea=_s(tw.get("text_main_idea")),
        sermon_main_idea=_s(sw.get("sermon_main_idea")),
        overview=_first_nonempty_str(session_state, "overview"),
        exegesis=_first_nonempty_str(session_state, "exegesis"),
        original_text=_first_nonempty_str(session_state, "original_text"),
        history=_first_nonempty_str(session_state, "history"),
        theology=_first_nonempty_str(session_state, "theology"),
    )
    if context.reference and context.passage_text:
        context = replace(context, context_hash=compute_arc_generation_context_hash(context))
    return context


# =============================================================================
# Rendszerprompt + válaszséma
# =============================================================================

ARC_SYSTEM_PROMPT = """SZEREP: Református homiletikai szakértő és szerkesztő vagy, aki a Történetív modell szerint készít igehirdetési vázlatjavaslatot.

A TÖRTÉNETÍV MODELL: nem hét elszigetelt tétel, hanem EGYETLEN, előrehaladó gondolatmenet, amely a hallgatót a textus kérdéséből egy teológiai és egzisztenciális felismerési folyamaton vezeti végig. A "történet" jelleg nem azt jelenti, hogy kitalált történetet vagy anekdotát kell írni — ez a prédikáció belső mozgására vonatkozik: kiinduló helyzet → feszültség → valódi felismerés és elmozdulás → a textus új fénybe helyezi a kiinduló kérdést. A modell narratív és nem narratív szakaszokra egyaránt alkalmazható.

ALAPELVEK:
- mindig a bibliai textusból indulj ki, annak tényleges kérdését, feszültségét és teológiai állítását bontsd ki — ne használd puszta mottóként egy előre eldöntött témához;
- ne találj ki történeti, nyelvi vagy teológiai adatot; ha bizonytalan vagy hiányzik egy háttéradat, ne egészítsd ki kitalálással, inkább maradj a textus tényleges szövegénél és általánosan elfogadott, jól megalapozott ismereteknél;
- református teológiai érzékenységgel dolgozz, de ne erőltess minden textusra hitvallási formulákat;
- kerüld a moralizálást — mutasd meg, mit cselekszik, jelent ki vagy ígér Isten, és csak ebből vezesd le az ember válaszát;
- a hét pont EGYMÁSRA ÉPÜLJÖN: minden fordulópont valódi tartalmi elmozdulást okozzon, a következő rész NE kezdje újra a prédikációt, ugyanaz a felismerés, illusztráció vagy kép NE ismétlődjön több pontban — ne írd le hétféleképpen ugyanazt a gondolatot; egyik pont se mesélje újra a teljes textust, és egyik pont se árulja el előre egy KÉSŐBBI pont felismerését;
- a "Megérkezés" NE mechanikus összefoglalás vagy erkölcsi felhívás legyen — teológiailag a textus felismerésében érkezzen meg, lehetőleg visszakapcsolva a Belépés képéhez vagy kérdéséhez;
- a textus fő gondolatát és a fókuszmondatot KIZÁRÓLAG akkor vedd figyelembe explicit irányként, ha a promptban ténylegesen meg vannak adva — ha nincsenek megadva, magad határozd meg ezeket belső munkalépésként a textus és a háttéranyag alapján, ez nem jelenik meg külön a válaszban;
- ha a rendelkezésre álló háttéranyag eredeti nyelvi (görög/héber) elemzést tartalmaz, abból KIZÁRÓLAG a mögöttes teológiai vagy értelmezési felismerést építsd be, a nyelvi FORMÁT magát soha: a válaszban TILOS görög vagy héber szóalak, átírás (pl. "agapé", "cheszed"), Strong-szám vagy nyelvtani szakkifejezés (pl. "aorisztosz", "hitfeel", "STRONG") megjelenése — a felismerést mondd ki magyarul, a nyelvi hivatkozás nélkül;
- a válasz KIZÁRÓLAG magyar nyelvű legyen.

TERJEDELEM: minden pont egy feszes, jól szerkeszthető bekezdés, irányadóan 3–4 mondat / kb. 50–80 szó — kivéve a 4. "Mélyítés és fokozás" pontot, amely indokolt esetben legfeljebb 5 mondatig bővíthető. A hét pont EGYÜTT célzottan kb. 350–450 szó legyen — ez egy feszes homiletikai munkavázlat, amit a lelkész tovább dolgoz, NEM hét különálló, hosszú magyarázó esszé vagy mini-egzegézis.

A HÉT PONT FUNKCIÓJA (ebben a sorrendben, ez egyben a kimeneti kulcsok sorrendje is):
1. entry (Belépés) — természetes belépés a textus kérdésébe és a hallgató tapasztalatába; ne árulja el rögtön a végkövetkeztetést, ne kezdődjön közhelyes nyitással.
2. starting_point (Alaphelyzet) — a textus és a hallgatói helyzet kiinduló feszültsége; mi forog kockán a textusban.
3. first_shift (Első fordulópont) — az első felismerés, amely elmozdítja a megszokott értelmezést; valódi nézőpontváltás, nem puszta új információ.
4. deepening (Mélyítés és fokozás) — a kérdés teológiai, emberi és egzisztenciális kibontása; csak a valóban releváns háttéranyagot használd, kerüld az adathalmozást.
5. reinterpretation (Átértelmezés) — a textus KÖZPONTI teológiai felismerése, a gondolatmenet csúcsa; itt mondd ki legvilágosabban, mit állít, cselekszik vagy ígér Isten a textusban — ez a pont a FELISMERÉS maga.
6. second_shift (Második fordulópont) — az 5. pont felismerésének SZEMÉLYES ÉS KÖZÖSSÉGI KÖVETKEZMÉNYE, a hallgató felé forduló irány; NE ismételd meg az 5. pont teológiai állítását újra más szavakkal — ehelyett mutasd meg, mi VÁLTOZIK ebből fakadóan a hallgató életében vagy a közösségben, mi válik lehetségessé, ami korábban nem volt az.
7. arrival (Megérkezés) — a gondolatmenet természetes lezárása; nem összegzés, hanem eljuttat egy teológiai és egzisztenciális felismeréshez, lehetőleg visszakapcsolva a Belépéshez.

KIMENET: kizárólag egy JSON objektum, PONTOSAN ez a hét kulcs (entry, starting_point, first_shift, deepening, reinterpretation, second_shift, arrival), semmi más kulcs. Minden érték egy rövid, összefüggő, használható magyar bekezdés a fenti terjedelmi korláttal — nem egyetlen szó, nem puszta címszó. Ne írj bevezetőt, magyarázatot, bibliográfiát, forrásjegyzéket vagy teljes, szó szerint felolvasható prédikációt — homiletikai nyersanyagot adj, amit a lelkész tovább dolgoz. Ne ismételd meg szó szerint a bibliai szöveget hosszan — szintetizálj, ne idézz."""

ARC_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {key: {"type": "string"} for key in _ARC_POINT_KEYS},
    "required": list(_ARC_POINT_KEYS),
}


def build_arc_generation_prompt(context: ArcGenerationContext) -> str:
    """A tényleges feladatprompt — a rendszerutasítástól (`ARC_SYSTEM_
    PROMPT`) elkülönítve, kizárólag a konkrét bemeneti adatokat adja át."""
    parts: list[str] = [
        f"IGEHELY: {context.reference}",
        f"FORDÍTÁS: {context.bible_translation}",
        "",
        "BIBLIAI SZÖVEG (textus):",
        context.passage_text,
    ]

    if context.text_main_idea:
        parts += [
            "",
            "A TEXTUS FŐ GONDOLATA (a felhasználó adta meg — vedd figyelembe explicit irányként):",
            context.text_main_idea,
        ]
    if context.sermon_main_idea:
        parts += [
            "",
            "AZ IGEHIRDETÉS FÓKUSZMONDATA (a felhasználó adta meg — vedd figyelembe explicit irányként):",
            context.sermon_main_idea,
        ]

    background_blocks: list[str] = []
    for label, value in (
        ("Bibliai áttekintés", context.overview),
        ("Exegézis", context.exegesis),
        ("Eredeti nyelvi anyag", context.original_text),
        ("Kortörténet", context.history),
        ("Teológia", context.theology),
    ):
        if value:
            background_blocks.append(f"### {label}\n{value}")
    if background_blocks:
        parts += [
            "",
            "RENDELKEZÉSRE ÁLLÓ HÁTTÉRANYAG (ha van, építs rá; ha egy adott "
            "területről nincs, a bibliai szövegből és a saját, jól "
            "megalapozott tudásodból dolgozz — ne találj ki hiányzó adatot):",
            "\n\n".join(background_blocks),
        ]
    else:
        parts += [
            "",
            "Nincs külön mellékelt exegézis / kortörténet / eredeti nyelvi "
            "anyag — ez a leggyakoribb eset, nem kivétel. A saját "
            "teológiai, nyelvi és kortörténeti tudásodra támaszkodva "
            "dolgozd fel a textust, jól megalapozott, általánosan "
            "elfogadott ismeretek alapján.",
        ]

    parts += [
        "",
        "Készítsd el a hétpontos Történetív-vázlatot a rendszerutasítás "
        "szerint, kizárólag a megadott JSON sémával válaszolva.",
    ]
    return "\n".join(parts)


# =============================================================================
# Válasz-kinyerés és szigorú validáció
# =============================================================================


def _extract_json_object(raw: Any) -> dict[str, Any] | None:
    """Önálló, kis JSON-kinyerő — szándékosan NEM importál a régi
    section-szintű MI-modulokból (pl. a M4-es `extract_json_object`-ből),
    hogy ez a modul teljesen független maradjon.

    Megengedett, szűk tűrés: whitespace trim, markdown code-fence
    eltávolítás, egyetlen jól azonosítható JSON-object kibontása, és a
    záró vessző (trailing comma) levágása objektum/lista végén (LOCAL
    MANUAL QA FIX, 2.3) — UGYANAZ a szűk normalizálás, mint a `textus_
    summary_ai`/`sermon_workshop_blueprint_ai` saját kinyerőjében."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        candidate_fixed = re.sub(r",\s*}", "}", candidate)
        candidate_fixed = re.sub(r",\s*]", "]", candidate_fixed)
        for attempt in (candidate, candidate_fixed):
            try:
                obj = json.loads(attempt)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _diagnose_invalid_json_response(raw: Any) -> str:
    """Determinisztikus, durva DIAGNÓZIS arra, miért nem sikerült a
    modellválaszt érvényes JSON-objektumként kinyerni — kizárólag
    fejlesztői/debug célra (LOCAL MANUAL QA FIX, 2.2). Nem próbál semmit
    kijavítani, csak osztályozza a hibát. Azonos logika, mint a
    `sermon_workshop_blueprint_ai._diagnose_invalid_json_response` —
    szándékosan duplikálva, hogy ez a modul importfüggetlen maradjon."""
    if raw is None or _looks_like_api_error(raw):
        return "not_json:empty_or_api_error"
    text = str(raw).strip()
    if not text:
        return "not_json:empty_or_api_error"

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    body = fence.group(1).strip() if fence else text

    start = body.find("{")
    if start < 0:
        return "not_json:no_json_object_found"
    if body[:start].strip():
        return "not_json:prose_before_json"

    end = body.rfind("}")
    if end < start:
        return "not_json:truncated_response"
    if body[end + 1 :].strip():
        return "not_json:prose_after_json"

    candidate = body[start : end + 1]
    if re.search(r",\s*[}\]]", candidate):
        return "not_json:trailing_comma_unrecoverable"
    return "not_json:unparseable"


def validate_and_normalize_arc_response(raw: Any) -> dict[str, str] | None:
    """Szigorú validáció: a válasz PONTOSAN a hét engedélyezett kulcsot
    tartalmazza (se hiány, se ismeretlen extra kulcs), és minden érték
    nem-üres string. Bármilyen eltérés esetén `None` — a hívó ekkor SEM
    a kanonikus `arc`-ba, SEM az `arc_candidate`-be nem írhat semmit."""
    obj = _extract_json_object(raw)
    if obj is None:
        return None
    if set(obj.keys()) != set(_ARC_POINT_KEYS):
        return None
    points: dict[str, str] = {}
    for key in _ARC_POINT_KEYS:
        value = obj.get(key)
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        points[key] = text
    return points


def _looks_like_api_error(raw: Any) -> bool:
    text = str(raw or "")
    return text.startswith("⚠️") or text.startswith("⏳")


# =============================================================================
# Orchestráció — egyetlen belépési pont a UI számára
# =============================================================================


@dataclass(frozen=True)
class ArcGenerationOutcome:
    ok: bool
    status: str  # "applied" | "candidate" | "error"
    error_message: str = ""
    points: dict[str, str] | None = None
    reason: str = ""  # LOCAL MANUAL QA FIX, 2.2: fejlesztői debug-diagnózis


def generate_seven_point_arc(
    session_state: MutableMapping[str, Any],
    *,
    generate_fn: GenerateFn,
) -> ArcGenerationOutcome:
    """Egyetlen belépési pont: kontextus-ellenőrzés → legfeljebb EGY
    AI-hívás (LOCAL MANUAL QA FIX, 2.5: JSON-kinyerési hiba esetén
    legfeljebb 1 kontrollált retry) → szigorú válaszvalidálás →
    `store_generated_arc_result()` (RESET 2A, változatlan) az
    applied/candidate döntéshez.

    Ha a kontextus hiányos, vagy a válasz szerkezetileg érvénytelen, NEM
    indul (vagy nem hasznosul) AI-hívás, és sem a kanonikus `arc`, sem az
    `arc_candidate` nem módosul."""
    context = build_arc_generation_context(session_state)
    missing = context.missing_required_fields()
    if missing:
        return ArcGenerationOutcome(
            ok=False,
            status="error",
            error_message=(
                "Hiányzik a generáláshoz: " + ", ".join(missing) + ". "
                "Ezek nélkül nem indítható a hétpontos vázlatjavaslat "
                "generálása."
            ),
        )

    prompt = build_arc_generation_prompt(context)
    current_prompt = prompt
    points: dict[str, str] | None = None
    diagnosis = ""
    for attempt in range(2):
        try:
            raw = generate_fn(
                current_prompt,
                tab_label="Hétpontos vázlatjavaslat",
                use_cache=False,
                system_bundle=ARC_SYSTEM_PROMPT,
                include_brevity_directive=False,
                response_mime_type="application/json",
                response_schema=ARC_RESPONSE_SCHEMA,
                truncation_notice_mode="never",
                # 2026-09 audit fix: az ELSŐ (felhasználó által indított)
                # hívás marad cooldown-védett; KIZÁRÓLAG a belső JSON-
                # kinyerési hiba miatti, ugyanazon a gombnyomáson belüli
                # ismétlés (attempt > 0) kapja meg a bypass-t — enélkül a
                # globális cooldown-kapu szinte mindig elkapta ezt a
                # milliszekundumokkal később induló belső retry-t, és a
                # tervezett automatikus javítás sosem érte el ténylegesen
                # a modellt.
                bypass_cooldown=attempt > 0,
            )
        except Exception as exc:  # noqa: BLE001 — a UI-nak mindenképp választ kell adnunk
            return ArcGenerationOutcome(
                ok=False,
                status="error",
                error_message=f"A generálás sikertelen volt: {exc}",
            )

        if _looks_like_api_error(raw):
            return ArcGenerationOutcome(ok=False, status="error", error_message=str(raw))

        points = validate_and_normalize_arc_response(raw)
        if points is not None:
            break
        # A retry KIZÁRÓLAG akkor indokolt, ha a JSON-KINYERÉS magától
        # sikertelen (`_extract_json_object(raw) is None`) — ha a JSON
        # szintaktikailag rendben kinyerhető volt, csak a SÉMA (kulcsok/
        # típusok) hibás, az a modell valódi TARTALMI hibája, amit egy
        # néma retry csak elfedne.
        extraction_failed = _extract_json_object(raw) is None
        diagnosis = (
            _diagnose_invalid_json_response(raw)
            if extraction_failed
            else "invalid_shape"
        )
        if attempt == 0 and extraction_failed:
            current_prompt = (
                prompt
                + "\n\n==================================================\n"
                "KORREKCIÓ\n"
                "==================================================\n\n"
                "Az előző válaszod NEM volt érvényes, önmagában feldolgozható "
                "JSON-objektum (pl. csonka volt, vagy szöveg állt a JSON előtt/"
                "után). Add meg ÚJRA mind a hét pontot, KIZÁRÓLAG egyetlen, "
                "jólformált JSON-objektumként — semmilyen bevezető vagy záró "
                "szöveg, markdown-jelölés nélkül."
            )
            continue
        break

    if points is None:
        return ArcGenerationOutcome(
            ok=False,
            status="error",
            reason=diagnosis,
            error_message=(
                "A modell válasza nem érvényes hétpontos struktúra — "
                "nem került mentésre. Próbáld újra."
            ),
        )

    # `store_generated_arc_result` (RESET 2A) → `normalize_arc` a teljes
    # pontonkénti sémát várja ({"text": ..., "ai_suggestion": ..., ...}),
    # nem egy puszta stringet — itt csomagoljuk be a validált, lapos
    # {kulcs: szöveg} eredményt, MIELŐTT a változatlan adatmodell-
    # függvénynek átadnánk.
    wrapped_points = {key: {"text": text} for key, text in points.items()}
    result = store_generated_arc_result(
        session_state,
        points=wrapped_points,
        reference=context.reference,
        context_hash=context.context_hash,
    )
    return ArcGenerationOutcome(ok=True, status=result["status"], points=points)


__all__ = [
    "GenerateFn",
    "ArcGenerationContext",
    "ArcGenerationOutcome",
    "ARC_SYSTEM_PROMPT",
    "ARC_RESPONSE_SCHEMA",
    "ARC_GENERATION_CONTEXT_VERSION",
    "compute_arc_generation_context_hash",
    "build_arc_generation_context",
    "build_arc_generation_prompt",
    "validate_and_normalize_arc_response",
    "generate_seven_point_arc",
]
