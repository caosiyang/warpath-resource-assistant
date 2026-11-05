from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app import models
from app.data_io import (
    DataError,
    export_data,
    import_data,
    load_data_json,
    maybe_import_on_startup,
)
from app.db import SessionLocal

from test_pricing import make_box, make_resource, make_shop, make_shop_type


def build_sample(client):
    part = make_resource(client, "零件")
    ammo = make_resource(client, "弹药")
    gold_type = make_shop_type(client, "特权商店", "黄金", "vip_tiered", "gold")
    make_shop(
        client,
        gold_type,
        [
            {
                "resource_id": part["id"],
                "resource_qty": 30,
                "discounted_currency_qty": 135,
                "discount_pct": 85,
                "min_vip_level": 18,
                "limit_qty": 20,
            },
            {
                "resource_id": ammo["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 1800,
                "discount_pct": 80,
                "min_vip_level": 18,
                "limit_qty": 10,
            },
        ],
    )
    make_box(
        client,
        "陆军资源自选箱",
        [
            {"resource_id": part["id"], "qty": 30},
            {"resource_id": ammo["id"], "qty": 100},
        ],
    )


def test_export_shape_excludes_chat_and_ids(client):
    build_sample(client)
    client.post("/api/chat/sessions", json={"title": "测试会话"})

    with SessionLocal() as db:
        payload = export_data(db)

    assert payload["version"] == 1
    assert payload["settings"]["current_vip_level"] == 18
    assert "chat_sessions" not in payload
    assert "chat_messages" not in payload

    resource = payload["resources"][0]
    assert "id" not in resource
    assert "created_at" not in resource
    assert resource["type"] == "兵卡资源"

    shop = payload["shops"][0]
    assert shop["type"] == "特权商店"
    assert len(shop["offers"]) == 2
    assert "resource_id" not in shop["offers"][0]
    part_offer = next(
        offer for offer in shop["offers"] if offer["resource"] == "零件"
    )
    assert part_offer["resource_qty"] == 30

    assert payload["boxes"][0]["items"][0]["resource"] == "弹药"


def test_export_import_roundtrip_keeps_data(client):
    build_sample(client)

    with SessionLocal() as db:
        payload = export_data(db)
        counts = import_data(db, payload, replace=True)

    assert counts["resources"] == 2
    assert counts["shops"] == 1
    assert counts["shop_offers"] == 2
    assert counts["boxes"] == 1
    assert counts["box_items"] == 2

    with SessionLocal() as db:
        resources = db.scalars(select(models.Resource)).all()
        assert {item.name for item in resources} == {"零件", "弹药"}
        offers = db.scalars(
            select(models.ShopOffer).order_by(models.ShopOffer.resource_id)
        ).all()
        assert len(offers) == 2
        part_offer = next(item for item in offers if item.resource.name == "零件")
        assert part_offer.resource_qty == 30
        assert part_offer.discounted_currency_qty == 135
        assert part_offer.min_vip_level == 18
        box = db.scalars(select(models.Box)).one()
        assert {item.resource.name for item in box.items} == {"零件", "弹药"}


def test_import_refuses_non_empty_database_without_replace(client):
    build_sample(client)

    payload = {
        "version": 1,
        "settings": {"current_vip_level": 20},
        "currencies": [{"name": "黄金", "kind": "gold"}],
        "resource_types": [{"name": "兵卡资源", "sort_order": 0}],
        "resources": [{"name": "零件", "unit": "1", "type": "兵卡资源"}],
        "shop_types": [],
        "shops": [],
        "boxes": [],
    }

    with SessionLocal() as db:
        with pytest.raises(DataError):
            import_data(db, payload, replace=False)

        import_data(db, payload, replace=True)

    with SessionLocal() as db:
        assert len(db.scalars(select(models.Resource)).all()) == 1
        assert db.get(models.AppSetting, "current_vip_level").value == "20"


def test_import_rejects_unknown_reference(client):
    payload = {
        "version": 1,
        "settings": {"current_vip_level": 18},
        "currencies": [{"name": "黄金", "kind": "gold"}],
        "resource_types": [{"name": "兵卡资源", "sort_order": 0}],
        "resources": [{"name": "零件", "unit": "1", "type": "兵卡资源"}],
        "shop_types": [
            {
                "name": "特权商店",
                "currency": "黄金",
                "pricing_mode": "vip_tiered",
            }
        ],
        "shops": [
            {
                "type": "特权商店",
                "offers": [
                    {
                        "resource": "不存在的资源",
                        "resource_qty": 30,
                        "discounted_currency_qty": 135,
                        "min_vip_level": 18,
                    }
                ],
            }
        ],
        "boxes": [],
    }

    with SessionLocal() as db:
        with pytest.raises(DataError, match="不存在的资源"):
            import_data(db, payload, replace=True)


def test_import_validates_vip_tiered_offers(client):
    payload = {
        "version": 1,
        "settings": {"current_vip_level": 18},
        "currencies": [{"name": "黄金", "kind": "gold"}],
        "resource_types": [{"name": "兵卡资源", "sort_order": 0}],
        "resources": [{"name": "零件", "unit": "1", "type": "兵卡资源"}],
        "shop_types": [
            {"name": "特权商店", "currency": "黄金", "pricing_mode": "vip_tiered"}
        ],
        "shops": [
            {
                "type": "特权商店",
                "offers": [
                    {
                        "resource": "零件",
                        "resource_qty": 30,
                        "discounted_currency_qty": 135,
                    }
                ],
            }
        ],
        "boxes": [],
    }

    with SessionLocal() as db:
        with pytest.raises(DataError, match="min_vip_level"):
            import_data(db, payload, replace=True)


def test_replace_keeps_chat_history(client):
    build_sample(client)
    client.post("/api/chat/sessions", json={"title": "要保留的会话"})

    with SessionLocal() as db:
        payload = export_data(db)
        import_data(db, payload, replace=True)

    with SessionLocal() as db:
        assert db.scalars(select(models.ChatSession)).one().title == "要保留的会话"


def test_startup_auto_import(client, tmp_path, monkeypatch):
    payload = {
        "version": 1,
        "settings": {"current_vip_level": 21},
        "currencies": [{"name": "黄金", "kind": "gold"}],
        "resource_types": [{"name": "兵卡资源", "sort_order": 0}],
        "resources": [{"name": "零件", "unit": "1", "type": "兵卡资源"}],
        "shop_types": [],
        "shops": [],
        "boxes": [],
    }
    path = tmp_path / "warpath-data.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setenv("WARPATH_SEED", "1")
    monkeypatch.setenv("WARPATH_DATA_JSON", str(path))

    with SessionLocal() as db:
        assert maybe_import_on_startup(db) is True
        assert maybe_import_on_startup(db) is False
        assert db.get(models.AppSetting, "current_vip_level").value == "21"

    assert load_data_json(path)["settings"]["current_vip_level"] == 21
