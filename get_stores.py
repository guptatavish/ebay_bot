from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import time
import csv

# -------- CONFIG --------
BASE_URL = "https://www.ebay.com.au"
DAYS_LIMIT = 14
MIN_SALES = 3
MAX_ITEMS = 10          # stop after finding this many items with >= MIN_SALES changes
HEADLESS = False
DELAY_BETWEEN_ITEMS = 1.5
# ------------------------

def parse_sold_date(text):
    cleaned = text.replace("Sold", "").strip()

    try:
        # AU format: 18 Feb 2026
        return datetime.strptime(cleaned, "%d %b %Y")
    except ValueError:
        try:
            # US fallback (if ever used)
            return datetime.strptime(cleaned, "%b %d, %Y")
        except ValueError:
            print(f"[WARN] Could not parse sold date: {cleaned}")
            return None


def parse_revision_date(date_text):
    return datetime.strptime(date_text.strip(), "%b %d, %Y")


def count_quantity_revisions(context, item_id, cutoff_date):
    revision_url = f"{BASE_URL}/rvh/{item_id}"
    rev_page = context.new_page()

    try:
        print(f"[LOG] Opening revision page: {revision_url}")
        rev_page.goto(revision_url, timeout=60000)

        rev_page.wait_for_selector("table tbody tr", timeout=15000)

        rows = rev_page.query_selector_all("table tbody tr")

        if not rows:
            print(f"[LOG] No revision rows found for {item_id}")
            return 0

        print(f"[LOG] Found {len(rows)} revision rows")

        count = 0

        # REVERSE rows → newest first
        for row in reversed(rows):

            cells = row.query_selector_all("td")
            if len(cells) < 3:
                continue

            date_text = cells[0].inner_text().strip()
            change_type = cells[2].inner_text().strip()

            try:
                revision_date = datetime.strptime(date_text, "%d %b, %Y")
            except:
                continue

            # STOP when older than 14 days
            if revision_date < cutoff_date:
                print(f"[LOG] Reached older date: {revision_date} — stopping")
                break

            if "Quantity" in change_type:
                count += 1
                print(f"[LOG] Quantity change found on {revision_date}")

        return count

    except Exception as e:
        print(f"[ERROR] Revision page error for {item_id}: {e}")
        return 0

    finally:
        rev_page.close()
    


def scrape_store(store_name):
    sales_count = {}
    item_details = {}
    qualified_count = 0

    cutoff_date = datetime.now() - timedelta(days=DAYS_LIMIT)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        page_number = 1
        stop_scraping = False

        while not stop_scraping:
            url = (
                f"{BASE_URL}/sch/i.html"
                f"?_ssn={store_name}"
                f"&LH_Sold=1&LH_Complete=1&_sop=13&_ipg=200&_pgn={page_number}"
            )

            print(f"\nScraping page {page_number}...")
            page.goto(url, timeout=60000)
            page.wait_for_selector("li.s-card", timeout=10000)

            listings = page.query_selector_all("li.s-card")
            if not listings:
                break

            for listing in listings:

                item_id = listing.get_attribute("data-listingid")
                sold_span = listing.query_selector('span[aria-label="Sold item"]')

                if not item_id or not sold_span:
                    continue

                sold_date_text = sold_span.inner_text().strip()
                sold_date = parse_sold_date(sold_date_text)

                if sold_date < cutoff_date:
                    stop_scraping = True
                    break

                title_elem = listing.query_selector("div.s-card__title span")
                price_elem = listing.query_selector("span.s-card__price")

                title = title_elem.inner_text().strip() if title_elem else ""
                price = price_elem.inner_text().strip() if price_elem else ""

                print(f"Checking revisions for {item_id}...")

                quantity_count = count_quantity_revisions(
                    context, item_id, cutoff_date
                )

                sales_count[item_id] = quantity_count
                item_details[item_id] = {
                    "title": title,
                    "price": price,
                }

                if quantity_count >= MIN_SALES:
                    qualified_count += 1
                    print(f"[INFO] Qualified items so far: {qualified_count}/{MAX_ITEMS}")
                    if qualified_count >= MAX_ITEMS:
                        print(f"[INFO] Reached {MAX_ITEMS} qualified items — stopping scrape.")
                        stop_scraping = True
                        break

                time.sleep(DELAY_BETWEEN_ITEMS)

            page_number += 1

        browser.close()

    return sales_count, item_details


def print_results(sales_count, item_details, store_name):
    print("\n==== ALL ITEMS (Quantity Revisions Last 14 Days) ====")
    print(f"{'Item ID':<15} {'QtyChanges':<12} {'Price':<10} Title")
    print("-" * 100)

    for item_id, count in sales_count.items():
        details = item_details.get(item_id, {})
        print(f"{item_id:<15} {count:<12} {details.get('price',''):<10} {details.get('title','')}")

    print("\n==== FILTERED (>= 3 Quantity Changes) ====")
    print(f"{'Item ID':<15} {'QtyChanges':<12} {'Price':<10} Title")
    print("-" * 100)

    filtered = [
        (item_id, count, item_details.get(item_id, {}))
        for item_id, count in sales_count.items()
        if count >= MIN_SALES
    ]

    for item_id, count, details in filtered:
        print(f"{item_id:<15} {count:<12} {details.get('price',''):<10} {details.get('title','')}")

    csv_filename = f"{store_name}_results.csv"
    with open(csv_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["itemID", "quantitysold", "price", "title"])
        for item_id, count, details in filtered:
            writer.writerow([item_id, count, details.get("price", ""), details.get("title", "")])

    print(f"\n[INFO] Saved {len(filtered)} items to {csv_filename}")


if __name__ == "__main__":
    store = input("Enter eBay store name: ").strip()
    sales_count, item_details = scrape_store(store)
    print_results(sales_count, item_details, store)
