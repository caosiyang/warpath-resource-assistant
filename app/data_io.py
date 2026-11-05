"""业务数据的 JSON 导入/导出。

仓库里提交的是可读的 JSON 快照，SQLite 数据库只在本机运行。
导出时用名称表达外键，不写数字 ID 和时间戳，保证 diff 稳定。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, services

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_JSON = PROJECT_ROOT / "data" / "warpath-data.json"
DATA_VERSION = 1
CURRENCY_KINDS = ("gold", "token")
PRICING_MODES = ("standard", "vip_tiered")


class DataError(ValueError):
    """数据文件格式或引用错误。"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _num(value: float | int | None):
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _text(item: dict, key: str, *, required: bool = True) -> str | None:
    value = item.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise DataError(f"缺少字段：{key}")
        return None
    if not isinstance(value, str):
        raise DataError(f"字段 {key} 必须是字符串")
    return value.strip()


def _dict_list(payload: dict, key: str) -> list[dict]:
    value = payload.get(key) or []
    if not isinstance(value, list):
        raise DataError(f"{key} 必须是数组")
    for item in value:
        if not isinstance(item, dict):
            raise DataError(f"{key} 里的每一项必须是对象")
    return value


def _check_unique(names: set[str], name: str, label: str) -> None:
    if name in names:
        raise DataError(f"{label}“{name}”重复")
    names.add(name)


def _check_number(
    item: dict, key: str, *, required: bool = True, minimum: float | None = None
) -> float | None:
    value = item.get(key)
    if value is None:
        if required:
            raise DataError(f"缺少字段：{key}")
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DataError(f"字段 {key} 必须是数字")
    if minimum is not None and value < minimum:
        raise DataError(f"字段 {key} 必须大于等于 {minimum}")
    return float(value)


def _check_int(
    item: dict, key: str, *, minimum: int | None = None, maximum: int | None = None
) -> int | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise DataError(f"字段 {key} 必须是整数")
    if minimum is not None and value < minimum:
        raise DataError(f"字段 {key} 必须大于等于 {minimum}")
    if maximum is not None and value > maximum:
        raise DataError(f"字段 {key} 必须小于等于 {maximum}")
    return value


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def export_data(db: Session) -> dict:
    settings = db.get(models.AppSetting, services.CURRENT_VIP_KEY)
    try:
        vip_level = int(settings.value) if settings is not None else services.DEFAULT_VIP_LEVEL
    except (TypeError, ValueError):
        vip_level = services.DEFAULT_VIP_LEVEL

    currencies = db.scalars(
        select(models.Currency).order_by(models.Currency.name)
    ).all()
    resource_types = db.scalars(
        select(models.ResourceType).order_by(
            models.ResourceType.sort_order, models.ResourceType.name
        )
    ).all()
    resources = db.scalars(
        select(models.Resource).order_by(models.Resource.name)
    ).all()
    shop_types = db.scalars(
        select(models.ShopType).order_by(
            models.ShopType.sort_order, models.ShopType.name
        )
    ).all()
    boxes = db.scalars(select(models.Box).order_by(models.Box.name)).all()

    resource_type_names = {item.id: item.name for item in resource_types}
    shop_type_names = {item.id: item.name for item in shop_types}

    exported_shop_types = [
        {
            "name": item.name,
            "currency": item.currency.name if item.currency else None,
            "default_refresh_period": item.default_refresh_period,
            "pricing_mode": item.pricing_mode,
            "sort_order": item.sort_order,
            "is_active": item.is_active,
            "note": item.note,
        }
        for item in shop_types
    ]

    exported_shops = []
    for shop_type in shop_types:
        shop = shop_type.shop
        if shop is None:
            continue
        offers = sorted(
            shop.offers,
            key=lambda offer: (
                offer.resource.name,
                offer.min_vip_level if offer.min_vip_level is not None else 0,
            ),
        )
        exported_shops.append(
            {
                "type": shop_type.name,
                "refresh_period": shop.refresh_period,
                "note": shop.note,
                "offers": [
                    {
                        "resource": offer.resource.name,
                        "resource_qty": _num(offer.resource_qty),
                        "discounted_currency_qty": _num(
                            offer.discounted_currency_qty
                        ),
                        "discount_pct": _num(offer.discount_pct),
                        "min_vip_level": offer.min_vip_level,
                        "limit_qty": offer.limit_qty,
                        "note": offer.note,
                    }
                    for offer in offers
                ],
            }
        )

    exported_boxes = []
    for box in boxes:
        items = sorted(box.items, key=lambda item: item.resource.name)
        exported_boxes.append(
            {
                "name": box.name,
                "note": box.note,
                "items": [
                    {"resource": item.resource.name, "qty": _num(item.qty)}
                    for item in items
                ],
            }
        )

    return {
        "version": DATA_VERSION,
        "settings": {"current_vip_level": vip_level},
        "currencies": [
            {"name": item.name, "kind": item.kind, "note": item.note}
            for item in currencies
        ],
        "resource_types": [
            {
                "name": item.name,
                "sort_order": item.sort_order,
                "note": item.note,
            }
            for item in resource_types
        ],
        "resources": [
            {
                "name": item.name,
                "unit": item.unit,
                "type": resource_type_names.get(item.type_id),
                "note": item.note,
            }
            for item in resources
        ],
        "shop_types": exported_shop_types,
        "shops": exported_shops,
        "boxes": exported_boxes,
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
def _clear_business_data(db: Session) -> None:
    for model in (
        models.BoxItem,
        models.Box,
        models.ShopOffer,
        models.Shop,
        models.ShopType,
        models.Resource,
        models.ResourceType,
        models.Currency,
        models.AppSetting,
    ):
        db.execute(delete(model))
    db.flush()


def import_data(db: Session, payload: dict, *, replace: bool = False) -> dict:
    if not isinstance(payload, dict):
        raise DataError("JSON 顶层必须是对象")
    version = payload.get("version", DATA_VERSION)
    if version != DATA_VERSION:
        raise DataError(f"不支持的数据版本：{version}")

    if replace:
        _clear_business_data(db)
    elif db.scalar(select(models.Currency).limit(1)) is not None:
        raise DataError("数据库已有数据；使用 --replace 覆盖，或先清空数据库")

    counts: dict[str, int] = {}

    # 货币
    currency_objs: dict[str, models.Currency] = {}
    names: set[str] = set()
    for item in _dict_list(payload, "currencies"):
        name = _text(item, "name")
        _check_unique(names, name, "货币")
        kind = item.get("kind", "token")
        if kind not in CURRENCY_KINDS:
            raise DataError(f"货币“{name}”的类型必须是 gold 或 token")
        currency = models.Currency(name=name, kind=kind, note=item.get("note"))
        db.add(currency)
        db.flush()
        currency_objs[name] = currency
    counts["currencies"] = len(currency_objs)

    # 资源类型
    type_objs: dict[str, models.ResourceType] = {}
    names = set()
    for item in _dict_list(payload, "resource_types"):
        name = _text(item, "name")
        _check_unique(names, name, "资源类型")
        sort_order = _check_int(item, "sort_order") or 0
        resource_type = models.ResourceType(
            name=name, sort_order=sort_order, note=item.get("note")
        )
        db.add(resource_type)
        db.flush()
        type_objs[name] = resource_type
    counts["resource_types"] = len(type_objs)

    # 资源
    resource_objs: dict[str, models.Resource] = {}
    names = set()
    for item in _dict_list(payload, "resources"):
        name = _text(item, "name")
        _check_unique(names, name, "资源")
        type_name = _text(item, "type", required=False)
        resource_type = None
        if type_name is not None:
            resource_type = type_objs.get(type_name)
            if resource_type is None:
                raise DataError(f"资源“{name}”引用了不存在的类型：{type_name}")
        unit = item.get("unit") or "1"
        resource = models.Resource(
            name=name,
            unit=str(unit),
            type_id=resource_type.id if resource_type else None,
            note=item.get("note"),
        )
        db.add(resource)
        db.flush()
        resource_objs[name] = resource
    counts["resources"] = len(resource_objs)

    # 商店类型
    shop_type_objs: dict[str, models.ShopType] = {}
    names = set()
    for item in _dict_list(payload, "shop_types"):
        name = _text(item, "name")
        _check_unique(names, name, "商店类型")
        currency_name = _text(item, "currency")
        currency = currency_objs.get(currency_name)
        if currency is None:
            raise DataError(f"商店类型“{name}”引用了不存在的货币：{currency_name}")
        pricing_mode = item.get("pricing_mode", "standard")
        if pricing_mode not in PRICING_MODES:
            raise DataError(f"商店类型“{name}”的定价模式无效：{pricing_mode}")
        shop_type = models.ShopType(
            name=name,
            currency_id=currency.id,
            default_refresh_period=item.get("default_refresh_period"),
            pricing_mode=pricing_mode,
            sort_order=_check_int(item, "sort_order") or 0,
            is_active=bool(item.get("is_active", True)),
            note=item.get("note"),
        )
        db.add(shop_type)
        db.flush()
        shop_type_objs[name] = shop_type
    counts["shop_types"] = len(shop_type_objs)

    # 商店与商品
    shop_count = 0
    offer_count = 0
    shop_names: set[str] = set()
    for item in _dict_list(payload, "shops"):
        type_name = _text(item, "type")
        _check_unique(shop_names, type_name, "商店")
        shop_type = shop_type_objs.get(type_name)
        if shop_type is None:
            raise DataError(f"商店引用了不存在的类型：{type_name}")
        shop = models.Shop(
            shop_type_id=shop_type.id,
            refresh_period=item.get("refresh_period"),
            note=item.get("note"),
        )
        db.add(shop)
        db.flush()
        shop_count += 1

        offer_keys: set[tuple[int, int | None]] = set()
        for raw_offer in item.get("offers") or []:
            if not isinstance(raw_offer, dict):
                raise DataError(f"商店“{type_name}”的商品必须是对象")
            resource_name = _text(raw_offer, "resource")
            resource = resource_objs.get(resource_name)
            if resource is None:
                raise DataError(
                    f"商店“{type_name}”引用了不存在的资源：{resource_name}"
                )
            resource_qty = _check_number(raw_offer, "resource_qty", minimum=0.000001)
            discounted_qty = _check_number(
                raw_offer, "discounted_currency_qty", minimum=0.000001
            )
            discount_pct = _check_number(
                raw_offer, "discount_pct", required=False
            )
            if discount_pct is not None and not 0 <= discount_pct <= 100:
                raise DataError("discount_pct 必须在 0–100 之间")
            min_vip_level = _check_int(
                raw_offer,
                "min_vip_level",
                minimum=1,
                maximum=services.MAX_VIP_LEVEL,
            )
            if shop_type.pricing_mode == "vip_tiered" and min_vip_level is None:
                raise DataError(
                    f"特权商店“{type_name}”的商品必须填写 min_vip_level"
                )
            if shop_type.pricing_mode == "standard" and min_vip_level is not None:
                raise DataError(
                    f"普通商店“{type_name}”的商品不需要 min_vip_level"
                )
            limit_qty = _check_int(raw_offer, "limit_qty", minimum=1)

            key = (resource.id, min_vip_level)
            if key in offer_keys:
                raise DataError(
                    f"商店“{type_name}”里资源“{resource_name}”在 VIP{min_vip_level} 重复"
                )
            offer_keys.add(key)

            db.add(
                models.ShopOffer(
                    shop_id=shop.id,
                    resource_id=resource.id,
                    resource_qty=resource_qty,
                    discounted_currency_qty=discounted_qty,
                    discount_pct=discount_pct,
                    min_vip_level=min_vip_level,
                    limit_qty=limit_qty,
                    note=raw_offer.get("note"),
                )
            )
            offer_count += 1
    counts["shops"] = shop_count
    counts["shop_offers"] = offer_count

    # 箱子
    box_count = 0
    item_count = 0
    box_names: set[str] = set()
    for item in _dict_list(payload, "boxes"):
        name = _text(item, "name")
        _check_unique(box_names, name, "箱子")
        box = models.Box(name=name, note=item.get("note"))
        db.add(box)
        db.flush()
        box_count += 1

        item_keys: set[int] = set()
        for raw_item in item.get("items") or []:
            if not isinstance(raw_item, dict):
                raise DataError(f"箱子“{name}”的资源必须是对象")
            resource_name = _text(raw_item, "resource")
            resource = resource_objs.get(resource_name)
            if resource is None:
                raise DataError(f"箱子“{name}”引用了不存在的资源：{resource_name}")
            qty = _check_number(raw_item, "qty", minimum=0.000001)
            if resource.id in item_keys:
                raise DataError(f"箱子“{name}”里的资源“{resource_name}”重复")
            item_keys.add(resource.id)
            db.add(
                models.BoxItem(
                    box_id=box.id,
                    resource_id=resource.id,
                    qty=qty,
                    note=raw_item.get("note"),
                )
            )
            item_count += 1
    counts["boxes"] = box_count
    counts["box_items"] = item_count

    # 设置
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        raise DataError("settings 必须是对象")
    vip_level = settings.get("current_vip_level", services.DEFAULT_VIP_LEVEL)
    if (
        not isinstance(vip_level, int)
        or isinstance(vip_level, bool)
        or not 1 <= vip_level <= services.MAX_VIP_LEVEL
    ):
        raise DataError(
            f"current_vip_level 必须是 1–{services.MAX_VIP_LEVEL} 的整数"
        )
    db.add(models.AppSetting(key=services.CURRENT_VIP_KEY, value=str(vip_level)))
    counts["settings"] = 1

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DataError(f"数据冲突：{exc.orig}") from exc

    return counts


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def load_data_json(path: Path | str = DEFAULT_DATA_JSON) -> dict:
    path = Path(path)
    if not path.exists():
        raise DataError(f"数据文件不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataError(f"JSON 解析失败：{exc}") from exc
    if not isinstance(payload, dict):
        raise DataError("JSON 顶层必须是对象")
    return payload


def write_data_json(payload: dict, path: Path | str = DEFAULT_DATA_JSON) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def maybe_import_on_startup(db: Session) -> bool:
    """空库且存在数据文件时自动导入；返回是否执行了导入。

    测试环境（WARPATH_SEED=0）跳过，避免把仓库数据灌进测试库。
    """
    if os.environ.get("WARPATH_SEED", "1") == "0":
        return False
    raw_path = os.environ.get("WARPATH_DATA_JSON", str(DEFAULT_DATA_JSON))
    path = Path(raw_path)
    if not path.exists():
        return False
    if db.scalar(select(models.Currency).limit(1)) is not None:
        return False
    import_data(db, load_data_json(path), replace=False)
    return True
