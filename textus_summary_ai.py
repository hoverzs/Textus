"""Textusösszegzés — MI háttérréteg (a Textusműhely záró, jóváhagyandó bundle-jéhez).

Önálló modul: nem módosítja a befagyasztott elemző promptokat
(exegézis, kortörténet, teológia, eredeti szöveg). A Gemini-hívást a hívó
által átadott `generate_fn`-nel végzi (általában az app.py `generate_text`
függvénye) — ugyanaz a motor, mint minden más Textus AI-modulnál, nem új
párhuzamos gépezet.

A Textusösszegzés a Textusműhely már meglévő, jóváhagyott/piszkozat
anyagából (fő gondolat, exegézis, teológia, kortörténet, RESET 3B-2 óta
eredeti nyelvi megfigyelések is) egyetlen hívással javasol négy mezőt: a
textus alapfeszültségét, a legfontosabb exegetikai felismeréseket, a
teológiai hangsúlyokat és a műfaji/szerkezeti sajátosságokat. A
`main_idea` mezőt nem az MI generálja — az a jóváhagyott `text_main_idea`
egyszerű átvétele.

RESET 3B-2 — EREDETI NYELVI SŰRÍTÉS: a `key_exegetical_findings` mező
KURÁTORI, nem újraelemző szerepet tölt be az "Eredeti szöveg" modul
kimenetére nézve — a szintézis kizárólag a KAPOTT eredeti nyelvi
megfigyelésekből válogathat, ha azok ténylegesen relevánsak, de SOSEM
végez új görög/héber elemzést. Nincs önálló "original_language" mező —
ez SZÁNDÉKOS: a meglévő négy mező sémáját a feladat nem indokolja
bővíteni (ld. az implementáció melletti audit indoklását)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence
from llm_text_utils import is_llm_error_text

MISSING = "nincs adat"

TAB_LABEL_SUGGEST = "Textusösszegzés — javaslat"

# Exegetikai feladat: alacsonyabb kreativitás (session temperature override).
DEFAULT_TEMPERATURE = 0.15

_LIMITS = {
    "passage_text": 4000,
    "text_main_idea": 800,
    "approved_insights": 3000,
    "exegesis": 3200,
    "theology": 2500,
    "historical_context": 1800,
    # RESET 3B-2: az "Eredeti szöveg" modul kimenete jellemzően egyetlen,
    # rövid, összefüggő bekezdés (legfeljebb 5 kiemelt szó egy magyarázó
    # szövegben) — nem igényel akkora keretet, mint az exegézis.
    "original_text": 1500,
}

SUMMARY_SYSTEM_BUNDLE = """\
Te a TEXTUS homiletikai segéd szöveghű exegetikai asszisztense vagy.
Csak a felhasználói feladatban megadott anyagból dolgozz.
Ne egészítsd ki a hiányzó bibliai szöveget vagy elemzést saját emlékezetből.
Válaszod KIZÁRÓLAG érvényes JSON legyen — semmi más szöveg, markdown vagy magyarázat.
Minden string szabályosan escape-elt legyen; az objektumban ne legyen záró vessző.\
"""

GenerateFn = Callable[..., str]


@dataclass
class TextSummarySuggestionResult:
    """Textusösszegzés-javaslat strukturált kimenet."""

    base_tension: str = ""
    key_exegetical_findings: str = ""
    theological_emphases: str = ""
    genre_structure_notes: str = ""
    reasoning_summary: str = ""
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Segédek — szöveg / jelenlét (a textus_main_idea_ai.py mintájára)
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
    return text.casefold() not in {MISSING, "nincs", "n/a", "na", "-", "—"}


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
                if not content:
                    continue
                prefix = f"[{cat}] " if cat else ""
                lines.append(f"- {prefix}{content}")
            else:
                t = _as_text(item)
                if t:
                    lines.append(f"- {t}")
        if not lines:
            return MISSING
        return _display("\n".join(lines), max_chars=max_chars)
    return _display(insights, max_chars=max_chars)


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos is_llm_error_text (llm_text_utils.py; azonosság: tests/test_llm_text_utils.py).
_is_api_error_text = is_llm_error_text


# ---------------------------------------------------------------------------
# Kontextusépítés
# ---------------------------------------------------------------------------


def build_summary_context(
    *,
    passage: str = "",
    passage_text: str = "",
    text_main_idea: str = "",
    text_main_idea_is_fresh: bool = True,
    approved_insights: Any = None,
    exegesis: str = "",
    exegesis_is_fresh: bool = True,
    theology: str = "",
    theology_is_fresh: bool = True,
    historical_context: str = "",
    historical_context_is_fresh: bool = True,
    original_text: str = "",
    original_text_is_fresh: bool = True,
) -> dict[str, str]:
    """Szelektív, címkézett kontextus-dict a promptkitöltéshez.

    Nem módosítja a session állapotot; csak olvas és levág.

    RESET 3B-2 — `original_text`/`original_text_is_fresh`, RESET 3D-1 —
    ugyanez az elv kiterjesztve `exegesis`/`theology`/`historical_context`/
    `text_main_idea`-ra: ez a modul SZÁNDÉKOSAN nem fér hozzá
    `st.session_state`-hez (a hívó adja át a nyers stringeket) — ezért a
    frissesség-ELLENŐRZÉST (a MEGLÉVŐ `*_approved_context_hash`
    kontraktus alapján, ld. `textus_workshop_ui._run_suggest_summary`) is
    a HÍVÓ végzi el, és egyetlen `bool`-t ad át mezőnként. Itt NEM
    számolunk új hash-t — ha egy `*_is_fresh` `False`, a hozzá tartozó
    mezőt EGYSZERŰEN úgy kezeljük, mintha hiányozna (nem kerül a
    promptba), a bemeneti stringet magát nem módosítjuk."""
    effective_original_text = original_text if original_text_is_fresh else ""
    effective_exegesis = exegesis if exegesis_is_fresh else ""
    effective_theology = theology if theology_is_fresh else ""
    effective_historical_context = historical_context if historical_context_is_fresh else ""
    effective_text_main_idea = text_main_idea if text_main_idea_is_fresh else ""
    return {
        "passage": _display(passage, max_chars=200) if _is_present(passage) else MISSING,
        "passage_text": _display(passage_text, max_chars=_LIMITS["passage_text"]),
        "text_main_idea": _display(
            effective_text_main_idea, max_chars=_LIMITS["text_main_idea"]
        ),
        "approved_insights": _format_insights(
            approved_insights, max_chars=_LIMITS["approved_insights"]
        ),
        "exegesis": _display(effective_exegesis, max_chars=_LIMITS["exegesis"]),
        "theology": _display(effective_theology, max_chars=_LIMITS["theology"]),
        "historical_context": _display(
            effective_historical_context, max_chars=_LIMITS["historical_context"]
        ),
        "original_text": _display(
            effective_original_text, max_chars=_LIMITS["original_text"]
        ),
    }


# Javaslatkészítéshez elfogadott minimális források (legalább egy kell).
_SUGGEST_SOURCE_KEYS: tuple[tuple[str, str], ...] = (
    ("passage_text", "bibliai szöveg (passage_text)"),
    ("text_main_idea", "a textus fő gondolata"),
    ("approved_insights", "jóváhagyott felismerések"),
    ("exegesis", "exegézis"),
    ("theology", "teológia"),
)


def _suggest_sources_present(ctx: Mapping[str, str]) -> list[str]:
    return [label for key, label in _SUGGEST_SOURCE_KEYS if _is_present(ctx.get(key, MISSING))]


def _missing_analysis_labels(ctx: Mapping[str, str]) -> list[str]:
    return [
        label for key, label in _SUGGEST_SOURCE_KEYS if not _is_present(ctx.get(key, MISSING))
    ]


def has_sufficient_summary_material(ctx: Mapping[str, str]) -> bool:
    """Van-e elegendő anyag felelős összegzés-javaslat API-híváshoz.

    Minimális feltétel: nem üres `passage`, ÉS legalább egy érdemi forrás
    (exegézis, teológia, fő gondolat, jóváhagyott felismerés vagy
    bibliai szöveg).
    """
    if not _is_present(ctx.get("passage", MISSING)):
        return False
    return bool(_suggest_sources_present(ctx))


# ---------------------------------------------------------------------------
# Promptépítés
# ---------------------------------------------------------------------------


def _fill_placeholders(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", value)
    return out


_SUGGEST_PROMPT_TEMPLATE = """\
Feladatod: a megadott bibliai szakaszhoz TEXTUSÖSSZEGZÉS négy mezőjének javaslata.

Ez a Textusműhely záró, jóváhagyandó összegzése — az Igehirdetési műhely ebből fog dolgozni exegetikai kontextusként, nem futtat újra saját exegézist. Ezért az összegzésnek szöveghűnek, tömörnek és a megadott anyagra kell épülnie.

## A négy mező

1. base_tension — a textus ALAPFESZÜLTSÉGE: milyen belső feszültséget, kérdést, ellentétet vagy problémát hordoz maga a szakasz (nem a mai hallgató élethelyzete, hanem a textus saját belső mozgása/dinamikája). 1-3 mondat.
2. key_exegetical_findings — a legfontosabb exegetikai felismerések tömör, pontokba szedhető összegzése (szerkezet, kulcskifejezések, az állítás logikája). Legfeljebb 5 rövid pont vagy 4-5 mondat. Ha az alább mellékelt eredeti nyelvi megfigyelések között van olyan, ami TÉNYLEGESEN segíti a szakasz értelmezését, tömören építsd be ide, a többi exegetikai megfigyeléssel egy összefüggő gondolatmenetben — ne külön alcímként vagy tételként. Ha nincs ilyen releváns eredeti nyelvi megfigyelés, egyszerűen hagyd ki: ne erőltess bele semmit csak azért, mert kaptál eredeti nyelvi anyagot.
3. theological_emphases — a textus legfontosabb teológiai hangsúlyai, tömören. Legfeljebb 4-5 mondat.
4. genre_structure_notes — a szakasz műfaja és szerkezeti sajátosságai (pl. elbeszélés/levél/próféta/költői szöveg; felépítés, fordulópontok). 2-4 mondat.

## Források súlya

Elsődleges: a rendelkezésre bocsátott bibliai szöveg ({{passage_text}}), ha van; a jóváhagyott/piszkozat fő gondolat; az exegézis.
Fontos kiegészítő: teológiai elemzés; jóváhagyott felismerések.
Csak akkor vedd figyelembe, ha ténylegesen szükséges: kortörténeti háttér; eredeti nyelvi megfigyelések.

## Abszolút tilalmak

- Ne találj ki görög/héber nyelvi adatot, kortörténetet, kommentárt.
- Ne hivatkozz nem megadott szakirodalomra.
- Ne moralizálj, ne írj alkalmazást, ne szólítsd meg a hallgatót.
- Ne keverd a base_tension mezőbe a mai hallgatói élethelyzetet — az a textus SAJÁT belső feszültsége, nem homiletikai belépési pont.
- Ha egy adatforrás „nincs adat” vagy üres: ne találj ki helyette semmit.
- Ne adj belső gondolatmenetet vagy hosszú érvelést; a reasoning_summary legyen rövid.
- Eredeti nyelvi (görög/héber) információt KIZÁRÓLAG az alább mellékelt eredeti nyelvi megfigyelésekből emelhetsz át — SOHA ne találj ki, ne egészíts ki és ne pontosíts saját emlékezetből új lemmát, morfológiai vagy lexikai adatot. Nem a te feladatod új nyelvi elemzést végezni, kizárólag a KAPOTT megfigyelésekből azt kiválasztani és sűríteni, ami ténylegesen releváns. Ne ismételd meg a teljes mellékelt eredeti nyelvi elemzést — csak a ténylegesen legfontosabb, a szakasz értelmezését segítő pontot/pontokat vedd át, tömören.
- Ha a mellékelt exegézis, kortörténet vagy teológia egy állítást vitatottként, bizonytalanként vagy több legitim értelmezés egyikeként kezel, az összegzés (különösen a key_exegetical_findings és a theological_emphases) NE emelje ezt kategorikus, eldöntött tényként — a bizonytalanságot rövid formában (pl. "vitatott, hogy...", "a hagyomány többféleképpen érti...") tartsd meg, ne old fel csendben.

## Elégtelen adat

Ha sem a bibliai szöveg, sem az exegézis, sem a teológia, sem a fő gondolat, sem a jóváhagyott felismerések között nincs érdemi tartalom, mind a négy mező legyen üres string: "". Ilyenkor a hiányt a missing_information és a reasoning_summary jelezze.

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

A textus fő gondolata (jóváhagyott vagy piszkozat):
{{text_main_idea}}

Jóváhagyott felismerések:
{{approved_insights}}

Exegézis:
{{exegesis}}

Teológiai elemzés:
{{theology}}

Eredeti nyelvi megfigyelések, ha rendelkezésre állnak (csak akkor emelj át belőle, ha ténylegesen releváns — ne találj ki újat, ne ismételd meg a teljeset):
{{original_text}}

Kortörténeti háttér (csak ha releváns):
{{historical_context}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül, nincs markdown/kódblokk.
- Minden mező kötelező; ha nincs elem egy listában, üres listát adj: [].
- Minden JSON-string legyen szabályosan escape-elt, érvényes JSON-érték.
- Az objektumban ne legyen záró vessző (trailing comma).
- A JSON-kulcsok pontosan az alábbi angol nevek legyenek.

Séma:

{
  "base_tension": "string",
  "key_exegetical_findings": "string",
  "theological_emphases": "string",
  "genre_structure_notes": "string",
  "reasoning_summary": "string",
  "warnings": ["string"],
  "missing_information": ["string"]
}
"""


def build_summary_suggest_prompt(ctx: Mapping[str, str]) -> str:
    return _fill_placeholders(_SUGGEST_PROMPT_TEMPLATE, ctx)


# ---------------------------------------------------------------------------
# JSON kinyerés és validáció
# ---------------------------------------------------------------------------


def extract_json_object(raw: str) -> dict[str, Any] | None:
    """Nyers modellválaszból JSON-objektum kinyerése (markdown fence tűréssel)."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
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


def fallback_summary(
    *,
    reasoning: str,
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> TextSummarySuggestionResult:
    return TextSummarySuggestionResult(
        base_tension="",
        key_exegetical_findings="",
        theological_emphases="",
        genre_structure_notes="",
        reasoning_summary=reasoning,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def parse_summary_suggestion(raw: str) -> TextSummarySuggestionResult:
    """Összegzés-javaslat JSON parse + sémaellenőrzés; hibánál biztonságos fallback."""
    if _is_api_error_text(raw):
        return fallback_summary(
            reasoning="A modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )

    obj = extract_json_object(raw)
    if obj is None:
        return fallback_summary(
            reasoning="A válasz nem dolgozható fel érvényes JSON-ként.",
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )

    reasoning = _as_text(obj.get("reasoning_summary"))
    if not reasoning:
        reasoning = "A modell nem adott indoklást."

    return TextSummarySuggestionResult(
        base_tension=_as_text(obj.get("base_tension")),
        key_exegetical_findings=_as_text(obj.get("key_exegetical_findings")),
        theological_emphases=_as_text(obj.get("theological_emphases")),
        genre_structure_notes=_as_text(obj.get("genre_structure_notes")),
        reasoning_summary=reasoning,
        warnings=_as_str_list(obj.get("warnings")),
        missing_information=_as_str_list(obj.get("missing_information")),
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


# ---------------------------------------------------------------------------
# Gemini-hívás wrapper (a textus_main_idea_ai.py mintájára)
# ---------------------------------------------------------------------------


def _call_generate(
    generate_fn: GenerateFn,
    prompt: str,
    *,
    tab_label: str,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> str:
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
        return generate_fn(
            prompt,
            enable_google_search=False,
            tab_label=tab_label,
            use_cache=False,
            system_bundle=SUMMARY_SYSTEM_BUNDLE,
            include_brevity_directive=False,
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


def suggest_text_summary(
    *,
    passage: str,
    passage_text: str = "",
    text_main_idea: str = "",
    text_main_idea_is_fresh: bool = True,
    approved_insights: Any = None,
    exegesis: str = "",
    exegesis_is_fresh: bool = True,
    theology: str = "",
    theology_is_fresh: bool = True,
    historical_context: str = "",
    historical_context_is_fresh: bool = True,
    original_text: str = "",
    original_text_is_fresh: bool = True,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> TextSummarySuggestionResult:
    """Textusösszegzés-javaslat (base_tension + 3 kísérő mező) egy hívásban.

    `generate_fn`: tipikusan az app.py `generate_text` függvénye.

    `original_text_is_fresh`/`exegesis_is_fresh`/`theology_is_fresh`/
    `historical_context_is_fresh`/`text_main_idea_is_fresh`: a hívó
    (`textus_workshop_ui._run_suggest_summary`) a MEGLÉVŐ
    `*_approved_context_hash` kontraktusok alapján dönti el mezőnként, és
    `False`-t ad át azokra, amelyek kimenete már NEM a jelenlegi
    igehelyhez/textushoz tartozik (RESET 3B-2 az `original_text`-re,
    RESET 3D-1 a többi négy mezőre) — ez a modul maga nem fér hozzá
    session_state-hez, ezért nem számol hash-t, csak a kapott döntéseket
    alkalmazza (ld. `build_summary_context`)."""
    ctx = build_summary_context(
        passage=passage,
        passage_text=passage_text,
        text_main_idea=text_main_idea,
        text_main_idea_is_fresh=text_main_idea_is_fresh,
        approved_insights=approved_insights,
        exegesis=exegesis,
        exegesis_is_fresh=exegesis_is_fresh,
        theology=theology,
        theology_is_fresh=theology_is_fresh,
        historical_context=historical_context,
        historical_context_is_fresh=historical_context_is_fresh,
        original_text=original_text,
        original_text_is_fresh=original_text_is_fresh,
    )

    if not _is_present(ctx["passage"]):
        return fallback_summary(
            reasoning="Nincs megadva igehely-megjelölés; javaslat nem indítható.",
            warnings=["Az igehely (passage) hiányzik."],
            missing=["igehely-megjelölés (passage)"],
            error_message="Hiányzó igehely.",
            ok=False,
        )

    missing = _missing_analysis_labels(ctx)
    if skip_api_if_insufficient and not has_sufficient_summary_material(ctx):
        return fallback_summary(
            reasoning=(
                "Nincs elegendő rendelkezésre bocsátott bibliai szöveg vagy "
                "elemzési anyag felelős textusösszegzéshez. A modell nem "
                "egészíti ki a hiányt saját emlékezetből."
            ),
            warnings=["Elégtelen adat: felelős javaslat helyett üres mezők."],
            missing=missing or ["elemzési anyag"],
            ok=True,
        )

    if generate_fn is None:
        return fallback_summary(
            reasoning="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )

    prompt = build_summary_suggest_prompt(ctx)
    try:
        raw = _call_generate(
            generate_fn,
            prompt,
            tab_label=TAB_LABEL_SUGGEST,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001 — UI ne dőljön el
        return fallback_summary(
            reasoning="A javaslatkészítés közben váratlan hiba történt.",
            warnings=[f"Váratlan hiba: {exc}"],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )

    return parse_summary_suggestion(raw or "")


# ---------------------------------------------------------------------------
# Smoke / önellenőrzés (API nélkül)
# ---------------------------------------------------------------------------


def _self_check() -> list[str]:
    errors: list[str] = []

    called = {"n": 0}

    def _should_not_run(*_a, **_k):
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    r = suggest_text_summary(passage="Jn 3,16–21", generate_fn=_should_not_run)
    if called["n"] != 0:
        errors.append("insufficient suggest still called API")
    if r.base_tension or r.key_exegetical_findings:
        errors.append("insufficient suggest should be empty")
    if not r.missing_information:
        errors.append("insufficient suggest missing_information empty")

    raw = (
        '```json\n{"base_tension":"BT","key_exegetical_findings":"KF",'
        '"theological_emphases":"TE","genre_structure_notes":"GS",'
        '"reasoning_summary":"Ok.","warnings":[],"missing_information":[]}\n```'
    )
    p = parse_summary_suggestion(raw)
    if not p.ok or p.base_tension != "BT" or p.genre_structure_notes != "GS":
        errors.append("summary parse failed")

    bad = parse_summary_suggestion("ez nem json")
    if bad.ok or bad.base_tension:
        errors.append("bad json should fallback")

    called["n"] = 0

    def _gen(*_a, **_k):
        called["n"] += 1
        return json.dumps(
            {
                "base_tension": "A szakasz feszültsége a sötétség és világosság között.",
                "key_exegetical_findings": "A mondat szerkezete kiemeli Isten cselekvését.",
                "theological_emphases": "Isten szeretete megelőzi az emberi választ.",
                "genre_structure_notes": "Elbeszélő keretbe ágyazott teológiai kijelentés.",
                "reasoning_summary": "Az exegézis és a fő gondolat alapján.",
                "warnings": [],
                "missing_information": [],
            },
            ensure_ascii=False,
        )

    rr = suggest_text_summary(
        passage="Jn 3,16",
        exegesis="A szakasz a világosság és sötétség ellentétén keresztül mutatja be Isten szeretetét.",
        generate_fn=_gen,
    )
    if called["n"] != 1 or not rr.base_tension:
        errors.append("exegesis-only suggest should call API and yield base_tension")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("SELF-CHECK FAILED:")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("textus_summary_ai self-check OK")
