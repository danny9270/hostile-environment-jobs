"""Send job alert notifications for new jobs and courses. Run by the "Job alerts" GitHub Action.

Asks the alerts Worker (ALERTS_API) for every paid-up phone and its preferences, finds listings in jobs.json and
courses.json it hasn't sent before, waits until each new job's own page is live, and pushes the matches.
Up to 3 matches go as one notification each; more than that go as one "N new jobs" notification.
It also reminds subscribers 60, 30 and 7 days before a ticket or document they logged runs out, and 3 days before a saved job closes.
The very first run only records what's already listed, so nobody gets a flood of old jobs.

Email alerts (kind "email", endpoint "email:<code>") get every match in one email per run, plus the same reminders.
The Worker fills in the address and unsubscribe link and sends them through Resend, so nothing here needs a mail key.

Store-app phones (kind "fcm") are sent through Firebase Cloud Messaging, which reaches both iPhones and Android phones.
That needs the repository secret FCM_SERVICE_ACCOUNT: the JSON key of a Firebase service account (Project settings >
Service accounts > Generate new private key). Without it those phones are skipped and the rest still go.

Needs: pip install pywebpush google-auth requests. Signs in to the Worker with the Action's GitHub token (permissions: id-token: write).
Run locally with --dry-run and a recipients JSON file to see what would be sent: python3 alerts/send_alerts.py --dry-run file.json
"""
import datetime
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://hostileenvironmentjobs.com"
TODAY = datetime.datetime.now(datetime.timezone.utc).date()
CONTACT = "mailto:contact@hostileenvironmentjobs.com"


def is_open(j, field):
    d = j.get(field)
    return not d or d == "Rolling" or (re.fullmatch(r"\d{4}-\d\d-\d\d", d) and datetime.date.fromisoformat(d) >= TODAY)


def words(text):
    return [w.strip().lower() for w in re.split(r"[,;\n]", text or "") if w.strip()]


def job_matches(j, p):
    if p.get("categories") and j.get("category") not in p["categories"]:
        return False
    # "Worldwide" jobs and jobs with no region suit anyone who picked regions.
    if p.get("regions") and j.get("region") not in p["regions"] and j.get("region") not in ("Worldwide", None, ""):
        return False
    keys = words(p.get("keywords"))
    hay = " ".join(str(j.get(k, "")) for k in ("title", "employer", "location", "summary", "category")).lower()
    return not keys or any(k in hay for k in keys)


def course_matches(c, p):
    if not p.get("courses"):
        return False
    return not p.get("course_types") or c.get("type") in p["course_types"]


def job_note(j):
    return {"title": f"New {j['category']} job: {j['title']}", "body": f"{j['employer']} · {j['location']}",
            "url": f"/jobs/{j['id']}/", "tag": "job-" + j["id"]}


def course_note(c):
    return {"title": f"New course: {c['title']}", "body": f"{c['provider']} · {c.get('location', '')} · starts {c.get('start', '')}",
            "url": "/#courses", "tag": "course-" + c["id"]}


def plan(recipients, jobs, courses, seen):
    """Returns ({endpoint: [notification, ...]}, ids now sent)."""
    seen = set(seen)
    new_jobs = [j for j in jobs if j.get("id") and "job:" + j["id"] not in seen]
    new_courses = [c for c in courses if c.get("id") and "course:" + c["id"] not in seen]
    sent = ["job:" + j["id"] for j in new_jobs] + ["course:" + c["id"] for c in new_courses]
    out = {}
    for r in recipients:
        p = r.get("prefs") or {}
        hits = [job_note(j) for j in new_jobs if job_matches(j, p)] + [course_note(c) for c in new_courses if course_matches(c, p)]
        if len(hits) > 3 and r.get("kind") != "email":  # an email has room for every match
            n_jobs = sum(h["tag"].startswith("job-") for h in hits)
            what = f"{n_jobs} new jobs" + (f" and {len(hits) - n_jobs} courses" if len(hits) > n_jobs else "") if n_jobs else f"{len(hits)} new courses"
            hits = [{"title": f"{what} match your alerts", "body": "; ".join(h["title"].split(": ", 1)[-1] for h in hits[:4]) + "…",
                     "url": "/app/#matches", "tag": "roundup"}]
        if hits:
            out[r["endpoint"]] = hits
    return out, sent


CERT_DAYS = (60, 30, 7)  # reminders go this many days before a ticket or document runs out
SAVED_DAYS = 3  # and this many days before a saved job closes


def nice_date(d):
    return f"{d.day} {d.strftime('%b %Y')}"


def plan_reminders(recipients, jobs, seen, today=None):
    """Cert expiry and saved-job reminders. Returns ({endpoint: [notification, ...]}, ids now sent).
    Each reminder is sent once per account; when two thresholds pass between runs, only the nearest one goes."""
    today = today or TODAY
    seen = set(seen)
    by_id = {j["id"]: j for j in jobs if j.get("id")}
    per_code, sent = {}, []
    for r in recipients:
        if r["code"] in per_code:
            continue
        p, notes = r.get("prefs") or {}, []
        for c in p.get("certs") or []:
            try:
                d = datetime.date.fromisoformat(c.get("d", ""))
            except ValueError:
                continue
            left, name = (d - today).days, (c.get("n") or "A ticket").strip()[:60]
            if left < 0:
                continue
            due = [t for t in CERT_DAYS if left <= t and f"rem:{r['code']}:c:{name}:{c['d']}:{t}" not in seen]
            if not due:
                continue
            sent += [f"rem:{r['code']}:c:{name}:{c['d']}:{t}" for t in due]
            when = "today" if left == 0 else "tomorrow" if left == 1 else f"in {left} days"
            notes.append({"title": f"Your {name} runs out {when}", "body": f"Expires {nice_date(d)}. Tap to see all your dates.",
                          "url": "/app/#certs", "tag": f"cert-{c['d']}-{re.sub(r'[^A-Za-z0-9]', '', name)[:20]}"})
        for jid in p.get("saved") or []:
            j = by_id.get(jid)
            key = f"rem:{r['code']}:s:{jid}"
            if not j or key in seen or not re.fullmatch(r"\d{4}-\d\d-\d\d", j.get("closing") or ""):
                continue
            left = (datetime.date.fromisoformat(j["closing"]) - today).days
            if 0 <= left <= SAVED_DAYS:
                sent.append(key)
                when = "today" if left == 0 else "tomorrow" if left == 1 else f"in {left} days"
                notes.append({"title": f"Saved job closes {when}: {j['title']}", "body": f"{j['employer']} · {j['location']}",
                              "url": f"/jobs/{j['id']}/", "tag": "saved-" + j["id"]})
        per_code[r["code"]] = notes
    out = {r["endpoint"]: per_code[r["code"]] for r in recipients if per_code.get(r["code"])}
    return out, sent


def link(path):
    base, _, frag = path.partition("#")
    return SITE + base + ("&" if "?" in base else "?") + "utm_source=email-alert" + ("#" + frag if frag else "")


def email_for(code, notes):
    """One alert email: {code, subject, text, html}. The Worker swaps {{UNSUBSCRIBE}} for the account's own link."""
    jobs = [n for n in notes if n["tag"].startswith("job-")]
    if len(notes) == 1:
        subject = notes[0]["title"]
    elif jobs:
        subject = f"{len(jobs)} new job{'s' if len(jobs) > 1 else ''} match your alerts" + (f": {jobs[0]['title'].split(': ', 1)[-1]} and more" if len(jobs) > 1 else "")
    else:
        subject = f"{len(notes)} updates from H.E. Jobs"
    subject = subject[:150]
    lines = [f"{n['title']}\n{n['body']}\n{link(n['url'])}" for n in notes]
    text = ("New listings that match your alerts:\n\n" + "\n\n".join(lines) +
            f"\n\nSee every open job: {link('/#jobs')}\nChange what you get: {SITE}/app/#alerts\n"
            "Stop these emails: {{UNSUBSCRIBE}}\n\nH.E. Jobs Team\n" + SITE)
    e = html.escape
    items = "".join(
        f'<tr><td style="padding:14px 0;border-bottom:1px solid #e3e6e4"><a href="{e(link(n["url"]))}" style="color:#1d5b3f;font-weight:700;font-size:16px;text-decoration:none">{e(n["title"])}</a>'
        f'<div style="color:#55605a;font-size:14px;margin-top:3px">{e(n["body"])}</div></td></tr>' for n in notes)
    body = f"""<!doctype html><html><body style="margin:0;background:#f3f5f4;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1c2420">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:20px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#fff;border-radius:10px">
<tr><td style="background:#0f1412;color:#e0b341;padding:16px 22px;border-radius:10px 10px 0 0;font-weight:800;letter-spacing:.04em">HOSTILE ENVIRONMENT JOBS</td></tr>
<tr><td style="padding:18px 22px 6px"><p style="margin:0 0 4px;font-size:15px">New listings that match your alerts:</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{items}</table>
<p style="margin:18px 0"><a href="{e(link('/#jobs'))}" style="background:#e0b341;color:#0f1412;padding:10px 16px;border-radius:8px;font-weight:700;text-decoration:none;display:inline-block">See every open job</a></p>
<p style="margin:0 0 18px;font-size:15px">H.E. Jobs Team</p></td></tr>
<tr><td style="padding:14px 22px 18px;border-top:1px solid #e3e6e4;color:#6b756f;font-size:12px">You get these because you turned on email alerts in The App.
<a href="{SITE}/app/#alerts" style="color:#6b756f">Change what you get</a> · <a href="{{{{UNSUBSCRIBE}}}}" style="color:#6b756f">Stop these emails</a></td></tr>
</table></td></tr></table></body></html>"""
    return {"code": code, "subject": subject, "text": text, "html": body}


def page_live(path):
    try:
        return urllib.request.urlopen(urllib.request.Request(SITE + path, method="HEAD"), timeout=20).status == 200
    except Exception:
        return False


def id_token():
    req = urllib.request.Request(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&audience=hej-alerts",
                                 headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    return json.load(urllib.request.urlopen(req))["value"]


def call(api, path, token, body=None):
    req = urllib.request.Request(api.rstrip("/") + path, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET",
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": "hej-alerts-sender"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as err:
        raise SystemExit(f"Alerts Worker said {err.code} on {path}: {err.read().decode()[:300]}")


def fcm_sender():
    """Returns send(token, note) -> "ok" | "gone" | "failed", or None when there's no Firebase key."""
    raw = os.environ.get("FCM_SERVICE_ACCOUNT", "").strip()
    if not raw:
        return None
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
    session = AuthorizedSession(creds)
    url = f"https://fcm.googleapis.com/v1/projects/{info['project_id']}/messages:send"

    def send(token, n):
        tag = re.sub(r"[^A-Za-z0-9_-]", "", n["tag"])[:64]
        msg = {"message": {"token": token, "notification": {"title": n["title"], "body": n["body"]}, "data": {"url": n["url"]},
                           "android": {"ttl": f"{3 * 86400}s", "notification": {"tag": tag, "channel_id": "job_alerts"}},
                           "apns": {"headers": {"apns-collapse-id": tag, "apns-expiration": str(int(datetime.datetime.now().timestamp()) + 3 * 86400)},
                                    "payload": {"aps": {"sound": "default", "thread-id": "job-alerts"}}}}}
        r = session.post(url, json=msg, timeout=30)
        if r.ok:
            return "ok"
        err = r.text[:300]
        if r.status_code == 404 or "UNREGISTERED" in err or (r.status_code == 400 and "registration token" in err.lower()):
            return "gone"  # the app was removed or the token replaced
        print(f"FCM push failed ({r.status_code}): {err}")
        return "failed"
    return send


def main():
    dry = "--dry-run" in sys.argv
    jobs = [j for j in json.loads((ROOT / "jobs.json").read_text()) if is_open(j, "closing") and not j.get("sample")]
    courses = [c for c in json.loads((ROOT / "courses.json").read_text()) if is_open(c, "start") and not c.get("sample")]
    if dry:
        data = json.loads(pathlib.Path(sys.argv[-1]).read_text())
    else:
        api = os.environ.get("ALERTS_API")
        if not api:
            print("No ALERTS_API repository variable yet, so there's nobody to send to.")
            return
        token = id_token()
        data = call(api, "/api/internal/recipients", token)
    if not data["seen"]:
        print(f"First run: recording {len(jobs)} jobs and {len(courses)} courses as already sent.")
        if not dry:
            call(api, "/api/internal/sent", token, {"seen": ["job:" + j["id"] for j in jobs] + ["course:" + c["id"] for c in courses]})
        return
    # Hold back jobs whose page isn't up yet (the page build runs a minute or two behind jobs.json); the next run picks them up.
    seen = set(data["seen"])
    if not dry:
        jobs = [j for j in jobs if "job:" + j["id"] in seen or page_live(f"/jobs/{j['id']}/")]
    todo, sent = plan(data["recipients"], jobs, courses, seen)
    reminders, rem_sent = plan_reminders(data["recipients"], jobs, seen)
    for endpoint, notes in reminders.items():
        todo.setdefault(endpoint, []).extend(notes)
    sent += rem_sent
    print(f"{len(sent)} new listings, {sum(map(len, todo.values()))} notifications to {len(todo)} phones")
    emails = [email_for(ep.split(":", 1)[1], notes) for ep, notes in todo.items() if ep.startswith("email:")]
    if dry:
        print(json.dumps({ep: n for ep, n in todo.items() if not ep.startswith("email:")}, indent=1))
        for m in emails:
            print(f"\nEMAIL to account {m['code']}: {m['subject']}\n{m['text']}")
        return

    from pywebpush import WebPushException, webpush
    from py_vapid import Vapid02
    key = Vapid02.from_raw(data["vapid"]["private"].encode())
    by_endpoint = {r["endpoint"]: r for r in data["recipients"]}
    gone, failed = [], 0
    fcm = fcm_sender()
    for endpoint, notes in todo.items():
        r = by_endpoint[endpoint]
        if r["kind"] == "email":
            continue
        if r["kind"] == "fcm":
            if not fcm:
                print("A store-app phone is waiting but there's no FCM_SERVICE_ACCOUNT secret yet, so it was skipped.")
                continue
            for n in notes:
                result = fcm(r["sub"]["token"], n)
                if result == "gone":
                    gone.append(endpoint)
                    break
                failed += result == "failed"
            continue
        for n in notes:
            try:
                webpush(r["sub"], json.dumps(n), vapid_private_key=key, vapid_claims={"sub": CONTACT}, ttl=3 * 86400,
                        headers={"Urgency": "normal", "Topic": re.sub(r"[^A-Za-z0-9_-]", "", n["tag"])[:32]})
            except WebPushException as err:
                status = getattr(err.response, "status_code", None)
                if status in (404, 410):
                    gone.append(endpoint)  # the phone unsubscribed or the app was removed
                    break
                failed += 1
                print(f"Push failed ({status}): {str(err)[:200]}")
    mailed = 0
    for i in range(0, len(emails), 90):
        if i:
            time.sleep(1)  # Resend allows a couple of requests a second
        res = call(api, "/api/internal/email", token, {"emails": emails[i:i + 90]})
        mailed += res.get("sent", 0)
        failed += res.get("failed", 0)
        if res.get("error") or res.get("note"):
            print("Email alerts:", res.get("error") or res.get("note"))
    call(api, "/api/internal/sent", token, {"seen": sent, "gone": gone})
    print(f"Done. {mailed} emails sent, {len(gone)} old phones removed, {failed} failures.")


if __name__ == "__main__":
    main()
