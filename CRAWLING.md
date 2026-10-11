# Crawling Notes

Many ATS (Paylocity, Workday, iCIMS, UltiPro, SmartRecruiters, GovernmentJobs) render client-side; simple static scraping won't capture all listings. Options:
- RSS feeds where available (rare)
- Use publicly accessible API endpoints if discoverable
- For GovernmentJobs, can scrape HTML search pages; for others often need headless browser (not free in GitHub Actions without workarounds)

Start by adding parsers for easier sites. Run locally first.
