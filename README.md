# Resale Tracker

A lightweight tracking database for items purchased for resale.

## What this product is
Resale Tracker is a simple web app that replaces a spreadsheet for tracking:
- What you bought
- What you paid
- Where/when you listed it
- If/when it sold and for how much

## Confirmed decisions (from you)
- **Each item is a separate line**, even if multiple copies are bought.
- **Statuses**: Unlisted and Listed, plus Sold.
- **Sale price already includes fees**, so no extra fee fields needed for v1.
- **Marketplaces**: eBay, Vinted, Adverts.ie.
- **Cross-listing**: Yes, one item can be listed on multiple marketplaces at once.
- **Listing URLs are required** for each marketplace.
- **Single-user web app** (mobile-friendly).
- **No photos** for v1.
- **Track purchase source** (where the item was bought).
- **Track where the item sold** (marketplace sold on).

## Proposed V1 scope (based on your answers)
- Item list with core fields.
- Multiple marketplace listings per item, each with a URL.
- Mark item as Sold and record the marketplace where it sold.
- Simple profit calculation (sale price minus purchase price).
- Filters by status and marketplace.
- Basic reports (profit & loss, ROI, marketplace breakdown).
- Export to CSV.
- CSV import.

## V1 data model (draft)
- Item
  - Name
  - SKU (optional)
  - Description (optional)
  - Purchase price
  - Purchase date
  - Purchase source (where bought)
  - Status (Unlisted / Listed / Sold)
  - Listed date (optional)
  - Sale price (optional)
  - Sale date (optional)
  - Sold marketplace (optional)
  - Notes (optional)

- Listing (per marketplace)
  - Marketplace (eBay / Vinted / Adverts.ie)
  - Listing URL
  - Listing date (optional)

## V2 ideas (from your wishlist)
- One-click “open all listings” to remove an item from other marketplaces after it sells.

## Getting started
### Local setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app runs at `http://localhost:5000`.

### Windows setup (PowerShell)
1) Install Python 3.11+ from https://www.python.org/downloads/windows/
   - During install, check **“Add python.exe to PATH”**.
2) Close and reopen PowerShell.
3) In the project folder, run:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

### Windows troubleshooting
- **`Python was not found`**: Python isn’t installed or not on PATH. Re-run the installer and ensure
  “Add python.exe to PATH” is checked, then reopen PowerShell.
- **`Activate.ps1` not recognized**: the `.venv` folder wasn’t created. Run `python -m venv .venv`
  again in the project folder, then retry activation.
- **`pip` not recognized**: use `python -m pip install -r requirements.txt` instead.

### Environment variables
- `RESALE_DB_PATH` (optional): path to the SQLite database file.
- `RESALE_SECRET_KEY` (optional): Flask secret key.

## CSV import format
Required columns:
- `name`
- `purchase_price`
- `purchase_date` (DD/MM/YYYY)
- `purchase_source`

Optional columns:
- `sku`
- `description`
- `status` (Unlisted / Listed / Sold)
- `listed_date` (DD/MM/YYYY)
- `ebay_url`
- `vinted_url`
- `adverts_url`
- `sale_price`
- `sale_date` (DD/MM/YYYY)
- `sold_marketplace`
- `notes`

## Deployment (online)
This is ready for a small online deployment (e.g., Render, Fly.io, or Railway).
When you pick a host, I’ll add the exact deployment config.

## Split box wizard
Use **Boxes** -> **Split new box** to create a box/lot purchase and split the total cost evenly across items.

Wizard supports two modes:
- Create a batch of new items and auto-allocate cost.
- Select existing unassigned items and re-allocate cost evenly.

Each lot keeps a running summary of total cost, allocated cost, and remaining cost.

## Purchase source cleanup
To normalize existing `purchase_source` values (e.g., casing or naming variants), run:

```bash
python scripts/normalize_purchase_sources.py
```

Review the dry run output, then apply updates with:

```bash
python scripts/normalize_purchase_sources.py --apply
```

## AI insights for a reselling business
The app already captures enough data to generate high-value insights with simple AI/analytics workflows.

### What you can learn from current data
- **Best sourcing locations**: compare profit and ROI by `purchase_source` to find where your best stock comes from.
- **Marketplace performance**: track sell-through, average sale price, and margin by `sold_marketplace`.
- **Stock risk**: flag old listed inventory (high days-in-stock) likely to tie up cash.
- **Pricing opportunities**: detect items/SKUs consistently selling far above cost and items that underperform.
- **Seasonality**: use month-based trends in `sale_date` to predict stronger sourcing or listing windows.
- **Box/lot quality**: compare lot-level allocated cost vs realized sale value to see which box purchases are strongest.
- **Cross-listing health**: use listing status scans to detect dead links and stale listings that reduce conversion.

### Useful metrics to add to your weekly review
- Gross margin % = `(sale_price - purchase_price) / sale_price`
- Cash conversion cycle proxy = `sale_date - purchase_date`
- Sell-through rate = `sold items / total items listed`
- Median days to sale by source and marketplace
- Unsold value at risk = sum of `purchase_price` for old listed items

### AI use-cases that fit this app well
- **Automated weekly summary**: LLM-generated narrative over your KPIs (what changed, what to do next).
- **Anomaly detection**: identify unusual drops in conversion or margin by source/marketplace.
- **Profit forecasting**: predict expected monthly profit from listed inventory and historical sell-through.
- **Next-best-action suggestions**: recommend markdown, re-list, or cross-list actions per item.
- **Listing text optimization** (if titles/descriptions are expanded later): suggest edits to improve sell-through.

### Minimum data additions (optional, high impact)
If you want more precise AI recommendations later, consider adding:
- Item category/brand
- Condition grade
- Shipping cost and packaging cost
- Time-to-list timestamp
- Watchers/views (if available from marketplaces)
