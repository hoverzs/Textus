"""Textus fő gondolata — MI háttérréteg (javaslat + értékelés).

Önálló modul: nem módosítja a befagyasztott elemző promptokat
(exegézis, kortörténet, teológia, eredeti szöveg, illusztráció, aktualizálás).
A Gemini-hívást a hívó által átadott `generate_fn`-nel végzi
(általában az app.py `generate_text` függvénye).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence
from llm_text_utils import extract_json_object_lenient, is_llm_error_text

# ---------------------------------------------------------------------------
# Konstansok
# ---------------------------------------------------------------------------

MISSING = "nincs adat"

TAB_LABEL_SUGGEST = "Textus fő gondolat — javaslat"
TAB_LABEL_ASSESS = "Textus fő gondolat — értékelés"

# Exegetikai feladat: alacsonyabb kreativitás (session temperature override).
DEFAULT_TEMPERATURE = 0.15

# Szelektív kontextus hosszlimitek (karakter)
_LIMITS = {
    "passage_text": 4000,
    "approved_insights": 3500,
    "exegesis": 3200,
    "original_text": 2000,
    "theology": 2500,
    "overview": 1500,
    "historical_context": 1200,
    "user_focus": 800,
    "occasion": 400,
    "user_main_idea": 1200,
}

MAIN_IDEA_SYSTEM_BUNDLE = """\
Te a TEXTUS homiletikai segéd szöveghű exegetikai asszisztense vagy.
Csak a felhasználói feladatban megadott anyagból dolgozz.
Ne egészítsd ki a hiányzó bibliai szöveget saját emlékezetből.
Válaszod KIZÁRÓLAG érvényes JSON legyen — semmi más szöveg, markdown vagy magyarázat.
Minden string szabályosan escape-elt legyen; az objektumban ne legyen záró vessző.\
"""

_ASSESSMENT_PREFIXES = (
    "Megfelelő —",
    "Részben megfelelő —",
    "Javítandó —",
    "Nem megítélhető —",
)

GenerateFn = Callable[..., str]

# LOCAL QA FINAL FUNCTIONAL POLISH (2026-08-21) — a "Textus fő gondolata"
# hívás korábban sem `response_schema`-t, sem dedikált token-budgetet nem
# kapott (a generikus 4096-os alapértékre esett vissza). Valós Gemini-
# méréssel (1Móz 32,23-32, teljes exegézis/eredeti szöveg/teológia/
# kortörténet kontextussal): suggest thoughts+candidates = 2740-4001,
# assess = 3476 — a 4096-os plafonhoz veszélyesen közel, élesben
# ténylegesen `finishReason=MAX_TOKENS`-hez (csonka -> érvénytelen JSON)
# vezetett. A `response_schema` a strukturált kimenetet Gemini oldalon
# kényszeríti ki (ugyanaz a módszer, mint a tervrajznál/hétpontos ívnél).
MAIN_IDEA_SUGGEST_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommended": {"type": "string"},
        "expanded_summary": {"type": "string"},
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "reasoning_summary": {"type": "string"},
        "textual_basis": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "recommended",
        "expanded_summary",
        "alternatives",
        "reasoning_summary",
        "textual_basis",
        "warnings",
        "missing_information",
    ],
}

MAIN_IDEA_ASSESS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "assessment": {
            "type": "object",
            "properties": {
                "text_fidelity": {"type": "string"},
                "clarity": {"type": "string"},
                "unity": {"type": "string"},
                "theological_accuracy": {"type": "string"},
                "scope": {"type": "string"},
                "statement_quality": {"type": "string"},
                "application_confusion": {"type": "string"},
            },
            "required": [
                "text_fidelity",
                "clarity",
                "unity",
                "theological_accuracy",
                "scope",
                "statement_quality",
                "application_confusion",
            ],
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "revision_priorities": {"type": "array", "items": {"type": "string"}},
        "revised_version": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "assessment",
        "strengths",
        "revision_priorities",
        "revised_version",
        "warnings",
    ],
}


def _diagnose_invalid_json_response(raw: Any) -> str:
    """Determinisztikus, durva diagnózis — kizárólag fejlesztői/debug
    célra (sosem a végfelhasználónak mutatott hibaüzenetbe kerül).
    Ugyanaz a logika, mint a blueprint/arc moduloknál (modul-független
    másolat, a bevett konvenció szerint)."""
    if _is_api_error_text(raw):
        return "not_json:empty_or_api_error"
    text = str(raw or "").strip()
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


# ---------------------------------------------------------------------------
# Adatstruktúrák
# ---------------------------------------------------------------------------


@dataclass
class MainIdeaSuggestionResult:
    """Javaslatkészítő strukturált kimenet."""

    recommended: str = ""
    expanded_summary: str = ""
    alternatives: list[str] = field(default_factory=list)
    reasoning_summary: str = ""
    textual_basis: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MainIdeaAssessmentFields:
    """Értékelési szempontok (rövid szövegek minősítő előtaggal)."""

    text_fidelity: str = ""
    clarity: str = ""
    unity: str = ""
    theological_accuracy: str = ""
    scope: str = ""
    statement_quality: str = ""
    application_confusion: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class MainIdeaAssessmentResult:
    """Értékelő strukturált kimenet."""

    assessment: MainIdeaAssessmentFields = field(
        default_factory=MainIdeaAssessmentFields
    )
    strengths: list[str] = field(default_factory=list)
    revision_priorities: list[str] = field(default_factory=list)
    revised_version: str = ""
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Segédek — szöveg / jelenlét
# ---------------------------------------------------------------------------


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _is_present(value: Any) -> bool:
    text = _as_text(value)
    if not text:
        return False
    low = text.casefold()
    return low not in {
        MISSING,
        "nincs",
        "n/a",
        "na",
        "nem releváns",
        "nem releváns ehhez a kéréshez",
        "-",
        "—",
    }


def _display(value: Any, *, max_chars: int | None = None) -> str:
    text = _as_text(value)
    if not _is_present(text):
        return MISSING
    if max_chars is not None and len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _format_insights(insights: Any, *, max_chars: int) -> str:
    if insights is None:
        return MISSING
    if isinstance(insights, str):
        return _display(insights, max_chars=max_chars)
    if isinstance(insights, Sequence) and not isinstance(insights, (str, bytes)):
        lines: list[str] = []
        for item in insights:
            if isinstance(item, Mapping):
                if item.get("approved") is False:
                    continue
                cat = _as_text(item.get("category"))
                content = _as_text(item.get("content"))
                source = _as_text(item.get("source"))
                if not content:
                    continue
                prefix = f"[{cat}] " if cat else ""
                suffix = f" (forrás: {source})" if source else ""
                lines.append(f"- {prefix}{content}{suffix}")
            else:
                t = _as_text(item)
                if t:
                    lines.append(f"- {t}")
        if not lines:
            return MISSING
        joined = "\n".join(lines)
        return _display(joined, max_chars=max_chars)
    return _display(insights, max_chars=max_chars)


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos is_llm_error_text (llm_text_utils.py; azonosság: tests/test_llm_text_utils.py).
_is_api_error_text = is_llm_error_text


# ---------------------------------------------------------------------------
# Kontextusépítés
# ---------------------------------------------------------------------------


def build_main_idea_context(
    *,
    passage: str = "",
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    approved_insights: Any = None,
    exegesis: str = "",
    original_text: str = "",
    theology: str = "",
    overview: str = "",
    historical_context: str = "",
    user_main_idea: str = "",
    include_historical_context: bool = False,
) -> dict[str, str]:
    """Szelektív, címkézett kontextus-dict a promptkitöltéshez.

    Nem módosítja a session állapotot; csak olvas és levág.
    """
    hist = (
        _display(historical_context, max_chars=_LIMITS["historical_context"])
        if include_historical_context
        else "nem releváns ehhez a kéréshez"
    )
    if include_historical_context and not _is_present(historical_context):
        hist = MISSING

    return {
        "passage": _display(passage, max_chars=200) if _is_present(passage) else MISSING,
        "passage_text": _display(passage_text, max_chars=_LIMITS["passage_text"]),
        "occasion": _display(occasion, max_chars=_LIMITS["occasion"]),
        "user_focus": _display(user_focus, max_chars=_LIMITS["user_focus"]),
        "approved_insights": _format_insights(
            approved_insights, max_chars=_LIMITS["approved_insights"]
        ),
        "exegesis": _display(exegesis, max_chars=_LIMITS["exegesis"]),
        "original_text": _display(original_text, max_chars=_LIMITS["original_text"]),
        "theology": _display(theology, max_chars=_LIMITS["theology"]),
        "overview": _display(overview, max_chars=_LIMITS["overview"]),
        "historical_context": hist,
        "user_main_idea": _display(
            user_main_idea, max_chars=_LIMITS["user_main_idea"]
        ),
    }


# Javaslatkészítéshez elfogadott minimális források
# (a passage_text hiánya önmagában nem blokkol).
_SUGGEST_SOURCE_KEYS: tuple[tuple[str, str], ...] = (
    ("passage_text", "bibliai szöveg (passage_text)"),
    ("approved_insights", "jóváhagyott felismerések"),
    ("exegesis", "exegézis"),
    ("original_text", "eredeti szöveg elemzése"),
    ("theology", "teológia"),
    ("overview", "áttekintés"),
)

_PASSAGE_TEXT_MISSING_WARNING = (
    "A teljes bibliai szöveg (passage_text) nem állt közvetlenül "
    "rendelkezésre; a javaslat az elemzési anyagból készült, ezért "
    "ne tulajdoníts neki nagyobb bizonyosságot."
)
_PASSAGE_TEXT_MISSING_LABEL = "bibliai szöveg (passage_text)"


def _analysis_sources_present(ctx: Mapping[str, str]) -> list[str]:
    """Mely elemzési források vannak ténylegesen jelen (értékeléshez is)."""
    keys = (
        *_SUGGEST_SOURCE_KEYS,
        ("historical_context", "kortörténet"),
    )
    present: list[str] = []
    for key, label in keys:
        val = ctx.get(key, MISSING)
        if key == "historical_context" and val.casefold().startswith("nem releváns"):
            continue
        if _is_present(val):
            present.append(label)
    return present


def _suggest_sources_present(ctx: Mapping[str, str]) -> list[str]:
    """Javaslatkészítéshez használható források (passage_text opcionális)."""
    present: list[str] = []
    for key, label in _SUGGEST_SOURCE_KEYS:
        if _is_present(ctx.get(key, MISSING)):
            present.append(label)
    return present


def _missing_analysis_labels(ctx: Mapping[str, str]) -> list[str]:
    missing: list[str] = []
    for key, label in _SUGGEST_SOURCE_KEYS:
        if not _is_present(ctx.get(key, MISSING)):
            missing.append(label)
    return missing


def has_sufficient_suggest_material(ctx: Mapping[str, str]) -> bool:
    """Van-e elegendő anyag felelős javaslat API-híváshoz.

    Minimális feltétel: nem üres `passage`, ÉS legalább egy érdemi forrás:
    `passage_text`, `approved_insights`, `exegesis`, `original_text`,
    `theology` vagy `overview`. A `passage_text` hiánya önmagában nem
    blokkol, ha van más elemzési anyag.
    """
    if not _is_present(ctx.get("passage", MISSING)):
        return False
    return bool(_suggest_sources_present(ctx))


def _ensure_passage_text_absence_notes(
    result: MainIdeaSuggestionResult,
    ctx: Mapping[str, str],
) -> MainIdeaSuggestionResult:
    """Ha nincs passage_text, de van javaslat: figyelmeztetés + hiányjelzés."""
    if not result.ok:
        return result
    if _is_present(ctx.get("passage_text", MISSING)):
        return result
    # Csak akkor, ha tényleg elemzési anyagra támaszkodtunk / van eredmény
    if not (result.recommended or result.alternatives):
        # Üres javaslatnál is jelezhető a hiány a missing listában
        if _PASSAGE_TEXT_MISSING_LABEL not in result.missing_information:
            result.missing_information = list(result.missing_information) + [
                _PASSAGE_TEXT_MISSING_LABEL
            ]
        return result
    if _PASSAGE_TEXT_MISSING_WARNING not in result.warnings:
        result.warnings = list(result.warnings) + [_PASSAGE_TEXT_MISSING_WARNING]
    if _PASSAGE_TEXT_MISSING_LABEL not in result.missing_information:
        result.missing_information = list(result.missing_information) + [
            _PASSAGE_TEXT_MISSING_LABEL
        ]
    return result

# ---------------------------------------------------------------------------
# Promptépítés (a TEXTUS_MAIN_IDEA_PROMPTS_DRAFT.md elvei szerint)
# ---------------------------------------------------------------------------


def _fill_placeholders(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", value)
    return out


_SUGGEST_PROMPT_TEMPLATE = """\
Feladatod: a megadott bibliai szakasz TEXTUS FŐ GONDOLATÁNAK megfogalmazása.

Ez NEM az igehirdetés fő gondolata, NEM prédikációs cím, NEM alkalmazás, NEM felszólítás a hallgatóhoz (kivéve, ha maga a textus egyértelműen felszólító jellegű és ezt a megadott anyag is alátámasztja).

## Fogalom

A textus fő gondolata:
- egyetlen világos, teljes állító mondat;
- megmondja, miről beszél a szöveg, és mit állít róla;
- a textusból és a rendelkezésedre bocsátott elemzési anyagból következik;
- nem általános teológiai közhely;
- nem szlogen, nem cím, nem vázlatpont-lista.

## Igehely és bibliai szöveg

- Az {{passage}} csak igehely-megjelölés. Önmagában NEM tekinthető rendelkezésre bocsátott bibliai szövegnek.
- A rendelkezésre bocsátott bibliai szöveg kizárólag az {{passage_text}} mezőben van (ha van).
- NE egészítsd ki a hiányzó bibliai szöveget saját emlékezetből, betanított versidézettel vagy „ismert szöveg” pótlásával.
- A {{passage_text}} hiánya ÖNMAGÁBAN NEM blokkolja a javaslatot, ha van érdemi elemzési anyag (jóváhagyott felismerések, exegézis, eredeti szöveg, teológia vagy áttekintés).
- Csak akkor jelezd elégtelen adatként a helyzetet, ha sem a bibliai szöveg, sem érdemi elemzési anyag nem áll rendelkezésre (lásd: elégtelen adat).

## Források súlya

Elsődleges (bármelyik elegendő lehet javaslatindításhoz, ha érdemi):
1) a rendelkezésre bocsátott bibliai szöveg ({{passage_text}}), ha van;
2) a jóváhagyott felismerések;
3) az exegézis és a szövegszerkezet.

Fontos kiegészítő (önállóan is elegendőek lehetnek, ha érdemi tartalmúak):
4) eredeti szöveg elemzése;
5) teológiai elemzés;
6) áttekintés.

Csak akkor vedd figyelembe, ha a jelentéshez ténylegesen szükséges:
7) kortörténeti háttér.

Az alkalom ({{occasion}}) és a felhasználói szempont ({{user_focus}}) NEM írhatja felül a textust vagy az elemzési anyagot. Legfeljebb háttérinformáció.

A {{user_main_idea}} csak nem kötelező vázlat. NEM tekintélyi forrás. NE horonyzd le a megfogalmazást hozzá; ne másold át stilisztikailag, és ne tekintsd „helyes válasznak”.

TILOS forrásként használni (még ha máshol léteznének is): illusztrációk, aktualizálás, énekajánló, prédikációs vázlat.

## Abszolút tilalmak

- Ne találj ki görög vagy héber nyelvi adatot.
- Ne találj ki kortörténeti információt.
- Ne hivatkozz nem megadott kommentárra, szakirodalomra vagy „általános exegetikai konszenzusra” forrásként.
- Ne moralizálj; ne írj alkalmazást; ne írj prédikációs címet.
- Ne alakítsd automatikusan felszólítássá a kijelentő vagy narratív szöveget.
- Ne erőltess olyan Krisztus-kapcsolatot, amelyet a textus vagy a megadott kánoni/teológiai anyag nem támaszt alá.
- Ne gyárts fellengzős, homályos vagy szlogenszerű nyelvet.
- Ne adj belső gondolatmenetet, lépésenkénti érvelést vagy hosszú elemzést. Csak rövid, felhasználónak szánt indoklást írj a reasoning_summary mezőben.
- Ha egy adatforrás értéke „nincs adat”, üres, vagy hiányzik: NE találj ki helyette semmit.

## Elégtelen adat (kötelező szabály)

Csak akkor nincs elegendő adat felelős főgondolat-javaslathoz, ha:
- a {{passage_text}} NEM áll rendelkezésre, ÉS
- az összes használható elemzési forrás is üres vagy hiányzik
  (jóváhagyott felismerések, exegézis, eredeti szöveg elemzése, teológia, áttekintés).

Ilyenkor:
- "recommended" legyen üres string: "";
- "expanded_summary" legyen üres string: "";
- "alternatives" legyen üres lista: [];
- "textual_basis" legyen üres lista: [];
- a problémát a "reasoning_summary", "warnings" és "missing_information" mezők jelezzék.
Ilyenkor NE találj ki „valószínű” fő gondolatot.

A {{passage_text}} vagy a jóváhagyott felismerések hiánya ÖNMAGÁBAN NEM elégtelen adat.
Ha van legalább egy érdemi elemzési forrás (exegézis, eredeti szöveg, teológia, áttekintés vagy jóváhagyott felismerés), készíts recommended javaslatot.

Ha nincs {{passage_text}}, de van elegendő elemzési anyag:
- készíts recommended javaslatot az elemzési anyag alapján;
- a warnings mezőben jelezd, hogy a teljes bibliai szöveg nem állt közvetlenül rendelkezésre;
- a missing_information mezőben szerepelhet a bibliai szöveg hiánya;
- ne kelts nagyobb bizonyosságot, mint amit az elemzési anyag megenged;
- NE találj ki bibliai idézetet, görög/héber adatot vagy történeti hátteret.

## Hibajelző mezők

- missing_information: CSAK a hiányzó vagy rendelkezésre nem bocsátott adatok (pl. nincs passage_text; nincs exegézis). A hiány jelzése NEM jelenti automatikusan, hogy a recommended üres legyen.
- warnings: bizonytalanságok, ellentmondások, többféle megalapozott értelmezés, a következtetés korlátai, vagy a közvetlen bibliai szöveg hiánya — NEM a puszta hiánylista megismétlése.

## Alternatívák szabálya

- Legfeljebb két alternatíva.
- Minden alternatíva egy-egy teljes mondat legyen.
- Az alternatívák NE ugyanazon mondat stilisztikai változatai legyenek, hanem valódi értelmezési hangsúlyeltérést mutassanak.
- Ha nincs két megalapozott alternatíva, az alternatives lista legyen rövidebb vagy üres: [].
- Az alternatives elemei továbbra is egy-egy mondatos főgondolatok; NE készíts hozzájuk külön 3–4 mondatos kifejtést.

## expanded_summary szabályai

A recommended továbbra is EGYETLEN teljes állító mondat.
A többmondatos magyarázat KIZÁRÓLAG az expanded_summary mezőbe kerüljön.

Az expanded_summary:
- 3–4 rövid, összefüggő mondat;
- fejtse ki a textus belső mozgását;
- mutassa meg, hogyan kapcsolódnak össze a szakasz fő elemei;
- nevezze meg Isten cselekvését és az emberi választ, ha a textus ezt megalapozza;
- NE legyen prédikációs alkalmazás;
- NE szólítsa meg közvetlenül a hallgatót;
- NE írjon minivázlatot vagy pontlistát;
- NE ismételje szó szerint a recommended mondatot;
- NE tartalmazzon új, a forrásanyagban nem szereplő adatot;
- elégtelen recommended esetén legyen üres string: "".

## textual_basis forrásjelölés

Minden textual_basis elem EZZEL a forrástípussal kezdődjön (pontosan így), majd kötőjel és rövid tartalom:

- „Jóváhagyott felismerés — …”
- „Exegézis — …”
- „Eredeti szöveg — …”
- „Teológia — …”
- „Áttekintés — …”
- „Kortörténet — …”
- „Bibliai szöveg — …” (csak ha a {{passage_text}} ténylegesen rendelkezésre áll)

Ne kerüljön bele olyan forrásjelölés, idézet vagy versszám, amelyet a bemeneti anyag nem támaszt alá. Legfeljebb négy elem.

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

Alkalom / felhasználási cél (nem írhatja felül a textust):
{{occasion}}

Felhasználói szempont (nem írhatja felül a textust; nem tekintélyi forrás):
{{user_focus}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis (szerkezet és állítás):
{{exegesis}}

Eredeti szöveg elemzése:
{{original_text}}

Teológiai elemzés:
{{theology}}

Áttekintés:
{{overview}}

Kortörténeti háttér (csak ha releváns; különben „nincs adat” / „nem releváns”):
{{historical_context}}

Felhasználói főgondolat-vázlat (opcionális; NEM tekintélyi forrás; ne horonyzz le hozzá):
{{user_main_idea}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot, kódblokkot, magyarázó bevezetőt vagy utószót.
- Minden mező kötelező.
- Ha nincs elem egy listában, üres listát adj: [].
- Ha van recommended, az egyetlen mondat legyen; elégtelen adatnál "".
- Az expanded_summary 3–4 rövid mondat legyen, vagy elégtelen adatnál "".
- A reasoning_summary rövid legyen (legfeljebb néhány mondat).
- Minden JSON-string legyen szabályosan escape-elt, érvényes JSON-érték.
- Az objektumban ne legyen záró vessző (trailing comma).
- A JSON-kulcsok pontosan az alábbi angol nevek legyenek.

Séma:

{
  "recommended": "string",
  "expanded_summary": "string",
  "alternatives": ["string"],
  "reasoning_summary": "string",
  "textual_basis": ["string"],
  "warnings": ["string"],
  "missing_information": ["string"]
}
"""

_ASSESS_PROMPT_TEMPLATE = """\
Feladatod: a felhasználó által megfogalmazott TEXTUS FŐ GONDOLAT értékelése.

Ez NEM az igehirdetés fő gondolatának bírálata, és NEM automatikus átírás. A felhasználó mondatát NE írd felül automatikusan. Adj szakmai értékelést és — ha felelősen lehetséges — egyetlen átdolgozott JAVASLATOT; a döntés a felhasználóé marad.

## Fogalom — mire kell emlékeztetned magad

A textus fő gondolata:
- egyetlen világos, teljes állítás;
- megmondja, miről beszél a szöveg, és mit állít róla;
- a textusból és a megadott elemzési anyagból következik;
- nem prédikációs cím;
- nem alkalmazás;
- nem moralizálás;
- nem általános teológiai közhely;
- nem automatikus felszólítás (kivéve, ha a textus maga az, és az anyag ezt alátámasztja).

## Igehely és bibliai szöveg

- Az {{passage}} csak igehely-megjelölés. Önmagában NEM tekinthető rendelkezésre bocsátott bibliai szövegnek.
- A rendelkezésre bocsátott bibliai szöveg kizárólag az {{passage_text}} mezőben van (ha van).
- NE egészítsd ki a hiányzó bibliai szöveget saját emlékezetből.
- Ha a bibliai szöveg és az elemzési anyag együtt sem elegendő megalapozott döntéshez, jelezd hiányként / figyelmeztetésként.

## Források súlya

Elsődleges: rendelkezésre bocsátott bibliai szöveg (ha van), jóváhagyott felismerések, exegézis/szerkezet.
Fontos kiegészítő: eredeti szöveg, teológia, áttekintés.
Csak releváns esetben: kortörténet.
TILOS forrás: illusztrációk, aktualizálás, énekajánló, prédikációs vázlat.

Az alkalom ({{occasion}}) és a felhasználói szempont ({{user_focus}}) NEM írhatja felül a textust vagy az elemzési anyagot.

## Abszolút tilalmak

- Ne találj ki görög/héber adatot, kortörténetet, kommentárt.
- Ne hivatkozz nem megadott szakirodalomra.
- Ne moralizálj; ne írj prédikációs címet helyette „javításként”, ha az elkerülhető.
- Ne erőltess megalapozatlan Krisztus-kapcsolatot.
- Ne adj százalékos pontszámot, csillagot, 1–10 skálát vagy mesterségesen precíz számszerű értékelést.
- Ne adj belső gondolatmenetet vagy hosszú érvelést.
- Ha egy adatforrás „nincs adat” / üres: ne találj ki semmit.
- Ha a {{user_main_idea}} üres: NE próbáld kitalálni a felhasználó mondatát. Jelezd a hiányt; az assessment mezőkben használd a „Nem megítélhető —” minősítést, ahol indokolt; a revised_version legyen "".
- Az átdolgozott javaslat (revised_version) NE tartalmazzon olyan új teológiai, nyelvi vagy történeti állítást, amely nincs jelen a megadott anyagban.
- Ha nincs elegendő elemzési alap a felelős átdolgozáshoz: revised_version legyen üres string: "".
- Ha van revised_version, az egyetlen világos mondat legyen, és világosan értendő JAVASLATKÉNT — nem automatikus csere.

## Hibajelző mezők

- warnings: bizonytalanságok, ellentmondások, többféle megalapozott értelmezés, a következtetés korlátai, illetve az értékelés korlátai (pl. üres user_main_idea).

## Értékelési szempontok (assessment)

Minden assessment mező rövid szövege PONTOSAN a következő minősítések egyikével kezdődjön, majd szóköz, kötőjel, szóköz, majd rövid szakmai magyarázat:

- „Megfelelő — …”
- „Részben megfelelő — …”
- „Javítandó — …”
- „Nem megítélhető — …”

Mezők:

- text_fidelity: mennyire hű a megadott textushoz és anyaghoz;
- clarity: világos-e a mondat;
- unity: egyetlen állítás-e, vagy több gondolat keveredik;
- theological_accuracy: teológiailag pontos-e a rendelkezésre álló anyaghoz képest;
- scope: nem túl tág / nem túl szűk-e;
- statement_quality: valóban állítás-e (nem cím, nem szlogen, nem kérdés-halmaz);
- application_confusion: keveri-e az alkalmazással / hallgatói felszólítással.

## Kimeneti korlátok

- strengths: legfeljebb három erősség;
- revision_priorities: legfeljebb három elsődleges javítási szempont;
- revised_version: egy mondat (javaslat), vagy "" ha nem felelős az átdolgozás / üres a user_main_idea;
- warnings: lista; ha nincs, [].

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

Alkalom / felhasználási cél (nem írhatja felül a textust):
{{occasion}}

Felhasználói szempont (nem írhatja felül a textust):
{{user_focus}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis:
{{exegesis}}

Eredeti szöveg elemzése:
{{original_text}}

Teológiai elemzés:
{{theology}}

Áttekintés:
{{overview}}

Kortörténeti háttér:
{{historical_context}}

A felhasználó saját fő gondolata (értékelendő mondat; ha üres, ne találj ki semmit):
{{user_main_idea}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot, kódblokkot, bevezetőt vagy utószót.
- Minden mező kötelező.
- Ha nincs elem egy listában, üres listát adj: [].
- Minden JSON-string legyen szabályosan escape-elt, érvényes JSON-érték.
- Az objektumban ne legyen záró vessző (trailing comma).
- A JSON-kulcsok pontosan az alábbi angol nevek legyenek.

Séma:

{
  "assessment": {
    "text_fidelity": "string",
    "clarity": "string",
    "unity": "string",
    "theological_accuracy": "string",
    "scope": "string",
    "statement_quality": "string",
    "application_confusion": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_version": "string",
  "warnings": ["string"]
}
"""


def build_main_idea_suggest_prompt(ctx: Mapping[str, str]) -> str:
    """Teljes javaslatkészítő user-prompt a kitöltött kontextusból."""
    return _fill_placeholders(_SUGGEST_PROMPT_TEMPLATE, ctx)


def build_main_idea_assess_prompt(ctx: Mapping[str, str]) -> str:
    """Teljes értékelő user-prompt a kitöltött kontextusból."""
    return _fill_placeholders(_ASSESS_PROMPT_TEMPLATE, ctx)


# ---------------------------------------------------------------------------
# JSON kinyerés és validáció
# ---------------------------------------------------------------------------


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos extract_json_object_lenient (llm_text_utils.py; azonosság:
# tests/test_llm_json_extractors.py).
extract_json_object = extract_json_object_lenient


def _as_str_list(value: Any, *, max_items: int | None = None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        out = [s] if s else []
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        out = [_as_text(x) for x in value if _as_text(x)]
    else:
        s = _as_text(value)
        out = [s] if s else []
    if max_items is not None:
        out = out[:max_items]
    return out


def _normalize_assessment_text(value: Any, *, empty_reason: str) -> str:
    text = _as_text(value)
    if not text:
        return f"Nem megítélhető — {empty_reason}"
    for prefix in _ASSESSMENT_PREFIXES:
        if text.startswith(prefix):
            return text
    # Ha a modell elfelejtette az előtagot, ne dobjuk el a tartalmat.
    return f"Részben megfelelő — {text}"


def fallback_suggestion(
    *,
    reasoning: str,
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> MainIdeaSuggestionResult:
    return MainIdeaSuggestionResult(
        recommended="",
        expanded_summary="",
        alternatives=[],
        reasoning_summary=reasoning,
        textual_basis=[],
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def fallback_assessment(
    *,
    reason: str,
    warnings: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> MainIdeaAssessmentResult:
    tag = f"Nem megítélhető — {reason}"
    return MainIdeaAssessmentResult(
        assessment=MainIdeaAssessmentFields(
            text_fidelity=tag,
            clarity=tag,
            unity=tag,
            theological_accuracy=tag,
            scope=tag,
            statement_quality=tag,
            application_confusion=tag,
        ),
        strengths=[],
        revision_priorities=[],
        revised_version="",
        warnings=list(warnings or [reason]),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def parse_main_idea_suggestions(
    raw: str,
    *,
    force_empty_on_insufficient: bool = False,
) -> MainIdeaSuggestionResult:
    """Javaslat JSON parse + sémaellenőrzés; hibánál biztonságos fallback."""
    if _is_api_error_text(raw):
        return fallback_suggestion(
            reasoning="A modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            missing=[],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )

    obj = extract_json_object(raw)
    if obj is None:
        return fallback_suggestion(
            reasoning="A válasz nem dolgozható fel érvényes JSON-ként.",
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            missing=[],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )

    recommended = _as_text(obj.get("recommended"))
    expanded_summary = _as_text(obj.get("expanded_summary"))
    alternatives = _as_str_list(obj.get("alternatives"), max_items=2)
    reasoning = _as_text(obj.get("reasoning_summary"))
    textual_basis = _as_str_list(obj.get("textual_basis"), max_items=4)
    warnings = _as_str_list(obj.get("warnings"))
    missing = _as_str_list(obj.get("missing_information"))

    if force_empty_on_insufficient:
        recommended = ""
        expanded_summary = ""
        alternatives = []
        textual_basis = []

    if not recommended:
        expanded_summary = ""

    if not reasoning:
        reasoning = (
            "A modell nem adott indoklást."
            if recommended
            else "Nincs elegendő megalapozott javaslat a rendelkezésre álló anyagból."
        )

    return MainIdeaSuggestionResult(
        recommended=recommended,
        expanded_summary=expanded_summary,
        alternatives=alternatives,
        reasoning_summary=reasoning,
        textual_basis=textual_basis,
        warnings=warnings,
        missing_information=missing,
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


def parse_main_idea_assessment(raw: str) -> MainIdeaAssessmentResult:
    """Értékelés JSON parse + sémaellenőrzés; hibánál biztonságos fallback."""
    if _is_api_error_text(raw):
        return fallback_assessment(
            reason="A modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )

    obj = extract_json_object(raw)
    if obj is None:
        return fallback_assessment(
            reason="A válasz nem dolgozható fel érvényes JSON-ként.",
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )

    assessment_raw = obj.get("assessment")
    if not isinstance(assessment_raw, dict):
        assessment_raw = {}

    empty_reason = "hiányos értékelési mező"
    fields = MainIdeaAssessmentFields(
        text_fidelity=_normalize_assessment_text(
            assessment_raw.get("text_fidelity"), empty_reason=empty_reason
        ),
        clarity=_normalize_assessment_text(
            assessment_raw.get("clarity"), empty_reason=empty_reason
        ),
        unity=_normalize_assessment_text(
            assessment_raw.get("unity"), empty_reason=empty_reason
        ),
        theological_accuracy=_normalize_assessment_text(
            assessment_raw.get("theological_accuracy"), empty_reason=empty_reason
        ),
        scope=_normalize_assessment_text(
            assessment_raw.get("scope"), empty_reason=empty_reason
        ),
        statement_quality=_normalize_assessment_text(
            assessment_raw.get("statement_quality"), empty_reason=empty_reason
        ),
        application_confusion=_normalize_assessment_text(
            assessment_raw.get("application_confusion"), empty_reason=empty_reason
        ),
    )

    return MainIdeaAssessmentResult(
        assessment=fields,
        strengths=_as_str_list(obj.get("strengths"), max_items=3),
        revision_priorities=_as_str_list(obj.get("revision_priorities"), max_items=3),
        revised_version=_as_text(obj.get("revised_version")),
        warnings=_as_str_list(obj.get("warnings")),
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


# ---------------------------------------------------------------------------
# Gemini-hívás wrapper (meglévő generate_text mintára)
# ---------------------------------------------------------------------------


def _call_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    tab_label: str,
    temperature: float | None = DEFAULT_TEMPERATURE,
    response_schema: dict[str, Any] | None = None,
) -> str:
    """generate_fn hívása; opcionális session temperature felülírással.

    `response_schema` megadásakor JSON-mód (`response_mime_type`) is
    aktiválódik, és a csonkulás-jelző magyar mondat hozzáfűzése kikapcsolt
    (`truncation_notice_mode="never"`) — ez MINDIG érvénytelenné tenné a
    JSON-t egy csonka válasz esetén is, ugyanaz a minta, mint a tervrajz/
    hétpontos ív hívásoknál."""
    prev_temp = None
    touched_temp = False
    if temperature is not None:
        try:
            import streamlit as st

            prev_temp = st.session_state.get("temperature")
            st.session_state["temperature"] = float(temperature)
            touched_temp = True
        except Exception:
            touched_temp = False
    try:
        extra: dict[str, Any] = {}
        if response_schema is not None:
            extra["response_mime_type"] = "application/json"
            extra["response_schema"] = response_schema
            extra["truncation_notice_mode"] = "never"
        return generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=tab_label,
            use_cache=False,
            system_bundle=MAIN_IDEA_SYSTEM_BUNDLE,
            include_brevity_directive=False,
            **extra,
        )
    finally:
        if touched_temp:
            try:
                import streamlit as st

                if prev_temp is None:
                    st.session_state.pop("temperature", None)
                else:
                    st.session_state["temperature"] = prev_temp
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Publikus API
# ---------------------------------------------------------------------------


def suggest_text_main_idea(
    *,
    passage: str,
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    approved_insights: Any = None,
    exegesis: str = "",
    original_text: str = "",
    theology: str = "",
    overview: str = "",
    historical_context: str = "",
    user_main_idea: str = "",
    include_historical_context: bool = False,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> MainIdeaSuggestionResult:
    """Textus fő gondolat javaslatkészítés.

    `generate_fn`: tipikusan az app.py `generate_text` függvénye.
    Ha nincs elegendő anyag és `skip_api_if_insufficient=True`, API-hívás
    nélkül ad vissza üres recommended / alternatives eredményt.
    """
    ctx = build_main_idea_context(
        passage=passage,
        passage_text=passage_text,
        occasion=occasion,
        user_focus=user_focus,
        approved_insights=approved_insights,
        exegesis=exegesis,
        original_text=original_text,
        theology=theology,
        overview=overview,
        historical_context=historical_context,
        user_main_idea=user_main_idea,
        include_historical_context=include_historical_context,
    )

    if not _is_present(ctx["passage"]):
        return fallback_suggestion(
            reasoning="Nincs megadva igehely-megjelölés; javaslat nem indítható.",
            warnings=["Az igehely (passage) hiányzik."],
            missing=["igehely-megjelölés (passage)"],
            error_message="Hiányzó igehely.",
            ok=False,
        )

    missing = _missing_analysis_labels(ctx)
    if skip_api_if_insufficient and not has_sufficient_suggest_material(ctx):
        return fallback_suggestion(
            reasoning=(
                "Nincs elegendő rendelkezésre bocsátott bibliai szöveg vagy "
                "elemzési anyag felelős főgondolat-javaslathoz. "
                "A modell nem egészíti ki a hiányt saját emlékezetből."
            ),
            warnings=[
                "Elégtelen adat: felelős javaslat helyett üres recommended/alternatives."
            ],
            missing=missing or ["elemzési anyag"],
            ok=True,
        )

    if generate_fn is None:
        return fallback_suggestion(
            reasoning="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )

    prompt = build_main_idea_suggest_prompt(ctx)
    # LOCAL QA FINAL FUNCTIONAL POLISH — LEGFELJEBB 1 kontrollált retry,
    # KIZÁRÓLAG akkor, ha a válasz JSON-KINYERÉSI szinten hibás (csonkulás,
    # próza a JSON körül). Szemantikai tartalom esetén NEM ismételünk — ezt
    # a modul saját, megengedő parsere (`parse_main_idea_suggestions`)
    # amúgy is hiánytalanul kezeli hiányzó/üres mezőkkel.
    current_prompt = prompt
    raw = ""
    for attempt in range(2):
        try:
            raw = _call_generate(
                generate_fn,
                current_prompt,
                tab_label=TAB_LABEL_SUGGEST,
                temperature=temperature,
                response_schema=MAIN_IDEA_SUGGEST_RESPONSE_SCHEMA,
            )
        except Exception as exc:  # noqa: BLE001 — UI ne dőljön el
            return fallback_suggestion(
                reasoning="A javaslatkészítés közben váratlan hiba történt.",
                warnings=[f"Váratlan hiba: {exc}"],
                missing=missing,
                error_message=str(exc),
                ok=False,
            )
        extraction_failed = (
            not _is_api_error_text(raw) and extract_json_object(raw) is None
        )
        if attempt == 0 and extraction_failed:
            current_prompt = (
                prompt
                + "\n\n==================================================\n"
                "KORREKCIÓ\n"
                "==================================================\n\n"
                "Az előző válaszod NEM volt érvényes, önmagában feldolgozható "
                "JSON-objektum (pl. csonka volt, vagy szöveg állt a JSON előtt/"
                "után). Add meg ÚJRA a TELJES választ, KIZÁRÓLAG egyetlen, "
                "jólformált JSON-objektumként — semmilyen bevezető vagy záró "
                "szöveg, markdown-jelölés nélkül."
            )
            continue
        break

    return _ensure_passage_text_absence_notes(
        parse_main_idea_suggestions(raw or ""),
        ctx,
    )


def assess_user_main_idea(
    *,
    passage: str,
    user_main_idea: str,
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    approved_insights: Any = None,
    exegesis: str = "",
    original_text: str = "",
    theology: str = "",
    overview: str = "",
    historical_context: str = "",
    include_historical_context: bool = False,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> MainIdeaAssessmentResult:
    """Felhasználói főgondolat-megfogalmazás értékelése.

    Üres `user_main_idea` esetén nincs kitalálás / átdolgozás — helyi fallback.
    """
    if not _is_present(user_main_idea):
        return fallback_assessment(
            reason="A felhasználói fő gondolat üres; nincs mit értékelni.",
            warnings=["Üres user_main_idea — nincs kitalálás és nincs átdolgozás."],
            ok=True,
        )

    ctx = build_main_idea_context(
        passage=passage,
        passage_text=passage_text,
        occasion=occasion,
        user_focus=user_focus,
        approved_insights=approved_insights,
        exegesis=exegesis,
        original_text=original_text,
        theology=theology,
        overview=overview,
        historical_context=historical_context,
        user_main_idea=user_main_idea,
        include_historical_context=include_historical_context,
    )

    if not _is_present(ctx["passage"]):
        return fallback_assessment(
            reason="Nincs megadva igehely-megjelölés; az értékelés korlátozott.",
            warnings=["Az igehely (passage) hiányzik."],
            error_message="Hiányzó igehely.",
            ok=False,
        )

    if generate_fn is None:
        return fallback_assessment(
            reason="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            error_message="Hiányzó generate_fn.",
            ok=False,
        )

    # Ha nincs elemzési alap: még mindig hívható az API (figyelmeztetésekkel),
    # de a prompt előírja az üres revised_version-t. Helyi rövid út opcionális:
    if not _analysis_sources_present(ctx):
        # Felelős átdolgozás nélkül is értékelhető a mondat formai szempontból,
        # de inkább API-t hívunk ha van generate_fn — a prompt kezeli.
        pass

    prompt = build_main_idea_assess_prompt(ctx)
    current_prompt = prompt
    raw = ""
    for attempt in range(2):
        try:
            raw = _call_generate(
                generate_fn,
                current_prompt,
                tab_label=TAB_LABEL_ASSESS,
                temperature=temperature,
                response_schema=MAIN_IDEA_ASSESS_RESPONSE_SCHEMA,
            )
        except Exception as exc:  # noqa: BLE001
            return fallback_assessment(
                reason="Az értékelés közben váratlan hiba történt.",
                warnings=[f"Váratlan hiba: {exc}"],
                error_message=str(exc),
                ok=False,
            )
        extraction_failed = (
            not _is_api_error_text(raw) and extract_json_object(raw) is None
        )
        if attempt == 0 and extraction_failed:
            current_prompt = (
                prompt
                + "\n\n==================================================\n"
                "KORREKCIÓ\n"
                "==================================================\n\n"
                "Az előző válaszod NEM volt érvényes, önmagában feldolgozható "
                "JSON-objektum (pl. csonka volt, vagy szöveg állt a JSON előtt/"
                "után). Add meg ÚJRA a TELJES választ, KIZÁRÓLAG egyetlen, "
                "jólformált JSON-objektumként — semmilyen bevezető vagy záró "
                "szöveg, markdown-jelölés nélkül."
            )
            continue
        break

    result = parse_main_idea_assessment(raw or "")
    # Extra biztonság: ha semmi elemzési forrás, ne hagyjunk „új” átdolgozást
    # felelőtlenül (a parse után is üríthető).
    if result.ok and not _analysis_sources_present(ctx):
        result.revised_version = ""
        if "Nincs elegendő elemzési alap a felelős átdolgozáshoz." not in result.warnings:
            result.warnings = list(result.warnings) + [
                "Nincs elegendő elemzési alap a felelős átdolgozáshoz."
            ]
    return result


def build_context_from_session(
    session_state: Mapping[str, Any],
    *,
    user_main_idea: str | None = None,
    passage_text: str = "",
    include_historical_context: bool = False,
) -> dict[str, str]:
    """Kényelmi helper: session / project mezőkből kontextus (későbbi UI-bekötéshez)."""
    tw = session_state.get("text_workshop")
    insights: Any = None
    idea = ""
    if isinstance(tw, Mapping):
        insights = tw.get("approved_insights")
        idea = _as_text(tw.get("text_main_idea"))

    passage = (
        _as_text(session_state.get("last_igehely"))
        or _as_text(session_state.get("igehely_input"))
    )
    return build_main_idea_context(
        passage=passage,
        passage_text=passage_text,
        occasion=_as_text(session_state.get("last_alkalom"))
        or _as_text(session_state.get("alkalom_input")),
        user_focus=_as_text(session_state.get("last_sajat"))
        or _as_text(session_state.get("sajat_input")),
        approved_insights=insights,
        exegesis=_as_text(session_state.get("exegesis")),
        original_text=_as_text(session_state.get("original_text")),
        theology=_as_text(session_state.get("theology")),
        overview=_as_text(session_state.get("overview")),
        historical_context=_as_text(session_state.get("history")),
        user_main_idea=user_main_idea if user_main_idea is not None else idea,
        include_historical_context=include_historical_context,
    )


# ---------------------------------------------------------------------------
# Smoke / önellenőrzés (API nélkül)
# ---------------------------------------------------------------------------


def _self_check() -> list[str]:
    """Egyszerű regressziós ellenőrzések; hibák listája (üres = OK)."""
    errors: list[str] = []

    # 1) Elégtelen adat → üres javaslat, nincs generate_fn hívás
    called = {"n": 0}

    def _should_not_run(*_a, **_k):
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    r = suggest_text_main_idea(
        passage="Jn 3,16–21",
        generate_fn=_should_not_run,
    )
    if called["n"] != 0:
        errors.append("insufficient suggest still called API")
    if r.recommended or r.alternatives:
        errors.append("insufficient suggest should be empty")
    if not r.missing_information:
        errors.append("insufficient suggest missing_information empty")

    # 2) Üres user_main_idea → nincs API, revised=""
    called["n"] = 0
    a = assess_user_main_idea(
        passage="Jn 3,16",
        user_main_idea="",
        generate_fn=_should_not_run,
    )
    if called["n"] != 0:
        errors.append("empty assess still called API")
    if a.revised_version:
        errors.append("empty assess revised_version should be empty")
    if not a.assessment.text_fidelity.startswith("Nem megítélhető —"):
        errors.append("empty assess prefix wrong")

    # 3) JSON fence parse
    raw = (
        '```json\n{"recommended":"A.","expanded_summary":"Egy. Kettő. Három.",'
        '"alternatives":["B."],"reasoning_summary":"Ok.",'
        '"textual_basis":["Exegézis — x"],"warnings":[],"missing_information":[]}\n```'
    )
    p = parse_main_idea_suggestions(raw)
    if not p.ok or p.recommended != "A." or p.alternatives != ["B."]:
        errors.append("suggest parse failed")
    if p.expanded_summary != "Egy. Kettő. Három.":
        errors.append("expanded_summary parse failed")

    # 3b) Régi JSON expanded_summary nélkül → üres string
    legacy = parse_main_idea_suggestions(
        '{"recommended":"Régi.","alternatives":[],"reasoning_summary":"r",'
        '"textual_basis":[],"warnings":[],"missing_information":[]}'
    )
    if legacy.expanded_summary != "":
        errors.append("legacy suggest should default expanded_summary to empty")

    # 4) Hibás JSON fallback
    bad = parse_main_idea_suggestions("ez nem json")
    if bad.ok or bad.recommended:
        errors.append("bad json should fallback")
    if bad.expanded_summary:
        errors.append("bad json expanded_summary should be empty")

    # 5) Assessment prefix normalizálás
    raw_a = json.dumps(
        {
            "assessment": {
                "text_fidelity": "Megfelelő — hű",
                "clarity": "világos",
                "unity": "Megfelelő — egy",
                "theological_accuracy": "Megfelelő — ok",
                "scope": "Részben megfelelő — tág",
                "statement_quality": "Javítandó — cím",
                "application_confusion": "Megfelelő — nem kever",
            },
            "strengths": ["s1"],
            "revision_priorities": ["p1", "p2", "p3", "p4"],
            "revised_version": "Átdolgozott mondat.",
            "warnings": [],
        },
        ensure_ascii=False,
    )
    pa = parse_main_idea_assessment(raw_a)
    if not pa.assessment.clarity.startswith("Részben megfelelő —"):
        errors.append("assessment prefix normalize failed")
    if len(pa.revision_priorities) != 3:
        errors.append("revision_priorities not capped at 3")

    # 6) Prompt tartalmazza a passage_text helyőrző kitöltését
    ctx = build_main_idea_context(
        passage="Róm 8,1",
        passage_text="Nincs tehát most már semmi elítélés...",
        exegesis="A szakasz a szabadításról beszél.",
    )
    prompt = build_main_idea_suggest_prompt(ctx)
    if "Nincs tehát most már semmi elítélés" not in prompt:
        errors.append("passage_text missing from suggest prompt")
    if "{{passage" in prompt:
        errors.append("unfilled placeholder in suggest prompt")

    # 7) Prompt: passage_text hiánya önmagában ne legyen blokkoló
    if "ÖNMAGÁBAN NEM" not in prompt and "önmagában nem" not in prompt.casefold():
        # A kitöltött prompt a sablont használja; a sablont ellenőrizzük
        if "ÖNMAGÁBAN NEM" not in _SUGGEST_PROMPT_TEMPLATE:
            errors.append("suggest prompt missing non-blocking passage_text rule")

    def _mock_suggest_json(recommended: str = "Javasolt fő gondolat.") -> str:
        return json.dumps(
            {
                "recommended": recommended,
                "expanded_summary": (
                    "A szakasz belső mozgása a sötétségből a világosság felé tart. "
                    "Isten cselekvése a Fiú ajándékozásában válik láthatóvá. "
                    "Az emberi válasz a hit, amennyiben a textus ezt megalapozza."
                ),
                "alternatives": [],
                "reasoning_summary": "Az elemzési anyag alapján.",
                "textual_basis": ["Exegézis — állítás"],
                "warnings": [],
                "missing_information": [],
            },
            ensure_ascii=False,
        )

    # A) passage + exegesis, passage_text nélkül → API hívás + figyelmeztetés
    called["n"] = 0

    def _gen_a(*_a, **_k):
        called["n"] += 1
        return _mock_suggest_json("Isten szeretete világosságba hív.")

    ra = suggest_text_main_idea(
        passage="Jn 3,16–21",
        exegesis=(
            "A szakasz a világosság és a sötétség ellentétén keresztül "
            "mutatja be Isten szeretetét és az ítélet elkerülését."
        ),
        generate_fn=_gen_a,
    )
    if called["n"] != 1:
        errors.append("A: passage+exegesis should call API")
    if not ra.recommended:
        errors.append("A: expected recommended from exegesis")
    if not ra.expanded_summary:
        errors.append("A: expected expanded_summary")
    if not any("passage_text" in w or "bibliai szöveg" in w for w in ra.warnings):
        errors.append("A: expected passage_text warning")
    if _PASSAGE_TEXT_MISSING_LABEL not in ra.missing_information:
        errors.append("A: expected passage_text in missing_information")

    # Prompt séma tartalmazza az expanded_summary-t
    if '"expanded_summary"' not in _SUGGEST_PROMPT_TEMPLATE:
        errors.append("suggest prompt schema missing expanded_summary")

    # B) passage + theology + overview → javaslat
    called["n"] = 0

    def _gen_b(*_a, **_k):
        called["n"] += 1
        return _mock_suggest_json("A kegyelem megelőzi az emberi választ.")

    rb = suggest_text_main_idea(
        passage="Ef 2,1–10",
        theology="Az üdvösség kegyelemből, hit által van; nem cselekedetekből.",
        overview="Pál a kegyelem elsőbbségét hangsúlyozza a volt holtak életre kelésében.",
        generate_fn=_gen_b,
    )
    if called["n"] != 1 or not rb.recommended:
        errors.append("B: theology+overview should yield suggestion")

    # C) csak passage → ne legyen javaslat / API
    called["n"] = 0
    rc = suggest_text_main_idea(
        passage="Jn 3,16",
        generate_fn=_should_not_run,
    )
    if called["n"] != 0 or rc.recommended or rc.alternatives:
        errors.append("C: passage-only must stay empty")

    # D) passage + approved_insights → javaslat
    called["n"] = 0

    def _gen_d(*_a, **_k):
        called["n"] += 1
        return _mock_suggest_json("Isten szeretete ajándékozza a Fiút.")

    rd = suggest_text_main_idea(
        passage="Jn 3,16",
        approved_insights=[
            {
                "category": "Állítás",
                "content": "Isten szeretete a Fiú elküldésében válik láthatóvá.",
                "approved": True,
            }
        ],
        generate_fn=_gen_d,
    )
    if called["n"] != 1 or not rd.recommended:
        errors.append("D: approved_insights should yield suggestion")

    # E) passage + passage_text → javaslat
    called["n"] = 0

    def _gen_e(*_a, **_k):
        called["n"] += 1
        return _mock_suggest_json(
            "Aki hisz a Fiúban, nem megy a kárhozatra, hanem örök élete van."
        )

    re_ = suggest_text_main_idea(
        passage="Jn 3,16",
        passage_text=(
            "Mert úgy szerette Isten a világot, hogy egyszülött Fiát adta, "
            "hogy aki hisz őbenne, el ne vesszen, hanem örök élete legyen."
        ),
        generate_fn=_gen_e,
    )
    if called["n"] != 1 or not re_.recommended:
        errors.append("E: passage_text should yield suggestion")
    if any("nem állt közvetlenül" in w for w in re_.warnings):
        errors.append("E: should not warn about missing passage_text")

    # has_sufficient: historical_context alone is NOT enough
    ctx_hist = build_main_idea_context(
        passage="Jn 3,16",
        historical_context="Első századi jeruzsálemi háttér.",
        include_historical_context=True,
    )
    if has_sufficient_suggest_material(ctx_hist):
        errors.append("historical_context alone should not be sufficient")

    # user_main_idea / text_main_idea not required
    ctx_ex = build_main_idea_context(
        passage="Jn 3,16",
        exegesis="Érdemi exegézis a szerkezetről és az állításról.",
        user_main_idea="",
    )
    if not has_sufficient_suggest_material(ctx_ex):
        errors.append("exegesis without user_main_idea should be sufficient")

    return errors

if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("SELF-CHECK FAILED:")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("textus_main_idea_ai self-check OK")
