from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    unit: Mapped[str] = mapped_column(String(32), default="1")
    category: Mapped[str | None] = mapped_column(String(32), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    offers: Mapped[list["ShopOffer"]] = relationship(back_populates="resource")
    box_items: Mapped[list["BoxItem"]] = relationship(back_populates="resource")


class Currency(Base):
    __tablename__ = "currencies"
    __table_args__ = (
        CheckConstraint("kind IN ('gold', 'token')", name="ck_currency_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="token")
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    shop_types: Mapped[list["ShopType"]] = relationship(back_populates="currency")


class ShopType(Base):
    """商店类型字典：商店名称 + 绑定货币。"""

    __tablename__ = "shop_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    currency_id: Mapped[int] = mapped_column(
        ForeignKey("currencies.id", ondelete="RESTRICT")
    )
    default_refresh_period: Mapped[str | None] = mapped_column(
        String(32), default=None
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    currency: Mapped[Currency] = relationship(back_populates="shop_types")
    shop: Mapped["Shop | None"] = relationship(
        back_populates="shop_type", uselist=False
    )

    @property
    def shop_id(self) -> int | None:
        return self.shop.id if self.shop is not None else None


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_type_id: Mapped[int] = mapped_column(
        ForeignKey("shop_types.id", ondelete="RESTRICT"), unique=True, index=True
    )
    refresh_period: Mapped[str | None] = mapped_column(String(32), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    shop_type: Mapped[ShopType] = relationship(back_populates="shop")
    offers: Mapped[list["ShopOffer"]] = relationship(
        back_populates="shop",
        cascade="all, delete-orphan",
        order_by="ShopOffer.id",
    )

    @property
    def name(self) -> str:
        return self.shop_type.name

    @property
    def currency(self) -> Currency:
        return self.shop_type.currency


class ShopOffer(Base):
    __tablename__ = "shop_offers"
    __table_args__ = (
        CheckConstraint("resource_qty > 0", name="ck_offer_resource_qty"),
        CheckConstraint("list_currency_qty > 0", name="ck_offer_currency_qty"),
        CheckConstraint(
            "discount_pct IS NULL OR (discount_pct >= 0 AND discount_pct <= 100)",
            name="ck_offer_discount",
        ),
        CheckConstraint(
            "limit_qty IS NULL OR limit_qty >= 1", name="ck_offer_limit"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), index=True
    )
    resource_qty: Mapped[float] = mapped_column(Float)
    list_currency_qty: Mapped[float] = mapped_column(Float)
    discount_pct: Mapped[float | None] = mapped_column(Float, default=None)
    limit_qty: Mapped[int | None] = mapped_column(Integer, default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    shop: Mapped[Shop] = relationship(back_populates="offers")
    resource: Mapped[Resource] = relationship(back_populates="offers")

    @property
    def effective_currency_qty(self) -> float:
        discount = self.discount_pct or 0.0
        return self.list_currency_qty * (1 - discount / 100)

    @property
    def unit_price_per_1000(self) -> float:
        if self.resource_qty <= 0:
            return 0.0
        return self.effective_currency_qty / (self.resource_qty / 1000)


class Box(Base):
    __tablename__ = "boxes"
    __table_args__ = (
        CheckConstraint(
            "selection_type IN ('choose_one', 'fixed', 'random')",
            name="ck_box_selection_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    size: Mapped[str | None] = mapped_column(String(32), default=None)
    selection_type: Mapped[str] = mapped_column(String(16), default="choose_one")
    source: Mapped[str | None] = mapped_column(String(64), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    items: Mapped[list["BoxItem"]] = relationship(
        back_populates="box",
        cascade="all, delete-orphan",
        order_by="BoxItem.id",
    )


class BoxItem(Base):
    __tablename__ = "box_items"
    __table_args__ = (
        UniqueConstraint("box_id", "resource_id", name="uq_box_item_resource"),
        CheckConstraint("qty > 0", name="ck_box_item_qty"),
        CheckConstraint(
            "probability IS NULL OR (probability >= 0 AND probability <= 1)",
            name="ck_box_item_probability",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    box_id: Mapped[int] = mapped_column(
        ForeignKey("boxes.id", ondelete="CASCADE"), index=True
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), index=True
    )
    qty: Mapped[float] = mapped_column(Float)
    probability: Mapped[float | None] = mapped_column(Float, default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    box: Mapped[Box] = relationship(back_populates="items")
    resource: Mapped[Resource] = relationship(back_populates="box_items")
