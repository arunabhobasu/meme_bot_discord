import os
import sys
import json
import time
import requests
import feedparser

CHANNEL_MAPPINGS_RAW = os.environ.get("DISCORD_CHANNEL_MAPPINGS")

if not CHANNEL_MAPPINGS_RAW:
    print("Error: DISCORD_CHANNEL_MAPPINGS environment variable is missing.")
    sys.exit(1)

try:
    CHANNELS = json.loads(CHANNEL_MAPPINGS_RAW)
except json.JSONDecodeError as err:
    print(f"Error parsing DISCORD_CHANNEL_MAPPINGS JSON: {err}")
    sys.exit(1)

def process_subreddit(subreddit: str, webhook_url: str, index: int):
    # Unique user-agent string per subreddit
    headers = {
        "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.{index} Safari/537.36"
    }
    
    feed_url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t=day"
    print(f"Fetching r/{subreddit} via RSS...")

    try:
        resp = requests.get(feed_url, headers=headers, timeout=15)
    except requests.RequestException as e:
        print(f"Network error querying r/{subreddit}: {e}")
        return

    if resp.status_code != 200:
        print(f"Failed to fetch r/{subreddit} ({resp.status_code})")
        return

    feed = feedparser.parse(resp.content)
    if not feed.entries:
        print(f"No posts found in feed for r/{subreddit}.")
        return

    top_post = feed.entries[0]
    title = top_post.get("title", "")
    permalink = top_post.get("link", "")

    # Convert to vxreddit for native video/image/gallery embedding
    vx_url = permalink.replace("https://www.reddit.com", "https://www.vxreddit.com")
    vx_url = vx_url.replace("https://reddit.com", "https://www.vxreddit.com")

    # Clean formatting: displays the full title, followed by vxreddit's rich media card
    payload = {
        "content": f"## {title}\n{vx_url}"
    }

    try:
        res = requests.post(webhook_url, json=payload, timeout=15)
        if res.status_code in (200, 204):
            print(f"✓ Posted r/{subreddit} to Discord successfully.")
        else:
            print(f"✗ Discord error for r/{subreddit} ({res.status_code}): {res.text}")
    except requests.RequestException as e:
        print(f"✗ Error sending to Discord for r/{subreddit}: {e}")

def main():
    total = len(CHANNELS)
    for idx, entry in enumerate(CHANNELS):
        sub = entry.get("subreddit")
        webhook = entry.get("webhook_url")
        if sub and webhook:
            process_subreddit(sub, webhook, idx)
            # 25-second cooldown between subreddits avoids Reddit's IP-level 429 lockout
            if idx < total - 1:
                print("Waiting 25s for Reddit rate limit reset...")
                time.sleep(25)

if __name__ == "__main__":
    main()