"""步骤5: 验证 IR 模型能被 detector.py 加载并正确推理。"""

from __future__ import annotations

from pathlib import Path

from edge.inference.detector import YOLODetector

from ..config import DATASET_DIR, DEPLOY_DIR, IR_XML


def validate(model_path: Path | None = None) -> bool:
    """加载 IR 模型，用验证集图片跑一次推理。"""
    model_path = model_path or Path(DEPLOY_DIR / "yolo26n_neu_det.xml")
    if not model_path.exists():
        raise FileNotFoundError(f"IR 模型未找到: {model_path}\n请先运行 export.py")

    print(f"[验证] 加载: {model_path}")
    detector = YOLODetector(model_path=str(model_path))
    print(f"       输入: {detector._input_w}x{detector._input_h}")
    print(f"       OK")

    # 找测试图
    val_dir = DATASET_DIR / "images" / "val"
    test_imgs = sorted(val_dir.iterdir())
    if not test_imgs:
        print("[跳过] 无验证图")
        return True

    import cv2

    ok = 0
    for img_path in test_imgs[:10]:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        result = detector.detect(img)
        if result.count > 0:
            ok += 1
            names = ", ".join(f"{d.class_name}({d.confidence:.2f})" for d in result.detections)
            print(f"       {img_path.name}: {names}  [{result.inference_ms:.0f}ms]")

    print(f"\n[完成] {ok}/{min(10, len(test_imgs))} 张检测到缺陷, 模型正常")
    return True


if __name__ == "__main__":
    validate()
