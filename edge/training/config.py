"""训练模块共享配置 — 路径、类别、超参数。"""

from __future__ import annotations

from pathlib import Path

# ── 目录 ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent          # project14/
TRAINING_DIR = Path(__file__).resolve().parent                 # edge/training/
DATA_DIR = TRAINING_DIR / "data"                               # 原始下载
DATASET_DIR = TRAINING_DIR / "dataset"                         # YOLO 格式
RUNS_DIR = TRAINING_DIR / "runs"                               # 训练产出
IR_DIR = TRAINING_DIR / "ir"                                   # OpenVINO 导出
DEPLOY_DIR = ROOT / "edge" / "public" / "neu-det"              # 部署目标

# ── 数据 ──────────────────────────────────────────────────
DATA_YAML = DATASET_DIR / "data.yaml"

CLASSES = [
    "crazing",          # 裂纹
    "inclusion",        # 夹杂
    "patches",          # 斑块
    "pitted_surface",   # 麻点
    "rolled-in_scale",  # 氧化皮
    "scratches",        # 划痕
]

CLASS2ID: dict[str, int] = {c: i for i, c in enumerate(CLASSES)}

# ── 训练 ──────────────────────────────────────────────────
MODEL_NAME = "yolo26n.pt"
EPOCHS = 100
IMGSZ = 640
BATCH = 8
DEVICE = "cpu"

# ── IR 导出 ───────────────────────────────────────────────
IR_XML = IR_DIR / "yolo26n_neu_det.xml"
IR_BIN = IR_DIR / "yolo26n_neu_det.bin"

# ── 初始化 ─────────────────────────────────────────────────
for _d in [DATA_DIR, DATASET_DIR, RUNS_DIR, IR_DIR, DEPLOY_DIR]:
    _d.mkdir(parents=True, exist_ok=True)
