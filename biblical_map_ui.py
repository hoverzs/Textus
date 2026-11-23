"""UI for the biblical map prototype."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, replace
from functools import lru_cache
import html
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from biblical_map_data import (
    BIBLICAL_MAP_PLACES,
    BiblicalMapSource,
    BiblicalPlace,
    places_by_id,
    primary_place,
    sources_by_id,
)
from biblical_map_passages import (
    MAP_SELECTION_SOURCE_AUTO,
    MAP_SELECTION_SOURCE_KEY,
    MAP_SELECTION_SOURCE_MANUAL,
    apply_passage_place_selection,
    find_place_links_for_passage,
)
from biblical_routes import (
    BiblicalRoute,
    BiblicalRouteDataError,
    BiblicalRouteSegment,
    BiblicalRouteStop,
    find_route_stop_matches_for_passage,
    load_biblical_routes,
    route_options,
)
from biblical_place_enrichment import (
    CONFIDENCE_LABELS_HU,
    PROFILE_STATUS_LABELS_HU,
    SECTION_LABELS_HU,
    SECTION_REVIEW_LABELS_HU,
    EnrichmentKeyEventsSection,
    EnrichmentTextSection,
    PlaceEnrichment,
    PlaceEnrichmentSource,
    enrichment_profile_status,
    get_place_enrichment,
    place_profile_group_for_place,
    place_enrichment_sources_by_id,
)


SELECTED_PLACE_ID_KEY = "_biblical_map_selected_place_id"
SELECTED_PLACE_SELECTBOX_KEY = f"{SELECTED_PLACE_ID_KEY}_selectbox"
PENDING_PLACE_ID_KEY = "_biblical_map_pending_place_id"
CATALOG_SEARCH_QUERY_KEY = "_biblical_map_catalog_search_query"
CATALOG_SEARCH_PICK_KEY = "_biblical_map_catalog_search_pick"
CATALOG_SEARCH_LIMIT = 20
ACTIVE_MAP_VIEW_KEY = "_biblical_map_active_view"
MAP_VIEW_PLACES = "Helyszínek"
MAP_VIEW_ROUTES = "Bibliai útvonalak"
MAP_STYLE_KEY = "_biblical_map_style"
MAP_STYLE_CLEAN = "clean"
# Legacy style ids from earlier prototypes; always coerced to the clean basemap.
MAP_STYLE_TERRAIN = "terrain"
MAP_STYLE_HISTORICAL_MOOD = "historical_mood"
SELECTED_ROUTE_ID_KEY = "_biblical_map_selected_route_id"
SELECTED_ROUTE_STOP_ID_KEY = "_biblical_map_selected_route_stop_id"
HIGHLIGHTED_ROUTE_STOP_IDS_KEY = "_biblical_map_highlighted_route_stop_ids"
SELECTED_ROUTE_PHASE_KEY = "_biblical_map_selected_route_phase"
PENDING_ROUTE_ID_KEY = "_biblical_map_pending_route_id"
PENDING_ROUTE_STOP_IDS_KEY = "_biblical_map_pending_route_stop_ids"
PENDING_MAP_VIEW_KEY = "_biblical_map_pending_view"
LAST_RENDERED_ROUTE_ID_KEY = "_biblical_map_last_rendered_route_id"
LAST_FOCUSED_ROUTE_STOP_ID_KEY = "_biblical_map_last_focused_route_stop_id"
ROUTE_VIEWPORT_STATE_KEY = "_biblical_map_route_viewport"
ROUTE_VIEW_WARNING_HU = (
    "Az útvonal a bibliai szövegben megnevezett állomások sorrendjét mutatja. "
    "A vonalak sematikusak, nem a pontos ókori nyomvonalat jelölik."
)
MAP_BLOCK_HEIGHT_PX = 520
_RESEARCH_DIR = Path(__file__).resolve().parent / "data" / "biblical_places" / "enrichment_research"
MAP_SCOPE_NOTE_HU = (
    "Ez a térképmodul belső / béta előtti prototípus. A legtöbb helyszín egyelőre "
    "katalógus- és bibliai kapcsolati adatot mutat; részletes történeti vagy régészeti "
    "háttér csak a kiemelten forrásolt helyeken érhető el."
)


@lru_cache(maxsize=1)
def _research_readiness_index() -> dict[str, str]:
    """Map place_id -> highest research readiness class available on disk."""
    # Apply from lowest to highest so stronger classes overwrite weaker ones.
    ranking = (
        ("batch_001_biblical_draft_ready.json", "biblical_draft_ready"),
        ("batch_001_partial_profile_ready.json", "partial_profile_ready"),
        ("batch_001_source_backed_ready.json", "source_backed_profile_ready"),
        ("batch_001_featured_candidates.json", "featured_candidate"),
    )
    index: dict[str, str] = {}
    for filename, label in ranking:
        path = _RESEARCH_DIR / filename
        if not path.exists():
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            place_id = str(row.get("place_id") or "").strip()
            if place_id:
                index[place_id] = label
    return index


def research_readiness_class(place_id: str) -> str | None:
    return _research_readiness_index().get(place_id)


@dataclass(frozen=True)
class BiblicalMapStyle:
    style_id: str
    label_hu: str
    pydeck_style: str | None
    attribution_hu: str | None
    note_hu: str | None = None
    fallback_style_id: str | None = None


MAP_STYLE_CONFIGS: dict[str, BiblicalMapStyle] = {
    MAP_STYLE_CLEAN: BiblicalMapStyle(
        style_id=MAP_STYLE_CLEAN,
        label_hu="Letisztult",
        pydeck_style=None,
        attribution_hu=None,
    ),
}
MAP_STYLE_OPTIONS = (MAP_STYLE_CLEAN,)

IDENTIFICATION_STATUS_LABELS = {
    "certain": "biztos",
    "probable": "valószínű",
    "possible": "lehetséges",
    "disputed": "vitatott",
    "unknown": "ismeretlen",
}
TRANSLATION_STATUS_LABELS = {
    "not_translated": "nincs fordítva",
    "machine_draft": "gépi fordítási vázlat",
    "human_translated": "emberi fordítás",
    "not_required": "nem igényel fordítást",
}
REVIEW_STATUS_LABELS = {
    "prototype": "prototípus",
    "draft": "vázlat",
    "needs_review": "szakmai ellenőrzésre vár",
    "reviewed": "ellenőrzött",
    "approved": "jóváhagyott",
}
CERTAINTY_LABELS = {
    "certain": "biztos",
    "probable": "valószínű",
    "possible": "lehetséges",
    "disputed": "vitatott",
    "unknown": "ismeretlen",
    "mixed": "vegyes",
}
ROUTE_EVIDENCE_TIER_LABELS = {
    "strong": "erős",
    "moderate": "közepes",
    "weak": "gyenge",
}
ROUTE_EVIDENCE_TIER_MARKERS = {
    "strong": "●",
    "moderate": "◐",
    "weak": "○",
}
ROUTE_EVIDENCE_TIER_NOTES_HU = {
    "strong": (
        "Állomásbizonyosság: erős — a megnevezett állomások sorrendje a bibliai szövegből "
        "jól követhető."
    ),
    "moderate": (
        "Állomásbizonyosság: közepes — a fő állomások szövegből követhetők, de van régió, "
        "átmenet vagy értelmezési pont."
    ),
    "weak": (
        "Állomásbizonyosság: gyenge — sematikus helycsoport vagy több bizonytalan azonosítás; "
        "nem rekonstruált itinerárium."
    ),
}
ROUTE_EVIDENCE_LEGEND_HU = (
    "● erős · ◐ közepes · ○ gyenge — a vonal minden esetben vázlatos"
)
GEOMETRY_STATUS_LABELS = {
    "schematic": "sematikus",
    "reconstructed": "rekonstruált",
    "approximate": "hozzávetőleges",
    "exact": "pontos",
    "unavailable": "nem áll rendelkezésre",
}
STOP_TYPE_LABELS = {
    "embarkation": "behajózás",
    "disembarkation": "partraszállás",
    "transit": "áthaladás",
    "destination": "célállomás",
    "return_stop": "visszaúti állomás",
    "explicit_place": "a szövegben megnevezett hely",
    "inferred_stop": "kikövetkeztetett állomás",
    "region": "régió",
    "uncertain_place": "bizonytalan hely",
}
SEGMENT_TYPE_LABELS = {
    "land": "szárazföldi",
    "sea": "tengeri",
    "river": "folyami",
    "mixed": "vegyes",
    "schematic": "sematikus",
    "unknown": "ismeretlen",
}


def resolve_selected_place_id(
    session_state: Mapping[str, Any],
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> str | None:
    """Return a valid selected place id, or None when nothing was chosen yet."""
    if not places:
        raise ValueError("At least one biblical map place is required.")
    selected = str(session_state.get(SELECTED_PLACE_ID_KEY) or "").strip()
    valid_ids = {place.place_id for place in places}
    if selected in valid_ids:
        return selected
    return None


def selected_place_for_session(
    session_state: Mapping[str, Any],
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> BiblicalPlace:
    selected_id = resolve_selected_place_id(session_state, places)
    if selected_id:
        return places_by_id(places).get(selected_id) or primary_place(places)
    return primary_place(places)


def queue_place_navigation(session_state: dict[str, Any], place_id: str) -> None:
    """Queue a place-card switch without mutating widget-backed state immediately."""
    session_state[PENDING_PLACE_ID_KEY] = place_id


def apply_pending_place_navigation_state(
    session_state: dict[str, Any],
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> str | None:
    pending_place_id = str(session_state.get(PENDING_PLACE_ID_KEY) or "").strip()
    if not pending_place_id:
        return None
    if pending_place_id not in {place.place_id for place in places}:
        session_state.pop(PENDING_PLACE_ID_KEY, None)
        return None
    session_state[SELECTED_PLACE_ID_KEY] = pending_place_id
    session_state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_MANUAL
    session_state.pop(PENDING_PLACE_ID_KEY, None)
    return pending_place_id


def place_option_labels(
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> dict[str, str]:
    return {
        place.place_id: (
            f"{display_place_name(place)} – elsődleges helyszín"
            if place.is_primary
            else display_place_name(place)
        )
        for place in places
    }


def place_selectbox_options(
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
    prioritized_place_id: str | None = None,
) -> list[str]:
    """Return deterministic place id options with an optional first item."""
    by_id: dict[str, BiblicalPlace] = {}
    for place in places:
        by_id.setdefault(place.place_id, place)

    sorted_places = sorted(
        by_id.values(),
        key=lambda place: (display_place_name(place).casefold(), place.place_id),
    )
    options = [place.place_id for place in sorted_places]
    priority = str(prioritized_place_id or "").strip()
    if priority in by_id:
        return [priority] + [place_id for place_id in options if place_id != priority]
    return options


def passage_linked_places(
    reference: str | None,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> tuple[BiblicalPlace, ...]:
    """Places linked to the current passage only (never the full catalog)."""
    by_id = places_by_id(places)
    linked: list[BiblicalPlace] = []
    for link in find_place_links_for_passage(reference):
        place = by_id.get(link.place_id)
        if place is not None:
            linked.append(place)
    return tuple(linked)


def normalize_place_search_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _place_search_haystacks(place: BiblicalPlace) -> tuple[str, ...]:
    values = [
        place.name_hu,
        place.name_en,
        place.modern_name,
        place.modern_country,
        place.ancient_name,
        *place.ancient_names,
        *place.original_names,
        *place.transliterations,
        place.place_id,
    ]
    return tuple(normalize_place_search_text(value) for value in values if value)


def display_place_name(place: BiblicalPlace) -> str:
    for value in (
        place.name_hu,
        place.name_en,
        place.ancient_name,
        place.modern_name,
        *place.ancient_names,
        *place.transliterations,
    ):
        text = str(value or "").strip()
        if text:
            return text
    return "Névtelen bibliai hely"


def fallback_place_description(place: BiblicalPlace) -> str:
    if place.card_summary_hu:
        return place.card_summary_hu
    if not place.modern_name:
        return ""
    location_parts = [
        value
        for value in (place.ancient_region, place.region_hu, place.modern_country)
        if value
    ]
    if not location_parts:
        status_prefix = (
            "Bizonytalan azonosítású bibliai helyszín"
            if place.identification_status in {"possible", "disputed", "unknown"}
            else "Bibliai helyszín"
        )
        return f"{status_prefix}; mai azonosítása: {place.modern_name}."
    status_prefix = (
        "Bizonytalan azonosítású bibliai helyszín"
        if place.identification_status in {"possible", "disputed", "unknown"}
        else "Bibliai helyszín"
    )
    return (
        f"{status_prefix} az ókori {location_parts[0]} területén; "
        f"mai azonosítása: {place.modern_name}."
    )


def search_biblical_places(
    query: str | None,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
    *,
    limit: int = CATALOG_SEARCH_LIMIT,
) -> list[BiblicalPlace]:
    """Accent/case-insensitive ranked catalog search, capped to `limit` hits."""
    needle = normalize_place_search_text(query)
    if not needle or limit <= 0:
        return []

    ranked: list[tuple[int, str, BiblicalPlace]] = []
    for place in places:
        haystacks = _place_search_haystacks(place)
        if not haystacks:
            continue
        score = 0
        if any(item == needle for item in haystacks):
            score = 300
        elif any(item.startswith(needle) for item in haystacks):
            score = 200
        elif any(needle in item for item in haystacks):
            score = 100
        if score:
            if get_place_enrichment(place.place_id) is not None:
                score += 20
            group = place_profile_group_for_place(place.place_id)
            if group is not None and group.primary_place_id == place.place_id:
                score += 10
            ranked.append((score, display_place_name(place).casefold(), place))

    ranked.sort(key=lambda item: (-item[0], item[1], item[2].place_id))
    return [place for _, _, place in ranked[:limit]]


def map_rows(
    selected_place_id: str,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> list[dict[str, Any]]:
    """Rows for Streamlit's built-in map widget."""
    rows: list[dict[str, Any]] = []
    for place in places:
        is_selected = place.place_id == selected_place_id
        rows.append(
            {
                "lat": place.latitude,
                "lon": place.longitude,
                "name": display_place_name(place),
                "place_id": place.place_id,
                "size": 520 if place.is_primary or is_selected else 240,
                "color": "#5a7aa8" if place.is_primary or is_selected else "#8a6a3f",
            }
        )
    return rows


def route_stop_display_name(stop: BiblicalRouteStop, place: BiblicalPlace | None) -> str:
    override = str(stop.place_name_override_hu or "").strip()
    if override:
        return override
    if place is not None:
        return display_place_name(place)
    return stop.place_id or stop.stop_id


def route_direction_label(stop: BiblicalRouteStop) -> str:
    if stop.stop_type == "return_stop" or stop.stop_id.endswith("_return"):
        return "visszaút"
    return "odaút"


def route_stop_rows(
    route: BiblicalRoute,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
    *,
    selected_stop_id: str | None = None,
    highlighted_stop_ids: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    by_id = places_by_id(places)
    highlighted = set(highlighted_stop_ids)
    rows: list[dict[str, Any]] = []
    for stop in route.stops:
        if not stop.display_on_map:
            continue
        place = by_id.get(stop.place_id)
        if place is None:
            continue
        is_selected = stop.stop_id == selected_stop_id
        is_highlighted = stop.stop_id in highlighted
        marker_size = 780 if is_selected else 560 if is_highlighted else 420
        marker_fill = [255, 246, 213, 245] if is_selected else [232, 241, 245, 230] if is_highlighted else [245, 239, 224, 220]
        marker_line = [31, 94, 128, 255] if is_selected else [54, 112, 140, 235] if is_highlighted else [70, 78, 84, 220]
        rows.append(
            {
                "lat": place.latitude,
                "lon": place.longitude,
                "display_lat": place.latitude,
                "display_lon": place.longitude,
                "name": route_stop_display_name(stop, place),
                "place_id": place.place_id,
                "stop_id": stop.stop_id,
                "order": stop.order,
                "label": str(stop.order),
                "stop_type": stop.stop_type,
                "stop_type_label": _display_status(stop.stop_type, STOP_TYPE_LABELS),
                "certainty": stop.certainty,
                "certainty_label": _display_status(stop.certainty, CERTAINTY_LABELS),
                "direction": route_direction_label(stop),
                "passage_refs": ", ".join(stop.passage_refs),
                "is_selected": is_selected,
                "is_highlighted": is_highlighted,
                "size": marker_size,
                "color": "#1f5e80" if is_selected else "#36708c" if is_highlighted else "#6f6a5f",
                "fill_color": marker_fill,
                "line_color": marker_line,
                "line_width": 5 if is_selected else 3 if is_highlighted else 2,
                "label_size": 16 if is_selected else 14,
                "label_color": [20, 32, 46, 255] if is_selected else [30, 42, 56, 245],
            }
        )
    coordinate_groups: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for row in rows:
        key = (round(float(row["lat"]), 6), round(float(row["lon"]), 6))
        coordinate_groups.setdefault(key, []).append(row)
    for group in coordinate_groups.values():
        if len(group) < 2:
            continue
        radius = 0.035
        for index, row in enumerate(sorted(group, key=lambda item: int(item["order"]))):
            angle = (2 * math.pi * index) / len(group)
            row["display_lat"] = float(row["lat"]) + math.sin(angle) * radius
            row["display_lon"] = float(row["lon"]) + math.cos(angle) * radius
    return rows


def _route_segment_direction(from_stop: BiblicalRouteStop, to_stop: BiblicalRouteStop) -> str:
    if (
        from_stop.stop_type == "return_stop"
        or to_stop.stop_type == "return_stop"
        or from_stop.stop_id.endswith("_return")
        or to_stop.stop_id.endswith("_return")
    ):
        return "return"
    return "outbound"


def route_curve_profile(segment_type: str) -> tuple[str, float]:
    if segment_type == "sea":
        return "soft_sea_curve", 0.11
    return "subtle_land_curve", 0.085


def _normalize_stop_id_for_curve(stop_id: str) -> str:
    normalized = stop_id
    for suffix in ("_return", "_outbound", "_departure", "_arrival"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _curve_seed_key(from_stop_id: str, to_stop_id: str, segment_type: str) -> str:
    normalized = sorted(
        _normalize_stop_id_for_curve(stop_id)
        for stop_id in (from_stop_id, to_stop_id)
    )
    return "|".join([*normalized, segment_type])


def _route_corridor_key(
    *,
    from_place_id: str | None,
    to_place_id: str | None,
    from_stop_id: str,
    to_stop_id: str,
    segment_type: str,
) -> tuple[str, str, str]:
    """Stable undirected key so outbound/return of the same place pair share one line."""
    if from_place_id and to_place_id:
        left, right = sorted((from_place_id, to_place_id))
    else:
        left, right = sorted(
            (
                _normalize_stop_id_for_curve(from_stop_id),
                _normalize_stop_id_for_curve(to_stop_id),
            )
        )
    return (segment_type, left, right)


def schematic_segment_path(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    segment_type: str,
    direction: str,
    from_stop_id: str,
    to_stop_id: str,
    steps: int = 12,
) -> list[list[float]]:
    from_lon, from_lat = start
    to_lon, to_lat = end
    if steps < 2 or (from_lon == to_lon and from_lat == to_lat):
        return [[from_lon, from_lat], [to_lon, to_lat]]

    dx = to_lon - from_lon
    dy = to_lat - from_lat
    distance = math.hypot(dx, dy)
    if distance == 0:
        return [[from_lon, from_lat], [to_lon, to_lat]]

    _profile, strength = route_curve_profile(segment_type)
    from_seed_id = _normalize_stop_id_for_curve(from_stop_id)
    to_seed_id = _normalize_stop_id_for_curve(to_stop_id)
    stable_seed = sum(ord(char) for char in _curve_seed_key(from_stop_id, to_stop_id, segment_type))
    sign = -1.0 if stable_seed % 2 else 1.0
    if direction == "return" and from_seed_id <= to_seed_id:
        sign *= -1.0
    offset = min(max(distance * strength, 0.045), 0.55) * sign
    perp_lon = -dy / distance
    perp_lat = dx / distance
    control_lon = (from_lon + to_lon) / 2 + perp_lon * offset
    control_lat = (from_lat + to_lat) / 2 + perp_lat * offset

    path: list[list[float]] = []
    for index in range(steps + 1):
        t = index / steps
        one_minus_t = 1 - t
        lon = (
            one_minus_t * one_minus_t * from_lon
            + 2 * one_minus_t * t * control_lon
            + t * t * to_lon
        )
        lat = (
            one_minus_t * one_minus_t * from_lat
            + 2 * one_minus_t * t * control_lat
            + t * t * to_lat
        )
        path.append([lon, lat])
    path[0] = [from_lon, from_lat]
    path[-1] = [to_lon, to_lat]
    return path


def route_segment_rows(
    route: BiblicalRoute,
    places: tuple[BiblicalPlace, ...] = BIBLICAL_MAP_PLACES,
) -> list[dict[str, Any]]:
    by_place_id = places_by_id(places)
    stop_by_id = {stop.stop_id: stop for stop in route.stops}
    rows: list[dict[str, Any]] = []
    for segment in route.segments:
        from_stop = stop_by_id.get(segment.from_stop_id)
        to_stop = stop_by_id.get(segment.to_stop_id)
        if from_stop is None or to_stop is None:
            continue
        if not from_stop.display_on_map or not to_stop.display_on_map:
            continue
        from_place = by_place_id.get(from_stop.place_id)
        to_place = by_place_id.get(to_stop.place_id)
        if from_place is None or to_place is None:
            continue
        direction = _route_segment_direction(from_stop, to_stop)
        straight_path = [
            [from_place.longitude, from_place.latitude],
            [to_place.longitude, to_place.latitude],
        ]
        curve_profile, curve_strength = route_curve_profile(segment.segment_type)
        path = schematic_segment_path(
            (from_place.longitude, from_place.latitude),
            (to_place.longitude, to_place.latitude),
            segment_type=segment.segment_type,
            direction=direction,
            from_stop_id=segment.from_stop_id,
            to_stop_id=segment.to_stop_id,
        )
        rows.append(
            {
                "from_stop_id": segment.from_stop_id,
                "to_stop_id": segment.to_stop_id,
                "from_place_id": from_place.place_id,
                "to_place_id": to_place.place_id,
                "segment_type": segment.segment_type,
                "segment_type_label": _display_status(segment.segment_type, SEGMENT_TYPE_LABELS),
                "certainty": segment.certainty,
                "certainty_label": _display_status(segment.certainty, CERTAINTY_LABELS),
                "geometry_status": segment.geometry_status,
                "geometry_status_label": _display_status(segment.geometry_status, GEOMETRY_STATUS_LABELS),
                "direction": direction,
                "line_style": "dashed" if direction == "return" else "solid",
                "path": path,
                "straight_path": straight_path,
                "curve_profile": curve_profile,
                "curve_strength": curve_strength,
                "color": (
                    [53, 101, 132, 190]
                    if segment.segment_type == "sea"
                    else [132, 101, 61, 190]
                )
                if direction == "outbound"
                else (
                    [53, 101, 132, 125]
                    if segment.segment_type == "sea"
                    else [132, 101, 61, 125]
                ),
                "width": 4 if segment.segment_type == "sea" else 3,
            }
        )
    return rows


def _valid_route_path(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and all(
            isinstance(point, list)
            and len(point) == 2
            and all(isinstance(coordinate, (int, float)) for coordinate in point)
            for point in value
        )
    )


def route_line_rows(segment_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build one renderable path per undirected place corridor.

    Outbound/return pairs that share the same places would otherwise draw two
    near-parallel lines; keep a single gently curved path (outbound preferred).
    """
    rows: list[dict[str, Any]] = []
    seen_corridors: set[tuple[str, str, str]] = set()
    for segment in segment_rows:
        curved_path = segment.get("path")
        straight_path = segment.get("straight_path")
        if _valid_route_path(curved_path):
            render_path = curved_path
            geometry_source = "curved"
        elif _valid_route_path(straight_path):
            render_path = straight_path
            geometry_source = "fallback_straight"
        else:
            continue
        corridor = _route_corridor_key(
            from_place_id=str(segment.get("from_place_id") or "") or None,
            to_place_id=str(segment.get("to_place_id") or "") or None,
            from_stop_id=str(segment.get("from_stop_id") or ""),
            to_stop_id=str(segment.get("to_stop_id") or ""),
            segment_type=str(segment.get("segment_type") or "land"),
        )
        if corridor in seen_corridors:
            continue
        seen_corridors.add(corridor)
        rows.append(
            {
                key: value
                for key, value in segment.items()
                if key not in {"path", "straight_path"}
            }
        )
        rows[-1]["render_path"] = render_path
        rows[-1]["geometry_source"] = geometry_source
        rows[-1]["corridor_key"] = "|".join(corridor)
    return rows


def route_viewport(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {"latitude": 0.0, "longitude": 0.0, "zoom": 1.0}
    latitudes = [float(row["lat"]) for row in rows]
    longitudes = [float(row["lon"]) for row in rows]
    lat_span = max(latitudes) - min(latitudes)
    lon_span = max(longitudes) - min(longitudes)
    span = max(lat_span, lon_span)
    zoom = 6.0 if span < 2 else 5.0 if span < 6 else 4.0 if span < 14 else 3.0
    return {
        "latitude": sum(latitudes) / len(latitudes),
        "longitude": sum(longitudes) / len(longitudes),
        "zoom": zoom,
    }


def _coerce_viewport(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        latitude = float(value["latitude"])
        longitude = float(value["longitude"])
        zoom = float(value["zoom"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"latitude": latitude, "longitude": longitude, "zoom": zoom}


def selected_route_stop_row(
    rows: list[dict[str, Any]],
    selected_stop_id: str | None,
) -> dict[str, Any] | None:
    if not selected_stop_id:
        return None
    return next((row for row in rows if row.get("stop_id") == selected_stop_id), None)


def selected_route_stop_focus_viewport(
    rows: list[dict[str, Any]],
    selected_stop_id: str | None,
    *,
    previous_viewport: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    selected_row = selected_route_stop_row(rows, selected_stop_id)
    if selected_row is None:
        previous = _coerce_viewport(previous_viewport)
        return previous if previous is not None else route_viewport(rows)

    base_viewport = route_viewport(rows)
    base_zoom = float(base_viewport["zoom"])
    focus_zoom = min(max(base_zoom + 1.0, 5.0), 6.5)
    return {
        "latitude": float(selected_row["display_lat"]),
        "longitude": float(selected_row["display_lon"]),
        "zoom": focus_zoom,
    }


def route_viewport_for_selection(
    session_state: Any,
    rows: list[dict[str, Any]],
    *,
    route_id: str,
    selected_stop_id: str | None,
) -> dict[str, float]:
    previous_viewport = _coerce_viewport(session_state.get(ROUTE_VIEWPORT_STATE_KEY))
    focus_key = f"{route_id}:{selected_stop_id or ''}"
    last_focus_key = str(session_state.get(LAST_FOCUSED_ROUTE_STOP_ID_KEY) or "")
    selected_row = selected_route_stop_row(rows, selected_stop_id)

    if selected_row is None:
        viewport = previous_viewport if previous_viewport is not None else route_viewport(rows)
    elif focus_key != last_focus_key:
        viewport = selected_route_stop_focus_viewport(rows, selected_stop_id)
        session_state[LAST_FOCUSED_ROUTE_STOP_ID_KEY] = focus_key
    else:
        viewport = previous_viewport if previous_viewport is not None else selected_route_stop_focus_viewport(
            rows,
            selected_stop_id,
        )

    session_state[ROUTE_VIEWPORT_STATE_KEY] = dict(viewport)
    return viewport


def route_matches_for_passage(
    reference: str | None,
) -> dict[str, list[BiblicalRouteStop]]:
    grouped: dict[str, list[BiblicalRouteStop]] = {}
    for match in find_route_stop_matches_for_passage(reference):
        grouped.setdefault(match.route.route_id, []).append(match.stop)
    return grouped


def switch_to_route_view_for_passage(
    session_state: Any,
    route_id: str,
    stop_ids: list[str] | tuple[str, ...],
) -> None:
    queue_route_navigation(session_state, route_id, stop_ids)


def queue_route_navigation(
    session_state: Any,
    route_id: str,
    stop_ids: list[str] | tuple[str, ...] = (),
) -> None:
    unique_stop_ids = list(dict.fromkeys(str(stop_id) for stop_id in stop_ids if stop_id))
    session_state[PENDING_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    session_state[PENDING_ROUTE_ID_KEY] = route_id
    session_state[PENDING_ROUTE_STOP_IDS_KEY] = unique_stop_ids


def apply_pending_route_navigation_state(
    session_state: Any,
    valid_route_ids: list[str] | tuple[str, ...] | None = None,
) -> None:
    pending_view = str(session_state.get(PENDING_MAP_VIEW_KEY) or "").strip()
    if pending_view in {MAP_VIEW_PLACES, MAP_VIEW_ROUTES}:
        session_state[ACTIVE_MAP_VIEW_KEY] = pending_view
    session_state.pop(PENDING_MAP_VIEW_KEY, None)

    pending_route_id = str(session_state.get(PENDING_ROUTE_ID_KEY) or "").strip()
    if pending_route_id:
        if valid_route_ids is None or pending_route_id in valid_route_ids:
            session_state[SELECTED_ROUTE_ID_KEY] = pending_route_id
            stop_ids = list(session_state.get(PENDING_ROUTE_STOP_IDS_KEY) or ())
            unique_stop_ids = list(dict.fromkeys(str(stop_id) for stop_id in stop_ids if stop_id))
            session_state[HIGHLIGHTED_ROUTE_STOP_IDS_KEY] = unique_stop_ids
            if unique_stop_ids:
                session_state[SELECTED_ROUTE_STOP_ID_KEY] = unique_stop_ids[0]
            else:
                session_state.pop(SELECTED_ROUTE_STOP_ID_KEY, None)
        session_state.pop(PENDING_ROUTE_ID_KEY, None)
        session_state.pop(PENDING_ROUTE_STOP_IDS_KEY, None)


def route_phase_state_key(route_id: str) -> str:
    return f"{SELECTED_ROUTE_PHASE_KEY}_{route_id}"


def prepare_route_widget_state(
    session_state: Any,
    routes: tuple[BiblicalRoute, ...],
) -> tuple[str, str, str, BiblicalRoute, tuple[BiblicalRouteStop, ...], tuple[BiblicalRouteSegment, ...]]:
    options = route_options(routes)
    apply_pending_route_navigation_state(session_state, options)

    selected_route_id = str(session_state.get(SELECTED_ROUTE_ID_KEY) or "")
    if selected_route_id not in options:
        selected_route_id = options[0]
        session_state[SELECTED_ROUTE_ID_KEY] = selected_route_id

    route = next(route for route in routes if route.route_id == selected_route_id)
    phase_options = route_phase_options(route)
    selected_phase = ""
    if phase_options:
        phase_key = route_phase_state_key(route.route_id)
        selected_phase = str(session_state.get(phase_key) or phase_options[0])
        if selected_phase not in phase_options:
            selected_phase = phase_options[0]
            session_state[phase_key] = selected_phase

    visible_stops = filtered_route_stops(route, selected_phase)
    visible_segments = filtered_route_segments(route, visible_stops)
    valid_stop_ids = [stop.stop_id for stop in visible_stops]
    highlighted_stop_ids = tuple(session_state.get(HIGHLIGHTED_ROUTE_STOP_IDS_KEY) or ())
    selected_stop_id = str(session_state.get(SELECTED_ROUTE_STOP_ID_KEY) or "")
    previous_route_id = str(session_state.get(LAST_RENDERED_ROUTE_ID_KEY) or "")
    highlighted_valid = [stop_id for stop_id in highlighted_stop_ids if stop_id in valid_stop_ids]
    first_mappable_stop_id = next(
        (stop.stop_id for stop in visible_stops if stop.display_on_map),
        valid_stop_ids[0],
    )
    if (
        previous_route_id != selected_route_id
        or selected_stop_id not in valid_stop_ids
    ):
        selected_stop_id = highlighted_valid[0] if highlighted_valid else first_mappable_stop_id
        session_state[SELECTED_ROUTE_STOP_ID_KEY] = selected_stop_id
    session_state[LAST_RENDERED_ROUTE_ID_KEY] = selected_route_id

    return selected_route_id, selected_phase, selected_stop_id, route, visible_stops, visible_segments


def _streamlit():
    try:
        import streamlit as st  # type: ignore
    except ImportError as exc:  # pragma: no cover - app runtime dependency
        raise RuntimeError("Streamlit is required to render the biblical map prototype.") from exc
    return st


def _render_styles(st: Any) -> None:
    st.markdown(
        """
<style>
/* Feltűnőbb térkép-expander — ne olvadjon a felületbe */
.st-key-biblical_map_cta [data-testid="stExpander"],
.st-key-biblical_map_cta details {
  border: 1px solid rgba(90, 122, 168, 0.42) !important;
  border-left: 4px solid var(--tx-primary, #5a7aa8) !important;
  border-radius: 10px !important;
  background:
    linear-gradient(
      135deg,
      rgba(232, 238, 248, 0.92) 0%,
      rgba(248, 245, 238, 0.88) 55%,
      rgba(255, 252, 247, 0.95) 100%
    ) !important;
  box-shadow: 0 1px 3px rgba(42, 33, 23, 0.07) !important;
}
.st-key-biblical_map_cta [data-testid="stExpander"] summary,
.st-key-biblical_map_cta [data-testid="stExpander"] summary p,
.st-key-biblical_map_cta details summary,
.st-key-biblical_map_cta details summary p,
.st-key-biblical_map_cta [data-testid="stExpander"] span {
  font-weight: 650 !important;
  color: #2a2117 !important;
  font-size: 1.02rem !important;
  letter-spacing: 0.01em !important;
}
/* A fejléc a közös, sötétkék színátmenetes lenyitóstílust kapja, ezért a
   felirata fehér, mint a többi lenyitóé (UI/UX-audit 2026-11-23, V9). A
   nyitott lenyitó világos hátterű tartalma sötét marad (fenti szabály). */
.st-key-biblical_map_cta [data-testid="stExpander"] summary,
.st-key-biblical_map_cta [data-testid="stExpander"] summary p,
.st-key-biblical_map_cta [data-testid="stExpander"] summary span,
.st-key-biblical_map_cta details summary,
.st-key-biblical_map_cta details summary p,
.st-key-biblical_map_cta details summary span {
  color: #ffffff !important;
  text-shadow: 0 1px 0 rgba(18, 32, 48, 0.35) !important;
}
.st-key-biblical_map_cta [data-testid="stExpander"]:hover,
.st-key-biblical_map_cta details:hover {
  border-color: rgba(90, 122, 168, 0.62) !important;
  box-shadow: 0 2px 8px rgba(42, 33, 23, 0.1) !important;
}
.textus-biblical-map-note {
  color: var(--tx-text-muted, #5d5347);
  font-size: 0.84rem;
  line-height: 1.45;
  margin: 0.2rem 0 0.75rem;
}
.textus-biblical-map-card {
  border-left: 3px solid var(--tx-primary, #5a7aa8);
  background: rgba(236, 242, 248, 0.55);
  padding: 0.75rem 0.85rem;
  border-radius: 0 8px 8px 0;
  margin-top: 0.25rem;
}
.textus-biblical-map-card h4 {
  margin: 0 0 0.35rem;
  font-size: 1rem;
}
.textus-biblical-map-meta {
  color: var(--tx-text-muted, #5d5347);
  font-size: 0.84rem;
  line-height: 1.45;
}
.textus-biblical-map-sources {
  color: var(--tx-text-muted, #5d5347);
  font-size: 0.78rem;
  line-height: 1.3;
  margin: 0.3rem 0 0;
}
.textus-biblical-map-sources a {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
  word-break: break-word;
}
.textus-biblical-map-quality {
  color: var(--tx-text-muted, #5d5347);
  font-size: 0.78rem;
  line-height: 1.3;
  margin: 0.45rem 0 0;
}
.textus-biblical-map-block {
  margin: 0.35rem 0 0.85rem;
}
.textus-biblical-map-section {
  margin: 0.55rem 0 0.35rem;
}
@media (max-width: 768px) {
  .textus-biblical-map-card {
    margin-top: 0.75rem;
  }
}
</style>
""",
        unsafe_allow_html=True,
    )


def _render_map_block_open(st: Any) -> None:
    st.markdown('<div class="textus-biblical-map-block">', unsafe_allow_html=True)


def _render_map_block_close(st: Any) -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def _render_section_heading(st: Any, title: str) -> None:
    st.markdown('<div class="textus-biblical-map-section"></div>', unsafe_allow_html=True)
    st.markdown(f"#### {title}")


def resolve_map_style_id(session_state: Any) -> str:
    style_id = str(session_state.get(MAP_STYLE_KEY) or MAP_STYLE_CLEAN)
    if style_id not in MAP_STYLE_CONFIGS:
        style_id = MAP_STYLE_CLEAN
        session_state[MAP_STYLE_KEY] = style_id
    return style_id


def effective_map_style(style_id: str) -> BiblicalMapStyle:
    style = MAP_STYLE_CONFIGS.get(style_id) or MAP_STYLE_CONFIGS[MAP_STYLE_CLEAN]
    if style.pydeck_style is None and style.fallback_style_id:
        fallback = MAP_STYLE_CONFIGS.get(style.fallback_style_id)
        if fallback:
            return BiblicalMapStyle(
                style_id=style.style_id,
                label_hu=style.label_hu,
                pydeck_style=fallback.pydeck_style,
                attribution_hu=fallback.attribution_hu,
                note_hu=style.note_hu,
                fallback_style_id=style.fallback_style_id,
            )
    return style


def render_map_style_selector(st: Any) -> str:
    """Keep a single clean basemap; no style picker in the UI."""
    st.session_state[MAP_STYLE_KEY] = MAP_STYLE_CLEAN
    return MAP_STYLE_CLEAN


def _render_places_map_block(
    st: Any,
    *,
    map_focus_id: str,
    map_places: tuple[BiblicalPlace, ...],
    map_style_id: str | None = None,
) -> None:
    _render_map_block_open(st)
    _style = effective_map_style(map_style_id or resolve_map_style_id(st.session_state))
    map_kwargs: dict[str, Any] = {
        "latitude": "lat",
        "longitude": "lon",
        "size": "size",
        "color": "color",
        "zoom": 4,
        "use_container_width": True,
    }
    try:
        try:
            st.map(
                map_rows(map_focus_id, map_places),
                height=MAP_BLOCK_HEIGHT_PX,
                **map_kwargs,
            )
        except TypeError:
            # Older Streamlit builds may not accept height on st.map.
            st.map(map_rows(map_focus_id, map_places), **map_kwargs)
    except Exception as exc:  # pragma: no cover - depends on Streamlit runtime
        st.warning(
            "A térképi nézet nem érhető el, de a helyválasztó és az adatlap használható."
        )
        with st.expander("Technikai részletek", expanded=False):
            st.caption(type(exc).__name__)
    _render_map_block_close(st)


def _display_status(value: str | None, labels: Mapping[str, str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    return labels.get(raw, raw.replace("_", " "))


def _source_index() -> dict[str, BiblicalMapSource]:
    try:
        return sources_by_id()
    except Exception:
        return {}


def dedupe_sources(sources: list[BiblicalMapSource]) -> list[BiblicalMapSource]:
    """Drop duplicate source_id / provider entries while preserving order."""
    unique: list[BiblicalMapSource] = []
    seen_ids: set[str] = set()
    seen_providers: set[str] = set()
    for source in sources:
        source_id = _usable_text(source.source_id)
        provider = normalize_place_search_text(
            _usable_text(source.provider) or _usable_text(source.title)
        )
        if source_id and source_id in seen_ids:
            continue
        if provider and provider in seen_providers:
            continue
        if source_id:
            seen_ids.add(source_id)
        if provider:
            seen_providers.add(provider)
        unique.append(source)
    return unique


def _resolve_sources(place: BiblicalPlace) -> list[BiblicalMapSource]:
    by_id = _source_index()
    resolved = [source for source_id in place.source_ids if (source := by_id.get(source_id))]
    return dedupe_sources(resolved)


def _uses_only_manual_demo_source(place: BiblicalPlace) -> bool:
    source_ids = tuple(source_id for source_id in place.source_ids if source_id)
    return source_ids == ("manual_demo_v1",)


def _usable_text(value: str | None) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text


def _compact_source_markdown_item(source: BiblicalMapSource) -> str:
    provider = _usable_text(source.provider) or _usable_text(source.title) or "Forrás"
    url = _usable_text(source.source_url)
    if url:
        return f"[{provider}]({url})"
    return provider


def _compact_source_html_item(source: BiblicalMapSource) -> str:
    provider = html.escape(
        _usable_text(source.provider) or _usable_text(source.title) or "Forrás"
    )
    url = _usable_text(source.source_url)
    if url:
        return (
            f'<a href="{html.escape(url, quote=True)}" '
            f'target="_blank" rel="noopener">{provider}</a>'
        )
    return provider


def compact_sources_markdown(sources: list[BiblicalMapSource]) -> str:
    """Return a single compact inline sources line, or empty string."""
    items = [
        item
        for source in dedupe_sources(sources)
        if (item := _compact_source_markdown_item(source))
    ]
    if not items:
        return ""
    return "**Források:** " + " · ".join(items)


def compact_sources_html(sources: list[BiblicalMapSource]) -> str:
    """Return compact inline HTML for sources, or empty string."""
    items = [
        item
        for source in dedupe_sources(sources)
        if (item := _compact_source_html_item(source))
    ]
    if not items:
        return ""
    return (
        '<div class="textus-biblical-map-sources">'
        "<strong>Források:</strong> "
        + " · ".join(items)
        + "</div>"
    )


def _render_short_sources(st: Any, sources: list[BiblicalMapSource]) -> None:
    html_block = compact_sources_html(sources)
    if not html_block:
        return
    st.markdown(html_block, unsafe_allow_html=True)


def _render_detail_expanders(st: Any, place: BiblicalPlace) -> None:
    sources = _resolve_sources(place)

    background_fields = [
        ("Földrajzi háttér", place.geography_hu),
        ("Történeti háttér", place.history_hu),
        ("Politikai-közigazgatási háttér", place.political_context_hu),
        ("Gazdasági háttér", place.economic_context_hu),
        ("Társadalmi háttér", place.social_context_hu),
        ("Vallási háttér", place.religious_context_hu),
        ("Régészeti háttér", place.archaeology_hu),
        ("Bibliai jelentőség", place.biblical_significance_hu),
        ("Mai kontextus", place.modern_context_hu),
    ]
    if any(value for _, value in background_fields):
        with st.expander("Részletes háttér", expanded=False):
            for label, value in background_fields:
                if value:
                    st.markdown(f"**{label}.** {value}")
            quality_parts = []
            if place.identification_status:
                identification_label = _display_status(
                    place.identification_status,
                    IDENTIFICATION_STATUS_LABELS,
                )
                if identification_label and identification_label != "—":
                    quality_parts.append(f"{identification_label} helyazonosítás")
            if place.review_status:
                review_label = _display_status(place.review_status, REVIEW_STATUS_LABELS)
                if review_label and review_label != "—":
                    quality_parts.append(review_label)
            quality_text = " · ".join(part for part in quality_parts if part and part != "—")
            if quality_text:
                st.markdown(
                    f'<div class="textus-biblical-map-quality">'
                    f"Adatminőség: {html.escape(quality_text)}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            _render_short_sources(st, sources)

    if place.exegetical_notes:
        with st.expander("Exegetikai megjegyzések", expanded=False):
            for note in place.exegetical_notes:
                st.markdown(f"**{note.passage_reference} – {note.title_hu}**")
                st.markdown(note.note_hu)
                if note.limitations_hu:
                    st.caption(f"Korlátok: {note.limitations_hu}")
                source_lookup = _source_index()
                resolved = dedupe_sources(
                    [
                        source
                        for source_id in note.source_ids
                        if (source := source_lookup.get(source_id))
                    ]
                )
                _render_short_sources(st, resolved)


def _enrichment_source_label(source: PlaceEnrichmentSource) -> str:
    return _usable_text(source.institution) or _usable_text(source.title) or "Forrás"


def _enrichment_source_markdown(source: PlaceEnrichmentSource) -> str:
    label = _enrichment_source_label(source)
    if source.identifier:
        return f"[{label}]({source.identifier})"
    return label


def _section_status_line(section: EnrichmentTextSection | EnrichmentKeyEventsSection) -> str:
    parts = [
        CONFIDENCE_LABELS_HU.get(section.confidence, section.confidence),
        SECTION_REVIEW_LABELS_HU.get(section.review_status, section.review_status),
    ]
    return " · ".join(part for part in parts if part)


def _render_enrichment_sources(
    st: Any,
    source_ids: list[str] | tuple[str, ...],
    source_lookup: Mapping[str, PlaceEnrichmentSource],
) -> None:
    items: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        source = source_lookup.get(source_id)
        if source is None or source.source_id in seen:
            continue
        seen.add(source.source_id)
        items.append(_enrichment_source_markdown(source))
    if items:
        st.caption("Források: " + " · ".join(items))


def _render_enrichment_text_section(
    st: Any,
    section_key: str,
    section: EnrichmentTextSection,
    source_lookup: Mapping[str, PlaceEnrichmentSource],
    *,
    expanded: bool = False,
) -> None:
    with st.expander(SECTION_LABELS_HU.get(section_key, section_key), expanded=expanded):
        if section.review_status == "needs_review":
            st.warning("Ez a szakasz szakmai ellenőrzésre vár.")
        if section_key == "homiletical_context":
            st.caption(
                "Ez a rész a hely történeti, társadalmi és földrajzi hátterének "
                "szövegértelmezési jelentőségét foglalja össze; nem kész prédikációs alkalmazás."
            )
        st.markdown(section.text_hu)
        st.caption(_section_status_line(section))
        _render_enrichment_sources(st, section.source_ids, source_lookup)


def _render_enrichment_key_events(
    st: Any,
    section: EnrichmentKeyEventsSection,
    source_lookup: Mapping[str, PlaceEnrichmentSource],
) -> None:
    with st.expander(SECTION_LABELS_HU["key_events"], expanded=False):
        if section.review_status == "needs_review":
            st.warning("Ez a szakasz szakmai ellenőrzésre vár.")
        for item in section.items:
            refs = ", ".join(item.passage_refs)
            st.markdown(f"- **{refs}:** {item.summary_hu}")
        st.caption(_section_status_line(section))
        section_source_ids = [
            source_id
            for item in section.items
            for source_id in item.source_ids
        ]
        _render_enrichment_sources(st, section_source_ids, source_lookup)


def _render_enrichment_routes(st: Any, enrichment: PlaceEnrichment) -> None:
    if not enrichment.related_route_ids:
        return
    routes_by_id = {route.route_id: route for route in load_biblical_routes()}
    available_route_ids = [route_id for route_id in enrichment.related_route_ids if route_id in routes_by_id]
    if not available_route_ids:
        return
    with st.expander("Kapcsolódó bibliai útvonalak", expanded=False):
        for route_id in available_route_ids:
            route = routes_by_id[route_id]
            if st.button(route.name_hu, key=f"_biblical_map_enrichment_route_{enrichment.place_id}_{route_id}"):
                queue_route_navigation(st.session_state, route_id)
                if hasattr(st, "rerun"):
                    st.rerun()
            st.caption(route.short_description_hu)


def _render_profile_status_note(
    st: Any,
    status: str,
    *,
    has_enrichment: bool,
    research_class: str | None = None,
) -> None:
    label = PROFILE_STATUS_LABELS_HU.get(status, status)
    st.caption(f"Helyszínprofil állapota: {label}")
    if research_class:
        research_labels = {
            "biblical_draft_ready": "kutatási szinten: bibliai vázlat készíthető",
            "partial_profile_ready": "kutatási szinten: részleges profil (külső forrás van)",
            "source_backed_profile_ready": "kutatási szinten: source-backed profil",
            "featured_candidate": "kutatási szinten: featured jelölt",
        }
        st.caption(research_labels.get(research_class, f"kutatási szint: {research_class}"))
    if not has_enrichment or status in {"basic", "partial", "needs_review"}:
        st.caption(
            "A helyszínadatlapok bővítése fokozatosan történik. A rövidebb adatlap nem "
            "jelent adathiányt a bibliai helyazonosításban; csak azt, hogy még nem készült "
            "hozzá részletes, intézményi/tudományos forrású háttéranyag."
        )
    elif status == "source_backed":
        st.caption(
            "Ez a bővített adatlap intézményi vagy tudományos forrást is használ "
            "történeti/régészeti háttérhez."
        )


def _render_related_profile_records(st: Any, place: BiblicalPlace) -> None:
    group = place_profile_group_for_place(place.place_id)
    if group is None or len(group.member_place_ids) <= 1:
        return
    by_id = places_by_id(BIBLICAL_MAP_PLACES)
    related_places = [
        candidate
        for place_id in group.member_place_ids
        if place_id != place.place_id and (candidate := by_id.get(place_id)) is not None
    ]
    if not related_places:
        return
    with st.expander("Kapcsolódó korszakok vagy helyrekordok", expanded=False):
        st.caption(group.notes_hu or "Kapcsolódó, de külön canonical rekordok.")
        for related_place in related_places:
            label = display_place_name(related_place)
            meta = " · ".join(
                part
                for part in [
                    related_place.place_type,
                    _display_status(related_place.identification_status, IDENTIFICATION_STATUS_LABELS),
                ]
                if part
            )
            if st.button(label, key=f"_biblical_map_related_place_{place.place_id}_{related_place.place_id}"):
                queue_place_navigation(st.session_state, related_place.place_id)
                if hasattr(st, "rerun"):
                    st.rerun()
            if meta:
                st.caption(meta)


def _render_place_enrichment(st: Any, place: BiblicalPlace) -> None:
    enrichment = get_place_enrichment(place.place_id)
    research_class = research_readiness_class(place.place_id)
    if enrichment is None:
        _render_profile_status_note(
            st,
            "basic",
            has_enrichment=False,
            research_class=research_class,
        )
        _render_related_profile_records(st, place)
        return
    source_lookup = place_enrichment_sources_by_id()
    status = enrichment_profile_status(enrichment)
    st.markdown("#### Bővített helyszínadatlap")
    _render_profile_status_note(
        st,
        status,
        has_enrichment=True,
        research_class=research_class,
    )
    if status == "needs_review":
        st.warning("A bővített adatlap egy vagy több része szakmai ellenőrzésre vár.")

    section_order = [
        "biblical_significance",
        "key_events",
        "ancient_geography",
        "historical_context",
        "archaeology",
        "modern_context",
        "identification_notes",
        "homiletical_context",
    ]
    for section_key in section_order:
        section = enrichment.sections.get(section_key)
        if isinstance(section, EnrichmentTextSection):
            _render_enrichment_text_section(
                st,
                section_key,
                section,
                source_lookup,
                expanded=section_key == "biblical_significance",
            )
        elif isinstance(section, EnrichmentKeyEventsSection):
            _render_enrichment_key_events(st, section, source_lookup)
    _render_enrichment_routes(st, enrichment)

    all_source_ids: list[str] = []
    for section in enrichment.sections.values():
        if isinstance(section, EnrichmentTextSection):
            all_source_ids.extend(section.source_ids)
        elif isinstance(section, EnrichmentKeyEventsSection):
            for item in section.items:
                all_source_ids.extend(item.source_ids)
    if all_source_ids:
        with st.expander("Források", expanded=False):
            _render_enrichment_sources(st, tuple(all_source_ids), source_lookup)
    _render_related_profile_records(st, place)


def _render_place_card(st: Any, place: BiblicalPlace, passage_reference: str) -> None:
    current_ref = passage_reference.strip()
    primary_badge = " · elsődleges helyszín" if place.is_primary else ""
    display_name = display_place_name(place)
    ancient_name = place.ancient_name or "—"
    name_en = place.name_en or "—"
    modern_country = place.modern_country or "—"
    place_type = place.place_type or "—"
    description = fallback_place_description(place)
    passage_line = (
        f"<div><strong>Aktuális igerész:</strong> {html.escape(current_ref)}</div>"
        if current_ref
        else "<div><strong>Aktuális igerész:</strong> még nincs megadva.</div>"
    )
    sources = _resolve_sources(place)
    show_card_sources = sources and any(
        source.source_id != "manual_demo_v1" for source in sources
    )
    source_line = compact_sources_html(sources) if show_card_sources else ""
    demo_source_line = (
        f'<div class="textus-biblical-map-meta"><strong>Forrás:</strong> '
        f"{html.escape(place.source_note)}</div>"
        if _uses_only_manual_demo_source(place)
        else ""
    )
    st.markdown(
        f"""
<div class="textus-biblical-map-card">
  <h4>{html.escape(display_name)}{primary_badge}</h4>
  <div class="textus-biblical-map-meta">
    <div><strong>Ókori / alternatív név:</strong> {html.escape(ancient_name)}</div>
    <div><strong>Angol név:</strong> {html.escape(name_en)}</div>
    <div><strong>Mai ország:</strong> {html.escape(modern_country)}</div>
    <div><strong>Helytípus:</strong> {html.escape(place_type)}</div>
    <div><strong>Azonosítás:</strong> {_display_status(place.identification_status, IDENTIFICATION_STATUS_LABELS)}</div>
    <div><strong>Koordináta:</strong> {place.latitude:.4f}, {place.longitude:.4f}</div>
    {passage_line}
    {source_line}
  </div>
  {f"<p>{html.escape(description)}</p>" if description else ""}
  {demo_source_line}
</div>
""",
        unsafe_allow_html=True,
    )
    _render_detail_expanders(st, place)
    _render_place_enrichment(st, place)



def _render_passage_place_selector(
    st: Any,
    *,
    linked_places: tuple[BiblicalPlace, ...],
    selected_id: str | None,
    auto_place_id: str | None,
) -> str | None:
    """Render passage-only place controls; never the full catalog."""
    labels = place_option_labels(linked_places)
    linked_ids = [place.place_id for place in linked_places]
    selection_source = str(st.session_state.get(MAP_SELECTION_SOURCE_KEY) or "")

    if not linked_ids:
        return selected_id

    if len(linked_ids) == 1:
        only_id = linked_ids[0]
        st.caption(f"Aktuális igerész helyszíne: {labels.get(only_id, only_id)}")
        if selection_source == MAP_SELECTION_SOURCE_MANUAL and selected_id and selected_id != only_id:
            # Catalog pick stays until the user changes it.
            return selected_id
        st.session_state[SELECTED_PLACE_ID_KEY] = only_id
        return only_id

    options = place_selectbox_options(linked_places, auto_place_id or selected_id)
    if selected_id not in options:
        preferred = auto_place_id if auto_place_id in options else options[0]
        st.session_state[SELECTED_PLACE_SELECTBOX_KEY] = preferred
        selected_id = preferred
        st.session_state[SELECTED_PLACE_ID_KEY] = preferred
    elif (
        selection_source == MAP_SELECTION_SOURCE_AUTO
        or st.session_state.get(SELECTED_PLACE_SELECTBOX_KEY) not in options
    ):
        st.session_state[SELECTED_PLACE_SELECTBOX_KEY] = selected_id

    current_index = options.index(selected_id) if selected_id in options else 0
    chosen_id = st.selectbox(
        "Aktuális igerész helyszínei",
        options,
        index=current_index,
        format_func=lambda place_id: labels.get(place_id, place_id),
        key=SELECTED_PLACE_SELECTBOX_KEY,
    )
    if chosen_id != selected_id:
        st.session_state[SELECTED_PLACE_ID_KEY] = chosen_id
        st.session_state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_MANUAL
        return chosen_id
    return selected_id


def _render_catalog_search(
    st: Any,
    *,
    places: tuple[BiblicalPlace, ...],
    selected_id: str | None,
) -> str | None:
    """Separate full-catalog search; picking a hit updates map/card."""
    st.text_input(
        "Másik bibliai hely keresése",
        key=CATALOG_SEARCH_QUERY_KEY,
        placeholder="pl. korinthus, athens, antiochia…",
        help="Magyar, angol, ókori, mai és alternatív nevek; ékezetfüggetlen.",
    )
    query = str(st.session_state.get(CATALOG_SEARCH_QUERY_KEY) or "").strip()
    if not query:
        if CATALOG_SEARCH_PICK_KEY in st.session_state:
            del st.session_state[CATALOG_SEARCH_PICK_KEY]
        return selected_id

    hits = search_biblical_places(query, places, limit=CATALOG_SEARCH_LIMIT)
    if not hits:
        st.caption("Nincs találat a katalógusban.")
        return selected_id

    labels = place_option_labels(hits)
    options = [place.place_id for place in hits]
    placeholder = "— válassz a találatok közül —"
    select_options = [placeholder, *options]
    current_pick = str(st.session_state.get(CATALOG_SEARCH_PICK_KEY) or "").strip()
    if current_pick not in select_options:
        st.session_state[CATALOG_SEARCH_PICK_KEY] = placeholder
    chosen = st.selectbox(
        "Keresési találatok",
        select_options,
        format_func=lambda place_id: (
            placeholder if place_id == placeholder else labels.get(place_id, place_id)
        ),
        key=CATALOG_SEARCH_PICK_KEY,
    )
    if chosen != placeholder and chosen != selected_id:
        st.session_state[SELECTED_PLACE_ID_KEY] = chosen
        st.session_state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_MANUAL
        return chosen
    return selected_id


def _render_passage_route_prompt(st: Any, current_ref: str) -> None:
    matches_by_route = route_matches_for_passage(current_ref)
    if not matches_by_route:
        return
    try:
        routes = {route.route_id: route for route in load_biblical_routes()}
    except BiblicalRouteDataError:
        return
    for route_id, stops in matches_by_route.items():
        route = routes.get(route_id)
        if route is None:
            continue
        stop_names = [
            route_stop_display_name(stop, places_by_id(BIBLICAL_MAP_PLACES).get(stop.place_id))
            for stop in stops
        ]
        st.info(
            "Ez a szakasz egy nagyobb bibliai útvonal része.\n\n"
            f"Kapcsolódó útvonal: {route.name_hu}\n\n"
            f"Érintett állomások: {', '.join(stop_names)}"
        )
        if st.button(
            "A teljes útvonal megtekintése",
            key=f"_biblical_map_open_route_{route_id}",
        ):
            switch_to_route_view_for_passage(
                st.session_state,
                route_id,
                [stop.stop_id for stop in stops],
            )
            if hasattr(st, "rerun"):
                st.rerun()


def _route_labels(routes: tuple[BiblicalRoute, ...]) -> dict[str, str]:
    return {
        route.route_id: route_option_label(route)
        for route in routes
    }


def route_evidence_tier(route: BiblicalRoute) -> str:
    tier = str(getattr(route, "route_evidence_tier", "") or "moderate")
    return tier if tier in ROUTE_EVIDENCE_TIER_MARKERS else "moderate"


def route_option_label(route: BiblicalRoute) -> str:
    tier = route_evidence_tier(route)
    marker = ROUTE_EVIDENCE_TIER_MARKERS[tier]
    label = ROUTE_EVIDENCE_TIER_LABELS[tier]
    return f"{marker} {label.capitalize()} — {route.name_hu}"


def route_phase_options(route: BiblicalRoute) -> list[str]:
    phases = []
    for stop in route.stops:
        phase = str(getattr(stop, "journey_phase", "") or "").strip()
        if phase and phase not in phases:
            phases.append(phase)
    return ["Teljes útvonal", *phases] if phases else []


def filtered_route_stops(route: BiblicalRoute, phase: str | None) -> tuple[BiblicalRouteStop, ...]:
    if not phase or phase == "Teljes útvonal":
        return route.stops
    return tuple(stop for stop in route.stops if str(getattr(stop, "journey_phase", "") or "") == phase)


def filtered_route_segments(route: BiblicalRoute, stops: tuple[BiblicalRouteStop, ...]) -> tuple:
    stop_ids = {stop.stop_id for stop in stops}
    return tuple(
        segment
        for segment in route.segments
        if segment.from_stop_id in stop_ids and segment.to_stop_id in stop_ids
    )


def compact_ancient_name_options(place: BiblicalPlace, *, limit: int = 6) -> tuple[str, ...]:
    values = [
        *place.ancient_names,
        *place.original_names,
        *place.transliterations,
    ]
    compact: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _usable_text(value)
        if not text:
            continue
        if re.search(r"\s+\d+$", text):
            continue
        normalized = normalize_place_search_text(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        compact.append(text)
        if len(compact) >= limit:
            break
    return tuple(compact)


def _all_route_place_name_options(place: BiblicalPlace) -> tuple[str, ...]:
    values = [
        *place.ancient_names,
        *place.original_names,
        *place.transliterations,
    ]
    names: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _usable_text(value)
        normalized = normalize_place_search_text(text)
        if not text or normalized in seen:
            continue
        seen.add(normalized)
        names.append(text)
    return tuple(names)


def _render_compact_route_place_card(
    st: Any,
    place: BiblicalPlace,
    passage_reference: str,
) -> None:
    display_name = display_place_name(place)
    ancient_names = compact_ancient_name_options(place)
    all_names = _all_route_place_name_options(place)
    modern_location = " · ".join(
        part for part in (place.modern_name, place.modern_country) if _usable_text(part)
    ) or "—"
    description = fallback_place_description(place)
    st.markdown(
        f"""
<div class="textus-biblical-map-card">
  <h4>{html.escape(display_name)}</h4>
  <div class="textus-biblical-map-meta">
    <div><strong>Ókori / alternatív név:</strong> {html.escape(", ".join(ancient_names) if ancient_names else "—")}</div>
    <div><strong>Angol név:</strong> {html.escape(place.name_en or "—")}</div>
    <div><strong>Mai hely:</strong> {html.escape(modern_location)}</div>
    <div><strong>Helytípus:</strong> {html.escape(place.place_type or "—")}</div>
    <div><strong>Bizonyosság:</strong> {html.escape(_display_status(place.identification_status, IDENTIFICATION_STATUS_LABELS))}</div>
    <div><strong>Kapcsolódó igehely:</strong> {html.escape(passage_reference or "—")}</div>
  </div>
  {f"<p>{html.escape(description)}</p>" if description else ""}
</div>
""",
        unsafe_allow_html=True,
    )
    if len(all_names) > len(ancient_names):
        hidden_names = [name for name in all_names if name not in ancient_names]
        with st.expander("További névváltozatok", expanded=False):
            st.markdown(", ".join(html.escape(name) for name in hidden_names))


def _render_route_legend(st: Any, segment_rows: list[dict[str, Any]]) -> None:
    items = ["szárazföldi út", "tengeri út", "visszaút", "kiválasztott állomás"]
    if any(row.get("certainty") in {"possible", "disputed", "unknown"} for row in segment_rows):
        items.append("bizonytalan szakasz")
    st.caption("Jelmagyarázat: " + " · ".join(items))


def _render_route_map(
    st: Any,
    route: BiblicalRoute,
    stop_rows: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
    selected_stop_id: str | None = None,
    map_style_id: str | None = None,
) -> None:
    if not stop_rows:
        st.warning("Ehhez az útvonalhoz nincs megjeleníthető állomás.")
        return
    viewport = route_viewport_for_selection(
        st.session_state,
        stop_rows,
        route_id=route.route_id,
        selected_stop_id=selected_stop_id,
    )
    style = effective_map_style(map_style_id or resolve_map_style_id(st.session_state))
    _render_route_legend(st, segment_rows)
    try:
        import pydeck as pdk  # type: ignore

        layers = []
        line_rows = route_line_rows(segment_rows)
        if line_rows:
            layers.append(
                pdk.Layer(
                    "PathLayer",
                    data=line_rows,
                    get_path="render_path",
                    get_color="color",
                    get_width="width",
                    width_min_pixels=2,
                    pickable=True,
                )
            )
        layers.extend(
            [
                pdk.Layer(
                    "ScatterplotLayer",
                    data=stop_rows,
                    get_position="[display_lon, display_lat]",
                    get_radius="size",
                    get_fill_color="fill_color",
                    get_line_color="line_color",
                    get_line_width="line_width",
                    line_width_min_pixels=2,
                    line_width_max_pixels=7,
                    stroked=True,
                    pickable=True,
                ),
                pdk.Layer(
                    "TextLayer",
                    data=stop_rows,
                    get_position="[display_lon, display_lat]",
                    get_text="label",
                    get_size="label_size",
                    get_color="label_color",
                    get_alignment_baseline="'center'",
                    pickable=False,
                ),
            ]
        )
        st.pydeck_chart(
            pdk.Deck(
                map_style=style.pydeck_style,
                initial_view_state=pdk.ViewState(
                    latitude=viewport["latitude"],
                    longitude=viewport["longitude"],
                    zoom=viewport["zoom"],
                ),
                layers=layers,
                tooltip={
                    "text": "{order}. {name}\n{direction} · {passage_refs}\n{stop_type_label} · {certainty_label}"
                },
            ),
            use_container_width=True,
            height=MAP_BLOCK_HEIGHT_PX,
        )
    except Exception:
        st.warning(
            "Az útvonalas térképi nézet nem érhető el; az állomásmarkerek egyszerű térképen jelennek meg."
        )
        try:
            st.map(
                stop_rows,
                latitude="display_lat",
                longitude="display_lon",
                size="size",
                color="color",
                zoom=int(viewport["zoom"]),
                use_container_width=True,
                height=MAP_BLOCK_HEIGHT_PX,
            )
        except Exception:
            st.warning("Az útvonal térképi megjelenítése most nem érhető el.")


def _render_route_view(st: Any) -> None:
    st.markdown("### Bibliai útvonalak")
    try:
        routes = load_biblical_routes()
    except BiblicalRouteDataError:
        st.warning("A bibliai útvonalak adatai most nem érhetők el.")
        return
    if not routes:
        st.caption("Még nincs betölthető bibliai útvonal.")
        return

    options = route_options(routes)
    labels = _route_labels(routes)
    (
        selected_route_id,
        selected_phase,
        selected_stop_id,
        route,
        visible_stops,
        visible_segments,
    ) = prepare_route_widget_state(st.session_state, routes)
    selected_route_id = st.selectbox(
        "Útvonal kiválasztása",
        options,
        index=options.index(selected_route_id),
        format_func=lambda route_id: labels.get(route_id, route_id),
        key=SELECTED_ROUTE_ID_KEY,
    )
    route = next(route for route in routes if route.route_id == selected_route_id)
    phase_options = route_phase_options(route)
    if phase_options:
        phase_key = route_phase_state_key(route.route_id)
        selected_phase = st.selectbox(
            "Útvonalfázis",
            phase_options,
            index=phase_options.index(selected_phase),
            key=phase_key,
        )
        visible_stops = filtered_route_stops(route, selected_phase)
        visible_segments = filtered_route_segments(route, visible_stops)
    render_route = replace(route, stops=visible_stops, segments=visible_segments)
    highlighted_stop_ids = tuple(st.session_state.get(HIGHLIGHTED_ROUTE_STOP_IDS_KEY) or ())
    valid_stop_ids = [stop.stop_id for stop in render_route.stops]
    if selected_stop_id not in valid_stop_ids:
        selected_stop_id = highlighted_stop_ids[0] if highlighted_stop_ids else valid_stop_ids[0]
        st.session_state[SELECTED_ROUTE_STOP_ID_KEY] = selected_stop_id

    st.markdown(f"**{route.name_hu}**")
    if route.family_name_hu:
        sequence_label = ""
        if route.route_family_id:
            family_routes = [item for item in routes if item.route_family_id == route.route_family_id]
            if route.route_sequence_order:
                sequence_label = f" · {route.route_sequence_order}/{len(family_routes)}"
        st.caption(f"Útvonalcsalád: {route.family_name_hu}{sequence_label}")
    st.caption(
        "Elsődleges szakasz: "
        + ", ".join(route.primary_passage_refs)
        + (f" · {route.chronology_label_hu}" if route.chronology_label_hu else "")
    )
    evidence_tier = route_evidence_tier(route)
    st.caption(ROUTE_EVIDENCE_TIER_NOTES_HU[evidence_tier])
    st.caption(
        f"Geometria: {_display_status(route.geometry_status, GEOMETRY_STATUS_LABELS)}"
    )
    mapped_stop_count = sum(1 for stop in route.stops if stop.display_on_map)
    textual_stop_count = len(route.stops) - mapped_stop_count
    st.caption(
        f"Állomások: {len(route.stops)} · "
        f"térképen: {mapped_stop_count} · "
        f"csak szövegben ismert: {textual_stop_count}"
    )
    st.warning(ROUTE_VIEW_WARNING_HU)
    map_style_id = render_map_style_selector(st)

    stop_rows = route_stop_rows(
        render_route,
        selected_stop_id=selected_stop_id,
        highlighted_stop_ids=highlighted_stop_ids,
    )
    segment_rows = route_segment_rows(render_route)
    _render_map_block_open(st)
    _render_route_map(
        st,
        route,
        stop_rows,
        segment_rows,
        selected_stop_id=selected_stop_id,
        map_style_id=map_style_id,
    )
    _render_map_block_close(st)
    st.caption(ROUTE_EVIDENCE_LEGEND_HU)

    stop_labels = {
        stop.stop_id: (
            f"{stop.order}. "
            f"{route_stop_display_name(stop, places_by_id(BIBLICAL_MAP_PLACES).get(stop.place_id))} "
            f"– {route_direction_label(stop)}"
        )
        for stop in route.stops
    }
    _render_section_heading(st, "Állomás részletei")
    chosen_stop_id = st.selectbox(
        "Állomás kiválasztása",
        valid_stop_ids,
        index=valid_stop_ids.index(selected_stop_id),
        format_func=lambda stop_id: stop_labels.get(stop_id, stop_id),
        key=SELECTED_ROUTE_STOP_ID_KEY,
    )
    selected_stop = next(stop for stop in render_route.stops if stop.stop_id == chosen_stop_id)
    selected_place = places_by_id(BIBLICAL_MAP_PLACES).get(selected_stop.place_id)
    st.markdown(
        f"**{selected_stop.order}. {route_stop_display_name(selected_stop, selected_place)} – "
        f"{route_direction_label(selected_stop)}**"
    )
    st.caption(
        f"Igehely: {', '.join(selected_stop.passage_refs)} · "
        f"{_display_status(selected_stop.stop_type, STOP_TYPE_LABELS)} · "
        f"{_display_status(selected_stop.certainty, CERTAINTY_LABELS)}"
    )
    if selected_stop.mapping_status == "textual_only":
        st.warning("A hely pontos földrajzi azonosítása nem ismert.")
        if selected_stop.mapping_notes_hu:
            st.caption(selected_stop.mapping_notes_hu)
    st.markdown(selected_stop.event_summary_hu)
    if selected_place is not None:
        _render_compact_route_place_card(
            st,
            selected_place,
            ", ".join(selected_stop.passage_refs),
        )

    if route.previous_route_id or route.next_route_id:
        if route.previous_route_id and st.button("Előző szakasz"):
            queue_route_navigation(st.session_state, route.previous_route_id)
            if hasattr(st, "rerun"):
                st.rerun()
        if route.next_route_id and st.button("Következő szakasz"):
            queue_route_navigation(st.session_state, route.next_route_id)
            if hasattr(st, "rerun"):
                st.rerun()

    _render_section_heading(st, "Állomások")
    for stop in render_route.stops:
        place = places_by_id(BIBLICAL_MAP_PLACES).get(stop.place_id)
        emphasis = "**" if stop.stop_id in highlighted_stop_ids else ""
        textual_note = (
            "  \nA hely pontos földrajzi azonosítása nem ismert."
            if stop.mapping_status == "textual_only"
            else ""
        )
        st.markdown(
            f"{emphasis}{stop.order}. {route_stop_display_name(stop, place)} – "
            f"{route_direction_label(stop)}{emphasis}  \n"
            f"{stop.event_summary_hu}  \n"
            f"`{', '.join(stop.passage_refs)}` · "
            f"{_display_status(stop.stop_type, STOP_TYPE_LABELS)} · "
            f"{_display_status(stop.certainty, CERTAINTY_LABELS)}"
            f"{textual_note}"
        )


def _render_places_view(
    st: Any,
    *,
    passage_reference: str | None,
    places: tuple[BiblicalPlace, ...],
) -> None:
    current_ref = (passage_reference or "").strip()
    if current_ref:
        st.caption(f"Aktuális igerész: {current_ref}")
    else:
        st.caption("Aktuális igerész még nincs megadva.")
    if not places:
        st.warning("A bibliai térkép prototípus helyadatai nem érhetőek el.")
        return

    auto_link = apply_passage_place_selection(
        st.session_state,
        current_ref,
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )
    apply_pending_place_navigation_state(st.session_state, places)
    linked_places = passage_linked_places(current_ref, places)
    selected_id = resolve_selected_place_id(st.session_state, places)
    by_id = places_by_id(places)

    st.markdown(
        '<div class="textus-biblical-map-note">'
        "A térkép az aktuális igerészhez kapcsolódó bibliai helyszíneket jeleníti meg."
        "</div>",
        unsafe_allow_html=True,
    )
    if current_ref:
        _render_passage_route_prompt(st, current_ref)

    map_focus_id = selected_id or (
        auto_link.place_id if auto_link is not None else primary_place(places).place_id
    )
    map_places = linked_places or (
        (by_id[map_focus_id],) if map_focus_id in by_id else ()
    )
    map_style_id = render_map_style_selector(st)
    _render_places_map_block(
        st,
        map_focus_id=map_focus_id,
        map_places=map_places,
        map_style_id=map_style_id,
    )

    _render_section_heading(st, "Helyszín kiválasztása")
    selected_id = _render_passage_place_selector(
        st,
        linked_places=linked_places,
        selected_id=selected_id,
        auto_place_id=auto_link.place_id if auto_link is not None else None,
    )
    selected_id = _render_catalog_search(
        st,
        places=places,
        selected_id=selected_id,
    )

    selection_source = str(st.session_state.get(MAP_SELECTION_SOURCE_KEY) or "")
    if selected_id:
        st.session_state[SELECTED_PLACE_ID_KEY] = selected_id

    selected_place = by_id.get(selected_id) if selected_id else None
    if selected_place is None and auto_link is not None:
        selected_place = by_id.get(auto_link.place_id)
    if selected_place is None and linked_places:
        selected_place = linked_places[0]

    if current_ref and selection_source == MAP_SELECTION_SOURCE_AUTO and auto_link is not None:
        display_name = (
            display_place_name(selected_place)
            if selected_place is not None
            else display_place_name(by_id.get(auto_link.place_id))
            if by_id.get(auto_link.place_id) is not None
            else auto_link.place_id
        )
        st.info(
            "A helyszín a megadott igerész alapján automatikusan lett "
            f"kiválasztva: {display_name}."
        )
    elif current_ref and selection_source == MAP_SELECTION_SOURCE_MANUAL and selected_place:
        st.caption("A jelenlegi helyszínt kézzel választottad ki.")
    elif current_ref and not linked_places:
        st.caption(
            "Ehhez az igerészhez a prototípus még nem tartalmaz automatikus helykapcsolatot."
        )

    _render_section_heading(st, "Kiválasztott hely")
    if selected_place is not None:
        _render_place_card(st, selected_place, passage_reference or "")
    else:
        st.caption(
            "Válassz helyszínt a keresőből, vagy adj meg olyan igerészt, "
            "amelyhez van helykapcsolat."
        )


def render_biblical_map_prototype(
    passage_reference: str | None = None,
    *,
    st_module: Any | None = None,
) -> None:
    """Render the biblical map prototype in the Textus workshop."""
    st = st_module or _streamlit()
    places = BIBLICAL_MAP_PLACES

    _render_styles(st)
    container = getattr(st, "container", None)
    map_cta = container(key="biblical_map_cta") if callable(container) else nullcontext()
    with map_cta:
        with st.expander("Bibliai térkép", expanded=False):
            st.caption(MAP_SCOPE_NOTE_HU)
            st.caption(
                "Az útvonalnézet vázlatos (draft/schematic): a vonalak nem pontos ókori nyomvonalak."
            )
            apply_pending_route_navigation_state(st.session_state)
            view_options = [MAP_VIEW_PLACES, MAP_VIEW_ROUTES]
            current_view = str(st.session_state.get(ACTIVE_MAP_VIEW_KEY) or MAP_VIEW_PLACES)
            if current_view not in view_options:
                current_view = MAP_VIEW_PLACES
            active_view = st.radio(
                "Térkép nézet",
                view_options,
                index=view_options.index(current_view),
                horizontal=True,
                key=ACTIVE_MAP_VIEW_KEY,
            )
            if active_view == MAP_VIEW_ROUTES:
                _render_route_view(st)
            else:
                _render_places_view(st, passage_reference=passage_reference, places=places)


__all__ = [
    "ACTIVE_MAP_VIEW_KEY",
    "CATALOG_SEARCH_LIMIT",
    "CATALOG_SEARCH_PICK_KEY",
    "CATALOG_SEARCH_QUERY_KEY",
    "CERTAINTY_LABELS",
    "GEOMETRY_STATUS_LABELS",
    "HIGHLIGHTED_ROUTE_STOP_IDS_KEY",
    "LAST_FOCUSED_ROUTE_STOP_ID_KEY",
    "LAST_RENDERED_ROUTE_ID_KEY",
    "MAP_STYLE_CLEAN",
    "MAP_STYLE_CONFIGS",
    "MAP_STYLE_HISTORICAL_MOOD",
    "MAP_STYLE_KEY",
    "MAP_STYLE_OPTIONS",
    "MAP_STYLE_TERRAIN",
    "MAP_VIEW_PLACES",
    "MAP_VIEW_ROUTES",
    "PENDING_MAP_VIEW_KEY",
    "PENDING_PLACE_ID_KEY",
    "PENDING_ROUTE_ID_KEY",
    "PENDING_ROUTE_STOP_IDS_KEY",
    "ROUTE_VIEWPORT_STATE_KEY",
    "SELECTED_PLACE_ID_KEY",
    "SELECTED_PLACE_SELECTBOX_KEY",
    "SELECTED_ROUTE_ID_KEY",
    "SELECTED_ROUTE_STOP_ID_KEY",
    "ROUTE_VIEW_WARNING_HU",
    "ROUTE_EVIDENCE_LEGEND_HU",
    "ROUTE_EVIDENCE_TIER_LABELS",
    "ROUTE_EVIDENCE_TIER_MARKERS",
    "ROUTE_EVIDENCE_TIER_NOTES_HU",
    "SEGMENT_TYPE_LABELS",
    "STOP_TYPE_LABELS",
    "compact_ancient_name_options",
    "compact_sources_html",
    "compact_sources_markdown",
    "dedupe_sources",
    "apply_pending_route_navigation_state",
    "apply_pending_place_navigation_state",
    "map_rows",
    "filtered_route_segments",
    "filtered_route_stops",
    "normalize_place_search_text",
    "passage_linked_places",
    "place_option_labels",
    "place_selectbox_options",
    "render_biblical_map_prototype",
    "render_map_style_selector",
    "research_readiness_class",
    "prepare_route_widget_state",
    "queue_route_navigation",
    "queue_place_navigation",
    "resolve_selected_place_id",
    "resolve_map_style_id",
    "MAP_SCOPE_NOTE_HU",
    "route_viewport_for_selection",
    "route_matches_for_passage",
    "route_curve_profile",
    "route_evidence_tier",
    "route_line_rows",
    "route_option_label",
    "route_segment_rows",
    "route_phase_options",
    "route_phase_state_key",
    "schematic_segment_path",
    "route_stop_display_name",
    "route_stop_rows",
    "route_viewport",
    "selected_route_stop_focus_viewport",
    "selected_route_stop_row",
    "search_biblical_places",
    "selected_place_for_session",
    "switch_to_route_view_for_passage",
]
