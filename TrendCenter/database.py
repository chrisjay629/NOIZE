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
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_name ON hashtag_snapshots(name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON hashtag_snapshots(scraped_at)")
    conn.commit()
    conn.close()
    print("Database initialized.")

def save_snapshot(hashtags):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for h in hashtags:
        try:
            rank = int(h["rank"]) if h["rank"] else None
        except (ValueError, TypeError):
            rank = None
        c.execute("""
            INSERT INTO hashtag_snapshots (name, rank, posts, category, url)
            VALUES (?, ?, ?, ?, ?)
        """, (h["name"], rank, h["posts"], h["category"], h["url"]))
    conn.commit()
    conn.close()
    print(f"Saved {len(hashtags)} snapshots to database.")

def get_latest_hashtags():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT name, rank, posts, category, url, scraped_at
        FROM hashtag_snapshots
        WHERE scraped_at = (SELECT MAX(scraped_at) FROM hashtag_snapshots)
        ORDER BY rank ASC
    """)
    rows = c.fetchall()
    conn.close()
    return [
        {"name": r[0], "rank": r[1], "posts": r[2], "category": r[3], "url": r[4], "scraped_at": r[5]}
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

def get_hashtag_velocity():
    """
    Compare the most recent snapshot to a previous one (1+ hours ago)
    to detect rank movement. Returns hashtags sorted by velocity.

    Negative rank_change = climbing (good — strike now)
    Positive rank_change = falling (fading)
    is_new = first time seen in our data
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get the latest snapshot timestamp
    c.execute("SELECT MAX(scraped_at) FROM hashtag_snapshots")
    latest_time = c.fetchone()[0]

    if not latest_time:
        conn.close()
        return []

    # Get all hashtags from the latest scrape
    c.execute("""
        SELECT name, rank, posts, category, url
        FROM hashtag_snapshots
        WHERE scraped_at = ?
    """, (latest_time,))
    latest = c.fetchall()

    velocity_data = []
    for name, current_rank, posts, category, url in latest:
        # Find the earliest rank for this hashtag (excluding the latest)
        c.execute("""
            SELECT rank, scraped_at FROM hashtag_snapshots
            WHERE name = ? AND scraped_at < ?
            ORDER BY scraped_at ASC
            LIMIT 1
        """, (name, latest_time))
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
            "url": url
        })

    conn.close()
    # Sort by biggest climbers first (most negative rank_change)
    velocity_data.sort(key=lambda x: (not x["is_new"], x["rank_change"]))
    return velocity_data

if __name__ == "__main__":
    init_db()