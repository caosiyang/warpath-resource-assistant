"""OpenAI 兼容模型的流式客户端。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "deepseek-v4.1-flash"


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float


def get_llm_config() -> LLMConfig:
    load_dotenv(PROJECT_ROOT / ".env")
    base_url = os.environ.get("WARPATH_LLM_BASE_URL", "").strip().rstrip("/")
    api_key = os.environ.get("WARPATH_LLM_API_KEY", "").strip()
    model = os.environ.get("WARPATH_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    raw_timeout = os.environ.get("WARPATH_LLM_TIMEOUT", "60").strip()
    try:
        timeout = float(raw_timeout)
    except ValueError:
        timeout = 60.0

    if not base_url or not api_key:
        raise LLMError(
            "模型未配置。请在项目根目录创建 .env，填写 "
            "WARPATH_LLM_BASE_URL 和 WARPATH_LLM_API_KEY。"
        )
    return LLMConfig(base_url=base_url, api_key=api_key, model=model, timeout=timeout)


async def stream_chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    config: LLMConfig | None = None,
) -> AsyncIterator[dict]:
    """调用模型并逐块产出事件。

    事件类型：
    - {"type": "token", "text": str}
    - {"type": "tool_calls", "calls": [{"id", "name", "arguments"}]}
    - {"type": "finish", "reason": str}
    """
    cfg = config or get_llm_config()
    payload: dict = {
        "model": cfg.model,
        "messages": messages,
        "stream": True,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=cfg.timeout) as client:
            async with client.stream(
                "POST",
                f"{cfg.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise LLMError(
                        f"模型接口返回 {response.status_code}：{body[:300]}"
                    )

                tool_calls: dict[int, dict] = {}
                finish_reason: str | None = None

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        if raw == "[DONE]":
                            break
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}

                    text = delta.get("content")
                    if text:
                        yield {"type": "token", "text": text}

                    for call in delta.get("tool_calls") or []:
                        index = call.get("index", 0)
                        slot = tool_calls.setdefault(
                            index, {"id": "", "name": "", "arguments": ""}
                        )
                        if call.get("id"):
                            slot["id"] = call["id"]
                        function = call.get("function") or {}
                        if function.get("name"):
                            slot["name"] = function["name"]
                        if function.get("arguments"):
                            slot["arguments"] += function["arguments"]

                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]

                if tool_calls:
                    calls = []
                    for index in sorted(tool_calls):
                        slot = tool_calls[index]
                        if not slot["name"]:
                            continue
                        calls.append(
                            {
                                "id": slot["id"] or f"call_{index}",
                                "name": slot["name"],
                                "arguments": slot["arguments"] or "{}",
                            }
                        )
                    if calls:
                        yield {"type": "tool_calls", "calls": calls}
                        finish_reason = finish_reason or "tool_calls"

                yield {"type": "finish", "reason": finish_reason or "stop"}
    except httpx.HTTPError as exc:
        raise LLMError(f"连接模型失败：{exc}") from exc
