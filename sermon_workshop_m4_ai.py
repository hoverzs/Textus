"""Igehirdetési műhely M4 — MI háttérréteg (4 művelet).

Önálló modul: nem importál app.py / sermon_workshop_ui.py fájlból.
A Gemini-hívást a hívó által átadott `generate_fn`-nel végzi
(általában az app.py `generate_text` függvénye).
A promptok a felülvizsgált SERMON_WORKSHOP_M4_PROMPTS_DRAFT.md szerintiek.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence
from llm_text_utils import (
    call_generate_with_session_temperature,
    extract_json_object_lenient,
    is_llm_error_text,
)

# ---------------------------------------------------------------------------
# Konstansok
# ---------------------------------------------------------------------------

MISSING = "nincs adat"

TAB_SUGGEST_SERMON = "Igehirdetés fő gondolat — javaslat"
TAB_ASSESS_SERMON = "Igehirdetés fő gondolat — értékelés"
TAB_SUGGEST_HC = "Emberi helyzet — javaslat"
TAB_ASSESS_HC = "Emberi helyzet — értékelés"

DEFAULT_TEMPERATURE = 0.15

_LIMITS = {
    "passage_text": 4000,
    "approved_insights": 3500,
    "exegesis": 3200,
    "theology": 2500,
    "user_focus": 800,
    "occasion": 400,
    "text_main_idea": 1200,
    "sermon_main_idea": 1200,
    "human_condition_block": 2500,
}

M4_SYSTEM_BUNDLE = """\
Te a TEXTUS homiletikai segéd szöveghű exegetikai-homiletikai asszisztense vagy.
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

_HC_FIELD_KEYS = (
    "human_condition",
    "false_response",
    "human_need",
    "divine_action",
    "grace_response",
)

# UI / adatmodell mezőnév ↔ prompt JSON mező
_HC_UI_TO_PROMPT = {
    "condition": "human_condition",
    "false_response": "false_response",
    "human_need": "human_need",
    "divine_action": "divine_action",
    "grace_response": "grace_response",
}
_HC_PROMPT_TO_UI = {v: k for k, v in _HC_UI_TO_PROMPT.items()}

GenerateFn = Callable[..., str]


# ---------------------------------------------------------------------------
# Adatstruktúrák
# ---------------------------------------------------------------------------


@dataclass
class SermonMainIdeaSuggestionResult:
    recommended: str = ""
    expanded_summary: str = ""
    alternatives: list[str] = field(default_factory=list)
    reasoning_summary: str = ""
    textual_and_homiletical_basis: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SermonMainIdeaAssessmentFields:
    text_fidelity: str = ""
    hearability: str = ""
    unity: str = ""
    theological_accuracy: str = ""
    listener_relevance: str = ""
    title_or_slogan_confusion: str = ""
    application_confusion: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class SermonMainIdeaAssessmentResult:
    assessment: SermonMainIdeaAssessmentFields = field(
        default_factory=SermonMainIdeaAssessmentFields
    )
    strengths: list[str] = field(default_factory=list)
    revision_priorities: list[str] = field(default_factory=list)
    revised_version: str = ""
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HumanConditionSuggestionResult:
    human_condition: str = ""
    false_response: str = ""
    human_need: str = ""
    divine_action: str = ""
    grace_response: str = ""
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_ui_block(self) -> dict[str, str]:
        """Prompt-mezők → sermon_workshop human_condition UI-kulcsok."""
        return {
            "condition": self.human_condition,
            "false_response": self.false_response,
            "human_need": self.human_need,
            "divine_action": self.divine_action,
            "grace_response": self.grace_response,
        }


@dataclass
class HumanConditionAssessmentFields:
    text_fidelity: str = ""
    template_risk: str = ""
    divine_human_separation: str = ""
    moralizing_risk: str = ""
    false_response_appropriateness: str = ""
    grace_grounding: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class HumanConditionRevisedBlock:
    human_condition: str = ""
    false_response: str = ""
    human_need: str = ""
    divine_action: str = ""
    grace_response: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def to_ui_block(self) -> dict[str, str]:
        return {
            "condition": self.human_condition,
            "false_response": self.false_response,
            "human_need": self.human_need,
            "divine_action": self.divine_action,
            "grace_response": self.grace_response,
        }


@dataclass
class HumanConditionAssessmentResult:
    assessment: HumanConditionAssessmentFields = field(
        default_factory=HumanConditionAssessmentFields
    )
    strengths: list[str] = field(default_factory=list)
    revision_priorities: list[str] = field(default_factory=list)
    revised_block: HumanConditionRevisedBlock = field(
        default_factory=HumanConditionRevisedBlock
    )
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _format_human_condition_block(block: Any) -> str:
    """Felhasználói emberi helyzet blokk szöveges megjelenítése a promptban."""
    if block is None:
        return MISSING
    if isinstance(block, str):
        return _display(block, max_chars=_LIMITS["human_condition_block"])
    if not isinstance(block, Mapping):
        return MISSING

    # Fogadja mind a UI-kulcsokat (condition), mind a prompt-kulcsokat.
    labels = (
        ("human_condition", "Emberi helyzet", ("human_condition", "condition")),
        ("false_response", "Téves vagy elégtelen válasz", ("false_response",)),
        ("human_need", "Emberi szükség", ("human_need",)),
        ("divine_action", "Isten cselekvése", ("divine_action",)),
        ("grace_response", "Kegyelmi válasz", ("grace_response",)),
    )
    lines: list[str] = []
    any_present = False
    for _key, label, aliases in labels:
        value = ""
        for alias in aliases:
            value = _as_text(block.get(alias))
            if value:
                break
        if value:
            any_present = True
            lines.append(f"{label}: {value}")
        else:
            lines.append(f"{label}: {MISSING}")
    if not any_present:
        return MISSING
    joined = "\n".join(lines)
    return _display(joined, max_chars=_LIMITS["human_condition_block"])


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos is_llm_error_text (llm_text_utils.py; azonosság: tests/test_llm_text_utils.py).
_is_api_error_text = is_llm_error_text


def _safe_truncate_structured(text: str, max_chars: int) -> str:
    """Hosszú elemzés levágása anélkül, hogy JSON-t félbevágna.

    Ha a szöveg JSON-objektumnak/listának tűnik, inkább a teljes struktúrát
    tartjuk meg, ha belefér; különben szöveges levágás ellipszissel.
    """
    raw = _as_text(text)
    if not raw:
        return MISSING
    if len(raw) <= max_chars:
        return raw
    stripped = raw.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            # Ne vágjunk félbe érvényes JSON-t: kompakt újraszerializálás,
            # ha még így is túl hosszú, szöveges összefoglaló jelzés.
            compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
            if len(compact) <= max_chars:
                return compact
            return (
                compact[: max_chars - 1].rstrip()
                + "…"
            )
    return raw[: max_chars - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Kontextusépítés
# ---------------------------------------------------------------------------


def build_m4_context(
    *,
    passage: str = "",
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    approved_insights: Any = None,
    exegesis: str = "",
    theology: str = "",
    sermon_main_idea: str = "",
    human_condition: Any = None,
) -> dict[str, str]:
    """Szelektív M4-kontextus. Illusztráció / aktualizálás / ének / vázlat nélkül."""
    exegesis_disp = (
        _safe_truncate_structured(exegesis, _LIMITS["exegesis"])
        if _is_present(exegesis)
        else MISSING
    )
    theology_disp = (
        _safe_truncate_structured(theology, _LIMITS["theology"])
        if _is_present(theology)
        else MISSING
    )
    return {
        "passage": _display(passage, max_chars=200) if _is_present(passage) else MISSING,
        "passage_text": _display(passage_text, max_chars=_LIMITS["passage_text"]),
        "occasion": _display(occasion, max_chars=_LIMITS["occasion"]),
        "user_focus": _display(user_focus, max_chars=_LIMITS["user_focus"]),
        "text_main_idea": _display(text_main_idea, max_chars=_LIMITS["text_main_idea"]),
        "text_main_idea_status": (
            _display(text_main_idea_status, max_chars=40)
            if _is_present(text_main_idea_status)
            else MISSING
        ),
        "approved_insights": _format_insights(
            approved_insights, max_chars=_LIMITS["approved_insights"]
        ),
        "exegesis": exegesis_disp,
        "theology": theology_disp,
        "sermon_main_idea": _display(
            sermon_main_idea, max_chars=_LIMITS["sermon_main_idea"]
        ),
        "human_condition_block": _format_human_condition_block(human_condition),
    }


def _analysis_sources_present(ctx: Mapping[str, str]) -> list[str]:
    keys = (
        ("passage_text", "bibliai szöveg (passage_text)"),
        ("text_main_idea", "textus fő gondolata"),
        ("approved_insights", "jóváhagyott felismerések"),
        ("exegesis", "exegézis"),
        ("theology", "teológia"),
    )
    present: list[str] = []
    for key, label in keys:
        if _is_present(ctx.get(key, MISSING)):
            present.append(label)
    return present


def _missing_analysis_labels(ctx: Mapping[str, str]) -> list[str]:
    labels = {
        "passage_text": "bibliai szöveg (passage_text)",
        "text_main_idea": "textus fő gondolata",
        "approved_insights": "jóváhagyott felismerések",
        "exegesis": "exegézis",
        "theology": "teológia",
    }
    return [
        label
        for key, label in labels.items()
        if not _is_present(ctx.get(key, MISSING))
    ]


def has_sufficient_m4_material(ctx: Mapping[str, str]) -> bool:
    if not _is_present(ctx.get("passage", MISSING)):
        return False
    return bool(_analysis_sources_present(ctx))


# ---------------------------------------------------------------------------
# Promptépítés (új, külön a meglévő promptépítőktől)
# ---------------------------------------------------------------------------



_SUGGEST_SERMON_MAIN_IDEA_TEMPLATE = """\
Feladatod: az IGEHIRDETÉS FŐ GONDOLATÁNAK megfogalmazása.

Ez NEM prédikációs cím, NEM szlogen, NEM vázlat, NEM alkalmazás-lista, NEM puszta hallgatói felszólítás.

## Fogalom — textus fő gondolat vs. igehirdetés fő gondolata

- A textus fő gondolata és az igehirdetés fő gondolata KÜLÖN fogalom.
- NEM kötelező mesterségesen eltérő mondatot alkotni.
- Ha a textus fő gondolata már textushű, hallható és az egész prédikációt összetartó állítás, indokolt esetben ÁTVEHETŐ.
- NE írj át valamit pusztán a különbözőség kedvéért.
- Az alkalom és a hallgatói helyzet segítheti a hallhatóságot, de NEM írhatja felül a textus állítását.

Az igehirdetés fő gondolata:
- egyetlen világos, teljes állító mondat;
- a textus állításából következik;
- hallható (lásd lent);
- összetartja a prédikáció útját.

## Mit jelent a „hallható”

A mondat akkor hallható, ha:
- egyszeri hallás után követhető;
- világos mondatszerkezetű;
- nem túlterhelt;
- megmutatja, mi a textus állításának jelentősége a hallgató számára;
- MÉG NEM alkalmazás és NEM felszólításlista.

## Tilalmak

- Ne írj teljes prédikációt vagy pontokra bontott vázlatot.
- Ne moralizálj; ne gyárts mesterséges „bűnproblémát”.
- Ne erőltesd a Krisztus-kapcsolatot.
- Ne találj ki görög/héber adatot, kommentárt, történeti hátteret.
- Ne adj belső gondolatmenetet — csak rövid reasoning_summary-t.
- Ha nincs elegendő adat: recommended = ""; expanded_summary = ""; alternatives = []; a hiányt reasoning_summary, warnings és missing_information jelezze. Az üres mező jobb, mint a kitalált állítás.

## recommended szabályai

- Egyetlen teljes állító mondat.
- Textushű és hallható.
- Ne legyen cím vagy szlogen.
- Ne próbálja egyetlen mondatba zsúfolni a teljes exegézist.
- A többmondatos magyarázat NE a recommended mezőbe kerüljön, hanem az expanded_summary-ba.

## expanded_summary szabályai

Az expanded_summary 3–4 rövid, összefüggő mondatban:
- mutassa meg a prédikáció lehetséges felismerési irányát;
- tegye világossá a fő gondolat jelentőségét a hallgató számára;
- jelezze a textusban lévő feszültséget és annak irányát, ha van;
- kapcsolja össze Isten cselekvését és a kegyelemből fakadó emberi választ;
- MÉG NE készítsen vázlatot vagy alkalmazáslistát;
- NE sorolja fel a későbbi prédikációs pontokat;
- NE használjon közvetlen, moralizáló felszólításokat;
- NE erőltesse a Krisztus-kapcsolatot (az külön műhelyszakasz);
- NE ismételje szó szerint a recommended mondatot;
- elégtelen recommended esetén legyen üres string: "".

## Alternatívák

- Legfeljebb két alternatíva.
- Csak valódi homiletikai hangsúlyeltérés esetén jelenjenek meg.
- NE legyenek puszta stilisztikai átfogalmazások.
- Ha nincs valódi hangsúlyeltérés: alternatives = [].
- Az alternatives elemei egy-egy mondatos főgondolatok; NE készíts hozzájuk külön 3–4 mondatos kifejtést.
## textual_and_homiletical_basis forrásjelölés

Minden elem ezzel a forrástípussal kezdődjön, majd kötőjel és rövid tartalom:

- „Textus fő gondolata — …”
- „Jóváhagyott felismerés — …”
- „Exegézis — …”
- „Teológia — …”
- „Hallhatósági megfontolás — …”

A „Hallhatósági megfontolás” NE tartalmazzon új exegetikai vagy teológiai állítást. Csak olyan forrásjelölés, idézet vagy versszám kerülhet be, amelyet a bemenet alátámaszt.

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

Alkalom (segítheti a hallhatóságot, nem írhatja felül a textust):
{{occasion}}

Felhasználói szempont (segítheti a hallhatóságot, nem írhatja felül a textust):
{{user_focus}}

A textus fő gondolata:
{{text_main_idea}}

A textus fő gondolatának státusza:
{{text_main_idea_status}}

Jóváhagyott textusműhely-felismerések:
{{approved_insights}}

Exegézis (részlet):
{{exegesis}}

Teológia (részlet):
{{theology}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező.
- Listánál elemhiány esetén: [].
- Stringhiány esetén: "".
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző (trailing comma).

{
  "recommended": "string",
  "expanded_summary": "string",
  "alternatives": ["string"],
  "reasoning_summary": "string",
  "textual_and_homiletical_basis": ["string"],
  "warnings": ["string"],
  "missing_information": ["string"]
}
"""

_ASSESS_SERMON_MAIN_IDEA_TEMPLATE = """\
Feladatod: a felhasználó IGEHIRDETÉSI FŐ GONDOLATÁNAK értékelése.

Ne írd felül automatikusan. Adj szakmai értékelést és — ha felelősen lehetséges — egy átdolgozott JAVASLATOT (revised_version).
Üres user mondatnál ne találj ki semmit; revised_version = "".

## Fogalom

- A textus fő gondolata és az igehirdetés fő gondolata külön fogalom, de nem kötelező mesterségesen eltérőnek lenniük.
- Ha a felhasználó mondata lényegében a már megfelelő textus fő gondolat, ez lehet Megfelelő — ne javítsd a különbözőség kedvéért.
- Az alkalom / hallgatói helyzet segítheti a hallhatóságot, de nem írhatja felül a textust.
- Ha nincs elegendő adat, az üres / „Nem megítélhető —” jobb, mint a kitalált értékelés.

## Vizsgálandó szempontok (assessment)

Minden mező rövid szövege PONTOSAN ezzel a minősítéssel kezdődjön:
„Megfelelő — …” / „Részben megfelelő — …” / „Javítandó — …” / „Nem megítélhető — …”

- text_fidelity: hű-e a textushoz és a megadott anyaghoz;
- hearability: túl hosszú vagy túl összetett-e; egyszeri hallás után megjegyezhető-e a lényege; vannak-e homályos teológiai absztrakciók; természetes magyar mondat-e;
- unity: egyetlen állítás-e;
- theological_accuracy: teológiailag helyes-e a megadott anyaghoz képest;
- listener_relevance: érthetően kapcsolódik-e a hallgató valóságához — KÜLÖN jelezd, ha ez már alkalmazássá, felszólítássá vagy a textus felülírásává válik;
- title_or_slogan_confusion: cím / szlogen-e;
- application_confusion: alkalmazás / felszólítás-e a fő gondolat helyett.

## revised_version szabályai

- Csak akkor készüljön, ha van elegendő alap.
- Ne tartalmazzon új, a bemenetben nem szereplő teológiai állítást.
- Ne váljon alkalmazássá.
- Egyetlen teljes mondat legyen.
- Ha nincs elegendő alap: "".

## Tilalmak

- Ne adj pontszámot, százalékot, csillagot.
- Ne írj teljes prédikációt.
- Ne erőltesd a Krisztus-kapcsolatot.
- Ne moralizálj.
- Ne adj belső gondolatmenetet.
- Legfeljebb három revision_priorities.

## Bemeneti anyag

Igehely-megjelölés:
{{passage}}

Bibliai szöveg, ha van:
{{passage_text}}

A textus fő gondolata:
{{text_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis (részlet):
{{exegesis}}

Teológia (részlet):
{{theology}}

Alkalom / szempont (nem írhatja felül a textust):
{{occasion}}
{{user_focus}}

A felhasználó igehirdetési fő gondolata:
{{sermon_main_idea}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező.
- Listánál elemhiány esetén: [].
- Stringhiány esetén: "".
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző.

{
  "assessment": {
    "text_fidelity": "string",
    "hearability": "string",
    "unity": "string",
    "theological_accuracy": "string",
    "listener_relevance": "string",
    "title_or_slogan_confusion": "string",
    "application_confusion": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_version": "string",
  "warnings": ["string"]
}
"""

_SUGGEST_HUMAN_CONDITION_TEMPLATE = """\
Feladatod: az EMBERI HELYZET ÉS KEGYELMI VÁLASZ blokk javaslatának megfogalmazása.

Ez NEM prédikáció, NEM vázlat, NEM alkalmazás-lista.

## Fogalom és elkülönítés

Különítsd el:
- emberi helyzet;
- téves/elégtelen válasz (csak ha a textus indokolja);
- emberi szükség;
- Isten cselekvése;
- kegyelmi válasz.

A textus fő gondolata és az igehirdetés fő gondolata külön fogalom; az alkalom segítheti a hallhatóságot, de nem írhatja felül a textust.
Ne adj belső gondolatmenetet — csak a JSON mezőket.
Ha nincs elegendő adat, az üres mező jobb, mint a kitalált vagy sablonos állítás.

## Nem kötelező minden mező

- NEM kötelező minden mezőt kitölteni.
- false_response maradjon "" , ha a textus nem tár fel világos téves vagy elégtelen emberi választ.
- human_need maradjon "" , ha csak általános emberi szükségletet lehetne beírni textusbeli alap nélkül.
- grace_response maradjon "" , ha a textus nem alapoz meg világos kegyelmi választ.
- Az üres mező szakmailag helyesebb, mint a textusra kényszerített homiletikai kategória.

## Mezők pontosítása

- human_condition: a textus által feltárt emberi állapot, helyzet, korlátozottság, vágy, félelem, törés, kísértés vagy közösségi valóság.
- false_response: CSAK a textus által ténylegesen jelzett téves, elégtelen vagy önvédő válasz.
- human_need: az a szükség, amely a textus értelmezéséből következik — nem általános pszichológiai vagy vallási közhely.
- divine_action: ELSŐKÉNT azt fogalmazza meg, amit Isten a textusban közvetlenül cselekszik, ígér, kijelent vagy lehetővé tesz.
- grace_response: az a válasz, amelyet Isten megelőző cselekvése lehetővé tesz; ne legyen puszta moralizáló felszólítás.

Ha a divine_action csak tágabb teológiai következtetésből származik (nem a textus közvetlen cselekvése), ezt a warnings mezőben VILÁGOSAN jelezd.

## Ne legyen Chapell-sablon kötelező

Ne tekintsd kötelezőnek a fallen condition formális kitöltését.
Narratív, dicsőítő, bölcsességi, vigasztaló vagy eszkatologikus textusnál más jellegű emberi helyzet is lehet a középpontban.
Ne kényszeríts minden textusra azonos „bűnprobléma” sablont.
Ne moralizálj.
Ne erőltesd a Krisztus-kapcsolatot (az későbbi szakasz).

## Tilalmak

- Ne találj ki adatot a bemeneten kívül.
- Ha elégtelen az anyag: a nem megalapozható mezők legyenek ""; warnings + missing_information kötelező.
- Az alkalom NEM írhatja felül a textust.

## Bemeneti anyag

Igehely-megjelölés:
{{passage}}

Bibliai szöveg, ha van:
{{passage_text}}

A textus fő gondolata:
{{text_main_idea}}

Az igehirdetés fő gondolata (ha van):
{{sermon_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis (részlet):
{{exegesis}}

Teológia (részlet):
{{theology}}

Alkalom / szempont (nem írhatja felül a textust):
{{occasion}}
{{user_focus}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező (üres string megengedett).
- Listánál elemhiány esetén: [].
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző.

{
  "human_condition": "string",
  "false_response": "string",
  "human_need": "string",
  "divine_action": "string",
  "grace_response": "string",
  "warnings": ["string"],
  "missing_information": ["string"]
}
"""

_ASSESS_HUMAN_CONDITION_TEMPLATE = """\
Feladatod: a felhasználó EMBERI HELYZET ÉS KEGYELMI VÁLASZ elemzésének értékelése.

Ez a NEGYEDIK, önálló művelet — NEM a javaslatkészítő folytatása.
Ne pontozz. Adj rövid szöveges megállapításokat minősítő előtaggal:
„Megfelelő — …” / „Részben megfelelő — …” / „Javítandó — …” / „Nem megítélhető — …”

## Fogalom

- A textus fő gondolata és az igehirdetés fő gondolata külön fogalom.
- Az alkalom segítheti a hallhatóságot, de nem írhatja felül a textust.
- Ne adj belső gondolatmenetet.
- Ha nincs elegendő adat, az üres mező / „Nem megítélhető —” jobb, mint a kitalált javítás.
- Ne írj prédikációt; ne erőltesd a Krisztus-kapcsolatot.

## Vizsgálandó szempontok

- text_fidelity: a helyzet textushűségét;
- template_risk: külön vizsgáld — ráhúzott általános bűnprobléma; minden textusban azonos emberi szükség; automatikus „Isten megment, ezért nekünk…” formula; pszichologizálás textusbeli alap nélkül;
- divine_human_separation: Isten cselekvése valóban megelőzi-e és megalapozza-e az emberi választ; nem olvad-e össze a kettő; nem lesz-e az isteni cselekvés puszta háttér az emberi feladathoz;
- moralizing_risk: moralizálás / alkalmazás összekeverése;
- false_response_appropriateness: a false_response indokoltsága (üres is lehet helyes);
- grace_grounding: valóban a textusból vagy a jóváhagyott teológiai anyagból következik-e; nem általános kegyelmi formula-e; a kegyelmi válasz nem csúszik-e át alkalmazáslistába.

Adj legfeljebb három revision_priorities elemet.

## revised_block szabályai

A revised_block MINDIG objektum maradjon ezekkel a kulcsokkal (soha ne legyen null):

{
  "human_condition": "string",
  "false_response": "string",
  "human_need": "string",
  "divine_action": "string",
  "grace_response": "string"
}

Ha nincs elegendő alap a felelős javításhoz, minden nem megalapozható mező legyen üres string: "".
Ne használj null értéket.
Ne adj hozzá új teológiai állítást, amely nincs a bemenetben.

## Bemeneti anyag

Igehely-megjelölés:
{{passage}}

Bibliai szöveg, ha van:
{{passage_text}}

A textus fő gondolata:
{{text_main_idea}}

Az igehirdetés fő gondolata (ha van):
{{sermon_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis / teológia (részlet):
{{exegesis}}
{{theology}}

A felhasználó elemzése:
{{human_condition_block}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül.
- Ne használj markdownot vagy kódblokkot.
- Minden mező kötelező.
- Listánál elemhiány esetén: [].
- Stringhiány esetén: "".
- Minden string szabályosan escape-elt.
- Az objektumban ne legyen záró vessző.
- A revised_block mindig objektum; soha ne legyen null.

{
  "assessment": {
    "text_fidelity": "string",
    "template_risk": "string",
    "divine_human_separation": "string",
    "moralizing_risk": "string",
    "false_response_appropriateness": "string",
    "grace_grounding": "string"
  },
  "strengths": ["string"],
  "revision_priorities": ["string"],
  "revised_block": {
    "human_condition": "string",
    "false_response": "string",
    "human_need": "string",
    "divine_action": "string",
    "grace_response": "string"
  },
  "warnings": ["string"]
}
"""




def _fill_placeholders(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def build_sermon_main_idea_suggest_prompt(ctx: Mapping[str, str]) -> str:
    return _fill_placeholders(_SUGGEST_SERMON_MAIN_IDEA_TEMPLATE, ctx)


def build_sermon_main_idea_assess_prompt(ctx: Mapping[str, str]) -> str:
    return _fill_placeholders(_ASSESS_SERMON_MAIN_IDEA_TEMPLATE, ctx)


def build_human_condition_suggest_prompt(ctx: Mapping[str, str]) -> str:
    return _fill_placeholders(_SUGGEST_HUMAN_CONDITION_TEMPLATE, ctx)


def build_human_condition_assess_prompt(ctx: Mapping[str, str]) -> str:
    return _fill_placeholders(_ASSESS_HUMAN_CONDITION_TEMPLATE, ctx)


# ---------------------------------------------------------------------------
# JSON kinyerés és validáció
# ---------------------------------------------------------------------------


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos extract_json_object_lenient (llm_text_utils.py; azonosság:
# tests/test_llm_json_extractors.py).
# KOMPATIBILITÁSI ALIAS — 15 modul importálja innen
# (`from sermon_workshop_m4_ai import extract_json_object`), és az
# __all__ is felsorolja; a nevet ezért meg kell tartani.
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
    return f"Részben megfelelő — {text}"


def _hc_str_field(value: Any) -> str:
    """Emberi helyzet mező: mindig string, soha null."""
    if value is None:
        return ""
    return _as_text(value)


def fallback_sermon_main_idea_suggestion(
    *,
    reasoning: str,
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> SermonMainIdeaSuggestionResult:
    return SermonMainIdeaSuggestionResult(
        recommended="",
        expanded_summary="",
        alternatives=[],
        reasoning_summary=reasoning,
        textual_and_homiletical_basis=[],
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def fallback_sermon_main_idea_assessment(
    *,
    reason: str,
    warnings: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> SermonMainIdeaAssessmentResult:
    tag = f"Nem megítélhető — {reason}"
    return SermonMainIdeaAssessmentResult(
        assessment=SermonMainIdeaAssessmentFields(
            text_fidelity=tag,
            hearability=tag,
            unity=tag,
            theological_accuracy=tag,
            listener_relevance=tag,
            title_or_slogan_confusion=tag,
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


def fallback_human_condition_suggestion(
    *,
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> HumanConditionSuggestionResult:
    return HumanConditionSuggestionResult(
        human_condition="",
        false_response="",
        human_need="",
        divine_action="",
        grace_response="",
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def fallback_human_condition_assessment(
    *,
    reason: str,
    warnings: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> HumanConditionAssessmentResult:
    tag = f"Nem megítélhető — {reason}"
    return HumanConditionAssessmentResult(
        assessment=HumanConditionAssessmentFields(
            text_fidelity=tag,
            template_risk=tag,
            divine_human_separation=tag,
            moralizing_risk=tag,
            false_response_appropriateness=tag,
            grace_grounding=tag,
        ),
        strengths=[],
        revision_priorities=[],
        revised_block=HumanConditionRevisedBlock(),
        warnings=list(warnings or [reason]),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def parse_sermon_main_idea_suggestions(raw: str) -> SermonMainIdeaSuggestionResult:
    if _is_api_error_text(raw):
        return fallback_sermon_main_idea_suggestion(
            reasoning="A modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw)
    if obj is None:
        return fallback_sermon_main_idea_suggestion(
            reasoning="A válasz nem dolgozható fel érvényes JSON-ként.",
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )
    recommended = _as_text(obj.get("recommended"))
    expanded_summary = _as_text(obj.get("expanded_summary"))
    alternatives = _as_str_list(obj.get("alternatives"), max_items=2)
    reasoning = _as_text(obj.get("reasoning_summary"))
    basis = _as_str_list(obj.get("textual_and_homiletical_basis"), max_items=6)
    warnings = _as_str_list(obj.get("warnings"))
    missing = _as_str_list(obj.get("missing_information"))
    if not recommended:
        expanded_summary = ""
    if not reasoning:
        reasoning = (
            "A modell nem adott indoklást."
            if recommended
            else "Nincs elegendő megalapozott javaslat a rendelkezésre álló anyagból."
        )
    return SermonMainIdeaSuggestionResult(
        recommended=recommended,
        expanded_summary=expanded_summary,
        alternatives=alternatives,
        reasoning_summary=reasoning,
        textual_and_homiletical_basis=basis,
        warnings=warnings,
        missing_information=missing,
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


def parse_sermon_main_idea_assessment(raw: str) -> SermonMainIdeaAssessmentResult:
    if _is_api_error_text(raw):
        return fallback_sermon_main_idea_assessment(
            reason="A modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw)
    if obj is None:
        return fallback_sermon_main_idea_assessment(
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
    fields = SermonMainIdeaAssessmentFields(
        text_fidelity=_normalize_assessment_text(
            assessment_raw.get("text_fidelity"), empty_reason=empty_reason
        ),
        hearability=_normalize_assessment_text(
            assessment_raw.get("hearability"), empty_reason=empty_reason
        ),
        unity=_normalize_assessment_text(
            assessment_raw.get("unity"), empty_reason=empty_reason
        ),
        theological_accuracy=_normalize_assessment_text(
            assessment_raw.get("theological_accuracy"), empty_reason=empty_reason
        ),
        listener_relevance=_normalize_assessment_text(
            assessment_raw.get("listener_relevance"), empty_reason=empty_reason
        ),
        title_or_slogan_confusion=_normalize_assessment_text(
            assessment_raw.get("title_or_slogan_confusion"), empty_reason=empty_reason
        ),
        application_confusion=_normalize_assessment_text(
            assessment_raw.get("application_confusion"), empty_reason=empty_reason
        ),
    )
    return SermonMainIdeaAssessmentResult(
        assessment=fields,
        strengths=_as_str_list(obj.get("strengths"), max_items=3),
        revision_priorities=_as_str_list(obj.get("revision_priorities"), max_items=3),
        revised_version=_as_text(obj.get("revised_version")),
        warnings=_as_str_list(obj.get("warnings")),
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


def parse_human_condition_suggestion(raw: str) -> HumanConditionSuggestionResult:
    if _is_api_error_text(raw):
        return fallback_human_condition_suggestion(
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw)
    if obj is None:
        return fallback_human_condition_suggestion(
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )
    return HumanConditionSuggestionResult(
        human_condition=_hc_str_field(obj.get("human_condition")),
        false_response=_hc_str_field(obj.get("false_response")),
        human_need=_hc_str_field(obj.get("human_need")),
        divine_action=_hc_str_field(obj.get("divine_action")),
        grace_response=_hc_str_field(obj.get("grace_response")),
        warnings=_as_str_list(obj.get("warnings")),
        missing_information=_as_str_list(obj.get("missing_information")),
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


def parse_human_condition_assessment(raw: str) -> HumanConditionAssessmentResult:
    if _is_api_error_text(raw):
        return fallback_human_condition_assessment(
            reason="A modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw)
    if obj is None:
        return fallback_human_condition_assessment(
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
    fields = HumanConditionAssessmentFields(
        text_fidelity=_normalize_assessment_text(
            assessment_raw.get("text_fidelity"), empty_reason=empty_reason
        ),
        template_risk=_normalize_assessment_text(
            assessment_raw.get("template_risk"), empty_reason=empty_reason
        ),
        divine_human_separation=_normalize_assessment_text(
            assessment_raw.get("divine_human_separation"), empty_reason=empty_reason
        ),
        moralizing_risk=_normalize_assessment_text(
            assessment_raw.get("moralizing_risk"), empty_reason=empty_reason
        ),
        false_response_appropriateness=_normalize_assessment_text(
            assessment_raw.get("false_response_appropriateness"),
            empty_reason=empty_reason,
        ),
        grace_grounding=_normalize_assessment_text(
            assessment_raw.get("grace_grounding"), empty_reason=empty_reason
        ),
    )
    revised_raw = obj.get("revised_block")
    if not isinstance(revised_raw, dict):
        revised_raw = {}
    revised = HumanConditionRevisedBlock(
        human_condition=_hc_str_field(revised_raw.get("human_condition")),
        false_response=_hc_str_field(revised_raw.get("false_response")),
        human_need=_hc_str_field(revised_raw.get("human_need")),
        divine_action=_hc_str_field(revised_raw.get("divine_action")),
        grace_response=_hc_str_field(revised_raw.get("grace_response")),
    )
    return HumanConditionAssessmentResult(
        assessment=fields,
        strengths=_as_str_list(obj.get("strengths"), max_items=3),
        revision_priorities=_as_str_list(obj.get("revision_priorities"), max_items=3),
        revised_block=revised,
        warnings=_as_str_list(obj.get("warnings")),
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


# ---------------------------------------------------------------------------
# Gemini-hívás wrapper
# ---------------------------------------------------------------------------


def _call_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    tab_label: str,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> str:
    # 2026-11-23: a korábbi helyi törzs helyett a közös, viselkedésében azonos
    # call_generate_with_session_temperature (llm_text_utils.py; azonosság:
    # tests/test_llm_call_wrapper.py). A modul saját system_bundle-je és
    # DEFAULT_TEMPERATURE alapértéke itt marad.
    return call_generate_with_session_temperature(
        generate_fn,
        prompt,
        tab_label=tab_label,
        temperature=temperature,
        system_bundle=M4_SYSTEM_BUNDLE,
    )


def _common_ctx_kwargs(
    *,
    passage: str,
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    approved_insights: Any = None,
    exegesis: str = "",
    theology: str = "",
    sermon_main_idea: str = "",
    human_condition: Any = None,
) -> dict[str, Any]:
    return dict(
        passage=passage,
        passage_text=passage_text,
        occasion=occasion,
        user_focus=user_focus,
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        approved_insights=approved_insights,
        exegesis=exegesis,
        theology=theology,
        sermon_main_idea=sermon_main_idea,
        human_condition=human_condition,
    )


# ---------------------------------------------------------------------------
# Publikus API
# ---------------------------------------------------------------------------


def suggest_sermon_main_idea(
    *,
    passage: str,
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    approved_insights: Any = None,
    exegesis: str = "",
    theology: str = "",
    sermon_main_idea: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> SermonMainIdeaSuggestionResult:
    ctx = build_m4_context(
        **_common_ctx_kwargs(
            passage=passage,
            passage_text=passage_text,
            occasion=occasion,
            user_focus=user_focus,
            text_main_idea=text_main_idea,
            text_main_idea_status=text_main_idea_status,
            approved_insights=approved_insights,
            exegesis=exegesis,
            theology=theology,
            sermon_main_idea=sermon_main_idea,
        )
    )
    if not _is_present(ctx["passage"]):
        return fallback_sermon_main_idea_suggestion(
            reasoning="Nincs megadva igehely-megjelölés; javaslat nem indítható.",
            warnings=["Az igehely (passage) hiányzik."],
            missing=["igehely-megjelölés (passage)"],
            error_message="Hiányzó igehely.",
            ok=False,
        )
    missing = _missing_analysis_labels(ctx)
    if skip_api_if_insufficient and not has_sufficient_m4_material(ctx):
        return fallback_sermon_main_idea_suggestion(
            reasoning=(
                "Nincs elegendő rendelkezésre bocsátott bibliai szöveg vagy "
                "elemzési anyag felelős igehirdetési főgondolat-javaslathoz."
            ),
            warnings=[
                "Elégtelen adat: felelős javaslat helyett üres recommended/alternatives."
            ],
            missing=missing or ["elemzési anyag"],
            ok=True,
        )
    if generate_fn is None:
        return fallback_sermon_main_idea_suggestion(
            reasoning="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_sermon_main_idea_suggest_prompt(ctx)
    try:
        raw = _call_generate(
            generate_fn,
            prompt,
            tab_label=TAB_SUGGEST_SERMON,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_sermon_main_idea_suggestion(
            reasoning="A javaslatkészítés közben váratlan hiba történt.",
            warnings=["A javaslatkészítés nem sikerült. Próbáld újra később."],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )
    return parse_sermon_main_idea_suggestions(raw or "")


def assess_sermon_main_idea(
    *,
    passage: str,
    sermon_main_idea: str,
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    approved_insights: Any = None,
    exegesis: str = "",
    theology: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> SermonMainIdeaAssessmentResult:
    if not _is_present(sermon_main_idea):
        return fallback_sermon_main_idea_assessment(
            reason="A felhasználói igehirdetési fő gondolat üres; nincs mit értékelni.",
            warnings=["Üres sermon_main_idea — nincs kitalálás és nincs átdolgozás."],
            ok=True,
        )
    ctx = build_m4_context(
        **_common_ctx_kwargs(
            passage=passage,
            passage_text=passage_text,
            occasion=occasion,
            user_focus=user_focus,
            text_main_idea=text_main_idea,
            text_main_idea_status=text_main_idea_status,
            approved_insights=approved_insights,
            exegesis=exegesis,
            theology=theology,
            sermon_main_idea=sermon_main_idea,
        )
    )
    if not _is_present(ctx["passage"]):
        return fallback_sermon_main_idea_assessment(
            reason="Nincs megadva igehely-megjelölés; az értékelés korlátozott.",
            warnings=["Az igehely (passage) hiányzik."],
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if generate_fn is None:
        return fallback_sermon_main_idea_assessment(
            reason="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_sermon_main_idea_assess_prompt(ctx)
    try:
        raw = _call_generate(
            generate_fn,
            prompt,
            tab_label=TAB_ASSESS_SERMON,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_sermon_main_idea_assessment(
            reason="Az értékelés közben váratlan hiba történt.",
            warnings=["Az értékelés nem sikerült. Próbáld újra később."],
            error_message=str(exc),
            ok=False,
        )
    result = parse_sermon_main_idea_assessment(raw or "")
    if result.ok and not _analysis_sources_present(ctx):
        result.revised_version = ""
        note = "Nincs elegendő elemzési alap a felelős átdolgozáshoz."
        if note not in result.warnings:
            result.warnings = list(result.warnings) + [note]
    return result


def suggest_human_condition(
    *,
    passage: str,
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    approved_insights: Any = None,
    exegesis: str = "",
    theology: str = "",
    sermon_main_idea: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> HumanConditionSuggestionResult:
    ctx = build_m4_context(
        **_common_ctx_kwargs(
            passage=passage,
            passage_text=passage_text,
            occasion=occasion,
            user_focus=user_focus,
            text_main_idea=text_main_idea,
            text_main_idea_status=text_main_idea_status,
            approved_insights=approved_insights,
            exegesis=exegesis,
            theology=theology,
            sermon_main_idea=sermon_main_idea,
        )
    )
    if not _is_present(ctx["passage"]):
        return fallback_human_condition_suggestion(
            warnings=["Az igehely (passage) hiányzik."],
            missing=["igehely-megjelölés (passage)"],
            error_message="Hiányzó igehely.",
            ok=False,
        )
    missing = _missing_analysis_labels(ctx)
    if skip_api_if_insufficient and not has_sufficient_m4_material(ctx):
        return fallback_human_condition_suggestion(
            warnings=[
                "Elégtelen adat: felelős javaslat helyett üres mezők."
            ],
            missing=missing or ["elemzési anyag"],
            ok=True,
        )
    if generate_fn is None:
        return fallback_human_condition_suggestion(
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_human_condition_suggest_prompt(ctx)
    try:
        raw = _call_generate(
            generate_fn,
            prompt,
            tab_label=TAB_SUGGEST_HC,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_human_condition_suggestion(
            warnings=["A javaslatkészítés nem sikerült. Próbáld újra később."],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )
    return parse_human_condition_suggestion(raw or "")


def assess_human_condition(
    *,
    passage: str,
    human_condition: Any,
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    approved_insights: Any = None,
    exegesis: str = "",
    theology: str = "",
    sermon_main_idea: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> HumanConditionAssessmentResult:
    # Üres blokk: nincs kitalálás
    block_text = _format_human_condition_block(human_condition)
    if block_text == MISSING:
        return fallback_human_condition_assessment(
            reason="A felhasználói emberihelyzet-elemzés üres; nincs mit értékelni.",
            warnings=["Üres human_condition blokk — nincs kitalálás és nincs átdolgozás."],
            ok=True,
        )
    ctx = build_m4_context(
        **_common_ctx_kwargs(
            passage=passage,
            passage_text=passage_text,
            occasion=occasion,
            user_focus=user_focus,
            text_main_idea=text_main_idea,
            text_main_idea_status=text_main_idea_status,
            approved_insights=approved_insights,
            exegesis=exegesis,
            theology=theology,
            sermon_main_idea=sermon_main_idea,
            human_condition=human_condition,
        )
    )
    if not _is_present(ctx["passage"]):
        return fallback_human_condition_assessment(
            reason="Nincs megadva igehely-megjelölés; az értékelés korlátozott.",
            warnings=["Az igehely (passage) hiányzik."],
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if generate_fn is None:
        return fallback_human_condition_assessment(
            reason="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_human_condition_assess_prompt(ctx)
    try:
        raw = _call_generate(
            generate_fn,
            prompt,
            tab_label=TAB_ASSESS_HC,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_human_condition_assessment(
            reason="Az értékelés közben váratlan hiba történt.",
            warnings=["Az értékelés nem sikerült. Próbáld újra később."],
            error_message=str(exc),
            ok=False,
        )
    result = parse_human_condition_assessment(raw or "")
    if result.ok and not _analysis_sources_present(ctx):
        result.revised_block = HumanConditionRevisedBlock()
        note = "Nincs elegendő elemzési alap a felelős átdolgozáshoz."
        if note not in result.warnings:
            result.warnings = list(result.warnings) + [note]
    return result


# ---------------------------------------------------------------------------
# Smoke / önellenőrzés (API nélkül)
# ---------------------------------------------------------------------------


def _self_check() -> list[str]:
    errors: list[str] = []
    called = {"n": 0}

    def _should_not_run(*_a, **_k):
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    r = suggest_sermon_main_idea(passage="Jn 3,16–21", generate_fn=_should_not_run)
    if called["n"] != 0:
        errors.append("insufficient sermon suggest still called API")
    if r.recommended or r.alternatives:
        errors.append("insufficient sermon suggest should be empty")

    called["n"] = 0
    a = assess_sermon_main_idea(
        passage="Jn 3,16",
        sermon_main_idea="",
        generate_fn=_should_not_run,
    )
    if called["n"] != 0:
        errors.append("empty sermon assess still called API")
    if a.revised_version:
        errors.append("empty sermon assess should have empty revised")

    called["n"] = 0
    h = suggest_human_condition(passage="Jn 3,16", generate_fn=_should_not_run)
    if called["n"] != 0:
        errors.append("insufficient hc suggest still called API")
    if h.human_condition or h.divine_action:
        errors.append("insufficient hc suggest should be empty")

    called["n"] = 0
    _ha = assess_human_condition(
        passage="Jn 3,16",
        human_condition={},
        generate_fn=_should_not_run,
    )
    del _ha
    if called["n"] != 0:
        errors.append("empty hc assess still called API")

    # JSON parse — tiszta
    good = parse_sermon_main_idea_suggestions(
        '{"recommended":"A","expanded_summary":"Egy. Kettő. Három. Négy.",'
        '"alternatives":["B"],"reasoning_summary":"r",'
        '"textual_and_homiletical_basis":["x"],"warnings":[],"missing_information":[]}'
    )
    if good.recommended != "A" or good.alternatives != ["B"]:
        errors.append("good sermon suggest parse failed")
    if good.expanded_summary != "Egy. Kettő. Három. Négy.":
        errors.append("sermon expanded_summary parse failed")

    legacy = parse_sermon_main_idea_suggestions(
        '{"recommended":"A","alternatives":[],"reasoning_summary":"r",'
        '"textual_and_homiletical_basis":[],"warnings":[],"missing_information":[]}'
    )
    if legacy.expanded_summary != "":
        errors.append("legacy sermon suggest expanded_summary should be empty")

    if '"expanded_summary"' not in _SUGGEST_SERMON_MAIN_IDEA_TEMPLATE:
        errors.append("sermon suggest prompt missing expanded_summary")
    bad = parse_sermon_main_idea_suggestions("not json at all")
    if bad.ok:
        errors.append("bad json should not be ok")

    api_err = parse_sermon_main_idea_suggestions("⚠️ Hiba: timeout")
    if api_err.ok:
        errors.append("api error text should not be ok")

    # HC fields always string, never null
    hc = parse_human_condition_suggestion(
        '{"human_condition":null,"false_response":null,"human_need":"",'
        '"divine_action":"D","grace_response":null,"warnings":[],'
        '"missing_information":[]}'
    )
    for val in (
        hc.human_condition,
        hc.false_response,
        hc.human_need,
        hc.divine_action,
        hc.grace_response,
    ):
        if not isinstance(val, str):
            errors.append("hc field not string")
            break
    if hc.divine_action != "D":
        errors.append("hc divine_action parse failed")

    # revised_block never null
    hca = parse_human_condition_assessment(
        '{"assessment":{},"strengths":[],"revision_priorities":[],'
        '"revised_block":null,"warnings":[]}'
    )
    if not isinstance(hca.revised_block, HumanConditionRevisedBlock):
        errors.append("revised_block should be object")
    if hca.revised_block.human_condition is None:
        errors.append("revised_block field None")

    # Exception from generate_fn
    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    boom = suggest_sermon_main_idea(
        passage="Jn 3,16",
        passage_text="Mert úgy szerette…",
        text_main_idea="Isten szeretete",
        exegesis="Részletes exegézis anyag.",
        generate_fn=_boom,
        skip_api_if_insufficient=False,
    )
    if boom.ok:
        errors.append("exception should yield ok=False")

    # Prompt placeholders filled
    ctx = build_m4_context(
        passage="Jn 3,16",
        passage_text="szöveg",
        text_main_idea="idea",
        sermon_main_idea="sermon",
    )
    p1 = build_sermon_main_idea_suggest_prompt(ctx)
    if "{{passage}}" in p1 or "{{text_main_idea}}" in p1:
        errors.append("unfilled placeholders in suggest prompt")
    if "Jn 3,16" not in p1:
        errors.append("passage missing from suggest prompt")

    # Truncate JSON without half-cutting invalidly when short enough
    js = json.dumps({"a": 1, "b": ["x"] * 5}, ensure_ascii=False)
    truncated = _safe_truncate_structured(js, max_chars=len(js) + 10)
    if truncated != js and not truncated.endswith("…"):
        try:
            json.loads(truncated)
        except json.JSONDecodeError:
            errors.append("structured truncate broke JSON")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("SELF-CHECK FAILED:")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("sermon_workshop_m4_ai self-check OK")


__all__ = [
    "MISSING",
    "DEFAULT_TEMPERATURE",
    "SermonMainIdeaSuggestionResult",
    "SermonMainIdeaAssessmentResult",
    "HumanConditionSuggestionResult",
    "HumanConditionAssessmentResult",
    "build_m4_context",
    "build_sermon_main_idea_suggest_prompt",
    "build_sermon_main_idea_assess_prompt",
    "build_human_condition_suggest_prompt",
    "build_human_condition_assess_prompt",
    "extract_json_object",
    "parse_sermon_main_idea_suggestions",
    "parse_sermon_main_idea_assessment",
    "parse_human_condition_suggestion",
    "parse_human_condition_assessment",
    "suggest_sermon_main_idea",
    "assess_sermon_main_idea",
    "suggest_human_condition",
    "assess_human_condition",
]
