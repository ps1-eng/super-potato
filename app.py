from __future__ import annotations

import csv
import io
import os
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from flask import Flask, Response, flash, redirect, render_template, request, url_for

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("RESALE_DB_PATH", APP_DIR / "data" / "resale.db"))
MARKETPLACES = ["eBay", "Vinted", "Adverts.ie"]
STATUSES = ["Unlisted", "Listed", "Sold"]
DATE_FORMAT = "%d/%m/%Y"
PURCHASE_SOURCE_OPTIONS = [
    "Adverts",
    "Ark - Bray",
    "Auction - Downs",
    "Auction - Lockes",
    "Auction - Matthews",
    "Auction - South Dublin",
    "Auction - Other",
    "Barnardos - Clondalkin",
    "BRC - Belfast",
    "Car Boot - Athy",
    "Car Boot - Ballymun",
    "Car Boot - Bray",
    "Car Boot - Brockagh",
    "Car Boot - Inch",
    "Car Boot - Newtown",
    "Car Boot - Tallaght",
    "Cancer Research - Bray",
    "Cancer Research - Kimmage",
    "Cancer Research - Rathmines",
    "Cancer Research - Swords",
    "Cancer Research - Tallaght",
    "Charity Shop",
    "Enable Ireland - Finglas",
    "Enable Ireland - Kimmage",
    "Enable Ireland - Terenure",
    "Facebook Marketplace",
    "Five Loaves - Bray",
    "Free",
    "Home",
    "Jack and Jill - Arklow",
    "Jack and Jill - Gorey",
    "Jack and Jill - Wicklow",
    "Liberty - Bray",
    "Magpies Nest - Tallaght",
    "Marie Curie - Belfast",
    "NTMK Charity",
    "Oxfam - Belfast",
    "Oxfam - Bray",
    "Oxfam - DL",
    "Oxfam - Rathmines",
    "Octopus Garden - Belfast",
    "Other",
    "Purple House - Bray",
    "Save the Children - Belfast",
    "Sue Ryder - Arklow",
    "Sue Ryder - Blackrock",
    "Sue Ryder - Gorey",
    "Sue Ryder - Kimmage",
    "Sue Ryder - Wicklow",
    "SVP - Arklow",
    "SVP - Ballinteer",
    "SVP - Ballyfermot",
    "SVP - Bray",
    "SVP - Clondalkin",
    "SVP - Crumlin",
    "SVP - Finglas",
    "SVP - Firhouse",
    "SVP - Gorey",
    "SVP - Greystones",
    "SVP - Kells",
    "SVP - Kingscourt",
    "SVP - Navan",
    "SVP - Newtown",
    "SVP - NTMK",
    "SVP - Rathfarnham",
    "SVP - Rathmines",
    "SVP - Tallaght",
    "SVP - Terenure",
    "SVP - Wicklow",
    "Temu",
    "Thrift - Ashford",
    "Thrift - DL",
    "Thrift - Kilcoole",
    "Thrift - Navan",
    "TK Maxx",
    "Vinted",
    "Vision Ireland - Arklow",
    "Vision Ireland - Clondalkin",
    "Vision Ireland - Crumlin",
    "Vision Ireland - DL",
    "Vision Ireland - Finglas",
    "Vision Ireland - Kimmage",
    "Vision Ireland - Rathfarnam",
    "Vision Ireland - Rathmines",
    "Vision Ireland - Terenure",
    "Vision Ireland - Walkinstown",
    "Vision Ireland - Wicklow",
    "Wholesale - Italian Vintage",
    "Wholesale - Vintage",
    "Wholesale - Other",
]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("RESALE_SECRET_KEY", "resale-dev-key")


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def init_db() -> None:
    with get_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sku TEXT,
                description TEXT,
                purchase_price REAL NOT NULL,
                purchase_date TEXT NOT NULL,
                purchase_source TEXT NOT NULL,
                status TEXT NOT NULL,
                listed_date TEXT,
                sale_price REAL,
                sale_date TEXT,
                sold_marketplace TEXT,
                notes TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                marketplace TEXT NOT NULL,
                listing_url TEXT NOT NULL,
                listing_date TEXT,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
            """
        )
        ensure_column(conn, "items", "listed_date", "TEXT")
        conn.executemany(
            "INSERT OR IGNORE INTO purchase_sources (name) VALUES (?)",
            [(source,) for source in PURCHASE_SOURCE_OPTIONS],
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO purchase_sources (name)
            SELECT DISTINCT purchase_source FROM items
            WHERE purchase_source IS NOT NULL AND purchase_source <> ''
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_items_sku ON items (sku)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_items_status ON items (status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_listings_item_id ON listings (item_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_listings_marketplace ON listings (marketplace)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_purchase_sources_active ON purchase_sources (active)
            """
        )


def reconcile_sold_status() -> None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE items
            SET status = 'Sold'
            WHERE sale_price IS NOT NULL
              AND status = 'Listed'
            """
        )


init_db()
reconcile_sold_status()

def parse_decimal(value: str) -> Decimal | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_date(value: str) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None
    return parsed.strftime(DATE_FORMAT)


def format_currency(value: float | None) -> str:
    if value is None:
        return "–"
    return f"€{value:,.2f}"


@app.template_filter("today_input")
def today_input_filter(_: str | None = None) -> str:
    return datetime.now().strftime("%Y-%m-%d")


@app.template_filter("input_date")
def input_date_filter(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, DATE_FORMAT).strftime("%Y-%m-%d")
    except ValueError:
        return value


def normalize_purchase_source(value: str) -> str:
    source = value.strip()
    if not source:
        return source
    lower = " ".join(source.lower().split())
    replacements = {
        "fb": "Facebook Marketplace",
        "facebook": "Facebook Marketplace",
        "facebook m": "Facebook Marketplace",
        "home": "Home",
        "adverts": "Adverts",
        "vinted": "Vinted",
        "tk max": "TK Maxx",
        "tk maxx": "TK Maxx",
        "temu": "Temu",
        "charity shop": "Charity Shop",
        "free": "Free",
        "dump": "Dump",
    }
    if lower in replacements:
        return replacements[lower]

    def format_location(prefix: str, location: str) -> str:
        return f"{prefix} - {location.title()}"

    if lower.startswith("svp "):
        return format_location("SVP", lower.replace("svp", "", 1).strip())
    if lower.startswith("vision ireland "):
        return format_location("Vision Ireland", lower.replace("vision ireland", "", 1).strip())
    if lower.startswith("vision "):
        return format_location("Vision Ireland", lower.replace("vision", "", 1).strip())
    if lower.startswith("sue ryder "):
        return format_location("Sue Ryder", lower.replace("sue ryder", "", 1).strip())
    if lower.startswith("cancer research "):
        return format_location("Cancer Research", lower.replace("cancer research", "", 1).strip())
    if lower.startswith("cancer "):
        return format_location("Cancer Research", lower.replace("cancer", "", 1).strip())
    if "car boot" in lower or "carboot" in lower:
        location = lower.replace("car boot", "").replace("carboot", "").strip()
        return format_location("Car Boot", location or "Other")
    if "auction" in lower:
        if "lockes" in lower:
            return "Auction - Lockes"
        if "matthews" in lower:
            return "Auction - Matthews"
        if "south dublin" in lower:
            return "Auction - South Dublin"
        if "downs" in lower:
            return "Auction - Downs"
        return "Auction - Other"
    if "wholesale" in lower:
        if "italian vintage" in lower:
            return "Wholesale - Italian Vintage"
        if "vintage" in lower:
            return "Wholesale - Vintage"
        return "Wholesale - Other"
    if "thrift" in lower:
        location = lower.replace("thrift", "").strip()
        return format_location("Thrift", location or "Other")
    if lower.startswith("oxfam "):
        return format_location("Oxfam", lower.replace("oxfam", "", 1).strip())
    if lower.startswith("jack and jill "):
        return format_location("Jack and Jill", lower.replace("jack and jill", "", 1).strip())
    if lower.startswith("enable "):
        return format_location("Enable Ireland", lower.replace("enable", "", 1).strip())
    if lower.startswith("barnardos "):
        return format_location("Barnardos", lower.replace("barnardos", "", 1).strip())
    if lower.startswith("ark "):
        return format_location("Ark", lower.replace("ark", "", 1).strip())
    if lower == "ark":
        return "Ark - Bray"
    return source


def ensure_purchase_source(conn: sqlite3.Connection, source: str) -> None:
    if not source:
        return
    conn.execute(
        "INSERT OR IGNORE INTO purchase_sources (name) VALUES (?)",
        (source,),
    )


def fetch_purchase_sources(active_only: bool = True) -> list[str]:
    query = "SELECT name FROM purchase_sources"
    params: list[int] = []
    if active_only:
        query += " WHERE active = ?"
        params.append(1)
    query += " ORDER BY name COLLATE NOCASE"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [row["name"] for row in rows]


def fetch_items(
    status: str | None = None,
    marketplace: str | None = None,
    listing_url: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[sqlite3.Row]:
    query = """
        SELECT items.*, COUNT(listings.id) AS listing_count
        FROM items
        LEFT JOIN listings ON listings.item_id = items.id
    """
    filters = []
    params: list[str] = []
    if status:
        filters.append("items.status = ?")
        params.append(status)
    if marketplace:
        filters.append("listings.marketplace = ?")
        params.append(marketplace)
    if listing_url:
        filters.append("listings.listing_url LIKE ?")
        params.append(f"%{listing_url}%")
    if search:
        filters.append("(items.name LIKE ? OR listings.listing_url LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " GROUP BY items.id ORDER BY items.id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(str(limit))
    if offset is not None:
        query += " OFFSET ?"
        params.append(str(offset))
    with get_db() as conn:
        return conn.execute(query, params).fetchall()


def fetch_item(item_id: int) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()


def fetch_listings(item_id: int) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM listings WHERE item_id = ? ORDER BY id DESC", (item_id,)
        ).fetchall()


def fetch_listing(listing_id: int) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()


def fetch_sku_options() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT sku
            FROM items
            WHERE sku IS NOT NULL AND sku != ''
            ORDER BY sku
            """
        ).fetchall()
    return [row["sku"] for row in rows]




def calculate_summary(items: Iterable[sqlite3.Row]) -> dict[str, float]:
    total_purchase = 0.0
    total_sale = 0.0
    for item in items:
        total_purchase += float(item["purchase_price"])
        if item["sale_price"] is not None:
            total_sale += float(item["sale_price"])
    profit = total_sale - total_purchase
    roi = (profit / total_purchase * 100.0) if total_purchase else 0.0
    return {
        "total_purchase": total_purchase,
        "total_sale": total_sale,
        "profit": profit,
        "roi": roi,
    }


def fetch_summary(
    status: str | None = None,
    marketplace: str | None = None,
    listing_url: str | None = None,
    search: str | None = None,
) -> dict[str, float]:
    query = """
        SELECT
            SUM(items.purchase_price) AS total_purchase,
            SUM(COALESCE(items.sale_price, 0)) AS total_sale
        FROM items
        LEFT JOIN listings ON listings.item_id = items.id
    """
    filters = []
    params: list[str] = []
    if status:
        filters.append("items.status = ?")
        params.append(status)
    if marketplace:
        filters.append("listings.marketplace = ?")
        params.append(marketplace)
    if listing_url:
        filters.append("listings.listing_url LIKE ?")
        params.append(f"%{listing_url}%")
    if search:
        filters.append("(items.name LIKE ? OR listings.listing_url LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if filters:
        query += " WHERE " + " AND ".join(filters)
    with get_db() as conn:
        row = conn.execute(query, params).fetchone()
    total_purchase = float(row["total_purchase"] or 0)
    total_sale = float(row["total_sale"] or 0)
    profit = total_sale - total_purchase
    roi = (profit / total_purchase * 100.0) if total_purchase else 0.0
    return {
        "total_purchase": total_purchase,
        "total_sale": total_sale,
        "profit": profit,
        "roi": roi,
    }


def fetch_item_count(
    status: str | None = None,
    marketplace: str | None = None,
    listing_url: str | None = None,
    search: str | None = None,
) -> int:
    query = """
        SELECT COUNT(DISTINCT items.id) AS total
        FROM items
        LEFT JOIN listings ON listings.item_id = items.id
    """
    filters = []
    params: list[str] = []
    if status:
        filters.append("items.status = ?")
        params.append(status)
    if marketplace:
        filters.append("listings.marketplace = ?")
        params.append(marketplace)
    if listing_url:
        filters.append("listings.listing_url LIKE ?")
        params.append(f"%{listing_url}%")
    if search:
        filters.append("(items.name LIKE ? OR listings.listing_url LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if filters:
        query += " WHERE " + " AND ".join(filters)
    with get_db() as conn:
        row = conn.execute(query, params).fetchone()
    return int(row["total"] or 0)


@app.template_filter("currency")
def currency_filter(value: float | None) -> str:
    return format_currency(value)


@app.route("/")
def index() -> str:
    status = request.args.get("status") or None
    marketplace = request.args.get("marketplace") or None
    listing_url = (request.args.get("listing_url") or "").strip() or None
    search = (request.args.get("search") or "").strip() or None
    page = request.args.get("page", type=int) or 1
    per_page = 25
    offset = (page - 1) * per_page
    items = fetch_items(
        status=status,
        marketplace=marketplace,
        listing_url=listing_url,
        search=search,
        limit=per_page,
        offset=offset,
    )
    summary = fetch_summary(
        status=status,
        marketplace=marketplace,
        listing_url=listing_url,
        search=search,
    )
    total_items = fetch_item_count(
        status=status,
        marketplace=marketplace,
        listing_url=listing_url,
        search=search,
    )
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    sku_options = fetch_sku_options()
    return render_template(
        "index.html",
        items=items,
        summary=summary,
        status=status,
        marketplace=marketplace,
        listing_url=listing_url,
        search=search,
        page=page,
        total_pages=total_pages,
        total_items=total_items,
        sku_options=sku_options,
        purchase_sources=fetch_purchase_sources(),
        marketplaces=MARKETPLACES,
        statuses=STATUSES,
    )


@app.route("/settings")
def settings() -> str:
    return render_template("settings.html", purchase_sources=fetch_purchase_sources())


@app.route("/item/new", methods=["POST"])
def add_item() -> Response:
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    purchase_price = parse_decimal(request.form.get("purchase_price", ""))
    purchase_date = parse_date(request.form.get("purchase_date", ""))
    purchase_source = normalize_purchase_source(request.form.get("purchase_source", "").strip())
    status = request.form.get("status", "Unlisted")
    listed_date = parse_date(request.form.get("listed_date", ""))
    notes = request.form.get("notes", "").strip() or None

    if not name:
        flash("Item name is required.")
        return redirect(url_for("index"))
    if purchase_price is None:
        flash("Purchase price must be a number.")
        return redirect(url_for("index"))
    if purchase_date is None:
        flash(f"Purchase date must be in {DATE_FORMAT} format.")
        return redirect(url_for("index"))
    if not purchase_source:
        flash("Purchase source is required.")
        return redirect(url_for("index"))
    if status not in STATUSES:
        flash("Invalid status.")
        return redirect(url_for("index"))
    if request.form.get("listed_date", "").strip() and listed_date is None:
        flash(f"Listed date must be in {DATE_FORMAT} format.")
        return redirect(url_for("index"))

    with get_db() as conn:
        ensure_purchase_source(conn, purchase_source)
        conn.execute(
            """
            INSERT INTO items
                (name, sku, description, purchase_price, purchase_date, purchase_source, status, listed_date, notes)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                request.form.get("sku", "").strip() or None,
                description,
                float(purchase_price),
                purchase_date,
                purchase_source,
                status,
                listed_date,
                notes,
            ),
        )
    flash("Item added.")
    return redirect(url_for("index"))


@app.route("/purchase-sources", methods=["POST"])
def add_purchase_source() -> Response:
    raw_name = request.form.get("purchase_source_name", "")
    name = normalize_purchase_source(raw_name)
    if not name:
        flash("Purchase source name is required.")
        return redirect(url_for("settings"))

    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM purchase_sources WHERE name = ?",
            (name,),
        ).fetchone()
        if existing:
            flash("Purchase source already exists.")
            return redirect(url_for("settings"))
        conn.execute(
            "INSERT INTO purchase_sources (name) VALUES (?)",
            (name,),
        )
    flash("Purchase source added.")
    return redirect(url_for("settings"))


@app.route("/item/<int:item_id>")
def item_detail(item_id: int) -> str:
    item = fetch_item(item_id)
    if item is None:
        flash("Item not found.")
        return redirect(url_for("index"))
    listings = fetch_listings(item_id)
    return render_template(
        "item_detail.html",
        item=item,
        listings=listings,
        marketplaces=MARKETPLACES,
        statuses=STATUSES,
    )


@app.route("/item/<int:item_id>/listing", methods=["POST"])
def add_listing(item_id: int) -> Response:
    listing_date_raw = request.form.get("listing_date", "")
    listing_date = parse_date(listing_date_raw) if listing_date_raw.strip() else None
    sku = request.form.get("sku", "").strip() or None
    listing_date = listing_date or datetime.now().strftime(DATE_FORMAT)
    listings_to_add = [
        ("eBay", request.form.get("ebay_url", "").strip()),
        ("Vinted", request.form.get("vinted_url", "").strip()),
        ("Adverts.ie", request.form.get("adverts_url", "").strip()),
    ]
    listings_to_add = [
        (marketplace, url) for marketplace, url in listings_to_add if url
    ]

    if not sku:
        flash("SKU is required to add a listing.")
        return redirect(url_for("item_detail", item_id=item_id))
    if not listings_to_add:
        flash("Please enter at least one listing URL.")
        return redirect(url_for("item_detail", item_id=item_id))
    if listing_date is None:
        flash(f"Listing date must be in {DATE_FORMAT} format.")
        return redirect(url_for("item_detail", item_id=item_id))

    with get_db() as conn:
        for marketplace, listing_url in listings_to_add:
            if marketplace not in MARKETPLACES:
                flash("Invalid marketplace.")
                return redirect(url_for("item_detail", item_id=item_id))
            conn.execute(
                """
                INSERT INTO listings (item_id, marketplace, listing_url, listing_date)
                VALUES (?, ?, ?, ?)
                """,
                (item_id, marketplace, listing_url, listing_date),
            )
        if sku:
            conn.execute("UPDATE items SET sku = ? WHERE id = ?", (sku, item_id))
        conn.execute(
            "UPDATE items SET status = 'Listed', listed_date = ? WHERE id = ?",
            (listing_date, item_id),
        )
    flash("Listing added.")
    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/item/<int:item_id>/sell", methods=["POST"])
def mark_sold(item_id: int) -> Response:
    sale_price = parse_decimal(request.form.get("sale_price", ""))
    sale_date = parse_date(request.form.get("sale_date", ""))
    sold_marketplace = request.form.get("sold_marketplace", "")

    if sale_price is None:
        flash("Sale price must be a number.")
        return redirect(url_for("item_detail", item_id=item_id))
    if sale_date is None:
        flash(f"Sale date must be in {DATE_FORMAT} format.")
        return redirect(url_for("item_detail", item_id=item_id))
    if sold_marketplace not in MARKETPLACES:
        flash("Sold marketplace is required.")
        return redirect(url_for("item_detail", item_id=item_id))

    with get_db() as conn:
        conn.execute(
            """
            UPDATE items
            SET status = 'Sold', sale_price = ?, sale_date = ?, sold_marketplace = ?
            WHERE id = ?
            """,
            (float(sale_price), sale_date, sold_marketplace, item_id),
        )
    flash("Item marked as sold.")
    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/item/<int:item_id>/quick-update", methods=["POST"])
def quick_update_item(item_id: int) -> Response:
    item = fetch_item(item_id)
    if item is None:
        flash("Item not found.")
        return redirect(url_for("index"))

    sku = request.form.get("sku", "").strip() or None
    sale_price_raw = request.form.get("sale_price", "").strip()
    sold_marketplace = request.form.get("sold_marketplace", "").strip()
    sale_date_raw = request.form.get("sale_date", "").strip()

    sale_price = parse_decimal(sale_price_raw) if sale_price_raw else None
    sale_date = parse_date(sale_date_raw) if sale_date_raw else datetime.now().strftime(DATE_FORMAT)

    with get_db() as conn:
        if sku is not None:
            conn.execute("UPDATE items SET sku = ? WHERE id = ?", (sku, item_id))

        if sale_price is not None:
            if sold_marketplace not in MARKETPLACES:
                flash("Sold marketplace is required to mark as sold.")
                return redirect(url_for("index"))
            if sale_date is None:
                flash(f"Sale date must be in {DATE_FORMAT} format.")
                return redirect(url_for("index"))
            conn.execute(
                """
                UPDATE items
                SET status = 'Sold', sale_price = ?, sale_date = ?, sold_marketplace = ?
                WHERE id = ?
                """,
                (float(sale_price), sale_date, sold_marketplace, item_id),
            )
            flash("Item updated as sold.")
        else:
            flash("Item updated.")

    return redirect(url_for("index"))


@app.route("/item/<int:item_id>/open-listings")
def open_listings(item_id: int) -> str:
    item = fetch_item(item_id)
    if item is None:
        flash("Item not found.")
        return redirect(url_for("index"))
    listings = fetch_listings(item_id)
    return render_template("open_listings.html", item=item, listings=listings)


@app.route("/listing/<int:listing_id>/edit", methods=["GET", "POST"])
def edit_listing(listing_id: int) -> str | Response:
    listing = fetch_listing(listing_id)
    if listing is None:
        flash("Listing not found.")
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template(
            "listing_edit.html",
            listing=listing,
            marketplaces=MARKETPLACES,
            date_format=DATE_FORMAT,
        )

    marketplace = request.form.get("marketplace", "")
    listing_url = request.form.get("listing_url", "").strip()
    listing_date = parse_date(request.form.get("listing_date", ""))

    if marketplace not in MARKETPLACES:
        flash("Invalid marketplace.")
        return redirect(url_for("edit_listing", listing_id=listing_id))
    if not listing_url:
        flash("Listing URL is required.")
        return redirect(url_for("edit_listing", listing_id=listing_id))
    if listing_date is None:
        flash(f"Listing date must be in {DATE_FORMAT} format.")
        return redirect(url_for("edit_listing", listing_id=listing_id))

    with get_db() as conn:
        conn.execute(
            """
            UPDATE listings
            SET marketplace = ?, listing_url = ?, listing_date = ?
            WHERE id = ?
            """,
            (marketplace, listing_url, listing_date, listing_id),
        )
    flash("Listing updated.")
    return redirect(url_for("item_detail", item_id=listing["item_id"]))


@app.route("/item/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id: int) -> Response:
    item = fetch_item(item_id)
    if item is None:
        flash("Item not found.")
        return redirect(url_for("index"))
    with get_db() as conn:
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    flash("Item deleted.")
    return redirect(url_for("index"))


@app.route("/export.csv")
def export_csv() -> Response:
    items = fetch_items()

    def row_iter() -> Iterable[str]:
        header = [
            "name",
            "sku",
            "description",
            "purchase_price",
            "purchase_date",
            "purchase_source",
            "status",
            "listed_date",
            "sale_price",
            "sale_date",
            "sold_marketplace",
            "notes",
        ]
        yield ",".join(header) + "\n"
        for item in items:
            row = [
                item["name"],
                item["sku"] or "",
                item["description"] or "",
                str(item["purchase_price"]),
                item["purchase_date"],
                item["purchase_source"],
                item["status"],
                item["listed_date"] or "",
                str(item["sale_price"] or ""),
                item["sale_date"] or "",
                item["sold_marketplace"] or "",
                item["notes"] or "",
            ]
            output = io.StringIO()
            csv.writer(output).writerow(row)
            yield output.getvalue()

    return Response(row_iter(), mimetype="text/csv")


@app.route("/import", methods=["GET", "POST"])
def import_csv() -> str | Response:
    if request.method == "GET":
        return render_template("import.html", date_format=DATE_FORMAT)

    file = request.files.get("file")
    if file is None or file.filename == "":
        flash("Please choose a CSV file.")
        return redirect(url_for("import_csv"))

    decoded = file.stream.read().decode("utf-8-sig").splitlines()
    reader = csv.DictReader(decoded)
    required_fields = {
        "name",
        "purchase_price",
        "purchase_date",
        "purchase_source",
    }
    if not required_fields.issubset(reader.fieldnames or []):
        flash("CSV missing required columns.")
        return redirect(url_for("import_csv"))

    rows_inserted = 0
    with get_db() as conn:
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            sku = (row.get("sku") or "").strip() or None
            purchase_price = parse_decimal(row.get("purchase_price", ""))
            purchase_date = parse_date(row.get("purchase_date", ""))
            purchase_source = normalize_purchase_source((row.get("purchase_source") or "").strip())
            status = (row.get("status") or "Unlisted").strip() or "Unlisted"
            listed_date = parse_date(row.get("listed_date", ""))
            ebay_url = (row.get("ebay_url") or "").strip() or None
            vinted_url = (row.get("vinted_url") or "").strip() or None
            adverts_url = (row.get("adverts_url") or "").strip() or None
            sale_price = parse_decimal(row.get("sale_price", ""))
            sale_date = parse_date(row.get("sale_date", ""))
            sold_marketplace = (row.get("sold_marketplace") or "").strip() or None
            description = (row.get("description") or "").strip() or None
            notes = (row.get("notes") or "").strip() or None

            if purchase_price is None or purchase_date is None or not purchase_source:
                continue
            if status not in STATUSES:
                status = "Unlisted"

            ensure_purchase_source(conn, purchase_source)
            has_listing = any([ebay_url, vinted_url, adverts_url])
            if sale_price is not None:
                final_status = "Sold"
            else:
                final_status = "Listed" if has_listing else status
            if has_listing and listed_date is None:
                listed_date = parse_date(row.get("purchase_date", "")) or None

            cursor = conn.execute(
                """
                INSERT INTO items
                    (name, sku, description, purchase_price, purchase_date, purchase_source, status,
                     listed_date, sale_price, sale_date, sold_marketplace, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    sku,
                    description,
                    float(purchase_price),
                    purchase_date,
                    purchase_source,
                    final_status,
                    listed_date,
                    float(sale_price) if sale_price is not None else None,
                    sale_date,
                    sold_marketplace,
                    notes,
                ),
            )
            item_id = cursor.lastrowid
            listing_rows = [
                ("eBay", ebay_url),
                ("Vinted", vinted_url),
                ("Adverts.ie", adverts_url),
            ]
            for marketplace, listing_url in listing_rows:
                if not listing_url:
                    continue
                conn.execute(
                    """
                    INSERT INTO listings (item_id, marketplace, listing_url, listing_date)
                    VALUES (?, ?, ?, ?)
                    """,
                    (item_id, marketplace, listing_url, listed_date),
                )
            rows_inserted += 1

    flash(f"Imported {rows_inserted} items.")
    return redirect(url_for("index"))


@app.route("/reports")
def reports() -> str:
    month_filter = request.args.get("month") or "all"
    marketplace_filter = request.args.get("marketplace") or "all"
    summary = fetch_summary()
    with get_db() as conn:
        marketplace_data = conn.execute(
            """
            SELECT COALESCE(sold_marketplace, 'Unlisted') AS marketplace,
                   COUNT(*) AS count,
                   SUM(COALESCE(sale_price, 0)) AS total_sales
            FROM items
            GROUP BY marketplace
            ORDER BY total_sales DESC
            """
        ).fetchall()
        sold_items = conn.execute(
            """
            SELECT purchase_price, sale_price, sale_date, sold_marketplace
            FROM items
            WHERE sale_price IS NOT NULL AND sale_date IS NOT NULL
            """
        ).fetchall()
    monthly_summary: dict[str, dict[str, float]] = {}
    monthly_marketplace: dict[str, dict[str, float]] = {}
    available_months: set[str] = set()
    marketplace_names: set[str] = set()
    for item in sold_items:
        try:
            sale_month = datetime.strptime(item["sale_date"], DATE_FORMAT).strftime("%Y-%m")
        except ValueError:
            continue
        marketplace_name = item["sold_marketplace"] or "Unlisted"
        available_months.add(sale_month)
        marketplace_names.add(marketplace_name)
        if month_filter != "all" and sale_month != month_filter:
            continue
        if marketplace_filter != "all" and marketplace_name != marketplace_filter:
            continue
        if sale_month not in monthly_summary:
            monthly_summary[sale_month] = {
                "count": 0,
                "total_sales": 0.0,
                "total_cost": 0.0,
                "profit": 0.0,
            }
        if sale_month not in monthly_marketplace:
            monthly_marketplace[sale_month] = {}
        if marketplace_name not in monthly_marketplace[sale_month]:
            monthly_marketplace[sale_month][marketplace_name] = 0.0
        monthly_summary[sale_month]["count"] += 1
        monthly_summary[sale_month]["total_sales"] += float(item["sale_price"] or 0)
        monthly_summary[sale_month]["total_cost"] += float(item["purchase_price"] or 0)
        monthly_summary[sale_month]["profit"] += float(item["sale_price"] or 0) - float(
            item["purchase_price"] or 0
        )
        monthly_marketplace[sale_month][marketplace_name] += float(item["sale_price"] or 0)
    monthly_rows = [
        {
            "month": month,
            "count": data["count"],
            "total_sales": data["total_sales"],
            "total_cost": data["total_cost"],
            "profit": data["profit"],
        }
        for month, data in sorted(monthly_summary.items(), reverse=True)
    ]
    month_options = sorted(available_months)
    marketplace_options = sorted(marketplace_names)
    return render_template(
        "reports.html",
        summary=summary,
        marketplace_data=marketplace_data,
        monthly_rows=monthly_rows,
        monthly_marketplace=monthly_marketplace,
        month_options=month_options,
        marketplace_options=marketplace_options,
        month_filter=month_filter,
        marketplace_filter=marketplace_filter,
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
