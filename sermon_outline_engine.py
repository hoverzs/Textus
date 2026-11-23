"""Egyetlen közös igehirdetési-vázlat motor (pulpit_outline_v7).

Az Igehirdetési műhely „Igehirdetési vázlat” szekciója (az egyetlen
felhasználói vázlatkészítő belépési pont — a korábbi, párhuzamos
Textusműhely „Gyors vázlat” felület 2026-08-13-án megszűnt) ezt a modult
hívja. Egy kanonikus `movements` séma, egy validátor; tömörítés csak 850
szó felett. Az alsó céltartomány soft jelzés.
Nem importál app.py / sermon_workshop_ui.py fájlból.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, MutableMapping

from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    empty_outline_movement,
    empty_sermon_outline,
    ensure_sermon_workshop_state,
    normalize_sermon_outline,
)
from sermon_workshop_m4_ai import extract_json_object
from sermon_workshop_m5_ai import _is_api_error_text
from prompt_safety import wrap_untrusted_content
from ai_response_validation import sanitize_ai_json

GenerateFn = Callable[..., str]

logger = logging.getLogger("textus.outline")

TAB_OUTLINE = "Igehirdetési vázlat"
DEFAULT_TEMPERATURE = 0.2
_OUTLINE_INCOMPLETE_SENTINEL = "__OUTLINE_TRUNCATED__"
SCHEMA_VERSION = "pulpit_outline_v8"
ENGINE_VERSION = "outline_engine_v8"
LEGACY_SCHEMA_VERSIONS = frozenset(
    {
        "",
        "pulpit_outline_v3",
        "pulpit_outline_v4",
        "pulpit_outline_v5",
        "pulpit_outline_v6",
    }
)
OUTLINE_MAX_OUTPUT_TOKENS = 8000
RAPID_EVIDENCE_SESSION_KEY = "_outline_rapid_evidence_cache"

# ---------------------------------------------------------------------------
# Kanonikus movements-vázlat — nem prédikáció, nem kétsoros séma
# ---------------------------------------------------------------------------

LIMITS = {
    "title_words": 12,
    "focus_words": 40,
    "focus_min_words": 12,
    "intro_words": 80,
    "intro_min_words": 20,
    "intro_sentences_max": 3,
    "point_title_words": 12,
    "layer_min_words": 12,
    "layer_max_words": 60,
    "layer_sentences": 2,
    "point_layers_min_words": 40,
    "point_layers_max_words": 160,
    "conclusion_words": 80,
    "conclusion_min_words": 20,
    "conclusion_sentences_max": 3,
    "scope_note_words": 40,
    "transition_words": 40,
    "min_points": 2,
    "max_points": 5,
    "default_points": 3,
    # 2C.1 (célarchitektúra-terv, 2. fázis, 3. rész): KÜLÖN korlátpár az
    # élő, body_markdown-alapú beszédegység-szegmentáláshoz
    # (`_extract_markdown_movements`/`_assess_outline_structure`).
    # Szándékosan NEM a fenti `min_points`/`max_points` — azok a régi,
    # 2026-08-07 előtti points[] sémát validálják, amit élő AI-generálás
    # ma már nem tölt ki; módosításuk visszamenőleg érintené a régi,
    # mentett vázlatok újravalidálását. Ez a két új kulcs kizárólag az
    # új, Markdown-alapú szerkezeti ellenőrzésen belül él.
    "min_speech_units": 2,
    "max_speech_units": 4,
    # Soft céltartományok (abszolút max mindig 850).
    # Gyakorlatias szószéki jegyzet: kb. 300–500 szó.
    "target_min_words": 300,
    "target_max_words": 500,
    "target_min_2": 280,
    "target_max_2": 420,
    "target_min_3_4": 300,
    "target_max_3_4": 500,
    "target_min_5": 380,
    "target_max_5": 600,
    "soft_floor_words": 250,
    "absolute_max_words": 850,
    "max_prose_block_words": 140,
    "refinement_max": 2,
}

# Soft: under_target / too_thin → warning + opcionális enrich; soha nem önálló reject.
# Compress csak over_absolute_max (>850) / full_sermon_like.
#
# 2C.1: a Markdown beszédegység-szegmentálás SZERKEZETI proxy-jelzései
# (ld. `_assess_outline_structure`). Mindhárom ENRICHABLE — a meglévő
# AI-repair (`_enrich_markdown`) mindegyiknél kap először esélyt —, de
# csak `units_not_distinct` marad SOFT is: ha a javítás után is fennmarad,
# csak figyelmeztetés (a 0.60-as hasonlósági küszöb empirikus, nem elég
# megbízható kemény elutasításhoz). `too_few_speech_units`/
# `too_many_speech_units` NEM soft-only: a 2–4 beszédegység valódi
# kimeneti szerződés — ha a repair után is fennmaradnak, a
# `generate_sermon_outline()` egy külön, kifejezett ellenőrzése (a
# beszédegység-szám-blokk) blokkoló, retryable hibává alakítja őket,
# SOHA nem mechanikus fallbackkel, hanem strukturált `validation_failed`
# eredménnyel — a korábbi mentett vázlat változatlanul megmarad.
SOFT_QUALITY_ISSUES = frozenset(
    {
        "under_target",
        "too_thin",
        "repeated_thematic_triad",
        "generic_filler",
        "units_not_distinct",
    }
)
ENRICHABLE_ISSUES = frozenset(
    {
        "too_thin",
        "focus_too_short",
        "intro_too_short",
        "conclusion_too_short",
        "stub_layer",
        "point_layers_too_short",
        "truncated_sentence",
        "layer_sentence_count",
        "missing_textual_insight",
        "missing_theological_emphasis",
        "missing_listener_movement",
        "generic_filler",
        "repeated_layer_text",
        "repeated_thematic_triad",
        "focus_not_one_sentence",
        "too_few_speech_units",
        "too_many_speech_units",
        "units_not_distinct",
    }
)
COMPRESS_TRIGGER_ISSUES = frozenset(
    {
        "over_absolute_max",
        "full_sermon_like",
        "verbatim_source_copy",
        "forbidden_structure",
        "forbidden_filler",
    }
)

# Prose-bait / legacy fields — soha ne kérjük és ne jelenjenek meg elsődlegesen.
# Megjegyzés: `subpoints` / `application` migrációval beolvasható, de nem kanonikus kimenet.
FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "body",
        "content",
        "exegesis",
        "theological_expansion",
        "grace_connection",
        "listener_connection",
        "transition_logic",
        "full_introduction",
        "full_conclusion",
        "thesis",
        "outline_text",
    }
)

POINT_LAYER_KEYS = (
    "textual_insight",
    "theological_emphasis",
    "listener_movement",
)

FORBIDDEN_HEADINGS: tuple[str, ...] = (
    "Mit rendez ez a pont",
    "Textuális horgony",
    "Teológiai horgony",
    "Textuális/teológiai horgony",
    "Átvezetési logika",
    "Diagnózis → evangéliumi fordulat → Isten válasza",
    "diagnózis → evangéliumi fordulat",
    "Exegetikai kibontás",
    "Exegetikai és teológiai kibontás",
    "Hallgatói és kegyelmi kapcsolat",
    "Kegyelmi kapcsolat",
    "Hallgatói kapcsolat",
    "Hallgatói felismerés",
    "Hallgatói alkalmazás",
    "Alkalmazási pontok",
    "Problémafelvetés",
    "Magyarázat",
    "Teológiai kibontás",
    "Tételmondat (scopus)",
)

# A 2026-08-07 formai átalakítás ELŐTTI, mezőkre/pontokra tagolt struktúra
# technikai mezőnevei — ezek KIZÁRÓLAG az ÚJ, `body_markdown`-alapú formában
# tiltottak (`_has_forbidden_outline_structure`). Szándékosan KÜLÖN tuple a
# `FORBIDDEN_HEADINGS`-től: az a régebbi, univerzálisan tiltott
# (más regresszióból eredő) alcím-mintákat listázza, amik a RÉGI,
# visszafelé-kompatibilis renderelő ágban (`render_structured_outline` régi
# branch) továbbra is legitim módon megjelennek saját szekciócímkeként —
# ha ide kerülnének, a régi vázlatok visszafelé-kompatibilis megjelenítése
# hamisan "tiltott struktúrának" minősülne.
_LEGACY_FIELD_LABELS: tuple[str, ...] = (
    "Igei fókusz",
    "Exegetikai / Eredeti nyelvi mélység",
    "Exegetikai mélység",
    "Gyakorlati alkalmazás",
    "Alkalmazás",
    "Bevezetés és Ráhangolódás",
    "Befejezés és Útravaló",
    "Élethelyzet / Probléma",
    "A Textus Világa (Kontextus)",
    "Fókuszmondat",
    "Bevezetési irány",
    "Megérkezés",
)

# A régi mezőcímke-struktúra felismerésére — ha a modell visszacsúszik a
# tiltott formába, a `forbidden_structure` validációs hiba erre épül.
# 2026-08-07 (2. kör): a szabad, tartalmi mozgás-címkék (pl. "Indítás: ...",
# "I. Az áldozat, amit nem tudunk megmagyarázni") EXPLICIT MEGENGEDETTEK —
# ezért itt KIZÁRÓLAG a névvel azonosítható régi technikai mezőnevekre és a
# zárójeles/fejléc-szintaxisú versszám-jelölésre szűrünk, nem minden
# alcímezésre.
_FORBIDDEN_LABEL_PATTERN = "|".join(re.escape(h) for h in _LEGACY_FIELD_LABELS)
_FORBIDDEN_STRUCTURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?m)^#{1,6}\s"),  # bármilyen markdown-fejléc a fő cím soron kívül
    re.compile(
        rf"\*\*(?:\d{{1,2}}[.)]\s*)?(?:{_FORBIDDEN_LABEL_PATTERN})\s*:?\*\*"
    ),  # pl. "**Igei fókusz:**" vagy sorszámmal "**1. Igei fókusz:**"
    re.compile(
        rf"(?mi)^\s*(?:\d{{1,2}}[.)]\s*)?(?:{_FORBIDDEN_LABEL_PATTERN})\s*:\s*\**\s*$"
    ),  # bare (vagy sorszámozott/félkövér) "Igei fókusz:" sor, semmi utána
    re.compile(
        rf"(?mi)^\s*(?:\d{{1,2}}[.)]\s*)?(?:{_FORBIDDEN_LABEL_PATTERN})\s*:\s+\S"
    ),  # bare "Alkalmazás: <folytatódó tartalom>" — a címke egysoros,
        # tartalommal ellátott formában is tiltott, nem csak önmagában
    re.compile(r"(?m)^\s*\*{0,2}\(?v\.?\s*\d{1,3}[a-c]?(?:\s*[–\-]\s*\d{1,3}[a-c]?)?\)?\*{0,2}\s*$"),  # önálló versszám-sor (opcionálisan félkövér)
    re.compile(
        r"(?m)(?:"
        r"\(\s*v\.?\s*\d{1,3}[a-c]?(?:\s*[–\-]\s*\d{1,3}[a-c]?)?\s*(?:vers(?:ek)?)?\s*\)"
        r"|\(\s*\d{1,3}[a-c]?(?:\s*[–\-]\s*\d{1,3}[a-c]?)?\.\s*vers(?:ek)?\s*\)"
        r")\*{0,2}\s*$",
        re.I,
    ),  # zárójeles versszám-CÍMKE — csak sor/cím VÉGÉN tiltott (pl. "1. Cím (v. 6-8)",
        # vagy félkövér cím esetén "**1. Cím (v. 6-8)**" — a záró "**" jelet a `\*{0,2}`
        # engedi át a sorvég-illesztésen). Egy mondatba ágyazott, folytatódó közbevetés
        # (pl. "...volt (2. vers). Ezután…") NEM ide tartozik, mert utána még van
        # szöveg ugyanabban a bekezdésben.
    re.compile(r"(?m)^\s*[*\-•]\s+\S"),  # bullet-lista jel sor elején — a gondolat-
        # egységek folyó mondatok legyenek, nem itemizált felsorolás (2026-08-08:
        # élesben látott regresszió, amikor a bold+sorszámozott cím alá a modell
        # "*"-jelekkel tagolt katalógusszerű listát írt a folyó szöveg helyett).
)


def _has_forbidden_outline_structure(body: str) -> bool:
    """True, ha a szöveg a régi, mezőkre/pontokra tagolt formát mutatja."""
    raw = _s(body)
    if not raw:
        return False
    return any(pat.search(raw) for pat in _FORBIDDEN_STRUCTURE_PATTERNS)

FORBIDDEN_FILLERS: tuple[str, ...] = (
    "de vajon",
    "ez azonban",
    "itt felmerül a kérdés",
    "nem marad titokban",
)

COMPRESS_INSTRUCTION = (
    "FORMAI TÖMÖRÍTÉS ÉS/VAGY SZÓ SZERINTI ÁTVÉTEL JAVÍTÁSA — a JELZETT "
    "PROBLÉMÁK között szereplő `verbatim_source_copy` azt jelenti, hogy a "
    "vázlattest szó szerint (vagy majdnem szó szerint) átvette a forrásanyag "
    "(bibliai szöveg vagy háttéranyag) egy hosszabb részletét ahelyett, hogy "
    "szintetizálta volna — ezt írd át saját, tömör megfogalmazásra, ne csak "
    "töröld a mondatot. A `forbidden_structure` jelzés azt jelenti, hogy a "
    "vázlat számozott alcímet, mezőcímkét (pl. \"Igei fókusz:\") vagy "
    "zárójeles versszám-jelölést tartalmaz — EZ TILOS, írd át egyetlen, "
    "folyó szövegű bekezdéssorozattá. Ha a `over_absolute_max`/"
    "`full_sermon_like` jelzés is szerepel, a látható vázlat 850 szó felett van. "
    "A kapott vázlat tartalmi és homiletikai ívét őrizd meg; "
    "ne tervezz új vázlatot és ne adj hozzá új exegetikai vagy teológiai állítást. "
    "Csak a fölösleges ismétlést, metaszöveget és prédikációs bőbeszédűséget csökkentsd. "
    "Soha ne vágj félbe mondatot szószám alapján. "
    "Abszolút felső határ 850 szó. "
    "A kanonikus mező neve `body_markdown` — EGY folyó szövegű, bekezdésekre "
    "tagolt gondolatmenet, NEM tömb/pontokra bontott struktúra. "
    "Kizárólag a teljes, javított JSON objektumot add vissza."
)

ENRICH_INSTRUCTION = (
    "CÉLZOTT TARTALMI KIEGÉSZÍTÉS — ha a vázlat felszínes, ismétlődő, vagy "
    "túl rövid. "
    "A kapott vázlat szerkezetét és igehely-beosztását őrizd; "
    "ne írj új prédikációt és ne találj ki verseket. "
    "Gazdagítsd a FORRÁS és a gyors háttércsomag anyagából — konkrét, a "
    "forrásra visszavezethető megfigyeléssel, nem közhellyel. "
    "A `body_markdown` maradjon EGY folyó szövegű, bekezdésekre tagolt "
    "gondolatmenet — NE válts számozott alcímekre, mezőcímkékre (pl. "
    "\"Igei fókusz:\") vagy zárójeles versszám-jelölésre. "
    "Ne ismételd ugyanazt a mondatot más bekezdésben. "
    "refinement_suggestions: legfeljebb 2 hasznos szerkesztői javaslat, vagy []. "
    "Kizárólag a teljes, kiegészített JSON objektumot add vissza."
)

RAPID_EVIDENCE_SYSTEM_PROMPT = """\
Rövid, belső homiletikai háttércsomagot készítesz egy igehirdetési vázlathoz.
Nem teljes exegézis és nem prédikáció. Csak a releváns szempontok.

TILOS bizonytalan görög/héber adatot kitalálni. Ha nem biztos a nyelvi
részlet, hagyd el. Ne állítsd, hogy külső forráskutatást végeztél.

Kizárólag JSON:

{
  "central_claim": "a textus központi állítása",
  "internal_movement": "belső szerkezet és gondolati mozgás",
  "literary_context": "közvetlen irodalmi kontextus (röviden)",
  "historical_notes": "csak a megértéshez szükséges történeti háttér, vagy üres",
  "language_notes": "legfeljebb 1–2 biztos nyelvi megfigyelés, vagy üres",
  "theological_horizon": "teológiai / kánoni horizont",
  "homiletical_path": "természetes homiletikai út a hallgató felé"
}
"""

OUTLINE_SYSTEM_PROMPT = """\
SZEREP:
Te egy magas szinten képzett teológus, exegéta és tapasztalt igehirdető vagy. Feladatod egy mély, teológiailag megalapozott, mégis gyakorlatias prédikációvázlat összeállítása.

MI EZ A VÁZLAT — ÉS MI NEM:
Ez NEM kész, szó szerint felolvasható igehirdetés-szöveg, és NEM is puszta
témalista címszavakkal — hanem egy szószékre kész MUNKAANYAG, amire a
lelkész a szószéken TÁMASZKODIK, miközben saját szavaival mondja el a
prédikációt. A hézagokat
neki kell kitöltenie. Legyen elég konkrét és kifejtett ahhoz, hogy tényleges
támpontot adjon, de NE írd meg helyette a mondatokat, amiket a szószéken ki
kell mondania.

BEMENET KEZELÉSE:
1. Ha a kérés tartalmaz háttéranyagot (exegézis, kortörténet, eredeti nyelvi
   megfigyelés stb.), kizárólag ezekre a mellékelt anyagokra építve
   szervezd meg a vázlatot — ne végezz önálló nyelvi, kortörténeti vagy
   exegetikai elemzést azon a részterületen, ahol van mellékelt anyag.
   FONTOS: "erre építve" NEM azt jelenti, hogy szó szerint bemásolod a
   mellékelt anyagot — SŰRÍTSD, SZINTETIZÁLD a saját, tömör mondataiddá.
   Rossz példa (TILOS): a kortörténeti anyag egész bekezdését változtatás
   nélkül átemeled a "A Textus Világa (Kontextus)" mezőbe. Jó példa: a
   kortörténeti anyag lényegét 1-2 saját mondatban összefoglalod (pl. "A
   filippi gyülekezet tagjai büszke római polgárok voltak, ami élesen
   szembeállítja Krisztus szolgai formává válását a korabeli
   értékrenddel.").
2. HA NINCS (vagy csak részben van) HÁTTÉRANYAG megadva egy adott
   részterülethez (pl. nincs eredeti nyelvi vagy kortörténeti anyag), NE
   pótold saját tudásból, és NE találj ki új nyelvi/kortörténeti tényt.
   Ehelyett a vázlat elején, egy külön "Hiányzó háttéranyag" szakaszban
   sorold fel egyértelműen, mely részterülethez nincs elég anyag (pl.
   "Nincs eredeti nyelvi megfigyelés ehhez a szakaszhoz"). A vázlat
   többi része csak a ténylegesen mellékelt anyagra és a bibliai
   szövegre épülhet.

STÍLUS ÉS HANGVÉTEL:
- Szikár, jól áttekinthető, lényegretörő (tőmondatok és 1-2 mondatos, velős kifejtések).
- Tilos a teológiai bikkfanyelv és a sablonos, üres meta-szöveg (pl. 'A szakasz a bölcsességi irodalomba tartozik...', 'A textus mozgása...'). A hallgatóságnak szóló, életközeli nyelvezetet használj.
- SZIGORÚAN TILOS a bibliai igeszöveg — akár rövid szakaszának is — SZÓ
  SZERINTI idézése bárhol a vázlatban. Egy verstartományra csak a mondat
  természetes részeként utalhatsz (pl. "A 6–7. vers fordulópontja…"),
  SOHA nem idézőjeles szövegrészlettel.
- Ha a mellékelt anyagban (pl. vázlatkosár, illusztráció) NEVESÍTETT
  forrás szerepel — szerző, gondolkodó, teológus neve —, ŐRIZD MEG a
  nevesítést, ha ezt a gondolatot felhasználod, mondatba ágyazva (pl.
  "Anthony de Mello egyik tanítása szerint…"). NE anonimizáld
  "egy bölcs tanítás szerint" vagy hasonló, forrás nélküli formára —
  ez elveszíti a hitelességet és a visszakereshetőséget. Ha a mellékelt
  anyagban NINCS név, TE se találj ki egyet.
- Mértékkel alkalmazott **félkövér** kiemelés a bekezdésen/soron belüli
  valóban lényegi kulcsszavakra/kifejezésekre — hogy gyors rápillantással
  is tájékozódni lehessen a szószéken. NE minden mondatban, csak a
  ténylegesen fontos pontokon.
- Csak a kért forma szerinti szöveget add vissza, semmi bevezető vagy lezáró udvariaskodás!

KÖTELEZŐ FORMA — TÖMÖR, TARTALMI CÍMEKKEL TAGOLT MUNKAVÁZLAT:

# [A Prédikáció Címe] – [Igehely]

Ez után egy tapasztalt igehirdető tényleges gondolatmenete következik,
gondolat-egységenként — a hangsúly a TÖMÖRSÉGEN és a gyors
áttekinthetőségen van, NEM a szépirodalmi kifejtettségen, és NEM a régi
mezőkre/pontokra tagolt technikai struktúrán.

MOZGÁS-CÍMEK: minden gondolat-egység elé rövid, TARTALMI cím kerül,
MINDIG két elemmel együtt: (1) egyszerű sorszám a cím elején (1., 2.,
3. …, sorrendben, kihagyás nélkül), és (2) a teljes cím **félkövér**
kiemeléssel — pl. "**1. A kezdetek: két testvér, két út**" vagy "**2.
Az áldozat és az elutasítás**". A sorszám és a félkövér forma KIZÁRÓLAG
a gyors áttekinthetőséget szolgálja a szószéken — ez NEM hozza vissza a
régi, mezőkre bontott struktúrát: a cím után SOHA nem következik
"Igei fókusz:" / "Exegetikai mélység:" / "Gyakorlati alkalmazás:"
jellegű technikai almező, és a cím SOHA nem tartalmaz zárójeles
versszám-jelölést (pl. TILOS: "**1. Az áldozat (v. 6-8)**"). A cím
mindig TARTALMI (a mozgás lényegét nevezi meg), NEM üres sablon (TILOS:
"**1. Főpont**"). Ezek a címek SOSEM markdown-fejléc szintaxissal íródnak
(nincs "#"/"##"/"###" a fő cím során kívül) — önálló, félkövér szövegsorok.
FORMAI SZABÁLY: a cím saját sorban álljon, utána ÜRES SOR következzen, és
csak ez után a tartalom — soha ne írj a cím sora után közvetlenül, üres
sor nélkül folytatólagos szöveget.

GONDOLAT-EGYSÉGEK: a cím alatti tartalom NEM KELL, hogy mindig teljes,
kifejtett bekezdés legyen — rövidebb, akár tőmondat-szerű, jegyzetszerű
MONDATOK is elfogadhatók és kívánatosak, egymás után, folyó szövegként
(akár rövid bekezdésbe rendezve). A cél a tömörség: annyit írj ki,
amennyi egy lelkésznek támpontként kell, ne többet. FONTOS: ez SOHA NEM
jelent bullet-listát ("*"/"-"/"•" jelekkel tagolt felsorolást) — a
tömörség a MONDATOK rövidségéből fakadjon, nem listásításból. A
bullet-lista pontosan az a katalógusszerű, darabos hatás, amit a forma
kifejezetten kerül; a rövid mondatok egyszerűen egymás után, térköz
nélkül kövessék egymást ugyanabban a bekezdésben.

NYELVI/TÖRTÉNETI MEGFIGYELÉS: mondatba VAGY zárójelbe ágyazva jelenjen
meg — pl. "A »bűn« itt nem elvont fogalom (héb.: rōḇēṣ — lapuló,
ugrásra kész vadállat)." SOHA külön "Igei fókusz:" / "Exegetikai /
Eredeti nyelvi mélység:" / "Gyakorlati alkalmazás:" technikai mezőben.

ALKALMAZÁS: NE csak a vázlat legvégén, egyetlen záró bekezdésben
jelenjen meg — inkább FOLYAMATOSAN, a gondolatmenet több pontján is,
direkt megszólítással vagy kérdéssel a hallgató felé (pl. "Hol van ma a
te testvéred?"), a bekezdés természetes mondataként. SOHA ne vezesd be
külön "Alkalmazás:" vagy "Gyakorlati alkalmazás:" címkével — ez
ugyanolyan technikai mezőcímke, mint a többi tiltott forma, csak rövidebb
névvel. A záró gondolat-egység egy összegző, hazavezető mozdulat legyen,
de nem az egyetlen hely, ahol a hallgató megszólítást kap.

VERSTARTOMÁNY: csak a BEKEZDÉS szövegébe, mondat részeként ágyazva
fordulhat elő (pl. "A 6–7. vers fordulópontja…"), SOHA nem a cím
részeként és SOHA nem zárójeles címkeként — sem önálló sorban, sem a
cím végéhez fűzve (pl. TILOS: "(v. 6-7)", "(3-7. versek)", "**1. Az
önmegüresítés (v. 6-8)**"). A cím maga (a sorszám + félkövér tartalmi
cím) SOSEM tartalmaz versszámot.

A FORDULÓPONT-ALAPÚ EXPOZITÍV MODELL — A KANONIKUS FELISMERÉSI ÍV:

Az Igehirdetési műhelyben ez az EGYETLEN homiletikai modell (nem egy a
választható úttípusok közül). Hét egymásra épülő eleme:

1. BELÉPÉS — kérdés, kép, élethelyzet, tapasztalat vagy közvetlenül a
   textusból fakadó feszültség, amely bevonja a hallgatót: a textus
   kérdése valamilyen módon az ő kérdése is.
2. ALAPHELYZET — a textus saját kiinduló feszültsége: konfliktus, hiány,
   kérdés, paradoxon, félreértés, emberi helyzet vagy teológiai probléma.
3. ELSŐ FORDULÓPONT — felismerés, amely módosítja az addigi értelmezést
   (nem pusztán új információ: megváltozik, ahogyan a hallgató a
   helyzetet látja).
4. MÉLYÍTÉS ÉS FOKOZÁS — a kérdés összetettebbé válik, nő a tét; minden
   új mozzanat tovább viszi a gondolatmenetet (ha egy rész nem mélyíti a
   kérdést, kitérő, nem tartozik ide).
5. ÁTÉRTELMEZÉS (OPCIONÁLIS) — csak akkor, ha a jóváhagyott anyag vagy a
   textus valóban indokolja: a textus nem úgy oldja fel a kérdést,
   ahogyan ösztönösen várnánk (váratlan fordulat, paradoxon, korrekció).
   Ha nincs hozzá jóváhagyott tartalom, KIHAGYANDÓ — ne találj ki egyet.
6. MÁSODIK FORDULÓPONT — a teológiai súlypont: az addigi részletek
   mélyebb, gyakran krisztológiai/evangéliumi összefüggésben állnak
   össze; Isten cselekvése kerül az emberi teljesítmény elé.
7. MEGÉRKEZÉS — nem puszta összefoglalás: hogyan változott meg a kiinduló
   kérdés értelme, és mit jelent ez a hallgató számára (hitbeli
   felismerés, reménység, döntés vagy gyakorlati következmény — nem
   kötelező közvetlen felszólítással zárni).

Rövid alak: Belépés → Alaphelyzet → Első fordulópont → Mélyítés és fokozás
→ (opcionális Átértelmezés) → Második fordulópont → Megérkezés.

BESZÉDEGYSÉGEK SZÁMA, ÍV ÉS ÁTVEZETÉS:
A vázlat 2–4, EGYMÁSBÓL KÖVETKEZŐ beszédegységből álljon — a hét elemből
SZINTETIZÁLVA, nem hét külön címsorként kimásolva. Egy tipikus felosztás
(nem kötelező forma): 1. egység = Belépés+Alaphelyzet+Első fordulópont,
2. egység = Mélyítés és fokozás (+ Átértelmezés, ha van), 3. egység =
Második fordulópont+Megérkezés — de a tényleges egységhatárokat mindig a
textus és a jóváhagyott anyag indokolja, nem ez a séma. Csak akkor legyen
3 vagy 4 egység, ha a jóváhagyott anyag valóban külön egységet indokol —
ne erőltess pluszegységet. Minden beszédegység tartalmazza: rövid, tartalmi
címet; egy egyértelmű központi állítást (lehetőleg az egység elején); a
szükséges exegetikai-teológiai anyagot mondatba ágyazva; konkrét hallgatói
kapcsolódást; és — az utolsó egység kivételével — egy világos ÁTVEZETŐ
mondatot vagy félmondatot, amely megmutatja, HOGYAN visz tovább a
gondolatmenet a következő egységbe (ne csak "másodszor" jellegű technikai
összekötő szót használj, hanem tartalmi hidat).
TILOS a hét jóváhagyott modellelemet (belépés, alaphelyzet, első
fordulópont, mélyítés és fokozás, átértelmezés, második fordulópont,
megérkezés) egy az egyben, egymás mellé rendelt pontokként lemásolni —
ezek a FELISMERÉSI ÍV vázát adják, nem a végleges tagolást. A
beszédegységeknek érzékelhetően követniük és megőrizniük kell ezt a
jóváhagyott felismerési ívet (a belépéstől a megérkezésig, honnan hová jut
el a hallgató a textus mentén), de a tényleges egységhatárokat a textus és
a jóváhagyott anyag tartalma indokolja — ne állíts be mesterséges
fordulópontot vagy átértelmezést olyan helyen, ahol nincs hozzá jóváhagyott
tartalom.

SZIGORÚAN TILOS:
- markdown-fejléc szintaxis ("#", "##", "###") bárhol a fő cím során
  kívül,
- a régi, technikai mezőnevek bármelyike: "Igei fókusz:", "Exegetikai /
  Eredeti nyelvi mélység:", "Exegetikai mélység:", "Gyakorlati
  alkalmazás:", "Alkalmazás:", "Fókuszmondat:", "Bevezetési irány:",
  "Megérkezés:", "Bevezetés és Ráhangolódás", "Befejezés és Útravaló",
  "Élethelyzet / Probléma", "A Textus Világa (Kontextus)" — sem
  bullet-listában, sem címként,
- bullet-lista ("*"/"-"/"•" jelekkel tagolt felsorolás) BÁRHOL a gondolat-
  egységek tartalmában — a tartalom mindig folyó mondatokból áll, akár
  rövidekből is, sosem itemizált listából,
- üres sablon-cím tartalom nélkül (pl. "1. Főpont", "2. Főpont") —
  minden cím legyen SAJÁT, tartalmi cím, akár sorszámozott, akár nem,
- önálló zárójeles vagy fejléc-szerű versszám-címke (pl. "(v. 6-7)",
  "(3-7. versek)") bekezdés, sor vagy cím elején/végén,
- színpadi vagy rendezői utasítás (pl. "[Szünet]", "[Nézz körbe]",
  "[Halkabban]"),
- szó szerint előre megírt, idézőjeles retorikai beszédmondat — a vázlat
  maradjon gondolatváz, NE kész, felmondható szöveg,
- záró szótár, emlékeztető táblázat vagy összefoglaló lista az eredeti
  nyelvi szavakhoz — a nyelvi megfigyelés csak a saját gondolat-egysége
  helyén, mondatba/zárójelbe ágyazva jelenhet meg,
- puszta, elvont "kép"-leírás vagy analógia konkrét cselekmény/szereplő
  nélkül — ez az Illusztrációk modul feladata, itt csak annyi utalás
  kerülhet be, amennyi a gondolatmenethez szervesen kell.

A cím sora után a teljes válasz kb. 300–500 szó legyen — de ez a
tömörségből, nem a bőbeszédűségből fakadjon: inkább több rövid, tartalmi
sor, mint kevés, hosszan kifejtett bekezdés.
"""

_JSON_SHAPE = """\
{
  "title": "Figyelemfelkeltő, lényegre törő cím",
  "text_reference": "Igehely",
  "scope_note": "",
  "body_markdown": "Tömör, tartalmi címekkel tagolt munkavázlat — rövid, akár jegyzetszerű gondolat-egységek, NEM technikai mezőkre/üres sablonra bontva. Ld. a rendszerutasítás KÖTELEZŐ FORMA szakaszát.",
  "refinement_suggestions": []
}
"""

# Háttéranyag-kulcsok: ha bármelyik érdemi, a promptba kerül kiegészítő kontextusként.
_BACKGROUND_BUNDLE_KEYS: tuple[str, ...] = (
    # 2D.1 (adatfolyam-audit): a Bibliai áttekintés (`overview`) korábban
    # hiányzott ebből a tuple-ből, ezért `extract_outline_background_
    # material()` sosem engedte át — a bundle tartalmazta, de a motor
    # promptjáig nem jutott el. Nincs hozzá `_status` társmező (nincs
    # approval-fogalma az `overview`-nak), ezért nem kerül az
    # `_APPROVAL_GATED_KEYS` egyik csoportjába sem — ungate-elve megy át,
    # akárcsak `approved_insights`/`approved_sermon_decisions`.
    "overview",
    "exegesis",
    "exegesis_status",
    "original_text",
    "original_text_status",
    "theology",
    "theology_status",
    "history",
    "history_status",
    # Korrekciós fázis 3.1: korábban hiányzott innen — a Textusösszegzés
    # (jóváhagyva is) SOSEM jutott el a vázlatmotor promptjáig, mert ez a
    # tuple nem tartalmazta (ld. audit). Az `actualization` szintén új.
    "text_summary",
    "text_summary_status",
    "actualization",
    "actualization_status",
    "approved_sermon_decisions",
    "approved_insights",
    "sermon_main_idea",
    "sermon_main_idea_status",
    "text_main_idea",
    "text_main_idea_status",
    "human_condition",
    "human_condition_status",
    "listener_tension",
    "listener_tension_status",
    "entry_point",
    "entry_point_status",
    "christ_centered_arc",
    "christ_centered_arc_status",
    "sermon_path",
    "sermon_path_status",
    "sermon_movements",
    "closing",
    "closing_status",
    # Elemenként előre jóváhagyott lista (a szűrés a bundle-építéskor,
    # collect_outline_context_bundle-ben történik) — itt ungate-elve
    # megy át, mint approved_sermon_decisions/approved_insights.
    "engagement_elements",
    "user_notes",
    "rapid_evidence",
    "language_notes",
    "historical_notes",
)

# Ezekre a kulcsokra a MEGLÉVŐ session_state-beli draft/approved státusz
# (a "Jóváhagyom és átadom" gomb) ténylegesen kikényszerítendő — csak
# approved állapotban kerülnek a vázlatmotor promptjába.
# Korrekciós fázis 3.1 (automatikus/kanonikus forrás-hozzáférés): a korábbi
# egységes `_APPROVAL_GATED_KEYS` két, eltérő szabályú csoportra vált szét.
#
# `_HOMILETICAL_DECISION_KEYS` — igehirdetési DÖNTÉSEK (az Igehirdetési
# műhely saját szerkesztőfelületei). Ezeknél VÁLTOZATLANUL approval ÉS
# freshness szükséges — ezt a fázist ez nem érinti (a döntések jóváhagyási
# mechanizmusa külön kérdés, ld. audit 8. termékszabály).
_HOMILETICAL_DECISION_KEYS: frozenset[str] = frozenset(
    {
        "sermon_main_idea",
        "human_condition",
        "listener_tension",
        "entry_point",
        "christ_centered_arc",
        "sermon_path",
        # A mozgások ("A prédikáció íve" első látásváltás / mélyítés
        # tartalma is részben innen jön) ugyanazon a felületen, ugyanazzal
        # a gombbal kerülnek jóváhagyásra, mint a sermon_path — a
        # jóváhagyási állapotukat a bundle-építő (collect_outline_context_
        # bundle) a sermon_path-éból tükrözi, ezért itt is gate-elve vannak.
        "sermon_movements",
        "closing",
    }
)

# `_CANONICAL_TEXTUS_SOURCE_KEYS` — a Textusműhely háttérforrásai. Ezeknél
# a jóváhagyás (mezőnkénti "Jóváhagyom és átadom" kattintás) TÖBBÉ NEM
# feltétel: elég, hogy a tartalom nem üres és az AKTUÁLIS igehelyhez/
# szöveghez készült (nem "stale" — ld. `_canonical_source_is_usable`).
# Ez zárja le azt a — a kézi tesztben és az adatfolyam-auditban (ld.
# TEXTUS_IGEHIRDETESI_MUHELY_ADATFOLYAM_AUDIT.md 4. pont) dokumentált —
# helyzetet, hogy elkészült exegézis/kortörténet/teológia/eredeti szöveg a
# külön jóváhagyás elmaradása miatt láthatatlan maradt a vázlatmotor előtt.
_CANONICAL_TEXTUS_SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "text_main_idea",
        "exegesis",
        "theology",
        "history",
        "original_text",
        "text_summary",
        "actualization",
    }
)

# Visszafelé kompatibilis unió — a régi kódrészek (pl. `used_module_ids` a
# `generate_sermon_outline`-ban) ugyanazt a teljes halmazt kapják, mint
# korábban; csak a BELSŐ szűrési szabály vált szét kulcscsoportonként.
_APPROVAL_GATED_KEYS: frozenset[str] = (
    _HOMILETICAL_DECISION_KEYS | _CANONICAL_TEXTUS_SOURCE_KEYS
)

# =============================================================================
# DORMANT / FUTURE-USE — NEM AKTÍV. Célarchitektúra-terv (TEXTUS_
# EGYSZERUSITETT_IGEHIRDETESI_CELARCHITEKTURA_TERV_2026-08-13.md), 1. fázis.
#
# Ez a kulcshalmaz a leendő, egységesített `arc` adatmodellre mutat
# (ld. sermon_workshop_data.get_default_arc / _ARC_POINT_KEYS — a hét
# igehirdetési modellpont: entry, starting_point, first_shift, deepening,
# reinterpretation, second_shift, arrival).
#
# EBBEN A FÁZISBAN EZT A HALMAZT SEMMILYEN AKTÍV FÜGGVÉNY NEM HASZNÁLJA.
# A `_block_is_context_ready`, `extract_outline_background_material`,
# `_gated_fallback_bundle`, `collect_canonical_source_material`, valamint a
# `generate_sermon_outline()` VÁLTOZATLANUL, kizárólag a fenti
# `_HOMILETICAL_DECISION_KEYS` / `_CANONICAL_TEXTUS_SOURCE_KEYS` /
# `_APPROVAL_GATED_KEYS` szerint működik — ezt a jelen fázis nem módosítja.
#
# Az aktiválás (a vázlatmotor forráscsomagjának tényleges bővítése az
# `arc.*` mezőkkel) egy KÉSŐBBI, külön jóváhagyandó fázis feladata (ld. a
# tervdokumentum 10. szakasza, Fázis 3).
# =============================================================================
_FUTURE_ARC_SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "arc.entry",
        "arc.starting_point",
        "arc.first_shift",
        "arc.deepening",
        "arc.reinterpretation",
        "arc.second_shift",
        "arc.arrival",
    }
)

# Dormant, jövőbeli egységesített forráskulcs-halmaz — ma még sehol nem
# hivatkozott. Ld. a fenti figyelmeztetést: NEM váltja ki
# `_HOMILETICAL_DECISION_KEYS`-t / `_CANONICAL_TEXTUS_SOURCE_KEYS`-t.
_FUTURE_CANONICAL_SOURCE_KEYS: frozenset[str] = (
    _CANONICAL_TEXTUS_SOURCE_KEYS | frozenset({"sermon_main_idea"}) | _FUTURE_ARC_SOURCE_KEYS
)

_GATED_KEY_LABELS: dict[str, str] = {
    "sermon_main_idea": "Igehirdetés fő gondolata",
    "text_main_idea": "Textus fő gondolata",
    "human_condition": "Emberi állapot / helyzet",
    "listener_tension": "Hallgatói feszültség",
    "entry_point": "Homiletikai belépési pont",
    "christ_centered_arc": "Krisztus-központú ív",
    "sermon_path": "Igehirdetés útja",
    "sermon_movements": "Prédikációs mozgások",
    "closing": "Lezárás",
    "exegesis": "Exegézis",
    "theology": "Teológia",
    "history": "Kortörténet",
    "original_text": "Eredeti nyelvi elemzés",
    "text_summary": "Textusösszegzés",
    "actualization": "Aktualizálás",
}

_CORE_PASSAGE_KEYS: tuple[str, ...] = (
    "passage_reference",
    "passage_text",
    "project_title",
    "occasion",
    "user_focus",
    "bible_translation",
)

# Gemini responseSchema — egyetlen folyó szövegű vázlattest (body_markdown).
OUTLINE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "text_reference": {"type": "STRING"},
        "scope_note": {"type": "STRING"},
        "body_markdown": {"type": "STRING"},
        "refinement_suggestions": {
            "type": "ARRAY",
            "maxItems": 2,
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "title",
        "text_reference",
        "scope_note",
        "body_markdown",
        "refinement_suggestions",
    ],
}



def _s(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_cmp(text: str) -> str:
    return " ".join(_s(text).casefold().split())


def word_count(text: Any) -> int:
    raw = _s(text)
    if not raw:
        return 0
    return len([w for w in re.split(r"\s+", raw) if w])


def sentence_count(text: Any) -> int:
    raw = _s(text)
    if not raw:
        return 0
    # Ne tördeljen versszám/ordinal pontnál: „17–18. vers”, „3. pont”
    protected = re.sub(r"(?<=\d)\.(?=\s)", "⟪DOT⟫", raw)
    parts = [
        p.replace("⟪DOT⟫", ".").strip()
        for p in re.split(r"(?<=[.!?])\s+", protected)
        if p.strip()
    ]
    return max(1, len(parts)) if raw else 0


def _looks_truncated_sentence(text: Any) -> bool:
    """Félbemaradt mondat: nincs záró írásjel, vagy nyilvánvalóan csonka."""
    raw = _s(text)
    if not raw:
        return False
    if raw.endswith((".", "!", "?", "…", '"', "”", "'")):
        # Still flag obvious mid-clause stubs ending with period after tiny tail
        low = raw.casefold()
        if re.search(r"\b(és|vagy|hogy|mert|ha|de|majd)\s*\.$", low):
            return True
        return False
    # Ends mid-thought without terminal punctuation
    if re.search(r"\b(és|vagy|hogy|mert|ha|de|majd|két|egy)\s*$", raw.casefold()):
        return True
    if word_count(raw) >= 4 and not re.search(r"[.!?…]$", raw):
        return True
    return False


def _split_sentences(text: str) -> list[str]:
    raw = _s(text)
    if not raw:
        return []
    protected = re.sub(r"(?<=\d)\.(?=\s)", "⟪DOT⟫", raw)
    return [
        p.replace("⟪DOT⟫", ".").strip()
        for p in re.split(r"(?<=[.!?])\s+", protected)
        if p.strip()
    ]


def _clip_to_full_sentences(text: str, max_w: int) -> str:
    """Rövidít teljes mondatok mentén — soha nem vág félbe mondatot."""
    raw = _s(text)
    if not raw or word_count(raw) <= max_w:
        return raw
    sents = _split_sentences(raw)
    # Ha nincs mondatzáró, ne vágjunk szóhatáron — hagyjuk a validátorra.
    if len(sents) <= 1 and not re.search(r"[.!?…]$", raw):
        return raw
    kept: list[str] = []
    for sent in sents:
        trial = " ".join(kept + [sent]).strip()
        if kept and word_count(trial) > max_w:
            break
        kept.append(sent)
    if kept:
        return " ".join(kept).strip()
    # Első mondat önmagában túl hosszú: ne csonkítsuk szóhatáron.
    return sents[0] if sents else raw


def extract_verse_numbers(text: Any) -> set[int]:
    """Versszámok kinyerése igehely-mezőből vagy bibliai szövegből."""
    raw = _s(text)
    if not raw:
        return set()
    found: set[int] = set()
    # Ranges: 17–20 / 17-20 / 17–18
    for a, b in re.findall(r"\b(\d{1,3})\s*[–\-]\s*(\d{1,3})\b", raw):
        lo, hi = int(a), int(b)
        if 1 <= lo <= hi <= 200:
            found.update(range(lo, hi + 1))
    # Standalone verse markers near v. / vers
    for m in re.finditer(
        r"(?:(?:^|[\s(,;:])v\.?\s*|vers(?:e[ks])?\s+)(\d{1,3})\b",
        raw,
        flags=re.I | re.M,
    ):
        n = int(m.group(1))
        if 1 <= n <= 200:
            found.add(n)
    # Hungarian ordinal style: "21. vers"
    for m in re.finditer(r"\b(\d{1,3})\.\s*vers", raw, flags=re.I):
        n = int(m.group(1))
        if 1 <= n <= 200:
            found.add(n)
    # Leading verse numbers in loaded biblical text: "17 Ti pedig"
    for m in re.finditer(r"(?m)^\s*(\d{1,3})\s+\S", raw):
        n = int(m.group(1))
        if 1 <= n <= 200:
            found.add(n)
    return found


def scope_note_uses_unloaded_verse(scope_note: Any, passage_text: Any) -> bool:
    """True, ha a scope_note olyan verset említ tényként, ami nincs betöltve."""
    note = _s(scope_note)
    passage = _s(passage_text)
    if not note or not passage:
        return False
    loaded = extract_verse_numbers(passage)
    if not loaded:
        return False
    mentioned = extract_verse_numbers(note)
    if not mentioned:
        return False
    # Pure boundary suggestion (e.g. "fontolható a 21. vers bevétele") is OK
    # only if it does not assert content of the missing verse as fact.
    missing = mentioned - loaded
    if not missing:
        return False
    factual = re.search(
        r"(állít|mondja|tanítja|ígéri|parancsol|hirdeti|tartalmazza|arról beszél)",
        note.casefold(),
    )
    return bool(factual)


def _looks_multi_paragraph(text: Any) -> bool:
    raw = _s(text)
    if not raw:
        return False
    if "\n\n" in raw:
        return True
    return sentence_count(raw) >= 4 and word_count(raw) > 80


def _has_forbidden_keys(raw: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    for key in FORBIDDEN_PAYLOAD_KEYS:
        if key not in raw:
            continue
        val = raw.get(key)
        if val in (None, "", [], {}):
            continue
        if key == "content" and isinstance(val, str) and word_count(val) <= 5:
            continue
        found.append(key)
    for pt in raw.get("points") or raw.get("movements") or []:
        if not isinstance(pt, dict):
            continue
        for key in FORBIDDEN_PAYLOAD_KEYS:
            if key in pt and _s(pt.get(key)):
                if key in {
                    "body",
                    "content",
                    "exegesis",
                    "theological_expansion",
                    "grace_connection",
                    "listener_connection",
                    "transition_logic",
                    "thesis",
                }:
                    found.append(f"point.{key}")
    return list(dict.fromkeys(found))


def empty_structured_outline() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "title": "",
        "text_reference": "",
        "scope_note": "",
        # ÚJ (2026-08-07): egyetlen folyó szövegű vázlattest — ez a
        # kanonikus generálási cél. A `focus_sentence`/`introduction_direction`/
        # `movements`/`points`/`conclusion_direction` mezők csak a korábban
        # (a formai átalakítás előtt) mentett vázlatok visszafelé-kompatibilis
        # megjelenítésére maradtak meg — új generálás sosem tölti ki őket.
        "body_markdown": "",
        "focus_sentence": "",
        "introduction_direction": "",
        "movements": [],
        "points": [],
        "conclusion_direction": "",
        "refinement_suggestions": [],
    }


def _point_layer_words(pt: Mapping[str, Any]) -> int:
    return sum(word_count(pt.get(k)) for k in POINT_LAYER_KEYS)


def _migrate_point_layers(item: Mapping[str, Any]) -> dict[str, str]:
    """v5 subpoints/application vagy legacy development → három réteg."""
    textual = _s(item.get("textual_insight"))
    theological = _s(item.get("theological_emphasis"))
    listener = _s(item.get("listener_movement"))

    legacy_parts: list[str] = []
    legacy_thesis = _s(
        item.get("thesis") or item.get("core_content") or item.get("body")
    )
    if legacy_thesis:
        legacy_parts.append(legacy_thesis)
    subs_raw = item.get("subpoints")
    if not isinstance(subs_raw, list) or not subs_raw:
        development = item.get("development")
        subs_raw = development if isinstance(development, list) else []
    for x in subs_raw:
        part = _s(x)
        if part and all(_normalize_cmp(part) != _normalize_cmp(p) for p in legacy_parts):
            legacy_parts.append(part)

    application = _s(item.get("application"))
    if not application:
        application = _s(item.get("listener_insight")) or _s(
            item.get("listener_discovery")
        )
    if not application:
        apps = item.get("applications") if isinstance(item.get("applications"), list) else []
        application = _s(apps[0]) if apps else ""

    if not textual and legacy_parts:
        textual = legacy_parts[0]
    if not theological and len(legacy_parts) > 1:
        theological = legacy_parts[1]
    if not listener:
        # Prefer a full third development sentence over a short legacy application.
        if len(legacy_parts) > 2:
            listener = legacy_parts[2]
        elif application:
            listener = application
    elif (
        application
        and word_count(listener) < LIMITS["layer_min_words"]
        and len(legacy_parts) > 2
        and word_count(legacy_parts[2]) >= LIMITS["layer_min_words"]
    ):
        listener = legacy_parts[2]

    if textual and (not theological or not listener):
        sents = _split_sentences(textual)
        if len(sents) >= 3 and not theological and not listener:
            textual, theological, listener = sents[0], sents[1], sents[2]
        elif len(sents) == 2 and not theological:
            textual, theological = sents[0], sents[1]

    return {
        "textual_insight": textual,
        "theological_emphasis": theological,
        "listener_movement": listener,
    }


def normalize_structured_outline(raw: Any) -> dict[str, Any]:
    """AI / legacy payload → kanonikus háromrétegű struktúra."""
    base = empty_structured_outline()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    out["title"] = _s(raw.get("title") or raw.get("sermon_title"))
    out["text_reference"] = _s(
        raw.get("text_reference") or raw.get("passage_reference")
    )
    out["scope_note"] = _s(raw.get("scope_note") or raw.get("text_boundary_note"))
    out["body_markdown"] = _s(raw.get("body_markdown"))
    out["focus_sentence"] = _s(raw.get("focus_sentence") or raw.get("main_idea"))
    intro_raw = raw.get("introduction")
    intro = intro_raw if isinstance(intro_raw, dict) else {}
    out["introduction_direction"] = _s(
        raw.get("introduction_direction")
        or intro.get("development")
        or raw.get("opening_direction")
    )
    conc_raw = raw.get("conclusion")
    closing_raw = raw.get("closing")
    conc = conc_raw if isinstance(conc_raw, dict) else {}
    closing = closing_raw if isinstance(closing_raw, dict) else {}
    out["conclusion_direction"] = _s(
        raw.get("conclusion_direction")
        or conc.get("development")
        or closing.get("final_insight")
    )
    tips = raw.get("refinement_suggestions") or raw.get("editorial_tips") or []
    cleaned_tips: list[str] = []
    for t in tips if isinstance(tips, list) else []:
        tip = _s(t)
        if not tip:
            continue
        low = tip.casefold()
        if any(
            w in low
            for w in ("hiányzik", "kötelező", "nem töltött", "üres mező", "műhelymez")
        ):
            continue
        cleaned_tips.append(tip)
    out["refinement_suggestions"] = cleaned_tips[: LIMITS["refinement_max"]]

    movements: list[dict[str, Any]] = []
    raw_movements = raw.get("movements")
    if not isinstance(raw_movements, list) or not raw_movements:
        points_raw = raw.get("points")
        raw_movements = points_raw if isinstance(points_raw, list) else []
    assert isinstance(raw_movements, list)
    for i, item in enumerate(raw_movements[: LIMITS["max_points"]], start=1):
        if not isinstance(item, dict):
            continue
        title = re.sub(r"^\s*\d+[.)]\s*", "", _s(item.get("title"))).strip()
        verses = _s(
            item.get("verses")
            or item.get("textual_anchor")
            or item.get("textual_basis")
        )
        layers = _migrate_point_layers(item)
        if not title and not any(layers.values()):
            continue
        transition = _s(item.get("transition"))
        if word_count(transition) > LIMITS["transition_words"]:
            transition = _clip_to_full_sentences(transition, LIMITS["transition_words"])
        movements.append(
            {
                "title": title or f"{i}. mozgás",
                "verses": verses,
                "transition": transition,
                **layers,
            }
        )
    # Kanonikus: movements. points alias a meglévő belső hívásokhoz / tesztekhez.
    out["movements"] = movements
    out["points"] = movements
    out["schema_version"] = SCHEMA_VERSION
    out["engine_version"] = ENGINE_VERSION
    return out


_WORD_RE = re.compile(r"[\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ]+")


def _normalize_words(text: Any) -> list[str]:
    return _WORD_RE.findall(_s(text).casefold())


def _has_verbatim_overlap(
    candidate: Any, sources: list[str] | None, *, min_words: int = 8
) -> bool:
    """True, ha `candidate` legalább `min_words` egymást követő szava szó
    szerint (normalizálva) megtalálható valamelyik `sources` szövegben —
    azaz a modell nem szintetizált, hanem szó szerint átvette a forrást."""
    if not sources:
        return False
    cand_words = _normalize_words(candidate)
    if len(cand_words) < min_words:
        return False
    normalized_sources = [
        " ".join(_normalize_words(src)) for src in sources if _s(src)
    ]
    normalized_sources = [s for s in normalized_sources if s]
    if not normalized_sources:
        return False
    for i in range(len(cand_words) - min_words + 1):
        shingle = " ".join(cand_words[i : i + min_words])
        for src_joined in normalized_sources:
            if shingle in src_joined:
                return True
    return False


def validate_structured_outline(
    payload: Any,
    *,
    passage_text: Any = "",
    background_texts: list[str] | None = None,
) -> list[str]:
    """Hard validation — bármely találat → érvénytelen (compress / reject).

    2026-08-07 óta a kanonikus forma egyetlen folyó szövegű vázlattest
    (`body_markdown`) — az ellenőrzés ezért egész-szöveges, nem mezőnkénti/
    pontonkénti. A korábbi, mezőkre/pontokra bontott ág csak a formai
    átalakítás előtt mentett vázlatok visszafelé-kompatibilis
    (defenzív) ellenőrzésére maradt meg — ÚJ AI-generálás sosem ide fut."""
    data = normalize_structured_outline(payload)
    issues: list[str] = []
    overlap_sources = [_s(passage_text)] + list(background_texts or [])

    if isinstance(payload, dict):
        forbidden = _has_forbidden_keys(payload)
        if forbidden:
            issues.append("forbidden_prose_fields")
        raw_tips = payload.get("refinement_suggestions")
        if isinstance(raw_tips, list) and len(raw_tips) > LIMITS["refinement_max"]:
            issues.append("too_many_refinements")

    if data["title"] and word_count(data["title"]) > LIMITS["title_words"]:
        issues.append("title_too_long")
    if data["scope_note"] and word_count(data["scope_note"]) > LIMITS["scope_note_words"]:
        issues.append("scope_note_too_long")
    if passage_text and scope_note_uses_unloaded_verse(
        data["scope_note"], passage_text
    ):
        issues.append("scope_note_unloaded_verse")

    body = data["body_markdown"]
    if body:
        if _has_forbidden_outline_structure(body):
            issues.append("forbidden_structure")
        if _looks_truncated_sentence(body):
            issues.append("truncated_sentence")
        if _has_verbatim_overlap(body, overlap_sources, min_words=10):
            issues.append("verbatim_source_copy")
        blob = body.casefold()
        for filler in FORBIDDEN_FILLERS:
            if filler in blob:
                issues.append("forbidden_filler")
                break
        wc = word_count(body)
        if wc > LIMITS["absolute_max_words"]:
            issues.append("over_absolute_max")
        elif wc and wc < LIMITS["soft_floor_words"]:
            issues.append("too_thin")
        elif wc and wc < LIMITS["target_min_words"]:
            issues.append("under_target")
        para_count = len([p for p in body.split("\n\n") if len(p) > 120])
        if para_count >= 8 and wc > LIMITS["absolute_max_words"]:
            issues.append("full_sermon_like")
        # 2C.1: szerkezeti koherencia-proxy — a beszédegységek száma és
        # megkülönböztethetősége, NEM a felismerési ív szemantikai
        # ellenőrzése (ld. _assess_outline_structure docstringje).
        issues.extend(_assess_outline_structure(_extract_markdown_movements(body)))
        return list(dict.fromkeys(issues))

    if not data["points"] and not data["focus_sentence"]:
        issues.append("missing_body")
        return list(dict.fromkeys(issues))

    # ---- Visszafelé-kompatibilitás: a 2026-08-07 előtti, mezőkre/pontokra
    # bontott séma ellenőrzése. ÚJ generálás sosem ide fut — csak a
    # formai átalakítás előtt mentett vázlatok esetleges újra-validálására. ----
    if not data["focus_sentence"]:
        issues.append("missing_focus")
    else:
        fw = word_count(data["focus_sentence"])
        if fw > LIMITS["focus_words"]:
            issues.append("focus_too_long")
        if fw and fw < LIMITS["focus_min_words"]:
            issues.append("focus_too_short")
        if sentence_count(data["focus_sentence"]) != 1:
            issues.append("focus_not_one_sentence")
        if _looks_truncated_sentence(data["focus_sentence"]):
            issues.append("truncated_sentence")
        if _has_verbatim_overlap(data["focus_sentence"], overlap_sources):
            issues.append("verbatim_source_copy")

    intro = data["introduction_direction"]
    if not intro:
        issues.append("missing_intro")
    else:
        iw = word_count(intro)
        if iw > LIMITS["intro_words"]:
            issues.append("intro_too_long")
        if iw and iw < LIMITS["intro_min_words"]:
            issues.append("intro_too_short")
        if sentence_count(intro) > LIMITS["intro_sentences_max"]:
            issues.append("intro_too_many_sentences")
        if _looks_multi_paragraph(intro):
            issues.append("intro_multi_paragraph")
        if _looks_truncated_sentence(intro):
            issues.append("truncated_sentence")
        if _has_verbatim_overlap(intro, overlap_sources):
            issues.append("verbatim_source_copy")

    points = data["points"]
    n = len(points)
    if n < LIMITS["min_points"]:
        issues.append("too_few_points")
    if n > LIMITS["max_points"]:
        issues.append("too_many_points")

    titles_seen: set[str] = set()
    verse_sets: list[frozenset[int]] = []
    verse_labels: list[str] = []
    for pt in points:
        title = _s(pt.get("title"))
        verses = _s(pt.get("verses"))
        textual = _s(pt.get("textual_insight"))
        theological = _s(pt.get("theological_emphasis"))
        listener = _s(pt.get("listener_movement"))
        tnorm = _normalize_cmp(title)
        if not title:
            issues.append("empty_point_title")
        elif word_count(title) > LIMITS["point_title_words"]:
            issues.append("point_title_too_long")
        if any(_normalize_cmp(title) == _normalize_cmp(h) for h in FORBIDDEN_HEADINGS):
            issues.append("forbidden_heading")
        if re.search(r"\(\s*v\.?\s*\d", title.casefold()) or re.search(
            r"\bv\.?\s*\d{1,3}\s*[–\-]\s*\d", title.casefold()
        ):
            issues.append("verse_in_point_title")
        if tnorm in titles_seen:
            issues.append("duplicate_points")
        titles_seen.add(tnorm)
        for prev in titles_seen - {tnorm}:
            if prev and tnorm and (prev in tnorm or tnorm in prev):
                if abs(len(prev) - len(tnorm)) <= 8:
                    issues.append("duplicate_points")
        vset = frozenset(extract_verse_numbers(verses))
        verse_sets.append(vset)
        verse_labels.append(_normalize_cmp(verses))

        if not textual:
            issues.append("missing_textual_insight")
        if not theological:
            issues.append("missing_theological_emphasis")
        if not listener:
            issues.append("missing_listener_movement")

        for key, val in (
            ("textual_insight", textual),
            ("theological_emphasis", theological),
            ("listener_movement", listener),
        ):
            if not val:
                continue
            wc = word_count(val)
            if wc < LIMITS["layer_min_words"]:
                issues.append("stub_layer")
            if wc > LIMITS["layer_max_words"]:
                issues.append("layer_too_long")
            sc = sentence_count(val)
            if sc < 1 or sc > LIMITS["layer_sentences"]:
                issues.append("layer_sentence_count")
            # Ismételt réteg / közhely
            if key != "textual_insight" and textual and _normalize_cmp(val) == _normalize_cmp(
                textual
            ):
                issues.append("repeated_layer_text")
            generic_bits = (
                "a textus isten megtartó szavát",
                "a textus saját mozgása tovább pontosítja",
                "hitbeli felismerésre és válaszra hívja",
            )
            if any(g in val.casefold() for g in generic_bits):
                issues.append("generic_filler")
            template_titles = (
                "a textus megnyitása",
                "a központi állítás",
                "a kegyelmi megérkezés",
            )
            if tnorm in template_titles:
                issues.append("generic_filler")
            if _looks_multi_paragraph(val):
                issues.append("multi_paragraph_point")
            if _looks_truncated_sentence(val):
                issues.append("truncated_sentence")
            if wc > LIMITS["max_prose_block_words"]:
                issues.append("prose_block_too_long")
            if _has_verbatim_overlap(val, overlap_sources):
                issues.append("verbatim_source_copy")

        layer_total = _point_layer_words(pt)
        if layer_total and layer_total < LIMITS["point_layers_min_words"]:
            issues.append("point_layers_too_short")
        if layer_total > LIMITS["point_layers_max_words"]:
            issues.append("point_layers_too_long")

    for i in range(1, len(verse_labels)):
        a, b = verse_labels[i - 1], verse_labels[i]
        if a and b and a == b:
            issues.append("split_same_verse")

    loaded_verses = extract_verse_numbers(passage_text) if passage_text else set()
    covered: set[int] = set()
    for vs in verse_sets:
        covered |= set(vs)
    if loaded_verses and covered:
        for v in sorted(loaded_verses):
            if v in covered:
                continue
            if (v - 1) in covered and (v + 1) in covered:
                issues.append("missing_verse_unit")
                break

    point_blobs = [
        " ".join(
            [
                _s(pt.get("title")),
                _s(pt.get("textual_insight")),
                _s(pt.get("theological_emphasis")),
                _s(pt.get("listener_movement")),
            ]
        ).casefold()
        for pt in points
    ]
    triad = ("hordoz", "megtart", "megment")
    triad_hits = sum(1 for blob in point_blobs if sum(1 for t in triad if t in blob) >= 2)
    if triad_hits >= 3:
        issues.append("repeated_thematic_triad")

    conc = data["conclusion_direction"]
    if not conc:
        issues.append("missing_conclusion")
    else:
        cw = word_count(conc)
        if cw > LIMITS["conclusion_words"]:
            issues.append("conclusion_too_long")
        if cw and cw < LIMITS["conclusion_min_words"]:
            issues.append("conclusion_too_short")
        if sentence_count(conc) > LIMITS["conclusion_sentences_max"]:
            issues.append("conclusion_too_many_sentences")
        if _looks_multi_paragraph(conc):
            issues.append("conclusion_multi_paragraph")
        if _looks_truncated_sentence(conc):
            issues.append("truncated_sentence")
        if _has_verbatim_overlap(conc, overlap_sources):
            issues.append("verbatim_source_copy")

    rendered = render_structured_outline(data)
    total = word_count(rendered)
    if total > LIMITS["absolute_max_words"]:
        issues.append("over_absolute_max")
    if n <= 2:
        tmin = LIMITS["target_min_2"]
    elif n >= 5:
        tmin = LIMITS["target_min_5"]
    else:
        tmin = LIMITS["target_min_3_4"]
    if total and total < LIMITS["soft_floor_words"]:
        issues.append("too_thin")
    elif total and total < tmin:
        issues.append("under_target")

    blob = rendered.casefold()
    for heading in FORBIDDEN_HEADINGS:
        h = re.escape(heading.casefold())
        if re.search(
            rf"(?m)^(?:\*\*|#{1,3}\s*)?{h}\**\s*$",
            blob,
        ) or re.search(rf"\*\*{h}\*\*", blob):
            issues.append("forbidden_heading")
            break
    for filler in FORBIDDEN_FILLERS:
        if filler in blob:
            issues.append("forbidden_filler")
            break

    para_count = len([p for p in rendered.split("\n\n") if len(p) > 120])
    if para_count >= 8 and total > LIMITS["absolute_max_words"]:
        issues.append("full_sermon_like")

    return list(dict.fromkeys(issues))


def _strip_trailing_verse_from_title(title: str) -> str:
    # A [a-c]? résznél a betűs részvers-jelölést is elfogadjuk (pl. "6a",
    # "7b–8") — enélkül egy ilyen alakú hivatkozás nem illeszkedett, és
    # csonkán a címben maradt.
    cleaned = re.sub(r"^\s*\d+[.)]\s*", "", _s(title)).strip()
    cleaned = re.sub(
        r"\s*\(\s*v\.?\s*\d{1,3}[a-c]?(?:\s*[–\-]\s*\d{1,3}[a-c]?)?\s*\)\s*$",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    cleaned = re.sub(
        r"\s+v\.?\s*\d{1,3}[a-c]?(?:\s*[–\-]\s*\d{1,3}[a-c]?)?\s*$",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    return cleaned


def render_structured_outline(payload: Any) -> str:
    """Felhasználói megjelenés — egyetlen folyó szövegű vázlattest.

    Ha van `body_markdown` (2026-08-07 óta a kanonikus generálási cél),
    azt adja vissza cím + (opcionális) textushatár-megjegyzés után,
    tagolás/mezőcímke nélkül. A régi, mezőkre/pontokra bontott render
    csak a korábban mentett vázlatok visszafelé-kompatibilis
    megjelenítésére szolgál — új generálás sosem ide fut."""
    data = normalize_structured_outline(payload)

    if data["body_markdown"]:
        parts: list[str] = []
        heading = data["title"]
        if data["text_reference"]:
            heading = f"{heading} – {data['text_reference']}" if heading else data["text_reference"]
        if heading:
            parts.append(f"# {heading}")
        if data["scope_note"]:
            parts.append(f"*{data['scope_note']}*")
        parts.append(data["body_markdown"])
        return "\n\n".join(p for p in parts if p).strip() + "\n"

    blocks: list[str] = []

    def _sec(label: str, body: str) -> None:
        text = _s(body)
        if text:
            blocks.append(f"**{label}**\n\n{text}")

    _sec("Cím", data["title"])
    _sec("Textus", data["text_reference"])
    if data["scope_note"]:
        _sec("Megjegyzés a textushatárról", data["scope_note"])
    _sec("Fókuszmondat", data["focus_sentence"])
    _sec("Bevezetési irány", data["introduction_direction"])

    for idx, pt in enumerate(data["points"], start=1):
        title = _strip_trailing_verse_from_title(_s(pt.get("title")))
        if not title:
            continue
        verses = _s(pt.get("verses"))
        heading = f"{idx}. {title}"
        if verses:
            heading = f"{heading} ({verses})"
        textual = _s(pt.get("textual_insight"))
        theological = _s(pt.get("theological_emphasis"))
        listener = _s(pt.get("listener_movement"))
        parts: list[str] = []
        if textual:
            # Textuális felismerés: tipográfiailag hangsúlyos
            parts.append(f"**{textual}**")
        if theological:
            parts.append(theological)
        if listener:
            parts.append(f"*{listener}*")
        transition = _s(pt.get("transition"))
        if transition:
            parts.append(transition)
        if not parts:
            continue
        blocks.append(f"**{heading}**\n\n" + "\n\n".join(parts))

    _sec("Megérkezés", data["conclusion_direction"])
    # Finomítási javaslatok: editorial_tips mezőben + UI expanderben —
    # ne kerüljenek a kanonikus szószéki szövegtestbe.
    text = "\n\n".join(blocks).strip()
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    return text + ("\n" if text else "")


def structured_to_sermon_outline(
    payload: Any,
    *,
    seed: Mapping[str, Any] | None = None,
    source: str = "",
    context_hash: str = "",
) -> dict[str, Any]:
    """Struktúra → tartós sermon_outline."""
    data = normalize_structured_outline(payload)
    outline = normalize_sermon_outline(seed) if seed else empty_sermon_outline()
    stamp = _now()

    # Preserve prior long freeform as migration data — never as primary content
    prior_content = _s(outline.get("content"))
    prior_legacy = _s(outline.get("legacy_outline_text"))
    structured_preview = render_structured_outline(data)
    if prior_content and word_count(prior_content) > LIMITS["absolute_max_words"]:
        if _normalize_cmp(prior_content) != _normalize_cmp(structured_preview):
            prior_legacy = prior_legacy or prior_content
    if prior_legacy:
        outline["legacy_outline_text"] = prior_legacy

    outline["sermon_title"] = data["title"]
    outline["passage_reference"] = data["text_reference"] or _s(
        outline.get("passage_reference")
    )
    outline["text_boundary_note"] = data["scope_note"]
    outline["main_idea"] = data["focus_sentence"]
    outline["opening_direction"] = data["introduction_direction"]
    outline["introduction"] = {
        "development": data["introduction_direction"],
        "transition": "",
    }
    outline["conclusion"] = {
        "development": data["conclusion_direction"],
        "final_sentence": "",
    }
    closing = dict(outline.get("closing") or {})
    closing["final_insight"] = data["conclusion_direction"]
    outline["closing"] = closing
    outline["editorial_tips"] = list(data["refinement_suggestions"][:2])
    try:
        from sermon_workshop_outline_synth_ai import suggest_text_boundary_hint

        if not data["scope_note"]:
            hint = suggest_text_boundary_hint(
                data["text_reference"] or outline.get("passage_reference"),
                "",
            )
            if hint.get("text_boundary_note"):
                data["scope_note"] = hint["text_boundary_note"]
                outline["text_boundary_note"] = hint["text_boundary_note"]
                outline["suggested_text_boundary"] = hint.get(
                    "suggested_text_boundary", ""
                )
        elif "Júd 17–21" in data["scope_note"] or "Júd 17-21" in data["scope_note"]:
            outline["suggested_text_boundary"] = "Júd 17–21"
    except Exception:  # noqa: BLE001
        pass
    outline["text_boundary_note"] = data["scope_note"] or outline.get(
        "text_boundary_note", ""
    )

    movements: list[dict[str, Any]] = []
    for i, pt in enumerate(data["points"], start=1):
        item = empty_outline_movement()
        textual = _s(pt.get("textual_insight"))
        theological = _s(pt.get("theological_emphasis"))
        listener = _s(pt.get("listener_movement"))
        verses = _s(pt.get("verses"))
        development = [x for x in (textual, theological, listener) if x]
        item.update(
            {
                "id": f"pt_{i}",
                "title": _s(pt.get("title")),
                "textual_basis": verses,
                "textual_anchor": verses,
                "core_content": textual,
                "development": development,
                "listener_discovery": listener,
                "applications": [listener] if listener else [],
                "transition": "",
            }
        )
        movements.append(item)
    outline["movements"] = movements
    outline["structured"] = data
    outline["content"] = structured_preview
    outline["schema_version"] = SCHEMA_VERSION
    outline["source"] = source if source in ("quick", "workshop") else _s(
        outline.get("source")
    )
    outline["context_hash"] = context_hash or _s(outline.get("context_hash"))
    if not outline.get("generated_at"):
        outline["generated_at"] = stamp
    outline["updated_at"] = stamp
    # Új generálás mindig draft (régi needs_refresh seed ne ragadjon rá).
    outline["status"] = "draft"
    outline["needs_rebuild"] = False
    outline["provisional_sections"] = []
    return normalize_sermon_outline(outline)


def sermon_outline_to_structured(outline: Any) -> dict[str, Any]:
    safe = normalize_sermon_outline(outline)
    stored = safe.get("structured")
    if isinstance(stored, dict) and (
        stored.get("body_markdown") or stored.get("points") or stored.get("focus_sentence")
    ):
        return normalize_structured_outline(stored)
    return normalize_structured_outline(safe)


def compute_context_hash(bundle: Mapping[str, Any]) -> str:
    """Forrásanyag ujjlenyomat — változás → needs_refresh, nem auto-duplikátum."""
    keys = (
        "passage_reference",
        "passage_text",
        "text_main_idea",
        "sermon_main_idea",
        "exegesis",
        "original_text",
        "theology",
        "history",
        "approved_insights",
        "approved_sermon_decisions",
        "human_condition",
        "listener_tension",
        "christ_centered_arc",
        "sermon_path",
        "sermon_movements",
        "closing",
        "occasion",
        "user_focus",
    )
    payload = {k: bundle.get(k) for k in keys if bundle.get(k) not in (None, "", [], {})}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def compute_passage_context_hash(bundle: Mapping[str, Any]) -> str:
    """Szűk igehely-ujjlenyomat: KIZÁRÓLAG igehely + fordítás + bibliai
    szöveg alapján (ld. adatsema_v1.md 5. pont) — nem tartalmaz gated
    tartalmat, ezért alkalmas egyedi blokkok STALE-ellenőrzésére anélkül,
    hogy egy jóváhagyás vagy egy másik blokk szerkesztése önmagát vagy
    más, változatlan blokkokat hamisan elavulttá tenne."""
    payload = {
        "passage_reference": _s(bundle.get("passage_reference")),
        "bible_translation": _s(bundle.get("bible_translation")),
        "passage_text": _s(bundle.get("passage_text")),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def compute_current_passage_context_hash(session_state: Mapping[str, Any]) -> str:
    """Kényelmi függvény: az aktuális session_state-ből azonnal kiszámítja
    a szűk igehely-ujjlenyomatot — ezt hívja a "Jóváhagyom és átadom" gomb
    jóváhagyáskor, hogy elmentse `<blokk>_approved_context_hash`-ként."""
    from sermon_workshop_outline_ai import collect_available_sermon_material

    bundle = collect_available_sermon_material(session_state)
    return compute_passage_context_hash(bundle)


def collect_outline_evidence(
    session_state: Mapping[str, Any],
    *,
    sermon_workshop: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Központi evidence csomag — wrapper a meglévő material collectorre."""
    from sermon_workshop_outline_ai import collect_available_sermon_material

    bundle = collect_available_sermon_material(
        session_state, sermon_workshop=sermon_workshop
    )
    # Ne küldjük vissza a régi generált vázlatot mint követendő mintát.
    bundle.pop("sermon_outline", None)
    bundle.pop("outline_manual_notes", None)
    return bundle


def ensure_passage_text_for_outline(
    session_state: MutableMapping[str, Any],
) -> tuple[bool, str]:
    """Igehely + szöveg biztosítása; hiányzó szövegnél RÚF-betöltési kísérlet.

    Returns: (ok, message).
    """
    ref = _s(
        session_state.get("last_igehely")
        or session_state.get("igehely_input")
        or session_state.get("passage_reference")
    )
    if not ref:
        # Widget élő értéke
        ref = _s(session_state.get("igehely_input"))
    if ref and not _s(session_state.get("last_igehely")):
        session_state["last_igehely"] = ref

    text = _s(session_state.get("passage_text"))
    if not text:
        text = _s(session_state.get("passage_text_input"))
        if text:
            session_state["passage_text"] = text

    if ref and text:
        return True, ""
    if not ref:
        return False, (
            "Add meg az igehelyet, majd tölts be RÚF-szöveget "
            "(vagy engedd, hogy a rendszer betöltse)."
        )
    # Van igehely, nincs szöveg → RÚF
    try:
        from ruf_bible_service import fetch_ruf_passage
    except Exception as exc:  # pragma: no cover
        logger.info("ruf_import_failed err=%s", type(exc).__name__)
        return False, (
            "Az igehely megvan, de a bibliai szöveg hiányzik, "
            "és a RÚF-betöltő nem érhető el."
        )
    try:
        result = fetch_ruf_passage(ref)
    except Exception as exc:  # pragma: no cover
        logger.info("ruf_fetch_failed err=%s", type(exc).__name__)
        return False, (
            "Az igehely megvan, de a bibliai szöveg automatikus betöltése nem sikerült. "
            "Illeszd be kézzel a RÚF szöveget."
        )
    if not result.get("success"):
        return False, (
            "Az igehely megvan, de a RÚF-szöveg nem volt betölthető. "
            "Illeszd be kézzel a bibliai szöveget."
        )
    loaded = _s(result.get("text") or result.get("passage_text"))
    if not loaded:
        return False, (
            "Az igehely megvan, de a RÚF-válasz üres volt. "
            "Illeszd be kézzel a bibliai szöveget."
        )
    session_state["passage_text"] = loaded
    session_state["passage_text_input"] = loaded
    if result.get("reference"):
        session_state["last_igehely"] = _s(result.get("reference")) or ref
    session_state["bible_translation"] = _s(
        result.get("translation") or "RÚF 2014"
    ) or "RÚF 2014"
    return True, ""


def _background_value_is_usable(value: Any) -> bool:
    """True, ha a háttérmező nem üres / None / csak hiányjelző."""
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        markers = (
            "nincs kidolgozva",
            "nincs adat",
            "hiányzik",
            "placeholder",
            "n/a",
            "—",
            "-",
        )
        return text.casefold() not in markers
    if isinstance(value, Mapping):
        return any(_background_value_is_usable(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_background_value_is_usable(v) for v in value)
    return bool(value)


def _block_is_stale(bundle: Mapping[str, Any], base_key: str) -> bool:
    """True, ha a blokk approved, DE a jóváhagyáskor elmentett
    `<kulcs>_approved_context_hash` eltér az aktuális igehely/szöveg
    ujjlenyomatától. Ha nincs mentett hash (pl. a mechanizmus bevezetése
    előtti jóváhagyás), NEM tekintjük STALE-nek — visszafelé-kompatibilitás."""
    if _s(bundle.get(f"{base_key}_status")) != "approved":
        return False
    approved_hash = _s(bundle.get(f"{base_key}_approved_context_hash"))
    if not approved_hash:
        return False
    return approved_hash != compute_passage_context_hash(bundle)


def _block_is_approved_and_fresh(bundle: Mapping[str, Any], base_key: str) -> bool:
    """True, ha a blokk approved ÉS (nincs mentett hash VAGY a mentett hash
    megegyezik az aktuálissal) — azaz ténylegesen felhasználható.

    Kizárólag `_HOMILETICAL_DECISION_KEYS` tagjaira érvényes szabály."""
    if _s(bundle.get(f"{base_key}_status")) != "approved":
        return False
    return not _block_is_stale(bundle, base_key)


def _canonical_source_is_stale(bundle: Mapping[str, Any], base_key: str) -> bool:
    """True, ha a Textusműhely-forráshoz mentett igehely/szöveg-ujjlenyomat
    ELTÉR az aktuálistól — azaz a tartalom más textushoz készült.

    Jóváhagyási státusztól FÜGGETLEN ellenőrzés (Korrekciós fázis 3.1) — a
    hash-t a tartalom GENERÁLÁSAKOR/MENTÉSEKOR bélyegzi be a hívó (ld.
    `app.py::render_section_tab`, `textus_workshop_data.update_text_main_idea`
    / `update_text_summary_fields`), nem csak jóváhagyáskor. Ha nincs mentett
    ujjlenyomat (pl. régi projekt, a mechanizmus bevezetése előtti mentés),
    NEM tekintjük stale-nek — visszafelé-kompatibilitás."""
    saved_hash = _s(bundle.get(f"{base_key}_approved_context_hash"))
    if not saved_hash:
        return False
    return saved_hash != compute_passage_context_hash(bundle)


def _canonical_source_is_usable(bundle: Mapping[str, Any], base_key: str) -> bool:
    """True, ha a Textusműhely-forrás felhasználható a vázlatmotor
    kontextusában: van tartalma (a hívó ellenőrzi) és nem stale — a
    jóváhagyási állapot NEM feltétel."""
    return not _canonical_source_is_stale(bundle, base_key)


def _block_is_context_ready(bundle: Mapping[str, Any], base_key: str) -> bool:
    """Egyetlen belépési pont mindkét kulcscsoport felhasználhatóság-
    ellenőrzéséhez — ezt hívja mind a normál (AI) út
    (`extract_outline_background_material`), mind a fallback út
    (`_gated_fallback_bundle`), így a kettő garantáltan ugyanazt látja."""
    if base_key in _HOMILETICAL_DECISION_KEYS:
        return _block_is_approved_and_fresh(bundle, base_key)
    if base_key in _CANONICAL_TEXTUS_SOURCE_KEYS:
        return _canonical_source_is_usable(bundle, base_key)
    return True


def collect_canonical_source_material(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Egyetlen kanonikus forrásgyűjtő a Textusműhely háttérforrásaihoz
    (Korrekciós fázis 3.1 — TEXTUS_IGEHIRDETESI_MUHELY_ADATFOLYAM_AUDIT.md).

    A már összeállított `bundle`-ből (ld. `collect_outline_context_bundle`)
    strukturáltan adja vissza:
      - `passage`: igehely, bibliai szöveg, fordítás;
      - `sources`: a `_CANONICAL_TEXTUS_SOURCE_KEYS` közül azok, amiknek van
        tartalmuk — mindegyikhez `content`, `origin` ("textusműhely"),
        `editable_by_user` (mindig True — a felhasználó bármikor felülírhatja)
        és `current_passage` (a friss/stale ellenőrzés eredménye, ld.
        `_canonical_source_is_usable`);
      - `user_notes`: mindig üres lista (RESET 1A-DATA, 2026-08-18 — a
        korábbi vázlatkosár-jegyzetek forrása leválasztva, ld. lentebb);
      - `identity`: az aktuális igehely-ujjlenyomat, a stale-ellenőrzés alapja.

    Ezt a struktúrát ma az `extract_outline_background_material` (normál
    AI-út) és a `_gated_fallback_bundle` (heurisztikus fallback-út) is a
    `_block_is_context_ready` dispatcheren keresztül, közvetve használja —
    így mindkét út garantáltan ugyanazt a forráskészletet látja. Önálló
    hívásra (pl. UI-diagnosztika, "Felhasznált források" panel) is alkalmas.
    """
    sources: dict[str, dict[str, Any]] = {}
    for base_key in sorted(_CANONICAL_TEXTUS_SOURCE_KEYS):
        value = bundle.get(base_key)
        if not _background_value_is_usable(value):
            continue
        sources[base_key] = {
            "content": value,
            "origin": "textusműhely",
            "editable_by_user": True,
            "current_passage": _canonical_source_is_usable(bundle, base_key),
        }
    return {
        "passage": {
            "reference": _s(bundle.get("passage_reference")),
            "text": _s(bundle.get("passage_text")),
            "translation": _s(bundle.get("bible_translation")),
        },
        "sources": sources,
        # RESET 1A-DATA: korábban `bundle.get("outline_basket")` — a bundle
        # többé sosem tartalmaz ilyen kulcsot, ezért ez mindig üres marad.
        "user_notes": [],
        "identity": {
            "passage_reference": _s(bundle.get("passage_reference")),
            "passage_context_hash": compute_passage_context_hash(bundle),
        },
    }


def extract_outline_background_material(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Érdemi háttéranyagok (exegézis, nyelv, kortörténet, műhelydöntések…).

    Két szabály érvényesül `base_key` csoportja szerint (`_block_is_context_
    ready`): a `_HOMILETICAL_DECISION_KEYS` tagjai csak approved+friss
    állapotban kerülnek be (változatlan, ld. `_block_is_approved_and_fresh`);
    a `_CANONICAL_TEXTUS_SOURCE_KEYS` (Textusműhely-források) csak friss
    állapotot igényelnek, jóváhagyás nélkül is bekerülnek (Korrekciós fázis
    3.1, ld. `collect_canonical_source_material`). Minden más kulcs
    változatlanul megy át.
    """
    background: dict[str, Any] = {}
    for key in _BACKGROUND_BUNDLE_KEYS:
        if key not in bundle:
            continue
        base_key = key[: -len("_status")] if key.endswith("_status") else key
        if base_key in _APPROVAL_GATED_KEYS:
            if not _block_is_context_ready(bundle, base_key):
                continue
        value = bundle.get(key)
        if _background_value_is_usable(value):
            background[key] = value
    return background


def _gated_fallback_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """A bundle másolata, amelyben az `_APPROVAL_GATED_KEYS` blokkok
    KIZÁRÓLAG felhasználható (`_block_is_context_ready`) állapotban maradnak
    meg — draft/stale/soha jóvá nem hagyott HOMILETIKAI döntés, illetve
    stale Textusműhely-forrás itt eltávolítódik.

    MEGJEGYZÉS (2026-08-13, célarchitektúra-terv 2. fázis, 2. rész): a
    korábbi egyetlen hívója, a mechanikus `_heuristic_structured_from_
    bundle()` megszűnt (nincs többé nem-AI vázlat-fallback) — ez a
    függvény jelenleg a `generate_sermon_outline()` pipeline-jából NEM
    hívódik. Megmaradt, mert (a) tesztek közvetlenül ellenőrzik vele a
    "gated blokkok soha nem szivárognak ki draft/stale állapotban" garanciát
    (ld. tests/test_canonical_source_collector.py, tests/test_homiletical_
    model_unification.py, tests/test_sermon_workshop_ui_state_sync.py), és
    (b) ugyanazt a `_block_is_context_ready` dispatchert használja, mint a
    normál AI-útvonal `extract_outline_background_material()`-je — tehát
    továbbra is bizonyítja, hogy egy esetleges jövőbeli "mit látna egy
    gate-elt nézet" felhasználás garantáltan ugyanazt a forráskészletet
    kapná. Az összes NEM gated kulcs (igehely, bibliai szöveg, jóváhagyott
    felismerések/döntések, illusztrációk stb. — ezek saját gate-jükkel már a
    `collect_outline_context_bundle`-ben szűrve vannak) változatlanul átmegy.
    """
    out = dict(bundle)
    for base_key in _APPROVAL_GATED_KEYS:
        if base_key not in out:
            continue
        if not _block_is_context_ready(bundle, base_key):
            out.pop(base_key, None)
            out.pop(f"{base_key}_status", None)
            out.pop(f"{base_key}_approved_context_hash", None)
    return out


def extract_stale_approved_blocks(bundle: Mapping[str, Any]) -> list[str]:
    """Mely blokkok tartalma más igehelyhez/szöveghez készült, mint az
    aktuális — a homiletikai döntéseknél ("_HOMILETICAL_DECISION_KEYS")
    ez azt jelenti, hogy a jóváhagyást újra meg kell erősíteni; a
    Textusműhely-forrásoknál ("_CANONICAL_TEXTUS_SOURCE_KEYS", Korrekciós
    fázis 3.1 óta) jóváhagyás nélkül is figyelmeztető jelzés, hogy a
    tartalom frissítésre szorulhat, de NEM zárja ki automatikusan — ld.
    `_block_is_context_ready`."""
    stale: list[str] = []
    for key in _APPROVAL_GATED_KEYS:
        value = bundle.get(key)
        if not _background_value_is_usable(value):
            continue
        if key in _HOMILETICAL_DECISION_KEYS:
            is_stale = _block_is_stale(bundle, key)
        else:
            is_stale = _canonical_source_is_stale(bundle, key)
        if is_stale:
            stale.append(_GATED_KEY_LABELS.get(key, key))
    return stale


def extract_outline_excluded_draft_blocks(bundle: Mapping[str, Any]) -> list[str]:
    """Mely `_HOMILETICAL_DECISION_KEYS` blokkoknak van tartalma, de a
    session_state szerint nincsenek jóváhagyva — ezek maradnak ki emiatt a
    háttéranyagból. A `_CANONICAL_TEXTUS_SOURCE_KEYS` (Textusműhely-
    források) a Korrekciós fázis 3.1 óta jóváhagyás nélkül is bekerülnek,
    ezért itt nem szerepelnek — hiányuk nem "kizárás", legfeljebb hiányzó
    tartalom (ld. `collect_canonical_source_material`)."""
    excluded: list[str] = []
    for key in _HOMILETICAL_DECISION_KEYS:
        value = bundle.get(key)
        if not _background_value_is_usable(value):
            continue
        if _s(bundle.get(f"{key}_status")) != "approved":
            excluded.append(_GATED_KEY_LABELS.get(key, key))
    return excluded


def _bundle_has_rich_workshop_material(bundle: Mapping[str, Any]) -> bool:
    return bool(extract_outline_background_material(bundle))


def extract_outline_core_passage_context(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Mindig átadott alapbemenet: igehely + bibliai szöveg (+ alkalom/fókusz)."""
    core: dict[str, Any] = {}
    for key in _CORE_PASSAGE_KEYS:
        value = bundle.get(key)
        if value not in (None, "", [], {}):
            core[key] = value
    # Gyakori aliasok a session/collector oldaláról
    if "passage_reference" not in core:
        for alt in ("last_igehely", "igehely_input", "passage_reference"):
            if _s(bundle.get(alt)):
                core["passage_reference"] = _s(bundle.get(alt))
                break
    return core


def build_outline_user_prompt(
    bundle: Mapping[str, Any],
    *,
    mode: str = "standard",
) -> str:
    """Dinamikus user-prompt: textus mindig; háttér csak ha van érdemi anyag."""
    core = extract_outline_core_passage_context(bundle)
    background = extract_outline_background_material(bundle)
    excluded_blocks = extract_outline_excluded_draft_blocks(bundle)
    stale_blocks = extract_stale_approved_blocks(bundle)
    has_background = bool(background)

    # A korábbi "ÚJ GYORSVÁZLAT" (mode="quick") promptág a Textusműhely
    # önálló "Gyors vázlat" kártyájához tartozott — az a felület 2026-08-13-
    # án megszűnt (célarchitektúra-terv, 2. fázis, 1. lépés), az Igehirdetési
    # vázlat mostantól az EGYETLEN felhasználói vázlatkészítő belépési pont.
    # A `mode` paraméter csak forrás-jelölésre (source_tag) marad — a prompt
    # feltétel nélkül a műhely-jegyű utasítást kapja.
    _ = mode
    task_mode_note = (
        "ÚJ MŰHELYVÁZLAT: készíts szószékre kész Markdown prédikációvázlatot; "
        "a lelkész jóváhagyott döntéseit (ha vannak) építsd be szervesen."
    )
    try:
        from sermon_workshop_outline_synth_ai import (
            resolve_outline_occasion,
        )

        occasion = resolve_outline_occasion(bundle)
        occasion_block = f"ALKALOM: {occasion}\n"
    except Exception:  # noqa: BLE001
        occasion_block = ""

    ref = _s(core.get("passage_reference"))
    passage = _s(core.get("passage_text"))
    parts: list[str] = [
        task_mode_note,
        occasion_block.rstrip(),
        "Add vissza KIZÁRÓLAG a rendszerutasításban megadott Markdown struktúrát.",
        "Ne írj bevezetőt, magyarázatot vagy udvariaskodást.",
        "Célhossz kb. 300–500 szó.",
        "",
        f"IGEHELY: {ref or '(ismeretlen)'}",
        "",
        "BIBLIAI SZÖVEG (textus):",
        wrap_untrusted_content(
            "bibliai_textus",
            passage or json.dumps(core, ensure_ascii=False),
            limit_name="prompt_context_total",
        ),
    ]

    if has_background:
        parts.extend(
            [
                "",
                "HÁTTÉRANYAG (Bibliai áttekintés / exegézis / kortörténet / "
                "eredeti nyelv / műhely):",
                "Kizárólag erre az anyagra építve szervezd a vázlatot — ne "
                "végezz önálló elemzést azon a részterületen, ahol van adat.",
                wrap_untrusted_content(
                    "háttéranyag",
                    json.dumps(background, ensure_ascii=False),
                    limit_name="prompt_context_total",
                ),
            ]
        )
    else:
        parts.extend(
            [
                "",
                "BEMENETI MÓD: nincs külön mellékelt exegézis / kortörténet /"
                " eredeti nyelvi anyag ehhez a feladathoz — ez a leggyakoribb"
                " eset, nem kivétel. Ilyenkor a SAJÁT teológiai, nyelvi és"
                " kortörténeti tudásodra támaszkodva dolgozd fel a textust,"
                " hogy a vázlat önmagában is a lehető legjobb minőségű"
                " legyen.",
                "Használhatod a görög/héber kulcsszavak jelentését, ismert"
                " kortörténeti hátteret és teológiai összefüggéseket, HA"
                " azok jól megalapozott, általánosan elfogadott ismeretek."
                " SOHA ne találj ki konkrét, ellenőrizhetetlen részletet"
                " (pl. pontos évszámot, nevet, forrást, Strong-számot),"
                " amiben nem vagy biztos — ha bizonytalan egy állítás,"
                " fogalmazz óvatosan (\"valószínűleg\", \"a hagyomány"
                " szerint\"), vagy hagyd ki inkább, mint hogy kitalálj"
                " valamit.",
                "A cím sora után KÖZVETLENÜL a tartalmi gondolatmenet"
                " kezdődjön — ne írj bevezető megjegyzést arról, hogy nincs"
                " mellékelt háttéranyag; ez a bemeneti mód normális, nem"
                " hiány.",
            ]
        )

    if excluded_blocks:
        parts.extend(
            [
                "",
                "KIMARADT, NEM JÓVÁHAGYOTT BLOKKOK (szándékosan hiányoznak, "
                "a lelkész még nem hagyta jóvá őket): "
                + ", ".join(excluded_blocks) + ".",
                "NE hivatkozz rájuk, és NE pótold a tartalmukat saját "
                "kitalálással — egyszerűen hagyd ki őket a vázlatból.",
            ]
        )

    if stale_blocks:
        parts.extend(
            [
                "",
                "KIMARADT, ELAVULT JÓVÁHAGYÁSÚ BLOKKOK (az igehely vagy a "
                "bibliai szöveg megváltozott a jóváhagyás óta, ezért a "
                "vázlatmotor újra nem jóváhagyottnak tekinti őket): "
                + ", ".join(stale_blocks) + ".",
                "NE hivatkozz rájuk, és NE pótold a tartalmukat saját "
                "kitalálással — egyszerűen hagyd ki őket a vázlatból.",
            ]
        )

    return "\n".join(p for p in parts if p is not None)


def markdown_outline_to_structured(markdown: str) -> dict[str, Any]:
    """Markdown szószéki vázlat → belső structured séma (UI / validáció).

    2026-08-07 óta a kért forma EGYETLEN folyó szövegű test — nincs többé
    mezőnkénti/pontonkénti bontás, ezért a parser is minimális: a H1
    címsort (+ opcionális " – Igehely" utótagot) választja le, a maradék
    szöveg VÁLTOZATLANUL `body_markdown`. Ha a modell mégis a régi,
    tiltott mezős/pontos formában válaszolna, az itt nem kerül szétbontásra
    — a `validate_structured_outline()` `forbidden_structure` ellenőrzése
    fogja hibaként jelezni, ami a compress/enrich javítási kört indítja."""
    text = (markdown or "").strip()
    data = empty_structured_outline()
    if not text:
        return data

    # `re.search` + MULTILINE (nem `re.match`/pozíció-0 horgony): a modell
    # néha egy rövid előjegyzést (pl. "nincs mellékelt háttéranyag") tesz a
    # címsor ELÉ a kért elhelyezés ellenére is — ha a cím kinyerése pozíció-
    # 0-hoz lenne kötve, ez a teljes cím-felismerést meghiúsítaná. Az esetleg
    # a cím előtt/után maradó szöveg elvész, hanem a body_markdown elejére
    # kerül, hogy tartalom soha ne tűnjön el.
    title_m = re.search(r"^#\s+(.+?)(?:\s+[–—-]\s+(.+))?\s*$", text, re.M)
    if title_m:
        data["title"] = _s(title_m.group(1))
        if title_m.group(2):
            data["text_reference"] = _s(title_m.group(2))
        preamble = text[: title_m.start()].strip()
        remainder = text[title_m.end():].strip()
        text = f"{preamble}\n\n{remainder}".strip() if preamble else remainder

    data["body_markdown"] = text
    data["refinement_suggestions"] = []
    return normalize_structured_outline(data)


def _looks_like_markdown_outline(text: str) -> bool:
    """H1 címsor + érdemi folyó szöveg a cím után (2026-08-07 óta a forma
    NEM tartalmaz kötelező "###"/"Fókuszmondat" jelölőt — azok kifejezetten
    tiltottak —, ezért a régi jelölő-alapú felismerés helyett a cím +
    minimális szöveghossz a kritérium)."""
    raw = (text or "").strip()
    if not raw:
        return False
    title_m = re.search(r"^#\s+\S.*$", raw, re.M)
    if not title_m:
        return False
    body_after_title = raw[title_m.end():].strip()
    return word_count(body_after_title) >= 30


# =============================================================================
# 2C.1 (célarchitektúra-terv, 2. fázis, 3. rész, 2026-08-13): a generált
# vázlat SZERKEZETI koherenciájának ellenőrzése — NEM a hét homiletikai
# modellelem teológiai megvalósulásának szemantikai felismerése. A motor
# nem állítja és nem is állíthatja, hogy determinisztikusan megítéli, egy
# beszédegység ténylegesen "Alaphelyzet" vagy "Első fordulópont"-e — csak
# azt méri, hogy a KIMENET FORMÁJA (hány beszédegység van, egymástól
# ténylegesen megkülönböztethetőek-e) konzisztens-e azzal, amit egy jól
# tagolt, a rendszerpromptban leírt szerkezetet követő vázlat mutatna.
# =============================================================================

_MOVEMENT_HEADING_RE = re.compile(
    r"^[ \t]*\*\*[ \t]*(\d{1,2})[.)][ \t]*(.+?)[ \t]*\*\*[ \t]*$",
    re.MULTILINE,
)

SPEECH_UNIT_DISTINCTNESS_MIN_WORDS = 15
SPEECH_UNIT_DISTINCTNESS_SIMILARITY_THRESHOLD = 0.60


def _extract_markdown_movements(body_markdown: Any) -> list[dict[str, Any]]:
    """Defenzíven szegmentálja a kanonikus "**N. Cím**" mozgás-címekkel
    tagolt Markdown vázlattestet beszédegységekre.

    Kizárólag a KÖTELEZŐ FORMA szerinti (ld. OUTLINE_SYSTEM_PROMPT
    "MOZGÁS-CÍMEK" szakasza), számozott, félkövér, önálló sorban álló
    mozgás-címeket ismeri fel — NEM keresi és NEM várja el a hét
    modellelem (Belépés/Alaphelyzet/stb.) nevét vagy pontosan hét
    egységet; a cím szövege bármi lehet.

    Ha a szöveg nem tartalmaz felismerhető, kötelező formájú címet, üres
    listát ad vissza — ez NEM hibajelzés. A formai érvényesség (pl. hogy
    a modell egyáltalán a kért formában válaszolt-e) a MEGLÉVŐ
    `_has_forbidden_outline_structure`/`_looks_truncated_sentence`
    ellenőrzések felelőssége, nem ezé a függvényé; ez a függvény sosem
    dobhat kivételt üres, hiányos vagy hibás Markdownon."""
    text = (body_markdown or "")
    if not isinstance(text, str):
        text = _s(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return []
    matches = list(_MOVEMENT_HEADING_RE.finditer(text))
    if not matches:
        return []
    units: list[dict[str, Any]] = []
    for i, m in enumerate(matches):
        title = _s(m.group(2))
        if not title:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        unit_body = text[start:end].strip()
        units.append(
            {"index": len(units) + 1, "title": title, "body": unit_body}
        )
    return units


def _speech_unit_word_set(text: Any) -> set[str]:
    return set(re.findall(r"\w+", _s(text).casefold()))


def _assess_outline_structure(units: list[Mapping[str, Any]]) -> list[str]:
    """Szerkezeti proxy-ellenőrzések a Markdown beszédegységeken.

    KIZÁRÓLAG mennyiségi/formai jelzéseket ad — nem méri, hogy a
    tartalom ténylegesen követi-e a felismerési ívet. Ha `units` üres
    (a parser nem talált felismerhető címet), nem ad vissza issue-t: ez
    NEM azonos azzal, hogy "túl kevés" beszédegység van — egyszerűen
    nincs elég megbízható jel a szerkezeti ellenőrzéshez, és a formai
    érvényességet más ellenőrzés felelőssége lefedni."""
    issues: list[str] = []
    if not units:
        return issues

    n = len(units)
    if n < LIMITS["min_speech_units"]:
        issues.append("too_few_speech_units")
    elif n > LIMITS["max_speech_units"]:
        issues.append("too_many_speech_units")

    # Megkülönböztethetőség: csak akkor hasonlítunk két egységet, ha
    # mindkettő elér egy minimális hosszt (rövid egységeknél a kis
    # szókészlet miatt a hasonlósági arány megbízhatatlanul ingadozna),
    # és csak a NORMALIZÁLT szóhalmazok Jaccard-átfedését nézzük — pár
    # közös (akár teológiai) szó önmagában alacsony átfedést ad, csak a
    # nagyfokú, szinte-azonos tartalom éri el a küszöböt.
    word_sets: list[set[str]] = []
    for u in units:
        word_sets.append(_speech_unit_word_set(u.get("body")))
    for i in range(len(units)):
        if len(word_sets[i]) < SPEECH_UNIT_DISTINCTNESS_MIN_WORDS:
            continue
        for j in range(i + 1, len(units)):
            if len(word_sets[j]) < SPEECH_UNIT_DISTINCTNESS_MIN_WORDS:
                continue
            union = word_sets[i] | word_sets[j]
            if not union:
                continue
            overlap = len(word_sets[i] & word_sets[j]) / len(union)
            if overlap >= SPEECH_UNIT_DISTINCTNESS_SIMILARITY_THRESHOLD:
                issues.append("units_not_distinct")
                break
        if "units_not_distinct" in issues:
            break

    return issues


def clear_outline_generation_caches(session: MutableMapping[str, Any]) -> None:
    """Projektváltáskor / új munkánál ürítendő outline AI-cache."""
    session.pop(RAPID_EVIDENCE_SESSION_KEY, None)


def _generate_rapid_evidence(
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn,
    session: MutableMapping[str, Any],
    context_hash: str,
) -> dict[str, Any] | None:
    """Gyors háttércsomag — cache-elve context_hash alapján."""
    cache = session.get(RAPID_EVIDENCE_SESSION_KEY)
    if not isinstance(cache, dict):
        cache = {}
        session[RAPID_EVIDENCE_SESSION_KEY] = cache
    cached = cache.get(context_hash)
    if isinstance(cached, dict) and cached:
        return cached

    passage = _s(bundle.get("passage_text"))
    ref = _s(bundle.get("passage_reference"))
    if not passage:
        return None
    user_prompt = (
        f"Igehely: {ref}\n\n"
        f"{wrap_untrusted_content('PASSAGE', passage[:6000])}\n\n"
        "Készíts rövid belső háttércsomagot a fenti JSON sémában."
    )
    try:
        try:
            raw = generate_fn(
                user_prompt,
                enable_google_search=False,
                tab_label=TAB_OUTLINE,
                use_cache=False,
                system_bundle=RAPID_EVIDENCE_SYSTEM_PROMPT,
                include_brevity_directive=False,
                max_output_tokens=900,
            )
        except TypeError:
            raw = generate_fn(user_prompt)
    except Exception as exc:  # pragma: no cover
        logger.info("rapid_evidence_failed err=%s", type(exc).__name__)
        return None
    if _is_api_error_text(raw):
        return None
    obj = extract_json_object(raw) or {}
    if not isinstance(obj, dict):
        return None
    try:
        obj = sanitize_ai_json(obj)
    except Exception:
        pass
    pack = {
        "central_claim": _s(obj.get("central_claim")),
        "internal_movement": _s(obj.get("internal_movement")),
        "literary_context": _s(obj.get("literary_context")),
        "historical_notes": _s(obj.get("historical_notes")),
        "language_notes": _s(obj.get("language_notes")),
        "theological_horizon": _s(obj.get("theological_horizon")),
        "homiletical_path": _s(obj.get("homiletical_path")),
    }
    if not any(pack.values()):
        return None
    cache[context_hash] = pack
    session[RAPID_EVIDENCE_SESSION_KEY] = cache
    return pack


def mirror_outline_to_session_strings(
    session_state: MutableMapping[str, Any],
    outline: Mapping[str, Any],
) -> None:
    """Kanonikus vázlat → session outline / outline_draft tükrök (Word-export)."""
    from sermon_workshop_outline_ai import outline_canonical_text

    body = outline_canonical_text(outline)
    if body:
        session_state["outline"] = body
        session_state["outline_draft"] = body


def outline_needs_refresh(
    outline: Any,
    bundle: Mapping[str, Any],
) -> bool:
    safe = normalize_sermon_outline(outline)
    schema = _s(safe.get("schema_version"))
    if schema and schema != SCHEMA_VERSION:
        return True
    if not schema and (
        _s(safe.get("content"))
        or (isinstance(safe.get("movements"), list) and safe.get("movements"))
        or (isinstance(safe.get("structured"), dict) and safe.get("structured"))
    ):
        return True
    stored = _s(safe.get("context_hash") or safe.get("source_fingerprint"))
    if not stored:
        return False
    current = compute_context_hash(bundle)
    return bool(current and stored != current)


REFRESH_NOTICE = (
    "A műhelyanyag a vázlat elkészítése óta megváltozott. A vázlat frissíthető."
)

INVALID_OUTLINE_MESSAGE = (
    "A vázlatgenerálás nem adott szószéken használható munkavázlatot "
    f"(abszolút felső határ {LIMITS['absolute_max_words']} szó; "
    "a céltartomány minőségi iránymutatás). "
    "Próbáld újra — a hosszú prédikációs szöveg vagy a szerkezetileg hibás "
    "vázlat nem kerül mentésre."
)

# 2C.1: a beszédegység-SZÁM (nem a tartalom hossza) miatti elutasítás
# külön, pontosabb üzenetet kap — ha a javítási kísérlet(ek) után is
# 1 vagy 5+ felismerhető beszédegység marad.
SPEECH_UNIT_COUNT_INVALID_MESSAGE = (
    "A vázlatgenerálás a beszédegységek számában nem érte el a "
    f"szerkezeti elvárást ({LIMITS['min_speech_units']}–"
    f"{LIMITS['max_speech_units']} beszédegység) — sem az eredeti, sem a "
    "javítási kísérlet nem adott ennek megfelelő tagolást. "
    "Próbáld újra a generálást."
)

SCHEMA_REFRESH_NOTICE = (
    "Ez a vázlat korábbi sémával készült. Frissíthető az új motorral; "
    "a meglévő szöveg megmarad, amíg újat nem generálsz."
)

# =============================================================================
# EGYETLEN GENERÁLÁSI SZERZŐDÉS (célarchitektúra-terv, 2. fázis, 2. rész,
# 2026-08-13): vázlat KIZÁRÓLAG sikeres AI-szintézisből vagy már meglévő,
# érvényes mentett vázlatból származhat. Nincs többé mechanikus,
# versszakaszokra daraboló "álvázlat" — sem `generate_fn=None`, sem sikertelen
# AI-hívás, sem érvénytelen AI-válasz esetén. Az `OutlineGenerationResult.
# error_kind` legalább a következő három esetet különbözteti meg (ld. lent a
# tényleges hozzárendeléseket):
#   - "ai_unavailable"     — nincs elérhető MI-hívó funkció (generate_fn=None);
#   - "ai_call_failed"     — az MI-hívás kivételt dobott vagy a szolgáltatás
#                            explicit hibát jelzett;
#   - "ai_invalid_response" — az MI válasza csonka, feldolgozhatatlan, vagy a
#                            biztonsági szűrés elutasította.
# Emellett a meglévő, egyéb ok=False esetekhez is kapnak error_kind/retryable
# jelölést (pl. hiányzó bibliai szöveg, nem elég háttéranyag, kézi
# szerkesztés-ütközés, végső validáció sikertelensége, üres eredmény).
# =============================================================================

AI_UNAVAILABLE_MESSAGE = (
    "A vázlat elkészítéséhez MI-generálás szükséges — jelenleg nincs "
    "elérhető MI-hívó funkció. Mechanikus, versdaraboló álvázlat nem készül."
)


@dataclass
class OutlineGenerationResult:
    outline: dict[str, Any] = field(default_factory=empty_sermon_outline)
    ok: bool = True
    error_message: str = ""
    # Strukturált hibaosztályozás — üres string sikeres generáláskor.
    # Ismert értékek: "missing_passage", "not_ready", "manual_edit_conflict",
    # "ai_unavailable", "ai_call_failed", "ai_invalid_response",
    # "validation_failed", "empty_result".
    error_kind: str = ""
    # True, ha a hívó számára érdemes egy változatlan bemenettel újra
    # próbálkoznia (pl. átmeneti AI-hiba) — False, ha a hiba oka a bemenet
    # vagy a hívó felelőssége (pl. hiányzó igehely, nincs generate_fn).
    retryable: bool = False
    warnings: list[str] = field(default_factory=list)
    validation_issues: list[str] = field(default_factory=list)
    source: str = ""
    overwritten_manual_edit: bool = False
    compressed: bool = False
    enriched: bool = False
    schema_version: str = SCHEMA_VERSION
    raw_word_count: int = 0
    rendered_word_count: int = 0

    def to_assembly_dict(self) -> dict[str, Any]:
        return {
            "outline": dict(self.outline),
            "ok": self.ok,
            "error_message": self.error_message,
            "error_kind": self.error_kind,
            "retryable": self.retryable,
            "warnings": list(self.warnings),
            "overwritten_manual_edit": self.overwritten_manual_edit,
        }


def _call_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    system_bundle: str = OUTLINE_SYSTEM_PROMPT,
    temperature: float = DEFAULT_TEMPERATURE,
    as_json: bool = False,
) -> str:
    prev_temp = None
    touched = False
    try:
        import streamlit as st

        prev_temp = st.session_state.get("temperature")
        st.session_state["temperature"] = float(temperature)
        touched = True
    except Exception:  # noqa: BLE001
        touched = False
    try:
        kwargs: dict[str, Any] = {
            "enable_google_search": False,
            "tab_label": TAB_OUTLINE,
            "use_cache": False,
            "system_bundle": system_bundle,
            "include_brevity_directive": False,
            "max_output_tokens": OUTLINE_MAX_OUTPUT_TOKENS,
        }
        if as_json:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_schema"] = OUTLINE_RESPONSE_SCHEMA
        else:
            # Csonkulás-védelem: a Markdown-vázlat MAX_TOKENS-nél megszakadt
            # válasza korábban változtatás nélkül ment tovább a regex-
            # parserbe (torz "v. —" placeholderek, hiányos pontok). Most a
            # generate_text() már ismert truncated/_looks_incomplete_response
            # ellenőrzésével elutasítjuk — a hívó (_ai_generate_structured)
            # ezt a sentinelt felismeri és a heurisztikus fallbackra vált,
            # ahelyett hogy egy csonka dokumentumot próbálna feldolgozni.
            kwargs["truncation_notice_mode"] = "never"
            kwargs["incomplete_response_message"] = _OUTLINE_INCOMPLETE_SENTINEL
        try:
            return generate_fn(prompt, **kwargs)
        except TypeError:
            # Teszt / legacy generate_fn signature
            return generate_fn(
                prompt,
                enable_google_search=False,
                tab_label=TAB_OUTLINE,
                use_cache=False,
                system_bundle=system_bundle,
                include_brevity_directive=False,
                max_output_tokens=OUTLINE_MAX_OUTPUT_TOKENS,
            )
    finally:
        if touched:
            try:
                import streamlit as st

                if prev_temp is None:
                    st.session_state.pop("temperature", None)
                else:
                    st.session_state["temperature"] = prev_temp
            except Exception:  # noqa: BLE001
                pass


def _call_generate_with_retry(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    system_bundle: str = OUTLINE_SYSTEM_PROMPT,
    temperature: float = DEFAULT_TEMPERATURE,
    as_json: bool = False,
) -> str:
    """`_call_generate()` egyszeri újrapróbálkozással.

    Csak a compress/enrich/Markdown-javító hívásokhoz — ezek egy sikertelen
    (pl. átmeneti 503-as) próbálkozás esetén a teljes javítási kísérletet
    elvesztegetnék, és a mechanikus, kevésbé jó minőségű vészmegoldásra
    (`_rescue_structured_outline`) kényszerítenék a folyamatot, holott egy
    második próbálkozás gyakran sikerül. NEM az elsődleges vázlatgeneráló
    hívásra vonatkozik — az saját, meglévő csonkulás-kezeléssel rendelkezik."""
    try:
        result = _call_generate(
            generate_fn,
            prompt,
            system_bundle=system_bundle,
            temperature=temperature,
            as_json=as_json,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("outline_repair_call_retry reason=exception err=%s", exc)
        time.sleep(1.5)
        return _call_generate(
            generate_fn,
            prompt,
            system_bundle=system_bundle,
            temperature=temperature,
            as_json=as_json,
        )
    # `_is_api_error_text` az üres választ és a figyelmeztető-jelölésű
    # (⚠️/⏳/Hiba/❌) hibaszöveget kapja el, de a csonkulás-védelem sentinel
    # értékét (`_OUTLINE_INCOMPLETE_SENTINEL`, MAX_TOKENS esetén) NEM — azt
    # külön kell ellenőrizni, különben egy csonkult javító-válasz retry
    # nélkül, hiányos válaszként bukna el.
    stripped = (result or "").strip()
    if _is_api_error_text(result or "") or stripped == _OUTLINE_INCOMPLETE_SENTINEL:
        logger.info("outline_repair_call_retry reason=empty_or_truncated")
        time.sleep(1.5)
        return _call_generate(
            generate_fn,
            prompt,
            system_bundle=system_bundle,
            temperature=temperature,
            as_json=as_json,
        )
    return result


def _ai_generate_structured(
    bundle: Mapping[str, Any],
    *,
    generate_fn: GenerateFn,
    seed_outline: Mapping[str, Any] | None = None,
    mode: str = "standard",
) -> tuple[dict[str, Any] | None, list[str], int, str, str]:
    """Returns (structured|None, warnings, raw_word_count, markdown_content,
    error_kind). `error_kind` üres string sikeres válasznál; egyébként
    "ai_call_failed" (a hívás kivételt dobott, vagy a szolgáltatás explicit
    hibát jelzett) vagy "ai_invalid_response" (csonka, feldolgozhatatlan,
    vagy a biztonsági szűrésen elakadt válasz) — ld. AI_UNAVAILABLE_MESSAGE
    és a hívó `generate_sermon_outline()` egységes szerződését."""
    warnings: list[str] = []
    _ = seed_outline  # seed csak a végleges outline metaadat-egyesítésénél kell; az AI önálló vázlatot ír
    prompt = build_outline_user_prompt(bundle, mode=mode)
    try:
        raw = _call_generate(generate_fn, prompt, temperature=0.3, as_json=False)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Vázlat MI-hívás sikertelen: {exc}")
        return None, warnings, 0, "", "ai_call_failed"
    if _is_api_error_text(raw or ""):
        warnings.append("A vázlat MI-válasza hibát jelzett.")
        return None, warnings, 0, "", "ai_call_failed"
    if (raw or "").strip() == _OUTLINE_INCOMPLETE_SENTINEL:
        logger.warning(
            "outline_ai_truncated schema=%s mode=%s — MAX_TOKENS előtt megszakadt "
            "válasz",
            SCHEMA_VERSION,
            mode,
        )
        warnings.append(
            "A vázlat MI-válasza félbeszakadt (túllépte a kimeneti korlátot). "
            "Próbáld újra a generálást."
        )
        return None, warnings, 0, "", "ai_invalid_response"

    raw_text = (raw or "").strip()
    # Elsődleges: Markdown szószéki vázlat
    if _looks_like_markdown_outline(raw_text):
        structured = markdown_outline_to_structured(raw_text)
        # Tartalom: a nyers Markdown marad a megjelenített szöveg
        md_wc = word_count(raw_text)
        logger.info(
            "outline_ai_markdown schema=%s words=%s background=%s",
            SCHEMA_VERSION,
            md_wc,
            bool(extract_outline_background_material(bundle)),
        )
        return structured, warnings, md_wc, raw_text, ""

    # Visszafelé kompatibilitás: JSON válasz
    obj = extract_json_object(raw_text)
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen vázlatválasz (sem Markdown, sem JSON).")
        logger.info(
            "outline_invalid_response schema=%s raw_words=%s",
            SCHEMA_VERSION,
            word_count(raw_text),
        )
        return None, warnings, word_count(raw_text), "", "ai_invalid_response"
    cleaned = sanitize_ai_json(
        obj,
        allowed_keys={
            "title",
            "text_reference",
            "scope_note",
            "body_markdown",
            "refinement_suggestions",
            "schema_version",
            # Régi mezőnevek: csak visszafelé-kompatibilis beolvasásra (pl.
            # egy még folyamatban lévő javítási kísérlet a régi sémában
            # válaszol) — új generálás célja mindig `body_markdown`.
            "focus_sentence",
            "introduction_direction",
            "points",
            "conclusion_direction",
            "subpoints",
            "application",
            "textual_insight",
            "theological_emphasis",
            "listener_movement",
        },
    )
    if cleaned is None:
        warnings.append("A vázlat JSON biztonsági szűrése sikertelen.")
        return None, warnings, word_count(raw_text), "", "ai_invalid_response"
    structured = normalize_structured_outline(cleaned)
    raw_wc = word_count(render_structured_outline(structured))
    logger.info(
        "outline_ai_json schema=%s rendered_words=%s forbidden=%s background=%s",
        SCHEMA_VERSION,
        raw_wc,
        _has_forbidden_keys(obj),
        bool(extract_outline_background_material(bundle)),
    )
    return structured, warnings, raw_wc, "", ""


def _repair_source_context(bundle: Mapping[str, Any], *, rich: bool = False) -> dict[str, Any]:
    """Passage-only for compress; richer support material for enrich."""
    ctx: dict[str, Any] = {
        "passage_reference": bundle.get("passage_reference", ""),
        "passage_text": bundle.get("passage_text", ""),
        "bible_translation": bundle.get("bible_translation", ""),
    }
    if not rich:
        return ctx

    def _clip(value: Any, n: int) -> str:
        text = _s(value)
        return text if len(text) <= n else text[: n - 1].rstrip() + "…"

    for key, cap in (
        ("exegesis", 1200),
        ("original_text", 800),
        ("history", 600),
        ("theology", 800),
        ("user_focus", 400),
        ("text_main_idea", 400),
        ("sermon_main_idea", 400),
    ):
        val = _clip(bundle.get(key), cap)
        if val:
            ctx[key] = val
    return ctx


def _compress_structured(
    payload: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    # rich=True: a verbatim_source_copy javításához a modellnek ténylegesen
    # látnia kell az exegézis/kortörténet/teológia szövegét, különben csak
    # a már hibás vázlatból tud "szintetizálni" — nem tud valódi forrásra
    # visszavezetett, saját megfogalmazást adni.
    repair_context = _repair_source_context(bundle, rich=True)
    try:
        from sermon_workshop_outline_synth_ai import (
            _is_partial_workshop_bundle,
            outline_length_profile,
            resolve_outline_occasion,
        )

        profile = outline_length_profile(
            resolve_outline_occasion(bundle),
            partial=_is_partial_workshop_bundle(bundle),
        )
        occasion_line = (
            f"ALKALOM: {profile['occasion']}. "
            f"CÉL: ~{profile['target_range']} szó "
            f"(max {LIMITS['absolute_max_words']}).\n"
        )
        if profile.get("partial"):
            occasion_line += "Részleges műhelyanyag: tartsd a teljes szerkezetet, rövidebben.\n"
    except Exception:  # noqa: BLE001
        occasion_line = ""
    # Strip prose-bait keys before sending to compress
    slim = normalize_structured_outline(payload)
    prompt = (
        f"{COMPRESS_INSTRUCTION}\n"
        f"{occasion_line}"
        f"SÉMAVERZIÓ: {SCHEMA_VERSION}\n"
        f"JELZETT PROBLÉMÁK: {', '.join(issues)}\n"
        "Add vissza a teljes vázlatot a szigorú JSON sémában "
        "(thesis/body/content nélkül).\n\n"
        f"FORRÁS (csak támasz):\n{json.dumps(repair_context, ensure_ascii=False)}\n\n"
        f"JAVÍTANDÓ VÁZLAT:\n{json.dumps(slim, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_JSON_SHAPE}"
    )
    try:
        raw = _call_generate_with_retry(generate_fn, prompt, temperature=0.2, as_json=True)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Tömörítő javítás sikertelen: {exc}")
        return None, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A tömörítő javítás API-hibát jelzett.")
        return None, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen tömörítő válasz.")
        return None, warnings
    logger.info(
        "outline_compress schema=%s rendered_words=%s",
        SCHEMA_VERSION,
        word_count(render_structured_outline(normalize_structured_outline(obj))),
    )
    return normalize_structured_outline(obj), warnings


MARKDOWN_COMPRESS_INSTRUCTION = (
    "JAVÍTÁS A SAJÁT KORÁBBI VÁLASZODON — az alábbi vázlatot te magad írtad, "
    "de az automatikus ellenőrzés problémát jelzett benne. "
    "Ha a jelzett problémák közt szerepel `verbatim_source_copy`: egy vagy "
    "több szakasz szó szerint (vagy majdnem szó szerint, 8+ egymást követő "
    "szóban) átvette a bibliai szöveg vagy a lenti FORRÁS egy hosszabb "
    "részletét ahelyett, hogy szintetizálta volna — ezeket írd át saját, "
    "tömör, szintetizáló megfogalmazásra. NE idézd szó szerint a verset "
    "vagy a háttéranyagot; fogalmazd meg a lényegét a magad szavaival. "
    "Ha hosszúsági probléma is szerepel (pl. `over_absolute_max`, "
    "`layer_too_long`, `prose_block_too_long`, `intro_too_long`, "
    "`conclusion_too_long`): tömörítsd az érintett részt. "
    "A vázlat homiletikai ívét, szerkezetét és a meglévő főpontok számát "
    "őrizd meg — ne tervezz új vázlatot, ne adj hozzá új exegetikai vagy "
    "teológiai állítást. "
    "Add vissza a TELJES, javított vázlatot PONTOSAN ugyanabban a Markdown "
    "formátumban és szakaszszerkezetben, mint amit kaptál — ne válts JSON-ra "
    "vagy más formátumra, és ne írj magyarázatot a vázlaton kívül."
)

MARKDOWN_COMPRESS_ESCALATION_INSTRUCTION = (
    "MÁSODIK, HATÁROZOTTABB JAVÍTÁSI KÍSÉRLET — az előző javítási próbálkozásod "
    "NEM oldotta meg teljesen a problémát: az alábbi vázlatban MÉG MINDIG van "
    "olyan szakasz, amely 8 vagy több egymást követő szóban szó szerint "
    "megegyezik a bibliai szöveggel vagy a háttéranyaggal. "
    "Ez alkalommal NE csak finoman átfogalmazz — OLVASD ÁT SORBAN AZ EGÉSZ "
    "SZÖVEGET, bekezdésről bekezdésre, és ahol szó szerinti vagy majdnem szó "
    "szerinti átvételt találsz, ÍRD ÁT TELJESEN, saját szavakkal, a lényeg "
    "megtartásával, de egyetlen 8 szónál hosszabb szó szerinti egyezés "
    "nélkül a bibliai szöveggel vagy a háttéranyaggal. Inkább legyen egy "
    "mondat rövidebb és egyszerűbb, mint hogy idézetet tartalmazzon. "
    "A vázlat homiletikai ívét, szerkezetét és a meglévő főpontok számát "
    "őrizd meg. "
    "Add vissza a TELJES, javított vázlatot PONTOSAN ugyanabban a Markdown "
    "formátumban és szakaszszerkezetben, mint amit kaptál — ne válts JSON-ra "
    "vagy más formátumra, és ne írj magyarázatot a vázlaton kívül."
)


def _compress_markdown(
    markdown_text: str,
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn,
    escalate: bool = False,
) -> tuple[str | None, list[str]]:
    """Markdown-szintű javítás: a modell saját nyers Markdown-válaszát kapja
    vissza a konkrét validációs problémákkal együtt, és Markdown formátumban
    javít — nem vált a mechanikus JSON sémára (az természetellenes, tömbösített
    kimenetet adna), és a háttéranyagot (exegézis/kortörténet/teológia) is
    megkapja, hogy legyen miből ténylegesen szintetizálnia, ne csak a már
    hibás vázlatból dolgozzon.

    `escalate=True`: második, határozottabb kísérlet — akkor hívjuk, ha az
    első (akár Markdown-, akár JSON-alapú) javítás szintaktikailag sikerült,
    de a probléma a re-validáció szerint mégis megmaradt."""
    warnings: list[str] = []
    instruction = (
        MARKDOWN_COMPRESS_ESCALATION_INSTRUCTION if escalate else MARKDOWN_COMPRESS_INSTRUCTION
    )
    repair_context = _repair_source_context(bundle, rich=True)
    prompt = (
        f"{instruction}\n\n"
        f"JELZETT PROBLÉMÁK: {', '.join(issues)}\n\n"
        f"FORRÁS (támasz a javításhoz):\n"
        f"{wrap_untrusted_content('forrás', json.dumps(repair_context, ensure_ascii=False), limit_name='prompt_context_total')}\n\n"
        f"JAVÍTANDÓ VÁZLAT (Markdown):\n"
        f"{wrap_untrusted_content('vázlat', markdown_text, limit_name='prompt_context_total')}"
    )
    try:
        raw = _call_generate_with_retry(
            generate_fn,
            prompt,
            system_bundle=OUTLINE_SYSTEM_PROMPT,
            temperature=0.2,
            as_json=False,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Markdown-javítás sikertelen: {exc}")
        return None, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A Markdown-javítás API-hibát jelzett.")
        return None, warnings
    raw_text = (raw or "").strip()
    if not raw_text or raw_text == _OUTLINE_INCOMPLETE_SENTINEL:
        warnings.append("A Markdown-javítás válasza hiányos vagy üres volt.")
        return None, warnings
    if not _looks_like_markdown_outline(raw_text):
        warnings.append("A Markdown-javítás válasza nem Markdown-formátumú volt.")
        return None, warnings
    logger.info(
        "outline_markdown_compress schema=%s words=%s",
        SCHEMA_VERSION,
        word_count(raw_text),
    )
    return raw_text, warnings


def _enrich_structured(
    payload: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    repair_context = _repair_source_context(bundle, rich=True)
    slim = normalize_structured_outline(payload)
    prompt = (
        f"{ENRICH_INSTRUCTION}\n"
        f"SÉMAVERZIÓ: {SCHEMA_VERSION}\n"
        f"JELZETT PROBLÉMÁK: {', '.join(issues)}\n"
        "Egészítsd ki a `body_markdown` folyó szövegét a forrásból, mondatba "
        "ágyazva. Cél: 450–750 szó; ne lépd át a 850 szót.\n\n"
        f"FORRÁS (mélyítéshez):\n{json.dumps(repair_context, ensure_ascii=False)}\n\n"
        f"MÉLYÍTENDŐ VÁZLAT:\n{json.dumps(slim, ensure_ascii=False)}\n\n"
        f"Kimenet JSON séma:\n{_JSON_SHAPE}"
    )
    try:
        raw = _call_generate_with_retry(generate_fn, prompt, temperature=0.35, as_json=True)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Mélyítő javítás sikertelen: {exc}")
        return None, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A mélyítő javítás API-hibát jelzett.")
        return None, warnings
    obj = extract_json_object(raw or "")
    if not isinstance(obj, dict):
        warnings.append("Érvénytelen mélyítő válasz.")
        return None, warnings
    logger.info(
        "outline_enrich schema=%s rendered_words=%s",
        SCHEMA_VERSION,
        word_count(render_structured_outline(normalize_structured_outline(obj))),
    )
    return normalize_structured_outline(obj), warnings


MARKDOWN_ENRICH_INSTRUCTION = (
    "TARTALMI KIEGÉSZÍTÉS A SAJÁT KORÁBBI VÁLASZODON — az alábbi vázlatot te "
    "magad írtad, de az automatikus ellenőrzés szerint felszínes, "
    "ismétlődő, vagy túl rövid. "
    "A szerkezetet és az igehely-beosztást őrizd meg; ne írj új prédikációt "
    "és ne találj ki verseket vagy tényeket. "
    "Gazdagítsd a lenti FORRÁS anyagából — konkrét, a forrásra "
    "visszavezethető megfigyeléssel, nem közhellyel, MONDATBA ÁGYAZVA. "
    "A szöveg EGY folyó, bekezdésekre tagolt gondolatmenet maradjon — NE "
    "válts számozott alcímekre vagy mezőcímkékre (pl. \"Igei fókusz:\"). "
    "Ne ismételd ugyanazt a mondatot más bekezdésben. "
    "Ha a JELZETT PROBLÉMÁK között \"too_few_speech_units\" szerepel, a "
    "meglévő beszédegység(ek)et bontsd tovább egy indokolt, tartalmi "
    "határnál; \"too_many_speech_units\" esetén vonj össze két egymáshoz "
    "közel álló egységet; \"units_not_distinct\" esetén tedd egyértelműen "
    "megkülönböztethetővé a túlságosan hasonló beszédegységeket — mindezt "
    "a rendszerutasítás BESZÉDEGYSÉGEK SZÁMA szakasza szerint (2–4 egység, "
    "számozott félkövér cím soronként), nem a hét modellelem külön-külön "
    "kimásolásával. "
    "Add vissza a TELJES, kiegészített vázlatot PONTOSAN ugyanabban a "
    "Markdown formátumban, mint amit kaptál — ne válts JSON-ra vagy más "
    "formátumra, és ne írj magyarázatot a vázlaton kívül."
)

MARKDOWN_ENRICH_ESCALATION_INSTRUCTION = (
    "MÁSODIK, HATÁROZOTTABB KIEGÉSZÍTÉSI KÍSÉRLET — az előző kiegészítési "
    "próbálkozásod NEM oldotta meg teljesen a problémát: az alábbi vázlat "
    "MÉG MINDIG felszínes, ismétlődő vagy túl rövid. Ez alkalommal OLVASD "
    "ÁT SORBAN AZ EGÉSZ SZÖVEGET, bekezdésről bekezdésre, és ahol felszínes "
    "vagy hiányos, ÍRJ HOZZÁ konkrét, a FORRÁSBAN ténylegesen szereplő "
    "megfigyelést — ne általánosságot, ne közhelyet, mondatba ágyazva. "
    "A vázlat homiletikai ívét és a folyó szövegű, tagolatlan formát "
    "őrizd meg — NE válts számozott alcímekre vagy mezőcímkékre. "
    "Ha a JELZETT PROBLÉMÁK között beszédegység-szám vagy megkülönböztethe"
    "tőségi jelzés szerepel (too_few_speech_units / too_many_speech_units "
    "/ units_not_distinct), igazítsd a beszédegység-tagolást a "
    "rendszerutasítás szerinti 2–4 egységre. "
    "Add vissza a TELJES, kiegészített vázlatot PONTOSAN ugyanabban a "
    "Markdown formátumban, mint amit kaptál — ne válts JSON-ra vagy más "
    "formátumra, és ne írj magyarázatot a vázlaton kívül."
)


def _enrich_markdown(
    markdown_text: str,
    bundle: Mapping[str, Any],
    *,
    issues: list[str],
    generate_fn: GenerateFn,
    escalate: bool = False,
) -> tuple[str | None, list[str]]:
    """Markdown-szintű tartalmi kiegészítés — a `_compress_markdown()` párja
    a "túl sovány" hibaosztályra. Megőrzi a természetes prózát a mechanikus
    JSON-séma helyett, és a háttéranyagot is megkapja (rich=True).

    `escalate=True`: második, határozottabb kísérlet, ha az első kiegészítés
    szintaktikailag sikerült, de a probléma a re-validáció szerint mégis
    megmaradt."""
    warnings: list[str] = []
    instruction = (
        MARKDOWN_ENRICH_ESCALATION_INSTRUCTION if escalate else MARKDOWN_ENRICH_INSTRUCTION
    )
    repair_context = _repair_source_context(bundle, rich=True)
    prompt = (
        f"{instruction}\n\n"
        f"JELZETT PROBLÉMÁK: {', '.join(issues)}\n\n"
        f"FORRÁS (mélyítéshez):\n"
        f"{wrap_untrusted_content('forrás', json.dumps(repair_context, ensure_ascii=False), limit_name='prompt_context_total')}\n\n"
        f"MÉLYÍTENDŐ VÁZLAT (Markdown):\n"
        f"{wrap_untrusted_content('vázlat', markdown_text, limit_name='prompt_context_total')}"
    )
    try:
        raw = _call_generate_with_retry(
            generate_fn,
            prompt,
            system_bundle=OUTLINE_SYSTEM_PROMPT,
            temperature=0.3,
            as_json=False,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Markdown-mélyítés sikertelen: {exc}")
        return None, warnings
    if _is_api_error_text(raw or ""):
        warnings.append("A Markdown-mélyítés API-hibát jelzett.")
        return None, warnings
    raw_text = (raw or "").strip()
    if not raw_text or raw_text == _OUTLINE_INCOMPLETE_SENTINEL:
        warnings.append("A Markdown-mélyítés válasza hiányos vagy üres volt.")
        return None, warnings
    if not _looks_like_markdown_outline(raw_text):
        warnings.append("A Markdown-mélyítés válasza nem Markdown-formátumú volt.")
        return None, warnings
    logger.info(
        "outline_markdown_enrich schema=%s words=%s",
        SCHEMA_VERSION,
        word_count(raw_text),
    )
    return raw_text, warnings


def _clip_body_to_full_paragraphs(body: str, max_w: int) -> str:
    """Rövidít teljes bekezdések mentén — soha nem vág félbe mondatot/
    bekezdést. A `_clip_to_full_sentences()` bekezdés-tudatos párja,
    a folyó szövegű `body_markdown` biztonsági hálójaként."""
    raw = _s(body)
    if not raw or word_count(raw) <= max_w:
        return raw
    paragraphs = [p for p in raw.split("\n\n") if p.strip()]
    kept: list[str] = []
    for para in paragraphs:
        trial = "\n\n".join(kept + [para])
        if kept and word_count(trial) > max_w:
            break
        kept.append(para)
    if kept:
        return "\n\n".join(kept).strip()
    # Egyetlen bekezdés is túl hosszú: mondatszinten vágjunk.
    return _clip_to_full_sentences(paragraphs[0], max_w) if paragraphs else raw


def _programmatic_trim(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Könnyű tisztítás — csak abszolút felső határ felett agresszívebb; félmondat nélkül."""
    data = normalize_structured_outline(payload)

    data["title"] = _strip_trailing_verse_from_title(data["title"])
    if word_count(data["title"]) > LIMITS["title_words"]:
        data["title"] = " ".join(data["title"].split()[: LIMITS["title_words"]])

    if data["body_markdown"]:
        # A render a body elé fűzi a cím(+igehely)/scope_note sorát is —
        # a keretet ezekre a szavakra is le kell foglalni, különben a
        # végleges renderelt szöveg pár szóval túllépheti az abszolút
        # határt, még ha maga a body pontosan a limiten belül van is.
        reserved = (
            word_count(data["title"])
            + word_count(data["text_reference"])
            + word_count(data["scope_note"])
            + 5
        )
        budget = max(1, LIMITS["absolute_max_words"] - reserved)
        data["body_markdown"] = _clip_body_to_full_paragraphs(
            data["body_markdown"], budget
        )
        return normalize_structured_outline(data)

    data["focus_sentence"] = _clip_to_full_sentences(
        data["focus_sentence"], LIMITS["focus_words"]
    )
    data["introduction_direction"] = _clip_to_full_sentences(
        data["introduction_direction"], LIMITS["intro_words"]
    )
    data["conclusion_direction"] = _clip_to_full_sentences(
        data["conclusion_direction"], LIMITS["conclusion_words"]
    )
    data["scope_note"] = _clip_to_full_sentences(
        data["scope_note"], LIMITS["scope_note_words"]
    )
    trimmed_points: list[dict[str, Any]] = []
    for pt in data["points"][: LIMITS["max_points"]]:
        title = _strip_trailing_verse_from_title(_s(pt.get("title")))
        if word_count(title) > LIMITS["point_title_words"]:
            title = " ".join(title.split()[: LIMITS["point_title_words"]])
        layers: dict[str, str] = {}
        for key in POINT_LAYER_KEYS:
            cleaned = _s(pt.get(key))
            if "\n\n" in cleaned:
                cleaned = cleaned.split("\n\n")[0].strip()
            cleaned = _clip_to_full_sentences(cleaned, LIMITS["layer_max_words"])
            sents = _split_sentences(cleaned)[: LIMITS["layer_sentences"]]
            cleaned = " ".join(sents).strip()
            if cleaned and _looks_truncated_sentence(cleaned):
                first = _split_sentences(cleaned)
                cleaned = first[0] if first else cleaned
            layers[key] = cleaned
        trimmed_points.append(
            {
                "title": title,
                "verses": _s(pt.get("verses")),
                **layers,
            }
        )
    data["points"] = trimmed_points
    data["refinement_suggestions"] = []

    def _over() -> bool:
        return word_count(render_structured_outline(data)) > LIMITS["absolute_max_words"]

    # Csak 850+ szó esetén rövidíts programatikusan (AI compress utáni biztonsági háló).
    if _over():
        data["introduction_direction"] = _clip_to_full_sentences(
            data["introduction_direction"], 60
        )
        data["conclusion_direction"] = _clip_to_full_sentences(
            data["conclusion_direction"], 60
        )
        data["focus_sentence"] = _clip_to_full_sentences(data["focus_sentence"], 35)
    if _over() and len(data["points"]) > 3:
        data["points"] = data["points"][:3]
    return normalize_structured_outline(data)


_FATAL_OUTLINE_ISSUES = frozenset(
    {
        "over_absolute_max",
        "too_few_points",
        "missing_focus",
        "missing_conclusion",
        "missing_body",
        "full_sermon_like",
    }
)


def _structured_has_min_pulpit_shape(data: Mapping[str, Any]) -> bool:
    safe = normalize_structured_outline(data)
    body = safe.get("body_markdown")
    if body:
        return word_count(body) >= LIMITS["soft_floor_words"] // 2
    points = safe.get("points") if isinstance(safe.get("points"), list) else []
    return bool(
        _s(safe.get("focus_sentence"))
        and len(points) >= LIMITS["min_points"]
        and _s(safe.get("conclusion_direction"))
    )


def _rescue_structured_outline(
    structured: dict[str, Any] | None,
    *,
    bundle: Mapping[str, Any],
    seed_outline: Mapping[str, Any] | None,
    passage_text: Any,
    warnings: list[str],
    background_texts: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Szigorú AI-bukás után is próbáljunk menteni a MEGLÉVŐ AI-válaszból.

    Kizárólag a már megkapott AI-strukturát próbálja programozott
    tömörítéssel (`_programmatic_trim`) validálhatóvá tenni — ÚJ tartalmat
    nem generál, és nem esik vissza mechanikus, textus-daraboló
    heurisztikára. Ha a tömörített AI-válasz sem felel meg, a hívó felé
    `None`-t ad vissza — ez a `generate_sermon_outline()`-ban egyértelmű,
    retryable "validation_failed" hibát eredményez, nem áltartalmat."""
    from sermon_workshop_outline_ai import MISSING_PART, outline_to_readable_content

    stub_markers = (
        MISSING_PART.casefold(),
        "nincs kidolgozva",
        "ez a rész még",
        "placeholder",
    )

    def _looks_stub(data: Mapping[str, Any]) -> bool:
        try:
            text = outline_to_readable_content(
                structured_to_sermon_outline(data, seed=seed_outline or {})
            ).casefold()
        except Exception:  # noqa: BLE001
            text = json.dumps(dict(data), ensure_ascii=False).casefold()
        return any(m in text for m in stub_markers)

    if isinstance(structured, dict) and structured:
        trimmed = normalize_structured_outline(_programmatic_trim(structured))
        if _structured_has_min_pulpit_shape(trimmed) and not _looks_stub(trimmed):
            issues = validate_structured_outline(
                trimmed, passage_text=passage_text, background_texts=background_texts
            )
            hard = [
                i
                for i in issues
                if i not in SOFT_QUALITY_ISSUES and i not in ENRICHABLE_ISSUES
            ]
            wc = word_count(render_structured_outline(trimmed))
            if not hard and wc <= LIMITS["absolute_max_words"]:
                tip = "A vázlat automatikus formázással került mentésre."
                if tip not in warnings:
                    warnings.append(tip)
                for issue in issues:
                    soft_tip = f"Vázlat finomítható: {issue}"
                    if soft_tip not in warnings:
                        warnings.append(soft_tip)
                return trimmed, warnings

    # A tömörített AI-válasz sem érte el a minimális szószéki formát —
    # nincs mechanikus (nem-AI) mentőöv többé. A hívó "validation_failed"
    # hibát ad vissza, a korábbi mentett vázlat változatlanul megmarad.
    return None, warnings


def generate_sermon_outline(
    session_state: MutableMapping[str, Any] | Mapping[str, Any],
    *,
    mode: str = "standard",
    generate_fn: GenerateFn | None = None,
    force_overwrite: bool = False,
) -> OutlineGenerationResult:
    """Egyetlen vázlatgeneráló belépő.

    mode: \"quick\" | \"workshop\" | \"standard\" — csak kontextusdúsítás / forrásjelölés,
    NEM külön séma.
    """
    from sermon_workshop_outline_ai import (
        EMPTY_PROJECT_MESSAGE,
        assess_outline_readiness,
        build_outline_from_workshop,
        outline_has_content,
    )

    source_tag = "quick" if mode == "quick" else "workshop" if mode == "workshop" else ""
    if mode == "standard":
        source_tag = "workshop"

    if not isinstance(session_state, MutableMapping):
        session: MutableMapping[str, Any] = dict(session_state)
    else:
        session = session_state

    ensure_sermon_workshop_state(session)
    sw = session[SERMON_WORKSHOP_KEY]

    passage_ok, passage_msg = ensure_passage_text_for_outline(session)
    if not passage_ok:
        return OutlineGenerationResult(
            outline=normalize_sermon_outline(sw.get("sermon_outline")),
            ok=False,
            error_message=passage_msg or EMPTY_PROJECT_MESSAGE,
            error_kind="missing_passage",
            retryable=False,
            source=source_tag,
        )

    readiness = assess_outline_readiness(session, sermon_workshop=sw)
    if not readiness.ok:
        return OutlineGenerationResult(
            outline=normalize_sermon_outline(sw.get("sermon_outline")),
            ok=False,
            error_message=readiness.message or EMPTY_PROJECT_MESSAGE,
            error_kind="not_ready",
            retryable=False,
            source=source_tag,
        )

    existing = normalize_sermon_outline(sw.get("sermon_outline"))
    retained_outline_notice = (
        " A korábbi mentett vázlat változatlanul maradt, és továbbra is az látható."
        if outline_has_content(existing)
        else ""
    )
    manually_edited = bool(
        existing.get("manually_edited")
        or _s(sw.get("sermon_outline_status")) == "approved"
    )
    if outline_has_content(existing) and manually_edited and not force_overwrite:
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=(
                "A vázlat kézzel szerkesztve van. "
                "Frissítéshez erősítsd meg a felülírást."
            ),
            error_kind="manual_edit_conflict",
            retryable=False,
            source=_s(existing.get("source")) or source_tag,
            overwritten_manual_edit=False,
        )

    bundle = collect_outline_evidence(session, sermon_workshop=sw)
    ctx_hash = compute_context_hash(bundle)
    warnings: list[str] = []
    excluded_blocks = extract_outline_excluded_draft_blocks(bundle)
    if excluded_blocks:
        warnings.append(
            "Kimaradt a vázlatból (nincs jóváhagyva): "
            + ", ".join(excluded_blocks)
            + ". Hagyd jóvá a megfelelő fülön a „Jóváhagyom és átadom” gombbal."
        )
    stale_approved_blocks = extract_stale_approved_blocks(bundle)
    if stale_approved_blocks:
        warnings.append(
            "Ezeknél a blokkoknál megváltozott az igehely vagy a bibliai "
            "szöveg azóta, hogy a tartalom készült — ellenőrizd vagy "
            "frissítsd, mielőtt a vázlatmotor felhasználná őket: "
            + ", ".join(stale_approved_blocks) + "."
        )
    background_material = extract_outline_background_material(bundle)
    used_module_ids = [
        key for key in background_material if key in _APPROVAL_GATED_KEYS
    ]
    # Csak a valódi prózai háttéranyagot vetjük össze a kimenettel (nem a
    # listaszerű vázlatkosarat/döntéseket) — ezekben a szó szerinti átvétel
    # (pl. bemásolt kortörténet-bekezdés) a jellemző hiba.
    background_texts = [
        _s(background_material.get(k))
        for k in ("exegesis", "theology", "history", "original_text")
        if _s(background_material.get(k))
    ]
    compressed = False
    enriched = False
    # True, ha a `structured` egy AI-alapú compress/enrich/rescue javítás
    # eredménye — ilyenkor a megjelenített tartalomnak EZT kell tükröznie,
    # nem az eredeti, hibásnak jelzett nyers Markdown-választ.
    structured_was_repaired = False
    # Ha a Markdown-szintű javítás (lásd lejjebb) sikerül, ez tárolja a
    # javított, még mindig természetes prózájú Markdown-szöveget.
    repaired_markdown_content = ""
    # A legutóbb ismert, `structured`/`issues`-szal összhangban lévő Markdown-
    # szöveg — a compress ÉS az enrich blokk is frissíti/tovább örökíti, hogy
    # az eszkalációs kísérletek mindig a legjobb elérhető verzióból induljanak,
    # ne az eredeti, sokkal hibásabb szövegből.
    md_for_escalation = ""
    raw_wc = 0

    # A tisztított bundle néha eldobja a csonka/ellipsis szövegmintát; a generáláshoz
    # a nyers session passage továbbra is kell — a context_hash viszont stabil marad.
    raw_passage = _s(session.get("passage_text")) or _s(
        session.get("passage_text_input")
    )
    if raw_passage and not _s(bundle.get("passage_text")):
        bundle["passage_text"] = raw_passage
        keys = list(bundle.get("source_keys") or [])
        if "passage_text" not in keys:
            keys.append("passage_text")
        bundle["source_keys"] = keys

    # A system prompt maga végzi a mini-exegézist háttér nélkül —
    # ne hívjunk külön rapid_evidence AI-t (kerüljük a sablonos „textus mozgása” csomagot).
    markdown_content = ""

    seed = build_outline_from_workshop(session, sermon_workshop=sw)

    # EGYETLEN generálási szerződés (célarchitektúra-terv, 2. fázis, 2.
    # rész): vázlat KIZÁRÓLAG sikeres AI-szintézisből vagy a már meglévő,
    # érvényes mentett vázlatból származhat — mechanikus, versszakaszokra
    # daraboló "álvázlat" SOHA nem készül, sem generate_fn hiányában, sem
    # AI-hiba/érvénytelen AI-válasz esetén. A korábbi mentett vázlat (ha
    # van) mindig érintetlen marad — a hívó ezt kapja vissza `outline`-ként.
    if generate_fn is None:
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=AI_UNAVAILABLE_MESSAGE + retained_outline_notice,
            error_kind="ai_unavailable",
            retryable=False,
            warnings=warnings,
            source=source_tag,
        )

    structured, ai_warnings, raw_wc, markdown_content, ai_error_kind = (
        _ai_generate_structured(
            bundle, generate_fn=generate_fn, seed_outline=seed, mode=mode
        )
    )
    warnings.extend(ai_warnings)
    if structured is None:
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=(
                (ai_warnings[-1] if ai_warnings else INVALID_OUTLINE_MESSAGE)
                + retained_outline_notice
            ),
            error_kind=ai_error_kind or "ai_invalid_response",
            retryable=True,
            warnings=warnings,
            source=source_tag,
        )
    md_for_escalation = markdown_content

    passage_for_validation = bundle.get("passage_text") or ""

    def _hard_issues(items: list[str]) -> list[str]:
        return [
            i
            for i in items
            if i not in ENRICHABLE_ISSUES and i not in SOFT_QUALITY_ISSUES
        ]

    def _soft_final_issues(items: list[str]) -> list[str]:
        return [i for i in items if i in SOFT_QUALITY_ISSUES]

    def _needs_compress(items: list[str]) -> bool:
        return any(i in COMPRESS_TRIGGER_ISSUES for i in items)

    def _needs_enrich(items: list[str]) -> bool:
        return any(i in ENRICHABLE_ISSUES for i in items)

    # Validate BEFORE aggressive trim — trim must not hide a near-sermon.
    issues = validate_structured_outline(
        structured, passage_text=passage_for_validation, background_texts=background_texts
    )
    if raw_wc > LIMITS["absolute_max_words"] and "over_absolute_max" not in issues:
        issues = list(issues) + ["over_absolute_max"]

    # Tömörítés CSAK 850+ szó / prédikációjelleg esetén — nem minden hard hibánál.
    if _needs_compress(issues) and generate_fn is not None:
        # Elsőként Markdown-szintű javítás, ha van nyers Markdown-válasz —
        # ez megőrzi a természetes prózát (nem vált a mechanikus JSON-sémára)
        # és a modell most már a háttéranyagot is megkapja (rich=True), hogy
        # legyen miből ténylegesen szintetizálnia, ne csak a hibás vázlatot
        # kozmetikázza.
        # `md_for_escalation` a legutóbb ismert Markdown-szöveg (a függvény
        # elején az eredeti nyers Markdown-ra inicializálva) — itt frissül,
        # ha sikerül javítás.
        md_attempt_failed_outright = False
        if markdown_content:
            md_repaired, md_warn = _compress_markdown(
                markdown_content, bundle, issues=issues, generate_fn=generate_fn
            )
            warnings.extend(md_warn)
            if md_repaired is not None:
                # Maradunk a Markdown-vonalon akkor is, ha még nem tiszta —
                # az `issues`/`structured` innentől EBBŐL a szövegből
                # származik, hogy az esetleges eszkalációs próbálkozás
                # ugyanarra a szövegre hivatkozzon, amit a JELZETT PROBLÉMÁK
                # ténylegesen leír (JSON-fallback esetén ez az összhang
                # elveszne).
                md_for_escalation = md_repaired
                reparsed = markdown_outline_to_structured(md_repaired)
                reparsed_issues = validate_structured_outline(
                    reparsed, passage_text=passage_for_validation, background_texts=background_texts
                )
                structured = reparsed
                issues = reparsed_issues
                if not (_needs_compress(issues) or _hard_issues(issues)):
                    repaired_markdown_content = md_repaired
                    structured_was_repaired = True
            else:
                md_attempt_failed_outright = True
        # JSON-alapú fallback CSAK akkor, ha eleve nem volt Markdown-válasz
        # (legacy JSON mód), vagy a Markdown-javítás ténylegesen hibázott
        # (nem csak "még nem elég jó") — különben a Markdown-vonalon
        # maradunk, és az eszkaláció próbálja tovább javítani.
        if not repaired_markdown_content and (not markdown_content or md_attempt_failed_outright):
            repaired, c_warn = _compress_structured(
                structured, bundle, issues=issues, generate_fn=generate_fn
            )
            warnings.extend(c_warn)
            if repaired is not None:
                structured = repaired
                structured_was_repaired = True
                issues = validate_structured_outline(
                    structured, passage_text=passage_for_validation, background_texts=background_texts
                )
        compressed = True
        logger.info(
            "outline_after_compress schema=%s issues=%s words=%s",
            SCHEMA_VERSION,
            issues,
            word_count(render_structured_outline(structured)),
        )
        # Második, határozottabb Markdown-javítási kísérlet, mielőtt a
        # mechanikus vészmegoldásra esnénk — az első próbálkozás szintaktikailag
        # sikerülhetett, de a probléma (pl. verbatim_source_copy) a
        # re-validáció szerint mégis megmaradhatott.
        if (_needs_compress(issues) or _hard_issues(issues)) and md_for_escalation:
            md_repaired2, md_warn2 = _compress_markdown(
                md_for_escalation,
                bundle,
                issues=issues,
                generate_fn=generate_fn,
                escalate=True,
            )
            warnings.extend(md_warn2)
            if md_repaired2 is not None:
                reparsed2 = markdown_outline_to_structured(md_repaired2)
                reparsed2_issues = validate_structured_outline(
                    reparsed2, passage_text=passage_for_validation, background_texts=background_texts
                )
                if not (_needs_compress(reparsed2_issues) or _hard_issues(reparsed2_issues)):
                    structured = reparsed2
                    repaired_markdown_content = md_repaired2
                    structured_was_repaired = True
                    issues = reparsed2_issues
                    logger.info(
                        "outline_compress_escalation_success schema=%s", SCHEMA_VERSION
                    )
        if _needs_compress(issues) or _hard_issues(issues):
            rendered_wc = word_count(render_structured_outline(structured))
            logger.info(
                "outline_reject_after_compress schema=%s issues=%s words=%s",
                SCHEMA_VERSION,
                issues,
                rendered_wc,
            )
            rescued, warnings = _rescue_structured_outline(
                structured,
                bundle=bundle,
                seed_outline=seed,
                passage_text=passage_for_validation,
                warnings=warnings,
                background_texts=background_texts,
            )
            if rescued is None:
                return OutlineGenerationResult(
                    outline=existing,
                    ok=False,
                    error_message=INVALID_OUTLINE_MESSAGE + retained_outline_notice,
                    error_kind="validation_failed",
                    retryable=True,
                    warnings=warnings,
                    validation_issues=issues,
                    source=source_tag,
                    compressed=True,
                    enriched=enriched,
                    raw_word_count=raw_wc,
                    rendered_word_count=rendered_wc,
                )
            structured = rescued
            compressed = True
            structured_was_repaired = True
            issues = validate_structured_outline(
                structured, passage_text=passage_for_validation, background_texts=background_texts
            )

    # Tartalmi kiegészítés CSAK 350 alatt / hiányzó-sovány réteg esetén.
    if (
        generate_fn is not None
        and not _needs_compress(issues)
        and _needs_enrich(issues)
    ):
        # Ugyanaz a minta, mint a tömörítésnél: elsőként Markdown-szintű
        # kiegészítés (természetes próza), csak utána JSON-alapú fallback —
        # `md_for_escalation` a compress blokkból örökölt legutóbbi ismert
        # Markdown-szöveg (vagy az eredeti, ha compress nem futott).
        md_e_attempt_failed_outright = False
        if md_for_escalation:
            md_deepened, md_e_warn = _enrich_markdown(
                md_for_escalation, bundle, issues=issues, generate_fn=generate_fn
            )
            warnings.extend(md_e_warn)
            if md_deepened is not None:
                md_for_escalation = md_deepened
                reparsed_e = markdown_outline_to_structured(md_deepened)
                reparsed_e_issues = validate_structured_outline(
                    reparsed_e, passage_text=passage_for_validation, background_texts=background_texts
                )
                reparsed_e_leftover = [
                    i
                    for i in reparsed_e_issues
                    if i
                    in {
                        "missing_textual_insight",
                        "missing_theological_emphasis",
                        "missing_listener_movement",
                        "truncated_sentence",
                    }
                ]
                structured = reparsed_e
                issues = reparsed_e_issues
                if not (_hard_issues(reparsed_e_issues) or reparsed_e_leftover):
                    repaired_markdown_content = md_deepened
                    structured_was_repaired = True
            else:
                md_e_attempt_failed_outright = True
        enriched = True
        if not structured_was_repaired and (
            not markdown_content or md_e_attempt_failed_outright
        ):
            deepened, e_warn = _enrich_structured(
                structured, bundle, issues=issues, generate_fn=generate_fn
            )
            warnings.extend(e_warn)
            if deepened is not None:
                structured = deepened
                structured_was_repaired = True
                issues = validate_structured_outline(
                    structured, passage_text=passage_for_validation, background_texts=background_texts
                )
        logger.info(
            "outline_after_enrich schema=%s issues=%s words=%s",
            SCHEMA_VERSION,
            issues,
            word_count(render_structured_outline(structured)),
        )
        leftover_hard = [
            i
            for i in issues
            if i
            in {
                "missing_textual_insight",
                "missing_theological_emphasis",
                "missing_listener_movement",
                "truncated_sentence",
            }
        ]
        # Második, határozottabb Markdown-kiegészítési kísérlet, mielőtt a
        # mechanikus vészmegoldásra esnénk.
        if (_hard_issues(issues) or leftover_hard) and md_for_escalation:
            md_deepened2, md_e_warn2 = _enrich_markdown(
                md_for_escalation,
                bundle,
                issues=issues,
                generate_fn=generate_fn,
                escalate=True,
            )
            warnings.extend(md_e_warn2)
            if md_deepened2 is not None:
                reparsed_e2 = markdown_outline_to_structured(md_deepened2)
                reparsed_e2_issues = validate_structured_outline(
                    reparsed_e2, passage_text=passage_for_validation, background_texts=background_texts
                )
                leftover_hard2 = [
                    i
                    for i in reparsed_e2_issues
                    if i
                    in {
                        "missing_textual_insight",
                        "missing_theological_emphasis",
                        "missing_listener_movement",
                        "truncated_sentence",
                    }
                ]
                if not (_hard_issues(reparsed_e2_issues) or leftover_hard2):
                    structured = reparsed_e2
                    repaired_markdown_content = md_deepened2
                    structured_was_repaired = True
                    issues = reparsed_e2_issues
                    leftover_hard = leftover_hard2
                    logger.info(
                        "outline_enrich_escalation_success schema=%s", SCHEMA_VERSION
                    )
        if _hard_issues(issues) or leftover_hard:
            rendered_wc = word_count(render_structured_outline(structured))
            logger.info(
                "outline_reject_after_enrich schema=%s issues=%s words=%s",
                SCHEMA_VERSION,
                issues,
                rendered_wc,
            )
            rescued, warnings = _rescue_structured_outline(
                structured,
                bundle=bundle,
                seed_outline=seed,
                passage_text=passage_for_validation,
                warnings=warnings,
                background_texts=background_texts,
            )
            if rescued is None:
                return OutlineGenerationResult(
                    outline=existing,
                    ok=False,
                    error_message=INVALID_OUTLINE_MESSAGE + retained_outline_notice,
                    error_kind="validation_failed",
                    retryable=True,
                    warnings=warnings,
                    validation_issues=issues,
                    source=source_tag,
                    compressed=compressed,
                    enriched=True,
                    raw_word_count=raw_wc,
                    rendered_word_count=rendered_wc,
                )
            structured = rescued
            enriched = True
            structured_was_repaired = True
            issues = validate_structured_outline(
                structured, passage_text=passage_for_validation, background_texts=background_texts
            )

    structured = _programmatic_trim(structured)
    issues = validate_structured_outline(
        structured, passage_text=passage_for_validation, background_texts=background_texts
    )

    rendered_wc = word_count(render_structured_outline(structured))

    # 2C.1: a beszédegység-SZÁM valódi kimeneti szerződés, nem puszta
    # minőségi figyelmeztetés. too_few_speech_units/too_many_speech_units
    # ENRICHABLE (a fenti compress/enrich hurok, amely idáig már lefutott,
    # megkapta az esélyt a javításra) — de ha a javítás(ok) után is
    # fennmaradnak, blokkoló, retryable validációs hibává válnak. A
    # programozott tömörítés/mentőöv (`_rescue_structured_outline`) nem
    # tudna beszédegységeket szétbontani vagy összevonni, ezért erre a
    # konkrét hibaosztályra nem is próbálkozunk vele — egyenesen
    # strukturált hibát adunk, a korábbi mentett vázlat érintetlen marad.
    speech_unit_count_issues = [
        i for i in issues if i in ("too_few_speech_units", "too_many_speech_units")
    ]
    if speech_unit_count_issues:
        logger.info(
            "outline_reject_speech_unit_count schema=%s issues=%s rendered_words=%s",
            SCHEMA_VERSION,
            speech_unit_count_issues,
            rendered_wc,
        )
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=SPEECH_UNIT_COUNT_INVALID_MESSAGE + retained_outline_notice,
            error_kind="validation_failed",
            retryable=True,
            warnings=warnings,
            validation_issues=issues,
            source=source_tag,
            compressed=compressed,
            enriched=enriched,
            raw_word_count=raw_wc,
            rendered_word_count=rendered_wc,
        )

    # Soft quality flags (too_thin / under_target) → warning, keep if otherwise valid
    for soft in _soft_final_issues(issues):
        tip = f"Vázlat minőség: {soft}"
        if tip not in warnings:
            warnings.append(tip)

    # Hard reject: struktúra-/forma-hibák. Enrichable hossz/réteg soft warning a végén.
    post_hard = [
        i
        for i in issues
        if i not in SOFT_QUALITY_ISSUES and i not in ENRICHABLE_ISSUES
    ]
    for softish in issues:
        if softish in ENRICHABLE_ISSUES and softish not in SOFT_QUALITY_ISSUES:
            tip = f"Vázlat minőség: {softish}"
            if tip not in warnings:
                warnings.append(tip)
    if generate_fn is not None and post_hard:
        logger.info(
            "outline_reject schema=%s issues=%s rendered_words=%s raw_words=%s",
            SCHEMA_VERSION,
            issues,
            rendered_wc,
            raw_wc,
        )
        rescued, warnings = _rescue_structured_outline(
            structured,
            bundle=bundle,
            seed_outline=seed,
            passage_text=passage_for_validation,
            warnings=warnings,
            background_texts=background_texts,
        )
        if rescued is None:
            return OutlineGenerationResult(
                outline=existing,
                ok=False,
                error_message=INVALID_OUTLINE_MESSAGE + retained_outline_notice,
                error_kind="validation_failed",
                retryable=True,
                warnings=warnings,
                validation_issues=issues,
                source=source_tag,
                compressed=compressed,
                enriched=enriched,
                raw_word_count=raw_wc,
                rendered_word_count=rendered_wc,
            )
        structured = rescued
        structured_was_repaired = True
        issues = validate_structured_outline(
            structured, passage_text=passage_for_validation, background_texts=background_texts
        )
        rendered_wc = word_count(render_structured_outline(structured))
        for soft in _soft_final_issues(issues):
            tip = f"Vázlat minőség: {soft}"
            if tip not in warnings:
                warnings.append(tip)
        for softish in issues:
            if softish in ENRICHABLE_ISSUES and softish not in SOFT_QUALITY_ISSUES:
                tip = f"Vázlat minőség: {softish}"
                if tip not in warnings:
                    warnings.append(tip)

    # (A korábbi "offline heurisztika" ág itt megszűnt — generate_fn ezen a
    # ponton már garantáltan nem None, mert a függvény korábban, az AI-hívás
    # előtt visszatér, ha nincs generate_fn. Ld. AI_UNAVAILABLE_MESSAGE.)

    outline = structured_to_sermon_outline(
        structured,
        seed=seed,
        source=source_tag or "workshop",
        context_hash=ctx_hash,
    )
    # Markdown generálás: alapesetben a nyers Markdown a kanonikus megjelenített
    # tartalom. Ha a validáció hibát jelzett és sikerült Markdown-szintű
    # javítás (természetes próza marad), azt mutatjuk. Ha csak a mechanikus
    # JSON-alapú compress/enrich/rescue sikerült, az a második választás —
    # különben a validáció/javítás láthatatlan marad, és a hibás nyers szöveg
    # jelenik meg változatlanul.
    if repaired_markdown_content:
        outline["content"] = repaired_markdown_content
    elif structured_was_repaired:
        outline["content"] = render_structured_outline(structured)
    elif _s(markdown_content):
        outline["content"] = _s(markdown_content)
    outline["source_fingerprint"] = ctx_hash
    outline["used_module_ids"] = used_module_ids
    outline["source_sections"] = list(bundle.get("source_keys") or [])
    if not outline_has_content(outline):
        return OutlineGenerationResult(
            outline=existing,
            ok=False,
            error_message=EMPTY_PROJECT_MESSAGE,
            error_kind="empty_result",
            retryable=True,
            warnings=warnings,
            validation_issues=issues,
            source=source_tag,
            compressed=compressed,
            enriched=enriched,
            raw_word_count=raw_wc,
        )

    final_wc = word_count(outline.get("content") or render_structured_outline(structured))
    logger.info(
        "outline_ok schema=%s source=%s rendered_words=%s compressed=%s enriched=%s",
        SCHEMA_VERSION,
        source_tag,
        final_wc,
        compressed,
        enriched,
    )
    return OutlineGenerationResult(
        outline=outline,
        ok=True,
        warnings=warnings,
        validation_issues=[],
        source=source_tag or "workshop",
        overwritten_manual_edit=bool(manually_edited and force_overwrite),
        compressed=compressed,
        enriched=enriched,
        raw_word_count=raw_wc,
        rendered_word_count=final_wc,
    )


__all__ = [
    "AI_UNAVAILABLE_MESSAGE",
    "COMPRESS_INSTRUCTION",
    "COMPRESS_TRIGGER_ISSUES",
    "ENRICH_INSTRUCTION",
    "ENRICHABLE_ISSUES",
    "ENGINE_VERSION",
    "FORBIDDEN_HEADINGS",
    "FORBIDDEN_PAYLOAD_KEYS",
    "INVALID_OUTLINE_MESSAGE",
    "LEGACY_SCHEMA_VERSIONS",
    "LIMITS",
    "OUTLINE_MAX_OUTPUT_TOKENS",
    "OUTLINE_RESPONSE_SCHEMA",
    "OUTLINE_SYSTEM_PROMPT",
    "RAPID_EVIDENCE_SYSTEM_PROMPT",
    "REFRESH_NOTICE",
    "SCHEMA_REFRESH_NOTICE",
    "SCHEMA_VERSION",
    "SOFT_QUALITY_ISSUES",
    "OutlineGenerationResult",
    "build_outline_user_prompt",
    "clear_outline_generation_caches",
    "collect_outline_evidence",
    "compute_context_hash",
    "ensure_passage_text_for_outline",
    "extract_outline_background_material",
    "extract_outline_core_passage_context",
    "extract_verse_numbers",
    "generate_sermon_outline",
    "markdown_outline_to_structured",
    "mirror_outline_to_session_strings",
    "normalize_structured_outline",
    "outline_needs_refresh",
    "render_structured_outline",
    "scope_note_uses_unloaded_verse",
    "sermon_outline_to_structured",
    "structured_to_sermon_outline",
    "validate_structured_outline",
    "word_count",
]
