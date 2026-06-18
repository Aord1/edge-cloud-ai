"""
边缘端配置 — 所有可配置参数的唯一入口，各模块从此处引用，消除硬编码重定义。
"""

from __future__ import annotations

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class EdgeSettings(BaseSettings):
    # ── 设备 ──
    edge_device_id: str = "camera-01"

    # ── 模型路径 ──
    model_path: str = "edge/public/neu-det/yolo26n_neu_det.xml"

    # ── 云端地址 ──
    edge_cloud_api_url: str = "http://localhost:8000/api/v1"

    # ── MQTT ──
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: str = "edgecloud"
    mqtt_password: str = ""

    # ── 检测 ──
    detection_conf_threshold: float = 0.25   # YOLO 置信度阈值
    detection_max_detections: int = 20        # 单帧最大检出数
    detection_conf_edge: float = 0.5          # 边缘本地处理置信度阈值

    # ── 分类决策 ──
    classify_mixed_types_threshold: int = 2   # 缺陷类型数 > 此值 → 全部上传云端
    classify_crowded_threshold: int = 5       # 缺陷数 > 此值 → 全部上传云端

    # ── 帧间跟踪 ──
    tracker_iou_threshold: float = 0.4        # IoU 匹配阈值
    tracker_min_frames: int = 2              # 至少出现 N 帧才上报

    # ── 本地告警 ──
    alert_cooldown_sec: float = 30.0          # 同类型告警冷却时间
    alert_dense_threshold: int = 3            # 缺陷数 > 此值 → 密集告警
    alert_history_max: int = 200              # 告警历史上限

    # ── 视频采集 ──
    capture_width: int = 640
    capture_height: int = 480
    capture_fps: int = 30
    capture_buffer_size: int = 4
    capture_read_timeout: float = 2.0         # 摄像头帧读取超时
    capture_thread_join_timeout: float = 3.0

    # ── HTTP 服务 ──
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    server_thread_join_timeout: float = 3.0
    server_detect_join_timeout: float = 5.0

    # ── MJPEG 流 ──
    mjpeg_quality: int = 75                   # MJPEG 流 JPEG 质量
    mjpeg_frame_timeout: float = 0.5          # 帧等待超时
    mjpeg_stream_width: int = 960             # Web 端显示宽度

    # ── 云端上传 ──
    upload_jpeg_quality: int = 80             # 上传帧 JPEG 质量
    upload_http_timeout: int = 30             # HTTP 上传超时（秒）

    # ── 离线容错 ──
    cache_dir: str = "edge/cache"             # 离线缓存目录
    cache_retry_interval: int = 10            # 补传重试间隔（秒）
    cache_max_entries: int = 500              # 缓存最大条目数

    # ── FPS 统计 ──
    fps_window_size: int = 30                 # 滑动窗口大小

    # ── 摄像头探测 ──
    camera_probe_max: int = 4                 # 最多探测摄像头数

    model_config = ConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore",
    )


edge_settings = EdgeSettings()
