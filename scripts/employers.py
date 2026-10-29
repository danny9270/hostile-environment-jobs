"""Paid extras: featured jobs, employer profile pages and the Advertise page.

build_pages.py imports this. Employers who pay for a profile go in employers.json; a job is featured
while its "featured_until" date hasn't passed, or while its employer's profile is live.
"""
import datetime
import json
import re

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
                "Your name links to your profile on every listing", "A spotlight post on our Facebook and LinkedIn pages"],
     "payment_link": ""},
]
# Each "payment_link" is a Stripe Payment Link (https://buy.stripe.com/...). Left empty, the button asks people to email us instead.

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


def profile_page(x, jobs, page, e, closing_text, site):
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
  <div class="profile-head">{logo}<div><span class="tag featured-tag">Featured employer</span><h1>{e(x['name'])}</h1>
    {f'<div class="who">{e(x["tagline"])}</div>' if x.get("tagline") else ""}</div></div>
  {about}
  {f"<dl>{dl}</dl>" if dl else ""}
  {f'<div class="actions">{links}</div>' if links else ""}
</article>
<h2>Open jobs at {e(x['name'])}</h2>
{cards}"""
    org = {"@context": "https://schema.org", "@type": "Organization", "name": x["name"], "url": x.get("website"),
           "logo": (site + x["logo"]) if str(x.get("logo", "")).startswith("/") else x.get("logo"),
           "description": x.get("tagline") or x.get("about", "")[:200]}
    ld = json.dumps({k: v for k, v in org.items() if v}, ensure_ascii=False).replace("</", "<\\/")
    desc = x.get("tagline") or f"Jobs and company profile for {x['name']} on Hostile Environment Jobs."
    return path, page(f"{x['name']} jobs | Hostile Environment Jobs", desc, path, body, f'<script type="application/ld+json">{ld}</script>\n')


def employers_index(employers, page, e):
    cards = "\n".join(f"""<article class="detail">
  <span class="tag featured-tag">Featured employer</span>
  <h2><a href="/employers/{e(x['id'])}/">{e(x['name'])}</a></h2>
  {f'<div class="who">{e(x["tagline"])}</div>' if x.get("tagline") else ""}
</article>""" for x in employers) or "<p>No featured employers yet.</p>"
    body = f"""<a class="back" href="/#jobs">&larr; All jobs</a>
<h1 style="margin-top:24px">Featured employers</h1>
<p>Organisations hiring in hostile and high-risk places. <a href="/advertise/">Want your company here?</a></p>
{cards}"""
    return page("Featured employers | Hostile Environment Jobs", "Companies and NGOs hiring EOD, security, medic and mine action staff.", "/employers/", body)


def advertise_page(page, e):
    def button(p):
        if p["payment_link"] is None:
            return '<a class="btn" href="/#post">Post a job free</a>'
        if p["payment_link"]:
            return f'<a class="btn primary" href="{e(p["payment_link"])}" target="_blank" rel="noopener">Pay and book</a>'
        return f'<a class="btn primary" href="#enquire" data-plan="{e(p["name"])}">Book this</a>'
    plans = "\n".join(f"""<div class="plan{' best' if i == len(PLANS) - 1 else ''}">
  <h2>{e(p['name'])}</h2>
  <p class="price">{e(p['price'])} <span>{e(p['per'])}</span></p>
  <ul>{''.join(f'<li>{e(t)}</li>' for t in p['points'])}</ul>
  {button(p)}
</div>""" for i, p in enumerate(PLANS))
    body = f"""<div class="page" style="max-width:none">
<p class="eyebrow" style="margin-top:32px">For employers and training providers</p>
<h1>Advertise with us</h1>
<p>Hostile Environment Jobs reaches people who've done the job: EOD and search operators, security staff, hostile environment medics, managers and support crews. Every job goes on the site and to our 4.4K-member Facebook group. Posting stays free. If you need a role filled faster, put it in front of everyone first.</p>
<div class="plans">
{plans}
</div>
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
