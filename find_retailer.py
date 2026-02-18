import json
import re
import urllib.parse
from playwright.sync_api import sync_playwright

HEADLESS = False
MAX_RESULTS = 15


# -------------------------
# PRICE EXTRACTION LOGIC
# -------------------------
def extract_price_from_page(page):

    # 1️⃣ JSON-LD structured data
    scripts = page.query_selector_all("script[type='application/ld+json']")
    for script in scripts:
        try:
            data = json.loads(script.inner_text())

            if isinstance(data, dict):
                if "offers" in data:
                    offers = data["offers"]
                    if isinstance(offers, dict) and "price" in offers:
                        return str(offers["price"])
        except:
            continue

    # 2️⃣ Meta property price
    meta = page.query_selector("meta[property='product:price:amount']")
    if meta:
        return meta.get_attribute("content")

    # 3️⃣ Common ecommerce selectors
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
            text = el.inner_text().strip()
            match = re.search(r"\d+[.,]?\d{0,2}", text)
            if match:
                return match.group()

    # 4️⃣ Fallback: find all dollar values and return the highest
    try:
        body = page.inner_text("body")
        matches = re.findall(r"\$?\s?(\d+[.,]?\d{0,2})", body)

        prices = []
        for m in matches:
            try:
                prices.append(float(m.replace(",", "")))
            except:
                continue

        if prices:
            return str(max(prices))
    except:
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            locale="en-AU",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
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
            try:
                print(f"[LOG] Visiting: {url}")

                product_page = context.new_page()
                product_page.goto(url, timeout=30000, wait_until="domcontentloaded")


                product_page.wait_for_load_state("domcontentloaded")

                price = extract_price_from_page(product_page)

                if price:
                    print(f"[LOG] ✅ Price found: {price}")
                    retailer_data.append({
                        "url": url,
                        "price": price
                    })
                else:
                    print("[LOG] ❌ Price not found")

                product_page.close()

            except Exception as e:
                print(f"[ERROR] Failed to process {url}: {e}")

        browser.close()

    return retailer_data


# -------------------------
# MAIN
# -------------------------
if __name__ == "__main__":
    title = input("Enter product title: ").strip()

    results = search_duckduckgo(title)

    with open("retailer_results.json", "w") as f:
        json.dump(results, f, indent=4)

    print("\n✅ Results saved to retailer_results.json")
