from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..db import get_db

router = APIRouter(prefix="/api/currencies", tags=["currencies"])


@router.get("", response_model=list[schemas.CurrencyOut])
def list_currencies(db: Session = Depends(get_db)):
    return db.scalars(select(models.Currency).order_by(models.Currency.name)).all()


@router.post("", response_model=schemas.CurrencyOut, status_code=201)
def create_currency(data: schemas.CurrencyCreate, db: Session = Depends(get_db)):
    return services.create_currency(db, data)


@router.get("/{currency_id}", response_model=schemas.CurrencyOut)
def get_currency(currency_id: int, db: Session = Depends(get_db)):
    currency = db.get(models.Currency, currency_id)
    if currency is None:
        raise HTTPException(status_code=404, detail="货币不存在")
    return currency


@router.patch("/{currency_id}", response_model=schemas.CurrencyOut)
def update_currency(
    currency_id: int, data: schemas.CurrencyUpdate, db: Session = Depends(get_db)
):
    return services.update_currency(db, currency_id, data)


@router.delete("/{currency_id}", status_code=204)
def delete_currency(currency_id: int, db: Session = Depends(get_db)):
    services.delete_currency(db, currency_id)
