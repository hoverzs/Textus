"""Közös szöveges hibafelismerés a generate_fn (app.generate_text) válaszaihoz.

A ``generate_text`` szolgáltatói hiba esetén nem kivételt dob, hanem egy
figyelmeztető szöveget ad vissza (mindig ``⚠️`` vagy ``⏳`` előtaggal). Az
MI-modulok ezt szöveges előtag-vizsgálattal ismerik fel. 2026-11-23-ig ugyanez
a logika 17 helyen, három egymástól eltérő változatban volt bemásolva; ez a
modul a bizonyítottan azonos másolatokat vonja össze — VISELKEDÉSVÁLTOZÁS
NÉLKÜL. A három szabály szándékosan külön függvény marad, mert eltérően
kezelik az üres választ, a vezető szóközt és a nem szöveges bemenetet.

Ismert, tudatosan meghagyott viselkedés (jellemzőtesztekkel rögzítve,
tests/test_llm_text_utils.py): az ``is_llm_error_text`` a ``Hiba`` előtag
miatt minden „Hiba” betűsorral kezdődő választ hibának tekint, egy érvényes
„Hibaforrás…” vagy „Hibalista…” kezdetű modellválaszt is. (A „Hibás…” és
„Hibák…” szöveget az „á” betű miatt nem.) A ``generate_text`` ilyen előtagot
nem ad; a szabály esetleges szűkítése külön, bizonyítékon alapuló döntés.
"""

from __future__ import annotations

from typing import Any

# A négyelőtagos szabály előtagjai (korábban 8 modulban bemásolva,
# 14 további modul a sermon_workshop_m5_ai-ból importálta).
LLM_ERROR_PREFIXES: tuple[str, ...] = ("⚠️", "⏳", "Hiba", "❌")

# A generate_text tényleges hibaelőtagjai (kételőtagos szabályok).
PROVIDER_FAILURE_PREFIXES: tuple[str, ...] = ("⚠️", "⏳")


def is_llm_error_text(text: str) -> bool:
    """Négyelőtagos szabály: üres vagy csak szóköz → hiba; különben
    a szóközmentesített szöveg ``⚠️``/``⏳``/``Hiba``/``❌`` előtagja.

    Szó szerint a korábbi ``_is_api_error_text`` másolatok viselkedése
    (sermon_workshop_m5_ai, _m4_ai, _entry_point_ai, _engagement_ai,
    textus_summary_ai, textus_main_idea_ai, writing_desk_chat,
    writing_desk_extracts)."""
    t = (text or "").strip()
    if not t:
        return True
    return t.startswith(LLM_ERROR_PREFIXES)


def is_provider_failure_text(text: str) -> bool:
    """Kételőtagos, szóközmentesítő szabály: üres vagy csak szóköz → hiba;
    különben a szóközmentesített szöveg ``⚠️``/``⏳`` előtagja.

    Szó szerint a korábbi ``_looks_like_provider_failure`` másolatok
    viselkedése (commentary_compare, commentary_translation_service,
    bible_engine.original_language_analysis, bible_engine.greek_ és
    hebrew_contextual_analysis_service)."""
    raw = (text or "").strip()
    if not raw:
        return True
    return raw.startswith(PROVIDER_FAILURE_PREFIXES)


def starts_with_provider_warning(raw: Any) -> bool:
    """Kételőtagos, NEM szóközmentesítő szabály: ``str(raw or "")``
    ``⚠️``/``⏳`` előtagja. Üres bemenet → NEM hiba; vezető szóköz esetén
    nem talál; nem szöveges bemenetet is elfogad.

    Szó szerint a korábbi ``_looks_like_api_error`` másolatok viselkedése
    (sermon_workshop_arc_ai, _blueprint_ai, _developed_outline_ai,
    _refinement_ai)."""
    text = str(raw or "")
    return text.startswith("⚠️") or text.startswith("⏳")
