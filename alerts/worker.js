// Job alerts backend: a Cloudflare Worker (free plan) with a D1 database bound as DB.
// It keeps alert accounts, their preferences and their phones, and takes the $6 a year through Stripe Checkout.
// It never sends the notifications itself: the "Job alerts" GitHub Action asks it who wants what and sends them,
// because encrypting a push for every phone would go past the free plan's CPU limit.
//
// Settings (Worker > Settings > Variables and Secrets):
//   STRIPE_SECRET_KEY  secret. A restricted key with Checkout Sessions write, Prices read, Subscriptions read.
//                      Until it's set the app is free for everyone, so it can be tried out.
//   STRIPE_PRICE       the price id (price_...) of the "Job alerts, 1 year" product. Yearly recurring renews on its own;
//                      a one-off price gives a year and the app offers a renew button when it runs out.
// The push keys (VAPID) are made by the Worker the first time it runs and kept in the database.
// Referrals: every account has a short public referral code. Each 3 people who pay through someone's link earn them a
// free year. For a renewing subscription that pushes the next Stripe charge back a year, which needs the key above to
// have Subscriptions write as well; without it the year is still added here but Stripe would charge as normal.
// The Action proves who it is with a GitHub sign-in token for this repository, so there is no shared password.
// The admin page (/admin/) asks for payments with its own GitHub key; only the repository owner's key gets them.
// Payments are read from finished Stripe Checkouts, which also covers Payment Links, so the key above needs nothing more.
//   GOATCOUNTER_KEY    secret. A GoatCounter API key with "Read statistics" ticked. The admin page then shows visitor
//                      stats in any browser it's signed in on, without pasting the key into each one.
//   GOATCOUNTER_SITE   optional, the GoatCounter site code if it isn't "hostileenvironmentjobs".
// Course reviews: the "Review a course" form on the site posts here. Reviews wait in the database until the admin page
// publishes them (into reviews.json) or rejects them; nothing a visitor sends goes on the site by itself.
// Talent pool (/candidates/): operators post a profile and an "available from" date, free. Employers see the profiles
// without names, contact details or CVs, and only once the admin page has approved them and they've paid for search.
// An employer asks to get in touch; the operator's name, email, phone and CV are released only if they accept.
//   STRIPE_SEARCH_PRICE  the price id of the one-off "Candidate search, 30 days" product (£99). Without it employers
//                        can't pay by card, and the admin page gives them search days by hand (for invoices and the
//                        £149 Featured employer plan, which includes 90 days of search).
//   RESEND_API_KEY       optional secret, a Resend sending key for hostileenvironmentjobs.com. With it, operators get an
//                        email when an employer asks to get in touch, employers when they're accepted or approved,
//                        and contact@ when a new employer signs up. Without it everything still works on the page.
//   MAIL_FROM            optional, the sender, default "H.E. Jobs <jobs@hostileenvironmentjobs.com>".

const SITE = "https://hostileenvironmentjobs.com";
const REPO = "danny9270/hostile-environment-jobs";
const OWNER = REPO.split("/")[0];
const AUDIENCE = "hej-alerts";
const YEAR = 365 * 86400;
const DAY = 86400;
const REFERRALS_PER_YEAR = 3;

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS accounts (code TEXT PRIMARY KEY, prefs TEXT NOT NULL DEFAULT '{}', paid_until INTEGER NOT NULL DEFAULT 0,
     email TEXT, customer TEXT, subscription TEXT, pending_session TEXT, source TEXT, created INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS devices (endpoint TEXT PRIMARY KEY, code TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'web',
     sub TEXT NOT NULL, created INTEGER NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS devices_code ON devices (code)`,
  `CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, data TEXT NOT NULL, email TEXT, sender TEXT, created INTEGER NOT NULL)`,
  // Talent pool. profile is what approved employers see; private (name, email, phone, LinkedIn) only goes to employers
  // the operator accepts. pid is the id employers see, so the sign-in code never leaves the operator's own page.
  `CREATE TABLE IF NOT EXISTS candidates (code TEXT PRIMARY KEY, pid TEXT NOT NULL UNIQUE, profile TEXT NOT NULL, private TEXT NOT NULL,
     visible INTEGER NOT NULL DEFAULT 1, consent INTEGER NOT NULL, refreshed INTEGER NOT NULL, sender TEXT, created INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS cvs (code TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL, created INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS recruiters (code TEXT PRIMARY KEY, company TEXT NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL, website TEXT,
     about TEXT, status TEXT NOT NULL DEFAULT 'pending', access_until INTEGER NOT NULL DEFAULT 0, pending_session TEXT, sender TEXT, created INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS contact_requests (id TEXT PRIMARY KEY, recruiter TEXT NOT NULL, pid TEXT NOT NULL, role TEXT, message TEXT,
     status TEXT NOT NULL DEFAULT 'pending', created INTEGER NOT NULL, decided INTEGER, UNIQUE (recruiter, pid))`,
];
// Columns added after launch. SQLite has no ADD COLUMN IF NOT EXISTS, so each runs on its own and "duplicate column" is ignored.
const COLUMNS = ["ALTER TABLE accounts ADD COLUMN ref TEXT", "ALTER TABLE accounts ADD COLUMN referred_by TEXT",
                 "ALTER TABLE accounts ADD COLUMN ref_rewarded INTEGER NOT NULL DEFAULT 0"];
let ready = null;
const setup = db => (ready ??= (async () => {
  await db.batch(SCHEMA.map(s => db.prepare(s)));
  for (const c of COLUMNS) await db.prepare(c).run().catch(err => { if (!/duplicate column/i.test(err.message)) throw err; });
  await db.prepare("CREATE UNIQUE INDEX IF NOT EXISTS accounts_ref ON accounts (ref)").run();
})().catch(err => { ready = null; throw err; }));

const now = () => Math.floor(Date.now() / 1000);
const b64url = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64url = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), c => c.charCodeAt(0));

function cors(req) {
  const origin = req.headers.get("Origin") || "";
  const ok = origin === SITE || origin === "https://www.hostileenvironmentjobs.com" || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
  return { "Access-Control-Allow-Origin": ok ? origin : SITE, "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
           "Access-Control-Allow-Headers": "Content-Type, Authorization", "Vary": "Origin" };
}
const json = (req, body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...cors(req) } });

// Codes look like HEJ-7KQ2-M9XD-4TWB: 60 random bits, easy to read out, and the only thing that unlocks an account.
function newCode() {
  const abc = "0123456789ABCDEFGHJKMNPQRSTVWXYZ", r = crypto.getRandomValues(new Uint8Array(12));
  const s = [...r].map(x => abc[x & 31]).join("");
  return `HEJ-${s.slice(0, 4)}-${s.slice(4, 8)}-${s.slice(8)}`;
}
const newRef = () => { const abc = "23456789ABCDEFGHJKMNPQRSTVWXYZ"; return [...crypto.getRandomValues(new Uint8Array(6))].map(x => abc[x % abc.length]).join(""); };
const cleanRef = r => String(r || "").toUpperCase().replace(/[^0-9A-Z]/g, "").slice(0, 6);
const cleanCode = c => { const s = String(c || "").toUpperCase().replace(/[^0-9A-Z]/g, ""); return (s.length === 15 ? s.slice(3) : s).replace(/O/g, "0").replace(/[IL]/g, "1"); };
const fmtCode = c => { const s = cleanCode(c); return s.length === 12 ? `HEJ-${s.slice(0, 4)}-${s.slice(4, 8)}-${s.slice(8)}` : null; };

async function vapid(db) {
  const row = await db.prepare("SELECT v FROM config WHERE k = 'vapid'").first();
  if (row) return JSON.parse(row.v);
  const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
  const jwk = await crypto.subtle.exportKey("jwk", pair.privateKey);
  const keys = { public: b64url(await crypto.subtle.exportKey("raw", pair.publicKey)), private: jwk.d };
  await db.prepare("INSERT OR IGNORE INTO config (k, v) VALUES ('vapid', ?)").bind(JSON.stringify(keys)).run();
  return JSON.parse((await db.prepare("SELECT v FROM config WHERE k = 'vapid'").first()).v);
}

async function stripe(env, method, path, params) {
  const res = await fetch("https://api.stripe.com/v1/" + path, {
    method, body: params ? new URLSearchParams(params) : undefined,
    headers: { Authorization: "Bearer " + env.STRIPE_SECRET_KEY, "Content-Type": "application/x-www-form-urlencoded" },
  });
  const body = await res.json();
  if (!res.ok) throw new Error("Stripe: " + (body.error?.message || res.status));
  return body;
}
const paying = env => Boolean(env.STRIPE_SECRET_KEY && env.STRIPE_PRICE);

// Brings an account's paid_until up to date with Stripe: a finished checkout adds a year, a live subscription runs to its period end.
async function refresh(env, acct) {
  if (!paying(env)) return acct;
  const t = now();
  let firstPayment = false;
  if (acct.pending_session) {
    const s = await stripe(env, "GET", "checkout/sessions/" + acct.pending_session);
    if (s.status === "complete" && s.payment_status !== "unpaid") {
      firstPayment = acct.source !== "stripe";
      acct.paid_until = Math.max(acct.paid_until, t) + YEAR;
      acct.email = s.customer_details?.email || acct.email;
      acct.customer = s.customer || acct.customer;
      acct.subscription = s.subscription || acct.subscription;
      acct.pending_session = null;
      acct.source = "stripe";
    } else if (s.status === "expired") acct.pending_session = null;
  } else if (acct.subscription && acct.paid_until < t + DAY) {
    const sub = await stripe(env, "GET", "subscriptions/" + acct.subscription);
    const end = sub.items?.data?.[0]?.current_period_end || sub.current_period_end;
    if (["active", "trialing"].includes(sub.status) && end > acct.paid_until) acct.paid_until = end;
    if (sub.status === "canceled") acct.subscription = null;
  } else return acct;
  await env.DB.prepare("UPDATE accounts SET paid_until = ?, email = ?, customer = ?, subscription = ?, pending_session = ?, source = ? WHERE code = ?")
    .bind(acct.paid_until, acct.email, acct.customer, acct.subscription, acct.pending_session, acct.source, acct.code).run();
  if (firstPayment && acct.referred_by) await reward(env, acct.referred_by).catch(() => {});
  return acct;
}

// Counts the people who have paid through a referral code and gives its owner a free year for each 3 not yet rewarded.
async function reward(env, ref) {
  const db = env.DB;
  const owner = await db.prepare("SELECT * FROM accounts WHERE ref = ?").bind(ref).first();
  if (!owner) return;
  const paid = (await db.prepare("SELECT COUNT(*) AS n FROM accounts WHERE referred_by = ? AND source = 'stripe'").bind(ref).first()).n;
  const years = Math.floor(paid / REFERRALS_PER_YEAR) - owner.ref_rewarded;
  if (years <= 0) return;
  // Claim the years first, so two payments landing together can't both hand them out.
  const claimed = await db.prepare("UPDATE accounts SET ref_rewarded = ref_rewarded + ? WHERE code = ? AND ref_rewarded = ?").bind(years, owner.code, owner.ref_rewarded).run();
  if (!claimed.meta?.changes) return;
  let until = Math.max(owner.paid_until, now()) + years * YEAR;
  if (owner.subscription) {
    // Moves the next charge back by the free years. Stripe treats the gap as a trial, so nothing is charged or refunded now.
    const sub = await stripe(env, "GET", "subscriptions/" + owner.subscription).catch(() => null);
    const end = sub && (sub.items?.data?.[0]?.current_period_end || sub.current_period_end);
    if (sub && ["active", "trialing"].includes(sub.status) && end) {
      until = Math.max(owner.paid_until, end) + years * YEAR;
      await stripe(env, "POST", "subscriptions/" + owner.subscription, { trial_end: String(until), proration_behavior: "none" }).catch(() => {});
    }
  }
  await db.prepare("UPDATE accounts SET paid_until = ? WHERE code = ?").bind(until, owner.code).run();
}

// Gives older accounts a referral code the first time they're looked at.
async function ensureRef(db, acct) {
  if (acct.ref) return acct;
  for (let i = 0; i < 5 && !acct.ref; i++) {
    const ref = newRef();
    const r = await db.prepare("UPDATE accounts SET ref = ? WHERE code = ? AND ref IS NULL AND NOT EXISTS (SELECT 1 FROM accounts WHERE ref = ?)").bind(ref, acct.code, ref).run();
    acct.ref = r.meta?.changes ? ref : (await db.prepare("SELECT ref FROM accounts WHERE code = ?").bind(acct.code).first()).ref;
  }
  return acct;
}

const active = (env, acct) => !paying(env) || acct.paid_until > now();

async function publicAccount(env, acct, devices) {
  acct = await ensureRef(env.DB, acct);
  const referred = (await env.DB.prepare("SELECT COUNT(*) AS n FROM accounts WHERE referred_by = ? AND source = 'stripe'").bind(acct.ref).first()).n;
  return { code: acct.code, ref: acct.ref, referrals: referred, referrals_per_year: REFERRALS_PER_YEAR, free_years: acct.ref_rewarded || 0, active: active(env, acct), free: !paying(env), paid_until: acct.paid_until || null,
           renews: Boolean(acct.subscription), email: acct.email, prefs: JSON.parse(acct.prefs || "{}"), devices,
           checkout_pending: Boolean(acct.pending_session) };
}

const CLEAN_PREFS = p => ({
  categories: (Array.isArray(p.categories) ? p.categories : []).map(String).slice(0, 40),
  regions: (Array.isArray(p.regions) ? p.regions : []).map(String).slice(0, 20),
  keywords: String(p.keywords || "").slice(0, 200),
  courses: Boolean(p.courses),
  course_types: (Array.isArray(p.course_types) ? p.course_types : []).map(String).slice(0, 20),
});

// Admin sign-in: the GitHub key the admin page already uses, accepted only if it belongs to the repository owner.
// Answers are remembered for a few minutes so the admin page doesn't ask GitHub on every load.
const admins = new Map();
async function fromAdmin(req) {
  const token = (req.headers.get("Authorization") || "").replace(/^Bearer /, "");
  if (token.length < 20) return false;
  const id = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token)));
  const hit = admins.get(id);
  if (hit && hit.until > Date.now()) return hit.ok;
  const res = await fetch("https://api.github.com/user", { headers: { Authorization: "Bearer " + token, Accept: "application/vnd.github+json", "User-Agent": "hej-alerts" } });
  const ok = res.ok && (await res.json()).login?.toLowerCase() === OWNER.toLowerCase();
  if (admins.size > 50) admins.clear();
  admins.set(id, { ok, until: Date.now() + 5 * 60 * 1000 });
  return ok;
}

// Visitor stats: GoatCounter allows about 4 calls a second, so ask one at a time and keep the answer for a few minutes.
let visitsCache = null;
async function visits(env) {
  if (visitsCache && visitsCache.until > Date.now()) return visitsCache.body;
  const base = `https://${env.GOATCOUNTER_SITE || "hostileenvironmentjobs"}.goatcounter.com/api/v0`;
  const end = new Date(), start = new Date(end - 29 * DAY * 1000); start.setUTCHours(0, 0, 0, 0);
  const range = `start=${start.toISOString().slice(0, 19)}Z&end=${end.toISOString().slice(0, 19)}Z`;
  async function get(p) {
    for (let attempt = 0; ; attempt++) {
      const r = await fetch(base + p, { headers: { Authorization: "Bearer " + env.GOATCOUNTER_KEY, "Content-Type": "application/json" } });
      if (r.ok) { await new Promise(res => setTimeout(res, 300)); return r.json(); }
      if (r.status === 429 && attempt < 3) { await new Promise(res => setTimeout(res, 1500 * (attempt + 1))); continue; }
      const why = await r.text().catch(() => "");
      throw new Error(`GoatCounter error ${r.status}${why ? ": " + why.slice(0, 200) : ""}`);
    }
  }
  const body = { total: await get(`/stats/total?${range}`), pages: await get(`/stats/hits?${range}&limit=6`), refs: await get(`/stats/toprefs?${range}&limit=6`) };
  // Course booking clicks are GoatCounter events named book/<course id>; the admin page totals them per provider.
  const all = await get(`/stats/hits?${range}&limit=100`);
  body.bookings = (all.hits || []).filter(h => String(h.path).startsWith("book/")).map(h => ({ path: h.path, title: h.title, count: h.count }));
  visitsCache = { body, until: Date.now() + 5 * 60 * 1000 };
  return body;
}

// What a finished checkout was for: the alerts app tags its own; Payment Links are named by their product, or guessed from the price.
function paymentLabel(s) {
  if (s.metadata?.kind === "search") return "Candidate search, " + SEARCH_DAYS + " days";
  if (/^HEJ-/.test(s.client_reference_id || s.metadata?.code || "")) return "Job alerts, 1 year";
  const item = s.line_items?.data?.[0]?.description;
  if (item) return item;
  if (s.currency === "gbp" && s.amount_total === 4900) return "Featured job";
  if (s.currency === "gbp" && s.amount_total === 14900) return "Featured employer";
  if (s.currency === "gbp" && s.amount_total === 9900) return "Candidate search, " + SEARCH_DAYS + " days";
  return s.payment_link ? "Payment link" : "Other";
}

async function payments(env) {
  const t = now(), db = env.DB;
  const one = q => db.prepare(q).bind(t).first().then(r => r.n);
  const alerts = {
    accounts: (await db.prepare("SELECT COUNT(*) AS n FROM accounts").first()).n,
    active: await one("SELECT COUNT(*) AS n FROM accounts WHERE paid_until > ?"),
    renewing: await one("SELECT COUNT(*) AS n FROM accounts WHERE paid_until > ? AND subscription IS NOT NULL"),
    phones: (await db.prepare("SELECT COUNT(*) AS n FROM devices").first()).n,
    referred: (await db.prepare("SELECT COUNT(*) AS n FROM accounts WHERE referred_by IS NOT NULL AND source = 'stripe'").first()).n,
  };
  if (!env.STRIPE_SECRET_KEY) return { stripe: false, alerts, payments: [] };
  // Up to 500 of the latest finished checkouts. Renewals a year on are invoices, not checkouts, and come later.
  const list = [];
  let after = null, expand = true;
  for (let page = 0; page < 5; page++) {
    const q = new URLSearchParams({ limit: "100", status: "complete" });
    if (expand) q.append("expand[]", "data.line_items");
    if (after) q.set("starting_after", after);
    let r;
    try { r = await stripe(env, "GET", "checkout/sessions?" + q); }
    catch (err) { if (!expand) throw err; expand = false; page--; continue; }
    list.push(...r.data);
    if (!r.has_more || !r.data.length) break;
    after = r.data[r.data.length - 1].id;
  }
  const rows = list.filter(s => s.payment_status === "paid" || s.payment_status === "no_payment_required").map(s => ({
    id: s.id, created: s.created, amount: (s.amount_total || 0) / 100, currency: (s.currency || "").toUpperCase(),
    what: paymentLabel(s), email: s.customer_details?.email || null, name: s.customer_details?.name || null, mode: s.mode,
    test: !s.livemode,
  }));
  return { stripe: true, alerts, payments: rows };
}

// GitHub Actions sign-in: an RS256 token from token.actions.githubusercontent.com, for this repo's main branch.
let jwks = null;
async function fromAction(req) {
  try { return await checkActionToken(req); } catch { return false; }
}
async function checkActionToken(req) {
  const token = (req.headers.get("Authorization") || "").replace(/^Bearer /, "");
  const [h, p, s] = token.split(".");
  if (!s) return false;
  const head = JSON.parse(new TextDecoder().decode(unb64url(h))), claims = JSON.parse(new TextDecoder().decode(unb64url(p)));
  jwks ??= fetch("https://token.actions.githubusercontent.com/.well-known/jwks").then(r => r.json());
  let jwk = (await jwks).keys.find(k => k.kid === head.kid);
  if (!jwk) { jwks = null; jwk = (await (jwks = fetch("https://token.actions.githubusercontent.com/.well-known/jwks").then(r => r.json()))).keys.find(k => k.kid === head.kid); }
  if (!jwk || head.alg !== "RS256") return false;
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, unb64url(s), new TextEncoder().encode(h + "." + p));
  return ok && claims.iss === "https://token.actions.githubusercontent.com" && claims.aud === AUDIENCE
    && claims.repository === REPO && claims.ref === "refs/heads/main" && claims.exp > now();
}

// ---------- Talent pool ----------
const SEARCH_DAYS = 30;
const FRESH_DAYS = 90;    // a profile drops out of search this long after the operator last said they're available
const KEEP_DAYS = 365;    // and is deleted, with its CV and requests, this long after
const CV_MAX = 1400000;   // D1 keeps up to 2MB a row, and the CV is stored as base64 text
const CATEGORIES = ["EOD", "IEDD", "Search", "Survey & Clearance", "Security", "Maritime Security", "Medical", "Security Risk & Analysis", "K9", "CBRN", "Management", "Quality & Safety", "Training", "Life Support & Logistics", "Aviation", "Other"];
const REGIONS = ["Africa", "Middle East", "Europe", "Asia", "Americas", "Oceania"];
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const txt = (v, n) => String(v ?? "").trim().slice(0, n);
const pick = (v, from, n) => [...new Set((Array.isArray(v) ? v : []).map(String).filter(x => from.includes(x)))].slice(0, n);
const isDay = d => /^\d{4}-\d\d-\d\d$/.test(d || "") && !isNaN(new Date(d + "T00:00:00Z"));
const today = () => new Date().toISOString().slice(0, 10);
const newId = () => b64url(crypto.getRandomValues(new Uint8Array(9)));
const bearerCode = req => (req.headers.get("Authorization") || "").replace(/^Code\s+/i, "");
const senderOf = async (req, salt) => b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(salt + (req.headers.get("CF-Connecting-IP") || "")))).slice(0, 22);
const httpUrl = u => { const s = txt(u, 200); return !s ? "" : /^https?:\/\//i.test(s) ? s : "https://" + s; };

function cleanProfile(p) {
  p ||= {};
  return {
    headline: txt(p.headline, 120), categories: pick(p.categories, CATEGORIES, 6), years: Math.max(0, Math.min(50, parseInt(p.years, 10) || 0)),
    available_from: isDay(p.available_from) ? p.available_from : "", regions: pick(p.regions, REGIONS, 6), rotation: txt(p.rotation, 40),
    rate: txt(p.rate, 40), based: txt(p.based, 60), languages: txt(p.languages, 120), clearance: txt(p.clearance, 60),
    quals: txt(p.quals, 800), summary: txt(p.summary, 1500),
  };
}
const cleanPrivate = p => ({ name: txt(p?.name, 80), email: txt(p?.email, 200), phone: txt(p?.phone, 40), linkedin: httpUrl(p?.linkedin) });
const fresh = c => c.visible && c.refreshed > now() - FRESH_DAYS * DAY;

async function mail(env, to, subject, text) {
  if (!env.RESEND_API_KEY || !to) return false;
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST", headers: { Authorization: "Bearer " + env.RESEND_API_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ from: env.MAIL_FROM || "H.E. Jobs <jobs@hostileenvironmentjobs.com>", to: [to], reply_to: "contact@hostileenvironmentjobs.com",
                           subject, text: text + "\n\nH.E. Jobs Team\n" + SITE }),
  }).catch(() => null);
  return Boolean(res?.ok);
}

// Old profiles, CVs and requests go once a day or so; there's no timer on the free plan, so it runs on normal traffic.
let tidied = 0;
async function tidyTalent(db) {
  if (Date.now() - tidied < 3600 * 1000) return;
  tidied = Date.now();
  const old = now() - KEEP_DAYS * DAY;
  await db.batch([
    db.prepare("DELETE FROM cvs WHERE code IN (SELECT code FROM candidates WHERE refreshed < ?)").bind(old),
    db.prepare("DELETE FROM contact_requests WHERE pid IN (SELECT pid FROM candidates WHERE refreshed < ?)").bind(old),
    db.prepare("DELETE FROM candidates WHERE refreshed < ?").bind(old),
    db.prepare("DELETE FROM contact_requests WHERE created < ?").bind(old),
    db.prepare("DELETE FROM recruiters WHERE status = 'rejected' AND created < ?").bind(now() - 30 * DAY),
  ]);
}

// A recruiter's search time: a finished checkout adds SEARCH_DAYS, like refresh() does for alerts.
async function refreshRecruiter(env, r) {
  if (!r.pending_session || !env.STRIPE_SECRET_KEY) return r;
  const s = await stripe(env, "GET", "checkout/sessions/" + r.pending_session);
  if (s.status === "complete" && s.payment_status !== "unpaid") { r.access_until = Math.max(r.access_until, now()) + SEARCH_DAYS * DAY; r.pending_session = null; }
  else if (s.status === "expired") r.pending_session = null;
  else return r;
  await env.DB.prepare("UPDATE recruiters SET access_until = ?, pending_session = ? WHERE code = ?").bind(r.access_until, r.pending_session, r.code).run();
  return r;
}
const canSearch = r => r.status === "approved" && r.access_until > now();

async function candidateView(db, c) {
  const cv = await db.prepare("SELECT name, created FROM cvs WHERE code = ?").bind(c.code).first();
  const reqs = (await db.prepare(`SELECT q.id, q.role, q.message, q.status, q.created, r.company, r.name, r.email, r.website, r.about
      FROM contact_requests q JOIN recruiters r ON r.code = q.recruiter WHERE q.pid = ? ORDER BY q.created DESC`).bind(c.pid).all()).results;
  return { code: c.code, profile: JSON.parse(c.profile), private: JSON.parse(c.private), visible: Boolean(c.visible), live: Boolean(fresh(c)),
           refreshed: c.refreshed, hides_on: c.refreshed + FRESH_DAYS * DAY, cv: cv ? { name: cv.name, added: cv.created } : null,
           requests: reqs.map(q => ({ id: q.id, role: q.role, message: q.message, status: q.status, created: q.created, company: q.company,
             website: q.website, about: q.about, contact: q.status === "accepted" ? { name: q.name, email: q.email } : { name: q.name } })) };
}

async function recruiterView(env, r) {
  const reqs = (await env.DB.prepare(`SELECT q.id, q.pid, q.role, q.status, q.created, q.decided, c.profile, c.private, (SELECT 1 FROM cvs WHERE cvs.code = c.code) AS has_cv
      FROM contact_requests q LEFT JOIN candidates c ON c.pid = q.pid WHERE q.recruiter = ? ORDER BY q.created DESC`).bind(r.code).all()).results;
  return { code: r.code, company: r.company, name: r.name, email: r.email, website: r.website, status: r.status, access_until: r.access_until,
           can_search: canSearch(r), card: Boolean(env.STRIPE_SECRET_KEY && env.STRIPE_SEARCH_PRICE), checkout_pending: Boolean(r.pending_session), days: SEARCH_DAYS,
           requests: reqs.map(q => {
             const p = q.profile ? JSON.parse(q.profile) : null, accepted = q.status === "accepted" && p;
             return { id: q.id, pid: q.pid, role: q.role, status: p ? q.status : "gone", created: q.created, decided: q.decided,
                      headline: p?.headline || "Profile removed", contact: accepted ? JSON.parse(q.private) : null, cv: Boolean(accepted && q.has_cv) };
           }) };
}

async function handle(req, env) {
  const url = new URL(req.url), db = env.DB, path = url.pathname.replace(/\/+$/, "");
  if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });
  if (!db) return json(req, { error: "The Worker has no D1 database bound as DB yet." }, 500);
  await setup(db);
  const body = ["POST", "PUT", "DELETE"].includes(req.method) ? await req.json().catch(() => ({})) : {};
  const account = async c => { const code = fmtCode(c); return code && db.prepare("SELECT * FROM accounts WHERE code = ?").bind(code).first(); };
  const devicesOf = async code => (await db.prepare("SELECT endpoint, kind, created FROM devices WHERE code = ?").bind(code).all()).results;

  if (path === "/api/config") {
    let price = null;
    if (paying(env)) {
      const pr = await stripe(env, "GET", "prices/" + env.STRIPE_PRICE);
      price = { amount: pr.unit_amount / 100, currency: pr.currency.toUpperCase(), recurring: Boolean(pr.recurring) };
    }
    return json(req, { vapid_public_key: (await vapid(db)).public, free: !paying(env), price });
  }

  // Start: makes an account (or reuses the one on this phone) and, when payments are on, a Stripe Checkout for it.
  if (path === "/api/checkout" && req.method === "POST") {
    let acct = body.code && await account(body.code);
    if (!acct) {
      const by = cleanRef(body.ref) && await db.prepare("SELECT ref FROM accounts WHERE ref = ?").bind(cleanRef(body.ref)).first();
      acct = { code: newCode(), prefs: JSON.stringify(CLEAN_PREFS(body.prefs || {})), paid_until: 0, created: now(), referred_by: by?.ref || null };
      await db.prepare("INSERT INTO accounts (code, prefs, paid_until, created, referred_by) VALUES (?, ?, 0, ?, ?)").bind(acct.code, acct.prefs, acct.created, acct.referred_by).run();
    }
    if (!paying(env)) return json(req, { code: acct.code, url: null });
    const price = await stripe(env, "GET", "prices/" + env.STRIPE_PRICE);
    const back = `${SITE}/app/?code=${encodeURIComponent(acct.code)}`;
    const params = { mode: price.recurring ? "subscription" : "payment", "line_items[0][price]": env.STRIPE_PRICE, "line_items[0][quantity]": "1",
                     client_reference_id: acct.code, success_url: back + "&paid=1", cancel_url: back, allow_promotion_codes: "true",
                     "metadata[code]": acct.code };
    if (!price.recurring) params.customer_creation = "always";
    if (acct.customer) params.customer = acct.customer;
    const s = await stripe(env, "POST", "checkout/sessions", params);
    await db.prepare("UPDATE accounts SET pending_session = ? WHERE code = ?").bind(s.id, acct.code).run();
    return json(req, { code: acct.code, url: s.url });
  }

  if (path === "/api/account") {
    const code = req.method === "GET" ? url.searchParams.get("code") : body.code;
    let acct = await account(code);
    if (!acct) return json(req, { error: "No account with that code. Check it and try again." }, 404);
    if (req.method === "PUT" && body.prefs) {
      acct.prefs = JSON.stringify(CLEAN_PREFS(body.prefs));
      await db.prepare("UPDATE accounts SET prefs = ? WHERE code = ?").bind(acct.prefs, acct.code).run();
    }
    acct = await refresh(env, acct);
    return json(req, await publicAccount(env, acct, await devicesOf(acct.code)));
  }

  // A phone's push subscription: {code, subscription: {endpoint, keys}} from PushManager, or {code, kind: "fcm", token} from the store apps later.
  if (path === "/api/devices") {
    if (req.method === "DELETE") {
      await db.prepare("DELETE FROM devices WHERE endpoint = ?").bind(String(body.endpoint || "")).run();
      return json(req, { ok: true });
    }
    const acct = await account(body.code);
    if (!acct) return json(req, { error: "No account with that code." }, 404);
    const kind = body.kind === "fcm" ? "fcm" : "web";
    const sub = kind === "fcm" ? { token: String(body.token || "") } : body.subscription;
    const endpoint = kind === "fcm" ? "fcm:" + sub.token : sub?.endpoint;
    if (!endpoint || !/^(https:\/\/|fcm:.)/.test(endpoint) || (kind === "web" && !(sub.keys?.p256dh && sub.keys?.auth)))
      return json(req, { error: "That isn't a push subscription." }, 400);
    const count = (await db.prepare("SELECT COUNT(*) AS n FROM devices WHERE code = ? AND endpoint != ?").bind(acct.code, endpoint).first()).n;
    if (count >= 5) return json(req, { error: "This code is already on 5 phones. Remove one first." }, 400);
    await db.prepare("INSERT INTO devices (endpoint, code, kind, sub, created) VALUES (?, ?, ?, ?, ?) ON CONFLICT (endpoint) DO UPDATE SET code = excluded.code, sub = excluded.sub")
      .bind(endpoint, acct.code, kind, JSON.stringify(sub), now()).run();
    return json(req, { ok: true });
  }

  // For the sender only. Who to notify, what's been sent before, and the push keys.
  if (path === "/api/internal/recipients" && req.method === "GET") {
    if (!(await fromAction(req))) return json(req, { error: "Not allowed" }, 403);
    // Subscriptions that ran out in the last month get one look at Stripe in case they renewed.
    const lapsed = (await db.prepare("SELECT * FROM accounts WHERE subscription IS NOT NULL AND paid_until BETWEEN ? AND ? LIMIT 25").bind(now() - 30 * DAY, now() + DAY).all()).results;
    for (const a of lapsed) await refresh(env, a).catch(() => {});
    const rows = (await db.prepare(`SELECT d.endpoint, d.kind, d.sub, a.code, a.prefs, a.paid_until FROM devices d JOIN accounts a ON a.code = d.code`).all()).results;
    const recipients = rows.filter(r => active(env, r)).map(r => ({ endpoint: r.endpoint, kind: r.kind, sub: JSON.parse(r.sub), code: r.code, prefs: JSON.parse(r.prefs) }));
    const seen = (await db.prepare("SELECT id FROM seen").all()).results.map(r => r.id);
    const keys = await vapid(db);
    return json(req, { recipients, seen, vapid: keys });
  }

  // For the sender only: marks listings as sent and drops phones whose push address has gone.
  if (path === "/api/internal/sent" && req.method === "POST") {
    if (!(await fromAction(req))) return json(req, { error: "Not allowed" }, 403);
    const t = now(), stmts = [];
    for (const id of (body.seen || []).slice(0, 2000)) stmts.push(db.prepare("INSERT OR IGNORE INTO seen (id, at) VALUES (?, ?)").bind(String(id), t));
    for (const ep of (body.gone || []).slice(0, 2000)) stmts.push(db.prepare("DELETE FROM devices WHERE endpoint = ?").bind(String(ep)));
    if (stmts.length) await db.batch(stmts);
    return json(req, { ok: true });
  }

  // Course reviews from the site, held until the admin page publishes or rejects them.
  if (path === "/api/reviews" && req.method === "POST") {
    if (body._honey) return json(req, { ok: true }); // the hidden box only bots fill in
    const t = (v, n) => String(v ?? "").trim().slice(0, n);
    const r = { provider: t(body.provider, 120), course: t(body.course, 160), rating: Number(body.rating), headline: t(body.headline, 80),
                text: t(body.text, 2000), name: t(body.name, 40), background: t(body.background, 60),
                attended: /^\d{4}-\d\d$/.test(body.attended || "") ? body.attended : "", posted: new Date().toISOString().slice(0, 10) };
    const email = t(body.email, 200);
    if (!r.provider || !r.course || !(r.rating >= 1 && r.rating <= 5) || !Number.isInteger(r.rating) || r.text.length < 20 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))
      return json(req, { error: "Some of the review is missing. Check the form and send it again." }, 400);
    // A few reviews a day from one connection is plenty; the address is only kept as a one-way hash.
    const sender = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode("hej-review:" + (req.headers.get("CF-Connecting-IP") || "")))).slice(0, 22);
    const recent = await db.prepare("SELECT COUNT(*) AS n FROM reviews WHERE sender = ? AND created > ?").bind(sender, now() - DAY).first();
    const waiting = await db.prepare("SELECT COUNT(*) AS n FROM reviews").first();
    if (recent.n >= 5 || waiting.n >= 500) return json(req, { error: "We've had a lot of reviews from here today. Please try again tomorrow." }, 429);
    const id = b64url(crypto.getRandomValues(new Uint8Array(9)));
    await db.prepare("INSERT INTO reviews (id, data, email, sender, created) VALUES (?, ?, ?, ?, ?)").bind(id, JSON.stringify(r), email, sender, now()).run();
    return json(req, { ok: true });
  }

  // For the admin page only: reviews waiting to be checked, and removing one once it's published or rejected.
  if (path === "/api/admin/reviews" && ["GET", "DELETE"].includes(req.method)) {
    if (!(await fromAdmin(req))) return json(req, { error: "Not allowed" }, 403);
    if (req.method === "DELETE") {
      await db.prepare("DELETE FROM reviews WHERE id = ?").bind(String(url.searchParams.get("id") || "")).run();
      return json(req, { ok: true });
    }
    const rows = (await db.prepare("SELECT id, data, email, created FROM reviews ORDER BY created").all()).results;
    return json(req, { reviews: rows.map(x => ({ id: x.id, email: x.email, created: x.created, review: JSON.parse(x.data) })) });
  }

  // For the admin page only: visitor stats for the last 30 days from GoatCounter.
  if (path === "/api/admin/visits" && req.method === "GET") {
    if (!(await fromAdmin(req))) return json(req, { error: "Not allowed" }, 403);
    if (!env.GOATCOUNTER_KEY) return json(req, { error: "not set up" }, 501);
    return json(req, await visits(env));
  }

  // For the admin page only: payments received and alert subscriber numbers.
  if (path === "/api/admin/payments" && req.method === "GET") {
    if (!(await fromAdmin(req))) return json(req, { error: "Not allowed" }, 403);
    return json(req, await payments(env));
  }

  // ---------- Talent pool: operators ----------
  if (path.startsWith("/api/talent")) await tidyTalent(db).catch(() => {});
  const candidate = async () => { const code = fmtCode(bearerCode(req)); return code && db.prepare("SELECT * FROM candidates WHERE code = ?").bind(code).first(); };
  const recruiter = async () => { const code = fmtCode(bearerCode(req)); return code && db.prepare("SELECT * FROM recruiters WHERE code = ?").bind(code).first(); };

  // Public numbers for the page: how many operators are available, by job type. Nothing about any one person.
  if (path === "/api/talent/stats" && req.method === "GET") {
    const rows = (await db.prepare("SELECT profile FROM candidates WHERE visible = 1 AND refreshed > ?").bind(now() - FRESH_DAYS * DAY).all()).results;
    const by = {};
    for (const r of rows) for (const c of JSON.parse(r.profile).categories) by[c] = (by[c] || 0) + 1;
    return json(req, { available: rows.length, by_category: by, search_days: SEARCH_DAYS, card: Boolean(env.STRIPE_SECRET_KEY && env.STRIPE_SEARCH_PRICE) });
  }

  // Make or update your profile. Saving it also counts as "still available" and puts it back in search.
  if (path === "/api/talent/profile" && req.method === "POST") {
    if (body._honey) return json(req, { ok: true });
    const profile = cleanProfile(body.profile), priv = cleanPrivate(body.private);
    if (!profile.headline || !profile.categories.length || !profile.available_from)
      return json(req, { error: "Add a headline, at least one job type and the date you're available from." }, 400);
    if (!priv.name || !EMAIL.test(priv.email)) return json(req, { error: "Add your name and a working email. Employers only see them if you accept their request." }, 400);
    if (body.consent !== true) return json(req, { error: "Tick the box to agree to how your profile is shared." }, 400);
    const visible = body.visible === false ? 0 : 1;
    let c = await candidate();
    if (c) {
      await db.prepare("UPDATE candidates SET profile = ?, private = ?, visible = ?, consent = ?, refreshed = ? WHERE code = ?")
        .bind(JSON.stringify(profile), JSON.stringify(priv), visible, now(), now(), c.code).run();
    } else {
      const sender = await senderOf(req, "hej-talent:");
      if ((await db.prepare("SELECT COUNT(*) AS n FROM candidates WHERE sender = ? AND created > ?").bind(sender, now() - DAY).first()).n >= 5)
        return json(req, { error: "We've had a lot of new profiles from here today. Please try again tomorrow." }, 429);
      const code = newCode();
      await db.prepare("INSERT INTO candidates (code, pid, profile, private, visible, consent, refreshed, sender, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
        .bind(code, newId(), JSON.stringify(profile), JSON.stringify(priv), visible, now(), now(), sender, now()).run();
      c = { code };
    }
    return json(req, await candidateView(db, await db.prepare("SELECT * FROM candidates WHERE code = ?").bind(c.code).first()));
  }

  if (path === "/api/talent/me") {
    const c = await candidate();
    if (!c) return json(req, { error: "No profile with that code. Check it and try again." }, 404);
    if (req.method === "DELETE") {
      // Everything goes: the profile, the CV and every request to or about it.
      await db.batch([db.prepare("DELETE FROM cvs WHERE code = ?").bind(c.code), db.prepare("DELETE FROM contact_requests WHERE pid = ?").bind(c.pid),
                      db.prepare("DELETE FROM candidates WHERE code = ?").bind(c.code)]);
      return json(req, { ok: true });
    }
    if (req.method === "POST" && ["available", "hide"].includes(body.action)) {
      await db.prepare("UPDATE candidates SET visible = ?, refreshed = CASE WHEN ? THEN ? ELSE refreshed END WHERE code = ?")
        .bind(body.action === "hide" ? 0 : 1, body.action === "available" ? 1 : 0, now(), c.code).run();
    }
    return json(req, await candidateView(db, await db.prepare("SELECT * FROM candidates WHERE code = ?").bind(c.code).first()));
  }

  // Your CV: a PDF, sent as base64. Only you, and employers whose request you accepted, can download it.
  if (path === "/api/talent/cv") {
    if (req.method === "GET") {
      let c = await candidate();
      if (!c) {
        const r = await recruiter(), pid = url.searchParams.get("pid") || "";
        const ok = r && r.status === "approved" && await db.prepare("SELECT 1 FROM contact_requests WHERE recruiter = ? AND pid = ? AND status = 'accepted'").bind(r.code, pid).first();
        c = ok && await db.prepare("SELECT * FROM candidates WHERE pid = ?").bind(pid).first();
      }
      const cv = c && await db.prepare("SELECT name, data FROM cvs WHERE code = ?").bind(c.code).first();
      if (!cv) return json(req, { error: "No CV to download." }, 404);
      return new Response(unb64url(cv.data.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")), { headers: { "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="${cv.name.replace(/[^\w .-]/g, "_")}"`, "Cache-Control": "no-store", "Access-Control-Expose-Headers": "Content-Disposition", ...cors(req) } });
    }
    const c = await candidate();
    if (!c) return json(req, { error: "No profile with that code." }, 404);
    if (req.method === "DELETE") await db.prepare("DELETE FROM cvs WHERE code = ?").bind(c.code).run();
    else {
      const data = String(body.data || "").replace(/^data:[^,]*,/, "").replace(/\s/g, "");
      if (data.length > Math.ceil(CV_MAX / 3) * 4) return json(req, { error: "That file is too big. Keep your CV under 1.4 MB." }, 400);
      if (!data.startsWith("JVBER")) return json(req, { error: "Your CV needs to be a PDF. The CV builder can make one." }, 400); // "%PDF" in base64
      const name = (txt(body.name, 80).replace(/\.pdf$/i, "") || "CV") + ".pdf";
      await db.prepare("INSERT INTO cvs (code, name, data, created) VALUES (?, ?, ?, ?) ON CONFLICT (code) DO UPDATE SET name = excluded.name, data = excluded.data, created = excluded.created")
        .bind(c.code, name, data, now()).run();
    }
    return json(req, await candidateView(db, c));
  }

  // Accept or decline an employer's request. Accepting releases your name, email, phone, LinkedIn and CV to them.
  if (path === "/api/talent/requests" && req.method === "POST") {
    const c = await candidate();
    if (!c) return json(req, { error: "No profile with that code." }, 404);
    const decision = body.decision === "accept" ? "accepted" : body.decision === "decline" ? "declined" : null;
    const q = decision && await db.prepare("SELECT q.*, r.email, r.company FROM contact_requests q JOIN recruiters r ON r.code = q.recruiter WHERE q.id = ? AND q.pid = ?").bind(String(body.id || ""), c.pid).first();
    if (!q) return json(req, { error: "That request has gone." }, 404);
    await db.prepare("UPDATE contact_requests SET status = ?, decided = ? WHERE id = ?").bind(decision, now(), q.id).run();
    if (decision === "accepted" && q.status !== "accepted") {
      const p = JSON.parse(c.profile), priv = JSON.parse(c.private);
      await mail(env, q.email, `${priv.name} accepted your request`, `${priv.name} (${p.headline}) is happy to hear from you${q.role ? " about " + q.role : ""}.\n\n`
        + `Their contact details${(await db.prepare("SELECT 1 FROM cvs WHERE code = ?").bind(c.code).first()) ? " and CV are" : " are"} on your talent pool page: ${SITE}/candidates/#hiring`);
    }
    return json(req, await candidateView(db, c));
  }

  // ---------- Talent pool: employers ----------
  if (path === "/api/hire/register" && req.method === "POST") {
    if (body._honey) return json(req, { ok: true });
    const r = { company: txt(body.company, 120), name: txt(body.name, 80), email: txt(body.email, 200), website: httpUrl(body.website), about: txt(body.about, 600) };
    if (!r.company || !r.name || !EMAIL.test(r.email)) return json(req, { error: "Add your company, your name and a work email." }, 400);
    const sender = await senderOf(req, "hej-hire:");
    if ((await db.prepare("SELECT COUNT(*) AS n FROM recruiters WHERE sender = ? AND created > ?").bind(sender, now() - DAY).first()).n >= 3)
      return json(req, { error: "We've had a lot of sign-ups from here today. Please email us instead." }, 429);
    const code = newCode();
    await db.prepare("INSERT INTO recruiters (code, company, name, email, website, about, sender, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
      .bind(code, r.company, r.name, r.email, r.website, r.about, sender, now()).run();
    await mail(env, "contact@hostileenvironmentjobs.com", `Talent pool sign-up: ${r.company}`,
      `${r.name} <${r.email}> from ${r.company}${r.website ? " (" + r.website + ")" : ""} wants to search the talent pool.\n\n${r.about}\n\nApprove or reject them in the admin page: ${SITE}/admin/#talent`);
    return json(req, await recruiterView(env, await db.prepare("SELECT * FROM recruiters WHERE code = ?").bind(code).first()));
  }

  if (path === "/api/hire/me" && req.method === "GET") {
    let r = await recruiter();
    if (!r) return json(req, { error: "No employer account with that code. Check it and try again." }, 404);
    r = await refreshRecruiter(env, r);
    return json(req, await recruiterView(env, r));
  }

  if (path === "/api/hire/checkout" && req.method === "POST") {
    const r = await recruiter();
    if (!r) return json(req, { error: "No employer account with that code." }, 404);
    if (r.status !== "approved") return json(req, { error: "We need to approve your account before you can pay. We'll email you, usually within a day." }, 400);
    if (!env.STRIPE_SECRET_KEY || !env.STRIPE_SEARCH_PRICE) return json(req, { error: "Card payments aren't switched on yet. Email contact@hostileenvironmentjobs.com and we'll invoice you." }, 501);
    const back = `${SITE}/candidates/#hiring`;
    const s = await stripe(env, "POST", "checkout/sessions", { mode: "payment", "line_items[0][price]": env.STRIPE_SEARCH_PRICE, "line_items[0][quantity]": "1",
      client_reference_id: "search-" + r.code.slice(4), customer_email: r.email, success_url: back, cancel_url: back, allow_promotion_codes: "true",
      "metadata[kind]": "search", "metadata[company]": r.company, "invoice_creation[enabled]": "true" });
    await db.prepare("UPDATE recruiters SET pending_session = ? WHERE code = ?").bind(s.id, r.code).run();
    return json(req, { url: s.url });
  }

  // Search: every available profile, without names or contact details. Filtering happens on the page.
  if (path === "/api/hire/search" && req.method === "GET") {
    await tidyTalent(db).catch(() => {});
    let r = await recruiter();
    if (!r) return json(req, { error: "No employer account with that code." }, 404);
    r = await refreshRecruiter(env, r);
    if (!canSearch(r)) return json(req, { error: r.status === "approved" ? "Your search time has run out." : "Your account is waiting for approval." }, 402);
    const rows = (await db.prepare("SELECT pid, profile, refreshed, (SELECT 1 FROM cvs WHERE cvs.code = candidates.code) AS has_cv FROM candidates WHERE visible = 1 AND refreshed > ? ORDER BY refreshed DESC LIMIT 1000")
      .bind(now() - FRESH_DAYS * DAY).all()).results;
    const asked = new Map((await db.prepare("SELECT pid, status FROM contact_requests WHERE recruiter = ?").bind(r.code).all()).results.map(x => [x.pid, x.status]));
    return json(req, { profiles: rows.map(x => ({ pid: x.pid, ...JSON.parse(x.profile), has_cv: Boolean(x.has_cv), updated: x.refreshed, request: asked.get(x.pid) || null })) });
  }

  if (path === "/api/hire/request" && req.method === "POST") {
    const r = await recruiter();
    if (!r || !canSearch(r)) return json(req, { error: "You need an approved account with search time to send requests." }, 403);
    const c = await db.prepare("SELECT * FROM candidates WHERE pid = ?").bind(String(body.pid || "")).first();
    if (!c || !fresh(c)) return json(req, { error: "That profile isn't available any more." }, 404);
    if ((await db.prepare("SELECT COUNT(*) AS n FROM contact_requests WHERE recruiter = ? AND created > ?").bind(r.code, now() - DAY).first()).n >= 30)
      return json(req, { error: "That's 30 requests today. You can send more tomorrow." }, 429);
    const role = txt(body.role, 120), message = txt(body.message, 1000);
    if (!role) return json(req, { error: "Say which role it's about." }, 400);
    const res = await db.prepare("INSERT OR IGNORE INTO contact_requests (id, recruiter, pid, role, message, created) VALUES (?, ?, ?, ?, ?, ?)")
      .bind(newId(), r.code, c.pid, role, message, now()).run();
    if (!res.meta?.changes) return json(req, { error: "You've already asked this person." }, 400);
    await mail(env, JSON.parse(c.private).email, `${r.company} would like to get in touch`,
      `${r.company} saw your profile on the Hostile Environment Jobs talent pool and would like to contact you about: ${role}.\n\n${message ? message + "\n\n" : ""}`
      + `They can't see your name, contact details or CV unless you accept. Accept or decline on your profile page: ${SITE}/candidates/\n\n`
      + "Not looking any more? You can hide or delete your profile there too.");
    return json(req, await recruiterView(env, r));
  }

  // ---------- Talent pool: admin ----------
  if (path === "/api/admin/talent") {
    if (!(await fromAdmin(req))) return json(req, { error: "Not allowed" }, 403);
    await tidyTalent(db).catch(() => {});
    if (req.method === "POST") {
      const r = await db.prepare("SELECT * FROM recruiters WHERE code = ?").bind(String(body.code || "")).first();
      if (!r) return json(req, { error: "No such employer." }, 404);
      const days = Math.max(0, Math.min(365, parseInt(body.days, 10) || 0));
      if (body.action === "approve") {
        await db.prepare("UPDATE recruiters SET status = 'approved', access_until = MAX(access_until, ?) WHERE code = ?").bind(days ? now() + days * DAY : 0, r.code).run();
        if (r.status !== "approved") await mail(env, r.email, "Your talent pool account is approved", `Hi ${r.name},\n\n${r.company} can now use the Hostile Environment Jobs talent pool.`
          + (days ? ` You have ${days} days of search.` : ` Search costs £99 for ${SEARCH_DAYS} days, or comes with our £149 Featured employer plan.`) + `\n\nSign in with your code at ${SITE}/candidates/#hiring`);
      } else if (body.action === "days") await db.prepare("UPDATE recruiters SET access_until = MAX(access_until, ?) + ? WHERE code = ?").bind(now(), days * DAY, r.code).run();
      else if (body.action === "stop") await db.prepare("UPDATE recruiters SET access_until = 0 WHERE code = ?").bind(r.code).run();
      else if (body.action === "reject") await db.prepare("UPDATE recruiters SET status = 'rejected', access_until = 0 WHERE code = ?").bind(r.code).run();
      else if (body.action === "delete") await db.batch([db.prepare("DELETE FROM contact_requests WHERE recruiter = ?").bind(r.code), db.prepare("DELETE FROM recruiters WHERE code = ?").bind(r.code)]);
    }
    if (req.method === "DELETE") {
      const c = await db.prepare("SELECT * FROM candidates WHERE pid = ?").bind(String(url.searchParams.get("pid") || "")).first();
      if (c) await db.batch([db.prepare("DELETE FROM cvs WHERE code = ?").bind(c.code), db.prepare("DELETE FROM contact_requests WHERE pid = ?").bind(c.pid),
                             db.prepare("DELETE FROM candidates WHERE code = ?").bind(c.code)]);
    }
    const recruiters = (await db.prepare(`SELECT r.code, r.company, r.name, r.email, r.website, r.about, r.status, r.access_until, r.created,
        (SELECT COUNT(*) FROM contact_requests q WHERE q.recruiter = r.code) AS sent, (SELECT COUNT(*) FROM contact_requests q WHERE q.recruiter = r.code AND q.status = 'accepted') AS accepted
        FROM recruiters r ORDER BY r.status = 'pending' DESC, r.created DESC`).all()).results;
    const candidates = (await db.prepare(`SELECT c.pid, c.profile, c.private, c.visible, c.refreshed, c.created, (SELECT 1 FROM cvs WHERE cvs.code = c.code) AS has_cv,
        (SELECT COUNT(*) FROM contact_requests q WHERE q.pid = c.pid) AS requests FROM candidates c ORDER BY c.refreshed DESC`).all()).results;
    return json(req, { recruiters, mail: Boolean(env.RESEND_API_KEY), card: Boolean(env.STRIPE_SECRET_KEY && env.STRIPE_SEARCH_PRICE), fresh_days: FRESH_DAYS,
      candidates: candidates.map(c => ({ pid: c.pid, profile: JSON.parse(c.profile), private: JSON.parse(c.private), live: Boolean(fresh(c)), visible: Boolean(c.visible),
                                         refreshed: c.refreshed, created: c.created, cv: Boolean(c.has_cv), requests: c.requests })) });
  }

  if (path === "" || path === "/") return new Response("Hostile Environment Jobs alerts. The app is at " + SITE + "/app/", { headers: cors(req) });
  return json(req, { error: "Not found" }, 404);
}

export default {
  async fetch(req, env) {
    try { return await handle(req, env); }
    catch (err) { return json(req, { error: String(err.message || err) }, 500); }
  },
};
