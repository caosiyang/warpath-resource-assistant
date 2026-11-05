from __future__ import annotations

from app import pricing
from app.db import SessionLocal


def make_currency(client, name, kind):
    response = client.post("/api/currencies", json={"name": name, "kind": kind})
    assert response.status_code == 201, response.text
    return response.json()


def make_resource(client, name="零件"):
    types = client.get("/api/resource-types").json()
    type_id = types[0]["id"] if types else None
    if type_id is None:
        response = client.post(
            "/api/resource-types", json={"name": "兵卡资源", "sort_order": 1}
        )
        assert response.status_code == 201, response.text
        type_id = response.json()["id"]
    response = client.post(
        "/api/resources", json={"name": name, "unit": "1", "type_id": type_id}
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_shop_type(client, name, currency_name, pricing_mode="standard", kind="token"):
    currency = make_currency(client, currency_name, kind)
    response = client.post(
        "/api/shop-types",
        json={
            "name": name,
            "currency_id": currency["id"],
            "pricing_mode": pricing_mode,
            "sort_order": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_shop(client, shop_type, offers):
    response = client.post(
        "/api/shops",
        json={"shop_type_id": shop_type["id"], "offers": offers},
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_box(client, name, items):
    response = client.post("/api/boxes", json={"name": name, "items": items})
    assert response.status_code == 201, response.text
    return response.json()


def test_resource_values_and_box(client):
    part = make_resource(client, "零件")
    ammo = make_resource(client, "弹药")
    shop_type = make_shop_type(client, "特权商店", "黄金", "vip_tiered", "gold")
    shop = make_shop(
        client,
        shop_type,
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
    box = make_box(
        client,
        "陆军资源自选箱",
        [
            {"resource_id": part["id"], "qty": 30},
            {"resource_id": ammo["id"], "qty": 100},
        ],
    )

    with SessionLocal() as db:
        values = pricing.build_resource_values(db, 18)
        assert values["priced_count"] == 2
        by_name = {item["name"]: item for item in values["values"]}
        assert by_name["零件"]["unit_gev"] == 4.5
        assert by_name["弹药"]["unit_gev"] == 1.8
        assert by_name["零件"]["source_offer_id"] == shop["offers"][0]["id"]

        result = pricing.evaluate_box(db, box["id"], 18)
        assert result["recommended"]["resource"] == "弹药"
        assert result["recommended"]["value_gev"] == 180
        assert result["best_value"]["resource"] == "弹药"
        parts = {item["resource"]: item for item in result["options"]}
        assert parts["零件"]["value_gev"] == 135
        assert parts["零件"]["delta_vs_best"] == 45
        assert result["recommendation_reason"] == "按纯价值最高推荐"


def test_box_need_priority(client):
    part = make_resource(client, "零件")
    ammo = make_resource(client, "弹药")
    shop_type = make_shop_type(client, "特权商店", "黄金", "vip_tiered", "gold")
    make_shop(
        client,
        shop_type,
        [
            {
                "resource_id": part["id"],
                "resource_qty": 30,
                "discounted_currency_qty": 135,
                "discount_pct": 85,
                "min_vip_level": 18,
            },
            {
                "resource_id": ammo["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 1800,
                "discount_pct": 80,
                "min_vip_level": 18,
            },
        ],
    )
    box = make_box(
        client,
        "陆军资源自选箱",
        [
            {"resource_id": part["id"], "qty": 30},
            {"resource_id": ammo["id"], "qty": 100},
        ],
    )

    with SessionLocal() as db:
        result = pricing.evaluate_box(db, box["id"], 18, need="缺 500 零件")
        assert result["recommended"]["resource"] == "零件"
        assert result["best_value"]["resource"] == "弹药"
        assert "卡点资源" in result["recommendation_reason"]
        assert "纯价值最高" in result["recommendation_reason"]


def test_token_rate_from_overlap(client):
    part = make_resource(client, "零件")
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
                "min_vip_level": 1,
            }
        ],
    )
    token_type = make_shop_type(client, "战役商店", "战役币", "standard", "token")
    token_shop = make_shop(
        client,
        token_type,
        [
            {
                "resource_id": part["id"],
                "resource_qty": 30,
                "discounted_currency_qty": 270,
                "discount_pct": 50,
            }
        ],
    )

    with SessionLocal() as db:
        rates = pricing.build_currency_rates(db, 18)
        assert len(rates["rates"]) == 1
        rate = rates["rates"][0]
        assert rate["currency"] == "战役币"
        assert rate["gold_per_unit"] == 0.5
        assert rate["samples"] == 1

        result = pricing.evaluate_shop(db, token_shop["id"], 18)
        assert result["gold_per_currency_unit"] == 0.5
        offer = result["offers"][0]
        assert offer["unit_price"] == 9
        assert offer["unit_price_gold"] == 4.5
        assert offer["efficiency_gold"] == 1.0


def test_no_rate_without_overlap(client):
    part = make_resource(client, "零件")
    gold_type = make_shop_type(client, "特权商店", "黄金", "vip_tiered", "gold")
    make_shop(
        client,
        gold_type,
        [
            {
                "resource_id": part["id"],
                "resource_qty": 30,
                "discounted_currency_qty": 135,
                "min_vip_level": 1,
            }
        ],
    )
    token_type = make_shop_type(client, "战役商店", "战役币", "standard", "token")
    other = make_resource(client, "海军零件")
    shop = make_shop(
        client,
        token_type,
        [{"resource_id": other["id"], "resource_qty": 10, "discounted_currency_qty": 90}],
    )

    with SessionLocal() as db:
        rates = pricing.build_currency_rates(db, 18)
        assert rates["rates"] == []
        result = pricing.evaluate_shop(db, shop["id"], 18)
        assert result["gold_per_currency_unit"] is None
        assert any("无法反推汇率" in note for note in result["notes"])


def test_vip_tiered_effective_offer(client):
    part = make_resource(client, "零件")
    shop_type = make_shop_type(client, "特权商店", "黄金", "vip_tiered", "gold")
    shop = make_shop(
        client,
        shop_type,
        [
            {
                "resource_id": part["id"],
                "resource_qty": 30,
                "discounted_currency_qty": 270,
                "discount_pct": 70,
                "min_vip_level": 12,
            },
            {
                "resource_id": part["id"],
                "resource_qty": 30,
                "discounted_currency_qty": 135,
                "discount_pct": 85,
                "min_vip_level": 18,
            },
        ],
    )

    with SessionLocal() as db:
        low = pricing.evaluate_shop(db, shop["id"], 12)
        high = pricing.evaluate_shop(db, shop["id"], 18)
        assert low["offers"][0]["discounted_price"] == 270
        assert high["offers"][0]["discounted_price"] == 135


def test_data_status_lists_gaps(client):
    part = make_resource(client, "零件")
    make_resource(client, "海军零件")
    gold_type = make_shop_type(client, "特权商店", "黄金", "vip_tiered", "gold")
    make_shop(
        client,
        gold_type,
        [
            {
                "resource_id": part["id"],
                "resource_qty": 30,
                "discounted_currency_qty": 135,
                "min_vip_level": 1,
            }
        ],
    )

    with SessionLocal() as db:
        status = pricing.build_data_status(db, 18)
        assert status["resources_total"] == 2
        assert status["resources_priced"] == 1
        assert status["unpriced_resources"] == ["海军零件"]
        assert status["boxes_total"] == 0
        assert any("没有黄金价格" in warning for warning in status["warnings"])
