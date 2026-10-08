"""One-off probe: can we read a post's score from vxreddit when Reddit's own JSON is blocked?
Takes the top few weekly posts from RSS (which works from Actions) and tries several
vxreddit URLs for each, printing every meta tag / JSON snippet so we can spot the score."""
import os
import json
import time
from urllib.parse import urlparse
from html.parser import HTMLParser

import requests
import feedparser

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
DISCORD_UA = "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"


class Meta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = a.get("property") or a.get("name")
            if key:
                self.tags.append((key, a.get("content", "")))
        elif tag == "link" and "oembed" in (a.get("type") or ""):
            self.tags.append(("oembed-link", a.get("href", "")))


def show(label, url, ua):
    print(f"\n--- {label}\n    {url}")
    try:
        r = requests.get(url, headers={"User-Agent": ua}, timeout=15, allow_redirects=False)
    except requests.RequestException as e:
        print(f"    error: {e}")
        return
    ctype = r.headers.get("content-type", "")
    print(f"    status={r.status_code} type={ctype} location={r.headers.get('location')}")
    if r.status_code != 200:
        return
    if "json" in ctype:
        print("    JSON:", r.text[:800])
        return
    parser = Meta()
    parser.feed(r.text)
    if not parser.tags:
        print("    no meta tags; body starts:", r.text[:500].replace("\n", " "))
    oembed = None
    for k, v in parser.tags:
        print(f"    {k} = {v[:300]}")
        if k == "oembed-link":
            oembed = v
    if oembed:
        try:
            r2 = requests.get(oembed, headers={"User-Agent": ua}, timeout=15)
            print(f"    oembed status={r2.status_code}: {r2.text[:800]}")
        except requests.RequestException as e:
            print(f"    oembed error: {e}")


def main():
    channels = json.loads(os.environ.get("DISCORD_CHANNEL_MAPPINGS", "[]"))
    if not isinstance(channels, list):
        print(f"Secret is a {type(channels).__name__}, expected a list.")
        channels = []
    valid = [e for e in channels if e.get("subreddit") and e.get("webhook_url")]
    print(f"Secret has {len(channels)} entries, {len(valid)} valid (subreddit + webhook_url).")
    sub = valid[0]["subreddit"] if valid else "formuladank"

    rss = f"https://www.reddit.com/r/{sub}/top/.rss?t=week"
    resp = requests.get(rss, headers={"User-Agent": BROWSER_UA}, timeout=15)
    print(f"RSS r/{sub}: {resp.status_code}")
    entries = feedparser.parse(resp.content).entries[:3]

    for entry in entries:
        link = entry.get("link", "")
        path = urlparse(link).path
        vx = "https://www.vxreddit.com" + path
        print(f"\n=========== {entry.get('title', '')[:80]}\n{link}")
        attempts = [
            ("vx page, Discordbot UA", vx, DISCORD_UA),
            ("vx page, browser UA", vx, BROWSER_UA),
            ("vx page + .json", vx.rstrip("/") + ".json", DISCORD_UA),
            ("api.vxreddit.com", "https://api.vxreddit.com" + path, DISCORD_UA),
        ]
        for label, url, ua in attempts:
            show(label, url, ua)
            time.sleep(2)


if __name__ == "__main__":
    main()
