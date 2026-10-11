#!/usr/bin/env python3
import json
from datetime import datetime, timezone

IT_KEYWORDS = [
    'it', 'information technology', 'developer', 'software', 'engineer', 'network',
    'systems', 'sysadmin', 'administrator', 'support', 'help desk', 'helpdesk',
    'security', 'cybersecurity', 'analyst', 'database', 'cloud', 'devops',
    'infrastructure', 'desktop', 'windows', 'linux', 'aws', 'azure', 'site reliability',
    'sre', 'data engineer', 'qa', 'tester', 'technical', 'tech support', 'engineer i', 'engineer ii', 'engineer iii'
]

def is_it_job(title):
    if not title:
        return False
    t = title.lower()
    return any(k in t for k in IT_KEYWORDS)

def dedup(jobs):
    seen = set()
    out = []
    for j in jobs:
        key = (j.get('company'), j.get('title'), j.get('url'))
        if key not in seen:
            seen.add(key)
            out.append(j)
    return out

def main():
    out_path = 'jobs.json'
    jobs = []
    # Static curated IT openings if known (none scraped automatically for JS-heavy sites)
    # Just structure; real scraping would need site-specific parsers
    result = {
        'lastUpdated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'jobs': dedup(jobs)
    }
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=2)

if __name__ == '__main__':
    main()
