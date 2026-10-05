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
    # Unique user-agent per sub avoids Reddit 429 bucket clustering
    headers = {
        "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; sub_{index}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
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

    # Grab the top entry
    top_post = feed.entries[0]
    title = top_post.get("title", "")
    permalink = top_post.get("link", "")
    author = top_post.get("author", "unknown")

    # Convert reddit link to vxreddit for auto-embedded media (images, galleries, videos)
    vx_url = permalink.replace("https://www.reddit.com", "https://www.vxreddit.com")
    vx_url = vx_url.replace("https://reddit.com", "https://www.vxreddit.com")

    # Discord natively unpacks vxreddit cards into full video players and image carousels
    payload = {
        "content": f"🏆 **Top meme of the day from r/{subreddit}** (by {author})\n**{title}**\n{vx_url}"
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
    for idx, entry in enumerate(CHANNELS):
        sub = entry.get("subreddit")
        webhook = entry.get("webhook_url")
        if sub and webhook:
            process_subreddit(sub, webhook, idx)
            # 7-second cooldown between subreddits prevents Reddit's 429 lockout
            time.sleep(7)

if __name__ == "__main__":
    main()