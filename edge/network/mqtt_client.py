"""边缘端 MQTT 客户端 — 缺陷数据发布 + 云端告警订阅。"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt

from ..config import edge_settings


class EdgeMQTTClient:
    """边缘端 MQTT 客户端，负责缺陷数据发布和云端告警接收。"""

    def __init__(self) -> None:
        self._client = mqtt.Client(client_id=f"edge-{edge_settings.edge_device_id}")
        self._host = edge_settings.mqtt_broker_host
        self._port = edge_settings.mqtt_broker_port
        self._device_id = edge_settings.edge_device_id
        self._connected = False
        self._running = False
        self._thread: threading.Thread | None = None
        self._alert_callback: Callable[[dict], None] | None = None

        if edge_settings.mqtt_username:
            self._client.username_pw_set(
                edge_settings.mqtt_username, edge_settings.mqtt_password
            )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    @property
    def connected(self) -> bool:
        return self._connected

    def set_alert_callback(self, callback: Callable[[dict], None]) -> None:
        self._alert_callback = callback

    def connect(self) -> bool:
        try:
            self._client.connect(self._host, self._port, keepalive=60)
        except Exception as e:
            print(f"[EdgeMQTT] 连接失败 {self._host}:{self._port} — {e}")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def disconnect(self) -> None:
        self._running = False
        try:
            self._client.disconnect()
        except Exception:
            pass

    def publish_defect(
        self,
        detections: list[dict],
        reason: str,
        avg_confidence: float,
        inference_ms: float,
        timestamp: float,
        frame_jpg: bytes | None = None,
        decision: str = "CLOUD",
    ) -> bool:
        if not self._connected:
            return False

        image_b64 = ""
        if frame_jpg:
            image_b64 = base64.b64encode(frame_jpg).decode()

        payload = {
            "device_id": self._device_id,
            "reason": reason,
            "decision": decision,
            "detections": detections,
            "avg_confidence": avg_confidence,
            "inference_ms": inference_ms,
            "timestamp": timestamp,
            "image": image_b64,
        }

        topic = f"edge/{self._device_id}/defect/upload"
        msg = json.dumps(payload, ensure_ascii=False)
        result = self._client.publish(topic, msg, qos=1)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def _loop(self) -> None:
        while self._running:
            try:
                self._client.loop(timeout=1.0)
            except Exception as e:
                print(f"[EdgeMQTT] loop error: {e}")
                time.sleep(5)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self._connected = True
            alert_topic = f"edge/{self._device_id}/alert"
            client.subscribe(alert_topic, qos=1)
            print(f"[EdgeMQTT] 已连接 {self._host}:{self._port}  订阅 {alert_topic}")
        else:
            self._connected = False
            print(f"[EdgeMQTT] 连接失败 code={reason_code}")

    def _on_disconnect(self, client, userdata, reason_code, properties=None):
        self._connected = False
        print(f"[EdgeMQTT] 断开连接 code={reason_code}")
        if self._running:
            print("[EdgeMQTT] 5s 后重连...")
            time.sleep(5)
            try:
                client.reconnect()
            except Exception as e:
                print(f"[EdgeMQTT] 重连失败: {e}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            return
        print(f"[EdgeMQTT] ← 云端告警: {json.dumps(payload, ensure_ascii=False)[:120]}")
        if self._alert_callback:
            self._alert_callback(payload)
