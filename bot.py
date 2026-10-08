import os
import sys
import json
import time
import requests

STATE_FILE = "posted.json"
DEFAULT_MIN_SCORE = 1000   # used when an entry has no "min_score"
TOP_N = 5                  # how many top-of-week posts to inspect
PRUNE_DAYS = 14            # forget posted IDs older than this
COOLDOWN = 60              # seconds between subreddits

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
}
URL_TEMPLATES = [
    "https://www.reddit.com/r/{sub}/top.json?t=week&limit={n}",
]

CHANNEL_MAPPINGS_RAW = os.environ.get("DISCORD_CHANNEL_MAPPINGS")

if not CHANNEL_MAPPINGS_RAW:
    print("Error: DISCORD_CHANNEL_MAPPINGS environment variable is missing.")
    sys.exit(1)

try:
    CHANNELS = json.loads(CHANNEL_MAPPINGS_RAW)
except json.JSONDecodeError as err:
    print(f"Error parsing DISCORD_CHANNEL_MAPPINGS JSON: {err}")
    sys.exit(1)


def load_state() -> dict:
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict):
    cutoff = time.time() - PRUNE_DAYS * 86400
    pruned = {pid: ts for pid, ts in state.items() if ts >= cutoff}
    with open(STATE_FILE, "w") as f:
        json.dump(pruned, f, indent=2, sort_keys=True)


def process_subreddit(entry: dict, state: dict) -> bool:
    """Returns True if the Reddit fetch succeeded (regardless of posts sent)."""
    subreddit = entry["subreddit"]
    webhook_url = entry["webhook_url"]
    min_score = entry.get("min_score", DEFAULT_MIN_SCORE)

    print(f"Fetching r/{subreddit} (min_score={min_score})...")

    resp = None
    for template in URL_TEMPLATES:
        url = template.format(sub=subreddit, n=TOP_N)
        host = url.split("/")[2]
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            print(f"  {host}: network error: {e}")
            time.sleep(3)
            continue
        print(f"  {host}: {r.status_code}")
        if r.status_code == 200:
            resp = r
            break
        time.sleep(3)

    if resp is None:
        print(f"Failed to fetch r/{subreddit} from all hosts.")
        return False

    try:
        posts = [c["data"] for c in resp.json()["data"]["children"]]
    except (ValueError, KeyError, TypeError):
        print(f"Unexpected response format for r/{subreddit}.")
        return False

    for post in posts[:TOP_N]:
        pid = post.get("id")
        score = post.get("score", 0)
        title = post.get("title", "")

        if not pid:
            continue
        if score < min_score:
            print(f"  skip {pid}: score {score} < {min_score}")
            continue
        if pid in state:
            print(f"  skip {pid}: already posted")
            continue

        vx_url = f"https://www.vxreddit.com{post['permalink']}"
        payload = {"content": f"{title}\n{vx_url}"}

        try:
            res = requests.post(webhook_url, json=payload, timeout=15)
        except requests.RequestException as e:
            print(f"✗ Error sending to Discord for r/{subreddit}: {e}")
            continue

        if res.status_code in (200, 204):
            print(f"✓ Posted {pid} from r/{subreddit} (score {score}).")
            state[pid] = time.time()
            time.sleep(1)  # be gentle with the webhook if several qualify
        else:
            print(f"✗ Discord error for r/{subreddit} ({res.status_code}): {res.text}")

    return True


def main():
    state = load_state()
    valid = [e for e in CHANNELS if e.get("subreddit") and e.get("webhook_url")]
    fetched_ok = 0

    for idx, entry in enumerate(valid):
        if process_subreddit(entry, state):
            fetched_ok += 1
        save_state(state)  # save after each sub so a crash doesn't lose dedup info
        if idx < len(valid) - 1:
            print(f"Waiting {COOLDOWN}s for Reddit rate limit reset...")
            time.sleep(COOLDOWN)

    save_state(state)

    # Only fail the run if Reddit blocked every single fetch
    if valid and fetched_ok == 0:
        print("All fetches failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()