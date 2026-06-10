# Edge-Cloud AI — 边云协同智能检测系统

基于 **YOLO26n + OpenVINO** 的边缘端实时缺陷检测 + **LangChain Agent** 云端深度分析 + **Vue 3** 管理平台。

## 项目结构

```
edge-cloud-ai/
├── edge/                     # 边缘端（工控机）
│   ├── main.py               # 入口：CLI 模式 / HTTP 服务模式
│   ├── server.py             # HTTP 服务（REST 控制 + MJPEG 流）
│   ├── stream.py             # 独立 MJPEG 流模块（CLI --web-stream 用）
│   ├── config.py             # 边缘端统一配置入口
│   ├── inference/detector.py # YOLO26n + OpenVINO 推理引擎
│   ├── capture/camera.py     # 相机/视频采集
│   ├── classify/             # 缺陷分级 & 本地告警
│   ├── tracking.py           # 帧间跟踪去重
│   ├── network/
│   │   ├── mqtt_client.py   # MQTT 边缘客户端（发布缺陷 + 订阅告警）
│   │   └── http_client.py   # 云端 HTTP 上传（MQTT 不可用时回退）
│   ├── test/                 # 测试视频（.gitignore 排除）
│   └── training/             # 模型训练流水线
│       ├── config.py         # 训练配置（超参、路径、类别）
│       ├── scripts/          # 训练脚本（5步）
│       ├── data/             # NEU-DET 原始数据
│       ├── dataset/          # YOLO 格式数据集
│       ├── runs/             # 训练产物
│       └── ir/               # OpenVINO IR 导出
├── cloud/                    # 云端（FastAPI + PostgreSQL）
│   ├── main.py               # FastAPI 入口（lifespan 自动启动 MQTT）
│   ├── agent/                # AI Agent 引擎
│   │   ├── orchestrator.py   # LangGraph ReAct 编排
│   │   ├── prompts.py        # 系统提示词
│   │   ├── models/           # LLM 模型提供者
│   │   └── toolkit/          # 工具集（缺陷查询/统计/详情）
│   ├── api/
│   │   ├── routes_detect.py  # 检测上传 + 自动 Agent 复核
│   │   ├── routes_chat.py    # SSE 流式对话
│   │   └── routes_defects.py # 缺陷记录查询
│   ├── mqtt/handler.py       # MQTT 云端处理器（订阅 + 桥接 asyncio）
│   ├── db/models.py          # ORM（含 agent_review 存储）
│   └── schemas/              # Pydantic 模型
├── web/                      # 前端管理平台（Vue 3 + Vite，单页）
│   ├── src/
│   │   ├── views/Monitor.vue # 边端联动页（全功能）
│   │   ├── api/client.js     # 云端 API + 边端 API
│   │   └── router/index.js   # 路由
│   ├── package.json
│   └── vite.config.js
├── docker/
│   ├── docker-compose.yml    # PostgreSQL + pgvector + Mosquitto MQTT
│   └── mosquitto.conf        # MQTT Broker 配置（开发模式匿名访问）
├── docs/                     # 需求文档 & 课程设计资料
├── pyproject.toml            # 项目配置 & 依赖
├── start.ps1                 # 一键启动脚本 (Windows PowerShell)
├── start.sh                  # 一键启动脚本 (Bash / Linux / macOS)
├── .env.example              # 环境变量模板
└── .gitignore
```

## 环境准备

### 1. 安装 Python 依赖

本项目使用 **uv** 管理依赖（推荐），也兼容 pip。

```bash
# 方式一：uv（推荐）
pip install uv          # 如未安装
uv sync                 # 自动创建 venv 并安装所有依赖

# 方式二：pip
pip install -e .
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写必要信息：

| 变量               | 说明                              | 默认值           |
| ------------------ | --------------------------------- | ---------------- |
| `DB_PASSWORD`    | 数据库密码                        | —               |
| `MQTT_PASSWORD`  | MQTT 密码（可选）                 | —               |
| `JWT_SECRET_KEY` | JWT 签名密钥                      | 生产环境务必修改 |

> **LLM 配置已从 `.env` 移除**，改为通过 Web 端或 API 运行时配置，API Key 仅存内存、不落盘。详见[§4 MQTT 通信架构](#4-mqtt-通信架构)后的 LLM 配置说明。

### 3. 数据库 & MQTT

项目使用 PostgreSQL（pgvector）和 Mosquitto MQTT Broker。

**Docker 一键启动（推荐）**：

```bash
docker compose -f docker/docker-compose.yml up -d
```

启动后即可获得：
- PostgreSQL 数据库 `localhost:5432`
- Mosquitto MQTT Broker `localhost:1883`

数据库连接信息（在 `.env` 中配置）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DB_HOST` | 数据库地址 | `localhost` |
| `DB_PORT` | 数据库端口 | `5432` |
| `DB_NAME` | 数据库名 | `edge_cloud` |
| `DB_USER` | 数据库用户 | `edgecloud` |
| `DB_PASSWORD` | 数据库密码 | — |

MQTT 配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `mqtt_broker_host` | MQTT 地址 | `localhost` |
| `mqtt_broker_port` | MQTT 端口 | `1883` |

> 边缘端默认通过 MQTT 上传缺陷数据，MQTT 不可用时自动回退 HTTP 上传。

### 4. MQTT 通信架构

系统通过 MQTT 实现边缘端与云端的**双向异步通信**：

```
Edge  ──publish──> edge/{device_id}/defect/upload ──> Cloud (订阅)
Edge  <──subscribe── edge/{device_id}/alert <── Cloud (发布)
```

| 组件 | Topic | 方向 | 说明 |
|------|-------|------|------|
| 缺陷上传 | `edge/{device_id}/defect/upload` | Edge → Cloud | 检测到需云端处理的缺陷时发布，payload 含检测结果 + base64 帧图像 |
| 告警推送 | `edge/{device_id}/alert` | Cloud → Edge | Agent 复核完成后推送告警/建议回边端 |
| 云端通配订阅 | `edge/+/defect/upload` | — | Cloud 用 `+` 通配符订阅所有设备的上传 |

**MQTT 客户端的启动由应用自动完成，无需手动操作**：

| 时机 | 组件 | 触发位置 |
|------|------|----------|
| Cloud 启动 | `cloud/mqtt/handler.py:24` | `cloud/main.py` 的 FastAPI `lifespan` 自动调用 `start_mqtt()` |
| Edge CLI 启动 | `edge/network/mqtt_client.py:45` | `edge/main.py:82` 创建 `EdgeMQTTClient` 并调用 `connect()` |
| Edge Server 启动 | `edge/network/mqtt_client.py:45` | `edge/server.py:217` 在 `EdgeServer.start()` 中自动连接 |

**MQTT 不可用时的降级策略**：
- 边缘端尝试 MQTT 连接，失败后自动回退到 HTTP `POST /api/v1/detect/upload` 上传
- 云端尝试 MQTT 连接，失败后打印警告并继续运行（仅影响 MQTT 通道，HTTP 上传仍正常）
- Broker 恢复后客户端自动重连（5s 间隔）

### 5. LLM 配置（运行时切换）

LLM 不再通过 `.env` 配置，改为运行时管理，API Key **仅存内存、不落盘**。

**Web 端操作**：点击顶部栏 🤖 模型名 → 选择模型 → 填入 Key → 切换，无需重启。

**API 操作**：
```bash
# 查看当前配置（不返回 Key）
curl http://localhost:8000/api/v1/llm/config

# 切换模型
curl -X PUT http://localhost:8000/api/v1/llm/config \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","base_url":"https://api.deepseek.com/v1","api_key":"sk-xxx"}'
```

首次使用时需通过 API/Web 端配置 API Key，否则 Agent 复核功能不工作。

---

## 训练流程

YOLO26n 在 NEU-DET 钢材表面缺陷数据集上微调，共 **5 个步骤**，按顺序执行。

### 硬件建议

| 配置               | 训练时间（100 epochs） |
| ------------------ | ---------------------- |
| CPU                | ~2-3 小时              |
| NVIDIA GPU (CUDA)  | ~10-15 分钟            |
| Apple M 系列 (MPS) | ~20-30 分钟            |

> 默认使用 CPU。有 GPU 时，修改 `edge/training/config.py` 中 `DEVICE = "cpu"` 改为 `"cuda"` 或 `"mps"`。

### 第一步：下载数据集（已完成，可跳过）

NEU-DET 数据集已下载到 `edge/training/data/`，格式也已转换到 `edge/training/dataset/`（1439 张训练 + 360 张验证），**直接从第三步训练开始即可**。

如果需要在其他机器上重新下载：

```bash
python -m edge.training.scripts.download   # 从 Kaggle 下载原始数据
python -m edge.training.scripts.convert    # VOC XML → YOLO txt 格式
```

> 下载需要 Kaggle 账号，首次运行按终端提示登录。

### 第二步：训练

使用 YOLO26n（COCO 预训练权重）在 NEU-DET 上微调。

```bash
python -m edge.training.scripts.train
```

- 模型：`yolo26n.pt`（2.4M 参数，自动下载）
- 100 epochs，640×640 输入，batch=8
- 产物：`edge/training/runs/detect/neu-det/weights/best.pt`
- 如显存不足，修改 `edge/training/config.py` 中 `BATCH = 8` 调小

### 第三步：导出 OpenVINO IR

将 PyTorch 模型转为 OpenVINO IR 格式（FP16），用于边缘端推理。

```bash
python -m edge.training.scripts.export
```

- 导出到 `edge/training/ir/yolo26n_neu_det.xml` + `.bin`
- 同时复制到 `edge/public/neu-det/` 部署目录
- IR 模型大小约 9.5 MB，边缘端 CPU 推理 ~40ms/张

### 第四步：验证

用验证集图片测试 IR 模型是否正确加载和推理。

```bash
python -m edge.training.scripts.validate
```

- 加载 IR 模型，跑 10 张验证图
- 输出每张图的检测结果和推理耗时
- 全部通过即训练完成

### 训练汇总

```bash
# 直接从训练开始（数据已准备好）
python -m edge.training.scripts.train   && \
python -m edge.training.scripts.export  && \
python -m edge.training.scripts.validate
```

---

## 运行系统

### 边缘端

**服务模式（Web 端控制，推荐联调）**

边端启动 HTTP 服务，由前端选择摄像头/视频并控制检测启停。

```bash
python -m edge.main --server
```

| 端点 | 方法 | 说明 |
|------|------|------|
| `/stream` | `GET` | MJPEG 视频流（含 YOLO 标注） |
| `/api/status` | `GET` | 当前检测状态 |
| `/api/configure` | `POST` | 设置视频源、置信度等参数 |
| `/api/start` | `POST` | 开始检测 |
| `/api/stop` | `POST` | 停止检测 |
| `/api/summary` | `GET` | 检测汇总 |

**CLI 模式（本地直接运行）**

```bash
# 使用默认相机
python -m edge.main

# 使用视频文件
python -m edge.main -s test.mp4

# CLI + MJPEG 流（Web 端可观看，不能控制）
python -m edge.main -s test.mp4 --web-stream

# 不上传云端（本地测试）
python -m edge.main -s video.mp4 --no-upload
```

CLI 参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-s, --source` | 视频路径或相机 ID | `0` |
| `--fps` | 处理帧率 | — |
| `--conf` | YOLO 置信度阈值 | `0.3` |
| `--conf-edge` | 边缘本地处理阈值 | `0.5` |
| `--no-show` | 不显示 OpenCV 窗口 | — |
| `--no-upload` | 不上传云端 | — |
| `--server` | HTTP 服务模式 | — |
| `--web-stream` | CLI 模式开启 MJPEG 流 | — |
| `--web-port` | HTTP/MJPEG 端口 | `8080` |
| `--api-url` | 云端 API 地址 | `http://localhost:8000/api/v1` |

### 云端（API 服务）

```bash
python -m cloud.main
```

- FastAPI 服务启动在 `http://0.0.0.0:8000`
- Swagger 文档：`http://localhost:8000/docs`

| 方法 | 接口 | 说明 |
|------|------|------|
| `POST` | `/api/v1/detect/upload` | 缺陷上传（multipart），上传后自动触发 Agent 后台复核 |
| `GET` | `/api/v1/defects?limit=50` | 查询最近缺陷记录（含 `agent_review` 复核结果） |
| `POST` | `/api/v1/chat` | AI 对话（SSE 流式），也可独立使用 |

### 前端管理平台

单页应用，在浏览器内完成全流程：选择视频源 → 控制检测 → 实时查看 YOLO 标注画面 → 缺陷自动 Agent 复核 → 检测结束汇总。

```bash
cd web
npm install
npm run dev        # 开发服务器 → http://localhost:5173
```

页面布局：

```
   [摄像头 ● / 视频文件 ○] [置信度 0.3] [▶ 开始检测]
┌──────────────────────────┬──────────────────────────┐
│                          │ 缺陷记录 & Agent 复核      │
│     MJPEG 视频流         │ ┌────────────────────────┐│
│   (含 YOLO 标注框)       │ │ 12:34 crazing    72%   ▾││
│                          │ │  🤖 Agent 复核结论      ││
│                          │ │  "该裂纹长度超过标准..."  ││
│                          │ │  ▸ 使用工具: defect_stats││
│                          │ ├────────────────────────┤│
│                          │ │ 12:35 inclusion  58%   ▸││
│                          │ └────────────────────────┘│
│                          │ [检测完成] 总 5 | 复核 3    │
└──────────────────────────┴──────────────────────────┘
```

- **左栏** — 控制面板（视频源选择 + 置信度 + 启动/停止)+ 实时视频
- **右栏** — 缺陷记录列表，点击展开查看 Agent 复核结论；检测停止后显示汇总

### 全链路启动（一键脚本）

**Windows (PowerShell)**：
```powershell
.\start.ps1              # 启动全部服务
.\start.ps1 --no-web     # 跳过 Web 前端
```

**Git Bash / Linux / macOS**：
```bash
bash start.sh            # 启动全部服务
bash start.sh --no-web   # 跳过 Web 前端
```

脚本启动流程（5 步）：

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1/5 | 数据库连通性检测 | 通过 `.env` 配置连接 PostgreSQL，失败则退出 |
| 2/5 | MQTT Broker 检测 | socket 连通性检查，失败则警告但不中断（回退 HTTP） |
| 3/5 | 启动 Cloud API | `python -m cloud.main` → 端口 8000，lifespan 中自动连接 MQTT |
| 4/5 | 启动 Edge Server | `python -m edge.main --server` → 端口 8080，启动时自动连接 MQTT |
| 5/5 | 启动 Web 前端 | `npm run dev` → 端口 5173 |

`Ctrl+C` 一键停止所有服务。

启动后访问：
| 服务 | 地址 |
|------|------|
| Web 管理端 | http://localhost:5173 |
| Cloud API 文档 | http://localhost:8000/docs |
| Edge 流 | http://localhost:8080/stream |
| Edge 状态 | http://localhost:8080/api/status |

### 全链路启动（手动分步）

```bash
# 终端 1: 云端（含自动 Agent 复核）
python -m cloud.main

# 终端 2: 边端（服务模式，等待 Web 控制）
python -m edge.main --server

# 终端 3: 前端
cd web && npm run dev
```

### 生成测试视频

项目不含钢材缺陷视频（NEU-DET 是图像数据集），可用验证集图片合成：

```bash
python -c "
from pathlib import Path
import cv2, random

img_dir = Path('edge/training/dataset/images/val')
imgs = sorted(img_dir.glob('*.jpg'))
random.seed(42)
random.shuffle(imgs)

target = 640
fourcc = cv2.VideoWriter_fourcc(*'MJPG')
writer = cv2.VideoWriter('edge/test/neu_det_test.avi', fourcc, 15, (target, target))

for p in imgs[:100]:
    frame = cv2.imread(str(p))
    frame = cv2.resize(frame, (target, target))
    if len(frame.shape) == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    for _ in range(30):       # 每张图显示 2 秒
        writer.write(frame)
writer.release()
print('视频已生成: edge/test/neu_det_test.avi')
"
```

用生成的视频测试：
```bash
python -m edge.main -s edge/test/neu_det_test.avi --no-upload
```

---

## 6 类钢材缺陷

| 类别   | 英文名          | 说明           |
| ------ | --------------- | -------------- |
| 裂纹   | crazing         | 表面网状裂纹   |
| 夹杂   | inclusion       | 非金属夹杂物   |
| 斑块   | patches         | 表面不规则斑块 |
| 麻点   | pitted_surface  | 点状凹坑       |
| 氧化皮 | rolled-in_scale | 轧制嵌入氧化皮 |
| 划痕   | scratches       | 机械划伤       |

---

## 许可证

MIT
