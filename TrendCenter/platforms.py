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


# ── STRANGE SIGNALS ── real weird/unexplained posts from Reddit JSON ──

# Subreddit → signal "type" used for radar colour/sector.
STRANGE_SUBS = {
    "HighStrangeness":    "Strange",
    "UFOs":               "UFO",
    "aliens":             "UFO",
    "Paranormal":         "Paranormal",
    "Ghosts":             "Paranormal",
    "UnresolvedMysteries":"Unsolved",
    "Glitch_in_the_Matrix":"Glitch",
    "cryptids":           "Cryptid",
    "Thetruthishere":     "Paranormal",
}


def scrape_strange_signals(limit=12):
    """Pull real hot posts from high-strangeness subreddits via Reddit's RSS
    feed (the JSON endpoint is blocked for bots). Returns dicts with real
    titles, subreddits and direct permalinks, in hot order (rank 1 = hottest)."""
    subs = "+".join(STRANGE_SUBS.keys())
    url = f"https://www.reddit.com/r/{subs}/hot.rss?limit=60"
    ns = "http://www.w3.org/2005/Atom"
    try:
        r = requests.get(url, headers={"User-Agent": "TrendCenterBot/1.0"}, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        items, seen = [], set()
        for e in root.findall(f"{{{ns}}}entry"):
            t = e.find(f"{{{ns}}}title")
            l = e.find(f"{{{ns}}}link")
            c = e.find(f"{{{ns}}}category")
            cont = e.find(f"{{{ns}}}content")
            title = (t.text or "").strip() if t is not None else ""
            key = title.lower()
            if not title or key in seen:
                continue
            seen.add(key)
            sub = c.get("term") if c is not None else ""
            link = l.get("href") if l is not None else ""
            raw = cont.text if (cont is not None and cont.text) else ""
            # Pull a real image from the post's RSS content HTML if one exists.
            image_url = ""
            if raw:
                imgs = re.findall(r'<img[^>]+src="([^"]+)"', raw)
                for src in imgs:
                    src = src.replace("&amp;", "&")
                    # prefer real reddit-hosted media/preview images over icons
                    if any(d in src for d in (
                        "preview.redd.it", "i.redd.it", "external-preview.redd.it",
                        "b.thumbs.redditmedia.com", "a.thumbs.redditmedia.com")):
                        image_url = src
                        break
                if not image_url and imgs:
                    image_url = imgs[0].replace("&amp;", "&")
            body = ""
            if raw:
                body = re.sub(r"<[^>]+>", " ", raw)                 # strip HTML
                body = re.split(r"submitted by", body)[0]           # drop RSS boilerplate
                body = re.sub(r"\s+", " ", body).strip()
            items.append({
                "title": title[:160],
                "subreddit": f"r/{sub}",
                "type": STRANGE_SUBS.get(sub, "Strange"),
                "rank": len(items) + 1,
                "permalink": link,
                "selftext": body[:400],
                "image_url": image_url,
                "platform": "reddit",
            })
            if len(items) >= limit:
                break
        print(f"[STRANGE] Got {len(items)} strange posts", flush=True)
        return items
    except Exception as e:
        print(f"[STRANGE] Fetch failed: {e}", flush=True)
        return []


# ── STRANGE SIGNALS (GOOGLE NEWS) ── RSS, no key, not IP-blocked ──

# Search query → signal "type" used for radar colour/sector.
STRANGE_GOOGLE_QUERIES = {
    '"UFO" OR "UAP" OR "unidentified flying object"': "UFO",
    '"alien" sighting OR encounter':                  "UFO",
    'paranormal OR haunting OR poltergeist':          "Paranormal",
    'ghost sighting OR apparition':                   "Paranormal",
    '"unexplained" mystery OR phenomenon':            "Strange",
    'cold case OR unsolved mystery':                  "Unsolved",
    'cryptid OR bigfoot OR "loch ness"':              "Cryptid",
}


def scrape_strange_signals_google(limit=12):
    """Pull strange/unexplained news from Google News RSS search. Google News
    is not IP-blocked from datacenters (unlike Reddit), so this works on
    Railway. Returns dicts in the same shape as scrape_strange_signals()."""
    # Collect a small bucket per query, then round-robin so the radar shows a
    # variety of signal types instead of (e.g.) five UFO items in a row.
    buckets, seen = [], set()
    per_query = max(2, (limit // max(1, len(STRANGE_GOOGLE_QUERIES))) + 1)
    for query, sig_type in STRANGE_GOOGLE_QUERIES.items():
        q = query.replace(" ", "%20").replace('"', "%22")
        url = (
            f"https://news.google.com/rss/search?q={q}%20when:7d"
            "&hl=en-US&gl=US&ceid=US:en"
        )
        bucket = []
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            for it in root.findall(".//item"):
                if len(bucket) >= per_query:
                    break
                title_el = it.find("title")
                link_el = it.find("link")
                desc_el = it.find("description")
                source_el = it.find("source")
                title = (title_el.text or "").strip() if title_el is not None else ""
                # Google News titles look "Headline - Publisher"; keep the headline.
                headline = re.split(r"\s+-\s+[^-]+$", title)[0].strip() or title
                key = headline.lower()
                if not headline or key in seen:
                    continue
                seen.add(key)
                link = (link_el.text or "").strip() if link_el is not None else ""
                publisher = (source_el.text or "").strip() if source_el is not None else "Google News"
                raw = (desc_el.text or "") if desc_el is not None else ""
                body = re.sub(r"<[^>]+>", " ", raw)
                body = re.sub(r"\s+", " ", body).strip()
                bucket.append({
                    "title": headline[:160],
                    "subreddit": publisher or "Google News",
                    "type": sig_type,
                    "permalink": link,
                    "selftext": body[:400],
                    "image_url": "",
                    "platform": "google",
                })
        except Exception as e:
            print(f"[STRANGE-GOOGLE] Query failed ({sig_type}): {e}", flush=True)
        buckets.append(bucket)

    items = []
    for col in range(per_query):
        for bucket in buckets:
            if col < len(bucket) and len(items) < limit:
                items.append(bucket[col])
        if len(items) >= limit:
            break
    for i, it in enumerate(items):
        it["rank"] = i + 1
    print(f"[STRANGE-GOOGLE] Got {len(items)} strange news items", flush=True)
    return items


# ── PER-QUERY SEARCH ── real cross-platform results for INVESTIGATE ──
# Each returns the same trend-dict shape the niche-pulse cards consume:
#   {rank, name, posts, category, url, scraped_at, platform, source:"live"}
# plus a few extra keys the dossier can use (thumbnail, published, source_name).


def _fmt_count(n, unit):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return f"0 {unit}"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M {unit}"
    if n >= 1_000:
        return f"{n/1_000:.0f}K {unit}"
    return f"{n} {unit}"


def search_google_news(query, limit=4):
    """Real news headlines for a query via Google News RSS. Free, no key, and
    not datacenter-IP-blocked (works on Railway)."""
    q = query.replace(" ", "%20").replace('"', "%22")
    url = f"https://news.google.com/rss/search?q={q}%20when:30d&hl=en-US&gl=US&ceid=US:en"
    now = datetime.now().isoformat()
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        results, seen = [], set()
        for it in root.findall(".//item"):
            if len(results) >= limit:
                break
            title_el = it.find("title")
            link_el = it.find("link")
            src_el = it.find("source")
            date_el = it.find("pubDate")
            desc_el = it.find("description")
            title = (title_el.text or "").strip() if title_el is not None else ""
            headline = re.split(r"\s+-\s+[^-]+$", title)[0].strip() or title
            key = headline.lower()
            if not headline or key in seen:
                continue
            seen.add(key)
            publisher = (src_el.text or "").strip() if src_el is not None else "Google News"
            raw = (desc_el.text or "") if desc_el is not None else ""
            blurb = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()
            results.append({
                "rank": str(len(results) + 1),
                "name": headline[:120],
                "posts": publisher,
                "category": "News",
                "url": (link_el.text or "").strip() if link_el is not None else "",
                "scraped_at": now,
                "platform": "google",
                "source": "live",
                "source_name": publisher,
                "published": (date_el.text or "").strip() if date_el is not None else "",
                "blurb": blurb[:280],
                "thumbnail": "",
            })
        print(f"[SEARCH-GOOGLE] '{query}' -> {len(results)}", flush=True)
        return results
    except Exception as e:
        print(f"[SEARCH-GOOGLE] '{query}' failed: {e}", flush=True)
        return []


def search_youtube(query, limit=4):
    """Real videos for a query via YouTube Data API v3. Two calls: search.list
    for matches, then videos.list for view counts. Returns thumbnails too."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("[SEARCH-YOUTUBE] No API key", flush=True)
        return []
    now = datetime.now().isoformat()
    try:
        sr = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet", "q": query, "type": "video",
                "maxResults": limit, "order": "relevance", "regionCode": "US",
                "relevanceLanguage": "en", "key": api_key,
            },
            timeout=15,
        )
        sr.raise_for_status()
        items = sr.json().get("items", [])
        if not items:
            return []
        ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
        # Second call: real view counts for those video ids.
        stats = {}
        if ids:
            vr = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "statistics", "id": ",".join(ids), "key": api_key},
                timeout=15,
            )
            if vr.status_code == 200:
                for v in vr.json().get("items", []):
                    stats[v["id"]] = v.get("statistics", {})
        results = []
        for it in items:
            vid = it.get("id", {}).get("videoId")
            if not vid:
                continue
            sn = it.get("snippet", {})
            views = stats.get(vid, {}).get("viewCount")
            thumbs = sn.get("thumbnails", {})
            thumb = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
            results.append({
                "rank": str(len(results) + 1),
                "name": sn.get("title", "")[:120],
                "posts": _fmt_count(views, "views") if views is not None else sn.get("channelTitle", "YouTube"),
                "category": sn.get("channelTitle", "YouTube"),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "scraped_at": now,
                "platform": "youtube",
                "source": "live",
                "source_name": sn.get("channelTitle", "YouTube"),
                "published": sn.get("publishedAt", ""),
                "blurb": re.sub(r"\s+", " ", sn.get("description", "")).strip()[:280],
                "thumbnail": thumb,
            })
        print(f"[SEARCH-YOUTUBE] '{query}' -> {len(results)}", flush=True)
        return results
    except Exception as e:
        print(f"[SEARCH-YOUTUBE] '{query}' failed: {e}", flush=True)
        return []


def search_reddit(query, limit=4):
    """Real Reddit posts for a query via search RSS. Works locally; Reddit
    blocks datacenter IPs, so this degrades to [] on Railway (News/YouTube
    carry the result there)."""
    q = query.replace(" ", "+")
    url = f"https://www.reddit.com/search.rss?q={q}&sort=relevance&limit={limit * 2}&t=month"
    ns = "http://www.w3.org/2005/Atom"
    now = datetime.now().isoformat()
    try:
        r = requests.get(url, headers={"User-Agent": "TrendCenterBot/1.0"}, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        results, seen = [], set()
        for e in root.findall(f"{{{ns}}}entry"):
            if len(results) >= limit:
                break
            t = e.find(f"{{{ns}}}title")
            l = e.find(f"{{{ns}}}link")
            c = e.find(f"{{{ns}}}category")
            cont = e.find(f"{{{ns}}}content")
            title = (t.text or "").strip() if t is not None else ""
            key = title.lower()
            if not title or key in seen:
                continue
            seen.add(key)
            sub = c.get("term") if c is not None else "all"
            raw = cont.text if (cont is not None and cont.text) else ""
            blurb = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))
            blurb = re.split(r"submitted by", blurb)[0].strip()
            results.append({
                "rank": str(len(results) + 1),
                "name": (title[:117] + "...") if len(title) > 120 else title,
                "posts": f"r/{sub}",
                "category": f"r/{sub}",
                "url": l.get("href", "") if l is not None else "",
                "scraped_at": now,
                "platform": "reddit",
                "source": "live",
                "source_name": f"r/{sub}",
                "published": "",
                "blurb": blurb[:280],
                "thumbnail": "",
            })
        print(f"[SEARCH-REDDIT] '{query}' -> {len(results)}", flush=True)
        return results
    except Exception as e:
        print(f"[SEARCH-REDDIT] '{query}' failed: {e}", flush=True)
        return []
