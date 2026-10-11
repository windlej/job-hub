#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime, timezone

IT_KEYWORDS = [
    'it', 'information technology', 'developer', 'software', 'engineer', 'network',
    'systems', 'sysadmin', 'administrator', 'support', 'help desk', 'helpdesk',
    'security', 'cybersecurity', 'analyst', 'database', 'cloud', 'devops',
    'infrastructure', 'desktop', 'windows', 'linux', 'aws', 'azure', 'site reliability',
    'sre', 'data engineer', 'qa', 'tester', 'technical', 'tech support'
]

def is_it_job(title):
    t = title.lower()
    return any(k in t for k in IT_KEYWORDS)

def main():
    out_path = 'jobs.json'
    jobs = []
    # For now, just write empty/placeholder - real scraping needs per-site parsers
    # Keep existing jobs if file exists? but static list is fine to start
    result = {
        'lastUpdated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'jobs': jobs
    }
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=2)
    print('done')

if __name__ == '__main__':
    main()
