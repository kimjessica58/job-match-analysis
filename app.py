import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from pathlib import Path
import html
import re
from textwrap import wrap
import bq_client
import config

st.set_page_config(page_title="Job Match Analysis", page_icon="📊", layout="wide")

# ── Theme ─────────────────────────────────────────────────────────────────────

COLORS = {
    "bar": "#F4C247",
    "bar_line": "#C99835",
    "bg": "#F7F4EC",
    "surface": "#FFFDF8",
    "grid": "#D8D1C6",
    "text": "#2A231C",
    "secondary": "#8A6137",
    "header_top": "#F6DE6A",
    "header_bottom": "#D5E1F1",
    "header_border": "#B4C5DD",
    "panel_border": "#D8D1C6",
    "sidebar_bg": "#EAF1FA",
    "accent": "#111111",
    "success": "#15B8A6",
    "success_soft": "#D8EEE9",
    "warning": "#D2A13A",
    "warning_soft": "#F7E6B2",
    "danger": "#EF7B4D",
    "danger_soft": "#F7D8CB",
    "info": "#5C8FCA",
    "info_soft": "#D7E3F2",
    "brown": "#8A6137",
    "brown_soft": "#E6D8C6",
    "sage": "#9AA9A5",
    "sage_soft": "#D7E1DE",
    "muted": "#6D675E",
    "neutral_soft": "#F1EEE6",
}

RATE_COLOR_MAP = {
    "Decision rate": COLORS["info"],
    "Approval rate": COLORS["warning"],
    "Rejection rate": COLORS["danger"],
    "Application rate": COLORS["success"],
}

MATCH_MIX_COLOR_MAP = {
    "Pending review": COLORS["info"],
    "Rejected": COLORS["danger"],
    "Approved, awaiting app": COLORS["warning_soft"],
    "Applied": COLORS["success"],
    "Other outcomes": COLORS["brown_soft"],
}

FUNNEL_STAGE_COLOR_MAP = {
    "Match Coverage": COLORS["danger"],
    "Approval After Match": COLORS["warning"],
    "Application After Approval": COLORS["success"],
}

COVERAGE_TIER_COLORS = {
    "Low Coverage": COLORS["danger"],
    "Opportunity Band": COLORS["warning"],
    "Healthy Coverage": COLORS["success"],
}

BRAND_SEQUENCE = [
    COLORS["bar"],
    COLORS["warning"],
    COLORS["brown"],
    COLORS["success"],
    COLORS["info"],
    COLORS["danger"],
    COLORS["sage"],
]

st.markdown("""
<style>
    html, body, [class*="css"]  { font-size: 17px; }
    .stApp, [data-testid="stAppViewContainer"] { background-color: #F7F4EC; color: #2A231C; }
    [data-testid="stSidebar"] { background-color: #EAF1FA; border-right: 2px solid #D8D1C6; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1 {
        color: #2A231C; font-weight: 800; letter-spacing: -0.02em;
    }
    .dashboard-header {
        background: #FFF7D8;
        border: 2px solid #D2A13A;
        padding: 22px 28px; border-radius: 18px;
        margin: 0 0 1.25rem 0;
        box-shadow: 0 10px 28px rgba(0,0,0,0.06);
    }
    .dashboard-header-logo { max-width: 260px; margin-bottom: 0.85rem; }
    .dashboard-eyebrow { font-size: 0.88rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: #8A6137; }
    .dashboard-header h1 { font-size: 2rem; font-weight: 800; color: #2A231C; margin: 0.1rem 0 0 0; }
    .dashboard-header p { font-size: 1rem; color: #6D675E; margin: 0.35rem 0 0 0; line-height: 1.5; }
    .summary-card, .source-card {
        background: #FFFDF8; border: 1px solid #D8D1C6; border-radius: 16px;
        padding: 16px 18px; box-shadow: 0 4px 16px rgba(0,0,0,0.04); margin-bottom: 1rem;
    }
    .source-card {
        border: 2px solid #D8D1C6;
        padding: 0;
        overflow: hidden;
    }
    .source-card-header {
        background: #EAF1FA;
        border-bottom: 1px solid #D8D1C6;
        padding: 14px 18px 12px 18px;
    }
    .source-card-label {
        display: block;
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #5C8FCA;
        margin-bottom: 0.25rem;
    }
    .source-card-title {
        margin: 0;
        font-size: 1.08rem;
        font-weight: 800;
        color: #2A231C;
    }
    .source-card-subtitle {
        margin: 0.35rem 0 0 0;
        color: #6D675E;
        font-size: 0.94rem;
        line-height: 1.5;
    }
    .source-card-body {
        padding: 16px 18px 18px 18px;
    }
    .source-card-item + .source-card-item {
        border-top: 1px solid #E5DED3;
        margin-top: 0.9rem;
        padding-top: 0.9rem;
    }
    .source-item-title {
        margin: 0 0 0.28rem 0;
        font-size: 0.98rem;
        font-weight: 800;
        color: #2A231C;
    }
    .source-item-body {
        margin: 0;
        color: #3B352F;
        line-height: 1.6;
        font-size: 0.96rem;
    }
    .summary-card strong, .source-card strong { color: #2A231C; }
    .summary-card p { margin: 0; color: #3B352F; line-height: 1.55; font-size: 0.98rem; }
    .summary-card p + p { margin-top: 0.6rem; }
    .summary-card code, .source-card code {
        background: #D7E3F2; border: 1px solid #5C8FCA; border-radius: 6px;
        color: #2A231C; padding: 0.08rem 0.35rem; font-size: 0.9rem;
    }
    .page-pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 0.4rem 0 0.15rem 0; }
    .page-pill {
        background: rgba(255,255,255,0.92); border: 1px solid #5C8FCA;
        color: #2A231C; border-radius: 999px; padding: 6px 10px; font-size: 0.9rem; font-weight: 700;
    }
    .control-intro { margin-bottom: 0.35rem; }
    .control-intro p { margin: 0; color: #6D675E; }
    .filter-panel-title {
        margin: 0 0 0.35rem 0;
        font-size: 1.02rem;
        font-weight: 800;
        color: #2A231C;
    }
    .filter-panel-subtitle {
        margin: 0 0 0.9rem 0;
        color: #6D675E;
        line-height: 1.5;
    }
    [data-testid="stMetric"] {
        background: #FFFDF8; border: 1px solid #D8D1C6; border-radius: 14px;
        padding: 18px 20px; box-shadow: 0 4px 16px rgba(0,0,0,0.04);
    }
    [data-testid="stMetricLabel"] {
        color: #8A6137 !important; font-size: 0.88rem; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.04em;
    }
    [data-testid="stMetricValue"] { color: #2A231C !important; font-weight: 800; font-size: 1.65rem; }
    [data-testid="stDataFrame"] { border: 1px solid #D8D1C6; border-radius: 14px; overflow: hidden; }
    [data-testid="stDataFrame"] [role="grid"] { font-size: 0.96rem; }
    [data-testid="stDataFrame"] [role="columnheader"] {
        background: #F1EEE6 !important;
        color: #2A231C !important;
        font-weight: 800 !important;
        border-bottom: 1px solid #D8D1C6 !important;
    }
    [data-testid="stDataFrame"] [role="columnheader"] * {
        color: #2A231C !important;
        font-weight: 800 !important;
        opacity: 1 !important;
    }
    [data-testid="stExpander"] {
        background: #FFFDF8; border: 1px solid #D8D1C6 !important;
        border-radius: 14px !important; box-shadow: 0 4px 16px rgba(0,0,0,0.04);
    }
    .stButton > button {
        background: #F6DE6A; color: #2A231C; border: 2px solid #C99835;
        border-radius: 10px; font-weight: 800;
    }
    .stButton > button:hover {
        background: #F7E6B2; border-color: #C99835; color: #2A231C;
        transform: translateY(-1px); box-shadow: 0 6px 16px rgba(92,143,202,0.18);
    }
    [data-testid="stMultiSelect"] span[data-baseweb="tag"] {
        background: #D8EEE9; border: 1px solid #15B8A6; color: #2A231C;
    }
    hr { border-color: #D8D1C6; }
    .sql-display { background: #1e1e1e; color: #d4d4d4; padding: 16px;
        border-radius: 10px; font-family: 'SF Mono', 'Fira Code', monospace;
        font-size: 0.9rem; overflow-x: auto; margin: 8px 0; }
    h2, h3 { color: #2A231C; letter-spacing: -0.01em; }
    p, li, label, .stMarkdown, .stCaption { color: #3B352F !important; }
    /* Nav radio styling */
    [data-testid="stSidebar"] .stRadio > div { gap: 2px; }
    [data-testid="stSidebar"] .stRadio label {
        padding: 10px 12px; border-radius: 10px; cursor: pointer;
        font-weight: 700; font-size: 0.96rem;
    }
    [data-testid="stSidebar"] .stRadio label:hover { background: #D7E3F2; }
    [data-testid="stCaptionContainer"] { font-size: 0.9rem; color: #6D675E !important; }
</style>
""", unsafe_allow_html=True)

TIMEFRAME_PRESETS = {
    "Last 7 Days": 7,
    "Last 30 Days": 30,
    "Last 60 Days": 60,
    "Last 90 Days": 90,
    "Last 180 Days": 180,
    "Last 365 Days": 365,
    "All Time": None,
    "Custom": "custom",
}
COMPARE_TIMEFRAME_OPTIONS = [
    "Previous Equivalent Period",
    "Last 7 Days",
    "Last 30 Days",
    "Last 60 Days",
    "Last 90 Days",
    "Last 180 Days",
    "Last 365 Days",
    "Custom",
]
MATCH_SOURCE_OPTIONS = {
    "All Matches": "all",
    "XML Jobs Only": "xml",
    "Native Jobs Only": "native",
}
MATCH_SOURCE_LABELS = {value: label for label, value in MATCH_SOURCE_OPTIONS.items()}
MATCH_STATUS_LABELS = {
    "USER_PENDING": "Pending Review",
    "USER_APPROVED": "Approved",
    "USER_REJECTED": "Rejected",
    "CONTRACTOR_PENDING": "In Contractor Queue",
    "APPLIED": "Applied",
    "APP_FAILED": "Application Failed",
    "ACCOUNT_EXISTS": "Account Already Exists",
    "JOB_EXPIRED": "Job Expired",
}
VERSION_LABELS = {"instant": "Instant", "v1": "Cron V1", "v2": "Cron V2", "unknown": "Unknown"}
ASSETS_DIR = Path(__file__).parent / "assets"
WORDMARK_CANDIDATES = [
    ASSETS_DIR / "Combination-Brown.png",
    ASSETS_DIR / "bandana-logo.png",
    ASSETS_DIR / "bandana_wordmark.png",
    ASSETS_DIR / "bandana_wordmark.svg",
    ASSETS_DIR / "bandana_logo.png",
    ASSETS_DIR / "bandana_logo.svg",
]
ICON_CANDIDATES = [
    ASSETS_DIR / "Symbol-Brown.png",
    ASSETS_DIR / "bandana_icon.png",
    ASSETS_DIR / "bandana_icon.svg",
    ASSETS_DIR / "bandana_mark.png",
    ASSETS_DIR / "bandana_mark.svg",
]


def first_existing_path(candidates):
    """Return the first existing asset path from a candidate list."""
    for path in candidates:
        if path.exists():
            return path
    return None


def resolve_preset_dates(preset):
    """Resolve a preset label into a date range."""
    today = date.today()
    if preset == "All Time":
        return None, None
    if preset == "Custom":
        return today - timedelta(days=29), today
    days = TIMEFRAME_PRESETS[preset]
    return today - timedelta(days=days - 1), today


def format_period_label(start_date, end_date):
    """Format a timeframe label for display."""
    def _fmt(value):
        return pd.Timestamp(value).strftime("%b %d, %Y").replace(" 0", " ")

    if not start_date and not end_date:
        return "All Time"
    if start_date == end_date:
        return _fmt(start_date)
    return f"{_fmt(start_date)} to {_fmt(end_date)}"


def get_timeframe_filters():
    """Render global timeframe controls and return the selected date ranges."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("Match Source")
    match_source_label = st.sidebar.radio(
        "Match source",
        list(MATCH_SOURCE_OPTIONS.keys()),
        index=0,
        key="match_source_scope",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Timeframe")
    primary_preset = st.sidebar.selectbox(
        "Primary period",
        list(TIMEFRAME_PRESETS.keys()),
        index=1,
        key="primary_period",
    )
    primary_start, primary_end = resolve_preset_dates(primary_preset)
    if primary_preset == "Custom":
        primary_start, primary_end = st.sidebar.date_input(
            "Primary dates",
            value=(date.today() - timedelta(days=29), date.today()),
            key="primary_dates",
        )

    compare_enabled = st.sidebar.checkbox("Compare to second period", value=False, key="compare_enabled")
    compare_start = compare_end = None
    compare_label = None
    if compare_enabled:
        compare_mode = st.sidebar.selectbox(
            "Comparison period",
            COMPARE_TIMEFRAME_OPTIONS,
            index=0,
            key="compare_period",
        )
        if compare_mode == "Previous Equivalent Period":
            if primary_start and primary_end:
                length = (primary_end - primary_start).days + 1
                compare_end = primary_start - timedelta(days=1)
                compare_start = compare_end - timedelta(days=length - 1)
            else:
                compare_enabled = False
        elif compare_mode == "Custom":
            compare_start, compare_end = st.sidebar.date_input(
                "Comparison dates",
                value=(date.today() - timedelta(days=59), date.today() - timedelta(days=30)),
                key="compare_dates",
            )
        else:
            compare_start, compare_end = resolve_preset_dates(compare_mode)
        if compare_enabled:
            compare_label = format_period_label(compare_start, compare_end)

    return {
        "match_source": MATCH_SOURCE_OPTIONS[match_source_label],
        "match_source_label": match_source_label,
        "primary_preset": primary_preset,
        "primary_start": primary_start,
        "primary_end": primary_end,
        "primary_label": format_period_label(primary_start, primary_end),
        "compare_enabled": compare_enabled,
        "compare_mode": compare_mode if compare_enabled else None,
        "compare_start": compare_start,
        "compare_end": compare_end,
        "compare_label": compare_label,
    }


def apply_theme(fig, title="", height=None, x_title=None, y_title=None):
    """Apply consistent Plotly theme."""
    fig.update_layout(
        plot_bgcolor=COLORS["bg"], paper_bgcolor=COLORS["bg"],
        font_color=COLORS["text"],
        font=dict(size=15),
        title=dict(text=title, font=dict(size=20, color=COLORS["text"])),
        legend=dict(font=dict(size=14)),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    fig.update_xaxes(
        gridcolor=COLORS["grid"],
        title_text=x_title if x_title is not None else fig.layout.xaxis.title.text,
        title_font=dict(size=15, color=COLORS["text"]),
        tickfont=dict(size=14, color=COLORS["text"]),
        linecolor=COLORS["grid"],
        showline=True,
    )
    fig.update_yaxes(
        gridcolor=COLORS["grid"],
        title_text=y_title if y_title is not None else fig.layout.yaxis.title.text,
        title_font=dict(size=15, color=COLORS["text"]),
        tickfont=dict(size=14, color=COLORS["text"]),
        linecolor=COLORS["grid"],
        showline=True,
    )
    if height:
        fig.update_layout(height=height)
    return fig


def style_bar(fig):
    """Apply consistent bar colors."""
    fig.update_traces(marker_color=COLORS["bar"], marker_line_color=COLORS["bar_line"], marker_line_width=1)
    return fig


def pretty_label(value):
    """Convert raw labels into readable display text."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "Unknown"
    text = str(value)
    if text in MATCH_STATUS_LABELS:
        return MATCH_STATUS_LABELS[text]
    if text in VERSION_LABELS:
        return VERSION_LABELS[text]
    return text.replace("_", " ").replace("-", " ").title()


def pretty_match_status(value):
    """Render match statuses with explicit labels."""
    return MATCH_STATUS_LABELS.get(value, pretty_label(value))


def render_page_header(title, subtitle, show_time_filters=True, time_filters=None):
    """Render a branded page header."""
    pills = build_timeframe_pills(time_filters or TIME_FILTERS) if show_time_filters else ""
    st.markdown(
        f"""
        <div class="dashboard-header">
            <div class="dashboard-eyebrow">Bandana Job Match Analytics</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
            {pills}
        </div>
        """,
        unsafe_allow_html=True,
    )


def inline_markdown_to_html(text):
    """Convert simple inline markdown markers into HTML."""
    escaped = html.escape("" if text is None else str(text))
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def render_summary_card(summary_text):
    """Render a text summary card."""
    paragraphs = [segment.strip() for segment in str(summary_text).split("\n") if segment.strip()]
    body = "".join(f"<p>{inline_markdown_to_html(segment)}</p>" for segment in paragraphs)
    st.markdown(f"<div class='summary-card'>{body}</div>", unsafe_allow_html=True)


def render_source_reference(table_fields, timeframe_field):
    """Render source references for a section."""
    sources = " | ".join(table_fields)
    st.markdown(
        "<div class='source-card'>"
        "<div class='source-card-header'>"
        "<span class='source-card-label'>Audit Trail</span>"
        "<h3 class='source-card-title'>Source Fields</h3>"
        "<p class='source-card-subtitle'>Use this section to trace every metric back to the underlying warehouse columns.</p>"
        "</div>"
        "<div class='source-card-body'>"
        f"<p class='source-item-body'><strong>Source fields:</strong> {sources}. "
        f"<strong>Time filter field:</strong> {timeframe_field}.</p>"
        "<p class='source-item-body'><strong>Active match-user scope:</strong> Dashboard metrics are limited to "
        "<code>user.default_resume_id IS NOT NULL</code> and <code>user_job_match_settings.status != 'PAUSED'</code>, "
        "using the latest settings snapshot per <code>user_id</code>.</p>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def comparison_suffix(primary_value, comparison_value, percent=False):
    """Format a comparison suffix between primary and comparison values."""
    if comparison_value is None or pd.isna(comparison_value):
        return ""
    delta = primary_value - comparison_value
    if percent:
        return f" ({delta * 100:+.1f} pts vs comparison)"
    return f" ({delta:+,.0f} vs comparison)"


def safe_ratio(numerator, denominator):
    """Return a ratio or None when the denominator is zero."""
    return (numerator / denominator) if denominator else None


def format_pct(value):
    """Format a decimal ratio as a percent string."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value * 100:.1f}%"


def format_delta_points(current, previous):
    """Format the delta between two decimal ratios in percentage points."""
    if current is None or previous is None or pd.isna(current) or pd.isna(previous):
        return "N/A"
    delta = (current - previous) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f} pts"


def format_currency(value, decimals=0):
    """Format a numeric value as currency."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"${value:,.{decimals}f}"


def format_currency_delta(value, decimals=0):
    """Format a numeric delta as signed currency."""
    if value is None or pd.isna(value):
        return "N/A"
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.{decimals}f}"


def format_period_label(value, grain="month"):
    """Format a date-like cohort bucket label for display."""
    if value is None or pd.isna(value):
        return "N/A"
    ts = pd.Timestamp(value)
    if str(grain).lower() == "week":
        return f"Week of {ts.strftime('%b %d, %Y')}"
    return ts.strftime("%b %Y")


def format_period_column_label(value, grain="month"):
    """Format compact period labels for table columns."""
    if value is None or pd.isna(value):
        return "N/A"
    ts = pd.Timestamp(value)
    if str(grain).lower() == "week":
        return ts.strftime("%b %d")
    return ts.strftime("%b %Y")


def calculate_period_cagr(values):
    """Calculate compound growth across sequential period values."""
    cleaned = [0 if pd.isna(value) else float(value) for value in values]
    if len(cleaned) < 2:
        return None
    first = cleaned[0]
    last = cleaned[-1]
    periods = len(cleaned) - 1
    if periods <= 0 or first < 0 or last < 0:
        return None
    if first == 0:
        return None
    if last == 0:
        return -1.0
    return (last / first) ** (1 / periods) - 1


def get_partial_period_proration(period_start, grain="month", today_value=None):
    """Return proration details when the latest period is still in progress."""
    if period_start is None or pd.isna(period_start):
        return False, 1.0, None, None
    today_ts = pd.Timestamp(today_value or date.today()).normalize()
    start_ts = pd.Timestamp(period_start).normalize()
    if str(grain).lower() == "week":
        current_start = (today_ts - pd.Timedelta(days=today_ts.weekday())).normalize()
        if start_ts != current_start:
            return False, 1.0, None, None
        elapsed_days = (today_ts - start_ts).days + 1
        total_days = 7
    else:
        current_start = today_ts.to_period("M").start_time.normalize()
        if start_ts != current_start:
            return False, 1.0, None, None
        elapsed_days = today_ts.day
        total_days = today_ts.days_in_month
    if elapsed_days <= 0 or elapsed_days >= total_days:
        return False, 1.0, elapsed_days, total_days
    return True, total_days / elapsed_days, elapsed_days, total_days


def build_timeframe_pills(filters):
    """Return compact HTML pills for the active time filters."""
    if not filters:
        return ""
    pills = [f"<span class='page-pill'>Source: {filters.get('match_source_label', 'All Matches')}</span>"]
    pills.append(f"<span class='page-pill'>Primary: {filters['primary_label']}</span>")
    if filters.get("compare_enabled") and filters.get("compare_label"):
        pills.append(f"<span class='page-pill'>Compare: {filters['compare_label']}</span>")
    return f"<div class='page-pill-row'>{''.join(pills)}</div>"


def render_field_lineage(sections):
    """Render section-specific source lineage in a readable card."""
    items = "".join(
        f"<div class='source-card-item'><h4 class='source-item-title'>{title}</h4>"
        f"<p class='source-item-body'>{details}</p></div>"
        for title, details in sections
    )
    st.markdown(
        "<div class='source-card'>"
        "<div class='source-card-header'>"
        "<span class='source-card-label'>Definitions</span>"
        "<h3 class='source-card-title'>Metric Definitions & Source Lineage</h3>"
        "<p class='source-card-subtitle'>What each section represents, how the cohorts are constructed, which fields drive the numbers, and the shared user-scope rules behind the dashboard.</p>"
        "</div>"
        "<div class='source-card-body'>"
        "<div class='source-card-item'><h4 class='source-item-title'>Active Match User Scope</h4>"
        "<p class='source-item-body'>All dashboard cohorts are limited to users whose latest settings snapshot per "
        "<code>user_id</code> has <code>user.default_resume_id IS NOT NULL</code> and "
        "<code>user_job_match_settings.status != 'PAUSED'</code>.</p></div>"
        f"{items}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_page_reference(table_fields=None, timeframe_field=None, lineage_sections=None):
    """Render source references and lineage at the bottom of a page."""
    if not table_fields and not lineage_sections:
        return
    st.markdown("---")
    st.subheader("Reference")
    if table_fields and timeframe_field:
        render_source_reference(table_fields, timeframe_field)
    if lineage_sections:
        render_field_lineage(lineage_sections)


def describe_match_source_filter(match_source):
    """Explain how the active match-source filter is applied."""
    if match_source == "xml":
        return (
            "Restricted to XML-sourced matches where "
            "<code>user_job_match_auto_apply_posting.xml_raw_job_uuid</code> is present or the wrapped "
            "<code>job_postings.xml_job_uuid</code> resolves to <code>xml_job_feed_raw_jobs.uuid</code>."
        )
    if match_source == "native":
        return (
            "Restricted to native matches where both "
            "<code>user_job_match_auto_apply_posting.xml_raw_job_uuid</code> and "
            "<code>job_postings.xml_job_uuid</code> are null."
        )
    return (
        "No source restriction. Includes both native postings and XML-backed postings after the "
        "<code>user_job_match_auto_apply_posting</code> wrapper join."
    )


def coerce_date_range(value, fallback_start, fallback_end):
    """Normalize date input widget output into a start/end pair."""
    if isinstance(value, (list, tuple)):
        if len(value) >= 2:
            start_value, end_value = value[0], value[1]
        elif len(value) == 1:
            start_value = end_value = value[0]
        else:
            return fallback_start, fallback_end
    elif value:
        start_value = end_value = value
    else:
        return fallback_start, fallback_end
    return pd.Timestamp(start_value).date(), pd.Timestamp(end_value).date()


def resolve_compare_dates(compare_mode, primary_start, primary_end):
    """Resolve comparison dates for a preset mode."""
    if compare_mode == "Previous Equivalent Period":
        if not primary_start or not primary_end:
            return None, None
        window_length = (primary_end - primary_start).days + 1
        compare_end = primary_start - timedelta(days=1)
        compare_start = compare_end - timedelta(days=window_length - 1)
        return compare_start, compare_end
    return resolve_preset_dates(compare_mode)


def get_page_time_filters(prefix, base_filters=None):
    """Resolve page-local timeframe state with fallback to the global sidebar controls."""
    base_filters = base_filters or {}
    default_primary_preset = base_filters.get("primary_preset", "Last 30 Days")
    primary_preset = st.session_state.get(f"{prefix}_primary_preset", default_primary_preset)

    default_primary_start = base_filters.get("primary_start") or (date.today() - timedelta(days=29))
    default_primary_end = base_filters.get("primary_end") or date.today()
    if primary_preset == "Custom":
        primary_start, primary_end = coerce_date_range(
            st.session_state.get(f"{prefix}_primary_dates", (default_primary_start, default_primary_end)),
            default_primary_start,
            default_primary_end,
        )
    else:
        primary_start, primary_end = resolve_preset_dates(primary_preset)

    compare_enabled = st.session_state.get(f"{prefix}_compare_enabled", base_filters.get("compare_enabled", False))
    default_compare_mode = base_filters.get("compare_mode", "Previous Equivalent Period") or "Previous Equivalent Period"
    compare_mode = st.session_state.get(f"{prefix}_compare_mode", default_compare_mode)
    compare_start = compare_end = None
    compare_label = None
    if compare_enabled:
        if compare_mode == "Custom":
            default_compare_start = base_filters.get("compare_start") or (date.today() - timedelta(days=59))
            default_compare_end = base_filters.get("compare_end") or (date.today() - timedelta(days=30))
            compare_start, compare_end = coerce_date_range(
                st.session_state.get(f"{prefix}_compare_dates", (default_compare_start, default_compare_end)),
                default_compare_start,
                default_compare_end,
            )
        else:
            compare_start, compare_end = resolve_compare_dates(compare_mode, primary_start, primary_end)
            if compare_start is None or compare_end is None:
                compare_enabled = False
                compare_mode = None
        if compare_enabled:
            compare_label = format_period_label(compare_start, compare_end)

    return {
        "match_source": base_filters.get("match_source", "all"),
        "match_source_label": base_filters.get("match_source_label", "All Matches"),
        "primary_preset": primary_preset,
        "primary_start": primary_start,
        "primary_end": primary_end,
        "primary_label": format_period_label(primary_start, primary_end),
        "compare_enabled": compare_enabled,
        "compare_mode": compare_mode,
        "compare_start": compare_start,
        "compare_end": compare_end,
        "compare_label": compare_label,
    }


def render_page_time_controls(prefix, filters):
    """Render page-level created_at controls for a dashboard tab."""
    with st.container(border=True):
        st.markdown("<p class='filter-panel-title'>Created_at Window</p>", unsafe_allow_html=True)
        st.markdown(
            "<p class='filter-panel-subtitle'>Use quick time windows or custom dates. "
            "On demand pages, current user counts come from the latest active match-user snapshot per <code>user_id</code> "
            "(resume present and not paused); "
            "the date window filters match outcomes by <code>user_job_match_auto_apply_posting_match.created_at</code>. "
            f"Current match-source scope: <code>{filters.get('match_source_label', 'All Matches')}</code>.</p>",
            unsafe_allow_html=True,
        )

        primary_col, compare_col = st.columns([3.4, 2.0])
        preset_options = list(TIMEFRAME_PRESETS.keys())
        default_primary_index = preset_options.index(filters["primary_preset"]) if filters["primary_preset"] in preset_options else 1

        with primary_col:
            st.radio(
                "Primary period",
                preset_options,
                index=default_primary_index,
                horizontal=True,
                key=f"{prefix}_primary_preset",
            )
            if st.session_state.get(f"{prefix}_primary_preset", filters["primary_preset"]) == "Custom":
                st.date_input(
                    "Primary dates",
                    value=(filters["primary_start"], filters["primary_end"]),
                    key=f"{prefix}_primary_dates",
                )

        with compare_col:
            st.checkbox(
                "Compare to second period",
                value=filters["compare_enabled"],
                key=f"{prefix}_compare_enabled",
            )
            if st.session_state.get(f"{prefix}_compare_enabled", filters["compare_enabled"]):
                default_compare_mode = filters.get("compare_mode") or "Previous Equivalent Period"
                default_compare_index = COMPARE_TIMEFRAME_OPTIONS.index(default_compare_mode) if default_compare_mode in COMPARE_TIMEFRAME_OPTIONS else 0
                st.selectbox(
                    "Comparison period",
                    COMPARE_TIMEFRAME_OPTIONS,
                    index=default_compare_index,
                    key=f"{prefix}_compare_mode",
                )
                if st.session_state.get(f"{prefix}_compare_mode", default_compare_mode) == "Custom":
                    st.date_input(
                        "Comparison dates",
                        value=(
                            filters.get("compare_start") or (date.today() - timedelta(days=59)),
                            filters.get("compare_end") or (date.today() - timedelta(days=30)),
                        ),
                        key=f"{prefix}_compare_dates",
                    )


def percent_background_style(value):
    """Color-code percentage columns with solid bands."""
    if value is None or pd.isna(value):
        return ""
    if value < 40:
        color = COLORS["danger_soft"]
    elif value < 70:
        color = COLORS["warning_soft"]
    else:
        color = COLORS["success_soft"]
    return f"background-color: {color}; color: {COLORS['text']}; font-weight: 700;"


def delta_background_style(value):
    """Color-code delta columns around zero with solid colors."""
    if value is None or pd.isna(value):
        return ""
    if value >= 3:
        color = COLORS["success_soft"]
    elif value <= -3:
        color = COLORS["danger_soft"]
    else:
        color = COLORS["neutral_soft"]
    return f"background-color: {color}; color: {COLORS['text']}; font-weight: 700;"


def blend_hex_colors(start_hex, end_hex, weight):
    """Blend two hex colors into a single intermediate color."""
    weight = max(0.0, min(1.0, float(weight)))
    start_hex = start_hex.lstrip("#")
    end_hex = end_hex.lstrip("#")
    start_rgb = tuple(int(start_hex[i : i + 2], 16) for i in (0, 2, 4))
    end_rgb = tuple(int(end_hex[i : i + 2], 16) for i in (0, 2, 4))
    blended = tuple(round(start + (end - start) * weight) for start, end in zip(start_rgb, end_rgb))
    return "#{:02X}{:02X}{:02X}".format(*blended)


def growth_background_style(value):
    """Color-code growth-rate columns with a stronger directional ramp."""
    if value is None or pd.isna(value):
        return ""
    value = float(value)
    if value >= 0:
        capped = min(value, 0.5)
        intensity = capped / 0.5 if capped else 0
        if intensity < 0.2:
            color = blend_hex_colors(COLORS["neutral_soft"], COLORS["sage_soft"], intensity / 0.2 if intensity else 0)
            text_color = COLORS["text"]
        elif intensity < 0.55:
            color = blend_hex_colors(COLORS["sage_soft"], COLORS["success_soft"], (intensity - 0.2) / 0.35)
            text_color = COLORS["text"]
        else:
            color = blend_hex_colors(COLORS["success_soft"], COLORS["success"], (intensity - 0.55) / 0.45)
            text_color = COLORS["surface"] if intensity >= 0.82 else COLORS["text"]
    elif value <= -0.15:
        capped = min(abs(value), 0.5)
        intensity = capped / 0.5 if capped else 0
        if intensity < 0.4:
            color = blend_hex_colors(COLORS["neutral_soft"], COLORS["warning_soft"], intensity / 0.4 if intensity else 0)
            text_color = COLORS["text"]
        else:
            color = blend_hex_colors(COLORS["warning_soft"], COLORS["danger"], (intensity - 0.4) / 0.6)
            text_color = COLORS["surface"] if intensity >= 0.82 else COLORS["text"]
    else:
        if value < 0:
            capped = min(abs(value), 0.15)
            color = blend_hex_colors(COLORS["neutral_soft"], COLORS["warning_soft"], capped / 0.15 if capped else 0)
        else:
            capped = min(value, 0.15)
            color = blend_hex_colors(COLORS["neutral_soft"], COLORS["sage_soft"], capped / 0.15 if capped else 0)
        text_color = COLORS["text"]
    return f"background-color: {color}; color: {text_color}; font-weight: 800;"


def emphasis_style(_value):
    """Bold a value without adding a background treatment."""
    return f"color: {COLORS['text']}; font-weight: 800;"


def gap_stage_style(value):
    """Style the stage name for the largest gap in a funnel."""
    palette = {
        "No Match Assigned": COLORS["danger_soft"],
        "Not Approved After Match": COLORS["warning_soft"],
        "Approved But Not Applied": COLORS["info_soft"],
    }
    color = palette.get(value)
    if not color:
        return ""
    return f"background-color: {color}; color: {COLORS['text']}; font-weight: 700;"


def low_coverage_row_style(row, coverage_column, threshold):
    """Highlight an entire row when coverage is below a threshold."""
    coverage_value = row.get(coverage_column)
    if coverage_value is None or pd.isna(coverage_value):
        return [""] * len(row)
    if coverage_value < threshold:
        color = COLORS["danger_soft"] if coverage_value < threshold * 0.75 else COLORS["warning_soft"]
        return [f"background-color: {color}; color: {COLORS['text']}; font-weight: 700;"] * len(row)
    return [""] * len(row)


def build_table_styler(
    df,
    formatters,
    percent_columns=None,
    delta_columns=None,
    stage_columns=None,
    row_highlight_column=None,
    row_highlight_threshold=None,
    emphasis_columns=None,
    custom_style_columns=None,
):
    """Apply consistent table formatting and simple conditional styling."""
    active_formatters = {column: fmt for column, fmt in formatters.items() if column in df.columns}
    styler = df.style.format(active_formatters, na_rep="—").set_table_styles(
        [
            {
                "selector": "thead th",
                "props": [
                    ("background-color", COLORS["neutral_soft"]),
                    ("color", COLORS["brown"]),
                    ("font-weight", "800"),
                    ("border-bottom", f"1px solid {COLORS['panel_border']}"),
                ],
            },
            {
                "selector": "thead th.col_heading",
                "props": [
                    ("background-color", COLORS["neutral_soft"]),
                    ("color", COLORS["brown"]),
                    ("font-weight", "800"),
                ],
            },
        ],
        overwrite=False,
    )
    if row_highlight_column and row_highlight_column in df.columns and row_highlight_threshold is not None:
        styler = styler.apply(
            lambda row: low_coverage_row_style(row, row_highlight_column, row_highlight_threshold),
            axis=1,
        )
    for column in percent_columns or []:
        if column in df.columns:
            styler = styler.map(percent_background_style, subset=[column])
    for column in delta_columns or []:
        if column in df.columns:
            styler = styler.map(delta_background_style, subset=[column])
    for column in stage_columns or []:
        if column in df.columns:
            styler = styler.map(gap_stage_style, subset=[column])
    for column in emphasis_columns or []:
        if column in df.columns:
            styler = styler.map(emphasis_style, subset=[column])
    for column, style_fn in (custom_style_columns or {}).items():
        if column in df.columns:
            styler = styler.map(style_fn, subset=[column])
    return styler


def get_largest_gap_stage(row):
    """Identify the stage with the largest absolute user drop-off."""
    dropoffs = {
        "No Match Assigned": max(row.get("users", 0) - row.get("users_with_match", 0), 0),
        "Not Approved After Match": max(row.get("users_with_match", 0) - row.get("users_with_approved_match", 0), 0),
        "Approved But Not Applied": max(row.get("users_with_approved_match", 0) - row.get("users_with_application", 0), 0),
    }
    stage, count = max(dropoffs.items(), key=lambda item: item[1])
    return stage, count


def build_location_rollup(df):
    """Aggregate location performance into weighted KPI values."""
    if df.empty:
        return {}
    total_pairs = df["users"].sum()
    matched_pairs = df["users_with_match"].sum()
    approved_pairs = df["users_with_approved_match"].sum()
    applied_pairs = df["users_with_application"].sum()
    return {
        "user_location_pairs": int(total_pairs),
        "matched_pairs": int(matched_pairs),
        "approved_pairs": int(approved_pairs),
        "applied_pairs": int(applied_pairs),
        "match_rate": safe_ratio(matched_pairs, total_pairs),
        "approval_rate": safe_ratio(approved_pairs, matched_pairs),
        "application_rate": safe_ratio(applied_pairs, approved_pairs),
        "users_without_match": int((df["users"] - df["users_with_match"]).clip(lower=0).sum()),
        "realized_cpa": float(df["realized_cpa"].fillna(0).sum()),
    }


def wrap_chart_label(label, rank=None, width=18):
    """Wrap long category labels so vertical charts stay legible."""
    parts = wrap(str(label), width=width) or [str(label)]
    if rank is not None:
        parts[0] = f"{rank}. {parts[0]}"
    return "<br>".join(parts)


def match_supply_label(match_source):
    """Return a user-facing label for the active supply scope."""
    if match_source == "xml":
        return "XML job supply"
    if match_source == "native":
        return "native job supply"
    return "job supply"


def build_match_performance_summary(weekly_df, maturity_days=28, match_source="all"):
    """Summarize mature weekly match cohort performance."""
    if weekly_df.empty:
        return "No mature weekly match cohorts are available yet."

    compare_window = 4 if len(weekly_df) >= 8 else max(1, len(weekly_df) // 2)
    recent = weekly_df.tail(compare_window)
    previous = (
        weekly_df.iloc[-(compare_window * 2):-compare_window]
        if len(weekly_df) >= compare_window * 2
        else pd.DataFrame()
    )

    recent_total = int(recent["total_matches"].sum())
    recent_decision = safe_ratio(recent["decided_matches"].sum(), recent_total)
    recent_approval = safe_ratio(recent["approved_matches"].sum(), recent["decided_matches"].sum())
    recent_rejection = safe_ratio(recent["rejected_matches"].sum(), recent["decided_matches"].sum())
    recent_application = safe_ratio(recent["applied_matches"].sum(), recent["approved_matches"].sum())
    recent_pending = int(recent["pending_matches"].sum())
    recent_approved_waiting = int(
        (
            recent["approved_matches"]
            - recent["applied_matches"]
            - recent["failed_matches"]
            - recent["account_exists_matches"]
        ).clip(lower=0).sum()
    )
    supply_label = match_supply_label(match_source)
    if recent_pending >= recent_approved_waiting:
        priority_text = (
            f"the biggest immediate lever is expanding effective {supply_label} and moving **{recent_pending:,}** "
            f"still-pending matches into a user decision"
        )
    else:
        priority_text = (
            f"the biggest immediate lever is converting **{recent_approved_waiting:,}** already-approved matches "
            f"into completed applications"
        )

    summary = (
        f"Primary opportunity: increase {supply_label} against existing user demand. "
        f"Across the last **{compare_window}** mature weekly cohorts, Bandana generated **{recent_total:,} matches**, "
        f"but only **{format_pct(recent_decision)}** reached a user decision. Of decided matches, "
        f"**{format_pct(recent_approval)}** were approved and **{format_pct(recent_application)}** of approved matches became applications. "
        f"That means {priority_text}."
    )

    if previous.empty:
        return summary

    previous_approval = safe_ratio(previous["approved_matches"].sum(), previous["decided_matches"].sum())
    previous_rejection = safe_ratio(previous["rejected_matches"].sum(), previous["decided_matches"].sum())
    previous_application = safe_ratio(previous["applied_matches"].sum(), previous["approved_matches"].sum())

    return (
        f"{summary} Versus the previous {compare_window} cohorts, approval moved "
        f"**{format_delta_points(recent_approval, previous_approval)}**, rejection moved "
        f"**{format_delta_points(recent_rejection, previous_rejection)}**, and application moved "
        f"**{format_delta_points(recent_application, previous_application)}**."
    )


def build_signup_cohort_summary(signup_df, window_weeks=12, match_source="all"):
    """Summarize complete signup cohort performance over a fixed observation window."""
    if signup_df.empty:
        return "No complete signup cohorts are available yet."

    compare_window = 3 if len(signup_df) >= 6 else max(1, len(signup_df) // 2)
    recent = signup_df.tail(compare_window)
    previous = (
        signup_df.iloc[-(compare_window * 2):-compare_window]
        if len(signup_df) >= compare_window * 2
        else pd.DataFrame()
    )

    recent_users = int(recent["cohort_users"].sum())
    recent_matches_per_user = safe_ratio(recent["total_matches"].sum(), recent_users)
    recent_approval = safe_ratio(recent["approved_matches"].sum(), recent["decided_matches"].sum())
    recent_rejection = safe_ratio(recent["rejected_matches"].sum(), recent["decided_matches"].sum())
    recent_application = safe_ratio(recent["applied_matches"].sum(), recent["approved_matches"].sum())
    supply_label = match_supply_label(match_source)

    summary = (
        f"New-user opportunity: get more {supply_label} in front of users earlier. "
        f"Across the last **{compare_window}** complete signup cohorts, **{recent_users:,} users** averaged "
        f"**{recent_matches_per_user:.1f} matches per user** in their first {window_weeks} weeks. "
        f"Once users saw matches, approval ran at **{format_pct(recent_approval)}** and application after approval at "
        f"**{format_pct(recent_application)}**, so the first lever is still coverage rather than only downstream conversion."
    )

    if previous.empty:
        return summary

    previous_matches_per_user = safe_ratio(previous["total_matches"].sum(), previous["cohort_users"].sum())
    previous_approval = safe_ratio(previous["approved_matches"].sum(), previous["decided_matches"].sum())
    previous_application = safe_ratio(previous["applied_matches"].sum(), previous["approved_matches"].sum())

    return (
        f"{summary} Versus the previous {compare_window} complete cohorts, matches per user changed "
        f"**{recent_matches_per_user - previous_matches_per_user:+.1f}**, approval moved "
        f"**{format_delta_points(recent_approval, previous_approval)}**, and application moved "
        f"**{format_delta_points(recent_application, previous_application)}**."
    )


def build_match_funnel_summary(funnel_df, comparison_df=None, match_source="all"):
    """Create a funnel summary focused on conversion loss and revenue opportunity."""
    if funnel_df.empty:
        return "No match funnel records are available for the selected timeframe."

    counts = dict(zip(funnel_df["status"], funnel_df["count"]))
    total = int(funnel_df["count"].sum())
    decided = sum(counts.get(s, 0) for s in ["USER_APPROVED", "CONTRACTOR_PENDING", "APPLIED", "APP_FAILED", "ACCOUNT_EXISTS", "USER_REJECTED", "JOB_EXPIRED"])
    approved = sum(counts.get(s, 0) for s in ["USER_APPROVED", "CONTRACTOR_PENDING", "APPLIED", "APP_FAILED", "ACCOUNT_EXISTS"])
    applied = counts.get("APPLIED", 0)
    failed = counts.get("APP_FAILED", 0) + counts.get("ACCOUNT_EXISTS", 0) + counts.get("JOB_EXPIRED", 0)
    pending_review = counts.get("USER_PENDING", 0)
    approved_waiting = counts.get("USER_APPROVED", 0) + counts.get("CONTRACTOR_PENDING", 0)
    approval_rate = safe_ratio(approved, decided)
    application_rate = safe_ratio(applied, approved)
    supply_label = match_supply_label(match_source)
    if pending_review >= max(approved_waiting, failed):
        biggest_issue = f"more of the current {supply_label} is still stuck at review, with **{pending_review:,}** matches pending"
    elif approved_waiting >= failed:
        biggest_issue = f"users already approved **{approved_waiting:,}** matches that still have not turned into applications"
    else:
        biggest_issue = f"**{failed:,}** approved-or-near-approved matches failed before completion"

    summary = (
        f"Main improvement area: maximize useful matches first, then tighten the approval-to-apply path. "
        f"Out of **{total:,}** current matches, only **{format_pct(safe_ratio(decided, total))}** moved beyond pending review. "
        f"Approval is **{format_pct(approval_rate)}** once a decision happens, and application after approval is "
        f"**{format_pct(application_rate)}**. Right now, {biggest_issue}."
    )
    if comparison_df is None or comparison_df.empty:
        return summary

    comp_counts = dict(zip(comparison_df["status"], comparison_df["count"]))
    comp_decided = sum(comp_counts.get(s, 0) for s in ["USER_APPROVED", "CONTRACTOR_PENDING", "APPLIED", "APP_FAILED", "ACCOUNT_EXISTS", "USER_REJECTED", "JOB_EXPIRED"])
    comp_approved = sum(comp_counts.get(s, 0) for s in ["USER_APPROVED", "CONTRACTOR_PENDING", "APPLIED", "APP_FAILED", "ACCOUNT_EXISTS"])
    comp_applied = comp_counts.get("APPLIED", 0)
    return (
        f"{summary} Versus the comparison period, approval moved "
        f"**{format_delta_points(approval_rate, safe_ratio(comp_approved, comp_decided))}** and application moved "
        f"**{format_delta_points(application_rate, safe_ratio(comp_applied, comp_approved))}**."
    )


def build_location_summary(location_df, combo_df, comparison_df=None, match_source="all"):
    """Summarize location-level funnel performance."""
    if location_df.empty:
        return "No target-location cohorts are available for the selected timeframe."

    location_copy = location_df.copy()
    location_copy["users_without_match"] = (location_copy["users"] - location_copy["users_with_match"]).clip(lower=0)
    combo_copy = combo_df.copy()
    combo_copy["users_without_match"] = (combo_copy["users"] - combo_copy["users_with_match"]).clip(lower=0)

    top_location = location_copy.sort_values(["users", "users_with_match"], ascending=[False, False]).iloc[0]
    highest_gap_location = location_copy.sort_values(["users_without_match", "users"], ascending=[False, False]).iloc[0]
    best_cpa_location = (
        location_copy[location_copy["users_with_application"] > 0]
        .sort_values(["avg_cpa_per_application", "users_with_application"], ascending=[False, False])
        .head(1)
    )
    top_gap_combo = pd.DataFrame()
    if not combo_copy.empty:
        combo_copy[["largest_gap_stage", "largest_gap_users"]] = combo_copy.apply(
            lambda row: pd.Series(get_largest_gap_stage(row)),
            axis=1,
        )
        top_gap_combo = combo_copy.sort_values(["users_without_match", "users"], ascending=[False, False]).head(1)

    rollup = build_location_rollup(location_copy)
    supply_label = match_supply_label(match_source)
    conversion_priority = "approval" if (rollup.get("approval_rate") or 0) < (rollup.get("application_rate") or 0) else "application"
    summary_parts = [
        f"Biggest location supply opportunity: **{highest_gap_location['location']}** still has **{int(highest_gap_location['users_without_match']):,}** "
        f"user-location preferences with no coverage from current {supply_label}.",
        f"In the highest-demand market, **{top_location['location']}**, current match coverage is only "
        f"**{0 if pd.isna(top_location['match_user_rate']) else top_location['match_user_rate'] * 100:.1f}%** across "
        f"**{int(top_location['users']):,}** preferences, so expanding match supply remains the first priority.",
    ]

    if not top_gap_combo.empty:
        gap = top_gap_combo.iloc[0]
        summary_parts.append(
            f"Highest-priority location x role cohort: **{gap['location']} / {gap['role']}**. "
            f"The main break is **{gap['largest_gap_stage']}**, affecting **{int(gap['largest_gap_users']):,}** users."
        )

    if not best_cpa_location.empty:
        monetized = best_cpa_location.iloc[0]
        summary_parts.append(
            f"Best current monetization signal: **{monetized['location']}** is generating "
            f"**{format_currency(monetized['avg_cpa_per_application'])} per completed application**, so improving supply in similar markets should have the best payoff."
        )

    if rollup:
        summary_parts.append(
            f"Weighted location funnel today: coverage **{format_pct(rollup['match_rate'])}**, approval after match "
            f"**{format_pct(rollup['approval_rate'])}**, and application after approval **{format_pct(rollup['application_rate'])}**. "
            f"After supply, the next operational focus should be **{conversion_priority} conversion**."
        )

    summary = "\n".join(summary_parts)

    if comparison_df is None or comparison_df.empty:
        return summary

    current_rollup = build_location_rollup(location_df)
    previous_rollup = build_location_rollup(comparison_df)
    summary_parts.append(
        f"Vs comparison period: weighted match coverage moved "
        f"**{format_delta_points(current_rollup.get('match_rate'), previous_rollup.get('match_rate'))}** and realized CPA moved "
        f"**{format_currency_delta(current_rollup.get('realized_cpa', 0) - previous_rollup.get('realized_cpa', 0))}**."
    )
    return "\n".join(summary_parts)


def build_user_cohort_page_summary(engagement_df, signup_df, comparison_df=None):
    """Summarize user cohort takeaways."""
    if signup_df.empty:
        return "No user cohort data is available for the selected timeframe."

    latest_month = signup_df.groupby("month")["count"].sum().reset_index().sort_values("month").tail(1)
    inactive_bucket = engagement_df.sort_values("count", ascending=False).iloc[0] if not engagement_df.empty else None
    summary = (
        f"The latest signup month in view brought in **{int(latest_month['count'].iloc[0]):,} users**. "
        f"{f'The largest engagement bucket is **{inactive_bucket['bucket']}** at **{int(inactive_bucket['count']):,} users**, which is a reactivation opportunity.' if inactive_bucket is not None else ''}"
    )
    if comparison_df is None or comparison_df.empty:
        return summary
    current_total = int(signup_df["count"].sum())
    previous_total = int(comparison_df["count"].sum())
    return f"{summary} Total signups moved **{current_total - previous_total:+,}** versus the comparison period."


def build_role_summary(role_df, combo_df, ind_df, comparison_df=None, match_source="all"):
    """Summarize role-level funnel performance and gaps."""
    if role_df.empty:
        return "No target-role cohorts are available for the selected timeframe."

    role_copy = role_df.copy()
    role_copy["users_without_match"] = (role_copy["users"] - role_copy["users_with_match"]).clip(lower=0)
    combo_copy = combo_df.copy()
    combo_copy["users_without_match"] = (combo_copy["users"] - combo_copy["users_with_match"]).clip(lower=0)

    top_role = role_copy.sort_values(["users", "users_with_match"], ascending=[False, False]).iloc[0]
    highest_gap_role = role_copy.sort_values(["users_without_match", "users"], ascending=[False, False]).iloc[0]
    best_cpa_role = (
        role_copy[role_copy["users_with_application"] > 0]
        .sort_values(["avg_cpa_per_application", "users_with_application"], ascending=[False, False])
        .head(1)
    )
    top_gap_combo = pd.DataFrame()
    if not combo_copy.empty:
        combo_copy[["largest_gap_stage", "largest_gap_users"]] = combo_copy.apply(
            lambda row: pd.Series(get_largest_gap_stage(row)),
            axis=1,
        )
        top_gap_combo = combo_copy.sort_values(["users_without_match", "users"], ascending=[False, False]).head(1)
    top_industry = ind_df.iloc[0] if not ind_df.empty else None

    rollup = build_location_rollup(role_copy)
    supply_label = match_supply_label(match_source)
    conversion_priority = "approval" if (rollup.get("approval_rate") or 0) < (rollup.get("application_rate") or 0) else "application"
    summary_parts = [
        f"Biggest role supply opportunity: **{highest_gap_role['role']}** still has **{int(highest_gap_role['users_without_match']):,}** "
        f"user-role preferences without coverage from current {supply_label}.",
        f"In the highest-demand role, **{top_role['role']}**, current match coverage is only "
        f"**{0 if pd.isna(top_role['match_user_rate']) else top_role['match_user_rate'] * 100:.1f}%** across "
        f"**{int(top_role['users']):,}** preferences, so increasing supply against this role base remains the first lever.",
    ]

    if top_industry is not None:
        summary_parts.append(
            f"Leading industry context: **{top_industry['industry']}** with **{int(top_industry['count']):,}** users selecting it."
        )

    if not top_gap_combo.empty:
        gap = top_gap_combo.iloc[0]
        summary_parts.append(
            f"Highest-priority role x geography cohort: **{gap['role']} / {gap['location']}**. "
            f"The main break is **{gap['largest_gap_stage']}**, affecting **{int(gap['largest_gap_users']):,}** users."
        )

    if not best_cpa_role.empty:
        monetized = best_cpa_role.iloc[0]
        summary_parts.append(
            f"Best current monetization signal: **{monetized['role']}** is generating "
            f"**{format_currency(monetized['avg_cpa_per_application'])} per completed application**, so additional supply in similar roles should be high value."
        )

    if rollup:
        summary_parts.append(
            f"Weighted role funnel today: coverage **{format_pct(rollup['match_rate'])}**, approval after match is "
            f"**{format_pct(rollup['approval_rate'])}**, and application after approval is **{format_pct(rollup['application_rate'])}**. "
            f"After supply, the next operational focus should be **{conversion_priority} conversion**."
        )

    summary = " ".join(summary_parts)
    if comparison_df is None or comparison_df.empty:
        return summary

    current_rollup = build_location_rollup(role_df)
    previous_rollup = build_location_rollup(comparison_df)
    return (
        f"{summary} Versus the comparison period, weighted role coverage moved "
        f"**{format_delta_points(current_rollup.get('match_rate'), previous_rollup.get('match_rate'))}** and "
        f"realized CPA moved **{format_currency_delta(current_rollup.get('realized_cpa', 0) - previous_rollup.get('realized_cpa', 0))}**."
    )


def build_match_timing_summary(timing_df, dow_df, comparison_df=None, match_source="all"):
    """Summarize timing opportunities."""
    best_version = timing_df.sort_values("avg_hours_to_application").iloc[0] if not timing_df.empty else None
    top_day = dow_df.sort_values("count", ascending=False).iloc[0] if not dow_df.empty else None
    if best_version is None:
        return "No match timing data is available for the selected timeframe."
    summary = (
        f"Timing opportunity: once {match_supply_label(match_source)} reaches a user, revenue improves when approved matches convert faster. "
        f"The fastest current version is **{pretty_label(best_version['version'])}**, averaging "
        f"**{0 if pd.isna(best_version['avg_hours_to_application']) else best_version['avg_hours_to_application']:.1f} hours** from approval to application. "
        f"{f'The heaviest match day is **{top_day['day_name']}** with **{int(top_day['count']):,} matches**, which is where process latency matters most.' if top_day is not None else ''}"
    )
    if comparison_df is None or comparison_df.empty:
        return summary
    current_weight = timing_df.loc[timing_df["avg_hours_to_application"].notna(), "total"].sum()
    previous_weight = comparison_df.loc[comparison_df["avg_hours_to_application"].notna(), "total"].sum()
    current_avg = safe_ratio(
        (timing_df["avg_hours_to_application"].fillna(0) * timing_df["total"]).sum(),
        current_weight,
    )
    previous_avg = safe_ratio(
        (comparison_df["avg_hours_to_application"].fillna(0) * comparison_df["total"]).sum(),
        previous_weight,
    )
    if current_avg is None or previous_avg is None:
        return summary
    return f"{summary} Time from approval to application moved **{current_avg - previous_avg:+.1f} hours** versus the comparison period."


def build_contractor_summary(df, comparison_df=None, match_source="all"):
    """Summarize contractor performance."""
    if df.empty:
        return "No contractor data is available for the selected timeframe."
    top = df.sort_values(["conversion_rate", "total_assigned"], ascending=[False, False]).iloc[0]
    median_conversion = df["conversion_rate"].median()
    summary = (
        f"Operational opportunity: once {match_supply_label(match_source)} creates approved matches, contractor execution determines how much of that supply becomes paid applications. "
        f"Top contractor performance is **{top['contractor_id']}** at **{top['conversion_rate'] * 100:.1f}%** conversion across "
        f"**{int(top['total_assigned']):,} assignments**, versus a median contractor conversion of **{median_conversion * 100:.1f}%**."
    )
    if comparison_df is None or comparison_df.empty:
        return summary
    current_avg = df["conversion_rate"].mean()
    previous_avg = comparison_df["conversion_rate"].mean()
    return f"{summary} Average contractor conversion moved **{format_delta_points(current_avg, previous_avg)}** versus the comparison period."


# ── Session State ─────────────────────────────────────────────────────────────

if "last_refreshed" not in st.session_state:
    st.session_state["last_refreshed"] = datetime.now()
if "query_history" not in st.session_state:
    st.session_state["query_history"] = []

# ── Sidebar Navigation ────────────────────────────────────────────────────────

sidebar_wordmark = first_existing_path(WORDMARK_CANDIDATES)
if sidebar_wordmark:
    st.sidebar.image(str(sidebar_wordmark), use_container_width=True)
st.sidebar.title("Job Match Analysis")
st.sidebar.caption(f"Last updated: {st.session_state['last_refreshed'].strftime('%b %d, %Y %I:%M %p')}")
if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.session_state["last_refreshed"] = datetime.now()
    st.rerun()

st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigation",
    ["Query Lab", "Overview", "Match Funnel", "User Cohorts",
     "Location Analysis", "Role & Industry", "Match Timing",
     "Contractor Performance", "Data Explorer"],
    label_visibility="collapsed",
)
TIME_FILTERS = get_timeframe_filters()


# ══════════════════════════════════════════════════════════════════════════════
# TAB: Query Lab
# ══════════════════════════════════════════════════════════════════════════════

def render_query_lab():
    render_page_header("Query Lab", "Ask questions in plain English and turn them into BigQuery SQL against the Job Match warehouse.", show_time_filters=False)

    question = st.text_area(
        "What do you want to know?",
        placeholder="e.g. Show me top 20 users by total matches with their email and status",
        height=100,
    )

    col_gen, col_run = st.columns([1, 1])

    if "generated_sql" not in st.session_state:
        st.session_state["generated_sql"] = ""

    with col_gen:
        if st.button("Generate SQL", use_container_width=True):
            if not question.strip():
                st.warning("Enter a question first.")
                return
            if not config.ANTHROPIC_API_KEY:
                st.error("Set ANTHROPIC_API_KEY in your .env file.")
                return
            with st.spinner("Generating SQL..."):
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
                    # Load data model context
                    with open(config.CLAUDE_MD_PATH, "r") as f:
                        data_model = f.read()
                    msg = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=2000,
                        system=f"""You are a BigQuery SQL expert. Given the data model below, generate a single BigQuery SQL query that answers the user's question.

Rules:
- Return ONLY the SQL query, no explanation or markdown
- Use fully qualified table names: `{config.PROJECT_ID}.{config.DATASET}.<table>`
- Use standard BigQuery SQL syntax
- Limit results to 10000 rows max
- For nested/repeated fields, use UNNEST()
- Always handle NULLs appropriately

Data Model:
{data_model}""",
                        messages=[{"role": "user", "content": question}],
                    )
                    sql = msg.content[0].text.strip()
                    if sql.startswith("```"):
                        sql = sql.split("\n", 1)[1] if "\n" in sql else sql[3:]
                    if sql.endswith("```"):
                        sql = sql[:-3]
                    st.session_state["generated_sql"] = sql.strip()
                except Exception as e:
                    st.error(f"API error: {e}")

    sql_input = st.text_area(
        "Generated SQL (editable)",
        value=st.session_state.get("generated_sql", ""),
        height=200,
        key="sql_editor",
    )

    with col_run:
        if st.button("Run Query", use_container_width=True):
            if not sql_input.strip():
                st.warning("No SQL to run.")
                return
            with st.spinner("Running query..."):
                try:
                    result_df = bq_client.run_query(sql_input)
                    st.session_state["query_result"] = result_df
                    st.session_state["query_history"].append({
                        "question": question,
                        "sql": sql_input,
                        "rows": len(result_df),
                        "time": datetime.now().strftime("%I:%M %p"),
                    })
                except Exception as e:
                    st.error(f"Query error: {e}")
                    st.session_state["query_result"] = None

    if "query_result" in st.session_state and st.session_state["query_result"] is not None:
        df = st.session_state["query_result"]
        st.subheader(f"Results ({len(df):,} rows)")
        st.dataframe(df, use_container_width=True, height=400)

    if st.session_state["query_history"]:
        with st.expander(f"Query History ({len(st.session_state['query_history'])})"):
            for i, h in enumerate(reversed(st.session_state["query_history"])):
                st.markdown(f"**{h['time']}** — {h['question']} ({h['rows']} rows)")
                st.code(h["sql"], language="sql")


# ══════════════════════════════════════════════════════════════════════════════
# TAB: Overview
# ══════════════════════════════════════════════════════════════════════════════

def render_overview():
    render_page_header("Overview", "Key metrics, weekly match dynamics, and signup cohort performance for the selected timeframe.")
    match_source = TIME_FILTERS["match_source"]
    start_date = TIME_FILTERS["primary_start"]
    end_date = TIME_FILTERS["primary_end"]
    compare_start = TIME_FILTERS["compare_start"] if TIME_FILTERS["compare_enabled"] else None
    compare_end = TIME_FILTERS["compare_end"] if TIME_FILTERS["compare_enabled"] else None
    reference_fields = [
        "`user_job_match_settings.created_at`",
        "`user_job_match_settings.status`",
        "`user_job_match_auto_apply_posting_match.created_at`",
        "`user_job_match_auto_apply_posting_match.status`",
        "`user_job_match_auto_apply_posting_match.match_generation_version`",
        "`user_job_match_auto_apply_posting_match.cpa`",
        "`user_job_match_auto_apply_posting.xml_raw_job_uuid`",
        "`job_postings.xml_job_uuid`",
    ]
    reference_lineage = [("Active match source filter", describe_match_source_filter(match_source))]

    @st.cache_data(ttl=config.CACHE_TTL)
    def _kpis(start_date, end_date, match_source):
        return bq_client.get_overview_kpis(start_date, end_date, match_source=match_source)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _match_summary(start_date, end_date, match_source):
        return bq_client.get_match_performance_summary(start_date, end_date, match_source=match_source)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _weekly_match_cohorts(start_date, end_date, match_source):
        return bq_client.get_weekly_match_cohort_performance(
            start_date=start_date,
            end_date=end_date,
            match_source=match_source,
        )

    @st.cache_data(ttl=config.CACHE_TTL)
    def _signup_perf(start_date, end_date, match_source):
        return bq_client.get_signup_cohort_performance(
            start_date=start_date,
            end_date=end_date,
            match_source=match_source,
        )

    @st.cache_data(ttl=config.CACHE_TTL)
    def _signup_evolution(start_date, end_date, match_source):
        return bq_client.get_signup_cohort_evolution(
            start_date=start_date,
            end_date=end_date,
            match_source=match_source,
        )

    @st.cache_data(ttl=config.CACHE_TTL)
    def _top_users(start_date, end_date, match_source):
        return bq_client.get_top_match_users(start_date=start_date, end_date=end_date, match_source=match_source)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _xml_jobs(start_date, end_date):
        return bq_client.get_top_xml_jobs(start_date=start_date, end_date=end_date)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _failure_breakdown(start_date, end_date, match_source):
        return bq_client.get_match_failure_breakdown(start_date=start_date, end_date=end_date, match_source=match_source)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _status_dist(start_date, end_date):
        return bq_client.get_status_distribution("user_job_match_settings", "status", start_date, end_date)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _strategy_dist(start_date, end_date):
        return bq_client.get_status_distribution("user_job_match_settings", "strategy", start_date, end_date)

    try:
        kpis = _kpis(start_date, end_date, match_source).iloc[0]
    except Exception as e:
        st.error(f"Failed to load KPIs: {e}")
        return

    total = int(kpis["total_settings"])
    active = int(kpis["active_users"])
    paused_users = int(kpis["paused_users"])
    paused_rate = kpis["paused_rate"]
    total_matches = int(kpis["total_matches"])
    approved = int(kpis["approved_count"])
    rejected = int(kpis["rejected_count"])
    applied = int(kpis["applied_count"])
    past_pending = int(kpis["past_pending_count"])

    approval_rate = (past_pending / total_matches * 100) if total_matches > 0 else 0
    app_rate = (applied / past_pending * 100) if past_pending > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Match Users", f"{total:,}")
    c2.metric("Paused Rate", format_pct(paused_rate))
    c3.metric("Total Matches", f"{total_matches:,}")
    c4.metric("Exited Pending Share", f"{approval_rate:.1f}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Status = ACTIVE", f"{active:,}")
    c6.metric("Paused Users", f"{paused_users:,}")
    c7.metric("Application Rate", f"{app_rate:.1f}%")
    c8.metric("Approved Matches", f"{approved:,}")

    c9, c10 = st.columns(2)
    c9.metric("Rejected Matches", f"{rejected:,}")
    c10.metric("Completed Apps", f"{applied:,}")

    st.markdown("---")
    st.subheader("Match Performance Dynamics")
    st.caption(
        "Weekly cohort charts use match cohorts that are at least 28 days old so recent cohorts are not penalized "
        "for still being unresolved. Approval and rejection rates are based on decided matches; application rate is "
        "based on approved matches."
    )

    try:
        match_summary = _match_summary(start_date, end_date, match_source).iloc[0]
        weekly_df = _weekly_match_cohorts(start_date, end_date, match_source)
    except Exception as e:
        st.error(f"Failed to load match performance dynamics: {e}")
    else:
        render_summary_card(build_match_performance_summary(weekly_df, match_source=match_source))

        total_decided = int(match_summary["decided_matches"])
        total_approved = int(match_summary["approved_matches"])
        total_rejected = int(match_summary["rejected_matches"])
        total_applied = int(match_summary["applied_matches"])
        total_pending = int(match_summary["pending_matches"])
        total_failed = int(match_summary["failed_matches"])
        total_account_exists = int(match_summary["account_exists_matches"])
        total_expired = int(match_summary["expired_matches"])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Decided Matches", f"{total_decided:,} ({format_pct(match_summary['decision_rate'])})")
        c2.metric("Approved", f"{total_approved:,} ({format_pct(match_summary['approval_rate'])})")
        c3.metric("Rejected", f"{total_rejected:,} ({format_pct(match_summary['rejection_rate'])})")
        c4.metric("Applied", f"{total_applied:,} ({format_pct(match_summary['application_rate'])})")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Still Pending", f"{total_pending:,}")
        c6.metric("App Failed", f"{total_failed:,}")
        c7.metric("Account Exists", f"{total_account_exists:,}")
        c8.metric("Job Expired", f"{total_expired:,}")

        if not weekly_df.empty:
            weekly_df = weekly_df.copy()
            weekly_df["approved_waiting_matches"] = (
                weekly_df["approved_matches"]
                - weekly_df["applied_matches"]
                - weekly_df["failed_matches"]
                - weekly_df["account_exists_matches"]
            ).clip(lower=0)
            weekly_df["other_outcome_matches"] = (
                weekly_df["failed_matches"]
                + weekly_df["account_exists_matches"]
                + weekly_df["expired_matches"]
            )

            col_left, col_right = st.columns(2)

            with col_left:
                rate_df = weekly_df.melt(
                    id_vars=["cohort_week"],
                    value_vars=["decision_rate", "approval_rate", "rejection_rate", "application_rate"],
                    var_name="metric",
                    value_name="rate",
                )
                rate_df["metric"] = rate_df["metric"].map({
                    "decision_rate": "Decision rate",
                    "approval_rate": "Approval rate",
                    "rejection_rate": "Rejection rate",
                    "application_rate": "Application rate",
                })

                fig = px.line(
                    rate_df,
                    x="cohort_week",
                    y="rate",
                    color="metric",
                    markers=True,
                    color_discrete_map=RATE_COLOR_MAP,
                )
                apply_theme(fig, title="Weekly Match Cohort Rates", height=360, x_title="Cohort Week", y_title="Rate")
                fig.update_layout(legend_title_text="", hovermode="x unified")
                fig.update_yaxes(tickformat=".0%")
                st.plotly_chart(fig, use_container_width=True)

            with col_right:
                mix_df = weekly_df[[
                    "cohort_week",
                    "pending_matches",
                    "rejected_matches",
                    "approved_waiting_matches",
                    "applied_matches",
                    "other_outcome_matches",
                ]].melt(
                    id_vars=["cohort_week"],
                    var_name="status",
                    value_name="matches",
                )
                mix_df["status"] = mix_df["status"].map({
                    "pending_matches": "Pending review",
                    "rejected_matches": "Rejected",
                    "approved_waiting_matches": "Approved, awaiting app",
                    "applied_matches": "Applied",
                    "other_outcome_matches": "Other outcomes",
                })

                fig = px.bar(
                    mix_df,
                    x="cohort_week",
                    y="matches",
                    color="status",
                    barmode="stack",
                    color_discrete_map=MATCH_MIX_COLOR_MAP,
                )
                apply_theme(fig, title="Weekly Match Cohort Mix", height=360, x_title="Cohort Week", y_title="Matches")
                fig.update_layout(legend_title_text="", hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)

            with st.expander("Weekly cohort detail"):
                weekly_table = weekly_df.sort_values("cohort_week", ascending=False).copy()
                weekly_table["decision_rate_pct"] = weekly_table["decision_rate"] * 100
                weekly_table["approval_rate_pct"] = weekly_table["approval_rate"] * 100
                weekly_table["rejection_rate_pct"] = weekly_table["rejection_rate"] * 100
                weekly_table["application_rate_pct"] = weekly_table["application_rate"] * 100
                st.dataframe(
                    weekly_table[[
                        "cohort_week",
                        "total_matches",
                        "decided_matches",
                        "approved_matches",
                        "rejected_matches",
                        "applied_matches",
                        "pending_matches",
                        "decision_rate_pct",
                        "approval_rate_pct",
                        "rejection_rate_pct",
                        "application_rate_pct",
                    ]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "cohort_week": st.column_config.DateColumn("Cohort Week"),
                        "total_matches": st.column_config.NumberColumn("Total Matches", format="%d"),
                        "decided_matches": st.column_config.NumberColumn("Decided", format="%d"),
                        "approved_matches": st.column_config.NumberColumn("Approved", format="%d"),
                        "rejected_matches": st.column_config.NumberColumn("Rejected", format="%d"),
                        "applied_matches": st.column_config.NumberColumn("Applied", format="%d"),
                        "pending_matches": st.column_config.NumberColumn("Pending", format="%d"),
                        "decision_rate_pct": st.column_config.NumberColumn("Decision Rate", format="%.1f%%"),
                        "approval_rate_pct": st.column_config.NumberColumn("Approval Rate", format="%.1f%%"),
                        "rejection_rate_pct": st.column_config.NumberColumn("Rejection Rate", format="%.1f%%"),
                        "application_rate_pct": st.column_config.NumberColumn("Application Rate", format="%.1f%%"),
                    },
                )

    if match_source == "xml":
        st.markdown("---")
        st.subheader("XML Job Drilldown")
        st.caption(
            "These tables only use XML-backed matches resolved through "
            "`user_job_match_auto_apply_posting.xml_raw_job_uuid` or `job_postings.xml_job_uuid`."
        )
        reference_lineage.extend(
            [
                (
                    "Top XML jobs",
                    "<code>user_job_match_auto_apply_posting_match.auto_apply_posting_uuid</code> → "
                    "<code>user_job_match_auto_apply_posting.xml_raw_job_uuid</code> / <code>job_postings.xml_job_uuid</code> → "
                    "<code>xml_job_feed_raw_jobs.uuid</code>. Job metadata uses "
                    "<code>xml_job_feed_raw_jobs.role_name</code>, <code>.company_name</code>, <code>.city</code>, "
                    "<code>.state</code>, <code>.segment_name</code>, <code>.category</code>.",
                ),
                (
                    "Top matched users + failure breakdown",
                    "<code>user_job_match_settings.uuid</code> ↔ "
                    "<code>user_job_match_auto_apply_posting_match.user_job_match_settings_uuid</code>, plus "
                    "<code>user.id</code> ↔ <code>user_job_match_settings.user_id</code>. Outcome rates use "
                    "<code>user_job_match_auto_apply_posting_match.status</code> and revenue uses <code>.cpa</code>.",
                ),
            ]
        )

        try:
            xml_jobs_df = _xml_jobs(start_date, end_date)
            top_users_df = _top_users(start_date, end_date, match_source)
            failure_df = _failure_breakdown(start_date, end_date, match_source)
        except Exception as e:
            st.error(f"Failed to load XML drilldown: {e}")
        else:
            xml_left, xml_right = st.columns(2)

            with xml_left:
                st.markdown("#### Top XML Jobs")
                xml_jobs_display = xml_jobs_df.copy()
                for column in ["approval_rate", "application_rate", "failure_rate_after_approval"]:
                    if column in xml_jobs_display.columns:
                        xml_jobs_display[f"{column}_pct"] = xml_jobs_display[column] * 100
                st.dataframe(
                    xml_jobs_display[[
                        "xml_job_uuid",
                        "role_name",
                        "company_name",
                        "location",
                        "segment_name",
                        "category",
                        "total_matches",
                        "approved_matches",
                        "applied_matches",
                        "approval_rate_pct",
                        "application_rate_pct",
                        "failure_rate_after_approval_pct",
                        "realized_cpa",
                    ]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "xml_job_uuid": "XML Job UUID",
                        "role_name": "Role",
                        "company_name": "Company",
                        "location": "Location",
                        "segment_name": "Segment",
                        "category": "Category",
                        "total_matches": st.column_config.NumberColumn("Matches", format="%d"),
                        "approved_matches": st.column_config.NumberColumn("Approved", format="%d"),
                        "applied_matches": st.column_config.NumberColumn("Applied", format="%d"),
                        "approval_rate_pct": st.column_config.NumberColumn("Approval Rate", format="%.1f%%"),
                        "application_rate_pct": st.column_config.NumberColumn("Application Rate", format="%.1f%%"),
                        "failure_rate_after_approval_pct": st.column_config.NumberColumn("Failure Rate After Approval", format="%.1f%%"),
                        "realized_cpa": st.column_config.NumberColumn("Realized CPA", format="$%.0f"),
                    },
                )

            with xml_right:
                st.markdown("#### Top Users Matched to XML Jobs")
                top_users_display = top_users_df.copy()
                for column in ["approval_rate", "application_rate", "failure_rate_after_approval"]:
                    if column in top_users_display.columns:
                        top_users_display[f"{column}_pct"] = top_users_display[column] * 100
                st.dataframe(
                    top_users_display[[
                        "user_id",
                        "user_name",
                        "total_matches",
                        "approved_matches",
                        "applied_matches",
                        "approval_rate_pct",
                        "application_rate_pct",
                        "failure_rate_after_approval_pct",
                        "realized_cpa",
                    ]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "user_id": st.column_config.NumberColumn("User ID", format="%d"),
                        "user_name": "User",
                        "total_matches": st.column_config.NumberColumn("Matches", format="%d"),
                        "approved_matches": st.column_config.NumberColumn("Approved", format="%d"),
                        "applied_matches": st.column_config.NumberColumn("Applied", format="%d"),
                        "approval_rate_pct": st.column_config.NumberColumn("Approval Rate", format="%.1f%%"),
                        "application_rate_pct": st.column_config.NumberColumn("Application Rate", format="%.1f%%"),
                        "failure_rate_after_approval_pct": st.column_config.NumberColumn("Failure Rate After Approval", format="%.1f%%"),
                        "realized_cpa": st.column_config.NumberColumn("Realized CPA", format="$%.0f"),
                    },
                )

            st.markdown("#### XML Failure Breakdown")
            failure_display = failure_df.copy()
            if not failure_display.empty:
                failure_display["status"] = failure_display["status"].map(pretty_match_status)
                failure_display["share_of_failures_pct"] = failure_display["share_of_failures"] * 100
                failure_display["failure_rate_after_approval_pct"] = failure_display["failure_rate_after_approval"] * 100
                st.dataframe(
                    failure_display[[
                        "status",
                        "failure_count",
                        "share_of_failures_pct",
                        "failure_rate_after_approval_pct",
                    ]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "status": "Failure Outcome",
                        "failure_count": st.column_config.NumberColumn("Matches", format="%d"),
                        "share_of_failures_pct": st.column_config.NumberColumn("Share of XML Failures", format="%.1f%%"),
                        "failure_rate_after_approval_pct": st.column_config.NumberColumn("Rate After Approval", format="%.1f%%"),
                    },
                )

    st.markdown("---")
    st.subheader("Signup Cohort Evolution")
    st.caption(
        "Monthly cohorts are compared over the same first 12 weeks after signup. Evolution charts group users by "
        "signup quarter to show how early match volume and conversion behavior changes across cohorts."
    )

    try:
        signup_df = _signup_perf(start_date, end_date, match_source)
        signup_evolution_df = _signup_evolution(start_date, end_date, match_source)
    except Exception as e:
        st.error(f"Failed to load signup cohort analysis: {e}")
    else:
        render_summary_card(build_signup_cohort_summary(signup_df, match_source=match_source))

        signup_table = signup_df.sort_values("signup_month", ascending=False).copy()
        signup_table["matches_per_user"] = signup_table["matches_per_user"].fillna(0)
        signup_table["decision_rate_pct"] = signup_table["decision_rate"] * 100
        signup_table["approval_rate_pct"] = signup_table["approval_rate"] * 100
        signup_table["rejection_rate_pct"] = signup_table["rejection_rate"] * 100
        signup_table["application_rate_pct"] = signup_table["application_rate"] * 100

        st.dataframe(
            signup_table[[
                "signup_month",
                "cohort_users",
                "total_matches",
                "matches_per_user",
                "approved_matches",
                "rejected_matches",
                "applied_matches",
                "approval_rate_pct",
                "rejection_rate_pct",
                "application_rate_pct",
            ]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "signup_month": st.column_config.DateColumn("Signup Month"),
                "cohort_users": st.column_config.NumberColumn("Users", format="%d"),
                "total_matches": st.column_config.NumberColumn("Matches (First 12 Weeks)", format="%d"),
                "matches_per_user": st.column_config.NumberColumn("Matches / User", format="%.1f"),
                "approved_matches": st.column_config.NumberColumn("Approved", format="%d"),
                "rejected_matches": st.column_config.NumberColumn("Rejected", format="%d"),
                "applied_matches": st.column_config.NumberColumn("Applied", format="%d"),
                "approval_rate_pct": st.column_config.NumberColumn("Approval Rate", format="%.1f%%"),
                "rejection_rate_pct": st.column_config.NumberColumn("Rejection Rate", format="%.1f%%"),
                "application_rate_pct": st.column_config.NumberColumn("Application Rate", format="%.1f%%"),
            },
        )

        if not signup_evolution_df.empty:
            signup_evolution_df = signup_evolution_df.copy()
            signup_evolution_df["signup_cohort_label"] = (
                pd.to_datetime(signup_evolution_df["signup_cohort"])
                .dt.to_period("Q")
                .astype(str)
                .str.replace("Q", " Q", regex=False)
            )

            col_left, col_right = st.columns(2)

            with col_left:
                fig = px.line(
                    signup_evolution_df,
                    x="weeks_since_signup",
                    y="matches_per_user",
                    color="signup_cohort_label",
                    markers=True,
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                )
                apply_theme(fig, title="Matches per User by Weeks Since Signup", height=360, x_title="Weeks Since Signup", y_title="Matches per User")
                fig.update_layout(legend_title_text="Signup Quarter", hovermode="x unified")
                fig.update_xaxes(dtick=1)
                st.plotly_chart(fig, use_container_width=True)

            with col_right:
                fig = px.line(
                    signup_evolution_df,
                    x="weeks_since_signup",
                    y="approval_rate",
                    color="signup_cohort_label",
                    markers=True,
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                )
                apply_theme(fig, title="Approval Rate by Weeks Since Signup", height=360, x_title="Weeks Since Signup", y_title="Approval Rate")
                fig.update_layout(legend_title_text="Signup Quarter", hovermode="x unified")
                fig.update_xaxes(dtick=1)
                fig.update_yaxes(tickformat=".0%")
                st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("User Status Distribution")
        try:
            status_df = _status_dist(start_date, end_date)
            status_df["value"] = status_df["value"].map(pretty_label)
            fig = px.pie(status_df, values="count", names="value",
                         color_discrete_sequence=BRAND_SEQUENCE)
            apply_theme(fig, height=350)
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(str(e))

    with col_right:
        st.subheader("Strategy Distribution")
        try:
            strategy_df = _strategy_dist(start_date, end_date)
            strategy_df["value"] = strategy_df["value"].map(pretty_label)
            fig = px.bar(strategy_df, x="value", y="count", labels={"value": "Strategy", "count": "Users"})
            style_bar(fig)
            apply_theme(fig, height=350, x_title="Strategy", y_title="Users")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(str(e))

    render_page_reference(
        table_fields=reference_fields,
        timeframe_field="`created_at` on each source table",
        lineage_sections=reference_lineage,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB: Match Funnel
# ══════════════════════════════════════════════════════════════════════════════

def render_match_funnel():
    render_page_header("Match Funnel", "Where users and matches drop out between assignment, approval, and completed application.")
    match_source = TIME_FILTERS["match_source"]
    start_date = TIME_FILTERS["primary_start"]
    end_date = TIME_FILTERS["primary_end"]
    compare_start = TIME_FILTERS["compare_start"] if TIME_FILTERS["compare_enabled"] else None
    compare_end = TIME_FILTERS["compare_end"] if TIME_FILTERS["compare_enabled"] else None
    reference_fields = [
        "`user_job_match_auto_apply_posting_match.created_at`",
        "`user_job_match_auto_apply_posting_match.status`",
        "`user_job_match_auto_apply_posting_match.match_generation_version`",
        "`user_job_match_auto_apply_posting.xml_raw_job_uuid`",
        "`job_postings.xml_job_uuid`",
    ]
    reference_lineage = [("Active match source filter", describe_match_source_filter(match_source))]

    @st.cache_data(ttl=config.CACHE_TTL)
    def _funnel(start_date, end_date, match_source):
        return bq_client.get_match_funnel(start_date, end_date, match_source=match_source)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _funnel_ver(start_date, end_date, match_source):
        return bq_client.get_match_funnel_by_version(start_date, end_date, match_source=match_source)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _status_time(start_date, end_date, match_source):
        return bq_client.get_match_status_over_time(start_date=start_date, end_date=end_date, match_source=match_source)

    try:
        funnel_df = _funnel(start_date, end_date, match_source)
        comparison_df = _funnel(compare_start, compare_end, match_source) if TIME_FILTERS["compare_enabled"] else None
    except Exception as e:
        st.error(str(e))
        return

    render_summary_card(build_match_funnel_summary(funnel_df, comparison_df, match_source=match_source))
    status_counts = dict(zip(funnel_df["status"], funnel_df["count"]))
    happy_path = ["USER_PENDING", "USER_APPROVED", "CONTRACTOR_PENDING", "APPLIED"]

    total_past_pending = sum(status_counts.get(s, 0) for s in ["USER_APPROVED", "CONTRACTOR_PENDING", "APPLIED", "APP_FAILED", "ACCOUNT_EXISTS", "USER_REJECTED", "JOB_EXPIRED"])
    total_all = sum(status_counts.values())
    approve_total = sum(status_counts.get(s, 0) for s in ["USER_APPROVED", "CONTRACTOR_PENDING", "APPLIED", "APP_FAILED", "ACCOUNT_EXISTS"])
    applied_count = status_counts.get("APPLIED", 0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Decision Rate", format_pct(safe_ratio(total_past_pending, total_all)))
    c2.metric("Approval Rate", format_pct(safe_ratio(approve_total, total_past_pending)))
    c3.metric("Application Rate", format_pct(safe_ratio(applied_count, approve_total)))

    funnel_table = funnel_df.copy()
    funnel_table["stage"] = funnel_table["status"].map(pretty_match_status)
    funnel_table["share_of_matches"] = funnel_table["count"] / funnel_table["count"].sum() * 100
    st.dataframe(
        funnel_table[["stage", "count", "share_of_matches"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "stage": "Stage",
            "count": st.column_config.NumberColumn("Matches", format="%d"),
            "share_of_matches": st.column_config.NumberColumn("Share of Matches", format="%.1f%%"),
        },
    )

    st.markdown("---")
    col_left, col_right = st.columns([1.1, 0.9])

    with col_left:
        st.subheader("Happy Path Funnel")
        happy_vals = [status_counts.get(s, 0) for s in happy_path]
        fig = go.Figure(go.Funnel(
            y=[pretty_match_status(s) for s in happy_path],
            x=happy_vals,
            marker=dict(color=[COLORS["info_soft"], COLORS["warning_soft"], COLORS["warning"], COLORS["success"]]),
            textinfo="value+percent initial",
        ))
        apply_theme(fig, height=420, x_title="Matches", y_title="Stage")
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("Falloff Outcomes")
        falloff_df = funnel_df[funnel_df["status"].isin(["USER_REJECTED", "APP_FAILED", "JOB_EXPIRED", "ACCOUNT_EXISTS"])].copy()
        if not falloff_df.empty:
            falloff_df["status"] = falloff_df["status"].map(pretty_match_status)
            fig = px.bar(
                falloff_df.sort_values("count", ascending=True),
                x="count",
                y="status",
                orientation="h",
                labels={"count": "Matches", "status": "Outcome"},
            )
            style_bar(fig)
            apply_theme(fig, title="Non-Happy-Path Outcomes", height=420, x_title="Matches", y_title="Outcome")
            fig.update_layout(margin=dict(l=160))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Funnel by Match Generation Version")

    try:
        ver_df = _funnel_ver(start_date, end_date, match_source)
        ver_df["status"] = ver_df["status"].map(pretty_match_status)
        ver_df["version"] = ver_df["version"].map(pretty_label)
        version_pivot = ver_df.pivot_table(index="version", columns="status", values="count", fill_value=0)
        st.dataframe(version_pivot.reset_index(), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(str(e))

    st.markdown("---")
    st.subheader("Match Status Trends")

    try:
        time_df = _status_time(start_date, end_date, match_source)
        time_df["status"] = time_df["status"].map(pretty_match_status)
        fig = px.area(
            time_df,
            x="date",
            y="count",
            color="status",
            labels={"date": "Match Created Date", "count": "Matches", "status": "Status"},
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        apply_theme(fig, height=420, x_title="Match Created Date", y_title="Matches")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(str(e))

    render_page_reference(
        table_fields=reference_fields,
        timeframe_field="`user_job_match_auto_apply_posting_match.created_at`",
        lineage_sections=reference_lineage,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB: User Cohorts
# ══════════════════════════════════════════════════════════════════════════════

def render_user_cohorts():
    render_page_header("User Cohorts", "Who is joining, who is engaging, and which user cohorts need reactivation or better coverage.")
    start_date = TIME_FILTERS["primary_start"]
    end_date = TIME_FILTERS["primary_end"]
    compare_start = TIME_FILTERS["compare_start"] if TIME_FILTERS["compare_enabled"] else None
    compare_end = TIME_FILTERS["compare_end"] if TIME_FILTERS["compare_enabled"] else None
    reference_fields = [
        "`user_job_match_settings.created_at`",
        "`user_job_match_settings.last_job_match_activity_at`",
        "`user_job_match_settings.experience_level`",
        "`user_job_match_settings.education_level`",
        "`user_job_match_settings.status`",
    ]

    @st.cache_data(ttl=config.CACHE_TTL)
    def _exp(start_date, end_date):
        return bq_client.get_status_distribution("user_job_match_settings", "experience_level", start_date, end_date)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _edu(start_date, end_date):
        return bq_client.get_status_distribution("user_job_match_settings", "education_level", start_date, end_date)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _engagement(start_date, end_date):
        return bq_client.get_engagement_buckets(start_date, end_date)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _signups(start_date, end_date):
        return bq_client.get_signup_cohorts(start_date, end_date)

    try:
        exp_df = _exp(start_date, end_date)
        edu_df = _edu(start_date, end_date)
        eng_df = _engagement(start_date, end_date)
        signup_df = _signups(start_date, end_date)
        comparison_signup_df = _signups(compare_start, compare_end) if TIME_FILTERS["compare_enabled"] else None
    except Exception as e:
        st.error(str(e))
        return

    exp_df["value"] = exp_df["value"].map(pretty_label)
    edu_df["value"] = edu_df["value"].map(pretty_label)
    signup_df["status"] = signup_df["status"].map(pretty_label)

    render_summary_card(build_user_cohort_page_summary(eng_df, signup_df, comparison_signup_df))
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Experience Level Breakdown")
        st.dataframe(exp_df.rename(columns={"value": "Experience Level", "count": "Users"}), use_container_width=True, hide_index=True)
    with col_r:
        st.subheader("Education Level Breakdown")
        st.dataframe(edu_df.rename(columns={"value": "Education Level", "count": "Users"}), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Engagement Recency")
    fig = px.bar(eng_df, x="bucket", y="count", labels={"bucket": "Last Job Match Activity", "count": "Users"})
    style_bar(fig)
    apply_theme(fig, title="Users by Last Activity", height=360, x_title="Last Job Match Activity", y_title="Users")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Signup Cohorts by Month")
    total_by_month = signup_df.groupby("month")["count"].sum().reset_index()
    fig = px.line(total_by_month, x="month", y="count", markers=True, labels={"month": "Signup Month", "count": "Users"})
    fig.update_traces(line_color=COLORS["bar_line"], marker_color=COLORS["bar"])
    apply_theme(fig, title="New Users per Month", height=360, x_title="Signup Month", y_title="Users")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        signup_df.rename(columns={"month": "Signup Month", "status": "Status", "count": "Users"}),
        use_container_width=True,
        hide_index=True,
    )

    render_page_reference(
        table_fields=reference_fields,
        timeframe_field="`user_job_match_settings.created_at`",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB: Location Analysis
# ══════════════════════════════════════════════════════════════════════════════

def render_location():
    location_filters = get_page_time_filters("location_page", base_filters=TIME_FILTERS)
    render_page_header(
        "Location Analysis",
        "Target-location demand and funnel coverage to find underserved cohorts and revenue gaps.",
        time_filters=location_filters,
    )
    render_page_time_controls("location_page", location_filters)
    location_filters = get_page_time_filters("location_page", base_filters=TIME_FILTERS)

    match_source = location_filters["match_source"]
    start_date = location_filters["primary_start"]
    end_date = location_filters["primary_end"]
    compare_start = location_filters["compare_start"] if location_filters["compare_enabled"] else None
    compare_end = location_filters["compare_end"] if location_filters["compare_enabled"] else None
    reference_lineage = [
        (
            "Active match source filter",
            describe_match_source_filter(match_source),
        ),
        (
            "Remote preference cards",
            "<code>user_job_match_settings.open_to_remote</code> and <code>user_job_match_settings.open_to_any_city</code> "
            "from the latest active match-user snapshot per <code>user_id</code>. These cards do not use the date window.",
        ),
        (
            "Top Target Locations",
            "<code>user_job_match_settings.target_locations.city</code> + <code>.state</code>, joined at the user-settings level to "
            "<code>user_job_match_auto_apply_posting_match</code> through "
            "<code>user_job_match_settings.uuid = user_job_match_auto_apply_posting_match.user_job_match_settings_uuid</code>. "
            "The <code>Users</code> denominator comes from the latest active match-user snapshot per <code>user_id</code>, deduped at the "
            "user-location level. Match outcomes are then attached by <code>user_id</code> and filtered by "
            "<code>user_job_match_auto_apply_posting_match.created_at</code>; revenue uses <code>.cpa</code>.",
        ),
        (
            "Location x Role Funnel Coverage",
            "Same lineage as the location table plus <code>user_job_match_settings.target_roles_ref.alias</code>. "
            "This remains a user-preference cohort view: it does not yet force the matched posting itself to share the same location-role pair.",
        ),
        (
            "Active Match User Intake by Target Location",
            "<code>user.created_at</code> drives the weekly/monthly cohort bucket over a fixed rolling 3-month window. "
            "Users are first filtered to the current active match-user scope using the latest settings snapshot per "
            "<code>user_id</code> plus <code>user.default_resume_id IS NOT NULL</code> and "
            "<code>user_job_match_settings.status != 'PAUSED'</code>, then exploded across the latest "
            "<code>user_job_match_settings.target_locations.city</code> + <code>.state</code>. "
            "This is an intake trend view, not a match created_at view.",
        ),
    ]

    @st.cache_data(ttl=config.CACHE_TTL)
    def _remote(start_date, end_date):
        return bq_client.get_remote_preference_stats(start_date, end_date)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _location_perf(start_date, end_date, match_source):
        return bq_client.get_target_location_performance(
            limit=5000,
            start_date=start_date,
            end_date=end_date,
            match_source=match_source,
        )

    @st.cache_data(ttl=config.CACHE_TTL)
    def _location_role_perf(start_date, end_date, match_source):
        return bq_client.get_location_role_funnel(
            limit=5000,
            start_date=start_date,
            end_date=end_date,
            match_source=match_source,
        )

    @st.cache_data(ttl=config.CACHE_TTL)
    def _signup_location_trends(grain):
        return bq_client.get_active_match_user_signup_location_trends(
            grain=grain,
            months_back=3,
        )

    try:
        remote_df = _remote(start_date, end_date)
        location_df = _location_perf(start_date, end_date, match_source)
        combo_df = _location_role_perf(start_date, end_date, match_source)
        comparison_location_df = _location_perf(compare_start, compare_end, match_source) if location_filters["compare_enabled"] else None
        comparison_combo_df = _location_role_perf(compare_start, compare_end, match_source) if location_filters["compare_enabled"] else None
    except Exception as e:
        st.error(str(e))
        return

    render_summary_card(build_location_summary(location_df, combo_df, comparison_location_df, match_source=match_source))
    st.caption(
        "Interpretation note: a user can select multiple target locations and multiple target roles. "
        "Counts on this page are cohort counts within those selected preferences, not globally unique users across every row."
    )

    rollup = build_location_rollup(location_df)
    comparison_rollup = build_location_rollup(comparison_location_df) if comparison_location_df is not None else {}
    metric_cols = st.columns(5)
    metric_cols[0].metric(
        "User-Location Pairs",
        f"{rollup.get('user_location_pairs', 0):,}",
        None if not comparison_rollup else f"{rollup.get('user_location_pairs', 0) - comparison_rollup.get('user_location_pairs', 0):+,}",
    )
    metric_cols[1].metric(
        "Weighted Match Coverage",
        format_pct(rollup.get("match_rate")),
        None if not comparison_rollup else format_delta_points(rollup.get("match_rate"), comparison_rollup.get("match_rate")),
    )
    metric_cols[2].metric(
        "Approval After Match",
        format_pct(rollup.get("approval_rate")),
        None if not comparison_rollup else format_delta_points(rollup.get("approval_rate"), comparison_rollup.get("approval_rate")),
    )
    metric_cols[3].metric(
        "Application After Approval",
        format_pct(rollup.get("application_rate")),
        None if not comparison_rollup else format_delta_points(rollup.get("application_rate"), comparison_rollup.get("application_rate")),
    )
    metric_cols[4].metric(
        "Realized CPA",
        format_currency(rollup.get("realized_cpa")),
        None if not comparison_rollup else format_currency_delta(rollup.get("realized_cpa", 0) - comparison_rollup.get("realized_cpa", 0)),
    )

    c1, c2, c3, c4 = st.columns(4)
    for i, row in remote_df.iterrows():
        [c1, c2, c3, c4][i % 4].metric(pretty_label(row["preference"]), f"{int(row['count']):,}")

    st.markdown("---")
    st.subheader("Top 50 Target Locations (By Number of Active Match Users)")
    location_display = location_df.copy()
    location_display = location_display.sort_values(["users", "users_with_match"], ascending=[False, False]).reset_index(drop=True)
    location_display["rank"] = location_display.index + 1
    location_display["users_without_match"] = (location_display["users"] - location_display["users_with_match"]).clip(lower=0)
    location_display["match_user_rate_pct"] = location_display["match_user_rate"] * 100
    location_display["approved_user_rate_after_match_pct"] = location_display["approved_user_rate_after_match"] * 100
    location_display["application_user_rate_after_approval_pct"] = location_display["application_user_rate_after_approval"] * 100
    if comparison_location_df is not None and not comparison_location_df.empty:
        comparison_location_display = comparison_location_df.copy()
        comparison_location_display["comparison_match_user_rate_pct"] = comparison_location_display["match_user_rate"] * 100
        location_display = location_display.merge(
            comparison_location_display[["location", "comparison_match_user_rate_pct"]],
            on="location",
            how="left",
        )
        location_display["match_coverage_delta_pts"] = (
            location_display["match_user_rate_pct"] - location_display["comparison_match_user_rate_pct"]
        )

    location_table_columns = [
        "rank",
        "location",
        "users",
        "users_without_match",
        "users_with_match",
        "users_with_approved_match",
        "users_with_application",
        "match_user_rate_pct",
        "approved_user_rate_after_match_pct",
        "application_user_rate_after_approval_pct",
    ]
    if "match_coverage_delta_pts" in location_display.columns:
        location_table_columns.append("match_coverage_delta_pts")
    location_table_columns.extend(["realized_cpa", "avg_cpa_per_application"])

    location_table = location_display[location_table_columns].rename(
        columns={
            "rank": "Rank",
            "location": "Target Location",
            "users": "Users",
            "users_without_match": "Users Missing Match",
            "users_with_match": "Users with Match",
            "users_with_approved_match": "Users with Approved Match",
            "users_with_application": "Users with Application",
            "match_user_rate_pct": "Match Coverage %",
            "approved_user_rate_after_match_pct": "Approval After Match %",
            "application_user_rate_after_approval_pct": "Application After Approval %",
            "match_coverage_delta_pts": "Match Coverage Δ vs Compare (pts)",
            "realized_cpa": "Realized CPA",
            "avg_cpa_per_application": "Avg CPA / App",
        }
    )
    st.caption("Ranks are based on the latest active match-user snapshot per user. Match, approval, and application coverage measure how that current demand was served in the selected match created_at window.")
    st.dataframe(
        build_table_styler(
            location_table,
            {
                "Rank": "{:,.0f}",
                "Users": "{:,.0f}",
                "Users Missing Match": "{:,.0f}",
                "Users with Match": "{:,.0f}",
                "Users with Approved Match": "{:,.0f}",
                "Users with Application": "{:,.0f}",
                "Match Coverage %": "{:.1f}%",
                "Approval After Match %": "{:.1f}%",
                "Application After Approval %": "{:.1f}%",
                "Match Coverage Δ vs Compare (pts)": "{:+.1f}",
                "Realized CPA": "${:,.0f}",
                "Avg CPA / App": "${:,.0f}",
            },
            percent_columns=["Match Coverage %", "Approval After Match %", "Application After Approval %"],
            delta_columns=["Match Coverage Δ vs Compare (pts)"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("")
    low_coverage_locations = location_display[location_display["users"] > 200].copy()
    low_coverage_locations = low_coverage_locations.sort_values(
        ["match_user_rate_pct", "users"],
        ascending=[True, False],
    ).reset_index(drop=True)
    low_coverage_locations = low_coverage_locations.head(50).copy()
    low_coverage_locations["low_coverage_rank"] = low_coverage_locations.index + 1

    low_coverage_table_columns = [
        "low_coverage_rank",
        "location",
        "users",
        "users_without_match",
        "users_with_match",
        "users_with_approved_match",
        "users_with_application",
        "match_user_rate_pct",
        "approved_user_rate_after_match_pct",
        "application_user_rate_after_approval_pct",
    ]
    if "match_coverage_delta_pts" in low_coverage_locations.columns:
        low_coverage_table_columns.append("match_coverage_delta_pts")
    low_coverage_table_columns.extend(["realized_cpa", "avg_cpa_per_application"])

    low_coverage_table = low_coverage_locations[low_coverage_table_columns].rename(
        columns={
            "low_coverage_rank": "Coverage Rank",
            "location": "Target Location",
            "users": "Users",
            "users_without_match": "Users Missing Match",
            "users_with_match": "Users with Match",
            "users_with_approved_match": "Users with Approved Match",
            "users_with_application": "Users with Application",
            "match_user_rate_pct": "Match Coverage %",
            "approved_user_rate_after_match_pct": "Approval After Match %",
            "application_user_rate_after_approval_pct": "Application After Approval %",
            "match_coverage_delta_pts": "Match Coverage Δ vs Compare (pts)",
            "realized_cpa": "Realized CPA",
            "avg_cpa_per_application": "Avg CPA / App",
        }
    )

    st.subheader("Top 50 Target Locations (By Lowest % of Match Coverage, >200 Users)")
    st.caption(
        "This ranking filters to target locations with more than 200 active match users, then sorts by the lowest match coverage percentage so large underserved markets surface immediately."
    )
    st.dataframe(
        build_table_styler(
            low_coverage_table,
            {
                "Coverage Rank": "{:,.0f}",
                "Users": "{:,.0f}",
                "Users Missing Match": "{:,.0f}",
                "Users with Match": "{:,.0f}",
                "Users with Approved Match": "{:,.0f}",
                "Users with Application": "{:,.0f}",
                "Match Coverage %": "{:.1f}%",
                "Approval After Match %": "{:.1f}%",
                "Application After Approval %": "{:.1f}%",
                "Match Coverage Δ vs Compare (pts)": "{:+.1f}",
                "Realized CPA": "${:,.0f}",
                "Avg CPA / App": "${:,.0f}",
            },
            percent_columns=["Match Coverage %", "Approval After Match %", "Application After Approval %"],
            delta_columns=["Match Coverage Δ vs Compare (pts)"],
            row_highlight_column="Match Coverage %",
            row_highlight_threshold=90,
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    signup_header_col, signup_control_col = st.columns([4.2, 1.6])
    with signup_header_col:
        st.subheader("Top 50 DMAs by Active Match User Intake (Last 3 Months)")
    with signup_control_col:
        signup_grain_label = st.radio(
            "Intake View",
            ["Monthly", "Weekly"],
            horizontal=True,
            key="location_signup_location_grain",
        )

    signup_grain = "week" if signup_grain_label == "Weekly" else "month"
    signup_window_end = date.today()
    signup_window_start = (pd.Timestamp(signup_window_end) - pd.DateOffset(months=3)).date()
    try:
        signup_trend_df = _signup_location_trends(signup_grain)
    except Exception as e:
        st.error(str(e))
        signup_trend_df = pd.DataFrame()

    if signup_trend_df.empty:
        st.info("No active match-user signup location data is available for the last 3 months.")
    else:
        signup_trend_df = signup_trend_df.copy()
        signup_trend_df["cohort_period"] = pd.to_datetime(signup_trend_df["cohort_period"])
        signup_trend_df = signup_trend_df.sort_values(["cohort_period", "active_match_users"], ascending=[True, False]).reset_index(drop=True)

        dma_totals = (
            signup_trend_df.groupby("location", as_index=False)["active_match_users"]
            .sum()
            .sort_values(["active_match_users", "location"], ascending=[False, True])
            .reset_index(drop=True)
        )

        st.markdown(
            f"This section is based only on `user.created_at` between `{signup_window_start}` and "
            f"`{signup_window_end}`. It shows which current active match users entered Bandana over that window and "
            "which current target-location DMAs they currently want, independent of match `created_at` filters."
        )
        top_dmas = (
            location_display[["location", "users"]]
            .sort_values(["users", "location"], ascending=[False, True])
            .head(50)
            .rename(columns={"location": "Target DMA", "users": "Current Active Users"})
            .reset_index(drop=True)
        )
        top_dmas["Rank"] = top_dmas.index + 1
        period_order = sorted(signup_trend_df["cohort_period"].dropna().unique())
        period_columns = [format_period_column_label(period, signup_grain) for period in period_order]
        growth_label = "% WoW CAGR" if signup_grain == "week" else "% MoM CAGR"
        latest_period = pd.Timestamp(period_order[-1]) if period_order else None
        is_partial_period, proration_factor, elapsed_days, total_days = get_partial_period_proration(
            latest_period,
            grain=signup_grain,
            today_value=signup_window_end,
        )
        latest_period_label = format_period_column_label(latest_period, signup_grain) if latest_period is not None else None
        prorated_period_label = f"{latest_period_label} (Prorated)" if latest_period_label and is_partial_period else latest_period_label

        pivot_table = (
            signup_trend_df[signup_trend_df["location"].isin(top_dmas["Target DMA"])]
            .assign(period_label=lambda df: df["cohort_period"].map(lambda value: format_period_column_label(value, signup_grain)))
            .pivot_table(
                index="location",
                columns="period_label",
                values="active_match_users",
                aggfunc="sum",
                fill_value=0,
            )
            .reset_index()
        )
        intake_table = top_dmas.merge(
            pivot_table.rename(columns={"location": "Target DMA"}),
            on="Target DMA",
            how="left",
        )
        period_columns_in_table = [column for column in period_columns if column in intake_table.columns]
        intake_table[period_columns_in_table] = intake_table[period_columns_in_table].fillna(0)
        growth_period_columns = list(period_columns_in_table)
        if is_partial_period and latest_period_label in intake_table.columns:
            intake_table[latest_period_label] = intake_table[latest_period_label] * proration_factor
            intake_table = intake_table.rename(columns={latest_period_label: prorated_period_label})
            period_columns_in_table = [prorated_period_label if column == latest_period_label else column for column in period_columns_in_table]
            growth_period_columns = [column for column in growth_period_columns if column != latest_period_label]
        three_month_signups = dma_totals.rename(columns={"location": "Target DMA", "active_match_users": "3-Month Active Match User Signups"})
        intake_table = intake_table.merge(
            three_month_signups,
            on="Target DMA",
            how="left",
        ).fillna({"3-Month Active Match User Signups": 0})
        if growth_period_columns:
            intake_table[growth_label] = intake_table.apply(
                lambda row: calculate_period_cagr([row[column] for column in growth_period_columns]),
                axis=1,
            )
        else:
            intake_table[growth_label] = None
        ordered_columns = ["Rank", "Target DMA"] + period_columns_in_table + ["3-Month Active Match User Signups", "Current Active Users", growth_label]
        intake_table = intake_table[ordered_columns]
        intake_table_height = min(1800, 42 + (len(intake_table) + 1) * 35)
        st.dataframe(
            build_table_styler(
                intake_table,
                {
                    "Rank": "{:,.0f}",
                    **{column: "{:,.0f}" for column in period_columns_in_table},
                    "3-Month Active Match User Signups": "{:,.0f}",
                    "Current Active Users": "{:,.0f}",
                    growth_label: "{:.1%}",
                },
                emphasis_columns=["3-Month Active Match User Signups", "Current Active Users", growth_label],
                custom_style_columns={growth_label: growth_background_style},
            ),
            use_container_width=True,
            hide_index=True,
            height=intake_table_height,
        )
        if is_partial_period and latest_period_label:
            st.caption(
                f"`{prorated_period_label}` is prorated from {elapsed_days} observed day"
                f"{'' if elapsed_days == 1 else 's'} out of {total_days}. "
                f"It is excluded from `{growth_label}` so the growth calculation only uses completed periods."
            )

    top_location_chart = location_display.head(12).copy()
    top_location_chart["chart_label"] = top_location_chart.apply(
        lambda row: wrap_chart_label(row["location"], rank=int(row["rank"]), width=18),
        axis=1,
    )
    top_location_chart["coverage_label"] = top_location_chart["match_user_rate_pct"].map(lambda value: f"{value:.1f}%")
    top_location_chart["coverage_band"] = pd.cut(
        top_location_chart["match_user_rate_pct"],
        bins=[-0.01, 25, 90, 100],
        labels=["Low Coverage", "Opportunity Band", "Healthy Coverage"],
    )
    fig = px.bar(
        top_location_chart,
        x="chart_label",
        y="match_user_rate_pct",
        color="coverage_band",
        text="coverage_label",
        labels={"chart_label": "Target Location Rank", "match_user_rate_pct": "Match Coverage %", "coverage_band": "Coverage Tier"},
        color_discrete_map=COVERAGE_TIER_COLORS,
    )
    apply_theme(fig, title="Top Target Locations by Match Coverage", height=520, x_title="Target Location Rank", y_title="Match Coverage %")
    fig.update_layout(legend_title_text="")
    fig.update_traces(textposition="outside", textfont=dict(size=13, color=COLORS["text"]), cliponaxis=False)
    fig.update_xaxes(tickangle=-28)
    fig.update_yaxes(range=[0, max(100, top_location_chart["match_user_rate_pct"].max() + 10)], ticksuffix="%")
    fig.add_hline(
        y=90,
        line_dash="dash",
        line_color=COLORS["text"],
        annotation_text="90% coverage target",
        annotation_position="top left",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    combo_display = combo_df.copy()
    combo_display = combo_display.sort_values(["users", "users_with_match"], ascending=[False, False]).reset_index(drop=True)
    combo_display["match_user_rate_pct"] = combo_display["match_user_rate"] * 100
    combo_display["approved_user_rate_after_match_pct"] = combo_display["approved_user_rate_after_match"] * 100
    combo_display["application_user_rate_after_approval_pct"] = combo_display["application_user_rate_after_approval"] * 100
    combo_display["coverage_gap_score"] = combo_display["users"] * (1 - combo_display["match_user_rate"].fillna(0))
    combo_display["rank"] = combo_display.index + 1
    combo_display["users_without_match"] = (combo_display["users"] - combo_display["users_with_match"]).clip(lower=0)
    combo_display["approval_gap_users"] = (combo_display["users_with_match"] - combo_display["users_with_approved_match"]).clip(lower=0)
    combo_display["application_gap_users"] = (combo_display["users_with_approved_match"] - combo_display["users_with_application"]).clip(lower=0)
    combo_display[["largest_gap_stage", "largest_gap_users"]] = combo_display.apply(
        lambda row: pd.Series(get_largest_gap_stage(row)),
        axis=1,
    )
    if comparison_combo_df is not None and not comparison_combo_df.empty:
        comparison_combo_display = comparison_combo_df.copy()
        comparison_combo_display["comparison_match_user_rate_pct"] = comparison_combo_display["match_user_rate"] * 100
        combo_display = combo_display.merge(
            comparison_combo_display[["location", "role", "comparison_match_user_rate_pct"]],
            on=["location", "role"],
            how="left",
        )
        combo_display["match_coverage_delta_pts"] = (
            combo_display["match_user_rate_pct"] - combo_display["comparison_match_user_rate_pct"]
        )

    combo_gap_df = combo_display[combo_display["match_user_rate_pct"] < 90].copy()
    gap_count = len(combo_gap_df)
    shown_count = min(50, gap_count)
    st.subheader(f"Location x Role Combos Below 90% Match Coverage ({shown_count} shown)")
    underserved_df = combo_gap_df.sort_values(["coverage_gap_score", "users"], ascending=[False, False]).head(50).reset_index(drop=True)
    if underserved_df.empty:
        st.info("No location x role cohorts are below the 90% match coverage target in the selected window.")
        render_page_reference(lineage_sections=reference_lineage)
        return
    underserved_df["gap_rank"] = underserved_df.index + 1
    combo_table_columns = [
        "gap_rank",
        "location",
        "role",
        "users",
        "users_without_match",
        "approval_gap_users",
        "application_gap_users",
        "match_user_rate_pct",
        "approved_user_rate_after_match_pct",
        "application_user_rate_after_approval_pct",
        "largest_gap_stage",
        "largest_gap_users",
    ]
    if "match_coverage_delta_pts" in underserved_df.columns:
        combo_table_columns.append("match_coverage_delta_pts")
    combo_table_columns.extend(["realized_cpa", "avg_cpa_per_application"])

    combo_table = underserved_df[combo_table_columns].rename(
        columns={
            "gap_rank": "Gap Rank",
            "location": "Target Location",
            "role": "Target Role",
            "users": "Users",
            "users_without_match": "No Match Users",
            "approval_gap_users": "Not Approved After Match",
            "application_gap_users": "Approved But Not Applied",
            "match_user_rate_pct": "Match Coverage %",
            "approved_user_rate_after_match_pct": "Approval After Match %",
            "application_user_rate_after_approval_pct": "Application After Approval %",
            "largest_gap_stage": "Largest Gap Stage",
            "largest_gap_users": "Users Lost at Largest Gap",
            "match_coverage_delta_pts": "Match Coverage Δ vs Compare (pts)",
            "realized_cpa": "Realized CPA",
            "avg_cpa_per_application": "Avg CPA / App",
        }
    )
    combo_table_height = min(1800, 42 + (len(combo_table) + 1) * 35)
    st.caption(
        f"Showing {shown_count} current location x role cohorts below the 90% match coverage target, ranked by uncovered demand. "
        f"{'There are fewer than 50 qualifying cohorts under the current filters.' if gap_count < 50 else 'This is the top 50 only.'} "
        "Entire rows stay highlighted so the biggest XML supply gaps stand out immediately."
    )
    st.dataframe(
        build_table_styler(
            combo_table,
            {
                "Gap Rank": "{:,.0f}",
                "Users": "{:,.0f}",
                "No Match Users": "{:,.0f}",
                "Not Approved After Match": "{:,.0f}",
                "Approved But Not Applied": "{:,.0f}",
                "Match Coverage %": "{:.1f}%",
                "Approval After Match %": "{:.1f}%",
                "Application After Approval %": "{:.1f}%",
                "Users Lost at Largest Gap": "{:,.0f}",
                "Match Coverage Δ vs Compare (pts)": "{:+.1f}",
                "Realized CPA": "${:,.0f}",
                "Avg CPA / App": "${:,.0f}",
            },
            row_highlight_column="Match Coverage %",
            row_highlight_threshold=90,
        ),
        use_container_width=True,
        hide_index=True,
        height=combo_table_height,
    )

    combo_chart = underserved_df.head(10).copy()
    combo_chart["chart_label"] = combo_chart.apply(
        lambda row: wrap_chart_label(f"{row['location']} / {row['role']}", rank=int(row["gap_rank"]), width=16),
        axis=1,
    )
    funnel_chart = combo_chart.melt(
        id_vars=["chart_label"],
        value_vars=[
            "match_user_rate_pct",
            "approved_user_rate_after_match_pct",
            "application_user_rate_after_approval_pct",
        ],
        var_name="stage",
        value_name="conversion_pct",
    )
    stage_labels = {
        "match_user_rate_pct": "Match Coverage",
        "approved_user_rate_after_match_pct": "Approval After Match",
        "application_user_rate_after_approval_pct": "Application After Approval",
    }
    funnel_chart["stage"] = funnel_chart["stage"].map(stage_labels)
    funnel_chart["conversion_label"] = funnel_chart["conversion_pct"].map(lambda value: f"{value:.1f}%")
    fig = px.bar(
        funnel_chart,
        x="chart_label",
        y="conversion_pct",
        color="stage",
        barmode="group",
        text="conversion_label",
        color_discrete_map=FUNNEL_STAGE_COLOR_MAP,
        labels={"chart_label": "Location / Role Cohort", "conversion_pct": "Conversion %", "stage": "Funnel Stage"},
    )
    apply_theme(fig, title="Top Below-Target Location x Role Funnel Stage Conversion", height=560, x_title="Location / Role Cohort", y_title="Conversion %")
    fig.update_traces(textposition="outside", textfont=dict(size=12, color=COLORS["text"]), cliponaxis=False)
    fig.update_layout(legend_title_text="")
    fig.update_xaxes(tickangle=-26)
    fig.update_yaxes(range=[0, max(100, funnel_chart["conversion_pct"].max() + 12)], ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True)

    render_page_reference(lineage_sections=reference_lineage)


# ══════════════════════════════════════════════════════════════════════════════
# TAB: Role & Industry
# ══════════════════════════════════════════════════════════════════════════════

def render_role_industry():
    role_filters = get_page_time_filters("role_page", base_filters=TIME_FILTERS)
    render_page_header(
        "Role & Industry",
        "Target-role demand and role x geography funnel coverage to surface underserved cohorts and revenue gaps.",
        time_filters=role_filters,
    )
    render_page_time_controls("role_page", role_filters)
    role_filters = get_page_time_filters("role_page", base_filters=TIME_FILTERS)

    match_source = role_filters["match_source"]
    start_date = role_filters["primary_start"]
    end_date = role_filters["primary_end"]
    compare_start = role_filters["compare_start"] if role_filters["compare_enabled"] else None
    compare_end = role_filters["compare_end"] if role_filters["compare_enabled"] else None
    reference_lineage = [
        (
            "Active match source filter",
            describe_match_source_filter(match_source),
        ),
        (
            "Top Target Roles",
            "<code>user_job_match_settings.target_roles_ref.alias</code>, joined at the user-settings level to "
            "<code>user_job_match_auto_apply_posting_match</code> through "
            "<code>user_job_match_settings.uuid = user_job_match_auto_apply_posting_match.user_job_match_settings_uuid</code>. "
            "The <code>Users</code> denominator comes from the latest active match-user snapshot per <code>user_id</code>, deduped at the "
            "user-role level. Match outcomes are then attached by <code>user_id</code> and filtered by "
            "<code>user_job_match_auto_apply_posting_match.created_at</code>; revenue uses <code>.cpa</code>.",
        ),
        (
            "No Target Alias Selected",
            "Counts current active match users in the latest settings snapshot whose <code>target_roles_ref</code> array contains "
            "no non-null <code>alias</code> values. This is a current snapshot metric and does not use the match created_at window.",
        ),
        (
            "Role x Geography Funnel Coverage",
            "Same lineage as the role table plus <code>user_job_match_settings.target_locations.city</code> + <code>.state</code>. "
            "This remains a user-preference cohort view: it does not yet force the matched posting itself to share the same role-location pair.",
        ),
        (
            "Industry + Certification Context",
            "<code>user_job_match_settings.target_industries.name</code> and <code>user_job_match_settings.target_certifications.name</code> "
            "from the latest active match-user snapshot per <code>user_id</code>.",
        ),
    ]

    @st.cache_data(ttl=config.CACHE_TTL)
    def _industries(start_date, end_date):
        return bq_client.get_industry_distribution(start_date, end_date)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _roles(start_date, end_date, match_source):
        return bq_client.get_target_role_performance(
            start_date=start_date,
            end_date=end_date,
            match_source=match_source,
        )

    @st.cache_data(ttl=config.CACHE_TTL)
    def _role_geo(start_date, end_date, match_source):
        return bq_client.get_role_location_funnel(
            limit=5000,
            start_date=start_date,
            end_date=end_date,
            match_source=match_source,
        )

    @st.cache_data(ttl=config.CACHE_TTL)
    def _certs(start_date, end_date):
        return bq_client.get_certification_distribution(start_date=start_date, end_date=end_date)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _role_alias_summary():
        return bq_client.get_role_alias_selection_summary()

    try:
        ind_df = _industries(start_date, end_date)
        role_df = _roles(start_date, end_date, match_source)
        combo_df = _role_geo(start_date, end_date, match_source)
        cert_df = _certs(start_date, end_date)
        role_alias_summary = _role_alias_summary().iloc[0]
        comparison_role_df = _roles(compare_start, compare_end, match_source) if role_filters["compare_enabled"] else None
        comparison_combo_df = _role_geo(compare_start, compare_end, match_source) if role_filters["compare_enabled"] else None
    except Exception as e:
        st.error(str(e))
        return

    render_summary_card(build_role_summary(role_df, combo_df, ind_df, comparison_role_df, match_source=match_source))
    st.caption(
        "Interpretation note: a user can select multiple target roles and multiple target locations. "
        "Counts on this page are cohort counts within those selected preferences, not globally unique users across every row."
    )

    rollup = build_location_rollup(role_df)
    comparison_rollup = build_location_rollup(comparison_role_df) if comparison_role_df is not None else {}
    metric_cols = st.columns(6)
    metric_cols[0].metric(
        "User-Role Pairs",
        f"{rollup.get('user_location_pairs', 0):,}",
        None if not comparison_rollup else f"{rollup.get('user_location_pairs', 0) - comparison_rollup.get('user_location_pairs', 0):+,}",
    )
    metric_cols[1].metric(
        "No Target Alias Selected",
        f"{int(role_alias_summary.get('users_without_target_role_alias', 0)):,} / {int(role_alias_summary.get('active_match_users', 0)):,} ({format_pct(role_alias_summary.get('users_without_target_role_alias_rate'))})",
    )
    metric_cols[2].metric(
        "Weighted Match Coverage",
        format_pct(rollup.get("match_rate")),
        None if not comparison_rollup else format_delta_points(rollup.get("match_rate"), comparison_rollup.get("match_rate")),
    )
    metric_cols[3].metric(
        "Approval After Match",
        format_pct(rollup.get("approval_rate")),
        None if not comparison_rollup else format_delta_points(rollup.get("approval_rate"), comparison_rollup.get("approval_rate")),
    )
    metric_cols[4].metric(
        "Application After Approval",
        format_pct(rollup.get("application_rate")),
        None if not comparison_rollup else format_delta_points(rollup.get("application_rate"), comparison_rollup.get("application_rate")),
    )
    metric_cols[5].metric(
        "Realized CPA",
        format_currency(rollup.get("realized_cpa")),
        None if not comparison_rollup else format_currency_delta(rollup.get("realized_cpa", 0) - comparison_rollup.get("realized_cpa", 0)),
    )

    st.markdown("---")
    st.subheader("Industry + Certification Context")
    context_left, context_right = st.columns(2)
    with context_left:
        st.dataframe(
            ind_df.head(25).rename(columns={"industry": "Industry", "count": "Users"}),
            use_container_width=True,
            hide_index=True,
        )
    with context_right:
        st.dataframe(
            cert_df.head(25).rename(columns={"certification": "Certification", "count": "Users"}),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")
    st.subheader("Users by Industry")

    # Load coverage data (all active users with/without industry + created_at)
    @st.cache_data(ttl=config.CACHE_TTL)
    def _industry_coverage_dates(start_date, end_date):
        return bq_client.get_industry_coverage_with_dates(start_date, end_date)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _industry_users(start_date, end_date):
        return bq_client.get_industry_user_mapping(start_date, end_date)

    try:
        cov_df = _industry_coverage_dates(start_date, end_date)
        iu_df = _industry_users(start_date, end_date)
    except Exception as e:
        st.error(f"Industry data error: {e}")
        return

    if iu_df.empty and cov_df.empty:
        st.info("No industry data found.")
        return

    # Determine date range from coverage data (includes users without industry)
    cov_df["settings_created_at"] = pd.to_datetime(cov_df["settings_created_at"], utc=True, errors="coerce")
    cov_df = cov_df.dropna(subset=["settings_created_at"])
    min_date = cov_df["settings_created_at"].min().date()
    max_date = cov_df["settings_created_at"].max().date()

    # Date filter row
    date_col1, date_col2, ind_col = st.columns([1, 1, 2])
    with date_col1:
        from_date = st.date_input("Settings created from", value=min_date, min_value=min_date, max_value=max_date, key="ind_from")
    with date_col2:
        to_date = st.date_input("Settings created to", value=max_date, min_value=min_date, max_value=max_date, key="ind_to")

    # Filter coverage stats by date
    cov_filtered = cov_df[
        (cov_df["settings_created_at"].dt.date >= from_date) &
        (cov_df["settings_created_at"].dt.date <= to_date)
    ]
    total_active = len(cov_filtered)
    has_industry = int(cov_filtered["has_industry"].sum())
    no_industry = total_active - has_industry
    no_pct = (no_industry / total_active * 100) if total_active > 0 else 0

    cov_c1, cov_c2, cov_c3 = st.columns(3)
    cov_c1.metric("Total Active Users", f"{total_active:,}")
    cov_c2.metric("With Industry Selected", f"{has_industry:,}")
    cov_c3.metric("No Industry Selected", f"{no_industry:,} ({no_pct:.1f}%)")

    if "has_minimum_pay" in cov_filtered.columns:
        has_pay = int(cov_filtered["has_minimum_pay"].sum())
        no_pay = total_active - has_pay
        no_pay_pct = (no_pay / total_active * 100) if total_active > 0 else 0

        pay_c1, pay_c2, pay_c3 = st.columns(3)
        pay_c1.metric("Total Active Users", f"{total_active:,}")
        pay_c2.metric("With Minimum Pay Set", f"{has_pay:,}")
        pay_c3.metric("No Minimum Pay Set", f"{no_pay:,} ({no_pay_pct:.1f}%)")
    else:
        st.caption("Hit **Refresh Data** in the sidebar to load minimum pay stats.")

    st.caption("Each row is one user-industry pair. Users selecting multiple industries appear once per industry.")

    try:
        if not iu_df.empty:
            if "settings_created_at" not in iu_df.columns:
                st.warning("Hit **Refresh Data** in the sidebar to load updated columns.")
                return
            iu_df["settings_created_at"] = pd.to_datetime(iu_df["settings_created_at"], utc=True, errors="coerce")
            iu_df = iu_df.dropna(subset=["settings_created_at"])
            iu_df = iu_df[
                (iu_df["settings_created_at"].dt.date >= from_date) &
                (iu_df["settings_created_at"].dt.date <= to_date)
            ]
            with ind_col:
                industry_filter = st.selectbox(
                    "Filter by industry",
                    options=["All Industries"] + sorted(iu_df["industry"].unique().tolist()),
                    key="industry_user_filter",
                )
            filtered = iu_df if industry_filter == "All Industries" else iu_df[iu_df["industry"] == industry_filter]
            st.metric("Users in Selection", f"{filtered['user_id'].nunique():,}")
            st.dataframe(
                filtered[["user_name", "first_name", "last_name", "industry", "status", "strategy", "experience_level", "target_roles", "target_locations"]].rename(
                    columns={
                        "user_name": "Name",
                        "first_name": "First Name",
                        "last_name": "Last Name",
                        "industry": "Industry",
                        "status": "Status",
                        "strategy": "Strategy",
                        "experience_level": "Experience",
                        "target_roles": "Target Roles",
                        "target_locations": "Target Locations",
                    }
                ),
                use_container_width=True,
                hide_index=True,
                height=500,
            )
        else:
            st.info("No industry assignment data found.")
    except Exception as e:
        st.error(f"Industry user mapping error: {e}")

    st.markdown("---")
    st.subheader("Top Target Roles")
    role_display = role_df.copy()
    role_display = role_display.sort_values(["users", "users_with_match"], ascending=[False, False]).reset_index(drop=True)
    role_display["rank"] = role_display.index + 1
    role_display["users_without_match"] = (role_display["users"] - role_display["users_with_match"]).clip(lower=0)
    role_display["match_user_rate_pct"] = role_display["match_user_rate"] * 100
    role_display["approved_user_rate_after_match_pct"] = role_display["approved_user_rate_after_match"] * 100
    role_display["application_user_rate_after_approval_pct"] = role_display["application_user_rate_after_approval"] * 100
    if comparison_role_df is not None and not comparison_role_df.empty:
        comparison_role_display = comparison_role_df.copy()
        comparison_role_display["comparison_match_user_rate_pct"] = comparison_role_display["match_user_rate"] * 100
        role_display = role_display.merge(
            comparison_role_display[["role", "comparison_match_user_rate_pct"]],
            on="role",
            how="left",
        )
        role_display["match_coverage_delta_pts"] = (
            role_display["match_user_rate_pct"] - role_display["comparison_match_user_rate_pct"]
        )

    role_table_columns = [
        "rank",
        "role",
        "users",
        "users_without_match",
        "users_with_match",
        "users_with_approved_match",
        "users_with_application",
        "match_user_rate_pct",
        "approved_user_rate_after_match_pct",
        "application_user_rate_after_approval_pct",
    ]
    if "match_coverage_delta_pts" in role_display.columns:
        role_table_columns.append("match_coverage_delta_pts")
    role_table_columns.extend(["realized_cpa", "avg_cpa_per_application"])

    role_table = role_display[role_table_columns].rename(
        columns={
            "rank": "Rank",
            "role": "Target Role",
            "users": "Users",
            "users_without_match": "Users Missing Match",
            "users_with_match": "Users with Match",
            "users_with_approved_match": "Users with Approved Match",
            "users_with_application": "Users with Application",
            "match_user_rate_pct": "Match Coverage %",
            "approved_user_rate_after_match_pct": "Approval After Match %",
            "application_user_rate_after_approval_pct": "Application After Approval %",
            "match_coverage_delta_pts": "Match Coverage Δ vs Compare (pts)",
            "realized_cpa": "Realized CPA",
            "avg_cpa_per_application": "Avg CPA / App",
        }
    )
    st.caption("Ranks are based on the latest active match-user snapshot per user. Match, approval, and application coverage measure how that current demand was served in the selected match created_at window.")
    st.dataframe(
        build_table_styler(
            role_table,
            {
                "Rank": "{:,.0f}",
                "Users": "{:,.0f}",
                "Users Missing Match": "{:,.0f}",
                "Users with Match": "{:,.0f}",
                "Users with Approved Match": "{:,.0f}",
                "Users with Application": "{:,.0f}",
                "Match Coverage %": "{:.1f}%",
                "Approval After Match %": "{:.1f}%",
                "Application After Approval %": "{:.1f}%",
                "Match Coverage Δ vs Compare (pts)": "{:+.1f}",
                "Realized CPA": "${:,.0f}",
                "Avg CPA / App": "${:,.0f}",
            },
            percent_columns=["Match Coverage %", "Approval After Match %", "Application After Approval %"],
            delta_columns=["Match Coverage Δ vs Compare (pts)"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    top_role_chart = role_display.head(12).copy()
    top_role_chart["chart_label"] = top_role_chart.apply(
        lambda row: wrap_chart_label(row["role"], rank=int(row["rank"]), width=18),
        axis=1,
    )
    top_role_chart["coverage_label"] = top_role_chart["match_user_rate_pct"].map(lambda value: f"{value:.1f}%")
    top_role_chart["coverage_band"] = pd.cut(
        top_role_chart["match_user_rate_pct"],
        bins=[-0.01, 25, 90, 100],
        labels=["Low Coverage", "Opportunity Band", "Healthy Coverage"],
    )
    fig = px.bar(
        top_role_chart,
        x="chart_label",
        y="match_user_rate_pct",
        color="coverage_band",
        text="coverage_label",
        labels={"chart_label": "Target Role Rank", "match_user_rate_pct": "Match Coverage %", "coverage_band": "Coverage Tier"},
        color_discrete_map=COVERAGE_TIER_COLORS,
    )
    apply_theme(fig, title="Top Target Roles by Match Coverage", height=520, x_title="Target Role Rank", y_title="Match Coverage %")
    fig.update_layout(legend_title_text="")
    fig.update_traces(textposition="outside", textfont=dict(size=13, color=COLORS["text"]), cliponaxis=False)
    fig.update_xaxes(tickangle=-28)
    fig.update_yaxes(range=[0, max(100, top_role_chart["match_user_rate_pct"].max() + 10)], ticksuffix="%")
    fig.add_hline(
        y=90,
        line_dash="dash",
        line_color=COLORS["text"],
        annotation_text="90% coverage target",
        annotation_position="top left",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    combo_display = combo_df.copy()
    combo_display = combo_display.sort_values(["users", "users_with_match"], ascending=[False, False]).reset_index(drop=True)
    combo_display["match_user_rate_pct"] = combo_display["match_user_rate"] * 100
    combo_display["approved_user_rate_after_match_pct"] = combo_display["approved_user_rate_after_match"] * 100
    combo_display["application_user_rate_after_approval_pct"] = combo_display["application_user_rate_after_approval"] * 100
    combo_display["coverage_gap_score"] = combo_display["users"] * (1 - combo_display["match_user_rate"].fillna(0))
    combo_display["users_without_match"] = (combo_display["users"] - combo_display["users_with_match"]).clip(lower=0)
    combo_display["approval_gap_users"] = (combo_display["users_with_match"] - combo_display["users_with_approved_match"]).clip(lower=0)
    combo_display["application_gap_users"] = (combo_display["users_with_approved_match"] - combo_display["users_with_application"]).clip(lower=0)
    combo_display[["largest_gap_stage", "largest_gap_users"]] = combo_display.apply(
        lambda row: pd.Series(get_largest_gap_stage(row)),
        axis=1,
    )
    if comparison_combo_df is not None and not comparison_combo_df.empty:
        comparison_combo_display = comparison_combo_df.copy()
        comparison_combo_display["comparison_match_user_rate_pct"] = comparison_combo_display["match_user_rate"] * 100
        combo_display = combo_display.merge(
            comparison_combo_display[["role", "location", "comparison_match_user_rate_pct"]],
            on=["role", "location"],
            how="left",
        )
        combo_display["match_coverage_delta_pts"] = (
            combo_display["match_user_rate_pct"] - combo_display["comparison_match_user_rate_pct"]
        )

    combo_gap_df = combo_display[combo_display["match_user_rate_pct"] < 90].copy()
    gap_count = len(combo_gap_df)
    shown_count = min(50, gap_count)
    st.subheader(f"Role x Geography Combos Below 90% Match Coverage ({shown_count} shown)")
    underserved_df = combo_gap_df.sort_values(["coverage_gap_score", "users"], ascending=[False, False]).head(50).reset_index(drop=True)
    if underserved_df.empty:
        st.info("No role x geography cohorts are below the 90% match coverage target in the selected window.")
        render_page_reference(lineage_sections=reference_lineage)
        return
    underserved_df["gap_rank"] = underserved_df.index + 1
    combo_table_columns = [
        "gap_rank",
        "role",
        "location",
        "users",
        "users_without_match",
        "approval_gap_users",
        "application_gap_users",
        "match_user_rate_pct",
        "approved_user_rate_after_match_pct",
        "application_user_rate_after_approval_pct",
        "largest_gap_stage",
        "largest_gap_users",
    ]
    if "match_coverage_delta_pts" in underserved_df.columns:
        combo_table_columns.append("match_coverage_delta_pts")
    combo_table_columns.extend(["realized_cpa", "avg_cpa_per_application"])

    combo_table = underserved_df[combo_table_columns].rename(
        columns={
            "gap_rank": "Gap Rank",
            "role": "Target Role",
            "location": "Target Geography",
            "users": "Users",
            "users_without_match": "No Match Users",
            "approval_gap_users": "Not Approved After Match",
            "application_gap_users": "Approved But Not Applied",
            "match_user_rate_pct": "Match Coverage %",
            "approved_user_rate_after_match_pct": "Approval After Match %",
            "application_user_rate_after_approval_pct": "Application After Approval %",
            "largest_gap_stage": "Largest Gap Stage",
            "largest_gap_users": "Users Lost at Largest Gap",
            "match_coverage_delta_pts": "Match Coverage Δ vs Compare (pts)",
            "realized_cpa": "Realized CPA",
            "avg_cpa_per_application": "Avg CPA / App",
        }
    )
    combo_table_height = min(1800, 42 + (len(combo_table) + 1) * 35)
    st.caption(
        f"Showing {shown_count} current role x geography cohorts below the 90% match coverage target, ranked by uncovered demand. "
        f"{'There are fewer than 50 qualifying cohorts under the current filters.' if gap_count < 50 else 'This is the top 50 only.'} "
        "The gap-stage columns show where the funnel is breaking."
    )
    st.dataframe(
        build_table_styler(
            combo_table,
            {
                "Gap Rank": "{:,.0f}",
                "Users": "{:,.0f}",
                "No Match Users": "{:,.0f}",
                "Not Approved After Match": "{:,.0f}",
                "Approved But Not Applied": "{:,.0f}",
                "Match Coverage %": "{:.1f}%",
                "Approval After Match %": "{:.1f}%",
                "Application After Approval %": "{:.1f}%",
                "Users Lost at Largest Gap": "{:,.0f}",
                "Match Coverage Δ vs Compare (pts)": "{:+.1f}",
                "Realized CPA": "${:,.0f}",
                "Avg CPA / App": "${:,.0f}",
            },
            percent_columns=["Match Coverage %", "Approval After Match %", "Application After Approval %"],
            delta_columns=["Match Coverage Δ vs Compare (pts)"],
            stage_columns=["Largest Gap Stage"],
            row_highlight_column="Match Coverage %",
            row_highlight_threshold=90,
        ),
        use_container_width=True,
        hide_index=True,
        height=combo_table_height,
    )

    combo_chart = underserved_df.head(10).copy()
    combo_chart["chart_label"] = combo_chart.apply(
        lambda row: wrap_chart_label(f"{row['role']} / {row['location']}", rank=int(row["gap_rank"]), width=16),
        axis=1,
    )
    funnel_chart = combo_chart.melt(
        id_vars=["chart_label"],
        value_vars=[
            "match_user_rate_pct",
            "approved_user_rate_after_match_pct",
            "application_user_rate_after_approval_pct",
        ],
        var_name="stage",
        value_name="conversion_pct",
    )
    stage_labels = {
        "match_user_rate_pct": "Match Coverage",
        "approved_user_rate_after_match_pct": "Approval After Match",
        "application_user_rate_after_approval_pct": "Application After Approval",
    }
    funnel_chart["stage"] = funnel_chart["stage"].map(stage_labels)
    funnel_chart["conversion_label"] = funnel_chart["conversion_pct"].map(lambda value: f"{value:.1f}%")
    fig = px.bar(
        funnel_chart,
        x="chart_label",
        y="conversion_pct",
        color="stage",
        barmode="group",
        text="conversion_label",
        color_discrete_map=FUNNEL_STAGE_COLOR_MAP,
        labels={"chart_label": "Role / Geography Cohort", "conversion_pct": "Conversion %", "stage": "Funnel Stage"},
    )
    apply_theme(fig, title="Top Below-Target Role x Geography Funnel Stage Conversion", height=560, x_title="Role / Geography Cohort", y_title="Conversion %")
    fig.update_traces(textposition="outside", textfont=dict(size=12, color=COLORS["text"]), cliponaxis=False)
    fig.update_layout(legend_title_text="")
    fig.update_xaxes(tickangle=-26)
    fig.update_yaxes(range=[0, max(100, funnel_chart["conversion_pct"].max() + 12)], ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True)

    render_page_reference(lineage_sections=reference_lineage)


# ══════════════════════════════════════════════════════════════════════════════
# TAB: Match Timing
# ══════════════════════════════════════════════════════════════════════════════

def render_match_timing():
    render_page_header("Match Timing", "When matches are created and how quickly they move to approval and application.")
    match_source = TIME_FILTERS["match_source"]
    start_date = TIME_FILTERS["primary_start"]
    end_date = TIME_FILTERS["primary_end"]
    compare_start = TIME_FILTERS["compare_start"] if TIME_FILTERS["compare_enabled"] else None
    compare_end = TIME_FILTERS["compare_end"] if TIME_FILTERS["compare_enabled"] else None
    reference_fields = [
        "`user_job_match_auto_apply_posting_match.created_at`",
        "`user_job_match_auto_apply_posting_match.user_approved_at`",
        "`user_job_match_auto_apply_posting_match.applied_at`",
        "`user_job_match_auto_apply_posting_match.match_generation_version`",
        "`user_job_match_auto_apply_posting.xml_raw_job_uuid`",
        "`job_postings.xml_job_uuid`",
    ]
    reference_lineage = [("Active match source filter", describe_match_source_filter(match_source))]

    @st.cache_data(ttl=config.CACHE_TTL)
    def _timing(start_date, end_date, match_source):
        return bq_client.get_match_timing_stats(start_date, end_date, match_source=match_source)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _ver_time(start_date, end_date, match_source):
        return bq_client.get_match_version_over_time(start_date=start_date, end_date=end_date, match_source=match_source)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _by_hour(start_date, end_date, match_source):
        return bq_client.get_match_volume_by_hour(start_date, end_date, match_source=match_source)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _by_dow(start_date, end_date, match_source):
        return bq_client.get_match_volume_by_dow(start_date, end_date, match_source=match_source)

    try:
        timing_df = _timing(start_date, end_date, match_source)
        timing_df["version"] = timing_df["version"].map(pretty_label)
        ver_df = _ver_time(start_date, end_date, match_source)
        ver_df["version"] = ver_df["version"].map(pretty_label)
        hour_df = _by_hour(start_date, end_date, match_source)
        dow_df = _by_dow(start_date, end_date, match_source)
        comparison_timing_df = _timing(compare_start, compare_end, match_source) if TIME_FILTERS["compare_enabled"] else None
    except Exception as e:
        st.error(str(e))
        return

    render_summary_card(build_match_timing_summary(timing_df, dow_df, comparison_timing_df, match_source=match_source))

    st.subheader("Average Conversion Times by Version")
    st.dataframe(
        timing_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "version": "Version",
            "total": st.column_config.NumberColumn("Total Matches", format="%d"),
            "avg_hours_to_approval": st.column_config.NumberColumn("Avg Hours to Approval", format="%.1f"),
            "avg_hours_to_application": st.column_config.NumberColumn("Avg Hours to Application", format="%.1f"),
        },
    )

    st.markdown("---")
    st.subheader("Match Generation Version Over Time")
    fig = px.area(
        ver_df,
        x="date",
        y="count",
        color="version",
        labels={"date": "Match Created Date", "count": "Matches", "version": "Generation Version"},
        color_discrete_sequence=[COLORS["info"], COLORS["warning"], COLORS["success"]],
    )
    apply_theme(fig, height=420, x_title="Match Created Date", y_title="Matches")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Matches by Hour of Day")
        fig = px.bar(hour_df, x="hour", y="count", labels={"hour": "Hour of Day", "count": "Matches"})
        style_bar(fig)
        apply_theme(fig, height=360, x_title="Hour of Day", y_title="Matches")
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Matches by Day of Week")
        st.dataframe(
            dow_df.rename(columns={"day_name": "Day of Week", "count": "Matches"})[["Day of Week", "Matches"]],
            use_container_width=True,
            hide_index=True,
        )
        fig = px.bar(dow_df, x="day_name", y="count", labels={"day_name": "Day of Week", "count": "Matches"})
        style_bar(fig)
        apply_theme(fig, height=360, x_title="Day of Week", y_title="Matches")
        st.plotly_chart(fig, use_container_width=True)

    render_page_reference(
        table_fields=reference_fields,
        timeframe_field="`user_job_match_auto_apply_posting_match.created_at`",
        lineage_sections=reference_lineage,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB: Contractor Performance
# ══════════════════════════════════════════════════════════════════════════════

def render_contractor():
    render_page_header("Contractor Performance", "Operational performance by contractor, with conversion efficiency in the selected period.")
    match_source = TIME_FILTERS["match_source"]
    start_date = TIME_FILTERS["primary_start"]
    end_date = TIME_FILTERS["primary_end"]
    compare_start = TIME_FILTERS["compare_start"] if TIME_FILTERS["compare_enabled"] else None
    compare_end = TIME_FILTERS["compare_end"] if TIME_FILTERS["compare_enabled"] else None
    reference_fields = [
        "`user_job_match_auto_apply_posting_match.created_at`",
        "`user_job_match_auto_apply_posting_match.assignedUserId`",
        "`user_job_match_auto_apply_posting_match.status`",
        "`user_job_match_auto_apply_posting_match.user_approved_at`",
        "`user_job_match_auto_apply_posting_match.applied_at`",
        "`user_job_match_auto_apply_posting.xml_raw_job_uuid`",
        "`job_postings.xml_job_uuid`",
    ]
    reference_lineage = [("Active match source filter", describe_match_source_filter(match_source))]

    @st.cache_data(ttl=config.CACHE_TTL)
    def _contractors(start_date, end_date, match_source):
        return bq_client.get_contractor_performance(start_date, end_date, match_source=match_source)

    try:
        df = _contractors(start_date, end_date, match_source)
        comparison_df = _contractors(compare_start, compare_end, match_source) if TIME_FILTERS["compare_enabled"] else None
        if df.empty:
            st.info("No contractor data found.")
            return

        render_summary_card(build_contractor_summary(df, comparison_df, match_source=match_source))

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Contractors", len(df))
        c2.metric("Avg Conversion Rate", f"{df['conversion_rate'].mean() * 100:.1f}%")
        c3.metric("Total Applied", f"{int(df['applied'].sum()):,}")

        st.markdown("---")
        st.subheader("Contractor Details")
        details_df = df.copy()
        details_df["conversion_rate_pct"] = details_df["conversion_rate"] * 100
        st.dataframe(details_df[[
            "contractor_id", "total_assigned", "applied", "failed", "pending", "conversion_rate_pct", "avg_hours_to_apply"
        ]], use_container_width=True, height=500, hide_index=True,
                     column_config={
                         "contractor_id": "Contractor ID",
                         "total_assigned": st.column_config.NumberColumn("Total Assigned", format="%d"),
                         "applied": st.column_config.NumberColumn("Applied", format="%d"),
                         "failed": st.column_config.NumberColumn("Failed", format="%d"),
                         "pending": st.column_config.NumberColumn("Pending", format="%d"),
                         "conversion_rate_pct": st.column_config.NumberColumn("Conversion Rate", format="%.1f%%"),
                         "avg_hours_to_apply": st.column_config.NumberColumn("Avg Hours to Apply", format="%.1f"),
                     })

        st.markdown("---")
        col_l, col_r = st.columns(2)

        with col_l:
            st.subheader("Top Contractors by Volume")
            top = df.nlargest(20, "total_assigned").copy()
            top["conversion_rate_pct"] = top["conversion_rate"] * 100
            top["performance_band"] = pd.cut(
                top["conversion_rate_pct"],
                bins=[-0.01, 25, 50, 100],
                labels=["Low Coverage", "Opportunity Band", "Healthy Coverage"],
            )
            fig = px.bar(top.sort_values("total_assigned", ascending=True),
                         x="total_assigned", y="contractor_id", orientation="h",
                         color="performance_band",
                         labels={"total_assigned": "Assignments", "contractor_id": "Contractor", "performance_band": "Conversion Tier"},
                         color_discrete_map=COVERAGE_TIER_COLORS)
            apply_theme(fig, height=500, x_title="Assignments", y_title="Contractor")
            fig.update_layout(legend_title_text="")
            fig.update_layout(margin=dict(l=140))
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.subheader("Conversion Rate Distribution")
            hist_df = df.copy()
            hist_df["conversion_rate_pct"] = hist_df["conversion_rate"] * 100
            fig = px.histogram(hist_df, x="conversion_rate_pct", nbins=20, labels={"conversion_rate_pct": "Conversion Rate (%)"})
            style_bar(fig)
            apply_theme(fig, height=500, x_title="Conversion Rate (%)", y_title="Contractors")
            st.plotly_chart(fig, use_container_width=True)

        render_page_reference(
            table_fields=reference_fields,
            timeframe_field="`user_job_match_auto_apply_posting_match.created_at`",
            lineage_sections=reference_lineage,
        )

    except Exception as e:
        st.error(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# TAB: Data Explorer
# ══════════════════════════════════════════════════════════════════════════════

def render_data_explorer():
    render_page_header("Data Explorer", "Browse raw joined records and validate assumptions directly against source tables.", show_time_filters=False)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _schema(t):
        return bq_client.get_table_schema(t)

    try:
        settings_schema = _schema("user_job_match_settings")
        user_schema = _schema("user")
        posting_schema = _schema("user_job_match_auto_apply_posting_match")
    except Exception as e:
        st.error(f"Schema load error: {e}")
        return

    settings_columns = settings_schema["column_name"].tolist()
    settings_types = dict(zip(settings_schema["column_name"], settings_schema["data_type"]))
    user_columns = user_schema["column_name"].tolist()
    user_types = dict(zip(user_schema["column_name"], user_schema["data_type"]))
    posting_columns = posting_schema["column_name"].tolist()
    posting_types = dict(zip(posting_schema["column_name"], posting_schema["data_type"]))

    timestamp_cols = (
        [f"s.{c}" for c, t in settings_types.items() if "TIMESTAMP" in t or "DATE" in t]
        + [f"u.{c}" for c, t in user_types.items() if "TIMESTAMP" in t or "DATE" in t]
        + [f"p.{c}" for c, t in posting_types.items() if "TIMESTAMP" in t or "DATE" in t]
    )

    with st.expander("Column Selection", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            sel_settings = st.multiselect("Settings columns", settings_columns, default=settings_columns, key="de_settings")
        with c2:
            sel_user = st.multiselect("User columns", user_columns, default=user_columns, key="de_user")
        with c3:
            sel_posting = st.multiselect("Posting Match columns", posting_columns, default=[], key="de_posting")

    with st.expander("Filters", expanded=False):
        fc1, fc2, fc3 = st.columns(3)
        where_parts = []
        with fc1:
            if timestamp_cols:
                time_col = st.selectbox("Time column", timestamp_cols, key="de_time")
                hours_back = st.slider("Last N hours", 1, 720, 24, key="de_hours")
                where_parts.append(f"{time_col} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours_back} HOUR)")
        with fc2:
            custom_where = st.text_input(
                "Custom WHERE",
                placeholder="s.status != 'PAUSED' AND u.default_resume_id IS NOT NULL",
                key="de_where",
            )
            if custom_where:
                where_parts.append(f"({custom_where})")
        with fc3:
            row_limit = st.number_input("Row limit", 100, 50000, config.DEFAULT_ROW_LIMIT, step=100, key="de_limit")
            order_opts = [f"s.{c}" for c in sel_settings] + [f"u.{c}" for c in sel_user] + [f"p.{c}" for c in sel_posting]
            if not order_opts:
                order_opts = [f"s.{settings_columns[0]}"]
            order_by = st.selectbox("Order by", order_opts, key="de_order")

    where_clause = " AND ".join(where_parts)

    @st.cache_data(ttl=config.CACHE_TTL)
    def _load(s, u, p, w, o, l):
        return bq_client.query_three_way_join(
            settings_columns=list(s) if s else None,
            user_columns=list(u) if u else None,
            posting_columns=list(p) if p else None,
            where_clause=w, order_by=o, limit=l,
        )

    try:
        df = _load(
            tuple(sel_settings) if sel_settings else None,
            tuple(sel_user) if sel_user else None,
            tuple(sel_posting) if sel_posting else None,
            where_clause, order_by, row_limit,
        )
        st.subheader(f"Results ({len(df):,} rows)")
        st.dataframe(df, use_container_width=True, height=500)
    except Exception as e:
        st.error(f"Query error: {e}")

    with st.expander("Table Schema — Settings (s)"):
        st.dataframe(settings_schema, use_container_width=True)
    with st.expander("Table Schema — User (u)"):
        st.dataframe(user_schema, use_container_width=True)
    with st.expander("Table Schema — Posting Match (p)"):
        st.dataframe(posting_schema, use_container_width=True)
    st.caption("Joins: `s.user_id = u.id` | `s.uuid = p.user_job_match_settings_uuid`")


# ══════════════════════════════════════════════════════════════════════════════
# Main Dispatch
# ══════════════════════════════════════════════════════════════════════════════

PAGES = {
    "Query Lab": render_query_lab,
    "Overview": render_overview,
    "Match Funnel": render_match_funnel,
    "User Cohorts": render_user_cohorts,
    "Location Analysis": render_location,
    "Role & Industry": render_role_industry,
    "Match Timing": render_match_timing,
    "Contractor Performance": render_contractor,
    "Data Explorer": render_data_explorer,
}

PAGES[page]()
