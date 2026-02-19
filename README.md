# eBay Store Analyser

Scrapes an eBay AU store's sold listings, identifies hot items (by quantity revisions), then finds and prices them across Australian retailers.

## How it works

1. **`get_stores.py`** — scrapes a store's sold listings and counts quantity revisions in the last 14 days
2. **`find_retailer.py`** — takes the CSV output and finds AU retailer prices for each item via DuckDuckGo
3. **`run_pipeline.py`** — runs both steps back to back automatically

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Playwright browsers
playwright install 
```

## Run

```bash
python run_pipeline.py
```

You will be prompted:
```
Enter eBay store name:
```

**Example — test with ozplaza.living:**
```
Enter eBay store name: ozplaza.living
```

## Output

| File | Description |
|------|-------------|
| `<store>_results.csv` | All items with ≥ 3 quantity changes (itemID, quantitysold, price, title) |
| `<store>/<item_id>.json` | Retailer prices found for each item |

**Example output structure:**
```
ozplaza.living_results.csv
ozplaza.living/
  372287501609.json
  352541460390.json
  ...
```

## Config

Edit the constants at the top of each script to adjust behaviour:

| Variable | File | Default | Description |
|----------|------|---------|-------------|
| `DAYS_LIMIT` | `get_stores.py` | `14` | How many days back to look |
| `MIN_SALES` | `get_stores.py` | `3` | Minimum quantity changes to include |
| `MAX_RESULTS` | `find_retailer.py` | `15` | Max retailer links to check per item |
| `HEADLESS` | both | `False` | Run browser headlessly |
