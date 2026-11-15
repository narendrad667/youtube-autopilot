"""Daily topic planner for the YouTube autopilot — trending + competitors.

Free, no keys except Gemini (same free key as the script step).
Sources (all public RSS, no key, no YouTube quota):
- Competitor channels' YouTube RSS feeds (15 newest videos each):
  What If (Underknown), Kurzgesagt, RealLifeLore.
- Google News RSS: Earth / nature / science searches.
Gemini reads those signals and picks 6 fresh What If topics for today,
inspired by what's trending and what competitors just posted — never a
copy of a competitor's title, and never a topic from the used pool.
If Gemini or a feed fails, the missing slots are filled from the
102-topic pool rotation, so topics_today.json always has 6 topics.
Run once per day by the 'plan' job in the daily workflow; the 6 video
jobs read topics_today.json (and fall back to the pool if it is missing).
"""
import datetime
import html
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from script_gen import _call_gemini, DEFAULT_MODEL

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_FILE = os.path.join(BASE_DIR, "topics.json")
TODAY_FILE = os.path.join(BASE_DIR, "topics_today.json")
START_ORDINAL = datetime.date(2026, 11, 16).toordinal()

COMPETITORS = [
    ("What If", "https://www.youtube.com/feeds/videos.xml?channel_id=UCphTF9wHwhCt-BzIq-s4V-g"),
    ("Kurzgesagt", "https://www.youtube.com/feeds/videos.xml?channel_id=UCsXVk37bltHxD1rDPwtNM8Q"),
    ("RealLifeLore", "https://www.youtube.com/feeds/videos.xml?channel_id=UCP5tjEmvPItGyLhmjdwP7Ww"),
]
NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=earth%20nature%20science&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=climate%20ocean%20volcano%20space&hl=en-US&gl=US&ceid=US:en",
]
USER_AGENT = "FreeAiTools-YT-Autopilot/1.0"


def pick_topic(index):
    """Pool rotation: 102 topics, 6/day, no repeat for 17 days from go-live.
    Returns (topic, cycle) — cycle 0 for the first 17 days."""
    with open(TOPICS_FILE) as f:
        topics = json.load(f)
    days = max(0, datetime.date.today().toordinal() - START_ORDINAL)
    slot = days * 6 + index
    return topics[slot % len(topics)], slot // len(topics)


def fetch_titles(url, limit=8):
    """Titles from an RSS/Atom feed (one per item/entry, no duplicates).
    Empty list on any failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        titles, seen = [], set()
        for item in root.iter():
            if not (item.tag.endswith("entry") or item.tag.endswith("item")):
                continue
            for child in item:
                if child.tag.endswith("title") and child.text:
                    title = html.unescape(child.text.strip())
                    if title and title not in seen:
                        seen.add(title)
                        titles.append(title)
                    break
        return titles[:limit]
    except Exception as e:
        print("Feed failed (%s): %s" % (url[:60], e))
        return []


def gather_signals():
    """Competitor recent titles + trending science headlines."""
    signals = {"competitors": {}, "news": []}
    for name, url in COMPETITORS:
        titles = fetch_titles(url, limit=8)
        signals["competitors"][name] = titles
        print("%s: %d recent videos" % (name, len(titles)))
    for url in NEWS_FEEDS:
        signals["news"] += fetch_titles(url, limit=8)
    print("News headlines: %d" % len(signals["news"]))
    return signals


def pick_trending_topics(api_key, signals, used, count=6):
    """Ask Gemini for `count` fresh What If topics from today's signals."""
    comp_lines = []
    for name, titles in signals["competitors"].items():
        for t in titles:
            comp_lines.append("- [%s] %s" % (name, t))
    news_lines = ["- %s" % t for t in signals["news"][:12]]
    prompt = (
        "You plan YouTube videos for a 'What If — Earth & Nature' channel.\n"
        "TODAY'S SIGNALS — recent videos from competitor channels:\n"
        + "\n".join(comp_lines) +
        "\nTRENDING SCIENCE HEADLINES TODAY:\n"
        + "\n".join(news_lines) +
        "\n\nPick %d fresh 'What If' video topics about Earth or nature, "
        "inspired by what is trending and what competitors just posted. "
        "Each topic must be a NEW angle — never copy a competitor's title, "
        "never repeat any of these already-used topics: %s. "
        "Every topic must start with 'What If' and end with '?'. "
        "Return ONLY a JSON array of %d strings, no other text."
        % (count, ", ".join(used), count)
    )
    for attempt in (1, 2):
        text = _call_gemini(prompt, api_key, DEFAULT_MODEL)
        if not text:
            continue
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            continue
        try:
            topics = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            continue
        used_lower = {u.lower() for u in used}
        seen, clean = set(), []
        for t in topics:
            t = str(t).strip().strip('"')
            if (t.lower().startswith("what if") and t.endswith("?")
                    and t.lower() not in used_lower
                    and t.lower() not in seen):
                seen.add(t.lower())
                clean.append(t)
        if clean:
            return clean[:count]
        print("Trending-topic attempt %d gave no valid topics." % attempt)
    return []


def main():
    api_key = os.environ["GEMINI_API_KEY"]
    with open(TOPICS_FILE) as f:
        pool = json.load(f)
    signals = gather_signals()
    topics = pick_trending_topics(api_key, signals, pool, count=6)
    print("Gemini trending topics: %d" % len(topics))
    # Fill any missing slots from the pool rotation (today's slots).
    i = 0
    while len(topics) < 6:
        t, _ = pick_topic(i)
        if t not in topics:
            topics.append(t)
        i += 1
    with open(TODAY_FILE, "w") as f:
        json.dump(topics, f, indent=2)
    print("Wrote %s:" % TODAY_FILE)
    for t in topics:
        print(" - %s" % t)


if __name__ == "__main__":
    main()
