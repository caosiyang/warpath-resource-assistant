from __future__ import annotations

from app import chat as chat_service

from test_pricing import make_box, make_resource, make_shop, make_shop_type


class FakeModel:
    def __init__(self, tool_name: str | None = None, tool_arguments: str = "{}"):
        self.tool_name = tool_name
        self.tool_arguments = tool_arguments
        self.calls = 0

    async def __call__(self, messages, tools=None, config=None):
        self.calls += 1
        if self.calls == 1 and self.tool_name:
            yield {
                "type": "tool_calls",
                "calls": [
                    {
                        "id": "call_1",
                        "name": self.tool_name,
                        "arguments": self.tool_arguments,
                    }
                ],
            }
            yield {"type": "finish", "reason": "tool_calls"}
            return
        yield {"type": "token", "text": "当前是 "}
        yield {"type": "token", "text": "VIP 18。"}
        yield {"type": "finish", "reason": "stop"}


def test_chat_stream_calls_tool_and_persists(client, monkeypatch):
    fake = FakeModel(tool_name="get_settings")
    monkeypatch.setattr(chat_service.llm, "stream_chat", fake)

    response = client.post("/api/chat", json={"message": "我的自选箱该选什么？"})
    assert response.status_code == 200, response.text
    body = response.text

    assert "event: session" in body
    assert "event: tool" in body
    assert "读取设置" in body
    assert "event: token" in body
    assert "VIP 18" in body
    assert "event: done" in body
    assert fake.calls == 2

    sessions = client.get("/api/chat/sessions").json()
    assert len(sessions) == 1
    assert sessions[0]["title"] == "我的自选箱该选什么？"

    detail = client.get(f"/api/chat/sessions/{sessions[0]['id']}").json()
    assert [message["role"] for message in detail["messages"]] == [
        "user",
        "assistant",
    ]
    assert detail["messages"][1]["tools"] == ["读取设置"]
    assert "VIP 18" in detail["messages"][1]["html"]


def test_chat_continues_existing_session(client, monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(chat_service.llm, "stream_chat", fake)

    first = client.post("/api/chat", json={"message": "你好"})
    assert first.status_code == 200
    session_id = client.get("/api/chat/sessions").json()[0]["id"]

    second = client.post(
        "/api/chat", json={"session_id": session_id, "message": "再说一次"}
    )
    assert second.status_code == 200
    assert "event: session" in second.text

    detail = client.get(f"/api/chat/sessions/{session_id}").json()
    assert [message["role"] for message in detail["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_chat_unknown_session_returns_404(client, monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(chat_service.llm, "stream_chat", fake)

    response = client.post(
        "/api/chat", json={"session_id": 99999, "message": "你好"}
    )
    assert response.status_code == 404


def test_chat_tool_error_is_fed_back(client, monkeypatch):
    fake = FakeModel(tool_name="evaluate_box", tool_arguments='{"box_id": 99999}')
    monkeypatch.setattr(chat_service.llm, "stream_chat", fake)

    response = client.post("/api/chat", json={"message": "这个箱子选什么？"})
    assert response.status_code == 200
    assert "event: done" in response.text

    session_id = client.get("/api/chat/sessions").json()[0]["id"]
    detail = client.get(f"/api/chat/sessions/{session_id}").json()
    assert detail["messages"][1]["tools"] == ["计算箱子价值"]


def test_chat_uses_real_pricing_for_box(client, monkeypatch):
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

    class BoxModel:
        def __init__(self):
            self.calls = 0

        async def __call__(self, messages, tools=None, config=None):
            self.calls += 1
            if self.calls == 1:
                yield {
                    "type": "tool_calls",
                    "calls": [
                        {
                            "id": "call_1",
                            "name": "evaluate_box",
                            "arguments": f'{{"box_id": {box["id"]}}}',
                        }
                    ],
                }
                yield {"type": "finish", "reason": "tool_calls"}
                return
            tool_payload = messages[-1]["content"]
            assert '"resource": "弹药"' in tool_payload
            assert '"value_gev": 180.0' in tool_payload
            yield {"type": "token", "text": "建议选弹药。"}
            yield {"type": "finish", "reason": "stop"}

    monkeypatch.setattr(chat_service.llm, "stream_chat", BoxModel())

    response = client.post("/api/chat", json={"message": "自选箱选什么？"})
    assert response.status_code == 200
    assert "建议选弹药" in response.text


def test_delete_session(client, monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(chat_service.llm, "stream_chat", fake)
    client.post("/api/chat", json={"message": "你好"})
    session_id = client.get("/api/chat/sessions").json()[0]["id"]

    response = client.delete(f"/api/chat/sessions/{session_id}")
    assert response.status_code == 204
    assert client.get("/api/chat/sessions").json() == []
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 404


def test_chat_page_renders(client):
    response = client.get("/chat")
    assert response.status_code == 200
    assert "助手" in response.text
    assert "chatApp" in response.text


def test_chat_page_lists_existing_sessions(client, monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(chat_service.llm, "stream_chat", fake)
    client.post("/api/chat", json={"message": "我的自选箱该选什么？"})

    response = client.get("/chat")
    assert response.status_code == 200
    assert "我的自选箱该选什么？" in response.text


def test_chat_returns_error_event_when_model_fails(client, monkeypatch):
    async def broken(messages, tools=None, config=None):
        if False:
            yield {}
        raise chat_service.llm.LLMError("模型未配置")

    monkeypatch.setattr(chat_service.llm, "stream_chat", broken)

    response = client.post("/api/chat", json={"message": "你好"})
    assert response.status_code == 200
    assert "event: error" in response.text
    assert "模型未配置" in response.text
