"""Premium UX 2.0 design tokens és közös felületi stílusok.

Csak vizuális finomhangolás: nem módosít üzleti logikát.
"""

from __future__ import annotations


def premium_tokens_css() -> str:
    """Központi UI-tokenek (színek, térközök, radiusok, árnyékok)."""
    return """
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0&display=swap');

:root {
    /* Textus alap-paletta */
    --tx-bg: #f5eee2;
    --tx-surface: rgba(255, 251, 244, 0.88);
    --tx-surface-strong: rgba(255, 252, 247, 0.94);
    --tx-primary: #5a7aa8;
    --tx-primary-deep: #1f334d;
    --tx-primary-soft: rgba(232, 238, 247, 0.78);
    --tx-ui-pass: v3-20260902;
    --tx-btn-primary-top: #6d8bb6;
    --tx-btn-primary-mid: #4d6f9a;
    --tx-btn-primary-bot: #3b5a84;
    --tx-gold: #8a6a3f;
    --tx-text: #2f2a24;
    --tx-text-muted: #5d5347;
    --tx-border: rgba(170, 145, 112, 0.28);
    --tx-success: #6f9a78;
    --tx-warning: #b2853e;
    --tx-danger: #a65d48;
    --tx-neutral: #8d8378;

    --tx-space-xs: 0.25rem;
    --tx-space-sm: 0.5rem;
    --tx-space-md: 0.75rem;
    --tx-space-lg: 1rem;
    --tx-space-xl: 1.5rem;

    /* Hierarchia térközskála: 4 / 8 / 12 / 16 / 24 / 32 */
    --tx-space-1: 4px;
    --tx-space-2: 8px;
    --tx-space-3: 12px;
    --tx-space-4: 16px;
    --tx-space-5: 24px;
    --tx-space-6: 32px;

    --tx-radius-sm: 8px;
    --tx-radius-md: 12px;
    --tx-radius-lg: 18px;
    --tx-radius-surface: 12px;

    --tx-shadow-soft: 0 4px 12px rgba(58, 40, 22, 0.08);
    --tx-shadow-float: 0 10px 24px rgba(38, 25, 10, 0.14);
    --tx-shadow-surface: 0 1px 2px rgba(58, 40, 22, 0.04), 0 4px 14px rgba(58, 40, 22, 0.05);

    --tx-work-surface: rgba(255, 252, 247, 0.96);
    --tx-helper-bg: rgba(236, 242, 248, 0.55);
    --tx-helper-bg-warm: rgba(247, 241, 232, 0.72);
    --tx-prose-width: 72ch;

    /* Scoped navigáció / command bar — aliasok a meglévő palettára */
    --ui-surface: rgba(255, 252, 247, 0.94);
    --ui-surface-hover: rgba(90, 122, 168, 0.08);
    --ui-surface-active: rgba(90, 122, 168, 0.14);
    --ui-border: rgba(170, 145, 112, 0.3);
    --ui-border-active: rgba(90, 122, 168, 0.4);
    --ui-text: #2f2a24;
    --ui-text-muted: #5d5347;
    --ui-accent: #5a7aa8;
    --ui-shadow-sm: 0 2px 8px rgba(52, 72, 98, 0.07);
    --ui-radius-sm: 10px;
    --ui-radius-md: 14px;
    --ui-space-1: 4px;
    --ui-space-2: 8px;
    --ui-space-3: 12px;
    --ui-space-4: 20px;
    --ui-space-5: 32px;
}
""".strip()


def premium_overlay_css() -> str:
    """Globális, alkalmazásszintű finomhangolás a meglévő stílus fölött."""
    return """
/* ===== Premium UX 2.0 overlay ===== */
.tx-page-intro {
    margin: 0 0 0.55rem;
    padding: 0 0 0.12rem;
}

.tx-shell-axis {
    max-width: 1160px;
    margin-left: auto;
    margin-right: auto;
    width: 100%;
}

.tx-intro-eyebrow {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--tx-gold);
    margin-bottom: 8px;
    text-transform: uppercase;
}

.tx-intro-title {
    font-family: "Playfair Display", "Cormorant Garamond", Georgia, serif;
    font-size: clamp(1.5rem, 2.8vw, 2rem);
    line-height: 1.2;
    margin: 0;
    color: #2a2117;
}

.tx-intro-body {
    margin-top: 6px;
    margin-bottom: 0;
    font-family: "Lora", Georgia, serif;
    font-size: 0.92rem;
    line-height: 1.4;
    color: var(--tx-text-muted);
    max-width: 64ch;
}

/* Gyorseszközök cím után a rács távolsága */
.tx-page-intro + .st-key-quick_tools_grid,
.tx-page-intro ~ .st-key-quick_tools_grid,
.st-key-workspace_intro + .st-key-quick_tools_grid,
.st-key-workspace_intro ~ .st-key-quick_tools_grid {
    margin-top: 10px !important;
}

.tx-status-badge {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 0.17rem 0.58rem;
    margin: 0.15rem 0;
    font-size: 0.78rem;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-weight: 600;
    letter-spacing: 0.01em;
    border: 1px solid transparent;
}

.tx-status-neutral { background: rgba(140, 132, 120, 0.14); color: #5d5347; border-color: rgba(140,132,120,0.24); }
.tx-status-info { background: rgba(90, 122, 168, 0.14); color: var(--tx-primary-deep); border-color: rgba(90,122,168,0.28); }
.tx-status-success { background: rgba(111, 154, 120, 0.14); color: #3d5a45; border-color: rgba(111,154,120,0.28); }
.tx-status-warning { background: rgba(178, 133, 62, 0.15); color: #6d4b1f; border-color: rgba(178,133,62,0.28); }
.tx-status-danger { background: rgba(166, 93, 72, 0.14); color: #6e2e1f; border-color: rgba(166,93,72,0.3); }

/* Helper / státusz — nem kártyarakás; bal oldali hangsúlycsík */
.tx-panel,
.tx-helper {
    border-radius: 0 var(--tx-radius-sm) var(--tx-radius-sm) 0;
    border: 1px solid rgba(170, 145, 112, 0.16);
    border-left-width: 3px;
    background: var(--tx-helper-bg);
    box-shadow: none;
    padding: 10px 14px 10px 12px;
    margin: var(--tx-space-2) 0 var(--tx-space-3);
    max-width: var(--tx-prose-width);
}
.tx-panel-title,
.tx-helper-title {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.84rem;
    font-weight: 650;
    margin-bottom: 2px;
    color: var(--tx-primary-deep);
    letter-spacing: 0.01em;
}
.tx-panel-body,
.tx-helper-body {
    font-family: "Lora", Georgia, serif;
    font-size: 0.9rem;
    line-height: 1.45;
    color: var(--tx-text-muted);
    max-width: var(--tx-prose-width);
}
.tx-panel-info,
.tx-helper-info { border-left-color: var(--tx-primary); background: var(--tx-helper-bg); }
.tx-panel-success,
.tx-helper-success { border-left-color: var(--tx-success); background: rgba(111, 154, 120, 0.1); }
.tx-panel-warning,
.tx-helper-warning { border-left-color: var(--tx-warning); background: rgba(178, 133, 62, 0.1); }
.tx-panel-danger,
.tx-helper-danger { border-left-color: var(--tx-danger); background: rgba(166, 93, 72, 0.1); }
.tx-panel-neutral,
.tx-helper-neutral { border-left-color: var(--tx-neutral); background: var(--tx-helper-bg-warm); }

.block-container {
    max-width: 1160px !important;
    margin-left: auto !important;
    margin-right: auto !important;
}

.main-card {
    border-radius: 24px !important;
    padding: 1.6rem 1.9rem 1.35rem !important;
    box-shadow: var(--tx-shadow-soft) !important;
    border: 1px solid var(--tx-border) !important;
}

.main-card:hover {
    transform: translateY(-2px) !important;
    box-shadow: var(--tx-shadow-float) !important;
}

.header-grid,
.textus-header,
.header-grid.textus-header {
    display: grid !important;
    align-items: center !important;
}

@media (min-width: 1025px) {
    .header-grid,
    .textus-header,
    .header-grid.textus-header {
        grid-template-columns: 148px minmax(0, 1fr) !important;
        gap: 22px !important;
    }
}

.header-logo {
    width: 148px !important;
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    background-image: none !important;
}

.textus-logo-badge {
    position: relative !important;
    display: grid !important;
    place-items: center !important;
    margin: 0 !important;
    box-sizing: border-box !important;
    border-radius: 50% !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    overflow: visible !important;
}

@media (min-width: 1025px) {
    .header-logo {
        width: 148px !important;
    }
    .textus-logo-badge {
        width: 142px !important;
        height: 142px !important;
        flex: 0 0 142px !important;
        padding: 0 !important;
    }
    div.header-logo > div.textus-logo-badge > img.textus-logo-image,
    div.textus-logo-badge > img.textus-logo-image,
    div.header-logo img.textus-logo-image.main-logo,
    .textus-logo-badge .textus-logo-image,
    .textus-logo-badge .main-logo,
    .header-logo .textus-logo-image,
    .header-logo .main-logo {
        max-width: 142px !important;
        max-height: 142px !important;
    }
}

div.header-logo > div.textus-logo-badge > img.textus-logo-image,
div.textus-logo-badge > img.textus-logo-image,
div.header-logo img.textus-logo-image.main-logo,
.textus-logo-badge .textus-logo-image,
.textus-logo-badge .main-logo,
.header-logo .textus-logo-image,
.header-logo .main-logo {
    position: static !important;
    display: block !important;
    width: 100% !important;
    height: 100% !important;
    margin: 0 auto !important;
    padding: 0 !important;
    inset: auto !important;
    left: auto !important;
    top: auto !important;
    right: auto !important;
    bottom: auto !important;
    transform: none !important;
    object-fit: contain !important;
    object-position: center center !important;
    background: transparent !important;
    background-image: none !important;
    opacity: 1 !important;
    mix-blend-mode: normal !important;
    filter: drop-shadow(0 4px 12px rgba(20, 32, 54, 0.22)) !important;
}

.main-card.header-card {
    /* tx-header-v2-marker */
    padding: 18px 28px 16px !important;
    margin-bottom: 1.35rem !important;
    border-radius: 22px !important;
    box-sizing: border-box !important;
}

@media (min-width: 1025px) {
    .main-card.header-card {
        min-height: 220px !important;
        max-height: 240px !important;
        padding: 20px 28px 18px !important;
    }
}

.main-card.header-card:hover {
    transform: none !important;
}

.header-text {
    max-width: 740px !important;
    gap: 0.22rem !important;
}

.brand-lockup {
    display: flex !important;
    flex-wrap: nowrap !important;
    align-items: baseline !important;
    gap: 0.55rem !important;
    line-height: 1 !important;
}

.main-title {
    font-family: "Cormorant Garamond", "Playfair Display", "Palatino Linotype", "Book Antiqua", Georgia, serif !important;
    font-size: clamp(2.15rem, 3.2vw, 2.75rem) !important;
    letter-spacing: 0.12em !important;
    line-height: 1 !important;
    margin: 0 !important;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.5) !important;
}

.version-inline {
    font-family: "Inter", "Segoe UI", system-ui, sans-serif !important;
    font-size: 1.2rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
    color: #7a8fad !important;
    line-height: 1 !important;
    white-space: nowrap !important;
}

.version-line {
    display: none !important;
}

.header-caption {
    margin-top: 0.12rem !important;
    padding: 0 !important;
    border: none !important;
    background: none !important;
    letter-spacing: 0.04em !important;
    text-transform: none !important;
    font-weight: 500 !important;
    font-size: 0.84rem !important;
    color: #5a6f8c !important;
    text-shadow: none !important;
}

.header-tagline {
    font-size: 1.1rem !important;
    letter-spacing: 0.03em !important;
    line-height: 1.3 !important;
    text-shadow: none !important;
}

.header-card .subtitle {
    margin-top: 0.35rem !important;
    font-size: 0.92rem !important;
    line-height: 1.38 !important;
    max-width: 46rem !important;
    color: #6a5844 !important;
    text-shadow: none !important;
    border-left: 2px solid rgba(141, 113, 79, 0.28) !important;
    padding-left: 0.7rem !important;
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
}

.header-card .scripture-ref {
    margin-top: 0.18rem !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    padding-left: 0.7rem !important;
    color: #7a6a56 !important;
}

/* Gyorseszközök kártyarács — .st-key-quick_tools_grid (auth-független, JS nélkül).
   Streamlit ≤1.58: [data-baseweb="tab-list"/"tab"].
   Streamlit ≥1.59 (Cloud): react-aria — [role="tablist"] + [data-testid="stTab"].
   .tx-quick-tools* csak visszafelé kompatibilis alias; új kód a keyed konténert használja. */
.st-key-quick_tools_grid [data-testid="stTabs"],
.st-key-quick_tools_grid [data-testid="stTabs"] > div {
    overflow: visible !important;
    max-width: 100% !important;
}

.st-key-quick_tools_grid [data-testid="stTabs"] [data-baseweb="tab-list"],
.st-key-quick_tools_grid [data-testid="stTabs"] [role="tablist"],
.st-key-quick_tools_grid [data-baseweb="tab-list"],
.st-key-quick_tools_grid [role="tablist"],
.tx-quick-tools,
.tx-quick-tools-root [data-baseweb="tab-list"],
.tx-quick-tools-root [role="tablist"] {
    display: grid !important;
    grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
    gap: 9px !important;
    border-bottom: none !important;
    padding: var(--ui-space-2) !important;
    background: var(--ui-surface) !important;
    border: 1px solid var(--ui-border) !important;
    border-radius: var(--ui-radius-md) !important;
    box-shadow: var(--ui-shadow-sm) !important;
    flex-wrap: unset !important;
    overflow-x: visible !important;
    overflow-y: visible !important;
    width: 100% !important;
    max-width: 100% !important;
}

.st-key-quick_tools_grid [data-testid="stTabs"] [data-baseweb="tab-highlight"],
.st-key-quick_tools_grid [data-testid="stTabs"] [data-baseweb="tab-border"],
.st-key-quick_tools_grid .react-aria-SelectionIndicator,
.st-key-quick_tools_grid [data-testid="stTabsScrollLeft"],
.st-key-quick_tools_grid [data-testid="stTabsScrollRight"],
.tx-quick-tools-root [data-baseweb="tab-highlight"],
.tx-quick-tools-root [data-baseweb="tab-border"] {
    display: none !important;
}

.st-key-quick_tools_grid [data-baseweb="tab"],
.st-key-quick_tools_grid [data-testid="stTab"],
.tx-quick-tools [data-baseweb="tab"],
.tx-quick-tools [data-testid="stTab"],
.tx-quick-tools-root [data-baseweb="tab"],
.tx-quick-tools-root [data-testid="stTab"] {
    min-height: 58px !important;
    height: 60px !important;
    max-height: 62px !important;
    border-radius: var(--ui-radius-sm) !important;
    border: 1px solid rgba(170, 145, 112, 0.55) !important;
    background: rgba(255, 255, 255, 0.98) !important;
    display: inline-flex !important;
    justify-content: flex-start !important;
    text-align: left !important;
    align-items: center !important;
    padding: 0 12px !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.92) inset,
        0 3px 8px rgba(58, 40, 22, 0.1) !important;
    font-weight: 600 !important;
    white-space: normal !important;
    line-height: 1.2 !important;
    gap: 9px !important;
    transition: background 160ms ease, border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease !important;
    transform: none !important;
    position: relative !important;
    min-width: 0 !important;
    max-width: 100% !important;
}

/* Nincs második ikon / elválasztó — csak Streamlit Material */
.st-key-quick_tools_grid [data-baseweb="tab"]::before,
.st-key-quick_tools_grid [data-testid="stTab"]::before,
.tx-quick-tools [data-baseweb="tab"]::before,
.tx-quick-tools [data-testid="stTab"]::before,
.tx-quick-tools-root [data-baseweb="tab"]::before,
.tx-quick-tools-root [data-testid="stTab"]::before,
.st-key-quick_tools_grid [data-baseweb="tab"] p::before,
.st-key-quick_tools_grid [data-baseweb="tab"] p::after,
.st-key-quick_tools_grid [data-baseweb="tab"] span::before,
.st-key-quick_tools_grid [data-baseweb="tab"] span::after,
.st-key-quick_tools_grid [data-testid="stTab"] p::before,
.st-key-quick_tools_grid [data-testid="stTab"] p::after,
.st-key-quick_tools_grid [data-testid="stTab"] span::before,
.st-key-quick_tools_grid [data-testid="stTab"] span::after,
.tx-quick-tools [data-baseweb="tab"] p::before,
.tx-quick-tools [data-baseweb="tab"] p::after,
.tx-quick-tools [data-baseweb="tab"] span::before,
.tx-quick-tools [data-baseweb="tab"] span::after,
.tx-quick-tools [data-testid="stTab"] p::before,
.tx-quick-tools [data-testid="stTab"] p::after,
.tx-quick-tools [data-testid="stTab"] span::before,
.tx-quick-tools [data-testid="stTab"] span::after,
.tx-quick-tools-root [data-baseweb="tab"] p::before,
.tx-quick-tools-root [data-baseweb="tab"] p::after,
.tx-quick-tools-root [data-baseweb="tab"] span::before,
.tx-quick-tools-root [data-baseweb="tab"] span::after,
.tx-quick-tools-root [data-testid="stTab"] p::before,
.tx-quick-tools-root [data-testid="stTab"] p::after,
.tx-quick-tools-root [data-testid="stTab"] span::before,
.tx-quick-tools-root [data-testid="stTab"] span::after {
    content: none !important;
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: none !important;
}

.st-key-quick_tools_grid [data-baseweb="tab"]::after,
.st-key-quick_tools_grid [data-testid="stTab"]::after,
.tx-quick-tools [data-baseweb="tab"]::after,
.tx-quick-tools [data-testid="stTab"]::after,
.tx-quick-tools-root [data-baseweb="tab"]::after,
.tx-quick-tools-root [data-testid="stTab"]::after {
    content: none !important;
    display: none !important;
}

.st-key-quick_tools_grid [data-baseweb="tab"]:hover,
.st-key-quick_tools_grid [data-testid="stTab"]:hover,
.tx-quick-tools [data-baseweb="tab"]:hover,
.tx-quick-tools [data-testid="stTab"]:hover,
.tx-quick-tools-root [data-baseweb="tab"]:hover,
.tx-quick-tools-root [data-testid="stTab"]:hover {
    transform: translateY(-2px) !important;
    background: rgba(232, 238, 247, 0.92) !important;
    border-color: rgba(90, 122, 168, 0.55) !important;
    box-shadow: 0 8px 16px rgba(58, 40, 22, 0.16) !important;
}

.st-key-quick_tools_grid [data-baseweb="tab"] [data-testid="stMarkdownContainer"],
.st-key-quick_tools_grid [data-testid="stTab"] [data-testid="stMarkdownContainer"],
.tx-quick-tools [data-baseweb="tab"] [data-testid="stMarkdownContainer"],
.tx-quick-tools [data-testid="stTab"] [data-testid="stMarkdownContainer"],
.tx-quick-tools-root [data-baseweb="tab"] [data-testid="stMarkdownContainer"],
.tx-quick-tools-root [data-testid="stTab"] [data-testid="stMarkdownContainer"] {
    display: inline-flex !important;
    align-items: center !important;
    gap: 9px !important;
    min-width: 0 !important;
}

.st-key-quick_tools_grid [data-baseweb="tab"] [data-testid="stMarkdownContainer"] p,
.st-key-quick_tools_grid [data-baseweb="tab"] p,
.st-key-quick_tools_grid [data-testid="stTab"] [data-testid="stMarkdownContainer"] p,
.st-key-quick_tools_grid [data-testid="stTab"] p,
.tx-quick-tools [data-baseweb="tab"] [data-testid="stMarkdownContainer"] p,
.tx-quick-tools [data-baseweb="tab"] p,
.tx-quick-tools [data-testid="stTab"] [data-testid="stMarkdownContainer"] p,
.tx-quick-tools [data-testid="stTab"] p,
.tx-quick-tools-root [data-baseweb="tab"] p,
.tx-quick-tools-root [data-testid="stTab"] p {
    display: inline-flex !important;
    align-items: center !important;
    gap: 9px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    font-size: 0.89rem !important;
    line-height: 1.2 !important;
    margin: 0 !important;
    color: var(--tx-text) !important;
}

.st-key-quick_tools_grid [data-baseweb="tab"] [data-testid="stIconMaterial"],
.st-key-quick_tools_grid [data-testid="stTab"] [data-testid="stIconMaterial"],
.st-key-quick_tools_grid [data-testid="stTab"] [role="img"],
.tx-quick-tools [data-baseweb="tab"] [data-testid="stIconMaterial"],
.tx-quick-tools [data-testid="stTab"] [data-testid="stIconMaterial"],
.tx-quick-tools [data-testid="stTab"] [role="img"],
.tx-quick-tools-root [data-baseweb="tab"] [data-testid="stIconMaterial"],
.tx-quick-tools-root [data-testid="stTab"] [data-testid="stIconMaterial"],
.tx-quick-tools-root [data-testid="stTab"] [role="img"] {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined", sans-serif !important;
    font-feature-settings: "liga" 1 !important;
    -webkit-font-feature-settings: "liga" 1 !important;
    font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 20 !important;
    font-size: 19px !important;
    line-height: 1 !important;
    color: var(--ui-accent) !important;
    flex-shrink: 0 !important;
    width: 19px !important;
    height: 19px !important;
    overflow: hidden !important;
    text-overflow: clip !important;
    white-space: nowrap !important;
}

.st-key-quick_tools_grid [aria-selected="true"][data-baseweb="tab"],
.st-key-quick_tools_grid [data-testid="stTab"][aria-selected="true"],
.tx-quick-tools [aria-selected="true"][data-baseweb="tab"],
.tx-quick-tools [data-testid="stTab"][aria-selected="true"],
.tx-quick-tools-root [aria-selected="true"][data-baseweb="tab"],
.tx-quick-tools-root [data-testid="stTab"][aria-selected="true"] {
    background: rgba(90, 122, 168, 0.38) !important;
    border-color: rgba(53, 85, 124, 0.72) !important;
    color: #102033 !important;
    /* Bal oldali accent-sáv — egyértelmű "ez van kiválasztva" jelzés,
       nem csak a háttérszín-árnyalatra hagyatkozva. */
    box-shadow:
        inset 3px 0 0 0 var(--tx-primary),
        0 1px 0 rgba(255, 255, 255, 0.55) inset,
        0 4px 12px rgba(52, 72, 98, 0.14) !important;
    transform: translateY(-1px) !important;
}
.st-key-quick_tools_grid [aria-selected="true"][data-baseweb="tab"] [data-testid="stMarkdownContainer"] p,
.st-key-quick_tools_grid [data-testid="stTab"][aria-selected="true"] [data-testid="stMarkdownContainer"] p,
.tx-quick-tools [aria-selected="true"][data-baseweb="tab"] [data-testid="stMarkdownContainer"] p,
.tx-quick-tools [data-testid="stTab"][aria-selected="true"] [data-testid="stMarkdownContainer"] p,
.tx-quick-tools-root [aria-selected="true"][data-baseweb="tab"] [data-testid="stMarkdownContainer"] p,
.tx-quick-tools-root [data-testid="stTab"][aria-selected="true"] [data-testid="stMarkdownContainer"] p {
    font-weight: 650 !important;
}

@media (max-width: 1024px) {
    .st-key-quick_tools_grid [data-testid="stTabs"] [data-baseweb="tab-list"],
    .st-key-quick_tools_grid [data-testid="stTabs"] [role="tablist"],
    .st-key-quick_tools_grid [data-baseweb="tab-list"],
    .st-key-quick_tools_grid [role="tablist"],
    .tx-quick-tools,
    .tx-quick-tools-root [data-baseweb="tab-list"],
    .tx-quick-tools-root [role="tablist"] {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }
}

@media (max-width: 560px) {
    .st-key-quick_tools_grid [data-testid="stTabs"] [data-baseweb="tab-list"],
    .st-key-quick_tools_grid [data-testid="stTabs"] [role="tablist"],
    .st-key-quick_tools_grid [data-baseweb="tab-list"],
    .st-key-quick_tools_grid [role="tablist"],
    .tx-quick-tools,
    .tx-quick-tools-root [data-baseweb="tab-list"],
    .tx-quick-tools-root [role="tablist"] {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }
    .st-key-quick_tools_grid [data-baseweb="tab"],
    .st-key-quick_tools_grid [data-testid="stTab"],
    .tx-quick-tools [data-baseweb="tab"],
    .tx-quick-tools [data-testid="stTab"],
    .tx-quick-tools-root [data-baseweb="tab"],
    .tx-quick-tools-root [data-testid="stTab"] {
        min-height: 52px !important;
        height: 56px !important;
        max-height: none !important;
    }
}

@media (max-width: 390px) {
    .st-key-quick_tools_grid [data-testid="stTabs"] [data-baseweb="tab-list"],
    .st-key-quick_tools_grid [data-testid="stTabs"] [role="tablist"],
    .st-key-quick_tools_grid [data-baseweb="tab-list"],
    .st-key-quick_tools_grid [role="tablist"],
    .tx-quick-tools,
    .tx-quick-tools-root [data-baseweb="tab-list"],
    .tx-quick-tools-root [role="tablist"] {
        grid-template-columns: 1fr !important;
    }
}

[data-testid="stTextInput"] > label,
[data-testid="stTextArea"] > label,
[data-testid="stSelectbox"] > label {
    margin-bottom: 0.25rem !important;
}

.stTextInput input,
.stTextArea textarea,
.stSelectbox [data-baseweb="select"] > div {
    border-radius: var(--tx-radius-md) !important;
}

/* ===== Igehely keresése — alkalomválasztó (scoped) =====
   Csak .st-key-passage_search_occasion_field; más selectboxokat nem érint.
   Nyitott lista: BaseWeb portal — body:has(combobox aria-expanded) + [role=option]. */
.st-key-passage_search_occasion_field {
    margin: 0.15rem 0 0.55rem !important;
}
.st-key-passage_search_occasion_field [data-testid="stSelectbox"] > label,
.st-key-passage_search_occasion_field [data-testid="stWidgetLabel"] {
    margin-bottom: 0.35rem !important;
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    color: var(--tx-text) !important;
    letter-spacing: 0.01em !important;
}
.st-key-passage_search_occasion_field [data-testid="stCaption"],
.st-key-passage_search_occasion_field [data-testid="stCaptionContainer"] {
    margin-top: 0.35rem !important;
    margin-bottom: 0 !important;
}
.st-key-passage_search_occasion_field [data-testid="stCaption"] p,
.st-key-passage_search_occasion_field [data-testid="stCaptionContainer"] p {
    font-size: 0.82rem !important;
    line-height: 1.35 !important;
    color: var(--tx-text-muted) !important;
}
.st-key-passage_search_occasion_field [data-baseweb="select"] {
    cursor: pointer !important;
}
.st-key-passage_search_occasion_field [data-baseweb="select"] > div {
    position: relative !important;
    min-height: 50px !important;
    height: 50px !important;
    max-height: 52px !important;
    padding: 0 0.15rem 0 2.55rem !important;
    border-radius: 11px !important;
    border: 1px solid rgba(155, 145, 132, 0.48) !important;
    background: #fbf7f0 !important; /* egy árnyalattal világosabb a --tx-bg-nél */
    box-shadow: 0 1px 2px rgba(58, 40, 22, 0.05) !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease !important;
    cursor: pointer !important;
}
.st-key-passage_search_occasion_field [data-baseweb="select"] > div:hover {
    border-color: rgba(90, 122, 168, 0.55) !important;
    background: #fffcf7 !important;
    box-shadow: 0 1px 3px rgba(90, 122, 168, 0.1) !important;
}
.st-key-passage_search_occasion_field [data-baseweb="select"] > div:focus-within {
    border-color: rgba(90, 122, 168, 0.72) !important;
    box-shadow: 0 0 0 2px rgba(90, 122, 168, 0.18) !important;
    background: #fffcf7 !important;
}
/* Bal oldali alkalom / naptár ikon */
.st-key-passage_search_occasion_field [data-baseweb="select"] > div::before {
    content: "event" !important;
    font-family: "Material Symbols Rounded", "Material Symbols Outlined", sans-serif !important;
    font-size: 1.2rem !important;
    font-weight: 400 !important;
    line-height: 1 !important;
    color: rgba(90, 122, 168, 0.78) !important;
    position: absolute !important;
    left: 0.85rem !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    pointer-events: none !important;
    font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24 !important;
}
.st-key-passage_search_occasion_field [data-baseweb="select"] div[value] {
    font-size: 15.5px !important;
    font-weight: 500 !important;
    color: var(--tx-text) !important;
    line-height: 1.3 !important;
}
/* Jobb oldali chevron zóna — legalább 32×32, enyhén elválasztva */
.st-key-passage_search_occasion_field [data-baseweb="select"] > div > div:last-child {
    min-width: 36px !important;
    min-height: 36px !important;
    width: 36px !important;
    height: 36px !important;
    margin: 0 0.2rem 0 0.15rem !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    border-left: 1px solid rgba(170, 145, 112, 0.22) !important;
    border-radius: 0 10px 10px 0 !important;
    flex-shrink: 0 !important;
}
.st-key-passage_search_occasion_field [data-baseweb="select"] svg {
    width: 18px !important;
    height: 18px !important;
    color: rgba(93, 83, 71, 0.72) !important;
}
/* Nyitott lista — Streamlit select UL-je gyakran role nélkül; option-ökön van role=option */
body:has(.st-key-passage_search_occasion_field [aria-expanded="true"])
    div[data-baseweb="popover"]:has([role="option"]) {
    z-index: 10050 !important;
    width: min(360px, 92vw) !important;
    max-width: min(360px, 92vw) !important;
}
body:has(.st-key-passage_search_occasion_field [aria-expanded="true"])
    div[data-baseweb="popover"]:has([role="option"]) > div {
    border-radius: 12px !important;
    border: 1px solid rgba(160, 150, 138, 0.4) !important;
    background: #fffcf7 !important;
    box-shadow: 0 8px 22px rgba(38, 25, 10, 0.14), 0 2px 6px rgba(58, 40, 22, 0.06) !important;
    overflow: hidden !important;
    width: 100% !important;
    max-width: 100% !important;
}
body:has(.st-key-passage_search_occasion_field [aria-expanded="true"])
    div[data-baseweb="popover"]:has([role="option"]) ul {
    max-height: 320px !important;
    overflow-y: auto !important;
    padding: 0.25rem 0 !important;
    background: #fffcf7 !important;
    width: 100% !important;
}
body:has(.st-key-passage_search_occasion_field [aria-expanded="true"])
    div[data-baseweb="popover"]:has([role="option"]) li[role="option"] {
    /* BaseWeb virtualizált sor: inline height ~40px — ne törjük a top pozíciókat */
    box-sizing: border-box !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
    border-radius: 8px !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    color: var(--tx-text) !important;
    transition: background 0.12s ease !important;
}
body:has(.st-key-passage_search_occasion_field [aria-expanded="true"])
    div[data-baseweb="popover"]:has([role="option"]) li[role="option"]:hover {
    background: rgba(90, 122, 168, 0.1) !important;
}
body:has(.st-key-passage_search_occasion_field [aria-expanded="true"])
    div[data-baseweb="popover"]:has([role="option"]) li[role="option"][aria-selected="true"] {
    background: rgba(232, 238, 247, 0.95) !important; /* beige-blue */
    color: var(--tx-primary-deep) !important;
    font-weight: 600 !important;
}
@media (max-width: 640px) {
    .st-key-passage_search_occasion_field [data-baseweb="select"] > div {
        min-height: 48px !important;
        height: 48px !important;
        padding-left: 2.4rem !important;
    }
    body:has(.st-key-passage_search_occasion_field [aria-expanded="true"])
        div[data-baseweb="popover"]:has([role="option"]) {
        width: min(100vw - 1.5rem, 360px) !important;
        max-width: min(100vw - 1.5rem, 360px) !important;
    }
}

/* ===== Igehely keresése — alkalom háttere (opcionális, ceremoniális) ===== */
.st-key-passage_search_occasion_context {
    margin: 0.35rem 0 0.75rem 0 !important;
    padding: 0.55rem 0.8rem 0.65rem 0.8rem !important;
    border: 1px solid var(--tx-border) !important;
    border-radius: var(--tx-radius-md) !important;
    background: var(--tx-surface) !important;
    box-shadow: none !important;
}
.st-key-passage_search_occasion_context [data-testid="stWidgetLabel"] p,
.st-key-passage_search_occasion_context label p {
    font-size: 0.88rem !important;
    font-weight: 500 !important;
}
.st-key-passage_search_occasion_context [data-testid="stCaption"] p,
.st-key-passage_search_occasion_context [data-testid="stCaptionContainer"] p {
    font-size: 0.82rem !important;
    line-height: 1.35 !important;
}
.st-key-passage_search_occasion_context textarea {
    min-height: 4.1rem !important;
}

.stExpander {
    border: 1px solid rgba(170, 145, 112, 0.42) !important;
    border-radius: var(--tx-radius-md) !important;
    background: rgba(255, 252, 247, 0.94) !important;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.8) inset, 0 2px 6px rgba(58, 40, 22, 0.06) !important;
}

/* ===== Egységes gombhierarchia (alap magasság; scoped nav felülírja) ===== */
.stButton > button {
    min-height: 2.4rem !important;
    border-radius: var(--tx-radius-md) !important;
    font-weight: 600 !important;
    transition: transform 0.14s ease, box-shadow 0.14s ease, background 0.14s ease, border-color 0.14s ease;
}
.stButton > button[kind="secondary"],
.stButton > button[data-testid="stBaseButton-secondary"] {
    background:
        linear-gradient(
            180deg,
            rgba(255, 254, 250, 0.98) 0%,
            rgba(236, 226, 210, 0.9) 100%
        ) !important;
    border: 1px solid rgba(170, 145, 112, 0.46) !important;
    color: var(--tx-primary-deep) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.9) inset,
        0 -1px 0 rgba(86, 64, 38, 0.08) inset,
        0 3px 8px rgba(58, 40, 22, 0.1) !important;
}
.stButton > button[kind="secondary"]:hover,
.stButton > button[data-testid="stBaseButton-secondary"]:hover {
    background:
        linear-gradient(
            180deg,
            rgba(255, 255, 252, 1) 0%,
            rgba(232, 238, 247, 0.94) 100%
        ) !important;
    border-color: rgba(90, 122, 168, 0.48) !important;
    transform: translateY(-1px) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.95) inset,
        0 6px 14px rgba(52, 72, 98, 0.14) !important;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"],
.stButton > button[kind="primaryFormSubmit"] {
    background:
        linear-gradient(
            180deg,
            var(--tx-btn-primary-top) 0%,
            var(--tx-btn-primary-mid) 52%,
            var(--tx-btn-primary-bot) 100%
        ) !important;
    border: 1px solid #35557c !important;
    color: #ffffff !important;
    text-shadow: 0 1px 0 rgba(18, 32, 48, 0.25) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.28) inset,
        0 4px 10px rgba(31, 51, 77, 0.28) !important;
}
.stButton > button[kind="primary"]::before,
.stButton > button[kind="primary"]::after,
.stButton > button[kind="primaryFormSubmit"]::before,
.stButton > button[kind="primaryFormSubmit"]::after,
.stButton > button[data-testid="stBaseButton-primary"]::before,
.stButton > button[data-testid="stBaseButton-primary"]::after {
    content: none !important;
    display: none !important;
    background: none !important;
    opacity: 0 !important;
}
.stButton > button[kind="primary"] [data-testid="stMarkdownContainer"] p,
.stButton > button[data-testid="stBaseButton-primary"] [data-testid="stMarkdownContainer"] p,
.stButton > button[kind="primary"] > div > p,
.stButton > button[kind="primaryFormSubmit"] > div > p,
.stButton > button[kind="primary"] [data-testid="stIconMaterial"],
.stButton > button[data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"] {
    color: #ffffff !important;
    text-shadow: 0 1px 0 rgba(18, 32, 48, 0.25) !important;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    background:
        linear-gradient(
            180deg,
            #7a98c0 0%,
            #5a7aa8 52%,
            #45678f 100%
        ) !important;
    transform: translateY(-1px) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.34) inset,
        0 7px 14px rgba(31, 51, 77, 0.32) !important;
}
.stButton > button:active {
    transform: translateY(1px) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.18) inset,
        0 1px 3px rgba(31, 51, 77, 0.28) inset !important;
}
.stButton > button:focus-visible {
    outline: 2px solid rgba(90, 122, 168, 0.55) !important;
    outline-offset: 2px !important;
}

/* ===== Tartalmi felületek és üzenetek ===== */
/* Szakaszcím (H2/H3) egységes, visszafogott méret */
.stMarkdown h2, [data-testid="stHeading"] h2 {
    font-size: 1.55rem !important;
    line-height: 1.25 !important;
    letter-spacing: 0 !important;
}
.stMarkdown h3, [data-testid="stHeading"] h3 {
    font-size: 1.2rem !important;
    line-height: 1.3 !important;
}

/* Információs panelek: finom, bal kék sáv, nem csupa félkövér, nem harsány */
[data-testid="stAlert"] {
    border-radius: var(--tx-radius-md) !important;
    border: 1px solid var(--tx-border) !important;
    border-left: 3px solid var(--tx-primary) !important;
    box-shadow: none !important;
    padding: 0.65rem 0.9rem !important;
}
[data-testid="stAlertContentSuccess"] { }
[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) { border-left-color: var(--tx-success) !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) { border-left-color: var(--tx-warning) !important; }
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) { border-left-color: var(--tx-danger) !important; }
[data-testid="stAlert"] p {
    font-weight: 500 !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    font-size: 0.95rem !important;
    line-height: 1.5 !important;
}

@media (max-width: 1024px) {
    .block-container {
        max-width: 100% !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    .header-grid,
    .textus-header,
    .header-grid.textus-header,
    div.header-grid.textus-header {
        grid-template-columns: 1fr !important;
        text-align: center !important;
        justify-items: center !important;
        gap: 0.8rem !important;
    }
    .header-logo {
        width: 96px !important;
    }
    .textus-logo-badge {
        width: 90px !important;
        height: 90px !important;
        flex: 0 0 90px !important;
        flex-basis: 90px !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    div.header-logo > div.textus-logo-badge > img.textus-logo-image,
    div.textus-logo-badge > img.textus-logo-image,
    .textus-logo-badge .textus-logo-image,
    .textus-logo-badge .main-logo,
    .header-logo .textus-logo-image,
    .header-logo .main-logo {
        width: 100% !important;
        height: 100% !important;
        max-width: 90px !important;
        max-height: 90px !important;
        transform: none !important;
        margin: 0 auto !important;
        left: auto !important;
        top: auto !important;
    }
    .header-text {
        align-items: center !important;
        max-width: 28rem !important;
    }
    .brand-lockup {
        justify-content: center !important;
    }
    .main-title {
        font-size: clamp(1.85rem, 5vw, 2.25rem) !important;
    }
    .version-inline {
        font-size: 1.05rem !important;
    }
    .header-card .subtitle {
        -webkit-line-clamp: 3 !important;
        text-align: left !important;
        font-size: 0.84rem !important;
    }
}

@media (max-width: 768px) {
    .main-card {
        padding: 1rem 1rem 0.95rem !important;
        border-radius: 18px !important;
    }
    .main-card.header-card {
        padding: 14px 14px 12px !important;
    }
    .main-title {
        font-size: 2rem !important;
    }
}

/* ===== Unified app toolbar — key=textus_app_toolbar ===== */
.st-key-textus_app_toolbar {
    width: 100% !important;
    max-width: 1160px !important;
    margin: 0 0 10px !important;
    padding: 8px 12px !important;
    box-sizing: border-box !important;
    border-radius: 14px !important;
    border: 1px solid rgba(170, 145, 112, 0.32) !important;
    background:
        linear-gradient(
            180deg,
            rgba(255, 253, 248, 0.97) 0%,
            rgba(247, 239, 226, 0.92) 100%
        ) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.92) inset,
        0 -1px 0 rgba(86, 64, 38, 0.06) inset,
        0 8px 18px rgba(58, 40, 22, 0.08) !important;
    min-height: 54px !important;
}

.st-key-textus_app_toolbar [data-testid="stHorizontalBlock"],
.st-key-textus_app_toolbar [data-testid="stLayoutWrapper"] {
    align-items: center !important;
}

.st-key-textus_app_toolbar > div,
.st-key-textus_app_toolbar[data-testid="stHorizontalBlock"],
.st-key-tx_toolbar_main,
.st-key-tx_toolbar_center,
.st-key-tx_toolbar_actions,
.st-key-tx_toolbar_main[data-testid="stHorizontalBlock"],
.st-key-tx_toolbar_center[data-testid="stHorizontalBlock"],
.st-key-tx_toolbar_actions[data-testid="stHorizontalBlock"],
.st-key-tx_toolbar_main > div,
.st-key-tx_toolbar_center > div,
.st-key-tx_toolbar_actions > div {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    flex-wrap: nowrap !important;
    gap: 8px !important;
    min-height: 42px !important;
}

.st-key-textus_app_toolbar > div,
.st-key-textus_app_toolbar[data-testid="stHorizontalBlock"] {
    width: 100% !important;
}

.st-key-tx_toolbar_main,
.st-key-tx_toolbar_center,
.st-key-tx_toolbar_actions {
    width: auto !important;
    max-width: 100% !important;
}

.st-key-tx_toolbar_main [data-testid="stElementContainer"],
.st-key-tx_toolbar_center [data-testid="stElementContainer"],
.st-key-tx_toolbar_actions [data-testid="stElementContainer"],
.st-key-tx_toolbar_main [data-testid="stMarkdown"],
.st-key-tx_toolbar_center [data-testid="stMarkdown"],
.st-key-tx_toolbar_actions [data-testid="stMarkdown"],
.st-key-tx_toolbar_main [data-testid="stLayoutWrapper"],
.st-key-tx_toolbar_center [data-testid="stLayoutWrapper"],
.st-key-tx_toolbar_actions [data-testid="stLayoutWrapper"] {
    width: auto !important;
    max-width: max-content !important;
    flex: 0 0 auto !important;
    min-width: 0 !important;
}

.st-key-tx_toolbar_main [data-testid="stElementContainer"]:has(.tx-project-name-row) {
    flex: 0 1 auto !important;
    max-width: 220px !important;
    min-width: 0 !important;
}

.st-key-tx_toolbar_main {
    flex: 0 1 auto !important;
    min-width: 0 !important;
}

.st-key-tx_toolbar_flex,
.st-key-tx_toolbar_flex_end {
    flex: 1 1 auto !important;
    min-width: 8px !important;
    max-width: none !important;
}

.st-key-tx_toolbar_center {
    flex: 0 0 auto !important;
    padding: 0 10px !important;
    margin: 0 4px !important;
    border-left: 1px solid rgba(170, 145, 112, 0.3) !important;
    border-right: 1px solid rgba(170, 145, 112, 0.3) !important;
}

.st-key-tx_toolbar_actions {
    flex: 0 0 auto !important;
}

.st-key-textus_app_toolbar > [data-testid="stLayoutWrapper"]:has(.st-key-tx_toolbar_main) {
    flex: 0 1 auto !important;
    min-width: 0 !important;
    width: auto !important;
    max-width: none !important;
}
.st-key-textus_app_toolbar > [data-testid="stLayoutWrapper"]:has(.st-key-tx_toolbar_flex),
.st-key-textus_app_toolbar > [data-testid="stLayoutWrapper"]:has(.st-key-tx_toolbar_flex_end) {
    flex: 1 1 auto !important;
    min-width: 8px !important;
    width: auto !important;
}
.st-key-textus_app_toolbar > [data-testid="stLayoutWrapper"]:has(.st-key-tx_toolbar_center) {
    flex: 0 0 auto !important;
    width: auto !important;
}
.st-key-textus_app_toolbar > [data-testid="stLayoutWrapper"]:has(.st-key-tx_toolbar_actions) {
    flex: 0 0 auto !important;
    margin-left: 0 !important;
    width: auto !important;
}

.st-key-textus_app_toolbar .stButton,
.st-key-textus_app_toolbar [data-testid="stPopover"] {
    width: auto !important;
    margin: 0 !important;
    flex: 0 0 auto !important;
}

.st-key-textus_app_toolbar .stButton button,
.st-key-textus_app_toolbar [data-testid="stPopover"] > button {
    min-height: 40px !important;
    height: 40px !important;
    padding: 0 0.7rem !important;
    border-radius: 10px !important;
    font-weight: 650 !important;
    gap: 6px !important;
    display: inline-flex !important;
    align-items: center !important;
    white-space: nowrap !important;
    width: auto !important;
    transition: transform 0.14s ease, box-shadow 0.14s ease, border-color 0.14s ease, background 0.14s ease !important;
}

.st-key-textus_app_toolbar .stButton button[kind="secondary"],
.st-key-textus_app_toolbar [data-testid="stPopover"] > button {
    background:
        linear-gradient(
            180deg,
            rgba(255, 254, 250, 0.98) 0%,
            rgba(236, 226, 210, 0.9) 100%
        ) !important;
    border: 1px solid rgba(170, 145, 112, 0.46) !important;
    color: var(--tx-primary-deep) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.9) inset,
        0 -1px 0 rgba(86, 64, 38, 0.08) inset,
        0 3px 8px rgba(58, 40, 22, 0.1) !important;
}

.st-key-textus_app_toolbar .stButton button[kind="secondary"]:hover,
.st-key-textus_app_toolbar [data-testid="stPopover"] > button:hover {
    background:
        linear-gradient(
            180deg,
            rgba(255, 255, 252, 1) 0%,
            rgba(232, 238, 247, 0.94) 100%
        ) !important;
    border-color: rgba(90, 122, 168, 0.48) !important;
    transform: translateY(-1px) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.95) inset,
        0 6px 14px rgba(52, 72, 98, 0.14) !important;
}

.st-key-textus_app_toolbar .stButton button[kind="primary"] {
    background:
        linear-gradient(
            180deg,
            var(--tx-btn-primary-top) 0%,
            var(--tx-btn-primary-mid) 52%,
            var(--tx-btn-primary-bot) 100%
        ) !important;
    border: 1px solid #35557c !important;
    color: #ffffff !important;
    text-shadow: 0 1px 0 rgba(18, 32, 48, 0.25) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.28) inset,
        0 4px 10px rgba(31, 51, 77, 0.28) !important;
}

.st-key-textus_app_toolbar .stButton button[kind="primary"] [data-testid="stMarkdownContainer"] p,
.st-key-textus_app_toolbar .stButton button[kind="primary"] [data-testid="stIconMaterial"] {
    color: #ffffff !important;
}

.st-key-textus_app_toolbar .stButton button[kind="primary"]:hover {
    background:
        linear-gradient(
            180deg,
            #7a98c0 0%,
            #5a7aa8 52%,
            #45678f 100%
        ) !important;
    transform: translateY(-1px) !important;
}
.st-key-textus_app_toolbar .stButton button:active,
.st-key-textus_app_toolbar [data-testid="stPopover"] > button:active {
    transform: translateY(0) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.55) inset,
        0 1px 3px rgba(58, 40, 22, 0.14) !important;
}

.tx-toolbar-divider {
    width: 1px;
    align-self: stretch;
    min-height: 28px;
    height: 28px;
    margin: 0 2px;
    background: rgba(170, 145, 112, 0.45);
    flex: 0 0 auto;
}
.st-key-textus_app_toolbar [data-testid="stElementContainer"]:has(.tx-toolbar-divider) {
    width: auto !important;
    flex: 0 0 auto !important;
    display: flex !important;
    align-items: center !important;
}

.tx-appbar-guest-inline {
    display: inline-flex;
    align-items: center;
    margin-right: 0.35rem;
}

.tx-appbar-guest-label {
    font-size: 0.88rem;
    font-weight: 600;
    color: var(--ui-text-muted);
    white-space: nowrap;
    text-align: left;
    padding: 0 0.15rem;
}

.tx-guest-strip {
    margin: 0 0 10px;
    padding: 0.28rem 0.72rem;
    border-radius: 999px;
    border: 1px solid rgba(170, 145, 112, 0.28);
    background:
        linear-gradient(
            180deg,
            rgba(255, 252, 247, 0.92),
            rgba(238, 228, 211, 0.78)
        );
    color: var(--ui-text-muted);
    font-size: 0.78rem;
    font-weight: 600;
    line-height: 1.3;
    display: inline-flex;
    align-items: center;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.8) inset, 0 2px 6px rgba(58, 40, 22, 0.06);
}

.tx-project-name-row {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    max-width: 220px;
    flex-wrap: nowrap;
}

.tx-project-name-text {
    font-size: 0.92rem;
    font-weight: 650;
    color: var(--ui-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 160px;
}

.tx-project-status-chip {
    display: inline-flex;
    align-items: center;
    font-size: 0.72rem;
    font-weight: 650;
    letter-spacing: 0.01em;
    padding: 0.14rem 0.5rem;
    border-radius: 999px;
    border: 1px solid rgba(170, 145, 112, 0.32);
    background:
        linear-gradient(
            180deg,
            rgba(255, 253, 248, 0.96),
            rgba(238, 228, 211, 0.86)
        );
    color: var(--ui-text-muted);
    white-space: nowrap;
    flex: 0 0 auto;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.82) inset, 0 1px 3px rgba(58, 40, 22, 0.06);
}

.tx-project-status-chip.is-dirty {
    border-color: rgba(178, 133, 62, 0.35);
    background: rgba(178, 133, 62, 0.12);
    color: #6d4b1f;
}

.tx-project-status-chip.is-saved {
    border-color: rgba(111, 154, 120, 0.35);
    background: rgba(111, 154, 120, 0.12);
    color: #3d5a45;
}

.tx-project-status-chip.is-temp {
    border-color: rgba(140, 132, 120, 0.3);
    background: rgba(140, 132, 120, 0.12);
    color: #5d5347;
}

.tx-project-status-chip.is-save-failed {
    border-color: rgba(178, 58, 46, 0.4);
    background: rgba(178, 58, 46, 0.14);
    color: #8f2e21;
}

.tx-project-status-chip.is-conflict {
    border-color: rgba(146, 78, 176, 0.4);
    background: rgba(146, 78, 176, 0.14);
    color: #6a3d80;
}

.st-key-textus_app_toolbar .st-key-tx_appbar_home button,
.st-key-textus_app_toolbar .st-key-bar_title_edit button,
.st-key-textus_app_toolbar .st-key-tx_appbar_settings button {
    min-width: 40px !important;
    width: 40px !important;
    max-width: 44px !important;
    padding: 0 !important;
    justify-content: center !important;
}
.st-key-textus_app_toolbar .st-key-tx_appbar_home button [data-testid="stMarkdownContainer"],
.st-key-textus_app_toolbar .st-key-bar_title_edit button [data-testid="stMarkdownContainer"],
.st-key-textus_app_toolbar .st-key-tx_appbar_settings button [data-testid="stMarkdownContainer"] {
    position: absolute !important;
    width: 1px !important;
    height: 1px !important;
    padding: 0 !important;
    margin: -1px !important;
    overflow: hidden !important;
    clip: rect(0, 0, 0, 0) !important;
    border: 0 !important;
}

.st-key-textus_app_toolbar .st-key-bar_save_more_popover button {
    min-width: 40px !important;
    width: 40px !important;
    padding: 0 !important;
    justify-content: center !important;
}

.st-key-textus_app_toolbar .st-key-bar_overflow_more {
    display: none !important;
}

.st-key-textus_app_toolbar .st-key-bar_projects_popover,
.st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"],
.st-key-textus_app_toolbar .st-key-bar_projects_popover [data-testid="stPopover"],
.st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] [data-testid="stPopover"],
.st-key-textus_app_toolbar .st-key-bar_projects_open {
    width: auto !important;
    min-width: 112px !important;
    flex: 0 0 auto !important;
}
.st-key-textus_app_toolbar .st-key-bar_projects_popover > button,
.st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] > button,
.st-key-textus_app_toolbar .st-key-bar_projects_popover [data-testid="stPopover"] > button,
.st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] [data-testid="stPopover"] > button,
.st-key-textus_app_toolbar .st-key-bar_projects_open button {
    min-width: 112px !important;
    width: auto !important;
    white-space: nowrap !important;
    justify-content: flex-start !important;
}

.tx-projects-empty {
    padding: 0.55rem 0.15rem 0.35rem;
    color: var(--ui-text-muted);
    font-size: 0.88rem;
    line-height: 1.45;
}
.tx-projects-empty p {
    margin: 0 0 0.35rem;
}

div[data-baseweb="popover"]:has([class*="st-key-project_picker_content"]) {
    width: 520px !important;
    min-width: 440px !important;
    max-width: calc(100vw - 32px) !important;
}
div[data-baseweb="popover"]:has([class*="st-key-project_picker_content"]) > div,
div[data-baseweb="popover"]:has([class*="st-key-project_picker_content"]) [data-testid="stVerticalBlock"],
div[data-baseweb="popover"]:has([class*="st-key-project_picker_content"]) [data-testid="stLayoutWrapper"] {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    box-sizing: border-box !important;
}
div[data-baseweb="popover"]:has([class*="st-key-project_picker_content"]) [data-testid="stPopoverBody"] {
    width: 100% !important;
    min-width: 0 !important;
    max-width: 100% !important;
    max-height: 68vh !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
    padding: 0.65rem 0.75rem 0.75rem !important;
    box-sizing: border-box !important;
}

[class*="st-key-project_picker_content"] {
    width: 100% !important;
    min-width: 0 !important;
    box-sizing: border-box !important;
}

/* Projektek dialógus — picker tartalom */
[data-testid="stDialog"] [class*="st-key-project_picker_content"],
div[role="dialog"] [class*="st-key-project_picker_content"] {
    width: 100% !important;
    min-width: 0 !important;
    box-sizing: border-box !important;
}
[data-testid="stDialog"] [class*="st-key-project_picker_row_"],
div[role="dialog"] [class*="st-key-project_picker_row_"] {
    width: 100% !important;
    min-width: 0 !important;
    margin: 0 0 0.55rem !important;
    padding: 0.55rem 0.65rem !important;
    box-sizing: border-box !important;
}

/* Legacy: elavult popover-dismiss jelölő (ha még a DOM-ban van) */
div[data-baseweb="popover"][data-tx-projects-dismissed="1"] {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
    opacity: 0 !important;
}

.tx-project-picker-title {
    font-size: 0.95rem;
    font-weight: 650;
    color: var(--ui-text);
    margin: 0 0 0.55rem;
}

div[data-baseweb="popover"]:has([class*="st-key-project_picker_content"]) [class*="st-key-project_picker_row_"] {
    width: 100% !important;
    min-width: 0 !important;
    margin: 0 0 0.55rem !important;
    padding: 0.55rem 0.65rem !important;
    box-sizing: border-box !important;
}

.tx-project-row-name {
    font-size: 0.92rem;
    font-weight: 650;
    color: var(--ui-text);
    line-height: 1.35;
    max-width: 100%;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    word-break: normal;
    overflow-wrap: break-word;
    min-width: 0;
}

.tx-project-current-badge {
    display: inline-flex;
    align-items: center;
    margin-left: 0.4rem;
    padding: 0.05rem 0.45rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 650;
    border: 1px solid rgba(90, 122, 168, 0.35);
    background: rgba(90, 122, 168, 0.12);
    color: #1f334d;
    white-space: nowrap;
    vertical-align: middle;
}

.tx-project-row-meta {
    margin: 0.2rem 0 0.45rem;
    font-size: 0.8rem;
    color: var(--ui-text-muted);
    line-height: 1.35;
    word-break: normal;
    overflow-wrap: break-word;
    min-width: 0;
}

[class*="st-key-project_picker_content"] .stButton > button {
    position: relative !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.35rem !important;
    text-align: center !important;
    min-height: 38px !important;
    height: 38px !important;
    width: auto !important;
    border-radius: 10px !important;
    border: 1px solid var(--ui-border) !important;
    background: rgba(255, 253, 249, 0.98) !important;
    box-shadow: none !important;
    white-space: nowrap !important;
    font-weight: 600 !important;
    color: var(--tx-primary-deep) !important;
    padding: 0 0.85rem !important;
    margin: 0 !important;
}
[class*="st-key-project_picker_content"] .stButton > button::before {
    content: none !important;
    display: none !important;
}
[class*="st-key-project_picker_content"] .stButton > button [data-testid="stIconMaterial"] {
    position: static !important;
    background: transparent !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    width: auto !important;
    height: auto !important;
    margin-right: 0 !important;
    font-size: 1rem !important;
    line-height: 1 !important;
}
[class*="st-key-project_picker_content"] .stButton > button [data-testid="stMarkdownContainer"] p {
    display: block !important;
    margin: 0 !important;
    width: auto !important;
}
[class*="st-key-project_picker_content"] .stButton > button [data-testid="stMarkdownContainer"] p span {
    flex: none !important;
    width: auto !important;
    min-width: 0 !important;
    text-align: inherit !important;
    color: inherit !important;
    font-size: inherit !important;
    font-weight: inherit !important;
    white-space: nowrap !important;
}

[class*="st-key-project_picker_content"] [class*="st-key-bar_project_open_"] button {
    min-width: 96px !important;
}
[class*="st-key-project_picker_content"] [class*="st-key-bar_project_delete_"] button {
    min-width: 80px !important;
}

@media (max-width: 1023px) {
    .st-key-textus_app_toolbar > div,
    .st-key-textus_app_toolbar[data-testid="stHorizontalBlock"],
    .st-key-tx_toolbar_main > div,
    .st-key-tx_toolbar_actions > div {
        flex-wrap: nowrap !important;
    }
    .st-key-tx_toolbar_flex,
    .st-key-textus_app_toolbar > [data-testid="stLayoutWrapper"]:has(.st-key-tx_toolbar_flex) {
        display: none !important;
        min-width: 0 !important;
        flex: 0 0 0 !important;
    }
    .st-key-textus_app_toolbar > [data-testid="stLayoutWrapper"]:has(.st-key-tx_toolbar_actions) {
        margin-left: auto !important;
    }
    .tx-project-name-text {
        max-width: min(160px, 48vw);
    }
    .tx-project-name-row {
        max-width: min(200px, 58vw);
        gap: 6px;
    }
    /* Mentve / Ideiglenes → színes pont, több hely a címnek */
    .tx-project-status-chip {
        font-size: 0 !important;
        line-height: 0 !important;
        width: 10px !important;
        height: 10px !important;
        min-width: 10px !important;
        padding: 0 !important;
        border-radius: 50% !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_new_work button {
        min-width: 40px !important;
        width: 40px !important;
        padding: 0 !important;
        justify-content: center !important;
        font-size: 0 !important;
        gap: 0 !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_new_work button [data-testid="stIconMaterial"] {
        font-size: 1.25rem !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_new_work button [data-testid="stMarkdownContainer"] {
        display: none !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_projects_popover,
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"],
    .st-key-textus_app_toolbar .st-key-bar_projects_popover [data-testid="stPopover"],
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] [data-testid="stPopover"],
    .st-key-textus_app_toolbar .st-key-bar_projects_open {
        min-width: 0 !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_projects_popover button,
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] button,
    .st-key-textus_app_toolbar .st-key-bar_projects_open button {
        min-width: 40px !important;
        width: 40px !important;
        max-width: 44px !important;
        padding: 0 !important;
        justify-content: center !important;
        gap: 0 !important;
        font-size: 0 !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_projects_popover button [data-testid="stIconMaterial"],
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] button [data-testid="stIconMaterial"],
    .st-key-textus_app_toolbar .st-key-bar_projects_open button [data-testid="stIconMaterial"] {
        font-size: 1.25rem !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_projects_popover button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar .st-key-bar_projects_open button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar .st-key-bar_projects_popover button svg,
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] button svg,
    .st-key-textus_app_toolbar .st-key-bar_projects_open button svg {
        display: none !important;
    }
    .tx-appbar-guest-label {
        display: none !important;
    }
}

@media (max-width: 759px) {
    .st-key-textus_app_toolbar > div,
    .st-key-textus_app_toolbar[data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        row-gap: 8px !important;
        align-items: stretch !important;
    }
    .st-key-textus_app_toolbar > [data-testid="stLayoutWrapper"]:has(.st-key-tx_toolbar_main),
    .st-key-tx_toolbar_main {
        flex: 1 1 100% !important;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
    }
    .st-key-textus_app_toolbar > [data-testid="stLayoutWrapper"]:has(.st-key-tx_toolbar_actions),
    .st-key-tx_toolbar_actions {
        flex: 1 1 100% !important;
        width: 100% !important;
        max-width: 100% !important;
        margin-left: 0 !important;
        min-width: 0 !important;
    }
    .st-key-tx_toolbar_main,
    .st-key-tx_toolbar_actions,
    .st-key-tx_toolbar_main[data-testid="stHorizontalBlock"],
    .st-key-tx_toolbar_actions[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        overflow-x: visible !important;
        width: 100% !important;
        max-width: 100% !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_new_work,
    .st-key-textus_app_toolbar .st-key-tx_appbar_settings,
    .st-key-textus_app_toolbar .st-key-bar_save_more_popover {
        display: none !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_overflow_more {
        display: flex !important;
        align-items: center !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_project_save button,
    .st-key-textus_app_toolbar .st-key-bar_project_save_as_new button,
    .st-key-textus_app_toolbar .st-key-bar_projects_popover button,
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] button,
    .st-key-textus_app_toolbar .st-key-bar_projects_open button,
    .st-key-textus_app_toolbar .st-key-bar_overflow_more button,
    .st-key-textus_app_toolbar .st-key-tx_appbar_login_popover button,
    .st-key-textus_app_toolbar .st-key-tx_appbar_account_popover button {
        min-width: 40px !important;
        width: 40px !important;
        max-width: 44px !important;
        padding: 0 !important;
        justify-content: center !important;
        gap: 0 !important;
        font-size: 0 !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_project_save button [data-testid="stIconMaterial"],
    .st-key-textus_app_toolbar .st-key-bar_project_save_as_new button [data-testid="stIconMaterial"],
    .st-key-textus_app_toolbar .st-key-bar_projects_popover button [data-testid="stIconMaterial"],
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] button [data-testid="stIconMaterial"],
    .st-key-textus_app_toolbar .st-key-bar_projects_open button [data-testid="stIconMaterial"],
    .st-key-textus_app_toolbar .st-key-bar_overflow_more button [data-testid="stIconMaterial"],
    .st-key-textus_app_toolbar .st-key-tx_appbar_login_popover button [data-testid="stIconMaterial"],
    .st-key-textus_app_toolbar .st-key-tx_appbar_account_popover button [data-testid="stIconMaterial"] {
        font-size: 1.25rem !important;
        line-height: 1 !important;
    }
    .st-key-textus_app_toolbar .st-key-bar_project_save button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar .st-key-bar_project_save_as_new button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar .st-key-bar_projects_popover button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar .st-key-bar_projects_open button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar .st-key-bar_overflow_more button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar .st-key-tx_appbar_login_popover button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar .st-key-tx_appbar_account_popover button [data-testid="stMarkdownContainer"],
    .st-key-textus_app_toolbar .st-key-bar_projects_popover button svg,
    .st-key-textus_app_toolbar [class*="st-key-bar_projects_popover_"] button svg,
    .st-key-textus_app_toolbar .st-key-bar_projects_open button svg,
    .st-key-textus_app_toolbar .st-key-bar_overflow_more button svg,
    .st-key-textus_app_toolbar .st-key-tx_appbar_login_popover button svg,
    .st-key-textus_app_toolbar .st-key-tx_appbar_account_popover button svg {
        display: none !important;
    }
    .tx-project-name-text {
        max-width: min(140px, 42vw);
    }
    .st-key-tx_toolbar_main [data-testid="stElementContainer"]:has(.tx-project-name-row) {
        max-width: min(200px, 58vw) !important;
    }
}

@media (max-width: 390px) {
    .st-key-textus_app_toolbar {
        padding: 6px 8px !important;
    }
    .tx-project-name-text {
        max-width: min(110px, 36vw);
    }
    div[data-baseweb="popover"]:has([class*="st-key-project_picker_content"]) {
        width: calc(100vw - 24px) !important;
        min-width: 0 !important;
        max-width: calc(100vw - 24px) !important;
    }
    div[data-baseweb="popover"]:has([class*="st-key-project_picker_content"]) [data-testid="stPopoverBody"] {
        width: 100% !important;
        min-width: 0 !important;
        max-width: 100% !important;
    }
}
/* Segmented nav: Streamlit piros indikátor kiütése (theme primary mellett is) */
[data-testid="stSegmentedControl"] button {
    outline: none !important;
}
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
    color: #1f334d !important;
}

/* ===== Központi lépésválasztó (StepSelector) — scoped workshop_step_bar ===== */
/* tx-stepbar-v2-marker */
.tx-stepselect-anchor { display: none !important; height: 0 !important; margin: 0 !important; }

.st-key-workshop_step_bar {
    max-width: 780px !important;
    margin-left: auto !important;
    margin-right: auto !important;
    width: 100% !important;
}

/* Zárt vezérlő — NINCS child combinator (>) : a Streamlit HTML sanitizer azt kiszűri.
   display:contents a belső emotion wrappereken → badge | markdown | chevron egy flex sor. */
.st-key-workshop_step_bar [data-testid="stPopoverButton"] {
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    gap: 0.35rem !important;
    text-align: left !important;
    min-height: 60px !important;
    height: auto !important;
    border-radius: 12px !important;
    border: 1px solid rgba(170, 145, 112, 0.28) !important;
    background: rgba(255, 253, 249, 0.97) !important;
    box-shadow: 0 1px 3px rgba(58, 40, 22, 0.06) !important;
    color: var(--tx-primary-deep) !important;
    font-family: "Inter", "Segoe UI", sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.97rem !important;
    padding: 0.55rem 0.85rem 0.55rem 0.7rem !important;
    transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease !important;
}
.st-key-workshop_step_bar [data-testid="stPopoverButton"] div {
    display: contents !important;
}
.st-key-workshop_step_bar [data-testid="stPopoverButton"]:hover {
    background: rgba(255, 252, 247, 1) !important;
    border-color: rgba(90, 122, 168, 0.38) !important;
    box-shadow: 0 1px 4px rgba(58, 40, 22, 0.08) !important;
}
.st-key-workshop_step_bar [data-testid="stPopoverButton"]:focus-visible {
    outline: 2px solid var(--tx-primary) !important;
    outline-offset: 2px !important;
    box-shadow: 0 0 0 3px rgba(90, 122, 168, 0.18) !important;
}
/* Nyitott: a lépéslista fejlécét nézzük (:has), nem tetszőleges popover-t */
body:has([data-testid="stPopoverBody"] .tx-stepmenu-head) .st-key-workshop_step_bar [data-testid="stPopoverButton"] {
    background: rgba(90, 122, 168, 0.08) !important;
    border-color: rgba(90, 122, 168, 0.36) !important;
    box-shadow: inset 3px 0 0 0 var(--tx-primary), 0 1px 3px rgba(58, 40, 22, 0.05) !important;
}
/* Számjelvény (bal) */
.st-key-workshop_step_bar [data-testid="stPopoverButton"]::before {
    content: var(--tx-step-num, "1");
    flex: 0 0 auto;
    display: inline-flex !important;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    min-width: 28px;
    margin-right: 0.45rem;
    border-radius: 999px;
    background: rgba(90, 122, 168, 0.12);
    color: var(--tx-primary-deep);
    font-size: 0.82rem;
    font-weight: 650;
    line-height: 1;
}
body:has([data-testid="stPopoverBody"] .tx-stepmenu-head) .st-key-workshop_step_bar [data-testid="stPopoverButton"]::before {
    background: rgba(90, 122, 168, 0.2);
}
/* Címke: név balra, státusz jobbra — kitölti a középső sávot */
.st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"] {
    display: block !important;
    flex: 1 1 auto !important;
    min-width: 0 !important;
    width: auto !important;
    max-width: none !important;
}
.st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"] p {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 0.75rem !important;
    width: 100% !important;
    margin: 0 !important;
    line-height: 1.3 !important;
}
.st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"] p strong {
    flex: 1 1 auto !important;
    min-width: 0 !important;
    font-size: 15.5px !important;
    font-weight: 600 !important;
    color: var(--tx-primary-deep) !important;
    display: -webkit-box !important;
    -webkit-box-orient: vertical !important;
    -webkit-line-clamp: 2 !important;
    overflow: hidden !important;
}
.st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"] p span {
    flex: 0 0 auto !important;
    color: var(--tx-text-muted) !important;
    font-weight: 500 !important;
    font-size: 0.8rem !important;
    white-space: nowrap !important;
    line-height: 1.25 !important;
}
/* Egyetlen chevron */
.st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stIconMaterial"] {
    display: none !important;
}
.st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stIconMaterial"]:last-of-type {
    display: inline-flex !important;
    flex: 0 0 auto !important;
    margin-left: 0.15rem !important;
    color: #5a7aa8 !important;
    font-size: 1.2rem !important;
    transition: transform 0.18s ease !important;
}
body:has([data-testid="stPopoverBody"] .tx-stepmenu-head) .st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stIconMaterial"]:last-of-type {
    transform: rotate(180deg) !important;
}
.st-key-workshop_step_bar [data-testid="stPopoverButton"] svg:not([data-testid="stIconMaterial"] svg) {
    display: none !important;
}

/* Progress sáv közvetlenül a zárt trigger alatt */
.st-key-workshop_step_bar .tx-stepbar-track {
    margin: 3px 2px 0;
    padding: 0;
}
.st-key-workshop_step_bar .tx-stepbar-track .tx-wf-progress {
    height: 3px;
    background: rgba(160, 150, 135, 0.22);
    border-radius: 999px;
    overflow: hidden;
}
.st-key-workshop_step_bar .tx-stepbar-track .tx-wf-progress-fill {
    height: 100%;
    background: var(--tx-primary, #5a7aa8);
    border-radius: 999px;
    transition: width 0.3s ease;
}

/* ===== Lenyíló panel — összegző fejléc (görgetéskor ragadós) ===== */
.tx-stepmenu-head {
    font-family: "Inter", "Segoe UI", sans-serif;
    position: sticky;
    top: 0;
    z-index: 2;
    margin: 0 0 0.4rem;
    padding: 0.35rem 0.15rem 0.55rem;
    border-bottom: 1px solid var(--tx-border);
    background: rgba(253, 251, 247, 0.97);
}
.tx-stepmenu-title {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--tx-gold);
}
.tx-stepmenu-sub {
    font-size: 0.8rem;
    color: var(--tx-text-muted);
    margin: 0.15rem 0 0.4rem;
}
.tx-stepmenu-head .tx-wf-progress { margin: 0; }

/* ===== Idővonal sorok — kompakt, teljes szélességű flex (ikon | név | állapot) ===== */
[data-testid="stPopover"] .stButton > button,
div[data-baseweb="popover"] .stButton > button {
    position: relative !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    gap: 0.45rem !important;
    text-align: left !important;
    min-height: 48px !important;
    height: auto !important;
    border-radius: 10px !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    box-shadow: none !important;
    white-space: normal !important;
    font-weight: 500 !important;
    color: #3d3228 !important;
    padding: 0.25rem 0.5rem !important;
    margin: 0.1rem 0 !important;
    width: 100% !important;
}
/* Vékony függőleges összekötő vonal a státuszkör mögött (szín lépésenként). */
[data-testid="stPopover"] .stButton > button::before,
div[data-baseweb="popover"] .stButton > button::before {
    content: "";
    position: absolute;
    left: 1.34rem;
    top: 0;
    bottom: 0;
    width: 2px;
    background: rgba(160, 150, 135, 0.45);
    z-index: 0;
}
[data-testid="stPopover"] .stButton > button:hover,
div[data-baseweb="popover"] .stButton > button:hover {
    background: rgba(90, 122, 168, 0.07) !important;
    border-color: transparent !important;
}
/* Aktív sor: halvány kék háttér, finom keret, kissé erősebb betű. */
[data-testid="stPopover"] .stButton > button[kind="primary"],
div[data-baseweb="popover"] .stButton > button[kind="primary"] {
    background: rgba(90, 122, 168, 0.12) !important;
    border-color: rgba(90, 122, 168, 0.3) !important;
    color: #1f334d !important;
    font-weight: 650 !important;
}
/* Státuszkör (material ikon) mint idővonal-csomópont; korong maszkolja a vonalat. */
[data-testid="stPopover"] .stButton > button [data-testid="stIconMaterial"],
div[data-baseweb="popover"] .stButton > button [data-testid="stIconMaterial"] {
    position: relative !important;
    z-index: 1 !important;
    order: 0 !important;
    flex: 0 0 auto !important;
    margin-right: 0.6rem !important;
    font-size: 1.35rem !important;
    width: 1.65rem !important;
    height: 1.65rem !important;
    line-height: 1.65rem !important;
    text-align: center !important;
    background: #fdfbf7 !important;
    border-radius: 50% !important;
    color: #9c9384;
    box-sizing: border-box !important;
}
/* Aktív csomópont: erősebb kék + finom külső gyűrű. */
[data-testid="stPopover"] .stButton > button[kind="primary"] [data-testid="stIconMaterial"],
div[data-baseweb="popover"] .stButton > button[kind="primary"] [data-testid="stIconMaterial"] {
    color: #3f6699 !important;
    box-shadow: 0 0 0 3px rgba(90, 122, 168, 0.28) !important;
}
/* Címke konténere és belső flex: szám + név balra, állapot jobbra. */
[data-testid="stPopover"] .stButton > button [data-testid="stMarkdownContainer"],
div[data-baseweb="popover"] .stButton > button [data-testid="stMarkdownContainer"] {
    order: 1 !important;
    flex: 1 1 auto !important;
    min-width: 0 !important;
    position: relative;
    z-index: 1;
}
[data-testid="stPopover"] .stButton > button [data-testid="stMarkdownContainer"] p,
div[data-baseweb="popover"] .stButton > button [data-testid="stMarkdownContainer"] p {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 0.6rem !important;
    width: 100% !important;
    margin: 0 !important;
}
/* Jobb oldali, minden soron azonos pozíciójú, visszafogott állapotszöveg. */
[data-testid="stPopover"] .stButton > button [data-testid="stMarkdownContainer"] p span,
div[data-baseweb="popover"] .stButton > button [data-testid="stMarkdownContainer"] p span {
    flex: 0 0 110px !important;
    width: 110px !important;
    min-width: 110px !important;
    text-align: right !important;
    color: var(--tx-text-muted) !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    white-space: nowrap !important;
}
/* Hosszú munkafolyamat: panelmagasság + belső görgetés, triggerhez igazított szélesség. */
div[data-baseweb="popover"] [data-testid="stPopoverBody"] {
    max-height: min(70vh, 540px) !important;
    overflow-y: auto !important;
    width: min(780px, 92vw) !important;
    padding: 0.35rem 0.55rem 0.5rem 0.35rem !important;
    background: rgba(253, 251, 247, 0.98) !important;
    border: 1px solid rgba(186, 158, 122, 0.35) !important;
    border-radius: 14px !important;
    box-shadow: 0 10px 28px rgba(58, 40, 22, 0.1) !important;
}
div[data-baseweb="popover"] [data-testid="stPopoverBody"]::-webkit-scrollbar {
    width: 8px;
}
div[data-baseweb="popover"] [data-testid="stPopoverBody"]::-webkit-scrollbar-thumb {
    background: rgba(160, 140, 115, 0.35);
    border-radius: 999px;
}
/* Nyitási animáció — mozgáscsökkentés esetén kikapcsol. */
@media (prefers-reduced-motion: no-preference) {
    div[data-baseweb="popover"] [data-testid="stPopoverBody"] {
        animation: tx-stepmenu-in 180ms ease both;
    }
}
@keyframes tx-stepmenu-in {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* ===== Haladás (legacy / menüfej) ===== */
.tx-progress-wrap { margin: 0.5rem 0 0.4rem; }
.tx-progress-info {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    flex-wrap: wrap;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.78rem;
    color: var(--tx-text-muted);
    margin-bottom: 0.3rem;
}
.tx-wf-progress {
    height: 4px;
    width: 100%;
    background: rgba(160, 140, 115, 0.22);
    border-radius: 999px;
    overflow: hidden;
}
.tx-wf-progress-fill {
    height: 100%;
    background: var(--tx-primary, #5a7aa8);
    border-radius: 999px;
    transition: width 0.3s ease;
}

/* ===== ContextSummary — kompakt kontextussor ===== */
.tx-context {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 1.1rem;
    align-items: baseline;
    padding: 10px 14px;
    margin: var(--tx-space-2) 0 var(--tx-space-3);
    border: 1px solid rgba(170, 145, 112, 0.18);
    border-radius: var(--tx-radius-sm);
    background: rgba(255, 252, 247, 0.55);
    font-family: "Inter", "Segoe UI", sans-serif;
}
.tx-context-item { font-size: 0.84rem; color: #3d3228; }
.tx-context-item .k { color: var(--tx-text-muted); margin-right: 0.3rem; font-weight: 500; }
.tx-context-item .v { font-weight: 600; color: var(--tx-primary-deep); }

/* ===== Munkaterület keret — nem egy folyamatos fehér dokumentumkártya ===== */
.tx-workcard-anchor { display: none !important; height: 0 !important; margin: 0 !important; }
.element-container:has(.tx-workcard-anchor) + [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"],
.element-container:has(.tx-workcard-anchor) + [data-testid="stLayoutWrapper"] [data-testid="stVerticalBlockBorderWrapper"] {
    max-width: 1040px !important;
    margin: var(--tx-space-3) auto 0 !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
}

/* ===== 1. Munkaszakasz — kompakt cím + magyarázat, NEM teljes kártya ===== */
.tx-work-section {
    margin: 0 0 var(--tx-space-2);
    padding: 0;
    max-width: 100%;
}
.tx-work-section-context {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--tx-gold);
    margin: 0 0 4px;
}
.tx-work-section-lead {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    column-gap: 0.75rem;
    row-gap: 0.1rem;
}
.tx-work-section-title {
    font-family: "Playfair Display", "Cormorant Garamond", Georgia, serif;
    font-size: clamp(17px, 1.65vw, 20px);
    font-weight: 650;
    line-height: 1.2;
    margin: 0;
    color: #2a2117;
    flex: 0 0 auto;
}
.tx-work-section-body {
    margin: 0;
    font-family: "Lora", Georgia, serif;
    font-size: 0.82rem;
    line-height: 1.35;
    color: var(--tx-text-muted);
    flex: 1 1 14rem;
    max-width: min(36rem, 100%);
}
.tx-work-section-rule {
    display: none !important;
    margin: 0 !important;
    height: 0 !important;
    border: 0 !important;
    background: none !important;
}

/* ===== 2. Munkafelület — egy feladat = egy emelt panel ===== */
[class*="st-key-tx_work_surface"] {
    background: var(--tx-work-surface) !important;
    border: 1px solid rgba(170, 145, 112, 0.24) !important;
    border-radius: var(--tx-radius-surface) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.78) inset,
        0 6px 16px rgba(58, 40, 22, 0.06) !important;
    padding: 12px 16px !important;
    margin: 0 0 16px !important;
}
[class*="st-key-tx_work_surface"] > div {
    gap: 10px !important;
}

/* Tipográfia a munkafelületen: címke / mező / meta */
[class*="st-key-tx_work_surface"] [data-testid="stWidgetLabel"] p,
[class*="st-key-tx_work_surface"] label p {
    font-family: "Inter", "Segoe UI", sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    color: #3a3229 !important;
}
[class*="st-key-tx_work_surface"] [data-testid="stCaption"] p,
[class*="st-key-tx_work_surface"] [data-testid="stCaptionContainer"] p {
    font-family: "Inter", "Segoe UI", sans-serif !important;
    font-size: 0.8rem !important;
    color: var(--tx-text-muted) !important;
    max-width: var(--tx-prose-width);
}
[class*="st-key-tx_work_surface"] [data-testid="stMarkdown"] p,
[class*="st-key-tx_work_surface"] [data-testid="stMarkdownContainer"] p {
    max-width: var(--tx-prose-width);
}

/* ===== 3. Helper / MI-zóna — halk, nem kártyarakás ===== */
[class*="st-key-tx_mi_helper"] {
    background: var(--tx-helper-bg) !important;
    border: 1px solid rgba(90, 122, 168, 0.16) !important;
    border-left: 3px solid rgba(90, 122, 168, 0.45) !important;
    border-radius: 0 var(--tx-radius-sm) var(--tx-radius-sm) 0 !important;
    box-shadow: none !important;
    padding: var(--tx-space-3) var(--tx-space-4) !important;
    margin: var(--tx-space-4) 0 var(--tx-space-3) !important;
}
[class*="st-key-tx_mi_helper"] .tx-mi-title {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.84rem;
    font-weight: 650;
    color: var(--tx-primary-deep);
    margin: 0 0 4px;
}
[class*="st-key-tx_mi_helper"] .tx-mi-body {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 0.82rem;
    line-height: 1.45;
    color: var(--tx-text-muted);
    margin: 0 0 var(--tx-space-3);
    max-width: var(--tx-prose-width);
}

/* Műveleti sor — gombok a munkafelület alján, nem lebegve */
[class*="st-key-tx_action_row"] {
    margin-top: var(--tx-space-3) !important;
    padding-top: var(--tx-space-3) !important;
    border-top: 1px solid rgba(170, 145, 112, 0.14) !important;
}
[class*="st-key-tx_action_row"] [data-testid="stHorizontalBlock"] {
    gap: var(--tx-space-3) !important;
    align-items: stretch !important;
}
[class*="st-key-tx_mi_helper"] [data-testid="stHorizontalBlock"] {
    gap: var(--tx-space-3) !important;
}

@media (max-width: 640px) {
    [class*="st-key-tx_action_row"] [data-testid="stHorizontalBlock"],
    [class*="st-key-tx_mi_helper"] [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: var(--tx-space-2) !important;
    }
    [class*="st-key-tx_action_row"] [data-testid="stColumn"],
    [class*="st-key-tx_mi_helper"] [data-testid="stColumn"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
    [class*="st-key-tx_work_surface"] {
        padding: var(--tx-space-3) !important;
        border-radius: 10px !important;
    }
}

/* Magyarázó próza olvasási szélesség.
   A .result-box a KÁRTYA (háttér/keret/árnyék) — ez töltse ki a
   .main-card rendelkezésre álló szélességét. Az olvashatóságot a
   benne lévő bekezdések biztosítják (`.stMarkdown p { max-width: 78ch }`,
   app.py ~1071), mivel a .result-box tartalma mindig egy .stMarkdown
   wrapperbe ágyazva jelenik meg — nem a kártya-konténerre kell rátenni
   a sor-hossz limitet, mert az feleslegesen szűkíti a teljes kártyát. */
.tx-prose {
    max-width: var(--tx-prose-width);
}
.tx-prose p,
.tx-intro-body,
.tx-work-section-body {
    max-width: var(--tx-prose-width);
}

/* Kék csak aktív / fókusz / elsődleges — ne minden keret */
[class*="st-key-tx_work_surface"] [data-baseweb="input"] > div,
[class*="st-key-tx_work_surface"] [data-baseweb="textarea"] > div,
[class*="st-key-tx_work_surface"] [data-baseweb="select"] > div {
    border-color: rgba(170, 145, 112, 0.28) !important;
}
[class*="st-key-tx_work_surface"] [data-baseweb="input"] > div:focus-within,
[class*="st-key-tx_work_surface"] [data-baseweb="textarea"] > div:focus-within,
[class*="st-key-tx_work_surface"] [data-baseweb="select"] > div:focus-within {
    border-color: rgba(90, 122, 168, 0.55) !important;
    box-shadow: 0 0 0 1px rgba(90, 122, 168, 0.22) !important;
}

/* ===== Workspace switcher — kompakt, címke-only szegmensek ===== */
.st-key-workspace_switcher {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 0 14px !important;
    padding: 0 !important;
    gap: 0 !important;
    row-gap: 0 !important;
}

.st-key-workspace_switcher [data-testid="stHorizontalBlock"] {
    display: grid !important;
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    gap: 4px !important;
    margin: 0 !important;
    align-items: stretch !important;
    min-height: 50px !important;
    box-sizing: border-box !important;
    width: 100% !important;
    max-width: 100% !important;
    background:
        linear-gradient(
            180deg,
            rgba(255, 253, 248, 0.96) 0%,
            rgba(244, 235, 220, 0.9) 100%
        ) !important;
    border: 1px solid rgba(170, 145, 112, 0.34) !important;
    border-radius: var(--ui-radius-md) !important;
    padding: 5px !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.88) inset,
        0 8px 18px rgba(58, 40, 22, 0.08) !important;
}

.st-key-workspace_switcher [data-testid="stColumn"] {
    display: flex !important;
    align-items: stretch !important;
    width: 100% !important;
    max-width: none !important;
    min-width: 0 !important;
    flex: unset !important;
}

.st-key-workspace_switcher .stButton {
    width: 100% !important;
    height: 100% !important;
    margin: 0 !important;
    display: block !important;
}

.st-key-workspace_switcher .stButton > div,
.st-key-workspace_switcher .stButton .stTooltipIcon,
.st-key-workspace_switcher .stButton .stTooltipHoverTarget,
.st-key-workspace_switcher .stButton [class*="TooltipHoverTarget"] {
    width: 100% !important;
    max-width: 100% !important;
    display: block !important;
    box-sizing: border-box !important;
}

/* Tooltip/help másodpéldány ne jelenjen meg külön fülként */
.st-key-workspace_switcher .stButton > *:not(:first-child),
.st-key-workspace_switcher .stButton button [data-testid="stMarkdownContainer"] ~ * {
    display: none !important;
}

.st-key-workspace_switcher .stButton button {
    position: relative !important;
    width: 100% !important;
    max-width: 100% !important;
    flex: 1 1 auto !important;
    align-self: stretch !important;
    height: 100% !important;
    min-height: 46px !important;
    max-height: 50px !important;
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    padding: 0 0.65rem !important;
    border-radius: var(--ui-radius-sm) !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    box-shadow: none !important;
    color: var(--ui-text) !important;
    cursor: pointer !important;
    transition:
        background 170ms ease,
        border-color 170ms ease,
        box-shadow 170ms ease,
        color 170ms ease,
        transform 170ms ease !important;
    transform: none !important;
}

.st-key-workspace_switcher .stButton button [data-testid="stMarkdownContainer"] {
    flex: 0 1 auto !important;
    min-width: 0 !important;
}

.st-key-workspace_switcher .stButton button [data-testid="stMarkdownContainer"] p {
    margin: 0 !important;
    display: block !important;
    font-family: "Inter", "Segoe UI", sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    line-height: 1.2 !important;
    letter-spacing: 0.01em !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    color: inherit !important;
    text-align: center !important;
}

.st-key-workspace_switcher .stButton button [data-testid="stIconMaterial"] {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    flex-shrink: 0 !important;
    width: 18px !important;
    height: 18px !important;
    min-width: 18px !important;
    min-height: 18px !important;
    border-radius: 0 !important;
    font-size: 17px !important;
    line-height: 1 !important;
    color: var(--ui-accent) !important;
    background: transparent !important;
    transition: color 170ms ease !important;
}

.st-key-workspace_switcher .stButton button:hover {
    background:
        linear-gradient(
            180deg,
            rgba(255, 254, 250, 0.9) 0%,
            rgba(232, 238, 247, 0.72) 100%
        ) !important;
    border-color: rgba(90, 122, 168, 0.28) !important;
    color: var(--tx-primary-deep) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 10px rgba(52, 72, 98, 0.1) !important;
}

.st-key-workspace_switcher .stButton button:active {
    transform: translateY(0) !important;
}

.st-key-workspace_switcher .stButton button::after {
    content: "" !important;
    display: block !important;
    position: absolute !important;
    left: 12px !important;
    right: 12px !important;
    bottom: 0 !important;
    height: 0 !important;
    background: var(--ui-accent) !important;
    border-radius: 2px 2px 0 0 !important;
    transition: height 170ms ease !important;
    pointer-events: none !important;
}

.st-key-workspace_switcher .stButton button:focus-visible {
    outline: 2px solid rgba(90, 122, 168, 0.5) !important;
    outline-offset: 2px !important;
}

/* ===== Workspace page intro — kompakt cím + egy mondat ===== */
.st-key-workspace_intro {
    margin: 0 0 8px !important;
    padding: 0 !important;
}

.st-key-workspace_intro .tx-page-intro {
    margin: 0 !important;
    padding: 0 !important;
}

.st-key-workspace_intro .tx-intro-eyebrow {
    display: none !important;
}

.st-key-workspace_intro .tx-intro-title {
    font-family: "Playfair Display", "Cormorant Garamond", Georgia, serif !important;
    font-size: 26px !important;
    font-weight: 650 !important;
    line-height: 1.15 !important;
    margin: 0 !important;
    color: #2a2117 !important;
}

.st-key-workspace_intro .tx-intro-body {
    margin-top: 4px !important;
    margin-bottom: 0 !important;
    font-family: "Lora", Georgia, serif !important;
    font-size: 0.92rem !important;
    line-height: 1.35 !important;
    color: var(--tx-text-muted) !important;
    max-width: 640px !important;
}

/* spacing handled above (.st-key-workspace_intro ~ .st-key-quick_tools_grid) */

@media (max-width: 768px) {
    .st-key-workspace_switcher [data-testid="stHorizontalBlock"] {
        grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
        gap: 2px !important;
        padding: 3px !important;
    }
    .st-key-workspace_switcher .stButton button {
        min-height: 44px !important;
        max-height: 48px !important;
        gap: 6px !important;
        padding: 0 0.35rem !important;
    }
    .st-key-workspace_switcher .stButton button [data-testid="stMarkdownContainer"] p {
        font-size: 0.72rem !important;
    }
    .st-key-workspace_intro .tx-intro-title {
        font-size: 26px !important;
    }
    .st-key-workspace_intro .tx-intro-body {
        font-size: 14.5px !important;
    }
}

@media (max-width: 390px) {
    .st-key-workspace_switcher .stButton button [data-testid="stMarkdownContainer"] p {
        font-size: 0.68rem !important;
    }
    .st-key-workspace_intro {
        margin-bottom: 20px !important;
    }
}

@media (prefers-reduced-motion: reduce) {
    .st-key-workspace_switcher .stButton button {
        transition: none !important;
    }
}

/* ===== Imádság — gyors MI-sáv (munkakártyán belül) ===== */
.tx-prayer-quick {
    background: rgba(214, 228, 240, 0.42);
    border: 1px solid rgba(90, 130, 168, 0.28);
    border-radius: 12px;
    padding: 0.7rem 0.85rem 0.75rem;
    margin: 0.15rem 0 0.55rem;
}
.tx-prayer-quick-title {
    font-size: 0.95rem;
    font-weight: 650;
    color: #1f334d;
    margin: 0 0 0.25rem;
}
.tx-prayer-quick-help {
    margin: 0;
    font-size: 0.84rem;
    line-height: 1.45;
    color: #3d4f66;
}
.tx-prayer-or {
    margin: 0.55rem 0 0.65rem;
    text-align: center;
    font-size: 0.82rem;
    color: var(--tx-text-muted, #6b5e52);
    letter-spacing: 0.01em;
}

@media (max-width: 768px) {
    .st-key-workshop_step_bar {
        max-width: 100% !important;
    }
    .st-key-workshop_step_bar [data-testid="stPopoverButton"] {
        min-height: 52px !important;
        padding: 0.5rem 0.65rem 0.5rem 0.55rem !important;
        gap: 0.25rem !important;
    }
    .st-key-workshop_step_bar [data-testid="stPopoverButton"]::before {
        width: 26px;
        height: 26px;
        min-width: 26px;
        margin-right: 0.35rem;
        font-size: 0.78rem;
    }
    /* Státusz a cím alá; rövidített szöveg CSS-változóból */
    .st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"] p {
        flex-direction: column !important;
        align-items: flex-start !important;
        justify-content: center !important;
        gap: 0.12rem !important;
    }
    .st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"] p strong {
        font-size: 14.5px !important;
        width: 100% !important;
    }
    .st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"] p span {
        font-size: 0 !important;
        line-height: 0 !important;
        white-space: normal !important;
    }
    .st-key-workshop_step_bar [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"] p span::after {
        content: var(--tx-step-status-short, "");
        font-size: 0.74rem !important;
        font-weight: 500 !important;
        color: var(--tx-text-muted) !important;
        line-height: 1.25 !important;
        white-space: nowrap !important;
    }
    div[data-baseweb="popover"] [data-testid="stPopoverBody"] { width: 94vw !important; }
    /* Az állapotszöveg a cím alá törhet, ha nem fér ki egy sorba. */
    [data-testid="stPopover"] .stButton [data-testid="stMarkdownContainer"] p,
    div[data-baseweb="popover"] .stButton [data-testid="stMarkdownContainer"] p {
        flex-wrap: wrap !important;
    }
    [data-testid="stPopover"] .stButton [data-testid="stMarkdownContainer"] p span,
    div[data-baseweb="popover"] .stButton [data-testid="stMarkdownContainer"] p span {
        flex: 1 1 100% !important;
        width: auto !important;
        min-width: 0 !important;
        text-align: left !important;
    }
    .tx-prayer-quick {
        padding: 0.65rem 0.75rem;
    }
}

/* ===== Hallgatói feszültség — átvételi döntéscsoport =====
   A keyed container maga a stVerticalBlock — közvetlenül sorba rendezzük. */
.st-key-tension_transfer_actions {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: wrap !important;
    align-items: center !important;
    justify-content: flex-start !important;
    gap: 0.35rem 0.45rem !important;
    width: fit-content !important;
    max-width: 100% !important;
    margin: 0.4rem 0 0.1rem !important;
    padding: 0 !important;
}
.st-key-tension_transfer_actions > [data-testid="stElementContainer"] {
    width: auto !important;
    flex: 0 0 auto !important;
    min-width: 0 !important;
}
.st-key-tension_transfer_actions .stButton,
.st-key-tension_transfer_actions [data-testid="stTooltipHoverTarget"] {
    width: auto !important;
}
.st-key-tension_transfer_actions button[data-testid="stBaseButton-primary"],
.st-key-tension_transfer_actions button[data-testid="stBaseButton-secondary"],
.st-key-tension_transfer_actions .stButton > button {
    min-height: 36px !important;
    max-height: 40px !important;
    height: 38px !important;
    padding: 0.3rem 0.85rem !important;
    font-size: 0.875rem !important;
    font-weight: 550 !important;
    line-height: 1.2 !important;
    white-space: nowrap !important;
    width: auto !important;
    border-radius: 8px !important;
}
.st-key-tension_transfer_actions button[data-testid="stBaseButton-primary"] {
    background: rgba(90, 122, 168, 0.16) !important;
    border: 1px solid rgba(90, 122, 168, 0.42) !important;
    color: var(--tx-primary-deep, #1f334d) !important;
    box-shadow: none !important;
}
.st-key-tension_transfer_actions button[data-testid="stBaseButton-primary"]:hover {
    background: rgba(90, 122, 168, 0.24) !important;
    border-color: rgba(90, 122, 168, 0.55) !important;
}
.st-key-tension_transfer_actions button[data-testid="stBaseButton-secondary"] {
    background: rgba(248, 246, 242, 0.92) !important;
    border: 1px solid rgba(170, 145, 112, 0.28) !important;
    color: var(--tx-text, #3a2816) !important;
    padding: 0.28rem 0.7rem !important;
}
.st-key-tension_transfer_actions button[data-testid="stBaseButton-secondary"]:hover {
    background: rgba(232, 238, 247, 0.72) !important;
    border-color: rgba(90, 122, 168, 0.36) !important;
    color: var(--tx-primary-deep, #1f334d) !important;
}
.st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(.tx-tt-sep) {
    display: flex !important;
    align-items: center !important;
    align-self: center !important;
    padding: 0 0.2rem !important;
    margin: 0 !important;
    width: auto !important;
    flex: 0 0 auto !important;
    min-height: 38px !important;
}
.st-key-tension_transfer_actions .tx-tt-sep {
    width: 1px;
    height: 1.4rem;
    background: rgba(90, 122, 168, 0.38);
    margin: 0;
    border-radius: 1px;
}

@media (max-width: 640px) {
    .st-key-tension_transfer_actions {
        width: 100% !important;
        max-width: 100% !important;
        gap: 0.4rem !important;
    }
    .st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-primary"]) {
        flex: 1 1 100% !important;
        width: 100% !important;
    }
    .st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-primary"]) .stButton,
    .st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-primary"]) button {
        width: 100% !important;
    }
    .st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(.tx-tt-sep) {
        display: none !important;
    }
    .st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-secondary"]) {
        flex: 1 1 calc(33.333% - 0.3rem) !important;
        min-width: 5.75rem !important;
        max-width: 100% !important;
    }
    .st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-secondary"]) .stButton,
    .st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-secondary"]) [data-testid="stTooltipHoverTarget"],
    .st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-secondary"]) button {
        width: 100% !important;
    }
    .st-key-tension_transfer_actions > [data-testid="stElementContainer"]:has(button[data-testid="stBaseButton-secondary"]) button {
        padding-left: 0.45rem !important;
        padding-right: 0.45rem !important;
        font-size: 0.82rem !important;
    }
}

/* ===== FINAL UI REFINEMENT — sermon-workshop AI-akciógombok
   (SCOPED, nem globális, 2026-08-21) =====
   Alapból a Streamlit "secondary" gomb háttere teljesen átlátszó, a
   szegélye is csak halványan látszik — a bézs alapszínen ez könnyen
   "beleolvad" a háttérbe. Ez KIFEJEZETTEN csak a tényleges Igehirdetési
   műhely AI-akciógombjait célozza a saját `key=`-eik prefixe alapján
   (`sw_refine_*`: MI-javaslat / pontosítás a hét ponthoz és a két
   főgondolathoz; `sw_flat_*`: hétpontos ív / tervrajz / részletes vázlat
   generálása és a candidate elfogadása/elvetése) — NEM minden Streamlit
   gombra. A vizuális nyelv a már bevált (.st-key-tension_transfer_actions)
   telt, visszafogott stílust követi: elsődleges = kékes telítésű, erősebb
   szegély; másodlagos = tompább, de MINDIG jól látható, telt háttér. */
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-primary"],
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-primary"] {
    background:
        linear-gradient(
            180deg,
            var(--tx-btn-primary-top) 0%,
            var(--tx-btn-primary-mid) 52%,
            var(--tx-btn-primary-bot) 100%
        ) !important;
    border: 1px solid #35557c !important;
    color: #ffffff !important;
    text-shadow: 0 1px 0 rgba(18, 32, 48, 0.25) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.28) inset,
        0 4px 10px rgba(31, 51, 77, 0.28) !important;
    font-weight: 650 !important;
}
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-primary"] [data-testid="stMarkdownContainer"] p,
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-primary"] [data-testid="stMarkdownContainer"] p,
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"],
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"] {
    color: #ffffff !important;
}
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-primary"]:hover,
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-primary"]:hover {
    background:
        linear-gradient(
            180deg,
            #7a98c0 0%,
            #5a7aa8 52%,
            #45678f 100%
        ) !important;
    border-color: #35557c !important;
    transform: translateY(-1px) !important;
}
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-primary"]:active,
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-primary"]:active {
    transform: translateY(0) !important;
}
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-secondary"],
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-secondary"] {
    background:
        linear-gradient(
            180deg,
            rgba(255, 254, 250, 0.98) 0%,
            rgba(236, 226, 210, 0.9) 100%
        ) !important;
    border: 1px solid rgba(170, 145, 112, 0.48) !important;
    color: var(--tx-text) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.9) inset,
        0 3px 8px rgba(58, 40, 22, 0.1) !important;
}
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-secondary"]:hover,
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-secondary"]:hover {
    background:
        linear-gradient(
            180deg,
            rgba(255, 255, 252, 1) 0%,
            rgba(232, 238, 247, 0.94) 100%
        ) !important;
    border-color: rgba(90, 122, 168, 0.48) !important;
    color: var(--tx-primary-deep) !important;
    transform: translateY(-1px) !important;
}
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-secondary"]:active,
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-secondary"]:active {
    background: rgba(232, 238, 247, 0.85) !important;
}
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-primary"]:focus-visible,
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-primary"]:focus-visible,
[class*="st-key-sw_refine_"] button[data-testid="stBaseButton-secondary"]:focus-visible,
[class*="st-key-sw_flat_"] button[data-testid="stBaseButton-secondary"]:focus-visible {
    outline: 2px solid rgba(90, 122, 168, 0.55) !important;
    outline-offset: 2px !important;
}
[class*="st-key-sw_refine_"] button:disabled,
[class*="st-key-sw_flat_"] button:disabled {
    opacity: 0.55 !important;
}

/* ===== FINAL SERMON WORKFLOW + OUTLINE PRESENTATION POLISH — a
   részletes vázlat (developed outline) főnézetének sűrítése
   (SCOPED a `.st-key-sw_flat_outline_canonical` blokkra, 2026-08-21) =====
   KIZÁRÓLAG a kanonikus részletes vázlat kártyáit célozza — nem az
   app globális tipográfiáját. A cél sűrűbb, könyvszerűbb, könnyebben
   pásztázható megjelenés: kisebb függőleges távolság a mozgás-kártyák
   között, cím/funkció/fő állítás/kibontás/átvezetés mezők között, és
   a kibontás-textarea sorai között — a betűméret VÁLTOZATLAN marad. */
.st-key-sw_flat_outline_canonical [data-testid="stVerticalBlock"] {
    gap: 0.28rem !important;
}
.st-key-sw_flat_outline_canonical [data-testid="stElementContainer"] {
    margin-bottom: 0 !important;
}
.st-key-sw_flat_outline_canonical [data-testid="stWidgetLabel"] {
    margin-bottom: 0.1rem !important;
    padding-bottom: 0 !important;
}
.st-key-sw_flat_outline_canonical [data-testid="stWidgetLabel"] p {
    margin-bottom: 0 !important;
    font-size: 0.85rem !important;
    opacity: 0.85;
}
.st-key-sw_flat_outline_canonical textarea,
.st-key-sw_flat_outline_canonical input[type="text"] {
    padding: 0.35rem 0.55rem !important;
    line-height: 1.35 !important;
}
.st-key-sw_flat_outline_canonical [data-testid="stMarkdownContainer"] p,
.st-key-sw_flat_outline_canonical [data-testid="stMarkdown"] p {
    line-height: 1.32 !important;
    margin-bottom: 0.28rem !important;
}
.st-key-sw_flat_outline_canonical [data-testid="stMarkdownContainer"] li,
.st-key-sw_flat_outline_canonical [data-testid="stMarkdown"] li {
    line-height: 1.32 !important;
    margin: 0.05rem 0 !important;
}
.st-key-sw_flat_outline_canonical [data-testid="stMarkdownContainer"] ul,
.st-key-sw_flat_outline_canonical [data-testid="stMarkdown"] ul {
    margin: 0.15rem 0 0.35rem 0.9rem !important;
}
.st-key-sw_flat_outline_canonical [data-testid="stCaptionContainer"] {
    margin-top: 0.05rem !important;
    margin-bottom: 0.12rem !important;
}
.st-key-sw_flat_outline_canonical [data-testid="stCaptionContainer"] p {
    line-height: 1.28 !important;
    margin-bottom: 0 !important;
}
[class*="st-key-sw_flat_outline_movement_"] {
    padding: 0.5rem 0.7rem !important;
}

/* Hétpontos kártyák + Íróasztal kivonatok — emelt, sűrű dashboard-elemek */
[class*="st-key-writing_desk_extract_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
    padding: 12px 14px !important;
    background:
        linear-gradient(
            180deg,
            rgba(255, 253, 248, 0.96) 0%,
            rgba(247, 239, 226, 0.9) 100%
        ) !important;
    border: 1px solid rgba(170, 145, 112, 0.34) !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.88) inset,
        0 5px 12px rgba(58, 40, 22, 0.08) !important;
}
[class*="st-key-writing_desk_extract_card_"] [data-testid="stVerticalBlock"] {
    gap: 0.32rem !important;
}

/* tx-ui-pass-v3-20260902 — hétpontos kártyák sűrítése */
[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-sw_refine_quick_"]) {
    padding: 8px 12px !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-sw_refine_quick_"]) > [data-testid="stVerticalBlock"] {
    gap: 8px !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-sw_refine_quick_"]) textarea {
    min-height: 64px !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-sw_refine_quick_"]) [data-testid="stElementContainer"] {
    margin-bottom: 0 !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-sw_refine_quick_"]) [data-testid="stExpander"] details,
[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-sw_refine_quick_"]) [data-testid="stExpander"] summary {
    padding-top: 4px !important;
    padding-bottom: 4px !important;
    min-height: 0 !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-sw_refine_quick_"]) [data-testid="stExpander"] summary p {
    font-size: 0.82rem !important;
}

/* tx-ui-pass-v3-20260902 — last-wins a korábbi app.py CTA-blokk ellen */
:root {
    --tx-ui-pass: v3-20260902;
}
.stButton > button[kind="primary"],
.stButton > button[kind="primaryFormSubmit"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background-color: #4d6f9a !important;
    background-image: linear-gradient(180deg, #6d8bb6 0%, #4d6f9a 52%, #3b5a84 100%) !important;
    color: #ffffff !important;
    border: 1px solid #35557c !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.28) inset,
        0 4px 10px rgba(31, 51, 77, 0.28) !important;
}
.st-key-bible_text_ruf_load_btn button,
.st-key-bible_text_ruf_load_btn [data-testid="stBaseButton-primary"] {
    background-color: #4d6f9a !important;
    background-image: linear-gradient(180deg, #6d8bb6 0%, #4d6f9a 52%, #3b5a84 100%) !important;
    color: #ffffff !important;
    border: 1px solid #35557c !important;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.28) inset,
        0 4px 10px rgba(31, 51, 77, 0.28) !important;
}
.stButton > button[kind="primary"]::before,
.stButton > button[kind="primary"]::after,
.stButton > button[kind="primaryFormSubmit"]::before,
.stButton > button[kind="primaryFormSubmit"]::after {
    content: none !important;
    display: none !important;
    background: none !important;
    opacity: 0 !important;
}
.stButton > button[kind="primary"] > div > p,
.stButton > button[kind="primaryFormSubmit"] > div > p,
.stButton > button[kind="primary"] [data-testid="stMarkdownContainer"] p,
.stButton > button[kind="primaryFormSubmit"] [data-testid="stMarkdownContainer"] p {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    text-shadow: 0 1px 0 rgba(18, 32, 48, 0.25) !important;
}
.st-key-bible_text_ruf_load_btn button,
.st-key-bible_text_ruf_load_btn button *,
.st-key-bible_text_ruf_load_btn button p {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
""".strip()

