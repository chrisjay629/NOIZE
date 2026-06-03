"""
platforms.py — scrapers for Google Trends, YouTube, and Reddit.
Each returns a list of trend dicts in the same format as TikTok.
Falls back to GPT if the real scrape fails.
"""

import os
import json
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_gpt_json(text):
    """Safely parse GPT response — strips markdown code fences if present."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _gpt_fallback(platform):
    print(f"[{platform.upper()}] Using GPT fallback", flush=True)
    today = datetime.now().strftime("%B %d, %Y")
    prompts = {
        "google": (
            f"Today is {today}. List 20 topics trending on Google Search right now in the US. "
            "Think current events, viral moments, sports, entertainment, pop culture. "
            "Return ONLY a JSON array, no markdown:\n"
            '[{"rank":"1","name":"...","posts":"500K+ searches","category":"News"}]'
        ),
        "youtube": (
            f"Today is {today}. List 20 videos/topics trending on YouTube right now. "
            "Think viral videos, music, news, gaming, sports highlights. "
            "Return ONLY a JSON array, no markdown:\n"
            '[{"rank":"1","name":"...","posts":"4.2M views","category":"Music"}]'
        ),
        "reddit": (
            f"Today is {today}. List 20 topics trending on Reddit r/all right now. "
            "Think viral stories, memes, news, sports, tech, gaming. "
            "Return ONLY a JSON array, no markdown:\n"
            '[{"rank":"1","name":"...","posts":"89K upvotes","category":"r/gaming"}]'
        ),
    }
    url_builders = {
        "google":  lambda n: f"https://www.google.com/search?q={n.replace(' ', '+')}",
        "youtube": lambda n: f"https://www.youtube.com/results?search_query={n.replace(' ', '+')}",
        "reddit":  lambda n: f"https://www.reddit.com/search/?q={n.replace(' ', '+')}&sort=hot",
    }
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompts[platform]}]
        )
        data = _parse_gpt_json(response.choices[0].message.content)
        now = datetime.now().isoformat()
        return [{
            "rank": str(h.get("rank", i + 1)),
            "name": h.get("name", ""),
            "posts": h.get("posts", ""),
            "category": h.get("category", ""),
            "url": url_builders[platform](h.get("name", "")),
            "scraped_at": now,
            "platform": platform,
            "source": "gpt_fallback"
        } for i, h in enumerate(data)]
    except Exception as e:
        print(f"[{platform.upper()}] GPT fallback failed: {e}", flush=True)
        return []


# ── GOOGLE TRENDS ── RSS feed, no API key needed ────────────────

def scrape_google():
    print("[GOOGLE] Starting scrape via RSS", flush=True)
    try:
        r = requests.get(
            "https://trends.google.com/trending/rss?geo=US",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        r.raise_for_status()
        root = ET.fromstring(r.text)
        ns = {"ht": "https://trends.google.com/trending/rss"}
        items = root.findall(".//item")
        if not items:
            raise ValueError("No items in RSS feed")

        results = []
        for i, item in enumerate(items[:20]):
            title_el = item.find("title")
            traffic_el = item.find("ht:approx_traffic", ns)
            name = title_el.text.strip() if title_el is not None and title_el.text else ""
            traffic_str = (traffic_el.text.strip() + " searches") if traffic_el is not None else "Trending"
            results.append({
                "rank": str(i + 1),
                "name": name,
                "posts": traffic_str,
                "category": "Google Trends",
                "url": f"https://www.google.com/search?q={name.replace(' ', '+')}",
                "scraped_at": datetime.now().isoformat(),
                "platform": "google",
                "source": "live"
            })
        print(f"[GOOGLE] Got {len(results)} trends", flush=True)
        return results
    except Exception as e:
        print(f"[GOOGLE] Scrape failed: {e}", flush=True)
        return _gpt_fallback("google")


# ── YOUTUBE ── YouTube Data API v3 ─────────────────────────────

def scrape_youtube():
    print("[YOUTUBE] Starting scrape via Data API v3", flush=True)
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("[YOUTUBE] No API key found — using GPT fallback", flush=True)
        return _gpt_fallback("youtube")
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": "US",
                "maxResults": 20,
                "key": api_key,
            },
            timeout=15
        )
        print(f"[YOUTUBE] API status: {r.status_code}", flush=True)
        if r.status_code != 200:
            print(f"[YOUTUBE] API error response: {r.text[:300]}", flush=True)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        if not items:
            print(f"[YOUTUBE] API returned 0 items. Full response: {r.text[:300]}", flush=True)
            raise ValueError("No items returned from YouTube API")

        results = []
        for i, item in enumerate(items):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            title = snippet.get("title", "")
            channel = snippet.get("channelTitle", "YouTube")
            video_id = item.get("id", "")
            views = int(stats.get("viewCount", 0))
            if views >= 1_000_000:
                views_str = f"{views/1_000_000:.1f}M views"
            elif views >= 1_000:
                views_str = f"{views/1_000:.0f}K views"
            else:
                views_str = f"{views} views"
            results.append({
                "rank": str(i + 1),
                "name": title,
                "posts": views_str,
                "category": channel,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "scraped_at": datetime.now().isoformat(),
                "platform": "youtube",
                "source": "live"
            })
        print(f"[YOUTUBE] Got {len(results)} trending videos", flush=True)
        return results
    except Exception as e:
        print(f"[YOUTUBE] API failed: {e} — using GPT fallback", flush=True)
        return _gpt_fallback("youtube")


# ── REDDIT ── RSS feed, no API key needed ───────────────────────

def scrape_reddit():
    print("[REDDIT] Starting scrape via RSS", flush=True)
    try:
        r = requests.get(
            "https://www.reddit.com/r/all/hot.rss?limit=20",
            headers={"User-Agent": "TrendCenterBot/1.0"},
            timeout=15
        )
        r.raise_for_status()
        root = ET.fromstring(r.text)
        atom_ns = "http://www.w3.org/2005/Atom"
        entries = root.findall(f"{{{atom_ns}}}entry")
        if not entries:
            raise ValueError("No entries in RSS")

        results = []
        for i, entry in enumerate(entries[:20]):
            title_el = entry.find(f"{{{atom_ns}}}title")
            link_el = entry.find(f"{{{atom_ns}}}link")
            category_el = entry.find(f"{{{atom_ns}}}category")
            name = title_el.text.strip() if title_el is not None and title_el.text else ""
            if len(name) > 80:
                name = name[:77] + "..."
            url = link_el.get("href", "") if link_el is not None else ""
            subreddit = category_el.get("term", "r/all") if category_el is not None else "r/all"
            results.append({
                "rank": str(i + 1),
                "name": name,
                "posts": "Hot post",
                "category": subreddit,
                "url": url,
                "scraped_at": datetime.now().isoformat(),
                "platform": "reddit",
                "source": "live"
            })
        print(f"[REDDIT] Got {len(results)} posts", flush=True)
        return results
    except Exception as e:
        print(f"[REDDIT] Scrape failed: {e}", flush=True)
        return _gpt_fallback("reddit")
