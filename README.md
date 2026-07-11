# PPT Agent - LangGraph 多阶段生成

基于「需求调研 → 大纲 → 资料 → 策划 → SVG 设计」工作流。

## 功能

- 简易 Web UI（可嵌入你的网站）
- 中转 API（OpenAI 兼容协议，Grok + Gemini）
- 优先 SVG 预览（1280×720 Bento Grid）
- 大纲可人工确认后再继续设计

## 关于「直接 PPT 能否改文字」

| 导出方式 | 能否在 PPT 里改字 | 说明 |
|---------|------------------|------|
| SVG 当图片插入 | ❌ | 整页位图/矢量图，点选不到文字 |
| SVG 用 Office 插入并「转换为形状」 | 部分可以 | 部分文本可能变成形状，不稳 |
| 解析 SVG → python-pptx 文本框 | ✅ 推荐 | 需要二次转换逻辑（后续可加） |
| 直接生成 PPTX（文本框+形状） | ✅ 最好改 | 与当前 SVG 路线是另一条产线 |

**当前版本优先 SVG 预览**（效果好、迭代快）。需要「进 PPT 可改字」时，建议第二期做 SVG→PPTX 文本映射，或并行一条 native PPTX 产线。

## 快速开始

```bash
cd ppt-agent
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env 填入中转地址和 key
python -m app.main
```

浏览器打开：http://127.0.0.1:8787

## 环境变量

见 `.env.example`。中转通常是 OpenAI 兼容：

```
LLM_BASE_URL=https://your-proxy.com/v1
LLM_API_KEY=sk-xxx
GROK_MODEL=grok-3
GEMINI_MODEL=gemini-2.5-flash
```

## 集成到你的网站

1. **iframe**：`<iframe src="https://your-domain/ppt-agent/" style="width:100%;height:100vh;border:0">`
2. **反代**：Nginx/Caddy 把 `/ppt-agent/` 转到本服务
3. **API**：前端只调 `/api/jobs`，自己做 UI（接口见下方）

### 主要 API

- `POST /api/jobs` — 创建任务 `{topic, audience, purpose, pages, style, extra}`
- `GET /api/jobs/{id}` — 查状态与结果
- `POST /api/jobs/{id}/confirm-outline` — 确认/修改大纲后继续
- `GET /api/jobs/{id}/pages/{i}.svg` — 单页 SVG

## 目录

```
ppt-agent/
  app/
    main.py          # FastAPI
    graph.py         # LangGraph 编排
    state.py
    config.py
    llm.py           # 中转客户端
    prompts.py
    nodes/
  static/            # 简易前端
  outputs/           # 生成的 SVG
  .env.example
```
