from __future__ import annotations

from typing import Any, Literal, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.nodes.pipeline import (
    node_design_svgs,
    node_generate_outline,
    node_plan_layouts,
    node_research_background,
    node_research_pages,
)
from app.state import PPTState


def _wait_outline_confirm(state: PPTState) -> dict:
    """人工确认大纲。Web 层通过 Command(resume=...) 注入修改后的大纲。"""
    if state.get("auto_confirm_outline"):
        return {
            "status": "researching_pages",
            "progress": "跳过确认，继续检索…",
            "wait_for_outline": False,
        }

    payload = {
        "type": "outline_confirm",
        "outline": state.get("outline"),
        "message": "请确认或修改大纲后继续",
    }
    resumed = interrupt(payload)
    # resumed 期望: {"action": "confirm"|"edit", "outline": optional dict}
    outline = state.get("outline") or {}
    if isinstance(resumed, dict):
        if resumed.get("outline"):
            outline = resumed["outline"]
        action = resumed.get("action", "confirm")
        if action == "cancel":
            return {
                "status": "error",
                "error": "用户取消",
                "progress": "已取消",
                "wait_for_outline": False,
            }

    from app.nodes.pipeline import flatten_outline

    return {
        "outline": outline,
        "page_list": flatten_outline(outline),
        "status": "researching_pages",
        "progress": "大纲已确认，开始检索各页资料…",
        "wait_for_outline": False,
    }


def _route_after_outline(state: PPTState) -> Literal["wait_outline", "research_pages"]:
    if state.get("auto_confirm_outline"):
        return "research_pages"
    return "wait_outline"


def build_graph():
    g = StateGraph(PPTState)

    g.add_node("research_background", node_research_background)
    g.add_node("generate_outline", node_generate_outline)
    g.add_node("wait_outline", _wait_outline_confirm)
    g.add_node("research_pages", node_research_pages)
    g.add_node("plan_layouts", node_plan_layouts)
    g.add_node("design_svgs", node_design_svgs)

    g.add_edge(START, "research_background")
    g.add_edge("research_background", "generate_outline")
    g.add_conditional_edges(
        "generate_outline",
        _route_after_outline,
        {
            "wait_outline": "wait_outline",
            "research_pages": "research_pages",
        },
    )
    g.add_edge("wait_outline", "research_pages")
    g.add_edge("research_pages", "plan_layouts")
    g.add_edge("plan_layouts", "design_svgs")
    g.add_edge("design_svgs", END)

    return g


def compile_app(checkpointer: Any):
    return build_graph().compile(checkpointer=checkpointer)
