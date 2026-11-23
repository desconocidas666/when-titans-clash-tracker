#!/usr/bin/env python3
"""Monitor individual comic records on the When Titans Clash SellerDeck catalogue."""
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

BASE = "https://www.whentitansclash.co.uk"
SHOP = BASE + "/acatalog/shop.html"
OUT = "docs/data.json"
SCHEMA_VERSION = 2
HEADERS = {"User-Agent": "WhenTitansClashStockMonitor/2.0 (polite periodic catalogue monitor)"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

PRICE_RE = re.compile(r"£\s*[\d,]+(?:\.\d{1,2})?")
# SellerDeck product headings on this site include a grade in brackets.
GRADE_RE = re.compile(
    r"(?<![A-Z0-9])(?P<label>FR/G|G/VG|VG/FN|FN/VF|VF/NM|VG\\+|VG-|FN\\+|FN-|VF\\+|VF-|G\\+|G-|FR|P|G|VG|FN|VF|NM|M)"
    r"\\s*\\(?\\s*(?P<score>\\d{1,2}(?:\\.\\d)?)\\s*\\)?(?![\\d.])",
    re.I,
)
SKIP = ("basket", "cart", "checkout", "search", "contact", "privacy", "terms",
        "postage", "grading", "about", "login", "register")


def clean_url(href, base):
    url = urldefrag(urljoin(base, href))[0]
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.netloc.lower() not in ("www.whentitansclash.co.uk", "whentitansclash.co.uk"):
        return None
    path = parsed.path.lower()
    if not path.endswith((".html", ".htm")):
        return None
    if any(word in path for word in SKIP):
        return None
    return url


def is_catalogue_page(url):
    path = urlparse(url).path
    # The shop index, publisher landing pages, series pages and their pagination.
    # Other links (including images, basket and general site pages) are not crawl targets.
    return (path.endswith("/shop.html")
            or "/acatalog/when_titans_clash__" in path.lower()
            or "/acatalog/____strong____" in path.lower())


def fetch(url):
    try:
        response = SESSION.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "windows-1252"
        return BeautifulSoup(response.text, "html.parser")
    except Exception as exc:
        print("Fetch failed:", url, str(exc)[:180])
        return None


def text_of(node):
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def product_heading(node):
    value = text_of(node)
    return bool(value and GRADE_RE.search(value) and len(value) < 180)


def listing_block(heading):
    """Find the smallest surrounding block containing exactly this product.

    Condition is deliberately optional: SellerDeck sometimes omits that label
    even though the heading and price identify a valid comic product block.
    """
    node = heading
    for _ in range(7):
        parent = getattr(node, "parent", None)
        if parent is None:
            break
        node = parent
        headings = [h for h in node.find_all(["h2", "h3", "h4"]) if product_heading(h)]
        block_text = text_of(node)
        if (len(headings) == 1 and headings[0] is heading
                and PRICE_RE.search(block_text)):
            return block_text
    return ""


def extract_records(soup, page_url):
    found = {}
    # This SellerDeck catalogue displays each comic as a product block within its
    # series page; the individual stock item is not a separate HTML detail page.
    for heading in soup.find_all(["h2", "h3", "h4"]):
        title = text_of(heading)
        if not product_heading(heading):
            continue
        block = listing_block(heading)
        if not block:
            continue
        price_match = PRICE_RE.search(block)
        grade_match = GRADE_RE.search(title)
        if not price_match or not grade_match:
            continue

        # Keep the product-specific text only; never use a page-wide/sidebar block.
        condition_match = re.search(r"\bCondition\s*:\s*(.*)", block, re.I)
        condition = condition_match.group(1).strip() if condition_match else ""
        if not condition:
            continue
        notes_match = re.search(r"\bNotes\s*:\s*(.*?)(?=\bCondition\s*:|$)", block, re.I)
        notes = notes_match.group(1).strip() if notes_match else ""
        price = price_match.group(0).replace(" ", "")
        grade = f"{grade_match.group('label').upper()} {grade_match.group('score')}"
        sold = bool(re.search(r"(?<![A-Z])SOLD(?![A-Z])", block, re.I))
        stable = "|".join((page_url, title.casefold()))
        item_id = hashlib.sha1(stable.encode("utf-8")).hexdigest()
        found[item_id] = {
            "id": item_id,
            "title": title,
            "price": price,
            "grade": grade,
            "condition": condition[:900],
            "status": "sold" if sold else "in_stock",
            "notes": notes[:500],
            "url": page_url,
            "category_page": page_url,
        }
    return found


def main():
    os.makedirs("docs", exist_ok=True)
    try:
        with open(OUT, encoding="utf-8") as handle:
            old = json.load(handle)
    except Exception:
        old = {}

    # The previous scraper stored category/navigation pages as stock records.
    # Discard that contaminated baseline once, then establish a clean baseline.
    clean_baseline = old.get("schema_version") == SCHEMA_VERSION
    previous = old.get("items", {}) if clean_baseline else {}
    initialized = bool(old.get("initialized")) if clean_baseline else False
    events = old.get("events", []) if clean_baseline else []

    queue = [SHOP]
    seen_pages = set()
    records = {}
    max_pages = int(os.getenv("MAX_PAGES", "5000"))

    while queue and len(seen_pages) < max_pages:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        soup = fetch(url)
        if soup is None:
            continue

        records.update(extract_records(soup, url))

        # Use the site's own publisher/series navigation as a discovery map,
        # but only enqueue known catalogue and pagination URL patterns.
        for anchor in soup.find_all("a", href=True):
            target = clean_url(anchor["href"], url)
            if (target and is_catalogue_page(target)
                    and target not in seen_pages and target not in queue):
                queue.append(target)

        if len(seen_pages) % 25 == 0:
            print("Pages scanned:", len(seen_pages), "individual listings:", len(records))
        time.sleep(0.4)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    current = {}
    for key, item in records.items():
        prior = previous.get(key)
        item["first_seen"] = prior.get("first_seen", now) if prior else now
        item["last_seen"] = now
        if prior:
            if prior.get("price") != item.get("price"):
                events.append({"type": "price_change", "date": now, "title": item["title"],
                               "url": item["url"], "from": prior.get("price", ""),
                               "to": item.get("price", "")})
            if prior.get("status") in ("removed", "sold") and item["status"] == "in_stock":
                events.append({"type": "restocked", "date": now, "title": item["title"],
                               "url": item["url"]})
            if prior.get("status") == "in_stock" and item["status"] == "sold":
                events.append({"type": "sold", "date": now, "title": item["title"],
                               "url": item["url"], "price": item.get("price", "")})
        elif initialized:
            item["new_detected"] = now
            events.append({"type": "new_listing", "date": now, "title": item["title"],
                           "url": item["url"], "price": item.get("price", "")})
        current[key] = item

    for key, prior in previous.items():
        if key not in current:
            prior["missing_scans"] = int(prior.get("missing_scans", 0)) + 1
            if prior["missing_scans"] >= 2 and prior.get("status") != "removed":
                prior["status"] = "removed"
                events.append({"type": "removed", "date": now, "title": prior.get("title", ""),
                               "url": prior.get("url", "")})
            current[key] = prior

    events = events[-3000:]
    data = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now,
        "initialized": True,
        "baseline_reset": not clean_baseline,
        "pages_scanned": len(seen_pages),
        "scan_limit": max_pages,
        "items": current,
        "events": events,
        "note": ("Clean baseline established by the corrected catalogue parser. "
                 "The previous category-page false positives were discarded. "
                 "Dates are when the monitor detected a listing, not the seller's upload date. "
                 "Each comic is listed within its series/category page on the source site. "
                 "Explicit SOLD labels are retained as sold; missing condition text does not discard a product."),
    }
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    print("Scan complete:", len(seen_pages), "catalogue pages,", len(records),
          "individual comic records;", "clean baseline" if not clean_baseline else "change detection active")


if __name__ == "__main__":
    main()
