#!/usr/bin/env python3
"""Aggregate IT jobs from ATS platforms that expose public JSON APIs.

Supported source types (see data/sources.json):
  - greenhouse:     GET  https://boards-api.greenhouse.io/v1/boards/{token}/jobs
  - smartrecruiters:GET  https://api.smartrecruiters.com/v1/companies/{token}/postings
  - workday:        POST https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
  - neogov:         GET  https://www.governmentjobs.com/careers/{tenant}/home/loadJobsOnMaps
  - icims:          GET  https://{portal}.icims.com/jobs/search?ss=1&in_iframe=1&pr={page}
  - ultipro:        POST https://{host}/{tenant}/JobBoard/{board}/JobBoardView/LoadSearchResults
  - paylocity:      GET  https://recruiting.paylocity.com/recruiting/jobs/All/{token}

Relevance criteria live in data/criteria.json so they can be tuned without
touching code. No third-party dependencies; uses only the standard library so
it runs locally and in GitHub Actions without extra installs.
"""
import html
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
UKG_PAGE_SIZE = 100
UKG_MAX_JOBS = 500
ICIMS_MAX_PAGES = 25


def fetch_json(url, payload=None, extra_headers=None):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def fetch_text(url):
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read().decode("utf-8", "ignore")


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


def parse_us_date(value):
    """NEOGOV returns posting dates as MM/DD/YY."""
    if not value:
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def extract_js_object(text, marker):
    """Pull a balanced {...} JavaScript/JSON object literal out of page HTML."""
    start = text.find(marker)
    if start == -1:
        return {}
    brace = text.find("{", start)
    if brace == -1:
        return {}
    depth = 0
    in_string = False
    escaped = False
    quote = ""
    for i in range(brace, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_string = False
            continue
        if ch in ('"', "'"):
            in_string = True
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[brace:i + 1])
                except ValueError:
                    return {}
    return {}


def strip_tags(value):
    return re.sub(r"<[^>]+>", "", html.unescape(value or "")).strip()


def extract_icims_location(card):
    """iCIMS portals vary; try the list-view field, then the detail fields."""
    m = re.search(r'Job Locations</span>\s*<span[^>]*>\s*(.*?)\s*</span>', card, re.S)
    if m:
        return strip_tags(m.group(1))
    fields = {}
    for dt, dd in re.findall(
        r'<dt class="iCIMS_JobHeaderField">(.*?)</dt>\s*'
        r'<dd class="iCIMS_JobHeaderData">\s*<span[^>]*>(.*?)</span>',
        card, re.S,
    ):
        fields[strip_tags(dt)] = strip_tags(dd)
    city = fields.get("City")
    state = fields.get("Select State") or fields.get("State")
    if city:
        return f"{city}, {state}".strip(", ")
    return fields.get("Location", "")


def ultipro_location(item):
    parts = []
    for loc in item.get("Locations") or []:
        addr = loc.get("Address") or {}
        city = addr.get("City")
        state = (addr.get("State") or {}).get("Code")
        if city:
            parts.append(f"{city}, {state}" if state else city)
        elif loc.get("LocalizedDescription"):
            parts.append(loc["LocalizedDescription"])
    return "; ".join(parts)


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


def scrape_neogov(source):
    """NEOGOV/GovernmentJobs exposes one JSON map/list per agency tenant.

    The endpoint needs the XHR header (a session cookie is not required).
    `department` narrows to a single agency, e.g. WSDOT or OSOS.
    """
    tenant = source["tenant"]
    url = f"https://www.governmentjobs.com/careers/{tenant}/home/loadJobsOnMaps"
    data = fetch_json(url, extra_headers={"X-Requested-With": "XMLHttpRequest"})
    department = source.get("department")
    jobs = []
    for item in data.get("jobList", []):
        if department and item.get("DepartmentName") != department:
            continue
        jobs.append({
            "company": source["name"],
            "title": item.get("Classification", ""),
            "location": item.get("Location", ""),
            "url": (
                f"https://www.governmentjobs.com/jobs/{item.get('ID')}/"
                f"{item.get('JobTitle', '')}"
            ),
            "posted": parse_us_date(item.get("PostingDate")),
        })
    return jobs


def scrape_icims(source):
    """iCIMS search is server-rendered HTML; `pr` is a zero-indexed page."""
    portal = source["portal"]
    jobs = []
    seen = set()
    for pr in range(ICIMS_MAX_PAGES):
        url = f"https://{portal}.icims.com/jobs/search?ss=1&in_iframe=1&pr={pr}"
        page = fetch_text(url)
        cards = re.findall(
            r'<li class="[^"]*iCIMS_JobCardItem[^"]*">(.*?)</li>', page, re.S
        )
        if not cards:
            break
        added = 0
        for card in cards:
            title_match = re.search(r"<h3[^>]*>(.*?)</h3>", card, re.S)
            link_match = re.search(r'href="(https://[^"]+?/job)(?:\?[^"]*)?"', card)
            if not (title_match and link_match):
                continue
            link = link_match.group(1)
            if link in seen:
                continue
            seen.add(link)
            added += 1
            jobs.append({
                "company": source["name"],
                "title": strip_tags(title_match.group(1)),
                "location": extract_icims_location(card),
                "url": link,
                "posted": None,
            })
        if added == 0:
            break
    return jobs


def scrape_ultipro(source):
    """UltiPro/UKG Pro Recruiting public job board search endpoint."""
    host, tenant, board = source["host"], source["tenant"], source["board"]
    endpoint = (
        f"https://{host}/{tenant}/JobBoard/{board}/JobBoardView/LoadSearchResults"
    )
    base_url = f"https://{host}/{tenant}/JobBoard/{board}"
    jobs = []
    offset = 0
    while True:
        payload = {
            "opportunitySearch": {
                "Top": UKG_PAGE_SIZE,
                "Skip": offset,
                "QueryString": "",
                "OrderBy": [
                    {"Value": "postedDateDesc", "PropertyName": "PostedDate", "Ascending": False}
                ],
                "Filters": [],
            }
        }
        data = fetch_json(endpoint, payload)
        opportunities = data.get("opportunities", [])
        for item in opportunities:
            jobs.append({
                "company": source["name"],
                "title": item.get("Title", ""),
                "location": ultipro_location(item),
                "url": f"{base_url}/OpportunityDetail?opportunityId={item.get('Id')}",
                "posted": edge_iso(item.get("PostedDate")),
            })
        total = data.get("totalCount")
        offset += UKG_PAGE_SIZE
        if not opportunities or (total is not None and offset >= total) or offset >= UKG_MAX_JOBS:
            break
    return jobs


def scrape_paylocity(source):
    """Paylocity boards embed the full job list as window.pageData (JSON)."""
    token = source["token"]
    page = fetch_text(f"https://recruiting.paylocity.com/recruiting/jobs/All/{token}")
    data = extract_js_object(page, "window.pageData")
    jobs = []
    for item in data.get("Jobs", []):
        loc = item.get("JobLocation") or {}
        city, state = loc.get("City") or "", loc.get("State") or ""
        name = item.get("LocationName") or ""
        if city and state:
            location = (
                name if city.lower() in name.lower()
                else f"{name} - {city}, {state}".strip(" -")
            )
        else:
            location = name
        jobs.append({
            "company": source["name"],
            "title": item.get("JobTitle", ""),
            "location": location,
            "url": f"https://recruiting.paylocity.com/recruiting/jobs/Details/{item.get('JobId')}",
            "posted": edge_iso(item.get("PublishedDate")),
        })
    return jobs


SCRAPERS = {
    "greenhouse": scrape_greenhouse,
    "smartrecruiters": scrape_smartrecruiters,
    "workday": scrape_workday,
    "neogov": scrape_neogov,
    "icims": scrape_icims,
    "ultipro": scrape_ultipro,
    "paylocity": scrape_paylocity,
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