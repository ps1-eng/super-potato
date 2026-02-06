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
- `sale_price`
- `sale_date` (DD/MM/YYYY)
- `sold_marketplace`
- `notes`

## Deployment (online)
This is ready for a small online deployment (e.g., Render, Fly.io, or Railway).
When you pick a host, I’ll add the exact deployment config.
