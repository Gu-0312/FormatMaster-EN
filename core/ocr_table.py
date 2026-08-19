"""ocr_table — 扫描件表格结构识别与重建。

把 RapidOCR 返回的带坐标文本框，重建成二维「单元格文本网格」，
供上层生成真正可编辑的 Word 表格（而非平铺段落）。

策略：
1. 几何聚类（主，纯 numpy，离线可用）：按垂直重叠分行 → 全局列锚点聚类
   → 连续多行共享 ≥2 列即判定为表格 → 按 (行,列) 填字 → 剪枝空列/空行。
2. OpenCV 栅格线检测（辅，可选）：检测扫描页中的横/竖栅格线，
   用于更精确地切分表格区域。不依赖 cv2 也能工作，缺失时自动降级为纯几何。

输入坐标约定：与渲染页图像同分辨率的图像像素坐标 (x0, y0, x1, y1)。
注意：core.ocr_tool.ocr_image_detailed 返回的是归一化坐标 [0,1]，
调用前需乘以图像宽高反归一化为像素坐标（见 core.ocr_batch 的用法）。
"""

from __future__ import annotations

import math

import numpy as np

# 把 OCR 文本框像素高度换算为 Word 磅值的校准系数。
# RapidOCR 的框通常是整行文字的包围盒（略大于真实字号），
# 取 0.85 左右可让换算出的磅值更接近原文件实际字号。
FONT_CALIB = 0.85


# ── 基础工具 ─────────────────────────────────────
def _cluster_anchors(values, tol):
    """把一维坐标聚类为若干锚点（升序返回锚点均值列表）。"""
    if not values:
        return []
    s = sorted(values)
    clusters = [[s[0]]]
    for v in s[1:]:
        if v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def _median(values):
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _nearest_index(anchors, x):
    """返回 x 在 anchors 中最近元素的下标。"""
    best_i = 0
    best_d = abs(anchors[0] - x)
    for i, a in enumerate(anchors[1:], start=1):
        d = abs(a - x)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def _box_point_size(box, dpi):
    """把像素文本框高度换算为 Word 磅值（带校准系数与合理区间）。

    box: 图像像素坐标 (x0, y0, x1, y1)。换算公式：
    磅值 = (像素高 / dpi * 72) * FONT_CALIB。
    返回 float；异常或不可用时返回 0.0（调用方按默认处理）。
    """
    try:
        ph = float(box[3] - box[1])
        if ph <= 0:
            return 0.0
        pt = ph / float(dpi) * 72.0 * FONT_CALIB
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0
    # 合理区间，避免极端值
    return max(4.0, min(200.0, pt))


# ── OpenCV 栅格线检测（可选） ──────────────────
def detect_grid_lines(image_path, h_scale=40, v_scale=40, min_len_ratio=0.25):
    """用 OpenCV 检测扫描页横/竖栅格线，返回 (rows_y, cols_x)。

    rows_y: 横线 y 坐标列表（升序）；cols_x: 竖线 x 坐标列表（升序）。
    无 cv2 或检测失败时返回 ([], [])。
    """
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return [], []

    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return [], []
    h, w = img.shape
    if h < 10 or w < 10:
        return [], []

    # 二值化（反相：线为白）
    _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 横向线：细长水平核
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, w // h_scale), 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=1)
    # 纵向线：细长垂直核
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(5, h // v_scale)))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=1)

    def _collect_lines(mask, horizontal):
        coords = []
        n_c, labels, stats, _ = cv2.connectedComponents(mask, 8)
        for ci in range(1, n_c):
            area = stats[ci, cv2.CC_STAT_AREA]
            x = stats[ci, cv2.CC_STAT_LEFT]
            y = stats[ci, cv2.CC_STAT_TOP]
            ww = stats[ci, cv2.CC_STAT_WIDTH]
            hh = stats[ci, cv2.CC_STAT_HEIGHT]
            if horizontal and ww >= min_len_ratio * w and hh <= max(6, h // 60):
                coords.append(y + hh / 2.0)
            elif (not horizontal) and hh >= min_len_ratio * h and ww <= max(6, w // 60):
                coords.append(x + ww / 2.0)
        return coords

    rows_y = _collect_lines(h_lines, True)
    cols_x = _collect_lines(v_lines, False)
    return rows_y, cols_x


# ── 几何聚类重建（主） ──────────────────────────
def _group_rows(boxes, row_tol):
    """按中心 y 聚类把 boxes 分成行；行内按 x0 升序。"""
    cy = [(b[1][1] + b[1][3]) / 2.0 for b in boxes]
    anchors = _cluster_anchors(cy, row_tol)
    rows = {}
    for b, c in zip(boxes, cy):
        best = min(anchors, key=lambda a: abs(a - c))
        rows.setdefault(best, []).append(b)
    out = [rows[a] for a in sorted(rows)]
    for r in out:
        r.sort(key=lambda b: b[1][0])
    return out


def prune_table(table):
    """剪枝表格中的全空列与全空行，返回新的 table dict。

    全空列（所有行该列均为空）通常是双栏布局的 gutter 或栅格间隙，
    应移除以得到干净的 Word 表格。sizes / merges / col_bounds 与 grid 同步剪枝。
    """
    grid = [list(row) for row in table.get("grid", [])]
    sizes = [list(row) for row in table.get("sizes", [])]
    merges = [tuple(m) for m in table.get("merges", [])]
    col_bounds = [tuple(c) for c in table.get("col_bounds", [])]
    if not grid:
        return {"bbox": table.get("bbox", (0, 0, 0, 0)), "rows": 0, "cols": 0,
                "grid": [], "sizes": [], "merges": [], "col_bounds": []}
    n_rows = len(grid)
    n_cols = len(grid[0]) if grid else 0
    if n_cols == 0:
        return table

    # 列保留（原始列非空），并建立旧→新列索引映射
    keep_col = [any(grid[r][c].strip() for r in range(n_rows)) for c in range(n_cols)]
    old2new_col = {}
    nc = 0
    for c in range(n_cols):
        if keep_col[c]:
            old2new_col[c] = nc
            nc += 1
    new_grid = [[grid[r][c] for c in range(n_cols) if keep_col[c]] for r in range(n_rows)]
    new_sizes = [[sizes[r][c] for c in range(n_cols) if keep_col[c]] for r in range(n_rows)] \
        if sizes else []
    new_col_bounds = [col_bounds[c] for c in range(n_cols) if keep_col[c]] \
        if col_bounds else []

    # 行保留（剪列后行非空），并建立旧→新行索引映射
    keep_row = [any(new_grid[r][c].strip() for c in range(len(new_grid[r])))
                for r in range(len(new_grid))]
    old2new_row = {}
    nr = 0
    for r in range(len(new_grid)):
        if keep_row[r]:
            old2new_row[r] = nr
            nr += 1
    new_grid = [new_grid[r] for r in range(len(new_grid)) if keep_row[r]]
    new_sizes = [new_sizes[r] for r in range(len(new_sizes)) if keep_row[r]] \
        if new_sizes else []

    # 合并单元格坐标重映射（涉及被删行/列的 merge 视为失效）
    new_merges = []
    for (r1, c1, r2, c2) in merges:
        if r1 in old2new_row and r2 in old2new_row \
                and c1 in old2new_col and c2 in old2new_col:
            new_merges.append((old2new_row[r1], old2new_col[c1],
                               old2new_row[r2], old2new_col[c2]))

    new_cols = len(new_grid[0]) if new_grid else 0
    return {
        "bbox": table.get("bbox", (0, 0, 0, 0)),
        "rows": len(new_grid),
        "cols": new_cols,
        "grid": new_grid,
        "sizes": new_sizes,
        "merges": new_merges,
        "col_bounds": new_col_bounds,
    }


def _span_in_axis(box_lo, box_hi, centers):
    """返回 box 在轴（centers 升序）上覆盖的 [lo, hi] 索引（含）。

    以 box 跨过的 grid 中心判定跨行/跨列：若 box 同时覆盖相邻多个
    center，即视为合并单元格；否则归入最近 center。单格 box 返回 (k, k)。
    """
    if not centers:
        return 0, 0
    covered = [i for i, c in enumerate(centers) if box_lo <= c <= box_hi]
    if covered:
        return min(covered), max(covered)
    k = min(range(len(centers)),
            key=lambda i: min(abs(centers[i] - box_lo), abs(centers[i] - box_hi)))
    return k, k


def _col_x_bounds(centers):
    """由列中心生成每列的像素 x 边界 (x0, x1)（相邻中心中点分界）。"""
    n = len(centers)
    out = []
    for c in range(n):
        if c > 0:
            lo = (centers[c - 1] + centers[c]) / 2.0
        else:
            lo = centers[c] - ((centers[1] - centers[0]) if n > 1 else 50.0)
        if c < n - 1:
            hi = (centers[c] + centers[c + 1]) / 2.0
        else:
            hi = centers[c] + ((centers[c] - centers[c - 1]) if n > 1 else 50.0)
        out.append((lo, hi))
    return out


def _build_grid_from_runs(run, all_cols, img_w, img_h, dpi,
                          row_centers, col_centers):
    """把连续行 run 填成二维网格，识别合并单元格，生成 sizes 与列边界。

    合并单元格：单个 OCR 文本框若垂直/水平跨越多行/多列（如标题跨列、
    项目名跨行），则记录 merge 跨度，供上层生成 Word 合并单元格。
    """
    n_rows = len(run)
    n_cols = len(all_cols)
    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    sizes = [[0.0 for _ in range(n_cols)] for _ in range(n_rows)]
    raw_merges = []
    bbox = [10 ** 9, 10 ** 9, -10 ** 9, -10 ** 9]
    for ri, rc in enumerate(run):
        for ci, b in rc:
            box = b[1]
            x0, y0, x1, y1 = box[0], box[1], box[2], box[3]
            r_top, r_bot = _span_in_axis(y0, y1, row_centers)
            c_left, c_right = _span_in_axis(x0, x1, col_centers)
            txt = b[0]
            if grid[r_top][c_left]:
                grid[r_top][c_left] = (grid[r_top][c_left] + " " + txt).strip()
            else:
                grid[r_top][c_left] = txt
            sizes[r_top][c_left] = _box_point_size(box, dpi)
            bbox[0] = min(bbox[0], x0)
            bbox[1] = min(bbox[1], y0)
            bbox[2] = max(bbox[2], x1)
            bbox[3] = max(bbox[3], y1)
            if r_bot > r_top or c_right > c_left:
                raw_merges.append((r_top, c_left, r_bot, c_right))
    col_x = _col_x_bounds(col_centers)
    table = {"bbox": tuple(bbox), "rows": n_rows, "cols": n_cols,
             "grid": grid, "sizes": sizes,
             "merges": raw_merges, "col_bounds": col_x}
    return prune_table(table)


def _reconstruct_geometric(boxes, img_w, img_h, row_tol, col_tol,
                           min_rows, min_cols, dpi=300):
    """纯几何聚类的表格重建。返回 (tables, free_boxes)。"""
    items = [(t, tuple(b)) for t, b in boxes
             if t and t.strip() and len(b) == 4]
    if not items:
        return [], []

    heights = [b[3] - b[1] for _, b in items]
    med_h = _median(heights) or 10.0
    if row_tol is None:
        row_tol = max(6.0, med_h * 0.6)
    if col_tol is None:
        col_tol = max(6.0, med_h * 0.8)

    rows = _group_rows(items, row_tol)
    cy = [(box[1] + box[3]) / 2.0 for _, box in items]
    row_centers = _cluster_anchors(cy, row_tol)

    # 全局列锚点（按各 box 左缘 x0 聚类）
    lefts = [b[1][0] for b in items]
    col_anchors = _cluster_anchors(lefts, col_tol)
    if len(col_anchors) < min_cols:
        # 列不足以构成表格 → 全部视为自由文本
        return [], list(items)

    # 为每行分配每个 box 的最近列，并算出其跨列跨度（用于合并判定）
    row_cols = []  # 每行：list of (col_idx, box)
    row_spans = []  # 每行：list of (c_left, c_right, box)
    for r in rows:
        assigned = []
        spans = []
        for b in r:
            ci = _nearest_index(col_anchors, b[1][0])
            c_left, c_right = _span_in_axis(b[1][0], b[1][2], col_anchors)
            assigned.append((ci, b))
            spans.append((c_left, c_right, b))
        row_cols.append(assigned)
        row_spans.append(spans)

    # 判定表格：连续多行（每行至少用到 1 列），整体共享列数 ≥ min_cols、
    # 行数 ≥ min_rows 即视为表格。这样跨行项目名（独占一行、仅 1 列）也能
    # 与上下行共同构成多列表格，正确识别合并单元格。
    def _row_used_cols(spans):
        cols = set()
        for c_left, c_right, _b in spans:
            for c in range(c_left, c_right + 1):
                cols.add(c)
        return sorted(cols)
    used_cols_per_row = [_row_used_cols(sp) for sp in row_spans]
    has_col = [len(uc) >= 1 for uc in used_cols_per_row]

    tables = []
    free = []
    i = 0
    n = len(row_cols)
    while i < n:
        if not has_col[i]:
            for _, b in row_cols[i]:
                free.append(b)
            i += 1
            continue
        j = i
        while j < n and has_col[j]:
            j += 1
        run = row_cols[i:j]
        all_cols = set()
        for uc in used_cols_per_row[i:j]:
            all_cols.update(uc)
        all_cols = sorted(all_cols)
        if len(all_cols) >= min_cols and (j - i) >= min_rows:
            table = _build_grid_from_runs(run, all_cols, img_w, img_h, dpi,
                                          row_centers[i:j], col_anchors)
            if table["rows"] >= 1 and table["cols"] >= 1:
                tables.append(table)
            i = j
            continue
        else:
            for row in run:
                for _, b in row:
                    free.append(b)
            i = j
            continue

    return tables, free


def _reconstruct_with_lines(image_path, boxes, img_w, img_h,
                            min_rows, min_cols, dpi=300):
    """融合栅格线检测的表格重建：用线构造规则网格并填字。"""
    rows_y, cols_x = detect_grid_lines(image_path)
    if len(rows_y) < 2 or len(cols_x) < 2:
        return [], []

    items = [(t, tuple(b)) for t, b in boxes
             if t and t.strip() and len(b) == 4]
    if not items:
        return [], []

    ry = sorted(rows_y)
    cx = sorted(cols_x)
    n_rows = len(ry) - 1
    n_cols = len(cx) - 1
    if n_rows < min_rows or n_cols < min_cols:
        return [], []

    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    sizes = [[0.0 for _ in range(n_cols)] for _ in range(n_rows)]
    assigned = set()
    for idx, (text, b) in enumerate(items):
        ccx = (b[0] + b[2]) / 2.0
        ccy = (b[1] + b[3]) / 2.0
        col = None
        for c in range(n_cols):
            if cx[c] <= ccx <= cx[c + 1]:
                col = c
                break
        row = None
        for r in range(n_rows):
            if ry[r] <= ccy <= ry[r + 1]:
                row = r
                break
        if row is None or col is None:
            continue
        grid[row][col] = (grid[row][col] + " " + text).strip() if grid[row][col] else text
        sizes[row][col] = _box_point_size(b[1], dpi)
        assigned.add(idx)

    free = [items[i] for i in range(len(items)) if i not in assigned]
    col_bounds = [(cx[c], cx[c + 1]) for c in range(n_cols)] if n_cols > 0 else []
    table = {
        "bbox": (cx[0], ry[0], cx[-1], ry[-1]),
        "rows": n_rows,
        "cols": n_cols,
        "grid": grid,
        "sizes": sizes,
        "merges": [],
        "col_bounds": col_bounds,
    }
    table = prune_table(table)
    if table["rows"] < 1 or table["cols"] < 1:
        return [], free
    return [table], free


# ── 统一入口 ─────────────────────────────────────
def reconstruct_tables(boxes, img_w, img_h,
                       row_tol=None, col_tol=None,
                       min_rows=2, min_cols=2,
                       use_grid_lines=False, image_path=None, dpi=300):
    """从带坐标文本框重建表格（统一入口）。

    boxes: [(text, (x0,y0,x1,y1)), ...]（图像像素坐标）。
    img_w, img_h: 对应渲染图像的尺寸（像素）。
    dpi: 渲染图像使用的 DPI，用于把文本框像素高度换算为 Word 磅值。
    use_grid_lines: 是否尝试用 OpenCV 栅格线辅助（需 image_path 与 cv2）。
    返回 (tables, free_boxes)：
      tables: 元素为 dict {'bbox', 'rows', 'cols', 'grid', 'sizes'}，
              grid 为 [[cell_text,...],...]，空串表示空单元格；
              sizes 为同形 [[cell_pt,...]]，单元格磅值（0 表示未知）。
      free_boxes: 未归入表格的 (text, box) 列表。
    """
    if use_grid_lines and image_path:
        tables, free = _reconstruct_with_lines(
            image_path, boxes, img_w, img_h, min_rows, min_cols, dpi)
        if tables:
            return tables, free
    return _reconstruct_geometric(
        boxes, img_w, img_h, row_tol, col_tol, min_rows, min_cols, dpi)


def lines_from_boxes(boxes, row_tol=None, dpi=300):
    """把自由文本框按行聚类，返回每行 (拼接文本, 行磅值) 列表。

    用于把非表格区域的 OCR 文字还原成可读段落（保持阅读顺序）。
    行磅值取该行各框磅值的中位数，用于让 Word 中的字号接近原文件。
    """
    items = [(t, tuple(b)) for t, b in boxes
             if t and t.strip() and len(b) == 4]
    if not items:
        return []
    heights = [b[3] - b[1] for _, b in items]
    med_h = _median(heights) or 10.0
    if row_tol is None:
        row_tol = max(6.0, med_h * 0.6)
    rows = _group_rows(items, row_tol)
    out = []
    for r in rows:
        line = " ".join(t for t, _b in r if t.strip())
        if line.strip():
            szs = [_box_point_size(b, dpi) for _, b in r]
            szs = [s for s in szs if s > 0]
            size = _median(szs) if szs else 0.0
            out.append((line, size))
    return out


# ── RapidTable 结构模型（方案 A） ──────────────────
# 用深度学习表格结构模型（SLANet-plus，onnx）替代纯几何行列划分，
# 正确处理合并单元格/复杂表头。不可用或退化时自动降级回几何重建（方案 D）。
_rapid_table_engine = None
_rapid_table_state = None  # None=未探测 / True=可用 / False=不可用


def _get_rapid_table_engine():
    """懒加载 RapidTable 引擎（SLANet-plus）。导入/加载失败返回 None。"""
    global _rapid_table_engine, _rapid_table_state
    if _rapid_table_state is not None:
        return _rapid_table_engine if _rapid_table_state else None
    try:
        from rapid_table import ModelType, RapidTable, RapidTableInput
        _rapid_table_engine = RapidTable(
            RapidTableInput(model_type=ModelType.SLANETPLUS, use_ocr=True))
        _rapid_table_state = True
    except Exception:  # noqa: BLE001 - 无模型/缺依赖均降级
        _rapid_table_engine = None
        _rapid_table_state = False
    return _rapid_table_engine if _rapid_table_state else None


def _raw_to_items(raw):
    """把 rapidocr 原始结果转 (cx, cy, bbox4, text, conf) 列表（bbox 为像素4点）。"""
    out = []
    for item in raw or []:
        try:
            bbox, text = item[0], item[1]
            conf = float(item[2]) if len(item) > 2 else 0.9
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            if not xs or not ys:
                continue
            out.append((sum(xs) / len(xs), sum(ys) / len(ys),
                        bbox, text or "", conf))
        except Exception:  # noqa: BLE001 - 单条异常跳过
            continue
    return out


def _html_rows_to_grid(rows):
    """把 HTML 解析出的 [[(text, rowspan, colspan), ...], ...] 展开为网格。

    返回 (grid, merges, nrows, ncols)：
      grid: 二维文本（合并区域除左上角外为空串）；
      merges: [(r1,c1,r2,c2), ...] 与 _add_word_table 契约一致。
    """
    ncols = 0
    for cells in rows:
        ncols = max(ncols, sum(c[2] for c in cells))
    if ncols == 0:
        return [], [], 0, 0
    grid, merges, pending = [], [], [0] * ncols
    for r, cells in enumerate(rows):
        row = [""] * ncols
        c = 0
        for text, rs, cs in cells:
            while c < ncols and pending[c] > 0:
                pending[c] -= 1
                c += 1
            if c >= ncols:
                break
            row[c] = (text or "").strip()
            if rs > 1:
                for cc in range(c, min(ncols, c + cs)):
                    pending[cc] = max(pending[cc], rs - 1)
            if cs > 1 or rs > 1:
                # 越界合并截断到网格边界，避免生成无效 merge
                merges.append((r, c, r + rs - 1,
                               min(c + cs - 1, ncols - 1)))
            c += cs
        grid.append(row)
    return grid, merges, len(grid), ncols


def _parse_table_html(html):
    """解析 RapidTable 输出的 <table> HTML → [[(text, rowspan, colspan), ...], ...]。

    用标准库 HTMLParser，容忍 td/th 混排与单元格内换行。
    """
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.rows, self.row, self.cell = [], None, None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.row = []
            elif tag in ("td", "th"):
                a = dict(attrs)
                self.cell = [None, 1, 1]  # text, rowspan, colspan
                try:
                    self.cell[1] = max(1, int(a.get("rowspan", "1")))
                except (TypeError, ValueError):
                    pass
                try:
                    self.cell[2] = max(1, int(a.get("colspan", "1")))
                except (TypeError, ValueError):
                    pass

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.cell is not None:
                self.row.append((self.cell[0] or "", self.cell[1], self.cell[2]))
                self.cell = None
            elif tag == "tr" and self.row is not None:
                if self.row:
                    self.rows.append(self.row)
                self.row = None

        def handle_data(self, data):
            if self.cell is not None:
                self.cell[0] = (self.cell[0] or "") + data

    p = _P()
    try:
        p.feed(html or "")
        p.close()
    except Exception:  # noqa: BLE001 - 解析失败按无表格处理
        return []
    return [r for r in p.rows if r]


def _rebuild_table_with_rapidtable(engine, image_path, bbox, items, dpi):
    """对单个表格区域用 RapidTable 重建结构；失败/退化返回 None（调用方兜底）。"""
    x0, y0, x1, y1 = [int(round(v)) for v in bbox]
    pad = 6
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = x1 + pad
    y1 = y1 + pad
    if x1 - x0 < 20 or y1 - y0 < 20:
        return None
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            crop = im.crop((x0, y0, x1, y1))
        crop_np = np.array(crop.convert("RGB"))
    except Exception:  # noqa: BLE001
        return None
    # 区域内 OCR 框（中心点落入扩边后的 bbox），坐标相对裁剪图
    sel = [(cx - x0, cy - y0, b, t, c) for (cx, cy, b, t, c) in items
           if x0 <= cx <= x1 and y0 <= cy <= y1]
    if len(sel) < 2:
        return None
    boxes_np = np.array([b for _, _, b, _, _ in sel], dtype=np.float32)
    txts = tuple(t for _, _, _, t, _ in sel)
    scores = tuple(c for _, _, _, _, c in sel)
    try:
        res = engine(crop_np, ocr_results=[(boxes_np, txts, scores)])
        html = res.pred_htmls[0] if (res and res.pred_htmls) else None
    except Exception:  # noqa: BLE001
        return None
    if not html:
        return None
    rows = _parse_table_html(html)
    grid, merges, nrows, ncols = _html_rows_to_grid(rows)
    if nrows < 2 or ncols < 2:
        return None  # 结构模型退化（整页文字被识别为单列表格）→ 几何兜底
    sizes = [[0.0] * ncols for _ in range(nrows)]
    return {"bbox": tuple(bbox), "rows": nrows, "cols": ncols,
            "grid": grid, "sizes": sizes, "merges": merges,
            "col_bounds": []}


def reconstruct_tables_hybrid(boxes, img_w, img_h, image_path=None, dpi=300,
                              use_grid_lines=False, ocr_raw=None,
                              min_rows=2, min_cols=2):
    """表格结构识别：RapidTable(SLANet) 为主，几何重建兜底（方案 A+D）。

    - 先用几何算法定位表格区域 bbox（其 grid 仅作兜底）；
    - 每个区域裁剪后交给 RapidTable 还原结构（正确处理合并单元格）；
    - RapidTable 不可用/输出退化时，该区域回退为几何 grid。
    返回 (tables, free_boxes)，与 reconstruct_tables 同构。
    """
    if use_grid_lines and image_path:
        tables, free = _reconstruct_with_lines(
            image_path, boxes, img_w, img_h, min_rows, min_cols, dpi)
        if not tables:
            tables, free = _reconstruct_geometric(
                boxes, img_w, img_h, None, None, min_rows, min_cols, dpi)
    else:
        tables, free = _reconstruct_geometric(
            boxes, img_w, img_h, None, None, min_rows, min_cols, dpi)

    engine = _get_rapid_table_engine()
    if engine is None or not tables or not image_path:
        return tables, free

    items = _raw_to_items(ocr_raw)
    if not items:
        # 未提供含置信度原始结果：现场补一次 OCR（含 conf）
        try:
            from core.ocr_tool import _get_engine as _get_ocr_engine
            raw, _ = _get_ocr_engine()(image_path)
            items = _raw_to_items(raw)
        except Exception:  # noqa: BLE001
            items = []
    if not items:
        return tables, free

    out = []
    for t in tables:
        bbox = t.get("bbox")
        geo_grid = t.get("grid", [])
        if not bbox or len(geo_grid) < min_rows:
            out.append(t)
            continue
        rt = _rebuild_table_with_rapidtable(engine, image_path, bbox, items, dpi)
        if rt is None:
            out.append(t)
        else:
            out.append(rt)
    return out, free
