# 局域网网页预览 + 视频转GIF二维码 设计文档

## 概述

两个增强功能：
1. **局域网网页预览** — 手机扫描二维码后，网页显示文件列表，支持图片/视频/PDF/Office文档在线预览
2. **视频转GIF+二维码** — GIF面板底部新增「扫码下载」区域，GIF生成后自动显示二维码+链接

## 功能一：局域网网页预览

### 需求
- 现有局域网传输功能升级为网页端预览
- 手机扫描二维码后，网页显示文件列表
- 支持图片/视频/PDF/Office文档在线预览
- 使用内嵌HTTP服务器实现

### 技术方案

修改 `core/lan_transfer.py`：

#### 1. 扩展预览格式支持

在 `_CLASSIFY_GROUPS` 中添加预览支持的格式：
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

#### 2. 修改HTML模板

在JavaScript中添加格式检测函数：
```javascript
function isImg(n){return /\.(jpe?g|png|gif|webp|bmp|svg|heic|heif)$/i.test(n)}
function isVid(n){return /\.(mp4|webm|ogg)$/i.test(n)}
function isPdf(n){return /\.pdf$/i.test(n)}
function isDoc(n){return /\.(doc|docx|xls|xlsx|ppt|pptx)$/i.test(n)}
```

修改预览函数：
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
    // Office文档：使用Google Docs Viewer或微软Office Online预览
    var viewer='https://view.officeapps.live.com/op/embed.aspx?src='+encodeURIComponent(full);
    box.innerHTML='<iframe src="'+viewer+'" style="width:100%;height:80vh;border:none;"></iframe>';
  }
  
  document.getElementById('lb').style.display='flex';
}
```

#### 3. 修改文件行生成逻辑

在 `_SendHandler.do_GET` 方法中，为预览格式添加预览按钮：
```python
is_preview = (not e.is_dir()) and ext in _PREVIEW_EXTS
pv = (f"<button class='pv' onclick=\"preview(this.closest('.row'))\">👁</button>"
      if is_preview else "")
```

#### 4. 文件图标增强

根据文件类型显示不同图标：
```python
def _get_file_icon(ext):
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

### 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `core/lan_transfer.py` | 1. 添加 `_PREVIEW_EXTS` 常量<br>2. 添加 `_get_file_icon()` 函数<br>3. 修改HTML模板的JavaScript<br>4. 修改文件行生成逻辑 |

## 功能二：视频转GIF+二维码

### 需求
- GIF面板底部新增「扫码下载」区域
- GIF生成后自动显示二维码+链接
- 手机扫码直接下载GIF文件

### 技术方案

修改 `gui_qt/panels/gif_panel.py`：

#### 1. 添加UI组件

在GIF面板底部新增「扫码下载」区域：
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

#### 2. 启动临时HTTP服务器

GIF生成后启动临时HTTP服务器：
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

#### 3. 生成二维码

GIF生成后自动生成二维码：
```python
def _show_qr_code(self, url):
    """显示二维码"""
    try:
        import qrcode
        from PySide6.QtGui import QImage, QPixmap
        
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

#### 4. 在任务完成后调用

修改 `_runner` 方法，在GIF生成成功后调用：
```python
def _runner(self, task, prog):
    # ... 现有代码 ...
    
    # GIF生成成功后显示二维码
    if proc.returncode == 0:
        url, server = self._start_qr_server(task.output_path)
        if url:
            self._show_qr_code(url)
    
    return proc.returncode == 0
```

### 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `gui_qt/panels/gif_panel.py` | 1. 添加UI组件（qr_area, qr_label, qr_link）<br>2. 添加 `_start_qr_server()` 方法<br>3. 添加 `_show_qr_code()` 方法<br>4. 修改 `_runner()` 方法 |

## 测试方案

### 功能一测试
1. 启动局域网传输服务
2. 手机扫描二维码
3. 验证网页显示文件列表
4. 点击图片文件，验证预览功能
5. 点击视频文件，验证播放功能
6. 点击PDF文件，验证预览功能
7. 点击Office文档，验证预览功能

### 功能二测试
1. 在GIF面板添加视频文件
2. 点击「开始转换」
3. 验证GIF生成成功
4. 验证二维码显示
5. 手机扫描二维码
6. 验证GIF文件下载成功

## 依赖

- `qrcode[pil]` — 二维码生成（已存在）
- `Pillow` — 图片处理（已存在）
- 无需新增依赖

## 风险

1. **Office文档预览** — 使用微软Office Online预览需要网络连接，离线环境可能失败
2. **端口占用** — 临时HTTP服务器可能端口被占用
3. **防火墙** — 手机可能无法访问临时服务器

## 后续优化

1. 支持更多Office格式预览
2. 添加预览历史记录
3. 支持批量GIF生成+二维码
4. 添加密码保护功能
