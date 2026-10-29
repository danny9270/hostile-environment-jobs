# Hostile Environment Jobs

Static jobs and training board for EOD, IEDD, search, mine action, security, hostile environment medics and support roles. Hosted on GitHub Pages.

## Adding listings

- Jobs go in `jobs.json`, courses in `courses.json`. Each entry needs a unique `id`.
- Dates use `YYYY-MM-DD`. Jobs with a past `closing` date and courses with a past `start` date are hidden automatically. Use `"Rolling"` for open-ended ones.
- Entries with `"sample": true` are placeholders and show a sample notice; delete them before launch.

## Course reviews

- Approved reviews go in `reviews.json`. Each has `id`, `provider`, `course`, `rating` (1 to 5), `text`, and optionally `headline`, `name` (blank shows "Anonymous"), `background`, `attended` (`YYYY-MM`) and `posted`.
- A review attaches to every listing whose provider and title match `provider` and `course` (ignoring case and spacing), so it carries over to later dates of the same course. Reviews for a course that isn't listed are kept and show again when it is.
- Nothing goes up automatically. The "Review a course" form emails the review, with a `review_code` line, to `CONTACT`; paste that code into Reviews, Add review on `/admin/` to publish it.

## Settings

At the top of the script in `index.html`: `CONTACT` (email for the job and course forms), `FACEBOOK_GROUP` (group link) and the job/course categories.

The forms use FormSubmit: the first submission sends a confirmation email to `CONTACT` that must be clicked once.

## Admin page

`/admin/` is a private dashboard for adding, editing and closing jobs and courses. Signing in needs a GitHub fine-grained token for this repository with Contents set to Read and write; the page itself holds no secrets, and nothing can be read or changed without that token. Each save commits `jobs.json` or `courses.json` straight to `main`.

Visitor stats on the dashboard come from GoatCounter: the site code (`hostileenvironmentjobs`) is built in; paste an API key (with "Read statistics") under Settings on the admin page. It is kept only in that browser.

## Job pages for Google

`scripts/build_pages.py` builds a page for each open job at `/jobs/<id>/` (with Google for Jobs data), a `/jobs/` list, `404.html` and `sitemap.xml`. The "Build job pages" GitHub Action runs it whenever `jobs.json` changes and every morning, so closed jobs drop off. Don't edit those generated files by hand.

## Pay guide

`/pay/` shows indicative day rates and salaries from `pay.json`, community pay reports, and the stated pay on open jobs (read live from `jobs.json`). The page body lives in `scripts/pay.html`; `scripts/build_pages.py` wraps it in the site header and footer, so don't edit `pay/index.html` by hand.

- `ranges`: each has `role`, `category`, `region`, `where`, `low` and/or `high`, `currency`, `per` (`day`, `month`, `year` or `hour`) and `basis` (`estimate`, `advert` or `published`, with `source` and `source_url` for the last two). Update `updated` when you review them.
- `reports`: anonymous reports arrive by email (FormSubmit, subject "Pay report"). Nothing is published until it's added here. Before adding one, drop anything identifying and round the pay. Fields: `role`, `category`, `region`, `country`, `employer_type`, `amount`, `currency`, `per`, `year`, and optional `rotation`, `experience` and `extras`.
