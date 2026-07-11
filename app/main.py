"""PPT Agent Web API + 简易前端。"""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.config import get_settings
from app.graph import compile_app
from app.state import JobRequest, JobStatus, SlideResult

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

settings = get_settings()
checkpointer = MemorySaver()
graph = compile_app(checkpointer)

# 内存任务表（集成到网站时可换成 Redis/DB）
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


app = FastAPI(title="PPT Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def _public_status(job_id: str) -> JobStatus:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "任务不存在")
        slides = [SlideResult(**s) for s in job.get("slides") or []]
        return JobStatus(
            id=job_id,
            status=job.get("status", "queued"),
            topic=job.get("topic", ""),
            progress=job.get("progress", ""),
            error=job.get("error"),
            outline=job.get("outline"),
            slides=slides,
            background=job.get("background", ""),
        )


def _save_svgs(job_id: str, slides: list[dict]) -> None:
    out = settings.output_path / job_id
    out.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(slides):
        name = f"{i:02d}_{s.get('page_key', 'page')}.svg"
        (out / name).write_text(s.get("svg") or "", encoding="utf-8")
    manifest = [
        {
            "index": i,
            "page_key": s.get("page_key"),
            "page_title": s.get("page_title"),
            "page_kind": s.get("page_kind"),
            "error": s.get("error"),
        }
        for i, s in enumerate(slides)
    ]
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _run_until_pause_or_end(job_id: str, input_payload: Any) -> None:
    config = {"configurable": {"thread_id": job_id}}
    try:
        with _lock:
            _jobs[job_id]["status"] = "researching"
            _jobs[job_id]["progress"] = "开始背景调研…"

        result = graph.invoke(input_payload, config=config)

        # 检查是否 interrupt
        state = graph.get_state(config)
        if state.next:
            # 暂停在 wait_outline
            values = state.values or {}
            with _lock:
                _jobs[job_id].update(
                    {
                        "status": values.get("status") or "waiting_outline_confirm",
                        "progress": values.get("progress") or "等待确认大纲",
                        "outline": values.get("outline"),
                        "background": values.get("background") or "",
                    }
                )
            return

        values = result if isinstance(result, dict) else (state.values or {})
        slides = values.get("slides") or []
        # slides 可能因 Annotated add 重复，按 page_key 去重保序
        slides = _dedupe_slides(slides)
        _save_svgs(job_id, slides)
        with _lock:
            _jobs[job_id].update(
                {
                    "status": values.get("status") or "done",
                    "progress": values.get("progress") or "完成",
                    "outline": values.get("outline"),
                    "background": values.get("background") or "",
                    "slides": slides,
                    "error": values.get("error"),
                }
            )
    except Exception as e:
        traceback.print_exc()
        with _lock:
            _jobs[job_id].update(
                {
                    "status": "error",
                    "error": str(e),
                    "progress": "失败",
                }
            )


def _dedupe_slides(slides: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for s in slides:
        key = s.get("page_key") or s.get("page_title")
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _resume_job(job_id: str, resume_payload: dict) -> None:
    config = {"configurable": {"thread_id": job_id}}
    try:
        with _lock:
            _jobs[job_id]["status"] = "researching_pages"
            _jobs[job_id]["progress"] = "大纲已确认，继续生成…"

        result = graph.invoke(Command(resume=resume_payload), config=config)
        state = graph.get_state(config)
        values = result if isinstance(result, dict) else (state.values or {})
        slides = _dedupe_slides(values.get("slides") or [])
        _save_svgs(job_id, slides)
        with _lock:
            _jobs[job_id].update(
                {
                    "status": values.get("status") or "done",
                    "progress": values.get("progress") or "完成",
                    "outline": values.get("outline"),
                    "background": values.get("background") or "",
                    "slides": slides,
                    "error": values.get("error"),
                }
            )
    except Exception as e:
        traceback.print_exc()
        with _lock:
            _jobs[job_id].update(
                {
                    "status": "error",
                    "error": str(e),
                    "progress": "失败",
                }
            )


@app.get("/", response_class=HTMLResponse)
def index():
    index_file = STATIC / "index.html"
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    s = get_settings()
    return {
        "ok": True,
        "has_grok_key": bool(s.grok_key()),
        "has_gemini_key": bool(s.gemini_key()),
        "grok_base_url": s.grok_url(),
        "gemini_base_url": s.gemini_url(),
        "grok_model": s.grok_model,
        "gemini_model": s.gemini_model,
        "design_model": s.design_model,
    }


@app.post("/api/jobs", response_model=JobStatus)
def create_job(req: JobRequest):
    s = get_settings()
    if not s.grok_key() or not s.gemini_key():
        raise HTTPException(
            400,
            "请先在 .env 配置 GROK_API_KEY 与 GEMINI_API_KEY（可分 key）",
        )

    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "status": "queued",
            "topic": req.topic,
            "progress": "排队中",
            "outline": None,
            "slides": [],
            "background": "",
            "error": None,
            "request": req.model_dump(),
        }

    init_state = {
        "job_id": job_id,
        "topic": req.topic,
        "audience": req.audience,
        "purpose": req.purpose,
        "pages": req.pages,
        "style": req.style,
        "extra": req.extra,
        "auto_confirm_outline": req.auto_confirm_outline,
        "page_research": [],
        "slides": [],
        "status": "queued",
        "progress": "排队中",
        "wait_for_outline": not req.auto_confirm_outline,
    }

    t = threading.Thread(
        target=_run_until_pause_or_end,
        args=(job_id, init_state),
        daemon=True,
    )
    t.start()
    return _public_status(job_id)


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    # 轮询时顺便同步 graph 中间状态（若有）
    config = {"configurable": {"thread_id": job_id}}
    try:
        state = graph.get_state(config)
        if state and state.values:
            values = state.values
            with _lock:
                if job_id in _jobs and _jobs[job_id]["status"] not in ("done", "error"):
                    if values.get("status"):
                        _jobs[job_id]["status"] = values["status"]
                    if values.get("progress"):
                        _jobs[job_id]["progress"] = values["progress"]
                    if values.get("outline"):
                        _jobs[job_id]["outline"] = values["outline"]
                    if values.get("background"):
                        _jobs[job_id]["background"] = values["background"]
                    if values.get("slides"):
                        _jobs[job_id]["slides"] = _dedupe_slides(values["slides"])
    except Exception:
        pass
    return _public_status(job_id)


class ConfirmOutlineBody(BaseModel):
    action: str = Field(default="confirm", description="confirm | edit | cancel")
    outline: Optional[dict[str, Any]] = None


@app.post("/api/jobs/{job_id}/confirm-outline", response_model=JobStatus)
def confirm_outline(job_id: str, body: ConfirmOutlineBody):
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "任务不存在")
        if job.get("status") != "waiting_outline_confirm":
            raise HTTPException(400, f"当前状态不可确认大纲: {job.get('status')}")

    t = threading.Thread(
        target=_resume_job,
        args=(job_id, body.model_dump()),
        daemon=True,
    )
    t.start()
    return _public_status(job_id)


@app.get("/api/jobs/{job_id}/pages/{index}.svg")
def get_page_svg(job_id: str, index: int):
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "任务不存在")
        slides = job.get("slides") or []
        if index < 0 or index >= len(slides):
            raise HTTPException(404, "页面不存在")
        svg = slides[index].get("svg") or ""
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/jobs/{job_id}/download.zip")
def download_zip(job_id: str):
    """打包 outputs/{job_id} 为 zip（惰性创建）。"""
    import io
    import zipfile

    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "任务不存在")
        slides = job.get("slides") or []
        if not slides:
            raise HTTPException(400, "尚无生成页面")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, s in enumerate(slides):
            name = f"{i:02d}_{s.get('page_key', 'page')}.svg"
            zf.writestr(name, s.get("svg") or "")
        zf.writestr(
            "outline.json",
            json.dumps(job.get("outline") or {}, ensure_ascii=False, indent=2),
        )
    buf.seek(0)
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="ppt-{job_id}.zip"'},
    )


# PPTX 生成较慢（逐页用 Edge 渲染兜底图），用锁避免同一任务并发重复构建
_pptx_locks: dict[str, threading.Lock] = {}
_pptx_locks_guard = threading.Lock()


def _pptx_lock_for(job_id: str) -> threading.Lock:
    with _pptx_locks_guard:
        lk = _pptx_locks.get(job_id)
        if lk is None:
            lk = threading.Lock()
            _pptx_locks[job_id] = lk
        return lk


@app.get("/api/jobs/{job_id}/download.pptx")
def download_pptx(job_id: str):
    """把该任务的 SVG 合成可编辑 PPTX（矢量 SVG + PNG 兜底图）。

    首次调用会用 headless Edge 逐页渲染，较慢；生成后缓存到磁盘，再次调用秒回。
    """
    svg_dir = settings.output_path / job_id
    disk_svgs = list(svg_dir.glob("*.svg")) if svg_dir.exists() else []

    with _lock:
        job = _jobs.get(job_id)
        slides = (job.get("slides") if job else None) or []

    # 内存里有任务但 SVG 还没落地，补写；磁盘已有 SVG 则可脱离内存直接用（重启后仍可下载）
    if slides and not disk_svgs:
        _save_svgs(job_id, slides)
        disk_svgs = list(svg_dir.glob("*.svg"))

    if not disk_svgs:
        if job is None:
            raise HTTPException(404, "任务不存在或已过期")
        raise HTTPException(400, "尚无生成页面")

    pptx_path = svg_dir / "slides.pptx"

    lock = _pptx_lock_for(job_id)
    with lock:
        # 已有且比最新 SVG 新则直接用
        need_build = True
        if pptx_path.exists():
            try:
                newest_svg = max(
                    (p.stat().st_mtime for p in svg_dir.glob("*.svg")),
                    default=0,
                )
                if pptx_path.stat().st_mtime >= newest_svg:
                    need_build = False
            except OSError:
                need_build = True

        if need_build:
            try:
                from svg_to_pptx import build_pptx
            except Exception as e:  # pragma: no cover
                raise HTTPException(
                    500, f"未找到转换模块 svg_to_pptx: {e}"
                ) from e
            try:
                build_pptx(svg_dir, pptx_path)
            except Exception as e:
                traceback.print_exc()
                raise HTTPException(
                    500,
                    f"PPTX 生成失败: {e}（通常是缺少 Edge 渲染器，"
                    f"或 SVG 内容异常）",
                ) from e

    if not pptx_path.exists():
        raise HTTPException(500, "PPTX 未生成")

    return FileResponse(
        str(pptx_path),
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "presentationml.presentation"
        ),
        filename=f"ppt-{job_id}.pptx",
    )


def main():
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.host,
        port=s.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
