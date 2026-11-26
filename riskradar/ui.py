"""Presentation helpers for the Streamlit UI: theme CSS, status pills, cards and chart styling.

Kept separate from app.py so layout code stays readable. Nothing here computes risk.
"""
from __future__ import annotations

from html import escape

import pandas as pd

# ------------------------------------------------------------------ design tokens
INK = "#16202E"
MUTED = "#5E6878"
LINE = "#E3E6EB"
SURFACE = "#FFFFFF"
PAGE = "#F5F6F8"
ACCENT = "#24489B"
FONT = "'IBM Plex Sans', -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

STATUS = {
    "High": {"fg": "#B42318", "bg": "#FEF3F2", "label": "High", "css": "high"},
    "Elevated": {"fg": "#B54708", "bg": "#FFF6E5", "label": "Elevated", "css": "elev"},
    "Normal": {"fg": "#067647", "bg": "#ECFDF3", "label": "Normal", "css": "norm"},
    "Insufficient data": {"fg": "#667085", "bg": "#F2F4F7", "label": "No data", "css": "none"},
}

SHORT_CATEGORY = {
    "Market volatility": "Volatility",
    "Corporate credit spreads": "Credit spreads",
    "Interest rates": "Rates",
    "Equity market drawdown": "Equities",
    "AI financing": "AI financing",
    "Hedge fund leverage": "Hedge funds",
    "Agricultural lending stress": "Farm lending",
    "NDFI lending growth": "NDFI lending",
    "Bank lending": "Bank lending",
}

RADAR_SVG = f"""<svg width="34" height="34" viewBox="0 0 34 34" aria-hidden="true">
<circle cx="17" cy="17" r="15.5" fill="none" stroke="{ACCENT}" stroke-opacity=".25" stroke-width="1.5"/>
<circle cx="17" cy="17" r="10" fill="none" stroke="{ACCENT}" stroke-opacity=".45" stroke-width="1.5"/>
<circle cx="17" cy="17" r="4.5" fill="none" stroke="{ACCENT}" stroke-opacity=".7" stroke-width="1.5"/>
<path d="M17 17 L17 1.5 A15.5 15.5 0 0 1 30.4 9.2 Z" fill="{ACCENT}" fill-opacity=".22"/>
<line x1="17" y1="17" x2="30.4" y2="9.2" stroke="{ACCENT}" stroke-width="1.8" stroke-linecap="round"/>
<circle cx="24.5" cy="11" r="2" fill="#B42318"/>
</svg>"""


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

.stApp {{ background: {PAGE}; font-family: {FONT}; color: {INK}; }}
.stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ font-family: {FONT}; }}

/* Remove Streamlit chrome: no sidebar, quiet header, no footer */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{ display: none !important; }}
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"] {{ right: 1rem; }}
footer, [data-testid="stDecoration"] {{ display: none !important; }}

[data-testid="stMainBlockContainer"], .block-container {{ max-width: 100%; padding: 1.6rem 3rem 7rem; }}
@media (min-width: 1900px) {{ [data-testid="stMainBlockContainer"], .block-container {{ padding-left: 4.5rem; padding-right: 4.5rem; }} }}

h1, h2, h3 {{ letter-spacing: -0.01em; color: {INK}; }}
.stApp h3 {{ font-size: 1.08rem; font-weight: 600; }}

/* Tabs */
[data-baseweb="tab-list"] {{ gap: 1.6rem; border-bottom: 1px solid {LINE}; }}
button[data-baseweb="tab"] {{ padding: 0.7rem 0 0.75rem; }}
button[data-baseweb="tab"] p {{ font-size: 0.95rem; font-weight: 500; color: {MUTED}; }}
button[data-baseweb="tab"][aria-selected="true"] p {{ color: {INK}; font-weight: 600; }}
[data-baseweb="tab-highlight"] {{ background-color: {ACCENT}; height: 2px; }}
[data-baseweb="tab-border"] {{ display: none; }}

/* Buttons */
.stButton button, .stFormSubmitButton button, .stDownloadButton button {{ border-radius: 8px; font-weight: 500; }}

/* Header */
.rr-brand {{ display: flex; align-items: center; gap: 0.75rem; }}
.rr-brand-name {{ font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; }}
.rr-brand-sub {{ font-size: 0.86rem; color: {MUTED}; margin-top: 2px; }}

/* Overview */
.rr-overview {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 14px; padding: 1.4rem 1.5rem 1.2rem; margin: 1.2rem 0 1.4rem; }}
.rr-ov-top {{ display: flex; justify-content: space-between; gap: 1.5rem; flex-wrap: wrap; align-items: flex-end; }}
.rr-ov-title {{ font-size: 1.6rem; font-weight: 600; letter-spacing: -0.02em; line-height: 1.2; }}
.rr-ov-meta {{ color: {MUTED}; font-size: .88rem; margin-top: .35rem; }}
.rr-counts {{ display: flex; gap: 2.4rem; flex-wrap: wrap; }}
.rr-count-n {{ min-height: 1px; }}
.rr-count {{ min-width: 64px; }}
.rr-count-n {{ font-size: 1.75rem; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1; }}
.rr-count-l {{ font-size: .8rem; color: {MUTED}; margin-top: .3rem; display: flex; align-items: center; gap: .35rem; }}
.rr-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; }}

.rr-strip {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 1.3rem; padding-top: 1.1rem; border-top: 1px solid {LINE}; }}
.rr-group {{ display: flex; flex-direction: column; gap: .45rem; min-width: 64px; }}
.rr-cells {{ display: flex; gap: 3px; }}
.rr-cell {{ flex: 1 1 0; min-width: 14px; height: 28px; border-radius: 4px; }}
.rr-cell.high {{ background: #D92D20; }} .rr-cell.elev {{ background: #F79009; }}
.rr-cell.norm {{ background: #A6D9BC; }} .rr-cell.none {{ background: repeating-linear-gradient(45deg,#E4E7EC 0 3px,#F2F4F7 3px 6px); }}
.rr-group-l {{ font-size: .75rem; color: {MUTED}; white-space: nowrap; }}

/* Section heading */
.rr-section {{ display: flex; align-items: baseline; justify-content: space-between; margin: 1.6rem 0 .6rem; }}
.rr-section-t {{ font-size: 1.05rem; font-weight: 600; }}
.rr-section-s {{ font-size: .82rem; color: {MUTED}; }}

/* Indicator cards (keyed containers) */
[class*="st-key-card_"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px; padding: 1rem 1.1rem .6rem;
  gap: .4rem; height: 100%; }}
.rr-card-head {{ display: flex; justify-content: space-between; gap: .8rem; align-items: flex-start; }}
.rr-card-area {{ font-size: .74rem; color: {ACCENT}; font-weight: 500; margin-bottom: .2rem; }}
.rr-link {{ font-size: .84rem; color: {ACCENT} !important; text-decoration: none; font-weight: 500; }}
.rr-link:hover {{ text-decoration: underline; }}
.rr-card-label {{ font-size: .9rem; font-weight: 500; color: {INK}; line-height: 1.35; }}
.rr-card-src {{ font-size: .76rem; color: {MUTED}; margin-top: 2px; }}
.rr-pill {{ display: inline-flex; align-items: center; gap: .35rem; padding: .18rem .55rem; border-radius: 999px;
  font-size: .76rem; font-weight: 600; white-space: nowrap; }}
.rr-value {{ font-size: 1.7rem; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; margin-top: .5rem; line-height: 1.1; }}
.rr-unit {{ font-size: .85rem; font-weight: 500; color: {MUTED}; margin-left: .3rem; }}
.rr-sub {{ display: flex; gap: 1rem; flex-wrap: wrap; font-size: .82rem; color: {MUTED}; margin-top: .25rem; font-variant-numeric: tabular-nums; }}
.rr-empty {{ font-size: .86rem; color: {MUTED}; background: {PAGE}; border-radius: 8px; padding: .7rem .8rem; margin: .6rem 0 .4rem; line-height: 1.45; }}

/* Generic panels */
[class*="st-key-panel_"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px; padding: 1.1rem 1.2rem; }}

.rr-foot {{ color: {MUTED}; font-size: .8rem; margin-top: 2.2rem; padding-top: 1rem; border-top: 1px solid {LINE}; line-height: 1.5; }}
.rr-lede {{ color: {MUTED}; font-size: .95rem; line-height: 1.55; max-width: 72ch; margin: .2rem 0 1rem; }}
.rr-conn {{ display: grid; grid-template-columns: auto 1fr; gap: .2rem .7rem; align-items: start; padding: .7rem 0; border-bottom: 1px solid {LINE}; }}
.rr-conn:last-child {{ border-bottom: 0; }}
.rr-conn-t {{ font-weight: 600; font-size: .92rem; }}
.rr-conn-d {{ grid-column: 2; font-size: .84rem; color: {MUTED}; line-height: 1.45; }}
.rr-conn .rr-dot {{ margin-top: .45rem; }}

[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}

/* Header status */
.rr-status {{ display: flex; align-items: center; justify-content: flex-end; gap: .45rem; font-size: .84rem; color: {MUTED}; }}

/* Loading card */
.rr-loading {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 14px; padding: 2.4rem 1.5rem; margin: 1.2rem 0;
  display: flex; flex-direction: column; align-items: center; text-align: center; gap: .6rem; }}
.rr-loading-t {{ font-size: 1.15rem; font-weight: 600; }}
.rr-loading-d {{ color: {MUTED}; font-size: .9rem; max-width: 46ch; line-height: 1.5; }}
.rr-sweep {{ transform-origin: 17px 17px; animation: rr-spin 2.4s linear infinite; }}
@keyframes rr-spin {{ to {{ transform: rotate(360deg); }} }}
@media (prefers-reduced-motion: reduce) {{ .rr-sweep {{ animation: none; }} }}

/* Floating chat launcher + window */
.st-key-chat_fab {{ position: fixed; right: 28px; bottom: 28px; z-index: 1001; width: auto !important; }}
.st-key-chat_fab button {{ border-radius: 999px; padding: .7rem 1.2rem; font-weight: 600; min-height: 0;
  box-shadow: 0 10px 28px -8px rgba(36,72,155,.55), 0 2px 6px rgba(16,24,40,.12); }}
.st-key-chatdrawer {{ position: fixed; right: 28px; bottom: 92px; z-index: 1000; width: min(440px, calc(100vw - 32px));
  max-height: calc(100vh - 120px); overflow: hidden; background: {SURFACE}; border: 1px solid {LINE}; border-radius: 16px;
  padding: .9rem 1rem .6rem; gap: .5rem; box-shadow: 0 24px 60px -20px rgba(16,24,40,.35), 0 4px 12px rgba(16,24,40,.08);
  animation: rr-pop .18s ease-out; transform-origin: bottom right; }}
@keyframes rr-pop {{ from {{ opacity: 0; transform: translateY(10px) scale(.98); }} to {{ opacity: 1; transform: none; }} }}
@media (prefers-reduced-motion: reduce) {{ .st-key-chatdrawer {{ animation: none; }} }}
.st-key-chatdrawer [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: .25rem; }}
.st-key-chatdrawer .st-key-chat_clear button, .st-key-chatdrawer .st-key-chat_close button {{ border: 0; background: transparent;
  color: {MUTED}; padding: .3rem; min-height: 0; }}
.st-key-chatdrawer .st-key-chat_clear button:hover, .st-key-chatdrawer .st-key-chat_close button:hover {{ background: {PAGE}; color: {INK}; }}
.rr-chat-h {{ display: flex; align-items: center; gap: .6rem; }}
.rr-chat-t {{ font-weight: 600; font-size: 1rem; line-height: 1.2; }}
.rr-chat-s {{ font-size: .78rem; color: {MUTED}; display: flex; align-items: center; gap: .35rem; margin-top: 2px; }}
.st-key-chatmsgs {{ border-top: 1px solid {LINE}; border-bottom: 1px solid {LINE}; padding: .4rem .1rem; }}
.st-key-chatmsgs [data-testid="stChatMessage"] {{ padding: .55rem .6rem; border-radius: 10px; }}
.st-key-chatmsgs [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
.st-key-chatmsgs [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{ background: #EEF2FA; }}
.st-key-chatmsgs [data-testid="stChatMessage"] p, .st-key-chatmsgs [data-testid="stChatMessage"] li {{ font-size: .9rem; line-height: 1.5; }}
.st-key-chatmsgs .stButton button {{ justify-content: flex-start; text-align: left; font-size: .84rem; font-weight: 400;
  color: {ACCENT}; border-color: #D3DCEF; background: #F7F9FD; padding: .45rem .7rem; }}
.st-key-chatmsgs .stButton button:hover {{ border-color: {ACCENT}; }}

@media (max-width: 640px) {{
  .st-key-chatdrawer {{ right: 8px; left: 8px; bottom: 80px; width: auto; }}
  .st-key-chat_fab {{ right: 16px; bottom: 16px; }}
  [data-testid="stMainBlockContainer"], .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
  .rr-ov-title {{ font-size: 1.25rem; }}
  .rr-counts {{ gap: 1.1rem; }}
  .rr-cell {{ height: 20px; }}
}}
</style>
"""


# ------------------------------------------------------------------ formatting

def pretty_date(value) -> str:
    if not value:
        return "n/a"
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return str(value)
    return f"{ts:%b} {ts.day}, {ts.year}"


def pretty_datetime(value) -> str:
    if not value:
        return "never"
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return str(value)
    return f"{ts:%b} {ts.day}, {ts.year} at {ts:%H:%M}"


# ------------------------------------------------------------------ components

def status_html(text: str, color: str) -> str:
    return f'<div class="rr-status">{dot(color)}<span>{escape(text)}</span></div>'


def loading_html() -> str:
    svg = RADAR_SVG.replace('<path d=', '<g class="rr-sweep"><path d=').replace('stroke-linecap="round"/>',
                                                                                  'stroke-linecap="round"/></g>', 1)
    svg = svg.replace('width="34" height="34"', 'width="56" height="56"')
    return ('<div class="rr-loading" role="status">' + svg +
            '<div class="rr-loading-t">Getting the latest market data</div>'
            '<div class="rr-loading-d">Pulling figures from FRED, OFR, SEC EDGAR and the Federal Reserve. This takes '
            'about a minute on the first visit and is instant after that.</div></div>')


def chat_header_html(ready: bool) -> str:
    color, label = ((STATUS["Normal"]["fg"], "Online, cites its sources") if ready
                    else (STATUS["Insufficient data"]["fg"], "Unavailable"))
    icon = RADAR_SVG.replace('width="34" height="34"', 'width="30" height="30"')
    return (f'<div class="rr-chat-h">{icon}<div><div class="rr-chat-t">RiskRadar assistant</div>'
            f'<div class="rr-chat-s">{dot(color)}{label}</div></div></div>')


def pill(classification: str) -> str:
    st_ = STATUS.get(classification, STATUS["Insufficient data"])
    return (f'<span class="rr-pill" style="color:{st_["fg"]};background:{st_["bg"]}">'
            f'<span class="rr-dot" style="background:{st_["fg"]}"></span>{st_["label"]}</span>')


def dot(color: str) -> str:
    return f'<span class="rr-dot" style="background:{color}"></span>'


def header_html(subtitle: str) -> str:
    return (f'<div class="rr-brand">{RADAR_SVG}<div><div class="rr-brand-name">RiskRadar</div>'
            f'<div class="rr-brand-sub">{escape(subtitle)}</div></div></div>')


def overview_html(results, category_order: list[str], last_refresh: str) -> str:
    counts = {k: 0 for k in STATUS}
    for r in results:
        counts[r.classification] = counts.get(r.classification, 0) + 1
    n_alert = counts["High"] + counts["Elevated"]
    total = len(results)
    if counts["Insufficient data"] == total:
        title = "No data loaded yet"
    elif n_alert == 0:
        title = "All indicators are within their normal ranges"
    else:
        title = (f"{n_alert} of {total} indicators {'is' if n_alert == 1 else 'are'} above "
                 f"{'its' if n_alert == 1 else 'their'} normal range")
    meta = (f"Last data refresh {last_refresh}" if last_refresh != "never" else "No successful data load yet") + \
        f" &nbsp;/&nbsp; {total} indicators across {len({r.category for r in results})} risk areas"

    count_html = "".join(
        f'<div class="rr-count"><div class="rr-count-n" style="color:{STATUS[k]["fg"] if k in ("High", "Elevated") and counts[k] else INK}">{counts[k]}</div>'
        f'<div class="rr-count-l">{dot(STATUS[k]["fg"])}{STATUS[k]["label"]}</div></div>'
        for k in ("High", "Elevated", "Normal", "Insufficient data"))

    groups = []
    for cat in category_order:
        group = [r for r in results if r.category == cat]
        if not group:
            continue
        cells = "".join(
            f'<span class="rr-cell {STATUS[r.classification]["css"]}" title="{escape(r.label)}: '
            f'{STATUS[r.classification]["label"]}"></span>' for r in group)
        groups.append(f'<div class="rr-group" style="flex:{len(group)} 1 0"><div class="rr-cells">{cells}</div>'
                      f'<div class="rr-group-l">{escape(SHORT_CATEGORY.get(cat, cat))}</div></div>')

    return (f'<div class="rr-overview"><div class="rr-ov-top"><div><div class="rr-ov-title">{escape(title)}</div>'
            f'<div class="rr-ov-meta">{meta}</div></div><div class="rr-counts">{count_html}</div></div>'
            f'<div class="rr-strip" role="img" aria-label="Status of each indicator by risk area">{"".join(groups)}</div></div>')


def section_html(title: str, group) -> str:
    flagged = sum(r.classification in ("High", "Elevated") for r in group)
    sub = f"{len(group)} indicator{'s' if len(group) != 1 else ''}" + (f", {flagged} flagged" if flagged else "")
    return f'<div class="rr-section"><span class="rr-section-t">{escape(title)}</span><span class="rr-section-s">{sub}</span></div>'


def _card_top(r) -> str:
    area = SHORT_CATEGORY.get(r.category, r.category)
    return (f'<div class="rr-card-head"><div><div class="rr-card-area">{escape(area)}</div>'
            f'<div class="rr-card-label">{escape(r.label)}</div>'
            f'<div class="rr-card-src">{escape(r.source)}</div></div>{pill(r.classification)}</div>')


def card_head_html(r, value: str, unit: str, change: str, asof: str) -> str:
    unit_html = f'<span class="rr-unit">{escape(unit)}</span>' if unit else ""
    return (_card_top(r) +
            f'<div class="rr-value">{escape(value)}{unit_html}</div><div class="rr-sub"><span>{escape(change)}</span><span>As of {escape(asof)}</span></div>')


def card_empty_html(r, message: str) -> str:
    return _card_top(r) + f'<div class="rr-empty">{escape(message)}</div>'


def connection_html(rows: list[tuple[bool, str, str]]) -> str:
    out = []
    for ok, title, desc in rows:
        color = STATUS["Normal"]["fg"] if ok else STATUS["Elevated"]["fg"]
        out.append(f'<div class="rr-conn">{dot(color)}<span class="rr-conn-t">{escape(title)}</span>'
                   f'<span class="rr-conn-d">{desc}</span></div>')
    return "".join(out)


def style_figure(fig, unit: str = ""):
    fig.update_layout(
        height=190, margin=dict(l=0, r=4, t=26, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=11, color=MUTED),
        hovermode="x unified", hoverlabel=dict(font=dict(family=FONT, size=12)),
        showlegend=True, legend=dict(orientation="h", x=0, y=1.18, font=dict(size=10.5), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, linecolor=LINE, ticks="", tickfont=dict(size=10.5)),
        yaxis=dict(gridcolor="#EEF0F3", zeroline=False, title=None, tickfont=dict(size=10.5), ticksuffix=""),
    )
    return fig
