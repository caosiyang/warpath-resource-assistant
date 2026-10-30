from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..db import get_db

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _fmt_num(value) -> str:
    if value is None or value == "":
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    text = f"{number:,.2f}".rstrip("0").rstrip(".")
    return text


templates.env.filters["num"] = _fmt_num

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _render(request: Request, name: str, **context):
    context.setdefault("msg", request.query_params.get("msg"))
    context.setdefault("msg_kind", request.query_params.get("kind", "ok"))
    return templates.TemplateResponse(request, name, context)


def _redirect(url: str, msg: str | None = None, kind: str = "ok") -> RedirectResponse:
    if msg:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}msg={quote(msg)}&kind={kind}"
    return RedirectResponse(url, status_code=303)


def _error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for error in exc.errors():
            loc = ".".join(str(item) for item in error["loc"])
            parts.append(f"{loc}: {error['msg']}")
        return "；".join(parts)
    return str(exc)


def _at(values: list[str], index: int) -> str:
    return values[index] if index < len(values) else ""


def _parse_float(value: str, label: str, errors: list[str]) -> float | None:
    value = (value or "").strip()
    if not value:
        errors.append(f"{label}不能为空")
        return None
    try:
        return float(value)
    except ValueError:
        errors.append(f"{label}必须是数字")
        return None


def _parse_optional_float(value: str, label: str, errors: list[str]) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        errors.append(f"{label}必须是数字")
        return None


def _parse_optional_int(value: str, label: str, errors: list[str]) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        errors.append(f"{label}必须是整数")
        return None


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------
@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    stats = {
        "resources": db.scalar(select(func.count()).select_from(models.Resource)),
        "currencies": db.scalar(select(func.count()).select_from(models.Currency)),
        "shop_types": db.scalar(select(func.count()).select_from(models.ShopType)),
        "shops": db.scalar(select(func.count()).select_from(models.Shop)),
        "offers": db.scalar(select(func.count()).select_from(models.ShopOffer)),
        "boxes": db.scalar(select(func.count()).select_from(models.Box)),
        "box_items": db.scalar(select(func.count()).select_from(models.BoxItem)),
    }
    recent_shops = db.scalars(
        select(models.Shop).order_by(models.Shop.created_at.desc()).limit(5)
    ).all()
    recent_boxes = db.scalars(
        select(models.Box).order_by(models.Box.created_at.desc()).limit(5)
    ).all()
    return _render(
        request,
        "index.html",
        stats=stats,
        recent_shops=recent_shops,
        recent_boxes=recent_boxes,
    )


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------
@router.get("/resources")
def resources_page(request: Request, db: Session = Depends(get_db)):
    items = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()
    return _render(request, "resources/list.html", items=items)


@router.post("/resources")
async def create_resource_page(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    payload = {
        "name": (form.get("name") or "").strip(),
        "unit": (form.get("unit") or "1").strip() or "1",
        "category": (form.get("category") or "").strip() or None,
        "note": (form.get("note") or "").strip() or None,
    }
    try:
        services.create_resource(db, schemas.ResourceCreate(**payload))
    except (ValueError, ValidationError) as exc:
        items = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()
        return _render(
            request,
            "resources/list.html",
            items=items,
            form=payload,
            error=_error_text(exc),
        )
    return _redirect("/resources", "资源已创建")


@router.post("/resources/{resource_id}/delete")
def delete_resource_page(resource_id: int, db: Session = Depends(get_db)):
    try:
        services.delete_resource(db, resource_id)
    except ValueError as exc:
        return _redirect("/resources", _error_text(exc), "error")
    return _redirect("/resources", "资源已删除")


# ---------------------------------------------------------------------------
# Currencies
# ---------------------------------------------------------------------------
@router.get("/currencies")
def currencies_page(request: Request, db: Session = Depends(get_db)):
    items = db.scalars(select(models.Currency).order_by(models.Currency.name)).all()
    return _render(request, "currencies/list.html", items=items)


@router.post("/currencies")
async def create_currency_page(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    payload = {
        "name": (form.get("name") or "").strip(),
        "kind": (form.get("kind") or "token").strip(),
        "note": (form.get("note") or "").strip() or None,
    }
    try:
        services.create_currency(db, schemas.CurrencyCreate(**payload))
    except (ValueError, ValidationError) as exc:
        items = db.scalars(select(models.Currency).order_by(models.Currency.name)).all()
        return _render(
            request,
            "currencies/list.html",
            items=items,
            form=payload,
            error=_error_text(exc),
        )
    return _redirect("/currencies", "货币已创建")


@router.post("/currencies/{currency_id}/delete")
def delete_currency_page(currency_id: int, db: Session = Depends(get_db)):
    try:
        services.delete_currency(db, currency_id)
    except ValueError as exc:
        return _redirect("/currencies", _error_text(exc), "error")
    return _redirect("/currencies", "货币已删除")


# ---------------------------------------------------------------------------
# Shop types
# ---------------------------------------------------------------------------
def _shop_type_form_payload(form) -> dict:
    return {
        "name": (form.get("name") or "").strip(),
        "currency_id": (form.get("currency_id") or "").strip(),
        "default_refresh_period": (form.get("default_refresh_period") or "").strip()
        or None,
        "sort_order": (form.get("sort_order") or "0").strip() or "0",
        "is_active": form.get("is_active") == "on",
        "note": (form.get("note") or "").strip() or None,
    }


def _shop_type_values(payload: dict, errors: list[str]) -> tuple[int, int]:
    if not payload["currency_id"]:
        errors.append("请选择货币")
        currency_id = 0
    else:
        try:
            currency_id = int(payload["currency_id"])
        except ValueError:
            errors.append("货币无效")
            currency_id = 0
    try:
        sort_order = int(payload["sort_order"])
    except ValueError:
        errors.append("排序必须是整数")
        sort_order = 0
    return currency_id, sort_order


@router.get("/shop-types")
def shop_types_page(request: Request, db: Session = Depends(get_db)):
    items = db.scalars(
        select(models.ShopType).order_by(
            models.ShopType.sort_order, models.ShopType.name
        )
    ).all()
    currencies = db.scalars(select(models.Currency).order_by(models.Currency.name)).all()
    return _render(
        request,
        "shop_types/list.html",
        items=items,
        currencies=currencies,
        form={},
    )


@router.post("/shop-types")
async def create_shop_type_page(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    payload = _shop_type_form_payload(form)
    errors: list[str] = []
    currency_id, sort_order = _shop_type_values(payload, errors)

    if errors:
        items = db.scalars(
            select(models.ShopType).order_by(
                models.ShopType.sort_order, models.ShopType.name
            )
        ).all()
        currencies = db.scalars(
            select(models.Currency).order_by(models.Currency.name)
        ).all()
        return _render(
            request,
            "shop_types/list.html",
            items=items,
            currencies=currencies,
            form=payload,
            error="；".join(errors),
        )

    try:
        services.create_shop_type(
            db,
            schemas.ShopTypeCreate(
                name=payload["name"],
                currency_id=currency_id,
                default_refresh_period=payload["default_refresh_period"],
                sort_order=sort_order,
                is_active=payload["is_active"],
                note=payload["note"],
            ),
        )
    except (ValueError, ValidationError) as exc:
        items = db.scalars(
            select(models.ShopType).order_by(
                models.ShopType.sort_order, models.ShopType.name
            )
        ).all()
        currencies = db.scalars(
            select(models.Currency).order_by(models.Currency.name)
        ).all()
        return _render(
            request,
            "shop_types/list.html",
            items=items,
            currencies=currencies,
            form=payload,
            error=_error_text(exc),
        )
    return _redirect("/shop-types", "商店类型已创建")


@router.get("/shop-types/{shop_type_id}/edit")
def shop_type_edit_page(
    shop_type_id: int, request: Request, db: Session = Depends(get_db)
):
    shop_type = db.get(models.ShopType, shop_type_id)
    if shop_type is None:
        raise HTTPException(status_code=404, detail="商店类型不存在")
    currencies = db.scalars(select(models.Currency).order_by(models.Currency.name)).all()
    return _render(
        request,
        "shop_types/edit.html",
        shop_type=shop_type,
        currencies=currencies,
        form={},
    )


@router.post("/shop-types/{shop_type_id}/edit")
async def shop_type_edit_submit(
    shop_type_id: int, request: Request, db: Session = Depends(get_db)
):
    form = await request.form()
    shop_type = db.get(models.ShopType, shop_type_id)
    if shop_type is None:
        raise HTTPException(status_code=404, detail="商店类型不存在")
    currencies = db.scalars(select(models.Currency).order_by(models.Currency.name)).all()

    payload = _shop_type_form_payload(form)
    errors: list[str] = []
    currency_id, sort_order = _shop_type_values(payload, errors)

    if errors:
        return _render(
            request,
            "shop_types/edit.html",
            shop_type=shop_type,
            currencies=currencies,
            form=payload,
            error="；".join(errors),
        )

    try:
        services.update_shop_type(
            db,
            shop_type_id,
            schemas.ShopTypeUpdate(
                name=payload["name"],
                currency_id=currency_id,
                default_refresh_period=payload["default_refresh_period"],
                sort_order=sort_order,
                is_active=payload["is_active"],
                note=payload["note"],
            ),
        )
    except (ValueError, ValidationError) as exc:
        return _render(
            request,
            "shop_types/edit.html",
            shop_type=shop_type,
            currencies=currencies,
            form=payload,
            error=_error_text(exc),
        )
    return _redirect("/shop-types", "商店类型已更新")


@router.post("/shop-types/{shop_type_id}/delete")
def delete_shop_type_page(shop_type_id: int, db: Session = Depends(get_db)):
    try:
        services.delete_shop_type(db, shop_type_id)
    except ValueError as exc:
        return _redirect("/shop-types", _error_text(exc), "error")
    return _redirect("/shop-types", "商店类型已删除")


# ---------------------------------------------------------------------------
# Shops
# ---------------------------------------------------------------------------
def _available_shop_types(db: Session):
    return db.scalars(
        select(models.ShopType)
        .outerjoin(models.Shop, models.Shop.shop_type_id == models.ShopType.id)
        .where(models.ShopType.is_active.is_(True), models.Shop.id.is_(None))
        .order_by(models.ShopType.sort_order, models.ShopType.name)
    ).all()


@router.get("/shops")
def shops_page(request: Request, db: Session = Depends(get_db)):
    items = db.scalars(select(models.Shop).order_by(models.Shop.created_at.desc())).all()
    return _render(request, "shops/list.html", items=items)


@router.get("/shops/new")
def shop_new_page(request: Request, db: Session = Depends(get_db)):
    shop_types = _available_shop_types(db)
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()
    return _render(
        request,
        "shops/form.html",
        shop_types=shop_types,
        resources=resources,
        form={},
        initial_offers=[],
    )


@router.post("/shops")
async def create_shop_page(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    shop_types = _available_shop_types(db)
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()

    shop_type_id = (form.get("shop_type_id") or "").strip()
    refresh_period = (form.get("refresh_period") or "").strip() or None
    note = (form.get("note") or "").strip() or None

    errors: list[str] = []
    if not shop_type_id:
        errors.append("请选择商店类型")

    offer_rows: list[dict[str, str]] = []
    offers: list[schemas.ShopOfferCreate] = []
    resource_ids = form.getlist("resource_id")
    resource_qtys = form.getlist("resource_qty")
    list_costs = form.getlist("list_currency_qty")
    discounts = form.getlist("discount_pct")
    limits = form.getlist("limit_qty")

    for index, resource_id in enumerate(resource_ids):
        row = {
            "resource_id": resource_id,
            "resource_qty": _at(resource_qtys, index),
            "list_currency_qty": _at(list_costs, index),
            "discount_pct": _at(discounts, index),
            "limit_qty": _at(limits, index),
        }
        if not any(value.strip() for value in row.values()):
            continue
        offer_rows.append(row)
        row_errors: list[str] = []
        if not resource_id:
            row_errors.append(f"第 {index + 1} 行未选择资源")
        resource_qty = _parse_float(row["resource_qty"], f"第 {index + 1} 行资源数量", row_errors)
        list_cost = _parse_float(
            row["list_currency_qty"], f"第 {index + 1} 行货币数量", row_errors
        )
        discount = _parse_optional_float(
            row["discount_pct"], f"第 {index + 1} 行折扣", row_errors
        )
        limit = _parse_optional_int(row["limit_qty"], f"第 {index + 1} 行限购", row_errors)
        if row_errors:
            errors.extend(row_errors)
            continue
        offers.append(
            schemas.ShopOfferCreate(
                resource_id=int(resource_id),
                resource_qty=resource_qty,
                list_currency_qty=list_cost,
                discount_pct=discount,
                limit_qty=limit,
            )
        )

    if errors:
        return _render(
            request,
            "shops/form.html",
            shop_types=shop_types,
            resources=resources,
            form={
                "shop_type_id": shop_type_id,
                "refresh_period": refresh_period or "",
                "note": note or "",
            },
            initial_offers=offer_rows,
            error="；".join(errors),
        )

    try:
        shop = services.create_shop(
            db,
            schemas.ShopCreate(
                shop_type_id=int(shop_type_id),
                refresh_period=refresh_period,
                note=note,
                offers=offers,
            ),
        )
    except (ValueError, ValidationError) as exc:
        return _render(
            request,
            "shops/form.html",
            shop_types=shop_types,
            resources=resources,
            form={
                "shop_type_id": shop_type_id,
                "refresh_period": refresh_period or "",
                "note": note or "",
            },
            initial_offers=offer_rows,
            error=_error_text(exc),
        )
    return _redirect(f"/shops/{shop.id}", "商店已创建")


@router.get("/shops/{shop_id}")
def shop_detail_page(shop_id: int, request: Request, db: Session = Depends(get_db)):
    shop = db.get(models.Shop, shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="商店不存在")
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()
    return _render(request, "shops/detail.html", shop=shop, resources=resources)


@router.get("/shops/{shop_id}/edit")
def shop_edit_page(shop_id: int, request: Request, db: Session = Depends(get_db)):
    shop = db.get(models.Shop, shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="商店不存在")
    return _render(request, "shops/edit.html", shop=shop, form={})


@router.post("/shops/{shop_id}/edit")
async def shop_edit_submit(
    shop_id: int, request: Request, db: Session = Depends(get_db)
):
    form = await request.form()
    shop = db.get(models.Shop, shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="商店不存在")

    refresh_period = (form.get("refresh_period") or "").strip() or None
    note = (form.get("note") or "").strip() or None
    try:
        services.update_shop(
            db,
            shop_id,
            schemas.ShopUpdate(refresh_period=refresh_period, note=note),
        )
    except (ValueError, ValidationError) as exc:
        return _render(
            request,
            "shops/edit.html",
            shop=shop,
            form={"refresh_period": refresh_period or "", "note": note or ""},
            error=_error_text(exc),
        )
    return _redirect(f"/shops/{shop_id}", "商店已更新")


@router.get("/shops/{shop_id}/offers/{offer_id}/edit")
def offer_edit_page(
    shop_id: int, offer_id: int, request: Request, db: Session = Depends(get_db)
):
    shop = db.get(models.Shop, shop_id)
    offer = db.get(models.ShopOffer, offer_id)
    if shop is None or offer is None or offer.shop_id != shop_id:
        raise HTTPException(status_code=404, detail="商品不存在")
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()
    return _render(
        request,
        "shops/offer_form.html",
        shop=shop,
        offer=offer,
        resources=resources,
        form={},
    )


@router.post("/shops/{shop_id}/offers/{offer_id}/edit")
async def offer_edit_submit(
    shop_id: int, offer_id: int, request: Request, db: Session = Depends(get_db)
):
    form = await request.form()
    shop = db.get(models.Shop, shop_id)
    offer = db.get(models.ShopOffer, offer_id)
    if shop is None or offer is None or offer.shop_id != shop_id:
        raise HTTPException(status_code=404, detail="商品不存在")
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()

    errors: list[str] = []
    resource_id = (form.get("resource_id") or "").strip()
    if not resource_id:
        errors.append("请选择资源")
    resource_qty = _parse_float(form.get("resource_qty") or "", "资源数量", errors)
    list_cost = _parse_float(form.get("list_currency_qty") or "", "货币数量", errors)
    discount = _parse_optional_float(form.get("discount_pct") or "", "折扣", errors)
    limit = _parse_optional_int(form.get("limit_qty") or "", "限购", errors)

    if errors:
        return _render(
            request,
            "shops/offer_form.html",
            shop=shop,
            offer=offer,
            resources=resources,
            form={
                "resource_id": resource_id,
                "resource_qty": form.get("resource_qty") or "",
                "list_currency_qty": form.get("list_currency_qty") or "",
                "discount_pct": form.get("discount_pct") or "",
                "limit_qty": form.get("limit_qty") or "",
            },
            error="；".join(errors),
        )

    try:
        services.update_offer(
            db,
            shop_id,
            offer_id,
            schemas.ShopOfferUpdate(
                resource_id=int(resource_id),
                resource_qty=resource_qty,
                list_currency_qty=list_cost,
                discount_pct=discount,
                limit_qty=limit,
            ),
        )
    except (ValueError, ValidationError) as exc:
        return _render(
            request,
            "shops/offer_form.html",
            shop=shop,
            offer=offer,
            resources=resources,
            form={
                "resource_id": resource_id,
                "resource_qty": form.get("resource_qty") or "",
                "list_currency_qty": form.get("list_currency_qty") or "",
                "discount_pct": form.get("discount_pct") or "",
                "limit_qty": form.get("limit_qty") or "",
            },
            error=_error_text(exc),
        )
    return _redirect(f"/shops/{shop_id}", "商品已更新")


@router.post("/shops/{shop_id}/offers")
async def add_offer_page(shop_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    errors: list[str] = []
    resource_id = (form.get("resource_id") or "").strip()
    if not resource_id:
        errors.append("请选择资源")
    resource_qty = _parse_float(form.get("resource_qty") or "", "资源数量", errors)
    list_cost = _parse_float(form.get("list_currency_qty") or "", "货币数量", errors)
    discount = _parse_optional_float(form.get("discount_pct") or "", "折扣", errors)
    limit = _parse_optional_int(form.get("limit_qty") or "", "限购", errors)
    if errors:
        return _redirect(f"/shops/{shop_id}", "；".join(errors), "error")
    try:
        services.add_offer(
            db,
            shop_id,
            schemas.ShopOfferCreate(
                resource_id=int(resource_id),
                resource_qty=resource_qty,
                list_currency_qty=list_cost,
                discount_pct=discount,
                limit_qty=limit,
            ),
        )
    except (ValueError, ValidationError) as exc:
        return _redirect(f"/shops/{shop_id}", _error_text(exc), "error")
    return _redirect(f"/shops/{shop_id}", "商品已添加")


@router.post("/shops/{shop_id}/offers/{offer_id}/delete")
def delete_offer_page(shop_id: int, offer_id: int, db: Session = Depends(get_db)):
    try:
        services.delete_offer(db, shop_id, offer_id)
    except ValueError as exc:
        return _redirect(f"/shops/{shop_id}", _error_text(exc), "error")
    return _redirect(f"/shops/{shop_id}", "商品已删除")


@router.post("/shops/{shop_id}/delete")
def delete_shop_page(shop_id: int, db: Session = Depends(get_db)):
    try:
        services.delete_shop(db, shop_id)
    except ValueError as exc:
        return _redirect("/shops", _error_text(exc), "error")
    return _redirect("/shops", "商店已删除")


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------
@router.get("/boxes")
def boxes_page(request: Request, db: Session = Depends(get_db)):
    items = db.scalars(select(models.Box).order_by(models.Box.created_at.desc())).all()
    return _render(request, "boxes/list.html", items=items)


@router.get("/boxes/new")
def box_new_page(request: Request, db: Session = Depends(get_db)):
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()
    return _render(
        request,
        "boxes/form.html",
        resources=resources,
        form={},
        initial_items=[],
    )


@router.post("/boxes")
async def create_box_page(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()

    name = (form.get("name") or "").strip()
    size = (form.get("size") or "").strip() or None
    selection_type = (form.get("selection_type") or "choose_one").strip()
    source = (form.get("source") or "").strip() or None
    note = (form.get("note") or "").strip() or None

    errors: list[str] = []
    if not name:
        errors.append("箱子名称不能为空")

    item_rows: list[dict[str, str]] = []
    items: list[schemas.BoxItemCreate] = []
    resource_ids = form.getlist("resource_id")
    quantities = form.getlist("qty")
    probabilities = form.getlist("probability")

    for index, resource_id in enumerate(resource_ids):
        row = {
            "resource_id": resource_id,
            "qty": _at(quantities, index),
            "probability": _at(probabilities, index),
        }
        if not any(value.strip() for value in row.values()):
            continue
        item_rows.append(row)
        row_errors: list[str] = []
        if not resource_id:
            row_errors.append(f"第 {index + 1} 行未选择资源")
        qty = _parse_float(row["qty"], f"第 {index + 1} 行数量", row_errors)
        probability = _parse_optional_float(
            row["probability"], f"第 {index + 1} 行概率", row_errors
        )
        if row_errors:
            errors.extend(row_errors)
            continue
        items.append(
            schemas.BoxItemCreate(
                resource_id=int(resource_id),
                qty=qty,
                probability=probability,
            )
        )

    if errors:
        return _render(
            request,
            "boxes/form.html",
            resources=resources,
            form={
                "name": name,
                "size": size or "",
                "selection_type": selection_type,
                "source": source or "",
                "note": note or "",
            },
            initial_items=item_rows,
            error="；".join(errors),
        )

    try:
        box = services.create_box(
            db,
            schemas.BoxCreate(
                name=name,
                size=size,
                selection_type=selection_type,
                source=source,
                note=note,
                items=items,
            ),
        )
    except (ValueError, ValidationError) as exc:
        return _render(
            request,
            "boxes/form.html",
            resources=resources,
            form={
                "name": name,
                "size": size or "",
                "selection_type": selection_type,
                "source": source or "",
                "note": note or "",
            },
            initial_items=item_rows,
            error=_error_text(exc),
        )
    return _redirect(f"/boxes/{box.id}", "箱子已创建")


@router.get("/boxes/{box_id}")
def box_detail_page(box_id: int, request: Request, db: Session = Depends(get_db)):
    box = db.get(models.Box, box_id)
    if box is None:
        raise HTTPException(status_code=404, detail="箱子不存在")
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()
    return _render(request, "boxes/detail.html", box=box, resources=resources)


@router.get("/boxes/{box_id}/items/{item_id}/edit")
def box_item_edit_page(
    box_id: int, item_id: int, request: Request, db: Session = Depends(get_db)
):
    box = db.get(models.Box, box_id)
    item = db.get(models.BoxItem, item_id)
    if box is None or item is None or item.box_id != box_id:
        raise HTTPException(status_code=404, detail="资源不存在")
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()
    return _render(
        request,
        "boxes/item_form.html",
        box=box,
        item=item,
        resources=resources,
        form={},
    )


@router.post("/boxes/{box_id}/items/{item_id}/edit")
async def box_item_edit_submit(
    box_id: int, item_id: int, request: Request, db: Session = Depends(get_db)
):
    form = await request.form()
    box = db.get(models.Box, box_id)
    item = db.get(models.BoxItem, item_id)
    if box is None or item is None or item.box_id != box_id:
        raise HTTPException(status_code=404, detail="资源不存在")
    resources = db.scalars(select(models.Resource).order_by(models.Resource.name)).all()

    errors: list[str] = []
    resource_id = (form.get("resource_id") or "").strip()
    if not resource_id:
        errors.append("请选择资源")
    qty = _parse_float(form.get("qty") or "", "数量", errors)
    probability = _parse_optional_float(form.get("probability") or "", "概率", errors)

    form_values = {
        "resource_id": resource_id,
        "qty": form.get("qty") or "",
        "probability": form.get("probability") or "",
    }

    if errors:
        return _render(
            request,
            "boxes/item_form.html",
            box=box,
            item=item,
            resources=resources,
            form=form_values,
            error="；".join(errors),
        )

    try:
        services.update_box_item(
            db,
            box_id,
            item_id,
            schemas.BoxItemUpdate(
                resource_id=int(resource_id),
                qty=qty,
                probability=probability,
            ),
        )
    except (ValueError, ValidationError) as exc:
        return _render(
            request,
            "boxes/item_form.html",
            box=box,
            item=item,
            resources=resources,
            form=form_values,
            error=_error_text(exc),
        )
    return _redirect(f"/boxes/{box_id}", "资源已更新")


@router.post("/boxes/{box_id}/items")
async def add_box_item_page(box_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    errors: list[str] = []
    resource_id = (form.get("resource_id") or "").strip()
    if not resource_id:
        errors.append("请选择资源")
    qty = _parse_float(form.get("qty") or "", "数量", errors)
    probability = _parse_optional_float(form.get("probability") or "", "概率", errors)
    if errors:
        return _redirect(f"/boxes/{box_id}", "；".join(errors), "error")
    try:
        services.add_box_item(
            db,
            box_id,
            schemas.BoxItemCreate(
                resource_id=int(resource_id),
                qty=qty,
                probability=probability,
            ),
        )
    except (ValueError, ValidationError) as exc:
        return _redirect(f"/boxes/{box_id}", _error_text(exc), "error")
    return _redirect(f"/boxes/{box_id}", "资源已添加")


@router.post("/boxes/{box_id}/items/{item_id}/delete")
def delete_box_item_page(box_id: int, item_id: int, db: Session = Depends(get_db)):
    try:
        services.delete_box_item(db, box_id, item_id)
    except ValueError as exc:
        return _redirect(f"/boxes/{box_id}", _error_text(exc), "error")
    return _redirect(f"/boxes/{box_id}", "资源已删除")


@router.post("/boxes/{box_id}/delete")
def delete_box_page(box_id: int, db: Session = Depends(get_db)):
    try:
        services.delete_box(db, box_id)
    except ValueError as exc:
        return _redirect("/boxes", _error_text(exc), "error")
    return _redirect("/boxes", "箱子已删除")
