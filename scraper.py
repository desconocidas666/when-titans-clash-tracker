#!/usr/bin/env python3
"""Polite catalogue monitor for When Titans Clash. Runs in GitHub Actions."""
import json, os, re, time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
import requests
from bs4 import BeautifulSoup

BASE = "https://www.whentitansclash.co.uk"
SHOP = BASE + "/acatalog/shop.html"
OUT = "docs/data.json"
HEADERS = {"User-Agent": "WhenTitansClashStockMonitor/1.0 (polite periodic catalogue monitor)"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
PRICE_RE = re.compile(r"£\s*[\d,]+(?:\.\d{1,2})?")
GRADE_RE = re.compile(r"\b(?:NM|M|VF|FN|VG|G|F|P)(?:\s*/\s*(?:NM|M|VF|FN|VG|G|F|P))?\s*[+-]?\s*\(?\d(?:\.\d)?\)?", re.I)
SKIP = ("basket", "cart", "checkout", "search", "contact", "privacy", "terms", "postage", "grading", "about")

def clean_url(href, base):
    u = urldefrag(urljoin(base, href))[0]
    p = urlparse(u)
    if p.netloc not in ("www.whentitansclash.co.uk", "whentitansclash.co.uk") or not p.path.lower().endswith((".html", ".htm")):
        return None
    if any(s in u.lower() for s in SKIP): return None
    return u

def fetch(url):
    try:
        r = SESSION.get(url, timeout=25)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "windows-1252"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print("Fetch failed:", url, str(e)[:180])
        return None

def text_of(node):
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()

def extract_records(soup, page_url):
    found = {}
    # Product anchors usually sit inside a table/cell or a compact listing block.
    for a in soup.find_all("a", href=True):
        href = clean_url(a["href"], page_url)
        label = text_of(a)
        if not href or not label or href == page_url or "/acatalog/" not in href: continue
        node = a
        best = ""
        for _ in range(5):
            if not getattr(node, "parent", None): break
            node = node.parent
            t = text_of(node)
            if PRICE_RE.search(t) and (GRADE_RE.search(t) or "Condition:" in t or len(t) > 35):
                best = t
                break
        if not best: continue
        price = PRICE_RE.search(best)
        grade = GRADE_RE.search(best)
        title = label if len(label) > 2 else best[:110]
        # Avoid category-navigation anchors that happen to contain another product's price.
        if len(title) > 180: title = title[:180]
        found[href] = {
            "id": href, "title": title, "price": price.group(0).replace(" ", "") if price else "",
            "grade": grade.group(0) if grade else "",
            "condition": best[:900], "url": href, "category_page": page_url
        }
    # Some SellerDeck templates render each listing as headings rather than linked product cards.
    for h in soup.find_all(["h2", "h3", "h4"]):
        title = text_of(h)
        if not title: continue
        node = h
        block = ""
        for _ in range(4):
            if not getattr(node, "parent", None): break
            node = node.parent
            t = text_of(node)
            if PRICE_RE.search(t) and len(t) < 1600:
                block = t; break
        if not block: continue
        links = [clean_url(a.get("href",""), page_url) for a in node.find_all("a", href=True)]
        links = [u for u in links if u and u != page_url]
        if not links: continue
        href = links[0]
        price = PRICE_RE.search(block); grade = GRADE_RE.search(block)
        found.setdefault(href, {
            "id": href, "title": title, "price": price.group(0).replace(" ", "") if price else "",
            "grade": grade.group(0) if grade else "", "condition": block[:900],
            "url": href, "category_page": page_url
        })
    return found

def main():
    os.makedirs("docs", exist_ok=True)
    try:
        with open(OUT, encoding="utf-8") as f: old = json.load(f)
    except Exception: old = {"initialized": False, "items": {}, "events": []}
    queue = [SHOP]; seen_pages = set(); records = {}
    max_pages = int(os.getenv("MAX_PAGES", "5000"))
    while queue and len(seen_pages) < max_pages:
        url = queue.pop(0)
        if url in seen_pages: continue
        seen_pages.add(url)
        soup = fetch(url)
        if not soup: continue
        records.update(extract_records(soup, url))
        # Discover every category and pagination page reachable from the catalogue index.
        for a in soup.find_all("a", href=True):
            nxt = clean_url(a["href"], url)
            if nxt and nxt not in seen_pages and nxt not in queue:
                # The index is the entry point; only follow catalogue pages and their pagination.
                queue.append(nxt)
        if len(seen_pages) % 20 == 0: print("Pages scanned:", len(seen_pages), "records:", len(records))
        time.sleep(0.35)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    previous = old.get("items", {})
    initialized = bool(old.get("initialized"))
    events = old.get("events", [])
    current = {}
    for key, item in records.items():
        prior = previous.get(key)
        item["first_seen"] = prior.get("first_seen", now) if prior else now
        item["last_seen"] = now
        item["status"] = "in_stock"
        if prior:
            if prior.get("price") != item.get("price"):
                events.append({"type":"price_change","date":now,"title":item["title"],"url":key,"from":prior.get("price",""),"to":item.get("price","")})
            if prior.get("status") == "removed":
                events.append({"type":"restocked","date":now,"title":item["title"],"url":key})
        elif initialized:
            item["new_detected"] = now
            events.append({"type":"new_listing","date":now,"title":item["title"],"url":key,"price":item.get("price","")})
        current[key] = item
    for key, prior in previous.items():
        if key not in current:
            prior["missing_scans"] = int(prior.get("missing_scans", 0)) + 1
            # Require two consecutive missed scans before marking a listing as removed.
            if prior["missing_scans"] >= 2 and prior.get("status") != "removed":
                prior["status"] = "removed"
                events.append({"type":"removed","date":now,"title":prior.get("title",""),"url":key})
            current[key] = prior
    # Bound event history so the JSON and dashboard stay responsive.
    events = events[-3000:]
    data = {"updated_at":now,"initialized":True,"pages_scanned":len(seen_pages),
            "scan_limit":max_pages,"items":current,"events":events,
            "note":"Date shown is when the monitor detected a listing, not the seller's upload date."}
    with open(OUT, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    print("Scan complete:", len(seen_pages), "pages,", len(records), "current listings;",
          "baseline" if not initialized else "change detection active")
if __name__ == "__main__": main()
