"""ocr_table hybrid（RapidTable 结构模型 + 几何兜底）单元测试。

纯离线：不初始化真实模型，用 monkeypatch 注入假引擎/降级路径。
"""
import numpy as np
import pytest

from core import ocr_table as ot
from core.ocr_table import (
    reconstruct_tables_hybrid, _parse_table_html, _html_rows_to_grid,
    _raw_to_items,
)


def _grid_boxes(rows_text, col_xs, row_ys):
    """构造 (text, (x0,y0,x1,y1)) 网格。"""
    boxes = []
    for r, y in enumerate(row_ys):
        for c, x in enumerate(col_xs):
            t = rows_text[r][c]
            if not t:
                continue
            boxes.append((t, (x, y, x + 120, y + 40)))
    return boxes


def _white_img(path, w=800, h=1000):
    from PIL import Image
    Image.new("RGB", (w, h), "white").save(path)
    return path


def _fake_raw(rows_text, col_xs, row_ys):
    """按网格构造含置信度的 rapidocr 原始结果。"""
    raw = []
    for r, y in enumerate(row_ys):
        for c, x in enumerate(col_xs):
            t = rows_text[r][c]
            if not t:
                continue
            raw.append([[[x, y], [x + 120, y], [x + 120, y + 40], [x, y + 40]],
                        t, 0.9])
    return raw


# ── HTML 解析 ──────────────────────────────
def test_parse_table_html_rowspan_colspan():
    html = ('<table><tr><td rowspan="2">A</td><td>B</td></tr>'
            '<tr><td colspan="2">C</td></tr>'
            '<tr><td>D</td><td>E</td></tr></table>')
    rows = _parse_table_html(html)
    assert rows[0] == [("A", 2, 1), ("B", 1, 1)]
    assert rows[1] == [("C", 1, 2)]
    assert rows[2] == [("D", 1, 1), ("E", 1, 1)]


def test_parse_table_html_empty():
    assert _parse_table_html("") == []
    assert _parse_table_html("<html><body>no table</body></html>") == []


def test_html_rows_to_grid_rowspan():
    rows = [[("A", 2, 1), ("B", 1, 1)], [("C", 1, 1)],
            [("D", 1, 1), ("E", 1, 1)]]
    grid, merges, nrows, ncols = _html_rows_to_grid(rows)
    assert nrows == 3 and ncols == 2
    assert grid == [["A", "B"], ["", "C"], ["D", "E"]]
    assert (0, 0, 1, 0) in merges


def test_html_rows_to_grid_colspan():
    rows = [[("H", 1, 2)], [("a", 1, 1), ("b", 1, 1)]]
    grid, merges, nrows, ncols = _html_rows_to_grid(rows)
    assert grid == [["H", ""], ["a", "b"]]
    assert (0, 0, 0, 1) in merges


def test_html_rows_to_grid_rowspan_colspan_mixed():
    rows = [[("H", 2, 2)], [("x", 1, 1)], [("a", 1, 1), ("b", 1, 1)]]
    grid, merges, nrows, ncols = _html_rows_to_grid(rows)
    assert grid == [["H", ""], ["", ""], ["a", "b"]]
    assert (0, 0, 1, 1) in merges


def test_html_rows_to_grid_empty():
    grid, merges, nrows, ncols = _html_rows_to_grid([])
    assert grid == [] and nrows == 0 and ncols == 0


# ── 原始结果转换 ────────────────────────────
def test_raw_to_items():
    raw = [[[[0, 0], [10, 0], [10, 5], [0, 5]], "hi", 0.9]]
    items = _raw_to_items(raw)
    assert len(items) == 1
    cx, cy, bbox, text, conf = items[0]
    assert (cx, cy) == (5.0, 2.5)
    assert text == "hi" and conf == 0.9
    assert len(bbox) == 4


def test_raw_to_items_bad_item_skipped():
    raw = [[[0, 1], "no-bbox", 0.5]]
    assert _raw_to_items(raw) == []


# ── hybrid：降级与结构模型路径 ──────────────
def test_hybrid_fallback_when_engine_unavailable(tmp_path, monkeypatch):
    """引擎不可用 → 返回几何重建结果（方案 D 兜底）。"""
    monkeypatch.setattr(ot, "_get_rapid_table_engine", lambda: None)
    rows = [["r0c0", "r0c1"], ["r1c0", "r1c1"], ["r2c0", "r2c1"]]
    boxes = _grid_boxes(rows, [50, 300], [100, 300, 500])
    img = _white_img(str(tmp_path / "t.png"))
    tables, free = reconstruct_tables_hybrid(boxes, 800, 1000,
                                             image_path=img)
    assert len(tables) == 1
    assert tables[0]["grid"][0] == ["r0c0", "r0c1"]
    assert tables[0]["rows"] == 3 and tables[0]["cols"] == 2


class _FakeOut:
    pred_htmls = ['<table><tr><td rowspan="2">A</td><td>B</td></tr>'
                  '<tr><td>C</td></tr>'
                  '<tr><td colspan="2">E</td></tr></table>']


class _FakeEngine:
    def __call__(self, img, ocr_results=None):
        return _FakeOut()


def test_hybrid_uses_rapidtable_structure(tmp_path, monkeypatch):
    """引擎可用 → 表格区域用结构模型输出（rowspan/colspan 生效）。"""
    monkeypatch.setattr(ot, "_get_rapid_table_engine", lambda: _FakeEngine())
    rows = [["A", "B"], ["C", "D"], ["E", "F"]]
    boxes = _grid_boxes(rows, [50, 300], [100, 300, 500])
    img = _white_img(str(tmp_path / "t.png"))
    raw = _fake_raw(rows, [50, 300], [100, 300, 500])
    tables, free = reconstruct_tables_hybrid(boxes, 800, 1000,
                                             image_path=img, dpi=300,
                                             ocr_raw=raw)
    assert len(tables) == 1
    t = tables[0]
    # 结构模型输出 3x2：A 跨行 2 格、E 跨列 2 格
    assert t["rows"] == 3 and t["cols"] == 2
    assert t["grid"][0] == ["A", "B"]
    assert t["grid"][1] == ["", "C"]
    assert t["grid"][2] == ["E", ""]
    assert (0, 0, 1, 0) in t["merges"]
    assert (2, 0, 2, 1) in t["merges"]


def test_hybrid_degenerate_structure_falls_back(tmp_path, monkeypatch):
    """结构模型输出退化（单列）→ 回退几何结果。"""

    class _DegenerateOut:
        pred_htmls = ['<table><tr><td>整页文字一</td></tr>'
                      '<tr><td>整页文字二</td></tr>'
                      '<tr><td>整页文字三</td></tr></table>']

    class _DegenerateEngine:
        def __call__(self, img, ocr_results=None):
            return _DegenerateOut()

    monkeypatch.setattr(ot, "_get_rapid_table_engine",
                        lambda: _DegenerateEngine())
    rows = [["A", "B"], ["C", "D"], ["E", "F"]]
    boxes = _grid_boxes(rows, [50, 300], [100, 300, 500])
    img = _white_img(str(tmp_path / "t.png"))
    raw = _fake_raw(rows, [50, 300], [100, 300, 500])
    tables, free = reconstruct_tables_hybrid(boxes, 800, 1000,
                                             image_path=img, dpi=300,
                                             ocr_raw=raw)
    assert len(tables) == 1
    assert tables[0]["rows"] == 3 and tables[0]["cols"] == 2
    assert tables[0]["grid"][0] == ["A", "B"]


def test_hybrid_no_image_path_uses_geometry():
    """无 image_path → 直接几何结果（不触发结构模型）。"""
    rows = [["x", "y"], ["z", "w"]]
    boxes = _grid_boxes(rows, [50, 300], [100, 300])
    tables, free = reconstruct_tables_hybrid(boxes, 800, 1000)
    assert len(tables) == 1
    assert tables[0]["grid"][0] == ["x", "y"]
