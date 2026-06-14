"""MQTT 消息处理 — 边缘端缺陷数据订阅 + Agent 复核结果发布。"""

from __future__ import annotations

import asyncio
import json
import threading
import time

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from ..config import settings
from ..schemas.detection import DetectionUploadRequest
from ..services.review import process_upload

_mqtt_client: mqtt.Client | None = None
_bridge_queue: asyncio.Queue | None = None
_running = False


def get_mqtt_client() -> mqtt.Client | None:
    return _mqtt_client


def start_mqtt(bridge_queue: asyncio.Queue) -> None:
    global _mqtt_client, _bridge_queue, _running
    if _running:
        return
    _bridge_queue = bridge_queue
    _running = True

    client = mqtt.Client(client_id=f"cloud-{settings.db_host}")
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

    client.on_connect = _on_connect
    client.on_message = _on_message
    client.on_disconnect = _on_disconnect

    try:
        client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, keepalive=60)
    except Exception as e:
        print(f"[MQTT] 连接失败 {settings.mqtt_broker_host}:{settings.mqtt_broker_port} — {e}")
        print("[MQTT] 将继续运行，边缘端 MQTT 上传暂不可用")
        _running = False
        return

    _mqtt_client = client
    thread = threading.Thread(target=_mqtt_loop, daemon=True)
    thread.start()
    print(f"[MQTT] 已连接 {settings.mqtt_broker_host}:{settings.mqtt_broker_port}")


def stop_mqtt() -> None:
    global _running, _mqtt_client
    _running = False
    if _mqtt_client:
        _mqtt_client.disconnect()
        _mqtt_client = None
    print("[MQTT] 已断开")


def publish_alert(device_id: str, payload: dict) -> None:
    if not _mqtt_client:
        return
    topic = f"edge/{device_id}/alert"
    msg = json.dumps(payload, ensure_ascii=False)
    _mqtt_client.publish(topic, msg, qos=1)
    print(f"[MQTT] → {topic}: {msg[:80]}...")


def _mqtt_loop() -> None:
    while _running and _mqtt_client:
        try:
            _mqtt_client.loop(timeout=1.0)
        except Exception as e:
            print(f"[MQTT] loop error: {e}")
            time.sleep(5)


def _on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        client.subscribe("edge/+/defect/upload", qos=1)
        print("[MQTT] 已订阅 edge/+/defect/upload")
    else:
        print(f"[MQTT] 连接失败 code={reason_code}")


def _on_disconnect(client, userdata, reason_code, properties=None):
    print(f"[MQTT] 断开连接 code={reason_code}")
    if _running:
        print("[MQTT] 5s 后重连...")
        time.sleep(5)
        try:
            client.reconnect()
        except Exception as e:
            print(f"[MQTT] 重连失败: {e}")


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError as e:
        print(f"[MQTT] JSON 解析失败: {e}")
        return

    try:
        data = DetectionUploadRequest(**payload)
    except (ValidationError, TypeError) as e:
        print(f"[MQTT] 数据校验失败: {e}")
        return

    print(f"[MQTT] ← {data.device_id} {len(data.detections)} 条缺陷")

    if _bridge_queue:
        try:
            _bridge_queue.put_nowait({
                "device_id": data.device_id,
                "reason": data.reason,
                "detections": [d.model_dump() for d in data.detections],
                "avg_confidence": data.avg_confidence,
                "inference_ms": data.inference_ms,
                "image_b64": data.image,
                "decision": data.decision,
            })
        except asyncio.QueueFull:
            print("[MQTT] 桥接队列满，丢弃消息")