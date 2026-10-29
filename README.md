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

## Job alerts app

`/app/` is an installable phone app (a web app: Android installs it from Chrome, iPhone from Safari's Share > Add to Home Screen, iOS 16.4 or newer). People pick job types, regions, keywords and course types, pay $6 a year, and get a push notification when a matching job or course goes up. It also lists the open jobs that match.

- **Page:** `scripts/app.html`, wrapped by `scripts/build_pages.py` into `app/index.html` (don't edit that by hand). `ALERTS_API` at the top of its script is the Worker's address; empty shows "being switched on". `sw.js` at the site root shows the notifications.
- **Backend:** `alerts/worker.js`, a Cloudflare Worker (free plan) with a D1 database bound as `DB`. It keeps accounts (each has a code like `HEJ-7KQ2-M9XD-4TWB`, used to sign in on another phone), preferences and phones, and takes payment through Stripe Checkout. Settings are explained at the top of the file. With no Stripe settings it's free for everyone, for testing. Paste the file into the Worker's code editor again after changing it.
- **Sending:** the "Job alerts" Action runs `alerts/send_alerts.py` after each job page build and every 3 hours. It asks the Worker who wants what (signing in with GitHub's own token, no secret), sends each new listing to the matching phones, and tells the Worker what it sent. The Worker lives at https://hej-alerts.danieldobb.workers.dev (Dobbo's Cloudflare account); the repository variable `ALERTS_API` overrides it. The first run only records the listings already up.
- **Lost code:** in the Cloudflare dashboard, D1 > hej-alerts > Console: `SELECT code, paid_until FROM accounts WHERE email = 'their@email'`.
- **Give someone free alerts:** after they've tapped "Get job alerts" once, run `UPDATE accounts SET paid_until = strftime('%s','2027-12-31') WHERE code = 'HEJ-...'` in the same console.
