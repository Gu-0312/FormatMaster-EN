"""table_recognizer — 表格识别（OCR 文字 + 位置聚类 → 结构化表格）。

基于 RapidOCR 的带坐标识别结果，按 y 中心聚类成行、按 x 排序成列，
输出 CSV 或 XLSX。不引入表格结构模型，适合规则/无复杂合并的表格。
"""
import os

from core.ocr_tool import _get_engine

XLSX_EXTS = {".xlsx", ".xls"}
CSV_EXTS = {".csv", ".txt"}


def _items(result):
    """把 rapidocr result 转为 (cy, cx, height, text) 列表并排序。"""
    out = []
    for bbox, text, _conf in result:
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        cy = sum(ys) / len(ys)
        cx = sum(xs) / len(xs)
        h = max(ys) - min(ys)
        out.append((cy, cx, max(h, 1.0), text))
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def recognize_rows(input_path, progress_cb=None):
    """识别图片 → 行列表 [[cell, cell, ...], ...]。"""
    if progress_cb:
        progress_cb(30, "打开图片…")
    engine = _get_engine()
    if progress_cb:
        progress_cb(50, "识别文字与位置…")
    result, _elapse = engine(input_path)
    if not result:
        return []
    items = _items(result)
    heights = sorted(t[2] for t in items)
    med_h = heights[len(heights) // 2] if heights else 20.0

    rows = []
    cur = []
    last_cy = None
    for cy, cx, h, text in items:
        if last_cy is not None and cy - last_cy > med_h * 0.7:
            rows.append(sorted(cur, key=lambda t: t[0]))
            cur = []
        cur.append((cx, text))
        last_cy = cy if last_cy is None else max(last_cy, cy)
    if cur:
        rows.append(sorted(cur, key=lambda t: t[0]))
    return [[t for _cx, t in row] for row in rows]


def table_to_csv(input_path, output_path, progress_cb=None):
    """识别表格并保存为 CSV（UTF-8-sig，Excel 可直接打开）。"""
    import csv
    rows = recognize_rows(input_path, progress_cb)
    if not rows:
        if progress_cb:
            progress_cb(-1, "未识别到文字")
        return False
    if progress_cb:
        progress_cb(80, "写入 CSV…")
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    if progress_cb:
        progress_cb(100, "识别完成")
    return True


def table_to_xlsx(input_path, output_path, progress_cb=None, chart_type=None):
    """识别表格并保存为 XLSX。

    chart_type: None 不生成图表 / "bar" 柱状 / "line" 折线 / "pie" 饼图。
    图表取首行为表头、首列为分类、其余列为数值（需 ≥2 行 ≥2 列）。
    """
    from openpyxl import Workbook
    rows = recognize_rows(input_path, progress_cb)
    if not rows:
        if progress_cb:
            progress_cb(-1, "未识别到文字")
        return False
    if progress_cb:
        progress_cb(80, "写入 Excel…")
    wb = Workbook()
    ws = wb.active
    ws.title = "表格"
    for row in rows:
        ws.append(row)
    if chart_type:
        try:
            from openpyxl.chart import BarChart, LineChart, PieChart
            from openpyxl.chart.reference import Reference
            ncols = max(len(r) for r in rows)
            if len(rows) >= 2 and ncols >= 2:
                cls = {"bar": BarChart, "line": LineChart,
                       "pie": PieChart}[chart_type]
                chart = cls()
                data = Reference(ws, min_col=2, min_row=1,
                                 max_col=ncols, max_row=len(rows))
                cats = Reference(ws, min_col=1, min_row=2,
                                 max_row=len(rows))
                chart.add_data(data, titles_from_data=True)
                chart.set_categories(cats)
                chart.title = "数据图表"
                ws.add_chart(chart, f"H{len(rows) + 3}")
            elif progress_cb:
                progress_cb(90, "数据不足，跳过图表")
        except Exception:  # noqa: BLE001 - 图表失败不影响表格数据
            pass
    wb.save(output_path)
    if progress_cb:
        progress_cb(100, "识别完成")
    return True


def recognize_table(input_path, output_path, progress_cb=None, chart_type=None):
    """按输出扩展名自动选择 CSV / XLSX。"""
    ext = os.path.splitext(output_path)[1].lower()
    if ext in XLSX_EXTS:
        return table_to_xlsx(input_path, output_path, progress_cb, chart_type)
    return table_to_csv(input_path, output_path, progress_cb)
