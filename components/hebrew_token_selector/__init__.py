from __future__ import annotations

from passage_trace import traced as _traced_stage  # TEMPORARY passage-crash diagnostics

from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st

from bible_engine.hebrew_parser import HebrewToken


_COMPONENT_DIR = Path(__file__).parent
_FRONTEND_DIR = _COMPONENT_DIR / "frontend"


@_traced_stage("hebrew_token_selector_component_v2")
def hebrew_token_selector(
    tokens: list[HebrewToken],
    selected_token_key: str | None,
    key: str,
    on_selected_token_key_change: Callable[[], None] | None = None,
) -> str | None:
    component = _component()
    result = component(
        data={
            "tokens": component_tokens(tokens, selected_token_key),
            "selected_token_key": selected_token_key,
            "selected_word_index": _word_index_from_selection_key(selected_token_key),
        },
        key=key,
        on_selected_token_key_change=on_selected_token_key_change
        if on_selected_token_key_change is not None
        else lambda: None,
    )
    selected = getattr(result, "selected_token_key", None)
    if selected is None:
        selected = getattr(result, "selected_word_index", None)
    return normalize_hebrew_component_selection_key(selected, tokens)


def component_tokens(
    tokens: list[HebrewToken],
    selected_token_key: str | None = None,
) -> list[dict[str, int | str | bool]]:
    rendered: list[dict[str, int | str | bool]] = []
    for token in sorted(tokens, key=lambda item: (item.chapter, item.verse, item.word_index)):
        rendered.append(
            {
                "book": token.book,
                "chapter": token.chapter,
                "verse": token.verse,
                "word_index": token.word_index,
                "surface": token.surface,
                "language": token.language,
                "morphology_code": token.morphology_code,
                "strong_id": token.core_component.strong_id if token.core_component else "",
                "selected_word_index": token.word_index,
                "selection_key": token.stable_key,
                "selected": token.stable_key == selected_token_key,
            }
        )
    return rendered


def normalize_hebrew_component_selection_key(value: Any, tokens: list[HebrewToken]) -> str | None:
    if value is None:
        return None
    candidate = str(value)
    valid_keys = {token.stable_key for token in tokens}
    if candidate in valid_keys:
        return candidate
    try:
        word_index = int(candidate)
    except ValueError:
        return None
    matches = [token.stable_key for token in tokens if token.word_index == word_index]
    return matches[0] if len(matches) == 1 else None


def _word_index_from_selection_key(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).split(":")[-1])
    except ValueError:
        return None


@_traced_stage("hebrew_component_v2_register")
def _component():
    return st.components.v2.component(
        "hebrew_token_selector",
        html=(_FRONTEND_DIR / "index.html").read_text(encoding="utf-8"),
        css=(_FRONTEND_DIR / "style.css").read_text(encoding="utf-8"),
        js=(_FRONTEND_DIR / "main.js").read_text(encoding="utf-8"),
    )
