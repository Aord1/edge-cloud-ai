# Edge-Cloud AI — 边云协同智能检测系统

基于 **YOLO26n + OpenVINO** 的边缘端实时缺陷检测 + **LangChain Agent** 云端深度分析 + **Vue 3** 管理平台。

## 项目结构

```
edge-cloud-ai/
├── edge/                     # 边缘端（工控机）
│   ├── main.py               # 入口：采集 → 检测 → 分类 → 告警/上传
│   ├── inference/detector.py # YOLO26n + OpenVINO 推理引擎
│   ├── capture/camera.py     # 相机/视频采集
│   ├── classify/             # 缺陷分级 & 本地告警
│   ├── network/http_client.py# 云端上传
│   └── training/             # 模型训练流水线
│       ├── config.py         # 训练配置（超参、路径、类别）
│       ├── scripts/          # 训练脚本（5步）
│       ├── data/             # NEU-DET 原始数据
│       ├── dataset/          # YOLO 格式数据集
│       ├── runs/             # 训练产物
│       └── ir/               # OpenVINO IR 导出
├── cloud/                    # 云端（FastAPI + PostgreSQL）
│   ├── main.py               # FastAPI 入口
│   ├── api/routes_detect.py  # 检测上传接口
│   └── db/models.py          # ORM 模型
├── docker/
│   └── docker-compose.yml    # PostgreSQL + pgvector
├── docs/                     # 需求文档 & 课程设计资料
├── pyproject.toml            # 项目配置 & 依赖
└── .env.example              # 环境变量模板
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

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DB_PASSWORD` | 数据库密码 | — |
| `LLM_API_KEY` | 大模型 API Key（OpenAI/兼容接口） | — |
| `MQTT_PASSWORD` | MQTT 密码（可选） | — |
| `JWT_SECRET_KEY` | JWT 签名密钥 | 生产环境务必修改 |

### 3. 启动数据库（可选，训练不需要）

```bash
docker compose -f docker/docker-compose.yml up -d
```

---

## 训练流程

YOLO26n 在 NEU-DET 钢材表面缺陷数据集上微调，共 **5 个步骤**，按顺序执行。

### 硬件建议

| 配置 | 训练时间（100 epochs） |
|------|----------------------|
| CPU | ~2-3 小时 |
| NVIDIA GPU (CUDA) | ~10-15 分钟 |
| Apple M 系列 (MPS) | ~20-30 分钟 |

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

### 边缘端（检测）

```bash
# 使用默认相机
python -m edge.main

# 使用视频文件
python -m edge.main -s edge/test/traffic_trim.mp4

# 不上传云端（本地测试）
python -m edge.main -s video.mp4 --no-upload
```

CLI 参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-s, --source` | 视频路径或相机 ID | `0`（默认相机） |
| `--fps` | 处理帧率 | — |
| `--conf` | 检测置信度阈值 | `0.5` |
| `--no-show` | 不显示画面 | — |
| `--no-upload` | 不上传云端 | — |
| `--api-url` | 云端 API 地址 | `http://localhost:8000/api/v1` |

### 云端（API 服务）

```bash
python -m cloud.main
```

- FastAPI 服务启动在 `http://0.0.0.0:8000`
- API 文档：`http://localhost:8000/docs`
- 接口：`POST /api/v1/detect/upload` — 接收检测结果 + 关键帧

---

## 6 类钢材缺陷

| 类别 | 英文名 | 说明 |
|------|--------|------|
| 裂纹 | crazing | 表面网状裂纹 |
| 夹杂 | inclusion | 非金属夹杂物 |
| 斑块 | patches | 表面不规则斑块 |
| 麻点 | pitted_surface | 点状凹坑 |
| 氧化皮 | rolled-in_scale | 轧制嵌入氧化皮 |
| 划痕 | scratches | 机械划伤 |

---

## 许可证

MIT
