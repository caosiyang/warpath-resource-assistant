from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..db import get_db

router = APIRouter(prefix="/api/shop-types", tags=["shop-types"])


@router.get("", response_model=list[schemas.ShopTypeOut])
def list_shop_types(db: Session = Depends(get_db)):
    return db.scalars(
        select(models.ShopType).order_by(
            models.ShopType.sort_order, models.ShopType.name
        )
    ).all()


@router.post("", response_model=schemas.ShopTypeOut, status_code=201)
def create_shop_type(data: schemas.ShopTypeCreate, db: Session = Depends(get_db)):
    return services.create_shop_type(db, data)


@router.get("/{shop_type_id}", response_model=schemas.ShopTypeOut)
def get_shop_type(shop_type_id: int, db: Session = Depends(get_db)):
    shop_type = db.get(models.ShopType, shop_type_id)
    if shop_type is None:
        raise HTTPException(status_code=404, detail="商店类型不存在")
    return shop_type


@router.patch("/{shop_type_id}", response_model=schemas.ShopTypeOut)
def update_shop_type(
    shop_type_id: int, data: schemas.ShopTypeUpdate, db: Session = Depends(get_db)
):
    return services.update_shop_type(db, shop_type_id, data)


@router.delete("/{shop_type_id}", status_code=204)
def delete_shop_type(shop_type_id: int, db: Session = Depends(get_db)):
    services.delete_shop_type(db, shop_type_id)
