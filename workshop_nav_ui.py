"""Közös műhely-navigáció (Textusműhely / Igehirdetési műhely).

Streamlit widgetek + CSS stepper / elsődleges nézetváltó.
A session kulcsok és a navigációs logika változatlan.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from html import escape
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

_DEFAULT_UI_MODE_LABELS: dict[str, str] = {
    "workshop": "Textusműhely",
    "sermon_workshop": "Igehirdetési műhely",
}

# Optional Material icons — a nézetváltó szöveges címkéket használ (ikon nélkül).
_DEFAULT_UI_MODE_ICONS: dict[str, str] = {}

def completed_step_indices(
    options: Sequence[str],
    completed: Iterable[str] | None,
) -> list[int]:
    """0-based indices of completed (not necessarily active) steps."""
    done = {str(x) for x in (completed or ()) if str(x).strip()}
    return [i for i, opt in enumerate(options) if opt in done]


def _render_stepper(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None,
    label: str,
    anchor_base: str,
) -> str:
    """Közös lépésnavigáció-mag — a megjelenést az anchor osztály vezérli.

    A címben nincs ✓; a kész állapotot CSS jelöli (ws-done-N osztályok).
    A session kulcs és a navigációs logika minden variánsnál azonos.
    """
    opts = [str(o) for o in options if str(o).strip()]
    if not opts:
        return ""

    done = {str(x) for x in (completed or ()) if str(x).strip()}
    current = str(st.session_state.get(key) or "")
    if current not in opts:
        st.session_state[key] = opts[0]
        current = opts[0]

    done_classes = " ".join(f"ws-done-{i}" for i in completed_step_indices(opts, done))
    anchor_cls = f"{anchor_base} {done_classes}".strip()
    st.markdown(
        f'<div class="{anchor_cls}" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    # format_func: plain labels only (no checkmark in text)
    st.radio(
        label,
        options=opts,
        key=key,
        format_func=lambda opt: str(opt),
        label_visibility="collapsed",
    )
    return str(st.session_state.get(key) or opts[0])


def render_workshop_stepper(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None = None,
    label: str = "Szakaszok",
) -> str:
    """Függőleges lépésnavigáció (visszafelé kompatibilis változat)."""
    return _render_stepper(
        options,
        key=key,
        completed=completed,
        label=label,
        anchor_base="ws-stepper-anchor",
    )


def render_workshop_step_grid(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None = None,
    label: str = "Munkafolyamat",
) -> str:
    """Felső, több sorba törhető lépésrács — aktív / kész / várakozó.

    Ugyanaz a widget és session kulcs, mint a függőleges stepperé; csak a
    megjelenés más (grid). Mindkét műhely ezt használja.
    """
    return _render_stepper(
        options,
        key=key,
        completed=completed,
        label=label,
        anchor_base="ws-step-grid-anchor",
    )


# Státuszikonok a lépéslistához (glyph-alapú, nem csak szín → hozzáférhető).
# Opcionális műhelyszakaszok: ne „Nincs elkezdve” (kötelező hangnem).
_STEP_STATE_ICON: dict[str, str] = {
    "active": ":material/radio_button_checked:",
    "approved": ":material/verified:",
    "own_emphasis": ":material/edit_note:",
    "ai_suggested": ":material/auto_awesome:",
    "ai_ready": ":material/radio_button_unchecked:",
    # Legacy aliasok (régi completed-halmaz)
    "done": ":material/check_circle:",
    "pending": ":material/radio_button_unchecked:",
}
_STEP_STATE_LABEL: dict[str, str] = {
    "active": "Munkában",
    "approved": "Jóváhagyva",
    "own_emphasis": "Saját hangsúly hozzáadva",
    "ai_suggested": "AI-javaslat elkészült",
    "ai_ready": "AI által kidolgozható",
    "done": "Jóváhagyva",
    "pending": "AI által kidolgozható",
}

# Progress / „kész” számlálóhoz: saját hangsúly vagy jóváhagyás.
_PROGRESS_DONE_STATES = frozenset({"approved", "own_emphasis", "done"})


def render_step_selector(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None = None,
    status_map: Mapping[str, str] | None = None,
    key_prefix: str | None = None,
    outline_ready: bool | None = None,
) -> str:
    """Központi lépésválasztó — zárt sáv (szám · név · státusz · chevron) + lista.

    Nincs Előző/Következő navigáció: a felhasználó szabadon választ a lépések
    közül. A lenyíló panel a triggerhez igazodik (st.popover), Escape és külső
    kattintás bezárja, billentyűzettel használható. A `key` marad a szakasz
    forrása; gombok állítják (tisztán felületi állapot).

    `status_map`: szakasz → ai_ready | ai_suggested | own_emphasis | approved.
    Ha meg van adva, az opcionális műhely hangnemét használja (nem „Nincs elkezdve”).
    """
    opts = [str(o) for o in options if str(o).strip()]
    if not opts:
        return ""

    statuses = {str(k): str(v) for k, v in (status_map or {}).items()}
    done = {str(x) for x in (completed or ()) if str(x).strip()}
    current = str(st.session_state.get(key) or "")
    if current not in opts:
        st.session_state[key] = opts[0]
        current = opts[0]

    idx = opts.index(current)
    total = len(opts)
    prefix = key_prefix or key

    def _underlying(opt: str) -> str:
        """Aktív UI-állapot mögötti tartalmi státusz (progresshez)."""
        if statuses:
            stt = statuses.get(opt, "ai_ready")
            return stt if stt in _STEP_STATE_LABEL else "ai_ready"
        return "done" if opt in done else "pending"

    def _state_of(opt: str) -> str:
        if opt == current:
            return "active"
        return _underlying(opt)

    progress_done = sum(
        1 for o in opts if _underlying(o) in _PROGRESS_DONE_STATES
    )
    pct = int(round((progress_done / total) * 100)) if total else 0

    # Idővonal-csomópontok és összekötő vonal színe lépésenként (st-key osztályok).
    node_rules: list[str] = []
    for i, opt in enumerate(opts):
        state = _state_of(opt)
        underlying = _underlying(opt)
        cls = f"st-key-{prefix}_step_{i}"
        if state == "active":
            icon_c, line_c = "#3f6699", "rgba(160, 150, 135, 0.45)"
        elif underlying in ("approved", "done"):
            icon_c, line_c = "#5a7aa8", "#5a7aa8"
        elif underlying == "own_emphasis":
            icon_c, line_c = "#5a7aa8", "rgba(90, 122, 168, 0.55)"
        elif underlying == "ai_suggested":
            icon_c, line_c = "#7a91b0", "rgba(160, 150, 135, 0.45)"
        else:
            icon_c, line_c = "#9c9384", "rgba(160, 150, 135, 0.45)"
        node_rules.append(
            f'.{cls} button [data-testid="stIconMaterial"]{{color:{icon_c} !important;}}'
            f".{cls} button::before{{background:{line_c} !important;}}"
        )
        if i == 0:
            node_rules.append(f".{cls} button::before{{top:50% !important;}}")
        if i == total - 1:
            node_rules.append(f".{cls} button::before{{bottom:50% !important;}}")
    if total == 1:
        node_rules.append(f".st-key-{prefix}_step_0 button::before{{display:none !important;}}")

    # Zárt sáv státuszszövege (meglévő logika) + mobil rövidítés CSS-változóhoz.
    if outline_ready is True:
        progress_caption = "Vázlathoz elegendő forrás"
        progress_short = "Forrás OK"
    elif outline_ready is False:
        progress_caption = "Vázlathoz még forrás kell"
        progress_short = "Forrás kell"
    elif statuses:
        progress_caption = f"{progress_done} saját hangsúly / jóváhagyás"
        progress_short = f"{progress_done} hangsúly"
    else:
        progress_caption = f"{progress_done} / {total} megtartott anyag"
        progress_short = f"{progress_done}/{total} megtartva"

    step_num_css = f'"{idx + 1}"'
    status_short_css = '"' + progress_short.replace("\\", "\\\\").replace('"', '\\"') + '"'

    with st.container(key="workshop_step_bar"):
        # Horgony + CSS-változók + zárt sáv layout (helyi style: biztosan eljut a böngészőbe).
        # Kerüljük a child combinatort (>) — a Streamlit HTML sanitizer azt kiszűrheti.
        st.markdown(
            '<div class="tx-stepselect-anchor" aria-hidden="true"></div>'
            "<style>"
            ".st-key-workshop_step_bar{"
            "max-width:780px !important;margin-left:auto !important;"
            "margin-right:auto !important;width:100% !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"]{"
            f"--tx-step-pct:{pct};"
            f"--tx-step-num:{step_num_css};"
            f"--tx-step-status-short:{status_short_css};"
            "position:relative !important;width:100% !important;"
            "display:flex !important;align-items:center !important;"
            "min-height:60px !important;height:auto !important;"
            "border-radius:12px !important;"
            "border:1px solid rgba(170,145,112,0.28) !important;"
            "background:rgba(255,253,249,0.97) !important;"
            "box-shadow:0 1px 3px rgba(58,40,22,0.06) !important;"
            "color:var(--tx-primary-deep) !important;"
            "font-family:Inter,Segoe UI,sans-serif !important;"
            "font-weight:600 !important;font-size:0.97rem !important;"
            "padding:0.55rem 2.4rem 0.55rem 0.7rem !important;"
            "text-align:left !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"]:hover{"
            "background:rgba(255,252,247,1) !important;"
            "border-color:rgba(90,122,168,0.38) !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"]:focus-visible{"
            "outline:2px solid var(--tx-primary) !important;outline-offset:2px !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"]::before{"
            "content:var(--tx-step-num,\"1\");flex:0 0 auto;"
            "display:inline-flex !important;align-items:center;justify-content:center;"
            "width:28px;height:28px;min-width:28px;margin-right:0.55rem;"
            "border-radius:999px;background:rgba(90,122,168,0.12);"
            "color:var(--tx-primary-deep);font-size:0.82rem;font-weight:650;line-height:1;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stMarkdownContainer\"]{"
            "position:absolute !important;left:3.15rem !important;right:2.35rem !important;"
            "top:50% !important;transform:translateY(-50%) !important;"
            "width:auto !important;max-width:none !important;margin:0 !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stMarkdownContainer\"] p{"
            "display:flex !important;align-items:center !important;"
            "justify-content:space-between !important;gap:0.75rem !important;"
            "width:100% !important;margin:0 !important;line-height:1.3 !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stMarkdownContainer\"] p strong{"
            "flex:1 1 auto !important;min-width:0 !important;"
            "font-size:15.5px !important;font-weight:600 !important;"
            "color:var(--tx-primary-deep) !important;"
            "display:-webkit-box !important;-webkit-box-orient:vertical !important;"
            "-webkit-line-clamp:2 !important;overflow:hidden !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stMarkdownContainer\"] p span{"
            "flex:0 0 auto !important;color:var(--tx-text-muted) !important;"
            "font-weight:500 !important;font-size:0.8rem !important;"
            "white-space:nowrap !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stIconMaterial\"]{display:none !important;}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stIconMaterial\"]:last-of-type{"
            "display:inline-flex !important;position:absolute !important;"
            "right:0.7rem !important;top:50% !important;transform:translateY(-50%) !important;"
            "color:#5a7aa8 !important;font-size:1.2rem !important;margin:0 !important;"
            "transition:transform 0.18s ease !important;"
            "}"
            "body:has([data-testid=\"stPopoverBody\"] .tx-stepmenu-head) "
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"]{"
            "background:rgba(90,122,168,0.08) !important;"
            "border-color:rgba(90,122,168,0.36) !important;"
            "box-shadow:inset 3px 0 0 0 var(--tx-primary),0 1px 3px rgba(58,40,22,0.05) !important;"
            "}"
            "body:has([data-testid=\"stPopoverBody\"] .tx-stepmenu-head) "
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stIconMaterial\"]:last-of-type{"
            "transform:translateY(-50%) rotate(180deg) !important;"
            "}"
            ".st-key-workshop_step_bar .tx-stepbar-track{margin:3px 2px 0;padding:0;}"
            ".st-key-workshop_step_bar .tx-stepbar-track .tx-wf-progress{"
            "height:3px;background:rgba(160,150,135,0.22);border-radius:999px;overflow:hidden;"
            "}"
            ".st-key-workshop_step_bar .tx-stepbar-track .tx-wf-progress-fill{"
            "height:100%;background:var(--tx-primary,#5a7aa8);border-radius:999px;"
            "}"
            "@media (max-width:768px){"
            ".st-key-workshop_step_bar{max-width:100% !important;}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"]{"
            "min-height:52px !important;padding:0.5rem 2.1rem 0.5rem 0.55rem !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"]::before{"
            "width:26px;height:26px;min-width:26px;margin-right:0.4rem;font-size:0.78rem;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stMarkdownContainer\"]{"
            "left:2.85rem !important;right:2.05rem !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stMarkdownContainer\"] p{"
            "flex-direction:column !important;align-items:flex-start !important;"
            "gap:0.12rem !important;"
            "}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stMarkdownContainer\"] p strong{font-size:14.5px !important;width:100% !important;}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stMarkdownContainer\"] p span{font-size:0 !important;line-height:0 !important;}"
            ".st-key-workshop_step_bar [data-testid=\"stPopoverButton\"] "
            "[data-testid=\"stMarkdownContainer\"] p span::after{"
            "content:var(--tx-step-status-short,\"\");font-size:0.74rem !important;"
            "font-weight:500 !important;color:var(--tx-text-muted) !important;"
            "line-height:1.25 !important;white-space:nowrap !important;"
            "}"
            "}"
            + "".join(node_rules)
            + "</style>",
            unsafe_allow_html=True,
        )

        # Zárt vezérlő: **név** balra, státusz jobbra; a szám CSS ::before jelvény.
        # Ne „N/M elkészült” (az minden lépést kötelezőnek sugall).
        trigger_label = f"**{current}** :gray[{progress_caption}]"
        with st.popover(trigger_label, use_container_width=True):
            if statuses or outline_ready is not None:
                sub = (
                    "A részletes szakaszok opcionálisak. A vázlat a textus és a "
                    "rendelkezésre álló anyag alapján készülhet."
                )
                if outline_ready is True:
                    sub = (
                        "Vázlatkészítéshez elegendő forrásanyag áll rendelkezésre. "
                        "A többi szakasz finomít, nem kötelező."
                    )
                head_count = (
                    f"{progress_done} szakaszban van saját hangsúly vagy jóváhagyás"
                )
            else:
                sub = (
                    "A lépések rugalmasan használhatók; nem kötelező mindet kitölteni."
                )
                head_count = (
                    f"{progress_done} / {total} szakaszban van megtartott anyag"
                )
            st.markdown(
                (
                    '<div class="tx-stepmenu-head">'
                    '<div class="tx-stepmenu-title">Munkafolyamat</div>'
                    f'<div class="tx-stepmenu-sub">{head_count}</div>'
                    f'<div class="tx-stepmenu-sub">{sub}</div>'
                    '<div class="tx-wf-progress" role="presentation">'
                    f'<div class="tx-wf-progress-fill" style="width:{pct}%"></div>'
                    "</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            for i, opt in enumerate(opts):
                state = _state_of(opt)
                # Aktív sor: tartalmi státusz is látszódjon zárójelben, ha van.
                if state == "active" and statuses:
                    detail = _STEP_STATE_LABEL.get(
                        _underlying(opt), _STEP_STATE_LABEL["ai_ready"]
                    )
                    status_txt = f"Munkában · {detail}"
                else:
                    status_txt = _STEP_STATE_LABEL.get(
                        state, _STEP_STATE_LABEL["ai_ready"]
                    )
                label = f"{i + 1}. {opt} :gray[{status_txt}]"
                icon = _STEP_STATE_ICON.get(state) or _STEP_STATE_ICON["ai_ready"]
                if st.button(
                    label,
                    key=f"{prefix}_step_{i}",
                    icon=icon,
                    type="primary" if state == "active" else "secondary",
                    use_container_width=True,
                ):
                    if opt != current:
                        st.session_state[key] = opt
                        st.rerun()
            # Nyitáskor az aktív lépéshez görgetés (mozgáscsökkentést tisztelve).
            # Minden script-újrafuttatáson új iframe jön létre — a korábbi
            # MutationObserver-t explicit lecsatlakoztatjuk (window.parent-en
            # tárolt referencia), hogy reruns között ne halmozódjanak fel
            # élő megfigyelők ugyanarra a document.body-ra (stale/duplikált
            # overlay-tünetek egyik lehetséges forrása).
            components.html(
                """
<script>
(function () {
  try {
    var pdoc = window.parent.document;
    var pwin = window.parent;
    if (pwin.__txStepbarObserver) {
      try { pwin.__txStepbarObserver.disconnect(); } catch (e) {}
      pwin.__txStepbarObserver = null;
    }
    var mq = pwin.matchMedia && pwin.matchMedia('(prefers-reduced-motion: reduce)');
    var reduce = !!(mq && mq.matches);
    function scrollActive() {
      var body = pdoc.querySelector('[data-testid="stPopoverBody"]');
      if (!body) return;
      var act = body.querySelector('.stButton > button[kind="primary"]');
      if (act) act.scrollIntoView({ block: 'center', behavior: reduce ? 'auto' : 'smooth' });
    }
    setTimeout(scrollActive, 60);
    var obs = new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var added = muts[i].addedNodes || [];
        for (var j = 0; j < added.length; j++) {
          var n = added[j];
          if (n.nodeType === 1 && n.querySelector &&
              (n.matches && n.matches('[data-testid="stPopoverBody"]')
               || n.querySelector('[data-testid="stPopoverBody"]'))) {
            setTimeout(scrollActive, 50);
          }
        }
      }
    });
    obs.observe(pdoc.body, { childList: true, subtree: true });
    pwin.__txStepbarObserver = obs;
  } catch (e) {}
})();
</script>
""",
                height=0,
            )

        # Diszkrét progress sáv a zárt trigger alatt (ugyanaz a % számítás).
        st.markdown(
            (
                '<div class="tx-stepbar-track" role="presentation" aria-hidden="true">'
                '<div class="tx-wf-progress">'
                f'<div class="tx-wf-progress-fill" style="width:{pct}%"></div>'
                "</div></div>"
            ),
            unsafe_allow_html=True,
        )

    return str(st.session_state.get(key) or opts[0])


def render_progress_summary(
    options: Sequence[str],
    *,
    completed: Iterable[str] | None = None,
    status_map: Mapping[str, str] | None = None,
    outline_ready: bool | None = None,
) -> None:
    """Kompatibilitási no-op — a progress sáv a zárt lépéssáv alatt van.

    A státusz / százalék számítás a ``render_step_selector``-ban történik;
    ez a függvény szándékosan nem rajzol második sávot.
    """
    _ = (options, completed, status_map, outline_ready)
    return None


def render_workshop_workflow_nav(
    options: Sequence[str],
    *,
    key: str,
    completed: Iterable[str] | None = None,
    status_map: Mapping[str, str] | None = None,
    key_prefix: str | None = None,
    outline_ready: bool | None = None,
) -> str:
    """Közös munkafolyamat-navigáció: központi lépésválasztó (státusz + progress)."""
    return render_step_selector(
        options,
        key=key,
        completed=completed,
        status_map=status_map,
        key_prefix=key_prefix,
        outline_ready=outline_ready,
    )


# Backward-compatible aliasok
render_section_stepper = render_workshop_stepper


def render_primary_view_switcher(
    options: Sequence[str] | None = None,
    *,
    labels: Mapping[str, str] | None = None,
    icons: Mapping[str, str] | None = None,
    subtitles: Mapping[str, str] | None = None,
    key: str = "ui_mode",
) -> str:
    """Háromelemű module switcher — egyenlő szélességű szegmensek.

    A nézetváltási state és logika változatlan: a `key` (alapból `ui_mode`)
    értéke marad a nézet forrása. A gombok `secondary` típusúak (a Streamlit
    primary kék kitöltését CSS/kulcs alapján kerüljük el).
    """
    opts = [str(o) for o in (options or ("workshop", "sermon_workshop"))]
    label_map = dict(_DEFAULT_UI_MODE_LABELS)
    if labels:
        label_map.update({str(k): str(v) for k, v in labels.items()})
    icon_map = dict(_DEFAULT_UI_MODE_ICONS)
    if icons:
        icon_map.update({str(k): str(v) for k, v in icons.items()})
    # Subtitles are intentionally unused — segments are label-only.
    _ = subtitles

    if st.session_state.get(key) not in opts:
        st.session_state[key] = opts[0]
    current = str(st.session_state.get(key) or opts[0])

    # Aktív szegmens: kulcs-alapú CSS a workspace_switcher konténeren belül.
    active_cls = f"st-key-tx_mainnav_{current}"
    scope = ".st-key-workspace_switcher"
    with st.container(key="workspace_switcher"):
        st.markdown(
            "<style>"
            f"{scope}{{max-width:920px!important;margin-left:auto!important;"
            "margin-right:auto!important;width:100%!important;}"
            f"{scope} [data-testid='stHorizontalBlock']{{"
            "display:grid!important;"
            f"grid-template-columns:repeat({len(opts)},minmax(0,1fr))!important;"
            "align-items:stretch!important;"
            "background:linear-gradient(180deg,rgba(255,253,248,0.96),rgba(244,235,220,0.9))!important;"
            "border:1px solid rgba(170,145,112,0.34)!important;"
            "border-radius:16px!important;"
            "box-shadow:0 1px 0 rgba(255,255,255,0.88) inset,0 8px 18px rgba(58,40,22,0.08)!important;"
            "padding:5px!important;gap:4px!important;"
            "width:100%!important;}"
            f"{scope} [data-testid='stColumn']{{"
            "flex:1 1 0!important;min-width:0!important;width:100%!important;"
            "max-width:100%!important;}}"
            f"{scope} .stButton{{width:100%!important;}}"
            f"{scope} .stButton button{{"
            "width:100%!important;"
            "min-height:52px!important;"
            "background:transparent!important;"
            "border:1px solid transparent!important;"
            "border-radius:12px!important;"
            "box-shadow:none!important;"
            "transition:background 160ms ease,border-color 160ms ease,"
            "box-shadow 160ms ease,color 160ms ease,transform 160ms ease!important;"
            "}"
            f"{scope} .stButton button [data-testid='stMarkdownContainer'] p{{"
            "font-size:1rem!important;font-weight:600!important;"
            "}"
            f"{scope} .stButton button [data-testid='stIconMaterial']{{"
            "width:20px!important;height:20px!important;font-size:19px!important;"
            "}"
            f"{scope} .stButton button:hover{{"
            "background:linear-gradient(180deg,rgba(255,254,250,0.9),rgba(232,238,247,0.72))!important;"
            "border-color:rgba(90,122,168,0.28)!important;"
            "transform:translateY(-1px)!important;"
            "box-shadow:0 4px 10px rgba(52,72,98,0.1)!important;"
            "}"
            f"{scope} .{active_cls} .stButton button,"
            f"{scope} .{active_cls} button{{"
            "background:linear-gradient(180deg,#6d8bb6,#4d6f9a)!important;"
            "border:1px solid #35557c!important;"
            "box-shadow:0 1px 0 rgba(255,255,255,0.28) inset,0 4px 12px rgba(31,51,77,0.28)!important;"
            "color:#fff!important;"
            "transform:translateY(-1px)!important;"
            "}"
            f"{scope} .{active_cls} .stButton button:hover{{"
            "background:linear-gradient(180deg,#7a98c0,#5a7aa8)!important;"
            "}"
            f"{scope} .{active_cls} .stButton button p,"
            f"{scope} .{active_cls} button p{{"
            "color:#fff!important;font-weight:700!important;"
            "}"
            f"{scope} .{active_cls} .stButton button [data-testid='stIconMaterial'],"
            f"{scope} .{active_cls} button [data-testid='stIconMaterial']{{"
            "color:#fff!important;"
            "}"
            f"{scope} .{active_cls} .stButton button::after,"
            f"{scope} .{active_cls} button::after{{height:2px!important;}}"
            "@media (max-width:768px){"
            f"{scope}{{max-width:100%!important;}}"
            f"{scope} .stButton button{{min-height:46px!important;}}"
            f"{scope} .stButton button [data-testid='stMarkdownContainer'] p{{"
            "font-size:0.86rem!important;}"
            "}"
            "</style>",
            unsafe_allow_html=True,
        )
        cols = st.columns(len(opts), gap="small")
        for col, mode in zip(cols, opts):
            is_active = mode == current
            title = label_map.get(mode, mode)
            with col:
                clicked = st.button(
                    title,
                    key=f"tx_mainnav_{mode}",
                    type="secondary",
                    width="stretch",
                )
            if clicked and not is_active:
                st.session_state[key] = mode
                st.rerun()

    return str(st.session_state.get(key) or opts[0])


def render_workspace_switcher(
    options: Sequence[str] | None = None,
    *,
    labels: Mapping[str, str] | None = None,
    icons: Mapping[str, str] | None = None,
    subtitles: Mapping[str, str] | None = None,
    key: str = "ui_mode",
) -> str:
    """Egységes munkaterület-váltó — alias a primary view switcherre."""
    return render_primary_view_switcher(
        options,
        labels=labels,
        icons=icons,
        subtitles=subtitles,
        key=key,
    )


# Gyorseszközök kártyarács — egyetlen közös render; vendég/login azonos.
# A `.st-key-quick_tools_grid` CSS a ui_theme.premium_overlay_css-ben van (startup).
QUICK_TOOLS_TAB_LABELS: tuple[str, ...] = (
    ":material/menu_book: Igehely",
    ":material/translate: Eredeti szöveg tanulmányozása",
    ":material/library_books: Kommentárok",
    ":material/psychology: Exegézis",
    ":material/history_edu: Kortörténet",
    ":material/account_balance: Teológia",
    ":material/image: Illusztrációk",
    ":material/lightbulb: Aktualizálás",
    ":material/music_note: Énekajánló",
    ":material/calendar_month: Igehirdetési sorozat tervező",
    ":material/target: A textus fő gondolata",
    ":material/help: Útmutatás",
)

QUICK_TOOLS_GRID_KEY = "quick_tools_grid"
QUICK_TOOLS_ACTIVE_TAB_KEY = "quick_tools_active_tab"


def render_quick_tools_tabs(
    labels: Sequence[str] | None = None,
) -> Sequence[Any]:
    """Gyorseszközök 4×3 kártyarács — auth-független, egyetlen render út.

    Mindig kulcsolt konténerben épül (`quick_tools_grid`), hogy a premium
    rács-CSS vendég/Cloud módban is érvényesüljön JS/`parent.document` nélkül.
    Nem fogad login/guest paramétert: a megjelenés minden sessionben azonos.

    Az `st.tabs()` kulcsolt (`key=QUICK_TOOLS_ACTIVE_TAB_KEY`) — enélkül a
    kiválasztott fül csak a böngésző oldali, nem-perzisztens állapot volt,
    és egy generálás gomb utáni `st.rerun()` (pl. Vázlat/Eredeti szöveg
    generálása) visszaugrasztotta a nézetet az első fülre (Igehely), holott
    a generálás maga rendben lefutott — csak a UI ugrott vissza, nem a
    munkamenet szakadt meg.
    """
    tab_labels = [str(x) for x in (labels or QUICK_TOOLS_TAB_LABELS) if str(x).strip()]
    if not tab_labels:
        tab_labels = list(QUICK_TOOLS_TAB_LABELS)
    with st.container(key=QUICK_TOOLS_GRID_KEY):
        # `on_change="rerun"`: a szerver tudja, melyik fül nyitott (`.open`), így az
        # inaktív, nehéz fülek törzse nem fut le minden teljes rerunnál (2026-09
        # memória-hotfix: a Cloud 3 GB-os korlátja). Fülváltás = egy olcsó rerun,
        # amely csak az aktív fül törzsét futtatja.
        return st.tabs(tab_labels, key=QUICK_TOOLS_ACTIVE_TAB_KEY, on_change="rerun")


def render_project_toolbar_anchor() -> None:
    """Kompatibilitási no-op — a toolbar `st.container(key=…)`-t használ."""
    return None


def _render_account_controls(
    *,
    is_logged_in: bool,
    auth_configured: bool,
    user_label: str,
) -> str | None:
    """Fiók / vendég vezérlők a toolbar jobb szélére. Visszatér: login|logout|None."""
    action: str | None = None
    if is_logged_in:
        label = (user_label or "Fiók").strip() or "Fiók"
        short = label if len(label) <= 28 else (label[:25] + "…")
        with st.popover(
            short,
            icon=":material/account_circle:",
            help="Fiók",
            use_container_width=False,
            key="tx_appbar_account_popover",
        ):
            st.caption(label)
            if st.button(
                "Kijelentkezés",
                key="tx_appbar_logout",
                icon=":material/logout:",
                type="secondary",
                use_container_width=True,
            ):
                action = "logout"
    elif auth_configured:
        st.markdown(
            '<div class="tx-appbar-guest-label">Vendég mód</div>',
            unsafe_allow_html=True,
        )
        with st.popover(
            "Bejelentkezés",
            icon=":material/login:",
            help="Opcionális Google-bejelentkezés",
            use_container_width=False,
            key="tx_appbar_login_popover",
        ):
            st.caption(
                "A bejelentkezés opcionális. Vendégként is teljes mértékben "
                "használhatod a TEXTUS-t; a Google-fiók a felhőmentéshez kell."
            )
            if st.button(
                "Bejelentkezés Google-fiókkal",
                key="tx_appbar_login",
                icon=":material/login:",
                type="primary",
                use_container_width=True,
            ):
                action = "login"
    else:
        st.markdown(
            '<div class="tx-appbar-guest-label">Vendég mód</div>',
            unsafe_allow_html=True,
        )
    return action


def render_app_toolbar(
    *,
    is_logged_in: bool = False,
    auth_configured: bool = False,
    user_label: str = "",
    home_active: bool = False,
    has_active_project: bool = False,
    project_label: str = "",
    status_label: str = "Ideiglenes",
    status_kind: str = "temp",
    editing_title: bool = False,
    projects_renderer: Callable[[], None] | None = None,
) -> str | None:
    """Egyetlen felső app-sáv (egy sor desktopon).

    Bal: Főoldal | projekt + státusz + szerkesztés
    Jobb: Mentés | ··· | Projektek | Új munka | Beállítások | fiók
    (<760 px: Új munka + Beállítások a Továbbiak menüben)

    Visszatér: home | login | logout | settings | save | save_as_new |
    new_work | edit_title | done_edit | None
    """
    action: str | None = None
    label = (project_label or "").strip() or "Névtelen projekt"
    status = (status_label or "").strip() or "Ideiglenes"
    kind = (
        status_kind
        if status_kind in {"temp", "saved", "dirty", "save_failed", "conflict"}
        else "temp"
    )
    kind_cls = {
        "temp": "is-temp",
        "saved": "is-saved",
        "dirty": "is-dirty",
        "save_failed": "is-save-failed",
        "conflict": "is-conflict",
    }.get(kind, "is-temp")

    def _projects_picker() -> None:
        """Projektek: gomb + st.dialog (a popover megnyitás után szellemként ragadt)."""

        @st.dialog("Mentett projektek", width="large")
        def _projects_dialog() -> None:
            with st.container(key="project_picker_content"):
                if projects_renderer is not None:
                    projects_renderer()
                else:
                    st.markdown(
                        '<div class="tx-projects-empty">'
                        "Nincs megjeleníthető projekt.</div>",
                        unsafe_allow_html=True,
                    )

        open_clicked = st.button(
            "Projektek",
            icon=":material/folder:",
            help="Mentett projektek megnyitása",
            use_container_width=False,
            key="bar_projects_open",
        )
        # Törlés megerősítése a dialógusban maradjon; megnyitás után ne nyíljon újra.
        keep_open = bool(st.session_state.get("project_delete_confirm_id"))
        if open_clicked or keep_open:
            _projects_dialog()

    def _save_controls() -> None:
        nonlocal action
        if has_active_project:
            if st.button(
                "Mentés",
                key="bar_project_save",
                type="primary",
                icon=":material/save:",
                use_container_width=False,
            ):
                action = "save"
            with st.popover(
                "···",
                help="További mentési lehetőségek",
                use_container_width=False,
                key="bar_save_more_popover",
            ):
                if st.button(
                    "Mentés másolatként",
                    key="bar_project_save_as_new",
                    type="secondary",
                    icon=":material/save_as:",
                    use_container_width=True,
                ):
                    action = "save_as_new"
        else:
            if st.button(
                "Mentés újként",
                key="bar_project_save_as_new",
                type="primary",
                icon=":material/save_as:",
                use_container_width=False,
            ):
                action = "save_as_new"

    with st.container(
        key="textus_app_toolbar",
        horizontal=True,
        vertical_alignment="center",
        gap="small",
    ):
        # Bal: kezdőlap + projekt azonosítók
        with st.container(
            key="tx_toolbar_main",
            horizontal=True,
            vertical_alignment="center",
            gap="small",
            width="content",
        ):
            home_help = (
                "Aktuális nézet: Főoldal"
                if home_active
                else "Vissza a főoldalra"
            )
            if st.button(
                "Vissza a főoldalra",
                key="tx_appbar_home",
                icon=":material/home:",
                type="secondary",
                use_container_width=False,
                help=home_help,
            ):
                action = "home"

            st.markdown(
                '<div class="tx-toolbar-divider" aria-hidden="true"></div>',
                unsafe_allow_html=True,
            )

            if editing_title:
                with st.form("bar_project_title_form", border=False, clear_on_submit=False):
                    st.text_input(
                        "Projekt címe",
                        key="project_title_input",
                        label_visibility="collapsed",
                        placeholder="Pl. Jn 3,16 — húsvéti igehirdetés",
                    )
                    if st.form_submit_button(
                        "Kész",
                        type="secondary",
                        use_container_width=False,
                    ):
                        action = "done_edit"
            else:
                safe_label = escape(label)
                st.markdown(
                    (
                        f'<div class="tx-project-name-row" title="{safe_label}">'
                        f'<span class="tx-project-name-text">{safe_label}</span>'
                        f'<span class="tx-project-status-chip {kind_cls}" '
                        f'title="{escape(status)}">{escape(status)}</span></div>'
                    ),
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Projekt nevének szerkesztése",
                    key="bar_title_edit",
                    icon=":material/edit:",
                    type="secondary",
                    use_container_width=False,
                    help="Projekt nevének szerkesztése",
                ):
                    action = "edit_title"

        st.container(key="tx_toolbar_flex", width="stretch")

        with st.container(
            key="tx_toolbar_center",
            horizontal=True,
            vertical_alignment="center",
            gap="small",
            width="content",
        ):
            _save_controls()
            _projects_picker()
            if st.button(
                "Új munka",
                key="bar_new_work",
                type="secondary",
                icon=":material/add:",
                width="content",
            ):
                action = "new_work"

        st.container(key="tx_toolbar_flex_end", width="stretch")

        # Jobb: beállítások / fiók
        with st.container(
            key="tx_toolbar_actions",
            horizontal=True,
            vertical_alignment="center",
            gap="small",
            width="content",
        ):
            if st.button(
                "Beállítások",
                key="tx_appbar_settings",
                icon=":material/settings:",
                type="secondary",
                width="content",
                help="Beállítások",
            ):
                action = "settings"

            # <760 px: másodlagos gombok a Továbbiak menüben (CSS váltja)
            with st.popover(
                "Továbbiak",
                icon=":material/more_horiz:",
                help="Továbbiak",
                use_container_width=False,
                key="bar_overflow_more",
            ):
                if st.button(
                    "Új munka",
                    key="bar_overflow_new_work",
                    type="secondary",
                    icon=":material/add:",
                    use_container_width=True,
                ):
                    action = "new_work"
                if st.button(
                    "Beállítások",
                    key="bar_overflow_settings",
                    type="secondary",
                    icon=":material/settings:",
                    use_container_width=True,
                ):
                    action = "settings"
                if has_active_project:
                    if st.button(
                        "Mentés másolatként",
                        key="bar_overflow_save_as_new",
                        type="secondary",
                        icon=":material/save_as:",
                        use_container_width=True,
                    ):
                        action = "save_as_new"

            account_action = _render_account_controls(
                is_logged_in=is_logged_in,
                auth_configured=auth_configured,
                user_label=user_label,
            )
            if account_action and action is None:
                action = account_action

    return action


def render_global_appbar(
    *,
    is_logged_in: bool,
    auth_configured: bool,
    user_label: str = "",
    home_active: bool = False,
) -> str | None:
    """Kompatibilitási no-op — használd a `render_app_toolbar`-t (egy sáv)."""
    _ = (is_logged_in, auth_configured, user_label, home_active)
    return None


def render_project_toolbar(
    *,
    has_active_project: bool,
    project_label: str = "",
    status_label: str = "Ideiglenes",
    status_kind: str = "temp",
    editing_title: bool = False,
    projects_renderer: Callable[[], None] | None = None,
    is_logged_in: bool = False,
    auth_configured: bool = False,
    user_label: str = "",
    home_active: bool = False,
) -> str | None:
    """Kompatibilitási alias a unified app toolbarra."""
    return render_app_toolbar(
        is_logged_in=is_logged_in,
        auth_configured=auth_configured,
        user_label=user_label,
        home_active=home_active,
        has_active_project=has_active_project,
        project_label=project_label,
        status_label=status_label,
        status_kind=status_kind,
        editing_title=editing_title,
        projects_renderer=projects_renderer,
    )


def render_info_panel(title: str, body: str = "") -> None:
    """Cím + törzs hierarchia info-panelekhez (sentence case)."""
    t = escape((title or "").strip())
    b = escape((body or "").strip())
    if not t and not b:
        return
    title_html = f'<div class="ws-info-title">{t}</div>' if t else ""
    body_html = f'<div class="ws-info-body">{b}</div>' if b else ""
    st.markdown(
        f'<div class="ws-info-panel">{title_html}{body_html}</div>',
        unsafe_allow_html=True,
    )


def textus_completed_sections(state: Any) -> set[str]:
    """Textusműhely: tartalom alapján késznek jelölt szakaszok."""
    get = state.get if hasattr(state, "get") else (lambda *_: None)
    done: set[str] = set()
    if str(get("last_igehely") or get("igehely_input") or "").strip() or str(
        get("passage_text") or ""
    ).strip():
        done.add("Igehely, alkalom és szövegkörnyezet")
    if str(get("original_text") or "").strip():
        done.add("Eredeti szöveg és kulcsszavak")
    if str(get("exegesis") or "").strip():
        done.add("Exegézis, műfaj és szerkezet")
    if str(get("history") or "").strip():
        done.add("Kortörténeti háttér")
    if str(get("theology") or "").strip():
        done.add("Teológiai hangsúlyok")
    tw = get("text_workshop") if isinstance(get("text_workshop"), dict) else {}
    if not isinstance(tw, dict):
        tw = {}
    if str(tw.get("text_main_idea") or "").strip() or str(
        tw.get("text_main_idea_status") or ""
    ).strip() in ("draft", "approved"):
        done.add("A textus fő gondolata")
    insights = tw.get("approved_insights")
    if isinstance(insights, list) and any(
        isinstance(x, dict) and str(x.get("content") or "").strip() for x in insights
    ):
        done.add("Mit viszünk tovább?")
    return done


def _suggestion_payload_nonempty(raw: Any) -> bool:
    if raw is None:
        return False
    if isinstance(raw, list):
        return any(
            (isinstance(x, dict) and any(str(v).strip() for v in x.values() if not isinstance(v, (list, dict))))
            or (isinstance(x, str) and x.strip())
            for x in raw
        )
    if isinstance(raw, dict):
        # Tipikus MI-javaslat csomag: van legalább egy nem üres mező / lista
        for v in raw.values():
            if isinstance(v, str) and v.strip():
                return True
            if isinstance(v, list) and v:
                return True
            if isinstance(v, dict) and any(str(x).strip() for x in v.values()):
                return True
        return False
    return bool(str(raw).strip())


def sermon_section_statuses(
    state: Any,
    *,
    status_of: Callable[[str], str] | None = None,
) -> dict[str, str]:
    """Igehirdetési műhely szakaszállapotai (opcionális hangnem).

    Értékek: ``ai_ready`` | ``ai_suggested`` | ``own_emphasis`` | ``approved``.
    """
    get = state.get if hasattr(state, "get") else (lambda *_: None)
    sw = get("sermon_workshop") if isinstance(get("sermon_workshop"), dict) else {}
    if not isinstance(sw, dict):
        sw = {}

    def _status(key: str) -> str:
        if status_of is not None:
            return str(status_of(key) or "").strip()
        return str(sw.get(key) or "").strip()

    def _has_decision(source_section: str) -> bool:
        for item in sw.get("approved_sermon_decisions") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("source_section") or "").strip() != source_section:
                continue
            if item.get("approved") is False:
                continue
            if str(item.get("content") or "").strip():
                return True
        return False

    def _has_text(*keys: str) -> bool:
        for k in keys:
            val = sw.get(k)
            if isinstance(val, str) and val.strip():
                return True
            if isinstance(val, dict) and any(
                str(v).strip() for v in val.values() if not isinstance(v, (list, dict))
            ):
                return True
            if isinstance(val, list) and val:
                return True
        return False

    def _classify(
        *,
        approved: bool,
        own: bool,
        suggested: bool,
    ) -> str:
        if approved:
            return "approved"
        if own:
            return "own_emphasis"
        if suggested:
            return "ai_suggested"
        return "ai_ready"

    out: dict[str, str] = {}
    out["Az igehirdetés fő gondolata"] = _classify(
        approved=_status("sermon_main_idea_status") == "approved"
        or _has_decision("Az igehirdetés fő gondolata"),
        own=_has_text("sermon_main_idea"),
        suggested=_suggestion_payload_nonempty(sw.get("sermon_main_idea_suggestions")),
    )
    out["Emberi helyzet és kegyelmi válasz"] = _classify(
        approved=_status("human_condition_status") == "approved"
        or _has_decision("Emberi helyzet és kegyelmi válasz"),
        own=_has_text("human_condition"),
        suggested=_suggestion_payload_nonempty(sw.get("human_condition_suggestion"))
        or _suggestion_payload_nonempty(sw.get("human_condition_suggestions")),
    )
    out["Hallgatói kérdés és feszültség"] = _classify(
        approved=_status("listener_tension_status") == "approved"
        or _has_decision("Hallgatói kérdés és feszültség"),
        own=_has_text("listener_tension"),
        suggested=_suggestion_payload_nonempty(sw.get("listener_tension_suggestions")),
    )
    # A "Homiletikai belépési pont" fázis tényleges UI-tartalma a Korrekciós
    # fázis 2A/2D óta az `entry_point` blokk — a legacy human_condition/
    # listener_tension szakaszstátuszok fentebb régi projektek miatt
    # maradnak meg, de önmagukban NEM tükrözik az entry_point jóváhagyását.
    # E nélkül a bejegyzés nélkül a progresszsáv soha nem mutatott
    # "Jóváhagyva"-t egy kizárólag entry_point-tal kitöltött projektnél.
    out["Homiletikai belépési pont"] = _classify(
        approved=_status("entry_point_status") == "approved"
        or _has_decision("Homiletikai belépési pont"),
        own=_has_text("entry_point"),
        suggested=_suggestion_payload_nonempty(sw.get("entry_point_suggestions")),
    )
    out["Krisztus-központú és evangéliumi ív"] = _classify(
        approved=_status("christ_centered_arc_status") == "approved"
        or _has_decision("Krisztus-központú és evangéliumi ív"),
        own=_has_text("christ_centered_arc"),
        suggested=_suggestion_payload_nonempty(sw.get("gospel_arc_suggestions")),
    )
    out["Az igehirdetés útja és mozgásai"] = _classify(
        approved=_status("sermon_path_status") == "approved"
        or _has_decision("Az igehirdetés útja és mozgásai"),
        own=_has_text("sermon_path", "sermon_movements"),
        suggested=_suggestion_payload_nonempty(sw.get("sermon_path_suggestions")),
    )
    out["Illusztrációk és aktualizálás"] = _classify(
        approved=_status("enrichment_status") == "approved",
        own=_has_text(
            "selected_images",
            "illustrations",
            "applications",
            "retained_illustration_cards",
            "actualization_connections",
        ),
        suggested=_suggestion_payload_nonempty(sw.get("sermon_enrichment_suggestions"))
        or _suggestion_payload_nonempty(sw.get("illustration_suggestions"))
        or _suggestion_payload_nonempty(sw.get("actualization_suggestions")),
    )
    out["Képek, illusztrációk és alkalmazás"] = out["Illusztrációk és aktualizálás"]

    engagement_items = sw.get("engagement_elements")
    engagement_items = engagement_items if isinstance(engagement_items, list) else []
    engagement_approved = any(
        isinstance(e, dict) and (e.get("status") or "") == "approved"
        for e in engagement_items
    )
    engagement_own = any(
        isinstance(e, dict) and (e.get("text") or "").strip() for e in engagement_items
    )
    out["Megszólítás és bevonás"] = _classify(
        approved=engagement_approved,
        own=engagement_own,
        suggested=_suggestion_payload_nonempty(sw.get("engagement_suggestions")),
    )

    out["Lezárás és megérkezés"] = _classify(
        approved=_status("closing_status") == "approved",
        own=_has_text("closing"),
        suggested=_suggestion_payload_nonempty(sw.get("closing_suggestions")),
    )
    out["Lekciójavaslat"] = _classify(
        approved=_status("lection_status") == "approved",
        own=isinstance(sw.get("lection"), dict)
        and bool(str(sw["lection"].get("reference") or "").strip()),
        suggested=_suggestion_payload_nonempty(sw.get("lection_suggestions")),
    )
    prep = sw.get("prayer_preparation") if isinstance(sw.get("prayer_preparation"), dict) else {}
    prayer_own = False
    if isinstance(prep, dict):
        for side_key in ("before", "after"):
            side = prep.get(side_key) if isinstance(prep.get(side_key), dict) else {}
            if any(
                str(side.get(f) or "").strip()
                for f in (
                    "own_thoughts",
                    "selected_opening",
                    "closing_direction",
                    "purpose",
                    "movement_notes",
                )
            ):
                prayer_own = True
            lines = side.get("selected_lines")
            if isinstance(lines, list) and any(str(x).strip() for x in lines):
                prayer_own = True
    out["Imádsági előkészítés"] = _classify(
        approved=str(prep.get("status") or "").strip().casefold() == "approved"
        or _status("prayer_status") == "approved",
        own=prayer_own,
        suggested=_suggestion_payload_nonempty(prep.get("before_suggestions"))
        or _suggestion_payload_nonempty(prep.get("after_suggestions")),
    )

    try:
        from sermon_workshop_outline_ai import outline_has_content
    except Exception:  # pragma: no cover
        outline_has_content = None  # type: ignore[assignment]

    has_outline = bool(
        outline_has_content is not None and outline_has_content(sw.get("sermon_outline"))
    )
    outline = sw.get("sermon_outline") if isinstance(sw.get("sermon_outline"), dict) else {}
    outline_approved = (
        _status("sermon_outline_status") == "approved"
        or str(outline.get("status") or "").strip() == "approved"
    ) and has_outline
    if outline_approved:
        out["Igehirdetési vázlat"] = "approved"
    elif has_outline and bool(outline.get("manually_edited")):
        out["Igehirdetési vázlat"] = "own_emphasis"
    elif has_outline:
        out["Igehirdetési vázlat"] = "ai_suggested"
    else:
        out["Igehirdetési vázlat"] = "ai_ready"

    diag_raw = sw.get("diagnostics")
    diag = diag_raw if isinstance(diag_raw, dict) else {}
    result_raw = diag.get("result")
    result = result_raw if isinstance(result_raw, dict) else {}
    outline_diag = (
        sw.get("sermon_outline_diagnostics")
        if isinstance(sw.get("sermon_outline_diagnostics"), dict)
        else {}
    )
    has_diag = bool(
        str(result.get("overview") or "").strip()
        or result.get("diagnostic_areas")
        or (isinstance(diag.get("priorities"), list) and diag.get("priorities"))
        or str(outline_diag.get("overview") or "").strip()
        or outline_diag.get("strengths")
        or outline_diag.get("refinements")
    )
    out["Homiletikai diagnosztika"] = _classify(
        approved=False,
        own=has_diag,
        suggested=False,
    )
    return out


def sermon_completed_sections(
    state: Any,
    *,
    status_of: Callable[[str], str] | None = None,
) -> set[str]:
    """Igehirdetési műhely: saját hangsúly / jóváhagyott / AI-összeállított szakaszok.

    A ``ai_ready`` szakaszok szándékosan nincsenek benne — azok opcionálisak,
    és a vázlat nélkülük is elkészülhet.
    """
    statuses = sermon_section_statuses(state, status_of=status_of)
    return {
        name
        for name, stt in statuses.items()
        if stt in ("approved", "own_emphasis", "ai_suggested", "done")
    }


# ---------------------------------------------------------------------------
# Igehirdetési műhely — 5 fázisra összesített nézet (két-műhely refaktor).
#
# A mögöttes 11/12 régi szakasznév és session_state mező NEM változik —
# `sermon_section_statuses` marad az igazi forrás. Ez a réteg csak
# összesíti a régi szakaszállapotokat az öt új fázisnévre, hogy a
# leegyszerűsített navigáció ugyanazt a státuszinformációt tudja mutatni.
# ---------------------------------------------------------------------------

SERMON_PHASE_OPTIONS: tuple[str, ...] = (
    "Textusmag és fókuszmondat",
    "Homiletikai belépési pont",
    "A prédikáció íve",
    "Megszólítás és bevonás",
    "Igehirdetési vázlat",
)

_SERMON_PHASE_SECTION_MAP: dict[str, tuple[str, ...]] = {
    "Textusmag és fókuszmondat": ("Az igehirdetés fő gondolata",),
    "Homiletikai belépési pont": (
        "Homiletikai belépési pont",
        "Emberi helyzet és kegyelmi válasz",
        "Hallgatói kérdés és feszültség",
    ),
    "A prédikáció íve": (
        "Krisztus-központú és evangéliumi ív",
        "Az igehirdetés útja és mozgásai",
        "Lezárás és megérkezés",
    ),
    "Megszólítás és bevonás": ("Megszólítás és bevonás",),
    "Igehirdetési vázlat": ("Igehirdetési vázlat",),
}

_SERMON_STATUS_RANK: dict[str, int] = {
    "ai_ready": 0,
    "ai_suggested": 1,
    "own_emphasis": 2,
    "approved": 3,
}


def sermon_phase_statuses(
    state: Any,
    *,
    status_of: Callable[[str], str] | None = None,
) -> dict[str, str]:
    """Az öt igehirdetési-műhely fázis állapota.

    A régi (11 szakaszos) ``sermon_section_statuses`` eredményét összesíti
    fázisonként: egy fázis állapota a benne összevont szakaszok legmagasabb
    rangú állapota (approved > own_emphasis > ai_suggested > ai_ready).
    """
    section_statuses = sermon_section_statuses(state, status_of=status_of)
    out: dict[str, str] = {}
    for phase, sections in _SERMON_PHASE_SECTION_MAP.items():
        best = "ai_ready"
        for section in sections:
            stt = section_statuses.get(section, "ai_ready")
            if _SERMON_STATUS_RANK.get(stt, 0) > _SERMON_STATUS_RANK.get(best, 0):
                best = stt
        out[phase] = best
    return out


def sermon_phase_completed(
    state: Any,
    *,
    status_of: Callable[[str], str] | None = None,
) -> set[str]:
    """Igehirdetési műhely: az öt fázis közül melyik számít késznek."""
    statuses = sermon_phase_statuses(state, status_of=status_of)
    return {
        name
        for name, stt in statuses.items()
        if stt in ("approved", "own_emphasis", "ai_suggested")
    }


__all__ = [
    "completed_step_indices",
    "render_workshop_stepper",
    "render_section_stepper",
    "render_primary_view_switcher",
    "render_workspace_switcher",
    "render_quick_tools_tabs",
    "QUICK_TOOLS_TAB_LABELS",
    "QUICK_TOOLS_GRID_KEY",
    "render_app_toolbar",
    "render_global_appbar",
    "render_project_toolbar_anchor",
    "render_project_toolbar",
    "render_info_panel",
    "textus_completed_sections",
    "sermon_completed_sections",
    "sermon_section_statuses",
    "SERMON_PHASE_OPTIONS",
    "sermon_phase_statuses",
    "sermon_phase_completed",
]
