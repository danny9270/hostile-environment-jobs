# Hostile Environment Jobs

Static jobs and training board for EOD, IEDD, search, mine action, security, hostile environment medics and support roles. Hosted on GitHub Pages.

## Adding listings

- Jobs go in `jobs.json`, courses in `courses.json`. Each entry needs a unique `id`.
- Dates use `YYYY-MM-DD`. Jobs with a past `closing` date and courses with a past `start` date are hidden automatically. Use `"Rolling"` for open-ended ones.
- Entries with `"sample": true` are placeholders and show a sample notice; delete them before launch.

## Settings

At the top of the script in `index.html`: `CONTACT` (email for the job and course forms), `FACEBOOK_GROUP` (group link) and the job/course categories.

The forms use FormSubmit: the first submission sends a confirmation email to `CONTACT` that must be clicked once.
