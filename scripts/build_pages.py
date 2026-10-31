"""Build a static page for each open job, a /jobs/ index, the /pay/ guide, the /deploy/ guide, the /leavers/ hub, the /app/ job alerts page, the /candidates/ talent pool, /work/ landing pages, sitemap.xml and calendar.ics from jobs.json and courses.json.

The main site is one page with #hash views, which Google can't index one job at a time.
These pages give every job its own address with JobPosting data for Google's job search.
Run from the repo root: python3 scripts/build_pages.py (the GitHub Action runs it on every
jobs.json change and once a day, so closed jobs drop off).
"""
import datetime
import html
import json
import pathlib
import re
import shutil

import employers as paid
import landing
from referral import booking_url, promo_text

SITE = "https://hostileenvironmentjobs.com"
ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = datetime.datetime.now(datetime.timezone.utc).date()

index = (ROOT / "index.html").read_text()
STYLE = re.search(r"<style>.*?</style>", index, re.S).group(0)
FONTS = re.search(r'<link rel="preconnect".*?display=swap">', index, re.S).group(0)
# Reuse the main page's header and footer, pointing their #view links back at the home page.
HEADER = re.sub(r'href="#', 'href="/#', re.search(r'<header class="top">.*?</header>', index, re.S).group(0))
FOOTER = re.sub(r'href="#', 'href="/#', re.search(r"<footer>.*?</footer>", index, re.S).group(0))
FOOTER = FOOTER.replace('<span id="yr"></span>', str(TODAY.year))
GOATCOUNTER = '<script data-goatcounter="https://hostileenvironmentjobs.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'

e = lambda t: html.escape(str(t or ""))


def is_open(j):
    c = j.get("closing")
    return not c or c == "Rolling" or (re.fullmatch(r"\d{4}-\d\d-\d\d", c) and datetime.date.fromisoformat(c) >= TODAY)


def fmt(d):
    return datetime.date.fromisoformat(d).strftime("%-d %b %Y")


def closing_text(j):
    c = j.get("closing")
    return "Open until filled" if not c or c == "Rolling" else "Closes " + fmt(c)


# Country codes for Google's job search, matched by name anywhere in the location text.
COUNTRIES = {
    "Afghanistan": "AF", "Angola": "AO", "Australia": "AU", "Bosnia": "BA", "Burkina Faso": "BF", "Cambodia": "KH",
    "Cameroon": "CM", "Canada": "CA", "Central African Republic": "CF", "Chad": "TD", "Colombia": "CO", "Croatia": "HR",
    "Cyprus": "CY", "Djibouti": "DJ", "DRC": "CD", "Congo": "CD", "Egypt": "EG", "Ethiopia": "ET", "France": "FR",
    "Germany": "DE", "Haiti": "HT", "Iraq": "IQ", "Israel": "IL", "Jordan": "JO", "Kenya": "KE", "Kosovo": "XK",
    "Laos": "LA", "Lebanon": "LB", "Libya": "LY", "Mali": "ML", "Mozambique": "MZ", "Myanmar": "MM", "Netherlands": "NL",
    "Niger": "NE", "Nigeria": "NG", "Norway": "NO", "Pakistan": "PK", "Palestine": "PS", "Gaza": "PS", "Qatar": "QA",
    "Saudi Arabia": "SA", "Senegal": "SN", "Somalia": "SO", "South Sudan": "SS", "Sri Lanka": "LK", "Sudan": "SD",
    "Switzerland": "CH", "Syria": "SY", "Tajikistan": "TJ", "Turkey": "TR", "Uganda": "UG", "Ukraine": "UA",
    "United Arab Emirates": "AE", "UAE": "AE", "United Kingdom": "GB", "UK": "GB", "United States": "US", "USA": "US",
    "Vietnam": "VN", "Western Sahara": "EH", "Yemen": "YE", "Zimbabwe": "ZW",
}


def country(location):
    found = [(m.start(), code) for name, code in COUNTRIES.items() for m in [re.search(rf"\b{re.escape(name)}\b", location)] if m]
    return min(found)[1] if found else None


def employment_type(contract):
    # Google's fixed values, guessed from the contract text; left out when it doesn't say.
    c = contract.lower()
    for pattern, value in ((r"contractor|freelance|rotational", "CONTRACTOR"), (r"\bmonths?\b|temporary|fixed[- ]term", "TEMPORARY"),
                           (r"full[- ]time|permanent", "FULL_TIME"), (r"part[- ]time", "PART_TIME")):
        if re.search(pattern, c):
            return value
    return None


def page(title, description, path, body, head_extra=""):
    url = SITE + path
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="Hostile Environment Jobs">
<meta property="og:image" content="{SITE}/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#111310">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon-96x96.png" type="image/png" sizes="96x96">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
{FONTS}
{head_extra}{STYLE}
</head>
<body>
{HEADER}
<main class="wrap">
{body}
</main>
{FOOTER}
{GOATCOUNTER}
</body>
</html>
"""


def job_page(j, employers=()):
    path = f"/jobs/{j['id']}/"
    profile = paid.profile_for(j, employers)
    reqs = j.get("requirements") or []
    description = f"<p>{e(j['summary'])}</p>" + (f"<ul>{''.join(f'<li>{e(r)}</li>' for r in reqs)}</ul>" if reqs else "")
    posting = {
        "@context": "https://schema.org", "@type": "JobPosting",
        "title": j["title"], "description": description,
        "identifier": {"@type": "PropertyValue", "name": j["employer"], "value": j["id"]},
        "datePosted": j.get("posted"),
        "hiringOrganization": {"@type": "Organization", "name": j["employer"], **({"sameAs": profile["website"]} if profile and profile.get("website") else {})},
        "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": j["location"]}},
        "directApply": False, "url": SITE + path,
    }
    if employment_type(j.get("contract", "")):
        posting["employmentType"] = employment_type(j["contract"])
    if country(j["location"]):
        posting["jobLocation"]["address"]["addressCountry"] = country(j["location"])
    if j.get("closing") and j["closing"] != "Rolling":
        posting["validThrough"] = j["closing"] + "T23:59:59Z"
    ld = json.dumps({k: v for k, v in posting.items() if v}, ensure_ascii=False).replace("</", "<\\/")
    body = f"""<a class="back" href="/#jobs">&larr; All jobs</a>
<article class="detail">
  <span class="tag">{e(j['category'])}</span>{' <span class="tag featured-tag">Featured</span>' if j.get('_featured') else ''}
  <h1>{e(j['title'])}</h1>
  <div class="who">{f'<a href="/employers/{e(profile["id"])}/">{e(j["employer"])}</a>' if profile else e(j['employer'])} · {e(j['location'])}</div>
  <p>{e(j['summary'])}</p>
  <dl><dt>Closing</dt><dd>{closing_text(j)}</dd><dt>Contract</dt><dd>{e(j.get('contract'))}</dd><dt>Salary</dt><dd>{e(j.get('salary') or 'Not stated')}</dd>
    <dt>Requirements</dt><dd>{'<br>'.join(e(r) for r in reqs)}</dd><dt>Added</dt><dd>{fmt(j['posted']) if j.get('posted') else ''}</dd></dl>
  <div class="actions">
    <a class="btn primary" href="{e(j['apply_url'])}" target="_blank" rel="noopener">Apply on employer's site</a>
    <a class="btn" href="https://www.facebook.com/sharer/sharer.php?u={e(SITE + path)}" target="_blank" rel="noopener">Share on Facebook</a>
  </div>
</article>"""
    title = f"{j['title']}, {j['location']} | Hostile Environment Jobs"
    desc = f"{j['employer']}: {j['summary']}"
    return page(title, desc, path, body, f'<script type="application/ld+json">{ld}</script>\n')


def jobs_index(jobs, browse=""):
    cards = "\n".join(f"""<article class="detail{' featured' if j.get('_featured') else ''}">
  <span class="tag">{e(j['category'])}</span>{' <span class="tag featured-tag">Featured</span>' if j.get('_featured') else ''}
  <h2><a href="/jobs/{e(j['id'])}/">{e(j['title'])}</a></h2>
  <div class="who">{e(j['employer'])} · {e(j['location'])} · {closing_text(j)}</div>
  <p>{e(j['summary'])}</p>
</article>""" for j in jobs)
    body = f"""<a class="back" href="/#jobs">&larr; Search and filter jobs</a>
<h1 style="margin-top:24px">Open jobs</h1>
<p>EOD, search, mine action, security, medic and support jobs in hostile environments. Every listing links to the employer's own advert.</p>
{browse}
{cards}"""
    return page("Open jobs | Hostile Environment Jobs", "All open EOD, security, medic and mine action jobs on Hostile Environment Jobs.", "/jobs/", body)


def ics_text(t):
    return str(t or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line):
    # Calendar files cap lines at 75 bytes; longer ones carry on after a newline and a space.
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > 75:
            out.append(cur)
            cur = " "
        cur += ch
    return "\r\n".join(out + [cur])


def calendar(jobs, courses):
    """calendar.ics: course start dates and job closing dates as all-day events people can subscribe to.

    Each is a one-day event (a four-week course would otherwise fill people's calendars). Events stay in the feed for 90 days after they pass, so they don't vanish from people's calendars the next morning.
    """
    keep_from = TODAY - datetime.timedelta(days=90)
    is_date = lambda d: bool(re.fullmatch(r"\d{4}-\d\d-\d\d", d or ""))
    events = []
    for c in courses:
        if c.get("sample") or not is_date(c.get("start")):
            continue
        start = datetime.date.fromisoformat(c["start"])
        if start < keep_from:
            continue
        facts = ". ".join(x for x in (f"{c['provider']}, {c['location']}", c.get("duration"), c.get("price")) if x)
        link, code = booking_url(c, "calendar"), promo_text(c)
        text = f"{facts}\n{c.get('summary', '')}\n\nBook: {link}" + (f" ({code})" if code else "")
        events.append((start, f"course-{c['id']}", f"Course starts: {c['title']} ({c['location']})", c["location"],
                       start + datetime.timedelta(days=1), text, link, c.get("posted")))
    for j in jobs:
        if j.get("sample") or not is_date(j.get("closing")):
            continue
        day = datetime.date.fromisoformat(j["closing"])
        if day < keep_from:
            continue
        url = f"{SITE}/jobs/{j['id']}/"
        text = f"{j['employer']}, {j['location']}\n{j.get('summary', '')}\n\nDetails and how to apply: {url}"
        events.append((day, f"job-{j['id']}", f"Job closes: {j['title']} ({j['employer']})", j["location"],
                       day + datetime.timedelta(days=1), text, url, j.get("posted")))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Hostile Environment Jobs//Calendar//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Hostile Environment Jobs", "X-WR-TIMEZONE:UTC",
             "X-WR-CALDESC:Course start dates and job closing dates from hostileenvironmentjobs.com",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for start, uid, summary, location, end, text, url, posted in sorted(events):
        # DTSTAMP comes from the listing date, not the build time, so the file only changes when the listings do.
        stamp = (posted or "2026-01-01").replace("-", "") + "T000000Z"
        lines += ["BEGIN:VEVENT", f"UID:{uid}@hostileenvironmentjobs.com", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{end:%Y%m%d}",
                  f"SUMMARY:{ics_text(summary)}", f"LOCATION:{ics_text(location)}", f"DESCRIPTION:{ics_text(text)}",
                  f"URL:{url}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(ics_fold(l) for l in lines) + "\r\n", len(events)


def main():
    all_jobs = json.loads((ROOT / "jobs.json").read_text())
    courses = json.loads((ROOT / "courses.json").read_text())
    ics, n_events = calendar(all_jobs, courses)
    (ROOT / "calendar.ics").write_bytes(ics.encode())
    jobs = all_jobs
    jobs = sorted((j for j in jobs if is_open(j) and not j.get("sample") and j.get("id")), key=lambda j: j.get("posted", ""), reverse=True)
    employers = paid.load(ROOT, TODAY)
    for j in jobs:
        j["_featured"] = paid.is_featured(j, employers, TODAY)
    jobs.sort(key=lambda j: not j["_featured"])  # featured first, newest first within each group
    out = ROOT / "jobs"
    if out.exists():
        shutil.rmtree(out)
    for j in jobs:
        (out / j["id"]).mkdir(parents=True)
        (out / j["id"] / "index.html").write_text(job_page(j, employers))
    out.mkdir(exist_ok=True)
    landing_urls, browse = landing.build(ROOT, jobs, courses, page, e, closing_text, SITE, COUNTRIES, country, TODAY)
    (out / "index.html").write_text(jobs_index(jobs, browse))

    # Employer profiles last only while paid for, so the folder is rebuilt each time.
    emp_out = ROOT / "employers"
    if emp_out.exists():
        shutil.rmtree(emp_out)
    emp_out.mkdir()
    profile_urls = []
    for x in employers:
        path, html_text = paid.profile_page(x, [j for j in jobs if paid.profile_for(j, [x])], page, e, closing_text, SITE)
        (ROOT / path.strip("/")).mkdir(parents=True)
        (ROOT / path.strip("/") / "index.html").write_text(html_text)
        profile_urls.append((SITE + path, "weekly"))
    (emp_out / "index.html").write_text(paid.employers_index(employers, page, e))
    (ROOT / "advertise").mkdir(exist_ok=True)
    (ROOT / "advertise" / "index.html").write_text(paid.advertise_page(page, e))

    # Closed jobs' pages are deleted, so old shared links land here instead.
    (ROOT / "404.html").write_text(page("Page not found | Hostile Environment Jobs", "This page or job has gone.", "/404.html",
        '<h1 style="margin-top:32px">Not found</h1>\n<p>This job may have closed, or the link is wrong.</p>\n'
        '<div class="actions"><a class="btn primary" href="/#jobs">See open jobs</a></div>').replace('<meta name="description"', '<meta name="robots" content="noindex">\n<meta name="description"'))

    # Pay guide: the page reads pay.json and jobs.json in the browser, so it only needs rebuilding when the header changes.
    pay = (ROOT / "scripts" / "pay.html").read_text()
    pay_style = re.match(r"\s*<style>.*?</style>\n", pay, re.S).group(0)
    (ROOT / "pay").mkdir(exist_ok=True)
    (ROOT / "pay" / "index.html").write_text(page("Pay guide: day rates and salaries | Hostile Environment Jobs",
        "Indicative day rates and salaries for EOD, mine action, security, medic and support roles, plus anonymous pay reports.",
        "/pay/", pay[len(pay_style):], pay_style))

    # Kit list: static page drawn from kit.json, with supplier links where we know a maker or dealer.
    kit_data = json.loads((ROOT / "kit.json").read_text())
    kit = (ROOT / "scripts" / "kit.html").read_text()
    kit_style = re.match(r"\s*<style>.*?</style>\n", kit, re.S).group(0)
    sup = kit_data["suppliers"]
    def kit_row(it):
        links = ", ".join(f'<a href="{e(sup[s]["url"])}" rel="noopener">{e(sup[s]["name"])}</a>' for s in it.get("suppliers", []))
        return (f'<li class="kit-row"><div><h3>{e(it["item"])}</h3>'
                + (f'<p class="note">{e(it["note"])}</p>' if it.get("note") else "")
                + (f'<p class="where">Where to look: {links}</p>' if links else "")
                + f'</div><div class="qty">{e(it["qty"])}' + (f'<small>{e(it["unit"])}</small>' if it.get("unit") else "") + "</div></li>")
    kit_body = "".join(f'<section class="kit-section"><h2>{e(sec["name"])}</h2><ul class="kit-list">{"".join(kit_row(it) for it in sec["items"])}</ul></section>' for sec in kit_data["sections"])
    kit_body += "".join(f'<p class="kit-foot">{e(n)}</p>' for n in kit_data.get("notes", []))
    (ROOT / "kit").mkdir(exist_ok=True)
    (ROOT / "kit" / "index.html").write_text(page("EOD team kit list: what a mine action team carries | Hostile Environment Jobs",
        "A typical humanitarian EOD and mine action multi-task team kit list: detectors, PPE, demolition, comms, medical and CASEVAC, hand tools and welfare, with quantities and where to buy. Printable checklist.",
        "/kit/", kit[len(kit_style):].replace("<!--KIT-->", kit_body), kit_style))

    # Job alerts app: like the pay guide, the page does its work in the browser.
    app = (ROOT / "scripts" / "app.html").read_text()
    app_style = re.match(r"\s*<style>.*?</style>\n", app, re.S).group(0)
    (ROOT / "app").mkdir(exist_ok=True)
    (ROOT / "app" / "index.html").write_text(page("Job alerts app: new jobs on your phone | Hostile Environment Jobs",
        "Get a notification on your phone when a new EOD, mine action, security, medic or support job matching what you want goes up, plus a free rotation tracker that counts down to your next leave.",
        "/app/", app[len(app_style):], app_style).replace('<a href="/app/">', '<a href="/app/" aria-current="page">', 1))

    # Talent pool: operators' profiles and employers' search, kept by the alerts Worker and drawn in the browser.
    tp = (ROOT / "scripts" / "candidates.html").read_text()
    tp_style = re.match(r"\s*<style>.*?</style>\n", tp, re.S).group(0)
    (ROOT / "candidates").mkdir(exist_ok=True)
    (ROOT / "candidates" / "index.html").write_text(page("Talent pool: get found by hostile environment employers | Hostile Environment Jobs",
        "Free for EOD, search, mine action, security, HE medic and support operators: say when you're available and let checked employers find you. Your details stay hidden until you accept.",
        "/candidates/", tp[len(tp_style):], tp_style).replace('<a href="/candidates/">', '<a href="/candidates/" aria-current="page">', 1))

    # Deployment guide: reads deploy.json (refreshed daily by scripts/build_deploy.py) in the browser.
    dep = (ROOT / "scripts" / "deploy.html").read_text().replace("<!--MAP-->", (ROOT / "scripts" / "deploy-map.svg").read_text())
    dep_style = re.match(r"\s*<style>.*?</style>\n", dep, re.S).group(0)
    (ROOT / "deploy").mkdir(exist_ok=True)
    (ROOT / "deploy" / "index.html").write_text(page("Deployment guide: Horn of Africa and MENA | Hostile Environment Jobs",
        "Travel advice levels, recent security updates, live weather, visas and cultural pointers for the Horn of Africa, Middle East and North Africa.",
        "/deploy/", dep[len(dep_style):], dep_style).replace('<a href="/deploy/">', '<a href="/deploy/" aria-current="page">', 1))

    # Service leaver hub: static advice plus the open courses, read from courses.json in the browser.
    lv = (ROOT / "scripts" / "leavers.html").read_text()
    lv_style = re.match(r"\s*<style>.*?</style>\n", lv, re.S).group(0)
    (ROOT / "leavers").mkdir(exist_ok=True)
    (ROOT / "leavers" / "index.html").write_text(page("Service leaver hub: resettlement, ELCAS and your first contract | Hostile Environment Jobs",
        "Leaving the forces for EOD, security, medic or mine action work? Resettlement funding (ELC, IRTC, SLC), which courses count, what your trade fits and a first contract checklist.",
        "/leavers/", lv[len(lv_style):], lv_style).replace('<a href="/leavers/">', '<a href="/leavers/" aria-current="page">', 1))

    urls = [(SITE + "/", "daily"), (SITE + "/jobs/", "daily"), (SITE + "/pay/", "weekly"), (SITE + "/deploy/", "daily"), (SITE + "/leavers/", "monthly"), (SITE + "/cv/", "monthly"), (SITE + "/app/", "monthly"), (SITE + "/candidates/", "monthly"), (SITE + "/advertise/", "monthly"), (SITE + "/kit/", "monthly")] + [(f"{SITE}/jobs/{j['id']}/", "weekly") for j in jobs]
    urls += landing_urls + ([(SITE + "/employers/", "weekly")] if employers else []) + profile_urls
    (ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><changefreq>{f}</changefreq></url>\n" for u, f in urls) + "</urlset>\n")
    print(f"Built {len(jobs)} job pages, {len(employers)} employer profiles and {n_events} calendar events")


if __name__ == "__main__":
    main()
