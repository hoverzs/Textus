from __future__ import annotations

from passage_trace import traced as _traced_stage  # TEMPORARY passage-crash diagnostics

from pathlib import Path
from collections.abc import Callable
from typing import Any

import streamlit as st

from bible_engine.tagnt_parser import GreekToken


_COMPONENT_DIR = Path(__file__).parent
_FRONTEND_DIR = _COMPONENT_DIR / "frontend"


def greek_token_selector(
    tokens: list[GreekToken],
    selected_word_index: int,
    key: str,
    on_selected_word_index_change: Callable[[], None] | None = None,
) -> int | None:
    selected_key = str(selected_word_index)
    result = greek_token_selector_value(
        tokens=tokens,
        selected_token_key=selected_key,
        key=key,
        on_selected_token_key_change=on_selected_word_index_change,
    )
    if result is None:
        return None
    return normalize_component_selection(_word_index_from_selection_key(result), tokens)


@_traced_stage("greek_token_selector_component_v2")
def greek_token_selector_value(
    tokens: list[GreekToken],
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
    return normalize_component_selection_key(selected, tokens)


@_traced_stage("greek_component_v2_register")
def _component():
    return st.components.v2.component(
        "greek_token_selector",
        html=(_FRONTEND_DIR / "index.html").read_text(encoding="utf-8"),
        css=(_FRONTEND_DIR / "style.css").read_text(encoding="utf-8"),
        js=(_FRONTEND_DIR / "main.js").read_text(encoding="utf-8"),
    )


def component_tokens(
    tokens: list[GreekToken],
    selected_token_key: str | int | None = None,
    *,
    selected_word_index: int | None = None,
) -> list[dict[str, int | str | bool]]:
    if selected_token_key is None and selected_word_index is not None:
        selected_token_key = selected_word_index
    selected_key = str(selected_token_key) if selected_token_key is not None else None
    rendered = []
    for token in sorted(
        tokens,
        key=lambda token: (token.book, token.chapter, token.verse, token.word_index),
    ):
        item: dict[str, int | str | bool] = {
            "book": token.book,
            "chapter": token.chapter,
            "verse": token.verse,
            "word_index": token.word_index,
            "greek_form": token.greek_form,
            "selection_key": _token_selection_key(token),
            "selected": _token_selection_key(token) == selected_key
            or (
                selected_key is not None
                and ":" not in selected_key
                and str(token.word_index) == selected_key
            ),
        }
        rendered.append(item)
    return rendered


def normalize_component_selection(value: Any, tokens: list[GreekToken]) -> int | None:
    valid_indexes = {token.word_index for token in tokens}
    try:
        selected = int(value)
    except (TypeError, ValueError):
        return None
    return selected if selected in valid_indexes else None


def normalize_component_selection_key(value: Any, tokens: list[GreekToken]) -> str | None:
    if value is None:
        return None
    candidate = str(value)
    valid_keys = {_token_selection_key(token) for token in tokens}
    if candidate in valid_keys:
        return candidate
    selected_word_index = normalize_component_selection(candidate, tokens)
    return str(selected_word_index) if selected_word_index is not None else None


def _token_selection_key(token: GreekToken) -> str:
    return f"{token.book}:{token.chapter}:{token.verse}:{token.word_index}"


def _word_index_from_selection_key(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).split(":")[-1])
    except ValueError:
        return None
