import schedule
import time
from datetime import datetime
from scraper import scrape_hashtags
from database import init_db

def job():
    print(f"\n{'='*60}")
    print(f"Running scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('='*60)
    try:
        scrape_hashtags()
    except Exception as e:
        print(f"Error during scrape: {e}")

if __name__ == "__main__":
    init_db()

    # Run once immediately so you don't wait an hour for the first scrape
    job()

    # Then every hour after that
    schedule.every(1).hours.do(job)

    print(f"\nScheduler running. Next scrape in 1 hour.")
    print("Press Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(30)  # Check every 30 seconds if it's time to run