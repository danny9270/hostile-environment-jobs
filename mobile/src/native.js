// What the store apps add to the /app/ page, as window.HEJNative. scripts/app.html checks for it and, when it's there,
// uses the App Store or Google Play for the $6 a year (through RevenueCat) and Firebase for notifications,
// instead of Stripe and web push. On the website none of this loads, so the page works as before.
//
// The RevenueCat keys are the public SDK keys (appl_... and goog_...). They aren't secret: the GitHub Action that builds
// the apps puts them in from the repository variables REVENUECAT_IOS_KEY and REVENUECAT_ANDROID_KEY.
// The plugins are reached by name, so only their native halves are needed (no web copies of Firebase in the app).
import { Capacitor, registerPlugin } from "@capacitor/core";

const Purchases = registerPlugin("Purchases");
const Messaging = registerPlugin("FirebaseMessaging");
const Browser = registerPlugin("Browser");
const Share = registerPlugin("Share");
const Filesystem = registerPlugin("Filesystem");
const App = registerPlugin("App");
const Splash = registerPlugin("SplashScreen");

const SITE = "https://hostileenvironmentjobs.com";
const ENTITLEMENT = "alerts"; // the RevenueCat entitlement that the yearly subscription unlocks
const platform = Capacitor.getPlatform(); // "ios" or "android"
const rcKey = platform === "ios" ? REVENUECAT_IOS_KEY : REVENUECAT_ANDROID_KEY;
let configured = null; // RevenueCat can only be set up once per launch

async function purchases(code) {
  if (!rcKey) throw new Error("In-app purchases aren't set up in this build yet.");
  // Before there's an account the store is opened anonymously (just to show the price); logIn then ties it to the code.
  configured ??= Purchases.configure(code ? { apiKey: rcKey, appUserID: code } : { apiKey: rcKey });
  await configured;
  if (code) {
    const { appUserID } = await Purchases.getAppUserID();
    if (appUserID !== code) await Purchases.logIn({ appUserID: code });
  }
  return Purchases;
}

// Tapped notifications open the job, in the app's own browser sheet.
const openUrl = u => {
  const full = new URL(u || "/app/", SITE).href;
  const here = /deploy\.html$/.test(location.pathname) ? "deploy" : "app";
  if (/\/app\/(#.*)?$/.test(full)) {
    const hash = new URL(full).hash || "#top";
    if (here === "app") location.hash = hash; else location.href = "index.html" + hash;
    return;
  }
  // The deployment guide is bundled with the app, so it opens offline.
  if (/\/deploy\/(#.*)?$/.test(full)) { location.href = "deploy.html" + new URL(full).hash; return; }
  return Browser.open({ url: full, presentationStyle: "popover", toolbarColor: "#111310" });
};

window.HEJNative = {
  platform,
  store: platform === "ios" ? "App Store" : "Google Play",

  // The yearly product as the store shows it, e.g. { price: "$5.99", period: "a year", trial: true }, or null if it isn't set up.
  async product(code) {
    try {
      const p = await purchases(code);
      const { current } = await p.getOfferings();
      const pkg = current?.annual || current?.availablePackages?.[0];
      // trial is true when the store has a free introductory period set up for this product (the free first month).
      const intro = pkg?.product?.introPrice;
      return pkg ? { price: pkg.product.priceString, period: "a year", trial: Boolean(intro && Number(intro.price) === 0) } : null;
    } catch { return null; }
  },

  // Buys the yearly subscription for this account code. Resolves true when it went through, false if the user backed out.
  async buy(code) {
    const p = await purchases(code);
    const { current } = await p.getOfferings();
    const pkg = current?.annual || current?.availablePackages?.[0];
    if (!pkg) throw new Error(`The subscription isn't available from the ${this.store} yet. Try again later.`);
    try {
      const { customerInfo } = await p.purchasePackage({ aPackage: pkg });
      return Boolean(customerInfo.entitlements.active[ENTITLEMENT]);
    } catch (err) {
      if (err?.userCancelled || err?.code === "1" || /cancel/i.test(err?.message || "")) return false;
      throw new Error(err?.message || "The purchase didn't go through.");
    }
  },

  // Restore purchases: moves a subscription bought on this Apple or Google account onto this code.
  async restore(code) {
    const p = await purchases(code);
    const { customerInfo } = await p.restorePurchases();
    return Boolean(customerInfo.entitlements.active[ENTITLEMENT]);
  },

  manageUrl: platform === "ios" ? "https://apps.apple.com/account/subscriptions" : "https://play.google.com/store/account/subscriptions",

  // Asks to show notifications and returns this phone's Firebase token for /api/devices, or throws if refused.
  async pushToken() {
    let { receive } = await Messaging.checkPermissions();
    if (receive !== "granted") ({ receive } = await Messaging.requestPermissions());
    if (receive !== "granted") throw new Error("Notifications are off for HE Jobs. Turn them on in your phone's Settings, then try again.");
    const { token } = await Messaging.getToken();
    if (!token) throw new Error("Couldn't get this phone's notification address. Try again in a minute.");
    return token;
  },
  async pushOn() {
    try { return (await Messaging.checkPermissions()).receive === "granted"; } catch { return false; }
  },

  // A file the page would download on the web (rotation CSV, calendar) goes to the share sheet instead.
  async save(name, type, text) {
    const { uri } = await Filesystem.writeFile({ path: name, data: text, directory: "CACHE", encoding: "utf8" });
    await Share.share({ title: name, files: [uri], dialogTitle: name });
  },
  async share(opts) { return Share.share(opts); },
  open: openUrl,
};

// Links to the website open in the in-app browser, not inside the app's own page.
document.addEventListener("click", e => {
  const a = e.target.closest?.("a[href]");
  if (!a) return;
  const href = a.getAttribute("href");
  if (/^(mailto:|tel:)/.test(href)) return;
  if (/^https?:/.test(href)) { e.preventDefault(); openUrl(href); }
}, true);

if (platform === "android") Messaging.createChannel({ id: "job_alerts", name: "Job alerts", description: "New jobs and courses that match your alerts", importance: 4 }).catch(() => {});
Messaging.addListener("notificationActionPerformed", e => openUrl(e?.notification?.data?.url));
App.addListener("appUrlOpen", e => { try { const u = new URL(e.url); if (u.pathname.startsWith("/jobs/")) openUrl(u.href); } catch {} });
addEventListener("DOMContentLoaded", () => setTimeout(() => Splash.hide().catch(() => {}), 150));
