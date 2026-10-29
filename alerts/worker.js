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
// The Action proves who it is with a GitHub sign-in token for this repository, so there is no shared password.

const SITE = "https://hostileenvironmentjobs.com";
const REPO = "danny9270/hostile-environment-jobs";
const AUDIENCE = "hej-alerts";
const YEAR = 365 * 86400;
const DAY = 86400;

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS accounts (code TEXT PRIMARY KEY, prefs TEXT NOT NULL DEFAULT '{}', paid_until INTEGER NOT NULL DEFAULT 0,
     email TEXT, customer TEXT, subscription TEXT, pending_session TEXT, source TEXT, created INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS devices (endpoint TEXT PRIMARY KEY, code TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'web',
     sub TEXT NOT NULL, created INTEGER NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS devices_code ON devices (code)`,
  `CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT NOT NULL)`,
];
let ready = null;
const setup = db => (ready ??= db.batch(SCHEMA.map(s => db.prepare(s))).catch(err => { ready = null; throw err; }));

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
  if (acct.pending_session) {
    const s = await stripe(env, "GET", "checkout/sessions/" + acct.pending_session);
    if (s.status === "complete" && s.payment_status !== "unpaid") {
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
  return acct;
}

const active = (env, acct) => !paying(env) || acct.paid_until > now();

function publicAccount(env, acct, devices) {
  return { code: acct.code, active: active(env, acct), free: !paying(env), paid_until: acct.paid_until || null,
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
      acct = { code: newCode(), prefs: JSON.stringify(CLEAN_PREFS(body.prefs || {})), paid_until: 0, created: now() };
      await db.prepare("INSERT INTO accounts (code, prefs, paid_until, created) VALUES (?, ?, 0, ?)").bind(acct.code, acct.prefs, acct.created).run();
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
    return json(req, publicAccount(env, acct, await devicesOf(acct.code)));
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

  if (path === "" || path === "/") return new Response("Hostile Environment Jobs alerts. The app is at " + SITE + "/app/", { headers: cors(req) });
  return json(req, { error: "Not found" }, 404);
}

export default {
  async fetch(req, env) {
    try { return await handle(req, env); }
    catch (err) { return json(req, { error: String(err.message || err) }, 500); }
  },
};
