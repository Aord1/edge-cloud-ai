"""
边缘端配置 — 仅可部署差异化项，其余参数由各模块自行硬编码默认值。
"""

from __future__ import annotations

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

    model_config = dict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore",
    )


edge_settings = EdgeSettings()
