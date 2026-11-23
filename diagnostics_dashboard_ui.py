"""Homiletikai diagnosztikai munkatérkép — függőségmentes SVG-vizualizáció.

Elvek:
- Nincs pontszám, százalék, rangsor vagy osztályzat.
- Csak a meglévő diagnosztikai státuszokból származó minőségi állapotok.
- Hiányzó adat soha nem jelenik meg „nullaként” vagy gyenge értékelésként.
- Könnyű, reszponzív SVG + scoped CSS — nincs külső chart-könyvtár.
"""

from __future__ import annotations

import html
import math
from typing import Any, Sequence

import streamlit as st

_DASH_STYLE_FLAG = "_tx_diag_dash_styles"

# Minőségi állapotok — színek (visszafogott Textus-paletta).
_STATE_COLORS: dict[str, str] = {
    "emerged": "#5a7aa8",  # Kirajzolódik — muted Textus blue
    "forming": "#c4a06a",  # Alakul — warm beige/gold
    "attention": "#b87a52",  # Figyelmet kér — restrained terracotta
    "unknown": "#d4cfc7",  # Még nincs elég adat — light gray
}

_STATE_LABELS: dict[str, str] = {
    "emerged": "Kirajzolódik",
    "forming": "Alakul",
    "attention": "Figyelmet kér",
    "unknown": "Még nincs elég adat",
}

_C_INK = "#1f334d"
_C_MUTED = "#6b5a48"
_C_TRACK = "rgba(160,140,115,0.18)"
_C_CENTER_BG = "#fffdf9"


def ensure_dashboard_styles() -> None:
    """A munkatérkép-specifikus CSS beszúrása — minden futásban.

    2026-11-23: a korábbi, _DASH_STYLE_FLAG-gel védett egyszeri beszúrás után
    a Streamlit a következő futás végén eltávolította a <style> elemet. A flag
    konstans csak a régi sessionök értelmezhetősége miatt maradt meg.
    """
    st.markdown(
        """
<style>
.tx-wmap-wrap {
  display: flex; flex-direction: column; align-items: center;
  width: 100%; min-width: 0;
}
.tx-wmap-svg { width: 100%; max-width: 360px; height: auto; display: block; margin: 0 auto; }
.tx-wmap-svg .tx-wmap-seg {
  transition: opacity 420ms ease, fill 420ms ease;
  cursor: default;
}
.tx-wmap-svg .tx-wmap-seg:hover { opacity: 0.88; }
.tx-wmap-legend {
  display: flex; flex-wrap: wrap; gap: 0.45rem 0.85rem;
  justify-content: center; margin-top: 0.55rem;
  font-family: "Source Sans 3","Segoe UI",sans-serif;
  font-size: 0.72rem; color: #6b5a48;
}
.tx-wmap-legend span { display: inline-flex; align-items: center; gap: 0.28rem; }
.tx-wmap-legend i {
  width: 0.55rem; height: 0.55rem; border-radius: 50%;
  display: inline-block; flex: 0 0 auto;
}
.tx-wmap-layout {
  display: grid;
  grid-template-columns: minmax(220px, 0.95fr) minmax(240px, 1.05fr);
  gap: 1rem 1.25rem;
  align-items: start;
  margin: 0.35rem 0 0.85rem 0;
}
.tx-wmap-summary { display: flex; flex-direction: column; gap: 0.55rem; min-width: 0; }
.tx-wsum-card {
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  background: rgba(255,252,247,0.88);
  border: 1px solid rgba(93,72,48,0.12);
}
.tx-wsum-card h5 {
  margin: 0 0 0.35rem 0;
  font-family: "Source Sans 3","Segoe UI",sans-serif;
  font-size: 0.72rem; font-weight: 650; letter-spacing: 0.04em;
  text-transform: uppercase; color: #8a6a3f;
}
.tx-wsum-card p {
  margin: 0; font-size: 0.88rem; line-height: 1.4; color: #3d3228;
}
.tx-wsum-card .tx-wsum-item {
  display: flex; gap: 0.45rem; align-items: flex-start;
  margin: 0.28rem 0 0 0; font-size: 0.88rem; line-height: 1.4; color: #3d3228;
}
.tx-wsum-card .tx-wsum-item:first-of-type { margin-top: 0; }
.tx-wsum-ico {
  flex: 0 0 auto; width: 0.55rem; height: 0.55rem; margin-top: 0.35rem;
  border-radius: 50%; background: #5a7aa8;
}
.tx-wsum-card.-next {
  background: linear-gradient(165deg, rgba(255,248,235,0.96), rgba(248,236,214,0.7));
  border: 1px solid rgba(196,146,58,0.38);
  border-left: 4px solid #c4923a;
  box-shadow: 0 3px 10px rgba(120,90,40,0.08);
}
.tx-wsum-card.-next h5 { color: #7a5620; }
.tx-wsum-card.-next p { font-weight: 550; color: #2b2116; }
.tx-wsum-card.-tips .tx-wsum-item .tx-wsum-ico { background: #c4a06a; }
.tx-wmap-faint .tx-wmap-seg { opacity: 0.45; }
.tx-diag-head {
  display: flex; flex-wrap: wrap; align-items: flex-start;
  justify-content: space-between; gap: 0.75rem 1rem;
  margin: 0.15rem 0 0.7rem 0;
}
.tx-diag-head-left { min-width: 0; flex: 1 1 200px; }
.tx-diag-head-right {
  display: flex; flex-wrap: wrap; align-items: center;
  gap: 0.45rem 0.65rem; flex: 0 1 auto;
}
.tx-diag-head-title {
  margin: 0; font-family: "Source Serif 4","Georgia",serif;
  font-size: 1.35rem; font-weight: 650; color: #1f334d; line-height: 1.25;
}
.tx-diag-head-sub {
  margin: 0.2rem 0 0 0; font-size: 0.88rem; color: #6b5a48; line-height: 1.35;
}
.tx-diag-status-pill {
  display: inline-flex; align-items: center; gap: 0.3rem;
  padding: 0.18rem 0.55rem; border-radius: 999px;
  font-size: 0.78rem; font-weight: 600; line-height: 1.3;
  border: 1px solid rgba(93,72,48,0.14);
  background: rgba(248,245,238,0.9); color: #5a4a3a;
}
.tx-diag-status-pill.-stale {
  background: rgba(255,246,230,0.95); color: #7a5620;
  border-color: rgba(196,146,58,0.35);
}
.tx-diag-status-pill .dot {
  width: 0.4rem; height: 0.4rem; border-radius: 50%; background: #5a7aa8;
}
.tx-diag-status-pill.-stale .dot { background: #c4923a; }
@media (max-width: 820px) {
  .tx-wmap-layout { grid-template-columns: 1fr; gap: 0.85rem; }
  .tx-wmap-svg { max-width: 300px; }
}
@media (prefers-reduced-motion: reduce) {
  .tx-wmap-svg .tx-wmap-seg { transition: none !important; }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def segment_state_label(state_key: str) -> str:
    return _STATE_LABELS.get(state_key, _STATE_LABELS["unknown"])


def segment_state_color(state_key: str) -> str:
    return _STATE_COLORS.get(state_key, _STATE_COLORS["unknown"])


def _arc_path(
    cx: float,
    cy: float,
    r_outer: float,
    r_inner: float,
    start_ang: float,
    end_ang: float,
) -> str:
    """Donut-szelet SVG path (angles in radians, 0 = east, CCW)."""
    # Slight gap between segments for readability.
    gap = 0.035
    a0 = start_ang + gap / 2
    a1 = end_ang - gap / 2
    if a1 <= a0:
        a1 = a0 + 0.01

    def _p(r: float, a: float) -> tuple[float, float]:
        return cx + r * math.cos(a), cy + r * math.sin(a)

    x0, y0 = _p(r_outer, a0)
    x1, y1 = _p(r_outer, a1)
    x2, y2 = _p(r_inner, a1)
    x3, y3 = _p(r_inner, a0)
    large = 1 if (a1 - a0) > math.pi else 0
    return (
        f"M {x0:.2f},{y0:.2f} "
        f"A {r_outer:.2f},{r_outer:.2f} 0 {large} 1 {x1:.2f},{y1:.2f} "
        f"L {x2:.2f},{y2:.2f} "
        f"A {r_inner:.2f},{r_inner:.2f} 0 {large} 0 {x3:.2f},{y3:.2f} Z"
    )


def build_work_map_svg(
    segments: Sequence[dict[str, Any]],
    *,
    center_title: str = "Aktuális vázlat",
    center_qualifier: str = "",
    faint: bool = False,
    size: int = 320,
) -> str:
    """6 szegmenses gyűrű/hex munkatérkép SVG.

    Minden ``segments`` elem: key, label, state_key, tooltip (opcionális).
    """
    n = max(1, len(segments) or 6)
    cx = cy = size / 2
    r_outer = size / 2 - 36
    r_inner = r_outer * 0.48
    r_label = r_outer + 16

    # Start at top (−90°).
    start0 = -math.pi / 2
    step = 2 * math.pi / n

    parts: list[str] = []
    # Soft outer hex guide (visual “work map” feel, not a score).
    hex_pts = []
    for i in range(6):
        ang = -math.pi / 2 + i * math.pi / 3
        hex_pts.append(
            f"{cx + (r_outer + 6) * math.cos(ang):.1f},"
            f"{cy + (r_outer + 6) * math.sin(ang):.1f}"
        )
    parts.append(
        f'<polygon points="{" ".join(hex_pts)}" fill="none" '
        f'stroke="{_C_TRACK}" stroke-width="1.2" opacity="0.7" />'
    )

    segs = list(segments) if segments else [
        {
            "key": f"empty_{i}",
            "label": "",
            "state_key": "unknown",
            "tooltip": "Még nincs diagnosztikai adat.",
        }
        for i in range(6)
    ]

    for i, seg in enumerate(segs[:n]):
        a0 = start0 + i * step
        a1 = start0 + (i + 1) * step
        state = str(seg.get("state_key") or "unknown")
        color = segment_state_color(state)
        label = str(seg.get("label") or "")
        tip = str(seg.get("tooltip") or "")
        if not tip:
            tip = f"{label}: {segment_state_label(state)}"
        path = _arc_path(cx, cy, r_outer, r_inner, a0, a1)
        parts.append(
            f'<path class="tx-wmap-seg" d="{path}" fill="{color}" '
            f'stroke="#fffdf9" stroke-width="1.5">'
            f"<title>{html.escape(tip)}</title></path>"
        )
        # Label at segment mid-angle.
        mid = (a0 + a1) / 2
        lx = cx + r_label * math.cos(mid)
        ly = cy + r_label * math.sin(mid)
        anchor = "middle"
        if math.cos(mid) > 0.35:
            anchor = "start"
        elif math.cos(mid) < -0.35:
            anchor = "end"
        # Soften long labels into two lines when needed.
        words = label.split()
        if len(words) >= 2 and len(label) > 12:
            mid_w = (len(words) + 1) // 2
            line1 = " ".join(words[:mid_w])
            line2 = " ".join(words[mid_w:])
            parts.append(
                f'<text x="{lx:.1f}" y="{ly - 5:.1f}" text-anchor="{anchor}" '
                f'dominant-baseline="middle" style="font-size:9.5px;fill:{_C_INK};'
                f'font-family:Source Sans 3,Segoe UI,sans-serif;font-weight:600">'
                f"{html.escape(line1)}</text>"
                f'<text x="{lx:.1f}" y="{ly + 7:.1f}" text-anchor="{anchor}" '
                f'dominant-baseline="middle" style="font-size:9.5px;fill:{_C_INK};'
                f'font-family:Source Sans 3,Segoe UI,sans-serif;font-weight:600">'
                f"{html.escape(line2)}</text>"
            )
        elif label:
            parts.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                f'dominant-baseline="middle" style="font-size:9.5px;fill:{_C_INK};'
                f'font-family:Source Sans 3,Segoe UI,sans-serif;font-weight:600">'
                f"{html.escape(label)}</text>"
            )

    # Center disc.
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r_inner - 4:.1f}" '
        f'fill="{_C_CENTER_BG}" stroke="{_C_TRACK}" stroke-width="1.5" />'
    )
    title = html.escape(center_title or "Aktuális vázlat")
    parts.append(
        f'<text x="{cx}" y="{cy - (10 if center_qualifier else 0):.1f}" '
        f'text-anchor="middle" dominant-baseline="middle" '
        f'style="font-size:11px;font-weight:650;fill:{_C_INK};'
        f'font-family:Source Sans 3,Segoe UI,sans-serif">{title}</text>'
    )
    if center_qualifier:
        parts.append(
            f'<text x="{cx}" y="{cy + 12:.1f}" text-anchor="middle" '
            f'dominant-baseline="middle" style="font-size:10px;fill:{_C_MUTED};'
            f'font-family:Source Sans 3,Segoe UI,sans-serif">'
            f"{html.escape(center_qualifier)}</text>"
        )

    aria_bits = [
        f"{s.get('label', '')}: {segment_state_label(str(s.get('state_key') or 'unknown'))}"
        for s in segs[:n]
        if s.get("label")
    ]
    aria = "Homiletikai térkép. " + ("; ".join(aria_bits) if aria_bits else "Nincs adat.")
    if center_qualifier:
        aria += f" Összkép: {center_qualifier}."
    faint_cls = " tx-wmap-faint" if faint else ""
    return (
        f'<svg class="tx-wmap-svg{faint_cls}" width="100%" viewBox="0 0 {size} {size}" '
        f'role="img" preserveAspectRatio="xMidYMid meet" '
        f'aria-label="{html.escape(aria)}">'
        + "".join(parts)
        + "</svg>"
    )


def render_work_map(
    segments: Sequence[dict[str, Any]],
    *,
    center_title: str = "Aktuális vázlat",
    center_qualifier: str = "",
    faint: bool = False,
    show_legend: bool = True,
) -> None:
    """Homiletikai térkép kirajzolása Streamlitbe."""
    ensure_dashboard_styles()
    svg = build_work_map_svg(
        segments,
        center_title=center_title,
        center_qualifier=center_qualifier,
        faint=faint,
    )
    legend = ""
    if show_legend:
        items = "".join(
            f'<span><i style="background:{segment_state_color(k)};"></i>'
            f"{html.escape(segment_state_label(k))}</span>"
            for k in ("emerged", "forming", "attention", "unknown")
        )
        legend = f'<div class="tx-wmap-legend">{items}</div>'
    st.markdown(
        f'<div class="tx-wmap-wrap">{svg}{legend}</div>',
        unsafe_allow_html=True,
    )


def render_summary_card(
    *,
    title: str,
    body_html: str,
    variant: str = "default",
) -> None:
    """Egy kompakt összefoglaló kártya (erősség / következő lépés / tippek)."""
    ensure_dashboard_styles()
    cls = "tx-wsum-card"
    if variant == "next":
        cls += " -next"
    elif variant == "tips":
        cls += " -tips"
    st.markdown(
        f'<div class="{cls}"><h5>{html.escape(title)}</h5>{body_html}</div>',
        unsafe_allow_html=True,
    )


# --- Backward-compatible stubs (tests / older callers) ---------------------

_C_BLUE = "#5a7aa8"
_C_GREEN = "#4a7c74"
_C_AMBER = "#c4923a"
_C_GREY = "#9a938a"


def render_score_ring(
    *,
    score: int | None,
    qualifier: str,
    qualifier_key: str,
    summary: str,
    sufficient: bool,
) -> None:
    """Deprecated: scores removed. Renders a qualitative center note instead."""
    ensure_dashboard_styles()
    # Never show numeric scores — map to a qualitative work-map center.
    if not sufficient or score is None:
        state = "unknown"
        center_q = "Még nincs elég adat"
    else:
        # Legacy callers may still pass a score; convert without displaying it.
        if qualifier_key == "strong" or (isinstance(score, int) and score >= 78):
            state = "emerged"
            center_q = "Kibontakozó ív"
        elif qualifier_key == "good" or (isinstance(score, int) and score >= 60):
            state = "forming"
            center_q = "Kibontakozó ív"
        else:
            state = "attention"
            center_q = "További fókusz szükséges"
    segs = [
        {
            "key": f"legacy_{i}",
            "label": lbl,
            "state_key": state if sufficient else "unknown",
            "tooltip": summary or segment_state_label(state if sufficient else "unknown"),
        }
        for i, lbl in enumerate(
            (
                "Textushűség",
                "Fő gondolat",
                "Igehirdetési ív",
                "Krisztus-központúság",
                "Hallgatói megszólítás",
                "Megérkezés",
            )
        )
    ]
    # Suppress unused warning for score while ensuring it never appears in HTML.
    _ = score
    render_work_map(
        segs,
        center_title="Aktuális vázlat",
        center_qualifier=center_q if sufficient else "Nincs elég adat",
        faint=not sufficient,
    )
    if qualifier and sufficient:
        st.caption(qualifier)
    if summary:
        st.caption(summary)


def render_coverage_ring(
    *,
    evaluated: int,
    total: int,
    missing_labels: Sequence[str],
) -> None:
    """Deprecated coverage ring — qualitative note only (no ratios as grades)."""
    ensure_dashboard_styles()
    if evaluated <= 0:
        note = "Még egy terület sincs kirajzolva."
    elif evaluated < total:
        shown = ", ".join(html.escape(m) for m in list(missing_labels)[:4])
        extra = "" if len(missing_labels) <= 4 else " …"
        note = f"Részleges kép — még alakul: {shown}{extra}" if shown else "Részleges kép."
    else:
        note = "Mind a hat homiletikai területre van visszajelzés."
    st.markdown(
        f'<div class="tx-wmap-wrap"><div class="tx-wmap-legend">{note}</div></div>',
        unsafe_allow_html=True,
    )


def render_profile_diagram(rows: list[dict[str, Any]]) -> None:
    """Deprecated radar — forwards to the 6-segment work map when possible."""
    # Best-effort: take up to 6 labeled rows and map status → state_key.
    status_to_state = {
        "strong": "emerged",
        "stable": "forming",
        "needs_attention": "attention",
        "critical_gap": "attention",
        "not_enough_information": "unknown",
    }
    segs: list[dict[str, Any]] = []
    for row in rows[:6]:
        status = str(row.get("status") or "not_enough_information")
        state = status_to_state.get(status, "unknown")
        if row.get("value") is None and status == "not_enough_information":
            state = "unknown"
        segs.append(
            {
                "key": str(row.get("key") or row.get("label") or ""),
                "label": str(row.get("label") or ""),
                "state_key": state,
                "tooltip": (
                    f"{row.get('label', '')}: "
                    f"{row.get('status_label') or segment_state_label(state)}"
                ),
            }
        )
    while len(segs) < 6:
        segs.append(
            {
                "key": f"pad_{len(segs)}",
                "label": "",
                "state_key": "unknown",
                "tooltip": "Még nincs elég adat",
            }
        )
    evaluated = sum(1 for s in segs if s["state_key"] != "unknown")
    render_work_map(
        segs,
        center_qualifier="Kibontakozó ív" if evaluated else "Még alakuló kép",
        faint=evaluated == 0,
    )
