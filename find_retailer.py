import json
import re
import csv
import os
import time
import random
import urllib.parse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

HEADLESS = False
MAX_RESULTS = 15
DELAY_BETWEEN_PAGES = (2, 5)  # random seconds between retailer page visits


# -------------------------
# PRICE HELPERS
# -------------------------
def is_access_denied(page):
    try:
        title = page.title().lower()
        if any(x in title for x in ["access denied", "403", "blocked", "captcha", "just a moment"]):
            return True
        for selector in ["h1", "h2"]:
            for el in page.query_selector_all(selector):
                if any(x in el.inner_text().lower() for x in ["access denied", "403", "blocked"]):
                    return True
    except Exception:
        pass
    return False


def parse_price(price_str):
    """Return float if price is in a realistic product range, else None."""
    try:
        value = float(str(price_str).replace(",", "").replace("$", "").strip())
        if 0.5 <= value <= 50000:
            return value
    except (ValueError, AttributeError):
        pass
    return None


# -------------------------
# PRICE EXTRACTION LOGIC
# -------------------------
def extract_price_from_page(page):

    # 0️⃣ Skip blocked / access-denied pages
    if is_access_denied(page):
        print("[LOG] Access denied / blocked page — skipping price extraction")
        return None

    # 1️⃣ JSON-LD structured data
    scripts = page.query_selector_all("script[type='application/ld+json']")
    for script in scripts:
        try:
            data = json.loads(script.inner_text())
            if isinstance(data, dict) and "offers" in data:
                offers = data["offers"]
                if isinstance(offers, dict) and "price" in offers:
                    price = str(offers["price"])
                    if parse_price(price) is not None:
                        return price
        except Exception:
            continue

    # 2️⃣ Meta property price
    meta = page.query_selector("meta[property='product:price:amount']")
    if meta:
        price = meta.get_attribute("content")
        if parse_price(price) is not None:
            return price

    # 3️⃣ Common ecommerce selectors — exclude <sup> nodes (cent superscripts)
    selectors = [
        "[itemprop='price']",
        ".price",
        ".product-price",
        "[class*='price']",
        "[data-testid*='price']",
        ".offer-price"
    ]

    for sel in selectors:
        elements = page.query_selector_all(sel)
        for el in elements:
            try:
                # Recursively collect text, skipping <sup> elements
                text = el.evaluate("""el => {
                    function getText(node) {
                        if (node.nodeType === 3) return node.textContent;
                        if (node.nodeName === 'SUP') return '';
                        return Array.from(node.childNodes).map(getText).join('');
                    }
                    return getText(el);
                }""").strip()
            except Exception:
                text = el.inner_text().strip()

            match = re.search(r"\d+[.,]?\d{0,2}", text)
            if match:
                price = match.group()
                if parse_price(price) is not None:
                    return price

    # 4️⃣ Fallback: find $-prefixed values in body text, return highest in range
    try:
        body = page.inner_text("body")
        matches = re.findall(r"\$\s*(\d+[.,]?\d{0,2})", body)

        prices = []
        for m in matches:
            value = parse_price(m)
            if value is not None:
                prices.append(value)

        if prices:
            return str(max(prices))
    except Exception:
        pass

    return None



# -------------------------
# DUCKDUCKGO SEARCH LOGIC
# -------------------------
def search_duckduckgo(title):
    query = f'{title} -ebay -amazon -catch -kogan'
    encoded_query = urllib.parse.quote(query)

    # Force AU region
    search_url = f"https://duckduckgo.com/html/?q={encoded_query}&kl=au-en"

    retailer_data = []

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            locale="en-AU",
            timezone_id="Australia/Sydney",
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        print("[LOG] Opening DuckDuckGo (AU region)...")
        page.goto(search_url, timeout=60000)

        page.wait_for_selector("a.result__a", timeout=15000)

        links = page.query_selector_all("a.result__a")
        print(f"[LOG] Found {len(links)} search results")

        clean_results = []

        # -------------------------
        # CLEAN & DECODE LINKS
        # -------------------------
        for link in links:
            href = link.get_attribute("href")
            if not href:
                continue

            # Fix protocol-relative URLs
            if href.startswith("//"):
                href = "https:" + href

            # Extract real URL from DuckDuckGo redirect
            if "uddg=" in href:
                parsed = urllib.parse.urlparse(href)
                query_params = urllib.parse.parse_qs(parsed.query)

                if "uddg" in query_params:
                    real_url = query_params["uddg"][0]
                    real_url = urllib.parse.unquote(real_url)
                else:
                    continue
            else:
                real_url = href

            # Filter AU retailer domains
            if (
                ".com.au" in real_url
                and all(x not in real_url.lower()
                        for x in ["ebay", "amazon", "catch", "kogan"])
            ):
                clean_results.append(real_url)

            if len(clean_results) >= MAX_RESULTS:
                break

        print(f"[LOG] Filtered {len(clean_results)} AU retailer links")

        # -------------------------
        # VISIT RETAILER PAGES
        # -------------------------
        for url in clean_results:
            product_page = context.new_page()
            try:
                delay = random.uniform(*DELAY_BETWEEN_PAGES)
                time.sleep(delay)
                print(f"[LOG] Visiting: {url}")
                product_page.goto(url, timeout=30000, wait_until="domcontentloaded")

                price = extract_price_from_page(product_page)

                if price:
                    print(f"[LOG] ✅ Price found: {price}")
                else:
                    print("[LOG] ❌ Price not found")
                retailer_data.append({
                    "url": url,
                    "price": price if price else "price not found"
                })

            except PlaywrightTimeoutError:
                print(f"[WARN] Page timed out, skipping: {url}")
            except Exception as e:
                print(f"[ERROR] Failed to process {url}: {e}")
            finally:
                product_page.close()

        browser.close()

    return retailer_data


# -------------------------
# MAIN
# -------------------------
if __name__ == "__main__":
    csv_file = input("Enter path to store results CSV: ").strip()

    # Derive store name from filename e.g. "mystore_results.csv" → "mystore"
    base = os.path.basename(csv_file)
    store_name = base.replace("_results.csv", "").replace(".csv", "")

    output_folder = store_name
    os.makedirs(output_folder, exist_ok=True)
    print(f"[INFO] Saving results to folder: {output_folder}/")

    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        items = list(reader)

    print(f"[INFO] Loaded {len(items)} items from {csv_file}")

    for item in items:
        item_id = item["itemID"]
        title = item["title"]
        print(f"\n[INFO] Processing item {item_id}: {title}")

        results = search_duckduckgo(title)

        out_path = os.path.join(output_folder, f"{item_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "itemID": item_id,
                "title": title,
                "price": item["price"],
                "quantitysold": item["quantitysold"],
                "retailers": results
            }, f, indent=4)

        print(f"[INFO] Saved {len(results)} retailers → {out_path}")
