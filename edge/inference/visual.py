"""OpenCV 中文字体渲染 — 用 PIL 在图像上绘制中文文本。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONT_PATH = "C:/Windows/Fonts/simhei.ttf"


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    path = _FONT_PATH
    if not Path(path).exists():
        path = "C:/Windows/Fonts/msyh.ttc"
    if not Path(path).exists():
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def put_chinese_text(
    img: np.ndarray,
    text: str,
    org: tuple[int, int],
    font_size: int = 20,
    color: tuple[int, int, int] = (255, 255, 255),
) -> None:
    """在 OpenCV 图像上绘制中文文本（原地修改）。

    参数:
        img: OpenCV BGR 图像 (numpy array)
        text: 待绘制文本（支持中文）
        org: 文本左下角坐标 (x, y)
        font_size: 字号
        color: BGR 颜色
    """
    if not text:
        return

    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = _get_font(font_size)
    pil_color = (color[2], color[1], color[0])
    draw.text(org, text, font=font, fill=pil_color)
    img[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def get_text_size(text: str, font_size: int = 20) -> tuple[int, int]:
    """获取文本占用的宽高（像素）。"""
    font = _get_font(font_size)
    bbox = font.getbbox(text)
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])
