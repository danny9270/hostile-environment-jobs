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
  visitsCache = { body, until: Date.now() + 5 * 60 * 1000 };
  return body;
}

// What a finished checkout was for: the alerts app tags its own; Payment Links are named by their product, or guessed from the price.
function paymentLabel(s) {
  if (/^HEJ-/.test(s.client_reference_id || s.metadata?.code || "")) return "Job alerts, 1 year";
  const item = s.line_items?.data?.[0]?.description;
  if (item) return item;
  if (s.currency === "gbp" && s.amount_total === 4900) return "Featured job";
  if (s.currency === "gbp" && s.amount_total === 14900) return "Featured employer";
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

  if (path === "" || path === "/") return new Response("Hostile Environment Jobs alerts. The app is at " + SITE + "/app/", { headers: cors(req) });
  return json(req, { error: "Not found" }, 404);
}

export default {
  async fetch(req, env) {
    try { return await handle(req, env); }
    catch (err) { return json(req, { error: String(err.message || err) }, 500); }
  },
};
