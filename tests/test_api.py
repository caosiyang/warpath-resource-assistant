from __future__ import annotations


def create_resource(client, name="钢铁", unit="1", category="基础资源"):
    response = client.post(
        "/api/resources",
        json={"name": name, "unit": unit, "category": category},
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
            "sort_order": sort_order,
            "is_active": is_active,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


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

    duplicate = client.post("/api/resources", json={"name": "钢铁"})
    assert duplicate.status_code == 400
    assert "已存在" in duplicate.json()["detail"]

    listing = client.get("/api/resources").json()
    assert len(listing) == 1


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
                    "list_currency_qty": 500,
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
    assert offer["effective_currency_qty"] == 400
    assert offer["unit_price_per_1000"] == 4.0
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
                "list_currency_qty": 10,
            },
            {
                "resource_id": resource["id"],
                "resource_qty": 2000,
                "list_currency_qty": 15,
            },
        ],
    }
    response = client.post("/api/shops", json=payload)
    assert response.status_code == 201, response.text
    offers = response.json()["offers"]
    assert len(offers) == 2
    assert offers[0]["unit_price_per_1000"] == 10.0
    assert offers[1]["unit_price_per_1000"] == 7.5


def test_add_and_delete_offer(client):
    resource = create_resource(client)
    shop_type = create_shop_type(client)
    shop = create_shop(client, shop_type)

    created = client.post(
        f"/api/shops/{shop['id']}/offers",
        json={
            "resource_id": resource["id"],
            "resource_qty": 50000,
            "list_currency_qty": 250,
            "discount_pct": 10,
        },
    )
    assert created.status_code == 201, created.text
    offer = created.json()
    assert offer["effective_currency_qty"] == 225
    assert offer["unit_price_per_1000"] == 4.5

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
            "size": "中",
            "selection_type": "choose_one",
            "source": "战役",
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


def test_random_box_probability_validation(client):
    resource = create_resource(client)
    invalid = client.post(
        "/api/boxes",
        json={
            "name": "随机箱",
            "selection_type": "random",
            "items": [
                {"resource_id": resource["id"], "qty": 100, "probability": 1.5}
            ],
        },
    )
    assert invalid.status_code == 422


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
                    "list_currency_qty": 10,
                }
            ],
        },
    )
    assert response.status_code == 422


def test_pages_render(client):
    create_shop_type(client)
    for path in [
        "/",
        "/resources",
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
            "resource_qty": "100000",
            "list_currency_qty": "500",
            "discount_pct": "20",
            "limit_qty": "3",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/shops/")

    detail = client.get(location)
    assert detail.status_code == 200
    assert "页面测试商店" in detail.text
    assert "4" in detail.text  # 单价 4 / 千


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
            "size": "大",
            "selection_type": "choose_one",
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
                "list_currency_qty": 500,
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
            "list_currency_qty": "600",
            "discount_pct": "50",
            "limit_qty": "2",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = client.get(f"/api/shops/{shop['id']}").json()["offers"][0]
    assert updated["resource_qty"] == 200000
    assert updated["effective_currency_qty"] == 300
    assert updated["unit_price_per_1000"] == 1.5


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
        data={"resource_id": str(resource["id"]), "qty": "250", "probability": ""},
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
                "list_currency_qty": 10,
            }
        ],
    )

    assert client.delete(f"/api/shops/{shop['id']}").status_code == 204
    assert client.get("/api/shops").json() == []
