"""中转 API 客户端：OpenAI 兼容协议；支持 Grok / Gemini 分 key。"""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Type, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


def _client(
    model: str,
    api_key: str,
    base_url: str,
    temperature: float = 0.4,
) -> ChatOpenAI:
    if not api_key:
        raise RuntimeError("未配置 API Key，请在 .env 中填写 GROK_API_KEY / GEMINI_API_KEY")
    s = get_settings()
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        temperature=temperature,
        timeout=s.llm_timeout,
        max_retries=2,
        # 部分中转默认 stream；显式关闭，避免非标准 SSE 解析失败
        streaming=False,
        model_kwargs={"stream": False},
    )


def grok(temperature: float = 0.3) -> ChatOpenAI:
    s = get_settings()
    return _client(s.grok_model, s.grok_key(), s.grok_url(), temperature)


def gemini(temperature: float = 0.4) -> ChatOpenAI:
    s = get_settings()
    return _client(s.gemini_model, s.gemini_key(), s.gemini_url(), temperature)


def gemini_design(temperature: float = 0.5) -> ChatOpenAI:
    s = get_settings()
    return _client(s.design_model, s.gemini_key(), s.gemini_url(), temperature)


def chat(
    llm: ChatOpenAI,
    user: str,
    system: Optional[str] = None,
) -> str:
    msgs = []
    if system:
        msgs.append(SystemMessage(content=system))
    msgs.append(HumanMessage(content=user))
    resp = llm.invoke(msgs)
    content = resp.content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict) and "text" in c:
                parts.append(c["text"])
            else:
                parts.append(str(c))
        return "".join(parts)
    return str(content)


def extract_json_block(text: str) -> Any:
    """从模型输出中尽量抠出 JSON。"""
    text = text.strip()
    m = re.search(
        r"\[PPT_OUTLINE\]\s*([\s\S]*?)\s*\[/PPT_OUTLINE\]",
        text,
        re.I,
    )
    if m:
        text = m.group(1).strip()

    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if m:
        text = m.group(1).strip()

    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    return json.loads(text)


def extract_svg(text: str) -> str:
    text = text.strip()
    m = re.search(r"(<svg[\s\S]*?</svg>)", text, re.I)
    if not m:
        raise ValueError("模型输出中未找到 <svg>...</svg>")
    return m.group(1).strip()


def parse_as(model: Type[T], text: str) -> T:
    data = extract_json_block(text)
    if isinstance(data, dict) and "ppt_outline" in data:
        data = data["ppt_outline"]
    return model.model_validate(data)
