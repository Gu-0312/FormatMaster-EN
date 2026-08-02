"""Crop panel — 图像预设裁剪面板（DI 化，第 13 个迁移面板）。

标准模板（与 compress/compress_img 同构）。
特殊点：_go 入口内联收集参数（不走通用 _run_task_general 的 module_params 模式），
但 collect_params 仍提供参数供 _go 入口使用。

语义区分（重要）：
  - collect_prefs 的 "mode" 键：原始字符串（"cover（裁剪填充）"/"fit（等比适应）"），
    用于持久化恢复 Combobox 选择
  - collect_params 的 "crop_mode" 键：简化字符串（"cover"/"fit"），
    供 _go 入口传给执行层（_run_task_general 的 crop 分支读 crop_mode）
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
import main as _main
from core.image_cropper import PRESETS as CROP_PRESETS

# 预置值（与 main.py:_p_crop 原始值一致）
MODE_VALUES = ["cover（裁剪填充）", "fit（等比适应）"]
DEFAULT_PRESET = "1:1 正方形 (1080×1080)"
DEFAULT_MODE = "cover（裁剪填充）"


@dataclass
class CropContext(PanelContext):
    """图像裁剪面板状态。"""
    panel_key: str = "crop"

    # 裁剪设置
    preset: Optional[ttk.Combobox] = None   # 预设尺寸
    mode: Optional[ttk.Combobox] = None      # 裁剪模式

    # 输出目录
    out_dir_combo: Optional[ttk.Combobox] = None
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_path: Optional[tk.StringVar] = None
    out_dir_label: Optional[tk.Widget] = None

    # 底部进度栏控件（_w("crop") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class CropPanel(BasePanel):
    panel_key = "crop"
    context_cls = CropContext

    def build(self) -> tk.Widget:
        D = _main.D
        app = self.ctx._app

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["crop"] = p

        c = CropContext()
        self.context = c

        self._build_header(p, app)
        self._build_file_section(p, app)
        s = self._build_settings_card(p, c)
        self._build_output_dir(s, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("crop", c)
        return p

    # ── UI 分区构建 ─────────────────────────────────
    def _build_header(self, parent: tk.Frame, app) -> None:
        app._hdr(parent, "图像预设裁剪", "按社交媒体尺寸批量裁剪图片")

    def _build_file_section(self, parent: tk.Frame, app) -> None:
        app._file_sec(parent, "crop",
            [("图片文件", "*.jpg *.jpeg *.png *.bmp *.webp"),
             ("所有文件", "*.*")])

    def _build_settings_card(self, parent: tk.Frame, c: CropContext) -> tk.Frame:
        """构建"裁剪设置"卡片：预设尺寸 + 裁剪模式。"""
        D = _main.D
        SM = _main.SM

        s = self.ctx._app._card(parent, "裁剪设置")
        # 预设尺寸
        tk.Label(s, text="预设尺寸", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=0, column=0, sticky="w")
        c.preset = ttk.Combobox(s, values=list(CROP_PRESETS.keys()),
                                state="readonly", width=28)
        c.preset.set(DEFAULT_PRESET)
        c.preset.grid(row=0, column=1, sticky="w", padx=(8, 0))
        # 裁剪模式
        tk.Label(s, text="裁剪模式", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        c.mode = ttk.Combobox(s, values=MODE_VALUES, state="readonly", width=20)
        c.mode.set(DEFAULT_MODE)
        c.mode.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        return s

    def _build_output_dir(self, card: tk.Frame, c: CropContext, app) -> None:
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        out_frame = tk.Frame(card, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"],
                                       state="readonly", width=14)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_frame, "浏览",
                                  lambda: app._select_out_dir("crop"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path,
                                   bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: CropContext, app) -> None:
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(command=lambda: app._go("crop"))
        c.ca.configure(command=lambda: app._stop("crop"), state=tk.DISABLED)

    # ── 参数收集（供 _go 调度使用）──────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（2 键，与 main.py:_go 的 crop 分支一致）。

        - preset: 预设尺寸全名（如 "1:1 正方形 (1080×1080)"）
        - crop_mode: 简化模式名（"cover"/"fit"），从 mode 原始字符串提取

        注意：键名 crop_mode（不是 mode），与 _run_task_general 的 crop 执行分支读取键一致。
        """
        mode_raw = self.context.mode.get()
        crop_mode = "cover" if "cover" in mode_raw else "fit"
        return {
            "preset": self.context.preset.get(),
            "crop_mode": crop_mode,
        }

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 crop 分支一致，4 键）。

        注意：mode 键是原始字符串（"cover（裁剪填充）"），用于恢复 Combobox 选择，
        与 collect_params 的 crop_mode（简化字符串）语义不同。
        """
        c = self.context
        return {
            "preset": c.preset.get(),
            "mode": c.mode.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 crop 分支一致）。"""
        c = self.context
        if prefs.get("preset"):       c.preset.set(prefs["preset"])
        if prefs.get("mode"):          c.mode.set(prefs["mode"])
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
