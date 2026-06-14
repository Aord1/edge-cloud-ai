"""边缘端 REST API 路由 — 薄层，仅处理 HTTP 请求/响应。"""

from __future__ import annotations

import asyncio

import cv2
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse

from ..config import edge_settings

router = APIRouter()


def _get_server():
    from ..service import get_server
    srv = get_server()
    if srv is None:
        raise HTTPException(status_code=503, detail="Edge Server 未初始化")
    return srv


# ── MJPEG 流 ─────────────────────────────────────────────────────

async def _generate_mjpeg():
    server = _get_server()
    while server._stream_running:
        frame = server._latest_frame
        if frame is None:
            await asyncio.sleep(0.05)
            continue
        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, edge_settings.mjpeg_quality])
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n"
               b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n"
               + jpg.tobytes() + b"\r\n")
        await asyncio.sleep(0.02)


@router.get("/stream")
async def stream():
    return StreamingResponse(
        _generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "Connection": "close"},
    )


# ── 查询 ─────────────────────────────────────────────────────────

@router.get("/api/status")
async def api_status():
    return _get_server().get_status()


@router.get("/api/summary")
async def api_summary():
    return _get_server().get_summary()


@router.get("/api/files")
async def api_files():
    return _get_server().list_files()


@router.get("/api/cameras")
async def api_cameras():
    return _get_server().list_cameras()


# ── 配置 ─────────────────────────────────────────────────────────

@router.post("/api/configure")
async def api_configure(
    source: str = Form(default="0"),
    conf: float = Form(default=None),
    conf_edge: float = Form(default=None),
    api_url: str = Form(default=""),
    device_id: str = Form(default=""),
    video_dir: str = Form(default=""),
):
    server = _get_server()
    server.configure(
        source=source,
        conf=conf if conf is not None else edge_settings.detection_conf_threshold,
        conf_edge=conf_edge if conf_edge is not None else edge_settings.detection_conf_edge,
        api_url=api_url,
        device_id=device_id,
        video_dir=video_dir,
    )
    return {"ok": True, "source": server._source}


# ── 文件上传 ─────────────────────────────────────────────────────

@router.post("/api/upload-file", status_code=201)
async def api_upload_file(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="未收到文件")
    result = _get_server().upload_file(file.filename or "upload", data)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "上传失败"))
    return result


# ── 控制 ─────────────────────────────────────────────────────────

@router.post("/api/start")
async def api_start():
    result = _get_server().start_detection()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "启动失败"))
    return result


@router.post("/api/stop")
async def api_stop():
    return _get_server().stop_detection()