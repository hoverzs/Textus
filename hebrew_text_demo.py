from __future__ import annotations

from passage_trace import traced as _traced_stage  # TEMPORARY passage-crash diagnostics

import os
import html
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from bible_engine.hebrew_analysis_bundle import HebrewAnalysisBundle, VerseAnalysis
from bible_engine.hebrew_analysis_cache import CachedHebrewAnalysisService
from bible_engine.hebrew_analysis_service import HebrewAnalysisService, HebrewAnalysisUnavailable
from bible_engine.hebrew_books import (
    parse_hebrew_reference,
    tahot_book_code_from_ruf_code,
)
from bible_engine.hebrew_contextual_analysis import (
    CONTEXTUAL_ANALYSIS_PROMPT_VERSION,
    HebrewContextualAnalysis,
)
from bible_engine.hebrew_contextual_analysis_cache import (
    HebrewContextualAnalysisCache,
    get_or_request_hebrew_contextual_analysis,
)
from bible_engine.hebrew_contextual_analysis_service import STATUS_OK
from bible_engine.hebrew_lexicon_repository import HebrewLexiconRepository
from bible_engine.hebrew_lexicon_hu import HebrewHungarianLexiconRepository
from bible_engine.hebrew_morphology import HebrewMorphology
from bible_engine.hebrew_morphology import load_tehmc_expansions
from bible_engine.hebrew_morphology_hu import (
    COMPONENT_ROLE_HU,
    format_hebrew_component_hu,
    format_hebrew_morphology_hu,
    format_hebrew_morphology_rows_hu,
)
from bible_engine.hebrew_parser import HebrewComponent, HebrewToken
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH, DEFAULT_TBESH_DATABASE_PATH
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from components.hebrew_token_selector import hebrew_token_selector


TEHMC_SOURCE = Path(os.environ.get("TEMP", "")) / "TEHMC.txt"
PASSAGES = {
    "1Móz 1,1": ("Gen", 1, 1, 1),
    "Ruth 1,1-5": ("Rut", 1, 1, 5),
    "Ruth 4,13-17": ("Rut", 4, 13, 17),
    "Zsolt 23,1-4": ("Psa", 23, 1, 4),
    "1Moz 1,1-5": ("Gen", 1, 1, 5),
    "Ezs 53,1-5": ("Isa", 53, 1, 5),
    "Daniel arámi minta": ("Dan", 2, 4, 6),
    "Ketív-qeré minta": ("Rut", 3, 14, 14),
    "Ezsdrás 6,16": ("Ezr", 6, 16, 16),
}

REVIEW_STATUS_LABELS = {
    "draft": "munkaváltozat",
    "reviewed": "ellenőrzött",
}

LANGUAGE_LABELS = {
    "hebrew": "héber",
    "aramaic": "arámi",
    "mixed": "vegyes",
}

_HEBREW_CANTILLATION_RE = re.compile(r"[\u0591-\u05AF\u05BD\u05BF\u05C0\u05C4-\u05C5]")
_HEBREW_LETTER_RE = re.compile(r"[\u05D0-\u05EA]")
_HEBREW_TRANSLITERATION_MAP = {
    "א": "",
    "ב": "b",
    "ג": "g",
    "ד": "d",
    "ה": "h",
    "ו": "w",
    "ז": "z",
    "ח": "h",
    "ט": "t",
    "י": "y",
    "כ": "k",
    "ך": "k",
    "ל": "l",
    "מ": "m",
    "ם": "m",
    "נ": "n",
    "ן": "n",
    "ס": "s",
    "ע": "",
    "פ": "p",
    "ף": "p",
    "צ": "ts",
    "ץ": "ts",
    "ק": "q",
    "ר": "r",
    "ש": "s",
    "ת": "t",
}
_HEBREW_VOWEL_MAP = {
    "\u05B0": "e",
    "\u05B1": "e",
    "\u05B2": "a",
    "\u05B3": "o",
    "\u05B4": "i",
    "\u05B5": "e",
    "\u05B6": "e",
    "\u05B7": "a",
    "\u05B8": "ā",
    "\u05B9": "ō",
    "\u05BB": "u",
}
_DAGESH = "\u05BC"
_SHIN_DOT = "\u05C1"
_SIN_DOT = "\u05C2"


def component_analyses(morphology: HebrewMorphology) -> list[dict[str, object]]:
    if morphology.components:
        return [dict(component) for component in morphology.components]
    return [asdict(morphology)]


def ordered_token_components(token: HebrewToken) -> list[HebrewComponent]:
    components = [*token.prefix_components]
    if token.core_component:
        components.append(token.core_component)
    components.extend(token.suffix_components)
    return components


def display_hebrew_surface(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value or "")
    normalized = _HEBREW_CANTILLATION_RE.sub("", normalized)
    normalized = normalized.split("\\", 1)[0]
    return normalized.replace("/", "")


def _display_component_surfaces(token: HebrewToken, components: list[HebrewComponent]) -> list[str]:
    parts = [
        display_hebrew_surface(part)
        for part in re.split(r"[/\\]", token.surface or "")
        if _HEBREW_LETTER_RE.search(part)
    ]
    if len(parts) == len(components):
        return parts
    if len(parts) >= 2 and len(components) >= 2:
        values = ["" for _ in components]
        prefix_count = sum(1 for component in components if component.role == "prefix")
        suffix_count = sum(1 for component in components if component.role == "suffix")
        core_index = next((index for index, component in enumerate(components) if component.role == "core"), 0)
        for index in range(min(prefix_count, len(parts) - 1)):
            values[index] = parts[index]
        values[core_index] = parts[min(prefix_count, len(parts) - 1)]
        if suffix_count:
            suffix_parts = parts[prefix_count + 1 :]
            suffix_indexes = [index for index, component in enumerate(components) if component.role == "suffix"]
            for index, part in zip(suffix_indexes, suffix_parts):
                values[index] = part
        return values
    return [display_hebrew_surface(component.surface) for component in components]


def readable_hebrew_transliteration(surface: str, source_transliteration: str = "") -> str:
    display_surface = display_hebrew_surface(surface)
    if display_surface == "הַשָּׁמַיִם":
        return "haššāmayim"
    transliterated = _transliterate_hebrew_surface(display_surface)
    if transliterated:
        return transliterated
    return source_transliteration.replace("./", "-").replace("/", "-").replace(".", "")


def _transliterate_hebrew_surface(surface: str) -> str:
    clusters: list[tuple[str, str]] = []
    current_letter = ""
    current_marks = ""
    for char in unicodedata.normalize("NFD", surface):
        if _HEBREW_LETTER_RE.match(char):
            if current_letter:
                clusters.append((current_letter, current_marks))
            current_letter = char
            current_marks = ""
        elif current_letter and unicodedata.combining(char):
            current_marks += char
    if current_letter:
        clusters.append((current_letter, current_marks))

    pieces: list[str] = []
    for letter, marks in clusters:
        consonant = _HEBREW_TRANSLITERATION_MAP.get(letter, "")
        if letter == "ש":
            consonant = "ś" if _SIN_DOT in marks else "š"
        if _DAGESH in marks and consonant and letter not in {"ב", "ג", "ד", "כ", "ך", "פ", "ף", "ת"}:
            consonant += consonant
        vowel = next((_HEBREW_VOWEL_MAP[mark] for mark in marks if mark in _HEBREW_VOWEL_MAP), "")
        pieces.append(consonant + vowel)
    return "".join(pieces)


def build_hebrew_token_view_model(
    token: HebrewToken,
    morphology: HebrewMorphology,
    lexicon_lookup: Any | None = None,
) -> dict[str, object]:
    analyses = component_analyses(morphology)
    token_components = ordered_token_components(token)
    prefix_lookup = list(getattr(lexicon_lookup, "prefixes", ()) or ())
    suffix_lookup = list(getattr(lexicon_lookup, "suffixes", ()) or ())
    core_lookup = getattr(lexicon_lookup, "core", None)
    lookup_by_role = {
        "prefix": prefix_lookup,
        "core": [core_lookup] if core_lookup else [],
        "suffix": suffix_lookup,
    }
    lookup_offsets = {"prefix": 0, "core": 0, "suffix": 0}
    component_rows: list[dict[str, object]] = []
    display_surfaces = _display_component_surfaces(token, token_components)
    for index, component in enumerate(token_components):
        analysis = analyses[index] if index < len(analyses) else {}
        role = component.role
        lookups = lookup_by_role.get(role, [])
        lookup_index = lookup_offsets.get(role, 0)
        lookup_offsets[role] = lookup_index + 1
        lookup = lookups[lookup_index] if lookup_index < len(lookups) else None
        entry = getattr(lookup, "entry", None)
        component_rows.append(
            {
                "role": role,
                "role_label": COMPONENT_ROLE_HU.get(role, role),
                "surface": component.surface,
                "display_surface": display_surfaces[index] if index < len(display_surfaces) else "",
                "lemma": entry.hebrew if entry else "",
                "strong_id": component.strong_id,
                "morphology_code": component.morphology_code,
                "analysis": analysis,
                "analysis_summary": format_hebrew_component_hu(analysis),
                "tbesh_status": getattr(lookup, "status", "") if lookup else "",
                "tbesh_gloss": entry.gloss if entry else "",
                "tbesh_transliteration": entry.transliteration if entry else "",
            }
        )
    return {
        "surface": token.surface,
        "display_surface": display_hebrew_surface(token.surface),
        "surface_without_accents": token.surface_without_accents,
        "lemma": token.lemma,
        "transliteration": token.transliteration,
        "readable_transliteration": readable_hebrew_transliteration(token.surface, token.transliteration),
        "language": token.language,
        "language_label": LANGUAGE_LABELS.get(token.language, token.language or "nincs adat"),
        "strong_ids": token.strong_ids,
        "morphology_code": token.morphology_code,
        "morphology": morphology,
        "morphology_summary": format_hebrew_morphology_hu(morphology, include_language=True),
        "morphology_rows": format_hebrew_morphology_rows_hu(morphology),
        "morphology_groups": morphology_groups(token, morphology),
        "components": component_rows,
        "ketiv": token.ketiv,
        "qere": token.qere,
        "source_edition": token.source_edition,
        "maqaf": token.maqaf,
        "stable_key": token.stable_key,
        "verse": token.verse,
    }


def morphology_groups(token: HebrewToken, morphology: HebrewMorphology) -> dict[str, list[tuple[str, str]]]:
    rows = dict(format_hebrew_morphology_rows_hu(morphology))
    return {
        "Alapadatok": _present_items(
            [
                ("Lemma", token.lemma),
                ("Transzliteráció", readable_hebrew_transliteration(token.surface, token.transliteration)),
                ("Strong/STEP", ", ".join(token.strong_ids)),
                ("Nyelv", LANGUAGE_LABELS.get(token.language, token.language)),
                ("Szófaj", rows.get("Szófaj") or morphology.part_of_speech),
            ]
        ),
        "Igei vagy névszói morfológia": _present_items(
            [
                ("Igetörzs", rows.get("Igetörzs")),
                ("Igealak", rows.get("Igealak")),
                ("Személy", rows.get("Személy")),
                ("Nem", rows.get("Nem")),
                ("Szám", rows.get("Szám")),
                ("Állapot", rows.get("Állapot")),
                ("Suffixum", rows.get("Suffixum")),
            ]
        ),
        "Különleges adatok": _present_items(
            [
                ("Ketív", token.ketiv),
                ("Qeré", token.qere),
                ("Kiadásjelölés", token.source_edition if token.source_edition not in {"", "L"} else ""),
                ("Maqaf", "igen" if token.maqaf else ""),
            ]
        ),
    }


def _present_items(items: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
    return [(label, value.strip()) for label, value in items if value and value.strip()]


def render_hebrew_analysis_card(
    selected_token: HebrewToken,
    view_model: dict[str, object],
    hu_lookup: object | None,
    tbesh_lookup: object,
    *,
    key_prefix: str = "hebrew_original",
    display_mode: str = "full",
) -> None:
    if display_mode == "compact":
        _render_compact_hebrew_analysis_card(
            selected_token, view_model, hu_lookup, tbesh_lookup, key_prefix=key_prefix
        )
        return
    st.markdown('<div class="textus-hebrew-analysis-card-marker"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        display_surface = str(view_model.get("display_surface") or selected_token.surface)
        st.markdown(
            f'<h3 class="textus-hebrew-token-title" dir="rtl" lang="{_token_lang(selected_token)}">'
            f"{html.escape(display_surface)}</h3>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="textus-hebrew-selected-word" dir="rtl" lang="{_token_lang(selected_token)}">'
            f"{html.escape(display_surface)}</div>",
            unsafe_allow_html=True,
        )
        _render_morphology_groups(view_model)
        _render_component_group(view_model)
        _render_special_group(view_model)
        with st.expander("Technikai morfológiai részletek", expanded=False):
            st.json(asdict(view_model["morphology"]))  # type: ignore[arg-type]
        render_lexical_panel(hu_lookup, tbesh_lookup, view_model)
        _render_concordance_jump_button(selected_token, key_prefix=key_prefix)


def _render_compact_hebrew_analysis_card(
    selected_token: HebrewToken,
    view_model: dict[str, object],
    hu_lookup: object | None,
    tbesh_lookup: object,
    *,
    key_prefix: str = "hebrew_original",
) -> None:
    display_surface = str(view_model.get("display_surface") or selected_token.surface)
    lemma = str(view_model.get("lemma") or "").strip()
    morphology = _compact_hebrew_morphology(view_model)
    gloss, note = _compact_hebrew_gloss_and_note(hu_lookup, tbesh_lookup, view_model)
    st.markdown('<div class="textus-hebrew-compact-card-marker"></div>', unsafe_allow_html=True)
    with st.container(border=True, key=f"{key_prefix}_compact_analysis"):
        heading = f"**{display_surface}**"
        if lemma:
            heading = f"{heading} — {lemma}"
        st.markdown(heading)
        if morphology:
            st.markdown(f"**Morfológia:** {morphology}")
        if gloss:
            st.markdown(f"**Alapjelentés:** {gloss}")
        if note:
            st.markdown(f"**Rövid magyarázat:** {note}")


def _compact_hebrew_morphology(view_model: dict[str, object]) -> str:
    groups = view_model.get("morphology_groups") or {}
    alap = dict(groups.get("Alapadatok") or []) if isinstance(groups, dict) else {}
    part_of_speech = str(alap.get("Szófaj") or "").strip()
    if part_of_speech:
        return part_of_speech
    return _core_part_of_speech_label(view_model)


def _compact_hebrew_gloss_and_note(
    hu_lookup: object | None,
    tbesh_lookup: object,
    view_model: dict[str, object],
) -> tuple[str, str]:
    hu_entry = getattr(hu_lookup, "entry", None) if hu_lookup is not None else None
    if hu_entry is not None:
        gloss = str(getattr(hu_entry, "base_meaning_hu", "") or "").strip()
        note = _display_lexical_note(hu_entry, view_model).strip()
        if note:
            note = _short_hebrew_note(note)
        return gloss, note
    fallback = getattr(hu_lookup, "tbesh_fallback", None) if hu_lookup is not None else None
    fallback = fallback or getattr(tbesh_lookup, "core", None)
    entry = getattr(fallback, "entry", None) if fallback else None
    if entry is not None:
        return str(getattr(entry, "gloss", "") or "").strip(), ""
    return "", ""


def _short_hebrew_note(text: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    truncated = compact[:limit].rstrip()
    last_sentence = max(truncated.rfind("."), truncated.rfind(";"), truncated.rfind(":"))
    if last_sentence >= 80:
        truncated = truncated[: last_sentence + 1]
    else:
        truncated = truncated.rstrip(" ,;:")
    return f"{truncated}..."


def _render_concordance_jump_button(selected_token: HebrewToken, *, key_prefix: str) -> None:
    query = selected_token.strong_ids[0] if selected_token.strong_ids else selected_token.lemma
    query = (query or "").strip()
    if not query:
        return
    try:
        from bible_engine.hebrew_token_repository import HebrewTokenRepository

        repo = HebrewTokenRepository()
        tokens = (
            repo.by_strong_id(query) if selected_token.strong_ids else repo.by_lemma(query)
        )
        count = len({t.stable_key for t in tokens})
    except Exception:  # noqa: BLE001 — a gomb hiánya nem akaszthatja meg a fő elemzést
        count = 0
    if count == 0:
        return
    from concordance_ui import request_original_language_search

    # A kulcs a `key_prefix`-et (ez a felület egyszerre TÖBB, párhuzamos
    # elrendezésben is renderelheti ugyanezt a panelt) ÉS a token
    # pozícióját is tartalmazza — ugyanaz a Strong-szám/lemma több helyen
    # is előfordulhat egy betöltött szakaszban, önmagában nem egyedi kulcs.
    if st.button(
        f"Konkordancia: mind a {count} előfordulás",
        key=(
            f"{key_prefix}_concordance_jump_{query}_{selected_token.book}_"
            f"{selected_token.chapter}_{selected_token.verse}_{selected_token.word_index}"
        ),
    ):
        request_original_language_search(query)
        st.rerun()


def render_lexical_panel(
    hu_lookup: object | None,
    tbesh_lookup: object,
    view_model: dict[str, object] | None = None,
) -> None:
    st.markdown("#### Lexikai adatok")
    hu_entry = getattr(hu_lookup, "entry", None) if hu_lookup is not None else None
    if hu_entry is not None:
        st.markdown("**Magyar lexikai jelentések**")
        st.markdown(f"**Alapjelentés:** {hu_entry.base_meaning_hu}")
        st.markdown(f"**Lehetséges jelentések:** {' · '.join(hu_entry.possible_meanings_hu)}")
        lexical_note = _display_lexical_note(hu_entry, view_model)
        if lexical_note:
            st.markdown(f"**Lexikai megjegyzés:** {lexical_note}")
        for warning in getattr(hu_lookup, "warnings", ()) or ():
            st.caption(warning)
        review_status = REVIEW_STATUS_LABELS.get(hu_entry.review_status, hu_entry.review_status)
        st.caption(f"Ellenőrzési állapot: {review_status}")
        st.caption("Forrás: STEP Bible TBESH alapján készült magyar lexikai munkaváltozat")
        return

    fallback = getattr(hu_lookup, "tbesh_fallback", None) if hu_lookup is not None else None
    fallback = fallback or getattr(tbesh_lookup, "core", None)
    if fallback and fallback.entry:
        entry = fallback.entry
        source_note = (
            f"{fallback.source_strong_id} -> {fallback.alias_target}"
            if fallback.via_alias
            else fallback.matched_strong_id
        )
        st.info(
            "Ehhez a Strong/STEP rekordhoz még nincs közvetlen magyar lexikai bejegyzés. "
            "Az angol TBESH szótári adat jelenik meg."
        )
        st.markdown(f"`{source_note}` · {entry.hebrew} · {entry.transliteration}")
        st.markdown(f"**Gloss:** {entry.gloss}")
        st.markdown(entry.meaning or "Nincs hosszabb TBESH megjegyzés.")
        return

    st.warning("Nincs lexikai adat ehhez a Strong/STEP azonosítóhoz.")


def _hebrew_analysis_bundle_cache(production_db_path: Path | None) -> CachedHebrewAnalysisService:
    """One Phase 2D.2 dataset-version-keyed bundle cache per (Streamlit
    session, production_db_path) — reused across every rerun/token-click,
    exactly like the existing ``_call_cache`` session-state pattern for AI
    text. Keyed by path so the dev demo harness's non-default database
    path (``render_hebrew_demo``) never shares a cache with the real app's
    default path."""
    registry: dict[str, CachedHebrewAnalysisService] = st.session_state.setdefault(
        "_hebrew_analysis_bundle_cache_registry", {}
    )
    key = str(production_db_path) if production_db_path is not None else "__default__"
    if key not in registry:
        service = HebrewAnalysisService(production_db_path=production_db_path)
        registry[key] = CachedHebrewAnalysisService(service)
    return registry[key]


def _hebrew_contextual_analysis_cache() -> HebrewContextualAnalysisCache:
    """The SEPARATE Phase 2E AI-result cache — deliberately not the same
    object as the deterministic bundle cache above (different versioning
    semantics; see bible_engine.hebrew_contextual_analysis_cache)."""
    return st.session_state.setdefault("_hebrew_contextual_analysis_cache", HebrewContextualAnalysisCache())


def render_hebrew_contextual_analysis_panel(
    selected_token: HebrewToken,
    reference: str,
    *,
    generate_text_fn: Callable[..., str] | None,
    key_prefix: str = "hebrew_original",
    production_db_path: Path | None = None,
    model_id: str = "gemini-2.5-flash",
    generate_kwargs: dict[str, object] | None = None,
) -> None:
    """Phase 2E — additive contextual-grammar/syntax interpretation for the
    SAME token the deterministic card above already shows, grounded on the
    ``HebrewAnalysisBundle`` (Phase 2C/2D/2D.1/2D.2), never on raw text.

    Purely additive: when ``generate_text_fn`` is ``None`` (every existing
    call site that does not pass it — demo harness, other embeddings),
    this renders nothing and every other section of the panel is byte-
    identical to before Phase 2E. On any failure (bundle unavailable, AI
    call fails, malformed response) this degrades to a small notice — the
    deterministic card above is never affected.
    """
    if generate_text_fn is None:
        return

    bundle_service = _hebrew_analysis_bundle_cache(production_db_path)
    try:
        bundle: HebrewAnalysisBundle = bundle_service.get_hebrew_analysis(reference)
    except HebrewAnalysisUnavailable:
        return

    verse: VerseAnalysis | None = next(
        (v for v in bundle.verses if v.chapter == selected_token.chapter and v.verse == selected_token.verse),
        None,
    )
    if verse is None:
        return

    st.markdown("#### Nyelvtani és mondattani elemzés (AI)")

    dataset_signature = bundle_service.dataset_version_signature()
    contextual_cache = _hebrew_contextual_analysis_cache()
    cached = contextual_cache.get(
        verse_id=verse.verse_id,
        dataset_version_signature=dataset_signature,
        prompt_version=CONTEXTUAL_ANALYSIS_PROMPT_VERSION,
        model_id=model_id,
    )

    button_key = f"{key_prefix}_contextual_analysis_run_{verse.verse_id}"
    if cached is None:
        st.caption(
            "Ehhez a vershez még nincs legenerálva kontextuális nyelvtani/"
            "mondattani elemzés."
        )
        if st.button("Kontextuális elemzés generálása", key=button_key):
            with st.spinner("Kontextuális nyelvtani elemzés készül..."):
                result = get_or_request_hebrew_contextual_analysis(
                    verse,
                    dataset_version_signature=dataset_signature,
                    model_id=model_id,
                    generate_fn=generate_text_fn,
                    cache=contextual_cache,
                    generate_kwargs=generate_kwargs,
                )
            if result.status != STATUS_OK:
                # Compact, non-blocking notice — never raises, the
                # deterministic morphology/lexicon card above (rendered
                # unconditionally, independent data path) stays usable
                # regardless of Gemini timeout/error/malformed-response.
                st.warning(
                    "A kontextuális elemzés jelenleg nem érhető el (időtúllépés "
                    "vagy hiba történt). A determinisztikus szó- és mondattani "
                    "adatok fent továbbra is elérhetők."
                )
                return
            st.rerun()
        return

    analysis: HebrewContextualAnalysis = cached.analysis  # type: ignore[assignment]
    token_analysis = next((t for t in verse.tokens if t.legacy_stable_key == selected_token.stable_key), None)
    shown_construction_ids = _render_hebrew_contextual_word_note(
        analysis, token_analysis.token_id if token_analysis else None
    )
    _render_hebrew_contextual_verse_sections(analysis, already_shown_construction_ids=shown_construction_ids)


def _render_hebrew_contextual_word_note(analysis: HebrewContextualAnalysis, token_id: str | None) -> frozenset[int]:
    """Word-level Phase 2E fields — kept compact (a handful of short markdown
    lines, never the full JSON/all word_notes), one selected token at a time.

    Returns the ``id()``s of any ``ConstructionNote`` objects rendered here
    (under "Kapcsolódó konstrukciók") so the verse-level section below can
    skip repeating the SAME construction immediately after — a UI display
    dedup only (production quality-review finding: "Több prefixumból álló
    szó" appeared twice in the same view). The underlying
    ``analysis.construction_notes`` data is never touched or dropped."""
    if token_id is None:
        return frozenset()
    note = next((n for n in analysis.word_notes if n.token_id == token_id), None)
    if note is None:
        return frozenset()
    if note.lexical_basic_meaning_hu:
        st.markdown(f"**Lexikai alapjelentés:** {note.lexical_basic_meaning_hu}")
    if note.contextual_meaning_hu:
        st.markdown(f"**Kontextuális jelentés:** {note.contextual_meaning_hu}")
    if note.grammar_explanation_hu:
        st.markdown(f"**Nyelvtani magyarázat:** {note.grammar_explanation_hu}")
    if note.syntax_explanation_hu:
        st.markdown(f"**Mondattani szerep:** {note.syntax_explanation_hu}")
    if note.translation_note_hu:
        st.caption(f"Fordítási megjegyzés: {note.translation_note_hu}")

    related_constructions = [c for c in analysis.construction_notes if token_id in c.token_ids]
    if related_constructions:
        st.markdown("**Kapcsolódó konstrukciók:**")
        for construction in related_constructions:
            st.markdown(f"- **{construction.title_hu}** — {construction.explanation_hu}")
    return frozenset(id(c) for c in related_constructions)


def _render_hebrew_contextual_verse_sections(
    analysis: HebrewContextualAnalysis, *, already_shown_construction_ids: frozenset[int] = frozenset()
) -> None:
    """Verse-level Phase 2E fields — compact expandable sections below the
    word-level note, shared by every word click within the same verse.

    ``already_shown_construction_ids`` (from ``_render_hebrew_contextual_
    word_note``) skips constructions already rendered for the selected
    word above — display-only dedup, never mutates ``analysis`` and never
    drops a genuinely distinct construction (a construction not covering
    the selected token, or the selected token's construction when a
    DIFFERENT word is selected, still appears here as before)."""
    remaining_constructions = [
        c for c in analysis.construction_notes if id(c) not in already_shown_construction_ids
    ]
    if remaining_constructions:
        with st.expander("Mondattani összefoglalás — kapcsolódó konstrukciók", expanded=False):
            for construction in remaining_constructions:
                st.markdown(f"**{construction.title_hu}**")
                st.markdown(construction.explanation_hu)
                if construction.translation_significance_hu:
                    st.caption(construction.translation_significance_hu)

    if analysis.syntax_summary.summary_hu:
        with st.expander("Mondattani összefoglalás", expanded=False):
            st.markdown(analysis.syntax_summary.summary_hu)

    if analysis.translation_notes:
        with st.expander("Fordítási megjegyzések", expanded=False):
            for note in analysis.translation_notes:
                st.markdown(f"- {note}")

    if analysis.exegetical_notes:
        with st.expander("Exegetikai megjegyzések", expanded=False):
            for note in analysis.exegetical_notes:
                st.markdown(f"- {note}")

    if analysis.warnings:
        with st.expander("Figyelmeztetések", expanded=False):
            for warning in analysis.warnings:
                st.markdown(f"- {warning}")

    if analysis.grounding_status == "PARTIALLY_GROUNDED_SYNTAX":
        st.caption(
            "A mondat szerkezetének egy része ezen a helyen nem kapcsolható "
            "teljes biztonsággal a szöveg szavaihoz."
        )


def _render_morphology_groups(view_model: dict[str, object]) -> None:
    groups = view_model.get("morphology_groups") or {}
    if not isinstance(groups, dict):
        return
    left, right = st.columns(2, gap="small")
    left.markdown(_field_group_markup("Alapadatok", groups.get("Alapadatok", [])), unsafe_allow_html=True)
    right.markdown(
        _field_group_markup(
            "Igei vagy névszói morfológia",
            groups.get("Igei vagy névszói morfológia", []),
        ),
        unsafe_allow_html=True,
    )


def _render_component_group(view_model: dict[str, object]) -> None:
    components = list(view_model.get("components") or [])
    if not components:
        return
    has_affix = any(component.get("role") in {"prefix", "suffix"} for component in components)
    rows = [
        (
            str(component.get("role_label") or component.get("role") or ""),
            _component_value(component),
        )
        for component in components
    ]
    if has_affix and not any(component.get("role") == "suffix" for component in components):
        rows.append(("suffixum", "nincs"))
    st.markdown(_field_group_markup("Szóösszetétel", rows), unsafe_allow_html=True)


def _render_special_group(view_model: dict[str, object]) -> None:
    groups = view_model.get("morphology_groups") or {}
    rows = groups.get("Különleges adatok", []) if isinstance(groups, dict) else []
    if rows:
        st.markdown(_field_group_markup("Különleges adatok", rows), unsafe_allow_html=True)


def _component_value(component: dict[str, object]) -> str:
    surface = str(component.get("display_surface") or component.get("surface") or "nincs felszíni alak")
    strong = str(component.get("strong_id") or "nincs adat")
    summary = str(component.get("analysis_summary") or "")
    if component.get("role") == "prefix" and summary:
        surface = f"{surface}־"
    if summary:
        return f"{surface} — {summary} · Strong/STEP: {strong}"
    return f"{surface} · Strong/STEP: {strong}"


def _display_lexical_note(hu_entry: object, view_model: dict[str, object] | None = None) -> str:
    note = str(getattr(hu_entry, "lexical_note_hu", "") or "")
    if view_model is None:
        return note
    language_label = str(view_model.get("language_label") or "").strip()
    part_of_speech = _core_part_of_speech_label(view_model)
    if language_label and part_of_speech:
        prefix = f"{language_label.capitalize()} {part_of_speech}."
        expected_language = language_label.capitalize()
        if note.startswith(f"{expected_language} "):
            return note
        if note.startswith(("Héber ", "Arámi ")):
            return (
                f"{prefix} A felsorolt jelentések közül a szövegkörnyezet alapján "
                "választandó ki a megfelelő árnyalat."
            )
    return note


def _core_part_of_speech_label(view_model: dict[str, object]) -> str:
    components = list(view_model.get("components") or [])
    core = next((component for component in components if component.get("role") == "core"), None)
    analysis = core.get("analysis") if isinstance(core, dict) else None
    part_of_speech = ""
    if isinstance(analysis, dict):
        part_of_speech = str(analysis.get("part_of_speech") or "")
    return {
        "Noun": "főnév",
        "Verb": "ige",
        "Adjective": "melléknév",
        "Adverb": "határozószó",
        "Pronoun": "névmás",
        "Preposition": "elöljárószó",
        "Conjunction": "kötőszó",
        "Article": "névelő",
        "Particle": "partikula",
    }.get(part_of_speech, part_of_speech.lower())


def _field_group_markup(title: str, rows: list[tuple[str, str]]) -> str:
    body = "\n".join(
        '<div class="textus-hebrew-field">'
        f"<strong>{html.escape(label)}:</strong> {html.escape(value)}"
        "</div>"
        for label, value in rows
        if value
    )
    if not body:
        body = '<div class="textus-hebrew-field textus-hebrew-muted">nincs megjeleníthető adat</div>'
    return (
        '<div class="textus-hebrew-field-list">'
        f'<div class="textus-hebrew-field-group-title">{html.escape(title)}</div>'
        f"{body}</div>"
    )


def _token_lang(token: HebrewToken) -> str:
    return "arc" if token.language == "aramaic" else "he"


def _selected_token_key(tokens: list[HebrewToken], current: object) -> str:
    valid_keys = {token.stable_key for token in tokens}
    if current is not None and str(current) in valid_keys:
        return str(current)
    return tokens[0].stable_key


def _fallback_label(tokens: list[HebrewToken], selection_key: str) -> str:
    token = next((item for item in tokens if item.stable_key == selection_key), tokens[0])
    strong = token.core_component.strong_id if token.core_component else ", ".join(token.strong_ids)
    return f"{token.chapter},{token.verse} / {token.word_index}. {token.surface} · {strong or 'nincs Strong'}"


def _reference_label(book: str, chapter: int, start: int, end: int) -> str:
    if start == end:
        return f"{book} {chapter},{start}"
    return f"{book} {chapter},{start}-{end}"


def parse_hebrew_original_reference(reference: str) -> tuple[str, int, int, int]:
    return parse_hebrew_reference(reference)


def render_hebrew_original_language_panel(
    book: str,
    chapter: int,
    verse_start: int,
    verse_end: int | None = None,
    *,
    key_prefix: str = "hebrew_original",
    database_path: Path = DEFAULT_TAHOT_DATABASE_PATH,
    reference_label: str | None = None,
    display_mode: str = "full",
    generate_text_fn: Callable[..., str] | None = None,
    contextual_analysis_model_id: str = "gemini-2.5-flash",
    contextual_analysis_generate_kwargs: dict[str, object] | None = None,
) -> None:
    _ensure_hebrew_analysis_styles()

    token_repository = HebrewTokenRepository(database_path)
    diagnostics = token_repository.diagnostics()
    if not diagnostics.exists:
        st.warning("A h\u00e9ber-ar\u00e1mi eredeti sz\u00f6veg adatb\u00e1zisa m\u00e9g nincs el\u0151k\u00e9sz\u00edtve.")
        st.code(str(database_path))
        return
    if diagnostics.integrity_check != "ok" or not diagnostics.required_tables_present:
        st.error("A h\u00e9ber-ar\u00e1mi adatb\u00e1zis l\u00e9tezik, de nem \u00e9rv\u00e9nyes vagy nem teljes.")
        st.json(diagnostics.__dict__)
        return

    end = verse_end or verse_start
    result = token_repository.passage(book, chapter, verse_start, end)
    if result.status != "ok":
        st.warning("A kért ószövetségi szakasz nem található a helyi TAHOT adatbázisban.")
        with st.expander("Fejlesztői részletek", expanded=False):
            st.code(f"{book} {chapter},{verse_start}-{end}: {result.status}")
        return
    tokens = list(result.tokens)
    if not tokens:
        return

    selected_state_key = f"{key_prefix}_selected_key"
    reference_state_key = f"{key_prefix}_reference_key"
    fallback_key = f"{key_prefix}_fallback_selector"
    reference_key = f"{book}:{chapter}:{verse_start}:{end}:{len(tokens)}"
    if st.session_state.get(reference_state_key) != reference_key:
        st.session_state[selected_state_key] = tokens[0].stable_key
        st.session_state[reference_state_key] = reference_key

    current_key = _selected_token_key(tokens, st.session_state.get(selected_state_key))
    st.session_state[selected_state_key] = current_key

    resolved_reference = reference_label or _reference_label(book, chapter, verse_start, end)
    st.markdown(
        '<h3 class="textus-hebrew-analysis-title">H\u00e9ber-ar\u00e1mi eredeti sz\u00f6veg</h3>',
        unsafe_allow_html=True,
    )
    helper = "V\u00e1lasszon egy h\u00e9ber vagy ar\u00e1mi sz\u00f3t"
    if display_mode == "compact" and resolved_reference:
        helper = f"{helper} \u00b7 {resolved_reference}"
    st.markdown(
        f'<div class="textus-hebrew-analysis-label">{html.escape(helper)}</div>',
        unsafe_allow_html=True,
    )
    if display_mode != "compact":
        st.caption(resolved_reference)
    selected = hebrew_token_selector(
        tokens,
        current_key,
        key=f"{key_prefix}_inline_token_selector",
    )
    selected_key = _selected_token_key(tokens, selected or current_key)
    if selected_key != current_key:
        st.session_state[selected_state_key] = selected_key
        st.rerun()
    selected_token = next((token for token in tokens if token.stable_key == selected_key), tokens[0])
    st.session_state[fallback_key] = selected_token.stable_key

    def sync_fallback_selection() -> None:
        st.session_state[selected_state_key] = _selected_token_key(
            tokens,
            st.session_state.get(fallback_key),
        )

    if display_mode == "compact":
        st.markdown(
            '<div class="textus-hebrew-compact-fallback-marker"></div>',
            unsafe_allow_html=True,
        )
        st.selectbox(
            "Token",
            [token.stable_key for token in tokens],
            index=[token.stable_key for token in tokens].index(selected_token.stable_key),
            key=fallback_key,
            format_func=lambda key: _fallback_label(tokens, key),
            on_change=sync_fallback_selection,
            label_visibility="collapsed",
        )
    else:
        st.markdown('<div class="textus-hebrew-fallback-marker"></div>', unsafe_allow_html=True)
        with st.expander("Alternat\u00edv sz\u00f3v\u00e1laszt\u00e1s", expanded=False):
            st.selectbox(
                "Token",
                [token.stable_key for token in tokens],
                index=[token.stable_key for token in tokens].index(selected_token.stable_key),
                key=fallback_key,
                format_func=lambda key: _fallback_label(tokens, key),
                on_change=sync_fallback_selection,
            )

    lexicon = HebrewLexiconRepository(DEFAULT_TBESH_DATABASE_PATH)
    hungarian_lexicon = HebrewHungarianLexiconRepository(tbesh_database_path=DEFAULT_TBESH_DATABASE_PATH)
    expansions = load_tehmc_expansions(TEHMC_SOURCE) if TEHMC_SOURCE.exists() else {}
    morphology = token_repository.morphology(selected_token, expansions)
    lookup = lexicon.lookup_token(selected_token)
    hu_lookup = (
        hungarian_lexicon.lookup(
            selected_token.core_component.strong_id,
            expected_lemma=selected_token.lemma,
        )
        if selected_token.core_component
        else None
    )
    view_model = build_hebrew_token_view_model(selected_token, morphology, lookup)
    render_hebrew_analysis_card(
        selected_token,
        view_model,
        hu_lookup,
        lookup,
        key_prefix=key_prefix,
        display_mode=display_mode,
    )
    if display_mode != "compact":
        st.caption("Forr\u00e1s \u00e9s licenc: STEP Bible / STEPBible-Data, CC BY 4.0, www.STEPBible.org.")
        render_hebrew_contextual_analysis_panel(
            selected_token,
            _reference_label(book, chapter, verse_start, end),
            generate_text_fn=generate_text_fn,
            key_prefix=key_prefix,
            production_db_path=database_path,
            model_id=contextual_analysis_model_id,
            generate_kwargs=contextual_analysis_generate_kwargs,
        )


@_traced_stage("hebrew_original_language_reference")
def render_hebrew_original_language_reference(
    reference: str,
    *,
    key_prefix: str = "hebrew_original",
    database_path: Path = DEFAULT_TAHOT_DATABASE_PATH,
    display_mode: str = "full",
    generate_text_fn: Callable[..., str] | None = None,
    contextual_analysis_model_id: str = "gemini-2.5-flash",
    contextual_analysis_generate_kwargs: dict[str, object] | None = None,
) -> None:
    book, chapter, verse_start, verse_end = parse_hebrew_original_reference(reference)
    render_hebrew_original_language_panel(
        book,
        chapter,
        verse_start,
        verse_end,
        key_prefix=key_prefix,
        database_path=database_path,
        reference_label=reference,
        display_mode=display_mode,
        generate_text_fn=generate_text_fn,
        contextual_analysis_model_id=contextual_analysis_model_id,
        contextual_analysis_generate_kwargs=contextual_analysis_generate_kwargs,
    )


def _ensure_hebrew_analysis_styles() -> None:
    st.markdown(
        """
        <style>
        .textus-hebrew-analysis-title {
            margin: 0;
            font-size: 0.98rem;
            line-height: 1.15;
            font-weight: 700;
        }
        .textus-hebrew-analysis-label {
            margin: 0;
            font-size: 0.86rem;
            font-weight: 600;
            line-height: 1.25;
        }
        .hebrew-token-selector {
            margin: 0 0 0.06rem;
            line-height: 1.32;
        }
        .textus-hebrew-fallback-marker,
        .textus-hebrew-compact-fallback-marker,
        .textus-hebrew-analysis-card-marker,
        .textus-hebrew-compact-card-marker {
            display: none !important;
            height: 0 !important;
            overflow: hidden !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
            list-style: none !important;
        }
        .element-container:has(.textus-hebrew-compact-card-marker) {
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }
        .element-container:has(.textus-hebrew-compact-card-marker) + .element-container {
            margin-top: 0.12rem !important;
            margin-bottom: 0 !important;
        }
        .element-container:has(.textus-hebrew-compact-card-marker) + .element-container [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.26rem 0.42rem 0.28rem !important;
        }
        .element-container:has(.textus-hebrew-compact-card-marker) + .element-container [data-testid="stVerticalBlock"] {
            gap: 0.2rem !important;
        }
        .element-container:has(.textus-hebrew-compact-card-marker) + .element-container [data-testid="stMarkdownContainer"] p {
            margin-bottom: 0.06rem !important;
            line-height: 1.32 !important;
        }
        .element-container:has(.textus-hebrew-compact-fallback-marker),
        .element-container:has(.textus-hebrew-compact-fallback-marker) + .element-container {
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
            visibility: hidden !important;
            pointer-events: none !important;
        }
        .element-container:has(.textus-hebrew-fallback-marker) {
            margin: 0 !important;
            padding: 0 !important;
        }
        .element-container:has(.textus-hebrew-fallback-marker) + .element-container summary {
            padding-top: 0.04rem !important;
            padding-bottom: 0.04rem !important;
            min-height: 0 !important;
            line-height: 1.08 !important;
            font-size: 0.84rem !important;
        }
        .textus-hebrew-selected-word {
            font-family: "SBL Hebrew", "Ezra SIL", "Noto Sans Hebrew", serif;
            font-size: 1.65rem;
            line-height: 1.5;
            word-break: keep-all;
            overflow-wrap: normal;
        }
        .textus-hebrew-token-title {
            margin: 0 0 0.18rem;
            font-family: "SBL Hebrew", "Ezra SIL", "Noto Sans Hebrew", serif;
            font-size: 1.35rem;
            line-height: 1.35;
            font-weight: 700;
            word-break: keep-all;
            overflow-wrap: normal;
        }
        .textus-hebrew-field-list {
            margin: 0 0 0.12rem !important;
            line-height: 1.18 !important;
        }
        .textus-hebrew-field-group-title {
            margin: 0.06rem 0 0.03rem;
            font-weight: 700;
            font-size: 0.9rem;
        }
        .textus-hebrew-field {
            margin: 0 0 0.025rem !important;
            line-height: 1.18 !important;
            font-size: 0.9rem !important;
        }
        .textus-hebrew-muted {
            color: #7a6c5c;
        }
        @media (max-width: 640px) {
            .textus-hebrew-selected-word {
                font-size: 1.45rem;
            }
            .textus-hebrew-field {
                font-size: 0.88rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hebrew_demo(database_path: Path = DEFAULT_TAHOT_DATABASE_PATH) -> None:
    st.title("H\u00e9ber \u00d3sz\u00f6vets\u00e9g protot\u00edpus")
    st.caption("Fejleszt\u0151i TAHOT/TBESH protot\u00edpus. Forr\u00e1s: STEP Bible, CC BY 4.0.")

    label = st.selectbox("Szakasz", tuple(PASSAGES))
    book, chapter, start, end = PASSAGES[label]
    render_hebrew_original_language_panel(
        book,
        chapter,
        start,
        end,
        key_prefix="hebrew_demo",
        database_path=database_path,
    )


if __name__ == "__main__":
    render_hebrew_demo()
