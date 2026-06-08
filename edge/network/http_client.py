"""HTTP 客户端 — 检测结果上传云端。"""

from __future__ import annotations

import json

import httpx


def build_payload(
    device_id: str, detections: list[dict], reason: str,
    avg_confidence: float, inference_ms: float, timestamp: float,
    frame_jpg: bytes | None,
) -> tuple[dict, dict]:
    dets_json = json.dumps([{**d, "bbox": list(d["bbox"])} for d in detections])
    data = {
        "device_id": device_id,
        "reason": reason,
        "detections": dets_json,
        "avg_confidence": str(avg_confidence),
        "inference_ms": str(inference_ms),
        "timestamp": str(timestamp),
    }
    files = {}
    if frame_jpg:
        files["image"] = ("frame.jpg", frame_jpg, "image/jpeg")
    return data, files


async def upload(
    api_url: str, device_id: str, detections: list[dict], reason: str,
    avg_confidence: float, inference_ms: float, timestamp: float,
    frame_jpg: bytes | None = None,
) -> dict:
    """异步上传检测结果。"""
    data, files = build_payload(
        device_id, detections, reason, avg_confidence, inference_ms, timestamp, frame_jpg,
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{api_url}/detect/upload", data=data, files=files)
        resp.raise_for_status()
        return resp.json()


def upload_sync(
    api_url: str, device_id: str, detections: list[dict], reason: str,
    avg_confidence: float, inference_ms: float, timestamp: float,
    frame_jpg: bytes | None = None,
) -> dict:
    """同步上传（避免 asyncio，适合边缘端主循环）。"""
    data, files = build_payload(
        device_id, detections, reason, avg_confidence, inference_ms, timestamp, frame_jpg,
    )
    resp = httpx.post(f"{api_url}/detect/upload", data=data, files=files, timeout=30)
    resp.raise_for_status()
    return resp.json()
