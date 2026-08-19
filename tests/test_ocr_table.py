"""ocr_table 单元测试：几何聚类重建、空列剪枝、自由文本分离、行聚合。

纯 numpy，离线运行，不依赖 RapidOCR 模型与 cv2。
"""
import pytest

from core.ocr_table import (reconstruct_tables, prune_table,
                            lines_from_boxes, detect_grid_lines)


def _grid_boxes(rows_text, col_xs, row_ys, W=800, H=1000):
    """构造 (text, (x0,y0,x1,y1)) 网格：rows_text[r][c] 为单元格文字。"""
    boxes = []
    for r, y in enumerate(row_ys):
        for c, x in enumerate(col_xs):
            t = rows_text[r][c]
            if not t:
                continue
            boxes.append((t, (x, y, x + 120, y + 40)))
    return boxes


def test_reconstruct_geometric_basic():
    """3 行 × 2 列网格应重建为 1 个 3x2 表格，文字落位正确。"""
    rows = [["r0c0", "r0c1"], ["r1c0", "r1c1"], ["r2c0", "r2c1"]]
    boxes = _grid_boxes(rows, col_xs=[50, 300], row_ys=[100, 300, 500])
    tables, free = reconstruct_tables(boxes, 800, 1000)
    assert len(tables) == 1 and not free
    t = tables[0]
    assert t["rows"] == 3 and t["cols"] == 2
    assert t["grid"][0] == ["r0c0", "r0c1"]
    assert t["grid"][2] == ["r2c0", "r2c1"]


def test_reconstruct_carries_sizes():
    """重建表格应带 sizes 网格，且磅值落在合理区间（非全 0、非越界）。"""
    rows = [["r0c0", "r0c1"], ["r1c0", "r1c1"], ["r2c0", "r2c1"]]
    boxes = _grid_boxes(rows, col_xs=[50, 300], row_ys=[100, 300, 500])
    tables, free = reconstruct_tables(boxes, 800, 1000, dpi=300)
    assert len(tables) == 1
    t = tables[0]
    assert "sizes" in t
    assert len(t["sizes"]) == 3 and len(t["sizes"][0]) == 2
    # 行高 40px @300dpi * calib0.85 ≈ 8.16pt
    assert 6.0 < t["sizes"][0][0] < 12.0
    assert all(0 < s <= 200 for row in t["sizes"] for s in row)


def test_prune_keeps_sizes_aligned():
    """剪枝空列/空行时，sizes 应与 grid 同步裁剪且形状一致。"""
    t = {"bbox": (0, 0, 0, 0), "rows": 2, "cols": 3,
         "grid": [["a", "", "b"], ["c", "", "d"]],
         "sizes": [[10.0, 0.0, 11.0], [9.0, 0.0, 12.0]]}
    out = prune_table(t)
    assert out["cols"] == 2
    assert out["grid"] == [["a", "b"], ["c", "d"]]
    assert out["sizes"] == [[10.0, 11.0], [9.0, 12.0]]


def test_lines_from_boxes_returns_size():
    """lines_from_boxes 应返回 (text, pt) 元组，且 pt 为正。"""
    boxes = [("B1", (10, 200, 50, 240)), ("B2", (100, 200, 150, 240)),
             ("A1", (10, 50, 50, 90))]
    lines = lines_from_boxes(boxes, dpi=300)
    assert all(isinstance(x, tuple) and len(x) == 2 and x[1] > 0 for x in lines)
    """全空列应被剪枝：['a','','b'] → ['a','b']。"""
    t = {"bbox": (0, 0, 0, 0), "rows": 2, "cols": 3,
         "grid": [["a", "", "b"], ["c", "", "d"]]}
    out = prune_table(t)
    assert out["cols"] == 2
    assert out["grid"] == [["a", "b"], ["c", "d"]]


def test_prune_removes_all_empty_row():
    """全空行应被剪枝。"""
    t = {"bbox": (0, 0, 0, 0), "rows": 2, "cols": 2,
         "grid": [["a", "b"], ["", ""]]}
    out = prune_table(t)
    assert out["rows"] == 1
    assert out["grid"] == [["a", "b"]]


def test_single_column_is_free_text():
    """只有 1 列（不足 min_cols=2）应判为自由文本，不误判为表格。"""
    boxes = [("行一", (50, 100, 200, 140)),
             ("行二", (50, 300, 200, 340)),
             ("行三", (50, 500, 200, 540))]
    tables, free = reconstruct_tables(boxes, 800, 1000)
    assert tables == [] and len(free) == 3


def test_lines_from_boxes_join():
    """同行多框按 x 聚合为一行，行间按 y 排序；返回 (text, size) 元组。"""
    boxes = [("B1", (10, 200, 50, 240)), ("B2", (100, 200, 150, 240)),
             ("A1", (10, 50, 50, 90))]
    lines = lines_from_boxes(boxes)
    assert [t for t, _ in lines] == ["A1", "B1 B2"]
    assert all(s > 0 for _, s in lines)


def test_detect_grid_lines_no_cv2_safe():
    """无图/无效路径时检测返回空，不抛异常。"""
    rows_y, cols_x = detect_grid_lines("__not_exist__.png")
    assert rows_y == [] and cols_x == []


def test_merge_spanning_column_header():
    """跨列标题（一个 box 覆盖多列）应生成合并单元格信息。"""
    # 标题跨列0-1（x 覆盖两列中心），下方两行单格
    boxes = [
        ("总标题横跨两列", (50, 100, 420, 140)),
        ("a1", (50, 200, 170, 240)),
        ("b1", (300, 200, 420, 240)),
        ("a2", (50, 300, 170, 340)),
        ("b2", (300, 300, 420, 340)),
    ]
    tables, free = reconstruct_tables(boxes, 800, 1000, dpi=300)
    assert len(tables) == 1
    t = tables[0]
    assert t["cols"] == 2
    # 应检测到跨列合并 (row0, col0..col1)
    assert (0, 0, 0, 1) in t["merges"]
    assert "总标题横跨两列" in t["grid"][0][0]


def test_merge_spanning_row():
    """跨行项目名（一个 box 覆盖多行）应生成跨行合并信息。"""
    boxes = [
        ("项目A", (50, 100, 170, 340)),   # y 覆盖 row0(100) 与 row1(300) 中心
        ("x", (300, 100, 420, 140)),
        ("y", (300, 300, 420, 340)),
    ]
    tables, free = reconstruct_tables(boxes, 800, 1000, dpi=300)
    assert len(tables) == 1
    t = tables[0]
    assert (0, 0, 1, 0) in t["merges"]


def test_no_false_merge_single_row():
    """纯单格框不应产生任何合并。"""
    rows = [["x", "y"], ["z", "w"]]
    boxes = _grid_boxes(rows, col_xs=[50, 300], row_ys=[100, 300])
    tables, free = reconstruct_tables(boxes, 800, 1000, dpi=300)
    assert tables and not tables[0]["merges"]


def test_col_bounds_present_and_aligned():
    """重建表格应带 col_bounds，且列数与 grid 一致。"""
    rows = [["x", "y"], ["z", "w"]]
    boxes = _grid_boxes(rows, col_xs=[50, 300], row_ys=[100, 300])
    tables, free = reconstruct_tables(boxes, 800, 1000, dpi=300)
    t = tables[0]
    assert len(t["col_bounds"]) == t["cols"] == 2


def test_prune_syncs_merges():
    """剪枝空列时，合并坐标应同步重映射。"""
    # 3 列，中间列全空（会被剪）；(0,0)-(0,2) 跨列合并
    t = {"bbox": (0, 0, 0, 0), "rows": 2, "cols": 3,
         "grid": [["H", "", "H"], ["a", "", "b"]],
         "sizes": [[10.0, 0.0, 10.0], [9.0, 0.0, 11.0]],
         "merges": [(0, 0, 0, 2)],
         "col_bounds": [(0, 50), (50, 100), (100, 150)]}
    out = prune_table(t)
    assert out["cols"] == 2
    # 合并跨列0-2 剪掉中间列后应为 (0,0)-(0,1)
    assert (0, 0, 0, 1) in out["merges"]
    assert len(out["col_bounds"]) == 2
