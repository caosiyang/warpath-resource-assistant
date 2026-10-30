from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, services
from ..db import get_db

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("", response_model=list[schemas.ResourceOut])
def list_resources(db: Session = Depends(get_db)):
    return db.scalars(select(models.Resource).order_by(models.Resource.name)).all()


@router.post("", response_model=schemas.ResourceOut, status_code=201)
def create_resource(data: schemas.ResourceCreate, db: Session = Depends(get_db)):
    return services.create_resource(db, data)


@router.get("/{resource_id}", response_model=schemas.ResourceOut)
def get_resource(resource_id: int, db: Session = Depends(get_db)):
    resource = db.get(models.Resource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="资源不存在")
    return resource


@router.patch("/{resource_id}", response_model=schemas.ResourceOut)
def update_resource(
    resource_id: int, data: schemas.ResourceUpdate, db: Session = Depends(get_db)
):
    return services.update_resource(db, resource_id, data)


@router.delete("/{resource_id}", status_code=204)
def delete_resource(resource_id: int, db: Session = Depends(get_db)):
    services.delete_resource(db, resource_id)
