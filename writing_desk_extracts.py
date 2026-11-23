"""Íróasztal munkakivonatok — célzott tömörítés a meglévő forrásanyagból.

Nem végez új kutatást, nem nyúl a teljes `original_text` / `history` /
`theology` mezőkhöz, és nem renderel Streamlit-widgetet. A Gemini-hívást
a hívó `generate_fn`-je végzi (általában `app.generate_text`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping

from prompt_safety import wrap_untrusted_content
from writing_desk_data import (
    WRITING_DESK_EXTRACT_KEYS,
    WRITING_DESK_KEY,
    fingerprint_source_text,
    normalize_writing_desk,
    set_writing_desk_extract,
)
from llm_text_utils import is_llm_error_text

GenerateFn = Callable[..., str]

STATUS_MISSING_SOURCE = "missing_source"
STATUS_READY = "ready"
STATUS_VALID = "valid"
STATUS_STALE = "stale"

EXTRACT_SOURCE_FIELDS: dict[str, str] = {
    "original_text": "original_text",
    "history": "history",
    "theology": "theology",
}

EXTRACT_LABELS: dict[str, str] = {
    "original_text": "Eredeti szöveg",
    "history": "Kortörténet",
    "theology": "Teológia",
}

EXTRACT_MISSING_MESSAGES: dict[str, str] = {
    "original_text": (
        "Ehhez a projekthez még nincs elkészített eredeti szöveges elemzés."
    ),
    "history": "Ehhez a projekthez még nincs elkészített kortörténeti elemzés.",
    "theology": "Ehhez a projekthez még nincs elkészített teológiai elemzés.",
}

TAB_LABEL_EXTRACT = "Íróasztal — munkakivonat"
EXTRACT_ERROR_KEY_PREFIX = "_writing_desk_extract_error"
MAX_SOURCE_CHARS = 16000
# Gemini 2.5 Flash: a thoughtsTokenCount IS a maxOutputTokens keretből
# fogy. 1024-nél a látható kivonat mondat közben MAX_TOKENS-re futott.
# 8000 a rövid, gondolkodós hívások (pl. Textus fő gondolat) bevált kerete.
MAX_OUTPUT_TOKENS = 8000
DEFAULT_TEMPERATURE = 0.2
OUTPUT_LIMIT_NOTICE = "kimeneti korlátjánál megszakadt"
_EXTRACT_INCOMPLETE_SENTINEL = "__WRITING_DESK_EXTRACT_INCOMPLETE__"
EXTRACT_INCOMPLETE_MESSAGE = (
    "A kivonat nem készült el teljesen. Próbáld újra."
)

EXTRACT_SYSTEM_BUNDLE = """\
Csak a megadott forrásanyagból dolgozz.
Ne végezz új kutatást, ne egészítsd ki a forrást saját emlékezetből,
és ne adj hozzá a forrásban nem szereplő információt.
Sima magyar szöveg legyen: ne JSON, ne cím, ne lista.\
"""

EXTRACT_ROLE_INSTRUCTIONS: dict[str, str] = {
    "original_text": (
        "Csak nyelvi és szövegi megfigyelés: kulcsszavak, grammatika, "
        "szemantika, szövegszerkezet. Ne írj teológiai tanítást és ne "
        "adj kortörténeti hátteret."
    ),
    "history": (
        "Csak valóban történeti vagy kulturális háttér: társadalom, "
        "politika, vallási gyakorlat, korabeli szokások, intézmények, "
        "földrajz, történeti kontextus. Ne tegyél ide jánosi teológiai "
        "vagy dogmatikai állítást, és ne elemezz irodalmi fogalmakat "
        "teológiaként."
    ),
    "theology": (
        "Csak az aktuális textushoz tartozó teológiai forrásréteg "
        "összegzése. A forrásban nem szereplő tanítást, más igehely "
        "történetét vagy példázatát ne hozd be."
    ),
}

_PROMPT_TEMPLATE = """\
A megadott {label} forrásanyagból válassz ki 3–5, prédikációs előkészítéshez \
leginkább használható megállapítást.
Mindegyik legyen önálló, rövid, teljes mondat.
Csak a forrásban szereplő információt használd.
{role_instruction}
Ne írj bevezetőt, lezárást vagy meta-kommentárt, és ne ismételd a feladatot.

Forrásanyag ({label}):
{source_block}
"""


@dataclass(frozen=True)
class WritingDeskExtractView:
    extract_key: str
    label: str
    status: str
    source_text: str
    current_fingerprint: str
    saved_content: str
    saved_fingerprint: str
    missing_message: str

    @property
    def content(self) -> str:
        if self.status == STATUS_VALID:
            return self.saved_content
        return ""


@dataclass
class WritingDeskExtractResult:
    extract_key: str
    ok: bool
    content: str = ""
    source_fingerprint: str = ""
    error_message: str = ""
    llm_called: bool = False
    used_cache: bool = False


def extract_error_session_key(extract_key: str) -> str:
    return f"{EXTRACT_ERROR_KEY_PREFIX}_{extract_key}"


def source_text_for_extract(session_state: Mapping[str, Any], extract_key: str) -> str:
    if extract_key not in WRITING_DESK_EXTRACT_KEYS:
        raise ValueError(f"Ismeretlen Íróasztal-kivonat: {extract_key}")
    field = EXTRACT_SOURCE_FIELDS[extract_key]
    return str(session_state.get(field) or "")


def passage_identity_for_extracts(session_state: Mapping[str, Any]) -> str:
    """Az aktuális textus identitása — kivonat nem lehet érvényes más igehelyen."""
    reference = str(
        session_state.get("last_igehely") or session_state.get("igehely_input") or ""
    ).strip()
    translation = str(session_state.get("bible_translation") or "").strip()
    passage = str(
        session_state.get("passage_text") or session_state.get("passage_text_input") or ""
    ).strip()
    return f"{reference}\n{translation}\n{passage}"


def current_extract_fingerprint(
    session_state: Mapping[str, Any], extract_key: str
) -> str:
    """Forrásréteg + aktuális igehely/passzus. Üres forrás → üres ujjlenyomat."""
    source = source_text_for_extract(session_state, extract_key)
    source_fp = fingerprint_source_text(source)
    if not source_fp:
        return ""
    payload = (
        f"{passage_identity_for_extracts(session_state)}\n{extract_key}\n{source}"
    )
    return fingerprint_source_text(payload)


def inspect_writing_desk_extract(
    session_state: Mapping[str, Any],
    extract_key: str,
) -> WritingDeskExtractView:
    if extract_key not in WRITING_DESK_EXTRACT_KEYS:
        raise ValueError(f"Ismeretlen Íróasztal-kivonat: {extract_key}")
    source = source_text_for_extract(session_state, extract_key)
    current_fp = current_extract_fingerprint(session_state, extract_key)
    desk = normalize_writing_desk(session_state.get(WRITING_DESK_KEY))
    saved = desk["extracts"][extract_key]
    saved_content = str(saved.get("content") or "")
    saved_fp = str(saved.get("source_fingerprint") or "")
    has_content = bool(saved_content.strip()) and not _is_output_limit_response(
        saved_content
    )

    if not current_fp:
        status = STATUS_MISSING_SOURCE
    elif has_content and saved_fp == current_fp:
        status = STATUS_VALID
    elif has_content:
        status = STATUS_STALE
    else:
        status = STATUS_READY

    return WritingDeskExtractView(
        extract_key=extract_key,
        label=EXTRACT_LABELS[extract_key],
        status=status,
        source_text=source,
        current_fingerprint=current_fp,
        saved_content=saved_content,
        saved_fingerprint=saved_fp,
        missing_message=EXTRACT_MISSING_MESSAGES[extract_key],
    )


def build_extract_prompt(extract_key: str, source_text: str) -> str:
    if extract_key not in WRITING_DESK_EXTRACT_KEYS:
        raise ValueError(f"Ismeretlen Íróasztal-kivonat: {extract_key}")
    label = EXTRACT_LABELS[extract_key]
    source_block = wrap_untrusted_content(
        label,
        source_text,
        limit_name="exegesis",
        max_chars=MAX_SOURCE_CHARS,
    )
    return _PROMPT_TEMPLATE.format(
        label=label,
        role_instruction=EXTRACT_ROLE_INSTRUCTIONS[extract_key],
        source_block=source_block,
    )


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos is_llm_error_text (llm_text_utils.py; azonosság: tests/test_llm_text_utils.py).
_is_api_error_text = is_llm_error_text


def _is_output_limit_response(text: str) -> bool:
    """generate_text MAX_TOKENS / incomplete sentinel — ne a prefix-heurisztika."""
    t = (text or "").strip()
    if not t:
        return False
    if t in {_EXTRACT_INCOMPLETE_SENTINEL, EXTRACT_INCOMPLETE_MESSAGE}:
        return True
    return OUTPUT_LIMIT_NOTICE in t


def _clean_extract_text(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def generate_writing_desk_extract(
    session_state: MutableMapping[str, Any],
    extract_key: str,
    *,
    generate_fn: GenerateFn | None,
) -> WritingDeskExtractResult:
    """Egy kivonat explicit előállítása. Cache-hit esetén nincs LLM-hívás."""
    if extract_key not in WRITING_DESK_EXTRACT_KEYS:
        raise ValueError(f"Ismeretlen Íróasztal-kivonat: {extract_key}")

    view = inspect_writing_desk_extract(session_state, extract_key)
    if view.status == STATUS_MISSING_SOURCE:
        return WritingDeskExtractResult(
            extract_key=extract_key,
            ok=False,
            error_message=view.missing_message,
            llm_called=False,
        )
    if view.status == STATUS_VALID:
        return WritingDeskExtractResult(
            extract_key=extract_key,
            ok=True,
            content=view.saved_content,
            source_fingerprint=view.saved_fingerprint,
            llm_called=False,
            used_cache=True,
        )
    if generate_fn is None:
        return WritingDeskExtractResult(
            extract_key=extract_key,
            ok=False,
            error_message="A kivonat most nem készíthető el.",
            llm_called=False,
        )

    prompt = build_extract_prompt(extract_key, view.source_text)
    generate_kwargs = {
        "tab_label": TAB_LABEL_EXTRACT,
        "system_bundle": EXTRACT_SYSTEM_BUNDLE,
        "include_brevity_directive": True,
        "use_cache": True,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "temperature": DEFAULT_TEMPERATURE,
        "truncation_notice_mode": "never",
        "incomplete_response_message": _EXTRACT_INCOMPLETE_SENTINEL,
    }
    try:
        try:
            raw = generate_fn(prompt, **generate_kwargs)
        except TypeError:
            raw = generate_fn(prompt, tab_label=TAB_LABEL_EXTRACT)
    except Exception:  # noqa: BLE001
        return WritingDeskExtractResult(
            extract_key=extract_key,
            ok=False,
            error_message="A kivonat most nem készíthető el. Próbáld újra később.",
            llm_called=True,
        )

    llm_text = "" if raw is None else str(raw)
    if _is_output_limit_response(llm_text):
        return WritingDeskExtractResult(
            extract_key=extract_key,
            ok=False,
            error_message=EXTRACT_INCOMPLETE_MESSAGE,
            llm_called=True,
        )
    if _is_api_error_text(llm_text):
        message = llm_text.strip() or "A kivonat most nem készíthető el."
        return WritingDeskExtractResult(
            extract_key=extract_key,
            ok=False,
            error_message=message,
            llm_called=True,
        )

    cleaned = _clean_extract_text(llm_text)
    if not cleaned or _is_output_limit_response(cleaned):
        return WritingDeskExtractResult(
            extract_key=extract_key,
            ok=False,
            error_message=(
                EXTRACT_INCOMPLETE_MESSAGE
                if cleaned
                else "A kivonat most nem készíthető el."
            ),
            llm_called=True,
        )

    set_writing_desk_extract(
        session_state,
        extract_key,
        content=cleaned,
        source_fingerprint=view.current_fingerprint,
    )
    return WritingDeskExtractResult(
        extract_key=extract_key,
        ok=True,
        content=cleaned,
        source_fingerprint=view.current_fingerprint,
        llm_called=True,
        used_cache=False,
    )


__all__ = [
    "DEFAULT_TEMPERATURE",
    "EXTRACT_ERROR_KEY_PREFIX",
    "EXTRACT_INCOMPLETE_MESSAGE",
    "EXTRACT_LABELS",
    "EXTRACT_MISSING_MESSAGES",
    "EXTRACT_ROLE_INSTRUCTIONS",
    "EXTRACT_SOURCE_FIELDS",
    "EXTRACT_SYSTEM_BUNDLE",
    "current_extract_fingerprint",
    "passage_identity_for_extracts",
    "MAX_OUTPUT_TOKENS",
    "STATUS_MISSING_SOURCE",
    "STATUS_READY",
    "STATUS_STALE",
    "STATUS_VALID",
    "TAB_LABEL_EXTRACT",
    "WRITING_DESK_EXTRACT_KEYS",
    "WRITING_DESK_KEY",
    "WritingDeskExtractResult",
    "WritingDeskExtractView",
    "build_extract_prompt",
    "extract_error_session_key",
    "generate_writing_desk_extract",
    "inspect_writing_desk_extract",
    "source_text_for_extract",
]
