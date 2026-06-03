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
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600;700;800;900&display=swap');
  html, body, [class*="css"] { font-family: -apple-system, system-ui, sans-serif; }

  .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: #0a0a12 !important;
  }
  [data-testid="stSidebar"] { background-color: #0f0f1a !important; }
  .block-container { padding: 0 2rem 2rem 2rem; max-width: 1200px; }

  html, body, p, span, div, label, h1, h2, h3 { color: #e0e0e0; }

  /* Tabs */
  [data-testid="stTabs"] button { color: #666 !important; font-size: 13px !important; font-weight: 600 !important; }
  [data-testid="stTabs"] button[aria-selected="true"] { color: #fe2c55 !important; border-bottom-color: #fe2c55 !important; }

  /* Inputs */
  [data-testid="stTextInput"] input {
    background: #13131e !important;
    border: 1px solid #2a2a3a !important;
    color: #e0e0e0 !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    padding: 10px 14px !important;
  }
  [data-testid="stTextInput"] input:focus {
    border-color: #fe2c55 !important;
    box-shadow: 0 0 0 2px rgba(254,44,85,0.15) !important;
  }

  hr { border-color: #1e1e2e !important; }

  /* Old cards (kept for blueprint/niche tabs) */
  .ht-card {
    background: #13131e;
    border: 0.5px solid #252535;
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 8px;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .ht-card:hover { border-color: #fe2c55; }
  .ht-card * { color: inherit; }
  .ht-card.featured { border: 1.5px solid #185fa5; }
  .ht-card.faded { opacity: 0.5; }

  /* Badges */
  .badge {
    display: inline-block;
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 5px;
    margin-left: 5px;
    vertical-align: middle;
    font-weight: 700;
    letter-spacing: 0.02em;
  }
  .badge-green  { background: #0f3d2e; color: #3dd68c; }
  .badge-blue   { background: #0d2a4a; color: #60a5fa; }
  .badge-red    { background: #3d1010; color: #f87171; }
  .badge-strike { background: #185fa5; color: #fff; }

  /* Status pills */
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    color: #555;
    padding: 3px 10px;
    background: #13131e;
    border: 0.5px solid #252535;
    border-radius: 20px;
  }
  .dot-live { width:6px;height:6px;border-radius:50%;background:#1d9e75;display:inline-block; }
  .dot-gpt  { width:6px;height:6px;border-radius:50%;background:#f5a623;display:inline-block; }

  /* Buttons */
  .stButton > button {
    border-radius: 10px !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    letter-spacing: 0.01em !important;
    transition: all 0.15s !important;
  }

  /* Trend chip pills (for quick-select trending topics) */
  .trend-chip {
    display: inline-block;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 12px;
    color: #aaa;
    cursor: pointer;
    transition: all 0.15s;
    text-decoration: none;
  }
  .trend-chip:hover { background: rgba(254,44,85,0.15); border-color: rgba(254,44,85,0.4); color: #fe2c55; }

  /* Section labels */
  .section-label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #444;
    text-transform: uppercase;
    margin-bottom: 8px;
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
        st.markdown("<div style='color:#444;font-size:13px;padding:30px 0;text-align:center'>No data yet — click the platform button above to load trends.</div>", unsafe_allow_html=True)
        return

    cfg     = PLATFORM_CONFIG.get(platform, {})
    color   = cfg.get("color", "#fe2c55")
    link_lbl = cfg.get("link_label", "↗ View")
    prefix  = "#" if platform == "tiktok" else ""

    for h in data:
        change   = h.get("rank_change", 0)
        is_new   = h.get("is_new", False)
        badge    = velocity_badge(h)
        category = h.get("category") or "—"
        posts    = h.get("posts") or "—"
        rank_raw = h.get("current_rank") or h.get("rank") or 10
        name     = h.get("name", "")
        url      = h.get("url") or f"https://www.google.com/search?q={name}"
        posts_label = f"{posts} posts" if platform == "tiktok" else posts

        try:
            rank_int = int(str(rank_raw))
        except (ValueError, TypeError):
            rank_int = 10

        # Progress bar — rank 1=100%, rank 20=5%
        bar_pct = max(5, int((21 - rank_int) / 20 * 100))

        # Rank circle style: top 3 filled, 4-10 outlined, 11+ grey
        if rank_int <= 3:
            circle_bg     = color
            circle_color  = "#fff"
            circle_border = color
        elif rank_int <= 10:
            circle_bg     = f"{color}22"
            circle_color  = color
            circle_border = f"{color}66"
        else:
            circle_bg     = "#1a1a26"
            circle_color  = "#555"
            circle_border = "#333"

        # Card opacity for falling trends
        card_opacity = "0.55" if change > 5 else "1"
        # Highlight border for fast climbers
        card_border = f"1.5px solid {color}88" if change < -3 else "0.5px solid #252535"

        st.markdown(f"""
        <a href="{url}" target="_blank" style="text-decoration:none">
        <div style="background:#13131e;border:{card_border};border-radius:14px;
                    padding:14px 16px;margin-bottom:9px;
                    display:flex;align-items:center;gap:14px;
                    cursor:pointer;opacity:{card_opacity};
                    transition:all 0.15s"
             onmouseover="this.style.borderColor='{color}';this.style.transform='translateY(-1px)';this.style.boxShadow='0 4px 20px {color}22'"
             onmouseout="this.style.borderColor='';this.style.transform='translateY(0)';this.style.boxShadow='none'">

          <!-- Rank circle -->
          <div style="width:42px;height:42px;border-radius:50%;
                      background:{circle_bg};border:2px solid {circle_border};
                      display:flex;align-items:center;justify-content:center;
                      font-family:'Poppins',sans-serif;font-weight:800;font-size:13px;
                      color:{circle_color};flex-shrink:0">
            {rank_int}
          </div>

          <!-- Main content -->
          <div style="flex:1;min-width:0">
            <div style="font-size:15px;font-weight:700;color:#f0f0f0;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
                        margin-bottom:2px;font-family:'Poppins',sans-serif">
              {prefix}{name}
            </div>
            <div style="font-size:11px;color:#555;margin-bottom:7px">
              {posts_label} &nbsp;·&nbsp; {category}
            </div>
            <!-- Prominence bar (like YouGov's Fame bar) -->
            <div style="height:3px;background:#1e1e2a;border-radius:3px">
              <div style="height:3px;width:{bar_pct}%;
                          background:linear-gradient(90deg,{color},{color}55);
                          border-radius:3px"></div>
            </div>
          </div>

          <!-- Right: badge + link -->
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:5px;flex-shrink:0;padding-left:6px">
            <div>{badge}</div>
            <span style="font-size:11px;color:{color};font-weight:600">{link_lbl}</span>
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
                rank_raw = t.get("rank") or t.get("current_rank") or 10
                url   = t.get("url", "#")
                prefix = "#" if key == "tiktok" else ""
                disp_name = name[:20] + ("…" if len(name) > 20 else "")
                try:
                    rank_int = int(str(rank_raw))
                except (ValueError, TypeError):
                    rank_int = 10
                bar_pct = max(5, int((21 - rank_int) / 20 * 100))

                st.markdown(f"""
                <a href="{url}" target="_blank" style="text-decoration:none">
                <div style="background:#13131e;border:0.5px solid #252535;border-radius:10px;
                            padding:10px 12px;margin-bottom:6px;transition:all 0.15s"
                     onmouseover="this.style.borderColor='{color}';this.style.transform='translateY(-1px)'"
                     onmouseout="this.style.borderColor='#252535';this.style.transform='translateY(0)'">
                  <div style="font-size:13px;font-weight:700;color:#eee;
                              white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
                              font-family:'Poppins',sans-serif">{prefix}{disp_name}</div>
                  <div style="font-size:10px;color:#444;margin:3px 0 6px 0">{posts}</div>
                  <div style="height:2px;background:#1e1e2a;border-radius:2px">
                    <div style="height:2px;width:{bar_pct}%;background:{color};border-radius:2px;opacity:0.7"></div>
                  </div>
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

# ── Header — gradient hero ─────────────────────────────────────
# Collect top trends for chips
_chip_data = []
if active_platform:
    _chip_data = get_latest_hashtags(platform=active_platform)[:5]

chip_html = ""
if _chip_data:
    chips = "".join([
        f'<a href="{h.get("url","#")}" target="_blank" class="trend-chip">'
        f'{"#" if active_platform=="tiktok" else ""}{h["name"]}</a>'
        for h in _chip_data
    ])
    chip_html = f'<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center"><span style="font-size:11px;color:#444;font-weight:700;letter-spacing:0.08em;text-transform:uppercase">Trending</span>{chips}</div>'

st.markdown(f"""
<div style="background:linear-gradient(135deg,#1a0830 0%,#0f0a1e 40%,#0a0a12 100%);
            border-radius:0 0 20px 20px;
            padding:22px 24px 20px 24px;
            margin:-1rem -2rem 16px -2rem;
            position:relative;overflow:hidden">

  <!-- Decorative glow blobs -->
  <div style="position:absolute;top:-40px;right:60px;width:200px;height:200px;
              background:radial-gradient(circle,rgba(254,44,85,0.12) 0%,transparent 70%);
              pointer-events:none"></div>
  <div style="position:absolute;bottom:-60px;left:100px;width:160px;height:160px;
              background:radial-gradient(circle,rgba(37,244,238,0.07) 0%,transparent 70%);
              pointer-events:none"></div>

  <div style="display:flex;align-items:center;gap:14px;position:relative">
    <div style="position:relative;width:44px;height:44px;flex-shrink:0">
      <svg width="44" height="44" viewBox="0 0 44 44" fill="none">
        <rect width="44" height="44" rx="11" fill="#010101"/>
        <path d="M28.5 10h-4v15.5a4.5 4.5 0 1 1-4.5-4.5c.39 0 .77.05 1.13.14V16.9A9 9 0 1 0 29.5 25.5V17.3a13.4 13.4 0 0 0 6 1.7v-4a9.4 9.4 0 0 1-7-5z" fill="white"/>
        <path d="M28.5 10h-4v15.5a4.5 4.5 0 1 1-4.5-4.5c.39 0 .77.05 1.13.14V16.9A9 9 0 1 0 29.5 25.5V17.3a13.4 13.4 0 0 0 6 1.7v-4a9.4 9.4 0 0 1-7-5z" fill="#fe2c55" opacity="0.55" transform="translate(1,1)"/>
        <path d="M28.5 10h-4v15.5a4.5 4.5 0 1 1-4.5-4.5c.39 0 .77.05 1.13.14V16.9A9 9 0 1 0 29.5 25.5V17.3a13.4 13.4 0 0 0 6 1.7v-4a9.4 9.4 0 0 1-7-5z" fill="#25f4ee" opacity="0.55" transform="translate(-1,-1)"/>
      </svg>
    </div>
    <div>
      <div style="font-family:'Poppins',sans-serif;font-size:26px;font-weight:900;
                  letter-spacing:-0.5px;line-height:1;color:#fff">
        Trend<span style="color:#fe2c55">Center</span>
      </div>
      <div style="font-size:12px;color:#555;margin-top:3px">
        Real-time trends · TikTok &nbsp;·&nbsp; Google &nbsp;·&nbsp; YouTube &nbsp;·&nbsp; Reddit
      </div>
    </div>
  </div>

  {chip_html}
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
tab_all, tab_bp, tab_niche, tab_chat = st.tabs(["🌐 All Platforms", "🎬 Blueprint Generator", "🔍 Niche Research", "💬 Ask the Agent"])


# ═══════════════════════════════════════════════════════════════
# ALL PLATFORMS TAB
# ═══════════════════════════════════════════════════════════════
with tab_all:
    st.markdown("<div style='font-size:13px;color:#aaa;margin-bottom:14px'>Type any topic and see the top 3 trending stories or hashtags from <b style='color:#ccc'>all 4 platforms</b> at once. Falls back to AI if a platform has no live data.</div>", unsafe_allow_html=True)

    ap_col1, ap_col2 = st.columns([5, 1])
    with ap_col1:
        ap_topic = st.text_input(
            "topic",
            placeholder="e.g. pokemon, elections, fitness, Taylor Swift, AI...",
            label_visibility="collapsed",
            key="ap_topic"
        )
    with ap_col2:
        ap_search = st.button("🔍 Search", type="primary", use_container_width=True, key="ap_search_btn")

    if ap_search and ap_topic.strip():
        with st.spinner(f"Scanning TikTok · Google · YouTube · Reddit for \"{ap_topic.strip()}\"..."):
            st.session_state.pulse_results = niche_pulse(ap_topic.strip())
            st.session_state.pulse_query   = ap_topic.strip()

    if st.session_state.pulse_results and st.session_state.pulse_query:
        st.markdown("---")
        render_niche_pulse(st.session_state.pulse_results, st.session_state.pulse_query)
        if st.button("✕ Clear results", key="ap_clear"):
            st.session_state.pulse_results = None
            st.session_state.pulse_query   = ""
            st.rerun()
    elif not st.session_state.pulse_results:
        st.markdown("""
        <div style="text-align:center;padding:40px 20px">
          <div style="font-size:36px;margin-bottom:10px">🌐</div>
          <div style="font-size:15px;font-weight:600;color:#aaa;margin-bottom:6px">Search any topic</div>
          <div style="font-size:13px;color:#555">Type a topic above and hit Search to see what's trending across all platforms right now.</div>
        </div>
        """, unsafe_allow_html=True)


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
