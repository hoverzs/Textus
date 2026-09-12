"""Közös workspace / project_data kulcsok és összeállítás.

Az app.py fájlmentése és a Supabase project_data ugyanebből a
kulcskészletből épül. Futásidejű / titkos / widget állapot nem kerül bele.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from textus_workshop_data import (
    TEXT_WORKSHOP_KEY,
    normalize_text_workshop,
)
from sermon_workshop_data import (
    SERMON_WORKSHOP_KEY,
    normalize_sermon_workshop,
)
from occasion_context import (
    OCCASION_CONTEXT_KEY,
    normalize_occasion_context,
)
from writing_desk_data import (
    WRITING_DESK_KEY,
    normalize_writing_desk,
)
from writing_desk_chat import (
    WRITING_DESK_CHAT_KEY,
    normalize_writing_desk_chat,
)

# Meglévő workspace-export kulcsok (app.py serialize_workspace).
WORKSPACE_STR_KEYS: list[str] = [
    "last_igehely",
    "last_alkalom",
    "last_stilus",
    "last_sajat",
    "bible_translation",
    "passage_text",
    "passage_text_source",
    "passage_text_source_url",
    # 2026-09 audit fix: fresh/stale_fallback finomság a durva
    # passage_text_source osztályozástól függetlenül — lásd
    # bible_text_ui.DURABLE_SOURCE_CACHE_STATUS.
    "passage_text_cache_status",
    "passage_text_fetched_at",
    "passage_text_fetched_reference",
    "passage_text_last_fetched_text",
    "overview",
    "exegesis",
    "exegesis_status",
    "history",
    "history_status",
    "theology",
    "theology_status",
    "illustrations",
    "actualization",
    "outline",
    "outline_draft",
    "outline_workshop_questions",
    "outline_workshop_answers",
    "outline_reworked_draft",
    "outline_title_suggestions",
    "original_text",
    "original_text_status",
    "songs",
    "series_planner_output",
    "series_idea",
]

WORKSPACE_LIST_KEYS: list[str] = [
    "basket",
    "verse_history",
    "exegesis_chat",
    "history_chat",
    "theology_chat",
    "illustrations_chat",
    "actualization_chat",
    "outline_chat",
    "original_text_chat",
    "songs_chat",
]

WORKSPACE_KEYS: list[str] = WORKSPACE_STR_KEYS + WORKSPACE_LIST_KEYS

# Tartós projektmezők a workspace-en felül (session defaults).
PROJECT_EXTRA_STR_KEYS: list[str] = [
    "series_cadence",
]

PROJECT_EXTRA_INT_KEYS: list[str] = [
    "series_weeks",
]

# Beágyazott objektumok a tartós project_data-ban (Textus 2.0).
PROJECT_NESTED_KEYS: list[str] = [
    TEXT_WORKSHOP_KEY,
    SERMON_WORKSHOP_KEY,
    OCCASION_CONTEXT_KEY,
    WRITING_DESK_KEY,
    # 2026-09 audit fix: a Segítő chat mostantól a projekt tartós
    # állapotának része — korábban explicit ki volt zárva
    # (lásd EXCLUDED_SESSION_KEYS lentebb, "_wd_helper_chat" már nincs benne).
    WRITING_DESK_CHAT_KEY,
]

PROJECT_DATA_STR_KEYS: list[str] = WORKSPACE_STR_KEYS + PROJECT_EXTRA_STR_KEYS
PROJECT_DATA_INT_KEYS: list[str] = list(PROJECT_EXTRA_INT_KEYS)
PROJECT_DATA_LIST_KEYS: list[str] = list(WORKSPACE_LIST_KEYS)
PROJECT_DATA_KEYS: list[str] = (
    PROJECT_DATA_STR_KEYS
    + PROJECT_DATA_INT_KEYS
    + PROJECT_DATA_LIST_KEYS
    + PROJECT_NESTED_KEYS
)

# Szándékosan soha nem kerül a project_data / workspace JSON-ba.
EXCLUDED_SESSION_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "using_builtin_key",
        "user_model_choice",
        "model_name",
        "temperature",
        "api_key_input",
        "_call_cache",
        "_debug_log",
        "_last_api_call_ts",
        "_session_uuid",
        "enable_cache",
        "_overview_running",
        "_outline_running",
        "_outline_questions_running",
        "_outline_rework_running",
        "_outline_final_running",
        "_outline_titles_running",
        "_original_running",
        "_songs_running",
        "igehely_input",
        "alkalom_input",
        "stilus_input",
        "sajat_input",
        "passage_text_input",
        "bible_translation_select",
        "bible_translation_other",
        "_bible_text_ui_resync",
        "_outline_draft_editor",
        "_outline_answers_editor",
        "_outline_reworked_editor",
        "_pending_outline_draft_editor",
        "_clear_outline_workshop_editors",
        "_feedback_last_sent",
        # Felületi nézetkulcsok — ne kerüljenek tartós mentésbe
        "ui_mode",
        "quick_tools_active_tab",
        "tw_active_section",
        "tw_main_idea_input",
        "tw_main_idea_status_radio",
        "_tw_ui_resync",
        "writing_desk_draft_input",
        "_wd_draft_resync",
        "_wd_draft_resync_bumped",
        "_wd_draft_revision",
        "_wd_outline_handoff_confirm",
        # "_wd_helper_chat" SZÁNDÉKOSAN NINCS itt (2026-09 audit fix) — lásd
        # PROJECT_NESTED_KEYS: a Segítő chat mostantól a projekt tartós
        # állapotának része, csak a live input-mező marad kizárva.
        "_wd_helper_chat_input",
        "writing_desk_docx_download",
        "_tw_main_idea_adopt_pending",
        "_main_idea_suggest_running",
        "_main_idea_assess_running",
        "sw_active_section",
        "sw_sermon_main_idea_input",
        "sw_hc_condition",
        "sw_hc_false_response",
        "sw_hc_human_need",
        "sw_hc_divine_action",
        "sw_hc_grace_response",
        "_sw_ui_resync",
        "_sw_sermon_idea_adopt_pending",
        "_sw_hc_adopt_pending",
        "_sw_m4_suggest_running",
        "_sw_m4_assess_running",
        "sw_lt_listener_question",
        "sw_lt_listener_resistance",
        "sw_lt_sermon_tension",
        "_sw_lt_adopt_pending",
        "_sw_m5_suggest_running",
        "_sw_m5_assess_running",
        "sw_ga_divine_gracious_action",
        "sw_ga_christ_connection",
        "sw_ga_christ_connection_type",
        "sw_ga_promised_resolution",
        "sw_ga_grace_enabled_response",
        "_sw_ga_adopt_pending",
        "_sw_m5_ga_suggest_running",
        "_sw_m5_ga_assess_running",
        "sw_path_type",
        "sw_path_reason",
        "sw_path_starting_point",
        "sw_path_destination",
        "_sw_path_adopt_pending",
        "_sw_movements_adopt_pending",
        "_sw_mv_delete_pending",
        "_sw_m6_suggest_running",
        "_sw_m6_assess_running",
        "_sw_en_adopt_all_pending",
        "_sw_en_adopt_images_pending",
        "_sw_en_adopt_ill_pending",
        "_sw_en_adopt_apps_pending",
        "_sw_en_img_delete_pending",
        "_sw_en_ill_delete_pending",
        "_sw_en_app_delete_pending",
        "_sw_m7_suggest_running",
        "_sw_m7_assess_running",
        "sw_cl_type",
        "sw_cl_final_discovery",
        "sw_cl_hope",
        "sw_cl_call_or_response",
        "sw_cl_image_or_line",
        "sw_cl_open_question",
        "sw_cl_tone",
        "_sw_cl_adopt_pending",
        "_sw_m7_cl_suggest_running",
        "_sw_m7_cl_assess_running",
        "sw_diag_self_strengths",
        "sw_diag_self_uncertainties",
        "sw_diag_self_priority",
        "sw_diag_self_focus",
        "sw_lection_reference",
        "sw_lection_connection_type",
        "sw_lection_function",
        "sw_lection_rationale",
        "sw_lection_text",
        "sw_lection_notes",
        "sw_lection_testament_preference",
        "sw_lection_length_preference",
        "sw_lection_user_focus",
        "_sw_lection_adopt_pending",
        "_sw_lection_ruf_pending",
        "sw_prayer_tone",
        "sw_prayer_general_focus",
        "sw_prayer_rewrite_mode",
        "sw_prayer_before_own_thoughts",
        "sw_prayer_before_purpose",
        "sw_prayer_before_movement_notes",
        "sw_prayer_before_selected_opening",
        "sw_prayer_before_selected_lines",
        "sw_prayer_before_closing_direction",
        "sw_prayer_after_own_thoughts",
        "sw_prayer_after_purpose",
        "sw_prayer_after_movement_notes",
        "sw_prayer_after_selected_opening",
        "sw_prayer_after_selected_lines",
        "sw_prayer_after_closing_direction",
        "_sw_prayer_adopt_pending",
        "sw_outline_main_idea",
        "sw_outline_main_idea_summary",
        "sw_outline_listener_question",
        "sw_outline_central_tension",
        "sw_outline_listener_resistance",
        "sw_outline_divine_action",
        "sw_outline_christ_connection",
        "sw_outline_christ_type",
        "sw_outline_gospel_resolution",
        "sw_outline_grace_response",
        "sw_outline_opening",
        "sw_outline_manual_notes",
        "sw_outline_closing_final",
        "sw_outline_closing_hope",
        "sw_outline_closing_invitation",
        "sw_outline_closing_image",
        "sw_outline_closing_question",
        "sw_outline_closing_tone",
        "sw_outline_lection_ref",
        "sw_outline_lection_function",
        "sw_outline_lection_rationale",
        "sw_outline_prayer_before_own",
        "sw_outline_prayer_before_opening",
        "sw_outline_prayer_before_lines",
        "sw_outline_prayer_before_closing",
        "sw_outline_prayer_after_own",
        "sw_outline_prayer_after_opening",
        "sw_outline_prayer_after_lines",
        "sw_outline_prayer_after_closing",
        "_sw_outline_confirm_overwrite",
        "_sw_outline_running",
        "_sw_outline_diag_running",
    }
)


def build_workspace_payload(
    *,
    version: str,
    state: Mapping[str, Any],
    app_name: str = "Textus",
) -> dict[str, Any]:
    """Ugyanaz a tartalom, mint az app.py `serialize_workspace()` payloadja."""
    payload: dict[str, Any] = {
        "_app": app_name,
        "_version": version,
        "_saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    for key in WORKSPACE_STR_KEYS:
        payload[key] = state.get(key, "")
    for key in WORKSPACE_LIST_KEYS:
        value = state.get(key, [])
        payload[key] = list(value) if isinstance(value, list) else []
    return payload


def build_project_data(
    state: Mapping[str, Any],
    *,
    version: str | None = None,
    app_name: str = "Textus",
) -> dict[str, Any]:
    """Tartós projekt JSON a workspace-serializáció alapján (+ sorozatmezők)."""
    payload = build_workspace_payload(
        version=version or "",
        state=state,
        app_name=app_name,
    )
    if not version:
        payload.pop("_version", None)

    for key in PROJECT_EXTRA_STR_KEYS:
        payload[key] = state.get(key, "")

    for key in PROJECT_EXTRA_INT_KEYS:
        raw = state.get(key, 4)
        try:
            payload[key] = int(raw)
        except (TypeError, ValueError):
            payload[key] = 4

    # Textus 2.0 műhelyadat — hiányzó / hibás érték esetén alapértelmezett
    payload[TEXT_WORKSHOP_KEY] = normalize_text_workshop(state.get(TEXT_WORKSHOP_KEY))
    payload[SERMON_WORKSHOP_KEY] = normalize_sermon_workshop(
        state.get(SERMON_WORKSHOP_KEY)
    )
    payload[OCCASION_CONTEXT_KEY] = normalize_occasion_context(
        state.get(OCCASION_CONTEXT_KEY)
    )
    payload[WRITING_DESK_KEY] = normalize_writing_desk(state.get(WRITING_DESK_KEY))
    payload[WRITING_DESK_CHAT_KEY] = normalize_writing_desk_chat(state.get(WRITING_DESK_CHAT_KEY))

    # Biztonsági szűrés: kizárt / titkos / futásidejű kulcsok soha ne maradjanak.
    for excluded in EXCLUDED_SESSION_KEYS:
        payload.pop(excluded, None)

    return sanitize_project_data(payload)


# Import / mélység korlátok (memória és biztonság — nem API-kvóta).
MAX_IMPORT_BYTES = 2_000_000
MAX_IMPORT_STRING_CHARS = 100_000
MAX_IMPORT_LIST_ITEMS = 200
MAX_IMPORT_DICT_KEYS = 200
MAX_IMPORT_DEPTH = 12

_DANGEROUS_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "secret",
        "token",
        "password",
        "authorization",
        "cookie_secret",
        "private_key",
        "access_token",
        "refresh_token",
        "interpreter",
        "pythonpath",
        "system_prompt",
    }
)


@dataclass
class ProjectSanitizeReport:
    data: dict[str, Any]
    dropped_keys: list[str] = field(default_factory=list)
    truncated_fields: list[str] = field(default_factory=list)
    rejected: bool = False
    reject_reason: str = ""


def _key_is_dangerous(key: Any) -> bool:
    k = str(key or "").strip().casefold().replace("-", "_")
    if k in EXCLUDED_SESSION_KEYS:
        return True
    if k in _DANGEROUS_KEY_FRAGMENTS:
        return True
    return any(frag in k for frag in _DANGEROUS_KEY_FRAGMENTS)


def _sanitize_value(
    value: Any,
    *,
    path: str,
    depth: int,
    report: ProjectSanitizeReport,
) -> Any:
    if depth > MAX_IMPORT_DEPTH:
        report.truncated_fields.append(path or "(root)")
        return None
    if isinstance(value, str):
        if len(value) > MAX_IMPORT_STRING_CHARS:
            report.truncated_fields.append(path)
            return value[: MAX_IMPORT_STRING_CHARS - 1] + "…"
        return value
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, list):
        items = value[:MAX_IMPORT_LIST_ITEMS]
        if len(value) > MAX_IMPORT_LIST_ITEMS:
            report.truncated_fields.append(path)
        out: list[Any] = []
        for i, item in enumerate(items):
            cleaned = _sanitize_value(
                item, path=f"{path}[{i}]", depth=depth + 1, report=report
            )
            if cleaned is not None or item is None:
                out.append(cleaned)
        return out
    if isinstance(value, Mapping):
        out_map: dict[str, Any] = {}
        for i, (raw_key, raw_val) in enumerate(value.items()):
            if i >= MAX_IMPORT_DICT_KEYS:
                report.truncated_fields.append(path)
                break
            key = str(raw_key)
            child = f"{path}.{key}" if path else key
            if _key_is_dangerous(key):
                report.dropped_keys.append(child)
                continue
            cleaned = _sanitize_value(
                raw_val, path=child, depth=depth + 1, report=report
            )
            out_map[key] = cleaned
        return out_map
    # bytes / egyéb — eldobás
    report.dropped_keys.append(path or "(unsupported)")
    return None


def sanitize_project_data_report(
    project_data: Mapping[str, Any] | None,
) -> ProjectSanitizeReport:
    """Allowlist + mélység/méret szűrés; részletes jelentéssel."""
    report = ProjectSanitizeReport(data={})
    if not isinstance(project_data, Mapping):
        return report

    allowed = set(PROJECT_DATA_KEYS) | {"_app", "_version", "_saved_at"}
    clean: dict[str, Any] = {}
    for key, value in project_data.items():
        key_s = str(key)
        if _key_is_dangerous(key_s) or key_s in EXCLUDED_SESSION_KEYS:
            report.dropped_keys.append(key_s)
            continue
        if key_s not in allowed:
            report.dropped_keys.append(key_s)
            continue
        if key_s == TEXT_WORKSHOP_KEY:
            nested = _sanitize_value(
                value, path=key_s, depth=1, report=report
            )
            clean[key_s] = normalize_text_workshop(nested)
        elif key_s == SERMON_WORKSHOP_KEY:
            nested = _sanitize_value(
                value, path=key_s, depth=1, report=report
            )
            clean[key_s] = normalize_sermon_workshop(nested)
        elif key_s == OCCASION_CONTEXT_KEY:
            nested = _sanitize_value(
                value, path=key_s, depth=1, report=report
            )
            clean[key_s] = normalize_occasion_context(nested)
        elif key_s == WRITING_DESK_KEY:
            nested = _sanitize_value(
                value, path=key_s, depth=1, report=report
            )
            clean[key_s] = normalize_writing_desk(nested)
        elif key_s == WRITING_DESK_CHAT_KEY:
            nested = _sanitize_value(
                value, path=key_s, depth=1, report=report
            )
            clean[key_s] = normalize_writing_desk_chat(nested)
        else:
            cleaned = _sanitize_value(
                value, path=key_s, depth=1, report=report
            )
            if key_s in PROJECT_DATA_LIST_KEYS:
                clean[key_s] = cleaned if isinstance(cleaned, list) else []
            elif key_s in PROJECT_DATA_INT_KEYS:
                try:
                    clean[key_s] = int(cleaned)
                except (TypeError, ValueError):
                    clean[key_s] = 4
            else:
                clean[key_s] = "" if cleaned is None else cleaned

    for key in (
        "bible_translation",
        "passage_text",
        "passage_text_source",
        "passage_text_source_url",
        "passage_text_cache_status",
        "passage_text_fetched_at",
        "passage_text_fetched_reference",
    ):
        if key not in clean:
            clean[key] = ""
    if OCCASION_CONTEXT_KEY not in clean:
        clean[OCCASION_CONTEXT_KEY] = normalize_occasion_context(None)
    if WRITING_DESK_KEY not in clean:
        clean[WRITING_DESK_KEY] = normalize_writing_desk(None)
    if WRITING_DESK_CHAT_KEY not in clean:
        clean[WRITING_DESK_CHAT_KEY] = normalize_writing_desk_chat(None)

    # Titkok soha
    for excluded in EXCLUDED_SESSION_KEYS:
        clean.pop(excluded, None)

    report.data = clean
    # Egyedi dropped lista
    report.dropped_keys = list(dict.fromkeys(report.dropped_keys))
    report.truncated_fields = list(dict.fromkeys(report.truncated_fields))
    return report


def sanitize_project_data(project_data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Csak a engedélyezett tartós kulcsokat (+ meta) hagyja meg."""
    return sanitize_project_data_report(project_data).data


def sanitize_workspace_import_bytes(
    raw_bytes: bytes | str,
    *,
    max_bytes: int = MAX_IMPORT_BYTES,
) -> ProjectSanitizeReport:
    """JSON workspace / projekt import: méretellenőrzés + sanitizálás."""
    report = ProjectSanitizeReport(data={})
    if isinstance(raw_bytes, bytes):
        if len(raw_bytes) > max_bytes:
            report.rejected = True
            report.reject_reason = (
                f"A fájl túl nagy ({len(raw_bytes)} bájt). "
                f"A maximális méret {max_bytes} bájt."
            )
            return report
        try:
            text = raw_bytes.decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            report.rejected = True
            report.reject_reason = f"A fájl nem olvasható UTF-8 szövegként: {exc}"
            return report
    else:
        text = str(raw_bytes)
        if len(text.encode("utf-8", errors="ignore")) > max_bytes:
            report.rejected = True
            report.reject_reason = (
                f"A fájl túl nagy. A maximális méret {max_bytes} bájt."
            )
            return report
    try:
        obj = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        report.rejected = True
        report.reject_reason = f"A fájl nem olvasható JSON: {exc}"
        return report
    if not isinstance(obj, dict) or obj.get("_app") not in ("Textus", "Emmaus"):
        report.rejected = True
        report.reject_reason = "Ez nem TEXTUS munkamenet-fájl."
        return report
    # Mélység / kulcsszám előellenőrzés a nyers fán
    probe = ProjectSanitizeReport(data={})
    _sanitize_value(obj, path="", depth=0, report=probe)
    if any(p.count(".") >= MAX_IMPORT_DEPTH for p in probe.truncated_fields):
        report.rejected = True
        report.reject_reason = "A JSON túl mélyen beágyazott; az import elutasítva."
        return report
    inner = sanitize_project_data_report(obj)
    # Meta megőrzése
    for meta in ("_app", "_version", "_saved_at"):
        if meta in obj and meta not in inner.data:
            inner.data[meta] = obj.get(meta)
    return inner


def project_content_fingerprint(state: Mapping[str, Any]) -> str:
    """Tartós projektmezők ujjlenyomata (dirty-jelzéshez; meta nélkül)."""
    payload: dict[str, Any] = {}
    for key in PROJECT_DATA_STR_KEYS:
        payload[key] = state.get(key, "")
    for key in PROJECT_DATA_INT_KEYS:
        raw = state.get(key, 4)
        try:
            payload[key] = int(raw)
        except (TypeError, ValueError):
            payload[key] = 4
    for key in PROJECT_DATA_LIST_KEYS:
        value = state.get(key, [])
        payload[key] = list(value) if isinstance(value, list) else []
    payload[TEXT_WORKSHOP_KEY] = normalize_text_workshop(state.get(TEXT_WORKSHOP_KEY))
    payload[SERMON_WORKSHOP_KEY] = normalize_sermon_workshop(
        state.get(SERMON_WORKSHOP_KEY)
    )
    payload[OCCASION_CONTEXT_KEY] = normalize_occasion_context(
        state.get(OCCASION_CONTEXT_KEY)
    )
    payload[WRITING_DESK_KEY] = normalize_writing_desk(state.get(WRITING_DESK_KEY))
    payload[WRITING_DESK_CHAT_KEY] = normalize_writing_desk_chat(state.get(WRITING_DESK_CHAT_KEY))
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "WORKSPACE_STR_KEYS",
    "WORKSPACE_LIST_KEYS",
    "WORKSPACE_KEYS",
    "PROJECT_DATA_KEYS",
    "PROJECT_NESTED_KEYS",
    "EXCLUDED_SESSION_KEYS",
    "MAX_IMPORT_BYTES",
    "ProjectSanitizeReport",
    "build_workspace_payload",
    "build_project_data",
    "sanitize_project_data",
    "sanitize_project_data_report",
    "sanitize_workspace_import_bytes",
    "project_content_fingerprint",
]
