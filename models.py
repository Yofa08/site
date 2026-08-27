"""Data models — Category, Merch, Setting, Subscriber"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    DateTime,
    Date,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from database import Base


def gen_id():
    return str(uuid.uuid4()).replace("-", "")


class Category(Base):
    __tablename__ = "categories"

    id = Column(String(32), primary_key=True, default=gen_id)
    name = Column(String(100), nullable=False, comment="Category name")
    keywords = Column(String(500), default="", comment="SEO keywords, comma-separated")
    sort_order = Column(Integer, default=0, comment="Display order")
    status = Column(Integer, default=1, comment="1=active 0=inactive")
    remark = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deals = relationship("Merch", back_populates="category")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "keywords": self.keywords,
            "sort_order": self.sort_order,
            "status": self.status,
            "remark": self.remark,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Merch(Base):
    __tablename__ = "merches"

    id = Column(String(32), primary_key=True, default=gen_id)
    category_id = Column(String(32), ForeignKey("categories.id"), nullable=True)

    name = Column(String(500), nullable=False, comment="Product name")
    image_url = Column(String(1000), default="", comment="Product image URL")
    info = Column(Text, default="", comment="Product description / highlights")

    original_price = Column(String(50), default="", comment="Original price")
    discount_price = Column(String(50), default="", comment="Discounted price")
    total_discount = Column(String(20), default="", comment="Total discount e.g. 66%")
    discount_detail = Column(String(500), default="", comment="Discount breakdown")

    code = Column(String(100), default="", comment="Promo / coupon code")

    amazon_link = Column(String(1000), default="", comment="Amazon product link")
    promotion_link = Column(String(1000), default="", comment="Amazon promotion link")

    rating = Column(String(10), default="", comment="Star rating")
    review_count = Column(String(20), default="", comment="Review count")

    start_time = Column(String(50), default="", comment="Deal start time")
    end_time = Column(String(50), default="", comment="Deal end time")
    deal_date = Column(Date, default=date.today, comment="The date this deal is featured for")

    status = Column(Integer, default=1, comment="1=active 0=inactive 2=expired")
    is_hot = Column(Boolean, default=False, comment="Featured / hot deal")
    is_lower_price = Column(Boolean, default=False, comment="All-time low price")
    is_featured = Column(Boolean, default=False, comment="Show in today's featured hero section")

    # Orders & Creator
    budget = Column(String(50), default="", comment="Target orders e.g. 50")
    creator_name = Column(String(100), default="", comment="Creator/influencer name")
    creator_id = Column(String(100), default="", comment="Creator/influencer platform ID")

    tenant_id = Column(String(32), default="000000")
    remark = Column(String(500), default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("Category", back_populates="deals")

    def to_dict(self):
        return {
            "id": self.id,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else None,
            "name": self.name,
            "image_url": self.image_url,
            "info": self.info,
            "original_price": self.original_price,
            "discount_price": self.discount_price,
            "total_discount": self.total_discount,
            "discount_detail": self.discount_detail,
            "code": self.code,
            "amazon_link": self.amazon_link,
            "promotion_link": self.promotion_link,
            "rating": self.rating,
            "review_count": self.review_count,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "deal_date": self.deal_date.isoformat() if self.deal_date else None,
            "status": self.status,
            "is_hot": self.is_hot,
            "is_lower_price": self.is_lower_price,
            "is_featured": self.is_featured,
            "budget": self.budget,
            "creator_name": self.creator_name,
            "creator_id": self.creator_id,
            "tenant_id": self.tenant_id,
            "remark": self.remark,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── Site Settings (key-value) ───────────────────────────

class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True, comment="Setting key")
    value = Column(Text, default="", comment="Setting value")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {"key": self.key, "value": self.value}


# ── Subscribers ─────────────────────────────────────────

class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(String(32), primary_key=True, default=gen_id)
    email = Column(String(200), nullable=False, unique=True, comment="Subscriber email")
    status = Column(Integer, default=1, comment="1=active 0=unsubscribed")
    subscribed_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "status": self.status,
            "subscribed_at": self.subscribed_at.isoformat() if self.subscribed_at else None,
        }
