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
| `neogov` | `GET https://www.governmentjobs.com/careers/{tenant}/home/loadJobsOnMaps` |
| `icims` | `GET https://{portal}.icims.com/jobs/search?ss=1&in_iframe=1&pr={page}` |
| `ultipro` | `POST https://{host}/{tenant}/JobBoard/{board}/JobBoardView/LoadSearchResults` |
| `paylocity` | `GET https://recruiting.paylocity.com/recruiting/jobs/All/{token}` |

Notes:
- `neogov` needs the `X-Requested-With: XMLHttpRequest` header (no cookie needed)
  and one `department` value per source to narrow to an agency (e.g. WSDOT, OSOS).
  One request returns the full tenant job list; posting dates arrive as `MM/DD/YY`.
- `icims` search results are server-rendered HTML paginated by zero-indexed `pr`.
  List cards omit the posted date, so `posted` is `null` for iCIMS.
- `ultipro` uses `host` + `tenant` + `board` (the GUID in the careers URL);
  locations are built from each address city/state.
- `paylocity` reads the complete board out of `window.pageData` embedded in the
  HTML - one GET per board, no key or pagination.

Add a company by appending an entry to `data/sources.json` - no code changes needed.

## Not yet supported

These render client-side or block bots, so they need HTML parsing or a headless
browser (not free in GitHub Actions without workarounds):

- Paycom (Gesa), PeopleAdmin (Gonzaga), custom sites (NoaNet, Providence, MultiCare)
- Workday tenants that need extra setup: D.A. Davidson, Banner Bank (return HTTP 422)

## Relevance filtering

Criteria live in `data/criteria.json` (no code changes needed to tune):
- `include`: must-match keywords (help desk, desktop, sysadmin, network, security, ...)
- `weak`: context-dependent (support, analyst, administrator) - kept only if no `exclude` term matches
- `exclude`: disciplines to drop (software, mechanical, cloud, financial, security officer, ...)
- `region` / `region_word`: locations to keep (Spokane-area cities, remote, `wa`)

Exclude beats include. Workday posted dates are backfilled from each matched
job's detail endpoint. Run locally with `python3 scripts/scrape_jobs.py`.
