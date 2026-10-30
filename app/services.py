from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("数据冲突，请检查名称是否重复或是否被引用") from exc


def _get(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise ValueError("记录不存在")
    return obj


def _ensure_unique_name(db: Session, model, name: str, exclude_id: int | None = None) -> None:
    stmt = select(model).where(model.name == name)
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise ValueError(f"名称“{name}”已存在")


def _ensure_resource(db: Session, resource_id: int) -> models.Resource:
    resource = db.get(models.Resource, resource_id)
    if resource is None:
        raise ValueError("资源不存在")
    return resource


def _ensure_currency(db: Session, currency_id: int) -> models.Currency:
    currency = db.get(models.Currency, currency_id)
    if currency is None:
        raise ValueError("货币不存在")
    return currency


def _ensure_shop_type(db: Session, shop_type_id: int) -> models.ShopType:
    shop_type = db.get(models.ShopType, shop_type_id)
    if shop_type is None:
        raise ValueError("商店类型不存在")
    return shop_type


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------
def create_resource(db: Session, data: schemas.ResourceCreate) -> models.Resource:
    _ensure_unique_name(db, models.Resource, data.name)
    obj = models.Resource(**data.model_dump())
    db.add(obj)
    _commit(db)
    db.refresh(obj)
    return obj


def update_resource(db: Session, resource_id: int, data: schemas.ResourceUpdate) -> models.Resource:
    obj = _get(db, models.Resource, resource_id)
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] != obj.name:
        _ensure_unique_name(db, models.Resource, payload["name"], exclude_id=obj.id)
    for key, value in payload.items():
        setattr(obj, key, value)
    _commit(db)
    db.refresh(obj)
    return obj


def delete_resource(db: Session, resource_id: int) -> None:
    obj = _get(db, models.Resource, resource_id)
    used_by_offer = db.scalar(
        select(models.ShopOffer).where(models.ShopOffer.resource_id == obj.id).limit(1)
    )
    used_by_box = db.scalar(
        select(models.BoxItem).where(models.BoxItem.resource_id == obj.id).limit(1)
    )
    if used_by_offer is not None or used_by_box is not None:
        raise ValueError("该资源已被商店或箱子引用，无法删除")
    db.delete(obj)
    _commit(db)


# ---------------------------------------------------------------------------
# Currencies
# ---------------------------------------------------------------------------
def create_currency(db: Session, data: schemas.CurrencyCreate) -> models.Currency:
    _ensure_unique_name(db, models.Currency, data.name)
    obj = models.Currency(**data.model_dump())
    db.add(obj)
    _commit(db)
    db.refresh(obj)
    return obj


def update_currency(db: Session, currency_id: int, data: schemas.CurrencyUpdate) -> models.Currency:
    obj = _get(db, models.Currency, currency_id)
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] != obj.name:
        _ensure_unique_name(db, models.Currency, payload["name"], exclude_id=obj.id)
    for key, value in payload.items():
        setattr(obj, key, value)
    _commit(db)
    db.refresh(obj)
    return obj


def delete_currency(db: Session, currency_id: int) -> None:
    obj = _get(db, models.Currency, currency_id)
    used = db.scalar(
        select(models.ShopType)
        .where(models.ShopType.currency_id == obj.id)
        .limit(1)
    )
    if used is not None:
        raise ValueError("该货币已被商店类型引用，无法删除")
    db.delete(obj)
    _commit(db)


# ---------------------------------------------------------------------------
# Shop types
# ---------------------------------------------------------------------------
def create_shop_type(db: Session, data: schemas.ShopTypeCreate) -> models.ShopType:
    _ensure_unique_name(db, models.ShopType, data.name)
    _ensure_currency(db, data.currency_id)
    obj = models.ShopType(**data.model_dump())
    db.add(obj)
    _commit(db)
    db.refresh(obj)
    return obj


def update_shop_type(
    db: Session, shop_type_id: int, data: schemas.ShopTypeUpdate
) -> models.ShopType:
    obj = _get(db, models.ShopType, shop_type_id)
    payload = data.model_dump(exclude_unset=True)

    if "name" in payload and payload["name"] != obj.name:
        _ensure_unique_name(db, models.ShopType, payload["name"], exclude_id=obj.id)

    if "currency_id" in payload and payload["currency_id"] != obj.currency_id:
        if obj.shop is not None:
            raise ValueError("该商店类型已创建商店，不能修改绑定货币")
        _ensure_currency(db, payload["currency_id"])

    for key, value in payload.items():
        setattr(obj, key, value)
    _commit(db)
    db.refresh(obj)
    return obj


def delete_shop_type(db: Session, shop_type_id: int) -> None:
    obj = _get(db, models.ShopType, shop_type_id)
    if obj.shop is not None:
        raise ValueError("该商店类型已创建商店，无法删除")
    db.delete(obj)
    _commit(db)


# ---------------------------------------------------------------------------
# Shops
# ---------------------------------------------------------------------------
def _validate_offer_resources(db: Session, offers: list[schemas.ShopOfferCreate]) -> None:
    for offer in offers:
        _ensure_resource(db, offer.resource_id)


def create_shop(db: Session, data: schemas.ShopCreate) -> models.Shop:
    shop_type = _ensure_shop_type(db, data.shop_type_id)
    if not shop_type.is_active:
        raise ValueError("该商店类型已停用，无法创建商店")
    if shop_type.shop is not None:
        raise ValueError("该商店类型已创建商店")
    _validate_offer_resources(db, data.offers)

    refresh_period = (
        data.refresh_period
        if data.refresh_period is not None
        else shop_type.default_refresh_period
    )
    shop = models.Shop(
        shop_type_id=shop_type.id,
        refresh_period=refresh_period,
        note=data.note,
    )
    for offer in data.offers:
        shop.offers.append(models.ShopOffer(**offer.model_dump()))
    db.add(shop)
    _commit(db)
    db.refresh(shop)
    return shop


def update_shop(db: Session, shop_id: int, data: schemas.ShopUpdate) -> models.Shop:
    shop = _get(db, models.Shop, shop_id)
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(shop, key, value)
    _commit(db)
    db.refresh(shop)
    return shop


def delete_shop(db: Session, shop_id: int) -> None:
    shop = _get(db, models.Shop, shop_id)
    db.delete(shop)
    _commit(db)


def add_offer(db: Session, shop_id: int, data: schemas.ShopOfferCreate) -> models.ShopOffer:
    shop = _get(db, models.Shop, shop_id)
    _ensure_resource(db, data.resource_id)
    offer = models.ShopOffer(shop_id=shop.id, **data.model_dump())
    db.add(offer)
    _commit(db)
    db.refresh(offer)
    return offer


def update_offer(
    db: Session, shop_id: int, offer_id: int, data: schemas.ShopOfferUpdate
) -> models.ShopOffer:
    offer = _get(db, models.ShopOffer, offer_id)
    if offer.shop_id != shop_id:
        raise ValueError("商品不属于该商店")
    payload = data.model_dump(exclude_unset=True)
    if "resource_id" in payload:
        _ensure_resource(db, payload["resource_id"])
    for key, value in payload.items():
        setattr(offer, key, value)
    _commit(db)
    db.refresh(offer)
    return offer


def delete_offer(db: Session, shop_id: int, offer_id: int) -> None:
    offer = _get(db, models.ShopOffer, offer_id)
    if offer.shop_id != shop_id:
        raise ValueError("商品不属于该商店")
    db.delete(offer)
    _commit(db)


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------
def _validate_box_items(db: Session, items: list[schemas.BoxItemCreate]) -> None:
    seen: set[int] = set()
    for item in items:
        _ensure_resource(db, item.resource_id)
        if item.resource_id in seen:
            raise ValueError("同一箱子不能重复添加同一资源")
        seen.add(item.resource_id)


def create_box(db: Session, data: schemas.BoxCreate) -> models.Box:
    _ensure_unique_name(db, models.Box, data.name)
    _validate_box_items(db, data.items)

    box = models.Box(
        name=data.name,
        size=data.size,
        selection_type=data.selection_type,
        source=data.source,
        note=data.note,
    )
    for item in data.items:
        box.items.append(models.BoxItem(**item.model_dump()))
    db.add(box)
    _commit(db)
    db.refresh(box)
    return box


def update_box(db: Session, box_id: int, data: schemas.BoxUpdate) -> models.Box:
    box = _get(db, models.Box, box_id)
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] != box.name:
        _ensure_unique_name(db, models.Box, payload["name"], exclude_id=box.id)
    for key, value in payload.items():
        setattr(box, key, value)
    _commit(db)
    db.refresh(box)
    return box


def delete_box(db: Session, box_id: int) -> None:
    box = _get(db, models.Box, box_id)
    db.delete(box)
    _commit(db)


def add_box_item(db: Session, box_id: int, data: schemas.BoxItemCreate) -> models.BoxItem:
    box = _get(db, models.Box, box_id)
    _ensure_resource(db, data.resource_id)
    if any(item.resource_id == data.resource_id for item in box.items):
        raise ValueError("该箱子已存在此资源")
    item = models.BoxItem(box_id=box.id, **data.model_dump())
    db.add(item)
    _commit(db)
    db.refresh(item)
    return item


def update_box_item(
    db: Session, box_id: int, item_id: int, data: schemas.BoxItemUpdate
) -> models.BoxItem:
    item = _get(db, models.BoxItem, item_id)
    if item.box_id != box_id:
        raise ValueError("资源不属于该箱子")
    payload = data.model_dump(exclude_unset=True)
    if "resource_id" in payload:
        _ensure_resource(db, payload["resource_id"])
        if any(
            other.resource_id == payload["resource_id"] and other.id != item.id
            for other in item.box.items
        ):
            raise ValueError("该箱子已存在此资源")
    for key, value in payload.items():
        setattr(item, key, value)
    _commit(db)
    db.refresh(item)
    return item


def delete_box_item(db: Session, box_id: int, item_id: int) -> None:
    item = _get(db, models.BoxItem, item_id)
    if item.box_id != box_id:
        raise ValueError("资源不属于该箱子")
    db.delete(item)
    _commit(db)
