"""步骤3: YOLO26n NEU-DET 微调训练 → edge/training/runs/"""

from __future__ import annotations

from pathlib import Path

from ultralytics import YOLO

from ..config import BATCH, DATA_YAML, DEVICE, EPOCHS, IMGSZ, MODEL_NAME, RUNS_DIR


def train(
    epochs: int = EPOCHS,
    imgsz: int = IMGSZ,
    batch: int = BATCH,
    device: str = DEVICE,
) -> Path:
    """训练 YOLO26n，返回 best.pt 路径。"""
    if not DATA_YAML.exists():
        raise FileNotFoundError(f"数据集未准备: {DATA_YAML}\n请先运行 convert.py")

    print(f"[训练] YOLO26n  |  epochs={epochs}  imgsz={imgsz}  batch={batch}  device={device}")
    print(f"       数据: {DATA_YAML}")

    model = YOLO(MODEL_NAME)

    model.train(
        data=str(DATA_YAML),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        workers=0,
        name="neu-det",
        exist_ok=True,
        # 轻量增强（小数据集适用）
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=0.0,
        translate=0.1,
        scale=0.5,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.0,
        copy_paste=0.0,
        erasing=0.4,
    )

    best_pt = RUNS_DIR / "detect" / "neu-det" / "weights" / "best.pt"
    if best_pt.exists():
        print(f"[完成] best.pt: {best_pt}")
    else:
        print("[警告] best.pt 未找到，请检查训练输出")
    return best_pt


if __name__ == "__main__":
    train()
