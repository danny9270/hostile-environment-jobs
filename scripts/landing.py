"""Landing pages for the searches people make, like "EOD jobs", "close protection jobs" or "jobs in Ukraine".

Each page at /work/<slug>/ has a short guide to the work plus the open jobs and courses that match, so it stays
current as listings come and go. Topic pages are always built; a country page is only built while it has an open job.
build_pages.py calls build() and adds the pages to the sitemap.
"""
import re
import shutil

TOPICS = [
    {"slug": "eod-jobs", "name": "EOD jobs", "title": "EOD jobs: bomb disposal and UXO work",
     "categories": ["EOD", "IEDD", "Survey & Clearance"], "keywords": ["eod", "uxo", "explosive ordnance", "iedd", "bomb disposal", "ammunition technician"],
     "course_types": ["EOD & IEDD"],
     "intro": ["Explosive ordnance disposal (EOD) work covers clearing unexploded bombs, shells and mines, from UK construction sites to post-conflict clearance overseas. Most roles ask for a military EOD background (ex-Royal Engineers, RLC Ammunition Technicians, RAF and Navy clearance divers) and an IMAS EOD level, usually EOD 3 or higher for team leaders.",
               "Contracts range from permanent UK UXO jobs to rotational overseas posts. Pay is usually a day rate, often higher in high-risk countries."]},
    {"slug": "uxo-jobs-uk", "name": "UXO jobs in the UK", "title": "UXO jobs in the UK: unexploded ordnance engineers and technicians",
     "categories": ["EOD"], "keywords": ["uxo"], "country": "GB", "course_types": ["EOD & IEDD"],
     "intro": ["UK unexploded ordnance (UXO) companies survey and clear building sites, offshore wind farms and cable routes of wartime bombs. Typical roles are UXO engineers, UXO technicians, magnetometer survey operators and site supervisors.",
               "Most UK UXO jobs want an EOD background or recognised EOD qualification, a full driving licence and site cards such as CSCS. Work is often project-based and involves travel around the country."]},
    {"slug": "mine-action-jobs", "name": "Mine action jobs", "title": "Mine action and demining jobs",
     "categories": ["Survey & Clearance", "Search"], "keywords": ["mine action", "demining", "hma", "non-technical survey", "landmine", "mine clearance"],
     "course_types": ["EOD & IEDD"],
     "intro": ["Humanitarian mine action (HMA) clears landmines and explosive remnants of war so people can use their land again. Jobs include deminers, team leaders, technical field managers, non-technical survey and explosive ordnance risk education officers, as well as programme, operations and quality managers.",
               "International roles usually ask for IMAS EOD qualifications and field experience. Most employers are NGOs, the UN and commercial clearance companies, working in places like Ukraine, Iraq, Syria, Afghanistan, Cambodia and Angola."]},
    {"slug": "close-protection-jobs", "name": "Close protection jobs", "title": "Close protection jobs in hostile environments",
     "categories": [], "keywords": ["close protection", "cpo", "psd", "protective security", "bodyguard"],
     "course_types": ["Security"],
     "intro": ["Close protection officers (CPOs) keep clients safe in high-risk places, often as part of a protective security detail (PSD) with armoured vehicles. Common clients are embassies, aid agencies, media and oil and gas firms.",
               "Most hostile environment CP jobs want an SIA Close Protection licence or equivalent, recent military or police experience, a medical qualification such as FREC 3 and, for many contracts, a Five Eyes or EU passport."]},
    {"slug": "security-jobs", "name": "Hostile environment security jobs", "title": "Hostile environment security jobs",
     "categories": ["Security", "Security Risk & Analysis"], "keywords": ["security officer", "security manager", "security advisor", "security adviser", "guard"],
     "course_types": ["Security", "HEAT"],
     "intro": ["Security work in hostile environments runs from static guarding and convoy work to security management for NGOs and the UN. Roles include guards, team leaders, security managers, safety and security advisers and access officers.",
               "Requirements vary a lot: commercial contracts favour ex-forces and police with SIA licences, while NGO safety and security roles also want humanitarian experience, languages and strong report writing."]},
    {"slug": "ngo-safety-security-jobs", "name": "NGO safety and security jobs", "title": "NGO safety and security jobs",
     "categories": [], "keywords": ["safety and security", "safety & security", "humanitarian access", "ngo"],
     "course_types": ["HEAT", "Security"],
     "intro": ["Aid agencies and the UN employ safety and security advisers to keep staff safe in conflict zones and disasters. The work is about risk assessment, security plans, incident tracking, training staff and building acceptance with local communities.",
               "Employers often ask for a HEAT certificate, experience in the region, and French, Arabic or another local language. Many people move into these roles from the military, police or security management."]},
    {"slug": "maritime-security-jobs", "name": "Maritime security jobs", "title": "Maritime security jobs: PMSO and anti-piracy work",
     "categories": ["Maritime Security"], "keywords": ["maritime", "anti-piracy", "pmso", "mso", "vessel"],
     "course_types": [],
     "intro": ["Maritime security officers (MSOs and PMSOs) protect merchant ships transiting high-risk areas such as the Gulf of Aden, Red Sea, Gulf of Guinea and Indian Ocean. Teams embark for a voyage, then rotate home.",
               "Employers usually want ex-forces with weapons experience, STCW and ship security officer (SSO) certificates, a seafarer's medical and a valid seaman's book."]},
    {"slug": "hostile-environment-medic-jobs", "name": "Hostile environment medic jobs", "title": "Hostile environment medic and paramedic jobs",
     "categories": ["Medical"], "keywords": ["medic", "paramedic", "nurse", "medical"],
     "course_types": ["Medical"],
     "intro": ["Hostile environment medics support security teams, clearance programmes, oil and gas sites and aid agencies far from hospital care. Roles include remote paramedics, HE medics on protective details, site medics and humanitarian health advisers.",
               "Most jobs want HCPC registration as a paramedic or nurse, or a military medic background, plus pre-hospital trauma qualifications. Some security contracts also want an SIA licence."]},
    {"slug": "k9-explosive-detection-jobs", "name": "K9 and explosive detection dog jobs", "title": "K9 handler and explosive detection dog jobs",
     "categories": ["K9"], "keywords": ["k9", "dog handler", "detection dog", "mdd", "edd"],
     "course_types": [],
     "intro": ["K9 handlers work explosive detection dogs (EDDs) and mine detection dogs (MDDs) at airports, venues, embassies and clearance sites. Many come from military working dog units or police dog sections.",
               "Jobs often want handler certification for explosives search, a clean record that passes security vetting, and the ability to look after dogs on deployment."]},
    {"slug": "security-risk-analyst-jobs", "name": "Security risk analyst jobs", "title": "Security risk and intelligence analyst jobs",
     "categories": ["Security Risk & Analysis"], "keywords": ["analyst", "intelligence", "risk analysis", "threat assessment"],
     "course_types": [],
     "intro": ["Security risk analysts track threats, write assessments and brief clients and field teams on what is happening in fragile countries. Employers include risk consultancies, insurers, NGOs and the UN.",
               "Analysts usually need strong writing, open-source research skills and regional knowledge, often with a language. Military intelligence, journalism and international relations backgrounds are all common routes in."]},
    {"slug": "heat-courses", "name": "HEAT courses", "title": "HEAT courses: hostile environment awareness training",
     "categories": [], "keywords": [], "course_types": ["HEAT"], "courses_first": True,
     "intro": ["Hostile environment awareness training (HEAT, also called HEFAT when it includes first aid) prepares aid workers, journalists and contractors to stay safe in dangerous places. Courses usually last three to five days and cover kidnap and hostage survival, checkpoints, first aid, vehicle safety and dealing with explosive hazards.",
               "Many NGOs, the UN and media employers require a HEAT certificate before deploying staff, so it is often the first course people book."]},
    {"slug": "eod-courses", "name": "EOD and IEDD courses", "title": "EOD and IEDD courses",
     "categories": [], "keywords": [], "course_types": ["EOD & IEDD"], "courses_first": True,
     "intro": ["EOD and IEDD courses train people to the International Mine Action Standards (IMAS) EOD levels, from EOD 1 for deminers up to EOD 3 and 4 for team leaders and supervisors, and in improvised explosive device disposal.",
               "Civilian courses are mainly for people with some military background. Check that a course is accredited and recognised by the employers you want to work for."]},
]


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def text_of(j):
    return " ".join([j.get("title", ""), j.get("summary", ""), j.get("category", ""), " ".join(j.get("requirements") or [])]).lower()


def topic_jobs(t, jobs, country):
    def ok(j):
        if t.get("country") and country(j.get("location", "")) != t["country"]:
            return False
        txt = text_of(j)
        return j.get("category") in t["categories"] or any(re.search(rf"\b{re.escape(k)}\b", txt) for k in t["keywords"])
    return [j for j in jobs if ok(j)] if t["categories"] or t["keywords"] else []


def countries_in(location, names):
    # Every country a job names, as (code, display name). names maps codes to the first spelling in COUNTRIES.
    found = {}
    for name, code in names["all"].items():
        if re.search(rf"\b{re.escape(name)}\b", location):
            found[code] = names["display"][code]
    return found


def job_cards(jobs, e, closing_text):
    return "\n".join(f"""<article class="detail{' featured' if j.get('_featured') else ''}">
  <span class="tag">{e(j['category'])}</span>{' <span class="tag featured-tag">Featured</span>' if j.get('_featured') else ''}
  <h3><a href="/jobs/{e(j['id'])}/">{e(j['title'])}</a></h3>
  <div class="who">{e(j['employer'])} · {e(j['location'])} · {closing_text(j)}</div>
  <p>{e(j['summary'])}</p>
</article>""" for j in jobs)


def course_cards(courses, e):
    return "\n".join(f"""<article class="detail">
  <span class="tag">{e(c['type'])}</span>
  <h3><a href="{e(c['url'])}" target="_blank" rel="noopener">{e(c['title'])}</a></h3>
  <div class="who">{e(c['provider'])} · {e(c['location'])}{' · Starts ' + e(c['start']) if c.get('start') else ''}</div>
  <p>{e(c.get('summary'))}</p>
</article>""" for c in courses)


def browse_links(e, extra=()):
    links = [(f"/work/{t['slug']}/", t["name"]) for t in TOPICS] + list(extra)
    return '<nav class="chips" aria-label="Browse by type">' + "".join(f'<a class="btn" href="{u}">{e(n)}</a>' for u, n in links) + "</nav>"


ALERTS = """<div class="actions"><a class="btn primary" href="/app/">Get alerts for new jobs like these</a>
  <a class="btn" href="/#sitrep">Weekly Sitrep email</a> <a class="btn" href="/pay/">Pay guide</a> <a class="btn" href="/cv/">CV builder</a></div>"""


def landing(slug, h1, intro, jobs, courses, courses_first, page, e, closing_text, related, title, description):
    jobs_html = f"<h2>Open jobs ({len(jobs)})</h2>\n" + (job_cards(jobs, e, closing_text) if jobs else
        '<p>No open jobs match right now. New jobs go up every couple of days: get an alert on your phone the moment one does.</p>')
    courses_html = (f"<h2>Upcoming courses ({len(courses)})</h2>\n" + course_cards(courses, e)) if courses or courses_first else ""
    if courses_first and not courses:
        courses_html += '<p>No upcoming courses listed right now. <a href="/#courses">See all courses</a> or <a href="/#post">list a course free</a>.</p>'
    sections = [courses_html, jobs_html] if courses_first else [jobs_html, courses_html]
    body = f"""<a class="back" href="/#jobs">&larr; Search and filter all jobs</a>
<h1 style="margin-top:24px">{e(h1)}</h1>
{''.join(f'<p>{e(p)}</p>' for p in intro)}
{ALERTS}
{''.join(sections)}
<h2>Browse more</h2>
{related}"""
    return page(title, description, f"/work/{slug}/", body)


def build(root, jobs, courses, page, e, closing_text, site, countries, country, today):
    """Writes /work/ and returns [(url, changefreq)] for the sitemap."""
    out = root / "work"
    if out.exists():
        shutil.rmtree(out)
    open_courses = sorted((c for c in courses if not c.get("sample") and (not c.get("start") or not re.fullmatch(r"\d{4}-\d\d-\d\d", c["start"]) or c["start"] >= today.isoformat())),
                          key=lambda c: c.get("start") or "9999")
    display = {}
    for name, code in countries.items():
        display.setdefault(code, name)
    names = {"all": countries, "display": display}

    by_country = {}
    for j in jobs:
        for code, name in countries_in(j.get("location", ""), names).items():
            by_country.setdefault(code, (name, []))[1].append(j)
    country_pages = sorted(((f"jobs-in-{slugify(name)}", name, js) for name, js in by_country.values()), key=lambda x: -len(x[2]))
    country_links = [(f"/work/{s}/", f"Jobs in {n}") for s, n, _ in country_pages]
    related = browse_links(e, country_links)

    urls = [(site + "/work/", "daily")]
    for t in TOPICS:
        js = topic_jobs(t, jobs, country)
        cs = [c for c in open_courses if c.get("type") in t["course_types"]]
        n = len(cs) if t.get("courses_first") else len(js)
        what = "upcoming courses" if t.get("courses_first") else "open jobs"
        desc = f"{t['title']}: {n} {what} on Hostile Environment Jobs, plus what employers look for and how to get in."
        (out / t["slug"]).mkdir(parents=True)
        (out / t["slug"] / "index.html").write_text(landing(t["slug"], t["title"], t["intro"], js, cs, t.get("courses_first"), page, e, closing_text,
            related, f"{t['title']} | Hostile Environment Jobs", desc))
        urls.append((f"{site}/work/{t['slug']}/", "daily"))
    for slug, name, js in country_pages:
        intro = [f"Open EOD, mine action, security, medic and support jobs in {name}, checked and linked to each employer's own advert. "
                 "Hostile environment work changes fast, so check the employer's travel and security requirements before you apply."]
        (out / slug).mkdir(parents=True)
        (out / slug / "index.html").write_text(landing(slug, f"Jobs in {name}", intro, js, [], False, page, e, closing_text, related,
            f"Hostile environment jobs in {name} | Hostile Environment Jobs",
            f"{len(js)} open EOD, security, medic and mine action jobs in {name} on Hostile Environment Jobs."))
        urls.append((f"{site}/work/{slug}/", "daily"))

    index = f"""<a class="back" href="/#jobs">&larr; Search and filter all jobs</a>
<h1 style="margin-top:24px">Browse jobs and courses</h1>
<p>Guides to each kind of hostile environment work, with the open jobs and courses that match.</p>
<h2>By type of work</h2>
{browse_links(e)}
<h2>By country</h2>
<nav class="chips" aria-label="Browse by country">{''.join(f'<a class="btn" href="{u}">{e(n)}</a>' for u, n in country_links)}</nav>
{ALERTS}"""
    (out / "index.html").write_text(page("Browse hostile environment jobs by type and country | Hostile Environment Jobs",
        "EOD, mine action, close protection, maritime security, HE medic and K9 jobs and courses, by type of work and by country.", "/work/", index))
    return urls, browse_links(e)
