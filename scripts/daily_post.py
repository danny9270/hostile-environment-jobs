"""Daily social post: one evergreen post a day for the Facebook and LinkedIn Pages, built from the site's own data.

Usage: python3 scripts/daily_post.py [YYYY-MM-DD]
Adds the day's post to social/facebook.xml and social/linkedin.xml (Zapier posts them to the Pages).
The GitHub Action "Daily social post" runs it every day at 11:30 UTC, so it lands in the UK lunch break,
after the morning new-jobs roundup. Thursday is left to the closing-soon post (scripts/closing_soon.py).

Rotation (by weekday):
  Mon  job spotlight        one open job, picked so it changes every week
  Tue  pay guide            one role's going rate from pay.json
  Wed  deployment brief     one country's culture tips from deploy-countries.json
  Fri  course spotlight     one upcoming course
  Sat  free tool            one free tool on the site (CV builder, talent pool, rotation tracker...)
  Sun  week in numbers      new jobs this week, what's closing, link to all jobs
Each post ends with a question, because comments are what get a Page post shown to more people.
The pick is worked out from the date, so a rerun on the same day gives the same post and nothing needs storing.
"""
import datetime
import json
import sys
from pathlib import Path

import social_feed
from closing_soon import CATEGORY_EMOJI, closing_soon, short_place

ROOT = Path(__file__).resolve().parent.parent
SITE = "hostileenvironmentjobs.com"
HOUR = 11  # UTC; the item is dated 11:00 and published at 11:30, so Zapier posts it around midday UK


def load(name):
    data = json.loads((ROOT / name).read_text(encoding="utf-8"))
    return data


def link(path, network, kind):
    """Site link with UTM tags, so GoatCounter shows which daily posts bring people in."""
    path, _, frag = path.partition("#")
    sep = "&" if "?" in path else "?"
    return (f"https://{SITE}{path}{sep}utm_source={network}&utm_medium=social&utm_campaign=daily-{kind}"
            + (f"#{frag}" if frag else ""))


def pick(items, day, period=7):
    """A different item each `period` days, cycling through the list in order."""
    return items[(day.toordinal() // period) % len(items)] if items else None


def money(n, cur):
    sym = {"GBP": "£", "USD": "$", "EUR": "€"}.get(cur, "")
    return f"{sym}{n:,}" if sym else f"{n:,} {cur}"


# ---------- the six post types ----------

def job_spotlight(day, network):
    jobs = [j for j in load("jobs.json") if j.get("id") and not j.get("sample")]
    open_jobs = [j for j in jobs if not j.get("closing") or j["closing"] >= day.isoformat()]
    open_jobs.sort(key=lambda j: j["id"])
    j = pick(open_jobs, day)
    if not j:
        return None
    mark = CATEGORY_EMOJI.get(j.get("category"), "📌")
    reqs = [r for r in j.get("requirements", [])][:3]
    closes = ""
    if j.get("closing"):
        closes = "⏳ Closes " + datetime.date.fromisoformat(j["closing"]).strftime("%a %-d %b") + "\n"
    salary = f"💷 {j['salary']}\n" if j.get("salary") and not j["salary"].startswith("Not stated") else ""
    url = link(f"/jobs/{j['id']}/", network, "job")
    if network == "facebook":
        return (f"{mark} Job spotlight: {j['title']}, {j['employer']}\n\n"
                f"📍 {j['location']}\n📝 {j.get('contract', '')}\n{salary}{closes}\n"
                f"{j.get('summary', '')}\n\n"
                + ("What they want:\n" + "\n".join(f"✔️ {r}" for r in reqs) + "\n\n" if reqs else "")
                + f"Full advert and apply link 👇\n{url}\n\nKnow someone who'd fit? Tag them 👇")
    return (f"Job spotlight: {j['title']} with {j['employer']}, {j['location']}.\n\n"
            f"{j.get('summary', '')}\n\n"
            + ("What they're looking for:\n" + "\n".join(f"• {r}" for r in reqs) + "\n\n" if reqs else "")
            + f"{j.get('contract', '')}. {closes.replace('⏳ ', '').strip()}\n\n"
            f"Full advert and how to apply: {url}\n\n"
            f"Know someone who'd fit? Tag them in the comments.\n\n#{j.get('category', 'Jobs').replace(' ', '').replace('&', '')} #HostileEnvironment #Jobs")


def pay_fact(day, network):
    ranges = [r for r in load("pay.json")["ranges"] if r.get("low") or r.get("high")]
    r = pick(ranges, day)
    lo, hi, cur, per = r.get("low"), r.get("high"), r["currency"], r["per"]
    rate = (f"{money(lo, cur)} to {money(hi, cur)}" if lo and hi else f"from {money(lo, cur)}" if lo else f"up to {money(hi, cur)}")
    basis = "from published adverts" if r.get("basis") == "advertised" else "a guide range, not a quote"
    url = link("/pay/", network, "pay")
    if network == "facebook":
        return (f"💷 What does a {r['role']} earn?\n\n"
                f"📍 {r['where']}\n💰 {rate} a {per}\n({basis})\n\n"
                f"The free pay guide has {len(ranges)} roles across EOD, mine action, security, maritime and HE medicine 👇\n{url}\n\n"
                f"Is that about right where you've worked? Drop your view below 👇")
    return (f"What does a {r['role']} earn? Our pay guide puts it at {rate} a {per} ({r['where']}; {basis}).\n\n"
            f"The free guide covers {len(ranges)} roles across EOD, mine action, security, maritime and hostile environment medicine: {url}\n\n"
            f"Does that match what you've seen? Comments welcome.\n\n#PayGuide #EOD #Security #HostileEnvironment")


def deploy_brief(day, network):
    countries = [c for c in load("deploy-countries.json")["countries"] if c.get("culture")]
    c = pick(countries, day)
    tips = c["culture"][:3]
    url = link(f"/deploy/#{c['iso2']}", network, "deploy")
    if network == "facebook":
        return (f"🌍 Deploying to {c['name']}? Three things to know before you land\n\n"
                + "\n\n".join(f"{i}️⃣ {t}" for i, t in zip((1, 2, 3), tips))
                + f"\n\nThe free deployment guide has travel advice, local time and more for {c['name']} and {len(countries) - 1} other countries 👇\n{url}\n\n"
                f"Worked in {c['name']}? What would you add? 👇")
    return (f"Deploying to {c['name']}? Three things worth knowing before you land:\n\n"
            + "\n".join(f"{i}. {t}" for i, t in zip((1, 2, 3), tips))
            + f"\n\nOur free deployment guide covers {c['name']} and {len(countries) - 1} other countries, with current travel advice: {url}\n\n"
            f"If you've worked in {c['name']}, what would you add?\n\n#Deployment #SecurityRisk #HostileEnvironment #{c['name'].replace(' ', '')}")


def course_spotlight(day, network):
    courses = [c for c in load("courses.json") if c.get("start", "") >= day.isoformat()]
    courses.sort(key=lambda c: c["id"])
    c = pick(courses, day)
    if not c:
        return None
    when = datetime.date.fromisoformat(c["start"]).strftime("%-d %b %Y")
    price = f"💷 {c['price']}\n" if c.get("price") else ""
    url = link("/#courses", network, "course")
    if network == "facebook":
        return (f"🎯 Course spotlight: {c['title']}\n\n"
                f"🏫 {c['provider']}\n📍 {c['location']}\n📅 Next start {when}, {c.get('duration', '')}\n{price}\n"
                f"{c.get('summary', '')}\n\n"
                f"All upcoming courses, and add the dates to your calendar 👇\n{url}\n\n"
                f"Done this one? How was it? Leave a word for the next lot 👇")
    return (f"Course spotlight: {c['title']} with {c['provider']}, {c['location']}. Next start {when}, {c.get('duration', '')}.\n\n"
            f"{c.get('summary', '')}\n\n"
            f"See every upcoming EOD, mine action, HEAT and medical course: {url}\n\n"
            f"Have you done this course? Your view helps the next person decide.\n\n#Training #HEAT #EOD #HostileEnvironment")


TOOLS = [
    ("📄", "CV builder", "/cv/", "cv",
     "Build a CV in the format security and mine action employers expect: quals, tours and courses laid out properly, saved as a PDF. No sign-up.",
     "What's the one thing you wish you'd put on your first circuit CV?"),
    ("🧑‍💼", "Talent pool", "/candidates/", "talent",
     "Add your trade, quals, regions and the date you're free. Employers see your skills, not your name, and contact you through us.",
     "When are you next free for work? 👀"),
    ("🗓️", "Rotation tracker", "/app/", "rota",
     "Count down to your next leave, log days in and out of country, and keep a record that's handy for residence rules (a record, not tax advice).",
     "How many days left on this rotation?"),
    ("🎖️", "Service leaver hub", "/leavers/", "leavers",
     "Your resettlement timeline from two years out, ELCAS-eligible courses, CV help and the jobs that suit your trade.",
     "Leavers who've done it: what's your best advice for someone two years out?"),
    ("🌍", "Deployment guide", "/deploy/", "deploy-tool",
     "Travel advice, local time and culture tips for 27 countries across Africa and the Middle East, refreshed daily.",
     "Where's your next deployment?"),
    ("💷", "Pay guide", "/pay/", "pay-tool",
     "Day rates and salaries for 21 roles across EOD, mine action, security, maritime and HE medicine.",
     "Which role should we add next?"),
    ("🏢", "Company reviews", "/companies/", "reviews",
     "Anonymous, moderated reviews of the companies hiring in this industry, with a right of reply.",
     "Who's the best outfit you've worked for, and why?"),
    ("📬", "Weekly Sitrep", "/sitrep/", "sitrep",
     "Every new job and course, once a week, straight to your inbox. Free, unsubscribe any time.",
     "What would you want in a weekly industry email?"),
]


def free_tool(day, network):
    icon, name, path, kind, what, question = pick(TOOLS, day)
    url = link(path, network, kind)
    if network == "facebook":
        return (f"{icon} {name}, free on H.E. Jobs\n\n{what}\n\nTry it 👇\n{url}\n\n{question} 👇")
    return (f"{name}, free on Hostile Environment Jobs.\n\n{what}\n\n{url}\n\n{question}\n\n#HostileEnvironment #Veterans #Careers")


def week_in_numbers(day, network):
    jobs = [j for j in load("jobs.json") if j.get("id") and not j.get("sample")]
    week_ago = (day - datetime.timedelta(days=7)).isoformat()
    new = [j for j in jobs if j.get("posted", "") > week_ago]
    soon = closing_soon(jobs, day, 7)
    courses = [c for c in load("courses.json") if c.get("start", "") >= day.isoformat()]
    url = link("/#jobs", network, "week")
    lines = ([f"🆕 {len(new)} new job{'s' if len(new) != 1 else ''} this week"] if new else []) + [
             f"📋 {len(jobs)} live jobs in total",
             f"⏰ {len(soon)} closing in the next 7 days",
             f"🎯 {len(courses)} upcoming courses"]
    if new:
        lines.append("\nNew this week:\n" + "\n".join(f"• {j['title']}, {short_place(j['location'])}" for j in new[:6]))
    if network == "facebook":
        return ("📊 The week on H.E. Jobs\n\n" + "\n".join(lines) + f"\n\nEvery listing checked by hand, free to search 👇\n{url}\n\n"
                "Hiring? Posting a job is free too. Share this with your ops manager 👇")
    return ("The week on Hostile Environment Jobs:\n\n" + "\n".join(lines).replace("🆕 ", "").replace("📋 ", "").replace("⏰ ", "").replace("🎯 ", "")
            + f"\n\nEvery listing is checked by hand and free to search: {url}\n\n"
            "Hiring for hostile environment roles? Posting a job is free.\n\n#Jobs #EOD #MineAction #Security #Hiring")


ROTATION = {0: job_spotlight, 1: pay_fact, 2: deploy_brief, 4: course_spotlight, 5: free_tool, 6: week_in_numbers}


def main():
    day = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.datetime.now(datetime.timezone.utc).date()
    make = ROTATION.get(day.weekday())
    if not make:
        print("Thursday: the closing-soon post covers today.")
        return
    texts = {n: make(day, n) for n in ("facebook", "linkedin")}
    if not texts["facebook"]:
        print("Nothing to post today.")
        return
    for network, text in texts.items():
        # Own guid ("daily-<date>"), so it never replaces the morning roundup or the closing-soon post.
        social_feed.write_feed(network, f"daily-{day.isoformat()}", text, day.isoformat(), hour=HOUR)
    print(texts["facebook"])
    print("\n---- linkedin ----\n" + texts["linkedin"])


if __name__ == "__main__":
    main()
