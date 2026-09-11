"""Központi Bibliai szöveg — UI és session-szinkron.

Tartós kulcsok (project_data / workspace):
- `last_igehely`  → igehely (`passage` szerep)
- `bible_translation` → fordítás megnevezése (RÚF 2014 az automatikus betöltésnél)
- `passage_text` → teljes bibliai szöveg
- `passage_text_source` / `passage_text_source_url` / `passage_text_fetched_at`
  / `passage_text_fetched_reference` → forrásmeta (nem a szöveg része)
- `passage_text_last_fetched_text` → az utolsó sikeres RÚF-lekérés szövege
  (belső összehasonlításra: kézi mentéskor ebből derül ki, hogy a szöveg
  ténylegesen eltér-e az utolsó API-eredménytől — nem UI-elem)

Widgetkulcsok nem mennek mentésbe.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any, Callable, MutableMapping

import streamlit as st

from bible_engine.greek_analysis_ui import render_greek_analysis_block
from ruf_bible_service import (
    SOURCE_NAME,
    SOURCE_ATTRIBUTION,
    TRANSLATION_NAME,
    fetch_ruf_passage,
    format_structured_verses,
    parse_bible_reference,
)
from ui_components import render_work_section

# Durable session / project keys
DURABLE_PASSAGE_TEXT = "passage_text"
DURABLE_TRANSLATION = "bible_translation"
DURABLE_PASSAGE = "last_igehely"  # meglévő igehely-kulcs
DURABLE_SOURCE = "passage_text_source"
DURABLE_SOURCE_URL = "passage_text_source_url"
DURABLE_FETCHED_AT = "passage_text_fetched_at"
DURABLE_FETCHED_REF = "passage_text_fetched_reference"
DURABLE_LAST_FETCHED_TEXT = "passage_text_last_fetched_text"

# adatsema_v1.md 2. pont: BibliaiSzoveg forrás-típusok.
SOURCE_TYPE_USER_OVERRIDE = "user_override"
SOURCE_TYPE_LOCAL_STORE = "local_store"
SOURCE_TYPE_EXTERNAL_API = "external_api"

# Widget-only
KEY_PASSAGE_TEXT_INPUT = "passage_text_input"
# Legacy widget keys (régi projektek / session; nem rendereljük)
KEY_TRANSLATION_SELECT = "bible_translation_select"
KEY_TRANSLATION_OTHER = "bible_translation_other"
RESYNC_FLAG = "_bible_text_ui_resync"
FLASH_KEY = "_bible_text_flash"
STYLES_FLAG = "_bible_text_styles_injected"
RUF_LAST_ERROR_KEY = "_bible_text_ruf_last_error"
RUF_LAST_ERROR_REF_KEY = "_bible_text_ruf_last_error_ref"
BIBLE_TEXT_VIEW_KEY = "_bible_text_view_mode"
MANUAL_PASTE_EXPANDER_KEY = "_bible_text_manual_paste_expander"

# „17Ti…”, „17 Ti…”, „17. Ti…”, „100. Ti…” — versszám csak a sor elején.
_VERSE_LINE_RE = re.compile(r"^(\d{1,3})(?:\.\s*|\s+)?(\D.*)$")

# A RÚF betöltő gomb saját, kék primary stílusa (ne örökölje a Streamlit
# alapértelmezett piros primary színét; ne érintse a többi gombot).
_BIBLE_TEXT_CSS = """
<style>
.bible-ruf-load-marker {
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}

.st-key-bible_text_ruf_load_btn button,
.st-key-bible_text_ruf_load_btn [data-testid="stBaseButton-primary"],
.st-key-bible_text_ruf_load_btn button *,
.st-key-bible_text_ruf_load_btn button p,
.st-key-bible_text_ruf_load_btn button [data-testid="stMarkdownContainer"] p,
.st-key-bible_text_ruf_load_btn button [data-testid="stMarkdownContainer"] span,
.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button,
.element-container:has(.bible-ruf-load-marker) + .element-container [data-testid="stBaseButton-primary"],
.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button *,
.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button p {
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
  text-shadow: 0 1px 0 rgba(18, 32, 48, 0.25) !important;
}

/* Csak a marker utáni gomb — Textus primary kék */
.st-key-bible_text_ruf_load_btn button,
.st-key-bible_text_ruf_load_btn [data-testid="stBaseButton-primary"],
.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button,
.element-container:has(.bible-ruf-load-marker) + .element-container [data-testid="stBaseButton-primary"] {
  position: relative !important;
  background-color: #4d6f9a !important;
  background-image: linear-gradient(
      180deg,
      #6d8bb6 0%,
      #4d6f9a 52%,
      #3b5a84 100%
    ) !important;
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
  border: 1px solid #35557c !important;
  border-radius: 12px !important;
  font-family: "Inter", "Segoe UI", sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: 0.01em !important;
  text-transform: none !important;
  text-shadow: 0 1px 0 rgba(18, 32, 48, 0.25) !important;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.28) inset,
    0 4px 10px rgba(31, 51, 77, 0.28) !important;
}

.st-key-bible_text_ruf_load_btn button:hover,
.st-key-bible_text_ruf_load_btn [data-testid="stBaseButton-primary"]:hover,
.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button:hover,
.element-container:has(.bible-ruf-load-marker) + .element-container [data-testid="stBaseButton-primary"]:hover {
  background:
    linear-gradient(
      180deg,
      #7a98c0 0%,
      #5a7aa8 52%,
      #45678f 100%
    ) !important;
  color: #ffffff !important;
  border-color: #35557c !important;
  transform: translateY(-1px) !important;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.34) inset,
    0 7px 14px rgba(31, 51, 77, 0.32) !important;
}

.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button:active,
.element-container:has(.bible-ruf-load-marker) + .element-container [data-testid="stBaseButton-primary"]:active {
  transform: translateY(1px) !important;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.18) inset,
    0 1px 3px rgba(31, 51, 77, 0.28) inset !important;
}

.st-key-bible_text_ruf_load_btn button > div > p,
.st-key-bible_text_ruf_load_btn [data-testid="stBaseButton-primary"] > div > p,
.element-container:has(.bible-ruf-load-marker) + .element-container .stButton > button > div > p,
.element-container:has(.bible-ruf-load-marker) + .element-container [data-testid="stBaseButton-primary"] > div > p {
  color: #ffffff !important;
  text-shadow: 0 1px 0 rgba(18, 32, 48, 0.25) !important;
}

.bible-reader {
  margin: 0.12rem 0 0.4rem 0;
  padding: 0.1rem 0;
  max-width: 74ch;
  max-height: min(58vh, 520px);
  overflow-y: auto;
  box-sizing: border-box;
}

.bible-verse {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  margin: 0 0 0.28rem 0;
  line-height: 1.52;
}

.bible-verse:last-child,
.bible-para:last-child {
  margin-bottom: 0;
}

.bible-verse-num {
  flex: 0 0 auto;
  width: 2.1rem;
  font-size: 0.86rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #746a5e;
  line-height: 1.52;
  padding-top: 0.02em;
  user-select: none;
  text-align: right;
}

.bible-verse-text {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 1.04rem;
  font-weight: 450;
  color: #2a241c;
  line-height: 1.52;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.bible-para {
  margin: 0 0 0.42rem 0;
  font-size: 1.04rem;
  font-weight: 450;
  color: #2a241c;
  line-height: 1.52;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.bible-reader-continuous {
  font-size: 1.04rem;
  font-weight: 450;
  line-height: 1.52;
  color: #2a241c;
}

.bible-reader-continuous .bible-inline-verse {
  margin-right: 0.26rem;
}

.bible-reader-continuous .bible-inline-num {
  display: inline-block;
  min-width: 1.65rem;
  margin-right: 0.16rem;
  color: #746a5e;
  font-size: 0.82em;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  vertical-align: 0.06em;
}

.bible-source-note {
  margin: 0.04rem 0 0.12rem 0;
  font-size: 0.75rem;
  line-height: 1.3;
  color: #7a6c5c;
}

.bible-source-note a {
  color: #4a6a8c;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.bible-view-radio-marker {
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}
.element-container:has(.bible-view-radio-marker) {
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}
.element-container:has(.bible-view-radio-marker) + .element-container {
  margin-top: 0 !important;
  margin-bottom: 4px !important;
}
.element-container:has(.bible-view-radio-marker) + .element-container [data-testid="stRadio"] {
  gap: 4px !important;
}
.element-container:has(.bible-view-radio-marker) + .element-container label {
  min-height: 0 !important;
  padding-top: 2px !important;
  padding-bottom: 2px !important;
}

@media (max-width: 640px) {
  .bible-reader {
    padding: 0.2rem 0;
    max-height: min(52vh, 440px);
  }
  .bible-verse {
    gap: 0.45rem;
    margin-bottom: 0.22rem;
  }
  .bible-verse-text,
  .bible-para {
    font-size: 1rem;
  }
}
</style>
"""


def normalize_passage_text(value: Any) -> str:
    """Sortörések megőrzése; csak CRLF → LF."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text


def parse_passage_text_blocks(passage_text: str) -> list[tuple[str | None, str]]:
    """passage_text sorok → (verszám|None, szöveg) listája.

    Felismeri: ``17 Ti…``, ``17. Ti…``, ``17  Ti…``.
    Versszám nélküli sor → (None, teljes sor).
    """
    text = normalize_passage_text(passage_text)
    blocks: list[tuple[str | None, str]] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = _VERSE_LINE_RE.match(line)
        if m:
            blocks.append((m.group(1), m.group(2).strip()))
        else:
            blocks.append((None, line))
    return blocks


def format_passage_text_blocks(blocks: list[tuple[str | None, str]]) -> str:
    lines: list[str] = []
    for num, body in blocks:
        clean_body = normalize_passage_text(body).strip()
        if not clean_body:
            continue
        if num is None:
            lines.append(clean_body)
        else:
            lines.append(f"{num}. {clean_body}")
    return "\n".join(lines)


def normalize_verse_number_spacing(passage_text: str) -> str:
    return format_passage_text_blocks(parse_passage_text_blocks(passage_text))


# A Szentírás.eu API (és a belőle importált helyi RÚF-tár) néhány vers
# szövegébe közvetlenül beágyazott szakaszcím-/kereszthivatkozás-HTML-t ad
# vissza (pl. "1. Péter halfogása <a href='Mt 4,18-22'>Mt 4,18-22</a>; ...").
# A `ruf_bible_local_db.py` szerződéses elvárása szerint ezt a szöveget SZÓ
# SZERINT, változtatás nélkül kell TÁROLNI — ezért a nyers HTML-t itt, a
# MEGJELENÍTÉSI rétegben szűrjük ki (nem a tárolt/visszaadott adatban).
# Puszta `html.escape()` nélküle csak láthatóvá, nem eltávolítottá tenné a
# taget (a felhasználó a nyers `&lt;a href=...&gt;` szöveget látná). Ugyanaz
# a minta, mint a Konkordancia MEGJELENÍTÉSI rétegében (`concordance_ui.py`
# `_strip_html_tags`) — itt önálló másolatként, hogy ez a modul ne kössön
# új importot egy UI-feature-specifikus modulra.
_EMBEDDED_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DOUBLE_SPACE_RE = re.compile(r" {2,}")


def _strip_embedded_html_tags(text: str) -> str:
    """Tag eltávolítás, majd a tag körüli szóközök összevonása — a
    versszám és a szöveg közötti térköz emiatt nem sérülhet meg akkor sem,
    ha egy eltávolított tag mindkét oldalán szóköz maradt."""
    without_tags = _EMBEDDED_HTML_TAG_RE.sub("", text or "")
    return _DOUBLE_SPACE_RE.sub(" ", without_tags).strip()


def build_formatted_bible_text_html(
    passage_text: str,
    *,
    view_mode: str = "Versenkénti nézet",
) -> str:
    """Biztonságos HTML a formázott olvasónézethez (escape-elt tartalom)."""
    blocks = parse_passage_text_blocks(passage_text)
    if not blocks:
        return ""

    if view_mode == "Folyamatos nézet":
        inline_parts: list[str] = []
        for num, body in blocks:
            clean_body = _strip_embedded_html_tags(body)
            safe_body = html.escape(clean_body, quote=True)
            if num is None:
                inline_parts.append(safe_body)
            else:
                safe_num = html.escape(num, quote=True)
                inline_parts.append(
                    '<span class="bible-inline-verse">'
                    f'<span class="bible-inline-num">{safe_num}.</span>'
                    f'{safe_body}</span>'
                )
        return (
            '<div class="bible-reader bible-reader-continuous">'
            + " ".join(inline_parts)
            + "</div>"
        )

    parts: list[str] = ['<div class="bible-reader bible-reader-lines">']
    for num, body in blocks:
        clean_body = _strip_embedded_html_tags(body)
        safe_body = html.escape(clean_body, quote=True)
        if num is None:
            parts.append(f'<p class="bible-para">{safe_body}</p>')
        else:
            safe_num = html.escape(num, quote=True)
            parts.append(
                '<div class="bible-verse">'
                f'<span class="bible-verse-num">{safe_num}.</span>'
                f'<span class="bible-verse-text">{safe_body}</span>'
                "</div>"
            )
    parts.append("</div>")
    return "\n".join(parts)


def render_formatted_bible_text(
    passage_text: str,
    *,
    view_key: str = BIBLE_TEXT_VIEW_KEY,
) -> None:
    """Formázott, csak olvasható Bibliai szöveg előnézet."""
    st.markdown('<div class="bible-view-radio-marker"></div>', unsafe_allow_html=True)
    view_mode = st.radio(
        "Bibliai szöveg nézete",
        ("Versenkénti nézet", "Folyamatos nézet"),
        key=view_key,
        horizontal=True,
        label_visibility="collapsed",
    )
    markup = build_formatted_bible_text_html(passage_text, view_mode=view_mode)
    if not markup:
        return
    st.markdown(markup, unsafe_allow_html=True)


def apply_bible_text_resync_if_needed(session_state: MutableMapping[str, Any]) -> None:
    """Widgetkulcsok szinkronja a tartós mezőkkel (widget létrehozása előtt)."""
    force = bool(session_state.pop(RESYNC_FLAG, False))
    text = normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))

    if force or KEY_PASSAGE_TEXT_INPUT not in session_state:
        session_state[KEY_PASSAGE_TEXT_INPUT] = text


def queue_bible_widget_sync_values(session_state: MutableMapping[str, Any]) -> dict[str, str]:
    """Pending project widget sync dict-be tehető értékek."""
    text = normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))
    return {KEY_PASSAGE_TEXT_INPUT: text}


def save_bible_text_from_widgets(session_state: MutableMapping[str, Any]) -> dict[str, str]:
    """Widgetek → tartós passage_text / bible_translation (és last_igehely szinkron)."""
    apply_bible_text_resync_if_needed(session_state)

    ige = str(session_state.get("igehely_input") or "").strip()
    if ige:
        session_state[DURABLE_PASSAGE] = ige

    text = normalize_verse_number_spacing(session_state.get(KEY_PASSAGE_TEXT_INPUT))
    session_state[DURABLE_PASSAGE_TEXT] = text

    # Ha a mentett szöveg eltér az utolsó sikeres RÚF-lekérés szövegétől,
    # a felhasználó ténylegesen felülírta kézzel — a forrás user_override
    # lesz. Ha megegyezik (pl. autosave-flush, a user nem nyúlt hozzá),
    # a meglévő forrásjelzést (external_api/local_store) nem bántjuk.
    last_fetched = session_state.get(DURABLE_LAST_FETCHED_TEXT)
    if last_fetched is None or text != normalize_passage_text(last_fetched):
        session_state[DURABLE_SOURCE] = SOURCE_TYPE_USER_OVERRIDE
        session_state[DURABLE_SOURCE_URL] = ""
        session_state[DURABLE_FETCHED_AT] = ""
        session_state[DURABLE_FETCHED_REF] = ""

    # A központi blokk RÚF 2014-re van szabva (automatikus + kézi).
    translation = TRANSLATION_NAME
    session_state[DURABLE_TRANSLATION] = translation
    return {
        "passage": str(session_state.get(DURABLE_PASSAGE) or ""),
        "bible_translation": translation,
        "passage_text": text,
    }


def get_bible_text_snapshot(session_state: MutableMapping[str, Any]) -> dict[str, str]:
    return {
        "passage": (
            str(session_state.get(DURABLE_PASSAGE) or "").strip()
            or str(session_state.get("igehely_input") or "").strip()
        ),
        "bible_translation": str(
            session_state.get(DURABLE_TRANSLATION) or TRANSLATION_NAME
        ).strip()
        or TRANSLATION_NAME,
        "passage_text": normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT)),
        "passage_text_source": str(session_state.get(DURABLE_SOURCE) or "").strip(),
        "passage_text_source_url": str(session_state.get(DURABLE_SOURCE_URL) or "").strip(),
        "passage_text_fetched_at": str(session_state.get(DURABLE_FETCHED_AT) or "").strip(),
        "passage_text_fetched_reference": str(
            session_state.get(DURABLE_FETCHED_REF) or ""
        ).strip(),
    }


def _ensure_bible_text_styles() -> None:
    if st.session_state.get(STYLES_FLAG):
        return
    st.session_state[STYLES_FLAG] = True
    st.markdown(_BIBLE_TEXT_CSS, unsafe_allow_html=True)


def _current_reference(session_state: MutableMapping[str, Any]) -> str:
    return (
        str(session_state.get("igehely_input") or "").strip()
        or str(session_state.get(DURABLE_PASSAGE) or "").strip()
    )


def _display_passage_text(session_state: MutableMapping[str, Any]) -> str:
    """Olvasónézet forrása: widget (ha van), különben tartós mező."""
    if KEY_PASSAGE_TEXT_INPUT in session_state:
        widget_text = normalize_passage_text(session_state.get(KEY_PASSAGE_TEXT_INPUT))
        if widget_text.strip():
            return widget_text
    return normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))


def _reraise_streamlit_runtime_error(exc: BaseException) -> None:
    """Do not swallow Streamlit widget / rerun control errors as missing data."""
    from streamlit.errors import Error as StreamlitError

    if isinstance(exc, StreamlitError):
        raise exc


def _refs_equivalent(a: str, b: str) -> bool:
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return (
            parse_bible_reference(a).normalized_reference
            == parse_bible_reference(b).normalized_reference
        )
    except ValueError:
        return a.casefold() == b.casefold()


def _set_flash(kind: str, text: str) -> None:
    st.session_state[FLASH_KEY] = {"type": kind, "text": text}


def _render_flash() -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if not isinstance(flash, dict):
        return
    text = str(flash.get("text") or "").strip()
    if not text:
        return
    kind = flash.get("type") or "info"
    if kind == "error":
        st.error(text)
    elif kind == "warning":
        st.warning(text)
    elif kind == "success":
        st.success(text)
    else:
        st.info(text)


def _apply_ruf_fetch_success(result: dict[str, Any]) -> bool:
    verses = result.get("verses")
    if isinstance(verses, list) and verses:
        text = format_structured_verses(verses)
    else:
        text = normalize_verse_number_spacing(result.get("text"))
    if not normalize_passage_text(text).strip():
        return False
    st.session_state[DURABLE_PASSAGE_TEXT] = text
    st.session_state[DURABLE_TRANSLATION] = TRANSLATION_NAME
    # cache_status "live" = valódi hálózati hívás; "fresh"/"stale_fallback" a
    # process-szintű memória-cache-ből jött, nem új API-hívásból.
    st.session_state[DURABLE_SOURCE] = (
        SOURCE_TYPE_EXTERNAL_API
        if result.get("cache_status") == "live"
        else SOURCE_TYPE_LOCAL_STORE
    )
    st.session_state[DURABLE_SOURCE_URL] = str(result.get("source_url") or "")
    st.session_state[DURABLE_FETCHED_AT] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    st.session_state[DURABLE_FETCHED_REF] = str(
        result.get("normalized_reference") or result.get("requested_reference") or ""
    )
    st.session_state[DURABLE_LAST_FETCHED_TEXT] = text
    ige = _current_reference(st.session_state)
    if ige:
        st.session_state[DURABLE_PASSAGE] = ige
    st.session_state[RESYNC_FLAG] = True
    warnings = [str(w).strip() for w in result.get("warnings", []) if str(w).strip()]
    if warnings:
        _set_flash("warning", warnings[0])
    else:
        _set_flash(
            "success",
            "A RÚF 2014 szövege betöltődött. Mentés előtt ellenőrizd az igehelyet és a szöveget.",
        )
    return True


def _fetch_ruf_for_current_reference(ref: str) -> bool:
    with st.spinner("RÚF-szöveg lekérése…"):
        result = fetch_ruf_passage(ref)
    if result.get("success"):
        if not _apply_ruf_fetch_success(result):
            st.session_state[RUF_LAST_ERROR_KEY] = (
                "A Szentírás.eu válasza nem tartalmazott megjeleníthető RÚF-szöveget."
            )
            st.session_state[RUF_LAST_ERROR_REF_KEY] = ref
            return False
        st.session_state.pop(RUF_LAST_ERROR_KEY, None)
        st.session_state.pop(RUF_LAST_ERROR_REF_KEY, None)
        st.rerun()
        return True

    err = str(
        result.get("error")
        or "Külső szolgáltatási kapcsolat hibája: a RÚF-szöveg betöltése nem sikerült."
    )
    st.session_state[RUF_LAST_ERROR_KEY] = err
    st.session_state[RUF_LAST_ERROR_REF_KEY] = ref
    return False


def _render_ruf_error_retry() -> None:
    err = str(st.session_state.get(RUF_LAST_ERROR_KEY) or "").strip()
    ref = str(st.session_state.get(RUF_LAST_ERROR_REF_KEY) or "").strip()
    if not err:
        return
    st.error(err)
    st.info("A kézi beillesztés továbbra is elérhető; a már megadott igehely és szöveg megmarad.")
    if st.button("Újrapróbálás", key="bible_text_ruf_retry_btn"):
        retry_ref = _current_reference(st.session_state) or ref
        if retry_ref:
            _fetch_ruf_for_current_reference(retry_ref)


def _render_source_caption(session_state: MutableMapping[str, Any]) -> None:
    snap = get_bible_text_snapshot(session_state)
    if not normalize_passage_text(snap["passage_text"]).strip():
        return
    source = snap["passage_text_source"]
    if source == SOURCE_TYPE_USER_OVERRIDE:
        st.markdown(
            '<p class="bible-source-note">Kézi beillesztés</p>',
            unsafe_allow_html=True,
        )
        return
    if not source and not snap["passage_text_source_url"]:
        return
    url = snap["passage_text_source_url"]
    caption = html.escape(
        SOURCE_ATTRIBUTION,
        quote=True,
    )
    if url:
        safe_url = html.escape(url, quote=True)
        st.markdown(
            f'<p class="bible-source-note">{caption}<br/>'
            f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">'
            "Megnyitás a forrásoldalon</a></p>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<p class="bible-source-note">{caption}</p>',
            unsafe_allow_html=True,
        )


def _render_reference_mismatch_warning(session_state: MutableMapping[str, Any]) -> None:
    fetched = str(session_state.get(DURABLE_FETCHED_REF) or "").strip()
    current = _current_reference(session_state)
    text = normalize_passage_text(session_state.get(DURABLE_PASSAGE_TEXT))
    if not fetched or not current or not text.strip():
        return
    if _refs_equivalent(fetched, current):
        return
    st.warning(
        f"Az igehely ({current}) különbözik a szöveg utolsó RÚF-betöltésekor "
        f"használt helytől ({fetched}). A mentett szöveg nem törlődött — "
        "szükség esetén töltsd be újra vagy szerkeszd kézzel."
    )


def _render_ruf_load_button() -> None:
    st.markdown('<div class="bible-ruf-load-marker"></div>', unsafe_allow_html=True)
    if st.button(
        "RÚF-szöveg betöltése",
        key="bible_text_ruf_load_btn",
        type="primary",
        width="stretch",
        help="A megadott igehely RÚF 2014 szövegét tölti be.",
    ):
        ref = _current_reference(st.session_state)
        if not ref:
            st.error("Előbb add meg az igehelyet (pl. Júd 17–20).")
        else:
            _fetch_ruf_for_current_reference(ref)
    st.markdown(
        """
        <style>
        html body .st-key-bible_text_ruf_load_btn button[kind="primary"],
        html body .st-key-bible_text_ruf_load_btn button[data-testid="stBaseButton-primary"],
        html body .st-key-bible_text_ruf_load_btn button {
          background-color: #4d6f9a !important;
          background-image: linear-gradient(180deg, #6d8bb6 0%, #4d6f9a 52%, #3b5a84 100%) !important;
          color: #ffffff !important;
          -webkit-text-fill-color: #ffffff !important;
          border: 1px solid #35557c !important;
          box-shadow:
            0 1px 0 rgba(255, 255, 255, 0.28) inset,
            0 4px 10px rgba(31, 51, 77, 0.28) !important;
        }
        html body .st-key-bible_text_ruf_load_btn button *,
        html body .st-key-bible_text_ruf_load_btn button p,
        html body .st-key-bible_text_ruf_load_btn button [data-testid="stMarkdownContainer"] p,
        html body .st-key-bible_text_ruf_load_btn button [data-testid="stMarkdownContainer"] span {
          color: #ffffff !important;
          -webkit-text-fill-color: #ffffff !important;
          text-shadow: 0 1px 0 rgba(18, 32, 48, 0.25) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _render_ruf_error_retry()


def _render_editor_fields(*, save_label: str = "Bibliai szöveg mentése") -> None:
    st.text_area(
        "Teljes bibliai szöveg",
        key=KEY_PASSAGE_TEXT_INPUT,
        height=220,
        placeholder="Töltsd be a RÚF szöveget, vagy illeszd be ide kézzel…",
    )
    if st.button(save_label, key="bible_text_save_btn", width="stretch"):
        saved = save_bible_text_from_widgets(st.session_state)
        n = len((saved["passage_text"] or "").strip())
        if n:
            st.success(
                f"Bibliai szöveg elmentve ({saved['bible_translation']}) — {n} karakter."
            )
        else:
            st.success("Bibliai szöveg mező elmentve (üres).")


def _render_manual_paste_fallback() -> None:
    expander = st.expander(
        "Bibliai szöveg kézi beillesztése",
        expanded=False,
        key=MANUAL_PASTE_EXPANDER_KEY,
        on_change="rerun",
    )
    if expander.open:
        with expander:
            _render_editor_fields()


def render_bible_text_editor(
    *,
    hebrew_contextual_analysis_generate_fn: Callable[..., str] | None = None,
    hebrew_contextual_analysis_model_id: str = "gemini-2.5-flash",
    hebrew_contextual_analysis_generate_kwargs: dict[str, object] | None = None,
) -> None:
    """Szerkeszthető Bibliai szöveg blokk (Textusműhely / Igehely szakasz).

    ``hebrew_contextual_analysis_generate_fn`` — without it,
    ``render_greek_analysis_block``'s Hebrew path renders no Phase 2E
    section at all (``render_hebrew_contextual_analysis_panel`` returns
    immediately when its ``generate_text_fn`` is ``None``, by design — see
    that function's own docstring). This is the "Igehely" tab's own
    Hebrew/Greek word preview, so the caller must forward the same
    ``generate_hebrew_contextual_analysis_text`` binding
    ``render_original_text_panel`` already passes, or the panel silently
    disappears here even though the deterministic morphology/lexicon card
    above it renders fine (they are independent data paths)."""
    _ensure_bible_text_styles()
    apply_bible_text_resync_if_needed(st.session_state)

    render_work_section(
        title="Bibliai szöveg",
        body="RÚF 2014",
        show_rule=False,
    )

    _render_flash()
    _render_reference_mismatch_warning(st.session_state)
    _render_ruf_load_button()

    display_text = _display_passage_text(st.session_state)
    # Az olvasónézet csak tartós / betöltött szövegnél jelenjen meg —
    # gépelés közben ne csukódjon össze a szerkesztő.
    has_text = bool(
        normalize_passage_text(st.session_state.get(DURABLE_PASSAGE_TEXT)).strip()
    )

    if has_text:
        render_formatted_bible_text(display_text)
        _render_source_caption(st.session_state)
        render_greek_analysis_block(
            reference=_current_reference(st.session_state),
            key_prefix="bible_text_ui",
            hebrew_contextual_analysis_generate_fn=hebrew_contextual_analysis_generate_fn,
            hebrew_contextual_analysis_model_id=hebrew_contextual_analysis_model_id,
            hebrew_contextual_analysis_generate_kwargs=hebrew_contextual_analysis_generate_kwargs,
        )
        _render_manual_paste_fallback()
    else:
        _render_source_caption(st.session_state)
        render_greek_analysis_block(
            reference=_current_reference(st.session_state),
            key_prefix="bible_text_ui",
            hebrew_contextual_analysis_generate_fn=hebrew_contextual_analysis_generate_fn,
            hebrew_contextual_analysis_model_id=hebrew_contextual_analysis_model_id,
            hebrew_contextual_analysis_generate_kwargs=hebrew_contextual_analysis_generate_kwargs,
        )
        _render_manual_paste_fallback()


def render_bible_text_preview(*, expanded: bool = False) -> None:
    """Csak olvasható előnézet (Igehirdetési műhely)."""
    _ensure_bible_text_styles()
    snap = get_bible_text_snapshot(st.session_state)
    passage = snap["passage"] or "—"
    translation = snap["bible_translation"] or TRANSLATION_NAME
    text = snap["passage_text"]

    with st.expander("Bibliai szöveg", expanded=expanded):
        st.markdown(f"**Igehely:** {passage}  ·  **Fordítás:** {translation}")
        if text.strip():
            render_formatted_bible_text(text)
            _render_source_caption(st.session_state)
        else:
            st.caption(
                "Még nincs bibliai szöveg. "
                "Töltsd be vagy add meg a Textusműhelyben."
            )


def render_bible_text_reading_block(
    *,
    original_language_key_prefix: str,
    bible_view_key: str = BIBLE_TEXT_VIEW_KEY,
    display_mode: str = "full",
    hebrew_contextual_analysis_generate_fn: Callable[..., str] | None = None,
    hebrew_contextual_analysis_model_id: str = "gemini-2.5-flash",
    hebrew_contextual_analysis_generate_kwargs: dict[str, object] | None = None,
) -> None:
    """Read-only RÚF + eredeti nyelvi token UI.

    A tartós projektmezőket olvassa (`last_igehely`, `passage_text`).
    Nem szerkeszt, nem tölt be RÚF-ot, és nem indít LLM-et.
    Hiányzó vagy hibás adat nem emeli a kivételt a hívó felé.
    """
    _ensure_bible_text_styles()
    snap = get_bible_text_snapshot(st.session_state)
    reference = (snap.get("passage") or "").strip()
    text = snap.get("passage_text") or ""
    translation = (snap.get("bible_translation") or TRANSLATION_NAME).strip() or TRANSLATION_NAME

    if reference:
        st.markdown(f"**Igehely:** {reference}  ·  **Fordítás:** {translation}")

    if str(text).strip():
        try:
            render_formatted_bible_text(str(text), view_key=bible_view_key)
            _render_source_caption(st.session_state)
        except Exception as exc:
            _reraise_streamlit_runtime_error(exc)
            st.caption("A RÚF szöveg jelenleg nem jeleníthető meg.")
    elif reference:
        st.caption(
            "Még nincs RÚF szöveg ehhez az igehelyhez. "
            "Töltsd be a Textusműhelyben."
        )
    else:
        st.caption(
            "Nincs megadott igehely. Add meg a Textusműhelyben, "
            "majd térj vissza az Íróasztalra."
        )

    if not reference:
        return

    try:
        render_greek_analysis_block(
            reference=reference,
            key_prefix=original_language_key_prefix,
            display_mode=display_mode,
            hebrew_contextual_analysis_generate_fn=hebrew_contextual_analysis_generate_fn,
            hebrew_contextual_analysis_model_id=hebrew_contextual_analysis_model_id,
            hebrew_contextual_analysis_generate_kwargs=hebrew_contextual_analysis_generate_kwargs,
        )
    except Exception as exc:
        _reraise_streamlit_runtime_error(exc)
        st.caption("Az eredeti nyelvi szöveg jelenleg nem tölthető be.")


__all__ = [
    "DURABLE_PASSAGE_TEXT",
    "DURABLE_TRANSLATION",
    "DURABLE_PASSAGE",
    "DURABLE_SOURCE",
    "DURABLE_SOURCE_URL",
    "DURABLE_FETCHED_AT",
    "DURABLE_FETCHED_REF",
    "DURABLE_LAST_FETCHED_TEXT",
    "SOURCE_TYPE_USER_OVERRIDE",
    "SOURCE_TYPE_LOCAL_STORE",
    "SOURCE_TYPE_EXTERNAL_API",
    "KEY_PASSAGE_TEXT_INPUT",
    "KEY_TRANSLATION_SELECT",
    "KEY_TRANSLATION_OTHER",
    "RESYNC_FLAG",
    "TRANSLATION_NAME",
    "normalize_passage_text",
    "parse_passage_text_blocks",
    "format_passage_text_blocks",
    "normalize_verse_number_spacing",
    "build_formatted_bible_text_html",
    "render_formatted_bible_text",
    "apply_bible_text_resync_if_needed",
    "queue_bible_widget_sync_values",
    "save_bible_text_from_widgets",
    "get_bible_text_snapshot",
    "render_bible_text_editor",
    "render_bible_text_preview",
    "render_bible_text_reading_block",
]
