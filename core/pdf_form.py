"""pdf_form — PDF 表单读取与填写。

使用 PyMuPDF (fitz) 读取 PDF 中的表单字段（text / checkbox / combo / list），
并支持填写/导出。无表单的 PDF 返回空列表。
"""
import os
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


def is_available():
    """检查 PyMuPDF 是否可用。"""
    return fitz is not None


def get_form_fields(pdf_path):
    """读取 PDF 表单字段。

    Returns:
        list[dict]: 每个字段包含:
            - name: 字段名
            - type: 字段类型 (text / checkbox / combo / list / radio / signature / unknown)
            - value: 当前值
            - options: 下拉/列表选项（仅 combo/list/radio）
            - page: 所在页码（0-indexed）
            - rect: 字段位置 (x0, y0, x1, y1)
    """
    if not fitz:
        return []
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return []

    fields = []
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            widgets = page.widgets()
            if widgets:
                for w in widgets:
                    ft = w.field_type
                    field = {
                        "name": w.field_name or f"field_{page_num}_{len(fields)}",
                        "type": _type_name(ft),
                        "value": w.field_value or "",
                        "options": list(w.choice_values) if w.choice_values else [],
                        "page": page_num,
                        "rect": tuple(w.rect),
                    }
                    fields.append(field)
    finally:
        doc.close()
    return fields


def fill_form(pdf_path, output_path, field_values):
    """填写 PDF 表单并保存。

    Args:
        pdf_path: 源 PDF 路径
        output_path: 输出 PDF 路径
        field_values: dict { field_name: new_value }

    Returns:
        (success: bool, message: str)
    """
    if not fitz:
        return False, "PyMuPDF 未安装"
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return False, f"无法打开 PDF: {e}"

    try:
        filled = 0
        for page in doc:
            widgets = page.widgets()
            if widgets:
                for w in widgets:
                    name = w.field_name
                    if name in field_values:
                        new_val = field_values[name]
                        # checkbox: "Yes" / "Off"
                        if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                            w.field_value = "Yes" if new_val else "Off"
                        else:
                            w.field_value = str(new_val)
                        w.update()
                        filled += 1

        if filled == 0:
            doc.close()
            return False, "未找到可填写的表单字段"

        # 保存：incremental=True 尽量保留原有格式
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        try:
            doc.save(output_path, incremental=False, deflate=True)
        except Exception:
            doc.save(output_path)
        doc.close()
        return True, f"已填写 {filled} 个字段"
    except Exception as e:
        doc.close()
        return False, f"填写失败: {e}"


def flatten_form(pdf_path, output_path):
    """将表单扁平化（不可编辑的纯文本）。"""
    if not fitz:
        return False, "PyMuPDF 未安装"
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            page._clean_contents()
        doc.save(output_path)
        doc.close()
        return True, "已扁平化"
    except Exception as e:
        return False, f"扁平化失败: {e}"


def _type_name(ft):
    """将 PyMuPDF 字段类型码转为可读名称。"""
    if not fitz:
        return "unknown"
    _map = {
        fitz.PDF_WIDGET_TYPE_TEXT: "text",
        fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
        fitz.PDF_WIDGET_TYPE_COMBOBOX: "combo",
        fitz.PDF_WIDGET_TYPE_LISTBOX: "list",
        fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
        fitz.PDF_WIDGET_TYPE_SIGNATURE: "signature",
    }
    return _map.get(ft, "unknown")
