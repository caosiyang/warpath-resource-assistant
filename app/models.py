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


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class ResourceType(Base):
    __tablename__ = "resource_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    resources: Mapped[list["Resource"]] = relationship(back_populates="resource_type")

    @property
    def resource_count(self) -> int:
        return len(self.resources)


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    unit: Mapped[str] = mapped_column(String(32), default="1")
    type_id: Mapped[int | None] = mapped_column(
        ForeignKey("resource_types.id", ondelete="RESTRICT"), default=None, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    resource_type: Mapped[ResourceType | None] = relationship(
        back_populates="resources"
    )
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
    __table_args__ = (
        CheckConstraint(
            "pricing_mode IN ('standard', 'vip_tiered')",
            name="ck_shop_type_pricing_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    currency_id: Mapped[int] = mapped_column(
        ForeignKey("currencies.id", ondelete="RESTRICT")
    )
    default_refresh_period: Mapped[str | None] = mapped_column(
        String(32), default=None
    )
    pricing_mode: Mapped[str] = mapped_column(String(16), default="standard")
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

    @property
    def is_vip_tiered(self) -> bool:
        return self.pricing_mode == "vip_tiered"


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
        UniqueConstraint(
            "shop_id",
            "resource_id",
            "min_vip_level",
            name="uq_shop_offer_resource_vip",
        ),
        CheckConstraint("resource_qty > 0", name="ck_offer_resource_qty"),
        CheckConstraint("list_currency_qty > 0", name="ck_offer_currency_qty"),
        CheckConstraint(
            "discount_pct IS NULL OR (discount_pct >= 0 AND discount_pct <= 100)",
            name="ck_offer_discount",
        ),
        CheckConstraint(
            "min_vip_level IS NULL OR (min_vip_level >= 1 AND min_vip_level <= 25)",
            name="ck_offer_min_vip_level",
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
    # 历史列名 list_currency_qty，实际存储“折后价/组”
    discounted_currency_qty: Mapped[float] = mapped_column(
        "list_currency_qty", Float
    )
    discount_pct: Mapped[float | None] = mapped_column(Float, default=None)
    min_vip_level: Mapped[int | None] = mapped_column(
        Integer, default=None, index=True
    )
    limit_qty: Mapped[int | None] = mapped_column(Integer, default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    shop: Mapped[Shop] = relationship(back_populates="offers")
    resource: Mapped[Resource] = relationship(back_populates="offers")

    @property
    def original_currency_qty(self) -> float | None:
        discount = self.discount_pct or 0.0
        if discount >= 100:
            return None
        return round(self.discounted_currency_qty / (1 - discount / 100), 2)

    @property
    def unit_price(self) -> float:
        if self.resource_qty <= 0:
            return 0.0
        return round(self.discounted_currency_qty / self.resource_qty, 6)


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
    # 历史列：所有箱子现在都按“自选资源”处理，不再对外暴露
    selection_type: Mapped[str] = mapped_column(String(16), default="choose_one")
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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    box_id: Mapped[int] = mapped_column(
        ForeignKey("boxes.id", ondelete="CASCADE"), index=True
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT"), index=True
    )
    qty: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    box: Mapped[Box] = relationship(back_populates="items")
    resource: Mapped[Resource] = relationship(back_populates="box_items")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(64), default="新对话")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'tool')", name="ck_chat_message_role"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    # 仅 assistant 消息使用：OpenAI 格式的 tool_calls JSON
    tool_calls_json: Mapped[str | None] = mapped_column(Text, default=None)
    # 仅 tool 消息使用
    tool_call_id: Mapped[str | None] = mapped_column(String(64), default=None)
    name: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    session: Mapped[ChatSession] = relationship(back_populates="messages")
