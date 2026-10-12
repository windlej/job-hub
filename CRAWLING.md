# Crawling Notes

Jobs are aggregated by `scripts/scrape_jobs.py` (stdlib only, no dependencies) from
sources listed in `data/sources.json`. The GitHub Action runs it weekdays and commits
`jobs.json`, which `jobs.js` renders on `dashboard.html`.

## Supported source types (public JSON APIs)

| Type | Endpoint |
|------|----------|
| `greenhouse` | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs` |
| `smartrecruiters` | `https://api.smartrecruiters.com/v1/companies/{token}/postings` |
| `workday` | `POST https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` |

Add a company by appending an entry to `data/sources.json` - no code changes needed.

## Not yet supported

These render client-side or block bots, so they need HTML parsing or a headless
browser (not free in GitHub Actions without workarounds):

- Paylocity (URM, Numerica), UltiPro/UKG (Avista, Washington Trust Bank)
- iCIMS (TierPoint, Global CU), NEOGOV/GovernmentJobs (OSOS, WSDOT)
- Paycom (Gesa), PeopleAdmin (Gonzaga), custom sites (NoaNet, Providence, MultiCare)
- Workday tenants that need extra setup: D.A. Davidson, Banner Bank (return HTTP 422)

## Relevance filtering

Titles must match a strong IT keyword (`software`, `network`, `firmware`, ...), or a
weaker one (`engineer`, `analyst`, `support`) with no non-IT discipline present.
Locations are kept when they are in the Spokane region or remote. Tune the keyword
lists at the top of `scripts/scrape_jobs.py`.

Run locally with `python3 scripts/scrape_jobs.py`.
