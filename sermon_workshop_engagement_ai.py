"""Megszólítás és bevonás — MI háttérréteg (2-4 rövid, eltérő típusú javaslat).

Önálló modul: nem végez exegézist, és nem olvas nyers, jóvá nem hagyott
műhelymezőt. A hívó (UI réteg) felelőssége, hogy KIZÁRÓLAG jóváhagyott
tartalmat adjon át kontextusként — ez a modul csak a kapott szöveget
dolgozza fel, nem tér vissza a session_state-hez. A Gemini-hívást a hívó
által átadott `generate_fn`-nel végzi (általában az app.py `generate_text`
függvénye) — ugyanaz a motor, mint minden más Textus AI-modulnál, nem új
párhuzamos gépezet.

A "Megszólítás és bevonás" a jóváhagyott textus- és igehirdetési-műhelyi
anyagból (Textusösszegzés, fókuszmondat, homiletikai belépési pont,
prédikációs ív, evangéliumi fordulat, megérkezés) javasol 2-4 rövid,
konkrét, eltérő típusú retorikai eszközt, amely segít az igehirdetésnek
nem távoli "szentbeszédként" hatni.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence
from llm_text_utils import extract_json_object_lenient, is_llm_error_text

MISSING = "nincs adat"

TAB_LABEL_SUGGEST = "Megszólítás és bevonás — javaslat"

DEFAULT_TEMPERATURE = 0.3
MAX_SUGGESTION_OPTIONS = 4
MIN_SUGGESTION_OPTIONS = 2

_LIMITS = {
    "text_summary_main_idea": 500,
    "text_summary_base_tension": 700,
    "sermon_main_idea": 500,
    "entry_point": 500,
    "human_condition": 900,
    "listener_tension": 900,
    "sermon_path": 900,
    "christ_centered_arc": 900,
    "closing": 700,
}

ENGAGEMENT_TYPES: tuple[tuple[str, str], ...] = (
    ("question", "Elgondolkodtató vagy költői kérdés"),
    ("direct_address", "Közvetlen, de nem manipulatív megszólítás"),
    ("image_metaphor", "Vizuális kép vagy metafora"),
    ("life_situation", "Rövid élethelyzet vagy megtörtént eset"),
    ("presence_sentence", "Jelenlétteremtő mondat"),
)
ENGAGEMENT_TYPE_KEYS: tuple[str, ...] = tuple(k for k, _ in ENGAGEMENT_TYPES)
ENGAGEMENT_TYPE_LABELS_HU: dict[str, str] = dict(ENGAGEMENT_TYPES)

ENGAGEMENT_SYSTEM_BUNDLE = """\
Te a TEXTUS homiletikai segéd szöveghű, prédikátori asszisztense vagy.
Csak a felhasználói feladatban megadott, MÁR JÓVÁHAGYOTT anyagból dolgozz.
Ne végezz új exegézist, és ne állíts a megadott anyaggal ellentétes értelmezést.
Ne találj ki bibliai szöveget, kortörténetet vagy adatot a megadott anyagon túl.
Válaszod KIZÁRÓLAG érvényes JSON legyen — semmi más szöveg, markdown vagy magyarázat.
Minden string szabályosan escape-elt legyen; az objektumban ne legyen záró vessző.\
"""

GenerateFn = Callable[..., str]


def normalize_engagement_type(raw: Any) -> str:
    val = str(raw or "").strip()
    return val if val in ENGAGEMENT_TYPE_KEYS else ""


def engagement_type_label(raw: Any) -> str:
    key = normalize_engagement_type(raw)
    return ENGAGEMENT_TYPE_LABELS_HU.get(key, key or "—")


@dataclass
class EngagementOption:
    """Egy javasolt megszólító elem: típus + rövid szöveg."""

    type: str = ""
    text: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "text": self.text}


@dataclass
class EngagementSuggestionResult:
    """Megszólítás és bevonás javaslat strukturált kimenet."""

    options: list[EngagementOption] = field(default_factory=list)
    reasoning_summary: str = ""
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "options": [o.to_dict() for o in self.options],
            "reasoning_summary": self.reasoning_summary,
            "warnings": list(self.warnings),
            "missing_information": list(self.missing_information),
            "ok": self.ok,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
        }


# ---------------------------------------------------------------------------
# Segédek
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


def _format_block(block: Any, *, max_chars: int) -> str:
    if isinstance(block, Mapping):
        lines = [
            f"- {k}: {v}" for k, v in block.items() if isinstance(v, str) and v.strip()
        ]
        if not lines:
            return MISSING
        return _display("\n".join(lines), max_chars=max_chars)
    return _display(block, max_chars=max_chars)


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos is_llm_error_text (llm_text_utils.py; azonosság: tests/test_llm_text_utils.py).
_is_api_error_text = is_llm_error_text


# ---------------------------------------------------------------------------
# Kontextusépítés — a hívó felelőssége, hogy csak jóváhagyott tartalmat adjon át
# ---------------------------------------------------------------------------


def build_engagement_context(
    *,
    passage: str = "",
    text_summary_main_idea: str = "",
    text_summary_base_tension: str = "",
    sermon_main_idea: str = "",
    entry_point: Any = None,
    human_condition: Any = None,
    listener_tension: Any = None,
    sermon_path: Any = None,
    christ_centered_arc: Any = None,
    closing: Any = None,
) -> dict[str, str]:
    return {
        "passage": _display(passage, max_chars=200) if _is_present(passage) else MISSING,
        "text_summary_main_idea": _display(
            text_summary_main_idea, max_chars=_LIMITS["text_summary_main_idea"]
        ),
        "text_summary_base_tension": _display(
            text_summary_base_tension, max_chars=_LIMITS["text_summary_base_tension"]
        ),
        "sermon_main_idea": _display(
            sermon_main_idea, max_chars=_LIMITS["sermon_main_idea"]
        ),
        "entry_point": _format_block(entry_point, max_chars=_LIMITS["entry_point"]),
        "human_condition": _format_block(
            human_condition, max_chars=_LIMITS["human_condition"]
        ),
        "listener_tension": _format_block(
            listener_tension, max_chars=_LIMITS["listener_tension"]
        ),
        "sermon_path": _format_block(sermon_path, max_chars=_LIMITS["sermon_path"]),
        "christ_centered_arc": _format_block(
            christ_centered_arc, max_chars=_LIMITS["christ_centered_arc"]
        ),
        "closing": _format_block(closing, max_chars=_LIMITS["closing"]),
    }


_SUGGEST_SOURCE_KEYS: tuple[tuple[str, str], ...] = (
    ("text_summary_base_tension", "textus alapfeszültsége"),
    ("sermon_main_idea", "fókuszmondat"),
    ("entry_point", "homiletikai belépési pont"),
    ("human_condition", "emberi helyzet"),
    ("listener_tension", "hallgatói feszültség"),
    ("sermon_path", "a prédikáció íve"),
    ("christ_centered_arc", "evangéliumi fordulat"),
    ("closing", "megérkezés"),
    ("text_summary_main_idea", "a textus fő gondolata"),
)


def _suggest_sources_present(ctx: Mapping[str, str]) -> list[str]:
    return [label for key, label in _SUGGEST_SOURCE_KEYS if _is_present(ctx.get(key, MISSING))]


def _missing_analysis_labels(ctx: Mapping[str, str]) -> list[str]:
    return [
        label for key, label in _SUGGEST_SOURCE_KEYS if not _is_present(ctx.get(key, MISSING))
    ]


def has_sufficient_engagement_material(ctx: Mapping[str, str]) -> bool:
    """Van-e elegendő JÓVÁHAGYOTT anyag felelős megszólítás-javaslathoz.

    Minimális feltétel: nem üres `passage`, ÉS legalább egy jóváhagyott
    forrás (a hívó csak jóváhagyott tartalmat adhat át ezekre a mezőkre).
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


_TYPE_LIST_HU = "\n".join(f"- {key}: {label}" for key, label in ENGAGEMENT_TYPES)

_SUGGEST_PROMPT_TEMPLATE = """\
Feladatod: MEGSZÓLÍTÁS ÉS BEVONÁS javaslat a megadott, MÁR JÓVÁHAGYOTT
igehirdetési anyaghoz.

A cél: 2-4 rövid, konkrét retorikai eszköz, amely segít az igehirdetésnek
nem távoli "szentbeszédként" hatni, hanem valóban megszólítani a
hallgatót — a jóváhagyott textus- és igehirdetési anyag alapján, azzal
összhangban.

## Támogatott típusok

{{type_list}}

Válassz 2-4 elemet, EGYMÁSTÓL ELTÉRŐ típusból — nem kell mind az ötnek
szerepelnie, csak amit a textus és a prédikációs ív valóban indokol.

## Minőségi elvárások minden javaslatra

- Legyen tömör (1-3 mondat) és konkrét.
- NE legyen általános közhely vagy elcsépelt fordulat.
- NE legyen érzelgős vagy manipulatív.
- NE állítson bizonyosságként olyat, amit a megadott anyag nem támaszt alá.
- NE írja meg a teljes igehirdetést vagy annak egy szakaszát — csak a
  megszólító elemet magát.
- NE ismételje meg egyszerűen a fókuszmondatot vagy a megérkezést szó
  szerint — egészítse ki, ne másolja.
- A "life_situation" (megtörtént eset) típusnál NE találj ki ellenőrizhetetlen
  konkrét személyt vagy nevet — fogalmazd meg tipikus, hihető helyzetként.

## Abszolút tilalmak

- Ne végezz új exegézist, és ne állíts a megadott anyaggal ellentétes
  értelmezést — kizárólag a megadott, jóváhagyott anyagra építs.
- Ne találj ki bibliai szöveget, kortörténetet vagy adatot a megadott
  anyagon túl.
- Ha egy adatforrás „nincs adat” vagy üres: ne találj ki helyette semmit.
- Ne adj belső gondolatmenetet vagy hosszú érvelést; a reasoning_summary
  legyen rövid.

## Elégtelen adat

Ha a megadott jóváhagyott anyagok között nincs érdemi tartalom, az options
legyen üres lista — a hiányt a missing_information és a reasoning_summary
jelezze.

## Bemeneti anyag (mind jóváhagyott)

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

A textus fő gondolata:
{{text_summary_main_idea}}

A textus alapfeszültsége (Textusösszegzés):
{{text_summary_base_tension}}

Fókuszmondat (az igehirdetés fő gondolata):
{{sermon_main_idea}}

Homiletikai belépési pont:
{{entry_point}}

Emberi helyzet és kegyelmi válasz:
{{human_condition}}

Hallgatói kérdés és feszültség:
{{listener_tension}}

A prédikáció íve (kiinduló látás, első látásváltás, mélyítés, megérkezési pont):
{{sermon_path}}

Evangéliumi fordulat:
{{christ_centered_arc}}

Megérkezés:
{{closing}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül, nincs markdown/kódblokk.
- Minden mező kötelező; ha nincs elem egy listában, üres listát adj: [].
- Az options legalább 0, legfeljebb 4 elemű; minden elem "type" mezője
  pontosan az öt angol kulcs egyike legyen: question, direct_address,
  image_metaphor, life_situation, presence_sentence.
- Minden JSON-string legyen szabályosan escape-elt, érvényes JSON-érték.
- Az objektumban ne legyen záró vessző (trailing comma).

Séma:

{
  "options": [
    {"type": "string", "text": "string"}
  ],
  "reasoning_summary": "string",
  "warnings": ["string"],
  "missing_information": ["string"]
}
"""


def build_engagement_suggest_prompt(ctx: Mapping[str, str]) -> str:
    filled_ctx = dict(ctx)
    filled_ctx["type_list"] = _TYPE_LIST_HU
    return _fill_placeholders(_SUGGEST_PROMPT_TEMPLATE, filled_ctx)


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


def _parse_options(raw: Any) -> list[EngagementOption]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    out: list[EngagementOption] = []
    seen_types: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        type_key = normalize_engagement_type(item.get("type"))
        text = _as_text(item.get("text"))
        if not text or not type_key:
            continue
        if type_key in seen_types:
            continue
        seen_types.add(type_key)
        out.append(EngagementOption(type=type_key, text=text))
        if len(out) >= MAX_SUGGESTION_OPTIONS:
            break
    return out


def fallback_suggestion(
    *,
    reasoning: str,
    warnings: list[str] | None = None,
    missing: list[str] | None = None,
    error_message: str = "",
    raw_response: str = "",
    ok: bool = False,
) -> EngagementSuggestionResult:
    return EngagementSuggestionResult(
        options=[],
        reasoning_summary=reasoning,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def parse_engagement_suggestion(raw: str) -> EngagementSuggestionResult:
    if _is_api_error_text(raw):
        return fallback_suggestion(
            reasoning="A modellhívás nem adott feldolgozható választ.",
            warnings=["API-hiba vagy üres válasz."],
            error_message=_as_text(raw) or "Üres vagy hibás API-válasz.",
            raw_response=raw or "",
            ok=False,
        )

    obj = extract_json_object(raw)
    if obj is None:
        return fallback_suggestion(
            reasoning="A válasz nem dolgozható fel érvényes JSON-ként.",
            warnings=["Érvénytelen vagy hiányos JSON a modellválaszban."],
            error_message="A válasz nem dolgozható fel érvényes JSON-ként.",
            raw_response=raw or "",
            ok=False,
        )

    reasoning = _as_text(obj.get("reasoning_summary"))
    if not reasoning:
        reasoning = "A modell nem adott indoklást."

    return EngagementSuggestionResult(
        options=_parse_options(obj.get("options")),
        reasoning_summary=reasoning,
        warnings=_as_str_list(obj.get("warnings")),
        missing_information=_as_str_list(obj.get("missing_information")),
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
            system_bundle=ENGAGEMENT_SYSTEM_BUNDLE,
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


def suggest_engagement_elements(
    *,
    passage: str,
    text_summary_main_idea: str = "",
    text_summary_base_tension: str = "",
    sermon_main_idea: str = "",
    entry_point: Any = None,
    human_condition: Any = None,
    listener_tension: Any = None,
    sermon_path: Any = None,
    christ_centered_arc: Any = None,
    closing: Any = None,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> EngagementSuggestionResult:
    """Megszólítás és bevonás javaslat: 2-4 rövid, eltérő típusú elem.

    A hívó (UI réteg) felelőssége, hogy KIZÁRÓLAG jóváhagyott tartalmat
    adjon át ezekhez a paraméterekhez — ez a modul nem olvas session_state-et.
    `generate_fn`: tipikusan az app.py `generate_text` függvénye.
    """
    ctx = build_engagement_context(
        passage=passage,
        text_summary_main_idea=text_summary_main_idea,
        text_summary_base_tension=text_summary_base_tension,
        sermon_main_idea=sermon_main_idea,
        entry_point=entry_point,
        human_condition=human_condition,
        listener_tension=listener_tension,
        sermon_path=sermon_path,
        christ_centered_arc=christ_centered_arc,
        closing=closing,
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
    if skip_api_if_insufficient and not has_sufficient_engagement_material(ctx):
        return fallback_suggestion(
            reasoning=(
                "Nincs elegendő jóváhagyott anyag (Textusösszegzés, "
                "fókuszmondat, belépési pont, emberi helyzet, hallgatói "
                "feszültség, prédikációs ív, evangéliumi fordulat vagy "
                "megérkezés egyike sem áll rendelkezésre jóváhagyott "
                "állapotban) felelős megszólítás-javaslathoz."
            ),
            warnings=["Elégtelen jóváhagyott adat: felelős javaslat helyett üres lista."],
            missing=missing or ["jóváhagyott anyag"],
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

    prompt = build_engagement_suggest_prompt(ctx)
    try:
        raw = _call_generate(
            generate_fn,
            prompt,
            tab_label=TAB_LABEL_SUGGEST,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001 — UI ne dőljön el
        return fallback_suggestion(
            reasoning="A javaslatkészítés közben váratlan hiba történt.",
            warnings=[f"Váratlan hiba: {exc}"],
            missing=missing,
            error_message=str(exc),
            ok=False,
        )

    return parse_engagement_suggestion(raw or "")


# ---------------------------------------------------------------------------
# Smoke / önellenőrzés (API nélkül)
# ---------------------------------------------------------------------------


def _self_check() -> list[str]:
    errors: list[str] = []

    called = {"n": 0}

    def _should_not_run(*_a, **_k):
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    r = suggest_engagement_elements(passage="Jn 3,16–21", generate_fn=_should_not_run)
    if called["n"] != 0:
        errors.append("insufficient suggest still called API")
    if r.options:
        errors.append("insufficient suggest should be empty")
    if not r.missing_information:
        errors.append("insufficient suggest missing_information empty")

    raw = json.dumps(
        {
            "options": [
                {"type": "question", "text": "Q?"},
                {"type": "image_metaphor", "text": "Kép."},
                {"type": "presence_sentence", "text": "Itt vagy."},
            ],
            "reasoning_summary": "Ok.",
            "warnings": [],
            "missing_information": [],
        }
    )
    p = parse_engagement_suggestion(raw)
    if not p.ok or len(p.options) != 3:
        errors.append("engagement parse failed")

    # 5 elem -> max 4 marad
    five_raw = json.dumps(
        {
            "options": [{"type": t, "text": f"T{i}"} for i, t in enumerate(ENGAGEMENT_TYPE_KEYS)],
            "reasoning_summary": "Ok.",
            "warnings": [],
            "missing_information": [],
        }
    )
    five = parse_engagement_suggestion(five_raw)
    if len(five.options) != MAX_SUGGESTION_OPTIONS:
        errors.append("options should be capped at MAX_SUGGESTION_OPTIONS")

    bad = parse_engagement_suggestion("nem json")
    if bad.ok or bad.options:
        errors.append("bad json should fallback")

    called["n"] = 0

    def _gen(*_a, **_k):
        called["n"] += 1
        return json.dumps(
            {
                "options": [
                    {"type": "question", "text": "Mikor éreztél hasonlót?"},
                    {"type": "presence_sentence", "text": "Ma is itt van veled."},
                ],
                "reasoning_summary": "A megérkezés alapján.",
                "warnings": [],
                "missing_information": [],
            },
            ensure_ascii=False,
        )

    rr = suggest_engagement_elements(
        passage="Júd 17-20",
        closing={"final_discovery": "Isten megtart a szétszóratásban is."},
        generate_fn=_gen,
    )
    if called["n"] != 1 or not rr.options:
        errors.append("closing-only suggest should call API and yield options")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("SELF-CHECK FAILED:")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("sermon_workshop_engagement_ai self-check OK")
