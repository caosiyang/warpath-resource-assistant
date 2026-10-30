from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..db import get_db

router = APIRouter(prefix="/api/boxes", tags=["boxes"])


@router.get("", response_model=list[schemas.BoxOut])
def list_boxes(db: Session = Depends(get_db)):
    return db.scalars(select(models.Box).order_by(models.Box.name)).all()


@router.post("", response_model=schemas.BoxOut, status_code=201)
def create_box(data: schemas.BoxCreate, db: Session = Depends(get_db)):
    return services.create_box(db, data)


@router.get("/{box_id}", response_model=schemas.BoxOut)
def get_box(box_id: int, db: Session = Depends(get_db)):
    box = db.get(models.Box, box_id)
    if box is None:
        raise HTTPException(status_code=404, detail="箱子不存在")
    return box


@router.patch("/{box_id}", response_model=schemas.BoxOut)
def update_box(box_id: int, data: schemas.BoxUpdate, db: Session = Depends(get_db)):
    return services.update_box(db, box_id, data)


@router.delete("/{box_id}", status_code=204)
def delete_box(box_id: int, db: Session = Depends(get_db)):
    services.delete_box(db, box_id)


@router.post("/{box_id}/items", response_model=schemas.BoxItemOut, status_code=201)
def add_box_item(
    box_id: int, data: schemas.BoxItemCreate, db: Session = Depends(get_db)
):
    return services.add_box_item(db, box_id, data)


@router.patch("/{box_id}/items/{item_id}", response_model=schemas.BoxItemOut)
def update_box_item(
    box_id: int,
    item_id: int,
    data: schemas.BoxItemUpdate,
    db: Session = Depends(get_db),
):
    return services.update_box_item(db, box_id, item_id, data)


@router.delete("/{box_id}/items/{item_id}", status_code=204)
def delete_box_item(box_id: int, item_id: int, db: Session = Depends(get_db)):
    services.delete_box_item(db, box_id, item_id)
