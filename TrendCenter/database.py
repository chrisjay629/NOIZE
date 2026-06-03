import sqlite3
from datetime import datetime

DB_PATH = "trends.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS hashtag_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rank INTEGER,
            posts TEXT,
            category TEXT,
            url TEXT,
            platform TEXT DEFAULT 'tiktok',
            source TEXT DEFAULT 'live',
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migrate existing tables that don't have platform/source columns
    for col, default in [("platform", "'tiktok'"), ("source", "'live'")]:
        try:
            c.execute(f"ALTER TABLE hashtag_snapshots ADD COLUMN {col} TEXT DEFAULT {default}")
        except Exception:
            pass  # Column already exists
    c.execute("CREATE INDEX IF NOT EXISTS idx_name ON hashtag_snapshots(name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON hashtag_snapshots(scraped_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_platform ON hashtag_snapshots(platform)")
    conn.commit()
    conn.close()
    print("Database initialized.")

def save_snapshot(hashtags, platform="tiktok"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for h in hashtags:
        try:
            rank = int(h["rank"]) if h.get("rank") else None
        except (ValueError, TypeError):
            rank = None
        c.execute("""
            INSERT INTO hashtag_snapshots (name, rank, posts, category, url, platform, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            h.get("name"), rank, h.get("posts"), h.get("category"),
            h.get("url"), h.get("platform", platform), h.get("source", "live")
        ))
    conn.commit()
    conn.close()
    print(f"Saved {len(hashtags)} snapshots to database (platform: {platform}).")

def get_data_age_minutes(platform="tiktok"):
    """Returns how many minutes old the latest snapshot is, or None if no data."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(scraped_at) FROM hashtag_snapshots WHERE platform = ?", (platform,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    try:
        latest = datetime.fromisoformat(row[0])
        delta = datetime.now() - latest
        return delta.total_seconds() / 60
    except Exception:
        return None

def get_latest_hashtags(platform="tiktok"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT name, rank, posts, category, url, scraped_at, platform, source
        FROM hashtag_snapshots
        WHERE platform = ?
          AND scraped_at = (
              SELECT MAX(scraped_at) FROM hashtag_snapshots WHERE platform = ?
          )
        ORDER BY rank ASC
    """, (platform, platform))
    rows = c.fetchall()
    conn.close()
    return [
        {
            "name": r[0], "rank": r[1], "posts": r[2], "category": r[3],
            "url": r[4], "scraped_at": r[5], "platform": r[6], "source": r[7]
        }
        for r in rows
    ]

def cleanup_old_snapshots(hours=48):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        DELETE FROM hashtag_snapshots
        WHERE scraped_at < datetime('now', '-' || ? || ' hours')
    """, (hours,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    print(f"Cleaned up {deleted} old snapshots (older than {hours} hours)")
    return deleted

def get_hashtag_velocity(platform="tiktok"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT MAX(scraped_at) FROM hashtag_snapshots WHERE platform = ?", (platform,))
    latest_time = c.fetchone()[0]

    if not latest_time:
        conn.close()
        return []

    c.execute("""
        SELECT name, rank, posts, category, url, source
        FROM hashtag_snapshots
        WHERE scraped_at = ? AND platform = ?
    """, (latest_time, platform))
    latest = c.fetchall()

    velocity_data = []
    for name, current_rank, posts, category, url, source in latest:
        c.execute("""
            SELECT rank FROM hashtag_snapshots
            WHERE name = ? AND scraped_at < ? AND platform = ?
            ORDER BY scraped_at ASC
            LIMIT 1
        """, (name, latest_time, platform))
        previous = c.fetchone()

        if previous:
            previous_rank = previous[0]
            rank_change = current_rank - previous_rank if (current_rank and previous_rank) else 0
            is_new = False
        else:
            previous_rank = None
            rank_change = 0
            is_new = True

        velocity_data.append({
            "name": name,
            "current_rank": current_rank,
            "previous_rank": previous_rank,
            "rank_change": rank_change,
            "is_new": is_new,
            "posts": posts,
            "category": category,
            "url": url,
            "platform": platform,
            "source": source
        })

    conn.close()
    velocity_data.sort(key=lambda x: (not x["is_new"], x["rank_change"]))
    return velocity_data

if __name__ == "__main__":
    init_db()
