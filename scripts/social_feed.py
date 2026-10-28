"""Adds a roundup post to the social RSS feeds that Zapier reads to post on the LinkedIn and Facebook Pages.

Usage: python3 scripts/social_feed.py YYYY-MM-DD linkedin.txt facebook.txt
Each feed keeps the 20 most recent posts. A post already in a feed (same date) is replaced.
"""
import datetime
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://hostileenvironmentjobs.com"
KEEP = 20


def read_items(path):
    if not path.exists():
        return []
    return re.findall(r"<item>.*?</item>", path.read_text(encoding="utf-8"), re.S)


def item(day, network, text):
    date = datetime.datetime.combine(datetime.date.fromisoformat(day), datetime.time(6, 0), datetime.timezone.utc)
    title = text.strip().splitlines()[0]
    body = text.strip().replace("]]>", "]]&gt;")
    return (f"<item><title>{html.escape(title)}</title><link>{SITE}/</link>"
            f"<guid isPermaLink=\"false\">hej-{network}-{day}</guid>"
            f"<pubDate>{date.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
            f"<description><![CDATA[{body}]]></description></item>")


def write_feed(network, day, text):
    path = ROOT / "social" / f"{network}.xml"
    guid = f"hej-{network}-{day}<"
    items = [i for i in read_items(path) if guid not in i]
    items = [item(day, network, text)] + items
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>\n'
        f"<title>Hostile Environment Jobs: {network.title()} posts</title><link>{SITE}/</link>\n"
        "<description>New jobs and courses roundups, published automatically to the social pages.</description>\n"
        + "\n".join(items[:KEEP]) + "\n</channel></rss>\n", encoding="utf-8")


if __name__ == "__main__":
    day, linkedin, facebook = sys.argv[1:4]
    write_feed("linkedin", day, Path(linkedin).read_text(encoding="utf-8"))
    write_feed("facebook", day, Path(facebook).read_text(encoding="utf-8"))
