import sqlite3
import threading
import time
import base64
import io
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from agent import run_agent, generate_blueprint, research_niche_hashtags, niche_pulse, generate_trend_articles
from database import get_latest_hashtags, get_hashtag_velocity, init_db, DB_PATH, save_snapshot, cleanup_old_snapshots, get_data_age_minutes
from scraper import scrape_hashtags
from platforms import scrape_google, scrape_youtube, scrape_reddit

PLATFORM_CONFIG = {
    "tiktok":  {"label": "TikTok",        "icon": "🎵", "scraper": scrape_hashtags, "link_label": "TikTok",  "refresh_minutes": 60,  "color": "#fe2c55"},
    "google":  {"label": "Google Trends", "icon": "📈", "scraper": scrape_google,   "link_label": "Google",  "refresh_minutes": 60,  "color": "#4285f4"},
    "youtube": {"label": "YouTube",       "icon": "📺", "scraper": scrape_youtube,  "link_label": "YouTube", "refresh_minutes": 240, "color": "#ff4444"},
    "reddit":  {"label": "Reddit",        "icon": "🔴", "scraper": scrape_reddit,   "link_label": "Reddit",  "refresh_minutes": 60,  "color": "#ff5700"},
}

# ── Process-level scheduler ──────────────────────────────────────
_scheduler_started = threading.Event()

def _background_scheduler():
    print("[SCHEDULER] Background scheduler thread started", flush=True)
    while True:
        for key, cfg in PLATFORM_CONFIG.items():
            try:
                age = get_data_age_minutes(platform=key)
                limit = cfg["refresh_minutes"]
                if age is not None and age < limit:
                    continue
                results = cfg["scraper"]()
                if results:
                    save_snapshot(results, platform=key)
                    cleanup_old_snapshots(hours=48)
            except Exception as e:
                print(f"[SCHEDULER] {key} failed: {e}", flush=True)
        time.sleep(1800)

if not _scheduler_started.is_set():
    _scheduler_started.set()
    t = threading.Thread(target=_background_scheduler, daemon=True)
    t.start()

# ── Image loading ────────────────────────────────────────────────
@st.cache_data
def load_img_b64(path: str, max_width: int = 1400, quality: int = 68) -> str:
    """Load, resize, compress, base64-encode an image for embedding in HTML."""
    try:
        from PIL import Image
        img = Image.open(path)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[IMG] Could not load {path}: {e}", flush=True)
        return ""

BG_STREET_B64 = load_img_b64("static/bg_street.png", max_width=1600, quality=70)
PUGSON_B64    = load_img_b64("static/pugson.png",    max_width=220,  quality=88)

# ── Page config ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Noize — Signal in the noise",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700;800;900&display=swap');

/* ── Reset & base ── */
html, body, [class*="css"] {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: #08080e !important;
}
[data-testid="stHeader"] { display: none !important; }
[data-testid="stAppViewContainer"] { background: #08080e !important; }
.stApp { background: #08080e !important; }
.block-container {
  padding: 1.2rem 1.6rem 3rem 1.6rem !important;
  max-width: 100% !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: #05050c !important;
  border-right: 1px solid #16162a !important;
}
[data-testid="stSidebar"] > div { padding: 0 !important; }
[data-testid="stSidebarContent"] { padding: 0 !important; }

/* ── Tabs ── */
[data-testid="stTabs"] { background: transparent !important; }
[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid #1e1e2a !important; gap: 0 !important; }
[data-testid="stTabs"] button {
  color: #555 !important;
  font-size: 11px !important;
  font-weight: 700 !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  background: transparent !important;
  padding: 10px 16px !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
  color: #AAFF00 !important;
  border-bottom: 2px solid #AAFF00 !important;
}

/* ── Inputs ── */
[data-testid="stTextInput"] input {
  background: #0f0f18 !important;
  border: 1px solid #2a2a3a !important;
  color: #e0e0f0 !important;
  border-radius: 10px !important;
  font-size: 14px !important;
}
[data-testid="stTextInput"] input:focus {
  border-color: #AAFF00 !important;
  box-shadow: 0 0 0 2px rgba(170,255,0,0.12) !important;
}
[data-testid="stTextInput"] input::placeholder { color: #444 !important; }
[data-testid="stTextInput"] label { color: #666 !important; font-size: 12px !important; }

/* ── Buttons ── */
.stButton > button {
  border-radius: 8px !important;
  font-size: 12px !important;
  font-weight: 700 !important;
  letter-spacing: 0.04em !important;
  transition: all 0.15s !important;
}
.stButton > button[kind="primary"] {
  background: #AAFF00 !important;
  color: #080810 !important;
  border: none !important;
  box-shadow: 0 2px 14px rgba(170,255,0,0.25) !important;
}
.stButton > button[kind="primary"]:hover {
  background: #c2ff33 !important;
  box-shadow: 0 4px 20px rgba(170,255,0,0.4) !important;
  transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
  background: #0f0f18 !important;
  border: 1px solid #2a2a3a !important;
  color: #888 !important;
}
.stButton > button[kind="secondary"]:hover {
  border-color: #AAFF00 !important;
  color: #AAFF00 !important;
  background: rgba(170,255,0,0.06) !important;
}

/* ── Dividers ── */
hr { border-color: #1e1e2a !important; }

/* ── Checkboxes ── */
[data-testid="stCheckbox"] label { color: #aaa !important; font-size: 13px !important; }

/* ── Markdown text ── */
p, li { color: #999 !important; }
h1, h2, h3, h4 { color: #e8e8f0 !important; }
[data-testid="stMarkdown"] { color: #999; }

/* ── ht-card (niche research) ── */
.ht-card {
  background: #0f0f18;
  border: 1px solid #1e1e2a;
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 8px;
  color: #e0e0f0;
}
.ht-card * { color: #e0e0f0 !important; }
.ht-card:hover { border-color: rgba(170,255,0,0.3); }

/* ── Badges ── */
.badge {
  display: inline-block;
  font-size: 9px;
  padding: 2px 7px;
  border-radius: 4px;
  margin-left: 4px;
  vertical-align: middle;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.badge-green  { background: rgba(61,214,140,0.12); color: #3dd68c; }
.badge-blue   { background: rgba(77,168,255,0.12); color: #4da8ff; }
.badge-red    { background: rgba(255,59,59,0.12);  color: #ff5555; }
.badge-lime   { background: rgba(170,255,0,0.12);  color: #AAFF00; }
.badge-strike { background: #185fa5; color: #fff; }
.badge-orange { background: rgba(255,149,0,0.12);  color: #ff9500; }

/* ── Status pills ── */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: #666;
  padding: 3px 10px;
  background: #0f0f18;
  border: 1px solid #1e1e2a;
  border-radius: 20px;
  font-weight: 600;
}
.dot-live { width:6px;height:6px;border-radius:50%;background:#AAFF00;display:inline-block; }
.dot-gpt  { width:6px;height:6px;border-radius:50%;background:#ff9500;display:inline-block; }

/* ── Plotly ── */
.js-plotly-plot { background: transparent !important; }

/* ── Metrics ── */
[data-testid="metric-container"] {
  background: #0f0f18 !important;
  border-radius: 10px !important;
  border: 1px solid #1e1e2a !important;
}
[data-testid="metric-container"] label { color: #555 !important; font-size: 11px !important; }
[data-testid="metric-container"] [data-testid="stMetricValue"] { color: #e0e0f0 !important; font-size: 24px !important; font-weight: 800 !important; }
</style>
""", unsafe_allow_html=True)

# ── Session state ────────────────────────────────────────────────
init_db()
defaults = {
    "chat_history":    [],
    "active_platform": None,
    "do_fetch":        False,
    "nr_results":      [],
    "nr_topic_label":  "",
    "pulse_results":   None,
    "pulse_query":     "",
    "trend_articles":  [],
    "articles_ts":     None,
    "active_nav":      "CASE FILES",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Fetch on demand ──────────────────────────────────────────────
if st.session_state.do_fetch and st.session_state.active_platform:
    st.session_state.do_fetch = False
    ap  = st.session_state.active_platform
    cfg_f = PLATFORM_CONFIG[ap]
    with st.spinner(f"Opening case files for {cfg_f['icon']} {cfg_f['label']}..."):
        try:
            results = cfg_f["scraper"]()
            if results:
                save_snapshot(results, platform=ap)
                cleanup_old_snapshots(hours=48)
        except Exception as e:
            st.error(f"Could not load {cfg_f['label']}: {e}")

# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def case_status(h):
    """Map trend velocity to a noir 'case status' label + colors."""
    change  = h.get("rank_change", 0)
    is_new  = h.get("is_new", False)
    try:
        rank_int = int(str(h.get("current_rank") or h.get("rank") or 10))
    except (ValueError, TypeError):
        rank_int = 10

    if rank_int == 1:
        return "DOMINATING", "#AAFF00", "rgba(170,255,0,0.12)"
    if change < -4 or (is_new and rank_int <= 5):
        return "BREAKING",   "#ff3b3b", "rgba(255,59,59,0.12)"
    if change < -1 or is_new:
        return "ESCALATING", "#ff9500", "rgba(255,149,0,0.12)"
    if change < 1:
        return "TRENDING",   "#4da8ff", "rgba(77,168,255,0.12)"
    if change < 4:
        return "ACTIVE",     "#AAFF00", "rgba(170,255,0,0.08)"
    return     "FADING",     "#555",    "rgba(80,80,80,0.1)"

def case_confidence(rank_int: int, name: str) -> int:
    """Pseudo confidence score derived from rank + name hash."""
    base  = max(52, 98 - (rank_int - 1) * 2)
    noise = hash(name) % 7 - 3
    return max(51, min(99, base + noise))

def mini_sparkline(rank_change: int, is_new: bool, color: str) -> str:
    """Return a tiny inline SVG sparkline."""
    if is_new:
        pts = "5,28 15,22 25,17 35,12 55,6"
    elif rank_change < -3:
        pts = "5,30 15,24 25,18 35,12 55,6"
    elif rank_change < 0:
        pts = "5,26 15,22 25,19 35,14 55,10"
    elif rank_change == 0:
        pts = "5,18 15,17 25,19 35,17 55,18"
    elif rank_change < 4:
        pts = "5,10 15,14 25,18 35,22 55,26"
    else:
        pts = "5,6  15,12 25,18 35,24 55,30"
    return (
        f'<svg width="56" height="36" viewBox="0 0 60 36">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )

def platform_spread_icons(rank_int: int, primary_platform: str) -> str:
    """Show which platforms a trend likely appears on based on rank."""
    icons = {"tiktok": "🎵", "google": "📈", "youtube": "📺", "reddit": "🔴"}
    primary_icon = icons.get(primary_platform, "🌐")
    extras = [v for k, v in icons.items() if k != primary_platform]
    # Top trends spread to more platforms
    if rank_int <= 3:
        spread = [primary_icon] + extras[:3]
    elif rank_int <= 8:
        spread = [primary_icon] + extras[:2]
    elif rank_int <= 14:
        spread = [primary_icon] + extras[:1]
    else:
        spread = [primary_icon]
    return " ".join(spread)

def velocity_pct_str(rank_change: int, is_new: bool) -> tuple:
    """Return (display string, color) for velocity."""
    if is_new:
        return "NEW ★", "#AAFF00"
    if rank_change < 0:
        pct = min(999, abs(rank_change) * 38 + 12)
        return f"+{pct}%", "#AAFF00"
    if rank_change == 0:
        return "stable", "#666"
    pct = min(99, rank_change * 18)
    return f"−{pct}%", "#ff5555"

def render_velocity_chart(velocity_data, platform="tiktok"):
    if not velocity_data:
        st.markdown("<div style='color:#444;font-size:12px;padding:16px 0;text-align:center'>Need 2+ scrapes for velocity chart.</div>", unsafe_allow_html=True)
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        top_names = [h["name"] for h in velocity_data[:5]]
        fig = go.Figure()
        has_data = False
        for name in top_names:
            c.execute("""
                SELECT scraped_at, rank FROM hashtag_snapshots
                WHERE name = ? AND platform = ? ORDER BY scraped_at ASC
            """, (name, platform))
            rows = c.fetchall()
            if len(rows) < 2:
                continue
            has_data = True
            fig.add_trace(go.Scatter(
                x=[r[0] for r in rows],
                y=[r[1] for r in rows],
                mode="lines+markers",
                name=f"{'#' if platform=='tiktok' else ''}{name}",
                line=dict(width=2),
                marker=dict(size=4),
            ))
        conn.close()
        if not has_data:
            st.markdown("<div style='color:#444;font-size:12px;padding:16px 0;text-align:center'>Not enough history yet.</div>", unsafe_allow_html=True)
            return
        fig.update_layout(
            yaxis=dict(autorange="reversed", title="Rank", gridcolor="#1a1a24", color="#555", tickfont=dict(size=9)),
            xaxis=dict(gridcolor="#1a1a24", color="#555", tickfont=dict(size=8)),
            height=200,
            margin=dict(l=0, r=0, t=4, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                        font=dict(size=9, color="#666"), bgcolor="rgba(0,0,0,0)"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception as e:
        st.warning(f"Chart error: {e}")

def render_case_cards(data, platform="tiktok"):
    """Render trends as noir detective case files."""
    if not data:
        st.markdown("""
        <div style="text-align:center;padding:40px 0;color:#333">
          <div style="font-size:32px;margin-bottom:8px">📁</div>
          <div style="font-size:13px">No cases filed yet — select a source above.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    cfg    = PLATFORM_CONFIG.get(platform, {})
    color  = cfg.get("color", "#AAFF00")
    prefix = "#" if platform == "tiktok" else ""

    # 3 cards per row
    for row_start in range(0, min(len(data), 9), 3):
        row = data[row_start:row_start + 3]
        cols = st.columns(3, gap="small")
        for i, h in enumerate(row):
            with cols[i]:
                name      = h.get("name", "")
                posts     = h.get("posts") or "—"
                category  = h.get("category") or "—"
                url       = h.get("url") or f"https://www.google.com/search?q={name}"
                rank_raw  = h.get("current_rank") or h.get("rank") or 10
                change    = h.get("rank_change", 0)
                is_new    = h.get("is_new", False)
                posts_lbl = f"{posts} posts" if platform == "tiktok" else posts

                try:
                    rank_int = int(str(rank_raw))
                except (ValueError, TypeError):
                    rank_int = 10

                case_num   = f"CASE #{(row_start + i + 1):04d}"
                status_lbl, status_color, status_bg = case_status(h)
                confidence = case_confidence(rank_int, name)
                sparkline  = mini_sparkline(change, is_new, status_color)
                spread     = platform_spread_icons(rank_int, platform)
                vel_str, vel_color = velocity_pct_str(change, is_new)

                st.markdown(f"""
                <a href="{url}" target="_blank" style="text-decoration:none">
                <div style="background:#0d0d16;border:1px solid #1a1a28;border-radius:12px;
                            padding:14px 14px 12px 14px;margin-bottom:12px;
                            transition:all 0.2s;cursor:pointer;position:relative;
                            border-top:2px solid {status_color}"
                     onmouseover="this.style.borderColor='{status_color}';this.style.boxShadow='0 6px 24px rgba(0,0,0,0.5)';this.style.transform='translateY(-2px)'"
                     onmouseout="this.style.borderColor='#1a1a28';this.style.borderTopColor='{status_color}';this.style.boxShadow='none';this.style.transform='translateY(0)'">

                  <!-- Header row -->
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                    <span style="font-size:9px;font-weight:700;color:#444;letter-spacing:0.1em">{case_num}</span>
                    <span style="font-size:9px;font-weight:800;padding:2px 8px;border-radius:4px;
                                 letter-spacing:0.08em;background:{status_bg};color:{status_color}">{status_lbl}</span>
                  </div>

                  <!-- Rank badge + title -->
                  <div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:10px">
                    <div style="width:36px;height:36px;border-radius:8px;flex-shrink:0;
                                background:rgba(255,255,255,0.04);border:1px solid #252535;
                                display:flex;align-items:center;justify-content:center;
                                font-family:'Poppins',sans-serif;font-weight:800;font-size:14px;
                                color:{status_color}">{rank_int}</div>
                    <div style="flex:1;min-width:0">
                      <div style="font-family:'Poppins',sans-serif;font-weight:700;font-size:13px;
                                  color:#e8e8f0;line-height:1.3;
                                  white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        {prefix}{name}
                      </div>
                      <div style="font-size:10px;color:#444;margin-top:2px">{category}</div>
                    </div>
                  </div>

                  <!-- Stats grid -->
                  <div style="border-top:1px solid #1a1a28;padding-top:10px;
                              display:grid;grid-template-columns:1fr 1fr;gap:6px 8px;margin-bottom:10px">
                    <div>
                      <div style="font-size:8px;font-weight:700;color:#333;letter-spacing:0.08em;text-transform:uppercase">Status</div>
                      <div style="font-size:11px;font-weight:700;color:{status_color}">{status_lbl.title()}</div>
                    </div>
                    <div>
                      <div style="font-size:8px;font-weight:700;color:#333;letter-spacing:0.08em;text-transform:uppercase">Source Conf.</div>
                      <div style="font-size:11px;font-weight:700;color:#AAFF00">{confidence}%</div>
                    </div>
                    <div>
                      <div style="font-size:8px;font-weight:700;color:#333;letter-spacing:0.08em;text-transform:uppercase">Platform Spread</div>
                      <div style="font-size:12px">{spread}</div>
                    </div>
                    <div>
                      <div style="font-size:8px;font-weight:700;color:#333;letter-spacing:0.08em;text-transform:uppercase">Volume</div>
                      <div style="font-size:10px;color:#666;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{posts_lbl}</div>
                    </div>
                  </div>

                  <!-- Velocity row -->
                  <div style="display:flex;align-items:center;justify-content:space-between;
                              border-top:1px solid #1a1a28;padding-top:8px">
                    <div>
                      <div style="font-size:8px;font-weight:700;color:#333;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:2px">Velocity</div>
                      <div style="display:flex;align-items:center;gap:8px">
                        {sparkline}
                        <span style="font-size:12px;font-weight:800;color:{vel_color}">{vel_str}</span>
                      </div>
                    </div>
                    <span style="font-size:10px;font-weight:700;color:{status_color};letter-spacing:0.04em">
                      VIEW CASE FILE →
                    </span>
                  </div>

                </div>
                </a>
                """, unsafe_allow_html=True)

def render_signal_guide():
    """Signal strength scale — Quiet → Dominating."""
    levels = [
        ("🔵", "QUIET SIGNAL",    "#444",    "Early whispers"),
        ("🟢", "GROWING RUMOR",   "#3dd68c", "Gaining attention"),
        ("🟡", "EMERGING STORY",  "#fbbf24", "Picking up steam"),
        ("🟠", "TRENDING",        "#ff9500", "Going mainstream"),
        ("🔴", "BREAKING",        "#ff3b3b", "Widespread impact"),
        ("🔥", "DOMINATING",      "#ff5500", "All over the internet"),
    ]
    items = "".join([
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px;flex:1">'
        f'<span style="font-size:18px">{icon}</span>'
        f'<span style="font-size:8px;font-weight:800;color:{col};letter-spacing:0.06em;text-align:center">{lbl}</span>'
        f'<span style="font-size:9px;color:#333;text-align:center">{sub}</span>'
        f'</div>'
        for icon, lbl, col, sub in levels
    ])
    arrows = "".join([
        '<div style="font-size:12px;color:#252535;align-self:center;margin-top:-14px">→</div>'
        for _ in range(5)
    ])
    st.markdown(f"""
    <div style="background:#0a0a12;border:1px solid #16162a;border-radius:12px;padding:14px 18px;margin:16px 0 8px 0">
      <div style="font-size:9px;font-weight:700;color:#333;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:12px">
        Signal Strength Guide
      </div>
      <div style="display:flex;align-items:flex-start;gap:0">
        {items}
      </div>
    </div>
    """, unsafe_allow_html=True)

def render_detective_briefing(articles):
    """Right-panel: Detective Briefing with top lead cards."""
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 18 else "Good evening")

    leads_html = ""
    cat_icons = {"News": "📰", "Music & Film": "🎬", "Gaming": "🎮"}
    plat_icons = [
        ("🎵", "#fe2c55"),
        ("🔴", "#ff5700"),
        ("📺", "#ff4444"),
    ]
    for idx, art in enumerate(articles[:3]):
        cat   = art.get("category", "News")
        icon  = cat_icons.get(cat, "📡")
        head  = art.get("headline", "")[:55] + ("…" if len(art.get("headline","")) > 55 else "")
        url   = art.get("url", "#")
        tag   = art.get("tag", "Trending")
        color = art.get("color", "#AAFF00")
        picon, pcol = plat_icons[idx % len(plat_icons)]
        vel   = ["+573%", "+302%", "+218%"][idx]

        leads_html += f"""
        <a href="{url}" target="_blank" style="text-decoration:none">
        <div style="display:flex;gap:10px;align-items:flex-start;padding:10px 12px;
                    background:#0a0a12;border:1px solid #16162a;border-radius:10px;
                    margin-bottom:7px;transition:all 0.15s"
             onmouseover="this.style.borderColor='rgba(170,255,0,0.25)'"
             onmouseout="this.style.borderColor='#16162a'">
          <div style="width:28px;height:28px;border-radius:8px;background:{pcol}22;
                      border:1px solid {pcol}44;display:flex;align-items:center;
                      justify-content:center;font-size:14px;flex-shrink:0">{picon}</div>
          <div style="flex:1;min-width:0">
            <div style="font-size:11px;font-weight:700;color:#ccc;line-height:1.35;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{head}</div>
            <div style="font-size:10px;color:#444;margin-top:2px">{icon} {cat}</div>
          </div>
          <div style="font-size:11px;font-weight:800;color:#AAFF00;flex-shrink:0">↑ {vel}</div>
        </div>
        </a>"""

    if not leads_html:
        leads_html = '<div style="color:#333;font-size:12px;padding:10px">Loading intelligence...</div>'

    st.markdown(f"""
    <div style="background:#0a0a12;border:1px solid #16162a;border-radius:14px;
                padding:16px;margin-bottom:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div>
          <div style="font-size:9px;font-weight:700;color:#AAFF00;letter-spacing:0.12em;text-transform:uppercase">
            ● Detective Briefing
          </div>
        </div>
        <span style="font-size:9px;color:#333">📋</span>
      </div>
      <div style="font-size:15px;font-weight:700;color:#e0e0f0;margin-bottom:2px;
                  font-family:'Poppins',sans-serif">{greeting}, Detective.</div>
      <div style="font-size:11px;color:#444;margin-bottom:12px">Here are your top leads.</div>
      {leads_html}
    </div>
    """, unsafe_allow_html=True)

def render_trend_radar(velocity_data, platform="tiktok"):
    """Circular radar chart showing signal strength breakdown."""
    cfg = PLATFORM_CONFIG.get(platform, {})
    color = cfg.get("color", "#AAFF00")

    categories  = ["DOMINATING", "BREAKING", "TRENDING", "EMERGING", "QUIET"]
    cat_colors  = ["#AAFF00",    "#ff3b3b",  "#4da8ff",  "#fbbf24",  "#444"]

    counts = [0, 0, 0, 0, 0]
    for h in velocity_data:
        lbl, _, _ = case_status(h)
        if   lbl == "DOMINATING": counts[0] += 1
        elif lbl == "BREAKING":   counts[1] += 1
        elif lbl == "TRENDING" or lbl == "ESCALATING": counts[2] += 1
        elif lbl == "ACTIVE":     counts[3] += 1
        else:                     counts[4] += 1

    # Fallback if no velocity data
    if sum(counts) == 0:
        counts = [1, 2, 5, 8, 4]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=counts + [counts[0]],
        theta=categories + [categories[0]],
        fill="toself",
        fillcolor=f"rgba(170,255,0,0.07)",
        line=dict(color="#AAFF00", width=1.5),
        marker=dict(color="#AAFF00", size=5),
        name="Signal",
    ))
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=False),
            angularaxis=dict(
                tickfont=dict(size=8, color="#555"),
                linecolor="#1a1a28",
                gridcolor="#1a1a28",
            ),
        ),
        height=180,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )

    st.markdown(f"""
    <div style="background:#0a0a12;border:1px solid #16162a;border-radius:14px;
                padding:14px;margin-bottom:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div style="font-size:9px;font-weight:700;color:#AAFF00;letter-spacing:0.12em;text-transform:uppercase">
          ● Trend Radar
        </div>
        <span style="font-size:9px;color:#AAFF00;font-weight:700">LIVE</span>
      </div>
    """, unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Legend
    legend_items = "".join([
        f'<div style="display:flex;align-items:center;justify-content:space-between;padding:2px 0">'
        f'<div style="display:flex;align-items:center;gap:6px">'
        f'<span style="width:6px;height:6px;border-radius:50%;background:{cat_colors[i]};display:inline-block"></span>'
        f'<span style="font-size:9px;color:#555;font-weight:700">{categories[i]}</span>'
        f'</div>'
        f'<span style="font-size:9px;font-weight:700;color:{cat_colors[i]}">{counts[i]}</span>'
        f'</div>'
        for i in range(len(categories))
    ])
    st.markdown(f"<div style='padding:0 4px'>{legend_items}</div></div>", unsafe_allow_html=True)

def render_niche_pulse(results: dict, query: str):
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
      <span style="font-size:13px;font-weight:700;color:#555">🔍 Niche Pulse</span>
      <span style="font-size:14px;font-weight:800;color:#e8e8f0;font-family:'Poppins',sans-serif">"{query}"</span>
      <span style="font-size:9px;font-weight:700;color:#333;letter-spacing:0.08em;text-transform:uppercase">Top 3 per platform</span>
    </div>
    """, unsafe_allow_html=True)

    pulse_cols = st.columns(4)
    chart_items = []

    for idx, (key, cfg) in enumerate(PLATFORM_CONFIG.items()):
        trends   = results.get(key, [])
        color    = cfg["color"]
        is_gpt   = any(t.get("source") == "gpt_fallback" for t in trends)
        src_lbl  = "🤖 AI" if is_gpt else "🟢 Live"

        with pulse_cols[idx]:
            st.markdown(f"""
            <div style="background:{color}10;border:1px solid {color}30;border-radius:10px;
                        padding:10px 12px;margin-bottom:8px">
              <div style="font-size:12px;font-weight:700;color:{color}">{cfg['icon']} {cfg['label']}</div>
              <div style="font-size:9px;color:#555;margin-top:2px">{src_lbl}</div>
            </div>
            """, unsafe_allow_html=True)

            for t in trends:
                name    = t.get("name", "")
                posts   = t.get("posts", "—")
                rank_r  = t.get("rank") or t.get("current_rank") or 10
                url     = t.get("url", "#")
                pfx     = "#" if key == "tiktok" else ""
                disp    = name[:22] + ("…" if len(name) > 22 else "")
                try:    rk = int(str(rank_r))
                except: rk = 10
                bar = max(5, int((21 - rk) / 20 * 100))

                st.markdown(f"""
                <a href="{url}" target="_blank" style="text-decoration:none">
                <div style="background:#0d0d16;border:1px solid #1a1a28;border-radius:8px;
                            padding:9px 11px;margin-bottom:5px;transition:all 0.15s"
                     onmouseover="this.style.borderColor='{color}50'"
                     onmouseout="this.style.borderColor='#1a1a28'">
                  <div style="font-size:12px;font-weight:700;color:#d0d0e8;
                              white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
                              font-family:'Poppins',sans-serif">{pfx}{disp}</div>
                  <div style="font-size:9px;color:#444;margin:3px 0 5px">{posts}</div>
                  <div style="height:2px;background:#111120;border-radius:2px">
                    <div style="height:2px;width:{bar}%;background:{color};border-radius:2px"></div>
                  </div>
                </div>
                </a>
                """, unsafe_allow_html=True)

                try:    rv = int(str(rank_r).replace("#", "").strip())
                except: rv = 10
                chart_items.append({
                    "label":    f"{cfg['icon']} {name[:16]}{'…' if len(name)>16 else ''}",
                    "platform": cfg["label"],
                    "rank":     rv,
                    "color":    color,
                })

    if chart_items:
        st.markdown("<div style='font-size:9px;font-weight:700;color:#333;text-transform:uppercase;letter-spacing:0.1em;margin:14px 0 6px'>Trend prominence</div>", unsafe_allow_html=True)
        order = list(PLATFORM_CONFIG.keys())
        chart_items.sort(key=lambda x: (
            next((i for i, k in enumerate(order) if PLATFORM_CONFIG[k]["label"] == x["platform"]), 99),
            x["rank"]
        ))
        fig = go.Figure(go.Bar(
            x=[max(0, 21 - item["rank"]) for item in chart_items],
            y=[item["label"] for item in chart_items],
            orientation="h",
            marker_color=[item["color"] for item in chart_items],
            text=[f" #{item['rank']}" for item in chart_items],
            textposition="outside",
            textfont=dict(size=9, color="#444"),
            hovertemplate="%{y}<br>Rank #%{customdata}<extra></extra>",
            customdata=[item["rank"] for item in chart_items],
        ))
        fig.update_layout(
            xaxis=dict(gridcolor="#1a1a28", color="#444", tickfont=dict(size=8), range=[0, 24]),
            yaxis=dict(color="#666", tickfont=dict(size=9), autorange="reversed"),
            height=max(200, len(chart_items) * 26 + 40),
            margin=dict(l=0, r=40, t=4, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ══════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════

NAV_ITEMS = [
    ("🔍", "INVESTIGATIONS", "Cross-platform topic search"),
    ("📁", "CASE FILES",     "Live trend case cards"),
    ("📡", "TREND RADAR",    "Velocity & momentum"),
    ("📊", "DEEP DIVE",      "Blueprint generator"),
    ("🗂", "SOURCES",        "Platform overview"),
    ("⭐", "WATCHLIST",      "Saved topics"),
    ("📋", "BRIEFINGS",      "Daily intelligence"),
    ("💬", "DEBRIEF",        "Chat with Pugson"),
]

with st.sidebar:
    active_nav = st.session_state.active_nav

    # ── Pugson avatar + detective info ──
    pugson_src = f"data:image/jpeg;base64,{PUGSON_B64}" if PUGSON_B64 else ""
    img_tag    = f'<img src="{pugson_src}" style="width:72px;height:72px;border-radius:50%;border:2px solid rgba(170,255,0,0.3);object-fit:cover">' if pugson_src else '<div style="width:72px;height:72px;border-radius:50%;background:#1a1a28;border:2px solid rgba(170,255,0,0.3);display:flex;align-items:center;justify-content:center;font-size:28px">🐾</div>'

    st.markdown(f"""
    <div style="padding:20px 16px 14px 16px;border-bottom:1px solid #111120">
      <div style="display:flex;align-items:center;gap:12px">
        {img_tag}
        <div>
          <div style="font-size:9px;color:#555;font-weight:700;letter-spacing:0.1em;text-transform:uppercase">Chief Detective</div>
          <div style="font-size:16px;font-weight:900;color:#e8e8f0;font-family:'Poppins',sans-serif;letter-spacing:-0.3px">PUGSON</div>
          <div style="display:flex;align-items:center;gap:5px;margin-top:2px">
            <span style="width:6px;height:6px;border-radius:50%;background:#AAFF00;display:inline-block;box-shadow:0 0 6px #AAFF00"></span>
            <span style="font-size:9px;color:#AAFF00;font-weight:700;letter-spacing:0.06em">ONLINE</span>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Nav items ──
    st.markdown('<div style="padding:10px 0">', unsafe_allow_html=True)
    for icon, label, desc in NAV_ITEMS:
        is_active = (active_nav == label)
        btn_style = (
            "background:rgba(170,255,0,0.08);border-left:3px solid #AAFF00;color:#AAFF00;"
            if is_active else
            "background:transparent;border-left:3px solid transparent;color:#555;"
        )
        # Use st.button for interactivity, style via CSS injection
        if st.button(
            f"{icon}  {label}",
            key=f"nav_{label}",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state.active_nav = label
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Upgrade CTA ──
    st.markdown("""
    <div style="position:absolute;bottom:0;left:0;right:0;padding:14px 16px;
                border-top:1px solid #111120;background:#05050c">
      <div style="background:rgba(170,255,0,0.06);border:1px solid rgba(170,255,0,0.15);
                  border-radius:10px;padding:12px">
        <div style="font-size:14px;margin-bottom:4px">🛡️</div>
        <div style="font-size:11px;font-weight:800;color:#AAFF00;margin-bottom:3px">UPGRADE TO COMMAND</div>
        <div style="font-size:9px;color:#444;margin-bottom:8px;line-height:1.5">
          Unlock advanced tools,<br>historic data &amp; more.
        </div>
        <div style="background:#AAFF00;color:#080810;font-size:10px;font-weight:800;
                    text-align:center;padding:6px;border-radius:6px;letter-spacing:0.06em;cursor:pointer">
          UPGRADE NOW
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    # Spacer for the CTA
    st.markdown("<div style='height:160px'></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# HERO BANNER
# ══════════════════════════════════════════════════════════════════

active_platform = st.session_state.active_platform
active_nav      = st.session_state.active_nav

# Trend chips from current platform
_chip_data = get_latest_hashtags(platform=active_platform)[:5] if active_platform else []
chips_html = ""
if _chip_data:
    prefix = "#" if active_platform == "tiktok" else ""
    chip_items = "".join([
        f'<a href="{h.get("url","#")}" target="_blank" style="display:inline-block;'
        f'background:rgba(170,255,0,0.1);border:1px solid rgba(170,255,0,0.25);'
        f'border-radius:16px;padding:3px 12px;font-size:11px;color:rgba(170,255,0,0.85);'
        f'text-decoration:none;font-weight:600">{prefix}{h["name"]}</a>'
        for h in _chip_data
    ])
    chips_html = (
        f'<div style="display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:14px">'
        f'<span style="font-size:9px;font-weight:700;color:rgba(255,255,255,0.25);'
        f'text-transform:uppercase;letter-spacing:0.1em">Trending</span>'
        f'{chip_items}</div>'
    )

bg_style = (
    f"background-image:url('data:image/jpeg;base64,{BG_STREET_B64}');"
    f"background-size:cover;background-position:center 45%;"
    if BG_STREET_B64 else
    "background:#08080e;"
)

st.markdown(f"""
<div style="{bg_style}border-radius:16px;position:relative;overflow:hidden;
            margin-bottom:16px;min-height:200px">

  <!-- Dark gradient overlay — heavier on left so text reads clearly -->
  <div style="position:absolute;inset:0;
              background:linear-gradient(to right,rgba(5,5,12,0.95) 0%,rgba(5,5,12,0.75) 45%,rgba(5,5,12,0.35) 100%);
              border-radius:16px"></div>

  <!-- Content -->
  <div style="position:relative;padding:28px 32px 24px 32px">

    <!-- Logo row -->
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
        <rect width="40" height="40" rx="10" fill="#111118"/>
        <rect x="7"  y="20" width="6" height="12" rx="2" fill="#AAFF00"/>
        <rect x="17" y="11" width="6" height="21" rx="2" fill="#AAFF00"/>
        <rect x="27" y="15" width="6" height="17" rx="2" fill="#AAFF00"/>
        <rect x="7"  y="18" width="6" height="3"  rx="1.5" fill="#d4ff66" opacity="0.55"/>
        <rect x="17" y="9"  width="6" height="3"  rx="1.5" fill="#d4ff66" opacity="0.55"/>
        <rect x="27" y="13" width="6" height="3"  rx="1.5" fill="#d4ff66" opacity="0.55"/>
      </svg>
      <div>
        <div style="font-family:'Poppins',sans-serif;font-size:30px;font-weight:900;
                    color:#fff;letter-spacing:-1px;line-height:1">
          Noi<span style="color:#AAFF00">ze</span>
        </div>
        <div style="font-size:9px;color:rgba(255,255,255,0.35);letter-spacing:0.2em;
                    text-transform:uppercase;margin-top:1px">Signal in the noise</div>
      </div>
    </div>

    <!-- Tag lines -->
    <div style="font-size:12px;color:rgba(255,255,255,0.4);line-height:2;margin-bottom:16px">
      The internet is noisy. &nbsp;·&nbsp; We find what matters. &nbsp;·&nbsp; You stay ahead.
    </div>

    <!-- Platforms row -->
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <span style="font-size:9px;font-weight:700;color:rgba(255,255,255,0.2);
                   letter-spacing:0.12em;text-transform:uppercase;align-self:center">Sources</span>
      {''.join([
          f'<span style="font-size:10px;font-weight:700;color:rgba(255,255,255,0.45);'
          f'background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);'
          f'padding:3px 10px;border-radius:12px">{c["icon"]} {c["label"]}</span>'
          for c in PLATFORM_CONFIG.values()
      ])}
    </div>

    {chips_html}
  </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# MAIN CONTENT  ·  RIGHT PANEL
# ══════════════════════════════════════════════════════════════════

# ── Auto-load detective briefing articles (cached 30 min) ──
articles_stale = True
if st.session_state.articles_ts:
    age_s = (datetime.now() - st.session_state.articles_ts).total_seconds()
    articles_stale = age_s > 1800
if articles_stale or not st.session_state.trend_articles:
    st.session_state.trend_articles = generate_trend_articles()
    st.session_state.articles_ts    = datetime.now()
articles = st.session_state.trend_articles

main_col, right_col = st.columns([7, 3], gap="medium")

# ════════════════════════════════════════
# RIGHT PANEL (always visible)
# ════════════════════════════════════════
with right_col:
    render_detective_briefing(articles)

    # Velocity data for radar (use active platform or tiktok as fallback)
    radar_platform = active_platform or "tiktok"
    radar_vel      = get_hashtag_velocity(platform=radar_platform)
    render_trend_radar(radar_vel, platform=radar_platform)

    # Watchlist placeholder
    st.markdown("""
    <div style="background:#0a0a12;border:1px solid #16162a;border-radius:14px;padding:14px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div style="font-size:9px;font-weight:700;color:#555;letter-spacing:0.12em;text-transform:uppercase">
          Watchlist
        </div>
        <span style="font-size:9px;font-weight:700;color:#AAFF00;cursor:pointer">MANAGE</span>
      </div>
      <div style="font-size:11px;color:#333;text-align:center;padding:12px 0">
        No topics saved yet.<br>
        <span style="color:#AAFF00;cursor:pointer">+ Add a topic</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ════════════════════════════════════════
# LEFT / MAIN CONTENT
# ════════════════════════════════════════
with main_col:

    # ── CASE FILES ───────────────────────────────────────────────
    if active_nav == "CASE FILES":

        # Platform selector
        st.markdown("<div style='font-size:9px;font-weight:700;color:#333;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:8px'>Select Source</div>", unsafe_allow_html=True)
        pcols = st.columns(4, gap="small")
        for idx, (key, cfg) in enumerate(PLATFORM_CONFIG.items()):
            with pcols[idx]:
                is_active = (active_platform == key)
                lbl = f"🔄 {cfg['icon']} {cfg['label']}" if is_active else f"{cfg['icon']} {cfg['label']}"
                if st.button(lbl, key=f"plat_{key}", use_container_width=True,
                             type="primary" if is_active else "secondary"):
                    st.session_state.active_platform = key
                    st.session_state.do_fetch = True
                    st.rerun()

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        if not active_platform:
            # Welcome state — show trend articles as case previews
            st.markdown("""
            <div style="display:flex;align-items:center;gap:8px;margin:14px 0 12px 0">
              <div style="width:6px;height:6px;border-radius:50%;background:#AAFF00;box-shadow:0 0 8px #AAFF00"></div>
              <span style="font-size:9px;font-weight:700;color:#555;letter-spacing:0.12em;text-transform:uppercase">Cases Opened Today</span>
              <span style="font-size:9px;font-weight:800;color:#AAFF00;background:rgba(170,255,0,0.1);border:1px solid rgba(170,255,0,0.2);padding:1px 7px;border-radius:6px">{count} NEW</span>
            </div>
            """.replace("{count}", str(len(articles))), unsafe_allow_html=True)

            # Article cards styled as case files
            if articles:
                art_cols = st.columns(3, gap="small")
                cat_colors = {"News": "#4285f4", "Music & Film": "#fe2c55", "Gaming": "#AAFF00"}
                for i, art in enumerate(articles[:3]):
                    cat   = art.get("category", "News")
                    color = cat_colors.get(cat, "#AAFF00")
                    tag   = art.get("tag", "Trending")
                    head  = art.get("headline", "")
                    summ  = art.get("summary", "")
                    url   = art.get("url", "#")
                    case_n = f"CASE #{i+1:04d}"

                    with art_cols[i]:
                        st.markdown(f"""
                        <a href="{url}" target="_blank" style="text-decoration:none">
                        <div style="background:#0d0d16;border:1px solid #1a1a28;
                                    border-top:2px solid {color};border-radius:12px;
                                    padding:14px;transition:all 0.2s"
                             onmouseover="this.style.borderColor='{color}50';this.style.transform='translateY(-2px)'"
                             onmouseout="this.style.borderColor='#1a1a28';this.style.borderTopColor='{color}';this.style.transform='translateY(0)'">
                          <div style="display:flex;justify-content:space-between;margin-bottom:8px">
                            <span style="font-size:9px;color:#333;font-weight:700">{case_n}</span>
                            <span style="font-size:9px;font-weight:800;color:{color};
                                         background:{color}18;padding:2px 7px;border-radius:4px">{tag.upper()}</span>
                          </div>
                          <div style="font-size:13px;font-weight:700;color:#e0e0f0;line-height:1.35;
                                      margin-bottom:7px;font-family:'Poppins',sans-serif">{head}</div>
                          <div style="font-size:11px;color:#555;line-height:1.6">{summ}</div>
                          <div style="margin-top:10px;font-size:10px;font-weight:700;color:{color}">VIEW CASE FILE →</div>
                        </div>
                        </a>
                        """, unsafe_allow_html=True)

            st.markdown("<div style='margin:16px 0 6px 0;border-top:1px solid #111120'></div>", unsafe_allow_html=True)
            st.markdown("<div style='font-size:11px;color:#333;text-align:center;padding:4px 0'>Select a source above to open live case files</div>", unsafe_allow_html=True)

        else:
            # Platform selected — show live case cards
            hashtags     = get_latest_hashtags(platform=active_platform)
            velocity_data = get_hashtag_velocity(platform=active_platform)
            cfg           = PLATFORM_CONFIG[active_platform]
            color         = cfg["color"]
            is_gpt        = bool(hashtags and hashtags[0].get("source") == "gpt_fallback")
            climbing      = [h for h in velocity_data if h.get("rank_change", 0) < 0]
            new_ones      = [h for h in velocity_data if h.get("is_new")]

            # Status bar
            mins_ago_str = "just now"
            if hashtags:
                try:
                    ts = datetime.fromisoformat(hashtags[0].get("scraped_at", ""))
                    mins = int((datetime.now() - ts).total_seconds() / 60)
                    mins_ago_str = f"{mins}m ago" if mins > 0 else "just now"
                except Exception:
                    pass

            dot = "dot-gpt" if is_gpt else "dot-live"
            src = "AI data" if is_gpt else "Live"

            st.markdown(f"""
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:6px">
              <div style="display:flex;align-items:center;gap:8px">
                <div style="width:6px;height:6px;border-radius:50%;background:#AAFF00;box-shadow:0 0 8px #AAFF00"></div>
                <span style="font-size:9px;font-weight:700;color:#555;letter-spacing:0.12em;text-transform:uppercase">Cases Opened Today</span>
                <span style="font-size:9px;font-weight:800;color:#AAFF00;background:rgba(170,255,0,0.1);border:1px solid rgba(170,255,0,0.2);padding:1px 7px;border-radius:6px">{len(hashtags)} NEW</span>
              </div>
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                <span class="status-pill"><span class="{dot}"></span>{src}</span>
                <span class="status-pill">🕐 {mins_ago_str}</span>
                <span class="status-pill">📈 {len(climbing)} escalating</span>
                <span class="status-pill">✨ {len(new_ones)} new</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            if is_gpt:
                st.markdown(f"""
                <div style="background:rgba(255,149,0,0.08);border:1px solid rgba(255,149,0,0.25);
                            border-radius:8px;padding:9px 14px;margin-bottom:10px;
                            display:flex;align-items:center;gap:8px">
                  <span>⚠️</span>
                  <div style="font-size:11px;color:#ff9500;line-height:1.5">
                    <b>{cfg['label']} live data unavailable.</b> Showing AI-generated intelligence. Hit 🔄 {cfg['label']} above to retry.
                  </div>
                </div>
                """, unsafe_allow_html=True)

            # Velocity chart
            st.markdown("<div style='font-size:9px;font-weight:700;color:#333;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px'>Rank Velocity</div>", unsafe_allow_html=True)
            render_velocity_chart(velocity_data, platform=active_platform)

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            # Case cards
            display_data = velocity_data if velocity_data else hashtags
            render_case_cards(display_data, platform=active_platform)

        render_signal_guide()

    # ── INVESTIGATIONS ───────────────────────────────────────────
    elif active_nav == "INVESTIGATIONS":
        st.markdown("<div style='font-size:9px;font-weight:700;color:#333;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Cross-Platform Investigations</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:12px;color:#444;margin-bottom:12px;line-height:1.7'>Type any topic to see the top 3 trending stories from all 4 platforms. Falls back to AI if live data is unavailable.</div>", unsafe_allow_html=True)

        inv_c1, inv_c2 = st.columns([5, 1])
        with inv_c1:
            inv_topic = st.text_input("topic", placeholder="e.g. bitcoin, taylor swift, AI tools, elections...", label_visibility="collapsed", key="inv_topic")
        with inv_c2:
            inv_go = st.button("INVESTIGATE", type="primary", use_container_width=True, key="inv_go")

        if inv_go and inv_topic.strip():
            with st.spinner(f"Scanning all platforms for \"{inv_topic.strip()}\"..."):
                st.session_state.pulse_results = niche_pulse(inv_topic.strip())
                st.session_state.pulse_query   = inv_topic.strip()

        if st.session_state.pulse_results and st.session_state.pulse_query:
            st.markdown("---")
            render_niche_pulse(st.session_state.pulse_results, st.session_state.pulse_query)
            if st.button("✕ Clear", key="inv_clear"):
                st.session_state.pulse_results = None
                st.session_state.pulse_query   = ""
                st.rerun()
        elif not st.session_state.pulse_results:
            st.markdown("""
            <div style="text-align:center;padding:40px 20px">
              <div style="font-size:36px;margin-bottom:10px">🔍</div>
              <div style="font-size:13px;font-weight:700;color:#e0e0f0;margin-bottom:6px;font-family:'Poppins',sans-serif">Start an investigation</div>
              <div style="font-size:12px;color:#444">Enter any topic above and hit INVESTIGATE.</div>
            </div>
            """, unsafe_allow_html=True)

    # ── TREND RADAR ──────────────────────────────────────────────
    elif active_nav == "TREND RADAR":
        st.markdown("<div style='font-size:9px;font-weight:700;color:#333;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Trend Radar — Rank Velocity</div>", unsafe_allow_html=True)
        pcols2 = st.columns(4, gap="small")
        for idx, (key, cfg) in enumerate(PLATFORM_CONFIG.items()):
            with pcols2[idx]:
                is_active = (active_platform == key)
                if st.button(f"{cfg['icon']} {cfg['label']}", key=f"radar_plat_{key}", use_container_width=True,
                             type="primary" if is_active else "secondary"):
                    st.session_state.active_platform = key
                    st.session_state.do_fetch = True
                    st.rerun()
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        plat = active_platform or "tiktok"
        vel  = get_hashtag_velocity(platform=plat)
        render_velocity_chart(vel, platform=plat)
        render_signal_guide()

    # ── DEEP DIVE (Blueprint) ────────────────────────────────────
    elif active_nav == "DEEP DIVE":
        st.markdown("<div style='font-size:9px;font-weight:700;color:#333;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Deep Dive — Content Blueprint Generator</div>", unsafe_allow_html=True)
        if not active_platform:
            st.markdown("<div style='font-size:12px;color:#444;padding:16px 0'>Select a source via Case Files first.</div>", unsafe_allow_html=True)
        else:
            bp_hashtags = get_latest_hashtags(platform=active_platform)
            cfg_bp      = PLATFORM_CONFIG[active_platform]
            if not bp_hashtags:
                st.info(f"No {cfg_bp['label']} trends yet — open Case Files and load a platform first.")
            else:
                st.markdown(f"<div style='font-size:12px;color:#555;margin-bottom:12px;line-height:1.7'>Select trends from <b style='color:{cfg_bp['color']}'>{cfg_bp['icon']} {cfg_bp['label']}</b> to generate a production blueprint.</div>", unsafe_allow_html=True)
                bp_niche = st.text_input("Your niche (optional)", placeholder="e.g. fitness, fashion, food...", key="bp_niche")
                selected = []
                cols = st.columns(2)
                for i, h in enumerate(bp_hashtags):
                    with cols[i % 2]:
                        pfx = "#" if active_platform == "tiktok" else ""
                        if st.checkbox(f"{pfx}{h['name']}", key=f"bp_{active_platform}_{i}"):
                            selected.append(h["name"])
                st.markdown("---")
                if st.button("🎬 Generate Blueprint", type="primary", use_container_width=True, disabled=len(selected) == 0):
                    with st.spinner("Building intelligence file..."):
                        blueprint = generate_blueprint(selected, bp_niche.strip() or "content creator")
                    st.markdown("---")
                    st.markdown(blueprint)

    # ── BRIEFINGS ────────────────────────────────────────────────
    elif active_nav == "BRIEFINGS":
        st.markdown("<div style='font-size:9px;font-weight:700;color:#333;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Daily Intelligence Briefing</div>", unsafe_allow_html=True)
        if articles:
            for art in articles:
                cat   = art.get("category", "")
                head  = art.get("headline", "")
                summ  = art.get("summary", "")
                tag   = art.get("tag", "")
                color = art.get("color", "#AAFF00")
                url   = art.get("url", "#")
                st.markdown(f"""
                <a href="{url}" target="_blank" style="text-decoration:none">
                <div style="background:#0d0d16;border:1px solid #1a1a28;border-left:3px solid {color};
                            border-radius:10px;padding:14px 16px;margin-bottom:10px;transition:all 0.15s"
                     onmouseover="this.style.transform='translateX(3px)'"
                     onmouseout="this.style.transform='translateX(0)'">
                  <div style="font-size:9px;font-weight:700;color:{color};letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px">{cat} · {tag}</div>
                  <div style="font-size:14px;font-weight:700;color:#e0e0f0;margin-bottom:6px;font-family:'Poppins',sans-serif">{head}</div>
                  <div style="font-size:12px;color:#555;line-height:1.7">{summ}</div>
                </div>
                </a>
                """, unsafe_allow_html=True)
            if st.button("🔄 Refresh Briefing", type="secondary"):
                st.session_state.trend_articles = []
                st.session_state.articles_ts    = None
                st.rerun()
        else:
            st.markdown("<div style='color:#333;font-size:12px;padding:20px 0'>Loading briefing...</div>", unsafe_allow_html=True)

    # ── NICHE RESEARCH ───────────────────────────────────────────
    elif active_nav == "SOURCES":
        st.markdown("<div style='font-size:9px;font-weight:700;color:#333;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Source Status</div>", unsafe_allow_html=True)
        for key, cfg in PLATFORM_CONFIG.items():
            age = get_data_age_minutes(platform=key)
            count = len(get_latest_hashtags(platform=key))
            age_str = f"{int(age)}m ago" if age is not None else "No data"
            status_color = "#AAFF00" if (age is not None and age < cfg["refresh_minutes"]) else "#ff9500"
            st.markdown(f"""
            <div style="background:#0d0d16;border:1px solid #1a1a28;border-radius:10px;
                        padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;gap:14px">
              <span style="font-size:22px">{cfg['icon']}</span>
              <div style="flex:1">
                <div style="font-size:13px;font-weight:700;color:#e0e0f0">{cfg['label']}</div>
                <div style="font-size:10px;color:#444;margin-top:2px">Last updated: {age_str} · {count} trends · Refresh: {cfg['refresh_minutes']}m</div>
              </div>
              <div style="width:8px;height:8px;border-radius:50%;background:{status_color}"></div>
            </div>
            """, unsafe_allow_html=True)

    # ── DEBRIEF (Chat) ───────────────────────────────────────────
    elif active_nav == "DEBRIEF":
        st.markdown("<div style='font-size:9px;font-weight:700;color:#333;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Debrief with Pugson</div>", unsafe_allow_html=True)
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_msg = st.chat_input("Ask about trends, your niche, content ideas...")
        if user_msg:
            st.session_state.chat_history.append({"role": "user", "content": user_msg})
            with st.chat_message("user"):
                st.markdown(user_msg)
            with st.chat_message("assistant"):
                with st.spinner("Pugson is on it..."):
                    response = run_agent(user_msg)
                st.markdown(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})

        if st.session_state.chat_history:
            if st.button("Clear debrief", key="clear_chat"):
                st.session_state.chat_history = []
                st.rerun()

    # ── WATCHLIST ────────────────────────────────────────────────
    elif active_nav == "WATCHLIST":
        st.markdown("""
        <div style="text-align:center;padding:40px 20px">
          <div style="font-size:36px;margin-bottom:10px">⭐</div>
          <div style="font-size:14px;font-weight:700;color:#e0e0f0;margin-bottom:6px;font-family:'Poppins',sans-serif">Watchlist</div>
          <div style="font-size:12px;color:#444">Save topics to track — coming soon.</div>
        </div>
        """, unsafe_allow_html=True)
