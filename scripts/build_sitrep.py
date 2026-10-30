"""Build this week's Sitrep newsletter from jobs.json and courses.json.

Writes the web copy to /sitrep/<date>/, the archive at /sitrep/, an RSS feed at /sitrep/feed.xml,
and the email body to the path given (the "Weekly Sitrep" GitHub Action sends that to Kit).
A note written to sitrep/note.txt before Monday goes at the top of that week's issue.
Run from the repo root: python3 scripts/build_sitrep.py [email.html] [YYYY-MM-DD], or with --archive to rebuild only /sitrep/.
Running it again on the same date rebuilds that issue rather than adding a new one.
"""
import datetime
import json
import re
import sys

from build_pages import ROOT, SITE, e, fmt, is_open, page
from referral import booking_url, promo_text

SITREP = ROOT / "sitrep"
COURSE_WEEKS = 8
# Optional note for the next issue (plain text, blank lines between paragraphs). It's used once, then deleted.
NOTE = SITREP / "note.txt"
# Inline styles only: email apps ignore the site's stylesheet.
A = 'style="color:#c2410c"'
H2 = 'style="font-size:18px;margin:28px 0 8px;text-transform:uppercase;letter-spacing:.04em"'
SMALL = 'style="color:#666;font-size:14px"'


def is_date(d):
    return bool(re.fullmatch(r"\d{4}-\d\d-\d\d", d or ""))


def past_issues():
    return sorted(p.name for p in SITREP.glob("20??-??-??") if (p / "index.html").exists())


def content(day, issue, previous):
    jobs = [j for j in json.loads((ROOT / "jobs.json").read_text()) if is_open(j) and not j.get("sample") and j.get("id")]
    courses = json.loads((ROOT / "courses.json").read_text())
    since = datetime.date.fromisoformat(previous) if previous else None
    new = sorted((j for j in jobs if not since or (j.get("posted") or "") > previous), key=lambda j: j.get("posted", ""), reverse=True)
    soon = sorted((j for j in jobs if is_date(j.get("closing")) and j not in new
                   and (datetime.date.fromisoformat(j["closing"]) - day).days <= 14), key=lambda j: j["closing"])
    upto = day + datetime.timedelta(weeks=COURSE_WEEKS)
    upcoming = sorted((c for c in courses if not c.get("sample") and is_date(c.get("start"))
                       and day <= datetime.date.fromisoformat(c["start"]) <= upto), key=lambda c: c["start"])

    def job(j):
        closing = "open until filled" if not is_date(j.get("closing")) else "closes " + fmt(j["closing"])
        return (f'<li style="margin-bottom:10px"><a {A} href="{SITE}/jobs/{e(j["id"])}/"><b>{e(j["title"])}</b></a>, {e(j["employer"])}<br>'
                f'<span {SMALL}>{e(j["category"])} · {e(j["location"])} · {closing}</span></li>')

    def course(c):
        return (f'<li style="margin-bottom:10px"><a {A} href="{e(booking_url(c, "sitrep"))}"><b>{e(c["title"])}</b></a>, {e(c["provider"])}<br>'
                f'<span {SMALL}>Starts {fmt(c["start"])} · {e(c["location"])}{" · " + e(c["price"]) if c.get("price") else ""}'
                f'{" · " + e(promo_text(c)) if c.get("promo_code") else ""}</span></li>')

    intro = (f"The first Sitrep: every open job on the site, plus course dates for the next {COURSE_WEEKS} weeks." if not previous else
             f"{len(new)} new job{'s' if len(new) != 1 else ''} since the last Sitrep, {len(jobs)} open in total.")
    if previous and not new:
        intro = f"No new jobs this week, but {len(jobs)} are still open."
    note = NOTE.read_text().strip().split("\n\n") if NOTE.exists() else []
    parts = [f"<p>{e(p)}</p>" for p in note if p.strip()] + [f"<p>{intro}</p>"]
    if new:
        parts += [f'<h2 {H2}>{"Open jobs" if not previous else "New jobs"}</h2>', "<ul>" + "".join(job(j) for j in new) + "</ul>"]
    if soon:
        parts += [f'<h2 {H2}>Closing soon</h2>', "<ul>" + "".join(job(j) for j in soon) + "</ul>"]
    if upcoming:
        parts += [f'<h2 {H2}>Courses starting soon</h2>', "<ul>" + "".join(course(c) for c in upcoming) + "</ul>"]
    parts.append(f'<p>See every job, filter by trade and region, and add course dates to your calendar at '
                 f'<a {A} href="{SITE}/">hostileenvironmentjobs.com</a>.</p>'
                 f'<p>Hiring or running a course? <a {A} href="{SITE}/#post">List it free</a>. '
                 f'Know someone leaving the forces? Forward them this email.</p>'
                 f'<p>Stay safe,<br>H.E. Jobs Team</p>')
    subject = f"Sitrep #{issue}: " + (f"{len(new)} new job{'s' if len(new) != 1 else ''}" if previous and new else f"{len(jobs)} open jobs")
    subject += f", {len(upcoming)} course date{'s' if len(upcoming) != 1 else ''}" if upcoming else ""
    preview = ", ".join(f"{j['title']} ({j['employer']})" for j in new[:3]) or "This week's hostile environment jobs and courses"
    return subject, preview, "\n".join(parts)


def main():
    if sys.argv[1:] == ["--archive"]:
        return write_archive()
    out = sys.argv[1] if len(sys.argv) > 1 else None
    day = datetime.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.datetime.now(datetime.timezone.utc).date()
    issues = [d for d in past_issues() if d != day.isoformat()]
    previous = issues[-1] if issues else None
    issue = len(issues) + 1
    subject, preview, body = content(day, issue, previous)

    folder = SITREP / day.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"issue": issue, "date": day.isoformat(), "subject": subject, "preview": preview}
    (folder / "issue.json").write_text(json.dumps(meta, indent=1) + "\n")
    signup = f'<div class="actions"><a class="btn primary" href="/#sitrep">Get the Sitrep by email</a><a class="btn" href="/sitrep/">All issues</a></div>'
    web = f'<a class="back" href="/sitrep/">&larr; All Sitreps</a>\n<article class="detail">\n<span class="tag">Sitrep #{issue} · {fmt(day.isoformat())}</span>\n<h1>{e(subject)}</h1>\n{body}\n{signup}\n</article>'
    (folder / "index.html").write_text(page(f"{subject} | Hostile Environment Jobs", preview, f"/sitrep/{day.isoformat()}/", web))
    NOTE.unlink(missing_ok=True)
    if out:
        open(out, "w").write(body)
        open(out + ".json", "w").write(json.dumps(meta))
    write_archive()
    print(f"Built Sitrep #{issue} for {day}: {subject}")


def write_archive():
    all_meta = [json.loads((SITREP / d / "issue.json").read_text()) for d in past_issues()][::-1]
    rows = "\n".join(f'<li><a href="/sitrep/{m["date"]}/">{e(m["subject"])}</a> <span class="when">{fmt(m["date"])}</span></li>' for m in all_meta)
    archive = (f'<h1 style="margin-top:24px">The Sitrep</h1>\n<p>New jobs, closing dates and course dates in one short email every Monday.</p>\n'
               f'<div class="actions"><a class="btn primary" href="/#sitrep">Subscribe free</a><a class="btn" href="/sitrep/feed.xml">RSS feed</a></div>\n'
               + (f'<h2>Past issues</h2>\n<ul>\n{rows}\n</ul>' if rows else "<p>The first issue goes out on Monday.</p>"))
    (SITREP / "index.html").write_text(page("The Sitrep: weekly newsletter | Hostile Environment Jobs",
                                            "A weekly email of new EOD, security, medic and mine action jobs and course dates.", "/sitrep/", archive,
                                            f'<link rel="alternate" type="application/rss+xml" title="The Sitrep" href="{SITE}/sitrep/feed.xml">\n'))
    items = "".join(
        f'<item><title>{e(m["subject"])}</title><link>{SITE}/sitrep/{m["date"]}/</link><guid>{SITE}/sitrep/{m["date"]}/</guid>'
        f'<pubDate>{datetime.datetime.fromisoformat(m["date"] + "T06:00:00+00:00").strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>'
        f'<description>{e(m["preview"])}</description></item>\n' for m in all_meta[:20])
    (SITREP / "feed.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>\n'
                                     f"<title>The Sitrep from Hostile Environment Jobs</title><link>{SITE}/sitrep/</link>\n"
                                     "<description>Weekly hostile environment jobs and course dates.</description>\n" + items + "</channel></rss>\n")


if __name__ == "__main__":
    main()
