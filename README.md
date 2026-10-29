# Hostile Environment Jobs

Static jobs and training board for EOD, IEDD, search, mine action, security, hostile environment medics and support roles. Hosted on GitHub Pages.

## Adding listings

- Jobs go in `jobs.json`, courses in `courses.json`. Each entry needs a unique `id`.
- Dates use `YYYY-MM-DD`. Jobs with a past `closing` date and courses with a past `start` date are hidden automatically. Use `"Rolling"` for open-ended ones.
- Entries with `"sample": true` are placeholders and show a sample notice; delete them before launch.

## Settings

At the top of the script in `index.html`: `CONTACT` (email for the job and course forms), `FACEBOOK_GROUP` (group link) and the job/course categories.

The forms use FormSubmit: the first submission sends a confirmation email to `CONTACT` that must be clicked once.

## Admin page

`/admin/` is a private dashboard for adding, editing and closing jobs and courses. Signing in needs a GitHub fine-grained token for this repository with Contents set to Read and write; the page itself holds no secrets, and nothing can be read or changed without that token. Each save commits `jobs.json` or `courses.json` straight to `main`.

Visitor stats on the dashboard come from GoatCounter: the site code (`hostileenvironmentjobs`) is built in; paste an API key (with "Read statistics") under Settings on the admin page. It is kept only in that browser.

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
