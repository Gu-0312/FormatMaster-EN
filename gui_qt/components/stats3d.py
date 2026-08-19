# -*- coding: utf-8 -*-
"""stats3d — QtDataVisualization 3D 柱状统计视图（懒加载）。

Q3DBars：X=日期，Z=转换类型，Y=次数。主题随深/浅模式切换。
无 OpenGL 上下文（如 offscreen 测试）或缺库时自动兜底为提示，
不抛异常；真实桌面环境正常渲染。
"""
import os

from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from gui_qt.i18n import tr


class Stats3DDialog(QDialog):
    """3D 统计对话框：set_data(rows) 后渲染。

    rows: [{day:'08-13', type:'视频转换', count:5}, ...]
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("3D 统计视图", "3D stats view"))
        self.resize(780, 580)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        self._graph = None
        self._build()

        bar = QHBoxLayout()
        bar.addStretch(1)
        self.btn_reset = QPushButton(tr("重置视角", "Reset view"))
        self.btn_reset.clicked.connect(self._reset_view)
        bar.addWidget(self.btn_reset)
        lay.addLayout(bar)

    def _build(self):
        try:
            # 关键：offscreen（无 OpenGL 上下文）下 Q3DBars() 构造会
            # 原生 access violation 直接崩进程（连 Python 异常都抛不出），
            # 必须在构造前拦截。
            if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
                raise RuntimeError("offscreen: no OpenGL context")
            from PySide6.QtDataVisualization import Q3DBars
            self._graph = Q3DBars()
            self._graph.setMinimumWidth(740)
            self._graph.setMinimumHeight(460)
            container = QWidget.createWindowContainer(self._graph, self)
            self.layout().insertWidget(0, container, 1)
        except Exception as e:  # noqa: BLE001
            lb = QLabel(tr("3D 视图不可用：{}", "3D view unavailable: {}").format(e), self)
            lb.setAlignment(Qt.AlignCenter)
            self.layout().insertWidget(0, lb, 1)
            self._graph = None
            return

        try:
            from PySide6.QtDataVisualization import Q3DTheme
            from gui_qt.components import design_system as ds
            theme = Q3DTheme()
            theme.setType(Q3DTheme.Theme.ThemeEbony if ds.isDarkTheme()
                          else Q3DTheme.Theme.ThemePrimaryColors)
            self._graph.setTheme(theme)
            # Q3DBars 轴：columnAxis=X(日期) rowAxis=Z(类型) valueAxis=Y(次数)
            self._graph.valueAxis().setTitle(tr("次数", "Count"))
            self._graph.columnAxis().setTitle(tr("日期", "Date"))
            self._graph.rowAxis().setTitle(tr("类型", "Type"))
        except Exception:  # noqa: BLE001
            pass

    def available(self):
        return self._graph is not None

    def set_data(self, rows):
        if self._graph is None:
            return False
        try:
            from PySide6.QtDataVisualization import (QAbstract3DSeries,
                                                     QBar3DSeries,
                                                     QBarDataItem,
                                                     QCategory3DAxis)
            days, types, index = [], [], {}
            for r in rows:
                d, t, c = r["day"], r["type"], r["count"]
                if d not in index:
                    index[d] = {}
                    days.append(d)
                if t not in index[d]:
                    index[d][t] = 0
                    if t not in types:
                        types.append(t)
                index[d][t] += c

            ax_col = QCategory3DAxis()
            ax_col.setLabels(days)
            ax_row = QCategory3DAxis()
            ax_row.setLabels(types)
            self._graph.setColumnAxis(ax_col)
            self._graph.setRowAxis(ax_row)

            series = QBar3DSeries()
            series.setMesh(QAbstract3DSeries.Mesh.MeshCylinder)
            for t in types:
                row_vals = [index.get(d, {}).get(t, 0) for d in days]
                # addRow 需要 QBarDataItem 序列（PySide6 严格类型检查）
                series.dataProxy().addRow(
                    [QBarDataItem(v) for v in row_vals])
            self._graph.addSeries(series)
            self._reset_view()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _reset_view(self):
        if self._graph is None:
            return
        try:
            cam = self._graph.scene().activeCamera()
            cam.setCameraPreset(cam.CameraPreset.CameraPresetIsometricLeft)
        except Exception:  # noqa: BLE001
            pass
