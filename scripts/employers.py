"""Paid extras: featured jobs, employer profile pages and the Advertise page.

build_pages.py imports this. Employers who pay for a profile go in employers.json; a job is featured
while its "featured_until" date hasn't passed, or while its employer's profile is live.
A profile's "offer" is a deal for our users (shown on its page, its jobs and courses, and /deals/), and
"booking_email" turns on a "Request a booking" form for its courses, copied to contact@ so we see every booking.
An employer with "partner": true is a founding partner: the featured employer plan given free until its
"featured_until" date, shown with a "Founding partner" badge and named on the Advertise page.
"""
import datetime
import json
import re

from referral import booking_url, promo_text

# Prices and what each plan includes. Change them here and the Advertise page follows.
PLANS = [
    {"name": "Standard listing", "price": "Free", "per": "always",
     "points": ["Listed on the site until it closes", "Its own page, found on Google for Jobs", "Shared in the Facebook group"],
     "payment_link": None},
    {"name": "Featured job", "price": "£49", "per": "per job, 30 days",
     "points": ["Pinned to the top of the jobs list", "Highlighted card with a Featured badge",
                "Its own post on our Facebook and LinkedIn pages", "Shared in the Facebook group"],
     "payment_link": ""},
    {"name": "Featured employer", "price": "£149", "per": "90 days",
     "points": ["Company profile page with your logo, story and every open job", "All your jobs featured for 90 days",
                "Your name links to your profile on every listing", "A spotlight post on our Facebook and LinkedIn pages",
                "90 days of talent pool search included"],
     "payment_link": "", "best": True},
    {"name": "Candidate search", "price": "£99", "per": "30 days",
     "points": ["Search operators who are available now, by trade, region and start date",
                "Ask to get in touch; their name, contact details and CV come through when they accept",
                "Every employer checked before they can search"],
     "payment_link": "/candidates/#hiring"},
]
# Each "payment_link" is a Stripe Payment Link (https://buy.stripe.com/...) or a page on this site. Left empty, the button asks people to email us instead.
# Candidate search is paid for on the talent pool page itself, once we've approved the employer.

def is_date(d):
    return bool(re.fullmatch(r"\d{4}-\d\d-\d\d", d or ""))


def live_until(until, today):
    """A profile with no end date runs until it's removed; one with a date stops after that day."""
    return not until or (is_date(until) and datetime.date.fromisoformat(until) >= today)


def load(root, today):
    path = root / "employers.json"
    data = json.loads(path.read_text()) if path.exists() else []
    return [x for x in data if x.get("id") and x.get("name") and live_until(x.get("featured_until"), today)]


def profile_for(job, employers):
    names = lambda x: [x["name"], *x.get("aliases", [])]
    return next((x for x in employers if job.get("employer") in names(x)), None)


def is_featured(job, employers, today):
    until = job.get("featured_until")
    return (is_date(until) and datetime.date.fromisoformat(until) >= today) or profile_for(job, employers) is not None


def badge(job, employers):
    """Badge text for a featured job: founding partners (free featured employer plan) get their own badge."""
    profile = profile_for(job, employers)
    return "Founding partner" if profile and profile.get("partner") else "Featured"


def courses_for(x, courses, today):
    names = [x["name"], *x.get("aliases", [])]
    return [c for c in courses if c.get("provider") in names and c.get("id") and not c.get("sample")
            and (not is_date(c.get("start")) or datetime.date.fromisoformat(c["start"]) >= today)]


def offer_box(x, e):
    """The partner's deal for our users, as a highlighted line."""
    if not x.get("offer"):
        return ""
    return f'<p class="offer"><b>{"Founding partner offer" if x.get("partner") else "Offer"}:</b> {e(x["offer"])}</p>'


def booking_form(x, courses, e):
    """A booking request that goes to contact@ with the provider copied in, so every booking is on record."""
    if not (x.get("booking_email") and courses):
        return ""
    opts = "".join(f'<option value="{e(c["id"])}">{e(c["title"])}{" (" + e(c["start"]) + ")" if is_date(c.get("start")) else ""}</option>' for c in courses)
    # The provider's address is put together in the browser so spam bots don't collect it.
    user, _, domain = x["booking_email"].partition("@")
    return f"""<h2 id="book">Request a booking</h2>
<p>Send your details and {e(x['name'])} will reply to confirm dates, price and payment.{' Mention Hostile Environment Jobs for the partner offer.' if x.get('offer') else ''}</p>
<form id="book-form" method="POST" data-u="{e(user)}" data-d="{e(domain)}">
  <input type="hidden" name="_subject" value="Course booking request from Hostile Environment Jobs: {e(x['name'])}">
  <input type="hidden" name="_next" value="https://hostileenvironmentjobs.com/employers/{e(x['id'])}/?sent=1#book">
  <input type="hidden" name="_cc" id="book-cc">
  <input type="hidden" name="provider" value="{e(x['name'])}">
  <input type="text" name="_honey" style="display:none" tabindex="-1" autocomplete="off">
  <label>Course <select name="course" id="book-course">{opts}</select></label>
  <div class="row">
    <label>Your name <input name="name" required></label>
    <label>Email <input name="email" type="email" required></label>
  </div>
  <div class="row">
    <label>Phone (optional) <input name="phone" type="tel"></label>
    <label>Places <input name="places" type="number" min="1" value="1"></label>
  </div>
  <label>Anything else (funding such as ELCAS, dates that suit you) <textarea name="details" rows="3"></textarea></label>
  <button class="btn primary" type="submit">Send booking request</button>
  <p class="sent" id="book-sent" hidden>Thanks, your request has gone to {e(x['name'])}. They'll be in touch to confirm.</p>
</form>
<script>
const CONTACT = ["contact", "hostileenvironmentjobs.com"].join("@"), bf = document.getElementById("book-form");
bf.action = "https://formsubmit.co/" + CONTACT;
document.getElementById("book-cc").value = bf.dataset.u + "@" + bf.dataset.d;
document.getElementById("book-sent").hidden = !/sent=1/.test(location.search);
const want = new URLSearchParams(location.search).get("course"), sel = document.getElementById("book-course");
if (want && [...sel.options].some(o => o.value === want)) sel.value = want;
</script>"""


def employer_tag(x):
    return "Founding partner" if x.get("partner") else "Featured employer"


def profile_page(x, jobs, page, e, closing_text, site, courses=()):
    path = f"/employers/{x['id']}/"
    logo = f'<img class="logo" src="{e(x["logo"])}" alt="{e(x["name"])} logo">' if x.get("logo") else ""
    facts = [("Based", x.get("based")), ("Works in", x.get("works_in")), ("Sectors", ", ".join(x.get("sectors", [])))]
    dl = "".join(f"<dt>{k}</dt><dd>{e(v)}</dd>" for k, v in facts if v)
    about = "".join(f"<p>{e(p)}</p>" for p in str(x.get("about", "")).split("\n\n") if p.strip())
    cards = "\n".join(f"""<article class="detail">
  <span class="tag">{e(j['category'])}</span>
  <h3><a href="/jobs/{e(j['id'])}/">{e(j['title'])}</a></h3>
  <div class="who">{e(j['location'])} · {closing_text(j)}</div>
</article>""" for j in jobs) or "<p>No open jobs right now. Check back soon, or join the Facebook group for new posts.</p>"
    links = "".join(f'<a class="btn{" primary" if i == 0 else ""}" href="{e(u)}" target="_blank" rel="noopener">{t}</a>'
                    for i, (t, u) in enumerate([("Careers page", x.get("careers_url")), ("Website", x.get("website"))]) if u)
    body = f"""<a class="back" href="/employers/">&larr; Featured employers</a>
<article class="detail profile">
  <div class="profile-head">{logo}<div><span class="tag featured-tag">{employer_tag(x)}</span><h1>{e(x['name'])}</h1>
    {f'<div class="who">{e(x["tagline"])}</div>' if x.get("tagline") else ""}</div></div>
  {offer_box(x, e)}
  {about}
  {f"<dl>{dl}</dl>" if dl else ""}
  {f'<div class="actions">{links}</div>' if links else ""}
</article>
<h2>Open jobs at {e(x['name'])}</h2>
{cards}
{course_list(x, courses, e)}
{booking_form(x, courses, e)}"""
    org = {"@context": "https://schema.org", "@type": "Organization", "name": x["name"], "url": x.get("website"),
           "logo": (site + x["logo"]) if str(x.get("logo", "")).startswith("/") else x.get("logo"),
           "description": x.get("tagline") or x.get("about", "")[:200]}
    ld = json.dumps({k: v for k, v in org.items() if v}, ensure_ascii=False).replace("</", "<\\/")
    desc = x.get("tagline") or f"Jobs and company profile for {x['name']} on Hostile Environment Jobs."
    return path, page(f"{x['name']} jobs | Hostile Environment Jobs", desc, path, body, f'<script type="application/ld+json">{ld}</script>\n')


def course_list(x, courses, e):
    if not courses:
        return ""
    book = lambda c: (f'<a class="btn primary" href="#book" data-course="{e(c["id"])}">Request a booking</a>' if x.get("booking_email") else "")
    cards = "\n".join(f"""<article class="detail">
  <span class="tag">{e(c['type'])}</span>
  <h3><a href="{e(booking_url(c, 'partner'))}" target="_blank" rel="noopener">{e(c['title'])}</a></h3>
  <div class="who">{e(c['location'])}{' · Starts ' + e(c['start']) if c.get('start') else ''}{' · ' + e(c['price']) if c.get('price') else ''}</div>
  <p>{e(c.get('summary'))}{'<br><strong>' + e(promo_text(c)) + '</strong>' if c.get('promo_code') else ''}</p>
  <div class="actions"><a class="btn" href="{e(booking_url(c, 'partner'))}" target="_blank" rel="noopener">Book on their site</a>{book(c)}</div>
</article>""" for c in courses)
    return f"""<h2>Courses from {e(x['name'])}</h2>
{cards}
<script>document.querySelectorAll("[data-course]").forEach(a => a.addEventListener("click", () => {{ const s = document.getElementById("book-course"); if (s) s.value = a.dataset.course; }}));</script>"""


def deals_page(employers, page, e):
    """Every live profile with an offer, founding partners first."""
    with_offer = sorted((x for x in employers if x.get("offer")), key=lambda x: not x.get("partner"))
    cards = "\n".join(f"""<article class="detail">
  <span class="tag featured-tag">{employer_tag(x)}</span>
  <h2><a href="/employers/{e(x['id'])}/">{e(x['name'])}</a></h2>
  {f'<div class="who">{e(x["tagline"])}</div>' if x.get("tagline") else ""}
  {offer_box(x, e)}
  <div class="actions"><a class="btn primary" href="/employers/{e(x['id'])}/{'#book' if x.get('booking_email') else ''}">{'Book or see jobs' if x.get('booking_email') else 'See their jobs'}</a></div>
</article>""" for x in with_offer) or "<p>No partner deals right now. Check back soon, or get them in the weekly Sitrep.</p>"
    body = f"""<a class="back" href="/#jobs">&larr; All jobs</a>
<h1 style="margin-top:24px">Partner deals</h1>
<p>Discounts and extras from the companies and training providers backing Hostile Environment Jobs. Mention us when you book or apply.</p>
{cards}
<p class="meta-line">Run a company or training school and want to offer something here? <a href="/advertise/">Advertise with us</a>.</p>"""
    return page("Partner deals | Hostile Environment Jobs", "Course discounts and offers from employers and training providers in EOD, security, medic and mine action work.", "/deals/", body)


def employers_index(employers, page, e):
    employers = sorted(employers, key=lambda x: not x.get("partner"))  # founding partners first
    cards = "\n".join(f"""<article class="detail">
  <span class="tag featured-tag">{employer_tag(x)}</span>
  <h2><a href="/employers/{e(x['id'])}/">{e(x['name'])}</a></h2>
  {f'<div class="who">{e(x["tagline"])}</div>' if x.get("tagline") else ""}
</article>""" for x in employers) or "<p>No featured employers yet.</p>"
    body = f"""<a class="back" href="/#jobs">&larr; All jobs</a>
<h1 style="margin-top:24px">Featured employers</h1>
<p>Organisations hiring in hostile and high-risk places. <a href="/deals/">See partner deals</a> · <a href="/advertise/">Want your company here?</a></p>
{cards}"""
    return page("Featured employers | Hostile Environment Jobs", "Companies and NGOs hiring EOD, security, medic and mine action staff.", "/employers/", body)


def partners_strip(employers, e):
    """Names of the founding partners on the Advertise page, so new employers can see who's already with us."""
    partners = [x for x in employers if x.get("partner")]
    if not partners:
        return ""
    links = ", ".join(f'<a href="/employers/{e(x["id"])}/">{e(x["name"])}</a>' for x in partners)
    return f'<p class="meta-line"><b>Our founding partners:</b> {links}. Thanks for backing the site from day one.</p>'


def advertise_page(page, e, employers=()):
    def button(p):
        if p["payment_link"] is None:
            return '<a class="btn" href="/#post">Post a job free</a>'
        if p["payment_link"].startswith("/"):
            return f'<a class="btn primary" href="{e(p["payment_link"])}">Sign up to search</a>'
        if p["payment_link"]:
            return f'<a class="btn primary" href="{e(p["payment_link"])}" target="_blank" rel="noopener">Pay and book</a>'
        return f'<a class="btn primary" href="#enquire" data-plan="{e(p["name"])}">Book this</a>'
    plans = "\n".join(f"""<div class="plan{' best' if p.get('best') else ''}">
  <h2>{e(p['name'])}</h2>
  <p class="price">{e(p['price'])} <span>{e(p['per'])}</span></p>
  <ul>{''.join(f'<li>{e(t)}</li>' for t in p['points'])}</ul>
  {button(p)}
</div>""" for p in PLANS)
    body = f"""<div class="page" style="max-width:none">
<p class="eyebrow" style="margin-top:32px">For employers and training providers</p>
<h1>Advertise with us</h1>
<p>Hostile Environment Jobs reaches people who've done the job: EOD and search operators, security staff, hostile environment medics, managers and support crews. Every job goes on the site and to our 4.4K-member Facebook group. Posting a job and searching the jobs list are free, and always will be. If you need a role filled faster, put it in front of everyone first, or search our <a href="/candidates/">talent pool</a> for people who are free now.</p>
<div class="plans">
{plans}
</div>
{partners_strip(employers, e)}
<p class="meta-line" id="pool-count" hidden></p>
<script>
// The talent pool's size, once it's big enough to be worth showing (POOL_MIN in scripts/candidates.html).
fetch("https://hej-alerts.danieldobb.workers.dev/api/talent/stats").then(r => r.json()).then(s => {{
  if (!(s.available >= 10)) return;
  const top = Object.entries(s.by_category).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([c, n]) => n + " " + c).join(", ");
  const el = document.getElementById("pool-count");
  el.textContent = s.available + " operators in the talent pool now" + (top ? " (" + top + ")" : "") + ".";
  el.hidden = false;
}}).catch(() => {{}});
</script>
<p class="meta-line">Prices exclude VAT where it applies. Featured time starts when the job goes live. We still check every job before it's listed, paid or not.</p>
<h2 id="enquire">Book or ask a question</h2>
<p>Tell us which plan and the job or company, and we'll reply with next steps, usually within a day. Paying by invoice is fine.</p>
<form id="ad-form" method="POST">
  <input type="hidden" name="_subject" value="Advertising enquiry for Hostile Environment Jobs">
  <input type="hidden" name="_next" value="https://hostileenvironmentjobs.com/advertise/?sent=1">
  <input type="text" name="_honey" style="display:none" tabindex="-1" autocomplete="off">
  <div class="row">
    <label>Your name <input name="name" required></label>
    <label>Company <input name="company" required></label>
  </div>
  <div class="row">
    <label>Email <input name="email" type="email" required></label>
    <label>Plan <select name="plan" id="ad-plan">{''.join(f'<option>{e(p["name"])}</option>' for p in PLANS[1:])}<option>Not sure yet</option></select></label>
  </div>
  <label>Job link or anything else we should know <textarea name="details" rows="4"></textarea></label>
  <button class="btn primary" type="submit">Send</button>
  <p class="sent" id="ad-sent" hidden>Thanks, we've got it and will be in touch shortly.</p>
</form>
</div>
<script>
// Assembled here so spam bots don't collect the address.
const CONTACT = ["contact", "hostileenvironmentjobs.com"].join("@");
document.getElementById("ad-form").action = "https://formsubmit.co/" + CONTACT;
document.getElementById("ad-sent").hidden = !/sent=1/.test(location.search);
document.querySelectorAll("[data-plan]").forEach(a => a.addEventListener("click", () => document.getElementById("ad-plan").value = a.dataset.plan));
</script>"""
    return page("Advertise with us | Hostile Environment Jobs",
                "Featured jobs and employer profiles on Hostile Environment Jobs: reach EOD, security, medic and mine action professionals.",
                "/advertise/", body)
