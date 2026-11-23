"""Textus 2.0 Igehirdetési műhely — AI-tól független adatstruktúra.

Csak a `sermon_workshop` session/project adatot kezeli. Nem hív Geminit,
Supabase-t, és nem renderel Streamlit-widgetet. A `text_workshop` és a
meglévő elemzési kulcsokhoz nem nyúl.
"""

from __future__ import annotations

import copy
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Mapping, MutableMapping

_LOG = logging.getLogger(__name__)


def _log_swallowed_exception(context: str, exc: BaseException) -> None:
    """Technikai napló egy szándékosan elnyelt kivételről (2026-11-23).

    A hívó fallback-viselkedése változatlan; ez csak láthatóvá teszi, hogy a
    fallback ág futott. Adatvédelmi okból KIZÁRÓLAG a kivétel típusát és a
    keletkezés helyét (fájlnév:sor, függvénynév) naplózza — a kivétel
    üzenetét és a tracebacket nem, mert azokban vázlat- vagy prédikációszöveg,
    illetve más felhasználói adat is lehet. A naplózás maga sosem dobhat.
    """
    try:
        tb = exc.__traceback__
        last = None
        while tb is not None:
            last, tb = tb, tb.tb_next
        where = ""
        if last is not None:
            code = last.tb_frame.f_code
            where = f" at {os.path.basename(code.co_filename)}:{last.tb_lineno} in {code.co_name}"
        _LOG.warning(
            "sermon_workshop_data fallback used (%s): %s%s",
            context,
            type(exc).__name__,
            where,
        )
    except Exception:  # noqa: BLE001 — a naplózás nem befolyásolhatja a működést
        pass


SERMON_WORKSHOP_KEY = "sermon_workshop"

_SECTION_DICT_KEYS = (
    "human_condition",
    "listener_tension",
    "christ_centered_arc",
    "sermon_path",
    "entry_point",
    "closing",
    "diagnostics",
    "lection",
    "prayer_preparation",
)

_SECTION_LIST_KEYS = (
    "sermon_movements",
    "selected_images",
    "illustrations",
    "applications",
    "approved_sermon_decisions",
    "illustration_suggestions",
    "actualization_suggestions",
    "retained_illustration_cards",
    "actualization_connections",
    "engagement_elements",
)

_SECTION_STR_KEYS = (
    "illustration_user_direction",
    "actualization_user_direction",
    "illustration_suggest_note",
    "actualization_suggest_note",
)


def get_default_sermon_workshop() -> dict[str, Any]:
    """Üres Igehirdetési műhely-adat (új session / régi projekt hiányzó mező)."""
    return {
        "sermon_main_idea": "",
        "sermon_main_idea_status": "draft",
        "sermon_main_idea_approved_context_hash": "",
        # ÚJ, additív mező (célarchitektúra-terv, 1. fázis, 2026-08-13).
        # Egységesített hétpontos "Az igehirdetés íve" modell. Ebben a
        # fázisban KIZÁRÓLAG adatmodell — nem aktív source of truth, a UI
        # nem írja, a vázlatmotor nem olvassa. A régi `entry_point` /
        # `sermon_path` / `christ_centered_arc` / `closing` / `human_condition`
        # / `listener_tension` mezők VÁLTOZATLANUL az aktív rendszer forrásai.
        "arc": get_default_arc(),
        # RESET 2A (2026-08-18): a kanonikus `arc`-ra EGYÜTTESEN vonatkozó
        # frissesség-/eredet-metaadat — külön mező, nem egy pont belseje.
        "arc_meta": empty_arc_meta(),
        # RESET 2A: additív scaffolding a biztonságos újragenerálás
        # előnézetéhez — `None`, amíg nincs függőben lévő candidate. Ha
        # van candidate, teljes {"points","reference","context_hash",
        # "generated_at"} szerkezetű (ld. normalize_arc_candidate).
        # Ebben a fázisban is kizárólag adatmodell.
        "arc_candidate": None,
        # RESET 2D-B1: kilenc egymástól teljesen független, függőben lévő
        # MI-pontosítási javaslat (két főgondolat + hét arc-pont) — az
        # `arc`/`arc_meta`/`arc_candidate` sémától teljesen külön, saját
        # mező. Ld. `get_default_field_refinements`.
        "field_refinements": get_default_field_refinements(),
        # RESET 2E-1 (2026-08-20): a kétlépcsős vázlatmotor két új, additív
        # rétege — BELSŐ homiletikai `blueprint` (sosem UI-tartalom, ezért
        # nincs candidate-je) és a felhasználónak szánt, SZERKESZTHETŐ
        # `developed_outline` (kötelező candidate/accept/discard
        # életciklussal). Ebben a fázisban kizárólag adatmodell: nincs
        # AI-hívás, nincs UI, és a legacy `sermon_outline`-nal SEMMILYEN
        # migrációs kapcsolatban nem állnak. Ld. a fájl RESET 2E-1 blokkját.
        "blueprint": empty_blueprint(),
        "blueprint_meta": empty_blueprint_meta(),
        "developed_outline": empty_developed_outline(),
        "developed_outline_meta": empty_developed_outline_meta(),
        "developed_outline_candidate": None,
        "human_condition": {
            "condition": "",
            "false_response": "",
            "human_need": "",
            "divine_action": "",
            "grace_response": "",
        },
        "human_condition_status": "draft",
        "human_condition_approved_context_hash": "",
        "listener_tension": {
            "listener_question": "",
            "listener_resistance": "",
            "sermon_tension": "",
            "promised_resolution": "",
        },
        "listener_tension_status": "draft",
        "listener_tension_approved_context_hash": "",
        "christ_centered_arc": {
            "divine_gracious_action": "",
            "christ_connection": "",
            "christ_connection_type": "",
            "grace_enabled_response": "",
        },
        "christ_centered_arc_status": "draft",
        "christ_centered_arc_approved_context_hash": "",
        "sermon_path": {
            "type": "",
            "reason": "",
            "starting_point": "",
            "first_shift": "",
            "deepening": "",
            "reinterpretation": "",
            "destination": "",
        },
        "sermon_path_status": "draft",
        "sermon_path_approved_context_hash": "",
        "entry_point": {
            "today_connection": "",
            "type": "",
            "text": "",
        },
        "entry_point_status": "draft",
        "entry_point_approved_context_hash": "",
        "entry_point_legacy_prefilled": False,
        "entry_point_suggestions": None,
        "entry_point_last_generated_at": "",
        "sermon_movements": [],
        "selected_images": [],
        "illustrations": [],
        "applications": [],
        "enrichment_status": "draft",
        "illustration_user_direction": "",
        "actualization_user_direction": "",
        "illustration_suggestions": [],
        "actualization_suggestions": [],
        "retained_illustration_cards": [],
        "actualization_connections": [],
        "illustration_suggest_note": "",
        "actualization_suggest_note": "",
        "engagement_elements": [],
        "engagement_suggestions": None,
        "engagement_last_generated_at": "",
        "closing": {
            "type": "",
            "final_discovery": "",
            "hope": "",
            "call_or_response": "",
            "image_or_line": "",
            "open_question": "",
            "tone": "",
        },
        "closing_status": "draft",
        "closing_approved_context_hash": "",
        "diagnostics": {
            "result": {},
            "priorities": [],
        },
        "self_review_strengths": "",
        "self_review_uncertainties": "",
        "self_review_priority": "",
        "self_review_focus": "",
        "m8_last_generated_at": "",
        "lection": {
            "reference": "",
            "connection_type": "",
            "function": "",
            "rationale": "",
            "text": "",
            "notes": "",
            "testament_preference": "any",
            "length_preference": "standard",
            "user_focus": "",
            "text_source": "",
            "text_source_url": "",
            "text_fetched_at": "",
            "text_fetched_reference": "",
        },
        "lection_status": "draft",
        "lection_suggestions": None,
        "lection_assessment": None,
        "lection_connection_analysis": None,
        "m9_lection_last_generated_at": "",
        "prayer_preparation": {
            "tone_preference": "mixed",
            "general_focus": "",
            "rewrite_mode": "integrate_into_arc",
            "before": {
                "own_thoughts": "",
                "purpose": "",
                "movement_notes": "",
                "selected_opening": "",
                "selected_lines": [],
                "closing_direction": "",
                "status": "draft",
            },
            "after": {
                "own_thoughts": "",
                "purpose": "",
                "movement_notes": "",
                "selected_opening": "",
                "selected_lines": [],
                "closing_direction": "",
                "status": "draft",
            },
            "before_suggestions": None,
            "after_suggestions": None,
            "assessment": None,
            "status": "draft",
            "last_generated_at": "",
        },
        "approved_sermon_decisions": [],
        "sermon_main_idea_suggestions": None,
        "sermon_main_idea_assessment": None,
        "human_condition_suggestion": None,
        "human_condition_assessment": None,
        "m4_last_generated_at": "",
        "listener_tension_suggestions": None,
        "listener_tension_assessment": None,
        "m5_last_generated_at": "",
        "gospel_arc_suggestions": None,
        "gospel_arc_assessment": None,
        "m5_gospel_arc_last_generated_at": "",
        "sermon_path_suggestions": None,
        "sermon_path_assessment": None,
        "m6_last_generated_at": "",
        "sermon_enrichment_suggestions": None,
        "sermon_enrichment_assessment": None,
        "m7_last_generated_at": "",
        "closing_suggestions": None,
        "closing_assessment": None,
        "m7_closing_last_generated_at": "",
        "sermon_outline": empty_sermon_outline(),
        "sermon_outline_status": "draft",
        "sermon_outline_generated_at": "",
        "sermon_outline_updated_at": "",
        "sermon_outline_diagnostics": {},
        "sermon_outline_diagnostics_generated_at": "",
        # idle | running | ready | error — normalize megőrzi (ne vesszen el rerun-kor)
        "sermon_outline_diagnostics_status": "idle",
        "sermon_outline_diagnostics_error": "",
    }


_MOVEMENT_FIELD_KEYS = (
    "id",
    "title",
    "role",
    "core_content",
    "textual_basis",
    "listener_discovery",
    "transition_to_next",
)


def empty_sermon_movement(*, role: str = "") -> dict[str, str]:
    """Üres prédikációs mozgás (új elem / biztonságos alapérték)."""
    return {
        "id": str(uuid.uuid4()),
        "title": "",
        "role": _as_str(role),
        "core_content": "",
        "textual_basis": "",
        "listener_discovery": "",
        "transition_to_next": "",
    }


def empty_outline_movement() -> dict[str, Any]:
    return {
        "id": "",
        "title": "",
        "role": "",
        "role_label": "",
        "textual_basis": "",
        "textual_anchor": "",
        "core_content": "",
        "exegetical_core": "",
        "theological_claim": "",
        "listener_discovery": "",
        "grace_application": "",
        "transition": "",
        # Kibontott prédikációs bulletök (homiletikai vázlat főnézet).
        "development": [],
        "images": [],
        "illustrations": [],
        "applications": [],
    }


def empty_sermon_outline() -> dict[str, Any]:
    """Üres igehirdetési vázlat — régi projektek biztonságos alapértéke."""
    return {
        "status": "draft",
        "generated_at": "",
        "updated_at": "",
        "project_title": "",
        "passage_reference": "",
        "bible_translation": "",
        "lection_reference": "",
        "lection_translation": "",
        "sermon_title": "",
        "title_suggestions": [],
        "main_idea": "",
        "main_idea_summary": "",
        "homiletical_aim": "",
        "human_situation": "",
        "listener_question": "",
        "central_tension": "",
        "listener_resistance": "",
        "divine_gracious_action": "",
        "christ_connection": "",
        "christ_connection_type_label": "",
        "gospel_resolution": "",
        "grace_enabled_response": "",
        "opening_direction": "",
        # Munkavázlat bevezetés / megérkezés (főnézet).
        "introduction": {
            "development": "",
            "transition": "",
        },
        "conclusion": {
            "development": "",
            "final_sentence": "",
        },
        # Nem blokkoló textushatár-megjegyzés (pl. gondolati ív a következő versben).
        "text_boundary_note": "",
        "suggested_text_boundary": "",
        # Kanonikus, olvasható vázlatszöveg — előnézet / szerkesztés / diagnosztika.
        "content": "",
        # Régi hosszú Markdown / szabad szöveg — csak „Korábbi vázlat” expanderben.
        "legacy_outline_text": "",
        # Közös motor struktúrája (points / focus_sentence / …).
        "structured": {},
        # pulpit_outline_v3 stb.
        "schema_version": "",
        # Belépési pont: quick | workshop
        "source": "",
        # Forrásanyag-hash a frissítési figyelmeztetéshez.
        "context_hash": "",
        # Mely gated Reszanyag-blokkok (kulcsnevei) kerültek ténylegesen
        # felhasználásra a vázlat összeállításakor — visszakövethetőség.
        "used_module_ids": [],
        "movements": [],
        "extra_enrichment": {
            "images": [],
            "illustrations": [],
            "applications": [],
        },
        "closing": {
            "final_insight": "",
            "gospel_assurance": "",
            "invitation": "",
            "image_or_line": "",
            "open_question": "",
            "tone": "",
            "tone_label": "",
        },
        "lection": {
            "reference": "",
            "function": "",
            "rationale": "",
        },
        "prayer_before": {
            "movements": [],
            "own_thoughts": "",
            "selected_opening": "",
            "selected_lines": [],
            "closing_direction": "",
        },
        "prayer_after": {
            "movements": [],
            "own_thoughts": "",
            "selected_opening": "",
            "selected_lines": [],
            "closing_direction": "",
        },
        "manual_notes": "",
        "editorial_tips": [],
        "manually_edited": False,
        # Hibás (approved + üres) állapot javítása után UI-üzenethez.
        "needs_rebuild": False,
        # Meta — fejlesztői / diagnosztikai; a fő UI nem listázza nyersen
        "source_sections": [],
        "provisional_sections": [],
        "source_fingerprint": "",
        "source_completeness": "",
        "actualization_connections": [],
    }


def _normalize_str_list(raw: Any, *, max_items: int = 20) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = _as_str(item)
        if text:
            out.append(text)
        if len(out) >= max_items:
            break
    return out


def _normalize_outline_prayer(raw: Any) -> dict[str, Any]:
    template = empty_sermon_outline()["prayer_before"]
    if not isinstance(raw, dict):
        return dict(template)
    return {
        "movements": _normalize_str_list(raw.get("movements")),
        "own_thoughts": _as_str(raw.get("own_thoughts")),
        "selected_opening": _as_str(raw.get("selected_opening")),
        "selected_lines": _normalize_str_list(raw.get("selected_lines")),
        "closing_direction": _as_str(raw.get("closing_direction")),
    }


def _normalize_outline_movement(raw: Any) -> dict[str, Any]:
    base = empty_outline_movement()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in (
        "id",
        "title",
        "role",
        "role_label",
        "textual_basis",
        "textual_anchor",
        "core_content",
        "exegetical_core",
        "theological_claim",
        "listener_discovery",
        "grace_application",
        "transition",
    ):
        if key in raw:
            out[key] = _as_str(raw.get(key))
    # Címek ne tartalmazzanak saját számozást (a render adja: „1. …”)
    if out["title"]:
        import re

        out["title"] = re.sub(r"^\s*\d+[.)]\s*", "", out["title"]).strip()
    if not out["textual_anchor"] and out["textual_basis"]:
        out["textual_anchor"] = out["textual_basis"]
    out["development"] = _normalize_str_list(raw.get("development"), max_items=8)
    for list_key in ("images", "illustrations", "applications"):
        out[list_key] = _normalize_str_list(raw.get(list_key))
    return out


# A vázlatmotor korábbi verziójának megfelelő, egyszer rögzített érték —
# KIZÁRÓLAG akkor használt, ha a lusta import (lásd lent) valamiért
# meghiúsulna. Ez nem önálló, karbantartandó "második kanonikus érték": a
# `sermon_outline_engine.SCHEMA_VERSION` mindig elsőbbséget élvez, ezt a
# konstanst csak import-hiba esetén, biztonsági hálóként olvassuk.
_SCHEMA_VERSION_IMPORT_FAILURE_FALLBACK = "pulpit_outline_v8"


def _canonical_outline_schema_version() -> str:
    """Lusta import — a `sermon_outline_engine.SCHEMA_VERSION` az egyetlen
    kanonikus, aktuális vázlat-sémaverzió; elkerüli a körkörös importot
    (a `sermon_outline_engine` modul-szinten importálja ezt a fájlt, ld.
    `from sermon_workshop_data import (...)`). Ugyanaz a minta, mint a
    `_current_passage_context_hash`-nél — hiba esetén sem dobhat kivételt,
    csak a korábban rögzített, ismert-jó értékre esik vissza."""
    try:
        from sermon_outline_engine import SCHEMA_VERSION

        return SCHEMA_VERSION
    except Exception as exc:  # noqa: BLE001
        _log_swallowed_exception("canonical_outline_schema_version", exc)
        return _SCHEMA_VERSION_IMPORT_FAILURE_FALLBACK


def normalize_sermon_outline(raw: Any) -> dict[str, Any]:
    """Vázlat normalizálása; hiányzó mezők biztonságos alapértékkel."""
    base = empty_sermon_outline()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in (
        "generated_at",
        "updated_at",
        "project_title",
        "passage_reference",
        "bible_translation",
        "lection_reference",
        "lection_translation",
        "sermon_title",
        "main_idea",
        "main_idea_summary",
        "homiletical_aim",
        "human_situation",
        "listener_question",
        "central_tension",
        "listener_resistance",
        "divine_gracious_action",
        "christ_connection",
        "christ_connection_type_label",
        "gospel_resolution",
        "grace_enabled_response",
        "opening_direction",
        "content",
        "legacy_outline_text",
        "schema_version",
        "manual_notes",
        "text_boundary_note",
        "suggested_text_boundary",
        "source",
        "context_hash",
    ):
        if key in raw:
            out[key] = _as_str(raw.get(key))
    # Új munkavázlat aliasok
    if not out["main_idea"] and raw.get("focus_sentence"):
        out["main_idea"] = _as_str(raw.get("focus_sentence"))
    if not out["sermon_title"] and raw.get("title"):
        out["sermon_title"] = _as_str(raw.get("title"))
    if not out["passage_reference"] and raw.get("text_reference"):
        out["passage_reference"] = _as_str(raw.get("text_reference"))
    if out["source"] not in ("quick", "workshop", ""):
        out["source"] = ""
    structured_raw = raw.get("structured")
    out["structured"] = dict(structured_raw) if isinstance(structured_raw, dict) else {}
    # Legacy freeform Markdown project outline → content-only shell
    if not out["content"] and isinstance(raw.get("outline"), str) and raw.get("outline"):
        out["content"] = _as_str(raw.get("outline"))
    out["title_suggestions"] = _normalize_str_list(
        raw.get("title_suggestions"), max_items=5
    )
    out["used_module_ids"] = _normalize_str_list(
        raw.get("used_module_ids"), max_items=20
    )
    out["editorial_tips"] = _normalize_str_list(
        raw.get("editorial_tips"), max_items=2
    )
    # Új séma alias: refinement_suggestions → editorial_tips
    if not out["editorial_tips"]:
        out["editorial_tips"] = _normalize_str_list(
            raw.get("refinement_suggestions"), max_items=2
        )
    status = _as_str(raw.get("status")) or "draft"
    if status not in ("draft", "approved", "empty", "needs_refresh", ""):
        status = "draft"
    out["status"] = status or "draft"
    # Régi / hiányzó séma → needs_refresh (tartalom megmarad).
    schema = _as_str(out.get("schema_version"))
    has_body = bool(
        _as_str(out.get("content"))
        or (isinstance(out.get("movements"), list) and out.get("movements"))
        or (isinstance(out.get("structured"), dict) and out.get("structured"))
    )
    if has_body and schema != _canonical_outline_schema_version():
        # Üres schema vagy legacy → jelölés; ne írjuk felül a tartalmat.
        if out["status"] != "needs_refresh":
            out["status"] = "needs_refresh"
    out["manually_edited"] = bool(raw.get("manually_edited"))
    out["needs_rebuild"] = bool(raw.get("needs_rebuild"))
    movements_raw = raw.get("movements")
    movements: list[dict[str, Any]] = []
    if isinstance(movements_raw, list):
        for item in movements_raw[:8]:
            if isinstance(item, dict):
                movements.append(_normalize_outline_movement(item))
    out["movements"] = movements
    intro_candidate = raw.get("introduction")
    intro_raw = intro_candidate if isinstance(intro_candidate, dict) else {}
    introduction = dict(base["introduction"])
    for key in introduction:
        if key in intro_raw:
            introduction[key] = _as_str(intro_raw.get(key))
    # Legacy: opening_direction → introduction.development
    if not introduction["development"] and out.get("opening_direction"):
        introduction["development"] = _as_str(out.get("opening_direction"))
    out["introduction"] = introduction
    if introduction["development"] and not out.get("opening_direction"):
        out["opening_direction"] = introduction["development"]
    conc_candidate = raw.get("conclusion")
    conc_raw = conc_candidate if isinstance(conc_candidate, dict) else {}
    conclusion = dict(base["conclusion"])
    for key in conclusion:
        if key in conc_raw:
            conclusion[key] = _as_str(conc_raw.get(key))
    out["conclusion"] = conclusion
    closing_candidate = raw.get("closing")
    closing_raw = closing_candidate if isinstance(closing_candidate, dict) else {}
    closing = dict(base["closing"])
    for key in closing:
        if key in closing_raw:
            closing[key] = _as_str(closing_raw.get(key))
    # Sync conclusion ↔ closing
    if not conclusion["development"] and closing.get("final_insight"):
        conclusion["development"] = _as_str(closing.get("final_insight"))
    if not conclusion["final_sentence"] and closing.get("image_or_line"):
        conclusion["final_sentence"] = _as_str(closing.get("image_or_line"))
    if conclusion["development"] and not closing.get("final_insight"):
        closing["final_insight"] = conclusion["development"]
    if conclusion["final_sentence"] and not closing.get("image_or_line"):
        closing["image_or_line"] = conclusion["final_sentence"]
    out["conclusion"] = conclusion
    out["closing"] = closing
    lection_candidate = raw.get("lection")
    lection_raw = lection_candidate if isinstance(lection_candidate, dict) else {}
    lection = dict(base["lection"])
    for key in lection:
        if key in lection_raw:
            lection[key] = _as_str(lection_raw.get(key))
    out["lection"] = lection
    extra_candidate = raw.get("extra_enrichment")
    extra_raw = (
        extra_candidate
        if isinstance(extra_candidate, dict)
        else {}
    )
    out["extra_enrichment"] = {
        "images": _normalize_str_list(extra_raw.get("images")),
        "illustrations": _normalize_str_list(extra_raw.get("illustrations")),
        "applications": _normalize_str_list(extra_raw.get("applications")),
    }
    out["prayer_before"] = _normalize_outline_prayer(raw.get("prayer_before"))
    out["prayer_after"] = _normalize_outline_prayer(raw.get("prayer_after"))
    out["source_sections"] = _normalize_str_list(
        raw.get("source_sections"), max_items=40
    )
    out["provisional_sections"] = _normalize_str_list(
        raw.get("provisional_sections"), max_items=20
    )
    out["source_fingerprint"] = _as_str(raw.get("source_fingerprint"))
    completeness = _as_str(raw.get("source_completeness"))
    if completeness not in ("full", "partial", "minimal", ""):
        completeness = "partial" if out["source_sections"] else ""
    out["source_completeness"] = completeness
    out["actualization_connections"] = _normalize_simple_card_list(
        raw.get("actualization_connections"), max_items=8
    )
    return out


def _normalize_diag_status(raw: Any) -> str:
    status = _as_str(raw).casefold() or "idle"
    if status not in ("idle", "running", "ready", "error"):
        return "idle"
    return status


def _diagnostics_has_result(payload: Any) -> bool:
    """Van-e megjeleníthető diagnosztikai eredmény (üres skeleton nem számít)."""
    if not isinstance(payload, dict) or not payload:
        return False
    if _as_str(payload.get("overview")):
        return True
    if _normalize_str_list(payload.get("strengths"), max_items=3):
        return True
    if isinstance(payload.get("refinements"), list) and any(
        isinstance(x, dict) and _as_str(x.get("title")) for x in payload["refinements"]
    ):
        return True
    if isinstance(payload.get("diagnostic_areas"), list) and any(
        isinstance(x, dict) and _as_str(x.get("key")) for x in payload["diagnostic_areas"]
    ):
        return True
    return False


def normalize_sermon_outline_diagnostics(raw: Any) -> dict[str, Any]:
    """Egyszerűsített vázlatdiagnosztika — max 3 erősség / finomítás."""
    if not isinstance(raw, dict):
        return {}
    strengths = _normalize_str_list(raw.get("strengths"), max_items=3)
    refinements: list[dict[str, Any]] = []
    for item in raw.get("refinements") or []:
        if not isinstance(item, dict):
            continue
        title = _as_str(item.get("title"))
        if not title:
            continue
        refinements.append(
            {
                "title": title,
                "explanation": _as_str(
                    item.get("explanation")
                    or item.get("why_it_matters")
                    or item.get("problem")
                ),
                "suggested_action": _as_str(
                    item.get("suggested_action") or item.get("recommended_action")
                ),
                "affected_outline_parts": _normalize_str_list(
                    item.get("affected_outline_parts")
                    or item.get("affected_sections")
                ),
            }
        )
        if len(refinements) >= 3:
            break
    return {
        "overview": _as_str(raw.get("overview") or raw.get("overall_summary")),
        "strengths": strengths,
        "refinements": refinements,
        "ready_to_use": bool(
            raw.get("ready_to_use")
            if "ready_to_use" in raw
            else raw.get("ready_for_next_stage")
        ),
        "next_step": _as_str(raw.get("next_step") or raw.get("readiness_note")),
        "detailed_notes": _normalize_str_list(raw.get("detailed_notes"), max_items=30),
        "warnings": _normalize_str_list(raw.get("warnings"), max_items=20),
        "diagnostic_areas": _normalize_outline_diag_areas(raw.get("diagnostic_areas")),
        "mode": _as_str(raw.get("mode")) or "ai",
        "ok": bool(raw.get("ok", True)),
        "error_message": _as_str(raw.get("error_message")),
        "missing_outline": bool(raw.get("missing_outline")),
        "outline_updated_at_at_diagnosis": _as_str(
            raw.get("outline_updated_at_at_diagnosis")
        ),
    }


def _normalize_outline_diag_areas(raw: Any) -> list[dict[str, Any]]:
    """Vázlatdiagnosztika 8 tengelye — hiányzó score soha ne legyen 0."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = _as_str(item.get("key"))
        if not key:
            continue
        status = _as_str(item.get("status")) or "not_enough_information"
        score_raw = item.get("score")
        score: int | None
        if status == "not_enough_information" or score_raw in (None, "", 0, "0"):
            score = None
        else:
            try:
                score = int(score_raw)
            except (TypeError, ValueError):
                score = None
            if score is not None and score <= 0:
                score = None
            elif score is not None:
                score = max(1, min(4, score))
        out.append(
            {
                "key": key,
                "label": _as_str(item.get("label")) or key,
                "status": status,
                "score": score,
                "summary": _as_str(item.get("summary")),
                "suggested_action": _as_str(item.get("suggested_action")),
            }
        )
    return out


def normalize_sermon_movement(raw: Any) -> dict[str, str]:
    """Egy mozgás normalizálása; hiányzó mezők üres stringgel."""
    base = empty_sermon_movement()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in _MOVEMENT_FIELD_KEYS:
        if key in raw:
            out[key] = _as_str(raw.get(key))
    if not out["id"]:
        out["id"] = str(uuid.uuid4())
    return out


def normalize_sermon_movements(raw: Any, *, max_items: int = 5) -> list[dict[str, str]]:
    """Mozgáslista normalizálása; max 5 elem, érvénytelen elemek kihagyva."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_sermon_movement(item))
        if len(out) >= max_items:
            break
    return out


_TEXTUAL_IMAGE_FIELDS = (
    "id",
    "image",
    "textual_basis",
    "homiletical_function",
    "placement",
    "movement_id",
    "development_notes",
    "source_ref",
)

_ILLUSTRATION_FIELDS = (
    "id",
    "idea",
    "source",
    "function",
    "placement",
    "movement_id",
    "connection_to_text",
    "risk_or_limit",
    "source_ref",
)

_APPLICATION_FIELDS = (
    "id",
    "application",
    "scope",
    "gospel_basis",
    "concreteness",
    "placement",
    "movement_id",
    "pastoral_caution",
    "source_ref",
)

_ENGAGEMENT_ELEMENT_FIELDS = (
    "id",
    "type",
    "text",
    "status",
    "source",
    "created_at",
)
_ENGAGEMENT_STATUSES = frozenset({"draft", "approved"})
_ENGAGEMENT_SOURCES = frozenset({"ai", "own"})


def empty_textual_image() -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "image": "",
        "textual_basis": "",
        "homiletical_function": "",
        "placement": "general",
        "movement_id": "",
        "development_notes": "",
        "source_ref": "",
    }


def empty_illustration() -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "idea": "",
        "source": "needs_verification",
        "function": "",
        "placement": "general",
        "movement_id": "",
        "connection_to_text": "",
        "risk_or_limit": "",
        "source_ref": "",
    }


def empty_application() -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "application": "",
        "scope": "personal",
        "gospel_basis": "",
        "concreteness": "",
        "placement": "general",
        "movement_id": "",
        "pastoral_caution": "",
        "source_ref": "",
    }


def empty_engagement_element(*, type: str = "", source: str = "own") -> dict[str, str]:
    return {
        "id": str(uuid.uuid4()),
        "type": type,
        "text": "",
        "status": "draft",
        "source": source if source in _ENGAGEMENT_SOURCES else "own",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def normalize_engagement_element(raw: Any) -> dict[str, str]:
    base = empty_engagement_element()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in _ENGAGEMENT_ELEMENT_FIELDS:
        if key in raw:
            out[key] = _as_str(raw.get(key))
    if not out["id"]:
        out["id"] = str(uuid.uuid4())
    if out["status"] not in _ENGAGEMENT_STATUSES:
        out["status"] = "draft"
    if out["source"] not in _ENGAGEMENT_SOURCES:
        out["source"] = "own"
    return out


def normalize_engagement_elements(raw: Any, *, max_items: int = 6) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_engagement_element(item))
        if len(out) >= max_items:
            break
    return out


def _normalize_enrichment_item(
    raw: Any,
    *,
    fields: tuple[str, ...],
    empty_fn,
) -> dict[str, str]:
    base = empty_fn()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in fields:
        if key in raw:
            out[key] = _as_str(raw.get(key))
    if not out["id"]:
        out["id"] = str(uuid.uuid4())
    return out


def normalize_textual_image(raw: Any) -> dict[str, str]:
    return _normalize_enrichment_item(
        raw, fields=_TEXTUAL_IMAGE_FIELDS, empty_fn=empty_textual_image
    )


def normalize_illustration(raw: Any) -> dict[str, str]:
    return _normalize_enrichment_item(
        raw, fields=_ILLUSTRATION_FIELDS, empty_fn=empty_illustration
    )


def normalize_application(raw: Any) -> dict[str, str]:
    return _normalize_enrichment_item(
        raw, fields=_APPLICATION_FIELDS, empty_fn=empty_application
    )


def normalize_textual_images(raw: Any, *, max_items: int = 3) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_textual_image(item))
        if len(out) >= max_items:
            break
    return out


def _normalize_simple_card_list(raw: Any, *, max_items: int = 12) -> list[dict[str, Any]]:
    """UI-kártyák laza normalizálása — régi projektek biztonsága."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cleaned: dict[str, Any] = {}
        for key, val in item.items():
            if isinstance(val, bool):
                cleaned[str(key)] = val
            elif isinstance(val, (int, float)):
                cleaned[str(key)] = val
            else:
                cleaned[str(key)] = _as_str(val)
        if not cleaned.get("id"):
            cleaned["id"] = str(uuid.uuid4())
        out.append(cleaned)
        if len(out) >= max_items:
            break
    return out


def normalize_illustrations(raw: Any, *, max_items: int = 3) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_illustration(item))
        if len(out) >= max_items:
            break
    return out


def normalize_applications(raw: Any, *, max_items: int = 4) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_application(item))
        if len(out) >= max_items:
            break
    return out


def _as_str(value: Any) -> str:
    return str(value or "")


def _normalize_str_dict(raw: Any, template: dict[str, str]) -> dict[str, str]:
    out = dict(template)
    if not isinstance(raw, dict):
        return out
    for key in template:
        if key in raw:
            out[key] = _as_str(raw.get(key))
    return out


def _normalize_diagnostics(raw: Any) -> dict[str, Any]:
    """M8 diagnosztika: result = teljes MI-eredmény; priorities = max 3 elem."""
    base: dict[str, Any] = {"result": {}, "priorities": []}
    if not isinstance(raw, dict):
        return base
    result = raw.get("result")
    priorities_raw = raw.get("priorities")
    priorities: list[Any] = []
    if isinstance(priorities_raw, list):
        for item in priorities_raw:
            if isinstance(item, dict):
                priorities.append(
                    {
                        "priority": item.get("priority", len(priorities) + 1),
                        "title": _as_str(item.get("title")),
                        "problem": _as_str(item.get("problem")),
                        "why_it_matters": _as_str(item.get("why_it_matters")),
                        "recommended_action": _as_str(item.get("recommended_action")),
                        "affected_sections": (
                            [_as_str(x) for x in item.get("affected_sections", []) if _as_str(x)]
                            if isinstance(item.get("affected_sections"), list)
                            else []
                        ),
                    }
                )
            elif _as_str(item):
                # Régi string prioritások visszafelé kompatibilisen
                priorities.append(
                    {
                        "priority": len(priorities) + 1,
                        "title": _as_str(item),
                        "problem": "",
                        "why_it_matters": "",
                        "recommended_action": "",
                        "affected_sections": [],
                    }
                )
            if len(priorities) >= 3:
                break
    return {
        "result": dict(result) if isinstance(result, dict) else {},
        "priorities": priorities,
    }


_LECTION_TESTAMENT_PREFS = frozenset(
    {"any", "old_testament", "psalm", "gospel", "new_testament"}
)
_LECTION_LENGTH_PREFS = frozenset({"short", "standard", "extended"})
_LECTION_CONNECTION_TYPES = frozenset(
    {
        "thematic",
        "canonical",
        "redemptive_historical",
        "preparatory",
        "contrast",
        "gospel_complement",
        "liturgical_echo",
    }
)


def normalize_lection_testament_preference(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _LECTION_TESTAMENT_PREFS else "any"


def normalize_lection_length_preference(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _LECTION_LENGTH_PREFS else "standard"


def normalize_lection_connection_type(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _LECTION_CONNECTION_TYPES else ""


def _normalize_lection(raw: Any) -> dict[str, str]:
    """M9 lekcióblokk — biztonságos alapértékek régi projektekhez."""
    template = get_default_sermon_workshop()["lection"]
    out = _normalize_str_dict(raw, template)
    out["testament_preference"] = normalize_lection_testament_preference(
        out.get("testament_preference")
    )
    out["length_preference"] = normalize_lection_length_preference(
        out.get("length_preference")
    )
    conn = normalize_lection_connection_type(out.get("connection_type"))
    out["connection_type"] = conn
    return out


_PRAYER_TONE_PREFS = frozenset(
    {
        "quiet_meditative",
        "honest_confessional",
        "hopeful",
        "assuring",
        "intercessory",
        "communal",
        "festive",
        "simple_direct",
        "biblical_imagery",
        "mixed",
    }
)
_PRAYER_REWRITE_MODES = frozenset(
    {"light_polish", "integrate_into_arc", "free_rephrase"}
)
_PRAYER_SIDE_STATUS = frozenset({"draft", "approved", ""})


def normalize_prayer_tone_preference(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _PRAYER_TONE_PREFS else "mixed"


def normalize_prayer_rewrite_mode(raw: Any) -> str:
    value = _as_str(raw).strip().casefold()
    return value if value in _PRAYER_REWRITE_MODES else "integrate_into_arc"


def _normalize_prayer_lines(raw: Any, *, max_items: int = 24) -> list[str]:
    if isinstance(raw, list):
        out = [_as_str(x).strip() for x in raw if _as_str(x).strip()]
        return out[:max_items]
    text = _as_str(raw).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return lines[:max_items]


def empty_prayer_side() -> dict[str, Any]:
    return {
        "own_thoughts": "",
        "purpose": "",
        "movement_notes": "",
        "selected_opening": "",
        "selected_lines": [],
        "closing_direction": "",
        "status": "draft",
    }


def _normalize_prayer_side(raw: Any) -> dict[str, Any]:
    base = empty_prayer_side()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in (
        "own_thoughts",
        "purpose",
        "movement_notes",
        "selected_opening",
        "closing_direction",
    ):
        if key in raw:
            out[key] = _as_str(raw.get(key))
    if "selected_lines" in raw:
        out["selected_lines"] = _normalize_prayer_lines(raw.get("selected_lines"))
    status = _as_str(raw.get("status")) or "draft"
    if status not in _PRAYER_SIDE_STATUS:
        status = "draft"
    out["status"] = status or "draft"
    return out


def _normalize_prayer_preparation(raw: Any) -> dict[str, Any]:
    """M9 imádsági előkészítés — biztonságos alapértékek régi projektekhez."""
    base = get_default_sermon_workshop()["prayer_preparation"]
    if not isinstance(raw, dict):
        return copy.deepcopy(base)
    status = _as_str(raw.get("status")) or "draft"
    if status not in ("draft", "approved", ""):
        status = "draft"
    return {
        "tone_preference": normalize_prayer_tone_preference(
            raw.get("tone_preference", base["tone_preference"])
        ),
        "general_focus": _as_str(raw.get("general_focus")),
        "rewrite_mode": normalize_prayer_rewrite_mode(
            raw.get("rewrite_mode", base["rewrite_mode"])
        ),
        "before": _normalize_prayer_side(raw.get("before")),
        "after": _normalize_prayer_side(raw.get("after")),
        "before_suggestions": _normalize_optional_dict(
            raw.get("before_suggestions", base["before_suggestions"])
        ),
        "after_suggestions": _normalize_optional_dict(
            raw.get("after_suggestions", base["after_suggestions"])
        ),
        "assessment": _normalize_optional_dict(
            raw.get("assessment", base["assessment"])
        ),
        "status": status or "draft",
        "last_generated_at": _as_str(raw.get("last_generated_at")),
    }


def _normalize_decisions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "id": _as_str(item.get("id")),
                "source_section": _as_str(item.get("source_section")),
                "category": _as_str(item.get("category")),
                "content": _as_str(item.get("content")),
                "approved": bool(item.get("approved", True)),
                "created_at": _as_str(item.get("created_at")),
            }
        )
    return out


def _normalize_generic_list(raw: Any) -> list[Any]:
    if not isinstance(raw, list):
        return []
    return list(raw)


def _normalize_optional_dict(raw: Any) -> dict[str, Any] | None:
    """MI-eredmény dict vagy None; hibás típus → None (régi projektek biztonsága)."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    return None


def normalize_sermon_workshop(data: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `sermon_workshop` struktúrát ad vissza."""
    base = get_default_sermon_workshop()
    if not isinstance(data, dict):
        return base

    status = _as_str(data.get("sermon_main_idea_status")) or "draft"
    if status not in ("draft", "approved", ""):
        status = "draft"

    def _norm_status(raw: Any) -> str:
        val = _as_str(raw) or "draft"
        if val not in ("draft", "approved", ""):
            return "draft"
        return val or "draft"

    enrichment_status = _norm_status(data.get("enrichment_status"))
    closing_status = _norm_status(data.get("closing_status"))
    lection_status = _norm_status(data.get("lection_status"))
    human_condition_status = _norm_status(data.get("human_condition_status"))
    listener_tension_status = _norm_status(data.get("listener_tension_status"))
    christ_centered_arc_status = _norm_status(data.get("christ_centered_arc_status"))
    sermon_path_status = _norm_status(data.get("sermon_path_status"))
    entry_point_status = _norm_status(data.get("entry_point_status"))

    outline_status = _as_str(data.get("sermon_outline_status")) or "draft"
    if outline_status not in ("draft", "approved", "empty", "needs_refresh", ""):
        outline_status = "draft"

    hc_block = _normalize_str_dict(data.get("human_condition"), base["human_condition"])
    lt_block = _normalize_str_dict(data.get("listener_tension"), base["listener_tension"])
    entry_block = _normalize_str_dict(data.get("entry_point"), base["entry_point"])
    legacy_prefilled = bool(data.get("entry_point_legacy_prefilled"))
    if (
        not legacy_prefilled
        and not entry_block.get("today_connection")
        and not entry_block.get("text")
    ):
        legacy_hint = (
            hc_block.get("condition")
            or hc_block.get("divine_action")
            or lt_block.get("sermon_tension")
            or ""
        ).strip()
        if legacy_hint:
            entry_block = dict(entry_block)
            entry_block["today_connection"] = legacy_hint
            legacy_prefilled = True

    return {
        "sermon_main_idea": _as_str(data.get("sermon_main_idea")),
        "sermon_main_idea_status": status or "draft",
        "sermon_main_idea_approved_context_hash": _as_str(
            data.get("sermon_main_idea_approved_context_hash")
        ),
        # ÚJ, additív mező — ld. get_default_sermon_workshop() megjegyzését.
        "arc": normalize_arc(data.get("arc")),
        # RESET 2A: ugyanúgy additív, önálló mezők — nem az `arc` alstruktúrái.
        "arc_meta": normalize_arc_meta(data.get("arc_meta")),
        "arc_candidate": normalize_arc_candidate(data.get("arc_candidate")),
        # RESET 2D-B1: ugyanúgy additív, önálló mező — ld.
        # get_default_sermon_workshop() megjegyzését.
        "field_refinements": normalize_field_refinements(data.get("field_refinements")),
        # RESET 2E-1: additív, önálló mezők — régi projektben hiányoznak,
        # ilyenkor biztonságos alapértéket kapnak (nincs migráció a legacy
        # `sermon_outline`-ból). Ld. get_default_sermon_workshop() megjegyzését.
        "blueprint": normalize_blueprint(data.get("blueprint")),
        "blueprint_meta": normalize_blueprint_meta(data.get("blueprint_meta")),
        "developed_outline": normalize_developed_outline(data.get("developed_outline")),
        "developed_outline_meta": normalize_developed_outline_meta(
            data.get("developed_outline_meta")
        ),
        "developed_outline_candidate": normalize_developed_outline_candidate(
            data.get("developed_outline_candidate")
        ),
        "human_condition": hc_block,
        "human_condition_status": human_condition_status,
        "human_condition_approved_context_hash": _as_str(
            data.get("human_condition_approved_context_hash")
        ),
        "listener_tension": lt_block,
        "listener_tension_status": listener_tension_status,
        "listener_tension_approved_context_hash": _as_str(
            data.get("listener_tension_approved_context_hash")
        ),
        "christ_centered_arc": _normalize_str_dict(
            data.get("christ_centered_arc"), base["christ_centered_arc"]
        ),
        "christ_centered_arc_status": christ_centered_arc_status,
        "christ_centered_arc_approved_context_hash": _as_str(
            data.get("christ_centered_arc_approved_context_hash")
        ),
        "sermon_path": _normalize_str_dict(
            data.get("sermon_path"), base["sermon_path"]
        ),
        "sermon_path_status": sermon_path_status,
        "sermon_path_approved_context_hash": _as_str(
            data.get("sermon_path_approved_context_hash")
        ),
        "entry_point": entry_block,
        "entry_point_status": entry_point_status,
        "entry_point_approved_context_hash": _as_str(
            data.get("entry_point_approved_context_hash")
        ),
        "entry_point_legacy_prefilled": legacy_prefilled,
        "entry_point_suggestions": _normalize_optional_dict(
            data.get("entry_point_suggestions", base["entry_point_suggestions"])
        ),
        "entry_point_last_generated_at": _as_str(
            data.get("entry_point_last_generated_at")
        ),
        "sermon_movements": normalize_sermon_movements(data.get("sermon_movements")),
        "selected_images": normalize_textual_images(data.get("selected_images")),
        "illustrations": normalize_illustrations(data.get("illustrations")),
        "applications": normalize_applications(data.get("applications")),
        "enrichment_status": enrichment_status or "draft",
        "illustration_user_direction": _as_str(
            data.get("illustration_user_direction")
        ),
        "actualization_user_direction": _as_str(
            data.get("actualization_user_direction")
        ),
        "illustration_suggestions": _normalize_simple_card_list(
            data.get("illustration_suggestions")
        ),
        "actualization_suggestions": _normalize_simple_card_list(
            data.get("actualization_suggestions")
        ),
        "retained_illustration_cards": _normalize_simple_card_list(
            data.get("retained_illustration_cards")
        ),
        "actualization_connections": _normalize_simple_card_list(
            data.get("actualization_connections")
        ),
        "illustration_suggest_note": _as_str(data.get("illustration_suggest_note")),
        "actualization_suggest_note": _as_str(data.get("actualization_suggest_note")),
        "engagement_elements": normalize_engagement_elements(
            data.get("engagement_elements")
        ),
        "engagement_suggestions": _normalize_optional_dict(
            data.get("engagement_suggestions", base["engagement_suggestions"])
        ),
        "engagement_last_generated_at": _as_str(
            data.get("engagement_last_generated_at")
        ),
        "closing": _normalize_str_dict(data.get("closing"), base["closing"]),
        "closing_status": closing_status or "draft",
        "closing_approved_context_hash": _as_str(
            data.get("closing_approved_context_hash")
        ),
        "diagnostics": _normalize_diagnostics(data.get("diagnostics")),
        "lection": _normalize_lection(data.get("lection")),
        "lection_status": lection_status or "draft",
        "prayer_preparation": _normalize_prayer_preparation(
            data.get("prayer_preparation")
        ),
        "approved_sermon_decisions": _normalize_decisions(
            data.get("approved_sermon_decisions")
        ),
        "sermon_main_idea_suggestions": _normalize_optional_dict(
            data.get(
                "sermon_main_idea_suggestions",
                base["sermon_main_idea_suggestions"],
            )
        ),
        "sermon_main_idea_assessment": _normalize_optional_dict(
            data.get(
                "sermon_main_idea_assessment",
                base["sermon_main_idea_assessment"],
            )
        ),
        "human_condition_suggestion": _normalize_optional_dict(
            data.get(
                "human_condition_suggestion",
                base["human_condition_suggestion"],
            )
        ),
        "human_condition_assessment": _normalize_optional_dict(
            data.get(
                "human_condition_assessment",
                base["human_condition_assessment"],
            )
        ),
        "m4_last_generated_at": _as_str(data.get("m4_last_generated_at")),
        "listener_tension_suggestions": _normalize_optional_dict(
            data.get(
                "listener_tension_suggestions",
                base["listener_tension_suggestions"],
            )
        ),
        "listener_tension_assessment": _normalize_optional_dict(
            data.get(
                "listener_tension_assessment",
                base["listener_tension_assessment"],
            )
        ),
        "m5_last_generated_at": _as_str(data.get("m5_last_generated_at")),
        "gospel_arc_suggestions": _normalize_optional_dict(
            data.get(
                "gospel_arc_suggestions",
                base["gospel_arc_suggestions"],
            )
        ),
        "gospel_arc_assessment": _normalize_optional_dict(
            data.get(
                "gospel_arc_assessment",
                base["gospel_arc_assessment"],
            )
        ),
        "m5_gospel_arc_last_generated_at": _as_str(
            data.get("m5_gospel_arc_last_generated_at")
        ),
        "sermon_path_suggestions": _normalize_optional_dict(
            data.get(
                "sermon_path_suggestions",
                base["sermon_path_suggestions"],
            )
        ),
        "sermon_path_assessment": _normalize_optional_dict(
            data.get(
                "sermon_path_assessment",
                base["sermon_path_assessment"],
            )
        ),
        "m6_last_generated_at": _as_str(data.get("m6_last_generated_at")),
        "sermon_enrichment_suggestions": _normalize_optional_dict(
            data.get(
                "sermon_enrichment_suggestions",
                base["sermon_enrichment_suggestions"],
            )
        ),
        "sermon_enrichment_assessment": _normalize_optional_dict(
            data.get(
                "sermon_enrichment_assessment",
                base["sermon_enrichment_assessment"],
            )
        ),
        "m7_last_generated_at": _as_str(data.get("m7_last_generated_at")),
        "closing_suggestions": _normalize_optional_dict(
            data.get("closing_suggestions", base["closing_suggestions"])
        ),
        "closing_assessment": _normalize_optional_dict(
            data.get("closing_assessment", base["closing_assessment"])
        ),
        "m7_closing_last_generated_at": _as_str(
            data.get("m7_closing_last_generated_at")
        ),
        "self_review_strengths": _as_str(data.get("self_review_strengths")),
        "self_review_uncertainties": _as_str(data.get("self_review_uncertainties")),
        "self_review_priority": _as_str(data.get("self_review_priority")),
        "self_review_focus": _as_str(data.get("self_review_focus")),
        "m8_last_generated_at": _as_str(data.get("m8_last_generated_at")),
        "lection_suggestions": _normalize_optional_dict(
            data.get("lection_suggestions", base["lection_suggestions"])
        ),
        "lection_assessment": _normalize_optional_dict(
            data.get("lection_assessment", base["lection_assessment"])
        ),
        "lection_connection_analysis": _normalize_lection_connection_analysis_field(
            data.get(
                "lection_connection_analysis",
                base.get("lection_connection_analysis"),
            )
        ),
        "m9_lection_last_generated_at": _as_str(
            data.get("m9_lection_last_generated_at")
        ),
        "sermon_outline": normalize_sermon_outline(data.get("sermon_outline")),
        "sermon_outline_status": outline_status or "draft",
        "sermon_outline_generated_at": _as_str(
            data.get("sermon_outline_generated_at")
        ),
        "sermon_outline_updated_at": _as_str(data.get("sermon_outline_updated_at")),
        "sermon_outline_diagnostics": normalize_sermon_outline_diagnostics(
            data.get("sermon_outline_diagnostics")
        ),
        "sermon_outline_diagnostics_generated_at": _as_str(
            data.get("sermon_outline_diagnostics_generated_at")
        ),
        "sermon_outline_diagnostics_status": _normalize_diag_status(
            data.get(
                "sermon_outline_diagnostics_status",
                base.get("sermon_outline_diagnostics_status"),
            )
        ),
        "sermon_outline_diagnostics_error": _as_str(
            data.get(
                "sermon_outline_diagnostics_error",
                base.get("sermon_outline_diagnostics_error"),
            )
        ),
    }


def ensure_sermon_workshop_state(
    session_state: MutableMapping[str, Any],
) -> dict[str, Any]:
    """Biztosítja, hogy a session tartalmazzon érvényes `sermon_workshop` adatot."""
    normalized = normalize_sermon_workshop(session_state.get(SERMON_WORKSHOP_KEY))
    session_state[SERMON_WORKSHOP_KEY] = normalized
    return normalized


def _current_passage_context_hash(session_state: Mapping[str, Any]) -> str:
    """Lusta import — a sermon_outline_engine modulra épülő szűk igehely-
    ujjlenyomat, elkerülve a körkörös importot (az modul-szinten importálja
    ezt a fájlt). Hiba esetén üres string — a jóváhagyás sose bukjon el
    emiatt, csak a STALE-ellenőrzés marad ki (visszafelé-kompatibilis eset)."""
    try:
        from sermon_outline_engine import compute_current_passage_context_hash

        return compute_current_passage_context_hash(session_state)
    except Exception as exc:  # noqa: BLE001
        _log_swallowed_exception("current_passage_context_hash", exc)
        return ""


# A gated blokkok közül melyikhez tartozik `_approved_context_hash` mentés,
# amikor a `_status` mezője "approved"-ra vált. Az enrichment/lection NINCS
# itt, mert azok nem `_APPROVAL_GATED_KEYS` tagjai.
_APPROVED_HASH_TRACKED_STATUS_KEYS = frozenset(
    {
        "sermon_main_idea_status",
        "human_condition_status",
        "listener_tension_status",
        "christ_centered_arc_status",
        "sermon_path_status",
        "entry_point_status",
        "closing_status",
    }
)


def update_sermon_workshop_section(
    session_state: MutableMapping[str, Any],
    section: str,
    data: Any,
) -> dict[str, Any]:
    """Egy szakasz / mezőcsoport frissítése a `sermon_workshop`-ban.

    `section` lehet pl. `human_condition`, `sermon_path`, `sermon_main_idea`,
    `sermon_movements`, stb. A `sermon_main_idea` esetén a `data` lehet string
    vagy dict (`sermon_main_idea` / `sermon_main_idea_status` kulcsokkal).

    Amikor egy gated blokk `_status` mezője "approved"-ra vált — bármelyik
    hívási úton (közvetlen gomb, `accept_workshop_proposal`, MI-javaslat
    elfogadása) —, ez a függvény EGYSÉGESEN elmenti a
    `<blokk>_approved_context_hash` mezőt is, hogy a vázlatmotor STALE-
    ellenőrzése működjön. Ez szándékosan központosított egyetlen helyen,
    hogy ne kelljen minden egyes UI-gombnál külön megismételni (és emiatt
    könnyen kifelejteni).
    """
    sw = ensure_sermon_workshop_state(session_state)
    key = str(section or "").strip()

    if key in ("sermon_main_idea", "main_idea"):
        if isinstance(data, dict):
            if "sermon_main_idea" in data:
                sw["sermon_main_idea"] = _as_str(data.get("sermon_main_idea"))
            if "sermon_main_idea_status" in data:
                status = _as_str(data.get("sermon_main_idea_status")) or "draft"
                if status not in ("draft", "approved", ""):
                    status = "draft"
                sw["sermon_main_idea_status"] = status or "draft"
                if status == "approved":
                    sw["sermon_main_idea_approved_context_hash"] = (
                        _current_passage_context_hash(session_state)
                    )
        else:
            sw["sermon_main_idea"] = _as_str(data)
        return sw

    if key == "sermon_main_idea_status":
        status = _as_str(data) or "draft"
        if status not in ("draft", "approved", ""):
            status = "draft"
        sw["sermon_main_idea_status"] = status or "draft"
        if status == "approved":
            sw["sermon_main_idea_approved_context_hash"] = (
                _current_passage_context_hash(session_state)
            )
        return sw

    if key in (
        "human_condition_status",
        "listener_tension_status",
        "christ_centered_arc_status",
        "sermon_path_status",
        "entry_point_status",
        "enrichment_status",
        "closing_status",
        "lection_status",
    ):
        status = _as_str(data) or "draft"
        if status not in ("draft", "approved", ""):
            status = "draft"
        sw[key] = status or "draft"
        if status == "approved" and key in _APPROVED_HASH_TRACKED_STATUS_KEYS:
            base_key = key[: -len("_status")]
            sw[f"{base_key}_approved_context_hash"] = _current_passage_context_hash(
                session_state
            )
        return sw

    if key == "sermon_outline_status":
        status = _as_str(data) or "draft"
        if status not in ("draft", "approved", "empty", ""):
            status = "draft"
        sw["sermon_outline_status"] = status or "draft"
        outline = normalize_sermon_outline(sw.get("sermon_outline"))
        outline["status"] = sw["sermon_outline_status"]
        sw["sermon_outline"] = outline
        return sw

    if key in ("sermon_outline", "outline"):
        outline = normalize_sermon_outline(data)
        sw["sermon_outline"] = outline
        status = _as_str(outline.get("status")) or "draft"
        if status not in ("draft", "approved", "empty", ""):
            status = "draft"
        sw["sermon_outline_status"] = status or "draft"
        if outline.get("generated_at"):
            sw["sermon_outline_generated_at"] = _as_str(outline.get("generated_at"))
        if outline.get("updated_at"):
            sw["sermon_outline_updated_at"] = _as_str(outline.get("updated_at"))
        return sw

    if key == "sermon_outline_diagnostics":
        sw["sermon_outline_diagnostics"] = normalize_sermon_outline_diagnostics(data)
        return sw

    if key in (
        "self_review_strengths",
        "self_review_uncertainties",
        "self_review_priority",
        "self_review_focus",
    ):
        sw[key] = _as_str(data)
        return sw

    if key in _SECTION_DICT_KEYS:
        template = get_default_sermon_workshop()[key]
        if key == "diagnostics":
            sw[key] = _normalize_diagnostics(data)
        elif key == "lection":
            current = sw.get(key) if isinstance(sw.get(key), dict) else {}
            merged = dict(template)
            if isinstance(current, dict):
                merged.update({k: _as_str(current.get(k)) for k in template})
            if isinstance(data, dict):
                for field_key in template:
                    if field_key in data:
                        merged[field_key] = _as_str(data.get(field_key))
            sw[key] = _normalize_lection(merged)
        elif key == "prayer_preparation":
            current = sw.get(key) if isinstance(sw.get(key), dict) else {}
            merged = copy.deepcopy(template)
            if isinstance(current, dict):
                merged = _normalize_prayer_preparation({**merged, **current})
            if isinstance(data, dict):
                # Mély merge: top-level + before/after részleges frissítés
                for top_key, top_val in data.items():
                    if top_key in ("before", "after") and isinstance(top_val, dict):
                        side = dict(merged.get(top_key) or {})
                        side.update(top_val)
                        merged[top_key] = side
                    elif top_key in merged or top_key in (
                        "before_suggestions",
                        "after_suggestions",
                        "assessment",
                        "tone_preference",
                        "general_focus",
                        "rewrite_mode",
                        "status",
                        "last_generated_at",
                    ):
                        merged[top_key] = top_val
            sw[key] = _normalize_prayer_preparation(merged)
        else:
            # Merge: meglévő + új mezők
            current = sw.get(key) if isinstance(sw.get(key), dict) else {}
            merged = dict(template)
            if isinstance(current, dict):
                merged.update({k: _as_str(current.get(k)) for k in template})
            if isinstance(data, dict):
                for field_key in template:
                    if field_key in data:
                        merged[field_key] = _as_str(data.get(field_key))
            sw[key] = merged
        return sw

    if key in _SECTION_LIST_KEYS:
        if key == "approved_sermon_decisions":
            sw[key] = _normalize_decisions(data)
        elif key == "sermon_movements":
            sw[key] = normalize_sermon_movements(data)
        elif key == "selected_images":
            sw[key] = normalize_textual_images(data)
        elif key == "illustrations":
            sw[key] = normalize_illustrations(data)
        elif key == "applications":
            sw[key] = normalize_applications(data)
        elif key in (
            "illustration_suggestions",
            "actualization_suggestions",
            "retained_illustration_cards",
            "actualization_connections",
        ):
            sw[key] = _normalize_simple_card_list(data)
        elif key == "engagement_elements":
            sw[key] = normalize_engagement_elements(data)
        else:
            sw[key] = _normalize_generic_list(data)
        return sw

    if key in _SECTION_STR_KEYS:
        sw[key] = _as_str(data)
        return sw

    # Ismeretlen szakasz: ne dobjon hibát; hagyja érintetlenül
    return sw


def add_approved_sermon_decision(
    session_state: MutableMapping[str, Any],
    source_section: str,
    category: str,
    content: str,
) -> dict[str, Any]:
    """Új jóváhagyott homiletikai döntés. Gemini / DB nélkül."""
    sw = ensure_sermon_workshop_state(session_state)
    decision = {
        "id": str(uuid.uuid4()),
        "source_section": _as_str(source_section),
        "category": _as_str(category),
        "content": _as_str(content),
        "approved": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    sw["approved_sermon_decisions"].append(decision)
    return decision


def _decision_duplicate_in_sw(
    sw: Mapping[str, Any],
    *,
    source_section: str,
    category: str,
    content: str,
) -> bool:
    needle = _as_str(content)
    if not needle:
        return True
    for item in sw.get("approved_sermon_decisions") or []:
        if not isinstance(item, dict):
            continue
        if (
            _as_str(item.get("source_section")) == source_section
            and _as_str(item.get("category")) == category
            and _as_str(item.get("content")) == needle
        ):
            return True
    return False


def accept_workshop_proposal(
    session_state: MutableMapping[str, Any],
    *,
    section_key: str,
    block: Mapping[str, Any] | str,
    source_section: str,
    field_categories: list[tuple[str, str]] | None = None,
    status_key: str | None = None,
    main_idea_category: str = "Fő gondolat",
    finalize: bool = False,
) -> dict[str, Any]:
    """Javaslat átvétele = tartós draft mentés a szerkeszthető mezőkbe.

    - ``finalize=False`` (alapértelmezett): státusz ``draft``, nem kerül a
      ``approved_sermon_decisions`` listába — a végleges jóváhagyás külön gomb.
    - ``finalize=True``: státusz ``approved`` + döntések rögzítése.

    Vissza: ``{"added": int, "status_key": str, "section_key": str, "status": str}``.
    """
    sw = ensure_sermon_workshop_state(session_state)
    resolved_status = status_key
    added = 0
    target_status = "approved" if finalize else "draft"

    if section_key in ("sermon_main_idea", "main_idea"):
        text = (
            _as_str(block.get("sermon_main_idea"))
            if isinstance(block, Mapping)
            else _as_str(block)
        )
        update_sermon_workshop_section(
            session_state,
            "sermon_main_idea",
            {
                "sermon_main_idea": text,
                "sermon_main_idea_status": target_status,
            },
        )
        resolved_status = "sermon_main_idea_status"
        if (
            finalize
            and text
            and not _decision_duplicate_in_sw(
                sw,
                source_section=source_section,
                category=main_idea_category,
                content=text,
            )
        ):
            add_approved_sermon_decision(
                session_state, source_section, main_idea_category, text
            )
            added = 1
        return {
            "added": added,
            "status_key": resolved_status,
            "section_key": "sermon_main_idea",
            "status": target_status,
        }

    payload = dict(block) if isinstance(block, Mapping) else {}
    update_sermon_workshop_section(session_state, section_key, payload)
    if not resolved_status:
        resolved_status = f"{section_key}_status"
    if resolved_status in sw or resolved_status.endswith("_status"):
        update_sermon_workshop_section(session_state, resolved_status, target_status)

    if not finalize:
        return {
            "added": 0,
            "status_key": resolved_status or "",
            "section_key": section_key,
            "status": target_status,
        }

    cats = field_categories or [
        (str(k), str(k)) for k in payload.keys() if _as_str(payload.get(k))
    ]
    for field, category in cats:
        content = _as_str(payload.get(field))
        if not content:
            continue
        if _decision_duplicate_in_sw(
            sw,
            source_section=source_section,
            category=category,
            content=content,
        ):
            continue
        add_approved_sermon_decision(
            session_state, source_section, category, content
        )
        added += 1

    return {
        "added": added,
        "status_key": resolved_status or "",
        "section_key": section_key,
        "status": target_status,
    }


def section_has_accepted_content(
    session_state: Mapping[str, Any],
    *,
    section_key: str,
    status_key: str | None = None,
    source_section: str | None = None,
) -> bool:
    """Van-e már jóváhagyott / átvett anyag a szakaszban."""
    sw = normalize_sermon_workshop(session_state.get(SERMON_WORKSHOP_KEY))
    sk = status_key or (
        "sermon_main_idea_status"
        if section_key in ("sermon_main_idea", "main_idea")
        else f"{section_key}_status"
    )
    if _as_str(sw.get(sk)) == "approved":
        return True
    if source_section:
        for item in sw.get("approved_sermon_decisions") or []:
            if not isinstance(item, dict):
                continue
            if _as_str(item.get("source_section")) != source_section:
                continue
            if item.get("approved") is False:
                continue
            if _as_str(item.get("content")):
                return True
    return False


def remove_approved_sermon_decision(
    session_state: MutableMapping[str, Any],
    decision_id: str,
) -> dict[str, Any]:
    """Homiletikai döntés eltávolítása `id` alapján."""
    sw = ensure_sermon_workshop_state(session_state)
    target = _as_str(decision_id)
    sw["approved_sermon_decisions"] = [
        item
        for item in sw["approved_sermon_decisions"]
        if _as_str(item.get("id")) != target
    ]
    return sw


def add_engagement_element(
    session_state: MutableMapping[str, Any],
    *,
    type: str,
    text: str,
    source: str = "own",
) -> dict[str, Any]:
    """Új megszólító elem hozzáadása (MI-javaslat átvétele vagy saját elem)."""
    sw = ensure_sermon_workshop_state(session_state)
    element = empty_engagement_element(type=type, source=source)
    element["text"] = _as_str(text)
    sw["engagement_elements"] = list(sw.get("engagement_elements") or []) + [element]
    return element


def update_engagement_element(
    session_state: MutableMapping[str, Any],
    element_id: str,
    *,
    type: str | None = None,
    text: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    """Egy megszólító elem szerkesztése / jóváhagyása `id` alapján.

    Jóváhagyáskor (`status == "approved"`) a többi szakaszhoz hasonlóan
    STALE-ellenőrzésre alkalmas kontextushash-t is kapna — mivel azonban
    ez elemenkénti (nem egyetlen blokk-státusz), a vázlatmotor a
    jóváhagyott elemet magát a tartalom alapján szűri be
    (`collect_outline_context_bundle`), nem egy közös blokk-hash alapján.
    """
    sw = ensure_sermon_workshop_state(session_state)
    target = _as_str(element_id)
    updated: dict[str, Any] | None = None
    elements: list[dict[str, Any]] = []
    for item in sw.get("engagement_elements") or []:
        if not isinstance(item, dict):
            continue
        if _as_str(item.get("id")) == target:
            item = dict(item)
            if type is not None:
                item["type"] = _as_str(type)
            if text is not None:
                item["text"] = _as_str(text)
            if status is not None:
                status_norm = _as_str(status)
                item["status"] = status_norm if status_norm in _ENGAGEMENT_STATUSES else "draft"
            updated = item
        elements.append(item)
    sw["engagement_elements"] = elements
    return updated


def remove_engagement_element(
    session_state: MutableMapping[str, Any],
    element_id: str,
) -> dict[str, Any]:
    """Megszólító elem eltávolítása `id` alapján."""
    sw = ensure_sermon_workshop_state(session_state)
    target = _as_str(element_id)
    sw["engagement_elements"] = [
        item
        for item in (sw.get("engagement_elements") or [])
        if isinstance(item, dict) and _as_str(item.get("id")) != target
    ]
    return sw


def save_engagement_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós Megszólítás és bevonás javaslat mentése (átvétel előtti staging)."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["engagement_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["engagement_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def deepcopy_sermon_workshop(data: Any) -> dict[str, Any]:
    """Normalizált másolat (tesztekhez / biztonságos átadáshoz)."""
    return copy.deepcopy(normalize_sermon_workshop(data))


def save_sermon_main_idea_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M4 főgondolat-javaslat mentése a sermon_workshop-ba."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_main_idea_suggestions"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m4_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_sermon_main_idea_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M4 főgondolat-értékelés mentése a sermon_workshop-ba."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_main_idea_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m4_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_human_condition_suggestion(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós emberi helyzet javaslat mentése a sermon_workshop-ba."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["human_condition_suggestion"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m4_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_human_condition_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós emberi helyzet értékelés mentése a sermon_workshop-ba."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["human_condition_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m4_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_listener_tension_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M5 hallgatói feszültség-javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["listener_tension_suggestions"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m5_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_listener_tension_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M5 hallgatói feszültség-értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["listener_tension_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m5_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_gospel_arc_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M5 evangéliumi ív javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["gospel_arc_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m5_gospel_arc_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_gospel_arc_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M5 evangéliumi ív értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["gospel_arc_assessment"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m5_gospel_arc_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_entry_point_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós Homiletikai belépési pont javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["entry_point_suggestions"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["entry_point_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_sermon_path_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M6 igehirdetési út javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_path_suggestions"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m6_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_sermon_path_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M6 igehirdetési út értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_path_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m6_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_sermon_enrichment_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M7 kép/illusztráció/alkalmazás javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_enrichment_suggestions"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m7_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_sermon_enrichment_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M7 kép/illusztráció/alkalmazás értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["sermon_enrichment_assessment"] = (
        dict(payload) if isinstance(payload, dict) else None
    )
    if stamp_generated_at:
        sw["m7_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def save_closing_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M7 lezárási javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["closing_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m7_closing_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_closing_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M7 lezárási értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["closing_assessment"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m7_closing_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_homiletical_diagnostics(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M8 diagnosztika mentése a meglévő `diagnostics` kulcsba.

    Nem módosítja az M4–M7 tartalmakat és a kézi önellenőrző mezőket.
    """
    sw = ensure_sermon_workshop_state(session_state)
    result = dict(payload) if isinstance(payload, dict) else {}
    priorities_raw = result.get("revision_priorities")
    priorities: list[Any] = []
    if isinstance(priorities_raw, list):
        for item in priorities_raw[:3]:
            if isinstance(item, dict):
                priorities.append(item)
            elif _as_str(item):
                priorities.append({"title": _as_str(item), "priority": len(priorities) + 1})
    sw["diagnostics"] = _normalize_diagnostics(
        {"result": result, "priorities": priorities}
    )
    if stamp_generated_at:
        sw["m8_last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    return sw


def _normalize_lection_connection_analysis_field(raw: Any) -> dict[str, Any] | None:
    """Lekció–textus kapcsolati elemzés tartós mezője."""
    try:
        from sermon_workshop_lection_link_ai import (
            normalize_lection_connection_analysis,
        )
    except Exception as exc:  # pragma: no cover
        _log_swallowed_exception("lection_connection_analysis_import", exc)
        return _normalize_optional_dict(raw) if isinstance(raw, dict) else None
    return normalize_lection_connection_analysis(raw)


def save_lection_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 lekciójavaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["lection_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m9_lection_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_lection_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 lekcióértékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["lection_assessment"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        sw["m9_lection_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_lection_connection_analysis(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any] | None,
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós lekció–textus kapcsolati elemzés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    normalized = _normalize_lection_connection_analysis_field(payload)
    sw["lection_connection_analysis"] = normalized
    if stamp_generated_at and isinstance(normalized, dict) and normalized.get("ok"):
        if not _as_str(normalized.get("generated_at")):
            normalized["generated_at"] = datetime.now().isoformat(timespec="seconds")
            sw["lection_connection_analysis"] = normalized
        sw["m9_lection_last_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    return sw


def save_prayer_before_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 előtti imaív javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    prep = _normalize_prayer_preparation(sw.get("prayer_preparation"))
    prep["before_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        prep["last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    sw["prayer_preparation"] = prep
    return sw


def save_prayer_after_suggestions(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 utáni imaív javaslat mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    prep = _normalize_prayer_preparation(sw.get("prayer_preparation"))
    prep["after_suggestions"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        prep["last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    sw["prayer_preparation"] = prep
    return sw


def save_prayer_assessment(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Tartós M9 imádsági terv értékelés mentése."""
    sw = ensure_sermon_workshop_state(session_state)
    prep = _normalize_prayer_preparation(sw.get("prayer_preparation"))
    prep["assessment"] = dict(payload) if isinstance(payload, dict) else None
    if stamp_generated_at:
        prep["last_generated_at"] = datetime.now().isoformat(timespec="seconds")
    sw["prayer_preparation"] = prep
    return sw


def save_sermon_outline(
    session_state: MutableMapping[str, Any],
    outline: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
    mark_manual_edit: bool = False,
) -> dict[str, Any]:
    """Igehirdetési vázlat tartós mentése. Nem módosítja az M4–M9 forrásmezőket."""
    sw = ensure_sermon_workshop_state(session_state)
    normalized = normalize_sermon_outline(outline)
    now = datetime.now().isoformat(timespec="seconds")
    if stamp_generated_at and not _as_str(normalized.get("generated_at")):
        normalized["generated_at"] = now
    normalized["updated_at"] = now
    if mark_manual_edit:
        normalized["manually_edited"] = True
    status = _as_str(normalized.get("status")) or "draft"
    if status not in ("draft", "approved", "empty", "needs_refresh", ""):
        status = "draft"
    # Üres tartalom soha ne maradjon approved.
    try:
        from sermon_workshop_outline_ai import outline_has_content, sync_outline_content

        # Content: csak ha üres, töltsük a struktúrából — kézi content ne vesszen el.
        if not _as_str(normalized.get("content")):
            normalized = sync_outline_content(normalized, force=True)
        if not outline_has_content(normalized):
            if status == "approved":
                status = "draft"
                normalized["needs_rebuild"] = True
        else:
            normalized["needs_rebuild"] = False
    except Exception as exc:  # pragma: no cover
        _log_swallowed_exception("save_sermon_outline.content_sync", exc)
    normalized["status"] = status or "draft"
    sw["sermon_outline"] = normalized
    sw["sermon_outline_status"] = normalized["status"]
    sw["sermon_outline_generated_at"] = _as_str(normalized.get("generated_at"))
    sw["sermon_outline_updated_at"] = now
    # Kanonikus szöveg tükrözése a legacy session kulcsokra (Word-export / gyorsnézet).
    try:
        from sermon_outline_engine import mirror_outline_to_session_strings

        mirror_outline_to_session_strings(session_state, normalized)
    except Exception as exc:  # pragma: no cover
        _log_swallowed_exception("save_sermon_outline.mirror_to_session", exc)
        body = _as_str(normalized.get("content"))
        if body:
            session_state["outline"] = body
            session_state["outline_draft"] = body
    return sw


def save_sermon_outline_diagnostics(
    session_state: MutableMapping[str, Any],
    payload: dict[str, Any],
    *,
    stamp_generated_at: bool = True,
) -> dict[str, Any]:
    """Vázlatdiagnosztika mentése — nem módosítja a vázlatot / műhelymezőket."""
    sw = ensure_sermon_workshop_state(session_state)
    normalized = normalize_sermon_outline_diagnostics(payload)
    # Üres payload soha ne törölje a korábbi érvényes diagnózist.
    if not _diagnostics_has_result(normalized) and _diagnostics_has_result(
        sw.get("sermon_outline_diagnostics")
    ):
        return sw
    sw["sermon_outline_diagnostics"] = normalized
    if stamp_generated_at:
        sw["sermon_outline_diagnostics_generated_at"] = datetime.now().isoformat(
            timespec="seconds"
        )
    sw["sermon_outline_diagnostics_status"] = "ready"
    sw["sermon_outline_diagnostics_error"] = ""
    return sw


def set_sermon_outline_diagnostics_status(
    session_state: MutableMapping[str, Any],
    status: str,
    *,
    error_message: str = "",
) -> dict[str, Any]:
    """Diagnosztika futási / hibastátusz — a meglévő eredményt nem törli."""
    sw = ensure_sermon_workshop_state(session_state)
    normalized = _normalize_diag_status(status)
    sw["sermon_outline_diagnostics_status"] = normalized
    if normalized == "error":
        sw["sermon_outline_diagnostics_error"] = _as_str(error_message)
    elif normalized in ("idle", "running", "ready"):
        sw["sermon_outline_diagnostics_error"] = ""
    return sw


# =============================================================================
# ÚJ, ADDITÍV: "Az igehirdetés íve" egységesített hétpontos adatmodell.
#
# Célarchitektúra-terv (TEXTUS_EGYSZERUSITETT_IGEHIRDETESI_CELARCHITEKTURA_
# TERV_2026-08-13.md), 1. fázis. FONTOS KORLÁTOK ERRE A FÁZISRA:
#   - kizárólag adatmodell + tiszta, tesztelhető migrációs/frissítő függvény;
#   - NEM aktív source of truth — sem a jelenlegi öt munkafázisos UI, sem a
#     vázlatmotor (sermon_outline_engine.generate_sermon_outline) nem olvassa;
#   - a régi mezők (entry_point, sermon_path, christ_centered_arc, closing,
#     human_condition, listener_tension, engagement_elements) TELJESEN
#     ÉRINTETLENEK maradnak, továbbra is ők az aktív rendszer forrásai;
#   - a migrációs függvénynek NINCS automatikus UI- vagy projektbetöltési
#     hívása ebben a fázisban — csak tesztekből/később, explicit hívással.
# =============================================================================

_ARC_POINT_KEYS: tuple[str, ...] = (
    "entry",  # 1. Belépés
    "starting_point",  # 2. Alaphelyzet
    "first_shift",  # 3. Első fordulópont
    "deepening",  # 4. Mélyítés és fokozás
    "reinterpretation",  # 5. Átértelmezés — opcionális
    "second_shift",  # 6. Második fordulópont
    "arrival",  # 7. Megérkezés
)

# RESET 2D-B1: a célzott, elfogadásos MI-pontosítás kilenc egymástól
# teljesen független célmezője — a két főgondolat plusz mind a hét
# arc-pont. Az arc-pont kulcsokat innen, a `_ARC_POINT_KEYS`-ből veszi át
# (nem duplikálja), hogy a kulcsidentitás egyetlen forrásból származzon.
_REFINEMENT_FIELD_KEYS: tuple[str, ...] = ("text_main_idea", "sermon_main_idea") + _ARC_POINT_KEYS

_ARC_POINT_FIELDS: tuple[str, ...] = (
    "text",
    "ai_suggestion",
    "ai_suggested_at",
    "context_hash",
    "updated_at",
)


def empty_arc_point() -> dict[str, Any]:
    """Egy üres "Az igehirdetés íve" modellpont — mindegyik pont ugyanezt a
    sémát használja: 1 szerkeszthető mező + 1 MI-javaslat mező + auto-save
    metaadat. Nincs `status` (draft/approved) mező — a kapu (későbbi fázis)
    tartalom+frissesség alapú lesz, nem jóváhagyás-alapú.

    RESET 2A (2026-08-18, adatmodell-fázis): a termékkövetelmény szerint a
    hét pont mindegyikéhez NEM lesz külön, pontonkénti MI-javaslat — a
    javaslatkészítés a két különálló "központi irány" mezőhöz (textus fő
    gondolata / igehirdetés fő gondolata-fókuszmondat, ld. `sermon_main_idea`
    itt és `text_main_idea` a `textus_workshop_data.py`-ban) tartozik, NEM
    az `arc` pontjaihoz. Az `ai_suggestion`/`ai_suggested_at` mezők ezért a
    ÚJ folyamatban nem kerülnek kitöltésre — a séma NEM törlődik
    (visszafelé-kompatibilitás, nincs destruktív migráció), csak a UI/MI
    réteg nem épít rájuk a jövőben."""
    return {
        "text": "",
        "ai_suggestion": None,
        "ai_suggested_at": "",
        "context_hash": "",
        "updated_at": "",
    }


def get_default_arc() -> dict[str, Any]:
    """Üres, hét pontból álló `arc` struktúra."""
    return {key: empty_arc_point() for key in _ARC_POINT_KEYS}


_ARC_META_FIELDS: tuple[str, ...] = (
    "reference",
    "context_hash",
    "generated_at",
    "manually_updated_at",
)


def empty_arc_meta() -> dict[str, Any]:
    """RESET 2A: a kanonikus `arc` (NEM egy adott pont) frissesség- és
    eredet-metaadata. Szándékosan KÜLÖN, top-level `sermon_workshop.
    arc_meta` mező — nem egy arc-pont `context_hash`-ébe van elrejtve,
    mert ez a hét pontra EGYÜTTESEN, nem pontonként vonatkozó infó."""
    return {
        "reference": "",
        "context_hash": "",
        "generated_at": "",
        "manually_updated_at": "",
    }


def normalize_arc_meta(raw: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `arc_meta` struktúrát ad vissza —
    hiányzó/hibás bemenet esetén biztonságos alapérték. Idempotens:
    `normalize_arc_meta(normalize_arc_meta(x)) == normalize_arc_meta(x)`,
    mert minden mező egyszerű, önmagán stabil string-konverzión megy át."""
    base = empty_arc_meta()
    if not isinstance(raw, dict):
        return base
    return {key: _as_str(raw.get(key)) for key in _ARC_META_FIELDS}


def normalize_arc_candidate(raw: Any) -> dict[str, Any] | None:
    """RESET 2A: a biztonságos újragenerálás előnézeti tárolója.

    `None`, ha nincs függőben lévő candidate (ez a választott szerződés
    "üres állapota" — nincs külön szentinel-dict, a hiány maga `None`).

    Érvényes candidate esetén EGYÉRTELMŰ, metaadattal ellátott szerkezetet
    ad vissza — sosem puszta hétpontos dictet:
      - `points`: a hét normalizált arc-pont (`normalize_arc` szabályai);
      - `reference`, `context_hash`, `generated_at`: string metaadat.

    Biztonságos hibakezelés: ha a bemenet nem dict, VAGY a `points` mező
    hiányzik / nem dict (tehát szerkezetileg nem candidate), a teljes
    bemenetet érvénytelennek tekinti és `None`-t ad vissza — így egy
    sérült candidate sosem viselkedhet érvényesként, és sosem írhatja
    felül a kanonikus `arc`-ot (az elfogadás előfeltétele pont ez a
    sikeres normalizálás, ld. `accept_arc_candidate`). Hiányos, de
    szerkezetileg ép bemenetnél (van `points` dict, de pl. a `reference`
    hiányzik) a hiányzó metaadat egyszerűen üres string lesz — ez nem
    tekinthető sérültnek, csak hiányosnak."""
    if not isinstance(raw, dict):
        return None
    points_raw = raw.get("points")
    if not isinstance(points_raw, dict):
        return None
    return {
        "points": normalize_arc(points_raw),
        "reference": _as_str(raw.get("reference")),
        "context_hash": _as_str(raw.get("context_hash")),
        "generated_at": _as_str(raw.get("generated_at")),
    }


def arc_has_content(arc: Any) -> bool:
    """True, ha a (bármilyen bemenetből normalizált) kanonikus `arc`
    legalább egy pontjának `text` mezője nem üres. Tiszta, session-
    független segédfüggvény — nem hív AI-t, nem módosít semmit."""
    normalized = normalize_arc(arc)
    return any(_as_str(point.get("text")).strip() for point in normalized.values())


def _arc_candidate_matches_context(
    candidate: Mapping[str, Any], *, reference: str, context_hash: str
) -> bool:
    """True, ha egy már normalizált candidate `reference`/`context_hash`
    párja PONTOSAN megegyezik az aktuálisan átadott értékekkel — ez az
    egyetlen alapja annak, hogy egy candidate elfogadható-e.

    Üres kontextusazonosító SOSEM tekinthető érvényes egyezésnek — sem a
    candidate, sem az aktuálisan átadott oldal nem lehet üres, még akkor
    sem, ha mindkettő ÜGYANÚGY üres. (Az `accept_arc_candidate()` ugyanezt
    a szabályt implementálja, de a konkrét elutasítási OK — reference
    vs. context_hash vs. hiányzó azonosító — megkülönböztetése miatt ott
    közvetlenül, nem ezen a segédfüggvényen keresztül; ez a függvény
    olyan hívóknak való, akiknek csak az igen/nem eldöntés kell.)"""
    candidate_reference = _as_str(candidate.get("reference"))
    candidate_context_hash = _as_str(candidate.get("context_hash"))
    current_reference = _as_str(reference)
    current_context_hash = _as_str(context_hash)
    if (
        not candidate_reference.strip()
        or not candidate_context_hash.strip()
        or not current_reference.strip()
        or not current_context_hash.strip()
    ):
        return False
    return (
        candidate_reference == current_reference
        and candidate_context_hash == current_context_hash
    )


def set_arc_candidate(
    session_state: MutableMapping[str, Any],
    *,
    points: Any,
    reference: str,
    context_hash: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """A megadott hétpontos eredményt candidate-ként tárolja el —
    a kanonikus `arc`-hoz és `arc_meta`-hoz NEM nyúl. Egy új hívás mindig
    felülírja az esetlegesen már ott lévő korábbi candidate-et (egy új
    generálás a legutóbbi javaslatot tükrözi). Nem indít AI-hívást — csak
    egy már meglévő, kész eredményt tárol el.

    DÖNTÉS (szűk korrekció, 2026-08-18): ez a függvény (és a rajta
    keresztül hívó `store_generated_arc_result` candidate-ága) SZÁNDÉKOSAN
    NEM utasítja el az üres `reference`/`context_hash` értéket íráskor —
    ez a modul meglévő konvenciója (a `normalize_*` függvények mindenütt
    biztonságosan default-olnak íráskor/normalizáláskor, sosem dobnak
    kivételt hiányos metaadatra; a SZIGORÚ kapu mindig a felhasználásnál,
    itt az elfogadásnál van). Egy üres kontextusú candidate ETTŐL
    FÜGGETLENÜL SOSEM fogadható el — ld. `accept_arc_candidate()`, ami
    külön, explicit `"missing_context_identity"` okkal utasítja el. Ez a
    kettő együtt biztosítja, hogy hiányos kontextusú candidate sosem
    írhatja felül a kanonikus arc-ot, anélkül hogy a tárolást magát
    feleslegesen szigorítanánk."""
    sw = ensure_sermon_workshop_state(session_state)
    stamp = _as_str(generated_at) or datetime.now().isoformat(timespec="seconds")
    candidate = {
        "points": normalize_arc(points),
        "reference": _as_str(reference),
        "context_hash": _as_str(context_hash),
        "generated_at": stamp,
    }
    sw["arc_candidate"] = candidate
    return candidate


def discard_arc_candidate(session_state: MutableMapping[str, Any]) -> None:
    """A függőben lévő candidate elvetése. KIZÁRÓLAG az `arc_candidate`-et
    törli (`None`-ra állítja) — a kanonikus `arc` és `arc_meta`
    BIT-PONTOSAN változatlan marad. Nem indít AI-hívást."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["arc_candidate"] = None


def store_generated_arc_result(
    session_state: MutableMapping[str, Any],
    *,
    points: Any,
    reference: str,
    context_hash: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Egyetlen belépési pont egy frissen elkészült hétpontos eredmény
    biztonságos tárolásához — az "első generálás vs. újragenerálás"
    döntési szabály itt dől el.

    Döntés:
      - ha a kanonikus `arc` mind a hét pontja üres (`arc_has_content`
        hamis) -> az eredmény KÖZVETLENÜL az `arc`-ba kerül, az
        `arc_meta.reference`/`context_hash`/`generated_at` frissül, a
        visszatérési érték `{"status": "applied", ...}`;
      - egyébként (legalább egy pont nem üres) -> az `arc` egyetlen
        pontja SEM módosul; az eredmény a `set_arc_candidate()`-tel az
        `arc_candidate`-be kerül, a visszatérési érték
        `{"status": "candidate", ...}`.

    `arc_meta.manually_updated_at` szemantikája (szűk korrekció,
    2026-08-18): ez a mező KIZÁRÓLAG a JELENLEGI kanonikus `arc` utolsó
    KÉZI szerkesztésére vonatkozik. Egy közvetlen (üres arc-ra történő)
    alkalmazás nem kézi szerkesztés — az itt frissülő `arc` tartalma
    teljes egészében a generált eredmény, semmi kézi nincs benne, ezért
    az `manually_updated_at` itt mindig ÜRESRE áll (nem őrzi meg egy
    korábbi, MÁR LECSERÉLT arc kézi-szerkesztési időpontját).

    Sosem ír felül meglévő, kézzel vagy korábban elfogadott arc-tartalmat
    automatikusan. Nem indít AI-hívást — csak egy már meglévő, kész
    eredményt tárol el a fenti szabály szerint."""
    sw = ensure_sermon_workshop_state(session_state)
    stamp = _as_str(generated_at) or datetime.now().isoformat(timespec="seconds")
    normalized_points = normalize_arc(points)

    if not arc_has_content(sw.get("arc")):
        sw["arc"] = normalized_points
        sw["arc_meta"] = normalize_arc_meta(
            {
                "reference": reference,
                "context_hash": context_hash,
                "generated_at": stamp,
                "manually_updated_at": "",
            }
        )
        return {"status": "applied", "arc": sw["arc"], "arc_meta": sw["arc_meta"]}

    candidate = set_arc_candidate(
        session_state,
        points=normalized_points,
        reference=reference,
        context_hash=context_hash,
        generated_at=stamp,
    )
    return {"status": "candidate", "arc_candidate": candidate}


def accept_arc_candidate(
    session_state: MutableMapping[str, Any],
    *,
    reference: str,
    context_hash: str,
) -> dict[str, Any]:
    """A függőben lévő candidate elfogadása — "Lecserélem erre".

    KIZÁRÓLAG akkor fogadja el, ha:
      - van függőben lévő, szerkezetileg ép candidate (`normalize_arc_
        candidate` nem ad vissza `None`-t — ez már önmagában bizonyítja,
        hogy mind a hét pont érvényesen normalizálható);
      - a candidate `reference` értéke pontosan megegyezik az itt átadott
        `reference`-szel;
      - a candidate `context_hash` értéke pontosan megegyezik az itt
        átadott `context_hash`-sel.

    Sikeres elfogadáskor a candidate hét pontja kerül a kanonikus `arc`-ba,
    az `arc_meta` frissül a candidate saját reference/context_hash/
    generated_at adataival, az `arc_candidate` kiürül (`None`). Nem indít
    AI-hívást.

    `manually_updated_at` szemantikája (szűk korrekció, 2026-08-18): a
    candidate elfogadása a kanonikus `arc` TELJES tartalomcseréje — az
    elfogadott hét pont a candidate-ből származik, nem kézi szerkesztés.
    Ezért az elfogadás után az `arc_meta.manually_updated_at` mindig
    ÜRESRE áll, akkor is, ha a LECSERÉLT arc-ot korábban kézzel
    szerkesztették — az az időpont a MOST lecserélt tartalomra
    vonatkozott, a candidate tartalmára nem érvényes.

    Üres kontextusazonosítót SOSEM tekint érvényes egyezésnek — sem a
    candidate, sem az itt átadott `reference`/`context_hash` nem lehet
    üres, akkor sem, ha mindkét oldal ÜGYANÚGY üres (két hiányzó azonosító
    "egyezése" véletlen, nem valódi kontextus-igazolás).

    Sikertelen esetben (nincs candidate / sérült candidate / hiányzó
    kontextusazonosító bármelyik oldalon / eltérő reference / eltérő
    context_hash) a kanonikus `arc` és `arc_meta` BIT-PONTOSAN változatlan
    marad, és a visszatérési érték `reason` mezője jelzi az elutasítás
    pontos okát: `"no_candidate"`, `"invalid_candidate"`,
    `"missing_context_identity"`, `"reference_mismatch"` vagy
    `"context_hash_mismatch"`."""
    sw = ensure_sermon_workshop_state(session_state)
    raw_candidate = sw.get("arc_candidate")
    if raw_candidate is None:
        return {"accepted": False, "reason": "no_candidate"}

    candidate = normalize_arc_candidate(raw_candidate)
    if candidate is None:
        return {"accepted": False, "reason": "invalid_candidate"}

    candidate_reference = _as_str(candidate["reference"])
    candidate_context_hash = _as_str(candidate["context_hash"])
    current_reference = _as_str(reference)
    current_context_hash = _as_str(context_hash)
    if (
        not candidate_reference.strip()
        or not candidate_context_hash.strip()
        or not current_reference.strip()
        or not current_context_hash.strip()
    ):
        return {"accepted": False, "reason": "missing_context_identity"}

    if candidate_reference != current_reference:
        return {"accepted": False, "reason": "reference_mismatch"}
    if candidate_context_hash != current_context_hash:
        return {"accepted": False, "reason": "context_hash_mismatch"}

    sw["arc"] = candidate["points"]
    sw["arc_meta"] = normalize_arc_meta(
        {
            "reference": candidate["reference"],
            "context_hash": candidate["context_hash"],
            "generated_at": candidate["generated_at"],
            "manually_updated_at": "",
        }
    )
    sw["arc_candidate"] = None
    return {"accepted": True, "reason": "", "arc": sw["arc"], "arc_meta": sw["arc_meta"]}


# =============================================================================
# RESET 2D-B1: célzott, elfogadásos MI-pontosítás — kilenc egymástól
# teljesen független, függőben lévő javaslat-tároló (két főgondolat +
# hét arc-pont). Additív mező, nem az `arc`/`arc_meta`/`arc_candidate`
# séma része — attól teljesen külön, saját `field_refinements` kulcs
# alatt. Legacy projekteknél hiányzó/sérült adat esetén biztonságosan
# az összes célmezőre `None`-ra esik vissza (ugyanaz a védekező minta,
# mint `normalize_arc_candidate`-nél).
# =============================================================================


def get_default_field_refinements() -> dict[str, Any]:
    """Kilenc célmező, mindegyik `None` — nincs függőben lévő javaslat."""
    return {key: None for key in _REFINEMENT_FIELD_KEYS}


def _normalize_field_refinement_entry(raw: Any) -> dict[str, str] | None:
    """Biztonságos normalizálás egyetlen célmező javaslatára — sérült,
    hiányzó vagy üres szövegű bemenet esetén `None` (nincs érvényes
    javaslat), sosem dob kivételt."""
    if not isinstance(raw, dict):
        return None
    text = _as_str(raw.get("text")).strip()
    if not text:
        return None
    return {
        "text": text,
        "instruction": _as_str(raw.get("instruction")),
        "reference": _as_str(raw.get("reference")),
        "context_hash": _as_str(raw.get("context_hash")),
        "generated_at": _as_str(raw.get("generated_at")),
    }


def normalize_field_refinements(raw: Any) -> dict[str, dict[str, str] | None]:
    """Bármilyen bemenetből érvényes, pontosan a kilenc célmezőt lefedő
    struktúrát ad vissza — ismeretlen kulcsok kimaradnak, hiányzó/sérült
    mezők biztonságosan `None`-ra esnek (`normalize_arc_candidate`
    mintáját követve)."""
    base = get_default_field_refinements()
    if not isinstance(raw, dict):
        return base
    return {
        key: _normalize_field_refinement_entry(raw.get(key))
        for key in _REFINEMENT_FIELD_KEYS
    }


def set_field_refinement_suggestion(
    session_state: MutableMapping[str, Any],
    field_key: str,
    *,
    text: str,
    instruction: str = "",
    reference: str,
    context_hash: str,
    generated_at: str | None = None,
) -> dict[str, str]:
    """Egy adott célmezőhöz tartozó, frissen elkészült javaslat tárolása.
    KIZÁRÓLAG a megadott `field_key` bejegyzését írja — a másik nyolc
    célmező függőben lévő javaslata (ha van) érintetlen marad. Nem indít
    AI-hívást, csak egy már kész eredményt tárol el."""
    if field_key not in _REFINEMENT_FIELD_KEYS:
        raise ValueError(f"Ismeretlen pontosítási célmező: {field_key!r}")
    sw = ensure_sermon_workshop_state(session_state)
    stamp = _as_str(generated_at) or datetime.now().isoformat(timespec="seconds")
    entry = _normalize_field_refinement_entry(
        {
            "text": text,
            "instruction": instruction,
            "reference": reference,
            "context_hash": context_hash,
            "generated_at": stamp,
        }
    )
    if entry is None:
        raise ValueError("Üres javaslat szöveg nem tárolható.")
    refinements = sw.get("field_refinements")
    refinements = (
        dict(refinements) if isinstance(refinements, dict) else get_default_field_refinements()
    )
    refinements[field_key] = entry
    sw["field_refinements"] = refinements
    return entry


def discard_field_refinement_suggestion(
    session_state: MutableMapping[str, Any], field_key: str
) -> None:
    """A megadott célmező függőben lévő javaslatának elvetése. KIZÁRÓLAG
    azt az egy bejegyzést törli — a kanonikus mező és a többi nyolc
    célmező javaslata BIT-PONTOSAN változatlan marad. Nem indít AI-hívást."""
    if field_key not in _REFINEMENT_FIELD_KEYS:
        raise ValueError(f"Ismeretlen pontosítási célmező: {field_key!r}")
    sw = ensure_sermon_workshop_state(session_state)
    refinements = sw.get("field_refinements")
    refinements = (
        dict(refinements) if isinstance(refinements, dict) else get_default_field_refinements()
    )
    refinements[field_key] = None
    sw["field_refinements"] = refinements


def validate_field_refinement_acceptance(
    session_state: MutableMapping[str, Any],
    field_key: str,
    *,
    reference: str,
    context_hash: str,
) -> dict[str, Any]:
    """Elfogadás ELŐFELTÉTEL-ellenőrzése — NEM módosít semmilyen kanonikus
    mezőt; a tényleges írást a hívó (UI) végzi a megfelelő, meglévő
    mentési útvonalon (`update_arc_point` / `update_text_main_idea` /
    `update_sermon_workshop_section`), és csak SIKERES ellenőrzés után.

    KIZÁRÓLAG akkor `valid: True`, ha van függőben lévő, szerkezetileg ép
    javaslat, ÉS annak `reference`/`context_hash` párja pontosan
    megegyezik az itt átadott, aktuális értékekkel. Üres azonosító —
    akár a javaslat, akár az aktuális oldal — SOSEM tekinthető érvényes
    egyezésnek, még akkor sem, ha mindkét oldal ugyanúgy üres.

    Sikertelen esetben a `reason` jelzi a pontos okot: `"no_suggestion"`,
    `"invalid_suggestion"`, `"missing_context_identity"`,
    `"reference_mismatch"` vagy `"context_hash_mismatch"`."""
    if field_key not in _REFINEMENT_FIELD_KEYS:
        raise ValueError(f"Ismeretlen pontosítási célmező: {field_key!r}")
    sw = ensure_sermon_workshop_state(session_state)
    refinements = sw.get("field_refinements")
    raw = refinements.get(field_key) if isinstance(refinements, dict) else None
    if raw is None:
        return {"valid": False, "reason": "no_suggestion"}

    entry = _normalize_field_refinement_entry(raw)
    if entry is None:
        return {"valid": False, "reason": "invalid_suggestion"}

    s_ref = entry["reference"].strip()
    s_hash = entry["context_hash"].strip()
    c_ref = _as_str(reference).strip()
    c_hash = _as_str(context_hash).strip()
    if not s_ref or not s_hash or not c_ref or not c_hash:
        return {"valid": False, "reason": "missing_context_identity"}
    if s_ref != c_ref:
        return {"valid": False, "reason": "reference_mismatch"}
    if s_hash != c_hash:
        return {"valid": False, "reason": "context_hash_mismatch"}
    return {"valid": True, "reason": "", "text": entry["text"]}


def _normalize_arc_point(raw: Any) -> dict[str, Any]:
    base = empty_arc_point()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    out["text"] = _as_str(raw.get("text"))
    suggestion = raw.get("ai_suggestion")
    out["ai_suggestion"] = (
        str(suggestion) if isinstance(suggestion, str) and suggestion.strip() else None
    )
    out["ai_suggested_at"] = _as_str(raw.get("ai_suggested_at"))
    out["context_hash"] = _as_str(raw.get("context_hash"))
    out["updated_at"] = _as_str(raw.get("updated_at"))
    return out


def normalize_arc(raw: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes, pontosan hét pontból álló `arc`
    struktúrát ad vissza — hiányzó/hibás bemenet esetén biztonságos
    alapérték, adatvesztés nélkül (ismeretlen pontkulcsok egyszerűen nem
    kerülnek be, ismert pontok hiánya alapértékkel pótlódik)."""
    base = get_default_arc()
    if not isinstance(raw, dict):
        return base
    return {key: _normalize_arc_point(raw.get(key)) for key in _ARC_POINT_KEYS}


# =============================================================================
# RESET 2E-1 (2026-08-20): kétlépcsős vázlatmotor ADATMODELLJE — belső
# homiletikai `blueprint` + felhasználónak szánt `developed_outline`.
#
# Ebben a fázisban KIZÁRÓLAG adatmodell: nincs AI-hívás, nincs prompt,
# nincs UI, és a meglévő `arc` generálás VÁLTOZATLAN. A mezők additívak,
# a régi projektek biztonságos alapértéket kapnak (ugyanaz a védekező
# minta, mint `arc_candidate`/`field_refinements`-nél).
#
# A két réteg SZÁNDÉKOSAN külön:
#   - `blueprint`: teljesen BELSŐ artefaktum. Sosem jelenik meg a
#     felületen, a felhasználó sosem szerkeszti. Ezért NINCS
#     `blueprint_candidate` — a candidate egyetlen létező szerepe ebben a
#     kódbázisban (`arc_candidate`, `field_refinements`) a FELHASZNÁLÓ
#     saját tartalmának védelme a néma felülírástól; belső, sosem
#     szerkesztett artefaktumnál ez a szerep nem értelmezhető. A
#     biztonságot ugyanaz a "csak validált eredmény íródik ki" szabály
#     adja, amit a hétpontos motor is használ.
#   - `developed_outline`: a felhasználónak szánt, később SZERKESZTHETŐ
#     tartalom, ezért KÖTELEZŐEN candidate/accept/discard életciklussal.
#     Az elfogadás/elutasítás szerződése (szigorú reference+context_hash
#     egyezés, `reason`-kódok) az `accept_arc_candidate` bevált mintáját
#     követi, EGY SZÁNDÉKOS ELTÉRÉSSEL (RESET 2E-1A): itt MINDEN
#     generálás candidate-et hoz létre — az ELSŐ is —, sosem alkalmazódik
#     automatikusan. Ld. `store_generated_developed_outline_result`.
#
# A legacy `sermon_outline` egy MÁSIK, régi workflow mezője: sem oda-,
# sem visszafelé NEM migrálódik, és a jelentése változatlan marad.
# =============================================================================

_BLUEPRINT_TEXT_FIELDS: tuple[str, ...] = (
    "central_claim",
    "textual_center",
    "listener_tension",
    "theological_turn",
    "desired_listener_movement",
    "illustration_direction",
    "application_direction",
)

_BLUEPRINT_ARC_FIT_FIELDS: tuple[str, ...] = ("verdict", "reason")

_BLUEPRINT_SUPPORT_KEYS: tuple[str, ...] = (
    "exegetical",
    "original_language",
    "historical_theological",
)

_BLUEPRINT_MOVEMENT_TEXT_FIELDS: tuple[str, ...] = ("key", "function", "core_idea")

# Védekező felső korlát: a hétpontos modell 7 mozgása mellett az adaptív
# (összevont/rövidebb/custom) szerkezetnek is kényelmesen elég, de egy
# sérült vagy elszabadult bemenet nem növelheti korlátlanul a state-et.
_STRUCTURE_MOVEMENTS_MAX = 12


def empty_blueprint() -> dict[str, Any]:
    """Üres belső homiletikai blueprint — a kétlépcsős vázlatmotor első
    lépcsőjének (RESET 2E-0 terv) tárolója.

    A mezők jelentése röviden: `central_claim` a prédikáció egyetlen
    mondatos fő állítása; `textual_center` a textus saját, szöveghű
    központi mozgása; `listener_tension` a hallgató felőli kérdés;
    `theological_turn` a felismerés fordulópontja; `desired_listener_
    movement` a hallgató honnan-hová útja; `arc_fit` a hétpontos
    modellhez való illeszkedés ÉRTÉKELÉSE (a döntési logika NEM ebben a
    fázisban készül, itt csak tárolható); `recommended_structure` a
    javasolt mozgásszerkezet; `key_support` a ténylegesen releváns
    alátámasztás három forráscsoportból; `warnings` a feloldatlan
    feszültségek/ellentmondások (pl. a felhasználó szövege és az
    exegézis ütközése) — ez SOSEM néma felülírás, hanem jelzés."""
    return {
        **{key: "" for key in _BLUEPRINT_TEXT_FIELDS},
        "arc_fit": {key: "" for key in _BLUEPRINT_ARC_FIT_FIELDS},
        "recommended_structure": {"mode": "", "movements": []},
        "key_support": {key: [] for key in _BLUEPRINT_SUPPORT_KEYS},
        "warnings": [],
    }


def _normalize_structure_movement(raw: Any) -> dict[str, Any]:
    """Egy javasolt mozgás normalizálása a blueprintben. Hiányos bemenet
    NEM kerül eldobásra — a hiányzó mezők üres alapértéket kapnak, hogy a
    részleges modellválasz se okozzon adatvesztést.

    `key` szándékosan SZABAD string: lehet kanonikus hétpontos kulcs
    (`entry`…`arrival`) vagy adaptív/custom azonosító — a validálását
    (és bármilyen `strong_fit`/`partial_fit`/`weak_fit` döntést) egy
    későbbi AI-fázis végzi, az adatmodell csak biztonságosan tárolja."""
    base: dict[str, Any] = {key: "" for key in _BLUEPRINT_MOVEMENT_TEXT_FIELDS}
    base["grounded_in"] = []
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in _BLUEPRINT_MOVEMENT_TEXT_FIELDS:
        out[key] = _as_str(raw.get(key))
    out["grounded_in"] = _normalize_str_list(raw.get("grounded_in"))
    return out


def _normalize_structure_movements(raw: Any) -> list[dict[str, Any]]:
    """Mozgáslista normalizálása — nem-dict elemek kimaradnak, a többi
    hiányos elem alapértékkel egészül ki (nincs adatvesztés)."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(_normalize_structure_movement(item))
        if len(out) >= _STRUCTURE_MOVEMENTS_MAX:
            break
    return out


def normalize_blueprint(raw: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `blueprint` struktúrát ad vissza.

    Védett a hiányzó kulcsok, `None`, hibás scalar/list/dict típus,
    részleges mozgás és ismeretlen extra kulcs ellen — de szándékosan NEM
    agresszív: a meglévő, értelmezhető felhasználói/AI-tartalmat sosem
    dobja el csak azért, mert egy opcionális mező hiányzik. Idempotens."""
    base = empty_blueprint()
    if not isinstance(raw, dict):
        return base

    arc_fit_raw = raw.get("arc_fit")
    arc_fit = {key: "" for key in _BLUEPRINT_ARC_FIT_FIELDS}
    if isinstance(arc_fit_raw, dict):
        arc_fit = {key: _as_str(arc_fit_raw.get(key)) for key in _BLUEPRINT_ARC_FIT_FIELDS}

    structure_raw = raw.get("recommended_structure")
    structure: dict[str, Any] = {"mode": "", "movements": []}
    if isinstance(structure_raw, dict):
        structure = {
            "mode": _as_str(structure_raw.get("mode")),
            "movements": _normalize_structure_movements(structure_raw.get("movements")),
        }

    support_raw = raw.get("key_support")
    support = {key: [] for key in _BLUEPRINT_SUPPORT_KEYS}
    if isinstance(support_raw, dict):
        support = {
            key: _normalize_str_list(support_raw.get(key))
            for key in _BLUEPRINT_SUPPORT_KEYS
        }

    return {
        **{key: _as_str(raw.get(key)) for key in _BLUEPRINT_TEXT_FIELDS},
        "arc_fit": arc_fit,
        "recommended_structure": structure,
        "key_support": support,
        "warnings": _normalize_str_list(raw.get("warnings")),
    }


_BLUEPRINT_META_FIELDS: tuple[str, ...] = ("context_hash", "generated_at")


def empty_blueprint_meta() -> dict[str, Any]:
    """A `blueprint` frissesség-/eredet-metaadata.

    Szándékosan MINIMÁLIS: nincs `manually_updated_at`, mert a blueprint
    belső artefaktum, amit a felhasználó sosem szerkeszt kézzel. A
    `context_hash` KÉSŐBB annak eldöntésére szolgál, hogy a blueprint
    bemeneti kontextusa megváltozott-e — a tényleges kontextus-építő és
    bármilyen staleness-jelzés egy későbbi fázis feladata, ez a mező most
    csak tárolható és normalizált."""
    return {key: "" for key in _BLUEPRINT_META_FIELDS}


def normalize_blueprint_meta(raw: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `blueprint_meta`-t ad vissza —
    ugyanaz az egyszerű, idempotens string-konverziós minta, mint
    `normalize_arc_meta`-nál."""
    base = empty_blueprint_meta()
    if not isinstance(raw, dict):
        return base
    return {key: _as_str(raw.get(key)) for key in _BLUEPRINT_META_FIELDS}


def store_generated_blueprint_result(
    session_state: MutableMapping[str, Any],
    *,
    blueprint: Any,
    context_hash: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """RESET 2E-2: egy frissen elkészült, MÁR VALIDÁLT blueprint tárolása.

    A blueprintnek NINCS candidate életciklusa (ld. a RESET 2E-1 blokk
    indoklását): belső artefaktum, amit a felhasználó sosem szerkeszt,
    ezért nincs mit védeni néma felülírástól. A biztonságot az adja, hogy
    a hívó KIZÁRÓLAG sikeres szemantikai validálás után hívja meg ezt a
    függvényt — érvénytelen modellválasznál meg sem hívódik, így a
    korábbi kanonikus blueprint érintetlen marad.

    Nem indít AI-hívást — csak egy kész eredményt tárol el, és frissíti a
    `blueprint_meta.context_hash`/`generated_at` mezőt."""
    sw = ensure_sermon_workshop_state(session_state)
    stamp = _as_str(generated_at) or datetime.now().isoformat(timespec="seconds")
    sw["blueprint"] = normalize_blueprint(blueprint)
    sw["blueprint_meta"] = normalize_blueprint_meta(
        {"context_hash": context_hash, "generated_at": stamp}
    )
    return {"blueprint": sw["blueprint"], "blueprint_meta": sw["blueprint_meta"]}


_DEVELOPED_MOVEMENT_TEXT_FIELDS: tuple[str, ...] = (
    "key",
    "title",
    "function",
    "main_claim",
    "illustration_direction",
    "application_direction",
    "transition_to_next",
)

_DEVELOPED_MOVEMENT_LIST_FIELDS: tuple[str, ...] = (
    "development",
    "exegetical_support",
    "original_language_support",
    "historical_theological_support",
)

# Az egyetlen, kézzel is szerkeszthető mezőkészlet — a manual update
# helper KIZÁRÓLAG ezeket fogadja el célmezőként.
_DEVELOPED_MOVEMENT_FIELDS: tuple[str, ...] = (
    _DEVELOPED_MOVEMENT_TEXT_FIELDS + _DEVELOPED_MOVEMENT_LIST_FIELDS
)


def empty_developed_outline_movement() -> dict[str, Any]:
    """Egy mozgás a felhasználónak szánt, részletes vázlatban.

    A `development` és a három `*_support` mező LISTA, hogy 2-4 külön
    kibontási gondolat, illetve több önálló megfigyelés külön elemként
    legyen kezelhető (és később külön szerkeszthető) — nem egyetlen
    összefolyó szövegblokk. Tiszta domain-adat: NINCS benne HTML vagy
    bármilyen UI-formázás."""
    out: dict[str, Any] = {key: "" for key in _DEVELOPED_MOVEMENT_TEXT_FIELDS}
    for key in _DEVELOPED_MOVEMENT_LIST_FIELDS:
        out[key] = []
    return out


def normalize_developed_outline_movement(raw: Any) -> dict[str, Any]:
    """Egy vázlat-mozgás normalizálása. Részleges bemenet NEM vész el: a
    hiányzó mezők üres, de TÍPUSHELYES alapértéket kapnak (string vs.
    lista), így a hívóknak sosem kell típust ellenőrizniük."""
    base = empty_developed_outline_movement()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key in _DEVELOPED_MOVEMENT_TEXT_FIELDS:
        out[key] = _as_str(raw.get(key))
    for key in _DEVELOPED_MOVEMENT_LIST_FIELDS:
        out[key] = _normalize_str_list(raw.get(key))
    return out


def normalize_developed_outline_movements(raw: Any) -> list[dict[str, Any]]:
    """Vázlat-mozgások listájának normalizálása — nem-dict elemek
    kimaradnak, a hiányos elemek alapértékkel egészülnek ki."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(normalize_developed_outline_movement(item))
        if len(out) >= _STRUCTURE_MOVEMENTS_MAX:
            break
    return out


def empty_developed_outline() -> dict[str, Any]:
    """A felhasználónak szánt, részletes prédikációs munkavázlat.

    ADAPTÍV szerkezetű: a `movements` hossza NEM kötött hétre — a
    `structure_mode` (pl. teljes hétpontos / összevont / rövidebb egyedi)
    és a `structure_note` (rövid, emberi indoklás) írja le, milyen ívet
    használ. A tényleges döntési logikát egy későbbi AI-fázis hozza; itt
    csak biztonságos tárolás van.

    SZÁNDÉKOSAN külön a legacy `sermon_outline` mezőtől: az egy régi
    workflow más szerkezetű adata, a kettő között NINCS automatikus
    migráció egyik irányban sem."""
    return {
        "structure_mode": "",
        "structure_note": "",
        "movements": [],
    }


def normalize_developed_outline(raw: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `developed_outline`-t ad vissza —
    hiányzó/hibás bemenet esetén biztonságos alapérték, részleges
    bemenetnél adatvesztés nélkül. Idempotens."""
    base = empty_developed_outline()
    if not isinstance(raw, dict):
        return base
    return {
        "structure_mode": _as_str(raw.get("structure_mode")),
        "structure_note": _as_str(raw.get("structure_note")),
        "movements": normalize_developed_outline_movements(raw.get("movements")),
    }


def developed_outline_has_content(outline: Any) -> bool:
    """True, ha a (bármilyen bemenetből normalizált) vázlat legalább egy
    mozgásában van érdemi tartalom. Tiszta, session-független segéd —
    ugyanaz a szerep, mint `arc_has_content`-nél."""
    normalized = normalize_developed_outline(outline)
    for movement in normalized["movements"]:
        for key in _DEVELOPED_MOVEMENT_TEXT_FIELDS:
            if _as_str(movement.get(key)).strip():
                return True
        for key in _DEVELOPED_MOVEMENT_LIST_FIELDS:
            if any(str(item).strip() for item in movement.get(key) or []):
                return True
    return False


_DEVELOPED_OUTLINE_META_FIELDS: tuple[str, ...] = (
    "reference",
    "context_hash",
    "generated_at",
    "manually_updated_at",
)


def empty_developed_outline_meta() -> dict[str, Any]:
    """A `developed_outline`-ra EGYÜTTESEN vonatkozó frissesség-/eredet-
    metaadat — nem egy mozgás belseje (ugyanaz az elv, mint `arc_meta`).

    Mind a négy mező indokolt már V1-ben: a `reference` + `context_hash`
    pár az elfogadás előfeltétele (`accept_developed_outline_candidate`,
    az `accept_arc_candidate` bevált szerződése szerint — enélkül
    elveszne a `reference_mismatch` és a `context_hash_mismatch`
    megkülönböztetése); a `generated_at` az eredet; a
    `manually_updated_at` pedig azt védi, hogy egy kézzel szerkesztett
    vázlatot később ne lehessen némán felülírni."""
    return {key: "" for key in _DEVELOPED_OUTLINE_META_FIELDS}


def normalize_developed_outline_meta(raw: Any) -> dict[str, Any]:
    """Bármilyen bemenetből érvényes `developed_outline_meta`-t ad vissza."""
    base = empty_developed_outline_meta()
    if not isinstance(raw, dict):
        return base
    return {key: _as_str(raw.get(key)) for key in _DEVELOPED_OUTLINE_META_FIELDS}


def normalize_developed_outline_candidate(raw: Any) -> dict[str, Any] | None:
    """A biztonságos újragenerálás előnézeti tárolója a részletes
    vázlathoz — pontosan a `normalize_arc_candidate` szerződése szerint.

    `None`, ha nincs függőben lévő candidate (a hiány maga `None`, nincs
    külön szentinel-dict). Ha a bemenet nem dict, VAGY az `outline` mező
    hiányzik / nem dict (tehát szerkezetileg nem candidate), a teljes
    bemenet érvénytelen -> `None`; így egy sérült candidate sosem
    viselkedhet érvényesként, és sosem írhatja felül a kanonikus
    vázlatot. Hiányzó metaadat (pl. `reference`) csak HIÁNYOS, nem
    sérült: üres stringgé normalizálódik."""
    if not isinstance(raw, dict):
        return None
    outline_raw = raw.get("outline")
    if not isinstance(outline_raw, dict):
        return None
    return {
        "outline": normalize_developed_outline(outline_raw),
        "reference": _as_str(raw.get("reference")),
        "context_hash": _as_str(raw.get("context_hash")),
        "generated_at": _as_str(raw.get("generated_at")),
    }


def set_developed_outline_candidate(
    session_state: MutableMapping[str, Any],
    *,
    outline: Any,
    reference: str,
    context_hash: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """A megadott vázlat-eredményt candidate-ként tárolja — a kanonikus
    `developed_outline`-hoz és `developed_outline_meta`-hoz NEM nyúl. Egy
    új hívás mindig felülírja a korábbi candidate-et (egy új generálás a
    legutóbbi javaslatot tükrözi). Nem indít AI-hívást.

    Az üres `reference`/`context_hash` értéket — az `set_arc_candidate`
    meglévő konvenciója szerint — íráskor SZÁNDÉKOSAN nem utasítja el; a
    szigorú kapu mindig a FELHASZNÁLÁSNÁL, azaz az elfogadásnál van (ld.
    `accept_developed_outline_candidate`, `missing_context_identity`)."""
    sw = ensure_sermon_workshop_state(session_state)
    stamp = _as_str(generated_at) or datetime.now().isoformat(timespec="seconds")
    candidate = {
        "outline": normalize_developed_outline(outline),
        "reference": _as_str(reference),
        "context_hash": _as_str(context_hash),
        "generated_at": stamp,
    }
    sw["developed_outline_candidate"] = candidate
    return candidate


def discard_developed_outline_candidate(
    session_state: MutableMapping[str, Any],
) -> None:
    """A függőben lévő vázlat-candidate elvetése. KIZÁRÓLAG a
    `developed_outline_candidate`-et törli (`None`) — a kanonikus
    `developed_outline` és `developed_outline_meta` BIT-PONTOSAN
    változatlan marad. Nem indít AI-hívást."""
    sw = ensure_sermon_workshop_state(session_state)
    sw["developed_outline_candidate"] = None


def store_generated_developed_outline_result(
    session_state: MutableMapping[str, Any],
    *,
    outline: Any,
    reference: str,
    context_hash: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Egyetlen belépési pont egy frissen elkészült vázlat biztonságos
    tárolásához. Az eredmény MINDIG candidate lesz — az ELSŐ generálás is:

        generálás -> `developed_outline_candidate`
        explicit elfogadás -> `developed_outline`

    Ez a függvény tehát SOHA nem ír a kanonikus `developed_outline`
    mezőbe; azt kizárólag `accept_developed_outline_candidate()` teheti.
    Visszatérési érték mindig `{"status": "candidate", ...}`.

    RESET 2E-1A (2026-08-20) — SZÁNDÉKOS ELTÉRÉS a `store_generated_arc_
    result` mintájától: ott az üres `arc`-ra történő első generálás
    közvetlenül alkalmazódik ("applied"), itt viszont nem. Az ok
    tartalmi, nem technikai: a részletes vázlat FELHASZNÁLÓI artefaktum,
    és egy MI által készített vázlat első alkalommal is JAVASLAT, nem
    automatikusan elfogadott tartalom. A kanonikus `developed_outline`
    így kizárólag explicit felhasználói elfogadás nyomán jöhet létre —
    az üres kanonikus vázlat egyértelműen azt jelenti, hogy a felhasználó
    még semmit nem fogadott el.

    Sosem ír felül meglévő, kézzel szerkesztett vagy korábban elfogadott
    vázlatot. Nem indít AI-hívást — csak egy már kész eredményt tárol."""
    candidate = set_developed_outline_candidate(
        session_state,
        outline=outline,
        reference=reference,
        context_hash=context_hash,
        generated_at=generated_at,
    )
    return {"status": "candidate", "developed_outline_candidate": candidate}


def accept_developed_outline_candidate(
    session_state: MutableMapping[str, Any],
    *,
    reference: str,
    context_hash: str,
) -> dict[str, Any]:
    """A függőben lévő vázlat-candidate elfogadása — az
    `accept_arc_candidate` szerződésének pontos megfelelője.

    KIZÁRÓLAG akkor fogad el, ha van szerkezetileg ép candidate, ÉS annak
    `reference`/`context_hash` párja pontosan egyezik az itt átadott,
    aktuális értékekkel. Üres azonosító SOSEM érvényes egyezés, akkor sem,
    ha mindkét oldal ugyanúgy üres.

    Sikeres elfogadáskor a candidate tartalma lesz a kanonikus vázlat, a
    meta a candidate saját metaadataival frissül, és a
    `manually_updated_at` ÜRESRE áll (az elfogadott tartalom a
    candidate-ből származik, nem kézi szerkesztésből), a candidate pedig
    kiürül. Sikertelen esetben a kanonikus vázlat és meta BIT-PONTOSAN
    változatlan, a `reason` pedig jelzi az okot: `"no_candidate"`,
    `"invalid_candidate"`, `"missing_context_identity"`,
    `"reference_mismatch"` vagy `"context_hash_mismatch"`."""
    sw = ensure_sermon_workshop_state(session_state)
    raw_candidate = sw.get("developed_outline_candidate")
    if raw_candidate is None:
        return {"accepted": False, "reason": "no_candidate"}

    candidate = normalize_developed_outline_candidate(raw_candidate)
    if candidate is None:
        return {"accepted": False, "reason": "invalid_candidate"}

    candidate_reference = _as_str(candidate["reference"])
    candidate_context_hash = _as_str(candidate["context_hash"])
    current_reference = _as_str(reference)
    current_context_hash = _as_str(context_hash)
    if (
        not candidate_reference.strip()
        or not candidate_context_hash.strip()
        or not current_reference.strip()
        or not current_context_hash.strip()
    ):
        return {"accepted": False, "reason": "missing_context_identity"}
    if candidate_reference != current_reference:
        return {"accepted": False, "reason": "reference_mismatch"}
    if candidate_context_hash != current_context_hash:
        return {"accepted": False, "reason": "context_hash_mismatch"}

    sw["developed_outline"] = candidate["outline"]
    sw["developed_outline_meta"] = normalize_developed_outline_meta(
        {
            "reference": candidate["reference"],
            "context_hash": candidate["context_hash"],
            "generated_at": candidate["generated_at"],
            "manually_updated_at": "",
        }
    )
    sw["developed_outline_candidate"] = None
    return {
        "accepted": True,
        "reason": "",
        "developed_outline": sw["developed_outline"],
        "developed_outline_meta": sw["developed_outline_meta"],
    }


def update_developed_outline_movement_field(
    session_state: MutableMapping[str, Any],
    *,
    index: int,
    field: str,
    value: Any,
) -> dict[str, Any]:
    """Egyetlen vázlat-mozgás EGYETLEN mezőjének kézi frissítése.

    Kizárólag a célzott mezőt írja — a mozgás többi mezője, a többi
    mozgás, a `structure_mode`/`structure_note` és a candidate
    BIT-PONTOSAN változatlan marad. Sikeres írásnál a
    `developed_outline_meta.manually_updated_at` frissül (ez védi később
    a kézi munkát a néma felülírástól). Nem indít AI-hívást.

    Hibakezelés — a kódbázis meglévő kettős konvencióját követve:
      - ISMERETLEN `field` programozói hiba -> `ValueError` (ugyanúgy,
        mint `update_arc_point` ismeretlen pontkulcsnál);
      - ÉRVÉNYTELEN `index` viszont legitim futásidejű állapot (a vázlat
        időközben megváltozhatott) -> nem dob, hanem
        `{"updated": False, "reason": "index_out_of_range"}`.

    A `value` a mező típusa szerint normalizálódik: szöveges mezőnél
    stringgé, listamezőnél (`development`, `*_support`) stringlistává —
    így egy hibás típusú hívás sem ronthatja el a struktúrát."""
    if field not in _DEVELOPED_MOVEMENT_FIELDS:
        raise ValueError(f"Ismeretlen vázlat-mozgás mező: {field!r}")

    sw = ensure_sermon_workshop_state(session_state)
    outline = normalize_developed_outline(sw.get("developed_outline"))
    movements = outline["movements"]
    if not isinstance(index, int) or isinstance(index, bool):
        return {"updated": False, "reason": "index_out_of_range"}
    if index < 0 or index >= len(movements):
        return {"updated": False, "reason": "index_out_of_range"}

    movement = dict(movements[index])
    if field in _DEVELOPED_MOVEMENT_LIST_FIELDS:
        movement[field] = _normalize_str_list(value)
    else:
        movement[field] = _as_str(value)
    movements[index] = movement

    outline["movements"] = movements
    sw["developed_outline"] = outline

    meta = normalize_developed_outline_meta(sw.get("developed_outline_meta"))
    meta["manually_updated_at"] = datetime.now().isoformat(timespec="seconds")
    sw["developed_outline_meta"] = meta
    return {"updated": True, "reason": "", "movement": movement}


def _join_nonempty(*parts: Any, separator: str = "\n\n") -> str:
    """Nem üres részek összefűzése — a migrációs összevonásokhoz (pl. a régi
    `christ_centered_arc` 3 almezője -> 1 `arc.second_shift.text` mező)."""
    cleaned = [str(p).strip() for p in parts if str(p or "").strip()]
    return separator.join(cleaned)


_ENGAGEMENT_BASKET_SOURCE_LABEL = "Megszólítás (migrált)"


def _migrate_engagement_elements_to_basket(
    raw_elements: Any,
    *,
    existing_basket: Any = None,
) -> list[tuple[str, str]]:
    """Csak a korábban JÓVÁHAGYOTT (status == "approved") megszólító elemeket
    adja vissza, kosár-elem `(source, text)` pár formájában — duplikátumszűrve
    a már meglévő kosártartalommal ÉS egymással szemben is. Tiszta függvény:
    sem a bemenetet, sem semmilyen session_state-et nem módosít, csak az ÚJONNAN
    hozzáfűzendő elemeket adja vissza."""
    elements = normalize_engagement_elements(raw_elements) if raw_elements else []

    seen_texts: set[str] = set()
    if isinstance(existing_basket, list):
        for item in existing_basket:
            if isinstance(item, list | tuple) and len(item) == 2:
                text = str(item[1] or "").strip()
                if text:
                    seen_texts.add(text)

    out: list[tuple[str, str]] = []
    for element in elements:
        if element.get("status") != "approved":
            continue
        text = str(element.get("text") or "").strip()
        if not text or text in seen_texts:
            continue
        out.append((_ENGAGEMENT_BASKET_SOURCE_LABEL, text))
        seen_texts.add(text)
    return out


def migrate_legacy_arc_fields(
    sermon_workshop: Mapping[str, Any] | None,
    *,
    existing_arc: Mapping[str, Any] | None = None,
    existing_basket: Any = None,
) -> dict[str, Any]:
    """Nem destruktív, tisztán funkcionális migráció a régi Igehirdetési
    műhely-mezőkből az egységes `arc` struktúrába (célarchitektúra-terv,
    9.1. szakasz mezőtérképe szerint).

    KÖTELEZŐ SZABÁLYOK (mind betartva):
      - kizárólag ÜRES célmezőbe másolhat (`arc.<pont>.text` csak akkor
        töltődik, ha korábban is üres volt);
      - nem törli és nem módosítja a bemeneti `sermon_workshop`-ot (nincs
        mutáció — a `sermon_workshop` paraméter csak OLVASVA van);
      - nem ír semmilyen session_state-et vagy tartós projektadatot — tiszta
        függvény, a hívó felelőssége a visszatérési érték felhasználása;
      - ugyanazzal a bemenettel többször lefuttatva azonos eredményt ad
        (idempotens — ld. tests/test_arc_data_model.py);
      - az `engagement_elements` -> Vázlatkosár migráció csak a jóváhagyott
        elemeket veszi figyelembe, és duplikátummentes.

    Visszatérési érték:
        {
            "arc": dict[str, Any],               # a migrált, teljes arc
            "basket_items": list[tuple[str,str]], # ÚJONNAN kosárba teendő
                                                    # (source, text) párok
        }

    Ez a függvény ebben a fázisban SEHOL nem hívódik automatikusan (sem UI-,
    sem projektbetöltési útvonalon) — kizárólag tesztekből / jövőbeli,
    explicit hívásból érhető el.
    """
    sw = sermon_workshop if isinstance(sermon_workshop, dict) else {}

    result_arc = normalize_arc(existing_arc) if existing_arc is not None else get_default_arc()
    # Mély másolat — a visszaadott struktúra semmilyen közös referenciát nem
    # oszt meg a bemenettel, hogy a hívó biztonságosan módosíthassa.
    result_arc = copy.deepcopy(result_arc)

    entry = sw.get("entry_point") if isinstance(sw.get("entry_point"), dict) else {}
    sermon_path = sw.get("sermon_path") if isinstance(sw.get("sermon_path"), dict) else {}
    christ_arc = (
        sw.get("christ_centered_arc")
        if isinstance(sw.get("christ_centered_arc"), dict)
        else {}
    )
    closing = sw.get("closing") if isinstance(sw.get("closing"), dict) else {}
    human_condition = (
        sw.get("human_condition") if isinstance(sw.get("human_condition"), dict) else {}
    )
    listener_tension = (
        sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    )

    def _fill(point_key: str, candidate_text: str) -> None:
        """Csak akkor ír, ha a cél `text` mezője jelenleg üres, ÉS van
        tartalmas jelölt szöveg — soha nem ír felül nem üres célmezőt."""
        current = str(result_arc[point_key].get("text") or "").strip()
        if current:
            return
        candidate = candidate_text.strip()
        if not candidate:
            return
        result_arc[point_key] = dict(result_arc[point_key])
        result_arc[point_key]["text"] = candidate

    # --- Elsődleges (közvetlen 1:1, ill. 1 blokk -> 1 pont összevonás) ---
    _fill(
        "entry",
        _join_nonempty(entry.get("today_connection"), entry.get("text")),
    )
    _fill("starting_point", _as_str(sermon_path.get("starting_point")))
    _fill("first_shift", _as_str(sermon_path.get("first_shift")))
    _fill("deepening", _as_str(sermon_path.get("deepening")))
    _fill("reinterpretation", _as_str(sermon_path.get("reinterpretation")))
    _fill(
        "second_shift",
        _join_nonempty(
            christ_arc.get("divine_gracious_action"),
            christ_arc.get("christ_connection"),
            christ_arc.get("grace_enabled_response"),
        ),
    )
    _fill(
        "arrival",
        _join_nonempty(
            closing.get("final_discovery"),
            closing.get("hope"),
            closing.get("call_or_response"),
            closing.get("image_or_line"),
            closing.get("open_question"),
        ),
    )

    # --- Másodlagos, ALACSONYABB PRIORITÁSÚ pótló források — csak akkor
    # töltenek, ha az elsődleges forrás(ok) UTÁN a célpont még mindig üres.
    _fill(
        "starting_point",
        _join_nonempty(
            human_condition.get("condition"),
            human_condition.get("false_response"),
            human_condition.get("human_need"),
            human_condition.get("divine_action"),
            human_condition.get("grace_response"),
        ),
    )
    _fill(
        "first_shift",
        _join_nonempty(
            listener_tension.get("listener_question"),
            listener_tension.get("listener_resistance"),
            listener_tension.get("sermon_tension"),
            listener_tension.get("promised_resolution"),
        ),
    )

    basket_items = _migrate_engagement_elements_to_basket(
        sw.get("engagement_elements"), existing_basket=existing_basket
    )

    return {"arc": result_arc, "basket_items": basket_items}


def update_arc_point(
    session_state: MutableMapping[str, Any],
    point_key: str,
    text: str,
    *,
    context_hash: str | None = None,
) -> dict[str, Any]:
    """Egy `arc` pont szövegének frissítése — a jövőbeli auto-save mintázat
    adatréteg-szintű előkészítése.

    Szabályok:
      - csak érvényes `_ARC_POINT_KEYS` értéket fogad (egyébként ValueError);
      - normalizálja a szöveget (`_as_str`);
      - mindig frissíti az `updated_at` időbélyeget;
      - tartalmas (nem üres) mentésnél az aktuális igehelyhez/szöveghez
        kötött `context_hash`-t is beállítja a ponton — alapértelmezetten a
        szűk igehely-hash (ugyanaz a lusta-import minta, mint `_current_
        passage_context_hash`-nél — hiba esetén csendben üres marad, a
        mentés emiatt sosem bukik el);
      - SOHA nem nyúl az `ai_suggestion` / `ai_suggested_at` mezőkhöz;
      - a régi modellmezőket (entry_point, sermon_path, stb.) nem érinti;
      - kizárólag a meglévő session_state-mintát követi (ugyanúgy, mint pl.
        `update_sermon_workshop_section`) — nem ír külön tartós projektadatot,
        a projektmentés a meglévő `normalize_sermon_workshop` allowlist-úton
        történik, változatlanul;
      - RESET 2A: minden hívás frissíti az `arc_meta.manually_updated_at`
        időbélyeget is — ez alapértelmezetten az EGYETLEN `arc_meta` mező,
        amit ez a függvény érint (`reference`/`generated_at` mindig, és
        `context_hash` is, HA a hívó nem adja át a lenti opcionális
        paramétert, változatlan marad — azokat ekkor kizárólag `store_
        generated_arc_result`/`accept_arc_candidate` írja).

    `context_hash` (opcionális, szűk kiegészítés, 2026-08-19): ha a hívó
    átadja (jelenleg KIZÁRÓLAG az új, lapos hétpontos UI teszi ezt, a
    `sermon_workshop_arc_ai.compute_arc_generation_context_hash()` által
    számított TELJES generálási-kontextus hash-sel), akkor ez az érték
    kerül mind a pont saját `context_hash` mezőjébe, MIND az `arc_meta.
    context_hash`-ba — így kézi szerkesztés után az `arc_meta` a valódi,
    aktuális teljes kontextust tükrözi, nem csak a szűk igehely-hash-t.
    Ha a hívó nem ad át semmit (`None`, az alapértelmezés), a viselkedés
    száz százalékig megegyezik a korábbival: csak a pont saját mezője kap
    szűk igehely-hash-t, az `arc_meta.context_hash` érintetlen marad. Ez a
    régi hívók (pl. a közvetlen adatmodell-tesztek) számára teljesen
    visszafelé kompatibilis.
    """
    if point_key not in _ARC_POINT_KEYS:
        raise ValueError(f"Ismeretlen arc pont: {point_key!r}")

    sw = ensure_sermon_workshop_state(session_state)
    arc = sw.get("arc")
    if not isinstance(arc, dict):
        arc = get_default_arc()
    arc = normalize_arc(arc)

    point = dict(arc[point_key])
    normalized_text = _as_str(text)
    point["text"] = normalized_text
    point["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if normalized_text.strip():
        point["context_hash"] = (
            _as_str(context_hash)
            if context_hash is not None
            else _current_passage_context_hash(session_state)
        )

    arc[point_key] = point
    sw["arc"] = arc

    meta = normalize_arc_meta(sw.get("arc_meta"))
    meta["manually_updated_at"] = datetime.now().isoformat(timespec="seconds")
    if context_hash is not None:
        meta["context_hash"] = _as_str(context_hash)
    sw["arc_meta"] = meta

    return point


__all__ = [
    "SERMON_WORKSHOP_KEY",
    "get_default_sermon_workshop",
    "normalize_sermon_workshop",
    "ensure_sermon_workshop_state",
    "update_sermon_workshop_section",
    "empty_arc_point",
    "get_default_arc",
    "normalize_arc",
    "empty_arc_meta",
    "normalize_arc_meta",
    "normalize_arc_candidate",
    "arc_has_content",
    "set_arc_candidate",
    "discard_arc_candidate",
    "store_generated_arc_result",
    "accept_arc_candidate",
    "get_default_field_refinements",
    "normalize_field_refinements",
    "set_field_refinement_suggestion",
    "discard_field_refinement_suggestion",
    "validate_field_refinement_acceptance",
    # RESET 2E-1: kétlépcsős vázlatmotor adatmodellje.
    "empty_blueprint",
    "normalize_blueprint",
    "empty_blueprint_meta",
    "normalize_blueprint_meta",
    "store_generated_blueprint_result",
    "empty_developed_outline_movement",
    "normalize_developed_outline_movement",
    "normalize_developed_outline_movements",
    "empty_developed_outline",
    "normalize_developed_outline",
    "developed_outline_has_content",
    "empty_developed_outline_meta",
    "normalize_developed_outline_meta",
    "normalize_developed_outline_candidate",
    "set_developed_outline_candidate",
    "discard_developed_outline_candidate",
    "store_generated_developed_outline_result",
    "accept_developed_outline_candidate",
    "update_developed_outline_movement_field",
    "migrate_legacy_arc_fields",
    "update_arc_point",
    "add_approved_sermon_decision",
    "accept_workshop_proposal",
    "section_has_accepted_content",
    "remove_approved_sermon_decision",
    "deepcopy_sermon_workshop",
    "empty_sermon_movement",
    "normalize_sermon_movement",
    "normalize_sermon_movements",
    "empty_outline_movement",
    "empty_sermon_outline",
    "normalize_sermon_outline",
    "normalize_sermon_outline_diagnostics",
    "empty_textual_image",
    "empty_illustration",
    "empty_application",
    "normalize_textual_image",
    "normalize_illustration",
    "normalize_application",
    "normalize_textual_images",
    "normalize_illustrations",
    "normalize_applications",
    "normalize_lection_testament_preference",
    "normalize_lection_length_preference",
    "normalize_lection_connection_type",
    "normalize_prayer_tone_preference",
    "normalize_prayer_rewrite_mode",
    "empty_prayer_side",
    "save_sermon_main_idea_suggestions",
    "save_sermon_main_idea_assessment",
    "save_human_condition_suggestion",
    "save_human_condition_assessment",
    "save_listener_tension_suggestions",
    "save_listener_tension_assessment",
    "save_gospel_arc_suggestions",
    "save_gospel_arc_assessment",
    "save_sermon_path_suggestions",
    "save_sermon_path_assessment",
    "save_sermon_enrichment_suggestions",
    "save_sermon_enrichment_assessment",
    "save_closing_suggestions",
    "save_closing_assessment",
    "save_homiletical_diagnostics",
    "save_lection_suggestions",
    "save_lection_assessment",
    "save_lection_connection_analysis",
    "save_prayer_before_suggestions",
    "save_prayer_after_suggestions",
    "save_prayer_assessment",
    "save_sermon_outline",
    "save_sermon_outline_diagnostics",
    "set_sermon_outline_diagnostics_status",
    "_diagnostics_has_result",
]
