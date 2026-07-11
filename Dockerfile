# PPT Agent Docker 镜像
# python:3.12-slim + cairosvg 渲染 + 中文字体
FROM python:3.12-slim

# 系统依赖：
# - libcairo2 等：cairosvg 渲染 SVG->PNG
# - fonts-noto-cjk：SVG 里的中文字体（否则中文渲染成方块）
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt cairosvg

# 再拷代码
COPY . .

# 容器内监听所有网卡，端口 8787
ENV HOST=0.0.0.0 \
    PORT=8787 \
    OUTPUT_DIR=/app/outputs

EXPOSE 8787

CMD ["python", "-m", "app.main"]
