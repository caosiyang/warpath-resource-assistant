from __future__ import annotations


def create_resource_type(client, name="基础资源", sort_order=1, note=None):
    response = client.post(
        "/api/resource-types",
        json={"name": name, "sort_order": sort_order, "note": note},
    )
    assert response.status_code == 201, response.text
    return response.json()


def get_or_create_resource_type(client, name="基础资源", sort_order=1):
    existing = {
        item["name"]: item for item in client.get("/api/resource-types").json()
    }
    if name in existing:
        return existing[name]
    return create_resource_type(client, name=name, sort_order=sort_order)


def create_resource(
    client,
    name="钢铁",
    unit="1",
    type_name="基础资源",
    type_id=None,
):
    if type_id is None:
        type_id = get_or_create_resource_type(client, name=type_name)["id"]
    response = client.post(
        "/api/resources",
        json={"name": name, "unit": unit, "type_id": type_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_currency(client, name="战役币", kind="token"):
    response = client.post("/api/currencies", json={"name": name, "kind": kind})
    assert response.status_code == 201, response.text
    return response.json()


def get_or_create_currency(client, name="战役币", kind="token"):
    existing = {item["name"]: item for item in client.get("/api/currencies").json()}
    if name in existing:
        return existing[name]
    return create_currency(client, name=name, kind=kind)


def create_shop_type(
    client,
    name="战役商店",
    currency_name="战役币",
    currency_kind="token",
    refresh_period="7天",
    pricing_mode="standard",
    is_active=True,
    sort_order=1,
):
    currency = get_or_create_currency(client, name=currency_name, kind=currency_kind)
    response = client.post(
        "/api/shop-types",
        json={
            "name": name,
            "currency_id": currency["id"],
            "default_refresh_period": refresh_period,
            "pricing_mode": pricing_mode,
            "sort_order": sort_order,
            "is_active": is_active,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_vip_shop_type(
    client,
    name="特权商店",
    currency_name="黄金",
    currency_kind="gold",
    refresh_period="1周",
):
    return create_shop_type(
        client,
        name=name,
        currency_name=currency_name,
        currency_kind=currency_kind,
        refresh_period=refresh_period,
        pricing_mode="vip_tiered",
    )


def create_shop(client, shop_type, offers=None, refresh_period=None):
    payload = {"shop_type_id": shop_type["id"], "offers": offers or []}
    if refresh_period is not None:
        payload["refresh_period"] = refresh_period
    response = client.post("/api/shops", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_resource_and_duplicate(client):
    resource = create_resource(client)
    assert resource["name"] == "钢铁"
    assert resource["resource_type"]["name"] == "基础资源"

    duplicate = client.post(
        "/api/resources",
        json={"name": "钢铁", "type_id": resource["type_id"]},
    )
    assert duplicate.status_code == 400
    assert "已存在" in duplicate.json()["detail"]

    listing = client.get("/api/resources").json()
    assert len(listing) == 1


def test_page_edit_resource(client):
    resource = create_resource(client, name="旧资源")

    page = client.get(f"/resources/{resource['id']}/edit")
    assert page.status_code == 200

    response = client.post(
        f"/resources/{resource['id']}/edit",
        data={
            "name": "新资源",
            "unit": "1",
            "type_id": str(resource["type_id"]),
            "note": "改过",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = client.get(f"/api/resources/{resource['id']}").json()
    assert updated["name"] == "新资源"
    assert updated["note"] == "改过"

    other = create_resource(client, name="另一个资源")
    duplicate = client.post(
        f"/resources/{other['id']}/edit",
        data={
            "name": "新资源",
            "unit": "1",
            "type_id": str(other["type_id"]),
        },
        follow_redirects=False,
    )
    assert duplicate.status_code == 200
    assert "已存在" in duplicate.text


def test_resource_types_api(client):
    resource_type = create_resource_type(client, name="兵卡资源", sort_order=3)
    assert resource_type["name"] == "兵卡资源"
    assert resource_type["resource_count"] == 0

    duplicate = client.post("/api/resource-types", json={"name": "兵卡资源"})
    assert duplicate.status_code == 400
    assert "已存在" in duplicate.json()["detail"]

    updated = client.patch(
        f"/api/resource-types/{resource_type['id']}",
        json={"name": "兵卡资源改"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "兵卡资源改"

    resource = create_resource(client, name="弹药", type_id=resource_type["id"])
    assert resource["type_id"] == resource_type["id"]

    blocked = client.delete(f"/api/resource-types/{resource_type['id']}")
    assert blocked.status_code == 400
    assert "还有资源" in blocked.json()["detail"]

    assert client.delete(f"/api/resources/{resource['id']}").status_code == 204
    assert client.delete(f"/api/resource-types/{resource_type['id']}").status_code == 204


def test_page_resource_types(client):
    page = client.get("/resource-types")
    assert page.status_code == 200

    response = client.post(
        "/resource-types",
        data={"name": "兵卡资源", "sort_order": "3", "note": "兵卡"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    listing = client.get("/resource-types")
    assert "兵卡资源" in listing.text

    types = client.get("/api/resource-types").json()
    type_id = types[0]["id"]
    assert client.get(f"/resource-types/{type_id}/edit").status_code == 200

    response = client.post(
        f"/resource-types/{type_id}/edit",
        data={"name": "兵卡资源改", "sort_order": "3", "note": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/api/resource-types").json()[0]["name"] == "兵卡资源改"


def test_create_resource_requires_type(client):
    response = client.post("/api/resources", json={"name": "钢铁"})
    assert response.status_code == 422

    page = client.post(
        "/resources",
        data={"name": "钢铁", "unit": "1"},
        follow_redirects=False,
    )
    assert page.status_code == 200
    assert "请选择资源类型" in page.text


def test_create_currency(client):
    currency = create_currency(client)
    assert currency["kind"] == "token"

    gold = create_currency(client, name="黄金", kind="gold")
    assert gold["kind"] == "gold"

    invalid = client.post("/api/currencies", json={"name": "钻石", "kind": "gem"})
    assert invalid.status_code == 422


def test_create_shop_type_and_duplicate(client):
    shop_type = create_shop_type(client)
    assert shop_type["name"] == "战役商店"
    assert shop_type["currency"]["name"] == "战役币"
    assert shop_type["default_refresh_period"] == "7天"
    assert shop_type["pricing_mode"] == "standard"
    assert shop_type["shop_id"] is None

    duplicate = client.post(
        "/api/shop-types",
        json={"name": "战役商店", "currency_id": shop_type["currency_id"]},
    )
    assert duplicate.status_code == 400
    assert "已存在" in duplicate.json()["detail"]


def test_create_shop_with_discount(client):
    resource = create_resource(client)
    shop_type = create_shop_type(client)

    response = client.post(
        "/api/shops",
        json={
            "shop_type_id": shop_type["id"],
            "refresh_period": "每周",
            "offers": [
                {
                    "resource_id": resource["id"],
                    "resource_qty": 100000,
                    "discounted_currency_qty": 500,
                    "discount_pct": 20,
                    "limit_qty": 5,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    shop = response.json()
    assert shop["name"] == "战役商店"
    assert shop["currency"]["name"] == "战役币"
    assert shop["shop_type"]["name"] == "战役商店"
    assert shop["refresh_period"] == "每周"

    offer = shop["offers"][0]
    assert offer["discounted_currency_qty"] == 500
    assert offer["original_currency_qty"] == 625
    assert offer["unit_price"] == 0.005
    assert offer["resource"]["name"] == "钢铁"


def test_shop_uses_type_default_refresh_period(client):
    shop_type = create_shop_type(client, refresh_period="3天")
    shop = create_shop(client, shop_type)
    assert shop["refresh_period"] == "3天"


def test_cannot_create_duplicate_shop_for_type(client):
    shop_type = create_shop_type(client)
    create_shop(client, shop_type)
    duplicate = client.post(
        "/api/shops", json={"shop_type_id": shop_type["id"], "offers": []}
    )
    assert duplicate.status_code == 400
    assert "已创建" in duplicate.json()["detail"]


def test_inactive_shop_type_cannot_create_shop(client):
    shop_type = create_shop_type(client, is_active=False)
    response = client.post(
        "/api/shops", json={"shop_type_id": shop_type["id"], "offers": []}
    )
    assert response.status_code == 400
    assert "停用" in response.json()["detail"]


def test_shop_type_currency_locked_after_shop(client):
    shop_type = create_shop_type(client, name="特权商店", currency_name="黄金", currency_kind="gold")
    create_shop(client, shop_type)
    other = create_currency(client, name="联盟贡献币")

    response = client.patch(
        f"/api/shop-types/{shop_type['id']}", json={"currency_id": other["id"]}
    )
    assert response.status_code == 400
    assert "不能修改绑定货币" in response.json()["detail"]


def test_delete_shop_type_with_shop_fails(client):
    shop_type = create_shop_type(client)
    create_shop(client, shop_type)
    response = client.delete(f"/api/shop-types/{shop_type['id']}")
    assert response.status_code == 400
    assert "无法删除" in response.json()["detail"]


def test_delete_currency_used_by_shop_type_fails(client):
    shop_type = create_shop_type(client)
    response = client.delete(f"/api/currencies/{shop_type['currency_id']}")
    assert response.status_code == 400
    assert "无法删除" in response.json()["detail"]


def test_shop_allows_multiple_offers_same_resource(client):
    resource = create_resource(client)
    shop_type = create_shop_type(client)
    payload = {
        "shop_type_id": shop_type["id"],
        "offers": [
            {
                "resource_id": resource["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 10,
            },
            {
                "resource_id": resource["id"],
                "resource_qty": 2000,
                "discounted_currency_qty": 15,
            },
        ],
    }
    response = client.post("/api/shops", json=payload)
    assert response.status_code == 201, response.text
    offers = response.json()["offers"]
    assert len(offers) == 2
    assert offers[0]["unit_price"] == 0.01
    assert offers[1]["unit_price"] == 0.0075


def test_add_and_delete_offer(client):
    resource = create_resource(client)
    shop_type = create_shop_type(client)
    shop = create_shop(client, shop_type)

    created = client.post(
        f"/api/shops/{shop['id']}/offers",
        json={
            "resource_id": resource["id"],
            "resource_qty": 50000,
            "discounted_currency_qty": 250,
            "discount_pct": 50,
        },
    )
    assert created.status_code == 201, created.text
    offer = created.json()
    assert offer["discounted_currency_qty"] == 250
    assert offer["original_currency_qty"] == 500
    assert offer["unit_price"] == 0.005

    deleted = client.delete(f"/api/shops/{shop['id']}/offers/{offer['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/shops/{shop['id']}").json()["offers"] == []


def test_create_box_with_items(client):
    steel = create_resource(client)
    oil = create_resource(client, name="石油")

    response = client.post(
        "/api/boxes",
        json={
            "name": "中级资源自选箱",
            "items": [
                {"resource_id": steel["id"], "qty": 500000},
                {"resource_id": oil["id"], "qty": 300000},
            ],
        },
    )
    assert response.status_code == 201, response.text
    box = response.json()
    assert len(box["items"]) == 2
    assert {item["resource"]["name"] for item in box["items"]} == {"钢铁", "石油"}
    assert "size" not in box
    assert "selection_type" not in box
    assert "source" not in box
    assert "probability" not in box["items"][0]


def test_box_items_have_no_probability(client):
    resource = create_resource(client)
    completed = client.post(
        "/api/boxes",
        json={
            "name": "自选资源箱",
            "items": [{"resource_id": resource["id"], "qty": 100}],
        },
    )
    assert completed.status_code == 201, completed.text
    item = completed.json()["items"][0]
    assert "probability" not in item
    assert item["qty"] == 100


def test_negative_quantity_validation(client):
    resource = create_resource(client)
    shop_type = create_shop_type(client)
    response = client.post(
        "/api/shops",
        json={
            "shop_type_id": shop_type["id"],
            "offers": [
                {
                    "resource_id": resource["id"],
                    "resource_qty": -1,
                    "discounted_currency_qty": 10,
                }
            ],
        },
    )
    assert response.status_code == 422


def test_vip_tiered_offer_requires_level(client):
    resource = create_resource(client)
    shop_type = create_vip_shop_type(client)
    shop = create_shop(client, shop_type)

    response = client.post(
        f"/api/shops/{shop['id']}/offers",
        json={
            "resource_id": resource["id"],
            "resource_qty": 1000,
            "discounted_currency_qty": 10,
        },
    )
    assert response.status_code == 400
    assert "必须填写解锁特权等级" in response.json()["detail"]


def test_standard_shop_rejects_vip_level(client):
    resource = create_resource(client)
    shop_type = create_shop_type(client)
    shop = create_shop(client, shop_type)

    response = client.post(
        f"/api/shops/{shop['id']}/offers",
        json={
            "resource_id": resource["id"],
            "resource_qty": 1000,
            "discounted_currency_qty": 10,
            "min_vip_level": 10,
        },
    )
    assert response.status_code == 400
    assert "不需要解锁特权等级" in response.json()["detail"]


def test_duplicate_vip_offer_rejected(client):
    resource = create_resource(client)
    shop_type = create_vip_shop_type(client)
    shop = create_shop(
        client,
        shop_type,
        offers=[
            {
                "resource_id": resource["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 10,
                "min_vip_level": 10,
            }
        ],
    )

    duplicate = client.post(
        f"/api/shops/{shop['id']}/offers",
        json={
            "resource_id": resource["id"],
            "resource_qty": 2000,
            "discounted_currency_qty": 20,
            "min_vip_level": 10,
        },
    )
    assert duplicate.status_code == 400
    assert "已有商品" in duplicate.json()["detail"]

    allowed = client.post(
        f"/api/shops/{shop['id']}/offers",
        json={
            "resource_id": resource["id"],
            "resource_qty": 2000,
            "discounted_currency_qty": 20,
            "min_vip_level": 15,
        },
    )
    assert allowed.status_code == 201


def test_effective_offers_by_vip(client):
    steel = create_resource(client)
    oil = create_resource(client, name="石油")
    shop_type = create_vip_shop_type(client)
    shop = create_shop(
        client,
        shop_type,
        offers=[
            {
                "resource_id": steel["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 100,
                "discount_pct": 20,
                "min_vip_level": 10,
            },
            {
                "resource_id": steel["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 100,
                "discount_pct": 30,
                "min_vip_level": 15,
            },
            {
                "resource_id": oil["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 200,
                "discount_pct": 25,
                "min_vip_level": 20,
            },
        ],
    )

    # VIP12: 只有钢铁 20%
    offers = client.get(f"/api/shops/{shop['id']}/effective?vip_level=12").json()
    assert len(offers) == 1
    assert offers[0]["resource"]["name"] == "钢铁"
    assert offers[0]["discount_pct"] == 20

    # VIP18: 钢铁取最高 30%，石油未解锁
    offers = client.get(f"/api/shops/{shop['id']}/effective?vip_level=18").json()
    assert len(offers) == 1
    assert offers[0]["discount_pct"] == 30

    # VIP20: 钢铁 30% + 石油 25%
    offers = client.get(f"/api/shops/{shop['id']}/effective?vip_level=20").json()
    by_name = {offer["resource"]["name"]: offer for offer in offers}
    assert by_name["钢铁"]["discount_pct"] == 30
    assert by_name["石油"]["discount_pct"] == 25

    # 不传 vip_level 时使用设置里的默认值 18
    offers = client.get(f"/api/shops/{shop['id']}/effective").json()
    assert len(offers) == 1


def test_settings_api(client):
    settings = client.get("/api/settings")
    assert settings.status_code == 200
    assert settings.json() == {"current_vip_level": 18, "max_vip_level": 25}

    updated = client.put("/api/settings", json={"current_vip_level": 20})
    assert updated.status_code == 200
    assert updated.json()["current_vip_level"] == 20
    assert client.get("/api/settings").json()["current_vip_level"] == 20

    invalid = client.put("/api/settings", json={"current_vip_level": 26})
    assert invalid.status_code == 422


def test_pricing_mode_locked_with_offers(client):
    resource = create_resource(client)
    shop_type = create_vip_shop_type(client)
    create_shop(
        client,
        shop_type,
        offers=[
            {
                "resource_id": resource["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 10,
                "min_vip_level": 10,
            }
        ],
    )

    response = client.patch(
        f"/api/shop-types/{shop_type['id']}", json={"pricing_mode": "standard"}
    )
    assert response.status_code == 400
    assert "不能修改定价模式" in response.json()["detail"]


def test_page_settings(client):
    page = client.get("/settings")
    assert page.status_code == 200
    assert "VIP18" in page.text

    response = client.post(
        "/settings", data={"current_vip_level": "20"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert client.get("/api/settings").json()["current_vip_level"] == 20


def test_shop_detail_vip_view(client):
    steel = create_resource(client)
    shop_type = create_vip_shop_type(client)
    shop = create_shop(
        client,
        shop_type,
        offers=[
            {
                "resource_id": steel["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 100,
                "discount_pct": 20,
                "min_vip_level": 10,
            },
            {
                "resource_id": steel["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 100,
                "discount_pct": 30,
                "min_vip_level": 15,
            },
        ],
    )

    page = client.get(f"/shops/{shop['id']}?vip=12")
    assert page.status_code == 200
    assert "未解锁" in page.text
    assert "当前最优" in page.text
    assert "VIP15" in page.text


def test_pages_render(client):
    create_shop_type(client)
    for path in [
        "/",
        "/resources",
        "/resource-types",
        "/currencies",
        "/shop-types",
        "/shops",
        "/shops/new",
        "/boxes",
        "/boxes/new",
    ]:
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.text[:200]}"


def test_page_create_shop_type(client):
    currency = create_currency(client, name="黄金", kind="gold")
    response = client.post(
        "/shop-types",
        data={
            "name": "特权商店",
            "currency_id": str(currency["id"]),
            "default_refresh_period": "1周",
            "sort_order": "1",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    listing = client.get("/shop-types")
    assert listing.status_code == 200
    assert "特权商店" in listing.text


def test_page_create_shop(client):
    resource = create_resource(client)
    shop_type = create_shop_type(client, name="页面测试商店")

    response = client.post(
        "/shops",
        data={
            "shop_type_id": str(shop_type["id"]),
            "refresh_period": "每日",
            "resource_id": str(resource["id"]),
            "resource_qty": "30",
            "discounted_currency_qty": "135",
            "discount_pct": "85",
            "limit_qty": "20",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/shops/")

    detail = client.get(location)
    assert detail.status_code == 200
    assert "页面测试商店" in detail.text
    assert "135" in detail.text  # 折后价 / 组
    assert "900" in detail.text  # 反算原价
    assert "4.5" in detail.text  # 单价 / 个
    assert "20 组" in detail.text


def test_page_edit_shop(client):
    shop_type = create_shop_type(client, name="编辑商店")
    shop = create_shop(client, shop_type)

    edit_page = client.get(f"/shops/{shop['id']}/edit")
    assert edit_page.status_code == 200

    response = client.post(
        f"/shops/{shop['id']}/edit",
        data={"refresh_period": "每日", "note": "手动覆盖"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = client.get(f"/api/shops/{shop['id']}").json()
    assert updated["refresh_period"] == "每日"
    assert updated["note"] == "手动覆盖"


def test_page_create_box(client):
    resource = create_resource(client)

    response = client.post(
        "/boxes",
        data={
            "name": "页面箱子",
            "resource_id": str(resource["id"]),
            "qty": "500000",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "页面箱子" in detail.text


def test_page_edit_offer(client):
    resource = create_resource(client)
    shop_type = create_shop_type(client)
    shop = create_shop(
        client,
        shop_type,
        offers=[
            {
                "resource_id": resource["id"],
                "resource_qty": 100000,
                "discounted_currency_qty": 500,
            }
        ],
    )
    offer = shop["offers"][0]

    edit_page = client.get(f"/shops/{shop['id']}/offers/{offer['id']}/edit")
    assert edit_page.status_code == 200

    response = client.post(
        f"/shops/{shop['id']}/offers/{offer['id']}/edit",
        data={
            "resource_id": str(resource["id"]),
            "resource_qty": "200000",
            "discounted_currency_qty": "600",
            "discount_pct": "50",
            "limit_qty": "2",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = client.get(f"/api/shops/{shop['id']}").json()["offers"][0]
    assert updated["resource_qty"] == 200000
    assert updated["discounted_currency_qty"] == 600
    assert updated["original_currency_qty"] == 1200
    assert updated["unit_price"] == 0.003


def test_page_edit_box_item(client):
    resource = create_resource(client)
    box = client.post(
        "/api/boxes",
        json={
            "name": "编辑箱子",
            "items": [{"resource_id": resource["id"], "qty": 100}],
        },
    ).json()
    item = box["items"][0]

    edit_page = client.get(f"/boxes/{box['id']}/items/{item['id']}/edit")
    assert edit_page.status_code == 200

    response = client.post(
        f"/boxes/{box['id']}/items/{item['id']}/edit",
        data={"resource_id": str(resource["id"]), "qty": "250"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = client.get(f"/api/boxes/{box['id']}").json()["items"][0]
    assert updated["qty"] == 250


def test_delete_shop_cascades_offers(client):
    resource = create_resource(client)
    shop_type = create_shop_type(client)
    shop = create_shop(
        client,
        shop_type,
        offers=[
            {
                "resource_id": resource["id"],
                "resource_qty": 1000,
                "discounted_currency_qty": 10,
            }
        ],
    )

    assert client.delete(f"/api/shops/{shop['id']}").status_code == 204
    assert client.get("/api/shops").json() == []
