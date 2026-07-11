# 部署到服务器（Docker + IP 直接访问）

适用：CentOS / Ubuntu 云服务器，2 核 2G 起。以 IP:8787 直接访问。

> 本项目主要调用外部中转 API，不在本地跑模型，2G 内存足够。

---

## 一、装 Docker

```bash
# 阿里云镜像加速安装（推荐，国内快）
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun

# 开机自启并立即启动
systemctl enable --now docker

# 验证
docker --version
docker compose version
```

> 若 `curl` 脚本因系统源报错（CentOS 8 已 EOL 常见），见文末「换源」。

---

## 二、拉代码

```bash
cd /opt
git clone https://github.com/burulianghuan/ppt-agent.git
cd ppt-agent
```

---

## 三、配置 .env（填中转 key）

```bash
cp .env.example .env
vi .env      # 或 nano .env
```

填入你的中转地址、key、模型名。`HOST` 不用改，容器会强制用 `0.0.0.0`。

---

## 四、构建并启动

```bash
docker compose up -d --build
```

首次构建要装系统依赖和 Python 包，约 3-8 分钟。完成后：

```bash
docker compose logs -f        # 看日志，出现 Uvicorn running 即成功
# Ctrl+C 退出日志（容器仍在后台跑）
```

---

## 五、开放端口

**阿里云安全组**（必须做，否则外网访问不了）：

1. 控制台 → 该实例 → 安全组 → 配置规则 → 入方向
2. 手动添加：
   - 协议类型：**自定义 TCP**
   - 端口范围：**8787/8787**
   - 授权对象：**0.0.0.0/0**（所有人，或填你的 IP 更安全）

服务器本地防火墙（若开着 firewalld）：

```bash
firewall-cmd --permanent --add-port=8787/tcp
firewall-cmd --reload
```

---

## 六、访问

浏览器打开：

```
http://<你的公网IP>:8787
```

---

## 常用运维命令

```bash
docker compose ps            # 查看状态
docker compose logs -f       # 看日志
docker compose restart       # 重启
docker compose down          # 停止并删除容器
docker compose up -d --build # 改代码后重新构建启动

# 更新代码
git pull && docker compose up -d --build
```

生成的 SVG/PPTX 存在宿主机 `./outputs/`，容器重建不丢。

---

## 附：CentOS 8 换源（仅当第一步报源错误）

CentOS 8 官方源已下线，改用阿里云 vault：

```bash
sed -i 's|mirrorlist=|#mirrorlist=|g' /etc/yum.repos.d/CentOS-*.repo
sed -i 's|#baseurl=http://mirror.centos.org|baseurl=https://mirrors.aliyun.com|g' /etc/yum.repos.d/CentOS-*.repo
dnf clean all && dnf makecache
```

然后重试第一步装 Docker。

---

## 说明

- **PPTX 渲染**：容器内用 cairosvg（已装 libcairo2 + 中文字体 noto-cjk），无需浏览器。
- **安全**：`.env` 含 API key，已被 `.gitignore`/`.dockerignore` 排除，不会进仓库或镜像。
- **IP 明文访问**：当前是 HTTP，端口对外暴露。要正式对外请加域名 + Nginx/Caddy + HTTPS。
