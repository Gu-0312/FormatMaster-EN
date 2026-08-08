# -*- coding: utf-8 -*-
"""生成《测试数据采集模板.xlsx》：3 张数据表 + 指标口径说明。
统一字段口径，便于后续做质量趋势、缺陷根因、发布就绪分析。
"""
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "测试数据采集模板.xlsx")

HEAD_FILL = PatternFill("solid", fgColor="2F5597")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=11)
EXAMPLE_FONT = Font(color="808080", italic=True)
WRAP = Alignment(wrap_text=True, vertical="top")

SHEETS = {
    "用例执行记录": [
        "日期", "版本号", "测试阶段", "模块", "测试类型", "用例ID", "用例名称",
        "执行人", "结果", "失败原因分类", "关联缺陷ID", "执行耗时(分钟)",
        "用例优先级", "自动化(是/否)", "备注",
    ],
    "缺陷记录": [
        "缺陷ID", "创建日期", "版本号", "发现阶段", "模块", "严重度", "优先级",
        "缺陷类型", "状态", "发现人", "指派给", "关闭日期", "修复耗时(天)",
        "引入版本", "根因", "是否线上逃逸(是/否)", "备注",
    ],
    "版本汇总": [
        "版本号", "发布日期", "总用例数", "执行用例数", "通过数", "失败数",
        "阻塞数", "跳过数", "新增缺陷数", "关闭缺陷数", "未关闭缺陷数",
        "自动化用例数", "自动化通过数", "回归覆盖模块", "测试人天", "备注",
    ],
}

EXAMPLES = {
    "用例执行记录": [
        ["2026-07-01", "v2.3.0", "系统测试", "视频转换", "功能测试", "TC-1001",
         "MP4转AVI正常路径", "张三", "通过", "", "", "3", "P1", "是", ""],
        ["2026-07-01", "v2.3.0", "系统测试", "PDF工具", "功能测试", "TC-1002",
         "PDF合并后页序", "李四", "失败", "逻辑错误", "BUG-1088", "5", "P1", "是", "示例"],
    ],
    "缺陷记录": [
        ["BUG-1088", "2026-07-01", "v2.3.0", "系统测试", "PDF工具", "严重", "高",
         "功能缺陷", "已修复", "李四", "王五", "2026-07-03", "2", "v2.2.0",
         "编码错误", "否", ""],
    ],
    "版本汇总": [
        ["v2.3.0", "2026-07-10", "800", "760", "715", "28", "9", "8", "42",
         "35", "18", "420", "398", "视频/PDF/图片", "12", ""],
    ],
}

DV_RULES = {
    "用例执行记录": {9: "通过,失败,阻塞,跳过"},   # 结果
    "缺陷记录": {
        5: "致命,严重,一般,轻微",              # 严重度
        6: "紧急,高,中,低",                    # 优先级
        7: "功能缺陷,性能缺陷,界面缺陷,兼容性缺陷,文档缺陷,安全缺陷,其他",  # 缺陷类型
        8: "新建,处理中,已修复,已验证,关闭,重开",  # 状态
        14: "需求变更,设计缺陷,编码错误,测试漏测,环境问题,数据问题,其他",  # 根因
        15: "是,否",
    },
}


def build():
    wb = Workbook()
    wb.remove(wb.active)
    for sheet, headers in SHEETS.items():
        ws = wb.create_sheet(sheet)
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(1, c)
            cell.fill = HEAD_FILL
            cell.font = HEAD_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for row in EXAMPLES.get(sheet, []):
            ws.append(row)
            for c in range(1, len(headers) + 1):
                ws.cell(ws.max_row, c).font = EXAMPLE_FONT
        # 列宽
        for c in range(1, len(headers) + 1):
            col = get_column_letter(c)
            ws.column_dimensions[col].width = max(10, min(22, len(str(headers[c - 1])) * 2 + 6))
        ws.freeze_panes = "A2"
        # 数据验证（下拉）
        for col_idx, opts in DV_RULES.get(sheet, {}).items():
            col = get_column_letter(col_idx)
            dv = DataValidation(type="list", formula1='"' + opts + '"', allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{col}2:{col}500")
    # 指标口径说明
    ws = wb.create_sheet("指标口径说明")
    ws.append(["指标", "计算公式", "建议目标", "说明"])
    rows = [
        ["用例通过率", "通过数 / 执行用例数 × 100%", "≥ 98%（回归基线）", "执行数=通过+失败+阻塞，不含跳过"],
        ["用例执行率", "执行用例数 / 总用例数 × 100%", "≥ 95%", "反映测试覆盖是否充分"],
        ["缺陷逃逸率", "线上(生产)缺陷数 / (测试期缺陷数 + 线上缺陷数) × 100%", "≤ 5%", "衡量测试拦截能力，越低越好"],
        ["缺陷密度", "缺陷数 / 千行代码(KLOC) 或 / 功能点", "按模块对标基线", "评估模块复杂度与质量风险"],
        ["缺陷收敛趋势", "每轮测试新增缺陷数", "新增趋势单调下降→可发布", "核心发布门禁：收敛曲线"],
        ["未关闭缺陷存量", "开放缺陷数随时间", "发布前≤N 且无致命/严重", "技术债与发布风险"],
        ["用例有效率", "发现过缺陷的用例 / 总用例 × 100%", "5%~20%", "过低说明用例价值低，过高说明前期质量差"],
        ["平均修复时长(MTTR)", "Σ修复耗时 / 关闭缺陷数", "按严重度分层对标", "反映缺陷处理效率"],
        ["自动化覆盖率", "自动化用例数 / 总用例数 × 100%", "≥ 60%（稳定模块）", "提升回归效率的前提"],
        ["回归失败率", "回归轮失败用例 / 回归用例 × 100%", "≤ 1%", "防止改一处坏一片"],
    ]
    for r in rows:
        ws.append(r)
        for c in range(1, 5):
            ws.cell(ws.max_row, c).alignment = WRAP
    for c, w in zip(range(1, 5), [18, 46, 24, 46]):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A2"
    wb.save(OUT)
    print("已生成:", OUT)


if __name__ == "__main__":
    build()
