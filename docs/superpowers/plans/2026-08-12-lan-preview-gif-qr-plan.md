# 局域网网页预览 + 视频转GIF二维码 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强局域网传输功能支持网页预览，并为GIF转换添加二维码下载功能

**Architecture:** 修改 `core/lan_transfer.py` 添加预览支持，修改 `gui_qt/panels/gif_panel.py` 添加二维码功能

**Tech Stack:** Python, PySide6, HTTP服务器, qrcode库

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `core/lan_transfer.py` | 修改：添加预览格式支持、文件图标、HTML模板 |
| `gui_qt/panels/gif_panel.py` | 修改：添加二维码UI和HTTP服务器 |

---

### Task 1: 添加预览格式支持

**Files:**
- Modify: `core/lan_transfer.py:998-1047`

- [ ] **Step 1: 添加预览格式常量**

在 `_CLASSIFY_GROUPS` 定义后添加：

```python
_PREVIEW_EXTS = {
    # 图片（已有）
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "heic", "heif",
    # 视频（已有）
    "mp4", "webm", "ogg",
    # PDF
    "pdf",
    # Office文档（需要转换）
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
}
```

- [ ] **Step 2: 添加文件图标函数**

在 `_human_size` 函数后添加：

```python
def _get_file_icon(ext):
    """根据文件扩展名返回图标。"""
    if ext in _CLASSIFY_GROUPS["图片"]:
        return "🖼️"
    elif ext in _CLASSIFY_GROUPS["视频"]:
        return "🎬"
    elif ext in _CLASSIFY_GROUPS["音频"]:
        return "🎵"
    elif ext in _CLASSIFY_GROUPS["文档"]:
        if ext == "pdf":
            return "📕"
        elif ext in {"doc", "docx"}:
            return "📘"
        elif ext in {"xls", "xlsx"}:
            return "📗"
        elif ext in {"ppt", "pptx"}:
            return "📙"
        else:
            return "📄"
    else:
        return "📄"
```

- [ ] **Step 3: 修改文件行生成逻辑**

在 `_SendHandler.do_GET` 方法中，修改文件行生成部分（约254-276行）：

```python
# 原代码
icon = "📁" if e.is_dir() else "📄"

# 修改为
ext = os.path.splitext(e.name)[1].lower().lstrip(".")
icon = "📁" if e.is_dir() else _get_file_icon(ext)
```

并修改预览按钮逻辑：

```python
# 原代码
is_media = (not e.is_dir()) and ext in _MEDIA_EXTS
pv = (f"<button class='pv' onclick=\"preview(this.closest('.row'))\">👁</button>"
      if is_media else "")

# 修改为
is_preview = (not e.is_dir()) and ext in _PREVIEW_EXTS
pv = (f"<button class='pv' onclick=\"preview(this.closest('.row'))\">👁</button>"
      if is_preview else "")
```

- [ ] **Step 4: 验证修改**

运行以下命令检查语法：

```bash
python -c "import core.lan_transfer; print('OK')"
```

预期输出：`OK`

---

### Task 2: 修改HTML模板JavaScript

**Files:**
- Modify: `core/lan_transfer.py:429-447`

- [ ] **Step 1: 修改格式检测函数**

找到JavaScript中的 `isImg` 和 `isVid` 函数，修改为：

```javascript
function isImg(n){return /\.(jpe?g|png|gif|webp|bmp|svg|heic|heif)$/i.test(n)}
function isVid(n){return /\.(mp4|webm|ogg)$/i.test(n)}
function isPdf(n){return /\.pdf$/i.test(n)}
function isDoc(n){return /\.(doc|docx|xls|xlsx|ppt|pptx)$/i.test(n)}
```

- [ ] **Step 2: 修改预览函数**

找到 `preview` 函数，修改为：

```javascript
function preview(row){
  var nm=row.querySelector('.nm'),full=new URL(nm.getAttribute('href'),location.href).href;
  var box=document.getElementById('lbBox');
  var fn=row.dataset.fn;
  
  if(isImg(fn)){
    box.innerHTML='<img src="'+full+'">';
  } else if(isVid(fn)){
    box.innerHTML='<video src="'+full+'" controls autoplay playsinline></video>';
  } else if(isPdf(fn)){
    box.innerHTML='<iframe src="'+full+'" style="width:100%;height:80vh;border:none;"></iframe>';
  } else if(isDoc(fn)){
    var viewer='https://view.officeapps.live.com/op/embed.aspx?src='+encodeURIComponent(full);
    box.innerHTML='<iframe src="'+viewer+'" style="width:100%;height:80vh;border:none;"></iframe>';
  }
  
  document.getElementById('lb').style.display='flex';
}
```

- [ ] **Step 3: 修改onNm函数**

找到 `onNm` 函数，修改为：

```javascript
function onNm(a){
  var row=a.closest('.row');
  if(row.dataset.dir==='1')return true;
  var fn=row.dataset.fn;
  if(isImg(fn)||isVid(fn)||isPdf(fn)||isDoc(fn)){preview(row);return false}
  fetchDL(a.getAttribute('href'),fn);
  return false;
}
```

- [ ] **Step 4: 验证修改**

运行以下命令检查语法：

```bash
python -c "import core.lan_transfer; print('OK')"
```

预期输出：`OK`

---

### Task 3: 添加GIF面板二维码UI

**Files:**
- Modify: `gui_qt/panels/gif_panel.py:74-77`

- [ ] **Step 1: 添加导入**

在文件开头添加导入：

```python
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel
```

- [ ] **Step 2: 添加二维码UI组件**

在 `build` 方法中，在 `self.action_bar = ActionBar(...)` 之后添加：

```python
# 扫码下载区域（GIF生成后显示）
self.qr_area = QWidget()
qr_layout = QVBoxLayout(self.qr_area)
qr_layout.setContentsMargins(0, 12, 0, 0)
qr_layout.setSpacing(8)

# 标题
self.qr_title = CaptionLabel(tr("扫码下载", "Scan to download"))
self.qr_title.setStyleSheet("font-size: 14px; font-weight: 600;")
qr_layout.addWidget(self.qr_title)

# 二维码图片
self.qr_label = QLabel()
self.qr_label.setAlignment(Qt.AlignCenter)
self.qr_label.setFixedSize(180, 180)
qr_layout.addWidget(self.qr_label, 0, Qt.AlignCenter)

# 下载链接
self.qr_link = CaptionLabel("")
self.qr_link.setTextInteractionFlags(Qt.TextSelectableByMouse)
self.qr_link.setStyleSheet("font-size: 12px; color: #64748B;")
qr_layout.addWidget(self.qr_link)

self.qr_area.hide()  # 默认隐藏
lay.addWidget(self.qr_area)
```

- [ ] **Step 3: 验证修改**

运行以下命令检查语法：

```bash
python -c "import gui_qt.panels.gif_panel; print('OK')"
```

预期输出：`OK`

---

### Task 4: 添加GIF面板HTTP服务器

**Files:**
- Modify: `gui_qt/panels/gif_panel.py:115-169`

- [ ] **Step 1: 添加启动HTTP服务器方法**

在 `_cancel_proc` 方法后添加：

```python
def _start_qr_server(self, gif_path):
    """启动临时HTTP服务器供手机下载GIF"""
    import http.server
    import threading
    import socket
    
    # 获取本机IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    
    # 随机端口
    port = 8888
    
    # 创建HTTP服务器
    handler = lambda *args: http.server.SimpleHTTPRequestHandler(
        *args, directory=os.path.dirname(gif_path))
    
    try:
        server = http.server.HTTPServer(("0.0.0.0", port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        
        # 生成下载链接
        filename = os.path.basename(gif_path)
        url = f"http://{ip}:{port}/{filename}"
        
        return url, server
    except Exception as e:
        print(f"Failed to start QR server: {e}")
        return None, None
```

- [ ] **Step 2: 添加显示二维码方法**

在 `_start_qr_server` 方法后添加：

```python
def _show_qr_code(self, url):
    """显示二维码"""
    try:
        import qrcode
        
        # 生成二维码
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # 转换为QPixmap
        img = img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg)
        
        # 显示
        self.qr_label.setPixmap(pixmap.scaled(
            180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.qr_link.setText(url)
        self.qr_area.show()
        
    except Exception as e:
        print(f"Failed to generate QR code: {e}")
```

- [ ] **Step 3: 验证修改**

运行以下命令检查语法：

```bash
python -c "import gui_qt.panels.gif_panel; print('OK')"
```

预期输出：`OK`

---

### Task 5: 修改GIF转换完成逻辑

**Files:**
- Modify: `gui_qt/panels/gif_panel.py:116-169`

- [ ] **Step 1: 修改_runner方法**

找到 `_runner` 方法，在 `return proc.returncode == 0` 之前添加：

```python
# GIF生成成功后显示二维码
if proc.returncode == 0:
    url, server = self._start_qr_server(task.output_path)
    if url:
        self._show_qr_code(url)
```

- [ ] **Step 2: 验证修改**

运行以下命令检查语法：

```bash
python -c "import gui_qt.panels.gif_panel; print('OK')"
```

预期输出：`OK`

---

### Task 6: 测试功能

**Files:**
- Test: `core/lan_transfer.py`
- Test: `gui_qt/panels/gif_panel.py`

- [ ] **Step 1: 测试局域网预览功能**

1. 启动局域网传输服务
2. 手机扫描二维码
3. 验证网页显示文件列表
4. 点击图片文件，验证预览功能
5. 点击视频文件，验证播放功能
6. 点击PDF文件，验证预览功能
7. 点击Office文档，验证预览功能

- [ ] **Step 2: 测试GIF二维码功能**

1. 在GIF面板添加视频文件
2. 点击「开始转换」
3. 验证GIF生成成功
4. 验证二维码显示
5. 手机扫描二维码
6. 验证GIF文件下载成功

- [ ] **Step 3: 提交代码**

```bash
git add core/lan_transfer.py gui_qt/panels/gif_panel.py
git commit -m "feat: add web preview and GIF QR code download"
```

---

## 完成

实施计划完成。两个功能已分解为6个任务，每个任务包含具体的代码修改和验证步骤。

**执行选项：**

1. **Subagent-Driven (recommended)** - 我将为每个任务分派一个新鲜的子代理，任务之间进行审查，快速迭代

2. **Inline Execution** - 在当前会话中使用 executing-plans 执行任务，批量执行并设置检查点

选择哪种方式？