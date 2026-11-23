"""Közös szöveges hibafelismerés és JSON-kinyerés a generate_fn
(app.generate_text) válaszaihoz.

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

JSON-kinyerés (2026-11-23, 4. fázis 2. lépés): két, egymástól eltérő, de
csoporton belül bizonyítottan azonos változat. A kettő ott tér el, ahol a
teljes szöveg érvényes, de NEM objektum gyökerű JSON (pl. lista):

* ``extract_json_object_lenient`` ilyenkor továbbmegy, és az első ``{`` és
  az utolsó ``}`` közötti részt próbálja objektumként értelmezni — egy
  ``[{"a": 1}]`` válaszból tehát ``{"a": 1}`` lesz, ``[{"a":1},{"b":2}]``
  esetén viszont ``None``;
* ``extract_json_object_strict_root`` ilyenkor azonnal ``None``-t ad.

A két változat a bemenet ellenőrzésében is eltér (``not raw`` kontra
``raw is None``), ami nem szöveges bemenetnél számít. Mindkettő tűri a
markdown kódkerítést és a záró vesszőt. Egyik sem dob kivételt
szövegbemenetre. A fejlesztett vázlat (sermon_workshop_developed_outline_ai)
saját kinyerője ETTŐL ELTÉR (nem javítja a záró vesszőt), ezért nem ide
tartozik.
"""

from __future__ import annotations

import json
import re
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


def extract_json_object_lenient(raw: Any) -> dict[str, Any] | None:
    """Engedékeny JSON-objektum-kinyerés: markdown kódkerítés eltávolítása,
    közvetlen ``json.loads``; ha az nem ad objektumot (hibás JSON VAGY nem
    objektum gyökerű, pl. lista), az első ``{`` és az utolsó ``}`` közötti
    részt próbálja, eredetiben és záró vesszőktől megtisztítva.

    Szó szerint a korábbi ``extract_json_object`` másolatok viselkedése
    (textus_summary_ai, sermon_workshop_entry_point_ai, sermon_workshop_m4_ai,
    textus_main_idea_ai, sermon_workshop_engagement_ai)."""
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


def extract_json_object_strict_root(raw: Any) -> dict[str, Any] | None:
    """Szigorú gyökerű JSON-objektum-kinyerés: mint az engedékeny változat,
    de ha a (kódkerítés nélküli) teljes szöveg érvényes JSON, csak objektum
    gyökér esetén ad eredményt — lista vagy más gyökérnél azonnal ``None``,
    nem keres benne objektumot.

    Szó szerint a korábbi ``_extract_json_object`` másolatok viselkedése
    (sermon_workshop_arc_ai, sermon_workshop_blueprint_ai)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
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
