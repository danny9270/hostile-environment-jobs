"""Jobs closing soon: the /closing-soon/ page (built by build_pages.py) and a weekly "closing soon" social post.

Usage: python3 scripts/closing_soon.py [YYYY-MM-DD]
Adds this week's closing-soon post to social/facebook.xml and social/linkedin.xml, which Zapier posts to the
Facebook and LinkedIn Pages. Skips the post when no job closes in the next WINDOW days. The GitHub Action
"Closing soon post" runs it every Thursday morning.
"""
import datetime
import json
import re
import sys
from pathlib import Path

import social_feed

ROOT = Path(__file__).resolve().parent.parent
WINDOW = 14  # days ahead that count as "closing soon"
SHOWN = 8  # most jobs listed in one post

CATEGORY_EMOJI = {"EOD": "💥", "IEDD": "💥", "Search": "🔎", "Survey & Clearance": "⚠️", "Security": "🛡️",
                  "Maritime Security": "⚓", "Medical": "⛑️", "Security Risk & Analysis": "📊", "K9": "🐕", "CBRN": "☢️",
                  "Management": "📋", "Quality & Safety": "✅", "Training": "🎯", "Life Support & Logistics": "📦", "Aviation": "🚁"}


def dated(j):
    return bool(re.fullmatch(r"\d{4}-\d\d-\d\d", j.get("closing") or ""))


def days_left(j, today):
    return (datetime.date.fromisoformat(j["closing"]) - today).days


def closing_soon(jobs, today, window=WINDOW):
    """Open, real jobs with a closing date in the next `window` days, soonest first."""
    soon = [j for j in jobs if j.get("id") and not j.get("sample") and dated(j) and 0 <= days_left(j, today) <= window]
    return sorted(soon, key=lambda j: (j["closing"], j.get("title", "")))


def left_text(j, today):
    d = days_left(j, today)
    return "Closes today" if d == 0 else "Closes tomorrow" if d == 1 else f"{d} days left"


def short_place(location):
    return location.split(",")[0].strip()


def post_text(jobs, today, network):
    """The post body for one network, or None when nothing closes soon."""
    soon = closing_soon(jobs, today)
    if not soon:
        return None
    shown = soon[:SHOWN]
    n = len(soon)
    word = "job" if n == 1 else "jobs"
    lines = []
    for j in shown:
        when = datetime.date.fromisoformat(j["closing"]).strftime("%a %-d %b")
        mark = CATEGORY_EMOJI.get(j.get("category"), "📌")
        if network == "facebook":
            lines.append(f"{mark} {j['title']}, {j['employer']}, {short_place(j['location'])}\n   ⏳ closes {when}")
        else:
            lines.append(f"• {j['title']}, {j['employer']} · {j['location']} · closes {when}")
    more = f"\n…and {n - len(shown)} more.\n" if n > len(shown) else ""
    link = "hostileenvironmentjobs.com/closing-soon/"
    if network == "facebook":
        return (f"⏰ {n} {word} closing in the next {WINDOW} days 👇\n\n" + "\n\n".join(lines) + "\n" + more
                + f"\nDon't leave it to the last day. Details and apply links:\n{link}\n\nKnow someone who'd fit? Tag them 👇")
    tags = sorted({"#" + re.sub(r"\W", "", j.get("category", "")) for j in shown if j.get("category") not in (None, "", "Other")})
    return (f"Closing soon on Hostile Environment Jobs: {n} {word} with deadlines in the next {WINDOW} days.\n\n"
            + "\n".join(lines) + "\n" + more
            + f"\nEvery listing is checked before it goes live. Full details and how to apply:\n{link}\n\n"
            + " ".join(tags + ["#ClosingSoon", "#Jobs"]))


def main():
    today = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.datetime.now(datetime.timezone.utc).date()
    jobs = json.loads((ROOT / "jobs.json").read_text())
    jobs = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
    texts = {n: post_text(jobs, today, n) for n in ("facebook", "linkedin")}
    if not texts["facebook"]:
        print("No jobs closing in the next", WINDOW, "days, so no post this week.")
        return
    for network, text in texts.items():
        # Its own guid ("closing-<date>"), so it never replaces the new-jobs roundup from the same day.
        social_feed.write_feed(network, f"closing-{today.isoformat()}", text, today.isoformat(), hour=8)
    print(texts["facebook"])


if __name__ == "__main__":
    main()
