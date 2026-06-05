"""步骤1: 下载 NEU-DET 数据集 → edge/training/data/

来源: kaggle — kaustubhdikshit/neu-surface-defect-database
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from ..config import DATA_DIR

KAGGLE_DATASET = "kaustubhdikshit/neu-surface-defect-database"


def download() -> Path:
    """从 Kaggle 下载并解压原始数据。

    Returns:
        Path: DATA_DIR, 包含 train/ 和 validation/ 子目录。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 已存在则跳过
    train_img = DATA_DIR / "train" / "images"
    if train_img.exists() and any(train_img.iterdir()):
        count = len(list(train_img.rglob("*.jpg")))
        print(f"[跳过] 数据已存在 ({count}+ 张训练图)")
        return DATA_DIR

    import kagglehub

    print(f"[下载] kagglehub: {KAGGLE_DATASET} ...")
    src = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    print(f"  缓存: {src}")

    # 复制到 data/（跳过打包以便增量使用）
    _copy_dataset(src / "NEU-DET", DATA_DIR)

    train_n = len(list((DATA_DIR / "train" / "images").rglob("*.jpg")))
    val_n = len(list((DATA_DIR / "validation" / "images").rglob("*.jpg")))
    print(f"[完成] 训练 {train_n} 张, 验证 {val_n} 张")
    return DATA_DIR


def _copy_dataset(src: Path, dst: Path) -> None:
    """复制数据集目录（先删旧，简单粗暴但保证干净）。"""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"  已复制到 {dst}")


def _pack_to_zip(src_dir: Path, zip_path: Path) -> None:
    """将目录打包成 ZIP（备用）。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(src_dir))


if __name__ == "__main__":
    download()
