"""Igehirdetési műhely M5 — Hallgatói kérdés és feszültség MI-háttér.

Önálló modul: nem importál app.py / sermon_workshop_ui.py fájlból.
A Gemini-hívást a hívó `generate_fn` paramétere végzi.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence

from sermon_workshop_m4_ai import extract_json_object
from llm_text_utils import is_llm_error_text

MISSING = "nincs adat"
TAB_SUGGEST = "Hallgatói feszültség — javaslat"
TAB_ASSESS = "Hallgatói feszültség — értékelés"
DEFAULT_TEMPERATURE = 0.15

_LIMITS = {
    "passage_text": 3000,
    "approved_insights": 3000,
    "exegesis": 2800,
    "theology": 2200,
    "text_main_idea": 1200,
    "text_expanded_summary": 2000,
    "sermon_main_idea": 1200,
    "sermon_expanded_summary": 2000,
    "human_condition_block": 2200,
    "listener_block": 2000,
    "occasion": 400,
    "user_focus": 800,
}

M5_SYSTEM_BUNDLE = """\
Te a TEXTUS homiletikai segéd szöveghű asszisztense vagy.
Csak a megadott műhelyanyagból dolgozz. Ne találj ki bibliai szöveget,
demográfiai vagy pszichológiai adatot.
Válaszod KIZÁRÓLAG érvényes JSON legyen.\
"""

GenerateFn = Callable[..., str]


@dataclass
class ListenerTensionAlternativeSet:
    listener_question: str = ""
    listener_resistance: str = ""
    tension: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def to_ui_block(self) -> dict[str, str]:
        return {
            "listener_question": self.listener_question,
            "listener_resistance": self.listener_resistance,
            "sermon_tension": self.tension,
        }


@dataclass
class ListenerTensionSuggestionResult:
    recommended_listener_question: str = ""
    recommended_listener_resistance: str = ""
    recommended_tension: str = ""
    expanded_summary: str = ""
    alternative_sets: list[ListenerTensionAlternativeSet] = field(
        default_factory=list
    )
    reasoning_summary: str = ""
    basis: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_ui_block(self) -> dict[str, str]:
        return {
            "listener_question": self.recommended_listener_question,
            "listener_resistance": self.recommended_listener_resistance,
            "sermon_tension": self.recommended_tension,
        }


@dataclass
class ListenerTensionAssessmentResult:
    overall_assessment: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    revised_listener_question: str = ""
    revised_listener_resistance: str = ""
    revised_tension: str = ""
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def revised_to_ui_block(self) -> dict[str, str]:
        return {
            "listener_question": self.revised_listener_question,
            "listener_resistance": self.revised_listener_resistance,
            "sermon_tension": self.revised_tension,
        }


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


def _format_human_block(block: Any) -> str:
    if not isinstance(block, Mapping):
        return MISSING
    labels = (
        ("condition", "Emberi helyzet"),
        ("false_response", "Téves vagy elégtelen válasz"),
        ("human_need", "Emberi szükség"),
        ("divine_action", "Isten cselekvése"),
        ("grace_response", "Kegyelmi válasz"),
    )
    lines: list[str] = []
    any_present = False
    for key, label in labels:
        val = _as_text(block.get(key))
        if val:
            any_present = True
            lines.append(f"{label}: {val}")
        else:
            lines.append(f"{label}: {MISSING}")
    if not any_present:
        return MISSING
    return _display("\n".join(lines), max_chars=_LIMITS["human_condition_block"])


def _format_listener_block(block: Any) -> str:
    if not isinstance(block, Mapping):
        return MISSING
    labels = (
        ("listener_question", "Hallgatói kérdés"),
        ("listener_resistance", "Hallgatói ellenállás"),
        ("sermon_tension", "Központi feszültség"),
    )
    lines: list[str] = []
    any_present = False
    for key, label in labels:
        val = _as_text(block.get(key))
        if val:
            any_present = True
            lines.append(f"{label}: {val}")
        else:
            lines.append(f"{label}: {MISSING}")
    if not any_present:
        return MISSING
    return _display("\n".join(lines), max_chars=_LIMITS["listener_block"])


def _safe_truncate(text: str, max_chars: int) -> str:
    raw = _as_text(text)
    if not raw:
        return MISSING
    if len(raw) <= max_chars:
        return raw
    stripped = raw.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            parsed = json.loads(raw)
            compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
            if len(compact) <= max_chars:
                return compact
            return compact[: max_chars - 1].rstrip() + "…"
        except json.JSONDecodeError:
            pass
    return raw[: max_chars - 1].rstrip() + "…"


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos is_llm_error_text (llm_text_utils.py; azonosság: tests/test_llm_text_utils.py).
# KOMPATIBILITÁSI ALIAS — 14 modul innen importálja (`from sermon_workshop_m5_ai
# import _is_api_error_text`); a név ne tűnjön el.
_is_api_error_text = is_llm_error_text


def _as_str_list(value: Any, *, max_items: int | None = None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        out = [value.strip()] if value.strip() else []
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        out = [_as_text(x) for x in value if _as_text(x)]
    else:
        s = _as_text(value)
        out = [s] if s else []
    if max_items is not None:
        out = out[:max_items]
    return out


def build_m5_context(
    *,
    passage: str = "",
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    text_expanded_summary: str = "",
    approved_insights: Any = None,
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
    sermon_expanded_summary: str = "",
    human_condition: Any = None,
    listener_tension: Any = None,
    exegesis: str = "",
    theology: str = "",
) -> dict[str, str]:
    """M5 kontextus — illusztráció / aktualizálás / ének / vázlat nélkül.

    A fő gondolatokat csak jóváhagyott státusz esetén adja át tartalomként.
    """
    text_status = _as_text(text_main_idea_status).casefold()
    sermon_status = _as_text(sermon_main_idea_status).casefold()
    text_idea = (
        _display(text_main_idea, max_chars=_LIMITS["text_main_idea"])
        if text_status == "approved" and _is_present(text_main_idea)
        else MISSING
    )
    sermon_idea = (
        _display(sermon_main_idea, max_chars=_LIMITS["sermon_main_idea"])
        if sermon_status == "approved" and _is_present(sermon_main_idea)
        else MISSING
    )
    text_exp = (
        _display(text_expanded_summary, max_chars=_LIMITS["text_expanded_summary"])
        if text_idea != MISSING and _is_present(text_expanded_summary)
        else MISSING
    )
    sermon_exp = (
        _display(
            sermon_expanded_summary, max_chars=_LIMITS["sermon_expanded_summary"]
        )
        if sermon_idea != MISSING and _is_present(sermon_expanded_summary)
        else MISSING
    )
    return {
        "passage": _display(passage, max_chars=200) if _is_present(passage) else MISSING,
        "passage_text": _display(passage_text, max_chars=_LIMITS["passage_text"]),
        "occasion": _display(occasion, max_chars=_LIMITS["occasion"]),
        "user_focus": _display(user_focus, max_chars=_LIMITS["user_focus"]),
        "text_main_idea": text_idea,
        "text_main_idea_status": (
            _display(text_main_idea_status, max_chars=40)
            if _is_present(text_main_idea_status)
            else MISSING
        ),
        "text_expanded_summary": text_exp,
        "approved_insights": _format_insights(
            approved_insights, max_chars=_LIMITS["approved_insights"]
        ),
        "sermon_main_idea": sermon_idea,
        "sermon_main_idea_status": (
            _display(sermon_main_idea_status, max_chars=40)
            if _is_present(sermon_main_idea_status)
            else MISSING
        ),
        "sermon_expanded_summary": sermon_exp,
        "human_condition_block": _format_human_block(human_condition),
        "listener_tension_block": _format_listener_block(listener_tension),
        "exegesis": (
            _safe_truncate(exegesis, _LIMITS["exegesis"])
            if _is_present(exegesis)
            else MISSING
        ),
        "theology": (
            _safe_truncate(theology, _LIMITS["theology"])
            if _is_present(theology)
            else MISSING
        ),
    }


def _has_approved_idea(ctx: Mapping[str, str]) -> bool:
    return _is_present(ctx.get("text_main_idea")) or _is_present(
        ctx.get("sermon_main_idea")
    )


def _extra_sources_present(ctx: Mapping[str, str]) -> list[str]:
    keys = (
        ("approved_insights", "jóváhagyott felismerések"),
        ("human_condition_block", "emberi helyzet / kegyelmi válasz"),
        ("text_expanded_summary", "textus fő gondolat rövid kifejtése"),
        ("sermon_expanded_summary", "igehirdetési fő gondolat rövid kifejtése"),
        ("exegesis", "exegézis"),
        ("theology", "teológia"),
    )
    # Emberi helyzet: csak ha van érdemi tartalom a blokkban
    present: list[str] = []
    for key, label in keys:
        if _is_present(ctx.get(key, MISSING)):
            present.append(label)
    return present


def _missing_m5_labels(ctx: Mapping[str, str]) -> list[str]:
    missing: list[str] = []
    if not _is_present(ctx.get("passage", MISSING)):
        missing.append("igehely-megjelölés (passage)")
    if not _has_approved_idea(ctx):
        missing.append(
            "jóváhagyott textus- vagy igehirdetési fő gondolat"
        )
    if not _extra_sources_present(ctx):
        missing.append(
            "további érdemi forrás (felismerés, emberi helyzet, "
            "kifejtés, exegézis vagy teológia)"
        )
    return missing


def has_sufficient_m5_material(ctx: Mapping[str, str]) -> bool:
    if not _is_present(ctx.get("passage", MISSING)):
        return False
    if not _has_approved_idea(ctx):
        return False
    return bool(_extra_sources_present(ctx))


_SUGGEST_TEMPLATE = """\
Feladatod: a HALLGATÓI KÉRDÉS, a HALLGATÓI ELLENÁLLÁS és a KÖZPONTI
HOMILETIKAI FESZÜLTSÉG megfogalmazása.

Ez NEM mesterséges dráma, NEM hatásvadász konfliktus, NEM prédikációvázlat,
NEM alkalmazáslista, NEM kegyelmi feloldás, NEM Krisztus-kapcsolat szakasz.

## Fogalom — három külön elem

1) Hallgatói kérdés (`recommended_listener_question`):
- a textus / igehirdetési fő gondolat hallatán őszintén megszülető kérdés;
- természetes, kimondható, lehetőleg egyetlen kérdő mondat;
- NE tartalmazza előre a választ;
- NE legyen vizsgakérdés vagy retorikai trükk.

2) Hallgatói ellenállás (`recommended_listener_resistance`):
- miért nehéz elfogadni vagy megélni a textus állítását;
- együttérző, de őszinte; 1–2 mondat;
- NE ítélkezzen; NE szégyenítse meg a hallgatót;
- NE legyen általánosítás („a mai ember már semmiben sem hisz”).

3) Központi feszültség (`recommended_tension`):
- egyetlen világos állító mondat;
- a textus igazsága és a hallgató megélt valósága közötti távolság;
- MÉG NE tartalmazza a feloldást;
- NE ismételje a kérdést vagy az ellenállást más szavakkal.

A három elem NE legyen ugyanannak a mondatnak három változata.
NE ismételd puszta átfogalmazásként a korábbi emberi helyzet blokkot.

## expanded_summary

3–4 rövid, összefüggő mondatban magyarázd el:
- hogyan függ össze a kérdés, az ellenállás és a feszültség;
- milyen felismerési irányt nyithat meg az igehirdetésben.
TILOS:
- a feszültség feloldása;
- kegyelmi válasz megírása;
- prédikációvázlat vagy alkalmazáslista;
- Krisztus-kapcsolat erőltetése;
- a három ajánlott mondat szó szerinti ismétlése.

## Alternatívák

`alternative_sets`: legfeljebb két teljes hármas
(listener_question, listener_resistance, tension).
Csak valódi hangsúlyeltérés esetén. Ha nincs: [].

## Tilalmak

- Mesterséges / hatásvadász konfliktus.
- Textus által nem megalapozott feszültség.
- Hallgató megszégyenítése, diagnózis, kitalált demográfia/pszichológia.
- Moralizáló felszólítás; túl korai evangéliumi/krisztológiai feloldás.
- Ne találj ki bibliai idézetet, görög/héber vagy történeti adatot.
- A passage_text hiánya önmagában NEM elégtelen adat, ha van jóváhagyott
  műhelyeredmény; jelezd figyelmeztetésben.

## Elégtelen adat

Csak akkor legyen üres recommended_* / expanded_summary / alternative_sets,
ha a rendelkezésre álló anyagból nem lehet felelősen megkülönböztetni
a textus állítását és a hallgatói helyzetet. Ilyenkor töltsd a
warnings és missing_information mezőket.

## Bemeneti anyag

Igehely: {{passage}}
Bibliai szöveg (ha van): {{passage_text}}
Alkalom / szempont: {{occasion}} / {{user_focus}}

Jóváhagyott textus fő gondolata: {{text_main_idea}}
Textus fő gondolat rövid kifejtése: {{text_expanded_summary}}
Jóváhagyott felismerések: {{approved_insights}}

Jóváhagyott igehirdetési fő gondolat: {{sermon_main_idea}}
Igehirdetési fő gondolat rövid kifejtése: {{sermon_expanded_summary}}

Emberi helyzet és kegyelmi válasz: {{human_condition_block}}

Exegézis (részlet): {{exegesis}}
Teológia (részlet): {{theology}}

## Kimenet — KIZÁRÓLAG érvényes JSON

{
  "recommended_listener_question": "string",
  "recommended_listener_resistance": "string",
  "recommended_tension": "string",
  "expanded_summary": "string",
  "alternative_sets": [
    {
      "listener_question": "string",
      "listener_resistance": "string",
      "tension": "string"
    }
  ],
  "reasoning_summary": "string",
  "basis": ["string"],
  "warnings": ["string"],
  "missing_information": ["string"]
}
"""

_ASSESS_TEMPLATE = """\
Feladatod: a felhasználó HALLGATÓI KÉRDÉS / ELLENÁLLÁS / FESZÜLTSÉG
megfogalmazásának értékelése.

Ne írd felül automatikusan. Adj szakmai értékelést és — ha felelősen
lehetséges — javított javaslatokat. A döntés a prédikátoré.

## Vizsgálandó szempontok

- a hallgatói kérdés természetessége (nem tartalmazza-e már a választ);
- az ellenállás realitása és együttérző megfogalmazása;
- a feszültség textushűsége;
- a három elem közötti különbség és összhang;
- a feszültség nincs-e már túl korán feloldva (evangéliumi/krisztológiai);
- nem ismétli-e csupán a fő gondolatot vagy az emberi helyzetet;
- nincs-e megszégyenítés, általánosítás, moralizálás.

## revised_* szabályai

- Csak ha van elegendő alap; különben "".
- Ne adj új, a bemenetben nem szereplő teológiai állítást.
- A revised_tension még ne oldja fel a feszültséget.

## Bemeneti anyag

Igehely: {{passage}}
Bibliai szöveg (ha van): {{passage_text}}

Jóváhagyott textus fő gondolata: {{text_main_idea}}
Textus rövid kifejtés: {{text_expanded_summary}}
Jóváhagyott felismerések: {{approved_insights}}

Jóváhagyott igehirdetési fő gondolat: {{sermon_main_idea}}
Igehirdetési rövid kifejtés: {{sermon_expanded_summary}}

Emberi helyzet és kegyelmi válasz: {{human_condition_block}}

Exegézis / teológia: {{exegesis}} / {{theology}}

A felhasználó megfogalmazása:
{{listener_tension_block}}

## Kimenet — KIZÁRÓLAG érvényes JSON

{
  "overall_assessment": "string",
  "strengths": ["string"],
  "improvements": ["string"],
  "revised_listener_question": "string",
  "revised_listener_resistance": "string",
  "revised_tension": "string",
  "warnings": ["string"]
}
"""


def _fill(template: str, ctx: Mapping[str, str]) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def build_listener_tension_suggest_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_SUGGEST_TEMPLATE, ctx)


def build_listener_tension_assess_prompt(ctx: Mapping[str, str]) -> str:
    return _fill(_ASSESS_TEMPLATE, ctx)


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
            system_bundle=M5_SYSTEM_BUNDLE,
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


def fallback_listener_tension_suggestion(
    *,
    reasoning: str = "",
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> ListenerTensionSuggestionResult:
    return ListenerTensionSuggestionResult(
        reasoning_summary=reasoning,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def fallback_listener_tension_assessment(
    *,
    overall: str = "",
    warnings: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> ListenerTensionAssessmentResult:
    return ListenerTensionAssessmentResult(
        overall_assessment=overall
        or "Nem megítélhető — nincs elegendő értékelhető megfogalmazás.",
        warnings=list(warnings or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def _parse_alt_sets(raw: Any) -> list[ListenerTensionAlternativeSet]:
    if not isinstance(raw, list):
        return []
    out: list[ListenerTensionAlternativeSet] = []
    for item in raw[:2]:
        if not isinstance(item, dict):
            continue
        q = _as_text(item.get("listener_question"))
        r = _as_text(item.get("listener_resistance"))
        t = _as_text(item.get("tension"))
        if not (q or r or t):
            continue
        out.append(
            ListenerTensionAlternativeSet(
                listener_question=q,
                listener_resistance=r,
                tension=t,
            )
        )
    return out


def parse_listener_tension_suggestions(raw: str) -> ListenerTensionSuggestionResult:
    if _is_api_error_text(raw):
        return fallback_listener_tension_suggestion(
            reasoning="A modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw)
    if obj is None:
        return fallback_listener_tension_suggestion(
            reasoning="A válasz nem dolgozható fel érvényes JSON-ként.",
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )
    q = _as_text(obj.get("recommended_listener_question"))
    r = _as_text(obj.get("recommended_listener_resistance"))
    t = _as_text(obj.get("recommended_tension"))
    expanded = _as_text(obj.get("expanded_summary"))
    if not (q or r or t):
        expanded = ""
    return ListenerTensionSuggestionResult(
        recommended_listener_question=q,
        recommended_listener_resistance=r,
        recommended_tension=t,
        expanded_summary=expanded,
        alternative_sets=_parse_alt_sets(obj.get("alternative_sets")),
        reasoning_summary=_as_text(obj.get("reasoning_summary")),
        basis=_as_str_list(obj.get("basis"), max_items=6),
        warnings=_as_str_list(obj.get("warnings")),
        missing_information=_as_str_list(obj.get("missing_information")),
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


def parse_listener_tension_assessment(raw: str) -> ListenerTensionAssessmentResult:
    if _is_api_error_text(raw):
        return fallback_listener_tension_assessment(
            overall="Nem megítélhető — a modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )
    obj = extract_json_object(raw)
    if obj is None:
        return fallback_listener_tension_assessment(
            overall="Nem megítélhető — érvénytelen JSON.",
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )
    return ListenerTensionAssessmentResult(
        overall_assessment=_as_text(obj.get("overall_assessment"))
        or "A modell nem adott összegző értékelést.",
        strengths=_as_str_list(obj.get("strengths"), max_items=4),
        improvements=_as_str_list(obj.get("improvements"), max_items=4),
        revised_listener_question=_as_text(obj.get("revised_listener_question")),
        revised_listener_resistance=_as_text(
            obj.get("revised_listener_resistance")
        ),
        revised_tension=_as_text(obj.get("revised_tension")),
        warnings=_as_str_list(obj.get("warnings")),
        ok=True,
        error_message="",
        raw_response=raw or "",
    )


def suggest_listener_tension(
    *,
    passage: str,
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    text_expanded_summary: str = "",
    approved_insights: Any = None,
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
    sermon_expanded_summary: str = "",
    human_condition: Any = None,
    exegesis: str = "",
    theology: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> ListenerTensionSuggestionResult:
    ctx = build_m5_context(
        passage=passage,
        passage_text=passage_text,
        occasion=occasion,
        user_focus=user_focus,
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        text_expanded_summary=text_expanded_summary,
        approved_insights=approved_insights,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
        sermon_expanded_summary=sermon_expanded_summary,
        human_condition=human_condition,
        exegesis=exegesis,
        theology=theology,
    )
    missing = _missing_m5_labels(ctx)
    if not _is_present(ctx["passage"]):
        return fallback_listener_tension_suggestion(
            reasoning="Nincs megadva igehely-megjelölés; javaslat nem indítható.",
            warnings=["Az igehely (passage) hiányzik."],
            missing=missing,
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if skip_api_if_insufficient and not has_sufficient_m5_material(ctx):
        return fallback_listener_tension_suggestion(
            reasoning=(
                "Nincs elegendő jóváhagyott műhelyeredmény a felelős "
                "hallgatói kérdés és feszültség megfogalmazásához."
            ),
            warnings=[
                "Elégtelen adat: felelős javaslat helyett üres ajánlások."
            ],
            missing=missing,
            ok=True,
        )
    if generate_fn is None:
        return fallback_listener_tension_suggestion(
            reasoning="Nincs bekötött Gemini-hívó függvény (generate_fn).",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            missing=missing,
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_listener_tension_suggest_prompt(ctx)
    try:
        raw = _call_generate(
            generate_fn, prompt, tab_label=TAB_SUGGEST, temperature=temperature
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_listener_tension_suggestion(
            reasoning="A javaslatkészítés közben váratlan hiba történt.",
            warnings=["A javaslatkészítés nem sikerült. Próbáld újra később."],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )
    result = parse_listener_tension_suggestions(raw or "")
    if result.ok and not _is_present(ctx.get("passage_text")):
        note = (
            "A teljes bibliai szöveg (passage_text) nem állt közvetlenül "
            "rendelkezésre; a javaslat a jóváhagyott műhelyeredményekből készült."
        )
        if note not in result.warnings and (
            result.recommended_listener_question
            or result.recommended_tension
        ):
            result.warnings = list(result.warnings) + [note]
        label = "bibliai szöveg (passage_text)"
        if label not in result.missing_information:
            result.missing_information = list(result.missing_information) + [label]
    return result


def assess_listener_tension(
    *,
    passage: str,
    listener_tension: Any,
    passage_text: str = "",
    occasion: str = "",
    user_focus: str = "",
    text_main_idea: str = "",
    text_main_idea_status: str = "",
    text_expanded_summary: str = "",
    approved_insights: Any = None,
    sermon_main_idea: str = "",
    sermon_main_idea_status: str = "",
    sermon_expanded_summary: str = "",
    human_condition: Any = None,
    exegesis: str = "",
    theology: str = "",
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
) -> ListenerTensionAssessmentResult:
    block_text = _format_listener_block(listener_tension)
    if block_text == MISSING:
        return fallback_listener_tension_assessment(
            overall="Nem megítélhető — a felhasználói megfogalmazás üres.",
            warnings=["Üres hallgatói feszültség blokk — nincs mit értékelni."],
            ok=True,
        )
    ctx = build_m5_context(
        passage=passage,
        passage_text=passage_text,
        occasion=occasion,
        user_focus=user_focus,
        text_main_idea=text_main_idea,
        text_main_idea_status=text_main_idea_status,
        text_expanded_summary=text_expanded_summary,
        approved_insights=approved_insights,
        sermon_main_idea=sermon_main_idea,
        sermon_main_idea_status=sermon_main_idea_status,
        sermon_expanded_summary=sermon_expanded_summary,
        human_condition=human_condition,
        listener_tension=listener_tension,
        exegesis=exegesis,
        theology=theology,
    )
    if not _is_present(ctx["passage"]):
        return fallback_listener_tension_assessment(
            overall="Nem megítélhető — hiányzik az igehely.",
            warnings=["Az igehely (passage) hiányzik."],
            error_message="Hiányzó igehely.",
            ok=False,
        )
    if generate_fn is None:
        return fallback_listener_tension_assessment(
            overall="Nem megítélhető — nincs bekötött Gemini-hívó.",
            warnings=["A háttérréteg generate_fn nélkül nem indít API-hívást."],
            error_message="Hiányzó generate_fn.",
            ok=False,
        )
    prompt = build_listener_tension_assess_prompt(ctx)
    try:
        raw = _call_generate(
            generate_fn, prompt, tab_label=TAB_ASSESS, temperature=temperature
        )
    except Exception as exc:  # noqa: BLE001
        return fallback_listener_tension_assessment(
            overall="Nem megítélhető — váratlan hiba történt.",
            warnings=["Az értékelés nem sikerült. Próbáld újra később."],
            error_message=str(exc),
            ok=False,
        )
    return parse_listener_tension_assessment(raw or "")


def _self_check() -> list[str]:
    errors: list[str] = []
    called = {"n": 0}

    def _should_not(*_a, **_k):
        called["n"] += 1
        return "NO"

    # C) csak passage
    r = suggest_listener_tension(passage="Jn 3,16", generate_fn=_should_not)
    if called["n"] != 0 or r.recommended_listener_question:
        errors.append("C: passage-only should stay empty")

    # A) teljes kontextus → API
    called["n"] = 0

    def _gen(*_a, **_k):
        called["n"] += 1
        return json.dumps(
            {
                "recommended_listener_question": "Hogyan maradhatok meg a hitben?",
                "recommended_listener_resistance": "Könnyebb a környezetet hibáztatni.",
                "recommended_tension": "Isten a megmaradásra hív, a hallgató gyengének érzi hitét.",
                "expanded_summary": "Egy. Kettő. Három. Négy.",
                "alternative_sets": [
                    {
                        "listener_question": "Miért ilyen nehéz hinni?",
                        "listener_resistance": "A félelem elkerülést szül.",
                        "tension": "A textus bátorságot kér, a hallgató biztonságot keres.",
                    }
                ],
                "reasoning_summary": "Ok.",
                "basis": ["Textus fő gondolata — x"],
                "warnings": [],
                "missing_information": [],
            },
            ensure_ascii=False,
        )

    ra = suggest_listener_tension(
        passage="Jn 3,16",
        text_main_idea="Isten szeretete világosságba hív.",
        text_main_idea_status="approved",
        sermon_main_idea="Isten szeretete világosságba hívja a hallgatót.",
        sermon_main_idea_status="approved",
        human_condition={
            "condition": "Sötétségben élő ember",
            "grace_response": "Hit által élni",
        },
        approved_insights=[{"content": "Isten szeret", "approved": True}],
        generate_fn=_gen,
    )
    if called["n"] != 1 or not ra.recommended_listener_question:
        errors.append("A: full context should yield suggestion")
    if not ra.expanded_summary:
        errors.append("A: expected expanded_summary")
    if len(ra.alternative_sets) != 1:
        errors.append("A: expected one alternative set")

    # B) nincs passage_text, van jóváhagyott anyag → javaslat + figyelmeztetés
    called["n"] = 0
    rb = suggest_listener_tension(
        passage="Ef 2,1–10",
        text_main_idea="A kegyelem megelőzi a cselekedeteket.",
        text_main_idea_status="approved",
        human_condition={"condition": "Halál a bűnökben", "divine_action": "Isten életre kelt"},
        generate_fn=_gen,
    )
    if called["n"] != 1 or not rb.recommended_tension:
        errors.append("B: should suggest without passage_text")
    if not any("passage_text" in w or "bibliai szöveg" in w for w in rb.warnings):
        errors.append("B: expected passage_text warning")

    # Legacy / missing JSON fields
    legacy = parse_listener_tension_suggestions(
        '{"recommended_listener_question":"Q?","recommended_listener_resistance":"",'
        '"recommended_tension":"T.","alternative_sets":[],"reasoning_summary":"",'
        '"basis":[],"warnings":[],"missing_information":[]}'
    )
    if legacy.expanded_summary != "":
        errors.append("legacy expanded_summary should be empty")

    bad = parse_listener_tension_suggestions("not json")
    if bad.ok:
        errors.append("bad json should not be ok")

    # D/E/F assessment path
    called["n"] = 0

    def _gen_assess(*_a, **_k):
        called["n"] += 1
        return json.dumps(
            {
                "overall_assessment": "Részben megfelelő — a kérdés már tartalmaz választ.",
                "strengths": ["Őszinte hang"],
                "improvements": ["A kérdés ne tartalmazza a választ."],
                "revised_listener_question": "Hogyan maradhatok meg a hitben?",
                "revised_listener_resistance": "Könnyebb másokat hibáztatni.",
                "revised_tension": "Isten megmaradásra hív, a hallgató gyengének érzi magát.",
                "warnings": [
                    "A feszültség túl korán evangéliumi feloldást tartalmaz."
                ],
            },
            ensure_ascii=False,
        )

    ad = assess_listener_tension(
        passage="Jn 3,16",
        listener_tension={
            "listener_question": "Hogyan maradhatok meg, ha Isten úgyis megtart?",
            "listener_resistance": "Félek.",
            "sermon_tension": "De Krisztus már győzött, ezért nincs feszültség.",
        },
        text_main_idea="X",
        text_main_idea_status="approved",
        generate_fn=_gen_assess,
    )
    if called["n"] != 1 or not ad.overall_assessment:
        errors.append("D: assessment should run")
    if not ad.revised_listener_question:
        errors.append("D: expected revised question")

    empty_a = assess_listener_tension(
        passage="Jn 3,16",
        listener_tension={},
        generate_fn=_should_not,
    )
    if empty_a.revised_tension or called["n"] != 1:
        # called stayed 1 from previous assess; empty should not call
        pass
    called["n"] = 0
    empty_a = assess_listener_tension(
        passage="Jn 3,16",
        listener_tension={},
        generate_fn=_should_not,
    )
    if called["n"] != 0:
        errors.append("empty assess should not call API")

    # Draft idea should not count as approved
    ctx = build_m5_context(
        passage="Jn 3,16",
        text_main_idea="Draft idea",
        text_main_idea_status="draft",
        human_condition={"condition": "X"},
    )
    if has_sufficient_m5_material(ctx):
        errors.append("draft text idea should not be sufficient alone")

    if "{{passage}}" in build_listener_tension_suggest_prompt(
        build_m5_context(passage="Jn 3,16", text_main_idea="A", text_main_idea_status="approved",
                         human_condition={"condition": "c"})
    ):
        errors.append("unfilled placeholder")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("SELF-CHECK FAILED:")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("sermon_workshop_m5_ai self-check OK")


__all__ = [
    "ListenerTensionSuggestionResult",
    "ListenerTensionAssessmentResult",
    "ListenerTensionAlternativeSet",
    "build_m5_context",
    "has_sufficient_m5_material",
    "suggest_listener_tension",
    "assess_listener_tension",
    "parse_listener_tension_suggestions",
    "parse_listener_tension_assessment",
]
