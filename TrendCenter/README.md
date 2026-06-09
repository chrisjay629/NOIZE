# 🛰️ Noize — *Signal in the Noise*

**A real-time trend-intelligence command center that turns what's happening across the internet into ready-to-shoot content — fast.**

Built for content creators: pick a trend and instantly get the angle, the script, when to post, how to post, the tools to use, and the AI prompts to generate it — all in one window, so you stop scrolling ten sites and start shipping.

**Live app:** https://imaginative-dedication-production.up.railway.app

> Themed as a noir detective dashboard (your AI partner, *Chief Detective Pugson*), Noize reads the static of the internet so you only see the signal.

---

## What is Noize?

The internet never shuts up — millions of posts, clips and threads every minute, most of it pure static. Noize listens to all of it across multiple platforms, surfaces what's *actually* trending with **real, linked sources**, and hands creators a finished game plan for turning any trend into content.

It's part live-news terminal, part content strategist, part curiosities desk — wrapped in a single dark "intelligence dashboard."

### Why it's different
- **⚡ Faster, more efficient** — go from a trend to a ready-to-shoot piece in minutes, not an afternoon of research.
- **🗂 Everything in one window** — the news, the script, the timing, the tools, and the AI prompts. No tab-hopping.
- **✅ Real, grounded intel** — cards link to real publisher articles (Google News redirects are decoded to the true source). No invented headlines.
- **🎯 Honest by design** — when something is AI-generated, it's clearly labeled.

---

## What's inside

| Feature | What it does |
|---|---|
| **🔍 Investigate** | Type any topic → a live cross-platform **Dossier** + a ready content **Blueprint** for it. |
| **📡 Trending Now** | An image-first live feed of real stories across Politics, Tech, AI, Business, Music, Space, Science & Gaming — each card opens the actual article. |
| **🎬 Content Blueprint Generator** | Turn any trend into a **multi-platform** game plan (TikTok / Shorts / Reels / YouTube / X) with beat-by-beat script, shot list, on-screen text, posting times, tool stack, and a **copy-paste AI Prompt Pack**. |
| **🛸 Strange Signals / Classified Files** | The internet's weirdest unsolved files (UFOs, cold cases, glitches), declassified fresh daily with AI-written dossiers + generated art. |
| **📋 Daily Briefings** | A daily intelligence drop of the top stories, packaged and ready to act on. |

### The AI Prompt Pack
Every blueprint ships with copy-paste prompts you drop straight into your AI tools:
- 🖼 **Thumbnail** — a detailed image prompt (Midjourney / DALL·E / GPT-image)
- ✍️ **Titles & captions** — a GPT prompt that returns 10 scroll-stopping options
- 📝 **Full script** — a GPT prompt that expands the beats into a word-for-word script
- 🎙 **Voiceover / AI avatar** — tone + delivery direction (ElevenLabs / HeyGen)

---

## How to use it (the field manual)

1. **Chase a lead** — type a topic into **Investigate** and hit the button. Noize sweeps every platform and builds a Dossier + blueprint on the spot.
2. **Work a source** — tap **Google · YouTube · Reddit · GPT**, scan the Top 20, select the trends you want, and hit **Generate Blueprint**.
3. **Read the wire** — scroll **Trending Now** for the live feed; tap a card to open the real story.
4. **Crack the weird ones** — open **Classified Files** for the daily strange-signal dossiers.
5. **Steal the AI Prompt Pack** — paste the blueprint's prompts into your AI tools.
6. **Hit the Briefing Room** — the **Briefings** tab is your daily intelligence drop.

---

## How it works

```
            Google News RSS · YouTube Data API · Reddit · Google Trends · GPT
                                       │
                  platforms.py  ── per-source scrapers + the Trending Now engine
                                     (RSS → decode Google redirect → real og:image),
                                     parallelized & cached
                                       │
                  agent.py      ── OpenAI logic: cross-platform Dossier,
                                     multi-platform Blueprints + AI Prompt Pack,
                                     Strange Signals (text + generated images)
                                       │
                  database.py   ── SQLite snapshots + rank-velocity tracking
                                       │
                  app.py        ── Streamlit dashboard (single dark intelligence UI)
                                       │
            Shared server-side caches  ── trending_cache.json (hourly),
                                          strange_cache.json (daily)
```

### A few engineering highlights
- **Real article resolution (free, no API key):** Google News RSS gives headlines but only redirect links. Noize decodes those via Google's `batchexecute` endpoint to the true publisher URL, then fetches the article's `og:image` — so cards show real photos and link to real stories, with a graceful category-tinted fallback when a publisher blocks server-side fetches.
- **Shared caching:** the Trending Now feed and the daily Strange Signals drop are generated **once** and shared across all visitors (hourly / daily), so the expensive work happens once per period, not per session.
- **Velocity tracking:** every scrape is timestamped; rank movement over time powers the "what's accelerating" signals.
- **Honest AI:** GPT-sourced content is labeled as AI, never disguised as live data.

---

## Tech stack

- **Python 3.9+** · **Streamlit** (UI) · **Plotly** (charts)
- **OpenAI API** — `gpt-4o-mini` (Dossiers, Blueprints, Strange Signals text) + `gpt-image-1-mini` (case-file art)
- **Google News RSS · YouTube Data API v3 · Reddit · Google Trends** — live data
- **SQLite** — zero-setup storage + velocity history
- **requests / ElementTree** — fetching & parsing
- **Railway** — deployment & hosting

---

## Running locally

```bash
# Install dependencies
pip3 install -r requirements.txt

# Add your keys
echo "OPENAI_API_KEY=your_key_here"  > .env
echo "YOUTUBE_API_KEY=your_key_here" >> .env   # optional, enables the live YouTube feed

# Run the app
python3 -m streamlit run app.py
```

The first visit warms the shared caches (~10s); after that it's instant for everyone until the next refresh window.

---

## Notes
- `strange_cache.json`, `trending_cache.json`, `trends.db` and `.env` are local artifacts and are git-ignored.
- Costs are tiny: most data is free RSS/API; OpenAI calls run on `gpt-4o-mini`, and the daily Strange Signals art is ~5 images/day total thanks to the shared cache.

---

*Built as a complete, shipped product — from live data plumbing to a cohesive, themed UI. 🕵️‍♂️*
