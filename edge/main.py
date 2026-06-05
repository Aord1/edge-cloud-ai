"""边缘端主入口 — 视频采集 → NEU-DET 缺陷检测 → 分类 → 告警/上传。

用法:
    python -m edge.main                      # 默认摄像头
    python -m edge.main -s test.mp4          # 视频文件
    python -m edge.main -s 0 --no-upload     # 仅检测不上传
"""

from __future__ import annotations

import argparse
import time

import cv2
import numpy as np

from .capture.camera import make_camera
from .classify.alert import AlertEngine
from .classify.decision import Action, classify
from .config import edge_settings
from .inference.detector import YOLODetector
from .network.http_client import upload_sync


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Edge YOLO Detection")
    p.add_argument("-s", "--source", default="0")
    p.add_argument("--fps", type=int, default=0, help="0=视频自动/摄像头30")
    p.add_argument("--conf", type=float, default=0.3, help="YOLO 置信度阈值")
    p.add_argument("--conf-edge", type=float, default=0.5, help="边缘本地处理阈值")
    p.add_argument("--max-det", type=int, default=20)
    p.add_argument("--display", type=int, default=1280, help="0=原始尺寸")
    p.add_argument("--no-show", action="store_true")
    p.add_argument("--no-upload", action="store_true", help="禁用上传")
    p.add_argument("--api-url", default="http://localhost:8000/api/v1", help="云端地址")
    p.add_argument("--device-id", default="camera-01")
    args = p.parse_args(argv)

    src = int(args.source) if args.source.lstrip("-").isdigit() else args.source
    cam = make_camera(source=src, fps=args.fps)
    detector = YOLODetector(model_path=edge_settings.model_path, conf_threshold=args.conf, max_detections=args.max_det)
    alerter = AlertEngine()

    kind = "摄像头" if isinstance(src, int) else f"文件 {src!r}"
    print(f"[Edge] {kind}  fps={'自动' if args.fps <= 0 else args.fps}  "
          f"conf={args.conf}  edge_conf={args.conf_edge}")
    if args.no_upload:
        print("[Edge] 上传已禁用")
    else:
        print(f"[Edge] 云端: {args.api_url}")
    print("[Edge] 按 q 退出")
    cam.open()

    fps_window: list[float] = []
    edge_count = 0
    cloud_count = 0

    try:
        while True:
            t0 = time.perf_counter()
            frame = cam.read()
            if frame is None:
                break

            result = detector.detect(frame)
            decision = classify(result, conf_edge=args.conf_edge)

            # ── 本地告警 ──
            if decision.action == Action.EDGE and decision.local:
                alert = alerter.evaluate(decision.local)
                if alert:
                    print(f"  [本地告警] {alert.message}")
                    edge_count += 1

            # ── 上传云端 ──
            if decision.action == Action.CLOUD and not args.no_upload:
                _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                try:
                    r = upload_sync(
                        args.api_url, args.device_id,
                        decision.upload, decision.reason,
                        result.avg_confidence, result.inference_ms, result.timestamp,
                        frame_jpg=bytes(jpg),
                    )
                    print(f"  [上传云端] {decision.summary} → {r.get('message', 'ok')}")
                    cloud_count += 1
                except Exception as e:
                    print(f"  [上传失败] {e}")

            # ── 终端日志 ──
            elapsed = time.perf_counter() - t0
            fps_window.append(1.0 / max(elapsed, 0.001))
            if len(fps_window) > 30:
                fps_window.pop(0)
            actual_fps = sum(fps_window) / len(fps_window)

            if result.count:
                names = ", ".join(
                    f"{d.class_name}({d.confidence:.2f})" for d in result.detections
                )
                tag = "E" if decision.action == Action.EDGE else "C"
                print(f"  [{tag}] [{result.inference_ms:.0f}ms] [{actual_fps:.0f}fps] {names}")

            # ── 显示 ──
            if not args.no_show:
                h, w = frame.shape[:2]
                if args.display > 0 and w > args.display:
                    scale = args.display / w
                    display = cv2.resize(frame, (args.display, int(h * scale)))
                    annotated = _annotate_scaled(display, result, decision, scale, scale, actual_fps)
                else:
                    annotated = _annotate(frame, result, decision, actual_fps)
                cv2.imshow("Edge Detection", annotated)
                delay = 1 if cam.is_live else int(1000 / cam.fps)
                if cv2.waitKey(delay) & 0xFF == ord("q"):
                    break
    finally:
        cam.close()
        cv2.destroyAllWindows()
        print(f"[Edge] 已停止  edge:{edge_count}  cloud:{cloud_count}")


# ── 绘制 ──────────────────────────────────────────────────────

COLORS: dict[int, tuple[int, int, int]] = {
    0: (0, 0, 255),       # crazing — 红
    1: (255, 128, 0),     # inclusion — 橙
    2: (0, 255, 255),     # patches — 黄
    3: (255, 0, 255),     # pitted_surface — 紫
    4: (128, 128, 128),   # rolled-in_scale — 灰
    5: (0, 255, 0),       # scratches — 绿
}


def _annotate(frame: np.ndarray, result, decision, fps: float) -> np.ndarray:
    annotated = frame.copy()
    for d in result.detections:
        c = COLORS.get(d.class_id, (0, 255, 0))
        x1, y1, x2, y2 = d.bbox
        cv2.rectangle(annotated, (x1, y1), (x2, y2), c, 2)
        label = f"{d.class_name} {d.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        cv2.rectangle(annotated, (x1, y1 - th - 4), (x1 + tw + 4, y1), c, -1)
        cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    # 状态栏
    status = f"FPS:{fps:.0f} | 缺陷:{result.count} | "
    status += "EDGE" if decision.action == Action.EDGE else ">>CLOUD"
    color = (0, 255, 0) if decision.action == Action.EDGE else (0, 0, 255)
    cv2.putText(annotated, status, (10, annotated.shape[0] - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    return annotated


def _annotate_scaled(
    frame: np.ndarray, result, decision, sx: float, sy: float, fps: float,
) -> np.ndarray:
    annotated = frame.copy()
    for d in result.detections:
        c = COLORS.get(d.class_id, (0, 255, 0))
        x1, y1 = int(d.x1 * sx), int(d.y1 * sy)
        x2, y2 = int(d.x2 * sx), int(d.y2 * sy)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), c, 2)
        label = f"{d.class_name} {d.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        cv2.rectangle(annotated, (x1, y1 - th - 4), (x1 + tw + 4, y1), c, -1)
        cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    status = f"FPS:{fps:.0f} | 缺陷:{result.count}"
    color = (0, 255, 0) if decision.action == Action.EDGE else (0, 0, 255)
    cv2.putText(annotated, status, (10, annotated.shape[0] - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    return annotated


if __name__ == "__main__":
    main()
