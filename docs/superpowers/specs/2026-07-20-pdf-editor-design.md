# PDF 编辑器 — 设计文档

## 1. 概述

在格式大师现有 PDF 工具（合并/拆分/加密/解密/压缩/旋转/删除/提取）基础上，增加一个**可视化 PDF 编辑器**模式，提供基于缩略图预览的页面级编辑能力。

## 2. 架构

### 2.1 新增文件

| 文件 | 职责 | 依赖 |
|---|---|---|
| `core/pdf_editor.py` | PDF 引擎：打开/保存/缩略图/页面 CRUD/水印/元数据 | PyMuPDF (fitz), Pillow |
| `gui/pdf_editor_panel.py` | 编辑器 UI 面板：Canvas 缩略图网格/工具栏/交互 | tkinter, core.pdf_editor |

### 2.2 修改文件

| 文件 | 改动 |
|---|---|
| `main.py` | 在 `_p_pdf()` 面板中新增"编辑器"模式分支，引用 `PdfEditorPanel` |
| `core/tools.py` | 无改动（复用现有加密/解密检测） |
| `core/pdf_page_ops.py` | 无改动（与编辑器共存，编辑器提供更完整的替代） |

### 2.3 核心类设计

```python
class PdfEditor:
    """PDF 编辑器核心引擎，封装 PyMuPDF 操作"""

    def __init__(self): ...

    # 生命周期
    def open(self, path: str) -> bool          # 加载 PDF（加密文件需先解密）
    def save(self, path: str) -> bool           # 保存到新路径
    def close(self)                             # 关闭释放资源

    # 信息
    @property
    def page_count(self) -> int
    @property
    def metadata(self) -> dict                  # {title, author, subject, keywords}

    # 缩略图
    def get_thumbnail(self, page_num: int, max_size: tuple = (150, 200)) -> ImageTk.PhotoImage

    # 页面操作（支持撤销栈：每次操作记录旧顺序）
    def reorder_pages(self, new_order: list[int])      # 拖拽排序
    def delete_pages(self, indices: list[int])         # 删除页面
    def insert_pdf(self, at_index: int, pdf_path: str) # 插入外部 PDF
    def insert_image(self, at_index: int, img_path: str) # 插入图片为新页
    def rotate_pages(self, indices: list[int], angle: int) # 旋转
    def duplicate_pages(self, indices: list[int], at_index: int) # 复制
    def insert_blank(self, at_index: int, width=595, height=842) # 空白页

    # 增强操作
    def add_watermark(self, text: str, position: str, opacity: float, rotation: int)
    def add_page_numbers(self, start: int, position: str, fmt: str)
    def set_metadata(self, meta: dict)
    def crop_pages(self, indices: list[int], margin: tuple)

    # 撤销
    def undo(self) -> bool
```

## 3. UI 设计

### 3.1 面板布局

在现有 PDF 面板中，模式选择器 `self.pdf_mode` 新增选项 **"编辑器（可视化）"**。选择后面板切换为编辑器布局：

```
┌──────────────────────────────────────────────────────┐
│ [📂打开] [💾保存] [📝另存为]  | 模式: [编辑器 ▼]    │
├──────────────────────────────────────────────────────┤
│ 工具栏 (tk.Frame)                                    │
│ [↻旋转] [✕删除] [➕插入] [📄复制] [🔤水印]          │
│ [#编号] [📋元数据] [↩撤销] [☐全选]                  │
├──────────────────────────────────────────────────────┤
│ 缩略图画布 (tk.Canvas + Scrollbar)                   │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                    │
│  │  p1 │ │  p2 │ │  p3 │ │  p4 │                    │
│  │ ─── │ │ ─── │ │ ─── │ │ ─── │                    │
│  │     │ │     │ │     │ │     │                    │
│  └─────┘ └─────┘ └─────┘ └─────┘                    │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                    │
│  │  p5 │ │  p6 │ │  p7 │ │  p8 │                    │
│  └─────┘ └─────┘ └─────┘ └─────┘                    │
│ ◄──────────────────────────────► (水平滚动)          │
├──────────────────────────────────────────────────────┤
│ 状态栏: 共 12 页 | 选中 3 页 | 未保存的修改          │
└──────────────────────────────────────────────────────┘
```

### 3.2 缩略图交互

| 交互 | 行为 |
|---|---|
| 单击 | 选中/取消选中单页 (高亮边框) |
| Ctrl+单击 | 切换单页选中状态 |
| Shift+单击 | 范围选中 |
| 拖拽 | 拖动选中页面到新位置（半透明 ghost 反馈） |
| 双击 | 打开页面预览大图（新窗口） |
| 右键菜单 | 删除/复制/旋转/提取 |

### 3.3 缩略图渲染策略

- 目标显示尺寸：约 150×200px（可配置 小/中/大")
- 使用 `fitz.Page.get_pixmap(matrix=Matrix(factor))` 渲染
- 结果 → `PIL.Image` → `ImageTk.PhotoImage` → Canvas
- **懒加载**：只在进入可视区域时渲染
- **缓存**：`dict[int, PhotoImage]`，上限 200 张，超出淘汰最早条目
- **异步**：渲染在后台线程执行，完成后回调 UI 更新

## 4. 与现有 PDF 面板的集成

现有 `_p_pdf()` 面板（main.py ~3012 行）的模式选择器增加一个选项：

```python
self.pdf_mode = ttk.Combobox(
    values=["合并（多个→一个）", "拆分（一个→多个）",
            "加密（设置密码）", "解密（移除密码）",
            "压缩", "编辑器（可视化）"],
    ...
)
```

当选择"编辑器"模式时：
1. 隐藏现有控件（文件选择 + 模式参数区）
2. 显示编辑器面板（`PdfEditorPanel`）
3. 其他参数区保持不变

切换回非编辑器模式时：
1. 如果编辑器有未保存修改，提示保存
2. 隐藏编辑器面板，恢复原有控件

## 5. 数据流

```mermaid
flowchart TD
    A[用户打开PDF] --> B[PdfEditor.open(path)]
    B --> C[渲染缩略图]
    C --> D[Canvas 展示]
    D --> E[用户交互 拖拽/点击/按钮]
    E --> F{PdfEditor 操作}
    F --> G[reorder_pages / delete_pages / etc.]
    G --> H[更新内部页面列表]
    H --> I[撤销栈记录]
    I --> J[重新渲染受影响的缩略图]
    J --> D
    G --> K[保存/另存为]
    K --> L[doc.save(path)]
```

## 6. 撤销机制

- 使用简单栈：每次页面变更操作前，将当前页面顺序快照 (`list[int]`) 和操作描述入栈
- 撤销时：从栈顶恢复上一快照，清空缩略图缓存，重新渲染当前可视区域
- 栈深度：20 层（避免内存膨胀）

## 7. 错误处理

| 场景 | 处理 |
|---|---|
| 加密 PDF | 提示用户先解密再编辑（复用 `pdf_is_encrypted`） |
| 文件损坏 | 显示 "PDF 文件已损坏，无法打开" |
| 大文件 > 200 页 | 提示 "该文件页数较多，缩略图加载可能较慢" |
| 保存失败 | 显示具体失败原因（磁盘满/权限等） |
| 图片插入格式不支持 | 提示支持的图片格式 (JPG/PNG/BMP/TIFF/WEBP) |

## 8. 依赖

| 依赖 | 用途 | 状态 |
|---|---|---|
| PyMuPDF (fitz) | 核心 PDF 操作 | ✅ 已有 |
| Pillow | 缩略图后处理、水印合成 | ✅ 已有 |
| tkinter Canvas | 缩略图网格展示 | ✅ 内置 |

无需新增 Python 依赖。

## 9. 实现阶段

### Phase 1 — 基础引擎 + 面板集成（当前 sprint）
- `core/pdf_editor.py`：打开/保存/关闭/缩略图/页面 CRUD（增删改排旋转复制）
- 面板 UI 集成：模式选择 + 工具栏 + 缩略图 Canvas + 状态栏
- 懒加载缩略图 + 缓存
- 异步缩略图生成

### Phase 2 — 交互完善（下一 sprint）
- 拖拽排序
- 批量选择 (Ctrl/Shift 多选)
- 右键菜单
- 撤销/重做

### Phase 3 — 增强功能（后续）
- 文本水印
- 页码编号
- 元数据编辑
- 裁剪页面
- 空白页插入
- 缩放控制

## 10. 约束与假设

- 假设 PDF 文件在编辑器打开期间不被外部修改
- 编辑器每次只处理一个 PDF 文件（不支持多标签页）
- 加密 PDF 必须先解密才能载入编辑器
- 缩略图缓存上限 200 张，超过时淘汰最早生成的
- 撤销栈上限 20 层
