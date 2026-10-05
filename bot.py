import os
import sys
import json
import time
import re
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def extract_media(entry_content: str):
    """Extracts direct preview images or video links from Reddit's RSS HTML description."""
    # Look for image preview links
    img_match = re.search(r'<img\s+src="([^"]+)"', entry_content)
    if img_match:
        return img_match.group(1), "image"

    # Look for reddit direct link inside href
    href_match = re.search(r'<span><a href="([^"]+)">\[link\]</a></span>', entry_content)
    if href_match:
        link = href_match.group(1)
        if any(link.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
            return link, "image"
        if "v.redd.it" in link or "youtu" in link:
            return link, "video"

    return None, None

def process_subreddit(subreddit: str, webhook_url: str):
    # Reddit RSS endpoint (order by top of the day)
    feed_url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t=day"
    print(f"Fetching r/{subreddit} via RSS...")

    try:
        resp = requests.get(feed_url, headers=HEADERS, timeout=15)
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
    title = top_post.get("title", "No Title")
    permalink = top_post.get("link", "")
    author = top_post.get("author", "unknown")
    content_html = top_post.get("content", [{}])[0].get("value", "")

    media_url, media_type = extract_media(content_html)

    embed = {
        "title": title[:256],
        "url": permalink,
        "color": 16729344,  # Reddit orange
        "footer": {"text": f"Posted by {author} on r/{subreddit}"}
    }

    if media_type == "image" and media_url:
        embed["image"] = {"url": media_url}
        payload = {
            "content": f"**Top meme of the day from r/{subreddit}:**",
            "embeds": [embed]
        }
    else:
        # For videos or native previews, sending permalink in content lets Discord unfold the media
        payload = {
            "content": f"**Top meme of the day from r/{subreddit}:**\n{permalink}",
            "embeds": [embed]
        }

    try:
        res = requests.post(webhook_url, json=payload, timeout=15)
        if res.status_code in (200, 204):
            print(f"✓ Posted r/{subreddit} to Discord successfully.")
        else:
            print(f"✗ Discord error for r/{subreddit} ({res.status_code}): {res.text}")
    except requests.RequestException as e:
        print(f"✗ Error sending to Discord: {e}")

def main():
    for entry in CHANNELS:
        sub = entry.get("subreddit")
        webhook = entry.get("webhook_url")
        if sub and webhook:
            process_subreddit(sub, webhook)
            time.sleep(2)

if __name__ == "__main__":
    main()