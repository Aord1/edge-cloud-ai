"""合成测试视频 — 无文字叠加,可直接喂给 YOLO 检测管线。

覆盖全部 6 条决策路径:
  0-6s     scratches              简单缺陷 → EDGE 本地
  6-12s    patches                简单缺陷 → EDGE 本地
  12-18s   pitted_surface         简单缺陷 → EDGE 本地
  18-22s   crazing                严重缺陷 → CLOUD Agent
  22-26s   inclusion              严重缺陷 → CLOUD Agent
  26-30s   rolled-in_scale        严重缺陷 → CLOUD Agent

衍生产品:
  test_mixed_crowded.avi (8s) — 混杂/密集场景, 触发 mixed_defects / crowded 路径
  每张子图 ≥ 200×200, 确保 YOLO 能检测到。

用法: python -m edge.training.scripts.generate_test_video
输出: edge/test/
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
VAL_IMG_DIR = PROJECT_ROOT / "edge" / "training" / "dataset" / "images" / "val"
OUTPUT_DIR = PROJECT_ROOT / "edge" / "test"
OUTPUT_DIR.mkdir(exist_ok=True)

FPS = 15
W = 640
H = 480

CLASS_NAMES = ["crazing", "inclusion", "patches", "pitted_surface", "rolled-in_scale", "scratches"]
SEVERE_DEFECTS = {"crazing", "inclusion", "rolled-in_scale"}


def _sorted_images(class_name: str) -> list[Path]:
    return sorted(VAL_IMG_DIR.glob(f"{class_name}_*.jpg"))


def _resize_and_pad(img: np.ndarray, target_w: int = W, target_h: int = H) -> np.ndarray:
    """等比缩放并居中放到 target_w×target_h 画布, 背景深灰。"""
    h, w = img.shape[:2]
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h))
    canvas = np.full((target_h, target_w, 3), 40, dtype=np.uint8)
    x_off = (target_w - new_w) // 2
    y_off = (target_h - new_h) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    return canvas


def _dark_frame() -> np.ndarray:
    return np.zeros((H, W, 3), dtype=np.uint8)


def _make_writer(name: str, fourcc: str = "XVID") -> tuple[cv2.VideoWriter, Path]:
    path = OUTPUT_DIR / name
    return cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc), FPS, (W, H)), path


def _convert_to_mp4(avi_path: Path) -> Path | None:
    mp4_path = OUTPUT_DIR / avi_path.with_suffix(".mp4").name
    code = os.system(
        f'ffmpeg -y -loglevel error -i "{avi_path}" -c:v libx264 -preset fast '
        f'-crf 23 -pix_fmt yuv420p "{mp4_path}"'
    )
    return mp4_path if code == 0 else None


# ══════════════════════════════════════════════════════════════════
#  主测试视频 — 30 秒, 简单缺陷 EDGE + 严重缺陷 CLOUD
# ══════════════════════════════════════════════════════════════════

def generate_main_30s(seed: int = 42) -> Path:
    random.seed(seed)
    transitions = FPS

    writer, out_path = _make_writer("test_defects_30s.avi")

    sequence: list[tuple[str, list[str], str]] = [
        ("EDGE-简单划痕",    ["scratches"],       "EDGE"),
        ("EDGE-简单斑块",    ["patches"],         "EDGE"),
        ("EDGE-简单麻点",    ["pitted_surface"],  "EDGE"),
        ("CLOUD-严重裂纹",   ["crazing"],         "CLOUD"),
        ("CLOUD-严重夹杂",   ["inclusion"],       "CLOUD"),
        ("CLOUD-严重氧化皮", ["rolled-in_scale"], "CLOUD"),
    ]

    total_sec = 30
    seg_sec = total_sec / len(sequence)          # 5 秒/段
    seg_frames = int(seg_sec * FPS)              # 75 帧/段
    per_img_frames = int(2.0 * FPS)              # 30 帧/张

    for seg_idx, (label, class_names, decision) in enumerate(sequence):
        for _ in range(transitions // 2):
            writer.write(_dark_frame())

        all_imgs: list[np.ndarray] = []
        for cn in class_names:
            paths = _sorted_images(cn)
            pick = random.sample(paths, min(3, len(paths)))
            for p in pick:
                img = cv2.imread(str(p))
                if img is not None:
                    all_imgs.append(img)

        if not all_imgs:
            print(f"  [跳过] {label} — 无可用图像")
            continue

        body_frames = seg_frames - transitions
        written = 0
        while written < body_frames:
            for img in all_imgs:
                if written >= body_frames:
                    break
                canvas = _resize_and_pad(img)      # 整张图缩放居中
                for _ in range(per_img_frames):
                    if written >= body_frames:
                        break
                    writer.write(canvas)
                    written += 1

        for _ in range(transitions // 2):
            writer.write(_dark_frame())

        print(f"  [{decision}] {label}  → {written}+{transitions} 帧")

    writer.release()
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\n[v] {out_path.name}  ({size_mb:.1f} MB)  {FPS}fps  ~{total_sec}s")

    mp4_path = _convert_to_mp4(out_path)
    if mp4_path:
        print(f"[v] {mp4_path.name} ({mp4_path.stat().st_size / (1024 * 1024):.1f} MB)")
    return out_path


# ══════════════════════════════════════════════════════════════════
#  混杂/密集场景 — 每张子图 ≥ 200×200, 触发 mixed_defects / crowded
# ══════════════════════════════════════════════════════════════════

# 子图最小尺寸
SUB_MIN_W, SUB_MIN_H = 200, 200

def _resize_to_sub(img: np.ndarray, target_w: int = SUB_MIN_W, target_h: int = SUB_MIN_H) -> np.ndarray:
    """等比缩放, 短边撑满, 长边居中裁切, 确保返回 target_w×target_h。"""
    h, w = img.shape[:2]
    scale = max(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h))
    x = (new_w - target_w) // 2
    y = (new_h - target_h) // 2
    return resized[y:y + target_h, x:x + target_w]


def _make_mixed_frame(cls_a: str, cls_b: str, class_imgs: dict[str, np.ndarray]) -> np.ndarray | None:
    """两种缺陷上下并排, 各占 200×220, 画布 640×480。"""
    img_a = class_imgs.get(cls_a)
    img_b = class_imgs.get(cls_b)
    if img_a is None or img_b is None:
        return None
    a = _resize_to_sub(img_a, 200, 220)
    b = _resize_to_sub(img_b, 200, 220)
    canvas = np.full((H, W, 3), 40, dtype=np.uint8)
    x_center = (W - 200) // 2
    y_a, y_b = 20, H - 20 - 220
    canvas[y_a:y_a + 220, x_center:x_center + 200] = a
    canvas[y_b:y_b + 220, x_center:x_center + 200] = b
    return canvas


def _make_crowded_frame(imgs: list[np.ndarray]) -> np.ndarray:
    """2×3 网格, 每格 210×210, 全部 ≥ 200, 画布 640×480。"""
    rows, cols = 2, 3
    cell_w, cell_h = 210, 210
    # 网格总尺寸
    grid_w = cols * cell_w
    grid_h = rows * cell_h
    x0 = (W - grid_w) // 2
    y0 = (H - grid_h) // 2
    canvas = np.full((H, W, 3), 40, dtype=np.uint8)
    for idx, img in enumerate(imgs[:rows * cols]):
        r, c = idx // cols, idx % cols
        thumb = _resize_to_sub(img, cell_w, cell_h)
        x = x0 + c * cell_w
        y = y0 + r * cell_h
        canvas[y:y + cell_h, x:x + cell_w] = thumb
    return canvas


def generate_mixed_crowded(seed: int = 42) -> Path:
    random.seed(seed)

    writer, out_path = _make_writer("test_mixed_crowded.avi")

    # 加载各类别图像
    class_imgs: dict[str, np.ndarray] = {}
    for cn in CLASS_NAMES:
        paths = _sorted_images(cn)
        if paths:
            class_imgs[cn] = cv2.imread(str(paths[0]))

    if len(class_imgs) < 6:
        print(f"  [警告] 只有 {len(class_imgs)} 类缺陷可用")

    total_frames = 8 * FPS   # 120 帧
    seg_half = total_frames // 2  # 60 帧/段

    # ── 0-4s: 混杂场景 (2 种缺陷上下并排) → mixed_defects → CLOUD ──
    pairs = [
        ("crazing", "scratches"),
        ("inclusion", "patches"),
    ]
    written = 0
    while written < seg_half:
        for cls_a, cls_b in pairs:
            if written >= seg_half:
                break
            frame = _make_mixed_frame(cls_a, cls_b, class_imgs)
            if frame is None:
                continue
            for _ in range(FPS * 2):
                if written >= seg_half:
                    break
                writer.write(frame)
                written += 1
    print(f"  [CLOUD] mixed_defects  → {written} 帧 (子图 200×220)")

    # ── 4-8s: 密集场景 (>5 个缺陷 2×3 网格) → crowded → CLOUD ──
    img_list = list(class_imgs.values())
    written2 = 0
    seg2 = total_frames - seg_half
    while written2 < seg2:
        random.shuffle(img_list)
        frame = _make_crowded_frame(img_list)
        for _ in range(FPS * 2):
            if written2 >= seg2:
                break
            writer.write(frame)
            written2 += 1
    print(f"  [CLOUD] crowded       → {written2} 帧 (2×3 网格 210×210)")

    writer.release()
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\n[v] {out_path.name}  ({size_mb:.1f} MB)  {FPS}fps  ~8s")

    mp4_path = _convert_to_mp4(out_path)
    if mp4_path:
        print(f"[v] {mp4_path.name} ({mp4_path.stat().st_size / (1024 * 1024):.1f} MB)")
    return out_path


# ══════════════════════════════════════════════════════════════════

def generate() -> None:
    print("═" * 50)
    print("生成主测试视频 (30s, 简单+严重缺陷)")
    print("═" * 50)
    generate_main_30s()

    print("\n" + "═" * 50)
    print("生成混杂/密集测试视频 (8s, mixed+crowded)")
    print("═" * 50)
    generate_mixed_crowded()

    print("\n" + "═" * 50)
    print("全部完成! 输出文件:")
    for f in sorted(
        list(OUTPUT_DIR.glob("test_*.avi")) + list(OUTPUT_DIR.glob("test_*.mp4"))
    ):
        print(f"  {f.name}  ({f.stat().st_size / (1024 * 1024):.1f} MB)")


if __name__ == "__main__":
    generate()
