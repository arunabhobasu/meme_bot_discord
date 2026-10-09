import os
import re
import sys
import json
import time
from urllib.parse import urlparse
from html.parser import HTMLParser

import requests
import feedparser

STATE_FILE = "posted.json"
DEFAULT_MIN_SCORE = 1000   # used when an entry has no "min_score"
TOP_N = 5
PRUNE_DAYS = 14
COOLDOWN = 60              # seconds between subreddits (Reddit RSS)

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
# vxreddit only serves the embed page (with the score) to bot user agents
DISCORD_UA = "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"

CHANNEL_MAPPINGS_RAW = os.environ.get("DISCORD_CHANNEL_MAPPINGS")
if not CHANNEL_MAPPINGS_RAW:
    print("Error: DISCORD_CHANNEL_MAPPINGS environment variable is missing.")
    sys.exit(1)

try:
    CHANNELS = json.loads(CHANNEL_MAPPINGS_RAW)
except json.JSONDecodeError as err:
    print(f"Error parsing DISCORD_CHANNEL_MAPPINGS JSON: {err}")
    sys.exit(1)


class SiteName(HTMLParser):
    """Grabs <meta property="og:site_name" content="..."> e.g. 'u/x on r/y - ⬆️ 6507 | 💬 1160'"""
    def __init__(self):
        super().__init__()
        self.value = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("property") == "og:site_name":
            self.value = a.get("content", "")


def get_score(vx_url):
    try:
        r = requests.get(vx_url, headers={"User-Agent": DISCORD_UA}, timeout=15)
    except requests.RequestException as e:
        print(f"  vxreddit error: {e}")
        return None
    if r.status_code != 200:
        print(f"  vxreddit returned {r.status_code}")
        return None
    p = SiteName()
    p.feed(r.text)
    m = re.search(r"\u2b06\ufe0f?\s*([\d,.]+)\s*([kKmM]?)", p.value or "")
    if not m:
        print(f"  couldn't find score in: {p.value!r}")
        return None
    mult = {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1)
    return int(float(m.group(1).replace(",", "")) * mult)


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    cutoff = time.time() - PRUNE_DAYS * 86400
    with open(STATE_FILE, "w") as f:
        json.dump({k: v for k, v in state.items() if v >= cutoff}, f, indent=2)


def process_subreddit(entry, state):
    """Returns True if the Reddit RSS fetch succeeded."""
    sub = entry["subreddit"]
    min_score = entry.get("min_score", DEFAULT_MIN_SCORE)
    print(f"Fetching r/{sub} (min_score={min_score})...")

    try:
        resp = requests.get(
            f"https://www.reddit.com/r/{sub}/top/.rss?t=week",
            headers={"User-Agent": BROWSER_UA}, timeout=15,
        )
    except requests.RequestException as e:
        print(f"Network error querying r/{sub}: {e}")
        return False
    if resp.status_code != 200:
        print(f"Failed to fetch r/{sub} ({resp.status_code})")
        return False

    for e in feedparser.parse(resp.content).entries[:TOP_N]:
        link = e.get("link", "")
        m = re.search(r"/comments/([a-z0-9]+)/", link)
        if not m:
            continue
        pid = m.group(1)
        if pid in state:
            print(f"  skip {pid}: already posted")
            continue

        vx_url = "https://www.vxreddit.com" + urlparse(link).path
        score = get_score(vx_url)
        time.sleep(2)
        if score is None:
            print(f"  skip {pid}: no score")
            continue
        if score < min_score:
            print(f"  skip {pid}: score {score} < {min_score}")
            continue

        payload = {"content": f"{e.get('title', '')}\n{vx_url}"}
        try:
            res = requests.post(entry["webhook_url"], json=payload, timeout=15)
        except requests.RequestException as err:
            print(f"✗ Discord error for r/{sub}: {err}")
            continue
        if res.status_code in (200, 204):
            print(f"✓ Posted {pid} from r/{sub} (score {score})")
            state[pid] = time.time()
        else:
            print(f"✗ Discord error for r/{sub} ({res.status_code}): {res.text}")
    return True


def main():
    state = load_state()
    valid = [e for e in CHANNELS if e.get("subreddit") and e.get("webhook_url")]
    print(f"{len(valid)} valid subreddit entries.")
    ok = 0
    for idx, entry in enumerate(valid):
        ok += process_subreddit(entry, state)
        save_state(state)
        if idx < len(valid) - 1:
            print(f"Waiting {COOLDOWN}s...")
            time.sleep(COOLDOWN)
    if valid and ok == 0:
        sys.exit(1)  # every RSS fetch failed


if __name__ == "__main__":
    main()