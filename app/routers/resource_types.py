from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..db import get_db

router = APIRouter(prefix="/api/resource-types", tags=["resource-types"])


@router.get("", response_model=list[schemas.ResourceTypeOut])
def list_resource_types(db: Session = Depends(get_db)):
    return db.scalars(
        select(models.ResourceType).order_by(
            models.ResourceType.sort_order, models.ResourceType.name
        )
    ).all()


@router.post("", response_model=schemas.ResourceTypeOut, status_code=201)
def create_resource_type(
    data: schemas.ResourceTypeCreate, db: Session = Depends(get_db)
):
    return services.create_resource_type(db, data)


@router.get("/{type_id}", response_model=schemas.ResourceTypeOut)
def get_resource_type(type_id: int, db: Session = Depends(get_db)):
    resource_type = db.get(models.ResourceType, type_id)
    if resource_type is None:
        raise HTTPException(status_code=404, detail="资源类型不存在")
    return resource_type


@router.patch("/{type_id}", response_model=schemas.ResourceTypeOut)
def update_resource_type(
    type_id: int, data: schemas.ResourceTypeUpdate, db: Session = Depends(get_db)
):
    return services.update_resource_type(db, type_id, data)


@router.delete("/{type_id}", status_code=204)
def delete_resource_type(type_id: int, db: Session = Depends(get_db)):
    services.delete_resource_type(db, type_id)
