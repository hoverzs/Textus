"""RESET 2E-2 — a BELSŐ homiletikai blueprint MI-generálása.

Ez a kétlépcsős vázlatmotor ELSŐ lépcsője:

    kanonikus input -> HOMILETIKAI BLUEPRINT -> (később) részletes vázlat

A blueprint TELJESEN BELSŐ artefaktum. Nem prédikáció, nem vázlat, és
nem is felhasználói szöveg: az a feladata, hogy a szétszórt információkból
EGYETLEN koherens prédikációs logikát alakítson ki, mielőtt bármilyen
látható vázlat készülne. A felületen sosem jelenik meg.

Szándékosan TELJESEN FÜGGETLEN modul:
  - nem importál `sermon_workshop_arc_ai`-ból semmit (külön kontextus,
    külön prompt, külön validáció);
  - nem hívja a régi section-szintű MI-segédeket;
  - saját, önálló rendszerpromptot használ — SEMMILYEN megosztott
    `BASE_SYSTEM_PROMPT`-ot nem örököl, hogy más modulok utasításai ne
    szivárogjanak át (ez a hibaosztály korábban több modulnál is
    megjelent);
  - az AI-hívó függvényt (`generate_fn`) a hívó adja át; ez a modul maga
    sosem importálja `app.generate_text`-et, és sosem hív valódi
    hálózatot a saját tesztjeiben.

BEMENETI FEGYELEM (RESET 2E-2 alapszabály): a blueprint kontextusába
KIZÁRÓLAG kanonikus, a felhasználó által birtokolt vagy jóváhagyott adat
kerülhet. El nem fogadott MI-javaslat SOHA — sem `arc_candidate`, sem
`field_refinements`, sem `text_summary.suggestions`, sem
`developed_outline_candidate`, sem a legacy `arc.*.ai_suggestion`.

TEXTUSMŰHELY-ÁTADÁS: ha van JÓVÁHAGYOTT (`status == "approved"`) ÉS FRISS
`text_summary`, akkor az az elsődleges — és egyben KIZÁRÓLAGOS —
Textusműhely-kontextus; ilyenkor a nyers `overview`/`exegesis`/`history`/
`theology`/`original_text` blobok NEM kerülnek a promptba. Ez csökkenti a
prompt zaját és megakadályozza a már elvetett vagy megalapozatlan
információ visszaszivárgását. Jóváhagyott (vagy jóváhagyott, de STALE)
összegzés hiányában kontrollált, CÍMKÉZETT fallback történik a nyers
mezőkre — de KIZÁRÓLAG azokra, amelyek maguk is frissek — a prompt
ilyenkor explicit tudja, hogy ez NEM jóváhagyott anyag.

RESET 3B-1 — FRISSESSÉG: a `text_summary.approved_context_hash` és az
egyes nyers mezők `{mező}_approved_context_hash`-e (mindkettőt a
Textusműhely már MOST is bélyegzi mentéskor/generáláskor, ld.
`textus_workshop_data.py`/`app.py`) az AKTUÁLIS igehely/fordítás/bibliai
szöveg szűk ujjlenyomatával kerül összevetésre. Egy STALE forrás — akár
jóváhagyott, akár nyers — SOSEM kerül csendben a blueprint kontextusába;
sem a session_state-ből nem törlődik, sem nem íródik át, csak kimarad a
felhasznált anyagból. Ld. `_narrow_passage_identity_hash`/`_is_narrow_
context_fresh`/`build_blueprint_generation_context`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, MutableMapping

from sermon_workshop_data import _ARC_POINT_KEYS, store_generated_blueprint_result

GenerateFn = Callable[..., str]

# A kontextus-payload verziója — ha a figyelembe vett mezők köre valaha
# bővül/szűkül, ezt kötelező növelni, hogy a régi hash-ek automatikusan
# összemérhetetlenné váljanak az új sémával.
BLUEPRINT_CONTEXT_VERSION = "blueprint_ctx_v1"

ARC_FIT_VERDICTS: tuple[str, ...] = ("strong_fit", "partial_fit", "weak_fit")
STRUCTURE_MODES: tuple[str, ...] = ("seven_point", "merged", "custom")

# A verdikt <-> szerkezet-mód kötelező párosítás (RESET 2E-2 10-12. pont).
_VERDICT_TO_MODE: dict[str, str] = {
    "strong_fit": "seven_point",
    "partial_fit": "merged",
    "weak_fit": "custom",
}

# A jóváhagyott textusösszegzés érdemi (nem metaadat) mezői, rögzített
# sorrendben — ez egyben a `text_summary.*` provenance-készlet forrása is.
_TEXT_SUMMARY_FIELDS: tuple[str, ...] = (
    "main_idea",
    "base_tension",
    "key_exegetical_findings",
    "theological_emphases",
    "genre_structure_notes",
)

# A kontrollált fallback forrásai — kizárólag akkor, ha NINCS jóváhagyott
# összegzés. Rögzített sorrend a determinisztikus hash miatt.
_RAW_FALLBACK_FIELDS: tuple[str, ...] = (
    "overview",
    "exegesis",
    "history",
    "theology",
    "original_text",
)

_RAW_FALLBACK_LABELS: dict[str, str] = {
    "overview": "Bibliai áttekintés",
    "exegesis": "Exegézis",
    "history": "Kortörténet",
    "theology": "Teológia",
    "original_text": "Eredeti nyelvi anyag",
}

_ARC_POINT_LABELS: dict[str, str] = {
    "entry": "Belépés",
    "starting_point": "Alaphelyzet",
    "first_shift": "Első fordulópont",
    "deepening": "Mélyítés és fokozás",
    "reinterpretation": "Átértelmezés",
    "second_shift": "Második fordulópont",
    "arrival": "Megérkezés",
}

# =============================================================================
# `grounded_in` provenance-konvenció
#
# Az ADATMODELL szintjén a `grounded_in` szabad string (ld. RESET 2E-1),
# de az AI-rétegben RÖGZÍTETT azonosító-készlet — a modell nem találhat ki
# tetszőleges természetes nyelvű provenance-t, mert akkor a hivatkozás
# ellenőrizhetetlen és a későbbi vázlatlépcső sem tud rá építeni.
#
# FONTOS: az `arc.*` azonosítók a KÓDBÁZIS tényleges `_ARC_POINT_KEYS`
# kulcsaiból származnak (importálva, sosem duplikálva) — így a provenance
# mindig valódi, létező mezőre mutat.
# =============================================================================
_GROUNDED_IN_ROOT_KEYS: tuple[str, ...] = ("text_main_idea", "sermon_main_idea")

ALLOWED_GROUNDED_IN: frozenset[str] = frozenset(
    set(_GROUNDED_IN_ROOT_KEYS)
    | {f"arc.{key}" for key in _ARC_POINT_KEYS}
    | {f"text_summary.{field}" for field in _TEXT_SUMMARY_FIELDS}
    | {f"raw.{field}" for field in _RAW_FALLBACK_FIELDS}
)

# Az adatmodell védekező felső korlátjával összhangban (RESET 2E-1).
_MOVEMENTS_MAX = 12
_CUSTOM_KEY_PATTERN = re.compile(r"^custom_([1-9][0-9]*)$")


# =============================================================================
# Generálási kontextus — determinisztikus, kizárólag kanonikus bemenetből
# =============================================================================


@dataclass(frozen=True)
class BlueprintContext:
    """A blueprint-generálás TELJES, determinisztikus bemenete.

    A gyűjtemény-mezők rendezett tuple-párok (nem dict), hogy a sorrend —
    és így a `context_hash` — bitre determinisztikus legyen.

    `summary_source` a Textusműhely-átadás módja:
      - `"approved_summary"`: van jóváhagyott `text_summary` (kizárólagos);
      - `"raw_fallback"`: nincs jóváhagyott összegzés, címkézett nyers
        mezők kerülnek be, NEM jóváhagyott segédanyagként;
      - `"none"`: egyik sem érhető el.
    """

    reference: str
    passage_text: str
    bible_translation: str
    text_main_idea: str
    sermon_main_idea: str
    arc_points: tuple[tuple[str, str], ...]
    summary_source: str
    text_summary: tuple[tuple[str, str], ...]
    raw_fallback: tuple[tuple[str, str], ...]
    exegesis_warnings: tuple[str, ...]
    context_hash: str

    def missing_required_fields(self) -> list[str]:
        """A generáláshoz elengedhetetlen mezők közül melyik hiányzik.

        A két főgondolat és az arc-pontok SZÁNDÉKOSAN nem kötelezőek:
        hasznos, de nem előfeltétel-jellegű bemenetek (ugyanaz az elv,
        mint a hétpontos motornál)."""
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

    def has_approved_summary(self) -> bool:
        return self.summary_source == "approved_summary"


def compute_blueprint_context_hash(context: BlueprintContext) -> str:
    """A ténylegesen a modellnek elküldött bemenet determinisztikus
    azonosítója — "ugyanabból a tényleges blueprint-inputból készült-e?".

    KIZÁRÓLAG azt tartalmazza, amit a modell valóban lát: igehely,
    bibliai szöveg, fordítás, a két főgondolat, a NEM ÜRES arc-pontok, és
    a ténylegesen felhasznált Textusműhely-kontextus (jóváhagyott
    összegzés VAGY a ténylegesen becsatolt fallback mezők — sosem
    mindkettő).

    SOSEM tartalmaz: `generated_at`-ot vagy bármilyen időbélyeget,
    UI-state-et, candidate-et (`arc_candidate`, `field_refinements`,
    `developed_outline_candidate`, `text_summary.suggestions`), vagy nem
    használt legacy adatot — ezek egyike sem befolyásolja a generálás
    bemenetét, ezért egyik sem lehet része az identitásnak."""
    payload = {
        "version": BLUEPRINT_CONTEXT_VERSION,
        "reference": context.reference,
        "passage_text": context.passage_text,
        "bible_translation": context.bible_translation,
        "text_main_idea": context.text_main_idea,
        "sermon_main_idea": context.sermon_main_idea,
        "arc_points": [list(pair) for pair in context.arc_points],
        "summary_source": context.summary_source,
        "text_summary": [list(pair) for pair in context.text_summary],
        "raw_fallback": [list(pair) for pair in context.raw_fallback],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _first_nonempty_str(session_state: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        val = session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _s(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


# =============================================================================
# RESET 3B-1 — Textusműhely-forrás frissesség ("szűk igehely-ujjlenyomat")
#
# A Textusműhely szekciói (`exegesis`, `history`, `theology`,
# `original_text`, `overview`) és a `text_summary` MÁR MOST is bélyegeznek
# egy "szűk igehely-ujjlenyomatot" MENTÉSKOR/GENERÁLÁSKOR — ezt a MEGLÉVŐ
# kontraktust a `sermon_outline_engine.compute_passage_context_hash`
# rögzíti (SHA1[:16], a {passage_reference, bible_translation,
# passage_text} rendezett JSON-ján), és ezt írja be a hívó (`app.py`
# `render_section_tab`, `textus_workshop_data.update_text_main_idea`/
# `update_text_summary_fields`) a `{mező}_approved_context_hash` /
# `text_summary.approved_context_hash` mezőkbe.
#
# EZ a modul (`sermon_workshop_blueprint_ai`) SZÁNDÉKOSAN NEM importál
# `sermon_outline_engine`-t (ld. a modul-izolációs teszt,
# `test_blueprint_module_is_independent_of_other_ai_modules`) — ezért az
# ÖSSZEHASONLÍTÁSHOZ szükséges "friss" oldali hash-t ITT, önállóan
# számítjuk, DE UGYANAZZAL a payload-alakkal és algoritmussal, mint a
# `compute_passage_context_hash` — ez NEM új, párhuzamos hash-SÉMA, hanem
# a MEGLÉVŐ kontraktus tükrözése modul-határon át, hogy a blueprint réteg
# össze tudja mérni a MÁR TÁROLT `*_approved_context_hash` értékeket az
# aktuális igehellyel/textussal anélkül, hogy a legacy motorra épülne.
# =============================================================================


def _narrow_passage_identity_hash(
    *, reference: str, bible_translation: str, passage_text: str
) -> str:
    """A `sermon_outline_engine.compute_passage_context_hash` payload-
    alakjának és algoritmusának tükrözése — lásd a fenti modulszintű
    megjegyzést."""
    payload = {
        "passage_reference": _s(reference),
        "bible_translation": _s(bible_translation),
        "passage_text": _s(passage_text),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _is_narrow_context_fresh(stored_hash: Any, current_hash: str) -> bool:
    """True, ha a MENTETT szűk igehely-ujjlenyomat még megegyezik az
    aktuálissal, VAGY ha nincs mentett ujjlenyomat (régi projekt / a
    mechanizmus bevezetése előtti mentés) — ugyanaz a visszafelé-
    kompatibilis döntés, mint a `sermon_outline_engine._canonical_source_
    is_stale`-ben: hiányzó hash SOHA nem minősül stale-nek."""
    stored = _s(stored_hash)
    if not stored:
        return True
    return stored == current_hash


def build_blueprint_generation_context(
    session_state: Mapping[str, Any],
) -> BlueprintContext:
    """A kanonikus blueprint-bemenet determinisztikus összeállítása.

    Prioritás (RESET 2E-2, 4. pont): bibliai textus/igehely -> a textus fő
    gondolata -> az igehirdetés fókuszmondata -> a hét arc-pont -> a
    JÓVÁHAGYOTT ÉS FRISS textusösszegzés -> és csak szükség esetén a
    kontrollált, egyenként FRISS nyers fallback-mezők.

    El nem fogadott MI-javaslatot SOSEM olvas: sem `arc_candidate`, sem
    `field_refinements`, sem `text_summary.suggestions`, sem
    `developed_outline_candidate`, sem a legacy `arc.*.ai_suggestion`
    mezőt — kizárólag az `arc.*.text` kanonikus tartalmat.

    RESET 3B-1 — FRISSESSÉG: sem a jóváhagyott `text_summary`, sem
    EGYETLEN nyers fallback-mező sem kerülhet csendben a kontextusba, ha a
    hozzá tartozó `*_approved_context_hash` MÁR NEM egyezik az aktuális
    igehely/fordítás/bibliai szöveg szűk ujjlenyomatával (ld. a
    `_narrow_passage_identity_hash`/`_is_narrow_context_fresh` fenti
    modulszintű megjegyzését). Egy JÓVÁHAGYOTT, DE STALE `text_summary`
    NEM használható jóváhagyott forrásként — ilyenkor a függvény ÚGY
    viselkedik, mintha nem lenne jóváhagyott összegzés: a kontrollált,
    egyenként friss nyers fallback-ra esik vissza (vagy `"none"`-ra, ha
    abból sincs friss). Ez SZÁNDÉKOS döntés (nem blokkolás): a blueprint
    generálása így is folytatható a textus/arc-tartalomból, ahogy eddig
    is optionális volt a Textusműhely-anyag hiánya — csak a STALE anyag
    nem szivároghat be csendben. A session_state-ben tárolt adatot ez a
    függvény sosem törli vagy módosítja — tisztán OLVASÁSI/szűrési
    döntés."""
    reference = _first_nonempty_str(session_state, "last_igehely", "igehely_input")
    passage_text = _first_nonempty_str(
        session_state, "passage_text", "passage_text_input"
    )
    bible_translation = (
        _first_nonempty_str(session_state, "bible_translation") or "RÚF 2014"
    )
    current_narrow_hash = _narrow_passage_identity_hash(
        reference=reference,
        bible_translation=bible_translation,
        passage_text=passage_text,
    )

    tw = session_state.get("text_workshop")
    tw = tw if isinstance(tw, dict) else {}
    sw = session_state.get("sermon_workshop")
    sw = sw if isinstance(sw, dict) else {}

    # RESET 3F: a `text_main_idea` (a textus fő gondolata) UGYANAZZAL a
    # szűk igehely-ujjlenyomat-ellenőrzéssel védett, mint a raw-fallback
    # mezők — passzusváltás után, újragenerálás nélkül, a régi (más
    # igehelyhez tartozó) fő gondolat NEM kerülhet csendben a blueprint
    # kontextusába. A `sermon_main_idea`-nak (az igehirdető saját
    # fókuszmondata) nincs passzus-ujjlenyomat kontraktusa — az
    # változatlanul, feltétel nélkül kerül be, ahogy eddig is.
    text_main_idea_raw = _s(tw.get("text_main_idea"))
    text_main_idea = (
        text_main_idea_raw
        if text_main_idea_raw
        and _is_narrow_context_fresh(
            tw.get("text_main_idea_approved_context_hash"), current_narrow_hash
        )
        else ""
    )
    sermon_main_idea = _s(sw.get("sermon_main_idea"))

    # A hét arc-pont KANONIKUS sorrendben, kizárólag a `text` mezőből —
    # csak a nem üres pontok kerülnek be (üres pont nem hordoz információt,
    # és a hash-t sem szabad üres bejegyzésekkel zajosítani).
    arc = sw.get("arc") if isinstance(sw.get("arc"), dict) else {}
    arc_points: list[tuple[str, str]] = []
    for key in _ARC_POINT_KEYS:
        point = arc.get(key)
        text = _s(point.get("text")) if isinstance(point, dict) else ""
        if text:
            arc_points.append((key, text))

    # Textusműhely-átadás: jóváhagyott ÉS FRISS összegzés KIZÁRÓLAGOSAN,
    # egyébként kontrollált, egyenként FRISS nyers fallback.
    summary_raw = tw.get("text_summary")
    summary_raw = summary_raw if isinstance(summary_raw, dict) else {}
    approved = _s(summary_raw.get("status")) == "approved"
    summary_fresh = _is_narrow_context_fresh(
        summary_raw.get("approved_context_hash"), current_narrow_hash
    )

    text_summary: list[tuple[str, str]] = []
    raw_fallback: list[tuple[str, str]] = []
    exegesis_warnings: list[str] = []

    if approved and summary_fresh:
        for field in _TEXT_SUMMARY_FIELDS:
            value = _s(summary_raw.get(field))
            if value:
                text_summary.append((field, value))

    if text_summary:
        summary_source = "approved_summary"
    else:
        for field in _RAW_FALLBACK_FIELDS:
            value = _first_nonempty_str(session_state, field)
            if value and _is_narrow_context_fresh(
                session_state.get(f"{field}_approved_context_hash"),
                current_narrow_hash,
            ):
                raw_fallback.append((field, value))
        summary_source = "raw_fallback" if raw_fallback else "none"
        # Az exegézis megalapozottsági ÉS grounding-figyelmeztetései CSAK
        # akkor relevánsak, ha a nyers exegézist ténylegesen be is
        # csatoljuk (ami már önmagában feltételezi, hogy az exegézis
        # friss — ld. a fenti `_is_narrow_context_fresh` szűrést). RESET
        # 3D-3: a RESET 3B-6-ban bevezetett `exegesis_grounding_warnings`
        # (determinisztikus görög/héber token/lemma/Strong-ellenőrzés) a
        # MEGLÉVŐ `exegesis_support_warnings` (jelenlét-alapú, RESET
        # 2E-2 óta létező) lista UTÁN fűződik hozzá, ugyanabba a listába —
        # nincs új warning-séma, csak egy második, determinisztikus forrás
        # ugyanahhoz a figyelmeztetés-csatornához.
        if any(field == "exegesis" for field, _ in raw_fallback):
            support_warnings_raw = session_state.get("exegesis_support_warnings")
            support_warnings = (
                [_s(item) for item in support_warnings_raw if _s(item)]
                if isinstance(support_warnings_raw, list)
                else []
            )
            grounding_warnings_raw = session_state.get("exegesis_grounding_warnings")
            grounding_warnings = (
                [_s(item) for item in grounding_warnings_raw if _s(item)]
                if isinstance(grounding_warnings_raw, list)
                else []
            )
            exegesis_warnings = support_warnings + grounding_warnings

    context = BlueprintContext(
        reference=reference,
        passage_text=passage_text,
        bible_translation=bible_translation,
        text_main_idea=text_main_idea,
        sermon_main_idea=sermon_main_idea,
        arc_points=tuple(arc_points),
        summary_source=summary_source,
        text_summary=tuple(text_summary),
        raw_fallback=tuple(raw_fallback),
        exegesis_warnings=tuple(exegesis_warnings),
        context_hash="",
    )
    if context.reference and context.passage_text:
        context = replace(context, context_hash=compute_blueprint_context_hash(context))
    return context


# =============================================================================
# Rendszerprompt + válaszséma
# =============================================================================

BLUEPRINT_SYSTEM_PROMPT = """SZEREP: Református homiletikai szakértő vagy, aki egy igehirdetés BELSŐ gondolati szerkezetét tervezi meg — mielőtt bármilyen vázlat vagy prédikációszöveg elkészülne.

MIT KÉSZÍTESZ: egy belső homiletikai tervrajzot (blueprint). Ez NEM prédikáció, NEM kész vázlat, és NEM a szószéken elhangzó szöveg. A feladatod, hogy a szétszórt információkból EGYETLEN koherens prédikációs logikát alakíts ki: mi a tényleges központi állítás, milyen feszültség mozgatja, hol történik valódi fordulat, és hová jut el a hallgató. A tervrajzot a felhasználó sosem látja közvetlenül — egy későbbi lépés ebből készít majd részletes vázlatot.

ALAPELVEK:
- A FELHASZNÁLÓ TARTALMA ELSŐDLEGES. Minden megadott, nem üres vázlatpont a felhasználó saját, birtokolt homiletikai gondolata. Rendezheted, összekapcsolhatod, kibonthatod a logikai összefüggéseit — de SOHA ne cseréld le önkényesen egy másik gondolatra csak azért, mert más szerkezetet tartasz szebbnek.
- Ha valódi ellentmondást látsz a felhasználó vázlatpontja és a textus vagy az exegetikai anyag között, NE javítsd át csendben: tedd a `warnings` mezőbe, tömör, tárgyilagos megfogalmazásban.
- A TEXTUS SAJÁT SZERKEZETE ELSŐDLEGES. A prédikáció logikája a bibliai szakasz tényleges mozgásából, érveléséből vagy elbeszéléséből következzen — ne egy előre eldöntött sablonból.
- NE találj ki exegetikai, történeti, nyelvi vagy teológiai tényt. Ha egy adat hiányzik vagy bizonytalan, hagyd ki — a hiány jobb, mint a kitalálás.
- A KANONIKUS BEMENET BIZONYTALANSÁGI SZINTJÉT ŐRIZD MEG. Ha a bemeneti anyag (exegézis, kortörténet, teológia, textusösszegzés) egy állítást vitatottként, bizonytalanként vagy több legitim értelmezés egyikeként kezel, a tervrajz (pl. `central_claim`, `textual_center`) NE emelje ezt kategorikus tényként. Példa: ha az exegézis szerint egy szereplő kiléte vitatott, NE írj ilyet: "Isten találkozik vele" — írj helyette olyat, hogy "a szöveg egy titokzatos, isteni dimenzióval összekapcsolt alakkal való találkozást ír le" vagy hasonló, a forrás bizonytalanságát tükröző megfogalmazást.
- NE halmozz kutatási adatot. A minőséget nem az dönti el, mennyi információ kerül bele, hanem hogy MI MARAD KI. Csak azt vidd tovább, ami ténylegesen támogatja a prédikáció ívét.
- EREDETI NYELVI ADAT: soha ne díszítésként. Görög/héber szóalak, átírás vagy Strong-szám ÖNMAGÁBAN nem érték. Csak akkor kerüljön a `key_support.original_language` mezőbe valami, ha az adott megfigyelés ténylegesen szükséges a gondolatmenethez — és akkor is rövid, magyarul értelmezhető MEGÁLLAPÍTÁSKÉNT fogalmazd meg, ne nyers lexikai adatként. Ha nincs ilyen, hagyd üresen a listát.
- A válasz KIZÁRÓLAG magyar nyelvű legyen.

A HÉTPONTOS TÖRTÉNETÍV MODELL (PREFERÁLT, DE NEM KÖTELEZŐ):
1. entry (Belépés) — természetes belépés a textus kérdésébe és a hallgató tapasztalatába.
2. starting_point (Alaphelyzet) — a kiinduló feszültség; mi forog kockán.
3. first_shift (Első fordulópont) — az első valódi nézőpontváltás.
4. deepening (Mélyítés és fokozás) — a kérdés teológiai és egzisztenciális kibontása.
5. reinterpretation (Átértelmezés) — a textus központi felismerése, a gondolatmenet csúcsa.
6. second_shift (Második fordulópont) — a felismerés személyes és közösségi KÖVETKEZMÉNYE.
7. arrival (Megérkezés) — a gondolatmenet természetes lezárása.

ILLESZKEDÉS-DÖNTÉS (`arc_fit`): értékelned kell, hogy ez a textus és a kialakuló gondolatmenet mennyire hordozza természetesen ezt a hét mozgást. A döntés alapja KIZÁRÓLAG: a szakasz műfaja, a saját szerkezete, az érvelés vagy elbeszélés tényleges mozgása, és a felhasználó által már megadott vázlattartalom. SOHA ne stilisztikai preferencia alapján dönts.

- strong_fit -> `mode` = "seven_point": a textus természetesen hordozza mind a hét mozgást. Pontosan a fenti hét kulcsot használd, ebben a sorrendben.
- partial_fit -> `mode` = "merged": az ív alapvetően működik, de egyes pontok külön egységként mesterségesek lennének. Vond össze őket: kevesebb mozgás, a hét kanonikus kulcs egy RÉSZHALMAZA, eredeti sorrendben. Egy összevont mozgás `grounded_in` mezője több arc-pontra is hivatkozhat. NE gyárts mesterséges második fordulópontot pusztán azért, mert a modellben van ilyen mező.
- weak_fit -> `mode` = "custom": a hétpontos narratív forma jelentősen TORZÍTANÁ a textus saját logikáját (pl. levéli érvelés, bölcsességi vagy himnikus szöveg, felsorolás-jellegű tanítás). Ilyenkor 3-5 természetesebb mozgást adj, `custom_1`, `custom_2`, … kulcsokkal, folytonos sorszámozással.

A `weak_fit` NE legyen könnyű menekülőút: a hétpontos modell marad a preferált. Csak akkor térj el tőle, ha az eltérésnek a fenti szempontok alapján valódi, megnevezhető oka van — és ezt az okot írd le az `arc_fit.reason` mezőben.

PROVENANCE (`grounded_in`): minden mozgásnál sorold fel, mely bemenetekre épül. KIZÁRÓLAG az alábbi, pontos azonosítókat használhatod — természetes nyelvű forrásmegjelölést NE találj ki:
  text_main_idea, sermon_main_idea,
  arc.entry, arc.starting_point, arc.first_shift, arc.deepening, arc.reinterpretation, arc.second_shift, arc.arrival,
  text_summary.main_idea, text_summary.base_tension, text_summary.key_exegetical_findings, text_summary.theological_emphases, text_summary.genre_structure_notes,
  raw.overview, raw.exegesis, raw.history, raw.theology, raw.original_text
Csak olyan azonosítót használj, amelyhez a promptban ténylegesen kaptál tartalmat.

KIMENET: kizárólag egy JSON objektum a megadott séma szerint. A `central_claim`, a `textual_center` és a `desired_listener_movement` SOHA nem lehet üres. A szöveges mezők tömörek legyenek: a `central_claim` egyetlen mondat, a `core_idea` 1-2 mondat. A `key_support` listák elemei rövid, önálló megállapítások — nem bekezdések, nem idézetek."""


BLUEPRINT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "central_claim": {"type": "string"},
        "textual_center": {"type": "string"},
        "listener_tension": {"type": "string"},
        "theological_turn": {"type": "string"},
        "desired_listener_movement": {"type": "string"},
        "arc_fit": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": list(ARC_FIT_VERDICTS)},
                "reason": {"type": "string"},
            },
            "required": ["verdict", "reason"],
        },
        "recommended_structure": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": list(STRUCTURE_MODES)},
                "movements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "function": {"type": "string"},
                            "core_idea": {"type": "string"},
                            "grounded_in": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["key", "function", "core_idea", "grounded_in"],
                    },
                },
            },
            "required": ["mode", "movements"],
        },
        "key_support": {
            "type": "object",
            "properties": {
                "exegetical": {"type": "array", "items": {"type": "string"}},
                "original_language": {"type": "array", "items": {"type": "string"}},
                "historical_theological": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["exegetical", "original_language", "historical_theological"],
        },
        "illustration_direction": {"type": "string"},
        "application_direction": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "central_claim",
        "textual_center",
        "listener_tension",
        "theological_turn",
        "desired_listener_movement",
        "arc_fit",
        "recommended_structure",
        "key_support",
        "illustration_direction",
        "application_direction",
        "warnings",
    ],
}


def build_blueprint_prompt(context: BlueprintContext) -> str:
    """A tényleges feladatprompt — a rendszerutasítástól elkülönítve,
    kizárólag a konkrét bemeneti adatokat adja át, CÍMKÉZVE.

    A Textusműhely-blokk címkéje explicit jelzi, hogy jóváhagyott,
    kurátorált anyagról vagy nem jóváhagyott segédanyagról van-e szó."""
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
            "A TEXTUS FŐ GONDOLATA (a felhasználó kanonikus tartalma — "
            "azonosító: `text_main_idea`):",
            context.text_main_idea,
        ]
    if context.sermon_main_idea:
        parts += [
            "",
            "AZ IGEHIRDETÉS FÓKUSZMONDATA (a felhasználó kanonikus tartalma — "
            "azonosító: `sermon_main_idea`):",
            context.sermon_main_idea,
        ]

    if context.arc_points:
        parts += [
            "",
            "A FELHASZNÁLÓ MEGLÉVŐ VÁZLATPONTJAI — ez az Ő saját, birtokolt "
            "homiletikai tartalma. Rendezd, kösd össze, bontsd ki a logikai "
            "összefüggéseit, de NE cseréld le önkényesen. Csak a kitöltött "
            "pontok szerepelnek itt; a hiányzók egyszerűen még üresek:",
        ]
        for key, text in context.arc_points:
            label = _ARC_POINT_LABELS.get(key, key)
            parts.append(f"- [`arc.{key}`] {label}: {text}")
    else:
        parts += [
            "",
            "A felhasználó még egyetlen vázlatpontot sem töltött ki — a "
            "szerkezetet teljes egészében a textus saját mozgásából "
            "vezesd le.",
        ]

    if context.summary_source == "approved_summary":
        parts += [
            "",
            "TEXTUSMŰHELY — JÓVÁHAGYOTT TEXTUSÖSSZEGZÉS (a felhasználó által "
            "ELFOGADOTT, kurátorált elsődleges exegetikai kontextus; ez a "
            "megbízható átadási pont, erre építs):",
        ]
        for field, value in context.text_summary:
            parts.append(f"- [`text_summary.{field}`] {value}")
    elif context.summary_source == "raw_fallback":
        parts += [
            "",
            "TEXTUSMŰHELY — NYERS, NEM JÓVÁHAGYOTT SEGÉDANYAG: nincs "
            "jóváhagyott textusösszegzés, ezért az alábbi gépi elemzések "
            "állnak rendelkezésre. Ezek NEM a felhasználó által elfogadott "
            "tények — kritikusan és SZELEKTÍVEN használd őket, csak azt "
            "emeld át, ami a textus szövegéből is megáll, és a "
            "gondolatmenethez ténylegesen szükséges:",
        ]
        for field, value in context.raw_fallback:
            label = _RAW_FALLBACK_LABELS.get(field, field)
            parts.append(f"\n### [`raw.{field}`] {label}\n{value}")
        if context.exegesis_warnings:
            parts += [
                "",
                "FIGYELMEZTETÉS a fenti exegézishez — az alábbi pontok "
                "megalapozottsága vagy nyelvi pontossága bizonytalan lehet "
                "(pl. hiányzó vers- vagy eredeti nyelvi hivatkozás egy "
                "szakasz alatt, vagy a helyi adatbázissal nem egyező "
                "görög/héber adat). Ezek NEM bizonyított hibák, csak "
                "figyelmeztetések — ezekre NE építs érdemi állítást:",
            ]
            for warning in context.exegesis_warnings:
                parts.append(f"- {warning}")
    else:
        parts += [
            "",
            "Nincs mellékelt Textusműhely-anyag — sem jóváhagyott összegzés, "
            "sem nyers elemzés. Ez a leggyakoribb eset, nem kivétel: a "
            "bibliai szövegből és a saját, jól megalapozott teológiai "
            "tudásodból dolgozz, kitalált adat nélkül.",
        ]

    parts += [
        "",
        "Készítsd el a belső homiletikai tervrajzot a rendszerutasítás "
        "szerint, kizárólag a megadott JSON sémával válaszolva.",
    ]
    return "\n".join(parts)


# =============================================================================
# Válasz-kinyerés és SZIGORÚ szemantikai validáció
# =============================================================================


def _extract_json_object(raw: Any) -> dict[str, Any] | None:
    """Önálló, kis JSON-kinyerő — szándékosan NEM importál más
    MI-modulokból, hogy ez a modul teljesen független maradjon.

    Megengedett, szűk tűrés: whitespace trim, markdown code-fence
    eltávolítás, egyetlen jól azonosítható JSON-object kibontása a
    szövegből, és a záró vessző (trailing comma) levágása objektum/lista
    végén — ez utóbbi UGYANAZ a szűk, biztonságos normalizálás, mint a
    `textus_summary_ai.extract_json_object`-ben. Nem próbál tetszőleges
    prózából JSON-t kitalálni, és nem fogad el sémán kívüli tartalmat."""
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
    fejlesztői/debug célra (a `BlueprintOutcome.reason` mezőbe kerül,
    NEM a végfelhasználónak mutatott `error_message`-be, ld. `generate_
    blueprint`). Nem próbál semmit kijavítani, csak osztályozza a hibát,
    hogy egy fejlesztő ne csak azt lássa, hogy "invalid JSON", hanem
    hogy pl. csonka volt-e a válasz, próza előzte/követte-e, vagy
    egyáltalán nem talált benne JSON-objektumot."""
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


def _clean_str_list(raw: Any) -> list[str]:
    """Biztonságos normalizálás: nem-string elemek kimaradnak, a stringek
    trimmelődnek, az üresek eltűnnek. Ez MEGENGEDETT tisztítás — nem
    szemantikai javítás."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


@dataclass(frozen=True)
class BlueprintValidationResult:
    ok: bool
    reason: str = ""
    blueprint: dict[str, Any] | None = None


def _validate_movements(
    movements_raw: Any, *, mode: str
) -> tuple[list[dict[str, Any]] | None, str]:
    """A mozgáslista SZIGORÚ szerkezeti validálása a mód szerint.

    Visszatérés: `(movements, "")` sikernél, `(None, reason)` hibánál."""
    if not isinstance(movements_raw, list) or not movements_raw:
        return None, "empty_movements"
    if len(movements_raw) > _MOVEMENTS_MAX:
        return None, "too_many_movements"

    movements: list[dict[str, Any]] = []
    for item in movements_raw:
        if not isinstance(item, dict):
            return None, "invalid_movement_entry"
        key = item.get("key")
        if not isinstance(key, str) or not key.strip():
            return None, "invalid_movement_key"
        grounded_in = _clean_str_list(item.get("grounded_in"))
        for token in grounded_in:
            if token not in ALLOWED_GROUNDED_IN:
                return None, "invalid_grounded_in"
        movements.append(
            {
                "key": key.strip(),
                "function": str(item.get("function") or "").strip(),
                "core_idea": str(item.get("core_idea") or "").strip(),
                "grounded_in": grounded_in,
            }
        )

    keys = [m["key"] for m in movements]
    if len(set(keys)) != len(keys):
        return None, "duplicate_movement_keys"

    if mode == "seven_point":
        # Pontosan a hét kanonikus kulcs, pontosan kanonikus sorrendben.
        if keys != list(_ARC_POINT_KEYS):
            return None, "seven_point_keys_mismatch"
    elif mode == "merged":
        # A kanonikus kulcsok VALÓDI részhalmaza, eredeti relatív
        # sorrendben — az összevonás kevesebb mozgást jelent, nem újakat.
        #
        # RESET 2E-2A (2026-08-20): a `partial_fit` homiletikai jelentése
        # szűk — a hétpontos ív ALAPVETŐEN működik, csak néhány pont
        # önálló egységként lenne mesterséges. Ez PONTOSAN 5 vagy 6
        # mozgást jelent: 2-4 mozgás már lényegileg más szerkezet (az a
        # `weak_fit`/`custom` területe), 7 mozgás pedig nem is összevonás
        # (az a `strong_fit`/`seven_point`).
        if not set(keys).issubset(set(_ARC_POINT_KEYS)):
            return None, "merged_keys_not_canonical"
        if len(keys) < 5:
            return None, "merged_too_few_movements"
        if len(keys) > 6:
            return None, "merged_not_actually_merged"
        canonical_order = [k for k in _ARC_POINT_KEYS if k in set(keys)]
        if keys != canonical_order:
            return None, "merged_keys_out_of_order"
    else:  # "custom"
        # Stabil, folytonos `custom_N` sorszámozás 1-től.
        #
        # RESET 2E-2A: a `weak_fit` célja egy természetesebb, TÖMÖREBB
        # szerkezet — nem tetszőleges hosszúságú alternatív vázlat.
        # V1-ben ez pontosan 3-5 mozgást jelent.
        expected = [f"custom_{i}" for i in range(1, len(keys) + 1)]
        if keys != expected:
            return None, "custom_keys_not_sequential"
        if len(keys) < 3:
            return None, "custom_too_few_movements"
        if len(keys) > 5:
            return None, "custom_too_many_movements"

    return movements, ""


def validate_blueprint_response(raw: Any) -> BlueprintValidationResult:
    """SZIGORÚ szemantikai validáció — nem elég, hogy dict érkezett.

    Biztonságos NORMALIZÁLÁS megengedett (trimmelés, nem-string
    listaelemek kihagyása, hiányzó opcionális szöveges mező üresre
    állítása). SZEMANTIKAI SZERKEZETI HIBA esetén viszont ELUTASÍTÁS —
    a válasz "megjavítása" itt veszélyes lenne, mert egy kitalált
    szerkezet csendben helyesnek látszana.

    Elutasítási okok (`reason`): `not_json:*` (LOCAL MANUAL QA FIX —
    részletesebb debug-diagnózis, ld. `_diagnose_invalid_json_response`:
    `not_json:empty_or_api_error`, `not_json:no_json_object_found`,
    `not_json:prose_before_json`, `not_json:truncated_response`,
    `not_json:prose_after_json`, `not_json:trailing_comma_unrecoverable`,
    `not_json:unparseable`), `empty_central_claim`,
    `empty_textual_center`, `empty_desired_listener_movement`,
    `invalid_arc_fit`, `invalid_verdict`, `invalid_structure`,
    `invalid_mode`, `verdict_mode_mismatch`, plusz a mozgás-szintű okok
    (`empty_movements`, `too_many_movements`, `invalid_movement_entry`,
    `invalid_movement_key`, `invalid_grounded_in`,
    `duplicate_movement_keys`, `seven_point_keys_mismatch`,
    `merged_keys_not_canonical`, `merged_too_few_movements` (RESET 2E-2A:
    <5), `merged_not_actually_merged` (RESET 2E-2A: >6),
    `merged_keys_out_of_order`, `custom_keys_not_sequential`,
    `custom_too_few_movements` (RESET 2E-2A: <3),
    `custom_too_many_movements` (RESET 2E-2A: >5))."""
    obj = _extract_json_object(raw)
    if obj is None:
        return BlueprintValidationResult(
            ok=False, reason=_diagnose_invalid_json_response(raw)
        )

    central_claim = str(obj.get("central_claim") or "").strip()
    if not central_claim:
        return BlueprintValidationResult(ok=False, reason="empty_central_claim")
    textual_center = str(obj.get("textual_center") or "").strip()
    if not textual_center:
        return BlueprintValidationResult(ok=False, reason="empty_textual_center")
    desired_movement = str(obj.get("desired_listener_movement") or "").strip()
    if not desired_movement:
        return BlueprintValidationResult(
            ok=False, reason="empty_desired_listener_movement"
        )

    arc_fit_raw = obj.get("arc_fit")
    if not isinstance(arc_fit_raw, dict):
        return BlueprintValidationResult(ok=False, reason="invalid_arc_fit")
    verdict = str(arc_fit_raw.get("verdict") or "").strip()
    if verdict not in ARC_FIT_VERDICTS:
        return BlueprintValidationResult(ok=False, reason="invalid_verdict")

    structure_raw = obj.get("recommended_structure")
    if not isinstance(structure_raw, dict):
        return BlueprintValidationResult(ok=False, reason="invalid_structure")
    mode = str(structure_raw.get("mode") or "").strip()
    if mode not in STRUCTURE_MODES:
        return BlueprintValidationResult(ok=False, reason="invalid_mode")
    if _VERDICT_TO_MODE[verdict] != mode:
        return BlueprintValidationResult(ok=False, reason="verdict_mode_mismatch")

    movements, reason = _validate_movements(structure_raw.get("movements"), mode=mode)
    if movements is None:
        return BlueprintValidationResult(ok=False, reason=reason)

    support_raw = obj.get("key_support")
    support_raw = support_raw if isinstance(support_raw, dict) else {}

    blueprint = {
        "central_claim": central_claim,
        "textual_center": textual_center,
        "listener_tension": str(obj.get("listener_tension") or "").strip(),
        "theological_turn": str(obj.get("theological_turn") or "").strip(),
        "desired_listener_movement": desired_movement,
        "arc_fit": {
            "verdict": verdict,
            "reason": str(arc_fit_raw.get("reason") or "").strip(),
        },
        "recommended_structure": {"mode": mode, "movements": movements},
        "key_support": {
            "exegetical": _clean_str_list(support_raw.get("exegetical")),
            "original_language": _clean_str_list(support_raw.get("original_language")),
            "historical_theological": _clean_str_list(
                support_raw.get("historical_theological")
            ),
        },
        "illustration_direction": str(obj.get("illustration_direction") or "").strip(),
        "application_direction": str(obj.get("application_direction") or "").strip(),
        "warnings": _clean_str_list(obj.get("warnings")),
    }
    return BlueprintValidationResult(ok=True, blueprint=blueprint)


def _looks_like_api_error(raw: Any) -> bool:
    text = str(raw or "")
    return text.startswith("⚠️") or text.startswith("⏳")


# =============================================================================
# Orchestráció — egyetlen belépési pont
# =============================================================================


@dataclass(frozen=True)
class BlueprintOutcome:
    ok: bool
    status: str  # "generated" | "error"
    error_message: str = ""
    reason: str = ""
    blueprint: dict[str, Any] | None = None
    context_hash: str = ""


def generate_sermon_blueprint(
    session_state: MutableMapping[str, Any],
    *,
    generate_fn: GenerateFn,
    bypass_cooldown: bool = False,
) -> BlueprintOutcome:
    """Egyetlen belépési pont: determinisztikus kontextus -> legfeljebb EGY
    AI-hívás -> SZIGORÚ validálás -> és KIZÁRÓLAG érvényes eredmény esetén
    írás a kanonikus `sermon_workshop.blueprint` mezőbe.

    A blueprintnek NINCS candidate életciklusa (belső artefaktum). A
    biztonságot az adja, hogy érvénytelen modellválasznál a
    `store_generated_blueprint_result()` MEG SEM HÍVÓDIK — így a korábbi
    kanonikus blueprint és a `blueprint_meta` bit-pontosan változatlan
    marad, és semmilyen félkész adat nem kerül state-be.

    Hiányos kontextus esetén EL SEM INDUL az AI-hívás.

    `bypass_cooldown`: FINAL SERMON WORKFLOW + OUTLINE PRESENTATION
    POLISH (2026-08-21) — KIZÁRÓLAG akkor `True`, ha a hívó UGYANAZON a
    gombnyomáson belül közvetlenül ez után egy részletes vázlat
    generálást is indít (a hiányzó/elavult blueprint automatikus
    pótlása a "Részletes vázlat készítése" gomb egyetlen kattintásán
    belül) — a globális `GEMINI_COOLDOWN_S` két LOGIKAILAG FÜGGETLEN
    felhasználói hívás közé való, nem egyetlen gombnyomás belső,
    láncolt lépései közé."""
    context = build_blueprint_generation_context(session_state)
    missing = context.missing_required_fields()
    if missing:
        return BlueprintOutcome(
            ok=False,
            status="error",
            reason="missing_context",
            error_message=(
                "Hiányzik a tervrajz elkészítéséhez: "
                + ", ".join(missing)
                + ". Ezek nélkül nem indítható a generálás."
            ),
        )

    prompt = build_blueprint_prompt(context)
    # LOCAL MANUAL QA FIX, 2.5 — LEGFELJEBB 1 kontrollált retry, KIZÁRÓLAG
    # akkor, ha az első válasz JSON-KINYERÉSI szinten hibás (`not_json:*` —
    # pl. csonkulás, próza a JSON körül). Szemantikai/sémahiba (pl. üres
    # mező, érvénytelen `grounded_in`) esetén NEM ismételünk — az a
    # modell tényleges TARTALMI hibája, amit egy néma újrapróbálkozás
    # csak elfedne. A retry ugyanazt a kontextust és promptot használja,
    # csak egy rövid, korrekciós megjegyzést told hozzá — nem generálja
    # újra a teljes upstream Textusműhely-adatfolyamot.
    current_prompt = prompt
    result: BlueprintValidationResult | None = None
    for attempt in range(2):
        try:
            raw = generate_fn(
                current_prompt,
                tab_label="Igehirdetési tervrajz",
                use_cache=False,
                system_bundle=BLUEPRINT_SYSTEM_PROMPT,
                include_brevity_directive=False,
                response_mime_type="application/json",
                response_schema=BLUEPRINT_RESPONSE_SCHEMA,
                # 2026-09 audit fix: a hívó `bypass_cooldown` paramétere
                # a KÜLSŐ, két logikailag független felhasználói hívás
                # közötti láncolást szabályozza (lásd fent) — ettől
                # FÜGGETLENÜL a belső JSON-kinyerési retry (attempt > 0)
                # MINDIG bypassolja a cooldown-t, mert az garantáltan
                # ugyanazon a gombnyomáson belül, milliszekundumokkal az
                # első hívás után indul, és korábban emiatt szinte
                # sosem érte el ténylegesen a modellt.
                bypass_cooldown=bypass_cooldown or attempt > 0,
                # A csonka válaszhoz fűzött, ember-olvasható magyar
                # figyelmeztető mondat MINDIG érvénytelenné tenné a
                # JSON-t (a szintaktikai csonkaság mellett is) — inkább a
                # nyers (esetleg csonka) szöveget kapja meg a validáció,
                # hogy a `_diagnose_invalid_json_response` pontosan
                # jelezhesse a csonkulást.
                truncation_notice_mode="never",
            )
        except Exception as exc:  # noqa: BLE001 — a hívónak mindenképp választ kell adnunk
            return BlueprintOutcome(
                ok=False,
                status="error",
                reason="generate_failed",
                error_message=f"A tervrajz generálása sikertelen volt: {exc}",
            )

        if _looks_like_api_error(raw):
            return BlueprintOutcome(
                ok=False, status="error", reason="api_error", error_message=str(raw)
            )

        result = validate_blueprint_response(raw)
        if result.ok and result.blueprint is not None:
            break
        if attempt == 0 and result.reason.startswith("not_json:"):
            current_prompt = (
                prompt
                + "\n\n==================================================\n"
                "KORREKCIÓ\n"
                "==================================================\n\n"
                "Az előző válaszod NEM volt érvényes, önmagában feldolgozható "
                "JSON-objektum (pl. csonka volt, vagy szöveg állt a JSON előtt/"
                "után). Add meg ÚJRA a TELJES homiletikai tervrajzot, "
                "KIZÁRÓLAG egyetlen, jólformált JSON-objektumként — semmilyen "
                "bevezető vagy záró szöveg, markdown-jelölés nélkül."
            )
            continue
        break

    assert result is not None
    if not result.ok or result.blueprint is None:
        return BlueprintOutcome(
            ok=False,
            status="error",
            reason=result.reason,
            error_message=(
                "A modell válasza nem érvényes homiletikai tervrajz — nem "
                "került mentésre. Próbáld újra."
            ),
        )

    store_generated_blueprint_result(
        session_state,
        blueprint=result.blueprint,
        context_hash=context.context_hash,
    )
    return BlueprintOutcome(
        ok=True,
        status="generated",
        blueprint=result.blueprint,
        context_hash=context.context_hash,
    )


__all__ = [
    "GenerateFn",
    "BlueprintContext",
    "BlueprintOutcome",
    "BlueprintValidationResult",
    "BLUEPRINT_SYSTEM_PROMPT",
    "BLUEPRINT_RESPONSE_SCHEMA",
    "BLUEPRINT_CONTEXT_VERSION",
    "ARC_FIT_VERDICTS",
    "STRUCTURE_MODES",
    "ALLOWED_GROUNDED_IN",
    "compute_blueprint_context_hash",
    "build_blueprint_generation_context",
    "build_blueprint_prompt",
    "validate_blueprint_response",
    "generate_sermon_blueprint",
]
