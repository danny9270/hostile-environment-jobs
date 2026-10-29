"""Refresh deploy.json, the data behind the /deploy/ deployment guide.

For each country in deploy-countries.json it pulls, from public sources only:
  - UK FCDO travel advice (GOV.UK content API): alert level, latest changes, safety and
    security, visas for British passport holders, local laws and customs
  - US State Dept travel advisory level (its RSS feed)
  - the latest humanitarian and security reports from ReliefWeb (UN OCHA), if its API answers
Nothing is written by hand here: every item keeps its source link and date. If a source fails,
that country keeps what it had last time, so a bad run never empties the page.
Run from the repo root: python3 scripts/build_deploy.py (the deploy-guide GitHub Action runs it daily).
"""
import datetime
import html.parser
import json
import os
import pathlib
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = {"User-Agent": "HostileEnvironmentJobs/1.0 (+https://hostileenvironmentjobs.com/deploy/)"}
NOW = datetime.datetime.now(datetime.timezone.utc)

ISO3 = {"SO": "SOM", "ET": "ETH", "ER": "ERI", "DJ": "DJI", "KE": "KEN", "SD": "SDN", "SS": "SSD", "UG": "UGA",
        "MA": "MAR", "DZ": "DZA", "TN": "TUN", "LY": "LBY", "EG": "EGY", "IL": "ISR", "PS": "PSE", "LB": "LBN",
        "SY": "SYR", "JO": "JOR", "IQ": "IRQ", "IR": "IRN", "SA": "SAU", "YE": "YEM", "OM": "OMN", "AE": "ARE",
        "QA": "QAT", "BH": "BHR", "KW": "KWT"}
# Names the State Dept uses in its advisory titles, where they differ from ours.
US_NAMES = {"IL": "Israel, the West Bank and Gaza", "PS": "Israel, the West Bank and Gaza", "AE": "United Arab Emirates"}
ALERTS = {
    "avoid_all_travel_to_whole_country": (4, "FCDO advises against all travel to the whole country"),
    "avoid_all_travel_to_parts": (3, "FCDO advises against all travel to parts of the country"),
    "avoid_all_but_essential_travel_to_whole_country": (3, "FCDO advises against all but essential travel to the whole country"),
    "avoid_all_but_essential_travel_to_parts": (2, "FCDO advises against all but essential travel to parts of the country"),
}
SECURITY = re.compile(r"terror|kidnap|political|protest|unrest|crime|conflict|military|armed|curfew|landmine|mine|border|piracy|maritime|security situation|regional", re.I)


def get(url, data=None):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers={**UA, **({"Content-Type": "application/json"} if data else {})})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as err:
            if attempt == 2 or getattr(err, "code", 500) in (400, 401, 403, 404):
                raise
            time.sleep(2 ** attempt)


class Sections(html.parser.HTMLParser):
    """Split a GOV.UK body into (h2, h3, [paragraph texts]) sections."""

    def __init__(self):
        super().__init__()
        self.out, self.h2, self.h3, self.buf, self.tag = [], "", "", None, None

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "p", "li"):
            self.buf, self.tag = [], tag

    def handle_endtag(self, tag):
        if tag != self.tag or self.buf is None:
            return
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = self.tag = None
        if tag == "h2":
            self.h2, self.h3 = text, ""
        elif tag == "h3":
            self.h3 = text
        elif text:
            if not self.out or self.out[-1][:2] != (self.h2, self.h3):
                self.out.append((self.h2, self.h3, []))
            self.out[-1][2].append(text)

    def handle_data(self, d):
        if self.buf is not None:
            self.buf.append(d)


def sections(body):
    p = Sections()
    p.feed(body or "")
    return p.out


def clip(text, n=420):
    return text if len(text) <= n else text[: n].rsplit(" ", 1)[0] + "…"


def fcdo(slug):
    url = f"https://www.gov.uk/foreign-travel-advice/{slug}"
    d = json.loads(get(f"https://www.gov.uk/api/content/foreign-travel-advice/{slug}"))
    det = d["details"]
    parts = {p["slug"]: p for p in det.get("parts", [])}
    if not parts:
        raise ValueError("no advice parts (page moved or withdrawn?)")
    level, alert = max((ALERTS.get(a, (0, "")) for a in det.get("alert_status") or []), default=(1, "FCDO does not advise against travel"))

    def link(part):
        return f"{url}/{part}"

    warnings = [clip(t) for h2, h3, ps in sections(parts.get("warnings-and-insurance", {}).get("body"))
                if not re.search(r"insurance|before you travel|travel advice help|consular", h2 + h3, re.I)
                for t in ps if not re.search(r"insurance could be invalidated", t)][:4]

    security, laws = [], []
    for slug_ in ("safety-and-security", "terrorism", "local-laws-and-customs", "regional-risks"):
        for h2, h3, ps in sections(parts.get(slug_, {}).get("body")):
            head = h3 or h2
            if re.search(r"law|custom|cultur", h2 + " " + slug_, re.I):
                if h3 and len(laws) < 8:
                    laws.append({"heading": h3, "text": clip(" ".join(ps[:4]), 320), "url": link(slug_)})
            elif ps[0].startswith("There is a high threat of terrorist attack globally"):
                continue  # the same worldwide paragraph appears on every country
            elif SECURITY.search(head) and len(security) < 8 and not any(s["heading"] == head for s in security):
                security.append({"heading": head, "text": clip(" ".join(ps[:2])), "url": link(slug_)})

    visa = []
    for h2, h3, ps in sections(parts.get("entry-requirements", {}).get("body")):
        if re.search(r"visa|e-?visa|entry permit", h2 + " " + h3, re.I) and len(visa) < 4:
            visa.append({"heading": h3 or h2, "text": clip(" ".join(ps[:2]), 500)})

    history = [{"date": h["public_timestamp"][:10], "note": clip(re.sub(r"\s+", " ", h["note"]).strip(), 300)}
               for h in (det.get("change_history") or [])[:5]]
    return {"url": url, "level": level, "alert": alert, "updated": d.get("public_updated_at", "")[:10],
            "reviewed": (det.get("reviewed_at") or "")[:10], "changes": history, "warnings": warnings,
            "security": security, "laws": laws, "visa": visa, "visa_url": link("entry-requirements")}


def us_advisories():
    root = ET.fromstring(get("https://travel.state.gov/_res/rss/TAsTWs.xml"))
    out = {}
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        m = re.match(r"(.+?)\s+-\s+Level\s+(\d)\s*:\s*(.+)", title)
        if m:
            date = item.findtext("pubDate") or ""
            try:
                date = datetime.datetime.strptime(date.strip()[:16], "%a, %d %b %Y").date().isoformat()
            except ValueError:
                date = ""
            out[m.group(1).strip().lower()] = {"level": int(m.group(2)), "title": m.group(3).strip(), "date": date,
                                       "url": (item.findtext("link") or "").strip()}
    return out


def reliefweb(iso3):
    appname = os.environ.get("RELIEFWEB_APPNAME") or "hostileenvironmentjobs"
    query = {"filter": {"operator": "AND", "conditions": [{"field": "primary_country.iso3", "value": iso3.lower()},
             {"field": "date.created", "value": {"from": (NOW - datetime.timedelta(days=30)).strftime("%Y-%m-%dT00:00:00+00:00")}}]},
             "fields": {"include": ["title", "date.created", "source.shortname", "url_alias", "format.name"]},
             "sort": ["date.created:desc"], "limit": 6}
    d = json.loads(get(f"https://api.reliefweb.int/v2/reports?appname={appname}", json.dumps(query).encode()))
    return [{"title": r["fields"]["title"], "date": r["fields"]["date"]["created"][:10],
             "source": ", ".join(s.get("shortname", "") for s in r["fields"].get("source", [])[:2]),
             "type": (r["fields"].get("format") or [{}])[0].get("name", ""),
             "url": r["fields"].get("url_alias") or f"https://reliefweb.int/node/{r['id']}"} for r in d.get("data", [])]


def main():
    countries = json.loads((ROOT / "deploy-countries.json").read_text())["countries"]
    path = ROOT / "deploy.json"
    old = {c["iso2"]: c for c in json.loads(path.read_text())["countries"]} if path.exists() else {}
    errors = []
    try:
        us = us_advisories()
    except Exception as err:
        us, _ = {}, errors.append(f"US State Dept feed: {err}")
    rw_ok = True
    out = []
    for c in countries:
        prev = old.get(c["iso2"], {})
        row = {k: c[k] for k in ("iso2", "name", "region", "place", "lat", "lon", "culture")}
        try:
            row["fcdo"] = fcdo(c["fcdo"])
        except Exception as err:
            errors.append(f"FCDO {c['fcdo']}: {err}")
            row["fcdo"] = prev.get("fcdo")
        adv = us.get(US_NAMES.get(c["iso2"], c["name"]).lower())
        if us and not adv:
            errors.append(f"US advisory not found for {c['name']}; names starting {c['name'][:3]!r}: {[k for k in us if k.startswith(c['name'][:3].lower())]}")
        row["us"] = adv or prev.get("us")
        row["reports"] = prev.get("reports", [])
        if rw_ok:
            try:
                row["reports"] = reliefweb(ISO3[c["iso2"]])
            except Exception as err:
                # One failure usually means the API is refusing us (e.g. appname not approved); stop asking.
                errors.append(f"ReliefWeb: {err}")
                rw_ok = False
        out.append(row)
        time.sleep(0.3)
    if not any(r.get("fcdo") for r in out):
        sys.exit("No FCDO data at all, not writing deploy.json:\n" + "\n".join(errors))
    path.write_text(json.dumps({"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "errors": errors, "countries": out},
                               ensure_ascii=False, indent=1) + "\n")
    print(f"Wrote {len(out)} countries" + (f"; {len(errors)} problems:\n  " + "\n  ".join(errors) if errors else ""))


if __name__ == "__main__":
    main()
