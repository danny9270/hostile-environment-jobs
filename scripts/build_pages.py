"""Build a static page for each open job, a /jobs/ index and sitemap.xml from jobs.json.

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
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
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


def job_page(j):
    path = f"/jobs/{j['id']}/"
    reqs = j.get("requirements") or []
    description = f"<p>{e(j['summary'])}</p>" + (f"<ul>{''.join(f'<li>{e(r)}</li>' for r in reqs)}</ul>" if reqs else "")
    posting = {
        "@context": "https://schema.org", "@type": "JobPosting",
        "title": j["title"], "description": description,
        "identifier": {"@type": "PropertyValue", "name": j["employer"], "value": j["id"]},
        "datePosted": j.get("posted"),
        "hiringOrganization": {"@type": "Organization", "name": j["employer"]},
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
  <span class="tag">{e(j['category'])}</span>
  <h1>{e(j['title'])}</h1>
  <div class="who">{e(j['employer'])} · {e(j['location'])}</div>
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


def jobs_index(jobs):
    cards = "\n".join(f"""<article class="detail">
  <span class="tag">{e(j['category'])}</span>
  <h2><a href="/jobs/{e(j['id'])}/">{e(j['title'])}</a></h2>
  <div class="who">{e(j['employer'])} · {e(j['location'])} · {closing_text(j)}</div>
  <p>{e(j['summary'])}</p>
</article>""" for j in jobs)
    body = f"""<a class="back" href="/#jobs">&larr; Search and filter jobs</a>
<h1 style="margin-top:24px">Open jobs</h1>
<p>EOD, search, mine action, security, medic and support jobs in hostile environments. Every listing links to the employer's own advert.</p>
{cards}"""
    return page("Open jobs | Hostile Environment Jobs", "All open EOD, security, medic and mine action jobs on Hostile Environment Jobs.", "/jobs/", body)


def main():
    jobs = json.loads((ROOT / "jobs.json").read_text())
    jobs = sorted((j for j in jobs if is_open(j) and not j.get("sample") and j.get("id")), key=lambda j: j.get("posted", ""), reverse=True)
    out = ROOT / "jobs"
    if out.exists():
        shutil.rmtree(out)
    for j in jobs:
        (out / j["id"]).mkdir(parents=True)
        (out / j["id"] / "index.html").write_text(job_page(j))
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(jobs_index(jobs))

    # Closed jobs' pages are deleted, so old shared links land here instead.
    (ROOT / "404.html").write_text(page("Page not found | Hostile Environment Jobs", "This page or job has gone.", "/404.html",
        '<h1 style="margin-top:32px">Not found</h1>\n<p>This job may have closed, or the link is wrong.</p>\n'
        '<div class="actions"><a class="btn primary" href="/#jobs">See open jobs</a></div>').replace('<meta name="description"', '<meta name="robots" content="noindex">\n<meta name="description"'))

    urls = [(SITE + "/", "daily"), (SITE + "/jobs/", "daily")] + [(f"{SITE}/jobs/{j['id']}/", "weekly") for j in jobs]
    (ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><changefreq>{f}</changefreq></url>\n" for u, f in urls) + "</urlset>\n")
    print(f"Built {len(jobs)} job pages")


if __name__ == "__main__":
    main()
