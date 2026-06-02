import sqlite3
import threading
import time
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from agent import run_agent, generate_blueprint, research_niche_hashtags
from database import get_latest_hashtags, get_hashtag_velocity, init_db, DB_PATH
from scraper import scrape_hashtags

def _background_scheduler():
    print("[SCHEDULER] Background scheduler thread started", flush=True)
    while True:
        print("[SCHEDULER] Beginning scrape...", flush=True)
        try:
            scrape_hashtags()
            print("[SCHEDULER] Scrape completed successfully", flush=True)
        except Exception as e:
            print(f"[SCHEDULER] Scrape FAILED: {e}", flush=True)
        print("[SCHEDULER] Sleeping for 1 hour", flush=True)
        time.sleep(3600)  # 1 hour

if "scheduler_started" not in st.session_state:
    st.session_state.scheduler_started = True
    print("[SCHEDULER] Spawning background scheduler thread", flush=True)
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

  /* Force dark mode always */
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: #0f0f15 !important;
  }
  [data-testid="stSidebar"] { background-color: #15151f !important; }
  .block-container { padding: 1.5rem 2rem; max-width: 1100px; }

  /* All text defaults to light */
  html, body, p, span, div, label, h1, h2, h3 { color: #e0e0e0; }

  /* Metric cards */
  [data-testid="metric-container"] {
    background: #1e1e2e !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    border: 0.5px solid #3a3a4a !important;
  }
  [data-testid="metric-container"] label { color: #aaa !important; font-size: 13px !important; }
  [data-testid="metric-container"] [data-testid="stMetricValue"] { color: #fff !important; font-size: 28px !important; font-weight: 700 !important; }

  /* Tabs */
  [data-testid="stTabs"] button { color: #aaa !important; }
  [data-testid="stTabs"] button[aria-selected="true"] { color: #fe2c55 !important; border-bottom-color: #fe2c55 !important; }

  /* Input box */
  [data-testid="stTextInput"] input {
    background: #1e1e2e !important;
    border: 0.5px solid #3a3a4a !important;
    color: #e0e0e0 !important;
    border-radius: 8px !important;
  }

  /* Dividers */
  hr { border-color: #2a2a3a !important; }
  .ht-card {
    background: #1e1e2e;
    border: 0.5px solid #3a3a4a;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 10px;
    color: #e0e0e0 !important;
  }
  .ht-card * { color: inherit; }
  .ht-card.featured { border: 2px solid #185fa5; }
  .ht-card.faded { opacity: 0.6; }
  .badge {
    display: inline-block;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 6px;
    margin-left: 6px;
    vertical-align: middle;
  }
  .badge-green  { background: #e1f5ee; color: #0f6e56; }
  .badge-blue   { background: #e6f1fb; color: #0c447c; }
  .badge-red    { background: #faece7; color: #993c1d; }
  .badge-strike { background: #185fa5; color: #fff; }
  .bubble-user {
    background: #e6f1fb;
    color: #0c447c;
    padding: 10px 14px;
    border-radius: 12px;
    max-width: 70%;
    margin-left: auto;
    margin-bottom: 8px;
    font-size: 14px;
  }
  .bubble-agent {
    background: #1e1e1e;
    border: 0.5px solid #444;
    color: #e0e0e0;
    padding: 10px 14px;
    border-radius: 12px;
    max-width: 80%;
    margin-bottom: 8px;
    font-size: 14px;
    white-space: pre-wrap;
  }
  .status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #1d9e75;
    margin-right: 6px;
  }
</style>
""", unsafe_allow_html=True)


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


def render_velocity_chart(velocity_data):
    if not velocity_data:
        st.info("No velocity data yet — run the scheduler for at least 2 scrapes.")
        return

    # Build per-hashtag rank history from DB
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # Top 5 hashtags from velocity (new ones + climbers first)
        top_names = [h["name"] for h in velocity_data[:5]]
        fig = go.Figure()
        for name in top_names:
            c.execute("""
                SELECT scraped_at, rank FROM hashtag_snapshots
                WHERE name = ?
                ORDER BY scraped_at ASC
            """, (name,))
            rows = c.fetchall()
            if len(rows) < 2:
                continue
            times = [r[0] for r in rows]
            ranks = [r[1] for r in rows]
            fig.add_trace(go.Scatter(
                x=times, y=ranks,
                mode="lines+markers",
                name=f"#{name}",
                line=dict(width=2),
            ))
        conn.close()
        fig.update_layout(
            yaxis=dict(autorange="reversed", title="Rank (lower = better)"),
            xaxis=dict(title="Time"),
            height=280,
            margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
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
        return f'<span class="badge badge-green">↑ {abs(change)} ranks</span><span class="badge badge-strike">Strike now</span>'
    if change < 0:
        return f'<span class="badge badge-green">↑ {abs(change)} ranks</span>'
    if change > 3:
        return f'<span class="badge badge-red">↓ {change} ranks</span>'
    return '<span class="badge badge-blue">— stable</span>'


def render_hashtag_cards(velocity_data):
    if not velocity_data:
        st.info("No data yet. Hit **Refresh** to scrape TikTok.")
        return
    for i, h in enumerate(velocity_data):
        change = h.get("rank_change", 0)
        is_new = h.get("is_new", False)
        card_class = "featured" if (change < -3) else ("faded" if change > 5 else "")
        badge = velocity_badge(h)
        category = h.get("category") or "Uncategorized"
        posts = h.get("posts") or "—"
        rank = h.get("current_rank") or "—"
        name = h['name']
        web_url = f"https://www.tiktok.com/tag/{name}"
        app_url = f"tiktok://tag/{name}"
        onclick = (
            f"(function(e){{"
            f"var m=/Android|iPhone|iPad|iPod/i.test(navigator.userAgent);"
            f"if(m){{e.preventDefault();"
            f"window.location.href='{app_url}';"
            f"setTimeout(function(){{window.location.href='{web_url}';}},1500);}}"
            f"}})(event)"
        )
        st.markdown(f"""
        <a href="{web_url}" target="_blank" style="text-decoration:none" onclick="{onclick}">
        <div class="ht-card {card_class}" style="cursor:pointer;transition:border-color 0.2s" onmouseover="this.style.borderColor='#fe2c55'" onmouseout="this.style.borderColor=''">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <span style="font-size:16px;font-weight:600">#{name}</span>
              {badge}
              <div style="font-size:12px;color:#aaa;margin-top:4px">{posts} posts · {category}</div>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:11px;color:#fe2c55">↗ TikTok</span>
              <span style="font-size:13px;font-weight:500;color:#aaa">#{rank}</span>
            </div>
          </div>
        </div>
        </a>
        """, unsafe_allow_html=True)


# ── Init ───────────────────────────────────────────────────────
init_db()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ── Header ─────────────────────────────────────────────────────
hashtags = get_latest_hashtags()
mins_ago_str = ""
if hashtags:
    last_scraped = hashtags[0].get("scraped_at", "")
    try:
        ts = datetime.fromisoformat(last_scraped)
        mins_ago = int((datetime.now() - ts).total_seconds() / 60)
        mins_ago_str = f'<span class="status-dot"></span><span style="font-size:13px;color:#777">Updated {mins_ago}m ago</span>'
    except Exception:
        pass

st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;padding:0.5rem 0 0.25rem 0">
  <div style="display:flex;align-items:center;gap:12px">
    <div style="position:relative;width:44px;height:44px">
      <svg width="44" height="44" viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="44" height="44" rx="10" fill="#010101"/>
        <path d="M28.5 10h-4v15.5a4.5 4.5 0 1 1-4.5-4.5c.39 0 .77.05 1.13.14V16.9A9 9 0 1 0 29.5 25.5V17.3a13.4 13.4 0 0 0 6 1.7v-4a9.4 9.4 0 0 1-7-5z" fill="white"/>
        <path d="M28.5 10h-4v15.5a4.5 4.5 0 1 1-4.5-4.5c.39 0 .77.05 1.13.14V16.9A9 9 0 1 0 29.5 25.5V17.3a13.4 13.4 0 0 0 6 1.7v-4a9.4 9.4 0 0 1-7-5z" fill="#fe2c55" opacity="0.5" transform="translate(1,1)"/>
        <path d="M28.5 10h-4v15.5a4.5 4.5 0 1 1-4.5-4.5c.39 0 .77.05 1.13.14V16.9A9 9 0 1 0 29.5 25.5V17.3a13.4 13.4 0 0 0 6 1.7v-4a9.4 9.4 0 0 1-7-5z" fill="#25f4ee" opacity="0.5" transform="translate(-1,-1)"/>
      </svg>
    </div>
    <span style="font-family:'Poppins',sans-serif;font-size:28px;font-weight:800;letter-spacing:-0.5px;color:#fff">
      Trend<span style="color:#fe2c55">Center</span>
    </span>
  </div>
  <div style="text-align:right">{mins_ago_str}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div style="background:#1e1e2e;border:0.5px solid #3a3a4a;border-radius:12px;padding:20px 24px;margin-bottom:0.5rem">
  <div style="font-size:12px;font-weight:700;letter-spacing:0.1em;color:#fe2c55;text-transform:uppercase;margin-bottom:4px">Built for TikTok content creators</div>
  <div style="font-size:14px;color:#ccc;line-height:1.6">
    TrendCenter tracks what's trending on TikTok in real time, tells you which hashtags are climbing fastest, and builds you a full content plan — so you always know what to post and how to make it.
  </div>
</div>
""", unsafe_allow_html=True)

card_style = "background:#1e1e2e;border:0.5px solid #3a3a4a;border-radius:10px;padding:14px 16px;height:100%"
label_style = "font-size:11px;font-weight:700;letter-spacing:0.1em;color:#fe2c55;text-transform:uppercase;margin-bottom:6px"
body_style = "font-size:13px;color:#aaa;line-height:1.6"

oc1, oc2 = st.columns(2)
with oc1:
    st.markdown(f"""
    <div style="{card_style}">
      <div style="{label_style}">📊 Dashboard</div>
      <div style="{body_style}">Hit <b style="color:#e0e0e0">Refresh</b> to load the latest top 20 trending hashtags. Type your niche and hit <b style="color:#e0e0e0">Analyze</b> for AI-filtered results. Watch the velocity leaderboard — <b style="color:#185fa5">Strike now</b> means post today before it peaks. Tap any card to view it live on TikTok.</div>
    </div>
    """, unsafe_allow_html=True)
with oc2:
    st.markdown(f"""
    <div style="{card_style}">
      <div style="{label_style}">🎬 Blueprint Generator</div>
      <div style="{body_style}">Pick hashtags from the top 20 using checkboxes, hit <b style="color:#e0e0e0">Generate Blueprint</b>, and get a full production plan — hook, script outline, visual style, ready-to-paste caption, best time to post, and which tool to use.</div>
    </div>
    """, unsafe_allow_html=True)

oc3, oc4 = st.columns(2)
with oc3:
    st.markdown(f"""
    <div style="{card_style}">
      <div style="{label_style}">🔍 Niche Research</div>
      <div style="{body_style}">Not in the top 20? Type any topic — pickleball, van life, budget cooking — and the AI finds 15 relevant hashtags with competition level and best content format. Select what you want and generate a blueprint instantly.</div>
    </div>
    """, unsafe_allow_html=True)
with oc4:
    st.markdown(f"""
    <div style="{card_style}">
      <div style="{label_style}">💬 Ask the Agent</div>
      <div style="{body_style}">Chat with the AI in plain English. Ask what's blowing up right now, which hashtags to avoid, or get content strategy advice for your specific niche. No forms — just talk.</div>
    </div>
    """, unsafe_allow_html=True)

st.divider()


# ── Tabs ───────────────────────────────────────────────────────
tab_dash, tab_blueprint, tab_niche, tab_chat = st.tabs(["📊 Dashboard", "🎬 Blueprint Generator", "🔍 Niche Research", "💬 Ask the Agent"])


# ═══════════════════════════════════════════════════════════════
# DASHBOARD TAB
# ═══════════════════════════════════════════════════════════════
with tab_dash:

    col_input, col_btn, col_scrape = st.columns([4, 1, 1])
    with col_input:
        niche = st.text_input(
            "Your niche",
            placeholder="e.g. fitness, fashion, sports, cooking...",
            label_visibility="collapsed"
        )
    with col_btn:
        analyze = st.button("Analyze", type="primary", use_container_width=True)
    with col_scrape:
        if st.button("🔄 Refresh", use_container_width=True):
            print("[REFRESH] Manual refresh triggered", flush=True)
            with st.spinner("Scraping TikTok Creative Center..."):
                scrape_hashtags()
            print("[REFRESH] Manual refresh completed", flush=True)
            st.success("Data refreshed!")
            st.rerun()

    st.markdown("---")

    # Metrics
    velocity_data = get_hashtag_velocity()
    all_hashtags = get_latest_hashtags()
    climbing = [h for h in velocity_data if h.get("rank_change", 0) < 0]
    new_ones = [h for h in velocity_data if h.get("is_new")]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tracked", len(all_hashtags))
    m2.metric("Climbing ↑", len(climbing))
    m3.metric("New Entries", len(new_ones))
    m4.metric("DB Snapshots", get_snapshot_count())

    st.markdown("---")

    # Velocity chart
    st.markdown("**Rank velocity — all scrapes**")
    render_velocity_chart(velocity_data)

    st.markdown("---")

    # Recommendations or leaderboard
    if analyze and niche:
        st.markdown(f"**Recommendations for: *{niche}***")
        with st.spinner("Agent is analyzing trends..."):
            answer = run_agent(
                f"I make {niche} content. What hashtags should I use right now? "
                "For each relevant one, give me 3 content ideas."
            )
        st.markdown(answer)

    else:
        st.markdown("**Trending now — velocity leaderboard**")
        render_hashtag_cards(velocity_data[:10] if velocity_data else all_hashtags[:10])


# ═══════════════════════════════════════════════════════════════
# BLUEPRINT TAB
# ═══════════════════════════════════════════════════════════════
with tab_blueprint:
    st.markdown("**Select the hashtags you want a content blueprint for:**")

    bp_hashtags = get_latest_hashtags()
    if not bp_hashtags:
        st.info("No hashtags yet — hit Refresh on the Dashboard first.")
    else:
        bp_niche = st.text_input(
            "Your niche (optional)",
            placeholder="e.g. fitness, fashion, food...",
            key="bp_niche"
        )

        selected = []
        cols = st.columns(2)
        for i, h in enumerate(bp_hashtags):
            with cols[i % 2]:
                checked = st.checkbox(f"#{h['name']}", key=f"bp_{h['name']}")
                if checked:
                    selected.append(h['name'])

        st.markdown("---")
        generate_btn = st.button("🎬 Generate Blueprint", type="primary", use_container_width=True, disabled=len(selected) == 0)

        if generate_btn and selected:
            niche_label = bp_niche.strip() if bp_niche.strip() else "content creator"
            with st.spinner(f"Building blueprints for {len(selected)} hashtag(s)..."):
                blueprint = generate_blueprint(selected, niche_label)
            st.markdown("---")
            st.markdown(blueprint)


# ═══════════════════════════════════════════════════════════════
# NICHE RESEARCH TAB
# ═══════════════════════════════════════════════════════════════
with tab_niche:
    st.markdown("**Search any topic to find relevant TikTok hashtags — even if they're not in the top 20.**")
    st.markdown("<div style='font-size:13px;color:#aaa;margin-bottom:1rem'>Type a niche or topic, see which hashtags fit it, then generate a full content blueprint for the ones you want.</div>", unsafe_allow_html=True)

    nr_col1, nr_col2 = st.columns([4, 1])
    with nr_col1:
        nr_topic = st.text_input("Topic", placeholder="e.g. pickleball, van life, budget cooking, nail art...", label_visibility="collapsed", key="nr_topic")
    with nr_col2:
        nr_search = st.button("🔍 Search", type="primary", use_container_width=True)

    if nr_search and nr_topic.strip():
        with st.spinner(f"Researching hashtags for '{nr_topic}'..."):
            st.session_state["nr_results"] = research_niche_hashtags(nr_topic.strip())
            st.session_state["nr_topic_label"] = nr_topic.strip()

    nr_results = st.session_state.get("nr_results", [])
    nr_topic_label = st.session_state.get("nr_topic_label", "")

    if nr_results:
        st.markdown("---")
        st.markdown(f"**{len(nr_results)} hashtags found for: *{nr_topic_label}***")
        st.markdown("<div style='font-size:13px;color:#aaa;margin-bottom:0.75rem'>Check the ones you want to create content for, then hit Generate Blueprint.</div>", unsafe_allow_html=True)

        nr_selected = []
        for h in nr_results:
            competition = h.get("competition", "Medium")
            comp_color = {"Low": "#0f6e56", "Medium": "#7a5c00", "High": "#993c1d"}.get(competition, "#555")
            comp_bg = {"Low": "#e1f5ee", "Medium": "#fef9e7", "High": "#faece7"}.get(competition, "#333")
            content_type = h.get("content_type", "")
            description = h.get("description", "")
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
                      <span style="font-size:15px;font-weight:600">#{name}</span>
                      <span class="badge" style="background:{comp_bg};color:{comp_color};margin-left:8px">{competition} competition</span>
                      <span class="badge badge-blue" style="margin-left:4px">{content_type}</span>
                      <div style="font-size:12px;color:#aaa;margin-top:4px">{description}</div>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        nr_generate = st.button("🎬 Generate Blueprint", type="primary", use_container_width=True, disabled=len(nr_selected) == 0, key="nr_gen_btn")

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

    if st.button("Clear chat"):
        st.session_state.chat_history = []
        st.rerun()
