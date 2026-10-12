#!/usr/bin/env python3
"""Aggregate IT jobs from ATS platforms that expose public JSON APIs.

Supported source types (see data/sources.json):
  - greenhouse:     GET  https://boards-api.greenhouse.io/v1/boards/{token}/jobs
  - smartrecruiters:GET  https://api.smartrecruiters.com/v1/companies/{token}/postings
  - workday:        POST https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

Relevance criteria live in data/criteria.json so they can be tuned without
touching code. No third-party dependencies; uses only the standard library so
it runs locally and in GitHub Actions without extra installs.
"""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "data" / "sources.json"
CRITERIA_PATH = ROOT / "data" / "criteria.json"
OUT_PATH = ROOT / "jobs.json"

USER_AGENT = "Mozilla/5.0 (compatible; JobHubBot/1.0; +https://github.com/windlej/job-hub)"
HTTP_TIMEOUT = 30
WORKDAY_PAGE_SIZE = 20
WORKDAY_MAX_JOBS = 200
WORKDAY_ENRICH_DATES = True  # fetch each matched job's detail for a real posted date


def fetch_json(url, payload=None):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def load_criteria():
    return json.loads(CRITERIA_PATH.read_text())


def compile_patterns(keys):
    patterns = []
    for k in keys:
        escaped = re.escape(k)
        if len(k) <= 3:
            # short tokens (it, wa, qa) must stand alone
            patterns.append(re.compile(rf"\b{escaped}\b", re.IGNORECASE))
        else:
            patterns.append(re.compile(rf"\b{escaped}", re.IGNORECASE))
    return patterns


CRITERIA = load_criteria()
INCLUDE_PATTERNS = compile_patterns(CRITERIA["include"])
WEAK_PATTERNS = compile_patterns(CRITERIA["weak"])
EXCLUDE_PATTERNS = compile_patterns(CRITERIA["exclude"])
REGION_WORDS = CRITERIA.get("region", [])
REGION_PATTERNS = compile_patterns(CRITERIA.get("region_word", []))


def is_it_job(title):
    """Include beats nothing; exclude beats include; weak counts when no match above."""
    if not title:
        return False
    if any(p.search(title) for p in EXCLUDE_PATTERNS):
        return False
    if any(p.search(title) for p in INCLUDE_PATTERNS):
        return True
    return any(p.search(title) for p in WEAK_PATTERNS)


def is_relevant_location(location):
    if not location:
        return True
    loc = location.lower()
    if any(k in loc for k in REGION_WORDS):
        return True
    return any(p.search(location) for p in REGION_PATTERNS)


def parse_relative_date(text):
    """Turn Workday's 'Posted 3 Days Ago' style strings into an ISO date."""
    if not text:
        return None
    t = text.lower()
    today = datetime.now(timezone.utc).date()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s*\+?\s*day", t)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\s*\+?\s*month", t)
    if m:
        return (today - timedelta(days=30 * int(m.group(1)))).isoformat()
    return None


def edge_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value


def scrape_greenhouse(source):
    token = source["token"]
    data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    jobs = []
    for item in data.get("jobs", []):
        jobs.append({
            "company": source["name"],
            "title": item.get("title", ""),
            "location": (item.get("location") or {}).get("name", ""),
            "url": item.get("absolute_url", ""),
            "posted": edge_iso(item.get("first_published") or item.get("updated_at")),
        })
    return jobs


def scrape_smartrecruiters(source):
    token = source["token"]
    jobs = []
    offset = 0
    limit = 100
    while True:
        url = (
            f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
            f"?limit={limit}&offset={offset}"
        )
        data = fetch_json(url)
        content = data.get("content", [])
        for item in content:
            loc = item.get("location") or {}
            jobs.append({
                "company": source["name"],
                "title": item.get("name", ""),
                "location": loc.get("fullLocation") or loc.get("city", ""),
                "url": f"https://jobs.smartrecruiters.com/{token}/{item.get('id')}",
                "posted": edge_iso(item.get("releasedDate")),
            })
        total = data.get("totalFound", 0)
        offset += limit
        if not content or offset >= total:
            break
    return jobs


def workday_detail(source, external_path):
    """Fetch an individual Workday posting for its published/start date."""
    tenant, host, site = source["tenant"], source["host"], source["site"]
    url = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{external_path}"
    data = fetch_json(url)
    info = data.get("jobPostingInfo") or {}
    date = info.get("startDate") or parse_relative_date(info.get("postedOn"))
    return edge_iso(date)


def scrape_workday(source):
    tenant, host, site = source["tenant"], source["host"], source["site"]
    endpoint = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    base_url = f"https://{tenant}.{host}.myworkdayjobs.com/{site}"
    jobs = []
    offset = 0
    total = None
    while True:
        payload = {"appliedFacets": {}, "limit": WORKDAY_PAGE_SIZE, "offset": offset, "searchText": ""}
        data = fetch_json(endpoint, payload)
        postings = data.get("jobPostings", [])
        # Workday only reports `total` on the first page.
        if total is None and data.get("total"):
            total = data["total"]
        for item in postings:
            jobs.append({
                "company": source["name"],
                "title": item.get("title", ""),
                "location": item.get("locationsText", ""),
                "url": base_url + item.get("externalPath", ""),
                "external_path": item.get("externalPath", ""),
                "posted": parse_relative_date(item.get("postedOn")),
            })
        offset += WORKDAY_PAGE_SIZE
        if not postings or (total is not None and offset >= total) or offset >= WORKDAY_MAX_JOBS:
            break
    return jobs


SCRAPERS = {
    "greenhouse": scrape_greenhouse,
    "smartrecruiters": scrape_smartrecruiters,
    "workday": scrape_workday,
}


def collect():
    sources = json.loads(SOURCES_PATH.read_text())["sources"]
    all_jobs = []
    for source in sources:
        scraper = SCRAPERS.get(source.get("type"))
        if scraper is None:
            print(f"  ! unknown source type: {source.get('type')} ({source.get('name')})")
            continue
        try:
            found = scraper(source)
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
            print(f"  ! {source['name']}: {exc}")
            continue
        relevant = [
            j for j in found
            if is_it_job(j["title"]) and is_relevant_location(j["location"])
        ]
        if WORKDAY_ENRICH_DATES and source.get("type") == "workday":
            # Workday list endpoints often omit `postedOn`; backfill from detail.
            for job in relevant:
                try:
                    if not job.get("posted"):
                        job["posted"] = workday_detail(source, job["external_path"])
                except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
                    pass
            for job in relevant:
                job.pop("external_path", None)
        print(f"  {source['name']}: {len(found)} postings -> {len(relevant)} IT matches")
        all_jobs.extend(relevant)
    return all_jobs


def dedup(jobs):
    seen = set()
    out = []
    for job in jobs:
        key = (job.get("company"), job.get("title"), job.get("url"))
        if key not in seen:
            seen.add(key)
            out.append(job)
    return out


def main():
    print("Scraping job sources...")
    jobs = dedup(collect())
    jobs.sort(key=lambda j: (j.get("posted") or "", j.get("title") or ""), reverse=True)
    result = {
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "jobs": jobs,
    }
    OUT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {len(jobs)} jobs to {OUT_PATH.name}")


if __name__ == "__main__":
    main()