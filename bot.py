import os
import sys
import json
import time
import requests

CHANNEL_MAPPINGS_RAW = os.environ.get("DISCORD_CHANNEL_MAPPINGS")

if not CHANNEL_MAPPINGS_RAW:
    print("Error: DISCORD_CHANNEL_MAPPINGS environment variable is missing.")
    sys.exit(1)

try:
    CHANNELS = json.loads(CHANNEL_MAPPINGS_RAW)
except json.JSONDecodeError as err:
    print(f"Error parsing DISCORD_CHANNEL_MAPPINGS JSON: {err}")
    sys.exit(1)

HEADERS = {"User-Agent": "DailySportsMemeBot/1.0 (GitHub Actions Runner)"}

def process_subreddit(subreddit: str, webhook_url: str):
    # Fetch top 10 daily posts to ensure we skip pinned mod announcements
    reddit_url = f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit=10"
    print(f"Fetching r/{subreddit}...")

    try:
        response = requests.get(reddit_url, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        print(f"Network error querying r/{subreddit}: {e}")
        return

    if response.status_code != 200:
        print(f"Failed to fetch r/{subreddit} ({response.status_code}): {response.text}")
        return

    data = response.json()
    children = data.get("data", {}).get("children", [])
    
    # Filter out pinned/stickied mod posts
    posts = [p["data"] for p in children if not p["data"].get("stickied", False)]

    if not posts:
        print(f"No non-stickied posts found for r/{subreddit}.")
        return

    top_post = posts[0]
    title = top_post.get("title", "No Title")
    permalink = f"https://reddit.com{top_post.get('permalink')}"
    url = top_post.get("url", "")
    author = top_post.get("author", "unknown")
    score = top_post.get("score", 0)
    is_video = top_post.get("is_video", False)
    over_18 = top_post.get("over_18", False)

    # Clean embed base
    embed = {
        "title": title[:256],
        "url": permalink,
        "color": 16729344,  # Reddit Orange
        "footer": {"text": f"Posted by u/{author} • Score: {score} 👍" + (" • [NSFW]" if over_18 else "")},
    }

    # Case 1: Video (Reddit Video, YouTube, Streamable, etc.)
    # Sending permalink directly in content lets Discord render its native video player
    if is_video or "v.redd.it" in url or "youtu" in url:
        payload = {
            "content": f"**Top meme of the day from r/{subreddit}:**\n{permalink}",
            "embeds": [embed],
        }
    # Case 2: Direct image/GIF
    elif any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
        embed["image"] = {"url": url}
        payload = {
            "content": f"**Top meme of the day from r/{subreddit}:**",
            "embeds": [embed],
        }
    # Case 3: Reddit galleries or external link fallbacks
    else:
        embed["description"] = f"[Open post on Reddit]({permalink})"
        payload = {
            "content": f"**Top meme of the day from r/{subreddit}:**\n{permalink}",
            "embeds": [embed],
        }

    try:
        res = requests.post(webhook_url, json=payload, timeout=15)
        if res.status_code in (200, 204):
            print(f"✓ Posted r/{subreddit} to Discord successfully.")
        else:
            print(f"✗ Discord webhook error for r/{subreddit} ({res.status_code}): {res.text}")
    except requests.RequestException as e:
        print(f"✗ Error dispatching webhook for r/{subreddit}: {e}")

def main():
    for entry in CHANNELS:
        sub = entry.get("subreddit")
        webhook = entry.get("webhook_url")

        if sub and webhook:
            process_subreddit(sub, webhook)
            time.sleep(2)  # 2s safety pause between webhooks
        else:
            print(f"Skipping invalid mapping entry: {entry}")

if __name__ == "__main__":
    main()