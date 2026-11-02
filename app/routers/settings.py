from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas, services
from ..db import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=schemas.SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return {
        "current_vip_level": services.get_current_vip_level(db),
        "max_vip_level": services.MAX_VIP_LEVEL,
    }


@router.put("", response_model=schemas.SettingsOut)
def update_settings(data: schemas.SettingsUpdate, db: Session = Depends(get_db)):
    services.set_current_vip_level(db, data.current_vip_level)
    return {
        "current_vip_level": services.get_current_vip_level(db),
        "max_vip_level": services.MAX_VIP_LEVEL,
    }
