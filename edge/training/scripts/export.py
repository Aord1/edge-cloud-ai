"""步骤4: 导出 OpenVINO IR → edge/training/ir/ → edge/public/neu-det/"""

from __future__ import annotations

import shutil
from pathlib import Path

from ultralytics import YOLO

from ..config import DEPLOY_DIR, IR_BIN, IR_DIR, IR_XML, RUNS_DIR


def export(model_pt: Path | None = None) -> tuple[Path, Path]:
    """PyTorch → OpenVINO IR (FP16)，复制到部署目录。

    Returns:
        (xml_path, bin_path)
    """
    if model_pt is None:
        model_pt = RUNS_DIR / "detect" / "neu-det" / "weights" / "best.pt"
    if not model_pt.exists():
        raise FileNotFoundError(f"模型未找到: {model_pt}\n请先运行 train.py")

    print(f"[导出] {model_pt} → OpenVINO IR (FP16)")
    IR_DIR.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(model_pt))
    export_dir = model.export(format="openvino", half=True)

    # 定位导出产物
    export_dir = Path(export_dir).resolve()
    src_xml = export_dir / "best.xml"
    src_bin = export_dir / "best.bin"

    # 兜底查找
    for candidate in export_dir.parent.rglob("*.xml"):
        if candidate.stem == "best":
            src_xml = candidate
            src_bin = candidate.with_suffix(".bin")
            break

    print(f"  xml: {src_xml}  ({src_xml.stat().st_size if src_xml.exists() else '?':} bytes)")
    print(f"  bin: {src_bin}  ({src_bin.stat().st_size / 1024:.1f} KB)")

    # 复制到 ir/
    shutil.copy2(src_xml, IR_XML)
    shutil.copy2(src_bin, IR_BIN)

    # 部署到 edge/public/neu-det/
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_xml, DEPLOY_DIR / "yolo26n_neu_det.xml")
    shutil.copy2(src_bin, DEPLOY_DIR / "yolo26n_neu_det.bin")

    print(f"[完成] IR: {IR_XML}")
    print(f"       部署: {DEPLOY_DIR}")
    return IR_XML, IR_BIN


if __name__ == "__main__":
    export()
