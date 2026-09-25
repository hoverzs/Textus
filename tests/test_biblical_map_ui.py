from __future__ import annotations

import importlib
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
APP_SOURCE = ROOT / "app.py"
BIBLE_TEXT_UI_SOURCE = ROOT / "bible_text_ui.py"

from biblical_map_data import (
    BIBLICAL_MAP_PLACES,
    BIBLICAL_PLACES_CATALOG_PATH,
    BiblicalMapDataError,
    BiblicalPlace,
    BiblicalMapSource,
    PILOT_PLACES_PATH,
    SOURCES_PATH,
    get_all_biblical_places,
    get_biblical_place,
    load_biblical_places,
    load_pilot_biblical_places,
    load_biblical_sources,
    validate_place_record,
)
from biblical_map_ui import (
    ACTIVE_MAP_VIEW_KEY,
    CATALOG_SEARCH_PICK_KEY,
    CATALOG_SEARCH_QUERY_KEY,
    CERTAINTY_LABELS,
    GEOMETRY_STATUS_LABELS,
    HIGHLIGHTED_ROUTE_STOP_IDS_KEY,
    LAST_FOCUSED_ROUTE_STOP_ID_KEY,
    LAST_RENDERED_ROUTE_ID_KEY,
    MAP_SCOPE_NOTE_HU,
    MAP_STYLE_CLEAN,
    MAP_STYLE_CONFIGS,
    MAP_STYLE_HISTORICAL_MOOD,
    MAP_STYLE_KEY,
    MAP_STYLE_OPTIONS,
    MAP_STYLE_TERRAIN,
    MAP_VIEW_PLACES,
    MAP_VIEW_ROUTES,
    PENDING_MAP_VIEW_KEY,
    PENDING_PLACE_ID_KEY,
    PENDING_ROUTE_ID_KEY,
    PENDING_ROUTE_STOP_IDS_KEY,
    ROUTE_EVIDENCE_LEGEND_HU,
    ROUTE_EVIDENCE_TIER_NOTES_HU,
    ROUTE_VIEW_WARNING_HU,
    ROUTE_VIEWPORT_STATE_KEY,
    SEGMENT_TYPE_LABELS,
    SELECTED_ROUTE_ID_KEY,
    SELECTED_ROUTE_STOP_ID_KEY,
    STOP_TYPE_LABELS,
    SELECTED_PLACE_SELECTBOX_KEY,
    SELECTED_PLACE_ID_KEY,
    research_readiness_class,
    route_evidence_tier,
    route_option_label,
    _display_status,
    _render_place_card,
    _render_short_sources,
    compact_ancient_name_options,
    compact_sources_html,
    compact_sources_markdown,
    dedupe_sources,
    display_place_name,
    fallback_place_description,
    apply_pending_route_navigation_state,
    apply_pending_place_navigation_state,
    map_rows,
    normalize_place_search_text,
    passage_linked_places,
    place_option_labels,
    place_selectbox_options,
    render_biblical_map_prototype,
    render_map_style_selector,
    prepare_route_widget_state,
    queue_route_navigation,
    queue_place_navigation,
    resolve_selected_place_id,
    resolve_map_style_id,
    route_viewport_for_selection,
    route_curve_profile,
    filtered_route_segments,
    filtered_route_stops,
    route_line_rows,
    route_matches_for_passage,
    route_phase_options,
    route_phase_state_key,
    route_segment_rows,
    route_stop_rows,
    route_viewport,
    selected_route_stop_focus_viewport,
    selected_route_stop_row,
    schematic_segment_path,
    search_biblical_places,
    selected_place_for_session,
    switch_to_route_view_for_passage,
)
from biblical_routes import load_biblical_routes, route_options
from biblical_map_passages import (
    BIBLICAL_PASSAGE_PLACE_LINKS,
    MAP_LAST_PROCESSED_REFERENCE_KEY,
    MAP_SELECTION_SOURCE_AUTO,
    MAP_SELECTION_SOURCE_KEY,
    MAP_SELECTION_SOURCE_MANUAL,
    MAP_SELECTION_SOURCE_UNMATCHED,
    PASSAGE_LINK_SOURCE_NOTE,
    PASSAGE_LINK_TYPE_PRIMARY_EVENT_LOCATION,
    apply_passage_place_selection,
    find_place_links_for_passage,
    find_primary_place_for_passage,
    validate_passage_place_links,
)


class _FakeContext:
    def __init__(self, fake_st):
        self.fake_st = fake_st

    def __enter__(self):
        return self.fake_st

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeSessionState(dict):
    def __init__(self, *, enforce_widget_lock: bool = False):
        super().__init__()
        self.enforce_widget_lock = enforce_widget_lock
        self.locked_keys = set()

    def __setitem__(self, key, value):
        if self.enforce_widget_lock and key in self.locked_keys:
            current = self.get(key)
            if current != value:
                raise RuntimeError(f"widget-backed key modified after widget creation: {key}")
        super().__setitem__(key, value)

    def lock_widget_key(self, key):
        if key:
            self.locked_keys.add(key)


class _FakeStreamlit:
    def __init__(
        self,
        *,
        fail_map: bool = False,
        selectbox_choice: str | None = None,
        clicked_buttons: set[str] | None = None,
        enforce_widget_lock: bool = False,
    ):
        self.session_state = _FakeSessionState(enforce_widget_lock=enforce_widget_lock)
        self.fail_map = fail_map
        self.selectbox_choice = selectbox_choice
        self.clicked_buttons = clicked_buttons or set()
        self.captions = []
        self.errors = []
        self.expanders = []
        self.infos = []
        self.markdowns = []
        self.maps = []
        self.pydeck_charts = []
        self.radios = []
        self.selectboxes = []
        self.text_inputs = []
        self.warnings = []
        self.buttons = []
        self.columns_calls = []

    def expander(self, label, expanded=False):
        self.expanders.append((label, expanded))
        return _FakeContext(self)

    def container(self, *args, **kwargs):
        return _FakeContext(self)

    def columns(self, spec, gap=None):
        self.columns_calls.append((spec, gap))
        return [_FakeContext(self), _FakeContext(self)]

    def markdown(self, body, **kwargs):
        self.markdowns.append(body)

    def caption(self, body):
        self.captions.append(body)

    def error(self, body):
        self.errors.append(body)

    def info(self, body):
        self.infos.append(body)

    def warning(self, body):
        self.warnings.append(body)

    def map(self, rows, **kwargs):
        if self.fail_map:
            raise TypeError("unsupported st.map parameter")
        self.maps.append((rows, kwargs))

    def pydeck_chart(self, deck, **kwargs):
        if self.fail_map:
            raise TypeError("unsupported st.pydeck_chart parameter")
        self.pydeck_charts.append((deck, kwargs))

    def radio(self, label, options, index=0, **kwargs):
        self.radios.append((label, options, index, kwargs))
        key = kwargs.get("key")
        chosen = self.session_state.get(key) if key else None
        if chosen not in options:
            chosen = options[index]
        if key:
            self.session_state[key] = chosen
            self.session_state.lock_widget_key(key)
        return chosen

    def button(self, label, **kwargs):
        self.buttons.append((label, kwargs))
        return label in self.clicked_buttons

    def text_input(self, label, **kwargs):
        self.text_inputs.append((label, kwargs))
        key = kwargs.get("key")
        if key and key not in self.session_state:
            self.session_state[key] = ""
        if key:
            self.session_state.lock_widget_key(key)
        return self.session_state.get(key, "")

    def selectbox(self, label, options, index=0, **kwargs):
        self.selectboxes.append((label, options, index, kwargs))
        key = kwargs.get("key")
        if self.selectbox_choice is not None and self.selectbox_choice in options:
            chosen = self.selectbox_choice
        else:
            chosen = self.session_state.get(key) if key else None
            if chosen not in options:
                chosen = options[index]
        if key:
            self.session_state[key] = chosen
            self.session_state.lock_widget_key(key)
        return chosen


def test_biblical_place_ids_are_unique() -> None:
    ids = [place.place_id for place in BIBLICAL_MAP_PLACES]
    assert len(ids) > 100
    assert len(ids) == len(set(ids))


def test_full_catalog_loads_and_pilot_remains_override_layer() -> None:
    assert PILOT_PLACES_PATH.exists()
    assert BIBLICAL_PLACES_CATALOG_PATH.exists()
    assert SOURCES_PATH.exists()
    raw_places = json.loads(PILOT_PLACES_PATH.read_text(encoding="utf-8"))
    raw_catalog = json.loads(BIBLICAL_PLACES_CATALOG_PATH.read_text(encoding="utf-8"))
    raw_sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    data_source = (ROOT / "biblical_map_data.py").read_text(encoding="utf-8")

    assert isinstance(raw_places, list)
    assert isinstance(raw_catalog, list)
    assert isinstance(raw_sources, list)
    assert len(raw_places) == 10
    assert len(load_pilot_biblical_places()) == 10
    assert len(load_biblical_places()) == len(raw_catalog) > 100
    assert len(get_all_biblical_places()) == len(raw_catalog) > 100
    assert "BIBLICAL_MAP_PLACES: tuple[BiblicalPlace, ...] = (" not in data_source
    assert data_source.count("BiblicalPlace(") == 1


def test_sources_json_loads_and_demo_source_is_present() -> None:
    sources = load_biblical_sources()
    by_id = {source.source_id: source for source in sources}

    assert "manual_demo_v1" in by_id
    assert by_id["manual_demo_v1"].source_type == "manual_demo"
    assert by_id["manual_demo_v1"].reliability_tier == "prototype_only"
    assert by_id["openbible_geocoding_cc_by_4_0"].license == "CC-BY-4.0"
    assert by_id["pleiades_corinth_570182"].reliability_tier == "scholarly_curated"
    assert (
        by_id["ascsa_ancient_corinth_history"].source_type
        == "scholarly_archaeological_reference"
    )
    assert by_id["hellenic_ministry_ancient_corinth"].provider == "Hellenic Ministry of Culture"
    assert by_id["pleiades_ephesus_599612"].reliability_tier == "scholarly_curated"
    assert by_id["unesco_ephesus_1018"].provider == "UNESCO World Heritage Centre"
    assert (
        by_id["turkiye_ephesus_archaeological_site"].source_type
        == "official_archaeological_site"
    )


def test_biblical_places_have_valid_names_and_coordinates() -> None:
    names = {place.name_hu for place in BIBLICAL_MAP_PLACES}
    assert {
        "Jeruzsálem",
        "Názáret",
        "Kapernaum",
        "Korinthus",
        "Efezus",
        "Athén",
        "Filippi",
        "Thesszalonika",
        "Antiókhia",
        "Róma",
    }.issubset(names)
    for place in BIBLICAL_MAP_PLACES:
        assert place.name_hu.strip()
        assert place.place_id.strip()
        assert validate_place_record(place)
        assert -90 <= place.latitude <= 90
        assert -180 <= place.longitude <= 180
        assert place.geometry_type == "point"
        assert place.coordinate_source_id
        assert place.source_ids


def test_biblical_map_has_exactly_one_primary_place() -> None:
    primary_places = [place for place in BIBLICAL_MAP_PLACES if place.is_primary]
    assert len(primary_places) == 1
    assert primary_places[0].place_id == "jerusalem"


def test_hungarian_accents_load_from_json() -> None:
    jerusalem = get_biblical_place("jerusalem")
    nazareth = get_biblical_place("nazareth")

    assert jerusalem is not None
    assert nazareth is not None
    assert jerusalem.name_hu == "Jeruzsálem"
    assert nazareth.name_hu == "Názáret"


def test_corinth_pilot_record_contains_source_marked_details() -> None:
    corinth = get_biblical_place("corinth")

    assert corinth is not None
    assert corinth.identification_status == "certain"
    assert corinth.modern_country == "Görögország"
    assert "Κόρινθος" in corinth.original_names
    assert corinth.coordinate_source_id == "pleiades_corinth_570182"
    assert corinth.pleiades_id == "570182"
    assert corinth.translation_status == "not_required"
    assert corinth.translation_method == "human_authored_source_synthesis"
    assert corinth.review_status == "draft"
    assert set(corinth.source_ids) >= {
        "pleiades_corinth_570182",
        "ascsa_ancient_corinth_history",
        "hellenic_ministry_ancient_corinth",
    }
    assert len(corinth.exegetical_notes) == 1
    assert corinth.exegetical_notes[0].passage_reference == "ApCsel 18,1–18"


def test_non_corinth_records_are_import_reviewed_shells() -> None:
    by_id = {place.place_id: place for place in BIBLICAL_MAP_PLACES}

    assert "openbible_geocoding_cc_by_4_0" in by_id["jerusalem"].source_ids
    assert by_id["nazareth"].coordinate_source_id == "openbible_geocoding_cc_by_4_0"
    assert by_id["capernaum"].review_status == "draft"
    assert by_id["athens"].place_id == "athens"
    assert by_id["antioch_syria"].name_hu == "Antiókhia"


def test_ephesus_pilot_record_contains_source_marked_details() -> None:
    ephesus = get_biblical_place("ephesus")

    assert ephesus is not None
    assert ephesus.identification_status == "certain"
    assert ephesus.modern_country == "Törökország"
    assert "Ἔφεσος" in ephesus.original_names
    assert ephesus.coordinate_source_id == "pleiades_ephesus_599612"
    assert ephesus.pleiades_id == "599612"
    assert ephesus.translation_status == "not_required"
    assert ephesus.translation_method == "human_authored_source_synthesis"
    assert ephesus.review_status == "draft"
    assert set(ephesus.source_ids) >= {
        "pleiades_ephesus_599612",
        "unesco_ephesus_1018",
        "turkiye_ephesus_archaeological_site",
    }
    assert len(ephesus.exegetical_notes) == 1
    assert ephesus.exegetical_notes[0].passage_reference == "ApCsel 19,1–41"


def test_missing_optional_background_fields_do_not_break_loading() -> None:
    raw_places = json.loads(PILOT_PLACES_PATH.read_text(encoding="utf-8"))
    raw_places[0].pop("history_hu", None)
    raw_places[0]["unexpected_optional_field"] = "ignored"
    with tempfile.TemporaryDirectory() as tmp_dir:
        places_path = Path(tmp_dir) / "places.json"
        places_path.write_text(json.dumps(raw_places, ensure_ascii=False), encoding="utf-8")
        places = load_biblical_places(places_path=places_path)

    by_id = {place.place_id: place for place in places}
    assert by_id["jerusalem"].history_hu is None
    assert by_id["jerusalem"].name_hu == "Jeruzsálem"


def test_missing_required_field_raises_validation_error() -> None:
    raw_places = json.loads(PILOT_PLACES_PATH.read_text(encoding="utf-8"))
    raw_places[0].pop("place_id", None)
    with tempfile.TemporaryDirectory() as tmp_dir:
        places_path = Path(tmp_dir) / "places.json"
        places_path.write_text(json.dumps(raw_places, ensure_ascii=False), encoding="utf-8")
        try:
            load_biblical_places(places_path=places_path)
        except BiblicalMapDataError as exc:
            assert "place_id" in str(exc)
        else:
            raise AssertionError("Missing required field did not raise BiblicalMapDataError.")


def test_unknown_selected_place_id_falls_back_to_none() -> None:
    session_state = {SELECTED_PLACE_ID_KEY: "unknown-place"}
    assert resolve_selected_place_id(session_state) is None


def test_existing_selected_place_id_is_preserved() -> None:
    session_state = {SELECTED_PLACE_ID_KEY: "ephesus"}
    assert resolve_selected_place_id(session_state) == "ephesus"


def test_selected_place_for_session_returns_primary_without_selection() -> None:
    assert selected_place_for_session({}).place_id == "jerusalem"


def test_map_rows_mark_primary_or_selected_as_larger() -> None:
    rows = map_rows("ephesus")
    by_id = {row["place_id"]: row for row in rows}
    assert by_id["jerusalem"]["size"] > by_id["nazareth"]["size"]
    assert by_id["ephesus"]["size"] > by_id["nazareth"]["size"]


def test_demo_passage_links_have_valid_shape_and_places() -> None:
    valid_ids = {place.place_id for place in BIBLICAL_MAP_PLACES}

    assert len(BIBLICAL_PASSAGE_PLACE_LINKS) >= 10
    for link in BIBLICAL_PASSAGE_PLACE_LINKS:
        assert link.normalized_reference.strip()
        assert link.place_id in valid_ids
        assert link.link_type == PASSAGE_LINK_TYPE_PRIMARY_EVENT_LOCATION
        assert link.reason_hu.strip()
        assert link.source_note.strip()
    assert validate_passage_place_links() == BIBLICAL_PASSAGE_PLACE_LINKS


def test_every_place_source_reference_resolves() -> None:
    source_ids = {source.source_id for source in load_biblical_sources()}

    for place in BIBLICAL_MAP_PLACES:
        assert place.coordinate_source_id in source_ids
        assert set(place.source_ids).issubset(source_ids)
        for note in place.exegetical_notes:
            assert set(note.source_ids).issubset(source_ids)


def test_demo_passages_resolve_to_expected_places() -> None:
    assert find_primary_place_for_passage("ApCsel 18,1–18") == "corinth"
    assert find_primary_place_for_passage("ApCsel 18,1–5") == "corinth"
    assert find_primary_place_for_passage("Ef 1,1–14") == "ephesus"
    assert find_primary_place_for_passage("ApCsel 19,1–41") == "ephesus"
    assert find_primary_place_for_passage("ApCsel 19,1–10") == "ephesus"
    assert find_primary_place_for_passage("ApCsel 19,21–41") == "ephesus"
    assert find_primary_place_for_passage("ApCsel 19") == "ephesus"
    assert find_primary_place_for_passage("Mt 2,23") == "nazareth"
    assert find_primary_place_for_passage("Mk 1,21–28") == "capernaum"
    assert find_primary_place_for_passage("ApCsel 2,1–13") == "jerusalem"
    assert find_primary_place_for_passage("ApCsel 17,16–34") == "athens"
    assert find_primary_place_for_passage("ApCsel 16,11–40") == "philippi"
    assert find_primary_place_for_passage("ApCsel 17,1–9") == "thessalonica"
    assert find_primary_place_for_passage("ApCsel 11,19–30") == "antioch_syria"
    assert find_primary_place_for_passage("ApCsel 28,11–31") == "rome"


def test_unknown_empty_and_invalid_passages_do_not_resolve() -> None:
    assert find_primary_place_for_passage(None) is None
    assert find_primary_place_for_passage("") is None
    assert find_primary_place_for_passage("not a reference") is None
    assert find_primary_place_for_passage("Jn 3,16") is None
    assert find_primary_place_for_passage("ApCsel 18") == "corinth"


def test_all_resolved_place_ids_exist_in_prototype_places() -> None:
    valid_ids = {place.place_id for place in BIBLICAL_MAP_PLACES}

    for link in BIBLICAL_PASSAGE_PLACE_LINKS:
        assert link.place_id in valid_ids
    assert validate_passage_place_links() == BIBLICAL_PASSAGE_PLACE_LINKS


def test_auto_selection_updates_for_new_supported_reference() -> None:
    state = {}

    apply_passage_place_selection(
        state,
        "ApCsel 18,1-18",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )

    assert state[SELECTED_PLACE_ID_KEY] == "corinth"
    assert state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO
    assert state[MAP_LAST_PROCESSED_REFERENCE_KEY] == "ApCsel 18,1–18"


def test_manual_selection_is_preserved_for_same_reference() -> None:
    state = {}
    apply_passage_place_selection(
        state,
        "ApCsel 18,1-18",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )
    state[SELECTED_PLACE_ID_KEY] = "ephesus"
    state[MAP_SELECTION_SOURCE_KEY] = MAP_SELECTION_SOURCE_MANUAL

    apply_passage_place_selection(
        state,
        "ApCsel 18,1-18",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )

    assert state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_MANUAL


def test_new_supported_reference_can_override_manual_selection() -> None:
    state = {
        SELECTED_PLACE_ID_KEY: "ephesus",
        MAP_SELECTION_SOURCE_KEY: MAP_SELECTION_SOURCE_MANUAL,
        MAP_LAST_PROCESSED_REFERENCE_KEY: "ApCsel 18,1–18",
    }

    apply_passage_place_selection(
        state,
        "Mk 1,21-28",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )

    assert state[SELECTED_PLACE_ID_KEY] == "capernaum"
    assert state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO


def test_new_unsupported_reference_does_not_pick_arbitrary_place() -> None:
    state = {
        SELECTED_PLACE_ID_KEY: "ephesus",
        MAP_SELECTION_SOURCE_KEY: MAP_SELECTION_SOURCE_MANUAL,
        MAP_LAST_PROCESSED_REFERENCE_KEY: "ApCsel 18,1–18",
    }

    apply_passage_place_selection(
        state,
        "Jn 3,16",
        selected_place_key=SELECTED_PLACE_ID_KEY,
    )

    assert state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_UNMATCHED


def test_ui_module_imports_without_secret_or_network_access() -> None:
    module = importlib.import_module("biblical_map_ui")
    assert callable(module.render_biblical_map_prototype)


def test_app_imports_biblical_map_renderer() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")

    assert "from biblical_map_ui import render_biblical_map_prototype" in source


def test_map_call_is_in_igehely_panel_after_overview_button() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    helper_start = source.index("def render_current_biblical_map_prototype() -> None:")
    helper_end = source.index("def render_igehely_panel(", helper_start)
    helper_source = source[helper_start:helper_end]

    panel_start = source.index("def render_igehely_panel(")
    panel_end = source.index("def render_original_text_panel() -> None:", panel_start)
    panel_source = source[panel_start:panel_end]

    button_index = panel_source.index('"Bibliai háttér összegzése"')
    map_index = panel_source.index("render_current_biblical_map_prototype()")
    overview_result_index = panel_source.index(
        'if st.session_state.get("overview"):',
        button_index,
    )

    assert button_index < map_index < overview_result_index
    assert 'st.caption("Bibliai térkép renderpont elérve.")' not in source
    assert "SMART-MAP BIZTOS RENDERPONT ELÉRVE" not in source
    assert source.count("render_current_biblical_map_prototype()") == 2
    assert 'st.caption("Bibliai térkép modul")' not in source
    assert "render_biblical_map_prototype(passage_reference=passage_reference)" in helper_source
    assert "or None" in helper_source
    assert '(st.session_state.get("last_igehely") or "").strip()' in helper_source
    assert '(st.session_state.get("igehely_input") or "").strip()' in helper_source


def test_bible_text_editor_has_no_map_callback_or_renderer() -> None:
    bible_text_source = BIBLE_TEXT_UI_SOURCE.read_text(encoding="utf-8")

    assert "Callable" not in bible_text_source
    assert "after_bible_text" not in bible_text_source
    assert "render_biblical_map_prototype" not in bible_text_source


def test_exactly_one_active_ui_map_render_call() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    map_ui_source = (ROOT / "biblical_map_ui.py").read_text(encoding="utf-8")
    render_fn_start = map_ui_source.index("def render_biblical_map_prototype(")
    expander_index = map_ui_source.index(
        'with st.expander("Bibliai térkép", expanded=False):',
        render_fn_start,
    )
    before_expander = map_ui_source[render_fn_start:expander_index]

    assert source.count("render_biblical_map_prototype(") == 1
    assert "SMART-MAP RENDERFÜGGVÉNY ELINDULT" not in map_ui_source
    assert "Első izolált prototípus" not in map_ui_source
    assert "Még nincs automatikus kapcsolat" not in map_ui_source
    assert 'st.radio(\n                "Térkép nézet",' in map_ui_source
    assert "SELECTED_PLACE_RADIO_KEY" not in map_ui_source
    assert "st.selectbox(" in map_ui_source
    assert map_ui_source.count("Bibliai térkép") == 1
    assert "return" not in before_expander
    assert "passage_reference" not in before_expander.split("st_module", 1)[-1]
    assert "if not places" not in before_expander
    assert "try:" not in before_expander


def test_render_accepts_missing_passage_reference_without_early_return() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference=None, st_module=fake_st)

    assert fake_st.errors == []
    assert ("Bibliai térkép", False) in fake_st.expanders
    assert "A térképes prototípus renderelése aktív." not in fake_st.captions
    assert "Aktuális igerész még nincs megadva." in fake_st.captions
    assert any(
        "belső / béta előtti prototípus" in caption for caption in fake_st.captions
    )
    assert fake_st.maps
    assert fake_st.maps[-1][1]["use_container_width"] is True
    assert fake_st.maps[-1][1]["height"] == 520
    assert fake_st.text_inputs
    assert fake_st.text_inputs[0][0] == "Másik bibliai hely keresése"
    assert not any(label == "Aktuális igerész helyszínei" for label, *_ in fake_st.selectboxes)
    assert [label for label, *_ in fake_st.radios] == ["Térkép nézet"]
    assert any(
        "A térkép az aktuális igerészhez kapcsolódó bibliai helyszíneket jeleníti meg."
        in body
        for body in fake_st.markdowns
    )
    assert any(
        "Válassz helyszínt a keresőből" in caption for caption in fake_st.captions
    )
    assert fake_st.columns_calls == []


def test_render_auto_selects_linked_place_and_shows_status() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-5", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "corinth"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO
    assert (
        "A helyszín a megadott igerész alapján automatikusan lett kiválasztva: Korinthus."
        in fake_st.infos
    )
    passage_boxes = [
        (label, options)
        for label, options, *_ in fake_st.selectboxes
        if label == "Aktuális igerész helyszínei"
    ]
    assert passage_boxes
    assert passage_boxes[0][1][0] == "corinth"
    assert fake_st.text_inputs[0][0] == "Másik bibliai hely keresése"
    assert [label for label, *_ in fake_st.radios] == ["Térkép nézet"]
    assert any("Korinthus" in body for body in fake_st.markdowns)
    assert fake_st.maps[-1][1]["use_container_width"] is True
    assert fake_st.maps[-1][1]["height"] == 520
    assert fake_st.columns_calls == []


def test_passage_place_selector_only_lists_linked_places() -> None:
    acts_18_places = [place.place_id for place in passage_linked_places("ApCsel 18,1-18")]
    acts_16_places = [place.place_id for place in passage_linked_places("ApCsel 16,11-40")]

    assert acts_18_places[0] == "corinth"
    assert len(acts_18_places) > 1
    assert acts_16_places[0] == "philippi"
    assert len(acts_16_places) > 1
    assert passage_linked_places("Jn 3,16") == ()

    fake_st = _FakeStreamlit()
    render_biblical_map_prototype(passage_reference="ApCsel 16,11-40", st_module=fake_st)
    passage_boxes = [
        (label, options)
        for label, options, *_ in fake_st.selectboxes
        if label == "Aktuális igerész helyszínei"
    ]
    assert passage_boxes
    assert passage_boxes[0][1][0] == "philippi"
    assert len(passage_boxes[0][1]) == len(acts_16_places)
    assert set(place.place_id for place in BIBLICAL_MAP_PLACES) - {"philippi"}
    assert all(
        len(options) < len(BIBLICAL_MAP_PLACES)
        for _, options, *_ in fake_st.selectboxes
        if _ != "Keresési találatok"
    )


def test_acts_13_and_14_chapter_queries_resolve_place_links() -> None:
    acts_13 = [place.place_id for place in passage_linked_places("ApCsel 13")]
    acts_14 = [place.place_id for place in passage_linked_places("ApCsel 14")]
    acts_13_internal = [place.place_id for place in passage_linked_places("ACT 13")]

    assert acts_13 == acts_13_internal
    assert {"seleucia", "salamis", "paphos", "perga", "antioch_2"}.issubset(acts_13)
    assert {"iconium", "lystra", "derbe", "perga", "attalia"}.issubset(acts_14)
    assert route_matches_for_passage("ApCsel 13")
    assert route_matches_for_passage("ApCsel 14")


def test_places_view_with_route_match_uses_full_width_map_layout() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 13", st_module=fake_st)

    assert fake_st.maps
    assert fake_st.maps[-1][1]["use_container_width"] is True
    assert fake_st.maps[-1][1]["height"] == 520
    assert fake_st.columns_calls == []
    assert any("Kapcsolódó útvonal:" in info for info in fake_st.infos)
    assert any(label == "Aktuális igerész helyszínei" for label, *_ in fake_st.selectboxes)
    assert any(label == "Másik bibliai hely keresése" for label, _ in fake_st.text_inputs)


def test_specific_verse_does_not_inherit_whole_passage_place_list() -> None:
    whole_passage = [place.place_id for place in passage_linked_places("ApCsel 18,1-18")]
    single_verse = [place.place_id for place in passage_linked_places("ApCsel 18,5")]

    assert whole_passage[0] == "corinth"
    assert single_verse[0] == "corinth"
    assert len(single_verse) < len(whole_passage)
    assert set(single_verse) != set(whole_passage)


def test_same_named_distinct_places_are_not_merged() -> None:
    bethel_hits = search_biblical_places("bethel", limit=10)
    bethel_ids = {place.place_id for place in bethel_hits}
    raw_catalog = json.loads(BIBLICAL_PLACES_CATALOG_PATH.read_text(encoding="utf-8"))
    bethel_1 = next(item for item in raw_catalog if item["place_id"] == "bethel_1")

    assert {"bethel_1", "bethel_2"}.issubset(bethel_ids)
    assert "bethel_3" in (bethel_1.get("legacy_place_ids") or [])


def test_render_corinth_details_sources_and_quality_sections() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)

    assert ("Részletes háttér", False) in fake_st.expanders
    assert ("Exegetikai megjegyzések", False) in fake_st.expanders
    assert ("Források és adatminőség", False) not in fake_st.expanders
    joined_markdown = "\n".join(fake_st.markdowns)
    joined_captions = "\n".join(fake_st.captions)
    rendered_text = joined_markdown + "\n" + joined_captions

    assert "Korinthus a Korinthoszi-földszoros mellett" in joined_markdown
    assert "Korinthus jelentősége Pál szolgálatában" in joined_markdown
    assert "textus-biblical-map-quality" in rendered_text
    assert "textus-biblical-map-sources" in joined_markdown
    assert "textus-biblical-map-quality" in joined_markdown
    assert 'href="https://pleiades.stoa.org/places/570182"' in joined_markdown
    source_blocks = [
        body
        for body in fake_st.markdowns
        if body.strip().startswith('<div class="textus-biblical-map-sources">')
    ]
    assert source_blocks
    assert all(block.count(">Pleiades</a>") == 1 for block in source_blocks)
    assert (
        'href="https://www.ascsa.edu.gr/excavations/ancient-corinth/'
        'about-the-excavations-1/history-timeline"'
    ) in joined_markdown
    assert ">American School of Classical Studies at Athens</a>" in joined_markdown
    assert 'href="https://odysseus.culture.gr/h/3/eh351.jsp?obj_id=2388"' in joined_markdown
    assert ">Hellenic Ministry of Culture</a>" in joined_markdown
    assert " · " in joined_markdown
    assert "**Források**\n" not in joined_markdown
    assert "- [Pleiades]" not in joined_markdown
    assert "Pleiades ID: 570182" not in rendered_text
    assert "Licenc:" not in rendered_text
    assert "Minősítés:" not in rendered_text
    assert "Attribution:" not in rendered_text
    assert "Fordítás" not in rendered_text
    assert "human_authored_source_synthesis" not in rendered_text
    assert "scholarly_curated" not in rendered_text
    assert "source_type" not in rendered_text
    assert "None" not in rendered_text
    assert "null" not in rendered_text


def test_render_ephesus_details_use_existing_short_source_ui() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 19,1-41", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert ("Részletes háttér", False) in fake_st.expanders
    assert ("Exegetikai megjegyzések", False) in fake_st.expanders
    assert ("Források és adatminőség", False) not in fake_st.expanders
    joined_markdown = "\n".join(fake_st.markdowns)
    joined_captions = "\n".join(fake_st.captions)
    rendered_text = joined_markdown + "\n" + joined_captions

    assert "Efezus Kis-Ázsia egyik legjelentősebb" in joined_markdown
    assert "Az evangélium hatása Efezus vallási és gazdasági rendszerére" in joined_markdown
    assert "textus-biblical-map-quality" in rendered_text
    assert "textus-biblical-map-sources" in joined_markdown
    assert 'href="https://pleiades.stoa.org/places/599612"' in joined_markdown
    assert ">Pleiades</a>" in joined_markdown
    assert 'href="https://whc.unesco.org/en/list/1018/"' in joined_markdown
    assert ">UNESCO World Heritage Centre</a>" in joined_markdown
    assert (
        "href=\"https://muze.gov.tr/Language/Index/EN?url=%2Fmuze-detay"
        "%3Fsectionid%3Defs01%26distid%3Defs\""
    ) in joined_markdown
    assert ">Republic of Türkiye Ministry of Culture and Tourism</a>" in joined_markdown
    assert " · " in joined_markdown
    assert "- [Pleiades]" not in joined_markdown
    assert "Pleiades ID: 599612" not in rendered_text
    assert "Licenc:" not in rendered_text
    assert "Minősítés:" not in rendered_text
    assert "Attribution:" not in rendered_text
    assert "human_authored_source_synthesis" not in rendered_text
    assert "scholarly_curated" not in rendered_text


def test_real_source_place_cards_do_not_show_demo_source_note() -> None:
    for reference, place_name in [
        ("ApCsel 17,16-34", "Athén"),
        ("ApCsel 16,11-40", "Filippi"),
        ("ApCsel 28,11-31", "Róma"),
        ("ApCsel 18,1-18", "Korinthus"),
        ("ApCsel 19,1-41", "Efezus"),
    ]:
        fake_st = _FakeStreamlit()

        render_biblical_map_prototype(passage_reference=reference, st_module=fake_st)

        joined_markdown = "\n".join(fake_st.markdowns)
        assert place_name in joined_markdown
        assert "Forrás:</strong> demonstrációs adat" not in joined_markdown


def test_manual_demo_source_note_can_render_for_manual_only_records() -> None:
    fake_st = _FakeStreamlit()
    manual_place = replace(
        BIBLICAL_MAP_PLACES[0],
        source_ids=("manual_demo_v1",),
        coordinate_source_id="manual_demo_v1",
    )

    _render_place_card(fake_st, manual_place, "")

    assert any("Forrás:</strong> demonstrációs adat" in body for body in fake_st.markdowns)


def test_place_selectbox_options_prioritize_auto_place_and_sort_the_rest() -> None:
    base = BIBLICAL_MAP_PLACES[0]
    dummy_places = tuple(
        replace(
            base,
            place_id=f"dummy_{index:03d}",
            name_hu=name,
            is_primary_demo_place=False,
        )
        for index, name in enumerate(["Zéta", "Alfa", "Mű", "Béta"] * 75)
    )
    auto_place = replace(
        base,
        place_id="auto_place",
        name_hu="Kiemelt hely",
        is_primary_demo_place=False,
    )
    places = dummy_places + (auto_place,) + dummy_places[:10]

    options = place_selectbox_options(places, "auto_place")
    labels = place_option_labels(places)

    assert options[0] == "auto_place"
    assert options.count("auto_place") == 1
    assert len(options) == len(set(options))
    assert options[1:] == sorted(options[1:], key=lambda place_id: (labels[place_id].casefold(), place_id))
    assert labels["auto_place"] == "Kiemelt hely"
    assert "auto_place" not in labels["auto_place"]


def test_short_source_list_omits_heading_when_empty_and_handles_missing_url() -> None:
    fake_st = _FakeStreamlit()

    _render_short_sources(fake_st, [])
    _render_short_sources(
        fake_st,
        [
            BiblicalMapSource(
                source_id="source-without-url",
                provider="Teszt forrás",
                title="Teszt",
                original_language=None,
                source_url=None,
                license="test",
                attribution=None,
                retrieved_at=None,
                source_type="test",
                reliability_tier="test",
                notes_hu=None,
            )
        ],
    )

    assert fake_st.markdowns == [
        '<div class="textus-biblical-map-sources">'
        "<strong>Források:</strong> Teszt forrás"
        "</div>"
    ]
    assert compact_sources_markdown([]) == ""
    assert (
        compact_sources_markdown(
            [
                BiblicalMapSource(
                    source_id="linked",
                    provider="Pleiades",
                    title="Place",
                    original_language=None,
                    source_url="https://example.com/a",
                    license="test",
                    attribution=None,
                    retrieved_at=None,
                    source_type="test",
                    reliability_tier="test",
                    notes_hu=None,
                ),
                BiblicalMapSource(
                    source_id="linked-dup",
                    provider="Pleiades",
                    title="Place duplicate provider",
                    original_language=None,
                    source_url="https://example.com/b",
                    license="test",
                    attribution=None,
                    retrieved_at=None,
                    source_type="test",
                    reliability_tier="test",
                    notes_hu=None,
                ),
                BiblicalMapSource(
                    source_id="plain",
                    provider="Plain Provider",
                    title="Plain",
                    original_language=None,
                    source_url=None,
                    license="test",
                    attribution=None,
                    retrieved_at=None,
                    source_type="test",
                    reliability_tier="test",
                    notes_hu=None,
                ),
            ]
        )
        == "**Források:** [Pleiades](https://example.com/a) · Plain Provider"
    )
    html = compact_sources_html(
        [
            BiblicalMapSource(
                source_id="pleiades_corinth_570182",
                provider="Pleiades",
                title="A",
                original_language=None,
                source_url="https://pleiades.stoa.org/places/570182",
                license="test",
                attribution=None,
                retrieved_at=None,
                source_type="test",
                reliability_tier="test",
                notes_hu=None,
            ),
            BiblicalMapSource(
                source_id="pleiades_place_570182",
                provider="Pleiades",
                title="B",
                original_language=None,
                source_url="https://pleiades.stoa.org/places/570182",
                license="test",
                attribution=None,
                retrieved_at=None,
                source_type="test",
                reliability_tier="test",
                notes_hu=None,
            ),
        ]
    )
    assert html.count(">Pleiades</a>") == 1
    assert len(dedupe_sources(
        [
            BiblicalMapSource(
                source_id="a",
                provider="Pleiades",
                title="A",
                original_language=None,
                source_url=None,
                license="t",
                attribution=None,
                retrieved_at=None,
                source_type="t",
                reliability_tier="t",
                notes_hu=None,
            ),
            BiblicalMapSource(
                source_id="a",
                provider="Pleiades",
                title="A",
                original_language=None,
                source_url=None,
                license="t",
                attribution=None,
                retrieved_at=None,
                source_type="t",
                reliability_tier="t",
                notes_hu=None,
            ),
        ]
    )) == 1
    assert "None" not in "\n".join(fake_st.markdowns)
    assert "null" not in "\n".join(fake_st.markdowns)


def test_catalog_search_is_accent_insensitive_and_capped() -> None:
    assert normalize_place_search_text("Korinthús") == "korinthus"
    hits = search_biblical_places("korinthus")
    assert hits and hits[0].place_id == "corinth"
    hits_en = search_biblical_places("athens")
    assert hits_en and hits_en[0].place_id == "athens"
    hits_catalog = search_biblical_places("abana")
    assert hits_catalog and hits_catalog[0].place_id == "abana"
    many = search_biblical_places("a", limit=20)
    assert len(many) <= 20


def test_first_hungarian_review_batch_names_are_searchable() -> None:
    expected_hits = {
        "Babilon": "babylon_1",
        "Jordán": "jordan",
        "Moáb": "moab_1",
        "Asszíria": "assyria",
        "Samária": "samaria_1",
        "Damaszkusz": "damascus",
        "Ninive": "nineveh",
    }

    for query, expected_place_id in expected_hits.items():
        hits = search_biblical_places(query, limit=10)
        assert any(place.place_id == expected_place_id for place in hits)
        assert all(place.place_id not in display_place_name(place) for place in hits)

    assert search_biblical_places("Babylon")
    assert search_biblical_places("Ninive")


def test_first_hungarian_review_batch_card_summaries_are_compact() -> None:
    draft_path = ROOT / "data" / "biblical_places" / "hungarian_review_batch_001_hu_draft.json"
    draft_ids = {
        item["place_id"]
        for item in json.loads(draft_path.read_text(encoding="utf-8"))
    }

    for place_id in draft_ids:
        place = get_biblical_place(place_id)
        if place is None:
            raw_catalog = json.loads(BIBLICAL_PLACES_CATALOG_PATH.read_text(encoding="utf-8"))
            canonical_id = next(
                (
                    item["place_id"]
                    for item in raw_catalog
                    if place_id in (item.get("legacy_place_ids") or [])
                ),
                None,
            )
            place = get_biblical_place(canonical_id) if canonical_id else None
        assert place is not None
        summary = fallback_place_description(place)
        assert summary
        assert summary.count(".") + summary.count("?") + summary.count("!") <= 2


def test_second_hungarian_review_batch_names_are_searchable() -> None:
    expected_hits = {
        "Geba": "geba_1",
        "Tircá": "tirzah",
        "Ciklág": "ziklag",
        "Betánia": "bethany_1",
        "Ciprus": "cyprus",
        "Hárán": "haran",
        "Megiddó": "megiddo",
        "Askelón": "ashkelon",
        "Kréta": "crete",
        "Galácia": "galatia",
    }

    for query, expected_place_id in expected_hits.items():
        hits = search_biblical_places(query, limit=10)
        assert any(place.place_id == expected_place_id for place in hits)
        assert all(place.place_id not in display_place_name(place) for place in hits)

    assert search_biblical_places("Tirzah")
    assert search_biblical_places("Ziklag")


def test_second_hungarian_review_batch_card_summaries_are_compact() -> None:
    draft_path = ROOT / "data" / "biblical_places" / "hungarian_review_batch_002_hu_draft.json"
    draft_ids = {
        item["place_id"]
        for item in json.loads(draft_path.read_text(encoding="utf-8"))
    }

    for place_id in draft_ids:
        place = get_biblical_place(place_id)
        if place is None:
            raw_catalog = json.loads(BIBLICAL_PLACES_CATALOG_PATH.read_text(encoding="utf-8"))
            canonical_id = next(
                (
                    item["place_id"]
                    for item in raw_catalog
                    if place_id in (item.get("legacy_place_ids") or [])
                ),
                None,
            )
            place = get_biblical_place(canonical_id) if canonical_id else None
        assert place is not None
        summary = fallback_place_description(place)
        assert summary
        assert summary.count(".") + summary.count("?") + summary.count("!") <= 2


def test_missing_hungarian_name_and_summary_use_safe_ui_fallbacks() -> None:
    place = BiblicalPlace(
        place_id="synthetic_missing_hu",
        name_hu=None,
        name_en="Synthetic Place",
        ancient_names=(),
        original_names=(),
        transliterations=(),
        modern_name="Modern Site",
        modern_country="Testland",
        place_type="settlement",
        identification_status="possible",
        confidence_note_hu=None,
        latitude=1.0,
        longitude=2.0,
        region_hu=None,
        ancient_region=None,
        geometry_type="point",
        coordinate_source_id="test_source",
        card_summary_hu=None,
        card_summary_en=None,
        is_primary_demo_place=False,
        geography_hu=None,
        history_hu=None,
        political_context_hu=None,
        economic_context_hu=None,
        social_context_hu=None,
        religious_context_hu=None,
        archaeology_hu=None,
        biblical_significance_hu=None,
        modern_context_hu=None,
        exegetical_notes=(),
        source_ids=(),
        translation_status="not_translated",
        translation_method=None,
        translation_model=None,
        translated_at=None,
        review_status="needs_review",
        reviewed_by=None,
        reviewed_at=None,
        openbible_id=None,
        pleiades_id=None,
        step_id=None,
        wikidata_id=None,
    )

    assert display_place_name(place) == "Synthetic Place"
    assert "synthetic_missing_hu" not in display_place_name(place)
    assert fallback_place_description(place) == (
        "Bizonytalan azonosítású bibliai helyszín az ókori Testland területén; "
        "mai azonosítása: Modern Site."
    )


def test_compact_ancient_names_remove_duplicates_without_losing_full_data() -> None:
    ephesus = get_biblical_place("ephesus")
    assert ephesus is not None
    place = replace(
        ephesus,
        ancient_names=("Ephesus", "Ephesus", "Ephesus 2", "Efezus"),
        original_names=("Ephesus", "Ἔφεσος"),
        transliterations=("Efezus", "Ephesos"),
    )

    compact_names = compact_ancient_name_options(place, limit=6)

    assert compact_names == ("Ephesus", "Efezus", "Ἔφεσος", "Ephesos")
    assert "Ephesus 2" in place.ancient_names


def test_catalog_search_pick_updates_selected_place_without_query_alone() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)
    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "corinth"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO

    fake_st.selectbox_choice = "ephesus"
    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_MANUAL
    assert any("Efezus" in body for body in fake_st.markdowns)


def test_render_preserves_manual_catalog_choice_for_same_reference() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"
    fake_st.selectbox_choice = "ephesus"

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)
    fake_st.selectbox_choice = None
    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_MANUAL
    assert "A jelenlegi helyszínt kézzel választottad ki." in fake_st.captions


def test_new_supported_reference_can_override_manual_selectbox_choice() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"
    fake_st.selectbox_choice = "ephesus"

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)
    fake_st.selectbox_choice = None
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = ""
    if CATALOG_SEARCH_PICK_KEY in fake_st.session_state:
        del fake_st.session_state[CATALOG_SEARCH_PICK_KEY]
    render_biblical_map_prototype(passage_reference="ApCsel 16,11-40", st_module=fake_st)

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "philippi"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_AUTO
    assert fake_st.infos[-1] == (
        "A helyszín a megadott igerész alapján automatikusan lett kiválasztva: Filippi."
    )


def test_unknown_passage_preserves_existing_choice_without_arbitrary_pick() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"
    fake_st.selectbox_choice = "ephesus"

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)
    fake_st.selectbox_choice = None
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = ""
    if CATALOG_SEARCH_PICK_KEY in fake_st.session_state:
        del fake_st.session_state[CATALOG_SEARCH_PICK_KEY]
    selectbox_count = len(fake_st.selectboxes)
    render_biblical_map_prototype(passage_reference="Jn 3,16", st_module=fake_st)
    new_selectboxes = fake_st.selectboxes[selectbox_count:]

    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert fake_st.session_state[MAP_SELECTION_SOURCE_KEY] == MAP_SELECTION_SOURCE_UNMATCHED
    assert any(
        "Ehhez az igerészhez a prototípus még nem tartalmaz automatikus helykapcsolatot."
        in caption
        for caption in fake_st.captions
    )
    assert not any(label == "Aktuális igerész helyszínei" for label, *_ in new_selectboxes)


def test_selectbox_uses_place_ids_internally_and_hungarian_labels_in_ui() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 17,16-34", st_module=fake_st)

    passage_boxes = [
        (label, options, index, kwargs)
        for label, options, index, kwargs in fake_st.selectboxes
        if label == "Aktuális igerész helyszínei"
    ]
    assert passage_boxes
    label, options, index, kwargs = passage_boxes[-1]
    assert options[0] == "athens"
    assert kwargs["format_func"]("athens") == "Athén"
    assert "athens" not in kwargs["format_func"]("athens")
    assert fake_st.text_inputs[0][0] == "Másik bibliai hely keresése"
    assert [label for label, *_ in fake_st.radios] == ["Térkép nézet"]


def test_map_failure_keeps_selector_and_place_card_visible() -> None:
    fake_st = _FakeStreamlit(fail_map=True)
    fake_st.session_state[CATALOG_SEARCH_QUERY_KEY] = "efe"
    fake_st.selectbox_choice = "ephesus"

    render_biblical_map_prototype(passage_reference="ApCsel 19", st_module=fake_st)

    assert fake_st.errors == []
    assert "Aktuális igerész: ApCsel 19" in fake_st.captions
    assert fake_st.warnings == [
        "A térképi nézet nem érhető el, de a helyválasztó és az adatlap használható."
    ]
    assert fake_st.text_inputs
    assert [label for label, *_ in fake_st.radios] == ["Térkép nézet"]
    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "ephesus"
    assert any("Efezus" in body for body in fake_st.markdowns)


def test_route_view_helpers_build_first_missionary_journey_rows() -> None:
    route = load_biblical_routes()[0]
    stop_rows = route_stop_rows(route)
    segment_rows = route_segment_rows(route)

    assert len(stop_rows) == 15
    assert len(segment_rows) == 14
    assert sum(1 for row in segment_rows if row["segment_type"] == "land") == 11
    assert sum(1 for row in segment_rows if row["segment_type"] == "sea") == 3
    assert [row["place_id"] for row in stop_rows].count("perga") == 2
    assert [row["order"] for row in stop_rows] == list(range(1, 16))
    assert all("lat" in row and "lon" in row for row in stop_rows)
    assert all("display_lat" in row and "display_lon" in row for row in stop_rows)

    perga_rows = [row for row in stop_rows if row["place_id"] == "perga"]
    assert perga_rows[0]["lat"] == perga_rows[1]["lat"]
    assert perga_rows[0]["lon"] == perga_rows[1]["lon"]
    assert {
        (row["display_lat"], row["display_lon"])
        for row in perga_rows
    } != {(perga_rows[0]["lat"], perga_rows[0]["lon"])}
    assert route_stop_rows(route) == stop_rows

    assert {row["line_style"] for row in segment_rows} == {"solid", "dashed"}
    assert {row["segment_type_label"] for row in segment_rows} >= {"szárazföldi", "tengeri"}
    assert all(row["geometry_status_label"] == "sematikus" for row in segment_rows)
    assert all(len(row["path"]) == 13 for row in segment_rows)
    assert all(row["path"][0] == row["straight_path"][0] for row in segment_rows)
    assert all(row["path"][-1] == row["straight_path"][-1] for row in segment_rows)
    assert route_segment_rows(route) == segment_rows


def test_selected_mapped_route_stop_gets_focus_viewport_and_marker_highlight() -> None:
    route = load_biblical_routes()[0]
    stop_rows = route_stop_rows(route, selected_stop_id="perga_outbound")
    selected = selected_route_stop_row(stop_rows, "perga_outbound")
    other_perga = selected_route_stop_row(stop_rows, "perga_return")
    viewport = selected_route_stop_focus_viewport(stop_rows, "perga_outbound")
    full_viewport = route_viewport(stop_rows)

    assert selected is not None
    assert other_perga is not None
    assert selected["is_selected"] is True
    assert other_perga["is_selected"] is False
    assert selected["size"] > other_perga["size"]
    assert selected["line_width"] > other_perga["line_width"]
    assert (
        selected["display_lat"],
        selected["display_lon"],
    ) != (
        other_perga["display_lat"],
        other_perga["display_lon"],
    )
    assert viewport["latitude"] == selected["display_lat"]
    assert viewport["longitude"] == selected["display_lon"]
    assert 5.0 <= viewport["zoom"] <= 6.5
    assert viewport["zoom"] >= full_viewport["zoom"]


def test_selected_approximate_route_stop_gets_focus_viewport() -> None:
    route = {route.route_id: route for route in load_biblical_routes()}[
        "joshua_jordan_crossing_central_campaign"
    ]
    stop_rows = route_stop_rows(route, selected_stop_id="jordan_crossing")
    selected = selected_route_stop_row(stop_rows, "jordan_crossing")
    viewport = selected_route_stop_focus_viewport(stop_rows, "jordan_crossing")

    assert selected is not None
    assert selected["place_id"] == "jordan"
    assert selected["is_selected"] is True
    assert viewport["latitude"] == selected["display_lat"]
    assert viewport["longitude"] == selected["display_lon"]
    assert 5.0 <= viewport["zoom"] <= 6.5


def test_textual_only_route_stop_keeps_previous_viewport_without_marker_focus() -> None:
    route = {route.route_id: route for route in load_biblical_routes()}["exodus_egypt_to_sinai"]
    stop_rows = route_stop_rows(route, selected_stop_id="sea_crossing_textual")
    previous = {"latitude": 31.5, "longitude": 35.2, "zoom": 5.5}
    viewport = selected_route_stop_focus_viewport(
        stop_rows,
        "sea_crossing_textual",
        previous_viewport=previous,
    )
    state = {ROUTE_VIEWPORT_STATE_KEY: previous}
    state_viewport = route_viewport_for_selection(
        state,
        stop_rows,
        route_id=route.route_id,
        selected_stop_id="sea_crossing_textual",
    )

    assert selected_route_stop_row(stop_rows, "sea_crossing_textual") is None
    assert viewport == previous
    assert state_viewport == previous
    assert LAST_FOCUSED_ROUTE_STOP_ID_KEY not in state


def test_route_focus_state_updates_only_when_selected_stop_changes() -> None:
    route = load_biblical_routes()[0]
    rows = route_stop_rows(route, selected_stop_id="perga_outbound")
    state: dict[str, object] = {}

    first = route_viewport_for_selection(
        state,
        rows,
        route_id=route.route_id,
        selected_stop_id="perga_outbound",
    )
    state[ROUTE_VIEWPORT_STATE_KEY] = {"latitude": 99.0, "longitude": 88.0, "zoom": 4.0}
    second = route_viewport_for_selection(
        state,
        rows,
        route_id=route.route_id,
        selected_stop_id="perga_outbound",
    )
    rows = route_stop_rows(route, selected_stop_id="lystra_outbound")
    third = route_viewport_for_selection(
        state,
        rows,
        route_id=route.route_id,
        selected_stop_id="lystra_outbound",
    )

    assert first["latitude"] != 99.0
    assert second == {"latitude": 99.0, "longitude": 88.0, "zoom": 4.0}
    assert third != second
    assert state[LAST_FOCUSED_ROUTE_STOP_ID_KEY] == f"{route.route_id}:lystra_outbound"


def test_route_change_and_passage_navigation_focus_first_relevant_stop() -> None:
    routes = load_biblical_routes()
    state = {
        PENDING_MAP_VIEW_KEY: MAP_VIEW_ROUTES,
        PENDING_ROUTE_ID_KEY: "joshua_southern_campaign",
        PENDING_ROUTE_STOP_IDS_KEY: ["gezer_intervention", "lachish_southern"],
        ROUTE_VIEWPORT_STATE_KEY: {"latitude": 0.0, "longitude": 0.0, "zoom": 1.0},
    }

    selected_route_id, _phase, selected_stop_id, route, visible_stops, _segments = (
        prepare_route_widget_state(state, routes)
    )
    rows = route_stop_rows(
        replace(route, stops=visible_stops),
        selected_stop_id=selected_stop_id,
        highlighted_stop_ids=tuple(state[HIGHLIGHTED_ROUTE_STOP_IDS_KEY]),
    )
    viewport = route_viewport_for_selection(
        state,
        rows,
        route_id=selected_route_id,
        selected_stop_id=selected_stop_id,
    )

    assert selected_route_id == "joshua_southern_campaign"
    assert selected_stop_id == "gezer_intervention"
    assert state[HIGHLIGHTED_ROUTE_STOP_IDS_KEY] == ["gezer_intervention", "lachish_southern"]
    assert state[LAST_FOCUSED_ROUTE_STOP_ID_KEY] == "joshua_southern_campaign:gezer_intervention"
    assert viewport["latitude"] == selected_route_stop_row(rows, "gezer_intervention")["display_lat"]


def test_phase_change_normalizes_stop_and_focuses_first_visible_stop() -> None:
    routes = load_biblical_routes()
    route_id = "joshua_northern_campaign"
    state = {
        SELECTED_ROUTE_ID_KEY: route_id,
        SELECTED_ROUTE_STOP_ID_KEY: "sidon_pursuit",
        route_phase_state_key(route_id): "Hácór elfoglalása",
    }

    selected_route_id, selected_phase, selected_stop_id, route, visible_stops, _segments = (
        prepare_route_widget_state(state, routes)
    )
    rows = route_stop_rows(replace(route, stops=visible_stops), selected_stop_id=selected_stop_id)
    viewport = route_viewport_for_selection(
        state,
        rows,
        route_id=selected_route_id,
        selected_stop_id=selected_stop_id,
    )

    assert selected_phase == "Hácór elfoglalása"
    assert selected_stop_id == "hazor_capture"
    assert state[SELECTED_ROUTE_STOP_ID_KEY] == "hazor_capture"
    assert viewport["latitude"] == selected_route_stop_row(rows, "hazor_capture")["display_lat"]


def test_map_style_switch_preserves_selected_stop_focus_state() -> None:
    route = load_biblical_routes()[0]
    state = {
        MAP_STYLE_KEY: MAP_STYLE_CLEAN,
        SELECTED_ROUTE_ID_KEY: route.route_id,
        SELECTED_ROUTE_STOP_ID_KEY: "perga_outbound",
    }
    rows = route_stop_rows(route, selected_stop_id="perga_outbound")

    before = route_viewport_for_selection(
        state,
        rows,
        route_id=route.route_id,
        selected_stop_id="perga_outbound",
    )
    state[MAP_STYLE_KEY] = MAP_STYLE_CLEAN
    after = route_viewport_for_selection(
        state,
        rows,
        route_id=route.route_id,
        selected_stop_id="perga_outbound",
    )

    assert state[SELECTED_ROUTE_STOP_ID_KEY] == "perga_outbound"
    assert state[MAP_STYLE_KEY] == MAP_STYLE_CLEAN
    assert after == before


def test_route_segment_paths_are_deterministic_curves_without_mutating_stop_coordinates() -> None:
    route = load_biblical_routes()[0]
    stop_rows_before = route_stop_rows(route)
    segment_rows = route_segment_rows(route)

    assert route_segment_rows(route) == segment_rows
    assert route_stop_rows(route) == stop_rows_before
    assert any(row["path"][1:-1] for row in segment_rows)
    assert any(row["path"] != row["straight_path"] for row in segment_rows)
    assert all(row["straight_path"][0] == row["path"][0] for row in segment_rows)
    assert all(row["straight_path"][-1] == row["path"][-1] for row in segment_rows)


def test_route_line_rows_render_exactly_one_geometry_per_corridor() -> None:
    route = load_biblical_routes()[0]
    segment_rows = route_segment_rows(route)
    line_rows = route_line_rows(segment_rows)

    assert len(segment_rows) == 14
    # Outbound/return of the same place pair share one drawn corridor.
    assert len(line_rows) < len(segment_rows)
    assert len(line_rows) == len({row["corridor_key"] for row in line_rows})
    assert all("render_path" in row for row in line_rows)
    assert all("path" not in row and "straight_path" not in row for row in line_rows)
    assert all(row["geometry_source"] == "curved" for row in line_rows)
    assert all(len(row["render_path"]) > 2 for row in line_rows)
    assert all(row["direction"] == "outbound" or row["from_place_id"] != row["to_place_id"] for row in line_rows)
    # Shared Anatolian corridors keep the outbound (gently curved) line only.
    assert sum(1 for row in line_rows if row["direction"] == "return") == 2
    assert all(
        row["render_path"][0] != row["render_path"][-1] for row in line_rows
    )


def test_route_line_rows_use_single_straight_fallback_when_curved_path_is_unavailable() -> None:
    route = load_biblical_routes()[0]
    segment_rows = route_segment_rows(route)
    broken = [dict(row) for row in segment_rows]
    broken[0]["path"] = None
    line_rows = route_line_rows(broken)

    assert line_rows[0]["geometry_source"] == "fallback_straight"
    assert line_rows[0]["render_path"] == segment_rows[0]["straight_path"]
    assert "path" not in line_rows[0] and "straight_path" not in line_rows[0]
    assert all(row["geometry_source"] == "curved" for row in line_rows[1:])
    assert len(line_rows) == len({row["corridor_key"] for row in line_rows})


def test_textual_only_stop_is_listed_but_not_rendered_on_map() -> None:
    payload = json.loads((ROOT / "data" / "biblical_routes" / "biblical_routes.json").read_text(encoding="utf-8"))
    route = payload[0]
    route["stops"].insert(
        1,
        {
            "order": 2,
            "stop_id": "unknown_textual_stop",
            "place_id": None,
            "place_name_override_hu": "Ismeretlen állomás",
            "passage_refs": ["2Móz 15,22"],
            "event_summary_hu": "A hely szövegileg ismert, de nem térképezhető.",
            "certainty": "possible",
            "stop_type": "uncertain_place",
            "source_notes_hu": "Szövegileg igazolt állomás.",
            "mapping_status": "textual_only",
            "display_on_map": False,
            "mapping_notes_hu": "Nincs biztonságosan feloldható aktív helyrekord.",
            "sequence_status": "explicit",
        },
    )
    for index, stop in enumerate(route["stops"], start=1):
        stop["order"] = index
    route["segments"] = [
        {
            "from_stop_id": "antioch_syria_departure",
            "to_stop_id": "unknown_textual_stop",
            "certainty": "possible",
            "segment_type": "land",
            "geometry_status": "schematic",
            "source_notes_hu": "Nem jeleníthető meg térképi vonalként.",
            "waypoints": [],
            "geometry": None,
        },
        {
            "from_stop_id": "unknown_textual_stop",
            "to_stop_id": "seleucia_departure",
            "certainty": "possible",
            "segment_type": "land",
            "geometry_status": "schematic",
            "source_notes_hu": "Nem jeleníthető meg térképi vonalként.",
            "waypoints": [],
            "geometry": None,
        },
    ]
    path = Path(tempfile.mkdtemp()) / "routes.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    loaded = load_biblical_routes(routes_path=path)[0]

    stop_rows = route_stop_rows(loaded)
    segment_rows = route_segment_rows(loaded)

    assert any(stop.stop_id == "unknown_textual_stop" for stop in loaded.stops)
    assert all(row["stop_id"] != "unknown_textual_stop" for row in stop_rows)
    assert segment_rows == []


def test_all_pauline_routes_produce_one_route_line_per_corridor() -> None:
    for route in load_biblical_routes():
        segment_rows = route_segment_rows(route)
        line_rows = route_line_rows(segment_rows)

        assert len(line_rows) <= len(route.segments)
        assert len(line_rows) == len({row["corridor_key"] for row in line_rows})
        assert {row["segment_type"] for row in line_rows} <= {"land", "sea"}
        assert {row["line_style"] for row in line_rows} <= {"solid", "dashed"}
        assert all(row["render_path"][0] != row["render_path"][-1] for row in line_rows)
        assert all(row["geometry_source"] == "curved" for row in line_rows)


def test_route_segment_curve_profiles_separate_land_sea_and_return_paths() -> None:
    land_profile, land_strength = route_curve_profile("land")
    sea_profile, sea_strength = route_curve_profile("sea")

    assert land_profile == "subtle_land_curve"
    assert sea_profile == "soft_sea_curve"
    assert sea_strength > land_strength
    assert land_strength >= 0.08

    outbound = schematic_segment_path(
        (1.0, 1.0),
        (4.0, 2.0),
        segment_type="land",
        direction="outbound",
        from_stop_id="out_a",
        to_stop_id="out_b",
    )
    sea = schematic_segment_path(
        (1.0, 1.0),
        (4.0, 2.0),
        segment_type="sea",
        direction="outbound",
        from_stop_id="out_a",
        to_stop_id="out_b",
    )

    assert outbound[0] == [1.0, 1.0]
    assert outbound[-1] == [4.0, 2.0]
    assert len(outbound) > 2
    # Midpoint leaves the chord so the drawn path is gently curved.
    chord_mid = [(1.0 + 4.0) / 2, (1.0 + 2.0) / 2]
    assert outbound[6] != chord_mid
    assert sea[6] != outbound[6]

def test_route_viewport_is_calculated_from_all_stops() -> None:
    route = load_biblical_routes()[0]
    viewport = route_viewport(route_stop_rows(route))

    assert 33 <= viewport["latitude"] <= 39
    assert 30 <= viewport["longitude"] <= 37
    assert viewport["zoom"] >= 3


def test_route_ui_enum_labels_and_unknown_fallback_are_hungarian() -> None:
    assert _display_status("certain", CERTAINTY_LABELS) == "biztos"
    assert _display_status("schematic", GEOMETRY_STATUS_LABELS) == "sematikus"
    assert _display_status("return_stop", STOP_TYPE_LABELS) == "visszaúti állomás"
    assert _display_status("sea", SEGMENT_TYPE_LABELS) == "tengeri"
    assert _display_status("future_value", STOP_TYPE_LABELS) == "future value"


def test_passage_to_route_index_matches_acts_13_and_14() -> None:
    acts_13 = route_matches_for_passage("ApCsel 13")
    acts_14 = route_matches_for_passage("ApCsel 14")
    unrelated = route_matches_for_passage("Jn 3,16")

    assert "paul_first_missionary_journey" in acts_13
    assert "paul_first_missionary_journey" in acts_14
    assert any(stop.stop_id == "seleucia_departure" for stop in acts_13["paul_first_missionary_journey"])
    assert any(stop.stop_id == "lystra_return" for stop in acts_14["paul_first_missionary_journey"])
    assert unrelated == {}


def test_passage_to_route_index_matches_new_pauline_routes() -> None:
    acts_16 = route_matches_for_passage("ApCsel 16")
    acts_17 = route_matches_for_passage("ApCsel 17")
    acts_18_early = route_matches_for_passage("ApCsel 18,1-18")
    acts_18_late = route_matches_for_passage("ApCsel 18,23")
    acts_19 = route_matches_for_passage("ApCsel 19")
    acts_20 = route_matches_for_passage("ApCsel 20")
    acts_21_early = route_matches_for_passage("ApCsel 21,1-16")
    acts_21_late = route_matches_for_passage("ApCsel 21,18-40")
    acts_27 = route_matches_for_passage("ApCsel 27")
    acts_28 = route_matches_for_passage("ApCsel 28")

    assert "paul_second_missionary_journey" in acts_16
    assert "paul_second_missionary_journey" in acts_17
    assert "paul_second_missionary_journey" in acts_18_early
    assert "paul_third_missionary_journey" not in acts_18_early
    assert "paul_third_missionary_journey" in acts_18_late
    assert "paul_third_missionary_journey" in acts_19
    assert "paul_third_missionary_journey" in acts_20
    assert "paul_third_missionary_journey" in acts_21_early
    assert "paul_journey_to_rome" not in acts_21_early
    assert "paul_journey_to_rome" in acts_21_late
    assert "paul_journey_to_rome" in acts_27
    assert "paul_journey_to_rome" in acts_28


def test_passage_to_route_index_matches_patriarchal_routes() -> None:
    gen_12 = route_matches_for_passage("1M\u00f3z 12")
    gen_13 = route_matches_for_passage("1M\u00f3z 13")
    gen_22 = route_matches_for_passage("1M\u00f3z 22")
    gen_28 = route_matches_for_passage("1M\u00f3z 28")
    gen_31_33 = route_matches_for_passage("1M\u00f3z 31-33")
    gen_35 = route_matches_for_passage("1M\u00f3z 35")
    gen_37 = route_matches_for_passage("1M\u00f3z 37")
    gen_42_46 = route_matches_for_passage("1M\u00f3z 42-46")

    assert "abraham_journey" in gen_12
    assert "abraham_journey" in gen_13
    assert "abraham_journey" in gen_22
    assert "jacob_journeys" in gen_28
    assert "jacob_journeys" in gen_31_33
    assert "jacob_journeys" in gen_35
    assert "joseph_geographical_arc" in gen_37
    assert "joseph_geographical_arc" in gen_42_46


def test_passage_to_route_index_matches_exodus_and_wilderness_routes() -> None:
    for reference in ["2Móz 12", "2Móz 13", "2Móz 14", "2Móz 15", "2Móz 16", "2Móz 17", "2Móz 19", "4Móz 33,1-15"]:
        assert "exodus_egypt_to_sinai" in route_matches_for_passage(reference)
    for reference in ["4Móz 10", "4Móz 11", "4Móz 12", "4Móz 13-14", "4Móz 20", "4Móz 21", "4Móz 22,1", "4Móz 33,16-49"]:
        assert "wilderness_sinai_to_moab" in route_matches_for_passage(reference)
    numbers_33 = route_matches_for_passage("4Móz 33")
    assert "exodus_egypt_to_sinai" in numbers_33
    assert "wilderness_sinai_to_moab" in numbers_33


def test_passage_to_route_index_matches_joshua_conquest_routes() -> None:
    for reference in ["Jozs 2", "Jozs 3", "Jozs 4", "Jozs 5-6", "Jozs 7-8"]:
        assert "joshua_jordan_crossing_central_campaign" in route_matches_for_passage(reference)
    for reference in ["Jozs 9", "Jozs 10"]:
        assert "joshua_southern_campaign" in route_matches_for_passage(reference)
    assert "joshua_northern_campaign" in route_matches_for_passage("Jozs 11")

    assert route_matches_for_passage("Jozs 12") == {}
    whole_section = route_matches_for_passage("Jozs 1-11")
    assert "joshua_jordan_crossing_central_campaign" in whole_section
    assert "joshua_southern_campaign" in whole_section
    assert "joshua_northern_campaign" in whole_section


def test_joshua_partial_passage_overlap_highlights_expected_stops() -> None:
    joshua_2 = route_matches_for_passage("Jozs 2")
    assert [stop.stop_id for stop in joshua_2["joshua_jordan_crossing_central_campaign"]] == [
        "shittim_spies_departure",
        "jericho_spies",
    ]

    joshua_10_33 = route_matches_for_passage("Jozs 10,33")
    assert [stop.stop_id for stop in joshua_10_33["joshua_southern_campaign"]] == [
        "gezer_intervention"
    ]


def test_wilderness_route_phase_options_and_filtering() -> None:
    route = {route.route_id: route for route in load_biblical_routes()}["wilderness_sinai_to_moab"]
    assert route_phase_options(route) == [
        "Teljes útvonal",
        "Elindulás a Sínaitól",
        "Út Kádés felé",
        "A pusztai vándorlás évei",
        "Kádéstől Móábig",
    ]
    filtered = filtered_route_stops(route, "Kádéstől Móábig")
    assert filtered[0].stop_id == "kadesh_wilderness"
    assert filtered_route_segments(route, filtered)


def test_joshua_route_phase_options_and_branch_filtering() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}
    central = routes["joshua_jordan_crossing_central_campaign"]
    northern = routes["joshua_northern_campaign"]

    assert route_phase_options(central) == [
        "Teljes \u00fatvonal",
        "Felder\u00edt\u00e9s \u00e9s el\u0151k\u00e9sz\u00fclet",
        "\u00c1tkel\u00e9s a Jord\u00e1non",
        "Jerik\u00f3 elfoglal\u00e1sa",
        "Aj hadj\u00e1rata",
        "Sz\u00f6vets\u00e9gmeg\u00faj\u00edt\u00e1s Sikem t\u00e9rs\u00e9g\u00e9ben",
    ]
    pursuit_stops = filtered_route_stops(northern, "Az ellens\u00e9g \u00fcld\u00f6z\u00e9se")
    pursuit_segments = filtered_route_segments(northern, pursuit_stops)
    assert [stop.stop_id for stop in pursuit_stops] == [
        "sidon_pursuit",
        "misrephoth_maim_pursuit",
        "valley_mizpeh_pursuit",
    ]
    assert pursuit_segments == ()


def test_joshua_route_family_navigation_buttons_render() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_ID_KEY] = "joshua_jordan_crossing_central_campaign"

    render_biblical_map_prototype(st_module=fake_st)

    assert any("J\u00f3zsu\u00e9 honfoglal\u00e1si hadj\u00e1ratai" in caption for caption in fake_st.captions)
    assert any("1/3" in caption for caption in fake_st.captions)
    assert any(label == "K\u00f6vetkez\u0151 szakasz" for label, _kwargs in fake_st.buttons)

    fake_st = _FakeStreamlit()
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_ID_KEY] = "joshua_northern_campaign"

    render_biblical_map_prototype(st_module=fake_st)

    assert any("3/3" in caption for caption in fake_st.captions)
    assert any(label == "El\u0151z\u0151 szakasz" for label, _kwargs in fake_st.buttons)


def test_route_family_navigation_buttons_render_for_exodus_routes() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_ID_KEY] = "exodus_egypt_to_sinai"

    render_biblical_map_prototype(st_module=fake_st)

    assert any("Útvonalcsalád: A kivonulás és a pusztai vándorlás · 1/2" in caption for caption in fake_st.captions)
    assert any(label == "Következő szakasz" for label, _kwargs in fake_st.buttons)

    fake_st = _FakeStreamlit()
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_ID_KEY] = "wilderness_sinai_to_moab"

    render_biblical_map_prototype(st_module=fake_st)

    assert any("Útvonalcsalád: A kivonulás és a pusztai vándorlás · 2/2" in caption for caption in fake_st.captions)
    assert any(label == "Előző szakasz" for label, _kwargs in fake_st.buttons)
    assert any(box[0] == "Útvonalfázis" for box in fake_st.selectboxes)


def test_pauline_route_family_navigation_buttons_render() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_ID_KEY] = "paul_early_damascus_to_antioch"

    render_biblical_map_prototype(st_module=fake_st)

    assert any("Útvonalcsalád: Pál missziói útjai · 1/5" in caption for caption in fake_st.captions)
    assert any(label == "Következő szakasz" for label, _kwargs in fake_st.buttons)

    fake_st = _FakeStreamlit()
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_ID_KEY] = "paul_journey_to_rome"

    render_biblical_map_prototype(st_module=fake_st)

    assert any("Útvonalcsalád: Pál missziói útjai · 5/5" in caption for caption in fake_st.captions)
    assert any(label == "Előző szakasz" for label, _kwargs in fake_st.buttons)


def test_partial_passage_overlap_links_to_route_stop() -> None:
    matches = route_matches_for_passage("ApCsel 13,4")

    assert [stop.stop_id for stop in matches["paul_first_missionary_journey"]] == [
        "seleucia_departure"
    ]


def test_switch_to_route_view_state_sets_route_and_highlight_once() -> None:
    state = {}

    switch_to_route_view_for_passage(
        state,
        "paul_first_missionary_journey",
        ["seleucia_departure", "seleucia_departure", "salamis_arrival"],
    )

    assert state[PENDING_MAP_VIEW_KEY] == MAP_VIEW_ROUTES
    assert state[PENDING_ROUTE_ID_KEY] == "paul_first_missionary_journey"
    assert state[PENDING_ROUTE_STOP_IDS_KEY] == [
        "seleucia_departure",
        "salamis_arrival",
    ]


def test_pending_route_state_is_applied_before_widgets_and_then_cleared() -> None:
    routes = load_biblical_routes()
    state = {
        PENDING_MAP_VIEW_KEY: MAP_VIEW_ROUTES,
        PENDING_ROUTE_ID_KEY: "paul_first_missionary_journey",
        PENDING_ROUTE_STOP_IDS_KEY: ["seleucia_departure", "seleucia_departure"],
    }

    selected_route_id, _phase, selected_stop_id, _route, _stops, _segments = (
        prepare_route_widget_state(state, routes)
    )

    assert state[ACTIVE_MAP_VIEW_KEY] == MAP_VIEW_ROUTES
    assert selected_route_id == "paul_first_missionary_journey"
    assert selected_stop_id == "seleucia_departure"
    assert state[SELECTED_ROUTE_ID_KEY] == "paul_first_missionary_journey"
    assert state[SELECTED_ROUTE_STOP_ID_KEY] == "seleucia_departure"
    assert state[HIGHLIGHTED_ROUTE_STOP_IDS_KEY] == ["seleucia_departure"]
    assert PENDING_MAP_VIEW_KEY not in state
    assert PENDING_ROUTE_ID_KEY not in state
    assert PENDING_ROUTE_STOP_IDS_KEY not in state


def test_route_family_next_navigation_queues_route_without_widget_key_mutation() -> None:
    fake_st = _FakeStreamlit(
        clicked_buttons={"Következő szakasz"},
        enforce_widget_lock=True,
    )
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_ID_KEY] = "exodus_egypt_to_sinai"

    render_biblical_map_prototype(st_module=fake_st)

    assert fake_st.session_state[SELECTED_ROUTE_ID_KEY] == "exodus_egypt_to_sinai"
    assert fake_st.session_state[PENDING_ROUTE_ID_KEY] == "wilderness_sinai_to_moab"
    assert fake_st.session_state[PENDING_MAP_VIEW_KEY] == MAP_VIEW_ROUTES


def test_route_family_previous_navigation_queues_route_without_widget_key_mutation() -> None:
    fake_st = _FakeStreamlit(
        clicked_buttons={"Előző szakasz"},
        enforce_widget_lock=True,
    )
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_ID_KEY] = "wilderness_sinai_to_moab"

    render_biblical_map_prototype(st_module=fake_st)

    assert fake_st.session_state[SELECTED_ROUTE_ID_KEY] == "wilderness_sinai_to_moab"
    assert fake_st.session_state[PENDING_ROUTE_ID_KEY] == "exodus_egypt_to_sinai"
    assert fake_st.session_state[PENDING_MAP_VIEW_KEY] == MAP_VIEW_ROUTES


def test_pending_next_route_sets_first_valid_stop_on_following_render() -> None:
    fake_st = _FakeStreamlit(enforce_widget_lock=True)
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[PENDING_ROUTE_ID_KEY] = "wilderness_sinai_to_moab"
    fake_st.session_state[PENDING_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_STOP_ID_KEY] = "antioch_syria_departure"

    render_biblical_map_prototype(st_module=fake_st)

    assert fake_st.session_state[SELECTED_ROUTE_ID_KEY] == "wilderness_sinai_to_moab"
    assert fake_st.session_state[SELECTED_ROUTE_STOP_ID_KEY] == "sinai_wilderness_departure"
    assert PENDING_ROUTE_ID_KEY not in fake_st.session_state


def test_pending_previous_route_sets_first_valid_stop_on_following_render() -> None:
    fake_st = _FakeStreamlit(enforce_widget_lock=True)
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[PENDING_ROUTE_ID_KEY] = "exodus_egypt_to_sinai"
    fake_st.session_state[PENDING_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_STOP_ID_KEY] = "sinai_wilderness_departure"

    render_biblical_map_prototype(st_module=fake_st)

    assert fake_st.session_state[SELECTED_ROUTE_ID_KEY] == "exodus_egypt_to_sinai"
    assert fake_st.session_state[SELECTED_ROUTE_STOP_ID_KEY] == "rameses_exodus"
    assert PENDING_ROUTE_ID_KEY not in fake_st.session_state


def test_route_phase_state_is_kept_when_still_valid_and_normalized_when_invalid() -> None:
    routes = load_biblical_routes()
    state = {
        SELECTED_ROUTE_ID_KEY: "wilderness_sinai_to_moab",
        route_phase_state_key("wilderness_sinai_to_moab"): "Kádéstől Móábig",
    }

    selected_route_id, selected_phase, selected_stop_id, _route, _stops, _segments = (
        prepare_route_widget_state(state, routes)
    )

    assert selected_route_id == "wilderness_sinai_to_moab"
    assert selected_phase == "Kádéstől Móábig"
    assert selected_stop_id == "kadesh_wilderness"

    state[route_phase_state_key("wilderness_sinai_to_moab")] = "nem létező fázis"
    _selected_route_id, selected_phase, _selected_stop_id, _route, _stops, _segments = (
        prepare_route_widget_state(state, routes)
    )

    assert selected_phase == "Teljes útvonal"
    assert state[route_phase_state_key("wilderness_sinai_to_moab")] == "Teljes útvonal"


def test_route_navigation_preserves_map_style_state() -> None:
    fake_st = _FakeStreamlit(enforce_widget_lock=True)
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[PENDING_ROUTE_ID_KEY] = "wilderness_sinai_to_moab"
    fake_st.session_state[PENDING_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[MAP_STYLE_KEY] = MAP_STYLE_CLEAN

    render_biblical_map_prototype(st_module=fake_st)

    assert fake_st.session_state[SELECTED_ROUTE_ID_KEY] == "wilderness_sinai_to_moab"
    assert fake_st.session_state[MAP_STYLE_KEY] == MAP_STYLE_CLEAN


def test_render_default_places_view_does_not_force_route_map() -> None:
    fake_st = _FakeStreamlit()

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)

    assert fake_st.radios[-1][0] == "Térkép nézet"
    assert fake_st.session_state[ACTIVE_MAP_VIEW_KEY] == MAP_VIEW_PLACES
    assert fake_st.maps
    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "corinth"


def test_map_uses_single_clean_basemap_without_style_picker() -> None:
    assert MAP_STYLE_OPTIONS == (MAP_STYLE_CLEAN,)
    assert list(MAP_STYLE_CONFIGS) == [MAP_STYLE_CLEAN]
    assert MAP_STYLE_CONFIGS[MAP_STYLE_CLEAN].label_hu == "Letisztult"

    fake_st = _FakeStreamlit()
    fake_st.session_state[MAP_STYLE_KEY] = MAP_STYLE_HISTORICAL_MOOD
    assert resolve_map_style_id(fake_st.session_state) == MAP_STYLE_CLEAN
    assert fake_st.session_state[MAP_STYLE_KEY] == MAP_STYLE_CLEAN

    selected = render_map_style_selector(fake_st)
    assert selected == MAP_STYLE_CLEAN
    assert fake_st.session_state[MAP_STYLE_KEY] == MAP_STYLE_CLEAN

    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)
    assert not any(box[0] == "Térképstílus" for box in fake_st.selectboxes)
    assert fake_st.session_state[MAP_STYLE_KEY] == MAP_STYLE_CLEAN


def test_invalid_map_style_falls_back_to_clean() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[MAP_STYLE_KEY] = "missing_style"

    assert resolve_map_style_id(fake_st.session_state) == MAP_STYLE_CLEAN
    assert fake_st.session_state[MAP_STYLE_KEY] == MAP_STYLE_CLEAN


def test_map_style_state_is_shared_by_places_and_route_views() -> None:
    fake_st = _FakeStreamlit()
    render_biblical_map_prototype(passage_reference="ApCsel 18,1-18", st_module=fake_st)

    assert fake_st.session_state[MAP_STYLE_KEY] == MAP_STYLE_CLEAN
    assert not any(box[0] == "Térképstílus" for box in fake_st.selectboxes)

    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    render_biblical_map_prototype(st_module=fake_st)

    assert fake_st.session_state[MAP_STYLE_KEY] == MAP_STYLE_CLEAN
    assert not any(box[0] == "Térképstílus" for box in fake_st.selectboxes)


def test_map_style_switch_does_not_change_route_or_place_render_data() -> None:
    route = load_biblical_routes()[0]
    clean_stops = route_stop_rows(route)
    clean_segments = route_segment_rows(route)
    clean_lines = route_line_rows(clean_segments)

    fake_st = _FakeStreamlit()
    fake_st.session_state[MAP_STYLE_KEY] = MAP_STYLE_TERRAIN
    render_biblical_map_prototype(passage_reference="ApCsel 13", st_module=fake_st)

    assert fake_st.session_state[MAP_STYLE_KEY] == MAP_STYLE_CLEAN
    assert route_stop_rows(route) == clean_stops
    assert route_segment_rows(route) == clean_segments
    assert route_line_rows(route_segment_rows(route)) == clean_lines
    assert not any(box[0] == "Térképstílus" for box in fake_st.selectboxes)


def test_render_route_view_loads_first_missionary_journey() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES

    render_biblical_map_prototype(st_module=fake_st)

    assert fake_st.session_state[SELECTED_ROUTE_ID_KEY] == "paul_early_damascus_to_antioch"
    assert fake_st.session_state[SELECTED_ROUTE_STOP_ID_KEY] == "damascus_conversion"
    assert any("Pál korai útja Damaszkusztól Antiókhiáig" in body for body in fake_st.markdowns)
    assert fake_st.warnings.count(ROUTE_VIEW_WARNING_HU) == 1
    assert fake_st.pydeck_charts or fake_st.maps
    assert any(label == "Állomás kiválasztása" for label, *_ in fake_st.selectboxes)
    if fake_st.maps:
        assert fake_st.maps[-1][1]["use_container_width"] is True
        assert fake_st.maps[-1][1]["height"] == 520
    if fake_st.pydeck_charts:
        assert fake_st.pydeck_charts[-1][1]["use_container_width"] is True
        assert fake_st.pydeck_charts[-1][1]["height"] == 520
    assert fake_st.columns_calls == []


def test_route_selector_lists_all_biblical_routes() -> None:
    assert route_options() == [
        "paul_early_damascus_to_antioch",
        "paul_first_missionary_journey",
        "paul_second_missionary_journey",
        "paul_third_missionary_journey",
        "paul_journey_to_rome",
        "abraham_journey",
        "jacob_journeys",
        "joseph_geographical_arc",
        "ruth_moab_to_bethlehem",
        "exodus_egypt_to_sinai",
        "wilderness_sinai_to_moab",
        "joshua_jordan_crossing_central_campaign",
        "joshua_southern_campaign",
        "joshua_northern_campaign",
        "ezra_return_babylon_to_jerusalem",
        "nehemiah_susa_to_jerusalem",
        "philip_samaria_to_caesarea",
        "peter_jerusalem_to_caesarea",
        "jesus_infancy_egypt",
        "jesus_galilee_named_sites",
        "jesus_samaria_sychar",
        "jesus_passion_jerusalem",
        "seven_churches_asia",
    ]

    fake_st = _FakeStreamlit()
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES

    render_biblical_map_prototype(st_module=fake_st)

    route_box = next(
        (box for box in fake_st.selectboxes if box[0] == "Útvonal kiválasztása"),
        None,
    )
    assert route_box is not None
    assert route_box[1] == route_options()
    labels = route_box[3]["format_func"]
    assert labels("ruth_moab_to_bethlehem").startswith("● Erős — ")
    assert labels("jesus_galilee_named_sites").startswith("○ Gyenge — ")
    assert labels("paul_second_missionary_journey").startswith("◐ Közepes — ")
    assert any(ROUTE_EVIDENCE_LEGEND_HU in caption for caption in fake_st.captions)
    assert any(
        ROUTE_EVIDENCE_TIER_NOTES_HU["moderate"] in caption for caption in fake_st.captions
    )


def test_route_option_label_includes_evidence_marker() -> None:
    routes = {route.route_id: route for route in load_biblical_routes()}
    assert route_evidence_tier(routes["seven_churches_asia"]) == "strong"
    assert "Erős —" in route_option_label(routes["seven_churches_asia"])
    assert "Gyenge —" in route_option_label(routes["wilderness_sinai_to_moab"])


def test_route_switch_resets_station_selection_to_new_route() -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
    fake_st.session_state[SELECTED_ROUTE_ID_KEY] = "paul_journey_to_rome"
    fake_st.session_state[SELECTED_ROUTE_STOP_ID_KEY] = "lystra_return"

    render_biblical_map_prototype(st_module=fake_st)

    assert fake_st.session_state[SELECTED_ROUTE_ID_KEY] == "paul_journey_to_rome"
    assert fake_st.session_state[SELECTED_ROUTE_STOP_ID_KEY] == "jerusalem_rome_departure"
    assert fake_st.pydeck_charts or fake_st.maps


def test_route_view_handles_missing_route_data_gracefully() -> None:
    import biblical_map_ui

    original_loader = biblical_map_ui.load_biblical_routes
    try:
        biblical_map_ui.load_biblical_routes = lambda: (_ for _ in ()).throw(
            biblical_map_ui.BiblicalRouteDataError("broken")
        )  # type: ignore[assignment]
        fake_st = _FakeStreamlit()
        fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES
        render_biblical_map_prototype(st_module=fake_st)
    finally:
        biblical_map_ui.load_biblical_routes = original_loader  # type: ignore[assignment]

    assert fake_st.errors == []
    assert fake_st.warnings


def test_route_map_failure_keeps_station_list_visible() -> None:
    fake_st = _FakeStreamlit(fail_map=True)
    fake_st.session_state[ACTIVE_MAP_VIEW_KEY] = MAP_VIEW_ROUTES

    render_biblical_map_prototype(st_module=fake_st)

    assert fake_st.errors == []
    assert "Az útvonal térképi megjelenítése most nem érhető el." in fake_st.warnings
    assert any("Állomások" in body for body in fake_st.markdowns)


def test_enriched_place_card_renders_extended_profile() -> None:
    fake_st = _FakeStreamlit()
    place = get_biblical_place("corinth")
    assert place is not None

    _render_place_card(fake_st, place, "ApCsel 18,1-18")

    assert any("Bővített helyszínadatlap" in body for body in fake_st.markdowns)
    assert ("Bibliai jelentőség", True) in fake_st.expanders
    assert any(label == "Források" for label, _ in fake_st.expanders)
    assert any(
        "Helyszínprofil állapota: Kiemelt helyszínprofil (történeti/régészeti forrásokkal)"
        in body
        for body in fake_st.captions
    )


def test_non_enriched_place_card_keeps_compact_profile_only() -> None:
    fake_st = _FakeStreamlit()
    place = get_biblical_place("abana")
    assert place is not None

    _render_place_card(fake_st, place, "")

    assert not any("Bővített helyszínadatlap" in body for body in fake_st.markdowns)
    assert not any(label == "Kapcsolódó bibliai útvonalak" for label, _ in fake_st.expanders)
    assert any(
        "Helyszínprofil állapota: Alapadatlap (katalógus)" in body for body in fake_st.captions
    )


def test_enrichment_route_button_uses_pending_navigation_state() -> None:
    route_label = "Pál második missziói útja"
    fake_st = _FakeStreamlit(clicked_buttons={route_label}, enforce_widget_lock=True)
    place = get_biblical_place("corinth")
    assert place is not None

    _render_place_card(fake_st, place, "ApCsel 18,1-18")

    assert fake_st.session_state[PENDING_ROUTE_ID_KEY] == "paul_second_missionary_journey"
    assert fake_st.session_state[PENDING_MAP_VIEW_KEY] == MAP_VIEW_ROUTES


def test_related_profile_record_button_uses_pending_place_navigation() -> None:
    fake_st = _FakeStreamlit(clicked_buttons={"Jerikó"})
    place = get_biblical_place("jericho_1")
    assert place is not None

    _render_place_card(fake_st, place, "Jozs 6,1-27")

    assert any(label == "Kapcsolódó korszakok vagy helyrekordok" for label, _ in fake_st.expanders)
    assert fake_st.session_state[PENDING_PLACE_ID_KEY] == "jericho_2"


def test_pending_place_navigation_applies_before_widgets() -> None:
    fake_st = _FakeStreamlit(enforce_widget_lock=True)
    queue_place_navigation(fake_st.session_state, "jericho_2")

    applied = apply_pending_place_navigation_state(fake_st.session_state)

    assert applied == "jericho_2"
    assert fake_st.session_state[SELECTED_PLACE_ID_KEY] == "jericho_2"
    assert PENDING_PLACE_ID_KEY not in fake_st.session_state


def test_search_prefers_enriched_primary_record_for_duplicate_name() -> None:
    results = search_biblical_places("Jerikó")

    assert results
    assert results[0].place_id == "jericho_1"


def test_research_readiness_and_scope_note_are_honest() -> None:
    assert "béta előtti prototípus" in MAP_SCOPE_NOTE_HU
    assert research_readiness_class("egypt") == "partial_profile_ready"
    assert research_readiness_class("corinth") is None
