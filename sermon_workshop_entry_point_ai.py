"""Homiletikai belépési pont — MI háttérréteg (2-3 rövid, eltérő típusú javaslat).

Önálló modul: nem módosítja a meglévő M4 (emberi helyzet) / M5 (hallgatói
feszültség) promptokat, csak azok már elmentett tartalmát olvassa
kontextusként. A Gemini-hívást a hívó által átadott `generate_fn`-nel végzi
(általában az app.py `generate_text` függvénye) — ugyanaz a motor, mint
minden más Textus AI-modulnál, nem új párhuzamos gépezet.

A "Homiletikai belépési pont" a textus alapfeszültségének (Textusösszegzés)
és a már rögzített emberi helyzet / hallgatói feszültség anyagnak a mai
hallgatóhoz kapcsolása: mai kapcsolódás + 2-3 különböző típusú, rövid
belépési pont javaslat (kérdés / megtörtént eset / hétköznapi tapasztalat /
kép vagy ellentét / közvetlenül a textusból induló belépés).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence
from llm_text_utils import extract_json_object_lenient, is_llm_error_text

MISSING = "nincs adat"

TAB_LABEL_SUGGEST = "Homiletikai belépési pont — javaslat"

DEFAULT_TEMPERATURE = 0.25
MAX_SUGGESTION_OPTIONS = 3

_LIMITS = {
    "passage_text": 2500,
    "text_summary_main_idea": 600,
    "text_summary_base_tension": 800,
    "sermon_main_idea": 600,
    "human_condition": 1200,
    "listener_tension": 1200,
}

ENTRY_POINT_TYPES: tuple[tuple[str, str], ...] = (
    ("question", "Elgondolkodtató kérdés"),
    ("event", "Megtörtént eset"),
    ("everyday_experience", "Hétköznapi tapasztalat"),
    ("image_contrast", "Kép vagy ellentét"),
    ("text_direct", "Közvetlenül a textusból induló belépés"),
)
ENTRY_POINT_TYPE_KEYS: tuple[str, ...] = tuple(k for k, _ in ENTRY_POINT_TYPES)
ENTRY_POINT_TYPE_LABELS_HU: dict[str, str] = dict(ENTRY_POINT_TYPES)
NO_ENTRY_POINT_TYPE = ""  # "Nincs külön belépési pont" — a típusválasztó nem kötelező

ENTRY_POINT_SYSTEM_BUNDLE = """\
Te a TEXTUS homiletikai segéd szöveghű, prédikátori asszisztense vagy.
Csak a felhasználói feladatban megadott anyagból dolgozz.
Ne találj ki bibliai szöveget, kortörténetet vagy adatot a megadott anyagon túl.
Válaszod KIZÁRÓLAG érvényes JSON legyen — semmi más szöveg, markdown vagy magyarázat.
Minden string szabályosan escape-elt legyen; az objektumban ne legyen záró vessző.\
"""

GenerateFn = Callable[..., str]


def normalize_entry_point_type(raw: Any) -> str:
    """Érvényes belépési-pont típuskulcs, vagy üres string ("Nincs külön belépési pont")."""
    val = str(raw or "").strip()
    return val if val in ENTRY_POINT_TYPE_KEYS else NO_ENTRY_POINT_TYPE


def entry_point_type_label(raw: Any) -> str:
    key = normalize_entry_point_type(raw)
    if not key:
        return "Nincs külön belépési pont"
    return ENTRY_POINT_TYPE_LABELS_HU.get(key, key)


@dataclass
class EntryPointOption:
    """Egy javasolt belépési pont: típus + rövid szöveg."""

    type: str = ""
    text: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "text": self.text}


@dataclass
class EntryPointSuggestionResult:
    """Homiletikai belépési pont javaslat strukturált kimenet."""

    today_connection: str = ""
    options: list[EntryPointOption] = field(default_factory=list)
    reasoning_summary: str = ""
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    ok: bool = True
    error_message: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "today_connection": self.today_connection,
            "options": [o.to_dict() for o in self.options],
            "reasoning_summary": self.reasoning_summary,
            "warnings": list(self.warnings),
            "missing_information": list(self.missing_information),
            "ok": self.ok,
            "error_message": self.error_message,
            "raw_response": self.raw_response,
        }


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
# Kontextusépítés
# ---------------------------------------------------------------------------


def build_entry_point_context(
    *,
    passage: str = "",
    passage_text: str = "",
    text_summary_main_idea: str = "",
    text_summary_base_tension: str = "",
    sermon_main_idea: str = "",
    human_condition: Any = None,
    listener_tension: Any = None,
) -> dict[str, str]:
    return {
        "passage": _display(passage, max_chars=200) if _is_present(passage) else MISSING,
        "passage_text": _display(passage_text, max_chars=_LIMITS["passage_text"]),
        "text_summary_main_idea": _display(
            text_summary_main_idea, max_chars=_LIMITS["text_summary_main_idea"]
        ),
        "text_summary_base_tension": _display(
            text_summary_base_tension, max_chars=_LIMITS["text_summary_base_tension"]
        ),
        "sermon_main_idea": _display(
            sermon_main_idea, max_chars=_LIMITS["sermon_main_idea"]
        ),
        "human_condition": _format_block(
            human_condition, max_chars=_LIMITS["human_condition"]
        ),
        "listener_tension": _format_block(
            listener_tension, max_chars=_LIMITS["listener_tension"]
        ),
    }


_SUGGEST_SOURCE_KEYS: tuple[tuple[str, str], ...] = (
    ("text_summary_base_tension", "textus alapfeszültsége"),
    ("human_condition", "emberi helyzet"),
    ("listener_tension", "hallgatói feszültség"),
    ("text_summary_main_idea", "a textus fő gondolata"),
    ("sermon_main_idea", "az igehirdetés fő gondolata"),
)


def _suggest_sources_present(ctx: Mapping[str, str]) -> list[str]:
    return [label for key, label in _SUGGEST_SOURCE_KEYS if _is_present(ctx.get(key, MISSING))]


def _missing_analysis_labels(ctx: Mapping[str, str]) -> list[str]:
    return [
        label for key, label in _SUGGEST_SOURCE_KEYS if not _is_present(ctx.get(key, MISSING))
    ]


def has_sufficient_entry_point_material(ctx: Mapping[str, str]) -> bool:
    """Van-e elegendő anyag felelős belépésipont-javaslathoz.

    Minimális feltétel: nem üres `passage`, ÉS legalább egy érdemi forrás
    (textus alapfeszültsége, emberi helyzet, hallgatói feszültség, fő
    gondolat).
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


_TYPE_LIST_HU = "\n".join(f"- {key}: {label}" for key, label in ENTRY_POINT_TYPES)

_SUGGEST_PROMPT_TEMPLATE = """\
Feladatod: HOMILETIKAI BELÉPÉSI PONT javaslat a megadott bibliai szakaszhoz.

A homiletikai belépési pont az a hely, ahol az igehirdetés elindul: hogyan
találkozik a textus alapfeszültsége a mai hallgató élethelyzetével, és
milyen konkrét nyitó mozzanat (kérdés, eset, tapasztalat, kép, felütés)
viheti be a hallgatót a textusba.

## Két kimenet

1. today_connection — 1-2 mondat: hogyan találkozik a textus alapfeszültsége
   a mai hallgató jelenlegi élethelyzetével. Ez NEM maga a belépési pont,
   hanem a köztük lévő kapcsolat rövid megfogalmazása.
2. options — 2-3 rövid belépési pont javaslat, EGYMÁSTÓL ELTÉRŐ típusból
   választva az alábbi öt közül:
{{type_list}}

   Minden option legyen 1-3 mondat, konkrét és felhasználható — NE legyen
   általános vagy elcsépelt. Ha a megadott anyag alapján egy adott típus
   nem indokolt vagy erőltetett lenne, egyszerűen ne szerepeltesd — a
   listában NEM kell mind az öt típusnak szerepelnie, elég 2-3 valóban jó.

## Források súlya

Elsődleges: a textus alapfeszültsége (Textusösszegzés), az emberi helyzet
és a hallgatói feszültség anyaga.
Fontos kiegészítő: a textus vagy az igehirdetés fő gondolata.

## Abszolút tilalmak

- Ne moralizálj, ne írj alkalmazást vagy felszólítást.
- Ne találj ki konkrét, ellenőrizhetetlen "megtörtént esetet" való emberek
  neveivel — ha "megtörtént eset" típust adsz, fogalmazd meg úgy, hogy az
  egy tipikus, hihető helyzet leírása legyen, ne állítólagos konkrét személy.
- Ne legyen manipulatív, érzelgős vagy közhelyes a megfogalmazás.
- Ha egy adatforrás „nincs adat” vagy üres: ne találj ki helyette semmit.
- Ne adj belső gondolatmenetet vagy hosszú érvelést; a reasoning_summary
  legyen rövid.

## Elégtelen adat

Ha sem a textus alapfeszültsége, sem az emberi helyzet, sem a hallgatói
feszültség, sem a fő gondolat között nincs érdemi tartalom, a
today_connection legyen üres string, az options legyen üres lista — a
hiányt a missing_information és a reasoning_summary jelezze.

## Bemeneti anyag

Igehely-megjelölés (nem bibliai szöveg):
{{passage}}

Bibliai szöveg, ha rendelkezésre áll:
{{passage_text}}

A textus fő gondolata:
{{text_summary_main_idea}}

A textus alapfeszültsége (Textusösszegzés):
{{text_summary_base_tension}}

Az igehirdetés fő gondolata (ha van):
{{sermon_main_idea}}

Emberi helyzet és kegyelmi válasz (jóváhagyott/piszkozat anyag):
{{human_condition}}

Hallgatói kérdés és feszültség (jóváhagyott/piszkozat anyag):
{{listener_tension}}

## Kimenet — KIZÁRÓLAG érvényes JSON

- Semmilyen más szöveg a JSON-en kívül, nincs markdown/kódblokk.
- Minden mező kötelező; ha nincs elem egy listában, üres listát adj: [].
- Az options legfeljebb 3 elemű; minden elem "type" mezője pontosan az öt
  angol kulcs egyike legyen: question, event, everyday_experience,
  image_contrast, text_direct.
- Minden JSON-string legyen szabályosan escape-elt, érvényes JSON-érték.
- Az objektumban ne legyen záró vessző (trailing comma).

Séma:

{
  "today_connection": "string",
  "options": [
    {"type": "string", "text": "string"}
  ],
  "reasoning_summary": "string",
  "warnings": ["string"],
  "missing_information": ["string"]
}
"""


def build_entry_point_suggest_prompt(ctx: Mapping[str, str]) -> str:
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


def _parse_options(raw: Any) -> list[EntryPointOption]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    out: list[EntryPointOption] = []
    seen_types: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        type_key = normalize_entry_point_type(item.get("type"))
        text = _as_text(item.get("text"))
        if not text or not type_key:
            continue
        if type_key in seen_types:
            # Ne ismételjük ugyanazt a típust — a cél az eltérő megközelítés.
            continue
        seen_types.add(type_key)
        out.append(EntryPointOption(type=type_key, text=text))
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
) -> EntryPointSuggestionResult:
    return EntryPointSuggestionResult(
        today_connection="",
        options=[],
        reasoning_summary=reasoning,
        warnings=list(warnings or []),
        missing_information=list(missing or []),
        ok=ok,
        error_message=error_message,
        raw_response=raw_response,
    )


def parse_entry_point_suggestion(raw: str) -> EntryPointSuggestionResult:
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

    return EntryPointSuggestionResult(
        today_connection=_as_text(obj.get("today_connection")),
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
            system_bundle=ENTRY_POINT_SYSTEM_BUNDLE,
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


def suggest_entry_point(
    *,
    passage: str,
    passage_text: str = "",
    text_summary_main_idea: str = "",
    text_summary_base_tension: str = "",
    sermon_main_idea: str = "",
    human_condition: Any = None,
    listener_tension: Any = None,
    generate_fn: GenerateFn | None = None,
    temperature: float | None = DEFAULT_TEMPERATURE,
    skip_api_if_insufficient: bool = True,
) -> EntryPointSuggestionResult:
    """Homiletikai belépési pont javaslat: mai kapcsolódás + 2-3 eltérő típusú opció.

    `generate_fn`: tipikusan az app.py `generate_text` függvénye.
    """
    ctx = build_entry_point_context(
        passage=passage,
        passage_text=passage_text,
        text_summary_main_idea=text_summary_main_idea,
        text_summary_base_tension=text_summary_base_tension,
        sermon_main_idea=sermon_main_idea,
        human_condition=human_condition,
        listener_tension=listener_tension,
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
    if skip_api_if_insufficient and not has_sufficient_entry_point_material(ctx):
        return fallback_suggestion(
            reasoning=(
                "Nincs elegendő elemzési anyag (textus alapfeszültsége, "
                "emberi helyzet, hallgatói feszültség vagy fő gondolat "
                "egyike sem áll rendelkezésre) felelős belépésipont-"
                "javaslathoz. A modell nem egészíti ki a hiányt saját "
                "emlékezetből."
            ),
            warnings=["Elégtelen adat: felelős javaslat helyett üres mezők."],
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

    prompt = build_entry_point_suggest_prompt(ctx)
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

    return parse_entry_point_suggestion(raw or "")


# ---------------------------------------------------------------------------
# Smoke / önellenőrzés (API nélkül)
# ---------------------------------------------------------------------------


def _self_check() -> list[str]:
    errors: list[str] = []

    called = {"n": 0}

    def _should_not_run(*_a, **_k):
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    r = suggest_entry_point(passage="Jn 3,16–21", generate_fn=_should_not_run)
    if called["n"] != 0:
        errors.append("insufficient suggest still called API")
    if r.today_connection or r.options:
        errors.append("insufficient suggest should be empty")
    if not r.missing_information:
        errors.append("insufficient suggest missing_information empty")

    raw = (
        '```json\n{"today_connection":"TC",'
        '"options":[{"type":"question","text":"Q?"},'
        '{"type":"event","text":"E."}],'
        '"reasoning_summary":"Ok.","warnings":[],"missing_information":[]}\n```'
    )
    p = parse_entry_point_suggestion(raw)
    if not p.ok or p.today_connection != "TC" or len(p.options) != 2:
        errors.append("entry point parse failed")
    if p.options[0].type != "question" or p.options[1].type != "event":
        errors.append("entry point option types not preserved in order")

    # Duplikált típus kiszűrése
    dup_raw = json.dumps(
        {
            "today_connection": "TC",
            "options": [
                {"type": "question", "text": "Q1"},
                {"type": "question", "text": "Q2 dup"},
                {"type": "event", "text": "E1"},
            ],
            "reasoning_summary": "Ok.",
            "warnings": [],
            "missing_information": [],
        }
    )
    dup = parse_entry_point_suggestion(dup_raw)
    if len(dup.options) != 2:
        errors.append("duplicate type should be filtered")

    bad = parse_entry_point_suggestion("ez nem json")
    if bad.ok or bad.today_connection:
        errors.append("bad json should fallback")

    called["n"] = 0

    def _gen(*_a, **_k):
        called["n"] += 1
        return json.dumps(
            {
                "today_connection": "A mai hallgató is szembesül a kitartás nehézségével.",
                "options": [
                    {
                        "type": "question",
                        "text": "Mikor érezted úgy utoljára, hogy egyedül maradtál a hitedben?",
                    },
                    {
                        "type": "everyday_experience",
                        "text": "Egy hosszú, magányos projekt végén könnyű feladni.",
                    },
                ],
                "reasoning_summary": "Az emberi helyzet és a feszültség alapján.",
                "warnings": [],
                "missing_information": [],
            },
            ensure_ascii=False,
        )

    rr = suggest_entry_point(
        passage="Júd 17-20",
        human_condition={"condition": "Megosztottság fenyegeti a közösséget."},
        generate_fn=_gen,
    )
    if called["n"] != 1 or not rr.today_connection or not rr.options:
        errors.append("human_condition-only suggest should call API and yield options")

    return errors


if __name__ == "__main__":
    errs = _self_check()
    if errs:
        print("SELF-CHECK FAILED:")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("sermon_workshop_entry_point_ai self-check OK")
