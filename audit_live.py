#!/usr/bin/env python3
"""Live spot-audit of known SellerDeck product blocks against the source site."""
import sys
import requests
from bs4 import BeautifulSoup

from scraper import extract_records, product_heading, listing_block, text_of

CASES = [
    (
        "Popular Comics",
        "https://www.whentitansclash.co.uk/acatalog/When_Titans_Clash__Popular_Comics_550.html",
        [
            ("Popular Comics 96", "FR/G 1.5", "in_stock"),
            ("Popular Comics 49", "VG 4.0", "in_stock"),
        ],
    ),
    (
        "Action Comics",
        "https://www.whentitansclash.co.uk/acatalog/When_Titans_Clash__Action_Comics_2.html",
        [
            ("Action Comics 303", "FR/G 1.5", "in_stock"),
            ("Action Comics 296", "FN+ 6.5", "in_stock"),
            ("Action Comics 297", "VG/FN 5.0", "in_stock"),
        ],
    ),
    (
        "Hulk",
        "https://www.whentitansclash.co.uk/acatalog/When_Titans_Clash__Hulk_122.html",
        [
            ("Incredible Hulk 200", "VG 4.0", "sold"),
        ],
    ),
]

session = requests.Session()
session.headers.update({"User-Agent": "WhenTitansClashStockMonitor/3.0 (live parser audit)"})
failures = []
for category, url, expected in CASES:
    response = session.get(url, timeout=35)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "windows-1252"
    soup = BeautifulSoup(response.text, "html.parser")
    headings = [h for h in soup.find_all(["h2", "h3", "h4"]) if product_heading(h)]
    records = list(extract_records(soup, url).values())
    print(f"{category}: {len(headings)} grade-bearing headings; {len(records)} extracted records")
    if len(headings) != len(records):
        record_titles = {r["title"] for r in records}
        missing = [h for h in headings if text_of(h) not in record_titles]
        for heading in missing:
            parent_text = text_of(heading.parent)[:500]
            block = listing_block(heading)
            print(f"  UNMATCHED {text_of(heading)!r}; block_found={bool(block)}; parent={parent_text!r}")
        failures.append(f"{category}: extracted {len(records)} of {len(headings)} grade-bearing product headings")
    for title_prefix, grade, status in expected:
        matches = [r for r in records if r["title"].startswith(title_prefix) and r["grade"] == grade]
        if not matches:
            failures.append(f"{category}: missing {title_prefix} with grade {grade}")
            continue
        if not any(r["status"] == status for r in matches):
            failures.append(f"{category}: {title_prefix} expected status {status}, got {[r['status'] for r in matches]}")
        if title_prefix == "Popular Comics 49":
            item = next((r for r in matches if r["status"] == status), matches[0])
            if not item.get("notes", "").startswith("Mar 1940."):
                failures.append(f"{category}: Popular Comics 49 seller Notes not extracted: {item.get('notes', '')!r}")
            if item.get("published_date") != "Mar 1940":
                failures.append(f"{category}: Popular Comics 49 publication date expected 'Mar 1940', got {item.get('published_date')!r}")
            print(f"  Notes/date audit · {item.get('notes', '')[:90]!r} · {item.get('published_date')!r}")
        print(f"  OK {title_prefix} · {grade} · {status}")

if failures:
    print("LIVE AUDIT FAILED:")
    for failure in failures:
        print(" -", failure)
    sys.exit(1)
print("LIVE AUDIT PASSED: sampled live product blocks agree with expected grade and stock state.")
