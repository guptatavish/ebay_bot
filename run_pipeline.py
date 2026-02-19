import csv
import json
import os

from get_stores import scrape_store, MIN_SALES
from find_retailer import search_duckduckgo


def run_pipeline(store_name):
    # ── Step 1: Scrape store ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  STEP 1: Scraping sold listings for store: {store_name}")
    print(f"{'='*60}\n")

    sales_count, item_details = scrape_store(store_name)

    # ── Step 2: Filter & save CSV ─────────────────────────────────────────────
    filtered = [
        (item_id, count, item_details.get(item_id, {}))
        for item_id, count in sales_count.items()
        if count >= MIN_SALES
    ]

    csv_filename = f"{store_name}_results.csv"
    with open(csv_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["itemID", "quantitysold", "price", "title"])
        for item_id, count, details in filtered:
            writer.writerow([item_id, count, details.get("price", ""), details.get("title", "")])

    print(f"\n[INFO] {len(filtered)} items with >= {MIN_SALES} quantity changes saved to {csv_filename}")

    if not filtered:
        print("[INFO] No items passed the filter — nothing to search. Exiting.")
        return

    # ── Step 3: Find retailers for each item ──────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  STEP 2: Finding retailers for {len(filtered)} items")
    print(f"{'='*60}\n")

    output_folder = store_name
    os.makedirs(output_folder, exist_ok=True)
    print(f"[INFO] JSON files will be saved to: {output_folder}/")

    for item_id, count, details in filtered:
        title = details.get("title", "")
        price = details.get("price", "")

        print(f"\n[INFO] Processing item {item_id}: {title}")

        retailers = search_duckduckgo(title)

        out_path = os.path.join(output_folder, f"{item_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "itemID": item_id,
                "title": title,
                "ebay_price": price,
                "quantitysold": count,
                "retailers": retailers
            }, f, indent=4)

        print(f"[INFO] Saved {len(retailers)} retailers → {out_path}")

    print(f"\n{'='*60}")
    print(f"  DONE — results saved to {output_folder}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    store = input("Enter eBay store name: ").strip()
    run_pipeline(store)
