import sqlite3
import threading
import time
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from agent import run_agent
from database import get_latest_hashtags, get_hashtag_velocity, init_db, DB_PATH
from scraper import scrape_hashtags

def _background_scheduler():
    while True:
        try:
            scrape_hashtags()
        except Exception:
            pass
        time.sleep(3600)  # 1 hour

if "scheduler_started" not in st.session_state:
    st.session_state.scheduler_started = True
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
  html, body, [class*="css"] { font-family: -apple-system, system-ui, sans-serif; }
  .block-container { padding: 1.5rem 2rem; max-width: 1100px; }
  [data-testid="metric-container"] {
    background: #f5f4ef;
    border-radius: 10px;
    padding: 12px 16px;
    border: 0.5px solid #e0ddd5;
  }
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
        st.markdown(f"""
        <div class="ht-card {card_class}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <span style="font-size:16px;font-weight:600">#{h['name']}</span>
              {badge}
              <div style="font-size:12px;color:#aaa;margin-top:4px">{posts} posts · {category}</div>
            </div>
            <div style="font-size:13px;font-weight:500;color:#aaa">#{rank}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)


# ── Init ───────────────────────────────────────────────────────
init_db()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ── Header ─────────────────────────────────────────────────────
col_logo, col_status = st.columns([3, 1])
with col_logo:
    st.markdown("## 📈 TrendCenter")
with col_status:
    hashtags = get_latest_hashtags()
    if hashtags:
        last_scraped = hashtags[0].get("scraped_at", "")
        try:
            ts = datetime.fromisoformat(last_scraped)
            mins_ago = int((datetime.now() - ts).total_seconds() / 60)
            st.markdown(
                f'<div style="text-align:right;padding-top:1rem">'
                f'<span class="status-dot"></span>'
                f'<span style="font-size:13px;color:#777">Updated {mins_ago}m ago</span></div>',
                unsafe_allow_html=True
            )
        except Exception:
            pass

st.markdown("""
<div style="background:#1e1e2e;border:0.5px solid #3a3a4a;border-radius:12px;padding:18px 22px;margin-bottom:1rem">
  <div style="font-size:15px;font-weight:600;color:#e0e0e0;margin-bottom:6px">Built for TikTok content creators</div>
  <div style="font-size:13px;color:#aaa;line-height:1.7">
    TrendCenter tracks the top 20 trending hashtags on TikTok in real time and shows you which ones are climbing fastest —
    so you know exactly what to post and when to post it.<br><br>
    <b style="color:#ccc">How to use it:</b><br>
    &nbsp;&nbsp;1. Hit <b style="color:#ccc">Refresh</b> to pull the latest trending hashtags from TikTok.<br>
    &nbsp;&nbsp;2. Type your niche (fitness, fashion, food, etc.) and hit <b style="color:#ccc">Analyze</b> — the AI filters the trends for you and generates content ideas.<br>
    &nbsp;&nbsp;3. Check the <b style="color:#ccc">velocity leaderboard</b> to see which hashtags are climbing right now. <b style="color:#185fa5">Strike now</b> = post today before it peaks.<br>
    &nbsp;&nbsp;4. Use the <b style="color:#ccc">Ask the Agent</b> tab to chat directly — ask what's trending, what to post, or what to avoid.
  </div>
</div>
""", unsafe_allow_html=True)

st.divider()


# ── Tabs ───────────────────────────────────────────────────────
tab_dash, tab_chat = st.tabs(["📊 Dashboard", "💬 Ask the Agent"])


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
            with st.spinner("Scraping TikTok Creative Center..."):
                scrape_hashtags()
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
