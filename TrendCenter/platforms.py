"""
platforms.py — scrapers for Google Trends, YouTube, and Reddit.
Each function returns a list of trend dicts in the same format as TikTok.
Falls back to GPT if the real scrape fails.
"""

import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def _today():
    return datetime.now().strftime("%B %d, %Y")

def _gpt_fallback(platform, context=""):
    """Generic GPT fallback for any platform."""
    print(f"[{platform.upper()}] Using GPT fallback", flush=True)
    today = _today()
    prompts = {
        "google": (
            f"Today is {today}. Generate a list of 20 topics that are trending on Google Search right now. "
            "Think current events, viral moments, sports, entertainment, pop culture. "
            "For each provide: rank (1-20), name (the search term), posts (search volume like '2.1M searches'), "
            "category (News, Sports, Entertainment, Tech, Lifestyle, etc). "
            "Return ONLY a valid JSON array:\n"
            '[{"rank":"1","name":"...","posts":"...","category":"..."}]'
        ),
        "youtube": (
            f"Today is {today}. Generate a list of 20 topics that are trending on YouTube right now. "
            "Think viral videos, trending creators, music videos, news events, gaming, sports highlights. "
            "For each provide: rank (1-20), name (the video topic/title), posts (view count like '4.2M views'), "
            "category (Music, Gaming, News, Sports, Entertainment, Comedy, Education, etc). "
            "Return ONLY a valid JSON array:\n"
            '[{"rank":"1","name":"...","posts":"...","category":"..."}]'
        ),
        "reddit": (
            f"Today is {today}. Generate a list of 20 topics that are trending on Reddit right now. "
            "Think top posts from r/all — viral stories, memes, news, sports, tech, gaming. "
            "For each provide: rank (1-20), name (the post topic), posts (upvotes like '89K upvotes'), "
            "category (the subreddit like r/gaming, r/news, r/worldnews, r/funny, etc). "
            "Return ONLY a valid JSON array:\n"
            '[{"rank":"1","name":"...","posts":"...","category":"..."}]'
        ),
    }
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompts[platform]}]
        )
        data = json.loads(response.choices[0].message.content)
        now = datetime.now().isoformat()
        urls = {
            "google": lambda n: f"https://www.google.com/search?q={n.replace(' ', '+')}",
            "youtube": lambda n: f"https://www.youtube.com/results?search_query={n.replace(' ', '+')}",
            "reddit": lambda n: f"https://www.reddit.com/search/?q={n.replace(' ', '+')}&sort=hot",
        }
        return [{
            "rank": str(h.get("rank", i+1)),
            "name": h.get("name", ""),
            "posts": h.get("posts", ""),
            "category": h.get("category", ""),
            "url": urls[platform](h.get("name", "")),
            "scraped_at": now,
            "platform": platform,
            "source": "gpt_fallback"
        } for i, h in enumerate(data)]
    except Exception as e:
        print(f"[{platform.upper()}] GPT fallback failed: {e}", flush=True)
        return []


# ── GOOGLE TRENDS ───────────────────────────────────────────────

def scrape_google():
    print("[GOOGLE] Starting scrape", flush=True)
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        df = pytrends.trending_searches(pn="united_states")
        if df is None or df.empty:
            raise ValueError("Empty response from pytrends")

        trends = df[0].tolist()[:20]
        now = datetime.now().isoformat()
        results = []
        for i, term in enumerate(trends):
            results.append({
                "rank": str(i + 1),
                "name": term,
                "posts": "Trending",
                "category": "Google Trends",
                "url": f"https://trends.google.com/trends/explore?q={term.replace(' ', '%20')}&geo=US",
                "scraped_at": now,
                "platform": "google",
                "source": "live"
            })
        print(f"[GOOGLE] Got {len(results)} trends", flush=True)
        return results
    except Exception as e:
        print(f"[GOOGLE] Scrape failed: {e}", flush=True)
        return _gpt_fallback("google")


# ── YOUTUBE TRENDING ────────────────────────────────────────────

def scrape_youtube():
    print("[YOUTUBE] Starting scrape", flush=True)
    try:
        url = "https://www.youtube.com/feed/trending"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()

        # YouTube embeds page data as JSON in a ytInitialData script tag
        import re
        match = re.search(r'var ytInitialData = ({.*?});</script>', r.text, re.DOTALL)
        if not match:
            raise ValueError("Could not find ytInitialData")

        data = json.loads(match.group(1))
        # Navigate to the trending video list
        tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
        items = tabs[0]["tabRenderer"]["content"]["sectionListRenderer"]["contents"]

        results = []
        rank = 1
        for section in items:
            videos = section.get("itemSectionRenderer", {}).get("contents", [])
            for v in videos:
                vr = v.get("videoRenderer") or v.get("reelItemRenderer")
                if not vr:
                    continue
                title = vr.get("title", {})
                name = title.get("runs", [{}])[0].get("text", "") or title.get("simpleText", "")
                if not name:
                    continue
                views = vr.get("viewCountText", {}).get("simpleText", "") or \
                        vr.get("viewCountText", {}).get("runs", [{}])[0].get("text", "")
                video_id = vr.get("videoId", "")
                owner = vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
                category = owner or "YouTube"
                results.append({
                    "rank": str(rank),
                    "name": name,
                    "posts": views or "Trending",
                    "category": category,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "scraped_at": datetime.now().isoformat(),
                    "platform": "youtube",
                    "source": "live"
                })
                rank += 1
                if rank > 20:
                    break
            if rank > 20:
                break

        if not results:
            raise ValueError("No videos parsed from YouTube")

        print(f"[YOUTUBE] Got {len(results)} trending videos", flush=True)
        return results
    except Exception as e:
        print(f"[YOUTUBE] Scrape failed: {e}", flush=True)
        return _gpt_fallback("youtube")


# ── REDDIT TRENDING ─────────────────────────────────────────────

def scrape_reddit():
    print("[REDDIT] Starting scrape", flush=True)
    try:
        url = "https://www.reddit.com/r/all/hot.json?limit=20"
        headers = {**HEADERS, "Accept": "application/json"}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        posts = data["data"]["children"]

        results = []
        for i, post in enumerate(posts[:20]):
            p = post["data"]
            name = p.get("title", "")[:80]  # cap title length
            upvotes = p.get("score", 0)
            if upvotes >= 1000:
                upvotes_str = f"{upvotes/1000:.1f}K upvotes"
            else:
                upvotes_str = f"{upvotes} upvotes"
            subreddit = f"r/{p.get('subreddit', 'all')}"
            post_url = f"https://www.reddit.com{p.get('permalink', '')}"
            results.append({
                "rank": str(i + 1),
                "name": name,
                "posts": upvotes_str,
                "category": subreddit,
                "url": post_url,
                "scraped_at": datetime.now().isoformat(),
                "platform": "reddit",
                "source": "live"
            })

        print(f"[REDDIT] Got {len(results)} posts", flush=True)
        return results
    except Exception as e:
        print(f"[REDDIT] Scrape failed: {e}", flush=True)
        return _gpt_fallback("reddit")
