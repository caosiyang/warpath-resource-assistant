from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("名称不能为空")
    return value


# ---------------------------------------------------------------------------
# Resource types
# ---------------------------------------------------------------------------
class ResourceTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    sort_order: int = 0
    note: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_name(value)


class ResourceTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    sort_order: int | None = None
    note: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class ResourceTypeBrief(ORMModel):
    id: int
    name: str


class ResourceTypeOut(ORMModel):
    id: int
    name: str
    sort_order: int
    note: str | None
    created_at: datetime
    resource_count: int


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------
class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    unit: str = Field(default="1", max_length=32)
    type_id: int
    note: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_name(value)


class ResourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    unit: str | None = Field(default=None, max_length=32)
    type_id: int | None = None
    note: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class ResourceOut(ORMModel):
    id: int
    name: str
    unit: str
    type_id: int | None
    note: str | None
    created_at: datetime
    resource_type: ResourceTypeBrief | None


# ---------------------------------------------------------------------------
# Currencies
# ---------------------------------------------------------------------------
class CurrencyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    kind: Literal["gold", "token"] = "token"
    note: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_name(value)


class CurrencyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    kind: Literal["gold", "token"] | None = None
    note: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class CurrencyOut(ORMModel):
    id: int
    name: str
    kind: str
    note: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Shop types
# ---------------------------------------------------------------------------
class ShopTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    currency_id: int
    default_refresh_period: str | None = Field(default=None, max_length=32)
    pricing_mode: Literal["standard", "vip_tiered"] = "standard"
    sort_order: int = 0
    is_active: bool = True
    note: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_name(value)


class ShopTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    currency_id: int | None = None
    default_refresh_period: str | None = Field(default=None, max_length=32)
    pricing_mode: Literal["standard", "vip_tiered"] | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    note: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class ShopTypeBrief(ORMModel):
    id: int
    name: str
    pricing_mode: str


class ShopTypeOut(ORMModel):
    id: int
    name: str
    currency_id: int
    default_refresh_period: str | None
    pricing_mode: str
    sort_order: int
    is_active: bool
    note: str | None
    created_at: datetime
    currency: CurrencyOut
    shop_id: int | None = None


# ---------------------------------------------------------------------------
# Shop offers
# ---------------------------------------------------------------------------
class ShopOfferCreate(BaseModel):
    resource_id: int
    resource_qty: float = Field(gt=0)
    discounted_currency_qty: float = Field(gt=0)
    discount_pct: float | None = Field(default=None, ge=0, le=100)
    min_vip_level: int | None = Field(default=None, ge=1, le=25)
    limit_qty: int | None = Field(default=None, ge=1)
    note: str | None = None


class ShopOfferUpdate(BaseModel):
    resource_id: int | None = None
    resource_qty: float | None = Field(default=None, gt=0)
    discounted_currency_qty: float | None = Field(default=None, gt=0)
    discount_pct: float | None = Field(default=None, ge=0, le=100)
    min_vip_level: int | None = Field(default=None, ge=1, le=25)
    limit_qty: int | None = Field(default=None, ge=1)
    note: str | None = None


class ShopOfferOut(ORMModel):
    id: int
    shop_id: int
    resource_id: int
    resource_qty: float
    discounted_currency_qty: float
    original_currency_qty: float | None
    discount_pct: float | None
    min_vip_level: int | None
    limit_qty: int | None
    note: str | None
    created_at: datetime
    unit_price: float
    resource: ResourceOut


# ---------------------------------------------------------------------------
# Shops
# ---------------------------------------------------------------------------
class ShopCreate(BaseModel):
    shop_type_id: int
    refresh_period: str | None = Field(default=None, max_length=32)
    note: str | None = None
    offers: list[ShopOfferCreate] = Field(default_factory=list)


class ShopUpdate(BaseModel):
    refresh_period: str | None = Field(default=None, max_length=32)
    note: str | None = None


class ShopOut(ORMModel):
    id: int
    shop_type_id: int
    name: str
    currency: CurrencyOut
    refresh_period: str | None
    note: str | None
    created_at: datetime
    shop_type: ShopTypeBrief
    offers: list[ShopOfferOut]


# ---------------------------------------------------------------------------
# Box items
# ---------------------------------------------------------------------------
class BoxItemCreate(BaseModel):
    resource_id: int
    qty: float = Field(gt=0)
    note: str | None = None


class BoxItemUpdate(BaseModel):
    resource_id: int | None = None
    qty: float | None = Field(default=None, gt=0)
    note: str | None = None


class BoxItemOut(ORMModel):
    id: int
    box_id: int
    resource_id: int
    qty: float
    note: str | None
    created_at: datetime
    resource: ResourceOut


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------
class BoxCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    note: str | None = None
    items: list[BoxItemCreate] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_name(value)


class BoxUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    note: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class BoxOut(ORMModel):
    id: int
    name: str
    note: str | None
    created_at: datetime
    items: list[BoxItemOut]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class SettingsOut(BaseModel):
    current_vip_level: int
    max_vip_level: int


class SettingsUpdate(BaseModel):
    current_vip_level: int = Field(ge=1, le=25)
