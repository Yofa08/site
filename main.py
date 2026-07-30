"""Deal Manager — Internal Admin + Public API

Start: uv run python main.py
"""

import re
import math
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, Request, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
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


# ── Helpers ─────────────────────────────────────────────

def parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
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

    imported, errors = _process_import_rows(text, db)
    return JSONResponse({
        "code": 200,
        "success": True,
        "data": {"imported": imported, "errors": errors},
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

        # Read all rows, convert to tab-separated text
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() if c is not None else "" for c in row]
            # Trim trailing empty cells
            while cells and cells[-1] == "":
                cells.pop()
            if any(cells):
                rows.append("\t".join(cells))
        wb.close()

        if not rows:
            raise HTTPException(400, "No data found in file")

        text = "\n".join(rows)
        imported, errors = _process_import_rows(text, db)

        return JSONResponse({
            "code": 200,
            "success": True,
            "data": {"imported": imported, "errors": errors, "filename": file.filename},
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
        imported += 1

    db.commit()
    return imported, errors


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
    date_param: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
):
    categories = (
        db.query(Category).filter(Category.status == 1)
        .order_by(Category.sort_order).all()
    )
    q = db.query(Merch).filter(Merch.status == 1)

    selected_date = date.today()
    if date_param:
        d = parse_date(date_param)
        if d:
            selected_date = d
    q = q.filter(Merch.deal_date == selected_date)

    # Featured deals for hero section (today's featured)
    featured = (
        db.query(Merch)
        .filter(Merch.status == 1, Merch.deal_date == selected_date, Merch.is_featured == True)
        .order_by(Merch.is_hot.desc(), Merch.created_at.desc())
        .limit(6).all()
    )

    # Remaining deals (exclude featured, or all if no featured)
    if featured:
        featured_ids = [f.id for f in featured]
        deals = (
            q.filter(~Merch.id.in_(featured_ids))
            .order_by(Merch.is_hot.desc(), Merch.created_at.desc())
            .limit(40).all()
        )
    else:
        deals = (
            q.order_by(Merch.is_hot.desc(), Merch.created_at.desc())
            .limit(40).all()
        )

    # Build influencer copy for each deal
    deals_with_copy = []
    for d in deals:
        dd = d.to_dict()
        dd["influencer_copy"] = build_influencer_copy(d)
        dd["influencer_hashtags"] = build_influencer_hashtags(d)
        deals_with_copy.append(dd)
    featured_with_copy = []
    for f in featured:
        fd = f.to_dict()
        fd["influencer_copy"] = build_influencer_copy(f)
        fd["influencer_hashtags"] = build_influencer_hashtags(f)
        featured_with_copy.append(fd)

    # Date nav
    today = date.today()
    date_nav = []
    for i in range(3):
        d = today - timedelta(days=i)
        date_nav.append({
            "label": d.strftime("%b %d"),
            "iso": d.isoformat(),
            "suffix": "Today" if i == 0 else ("Yesterday" if i == 1 else ""),
        })

    # Site settings
    site_settings = {s.key: s.value for s in db.query(Setting).all()}

    return templates.TemplateResponse("public.html", {
        "request": request,
        "categories": [c.to_dict() for c in categories],
        "deals": deals_with_copy,
        "featured": featured_with_copy,
        "selected_date": selected_date.isoformat(),
        "date_nav": date_nav,
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
