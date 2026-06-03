from database import init_db, save_snapshot, cleanup_old_snapshots
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

URL = "https://ads.tiktok.com/creative/creativeCenter/trends"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def gpt_fallback_hashtags():
    """When TikTok's page is unavailable, use GPT to generate realistic trending hashtags."""
    print("[TIKTOK] Creative Center unavailable — using GPT fallback", flush=True)
    today = datetime.now().strftime("%B %d, %Y")
    prompt = (
        f"Today's date is {today}. You are a TikTok trend expert. "
        "TikTok's Creative Center is temporarily down. "
        "Generate a realistic list of 20 trending TikTok hashtags for today's leaderboard. "
        "Base this on what's currently popular in entertainment, sports, lifestyle, food, wellness, and pop culture. "
        "For each hashtag provide:\n"
        "- rank: 1 through 20\n"
        "- name: hashtag without the # symbol\n"
        "- posts: estimated post count (e.g. '2.4M', '890K')\n"
        "- category: one of Entertainment, Sports, Lifestyle, Food, Wellness, Fashion, Education, Comedy, Music, Gaming\n\n"
        "Return ONLY a valid JSON array, no other text:\n"
        '[{"rank":"1","name":"...","posts":"...","category":"..."}]'
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    try:
        data = json.loads(response.choices[0].message.content)
        now = datetime.now().isoformat()
        hashtags = []
        for h in data:
            name = h.get("name", "")
            hashtags.append({
                "rank": str(h.get("rank", "")),
                "name": name,
                "posts": h.get("posts", ""),
                "category": h.get("category", ""),
                "url": f"https://www.tiktok.com/tag/{name}",
                "scraped_at": now,
                "platform": "tiktok",
                "source": "gpt_fallback"
            })
        print(f"[TIKTOK] GPT fallback generated {len(hashtags)} hashtags", flush=True)
        return hashtags
    except Exception as e:
        print(f"[TIKTOK] GPT fallback failed: {e}", flush=True)
        return []


def scrape_hashtags():
    print("[TIKTOK] Starting scrape", flush=True)
    hashtags = []

    try:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        html = response.text

        if "Taking a short break" in html or "Back better and stronger" in html:
            print("[TIKTOK] Maintenance page detected", flush=True)
            hashtags = gpt_fallback_hashtags()
        else:
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.find_all("a", id="hashtagItemContainer")
            print(f"[TIKTOK] Found {len(cards)} hashtag cards", flush=True)

            if len(cards) == 0:
                print("[TIKTOK] 0 cards found — using GPT fallback", flush=True)
                hashtags = gpt_fallback_hashtags()
            else:
                for card in cards:
                    try:
                        rank_el = card.find("span", class_=lambda c: c and "rankingIndex" in c)
                        rank = rank_el.get_text(strip=True) if rank_el else None

                        name_el = card.find("span", class_=lambda c: c and "titleText" in c)
                        name = name_el.get_text(strip=True).replace("#", "").strip() if name_el else None

                        posts_el = card.find("span", class_=lambda c: c and "itemValue" in c)
                        posts = posts_el.get_text(strip=True) if posts_el else None

                        category_el = card.find("div", class_=lambda c: c and "infoContent" in c)
                        category = None
                        if category_el:
                            for s in category_el.find_all("span"):
                                text = s.get_text(strip=True)
                                if text and not text.startswith("<"):
                                    category = text

                        href = card.get("href", "")
                        url = f"https://ads.tiktok.com{href}" if href.startswith("/") else href

                        hashtags.append({
                            "rank": rank,
                            "name": name,
                            "posts": posts,
                            "category": category,
                            "url": url,
                            "scraped_at": datetime.now().isoformat(),
                            "platform": "tiktok",
                            "source": "live"
                        })
                    except Exception as e:
                        print(f"[TIKTOK] Error parsing card: {e}", flush=True)
                        continue

    except Exception as e:
        print(f"[TIKTOK] Request failed: {e} — using GPT fallback", flush=True)
        hashtags = gpt_fallback_hashtags()

    if not hashtags:
        print("[TIKTOK] No hashtags from any source", flush=True)
        return

    with open("hashtags.json", "w", encoding="utf-8") as f:
        json.dump(hashtags, f, indent=2, ensure_ascii=False)

    save_snapshot(hashtags, platform="tiktok")
    cleanup_old_snapshots(hours=48)
    print(f"[TIKTOK] Done — {len(hashtags)} hashtags saved (source: {hashtags[0].get('source')})", flush=True)


if __name__ == "__main__":
    init_db()
    scrape_hashtags()
