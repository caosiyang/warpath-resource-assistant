"""资源估值与商店/箱子性价比计算。

所有数字都在这里算，模型只负责调用工具和解释结果。
"""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, services

GOLD_KIND = "gold"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def resolve_vip(db: Session, vip_level: int | None = None) -> int:
    if vip_level is None:
        return services.get_current_vip_level(db)
    if not 1 <= vip_level <= services.MAX_VIP_LEVEL:
        raise ValueError(f"特权等级必须在 1–{services.MAX_VIP_LEVEL} 之间")
    return vip_level


def _all_shops(db: Session) -> list[models.Shop]:
    return list(
        db.scalars(
            select(models.Shop)
            .join(models.ShopType)
            .order_by(models.ShopType.sort_order, models.ShopType.name)
        ).all()
    )


def _all_resources(db: Session) -> list[models.Resource]:
    return list(db.scalars(select(models.Resource).order_by(models.Resource.name)).all())


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _need_tokens(need: str | None) -> list[str]:
    """把“零件:500 / 弹药”拆成资源名关键词。"""
    if not need:
        return []
    tokens: list[str] = []
    for part in re.split(r"[,，、;；\s]+", need):
        name = re.split(r"[:：]", part, maxsplit=1)[0].strip()
        if name:
            tokens.append(name)
    return tokens


def matches_need(need: str | None, resource_name: str) -> bool:
    for token in _need_tokens(need):
        if token == resource_name or token in resource_name or resource_name in token:
            return True
    return False


# ---------------------------------------------------------------------------
# Resource values (GEV)
# ---------------------------------------------------------------------------
def resource_value_map(db: Session, vip_level: int | None = None) -> dict[int, dict]:
    """当前 VIP 下，每个资源在黄金商店里的最低单价（黄金/个）。"""
    vip = resolve_vip(db, vip_level)
    values: dict[int, dict] = {}

    for shop in _all_shops(db):
        if shop.currency.kind != GOLD_KIND:
            continue
        for offer in services.effective_offers(shop, vip):
            unit_price = offer.unit_price
            if unit_price <= 0:
                continue
            current = values.get(offer.resource_id)
            better = current is None or unit_price < current["unit_gev"] - 1e-9
            same_price_better_discount = (
                current is not None
                and abs(unit_price - current["unit_gev"]) <= 1e-9
                and (offer.discount_pct or 0) > (current["discount_pct"] or 0)
            )
            if better or same_price_better_discount:
                values[offer.resource_id] = {
                    "resource_id": offer.resource_id,
                    "name": offer.resource.name,
                    "unit": offer.resource.unit,
                    "unit_gev": round(unit_price, 6),
                    "source_shop": shop.name,
                    "source_shop_id": shop.id,
                    "source_offer_id": offer.id,
                    "discount_pct": offer.discount_pct,
                }
    return values


def build_resource_values(db: Session, vip_level: int | None = None) -> dict:
    vip = resolve_vip(db, vip_level)
    values = resource_value_map(db, vip)
    resources = _all_resources(db)

    priced = sorted(values.values(), key=lambda item: (item["name"], item["resource_id"]))
    unpriced = [
        {"resource_id": resource.id, "name": resource.name, "unit": resource.unit}
        for resource in resources
        if resource.id not in values
    ]
    return {
        "vip_level": vip,
        "base_currency": "黄金",
        "rule": "GEV（黄金等价物）= 当前 VIP 下该资源在黄金商店的最低单价（黄金/个）",
        "priced_count": len(priced),
        "resource_count": len(resources),
        "values": priced,
        "unpriced": unpriced,
    }


# ---------------------------------------------------------------------------
# Currency conversion
# ---------------------------------------------------------------------------
def build_currency_rates(
    db: Session,
    vip_level: int | None = None,
    value_map: dict[int, dict] | None = None,
) -> dict:
    """用同时出现在黄金商店和代币商店里的资源，反推“1 代币 = ? 黄金”。

    没有重叠资源时不做猜测，对应货币不会出现在 rates 里。
    """
    vip = resolve_vip(db, vip_level)
    values = value_map if value_map is not None else resource_value_map(db, vip)

    grouped: dict[str, list[float]] = defaultdict(list)
    sources: dict[str, list[str]] = defaultdict(list)
    for shop in _all_shops(db):
        if shop.currency.kind == GOLD_KIND:
            continue
        for offer in services.effective_offers(shop, vip):
            gev = values.get(offer.resource_id)
            if gev is None or offer.unit_price <= 0:
                continue
            # gold/个 ÷ 代币/个 = gold/代币
            grouped[shop.currency.name].append(gev["unit_gev"] / offer.unit_price)
            sources[shop.currency.name].append(f"{shop.name}·{offer.resource.name}")

    rates = []
    for currency_name, samples in grouped.items():
        rates.append(
            {
                "currency": currency_name,
                "gold_per_unit": round(median(samples), 6),
                "samples": len(samples),
                "min": round(min(samples), 6),
                "max": round(max(samples), 6),
                "sources": sorted(set(sources[currency_name])),
            }
        )
    return {
        "vip_level": vip,
        "rates": sorted(rates, key=lambda item: item["currency"]),
        "note": "只使用同一资源在黄金商店和代币商店的单价反推；没有重叠资源时不估算。",
    }


# ---------------------------------------------------------------------------
# Data status
# ---------------------------------------------------------------------------
def build_data_status(db: Session, vip_level: int | None = None) -> dict:
    vip = resolve_vip(db, vip_level)
    values = resource_value_map(db, vip)
    resources = _all_resources(db)
    shop_types = list(
        db.scalars(
            select(models.ShopType).order_by(models.ShopType.sort_order, models.ShopType.name)
        ).all()
    )
    shops = _all_shops(db)
    boxes = list(db.scalars(select(models.Box).order_by(models.Box.name)).all())

    missing_shops = [shop_type.name for shop_type in shop_types if shop_type.shop is None]
    unpriced = [resource.name for resource in resources if resource.id not in values]

    warnings: list[str] = []
    if unpriced:
        warnings.append(f"{len(unpriced)} 个资源没有黄金价格：" + "、".join(unpriced))
    if missing_shops:
        warnings.append("还没创建商店：" + "、".join(missing_shops))
    if not boxes:
        warnings.append("还没有箱子数据")

    return {
        "vip_level": vip,
        "resources_total": len(resources),
        "resources_priced": len(values),
        "unpriced_resources": unpriced,
        "shop_types_total": len(shop_types),
        "shops_total": len(shops),
        "missing_shops": missing_shops,
        "boxes_total": len(boxes),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------
def list_boxes(db: Session) -> dict:
    boxes = list(db.scalars(select(models.Box).order_by(models.Box.name)).all())
    return {
        "boxes": [
            {
                "id": box.id,
                "name": box.name,
                "note": box.note,
                "items": [
                    {"resource": item.resource.name, "qty": item.qty}
                    for item in box.items
                ],
            }
            for box in boxes
        ]
    }


def evaluate_box(
    db: Session,
    box_id: int,
    vip_level: int | None = None,
    need: str | None = None,
) -> dict:
    vip = resolve_vip(db, vip_level)
    box = db.get(models.Box, box_id)
    if box is None:
        raise ValueError("箱子不存在")
    values = resource_value_map(db, vip)

    options: list[dict] = []
    for item in box.items:
        gev = values.get(item.resource_id)
        unit_gev = gev["unit_gev"] if gev else None
        options.append(
            {
                "resource_id": item.resource_id,
                "resource": item.resource.name,
                "qty": item.qty,
                "unit_gev": unit_gev,
                "value_gev": _round(item.qty * unit_gev) if unit_gev is not None else None,
                "priority": matches_need(need, item.resource.name),
                "priced": unit_gev is not None,
            }
        )

    comparable = [option for option in options if option["value_gev"] is not None]
    best = max(comparable, key=lambda option: option["value_gev"]) if comparable else None
    priority_options = [option for option in comparable if option["priority"]]
    recommended = (
        max(priority_options, key=lambda option: option["value_gev"])
        if priority_options
        else best
    )

    for option in options:
        option["is_best_value"] = best is not None and option is best
        option["is_recommended"] = recommended is not None and option is recommended
        option["delta_vs_best"] = (
            _round(best["value_gev"] - option["value_gev"])
            if best is not None and option["value_gev"] is not None
            else None
        )

    if not options:
        reason = "箱子还没有资源"
    elif recommended is None:
        reason = "箱内资源都没有黄金价格，无法比较"
    elif priority_options and recommended is not best:
        reason = f"按卡点资源「{recommended['resource']}」优先；纯价值最高是「{best['resource']}」"
    elif priority_options:
        reason = f"卡点资源「{recommended['resource']}」正好也是价值最高的"
    else:
        reason = "按纯价值最高推荐"

    return {
        "box": {"id": box.id, "name": box.name, "note": box.note},
        "vip_level": vip,
        "rule": "自选箱只能选择一个资源栈，选项价值 = 数量 × 该资源的 GEV",
        "options": sorted(
            options,
            key=lambda option: (
                not option["is_recommended"],
                -(option["value_gev"] or 0),
            ),
        ),
        "best_value": best,
        "recommended": recommended,
        "recommendation_reason": reason,
        "unpriced_options": [
            option["resource"] for option in options if option["value_gev"] is None
        ],
    }


# ---------------------------------------------------------------------------
# Shops
# ---------------------------------------------------------------------------
def list_shops(db: Session, vip_level: int | None = None) -> dict:
    vip = resolve_vip(db, vip_level)
    shops = []
    for shop in _all_shops(db):
        shops.append(
            {
                "id": shop.id,
                "name": shop.name,
                "currency": shop.currency.name,
                "currency_kind": shop.currency.kind,
                "pricing_mode": shop.shop_type.pricing_mode,
                "refresh_period": shop.refresh_period,
                "offer_count": len(shop.offers),
                "effective_offer_count": len(services.effective_offers(shop, vip)),
            }
        )
    return {"vip_level": vip, "shops": shops}


def evaluate_shop(
    db: Session,
    shop_id: int,
    vip_level: int | None = None,
    need: str | None = None,
) -> dict:
    vip = resolve_vip(db, vip_level)
    shop = db.get(models.Shop, shop_id)
    if shop is None:
        raise ValueError("商店不存在")

    values = resource_value_map(db, vip)
    rates = build_currency_rates(db, vip, value_map=values)
    rate_by_currency = {rate["currency"]: rate for rate in rates["rates"]}
    is_gold = shop.currency.kind == GOLD_KIND
    rate = None if is_gold else rate_by_currency.get(shop.currency.name)
    gold_per_unit = 1.0 if is_gold else (rate["gold_per_unit"] if rate else None)

    offers: list[dict] = []
    for offer in services.effective_offers(shop, vip):
        gev = values.get(offer.resource_id)
        unit_gev = gev["unit_gev"] if gev else None
        value_per_group = (
            offer.resource_qty * unit_gev if unit_gev is not None else None
        )
        cost_gold = (
            offer.discounted_currency_qty * gold_per_unit
            if gold_per_unit is not None
            else None
        )
        limit_qty = offer.limit_qty
        offers.append(
            {
                "offer_id": offer.id,
                "resource_id": offer.resource_id,
                "resource": offer.resource.name,
                "resource_qty": offer.resource_qty,
                "discounted_price": offer.discounted_currency_qty,
                "original_price": offer.original_currency_qty,
                "discount_pct": offer.discount_pct,
                "unit_price": round(offer.unit_price, 6),
                "unit_price_gold": _round(
                    offer.unit_price * gold_per_unit
                    if gold_per_unit is not None
                    else None
                ),
                "unit_gev": unit_gev,
                "limit_qty": limit_qty,
                "max_qty": _round(offer.resource_qty * limit_qty) if limit_qty else None,
                "total_cost": _round(offer.discounted_currency_qty * limit_qty)
                if limit_qty
                else None,
                "value_per_group": _round(value_per_group),
                "total_value": _round(value_per_group * limit_qty)
                if value_per_group is not None and limit_qty
                else None,
                "efficiency": _round(value_per_group / offer.discounted_currency_qty)
                if value_per_group is not None
                else None,
                "efficiency_gold": _round(value_per_group / cost_gold)
                if value_per_group is not None and cost_gold
                else None,
                "is_cheapest_source": bool(
                    gev
                    and gev["source_offer_id"] == offer.id
                    and abs(gev["unit_gev"] - offer.unit_price) <= 1e-9
                ),
                "priority": matches_need(need, offer.resource.name),
                "priced": unit_gev is not None,
            }
        )

    if is_gold:
        def sort_key(item: dict):
            return (
                not item["priority"],
                -(item["discount_pct"] or 0),
                item["unit_price"],
            )
    else:
        def sort_key(item: dict):
            return (
                not item["priority"],
                -(item["efficiency_gold"] or 0),
                -(item["discount_pct"] or 0),
            )

    notes: list[str] = []
    if is_gold:
        notes.append(
            "黄金商店内部 efficiency 接近 1，不能用来跨资源比较；应看折扣、限购和卡点资源。"
        )
    elif rate is None:
        notes.append(
            f"没有资源同时出现在黄金商店和{shop.currency.name}商店，无法反推汇率，只能看折扣。"
        )
    else:
        notes.append(
            f"按重叠资源反推：1 {shop.currency.name} ≈ {rate['gold_per_unit']} 黄金（{rate['samples']} 个样本）。"
        )
    if need:
        notes.append(f"已标记卡点资源：{need}")

    return {
        "shop": {
            "id": shop.id,
            "name": shop.name,
            "currency": shop.currency.name,
            "currency_kind": shop.currency.kind,
            "pricing_mode": shop.shop_type.pricing_mode,
            "refresh_period": shop.refresh_period,
        },
        "vip_level": vip,
        "gold_per_currency_unit": gold_per_unit,
        "offers": sorted(offers, key=sort_key),
        "unpriced_offers": [
            offer["resource"] for offer in offers if not offer["priced"]
        ],
        "notes": notes,
    }
