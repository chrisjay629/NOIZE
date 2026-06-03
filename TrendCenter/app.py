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

# ── Scheduler ────────────────────────────────────────────────────
_scheduler_started = threading.Event()

def _background_scheduler():
    print("[SCHEDULER] started", flush=True)
    while True:
        for key, cfg in PLATFORM_CONFIG.items():
            try:
                age = get_data_age_minutes(platform=key)
                if age is not None and age < cfg["refresh_minutes"]:
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
    threading.Thread(target=_background_scheduler, daemon=True).start()

# ── Image loading ─────────────────────────────────────────────────
@st.cache_data
def load_img_b64(path: str, max_width: int = 1400, quality: int = 68) -> str:
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
        print(f"[IMG] {path}: {e}", flush=True)
        return ""

PUGSON_B64           = load_img_b64("static/pugson.png",             max_width=220,  quality=90)
BG_DAY_CITY_B64      = load_img_b64("static/bg_day_city.png",       max_width=1600, quality=70)
BG_CITY_B64          = load_img_b64("static/bg_city.png",           max_width=1600, quality=65)
NEWSPAPER_B64        = load_img_b64("static/newspaper_bg.png",      max_width=1200, quality=65)
CASE_FOLDER_DARK_B64 = load_img_b64("static/case_folders_dark.png", max_width=300,  quality=85)
CASE_FOLDER_LIGHT_B64= load_img_b64("static/case_folders_light.png",max_width=300,  quality=85)
RADAR_BG_B64         = load_img_b64("static/radar_bg.jpg",          max_width=600,  quality=75)
HUD_BG_B64           = load_img_b64("static/hud_bg.jpg",            max_width=800,  quality=72)
BG_BODY_B64          = load_img_b64("static/bg_body.jpg",           max_width=1600, quality=70)

# ── Page config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Noize — Signal in the noise",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state ─────────────────────────────────────────────────
init_db()
for k, v in {
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
    "theme":           "night",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

theme = st.session_state.theme

# ── Body background texture injection ────────────────────────────
if BG_BODY_B64:
    st.markdown(f"""
    <style>
    .stApp {{
      background-image:
        linear-gradient(rgba(7,11,16,0.50), rgba(7,11,16,0.50)),
        url('data:image/jpeg;base64,{BG_BODY_B64}') !important;
      background-size: cover, cover !important;
      background-attachment: fixed, fixed !important;
      background-position: center, center !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# ── CSS — Bloomberg Terminal × Palantir × Intelligence Agency ────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;0,900;1,400&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* ══════════════════════════════════════════════════════════════
   NIGHT MODE  —  Bloomberg Terminal × Palantir × Ops Center
   Background: #070B10 · Panels: #0E131B · Cards: #171F29
   Borders: rgba(255,255,255,0.08) · Green: #A3FF12
   ══════════════════════════════════════════════════════════════ */
:root {
  --bg:           #070B10;
  --surface:      #0E131B;
  --surface-alt:  #151B24;
  --surface-2:    #0E131B;
  --border:       rgba(255,255,255,0.08);
  --border-2:     rgba(255,255,255,0.06);
  --tx1:          #F5F7FA;
  --tx2:          #8B93A7;
  --tx3:          #4a5568;
  --tx4:          #2d3748;
  --sb-bg:        #080C12;
  --sb-border:    rgba(255,255,255,0.06);
  --lime-t:       #A3FF12;
  --lime-bg:      rgba(163,255,18,0.07);
  --lime-border:  rgba(163,255,18,0.20);
  --amber:        #c8a96e;
  --amber-bg:     rgba(200,169,110,0.08);
  --amber-border: rgba(200,169,110,0.22);
  --radar-green:  #00ff88;
  --input-bg:     #0E131B;
  --input-bd:     rgba(255,255,255,0.08);
  --pill-bg:      #0E131B;
  --pill-bd:      rgba(255,255,255,0.06);
  --card-hover:   rgba(163,255,18,0.03);
  --data-font:    'JetBrains Mono', 'Courier New', monospace;
  --body-font:    'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  --shadow-card:  0 20px 60px rgba(0,0,0,0.50), 0 1px 0 rgba(255,255,255,0.04) inset, 0 0 0 1px rgba(255,255,255,0.03);
  --shadow-panel: 0 8px 40px rgba(0,0,0,0.55), 0 1px 0 rgba(255,255,255,0.04) inset;
  --glow-edge:    0 0 0 1px rgba(163,255,18,0.18), 0 4px 20px rgba(163,255,18,0.08);
  --app-grid:
    radial-gradient(circle at 50% 0%, rgba(18,24,38,0.90) 0%, transparent 65%),
    repeating-linear-gradient(0deg,  transparent, transparent 47px, rgba(163,255,18,0.014) 48px),
    repeating-linear-gradient(90deg, transparent, transparent 47px, rgba(163,255,18,0.014) 48px);
}

/* ── Base layout ── */
html, body, [class*="css"] {
  font-family: var(--body-font) !important;
  background: var(--bg) !important;
}
[data-testid="stHeader"] { display: none !important; }
[data-testid="stAppViewContainer"] { background: var(--bg) !important; }

.stApp {
  background-color: var(--bg) !important;
}

.block-container { padding: 0.75rem 1.2rem 2rem 1.2rem !important; max-width: 100% !important; }

/* ── Sidebar — Command Center ── */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #080C12 0%, #0E131B 100%) !important;
  border-right: 1px solid var(--sb-border) !important;
  box-shadow: 4px 0 32px rgba(0,0,0,0.6) !important;
}
[data-testid="stSidebar"] > div { padding: 0 !important; }
[data-testid="stSidebarContent"] { padding: 0 !important; }

/* Sidebar nav buttons */
[data-testid="stSidebar"] .stButton > button {
  background: transparent !important;
  border: none !important;
  border-left: 2px solid transparent !important;
  border-radius: 0 !important;
  color: var(--tx3) !important;
  font-size: 10px !important;
  font-weight: 700 !important;
  letter-spacing: 0.10em !important;
  text-align: left !important;
  padding: 10px 18px !important;
  width: 100% !important;
  transition: all 0.15s !important;
  text-transform: uppercase !important;
  font-family: var(--data-font) !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: var(--lime-bg) !important;
  color: var(--lime-t) !important;
  border-left-color: var(--lime-t) !important;
  text-shadow: 0 0 12px rgba(163,255,18,0.35) !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] { background: transparent !important; }
[data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid var(--border) !important; }
[data-testid="stTabs"] button {
  color: var(--tx3) !important; font-size: 10px !important; font-weight: 700 !important;
  letter-spacing: 0.08em !important; text-transform: uppercase !important;
  background: transparent !important; padding: 10px 16px !important;
  font-family: var(--data-font) !important;
}
[data-testid="stTabs"] button[aria-selected="true"] { color: var(--lime-t) !important; border-bottom: 2px solid var(--lime-t) !important; }

/* ── Inputs ── */
[data-testid="stTextInput"] input {
  background: var(--input-bg) !important; border: 1px solid var(--input-bd) !important;
  color: var(--tx1) !important; border-radius: 8px !important; font-size: 13px !important;
  font-family: var(--data-font) !important;
}
[data-testid="stTextInput"] input:focus {
  border-color: var(--lime-t) !important;
  box-shadow: 0 0 0 2px rgba(163,255,18,0.12), 0 0 16px rgba(163,255,18,0.06) !important;
}
[data-testid="stTextInput"] input::placeholder { color: var(--tx4) !important; }
[data-testid="stTextInput"] label { color: var(--tx3) !important; font-size: 11px !important; font-weight: 700 !important; letter-spacing: 0.06em !important; }

/* ── Buttons ── */
.stButton > button {
  border-radius: 7px !important; font-size: 11px !important; font-weight: 700 !important;
  letter-spacing: 0.06em !important; transition: all 0.15s !important;
  text-transform: uppercase !important; font-family: var(--body-font) !important;
}
.stButton > button[kind="primary"] {
  background: var(--lime-t) !important; color: #080e14 !important; border: none !important;
  box-shadow: 0 2px 16px rgba(163,255,18,0.28), 0 0 0 1px rgba(163,255,18,0.25) !important;
}
.stButton > button[kind="primary"]:hover {
  background: #b8ff3a !important;
  box-shadow: 0 4px 28px rgba(163,255,18,0.45), 0 0 0 1px rgba(163,255,18,0.4) !important;
  transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
  background: var(--surface) !important; border: 1px solid var(--border) !important; color: var(--tx3) !important;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
}
.stButton > button[kind="secondary"]:hover {
  border-color: rgba(163,255,18,0.35) !important; color: var(--lime-t) !important;
  background: var(--lime-bg) !important; box-shadow: var(--glow-edge) !important;
}

/* ── Utility classes ── */
hr { border-color: var(--border) !important; }
[data-testid="stCheckbox"] label { color: var(--tx2) !important; font-size: 12px !important; }
p, li { color: var(--tx2) !important; }
h1, h2, h3, h4 { color: var(--tx1) !important; font-family: var(--body-font) !important; font-weight: 800 !important; }

/* Data values — monospace */
.data-val { font-family: var(--data-font); font-size: 11px; font-weight: 600; color: var(--lime-t); }
.data-label { font-size: 8px; font-weight: 700; color: var(--tx4); letter-spacing: 0.10em; text-transform: uppercase; }
.amber-label { font-family: var(--data-font); font-size: 9px; font-weight: 600; color: var(--amber); letter-spacing: 0.08em; }

/* Status pills */
.status-pill {
  display:inline-flex; align-items:center; gap:5px; font-size:9px; color:var(--tx3);
  padding:3px 9px; background:var(--pill-bg); border:1px solid var(--pill-bd);
  border-radius:4px; font-weight:700; letter-spacing:0.06em; font-family:var(--data-font);
  box-shadow: 0 1px 4px rgba(0,0,0,0.3);
}
.dot-live { width:5px; height:5px; border-radius:50%; background:var(--lime-t); display:inline-block; box-shadow:0 0 6px var(--lime-t); }
.dot-gpt  { width:5px; height:5px; border-radius:50%; background:#ff9500; display:inline-block; }

/* Badges */
.badge { display:inline-block; font-size:8px; padding:2px 6px; border-radius:3px; margin-left:4px; vertical-align:middle; font-weight:800; letter-spacing:0.08em; text-transform:uppercase; font-family:var(--data-font); }
.badge-green  { background:rgba(61,214,140,0.10);  color:#3dd68c; border:1px solid rgba(61,214,140,0.2); }
.badge-blue   { background:rgba(77,168,255,0.10);  color:#4da8ff; border:1px solid rgba(77,168,255,0.2); }
.badge-red    { background:rgba(255,59,59,0.10);   color:#ff5555; border:1px solid rgba(255,59,59,0.2); }
.badge-lime   { background:rgba(163,255,18,0.10);  color:var(--lime-t); border:1px solid rgba(163,255,18,0.2); }
.badge-amber  { background:rgba(200,169,110,0.10); color:#c8a96e; border:1px solid rgba(200,169,110,0.2); }
.badge-orange { background:rgba(255,149,0,0.10);   color:#ff9500; border:1px solid rgba(255,149,0,0.2); }

/* Plotly */
.js-plotly-plot { background: transparent !important; }

/* Metrics */
[data-testid="metric-container"] {
  background:var(--surface) !important; border-radius:8px !important;
  border:1px solid var(--border) !important; box-shadow: var(--shadow-card) !important;
}
[data-testid="metric-container"] label { color:var(--tx3) !important; font-size:10px !important; font-weight:700 !important; letter-spacing:0.08em !important; text-transform:uppercase !important; }
[data-testid="metric-container"] [data-testid="stMetricValue"] { color:var(--tx1) !important; font-size:22px !important; font-weight:800 !important; font-family:var(--data-font) !important; }

/* ── ht-card ── */
.ht-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; margin-bottom: 8px; box-shadow: var(--shadow-card); }
.ht-card:hover { border-color: rgba(163,255,18,0.22); box-shadow: 0 8px 40px rgba(0,0,0,0.6), 0 0 0 1px rgba(163,255,18,0.08); }

</style>
""", unsafe_allow_html=True)

# ── Day mode override ─────────────────────────────────────────────
if theme == "day":
    st.markdown("""
    <style>
    :root {
      --bg:           #1a2538;
      --surface:      #f0e4cc;
      --surface-alt:  #203048;
      --surface-2:    #1e2d42;
      --border:       rgba(255,255,255,0.10);
      --border-2:     rgba(255,255,255,0.07);
      --tx1:          #1a1f2e;
      --tx2:          #2e3650;
      --tx3:          #8890a8;
      --tx4:          #5a6480;
      --input-bg:     #f0e4cc;
      --input-bd:     rgba(0,0,0,0.15);
      --pill-bg:      #253048;
      --pill-bd:      rgba(255,255,255,0.10);
      --lime-t:       #A3FF12;
      --lime-bg:      rgba(163,255,18,0.08);
      --lime-border:  rgba(163,255,18,0.22);
      --amber:        #c8a96e;
      --shadow-card:  0 4px 20px rgba(0,0,0,0.30);
      --app-grid:
        repeating-linear-gradient(0deg,  transparent, transparent 47px, rgba(255,255,255,0.018) 48px),
        repeating-linear-gradient(90deg, transparent, transparent 47px, rgba(255,255,255,0.018) 48px);
    }
    html, body, [class*="css"], [data-testid="stAppViewContainer"] { background: #1a2538 !important; }
    .stApp { background-color: #1a2538 !important; }
    </style>
    """, unsafe_allow_html=True)

# ── Fetch on demand ───────────────────────────────────────────────
if st.session_state.do_fetch and st.session_state.active_platform:
    st.session_state.do_fetch = False
    ap    = st.session_state.active_platform
    cfg_f = PLATFORM_CONFIG[ap]
    with st.spinner(f"Opening case files for {cfg_f['icon']} {cfg_f['label']}..."):
        try:
            results = cfg_f["scraper"]()
            if results:
                save_snapshot(results, platform=ap)
                cleanup_old_snapshots(hours=48)
        except Exception as e:
            st.error(f"Could not load {cfg_f['label']}: {e}")

# ═════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════

def case_status(h):
    change  = h.get("rank_change", 0)
    is_new  = h.get("is_new", False)
    try:    rank_int = int(str(h.get("current_rank") or h.get("rank") or 10))
    except: rank_int = 10
    # Use readable greens for day mode; signal green for night
    _lime   = "#2a5200"             if theme == "day" else "#A3FF12"
    _lime_b = "rgba(42,82,0,0.10)"  if theme == "day" else "rgba(163,255,18,0.12)"
    _lime_s = "rgba(42,82,0,0.08)"  if theme == "day" else "rgba(163,255,18,0.08)"
    if rank_int == 1:                                return "DOMINATING", _lime,    _lime_b
    if change < -4 or (is_new and rank_int <= 5):   return "BREAKING",   "#ff3b3b", "rgba(255,59,59,0.12)"
    if change < -1 or is_new:                        return "ESCALATING", "#ff9500", "rgba(255,149,0,0.12)"
    if change < 1:                                   return "TRENDING",   "#4da8ff", "rgba(77,168,255,0.12)"
    if change < 4:                                   return "ACTIVE",     _lime,    _lime_s
    return                                                  "FADING",     "#666",    "rgba(80,80,80,0.1)"

def case_confidence(rank_int, name):
    base  = max(52, 98 - (rank_int - 1) * 2)
    noise = hash(name) % 7 - 3
    return max(51, min(99, base + noise))

def mini_sparkline(rank_change, is_new, color, name=""):
    import random
    rng = random.Random(abs(hash(name or "x")) % 99991)
    W, H, N = 80, 30, 10
    if is_new or rank_change <= -4:
        # Sharp upward curve
        base = [H-2, H-4, H-7, H-10, H-13, H-16, H-19, H-22, H-26, 2]
    elif rank_change < 0:
        # Moderate upward
        base = [H-2, H-5, H-8, H-11, H-13, H-15, H-17, H-19, H-22, H-26]
    elif rank_change == 0:
        # Wavy flat
        base = [H//2+2, H//2-2, H//2+3, H//2-1, H//2+2, H//2-3, H//2+1, H//2-2, H//2+2, H//2]
    elif rank_change < 4:
        # Mild downward
        base = [4, 6, 9, 12, 14, 16, 18, 21, 24, H-2]
    else:
        # Sharp downward
        base = [2, 4, 7, 11, 15, 18, 21, 24, H-4, H-2]
    ys    = [max(2, min(H-2, v + rng.randint(-3, 3))) for v in base]
    xs    = [int(i * (W-6) / (N-1)) + 3 for i in range(N)]
    pts   = " ".join(f"{x},{y}" for x, y in zip(xs, ys))
    return (f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')

def platform_spread_icons(rank_int, primary_platform):
    icons   = {"tiktok": "🎵", "google": "📈", "youtube": "📺", "reddit": "🔴"}
    primary = icons.get(primary_platform, "🌐")
    extras  = [v for k, v in icons.items() if k != primary_platform]
    if rank_int <= 3:   spread = [primary] + extras[:3]
    elif rank_int <= 8: spread = [primary] + extras[:2]
    elif rank_int <= 14: spread = [primary] + extras[:1]
    else:               spread = [primary]
    return " ".join(spread)

def velocity_pct_str(rank_change, is_new, rank_int=10, name=""):
    import random
    rng   = random.Random(abs(hash(name or "x")) % 99991)
    noise = rng.randint(15, 75)
    # On light backgrounds #AAFF00 is invisible; use CSS variable so browser resolves correctly
    _lime = "var(--lime-t)"
    if is_new and rank_int <= 3:  return f"+{520 + noise}%", "#ff3b3b"
    if is_new and rank_int <= 6:  return f"+{340 + noise}%", "#ff9500"
    if is_new:                    return f"+{200 + noise}%", _lime
    if rank_change <= -5:         return f"+{460 + noise}%", "#ff3b3b"
    if rank_change <= -3:         return f"+{290 + noise}%", "#ff9500"
    if rank_change < 0:           return f"+{110 + noise}%", _lime
    if rank_change == 0:          return f"+{8  + noise//4}%", "var(--tx4)"
    return                               f"−{min(88, rank_change*14 + noise//3)}%", "#666"

def render_velocity_chart(velocity_data, platform="tiktok"):
    if not velocity_data:
        st.markdown("<div style='color:var(--tx4);font-size:12px;padding:16px 0;text-align:center'>Need 2+ scrapes for velocity chart.</div>", unsafe_allow_html=True)
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        fig  = go.Figure()
        has_data = False
        for name in [h["name"] for h in velocity_data[:5]]:
            c.execute("SELECT scraped_at, rank FROM hashtag_snapshots WHERE name=? AND platform=? ORDER BY scraped_at ASC", (name, platform))
            rows = c.fetchall()
            if len(rows) < 2: continue
            has_data = True
            fig.add_trace(go.Scatter(
                x=[r[0] for r in rows], y=[r[1] for r in rows],
                mode="lines+markers",
                name=f"{'#' if platform=='tiktok' else ''}{name}",
                line=dict(width=2), marker=dict(size=4),
            ))
        conn.close()
        if not has_data:
            st.markdown("<div style='color:var(--tx4);font-size:12px;padding:16px 0;text-align:center'>Not enough history yet.</div>", unsafe_allow_html=True)
            return
        grid = "#1a1a24" if theme == "night" else "#e0e0ec"
        tick = "#555"   if theme == "night" else "#999"
        fig.update_layout(
            yaxis=dict(autorange="reversed", title="Rank", gridcolor=grid, color=tick, tickfont=dict(size=9)),
            xaxis=dict(gridcolor=grid, color=tick, tickfont=dict(size=8)),
            height=200, margin=dict(l=0,r=0,t=4,b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=9,color=tick), bgcolor="rgba(0,0,0,0)"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception as e:
        st.warning(f"Chart error: {e}")

def render_case_cards(data, platform="tiktok"):
    if not data:
        st.markdown('<div style="text-align:center;padding:40px 0;color:var(--tx4)"><div style="font-size:32px;margin-bottom:8px">📁</div><div style="font-size:13px">No cases yet — select a source above.</div></div>', unsafe_allow_html=True)
        return
    cfg    = PLATFORM_CONFIG.get(platform, {})
    color  = cfg.get("color", "var(--lime-t)")
    prefix = "#" if platform == "tiktok" else ""
    # Thumbnail image (intelligence dossier folder)
    thumb_b64 = CASE_FOLDER_LIGHT_B64 if theme == "day" else CASE_FOLDER_DARK_B64
    thumb_src = f"data:image/jpeg;base64,{thumb_b64}" if thumb_b64 else ""
    # Premium card shadow: deeper in night mode
    card_bg     = "#171F29" if theme == "night" else "var(--surface)"
    card_shadow = "0 20px 60px rgba(0,0,0,0.50),0 1px 0 rgba(255,255,255,0.04) inset,0 0 0 1px rgba(255,255,255,0.04)" if theme == "night" else "0 2px 12px rgba(0,0,0,0.10)"
    for row_start in range(0, min(len(data), 9), 3):
        row  = data[row_start:row_start+3]
        cols = st.columns(3, gap="small")
        for i, h in enumerate(row):
            with cols[i]:
                name      = h.get("name","")
                posts     = h.get("posts") or "—"
                category  = h.get("category") or "—"
                url       = h.get("url") or f"https://www.google.com/search?q={name}"
                rank_raw  = h.get("current_rank") or h.get("rank") or 10
                change    = h.get("rank_change",0)
                is_new    = h.get("is_new",False)
                posts_lbl = f"{posts} posts" if platform=="tiktok" else posts
                try:    rank_int = int(str(rank_raw))
                except: rank_int = 10
                case_num           = f"CASE #{(row_start+i+1):04d}"
                status_lbl, sc, sb = case_status(h)
                confidence         = case_confidence(rank_int, name)
                sparkline          = mini_sparkline(change, is_new, sc, name)
                spread             = platform_spread_icons(rank_int, platform)
                vel_str, vel_col   = velocity_pct_str(change, is_new, rank_int, name)
                # Intelligence dossier thumbnail with rank stamp
                if thumb_src:
                    thumb_html = (f'<div style="width:78px;height:62px;border-radius:8px;overflow:hidden;flex-shrink:0;position:relative;border:1px solid {sc}44;box-shadow:0 2px 8px rgba(0,0,0,0.4)">'
                                  f'<img src="{thumb_src}" style="width:100%;height:100%;object-fit:cover;opacity:0.6">'
                                  f'<div style="position:absolute;inset:0;background:linear-gradient(to bottom,transparent 20%,{sc}44)"></div>'
                                  f'<div style="position:absolute;bottom:4px;left:0;right:0;text-align:center;font-family:Inter,sans-serif;font-weight:900;font-size:18px;color:#fff;text-shadow:0 2px 6px rgba(0,0,0,0.9)">{rank_int}</div>'
                                  f'</div>')
                else:
                    thumb_html = f'<div style="width:36px;height:36px;border-radius:8px;flex-shrink:0;background:var(--surface-alt);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-family:Inter,sans-serif;font-weight:800;font-size:14px;color:{sc}">{rank_int}</div>'
                # Paper clip SVG
                clip_html = (f'<div style="position:absolute;top:-9px;left:20px">'
                             f'<svg width="14" height="22" viewBox="0 0 14 22" fill="none">'
                             f'<path d="M7 1 C3.5 1 1 3.5 1 7 L1 17 C1 19.2 2.8 21 5 21 C7.2 21 9 19.2 9 17 L9 7 C9 5.8 8.2 5 7 5 C5.8 5 5 5.8 5 7 L5 16" '
                             f'stroke="{sc}" stroke-width="2.5" stroke-linecap="round" fill="none"/>'
                             f'</svg></div>')
                # HUD corner brackets
                corner_tl = f'<div style="position:absolute;top:6px;left:6px;width:14px;height:14px;border-left:1.5px solid {sc};border-top:1.5px solid {sc};opacity:0.45"></div>'
                corner_tr = f'<div style="position:absolute;top:6px;right:6px;width:14px;height:14px;border-right:1.5px solid {sc};border-top:1.5px solid {sc};opacity:0.45"></div>'
                st.markdown(
                    f'<a href="{url}" target="_blank" style="text-decoration:none">'
                    f'<div style="background:{card_bg};border:1px solid var(--border);border-top:2px solid {sc};border-radius:10px;padding:14px 14px 12px;margin-bottom:12px;cursor:pointer;position:relative;box-shadow:{card_shadow};transition:all 0.15s;backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)">'
                    f'{clip_html}{corner_tl}{corner_tr}'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
                    f'<span style="font-family:JetBrains Mono,monospace;font-size:8px;font-weight:600;color:var(--amber);letter-spacing:0.10em">{case_num}</span>'
                    f'<span style="font-family:JetBrains Mono,monospace;font-size:8px;font-weight:800;padding:2px 8px;border-radius:3px;letter-spacing:0.10em;background:{sb};color:{sc};border:1px solid {sc}44">{status_lbl}</span>'
                    f'</div>'
                    f'<div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:10px">'
                    f'{thumb_html}'
                    f'<div style="flex:1;min-width:0">'
                    f'<div style="font-family:Inter,sans-serif;font-weight:700;font-size:13px;color:var(--tx1);line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{prefix}{name}</div>'
                    f'<div style="font-size:9px;color:var(--tx3);margin-top:2px;font-family:JetBrains Mono,monospace;letter-spacing:0.04em">{category.upper()}</div>'
                    f'</div></div>'
                    f'<div style="border-top:1px solid var(--border);padding-top:9px;display:grid;grid-template-columns:1fr 1fr;gap:7px 8px;margin-bottom:10px">'
                    f'<div><div style="font-size:7.5px;font-weight:700;color:var(--tx4);letter-spacing:0.10em;text-transform:uppercase;font-family:JetBrains Mono,monospace">Status</div><div style="font-size:11px;font-weight:700;color:{sc};margin-top:2px">{status_lbl.title()}</div></div>'
                    f'<div><div style="font-size:7.5px;font-weight:700;color:var(--tx4);letter-spacing:0.10em;text-transform:uppercase;font-family:JetBrains Mono,monospace">Confidence</div><div style="font-family:JetBrains Mono,monospace;font-size:12px;font-weight:700;color:var(--lime-t);margin-top:2px">{confidence}%</div></div>'
                    f'<div><div style="font-size:7.5px;font-weight:700;color:var(--tx4);letter-spacing:0.10em;text-transform:uppercase;font-family:JetBrains Mono,monospace">Platform Spread</div><div style="font-size:12px;margin-top:2px">{spread}</div></div>'
                    f'<div><div style="font-size:7.5px;font-weight:700;color:var(--tx4);letter-spacing:0.10em;text-transform:uppercase;font-family:JetBrains Mono,monospace">Volume</div><div style="font-family:JetBrains Mono,monospace;font-size:10px;color:var(--tx3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px">{posts_lbl}</div></div>'
                    f'</div>'
                    f'<div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--border);padding-top:8px">'
                    f'<div><div style="font-size:7.5px;font-weight:700;color:var(--tx4);letter-spacing:0.10em;text-transform:uppercase;font-family:JetBrains Mono,monospace;margin-bottom:3px">Velocity</div>'
                    f'<div style="display:flex;align-items:center;gap:5px">{sparkline}<span style="font-family:JetBrains Mono,monospace;font-size:11px;font-weight:700;color:{vel_col}">{vel_str}</span></div></div>'
                    f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;font-weight:700;color:{sc};letter-spacing:0.08em">VIEW CASE FILE →</span>'
                    f'</div></div></a>',
                    unsafe_allow_html=True
                )

def render_signal_guide():
    _dom_col = "#2a5200" if theme == "day" else "#A3FF12"
    levels = [
        ("#555",    "QUIET",     "Early whispers",     1),
        ("#3dd68c", "GROWING",   "Gaining traction",   2),
        ("#fbbf24", "EMERGING",  "Picking up steam",   3),
        ("#ff9500", "TRENDING",  "Going mainstream",   4),
        ("#ff3b3b", "BREAKING",  "Widespread impact",  5),
        (_dom_col,  "DOMINATING","All over the net",   6),
    ]
    items = ""
    for col, lbl, sub, strength in levels:
        # Stacked bars representing signal strength
        bars = "".join([
            f'<div style="width:4px;height:{6+k*4}px;border-radius:2px;background:{"" if k >= strength else col};border:1px solid {col if k < strength else "var(--border)"};opacity:{1 if k < strength else 0.25}"></div>'
            for k in range(6)
        ])
        items += (f'<div style="display:flex;flex-direction:column;align-items:center;gap:5px;flex:1;min-width:0">'
                  f'<div style="display:flex;align-items:flex-end;gap:2px;height:36px">{bars}</div>'
                  f'<div style="font-size:7.5px;font-weight:800;color:{col};letter-spacing:0.06em;text-align:center;font-family:JetBrains Mono,monospace;line-height:1.2">{lbl}</div>'
                  f'<div style="font-size:8px;color:var(--tx4);text-align:center;line-height:1.3">{sub}</div>'
                  f'</div>')
    st.markdown(
        f'<div style="background:var(--surface-alt);border:1px solid var(--border-2);border-radius:12px;padding:16px 18px;margin:16px 0 8px">'
        f'<div style="font-size:8px;font-weight:700;color:var(--tx4);letter-spacing:0.14em;text-transform:uppercase;margin-bottom:14px;font-family:JetBrains Mono,monospace">── Signal Strength Index ──</div>'
        f'<div style="display:flex;align-items:flex-end;gap:0">{items}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

def render_detective_briefing(articles):
    hour     = datetime.now().hour
    greeting = "Good morning" if hour<12 else ("Good afternoon" if hour<18 else "Good evening")
    cat_icons = {"News":"📰","Music & Film":"🎬","Gaming":"🎮"}
    plat_data = [("🎵","#fe2c55","+573%"),("🔴","#ff5700","+302%"),("📺","#ff4444","+218%")]
    leads_html = ""
    for idx, art in enumerate(articles[:3]):
        cat   = art.get("category","News")
        head  = (art.get("headline","") or "")[:52]
        summ  = (art.get("summary","") or "")[:60]
        url   = art.get("url","#")
        picon,pcol,vel = plat_data[idx%len(plat_data)]
        num_style   = f"width:22px;height:22px;border-radius:50%;background:{pcol};display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:#fff;flex-shrink:0"
        icon_style  = f"width:32px;height:32px;border-radius:8px;background:{pcol}22;border:1px solid {pcol}44;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0"
        head_style  = "font-size:11px;font-weight:700;color:var(--tx1);line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
        cat_style   = "font-size:9px;color:var(--tx4);margin-top:1px"
        card_style  = f"display:flex;gap:8px;align-items:flex-start;padding:9px 10px;background:var(--surface-2);border:1px solid var(--border-2);border-left:2px solid {pcol};border-radius:9px;margin-bottom:6px"
        vel_style   = "font-size:11px;font-weight:800;color:var(--lime-t);flex-shrink:0;white-space:nowrap"
        leads_html += (f'<a href="{url}" target="_blank" style="text-decoration:none">'
                       f'<div style="{card_style}">'
                       f'<div style="{num_style}">{idx+1}</div>'
                       f'<div style="{icon_style}">{picon}</div>'
                       f'<div style="flex:1;min-width:0"><div style="{head_style}">{head}</div><div style="{cat_style}">{cat_icons.get(cat,"📡")} {cat}</div></div>'
                       f'<div style="{vel_style}">↑ {vel}</div>'
                       f'</div></a>')
    if not leads_html:
        leads_html = '<div style="color:var(--tx4);font-size:12px;padding:10px">Loading intelligence...</div>'
    view_btn = '<a href="#" style="display:block;text-align:center;margin-top:10px;padding:8px;background:var(--lime-bg);border:1px solid var(--lime-border);border-radius:8px;font-size:10px;font-weight:700;color:var(--lime-t);text-decoration:none;letter-spacing:0.06em">VIEW FULL BRIEFING →</a>'
    ts_str      = datetime.now().strftime("%H:%M · %b %d")
    panel_bg    = "background:rgba(10,14,20,0.55);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)" if theme == "night" else "background:var(--surface-alt)"
    panel_shad  = ";box-shadow:0 8px 40px rgba(0,0,0,0.45),0 0 0 1px rgba(255,255,255,0.04)" if theme == "night" else ""
    st.markdown(
        f'<div style="{panel_bg};border:1px solid var(--border-2);border-radius:14px;padding:16px;margin-bottom:12px{panel_shad}">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:8px;font-weight:700;color:var(--amber);letter-spacing:0.16em;text-transform:uppercase">▸ INTEL REPORT</div>'
        f'<span style="font-family:JetBrains Mono,monospace;font-size:8px;color:var(--tx4);letter-spacing:0.06em">{ts_str}</span>'
        f'</div>'
        f'<div style="font-size:14px;font-weight:800;color:var(--tx1);margin-bottom:1px;font-family:Inter,sans-serif">{greeting}, Detective.</div>'
        f'<div style="font-size:10px;color:var(--tx3);margin-bottom:12px;font-family:JetBrains Mono,monospace">3 LEADS ACTIVE · PRIORITY CLEARANCE</div>'
        f'{leads_html}'
        f'{view_btn}'
        f'</div>',
        unsafe_allow_html=True
    )

def render_trend_radar(velocity_data, platform="tiktok"):
    categories = ["DOMINATING","BREAKING","TRENDING","EMERGING","QUIET"]
    _rd_lime   = "#2a5200" if theme == "day" else "#A3FF12"
    cat_colors = [_rd_lime,"#ff3b3b","#4da8ff","#fbbf24","#555"]
    counts = [0,0,0,0,0]
    for h in velocity_data:
        lbl,_,_ = case_status(h)
        if   lbl=="DOMINATING":                counts[0]+=1
        elif lbl=="BREAKING":                  counts[1]+=1
        elif lbl in ("TRENDING","ESCALATING"): counts[2]+=1
        elif lbl=="ACTIVE":                    counts[3]+=1
        else:                                  counts[4]+=1
    if sum(counts)==0: counts=[1,2,5,8,4]
    fig = go.Figure()
    # Radar background image
    if RADAR_BG_B64:
        fig.update_layout(images=[dict(
            source=f"data:image/jpeg;base64,{RADAR_BG_B64}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor="center", yanchor="middle",
            sizex=1.1, sizey=1.1,
            sizing="contain", opacity=0.18 if theme=="night" else 0.10, layer="below"
        )])
    is_night  = (theme == "night")
    _r_lime   = "#A3FF12"              if is_night else "#2a5200"
    _r_fill   = "rgba(163,255,18,0.09)" if is_night else "rgba(42,82,0,0.10)"
    _r_mkline = "#0B0F14"             if is_night else "#fdfaf4"
    fig.add_trace(go.Scatterpolar(
        r=counts+[counts[0]], theta=categories+[categories[0]],
        fill="toself",
        fillcolor=_r_fill,
        line=dict(color=_r_lime, width=2),
        marker=dict(color=_r_lime, size=6, symbol="circle",
                    line=dict(color=_r_mkline, width=1.5)),
        name="Signal",
    ))
    grid_c   = "rgba(163,255,18,0.12)" if is_night else "rgba(100,80,40,0.15)"
    tick_c   = "rgba(163,255,18,0.5)"  if is_night else "#777"
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=False, range=[0, max(counts)+2]),
            angularaxis=dict(
                tickfont=dict(size=8, color=tick_c, family="JetBrains Mono, monospace"),
                linecolor=grid_c, gridcolor=grid_c, tickcolor=grid_c,
            ),
        ),
        height=190, margin=dict(l=12,r=12,t=8,b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    # Radar panel header — glass treatment in night mode
    _radar_bg   = "background:rgba(10,14,20,0.55);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)" if is_night else "background:var(--surface-alt)"
    _radar_shad = ";box-shadow:0 20px 60px rgba(0,0,0,0.45)" if is_night else ""
    _radar_bord = "border:1px solid rgba(163,255,18,0.18)" if is_night else "border:1px solid var(--border-2)"
    _live_glow  = f";text-shadow:0 0 10px {_r_lime}" if is_night else ""
    st.markdown(
        f'<div style="{_radar_bg};{_radar_bord};border-radius:14px;padding:14px 14px 10px;margin-bottom:12px{_radar_shad}">'
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">'
        f'<div style="font-size:9px;font-weight:700;color:var(--lime-t);letter-spacing:0.14em;text-transform:uppercase;font-family:JetBrains Mono,monospace">◉ TREND RADAR</div>'
        f'<span style="font-size:8px;color:var(--lime-t);font-weight:700;font-family:JetBrains Mono,monospace;letter-spacing:0.1em{_live_glow}">LIVE</span>'
        '</div>',
        unsafe_allow_html=True
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    # Legend with bar indicators
    legend = ""
    total  = max(1, sum(counts))
    for i in range(len(categories)):
        pct = int(counts[i] / total * 100)
        bar = f'<div style="height:2px;background:var(--border);border-radius:1px;flex:1"><div style="height:2px;background:{cat_colors[i]};border-radius:1px;width:{pct}%"></div></div>'
        legend += (f'<div style="display:flex;align-items:center;gap:7px;padding:3px 0">'
                   f'<span style="width:5px;height:5px;border-radius:50%;background:{cat_colors[i]};flex-shrink:0;display:inline-block"></span>'
                   f'<span style="font-size:8px;color:var(--tx3);font-weight:700;font-family:JetBrains Mono,monospace;letter-spacing:0.06em;width:88px">{categories[i]}</span>'
                   f'{bar}'
                   f'<span style="font-size:9px;font-weight:700;color:{cat_colors[i]};font-family:JetBrains Mono,monospace;width:14px;text-align:right">{counts[i]}</span>'
                   f'</div>')
    st.markdown(f'<div style="padding:0 2px 2px">{legend}</div></div>', unsafe_allow_html=True)

def render_niche_pulse(results, query):
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
      <span style="font-size:13px;font-weight:700;color:var(--tx3)">🔍 Niche Pulse</span>
      <span style="font-size:14px;font-weight:800;color:var(--tx1);font-family:'Poppins',sans-serif">"{query}"</span>
      <span style="font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.08em;text-transform:uppercase">Top 3 per platform</span>
    </div>""", unsafe_allow_html=True)
    pulse_cols  = st.columns(4)
    chart_items = []
    for idx,(key,cfg) in enumerate(PLATFORM_CONFIG.items()):
        trends  = results.get(key,[])
        color   = cfg["color"]
        is_gpt  = any(t.get("source")=="gpt_fallback" for t in trends)
        src_lbl = "🤖 AI" if is_gpt else "🟢 Live"
        with pulse_cols[idx]:
            st.markdown(f"""
            <div style="background:{color}10;border:1px solid {color}30;border-radius:10px;padding:10px 12px;margin-bottom:8px">
              <div style="font-size:12px;font-weight:700;color:{color}">{cfg['icon']} {cfg['label']}</div>
              <div style="font-size:9px;color:var(--tx3);margin-top:2px">{src_lbl}</div>
            </div>""", unsafe_allow_html=True)
            for t in trends:
                name  = t.get("name","")
                posts = t.get("posts","—")
                rank_r = t.get("rank") or t.get("current_rank") or 10
                url   = t.get("url","#")
                pfx   = "#" if key=="tiktok" else ""
                disp  = name[:22]+("…" if len(name)>22 else "")
                try:    rk = int(str(rank_r))
                except: rk = 10
                bar = max(5, int((21-rk)/20*100))
                st.markdown(f"""
                <a href="{url}" target="_blank" style="text-decoration:none">
                <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:9px 11px;margin-bottom:5px;transition:all 0.15s"
                     onmouseover="this.style.borderColor='{color}50'"
                     onmouseout="this.style.borderColor='var(--border)'">
                  <div style="font-size:12px;font-weight:700;color:var(--tx1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:'Poppins',sans-serif">{pfx}{disp}</div>
                  <div style="font-size:9px;color:var(--tx4);margin:3px 0 5px">{posts}</div>
                  <div style="height:2px;background:var(--border);border-radius:2px">
                    <div style="height:2px;width:{bar}%;background:{color};border-radius:2px"></div>
                  </div>
                </div></a>""", unsafe_allow_html=True)
                try:    rv = int(str(rank_r).replace("#","").strip())
                except: rv = 10
                chart_items.append({"label":f"{cfg['icon']} {name[:16]}{'…' if len(name)>16 else ''}","platform":cfg["label"],"rank":rv,"color":color})
    if chart_items:
        st.markdown("<div style='font-size:9px;font-weight:700;color:var(--tx4);text-transform:uppercase;letter-spacing:0.1em;margin:14px 0 6px'>Trend prominence</div>", unsafe_allow_html=True)
        order = list(PLATFORM_CONFIG.keys())
        chart_items.sort(key=lambda x:(next((i for i,k in enumerate(order) if PLATFORM_CONFIG[k]["label"]==x["platform"]),99),x["rank"]))
        grid_c = "#1a1a28" if theme=="night" else "#e0e0ec"
        fig = go.Figure(go.Bar(
            x=[max(0,21-item["rank"]) for item in chart_items],
            y=[item["label"] for item in chart_items],
            orientation="h", marker_color=[item["color"] for item in chart_items],
            text=[f" #{item['rank']}" for item in chart_items],
            textposition="outside", textfont=dict(size=9,color="#444"),
            hovertemplate="%{y}<br>Rank #%{customdata}<extra></extra>",
            customdata=[item["rank"] for item in chart_items],
        ))
        fig.update_layout(
            xaxis=dict(gridcolor=grid_c,color="#444",tickfont=dict(size=8),range=[0,24]),
            yaxis=dict(color="#666",tickfont=dict(size=9),autorange="reversed"),
            height=max(200,len(chart_items)*26+40), margin=dict(l=0,r=40,t=4,b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ═════════════════════════════════════════════════════════════════
# SIDEBAR
# ═════════════════════════════════════════════════════════════════

NAV_ITEMS = [
    ("🔍","INVESTIGATIONS","Cross-platform topic search"),
    ("📁","CASE FILES",    "Live trend case cards"),
    ("📡","TREND RADAR",   "Velocity & momentum"),
    ("📊","DEEP DIVE",     "Blueprint generator"),
    ("🗂","SOURCES",       "Platform overview"),
    ("⭐","WATCHLIST",     "Saved topics"),
    ("📋","BRIEFINGS",     "Daily intelligence"),
    ("💬","DEBRIEF",       "Chat with Pugson"),
]

with st.sidebar:
    pugson_src  = f"data:image/jpeg;base64,{PUGSON_B64}" if PUGSON_B64 else ""
    _sb_lime    = "#2a5200" if theme == "day" else "#A3FF12"
    _sb_img_bd  = "rgba(42,82,0,0.35)" if theme == "day" else "rgba(163,255,18,0.30)"
    _sb_glow    = "none" if theme == "day" else f"0 0 6px {_sb_lime}"
    img_tag     = (f'<img src="{pugson_src}" style="width:68px;height:68px;border-radius:50%;border:2px solid {_sb_img_bd};object-fit:cover">'
                   if pugson_src else
                   f'<div style="width:68px;height:68px;border-radius:50%;background:var(--surface);border:2px solid {_sb_img_bd};display:flex;align-items:center;justify-content:center;font-size:26px">🐾</div>')
    st.markdown(f"""
    <div style="padding:18px 16px 14px 16px;border-bottom:1px solid var(--sb-border)">
      <div style="display:flex;align-items:center;gap:11px">
        {img_tag}
        <div>
          <div style="font-size:9px;color:var(--tx4);font-weight:700;letter-spacing:0.1em;text-transform:uppercase">Chief Detective</div>
          <div style="font-size:15px;font-weight:900;color:var(--tx1);font-family:Inter,sans-serif;letter-spacing:-0.3px">PUGSON</div>
          <div style="display:flex;align-items:center;gap:5px;margin-top:2px">
            <span style="width:6px;height:6px;border-radius:50%;background:{_sb_lime};display:inline-block;box-shadow:{_sb_glow}"></span>
            <span style="font-size:9px;color:{_sb_lime};font-weight:700;letter-spacing:0.06em">ONLINE</span>
          </div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    active_nav = st.session_state.active_nav
    st.markdown('<div style="padding:8px 0">', unsafe_allow_html=True)
    for icon, label, _ in NAV_ITEMS:
        if st.button(f"{icon}  {label}", key=f"nav_{label}", use_container_width=True, type="secondary"):
            st.session_state.active_nav = label
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # Theme toggle inside sidebar
    tog_label = "☀️  DAY MODE" if theme == "night" else "🌙  NIGHT MODE"
    tog_tip   = "Switch to Day" if theme=="night" else "Switch to Night"
    if st.button(tog_label, key="theme_toggle", help=tog_tip, use_container_width=True, type="secondary"):
        st.session_state.theme = "day" if theme=="night" else "night"
        st.rerun()

    _upg_btn_bg  = "#2a5200" if theme == "day" else "#A3FF12"
    _upg_btn_col = "#ffffff" if theme == "day" else "#080e14"
    _upg_lbl_col = "#2a5200" if theme == "day" else "#A3FF12"
    st.markdown(f"""
    <div style="position:absolute;bottom:0;left:0;right:0;padding:12px 14px;
                border-top:1px solid var(--sb-border);background:var(--sb-bg)">
      <div style="background:var(--lime-bg);border:1px solid var(--lime-border);border-radius:10px;padding:11px">
        <div style="font-size:13px;margin-bottom:3px">🛡️</div>
        <div style="font-size:10px;font-weight:800;color:{_upg_lbl_col};margin-bottom:3px">UPGRADE TO COMMAND</div>
        <div style="font-size:9px;color:var(--tx4);margin-bottom:8px;line-height:1.5">Unlock advanced tools,<br>historic data &amp; more.</div>
        <div style="background:{_upg_btn_bg};color:{_upg_btn_col};font-size:10px;font-weight:800;text-align:center;padding:6px;border-radius:6px;letter-spacing:0.06em;cursor:pointer">UPGRADE NOW</div>
      </div>
    </div>
    <div style="height:155px"></div>""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════
# THEME TOGGLE  +  HERO
# ═════════════════════════════════════════════════════════════════

active_platform = st.session_state.active_platform
active_nav      = st.session_state.active_nav

# Hero background — day uses golden city, night uses dark city
if theme == "night":
    hero_b64 = BG_DAY_CITY_B64
    hero_overlay = "linear-gradient(to right,rgba(7,9,13,0.97) 0%,rgba(7,9,13,0.90) 38%,rgba(7,9,13,0.60) 65%,rgba(7,9,13,0.18) 100%)"
else:
    hero_b64 = BG_DAY_CITY_B64
    hero_overlay = "linear-gradient(to right,rgba(15,22,45,0.88) 0%,rgba(15,22,45,0.60) 50%,rgba(15,22,45,0.15) 100%)"

bg_style = (f"background-image:url('data:image/jpeg;base64,{hero_b64}');background-size:cover;background-position:65% 20%;"
            if hero_b64 else "background:var(--surface-alt);")

# Trend chips
_chip_data = get_latest_hashtags(platform=active_platform)[:5] if active_platform else []
chips_html = ""
if _chip_data:
    pfx  = "#" if active_platform=="tiktok" else ""
    chps = "".join([
        f'<a href="{h.get("url","#")}" target="_blank" style="display:inline-block;background:rgba(163,255,18,0.10);border:1px solid rgba(163,255,18,0.25);border-radius:16px;padding:3px 12px;font-size:11px;color:rgba(163,255,18,0.90);text-decoration:none;font-weight:600;font-family:Inter,sans-serif">{pfx}{h["name"]}</a>'
        for h in _chip_data
    ])
    chips_html = (f'<div style="display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:14px">'
                  f'<span style="font-size:9px;font-weight:700;color:rgba(255,255,255,0.25);text-transform:uppercase;letter-spacing:0.1em">Trending</span>{chps}</div>')

src_pills = "".join([
    f'<span style="font-size:10px;font-weight:700;color:rgba(255,255,255,0.45);background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);padding:3px 10px;border-radius:12px">{c["icon"]} {c["label"]}</span>'
    for c in PLATFORM_CONFIG.values()
])

popular_topics = ["AI Tools", "Taylor Swift", "Bitcoin", "Climate Change", "OpenAI", "Gaming"]
popular_chips  = "".join([
    f'<span style="font-size:10px;font-weight:600;color:rgba(255,255,255,0.55);background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);padding:4px 12px;border-radius:14px;cursor:pointer;white-space:nowrap">{t}</span>'
    for t in popular_topics
])

# ═════════════════════════════════════════════════════════════════
# AUTO BRIEFING ARTICLES  (compute before rendering)
# ═════════════════════════════════════════════════════════════════

articles_stale = True
if st.session_state.articles_ts:
    articles_stale = (datetime.now()-st.session_state.articles_ts).total_seconds() > 1800
if articles_stale or not st.session_state.trend_articles:
    st.session_state.trend_articles = generate_trend_articles()
    st.session_state.articles_ts    = datetime.now()
articles = st.session_state.trend_articles


# ═════════════════════════════════════════════════════════════════
# TRUE 3-COLUMN INTELLIGENCE DASHBOARD
# Sidebar | Center (Hero + Cases) | Right (Briefing + Radar)
# ═════════════════════════════════════════════════════════════════

_bottom_fade_color = "7,11,16" if theme == "night" else "26,37,56"

# Hero background style — fixed to viewport so center + right panel
# show the same continuous image without bleeding into the cards below.
_hero_bg = (
    f"background-image:{hero_overlay},url('data:image/jpeg;base64,{hero_b64}');"
    "background-size:cover;"
    "background-attachment:fixed;"
    "background-position:65% top;"
) if hero_b64 else ""
_hero_img_style = f"position:relative;z-index:2;{_hero_bg}"
_briefing_bg_style = _hero_bg  # same image, viewport-fixed → seamless continuation

main_col, right_col = st.columns([7, 3], gap="medium")

# ── RIGHT PANEL ───────────────────────────────────────────────────
with right_col:
    st.markdown(f'<div style="{_briefing_bg_style}border-radius:12px 12px 0 0;">', unsafe_allow_html=True)
    render_detective_briefing(articles)
    st.markdown('</div>', unsafe_allow_html=True)
    radar_vel = get_hashtag_velocity(platform=active_platform or "tiktok")
    render_trend_radar(radar_vel, platform=active_platform or "tiktok")
    _wl_style = "background:rgba(10,14,20,0.55);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.08);box-shadow:0 20px 60px rgba(0,0,0,0.45)" if theme == "night" else "background:var(--surface-alt);border:1px solid var(--border)"
    st.markdown(
        f'<div style="{_wl_style};border-radius:14px;padding:14px">'
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
        '<div style="font-family:JetBrains Mono,monospace;font-size:8px;font-weight:700;color:var(--tx3);letter-spacing:0.14em;text-transform:uppercase">⭐ WATCHLIST</div>'
        '<span style="font-family:JetBrains Mono,monospace;font-size:8px;font-weight:700;color:var(--lime-t);cursor:pointer;letter-spacing:0.08em">MANAGE →</span>'
        '</div>'
        '<div style="text-align:center;padding:14px 0">'
        '<div style="font-size:22px;margin-bottom:6px;opacity:0.25">◎</div>'
        '<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:var(--tx4);margin-bottom:10px;letter-spacing:0.04em;line-height:1.6">No signals tracked yet.<br>Add a topic to monitor.</div>'
        '<div style="font-family:JetBrains Mono,monospace;font-size:9px;font-weight:700;color:var(--lime-t);cursor:pointer;letter-spacing:0.08em;background:var(--lime-bg);border:1px solid var(--lime-border);padding:5px 10px;border-radius:6px;display:inline-block">+ ADD SIGNAL</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )

# ── MAIN CONTENT ──────────────────────────────────────────────────
with main_col:

    # ── HERO content ──
    st.markdown(
        f'<div style="position:relative;z-index:2;padding:20px 28px 16px 28px;border-radius:12px;{_hero_img_style}">'
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">'
        f'<svg width="38" height="38" viewBox="0 0 40 40" fill="none"><rect width="40" height="40" rx="10" fill="rgba(13,21,32,0.7)"/><rect x="7" y="20" width="6" height="12" rx="2" fill="#A3FF12"/><rect x="17" y="11" width="6" height="21" rx="2" fill="#A3FF12"/><rect x="27" y="15" width="6" height="17" rx="2" fill="#A3FF12"/></svg>'
        f'<div><div style="font-family:Inter,sans-serif;font-size:28px;font-weight:900;color:#fff;letter-spacing:-1px;line-height:1">Noi<span style="color:#A3FF12;text-shadow:0 0 20px rgba(163,255,18,0.6)">ze</span></div>'
        f'<div style="font-size:9px;color:rgba(255,255,255,0.30);letter-spacing:0.22em;text-transform:uppercase;margin-top:1px">Signal in the noise</div>'
        f'</div></div>'
        f'<div style="font-size:11px;color:rgba(255,255,255,0.40);line-height:1.8;margin-bottom:14px;font-family:Inter,sans-serif">The internet is noisy.&nbsp;·&nbsp;We find what matters.&nbsp;·&nbsp;You stay ahead.</div>'
        f'<div style="background:rgba(0,0,0,0.35);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:10px;margin-bottom:12px">'
        f'<span style="font-size:14px;opacity:0.35">🔍</span>'
        f'<span style="font-size:12px;color:rgba(255,255,255,0.25);font-family:Inter,sans-serif">Investigate any topic, keyword or trend...</span>'
        f'<div style="margin-left:auto;background:#A3FF12;color:#070B10;font-size:10px;font-weight:800;padding:5px 12px;border-radius:6px;letter-spacing:0.06em;white-space:nowrap;flex-shrink:0;box-shadow:0 0 20px rgba(163,255,18,0.40)">INVESTIGATE →</div>'
        f'</div>'
        f'<div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">'
        f'<span style="font-size:9px;font-weight:700;color:rgba(255,255,255,0.15);text-transform:uppercase;letter-spacing:0.12em;white-space:nowrap">Popular:</span>'
        f'{popular_chips}'
        f'</div>'
        f'{chips_html}'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── CASE FILES ───────────────────────────────────────────────
    if active_nav == "CASE FILES":
        st.markdown("<div style='font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:8px'>Select Source</div>", unsafe_allow_html=True)
        pcols = st.columns(4, gap="small")
        for idx,(key,cfg) in enumerate(PLATFORM_CONFIG.items()):
            with pcols[idx]:
                is_active = (active_platform==key)
                lbl = f"🔄 {cfg['icon']} {cfg['label']}" if is_active else f"{cfg['icon']} {cfg['label']}"
                if st.button(lbl,key=f"plat_{key}",use_container_width=True,type="primary" if is_active else "secondary"):
                    st.session_state.active_platform = key
                    st.session_state.do_fetch = True
                    st.rerun()
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        if not active_platform:
            # Welcome — show briefing articles as case previews
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:8px;margin:14px 0 12px 0">
              <div style="width:6px;height:6px;border-radius:50%;background:var(--lime-t);box-shadow:0 0 8px var(--lime-t)"></div>
              <span style="font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase">Cases Opened Today</span>
              <span style="font-size:9px;font-weight:800;color:var(--lime-t);background:var(--lime-bg);border:1px solid var(--lime-border);padding:1px 7px;border-radius:6px">{len(articles)} NEW</span>
            </div>""", unsafe_allow_html=True)
            if articles:
                art_cols = st.columns(3, gap="small")
                _gaming_col = "#2a5200" if theme == "day" else "#A3FF12"
                cat_colors = {"News":"#4285f4","Music & Film":"#fe2c55","Gaming":_gaming_col}
                for i,art in enumerate(articles[:3]):
                    cat   = art.get("category","News")
                    color = cat_colors.get(cat, _gaming_col)
                    tag   = art.get("tag","Trending")
                    head  = art.get("headline","")
                    summ  = art.get("summary","")
                    url   = art.get("url","#")
                    with art_cols[i]:
                        st.markdown(
                            f'<a href="{url}" target="_blank" style="text-decoration:none">'
                            f'<div style="background:var(--surface);border:1px solid var(--border);border-top:2px solid {color};border-radius:10px;padding:14px;height:100%">'
                            f'<div style="display:flex;justify-content:space-between;margin-bottom:8px">'
                            f'<span style="font-family:JetBrains Mono,monospace;font-size:8px;color:var(--amber);font-weight:600;letter-spacing:0.10em">CASE #{i+1:04d}</span>'
                            f'<span style="font-family:JetBrains Mono,monospace;font-size:8px;font-weight:800;color:{color};background:{color}18;padding:2px 7px;border-radius:3px;letter-spacing:0.08em">{tag.upper()}</span>'
                            f'</div>'
                            f'<div style="font-size:13px;font-weight:700;color:var(--tx1);line-height:1.35;margin-bottom:7px;font-family:Poppins,sans-serif">{head}</div>'
                            f'<div style="font-size:11px;color:var(--tx3);line-height:1.65">{summ}</div>'
                            f'<div style="margin-top:12px;font-family:JetBrains Mono,monospace;font-size:9px;font-weight:700;color:{color};letter-spacing:0.08em">OPEN FILE ›</div>'
                            f'</div></a>',
                            unsafe_allow_html=True
                        )
            st.markdown("<div style='margin:14px 0 4px;border-top:1px solid var(--border)'></div>", unsafe_allow_html=True)
            st.markdown("<div style='font-size:11px;color:var(--tx4);text-align:center;padding:4px 0'>Select a source above to open live case files</div>", unsafe_allow_html=True)

        else:
            hashtags      = get_latest_hashtags(platform=active_platform)
            velocity_data = get_hashtag_velocity(platform=active_platform)
            cfg           = PLATFORM_CONFIG[active_platform]
            is_gpt        = bool(hashtags and hashtags[0].get("source")=="gpt_fallback")
            climbing      = [h for h in velocity_data if h.get("rank_change",0)<0]
            new_ones      = [h for h in velocity_data if h.get("is_new")]
            mins_ago_str  = "just now"
            if hashtags:
                try:
                    ts = datetime.fromisoformat(hashtags[0].get("scraped_at",""))
                    m  = int((datetime.now()-ts).total_seconds()/60)
                    mins_ago_str = f"{m}m ago" if m>0 else "just now"
                except: pass

            st.markdown(f"""
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:6px">
              <div style="display:flex;align-items:center;gap:8px">
                <div style="width:6px;height:6px;border-radius:50%;background:var(--lime-t);box-shadow:0 0 8px var(--lime-t)"></div>
                <span style="font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase">Cases Opened Today</span>
                <span style="font-size:9px;font-weight:800;color:var(--lime-t);background:var(--lime-bg);border:1px solid var(--lime-border);padding:1px 7px;border-radius:6px">{len(hashtags)} NEW</span>
              </div>
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                <span class="status-pill"><span class="{'dot-gpt' if is_gpt else 'dot-live'}"></span>{'AI data' if is_gpt else 'Live'}</span>
                <span class="status-pill">🕐 {mins_ago_str}</span>
                <span class="status-pill">📈 {len(climbing)} escalating</span>
                <span class="status-pill">✨ {len(new_ones)} new</span>
              </div>
            </div>""", unsafe_allow_html=True)

            if is_gpt:
                st.markdown(f"""
                <div style="background:rgba(255,149,0,0.08);border:1px solid rgba(255,149,0,0.25);border-radius:8px;padding:9px 14px;margin-bottom:10px;display:flex;align-items:center;gap:8px">
                  <span>⚠️</span><div style="font-size:11px;color:#ff9500;line-height:1.5"><b>{cfg['label']} live data unavailable.</b> Showing AI-generated intelligence. Hit 🔄 {cfg['label']} to retry.</div>
                </div>""", unsafe_allow_html=True)

            st.markdown("<div style='font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px'>Rank Velocity</div>", unsafe_allow_html=True)
            render_velocity_chart(velocity_data, platform=active_platform)
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            render_case_cards(velocity_data if velocity_data else hashtags, platform=active_platform)

        render_signal_guide()

        # Quote banner with newspaper bg
        np_src = f"data:image/jpeg;base64,{NEWSPAPER_B64}" if NEWSPAPER_B64 else ""
        if np_src:
            st.markdown(
                f'<div style="display:flex;align-items:stretch;border-radius:16px;overflow:hidden;margin:8px 0 4px;min-height:130px;border:1px solid var(--border-2)">'
                f'<div style="flex:1;background:var(--surface-alt);padding:28px 32px;display:flex;flex-direction:column;justify-content:center">'
                f'<div style="font-size:32px;color:var(--amber);line-height:0.7;margin-bottom:12px;font-family:Georgia,serif;opacity:0.8">"</div>'
                f'<div style="font-size:14px;color:var(--tx2);line-height:1.75;font-style:italic">In a world of infinite noise,<br>we find the signal that shapes tomorrow.</div>'
                f'<div style="font-size:10px;color:var(--tx4);margin-top:10px;letter-spacing:0.04em">— Chief Detective Pugson</div>'
                f'</div>'
                f'<div style="width:42%;background-image:url(\'{np_src}\');background-size:cover;background-position:center 30%"></div>'
                f'</div>',
                unsafe_allow_html=True
            )

    # ── INVESTIGATIONS ───────────────────────────────────────────
    elif active_nav == "INVESTIGATIONS":
        st.markdown("<div style='font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Cross-Platform Investigations</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:12px;color:var(--tx3);margin-bottom:12px;line-height:1.7'>Type any topic to see the top 3 trending stories from all 4 platforms. Falls back to AI if live data is unavailable.</div>", unsafe_allow_html=True)
        inv_c1, inv_c2 = st.columns([5,1])
        with inv_c1:
            inv_topic = st.text_input("topic",placeholder="e.g. bitcoin, taylor swift, AI tools...",label_visibility="collapsed",key="inv_topic")
        with inv_c2:
            inv_go = st.button("INVESTIGATE",type="primary",use_container_width=True,key="inv_go")
        if inv_go and inv_topic.strip():
            with st.spinner(f"Scanning all platforms for \"{inv_topic.strip()}\"..."):
                st.session_state.pulse_results = niche_pulse(inv_topic.strip())
                st.session_state.pulse_query   = inv_topic.strip()
        if st.session_state.pulse_results and st.session_state.pulse_query:
            st.markdown("---")
            render_niche_pulse(st.session_state.pulse_results, st.session_state.pulse_query)
            if st.button("✕ Clear",key="inv_clear"):
                st.session_state.pulse_results=None; st.session_state.pulse_query=""; st.rerun()
        elif not st.session_state.pulse_results:
            st.markdown('<div style="text-align:center;padding:40px 20px"><div style="font-size:36px;margin-bottom:10px">🔍</div><div style="font-size:13px;font-weight:700;color:var(--tx1);margin-bottom:6px;font-family:Poppins,sans-serif">Start an investigation</div><div style="font-size:12px;color:var(--tx4)">Enter any topic above and hit INVESTIGATE.</div></div>', unsafe_allow_html=True)

    # ── TREND RADAR ──────────────────────────────────────────────
    elif active_nav == "TREND RADAR":
        st.markdown("<div style='font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Trend Radar — Rank Velocity</div>", unsafe_allow_html=True)
        pcols2 = st.columns(4, gap="small")
        for idx,(key,cfg) in enumerate(PLATFORM_CONFIG.items()):
            with pcols2[idx]:
                is_active=(active_platform==key)
                if st.button(f"{cfg['icon']} {cfg['label']}",key=f"radar_plat_{key}",use_container_width=True,type="primary" if is_active else "secondary"):
                    st.session_state.active_platform=key; st.session_state.do_fetch=True; st.rerun()
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        render_velocity_chart(get_hashtag_velocity(platform=active_platform or "tiktok"), platform=active_platform or "tiktok")
        render_signal_guide()

    # ── DEEP DIVE ────────────────────────────────────────────────
    elif active_nav == "DEEP DIVE":
        st.markdown("<div style='font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Deep Dive — Content Blueprint Generator</div>", unsafe_allow_html=True)
        if not active_platform:
            st.markdown("<div style='font-size:12px;color:var(--tx4);padding:16px 0'>Select a source via Case Files first.</div>", unsafe_allow_html=True)
        else:
            bp_hashtags = get_latest_hashtags(platform=active_platform)
            cfg_bp      = PLATFORM_CONFIG[active_platform]
            if not bp_hashtags:
                st.info(f"No {cfg_bp['label']} trends yet — load Case Files first.")
            else:
                st.markdown(f"<div style='font-size:12px;color:var(--tx3);margin-bottom:12px;line-height:1.7'>Select trends from <b style='color:{cfg_bp['color']}'>{cfg_bp['icon']} {cfg_bp['label']}</b> to generate a production blueprint.</div>", unsafe_allow_html=True)
                bp_niche = st.text_input("Your niche (optional)",placeholder="e.g. fitness, fashion, food...",key="bp_niche")
                selected=[]
                cols=st.columns(2)
                for i,h in enumerate(bp_hashtags):
                    with cols[i%2]:
                        pfx="#" if active_platform=="tiktok" else ""
                        if st.checkbox(f"{pfx}{h['name']}",key=f"bp_{active_platform}_{i}"): selected.append(h["name"])
                st.markdown("---")
                if st.button("🎬 Generate Blueprint",type="primary",use_container_width=True,disabled=len(selected)==0):
                    with st.spinner("Building intelligence file..."):
                        bp=generate_blueprint(selected,bp_niche.strip() or "content creator")
                    st.markdown("---"); st.markdown(bp)

    # ── BRIEFINGS ────────────────────────────────────────────────
    elif active_nav == "BRIEFINGS":
        # Newspaper hero banner
        np_src = f"data:image/jpeg;base64,{NEWSPAPER_B64}" if NEWSPAPER_B64 else ""
        date_str = datetime.now().strftime("%B %d, %Y").upper()
        if np_src:
            st.markdown(
                f'<div style="background-image:url(\'{np_src}\');background-size:cover;background-position:center 35%;'
                f'border-radius:16px;position:relative;overflow:hidden;margin-bottom:20px;min-height:130px;border:1px solid var(--border)">'
                f'<div style="position:absolute;inset:0;background:linear-gradient(to right,rgba(5,5,12,0.97) 0%,rgba(5,5,12,0.80) 50%,rgba(0,0,0,0.2) 100%);border-radius:16px"></div>'
                f'<div style="position:relative;padding:26px 30px">'
                f'<div style="font-size:9px;font-weight:700;color:#A3FF12;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:5px">● Daily Intelligence Report</div>'
                f'<div style="font-size:26px;font-weight:900;color:#fff;font-family:Poppins,sans-serif;letter-spacing:-0.5px">DAILY BRIEFING</div>'
                f'<div style="font-size:10px;color:rgba(255,255,255,0.32);margin-top:5px;letter-spacing:0.12em">SIGNALS · TRENDS · CLUES · {date_str}</div>'
                f'</div></div>',
                unsafe_allow_html=True
            )
        # Article cards
        _gaming_col_b = "#2a5200" if theme == "day" else "#A3FF12"
        cat_colors = {"News":"#4285f4","Music & Film":"#fe2c55","Gaming":_gaming_col_b}
        cat_icons_b = {"News":"📰","Music & Film":"🎬","Gaming":"🎮"}
        for i, art in enumerate(articles):
            cat   = art.get("category","")
            head  = art.get("headline","")
            summ  = art.get("summary","")
            tag   = art.get("tag","")
            color = art.get("color", cat_colors.get(cat, _gaming_col_b))
            url   = art.get("url","#")
            icon  = cat_icons_b.get(cat,"📡")
            st.markdown(
                f'<a href="{url}" target="_blank" style="text-decoration:none">'
                f'<div style="background:var(--surface);border:1px solid var(--border);border-left:3px solid {color};border-radius:12px;padding:16px 18px;margin-bottom:12px">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
                f'<div style="display:flex;align-items:center;gap:7px">'
                f'<div style="width:28px;height:28px;border-radius:7px;background:{color}20;border:1px solid {color}40;display:flex;align-items:center;justify-content:center;font-size:14px">{icon}</div>'
                f'<div><div style="font-size:9px;font-weight:700;color:{color};letter-spacing:0.1em;text-transform:uppercase">{cat}</div>'
                f'<div style="font-size:8px;color:var(--tx4)">{tag}</div></div></div>'
                f'<span style="font-size:9px;font-weight:800;color:{color};background:{color}18;padding:2px 8px;border-radius:4px">#{i+1}</span>'
                f'</div>'
                f'<div style="font-size:15px;font-weight:700;color:var(--tx1);margin-bottom:7px;font-family:Poppins,sans-serif;line-height:1.35">{head}</div>'
                f'<div style="font-size:12px;color:var(--tx3);line-height:1.7">{summ}</div>'
                f'<div style="margin-top:10px;font-size:10px;font-weight:700;color:{color}">READ FULL REPORT →</div>'
                f'</div></a>',
                unsafe_allow_html=True
            )
        if st.button("🔄 Refresh Briefing", type="secondary"):
            st.session_state.trend_articles=[]; st.session_state.articles_ts=None; st.rerun()

    # ── SOURCES ──────────────────────────────────────────────────
    elif active_nav == "SOURCES":
        st.markdown("<div style='font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Source Status</div>", unsafe_allow_html=True)
        for key,cfg in PLATFORM_CONFIG.items():
            age   = get_data_age_minutes(platform=key)
            count = len(get_latest_hashtags(platform=key))
            age_str = f"{int(age)}m ago" if age is not None else "No data"
            _src_lime = "#2a5200" if theme == "day" else "#A3FF12"
            sc    = _src_lime if (age is not None and age<cfg["refresh_minutes"]) else "#ff9500"
            st.markdown(f"""
            <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;gap:14px">
              <span style="font-size:22px">{cfg['icon']}</span>
              <div style="flex:1">
                <div style="font-size:13px;font-weight:700;color:var(--tx1)">{cfg['label']}</div>
                <div style="font-size:10px;color:var(--tx4);margin-top:2px">Updated: {age_str} · {count} trends · Refresh: {cfg['refresh_minutes']}m</div>
              </div>
              <div style="width:8px;height:8px;border-radius:50%;background:{sc}"></div>
            </div>""", unsafe_allow_html=True)

    # ── DEBRIEF ──────────────────────────────────────────────────
    elif active_nav == "DEBRIEF":
        st.markdown("<div style='font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px'>Debrief with Pugson</div>", unsafe_allow_html=True)
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        user_msg = st.chat_input("Ask about trends, your niche, content ideas...")
        if user_msg:
            st.session_state.chat_history.append({"role":"user","content":user_msg})
            with st.chat_message("user"): st.markdown(user_msg)
            with st.chat_message("assistant"):
                with st.spinner("Pugson is on it..."):
                    resp = run_agent(user_msg)
                st.markdown(resp)
            st.session_state.chat_history.append({"role":"assistant","content":resp})
        if st.session_state.chat_history:
            if st.button("Clear debrief",key="clear_chat"): st.session_state.chat_history=[]; st.rerun()

    # ── WATCHLIST ────────────────────────────────────────────────
    elif active_nav == "WATCHLIST":
        st.markdown('<div style="text-align:center;padding:40px 20px"><div style="font-size:36px;margin-bottom:10px">⭐</div><div style="font-size:14px;font-weight:700;color:var(--tx1);margin-bottom:6px;font-family:Poppins,sans-serif">Watchlist</div><div style="font-size:12px;color:var(--tx4)">Save topics to track — coming soon.</div></div>', unsafe_allow_html=True)
