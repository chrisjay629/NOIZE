# TrendCenter

A TikTok hashtag intelligence tool that helps creators identify trending hashtags, track velocity (which ones are climbing fast), and generate content ideas — powered by an AI agent.

**Live app:** https://imaginative-dedication-production.up.railway.app

---

## What it does

- Scrapes the top 20 trending hashtags from TikTok Creative Center every hour
- Tracks rank movement over time so you can see which hashtags are accelerating
- Filters hashtags by your niche using GPT (understands context, not just keywords)
- Generates 3 content ideas per hashtag tailored to your niche
- Displays everything in a web dashboard with a chat interface

---

## How to use it

### Dashboard tab
1. Hit **Refresh** to pull the latest trending hashtags
2. Type your niche (e.g. `fitness`, `fashion`, `cooking`) and hit **Analyze**
3. The agent will filter the trending hashtags for your niche and generate content ideas
4. The velocity leaderboard shows all trending hashtags ranked — ones marked **Strike now** are climbing fastest

### Ask the Agent tab
Talk to the agent directly in plain English. Examples:
- "What hashtags are blowing up right now?"
- "I make sports content, what should I post today?"
- "Which hashtags are fading that I should avoid?"

---

## How it works

### Architecture

```
TikTok Creative Center
        ↓
   scraper.py          Pulls top 20 trending hashtags via HTTP + BeautifulSoup
        ↓
   database.py         Stores snapshots in SQLite with timestamps
        ↓
   agent.py            OpenAI agent with 4 tools:
                         - get_trending_hashtags
                         - filter_by_niche (GPT-powered semantic matching)
                         - generate_content_ideas
                         - get_velocity (rank movement over time)
        ↓
   app.py              Streamlit web UI (dashboard + chat)
```

### Key files

| File | Purpose |
|------|---------|
| `scraper.py` | Scrapes TikTok Creative Center, saves to JSON + SQLite |
| `database.py` | SQLite storage, velocity calculations, 48h auto-cleanup |
| `agent.py` | OpenAI tool-calling agent loop |
| `scheduler.py` | Standalone hourly scheduler (for local use) |
| `app.py` | Streamlit web app with background scraping thread |

### Velocity tracking
Every scrape is timestamped. The velocity engine compares each hashtag's current rank to its earliest recorded rank and computes the change. Negative rank change = climbing (lower rank number = more trending). Hashtags are sorted by biggest movers first.

### Niche filtering
Instead of simple keyword matching, `filter_by_niche` sends all current hashtags to GPT and asks it to identify which ones are genuinely relevant to the user's niche — catching semantic matches like `#prom` for fashion even though "fashion" isn't in the name.

---

## Running locally

```bash
# Install dependencies
pip3 install -r requirements.txt

# Add your OpenAI API key
echo "OPENAI_API_KEY=your_key_here" > .env

# Run the web app
python3 -m streamlit run app.py

# Or run just the CLI agent
python3 agent.py

# Or run the hourly scheduler in the background
python3 scheduler.py
```

---

## Tech stack

- **Python 3.9+**
- **OpenAI API** (gpt-4o-mini) — agent reasoning + niche filtering + content ideas
- **BeautifulSoup** — HTML scraping
- **SQLite** — local database, zero setup
- **Streamlit** — web UI
- **Plotly** — velocity chart
- **Railway** — deployment and hosting

---

## Cost

- Scraping TikTok Creative Center: free
- OpenAI API calls: ~$0.0002–0.0005 per agent query (gpt-4o-mini)
- Railway hosting: free trial, then ~$5/month
