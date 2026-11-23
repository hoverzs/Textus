"""Textus 2.0 Igehirdetési műhely — UI (M4: kézi + MI-segéd).

Nem importál az app.py-ból. A Gemini-hívást a hívó által átadott
`generate_fn` végzi (tipikusan `generate_text`).
"""

from __future__ import annotations

import html
import json
from typing import Any, Callable, MutableMapping

import streamlit as st
from ui_components import (
    action_row,
    mi_helper_zone,
    render_context_summary,
    render_empty_state,
    render_info_panel,
    render_page_intro,
    render_work_section,
    work_surface,
)

from bible_text_ui import (
    normalize_passage_text,
    render_bible_text_preview,
    render_formatted_bible_text,
)
from bible_text_ui import _ensure_bible_text_styles
from ruf_bible_service import SOURCE_NAME, fetch_ruf_passage
from writing_desk_outline_handoff import (
    OUTLINE_HANDOFF_CONFIRM_KEY,
    apply_developed_outline_handoff,
    writing_desk_draft_needs_overwrite_confirmation,
)
from sermon_workshop_data import (
    _ARC_POINT_KEYS,
    _DEVELOPED_MOVEMENT_LIST_FIELDS,
    accept_arc_candidate,
    accept_workshop_proposal,
    discard_developed_outline_candidate,
    update_developed_outline_movement_field,
    add_approved_sermon_decision,
    add_engagement_element,
    discard_arc_candidate,
    discard_field_refinement_suggestion,
    validate_field_refinement_acceptance,
    update_engagement_element,
    remove_engagement_element,
    save_engagement_suggestions,
    empty_application,
    empty_illustration,
    empty_sermon_movement,
    empty_textual_image,
    ensure_sermon_workshop_state,
    update_arc_point,
    normalize_applications,
    normalize_illustrations,
    normalize_lection_connection_type,
    normalize_lection_length_preference,
    normalize_lection_testament_preference,
    normalize_sermon_movements,
    normalize_textual_images,
    remove_approved_sermon_decision,
    save_gospel_arc_assessment,
    save_gospel_arc_suggestions,
    save_human_condition_assessment,
    save_human_condition_suggestion,
    save_listener_tension_assessment,
    save_listener_tension_suggestions,
    save_closing_assessment,
    save_closing_suggestions,
    save_entry_point_suggestions,
    save_lection_assessment,
    save_lection_connection_analysis,
    save_lection_suggestions,
    save_prayer_after_suggestions,
    save_prayer_assessment,
    save_prayer_before_suggestions,
    save_sermon_enrichment_assessment,
    save_sermon_enrichment_suggestions,
    save_sermon_main_idea_assessment,
    save_sermon_main_idea_suggestions,
    save_sermon_outline,
    save_sermon_outline_diagnostics,
    section_has_accepted_content,
    set_sermon_outline_diagnostics_status,
    save_sermon_path_assessment,
    save_sermon_path_suggestions,
    update_sermon_workshop_section,
    normalize_prayer_rewrite_mode,
    normalize_prayer_tone_preference,
    normalize_sermon_outline,
    _diagnostics_has_result,
)
from sermon_workshop_m4_ai import (
    HumanConditionAssessmentResult,
    HumanConditionSuggestionResult,
    SermonMainIdeaAssessmentResult,
    SermonMainIdeaSuggestionResult,
    assess_human_condition,
    assess_sermon_main_idea,
    suggest_human_condition,
    suggest_sermon_main_idea,
)
from sermon_workshop_m5_ai import (
    ListenerTensionAssessmentResult,
    ListenerTensionSuggestionResult,
    assess_listener_tension,
    suggest_listener_tension,
)
from sermon_workshop_entry_point_ai import (
    ENTRY_POINT_TYPE_KEYS,
    EntryPointSuggestionResult,
    entry_point_type_label,
    normalize_entry_point_type,
    suggest_entry_point,
)
from sermon_workshop_engagement_ai import (
    ENGAGEMENT_TYPE_KEYS,
    EngagementSuggestionResult,
    engagement_type_label,
    normalize_engagement_type,
    suggest_engagement_elements,
)
from sermon_workshop_m5_gospel_ai import (
    CHRIST_CONNECTION_TYPES,
    CHRIST_CONNECTION_TYPE_LABELS_HU,
    GospelArcAssessmentResult,
    GospelArcSuggestionResult,
    assess_gospel_arc,
    christ_connection_type_label,
    normalize_christ_connection_type,
    suggest_gospel_arc,
)
from sermon_workshop_m6_ai import (
    DEFAULT_MOVEMENT_COUNT,
    MAX_MOVEMENTS,
    MIN_MOVEMENTS,
    MOVEMENT_ROLES,
    MOVEMENT_ROLE_LABELS_HU,
    SERMON_PATH_TYPES,
    SERMON_PATH_TYPE_LABELS_HU,
    SermonPathAssessmentResult,
    SermonPathSuggestionResult,
    assess_sermon_path,
    movement_role_label,
    normalize_movement_role,
    normalize_sermon_path_type,
    sermon_path_type_label,
    suggest_sermon_path,
)
from sermon_workshop_m7_ai import (
    APPLICATION_SCOPES,
    APPLICATION_SCOPE_LABELS_HU,
    IMAGE_FUNCTIONS,
    IMAGE_FUNCTION_LABELS_HU,
    ILLUSTRATION_FUNCTIONS,
    ILLUSTRATION_FUNCTION_LABELS_HU,
    ILLUSTRATION_SOURCES,
    ILLUSTRATION_SOURCE_LABELS_HU,
    MAX_APPLICATIONS,
    MAX_ILLUSTRATIONS,
    MAX_TEXTUAL_IMAGES,
    PLACEMENT_KINDS,
    PLACEMENT_KIND_LABELS_HU,
    EnrichmentAssessmentResult,
    EnrichmentSuggestionResult,
    application_scope_label,
    assess_enrichment,
    illustration_function_label,
    image_function_label,
    normalize_application_scope,
    normalize_illustration_function,
    normalize_illustration_source,
    normalize_image_function,
    normalize_placement_kind,
    suggest_enrichment,
)
from sermon_workshop_m7_simple_ai import (
    NO_SEARCH_MESSAGE as _EN_NO_SEARCH,
    assess_enrichment_readiness,
    collect_textus_retained_actualizations,
    collect_textus_retained_illustrations,
    illustration_card_to_legacy,
    legacy_illustration_to_card,
    normalize_actualization_card,
    normalize_actualization_cards,
    normalize_illustration_card,
    normalize_illustration_cards,
    suggest_actualizations,
    suggest_illustrations,
)
from sermon_workshop_m7_closing_ai import (
    CLOSING_TONES,
    CLOSING_TONE_LABELS_HU,
    CLOSING_TYPES,
    CLOSING_TYPE_LABELS_HU,
    ClosingAssessmentResult,
    ClosingSuggestionResult,
    assess_closing,
    closing_tone_label,
    closing_type_label,
    normalize_closing_tone,
    normalize_closing_type,
    suggest_closing,
)
from sermon_workshop_m8_ai import (
    DIAGNOSTIC_AREA_KEYS,
    HomileticalDiagnosticsResult,
    diagnostic_area_label,
    diagnostic_status_label,
    normalize_diagnostic_status,
)
from sermon_workshop_m9_lection_ai import (
    LECTION_CONNECTION_TYPES,
    LECTION_LENGTH_PREFERENCES,
    LECTION_TESTAMENT_PREFERENCES,
    LECTION_CONNECTION_TYPE_LABELS_HU,
    LECTION_LENGTH_PREFERENCE_LABELS_HU,
    LECTION_TESTAMENT_PREFERENCE_LABELS_HU,
    LectionAssessmentResult,
    LectionCandidate,
    LectionSuggestionResult,
    assess_lection,
    lection_connection_type_label,
    references_equivalent,
    suggest_lections,
    validate_lection_reference,
)
from sermon_workshop_lection_link_ai import (
    WEAK_CONNECTION_MESSAGE,
    analyze_lection_textus_link,
    before_after_label,
    build_lection_link_fingerprint,
    lection_connection_analysis_is_stale,
    lection_link_type_label,
    outline_signature_for_link,
    placement_label,
)
from sermon_workshop_m9_prayer_ai import (
    PRAYER_REWRITE_MODES,
    PRAYER_REWRITE_MODE_LABELS_HU,
    PRAYER_TONE_PREFERENCES,
    PRAYER_TONE_PREFERENCE_LABELS_HU,
    PRAYER_TONE_UI_OPTIONS,
    adapt_prayer_suggestion_for_ui,
    assess_prayer_preparation,
    build_prayer_source_caption,
    prayer_tone_preference_label,
    suggest_prayer_after,
    suggest_prayer_before,
)
from sermon_workshop_outline_ai import (
    EMPTY_PROJECT_MESSAGE,
    assemble_sermon_outline,
    collect_available_sermon_material,
    editable_outline_snapshot,
    outline_canonical_text,
    outline_has_content,
    repair_outline_integrity,
    render_compact_sermon_outline,
    render_pulpit_outline_view,
    sync_outline_content,
)
from sermon_outline_diagnostics_ai import (
    MAX_REFINEMENTS,
    MAX_STRENGTHS,
    OutlineDiagnosticsResult,
    adapt_m8_to_outline_diagnostics,
    run_outline_diagnostics,
)
from sermon_workshop_arc_ai import build_arc_generation_context, generate_seven_point_arc
from sermon_workshop_blueprint_ai import generate_sermon_blueprint
from sermon_workshop_developed_outline_ai import (
    build_developed_outline_context,
    generate_developed_outline,
    is_blueprint_fresh,
)
from sermon_workshop_refinement_ai import (
    build_refinement_context,
    generate_field_refinement,
)
from textus_workshop_data import ensure_text_workshop_state, update_text_main_idea
from textus_workshop_ui import (
    _KEY_IDEA_INPUT as _KEY_FLAT_TEXT_MAIN_IDEA,
    render_text_main_idea_section,
    render_text_summary_section,
)
from diagnostics_dashboard_ui import (
    ensure_dashboard_styles,
    render_summary_card,
    render_work_map,
    segment_state_color,
    segment_state_label,
)
from workshop_nav_ui import (
    SERMON_PHASE_OPTIONS,
    render_workshop_workflow_nav,
    sermon_phase_completed,
    sermon_phase_statuses,
)

GenerateFn = Callable[..., str]

_SW_SECTION_OPTIONS = [
    "Az igehirdetés fő gondolata",
    "Emberi helyzet és kegyelmi válasz",
    "Hallgatói kérdés és feszültség",
    "Krisztus-központú és evangéliumi ív",
    "Az igehirdetés útja és mozgásai",
    "Illusztrációk és aktualizálás",
    "Lezárás és megérkezés",
    "Lekciójavaslat",
    "Imádsági előkészítés",
    "Igehirdetési vázlat",
    "Homiletikai diagnosztika",
]

_SW_SECTION_PLACEHOLDERS: dict[str, dict[str, str]] = {}

# Régi (11 szakaszos) szakaszfelirat → új (5 fázisos) navigáció.
# A mögöttes render_* függvények és session_state mezők nem változnak —
# csak az, hogy melyik fázis alatt jelennek meg. Régi mentett projektek
# `sw_active_section` értéke ezen a táblán keresztül képződik az öt új
# fázisnév egyikére.
_SW_LEGACY_SECTION_TO_PHASE: dict[str, str] = {
    "Fókuszmondat": "Textusmag és fókuszmondat",
    "Az igehirdetés fő gondolata": "Textusmag és fókuszmondat",
    "Emberi helyzet és kegyelmi válasz": "Homiletikai belépési pont",
    "Hallgatói kérdés és feszültség": "Homiletikai belépési pont",
    "Krisztus-központú és evangéliumi ív": "A prédikáció íve",
    "Az igehirdetés útja és mozgásai": "A prédikáció íve",
    "A prédikáció útja": "A prédikáció íve",
    "Prédikációs mozgások": "A prédikáció íve",
    "Lezárás és megérkezés": "A prédikáció íve",
    "Lezárás": "A prédikáció íve",
    # A régi "Illusztrációk és aktualizálás" tartalma (render_enrichment_section)
    # a Korrekciós fázis 2B óta az "Igehirdetési vázlat" fázis Kiegészítők
    # blokkjába költözött — a "Megszólítás és bevonás" nevet az ÚJ,
    # jóváhagyott anyagból dolgozó modul (render_engagement_section) kapta.
    "Illusztrációk és aktualizálás": "Igehirdetési vázlat",
    "Képek, illusztrációk és alkalmazás": "Igehirdetési vázlat",
    "Lekciójavaslat": "Igehirdetési vázlat",
    "Imádsági előkészítés": "Igehirdetési vázlat",
    "Igehirdetési vázlat": "Igehirdetési vázlat",
    "Homiletikai diagnosztika": "Igehirdetési vázlat",
}

_SW_NEXT_HINTS: dict[str, str] = {
    "Textusmag és fókuszmondat": "Következő ajánlott lépés: Homiletikai belépési pont",
    "Homiletikai belépési pont": "Következő ajánlott lépés: A prédikáció íve",
    "A prédikáció íve": "Következő ajánlott lépés: Megszólítás és bevonás",
    "Megszólítás és bevonás": "Következő ajánlott lépés: Igehirdetési vázlat",
}

_STATUS_LABELS = {
    "draft": "Vázlat",
    "approved": "Jóváhagyva",
}


def _toast_and_rerun(message: str, *, icon: str | None = None) -> None:
    """Mentés/jóváhagyás után egységes, ATOMI minta: az állapot (tartalom +
    státusz + approved_context_hash) ekkorra már elmentve; itt csak
    visszajelzünk és azonnal, kontrolláltan újrafuttatjuk a scriptet.

    Enélkül egy adott futtatáson belül a navigáció/progresszsáv (amely a
    szakasz-tartalom ELŐTT renderel a shell-ben) még a jóváhagyás ELŐTTI
    állapotot mutatja, miközben a szakasz saját UI-ja már a frisset — ez a
    „progressz és a ténylegesen jóváhagyott tartalom nem egyezik” és a
    „lebegő panel/duplikált fejléc” tünetek gyökéroka. A `st.toast` a
    rerun után is látszik még egy pillanatra, így a visszajelzés nem vész el.
    """
    st.toast(message, icon=icon)
    st.rerun()

_SOURCE_SERMON_MAIN = "Az igehirdetés fő gondolata"
_SOURCE_ENTRY = "Homiletikai belépési pont"
_SOURCE_HUMAN = "Emberi helyzet és kegyelmi válasz"
_SOURCE_LISTENER = "Hallgatói kérdés és feszültség"
_SOURCE_GOSPEL = "Krisztus-központú és evangéliumi ív"
_SOURCE_PATH = "Az igehirdetés útja és mozgásai"
_SOURCE_ENRICHMENT = "Illusztrációk és aktualizálás"
_SOURCE_CLOSING = "Lezárás és megérkezés"
_SOURCE_LECTION = "Lekciójavaslat"
_SOURCE_PRAYER = "Imádsági előkészítés"
_SOURCE_OUTLINE = "Igehirdetési vázlat"
_CAT_MAIN_IDEA = "Fő gondolat"

_HC_FIELDS = [
    ("condition", "Milyen emberi helyzetet tár fel a textus?", "Emberi helyzet", False),
    (
        "false_response",
        "Milyen téves vagy elégtelen emberi válasz jelenik meg? (opcionális)",
        "Téves emberi válasz",
        True,
    ),
    ("human_need", "Mire van valójában szüksége az embernek?", "Emberi szükség", False),
    ("divine_action", "Mit cselekszik Isten ebben a helyzetben?", "Isten cselekvése", False),
    (
        "grace_response",
        "Milyen választ tesz lehetővé Isten kegyelme?",
        "Kegyelmi válasz",
        False,
    ),
]

_LT_FIELDS = [
    (
        "listener_question",
        "Hallgatói kérdés",
        (
            "Fogalmazd meg azt az őszinte kérdést, amely a textus hallgatása közben "
            "megszülethet a hallgatóban. Ne vizsgakérdés legyen, hanem valós, "
            "egzisztenciális vagy hitbeli kérdés."
        ),
        "Hogyan maradhatok meg a hitben, amikor körülöttem minden annak "
        "ellenkezőjét erősíti?",
        "Hallgatói kérdés",
    ),
    (
        "listener_resistance",
        "Hallgatói ellenállás",
        (
            "Nevezd meg röviden, miért nehéz a hallgatónak elfogadnia vagy "
            "megélnie azt, amit a textus állít. Kerüld az általánosítást és a "
            "hallgató elítélését."
        ),
        "Könnyebb a romboló környezetet hibáztatni, mint felelősséget vállalni "
        "a saját lelki épülésünkért.",
        "Hallgatói ellenállás",
    ),
    (
        "sermon_tension",
        "Központi feszültség",
        (
            "Fogalmazd meg egy világos mondatban a textus igazsága és a hallgató "
            "megélt valósága közötti feszültséget. Ez még ne legyen a feloldás."
        ),
        "Miközben Isten a hitben való megmaradásra hív, a hallgató gyakran úgy "
        "érzi, hogy a körülötte lévő romboló hatások erősebbek a benne lévő "
        "hitnél.",
        "Központi feszültség",
    ),
]

_GA_TEXT_FIELDS = [
    (
        "divine_gracious_action",
        "Isten kegyelmi cselekvése",
        (
            "Fogalmazd meg, mit tesz Isten a textusban, a textus ígéretében vagy a "
            "teljes bibliai összefüggésben. Ne csak azt írd le, mit kell tennie az "
            "embernek."
        ),
        "Isten nem hagyja magára a hitben megmaradásért küzdő gyülekezetet, "
        "hanem szeretetével körülveszi és irgalmában megtartja.",
        "Isten kegyelmi cselekvése",
    ),
    (
        "christ_connection",
        "Krisztus-kapcsolat",
        (
            "Fogalmazd meg, hogyan kapcsolódik a textus Krisztus személyéhez, "
            "munkájához vagy evangéliumához. Ne erőltesd a közvetlen kapcsolatot, "
            "ha a textus csak kánoni, üdvtörténeti vagy tematikus kapcsolatot "
            "alapoz meg."
        ),
        "A megtartó szeretet Krisztusban válik személyessé a gyülekezet számára.",
        "Krisztus-kapcsolat",
    ),
    (
        "promised_resolution",
        "Evangéliumi feloldás",
        (
            "Fogalmazd meg, hogyan válaszol Isten kegyelme a központi "
            "feszültségre. Ez ne legyen olcsó megoldás vagy gyors vallásos válasz, "
            "hanem a textusból és az evangéliumból fakadó valódi feloldás."
        ),
        "A romboló erők közepette Isten megtartó kegyelme ad valós reményt "
        "a megmaradásra.",
        "Evangéliumi feloldás",
    ),
    (
        "grace_enabled_response",
        "Kegyelemből fakadó válasz",
        (
            "Fogalmazd meg, milyen emberi válasz válik lehetővé Isten kegyelmi "
            "cselekvése által. Ne puszta kötelességet vagy moralizáló felszólítást adj."
        ),
        "A gyülekezet hittel ragaszkodhat Krisztushoz, és egymást is építheti.",
        "Kegyelemből fakadó válasz",
    ),
]

_GA_TYPE_HELP = (
    "Válaszd ki, milyen módon kapcsolódik a textus Krisztushoz. "
    "A közvetett vagy kánoni kapcsolat nem alacsonyabb rendű a közvetlennél."
)

_CONFIDENCE_LABELS_HU = {
    "high": "Magas bizonyosság",
    "medium": "Közepes bizonyosság",
    "low": "Alacsony bizonyosság / óvatosság",
}

_SERMON_ASSESSMENT_LABELS = [
    ("text_fidelity", "Textushűség"),
    ("hearability", "Hallhatóság"),
    ("unity", "Egység"),
    ("theological_accuracy", "Teológiai pontosság"),
    ("listener_relevance", "Hallgatói relevancia"),
    ("title_or_slogan_confusion", "Cím / szlogen kockázat"),
    ("application_confusion", "Alkalmazás-összekeverés"),
]

_HC_ASSESSMENT_LABELS = [
    ("text_fidelity", "Textushűség"),
    ("template_risk", "Sablon-kockázat"),
    ("divine_human_separation", "Isteni–emberi elkülönítés"),
    ("moralizing_risk", "Moralizálás kockázata"),
    ("false_response_appropriateness", "Téves válasz indokoltsága"),
    ("grace_grounding", "Kegyelmi megalapozottság"),
]

_HC_SUGGEST_DISPLAY = [
    ("human_condition", "Emberi helyzet"),
    ("false_response", "Téves vagy elégtelen válasz"),
    ("human_need", "Emberi szükség"),
    ("divine_action", "Isten cselekvése"),
    ("grace_response", "Kegyelmi válasz"),
]

# Widget / technikai kulcsok — nem project_data
_KEY_ACTIVE_SECTION = "sw_active_section"
_KEY_SERMON_IDEA = "sw_sermon_main_idea_input"

# RESET 2B (2026-08-18): az egyszerű, lapos "Textus és fókusz" + hétpontos
# szerkesztőfelület widgetkulcsai. A `_KEY_SERMON_IDEA`-t újrahasznosítjuk
# (már seedelve van `_apply_sw_ui_resync_if_needed()`-ben) — csak az
# arc-pontok kapnak új, dedikált kulcsot.
#
# RESET 2D-H (2026-08-20): a `_KEY_FLAT_TEXT_MAIN_IDEA` MOST a `textus_
# workshop_ui._KEY_IDEA_INPUT`-tal AZONOS kulcs (import-aliasként, ld. a
# fájl elejei import), nem saját, önálló string. Korábban a lapos UI
# (`sw_flat_text_main_idea`) és a Textusműhely gyorseszköz-tab
# (`render_text_main_idea_section`, `tw_main_idea_input`) KÉT, EGYMÁSTÓL
# FÜGGETLEN widget-kulcsot használt ugyanahhoz a kanonikus `text_workshop.
# text_main_idea` mezőhöz — a `flush_textus_workshop_from_widgets()` a
# stale (soha nem frissülő) régi kulcsból írt vissza, és felülírta a
# frissen beírt értéket (RESET 2D-G audit, determinisztikus AppTest-tel
# igazolva). A javítás — pontosan a `_KEY_SERMON_IDEA`-nál már bevált
# mintát követve — megszünteti a két divergens forrást: mostantól
# EGYETLEN widget-state forrás (`tw_main_idea_input`) táplálja mindkét
# felületet, ezért a két oldal SOSEM láthat egymástól eltérő értéket.
_KEY_FLAT_ARC: dict[str, str] = {key: f"sw_flat_arc_{key}" for key in _ARC_POINT_KEYS}

# A hét kártya sorrendje és tartalma — 1:1 a `_ARC_POINT_KEYS` sorrendjével
# (zip-elve), hogy a kulcs↔címke↔leírás hármas sosem csúszhat szét.
_ARC_CARD_TITLES: dict[str, str] = {
    "entry": "Belépés",
    "starting_point": "Alaphelyzet",
    "first_shift": "Első fordulópont",
    "deepening": "Mélyítés és fokozás",
    "reinterpretation": "Átértelmezés",
    "second_shift": "Második fordulópont",
    "arrival": "Megérkezés",
}
_ARC_CARD_DESCRIPTIONS: dict[str, str] = {
    "entry": "Természetes belépés a textus kérdésébe és a hallgató tapasztalatába.",
    "starting_point": "A textus és a hallgatói helyzet kiinduló feszültsége.",
    "first_shift": "Az első felismerés, amely elmozdítja a megszokott értelmezést.",
    "deepening": "A kérdés teológiai, emberi és egzisztenciális kibontása.",
    "reinterpretation": "A textus központi felismerése új fénybe helyezi a kiinduló kérdést.",
    "second_shift": "Az evangéliumi felismerés személyes és közösségi következménye.",
    "arrival": "A gondolatmenet természetes lezárása, amely eljuttat valahová.",
}

# RESET 2C: a hétpontos MI-generálás UI-technikai kulcsai és üzenetei.
_KEY_ARC_GEN_RUNNING = "_sw_flat_arc_gen_running"
_ARC_CANDIDATE_REJECT_MESSAGES: dict[str, str] = {
    "no_candidate": "Nincs függőben lévő javaslat.",
    "invalid_candidate": "A javaslat sérült — nem fogadható el.",
    "missing_context_identity": (
        "A javaslathoz vagy az aktuális igehelyhez nem tartozik kontextus-"
        "azonosító — nem fogadható el."
    ),
    "reference_mismatch": (
        "A javaslat egy másik igehelyhez készült — nem fogadható el "
        "ehhez a szöveghez."
    ),
    "context_hash_mismatch": (
        "A bibliai szöveg megváltozott a javaslat elkészülte óta — "
        "változatlanul nem fogadható el."
    ),
}

# RESET 2E-4: a kétlépcsős vázlatmotor (blueprint + részletes vázlat)
# UI-technikai kulcsai és üzenetei. A blueprintnek NINCS candidate-
# lifecycle-ja (RESET 2E-1/2E-2 szerződés, változatlan) — sikeres
# generálás közvetlenül a kanonikus `sermon_workshop.blueprint`-et írja.
# A részletes vázlat viszont KÖTELEZŐEN candidate-only (RESET 2E-1A/
# 2E-3) — ezt itt a UI sem változtatja meg, csak megjeleníti.
_KEY_BLUEPRINT_GEN_RUNNING = "_sw_flat_blueprint_gen_running"
_KEY_OUTLINE_GEN_RUNNING = "_sw_flat_outline_gen_running"

_DEVELOPED_OUTLINE_BLOCK_MESSAGES: dict[str, str] = {
    "missing_blueprint": "Előbb készítsd el az igehirdetési tervrajzot.",
    "blueprint_stale": (
        "A tervrajz elavult: a kanonikus bemenet megváltozott az "
        "elkészülte óta — készíts újat, mielőtt részletes vázlatot kérsz."
    ),
    "missing_reference": "Hiányzik az igehely a részletes vázlat elkészítéséhez.",
    "missing_passage_text": "Hiányzik a bibliai szöveg a részletes vázlat elkészítéséhez.",
    "missing_blueprint_context_identity": (
        "A tervrajz kontextusazonosítója hiányzik — készíts új tervrajzot."
    ),
}

_DEVELOPED_OUTLINE_CANDIDATE_REJECT_MESSAGES: dict[str, str] = {
    "no_candidate": "Nincs függőben lévő vázlatjavaslat.",
    "invalid_candidate": "A vázlatjavaslat sérült — nem fogadható el.",
    "missing_context_identity": (
        "A javaslathoz vagy az aktuális igehelyhez nem tartozik kontextus-"
        "azonosító — nem fogadható el."
    ),
    "reference_mismatch": (
        "A javaslat egy másik igehelyhez készült — nem fogadható el "
        "ehhez a szöveghez."
    ),
    "context_hash_mismatch": (
        "A tervrajz vagy a bibliai szöveg megváltozott a javaslat "
        "elkészülte óta — változatlanul nem fogadható el."
    ),
}

# RESET 2D-B1: célzott, elfogadásos MI-pontosítás UI-technikai üzenetei —
# kilenc egymástól teljesen független példány (két főgondolat + hét
# arc-pont), mindegyik saját, dinamikusan képzett widgetkulcsokkal.
#
# UX-korrekció (2026-08-19): a `_toast_and_rerun()` programozott
# `st.rerun()`-ja a kulcs nélküli `st.expander`-ek nyitott/csukott
# állapotát visszaállítja — sikeres javaslatkérés után emiatt a saját
# panel is visszacsukódott, noha friss, még át nem tekintett javaslat
# készült benne. Ez a fogyó (session-state, NEM projektmentett) jelző
# pontosan EGY rendereléshez jegyzi meg, melyik célmező paneljét kell
# `expanded=True`-val nyitni — a `_render_field_refinement_panel` a
# felolvasáskor azonnal törli is, hogy ne ragadjon be egy régi javaslat
# panelje nyitva a jövőbeli rendereléseken.
_KEY_REFINE_AUTO_OPEN_FIELD = "_sw_refine_auto_open_field"

_FIELD_REFINEMENT_REJECT_MESSAGES: dict[str, str] = {
    "no_suggestion": "Nincs függőben lévő javaslat.",
    "invalid_suggestion": "A javaslat sérült — nem fogadható el.",
    "missing_context_identity": (
        "A javaslathoz vagy az aktuális igehelyhez nem tartozik kontextus-"
        "azonosító — nem fogadható el."
    ),
    "reference_mismatch": (
        "A javaslat egy másik igehelyhez készült — nem fogadható el "
        "ehhez a szöveghez."
    ),
    "context_hash_mismatch": (
        "A bibliai szöveg vagy a mező tartalma megváltozott a javaslat "
        "elkészülte óta — változatlanul nem fogadható el."
    ),
}

_KEY_HC = {
    "condition": "sw_hc_condition",
    "false_response": "sw_hc_false_response",
    "human_need": "sw_hc_human_need",
    "divine_action": "sw_hc_divine_action",
    "grace_response": "sw_hc_grace_response",
}
_KEY_LT = {
    "listener_question": "sw_lt_listener_question",
    "listener_resistance": "sw_lt_listener_resistance",
    "sermon_tension": "sw_lt_sermon_tension",
}
_KEY_GA = {
    "divine_gracious_action": "sw_ga_divine_gracious_action",
    "christ_connection": "sw_ga_christ_connection",
    "christ_connection_type": "sw_ga_christ_connection_type",
    "promised_resolution": "sw_ga_promised_resolution",
    "grace_enabled_response": "sw_ga_grace_enabled_response",
}
_KEY_PATH = {
    "type": "sw_path_type",
    "reason": "sw_path_reason",
    "starting_point": "sw_path_starting_point",
    "first_shift": "sw_path_first_shift",
    "deepening": "sw_path_deepening",
    "reinterpretation": "sw_path_reinterpretation",
    "destination": "sw_path_destination",
}
_KEY_ENTRY = {
    "today_connection": "sw_entry_today_connection",
    "type": "sw_entry_type",
    "text": "sw_entry_text",
}
_ADOPT_ENTRY_PENDING = "_sw_entry_adopt_pending"
_ADOPT_ENTRY_TODAY_PENDING = "_sw_entry_today_adopt_pending"
_RESYNC_FLAG = "_sw_ui_resync"
# Több szakasz-render függvény is fut egyetlen scriptfuttatáson belül (öt
# fázisra csoportosított nézet) — a widget-szinkron csak EGYSZER futhat le
# egy futtatáson belül, különben egy már instanciált widget kulcsát írná
# felül (StreamlitAPIException). A jelzőt a shell törli minden futtatás
# elején, hogy a következő rerun újra szinkronizálhasson.
_RESYNC_DONE_THIS_RUN = "_sw_ui_resync_done_this_run"
_ADOPT_FEEDBACK = "_sw_adopt_feedback"
_ADOPT_SERMON_PENDING = "_sw_sermon_idea_adopt_pending"
_ADOPT_HC_PENDING = "_sw_hc_adopt_pending"
_ADOPT_LT_PENDING = "_sw_lt_adopt_pending"
_ADOPT_GA_PENDING = "_sw_ga_adopt_pending"
_ADOPT_PATH_PENDING = "_sw_path_adopt_pending"
_ADOPT_ARC_PREFILL_PENDING = "_sw_path_arc_prefill_pending"
_ADOPT_MOVEMENTS_PENDING = "_sw_movements_adopt_pending"
_ADOPT_HC_OVERWRITE_CONFIRM = "_sw_hc_adopt_overwrite_confirm"
_ADOPT_SERMON_OVERWRITE_CONFIRM = "_sw_sermon_idea_adopt_overwrite_confirm"
_ADOPT_LT_OVERWRITE_CONFIRM = "_sw_lt_adopt_overwrite_confirm"
_ADOPT_GA_OVERWRITE_CONFIRM = "_sw_ga_adopt_overwrite_confirm"
_ADOPT_PATH_OVERWRITE_CONFIRM = "_sw_path_adopt_overwrite_confirm"
_MV_DELETE_PENDING = "_sw_mv_delete_pending"
_MV_WIDGET_PREFIX = "sw_mv_"
_IMG_WIDGET_PREFIX = "sw_en_img_"
_ILL_WIDGET_PREFIX = "sw_en_ill_"
_APP_WIDGET_PREFIX = "sw_en_app_"
_ADOPT_EN_ALL_PENDING = "_sw_en_adopt_all_pending"
_ADOPT_EN_IMAGES_PENDING = "_sw_en_adopt_images_pending"
_ADOPT_EN_ILL_PENDING = "_sw_en_adopt_ill_pending"
_ADOPT_EN_APPS_PENDING = "_sw_en_adopt_apps_pending"
_ADOPT_CL_PENDING = "_sw_cl_adopt_pending"
_ADOPT_LECTION_PENDING = "_sw_lection_adopt_pending"
_LECTION_RUF_PENDING = "_sw_lection_ruf_pending"
_ADOPT_PRAYER_PENDING = "_sw_prayer_adopt_pending"
_KEY_DIAG = {
    "self_review_strengths": "sw_diag_self_strengths",
    "self_review_uncertainties": "sw_diag_self_uncertainties",
    "self_review_priority": "sw_diag_self_priority",
    "self_review_focus": "sw_diag_self_focus",
}
_KEY_CL = {
    "type": "sw_cl_type",
    "final_discovery": "sw_cl_final_discovery",
    "hope": "sw_cl_hope",
    "call_or_response": "sw_cl_call_or_response",
    "image_or_line": "sw_cl_image_or_line",
    "open_question": "sw_cl_open_question",
    "tone": "sw_cl_tone",
}
_KEY_LECTION = {
    "reference": "sw_lection_reference",
    "connection_type": "sw_lection_connection_type",
    "function": "sw_lection_function",
    "rationale": "sw_lection_rationale",
    "text": "sw_lection_text",
    "notes": "sw_lection_notes",
    "testament_preference": "sw_lection_testament_preference",
    "length_preference": "sw_lection_length_preference",
    "user_focus": "sw_lection_user_focus",
}
DEFAULT_LECTION_CONNECTION_UI = "thematic"
DEFAULT_LECTION_TESTAMENT_UI = "any"
DEFAULT_LECTION_LENGTH_UI = "standard"
_KEY_PRAYER_COMMON = {
    "tone_preference": "sw_prayer_tone",
    "general_focus": "sw_prayer_general_focus",
    "rewrite_mode": "sw_prayer_rewrite_mode",
}
_KEY_PRAYER_BEFORE = {
    "own_thoughts": "sw_prayer_before_own_thoughts",
    "purpose": "sw_prayer_before_purpose",
    "movement_notes": "sw_prayer_before_movement_notes",
    "selected_opening": "sw_prayer_before_selected_opening",
    "selected_lines": "sw_prayer_before_selected_lines",
    "closing_direction": "sw_prayer_before_closing_direction",
}
_KEY_PRAYER_AFTER = {
    "own_thoughts": "sw_prayer_after_own_thoughts",
    "purpose": "sw_prayer_after_purpose",
    "movement_notes": "sw_prayer_after_movement_notes",
    "selected_opening": "sw_prayer_after_selected_opening",
    "selected_lines": "sw_prayer_after_selected_lines",
    "closing_direction": "sw_prayer_after_closing_direction",
}
_KEY_OUTLINE = {
    "content": "sw_outline_content",
    "main_idea": "sw_outline_main_idea",
    "main_idea_summary": "sw_outline_main_idea_summary",
    "listener_question": "sw_outline_listener_question",
    "central_tension": "sw_outline_central_tension",
    "listener_resistance": "sw_outline_listener_resistance",
    "divine_gracious_action": "sw_outline_divine_action",
    "christ_connection": "sw_outline_christ_connection",
    "christ_connection_type_label": "sw_outline_christ_type",
    "gospel_resolution": "sw_outline_gospel_resolution",
    "grace_enabled_response": "sw_outline_grace_response",
    "opening_direction": "sw_outline_opening",
    "manual_notes": "sw_outline_manual_notes",
}
_KEY_OUTLINE_CLOSING = {
    "final_insight": "sw_outline_closing_final",
    "gospel_assurance": "sw_outline_closing_hope",
    "invitation": "sw_outline_closing_invitation",
    "image_or_line": "sw_outline_closing_image",
    "open_question": "sw_outline_closing_question",
    "tone_label": "sw_outline_closing_tone",
}
_KEY_OUTLINE_LECTION = {
    "reference": "sw_outline_lection_ref",
    "function": "sw_outline_lection_function",
    "rationale": "sw_outline_lection_rationale",
}
_KEY_OUTLINE_PRAYER_BEFORE = {
    "own_thoughts": "sw_outline_prayer_before_own",
    "selected_opening": "sw_outline_prayer_before_opening",
    "selected_lines": "sw_outline_prayer_before_lines",
    "closing_direction": "sw_outline_prayer_before_closing",
}
_KEY_OUTLINE_PRAYER_AFTER = {
    "own_thoughts": "sw_outline_prayer_after_own",
    "selected_opening": "sw_outline_prayer_after_opening",
    "selected_lines": "sw_outline_prayer_after_lines",
    "closing_direction": "sw_outline_prayer_after_closing",
}
_OUTLINE_MV_PREFIX = "sw_outline_mv_"
_CONFIRM_OUTLINE_OVERWRITE = "_sw_outline_confirm_overwrite"
_OUTLINE_ASSEMBLY_FLASH_WARNINGS = "_sw_outline_assembly_flash_warnings"
_OUTLINE_ASSEMBLY_FLASH_SUCCESS = "_sw_outline_assembly_flash_success"
_PENDING_PRAYER_SUGGEST = "_sw_prayer_suggest_pending"
_PRAYER_CONFIRM_PREFIX = "_sw_prayer_confirm_"
_PRAYER_BASELINE_PREFIX = "_sw_prayer_baseline_"
_PRAYER_EXPAND_PLAN_PREFIX = "_sw_prayer_expand_plan_"
DEFAULT_PRAYER_TONE_UI = "mixed"
DEFAULT_PRAYER_REWRITE_UI = "integrate_into_arc"
_CL_FIELDS = (
    ("type", "Lezárás iránya", "", False),
    (
        "final_discovery",
        "Végső felismerés",
        "Fogalmazd meg egyetlen világos mondatban, mit lásson másként a "
        "hallgató az igehirdetés végére.",
        False,
    ),
    (
        "hope",
        "Evangéliumi bizonyosság",
        "Mi az az isteni ígéret, kegyelmi valóság vagy Krisztusban adott "
        "bizonyosság, amelyre a hallgató támaszkodhat?",
        False,
    ),
    (
        "call_or_response",
        "Kegyelemből fakadó meghívás",
        "Milyen válaszra hívhatja az Ige a hallgatót Isten kegyelmi "
        "cselekvésének fényében? Ne parancslistát írj, hanem egy világos, "
        "megélhető irányt.",
        True,
    ),
    (
        "image_or_line",
        "Záró kép vagy mondatmag",
        "Adj egy rövid kép- vagy mondatmagot a lezárás megfogalmazásához. "
        "Ez még ne legyen teljes kész záróbekezdés.",
        True,
    ),
    (
        "open_question",
        "Nyitva maradó kérdés",
        "Ha indokolt, fogalmazz meg egy őszinte kérdést, amely tovább "
        "dolgozhat a hallgatóban. Ne tartalmazza előre a választ.",
        True,
    ),
    ("tone", "Hangnem", "", False),
)
DEFAULT_CLOSING_TYPE_UI = "gospel_assurance"
DEFAULT_CLOSING_TONE_UI = "hopeful"
_EN_IMG_DELETE_PENDING = "_sw_en_img_delete_pending"
_EN_ILL_DELETE_PENDING = "_sw_en_ill_delete_pending"
_EN_APP_DELETE_PENDING = "_sw_en_app_delete_pending"
_IMG_FIELDS = (
    "image",
    "textual_basis",
    "homiletical_function",
    "placement",
    "movement_id",
    "development_notes",
)
_ILL_FIELDS = (
    "idea",
    "source",
    "function",
    "placement",
    "movement_id",
    "connection_to_text",
    "risk_or_limit",
)
_APP_FIELDS = (
    "application",
    "scope",
    "gospel_basis",
    "concreteness",
    "placement",
    "movement_id",
    "pastoral_caution",
)
_MV_FIELDS = (
    "title",
    "role",
    "core_content",
    "textual_basis",
    "listener_discovery",
    "transition_to_next",
)

_HC_PROMPT_TO_UI = {
    "human_condition": "condition",
    "false_response": "false_response",
    "human_need": "human_need",
    "divine_action": "divine_action",
    "grace_response": "grace_response",
}


def _session_str(*keys: str) -> str:
    for key in keys:
        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _session_passage_text() -> str:
    """Központi passage_text; mentés előtt a szerkesztő widget is elfogadható."""
    for key in ("passage_text", "passage_text_input"):
        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.replace("\r\n", "\n").replace("\r", "\n")
    return ""


def _show_adopt_feedback_if_any() -> None:
    msg = st.session_state.pop(_ADOPT_FEEDBACK, None)
    if msg:
        st.success(str(msg))


def _mark_adopt_feedback() -> None:
    st.session_state[_ADOPT_FEEDBACK] = "A javaslat bekerült a műhelyanyagba."


def _hc_field_categories() -> list[tuple[str, str]]:
    return [(field, category) for field, _label, category, _opt in _HC_FIELDS]


def _lt_field_categories() -> list[tuple[str, str]]:
    return [(field, category) for field, _t, _h, _p, category in _LT_FIELDS]


def _ga_field_categories() -> list[tuple[str, str]]:
    cats = [(field, category) for field, _t, _h, _p, category in _GA_TEXT_FIELDS]
    cats.append(("christ_connection_type", "Krisztus-kapcsolat típusa"))
    return cats


def _apply_pending_adopts_if_needed() -> None:
    """Átvétel: widget ELŐTT (pending + rerun). Tartós draft mentés; jóváhagyás külön."""
    pending_idea = st.session_state.pop(_ADOPT_SERMON_PENDING, None)
    if pending_idea is not None:
        text = str(pending_idea).strip()
        st.session_state[_KEY_SERMON_IDEA] = text
        accept_workshop_proposal(
            st.session_state,
            section_key="sermon_main_idea",
            block=text,
            source_section=_SOURCE_SERMON_MAIN,
        )
        _mark_adopt_feedback()

    pending_hc = st.session_state.pop(_ADOPT_HC_PENDING, None)
    if isinstance(pending_hc, dict):
        # Csak nem üres javasolt mezőket írjuk; üres javaslat ne töröljön.
        for ui_key, wkey in _KEY_HC.items():
            suggested = str(pending_hc.get(ui_key) or "").strip()
            if suggested:
                st.session_state[wkey] = suggested
        block = {
            field: (st.session_state.get(wkey) or "").strip()
            for field, wkey in _KEY_HC.items()
        }
        accept_workshop_proposal(
            st.session_state,
            section_key="human_condition",
            block=block,
            source_section=_SOURCE_HUMAN,
            field_categories=_hc_field_categories(),
            status_key="human_condition_status",
        )
        _mark_adopt_feedback()

    pending_lt = st.session_state.pop(_ADOPT_LT_PENDING, None)
    if isinstance(pending_lt, dict):
        for ui_key, wkey in _KEY_LT.items():
            suggested = str(pending_lt.get(ui_key) or "").strip()
            if suggested:
                st.session_state[wkey] = suggested
        # Preserve promised_resolution from durable data
        sw = ensure_sermon_workshop_state(st.session_state)
        current = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
        block = {
            field: (st.session_state.get(wkey) or "").strip()
            for field, wkey in _KEY_LT.items()
        }
        block["promised_resolution"] = str(current.get("promised_resolution") or "")
        accept_workshop_proposal(
            st.session_state,
            section_key="listener_tension",
            block=block,
            source_section=_SOURCE_LISTENER,
            field_categories=_lt_field_categories(),
            status_key="listener_tension_status",
        )
        _mark_adopt_feedback()

    pending_ga = st.session_state.pop(_ADOPT_GA_PENDING, None)
    if isinstance(pending_ga, dict):
        for ui_key, wkey in _KEY_GA.items():
            suggested = str(pending_ga.get(ui_key) or "").strip()
            if not suggested:
                continue
            if ui_key == "christ_connection_type":
                st.session_state[wkey] = normalize_christ_connection_type(suggested)
            else:
                st.session_state[wkey] = suggested
        _persist_gospel_arc_from_widgets()
        sw = ensure_sermon_workshop_state(st.session_state)
        arc = (
            sw.get("christ_centered_arc")
            if isinstance(sw.get("christ_centered_arc"), dict)
            else {}
        )
        lt = (
            sw.get("listener_tension")
            if isinstance(sw.get("listener_tension"), dict)
            else {}
        )
        accept_workshop_proposal(
            st.session_state,
            section_key="christ_centered_arc",
            block={
                "divine_gracious_action": str(arc.get("divine_gracious_action") or ""),
                "christ_connection": str(arc.get("christ_connection") or ""),
                "christ_connection_type": str(arc.get("christ_connection_type") or ""),
                "grace_enabled_response": str(arc.get("grace_enabled_response") or ""),
            },
            source_section=_SOURCE_GOSPEL,
            field_categories=_ga_field_categories(),
            status_key="christ_centered_arc_status",
        )
        promised = str(lt.get("promised_resolution") or "").strip()
        if promised and not _decision_is_duplicate(
            source_section=_SOURCE_GOSPEL,
            category="Evangéliumi feloldás",
            content=promised,
        ):
            add_approved_sermon_decision(
                st.session_state,
                _SOURCE_GOSPEL,
                "Evangéliumi feloldás",
                promised,
            )
        _mark_adopt_feedback()

    pending_path = st.session_state.pop(_ADOPT_PATH_PENDING, None)
    if isinstance(pending_path, dict):
        for ui_key, wkey in _KEY_PATH.items():
            if ui_key not in pending_path:
                continue
            suggested = str(pending_path.get(ui_key) or "").strip()
            if ui_key == "type":
                st.session_state[wkey] = normalize_sermon_path_type(suggested)
            elif suggested:
                st.session_state[wkey] = suggested
        _persist_sermon_path_from_widgets()
        sw = ensure_sermon_workshop_state(st.session_state)
        path = sw.get("sermon_path") if isinstance(sw.get("sermon_path"), dict) else {}
        accept_workshop_proposal(
            st.session_state,
            section_key="sermon_path",
            block=dict(path),
            source_section=_SOURCE_PATH,
            field_categories=[
                ("type", "Út típusa"),
                ("reason", "Indoklás"),
                ("starting_point", "Kiindulópont"),
                ("destination", "Cél"),
            ],
            status_key="sermon_path_status",
        )
        _mark_adopt_feedback()

    pending_mvs = st.session_state.pop(_ADOPT_MOVEMENTS_PENDING, None)
    if isinstance(pending_mvs, list):
        normalized = normalize_sermon_movements(pending_mvs)
        update_sermon_workshop_section(
            st.session_state, "sermon_movements", normalized
        )
        update_sermon_workshop_section(
            st.session_state, "sermon_path_status", "approved"
        )
        for mv in normalized:
            title = str(mv.get("title") or "").strip()
            core = str(mv.get("core_content") or "").strip()
            content = title if not core else (f"{title}: {core}" if title else core)
            if not content:
                continue
            if _decision_is_duplicate(
                source_section=_SOURCE_PATH,
                category="Mozgás",
                content=content,
            ):
                continue
            add_approved_sermon_decision(
                st.session_state, _SOURCE_PATH, "Mozgás", content
            )
        _clear_movement_widgets()
        st.session_state[_RESYNC_FLAG] = True
        _mark_adopt_feedback()

    pending_en_all = st.session_state.pop(_ADOPT_EN_ALL_PENDING, None)
    if isinstance(pending_en_all, dict):
        if pending_en_all.get("images") is not None:
            update_sermon_workshop_section(
                st.session_state,
                "selected_images",
                normalize_textual_images(pending_en_all.get("images")),
            )
            _clear_enrichment_widgets("images")
        if pending_en_all.get("illustrations") is not None:
            update_sermon_workshop_section(
                st.session_state,
                "illustrations",
                normalize_illustrations(pending_en_all.get("illustrations")),
            )
            _clear_enrichment_widgets("illustrations")
        if pending_en_all.get("applications") is not None:
            update_sermon_workshop_section(
                st.session_state,
                "applications",
                normalize_applications(pending_en_all.get("applications")),
            )
            _clear_enrichment_widgets("applications")
        update_sermon_workshop_section(
            st.session_state, "enrichment_status", "approved"
        )
        st.session_state[_RESYNC_FLAG] = True
        _mark_adopt_feedback()

    pending_en_imgs = st.session_state.pop(_ADOPT_EN_IMAGES_PENDING, None)
    if isinstance(pending_en_imgs, list):
        update_sermon_workshop_section(
            st.session_state, "selected_images", normalize_textual_images(pending_en_imgs)
        )
        update_sermon_workshop_section(
            st.session_state, "enrichment_status", "approved"
        )
        _clear_enrichment_widgets("images")
        st.session_state[_RESYNC_FLAG] = True
        _mark_adopt_feedback()

    pending_en_ills = st.session_state.pop(_ADOPT_EN_ILL_PENDING, None)
    if isinstance(pending_en_ills, list):
        update_sermon_workshop_section(
            st.session_state, "illustrations", normalize_illustrations(pending_en_ills)
        )
        update_sermon_workshop_section(
            st.session_state, "enrichment_status", "approved"
        )
        _clear_enrichment_widgets("illustrations")
        st.session_state[_RESYNC_FLAG] = True
        _mark_adopt_feedback()

    pending_en_apps = st.session_state.pop(_ADOPT_EN_APPS_PENDING, None)
    if isinstance(pending_en_apps, list):
        update_sermon_workshop_section(
            st.session_state, "applications", normalize_applications(pending_en_apps)
        )
        update_sermon_workshop_section(
            st.session_state, "enrichment_status", "approved"
        )
        _clear_enrichment_widgets("applications")
        st.session_state[_RESYNC_FLAG] = True
        _mark_adopt_feedback()

    pending_cl = st.session_state.pop(_ADOPT_CL_PENDING, None)
    if isinstance(pending_cl, dict):
        for ui_key, wkey in _KEY_CL.items():
            suggested = str(pending_cl.get(ui_key) or "").strip()
            if not suggested:
                continue
            if ui_key == "type":
                st.session_state[wkey] = normalize_closing_type(suggested)
            elif ui_key == "tone":
                st.session_state[wkey] = normalize_closing_tone(suggested)
            else:
                st.session_state[wkey] = suggested
        _persist_closing_from_widgets()
        update_sermon_workshop_section(
            st.session_state, "closing_status", "approved"
        )
        _mark_adopt_feedback()

    pending_lection = st.session_state.pop(_ADOPT_LECTION_PENDING, None)
    if isinstance(pending_lection, dict):
        pending_analysis = pending_lection.pop("connection_analysis", None)
        for ui_key, wkey in _KEY_LECTION.items():
            if ui_key not in pending_lection:
                continue
            suggested = str(pending_lection.get(ui_key) or "").strip()
            if ui_key == "connection_type":
                st.session_state[wkey] = (
                    normalize_lection_connection_type(suggested)
                    if suggested
                    else DEFAULT_LECTION_CONNECTION_UI
                )
            elif ui_key == "testament_preference":
                st.session_state[wkey] = normalize_lection_testament_preference(
                    suggested
                )
            elif ui_key == "length_preference":
                st.session_state[wkey] = normalize_lection_length_preference(
                    suggested
                )
            elif suggested or ui_key in (
                "reference",
                "function",
                "rationale",
                "notes",
            ):
                # Átvétel: csak a választott mezőket írja; textet nem törli itt
                if ui_key == "text":
                    continue
                st.session_state[wkey] = suggested
        _persist_lection_from_widgets(include_text=False)
        update_sermon_workshop_section(
            st.session_state, "lection_status", "approved"
        )
        # Javaslat részeként elkészült kapcsolati elemzés átvétele
        if isinstance(pending_analysis, dict) and pending_analysis.get("ok") is not False:
            save_lection_connection_analysis(st.session_state, pending_analysis)
        else:
            sw = ensure_sermon_workshop_state(st.session_state)
            sug = sw.get("lection_suggestions")
            if isinstance(sug, dict) and isinstance(sug.get("connection_analysis"), dict):
                analysis = sug["connection_analysis"]
                adopted_ref = str(
                    st.session_state.get(_KEY_LECTION["reference"]) or ""
                ).strip()
                analysis_ref = str(analysis.get("lection_reference") or "").strip()
                if adopted_ref and (
                    not analysis_ref or references_equivalent(adopted_ref, analysis_ref)
                ):
                    save_lection_connection_analysis(st.session_state, analysis)
        _mark_adopt_feedback()

    pending_prayer = st.session_state.pop(_ADOPT_PRAYER_PENDING, None)
    if isinstance(pending_prayer, dict):
        side = str(pending_prayer.get("side") or "before").strip()
        keys = _KEY_PRAYER_BEFORE if side != "after" else _KEY_PRAYER_AFTER
        # own_thoughts soha nem törlődik átvételkor
        if "purpose" in pending_prayer:
            val = str(pending_prayer.get("purpose") or "").strip()
            if val:
                st.session_state[keys["purpose"]] = val
        if "movement_notes" in pending_prayer:
            val = str(pending_prayer.get("movement_notes") or "").strip()
            if val:
                st.session_state[keys["movement_notes"]] = val
        if "selected_opening" in pending_prayer:
            val = str(pending_prayer.get("selected_opening") or "").strip()
            if val:
                st.session_state[keys["selected_opening"]] = val
        if "closing_direction" in pending_prayer:
            val = str(pending_prayer.get("closing_direction") or "").strip()
            if val:
                st.session_state[keys["closing_direction"]] = val
        if "selected_lines" in pending_prayer:
            raw_lines = pending_prayer.get("selected_lines")
            if isinstance(raw_lines, list):
                lines = [str(x).strip() for x in raw_lines if str(x).strip()]
            else:
                lines = _lines_from_widget(raw_lines)
            # Teljes terv átvétele: cserél, ne duplikál
            st.session_state[keys["selected_lines"]] = "\n".join(lines)
        else:
            append_line = str(pending_prayer.get("append_line") or "").strip()
            if append_line:
                current = str(st.session_state.get(keys["selected_lines"]) or "")
                lines = [
                    ln.strip()
                    for ln in current.replace("\r\n", "\n").split("\n")
                    if ln.strip()
                ]
                if append_line not in lines:
                    lines.append(append_line)
                st.session_state[keys["selected_lines"]] = "\n".join(lines)
        _persist_prayer_from_widgets()


def _en_widget_key(prefix: str, item_id: str, field: str) -> str:
    return f"{prefix}{item_id}_{field}"


def _clear_enrichment_widgets(kind: str | None = None) -> None:
    prefixes: tuple[str, ...]
    if kind == "images":
        prefixes = (_IMG_WIDGET_PREFIX,)
    elif kind == "illustrations":
        prefixes = (_ILL_WIDGET_PREFIX,)
    elif kind == "applications":
        prefixes = (_APP_WIDGET_PREFIX,)
    else:
        prefixes = (_IMG_WIDGET_PREFIX, _ILL_WIDGET_PREFIX, _APP_WIDGET_PREFIX)
    stale = [
        key
        for key in list(st.session_state.keys())
        if isinstance(key, str) and key.startswith(prefixes)
    ]
    for key in stale:
        st.session_state.pop(key, None)


def _movement_options() -> list[tuple[str, str]]:
    sw = ensure_sermon_workshop_state(st.session_state)
    mvs = normalize_sermon_movements(sw.get("sermon_movements"))
    options: list[tuple[str, str]] = [("", "— nincs mozgáskapcsolat —")]
    for idx, mv in enumerate(mvs, start=1):
        mid = str(mv.get("id") or "")
        if not mid:
            continue
        title = str(mv.get("title") or f"Mozgás {idx}").strip()
        role = movement_role_label(mv.get("role"))
        options.append((mid, f"{idx}. {title} ({role})"))
    return options


def _read_textual_images_from_widgets() -> list[dict[str, str]]:
    sw = ensure_sermon_workshop_state(st.session_state)
    current = normalize_textual_images(sw.get("selected_images"))
    out: list[dict[str, str]] = []
    for item in current:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        row = dict(item)
        for field in _IMG_FIELDS:
            wkey = _en_widget_key(_IMG_WIDGET_PREFIX, iid, field)
            if wkey not in st.session_state:
                continue
            raw = st.session_state.get(wkey)
            if field == "homiletical_function":
                row[field] = normalize_image_function(raw)
            elif field == "placement":
                row[field] = normalize_placement_kind(raw)
            else:
                row[field] = str(raw or "").strip()
        out.append(row)
    return out


def _read_illustrations_from_widgets() -> list[dict[str, str]]:
    sw = ensure_sermon_workshop_state(st.session_state)
    current = normalize_illustrations(sw.get("illustrations"))
    out: list[dict[str, str]] = []
    for item in current:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        row = dict(item)
        for field in _ILL_FIELDS:
            wkey = _en_widget_key(_ILL_WIDGET_PREFIX, iid, field)
            if wkey not in st.session_state:
                continue
            raw = st.session_state.get(wkey)
            if field == "source":
                row[field] = normalize_illustration_source(raw)
            elif field == "function":
                row[field] = normalize_illustration_function(raw)
            elif field == "placement":
                row[field] = normalize_placement_kind(raw)
            else:
                row[field] = str(raw or "").strip()
        out.append(row)
    return out


def _read_applications_from_widgets() -> list[dict[str, str]]:
    sw = ensure_sermon_workshop_state(st.session_state)
    current = normalize_applications(sw.get("applications"))
    out: list[dict[str, str]] = []
    for item in current:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        row = dict(item)
        for field in _APP_FIELDS:
            wkey = _en_widget_key(_APP_WIDGET_PREFIX, iid, field)
            if wkey not in st.session_state:
                continue
            raw = st.session_state.get(wkey)
            if field == "scope":
                row[field] = normalize_application_scope(raw)
            elif field == "placement":
                row[field] = normalize_placement_kind(raw)
            else:
                row[field] = str(raw or "").strip()
        out.append(row)
    return out


def _persist_enrichment_from_widgets() -> None:
    update_sermon_workshop_section(
        st.session_state, "selected_images", _read_textual_images_from_widgets()
    )
    update_sermon_workshop_section(
        st.session_state, "illustrations", _read_illustrations_from_widgets()
    )
    update_sermon_workshop_section(
        st.session_state, "applications", _read_applications_from_widgets()
    )


def _existing_source_refs() -> set[str]:
    sw = ensure_sermon_workshop_state(st.session_state)
    refs: set[str] = set()
    for key in ("selected_images", "illustrations", "applications"):
        for item in sw.get(key) or []:
            if isinstance(item, dict):
                ref = str(item.get("source_ref") or "").strip()
                if ref:
                    refs.add(ref)
    return refs


def _collect_text_workshop_import_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    basket = st.session_state.get("basket") or []
    if isinstance(basket, list):
        for idx, entry in enumerate(basket):
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            source, text = str(entry[0] or ""), str(entry[1] or "").strip()
            if not text:
                continue
            if source == "Illusztráció":
                items.append(
                    {
                        "kind": "illustration",
                        "label": f"Illusztráció ({idx + 1})",
                        "content": text,
                        "source_ref": f"basket:Illusztráció:{idx}",
                    }
                )
            elif source == "Aktualizálás":
                items.append(
                    {
                        "kind": "application",
                        "label": f"Aktualizálás ({idx + 1})",
                        "content": text,
                        "source_ref": f"basket:Aktualizálás:{idx}",
                    }
                )
    tw = ensure_text_workshop_state(st.session_state)
    for insight in tw.get("approved_insights") or []:
        if not isinstance(insight, dict):
            continue
        content = str(insight.get("content") or "").strip()
        iid = str(insight.get("id") or "").strip()
        if not content:
            continue
        items.append(
            {
                "kind": "application",
                "label": f"Jóváhagyott felismerés ({insight.get('category') or '—'})",
                "content": content,
                "source_ref": f"insight:{iid or content[:40]}",
            }
        )
    return items


def _request_adopt_enrichment_plan(
    *,
    images: list[dict[str, str]] | None = None,
    illustrations: list[dict[str, str]] | None = None,
    applications: list[dict[str, str]] | None = None,
) -> None:
    st.session_state[_ADOPT_EN_ALL_PENDING] = {
        "images": images,
        "illustrations": illustrations,
        "applications": applications,
    }
    st.rerun()


def _request_adopt_enrichment_images(images: list[dict[str, str]]) -> None:
    st.session_state[_ADOPT_EN_IMAGES_PENDING] = list(images or [])
    st.rerun()


def _request_adopt_enrichment_illustrations(items: list[dict[str, str]]) -> None:
    st.session_state[_ADOPT_EN_ILL_PENDING] = list(items or [])
    st.rerun()


def _request_adopt_enrichment_applications(items: list[dict[str, str]]) -> None:
    st.session_state[_ADOPT_EN_APPS_PENDING] = list(items or [])
    st.rerun()


def _append_enrichment_item(kind: str) -> None:
    _persist_enrichment_from_widgets()
    sw = ensure_sermon_workshop_state(st.session_state)
    if kind == "images":
        current = normalize_textual_images(sw.get("selected_images"))
        if len(current) >= MAX_TEXTUAL_IMAGES:
            return
        current.append(empty_textual_image())
        update_sermon_workshop_section(st.session_state, "selected_images", current)
    elif kind == "illustrations":
        current = normalize_illustrations(sw.get("illustrations"))
        if len(current) >= MAX_ILLUSTRATIONS:
            return
        current.append(empty_illustration())
        update_sermon_workshop_section(st.session_state, "illustrations", current)
    else:
        current = normalize_applications(sw.get("applications"))
        if len(current) >= MAX_APPLICATIONS:
            return
        current.append(empty_application())
        update_sermon_workshop_section(st.session_state, "applications", current)
    st.session_state[_RESYNC_FLAG] = True


def _sync_enrichment_widgets(
    *,
    force: bool,
    images: list[dict[str, str]],
    illustrations: list[dict[str, str]],
    applications: list[dict[str, str]],
) -> None:
    if force:
        _clear_enrichment_widgets()
    live_img = {str(i.get("id") or "") for i in images if i.get("id")}
    live_ill = {str(i.get("id") or "") for i in illustrations if i.get("id")}
    live_app = {str(i.get("id") or "") for i in applications if i.get("id")}
    if not force:
        for prefix, live_ids in (
            (_IMG_WIDGET_PREFIX, live_img),
            (_ILL_WIDGET_PREFIX, live_ill),
            (_APP_WIDGET_PREFIX, live_app),
        ):
            stale = [
                key
                for key in list(st.session_state.keys())
                if isinstance(key, str)
                and key.startswith(prefix)
                and not any(
                    key.startswith(f"{prefix}{iid}_") for iid in live_ids
                )
            ]
            for key in stale:
                st.session_state.pop(key, None)
    mv_options = _movement_options()
    mv_ids = [mid for mid, _label in mv_options if mid]
    for item in images:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        for field in _IMG_FIELDS:
            wkey = _en_widget_key(_IMG_WIDGET_PREFIX, iid, field)
            if force or wkey not in st.session_state:
                if field == "homiletical_function":
                    raw = str(item.get(field) or "").strip()
                    st.session_state[wkey] = (
                        normalize_image_function(raw) if raw else "open"
                    )
                elif field == "placement":
                    st.session_state[wkey] = normalize_placement_kind(
                        item.get(field)
                    )
                elif field == "movement_id":
                    mid = str(item.get("movement_id") or "")
                    st.session_state[wkey] = mid if mid in mv_ids else ""
                else:
                    st.session_state[wkey] = str(item.get(field) or "")
    for item in illustrations:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        for field in _ILL_FIELDS:
            wkey = _en_widget_key(_ILL_WIDGET_PREFIX, iid, field)
            if force or wkey not in st.session_state:
                if field == "source":
                    st.session_state[wkey] = normalize_illustration_source(
                        item.get(field)
                    )
                elif field == "function":
                    raw = str(item.get(field) or "").strip()
                    st.session_state[wkey] = (
                        normalize_illustration_function(raw) if raw else "bridge"
                    )
                elif field == "placement":
                    st.session_state[wkey] = normalize_placement_kind(
                        item.get(field)
                    )
                elif field == "movement_id":
                    mid = str(item.get("movement_id") or "")
                    st.session_state[wkey] = mid if mid in mv_ids else ""
                else:
                    st.session_state[wkey] = str(item.get(field) or "")
    for item in applications:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        for field in _APP_FIELDS:
            wkey = _en_widget_key(_APP_WIDGET_PREFIX, iid, field)
            if force or wkey not in st.session_state:
                if field == "scope":
                    st.session_state[wkey] = normalize_application_scope(
                        item.get(field)
                    )
                elif field == "placement":
                    st.session_state[wkey] = normalize_placement_kind(
                        item.get(field)
                    )
                elif field == "movement_id":
                    mid = str(item.get("movement_id") or "")
                    st.session_state[wkey] = mid if mid in mv_ids else ""
                else:
                    st.session_state[wkey] = str(item.get(field) or "")


def _mv_widget_key(movement_id: str, field: str) -> str:
    return f"{_MV_WIDGET_PREFIX}{movement_id}_{field}"


def _clear_movement_widgets() -> None:
    stale = [
        key
        for key in list(st.session_state.keys())
        if isinstance(key, str) and key.startswith(_MV_WIDGET_PREFIX)
    ]
    for key in stale:
        st.session_state.pop(key, None)


def _persist_gospel_arc_from_widgets() -> None:
    """Widgetek → christ_centered_arc + listener_tension.promised_resolution."""
    sw = ensure_sermon_workshop_state(st.session_state)
    arc = {
        "divine_gracious_action": (
            st.session_state.get(_KEY_GA["divine_gracious_action"]) or ""
        ).strip(),
        "christ_connection": (
            st.session_state.get(_KEY_GA["christ_connection"]) or ""
        ).strip(),
        "christ_connection_type": normalize_christ_connection_type(
            st.session_state.get(_KEY_GA["christ_connection_type"])
        ),
        "grace_enabled_response": (
            st.session_state.get(_KEY_GA["grace_enabled_response"]) or ""
        ).strip(),
    }
    update_sermon_workshop_section(st.session_state, "christ_centered_arc", arc)
    lt = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    lt_block = {
        "listener_question": str(lt.get("listener_question") or ""),
        "listener_resistance": str(lt.get("listener_resistance") or ""),
        "sermon_tension": str(lt.get("sermon_tension") or ""),
        "promised_resolution": (
            st.session_state.get(_KEY_GA["promised_resolution"]) or ""
        ).strip(),
    }
    update_sermon_workshop_section(st.session_state, "listener_tension", lt_block)


def _apply_pending_arc_prefill_if_needed() -> None:
    """Mozgásból-előtöltés: widget ELŐTT (pending + rerun), a régi mozgás megmarad."""
    pending = st.session_state.pop(_ADOPT_ARC_PREFILL_PENDING, None)
    if not isinstance(pending, dict):
        return
    field = str(pending.get("field") or "")
    text = str(pending.get("text") or "")
    wkey = _KEY_PATH.get(field)
    if wkey:
        st.session_state[wkey] = text


def _render_arc_field_prefill_button(*, field: str, role: str, label: str) -> None:
    """Első látásváltás / mélyítés előtöltése a megfelelő szerepű mozgásból.

    Csak átmásolja a tartalmat a szövegmezőbe — a mozgás maga változatlanul
    megmarad a `sermon_movements` listában (nincs törlés/migráció-veszteség).
    """
    movements = normalize_sermon_movements(
        ensure_sermon_workshop_state(st.session_state).get("sermon_movements")
    )
    match = next(
        (
            m
            for m in movements
            if (m.get("role") or "") == role
            and ((m.get("core_content") or "").strip() or (m.get("title") or "").strip())
        ),
        None,
    )
    if st.button(label, key=f"sw_path_prefill_{field}", disabled=match is None):
        if match is None:
            st.info(
                f"Nincs „{movement_role_label(role)}” szerepű, tartalommal "
                "kitöltött mozgás, amiből előtölthetnéd."
            )
        else:
            content = (match.get("core_content") or "").strip() or (
                match.get("title") or ""
            ).strip()
            st.session_state[_ADOPT_ARC_PREFILL_PENDING] = {
                "field": field,
                "text": content,
            }
            st.rerun()


def _persist_sermon_path_from_widgets() -> None:
    """Widgetek → sermon_path (starting_point/first_shift/deepening/
    reinterpretation).

    Az egységesített modellben a type/reason/destination mezőknek már
    nincs saját widgetje — a bennük korábban tárolt legacy értéket
    megőrizzük (nem írjuk felül üresre), ha a widget nem létezik.
    """
    sw = ensure_sermon_workshop_state(st.session_state)
    existing = sw.get("sermon_path") if isinstance(sw.get("sermon_path"), dict) else {}
    path = {
        "type": (
            normalize_sermon_path_type(st.session_state[_KEY_PATH["type"]])
            if _KEY_PATH["type"] in st.session_state
            else str(existing.get("type") or "")
        ),
        "reason": (
            (st.session_state.get(_KEY_PATH["reason"]) or "").strip()
            if _KEY_PATH["reason"] in st.session_state
            else str(existing.get("reason") or "")
        ),
        "starting_point": (
            st.session_state.get(_KEY_PATH["starting_point"]) or ""
        ).strip(),
        "first_shift": (
            st.session_state.get(_KEY_PATH["first_shift"]) or ""
        ).strip(),
        "deepening": (
            st.session_state.get(_KEY_PATH["deepening"]) or ""
        ).strip(),
        "reinterpretation": (
            (st.session_state.get(_KEY_PATH["reinterpretation"]) or "").strip()
            if _KEY_PATH["reinterpretation"] in st.session_state
            else str(existing.get("reinterpretation") or "")
        ),
        "destination": (
            (st.session_state.get(_KEY_PATH["destination"]) or "").strip()
            if _KEY_PATH["destination"] in st.session_state
            else str(existing.get("destination") or "")
        ),
    }
    update_sermon_workshop_section(st.session_state, "sermon_path", path)


def _persist_entry_point_from_widgets() -> None:
    """Widgetek → entry_point (today_connection/type/text)."""
    block = {
        "today_connection": (
            st.session_state.get(_KEY_ENTRY["today_connection"]) or ""
        ).strip(),
        "type": normalize_entry_point_type(st.session_state.get(_KEY_ENTRY["type"])),
        "text": (st.session_state.get(_KEY_ENTRY["text"]) or "").strip(),
    }
    update_sermon_workshop_section(st.session_state, "entry_point", block)


def _read_movements_from_widgets() -> list[dict[str, str]]:
    """Tartós sorrend + widgetértékek → mozgáslista."""
    sw = ensure_sermon_workshop_state(st.session_state)
    current = normalize_sermon_movements(sw.get("sermon_movements"))
    out: list[dict[str, str]] = []
    for mv in current:
        mid = str(mv.get("id") or "")
        if not mid:
            continue
        item = dict(mv)
        for field in _MV_FIELDS:
            wkey = _mv_widget_key(mid, field)
            if wkey in st.session_state:
                raw = st.session_state.get(wkey)
                if field == "role":
                    item[field] = normalize_movement_role(raw)
                else:
                    item[field] = str(raw or "").strip()
        out.append(item)
    return out


def _persist_sermon_movements_from_widgets() -> None:
    update_sermon_workshop_section(
        st.session_state, "sermon_movements", _read_movements_from_widgets()
    )


def _apply_sw_ui_resync_if_needed() -> None:
    """Widgetkulcsok szinkronja a tartós sermon_workshop adatokkal (widget előtt).

    Több fázis-render függvény is meghívja ugyanazon scriptfuttatáson belül
    (öt fázisra csoportosított nézet) — a tényleges szinkron csak az első
    hívásnál fut le, a többi no-op, különben egy már instanciált widget
    session_state kulcsát írná felül.
    """
    if st.session_state.get(_RESYNC_DONE_THIS_RUN):
        return
    st.session_state[_RESYNC_DONE_THIS_RUN] = True

    sw = ensure_sermon_workshop_state(st.session_state)
    force = bool(st.session_state.pop(_RESYNC_FLAG, False))

    idea = sw.get("sermon_main_idea") or ""
    if force or _KEY_SERMON_IDEA not in st.session_state:
        st.session_state[_KEY_SERMON_IDEA] = idea

    hc = sw.get("human_condition") if isinstance(sw.get("human_condition"), dict) else {}
    for field, wkey in _KEY_HC.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(hc.get(field) or "")

    lt = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    for field, wkey in _KEY_LT.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(lt.get(field) or "")

    arc = (
        sw.get("christ_centered_arc")
        if isinstance(sw.get("christ_centered_arc"), dict)
        else {}
    )
    for field, wkey in _KEY_GA.items():
        if force or wkey not in st.session_state:
            if field == "promised_resolution":
                st.session_state[wkey] = str(lt.get("promised_resolution") or "")
            elif field == "christ_connection_type":
                raw = str(arc.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_christ_connection_type(raw)
                    if raw
                    else "none_or_uncertain"
                )
            else:
                st.session_state[wkey] = str(arc.get(field) or "")

    path = sw.get("sermon_path") if isinstance(sw.get("sermon_path"), dict) else {}
    for field, wkey in _KEY_PATH.items():
        if force or wkey not in st.session_state:
            if field == "type":
                raw = str(path.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_sermon_path_type(raw) if raw else "text_following"
                )
            else:
                st.session_state[wkey] = str(path.get(field) or "")

    entry = sw.get("entry_point") if isinstance(sw.get("entry_point"), dict) else {}
    for field, wkey in _KEY_ENTRY.items():
        if force or wkey not in st.session_state:
            if field == "type":
                st.session_state[wkey] = normalize_entry_point_type(entry.get(field))
            else:
                st.session_state[wkey] = str(entry.get(field) or "")

    movements = normalize_sermon_movements(sw.get("sermon_movements"))
    live_ids = {str(m.get("id") or "") for m in movements if m.get("id")}
    if force:
        _clear_movement_widgets()
    else:
        stale = [
            key
            for key in list(st.session_state.keys())
            if isinstance(key, str)
            and key.startswith(_MV_WIDGET_PREFIX)
            and not any(
                key.startswith(f"{_MV_WIDGET_PREFIX}{mid}_") for mid in live_ids
            )
        ]
        for key in stale:
            st.session_state.pop(key, None)
    for mv in movements:
        mid = str(mv.get("id") or "")
        if not mid:
            continue
        for field in _MV_FIELDS:
            wkey = _mv_widget_key(mid, field)
            if force or wkey not in st.session_state:
                if field == "role":
                    raw = str(mv.get(field) or "").strip()
                    st.session_state[wkey] = (
                        normalize_movement_role(raw) if raw else "deepening"
                    )
                else:
                    st.session_state[wkey] = str(mv.get(field) or "")

    images = normalize_textual_images(sw.get("selected_images"))
    illustrations = normalize_illustrations(sw.get("illustrations"))
    applications = normalize_applications(sw.get("applications"))
    _sync_enrichment_widgets(
        force=force,
        images=images,
        illustrations=illustrations,
        applications=applications,
    )

    closing = sw.get("closing") if isinstance(sw.get("closing"), dict) else {}
    for field, wkey in _KEY_CL.items():
        if force or wkey not in st.session_state:
            if field == "type":
                raw = str(closing.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_closing_type(raw) if raw else DEFAULT_CLOSING_TYPE_UI
                )
            elif field == "tone":
                raw = str(closing.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_closing_tone(raw) if raw else DEFAULT_CLOSING_TONE_UI
                )
            else:
                st.session_state[wkey] = str(closing.get(field) or "")

    for field, wkey in _KEY_DIAG.items():
        if force or wkey not in st.session_state:
            st.session_state[wkey] = str(sw.get(field) or "")

    lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    for field, wkey in _KEY_LECTION.items():
        if force or wkey not in st.session_state:
            if field == "connection_type":
                raw = str(lection.get(field) or "").strip()
                st.session_state[wkey] = (
                    normalize_lection_connection_type(raw) if raw else ""
                )
            elif field == "testament_preference":
                st.session_state[wkey] = normalize_lection_testament_preference(
                    lection.get(field)
                )
            elif field == "length_preference":
                st.session_state[wkey] = normalize_lection_length_preference(
                    lection.get(field)
                )
            elif field == "text":
                st.session_state[wkey] = normalize_passage_text(lection.get(field))
            else:
                st.session_state[wkey] = str(lection.get(field) or "")

    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    for field, wkey in _KEY_PRAYER_COMMON.items():
        if force or wkey not in st.session_state:
            if field == "tone_preference":
                st.session_state[wkey] = normalize_prayer_tone_preference(
                    prep.get(field)
                )
            elif field == "rewrite_mode":
                st.session_state[wkey] = normalize_prayer_rewrite_mode(
                    prep.get(field)
                )
            else:
                st.session_state[wkey] = str(prep.get(field) or "")
    before = prep.get("before") if isinstance(prep.get("before"), dict) else {}
    after = prep.get("after") if isinstance(prep.get("after"), dict) else {}
    for side_data, key_map in (
        (before, _KEY_PRAYER_BEFORE),
        (after, _KEY_PRAYER_AFTER),
    ):
        for field, wkey in key_map.items():
            if force or wkey not in st.session_state:
                if field == "selected_lines":
                    lines = side_data.get("selected_lines")
                    if isinstance(lines, list):
                        st.session_state[wkey] = "\n".join(
                            str(x).strip() for x in lines if str(x).strip()
                        )
                    else:
                        st.session_state[wkey] = str(lines or "")
                else:
                    st.session_state[wkey] = str(side_data.get(field) or "")

    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    for field, wkey in _KEY_OUTLINE.items():
        durable_val = str(outline.get(field) or "")
        if force or wkey not in st.session_state or (
            durable_val.strip() and not str(st.session_state.get(wkey) or "").strip()
        ):
            st.session_state[wkey] = durable_val
    closing_o = outline.get("closing") if isinstance(outline.get("closing"), dict) else {}
    for field, wkey in _KEY_OUTLINE_CLOSING.items():
        durable_val = str(closing_o.get(field) or "")
        if force or wkey not in st.session_state or (
            durable_val.strip() and not str(st.session_state.get(wkey) or "").strip()
        ):
            st.session_state[wkey] = durable_val
    lection_o = outline.get("lection") if isinstance(outline.get("lection"), dict) else {}
    for field, wkey in _KEY_OUTLINE_LECTION.items():
        durable_val = str(lection_o.get(field) or "")
        if force or wkey not in st.session_state or (
            durable_val.strip() and not str(st.session_state.get(wkey) or "").strip()
        ):
            st.session_state[wkey] = durable_val
    for side_key, key_map in (
        ("prayer_before", _KEY_OUTLINE_PRAYER_BEFORE),
        ("prayer_after", _KEY_OUTLINE_PRAYER_AFTER),
    ):
        side = outline.get(side_key) if isinstance(outline.get(side_key), dict) else {}
        for field, wkey in key_map.items():
            if field == "selected_lines":
                lines = side.get("selected_lines")
                if isinstance(lines, list):
                    durable_val = "\n".join(
                        str(x).strip() for x in lines if str(x).strip()
                    )
                else:
                    durable_val = str(lines or "")
            else:
                durable_val = str(side.get(field) or "")
            if force or wkey not in st.session_state or (
                durable_val.strip() and not str(st.session_state.get(wkey) or "").strip()
            ):
                st.session_state[wkey] = durable_val
    movements_o = outline.get("movements") if isinstance(outline.get("movements"), list) else []
    if force:
        for key in list(st.session_state.keys()):
            if isinstance(key, str) and key.startswith(_OUTLINE_MV_PREFIX):
                st.session_state.pop(key, None)
    for mv in movements_o:
        if not isinstance(mv, dict):
            continue
        mid = str(mv.get("id") or "")
        if not mid:
            continue
        for field in (
            "title",
            "role_label",
            "textual_basis",
            "core_content",
            "listener_discovery",
            "transition",
            "images",
            "illustrations",
            "applications",
        ):
            wkey = f"{_OUTLINE_MV_PREFIX}{mid}_{field}"
            val = mv.get(field)
            if isinstance(val, list):
                durable_val = "\n".join(
                    str(x).strip() for x in val if str(x).strip()
                )
            else:
                durable_val = str(val or "")
            if force or wkey not in st.session_state or (
                durable_val.strip() and not str(st.session_state.get(wkey) or "").strip()
            ):
                st.session_state[wkey] = durable_val

    # RESET 2B: az egyszerű, lapos "Textus és fókusz" + hétpontos
    # szerkesztőfelület widgetkulcsai — ugyanaz a "force vagy még nincs
    # session_state-ben" minta, mint a fentebbi mezőknél.
    tw = ensure_text_workshop_state(st.session_state)
    if force or _KEY_FLAT_TEXT_MAIN_IDEA not in st.session_state:
        st.session_state[_KEY_FLAT_TEXT_MAIN_IDEA] = tw.get("text_main_idea") or ""

    flat_arc = sw.get("arc") if isinstance(sw.get("arc"), dict) else {}
    for point_key, wkey in _KEY_FLAT_ARC.items():
        if force or wkey not in st.session_state:
            point = flat_arc.get(point_key) or {}
            st.session_state[wkey] = str(point.get("text") or "")

    # RESET 2E-6a: a részletes vázlat szerkesztő-widgetjei (RESET 2E-5)
    # mozgás-KULCS alapján kulcsolódnak (`sw_flat_outline_edit_<key>_
    # <field>`), NEM projekt- vagy session-specifikus azonosítóval. Ha egy
    # MÁSIK projekt megnyitása (`force=True`, ugyanaz a jelző, mint a
    # `_clear_movement_widgets()`-et is kiváltó projektváltás) UGYANAZOKKAL
    # a mozgás-kulcsokkal (pl. mindkettő seven_point) rendelkező kanonikus
    # vázlatot hoz be, a widget-kulcsok VÉLETLENÜL egyeznének — enélkül a
    # purge nélkül a régi projekt kézzel szerkesztett szövege maradna
    # látható és szerkeszthető az új projekt vázlata "helyén" (verifikálva
    # AppTest-tel: a widget a régi projekt szövegét mutatta az új projekt
    # betöltése UTÁN is). A purge kizárólag `force`-nál fut — sima
    # rerunnál (arc-pont szerkesztés stb.) a kézi vázlat-szerkesztés nem
    # veszhet el.
    if force:
        _clear_developed_outline_edit_widgets()


def _request_adopt_sermon_sentence(sentence: str) -> None:
    text = str(sentence or "").strip()
    if section_has_accepted_content(
        st.session_state,
        section_key="sermon_main_idea",
        status_key="sermon_main_idea_status",
        source_section=_SOURCE_SERMON_MAIN,
    ):
        st.session_state[_ADOPT_SERMON_OVERWRITE_CONFIRM] = text
        st.rerun()
        return
    st.session_state[_ADOPT_SERMON_PENDING] = text
    st.rerun()


def _request_adopt_hc_block(block: dict[str, str]) -> None:
    payload = dict(block or {})
    if section_has_accepted_content(
        st.session_state,
        section_key="human_condition",
        status_key="human_condition_status",
        source_section=_SOURCE_HUMAN,
    ):
        st.session_state[_ADOPT_HC_OVERWRITE_CONFIRM] = payload
        st.rerun()
        return
    st.session_state[_ADOPT_HC_PENDING] = payload
    st.rerun()


def _request_adopt_lt_block(block: dict[str, str]) -> None:
    payload = dict(block or {})
    if section_has_accepted_content(
        st.session_state,
        section_key="listener_tension",
        status_key="listener_tension_status",
        source_section=_SOURCE_LISTENER,
    ):
        st.session_state[_ADOPT_LT_OVERWRITE_CONFIRM] = payload
        st.rerun()
        return
    st.session_state[_ADOPT_LT_PENDING] = payload
    st.rerun()


def _request_adopt_ga_block(block: dict[str, str]) -> None:
    payload = dict(block or {})
    if section_has_accepted_content(
        st.session_state,
        section_key="christ_centered_arc",
        status_key="christ_centered_arc_status",
        source_section=_SOURCE_GOSPEL,
    ):
        st.session_state[_ADOPT_GA_OVERWRITE_CONFIRM] = payload
        st.rerun()
        return
    st.session_state[_ADOPT_GA_PENDING] = payload
    st.rerun()


def _request_adopt_path_block(block: dict[str, str]) -> None:
    payload = dict(block or {})
    if section_has_accepted_content(
        st.session_state,
        section_key="sermon_path",
        status_key="sermon_path_status",
        source_section=_SOURCE_PATH,
    ):
        st.session_state[_ADOPT_PATH_OVERWRITE_CONFIRM] = payload
        st.rerun()
        return
    st.session_state[_ADOPT_PATH_PENDING] = payload
    st.rerun()


def _render_overwrite_confirm(
    *,
    confirm_key: str,
    pending_key: str,
    label: str = "A szakaszban már van átvett / jóváhagyott anyag. Felülírod?",
) -> None:
    pending = st.session_state.get(confirm_key)
    if pending is None:
        return
    st.warning(label)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Igen, felülírom", key=f"{confirm_key}_yes", type="primary"):
            st.session_state[pending_key] = pending
            st.session_state.pop(confirm_key, None)
            st.rerun()
    with c2:
        if st.button("Mégse", key=f"{confirm_key}_no"):
            st.session_state.pop(confirm_key, None)
            st.rerun()


def _request_adopt_movements(movements: list[dict[str, str]]) -> None:
    st.session_state[_ADOPT_MOVEMENTS_PENDING] = list(movements or [])
    st.rerun()


def _request_adopt_path_plan(
    *,
    path_block: dict[str, str] | None = None,
    movements: list[dict[str, str]] | None = None,
) -> None:
    if path_block:
        st.session_state[_ADOPT_PATH_PENDING] = dict(path_block)
    if movements is not None:
        st.session_state[_ADOPT_MOVEMENTS_PENDING] = list(movements)
    st.rerun()


def _user_facing_error(result_ok: bool, error_message: str, *, fallback: str) -> str:
    if result_ok:
        return ""
    msg = (error_message or "").strip()
    if not msg:
        return fallback
    if len(msg) > 280:
        return fallback
    lower = msg.casefold()
    if "api key" in lower or "apikey" in lower or "x-goog-api-key" in lower:
        return fallback
    if (
        "unexpected keyword argument" in lower
        or "got an unexpected keyword" in lower
        or "system_instruction" in lower
    ):
        return fallback
    return msg


def _log_lection_developer_error(exact: str, *, tab: str = "Lekciójavaslat") -> None:
    """Pontos kivétel a fejlesztői debug logba; a UI-n ne jelenjen meg."""
    entry = {
        "ts": __import__("datetime").datetime.now().strftime("%H:%M:%S"),
        "tab": tab,
        "attempt": 0,
        "status": "LECTION_UI_ERROR",
        "error": (exact or "")[:2000],
    }
    try:
        log = st.session_state.setdefault("_debug_log", [])
        if isinstance(log, list):
            log.append(entry)
            if len(log) > 200:
                del log[:-200]
    except Exception:
        pass
    try:
        print(f"[lection] {tab}: {exact}", flush=True)
    except Exception:
        pass


def _collect_m4_kwargs(*, sermon_main_idea: str = "") -> dict[str, Any]:
    """Sessionből M4 MI-bemenet; illusztráció / aktualizálás / ének / vázlat nélkül."""
    tw = ensure_text_workshop_state(st.session_state)
    sw = ensure_sermon_workshop_state(st.session_state)
    idea = (sermon_main_idea or "").strip()
    if not idea:
        idea = (sw.get("sermon_main_idea") or "").strip()
    return {
        "passage": _session_str("last_igehely", "igehely_input"),
        "passage_text": _session_passage_text(),
        "occasion": _session_str("last_alkalom", "alkalom_input"),
        "user_focus": _session_str("last_sajat", "sajat_input"),
        "text_main_idea": (tw.get("text_main_idea") or "").strip(),
        "text_main_idea_status": (tw.get("text_main_idea_status") or "").strip(),
        "approved_insights": tw.get("approved_insights") or [],
        "exegesis": _session_str("exegesis"),
        "theology": _session_str("theology"),
        "sermon_main_idea": idea,
    }


def _collect_m5_kwargs() -> dict[str, Any]:
    """Sessionből M5 MI-bemenet (hallgatói kérdés és feszültség)."""
    tw = ensure_text_workshop_state(st.session_state)
    sw = ensure_sermon_workshop_state(st.session_state)
    text_sugs = tw.get("main_idea_suggestions")
    text_expanded = ""
    if isinstance(text_sugs, dict):
        text_expanded = str(text_sugs.get("expanded_summary") or "").strip()
    sermon_sugs = sw.get("sermon_main_idea_suggestions")
    sermon_expanded = ""
    if isinstance(sermon_sugs, dict):
        sermon_expanded = str(sermon_sugs.get("expanded_summary") or "").strip()
    hc = sw.get("human_condition") if isinstance(sw.get("human_condition"), dict) else {}
    return {
        "passage": _session_str("last_igehely", "igehely_input"),
        "passage_text": _session_passage_text(),
        "occasion": _session_str("last_alkalom", "alkalom_input"),
        "user_focus": _session_str("last_sajat", "sajat_input"),
        "text_main_idea": (tw.get("text_main_idea") or "").strip(),
        "text_main_idea_status": (tw.get("text_main_idea_status") or "").strip(),
        "text_expanded_summary": text_expanded,
        "approved_insights": tw.get("approved_insights") or [],
        "sermon_main_idea": (sw.get("sermon_main_idea") or "").strip(),
        "sermon_main_idea_status": (sw.get("sermon_main_idea_status") or "").strip(),
        "sermon_expanded_summary": sermon_expanded,
        "human_condition": dict(hc) if isinstance(hc, dict) else {},
        "exegesis": _session_str("exegesis"),
        "theology": _session_str("theology"),
    }


def _collect_gospel_arc_kwargs() -> dict[str, Any]:
    """Sessionből M5 evangéliumi ív MI-bemenet."""
    base = _collect_m5_kwargs()
    sw = ensure_sermon_workshop_state(st.session_state)
    lt = sw.get("listener_tension") if isinstance(sw.get("listener_tension"), dict) else {}
    # Élő widgetekkel frissített LT (feszültség + feloldás)
    live_lt = {
        "listener_question": (
            st.session_state.get(_KEY_LT["listener_question"])
            or lt.get("listener_question")
            or ""
        ),
        "listener_resistance": (
            st.session_state.get(_KEY_LT["listener_resistance"])
            or lt.get("listener_resistance")
            or ""
        ),
        "sermon_tension": (
            st.session_state.get(_KEY_LT["sermon_tension"])
            or lt.get("sermon_tension")
            or ""
        ),
        "promised_resolution": (
            st.session_state.get(_KEY_GA["promised_resolution"])
            or lt.get("promised_resolution")
            or ""
        ),
    }
    arc = (
        sw.get("christ_centered_arc")
        if isinstance(sw.get("christ_centered_arc"), dict)
        else {}
    )
    live_arc = {
        "divine_gracious_action": (
            st.session_state.get(_KEY_GA["divine_gracious_action"])
            or arc.get("divine_gracious_action")
            or ""
        ),
        "christ_connection": (
            st.session_state.get(_KEY_GA["christ_connection"])
            or arc.get("christ_connection")
            or ""
        ),
        "christ_connection_type": normalize_christ_connection_type(
            st.session_state.get(_KEY_GA["christ_connection_type"])
            or arc.get("christ_connection_type")
            or ""
        ),
        "grace_enabled_response": (
            st.session_state.get(_KEY_GA["grace_enabled_response"])
            or arc.get("grace_enabled_response")
            or ""
        ),
    }
    base["listener_tension"] = live_lt
    base["christ_centered_arc"] = live_arc
    base["bible_translation"] = _session_str("bible_translation") or "RÚF 2014"
    return base


def _collect_sermon_path_kwargs() -> dict[str, Any]:
    """Sessionből M6 igehirdetési út MI-bemenet."""
    base = _collect_gospel_arc_kwargs()
    sw = ensure_sermon_workshop_state(st.session_state)
    path = sw.get("sermon_path") if isinstance(sw.get("sermon_path"), dict) else {}
    live_path = {
        "type": normalize_sermon_path_type(
            st.session_state.get(_KEY_PATH["type"]) or path.get("type") or ""
        ),
        "reason": (
            st.session_state.get(_KEY_PATH["reason"]) or path.get("reason") or ""
        ),
        "starting_point": (
            st.session_state.get(_KEY_PATH["starting_point"])
            or path.get("starting_point")
            or ""
        ),
        "destination": (
            st.session_state.get(_KEY_PATH["destination"])
            or path.get("destination")
            or ""
        ),
    }
    # Ígért feloldás a LT-ben (gospel kwargs már beletette)
    lt = base.get("listener_tension") if isinstance(base.get("listener_tension"), dict) else {}
    if not str(lt.get("promised_resolution") or "").strip():
        # promised_resolution lehet a GA widgetben
        live_lt = dict(lt)
        live_lt["promised_resolution"] = (
            st.session_state.get(_KEY_GA["promised_resolution"]) or ""
        )
        base["listener_tension"] = live_lt
    base["sermon_path"] = live_path
    base["sermon_movements"] = _read_movements_from_widgets() or normalize_sermon_movements(
        sw.get("sermon_movements")
    )
    base["literary_genre"] = _session_str("exegesis")
    return base


def _collect_enrichment_kwargs() -> dict[str, Any]:
    """Sessionből M7 kép/illusztráció/alkalmazás MI-bemenet."""
    base = _collect_sermon_path_kwargs()
    base["selected_images"] = _read_textual_images_from_widgets()
    base["illustrations"] = _read_illustrations_from_widgets()
    base["applications"] = _read_applications_from_widgets()
    base["workshop_illustrations"] = _session_str("illustrations")
    base["workshop_actualization"] = _session_str("actualization")
    return base


def _read_closing_from_widgets() -> dict[str, str]:
    return {
        "type": normalize_closing_type(st.session_state.get(_KEY_CL["type"])),
        "final_discovery": (
            st.session_state.get(_KEY_CL["final_discovery"]) or ""
        ).strip(),
        "hope": (st.session_state.get(_KEY_CL["hope"]) or "").strip(),
        "call_or_response": (
            st.session_state.get(_KEY_CL["call_or_response"]) or ""
        ).strip(),
        "image_or_line": (
            st.session_state.get(_KEY_CL["image_or_line"]) or ""
        ).strip(),
        "open_question": (
            st.session_state.get(_KEY_CL["open_question"]) or ""
        ).strip(),
        "tone": normalize_closing_tone(st.session_state.get(_KEY_CL["tone"])),
    }


def _persist_closing_from_widgets() -> None:
    update_sermon_workshop_section(
        st.session_state, "closing", _read_closing_from_widgets()
    )


def _read_lection_from_widgets() -> dict[str, str]:
    """Widgetek → lekcióblokk; hiányzó widgetkulcsnál a tartós érték marad.

    Így a kapcsolat / funkció / indoklás akkor sem vész el, ha a
    részletes mezők nincsenek a fő felületen (csak összefoglalóban /
    zárt expanderben).
    """
    sw = ensure_sermon_workshop_state(st.session_state)
    durable = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}

    def _pick_str(field: str) -> str:
        wkey = _KEY_LECTION[field]
        if wkey in st.session_state:
            return (st.session_state.get(wkey) or "").strip()
        return str(durable.get(field) or "").strip()

    conn_raw = (
        st.session_state.get(_KEY_LECTION["connection_type"])
        if _KEY_LECTION["connection_type"] in st.session_state
        else durable.get("connection_type")
    )
    text_raw = (
        st.session_state.get(_KEY_LECTION["text"])
        if _KEY_LECTION["text"] in st.session_state
        else durable.get("text")
    )
    test_raw = (
        st.session_state.get(_KEY_LECTION["testament_preference"])
        if _KEY_LECTION["testament_preference"] in st.session_state
        else durable.get("testament_preference")
    )
    len_raw = (
        st.session_state.get(_KEY_LECTION["length_preference"])
        if _KEY_LECTION["length_preference"] in st.session_state
        else durable.get("length_preference")
    )
    return {
        "reference": _pick_str("reference"),
        "connection_type": (
            normalize_lection_connection_type(conn_raw)
            if str(conn_raw or "").strip()
            else ""
        ),
        "function": _pick_str("function"),
        "rationale": _pick_str("rationale"),
        "text": normalize_passage_text(text_raw),
        "notes": _pick_str("notes"),
        "testament_preference": normalize_lection_testament_preference(test_raw),
        "length_preference": normalize_lection_length_preference(len_raw),
        "user_focus": _pick_str("user_focus"),
    }


def _persist_lection_from_widgets(*, include_text: bool = True) -> None:
    """Lekció mezők mentése; opcionálisan a szövegmező kihagyásával."""
    sw = ensure_sermon_workshop_state(st.session_state)
    current = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    block = _read_lection_from_widgets()
    if not include_text:
        block["text"] = str(current.get("text") or "")
        for meta in (
            "text_source",
            "text_source_url",
            "text_fetched_at",
            "text_fetched_reference",
        ):
            block[meta] = str(current.get(meta) or "")
    else:
        for meta in (
            "text_source",
            "text_source_url",
            "text_fetched_at",
            "text_fetched_reference",
        ):
            block[meta] = str(current.get(meta) or "")
    update_sermon_workshop_section(st.session_state, "lection", block)


def _apply_lection_assessment_to_fields(result: LectionAssessmentResult) -> None:
    """Értékelés → háttér mezők (kapcsolat, funkció, indoklás), ha van javaslat."""
    sw = ensure_sermon_workshop_state(st.session_state)
    current = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    block = dict(current)

    conn = normalize_lection_connection_type(result.suggested_connection_type)
    if conn:
        block["connection_type"] = conn
        st.session_state[_KEY_LECTION["connection_type"]] = conn

    rationale = str(result.revised_rationale or "").strip()
    if rationale:
        block["rationale"] = rationale
        st.session_state[_KEY_LECTION["rationale"]] = rationale

    function = str(result.liturgical_fit_assessment or "").strip()
    if function:
        block["function"] = function
        st.session_state[_KEY_LECTION["function"]] = function

    update_sermon_workshop_section(st.session_state, "lection", block)


def _lines_from_widget(raw: Any) -> list[str]:
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def _read_prayer_side_from_widgets(key_map: dict[str, str]) -> dict[str, Any]:
    return {
        "own_thoughts": (st.session_state.get(key_map["own_thoughts"]) or "").strip(),
        "purpose": (st.session_state.get(key_map["purpose"]) or "").strip(),
        "movement_notes": (
            st.session_state.get(key_map["movement_notes"]) or ""
        ).strip(),
        "selected_opening": (
            st.session_state.get(key_map["selected_opening"]) or ""
        ).strip(),
        "selected_lines": _lines_from_widget(
            st.session_state.get(key_map["selected_lines"])
        ),
        "closing_direction": (
            st.session_state.get(key_map["closing_direction"]) or ""
        ).strip(),
    }


def _read_prayer_from_widgets() -> dict[str, Any]:
    sw = ensure_sermon_workshop_state(st.session_state)
    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    before = _read_prayer_side_from_widgets(_KEY_PRAYER_BEFORE)
    after = _read_prayer_side_from_widgets(_KEY_PRAYER_AFTER)
    before["status"] = str(
        (prep.get("before") or {}).get("status")
        if isinstance(prep.get("before"), dict)
        else "draft"
    ) or "draft"
    after["status"] = str(
        (prep.get("after") or {}).get("status")
        if isinstance(prep.get("after"), dict)
        else "draft"
    ) or "draft"
    return {
        "tone_preference": normalize_prayer_tone_preference(
            st.session_state.get(_KEY_PRAYER_COMMON["tone_preference"])
        ),
        "general_focus": (
            st.session_state.get(_KEY_PRAYER_COMMON["general_focus"]) or ""
        ).strip(),
        "rewrite_mode": normalize_prayer_rewrite_mode(
            st.session_state.get(_KEY_PRAYER_COMMON["rewrite_mode"])
        ),
        "before": before,
        "after": after,
        "before_suggestions": prep.get("before_suggestions"),
        "after_suggestions": prep.get("after_suggestions"),
        "assessment": prep.get("assessment"),
        "status": str(prep.get("status") or "draft"),
        "last_generated_at": str(prep.get("last_generated_at") or ""),
    }


def _persist_prayer_from_widgets() -> None:
    update_sermon_workshop_section(
        st.session_state, "prayer_preparation", _read_prayer_from_widgets()
    )


def _collect_closing_kwargs() -> dict[str, Any]:
    """Sessionből M7 lezárás MI-bemenet (M6 + M7 + élő lezárás widgetek)."""
    base = _collect_enrichment_kwargs()
    base["closing"] = _read_closing_from_widgets()
    return base


def _read_self_review_from_widgets() -> dict[str, str]:
    return {
        field: (st.session_state.get(wkey) or "").strip()
        for field, wkey in _KEY_DIAG.items()
    }


def _persist_self_review_from_widgets() -> None:
    block = _read_self_review_from_widgets()
    for field, value in block.items():
        update_sermon_workshop_section(st.session_state, field, value)


def _outline_mv_widget_key(mid: str, field: str) -> str:
    return f"{_OUTLINE_MV_PREFIX}{mid}_{field}"


def _outline_widget_str(
    wkey: str,
    durable: Any,
    *,
    protect_nonempty: bool,
) -> str | None:
    """Widget érték; None = ne írjuk felül a tartós mezőt.

    protect_nonempty=True esetén az üres/stale widget nem törli a kitöltött
    tartós tartalmat (jóváhagyás / flush útvonal).
    """
    if wkey not in st.session_state:
        return None
    widget_val = (st.session_state.get(wkey) or "").strip()
    durable_val = str(durable or "").strip()
    if protect_nonempty and not widget_val and durable_val:
        return None
    return widget_val


def _read_outline_from_widgets(*, protect_nonempty: bool = False) -> dict[str, Any]:
    sw = ensure_sermon_workshop_state(st.session_state)
    base = normalize_sermon_outline(sw.get("sermon_outline"))
    out = dict(base)
    for field, wkey in _KEY_OUTLINE.items():
        picked = _outline_widget_str(
            wkey, out.get(field), protect_nonempty=protect_nonempty
        )
        if picked is not None:
            out[field] = picked
    closing = dict(out.get("closing") or {})
    for field, wkey in _KEY_OUTLINE_CLOSING.items():
        picked = _outline_widget_str(
            wkey, closing.get(field), protect_nonempty=protect_nonempty
        )
        if picked is not None:
            closing[field] = picked
    out["closing"] = closing
    lection = dict(out.get("lection") or {})
    for field, wkey in _KEY_OUTLINE_LECTION.items():
        picked = _outline_widget_str(
            wkey, lection.get(field), protect_nonempty=protect_nonempty
        )
        if picked is not None:
            lection[field] = picked
    out["lection"] = lection
    out["lection_reference"] = str(lection.get("reference") or "")
    for side_key, key_map in (
        ("prayer_before", _KEY_OUTLINE_PRAYER_BEFORE),
        ("prayer_after", _KEY_OUTLINE_PRAYER_AFTER),
    ):
        side = dict(out.get(side_key) or {})
        for field, wkey in key_map.items():
            if wkey not in st.session_state:
                continue
            raw = st.session_state.get(wkey) or ""
            if field == "selected_lines":
                lines = [
                    line.strip()
                    for line in str(raw).splitlines()
                    if line.strip()
                ]
                durable_lines = side.get("selected_lines")
                if (
                    protect_nonempty
                    and not lines
                    and isinstance(durable_lines, list)
                    and any(str(x).strip() for x in durable_lines)
                ):
                    continue
                side[field] = lines
            else:
                picked = _outline_widget_str(
                    wkey, side.get(field), protect_nonempty=protect_nonempty
                )
                if picked is not None:
                    side[field] = picked
        out[side_key] = side
    movements: list[dict[str, Any]] = []
    for mv in out.get("movements") or []:
        if not isinstance(mv, dict):
            continue
        mid = str(mv.get("id") or "")
        item = dict(mv)
        if mid:
            for field in (
                "title",
                "role_label",
                "textual_basis",
                "core_content",
                "listener_discovery",
                "transition",
            ):
                wkey = _outline_mv_widget_key(mid, field)
                picked = _outline_widget_str(
                    wkey, item.get(field), protect_nonempty=protect_nonempty
                )
                if picked is not None:
                    item[field] = picked
            for field in ("images", "illustrations", "applications"):
                wkey = _outline_mv_widget_key(mid, field)
                if wkey not in st.session_state:
                    continue
                lines = [
                    line.strip()
                    for line in str(st.session_state.get(wkey) or "").splitlines()
                    if line.strip()
                ]
                durable_list = item.get(field)
                if (
                    protect_nonempty
                    and not lines
                    and isinstance(durable_list, list)
                    and any(str(x).strip() for x in durable_list)
                ):
                    continue
                item[field] = lines
        movements.append(item)
    out["movements"] = movements
    return normalize_sermon_outline(out)


def _persist_outline_from_widgets(*, mark_manual_edit: bool | None = True) -> None:
    """Widget → vázlat. mark_manual_edit=None: csak ha a szerkeszthető tartalom változott.

    flush/jóváhagyás (mark_manual_edit is not True): üres stale widgetek
    nem törlik a tartós vázlatszöveget.
    """
    sw = ensure_sermon_workshop_state(st.session_state)
    protect = mark_manual_edit is not True
    outline = _read_outline_from_widgets(protect_nonempty=protect)
    content_wkey = _KEY_OUTLINE.get("content")
    if content_wkey and content_wkey in st.session_state:
        widget_content = str(st.session_state.get(content_wkey) or "").strip()
        durable_content = str(outline.get("content") or "").strip()
        if protect and not widget_content and durable_content:
            outline["content"] = durable_content
        elif widget_content:
            outline["content"] = widget_content
        elif outline_has_content(outline) and not durable_content:
            outline = sync_outline_content(outline, force=True)
    elif outline_has_content(outline) and not str(outline.get("content") or "").strip():
        outline = sync_outline_content(outline, force=True)
    if mark_manual_edit is None:
        before = editable_outline_snapshot(sw.get("sermon_outline"))
        after = editable_outline_snapshot(outline)
        mark_manual_edit = before != after
    save_sermon_outline(
        st.session_state,
        outline,
        stamp_generated_at=False,
        mark_manual_edit=bool(mark_manual_edit),
    )


def _resolve_canonical_outline_for_diagnostics() -> dict[str, Any]:
    """Kanonikus vázlat a diagnosztikához — ugyanaz a szöveg, mint a főnézetben.

    Prioritás:
    1. aktuális szerkesztett tartalom (widget, ha van);
    2. `sermon_outline.content` / struktúrából szinkronizált kanonikus szöveg;
    3. a tartós vázlat (draft vagy approved — státusz nem számít).
    """
    sw = ensure_sermon_workshop_state(st.session_state)
    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    content_wkey = _KEY_OUTLINE.get("content")
    if content_wkey and content_wkey in st.session_state:
        widget_content = str(st.session_state.get(content_wkey) or "").strip()
        if widget_content:
            outline = dict(outline)
            outline["content"] = widget_content
    outline = sync_outline_content(outline, force=False)
    if not str(outline.get("content") or "").strip():
        outline = dict(outline)
        outline["content"] = outline_canonical_text(outline)
    return normalize_sermon_outline(outline)


def _collect_outline_diagnostics_kwargs() -> dict[str, Any]:
    base = _collect_closing_kwargs()
    outline = _resolve_canonical_outline_for_diagnostics()
    base["sermon_outline"] = outline
    base["outline_text"] = outline_canonical_text(outline)
    return base


def _outline_diagnostics_payload(result: OutlineDiagnosticsResult) -> dict[str, Any]:
    return result.to_dict()


def _format_diag_user_error(reason: str) -> str:
    text = str(reason or "").strip()
    if not text:
        text = "ismeretlen hiba"
    if text.startswith("A diagnosztika most nem készült el:"):
        return text
    return (
        f"A diagnosztika most nem készült el: {text}. "
        "A vázlat változatlanul megmaradt, próbáld újra."
    )


def _run_outline_homiletical_diagnostics(
    *,
    generate_fn: GenerateFn | None,
    prefer_local_heuristic: bool = False,
) -> None:
    outline = _resolve_canonical_outline_for_diagnostics()
    if not outline_has_content(outline):
        set_sermon_outline_diagnostics_status(st.session_state, "idle")
        st.session_state["_sw_outline_diag_running"] = False
        st.warning("Előbb készíts igehirdetési vázlatot.")
        return

    set_sermon_outline_diagnostics_status(st.session_state, "running")
    st.session_state["_sw_outline_diag_running"] = True
    sw = ensure_sermon_workshop_state(st.session_state)
    # Snapshot — diagnosztika nem módosíthatja a vázlatot / korábbi eredményt törölve.
    outline_before = dict(outline)
    main_idea_before = str(sw.get("sermon_main_idea") or "")
    previous_diag = (
        dict(sw.get("sermon_outline_diagnostics"))
        if isinstance(sw.get("sermon_outline_diagnostics"), dict)
        else {}
    )
    previous_generated = str(sw.get("sermon_outline_diagnostics_generated_at") or "")
    outline_updated = str(
        sw.get("sermon_outline_updated_at") or outline.get("updated_at") or ""
    )

    try:
        with st.spinner("A vázlat homiletikai elemzése folyamatban…"):
            kwargs = _collect_outline_diagnostics_kwargs()
            kwargs["sermon_outline"] = outline
            result = run_outline_diagnostics(
                **kwargs,
                generate_fn=None if prefer_local_heuristic else generate_fn,
                prefer_local_heuristic=prefer_local_heuristic,
            )

        sw_after = ensure_sermon_workshop_state(st.session_state)
        sw_after["sermon_outline"] = normalize_sermon_outline(outline_before)
        sw_after["sermon_main_idea"] = main_idea_before
        # Sikertelen frissítés soha ne törölje a korábbi diagnózist.
        if _diagnostics_has_result(previous_diag) and not _diagnostics_has_result(
            sw_after.get("sermon_outline_diagnostics")
        ):
            sw_after["sermon_outline_diagnostics"] = previous_diag
            sw_after["sermon_outline_diagnostics_generated_at"] = previous_generated

        if result.missing_outline:
            set_sermon_outline_diagnostics_status(
                st.session_state,
                "idle",
            )
            st.warning(
                result.error_message or "Előbb készíts igehirdetési vázlatot."
            )
            return

        if not result.ok:
            tech = ""
            for w in result.warnings or []:
                if str(w).startswith("Generálási hiba:"):
                    tech = str(w)
                    break
            if tech:
                import logging

                logging.getLogger("textus.diagnostics").error("%s", tech)
            err = _format_diag_user_error(
                result.error_message or "a modell válasza nem volt használható"
            )
            set_sermon_outline_diagnostics_status(
                st.session_state, "error", error_message=err
            )
            # Korábbi eredmény megmarad; csak a hibát jelezzük tartósan.
            if _diagnostics_has_result(previous_diag):
                sw_after = ensure_sermon_workshop_state(st.session_state)
                sw_after["sermon_outline_diagnostics"] = previous_diag
                sw_after["sermon_outline_diagnostics_generated_at"] = previous_generated
            return

        payload = _outline_diagnostics_payload(result)
        payload["outline_updated_at_at_diagnosis"] = outline_updated
        mode = str(result.mode or "ai")
        has_areas = any(
            isinstance(a, dict)
            and str(a.get("status") or "") != "not_enough_information"
            for a in (result.diagnostic_areas or [])
        )
        has_text = bool(result.overview or result.strengths or result.refinements)
        if mode == "ai" and not (has_areas or has_text):
            err = _format_diag_user_error("a diagnosztikai válasz üres volt")
            set_sermon_outline_diagnostics_status(
                st.session_state, "error", error_message=err
            )
            if _diagnostics_has_result(previous_diag):
                sw_after = ensure_sermon_workshop_state(st.session_state)
                sw_after["sermon_outline_diagnostics"] = previous_diag
                sw_after["sermon_outline_diagnostics_generated_at"] = previous_generated
            return

        save_sermon_outline_diagnostics(st.session_state, payload)
        set_sermon_outline_diagnostics_status(st.session_state, "ready")
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("textus.diagnostics").exception(
            "outline diagnostics failed: %s", exc
        )
        err = _format_diag_user_error(str(exc) or "váratlan hiba")
        set_sermon_outline_diagnostics_status(
            st.session_state, "error", error_message=err
        )
        if _diagnostics_has_result(previous_diag):
            sw_after = ensure_sermon_workshop_state(st.session_state)
            sw_after["sermon_outline_diagnostics"] = previous_diag
            sw_after["sermon_outline_diagnostics_generated_at"] = previous_generated
    finally:
        st.session_state["_sw_outline_diag_running"] = False
        sw_final = ensure_sermon_workshop_state(st.session_state)
        if sw_final.get("sermon_outline_diagnostics_status") == "running":
            set_sermon_outline_diagnostics_status(st.session_state, "idle")


def _run_homiletical_diagnostics(*, generate_fn: GenerateFn | None) -> None:
    """Kompatibilitási alias — a fő folyamat a vázlatdiagnosztika."""
    _run_outline_homiletical_diagnostics(generate_fn=generate_fn)


def _assemble_and_diagnose(*, generate_fn: GenerateFn | None) -> None:
    """1) anyaggyűjtés → 2) vázlat → 3) mentés → 4) diagnosztika."""
    _assemble_and_save_outline(generate_fn=generate_fn, force_overwrite=False)
    outline = _resolve_canonical_outline_for_diagnostics()
    if outline_has_content(outline):
        _run_outline_homiletical_diagnostics(generate_fn=generate_fn)


def _diagnostics_payload(result: HomileticalDiagnosticsResult) -> dict[str, Any]:
    return result.to_dict()


def _collect_diagnostics_kwargs() -> dict[str, Any]:
    """Sessionből M8 diagnosztika MI-bemenet (M4–M7 + lezárás + önellenőrzés)."""
    base = _collect_closing_kwargs()
    review = _read_self_review_from_widgets()
    base.update(review)
    return base


def _regenerate_outline_part_and_save(
    *,
    part: str,
    generate_fn: GenerateFn | None,
    movement_id: str = "",
) -> None:
    """Részleges újraírás — a többi vázlatrész érintetlen."""
    from sermon_workshop_outline_synth_ai import regenerate_outline_part

    if generate_fn is None:
        st.warning("A részleges újraíráshoz AI-generálás szükséges.")
        return
    sw = ensure_sermon_workshop_state(st.session_state)
    current = normalize_sermon_outline(sw.get("sermon_outline"))
    bundle = collect_available_sermon_material(st.session_state, sermon_workshop=sw)
    with st.spinner("Rész újragondolása…"):
        updated, warnings = regenerate_outline_part(
            current,
            bundle,
            part=part,
            movement_id=movement_id,
            generate_fn=generate_fn,
        )
    updated = sync_outline_content(updated, force=True)
    save_sermon_outline(
        st.session_state,
        updated,
        stamp_generated_at=False,
        mark_manual_edit=False,
    )
    st.session_state[_RESYNC_FLAG] = True
    for w in warnings:
        st.caption(w)
    st.success("A kiválasztott rész frissült.")
    st.rerun()


def _render_outline_partial_regen(
    outline: dict[str, Any],
    *,
    generate_fn: GenerateFn | None,
) -> None:
    """Részleges újragenerálás — nem írja felül a kézi megjegyzéseket."""
    with st.expander("Rész újragondolása", expanded=False):
        st.caption(
            "Csak a kiválasztott részt írja újra; a többi vázlatelem és a "
            "saját megjegyzések megmaradnak."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Bevezetés", key="sw_outline_regen_opening"):
                _regenerate_outline_part_and_save(
                    part="introduction", generate_fn=generate_fn
                )
            if st.button("Alkalmazási irány", key="sw_outline_regen_apps"):
                _regenerate_outline_part_and_save(
                    part="applications", generate_fn=generate_fn
                )
        with c2:
            if st.button("Megérkezés", key="sw_outline_regen_closing"):
                _regenerate_outline_part_and_save(
                    part="conclusion", generate_fn=generate_fn
                )
        with c3:
            mvs = [
                m
                for m in (outline.get("movements") or [])
                if isinstance(m, dict) and str(m.get("id") or "").strip()
            ]
            if mvs:
                labels = {
                    str(m.get("id")): f"{i}. {m.get('title') or 'mozgás'}"
                    for i, m in enumerate(mvs, start=1)
                }
                choice = st.selectbox(
                    "Mozgás",
                    options=list(labels.keys()),
                    format_func=lambda k: labels.get(k, k),
                    key="sw_outline_regen_mv_select",
                )
                if st.button("Kiválasztott mozgás", key="sw_outline_regen_mv"):
                    _regenerate_outline_part_and_save(
                        part="movement",
                        movement_id=str(choice or ""),
                        generate_fn=generate_fn,
                    )


def _assemble_and_save_outline(
    *,
    generate_fn: GenerateFn | None,
    force_overwrite: bool,
) -> None:
    with st.spinner("Igehirdetési vázlat összeállítása…"):
        result = assemble_sermon_outline(
            st.session_state,
            generate_fn=generate_fn,
            force_overwrite=force_overwrite,
            polish=False,
            mode="workshop",
        )
        if not result.ok:
            st.warning(result.error_message or "A vázlat összeállítása nem sikerült.")
            st.session_state[_CONFIRM_OUTLINE_OVERWRITE] = True
            return
        outline = sync_outline_content(result.outline, force=True)
        if not outline_has_content(outline):
            st.error(
                "Nem jött létre olvasható vázlattartalom — nincs sikerüzenet. "
                + EMPTY_PROJECT_MESSAGE
            )
            return
        save_sermon_outline(st.session_state, outline, mark_manual_edit=False)
        sw = ensure_sermon_workshop_state(st.session_state)
        sw["sermon_outline_status"] = "draft"
        outline["status"] = "draft"
        outline["needs_rebuild"] = False
        sw["sermon_outline"] = outline
        st.session_state[_CONFIRM_OUTLINE_OVERWRITE] = False
        st.session_state[_RESYNC_FLAG] = True
        # A st.rerun() eldobná a közvetlenül előtte kiírt st.caption/st.success
        # elemeket — a "flash" mintát követve (ld. _sw_prayer_flash_*) a
        # session_state-en át visszük át a következő renderre.
        if result.warnings:
            st.session_state[_OUTLINE_ASSEMBLY_FLASH_WARNINGS] = list(result.warnings)
        st.session_state[_OUTLINE_ASSEMBLY_FLASH_SUCCESS] = "A vázlat elkészült."
        st.rerun()


def _diag_view_model_simplified(diag: dict[str, Any]) -> dict[str, Any]:
    """Egyszerűsített diagnosztikai nézet — vázlatdiagnosztika vagy M8 adapter."""
    if not isinstance(diag, dict) or not diag:
        return {
            "overview": "",
            "strengths": [],
            "refinements": [],
            "ready_to_use": False,
            "next_step": "",
            "detailed_notes": [],
            "warnings": [],
        }
    # Új séma
    if "overview" in diag or "refinements" in diag or "strengths" in diag:
        return {
            "overview": str(diag.get("overview") or "").strip(),
            "strengths": [
                str(x).strip() for x in (diag.get("strengths") or []) if str(x).strip()
            ][:MAX_STRENGTHS],
            "refinements": list(diag.get("refinements") or [])[:MAX_REFINEMENTS],
            "ready_to_use": bool(diag.get("ready_to_use")),
            "next_step": str(diag.get("next_step") or "").strip(),
            "detailed_notes": [
                str(x).strip()
                for x in (diag.get("detailed_notes") or [])
                if str(x).strip()
            ],
            "warnings": [
                str(x).strip() for x in (diag.get("warnings") or []) if str(x).strip()
            ],
        }
    # Régi M8 séma a diagnostics.result alatt
    adapted = adapt_m8_to_outline_diagnostics(diag)
    return adapted.to_dict()


_DIAG_STATUS_COLORS: dict[str, str] = {
    "strong": "#4a7c74",
    "stable": "#5a6f8a",
    "needs_attention": "#c4923a",
    "critical_gap": "#a65d48",
    "not_enough_information": "#8a8580",
}

# Pastor-friendly UI labels (schema keys unchanged).
_DIAG_STATUS_SOFT_LABELS: dict[str, str] = {
    "strong": "Kirajzolódik",
    "stable": "Alakul",
    "needs_attention": "Figyelmet kér",
    "critical_gap": "Figyelmet kér",
    "not_enough_information": "Még nincs elég adat",
}

# 6 szegmenses homiletikai térkép — meglévő diagnostic_areas kulcsokból.
_DIAG_WORK_MAP_SEGMENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "text_fidelity",
        "label": "Textushűség",
        "keys": ("text_fidelity", "theological_accuracy"),
    },
    {
        "id": "main_idea",
        "label": "Fő gondolat",
        "keys": ("unity_and_focus",),
    },
    {
        "id": "sermon_arc",
        "label": "Igehirdetési ív",
        "keys": ("sermon_path", "hearability"),
    },
    {
        "id": "christ",
        "label": "Krisztus-központúság",
        "keys": ("christ_centeredness",),
    },
    {
        "id": "listener",
        "label": "Hallgatói megszólítás",
        "keys": ("listener_tension",),
    },
    {
        "id": "arrival",
        "label": "Megérkezés",
        "keys": ("closing", "application"),
    },
)

# Státusz → minőségi szegmensállapot (nincs pontszám).
_DIAG_STATUS_TO_STATE: dict[str, str] = {
    "strong": "emerged",
    "stable": "forming",
    "needs_attention": "attention",
    "critical_gap": "attention",
    "not_enough_information": "unknown",
}

# Rosszabb → jobb (aggregáláskor a legrosszabb értékelt státusz nyer).
_DIAG_STATUS_SEVERITY: dict[str, int] = {
    "critical_gap": 0,
    "needs_attention": 1,
    "stable": 2,
    "strong": 3,
    "not_enough_information": 9,
}

_DIAG_DETAIL_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "title": "Bibliai és teológiai alap",
        "keys": (
            "text_fidelity",
            "theological_accuracy",
            "christ_centeredness",
        ),
    },
    {
        "title": "Az igehirdetés íve",
        "keys": (
            "unity_and_focus",
            "listener_tension",
            "sermon_path",
            "closing",
        ),
    },
    {
        "title": "Hallhatóság és megvalósítás",
        "keys": (
            "hearability",
            "images_and_illustrations",
            "application",
        ),
    },
    {
        "title": "Pásztori hang és felelősség",
        "keys": (
            "pastoral_responsibility",
            "voice_and_originality",
        ),
    },
)

# Keep alias for older imports/tests.
_DIAG_MAP_GROUPS = _DIAG_DETAIL_GROUPS

_DIAG_SOFT_PHRASES: tuple[tuple[str, str], ...] = (
    ("kritikus hiányosságot mutat", "finomítást igényel"),
    ("kritikus hiányosság", "javítandó pont"),
    ("koherenciája jelenleg alacsony", "összhangja még gyenge"),
    ("koherencia jelenleg alacsony", "összhang még gyenge"),
    ("integritási probléma", "összefüggésbeli hiány"),
    ("lényeges hiányosságot", "javítandó pontot"),
    ("lényeges hiányosság", "javítandó pont"),
    ("lényeges hiány", "javítandó pont"),
)

_DIAG_STYLES_FLAG = "_sw_diag_ui_styles"


def _ensure_diag_styles() -> None:
    # 2026-11-23: minden futásban kirajzoljuk. A korábbi _DIAG_STYLES_FLAG-es
    # egyszeri injektálás után a Streamlit a következő futás végén eltávolította
    # a <style> elemet, így a diagnosztikai chipek stílusa elveszett. A flag
    # konstans csak a régi sessionök értelmezhetősége miatt maradt meg.
    st.markdown(
        """
<style>
.sw-diag-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border-radius: 999px;
  padding: 0.2rem 0.65rem;
  font-size: 0.82rem;
  font-weight: 600;
  border: 1px solid transparent;
  line-height: 1.3;
}
.sw-diag-chip .dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  flex: 0 0 auto;
}
.sw-diag-chip-strong { background: rgba(74,124,116,0.14); color: #2f5a54; border-color: rgba(74,124,116,0.28); }
.sw-diag-chip-stable { background: rgba(90,111,138,0.14); color: #3a4b63; border-color: rgba(90,111,138,0.28); }
.sw-diag-chip-needs_attention { background: rgba(196,146,58,0.16); color: #7a5620; border-color: rgba(196,146,58,0.34); }
.sw-diag-chip-critical_gap { background: rgba(166,93,72,0.14); color: #7a3d2f; border-color: rgba(166,93,72,0.30); }
.sw-diag-chip-not_enough_information { background: rgba(138,133,128,0.16); color: #5a5652; border-color: rgba(138,133,128,0.30); }
.sw-diag-count-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0.35rem 0 0.85rem 0;
}
@media (max-width: 900px) {
  .sw-diag-count-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
  .sw-diag-count-grid { grid-template-columns: 1fr; }
}
.sw-diag-count-card {
  border-radius: 12px;
  padding: 0.6rem 0.65rem;
  background: rgba(248, 245, 238, 0.92);
  border: 1px solid rgba(93, 72, 48, 0.12);
  min-width: 0;
}
.sw-diag-count-card .n {
  font-size: 1.3rem;
  font-weight: 700;
  color: #2b2116;
  line-height: 1.1;
}
.sw-diag-count-card .lbl {
  font-size: 0.78rem;
  color: #6b5a48;
  margin-top: 0.12rem;
  line-height: 1.25;
}
.sw-diag-prio-card {
  border-radius: 12px;
  padding: 0.75rem 0.85rem;
  margin-bottom: 0.5rem;
  background: rgba(255, 248, 238, 0.92);
  border: 1px solid rgba(196,146,58,0.28);
  border-left: 4px solid #c4923a;
}
.sw-diag-prio-card h5 {
  margin: 0 0 0.3rem 0;
  color: #2b2116;
  font-size: 0.96rem;
}
.sw-diag-prio-card p {
  margin: 0 0 0.3rem 0;
  color: #4a3e32;
  font-size: 0.88rem;
  line-height: 1.4;
}
.sw-diag-prio-card .meta {
  font-size: 0.8rem;
  color: #6b5a48;
}
.sw-diag-area-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.3rem 0.5rem;
  padding: 0.22rem 0;
  border-top: 1px solid rgba(93, 72, 48, 0.08);
}
.sw-diag-area-row:first-of-type { border-top: none; }
.sw-diag-area-name {
  color: #3d3228;
  font-size: 0.86rem;
  min-width: 0;
  flex: 1 1 auto;
}
.sw-diag-group-block {
  margin: 0.35rem 0 0.75rem 0;
  padding: 0.55rem 0.7rem;
  border-radius: 10px;
  background: rgba(255, 252, 247, 0.75);
  border: 1px solid rgba(93, 72, 48, 0.10);
}
.sw-diag-group-block h5 {
  margin: 0 0 0.25rem 0;
  color: #2b2116;
  font-size: 0.9rem;
}
/* ===== Diagnosztikai dashboard: KPI-kártyák ===== */
.tx-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.6rem;
  margin: 0.2rem 0 1rem 0;
}
@media (max-width: 900px) { .tx-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 520px) { .tx-kpi-grid { grid-template-columns: 1fr; } }
.tx-kpi-card {
  border-radius: 12px;
  padding: 0.7rem 0.8rem;
  background: linear-gradient(165deg, rgba(255,252,247,0.92), rgba(240,232,218,0.6));
  border: 1px solid rgba(170,145,112,0.28);
  border-top: 3px solid #5a7aa8;
  box-shadow: 0 1px 0 rgba(255,255,255,0.6) inset;
  min-width: 0;
}
.tx-kpi-card .k-lbl {
  font-family: "Inter","Segoe UI",sans-serif;
  font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em;
  text-transform: uppercase; color: #8a6a3f; margin-bottom: 0.25rem;
}
.tx-kpi-card .k-val {
  font-family: "Inter","Segoe UI",sans-serif;
  font-size: 1.02rem; font-weight: 650; color: #1f334d; line-height: 1.25;
}
/* ===== Homiletikai profil — vízszintes státuszsávok (fallback / natív) ===== */
.tx-profile { margin: 0.2rem 0 0.4rem; }
.tx-profile-row { margin: 0.4rem 0; }
.tx-profile-head {
  display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem;
  font-family: "Inter","Segoe UI",sans-serif;
}
.tx-profile-name { font-size: 0.9rem; color: #3d3228; font-weight: 550; }
.tx-profile-status { font-size: 0.8rem; color: #6b5a48; }
.tx-profile-track {
  height: 8px; width: 100%; background: rgba(160,140,115,0.18);
  border-radius: 999px; margin-top: 0.25rem; overflow: hidden;
}
.tx-profile-fill { height: 100%; border-radius: 999px; transition: width 0.3s ease; }
/* Dashboard fejlesztési fókusz kártyák (kék hangsúly, elkülönítve) */
.tx-diag-prio-card {
  border-radius: 12px;
  padding: 0.7rem 0.8rem;
  margin-bottom: 0.5rem;
  background: rgba(244, 247, 251, 0.94);
  border: 1px solid rgba(90,122,168,0.28);
  border-left: 4px solid #5a7aa8;
}
.tx-diag-prio-card h5 { margin: 0 0 0.3rem 0; color: #1f334d; font-size: 0.95rem; }
.tx-diag-prio-card p { margin: 0 0 0.3rem 0; color: #3a4b63; font-size: 0.86rem; line-height: 1.4; }
.tx-diag-prio-card .meta { font-size: 0.8rem; color: #5a6b82; }
/* Elsődleges fejlesztési prioritás kiemelése */
.sw-diag-prio-card.-primary {
  border-color: rgba(196,146,58,0.42);
  border-left-width: 5px;
  box-shadow: 0 4px 12px rgba(120, 90, 40, 0.10);
}
/* Részletes homiletikai profil — kompakt sorok */
.tx-arealist { margin: 0.15rem 0 0.6rem; }
.tx-arow {
  padding: 0.42rem 0;
  border-top: 1px solid rgba(93, 72, 48, 0.09);
}
.tx-arow:first-child { border-top: none; }
.tx-arow-head {
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 0.6rem; font-family: "Inter","Segoe UI",sans-serif;
}
.tx-arow-name { font-size: 0.9rem; color: #3d3228; font-weight: 550; }
.tx-arow-val { font-size: 0.8rem; color: #6b5a48; white-space: nowrap; }
.tx-arow-track {
  height: 7px; width: 100%; background: rgba(160,140,115,0.18);
  border-radius: 999px; margin-top: 0.28rem; overflow: hidden;
}
.tx-arow-fill { height: 100%; border-radius: 999px; transition: width 0.55s ease; }
.tx-arow.-empty .tx-arow-track {
  background: transparent;
  border: 1px dashed rgba(138,133,128,0.5);
  height: 7px;
}
.tx-arow.-empty .tx-arow-name { color: #7a746c; }
.tx-arow-expl {
  font-size: 0.8rem; color: #6b5a48; line-height: 1.4; margin-top: 0.2rem;
}
@media (prefers-reduced-motion: reduce) {
  .tx-arow-fill { transition: none !important; }
}
/* Kompakt diagnosztikai munkatérkép — kiegészítő chip/státusz */
.sw-diag-chip-strong { background: rgba(90,122,168,0.14); color: #3a5478; border-color: rgba(90,122,168,0.28); }
.sw-diag-chip-stable { background: rgba(196,160,106,0.16); color: #7a5620; border-color: rgba(196,160,106,0.34); }
.sw-diag-howto {
  font-size: 0.86rem; color: #4a3e32; line-height: 1.45; margin: 0.2rem 0;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _diag_areas_index(areas: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(areas, list):
        return out
    for area in areas:
        if not isinstance(area, dict):
            continue
        key = str(area.get("key") or "").strip()
        if key:
            out[key] = area
    return out


def _diag_shorten(text: str, *, limit: int = 320) -> str:
    raw = " ".join(str(text or "").split())
    if len(raw) <= limit:
        return raw
    cut = raw[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:")
    return (cut or raw[: limit - 1]) + "…"


def _diag_soften_text(text: str) -> str:
    """UI-only wording softener; does not alter stored JSON."""
    out = str(text or "")
    lower = out.casefold()
    for harsh, soft in _DIAG_SOFT_PHRASES:
        idx = lower.find(harsh.casefold())
        if idx < 0:
            continue
        out = out[:idx] + soft + out[idx + len(harsh) :]
        lower = out.casefold()
    return out


def _diag_status_soft_label(status: str) -> str:
    key = normalize_diagnostic_status(status)
    return _DIAG_STATUS_SOFT_LABELS.get(key, diagnostic_status_label(key))


def _diag_status_caption(status: str) -> str:
    return _diag_status_soft_label(status)


def _diag_status_chip_html(status: str, *, label: str | None = None) -> str:
    key = normalize_diagnostic_status(status)
    text = html.escape(label or _diag_status_soft_label(key))
    color = _DIAG_STATUS_COLORS.get(key, _DIAG_STATUS_COLORS["not_enough_information"])
    return (
        f'<span class="sw-diag-chip sw-diag-chip-{html.escape(key)}">'
        f'<span class="dot" style="background:{color};"></span>'
        f"{text}</span>"
    )


def _diag_count_statuses(areas_by_key: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {
        "strong_stable": 0,
        "needs_attention": 0,
        "critical_gap": 0,
        "not_enough_information": 0,
    }
    for key in DIAGNOSTIC_AREA_KEYS:
        area = areas_by_key.get(key) or {}
        status = normalize_diagnostic_status(area.get("status"))
        if key not in areas_by_key:
            status = "not_enough_information"
        if status in ("strong", "stable"):
            counts["strong_stable"] += 1
        elif status in counts:
            counts[status] += 1
        else:
            counts["not_enough_information"] += 1
    return counts


def _diag_collect_priorities(diag: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer durable/UI priorities, else revision_priorities (already max 3)."""
    priorities = diag.get("priorities") if isinstance(diag.get("priorities"), list) else []
    if not priorities:
        rev_raw = result.get("revision_priorities")
        if isinstance(rev_raw, list):
            priorities = [p for p in rev_raw if isinstance(p, dict)]
    out: list[dict[str, Any]] = []
    for item in priorities[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        out.append(item)
    return out


def _diag_view_model(diag: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Shape diagnostics JSON for the simplified pastor-facing UI."""
    areas_by_key = _diag_areas_index(result.get("diagnostic_areas"))
    summary = _diag_soften_text(str(result.get("overall_summary") or "").strip())
    return {
        "summary": _diag_shorten(summary, limit=420) if summary else "",
        "counts": _diag_count_statuses(areas_by_key),
        "priorities": _diag_collect_priorities(diag, result),
        "areas_by_key": areas_by_key,
        "coherence": _diag_soften_text(
            str(result.get("overall_coherence") or "").strip()
        ),
        "ready": result.get("ready_for_next_stage"),
        "readiness_note": _diag_soften_text(
            str(result.get("readiness_note") or "").strip()
        ),
        "strengths": result.get("major_strengths"),
        "consistency_warnings": result.get("consistency_warnings"),
        "pastoral_warnings": result.get("pastoral_warnings"),
        "voice_note": _diag_soften_text(
            str(result.get("voice_and_originality_note") or "").strip()
        ),
        "warnings": result.get("warnings"),
        "missing_information": result.get("missing_information"),
        "areas": result.get("diagnostic_areas"),
    }


def _render_diag_summary(summary: str) -> None:
    st.markdown("**Rövid összkép**")
    if summary:
        st.markdown(summary)
    else:
        st.caption("Még nincs rövid összkép ehhez a diagnosztikához.")


def _render_diag_status_cards(counts: dict[str, int]) -> None:
    st.markdown("**Gyors státusz**")
    cards = [
        (counts.get("strong_stable", 0), "Erősségek", "#4a7c74"),
        (counts.get("needs_attention", 0), "Figyelmet igényel", "#c4923a"),
        (counts.get("critical_gap", 0), "Javítandó pontok", "#a65d48"),
        (counts.get("not_enough_information", 0), "Nincs elég adat", "#8a8580"),
    ]
    cards_html = "".join(
        (
            '<div class="sw-diag-count-card" '
            f'style="border-top: 3px solid {color};">'
            f'<div class="n">{n}</div>'
            f'<div class="lbl">{html.escape(lbl)}</div>'
            "</div>"
        )
        for n, lbl, color in cards
    )
    st.markdown(
        f'<div class="sw-diag-count-grid">{cards_html}</div>',
        unsafe_allow_html=True,
    )


def _render_diag_focus(priorities: list[dict[str, Any]]) -> None:
    st.markdown("**Most erre figyelj**")
    if not priorities:
        st.caption("Most nincs kiemelt javítási javaslat.")
        return
    for item in priorities[:3]:
        title = _diag_soften_text(str(item.get("title") or "").strip())
        why = _diag_soften_text(
            str(item.get("why_it_matters") or item.get("problem") or "").strip()
        )
        action = _diag_soften_text(str(item.get("recommended_action") or "").strip())
        parts = [f"<h5>{html.escape(title)}</h5>"]
        if why:
            parts.append(f"<p>{html.escape(_diag_shorten(why, limit=240))}</p>")
        if action:
            parts.append(
                f'<div class="meta"><strong>Következő lépés:</strong> '
                f"{html.escape(_diag_shorten(action, limit=180))}</div>"
            )
        st.markdown(
            f'<div class="sw-diag-prio-card">{"".join(parts)}</div>',
            unsafe_allow_html=True,
        )


def _render_diag_area_detail(area: dict[str, Any], *, expanded: bool) -> None:
    key = str(area.get("key") or "").strip()
    label = str(area.get("label") or "").strip() or diagnostic_area_label(key)
    # Never show raw internal keys as the visible title.
    if label == key or "_" in label:
        label = diagnostic_area_label(key) or label
    status = str(area.get("status") or "").strip()
    status_label = _diag_status_soft_label(status)
    with st.expander(f"{label} — {status_label}", expanded=expanded):
        st.markdown(
            _diag_status_chip_html(status),
            unsafe_allow_html=True,
        )
        for field_label, field_key in (
            ("Megállapítás", "summary"),
            ("Bizonyíték", "evidence"),
            ("Javasolt irány", "concerns"),
        ):
            text = _diag_soften_text(str(area.get(field_key) or "").strip())
            if text:
                st.markdown(f"**{field_label}:** {_diag_shorten(text, limit=420)}")


def _render_diag_details(view: dict[str, Any]) -> None:
    areas_by_key: dict[str, dict[str, Any]] = view.get("areas_by_key") or {}
    areas = view.get("areas")

    with st.expander("Részletes diagnosztika", expanded=False):
        # Short category list (human labels only).
        if areas_by_key or (
            isinstance(areas, list) and any(isinstance(a, dict) for a in areas)
        ):
            st.markdown("**Területek áttekintése**")
            shown_keys: set[str] = set()
            for group in _DIAG_DETAIL_GROUPS:
                rows: list[str] = []
                for key in group["keys"]:
                    area = areas_by_key.get(key) or {}
                    if key in areas_by_key:
                        status = normalize_diagnostic_status(area.get("status"))
                    else:
                        status = "not_enough_information"
                    shown_keys.add(key)
                    rows.append(
                        '<div class="sw-diag-area-row">'
                        f'<span class="sw-diag-area-name">'
                        f"{html.escape(diagnostic_area_label(key))}</span>"
                        f"{_diag_status_chip_html(status)}"
                        "</div>"
                    )
                st.markdown(
                    '<div class="sw-diag-group-block">'
                    f"<h5>{html.escape(str(group['title']))}</h5>"
                    + "".join(rows)
                    + "</div>",
                    unsafe_allow_html=True,
                )
            # Any unexpected extras: show by human label only.
            if isinstance(areas, list):
                for area in areas:
                    if not isinstance(area, dict):
                        continue
                    key = str(area.get("key") or "").strip()
                    if not key or key in shown_keys:
                        continue
                    label = diagnostic_area_label(key) or str(
                        area.get("label") or "Egyéb terület"
                    ).strip()
                    status = normalize_diagnostic_status(area.get("status"))
                    st.markdown(
                        f"{label} — {_diag_status_soft_label(status)}"
                    )

        strengths = view.get("strengths")
        if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
            st.markdown("**Ami jól áll**")
            for item in strengths[:4]:
                line = _diag_soften_text(str(item or "").strip())
                if line:
                    st.markdown(f"- {line}")

        coherence = str(view.get("coherence") or "").strip()
        if coherence:
            st.markdown("**Összhang**")
            st.markdown(_diag_shorten(coherence, limit=280))

        ready = view.get("ready")
        readiness_note = str(view.get("readiness_note") or "").strip()
        if ready is not None or readiness_note:
            st.markdown("**Továbbhaladás**")
            if isinstance(ready, bool):
                st.markdown(
                    "A terv alapján tovább lehet lépni."
                    if ready
                    else "Érdemes még finomítani a fenti pontokon."
                )
            if readiness_note:
                st.markdown(_diag_shorten(readiness_note, limit=240))

        voice_note = str(view.get("voice_note") or "").strip()
        if voice_note:
            st.markdown("**Saját hang**")
            st.markdown(_diag_shorten(voice_note, limit=280))

        for title, key in (
            ("Összefüggésbeli megjegyzések", "consistency_warnings"),
            ("Pásztori megjegyzések", "pastoral_warnings"),
        ):
            items = view.get(key)
            if isinstance(items, list) and any(str(x).strip() for x in items):
                st.markdown(f"**{title}**")
                for item in items:
                    line = _diag_soften_text(str(item or "").strip())
                    if line:
                        st.caption(line)

        if isinstance(areas, list) and areas:
            attention = [
                a
                for a in areas
                if isinstance(a, dict)
                and normalize_diagnostic_status(a.get("status"))
                in ("critical_gap", "needs_attention")
            ]
            if attention:
                st.markdown("**Részletek a finomítandó területekről**")
                for area in attention:
                    _render_diag_area_detail(area, expanded=False)

        warnings = view.get("warnings")
        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            for item in warnings:
                line = _diag_soften_text(str(item or "").strip())
                if line:
                    st.caption(line)

        missing = view.get("missing_information")
        if isinstance(missing, list) and any(str(x).strip() for x in missing):
            st.caption(
                "Hiányzó információ: "
                + "; ".join(
                    _diag_soften_text(str(x).strip())
                    for x in missing
                    if str(x).strip()
                )
            )


def _outline_field_filled(value: Any) -> bool:
    if isinstance(value, list):
        return any(str(x or "").strip() for x in value)
    if isinstance(value, dict):
        return any(_outline_field_filled(v) for v in value.values())
    return bool(str(value or "").strip())


def _render_outline_edit_expander(outline: dict[str, Any]) -> None:
    """Szerkesztő — kanonikus vázlatszöveg + külön saját megjegyzések."""
    with st.expander("Vázlat szerkesztése", expanded=False):
        st.caption(
            "A módosítások csak a vázlatot érintik; az eredeti műhelydöntéseket "
            "nem írják felül. A saját megjegyzések nem helyettesítik a vázlatot."
        )
        st.text_area(
            "Vázlatszöveg",
            key=_KEY_OUTLINE["content"],
            height=320,
            placeholder="Az összeállított munkavázlat szövege…",
        )
        st.text_area(
            "Saját megjegyzéseim",
            key=_KEY_OUTLINE["manual_notes"],
            height=80,
            placeholder="Szószéki emlékeztetők, hangsúlyok, időzítés…",
        )
        if st.button("Vázlat mentése", key="sw_outline_save_edit"):
            _persist_outline_from_widgets(mark_manual_edit=True)
            saved = normalize_sermon_outline(
                ensure_sermon_workshop_state(st.session_state).get("sermon_outline")
            )
            if not outline_has_content(saved):
                st.warning(
                    "Üres vázlat nem menthető elkészültként. Írj be vázlatszöveget."
                )
                return
            st.session_state[_RESYNC_FLAG] = True
            st.success("Vázlat elmentve.")
            st.rerun()


def render_outline_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Igehirdetési vázlat — kanonikus előnézet + szerkesztés + jóváhagyás."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    flash_warnings = st.session_state.pop(_OUTLINE_ASSEMBLY_FLASH_WARNINGS, None)
    if flash_warnings:
        for w in flash_warnings:
            st.warning(str(w))
    flash_success = st.session_state.pop(_OUTLINE_ASSEMBLY_FLASH_SUCCESS, None)
    if flash_success:
        st.success(str(flash_success))

    render_work_section(
        title="Igehirdetési vázlat",
        context="Igehirdetési műhely",
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    outline, repaired = repair_outline_integrity(sw.get("sermon_outline"))
    if repaired:
        save_sermon_outline(
            st.session_state,
            outline,
            stamp_generated_at=False,
            mark_manual_edit=False,
        )
        sw = ensure_sermon_workshop_state(st.session_state)
        sw["sermon_outline_status"] = str(outline.get("status") or "draft")
        st.session_state[_RESYNC_FLAG] = True
        if outline.get("needs_rebuild") or not outline_has_content(outline):
            st.warning("A vázlatot újra össze kell állítani.")

    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    try:
        from sermon_outline_engine import REFRESH_NOTICE, outline_needs_refresh
        from sermon_workshop_outline_ai import collect_available_sermon_material

        bundle = collect_available_sermon_material(st.session_state, sermon_workshop=sw)
        if outline_has_content(outline) and outline_needs_refresh(outline, bundle):
            if str(outline.get("status") or "") != "needs_refresh":
                outline["status"] = "needs_refresh"
                sw["sermon_outline"] = outline
                sw["sermon_outline_status"] = "needs_refresh"
            st.info(REFRESH_NOTICE)
    except Exception:  # noqa: BLE001
        pass

    has_outline = outline_has_content(outline)
    manually_edited = bool(outline.get("manually_edited"))
    need_confirm = bool(st.session_state.get(_CONFIRM_OUTLINE_OVERWRITE))
    status = str(sw.get("sermon_outline_status") or outline.get("status") or "draft")
    if not has_outline and status == "approved":
        status = "draft"
        update_sermon_workshop_section(st.session_state, "sermon_outline_status", "draft")

    primary_label = (
        "Vázlat frissítése a meglévő anyagból"
        if has_outline
        else "Vázlat összeállítása a meglévő anyagból"
    )
    with work_surface("sw_outline"):
        with action_row("sw_outline_assemble"):
            if st.button(primary_label, type="primary", key="sw_outline_assemble"):
                if has_outline and manually_edited and not need_confirm:
                    st.session_state[_CONFIRM_OUTLINE_OVERWRITE] = True
                    st.warning(
                        "A vázlat kézzel szerkesztve van. "
                        "A frissítés felülírja a kézi módosításokat — "
                        "kattints újra a megerősítéshez."
                    )
                else:
                    _assemble_and_save_outline(
                        generate_fn=generate_fn,
                        force_overwrite=bool(has_outline),
                    )

        # Állapot + frissítési idő — csak valódi tartalom mellett „Elkészült”.
        if has_outline:
            if status == "approved":
                st.success("Vázlat állapota: jóváhagyott")
            else:
                render_info_panel(
                    title="Vázlat állapota: vázlat (draft)",
                    tone="info",
                )
            generated = str(
                sw.get("sermon_outline_updated_at") or outline.get("updated_at") or ""
            )
            if generated:
                st.caption(f"Utolsó frissítés: {generated}")

            st.markdown("### Vázlat előnézete")
            render_compact_sermon_outline(outline)
            with st.expander("Szószéki nézet", expanded=False):
                st.caption(
                    "Nagyobb betűméret, tiszta háttér — ugyanaz a kanonikus vázlattartalom."
                )
                render_pulpit_outline_view(outline)

            # Biztonsági háló: ha a lapos `outline` mirror-kulcs valamiért
            # még üres (pl. frissen betöltött régi projekt, amiben még nem
            # futott mentés ebben a munkamenetben), a Word-export előtt
            # pótoljuk a kanonikus szövegből — ugyanaz a minta, mint a
            # korábbi Textusműhely-oldali "Vázlat" fülön volt.
            _outline_body_for_export = outline_canonical_text(outline)
            if _outline_body_for_export and not str(
                st.session_state.get("outline") or ""
            ).strip():
                st.session_state["outline"] = _outline_body_for_export

            st.divider()
            st.subheader("Letöltés")
            try:
                from datetime import datetime

                from outline_word_export import build_outline_docx

                _verse_clean = (
                    (st.session_state.get("last_igehely") or "vazlat")
                    .replace(" ", "_")
                    .replace("/", "-")
                    .replace(",", "")
                    .replace(":", "-")
                )
                _ts = datetime.now().strftime("%Y%m%d-%H%M")
                _filename_docx = f"textus-vazlat-{_verse_clean}-{_ts}.docx"
                if not str(st.session_state.get("outline") or "").strip():
                    st.session_state["outline"] = _outline_body_for_export
                _docx_bytes = build_outline_docx()
                if st.download_button(
                    label="Vázlat letöltése (Word)",
                    data=_docx_bytes,
                    file_name=_filename_docx,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=False,
                    key="outline_download_docx",
                    type="primary",
                ):
                    from textus_analytics import track_event

                    track_event(
                        "file_export",
                        {
                            "feature_name": "outline",
                            "file_format": "docx",
                            "method": "download",
                        },
                    )
            except ImportError as _docx_exc:
                import logging as _logging

                _logging.getLogger(__name__).exception(
                    "Word export unavailable (python-docx): %s", _docx_exc
                )
                st.error(
                    "A Word-export jelenleg nem érhető el. Az alkalmazás egyik dokumentumkezelő összetevője hiányzik."
                )
                with st.expander("Technikai részletek", expanded=False):
                    st.caption("Hiányzó függőség: python-docx")

            _render_outline_partial_regen(outline, generate_fn=generate_fn)

            # Alsó műveleti terület: jóváhagyás + szerkesztés + következő lépés
            with action_row("sw_outline_approve"):
                b_ap, b_dr = st.columns(2)
                with b_ap:
                    if status != "approved" and st.button(
                        "Vázlat jóváhagyása", key="sw_outline_approve"
                    ):
                        before = normalize_sermon_outline(
                            ensure_sermon_workshop_state(st.session_state).get(
                                "sermon_outline"
                            )
                        )
                        if not outline_has_content(before):
                            st.warning(
                                "Üres vagy csak whitespace-t tartalmazó vázlat "
                                "nem hagyható jóvá."
                            )
                        else:
                            _persist_outline_from_widgets(mark_manual_edit=None)
                            after = normalize_sermon_outline(
                                ensure_sermon_workshop_state(st.session_state).get(
                                    "sermon_outline"
                                )
                            )
                            if not outline_has_content(after):
                                save_sermon_outline(
                                    st.session_state,
                                    before,
                                    stamp_generated_at=False,
                                    mark_manual_edit=False,
                                )
                                st.warning(
                                    "A vázlat jóváhagyása megszakadt: "
                                    "a tartalom nem veszhet el."
                                )
                            else:
                                update_sermon_workshop_section(
                                    st.session_state,
                                    "sermon_outline_status",
                                    "approved",
                                )
                                st.session_state[_RESYNC_FLAG] = True
                                st.success("Vázlat jóváhagyva.")
                                st.rerun()
                with b_dr:
                    if status == "approved" and st.button(
                        "Jóváhagyás visszavonása", key="sw_outline_unapprove"
                    ):
                        update_sermon_workshop_section(
                            st.session_state, "sermon_outline_status", "draft"
                        )
                        st.rerun()

                _render_outline_edit_expander(outline)
        else:
            st.caption("Még nincs olvasható vázlattartalom.")
            if outline.get("needs_rebuild"):
                st.warning("A vázlatot újra össze kell állítani.")
            # Jegyzetek szerkeszthetők üres állapotban is, de nem helyettesítik a vázlatot.
            with st.expander("Saját megjegyzéseim", expanded=False):
                st.text_area(
                    "Saját megjegyzéseim",
                    key=_KEY_OUTLINE["manual_notes"],
                    height=80,
                    label_visibility="collapsed",
                    placeholder="Szószéki emlékeztetők… (ez nem a vázlat)",
                )
                if st.button("Megjegyzések mentése", key="sw_outline_save_notes_only"):
                    notes = str(st.session_state.get(_KEY_OUTLINE["manual_notes"]) or "")
                    current = normalize_sermon_outline(sw.get("sermon_outline"))
                    current["manual_notes"] = notes.strip()
                    save_sermon_outline(
                        st.session_state,
                        current,
                        stamp_generated_at=False,
                        mark_manual_edit=False,
                    )
                    st.success("Megjegyzések elmentve.")
                    st.rerun()


# A homiletikai profil 8 tengelye (a prompt szerinti nevekkel), meglévő
# terület-kulcsokra képezve. A numerikus érték csak a grafikonhoz kell.
_DIAG_PROFILE_AXES: tuple[tuple[str, str], ...] = (
    ("text_fidelity", "Textushűség"),
    ("unity_and_focus", "Fő gondolat és fókusz"),
    ("listener_tension", "Hallgatói megszólítás"),
    ("christ_centeredness", "Krisztus-központúság"),
    ("sermon_path", "Szerkezet és mozgások"),
    ("application", "Alkalmazás"),
    ("closing", "Lezárás"),
    ("pastoral_responsibility", "Pásztori hang"),
)

# Státusz → belső numerikus szint (csak renderhez; nincs összpontszám).
_DIAG_STATUS_VALUE: dict[str, int | None] = {
    "strong": 4,
    "stable": 3,
    "needs_attention": 2,
    "critical_gap": 1,
    "not_enough_information": None,
}


def _diag_profile_rows(areas_by_key: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """A 8 profil-tengely státusza + numerikus értéke (hiány → None)."""
    rows: list[dict[str, Any]] = []
    for key, label in _DIAG_PROFILE_AXES:
        if key in areas_by_key:
            area = areas_by_key[key]
            status = normalize_diagnostic_status(area.get("status"))
            # Explicit score (1–4), ha van — soha ne legyen 0 hiányzó adatból.
            raw_score = area.get("score")
            if status == "not_enough_information":
                value = None
            elif isinstance(raw_score, int) and raw_score > 0:
                value = max(1, min(4, raw_score))
            else:
                value = _DIAG_STATUS_VALUE.get(status)
        else:
            status = "not_enough_information"
            value = None
        rows.append(
            {
                "key": key,
                "label": label,
                "status": status,
                "status_label": _diag_status_soft_label(status),
                "value": value,
                "color": _DIAG_STATUS_COLORS.get(
                    status, _DIAG_STATUS_COLORS["not_enough_information"]
                ),
            }
        )
    return rows


# Legalább ennyi kiértékelt terület kell az összesített értékhez (nincs kitalált pont).
_MIN_AREAS_FOR_SCORE = 4

# Diagnosztikai profil-tengely → kapcsolódó műhelyszakasz (ugrógombhoz).
_DIAG_KEY_TO_SECTION: dict[str, str] = {
    "unity_and_focus": "Az igehirdetés fő gondolata",
    "listener_tension": "Hallgatói kérdés és feszültség",
    "christ_centeredness": "Krisztus-központú és evangéliumi ív",
    "sermon_path": "Az igehirdetés útja és mozgásai",
    "application": "Illusztrációk és aktualizálás",
    "closing": "Lezárás és megérkezés",
}

# Műhelyszakasz → pastor-facing ugrógomb címke.
_DIAG_SECTION_CTA: dict[str, str] = {
    "Az igehirdetés fő gondolata": "Fő gondolat kidolgozása",
    "Emberi helyzet és kegyelmi válasz": "Emberi helyzet kidolgozása",
    "Hallgatói kérdés és feszültség": "Hallgatói feszültség kidolgozása",
    "Krisztus-központú és evangéliumi ív": "Evangéliumi ív kidolgozása",
    "Az igehirdetés útja és mozgásai": "Út és mozgások kidolgozása",
    "Illusztrációk és aktualizálás": "Illusztrációk és alkalmazás",
    "Lezárás és megérkezés": "Lezárás kidolgozása",
    "Lekciójavaslat": "Lekció kidolgozása",
    "Imádsági előkészítés": "Imádság kidolgozása",
    "Igehirdetési vázlat": "Vázlat szerkesztése",
}


def _diag_aggregate_status(statuses: list[str]) -> str:
    """Több tengely → egy minőségi státusz (legrosszabb értékelt nyer)."""
    evaluated = [
        normalize_diagnostic_status(s)
        for s in statuses
        if normalize_diagnostic_status(s) != "not_enough_information"
    ]
    if not evaluated:
        return "not_enough_information"
    return min(evaluated, key=lambda s: _DIAG_STATUS_SEVERITY.get(s, 9))


def _diag_status_to_state(status: str) -> str:
    return _DIAG_STATUS_TO_STATE.get(
        normalize_diagnostic_status(status), "unknown"
    )


def _diag_work_map_segments(
    areas_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """6 szegmens a meglévő diagnostic_areas mezőkből — nincs kitalált pontszám."""
    segs: list[dict[str, Any]] = []
    for spec in _DIAG_WORK_MAP_SEGMENTS:
        statuses: list[str] = []
        summaries: list[str] = []
        for key in spec["keys"]:
            area = areas_by_key.get(key)
            if not area:
                continue
            statuses.append(str(area.get("status") or "not_enough_information"))
            summary = _diag_soften_text(str(area.get("summary") or "").strip())
            if summary:
                summaries.append(summary)
        status = _diag_aggregate_status(statuses) if statuses else "not_enough_information"
        state = _diag_status_to_state(status)
        tip_parts = [
            f"{spec['label']}: {segment_state_label(state)}",
        ]
        if summaries:
            tip_parts.append(_diag_shorten(summaries[0], limit=160))
        segs.append(
            {
                "key": spec["id"],
                "label": spec["label"],
                "status": status,
                "state_key": state,
                "tooltip": " — ".join(tip_parts),
            }
        )
    return segs


def _diag_center_qualifier(segments: list[dict[str, Any]]) -> str:
    """Rövid középső minősítő — szöveges, nem számszerű."""
    states = [str(s.get("state_key") or "unknown") for s in segments]
    known = [s for s in states if s != "unknown"]
    if not known:
        return "Még alakuló kép"
    if "attention" in known:
        return "További fókusz szükséges"
    if all(s == "emerged" for s in known) and len(known) >= 4:
        return "Összeálló ív"
    return "Kibontakozó ív"


def _diag_score_model(rows: list[dict[str, Any]], *, ready: Any) -> dict[str, Any]:
    """Legacy helper — minőségi összkép, pontszám nélkül."""
    _ = ready
    evaluated = [r for r in rows if isinstance(r.get("value"), int)]
    n = len(evaluated)
    if n < _MIN_AREAS_FOR_SCORE:
        return {
            "sufficient": False,
            "score": None,
            "qualifier": "Még nincs elég adat",
            "qualifier_key": "none",
            "summary": (
                "A jelenlegi vázlatból még nincs elég visszajelzés "
                "a homiletikai összképhez."
            ),
        }
    # Qualitative only — never expose a numeric score to the UI.
    avg = sum(r["value"] for r in evaluated) / n
    if avg >= 3.2:
        qkey, qual = "strong", "Kirajzolódik"
        summary = "A vázlat homiletikai íve kirajzolódik."
    elif avg >= 2.4:
        qkey, qual = "good", "Alakul"
        summary = "A vázlat íve alakul; néhány ponton még finomítható."
    else:
        qkey, qual = "improve", "Figyelmet kér"
        summary = "A vázlat több ponton is figyelmet kér."
    return {
        "sufficient": True,
        "score": None,
        "qualifier": qual,
        "qualifier_key": qkey,
        "summary": summary,
    }


def _diag_state_badge(rows: list[dict[str, Any]], *, has_source: bool, error: bool) -> tuple[str, str]:
    """Fejléc-badge: (címke, tónus) az elemzés állapota szerint."""
    if error and not has_source:
        return "Az automatikus elemzés nem érhető el", "warning"
    if not has_source:
        return "Még nincs diagnózis", "neutral"
    total = len(rows)
    evaluated = sum(1 for r in rows if isinstance(r.get("value"), int))
    if evaluated == 0:
        return "Aktuális vázlat", "neutral"
    if evaluated < total:
        return "Aktuális vázlat", "neutral"
    return "Aktuális vázlat", "success"


def _diag_section_for_priority(item: dict[str, Any]) -> str | None:
    """Legjobb tudás szerinti műhelyszakasz egy prioritáshoz (ugrógombhoz)."""
    if not isinstance(item, dict):
        return None
    affected = item.get("affected_sections")
    if not isinstance(affected, list):
        affected = item.get("affected_outline_parts")
    if isinstance(affected, list):
        for raw in affected:
            token = str(raw or "").strip()
            if not token:
                continue
            if token in _DIAG_KEY_TO_SECTION:
                return _DIAG_KEY_TO_SECTION[token]
            for opt in _SW_SECTION_OPTIONS:
                if token == opt or token.casefold() in opt.casefold():
                    return opt
    # Cím / kulcsszó alapú heurisztika a 6 szegmenshez.
    blob = " ".join(
        str(item.get(k) or "")
        for k in ("title", "suggested_action", "recommended_action", "explanation")
    ).casefold()
    heuristics = (
        ("textus", "Igehirdetési vázlat"),
        ("fő gondolat", "Az igehirdetés fő gondolata"),
        ("fo gondolat", "Az igehirdetés fő gondolata"),
        ("hallgat", "Hallgatói kérdés és feszültség"),
        ("krisztus", "Krisztus-központú és evangéliumi ív"),
        ("evangélium", "Krisztus-központú és evangéliumi ív"),
        ("mozgás", "Az igehirdetés útja és mozgásai"),
        ("ív", "Az igehirdetés útja és mozgásai"),
        ("lezár", "Lezárás és megérkezés"),
        ("megérkez", "Lezárás és megérkezés"),
        ("alkalmaz", "Illusztrációk és aktualizálás"),
    )
    for needle, section in heuristics:
        if needle in blob:
            return section
    return None


def _render_diag_overview_card(source: dict[str, Any], view: dict[str, Any]) -> None:
    """Homiletikai térkép + három kompakt összefoglaló egység."""
    ensure_dashboard_styles()
    areas_by_key = _diag_areas_index(source.get("diagnostic_areas"))
    segments = _diag_work_map_segments(areas_by_key)
    qualifier = _diag_center_qualifier(segments)
    has_any = any(s.get("state_key") != "unknown" for s in segments)

    map_col, sum_col = st.columns([1.05, 1.0])
    with map_col:
        st.markdown("**Homiletikai térkép**")
        render_work_map(
            segments,
            center_title="Aktuális vázlat",
            center_qualifier=qualifier,
            faint=not has_any,
        )
    with sum_col:
        _render_diag_summary_units(view)


def _render_diag_summary_units(view: dict[str, Any]) -> None:
    """Három kompakt egység: erősségek / következő lépés / finomítható."""
    strengths = [
        _diag_soften_text(str(x or "").strip())
        for x in (view.get("strengths") or [])
        if str(x or "").strip()
    ][:2]
    refinements = [
        r for r in (view.get("refinements") or []) if isinstance(r, dict)
    ]
    primary = refinements[0] if refinements else None
    secondary = refinements[1:3]

    # Ami már összeállt
    if strengths:
        items = "".join(
            f'<div class="tx-wsum-item"><span class="tx-wsum-ico"></span>'
            f"<span>{html.escape(_diag_shorten(s, limit=140))}</span></div>"
            for s in strengths
        )
    else:
        items = '<p style="margin:0;color:#6b5a48;font-size:0.86rem;">Még nincs kiemelt erősség.</p>'
    render_summary_card(title="Ami már összeállt", body_html=items)

    # Következő legerősebb lépés
    if primary:
        title = _diag_soften_text(str(primary.get("title") or "").strip())
        action = _diag_soften_text(
            str(
                primary.get("suggested_action")
                or primary.get("recommended_action")
                or ""
            ).strip()
        )
        explanation = _diag_soften_text(
            str(
                primary.get("explanation")
                or primary.get("why_it_matters")
                or ""
            ).strip()
        )
        line = action or explanation or title
        body = f"<p>{html.escape(_diag_shorten(line, limit=180))}</p>"
        if title and action and title.casefold() not in action.casefold():
            body = (
                f"<p><strong>{html.escape(_diag_shorten(title, limit=80))}</strong> — "
                f"{html.escape(_diag_shorten(action, limit=140))}</p>"
            )
        render_summary_card(
            title="Következő legerősebb lépés",
            body_html=body,
            variant="next",
        )
        section = _diag_section_for_priority(primary)
        if section:
            cta = "Megnyitás"
            if st.button(cta, key="sw_diag_jump_0", use_container_width=True):
                st.session_state[_KEY_ACTIVE_SECTION] = section
                st.rerun()
    else:
        render_summary_card(
            title="Következő legerősebb lépés",
            body_html='<p style="margin:0;color:#6b5a48;font-size:0.86rem;">'
            "Most nincs kiemelt következő lépés.</p>",
            variant="next",
        )

    # Finomítható — max 2 másodlagos tipp
    if secondary:
        tip_items = []
        for item in secondary:
            tip = _diag_soften_text(
                str(
                    item.get("suggested_action")
                    or item.get("title")
                    or item.get("explanation")
                    or ""
                ).strip()
            )
            if tip:
                tip_items.append(
                    f'<div class="tx-wsum-item"><span class="tx-wsum-ico"></span>'
                    f"<span>{html.escape(_diag_shorten(tip, limit=120))}</span></div>"
                )
        if tip_items:
            render_summary_card(
                title="Finomítható",
                body_html="".join(tip_items),
                variant="tips",
            )
    elif not primary:
        pass
    else:
        next_step = _diag_soften_text(str(view.get("next_step") or "").strip())
        if next_step:
            render_summary_card(
                title="Finomítható",
                body_html=(
                    f'<div class="tx-wsum-item"><span class="tx-wsum-ico"></span>'
                    f"<span>{html.escape(_diag_shorten(next_step, limit=120))}</span></div>"
                ),
                variant="tips",
            )


_DIAG_LAST_ERROR = "sermon_outline_diagnostics_error"


def _diag_active_source() -> tuple[dict[str, Any], str, bool]:
    """Aktív diagnosztikai forrás + időpont + van-e egyáltalán eredmény."""
    sw = ensure_sermon_workshop_state(st.session_state)
    outline_diag = sw.get("sermon_outline_diagnostics")
    legacy = sw.get("diagnostics") if isinstance(sw.get("diagnostics"), dict) else {}
    legacy_result = legacy.get("result") if isinstance(legacy.get("result"), dict) else {}
    if _diagnostics_has_result(outline_diag):
        generated = str(sw.get("sermon_outline_diagnostics_generated_at") or "").strip()
        return outline_diag if isinstance(outline_diag, dict) else {}, generated, True
    if legacy_result:
        generated = str(sw.get("m8_last_generated_at") or "").strip()
        return legacy_result, generated, True
    return {}, "", False


def _diag_is_stale(source: dict[str, Any], generated: str) -> bool:
    """True, ha a vázlat a diagnózis óta megváltozott."""
    sw = ensure_sermon_workshop_state(st.session_state)
    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    outline_updated = str(
        sw.get("sermon_outline_updated_at") or outline.get("updated_at") or ""
    ).strip()
    if not outline_updated:
        return False
    pinned = str(source.get("outline_updated_at_at_diagnosis") or "").strip()
    reference = pinned or generated
    if not reference:
        return False
    return outline_updated > reference


def _diag_is_heuristic(source: dict[str, Any]) -> bool:
    mode = str(source.get("mode") or "").strip()
    if mode == "local_heuristic":
        return True
    warnings = source.get("warnings") or []
    joined = " ".join(str(w) for w in warnings).casefold()
    return "gyors helyi" in joined or "heurisztikus" in joined


def _render_diag_profile_list(source: dict[str, Any]) -> None:
    """Részletes területi megjegyzések — csak a details expanderben használt."""
    areas_by_key = _diag_areas_index(source.get("diagnostic_areas"))
    segments = _diag_work_map_segments(areas_by_key)
    if not any(s.get("state_key") != "unknown" for s in segments):
        return
    st.markdown("**Homiletikai területek**")
    for seg in segments:
        state = str(seg.get("state_key") or "unknown")
        color = segment_state_color(state)
        st.markdown(
            f"- **{html.escape(str(seg.get('label') or ''))}** — "
            f'<span style="color:{color};font-weight:600;">'
            f"{html.escape(segment_state_label(state))}</span>",
            unsafe_allow_html=True,
        )
        tip = str(seg.get("tooltip") or "")
        if " — " in tip:
            detail = tip.split(" — ", 1)[1].strip()
            if detail:
                st.caption(detail)


def _render_diag_priority_card(item: dict[str, Any], *, index: int, primary: bool) -> None:
    """Egy fejlesztési prioritás kártya + opcionális műhely-ugrógomb."""
    title = _diag_soften_text(str(item.get("title") or "").strip())
    explanation = _diag_soften_text(str(item.get("explanation") or "").strip())
    action = _diag_soften_text(str(item.get("suggested_action") or "").strip())
    # Régi (M8) prioritásmezők átvétele, ha az új mezők üresek.
    if not explanation:
        explanation = _diag_soften_text(str(item.get("why_it_matters") or "").strip())
    if not action:
        action = _diag_soften_text(str(item.get("recommended_action") or "").strip())
    cls = "sw-diag-prio-card -primary" if primary else "sw-diag-prio-card"
    parts = [f"<h5>{html.escape(title)}</h5>"]
    if explanation:
        parts.append(f"<p>{html.escape(_diag_shorten(explanation, limit=200))}</p>")
    if action:
        parts.append(
            '<div class="meta"><strong>Következő lépés:</strong> '
            f"{html.escape(_diag_shorten(action, limit=180))}</div>"
        )
    st.markdown(f'<div class="{cls}">{"".join(parts)}</div>', unsafe_allow_html=True)
    section = _diag_section_for_priority(item)
    if section:
        cta = _DIAG_SECTION_CTA.get(section, f"Ugrás: {section}")
        if st.button(
            cta,
            key=f"sw_diag_jump_{index}",
            use_container_width=True,
        ):
            st.session_state[_KEY_ACTIVE_SECTION] = section
            st.rerun()


def _render_diagnostics_results() -> None:
    source, generated, has_source = _diag_active_source()
    if not has_source:
        return

    _ensure_diag_styles()
    ensure_dashboard_styles()
    view = _diag_view_model_simplified(source)
    heuristic = _diag_is_heuristic(source)
    areas_by_key = _diag_areas_index(source.get("diagnostic_areas"))
    has_evaluable = any(
        normalize_diagnostic_status(a.get("status")) != "not_enough_information"
        for a in areas_by_key.values()
    )

    # Térkép + három összefoglaló egység (üres területekkel is — semleges szürke).
    _render_diag_overview_card(source, view)

    with st.expander("Részletes megjegyzések", expanded=False):
        overview = str(view.get("overview") or "").strip()
        if overview:
            st.markdown("**Összkép**")
            st.markdown(_diag_soften_text(overview))
        if heuristic:
            st.markdown(
                '<p class="sw-diag-howto">Ez gyors helyi ellenőrzés, nem teljes '
                "MI-diagnosztika. Az erősségek és javaslatok a vázlat egyszerű "
                "helyi áttekintéséből származnak.</p>",
                unsafe_allow_html=True,
            )
        if has_evaluable:
            _render_diag_profile_list(source)
        notes = view.get("detailed_notes") or []
        warnings = view.get("warnings") or []
        if notes:
            st.markdown("**Részletek**")
            for note in notes:
                line = _diag_soften_text(str(note or "").strip())
                if line:
                    st.markdown(f"- {line}")
        if warnings:
            for warn in warnings:
                line = _diag_soften_text(str(warn or "").strip())
                if line:
                    st.caption(line)
        if not overview and not notes and not warnings and not has_evaluable:
            st.caption("Nincs további részletes megjegyzés.")
        if generated:
            st.caption(f"Elemzés időpontja: {generated}")


def render_diagnostics_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Homiletikai diagnosztika — kompakt munkatükör az aktuális vázlatról."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    sw0 = st.session_state.get("sermon_workshop")
    if isinstance(sw0, dict):
        sw0.setdefault("sermon_outline_diagnostics", {})
        sw0.setdefault("sermon_outline_diagnostics_generated_at", "")
        sw0.setdefault("sermon_outline_diagnostics_status", "idle")
        sw0.setdefault("sermon_outline_diagnostics_error", "")

    outline = _resolve_canonical_outline_for_diagnostics()
    has_outline = outline_has_content(outline)

    ensure_dashboard_styles()
    _ensure_diag_styles()

    if not has_outline:
        from sermon_workshop_outline_ai import assess_outline_readiness

        readiness = assess_outline_readiness(st.session_state)
        with work_surface("sw_diag_empty"):
            st.markdown(
                '<div class="tx-diag-head">'
                '<div class="tx-diag-head-left">'
                '<h2 class="tx-diag-head-title">Homiletikai diagnózis</h2>'
                '<p class="tx-diag-head-sub">Rövid munkatükör az aktuális vázlatról.</p>'
                "</div></div>",
                unsafe_allow_html=True,
            )
            faint_segs = [
                {
                    "key": s["id"],
                    "label": s["label"],
                    "state_key": "unknown",
                    "tooltip": f"{s['label']}: még nincs vázlat a diagnózishoz.",
                }
                for s in _DIAG_WORK_MAP_SEGMENTS
            ]
            render_work_map(
                faint_segs,
                center_title="Aktuális vázlat",
                center_qualifier="Vázlatra vár",
                faint=True,
            )
            render_empty_state(
                title="Előbb készíts igehirdetési vázlatot.",
                body=(
                    "A diagnosztika csak olvasható vázlattartalom mellett fut. "
                    "Nem kell minden műhelyszakaszt kitölteni."
                ),
            )
            with action_row("sw_diag_empty"):
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(
                        "Ugrás a vázlathoz",
                        key="sw_diag_jump_outline",
                        use_container_width=True,
                    ):
                        st.session_state[_KEY_ACTIVE_SECTION] = "Igehirdetési vázlat"
                        st.rerun()
                with c2:
                    if readiness.ok and st.button(
                        "Vázlat összeállítása",
                        type="primary",
                        key="sw_diag_assemble_only",
                        use_container_width=True,
                    ):
                        _assemble_and_save_outline(
                            generate_fn=generate_fn, force_overwrite=False
                        )
                        st.rerun()
            if readiness.ok:
                if st.button(
                    "Vázlat összeállítása és elemzése",
                    key="sw_diag_assemble_and_run",
                ):
                    _assemble_and_diagnose(generate_fn=generate_fn)
                    st.rerun()
            with st.expander("Hogyan olvassa a diagnosztikát?", expanded=False):
                st.markdown(
                    '<p class="sw-diag-howto">A térkép hat homiletikai terület '
                    "minőségi állapotát mutatja — pontszám és rangsor nélkül. "
                    "A diagnosztika tükör, nem automatikus értékelő.</p>",
                    unsafe_allow_html=True,
                )
        return

    with work_surface("sw_diag"):
        _render_diag_header(generate_fn=generate_fn)
        _render_diagnostics_results()


def _render_diag_header(*, generate_fn: GenerateFn | None) -> None:
    """Kompakt fejléc: cím + státusz + Vázlat elemzése."""
    _ensure_diag_styles()
    ensure_dashboard_styles()
    source, generated, has_source = _diag_active_source()
    sw = ensure_sermon_workshop_state(st.session_state)
    err = str(sw.get(_DIAG_LAST_ERROR) or "").strip()
    error = bool(err) or str(sw.get("sermon_outline_diagnostics_status") or "") == "error"
    stale = _diag_is_stale(source, generated) if has_source else False
    running = (
        bool(st.session_state.get("_sw_outline_diag_running"))
        or str(sw.get("sermon_outline_diagnostics_status") or "") == "running"
    )

    if running:
        status_label, status_cls = "Elemzés folyamatban", ""
    elif stale:
        status_label, status_cls = "Frissítés ajánlott", " -stale"
    elif has_source:
        status_label, status_cls = "Aktuális vázlat", ""
    else:
        status_label, status_cls = "Még nincs diagnózis", ""

    left, right = st.columns([1.4, 1.0])
    with left:
        st.markdown(
            '<div class="tx-diag-head-left">'
            '<h2 class="tx-diag-head-title">Homiletikai diagnózis</h2>'
            '<p class="tx-diag-head-sub">Rövid munkatükör az aktuális vázlatról.</p>'
            "</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Hogyan olvassa a diagnosztikát?", expanded=False):
            st.markdown(
                '<p class="sw-diag-howto">A hat szegmens a vázlatban érzékelhető '
                "homiletikai területeket tükrözi: <em>Kirajzolódik</em>, "
                "<em>Alakul</em>, <em>Figyelmet kér</em>, vagy "
                "<em>Még nincs elég adat</em>. Nincs pontszám vagy rangsor — "
                "a diagnosztika reflektív segédlet.</p>",
                unsafe_allow_html=True,
            )
    with right:
        st.markdown(
            f'<div class="tx-diag-head-right">'
            f'<span class="tx-diag-status-pill{status_cls}">'
            f'<span class="dot"></span>{html.escape(status_label)}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            "Vázlat elemzése",
            type="primary",
            key="sw_diag_run",
            icon=":material/refresh:",
            use_container_width=True,
            disabled=running,
            help="A vázlat homiletikai ellenőrzése a jelenlegi tartalom alapján.",
        ):
            _run_outline_homiletical_diagnostics(generate_fn=generate_fn)
            st.rerun()

    if running:
        st.info("A vázlat homiletikai elemzése folyamatban…")

    if err:
        render_info_panel(
            title="A diagnosztika nem készült el",
            body=err,
            tone="warning",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Újrapróbálás",
                key="sw_diag_retry",
                type="primary",
                use_container_width=True,
                disabled=running,
            ):
                _run_outline_homiletical_diagnostics(generate_fn=generate_fn)
                st.rerun()
        with c2:
            if st.button(
                "Gyors helyi ellenőrzés",
                key="sw_diag_local",
                use_container_width=True,
                disabled=running,
            ):
                _run_outline_homiletical_diagnostics(
                    generate_fn=generate_fn, prefer_local_heuristic=True
                )
                st.rerun()

    # generated időpont csak a részletekben / diszkréten
    if generated and not stale:
        st.caption(f"Utolsó elemzés: {generated}")
    elif error and not has_source:
        pass

def _request_adopt_lection_block(block: dict[str, Any]) -> None:
    st.session_state[_ADOPT_LECTION_PENDING] = dict(block or {})
    st.rerun()


def _lection_suggestion_payload(result: LectionSuggestionResult) -> dict[str, Any]:
    return result.to_dict()


def _lection_assessment_payload(result: LectionAssessmentResult) -> dict[str, Any]:
    return result.to_dict()


def _collect_lection_kwargs() -> dict[str, Any]:
    """Sessionből M9 lekció MI-bemenet."""
    base = _collect_closing_kwargs()
    live = _read_lection_from_widgets()
    sw = ensure_sermon_workshop_state(st.session_state)
    durable = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    # Meta mezők megőrzése a durable blokkból
    for meta in (
        "text_source",
        "text_source_url",
        "text_fetched_at",
        "text_fetched_reference",
    ):
        live[meta] = str(durable.get(meta) or "")
    base["lection"] = live
    base["testament_preference"] = live.get("testament_preference") or "any"
    base["length_preference"] = live.get("length_preference") or "standard"
    base["lection_user_focus"] = live.get("user_focus") or ""
    base["sermon_outline"] = normalize_sermon_outline(sw.get("sermon_outline"))
    base["original_text"] = _session_str("original_text")
    base["history"] = _session_str("history")
    return base


def _lection_link_kwargs(
    *,
    lection_reference: str | None = None,
    lection_text: str | None = None,
) -> dict[str, Any]:
    """Kapcsolati elemzés bemenete a sessionből."""
    kwargs = _collect_lection_kwargs()
    live = kwargs.get("lection") if isinstance(kwargs.get("lection"), dict) else {}
    ref = (lection_reference or live.get("reference") or "").strip()
    text = normalize_passage_text(
        lection_text if lection_text is not None else live.get("text")
    )
    return {
        "passage": kwargs.get("passage") or "",
        "passage_text": kwargs.get("passage_text") or "",
        "lection_reference": ref,
        "lection_text": text,
        "exegesis": kwargs.get("exegesis") or "",
        "original_text": kwargs.get("original_text") or "",
        "history": kwargs.get("history") or "",
        "theology": kwargs.get("theology") or "",
        "sermon_main_idea": kwargs.get("sermon_main_idea") or "",
        "text_main_idea": kwargs.get("text_main_idea") or "",
        "sermon_outline": kwargs.get("sermon_outline"),
    }


def _current_lection_link_fingerprint(
    *,
    lection_reference: str | None = None,
    lection_text: str | None = None,
) -> str:
    link_kw = _lection_link_kwargs(
        lection_reference=lection_reference,
        lection_text=lection_text,
    )
    return build_lection_link_fingerprint(
        passage_reference=str(link_kw.get("passage") or ""),
        passage_text=str(link_kw.get("passage_text") or ""),
        lection_reference=str(link_kw.get("lection_reference") or ""),
        lection_text=str(link_kw.get("lection_text") or ""),
        sermon_main_idea=str(
            link_kw.get("sermon_main_idea") or link_kw.get("text_main_idea") or ""
        ),
        outline_signature=outline_signature_for_link(link_kw.get("sermon_outline")),
    )


def _run_lection_connection_analysis(
    *,
    generate_fn: GenerateFn | None,
    lection_reference: str | None = None,
    lection_text: str | None = None,
    show_spinner: bool = True,
) -> dict[str, Any] | None:
    """Kapcsolati elemzés futtatása és tartós mentése. Hiba esetén None."""
    link_kw = _lection_link_kwargs(
        lection_reference=lection_reference,
        lection_text=lection_text,
    )
    if not str(link_kw.get("lection_reference") or "").strip():
        st.warning("Add meg a lekció igehelyét a kapcsolati elemzéshez.")
        return None

    def _do() -> dict[str, Any] | None:
        result = analyze_lection_textus_link(**link_kw, generate_fn=generate_fn)
        if not result.ok:
            st.error(
                _user_facing_error(
                    False,
                    result.error_message,
                    fallback=(
                        "A kapcsolati elemzés most nem készíthető el. "
                        "Próbáld újra, vagy ellenőrizd a kapcsolatot."
                    ),
                )
            )
            return None
        payload = result.to_dict()
        save_lection_connection_analysis(st.session_state, payload)
        return payload

    if show_spinner:
        with st.spinner("Kapcsolódás elemzése a textushoz…"):
            return _do()
    return _do()


def _run_lection_suggest(*, generate_fn: GenerateFn | None) -> None:
    _persist_lection_from_widgets()
    with st.spinner("Lekciójavaslat készül…"):
        kwargs = _collect_lection_kwargs()
        result = suggest_lections(**kwargs, generate_fn=generate_fn)
        if not result.ok:
            exact = (result.error_message or "").strip()
            for w in result.warnings or []:
                if "Generálási hiba:" in str(w):
                    exact = str(w)
                    break
            _log_lection_developer_error(exact or "lection suggest failed")
            # Ne töröljük a korábbi javaslatokat / manuális lekcióadatot.
            st.error(
                _user_facing_error(
                    False,
                    result.error_message,
                    fallback=(
                        "A lekciójavaslat most nem készíthető el. "
                        "Próbáld újra, vagy ellenőrizd a kapcsolatot."
                    ),
                )
            )
            return
        has_rec = bool(
            (result.recommended_lection and result.recommended_lection.reference)
            or result.no_separate_lection_needed
        )
        if not has_rec:
            _log_lection_developer_error("lection suggest empty recommendation")
            st.error(
                "A lekciójavaslat nem adott értelmezhető igehelyet. "
                "Próbáld újra, vagy adj meg saját szempontot."
            )
            return
        save_lection_suggestions(
            st.session_state, _lection_suggestion_payload(result)
        )
        # Kapcsolati elemzés lehetőleg már a javaslat részeként (ajánlott lekció).
        # Tartós mezőbe csak átvételkor / kézi gombnál kerül.
        rec_ref = str(
            (result.recommended_lection and result.recommended_lection.reference) or ""
        ).strip()
        if rec_ref and not result.no_separate_lection_needed:
            link_kw = _lection_link_kwargs(
                lection_reference=rec_ref,
                lection_text="",
            )
            with st.spinner("Kapcsolódás elemzése a textushoz…"):
                link_result = analyze_lection_textus_link(
                    **link_kw, generate_fn=generate_fn
                )
            if link_result.ok:
                sw = ensure_sermon_workshop_state(st.session_state)
                sug = (
                    sw.get("lection_suggestions")
                    if isinstance(sw.get("lection_suggestions"), dict)
                    else {}
                )
                sug = dict(sug)
                sug["connection_analysis"] = link_result.to_dict()
                save_lection_suggestions(
                    st.session_state, sug, stamp_generated_at=False
                )
        if result.missing_information and not (
            result.recommended_lection.reference
            or result.no_separate_lection_needed
        ):
            st.warning(
                "Nincs elegendő adat a felelős javaslathoz. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Javaslat elkészült.")


def _run_lection_assess(*, generate_fn: GenerateFn | None) -> None:
    _persist_lection_from_widgets()
    live = _read_lection_from_widgets()
    if not live.get("reference"):
        st.warning("Add meg a lekció igehelyét az értékeléshez.")
        return
    with st.spinner("Saját lekció értékelése…"):
        kwargs = _collect_lection_kwargs()
        result = assess_lection(**kwargs, generate_fn=generate_fn)
        if not result.ok:
            exact = (result.error_message or "").strip()
            for w in result.warnings or []:
                if "Generálási hiba:" in str(w):
                    exact = str(w)
                    break
            _log_lection_developer_error(
                exact or "lection assess failed", tab="Lekcióértékelés"
            )
            # Korábbi értékelés és manuális lekciómezők megmaradnak.
            st.error(
                _user_facing_error(
                    False,
                    result.error_message,
                    fallback=(
                        "A lekciójavaslat most nem készíthető el. "
                        "Próbáld újra, vagy ellenőrizd a kapcsolatot."
                    ),
                )
            )
            return
        save_lection_assessment(
            st.session_state, _lection_assessment_payload(result)
        )
        _apply_lection_assessment_to_fields(result)
        st.success("Értékelés elkészült.")


def _apply_lection_ruf_result(result: dict[str, Any]) -> None:
    """RÚF eredmény → lection_text + meta; nem érinti a passage_text-et."""
    text = normalize_passage_text(result.get("text"))
    from datetime import datetime, timezone

    sw = ensure_sermon_workshop_state(st.session_state)
    current = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    block = dict(current)
    block["text"] = text
    block["text_source"] = str(result.get("source_name") or SOURCE_NAME)
    block["text_source_url"] = str(result.get("source_url") or "")
    block["text_fetched_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    block["text_fetched_reference"] = str(
        result.get("normalized_reference") or result.get("requested_reference") or ""
    )
    # Widget + tartós
    st.session_state[_KEY_LECTION["text"]] = text
    update_sermon_workshop_section(st.session_state, "lection", block)
    st.session_state[_RESYNC_FLAG] = True


def _lection_text_mismatch_warning() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    fetched = str(lection.get("text_fetched_reference") or "").strip()
    current = str(
        st.session_state.get(_KEY_LECTION["reference"])
        or lection.get("reference")
        or ""
    ).strip()
    text = normalize_passage_text(
        st.session_state.get(_KEY_LECTION["text"]) or lection.get("text")
    )
    if not fetched or not current or not text.strip():
        return
    if references_equivalent(fetched, current):
        return
    st.warning(
        "A betöltött lekciószöveg egy másik igehelyhez tartozik. "
        "Töltsd be az új szakaszt, vagy ellenőrizd a jelenlegi szöveget."
    )


def _request_lection_ruf_load(reference: str) -> None:
    ref = (reference or "").strip()
    validation = validate_lection_reference(ref)
    if not validation.get("ok"):
        st.warning(
            str(validation.get("error") or "Az igehely nem érvényes a RÚF-betöltéshez.")
        )
        return
    with st.spinner("RÚF-szöveg lekérése…"):
        result = fetch_ruf_passage(ref)
    if not result.get("success"):
        err = str(result.get("error") or "A RÚF-szöveg betöltése nem sikerült.")
        st.error(err)
        st.info("A meglévő lekciószöveg nem törlődött.")
        return

    sw = ensure_sermon_workshop_state(st.session_state)
    lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    existing = normalize_passage_text(lection.get("text")).strip()
    fetched_ref = str(lection.get("text_fetched_reference") or "").strip()
    new_ref = str(
        result.get("normalized_reference") or result.get("requested_reference") or ""
    )
    if existing and fetched_ref and not references_equivalent(fetched_ref, new_ref):
        st.session_state[_LECTION_RUF_PENDING] = result
        st.warning(
            "Már van betöltött lekciószöveg egy másik igehelyhez. "
            "Megerősítés nélkül nem írjuk felül."
        )
        return
    _apply_lection_ruf_result(result)
    warnings = [str(w).strip() for w in result.get("warnings", []) if str(w).strip()]
    if warnings:
        st.warning(warnings[0])
    else:
        st.success("A lekció RÚF-szövege betöltődött.")
    st.rerun()


def _render_lection_ruf_confirm() -> None:
    pending = st.session_state.get(_LECTION_RUF_PENDING)
    if not isinstance(pending, dict):
        return
    st.warning(
        "Megerősíted a meglévő lekciószöveg cseréjét az új RÚF-szakaszra?"
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Igen, cserélem", key="sw_lection_ruf_confirm_yes"):
            result = st.session_state.pop(_LECTION_RUF_PENDING, None)
            if isinstance(result, dict):
                _apply_lection_ruf_result(result)
                st.success("A lekció RÚF-szövege frissült.")
            st.rerun()
    with c2:
        if st.button("Mégse", key="sw_lection_ruf_confirm_no"):
            st.session_state.pop(_LECTION_RUF_PENDING, None)
            st.info("A meglévő lekciószöveg megmaradt.")


def _render_lection_candidate(
    candidate: LectionCandidate | dict[str, Any],
    *,
    key_prefix: str,
    heading: str,
) -> None:
    if isinstance(candidate, LectionCandidate):
        data = candidate.to_dict()
    elif isinstance(candidate, dict):
        data = candidate
    else:
        return
    ref = str(data.get("reference") or "").strip()
    if not ref and not str(data.get("rationale") or "").strip():
        return
    valid = bool(data.get("reference_valid"))
    if "reference_valid" not in data and ref:
        validation = validate_lection_reference(ref)
        valid = bool(validation.get("ok"))
        data["reference_error"] = str(validation.get("error") or "")
        data["reference_valid"] = valid

    st.markdown(f"**{heading}**")
    st.markdown(f"**Igehely:** {ref or '—'}")
    conn = normalize_lection_connection_type(data.get("connection_type"))
    if conn:
        st.markdown(
            f"**Kapcsolat típusa:** {lection_connection_type_label(conn)}"
        )
    rationale = str(data.get("rationale") or "").strip()
    if rationale:
        st.markdown("**Miért illik hozzá?**")
        st.write(rationale)
    func = str(
        data.get("liturgical_function") or data.get("function") or ""
    ).strip()
    if func:
        st.markdown(f"**Liturgiai funkció:** {func}")
    length = str(data.get("estimated_length") or "").strip()
    if length:
        st.markdown(f"**Becsült hossz:** {length}")

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if str(w).strip():
            st.caption(f"Figyelem: {w}")
    if ref and not valid:
        err = str(data.get("reference_error") or "").strip()
        st.warning(
            err
            or "Az igehely nem érvényesíthető — RÚF-betöltés nem érhető el."
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Ezt választom lekciónak", key=f"{key_prefix}_adopt"):
            _request_adopt_lection_block(
                {
                    "reference": ref,
                    "connection_type": conn,
                    "function": func,
                    "rationale": rationale,
                }
            )
    with b2:
        if ref and valid:
            if st.button("RÚF-szöveg betöltése", key=f"{key_prefix}_ruf"):
                _request_lection_ruf_load(ref)


def _render_lection_suggestions() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("lection_suggestions")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not (
        isinstance(data.get("recommended_lection"), dict)
        and data.get("recommended_lection", {}).get("reference")
    ):
        err = _user_facing_error(
            False,
            str(data.get("error_message") or ""),
            fallback=(
                "A lekciójavaslat most nem készíthető el. "
                "Próbáld újra, vagy ellenőrizd a kapcsolatot."
            ),
        )
        if err:
            st.error(err)
        return

    if data.get("no_separate_lection_needed"):
        st.info(
            str(data.get("no_lection_reason") or "").strip()
            or "Az MI szerint külön lekció nem feltétlenül szükséges."
        )

    rec = data.get("recommended_lection")
    if isinstance(rec, dict) and (
        rec.get("reference") or rec.get("rationale")
    ):
        st.markdown("**MI-javaslat**")
        _render_lection_candidate(
            rec, key_prefix="sw_mi_lection_rec", heading="Ajánlott lekció"
        )

    alts = (
        data.get("alternative_lections")
        if isinstance(data.get("alternative_lections"), list)
        else []
    )
    visible_alts = [a for a in alts[:3] if isinstance(a, dict)]
    if visible_alts:
        with st.expander(
            f"További javaslatok ({len(visible_alts)})",
            expanded=True,
        ):
            for idx, alt in enumerate(visible_alts, start=1):
                _render_lection_candidate(
                    alt,
                    key_prefix=f"sw_mi_lection_alt_{idx}",
                    heading=f"Alternatíva {idx}",
                )

    reasoning = str(data.get("overall_reasoning") or "").strip()
    basis = data.get("basis") if isinstance(data.get("basis"), list) else []
    with st.expander("Mi alapján készült?", expanded=False):
        if reasoning:
            st.write(reasoning)
        if basis:
            for b in basis:
                if str(b).strip():
                    st.caption(f"• {b}")
        if not reasoning and not basis:
            st.caption("Nincs részletes indoklás.")

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    missing = (
        data.get("missing_information")
        if isinstance(data.get("missing_information"), list)
        else []
    )
    for w in warnings:
        if str(w).strip():
            st.warning(str(w))
    if missing:
        st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))


def _render_lection_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("lection_assessment")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not str(data.get("overall_assessment") or "").strip():
        err = _user_facing_error(
            False,
            str(data.get("error_message") or ""),
            fallback=(
                "A lekciójavaslat most nem készíthető el. "
                "Próbáld újra, vagy ellenőrizd a kapcsolatot."
            ),
        )
        if err:
            st.error(err)
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and not data.get("strengths") and not data.get("improvements"):
        return
    st.markdown("**Saját lekció értékelése**")
    if overall:
        st.write(overall)
    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    if strengths:
        st.markdown("**Erősségek**")
        for s in strengths:
            if str(s).strip():
                st.caption(f"• {s}")
    improvements = (
        data.get("improvements") if isinstance(data.get("improvements"), list) else []
    )
    if improvements:
        st.markdown("**Javítási lehetőségek**")
        for s in improvements:
            if str(s).strip():
                st.caption(f"• {s}")
    for label, key in (
        ("Kapcsolattípus", "connection_type_assessment"),
        ("Hossz", "length_assessment"),
        ("Liturgiai illeszkedés", "liturgical_fit_assessment"),
    ):
        val = str(data.get(key) or "").strip()
        if val:
            st.markdown(f"**{label}:** {val}")
    sug_ref = str(data.get("suggested_reference") or "").strip()
    sug_conn = normalize_lection_connection_type(
        data.get("suggested_connection_type")
    )
    revised = str(data.get("revised_rationale") or "").strip()
    if sug_ref or revised:
        st.caption("Javaslatok (nem írják felül automatikusan a választásodat):")
        if sug_ref:
            st.write(f"Javasolt igehely: {sug_ref}")
        if sug_conn:
            st.write(
                f"Javasolt kapcsolattípus: {lection_connection_type_label(sug_conn)}"
            )
        if revised:
            st.write(revised)
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if str(w).strip():
            st.warning(str(w))


def _render_lection_reader() -> None:
    """Betöltött lekció olvasónézete — külön az alaptextustól."""
    text = normalize_passage_text(st.session_state.get(_KEY_LECTION["text"]))
    _ensure_bible_text_styles()
    st.markdown("**Lekció szövege**")
    if text.strip():
        _lection_text_mismatch_warning()
        render_formatted_bible_text(text)
        sw = ensure_sermon_workshop_state(st.session_state)
        lection = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
        source = str(lection.get("text_source") or "").strip()
        url = str(lection.get("text_source_url") or "").strip()
        fetched_ref = str(lection.get("text_fetched_reference") or "").strip()
        if source or url or fetched_ref:
            caption = f"Forrás: {source or SOURCE_NAME}"
            if fetched_ref:
                caption += f" — {fetched_ref}"
            if url:
                st.markdown(f"{caption}  \n[Megnyitás a forrásoldalon]({url})")
            else:
                st.caption(caption)
    with st.expander(
        "Lekció szövegének szerkesztése",
        expanded=not bool(text.strip()),
    ):
        st.text_area(
            "Lekció szövege",
            key=_KEY_LECTION["text"],
            height=180,
            label_visibility="collapsed",
            placeholder="Töltsd be a RÚF szöveget, vagy illeszd be ide kézzel…",
        )
        if st.button("Lekciószöveg mentése", key="sw_lection_text_save"):
            _persist_lection_from_widgets(include_text=True)
            st.success("Lekciószöveg elmentve.")


def _render_lection_selected_summary() -> None:
    """Kiválasztott / jóváhagyott lekció kompakt összefoglalója."""
    block = _read_lection_from_widgets()
    sw = ensure_sermon_workshop_state(st.session_state)
    durable = sw.get("lection") if isinstance(sw.get("lection"), dict) else {}
    ref = block.get("reference") or ""
    text = normalize_passage_text(block.get("text") or durable.get("text"))
    conn = normalize_lection_connection_type(block.get("connection_type"))
    function = (block.get("function") or "").strip()
    rationale = (block.get("rationale") or "").strip()
    if not (ref or text.strip() or conn or function or rationale):
        return

    status = (sw.get("lection_status") or "draft").strip()
    st.markdown("**Kiválasztott lekció**")
    st.caption(f"Állapot: {_STATUS_LABELS.get(status, status)}")
    if ref:
        st.markdown(f"**Igehely:** {ref}")
    if conn:
        st.markdown(
            f"**Kapcsolat típusa:** {lection_connection_type_label(conn)}"
        )
    if rationale:
        st.markdown("**Rövid indoklás**")
        st.write(rationale)
    if function:
        st.markdown(f"**Liturgiai funkció:** {function}")
    if text.strip():
        st.caption("RÚF-szöveg betöltve — lásd alább.")


def _render_lection_textus_link_card(*, generate_fn: GenerateFn | None) -> None:
    """Kapcsolódás a textushoz — egy munkakártya a kiválasztott lekció alatt."""
    block = _read_lection_from_widgets()
    ref = (block.get("reference") or "").strip()
    if not ref:
        return

    sw = ensure_sermon_workshop_state(st.session_state)
    analysis = sw.get("lection_connection_analysis")
    if not isinstance(analysis, dict):
        analysis = None

    fingerprint = _current_lection_link_fingerprint()
    analysis_ref = (
        str((analysis or {}).get("lection_reference") or "").strip() if analysis else ""
    )
    ref_mismatch = bool(
        analysis
        and analysis_ref
        and not references_equivalent(ref, analysis_ref)
        and ref.casefold() != analysis_ref.casefold()
    )
    stale = ref_mismatch or lection_connection_analysis_is_stale(
        analysis, current_fingerprint=fingerprint
    )
    has_content = bool(
        analysis
        and (
            str(analysis.get("one_sentence") or "").strip()
            or analysis.get("key_links")
            or analysis.get("connection_types")
        )
    )

    with st.container(border=True):
        st.markdown("**Kapcsolódás a textushoz**")
        st.caption(
            "A prédikáció textusa marad a középpontban — a lekció előkészíti, "
            "kiegészíti vagy liturgikusan keretezi, de nem váltja fel."
        )

        if stale and has_content:
            st.warning(
                "A kapcsolati elemzés elavult (megváltozott a textus, a lekció "
                "vagy a homiletikai anyag). Érdemes frissíteni."
            )
            if st.button(
                "Kapcsolódás frissítése",
                key="sw_lection_link_refresh",
                type="primary",
            ):
                payload = _run_lection_connection_analysis(generate_fn=generate_fn)
                if payload:
                    st.success("Kapcsolati elemzés frissítve.")
                    st.rerun()

        if not has_content:
            if st.button(
                "Kapcsolódás elemzése",
                key="sw_lection_link_analyze",
                type="primary",
            ):
                payload = _run_lection_connection_analysis(generate_fn=generate_fn)
                if payload:
                    st.success("Kapcsolati elemzés elkészült.")
                    st.rerun()
            return

        if analysis.get("ok") is False and not has_content:
            err = _user_facing_error(
                False,
                str(analysis.get("error_message") or ""),
                fallback=(
                    "A kapcsolati elemzés most nem készíthető el. "
                    "Próbáld újra, vagy ellenőrizd a kapcsolatot."
                ),
            )
            if err:
                st.error(err)
            return

        one = str(analysis.get("one_sentence") or "").strip()
        if one:
            st.markdown("**Kapcsolat egy mondatban**")
            st.write(one)

        types = (
            analysis.get("connection_types")
            if isinstance(analysis.get("connection_types"), list)
            else []
        )
        if types:
            st.markdown("**Kapcsolat típusa**")
            for item in types[:2]:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or "").strip() or lection_link_type_label(
                    str(item.get("type") or "")
                )
                rationale = str(item.get("rationale") or "").strip()
                if label and rationale:
                    st.markdown(f"**{label}.** {rationale}")
                elif label:
                    st.markdown(f"**{label}**")
                elif rationale:
                    st.write(rationale)

        links = (
            analysis.get("key_links")
            if isinstance(analysis.get("key_links"), list)
            else []
        )
        if links:
            st.markdown("**Kulcskapcsolatok**")
            for idx, link in enumerate(links[:4], start=1):
                if not isinstance(link, dict):
                    continue
                verse = str(link.get("verse_or_detail") or "").strip()
                motif = str(link.get("motif") or "").strip()
                sig = str(link.get("sermon_significance") or "").strip()
                parts = [p for p in (verse, motif, sig) if p]
                if not parts:
                    continue
                st.markdown(f"**{idx}.** " + " — ".join(parts))

        lit = (
            analysis.get("liturgical_role")
            if isinstance(analysis.get("liturgical_role"), dict)
            else {}
        )
        if any(str(lit.get(k) or "").strip() for k in lit) or lit.get(
            "needs_brief_intro"
        ):
            st.markdown("**Liturgikus szerep**")
            why = str(lit.get("why_read") or "").strip()
            focus = str(lit.get("congregation_focus") or "").strip()
            timing = before_after_label(str(lit.get("before_or_after") or ""))
            strongest = str(lit.get("strongest_verses") or "").strip()
            if why:
                st.write(why)
            if focus:
                st.caption(f"A gyülekezet figyeljen erre: {focus}")
            if timing:
                st.caption(timing)
            if lit.get("needs_brief_intro"):
                st.caption("Érdemes rövid felolvasás előtti bevezetés.")
            if strongest:
                st.caption(f"Legerősebb kapcsolathordozó versek: {strongest}")

        strength = str(analysis.get("connection_strength") or "").strip().casefold()
        if strength == "weak":
            st.info(
                str(analysis.get("weak_connection_note") or "").strip()
                or WEAK_CONNECTION_MESSAGE
            )
            alts = (
                analysis.get("alternative_lections")
                if isinstance(analysis.get("alternative_lections"), list)
                else []
            )
            visible = [a for a in alts[:2] if isinstance(a, dict)]
            if visible:
                st.markdown("**Szorosabb alternatívák**")
                for alt in visible:
                    aref = str(alt.get("reference") or "").strip()
                    arat = str(alt.get("rationale") or "").strip()
                    if aref and arat:
                        st.markdown(f"**{aref}** — {arat}")
                    elif aref:
                        st.markdown(f"**{aref}**")
                    elif arat:
                        st.write(arat)

        overlap = str(analysis.get("overlap_note") or "").strip()
        if overlap:
            st.caption(overlap)

        with st.expander("Háttér és részletek", expanded=False):
            ling = (
                analysis.get("linguistic_insights")
                if isinstance(analysis.get("linguistic_insights"), list)
                else []
            )
            if ling:
                st.markdown("**Releváns eredeti nyelvi felismerés**")
                for row in ling[:2]:
                    if not isinstance(row, dict):
                        continue
                    obs = str(row.get("observation") or "").strip()
                    why = str(row.get("why_it_matters") or "").strip()
                    if obs and why:
                        st.write(f"{obs} — {why}")
                    elif obs:
                        st.write(obs)
            else:
                st.caption("Nincs külön nyelvi megfigyelés ehhez a kapcsolathoz.")

            hist = (
                analysis.get("historical_background")
                if isinstance(analysis.get("historical_background"), list)
                else []
            )
            if hist:
                st.markdown("**Releváns kortörténeti háttér**")
                for row in hist[:3]:
                    if isinstance(row, dict):
                        obs = str(row.get("observation") or "").strip()
                        if obs:
                            st.write(f"• {obs}")
                    elif str(row).strip():
                        st.write(f"• {row}")
            else:
                st.caption("Nincs külön kortörténeti megjegyzés ehhez a kapcsolathoz.")

            theo = (
                analysis.get("theological_gospel_link")
                if isinstance(analysis.get("theological_gospel_link"), dict)
                else {}
            )
            theo_bits = [
                (label, str(theo.get(key) or "").strip())
                for key, label in (
                    ("divine_action", "Isten cselekvése"),
                    ("grace_arc", "Kegyelmi ív"),
                    ("christ_centered", "Krisztus-központú kapcsolat"),
                    ("listener_response", "Hallgatói válasz"),
                )
            ]
            theo_bits = [(lab, val) for lab, val in theo_bits if val]
            if theo_bits:
                st.markdown("**Teológiai és evangéliumi kapcsolat**")
                for lab, val in theo_bits:
                    st.markdown(f"**{lab}.** {val}")
            else:
                st.caption("Nincs külön teológiai kibontás ehhez a kapcsolathoz.")

            uses = (
                analysis.get("homiletical_uses")
                if isinstance(analysis.get("homiletical_uses"), list)
                else []
            )
            if uses:
                st.markdown("**Homiletikai felhasználás**")
                st.caption(
                    "Javaslatok — nem írják át automatikusan a vázlatot. "
                    "Te döntöd el, beilleszted-e őket."
                )
                for use in uses[:3]:
                    if not isinstance(use, dict):
                        continue
                    place = placement_label(str(use.get("placement") or ""))
                    sug = str(use.get("suggestion") or "").strip()
                    if sug:
                        st.markdown(f"**{place or 'Javaslat'}.** {sug}")
            else:
                st.caption("Nincs külön homiletikai felhasználási javaslat.")

        if not stale:
            st.caption("Az elemzés a jelenlegi textushoz és lekcióhoz igazodik.")


def _render_lection_connection_details_editor() -> None:
    """Mentett kapcsolat / funkció / indoklás — zárt, haladó szerkesztő."""
    block = _read_lection_from_widgets()
    has_details = bool(
        normalize_lection_connection_type(block.get("connection_type"))
        or (block.get("function") or "").strip()
        or (block.get("rationale") or "").strip()
    )
    if not has_details:
        return

    with st.expander("A lekció kapcsolódásának részletei", expanded=False):
        conn_options = [""] + list(LECTION_CONNECTION_TYPES)
        st.selectbox(
            "Kapcsolat típusa",
            options=conn_options,
            format_func=lambda v: (
                "—"
                if not v
                else LECTION_CONNECTION_TYPE_LABELS_HU.get(v, str(v))
            ),
            key=_KEY_LECTION["connection_type"],
        )
        st.text_area(
            "A lekció funkciója",
            key=_KEY_LECTION["function"],
            height=70,
            placeholder="Mit készít elő vagy mit mélyít el ez a lekció?",
        )
        st.text_area(
            "Rövid indoklás",
            key=_KEY_LECTION["rationale"],
            height=90,
            placeholder="Hogyan kapcsolódik a lekció az alaptextushoz?",
        )


def _render_lection_save_approve() -> None:
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_lection_save_draft"):
            block = _read_lection_from_widgets()
            if not any(
                block.get(k)
                for k in (
                    "reference",
                    "function",
                    "rationale",
                    "notes",
                    "text",
                    "user_focus",
                )
            ):
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                _persist_lection_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "lection_status", "draft"
                )
                _toast_and_rerun("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            type="primary",
            key="sw_lection_approve",
        ):
            block = _read_lection_from_widgets()
            if not block.get("reference"):
                st.warning("Jóváhagyáshoz add meg a lekció igehelyét.")
            else:
                _persist_lection_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "lection_status", "approved"
                )
                decisions = [
                    ("reference", "Lekció igehelye", block["reference"]),
                    (
                        "connection_type",
                        "Kapcsolat típusa",
                        lection_connection_type_label(block["connection_type"]),
                    ),
                    ("function", "A lekció funkciója", block["function"]),
                    ("rationale", "Rövid indoklás", block["rationale"]),
                ]
                added = 0
                skipped = 0
                for _field, category, content in decisions:
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_LECTION,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_LECTION,
                        category,
                        content,
                    )
                    added += 1
                if added:
                    _toast_and_rerun(f"Jóváhagyva ({added} döntés).")
                elif skipped:
                    _toast_and_rerun("Jóváhagyva. Ezek a döntések már szerepelnek.")
                else:
                    _toast_and_rerun("Jóváhagyva.")

    _render_decisions_for_section(_SOURCE_LECTION)


def render_lection_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Lekciójavaslat — egyszerűsített lelkipásztori munkafolyamat."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Lekciójavaslat")
    st.markdown(
        "A lekció hosszabb, összefüggő bibliai szakasz, amely előkészíti, "
        "elmélyíti vagy tágabb bibliai összefüggésbe helyezi az igehirdetés "
        "üzenetét. Elég néhány mondatban leírnod, mit keresel — vagy "
        "megadnod egy saját igehelyet."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    status = (sw.get("lection_status") or "draft").strip()
    st.caption(f"Állapot: {_STATUS_LABELS.get(status, status)}")

    st.text_area(
        "Milyen lekciót keresel?",
        key=_KEY_LECTION["user_focus"],
        height=100,
        help=(
            "Néhány mondatban megadhatod, milyen bibliai szakaszt szeretnél: "
            "milyen hangsúlyt hordozzon, melyik bibliai részből származzon, "
            "vagy körülbelül milyen hosszú legyen."
        ),
        placeholder=(
            "Evangéliumi szakaszt szeretnék, amely Isten megtartó kegyelmét "
            "és a hitben való megmaradást hangsúlyozza. Ne legyen túl hosszú."
        ),
    )
    st.caption(
        "Opcionális. Ha üresen hagyod, az MI a teljes eddigi munkafolyamat "
        "alapján javasol lekciót."
    )

    with st.expander("További beállítások", expanded=False):
        st.selectbox(
            "Melyik bibliai részből szeretnél lekciót?",
            options=list(LECTION_TESTAMENT_PREFERENCES),
            format_func=lambda v: LECTION_TESTAMENT_PREFERENCE_LABELS_HU.get(
                v, str(v)
            ),
            key=_KEY_LECTION["testament_preference"],
        )
        st.selectbox(
            "Körülbelül milyen hosszú legyen?",
            options=list(LECTION_LENGTH_PREFERENCES),
            format_func=lambda v: LECTION_LENGTH_PREFERENCE_LABELS_HU.get(
                v, str(v)
            ),
            key=_KEY_LECTION["length_preference"],
        )
        st.caption(
            "Irányadó: rövidebb ≈ 5–9 vers; átlagos ≈ 8–18; hosszabb ≈ 15–30. "
            "A szakasz természetes egysége fontosabb, mint a pontos versszám."
        )

    if st.button("Lekciók javaslata", type="primary", key="sw_lection_mi_suggest"):
        _run_lection_suggest(generate_fn=generate_fn)

    _render_lection_suggestions()

    with st.expander("Már van saját lekcióötletem", expanded=False):
        st.text_input(
            "Lekció igehelye",
            key=_KEY_LECTION["reference"],
            placeholder="Pl. Fil 2,1–16",
        )
        st.text_area(
            "Saját megjegyzés",
            key=_KEY_LECTION["notes"],
            height=70,
            help="Röviden leírhatod, mit szeretnél ezzel a szakasszal hangsúlyozni.",
            placeholder="Opcionális — mit szeretnél hangsúlyozni ezzel a szakasszal?",
        )
        manual_ref = (st.session_state.get(_KEY_LECTION["reference"]) or "").strip()
        if manual_ref:
            validation = validate_lection_reference(manual_ref)
            if validation.get("ok"):
                if st.button(
                    "RÚF-szöveg betöltése a megadott igehelyhez",
                    key="sw_lection_manual_ruf",
                ):
                    _request_lection_ruf_load(manual_ref)
            else:
                st.caption(
                    str(validation.get("error") or "Az igehely nem érvényesíthető.")
                )
        if st.button("Saját lekció értékelése", key="sw_lection_mi_assess"):
            _run_lection_assess(generate_fn=generate_fn)
        _render_lection_assessment()

    _render_lection_ruf_confirm()
    _render_lection_selected_summary()
    _render_lection_textus_link_card(generate_fn=generate_fn)
    _render_lection_connection_details_editor()

    st.markdown("---")
    _render_lection_reader()
    _render_lection_save_approve()


def _request_adopt_prayer(payload: dict[str, Any]) -> None:
    st.session_state[_ADOPT_PRAYER_PENDING] = dict(payload or {})
    st.rerun()


def _collect_prayer_kwargs() -> dict[str, Any]:
    """Imádsági MI-bemenet: központi anyaggyűjtő + élő imamezők.

    Ugyanazt a forrásanyag-gyűjtőt használja, mint a vázlatgenerálás.
    """
    base = _collect_closing_kwargs()
    live = _read_prayer_from_widgets()
    base["tone_preference"] = live.get("tone_preference") or "mixed"
    base["general_focus"] = live.get("general_focus") or ""
    base["rewrite_mode"] = live.get("rewrite_mode") or "integrate_into_arc"
    base["prayer_before"] = live.get("before") or {}
    base["prayer_after"] = live.get("after") or {}

    sw = ensure_sermon_workshop_state(st.session_state)
    bundle = collect_available_sermon_material(
        st.session_state, sermon_workshop=sw
    )
    # Bundle mezők: csak ha a meglévő base üres / hiányzik
    for key in (
        "passage_text",
        "bible_translation",
        "occasion",
        "user_focus",
        "text_main_idea",
        "text_main_idea_status",
        "sermon_main_idea",
        "sermon_main_idea_status",
        "approved_insights",
        "exegesis",
        "theology",
        "human_condition",
        "listener_tension",
        "christ_centered_arc",
        "sermon_path",
        "sermon_movements",
        "selected_images",
        "illustrations",
        "applications",
        "closing",
    ):
        if key not in bundle:
            continue
        cur = base.get(key)
        empty = cur in (None, "", [], {})
        if empty:
            base[key] = bundle[key]
        elif key.endswith("_status") and not str(cur or "").strip():
            base[key] = bundle[key]

    if not str(base.get("passage") or "").strip():
        passage = str(bundle.get("passage_reference") or "").strip()
        if passage:
            base["passage"] = passage

    outline = normalize_sermon_outline(sw.get("sermon_outline"))
    has_outline = outline_has_content(outline)
    if has_outline:
        base["sermon_outline"] = outline
        if str(outline.get("main_idea") or "").strip():
            if not str(base.get("sermon_main_idea") or "").strip():
                base["sermon_main_idea"] = str(outline.get("main_idea") or "").strip()
                base["sermon_main_idea_status"] = (
                    str(sw.get("sermon_outline_status") or "draft").strip()
                    or "draft"
                )
            if not str(base.get("text_main_idea") or "").strip():
                base["text_main_idea"] = str(outline.get("main_idea") or "").strip()

    source_keys = list(bundle.get("source_keys") or [])
    if has_outline and "sermon_outline" not in source_keys:
        source_keys.append("sermon_outline")
    before = base.get("prayer_before") if isinstance(base.get("prayer_before"), dict) else {}
    after = base.get("prayer_after") if isinstance(base.get("prayer_after"), dict) else {}
    if str(before.get("own_thoughts") or "").strip() and "prayer_before" not in source_keys:
        # Korábban elmentett imádsági gondolatok is forrás lehetnek
        source_keys.append("prayer_before")
    if str(after.get("own_thoughts") or "").strip() and "prayer_after" not in source_keys:
        source_keys.append("prayer_after")
    base["source_keys"] = list(dict.fromkeys(source_keys))
    return base


def _prayer_plan_fingerprint(side_data: dict[str, Any]) -> str:
    lines = side_data.get("selected_lines")
    if isinstance(lines, list):
        norm_lines = [str(x).strip() for x in lines if str(x).strip()]
    else:
        norm_lines = [
            ln.strip()
            for ln in str(lines or "").replace("\r\n", "\n").split("\n")
            if ln.strip()
        ]
    payload = {
        "o": str(side_data.get("selected_opening") or "").strip(),
        "l": norm_lines,
        "c": str(side_data.get("closing_direction") or "").strip(),
        "m": str(side_data.get("movement_notes") or "").strip(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _prayer_baseline_key(side: str) -> str:
    return f"{_PRAYER_BASELINE_PREFIX}{side}"


def _prayer_confirm_key(side: str) -> str:
    return f"{_PRAYER_CONFIRM_PREFIX}{side}"


def _prayer_side_key_map(side: str) -> dict[str, str]:
    return _KEY_PRAYER_BEFORE if side != "after" else _KEY_PRAYER_AFTER


def _prayer_plan_is_edited(side: str) -> bool:
    """Van-e kézzel módosított / megtartott imaív, amit újragenerálás felülírna."""
    key_map = _prayer_side_key_map(side)
    live = _read_prayer_side_from_widgets(key_map)
    if not _prayer_side_has_retained_plan(live):
        return False
    baseline = st.session_state.get(_prayer_baseline_key(side))
    if not baseline:
        return True
    return _prayer_plan_fingerprint(live) != str(baseline)


def _apply_prayer_suggestion_to_plan(data: dict[str, Any], *, side: str) -> None:
    """Javaslat → azonnal szerkeszthető tartós mezők (nem jóváhagyott)."""
    payload = _build_prayer_adopt_payload(data, side=side)
    keys = _prayer_side_key_map(side)
    if payload.get("purpose"):
        st.session_state[keys["purpose"]] = str(payload["purpose"]).strip()
    if payload.get("movement_notes"):
        st.session_state[keys["movement_notes"]] = str(payload["movement_notes"]).strip()
    if payload.get("selected_opening"):
        st.session_state[keys["selected_opening"]] = str(
            payload["selected_opening"]
        ).strip()
    if payload.get("closing_direction"):
        st.session_state[keys["closing_direction"]] = str(
            payload["closing_direction"]
        ).strip()
    if payload.get("selected_lines") is not None:
        lines = payload.get("selected_lines")
        if isinstance(lines, list):
            st.session_state[keys["selected_lines"]] = "\n".join(
                str(x).strip() for x in lines if str(x).strip()
            )
        else:
            st.session_state[keys["selected_lines"]] = str(lines or "").strip()
    _persist_prayer_from_widgets()
    live = _read_prayer_side_from_widgets(keys)
    st.session_state[_prayer_baseline_key(side)] = _prayer_plan_fingerprint(live)
    st.session_state[f"{_PRAYER_EXPAND_PLAN_PREFIX}{side}"] = True


def _queue_prayer_suggest(
    *,
    side: str,
    mode: str = "quick",
    force: bool = False,
) -> None:
    """Gyors / saját szempontos javaslat indítása; szerkesztett ívnél megerősítés."""
    if not force and _prayer_plan_is_edited(side):
        st.session_state[_prayer_confirm_key(side)] = {"mode": mode}
        return
    st.session_state.pop(_prayer_confirm_key(side), None)
    st.session_state[_PENDING_PRAYER_SUGGEST] = {
        "side": side,
        "mode": mode,
    }
    st.rerun()


def _run_prayer_suggest_for_side(
    *,
    side: str,
    mode: str = "quick",
    generate_fn: GenerateFn | None,
) -> None:
    _persist_prayer_from_widgets()
    kwargs = _collect_prayer_kwargs()
    # Gyors mód: nem követel saját szempontot; üres textarea = gyors mód
    live = kwargs.get("prayer_before") if side != "after" else kwargs.get("prayer_after")
    live = live if isinstance(live, dict) else {}
    own = str(live.get("own_thoughts") or "").strip()
    if mode == "quick":
        # Az eddigi munka az elsődleges; saját szempont opcionális kiegészítés
        pass
    elif mode == "refine" and not own:
        st.info(
            "A finomításhoz írd be a saját szempontokat a szövegmezőbe, "
            "majd indítsd újra."
        )
        return

    caption, sparse = build_prayer_source_caption(
        source_keys=kwargs.get("source_keys"),
        has_outline=outline_has_content(kwargs.get("sermon_outline")),
    )
    with st.spinner("Imaív készül…"):
        if side != "after":
            result = suggest_prayer_before(**kwargs, generate_fn=generate_fn)
            save_fn = save_prayer_before_suggestions
            success_msg = "Előtti imaív javaslat elkészült."
        else:
            result = suggest_prayer_after(**kwargs, generate_fn=generate_fn)
            save_fn = save_prayer_after_suggestions
            success_msg = "Utáni imaív javaslat elkészült."

        payload = result.to_dict()
        if not payload.get("source_caption"):
            payload["source_caption"] = caption
            payload["sparse_sources"] = sparse
        elif sparse and not payload.get("sparse_sources"):
            payload["sparse_sources"] = True
        # Generált tartalom soha ne legyen automatikusan jóváhagyott
        payload["status"] = "draft"
        save_fn(st.session_state, payload)

        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült.",
                )
            )
            return

        if result.missing_information and not (
            result.recommended_movements or result.suggested_lines
        ):
            st.warning(
                "Kevés előkészítő anyag áll rendelkezésre. "
                "Hiányzik: " + "; ".join(result.missing_information)
            )
            return

        _apply_prayer_suggestion_to_plan(payload, side=side)
        st.session_state[f"_sw_prayer_flash_{side}"] = success_msg
        st.rerun()


def _run_prayer_before_suggest(*, generate_fn: GenerateFn | None) -> None:
    _run_prayer_suggest_for_side(
        side="before", mode="criteria", generate_fn=generate_fn
    )


def _run_prayer_after_suggest(*, generate_fn: GenerateFn | None) -> None:
    _run_prayer_suggest_for_side(
        side="after", mode="criteria", generate_fn=generate_fn
    )


def _run_prayer_assess(*, generate_fn: GenerateFn | None) -> None:
    _persist_prayer_from_widgets()
    with st.spinner("Imádsági terv értékelése…"):
        kwargs = _collect_prayer_kwargs()
        result = assess_prayer_preparation(**kwargs, generate_fn=generate_fn)
        save_prayer_assessment(st.session_state, result.to_dict())
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült.",
                )
            )
        else:
            st.success("Értékelés elkészült.")


_PRAYER_BEFORE_OWN_HELP = (
    "Röviden leírhatod, mit szeretnél kérni vagy hangsúlyozni. Töredékesen "
    "is írható. Ha üresen hagyod, az MI a textus és az eddigi munka alapján "
    "javasol imaívet."
)
_PRAYER_BEFORE_OWN_PLACEHOLDER = (
    "Csendesedjünk el Isten előtt; kérjük a Szentlélek világosságát; ne "
    "csak másokra gondoljunk az Ige hallgatása közben."
)
_PRAYER_AFTER_OWN_HELP = (
    "Röviden leírhatod, mire szeretnél válaszolni hálaadással, "
    "bűnvallással, kéréssel vagy közbenjárással. Ha üresen hagyod, az MI az "
    "eddigi igehirdetési munka alapján javasol."
)
_PRAYER_AFTER_OWN_PLACEHOLDER = (
    "Hála Isten megtartó kegyelméért; imádság a hitükben elfáradtakért; "
    "kérés, hogy a gyülekezet egymást is erősítse."
)
_PRAYER_QUICK_HELP = (
    "Az MI az eddigi textusfeldolgozás és igehirdetési munka alapján állít össze "
    "egy szerkeszthető imaívet. Nem szükséges további szempontokat megadnod."
)


def _prayer_side_has_retained_plan(side: dict[str, Any]) -> bool:
    return bool(
        side.get("selected_opening")
        or side.get("selected_lines")
        or side.get("closing_direction")
        or side.get("purpose")
        or side.get("movement_notes")
    )


def _prayer_side_has_any_content(side: dict[str, Any]) -> bool:
    return _prayer_side_has_retained_plan(side) or bool(side.get("own_thoughts"))


def _build_prayer_adopt_payload(
    data: dict[str, Any],
    *,
    side: str,
) -> dict[str, Any]:
    """Egyetlen átvétel: nyitó + 4–6 ívpont + záró → tartós mezők."""
    simple = adapt_prayer_suggestion_for_ui(data)
    opening = str(simple.get("opening_line") or "").strip()
    closing = str(simple.get("closing_line") or "").strip()
    arc = (
        simple.get("prayer_arc")
        if isinstance(simple.get("prayer_arc"), list)
        else []
    )
    lines: list[str] = []
    notes: list[str] = []
    for item in arc:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        thought = str(item.get("thought") or "").strip()
        if thought:
            lines.append(thought)
        if title and thought:
            notes.append(f"{title}: {thought}")
        elif thought:
            notes.append(thought)
        elif title:
            notes.append(title)
    purpose = str(data.get("purpose") or "").strip()
    payload: dict[str, Any] = {"side": side}
    if opening:
        payload["selected_opening"] = opening
    if lines:
        payload["selected_lines"] = lines
    if closing:
        payload["closing_direction"] = closing
    if notes:
        payload["movement_notes"] = "\n".join(notes)
    if purpose:
        payload["purpose"] = purpose
    return payload


def _save_prayer_as_draft() -> None:
    block = _read_prayer_from_widgets()
    before = block.get("before") if isinstance(block.get("before"), dict) else {}
    after = block.get("after") if isinstance(block.get("after"), dict) else {}
    filled = (
        _prayer_side_has_any_content(before)
        or _prayer_side_has_any_content(after)
        or bool(block.get("general_focus"))
    )
    if not filled:
        st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
        return
    block["status"] = "draft"
    update_sermon_workshop_section(st.session_state, "prayer_preparation", block)
    _toast_and_rerun("Vázlatként elmentve.")


def _approve_prayer_and_handoff() -> None:
    block = _read_prayer_from_widgets()
    before = block.get("before") if isinstance(block.get("before"), dict) else {}
    after = block.get("after") if isinstance(block.get("after"), dict) else {}
    if not (
        _prayer_side_has_retained_plan(before)
        or _prayer_side_has_retained_plan(after)
        or before.get("own_thoughts")
        or after.get("own_thoughts")
    ):
        st.warning(
            "Jóváhagyáshoz legyen legalább saját gondolat vagy "
            "átvett imaív (előtti vagy utáni)."
        )
        return
    before["status"] = "approved"
    after["status"] = "approved"
    block["before"] = before
    block["after"] = after
    block["status"] = "approved"
    update_sermon_workshop_section(st.session_state, "prayer_preparation", block)
    decisions = [
        (
            "tone",
            "Imádsági hangoltság",
            prayer_tone_preference_label(block.get("tone_preference")),
        ),
        (
            "before_opening",
            "Előtti ima nyitó",
            str(before.get("selected_opening") or ""),
        ),
        (
            "after_opening",
            "Utáni ima nyitó",
            str(after.get("selected_opening") or ""),
        ),
        (
            "before_purpose",
            "Előtti ima célja",
            str(before.get("purpose") or ""),
        ),
        (
            "after_purpose",
            "Utáni ima célja",
            str(after.get("purpose") or ""),
        ),
    ]
    added = 0
    skipped = 0
    for _field, category, content in decisions:
        if not content:
            continue
        if _decision_is_duplicate(
            source_section=_SOURCE_PRAYER,
            category=category,
            content=content,
        ):
            skipped += 1
            continue
        add_approved_sermon_decision(
            st.session_state,
            _SOURCE_PRAYER,
            category,
            content,
        )
        added += 1
    if added:
        _toast_and_rerun(f"Jóváhagyva ({added} döntés).")
    elif skipped:
        _toast_and_rerun("Jóváhagyva. Ezek a döntések már szerepelnek.")
    else:
        _toast_and_rerun("Jóváhagyva.")


def _render_prayer_quick_strip(
    *,
    side: str,
    generate_fn: GenerateFn | None,
    busy: bool,
) -> None:
    st.markdown(
        f"""
<div class="tx-prayer-quick">
  <div class="tx-prayer-quick-title">Gyors MI-javaslat</div>
  <p class="tx-prayer-quick-help">{html.escape(_PRAYER_QUICK_HELP)}</p>
</div>
""".strip(),
        unsafe_allow_html=True,
    )
    quick_label = "Imaív készül…" if busy else "Javaslat az eddigi munkából"
    if st.button(
        quick_label,
        key=f"sw_prayer_quick_{side}",
        type="primary",
        icon=":material/auto_awesome:",
        disabled=busy,
        use_container_width=True,
    ):
        _queue_prayer_suggest(side=side, mode="quick")
    st.markdown(
        '<p class="tx-prayer-or">vagy adj meg saját szempontokat</p>',
        unsafe_allow_html=True,
    )


def _render_prayer_overwrite_confirm(
    *,
    side: str,
    generate_fn: GenerateFn | None,
) -> None:
    pending = st.session_state.get(_prayer_confirm_key(side))
    if not isinstance(pending, dict):
        return
    mode = str(pending.get("mode") or "quick")
    st.warning(
        "Az imaív kézzel szerkesztve van. Az új javaslat felülírja a "
        "módosításokat — erősítsd meg, vagy mentsd el előbb."
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Felülírom az új változattal",
            key=f"sw_prayer_overwrite_yes_{side}",
            type="primary",
        ):
            st.session_state.pop(_prayer_confirm_key(side), None)
            _queue_prayer_suggest(side=side, mode=mode, force=True)
    with c2:
        if st.button("Mégse", key=f"sw_prayer_overwrite_no_{side}"):
            st.session_state.pop(_prayer_confirm_key(side), None)
            st.rerun()


def _render_prayer_own_thoughts_field(
    *,
    title: str,
    key_map: dict[str, str],
    help_text: str,
    placeholder: str,
) -> None:
    st.markdown(f"**{title}**")
    st.caption(help_text)
    st.text_area(
        title,
        key=key_map["own_thoughts"],
        height=110,
        placeholder=placeholder,
        label_visibility="collapsed",
    )


def _render_prayer_plan_details(
    *,
    side: str,
    key_map: dict[str, str],
    side_data: dict[str, Any],
) -> None:
    """Átvétel / javaslat után szerkeszthető részletek."""
    if not _prayer_side_has_retained_plan(side_data):
        return
    expanded = bool(st.session_state.get(f"{_PRAYER_EXPAND_PLAN_PREFIX}{side}"))
    with st.expander("Szerkeszthető imaív", expanded=expanded):
        st.text_area(
            "Nyitó mondat",
            key=key_map["selected_opening"],
            height=60,
        )
        st.text_area(
            "Fontos imádsági gondolatok (soronként)",
            key=key_map["selected_lines"],
            height=120,
        )
        st.text_area(
            "Záró mondat",
            key=key_map["closing_direction"],
            height=60,
        )
        st.caption(
            "A cél és az imaív a háttérben megmarad a kompatibilitás miatt."
        )
        st.text_area(
            "Imaív (rövid)",
            key=key_map["movement_notes"],
            height=80,
        )
        st.text_area(
            "Cél (opcionális)",
            key=key_map["purpose"],
            height=60,
        )


def _render_prayer_simple_result(
    data: dict[str, Any] | None,
    *,
    side: str,
    heading: str,
    generate_fn: GenerateFn | None = None,
    busy: bool = False,
) -> None:
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not (
        data.get("recommended_movements") or data.get("suggested_lines")
    ):
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return

    simple = adapt_prayer_suggestion_for_ui(data)
    opening = str(simple.get("opening_line") or "").strip()
    closing = str(simple.get("closing_line") or "").strip()
    arc = (
        simple.get("prayer_arc")
        if isinstance(simple.get("prayer_arc"), list)
        else []
    )
    brief_warning = str(simple.get("brief_warning") or "").strip()
    if not (opening or arc or closing):
        missing = (
            data.get("missing_information")
            if isinstance(data.get("missing_information"), list)
            else []
        )
        if missing:
            st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))
        return

    source_caption = str(data.get("source_caption") or "").strip()
    if not source_caption:
        source_caption, sparse_guess = build_prayer_source_caption(
            source_keys=data.get("source_keys"),
            has_outline=False,
        )
    else:
        sparse_guess = bool(data.get("sparse_sources"))
    sparse = bool(data.get("sparse_sources")) or sparse_guess or (
        "általánosabb" in source_caption.casefold()
    )
    if source_caption:
        if sparse:
            st.info(source_caption)
        else:
            st.caption(source_caption)

    st.markdown(f"**{heading}**")
    # Egy tompított kártya — nyitó / ív / záró
    card_parts: list[str] = []
    if opening:
        card_parts.append(f"**Nyitó mondat**\n\n{opening}")
    if arc:
        arc_lines = ["**Javasolt imaív**"]
        for item in arc:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            thought = str(item.get("thought") or "").strip()
            if not (title or thought):
                continue
            if title:
                arc_lines.append(f"**{title}**")
            if thought:
                arc_lines.append(thought)
            arc_lines.append("")
        card_parts.append("\n".join(arc_lines).rstrip())
    if closing:
        card_parts.append(f"**Záró mondat**\n\n{closing}")
    st.markdown("\n\n---\n\n".join(card_parts))

    integrated = (
        data.get("integrated_user_thoughts")
        if isinstance(data.get("integrated_user_thoughts"), list)
        else []
    )
    if integrated:
        st.caption("A javaslat beépíti a saját gondolataidat is.")

    if brief_warning:
        st.warning(brief_warning)

    a1, a2 = st.columns(2)
    with a1:
        if st.button(
            "Másik változat",
            key=f"sw_prayer_{side}_another",
            disabled=busy,
            use_container_width=True,
        ):
            _queue_prayer_suggest(side=side, mode="quick")
    with a2:
        if st.button(
            "Finomítás saját szempontokkal",
            key=f"sw_prayer_{side}_refine",
            disabled=busy,
            use_container_width=True,
        ):
            _queue_prayer_suggest(side=side, mode="refine")
    b1, b2 = st.columns(2)
    with b1:
        if st.button(
            "Mentés vázlatként",
            key=f"sw_prayer_{side}_save_draft",
            disabled=busy,
            use_container_width=True,
        ):
            _save_prayer_as_draft()
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            key=f"sw_prayer_{side}_approve",
            type="primary",
            disabled=busy,
            use_container_width=True,
        ):
            _approve_prayer_and_handoff()

    with st.expander("Mi alapján készült?", expanded=False):
        st.caption(
            "Az imaív a textushoz és a műhelyanyaghoz kötődik; "
            "nem teljes imádság. Angol funkciókódok csak a háttérben vannak."
        )
        purpose = str(data.get("purpose") or "").strip()
        if purpose:
            st.caption(f"Irány: {purpose}")
        missing = (
            data.get("missing_information")
            if isinstance(data.get("missing_information"), list)
            else []
        )
        if missing:
            st.caption("Hiányzó: " + "; ".join(str(x) for x in missing if x))

    with st.expander("Részletes megjegyzések", expanded=False):
        notes = (
            data.get("language_notes")
            if isinstance(data.get("language_notes"), list)
            else []
        )
        cliches = (
            data.get("cliche_risks")
            if isinstance(data.get("cliche_risks"), list)
            else []
        )
        if notes:
            st.markdown("**Nyelvi megjegyzések**")
            for n in notes:
                if str(n).strip():
                    st.caption(f"• {n}")
        if cliches:
            st.markdown("**Sablonossági jelzések**")
            for c in cliches:
                if str(c).strip():
                    st.caption(f"• {c}")
        if integrated:
            st.markdown("**Saját gondolatok beépítése**")
            for item in integrated:
                if not isinstance(item, dict):
                    continue
                original = str(item.get("original") or "").strip()
                refined = str(item.get("refined") or "").strip()
                placement = str(item.get("placement") or "").strip()
                if refined:
                    st.caption(f"• {refined}")
                if original and original != refined:
                    st.caption(f"  Eredeti: {original}")
                if placement and placement not in (
                    "address",
                    "silence",
                    "confession",
                    "illumination",
                    "preacher",
                    "hearers",
                    "surrender",
                    "gratitude",
                    "gospel_trust",
                    "request",
                    "intercession",
                    "response",
                    "hope",
                ):
                    st.caption(f"  Hely: {placement}")
        if not (notes or cliches or integrated):
            st.caption("Nincs további részletes megjegyzés.")


def _render_prayer_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    data = prep.get("assessment")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not str(data.get("overall_assessment") or "").strip():
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and not data.get("strengths"):
        return
    with st.expander("Imádsági terv értékelése", expanded=False):
        if overall:
            st.write(overall)
        before_a = str(data.get("before_assessment") or "").strip()
        after_a = str(data.get("after_assessment") or "").strip()
        if before_a:
            st.markdown(f"**Előtti:** {before_a}")
        if after_a:
            st.markdown(f"**Utáni:** {after_a}")
        for label, key in (
            ("Erősségek", "strengths"),
            ("Javítási lehetőségek", "improvements"),
        ):
            items = data.get(key) if isinstance(data.get(key), list) else []
            if items:
                st.markdown(f"**{label}**")
                for item in items:
                    if str(item).strip():
                        st.caption(f"• {item}")
        cliches = (
            data.get("cliche_findings")
            if isinstance(data.get("cliche_findings"), list)
            else []
        )
        if cliches:
            with st.expander("Sablonossági részletek", expanded=False):
                for item in cliches:
                    if str(item).strip():
                        st.caption(f"• {item}")


def _render_prayer_side_block(
    *,
    side: str,
    key_map: dict[str, str],
    own_title: str,
    help_text: str,
    placeholder: str,
    result_heading: str,
    generate_fn: GenerateFn | None,
) -> None:
    side_key = "before" if side != "after" else "after"
    suggestions_key = (
        "before_suggestions" if side != "after" else "after_suggestions"
    )

    pending = st.session_state.get(_PENDING_PRAYER_SUGGEST)
    busy = (
        isinstance(pending, dict)
        and str(pending.get("side") or "") == side_key
    )
    if busy:
        queued = st.session_state.pop(_PENDING_PRAYER_SUGGEST, None)
        mode = str((queued or {}).get("mode") or "quick")
        _run_prayer_suggest_for_side(
            side=side_key, mode=mode, generate_fn=generate_fn
        )

    flash_key = f"_sw_prayer_flash_{side_key}"
    flash = st.session_state.pop(flash_key, None)
    if flash:
        st.success(str(flash))

    st.markdown(f"**{own_title}**")
    _render_prayer_quick_strip(
        side=side_key, generate_fn=generate_fn, busy=busy
    )
    _render_prayer_overwrite_confirm(side=side_key, generate_fn=generate_fn)

    st.caption(help_text)
    st.text_area(
        own_title,
        key=key_map["own_thoughts"],
        height=110,
        placeholder=placeholder,
        label_visibility="collapsed",
    )
    criteria_label = "Imaív készül…" if busy else "Javaslat saját szempontokkal"
    if st.button(
        criteria_label,
        key=f"sw_prayer_mi_{side_key}",
        disabled=busy,
        use_container_width=True,
    ):
        # Üres textarea → ugyanaz a gyors folyamat
        own = str(st.session_state.get(key_map["own_thoughts"]) or "").strip()
        _queue_prayer_suggest(
            side=side_key,
            mode="criteria" if own else "quick",
        )

    prep = ensure_sermon_workshop_state(st.session_state).get("prayer_preparation")
    prep = prep if isinstance(prep, dict) else {}
    sug = prep.get(suggestions_key)
    _render_prayer_simple_result(
        sug if isinstance(sug, dict) else None,
        side=side_key,
        heading=result_heading,
        generate_fn=generate_fn,
        busy=busy,
    )
    live = _read_prayer_side_from_widgets(key_map)
    side_data = (
        prep.get(side_key) if isinstance(prep.get(side_key), dict) else {}
    )
    _render_prayer_plan_details(
        side=side_key,
        key_map=key_map,
        side_data=live if _prayer_side_has_retained_plan(live) else side_data,
    )


def render_prayer_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Imádsági előkészítés — egyszerű saját gondolat + MI imaív."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Imádsági előkészítés")
    st.markdown(
        "Kérhetsz gyors MI-javaslatot az eddigi munkából, vagy megadhatsz "
        "saját szempontokat. Az MI egy nyitó mondatot, 4–6 pontból álló "
        "imaívet és egy záró mondatot javasol. Teljes imádság nem készül — "
        "az előtti és utáni ima külön marad."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    prep = (
        sw.get("prayer_preparation")
        if isinstance(sw.get("prayer_preparation"), dict)
        else {}
    )
    status = str(prep.get("status") or "draft").strip()
    st.caption(f"Állapot: {_STATUS_LABELS.get(status, status)}")

    before_tab, after_tab = st.tabs(
        ["Igehirdetés előtti imádság", "Igehirdetés utáni imádság"]
    )
    with before_tab:
        _render_prayer_side_block(
            side="before",
            key_map=_KEY_PRAYER_BEFORE,
            own_title="Saját gondolataim az igehirdetés előtti imádsághoz",
            help_text=_PRAYER_BEFORE_OWN_HELP,
            placeholder=_PRAYER_BEFORE_OWN_PLACEHOLDER,
            result_heading="MI-javaslat — igehirdetés előtti imádság",
            generate_fn=generate_fn,
        )
    with after_tab:
        _render_prayer_side_block(
            side="after",
            key_map=_KEY_PRAYER_AFTER,
            own_title="Saját gondolataim az igehirdetés utáni imádsághoz",
            help_text=_PRAYER_AFTER_OWN_HELP,
            placeholder=_PRAYER_AFTER_OWN_PLACEHOLDER,
            result_heading="MI-javaslat — igehirdetés utáni imádság",
            generate_fn=generate_fn,
        )

    with st.expander("További beállítások", expanded=False):
        tone_options = list(PRAYER_TONE_UI_OPTIONS)
        current_tone = normalize_prayer_tone_preference(
            st.session_state.get(_KEY_PRAYER_COMMON["tone_preference"])
        )
        if current_tone not in tone_options and current_tone in PRAYER_TONE_PREFERENCES:
            tone_options = tone_options + [current_tone]
        st.selectbox(
            "Imádsági hangoltság",
            options=tone_options,
            format_func=lambda v: PRAYER_TONE_PREFERENCE_LABELS_HU.get(v, str(v)),
            key=_KEY_PRAYER_COMMON["tone_preference"],
            help="Alapból az MI választ a textushoz illő hangot.",
        )
        st.selectbox(
            "Saját gondolatok átalakítási módja",
            options=list(PRAYER_REWRITE_MODES),
            format_func=lambda v: PRAYER_REWRITE_MODE_LABELS_HU.get(v, str(v)),
            key=_KEY_PRAYER_COMMON["rewrite_mode"],
        )
        st.caption(
            "Az imaív javaslata automatikusan beépíti a saját gondolatokat "
            "a választott mód szerint."
        )
        st.markdown("**Külön hangsúly**")
        st.caption(
            "Van-e külön gyülekezeti, liturgiai vagy lelkipásztori hangsúly?"
        )
        st.text_area(
            "Külön hangsúly",
            key=_KEY_PRAYER_COMMON["general_focus"],
            height=70,
            label_visibility="collapsed",
        )
        if st.button("Imádsági terv értékelése", key="sw_prayer_mi_assess"):
            _run_prayer_assess(generate_fn=generate_fn)

    _render_prayer_assessment()

    st.markdown("---")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_prayer_save_draft"):
            _save_prayer_as_draft()
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            type="primary",
            key="sw_prayer_approve",
        ):
            _approve_prayer_and_handoff()

    _render_decisions_for_section(_SOURCE_PRAYER)


def _request_adopt_closing_block(block: dict[str, str]) -> None:
    st.session_state[_ADOPT_CL_PENDING] = dict(block or {})
    st.rerun()


def _closing_suggestion_payload(result: ClosingSuggestionResult) -> dict[str, Any]:
    return result.to_dict()


def _closing_assessment_payload(result: ClosingAssessmentResult) -> dict[str, Any]:
    return result.to_dict()


def _run_closing_suggest(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Lezárási irány javaslata készül…"):
        kwargs = _collect_closing_kwargs()
        kwargs.pop("closing", None)
        result = suggest_closing(**kwargs, generate_fn=generate_fn)
        save_closing_suggestions(
            st.session_state, _closing_suggestion_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült.",
                )
            )
        elif result.missing_information and not (
            result.recommended_final_insight or result.recommended_gospel_assurance
        ):
            st.warning(
                "Nincs elegendő adat a felelős javaslathoz. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Javaslat elkészült.")


def _run_closing_assess(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Saját lezárási terv értékelése…"):
        kwargs = _collect_closing_kwargs()
        result = assess_closing(**kwargs, generate_fn=generate_fn)
        save_closing_assessment(
            st.session_state, _closing_assessment_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült.",
                )
            )
        else:
            st.success("Értékelés elkészült.")


def _enrichment_suggestion_payload(result: EnrichmentSuggestionResult) -> dict[str, Any]:
    return result.to_dict()


def _enrichment_assessment_payload(result: EnrichmentAssessmentResult) -> dict[str, Any]:
    return result.to_dict()


def _run_enrichment_suggest(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Képek és alkalmazások javaslata készül…"):
        kwargs = _collect_enrichment_kwargs()
        result = suggest_enrichment(**kwargs, generate_fn=generate_fn)
        save_sermon_enrichment_suggestions(
            st.session_state, _enrichment_suggestion_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült.",
                )
            )
        elif result.missing_information and not (
            result.recommended_textual_images
            or result.recommended_illustrations
            or result.recommended_applications
        ):
            st.warning(
                "Nincs elegendő adat a felelős javaslathoz. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Javaslat elkészült.")


def _run_enrichment_assess(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Saját terv értékelése…"):
        kwargs = _collect_enrichment_kwargs()
        result = assess_enrichment(**kwargs, generate_fn=generate_fn)
        save_sermon_enrichment_assessment(
            st.session_state, _enrichment_assessment_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült.",
                )
            )
        else:
            st.success("Értékelés elkészült.")


def _render_placement_and_movement(
    *,
    prefix: str,
    item_id: str,
    placement_key: str,
    movement_key: str,
) -> None:
    st.selectbox(
        "Elhelyezés",
        options=list(PLACEMENT_KINDS),
        format_func=lambda v: PLACEMENT_KIND_LABELS_HU.get(v, str(v)),
        key=placement_key,
    )
    placement = normalize_placement_kind(st.session_state.get(placement_key))
    mv_options = _movement_options()
    mv_ids = [mid for mid, _label in mv_options if mid]
    if placement == "movement" and mv_ids:
        current_mid = str(st.session_state.get(movement_key) or "")
        if current_mid not in mv_ids:
            st.session_state[movement_key] = mv_ids[0]
        st.selectbox(
            "Kapcsolódó mozgás",
            options=mv_ids,
            format_func=lambda mid: next(
                (label for oid, label in mv_options if oid == mid), mid
            ),
            key=movement_key,
        )
    elif movement_key in st.session_state:
        st.session_state[movement_key] = ""


def _render_reorder_delete_bar(
    *,
    kind: str,
    item_id: str,
    index: int,
    total: int,
    list_key: str,
    delete_pending_key: str,
    delete_prefix: str,
) -> None:
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Feljebb", key=f"{delete_prefix}_up_{item_id}", disabled=index <= 0):
            _persist_enrichment_from_widgets()
            sw = ensure_sermon_workshop_state(st.session_state)
            if kind == "images":
                items = normalize_textual_images(sw.get("selected_images"))
            elif kind == "illustrations":
                items = normalize_illustrations(sw.get("illustrations"))
            else:
                items = normalize_applications(sw.get("applications"))
            if index > 0 and index < len(items):
                items[index - 1], items[index] = items[index], items[index - 1]
                update_sermon_workshop_section(st.session_state, list_key, items)
                st.session_state[_RESYNC_FLAG] = True
                st.rerun()
    with c2:
        if st.button(
            "Lejjebb",
            key=f"{delete_prefix}_down_{item_id}",
            disabled=index >= total - 1,
        ):
            _persist_enrichment_from_widgets()
            sw = ensure_sermon_workshop_state(st.session_state)
            if kind == "images":
                items = normalize_textual_images(sw.get("selected_images"))
            elif kind == "illustrations":
                items = normalize_illustrations(sw.get("illustrations"))
            else:
                items = normalize_applications(sw.get("applications"))
            if index < len(items) - 1:
                items[index + 1], items[index] = items[index], items[index + 1]
                update_sermon_workshop_section(st.session_state, list_key, items)
                st.session_state[_RESYNC_FLAG] = True
                st.rerun()
    with c3:
        pending = st.session_state.get(delete_pending_key)
        if pending == item_id:
            if st.button(
                "Igen, törlés",
                key=f"{delete_prefix}_del_yes_{item_id}",
                type="primary",
            ):
                _persist_enrichment_from_widgets()
                sw = ensure_sermon_workshop_state(st.session_state)
                if kind == "images":
                    items = [
                        x
                        for x in normalize_textual_images(sw.get("selected_images"))
                        if str(x.get("id") or "") != item_id
                    ]
                    update_sermon_workshop_section(
                        st.session_state, "selected_images", items
                    )
                    _clear_enrichment_widgets("images")
                elif kind == "illustrations":
                    items = [
                        x
                        for x in normalize_illustrations(sw.get("illustrations"))
                        if str(x.get("id") or "") != item_id
                    ]
                    update_sermon_workshop_section(
                        st.session_state, "illustrations", items
                    )
                    _clear_enrichment_widgets("illustrations")
                else:
                    items = [
                        x
                        for x in normalize_applications(sw.get("applications"))
                        if str(x.get("id") or "") != item_id
                    ]
                    update_sermon_workshop_section(
                        st.session_state, "applications", items
                    )
                    _clear_enrichment_widgets("applications")
                st.session_state.pop(delete_pending_key, None)
                st.session_state[_RESYNC_FLAG] = True
                st.rerun()
            if st.button("Mégse", key=f"{delete_prefix}_del_no_{item_id}"):
                st.session_state.pop(delete_pending_key, None)
                st.rerun()
        elif st.button("Törlés", key=f"{delete_prefix}_del_{item_id}"):
            st.session_state[delete_pending_key] = item_id
            st.rerun()


def _render_textual_image_editor(item: dict[str, str], *, index: int, total: int) -> None:
    iid = str(item.get("id") or "")
    preview = (
        st.session_state.get(_en_widget_key(_IMG_WIDGET_PREFIX, iid, "image"))
        or item.get("image")
        or ""
    ).strip() or f"Kép {index + 1}"
    func = image_function_label(
        st.session_state.get(
            _en_widget_key(_IMG_WIDGET_PREFIX, iid, "homiletical_function")
        )
        or item.get("homiletical_function")
    )
    with st.expander(f"{index + 1}. {preview} — {func}", expanded=False):
        st.text_input(
            "Kép vagy motívum",
            key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "image"),
            placeholder="Textusbeli kép, jelenet, motívum…",
        )
        st.text_area(
            "Textusbeli alap",
            key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "textual_basis"),
            height=70,
        )
        st.selectbox(
            "Homiletikai funkció",
            options=list(IMAGE_FUNCTIONS),
            format_func=lambda v: IMAGE_FUNCTION_LABELS_HU.get(v, str(v)),
            key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "homiletical_function"),
        )
        _render_placement_and_movement(
            prefix=_IMG_WIDGET_PREFIX,
            item_id=iid,
            placement_key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "placement"),
            movement_key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "movement_id"),
        )
        st.text_area(
            "Kibontási jegyzet",
            key=_en_widget_key(_IMG_WIDGET_PREFIX, iid, "development_notes"),
            height=70,
        )
        _render_reorder_delete_bar(
            kind="images",
            item_id=iid,
            index=index,
            total=total,
            list_key="selected_images",
            delete_pending_key=_EN_IMG_DELETE_PENDING,
            delete_prefix="sw_en_img",
        )


def _render_illustration_editor(item: dict[str, str], *, index: int, total: int) -> None:
    iid = str(item.get("id") or "")
    preview = (
        st.session_state.get(_en_widget_key(_ILL_WIDGET_PREFIX, iid, "idea"))
        or item.get("idea")
        or ""
    ).strip() or f"Illusztráció {index + 1}"
    func = illustration_function_label(
        st.session_state.get(_en_widget_key(_ILL_WIDGET_PREFIX, iid, "function"))
        or item.get("function")
    )
    with st.expander(f"{index + 1}. {preview} — {func}", expanded=False):
        st.text_area(
            "Illusztrációs ötlet",
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "idea"),
            height=80,
        )
        st.selectbox(
            "Forrás",
            options=list(ILLUSTRATION_SOURCES),
            format_func=lambda v: ILLUSTRATION_SOURCE_LABELS_HU.get(v, str(v)),
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "source"),
        )
        st.selectbox(
            "Funkció",
            options=list(ILLUSTRATION_FUNCTIONS),
            format_func=lambda v: ILLUSTRATION_FUNCTION_LABELS_HU.get(v, str(v)),
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "function"),
        )
        _render_placement_and_movement(
            prefix=_ILL_WIDGET_PREFIX,
            item_id=iid,
            placement_key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "placement"),
            movement_key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "movement_id"),
        )
        st.text_area(
            "Kapcsolódás a textushoz",
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "connection_to_text"),
            height=70,
        )
        st.text_area(
            "Kockázat vagy korlát",
            key=_en_widget_key(_ILL_WIDGET_PREFIX, iid, "risk_or_limit"),
            height=60,
        )
        _render_reorder_delete_bar(
            kind="illustrations",
            item_id=iid,
            index=index,
            total=total,
            list_key="illustrations",
            delete_pending_key=_EN_ILL_DELETE_PENDING,
            delete_prefix="sw_en_ill",
        )


def _render_application_editor(item: dict[str, str], *, index: int, total: int) -> None:
    iid = str(item.get("id") or "")
    preview = (
        st.session_state.get(_en_widget_key(_APP_WIDGET_PREFIX, iid, "application"))
        or item.get("application")
        or ""
    ).strip() or f"Alkalmazás {index + 1}"
    scope = application_scope_label(
        st.session_state.get(_en_widget_key(_APP_WIDGET_PREFIX, iid, "scope"))
        or item.get("scope")
    )
    with st.expander(f"{index + 1}. {preview} — {scope}", expanded=False):
        st.text_area(
            "Alkalmazás",
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "application"),
            height=80,
        )
        st.selectbox(
            "Hatókör",
            options=list(APPLICATION_SCOPES),
            format_func=lambda v: APPLICATION_SCOPE_LABELS_HU.get(v, str(v)),
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "scope"),
        )
        st.text_area(
            "Evangéliumi alap",
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "gospel_basis"),
            height=70,
        )
        st.text_area(
            "Konkrétság",
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "concreteness"),
            height=70,
        )
        _render_placement_and_movement(
            prefix=_APP_WIDGET_PREFIX,
            item_id=iid,
            placement_key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "placement"),
            movement_key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "movement_id"),
        )
        st.text_area(
            "Pásztori óvatosság",
            key=_en_widget_key(_APP_WIDGET_PREFIX, iid, "pastoral_caution"),
            height=60,
        )
        _render_reorder_delete_bar(
            kind="applications",
            item_id=iid,
            index=index,
            total=total,
            list_key="applications",
            delete_pending_key=_EN_APP_DELETE_PENDING,
            delete_prefix="sw_en_app",
        )


def _render_text_workshop_import_panel() -> None:
    import_items = _collect_text_workshop_import_items()
    existing_refs = _existing_source_refs()
    with st.expander("Elem átvétele a Textusműhely / meglévő anyagból", expanded=False):
        if not import_items:
            st.caption(
                "Nincs átvehető illusztráció, aktualizálás vagy jóváhagyott felismerés."
            )
            return
        for idx, entry in enumerate(import_items):
            ref = entry.get("source_ref") or ""
            if ref in existing_refs:
                st.caption(f"✓ Már átvéve: {entry.get('label')}")
                continue
            st.markdown(f"**{entry.get('label')}**")
            st.write(str(entry.get("content") or "")[:500])
            if st.button("Átveszem", key=f"sw_en_import_{idx}"):
                _persist_enrichment_from_widgets()
                sw = ensure_sermon_workshop_state(st.session_state)
                content = str(entry.get("content") or "").strip()
                if entry.get("kind") == "illustration":
                    current = normalize_illustrations(sw.get("illustrations"))
                    if len(current) >= MAX_ILLUSTRATIONS:
                        st.warning(f"Legfeljebb {MAX_ILLUSTRATIONS} illusztráció lehet.")
                    else:
                        item = empty_illustration()
                        item["idea"] = content
                        item["source"] = "text_workshop_import"
                        item["source_ref"] = ref
                        current.append(item)
                        update_sermon_workshop_section(
                            st.session_state, "illustrations", current
                        )
                        st.session_state[_RESYNC_FLAG] = True
                        st.rerun()
                else:
                    current = normalize_applications(sw.get("applications"))
                    if len(current) >= MAX_APPLICATIONS:
                        st.warning(f"Legfeljebb {MAX_APPLICATIONS} alkalmazás lehet.")
                    else:
                        item = empty_application()
                        item["application"] = content
                        item["source_ref"] = ref
                        current.append(item)
                        update_sermon_workshop_section(
                            st.session_state, "applications", current
                        )
                        st.session_state[_RESYNC_FLAG] = True
                        st.rerun()


def _render_enrichment_suggestions() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("sermon_enrichment_suggestions")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not (
        data.get("recommended_textual_images")
        or data.get("recommended_illustrations")
        or data.get("recommended_applications")
    ):
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return

    images = normalize_textual_images(data.get("recommended_textual_images"))
    ills = normalize_illustrations(data.get("recommended_illustrations"))
    apps = normalize_applications(data.get("recommended_applications"))
    expanded = str(data.get("expanded_summary") or "").strip()
    load = str(data.get("load_assessment") or "").strip()
    basis = data.get("basis") if isinstance(data.get("basis"), list) else []
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    missing = (
        data.get("missing_information")
        if isinstance(data.get("missing_information"), list)
        else []
    )
    reasoning = str(data.get("reasoning_summary") or "").strip()

    if not (images or ills or apps or expanded or load):
        if missing:
            st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))
        return

    st.markdown("**MI-javaslat**")
    if images:
        st.markdown("**Textusból fakadó képek**")
        for idx, img in enumerate(images, start=1):
            with st.expander(
                f"{idx}. {img.get('image') or '—'} — "
                f"{image_function_label(img.get('homiletical_function'))}",
                expanded=False,
            ):
                st.write(img.get("textual_basis") or "")
                if st.button(f"Átveszem ezt a képet ({idx})", key=f"sw_mi_en_img_{idx}"):
                    current = _read_textual_images_from_widgets()
                    if len(current) >= MAX_TEXTUAL_IMAGES:
                        st.warning(f"Legfeljebb {MAX_TEXTUAL_IMAGES} kép lehet.")
                    else:
                        new_item = empty_textual_image()
                        for field in _IMG_FIELDS:
                            if field != "id":
                                new_item[field] = str(img.get(field) or "")
                        new_item["homiletical_function"] = normalize_image_function(
                            img.get("homiletical_function")
                        )
                        new_item["placement"] = normalize_placement_kind(
                            img.get("placement")
                        )
                        current.append(new_item)
                        _request_adopt_enrichment_images(current)

    if ills:
        st.markdown("**Illusztrációk**")
        for idx, ill in enumerate(ills, start=1):
            with st.expander(
                f"{idx}. {ill.get('idea') or '—'} — "
                f"{illustration_function_label(ill.get('function'))}",
                expanded=False,
            ):
                st.write(ill.get("connection_to_text") or "")
                if st.button(
                    f"Átveszem ezt az illusztrációt ({idx})",
                    key=f"sw_mi_en_ill_{idx}",
                ):
                    current = _read_illustrations_from_widgets()
                    if len(current) >= MAX_ILLUSTRATIONS:
                        st.warning(f"Legfeljebb {MAX_ILLUSTRATIONS} illusztráció lehet.")
                    else:
                        new_item = empty_illustration()
                        for field in _ILL_FIELDS:
                            if field != "id":
                                new_item[field] = str(ill.get(field) or "")
                        new_item["source"] = normalize_illustration_source(
                            ill.get("source")
                        ) or "needs_verification"
                        new_item["function"] = normalize_illustration_function(
                            ill.get("function")
                        )
                        current.append(new_item)
                        _request_adopt_enrichment_illustrations(current)
    elif load and "nem szükséges" in load.casefold():
        st.info(load)

    if apps:
        st.markdown("**Alkalmazási irányok**")
        for idx, app in enumerate(apps, start=1):
            with st.expander(
                f"{idx}. {app.get('application') or '—'} — "
                f"{application_scope_label(app.get('scope'))}",
                expanded=False,
            ):
                st.write(app.get("gospel_basis") or "")
                if st.button(
                    f"Átveszem ezt az alkalmazást ({idx})",
                    key=f"sw_mi_en_app_{idx}",
                ):
                    current = _read_applications_from_widgets()
                    if len(current) >= MAX_APPLICATIONS:
                        st.warning(f"Legfeljebb {MAX_APPLICATIONS} alkalmazás lehet.")
                    else:
                        new_item = empty_application()
                        for field in _APP_FIELDS:
                            if field != "id":
                                new_item[field] = str(app.get(field) or "")
                        new_item["scope"] = normalize_application_scope(app.get("scope"))
                        current.append(new_item)
                        _request_adopt_enrichment_applications(current)

    if expanded:
        st.markdown("**Az egész ív rövid összefoglalása**")
        st.write(expanded)
    if load:
        st.markdown(f"**Terheltségi értékelés:** {load}")

    if st.button("Átveszem a teljes tervet", key="sw_mi_en_adopt_all"):
        merged_imgs = _read_textual_images_from_widgets()
        merged_ills = _read_illustrations_from_widgets()
        merged_apps = _read_applications_from_widgets()
        for img in images:
            if len(merged_imgs) >= MAX_TEXTUAL_IMAGES:
                break
            new_item = empty_textual_image()
            for field in _IMG_FIELDS:
                if field != "id":
                    new_item[field] = str(img.get(field) or "")
            merged_imgs.append(new_item)
        for ill in ills:
            if len(merged_ills) >= MAX_ILLUSTRATIONS:
                break
            new_item = empty_illustration()
            for field in _ILL_FIELDS:
                if field != "id":
                    new_item[field] = str(ill.get(field) or "")
            new_item["source"] = normalize_illustration_source(ill.get("source"))
            merged_ills.append(new_item)
        for app in apps:
            if len(merged_apps) >= MAX_APPLICATIONS:
                break
            new_item = empty_application()
            for field in _APP_FIELDS:
                if field != "id":
                    new_item[field] = str(app.get(field) or "")
            merged_apps.append(new_item)
        _request_adopt_enrichment_plan(
            images=merged_imgs,
            illustrations=merged_ills,
            applications=merged_apps,
        )

    with st.expander("Mi alapján készült?", expanded=False):
        if reasoning:
            st.write(reasoning)
        if basis:
            for item in basis:
                if item:
                    st.markdown(f"- {item}")

    for w in warnings:
        if w:
            st.warning(str(w))
    if missing:
        st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))


def _render_enrichment_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("sermon_enrichment_assessment")
    if not isinstance(data, dict):
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and data.get("ok") is False:
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return
    if not overall and not data.get("revised_textual_images"):
        return

    st.markdown("**MI-értékelés**")
    if overall:
        st.write(overall)
    for key, label in (
        ("image_assessment", "Textusbeli képek"),
        ("illustration_assessment", "Illusztrációk"),
        ("application_assessment", "Alkalmazások"),
        ("load_assessment", "Terheltség"),
    ):
        val = str(data.get(key) or "").strip()
        if val:
            st.markdown(f"**{label}:** {val}")

    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    improvements = (
        data.get("improvements") if isinstance(data.get("improvements"), list) else []
    )
    if strengths:
        st.markdown("**Erősségek**")
        for s in strengths:
            if s:
                st.markdown(f"- {s}")
    if improvements:
        st.markdown("**Javítási javaslatok**")
        for s in improvements:
            if s:
                st.markdown(f"- {s}")

    rev_imgs = normalize_textual_images(data.get("revised_textual_images"))
    rev_ills = normalize_illustrations(data.get("revised_illustrations"))
    rev_apps = normalize_applications(data.get("revised_applications"))
    if rev_imgs or rev_ills or rev_apps:
        st.markdown("**Javított javaslatok**")
        if st.button("Átveszem a javított teljes tervet", key="sw_mi_en_adopt_rev_all"):
            _request_adopt_enrichment_plan(
                images=rev_imgs or None,
                illustrations=rev_ills or None,
                applications=rev_apps or None,
            )

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if w:
            st.warning(str(w))


def _render_closing_suggestions() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("closing_suggestions")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not (
        data.get("recommended_final_insight") or data.get("recommended_gospel_assurance")
    ):
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return

    closing_type = normalize_closing_type(data.get("recommended_closing_type"))
    final_insight = str(data.get("recommended_final_insight") or "").strip()
    assurance = str(data.get("recommended_gospel_assurance") or "").strip()
    invitation = str(data.get("recommended_invitation") or "").strip()
    image_line = str(data.get("recommended_closing_image_or_line") or "").strip()
    open_q = str(data.get("recommended_open_question") or "").strip()
    tone = normalize_closing_tone(data.get("recommended_tone"))
    expanded = str(data.get("expanded_summary") or "").strip()
    alternatives = (
        data.get("alternative_closings")
        if isinstance(data.get("alternative_closings"), list)
        else []
    )
    basis = data.get("basis") if isinstance(data.get("basis"), list) else []
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    missing = (
        data.get("missing_information")
        if isinstance(data.get("missing_information"), list)
        else []
    )
    reasoning = str(data.get("reasoning_summary") or "").strip()

    if not (final_insight or assurance or invitation or image_line or open_q):
        if missing:
            st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))
        return

    st.markdown("**MI-javaslat**")
    st.markdown(f"**Ajánlott lezárási irány:** {closing_type_label(closing_type)}")
    if st.button("Átveszem a lezárási irányt", key="sw_mi_cl_adopt_type"):
        _request_adopt_closing_block({"type": closing_type})

    if final_insight:
        st.markdown(f"**Végső felismerés:** {final_insight}")
        if st.button("Átveszem a végső felismerést", key="sw_mi_cl_adopt_insight"):
            _request_adopt_closing_block({"final_discovery": final_insight})

    if assurance:
        st.markdown(f"**Evangéliumi bizonyosság:** {assurance}")
        if st.button("Átveszem az evangéliumi bizonyosságot", key="sw_mi_cl_adopt_hope"):
            _request_adopt_closing_block({"hope": assurance})

    if invitation:
        st.markdown(f"**Kegyelemből fakadó meghívás:** {invitation}")
        if st.button("Átveszem a meghívást", key="sw_mi_cl_adopt_inv"):
            _request_adopt_closing_block({"call_or_response": invitation})

    if image_line:
        st.markdown(f"**Záró kép vagy mondatmag:** {image_line}")
        if st.button("Átveszem a záró képet", key="sw_mi_cl_adopt_img"):
            _request_adopt_closing_block({"image_or_line": image_line})

    if open_q:
        st.markdown(f"**Nyitva maradó kérdés:** {open_q}")
        if st.button("Átveszem a nyitott kérdést", key="sw_mi_cl_adopt_q"):
            _request_adopt_closing_block({"open_question": open_q})

    st.markdown(f"**Hangnem:** {closing_tone_label(tone)}")
    if st.button("Átveszem a hangnemet", key="sw_mi_cl_adopt_tone"):
        _request_adopt_closing_block({"tone": tone})

    if expanded:
        st.markdown("**Rövid kifejtés**")
        st.write(expanded)

    ui_block = {
        "type": closing_type,
        "final_discovery": final_insight,
        "hope": assurance,
        "call_or_response": invitation,
        "image_or_line": image_line,
        "open_question": open_q,
        "tone": tone,
    }
    if st.button("Átveszem a teljes lezárási tervet", key="sw_mi_cl_adopt_all"):
        _request_adopt_closing_block(ui_block)

    if alternatives:
        with st.expander("Alternatív lezárási irányok", expanded=False):
            for idx, alt in enumerate(alternatives, start=1):
                if not isinstance(alt, dict):
                    continue
                st.markdown(
                    f"**{idx}. {closing_type_label(alt.get('closing_type'))}** "
                    f"({closing_tone_label(alt.get('tone'))})"
                )
                if alt.get("emphasis"):
                    st.write(str(alt.get("emphasis")))
                if alt.get("reason_for_use"):
                    st.caption(str(alt.get("reason_for_use")))

    with st.expander("Mi alapján készült?", expanded=False):
        if reasoning:
            st.write(reasoning)
        if basis:
            for item in basis:
                if item:
                    st.markdown(f"- {item}")

    for w in warnings:
        if w:
            st.warning(str(w))
    if missing:
        st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))


def _render_closing_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("closing_assessment")
    if not isinstance(data, dict):
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and data.get("ok") is False:
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return
    if not overall and not data.get("revised_final_insight"):
        return

    st.markdown("**MI-értékelés**")
    if overall:
        st.write(overall)
    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    improvements = (
        data.get("improvements") if isinstance(data.get("improvements"), list) else []
    )
    if strengths:
        st.markdown("**Erősségek**")
        for s in strengths:
            if s:
                st.markdown(f"- {s}")
    if improvements:
        st.markdown("**Javítási javaslatok**")
        for s in improvements:
            if s:
                st.markdown(f"- {s}")
    for key, label in (
        ("arrival_assessment", "Megérkezés"),
        ("gospel_assurance_assessment", "Evangéliumi bizonyosság"),
        ("invitation_assessment", "Meghívás"),
        ("tone_assessment", "Hangnem"),
    ):
        val = str(data.get(key) or "").strip()
        if val:
            st.markdown(f"**{label}:** {val}")

    revised = {
        "type": normalize_closing_type(data.get("revised_closing_type")),
        "final_discovery": str(data.get("revised_final_insight") or "").strip(),
        "hope": str(data.get("revised_gospel_assurance") or "").strip(),
        "call_or_response": str(data.get("revised_invitation") or "").strip(),
        "image_or_line": str(data.get("revised_closing_image_or_line") or "").strip(),
        "open_question": str(data.get("revised_open_question") or "").strip(),
        "tone": normalize_closing_tone(data.get("revised_tone")),
    }
    if any(revised.values()):
        st.markdown("**Javított javaslatok**")
        if st.button("Átveszem a javított teljes tervet", key="sw_mi_cl_adopt_rev_all"):
            _request_adopt_closing_block(
                {k: v for k, v in revised.items() if v}
            )
        for field, label, key in (
            ("type", "lezárási irányt", "sw_mi_cl_adopt_rev_type"),
            ("final_discovery", "végső felismerést", "sw_mi_cl_adopt_rev_insight"),
            ("hope", "evangéliumi bizonyosságot", "sw_mi_cl_adopt_rev_hope"),
            ("call_or_response", "meghívást", "sw_mi_cl_adopt_rev_inv"),
            ("image_or_line", "záró képet", "sw_mi_cl_adopt_rev_img"),
            ("open_question", "nyitott kérdést", "sw_mi_cl_adopt_rev_q"),
            ("tone", "hangnemet", "sw_mi_cl_adopt_rev_tone"),
        ):
            val = revised.get(field) or ""
            if not val:
                continue
            display = (
                closing_type_label(val)
                if field == "type"
                else closing_tone_label(val)
                if field == "tone"
                else val
            )
            st.markdown(f"*{label.capitalize()}:* {display}")
            if st.button(f"Átveszem a {label}", key=key):
                _request_adopt_closing_block({field: val})

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if w:
            st.warning(str(w))


_SOURCE_ENGAGEMENT = "Megszólítás és bevonás"
_ENGAGE_ADD_TYPE_KEY = "sw_engage_add_type"
_ENGAGE_ADD_TEXT_KEY = "sw_engage_add_text"


def _engage_text_key(item_id: str) -> str:
    return f"sw_engage_text_{item_id}"


def _engage_type_key(item_id: str) -> str:
    return f"sw_engage_type_{item_id}"


def _block_if_approved(sw: dict[str, Any], block_key: str) -> Any:
    """Egy blokk tartalma, DE csak akkor, ha jóváhagyott állapotban van.

    A Megszólítás és bevonás modul kizárólag jóváhagyott anyagból dolgozhat
    — ez a segédfüggvény a forrás oldali (nem csak a végső vázlat oldali)
    szűrést végzi el, mielőtt bármi eljutna a generate_fn hívásig.
    """
    if (sw.get(f"{block_key}_status") or "") != "approved":
        return None
    return sw.get(block_key)


def _collect_approved_engagement_kwargs() -> dict[str, Any]:
    tw = ensure_text_workshop_state(st.session_state)
    sw = ensure_sermon_workshop_state(st.session_state)
    summary = tw.get("text_summary") if isinstance(tw.get("text_summary"), dict) else {}
    summary_approved = (summary.get("status") or "") == "approved"

    sermon_idea = sw.get("sermon_main_idea") or ""
    sermon_idea_approved = (sw.get("sermon_main_idea_status") or "") == "approved"

    return {
        "passage": (
            st.session_state.get("last_igehely")
            or st.session_state.get("igehely_input")
            or ""
        ).strip(),
        "text_summary_main_idea": (summary.get("main_idea") or "") if summary_approved else "",
        "text_summary_base_tension": (
            (summary.get("base_tension") or "") if summary_approved else ""
        ),
        "sermon_main_idea": sermon_idea if sermon_idea_approved else "",
        "entry_point": _block_if_approved(sw, "entry_point"),
        "human_condition": _block_if_approved(sw, "human_condition"),
        "listener_tension": _block_if_approved(sw, "listener_tension"),
        "sermon_path": _block_if_approved(sw, "sermon_path"),
        "christ_centered_arc": _block_if_approved(sw, "christ_centered_arc"),
        "closing": _block_if_approved(sw, "closing"),
    }


def _run_engagement_suggest(generate_fn: GenerateFn) -> None:
    if st.session_state.get("_sw_engage_suggest_running"):
        return
    st.session_state["_sw_engage_suggest_running"] = True
    try:
        kwargs = _collect_approved_engagement_kwargs()
        if not kwargs["passage"]:
            st.warning(
                "Add meg az igeszakaszt a Textusműhelyben, mielőtt javaslatot kérsz."
            )
            return

        with st.spinner("Megszólítás és bevonás javaslatok készülnek…"):
            result: EngagementSuggestionResult = suggest_engagement_elements(
                **kwargs, generate_fn=generate_fn
            )

        if not result.ok:
            st.warning(
                _user_facing_entry_point_error(
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
                )
            )
            return

        save_engagement_suggestions(st.session_state, result.to_dict())
        if not result.options:
            st.info(
                "Nincs elegendő jóváhagyott anyag érdemi javaslathoz — hagyj "
                "jóvá legalább egy szakaszt (pl. fókuszmondat, belépési "
                "pont, prédikáció íve), vagy nézd meg a hiányzó "
                "információkat."
            )
        else:
            st.success("A javaslatok elkészültek.")
    finally:
        st.session_state["_sw_engage_suggest_running"] = False


def _render_engagement_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    sugs = sw.get("engagement_suggestions")
    if not isinstance(sugs, dict):
        return

    st.markdown("**MI-javaslatok**")
    generated_at = (sw.get("engagement_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    options = sugs.get("options") or []
    if isinstance(options, list) and options:
        for idx, opt in enumerate(options):
            if not isinstance(opt, dict):
                continue
            type_key = normalize_engagement_type(opt.get("type"))
            text = (opt.get("text") or "").strip()
            if not text:
                continue
            with st.container(border=True):
                st.markdown(f"**{engagement_type_label(type_key)}**")
                st.markdown(text)
                if st.button("Átveszem", key=f"sw_engage_adopt_{idx}"):
                    add_engagement_element(
                        st.session_state, type=type_key, text=text, source="ai"
                    )
                    st.rerun()
    else:
        st.info(
            "Nincs javaslat (elégtelen jóváhagyott adat, vagy a modell "
            "üresen hagyta). A részletek a figyelmeztetéseknél/hiányzó "
            "információknál találhatók."
        )

    reasoning = (sugs.get("reasoning_summary") or "").strip()
    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    has_warnings = isinstance(warnings, list) and any(str(x).strip() for x in warnings)
    has_missing = isinstance(missing, list) and any(str(x).strip() for x in missing)
    if reasoning or has_warnings or has_missing:
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.markdown("**Indoklás**")
                st.markdown(reasoning)
            if has_warnings:
                st.markdown("**Figyelmeztetések**")
                for item in warnings:
                    line = str(item or "").strip()
                    if line:
                        st.warning(line)
            if has_missing:
                st.markdown("**Hiányzó információk**")
                for item in missing:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")


def _render_engagement_element_editor(item: dict[str, Any]) -> None:
    iid = str(item.get("id") or "")
    if not iid:
        return
    status = item.get("status") or "draft"
    source = item.get("source") or "own"

    with st.container(border=True):
        st.selectbox(
            "Típus",
            options=list(ENGAGEMENT_TYPE_KEYS),
            format_func=engagement_type_label,
            key=_engage_type_key(iid),
            index=(
                list(ENGAGEMENT_TYPE_KEYS).index(item.get("type"))
                if item.get("type") in ENGAGEMENT_TYPE_KEYS
                else 0
            ),
        )
        st.text_area(
            "Szöveg",
            key=_engage_text_key(iid),
            value=item.get("text") or "",
            height=80,
            label_visibility="collapsed",
        )
        st.caption(
            f"Állapot: **{_STATUS_LABELS.get(status, status)}** · "
            f"Forrás: {'MI-javaslat' if source == 'ai' else 'Saját elem'}"
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Mentés", key=f"sw_engage_save_{iid}"):
                update_engagement_element(
                    st.session_state,
                    iid,
                    type=st.session_state.get(_engage_type_key(iid)),
                    text=st.session_state.get(_engage_text_key(iid)),
                )
                _toast_and_rerun("Mentve.")
        with c2:
            if st.button("Jóváhagyom", key=f"sw_engage_approve_{iid}", type="primary"):
                text_now = (st.session_state.get(_engage_text_key(iid)) or "").strip()
                if not text_now:
                    st.warning("Üres elemet nem lehet jóváhagyni.")
                else:
                    update_engagement_element(
                        st.session_state,
                        iid,
                        type=st.session_state.get(_engage_type_key(iid)),
                        text=text_now,
                        status="approved",
                    )
                    _toast_and_rerun("Jóváhagyva — bekerülhet a végső vázlatba.")
        with c3:
            if st.button("Törlés", key=f"sw_engage_delete_{iid}"):
                remove_engagement_element(st.session_state, iid)
                st.rerun()


def render_engagement_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Megszólítás és bevonás — kizárólag jóváhagyott anyagból dolgozó MI-javaslat
    + kézi szerkesztés/jóváhagyás. Opcionális, kihagyható szakasz.
    """
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Megszólítás és bevonás")
    st.markdown(
        "2-4 rövid retorikai eszköz — kérdés, megszólítás, kép, élethelyzet "
        "vagy jelenlétteremtő mondat —, amely segít, hogy az igehirdetés ne "
        "távoli „szentbeszédként” hasson. A javaslat kizárólag a már "
        "jóváhagyott textus- és igehirdetési anyagból készül. Ez a szakasz "
        "teljesen opcionális — kihagyása nem akadályozza a vázlat "
        "elkészítését."
    )

    ai_ready = generate_fn is not None
    if st.button(
        "Javaslatok készítése",
        key="sw_engage_suggest",
        type="primary",
        disabled=not ai_ready or bool(st.session_state.get("_sw_engage_suggest_running")),
    ):
        if generate_fn is None:
            st.warning("Az MI-segéd jelenleg nem elérhető.")
        else:
            _run_engagement_suggest(generate_fn)
    if not ai_ready:
        st.caption("Az MI-segéd nincs bekötve ehhez a nézethez.")

    _render_engagement_suggestion_results()

    sw = ensure_sermon_workshop_state(st.session_state)
    elements = sw.get("engagement_elements") or []
    st.markdown("**Megszólító elemek**")
    if not elements:
        st.info(
            "Még nincs megszólító elem. Kérj javaslatot, vagy add hozzá "
            "saját ötletedet lentebb."
        )
    for item in elements:
        if isinstance(item, dict):
            _render_engagement_element_editor(item)

    with st.expander("Saját elem hozzáadása", expanded=False):
        st.selectbox(
            "Típus",
            options=list(ENGAGEMENT_TYPE_KEYS),
            format_func=engagement_type_label,
            key=_ENGAGE_ADD_TYPE_KEY,
        )
        st.text_area(
            "Szöveg",
            key=_ENGAGE_ADD_TEXT_KEY,
            height=80,
            placeholder="A saját megszólító elem szövege…",
        )
        if st.button("Hozzáadás", key="sw_engage_add_own"):
            text = (st.session_state.get(_ENGAGE_ADD_TEXT_KEY) or "").strip()
            if not text:
                st.warning("Üres elemet nem lehet hozzáadni.")
            else:
                add_engagement_element(
                    st.session_state,
                    type=st.session_state.get(_ENGAGE_ADD_TYPE_KEY) or "",
                    text=text,
                    source="own",
                )
                st.session_state[_ENGAGE_ADD_TEXT_KEY] = ""
                st.rerun()


def render_closing_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Lezárás és megérkezés — kézi szerkesztő + MI-segéd."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Lezárás és megérkezés")
    st.markdown(
        "Itt nem a teljes záróbekezdést írjuk meg, hanem megtervezzük, milyen "
        "felismeréshez és milyen kegyelemből fakadó válaszhoz érkezzen meg az "
        "igehirdetés."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    status = (sw.get("closing_status") or "draft").strip()
    st.caption(f"Állapot: {_STATUS_LABELS.get(status, status)}")

    if (sw.get("sermon_main_idea_status") or "").strip() != "approved":
        st.info(
            "A szakasz használható, de a javaslatkészítéshez előbb jóvá kell "
            "hagyni az igehirdetés fő gondolatát, szükség van M6-os megérkezési "
            "pontra vagy legalább három mozgásra, valamint evangéliumi feloldásra "
            "vagy Isten kegyelmi cselekvésére."
        )

    for field, title, help_text, optional in _CL_FIELDS:
        st.markdown(f"**{title}**")
        if help_text:
            st.caption(help_text)
        if optional:
            st.caption("Opcionális mező — üresen hagyható.")
        if field == "type":
            st.selectbox(
                title,
                options=list(CLOSING_TYPES),
                format_func=lambda v: CLOSING_TYPE_LABELS_HU.get(v, str(v)),
                key=_KEY_CL["type"],
                label_visibility="collapsed",
            )
        elif field == "tone":
            st.selectbox(
                title,
                options=list(CLOSING_TONES),
                format_func=lambda v: CLOSING_TONE_LABELS_HU.get(v, str(v)),
                key=_KEY_CL["tone"],
                label_visibility="collapsed",
            )
        else:
            st.text_area(
                title,
                key=_KEY_CL[field],
                height=80,
                label_visibility="collapsed",
            )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_cl_save_draft"):
            block = _read_closing_from_widgets()
            filled = any(
                block.get(k)
                for k in (
                    "final_discovery",
                    "hope",
                    "call_or_response",
                    "image_or_line",
                    "open_question",
                )
            )
            if not filled:
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                _persist_closing_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "closing_status", "draft"
                )
                _toast_and_rerun("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            type="primary",
            key="sw_cl_approve",
        ):
            block = _read_closing_from_widgets()
            if not any(
                block.get(k)
                for k in (
                    "final_discovery",
                    "hope",
                    "call_or_response",
                    "image_or_line",
                    "open_question",
                )
            ):
                st.warning(
                    "Üres megfogalmazást nem lehet jóváhagyni. Tölts ki legalább egyet."
                )
            else:
                _persist_closing_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "closing_status", "approved"
                )
                decisions = [
                    ("type", "Lezárás iránya", closing_type_label(block["type"])),
                    ("final_discovery", "Végső felismerés", block["final_discovery"]),
                    ("hope", "Evangéliumi bizonyosság", block["hope"]),
                    (
                        "call_or_response",
                        "Kegyelemből fakadó meghívás",
                        block["call_or_response"],
                    ),
                    (
                        "image_or_line",
                        "Záró kép vagy mondatmag",
                        block["image_or_line"],
                    ),
                    ("open_question", "Nyitva maradó kérdés", block["open_question"]),
                    ("tone", "Hangnem", closing_tone_label(block["tone"])),
                ]
                added = 0
                skipped = 0
                for _field, category, content in decisions:
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_CLOSING,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_CLOSING,
                        category,
                        content,
                    )
                    added += 1
                if added:
                    _toast_and_rerun(f"Jóváhagyva ({added} döntés).")
                elif skipped:
                    _toast_and_rerun("Jóváhagyva. Ezek a döntések már szerepelnek.")
                else:
                    _toast_and_rerun("Jóváhagyva.")

    _render_decisions_for_section(_SOURCE_CLOSING)

    st.markdown("---")
    st.markdown("**MI-segéd**")
    mi1, mi2 = st.columns(2)
    with mi1:
        if st.button("Lezárási irány javaslata", key="sw_cl_mi_suggest"):
            _run_closing_suggest(generate_fn=generate_fn)
    with mi2:
        if st.button("Saját lezárási terv értékelése", key="sw_cl_mi_assess"):
            _run_closing_assess(generate_fn=generate_fn)

    _render_closing_suggestions()
    _render_closing_assessment()


def _ensure_enrichment_retained_from_legacy(sw: dict[str, Any]) -> None:
    """Régi M7 illusztrációk → megtartott kártyák, ha a lista még üres."""
    retained = normalize_illustration_cards(sw.get("retained_illustration_cards"))
    if retained:
        return
    legacy = normalize_illustrations(sw.get("illustrations"))
    if not legacy:
        return
    cards = [legacy_illustration_to_card(x) for x in legacy]
    update_sermon_workshop_section(
        st.session_state, "retained_illustration_cards", cards
    )


def _sync_retained_illustrations_legacy(cards: list[dict[str, Any]]) -> None:
    legacy = [illustration_card_to_legacy(c) for c in cards]
    update_sermon_workshop_section(st.session_state, "illustrations", legacy)
    update_sermon_workshop_section(
        st.session_state, "retained_illustration_cards", cards
    )


def _retain_illustration_card(card: dict[str, Any]) -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    retained = normalize_illustration_cards(sw.get("retained_illustration_cards"))
    cid = str(card.get("id") or "")
    if any(str(x.get("id") or "") == cid for x in retained):
        st.info("Ez az ötlet már meg van tartva.")
        return
    item = normalize_illustration_card(card)
    item["selected"] = True
    retained.append(item)
    _sync_retained_illustrations_legacy(retained)
    st.success("Illusztráció megtartva.")
    st.rerun()


def _retain_actualization_card(card: dict[str, Any]) -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    retained = normalize_actualization_cards(sw.get("actualization_connections"))
    cid = str(card.get("id") or "")
    if any(str(x.get("id") or "") == cid for x in retained):
        st.info("Ez a kapcsolódási pont már meg van tartva.")
        return
    item = normalize_actualization_card(card)
    item["selected"] = True
    retained.append(item)
    update_sermon_workshop_section(
        st.session_state, "actualization_connections", retained
    )
    st.success("Kapcsolódási pont megtartva.")
    st.rerun()


def _merge_textus_enrichment_into_retained() -> None:
    """Textusműhely kosár / mező → megtartott listák (duplikáció nélkül)."""
    sw = ensure_sermon_workshop_state(st.session_state)
    retained_ill = normalize_illustration_cards(sw.get("retained_illustration_cards"))
    ids_ill = {str(x.get("id") or "") for x in retained_ill}
    for card in collect_textus_retained_illustrations(
        st.session_state, existing_ids=ids_ill
    ):
        retained_ill.append(card)
        ids_ill.add(str(card.get("id") or ""))
    if retained_ill != normalize_illustration_cards(sw.get("retained_illustration_cards")):
        _sync_retained_illustrations_legacy(retained_ill)

    retained_act = normalize_actualization_cards(sw.get("actualization_connections"))
    ids_act = {str(x.get("id") or "") for x in retained_act}
    changed = False
    for card in collect_textus_retained_actualizations(
        st.session_state, existing_ids=ids_act
    ):
        retained_act.append(card)
        ids_act.add(str(card.get("id") or ""))
        changed = True
    if changed:
        update_sermon_workshop_section(
            st.session_state, "actualization_connections", retained_act
        )


def _render_illustration_suggestion_card(card: dict[str, Any], *, key_prefix: str) -> None:
    title = str(card.get("title") or "Illusztráció").strip()
    idea = str(card.get("idea") or "").strip()
    connection = str(card.get("connection_to_text") or "").strip()
    usage = str(card.get("usage_note") or "").strip()
    listener = str(card.get("listener_link") or "").strip()
    st.markdown(f"**{title}**")
    if idea:
        st.markdown(f"**Az ötlet**\n\n{idea}")
    if connection:
        st.markdown(f"**Kapcsolódás a textushoz**\n\n{connection}")
    if usage:
        st.caption(f"Használati megjegyzés: {usage}")
    if listener:
        st.caption(f"Lehetséges kapcsolódás a hallgató életéhez: {listener}")
    if card.get("from_text_workshop"):
        st.caption("A Textusműhelyből megtartva")
    if st.button("Megtartom ezt az ötletet", key=f"{key_prefix}_keep"):
        _retain_illustration_card(card)


def _render_actualization_suggestion_card(
    card: dict[str, Any], *, key_prefix: str
) -> None:
    title = str(card.get("title") or "Kapcsolódási pont").strip()
    summary = str(card.get("event_summary") or "").strip()
    connection = str(card.get("connection_to_text") or "").strip()
    use = str(card.get("possible_use") or "").strip()
    source = str(card.get("source_name") or "").strip()
    url = str(card.get("source_url") or "").strip()
    published = str(card.get("published_at") or "").strip()
    caution = str(card.get("caution") or "").strip()
    st.markdown(f"**{title}**")
    if summary:
        st.markdown(f"**Mi történt?**\n\n{summary}")
    if connection:
        st.markdown(f"**Miért kapcsolódhat a textushoz?**\n\n{connection}")
    if use:
        st.markdown(f"**Felhasználási lehetőség**\n\n{use}")
    src_bits = []
    if source:
        src_bits.append(source)
    if published:
        src_bits.append(published)
    if src_bits:
        st.caption("Forrás és dátum: " + " · ".join(src_bits))
    if url:
        st.markdown(f"[Forráshivatkozás]({url})")
    if caution:
        st.caption(f"Óvatosság: {caution}")
    if card.get("from_text_workshop"):
        st.caption("A Textusműhelyből megtartva")
    if st.button("Megtartom kapcsolódási pontként", key=f"{key_prefix}_keep"):
        _retain_actualization_card(card)


def _run_simple_illustration_suggest(*, generate_fn: GenerateFn | None) -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    direction = str(
        st.session_state.get("sw_en_ill_direction")
        or sw.get("illustration_user_direction")
        or ""
    ).strip()
    update_sermon_workshop_section(
        st.session_state, "illustration_user_direction", direction
    )
    with st.spinner("Illusztrációs javaslatok készülnek…"):
        result = suggest_illustrations(
            st.session_state,
            user_direction=direction,
            generate_fn=generate_fn,
        )
    if not result.ok:
        st.warning(result.error_message or "A javaslatkészítés nem sikerült.")
        return
    update_sermon_workshop_section(
        st.session_state,
        "illustration_suggestions",
        result.suggestions,
    )
    update_sermon_workshop_section(
        st.session_state, "illustration_suggest_note", result.note
    )
    st.success("Illusztrációs javaslatok elkészültek.")
    st.rerun()


def _run_simple_actualization_suggest(*, generate_fn: GenerateFn | None) -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    direction = str(
        st.session_state.get("sw_en_act_direction")
        or sw.get("actualization_user_direction")
        or ""
    ).strip()
    update_sermon_workshop_section(
        st.session_state, "actualization_user_direction", direction
    )
    with st.spinner("Aktuális kapcsolódások keresése…"):
        result = suggest_actualizations(
            st.session_state,
            user_direction=direction,
            generate_fn=generate_fn,
        )
    if not result.ok:
        st.warning(result.error_message or _EN_NO_SEARCH)
        return
    update_sermon_workshop_section(
        st.session_state,
        "actualization_suggestions",
        result.suggestions,
    )
    update_sermon_workshop_section(
        st.session_state, "actualization_suggest_note", result.note
    )
    if result.suggestions:
        st.success("Aktuális kapcsolódási pontok elkészültek.")
    else:
        st.info(result.note or "Nincs erőltetés nélkül kapcsolható friss találat.")
    st.rerun()


def render_enrichment_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Illusztrációk és aktualizálás — egyszerű javaslat + megtartás."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    sw = ensure_sermon_workshop_state(st.session_state)
    _ensure_enrichment_retained_from_legacy(sw)
    _merge_textus_enrichment_into_retained()
    sw = ensure_sermon_workshop_state(st.session_state)

    render_page_intro(
        eyebrow="Műhelyszakasz",
        title="Illusztrációk és aktualizálás",
        body=(
            "Az alkalmazás a textus és a rendelkezésre álló igehirdetési anyag "
            "alapján ajánl képeket, példákat és aktuális kapcsolódási pontokat. "
            "Nem kell minden műhelyszakaszt kitölteni, és nem kötelező külső "
            "illusztrációt vagy hírt használni."
        ),
    )

    ready = assess_enrichment_readiness(st.session_state)
    if not ready.ok:
        render_info_panel(title="Még nincs elég alapanyag", body=ready.message, tone="info")

    tab_ill, tab_act = st.tabs(["Illusztrációk", "Aktualizálás"])

    with tab_ill:
        st.markdown("#### Illusztrációk és képek")
        st.markdown(
            "Az alkalmazás a textus és az elkészült igehirdetési anyag alapján "
            "ajánl képeket, példákat és történeteket. Nem szükséges minden "
            "prédikációhoz külső illusztrációt használni."
        )
        if "sw_en_ill_direction" not in st.session_state:
            st.session_state["sw_en_ill_direction"] = str(
                sw.get("illustration_user_direction") or ""
            )
        st.text_area(
            "Milyen illusztrációt keresel?",
            key="sw_en_ill_direction",
            height=90,
            help=(
                "Röviden megadhatod az irányt. Ha üresen hagyod, az alkalmazás "
                "a textus alapján önállóan javasol."
            ),
            placeholder=(
                "Pl. Egy hétköznapi, mai életből vett példát keresek. / "
                "Egy rövid haszid vagy spirituális történetet szeretnék. / "
                "Ne legyen történet, inkább a textus egyik képét bontsa ki."
            ),
        )
        if st.button(
            "Illusztrációk javaslata",
            type="primary",
            key="sw_en_ill_suggest",
            disabled=not ready.ok,
        ):
            _run_simple_illustration_suggest(generate_fn=generate_fn)

        note = str(sw.get("illustration_suggest_note") or "").strip()
        if note:
            st.caption(note)
        suggestions = normalize_illustration_cards(sw.get("illustration_suggestions"))
        for idx, card in enumerate(suggestions):
            with st.container():
                _render_illustration_suggestion_card(
                    card, key_prefix=f"sw_en_ill_sug_{idx}"
                )
                st.markdown("---")

        retained = normalize_illustration_cards(sw.get("retained_illustration_cards"))
        with st.expander("Megtartott illusztrációk", expanded=False):
            if not retained:
                st.caption("Még nincs megtartott illusztráció.")
            else:
                for idx, card in enumerate(retained):
                    title = str(card.get("title") or "Illusztráció").strip()
                    idea = str(card.get("idea") or "").strip()
                    st.markdown(f"**{title}**")
                    if idea:
                        st.write(idea)
                    if card.get("from_text_workshop"):
                        st.caption("A Textusműhelyből megtartva")
                    new_idea = st.text_area(
                        "Szerkesztés",
                        value=idea,
                        key=f"sw_en_ill_ret_edit_{idx}",
                        height=80,
                    )
                    if st.button("Mentés", key=f"sw_en_ill_ret_save_{idx}"):
                        retained[idx] = normalize_illustration_card(
                            {**card, "idea": new_idea}
                        )
                        _sync_retained_illustrations_legacy(retained)
                        st.rerun()
                    if st.button("Eltávolítás", key=f"sw_en_ill_ret_del_{idx}"):
                        del retained[idx]
                        _sync_retained_illustrations_legacy(retained)
                        st.rerun()

    with tab_act:
        st.markdown("#### Aktuális kapcsolódási pontok")
        st.markdown(
            "Az alkalmazás friss hírekből, társadalmi jelenségekből és aktuális "
            "eseményekből kereshet olyan kapcsolódási pontokat, amelyek "
            "segíthetik a textus mai meghallását. Nem kell mindenáron aktuális "
            "hírt beleilleszteni a prédikációba."
        )
        if "sw_en_act_direction" not in st.session_state:
            st.session_state["sw_en_act_direction"] = str(
                sw.get("actualization_user_direction") or ""
            )
        st.text_area(
            "Milyen irányban keressünk?",
            key="sw_en_act_direction",
            height=90,
            help=(
                "Megadhatsz témát, földrajzi területet vagy kerülendő területet. "
                "Ha üresen hagyod, az alkalmazás a textus fő hangsúlyai alapján keres."
            ),
            placeholder=(
                "Pl. Romániai vagy erdélyi aktualitást keresek. / "
                "Ne politikai hírt, inkább hétköznapi társadalmi jelenséget keress."
            ),
        )
        if st.button(
            "Aktuális kapcsolódások keresése",
            type="primary",
            key="sw_en_act_suggest",
            disabled=not ready.ok,
        ):
            _run_simple_actualization_suggest(generate_fn=generate_fn)

        act_note = str(sw.get("actualization_suggest_note") or "").strip()
        if act_note:
            st.caption(act_note)
        act_suggestions = normalize_actualization_cards(
            sw.get("actualization_suggestions")
        )
        for idx, card in enumerate(act_suggestions):
            with st.container():
                _render_actualization_suggestion_card(
                    card, key_prefix=f"sw_en_act_sug_{idx}"
                )
                st.markdown("---")

        retained_act = normalize_actualization_cards(
            sw.get("actualization_connections")
        )
        with st.expander("Megtartott aktualizálások", expanded=False):
            if not retained_act:
                st.caption("Még nincs megtartott aktualizálás.")
            else:
                for idx, card in enumerate(retained_act):
                    title = str(card.get("title") or "Kapcsolódás").strip()
                    summary = str(card.get("event_summary") or "").strip()
                    st.markdown(f"**{title}**")
                    if summary:
                        st.write(summary)
                    src = str(card.get("source_name") or "").strip()
                    published = str(card.get("published_at") or "").strip()
                    if src or published:
                        st.caption(" · ".join(x for x in (src, published) if x))
                    if card.get("from_text_workshop"):
                        st.caption("A Textusműhelyből megtartva")
                    if st.button("Eltávolítás", key=f"sw_en_act_ret_del_{idx}"):
                        del retained_act[idx]
                        update_sermon_workshop_section(
                            st.session_state,
                            "actualization_connections",
                            retained_act,
                        )
                        st.rerun()

    st.markdown("---")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_en_save_draft"):
            update_sermon_workshop_section(
                st.session_state, "enrichment_status", "draft"
            )
            _toast_and_rerun("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            type="primary",
            key="sw_en_approve",
        ):
            retained = normalize_illustration_cards(
                sw.get("retained_illustration_cards")
            )
            retained_act = normalize_actualization_cards(
                sw.get("actualization_connections")
            )
            if not retained and not retained_act:
                st.warning("Legalább egy megtartott elemet adj hozzá a jóváhagyáshoz.")
            else:
                update_sermon_workshop_section(
                    st.session_state, "enrichment_status", "approved"
                )
                added = 0
                for idx, card in enumerate(retained, start=1):
                    summary = (
                        f"{idx}. {card.get('title') or 'Illusztráció'}: "
                        f"{(card.get('idea') or '')[:160]}"
                    ).strip()
                    if _decision_is_duplicate(
                        source_section=_SOURCE_ENRICHMENT,
                        category="Illusztráció",
                        content=summary,
                    ):
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_ENRICHMENT,
                        "Illusztráció",
                        summary,
                    )
                    added += 1
                for idx, card in enumerate(retained_act, start=1):
                    summary = (
                        f"{idx}. {card.get('title') or 'Aktualizálás'}: "
                        f"{(card.get('event_summary') or '')[:160]}"
                    ).strip()
                    if _decision_is_duplicate(
                        source_section=_SOURCE_ENRICHMENT,
                        category="Aktualizálás",
                        content=summary,
                    ):
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_ENRICHMENT,
                        "Aktualizálás",
                        summary,
                    )
                    added += 1
                _toast_and_rerun(f"Jóváhagyva ({added} döntés)." if added else "Jóváhagyva.")

    _render_decisions_for_section(_SOURCE_ENRICHMENT)


def _suggestion_payload_from_result(
    result: SermonMainIdeaSuggestionResult,
) -> dict[str, Any]:
    return {
        "recommended": result.recommended,
        "expanded_summary": result.expanded_summary or "",
        "alternatives": list(result.alternatives),
        "reasoning_summary": result.reasoning_summary,
        "textual_and_homiletical_basis": list(result.textual_and_homiletical_basis),
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _sermon_assessment_payload(
    result: SermonMainIdeaAssessmentResult,
) -> dict[str, Any]:
    return {
        "assessment": result.assessment.to_dict(),
        "strengths": list(result.strengths),
        "revision_priorities": list(result.revision_priorities),
        "revised_version": result.revised_version,
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _hc_suggestion_payload(result: HumanConditionSuggestionResult) -> dict[str, Any]:
    return {
        "human_condition": result.human_condition,
        "false_response": result.false_response,
        "human_need": result.human_need,
        "divine_action": result.divine_action,
        "grace_response": result.grace_response,
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _hc_assessment_payload(result: HumanConditionAssessmentResult) -> dict[str, Any]:
    return {
        "assessment": result.assessment.to_dict(),
        "strengths": list(result.strengths),
        "revision_priorities": list(result.revision_priorities),
        "revised_block": result.revised_block.to_dict(),
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _lt_suggestion_payload(result: ListenerTensionSuggestionResult) -> dict[str, Any]:
    return {
        "recommended_listener_question": result.recommended_listener_question,
        "recommended_listener_resistance": result.recommended_listener_resistance,
        "recommended_tension": result.recommended_tension,
        "expanded_summary": result.expanded_summary or "",
        "alternative_sets": [alt.to_dict() for alt in result.alternative_sets],
        "reasoning_summary": result.reasoning_summary,
        "basis": list(result.basis),
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _lt_assessment_payload(result: ListenerTensionAssessmentResult) -> dict[str, Any]:
    return {
        "overall_assessment": result.overall_assessment,
        "strengths": list(result.strengths),
        "improvements": list(result.improvements),
        "revised_listener_question": result.revised_listener_question,
        "revised_listener_resistance": result.revised_listener_resistance,
        "revised_tension": result.revised_tension,
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _ga_suggestion_payload(result: GospelArcSuggestionResult) -> dict[str, Any]:
    return {
        "recommended_divine_gracious_action": result.recommended_divine_gracious_action,
        "recommended_christ_connection": result.recommended_christ_connection,
        "recommended_christ_connection_type": result.recommended_christ_connection_type,
        "recommended_promised_resolution": result.recommended_promised_resolution,
        "recommended_grace_enabled_response": result.recommended_grace_enabled_response,
        "expanded_summary": result.expanded_summary or "",
        "confidence": result.confidence or "low",
        "alternative_connections": [
            alt.to_dict() for alt in result.alternative_connections
        ],
        "reasoning_summary": result.reasoning_summary,
        "basis": list(result.basis),
        "warnings": list(result.warnings),
        "missing_information": list(result.missing_information),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _ga_assessment_payload(result: GospelArcAssessmentResult) -> dict[str, Any]:
    return {
        "overall_assessment": result.overall_assessment,
        "strengths": list(result.strengths),
        "improvements": list(result.improvements),
        "connection_type_assessment": result.connection_type_assessment,
        "revised_divine_gracious_action": result.revised_divine_gracious_action,
        "revised_christ_connection": result.revised_christ_connection,
        "suggested_christ_connection_type": result.suggested_christ_connection_type,
        "revised_promised_resolution": result.revised_promised_resolution,
        "revised_grace_enabled_response": result.revised_grace_enabled_response,
        "warnings": list(result.warnings),
        "ok": bool(result.ok),
        "error_message": result.error_message or "",
    }


def _prompt_block_to_ui(block: dict[str, Any] | None) -> dict[str, str]:
    out = {k: "" for k in _KEY_HC}
    if not isinstance(block, dict):
        return out
    for prompt_key, ui_key in _HC_PROMPT_TO_UI.items():
        if prompt_key in block:
            out[ui_key] = str(block.get(prompt_key) or "").strip()
        elif ui_key in block:
            out[ui_key] = str(block.get(ui_key) or "").strip()
    return out


def _render_shell_context_summary() -> None:
    """Kompakt kontextussor (ContextSummary) a shell tetején."""
    tw = ensure_text_workshop_state(st.session_state)
    passage = _session_str("last_igehely", "igehely_input") or "—"
    idea = (tw.get("text_main_idea") or "").strip()
    status = (tw.get("text_main_idea_status") or "").strip()
    insights = tw.get("approved_insights") or []
    insight_count = len(insights) if isinstance(insights, list) else 0
    project_title = (
        _session_str("current_project_title")
        or _session_str("project_title_input")
        or ""
    )

    if status == "approved" and idea:
        idea_line = _diag_shorten(idea, limit=80)
    elif idea:
        idea_line = f"{_diag_shorten(idea, limit=70)} (még nem jóváhagyva)"
    else:
        idea_line = "—"

    items: list[tuple[str, str]] = [
        ("Igehely", passage),
        ("A textus fő gondolata", idea_line),
        ("Jóváhagyott felismerések", str(insight_count)),
    ]
    if project_title:
        items.append(("Projekt", project_title))
    render_context_summary(items)


def _sermon_main_idea_approved() -> bool:
    tw = ensure_text_workshop_state(st.session_state)
    idea = (tw.get("text_main_idea") or "").strip()
    status = (tw.get("text_main_idea_status") or "").strip()
    return bool(idea and status == "approved")


def _render_textus_basis_expander() -> None:
    """Csak olvasható Textusműhely-alapok — alapból összecsukva."""
    tw = ensure_text_workshop_state(st.session_state)
    with st.expander("Textusműhelyi alapok", expanded=False):
        idea = (tw.get("text_main_idea") or "").strip()
        status = (tw.get("text_main_idea_status") or "").strip()
        st.markdown("**A textus fő gondolata**")
        if idea:
            label = _STATUS_LABELS.get(status, status or "—")
            st.markdown(idea)
            st.caption(f"Státusz: {label}")
        else:
            st.caption("Még nincs megfogalmazva.")

        insights = tw.get("approved_insights") or []
        st.markdown("**Jóváhagyott felismerések**")
        if isinstance(insights, list) and insights:
            for item in insights:
                if not isinstance(item, dict):
                    continue
                content = (item.get("content") or "").strip()
                if not content:
                    continue
                cat = (item.get("category") or "").strip()
                src = (item.get("source") or "").strip()
                prefix = f"**{cat}** — " if cat else ""
                suffix = f" *(forrás: {src})*" if src else ""
                st.markdown(f"- {prefix}{content}{suffix}")
        else:
            st.caption("Még nincs jóváhagyott felismerés.")

        for key, label in (("exegesis", "Exegézis"), ("theology", "Teológia")):
            text = (st.session_state.get(key) or "").strip()
            if not text:
                continue
            with st.expander(label, expanded=False):
                st.markdown(text)


def _decision_is_duplicate(
    *,
    source_section: str,
    category: str,
    content: str,
) -> bool:
    sw = ensure_sermon_workshop_state(st.session_state)
    needle = (content or "").strip()
    for item in sw.get("approved_sermon_decisions") or []:
        if not isinstance(item, dict):
            continue
        if (
            (item.get("source_section") or "") == source_section
            and (item.get("category") or "") == category
            and (item.get("content") or "").strip() == needle
        ):
            return True
    return False


def _render_decisions_for_section(source_section: str) -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    items = [
        item
        for item in (sw.get("approved_sermon_decisions") or [])
        if isinstance(item, dict)
        and (item.get("source_section") or "") == source_section
    ]
    with st.expander("Jóváhagyott homiletikai döntések", expanded=False):
        if not items:
            st.caption("Ebben a szakaszban még nincs jóváhagyott döntés.")
            return
        for item in items:
            did = str(item.get("id") or "")
            if not did:
                continue
            category = item.get("category") or "—"
            content = item.get("content") or ""
            created = item.get("created_at") or ""
            with st.container(border=True):
                st.markdown(f"**{category}**")
                if created:
                    st.caption(f"Létrehozva: {created}")
                st.markdown(content)
                confirm_key = f"sw_decision_del_confirm_{did}"
                if st.session_state.get(confirm_key):
                    st.warning("Biztosan eltávolítod ezt a döntést?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "Igen, törlés",
                            key=f"sw_decision_del_yes_{did}",
                            type="primary",
                        ):
                            remove_approved_sermon_decision(st.session_state, did)
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                    with c2:
                        if st.button("Mégse", key=f"sw_decision_del_no_{did}"):
                            st.session_state[confirm_key] = False
                            st.rerun()
                else:
                    if st.button(
                        "Döntés eltávolítása",
                        key=f"sw_decision_del_{did}",
                    ):
                        st.session_state[confirm_key] = True
                        st.rerun()


def _run_sermon_suggest(generate_fn: GenerateFn) -> None:
    kwargs = _collect_m4_kwargs(
        sermon_main_idea=(st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    )
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt javaslatot kérsz."
        )
        return
    with st.spinner(
        "Az igehirdetés fő gondolatának lehetséges megfogalmazásait vizsgálom…"
    ):
        result = suggest_sermon_main_idea(**kwargs, generate_fn=generate_fn)
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_sermon_main_idea_suggestions(
        st.session_state,
        _suggestion_payload_from_result(result),
    )
    if not (result.recommended or "").strip():
        st.info(
            "A rendelkezésre álló anyag alapján nem készült felelős ajánlott "
            "fő gondolat. Nézd meg a hiányzó információkat és figyelmeztetéseket."
        )
    else:
        st.success("A javaslatok elkészültek.")


def _run_sermon_assess(generate_fn: GenerateFn) -> None:
    idea = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    if not idea:
        st.warning("Nincs megfogalmazás az értékeléshez.")
        return
    kwargs = _collect_m4_kwargs(sermon_main_idea=idea)
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt értékelést kérsz."
        )
        return
    with st.spinner(
        "A megfogalmazást textushűségi és hallhatósági szempontból vizsgálom…"
    ):
        result = assess_sermon_main_idea(**kwargs, generate_fn=generate_fn)
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="Az értékelés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_sermon_main_idea_assessment(
        st.session_state,
        _sermon_assessment_payload(result),
    )
    st.success("Az értékelés elkészült.")


def _render_sermon_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    sugs = sw.get("sermon_main_idea_suggestions")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslatok")
    generated_at = (sw.get("m4_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    recommended = (sugs.get("recommended") or "").strip()
    expanded = (sugs.get("expanded_summary") or "").strip()
    alternatives = sugs.get("alternatives") or []
    if not isinstance(alternatives, list):
        alternatives = []

    if recommended:
        with st.container(border=True):
            st.markdown("**Ajánlott fő gondolat**")
            st.markdown(recommended)
            if expanded:
                st.caption("Rövid kifejtés")
                st.markdown(expanded)
            if st.button("Átveszem", key="sw_mi_adopt_recommended"):
                _request_adopt_sermon_sentence(recommended)
    else:
        st.info(
            "Nincs ajánlott fő gondolat (elégtelen adat vagy a modell üresen hagyta). "
            "A részletek a „Mi alapján készült?” részben vannak."
        )

    alt_items: list[str] = []
    for alt in alternatives[:2]:
        text = (alt or "").strip() if isinstance(alt, str) else str(alt or "").strip()
        if text:
            alt_items.append(text)
    if alt_items:
        with st.expander("További javaslatok", expanded=False):
            for idx, text in enumerate(alt_items):
                with st.container(border=True):
                    st.markdown(f"**Alternatíva {idx + 1}**")
                    st.markdown(text)
                    if st.button("Átveszem", key=f"sw_mi_adopt_alt_{idx}"):
                        _request_adopt_sermon_sentence(text)

    reasoning = (sugs.get("reasoning_summary") or "").strip()
    basis = sugs.get("textual_and_homiletical_basis") or []
    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    has_basis = isinstance(basis, list) and any(str(x).strip() for x in basis)
    has_warnings = isinstance(warnings, list) and any(str(x).strip() for x in warnings)
    has_missing = isinstance(missing, list) and any(str(x).strip() for x in missing)

    if reasoning or has_basis or has_warnings or has_missing:
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.markdown("**Indoklás**")
                st.markdown(reasoning)
            if has_basis:
                st.markdown("**Szövegbeli és homiletikai alapok**")
                for item in basis:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")
            if has_warnings:
                st.markdown("**Figyelmeztetések**")
                for item in warnings:
                    line = str(item or "").strip()
                    if line:
                        st.warning(line)
            if has_missing:
                st.markdown("**Hiányzó információk**")
                for item in missing:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")


def _render_sermon_assessment_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    assessment_payload = sw.get("sermon_main_idea_assessment")
    if not isinstance(assessment_payload, dict):
        return

    fields = assessment_payload.get("assessment") or {}
    if not isinstance(fields, dict):
        fields = {}
    strengths = assessment_payload.get("strengths") or []
    priorities = assessment_payload.get("revision_priorities") or []
    revised = (assessment_payload.get("revised_version") or "").strip()
    warnings = assessment_payload.get("warnings") or []

    with st.expander("Szakmai értékelés részletei", expanded=False):
        if any(str(fields.get(k) or "").strip() for k, _ in _SERMON_ASSESSMENT_LABELS):
            st.markdown("**Szempontok**")
            for key, label in _SERMON_ASSESSMENT_LABELS:
                text = str(fields.get(key) or "").strip()
                if text:
                    st.markdown(f"**{label}:** {text}")

        if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
            st.markdown("**Erősségek**")
            for item in strengths[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        if isinstance(priorities, list) and any(str(x).strip() for x in priorities):
            st.markdown("**Javítási szempontok**")
            for item in priorities[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        if revised:
            st.markdown("**Átdolgozott javaslat**")
            st.markdown(revised)
            if st.button(
                "Átdolgozott változat átvétele",
                key="sw_mi_adopt_revised_sermon",
            ):
                _request_adopt_sermon_sentence(revised)
        else:
            st.caption(
                "Nincs átdolgozott javaslat (üres mező vagy elégtelen elemzési alap)."
            )

        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            st.markdown("**Figyelmeztetések**")
            for item in warnings:
                line = str(item or "").strip()
                if line:
                    st.warning(line)


def _run_hc_suggest(generate_fn: GenerateFn) -> None:
    kwargs = _collect_m4_kwargs(
        sermon_main_idea=(st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    )
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt javaslatot kérsz."
        )
        return
    with st.spinner(
        "A textus által feltárt emberi helyzetet és Isten kegyelmi "
        "cselekvését vizsgálom…"
    ):
        result = suggest_human_condition(**kwargs, generate_fn=generate_fn)
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_human_condition_suggestion(
        st.session_state,
        _hc_suggestion_payload(result),
    )
    if not (
        result.human_condition.strip()
        or result.divine_action.strip()
        or result.false_response.strip()
        or result.human_need.strip()
        or result.grace_response.strip()
    ):
        st.info(
            "A rendelkezésre álló anyag alapján nem készült felelős javaslat. "
            "Nézd meg a hiányzó információkat és figyelmeztetéseket."
        )
    else:
        st.success("A javaslat elkészült.")


def _run_hc_assess(generate_fn: GenerateFn) -> None:
    block = {
        field: (st.session_state.get(wkey) or "").strip()
        for field, wkey in _KEY_HC.items()
    }
    if not any(block.values()):
        st.warning("Nincs kitöltött elemzés az értékeléshez.")
        return
    kwargs = _collect_m4_kwargs(
        sermon_main_idea=(st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    )
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt értékelést kérsz."
        )
        return
    with st.spinner(
        "Az emberihelyzet-elemzést textushűségi és szakmai szempontból vizsgálom…"
    ):
        result = assess_human_condition(
            **kwargs,
            human_condition=block,
            generate_fn=generate_fn,
        )
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="Az értékelés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_human_condition_assessment(
        st.session_state,
        _hc_assessment_payload(result),
    )
    st.success("Az értékelés elkészült.")


def _render_hc_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    sugs = sw.get("human_condition_suggestion")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslat")
    generated_at = (sw.get("m4_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    any_field = False
    for key, label in _HC_SUGGEST_DISPLAY:
        value = str(sugs.get(key) or "").strip()
        with st.container(border=True):
            st.markdown(f"**{label}**")
            if value:
                any_field = True
                st.markdown(value)
            else:
                st.caption(
                    "Üresen hagyva — a textus alapján nem megalapozható, "
                    "vagy szándékosan nem kötelező mező."
                )

    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
        st.markdown("**Figyelmeztetések**")
        for item in warnings:
            line = str(item or "").strip()
            if line:
                st.warning(line)
    if isinstance(missing, list) and any(str(x).strip() for x in missing):
        st.markdown("**Hiányzó információk**")
        for item in missing:
            line = str(item or "").strip()
            if line:
                st.markdown(f"- {line}")

    ui_block = _prompt_block_to_ui(sugs)
    _render_overwrite_confirm(
        confirm_key=_ADOPT_HC_OVERWRITE_CONFIRM,
        pending_key=_ADOPT_HC_PENDING,
    )
    if any(ui_block.values()):
        if st.button("Javaslat átvétele", key="sw_mi_hc_adopt_suggestion"):
            _request_adopt_hc_block(ui_block)
    elif not any_field:
        st.info("Nincs átvehető javasolt mező.")


def _render_hc_assessment_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    assessment_payload = sw.get("human_condition_assessment")
    if not isinstance(assessment_payload, dict):
        return

    fields = assessment_payload.get("assessment") or {}
    if not isinstance(fields, dict):
        fields = {}
    strengths = assessment_payload.get("strengths") or []
    priorities = assessment_payload.get("revision_priorities") or []
    revised_raw = assessment_payload.get("revised_block") or {}
    if not isinstance(revised_raw, dict):
        revised_raw = {}
    warnings = assessment_payload.get("warnings") or []

    with st.expander("Szakmai értékelés részletei", expanded=False):
        if any(str(fields.get(k) or "").strip() for k, _ in _HC_ASSESSMENT_LABELS):
            st.markdown("**Szempontok**")
            for key, label in _HC_ASSESSMENT_LABELS:
                text = str(fields.get(key) or "").strip()
                if text:
                    st.markdown(f"**{label}:** {text}")

        if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
            st.markdown("**Erősségek**")
            for item in strengths[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        if isinstance(priorities, list) and any(str(x).strip() for x in priorities):
            st.markdown("**Javítási szempontok**")
            for item in priorities[:3]:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        st.markdown("**Átdolgozott blokk**")
        revised_ui = _prompt_block_to_ui(revised_raw)
        any_revised = False
        for key, label in _HC_SUGGEST_DISPLAY:
            ui_key = _HC_PROMPT_TO_UI[key]
            value = (revised_ui.get(ui_key) or "").strip()
            st.markdown(f"*{label}*")
            if value:
                any_revised = True
                st.markdown(value)
            else:
                st.caption("Üres")

        if any_revised:
            if st.button(
                "Átdolgozott blokk átvétele",
                key="sw_mi_hc_adopt_revised",
            ):
                _request_adopt_hc_block(revised_ui)
        else:
            st.caption(
                "Nincs átdolgozott javaslat (üres mezők vagy elégtelen elemzési alap)."
            )

        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            st.markdown("**Figyelmeztetések**")
            for item in warnings:
                line = str(item or "").strip()
                if line:
                    st.warning(line)


def render_text_core_and_focus_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Textusmag és fókuszmondat — három egymásra épülő, jóváhagyható elem.

    A textus fő gondolata és a Textusösszegzés a Textusműhely már meglévő,
    saját jóváhagyási körű mezői — ez a szakasz ugyanazokat a render-
    függvényeket (és ugyanazt a `text_workshop` állapotot) hívja meg, nem
    indít új, párhuzamos exegézist. A fókuszmondat marad az Igehirdetési
    műhely saját, prédikációra fókuszáló mezője.
    """
    st.markdown(
        "A textus saját állítása → a legfontosabb exegetikai/teológiai "
        "felismerések tömör összegzése → ebből egyetlen, prédikálható "
        "fókuszmondat. Mindhárom elem kézzel is megfogalmazható, MI-"
        "javaslattal is támogatható, és külön-külön jóváhagyható."
    )

    st.markdown("##### 1. A textus fő gondolata")
    render_text_main_idea_section(generate_fn=generate_fn)

    st.divider()
    st.markdown("##### 2. Textusösszegzés")
    tw = ensure_text_workshop_state(st.session_state)
    summary = tw.get("text_summary") or {}
    summary_status = (summary.get("status") or "draft").strip()
    base_tension = (summary.get("base_tension") or "").strip()
    st.caption(
        f"Állapot: **{_STATUS_LABELS.get(summary_status, summary_status)}** — "
        + (base_tension or "Még nincs megfogalmazva.")
    )
    with st.expander("Szerkesztés és részletek", expanded=False):
        render_text_summary_section(generate_fn=generate_fn)

    st.divider()
    st.markdown("##### 3. Fókuszmondat")
    render_sermon_main_idea_section(generate_fn=generate_fn)


def render_sermon_main_idea_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Az igehirdetés fő gondolata — kézi szerkesztő + opcionális MI-segéd."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    tw = ensure_text_workshop_state(st.session_state)

    render_work_section(
        title="Az igehirdetés fő gondolata",
        body=(
            "Fogalmazd meg egyetlen világos mondatban, mit szeretnél, hogy a "
            "hallgató a textus alapján felismerjen. Ez még nem cím és nem "
            "vázlat, hanem az egész igehirdetést összetartó állítás."
        ),
        context="Igehirdetési műhely",
    )

    passage = _session_str("last_igehely", "igehely_input") or "—"
    text_idea = (tw.get("text_main_idea") or "").strip()
    text_status = (tw.get("text_main_idea_status") or "").strip()
    insights = tw.get("approved_insights") or []
    insight_count = len(insights) if isinstance(insights, list) else 0

    render_context_summary(
        [
            ("Igehely", passage),
            ("A textus fő gondolata", text_idea or "—"),
            ("Jóváhagyott felismerések", str(insight_count)),
        ]
    )

    with work_surface("sw_sermon_idea"):
        # Egyetlen figyelmeztetés — a döntési mező közelében.
        if text_status != "approved" or not text_idea:
            render_info_panel(
                title="A textus fő gondolata még nincs jóváhagyva",
                body=(
                    "A szakasz használható, de a homiletikai munka biztosabb "
                    "alapokon áll, ha előbb a Textusműhelyben jóváhagyod."
                ),
                tone="info",
            )

        st.text_area(
            "Az igehirdetés fő gondolata",
            key=_KEY_SERMON_IDEA,
            height=120,
            label_visibility="collapsed",
            placeholder="Egyetlen, hallható állítás…",
        )

        with action_row("sw_sermon_idea"):
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Mentés vázlatként", key="sw_sermon_idea_save_draft"):
                    content = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
                    if not content:
                        st.warning("Üres fő gondolatot nem lehet menteni. Írj egy mondatot.")
                    else:
                        update_sermon_workshop_section(
                            st.session_state,
                            "sermon_main_idea",
                            {
                                "sermon_main_idea": content,
                                "sermon_main_idea_status": "draft",
                            },
                        )
                        _toast_and_rerun("Vázlatként elmentve.")
            with b2:
                if st.button(
                    "Jóváhagyom és átadom",
                    type="primary",
                    key="sw_sermon_idea_approve",
                ):
                    content = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
                    if not content:
                        st.warning(
                            "Üres fő gondolatot nem lehet jóváhagyni. Írj egy mondatot."
                        )
                    else:
                        update_sermon_workshop_section(
                            st.session_state,
                            "sermon_main_idea",
                            {
                                "sermon_main_idea": content,
                                "sermon_main_idea_status": "approved",
                            },
                        )
                        if _decision_is_duplicate(
                            source_section=_SOURCE_SERMON_MAIN,
                            category=_CAT_MAIN_IDEA,
                            content=content,
                        ):
                            _toast_and_rerun(
                                "Jóváhagyva. Ez a fő gondolat már szerepel a "
                                "homiletikai döntések között."
                            )
                        else:
                            add_approved_sermon_decision(
                                st.session_state,
                                _SOURCE_SERMON_MAIN,
                                _CAT_MAIN_IDEA,
                                content,
                            )
                            _toast_and_rerun(
                                "Jóváhagyva és továbbvíve a homiletikai döntésekhez."
                            )

        sw = ensure_sermon_workshop_state(st.session_state)
        saved = (sw.get("sermon_main_idea") or "").strip()
        saved_status = sw.get("sermon_main_idea_status") or ""
        if saved or saved_status:
            label = _STATUS_LABELS.get(saved_status, saved_status or "—")
            st.caption(f"Elmentett állapot: **{label}**")

    ai_ready = generate_fn is not None
    idea_draft = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    with mi_helper_zone(
        "sw_sermon_idea",
        title="MI-segéd",
        body=(
            "Az MI a jóváhagyott textusműhelyi eredményekből segít "
            "megfogalmazni és megvizsgálni az igehirdetés fő gondolatát. "
            "A végső döntés továbbra is a prédikátoré."
        ),
    ):
        a1, a2 = st.columns(2)
        with a1:
            if st.button(
                "Javaslatok készítése",
                key="sw_mi_sermon_suggest",
                disabled=not ai_ready,
            ):
                if generate_fn is None:
                    st.warning("Az MI-segéd jelenleg nem elérhető.")
                else:
                    _run_sermon_suggest(generate_fn)
        with a2:
            if st.button(
                "Saját megfogalmazás értékelése",
                key="sw_mi_sermon_assess",
                disabled=not ai_ready or not idea_draft,
            ):
                if generate_fn is None:
                    st.warning("Az MI-segéd jelenleg nem elérhető.")
                else:
                    _run_sermon_assess(generate_fn)

    _render_sermon_suggestion_results()
    _render_sermon_assessment_results()
    _render_textus_basis_expander()
    _render_decisions_for_section(_SOURCE_SERMON_MAIN)


def render_human_condition_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Emberi helyzet és kegyelmi válasz — kézi szerkesztő + opcionális MI-segéd."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    _show_adopt_feedback_if_any()

    st.subheader("Emberi helyzet és kegyelmi válasz")
    st.markdown(
        "Vizsgáld meg, milyen emberi helyzetet tár fel a textus, és mit "
        "cselekszik ebben a helyzetben Isten. Ne csak problémát keress: "
        "figyelj a korlátozottságra, téves bizalomra, félelemre, vágyra, "
        "törésre és reménységre is."
    )

    for field, label, _category, _optional in _HC_FIELDS:
        st.text_area(
            label,
            key=_KEY_HC[field],
            height=80,
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_hc_save_draft"):
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_HC.items()
            }
            if not (block["condition"] or block["divine_action"]):
                st.warning(
                    "A mentéshez legalább az emberi helyzet vagy Isten "
                    "cselekvése mezőt töltsd ki."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "human_condition", block
                )
                update_sermon_workshop_section(
                    st.session_state, "human_condition_status", "draft"
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            type="primary",
            key="sw_hc_approve",
        ):
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_HC.items()
            }
            if not (block["condition"] or block["divine_action"]):
                st.warning(
                    "A jóváhagyáshoz legalább az emberi helyzet vagy Isten "
                    "cselekvése mezőt töltsd ki."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "human_condition", block
                )
                update_sermon_workshop_section(
                    st.session_state, "human_condition_status", "approved"
                )
                added = 0
                skipped = 0
                for field, _label, category, _optional in _HC_FIELDS:
                    content = block.get(field) or ""
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_HUMAN,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_HUMAN,
                        category,
                        content,
                    )
                    added += 1
                if added and skipped:
                    st.success(
                        f"Jóváhagyva. {added} új döntés került továbbvitelre; "
                        f"{skipped} már szerepelt."
                    )
                elif added:
                    st.success(
                        f"Jóváhagyva és továbbvíve ({added} homiletikai döntés)."
                    )
                else:
                    st.success(
                        "Jóváhagyva. A kitöltött elemek már szerepeltek a "
                        "homiletikai döntések között."
                    )

    st.markdown("---")
    st.markdown("**MI-segéd**")
    st.caption(
        "Az MI a jóváhagyott textusműhelyi eredményekből segít "
        "megfogalmazni és megvizsgálni az emberi helyzetet és a kegyelmi választ. "
        "A végső döntés továbbra is a prédikátoré."
    )
    ai_ready = generate_fn is not None
    hc_filled = any(
        (st.session_state.get(wkey) or "").strip() for wkey in _KEY_HC.values()
    )
    a1, a2 = st.columns(2)
    with a1:
        if st.button(
            "Javaslat készítése",
            key="sw_mi_hc_suggest",
            disabled=not ai_ready,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_hc_suggest(generate_fn)
    with a2:
        if st.button(
            "Saját elemzés értékelése",
            key="sw_mi_hc_assess",
            disabled=not ai_ready or not hc_filled,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_hc_assess(generate_fn)

    _render_hc_suggestion_results()
    _render_hc_assessment_results()

    _render_decisions_for_section(_SOURCE_HUMAN)


def _run_lt_suggest(generate_fn: GenerateFn) -> None:
    kwargs = _collect_m5_kwargs()
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt javaslatot kérsz."
        )
        return
    with st.spinner(
        "A hallgatói kérdést, ellenállást és a prédikációt mozgató "
        "feszültséget vizsgálom…"
    ):
        result = suggest_listener_tension(**kwargs, generate_fn=generate_fn)
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_listener_tension_suggestions(
        st.session_state,
        _lt_suggestion_payload(result),
    )
    if not (
        result.recommended_listener_question.strip()
        or result.recommended_listener_resistance.strip()
        or result.recommended_tension.strip()
    ):
        st.info(
            "A rendelkezésre álló anyag alapján nem készült felelős javaslat. "
            "Nézd meg a hiányzó információkat és figyelmeztetéseket."
        )
    else:
        st.success("A javaslatok elkészültek.")


def _run_lt_assess(generate_fn: GenerateFn) -> None:
    block = {
        field: (st.session_state.get(wkey) or "").strip()
        for field, wkey in _KEY_LT.items()
    }
    if not any(block.values()):
        st.warning("Nincs kitöltött megfogalmazás az értékeléshez.")
        return
    kwargs = _collect_m5_kwargs()
    if not kwargs["passage"]:
        st.warning(
            "Add meg az igeszakaszt az „Igehely” szakaszon, mielőtt értékelést kérsz."
        )
        return
    with st.spinner(
        "A hallgatói kérdés, ellenállás és feszültség megfogalmazását vizsgálom…"
    ):
        result = assess_listener_tension(
            **kwargs,
            listener_tension=block,
            generate_fn=generate_fn,
        )
    if not result.ok:
        st.warning(
            _user_facing_error(
                False,
                result.error_message,
                fallback="Az értékelés nem sikerült. Próbáld újra később.",
            )
        )
        return
    save_listener_tension_assessment(
        st.session_state,
        _lt_assessment_payload(result),
    )
    st.success("Az értékelés elkészült.")


def _render_lt_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    sugs = sw.get("listener_tension_suggestions")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslatok")
    generated_at = (sw.get("m5_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    q = str(sugs.get("recommended_listener_question") or "").strip()
    r = str(sugs.get("recommended_listener_resistance") or "").strip()
    t = str(sugs.get("recommended_tension") or "").strip()
    expanded = str(sugs.get("expanded_summary") or "").strip()

    with st.container(border=True):
        st.markdown("**Ajánlott hallgatói kérdés**")
        st.markdown(q or "—")
        st.markdown("**Ajánlott hallgatói ellenállás**")
        st.markdown(r or "—")
        st.markdown("**Ajánlott központi feszültség**")
        st.markdown(t or "—")
        if expanded:
            st.caption("Rövid kifejtés")
            st.markdown(expanded)

        ui_all = {
            "listener_question": q,
            "listener_resistance": r,
            "sermon_tension": t,
        }
        if any(ui_all.values()):
            _tt_item_help = "Csak ezt az elemet veszem át."
            with st.container(key="tension_transfer_actions"):
                if st.button(
                    "Mind átvétele",
                    type="primary",
                    key="sw_mi_lt_adopt_all",
                ):
                    _request_adopt_lt_block(ui_all)
                st.markdown(
                    '<div class="tx-tt-sep" aria-hidden="true"></div>',
                    unsafe_allow_html=True,
                )
                if q and st.button(
                    "Kérdés",
                    key="sw_mi_lt_adopt_q",
                    help=_tt_item_help,
                ):
                    _request_adopt_lt_block({"listener_question": q})
                if r and st.button(
                    "Ellenállás",
                    key="sw_mi_lt_adopt_r",
                    help=_tt_item_help,
                ):
                    _request_adopt_lt_block({"listener_resistance": r})
                if t and st.button(
                    "Feszültség",
                    key="sw_mi_lt_adopt_t",
                    help=_tt_item_help,
                ):
                    _request_adopt_lt_block({"sermon_tension": t})
        else:
            st.info(
                "Nincs átvehető ajánlás (elégtelen adat vagy üres modellválasz)."
            )

    alt_sets = sugs.get("alternative_sets") or []
    if isinstance(alt_sets, list) and alt_sets:
        with st.expander("További javaslatok", expanded=False):
            for idx, alt in enumerate(alt_sets[:2]):
                if not isinstance(alt, dict):
                    continue
                aq = str(alt.get("listener_question") or "").strip()
                ar = str(alt.get("listener_resistance") or "").strip()
                at = str(alt.get("tension") or "").strip()
                if not (aq or ar or at):
                    continue
                with st.container(border=True):
                    st.markdown(f"**Alternatíva {idx + 1}**")
                    if aq:
                        st.markdown(f"*Kérdés:* {aq}")
                    if ar:
                        st.markdown(f"*Ellenállás:* {ar}")
                    if at:
                        st.markdown(f"*Feszültség:* {at}")
                    if st.button(
                        "Átveszem ezt a hármast",
                        key=f"sw_mi_lt_adopt_alt_{idx}",
                    ):
                        _request_adopt_lt_block(
                            {
                                "listener_question": aq,
                                "listener_resistance": ar,
                                "sermon_tension": at,
                            }
                        )

    reasoning = str(sugs.get("reasoning_summary") or "").strip()
    basis = sugs.get("basis") or []
    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    has_basis = isinstance(basis, list) and any(str(x).strip() for x in basis)
    has_warnings = isinstance(warnings, list) and any(str(x).strip() for x in warnings)
    has_missing = isinstance(missing, list) and any(str(x).strip() for x in missing)
    if reasoning or has_basis or has_warnings or has_missing:
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.markdown("**Indoklás**")
                st.markdown(reasoning)
            if has_basis:
                st.markdown("**Alapok**")
                for item in basis:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")
            if has_warnings:
                st.markdown("**Figyelmeztetések**")
                for item in warnings:
                    line = str(item or "").strip()
                    if line:
                        st.warning(line)
            if has_missing:
                st.markdown("**Hiányzó információk**")
                for item in missing:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")


def _render_lt_assessment_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    payload = sw.get("listener_tension_assessment")
    if not isinstance(payload, dict):
        return

    overall = str(payload.get("overall_assessment") or "").strip()
    strengths = payload.get("strengths") or []
    improvements = payload.get("improvements") or []
    rq = str(payload.get("revised_listener_question") or "").strip()
    rr = str(payload.get("revised_listener_resistance") or "").strip()
    rt = str(payload.get("revised_tension") or "").strip()
    warnings = payload.get("warnings") or []

    with st.expander("Szakmai értékelés részletei", expanded=False):
        if overall:
            st.markdown("**Összegzés**")
            st.markdown(overall)
        if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
            st.markdown("**Erősségek**")
            for item in strengths:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")
        if isinstance(improvements, list) and any(str(x).strip() for x in improvements):
            st.markdown("**Javítási szempontok**")
            for item in improvements:
                line = str(item or "").strip()
                if line:
                    st.markdown(f"- {line}")

        st.markdown("**Átdolgozott javaslatok**")
        if rq:
            st.markdown(f"*Hallgatói kérdés:* {rq}")
            if st.button("Átdolgozott kérdés átvétele", key="sw_mi_lt_adopt_rev_q"):
                _request_adopt_lt_block({"listener_question": rq})
        if rr:
            st.markdown(f"*Hallgatói ellenállás:* {rr}")
            if st.button(
                "Átdolgozott ellenállás átvétele", key="sw_mi_lt_adopt_rev_r"
            ):
                _request_adopt_lt_block({"listener_resistance": rr})
        if rt:
            st.markdown(f"*Központi feszültség:* {rt}")
            if st.button(
                "Átdolgozott feszültség átvétele", key="sw_mi_lt_adopt_rev_t"
            ):
                _request_adopt_lt_block({"sermon_tension": rt})
        if rq or rr or rt:
            if st.button(
                "Átdolgozott hármas átvétele", key="sw_mi_lt_adopt_rev_all"
            ):
                _request_adopt_lt_block(
                    {
                        "listener_question": rq,
                        "listener_resistance": rr,
                        "sermon_tension": rt,
                    }
                )
        else:
            st.caption("Nincs átdolgozott javaslat.")

        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            st.markdown("**Figyelmeztetések**")
            for item in warnings:
                line = str(item or "").strip()
                if line:
                    st.warning(line)


def render_listener_tension_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Hallgatói kérdés és feszültség — kézi szerkesztő + opcionális MI-segéd."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    tw = ensure_text_workshop_state(st.session_state)

    st.subheader("Hallgatói kérdés és feszültség")
    st.markdown(
        "Tisztázd, milyen valódi kérdést, nehézséget vagy ellenállást érinthet "
        "a textus a hallgatóban. A cél nem mesterséges dráma, hanem a "
        "felismeréshez vezető feszültség megnevezése."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    text_idea = (tw.get("text_main_idea") or "").strip()
    text_status = (tw.get("text_main_idea_status") or "").strip()
    sermon_idea = (sw.get("sermon_main_idea") or "").strip()
    sermon_status = (sw.get("sermon_main_idea_status") or "").strip()
    if text_status != "approved" and sermon_status != "approved":
        st.info(
            "A szakasz használható, de a munka biztosabb, ha előbb jóváhagyod "
            "a textus vagy az igehirdetés fő gondolatát."
        )
    elif sermon_status != "approved" and not sermon_idea:
        st.caption(
            f"Textus fő gondolat: {(text_idea[:120] + '…') if len(text_idea) > 120 else text_idea or '—'}"
        )

    for field, title, help_text, placeholder, _category in _LT_FIELDS:
        st.markdown(f"**{title}**")
        st.caption(help_text)
        st.text_area(
            title,
            key=_KEY_LT[field],
            height=90,
            label_visibility="collapsed",
            placeholder=placeholder,
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_lt_save_draft"):
            current = (
                sw.get("listener_tension")
                if isinstance(sw.get("listener_tension"), dict)
                else {}
            )
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_LT.items()
            }
            block["promised_resolution"] = str(
                current.get("promised_resolution") or ""
            )
            if not any(block[f] for f in _KEY_LT):
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                update_sermon_workshop_section(
                    st.session_state, "listener_tension", block
                )
                update_sermon_workshop_section(
                    st.session_state, "listener_tension_status", "draft"
                )
                st.success("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            type="primary",
            key="sw_lt_approve",
        ):
            current = (
                sw.get("listener_tension")
                if isinstance(sw.get("listener_tension"), dict)
                else {}
            )
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_LT.items()
            }
            block["promised_resolution"] = str(
                current.get("promised_resolution") or ""
            )
            if not any(block[f] for f in _KEY_LT):
                st.warning(
                    "Üres megfogalmazást nem lehet jóváhagyni. Tölts ki legalább egyet."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "listener_tension", block
                )
                update_sermon_workshop_section(
                    st.session_state, "listener_tension_status", "approved"
                )
                added = 0
                skipped = 0
                for field, _title, _help, _ph, category in _LT_FIELDS:
                    content = block.get(field) or ""
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_LISTENER,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_LISTENER,
                        category,
                        content,
                    )
                    added += 1
                if added and skipped:
                    st.success(
                        f"Jóváhagyva. {added} új döntés került továbbvitelre; "
                        f"{skipped} már szerepelt."
                    )
                elif added:
                    st.success(
                        f"Jóváhagyva és továbbvíve ({added} homiletikai döntés)."
                    )
                else:
                    st.success(
                        "Jóváhagyva. A kitöltött elemek már szerepeltek a "
                        "homiletikai döntések között."
                    )

    saved = ensure_sermon_workshop_state(st.session_state).get("listener_tension") or {}
    if isinstance(saved, dict) and any(str(saved.get(k) or "").strip() for k in _KEY_LT):
        st.caption("Elmentett állapot: **vázlat / jóváhagyott döntésekkel** (lásd lent)")

    st.markdown("---")
    st.markdown("**MI-segéd**")
    st.caption(
        "Az MI a jóváhagyott textus- és igehirdetési műhelyeredményekből segít "
        "megfogalmazni a hallgatói kérdést, az ellenállást és a központi "
        "feszültséget. A végső döntés továbbra is a prédikátoré."
    )
    ai_ready = generate_fn is not None
    lt_filled = any(
        (st.session_state.get(wkey) or "").strip() for wkey in _KEY_LT.values()
    )
    a1, a2 = st.columns(2)
    with a1:
        if st.button(
            "Javaslatok készítése",
            key="sw_mi_lt_suggest",
            disabled=not ai_ready,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_lt_suggest(generate_fn)
    with a2:
        if st.button(
            "Saját megfogalmazás értékelése",
            key="sw_mi_lt_assess",
            disabled=not ai_ready or not lt_filled,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_lt_assess(generate_fn)

    _render_lt_suggestion_results()
    _render_lt_assessment_results()

    _render_decisions_for_section(_SOURCE_LISTENER)


def _apply_pending_entry_point_adopt_if_needed() -> None:
    """Belépésipont-javaslat átvétele: widget ELŐTT (pending + rerun)."""
    pending = st.session_state.pop(_ADOPT_ENTRY_PENDING, None)
    if isinstance(pending, dict):
        type_key = normalize_entry_point_type(pending.get("type"))
        text = str(pending.get("text") or "").strip()
        st.session_state[_KEY_ENTRY["type"]] = type_key
        st.session_state[_KEY_ENTRY["text"]] = text
        update_sermon_workshop_section(
            st.session_state, "entry_point", {"type": type_key, "text": text}
        )
        _mark_adopt_feedback()

    pending_today = st.session_state.pop(_ADOPT_ENTRY_TODAY_PENDING, None)
    if pending_today is not None:
        text = str(pending_today).strip()
        st.session_state[_KEY_ENTRY["today_connection"]] = text
        update_sermon_workshop_section(
            st.session_state, "entry_point", {"today_connection": text}
        )
        _mark_adopt_feedback()


def _request_adopt_entry_point_option(type_key: str, text: str) -> None:
    st.session_state[_ADOPT_ENTRY_PENDING] = {"type": type_key, "text": text}
    st.rerun()


def _request_adopt_entry_point_today(text: str) -> None:
    st.session_state[_ADOPT_ENTRY_TODAY_PENDING] = text
    st.rerun()


def _run_entry_point_suggest(generate_fn: GenerateFn) -> None:
    if st.session_state.get("_sw_entry_suggest_running"):
        return
    st.session_state["_sw_entry_suggest_running"] = True
    try:
        tw = ensure_text_workshop_state(st.session_state)
        sw = ensure_sermon_workshop_state(st.session_state)
        summary = tw.get("text_summary") if isinstance(tw.get("text_summary"), dict) else {}
        summary_approved = (summary.get("status") or "") == "approved"
        kwargs = {
            "passage": (
                st.session_state.get("last_igehely")
                or st.session_state.get("igehely_input")
                or ""
            ).strip(),
            "text_summary_main_idea": (
                (summary.get("main_idea") or "") if summary_approved else ""
            )
            or (tw.get("text_main_idea") or ""),
            "text_summary_base_tension": (
                (summary.get("base_tension") or "") if summary_approved else ""
            ),
            "sermon_main_idea": sw.get("sermon_main_idea") or "",
            "human_condition": sw.get("human_condition") or {},
            "listener_tension": sw.get("listener_tension") or {},
        }
        if not kwargs["passage"]:
            st.warning(
                "Add meg az igeszakaszt a Textusműhelyben, mielőtt javaslatot kérsz."
            )
            return

        with st.spinner("Homiletikai belépési pont javaslatok készülnek…"):
            result: EntryPointSuggestionResult = suggest_entry_point(
                **kwargs, generate_fn=generate_fn
            )

        if not result.ok:
            st.warning(
                _user_facing_entry_point_error(
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
                )
            )
            return

        save_entry_point_suggestions(st.session_state, result.to_dict())
        if not (result.today_connection or result.options):
            st.info(
                "A rendelkezésre álló anyag alapján nem készült érdemi javaslat. "
                "Nézd meg a hiányzó információkat és figyelmeztetéseket."
            )
        else:
            st.success("A javaslatok elkészültek.")
    finally:
        st.session_state["_sw_entry_suggest_running"] = False


def _user_facing_entry_point_error(error_message: str, *, fallback: str) -> str:
    msg = (error_message or "").strip()
    if not msg:
        return fallback
    if len(msg) > 280:
        return fallback
    lower = msg.casefold()
    if "api key" in lower or "apikey" in lower or "x-goog-api-key" in lower:
        return fallback
    return msg


def _render_entry_point_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    sugs = sw.get("entry_point_suggestions")
    if not isinstance(sugs, dict):
        return

    st.subheader("MI-javaslatok")
    generated_at = (sw.get("entry_point_last_generated_at") or "").strip()
    if generated_at:
        st.caption(f"Utolsó generálás: {generated_at}")

    today = (sugs.get("today_connection") or "").strip()
    if today:
        with st.container(border=True):
            st.markdown("**Mai kapcsolódás — javaslat**")
            st.markdown(today)
            if st.button("Átveszem", key="sw_entry_adopt_today"):
                _request_adopt_entry_point_today(today)

    options = sugs.get("options") or []
    if isinstance(options, list) and options:
        for idx, opt in enumerate(options):
            if not isinstance(opt, dict):
                continue
            type_key = normalize_entry_point_type(opt.get("type"))
            text = (opt.get("text") or "").strip()
            if not text:
                continue
            with st.container(border=True):
                st.markdown(f"**{entry_point_type_label(type_key)}**")
                st.markdown(text)
                if st.button("Átveszem", key=f"sw_entry_adopt_option_{idx}"):
                    _request_adopt_entry_point_option(type_key, text)
    else:
        st.info(
            "Nincs javaslat (elégtelen adat vagy a modell üresen hagyta). "
            "A részletek a figyelmeztetéseknél/hiányzó információknál "
            "találhatók."
        )

    reasoning = (sugs.get("reasoning_summary") or "").strip()
    warnings = sugs.get("warnings") or []
    missing = sugs.get("missing_information") or []
    has_warnings = isinstance(warnings, list) and any(str(x).strip() for x in warnings)
    has_missing = isinstance(missing, list) and any(str(x).strip() for x in missing)
    if reasoning or has_warnings or has_missing:
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.markdown("**Indoklás**")
                st.markdown(reasoning)
            if has_warnings:
                st.markdown("**Figyelmeztetések**")
                for item in warnings:
                    line = str(item or "").strip()
                    if line:
                        st.warning(line)
            if has_missing:
                st.markdown("**Hiányzó információk**")
                for item in missing:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")


def render_entry_point_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Mai kapcsolódás + belépési pont típusa/szövege — kézi szerkesztő + MI-segéd.

    Az emberi helyzet és a hallgatói feszültség változatlanul, saját
    szakaszként (render_human_condition_section / render_listener_tension_section)
    marad meg — ez a szakasz csak kiegészíti azokat a mai kapcsolódással és
    a konkrét belépési ponttal. A típusválasztó nem kötelező: "Nincs külön
    belépési pont" is választható, és a mező üresen hagyható/kihagyható.
    """
    _apply_sw_ui_resync_if_needed()
    _apply_pending_entry_point_adopt_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.markdown("---")
    st.subheader("Mai kapcsolódás és belépési pont")
    st.markdown(
        "Hogyan találkozik a textus alapfeszültsége a hallgató jelenlegi "
        "élethelyzetével, és milyen konkrét nyitó mozzanat viheti be a "
        "hallgatót a textusba? A típusválasztó nem kötelező — hagyható "
        "„Nincs külön belépési pont” állapotban is."
    )

    st.text_area(
        "Mai kapcsolódás",
        key=_KEY_ENTRY["today_connection"],
        height=90,
        placeholder=(
            "Hogyan találkozik a textus alapfeszültsége a hallgató mai "
            "élethelyzetével?"
        ),
    )

    type_options = ("",) + ENTRY_POINT_TYPE_KEYS
    st.selectbox(
        "Belépési pont típusa",
        options=type_options,
        format_func=entry_point_type_label,
        key=_KEY_ENTRY["type"],
        help="Opcionális — választhatod a „Nincs külön belépési pont” állapotot is.",
    )
    st.text_area(
        "Belépési pont szövege",
        key=_KEY_ENTRY["text"],
        height=90,
        placeholder="A konkrét kérdés, eset, tapasztalat, kép vagy felütés szövege…",
    )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_entry_save_draft"):
            _persist_entry_point_from_widgets()
            update_sermon_workshop_section(
                st.session_state, "entry_point_status", "draft"
            )
            _toast_and_rerun("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            type="primary",
            key="sw_entry_approve",
        ):
            _persist_entry_point_from_widgets()
            update_sermon_workshop_section(
                st.session_state, "entry_point_status", "approved"
            )
            entry = ensure_sermon_workshop_state(st.session_state).get(
                "entry_point"
            ) or {}
            decisions = [
                ("Mai kapcsolódás", entry.get("today_connection")),
                (
                    entry_point_type_label(entry.get("type")),
                    entry.get("text"),
                ),
            ]
            added = 0
            skipped = 0
            for category, content in decisions:
                content = (content or "").strip()
                if not content:
                    continue
                if _decision_is_duplicate(
                    source_section=_SOURCE_ENTRY,
                    category=category,
                    content=content,
                ):
                    skipped += 1
                    continue
                add_approved_sermon_decision(
                    st.session_state, _SOURCE_ENTRY, category, content
                )
                added += 1
            if added:
                _toast_and_rerun(f"Jóváhagyva ({added} döntés).")
            elif skipped:
                _toast_and_rerun("Jóváhagyva. Ezek a döntések már szerepelnek.")
            else:
                _toast_and_rerun("Jóváhagyva. A belépési pont egyelőre üres — bármikor kiegészítheted.")

    sw = ensure_sermon_workshop_state(st.session_state)
    status = sw.get("entry_point_status") or "draft"
    st.caption(f"Elmentett állapot: **{_STATUS_LABELS.get(status, status)}**")

    ai_ready = generate_fn is not None
    st.markdown("---")
    st.markdown("**MI-segéd**")
    st.caption(
        "Egy hívással 2-3 rövid, eltérő típusú belépési pont javaslatot ad "
        "a jóváhagyott Textusösszegzés, az emberi helyzet és a hallgatói "
        "feszültség alapján. A végső megfogalmazás és jóváhagyás a "
        "prédikátor döntése."
    )
    if st.button(
        "Javaslatok készítése",
        key="sw_entry_suggest",
        disabled=not ai_ready or bool(st.session_state.get("_sw_entry_suggest_running")),
    ):
        if generate_fn is None:
            st.warning("Az MI-segéd jelenleg nem elérhető.")
        else:
            _run_entry_point_suggest(generate_fn)
    if not ai_ready:
        st.caption("Az MI-segéd nincs bekötve ehhez a nézethez.")

    _render_entry_point_suggestion_results()
    _render_decisions_for_section(_SOURCE_ENTRY)


def _run_ga_suggest(generate_fn: GenerateFn) -> None:
    if st.session_state.get("_sw_m5_ga_suggest_running"):
        return
    st.session_state["_sw_m5_ga_suggest_running"] = True
    try:
        kwargs = _collect_gospel_arc_kwargs()
        with st.spinner("Evangéliumi ív javaslat készül…"):
            result = suggest_gospel_arc(**kwargs, generate_fn=generate_fn)
        save_gospel_arc_suggestions(
            st.session_state, _ga_suggestion_payload(result)
        )
        if result.ok and (
            result.recommended_divine_gracious_action
            or result.recommended_christ_connection
            or result.recommended_promised_resolution
            or result.recommended_grace_enabled_response
        ):
            st.success("A javaslatok elkészültek.")
        elif result.ok:
            st.info(
                result.reasoning_summary
                or "Nincs elegendő anyag felelős javaslathoz."
            )
        else:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült. Próbáld újra később.",
                )
            )
    finally:
        st.session_state["_sw_m5_ga_suggest_running"] = False


def _run_ga_assess(generate_fn: GenerateFn) -> None:
    if st.session_state.get("_sw_m5_ga_assess_running"):
        return
    st.session_state["_sw_m5_ga_assess_running"] = True
    try:
        kwargs = _collect_gospel_arc_kwargs()
        with st.spinner("Az evangéliumi ív értékelése készül…"):
            result = assess_gospel_arc(
                **kwargs,
                generate_fn=generate_fn,
            )
        save_gospel_arc_assessment(
            st.session_state, _ga_assessment_payload(result)
        )
        if result.ok:
            st.success("Az értékelés elkészült.")
        else:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült. Próbáld újra később.",
                )
            )
    finally:
        st.session_state["_sw_m5_ga_assess_running"] = False


def _render_ga_suggestion_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("gospel_arc_suggestions")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not any(
        str(data.get(k) or "").strip()
        for k in (
            "recommended_divine_gracious_action",
            "recommended_christ_connection",
            "recommended_promised_resolution",
            "recommended_grace_enabled_response",
        )
    ):
        err = _user_facing_error(
            False,
            str(data.get("error_message") or ""),
            fallback="A legutóbbi javaslatkészítés nem sikerült.",
        )
        if err:
            st.warning(err)
        return

    divine = str(data.get("recommended_divine_gracious_action") or "").strip()
    christ = str(data.get("recommended_christ_connection") or "").strip()
    ctype = normalize_christ_connection_type(
        data.get("recommended_christ_connection_type")
    )
    resolution = str(data.get("recommended_promised_resolution") or "").strip()
    grace = str(data.get("recommended_grace_enabled_response") or "").strip()
    expanded = str(data.get("expanded_summary") or "").strip()
    confidence = str(data.get("confidence") or "low").strip().casefold()
    if not (divine or christ or resolution or grace or expanded):
        missing = data.get("missing_information") or []
        warnings = data.get("warnings") or []
        if missing or warnings:
            st.markdown("**MI-javaslat**")
            for item in warnings if isinstance(warnings, list) else []:
                line = str(item or "").strip()
                if line:
                    st.warning(line)
            if isinstance(missing, list) and any(str(x).strip() for x in missing):
                st.caption("Hiányzó információk: " + "; ".join(
                    str(x).strip() for x in missing if str(x).strip()
                ))
        return

    st.markdown("**MI-javaslat**")
    if divine:
        st.markdown(f"**Isten kegyelmi cselekvése**  \n{divine}")
    if christ:
        st.markdown(f"**Krisztus-kapcsolat**  \n{christ}")
    st.markdown(
        f"**Kapcsolat típusa:** {christ_connection_type_label(ctype)}  \n"
        f"**Bizonyosság:** {_CONFIDENCE_LABELS_HU.get(confidence, confidence)}"
    )
    if ctype == "none_or_uncertain":
        st.info(
            "A rendelkezésre álló anyag alapján a konkrét Krisztus-kapcsolat még "
            "további vizsgálatot igényel."
        )
    if resolution:
        st.markdown(f"**Evangéliumi feloldás**  \n{resolution}")
    if grace:
        st.markdown(f"**Kegyelemből fakadó válasz**  \n{grace}")
    if expanded:
        st.markdown("**Rövid kifejtés**")
        st.write(expanded)

    if st.button("Átveszem mindet", key="sw_mi_ga_adopt_all"):
        _request_adopt_ga_block(
            {
                "divine_gracious_action": divine,
                "christ_connection": christ,
                "christ_connection_type": ctype,
                "promised_resolution": resolution,
                "grace_enabled_response": grace,
            }
        )

    c1, c2 = st.columns(2)
    with c1:
        if divine and st.button(
            "Kegyelmi cselekvés átvétele", key="sw_mi_ga_adopt_divine"
        ):
            _request_adopt_ga_block({"divine_gracious_action": divine})
        if christ and st.button(
            "Krisztus-kapcsolat átvétele", key="sw_mi_ga_adopt_christ"
        ):
            _request_adopt_ga_block(
                {"christ_connection": christ, "christ_connection_type": ctype}
            )
    with c2:
        if resolution and st.button(
            "Feloldás átvétele", key="sw_mi_ga_adopt_resolution"
        ):
            _request_adopt_ga_block({"promised_resolution": resolution})
        if grace and st.button(
            "Emberi válasz átvétele", key="sw_mi_ga_adopt_grace"
        ):
            _request_adopt_ga_block({"grace_enabled_response": grace})
    if ctype and st.button(
        "Kapcsolattípus átvétele", key="sw_mi_ga_adopt_type"
    ):
        _request_adopt_ga_block({"christ_connection_type": ctype})

    alts = data.get("alternative_connections") or []
    if isinstance(alts, list) and any(isinstance(a, dict) for a in alts):
        with st.expander("Alternatív kapcsolódási irányok", expanded=False):
            for idx, alt in enumerate(alts[:2]):
                if not isinstance(alt, dict):
                    continue
                a_conn = str(alt.get("christ_connection") or "").strip()
                a_type = normalize_christ_connection_type(alt.get("connection_type"))
                a_emp = str(alt.get("emphasis") or "").strip()
                if not (a_conn or a_emp):
                    continue
                st.markdown(
                    f"**Alternatíva {idx + 1}** — "
                    f"{christ_connection_type_label(a_type)}"
                )
                if a_conn:
                    st.write(a_conn)
                if a_emp:
                    st.caption(f"Hangsúly: {a_emp}")
                if st.button(
                    "Ezt a kapcsolatot átveszem",
                    key=f"sw_mi_ga_adopt_alt_{idx}",
                ):
                    _request_adopt_ga_block(
                        {
                            "christ_connection": a_conn,
                            "christ_connection_type": a_type,
                        }
                    )

    basis = data.get("basis") or []
    reasoning = str(data.get("reasoning_summary") or "").strip()
    if reasoning or (isinstance(basis, list) and any(str(x).strip() for x in basis)):
        with st.expander("Mi alapján készült?", expanded=False):
            if reasoning:
                st.write(reasoning)
            if isinstance(basis, list):
                for item in basis:
                    line = str(item or "").strip()
                    if line:
                        st.markdown(f"- {line}")

    warnings = data.get("warnings") or []
    missing = data.get("missing_information") or []
    if isinstance(warnings, list):
        for item in warnings:
            line = str(item or "").strip()
            if line:
                st.warning(line)
    if isinstance(missing, list) and any(str(x).strip() for x in missing):
        st.caption(
            "Hiányzó információk: "
            + "; ".join(str(x).strip() for x in missing if str(x).strip())
        )


def _render_ga_assessment_results() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("gospel_arc_assessment")
    if not isinstance(data, dict):
        return
    if data.get("ok") is False and not str(data.get("overall_assessment") or "").strip():
        err = _user_facing_error(
            False,
            str(data.get("error_message") or ""),
            fallback="A legutóbbi értékelés nem sikerült.",
        )
        if err:
            st.warning(err)
        return

    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and not any(
        str(data.get(k) or "").strip()
        for k in (
            "revised_divine_gracious_action",
            "revised_christ_connection",
            "revised_promised_resolution",
            "revised_grace_enabled_response",
        )
    ):
        return

    st.markdown("**MI-értékelés**")
    if overall:
        st.write(overall)

    strengths = data.get("strengths") or []
    if isinstance(strengths, list) and any(str(x).strip() for x in strengths):
        st.markdown("**Erősségek**")
        for item in strengths:
            line = str(item or "").strip()
            if line:
                st.markdown(f"- {line}")

    improvements = data.get("improvements") or []
    if isinstance(improvements, list) and any(str(x).strip() for x in improvements):
        st.markdown("**Javítási irányok**")
        for item in improvements:
            line = str(item or "").strip()
            if line:
                st.markdown(f"- {line}")

    type_assess = str(data.get("connection_type_assessment") or "").strip()
    if type_assess:
        st.markdown(f"**Kapcsolattípus értékelése**  \n{type_assess}")

    rd = str(data.get("revised_divine_gracious_action") or "").strip()
    rc = str(data.get("revised_christ_connection") or "").strip()
    rt = normalize_christ_connection_type(
        data.get("suggested_christ_connection_type") or ""
    )
    rr = str(data.get("revised_promised_resolution") or "").strip()
    rg = str(data.get("revised_grace_enabled_response") or "").strip()
    has_rev = bool(rd or rc or rr or rg or data.get("suggested_christ_connection_type"))
    if has_rev:
        st.markdown("**Átdolgozott javaslatok**")
        if rd:
            st.markdown(f"*Isten kegyelmi cselekvése:* {rd}")
            if st.button(
                "Átdolgozott kegyelmi cselekvés átvétele",
                key="sw_mi_ga_adopt_rev_divine",
            ):
                _request_adopt_ga_block({"divine_gracious_action": rd})
        if rc:
            st.markdown(f"*Krisztus-kapcsolat:* {rc}")
            if st.button(
                "Átdolgozott Krisztus-kapcsolat átvétele",
                key="sw_mi_ga_adopt_rev_christ",
            ):
                block = {"christ_connection": rc}
                if data.get("suggested_christ_connection_type"):
                    block["christ_connection_type"] = rt
                _request_adopt_ga_block(block)
        if data.get("suggested_christ_connection_type"):
            st.markdown(
                f"*Javasolt kapcsolattípus:* {christ_connection_type_label(rt)}"
            )
            if st.button(
                "Javasolt típus átvétele", key="sw_mi_ga_adopt_rev_type"
            ):
                _request_adopt_ga_block({"christ_connection_type": rt})
        if rr:
            st.markdown(f"*Evangéliumi feloldás:* {rr}")
            if st.button(
                "Átdolgozott feloldás átvétele", key="sw_mi_ga_adopt_rev_resolution"
            ):
                _request_adopt_ga_block({"promised_resolution": rr})
        if rg:
            st.markdown(f"*Kegyelemből fakadó válasz:* {rg}")
            if st.button(
                "Átdolgozott emberi válasz átvétele", key="sw_mi_ga_adopt_rev_grace"
            ):
                _request_adopt_ga_block({"grace_enabled_response": rg})
        if rd or rc or rr or rg:
            if st.button(
                "Átdolgozott ív átvétele", key="sw_mi_ga_adopt_rev_all"
            ):
                _request_adopt_ga_block(
                    {
                        "divine_gracious_action": rd,
                        "christ_connection": rc,
                        "christ_connection_type": rt
                        if data.get("suggested_christ_connection_type")
                        else "",
                        "promised_resolution": rr,
                        "grace_enabled_response": rg,
                    }
                )

    warnings = data.get("warnings") or []
    if isinstance(warnings, list):
        for item in warnings:
            line = str(item or "").strip()
            if line:
                st.warning(line)


def render_gospel_arc_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Krisztus-központú és evangéliumi ív — kézi szerkesztő + MI-segéd."""
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    tw = ensure_text_workshop_state(st.session_state)

    st.subheader("Második fordulópont: a mélyebb, evangéliumi felismerés")
    st.markdown(
        "Itt áll össze mélyebb összefüggésben mindaz, ami eddig történt: mit "
        "tesz Isten, hogyan kapcsolódik a textus Krisztushoz, és milyen "
        "kegyelemből fakadó válasz következhet. Isten cselekvése kerüljön az "
        "emberi teljesítmény elé — a cél nem az erőltetett krisztologizálás, "
        "hanem a textushű evangéliumi feloldási ív."
    )

    sw = ensure_sermon_workshop_state(st.session_state)
    text_status = (tw.get("text_main_idea_status") or "").strip()
    sermon_status = (sw.get("sermon_main_idea_status") or "").strip()
    if text_status != "approved" and sermon_status != "approved":
        st.info(
            "A szakasz használható, de a munka biztosabb, ha előbb jóváhagyod "
            "a textus vagy az igehirdetés fő gondolatát."
        )

    for field, title, help_text, placeholder, _category in _GA_TEXT_FIELDS:
        if field == "promised_resolution":
            # Kapcsolattípus a Krisztus-kapcsolat után, feloldás előtt
            st.markdown("**Kapcsolat típusa**")
            st.caption(_GA_TYPE_HELP)
            st.selectbox(
                "Kapcsolat típusa",
                options=list(CHRIST_CONNECTION_TYPES),
                format_func=lambda v: CHRIST_CONNECTION_TYPE_LABELS_HU.get(
                    v, str(v)
                ),
                key=_KEY_GA["christ_connection_type"],
                label_visibility="collapsed",
            )
            if (
                st.session_state.get(_KEY_GA["christ_connection_type"])
                == "none_or_uncertain"
            ):
                st.caption(
                    "A rendelkezésre álló anyag alapján a konkrét Krisztus-kapcsolat "
                    "még további vizsgálatot igényelhet."
                )
        st.markdown(f"**{title}**")
        st.caption(help_text)
        st.text_area(
            title,
            key=_KEY_GA[field],
            height=90,
            label_visibility="collapsed",
            placeholder=placeholder,
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_ga_save_draft"):
            filled = any(
                (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_GA.items()
                if field != "christ_connection_type"
            ) or bool(st.session_state.get(_KEY_GA["christ_connection_type"]))
            if not filled:
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                _persist_gospel_arc_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "christ_centered_arc_status", "draft"
                )
                _toast_and_rerun("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            type="primary",
            key="sw_ga_approve",
        ):
            block = {
                field: (st.session_state.get(wkey) or "").strip()
                for field, wkey in _KEY_GA.items()
            }
            block["christ_connection_type"] = normalize_christ_connection_type(
                block.get("christ_connection_type")
            )
            if not any(
                block.get(f)
                for f in (
                    "divine_gracious_action",
                    "christ_connection",
                    "promised_resolution",
                    "grace_enabled_response",
                )
            ):
                st.warning(
                    "Üres megfogalmazást nem lehet jóváhagyni. Tölts ki legalább egyet."
                )
            else:
                _persist_gospel_arc_from_widgets()
                update_sermon_workshop_section(
                    st.session_state, "christ_centered_arc_status", "approved"
                )
                text_items = [
                    (field, title, category)
                    for field, title, _help, _ph, category in _GA_TEXT_FIELDS
                ]
                # Add type as decision if meaningful
                added = 0
                skipped = 0
                for field, _title, category in text_items:
                    content = block.get(field) or ""
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_GOSPEL,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_GOSPEL,
                        category,
                        content,
                    )
                    added += 1
                type_label = christ_connection_type_label(
                    block.get("christ_connection_type")
                )
                type_content = f"Kapcsolat típusa: {type_label}"
                if block.get("christ_connection_type") and block.get(
                    "christ_connection_type"
                ) != "none_or_uncertain":
                    if not _decision_is_duplicate(
                        source_section=_SOURCE_GOSPEL,
                        category="Kapcsolat típusa",
                        content=type_content,
                    ):
                        add_approved_sermon_decision(
                            st.session_state,
                            _SOURCE_GOSPEL,
                            "Kapcsolat típusa",
                            type_content,
                        )
                        added += 1
                    else:
                        skipped += 1
                if added and skipped:
                    _toast_and_rerun(
                        f"Jóváhagyva. {added} új döntés került továbbvitelre; "
                        f"{skipped} már szerepelt."
                    )
                elif added:
                    _toast_and_rerun(
                        f"Jóváhagyva és továbbvíve ({added} homiletikai döntés)."
                    )
                else:
                    _toast_and_rerun(
                        "Jóváhagyva. A kitöltött elemek már szerepeltek a "
                        "homiletikai döntések között."
                    )

    saved_arc = (
        ensure_sermon_workshop_state(st.session_state).get("christ_centered_arc") or {}
    )
    saved_lt = (
        ensure_sermon_workshop_state(st.session_state).get("listener_tension") or {}
    )
    if isinstance(saved_arc, dict) and (
        any(
            str(saved_arc.get(k) or "").strip()
            for k in (
                "divine_gracious_action",
                "christ_connection",
                "grace_enabled_response",
            )
        )
        or (
            isinstance(saved_lt, dict)
            and str(saved_lt.get("promised_resolution") or "").strip()
        )
    ):
        st.caption("Elmentett állapot: **vázlat / jóváhagyott döntésekkel** (lásd lent)")

    st.markdown("---")
    st.markdown("**MI-segéd**")
    st.caption(
        "Az MI a jóváhagyott műhelyeredményekből segít megfogalmazni az "
        "evangéliumi ívet. Nem erőltet kapcsolatot, ahol az nem megalapozható. "
        "A végső döntés a prédikátoré."
    )
    ai_ready = generate_fn is not None
    ga_filled = any(
        (st.session_state.get(wkey) or "").strip()
        for field, wkey in _KEY_GA.items()
        if field != "christ_connection_type"
    )
    a1, a2 = st.columns(2)
    with a1:
        if st.button(
            "Javaslatok készítése",
            key="sw_mi_ga_suggest",
            disabled=not ai_ready,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_ga_suggest(generate_fn)
    with a2:
        if st.button(
            "Saját megfogalmazás értékelése",
            key="sw_mi_ga_assess",
            disabled=not ai_ready or not ga_filled,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                _run_ga_assess(generate_fn)

    _render_ga_suggestion_results()
    _render_ga_assessment_results()

    _render_decisions_for_section(_SOURCE_GOSPEL)


def _default_role_for_index(index: int) -> str:
    defaults = (
        "opening",
        "tension",
        "deepening",
        "gospel_resolution",
        "arrival",
    )
    if 0 <= index < len(defaults):
        return defaults[index]
    return "deepening"


def _render_movement_editor(mv: dict[str, str], *, index: int, total: int) -> None:
    mid = str(mv.get("id") or "")
    title_preview = (
        st.session_state.get(_mv_widget_key(mid, "title")) or mv.get("title") or ""
    ).strip() or f"Mozgás {index + 1}"
    role_preview = normalize_movement_role(
        st.session_state.get(_mv_widget_key(mid, "role")) or mv.get("role") or ""
    )
    header = f"{index + 1}. {title_preview} — {movement_role_label(role_preview)}"
    with st.expander(header, expanded=False):
        st.text_input(
            "Cím (munkacím)",
            key=_mv_widget_key(mid, "title"),
            placeholder="Rövid munkacím…",
        )
        st.selectbox(
            "Funkció",
            options=list(MOVEMENT_ROLES),
            format_func=lambda v: MOVEMENT_ROLE_LABELS_HU.get(v, str(v)),
            key=_mv_widget_key(mid, "role"),
        )
        st.text_area(
            "Központi tartalom",
            key=_mv_widget_key(mid, "core_content"),
            height=90,
            placeholder="Egyetlen világos bekezdés…",
            help=(
                "Mit bont ki ez a mozgás? Egyetlen világos bekezdésben fogalmazd meg, "
                "ne írd meg a teljes prédikációrészt."
            ),
        )
        st.text_area(
            "Textusbeli alap",
            key=_mv_widget_key(mid, "textual_basis"),
            height=70,
            placeholder="Vers, kifejezés, kép vagy összefüggés…",
            help=(
                "Melyik versre, kifejezésre, képre vagy szövegbeli összefüggésre épül "
                "ez a mozgás?"
            ),
        )
        st.text_area(
            "Hallgatói felismerés",
            key=_mv_widget_key(mid, "listener_discovery"),
            height=70,
            placeholder="Mit láthat meg másként a hallgató…",
            help="Mit láthat meg másként a hallgató ennek a mozgásnak a végére?",
        )
        st.text_area(
            "Átmenet a következőhöz",
            key=_mv_widget_key(mid, "transition_to_next"),
            height=70,
            placeholder="Mi teszi szükségessé a következő mozgást…",
            help=(
                "Mi teszi szükségessé a következő mozgást? Ne csak azt írd: "
                "„Térjünk át a következő pontra.”"
            ),
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button(
                "Feljebb",
                key=f"sw_mv_up_{mid}",
                disabled=index <= 0,
            ):
                _persist_sermon_movements_from_widgets()
                sw = ensure_sermon_workshop_state(st.session_state)
                mvs = normalize_sermon_movements(sw.get("sermon_movements"))
                if index > 0 and index < len(mvs):
                    mvs[index - 1], mvs[index] = mvs[index], mvs[index - 1]
                    update_sermon_workshop_section(
                        st.session_state, "sermon_movements", mvs
                    )
                    st.session_state[_RESYNC_FLAG] = True
                    st.rerun()
        with c2:
            if st.button(
                "Lejjebb",
                key=f"sw_mv_down_{mid}",
                disabled=index >= total - 1,
            ):
                _persist_sermon_movements_from_widgets()
                sw = ensure_sermon_workshop_state(st.session_state)
                mvs = normalize_sermon_movements(sw.get("sermon_movements"))
                if index < len(mvs) - 1:
                    mvs[index + 1], mvs[index] = mvs[index], mvs[index + 1]
                    update_sermon_workshop_section(
                        st.session_state, "sermon_movements", mvs
                    )
                    st.session_state[_RESYNC_FLAG] = True
                    st.rerun()
        with c3:
            pending = st.session_state.get(_MV_DELETE_PENDING)
            if pending == mid:
                if st.button("Igen, törlés", key=f"sw_mv_del_yes_{mid}", type="primary"):
                    _persist_sermon_movements_from_widgets()
                    sw = ensure_sermon_workshop_state(st.session_state)
                    mvs = [
                        m
                        for m in normalize_sermon_movements(sw.get("sermon_movements"))
                        if str(m.get("id") or "") != mid
                    ]
                    update_sermon_workshop_section(
                        st.session_state, "sermon_movements", mvs
                    )
                    st.session_state.pop(_MV_DELETE_PENDING, None)
                    _clear_movement_widgets()
                    st.session_state[_RESYNC_FLAG] = True
                    st.rerun()
                if st.button("Mégse", key=f"sw_mv_del_no_{mid}"):
                    st.session_state.pop(_MV_DELETE_PENDING, None)
                    st.rerun()
            else:
                if st.button("Törlés", key=f"sw_mv_del_{mid}"):
                    st.session_state[_MV_DELETE_PENDING] = mid
                    st.rerun()


def _path_suggestion_payload(result: SermonPathSuggestionResult) -> dict[str, Any]:
    return result.to_dict()


def _path_assessment_payload(result: SermonPathAssessmentResult) -> dict[str, Any]:
    return result.to_dict()


def _run_sermon_path_suggest(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Igehirdetési út javaslata készül…"):
        kwargs = _collect_sermon_path_kwargs()
        result = suggest_sermon_path(**kwargs, generate_fn=generate_fn)
        save_sermon_path_suggestions(
            st.session_state, _path_suggestion_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="A javaslatkészítés nem sikerült.",
                )
            )
        elif result.missing_information and not (
            result.path_rationale or result.movements
        ):
            st.warning(
                "Nincs elegendő adat a felelős javaslathoz. Hiányzik: "
                + "; ".join(result.missing_information)
            )
        else:
            st.success("Javaslat elkészült.")


def _run_sermon_path_assess(*, generate_fn: GenerateFn | None) -> None:
    with st.spinner("Saját út és mozgások értékelése…"):
        kwargs = _collect_sermon_path_kwargs()
        result = assess_sermon_path(**kwargs, generate_fn=generate_fn)
        save_sermon_path_assessment(
            st.session_state, _path_assessment_payload(result)
        )
        if not result.ok:
            st.error(
                _user_facing_error(
                    result.ok,
                    result.error_message,
                    fallback="Az értékelés nem sikerült.",
                )
            )
        else:
            st.success("Értékelés elkészült.")


def _render_sermon_path_suggestions() -> None:
    """MI-javaslat kizárólag a három aktív mezőre (kiinduló látás / első
    látásváltás / mélyítés) — a `suggest_sermon_path` válaszban lévő
    úttípus/indoklás/megérkezés/mozgás-lista mezőket nem jelenítjük meg
    választható rendszerként; a mozgások közül csak a "tension" és
    "deepening" szerepű elem tartalma kerül át javaslatként az első
    látásváltás, illetve a mélyítés mezőbe.
    """
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("sermon_path_suggestions")
    if not isinstance(data, dict):
        return

    starting = str(data.get("starting_point") or "").strip()
    movements = normalize_sermon_movements(data.get("movements"))
    first_shift = next(
        (
            str(mv.get("core_content") or "").strip()
            for mv in movements
            if mv.get("role") == "tension" and (mv.get("core_content") or "").strip()
        ),
        "",
    )
    deepening = next(
        (
            str(mv.get("core_content") or "").strip()
            for mv in movements
            if mv.get("role") == "deepening" and (mv.get("core_content") or "").strip()
        ),
        "",
    )
    expanded = str(data.get("expanded_summary") or "").strip()
    basis = data.get("basis") if isinstance(data.get("basis"), list) else []
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    missing = (
        data.get("missing_information")
        if isinstance(data.get("missing_information"), list)
        else []
    )
    reasoning = str(data.get("reasoning_summary") or "").strip()

    if not (starting or first_shift or deepening):
        if data.get("ok") is False:
            err = str(data.get("error_message") or "").strip()
            if err:
                st.error(err)
        if missing:
            st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))
        return

    st.markdown("**MI-javaslat**")
    if starting:
        st.markdown(f"**Alaphelyzet**  \n{starting}")
        if st.button("Átveszem az alaphelyzetet", key="sw_mi_path_adopt_start"):
            _request_adopt_path_block({"starting_point": starting})
    if first_shift:
        st.markdown(f"**Első fordulópont**  \n{first_shift}")
        if st.button(
            "Átveszem az első fordulópontot", key="sw_mi_path_adopt_first_shift"
        ):
            _request_adopt_path_block({"first_shift": first_shift})
    if deepening:
        st.markdown(f"**Mélyítés és fokozás**  \n{deepening}")
        if st.button(
            "Átveszem a mélyítést", key="sw_mi_path_adopt_deepening"
        ):
            _request_adopt_path_block({"deepening": deepening})
    if expanded:
        st.markdown("**Az egész út rövid összefoglalása**")
        st.write(expanded)

    if (starting and first_shift) or (starting and deepening) or (first_shift and deepening):
        if st.button("Mindhármat átveszem", key="sw_mi_path_adopt_all"):
            block = {}
            if starting:
                block["starting_point"] = starting
            if first_shift:
                block["first_shift"] = first_shift
            if deepening:
                block["deepening"] = deepening
            _request_adopt_path_block(block)

    with st.expander("Mi alapján készült?", expanded=False):
        if reasoning:
            st.write(reasoning)
        if basis:
            for item in basis:
                if item:
                    st.markdown(f"- {item}")

    if warnings:
        for w in warnings:
            if w:
                st.warning(str(w))
    if missing:
        st.info("Hiányzó információ: " + "; ".join(str(x) for x in missing if x))


def _render_sermon_path_assessment() -> None:
    sw = ensure_sermon_workshop_state(st.session_state)
    data = sw.get("sermon_path_assessment")
    if not isinstance(data, dict):
        return
    overall = str(data.get("overall_assessment") or "").strip()
    if not overall and data.get("ok") is False:
        err = str(data.get("error_message") or "").strip()
        if err:
            st.error(err)
        return
    if not overall and not data.get("revised_movements"):
        return

    st.markdown("**MI-értékelés**")
    if overall:
        st.write(overall)
    for key, label in (
        ("path_type_assessment", "Úttípus"),
        ("structure_assessment", "Szerkezet"),
        ("gospel_turn_assessment", "Evangéliumi fordulat"),
        ("transition_assessment", "Átmenetek"),
    ):
        val = str(data.get(key) or "").strip()
        if val:
            st.markdown(f"**{label}:** {val}")
    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    improvements = (
        data.get("improvements") if isinstance(data.get("improvements"), list) else []
    )
    if strengths:
        st.markdown("**Erősségek**")
        for s in strengths:
            if s:
                st.markdown(f"- {s}")
    if improvements:
        st.markdown("**Javítási javaslatok**")
        for s in improvements:
            if s:
                st.markdown(f"- {s}")

    revised_reason = str(data.get("revised_path_rationale") or "").strip()
    revised_start = str(data.get("revised_starting_point") or "").strip()
    revised_dest = str(data.get("revised_destination") or "").strip()
    revised_mvs = normalize_sermon_movements(data.get("revised_movements"))
    if revised_reason or revised_start or revised_dest or revised_mvs:
        st.markdown("**Javított javaslatok**")
        if revised_reason:
            st.markdown(f"*Indoklás:* {revised_reason}")
        if revised_start:
            st.markdown(f"*Kiindulópont:* {revised_start}")
        if revised_dest:
            st.markdown(f"*Megérkezés:* {revised_dest}")
        if revised_mvs:
            for idx, mv in enumerate(revised_mvs, start=1):
                with st.expander(
                    f"Javított mozgás {idx}: {mv.get('title') or '—'}",
                    expanded=False,
                ):
                    st.write(mv.get("core_content") or "")
                    if st.button(
                        f"Átveszem a javított mozgást ({idx})",
                        key=f"sw_mi_path_adopt_rev_mv_{idx}",
                    ):
                        current = _read_movements_from_widgets()
                        if len(current) >= MAX_MOVEMENTS:
                            st.warning(f"Legfeljebb {MAX_MOVEMENTS} mozgás lehet.")
                        else:
                            new_mv = empty_sermon_movement(
                                role=normalize_movement_role(mv.get("role"))
                            )
                            for field in _MV_FIELDS:
                                if field != "role":
                                    new_mv[field] = str(mv.get(field) or "")
                            new_mv["role"] = (
                                normalize_movement_role(mv.get("role")) or "deepening"
                            )
                            current.append(new_mv)
                            _request_adopt_movements(current)
        if st.button("Átveszem a javított egész tervet", key="sw_mi_path_adopt_rev_all"):
            path_block: dict[str, str] = {}
            if revised_reason:
                path_block["reason"] = revised_reason
            if revised_start:
                path_block["starting_point"] = revised_start
            if revised_dest:
                path_block["destination"] = revised_dest
            _request_adopt_path_plan(
                path_block=path_block or None,
                movements=revised_mvs or None,
            )

    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    for w in warnings:
        if w:
            st.warning(str(w))


def render_sermon_path_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Alaphelyzet → Első fordulópont → Mélyítés és fokozás → (opcionális
    Átértelmezés).

    Az egységesített, fordulópont-alapú modell 7 eleme közül ez a szakasz
    az „Alaphelyzet”, „Első fordulópont”, „Mélyítés és fokozás” és az
    opcionális „Átértelmezés” elemeket adja (a „Belépés” a Homiletikai
    belépési pont szakaszon, a „Második fordulópont”/„Megérkezés” lejjebb,
    a Krisztus-központú ív / Lezárás szakaszon jelenik meg). A korábbi
    úttípus-választó, indoklás és a külön Prédikációs mozgások szerkesztő
    (és az arról átöltő gombok) itt nem jelenik meg — nem választható
    út-alternatíva, ez maga a szerkesztési rendszer. A mögöttes
    `sermon_path`/`sermon_movements` legacy adatok nem vesznek el (ld.
    `_persist_sermon_path_from_widgets`), csak a felület nem mutatja őket
    párhuzamos rendszerként.
    """
    _apply_sw_ui_resync_if_needed()
    _apply_pending_adopts_if_needed()
    ensure_sermon_workshop_state(st.session_state)

    st.subheader("Az igehirdetés útja")

    sw = ensure_sermon_workshop_state(st.session_state)
    if (sw.get("sermon_main_idea_status") or "").strip() != "approved":
        st.info(
            "A szakasz használható, de a munka biztosabb, ha előbb jóváhagyod "
            "az igehirdetés fő gondolatát."
        )

    st.markdown("##### 1. Alaphelyzet")
    st.text_area(
        "Alaphelyzet",
        key=_KEY_PATH["starting_point"],
        height=80,
        label_visibility="collapsed",
        placeholder="Konfliktus, hiány, kérdés, paradoxon vagy teológiai probléma…",
    )

    st.markdown("##### 2. Első fordulópont")
    st.text_area(
        "Első fordulópont",
        key=_KEY_PATH["first_shift"],
        height=90,
        label_visibility="collapsed",
        placeholder="Váratlan isteni cselekvés, kulcsmondat, döntés vagy teológiai hangsúly… (opcionális)",
    )

    st.markdown("##### 3. Mélyítés és fokozás")
    st.text_area(
        "Mélyítés és fokozás",
        key=_KEY_PATH["deepening"],
        height=90,
        label_visibility="collapsed",
        placeholder="Mitől lesz összetettebb, súlyosabb a kérdés? (opcionális)",
    )

    with st.expander("4. Átértelmezés (opcionális)", expanded=False):
        st.text_area(
            "Átértelmezés",
            key=_KEY_PATH["reinterpretation"],
            height=90,
            label_visibility="collapsed",
            placeholder="Váratlan fordulat vagy korrekció a textusban… (opcionális, gyakran üres)",
        )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Mentés vázlatként", key="sw_path_save_draft"):
            _persist_sermon_path_from_widgets()
            filled = any(
                (st.session_state.get(_KEY_PATH[f]) or "").strip()
                for f in ("starting_point", "first_shift", "deepening", "reinterpretation")
            )
            if not filled:
                st.warning("Üres mezőket nem lehet menteni. Tölts ki legalább egyet.")
            else:
                update_sermon_workshop_section(
                    st.session_state, "sermon_path_status", "draft"
                )
                _toast_and_rerun("Vázlatként elmentve.")
    with b2:
        if st.button(
            "Jóváhagyom és átadom",
            type="primary",
            key="sw_path_approve",
        ):
            _persist_sermon_path_from_widgets()
            path = {
                "starting_point": (
                    st.session_state.get(_KEY_PATH["starting_point"]) or ""
                ).strip(),
                "first_shift": (
                    st.session_state.get(_KEY_PATH["first_shift"]) or ""
                ).strip(),
                "deepening": (
                    st.session_state.get(_KEY_PATH["deepening"]) or ""
                ).strip(),
                "reinterpretation": (
                    st.session_state.get(_KEY_PATH["reinterpretation"]) or ""
                ).strip(),
            }
            if not any(path.values()):
                st.warning(
                    "Üres megfogalmazást nem lehet jóváhagyni. Tölts ki legalább egyet."
                )
            else:
                update_sermon_workshop_section(
                    st.session_state, "sermon_path_status", "approved"
                )
                decisions = [
                    ("starting_point", "Alaphelyzet", path["starting_point"]),
                    ("first_shift", "Első fordulópont", path["first_shift"]),
                    (
                        "deepening",
                        "Mélyítés és fokozás",
                        path["deepening"],
                    ),
                    (
                        "reinterpretation",
                        "Átértelmezés",
                        path["reinterpretation"],
                    ),
                ]
                added = 0
                skipped = 0
                for _field, category, content in decisions:
                    if not content:
                        continue
                    if _decision_is_duplicate(
                        source_section=_SOURCE_PATH,
                        category=category,
                        content=content,
                    ):
                        skipped += 1
                        continue
                    add_approved_sermon_decision(
                        st.session_state,
                        _SOURCE_PATH,
                        category,
                        content,
                    )
                    added += 1
                if added:
                    _toast_and_rerun(f"Jóváhagyva ({added} döntés).")
                elif skipped:
                    _toast_and_rerun("Jóváhagyva. Ezek a döntések már szerepelnek.")
                else:
                    _toast_and_rerun("Jóváhagyva.")

    _render_decisions_for_section(_SOURCE_PATH)

    st.markdown("---")
    st.markdown("**MI-segéd**")
    if st.button("Javaslatot kérek", key="sw_path_mi_suggest"):
        _run_sermon_path_suggest(generate_fn=generate_fn)

    _render_sermon_path_suggestions()


def _render_section_placeholder(section: str) -> None:
    meta = _SW_SECTION_PLACEHOLDERS.get(section) or {
        "goal": "Ez a szakasz a későbbi mérföldkövekben válik működővé.",
        "later": "Itt később homiletikai döntést hozol.",
    }
    st.subheader(section)
    st.markdown(f"**Cél:** {meta['goal']}")
    st.markdown(meta["later"])
    st.caption("Következő fejlesztési mérföldkőben válik működővé.")


def flush_sermon_workshop_from_widgets() -> None:
    """Élő Streamlit widgetek → tartós `sermon_workshop` (ha a widget létezik).

    A fejléc Mentés / autosave előtt hívandó, hogy a még nem „Mentés
    vázlatként” gombbal elmentett mezők se vesszenek el — ugyanaz a minta,
    mint a Bibliai szöveg `save_bible_text_from_widgets` hívása.
    Nem változtatja a jóváhagyási státuszokat (draft/approved).
    Projektváltás után, ha a UI-resync még nem futott, előbb a tartós
    adatból frissíti a widgeteket, hogy régi session-érték ne írjon felül
    (ugyanaz a minta, mint a Textusműhely flush).
    """
    ensure_sermon_workshop_state(st.session_state)
    _apply_sw_ui_resync_if_needed()

    if _KEY_SERMON_IDEA in st.session_state:
        update_sermon_workshop_section(
            st.session_state,
            "sermon_main_idea",
            (st.session_state.get(_KEY_SERMON_IDEA) or "").strip(),
        )

    if all(wkey in st.session_state for wkey in _KEY_HC.values()):
        block = {
            field: (st.session_state.get(wkey) or "").strip()
            for field, wkey in _KEY_HC.items()
        }
        update_sermon_workshop_section(st.session_state, "human_condition", block)

    if all(wkey in st.session_state for wkey in _KEY_LT.values()):
        sw = ensure_sermon_workshop_state(st.session_state)
        current = (
            sw.get("listener_tension")
            if isinstance(sw.get("listener_tension"), dict)
            else {}
        )
        block = {
            field: (st.session_state.get(wkey) or "").strip()
            for field, wkey in _KEY_LT.items()
        }
        # promised_resolution a GA widgetből jöhet, ha létezik
        if _KEY_GA["promised_resolution"] in st.session_state:
            block["promised_resolution"] = (
                st.session_state.get(_KEY_GA["promised_resolution"]) or ""
            ).strip()
        else:
            block["promised_resolution"] = str(
                current.get("promised_resolution") or ""
            )
        update_sermon_workshop_section(st.session_state, "listener_tension", block)

    if all(
        wkey in st.session_state
        for field, wkey in _KEY_GA.items()
        if field != "promised_resolution"
    ):
        _persist_gospel_arc_from_widgets()

    if all(
        _KEY_PATH[field] in st.session_state
        for field in ("starting_point", "first_shift", "deepening")
    ):
        _persist_sermon_path_from_widgets()

    if all(wkey in st.session_state for wkey in _KEY_ENTRY.values()):
        _persist_entry_point_from_widgets()

    if any(
        isinstance(k, str) and k.startswith(_MV_WIDGET_PREFIX)
        for k in st.session_state.keys()
    ):
        _persist_sermon_movements_from_widgets()

    if any(
        isinstance(k, str)
        and (
            k.startswith(_IMG_WIDGET_PREFIX)
            or k.startswith(_ILL_WIDGET_PREFIX)
            or k.startswith(_APP_WIDGET_PREFIX)
        )
        for k in st.session_state.keys()
    ):
        _persist_enrichment_from_widgets()

    if all(wkey in st.session_state for wkey in _KEY_CL.values()):
        _persist_closing_from_widgets()

    if all(wkey in st.session_state for wkey in _KEY_DIAG.values()):
        _persist_self_review_from_widgets()

    if (
        _KEY_LECTION["reference"] in st.session_state
        or _KEY_LECTION["user_focus"] in st.session_state
    ):
        _persist_lection_from_widgets(include_text=True)

    if _KEY_PRAYER_COMMON["tone_preference"] in st.session_state:
        _persist_prayer_from_widgets()

    if (
        _KEY_OUTLINE["main_idea"] in st.session_state
        or _KEY_OUTLINE["opening_direction"] in st.session_state
        or _KEY_OUTLINE["manual_notes"] in st.session_state
        or _KEY_OUTLINE["content"] in st.session_state
        or any(
            isinstance(k, str) and k.startswith(_OUTLINE_MV_PREFIX)
            for k in st.session_state.keys()
        )
    ):
        # Csak valódi tartalomváltozáskor jelöljük kézi szerkesztésnek.
        _persist_outline_from_widgets(mark_manual_edit=None)


def _flat_save_text_main_idea() -> None:
    """A textus fő gondolata — automatikus mentés a kanonikus
    `text_workshop.text_main_idea` mezőbe. Nem igényel approval-státuszt
    és nem szivárog az `arc` egyetlen pontjába sem."""
    content = (st.session_state.get(_KEY_FLAT_TEXT_MAIN_IDEA) or "").strip()
    update_text_main_idea(st.session_state, content, "draft")


def _flat_save_sermon_main_idea() -> None:
    """Az igehirdetés fő gondolata / fókuszmondat — automatikus mentés a
    kanonikus `sermon_workshop.sermon_main_idea` mezőbe. A státuszt nem
    módosítja (a meglévő legacy státusz csak tájékoztató marad)."""
    content = (st.session_state.get(_KEY_SERMON_IDEA) or "").strip()
    update_sermon_workshop_section(st.session_state, "sermon_main_idea", content)


def _trigger_field_refinement_request(
    field_key: str,
    *,
    current_text: str,
    instruction: str,
    generate_fn: GenerateFn | None,
    running_key: str,
) -> None:
    """RESET 2D-B2: EGYETLEN megosztott végrehajtási út — mind a kártya
    alatti gyors („MI-javaslat ehhez a ponthoz”), mind a személyre szabott
    expander-gomb („Egyedi MI-javaslat kérése”) ugyanezt hívja, ugyanazzal
    a running-state védelemmel és a fogyó auto-open jelzővel. A gyors gomb
    üres `instruction`-nel hívja, a személyre szabott a felhasználó által
    beírt szöveggel — a mögöttes, biztonságos candidate-folyamat mindkét
    esetben azonos (`generate_field_refinement`)."""
    if generate_fn is None:
        st.warning("Az MI-segéd jelenleg nem elérhető.")
        return
    st.session_state[running_key] = True
    try:
        with st.spinner("Javaslat készül…"):
            outcome = generate_field_refinement(
                st.session_state,
                field_key=field_key,
                current_text=current_text,
                instruction=instruction,
                generate_fn=generate_fn,
            )
    finally:
        st.session_state[running_key] = False

    if not outcome.ok:
        st.error(outcome.error_message)
    else:
        st.session_state[_KEY_REFINE_AUTO_OPEN_FIELD] = field_key
        _toast_and_rerun("Elkészült egy javaslat — nézd át alul.")


def _render_field_refinement_panel(
    field_key: str,
    *,
    current_text: str,
    on_accept: Callable[[str], None],
    generate_fn: GenerateFn | None,
    expander_title: str,
) -> None:
    """RESET 2D-B1/2D-B2: célzott, elfogadásos MI-pontosítás EGY célmezőhöz
    — kilenc egymástól TELJESEN FÜGGETLEN példány (két főgondolat + hét
    arc-pont), mindegyik saját, `field_key`-vel képzett widgetkulcsokkal.
    Alapból összecsukott, KIVÉVE közvetlenül egy saját sikeres
    javaslatkérés utáni egyetlen rendereléskor (ld. `_KEY_REFINE_AUTO_
    OPEN_FIELD`). A javaslat SOSEM íródik automatikusan a kanonikus
    mezőbe — kizárólag az „Átvétel” gomb explicit hatására, és csak
    akkor, ha a generálás óta a teljes felhasznált kontextus (igehely,
    bibliai szöveg, fordítás, a mező saját aktuális tartalma) nem
    változott. `on_accept` a hívó által átadott, MEGLÉVŐ kanonikus
    mentési útvonal (pl. `update_arc_point`, `update_text_main_idea`).

    `expander_title` a hívó által megadott felirat (RESET 2D-B2): az
    arc-pontoknál „Pontosítási kérés (opcionális)” — mivel ott a
    kártya alatti önálló gomb már fedi az egyszerű „adj javaslatot”
    esetet —, a két főgondolatnál „MI-javaslat vagy pontosítás”, mivel
    azoknál nincs külön gyors gomb, az expander az egyetlen belépési
    pont mindkét esethez."""
    auto_open = st.session_state.get(_KEY_REFINE_AUTO_OPEN_FIELD) == field_key
    if auto_open:
        # Fogyó jelző: pontosan egyszer nyit, utána azonnal törlődik.
        st.session_state.pop(_KEY_REFINE_AUTO_OPEN_FIELD, None)

    with st.expander(expander_title, expanded=auto_open):
        instruction_key = f"sw_refine_instr_{field_key}"
        running_key = f"_sw_refine_running_{field_key}"
        running = bool(st.session_state.get(running_key))

        st.text_area(
            "Mit szeretnél pontosítani?",
            key=instruction_key,
            height=68,
            placeholder=(
                "Például: legyen konkrétabb, rövidebb, vagy kapcsolódjon "
                "jobban a textus feszültségéhez."
            ),
        )

        if st.button(
            "Egyedi MI-javaslat kérése",
            key=f"sw_refine_request_{field_key}",
            disabled=running or generate_fn is None,
        ):
            instruction = str(st.session_state.get(instruction_key) or "")
            _trigger_field_refinement_request(
                field_key,
                current_text=current_text,
                instruction=instruction,
                generate_fn=generate_fn,
                running_key=running_key,
            )
        if generate_fn is None:
            st.caption("Az MI-segéd jelenleg nem elérhető.")

        sw = ensure_sermon_workshop_state(st.session_state)
        refinements = sw.get("field_refinements")
        suggestion = (
            refinements.get(field_key) if isinstance(refinements, dict) else None
        )
        if not isinstance(suggestion, dict) or not suggestion.get("text"):
            return

        st.divider()
        st.caption("Javaslat:")
        st.markdown(suggestion["text"])

        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Javaslat átvétele",
                type="primary",
                key=f"sw_refine_accept_{field_key}",
            ):
                context = build_refinement_context(
                    st.session_state,
                    field_key=field_key,
                    current_text=current_text,
                )
                result = validate_field_refinement_acceptance(
                    st.session_state,
                    field_key,
                    reference=context.reference,
                    context_hash=context.context_hash,
                )
                if result["valid"]:
                    on_accept(result["text"])
                    discard_field_refinement_suggestion(st.session_state, field_key)
                    st.session_state[_RESYNC_FLAG] = True
                    _toast_and_rerun("A javaslat bekerült a szerkesztőbe.")
                else:
                    reason = str(result.get("reason") or "")
                    st.warning(
                        _FIELD_REFINEMENT_REJECT_MESSAGES.get(
                            reason, "A javaslat nem fogadható el."
                        )
                    )
        with c2:
            if st.button("Javaslat elvetése", key=f"sw_refine_discard_{field_key}"):
                discard_field_refinement_suggestion(st.session_state, field_key)
                _toast_and_rerun("A javaslat elvetve.")


def render_flat_text_and_focus_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """RESET 2B/2D-B1/2D-B2: „Textus és fókusz” — a hét pontot összetartó
    két központi irány. Mindkét mező önállóan, approval és automatikus
    felülírás nélkül, kézzel szerkeszthető és automatikusan mentődik.
    Mindkettő alatt egy összecsukott „MI-javaslat vagy pontosítás”
    szakasz ad célzott, elfogadásos MI-segítséget — a felirat (RESET
    2D-B2) szándékosan jelzi, hogy ÜRES mezőhöz is kérhető javaslat, nem
    csak meglévő tartalom pontosítható (nincs itt külön gyors gomb, az
    expander az egyetlen belépési pont mindkét esethez)."""
    render_work_section(
        title="Textus és fókusz",
        context="Igehirdetési műhely",
    )

    tw = ensure_text_workshop_state(st.session_state)
    sw = ensure_sermon_workshop_state(st.session_state)

    st.markdown("**A textus fő gondolata**")
    st.text_area(
        "A textus fő gondolata",
        key=_KEY_FLAT_TEXT_MAIN_IDEA,
        height=72,
        label_visibility="collapsed",
        placeholder="Mit mond a szakasz a saját összefüggésében?",
        on_change=_flat_save_text_main_idea,
    )
    _render_field_refinement_panel(
        "text_main_idea",
        current_text=str(tw.get("text_main_idea") or ""),
        on_accept=lambda text: update_text_main_idea(st.session_state, text, "draft"),
        generate_fn=generate_fn,
        expander_title="MI-javaslat vagy pontosítás",
    )

    st.markdown("**Az igehirdetés fő gondolata – fókuszmondat**")
    st.text_area(
        "Az igehirdetés fő gondolata – fókuszmondat",
        key=_KEY_SERMON_IDEA,
        height=72,
        label_visibility="collapsed",
        placeholder="Milyen felismerés felé vezesse a hallgatót?",
        on_change=_flat_save_sermon_main_idea,
    )
    _render_field_refinement_panel(
        "sermon_main_idea",
        current_text=str(sw.get("sermon_main_idea") or ""),
        on_accept=lambda text: update_sermon_workshop_section(
            st.session_state, "sermon_main_idea", text
        ),
        generate_fn=generate_fn,
        expander_title="MI-javaslat vagy pontosítás",
    )


def _flat_save_arc_point(point_key: str) -> None:
    """Egy hétpontos kártya automatikus mentése — közvetlenül a meglévő
    `update_arc_point()` adatmodell-függvényt hívja (ez frissíti az
    `arc_meta.manually_updated_at`-ot is), csak a célpontot módosítja.

    Szűk korrekció (2026-08-19): a jelenlegi TELJES generálási-kontextus
    hash-t (`sermon_workshop_arc_ai.compute_arc_generation_context_hash`)
    adja át `update_arc_point()`-nak, hogy az `arc_meta.context_hash` egy
    kézi szerkesztés után is az aktuális, teljes hétpontos-generálási
    kontextust tükrözze — ne csak a szűk igehely-hash-t. Nem indít
    AI-hívást, csak string-feldolgozás és hash-számítás."""
    widget_key = _KEY_FLAT_ARC[point_key]
    content = st.session_state.get(widget_key) or ""
    context = build_arc_generation_context(st.session_state)
    update_arc_point(
        st.session_state, point_key, content, context_hash=context.context_hash
    )


def render_flat_seven_point_outline_section(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """RESET 2B/2C/2D-B2/2D-F2: „Hétpontos igehirdetési vázlat” — hét,
    számozott, egyenként szerkeszthető kártya, közvetlenül az `arc.*`
    pontokat módosítva, plusz az EGYETLEN MI-generáló gomb (RESET 2C),
    amely továbbra is az egyetlen teljes-hétpontos candidate/applied
    útvonal (`generate_seven_point_arc`) — nincs második, párhuzamos
    teljes-vázlat-generáló. A gomb (RESET 2D-F2) saját, bekeretezett
    blokkot kap, és a függőben lévő candidate-panel közvetlenül e blokk
    ALATT jelenik meg — MÉG a hét kártya ELŐTT (ld. `_render_arc_
    candidate_panel` hívását lentebb) —, hogy a javaslat ugyanott
    látszódjon, ahol a felhasználó kérte, ne a kártyák után, elszakítva
    a kattintástól. Emellett (RESET 2D-B2) mind a hét kártyán van egy
    önálló, jól látható „MI-javaslat ehhez a ponthoz” gomb, közvetlenül a
    szövegmező alatt, az expander előtt — ez a meglévő field-refinement
    candidate-mechanizmust hívja üres instrukcióval, így üres mezőnél is,
    kitöltött mezőnél is működik, automatikus felülírás nélkül. Nincs
    approval vagy „Átveszem” a kártyákon magukon (a javaslatok kizárólag
    a saját candidate-panelen fogadhatók el), nincs régi outline-generálás
    vagy export ezen az útvonalon."""
    render_work_section(
        title="Hétpontos igehirdetési vázlat",
        context="Igehirdetési műhely",
    )

    running = bool(st.session_state.get(_KEY_ARC_GEN_RUNNING))
    with st.container(border=True):
        if st.button(
            "MI-javaslat mind a hét ponthoz",
            type="primary",
            key="sw_flat_arc_generate",
            disabled=running or generate_fn is None,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                st.session_state[_KEY_ARC_GEN_RUNNING] = True
                try:
                    with st.spinner("Hétpontos vázlatjavaslat készül…"):
                        outcome = generate_seven_point_arc(
                            st.session_state, generate_fn=generate_fn
                        )
                finally:
                    st.session_state[_KEY_ARC_GEN_RUNNING] = False

                if not outcome.ok:
                    st.error(outcome.error_message)
                elif outcome.status == "applied":
                    st.session_state[_RESYNC_FLAG] = True
                    _toast_and_rerun(
                        "A hétpontos vázlatjavaslat bekerült a szerkesztőbe."
                    )
                else:  # "candidate" — a kanonikus arc változatlan, lásd lentebb
                    _toast_and_rerun(
                        "Elkészült egy új vázlatjavaslat — nézd át alább."
                    )
        if generate_fn is None:
            st.caption("Az MI-segéd jelenleg nem elérhető.")

    # RESET 2D-F2: a candidate-panel közvetlenül a gombblokk alatt, MÉG a
    # hét kártya ELŐTT jelenik meg — üres/hiányzó candidate esetén a
    # függvény nem renderel semmit.
    _render_arc_candidate_panel()

    sw = ensure_sermon_workshop_state(st.session_state)
    arc = sw.get("arc") if isinstance(sw.get("arc"), dict) else {}
    for idx, point_key in enumerate(_ARC_POINT_KEYS, start=1):
        title = _ARC_CARD_TITLES[point_key]
        widget_key = _KEY_FLAT_ARC[point_key]
        with st.container(border=True):
            head_l, head_r = st.columns([1.7, 1], gap="small")
            with head_l:
                st.markdown(f"**{idx}. {title}**")
            with head_r:
                point_running_key = f"_sw_refine_running_{point_key}"
                if st.button(
                    "MI-javaslat ehhez a ponthoz",
                    key=f"sw_refine_quick_{point_key}",
                    disabled=bool(st.session_state.get(point_running_key))
                    or generate_fn is None,
                ):
                    _trigger_field_refinement_request(
                        point_key,
                        current_text=str((arc.get(point_key) or {}).get("text") or ""),
                        instruction="",
                        generate_fn=generate_fn,
                        running_key=point_running_key,
                    )
            st.text_area(
                title,
                key=widget_key,
                height=64,
                label_visibility="collapsed",
                placeholder=_ARC_CARD_DESCRIPTIONS.get(point_key, ""),
                on_change=_flat_save_arc_point,
                args=(point_key,),
            )
            _render_field_refinement_panel(
                point_key,
                current_text=str((arc.get(point_key) or {}).get("text") or ""),
                on_accept=lambda text, pk=point_key: update_arc_point(
                    st.session_state,
                    pk,
                    text,
                    context_hash=build_arc_generation_context(
                        st.session_state
                    ).context_hash,
                ),
                generate_fn=generate_fn,
                expander_title="Pontosítási kérés (opcionális)",
            )


def _render_arc_candidate_panel() -> None:
    """RESET 2C/2D-F2: readonly előnézet egy függőben lévő `arc_candidate`-
    re, pontosan két művelettel. Csak akkor jelenik meg, ha van ÉRVÉNYES
    candidate — üres/hiányzó candidate esetén nem renderel semmit. RESET
    2D-F2 óta a hívó (`render_flat_seven_point_outline_section`) a teljes
    generáló gomb blokkja UTÁN, de a hét arc-kártya ELŐTT hívja — a
    panel maga nem tud a saját pozíciójáról, ezt kizárólag a hívási hely
    dönti el."""
    sw = ensure_sermon_workshop_state(st.session_state)
    candidate = sw.get("arc_candidate")
    if not isinstance(candidate, dict):
        return
    points = candidate.get("points") if isinstance(candidate.get("points"), dict) else {}
    if not points:
        return

    st.divider()
    with st.container(border=True):
        st.markdown("**Új vázlatjavaslat**")
        st.caption(
            "Ez a javaslat még nem került a kanonikus vázlatba. Nézd át, "
            "majd vedd át vagy vesd el — a kanonikus vázlat addig "
            "változatlan marad."
        )
        for idx, point_key in enumerate(_ARC_POINT_KEYS, start=1):
            title = _ARC_CARD_TITLES[point_key]
            text = str((points.get(point_key) or {}).get("text") or "")
            st.markdown(f"**{idx}. {title}**")
            st.markdown(text if text.strip() else "_(üres)_")

        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Javaslat átvétele", type="primary", key="sw_flat_arc_candidate_accept"
            ):
                context = build_arc_generation_context(st.session_state)
                result = accept_arc_candidate(
                    st.session_state,
                    reference=context.reference,
                    context_hash=context.context_hash,
                )
                if result["accepted"]:
                    st.session_state[_RESYNC_FLAG] = True
                    _toast_and_rerun(
                        "A javaslat mind a hét pontba bekerült — ellenőrizd "
                        "és alakítsd tovább az alábbi kártyákban."
                    )
                else:
                    reason = str(result.get("reason") or "")
                    st.warning(
                        _ARC_CANDIDATE_REJECT_MESSAGES.get(
                            reason, "A javaslat nem fogadható el."
                        )
                    )
        with c2:
            if st.button("Javaslat elvetése", key="sw_flat_arc_candidate_discard"):
                discard_arc_candidate(st.session_state)
                _toast_and_rerun("A javaslat elvetve.")


def _render_flat_legacy_outline_panel() -> None:
    """RESET 2B/2E-6a: régi (2–4 beszédegységes) vázlat read-only
    megjelenítése — KIZÁRÓLAG migrációs fallbackként, amíg a felhasználó
    még nem kezdett bele az ÚJ workflow-ba. Nem szerkeszthető, nem
    másolja át automatikusan az adatot az `arc`-ba — nincs „Átemelem”
    gomb.

    RESET 2E-6a (2026-08-20): a korábbi feltétel (kizárólag az `arc`
    üressége) élesben ellenőrizve olyan állapotot engedett meg, ahol ez a
    panel EGYSZERRE jelent meg a blueprint/developed-outline szekcióval —
    ha a felhasználó a hét arc-kártyát sosem töltötte ki, de közvetlenül
    blueprintet és részletes vázlatot generált (ezekhez nem kötelező az
    arc). Ez a felhasználónak két, fogalmilag versengő "vázlat"-ot
    mutatott egyszerre. A kiegészített feltétel ezt zárja ki: a legacy
    panel csak akkor jelenik meg, ha SEM az arc, SEM semmilyen érdemi ÚJ
    workflow-állapot (blueprint tartalom, függőben lévő developed-outline
    candidate, vagy kanonikus developed_outline) nincs jelen. A legacy
    adat és kód VÁLTOZATLAN — csak az egyidejű UI-megjelenés szűnik meg."""
    sw = ensure_sermon_workshop_state(st.session_state)
    arc = sw.get("arc") if isinstance(sw.get("arc"), dict) else {}
    has_new_arc_content = any(
        str((arc.get(key) or {}).get("text") or "").strip() for key in _ARC_POINT_KEYS
    )
    if has_new_arc_content:
        return

    blueprint = sw.get("blueprint") if isinstance(sw.get("blueprint"), dict) else {}
    has_blueprint_content = bool(str(blueprint.get("central_claim") or "").strip())
    has_outline_candidate = isinstance(sw.get("developed_outline_candidate"), dict)
    developed_outline = sw.get("developed_outline")
    developed_outline = developed_outline if isinstance(developed_outline, dict) else {}
    has_canonical_outline = bool(developed_outline.get("movements"))
    if has_blueprint_content or has_outline_candidate or has_canonical_outline:
        return

    legacy_outline = sw.get("sermon_outline")
    if not outline_has_content(legacy_outline):
        return

    legacy_text = outline_canonical_text(legacy_outline)
    if not legacy_text.strip():
        return

    st.divider()
    with st.container(border=True):
        st.markdown("**Korábbi vázlat – régi formátum**")
        st.caption(
            "Csak megtekintésre — nem szerkeszthető, és nem kerül át "
            "automatikusan a fenti hét pontba."
        )
        st.markdown(legacy_text)


_BLUEPRINT_STRUCTURE_MODE_LABELS: dict[str, str] = {
    "seven_point": "Hétpontos ív",
    "merged": "Összevont szerkezet",
    "custom": "Egyedi szerkezet",
}


def _render_blueprint_details_inline(blueprint: dict) -> None:
    """RESET 2E-6b / FINAL SERMON UX POLISH: a tervrajz érdemi tartalma
    (`central_claim`, `textual_center`, a szerkezeti mód magyar címkéje,
    movementenként `function`+`core_idea`) — SZÁNDÉKOSAN NEM jelenik meg
    itt: `arc_fit.verdict`/`arc_fit.reason` (a döntés INDOKLÁSA, nem a
    felhasználónak szól), `key_support.*` (a developed outline-ban már
    konkretizálva van), és `grounded_in` provenance-tokenek — ezek belső,
    technikai részletek.

    Inline renderel (NEM saját `st.expander`), mert a hívója
    (`_render_blueprint_status_and_generate_button`) már maga egy
    összecsukható expander — Streamlit nem enged egymásba ágyazott
    expandereket."""
    central_claim = str(blueprint.get("central_claim") or "").strip()
    if central_claim:
        st.markdown(f"**{central_claim}**")
    textual_center = str(blueprint.get("textual_center") or "").strip()
    if textual_center:
        st.caption(textual_center)

    structure = blueprint.get("recommended_structure")
    structure = structure if isinstance(structure, dict) else {}
    mode = str(structure.get("mode") or "").strip()
    if mode:
        st.caption(_BLUEPRINT_STRUCTURE_MODE_LABELS.get(mode, mode))

    movements = structure.get("movements")
    for movement in movements if isinstance(movements, list) else []:
        if not isinstance(movement, dict):
            continue
        function = str(movement.get("function") or "").strip()
        core_idea = str(movement.get("core_idea") or "").strip()
        if not (function or core_idea):
            continue
        if function and core_idea:
            st.markdown(f"- **{function}**: {core_idea}")
        else:
            st.markdown(f"- {function or core_idea}")


def _render_blueprint_status_and_generate_button(
    *, generate_fn: GenerateFn | None
) -> None:
    """RESET 2E-4: a homiletikai blueprint minimális UI-ja.

    A blueprintnek NINCS candidate-lifecycle-ja (RESET 2E-1/2E-2
    szerződés, itt sem változik): sikeres generálás közvetlenül a
    kanonikus `sermon_workshop.blueprint`-et írja, érvénytelen válasz
    esetén a kanonikus blueprint bit-pontosan változatlan marad — ezt a
    `generate_sermon_blueprint()` már garantálja, a UI csak megjeleníti
    az eredményt. A `warnings` mindig látható, ha van tartalma, de itt
    NINCS "feloldás" — pusztán tájékoztató jelzés a generáláshoz.

    FINAL SERMON UX POLISH (2026-08-21): a tervrajz továbbra is a motor
    része (adatmodell, generálás, canonical state, hash/freshness logika
    változatlan) — de a normál felhasználói UI-ban túl nagy vizuális
    hangsúlyt kapott ahhoz képest, amennyi tényleges olvasói értéke van.
    Ezért a teljes állapot/részletek/figyelmeztetések/újragenerálás-gomb
    egyetlen, alapértelmezetten összecsukott expanderbe kerül — a
    felhasználó a hétpontos ívből normál esetben közvetlenül a részletes
    munkavázlathoz halad tovább, anélkül, hogy ezt ki kellene nyitnia.
    A `warnings` (RESET 2E-6b korábbi döntése szerint korábban szándékosan
    KÍVÜL maradt a részletek-expanderen) itt is az expanderen BELÜL van,
    mert most már maga a teljes blokk egyetlen összecsukható egység —
    nincs mód rá, hogy csak a figyelmeztetés maradjon kívül anélkül, hogy
    két egymásba ágyazott expander jönne létre (amit Streamlit nem
    enged)."""
    sw = ensure_sermon_workshop_state(st.session_state)
    blueprint = sw.get("blueprint") if isinstance(sw.get("blueprint"), dict) else {}
    has_blueprint = bool(str(blueprint.get("central_claim") or "").strip())
    fresh = is_blueprint_fresh(st.session_state) if has_blueprint else False
    running = bool(st.session_state.get(_KEY_BLUEPRINT_GEN_RUNNING))

    with st.expander("Igehirdetési tervrajz megtekintése", expanded=False):
        st.caption(
            "Belső szerkezeti terv, amely a textus és az összegyűjtött "
            "anyag alapján kialakítja az igehirdetés központi gondolatát "
            "és logikai ívét. Erre épül a részletes vázlat."
        )
        if not has_blueprint:
            st.info("Még nincs tervrajz ehhez az igehelyhez.")
            label = "Tervrajz készítése"
        elif not fresh:
            st.warning(
                "A tervrajz elavult: a kanonikus bemenet megváltozott az "
                "elkészülte óta."
            )
            label = "Tervrajz újragenerálása"
        else:
            st.success("A tervrajz friss és elkészült.")
            label = "Tervrajz újragenerálása"

        if has_blueprint:
            _render_blueprint_details_inline(blueprint)

        warnings = blueprint.get("warnings")
        for warning in warnings if isinstance(warnings, list) else []:
            st.warning(str(warning))

        if st.button(
            label,
            key="sw_flat_blueprint_generate",
            disabled=running or generate_fn is None,
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                st.session_state[_KEY_BLUEPRINT_GEN_RUNNING] = True
                try:
                    with st.spinner("Igehirdetési tervrajz készül…"):
                        outcome = generate_sermon_blueprint(
                            st.session_state, generate_fn=generate_fn
                        )
                finally:
                    st.session_state[_KEY_BLUEPRINT_GEN_RUNNING] = False

                if not outcome.ok:
                    st.error(outcome.error_message)
                else:
                    _toast_and_rerun("A tervrajz elkészült.")
        if generate_fn is None:
            st.caption("Az MI-segéd jelenleg nem elérhető.")


_DEVELOPED_OUTLINE_READONLY_SUPPORT_LABELS: tuple[tuple[str, str], ...] = (
    ("Szövegi kapaszkodó", "exegetical_support"),
    ("Eredeti nyelvi támasz", "original_language_support"),
    ("Történeti/teológiai támasz", "historical_theological_support"),
    ("Illusztrációs irány", "illustration_direction"),
    ("Alkalmazási irány", "application_direction"),
)


def _render_developed_outline_movement_readonly(index: int, movement: dict) -> None:
    """Egy vázlat-mozgás read-only megjelenítése — a függőben lévő
    `developed_outline_candidate` előnézetéhez.

    FINAL SERMON UX POLISH (2026-08-21) + FINAL SERMON WORKFLOW +
    OUTLINE PRESENTATION POLISH (2026-08-21): a főnézetben csak
    sorszám+cím, funkció, fő állítás, kibontás-bullet-ek és átvezetés
    jelenik meg. A támasz-/irány-mezők (`exegetical_support`,
    `original_language_support`, `historical_theological_support`,
    `illustration_direction`, `application_direction`) EBBEN a
    függvényben egyáltalán NEM jelennek meg — azokat a teljes candidate
    alatt EGYETLEN, közös "Háttéranyagok a vázlathoz" expander gyűjti
    össze (ld. `_render_developed_outline_support_material_readonly`),
    hogy ne tördelje szét pontonként a javaslatot."""
    title = str(movement.get("title") or "").strip() or f"{index}. mozgás"
    st.markdown(f"**{index}. {title}**")
    function = str(movement.get("function") or "").strip()
    if function:
        st.caption(function)
    main_claim = str(movement.get("main_claim") or "").strip()
    if main_claim:
        st.markdown(main_claim)
    development = movement.get("development")
    for item in development if isinstance(development, list) else []:
        st.markdown(f"- {item}")
    transition = str(movement.get("transition_to_next") or "").strip()
    if transition:
        st.caption(f"Átvezetés: {transition}")


def _render_developed_outline_support_material_readonly(
    movements: list[dict], *, start: int = 1
) -> None:
    """A `_render_developed_outline_support_material_expander` read-only
    megfelelője a még el nem bírált candidate-hez — ugyanaz az elv:
    EGYETLEN, közös, alapértelmezetten összecsukott "Háttéranyagok a
    vázlathoz" expander, mozgásonként csoportosítva, csak a ténylegesen
    kitöltött mezőkkel, csak akkor jelenik meg egyáltalán, ha van
    tényleges tartalom valahol."""
    indexed = list(enumerate(movements, start=start))
    with_content = [
        (index, movement)
        for index, movement in indexed
        if isinstance(movement, dict)
        and _developed_outline_movement_has_support_content(movement)
    ]
    if not with_content:
        return

    with st.expander("Háttéranyagok a vázlathoz", expanded=False):
        for i, (index, movement) in enumerate(with_content):
            if i > 0:
                st.divider()
            title = str(movement.get("title") or "").strip() or f"{index}. mozgás"
            st.caption(f"{index}. {title}")
            for label, field in _DEVELOPED_OUTLINE_READONLY_SUPPORT_LABELS:
                if field in _DEVELOPED_MOVEMENT_LIST_FIELDS:
                    items = movement.get(field)
                    items = items if isinstance(items, list) else []
                    items = [str(item) for item in items if str(item).strip()]
                    if items:
                        st.caption(f"{label}: " + "; ".join(items))
                else:
                    value = str(movement.get(field) or "").strip()
                    if value:
                        st.caption(f"{label}: {value}")


def _handoff_developed_outline_to_writing_desk() -> None:
    """Candidate elfogadása + teljes vázlat átadása az Íróasztalnak."""
    context = build_developed_outline_context(st.session_state)
    result = apply_developed_outline_handoff(
        st.session_state,
        reference=context.reference,
        context_hash=context.context_hash,
    )
    if result.get("accepted") and result.get("transferred"):
        _clear_developed_outline_edit_widgets()
        _toast_and_rerun("A részletes vázlat az Íróasztalra került.")
        return
    reason = str(result.get("reason") or "")
    st.warning(
        _DEVELOPED_OUTLINE_CANDIDATE_REJECT_MESSAGES.get(
            reason, "A javaslat nem fogadható el."
        )
    )


def _render_developed_outline_candidate_panel() -> None:
    """RESET 2E-4: readonly előnézet egy függőben lévő `developed_outline_
    candidate`-re, pontosan két művelettel — az `_render_arc_candidate_
    panel()` mintája, a részletes-vázlat state-szerződéshez igazítva.
    Csak akkor jelenik meg, ha van ÉRVÉNYES, tartalommal bíró candidate."""
    sw = ensure_sermon_workshop_state(st.session_state)
    candidate = sw.get("developed_outline_candidate")
    if not isinstance(candidate, dict):
        return
    outline = candidate.get("outline")
    outline = outline if isinstance(outline, dict) else {}
    movements = outline.get("movements")
    movements = movements if isinstance(movements, list) else []
    if not movements:
        return

    st.divider()
    with st.container(border=True):
        st.markdown("**Új részletes vázlatjavaslat**")
        st.caption(
            "Ez a javaslat még nem került a kanonikus vázlatba. Nézd át, "
            "majd vedd át vagy vesd el — a kanonikus vázlat addig "
            "változatlan marad."
        )
        meta = sw.get("developed_outline_meta")
        meta = meta if isinstance(meta, dict) else {}
        if str(meta.get("manually_updated_at") or "").strip():
            st.warning(
                "Az elfogadás lecseréli a jelenlegi, kézzel módosított "
                "vázlatot is."
            )
        structure_note = str(outline.get("structure_note") or "").strip()
        if structure_note:
            st.caption(structure_note)
        for idx, movement in enumerate(movements, start=1):
            if isinstance(movement, dict):
                _render_developed_outline_movement_readonly(idx, movement)

        _render_developed_outline_support_material_readonly(movements, start=1)

        if st.session_state.get(OUTLINE_HANDOFF_CONFIRM_KEY):
            st.warning(
                "Az Íróasztalon már van jegyzet. Lecseréled a teljes tartalmát "
                "erre a vázlatra?"
            )
            y1, y2 = st.columns(2)
            with y1:
                if st.button(
                    "Igen, lecserélem",
                    type="primary",
                    key="sw_flat_outline_handoff_replace_yes",
                ):
                    _handoff_developed_outline_to_writing_desk()
            with y2:
                if st.button("Mégse", key="sw_flat_outline_handoff_replace_no"):
                    st.session_state[OUTLINE_HANDOFF_CONFIRM_KEY] = False
                    st.rerun()
        else:
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "Szerkesztés az Íróasztalon",
                    type="primary",
                    key="sw_flat_outline_candidate_accept",
                ):
                    if writing_desk_draft_needs_overwrite_confirmation(
                        st.session_state
                    ):
                        st.session_state[OUTLINE_HANDOFF_CONFIRM_KEY] = True
                        st.rerun()
                    else:
                        _handoff_developed_outline_to_writing_desk()
            with c2:
                if st.button("Vázlat elvetése", key="sw_flat_outline_candidate_discard"):
                    st.session_state[OUTLINE_HANDOFF_CONFIRM_KEY] = False
                    discard_developed_outline_candidate(st.session_state)
                    _toast_and_rerun("A javaslat elvetve.")


# RESET 2E-5: a kanonikus, MÁR ELFOGADOTT részletes vázlat kézi
# szerkesztése. A widget-kulcs a mozgás SAJÁT, stabil `key`-éből (nem az
# indexéből) épül — ez a mozgás-azonosítás forrása marad addig, amíg a
# kanonikus vázlat maga nem cserélődik le (candidate-elfogadás). A
# `key`, a `structure_mode`, a mozgás-sorrend/darabszám és a
# `structure_note` SZÁNDÉKOSAN nincs ebben a listában — ezekhez nem
# létezik (és itt nem is készül) UI-widget.
_DEVELOPED_OUTLINE_EDIT_WIDGET_PREFIX = "sw_flat_outline_edit_"

_OUTLINE_SHORT_TEXT_FIELDS: tuple[str, ...] = ("title", "function")
_OUTLINE_TEXTAREA_FIELDS: tuple[str, ...] = (
    "main_claim",
    "illustration_direction",
    "application_direction",
    "transition_to_next",
)
_OUTLINE_FIELD_LABELS: dict[str, str] = {
    "title": "Cím",
    "function": "Szerep",
    "main_claim": "Fő állítás",
    "development": "Kibontás (soronként egy gondolat)",
    "exegetical_support": "Szövegi kapaszkodó (soronként egy elem)",
    "original_language_support": "Eredeti nyelvi támasz (soronként egy elem)",
    "historical_theological_support": (
        "Történeti/teológiai támasz (soronként egy elem)"
    ),
    "illustration_direction": "Illusztrációs irány",
    "application_direction": "Alkalmazási irány",
    "transition_to_next": "Átvezetés a következőhöz",
}


def _developed_outline_edit_widget_key(movement_key: str, field: str) -> str:
    return f"{_DEVELOPED_OUTLINE_EDIT_WIDGET_PREFIX}{movement_key}_{field}"


def _clear_developed_outline_edit_widgets() -> None:
    """A régi szerkesztő-widgetek session_state-kulcsainak törlése —
    KIZÁRÓLAG candidate-elfogadás után hívandó, MIELŐTT a rerun lefut
    (`_clear_movement_widgets()` bevett mintája, a részletes-vázlat
    szerkesztőhöz igazítva)."""
    stale = [
        key
        for key in list(st.session_state.keys())
        if isinstance(key, str) and key.startswith(_DEVELOPED_OUTLINE_EDIT_WIDGET_PREFIX)
    ]
    for key in stale:
        st.session_state.pop(key, None)


def _flat_save_developed_outline_movement_field(
    index: int, movement_key: str, field: str
) -> None:
    """Egy szerkesztett mozgás-mező automatikus mentése — közvetlenül a
    meglévő `update_developed_outline_movement_field()` adatmodell-
    függvényt hívja, VÁLTOZTATÁS NÉLKÜL. Lista-mezőnél a widget nyers,
    többsoros szövegét itt, a UI-ban alakítjuk explicit listává —
    trimmelt, nem üres sorok, sorrendben — mert a mutátor `_normalize_
    str_list()` szigorúan CSAK `list` bemenetet fogad el, nyers stringet
    csendben üres listává alakítana. Az esetleges `index_out_of_range`
    legitim, futásidejű állapot (a vázlat időközben megváltozhatott) —
    a mutátor ilyenkor sem dob kivételt, itt sincs külön kezelés rá."""
    widget_key = _developed_outline_edit_widget_key(movement_key, field)
    raw = st.session_state.get(widget_key)
    if field in _DEVELOPED_MOVEMENT_LIST_FIELDS:
        value: Any = [
            line.strip() for line in str(raw or "").split("\n") if line.strip()
        ]
    else:
        value = raw
    update_developed_outline_movement_field(
        st.session_state, index=index, field=field, value=value
    )


def _render_developed_outline_edit_field(
    *,
    index: int,
    movement_key: str,
    movement: dict,
    field: str,
    widget: str,
    height: int | None = None,
    label: str | None = None,
) -> None:
    """Egy szerkeszthető mozgás-mező widgetjének kiírása — a seed-elés
    (widget hiányában a kanonikus tartalomból) és az `on_change`-mentés
    közös a `text_input`/`text_area` esetek között, csak a widget típusa
    és mérete tér el (RESET 2E-6b: elsődleges vs. másodlagos mezők
    vizuális elkülönítéséhez).

    `label`: opcionális felülírás (pl. FINAL SERMON UX POLISH: a `title`
    mezőnél a sorszám a label részévé válik, "1. Cím" formában) — None
    esetén az alapértelmezett `_OUTLINE_FIELD_LABELS[field]` marad."""
    widget_key = _developed_outline_edit_widget_key(movement_key, field)
    if widget_key not in st.session_state:
        if field in _DEVELOPED_MOVEMENT_LIST_FIELDS:
            items = movement.get(field)
            items = items if isinstance(items, list) else []
            st.session_state[widget_key] = "\n".join(str(item) for item in items)
        else:
            st.session_state[widget_key] = str(movement.get(field) or "")

    label = label if label is not None else _OUTLINE_FIELD_LABELS[field]
    if widget == "text_input":
        st.text_input(
            label,
            key=widget_key,
            on_change=_flat_save_developed_outline_movement_field,
            args=(index, movement_key, field),
        )
    else:
        st.text_area(
            label,
            key=widget_key,
            height=height,
            on_change=_flat_save_developed_outline_movement_field,
            args=(index, movement_key, field),
        )


_DEVELOPED_OUTLINE_SUPPORT_FIELDS: tuple[str, ...] = (
    "exegetical_support",
    "original_language_support",
    "historical_theological_support",
    "illustration_direction",
    "application_direction",
)


def _developed_outline_field_has_content(movement: dict, field: str) -> bool:
    value = movement.get(field)
    if field in _DEVELOPED_MOVEMENT_LIST_FIELDS:
        items = value if isinstance(value, list) else []
        return any(str(item).strip() for item in items)
    return bool(str(value or "").strip())


def _developed_outline_movement_has_support_content(movement: dict) -> bool:
    return any(
        _developed_outline_field_has_content(movement, field)
        for field in _DEVELOPED_OUTLINE_SUPPORT_FIELDS
    )


def _render_developed_outline_movement_editable(index: int, movement: dict) -> None:
    """Egy kanonikus vázlat-mozgás szerkeszthető megjelenítése.

    FINAL SERMON UX POLISH (2026-08-21) + FINAL SERMON WORKFLOW +
    OUTLINE PRESENTATION POLISH (2026-08-21): korábban (RESET 2E-6b) a
    teljes mozgás — a fő állítástól a támasz-/irány-mezőkig — EGYETLEN,
    alapértelmezetten összecsukott `st.expander`-be volt zárva. A cél
    most a gyors, szószékre-vihető áttekinthetőség: a FŐNÉZET
    (sorszám+cím, funkció, fő állítás, kibontás-bullet-ek, átvezetés)
    mindig KÖZVETLENÜL látható, egy könnyű kártya-keretben
    (`st.container(border=True)`). A másodlagos SEGÉDANYAG
    (`exegetical_support`, `original_language_support`,
    `historical_theological_support`, `illustration_direction`,
    `application_direction`) EBBEN a függvényben egyáltalán NEM jelenik
    meg — azt a teljes vázlat alatt EGYETLEN, közös "Háttéranyagok a
    vázlathoz" expander gyűjti össze, mozgásonként csoportosítva (ld.
    `_render_developed_outline_support_material_expander`), hogy ne
    tördelje szét pontonként a vázlatot.

    A structured adatmodell, a mutátorok és a `key`-alapú widget-
    azonosítás VÁLTOZATLAN — kizárólag a RENDERELÉS egyszerűsödött.
    `index` a mozgás TÉNYLEGES, 0-alapú pozíciója a kanonikus listában
    (ez kell a mutátorhíváshoz); a widget-kulcsokhoz a mozgás saját
    `key`-e (nem az index) a forrás."""
    movement_key = str(movement.get("key") or f"movement_{index}")

    with st.container(border=True, key=f"sw_flat_outline_movement_{movement_key}"):
        _render_developed_outline_edit_field(
            index=index,
            movement_key=movement_key,
            movement=movement,
            field="title",
            widget="text_input",
            label=f"{index + 1}. Cím",
        )
        _render_developed_outline_edit_field(
            index=index,
            movement_key=movement_key,
            movement=movement,
            field="function",
            widget="text_input",
        )
        _render_developed_outline_edit_field(
            index=index,
            movement_key=movement_key,
            movement=movement,
            field="main_claim",
            widget="text_area",
            height=90,
        )
        _render_developed_outline_edit_field(
            index=index,
            movement_key=movement_key,
            movement=movement,
            field="development",
            widget="text_area",
            height=100,
        )
        _render_developed_outline_edit_field(
            index=index,
            movement_key=movement_key,
            movement=movement,
            field="transition_to_next",
            widget="text_area",
            height=68,
        )


def _render_developed_outline_support_material_expander(
    movements: list[dict],
) -> None:
    """A teljes kanonikus vázlat EGYETLEN, közös háttéranyag-expandere.

    FINAL SERMON WORKFLOW + OUTLINE PRESENTATION POLISH (2026-08-21):
    korábban minden mozgásnak SAJÁT, pontonkénti "Segédanyag ehhez a
    ponthoz" expandere volt — ez a vázlatot vizuálisan feldarabolta.
    Most a teljes vázlat alatt EGYETLEN, alapértelmezetten összecsukott
    "Háttéranyagok a vázlathoz" expander gyűjti össze az összes mozgás
    segédanyagát, mozgásonként csoportosítva egy rövid alcím alatt — és
    az expander maga is CSAK akkor jelenik meg, ha legalább egy
    mozgásnak van tényleges segédanyag-tartalma; egy adott mozgás
    csoportja pedig csak akkor jelenik meg ezen belül, ha annak a
    mozgásnak van tartalma (nincs üres placeholder-csoport)."""
    movements_with_content = [
        (index, movement)
        for index, movement in enumerate(movements)
        if isinstance(movement, dict)
        and _developed_outline_movement_has_support_content(movement)
    ]
    if not movements_with_content:
        return

    with st.expander("Háttéranyagok a vázlathoz", expanded=False):
        for i, (index, movement) in enumerate(movements_with_content):
            if i > 0:
                st.divider()
            movement_key = str(movement.get("key") or f"movement_{index}")
            title = str(movement.get("title") or "").strip() or f"{index + 1}. mozgás"
            st.caption(f"{index + 1}. {title}")
            for field in _DEVELOPED_OUTLINE_SUPPORT_FIELDS:
                if not _developed_outline_field_has_content(movement, field):
                    continue
                _render_developed_outline_edit_field(
                    index=index,
                    movement_key=movement_key,
                    movement=movement,
                    field=field,
                    widget="text_area",
                    height=68,
                )


def _developed_outline_freshness(
    session_state: MutableMapping[str, Any],
) -> tuple[bool, bool, str, str]:
    """RESET 2E-6a: a kanonikus `developed_outline` upstream frissessége —
    KIZÁRÓLAG a meglévő `build_developed_outline_context`/`is_blueprint_
    fresh` szerződésekből SZÁRMAZTATVA, semmilyen új hash-logika vagy
    perzisztált mező nélkül.

    Visszatérés: `(stale, reference_changed, stored_reference,
    current_reference)`.

    `stale` akkor `True`, ha VAGY a jelenlegi blueprint maga elavult
    (`is_blueprint_fresh() == False` — pl. egy arc-pont vagy a textus
    módosult a blueprint elkészülte óta), VAGY a jelenlegi, FRISS
    blueprintből újraszámolt developed-outline-context-hash eltér a
    kanonikus vázlat SAJÁT, tárolt `developed_outline_meta.context_hash`
    értékétől (pl. a blueprintet időközben — akár ugyanabból a bemenetből
    — újragenerálták, és más tartalommal állt elő, vagy az igehely/
    bibliai szöveg megváltozott). `reference_changed` külön jelzi, ha
    emellett a tárolt és a jelenlegi igehely is konkrétan eltér — ez egy
    élesebb, konkrétabb figyelmeztető szöveget indokol.

    Nincs kanonikus tartalom vagy nincs tárolt hash (pl. réges-régi
    projekt) esetén `stale=False` — ezekben az esetekben nincs elég
    infó a döntéshez, és a hamis pozitív jelzés rosszabb, mint a csend."""
    sw = ensure_sermon_workshop_state(session_state)
    outline = sw.get("developed_outline")
    outline = outline if isinstance(outline, dict) else {}
    if not outline.get("movements"):
        return False, False, "", ""

    meta = sw.get("developed_outline_meta")
    meta = meta if isinstance(meta, dict) else {}
    stored_hash = str(meta.get("context_hash") or "").strip()
    stored_reference = str(meta.get("reference") or "").strip()
    if not stored_hash:
        return False, False, stored_reference, ""

    current_context = build_developed_outline_context(session_state)
    current_reference = current_context.reference

    stale = (
        not is_blueprint_fresh(session_state)
        or not current_context.context_hash
        or current_context.context_hash != stored_hash
    )
    reference_changed = bool(
        stale
        and stored_reference
        and current_reference
        and stored_reference != current_reference
    )
    return stale, reference_changed, stored_reference, current_reference


def _format_human_timestamp(value: str) -> str:
    """`datetime.now().isoformat(timespec="seconds")` -> emberileg
    olvasható formátum. Sikertelen feldolgozásnál a nyers értéket adja
    vissza — sosem dob kivételt, ez pusztán megjelenítési segédlet."""
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return dt.strftime("%Y.%m.%d. %H:%M")


def _render_developed_outline_canonical_readonly() -> None:
    """A már elfogadott kanonikus vázlat read-only áttekintése.

    A második hétmezős szerkesztő UI kivezetve: a szabad szerkesztés az
    Íróasztalon történik. A structured `developed_outline` megmarad.
    """
    sw = ensure_sermon_workshop_state(st.session_state)
    outline = sw.get("developed_outline")
    outline = outline if isinstance(outline, dict) else {}
    movements = outline.get("movements")
    movements = movements if isinstance(movements, list) else []
    if not movements:
        return

    st.divider()
    with st.container(border=True, key="sw_flat_outline_canonical"):
        st.markdown("**Részletes prédikációs munkavázlat**")
        st.caption("A szabad szerkesztés az Íróasztalon történik.")

        meta = sw.get("developed_outline_meta")
        meta = meta if isinstance(meta, dict) else {}
        manually_updated_at = str(meta.get("manually_updated_at") or "").strip()
        if manually_updated_at:
            st.caption(f"Kézzel módosítva: {_format_human_timestamp(manually_updated_at)}.")
        else:
            st.caption("AI által generált, még nem szerkesztett vázlat.")

        stale, reference_changed, stored_reference, current_reference = (
            _developed_outline_freshness(st.session_state)
        )
        if reference_changed:
            st.warning(
                f"Ez a vázlat még a(z) „{stored_reference}” igehelyhez "
                f"készült — a jelenlegi igehely már „{current_reference}”. "
                "A tartalom megmarad, de valószínűleg nem ehhez a "
                "textushoz illik; érdemes új tervrajzot és új részletes "
                "vázlatot készíteni."
            )
        elif stale:
            st.warning(
                "Ez a vázlat egy KORÁBBI tervrajzból készült — az "
                "igehely, a bibliai szöveg vagy a tervrajz azóta "
                "megváltozott. A tartalom megmarad és tovább "
                "szerkesztheted, de érdemes lehet új tervrajzot és/vagy "
                "új részletes vázlatot készíteni."
            )

        structure_note = str(outline.get("structure_note") or "").strip()
        if structure_note:
            st.caption(structure_note)
        for index, movement in enumerate(movements, start=1):
            if isinstance(movement, dict):
                _render_developed_outline_movement_readonly(index, movement)

        _render_developed_outline_support_material_readonly(movements, start=1)


def render_flat_developed_outline_section(
    *, generate_fn: GenerateFn | None = None
) -> None:
    """A kétlépcsős vázlatmotor (blueprint -> részletes vázlat) UI-bekötése.

    FINAL SERMON WORKFLOW + OUTLINE PRESENTATION POLISH (2026-08-21): a
    blueprint (tervrajz) megszűnt user-facing GATE lenni — korábban
    (RESET 2E-4) a "Részletes vázlat készítése" gomb csak érvényes,
    KANONIKUS ÉS FRISS blueprintnél volt aktív, és a felhasználónak
    KÜLÖN, előzetes kattintással kellett elkészítenie a blueprintet. Most
    egyetlen gombnyomás:
      1. ha van friss, érvényes kanonikus blueprint -> azt használja,
         AI-hívás nélkül;
      2. ha nincs, vagy elavult (`is_blueprint_fresh()` szerint) -> a
         HÁTTÉRBEN, ugyanabban a kattintásban előbb elkészíti/frissíti
         (`generate_sermon_blueprint`) — a blueprint MOTORJA (schema,
         canonical state, hash/freshness-logika, validálás) VÁLTOZATLAN,
         kizárólag ez az UI-orchestráció bővült;
      3. ha az automatikus blueprint-generálás sikertelen, a részletes
         vázlat `generate_developed_outline` hívása EL SEM INDUL — rövid,
         kulturált hibaüzenet jelenik meg, a pontos ok a szerver-konzol
         logban (`textus.sermon_workshop` logger) marad;
      4. sikeres (vagy már eleve friss) blueprint esetén AZONNAL,
         ugyanabban a kattintásban elindul a részletes vázlat
         candidate-generálása — nincs második kattintás.

    A `_render_blueprint_status_and_generate_button` (a tervrajz
    összecsukott, alapértelmezetten rejtett állapot/részletek/
    figyelmeztetés/kézi-újragenerálás panelje) VÁLTOZATLANUL megmarad —
    de többé NEM előfeltétele a részletes vázlatnak, tisztán opcionális
    betekintési/kézi felülbírálási lehetőség marad."""
    render_work_section(
        title="Részletes prédikációs munkavázlat",
        context="Igehirdetési műhely",
    )

    _render_blueprint_status_and_generate_button(generate_fn=generate_fn)

    sw = ensure_sermon_workshop_state(st.session_state)
    context = build_developed_outline_context(st.session_state)
    missing = context.missing_required_fields()
    # KIZÁRÓLAG az igehely/bibliai szöveg hiánya blokkol ténylegesen — ezek
    # NEM automatizálhatók, a felhasználónak kell megadnia a Textusműhelyben.
    # A blueprint hiánya/elavultsága önmagában többé NEM blokkoló ok: azt a
    # gombnyomás automatikusan pótolja (ld. lent).
    hard_block_reason = ""
    if "igehely" in missing:
        hard_block_reason = "missing_reference"
    elif "bibliai szöveg" in missing:
        hard_block_reason = "missing_passage_text"

    running = bool(st.session_state.get(_KEY_OUTLINE_GEN_RUNNING))
    has_canonical = bool((sw.get("developed_outline") or {}).get("movements"))
    has_pending_candidate = isinstance(sw.get("developed_outline_candidate"), dict)
    label = (
        "Részletes vázlat újragenerálása"
        if has_canonical or has_pending_candidate
        else "Részletes vázlat készítése"
    )

    with st.container(border=True):
        st.markdown("**Részletes vázlat generálása**")
        if hard_block_reason:
            st.caption(_DEVELOPED_OUTLINE_BLOCK_MESSAGES[hard_block_reason])
        if has_pending_candidate:
            st.caption(
                "Az újragenerálás lecseréli a lenti, még el nem bírált "
                "javaslatot — a kanonikus vázlatot nem érinti."
            )
        if st.button(
            label,
            type="primary",
            key="sw_flat_outline_generate",
            disabled=running or generate_fn is None or bool(hard_block_reason),
        ):
            if generate_fn is None:
                st.warning("Az MI-segéd jelenleg nem elérhető.")
            else:
                st.session_state[_KEY_OUTLINE_GEN_RUNNING] = True
                outline_ready = False
                outcome = None
                try:
                    current_context = build_developed_outline_context(
                        st.session_state
                    )
                    blueprint_needs_prep = bool(
                        current_context.missing_required_fields()
                    ) or not is_blueprint_fresh(st.session_state)

                    outline_ready = True
                    if blueprint_needs_prep:
                        with st.spinner("Igehirdetési tervrajz előkészítése…"):
                            bp_outcome = generate_sermon_blueprint(
                                st.session_state, generate_fn=generate_fn
                            )
                        if not bp_outcome.ok:
                            import logging

                            logging.getLogger("textus.sermon_workshop").error(
                                "auto blueprint generation failed before "
                                "developed outline (reason=%s): %s",
                                bp_outcome.reason,
                                bp_outcome.error_message,
                            )
                            st.error(
                                "Nem sikerült elkészíteni az igehirdetési "
                                "tervrajzot a részletes vázlathoz. Próbáld "
                                "újra, vagy nyisd meg fent a tervrajz-"
                                "panelt kézi generáláshoz."
                            )
                            outline_ready = False

                    if outline_ready:
                        with st.spinner("Részletes munkavázlat készül…"):
                            outcome = generate_developed_outline(
                                st.session_state,
                                generate_fn=generate_fn,
                                # A globális GEMINI_COOLDOWN_S két
                                # LOGIKAILAG FÜGGETLEN felhasználói hívás
                                # közé való — nem az EGYETLEN kattintáson
                                # belül automatikusan láncolt blueprint+
                                # vázlat hívás közé. Csak akkor kerüljük
                                # meg, ha ebben a kattintásban TÉNYLEGESEN
                                # most készült/frissült a blueprint.
                                bypass_cooldown=blueprint_needs_prep,
                            )
                finally:
                    st.session_state[_KEY_OUTLINE_GEN_RUNNING] = False

                if outline_ready and outcome is not None:
                    if not outcome.ok:
                        if outcome.status == "blocked":
                            st.warning(
                                _DEVELOPED_OUTLINE_BLOCK_MESSAGES.get(
                                    outcome.reason, outcome.error_message
                                )
                            )
                        else:
                            st.error(outcome.error_message)
                    else:
                        _toast_and_rerun(
                            "Elkészült egy új részletes vázlatjavaslat — nézd "
                            "át alább."
                        )
        if generate_fn is None:
            st.caption("Az MI-segéd jelenleg nem elérhető.")

    _render_developed_outline_candidate_panel()
    _render_developed_outline_canonical_readonly()


def render_sermon_workshop_shell(
    *,
    generate_fn: GenerateFn | None = None,
) -> None:
    """Igehirdetési műhely — egyszerű, lapos, hétpontos szerkesztőfelület.

    RESET 2B (2026-08-18): a korábbi ötlépéses, popover-navigációs
    munkafolyamat aktív hívási útvonalból leválasztva. A régi függvények
    (`render_workshop_workflow_nav`, `render_entry_point_section`,
    `render_gospel_arc_section`, `render_sermon_path_section`,
    `render_engagement_section`, `render_closing_section`,
    `render_text_core_and_focus_section`, `render_outline_section` és a
    hozzájuk tartozó régi section-szintű MI-segédek) megmaradnak legacy
    kódként, de innen már nem hívódnak.

    RESET 2C (2026-08-19): a „Hétpontos igehirdetési vázlat” szakasz
    megkapja az egyetlen MI-generáló gombot (`sermon_workshop_arc_ai.
    generate_seven_point_arc`, candidate-alapú, üres/nem-üres arc szerint
    applied/candidate döntéssel) — a Word-export egy következő fázisban
    kerül vissza működőképesen.
    """
    st.session_state.pop(_RESYNC_DONE_THIS_RUN, None)
    _apply_sw_ui_resync_if_needed()
    ensure_sermon_workshop_state(st.session_state)
    ensure_text_workshop_state(st.session_state)

    render_page_intro(
        title="Igehirdetési műhely",
        body="",
        workspace_scope=True,
    )

    # A bibliai szöveg a munkaterület szerkezetében, nem külön lebegve.
    render_bible_text_preview(expanded=False)

    st.divider()
    render_flat_text_and_focus_section(generate_fn=generate_fn)

    st.divider()
    render_flat_seven_point_outline_section(generate_fn=generate_fn)

    _render_flat_legacy_outline_panel()

    st.divider()
    render_flat_developed_outline_section(generate_fn=generate_fn)


__all__ = [
    "render_sermon_workshop_shell",
    "render_flat_developed_outline_section",
    "flush_sermon_workshop_from_widgets",
    "render_text_core_and_focus_section",
    "render_sermon_main_idea_section",
    "render_human_condition_section",
    "render_listener_tension_section",
    "render_entry_point_section",
    "render_gospel_arc_section",
    "render_sermon_path_section",
    "render_enrichment_section",
    "render_engagement_section",
    "render_closing_section",
    "render_lection_section",
    "render_prayer_section",
    "render_outline_section",
    "render_diagnostics_section",
]
