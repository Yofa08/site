"""Deal Manager — Internal Admin + Public API

Start: uv run python main.py
"""

import re
import os
import math
import shutil
import subprocess
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, Request, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel

from database import get_db, init_db
from models import Category, Merch, Setting, Subscriber

# ── Field name aliases for template import ──────────────

FIELD_ALIASES = {
    "name": ["name", "product name", "product", "title", "item"],
    "category_id": ["category", "category_id", "cat"],
    "image_url": ["image url", "image", "img", "image_url", "picture", "photo"],
    "original_price": ["original price", "original", "reg price", "list price", "original_price", "was"],
    "discount_price": ["discount price", "sale price", "now", "price", "discount_price", "deal price"],
    "total_discount": ["total discount", "discount", "off", "total_discount", "savings", "% off"],
    "discount_detail": ["discount detail", "details", "discount_detail", "how to save", "instructions"],
    "code": ["code", "promo code", "coupon", "coupon code", "promo"],
    "amazon_link": ["amazon link", "link", "url", "amazon", "amazon_link", "buy"],
    "promotion_link": ["promotion link", "promo link", "promotion_link"],
    "rating": ["rating", "stars", "score", "review score"],
    "review_count": ["review count", "reviews", "review_count", "ratings", "# reviews"],
    "start_time": ["start time", "start date", "start", "start_time", "from"],
    "end_time": ["end time", "end date", "end", "end_time", "expires", "until"],
    "deal_date": ["deal date", "date", "deal_date", "day", "for date"],
    "is_hot": ["is hot", "hot", "featured", "is_hot", "top deal"],
    "is_featured": ["is featured", "hero", "featured deal", "is_featured", "showcase"],
    "budget": ["budget", "daily budget", "spend", "ad budget"],
    "creator_name": ["creator name", "creator", "influencer", "influencer name", "creator_name", "cc", "commission creator", "commission title", "commission"],
    "creator_id": ["creator id", "creator_id", "influencer id", "platform id", "cc id", "commission id", "commission creator id"],
    "status": ["status", "active"],
    "info": ["info", "description", "desc", "details", "highlights", "product info"],
    "remark": ["remark", "note", "notes", "remark", "internal"],
}

# Build reverse map: alias → field_name
ALIAS_TO_FIELD = {}
for field, aliases in FIELD_ALIASES.items():
    for a in aliases:
        ALIAS_TO_FIELD[a.lower().strip()] = field


def guess_field(col_name: str) -> Optional[str]:
    """Map a column header to a Merch field name, or None."""
    name = col_name.lower().strip()
    # Exact match
    if name in ALIAS_TO_FIELD:
        return ALIAS_TO_FIELD[name]
    # Strip parenthetical suffix: "CC (Commission)" → "cc"
    stripped = re.sub(r'\s*\(.*?\)\s*', '', name).strip()
    if stripped and stripped in ALIAS_TO_FIELD:
        return ALIAS_TO_FIELD[stripped]
    # Also try the parenthetical content itself: "(Commission)" → "commission"
    paren = re.search(r'\((.*?)\)', name)
    if paren and paren.group(1).strip() in ALIAS_TO_FIELD:
        return ALIAS_TO_FIELD[paren.group(1).strip()]
    return None


# Initialize DB at startup
init_db()


app = FastAPI(title="Deal Manager", version="1.2.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Pydantic Schemas ────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str
    keywords: str = ""
    sort_order: int = 0
    status: int = 1
    remark: str = ""


class MerchCreate(BaseModel):
    category_id: Optional[str] = None
    name: str
    image_url: str = ""
    info: str = ""
    original_price: str = ""
    discount_price: str = ""
    total_discount: str = ""
    discount_detail: str = ""
    code: str = ""
    amazon_link: str = ""
    promotion_link: str = ""
    rating: str = ""
    review_count: str = ""
    start_time: str = ""
    end_time: str = ""
    deal_date: Optional[str] = None
    status: int = 1
    is_hot: bool = False
    is_lower_price: bool = False
    is_featured: bool = False
    budget: str = ""
    creator_name: str = ""
    creator_id: str = ""
    remark: str = ""


class SettingUpdate(BaseModel):
    key: str
    value: str


class SubscribeRequest(BaseModel):
    email: str


class EnrichRequest(BaseModel):
    ids: list = []


# ── Helpers ─────────────────────────────────────────────

def parse_date(s: Optional[str]) -> Optional[date]:
    """Parse a deal date, tolerating the formats Excel / the admin form produce.

    Excel date cells come back as datetime objects and stringify to
    "YYYY-MM-DD 00:00:00", which the old date.fromisoformat() rejected — so
    every uploaded deal silently fell back to today's date. Accept objects,
    ISO date/datetime strings, and common MM/DD/YYYY variants.
    """
    if not s:
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    text = str(s).strip()
    if not text:
        return None
    # ISO date ("2026-08-30") or ISO datetime ("2026-08-30 00:00:00")
    try:
        return datetime.fromisoformat(text).date()
    except (ValueError, TypeError):
        pass
    # Common fallback formats (US MM/DD/YYYY, slashes/dashes, 2-digit year)
    for fmt in ("%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def get_setting(db: Session, key: str, default: str = "") -> str:
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default


def build_influencer_copy(deal: Merch) -> str:
    """Build influencer-ready text matching the standard deal template."""
    lines = []

    # Product name
    lines.append(f"Product name: {deal.name}")

    # CC (Commission program)
    if deal.creator_name:
        lines.append(f"CC：{deal.creator_name}")

    # CC ID
    if deal.creator_id:
        lines.append(f"CC ID: {deal.creator_id}")

    # Original price
    if deal.original_price:
        lines.append(f"Original price: ${deal.original_price}")

    # Discount price
    if deal.discount_price:
        lines.append(f"Discount price: ${deal.discount_price}")

    # Discount type
    if deal.total_discount:
        lines.append(f"Discount: {deal.total_discount}")

    # Discount code
    if deal.code:
        lines.append(f"Discount code: {deal.code}")

    # Discount detail (full description)
    if deal.discount_detail:
        lines.append(f"Detail: {deal.discount_detail}")

    # Budget
    if deal.budget:
        lines.append(f"Budget: ${deal.budget}")

    # Start time
    if deal.start_time:
        lines.append(f"Start time: {deal.start_time}")

    # End time
    if deal.end_time:
        lines.append(f"End time: {deal.end_time}")

    # Link
    if deal.amazon_link:
        lines.append(f"Link: {deal.amazon_link}")

    # Rating
    if deal.rating:
        review = f" ({deal.review_count} reviews)" if deal.review_count else ""
        lines.append(f"Rating: ⭐ {deal.rating}{review}")

    # Info / description
    if deal.info:
        lines.append(f"Info: {deal.info}")

    return "\n".join(lines)


def build_influencer_hashtags(deal: Merch) -> str:
    """Generate hashtags from deal info."""
    tags = ["#Deal", "#AmazonDeal", "#AmazonFinds"]
    if deal.category and deal.category.name:
        tags.append(f"#{deal.category.name.replace(' & ', '').replace(' ', '')}")
    if deal.total_discount:
        tags.append(f"#{deal.total_discount.replace('%', 'Percent')}Off")
    return " ".join(tags)


def _deal_with_copy(d: Merch) -> dict:
    """Serialize a deal and attach influencer copy for the public storefront."""
    dd = d.to_dict()
    dd["influencer_copy"] = build_influencer_copy(d)
    dd["influencer_hashtags"] = build_influencer_hashtags(d)
    return dd


# ── Amazon product scraper (price / rating / reviews) ──

AMZ_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
AMZ_COOKIE = "i18n-prefs=USD; lc-main=en_US; lc-acbus=en_US"  # force USD


def extract_asin(text: str) -> Optional[str]:
    """Pull a 10-char ASIN out of a URL or raw string."""
    m = re.search(r"(?:/dp/|/gp/product/|/gp/aw/d/|/product/)([A-Z0-9]{10})", text)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z0-9]{10})\b", text)
    if m:
        return m.group(1)
    return None


def fetch_amazon_page(asin: str) -> Optional[str]:
    """Download the product page via curl (its TLS fingerprint evades Amazon's
    bot check, which Python's urllib/requests reliably triggers).

    Timeouts are deliberately tight (connect 8s, total 10s) so the synchronous
    /api/amazon/lookup request always returns well under any gateway/nginx
    timeout. If Amazon hangs (JS challenge on datacenter IPs), we fail fast
    with a clean JSON error instead of letting the gateway cut us off and
    return an HTML 502/504 page (which the frontend can't parse as JSON).
    """
    if shutil.which("curl") is None:
        return None
    url = "https://www.amazon.com/dp/" + asin
    cmd = [
        "curl", "-s", "-L",
        "--connect-timeout", "8",
        "-m", "10",
        "-A", AMZ_UA,
        "-H", "Accept-Language: en-US,en;q=0.9",
        "-H", "Cookie: " + AMZ_COOKIE,
    ]
    # Optional proxy (e.g. residential proxy on Railway to dodge datacenter-IP
    # bot checks). Set env var AMZ_PROXY=http://user:pass@host:port
    proxy = os.getenv("AMZ_PROXY", "")
    if proxy:
        cmd += ["--proxy", proxy]
    cmd.append(url)
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=15)
        html = out.stdout.decode("utf-8", errors="replace")
        return html or None
    except (subprocess.TimeoutExpired, Exception):
        return None


def is_amazon_blocked(html: str) -> bool:
    return bool(re.search(
        r"(Robot Check|Enter the characters|not a robot|captcha|api-services-support)",
        html, re.I))


def parse_amazon_product(html: str) -> dict:
    """Extract title / price / original price / rating / reviews / image."""
    r = {"title": None, "price": None, "original_price": None,
         "rating": None, "reviews": None, "image_url": None}

    m = re.search(r'<span[^>]*id="productTitle"[^>]*>\s*(.*?)\s*</span>', html, re.S)
    if m:
        r["title"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()

    # Current price (embedded JSON)
    m = re.search(r'"priceAmount"\s*:\s*([0-9]+\.[0-9]{2})', html)
    if m:
        r["price"] = m.group(1)
    else:
        m = re.search(r'<span[^>]*class="a-offscreen"[^>]*>\s*\$?([0-9]+\.[0-9]{2})', html)
        if m:
            r["price"] = m.group(1)

    # Original / list price (strikethrough, if product is discounted)
    m = re.search(r'"(?:listPrice|basisPrice)"\s*:\s*\{[^}]*"amount"\s*:\s*([0-9]+\.[0-9]{2})', html)
    if m:
        r["original_price"] = m.group(1)

    # Star rating
    m = re.search(r"(\d\.\d)\s*out of 5 stars", html)
    if m:
        r["rating"] = m.group(1)

    # Review count
    m = re.search(r'id="acrCustomerReviewText"[^>]*aria-label="([\d,]+)\s*(?:Reviews?|ratings?)"', html)
    if m:
        r["reviews"] = m.group(1)
    else:
        m = re.search(r'id="acrCustomerReviewText"[^>]*>\s*\(?([\d,]+)\)?\s*<', html)
        if m:
            r["reviews"] = m.group(1)

    # Main image (upgrade to hi-res)
    m = re.search(r'data-a-dynamic-image="\{&quot;(https://m\.media-amazon\.com/images/I/[^&]+\.jpg)', html)
    if m:
        r["image_url"] = re.sub(r"_AC_S[XY]\d+_", "_AC_SL1500_", m.group(1))

    return r


def enrich_deals(db: Session, ids: list) -> dict:
    """Batch-scrape Amazon data to fill MISSING fields (never overwrite).

    Rate-limited via AMZ_ENRICH_DELAY (seconds between requests, default 2).
    Stops early if Amazon triggers a bot check.
    """
    import time

    deals = db.query(Merch).filter(Merch.id.in_(ids)).all()
    delay = float(os.getenv("AMZ_ENRICH_DELAY", "2.0"))
    stats = {"total": len(deals), "updated": 0, "no_change": 0,
             "no_asin": 0, "fetch_fail": 0, "blocked": False}

    for m in deals:
        asin = extract_asin(m.amazon_link or "")
        if not asin:
            stats["no_asin"] += 1
            continue

        html = fetch_amazon_page(asin)
        if html is None:
            stats["fetch_fail"] += 1
            time.sleep(delay)
            continue
        if is_amazon_blocked(html):
            stats["blocked"] = True
            break  # further requests would also be blocked

        r = parse_amazon_product(html)
        changed = False
        if not m.rating and r["rating"]:
            m.rating = r["rating"]; changed = True
        if not m.review_count and r["reviews"]:
            m.review_count = r["reviews"]; changed = True
        if not m.image_url and r["image_url"]:
            m.image_url = r["image_url"]; changed = True
        # Price mapping: listPrice → original, current → discount; else current → original
        if not m.original_price:
            if r["original_price"]:
                m.original_price = r["original_price"]; changed = True
            elif r["price"]:
                m.original_price = r["price"]; changed = True
        if not m.discount_price and r["original_price"] and r["price"]:
            m.discount_price = r["price"]; changed = True

        if changed:
            m.updated_at = datetime.utcnow()
            stats["updated"] += 1
        else:
            stats["no_change"] += 1
        time.sleep(delay)

    db.commit()
    return stats


# ── Health ────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ═════════════════════════════════════════════════════════
#  Admin Pages
# ═════════════════════════════════════════════════════════

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    page: int = Query(1, ge=1),
    date_param: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
):
    page_size = 30
    q = db.query(Merch)

    # Date filter
    selected_date = None
    if date_param:
        d = parse_date(date_param)
        if d:
            selected_date = d
            q = q.filter(Merch.deal_date == d)

    total = q.count()
    total_pages = max(1, math.ceil(total / page_size))
    deals = (
        q.order_by(Merch.is_hot.desc(), Merch.deal_date.desc(), Merch.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    categories = db.query(Category).order_by(Category.sort_order).all()

    # Build date nav (7 days back)
    today = date.today()
    date_nav = []
    for i in range(7):
        d = today - timedelta(days=i)
        date_nav.append({
            "label": d.strftime("%b %d"),
            "iso": d.isoformat(),
            "suffix": "Today" if i == 0 else ("Yesterday" if i == 1 else ""),
            "count": db.query(Merch).filter(Merch.deal_date == d).count(),
        })

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "deals": [d.to_dict() for d in deals],
        "categories": [c.to_dict() for c in categories],
        "page": page, "total_pages": total_pages, "total": total,
        "selected_date": selected_date.isoformat() if selected_date else "",
        "date_nav": date_nav,
        "all_count": db.query(Merch).count(),
    })


@app.get("/admin/categories", response_class=HTMLResponse)
def admin_categories(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.sort_order).all()
    return templates.TemplateResponse("categories.html", {
        "request": request,
        "categories": [c.to_dict() for c in categories],
    })


@app.get("/admin/settings", response_class=HTMLResponse)
def admin_settings(request: Request, db: Session = Depends(get_db)):
    settings = {s.key: s.value for s in db.query(Setting).all()}
    subscribers = db.query(Subscriber).order_by(Subscriber.subscribed_at.desc()).all()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "subscribers": [s.to_dict() for s in subscribers],
        "subscriber_count": len(subscribers),
    })


# ═════════════════════════════════════════════════════════
#  CRUD — Category
# ═════════════════════════════════════════════════════════

@app.post("/api/categories")
def create_category(data: CategoryCreate, db: Session = Depends(get_db)):
    cat = Category(**data.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return JSONResponse({"code": 200, "success": True, "data": cat.to_dict()})


@app.put("/api/categories/{cat_id}")
def update_category(cat_id: str, data: CategoryCreate, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(404, "Category not found")
    for k, v in data.model_dump().items():
        setattr(cat, k, v)
    db.commit()
    return JSONResponse({"code": 200, "success": True})


@app.delete("/api/categories/{cat_id}")
def delete_category(cat_id: str, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(404, "Category not found")
    db.query(Merch).filter(Merch.category_id == cat_id).update({Merch.category_id: None})
    db.delete(cat)
    db.commit()
    return JSONResponse({"code": 200, "success": True})


# ═════════════════════════════════════════════════════════
#  CRUD — Merch
# ═════════════════════════════════════════════════════════

@app.post("/api/merches")
def create_merch(data: MerchCreate, db: Session = Depends(get_db)):
    payload = data.model_dump()
    payload.pop("deal_date", None)
    m = Merch(**payload)
    d = parse_date(data.deal_date)
    if d:
        m.deal_date = d
    db.add(m)
    db.commit()
    db.refresh(m)
    return JSONResponse({"code": 200, "success": True, "data": m.to_dict()})


@app.put("/api/merches/{merch_id}")
def update_merch(merch_id: str, data: MerchCreate, db: Session = Depends(get_db)):
    m = db.query(Merch).filter(Merch.id == merch_id).first()
    if not m:
        raise HTTPException(404, "Deal not found")
    payload = data.model_dump()
    payload.pop("deal_date", None)
    for k, v in payload.items():
        setattr(m, k, v)
    d = parse_date(data.deal_date)
    if d:
        m.deal_date = d
    m.updated_at = datetime.utcnow()
    db.commit()
    return JSONResponse({"code": 200, "success": True})


@app.delete("/api/merches/{merch_id}")
def delete_merch(merch_id: str, db: Session = Depends(get_db)):
    m = db.query(Merch).filter(Merch.id == merch_id).first()
    if not m:
        raise HTTPException(404, "Deal not found")
    db.delete(m)
    db.commit()
    return JSONResponse({"code": 200, "success": True})


@app.post("/api/merches/batch-action")
async def batch_action(request: Request, db: Session = Depends(get_db)):
    """Batch operations on deals.

    Accepts JSON: {"action": "delete|set_status", "ids": [...], "status": 1}
    """
    body = await request.json()
    action = body.get("action", "")
    ids = body.get("ids", [])

    if not ids:
        raise HTTPException(400, "No deal IDs provided")

    deals = db.query(Merch).filter(Merch.id.in_(ids)).all()

    if action == "delete":
        for m in deals:
            db.delete(m)
        db.commit()
        return JSONResponse({"code": 200, "success": True, "data": {"deleted": len(deals)}})

    elif action == "set_status":
        status = body.get("status", 1)
        for m in deals:
            m.status = status
            m.updated_at = datetime.utcnow()
        db.commit()
        status_labels = {1: "active", 0: "draft", 2: "expired"}
        return JSONResponse({"code": 200, "success": True, "data": {"updated": len(deals), "status": status_labels.get(status, str(status))}})

    elif action == "toggle_hot":
        for m in deals:
            m.is_hot = not m.is_hot
            m.updated_at = datetime.utcnow()
        db.commit()
        return JSONResponse({"code": 200, "success": True, "data": {"toggled": len(deals)}})

    else:
        raise HTTPException(400, f"Unknown action: {action}")


@app.post("/api/merches/batch")
async def batch_import_merches(request: Request, db: Session = Depends(get_db)):
    """Import deals from pasted template text (tab/pipe/comma).

    Accepts JSON: {"text": "row1\\nrow2\\n..."}
    """
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(400, "No data provided")

    imported, errors, imported_ids = _process_import_rows(text, db)
    return JSONResponse({
        "code": 200,
        "success": True,
        "data": {"imported": imported, "errors": errors, "imported_ids": imported_ids},
    })


@app.post("/api/merches/upload")
async def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import deals from uploaded .xlsx file."""
    import io

    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Only .xlsx files are supported")

    try:
        import openpyxl
        contents = await file.read()
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        ws = wb.active

        # Read all rows, convert to tab-separated text.
        # Native Excel date/datetime cells (e.g. a user-typed "Deal Date") are
        # normalized to YYYY-MM-DD so parse_date() can read them.
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = []
            for c in row:
                if c is None:
                    cells.append("")
                elif isinstance(c, (datetime, date)):
                    cells.append(c.strftime("%Y-%m-%d"))
                else:
                    cells.append(str(c).strip())
            # Trim trailing empty cells
            while cells and cells[-1] == "":
                cells.pop()
            if any(cells):
                rows.append("\t".join(cells))
        wb.close()

        if not rows:
            raise HTTPException(400, "No data found in file")

        text = "\n".join(rows)
        imported, errors, imported_ids = _process_import_rows(text, db)

        return JSONResponse({
            "code": 200,
            "success": True,
            "data": {"imported": imported, "errors": errors, "imported_ids": imported_ids, "filename": file.filename},
        })
    except Exception as e:
        raise HTTPException(400, f"Failed to read Excel file: {str(e)}")


def _process_import_rows(text: str, db: Session):
    """Shared helper: parse tab/pipe/comma text and import rows. Returns (imported, errors)."""
    import csv
    import io

    first_line = text.split("\n")[0]
    if "\t" in first_line:
        delimiter = "\t"
    elif "|" in first_line:
        delimiter = "|"
    elif "," in first_line:
        delimiter = ","
    else:
        delimiter = "\t"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    cat_map = {c.name.lower(): c.id for c in db.query(Category).all()}

    rows = list(reader)
    if not rows:
        raise HTTPException(400, "No rows found")

    first_cell = rows[0][0].strip().lower() if rows[0] else ""
    has_header = guess_field(first_cell) is not None or first_cell in {"name", "product name", "product"}
    data_rows = rows[1:] if has_header else rows
    headers = rows[0] if has_header else None

    col_map = []
    if has_header and headers:
        for i, h in enumerate(headers):
            field = guess_field(h.strip())
            if field:
                col_map.append((field, i))
    else:
        defaults = ["name", "category_id", "image_url", "original_price", "discount_price",
                     "total_discount", "discount_detail", "code", "amazon_link",
                     "promotion_link", "rating", "review_count", "start_time", "end_time",
                     "deal_date", "is_hot", "is_featured", "budget", "creator_name", "creator_id", "status", "is_lower_price", "info", "remark"]
        for i, f in enumerate(defaults):
            col_map.append((f, i))

    imported = 0
    imported_ids = []
    errors = []

    for row_num, row in enumerate(data_rows, start=2 if has_header else 1):
        if not row or all(c.strip() == "" for c in row):
            continue

        deal_data = {"status": 1}
        for field, idx in col_map:
            if idx < len(row) and row[idx].strip():
                val = row[idx].strip()
                if field == "category_id":
                    cat_id = cat_map.get(val.lower())
                    if cat_id:
                        deal_data[field] = cat_id
                    else:
                        deal_data[field] = val
                elif field == "is_hot":
                    deal_data[field] = val.lower() in {"yes", "true", "1", "y", "hot", "x"}
                elif field == "is_featured":
                    deal_data[field] = val.lower() in {"yes", "true", "1", "y", "x"}
                elif field == "status":
                    try:
                        deal_data[field] = int(val)
                    except ValueError:
                        vlow = val.lower()
                        if vlow in {"active", "on", "yes"}:
                            deal_data[field] = 1
                        elif vlow in {"draft", "off"}:
                            deal_data[field] = 0
                        elif vlow in {"expired", "done"}:
                            deal_data[field] = 2
                elif field == "deal_date":
                    d = parse_date(val)
                    if d:
                        deal_data[field] = d
                elif field == "is_lower_price":
                    deal_data[field] = val.lower() in {"yes", "true", "1", "y", "x"}
                else:
                    deal_data[field] = val

        if not deal_data.get("name"):
            errors.append(f"Row {row_num}: missing product name, skipped")
            continue

        deal_date_val = deal_data.pop("deal_date", None)
        m = Merch(**deal_data)
        if deal_date_val:
            m.deal_date = deal_date_val

        db.add(m)
        db.flush()  # assign id
        imported_ids.append(m.id)
        imported += 1

    db.commit()
    return imported, errors, imported_ids


# ═════════════════════════════════════════════════════════
#  Settings API
# ═════════════════════════════════════════════════════════

@app.post("/api/settings")
def update_setting(data: SettingUpdate, db: Session = Depends(get_db)):
    s = db.query(Setting).filter(Setting.key == data.key).first()
    if s:
        s.value = data.value
        s.updated_at = datetime.utcnow()
    else:
        s = Setting(key=data.key, value=data.value)
        db.add(s)
    db.commit()
    return JSONResponse({"code": 200, "success": True})


@app.get("/api/settings")
def list_settings(db: Session = Depends(get_db)):
    settings = {s.key: s.value for s in db.query(Setting).all()}
    return JSONResponse({"code": 200, "success": True, "data": settings})


# ═════════════════════════════════════════════════════════
#  Subscriber API
# ═════════════════════════════════════════════════════════

@app.post("/api/subscribe")
def subscribe(data: SubscribeRequest, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if not email or "@" not in email:
        return JSONResponse({"code": 400, "success": False, "message": "Invalid email"})
    existing = db.query(Subscriber).filter(Subscriber.email == email).first()
    if existing:
        if existing.status == 0:
            existing.status = 1
            existing.subscribed_at = datetime.utcnow()
            db.commit()
            return JSONResponse({"code": 200, "success": True, "message": "Re-subscribed!"})
        return JSONResponse({"code": 200, "success": True, "message": "Already subscribed!"})
    sub = Subscriber(email=email)
    db.add(sub)
    db.commit()
    return JSONResponse({"code": 200, "success": True, "message": "Subscribed!"})


@app.delete("/api/subscribers/{sub_id}")
def delete_subscriber(sub_id: str, db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.id == sub_id).first()
    if not sub:
        raise HTTPException(404, "Subscriber not found")
    db.delete(sub)
    db.commit()
    return JSONResponse({"code": 200, "success": True})


# ── Amazon lookup (auto-fill price / rating / reviews) ──

@app.get("/api/amazon/lookup")
def amazon_lookup(url: str = Query(""), asin: str = Query("")):
    """Given an Amazon URL or ASIN, scrape current price / rating / review count."""
    target = (url or asin).strip()
    if not target:
        raise HTTPException(400, "Provide ?url= or ?asin=")
    asin_val = extract_asin(target)
    if not asin_val:
        raise HTTPException(400, "Could not extract an ASIN from input")

    html = fetch_amazon_page(asin_val)
    if html is None:
        raise HTTPException(502, "Failed to fetch Amazon page (curl unavailable or network error)")
    if is_amazon_blocked(html):
        raise HTTPException(429, "Amazon bot check triggered — try again later")

    r = parse_amazon_product(html)
    if not any([r["price"], r["rating"], r["reviews"]]):
        raise HTTPException(502, "Could not parse product data (page structure may have changed)")

    r["asin"] = asin_val
    r["amazon_link"] = "https://www.amazon.com/dp/" + asin_val
    return JSONResponse({"code": 200, "success": True, "data": r})


@app.post("/api/amazon/enrich")
def amazon_enrich(data: EnrichRequest, db: Session = Depends(get_db)):
    """Batch-fill missing price/rating/reviews/image on deals.

    Body: {"ids": [...]}  → enrich only those deals.
    Body: {"ids": []}     → auto-find active deals with a link but missing data.
    """
    ids = data.ids or []
    if not ids:
        q = (
            db.query(Merch)
            .filter(Merch.status == 1, Merch.amazon_link != "")
            .filter(or_(
                Merch.rating == "",
                Merch.review_count == "",
                Merch.original_price == "",
                Merch.image_url == "",
            ))
        )
        ids = [m.id for m in q.limit(50).all()]
        if not ids:
            return JSONResponse({"code": 200, "success": True, "data": {
                "total": 0, "updated": 0, "no_change": 0, "no_asin": 0,
                "fetch_fail": 0, "blocked": False, "message": "没有需要补全的 deal",
            }})

    stats = enrich_deals(db, ids)
    return JSONResponse({"code": 200, "success": True, "data": stats})


# ═════════════════════════════════════════════════════════
#  Public API
# ═════════════════════════════════════════════════════════

@app.get("/api/merches")
def api_list_merches(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category_id: Optional[str] = None,
    status: Optional[int] = None,
    is_hot: Optional[bool] = None,
    keyword: Optional[str] = None,
    deal_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Merch)
    if category_id:
        q = q.filter(Merch.category_id == category_id)
    if status is not None:
        q = q.filter(Merch.status == status)
    if is_hot is not None:
        q = q.filter(Merch.is_hot == is_hot)
    if keyword:
        q = q.filter(
            Merch.name.ilike(f"%{keyword}%")
            | Merch.discount_detail.ilike(f"%{keyword}%")
            | Merch.remark.ilike(f"%{keyword}%")
        )
    d = parse_date(deal_date)
    if d:
        q = q.filter(Merch.deal_date == d)

    total = q.count()
    items = (
        q.order_by(Merch.is_hot.desc(), Merch.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return JSONResponse({"code": 200, "success": True, "data": {
        "records": [m.to_dict() for m in items],
        "total": total, "page": page, "size": size,
    }})


@app.get("/api/merches/{merch_id}")
def api_get_merch(merch_id: str, db: Session = Depends(get_db)):
    m = db.query(Merch).filter(Merch.id == merch_id).first()
    if not m:
        raise HTTPException(404, "Deal not found")
    return JSONResponse({"code": 200, "success": True, "data": m.to_dict()})


@app.get("/api/categories")
def api_list_categories(db: Session = Depends(get_db)):
    cats = (
        db.query(Category).filter(Category.status == 1)
        .order_by(Category.sort_order).all()
    )
    return JSONResponse({"code": 200, "success": True, "data": [c.to_dict() for c in cats]})


# ═════════════════════════════════════════════════════════
#  Public Storefront
# ═════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def public_index(
    request: Request,
    db: Session = Depends(get_db),
):
    categories = (
        db.query(Category).filter(Category.status == 1)
        .order_by(Category.sort_order).all()
    )
    today = date.today()

    # Featured deals for hero section (today's featured)
    featured = (
        db.query(Merch)
        .filter(Merch.status == 1, Merch.deal_date == today, Merch.is_featured == True)
        .order_by(Merch.is_hot.desc(), Merch.created_at.desc())
        .limit(6).all()
    )
    featured_ids = {f.id for f in featured}

    # All active deals, newest date first — everything on a single page
    all_deals = (
        db.query(Merch)
        .filter(Merch.status == 1)
        .order_by(Merch.deal_date.desc(), Merch.is_hot.desc(), Merch.created_at.desc())
        .all()
    )

    # Group by deal_date, newest first; featured deals stay in the hero only.
    # Explicit key sort so NULL deal_date always lands last on any DB (SQLite/PG).
    groups = {}
    for d in all_deals:
        if d.id in featured_ids:
            continue
        groups.setdefault(d.deal_date, []).append(d)

    date_groups = []
    for dkey, items in sorted(
        groups.items(), key=lambda kv: (kv[0] is not None, kv[0] or date.max), reverse=True
    ):
        suffix = ""
        if dkey:
            if dkey == today:
                suffix = "Today"
            elif dkey == today - timedelta(days=1):
                suffix = "Yesterday"
        date_groups.append({
            "label": dkey.strftime("%b %d, %Y") if dkey else "No Date",
            "suffix": suffix,
            "iso": dkey.isoformat() if dkey else "",
            "deals": [_deal_with_copy(m) for m in items],
        })

    site_settings = {s.key: s.value for s in db.query(Setting).all()}

    return templates.TemplateResponse("public.html", {
        "request": request,
        "categories": [c.to_dict() for c in categories],
        "date_groups": date_groups,
        "featured": [_deal_with_copy(f) for f in featured],
        "settings": site_settings,
    })


# ── Entrypoint ──────────────────────────────────────────

if __name__ == "__main__":
    import os
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("ENV", "dev") == "dev"
    uvicorn.run("main:app", host=host, port=port, reload=reload)
else:
    import os
    # FastAPI prod-ready config
    pass
