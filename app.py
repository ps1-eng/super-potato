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

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("RESALE_SECRET_KEY", "resale-dev-key")


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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


init_db()

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


def fetch_items(
    status: str | None = None,
    marketplace: str | None = None,
    listing_url: str | None = None,
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
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " GROUP BY items.id ORDER BY items.id DESC"
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


@app.template_filter("currency")
def currency_filter(value: float | None) -> str:
    return format_currency(value)


@app.route("/")
def index() -> str:
    status = request.args.get("status") or None
    marketplace = request.args.get("marketplace") or None
    listing_url = (request.args.get("listing_url") or "").strip() or None
    items = fetch_items(status=status, marketplace=marketplace, listing_url=listing_url)
    summary = fetch_summary(
        status=status,
        marketplace=marketplace,
        listing_url=listing_url,
    )
    return render_template(
        "index.html",
        items=items,
        summary=summary,
        status=status,
        marketplace=marketplace,
        listing_url=listing_url,
        marketplaces=MARKETPLACES,
        statuses=STATUSES,
    )


@app.route("/item/new", methods=["POST"])
def add_item() -> Response:
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    purchase_price = parse_decimal(request.form.get("purchase_price", ""))
    purchase_date = parse_date(request.form.get("purchase_date", ""))
    purchase_source = request.form.get("purchase_source", "").strip()
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
    marketplace = request.form.get("marketplace", "")
    listing_url = request.form.get("listing_url", "").strip()
    listing_date = parse_date(request.form.get("listing_date", ""))

    if marketplace not in MARKETPLACES:
        flash("Invalid marketplace.")
        return redirect(url_for("item_detail", item_id=item_id))
    if not listing_url:
        flash("Listing URL is required.")
        return redirect(url_for("item_detail", item_id=item_id))
    if listing_date is None:
        flash(f"Listing date must be in {DATE_FORMAT} format.")
        return redirect(url_for("item_detail", item_id=item_id))

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO listings (item_id, marketplace, listing_url, listing_date)
            VALUES (?, ?, ?, ?)
            """,
            (item_id, marketplace, listing_url, listing_date),
        )
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


@app.route("/item/<int:item_id>/open-listings")
def open_listings(item_id: int) -> str:
    item = fetch_item(item_id)
    if item is None:
        flash("Item not found.")
        return redirect(url_for("index"))
    listings = fetch_listings(item_id)
    return render_template("open_listings.html", item=item, listings=listings)


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
            purchase_source = (row.get("purchase_source") or "").strip()
            status = (row.get("status") or "Unlisted").strip() or "Unlisted"
            listed_date = parse_date(row.get("listed_date", ""))
            sale_price = parse_decimal(row.get("sale_price", ""))
            sale_date = parse_date(row.get("sale_date", ""))
            sold_marketplace = (row.get("sold_marketplace") or "").strip() or None
            description = (row.get("description") or "").strip() or None
            notes = (row.get("notes") or "").strip() or None

            if purchase_price is None or purchase_date is None or not purchase_source:
                continue
            if status not in STATUSES:
                status = "Unlisted"

            conn.execute(
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
                    status,
                    listed_date,
                    float(sale_price) if sale_price is not None else None,
                    sale_date,
                    sold_marketplace,
                    notes,
                ),
            )
            rows_inserted += 1

    flash(f"Imported {rows_inserted} items.")
    return redirect(url_for("index"))


@app.route("/reports")
def reports() -> str:
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
    return render_template(
        "reports.html",
        summary=summary,
        marketplace_data=marketplace_data,
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
