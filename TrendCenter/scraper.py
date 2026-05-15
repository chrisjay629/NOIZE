from database import init_db, save_snapshot, cleanup_old_snapshots
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

URL = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def scrape_hashtags():
    response = requests.get(URL, headers=HEADERS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    hashtags = []

    # Each hashtag card is an <a> tag with id="hashtagItemContainer"
    cards = soup.find_all("a", id="hashtagItemContainer")
    print(f"Found {len(cards)} hashtag cards")

    for card in cards:
        try:
            # Rank number
            rank_el = card.find("span", class_=lambda c: c and "rankingIndex" in c)
            rank = rank_el.get_text(strip=True) if rank_el else None

            # Hashtag name (inside CardPc_titleText)
            name_el = card.find("span", class_=lambda c: c and "titleText" in c)
            name = name_el.get_text(strip=True).replace("#", "").strip() if name_el else None

            # Post count (inside CardPc_itemValue)
            posts_el = card.find("span", class_=lambda c: c and "itemValue" in c)
            posts = posts_el.get_text(strip=True) if posts_el else None

            # Category — sits as plain span text near the icon
            category_el = card.find("div", class_=lambda c: c and "infoContent" in c)
            category = None
            if category_el:
                spans = category_el.find_all("span")
                # Last span usually holds the category text
                for s in spans:
                    text = s.get_text(strip=True)
                    if text and not text.startswith("<"):
                        category = text

            # Detail page URL
            href = card.get("href", "")
            url = f"https://ads.tiktok.com{href}" if href.startswith("/") else href

            hashtags.append({
                "rank": rank,
                "name": name,
                "posts": posts,
                "category": category,
                "url": url,
                "scraped_at": datetime.now().isoformat()
            })
        except Exception as e:
            print(f"Error parsing card: {e}")
            continue

    # Save to JSON
    with open("hashtags.json", "w", encoding="utf-8") as f:
        json.dump(hashtags, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(hashtags)} hashtags to hashtags.json")
    save_snapshot(hashtags)
    cleanup_old_snapshots(hours=48)
    print("\nFirst 5 results:")
    for h in hashtags[:5]:
        print(f"  #{h['rank']} - {h['name']} ({h['posts']} posts) [{h['category']}]")

if __name__ == "__main__":
    init_db()
    scrape_hashtags()
