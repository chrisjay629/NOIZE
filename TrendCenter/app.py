import sqlite3
import threading
import time
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from agent import run_agent, generate_blueprint, research_niche_hashtags, niche_pulse
from database import get_latest_hashtags, get_hashtag_velocity, init_db, DB_PATH, save_snapshot, cleanup_old_snapshots, get_data_age_minutes
from scraper import scrape_hashtags
from platforms import scrape_google, scrape_youtube, scrape_reddit

PLATFORM_CONFIG = {
    "tiktok":  {"label": "TikTok",        "icon": "🎵", "scraper": scrape_hashtags, "link_label": "↗ TikTok",  "refresh_minutes": 60,  "color": "#fe2c55"},
    "google":  {"label": "Google Trends", "icon": "📈", "scraper": scrape_google,   "link_label": "↗ Google",  "refresh_minutes": 60,  "color": "#4285f4"},
    "youtube": {"label": "YouTube",       "icon": "📺", "scraper": scrape_youtube,  "link_label": "↗ YouTube", "refresh_minutes": 240, "color": "#ff4444"},
    "reddit":  {"label": "Reddit",        "icon": "🔴", "scraper": scrape_reddit,   "link_label": "↗ Reddit",  "refresh_minutes": 60,  "color": "#ff5700"},
}

# ── Process-level scheduler (one thread per Railway instance) ───
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

# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title="TrendCenter",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@700;800;900&display=swap');
  html, body, [class*="css"] { font-family: -apple-system, system-ui, sans-serif; }

  .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: #0f0f15 !important;
  }
  [data-testid="stSidebar"] { background-color: #15151f !important; }
  .block-container { padding: 1.25rem 2rem 2rem 2rem; max-width: 1200px; }

  html, body, p, span, div, label, h1, h2, h3 { color: #e0e0e0; }

  [data-testid="stTabs"] button { color: #aaa !important; font-size: 13px !important; }
  [data-testid="stTabs"] button[aria-selected="true"] { color: #fe2c55 !important; border-bottom-color: #fe2c55 !important; }

  [data-testid="stTextInput"] input {
    background: #1e1e2e !important;
    border: 0.5px solid #3a3a4a !important;
    color: #e0e0e0 !important;
    border-radius: 8px !important;
    font-size: 13px !important;
  }

  hr { border-color: #2a2a3a !important; }

  .ht-card {
    background: #1a1a28;
    border: 0.5px solid #2e2e42;
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 8px;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .ht-card:hover { border-color: #fe2c55; }
  .ht-card * { color: inherit; }
  .ht-card.featured { border: 1.5px solid #185fa5; }
  .ht-card.faded { opacity: 0.55; }

  .badge {
    display: inline-block;
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 5px;
    margin-left: 5px;
    vertical-align: middle;
    font-weight: 600;
  }
  .badge-green  { background: #0f3d2e; color: #3dd68c; }
  .badge-blue   { background: #0d2a4a; color: #60a5fa; }
  .badge-red    { background: #3d1010; color: #f87171; }
  .badge-strike { background: #185fa5; color: #fff; }

  .plat-btn-active {
    background: linear-gradient(135deg, #fe2c55, #c0203d) !important;
    color: #fff !important;
    border: none !important;
  }

  .welcome-state {
    text-align: center;
    padding: 50px 20px;
  }

  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    color: #666;
    padding: 3px 10px;
    background: #1a1a28;
    border: 0.5px solid #2e2e42;
    border-radius: 20px;
  }
  .dot-live { width:7px;height:7px;border-radius:50%;background:#1d9e75;display:inline-block; }
  .dot-gpt  { width:7px;height:7px;border-radius:50%;background:#f5a623;display:inline-block; }

  .stButton > button {
    border-radius: 8px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    transition: all 0.15s !important;
  }
</style>
""", unsafe_allow_html=True)


# ── Session state init ─────────────────────────────────────────
init_db()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "active_platform" not in st.session_state:
    st.session_state.active_platform = None   # No auto-select on load
if "do_fetch" not in st.session_state:
    st.session_state.do_fetch = False
if "nr_results" not in st.session_state:
    st.session_state.nr_results = []
if "nr_topic_label" not in st.session_state:
    st.session_state.nr_topic_label = ""
if "pulse_results" not in st.session_state:
    st.session_state.pulse_results = None
if "pulse_query" not in st.session_state:
    st.session_state.pulse_query = ""


# ── Fetch on platform click ────────────────────────────────────
if st.session_state.do_fetch and st.session_state.active_platform:
    st.session_state.do_fetch = False
    ap = st.session_state.active_platform
    cfg_f = PLATFORM_CONFIG[ap]
    with st.spinner(f"Loading {cfg_f['icon']} {cfg_f['label']} trends..."):
        try:
            results = cfg_f["scraper"]()
            if results:
                save_snapshot(results, platform=ap)
                cleanup_old_snapshots(hours=48)
        except Exception as e:
            st.error(f"Could not load {cfg_f['label']}: {e}")


# ── Helpers ────────────────────────────────────────────────────
def get_snapshot_count():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM hashtag_snapshots")
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def render_velocity_chart(velocity_data, platform="tiktok"):
    if not velocity_data:
        st.markdown("<div style='color:#555;font-size:13px;padding:20px 0;text-align:center'>Not enough data for velocity chart yet.<br>Check back after a second scrape.</div>", unsafe_allow_html=True)
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        top_names = [h["name"] for h in velocity_data[:5]]
        fig = go.Figure()
        has_data = False
        for name in top_names:
            c.execute("""
                SELECT scraped_at, rank FROM hashtag_snapshots
                WHERE name = ? AND platform = ?
                ORDER BY scraped_at ASC
            """, (name, platform))
            rows = c.fetchall()
            if len(rows) < 2:
                continue
            has_data = True
            fig.add_trace(go.Scatter(
                x=[r[0] for r in rows],
                y=[r[1] for r in rows],
                mode="lines+markers",
                name=f"#{name}",
                line=dict(width=2),
                marker=dict(size=5),
            ))
        conn.close()
        if not has_data:
            st.markdown("<div style='color:#555;font-size:13px;padding:20px 0;text-align:center'>Not enough data for velocity chart yet.</div>", unsafe_allow_html=True)
            return
        fig.update_layout(
            yaxis=dict(autorange="reversed", title="Rank", gridcolor="#1e1e2e", color="#555", tickfont=dict(size=10)),
            xaxis=dict(gridcolor="#1e1e2e", color="#555", tickfont=dict(size=9)),
            height=240,
            margin=dict(l=0, r=0, t=4, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    except Exception as e:
        st.warning(f"Chart unavailable: {e}")


def velocity_badge(h):
    change = h.get("rank_change", 0)
    is_new = h.get("is_new", False)
    if is_new:
        return '<span class="badge badge-blue">★ New</span>'
    if change < -3:
        return f'<span class="badge badge-green">↑{abs(change)}</span><span class="badge badge-strike">Strike now</span>'
    if change < 0:
        return f'<span class="badge badge-green">↑{abs(change)}</span>'
    if change > 3:
        return f'<span class="badge badge-red">↓{change}</span>'
    return '<span class="badge badge-blue">— stable</span>'


def render_cards(data, platform="tiktok"):
    if not data:
        st.markdown("<div style='color:#555;font-size:13px;padding:20px 0;text-align:center'>No data yet — click the platform button above to load trends.</div>", unsafe_allow_html=True)
        return
    link_label = PLATFORM_CONFIG.get(platform, {}).get("link_label", "↗ View")
    for h in data:
        change   = h.get("rank_change", 0)
        is_new   = h.get("is_new", False)
        card_cls = "featured" if change < -3 else ("faded" if change > 5 else "")
        badge    = velocity_badge(h)
        category = h.get("category") or "—"
        posts    = h.get("posts") or "—"
        rank     = h.get("current_rank") or h.get("rank") or "—"
        name     = h.get("name", "")
        url      = h.get("url") or f"https://www.google.com/search?q={name}"
        prefix   = "#" if platform == "tiktok" else ""

        posts_label = f"{posts} posts" if platform == "tiktok" else posts

        st.markdown(f"""
        <a href="{url}" target="_blank" style="text-decoration:none">
        <div class="ht-card {card_cls}">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div style="flex:1;min-width:0">
              <span style="font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block">{prefix}{name}</span>
              <div style="font-size:11px;color:#666;margin-top:2px">{posts_label} · {category}</div>
            </div>
            <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;margin-left:10px">
              {badge}
              <span style="font-size:11px;color:#555">#{rank}</span>
            </div>
          </div>
        </div>
        </a>
        """, unsafe_allow_html=True)


def render_niche_pulse(results: dict, query: str):
    """Renders the cross-platform niche pulse grid + chart."""
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <span style="font-size:16px;font-weight:700;color:#ccc">🔍 Niche Pulse:</span>
      <span style="font-size:16px;font-weight:700;color:#fff">"{query}"</span>
      <span style="font-size:11px;color:#444;margin-left:4px">Top 3 trends per platform</span>
    </div>
    """, unsafe_allow_html=True)

    pulse_cols = st.columns(4)
    chart_items = []  # For combined chart

    for idx, (key, cfg) in enumerate(PLATFORM_CONFIG.items()):
        trends = results.get(key, [])
        color  = cfg["color"]
        is_gpt = any(t.get("source") == "gpt_fallback" for t in trends)
        src_label = "🤖 AI suggestions" if is_gpt else "🟢 Live data"

        with pulse_cols[idx]:
            st.markdown(f"""
            <div style="background:{color}18;border:1px solid {color}55;border-radius:10px;padding:10px 12px;margin-bottom:8px">
              <div style="font-size:13px;font-weight:700;color:{color}">{cfg['icon']} {cfg['label']}</div>
              <div style="font-size:10px;color:#555;margin-top:1px">{src_label}</div>
            </div>
            """, unsafe_allow_html=True)

            for t in trends:
                name  = t.get("name", "")
                posts = t.get("posts", "—")
                rank  = t.get("rank") or t.get("current_rank") or "—"
                url   = t.get("url", "#")
                prefix = "#" if key == "tiktok" else ""
                disp_name = name[:22] + ("…" if len(name) > 22 else "")

                st.markdown(f"""
                <a href="{url}" target="_blank" style="text-decoration:none">
                <div style="background:#16161f;border:0.5px solid #2a2a3c;border-radius:8px;padding:8px 10px;margin-bottom:6px;transition:border-color 0.15s"
                     onmouseover="this.style.borderColor='{color}'" onmouseout="this.style.borderColor='#2a2a3c'">
                  <div style="font-size:12px;font-weight:600;color:#ddd">{prefix}{disp_name}</div>
                  <div style="font-size:10px;color:#555;margin-top:2px">{posts}</div>
                </div>
                </a>
                """, unsafe_allow_html=True)

                try:
                    rank_val = int(str(rank).replace("#", "").strip())
                except (ValueError, TypeError):
                    rank_val = 10

                chart_items.append({
                    "label": f"{cfg['icon']} {name[:16]}{'…' if len(name)>16 else ''}",
                    "platform": cfg["label"],
                    "rank": rank_val,
                    "color": color,
                })

    # Combined horizontal bar chart
    if chart_items:
        st.markdown("<div style='font-size:11px;font-weight:700;color:#444;text-transform:uppercase;letter-spacing:0.08em;margin:14px 0 6px 0'>Trend prominence across platforms</div>", unsafe_allow_html=True)

        # Sort by platform order then rank
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
            textfont=dict(size=10, color="#aaa"),
            hovertemplate="%{y}<br>Rank #%{customdata}<extra></extra>",
            customdata=[item["rank"] for item in chart_items],
        ))
        fig.update_layout(
            xaxis=dict(title="Prominence (higher = better ranked)", gridcolor="#1e1e2e", color="#444", tickfont=dict(size=9), range=[0, 24]),
            yaxis=dict(color="#aaa", tickfont=dict(size=10), autorange="reversed"),
            height=max(200, len(chart_items) * 26 + 40),
            margin=dict(l=0, r=40, t=6, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ══════════════════════════════════════════════════════════════
# PAGE LAYOUT
# ══════════════════════════════════════════════════════════════

active_platform = st.session_state.active_platform

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex;align-items:center;gap:12px;padding:0.25rem 0 0.5rem 0">
  <div style="position:relative;width:40px;height:40px;flex-shrink:0">
    <svg width="40" height="40" viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="44" height="44" rx="10" fill="#010101"/>
      <path d="M28.5 10h-4v15.5a4.5 4.5 0 1 1-4.5-4.5c.39 0 .77.05 1.13.14V16.9A9 9 0 1 0 29.5 25.5V17.3a13.4 13.4 0 0 0 6 1.7v-4a9.4 9.4 0 0 1-7-5z" fill="white"/>
      <path d="M28.5 10h-4v15.5a4.5 4.5 0 1 1-4.5-4.5c.39 0 .77.05 1.13.14V16.9A9 9 0 1 0 29.5 25.5V17.3a13.4 13.4 0 0 0 6 1.7v-4a9.4 9.4 0 0 1-7-5z" fill="#fe2c55" opacity="0.5" transform="translate(1,1)"/>
      <path d="M28.5 10h-4v15.5a4.5 4.5 0 1 1-4.5-4.5c.39 0 .77.05 1.13.14V16.9A9 9 0 1 0 29.5 25.5V17.3a13.4 13.4 0 0 0 6 1.7v-4a9.4 9.4 0 0 1-7-5z" fill="#25f4ee" opacity="0.5" transform="translate(-1,-1)"/>
    </svg>
  </div>
  <div>
    <div style="font-family:'Poppins',sans-serif;font-size:24px;font-weight:800;letter-spacing:-0.5px;line-height:1;color:#fff">
      Trend<span style="color:#fe2c55">Center</span>
    </div>
    <div style="font-size:12px;color:#555;margin-top:2px">
      Real-time trends across TikTok · Google · YouTube · Reddit
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Platform Selector ──────────────────────────────────────────
st.markdown("<div style='font-size:11px;font-weight:700;letter-spacing:0.08em;color:#444;text-transform:uppercase;margin-bottom:6px'>Click a platform to load trends</div>", unsafe_allow_html=True)

pcols = st.columns(4)
for idx, (key, cfg) in enumerate(PLATFORM_CONFIG.items()):
    with pcols[idx]:
        is_active = (active_platform == key)
        label = f"🔄 {cfg['icon']} {cfg['label']}" if is_active else f"{cfg['icon']} {cfg['label']}"
        if st.button(label, key=f"plat_{key}", use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state.active_platform = key
            st.session_state.do_fetch = True
            st.rerun()

st.markdown("<div style='margin:8px 0 8px 0;border-top:0.5px solid #2a2a3a'></div>", unsafe_allow_html=True)

# ── Niche Pulse Search (always visible) ───────────────────────
np_col1, np_col2, np_col3 = st.columns([5, 1, 1])
with np_col1:
    pulse_niche = st.text_input(
        "niche_pulse_input",
        placeholder="🔍  Search a niche across all platforms — e.g. pokemon, fitness, cooking...",
        label_visibility="collapsed",
        key="pulse_niche_input"
    )
with np_col2:
    pulse_search = st.button("Analyze All", type="primary", use_container_width=True)
with np_col3:
    if st.button("✕ Clear", use_container_width=True, disabled=not st.session_state.pulse_results):
        st.session_state.pulse_results = None
        st.session_state.pulse_query = ""
        st.rerun()

if pulse_search and pulse_niche.strip():
    with st.spinner(f"Scanning all 4 platforms for '{pulse_niche.strip()}'..."):
        st.session_state.pulse_results = niche_pulse(pulse_niche.strip())
        st.session_state.pulse_query = pulse_niche.strip()

# Show pulse results if active
if st.session_state.pulse_results:
    render_niche_pulse(st.session_state.pulse_results, st.session_state.pulse_query)
    st.markdown("<div style='margin:12px 0;border-top:0.5px solid #2a2a3a'></div>", unsafe_allow_html=True)


# ── Main content ───────────────────────────────────────────────
if not active_platform:
    # Welcome state
    st.markdown("""
    <div style="text-align:center;padding:70px 20px 50px 20px">
      <div style="font-size:52px;margin-bottom:14px">📡</div>
      <div style="font-size:22px;font-weight:700;color:#ccc;margin-bottom:8px">What's trending right now?</div>
      <div style="font-size:14px;color:#555;line-height:1.7;max-width:420px;margin:0 auto">
        Pick a platform above to see the top 20 trends in real time.<br>
        Use the tools below to build content, research niches, or chat with the AI.
      </div>
    </div>
    """, unsafe_allow_html=True)

else:
    hashtags     = get_latest_hashtags(platform=active_platform)
    velocity_data = get_hashtag_velocity(platform=active_platform)
    cfg          = PLATFORM_CONFIG[active_platform]
    color        = cfg["color"]
    is_gpt       = bool(hashtags and hashtags[0].get("source") == "gpt_fallback")
    climbing     = [h for h in velocity_data if h.get("rank_change", 0) < 0]
    new_ones     = [h for h in velocity_data if h.get("is_new")]

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
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
      <div style="font-size:17px;font-weight:700;color:{color}">{cfg['icon']} {cfg['label']}</div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <span class="status-pill"><span class="{dot}"></span>{src}</span>
        <span class="status-pill">🕐 {mins_ago_str}</span>
        <span class="status-pill">📊 {len(hashtags)} trends</span>
        <span class="status-pill">📈 {len(climbing)} climbing</span>
        <span class="status-pill">✨ {len(new_ones)} new</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # GPT warning
    if is_gpt:
        platform_name = cfg["label"]
        st.markdown(f"""
        <div style="background:#1f1500;border:1px solid #f5a623;border-radius:8px;padding:10px 14px;margin-bottom:10px;display:flex;align-items:center;gap:10px">
          <span>⚠️</span>
          <div style="font-size:12px;color:#f5a623;line-height:1.5">
            <b>{platform_name} is temporarily unavailable.</b> Showing AI-generated trend suggestions. Hit 🔄 {platform_name} above to check for live data.
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Side-by-side: chart + cards ────────────────────────────
    left_col, right_col = st.columns([4, 6], gap="large")

    with left_col:
        st.markdown(f"<div style='font-size:12px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px'>Rank velocity</div>", unsafe_allow_html=True)
        render_velocity_chart(velocity_data, platform=active_platform)

    with right_col:
        display_data = velocity_data[:10] if velocity_data else hashtags[:10]
        st.markdown(f"<div style='font-size:12px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px'>Trending now — top 10</div>", unsafe_allow_html=True)
        render_cards(display_data, platform=active_platform)


# ── Feature tabs (always visible) ─────────────────────────────
st.markdown("<div style='margin:16px 0 4px 0;border-top:0.5px solid #2a2a3a'></div>", unsafe_allow_html=True)
tab_bp, tab_niche, tab_chat = st.tabs(["🎬 Blueprint Generator", "🔍 Niche Research", "💬 Ask the Agent"])


# ═══════════════════════════════════════════════════════════════
# BLUEPRINT TAB
# ═══════════════════════════════════════════════════════════════
with tab_bp:
    if not active_platform:
        st.markdown("<div style='color:#555;font-size:14px;padding:20px 0'>Select a platform above first to pick trends for your blueprint.</div>", unsafe_allow_html=True)
    else:
        bp_hashtags = get_latest_hashtags(platform=active_platform)
        cfg_bp = PLATFORM_CONFIG[active_platform]
        if not bp_hashtags:
            st.info(f"No {cfg_bp['label']} trends yet — click 🔄 {cfg_bp['label']} above to load.")
        else:
            st.markdown(f"<div style='font-size:13px;color:#aaa;margin-bottom:12px'>Select trends from <b style='color:{cfg_bp['color']}'>{cfg_bp['icon']} {cfg_bp['label']}</b> to build a content blueprint.</div>", unsafe_allow_html=True)

            bp_niche = st.text_input(
                "Your niche (optional)",
                placeholder="e.g. fitness, fashion, food...",
                key="bp_niche"
            )

            selected = []
            cols = st.columns(2)
            for i, h in enumerate(bp_hashtags):
                with cols[i % 2]:
                    prefix = "#" if active_platform == "tiktok" else ""
                    checked = st.checkbox(f"{prefix}{h['name']}", key=f"bp_{active_platform}_{i}")
                    if checked:
                        selected.append(h['name'])

            st.markdown("---")
            generate_btn = st.button(
                "🎬 Generate Blueprint",
                type="primary",
                use_container_width=True,
                disabled=len(selected) == 0
            )
            if generate_btn and selected:
                niche_label = bp_niche.strip() if bp_niche.strip() else "content creator"
                with st.spinner(f"Building blueprints for {len(selected)} trend(s)..."):
                    blueprint = generate_blueprint(selected, niche_label)
                st.markdown("---")
                st.markdown(blueprint)


# ═══════════════════════════════════════════════════════════════
# NICHE RESEARCH TAB
# ═══════════════════════════════════════════════════════════════
with tab_niche:
    st.markdown("<div style='font-size:13px;color:#aaa;margin-bottom:12px'>Type any topic to find relevant hashtags — even if they're not in the top 20 — then generate a full content blueprint.</div>", unsafe_allow_html=True)

    nr_col1, nr_col2 = st.columns([4, 1])
    with nr_col1:
        nr_topic = st.text_input(
            "Topic",
            placeholder="e.g. pickleball, van life, budget cooking, nail art...",
            label_visibility="collapsed",
            key="nr_topic"
        )
    with nr_col2:
        nr_search = st.button("🔍 Search", type="primary", use_container_width=True)

    if nr_search and nr_topic.strip():
        with st.spinner(f"Researching '{nr_topic}'..."):
            st.session_state["nr_results"] = research_niche_hashtags(nr_topic.strip())
            st.session_state["nr_topic_label"] = nr_topic.strip()

    nr_results = st.session_state.get("nr_results", [])
    nr_topic_label = st.session_state.get("nr_topic_label", "")

    if nr_results:
        st.markdown("---")
        st.markdown(f"**{len(nr_results)} hashtags for: *{nr_topic_label}***")
        st.markdown("<div style='font-size:12px;color:#555;margin-bottom:8px'>Check the ones you want, then generate a blueprint.</div>", unsafe_allow_html=True)

        nr_selected = []
        for h in nr_results:
            competition = h.get("competition", "Medium")
            comp_color = {"Low": "#3dd68c", "Medium": "#fbbf24", "High": "#f87171"}.get(competition, "#aaa")
            comp_bg    = {"Low": "#0f3d2e", "Medium": "#3d2e0f", "High": "#3d0f0f"}.get(competition, "#222")
            content_type = h.get("content_type", "")
            description  = h.get("description", "")
            name = h.get("name", "")

            col_check, col_card = st.columns([0.5, 9.5])
            with col_check:
                checked = st.checkbox("", key=f"nr_{name}", label_visibility="collapsed")
                if checked:
                    nr_selected.append(name)
            with col_card:
                st.markdown(f"""
                <div class="ht-card" style="margin-bottom:6px">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start">
                    <div>
                      <span style="font-size:14px;font-weight:600">#{name}</span>
                      <span class="badge" style="background:{comp_bg};color:{comp_color}">{competition}</span>
                      <span class="badge badge-blue">{content_type}</span>
                      <div style="font-size:11px;color:#555;margin-top:3px">{description}</div>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        nr_generate = st.button(
            "🎬 Generate Blueprint",
            type="primary",
            use_container_width=True,
            disabled=len(nr_selected) == 0,
            key="nr_gen_btn"
        )
        if nr_generate and nr_selected:
            with st.spinner(f"Building blueprints for {len(nr_selected)} hashtag(s)..."):
                blueprint = generate_blueprint(nr_selected, nr_topic_label)
            st.markdown("---")
            st.markdown(blueprint)


# ═══════════════════════════════════════════════════════════════
# CHAT TAB
# ═══════════════════════════════════════════════════════════════
with tab_chat:
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("Ask about trends, your niche, content ideas...")

    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = run_agent(user_msg)
            st.markdown(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})

    if st.session_state.chat_history:
        if st.button("Clear chat", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()
