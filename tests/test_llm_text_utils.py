"""llm_text_utils — azonosság- és jellemzőtesztek (4. munkafázis, 1. lépés, 2026-11-23).

A három ``_ORIG_*`` függvény a 4fbdb83 commit szerinti eredeti másolatok szó
szerinti példánya (mintaként, „oracle”). A tesztek igazolják, hogy:
1. az új közös függvények minden bemenetre ugyanazt adják (vagy ugyanazt a
   kivételt dobják), mint az eredetiek;
2. minden érintett modul a régi néven ugyanazt a viselkedést kapja;
3. a „Hiba…” kezdetű válaszok kezelése változatlan (jellemzőteszt — a
   jelenlegi, tudatosan meghagyott viselkedést rögzíti; a „Hibás…”/„Hibák…”
   kezdetű szöveget az „á” betű miatt egyik szabály sem jelzi).
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest

import llm_text_utils as u

ROOT = Path(__file__).resolve().parents[1]


# ---- Eredeti implementációk, szó szerint (pl. sermon_workshop_m5_ai.py:238,
# ---- commentary_compare.py:201, sermon_workshop_arc_ai.py:388 @ 4fbdb83) ----


def _ORIG_is_api_error_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return t.startswith(("⚠️", "⏳", "Hiba", "❌"))


def _ORIG_looks_like_provider_failure(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    return raw.startswith(("⚠️", "⏳"))


def _ORIG_looks_like_api_error(raw: Any) -> bool:
    text = str(raw or "")
    return text.startswith("⚠️") or text.startswith("⏳")


# ---- Bemeneti tábla -------------------------------------------------------

INPUTS: list[Any] = [
    None, "", " ", "\n\t ", "0",
    "⚠️ **Hiányzó API kulcs.**", "⚠️", "  ⚠️ vezető szóközzel", "\n⚠️ sortöréssel",
    "⚠", "⚠ variációs jel nélkül", "⏳ **Kérlek várj**", " ⏳",
    "Hiba", "Hiba történt", "Hibaforrás: a 3. pont", "Hibalista a vázlathoz",
    "Hibás a vázlat második pontja.", "Hibák a vázlatban: 1) …",
    "  Hibás vezető szóközzel", "hiba kisbetűvel", "HIBA nagybetűvel",
    "❌ elutasítva", " ❌", "✅ rendben",
    "I. Bevezetés\n\nA textus…", '{"ok": true}', "```json\n{}\n```",
    "Szöveg ⚠️ a közepén", "__OUTLINE_TRUNCATED__",
    "> ⚠️ **A válasz a modell kimeneti korlátjánál megszakadt.**",
]
NON_STR_INPUTS: list[Any] = [0, 5, [], {}, {"a": 1}, ["⚠️"], 3.5, False, True]


def _outcome(fn, value):
    try:
        return ("ok", fn(value))
    except Exception as exc:  # noqa: BLE001 — a kivétel típusa is a viselkedés része
        return ("exc", type(exc).__name__)


PAIRS = [
    (u.is_llm_error_text, _ORIG_is_api_error_text),
    (u.is_provider_failure_text, _ORIG_looks_like_provider_failure),
    (u.starts_with_provider_warning, _ORIG_looks_like_api_error),
]


@pytest.mark.parametrize(("new", "orig"), PAIRS, ids=[p[0].__name__ for p in PAIRS])
@pytest.mark.parametrize("value", INPUTS + NON_STR_INPUTS, ids=repr)
def test_new_function_matches_original_exactly(new, orig, value) -> None:
    assert _outcome(new, value) == _outcome(orig, value)


# ---- Minden érintett modul a régi néven ugyanazt kapja ---------------------

FOUR_PREFIX_MODULES = [
    "sermon_workshop_m5_ai", "sermon_workshop_m4_ai", "sermon_workshop_entry_point_ai",
    "sermon_workshop_engagement_ai", "textus_summary_ai", "textus_main_idea_ai",
    "writing_desk_chat", "writing_desk_extracts",
]
PROVIDER_FAILURE_MODULES = [
    "commentary_compare", "commentary_translation_service",
    "bible_engine.original_language_analysis",
    "bible_engine.greek_contextual_analysis_service",
    "bible_engine.hebrew_contextual_analysis_service",
]
API_ERROR_MODULES = [
    "sermon_workshop_arc_ai", "sermon_workshop_blueprint_ai",
    "sermon_workshop_developed_outline_ai", "sermon_workshop_refinement_ai",
]
GROUPS = (
    [(m, "_is_api_error_text", _ORIG_is_api_error_text, u.is_llm_error_text) for m in FOUR_PREFIX_MODULES]
    + [(m, "_looks_like_provider_failure", _ORIG_looks_like_provider_failure, u.is_provider_failure_text) for m in PROVIDER_FAILURE_MODULES]
    + [(m, "_looks_like_api_error", _ORIG_looks_like_api_error, u.starts_with_provider_warning) for m in API_ERROR_MODULES]
)


@pytest.mark.parametrize(("module", "name", "orig", "shared"), GROUPS, ids=[f"{g[0]}.{g[1]}" for g in GROUPS])
def test_module_keeps_identical_behaviour_under_old_name(module, name, orig, shared) -> None:
    fn = getattr(importlib.import_module(module), name)
    for value in INPUTS + NON_STR_INPUTS:
        assert _outcome(fn, value) == _outcome(orig, value), (module, value)


@pytest.mark.parametrize(("module", "name", "orig", "shared"), GROUPS, ids=[f"{g[0]}.{g[1]}" for g in GROUPS])
def test_module_uses_the_shared_function(module, name, orig, shared) -> None:
    assert getattr(importlib.import_module(module), name) is shared


def test_m5_compatibility_alias_for_importers() -> None:
    """14 modul a sermon_workshop_m5_ai-ból importálja; az alias maradjon meg."""
    from sermon_workshop_m5_ai import _is_api_error_text

    assert _is_api_error_text is u.is_llm_error_text


def test_no_private_copies_left() -> None:
    names = {"_is_api_error_text", "_looks_like_provider_failure", "_looks_like_api_error"}
    covered = {m.replace(".", "/") + ".py" for m in FOUR_PREFIX_MODULES + PROVIDER_FAILURE_MODULES + API_ERROR_MODULES}
    leftovers = []
    for rel in sorted(covered):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        leftovers += [f"{rel}:{n.name}" for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert leftovers == []


# ---- Jellemzőtesztek: a „Hiba…” kezdetű válaszok jelenlegi kezelése ---------


@pytest.mark.parametrize(
    "text",
    ["Hiba", "Hiba történt", "Hibaforrás: a 3. pont", "Hibalista a vázlathoz", "  Hiba vezető szóközzel"],
)
def test_characterization_four_prefix_rule_flags_hiba_prefixed_text(text) -> None:
    """JELENLEGI viselkedés, tudatosan változatlanul hagyva: a négyelőtagos
    szabály minden „Hiba” betűsorral kezdődő választ hibának tekint — egy
    érvényes, „Hibaforrás…” vagy „Hibalista…” kezdetű modellválaszt is."""
    assert u.is_llm_error_text(text) is True


@pytest.mark.parametrize("text", ["Hibás a vázlat második pontja.", "Hibák a vázlatban: 1) …", "  Hibás vezető szóközzel"])
def test_characterization_hibas_and_hibak_are_not_flagged(text) -> None:
    """A „Hibás”/„Hibák” szó negyedik betűje „á”, nem „a”, ezért NEM
    kezdődik a „Hiba” előtaggal — egyik szabály sem jelzi hibának."""
    assert u.is_llm_error_text(text) is False
    assert u.is_provider_failure_text(text) is False
    assert u.starts_with_provider_warning(text) is False


@pytest.mark.parametrize("text", ["hiba kisbetűvel", "HIBA nagybetűvel"])
def test_characterization_hiba_match_is_case_sensitive(text) -> None:
    assert u.is_llm_error_text(text) is False


def test_characterization_empty_and_whitespace_differ_between_rules() -> None:
    for value in (None, "", "  "):
        assert u.is_llm_error_text(value) is True
        assert u.is_provider_failure_text(value) is True
        assert u.starts_with_provider_warning(value) is False
    assert u.is_provider_failure_text("  ⚠️ x") is True
    assert u.starts_with_provider_warning("  ⚠️ x") is False
