from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field
from typing_extensions import Annotated, TypedDict
import operator


class JobRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="PPT 主题")
    audience: str = Field(default="通用商务受众", description="受众")
    purpose: str = Field(default="介绍与说服", description="演示目的")
    pages: str = Field(default="8-12页", description="页数要求")
    style: str = Field(
        default="现代科技、高级感、简洁、深色背景点缀亮色",
        description="视觉风格",
    )
    extra: str = Field(default="", description="补充说明")
    auto_confirm_outline: bool = Field(
        default=False,
        description="True 则大纲生成后不暂停，直接跑完",
    )


class OutlinePage(BaseModel):
    title: str
    content: list[str] = Field(default_factory=list)


class OutlinePart(BaseModel):
    part_title: str
    pages: list[OutlinePage] = Field(default_factory=list)


class PPTOutline(BaseModel):
    cover: dict[str, Any] = Field(default_factory=dict)
    table_of_contents: dict[str, Any] = Field(default_factory=dict)
    parts: list[OutlinePart] = Field(default_factory=list)
    end_page: dict[str, Any] = Field(default_factory=dict)


class PageResearch(BaseModel):
    page_key: str
    page_title: str
    page_kind: str = "content"  # cover | toc | content | end
    bullets: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class LayoutCard(BaseModel):
    role: str = "body"
    text: str = ""
    size_hint: str = "md"  # sm | md | lg | hero
    visual_hint: str = ""


class LayoutPlan(BaseModel):
    page_key: str
    page_title: str
    page_kind: str = "content"
    layout_type: str = "mixed"
    cards: list[LayoutCard] = Field(default_factory=list)


class SlideResult(BaseModel):
    page_key: str
    page_title: str
    page_kind: str = "content"
    svg: str = ""
    error: Optional[str] = None


class JobStatus(BaseModel):
    id: str
    status: Literal[
        "queued",
        "researching",
        "outlining",
        "waiting_outline_confirm",
        "researching_pages",
        "planning",
        "designing",
        "done",
        "error",
    ]
    topic: str
    progress: str = ""
    error: Optional[str] = None
    outline: Optional[dict[str, Any]] = None
    slides: list[SlideResult] = Field(default_factory=list)
    background: str = ""


class PPTState(TypedDict, total=False):
    job_id: str
    topic: str
    audience: str
    purpose: str
    pages: str
    style: str
    extra: str
    auto_confirm_outline: bool

    background: str
    outline: dict
    page_list: list[dict]  # flattened pages
    page_research: Annotated[list[dict], operator.add]
    layout_plans: list[dict]
    slides: Annotated[list[dict], operator.add]

    status: str
    progress: str
    error: str
    wait_for_outline: bool
