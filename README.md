# Hostile Environment Jobs

Static jobs and training board for EOD, IEDD, search, mine action, security, hostile environment medics and support roles. Hosted on GitHub Pages.

## Adding listings

- Jobs go in `jobs.json`, courses in `courses.json`. Each entry needs a unique `id`.
- Dates use `YYYY-MM-DD`. Jobs with a past `closing` date and courses with a past `start` date are hidden automatically. Use `"Rolling"` for open-ended ones.
- Entries with `"sample": true` are placeholders and show a sample notice; delete them before launch.

## Course reviews

- Approved reviews go in `reviews.json`. Each has `id`, `provider`, `course`, `rating` (1 to 5), `text`, and optionally `headline`, `name` (blank shows "Anonymous"), `background`, `attended` (`YYYY-MM`) and `posted`.
- A review attaches to every listing whose provider and title match `provider` and `course` (ignoring case and spacing), so it carries over to later dates of the same course. Reviews for a course that isn't listed are kept and show again when it is.
- Nothing goes up automatically. The "Review a course" form sends the review to the job alerts Worker (`alerts/worker.js`, `POST /api/reviews`), which keeps it in its D1 database. It shows under Reviews, Waiting for approval on `/admin/`: Publish adds it to `reviews.json`, Reject deletes it.

## Company reviews

- `/companies/` lets people who've worked for an employer review it: overall stars, optional scores for paid on time, rotations kept, safety/kit/medical and management, would-recommend, what's good and what could be better. It's free and always anonymous: only the role, region, current or former, and years (if given) are shown.
- The page body lives in `scripts/companies.html`; `scripts/build_pages.py` wraps it into `companies/index.html` (don't edit that by hand). It reads `employer-reviews.json`, `jobs.json` and `employers.json` in the browser, groups reviews by company name (ignoring case, "Ltd", "The", brackets and so on, plus any `aliases` in `employers.json`) and lists companies with open jobs and no reviews yet. Job pages and employer profiles link to it, and the job view on the home page shows the employer's score.
- The form posts to the same Worker route as course reviews (`POST /api/reviews` with `kind: "employer"`), so they wait in the same list under Reviews on `/admin/`. Publish adds them to `employer-reviews.json`; the reviewer's email is deleted from the Worker once a review is published or rejected.
- Fields in `employer-reviews.json`: `id`, `employer`, `rating`, and optionally `pay`, `rotation`, `safety`, `management` (1 to 5, 0 = not given), `recommend` (`yes`/`no`), `headline`, `pros`, `cons`, `role`, `region`, `status` (`former`/`current`), `from`, `to`, `posted`, and a company's right of reply in `reply` and `reply_date`.
- Moderation: the Reviews tab on `/admin/` has a checklist. In short, publish first-hand experience and opinion, good or bad; take out names of people, accusations of crimes stated as fact, and anything operationally sensitive; reject fakes; never hide genuine negative reviews or let advertisers remove them. On a complaint, take the review down while checking, offer the company a reply, and never reveal who wrote it. It's a plain guide, not legal advice.

## Settings

At the top of the script in `index.html`: `CONTACT` (email for the job and course forms), `FACEBOOK_GROUP` (group link) and the job/course categories.

The forms use FormSubmit: the first submission sends a confirmation email to `CONTACT` that must be clicked once.

## Admin page

`/admin/` is a private dashboard for adding, editing and closing jobs and courses. Signing in needs a GitHub fine-grained token for this repository with Contents set to Read and write; the page itself holds no secrets, and nothing can be read or changed without that token. Each save commits `jobs.json` or `courses.json` straight to `main`.

Visitor stats on the dashboard come from GoatCounter: the site code (`hostileenvironmentjobs`) is built in; paste an API key (with "Read statistics") under Settings on the admin page. It is kept only in that browser. To make the stats show in every browser without pasting it each time, add the key to the alerts Worker as the secret `GOATCOUNTER_KEY`; the admin page then gets the stats from the Worker (owner only) whenever its own box is empty.

## Job pages for Google

`scripts/build_pages.py` builds a page for each open job at `/jobs/<id>/` (with Google for Jobs data), a `/jobs/` list, `404.html` and `sitemap.xml`. The "Build job pages" GitHub Action runs it whenever `jobs.json` changes and every morning, so closed jobs drop off. Don't edit those generated files by hand.

## Featured jobs and employer profiles (paid)

- **Featured job:** add `"featured_until": "YYYY-MM-DD"` to a job in `jobs.json` (or set "Featured until" in the admin page). Until that date it's pinned to the top of the list with a Featured badge; after it, it goes back to a normal listing on its own.
- **Featured employer:** add an entry to `employers.json`. While its `featured_until` date hasn't passed, the employer gets a profile page at `/employers/<id>/` and all their jobs are featured. Jobs are matched by `employer` name (or any of `aliases`). Fields: `id`, `name`, `featured_until`, and optionally `tagline`, `about` (blank line between paragraphs), `based`, `works_in`, `sectors` (list), `website`, `careers_url`, `logo` (e.g. `/img/logos/name.png`), `aliases` (list).
- **Prices and payment:** the plans on `/advertise/` live in `PLANS` at the top of `scripts/employers.py`. Paste a Stripe Payment Link into a plan's `payment_link` to show a "Pay and book" button; left empty, the button goes to the enquiry form instead.

Example `employers.json` entry:

```json
[{"id": "acme-demining", "name": "Acme Demining", "featured_until": "2027-01-31", "tagline": "Humanitarian mine action across Africa",
  "website": "https://example.com", "careers_url": "https://example.com/careers", "sectors": ["EOD", "Survey & Clearance"]}]
```

## Pay guide

`/pay/` shows indicative day rates and salaries from `pay.json`, community pay reports, and the stated pay on open jobs (read live from `jobs.json`). The page body lives in `scripts/pay.html`; `scripts/build_pages.py` wraps it in the site header and footer, so don't edit `pay/index.html` by hand.

- `ranges`: each has `role`, `category`, `region`, `where`, `low` and/or `high`, `currency`, `per` (`day`, `month`, `year` or `hour`) and `basis` (`estimate`, `advert` or `published`, with `source` and `source_url` for the last two). Update `updated` when you review them.
- `reports`: anonymous reports arrive by email (FormSubmit, subject "Pay report"). Nothing is published until it's added here. Before adding one, drop anything identifying and round the pay. Fields: `role`, `category`, `region`, `country`, `employer_type`, `amount`, `currency`, `per`, `year`, and optional `rotation`, `experience` and `extras`.

## Service leaver hub

`/leavers/` covers UK resettlement funding (ELC, IRTC, SLC, GRT), which courses usually count for ELCAS, what each military trade fits on the circuit, a first contract checklist (ticks kept in the visitor's browser only) and who can help. The page body lives in `scripts/leavers.html`; `scripts/build_pages.py` wraps it in the site header and footer, so don't edit `leavers/index.html` by hand. Check the funding figures against the CTP and ELCAS sites now and then.

It also lists the open courses from `courses.json`. Add `"elcas": "1234"` to a course once the provider has given you their ELCAS number, and it shows a green ELCAS tag there.

## Job alerts app

`/app/` is an installable phone app (a web app: Android installs it from Chrome, iPhone from Safari's Share > Add to Home Screen, iOS 16.4 or newer). People pick job types, regions, keywords and course types, pay $6 a year, and get a push notification when a matching job or course goes up. It also lists the open jobs that match.

- **Page:** `scripts/app.html`, wrapped by `scripts/build_pages.py` into `app/index.html` (don't edit that by hand). `ALERTS_API` at the top of its script is the Worker's address; empty shows "being switched on". `sw.js` at the site root shows the notifications.
- **Backend:** `alerts/worker.js`, a Cloudflare Worker (free plan) with a D1 database bound as `DB`. It keeps accounts (each has a code like `HEJ-7KQ2-M9XD-4TWB`, used to sign in on another phone), preferences and phones, and takes payment through Stripe Checkout. Settings are explained at the top of the file. With no Stripe settings it's free for everyone, for testing. Paste the file into the Worker's code editor again after changing it.
- **Sending:** the "Job alerts" Action runs `alerts/send_alerts.py` after each job page build and every 3 hours. It asks the Worker who wants what (signing in with GitHub's own token, no secret), sends each new listing to the matching phones, and tells the Worker what it sent. The Worker lives at https://hej-alerts.danieldobb.workers.dev (Dobbo's Cloudflare account); the repository variable `ALERTS_API` overrides it. The first run only records the listings already up.
- **Lost code:** in the Cloudflare dashboard, D1 > hej-alerts > Console: `SELECT code, paid_until FROM accounts WHERE email = 'their@email'`.
- **Give someone free alerts:** after they've tapped "Get job alerts" once, run `UPDATE accounts SET paid_until = strftime('%s','2027-12-31') WHERE code = 'HEJ-...'` in the same console.
- **Rotation tracker:** free for everyone, no account. People enter days on, days off and the first day of any hitch; it counts down to leave, logs worked, travel, standby and unpaid days with a day rate, and totals pay for the hitch, month, year and UK tax year. It's kept only in that phone's browser (`localStorage` key `hej-rota`), never sent to the Worker. They can download the log as CSV and load it back, and download the next 12 rotations as an `.ics` calendar file.

## Mine Action SOP Builder

`/sop/` (hand-written page, `sop/index.html`, not built by a script) builds an IMAS and IATG referenced SOP set in the browser and exports it to Word (.docx made in the browser) or print/PDF. Work is kept in that browser (`localStorage` key `hej-sop-v1`) and can be saved and opened as a `.json` project file. Nothing is uploaded.

- **Modules:** `MODULES` in the page script. 00 to 03 have `free: true`; 04 to 12, 11.3 clearance methods and Annex A (blank forms, using `fields` and `form` columns) export only with The App. A module or section with `acts` drops out when none of those activities are ticked on the cover page.
- **Guardrail:** structure, management, admin and QC wording only. Never add render safe, demolition, charge placement, firing or IED procedure content; technical sections stay as bracketed placeholders.
- **Unlock:** anyone can edit every module on screen. The full export checks the visitor's App account code against the alerts Worker (`GET /api/account`, the same `hej-code` the `/app/` page keeps), so App subscribers on the same browser are unlocked automatically. It's a soft lock, like the app's kit list. Full exports drop the "Made with" footer line; the disclaimer is on every export.
- **Organisations:** the first 7 get the full set free for year one (enquiries by email to contact@). Logo and shared projects aren't built yet.

## Talent pool

Operators say when they're free and what they do; checked employers who've paid for search find them. Posting jobs and browsing the jobs list stay free.

- **Page:** `scripts/candidates.html`, wrapped by `scripts/build_pages.py` into `candidates/index.html` (don't edit that by hand). "I'm looking for work" makes or edits a profile and uploads a PDF CV; "I'm hiring" (`/candidates/#hiring`) signs an employer up and, once approved with search time, searches.
- **Privacy:** employers see profiles without name, contact details or CV. They send a request (role + message); the operator accepts or declines. Only on accept do the name, email, phone, LinkedIn and CV go to that employer. Profiles leave search 90 days after the operator last confirms they're available and are deleted, with the CV and requests, after 12 months. Operators can hide or delete their profile any time.
- **Backend:** the same alerts Worker and D1 database (tables `candidates`, `cvs`, `recruiters`, `contact_requests`). Operators and employers each sign in with a `HEJ-` code kept on their device.
- **Approving employers:** `/admin/` > Talent pool. Approve (with free days, e.g. 90 for the £149 Featured employer plan), add 30 or 90 days, stop, reject, delete. Remove an operator's profile there on a deletion request.
- **Payment:** £99 for 30 days via Stripe Checkout once the Worker has `STRIPE_SEARCH_PRICE` (a one-off £99 price). Without it, give days by hand from the admin page.
- **Emails:** optional. With a `RESEND_API_KEY` secret on the Worker, operators are emailed about requests, employers about approval and acceptance, and contact@ about new employer sign-ups.
