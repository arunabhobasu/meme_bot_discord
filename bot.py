import os
import sys
import json
import time
import requests

STATE_FILE = "posted.json"
DEFAULT_MIN_SCORE = 1000   # used when an entry has no "min_score"
TOP_N = 5
PRUNE_DAYS = 14
COOLDOWN = 60

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
}

CHANNEL_MAPPINGS_RAW = os.environ.get("DISCORD_CHANNEL_MAPPINGS")
if not CHANNEL_MAPPINGS_RAW:
    print("Error: DISCORD_CHANNEL_MAPPINGS environment variable is missing.")
    sys.exit(1)

try:
    CHANNELS = json.loads(CHANNEL_MAPPINGS_RAW)
except json.JSONDecodeError as err:
    print(f"Error parsing DISCORD_CHANNEL_MAPPINGS JSON: {err}")
    sys.exit(1)


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
    sub = entry["subreddit"]
    min_score = entry.get("min_score", DEFAULT_MIN_SCORE)
    url = f"https://www.reddit.com/r/{sub}/top.json?t=week&limit={TOP_N}"
    print(f"Fetching r/{sub} (min_score={min_score})...")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"Failed to fetch r/{sub} ({resp.status_code})")
            return False
        posts = [c["data"] for c in resp.json()["data"]["children"]]
    except (requests.RequestException, ValueError, KeyError):
        print(f"Failed to fetch or parse r/{sub}")
        return False

    for post in posts:
        if post["score"] < min_score or post["id"] in state:
            continue
        payload = {"content": f"{post['title']}\nhttps://www.vxreddit.com{post['permalink']}"}
        try:
            res = requests.post(entry["webhook_url"], json=payload, timeout=15)
        except requests.RequestException as e:
            print(f"✗ Discord error for r/{sub}: {e}")
            continue
        if res.status_code in (200, 204):
            print(f"✓ Posted {post['id']} from r/{sub} (score {post['score']})")
            state[post["id"]] = time.time()
        else:
            print(f"✗ Discord error for r/{sub} ({res.status_code}): {res.text}")
    return True


def main():
    state = load_state()
    valid = [e for e in CHANNELS if e.get("subreddit") and e.get("webhook_url")]
    ok = 0
    for idx, entry in enumerate(valid):
        ok += process_subreddit(entry, state)
        if idx < len(valid) - 1:
            print(f"Waiting {COOLDOWN}s...")
            time.sleep(COOLDOWN)
    save_state(state)
    if valid and ok == 0:
        sys.exit(1)  # every fetch failed


if __name__ == "__main__":
    main()