// Builds www/, the web part of the store apps, from the live /app/ page (app/index.html, made by scripts/build_pages.py).
// The page is the same one the website serves, with three changes so it works inside the app:
//   - links and data files point at https://hostileenvironmentjobs.com instead of "/", because the app's own pages
//     are served from the phone (capacitor://localhost on iPhone, https://localhost on Android);
//   - the website's menu, footer links and visitor counter are taken out, so it reads as an app, not a website;
//   - native.js (src/native.js, bundled here) is loaded first. It gives the page store payments, phone push and
//     sharing through window.HEJNative, which scripts/app.html uses whenever it's there.
// Run: npm run build (or npm run sync to copy it into the iPhone and Android projects as well).
import { build } from "esbuild";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

const SITE = "https://hostileenvironmentjobs.com";
const here = path.dirname(url.fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const out = path.join(here, "www");

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });

function appPage(src, brand) {
let html = fs.readFileSync(path.join(root, src), "utf8");
const must = (re, what) => { if (!re.test(html)) throw new Error(`build-www: couldn't find ${what} in ${src}`); };

// The site's menu and footer: keep the brand, drop the website links.
must(/<nav[\s>][\s\S]*?<\/nav>/, "the site menu");
html = html.replace(/<nav[\s>][\s\S]*?<\/nav>/, "");
must(/<footer>[\s\S]*?<\/footer>/, "the footer");
html = html.replace(/<footer>[\s\S]*?<\/footer>/, `<footer><div class="wrap">
  <span>&copy; ${new Date().getFullYear()} Hostile Environment Jobs</span>
  <a href="${SITE}/#jobs">All jobs on the website</a>
  <a href="${SITE}/privacy/">Privacy</a>
  <a href="${SITE}/terms/">Terms</a>
  <a href="mailto:contact@hostileenvironmentjobs.com">Contact us</a>
</div></footer>`);
html = html.replace(/<script data-goatcounter[^>]*><\/script>\n?/, "");
html = html.replace(/<link rel="manifest"[^>]*>\n?/, "");

// Root-relative links, images and fetches go to the website.
html = html.replace(/(href|src)="\/(?!\/)/g, `$1="${SITE}/`);
html = html.replace(/fetch\("\//g, `fetch("${SITE}/`);
html = html.replace(/href="\/jobs\/\$\{/g, `href="${SITE}/jobs/\${`);
html = html.replace(/<a href="https:\/\/hostileenvironmentjobs\.com\/app\/" aria-current="page">/g, '<a href="#top" aria-current="page">');
// The brand's link goes to the top of the app rather than the website.
html = html.replace(/<a class="brand" href="[^"]*"/, `<a class="brand" href="${brand}"`);

// Native helpers load before the page's own script, and the page knows it's inside the app from the first paint.
must(/<\/head>/, "</head>");
html = html.replace("<html ", '<html data-native="1" ');
html = html.replace("</head>", `<style>
html[data-native] header.top { padding-top: 0; }
html[data-native] footer a { margin-right: 14px; }
</style>
<script src="native.js"></script>
</head>`);

return html;
}

const html = appPage("app/index.html", "#top");
fs.writeFileSync(path.join(out, "index.html"), html);
// The deployment guide is carried in the app too, so it opens with no signal (native.js opens it for /deploy/ links).
fs.writeFileSync(path.join(out, "deploy.html"), appPage("deploy/index.html", "index.html#kit").replace('<main class="wrap">', '<main class="wrap"><p style="margin:16px 0 0"><a class="btn" href="index.html#kit">&lsaquo; Back to the app</a></p>'));
for (const f of ["icon-192.png", "favicon-96x96.png", "favicon.svg"]) fs.copyFileSync(path.join(root, f), path.join(out, f));
// Copies of the data the app reads, so the kit list, jobs and deployment guide still open with no signal.
for (const f of ["kit.json", "jobs.json", "deploy.json"]) fs.copyFileSync(path.join(root, f), path.join(out, f));

await build({ entryPoints: [path.join(here, "src", "native.js")], bundle: true, minify: true, format: "iife", target: ["safari15", "chrome100"],
              outfile: path.join(out, "native.js"), define: {
                REVENUECAT_IOS_KEY: JSON.stringify(process.env.REVENUECAT_IOS_KEY || ""),
                REVENUECAT_ANDROID_KEY: JSON.stringify(process.env.REVENUECAT_ANDROID_KEY || ""),
              } });

const left = [...(html + fs.readFileSync(path.join(out, "deploy.html"), "utf8")).matchAll(/(?:href|src)="\/(?!\/)[^"]*"/g)].map(m => m[0]);
if (left.length) throw new Error("build-www: links still pointing at the phone: " + left.slice(0, 5).join(", "));
console.log(`www/ built: index.html (${(html.length / 1024).toFixed(0)} KB) and native.js`);
