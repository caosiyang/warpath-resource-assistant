from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

DEFAULT_CURRENCIES = [
    ("黄金", "gold"),
    ("战役币", "token"),
    ("联盟贡献币", "token"),
]

DEFAULT_RESOURCE_TYPES = [
    ("基础资源", 1),
    ("稀有资源", 2),
    ("兵卡资源", 3),
]

DEFAULT_RESOURCES = [
    ("食物", "1", "基础资源"),
    ("木材", "1", "基础资源"),
    ("钢铁", "1", "基础资源"),
    ("石油", "1", "基础资源"),
    ("合金", "1", "稀有资源"),
]

# (商店名称, 货币名称, 默认刷新周期, 排序, 定价模式)
DEFAULT_SHOP_TYPES = [
    ("特权商店", "黄金", "1周", 1, "vip_tiered"),
    ("联盟商店", "联盟贡献币", "3天", 2, "standard"),
    ("战役商店", "战役币", "7天", 3, "standard"),
]


def seed(db: Session) -> None:
    if os.environ.get("WARPATH_SEED", "1") == "0":
        return

    if db.scalar(select(models.Currency).limit(1)) is None:
        for name, kind in DEFAULT_CURRENCIES:
            db.add(models.Currency(name=name, kind=kind))
        db.flush()

    if db.scalar(select(models.ResourceType).limit(1)) is None:
        for name, sort_order in DEFAULT_RESOURCE_TYPES:
            db.add(models.ResourceType(name=name, sort_order=sort_order))
        db.flush()

    if db.scalar(select(models.Resource).limit(1)) is None:
        resource_types = {
            resource_type.name: resource_type
            for resource_type in db.scalars(select(models.ResourceType)).all()
        }
        for name, unit, type_name in DEFAULT_RESOURCES:
            resource_type = resource_types.get(type_name)
            if resource_type is None:
                resource_type = models.ResourceType(name=type_name, sort_order=0)
                db.add(resource_type)
                db.flush()
                resource_types[type_name] = resource_type
            db.add(
                models.Resource(name=name, unit=unit, type_id=resource_type.id)
            )

    if db.scalar(select(models.ShopType).limit(1)) is None:
        currencies = {
            currency.name: currency
            for currency in db.scalars(select(models.Currency)).all()
        }
        for name, currency_name, refresh_period, sort_order, pricing_mode in DEFAULT_SHOP_TYPES:
            currency = currencies.get(currency_name)
            if currency is None:
                continue
            db.add(
                models.ShopType(
                    name=name,
                    currency_id=currency.id,
                    default_refresh_period=refresh_period,
                    pricing_mode=pricing_mode,
                    sort_order=sort_order,
                    is_active=True,
                )
            )

    if db.get(models.AppSetting, "current_vip_level") is None:
        db.add(models.AppSetting(key="current_vip_level", value="18"))

    db.commit()
