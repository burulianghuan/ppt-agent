from __future__ import annotations

from app.llm import chat, extract_json_block, extract_svg, gemini, gemini_design, grok
from app.prompts import (
    BACKGROUND_PROMPT,
    LAYOUT_PROMPT,
    OUTLINE_SYSTEM,
    PAGE_RESEARCH_PROMPT,
    SVG_PROMPT,
)
from app.state import PPTState


def flatten_outline(outline: dict) -> list[dict]:
    """把大纲展平成有序页面列表。"""
    pages: list[dict] = []
    cover = outline.get("cover") or {}
    pages.append(
        {
            "page_key": "cover",
            "page_title": cover.get("title") or "封面",
            "page_kind": "cover",
            "part_title": "封面",
            "seed_content": cover.get("content") or [],
            "sub_title": cover.get("sub_title") or "",
        }
    )

    toc = outline.get("table_of_contents") or {}
    pages.append(
        {
            "page_key": "toc",
            "page_title": toc.get("title") or "目录",
            "page_kind": "toc",
            "part_title": "目录",
            "seed_content": toc.get("content") or [],
        }
    )

    for pi, part in enumerate(outline.get("parts") or []):
        part_title = part.get("part_title") or f"第{pi+1}部分"
        for qi, page in enumerate(part.get("pages") or []):
            title = page.get("title") or f"页面{qi+1}"
            pages.append(
                {
                    "page_key": f"p{pi}_{qi}",
                    "page_title": title,
                    "page_kind": "content",
                    "part_title": part_title,
                    "seed_content": page.get("content") or [],
                }
            )

    end = outline.get("end_page") or {}
    pages.append(
        {
            "page_key": "end",
            "page_title": end.get("title") or "总结与展望",
            "page_kind": "end",
            "part_title": "结尾",
            "seed_content": end.get("content") or [],
        }
    )
    return pages


def node_research_background(state: PPTState) -> dict:
    prompt = BACKGROUND_PROMPT.format(
        topic=state.get("topic", ""),
        audience=state.get("audience", ""),
        purpose=state.get("purpose", ""),
        extra=state.get("extra") or "无",
    )
    # 中转场景：Grok 若带搜索能力最好；否则当强总结模型用
    text = chat(grok(0.3), prompt)
    return {
        "background": text,
        "status": "outlining",
        "progress": "背景调研完成，正在生成大纲…",
    }


def node_generate_outline(state: PPTState) -> dict:
    system = OUTLINE_SYSTEM.format(page_requirements=state.get("pages", "8-12页"))
    user = f"""主题：{state.get('topic')}
受众：{state.get('audience')}
目的：{state.get('purpose')}
补充：{state.get('extra') or '无'}

背景调研信息：
{state.get('background', '')}
"""
    raw = chat(gemini(0.4), user, system=system)
    try:
        data = extract_json_block(raw)
    except Exception as e:
        raise RuntimeError(
            f"大纲 JSON 解析失败: {e}\n模型原始输出前 800 字:\n{raw[:800]}"
        ) from e

    if isinstance(data, dict) and "ppt_outline" in data:
        outline = data["ppt_outline"]
    elif isinstance(data, dict) and {"cover", "parts"} & set(data.keys()):
        outline = data
    else:
        raise RuntimeError(f"大纲结构异常，原始输出前 800 字:\n{raw[:800]}")

    if not isinstance(outline, dict):
        raise RuntimeError("大纲不是对象结构")

    auto = bool(state.get("auto_confirm_outline"))
    return {
        "outline": outline,
        "page_list": flatten_outline(outline),
        "status": "researching_pages" if auto else "waiting_outline_confirm",
        "progress": "大纲已生成" + ("，继续检索各页资料…" if auto else "，等待确认…"),
        "wait_for_outline": not auto,
    }


def node_research_pages(state: PPTState) -> dict:
    """串行检索各页（稳定优先；页数多时可改为并行）。"""
    page_list = state.get("page_list") or []
    results = []
    total = len(page_list)
    for i, page in enumerate(page_list):
        prompt = PAGE_RESEARCH_PROMPT.format(
            topic=state.get("topic", ""),
            audience=state.get("audience", ""),
            purpose=state.get("purpose", ""),
            background=state.get("background", "")[:3000],
            page_kind=page.get("page_kind", "content"),
            page_title=page.get("page_title", ""),
            part_title=page.get("part_title", ""),
            page_key=page.get("page_key", f"p{i}"),
        )
        try:
            raw = chat(grok(0.3), prompt)
            data = extract_json_block(raw)
            if not isinstance(data, dict):
                raise ValueError("research not dict")
            data.setdefault("page_key", page["page_key"])
            data.setdefault("page_title", page["page_title"])
            data.setdefault("page_kind", page.get("page_kind", "content"))
            data.setdefault("bullets", page.get("seed_content") or [])
            results.append(data)
        except Exception as e:
            seed = page.get("seed_content") or []
            if isinstance(seed, list):
                bullets = [str(x) for x in seed] or [page.get("page_title", "")]
            else:
                bullets = [str(seed)]
            results.append(
                {
                    "page_key": page["page_key"],
                    "page_title": page["page_title"],
                    "page_kind": page.get("page_kind", "content"),
                    "bullets": bullets,
                    "sources": [],
                    "error": str(e),
                }
            )

    return {
        "page_research": results,
        "status": "planning",
        "progress": f"已完成 {total} 页资料整理，正在策划版式…",
    }


def node_plan_layouts(state: PPTState) -> dict:
    research = {r["page_key"]: r for r in (state.get("page_research") or [])}
    plans = []
    for page in state.get("page_list") or []:
        r = research.get(page["page_key"], {})
        bullets = r.get("bullets") or page.get("seed_content") or []
        prompt = LAYOUT_PROMPT.format(
            page_kind=page.get("page_kind", "content"),
            page_title=page.get("page_title", ""),
            bullets="\n".join(f"- {b}" for b in bullets),
            page_key=page["page_key"],
        )
        try:
            raw = chat(gemini(0.3), prompt)
            data = extract_json_block(raw)
            if not isinstance(data, dict):
                raise ValueError("layout not dict")
            data.setdefault("page_key", page["page_key"])
            data.setdefault("page_title", page["page_title"])
            data.setdefault("page_kind", page.get("page_kind", "content"))
            plans.append(data)
        except Exception:
            plans.append(
                {
                    "page_key": page["page_key"],
                    "page_title": page["page_title"],
                    "page_kind": page.get("page_kind", "content"),
                    "layout_type": "single_focus" if page.get("page_kind") != "content" else "mixed",
                    "cards": [
                        {
                            "role": "title",
                            "text": page["page_title"],
                            "size_hint": "lg",
                            "visual_hint": "",
                        },
                        {
                            "role": "list",
                            "text": "\n".join(str(b) for b in bullets[:6]),
                            "size_hint": "hero",
                            "visual_hint": "",
                        },
                    ],
                }
            )
    return {
        "layout_plans": plans,
        "status": "designing",
        "progress": "版式策划完成，正在生成 SVG…",
    }


def node_design_svgs(state: PPTState) -> dict:
    import json

    research = {r["page_key"]: r for r in (state.get("page_research") or [])}
    slides = []
    style = state.get("style") or "现代科技、高级感、简洁"
    plans = state.get("layout_plans") or []
    total = len(plans)

    for i, plan in enumerate(plans):
        r = research.get(plan["page_key"], {})
        bullets = r.get("bullets") or []
        prompt = SVG_PROMPT.format(
            style=style,
            page_kind=plan.get("page_kind", "content"),
            page_title=plan.get("page_title", ""),
            layout_json=json.dumps(plan, ensure_ascii=False),
            bullets="\n".join(f"- {b}" for b in bullets),
        )
        try:
            raw = chat(gemini_design(0.5), prompt)
            svg = extract_svg(raw)
            slides.append(
                {
                    "page_key": plan["page_key"],
                    "page_title": plan["page_title"],
                    "page_kind": plan.get("page_kind", "content"),
                    "svg": svg,
                    "error": None,
                }
            )
        except Exception as e:
            # 兜底：简单 SVG，保证链路不中断
            title = plan.get("page_title", "页面")
            lines = "".join(
                f'<text x="80" y="{160 + j * 36}" fill="#e2e8f0" font-size="18" font-family="Microsoft YaHei, sans-serif">{_escape(str(b)[:80])}</text>'
                for j, b in enumerate(bullets[:10])
            )
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <rect width="1280" height="720" fill="#0f172a"/>
  <rect x="40" y="40" width="1200" height="640" rx="24" fill="#1e293b"/>
  <text x="80" y="110" fill="#38bdf8" font-size="36" font-weight="700" font-family="Microsoft YaHei, sans-serif">{_escape(title)}</text>
  {lines}
  <text x="80" y="660" fill="#64748b" font-size="14" font-family="sans-serif">fallback · {i+1}/{total} · {_escape(str(e)[:60])}</text>
</svg>'''
            slides.append(
                {
                    "page_key": plan["page_key"],
                    "page_title": plan["page_title"],
                    "page_kind": plan.get("page_kind", "content"),
                    "svg": svg,
                    "error": str(e),
                }
            )

    return {
        "slides": slides,
        "status": "done",
        "progress": f"完成 {len(slides)} 页 SVG 设计",
        "wait_for_outline": False,
    }


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
