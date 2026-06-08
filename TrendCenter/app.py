import sqlite3
import threading
import time
import base64
import io
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from datetime import datetime

from agent import run_agent, generate_blueprint, generate_topic_blueprint, research_niche_hashtags, niche_pulse, build_dossier, generate_trend_articles, generate_strange_signals, generate_case_file
from database import get_latest_hashtags, get_hashtag_velocity, init_db, DB_PATH, save_snapshot, cleanup_old_snapshots, get_data_age_minutes
from scraper import scrape_hashtags
from platforms import scrape_google, scrape_youtube, scrape_reddit

PLATFORM_CONFIG = {
    "tiktok":  {"label": "TikTok",        "icon": "🎵", "scraper": scrape_hashtags, "link_label": "TikTok",  "refresh_minutes": 60,  "color": "#fe2c55"},
    "google":  {"label": "Google Trends", "icon": "📈", "scraper": scrape_google,   "link_label": "Google",  "refresh_minutes": 60,  "color": "#4285f4"},
    "youtube": {"label": "YouTube",       "icon": "📺", "scraper": scrape_youtube,  "link_label": "YouTube", "refresh_minutes": 240, "color": "#ff4444"},
    "reddit":  {"label": "Reddit",        "icon": "🔴", "scraper": scrape_reddit,   "link_label": "Reddit",  "refresh_minutes": 60,  "color": "#ff5700"},
}

# Full-colour brand logos (inline SVG data URIs) for the Select Source icon
# buttons. Painted as CSS background-image so the buttons stay icon-only.
_TT = ("M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 "
       "1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 "
       "1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 "
       "1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 "
       "1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z")
_PLATFORM_SVG_RAW = {
    "tiktok": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
        "<path fill='#25F4EE' transform='translate(-1.1 -0.7)' d='" + _TT + "'/>"
        "<path fill='#FE2C55' transform='translate(1.1 0.7)' d='" + _TT + "'/>"
        "<path fill='#ffffff' d='" + _TT + "'/></svg>"
    ),
    "google": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'>"
        "<path fill='#FFC107' d='M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 "
        "0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 "
        "4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z'/>"
        "<path fill='#FF3D00' d='M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 "
        "1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z'/>"
        "<path fill='#4CAF50' d='M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238C29.211 35.091 26.715 "
        "36 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z'/>"
        "<path fill='#1976D2' d='M43.611 20.083H42V20H24v8h11.303c-.792 2.237-2.231 4.166-4.087 5.571l.003-.002 "
        "6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z'/></svg>"
    ),
    "youtube": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
        "<path fill='#FF0000' d='M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 "
        "3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 "
        "3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 "
        "2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814z'/>"
        "<path fill='#ffffff' d='M9.545 15.568V8.432L15.818 12z'/></svg>"
    ),
    "reddit": (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
        "<path fill='#FF4500' d='M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 "
        "0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 "
        "3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 "
        ".716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 "
        "0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 "
        "1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 "
        ".14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 "
        "8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 "
        "0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 "
        "0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 "
        "2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 "
        "0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z'/></svg>"
    ),
}
# Base64-encode so the data URIs survive CSS parsing with zero escaping issues.
PLATFORM_SVG = {
    _k: "data:image/svg+xml;base64," + base64.b64encode(_v.encode("utf-8")).decode("ascii")
    for _k, _v in _PLATFORM_SVG_RAW.items()
}


def _platform_icon(key, size=16):
    """Inline <img> of a platform's real brand logo (TikTok/Google/YouTube/
    Reddit). Falls back to the platform's emoji if no SVG exists."""
    svg = PLATFORM_SVG.get(key)
    if svg:
        return (f'<img src="{svg}" style="width:{size}px;height:{size}px;'
                f'vertical-align:middle;display:inline-block;flex-shrink:0"/>')
    return PLATFORM_CONFIG.get(key, {}).get("icon", "")

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
RADAR_MAP_B64        = load_img_b64("static/alien.png",            max_width=800,  quality=82)
HUD_BG_B64           = load_img_b64("static/hud_bg.jpg",            max_width=800,  quality=72)
BG_BODY_B64          = load_img_b64("static/bg_body.jpg",           max_width=1600, quality=70)
ASPHALT_BG_B64       = load_img_b64("static/asphalt_bg.png",        max_width=900,  quality=68)
CITYMAP_BG_B64       = load_img_b64("static/bg_citymap.png",        max_width=1800, quality=72)

# ── Old-city-map blueprint texture (drawn in code; faint, theme-matched lines) ──
def _build_old_city_map_svg() -> str:
    import math, random
    rnd = random.Random(7)
    W = H = 800
    p = ["<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 800'>"]
    p.append("<defs><style>"
             ".rd{fill:none;stroke:#A3FF12;stroke-opacity:0.30;stroke-width:1.3}"
             ".rd2{fill:none;stroke:#A3FF12;stroke-opacity:0.17;stroke-width:0.8}"
             ".blk{fill:#A3FF12;fill-opacity:0.04;stroke:#A3FF12;stroke-opacity:0.11;stroke-width:0.5}"
             ".rv{fill:none;stroke:#3fd0e6;stroke-opacity:0.22;stroke-width:7;stroke-linecap:round;stroke-linejoin:round}"
             ".cmp{fill:none;stroke:#A3FF12;stroke-opacity:0.30;stroke-width:1}"
             ".cmpf{fill:#A3FF12;fill-opacity:0.20}"
             "</style></defs>")
    # avenues (slightly jittered grid for a hand-drawn old-map feel)
    ys, y = [], 60
    while y < H - 30:
        ys.append(y); y += rnd.randint(58, 92)
    xs, x = [], 60
    while x < W - 30:
        xs.append(x); x += rnd.randint(58, 92)
    for yy in ys:
        p.append(f"<path class='rd' d='M16 {yy} L784 {yy+rnd.randint(-6,6)}'/>")
    for xx in xs:
        p.append(f"<path class='rd' d='M{xx} 16 L{xx+rnd.randint(-6,6)} 784'/>")
    # city blocks between intersections
    for i in range(len(xs) - 1):
        for k in range(len(ys) - 1):
            if rnd.random() < 0.42:
                bx, by = xs[i] + 5, ys[k] + 5
                bw, bh = xs[i+1] - xs[i] - 10, ys[k+1] - ys[k] - 10
                if bw > 6 and bh > 6:
                    p.append(f"<rect class='blk' x='{bx}' y='{by}' width='{bw}' height='{bh}'/>")
    # diagonal grand avenues
    p.append("<path class='rd2' d='M16 130 L770 740'/>")
    p.append("<path class='rd2' d='M784 90 L60 760'/>")
    # central plaza with radial streets
    cx, cy = 410, 380
    p.append(f"<circle class='rd' cx='{cx}' cy='{cy}' r='40'/><circle class='rd' cx='{cx}' cy='{cy}' r='80'/>")
    for a in range(0, 360, 45):
        rad = math.radians(a)
        p.append(f"<path class='rd2' d='M{cx+math.cos(rad)*40:.0f} {cy+math.sin(rad)*40:.0f} "
                 f"L{cx+math.cos(rad)*155:.0f} {cy+math.sin(rad)*155:.0f}'/>")
    # winding river
    p.append("<path class='rv' d='M-20 250 C160 330 250 170 430 300 S700 520 840 470'/>")
    # compass rose (top-right)
    ox, oy = 690, 115
    p.append(f"<circle class='cmp' cx='{ox}' cy='{oy}' r='34'/><circle class='cmp' cx='{ox}' cy='{oy}' r='23'/>")
    p.append(f"<polygon class='cmpf' points='{ox},{oy-32} {ox-7},{oy} {ox},{oy-5} {ox+7},{oy}'/>")
    p.append(f"<polygon class='cmp' points='{ox},{oy+32} {ox-7},{oy} {ox},{oy+5} {ox+7},{oy}'/>")
    p.append(f"<path class='cmp' d='M{ox-34} {oy} L{ox+34} {oy}'/>")
    p.append("</svg>")
    return "".join(p)

OLD_CITY_MAP_B64 = base64.b64encode(_build_old_city_map_svg().encode("utf-8")).decode("ascii")

# ── Page config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Noize — Signal in the noise",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="collapsed",
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
    "dossier":         None,
    "topic_blueprint": None,
    "topic_bp_query":  "",
    "trend_articles":  [],
    "articles_ts":     None,
    "strange_signals": [],
    "strange_ts":      None,
    "strange_sel":     None,
    "radar_nonce":     0,
    "active_nav":      "CASE FILES",
    "theme":           "night",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

theme = st.session_state.theme

# ── Body background texture injection ────────────────────────────
_SITE_BG_B64 = CITYMAP_BG_B64 or BG_BODY_B64
if _SITE_BG_B64:
    st.markdown(f"""
    <style id="noize-site-backdrop">
    .stApp {{
      background-color: #060904 !important;
      background-image: none !important;
    }}
    /* full-page city-map backdrop: fixed, brightened (source image is near-black)
       and a little transparent so it reads as a subtle noir texture */
    .stApp::before {{
      content: "";
      position: fixed;
      inset: 0;
      z-index: 0;
      pointer-events: none;
      background-image: url('data:image/jpeg;base64,{_SITE_BG_B64}');
      background-size: cover;
      background-position: center;
      background-repeat: no-repeat;
      filter: brightness(1.75) saturate(1.12) contrast(1.05);
      opacity: 0.55;
    }}
    /* a touch of vignette + dark wash on top of the map for depth/readability */
    .stApp::after {{
      content: "";
      position: fixed;
      inset: 0;
      z-index: 0;
      pointer-events: none;
      background:
        radial-gradient(ellipse at 50% 35%, rgba(6,9,4,0.10), rgba(6,9,4,0.55) 85%);
    }}
    /* let the backdrop show through the stacked Streamlit containers
       (these are painted solid elsewhere; higher specificity wins) and keep
       the actual content above the map layers */
    .stApp [data-testid="stAppViewContainer"],
    .stApp [data-testid="stHeader"],
    .stApp [data-testid="stMain"],
    .stApp section.main,
    .stApp .block-container {{
      background: transparent !important;
    }}
    .stApp [data-testid="stAppViewContainer"],
    .stApp [data-testid="stHeader"] {{
      position: relative;
      z-index: 1;
    }}
    </style>
    """, unsafe_allow_html=True)

# ── CSS — Bloomberg Terminal × Palantir × Intelligence Agency ────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;0,900;1,400&family=JetBrains+Mono:wght@400;500;600;700&family=Orbitron:wght@600;700;800;900&display=swap');

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
/* Nav now lives in a horizontal top bar (mobile-friendly), so the left sidebar
   is fully retired. Hide all header chrome AND the sidebar / its re-open arrow. */
[data-testid="stHeader"] {
  background: transparent !important;
  box-shadow: none !important;
  pointer-events: none !important;
}
[data-testid="stDecoration"], [data-testid="stStatusWidget"],
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
[data-testid="stSidebar"], [data-testid="stExpandSidebarButton"] {
  display: none !important;
}
/* Top nav: keep the button row horizontal and let it scroll on small screens
   instead of wrapping. Scoped to the keyed container .st-key-noizetopnav. */
.st-key-noizetopnav [data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap !important;
  overflow-x: auto !important;
  gap: 6px !important;
  padding-bottom: 4px !important;
}
.st-key-noizetopnav [data-testid="stColumn"] {
  min-width: fit-content !important;
  width: auto !important;
  flex: 0 0 auto !important;
}
.st-key-noizetopnav [data-testid="stColumn"] button {
  white-space: nowrap !important;
}
/* ── Hero glassy search — overlaid on the city image ── */
/* Glassy translucent input bar */
.st-key-herowrap [data-baseweb="input"],
.st-key-herowrap [data-baseweb="base-input"],
.st-key-herowrap [data-testid="stTextInput"] > div > div {
  background: rgba(0,0,0,0.38) !important;
  backdrop-filter: blur(12px) !important;
  -webkit-backdrop-filter: blur(12px) !important;
  border: 1px solid rgba(255,255,255,0.12) !important;
  border-radius: 10px !important;
}
.st-key-herowrap [data-testid="stTextInput"] input {
  color: #fff !important;
}
.st-key-herowrap [data-testid="stTextInput"] input::placeholder {
  color: rgba(255,255,255,0.40) !important;
}
/* INVESTIGATE: keep the lime pill on one line */
.st-key-herowrap button[kind="primary"] {
  white-space: nowrap !important;
  border-radius: 10px !important;
}
/* Popular chips → small translucent pills that scroll horizontally.
   Column sizing scoped to .st-key-herochips so the search input row is
   NOT shrunk. */
.st-key-herochips [data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap !important;
  overflow-x: auto !important;
  gap: 8px !important;
  padding-bottom: 2px !important;
}
.st-key-herochips [data-testid="stColumn"] {
  min-width: fit-content !important;
  width: auto !important;
  flex: 0 0 auto !important;
}
.st-key-herowrap button[kind="secondary"] {
  background: rgba(255,255,255,0.08) !important;
  border: 1px solid rgba(255,255,255,0.14) !important;
  color: rgba(255,255,255,0.85) !important;
  border-radius: 16px !important;
  padding: 2px 12px !important;
  min-height: 0 !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  white-space: nowrap !important;
}
.st-key-herowrap button[kind="secondary"]:hover {
  border-color: rgba(163,255,18,0.55) !important;
  color: #fff !important;
}
/* keep the popular-chip row horizontal + scrollable, but DON'T squash the
   search row (which has the wide text input) — target only the chip row via
   the 6-column layout is hard, so just let the row wrap gracefully */
.st-key-herowrap [data-testid="stHorizontalBlock"] {
  gap: 8px !important;
}
[data-testid="stAppViewContainer"] { background: var(--bg) !important; }

.stApp {
  background-color: var(--bg) !important;
}

.block-container { padding: 0.75rem 1.2rem 5rem 1.2rem !important; max-width: 1000px !important; margin: 0 auto !important; }

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

def render_detective_briefing(articles, panel_bg_override=None):
    hour     = datetime.now().hour
    greeting = "Good morning" if hour<12 else ("Good afternoon" if hour<18 else "Good evening")
    # Crisp inline SVG icons (stroke uses the COL token, swapped per-category).
    _svg_news = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="COL" '
                 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                 '<rect x="3" y="4" width="18" height="16" rx="2"/><line x1="7" y1="8.5" x2="13" y2="8.5"/>'
                 '<line x1="7" y1="12" x2="17" y2="12"/><line x1="7" y1="15.5" x2="17" y2="15.5"/></svg>')
    _svg_film = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="COL" '
                 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                 '<rect x="3" y="6" width="18" height="14" rx="2"/><line x1="3" y1="10.5" x2="21" y2="10.5"/>'
                 '<line x1="7" y1="6" x2="5" y2="10.5"/><line x1="12" y1="6" x2="10" y2="10.5"/>'
                 '<line x1="17" y1="6" x2="15" y2="10.5"/></svg>')
    _svg_game = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="COL" '
                 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                 '<rect x="2" y="7" width="20" height="11" rx="5"/><line x1="7" y1="11" x2="7" y2="14"/>'
                 '<line x1="5.5" y1="12.5" x2="8.5" y2="12.5"/>'
                 '<circle cx="16.5" cy="11.5" r="1" fill="COL" stroke="none"/>'
                 '<circle cx="18.5" cy="13.5" r="1" fill="COL" stroke="none"/></svg>')
    # Colors drawn from the page's own radar palette so it all reads as one system.
    cat_meta = {
        "News":         ("#4da8ff", _svg_news),
        "Music & Film": ("#fbbf24", _svg_film),
        "Gaming":       ("#A3FF12", _svg_game),
    }
    vels = ["+573%", "+302%", "+218%"]
    leads_html = ""
    for idx, art in enumerate(articles[:3]):
        cat   = art.get("category","News")
        head  = (art.get("headline","") or "")[:72]
        summ  = (art.get("summary","") or "")[:150]
        url   = art.get("url","#")
        col, svg = cat_meta.get(cat, ("#A3FF12", _svg_news))
        icon_svg = svg.replace("COL", col)
        vel = vels[idx % len(vels)]
        icon_style  = f"width:34px;height:34px;border-radius:9px;background:{col}1f;border:1px solid {col}55;display:flex;align-items:center;justify-content:center;flex-shrink:0"
        lead_style  = f"font-family:'JetBrains Mono',monospace;font-size:8px;font-weight:700;color:{col};letter-spacing:0.14em;text-transform:uppercase;margin-bottom:3px"
        head_style  = "font-size:11.5px;font-weight:700;color:var(--tx1);line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden"
        summ_style  = "font-size:9.5px;color:var(--tx3);line-height:1.5;margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden"
        meta_style  = "display:flex;align-items:center;justify-content:flex-end;margin-top:6px"
        card_style  = f"display:flex;gap:10px;align-items:flex-start;padding:10px 11px;background:var(--surface-2);border:1px solid var(--border-2);border-left:2px solid {col};border-radius:9px;height:100%"
        vel_style   = "font-size:10.5px;font-weight:800;color:var(--lime-t);white-space:nowrap"
        leads_html += (f'<a href="{url}" target="_blank" style="text-decoration:none;flex:1 1 240px;min-width:0;display:block">'
                       f'<div style="{card_style}">'
                       f'<div style="{icon_style}">{icon_svg}</div>'
                       f'<div style="flex:1;min-width:0">'
                       f'<div style="{lead_style}">Lead 0{idx+1} · {cat}</div>'
                       f'<div style="{head_style}">{head}</div>'
                       f'<div style="{summ_style}">{summ}</div>'
                       f'<div style="{meta_style}"><span style="{vel_style}">↑ {vel}</span></div>'
                       f'</div>'
                       f'</div></a>')
    if not leads_html:
        leads_html = '<div style="color:var(--tx4);font-size:12px;padding:10px">Loading intelligence...</div>'
    view_btn = '<a href="#" style="display:block;text-align:center;margin-top:10px;padding:8px;background:var(--lime-bg);border:1px solid var(--lime-border);border-radius:8px;font-size:10px;font-weight:700;color:var(--lime-t);text-decoration:none;letter-spacing:0.06em">VIEW FULL BRIEFING →</a>'
    ts_str      = datetime.now().strftime("%H:%M · %b %d")
    if panel_bg_override:
        panel_bg   = panel_bg_override
        panel_shad = ""
    else:
        panel_bg   = "background:rgba(10,14,20,0.55);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)" if theme == "night" else "background:var(--surface-alt)"
        panel_shad = ";box-shadow:0 8px 40px rgba(0,0,0,0.45),0 0 0 1px rgba(255,255,255,0.04)" if theme == "night" else ""
    st.markdown(
        f'<div style="{panel_bg};border:1px solid var(--border-2);border-radius:14px;padding:16px;margin-bottom:12px{panel_shad}">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:8px;font-weight:700;color:var(--amber);letter-spacing:0.16em;text-transform:uppercase">▸ INTEL REPORT</div>'
        f'<span style="font-family:JetBrains Mono,monospace;font-size:8px;color:var(--tx4);letter-spacing:0.06em">{ts_str}</span>'
        f'</div>'
        f'<div style="font-size:14px;font-weight:800;color:var(--tx1);margin-bottom:1px;font-family:Inter,sans-serif">{greeting}, Detective.</div>'
        f'<div style="font-size:10px;color:var(--tx3);margin-bottom:12px;font-family:JetBrains Mono,monospace">3 LEADS ACTIVE · PRIORITY CLEARANCE</div>'
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:4px">{leads_html}</div>'
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


# ── STRANGE SIGNALS RADAR ───────────────────────────────────────
SIGNAL_TYPE_COLORS = {
    "UFO":        "#4da8ff",
    "Strange":    "#A3FF12",
    "Paranormal": "#b07cff",
    "Unsolved":   "#fbbf24",
    "Glitch":     "#ff5cf0",
    "Cryptid":    "#ff7a3b",
}

# emoji used in the classified-files list (one per signal type)
SIGNAL_TYPE_EMOJI = {
    "UFO": "🛸", "Strange": "❔", "Paranormal": "👻",
    "Unsolved": "🔎", "Glitch": "🌀", "Cryptid": "🐾",
}


def _hex_rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _add_radar_bg(fig, is_night):
    """Drop the dark world map (preferred) behind the polar grid."""
    if RADAR_MAP_B64:
        fig.update_layout(images=[dict(
            source=f"data:image/png;base64,{RADAR_MAP_B64}",
            xref="paper", yref="paper", x=0.5, y=0.5,
            xanchor="center", yanchor="middle", sizex=1.0, sizey=1.0,
            # 'fill' so the portrait alien art covers the landscape radar area
            # (centered crop) instead of shrinking to a tiny centered strip.
            sizing="fill", opacity=0.6 if is_night else 0.4, layer="below")])
    elif RADAR_BG_B64:
        fig.update_layout(images=[dict(
            source=f"data:image/jpeg;base64,{RADAR_BG_B64}",
            xref="paper", yref="paper", x=0.5, y=0.5,
            xanchor="center", yanchor="middle", sizex=1.05, sizey=1.05,
            sizing="contain", opacity=0.22 if is_night else 0.12, layer="below")])


def _add_target_blips(fig, radii, thetas, sizes, colors, labels, custom, hovers, text_size=11):
    """Layered 'locked-on' blips: outer halo ring + glow + solid numbered core.
    customdata is set on every layer so a click anywhere resolves the index."""
    halo_c = [_hex_rgba(c, 0.16) for c in colors]
    glow_c = [_hex_rgba(c, 0.34) for c in colors]
    # outer halo ring
    fig.add_trace(go.Scatterpolar(
        r=radii, theta=thetas, mode="markers",
        marker=dict(size=[s * 2.5 for s in sizes], color="rgba(0,0,0,0)",
                    line=dict(color=halo_c, width=2)),
        customdata=custom, hoverinfo="skip", showlegend=False))
    # soft glow
    fig.add_trace(go.Scatterpolar(
        r=radii, theta=thetas, mode="markers",
        marker=dict(size=[s * 1.6 for s in sizes], color=glow_c,
                    line=dict(color="rgba(0,0,0,0)", width=0)),
        customdata=custom, hoverinfo="skip", showlegend=False))
    # solid numbered core
    fig.add_trace(go.Scatterpolar(
        r=radii, theta=thetas, mode="markers+text",
        text=labels,
        textfont=dict(size=text_size, color="#06110a", family="JetBrains Mono, monospace"),
        textposition="middle center",
        marker=dict(size=sizes, color=colors, opacity=1.0,
                    line=dict(color="rgba(255,255,255,0.9)", width=1.6)),
        customdata=custom, hovertext=hovers, hoverinfo="text", showlegend=False))


def get_strange_signals(force=False):
    """The daily drop of 5 real weird Reddit stories (refreshes once a day,
    or on demand via the Rescan button)."""
    stale = True
    if st.session_state.strange_ts:
        stale = (datetime.now() - st.session_state.strange_ts).total_seconds() > 86400
    if force or stale or not st.session_state.strange_signals:
        with st.spinner("📡 Scanning the fringe for strange signals…"):
            st.session_state.strange_signals = generate_strange_signals(limit=5)
            st.session_state.strange_ts = datetime.now()
        st.session_state.strange_sel = None
    return st.session_state.strange_signals


def ensure_case_file(idx):
    """Lazily build Pugson's full case write-up (+image) for one signal the
    first time it's opened, then cache it back into session state."""
    sigs = st.session_state.strange_signals
    if not (0 <= idx < len(sigs)):
        return None
    if not sigs[idx].get("case_body"):
        with st.spinner("🕵️ Pugson is writing up the case…"):
            sigs[idx] = generate_case_file(sigs[idx])
        st.session_state.strange_signals = sigs
    return sigs[idx]


def render_strange_radar(signals):
    n = len(signals)
    if n == 0:
        return
    max_rank = max((s["rank"] for s in signals), default=1)
    thetas, radii, sizes, colors, hovers, labels, custom = [], [], [], [], [], [], []
    for i, s in enumerate(signals):
        ang = (360.0 / n) * i
        # hottest (rank 1) sits near the centre — "locked on"
        frac = ((s["rank"] - 1) / (max_rank - 1)) if max_rank > 1 else 0.0
        radii.append(0.28 + 0.66 * frac)
        thetas.append(ang)
        sizes.append(40 - 16 * frac)
        colors.append(SIGNAL_TYPE_COLORS.get(s["type"], "#A3FF12"))
        hovers.append(
            f"<b>{s['title'][:64]}</b><br>{s['subreddit']} · {s['type']}"
            "<br><span style='color:#A3FF12'>▸ click to open the case</span>")
        labels.append(str(i + 1))
        custom.append(i)

    is_night = (theme == "night")
    fig = go.Figure()
    _add_radar_bg(fig, is_night)
    # faint sweep pointer
    fig.add_trace(go.Scatterpolar(
        r=[0, 1.05], theta=[0, 52], mode="lines",
        line=dict(color="rgba(163,255,18,0.16)", width=2),
        hoverinfo="skip", showlegend=False))
    # target-lock blips: outer halo + glow + solid numbered core
    _add_target_blips(fig, radii, thetas, sizes, colors, labels, custom, hovers,
                      text_size=11)
    # faint grid so the alien background art reads through cleanly
    grid_c = "rgba(163,255,18,0.06)" if is_night else "rgba(100,80,40,0.10)"
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=False, range=[0, 1.12]),
            angularaxis=dict(visible=True, showticklabels=False,
                             linecolor=grid_c, gridcolor=grid_c, tickcolor=grid_c,
                             nticks=8),
        ),
        height=360, margin=dict(l=30, r=30, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    # Nonce in the key so 'Close story' can fully reset the chart's persisted
    # selection (otherwise Plotly re-fires the old click and re-opens the story).
    event = st.plotly_chart(
        fig, use_container_width=True, on_select="rerun",
        selection_mode="points",
        key=f"strange_radar_chart_{st.session_state.get('radar_nonce', 0)}",
        config={"displayModeBar": False})

    # capture a blip click
    try:
        pts = event["selection"]["points"] if event and event.get("selection") else []
    except Exception:
        pts = []
    if pts:
        cd = pts[0].get("customdata")
        idx = cd[0] if isinstance(cd, list) else cd
        if idx is not None:
            st.session_state.strange_sel = int(idx)

    # selected case file — Pugson's full on-site write-up
    sel = st.session_state.get("strange_sel")
    if sel is not None and 0 <= sel < n:
        s = ensure_case_file(sel) or signals[sel]
        # Close buttons (top + bottom) so a long story can be collapsed in place
        # without scrolling up to the nav.
        if st.button("✕ Close story", key="strange_close_top", use_container_width=True):
            st.session_state.strange_sel = None
            st.session_state.radar_nonce = st.session_state.get("radar_nonce", 0) + 1
            st.rerun()
        render_case_file(s)
        if st.button("✕ Close story", key="strange_close_bottom", use_container_width=True):
            st.session_state.strange_sel = None
            st.session_state.radar_nonce = st.session_state.get("radar_nonce", 0) + 1
            st.rerun()
    else:
        st.markdown(
            "<div style='text-align:center;padding:14px;font-size:12px;color:var(--tx4)'>"
            "Click a blip on the radar (or a file in Classified Files) to open the case.</div>",
            unsafe_allow_html=True)


def render_case_file(s):
    """Render Pugson's full noir case write-up: image, headline, body, source."""
    col = SIGNAL_TYPE_COLORS.get(s["type"], "#A3FF12")
    img = s.get("image_url")
    img_html = ""
    if img:
        img_html = (
            f"<div style='position:relative;border-radius:12px;overflow:hidden;margin-bottom:14px;"
            f"max-height:340px'>"
            f"<img src='{img}' style='width:100%;display:block;object-fit:cover;max-height:340px'/>"
            f"<div style='position:absolute;inset:0;background:linear-gradient(180deg,"
            f"rgba(0,0,0,0) 55%,rgba(0,0,0,0.65) 100%)'></div></div>")
    paras = "".join(
        f"<p style='font-size:13.5px;color:var(--tx2);line-height:1.8;margin:0 0 12px'>{p}</p>"
        for p in (s.get("case_body") or [s.get("summary", "")]))
    st.markdown(
        f"<div style='background:var(--surface);border:1px solid {col}55;"
        f"border-left:3px solid {col};border-radius:14px;padding:18px 20px;margin-top:12px'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'>"
        f"<span style='font-family:JetBrains Mono,monospace;font-size:9px;font-weight:800;color:{col};"
        f"letter-spacing:0.1em;background:{col}1a;padding:3px 9px;border-radius:4px'>📡 {s['type'].upper()} SIGNAL · {s['subreddit']}</span>"
        f"<span style='font-family:JetBrains Mono,monospace;font-size:9px;color:var(--tx4)'>HOT #{s['rank']}</span>"
        f"</div>"
        f"{img_html}"
        f"<div style='font-size:20px;font-weight:800;color:var(--tx1);line-height:1.3;margin-bottom:4px;font-family:Poppins,sans-serif'>{s.get('case_headline') or s['title']}</div>"
        f"<div style='font-family:JetBrains Mono,monospace;font-size:9px;color:var(--tx4);letter-spacing:0.08em;margin-bottom:14px'>FILED BY PUGSON · NOIZE FIELD DESK</div>"
        f"{paras}"
        f"<div style='font-size:11px;color:var(--tx4);border-top:1px solid var(--border);padding-top:10px;margin-top:6px'>"
        f"Original report: <span style='color:{col}'>{s['subreddit']}</span> · Pugson's retelling — read the source for the unfiltered account.</div>"
        f"</div>", unsafe_allow_html=True)
    st.link_button("🔎 Read the original source →", s["permalink"], use_container_width=True)


def render_strange_radar_mini(signals):
    """Compact live Strange-Signals radar for the right rail. Clicking a blip or
    a number jumps to the TREND RADAR tab with that case file open."""
    is_night = (theme == "night")
    _r_lime  = "#A3FF12" if is_night else "#2a5200"
    _radar_bg   = "background:rgba(10,14,20,0.55);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)" if is_night else "background:var(--surface-alt)"
    _radar_shad = ";box-shadow:0 20px 60px rgba(0,0,0,0.45)" if is_night else ""
    _radar_bord = "border:1px solid rgba(163,255,18,0.18)" if is_night else "border:1px solid var(--border-2)"
    _live_glow  = f";text-shadow:0 0 10px {_r_lime}" if is_night else ""
    st.markdown(
        f'<div style="{_radar_bg};{_radar_bord};border-radius:14px;padding:14px 14px 10px;margin-bottom:12px{_radar_shad}">'
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">'
        '<div style="font-size:9px;font-weight:700;color:var(--lime-t);letter-spacing:0.14em;text-transform:uppercase;font-family:JetBrains Mono,monospace">◉ STRANGE SIGNALS</div>'
        f'<span style="font-size:8px;color:var(--lime-t);font-weight:700;font-family:JetBrains Mono,monospace;letter-spacing:0.1em{_live_glow}">LIVE</span>'
        '</div>',
        unsafe_allow_html=True)

    n = len(signals)
    if n == 0:
        st.markdown(
            "<div style='font-family:JetBrains Mono,monospace;font-size:9px;color:var(--tx4);"
            "text-align:center;padding:18px 4px'>No strange signals on the wire.</div></div>",
            unsafe_allow_html=True)
        return

    max_rank = max((s["rank"] for s in signals), default=1)
    thetas, radii, sizes, colors, labels, custom, hovers = [], [], [], [], [], [], []
    for i, s in enumerate(signals):
        frac = ((s["rank"] - 1) / (max_rank - 1)) if max_rank > 1 else 0.0
        radii.append(0.28 + 0.66 * frac)
        thetas.append((360.0 / n) * i)
        sizes.append(26 - 9 * frac)
        colors.append(SIGNAL_TYPE_COLORS.get(s["type"], "#A3FF12"))
        labels.append(str(i + 1))
        custom.append(i)
        hovers.append(f"<b>{s['title'][:60]}</b><br>{s['subreddit']} · {s['type']}")

    fig = go.Figure()
    _add_radar_bg(fig, is_night)
    fig.add_trace(go.Scatterpolar(
        r=[0, 1.05], theta=[0, 52], mode="lines",
        line=dict(color="rgba(163,255,18,0.16)", width=1.5),
        hoverinfo="skip", showlegend=False))
    _add_target_blips(fig, radii, thetas, sizes, colors, labels, custom, hovers,
                      text_size=9)
    # faint grid so the alien background art reads through cleanly
    grid_c = "rgba(163,255,18,0.06)" if is_night else "rgba(100,80,40,0.10)"
    fig.update_layout(
        polar=dict(bgcolor="rgba(0,0,0,0)",
                   radialaxis=dict(visible=False, range=[0, 1.12]),
                   angularaxis=dict(visible=True, showticklabels=False,
                                    linecolor=grid_c, gridcolor=grid_c, tickcolor=grid_c, nticks=8)),
        height=180, margin=dict(l=14, r=14, t=6, b=6),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
    event = st.plotly_chart(
        fig, use_container_width=True, on_select="rerun",
        selection_mode="points", key="strange_radar_mini",
        config={"displayModeBar": False})

    def _open(idx):
        st.session_state.strange_sel = int(idx)
        st.session_state.active_nav = "TREND RADAR"
        st.rerun()

    try:
        pts = event["selection"]["points"] if event and event.get("selection") else []
    except Exception:
        pts = []
    if pts:
        cd = pts[0].get("customdata")
        idx = cd[0] if isinstance(cd, list) else cd
        if idx is not None:
            _open(idx)
    st.markdown("</div>", unsafe_allow_html=True)


def _redact_title(title, keep=3, maxlen=42):
    """Black out most of a title for a 'classified leak' look — keeps the first
    few words as a teaser, redacts the rest with █ blocks."""
    words = title.replace("…", "").split()
    out = []
    for j, w in enumerate(words):
        if j < keep:
            out.append(w)
        else:
            out.append("█" * max(2, min(len(w), 6)))
    s = " ".join(out)
    return (s[:maxlen] + "…") if len(s) > maxlen else s


def render_strange_watchlist(signals):
    """The right-rail 'classified files' panel — a clickable, redacted dossier
    list of today's 5 strange cases. Clicking opens that case file."""
    is_night = (theme == "night")
    _panel = ("background:rgba(10,14,20,0.55);backdrop-filter:blur(20px);"
              "-webkit-backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.08);"
              "box-shadow:0 20px 60px rgba(0,0,0,0.45)"
              if is_night else "background:var(--surface-alt);border:1px solid var(--border)")
    st.markdown(
        "<style>"
        ".st-key-strangefiles{border-radius:14px;padding:12px 12px 8px;margin-top:2px;" + _panel + "}"
        ".st-key-strangefiles [data-testid='stVerticalBlock']{gap:5px}"
        ".st-key-strangefiles button{justify-content:flex-start!important;text-align:left!important;"
        "background:rgba(163,255,18,0.03)!important;border:1px solid var(--border)!important;"
        "border-left:2px solid var(--lime-t)!important;border-radius:8px!important;"
        "padding:7px 10px!important;min-height:0!important}"
        ".st-key-strangefiles button p{font-family:'JetBrains Mono',monospace!important;"
        "font-size:10px!important;font-weight:600!important;color:var(--tx2)!important;"
        "letter-spacing:0.01em!important;text-align:left!important;margin:0!important}"
        ".st-key-strangefiles button:hover{border-color:var(--lime-t)!important;"
        "box-shadow:0 0 14px rgba(163,255,18,0.15)!important}"
        ".st-key-strangefiles button:hover p{color:var(--tx1)!important}"
        "</style>",
        unsafe_allow_html=True)
    with st.container(key="strangefiles"):
        st.markdown(
            "<div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:8px'>"
            "<div style='font-family:JetBrains Mono,monospace;font-size:8px;font-weight:700;color:var(--tx3);letter-spacing:0.14em;text-transform:uppercase'>🔒 CLASSIFIED FILES</div>"
            f"<span style='font-family:JetBrains Mono,monospace;font-size:8px;font-weight:700;color:var(--lime-t);letter-spacing:0.08em'>{len(signals)} OPEN</span>"
            "</div>",
            unsafe_allow_html=True)
        if not signals:
            st.markdown(
                "<div style='font-family:JetBrains Mono,monospace;font-size:9px;color:var(--tx4);"
                "text-align:center;padding:14px 4px'>No files on the wire yet.</div>",
                unsafe_allow_html=True)
            return
        for i, s in enumerate(signals):
            emoji = SIGNAL_TYPE_EMOJI.get(s["type"], "❔")
            label = f"{emoji}  #{s['rank']}  {_redact_title(s['title'])}"
            if st.button(label, key=f"sf_{i}", use_container_width=True):
                st.session_state.strange_sel = i
                st.rerun()


def render_dossier(dossier):
    """Grounded cross-platform digest.
    Desktop: text sections (left) + a thumbnail 'sources' rail (right).
    Mobile : the rail is hidden and each story card pulls its own thumbnail
             inline on the right (Reddit-style) so nothing stacks awkwardly.
    One card markup, two presentations — switched purely by CSS at 640px."""
    sections = dossier.get("sections") or []
    panel    = dossier.get("sites_panel") or []
    query    = dossier.get("query", "")
    if not sections and not panel:
        return

    # Side-thumbs: hidden on desktop (the rail shows images there), shown on
    # mobile. The rail: shown on desktop, hidden on mobile.
    st.markdown("""
    <style>
      .dsr-mbanner,.dsr-mcard{display:none}
      @media (max-width:640px){
        .dsr-mbanner{display:block!important}
        .dsr-mcard{display:block!important}
        .st-key-dossier_rail{display:none!important}
      }
    </style>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <span style="font-size:13px;font-weight:700;color:var(--tx3)">🗞 The Dossier</span>
      <span style="font-size:14px;font-weight:800;color:var(--tx1);font-family:'Poppins',sans-serif">"{query}"</span>
      <span style="font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.08em;text-transform:uppercase">Live · cross-platform</span>
    </div>""", unsafe_allow_html=True)

    left, right = st.columns([7, 3])

    # Group rail thumbnails by platform so mobile can place any leftover image
    # (one with no matching text story) under that platform's section.
    panel_by_platform, shown_urls, done_platforms = {}, set(), set()
    for p in panel:
        panel_by_platform.setdefault(p.get("platform", ""), []).append(p)

    def _mobile_image_card(p, color):
        """A mobile-only full-width image card (hidden on desktop, where the rail
        shows it): image banner + title + its own source."""
        pthumb = p.get("thumb") or ""
        title  = (p.get("title") or "")[:90]
        psrc   = p.get("source") or ""
        purl   = p.get("url") or "#"
        return (
            f'<a href="{purl}" target="_blank" style="text-decoration:none">'
            f'<div class="dsr-mcard" style="background:var(--surface);border:1px solid var(--border);'
            f'border-left:3px solid {color};border-radius:8px;padding:10px 12px;margin-bottom:6px">'
            f'<img src="{pthumb}" loading="lazy" onerror="this.style.display=\'none\'" '
            f'style="width:100%;height:165px;object-fit:cover;border-radius:8px;display:block;margin-bottom:8px"/>'
            f"<div style=\"font-size:12.5px;font-weight:700;color:var(--tx1);font-family:'Poppins',sans-serif;line-height:1.3\">{title}</div>"
            f'<div style="font-size:9px;color:var(--tx4);margin-top:6px;text-transform:uppercase;letter-spacing:0.06em">{psrc}</div>'
            f'</div></a>'
        )

    with left:
        for sec in sections:
            platform = sec.get("platform", "")
            cfg   = PLATFORM_CONFIG.get(platform, {"label": platform, "icon": "•", "color": "#AAFF00"})
            color = cfg["color"]
            done_platforms.add(platform)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:8px;margin:14px 0 8px">
              <span style="font-size:12px;font-weight:800;color:{color};display:inline-flex;align-items:center;gap:6px">{_platform_icon(platform)} {cfg['label'].upper()}</span>
              <span style="font-size:13px;font-weight:700;color:var(--tx1);font-family:'Poppins',sans-serif">{sec.get('heading','')}</span>
            </div>""", unsafe_allow_html=True)
            for s in sec.get("stories", []):
                hl    = (s.get("headline") or "")[:120]
                take  = s.get("take") or ""
                src   = s.get("source") or ""
                url   = s.get("url") or "#"
                thumb = s.get("thumbnail") or ""
                kind  = s.get("thumb_kind", "image")

                text_block = (
                    f"<div style=\"font-size:12.5px;font-weight:700;color:var(--tx1);font-family:'Poppins',sans-serif;line-height:1.3\">{hl}</div>"
                    f'<div style="font-size:11px;color:var(--tx3);margin:3px 0 0;line-height:1.45">{take}</div>'
                    f'<div style="font-size:9px;color:var(--tx4);margin-top:7px;text-transform:uppercase;letter-spacing:0.06em">{src}</div>'
                )

                # Real photo/video thumbnail (YouTube/Reddit) → full-width banner,
                # MOBILE ONLY (on desktop these images live in the right rail).
                # News (logo kind) has no real photo, so it stays clean text.
                mbanner = ""
                if kind == "image" and thumb:
                    shown_urls.add(url)
                    mbanner = (
                        f'<div class="dsr-mbanner" style="margin-top:9px">'
                        f'<img src="{thumb}" loading="lazy" onerror="this.parentNode.style.display=\'none\'" '
                        f'style="width:100%;height:165px;object-fit:cover;border-radius:8px;display:block"/></div>'
                    )

                st.markdown(
                    f'<a href="{url}" target="_blank" style="text-decoration:none">'
                    f'<div style="background:var(--surface);border:1px solid var(--border);'
                    f'border-left:3px solid {color};border-radius:8px;padding:10px 12px;margin-bottom:6px">'
                    f'{text_block}{mbanner}</div></a>',
                    unsafe_allow_html=True)

            # Mobile-only: this platform's leftover thumbnails (no matching story).
            for p in panel_by_platform.get(platform, []):
                if p.get("url") in shown_urls:
                    continue
                shown_urls.add(p.get("url"))
                st.markdown(_mobile_image_card(p, color), unsafe_allow_html=True)

        # Mobile-only: platforms that have thumbnails but no text section at all.
        for platform, imgs in panel_by_platform.items():
            leftovers = [p for p in imgs if p.get("url") not in shown_urls]
            if platform in done_platforms or not leftovers:
                continue
            cfg   = PLATFORM_CONFIG.get(platform, {"label": platform, "icon": "•", "color": "#AAFF00"})
            color = cfg["color"]
            st.markdown(
                f'<div class="dsr-mcard" style="display:flex;align-items:center;gap:8px;margin:14px 0 8px">'
                f'<span style="font-size:12px;font-weight:800;color:{color};display:inline-flex;align-items:center;gap:6px">{_platform_icon(platform)} {cfg["label"].upper()}</span></div>',
                unsafe_allow_html=True)
            for p in leftovers:
                shown_urls.add(p.get("url"))
                st.markdown(_mobile_image_card(p, color), unsafe_allow_html=True)

    with right:
        with st.container(key="dossier_rail"):
            st.markdown(f"""
            <div style="font-size:9px;font-weight:700;color:var(--tx4);text-transform:uppercase;
                        letter-spacing:0.1em;margin:14px 0 8px">📎 {len(panel)} sources</div>""", unsafe_allow_html=True)
            for p in panel:
                pthumb = p.get("thumb") or ""
                title  = (p.get("title") or "")[:80]
                psrc   = p.get("source") or ""
                purl   = p.get("url") or "#"
                thumb_html = (
                    f'<img src="{pthumb}" loading="lazy" onerror="this.style.display=\'none\'" '
                    f'style="width:100%;height:64px;object-fit:cover;border-radius:6px;margin-bottom:5px"/>'
                    if pthumb else ""
                )
                st.markdown(
                    f'<a href="{purl}" target="_blank" style="text-decoration:none">'
                    f'<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px;margin-bottom:7px">'
                    f'{thumb_html}'
                    f'<div style="font-size:11px;font-weight:700;color:var(--tx1);line-height:1.3">{title}</div>'
                    f'<div style="font-size:9px;color:var(--tx4);margin-top:3px">{psrc}</div>'
                    f'</div></a>',
                    unsafe_allow_html=True)

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)


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
              <div style="font-size:12px;font-weight:700;color:{color};display:flex;align-items:center;gap:6px">{_platform_icon(key)} {cfg['label']}</div>
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
# TOP NAV  (replaces the left sidebar — mobile-friendly horizontal bar)
# ═════════════════════════════════════════════════════════════════

NAV_ITEMS = [
    ("📁","CASE FILES",    "Live trend case cards"),
    ("📡","TREND RADAR",   "Velocity & momentum"),
    ("📊","DEEP DIVE",     "Blueprint generator"),
    ("🗂","SOURCES",       "Platform overview"),
    ("⭐","WATCHLIST",     "Saved topics"),
    ("📋","BRIEFINGS",     "Daily intelligence"),
    ("💬","DEBRIEF",       "Chat with Pugson"),
]

active_nav = st.session_state.active_nav

with st.container(key="noizetopnav"):
    pugson_src = f"data:image/jpeg;base64,{PUGSON_B64}" if PUGSON_B64 else ""
    _sb_lime   = "#2a5200" if theme == "day" else "#A3FF12"
    _sb_img_bd = "rgba(42,82,0,0.35)" if theme == "day" else "rgba(163,255,18,0.30)"
    _sb_glow   = "none" if theme == "day" else f"0 0 6px {_sb_lime}"
    img_tag    = (f'<img src="{pugson_src}" style="width:40px;height:40px;border-radius:50%;border:2px solid {_sb_img_bd};object-fit:cover">'
                  if pugson_src else
                  f'<div style="width:40px;height:40px;border-radius:50%;background:var(--surface);border:2px solid {_sb_img_bd};display:flex;align-items:center;justify-content:center;font-size:20px">🐾</div>')

    tog_label = "☀️ DAY" if theme == "night" else "🌙 NIGHT"
    tog_tip   = "Switch to Day" if theme == "night" else "Switch to Night"

    # avatar | 8 nav buttons | theme toggle | upgrade
    top_cols = st.columns([1.6] + [1] * len(NAV_ITEMS) + [1, 1])

    with top_cols[0]:
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:9px;padding:2px 0">
          {img_tag}
          <div style="line-height:1.1">
            <div style="font-size:14px;font-weight:900;color:var(--tx1);font-family:Inter,sans-serif;letter-spacing:-0.3px">PUGSON</div>
            <div style="display:flex;align-items:center;gap:4px;margin-top:1px">
              <span style="width:6px;height:6px;border-radius:50%;background:{_sb_lime};display:inline-block;box-shadow:{_sb_glow}"></span>
              <span style="font-size:8px;color:{_sb_lime};font-weight:700;letter-spacing:0.06em">ONLINE</span>
            </div>
          </div>
        </div>""", unsafe_allow_html=True)

    for i, (icon, label, _) in enumerate(NAV_ITEMS):
        with top_cols[i + 1]:
            btn_type = "primary" if active_nav == label else "secondary"
            if st.button(f"{icon} {label}", key=f"nav_{label}", use_container_width=True, type=btn_type):
                st.session_state.active_nav = label
                st.rerun()

    with top_cols[-2]:
        if st.button(tog_label, key="theme_toggle", help=tog_tip, use_container_width=True, type="secondary"):
            st.session_state.theme = "day" if theme == "night" else "night"
            st.rerun()

    with top_cols[-1]:
        if st.button("🛡️ UPGRADE", key="upgrade_cta", help="Unlock advanced tools, historic data & more", use_container_width=True, type="secondary"):
            st.toast("Command tier coming soon 🛡️")

st.markdown("<div style='border-bottom:1px solid var(--sb-border);margin:2px 0 10px 0'></div>", unsafe_allow_html=True)


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

_hero_img_style = (
    f"position:relative;z-index:2;"
    f"background-image:{hero_overlay},url('data:image/jpeg;base64,{hero_b64}');"
    "background-size:cover;background-position:65% center;"
) if hero_b64 else "position:relative;z-index:2;"

_briefing_panel_bg = (
    f"background-image:{hero_overlay},url('data:image/jpeg;base64,{hero_b64}');"
    "background-size:cover;background-position:right center;"
) if hero_b64 else None

# ── MOBILE-ONLY LAYOUT REORDER ────────────────────────────────────
# On desktop the page is a 7/3 two-column split (main | right rail). Below
# 640px Streamlit stacks the columns, which dumps the whole right rail
# (briefing, radar, classified files) at the very bottom. This CSS — scoped
# to the split block and gated behind @media (max-width:640px) — flattens the
# two columns into one flex column and reorders the blocks so they read:
#   1 Hero · 2 Briefing · 3 Case content · 4 Radar · 5 Classified · 6 Signal index
# Desktop (>640px) gets NO rule and is left exactly as-is.
_SPLIT = '[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-strangefiles)'
st.markdown(
    "<style>@media (max-width:640px){"
    # stack + flatten the two columns so every inner block is a flex item.
    # Tighten the inter-section gap (was 'medium' ~1rem) so stacked cards sit
    # closer and don't leave a roomy void between, e.g., briefing and radar.
    f"{_SPLIT}{{flex-direction:column!important;flex-wrap:nowrap!important;gap:8px!important}}"
    f"{_SPLIT} > [data-testid=\"stColumn\"]{{display:contents!important}}"
    f"{_SPLIT} > [data-testid=\"stColumn\"] > [data-testid=\"stVerticalBlock\"]{{display:contents!important}}"
    # reorder: hero(-3) → blueprint generator(-2) → briefing(-1) → [case content/radar/classified 0] → signal index(1)
    f"{_SPLIT} [data-testid=\"stLayoutWrapper\"]:has(> .st-key-herowrap){{order:-3!important}}"
    f"{_SPLIT} [data-testid=\"stLayoutWrapper\"]:has(> .st-key-srcpanel){{order:-2!important}}"
    f"{_SPLIT} [data-testid=\"stLayoutWrapper\"]:has(> .st-key-briefingwrap){{order:-1!important}}"
    f"{_SPLIT} [data-testid=\"stLayoutWrapper\"]:has(> .st-key-cf_bottom){{order:1!important}}"
    # Hide the redundant 'pick a source' placeholder + its now-orphaned spacer on
    # mobile (the source picker already sits above the briefing here) — they were
    # leaving an empty gap between the briefing and Strange Signals. Hide both the
    # keyed containers and any layout/element wrapper that holds them, so no empty
    # wrapper box is left behind.
    ".st-key-cf_empty,.st-key-cf_spacer{display:none!important}"
    f"{_SPLIT} [data-testid=\"stLayoutWrapper\"]:has(.st-key-cf_empty),"
    f"{_SPLIT} [data-testid=\"stLayoutWrapper\"]:has(.st-key-cf_spacer),"
    f"{_SPLIT} [data-testid=\"stElementContainer\"]:has(.st-key-cf_empty),"
    f"{_SPLIT} [data-testid=\"stElementContainer\"]:has(.st-key-cf_spacer){{display:none!important}}"
    "}</style>",
    unsafe_allow_html=True,
)

# Single centered column: the old right rail (briefing + strange signals) now
# stacks inline in the main feed on the home view (see end of CASE FILES block).
main_col = st.container()

# ── MAIN CONTENT ──────────────────────────────────────────────────
# Rendered BEFORE the right panel so the hero + main content paint first on
# load. The right-panel briefing is appended at the very end of the script
# (Streamlit streams in code order), which keeps the initial load smooth.
with main_col:

    # ── HERO — glassy search + chips overlaid on the city image ──
    # The image is set as the wrapper's background so the real Streamlit
    # widgets render as its children, ON TOP of the image (old look).
    _hero_bg_css = (
        f"background-image:{hero_overlay},url('data:image/jpeg;base64,{hero_b64}');"
        "background-size:cover;background-position:65% center;"
    ) if hero_b64 else "background:var(--surface-alt);"
    st.markdown(
        f"<style>.st-key-herowrap{{{_hero_bg_css}"
        "border-radius:14px;padding:20px 26px 18px 26px;"
        "border:1px solid rgba(255,255,255,0.06);"
        "box-shadow:0 16px 50px rgba(0,0,0,0.45);margin-bottom:12px}</style>",
        unsafe_allow_html=True,
    )
    with st.container(key="herowrap"):
        st.markdown(
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">'
            '<svg width="38" height="38" viewBox="0 0 40 40" fill="none"><rect width="40" height="40" rx="10" fill="rgba(13,21,32,0.7)"/><rect x="7" y="20" width="6" height="12" rx="2" fill="#A3FF12"/><rect x="17" y="11" width="6" height="21" rx="2" fill="#A3FF12"/><rect x="27" y="15" width="6" height="17" rx="2" fill="#A3FF12"/></svg>'
            '<div><div style="font-family:Inter,sans-serif;font-size:28px;font-weight:900;color:#fff;letter-spacing:-1px;line-height:1">Noi<span style="color:#A3FF12;text-shadow:0 0 20px rgba(163,255,18,0.6)">ze</span></div>'
            '<div style="font-size:9px;color:rgba(255,255,255,0.30);letter-spacing:0.22em;text-transform:uppercase;margin-top:1px">Signal in the noise</div>'
            '</div></div>'
            '<div style="font-size:11px;color:rgba(255,255,255,0.40);line-height:1.8;font-family:Inter,sans-serif;margin-bottom:12px">The internet is noisy.&nbsp;·&nbsp;We find what matters.&nbsp;·&nbsp;You stay ahead.</div>',
            unsafe_allow_html=True,
        )

        hcol1, hcol2 = st.columns([4, 1.5], vertical_alignment="center")
        with hcol1:
            hero_topic = st.text_input(
                "hero_topic", placeholder="Investigate any topic, keyword or trend...",
                label_visibility="collapsed", key="hero_topic")
        with hcol2:
            hero_go = st.button("🔍 INVESTIGATE", type="primary", use_container_width=True, key="hero_go")

        st.markdown(
            "<div style='font-size:9px;font-weight:700;color:rgba(255,255,255,0.30);text-transform:uppercase;letter-spacing:0.12em;margin:6px 0 2px'>Popular</div>",
            unsafe_allow_html=True)
        chip_clicked = None
        with st.container(key="herochips"):
            pc_cols = st.columns(len(popular_topics))
            for i, t in enumerate(popular_topics):
                with pc_cols[i]:
                    if st.button(t, key=f"pop_{i}", use_container_width=True, type="secondary"):
                        chip_clicked = t

        if chips_html:
            st.markdown(chips_html, unsafe_allow_html=True)

    # Resolve the query from the search box or a popular chip, run the search.
    _hero_query = None
    if hero_go and hero_topic.strip():
        _hero_query = hero_topic.strip()
    elif chip_clicked:
        _hero_query = chip_clicked
    if _hero_query:
        with st.spinner(f'Scanning all platforms for "{_hero_query}"...'):
            dossier = build_dossier(_hero_query)
            st.session_state.dossier       = dossier
            st.session_state.pulse_results = dossier["cards"]
            st.session_state.pulse_query   = _hero_query
        st.rerun()

    # Show investigation results right under the hero, on any tab.
    if st.session_state.pulse_results and st.session_state.pulse_query:
        _q = st.session_state.pulse_query

        def _make_topic_blueprint():
            with st.spinner(f'Building a content blueprint for "{_q}"...'):
                st.session_state.topic_blueprint = generate_topic_blueprint(_q, st.session_state.dossier)
                st.session_state.topic_bp_query  = _q
            st.session_state.bp_scroll = True   # auto-scroll to it after rerun
            st.rerun()

        def _render_topic_blueprint():
            if st.session_state.topic_blueprint and st.session_state.topic_bp_query == _q:
                # Anchor (scroll-margin clears the sticky nav) the auto-scroll targets.
                st.markdown('<div class="noize-bp-anchor" style="scroll-margin-top:90px"></div>',
                            unsafe_allow_html=True)
                with st.container(border=True):
                    if st.button("✕ Close blueprint", key="bp_close_top", use_container_width=True):
                        st.session_state.topic_blueprint = None
                        st.rerun()
                    st.markdown(st.session_state.topic_blueprint)
                    if st.button("✕ Close blueprint", key="bp_close_bottom", use_container_width=True):
                        st.session_state.topic_blueprint = None
                        st.rerun()
                # After a fresh generation, jump the page to the blueprint.
                if st.session_state.get("bp_scroll"):
                    st.session_state.bp_scroll = False
                    components.html(
                        "<script>setTimeout(function(){"
                        "var a=window.parent.document.querySelector('.noize-bp-anchor');"
                        "if(a)a.scrollIntoView({behavior:'smooth',block:'start'});},150);</script>",
                        height=0,
                    )

        st.markdown("---")
        # TOP: one-click blueprint for the searched topic (grounded in the data
        # we just pulled). Mirrored at the bottom so it's reachable either way.
        if st.button(f'📐 Generate Blueprint for "{_q}"', key="bp_top", type="primary", use_container_width=True):
            _make_topic_blueprint()
        _render_topic_blueprint()

        if st.session_state.dossier:
            render_dossier(st.session_state.dossier)
        render_niche_pulse(st.session_state.pulse_results, st.session_state.pulse_query)

        # BOTTOM: same blueprint action.
        if st.button(f'📐 Generate Blueprint for "{_q}"', key="bp_bottom", type="primary", use_container_width=True):
            _make_topic_blueprint()

        if st.button("✕ Clear results", key="hero_clear"):
            st.session_state.pulse_results = None
            st.session_state.pulse_query   = ""
            st.session_state.dossier       = None
            st.session_state.topic_blueprint = None
            st.rerun()
        st.markdown("---")

    # ── CASE FILES ───────────────────────────────────────────────
    if active_nav == "CASE FILES":
        # Square, icon-only brand buttons inside a themed "TrendFeeds" panel.
        # CSS keeps all 4 on ONE row on both mobile and desktop.
        _bgsel = ".st-key-srcrow [data-testid=\"stColumn\"] button[kind]"  # high specificity + !important to beat Streamlit's `background:` shorthand
        _src_css = "<style>"
        # framed panel: cracked-asphalt photo under a heavy dark theme-tinted overlay (subtle), faint lime glow
        _src_css += (".st-key-srcpanel{"
                     "background-image:linear-gradient(155deg,rgba(8,11,6,0.90),rgba(8,11,6,0.84) 45%,rgba(12,20,4,0.88)),"
                     "url('data:image/jpeg;base64," + ASPHALT_BG_B64 + "')!important;"
                     "background-size:cover!important;background-position:center 35%!important;"
                     "border:1px solid var(--border-2);"
                     "border-radius:14px;padding:11px 14px 13px;margin-bottom:10px;"
                     "box-shadow:inset 0 0 60px rgba(0,0,0,0.45),0 0 0 1px rgba(163,255,18,0.06),0 10px 30px rgba(0,0,0,0.4)}")
        # keep all 4 columns on one row (no mobile stacking)
        _src_css += ".st-key-srcrow [data-testid=\"stHorizontalBlock\"]{flex-wrap:nowrap!important;gap:8px}"
        _src_css += ".st-key-srcrow [data-testid=\"stColumn\"]{min-width:0!important;flex:1 1 0!important}"
        # square shape, capped + centred
        _src_css += (".st-key-srcrow button{display:block!important;aspect-ratio:1!important;width:100%;max-width:86px;margin:0 auto;"
                     "border-radius:14px;padding:0!important}")
        # hide the (accessibility-only) text label
        _src_css += ".st-key-srcrow button p,.st-key-srcrow button div{font-size:0!important;line-height:0!important}"
        # icon background (longhands w/ !important so Streamlit's `background:` shorthand can't reset them)
        _src_css += (_bgsel + "{background-color:var(--surface)!important;background-repeat:no-repeat!important;"
                     "background-position:center!important;background-size:52%!important}")
        # active (selected) state
        _src_css += (".st-key-srcrow [data-testid=\"stColumn\"] button[kind=\"primary\"]{background-color:transparent!important;"
                     "border-color:var(--lime-t)!important;box-shadow:0 0 0 2px var(--lime-border),0 0 16px rgba(163,255,18,0.32)!important}")
        for _k, _svg in PLATFORM_SVG.items():
            _src_css += ".st-key-srcrow .st-key-plat_" + _k + " button[kind]{background-image:url(\"" + _svg + "\")!important}"
        _src_css += "</style>"
        st.markdown(_src_css, unsafe_allow_html=True)
        with st.container(key="srcpanel"):
            # Glowing-green "Content Blueprint Generator" title (Orbitron) + TOP 20 tag + creator tagline.
            st.markdown(
                "<div style='margin-bottom:12px'>"
                "<div style='display:flex;align-items:center;gap:8px;flex-wrap:wrap'>"
                "<span style=\"font-family:'Orbitron',sans-serif;font-weight:800;font-size:12.5px;letter-spacing:0.02em;"
                "color:#0a0f05;background:linear-gradient(135deg,#c8ff5e,#A3FF12);padding:4px 12px;border-radius:8px;"
                "box-shadow:0 0 18px rgba(163,255,18,0.55),0 0 5px rgba(163,255,18,0.9);text-shadow:0 1px 0 rgba(255,255,255,0.25);"
                "text-transform:uppercase\">Content Blueprint Generator</span>"
                "<span style=\"font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:800;letter-spacing:0.14em;"
                "color:var(--lime-t);border:1px solid var(--lime-border);background:var(--lime-bg);padding:3px 8px;"
                "border-radius:6px;text-transform:uppercase\">Top 20</span>"
                "</div>"
                "<div style=\"font-family:'JetBrains Mono',monospace;font-size:9.5px;font-weight:500;line-height:1.5;"
                "letter-spacing:0.03em;color:rgba(233,245,220,0.78);margin-top:7px;text-shadow:0 1px 3px rgba(0,0,0,0.8)\">"
                "Top 20 trends from the top 4 feeds &mdash; pick a source to build your next piece of content.</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            with st.container(key="srcrow"):
                pcols = st.columns(4, gap="small")
                for idx,(key,cfg) in enumerate(PLATFORM_CONFIG.items()):
                    with pcols[idx]:
                        is_active = (active_platform==key)
                        if st.button(cfg['label'],key=f"plat_{key}",use_container_width=True,
                                     type="primary" if is_active else "secondary"):
                            st.session_state.active_platform = key
                            st.session_state.do_fetch = True
                            st.rerun()
        with st.container(key="cf_spacer"):
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        if not active_platform:
            # Welcome — today's top leads live in the Detective Briefing (right rail);
            # this column just prompts the user to pick a source. Wrapped in a keyed
            # container so it can be hidden on mobile, where the source picker already
            # sits above the briefing and this placeholder just leaves an awkward gap.
            with st.container(key="cf_empty"):
                st.markdown(
                    "<div style='text-align:center;padding:18px 16px 10px'>"
                    "<div style='font-size:12px;color:var(--tx3);line-height:1.6'>Pick a source above to open live case files.</div>"
                    "<div style='font-size:10px;color:var(--tx4);margin-top:7px;font-family:JetBrains Mono,monospace;letter-spacing:0.04em'>Today&rsquo;s top leads are in the briefing.</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

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
            st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

            # ── Combined case-file + blueprint picker ──
            # One row per trend: [checkbox + name]  …  [mini case file → opens the story].
            # Replaces the old big-card grid + separate checkbox list (no duplication, no scroll).
            bp_source = velocity_data if velocity_data else hashtags
            if bp_source:
                st.markdown(
                    f"<div style='font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px'>🎬 Build a Blueprint</div>"
                    f"<div style='font-size:11px;color:var(--tx3);margin-bottom:10px;line-height:1.6'>Tick the {_platform_icon(active_platform)} {cfg['label']} trends you want, then generate a production blueprint. Tap any case file to open the story.</div>",
                    unsafe_allow_html=True
                )
                cf_niche = st.text_input("Your niche (optional)", placeholder="e.g. fitness, fashion, food...", key=f"cf_bp_niche_{active_platform}")
                # Keep [checkbox] and [case file] on ONE row even on mobile (Streamlit would stack them).
                st.markdown(
                    "<style>"
                    # Old-city-map blueprint texture behind the topic rows (noir theme)
                    ".st-key-bplist{"
                    "position:relative;border:1px solid var(--border);border-radius:14px;"
                    "padding:14px 14px 16px;overflow:hidden;"
                    "background-color:#070b05;"
                    "background-image:"
                    "radial-gradient(ellipse at 50% 0%,rgba(10,16,5,0.62),rgba(7,11,5,0.90) 72%),"
                    "url('data:image/svg+xml;base64," + OLD_CITY_MAP_B64 + "');"
                    "background-size:cover,140%;"
                    "background-position:center,center;"
                    "box-shadow:inset 0 0 70px rgba(0,0,0,0.55)}"
                    # rows sit above the texture
                    ".st-key-bplist [data-testid=\"stVerticalBlock\"]{position:relative;z-index:1}"
                    ".st-key-bplist [data-testid=\"stHorizontalBlock\"]{flex-wrap:nowrap!important;align-items:center;gap:10px}"
                    ".st-key-bplist [data-testid=\"stColumn\"]{min-width:0!important}"
                    ".st-key-bplist [data-testid=\"stColumn\"]:first-child{flex:1 1 auto!important}"
                    ".st-key-bplist [data-testid=\"stColumn\"]:last-child{flex:0 0 134px!important}"
                    "</style>",
                    unsafe_allow_html=True,
                )
                cf_selected = []
                cf_pfx = "#" if active_platform == "tiktok" else ""
                with st.container(key="bplist"):
                    for i, h in enumerate(bp_source):
                        name = h.get("name","")
                        url  = h.get("url") or f"https://www.google.com/search?q={name}"
                        status_lbl, sc, sb = case_status(h)
                        try:    rank_int = int(str(h.get("current_rank") or h.get("rank") or 10))
                        except: rank_int = 10
                        vel_str, vel_col = velocity_pct_str(h.get("rank_change",0), h.get("is_new",False), rank_int, name)
                        rcol, fcol = st.columns([0.66, 0.34])
                        with rcol:
                            if st.checkbox(f"{cf_pfx}{name}", key=f"cf_bp_{active_platform}_{i}"):
                                cf_selected.append(name)
                        with fcol:
                            st.markdown(
                                f'<a href="{url}" target="_blank" style="text-decoration:none;display:block">'
                                f'<div style="background:var(--surface-2);border:1px solid var(--border);border-left:2px solid {sc};border-radius:8px;padding:6px 9px">'
                                f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">'
                                f'<span style="font-family:JetBrains Mono,monospace;font-size:7px;font-weight:700;color:var(--amber);letter-spacing:0.07em">📄 CASE FILE</span>'
                                f'<span style="font-size:9px;color:{sc}">→</span>'
                                f'</div>'
                                f'<div style="display:flex;align-items:center;justify-content:space-between;gap:6px">'
                                f'<span style="font-family:JetBrains Mono,monospace;font-size:7.5px;font-weight:800;color:{sc};letter-spacing:0.03em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{status_lbl}</span>'
                                f'<span style="font-family:JetBrains Mono,monospace;font-size:10px;font-weight:700;color:{vel_col};white-space:nowrap">{vel_str}</span>'
                                f'</div>'
                                f'</div></a>',
                                unsafe_allow_html=True,
                            )
                if st.button("🎬 Generate Blueprint", type="primary", use_container_width=True,
                             disabled=len(cf_selected) == 0, key=f"cf_gen_bp_{active_platform}"):
                    with st.spinner("Building intelligence file..."):
                        cf_bp = generate_blueprint(cf_selected, cf_niche.strip() or "content creator")
                    st.markdown("---")
                    st.markdown(cf_bp)

        # ── Good Morning Detective + Strange Signals ─────────────────
        # Moved in from the old right rail: now centered in the main feed,
        # under the generator/case files, on the home view only.
        with st.container(key="briefingwrap"):
            render_detective_briefing(articles, panel_bg_override=_briefing_panel_bg)
        _strange = get_strange_signals()
        # 'STRANGE SIGNALS / LIVE' header bar above the radar (restored from the
        # old rail layout — the full radar has no built-in header).
        st.markdown(
            '<div style="display:flex;align-items:center;justify-content:space-between;'
            'background:rgba(10,14,20,0.55);border:1px solid rgba(163,255,18,0.18);'
            'border-radius:14px;padding:12px 16px;margin-bottom:10px">'
            '<span style="font-size:11px;font-weight:700;color:var(--lime-t);letter-spacing:0.16em;'
            'text-transform:uppercase;font-family:JetBrains Mono,monospace">◉ STRANGE SIGNALS</span>'
            '<span style="font-size:10px;color:var(--lime-t);font-weight:700;'
            'font-family:JetBrains Mono,monospace;letter-spacing:0.12em">LIVE</span>'
            '</div>',
            unsafe_allow_html=True)
        render_strange_radar(_strange)
        render_strange_watchlist(_strange)

        # Signal-strength index + quote banner (page footer / radar legend).
        with st.container(key="cf_bottom"):
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

    # ── TREND RADAR ── Strange Signals ──────────────────────────
    elif active_nav == "TREND RADAR":
        hcol, bcol = st.columns([4, 1.2], vertical_alignment="center")
        with hcol:
            st.markdown(
                "<div style='font-size:9px;font-weight:700;color:var(--tx4);letter-spacing:0.12em;"
                "text-transform:uppercase;margin-bottom:2px'>Trend Radar — Strange Signals</div>"
                "<div style='font-size:12px;color:var(--tx3);line-height:1.5'>Live sweep of the internet's "
                "weirdest corners — UFOs, the paranormal, unsolved mysteries &amp; glitches in the matrix. "
                "Click a blip to open the case.</div>",
                unsafe_allow_html=True)
        with bcol:
            if st.button("🔄 Rescan", key="strange_rescan", use_container_width=True):
                get_strange_signals(force=True)
                st.rerun()
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        signals = get_strange_signals()
        if signals:
            render_strange_radar(signals)
        else:
            st.markdown(
                "<div style='text-align:center;padding:40px 16px;font-size:13px;color:var(--tx4)'>"
                "📡 No strange signals on the wire right now. Try a rescan in a moment.</div>",
                unsafe_allow_html=True)

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
              <span style="display:inline-flex;align-items:center">{_platform_icon(key, 24)}</span>
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
