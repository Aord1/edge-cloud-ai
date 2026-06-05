"""步骤2: NEU-DET 原始数据 → YOLO txt 格式 → edge/training/dataset/

输入: data/train/ + data/validation/ (VOC XML)
输出: dataset/images/{train,val}/ + dataset/labels/{train,val}/ + dataset/data.yaml
"""

from __future__ import annotations

import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

from ..config import CLASS2ID, DATA_DIR, DATASET_DIR

TRAIN_IMG = DATASET_DIR / "images" / "train"
VAL_IMG = DATASET_DIR / "images" / "val"
TRAIN_LBL = DATASET_DIR / "labels" / "train"
VAL_LBL = DATASET_DIR / "labels" / "val"
DATA_YAML = DATASET_DIR / "data.yaml"


def convert() -> Path:
    """VOC XML → YOLO txt, 保留 Kaggle 版预划分的 train/validation。

    Returns:
        Path: DATA_YAML 路径。
    """
    src_train = DATA_DIR / "train"
    src_val = DATA_DIR / "validation"

    if not src_train.exists():
        raise FileNotFoundError(f"原始数据不存在: {src_train}\n请先运行 download.py")

    # 清理旧转换
    for d in [TRAIN_IMG, VAL_IMG, TRAIN_LBL, VAL_LBL]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    # ── 训练集 ──
    train_files = _collect_images(src_train / "images")
    train_ann = src_train / "annotations"
    _process_split("train", train_files, train_ann, TRAIN_IMG, TRAIN_LBL)

    # ── 验证集 ──
    val_files = _collect_images(src_val / "images")
    val_ann = src_val / "annotations"
    _process_split("val", val_files, val_ann, VAL_IMG, VAL_LBL)

    _write_data_yaml()

    total_train = len(list(TRAIN_IMG.iterdir()))
    total_val = len(list(VAL_IMG.iterdir()))
    print(f"[完成] 训练 {total_train} 张, 验证 {total_val} 张")
    print(f"       {DATA_YAML}")
    return DATA_YAML


# ── 内部 ──────────────────────────────────────────────────

def _collect_images(root: Path) -> list[Path]:
    return sorted(
        list(root.rglob("*.jpg")) + list(root.rglob("*.png")) + list(root.rglob("*.bmp"))
    )


def _process_split(
    name: str,
    files: list[Path],
    ann_dir: Path,
    img_dst: Path,
    lbl_dst: Path,
) -> None:
    import cv2

    skipped = 0
    total_objs = 0

    for img_path in files:
        # XML（recursive 查找）
        xml_path = ann_dir / f"{img_path.stem}.xml"
        if not xml_path.exists():
            found = list(ann_dir.rglob(f"{img_path.stem}.xml"))
            xml_path = found[0] if found else xml_path
        if not xml_path.exists():
            skipped += 1
            continue

        img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            img = cv2.imread(str(img_path))
        if img is None:
            skipped += 1
            continue

        objs = _voc_to_yolo(xml_path, img.shape[1], img.shape[0])
        if not objs:
            skipped += 1
            continue

        shutil.copy2(img_path, img_dst / img_path.name)
        lbl_path = lbl_dst / f"{img_path.stem}.txt"
        with open(lbl_path, "w") as f:
            for cls_id, cx, cy, bw, bh in objs:
                f.write(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")
        total_objs += len(objs)

    print(f"  [{name}] 有效 {len(files) - skipped}, 跳过 {skipped}, 标注框 {total_objs}")


def _voc_to_yolo(
    xml_path: Path, img_w: int, img_h: int
) -> list[tuple[int, float, float, float, float]]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    objs = []
    for obj in root.findall("object"):
        cls_name = (obj.findtext("name") or "").strip()
        if cls_name not in CLASS2ID:
            continue
        bbox = obj.find("bndbox")
        if bbox is None:
            continue
        xmin = float(bbox.findtext("xmin", 0))
        ymin = float(bbox.findtext("ymin", 0))
        xmax = float(bbox.findtext("xmax", 0))
        ymax = float(bbox.findtext("ymax", 0))
        objs.append((
            CLASS2ID[cls_name],
            (xmin + xmax) / 2 / img_w,
            (ymin + ymax) / 2 / img_h,
            (xmax - xmin) / img_w,
            (ymax - ymin) / img_h,
        ))
    return objs


def _write_data_yaml() -> None:
    yaml = f"""# NEU-DET 钢材表面缺陷 (YOLO 格式)
path: {DATASET_DIR.as_posix()}
train: images/train
val: images/val

nc: 6
names:
  0: crazing
  1: inclusion
  2: patches
  3: pitted_surface
  4: rolled-in_scale
  5: scratches
"""
    DATA_YAML.write_text(yaml, encoding="utf-8")
    print(f"  [yaml] {DATA_YAML}")


if __name__ == "__main__":
    convert()
