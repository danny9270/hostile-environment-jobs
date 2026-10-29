"""Send job alert notifications for new jobs and courses. Run by the "Job alerts" GitHub Action.

Asks the alerts Worker (ALERTS_API) for every paid-up phone and its preferences, finds listings in jobs.json and
courses.json it hasn't sent before, waits until each new job's own page is live, and pushes the matches.
Up to 3 matches go as one notification each; more than that go as one "N new jobs" notification.
The very first run only records what's already listed, so nobody gets a flood of old jobs.

Needs: pip install pywebpush. Signs in to the Worker with the Action's GitHub token (permissions: id-token: write).
Run locally with --dry-run and a recipients JSON file to see what would be sent: python3 alerts/send_alerts.py --dry-run file.json
"""
import datetime
import json
import os
import pathlib
import re
import sys
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
        if len(hits) > 3:
            n_jobs = sum(h["tag"].startswith("job-") for h in hits)
            what = f"{n_jobs} new jobs" + (f" and {len(hits) - n_jobs} courses" if len(hits) > n_jobs else "") if n_jobs else f"{len(hits)} new courses"
            hits = [{"title": f"{what} match your alerts", "body": "; ".join(h["title"].split(": ", 1)[-1] for h in hits[:4]) + "…",
                     "url": "/app/#matches", "tag": "roundup"}]
        if hits:
            out[r["endpoint"]] = hits
    return out, sent


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
    print(f"{len(sent)} new listings, {sum(map(len, todo.values()))} notifications to {len(todo)} phones")
    if dry:
        print(json.dumps(todo, indent=1))
        return

    from pywebpush import WebPushException, webpush
    from py_vapid import Vapid02
    key = Vapid02.from_raw(data["vapid"]["private"].encode())
    by_endpoint = {r["endpoint"]: r for r in data["recipients"]}
    gone, failed = [], 0
    for endpoint, notes in todo.items():
        r = by_endpoint[endpoint]
        if r["kind"] != "web":
            continue  # store-app phones (FCM) are sent by the app-store build, not yet live
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
    call(api, "/api/internal/sent", token, {"seen": sent, "gone": gone})
    print(f"Done. {len(gone)} old phones removed, {failed} failures.")


if __name__ == "__main__":
    main()
