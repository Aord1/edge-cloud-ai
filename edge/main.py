"""边缘端主入口 — 视频采集 → NEU-DET 缺陷检测 → 分类 → 告警/上传。

用法:
    python -m edge.main --server                    # HTTP 服务模式（Web 端控制）
    python -m edge.main -s test.mp4                 # CLI MQTT 检测模式
    python -m edge.main -s test.mp4 --use-http      # CLI HTTP 上传模式
    python -m edge.main -s test.mp4 --web-stream    # CLI + MJPEG 流
    python -m edge.main -s 0 --no-upload            # 仅检测不上传
"""

from __future__ import annotations

import argparse
import time
from collections import deque

import cv2
import numpy as np

from .capture.camera import make_camera
from .classify.alert import AlertEngine
from .classify.decision import Action, classify
from .config import edge_settings
from .inference.detector import CLASS_COLORS, YOLODetector
from .inference.visual import get_text_size, put_chinese_text
from .network.http_client import upload_sync
from .network.mqtt_client import EdgeMQTTClient
from .stream import EdgeStreamServer
from .server import EdgeServer
from .tracking import DefectTracker


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Edge YOLO Detection")
    p.add_argument("-s", "--source", default="0")
    p.add_argument("--fps", type=int, default=0, help="0=视频自动/摄像头30")
    p.add_argument("--conf", type=float, default=edge_settings.detection_conf_threshold, help="YOLO 置信度阈值")
    p.add_argument("--conf-edge", type=float, default=edge_settings.detection_conf_edge, help="边缘本地处理阈值")
    p.add_argument("--max-det", type=int, default=edge_settings.detection_max_detections)
    p.add_argument("--display", type=int, default=1280, help="0=原始尺寸")
    p.add_argument("--no-show", action="store_true")
    p.add_argument("--no-upload", action="store_true", help="禁用上传")
    p.add_argument("--use-http", action="store_true", help="使用 HTTP 上传（默认 MQTT）")
    p.add_argument("--api-url", default=edge_settings.edge_cloud_api_url, help="云端地址")
    p.add_argument("--device-id", default=edge_settings.edge_device_id)
    p.add_argument("--web-stream", action="store_true", help="开启 MJPEG 流供 Web 端查看")
    p.add_argument("--web-port", type=int, default=edge_settings.server_port, help="MJPEG 流端口")
    p.add_argument("--server", action="store_true", help="HTTP 服务模式，由 Web 端控制检测")
    p.add_argument("--server-host", default=edge_settings.server_host, help="服务监听地址")
    args = p.parse_args(argv)

    # ── 服务模式：启动 HTTP 服务，等待 Web 端控制 ──
    if args.server:
        server = EdgeServer(host=args.server_host, port=args.web_port)
        server.configure(
            source=args.source, conf=args.conf, conf_edge=args.conf_edge,
            api_url=args.api_url, device_id=args.device_id,
        )
        server.start()
        print(f"[Edge] 服务模式 — Web 端访问 http://localhost:{args.web_port}")
        print("[Edge] 按 Ctrl+C 退出")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
        return

    src = int(args.source) if args.source.lstrip("-").isdigit() else args.source
    cam = make_camera(source=src, fps=args.fps)
    detector = YOLODetector(model_path=edge_settings.model_path, conf_threshold=args.conf, max_detections=args.max_det)
    alerter = AlertEngine()
    tracker = DefectTracker()

    kind = "摄像头" if isinstance(src, int) else f"文件 {src!r}"
    print(f"[Edge] {kind}  fps={'自动' if args.fps <= 0 else args.fps}  "
          f"conf={args.conf}  edge_conf={args.conf_edge}")
    if args.no_upload:
        print("[Edge] 上传已禁用")
    else:
        mode = "HTTP" if args.use_http else "MQTT"
        print(f"[Edge] 上传模式: {mode} → {args.api_url}")

    mqtt: EdgeMQTTClient | None = None
    if not args.no_upload and not args.use_http:
        mqtt = EdgeMQTTClient()
        if mqtt.connect():
            print(f"[Edge] MQTT 已连接 {edge_settings.mqtt_broker_host}:{edge_settings.mqtt_broker_port}")
        else:
            print("[Edge] MQTT 连接失败，将回退到 HTTP 上传")
            mqtt = None
    print("[Edge] 按 q 退出")

    stream_server: EdgeStreamServer | None = None
    if args.web_stream:
        stream_server = EdgeStreamServer(port=args.web_port)
        stream_server.start()
    cam.open()

    fps_window = deque(maxlen=edge_settings.fps_window_size)
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

            # ── 上传云端（经 tracker 去重：同一缺陷只上传一次）──
            if decision.action == Action.CLOUD and not args.no_upload:
                new_defects = tracker.update(decision.upload)
                if new_defects:
                    _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, edge_settings.upload_jpeg_quality])
                    jpg_bytes = bytes(jpg)

                    if mqtt and mqtt.connected:
                        ok = mqtt.publish_defect(
                            new_defects, decision.reason,
                            result.avg_confidence, result.inference_ms, result.timestamp,
                            frame_jpg=jpg_bytes,
                        )
                        if ok:
                            print(f"  [MQTT上传] {decision.summary} ({len(new_defects)}个新缺陷)")
                            cloud_count += 1
                        else:
                            print(f"  [MQTT上传失败]")
                    else:
                        try:
                            r = upload_sync(
                                args.api_url, args.device_id,
                                new_defects, decision.reason,
                                result.avg_confidence, result.inference_ms, result.timestamp,
                                frame_jpg=jpg_bytes,
                            )
                            print(f"  [HTTP上传] {decision.summary} ({len(new_defects)}个新缺陷) → {r.get('message', 'ok')}")
                            cloud_count += 1
                        except Exception as e:
                            print(f"  [上传失败] {e}")

            # ── 终端日志 ──
            elapsed = time.perf_counter() - t0
            fps_window.append(1.0 / max(elapsed, 0.001))
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

            # ── Web 流推送 ──
            if stream_server:
                h, w = frame.shape[:2]
                web_w = edge_settings.mjpeg_stream_width
                if w > web_w:
                    ws = web_w / w
                    web_frame = cv2.resize(frame, (web_w, int(h * ws)))
                    web_annotated = _annotate_scaled(web_frame, result, decision, ws, ws, actual_fps)
                else:
                    web_annotated = _annotate(frame, result, decision, actual_fps)
                stream_server.push_frame(web_annotated)
                stream_server.update_status({
                    "detections": [
                        {"class": d.class_name, "conf": d.confidence, "bbox": list(d.bbox)}
                        for d in result.detections
                    ],
                    "count": result.count,
                    "fps": round(actual_fps, 1),
                    "inference_ms": result.inference_ms,
                    "decision": "CLOUD" if decision.action == Action.CLOUD else "EDGE",
                    "reason": decision.reason,
                })
    finally:
        if mqtt:
            mqtt.disconnect()
        cam.close()
        cv2.destroyAllWindows()
        if stream_server:
            stream_server.stop()
        print(f"[Edge] 已停止  edge:{edge_count}  cloud:{cloud_count}")


def _annotate(frame: np.ndarray, result, decision, fps: float) -> np.ndarray:
    return _draw_frame(frame.copy(), result, decision, fps, 1.0, 1.0)

def _annotate_scaled(
    frame: np.ndarray, result, decision, sx: float, sy: float, fps: float,
) -> np.ndarray:
    return _draw_frame(frame.copy(), result, decision, fps, sx, sy)


def _draw_frame(
    frame: np.ndarray, result, decision,
    fps: float, sx: float, sy: float,
) -> np.ndarray:
    for d in result.detections:
        c = CLASS_COLORS.get(d.class_id, (0, 255, 0))
        x1, y1 = int(d.x1 * sx), int(d.y1 * sy)
        x2, y2 = int(d.x2 * sx), int(d.y2 * sy)
        cv2.rectangle(frame, (x1, y1), (x2, y2), c, 2)
        label = f"{d.class_name} {d.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        cv2.rectangle(frame, (x1, y1 - th - 4), (x1 + tw + 4, y1), c, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    status = f"FPS:{fps:.0f} | 缺陷:{result.count} | "
    status += "EDGE" if decision.action == Action.EDGE else ">>CLOUD"
    color = (0, 255, 0) if decision.action == Action.EDGE else (0, 0, 255)
    put_chinese_text(frame, status, (10, frame.shape[0] - 32), font_size=20, color=color)
    return frame


if __name__ == "__main__":
    main()
