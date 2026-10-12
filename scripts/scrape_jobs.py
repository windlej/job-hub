#!/usr/bin/env python3
"""Aggregate IT jobs from ATS platforms that expose public JSON APIs.

Supported source types (see data/sources.json):
  - greenhouse:     GET  https://boards-api.greenhouse.io/v1/boards/{token}/jobs
  - smartrecruiters:GET  https://api.smartrecruiters.com/v1/companies/{token}/postings
  - workday:        POST https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

No third-party dependencies; uses only the standard library so it runs
locally and in GitHub Actions without extra installs.
"""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "data" / "sources.json"
OUT_PATH = ROOT / "jobs.json"

USER_AGENT = "Mozilla/5.0 (compatible; JobHubBot/1.0; +https://github.com/windlej/job-hub)"
HTTP_TIMEOUT = 30
WORKDAY_PAGE_SIZE = 20
WORKDAY_MAX_JOBS = 200

# Unambiguous technology keywords: a title match is treated as an IT job.
STRONG_IT_KEYWORDS = [
    "software", "developer", "programmer", "full stack", "front end", "back end",
    "network", "sysadmin", "sys admin", "help desk", "helpdesk", "security",
    "cybersecurity", "infosec", "database", "cloud", "devops", "infrastructure",
    "desktop", "windows", "linux", "unix", "aws", "azure", "kubernetes", "docker",
    "site reliability", "sre", "data engineer", "data scientist", "machine learning",
    "qa", "tester", "firmware", "embedded", "information technology", "it support",
    "systems administrator", "systems engineer", "systems analyst", "web developer",
    "sql", "python", "java", "javascript",
]

# Context-dependent keywords: count only when no non-IT discipline is present.
WEAK_IT_KEYWORDS = [
    "it", "engineer", "administrator", "analyst", "support", "technical",
    "architect", "technician", "admin",
]

# Non-IT disciplines/domains that would otherwise match a weak keyword.
NON_IT_KEYWORDS = [
    "mechanical", "electrical", "chemical", "civil", "structural", "welding",
    "manufacturing", "industrial", "process", "quality", "hardware", "emc",
    "compliance", "environmental", "ehs", "geotechnical", "facilities",
    "maintenance", "plumber", "electrician", "hvac", "machinist", "buyer",
    "accountant", "accounting", "financial", "fiscal", "payroll", "nurse",
    "clinical", "medical", "veterinary", "patient", "custodian", "food",
    "chef", "cook", "driver", "warehouse", "sales", "marketing", "retail",
    "recruiting", "human resources", "supply chain", "logistics",
    "customer service", "detention", "classroom", "technician",
    "administrative", "postdoctoral", "production", "calibration",
]

# Keep jobs in the Spokane region or remote. Matched case-insensitively.
REGION_KEYWORDS = [
    "spokane", "pullman", "liberty lake", "airway heights", "cheney", "medical lake",
    "coeur", "post falls", "idaho", "washington", "remote",
]
REGION_PATTERNS = [re.compile(r"\bwa\b", re.IGNORECASE)]


def fetch_json(url, payload=None):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def _compile(keys):
    patterns = []
    for k in keys:
        escaped = re.escape(k)
        if len(k) <= 3:
            # short tokens (it, qa, sre, aws) must stand alone
            patterns.append(re.compile(rf"\b{escaped}\b", re.IGNORECASE))
        else:
            patterns.append(re.compile(rf"\b{escaped}", re.IGNORECASE))
    return patterns


STRONG_IT_PATTERNS = _compile(STRONG_IT_KEYWORDS)
WEAK_IT_PATTERNS = _compile(WEAK_IT_KEYWORDS)
NON_IT_PATTERNS = _compile(NON_IT_KEYWORDS)


def is_it_job(title):
    if not title:
        return False
    if any(p.search(title) for p in STRONG_IT_PATTERNS):
        return True
    if any(p.search(title) for p in NON_IT_PATTERNS):
        return False
    return any(p.search(title) for p in WEAK_IT_PATTERNS)


def is_relevant_location(location):
    if not location:
        return True
    loc = location.lower()
    if any(k in loc for k in REGION_KEYWORDS):
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
