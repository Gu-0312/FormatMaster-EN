"""插件：图片信息清理（查看 EXIF 元数据，一键清理隐私信息，Pillow）。"""

import os
from plugins._i18n import t

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QPlainTextEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "图片信息清理",
    "description": "查看 / 清理 EXIF 隐私信息（拍摄时间、位置等）",
    "version": "1.0.0",
}

_KNOWN = {
    "DateTime": t("拍摄时间"), "Make": t("相机厂商"), "Model": t("相机型号"),
    "Software": t("软件"), "GPSInfo": t("GPS 信息"), "LensModel": t("镜头型号"),
    "ExposureTime": t("曝光时间"), "FNumber": t("光圈"), "ISOSpeedRatings": t("ISO"),
    "FocalLength": t("焦距"), "Orientation": t("方向"), "Artist": t("作者"),
    "Copyright": t("版权"), "XResolution": t("X 分辨率"), "YResolution": t("Y 分辨率"),
    "WhiteBalance": t("白平衡"), "Flash": t("闪光灯"),
}


def read_exif(path):
    """读取图片 EXIF → [(字段, 值), ...]。无 EXIF 返回空列表。"""
    from PIL import Image, ExifTags
    try:
        with Image.open(path) as _f:
            img = _f.copy()
        exif = img.getexif()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for k, v in exif.items():
        name = ExifTags.TAGS.get(k, str(k))
        if name == "GPSInfo" and hasattr(v, "items"):
            v = "GPS 坐标数据存在"
        out.append((_KNOWN.get(name, name), str(v)))
    return out


def strip_exif(src, dst):
    """重新保存不带 EXIF 的图片到 dst（保留原图）。"""
    from PIL import Image
    with Image.open(src) as _f:
        img = _f.copy()
    img.save(dst, exif=b"")
    return dst


class ExifPanel(QWidget):
    """图片 EXIF 查看/清理面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_pick = PrimaryPushButton(t("选择图片"))
        self.btn_pick.clicked.connect(self._pick)
        row.addWidget(self.btn_pick)
        self.btn_clean = PrimaryPushButton(t("清理并另存"))
        self.btn_clean.clicked.connect(self._clean)
        self.btn_clean.setEnabled(False)
        row.addWidget(self.btn_clean)
        self.btn_open = PrimaryPushButton(t("打开输出文件夹"))
        self.btn_open.clicked.connect(self._open_out)
        self.btn_open.setEnabled(False)
        row.addWidget(self.btn_open)
        row.addStretch(1)
        v.addLayout(row)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 1)
        self._src = ""
        self._last_out = ""
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("选择图片"), "", "图片 (*.jpg *.jpeg *.png *.webp *.bmp)")
        if not path:
            return
        self._src = path
        entries = read_exif(path)
        if not entries:
            self.ed_out.setPlainText(t("该图片没有 EXIF 信息（或格式不支持）"))
        else:
            lines = [f"文件：{os.path.basename(path)}",
                     f"EXIF 信息 {len(entries)} 条："]
            lines += [f"  {k}：{v}" for k, v in entries]
            self.ed_out.setPlainText("\n".join(lines))
        self.btn_clean.setEnabled(True)

    def _clean(self):
        if not self._src:
            return
        base, ext = os.path.splitext(self._src)
        out_path, _ = QFileDialog.getSaveFileName(
            self, t("另存为（已清理 EXIF）"), base + "_cleaned" + ext,
            f"图片 (*{ext})")
        if not out_path:
            return
        try:
            strip_exif(self._src, out_path)
        except Exception as e:  # noqa: BLE001
            self.ed_out.setPlainText(t("清理失败：{e}").format(e=e))
            return
        self._last_out = os.path.dirname(out_path)
        self.btn_open.setEnabled(True)
        remaining = read_exif(out_path)
        self.ed_out.setPlainText(
            f"✓ 已保存清理后的图片：{out_path}\n"
            f"剩余 EXIF：{len(remaining)} 条"
            + ("（未清理干净，可能是格式限制）" if remaining else "（已全部清除）"))

    def _open_out(self):
        if self._last_out and os.path.isdir(self._last_out):
            try:
                os.startfile(self._last_out)   # noqa: S606
                return
            except Exception:  # noqa: BLE001
                import subprocess
                try:
                    subprocess.Popen(["explorer", self._last_out])
                    return
                except Exception:  # noqa: BLE001
                    pass
        self.ed_out.setPlainText(t("输出目录不存在"))


PANEL_CLASS = ExifPanel


def on_load(ctx):
    pass


def on_unload():
    pass
