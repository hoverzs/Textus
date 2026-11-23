"""RESET 2E-3 — a felhasználónak szánt RÉSZLETES vázlat MI-generálása.

Ez a kétlépcsős vázlatmotor MÁSODIK lépcsője:

    kanonikus input -> (RESET 2E-2) HOMILETIKAI BLUEPRINT -> RÉSZLETES VÁZLAT

A blueprint DÖNT (homiletikai szerkezet, arc_fit, mozgások), ez a modul
KIBONT: a MÁR ELDÖNTÖTT, koherens blueprint-mozgásokból készít részletes,
szerkeszthető, a szószékre magával vihető munkavázlatot. Nem gondolja újra
a prédikációt, nem végez új exegézist, nem választ új szerkezetet.

MODULNÉV-MEGJEGYZÉS: a kódbázisban MÁR LÉTEZIK egy `sermon_workshop_
outline_ai.py` — az a RÉGI, aktív vázlatmotor (M10) AI-rétege, amit
számos production fájl importál (`sermon_outline_engine.py`,
`sermon_workshop_ui.py`, `workshop_nav_ui.py`, `sermon_workshop_data.py`
és ~25 teszt). EZ a modul TUDATOSAN más néven jött létre
(`sermon_workshop_developed_outline_ai.py`), hogy ne ütközzön vagy
írja felül a régi modult. A két rendszer ebben a fázisban egymástól
FÜGGETLEN — a kétlépcsős vázlatmotor (blueprint -> developed outline) a
régi vázlatmotort NEM helyettesíti és NEM hívja.

SZÁNDÉKOSAN KÜLÖN modul a `sermon_workshop_blueprint_ai.py`-tól is — a
két lépcső AI-döntési tere világosan elkülönül:
  - saját, önálló rendszerpromptot használ — SEMMILYEN megosztott
    `BASE_SYSTEM_PROMPT`-ot nem örököl, és nem örökli a
    `BLUEPRINT_SYSTEM_PROMPT`-ot sem;
  - nem hívja a régi section-szintű MI-segédeket, nem importál
    `sermon_workshop_arc_ai`-ból vagy `sermon_workshop_refinement_ai`-ból;
  - az AI-hívó függvényt (`generate_fn`) a hívó adja át; ez a modul maga
    sosem importálja `app.generate_text`-et.

EGYETLEN, SZÁNDÉKOS ÉS DOKUMENTÁLT KIVÉTEL: a blueprint FRISSESSÉGÉNEK
ellenőrzéséhez (RESET 2E-3, 6. pont) újra kell tudni számolni "az aktuális
kanonikus bemenetből épített blueprint input-context hash"-t — ehhez NEM
készül párhuzamos hash-logika, hanem a `sermon_workshop_blueprint_ai`
MÁR MEGLÉVŐ, exportált `build_blueprint_generation_context` helperét
használja újra. Ugyanígy a válaszséma szerkezet-mód felsorolásához a
blueprint-réteg már meglévő `STRUCTURE_MODES` konstansát importálja —
nem duplikálja kézzel. Ez az EGYETLEN irányú függés (ez a modul a
blueprint_ai-tól a KIZÁRÓLAG a determinisztikus kontextus-szerződését
veszi át, sosem a homiletikai döntési logikáját, promptját vagy
validátorát).

BEMENETI FEGYELEM (RESET 2E-3 alapszabály): a második modellhívás
KIZÁRÓLAG az igehelyet, a bibliai szöveget (groundingként) és az aktuális,
validált `sermon_workshop.blueprint` TARTALMÁT kapja. Nem kap újra nyers
Textusműhely-blobot, `text_summary`-t, `text_main_idea`-t,
`sermon_main_idea`-t, nyers `arc.*`-ot, `arc_candidate`-et,
`field_refinements`-et, `developed_outline_candidate`-et vagy legacy
mezőt — ezek homiletikai lényege már a blueprintben van.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, MutableMapping

from sermon_workshop_blueprint_ai import (
    STRUCTURE_MODES,
    build_blueprint_generation_context,
)
from sermon_workshop_data import (
    empty_blueprint,
    normalize_blueprint,
    store_generated_developed_outline_result,
)
from llm_text_utils import starts_with_provider_warning

GenerateFn = Callable[..., str]

# A kontextus-payload verziója — ha a figyelembe vett mezők köre valaha
# bővül/szűkül, ezt kötelező növelni.
DEVELOPED_OUTLINE_CONTEXT_VERSION = "outline_ctx_v1"

# Védekező felső korlát — ugyanaz az érték, mint az adatmodell
# (`sermon_workshop_data._STRUCTURE_MOVEMENTS_MAX`) és a blueprint-réteg
# (`sermon_workshop_blueprint_ai._MOVEMENTS_MAX`) saját, önálló másolata.
_MOVEMENTS_MAX = 12


# =============================================================================
# Generálási kontextus — determinisztikus, kizárólag a blueprintből
# =============================================================================


@dataclass(frozen=True)
class OutlineContext:
    """A részletes vázlat generálásának TELJES, determinisztikus bemenete.

    `blueprint` a kanonikus `sermon_workshop.blueprint` NORMALIZÁLT
    tartalma (nem csak egy hash-referencia) — ez teszi lehetővé, hogy két,
    azonos upstream input-context hash-ű, de TARTALMILAG eltérő blueprint
    eltérő outline-context-hash-t kapjon (RESET 2E-3, 8. pont).

    `blueprint_context_hash` a `sermon_workshop.blueprint_meta.
    context_hash` — az upstream identitás, amivel a frissesség-ellenőrzés
    összeveti az aktuális kanonikus bemenetet."""

    reference: str
    passage_text: str
    blueprint: dict[str, Any]
    blueprint_context_hash: str
    context_hash: str

    def missing_required_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.reference.strip():
            missing.append("igehely")
        if not self.passage_text.strip():
            missing.append("bibliai szöveg")
        if not _blueprint_has_content(self.blueprint):
            missing.append("homiletikai blueprint")
        if not self.blueprint_context_hash.strip():
            missing.append("blueprint kontextusazonosító")
        return missing

    def is_valid(self) -> bool:
        return not self.missing_required_fields()


def compute_developed_outline_context_hash(context: OutlineContext) -> str:
    """"Pontosan ebből a blueprint-verzióból és ebből a textusból
    készült-e ez a vázlat?" — determinisztikus azonosító.

    A blueprint TÉNYLEGES, normalizált tartalma kerül a payloadba (nem
    csak az upstream hash), ezért a blueprint tartalmi változása MÁS
    hash-t eredményez akkor is, ha a `blueprint_context_hash` (upstream
    identitás) véletlenül azonos maradt.

    SOSEM tartalmaz: `generated_at`-ot, UI-state-et, candidate-et vagy nem
    használt legacy adatot."""
    payload = {
        "version": DEVELOPED_OUTLINE_CONTEXT_VERSION,
        "reference": context.reference,
        "passage_text": context.passage_text,
        "blueprint": context.blueprint,
        "blueprint_context_hash": context.blueprint_context_hash,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _s(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first_nonempty_str(session_state: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        val = session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _blueprint_has_content(blueprint: Mapping[str, Any]) -> bool:
    """Van-e a blueprintben ténylegesen kibontható homiletikai döntés —
    nem csak üres alapérték."""
    if not _s(blueprint.get("central_claim")):
        return False
    structure = blueprint.get("recommended_structure")
    structure = structure if isinstance(structure, dict) else {}
    if not _s(structure.get("mode")):
        return False
    movements = structure.get("movements")
    return isinstance(movements, list) and len(movements) > 0


def build_developed_outline_context(
    session_state: Mapping[str, Any],
) -> OutlineContext:
    """A kanonikus vázlat-bemenet determinisztikus összeállítása.

    KIZÁRÓLAG az igehelyet, a bibliai szöveget és a kanonikus
    `sermon_workshop.blueprint`/`blueprint_meta` tartalmát olvassa —
    semmilyen nyers Textusműhely-mezőt, candidate-et vagy legacy adatot."""
    reference = _first_nonempty_str(session_state, "last_igehely", "igehely_input")
    passage_text = _first_nonempty_str(
        session_state, "passage_text", "passage_text_input"
    )

    sw = session_state.get("sermon_workshop")
    sw = sw if isinstance(sw, dict) else {}
    blueprint_raw = sw.get("blueprint")
    blueprint = (
        normalize_blueprint(blueprint_raw)
        if isinstance(blueprint_raw, dict)
        else empty_blueprint()
    )
    meta_raw = sw.get("blueprint_meta")
    blueprint_context_hash = (
        _s(meta_raw.get("context_hash")) if isinstance(meta_raw, dict) else ""
    )

    context = OutlineContext(
        reference=reference,
        passage_text=passage_text,
        blueprint=blueprint,
        blueprint_context_hash=blueprint_context_hash,
        context_hash="",
    )
    if not context.missing_required_fields():
        context = replace(
            context, context_hash=compute_developed_outline_context_hash(context)
        )
    return context


# =============================================================================
# Blueprint-frissesség — a blueprint_ai MEGLÉVŐ context builderének
# újrafelhasználásával, párhuzamos hash-logika nélkül
# =============================================================================


def compute_current_blueprint_input_hash(session_state: Mapping[str, Any]) -> str:
    """Az AKTUÁLIS kanonikus bemenetből (igehely, textus, két főgondolat,
    arc-pontok, Textusműhely-átadás) újraszámolt blueprint input-context
    hash — a `sermon_workshop_blueprint_ai.build_blueprint_generation_
    context` szerződésének újrafelhasználásával."""
    return build_blueprint_generation_context(session_state).context_hash


def is_blueprint_fresh(session_state: Mapping[str, Any]) -> bool:
    """True, ha a kanonikus blueprint UGYANABBÓL a bemenetből készült,
    mint amit a jelenlegi kanonikus state most adna — azaz a
    `blueprint_meta.context_hash` egyezik az aktuális, újraszámolt
    input-context hash-sel. Hiányzó tárolt hash sosem "friss"."""
    sw = session_state.get("sermon_workshop")
    sw = sw if isinstance(sw, dict) else {}
    meta = sw.get("blueprint_meta")
    stored_hash = _s(meta.get("context_hash")) if isinstance(meta, dict) else ""
    if not stored_hash:
        return False
    current_hash = compute_current_blueprint_input_hash(session_state)
    return bool(current_hash) and current_hash == stored_hash


# =============================================================================
# Rendszerprompt + válaszséma
# =============================================================================

DEVELOPED_OUTLINE_SYSTEM_PROMPT = """SZEREP: Református lelkész-munkatárs vagy, aki egy MÁR ELDÖNTÖTT homiletikai gondolatmenetet bont ki részletes, a szószékre magával vihető prédikációs munkavázlattá.

MIT KÉSZÍTESZ: részletes munkavázlatot. NEM kész, felolvasható prédikációt, és NEM szecskázott, címszavas AI-outline-t — olyan vázlatot, amelyből a prédikátor a saját nyelvén ténylegesen megszólalhat.

MIT NEM CSINÁLSZ:
- NEM gondolod újra a prédikációt, és nem alakítasz ki új homiletikai gondolatmenetet.
- NEM végzel új exegézist, és nem találsz ki új háttéradatot.
- NEM választasz új homiletikai szerkezetet, és nem változtatod meg a `structure_mode`-ot — pontosan azt add vissza, amit a blueprint megad.
- NEM döntöd el újra, mennyire hordozza a textus a hétpontos ívet — ez a döntés a blueprintben MÁR MEGSZÜLETETT.
- NEM adsz hozzá, nem törölsz és nem rendezel át mozgást, és nem nevezed át a `key`-eket: pontosan a blueprint mozgásait bontod ki, ugyanannyit, ugyanabban a sorrendben.
- NEM írod át önkényesen a felhasználó gondolatmenetét: ha egy mozgás felhasználói vázlatpontra épül, a központi gondolatát megőrzöd — kibontod, világosabbá teszed, de nem cseréled le egy másik ötletre.
- NEM "oldod fel" csendben a blueprint figyelmeztetéseiben jelzett feszültségeket — azok korlátozó kontextusként szolgálnak a generáláshoz, nem javítandó hibaként.
- NEM írsz előbb hosszú, kész prédikációs prózát azért, hogy azt utána kivonatold — közvetlenül a strukturált blueprintből dolgozol.
- A KANONIKUS BLUEPRINT BIZONYTALANSÁGI SZINTJÉT ŐRZÖD MEG. Ha a blueprint (vagy a mögötte álló exegetikai/kortörténeti anyag) egy állítást vitatottként, bizonytalanként vagy több legitim értelmezés egyikeként kezel, a részletes vázlat NE emelje ezt kategorikus, eldöntött tényként. NE írj ilyet: "A küzdő fél maga Isten." / "…egyértelműen isteni beavatkozásra utal." / "…egyértelműen isteni találkozásként…" / "…de a találkozás isteni dimenziója nyilvánvaló." — az "egyértelműen" szó és ehhez hasonló lezáró minősítők (biztosan, kétségtelenül, nyilvánvalóan, nyilvánvaló — RAGOZOTT ALAKBAN IS) TILOSAK egy olyan kérdésnél, amit a forrásanyag maga vitatottnak vagy homályosnak nevez — akkor is, ha a mondat korábbi fele már helyesen nyitva hagyta a kérdést: ne zárd le az imént nyitva hagyott bizonytalanságot egy ilyen szóval a MONDAT MÁSIK FELÉBEN. Írj helyette olyat, hogy "Jákób a találkozást Istennel való találkozásként értelmezi; a küzdő fél pontos identitását a szöveg nyitva hagyja, amit a hagyomány többféleképpen értelmezett." Ugyanez vonatkozik minden bizonytalan történeti, teológiai vagy nyelvi állításra — a homiletikai alkalmazás lehet magabiztos, de az ALAPJÁUL szolgáló, vitatott tényállítás nem.
- HOMILETIKAI KÖVETKEZTETÉST NE FOGALMAZZ ÚGY, MINTHA MAGA A TEXTUS BIZONYÍTANÁ. Írás közben tartsd fejben a különbséget — akkor is, ha ez a végleges szövegben nem külön címkeként jelenik meg, hanem a megfogalmazás módjában — (1) amit a textus explicit mond; (2) amit az exegézis valószínű vagy lehetséges értelmezésként ad; (3) amit a prédikáció homiletikai alkalmazásként épít tovább ezekre. Egy homiletikai vagy teológiai alkalmazás lehet magabiztos és bátor megfogalmazású, de NE állítsd be úgy, mintha a szöveg maga mondaná vagy bizonyítaná — jelöld meg nyelvileg alkalmazásként (pl. "homiletikailag…", "ez lehetőséget ad arra, hogy…", "megnyithatja a … témát"), ne textuális ténymegállapításként. Példa — ROSSZ: "A sérülés azt mutatja, hogy Isten ereje a gyengeségben teljesedik ki." JOBB: "Homiletikailag a sérülés megnyithatja a gyengeség és az Istentől való függés témáját." ROSSZ: "Jákób a csalóból Isten harcosává válik." JOBB: "A névváltoztatás új identitást és rendeltetést jelez; ennek pontos teológiai jelentését ne szűkítsd egyetlen szóetimológiai formulára." Hasonlóképpen: ha egy nehézség/küzdelem "szükségszerűen" vagy "elkerülhetetlenül" az átalakulás/növekedés része — mintha ez maga a textus kategorikus kijelentése lenne —, az UGYANAZ a hiba: fogalmazz helyette explicit homiletikai keretezéssel, pl. "a történet lehetőséget ad annak megfogalmazására, hogy bizonyos küzdelmek mögött Isten formáló jelenléte is felismerhető" jellegű, saját szavaiddal megfogalmazott mondattal — SOSE a jelen instrukcióban szereplő bármely mintamondatot szó szerint vagy majdnem szó szerint átvéve, egy másik mozgásban megismételve. Kerüld az olyan mondatszerkezeteket is, ahol egy konkrét textuális részlet (pl. egy sérülés, egy név, egy cselekedet) "mutatja", "megmutatja" vagy "bizonyítja", hogy egy elvont teológiai/homiletikai állítás igaz — ez ugyanaz a hiba MÁS SZAVAKKAL, akkor is, ha az "egyértelműen" szót nem használod. TILOS: "…megmutatva, hogy Isten ereje a gyengeségben teljesedik ki." — ez homiletikai alkalmazást állít be textuális bizonyítékként. JOBB: "Homiletikailag a sebesülés a gyengeségben megélt isteni erő témáját nyithatja meg."

TÁMASZ HASZNÁLATA: kizárólag a blueprint támogató anyagából (exegetikai, eredeti nyelvi, történeti/teológiai) dolgozhatsz. Nem hivatkozhatsz olyan állításra, aminek nincs alapja a blueprintben vagy a mellékelt bibliai szövegben. A bibliai szöveget kizárólag groundingként használd: szöveghűség-ellenőrzésre és idézetek pontosítására — nem új exegézis forrásaként. Eredeti nyelvi elem mozgásonként jellemzően 0 vagy 1 — csak ha ténylegesen fontos, és akkor is magyarul értelmezhető megállapításként, sosem díszítő Strong-számként vagy nyers szóalakként.

TÖMÖRSÉG ÉS REDUNDANCIA-TILALOM (FONTOS — a végső vázlat célja a gyors, szószékre vihető áttekinthetőség, nem a kimerítő teljesség): a `exegetical_support`, `illustration_direction` és `application_direction` mezők NEM automatikusan kitöltendők minden egyes mozgásnál. Ha egy adat már természetesen beleépült a `development` szövegébe, NE ismételd meg még egyszer külön mezőben ugyanazt.

EGY MOZGÁS RÉSZLETESSÉGE:
- `title`: rövid, beszédes cím.
- `function`: a mozgás homiletikai szerepe.
- `main_claim`: 1-2 tömör mondat.
- `development`: jellemzően 2-3 önálló kibontási pont — valódi külön gondolatok, nem egymás parafrázisai. Ha a mozgásnak van természetes, konkrét alkalmazása, az ne külön mezőben, hanem az UTOLSÓ development-pont 1-2 mondatában jelenjen meg — ilyenkor az `application_direction` maradjon üres string.
- `exegetical_support`: ÜRES LISTA az alapértelmezett. Csak akkor tölts ki (legfeljebb 1 elem), ha van olyan, különösen fontos vershivatkozás, eredeti nyelvi adat vagy szövegi megfigyelés, amit a prédikátor prédikálás közben gyors kapaszkodóként külön akar látni — NEM azért, mert "kell" egy exegetikai blokk minden ponthoz.
- `original_language_support`: 0-1 elem, csak ha tényleg fontos.
- `historical_theological_support`: 0-1 releváns elem.
- `illustration_direction`: ÜRES STRING az alapértelmezett — a LEGTÖBB mozgásnál maradjon üres. TILOS az olyan mondatszerkezet, amely "Egy történet/példa arról/arra, amikor valaki…" mintát követ, még akkor is, ha utána konkrétnak tűnő szó áll (pl. TILOS: "Egy történet arról, amikor valaki váratlanul tapasztalta meg Isten jelenlétét", TILOS: "Egy példa arra, amikor valaki kitartóan küzdött egy célért" — ezek NEM illusztrációk, csak illusztráció-keresési feladatok, akkor is, ha az elvont hallgatói tapasztalatot nevezik meg konkrétan). Ha mégis kitöltöd, egy MEGNEVEZETT, behatárolt területet, szerepkört vagy jelenetet adj meg — olyan konkrétsággal, hogy egy prédikátor AZONNAL tudjon mit keresni, ne egy újabb absztrakciót (pl. "egy sportoló visszatérése tartós sérülés után", "egy szülő és felnőtt gyermeke közötti régi sérelem rendezése", nem pedig "amikor valaki nehézségen megy át"). Ha nincs ilyen MEGNEVEZETT, szűk ötleted, hagyd üresen — ez JOBB, mint egy elvont keresési irány. Ne találj ki ellenőrizhetetlen történelmi vagy valós személyhez köthető történetet.
- `application_direction`: ÜRES STRING az alapértelmezett — az esetek túlnyomó többségében az alkalmazás a `development` utolsó pontjába épül be (ld. fent). Csak akkor tölts ki ide külön, ha az alkalmazás ténylegesen NEM fér el természetesen a development utolsó pontjában.
- `transition_to_next`: rövid, 1-2 mondat, valóban a KÖVETKEZŐ mozgás felé vezessen — ne az előző pont összefoglalása legyen. Az utolsó mozgásnál lehet üres.
- `structure_note`: rövid; hétpontos szerkezetnél akár üres is lehet, összevont/egyedi szerkezetnél röviden jelezheti az eltérés okát. Ne legyen hosszú metodikai magyarázat.

STÍLUS: magyar nyelven, természetes, homiletikailag rendezett, nem dagályos, nem generikus, nem coach-szerű. Kerüld a szecskázott, címszavas AI-outline-t éppúgy, mint a teljes mondatokból álló, kész prédikációs prózát. A `development` elemek 1-3 mondatos, tömör, de tartalmas egységek legyenek. A cél kb. 15-25%-kal kevesebb szöveg, mint egy olyan vázlat, ami minden mozgásnál minden opcionális mezőt kitölt — az érdemi tartalom elvesztése nélkül. Ne legyen vázlatosan szegényes: a tömörség a redundancia csökkentéséből fakadjon, ne a tartalom elhagyásából.

KIMENET: kizárólag egy JSON objektum a megadott séma szerint."""


DEVELOPED_OUTLINE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "structure_mode": {"type": "string", "enum": list(STRUCTURE_MODES)},
        "structure_note": {"type": "string"},
        "movements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "title": {"type": "string"},
                    "function": {"type": "string"},
                    "main_claim": {"type": "string"},
                    "development": {"type": "array", "items": {"type": "string"}},
                    "exegetical_support": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "original_language_support": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "historical_theological_support": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "illustration_direction": {"type": "string"},
                    "application_direction": {"type": "string"},
                    "transition_to_next": {"type": "string"},
                },
                "required": [
                    "key",
                    "title",
                    "function",
                    "main_claim",
                    "development",
                    "exegetical_support",
                    "original_language_support",
                    "historical_theological_support",
                    "illustration_direction",
                    "application_direction",
                    "transition_to_next",
                ],
            },
        },
    },
    "required": ["structure_mode", "structure_note", "movements"],
}


def build_developed_outline_prompt(context: OutlineContext) -> str:
    """A tényleges feladatprompt — kizárólag az igehelyet, a bibliai
    szöveget és a blueprint TARTALMÁT adja át, címkézve. Semmilyen nyers
    Textusműhely- vagy sermon-workshop mezőt nem olvas közvetlenül a
    session_state-ből: mindent a már megépített `context.blueprint`-ből
    vesz."""
    bp = context.blueprint
    structure = bp.get("recommended_structure")
    structure = structure if isinstance(structure, dict) else {}
    mode = _s(structure.get("mode"))
    movements_raw = structure.get("movements")
    movements = movements_raw if isinstance(movements_raw, list) else []
    support = bp.get("key_support")
    support = support if isinstance(support, dict) else {}

    parts: list[str] = [
        f"IGEHELY: {context.reference}",
        "",
        "BIBLIAI SZÖVEG (textus — kizárólag szöveghűség-ellenőrzéshez és "
        "groundinghoz, NEM új exegézis forrása):",
        context.passage_text,
        "",
        "A BLUEPRINT — a homiletikai döntés MÁR MEGSZÜLETETT, ezt nem "
        "gondolhatod újra:",
        f"- Központi állítás (`central_claim`): {_s(bp.get('central_claim'))}",
        f"- A textus szöveghű középpontja (`textual_center`): "
        f"{_s(bp.get('textual_center'))}",
    ]
    if _s(bp.get("listener_tension")):
        parts.append(
            f"- Hallgatói feszültség (`listener_tension`): "
            f"{_s(bp.get('listener_tension'))}"
        )
    if _s(bp.get("theological_turn")):
        parts.append(
            f"- Teológiai fordulat (`theological_turn`): "
            f"{_s(bp.get('theological_turn'))}"
        )
    parts.append(
        f"- A hallgató útja (`desired_listener_movement`): "
        f"{_s(bp.get('desired_listener_movement'))}"
    )

    expected_keys = [
        _s(m.get("key")) if isinstance(m, dict) else "" for m in movements
    ]
    parts += [
        "",
        f'SZERKEZETI MÓD (`structure_mode` = "{mode}") — a válaszodban '
        "PONTOSAN ezt kell visszaadnod, nem változtathatod meg.",
        "",
        "A KIBONTANDÓ MOZGÁSOK — pontosan ennyi, pontosan ezekkel a "
        "kulcsokkal, pontosan ebben a sorrendben kell szerepelniük a "
        "válaszodban. Új mozgást NEM adhatsz hozzá, meglévőt NEM "
        "törölhetsz, NEM rendezheted át, és a `key`-t sem nevezheted át:",
    ]
    for m in movements:
        if not isinstance(m, dict):
            continue
        key = _s(m.get("key"))
        function = _s(m.get("function"))
        core_idea = _s(m.get("core_idea"))
        grounded_raw = m.get("grounded_in")
        grounded = grounded_raw if isinstance(grounded_raw, list) else []
        parts.append(f"\n### [`{key}`]")
        if function:
            parts.append(f"Szerep: {function}")
        if core_idea:
            parts.append(f"Központi gondolat (őrizd meg, ezt bontsd ki): {core_idea}")
        if grounded:
            parts.append(f"Alap: {', '.join(str(g) for g in grounded)}")

    exeg = support.get("exegetical")
    exeg = exeg if isinstance(exeg, list) else []
    orig = support.get("original_language")
    orig = orig if isinstance(orig, list) else []
    hist = support.get("historical_theological")
    hist = hist if isinstance(hist, list) else []

    if exeg:
        parts += [
            "",
            "EXEGETIKAI TÁMASZ (kizárólag ebből dolgozhatsz, új exegézist "
            "nem kezdhetsz):",
        ]
        parts += [f"- {x}" for x in exeg]
    if orig:
        parts += [
            "",
            "EREDETI NYELVI TÁMASZ (kizárólag ebből, díszítés nélkül):",
        ]
        parts += [f"- {x}" for x in orig]
    if hist:
        parts += ["", "TÖRTÉNETI/TEOLÓGIAI TÁMASZ (kizárólag ebből):"]
        parts += [f"- {x}" for x in hist]

    if _s(bp.get("illustration_direction")):
        parts += [
            "",
            "ILLUSZTRÁCIÓS IRÁNY a blueprintből (irányadó, mozgásonként "
            f"konkretizálható): {_s(bp.get('illustration_direction'))}",
        ]
    if _s(bp.get("application_direction")):
        parts += [
            "",
            "ALKALMAZÁSI IRÁNY a blueprintből (irányadó): "
            f"{_s(bp.get('application_direction'))}",
        ]

    warnings_raw = bp.get("warnings")
    warnings = warnings_raw if isinstance(warnings_raw, list) else []
    if warnings:
        parts += [
            "",
            "FIGYELMEZTETÉSEK a blueprintből — ezek KORLÁTOZÓ kontextusok "
            "a generáláshoz, NE oldd fel őket önkényesen, és ne írd át "
            "csendben az érintett tartalmat:",
        ]
        parts += [f"- {w}" for w in warnings]

    parts += [
        "",
        "Készítsd el a részletes prédikációs munkavázlatot a "
        "rendszerutasítás szerint, kizárólag a megadott JSON sémával "
        "válaszolva. A `movements` tömb pontosan ennyi elemet "
        "tartalmazzon, pontosan ezekkel a kulcsokkal, pontosan ebben a "
        f"sorrendben: {expected_keys}.",
    ]
    return "\n".join(parts)


# =============================================================================
# Válasz-kinyerés és SZIGORÚ szemantikai validáció
# =============================================================================


def _extract_json_object(raw: Any) -> dict[str, Any] | None:
    """Önálló, kis JSON-kinyerő — szándékosan NEM importál más
    MI-modulokból, hogy ez a modul teljesen független maradjon."""
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
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


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
class DevelopedOutlineValidationResult:
    ok: bool
    reason: str = ""
    outline: dict[str, Any] | None = None


def validate_developed_outline_response(
    raw: Any, *, blueprint: Mapping[str, Any]
) -> DevelopedOutlineValidationResult:
    """SZIGORÚ szemantikai validáció a blueprint szerkezetéhez képest.

    Biztonságos NORMALIZÁLÁS megengedett (trimmelés, nem-string
    listaelemek kihagyása). SZERKEZETI ELTÉRÉS a blueprinttől viszont
    ELUTASÍTÁS — a válasz mozgásainak "helyrehozása" (átnevezés,
    átrendezés) itt veszélyes lenne, mert egy modell által elrontott
    szerkezet csendben helyesnek látszana.

    Elutasítási okok (`reason`): `not_json`, `structure_mode_mismatch`,
    `invalid_movements`, `empty_movements`, `too_many_movements`,
    `invalid_movement_entry`, `invalid_movement_key`,
    `movement_count_mismatch`, `movement_key_mismatch`,
    `movement_order_mismatch`, `empty_title`, `empty_function`,
    `empty_main_claim`, `empty_development`."""
    obj = _extract_json_object(raw)
    if obj is None:
        return DevelopedOutlineValidationResult(ok=False, reason="not_json")

    structure = blueprint.get("recommended_structure")
    structure = structure if isinstance(structure, dict) else {}
    blueprint_mode = _s(structure.get("mode"))
    blueprint_movements_raw = structure.get("movements")
    blueprint_movements = (
        blueprint_movements_raw if isinstance(blueprint_movements_raw, list) else []
    )
    blueprint_keys = [
        _s(m.get("key")) if isinstance(m, dict) else "" for m in blueprint_movements
    ]

    structure_mode = _s(obj.get("structure_mode"))
    if structure_mode != blueprint_mode:
        return DevelopedOutlineValidationResult(
            ok=False, reason="structure_mode_mismatch"
        )

    movements_raw = obj.get("movements")
    if not isinstance(movements_raw, list):
        return DevelopedOutlineValidationResult(ok=False, reason="invalid_movements")
    if not movements_raw:
        return DevelopedOutlineValidationResult(ok=False, reason="empty_movements")
    if len(movements_raw) > _MOVEMENTS_MAX:
        return DevelopedOutlineValidationResult(
            ok=False, reason="too_many_movements"
        )

    for item in movements_raw:
        if not isinstance(item, dict):
            return DevelopedOutlineValidationResult(
                ok=False, reason="invalid_movement_entry"
            )
        if not _s(item.get("key")):
            return DevelopedOutlineValidationResult(
                ok=False, reason="invalid_movement_key"
            )

    keys = [_s(item.get("key")) for item in movements_raw]
    if len(keys) != len(blueprint_keys):
        return DevelopedOutlineValidationResult(
            ok=False, reason="movement_count_mismatch"
        )
    if set(keys) != set(blueprint_keys):
        return DevelopedOutlineValidationResult(
            ok=False, reason="movement_key_mismatch"
        )
    if keys != blueprint_keys:
        return DevelopedOutlineValidationResult(
            ok=False, reason="movement_order_mismatch"
        )

    movements: list[dict[str, Any]] = []
    for item in movements_raw:
        title = _s(item.get("title"))
        if not title:
            return DevelopedOutlineValidationResult(ok=False, reason="empty_title")
        function = _s(item.get("function"))
        if not function:
            return DevelopedOutlineValidationResult(ok=False, reason="empty_function")
        main_claim = _s(item.get("main_claim"))
        if not main_claim:
            return DevelopedOutlineValidationResult(
                ok=False, reason="empty_main_claim"
            )
        development = _clean_str_list(item.get("development"))
        if not development:
            return DevelopedOutlineValidationResult(
                ok=False, reason="empty_development"
            )

        movements.append(
            {
                "key": _s(item.get("key")),
                "title": title,
                "function": function,
                "main_claim": main_claim,
                "development": development,
                "exegetical_support": _clean_str_list(item.get("exegetical_support")),
                "original_language_support": _clean_str_list(
                    item.get("original_language_support")
                ),
                "historical_theological_support": _clean_str_list(
                    item.get("historical_theological_support")
                ),
                "illustration_direction": _s(item.get("illustration_direction")),
                "application_direction": _s(item.get("application_direction")),
                "transition_to_next": _s(item.get("transition_to_next")),
            }
        )

    outline = {
        "structure_mode": structure_mode,
        "structure_note": _s(obj.get("structure_note")),
        "movements": movements,
    }
    return DevelopedOutlineValidationResult(ok=True, outline=outline)


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos starts_with_provider_warning (llm_text_utils.py; azonosság: tests/test_llm_text_utils.py).
_looks_like_api_error = starts_with_provider_warning


# =============================================================================
# Orchestráció — egyetlen belépési pont
# =============================================================================


@dataclass(frozen=True)
class DevelopedOutlineOutcome:
    ok: bool
    status: str  # "candidate" | "blocked" | "error"
    reason: str = ""
    error_message: str = ""
    outline: dict[str, Any] | None = None
    context_hash: str = ""


def generate_developed_outline(
    session_state: MutableMapping[str, Any],
    *,
    generate_fn: GenerateFn,
    bypass_cooldown: bool = False,
) -> DevelopedOutlineOutcome:
    """Egyetlen belépési pont: determinisztikus kontextus -> blueprint
    frissesség-ellenőrzés -> legfeljebb EGY AI-hívás -> SZIGORÚ,
    blueprint-konzisztens validálás -> és KIZÁRÓLAG érvényes eredmény
    esetén candidate-ként tárolás (`store_generated_developed_outline_
    result` — SOHA nem ír közvetlenül a kanonikus `developed_outline`
    mezőbe, az ELSŐ generálás is candidate).

    Hiányzó vagy elavult (stale) blueprint esetén EL SEM INDUL az
    AI-hívás — determinisztikus, `status="blocked"` eredmény érkezik.

    `bypass_cooldown`: FINAL SERMON WORKFLOW + OUTLINE PRESENTATION
    POLISH (2026-08-21) — KIZÁRÓLAG akkor `True`, ha a hívó UGYANAZON a
    gombnyomáson belül közvetlenül egy sikeres automatikus blueprint-
    generálás UTÁN hívja ezt (a globális `GEMINI_COOLDOWN_S` két
    LOGIKAILAG FÜGGETLEN felhasználói hívás közé való, nem egyetlen
    gombnyomás belső, láncolt lépései közé — ugyanaz az elv, mint amit a
    `generate_text(..., bypass_cooldown=True)` már meglévő "ugyanazon
    gombnyomás fill/repair hívásai" kivétele dokumentál)."""
    context = build_developed_outline_context(session_state)

    if not context.reference.strip():
        return DevelopedOutlineOutcome(
            ok=False,
            status="blocked",
            reason="missing_reference",
            error_message=(
                "Hiányzik az igehely a részletes vázlat elkészítéséhez."
            ),
        )
    if not context.passage_text.strip():
        return DevelopedOutlineOutcome(
            ok=False,
            status="blocked",
            reason="missing_passage_text",
            error_message=(
                "Hiányzik a bibliai szöveg a részletes vázlat "
                "elkészítéséhez."
            ),
        )
    if not _blueprint_has_content(context.blueprint):
        return DevelopedOutlineOutcome(
            ok=False,
            status="blocked",
            reason="missing_blueprint",
            error_message=(
                "Nincs érvényes homiletikai blueprint — előbb azt kell "
                "elkészíteni."
            ),
        )
    if not context.blueprint_context_hash.strip():
        return DevelopedOutlineOutcome(
            ok=False,
            status="blocked",
            reason="missing_blueprint_context_identity",
            error_message=(
                "A blueprint kontextusazonosítója hiányzik — a "
                "frissesség nem ellenőrizhető."
            ),
        )
    if not is_blueprint_fresh(session_state):
        return DevelopedOutlineOutcome(
            ok=False,
            status="blocked",
            reason="blueprint_stale",
            error_message=(
                "A blueprint elavult: a kanonikus bemenet megváltozott a "
                "blueprint elkészülte óta. Előbb új blueprintet kell "
                "generálni, csak utána új részletes vázlatot."
            ),
        )

    prompt = build_developed_outline_prompt(context)
    try:
        raw = generate_fn(
            prompt,
            tab_label="Részletes prédikációs munkavázlat",
            use_cache=False,
            system_bundle=DEVELOPED_OUTLINE_SYSTEM_PROMPT,
            include_brevity_directive=False,
            response_mime_type="application/json",
            response_schema=DEVELOPED_OUTLINE_RESPONSE_SCHEMA,
            bypass_cooldown=bypass_cooldown,
        )
    except Exception as exc:  # noqa: BLE001 — a hívónak mindenképp választ kell adnunk
        return DevelopedOutlineOutcome(
            ok=False,
            status="error",
            reason="generate_failed",
            error_message=f"A részletes vázlat generálása sikertelen volt: {exc}",
        )

    if _looks_like_api_error(raw):
        return DevelopedOutlineOutcome(
            ok=False, status="error", reason="api_error", error_message=str(raw)
        )

    result = validate_developed_outline_response(raw, blueprint=context.blueprint)
    if not result.ok or result.outline is None:
        return DevelopedOutlineOutcome(
            ok=False,
            status="error",
            reason=result.reason,
            error_message=(
                "A modell válasza nem érvényes részletes vázlat — nem "
                "került mentésre. Próbáld újra."
            ),
        )

    store_generated_developed_outline_result(
        session_state,
        outline=result.outline,
        reference=context.reference,
        context_hash=context.context_hash,
    )
    return DevelopedOutlineOutcome(
        ok=True,
        status="candidate",
        outline=result.outline,
        context_hash=context.context_hash,
    )


__all__ = [
    "GenerateFn",
    "OutlineContext",
    "DevelopedOutlineOutcome",
    "DevelopedOutlineValidationResult",
    "DEVELOPED_OUTLINE_SYSTEM_PROMPT",
    "DEVELOPED_OUTLINE_RESPONSE_SCHEMA",
    "DEVELOPED_OUTLINE_CONTEXT_VERSION",
    "compute_developed_outline_context_hash",
    "compute_current_blueprint_input_hash",
    "is_blueprint_fresh",
    "build_developed_outline_context",
    "build_developed_outline_prompt",
    "validate_developed_outline_response",
    "generate_developed_outline",
]
