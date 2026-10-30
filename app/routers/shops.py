from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..db import get_db

router = APIRouter(prefix="/api/shops", tags=["shops"])


@router.get("", response_model=list[schemas.ShopOut])
def list_shops(db: Session = Depends(get_db)):
    return db.scalars(
        select(models.Shop)
        .join(models.ShopType)
        .order_by(models.ShopType.sort_order, models.ShopType.name)
    ).all()


@router.post("", response_model=schemas.ShopOut, status_code=201)
def create_shop(data: schemas.ShopCreate, db: Session = Depends(get_db)):
    return services.create_shop(db, data)


@router.get("/{shop_id}", response_model=schemas.ShopOut)
def get_shop(shop_id: int, db: Session = Depends(get_db)):
    shop = db.get(models.Shop, shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="商店不存在")
    return shop


@router.patch("/{shop_id}", response_model=schemas.ShopOut)
def update_shop(shop_id: int, data: schemas.ShopUpdate, db: Session = Depends(get_db)):
    return services.update_shop(db, shop_id, data)


@router.delete("/{shop_id}", status_code=204)
def delete_shop(shop_id: int, db: Session = Depends(get_db)):
    services.delete_shop(db, shop_id)


@router.post("/{shop_id}/offers", response_model=schemas.ShopOfferOut, status_code=201)
def add_offer(
    shop_id: int, data: schemas.ShopOfferCreate, db: Session = Depends(get_db)
):
    return services.add_offer(db, shop_id, data)


@router.patch(
    "/{shop_id}/offers/{offer_id}", response_model=schemas.ShopOfferOut
)
def update_offer(
    shop_id: int,
    offer_id: int,
    data: schemas.ShopOfferUpdate,
    db: Session = Depends(get_db),
):
    return services.update_offer(db, shop_id, offer_id, data)


@router.delete("/{shop_id}/offers/{offer_id}", status_code=204)
def delete_offer(shop_id: int, offer_id: int, db: Session = Depends(get_db)):
    services.delete_offer(db, shop_id, offer_id)
