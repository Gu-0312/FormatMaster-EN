<div align="center">

# 🔄 FormatMaster / 格式大师

**All-in-one format converter for video, audio, image & documents.**
**全能格式转换工具 — 视频、音频、图片、文档一站式转换**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Release](https://img.shields.io/badge/Release-v1.3.1-orange.svg)]()

---

[English](#english) · [中文](#中文)

</div>

---

## English

### ✨ Features Overview

| Module | Description |
|--------|-------------|
| 🎬 Video Convert | MP4, AVI, MKV, WMV, MOV, FLV, WEBM, TS, MPEG, 3GP |
| 🎵 Audio Convert | MP3, WAV, WMA, AAC, FLAC, OGG, M4A, AMR, OPUS |
| 🖼 Image Convert | JPG, PNG, BMP, GIF, TIFF, WEBP, ICO, TGA |
| 📄 Document Convert | PDF ↔ Word ↔ Excel ↔ PPT ↔ WPS ↔ TXT ↔ HTML ↔ Image (168+ combinations) |
| ↓ Extract Audio | Extract audio track from video files |
| 📦 Video Compress | High / Medium / Low quality presets with resolution limit |
| ⊙ Video to GIF | Custom width, fps, start time, duration |
| ⊞ PDF Merge / Split | Merge multiple PDFs, split by page ranges |
| 🔒 PDF Encrypt / Decrypt | AES-256/AES-128 encryption with password history |
| 🗜 PDF Compress | Reduce PDF size with DPI and quality control |
| ⊡ Image Compress | Quality control, max resolution, save percentage display |
| ✏ Batch Rename | Templates with `{n}` serial, `{name}`, `{date}` placeholders |
| 🔊 Audio Volume | Adjust output volume (20% - 200%) |
| 🏷 Image Watermark | Add custom text watermark with 5 position choices |
| 🖼 Image Crop Presets | Social media dimension presets (1:1, 4:5, 16:9, etc.) |
| 🔍 Format Detect | Batch scan folder, auto-classify by format, content header detection |
| 📥 Video Download | Download from Bilibili, YouTube, Weibo, Instagram, etc. (via yt-dlp) |
| 📊 Status Stream | Real-time progress logs with auto-scroll and error highlighting |

---

### 🎬 Video Convert — Details

**Supported formats**: MP4, AVI, MKV, WMV, MOV, FLV, WEBM, TS, MPEG, 3GP

| Setting | Options |
|---------|---------|
| Target Format | MP4, AVI, MKV, WMV, MOV, FLV, WEBM, TS, MPEG, 3GP |
| Video Codec | Default, H.264, H.265/HEVC, VP9, MPEG4 |
| Quality Preset | Original, High (large file), Medium, Low (small file), Mobile, Web Share |
| Resolution | Original, 4K (3840×2160), 2K (2560×1440), 1080p, 720p, 480p, 360p |
| Frame Rate | Original, 24, 25, 30, 60 fps |
| Bitrate | Auto, 1M, 2M, 5M, 8M, 10M, 20M |
| Stream Copy (Lossless) | ON/OFF — remux without re-encoding (MP4/MKV/TS/FLV/MOV only) |
| Quick Presets | Custom + user-defined preset templates |
| Output Dir | Same as source / Custom directory |

**Special capabilities**:
- **Stream selection**: Choose which audio/video streams to keep
- **Codec compatibility check**: Auto-detects incompatible codec+container combos (e.g. H.265→FLV)
- **Auto-rename**: Output file automatically gets `_1` suffix if name conflicts with input

---

### 🎵 Audio Convert — Details

**Supported formats**: MP3, WAV, WMA, AAC, FLAC, OGG, M4A, AMR, OPUS

| Setting | Options |
|---------|---------|
| Target Format | MP3, WAV, WMA, AAC, FLAC, OGG, M4A, AMR, OPUS |
| Bitrate | 128k, 192k, 256k, 320k |
| Sample Rate | Original, 22050, 44100, 48000, 96000 |
| Channels | Original, Mono, Stereo |
| Volume | 20% ~ 200% (slider control) |
| Output Dir | Same as source / Custom directory |

---

### 🖼 Image Convert — Details

**Supported formats**: JPG, PNG, BMP, GIF, TIFF, WEBP, ICO, TGA

| Setting | Options |
|---------|---------|
| Target Format | JPG, PNG, BMP, GIF, TIFF, WEBP, ICO, TGA |
| Quality | 100 (lossless), 95 (high), 85 (medium), 70 (low), 50 (compressed) |
| Resize | Original, 50%, 25%, 200% |
| Rotate | 0°, 90°, 180°, 270° |
| Crop | Original ratio, Crop to square |
| Grayscale | ON/OFF — convert to black & white |
| Watermark Text | Custom input |
| Watermark Position | Bottom-right, Bottom-left, Top-right, Top-left, Center |
| Output Dir | Same as source / Custom directory |

---

### 📄 Document Convert — Details

**Supported formats**: PDF, DOCX, DOC, WPS, XLSX, XLS, ET, CSV, PPTX, PPT, DPS, TXT, HTML, HTM, MD, EPUB, RTF, ODT, JPG, JPEG, PNG, BMP, TIFF, WEBP

**168+ conversion combinations**:

| Source | Target Formats |
|--------|----------------|
| PDF | DOCX, DOC, TXT, JPG, PNG, HTML, PPTX, XLSX |
| DOCX | PDF, TXT, HTML, JPG, PNG, PPTX, MD, DOC, WPS |
| DOC | PDF, TXT, DOCX, HTML, MD |
| WPS | DOCX, PDF, TXT, HTML, MD |
| XLSX | PDF, CSV, TXT, JPG, PNG, HTML, MD, ET |
| XLS | XLSX, PDF, CSV, TXT, JPG, PNG, HTML, MD |
| CSV | XLSX, PDF, TXT, HTML, MD |
| PPTX | PDF, TXT, JPG, PNG, PPT, DPS, DOCX, HTML, MD |
| PPT | PPTX, PDF, TXT |
| TXT | PDF, XLSX, DOCX, PPTX, HTML, MD |
| HTML | PDF, DOCX, TXT, XLSX, MD |
| MD | HTML, PDF, DOCX, TXT |
| EPUB | PDF, TXT, HTML, DOCX |
| RTF | TXT, PDF, DOCX |
| ODT | PDF, DOCX, TXT |
| Images | PDF, DOCX |

**Special capabilities**:
- **Format detection**: Auto-identify source format and list convertible targets
- **Word→PDF**: Via Microsoft Word COM automation
- **PPT→PDF**: Via Microsoft PowerPoint COM automation
- **Real-time compatibility hints**: Shows if current source/target pair is supported

---

### ⊙ Video to GIF — Details

| Setting | Options |
|---------|---------|
| Width | Original, 640, 480, 320, 240 |
| Frame Rate | 10, 15, 20, 24, 30 fps |
| Start Time (sec) | 0 |
| Duration (sec) | 5, 10, 15, 30, 60, All |
| Output Dir | Same as source / Custom directory |

---

### 🔒 PDF Tools — Details

**5 operation modes**:

| Mode | Description | Parameters |
|------|-------------|------------|
| Merge (many→one) | Combine multiple PDFs | — |
| Split (one→many) | Split by page ranges | Page range: `1-3,5,7-10` |
| Encrypt | Password-protect PDF | Open password, Owner password, Method (AES-256/AES-128) |
| Decrypt | Remove password | Input password |
| Compress | Reduce PDF size | Target DPI (72/100/150/200), Image quality (60–90) |

**Additional features**:
- **Password history**: Saves last 10 passwords for reuse
- **Password show/hide toggle**: Click eye icon to reveal

---

### 📥 Video Download — Details

**Supported platforms**: Bilibili, YouTube, Weibo, Instagram, and hundreds more (via yt-dlp)

| Feature | Description |
|---------|-------------|
| URL Parsing | Auto-extract valid URL, filter non-ASCII characters |
| Format Listing | Show all available formats (resolution, size, format ID) |
| Format Selection | Choose target format from list |
| Save Directory | Default ~/Downloads, customizable |
| Douyin/TikTok Warning | Alert when platform is unsupported |
| yt-dlp Version Check | Sidebar displays version, update notification available |

---

### 🔍 Format Detect — Details

| Feature | Description |
|---------|-------------|
| Folder Scanning | Recursive traversal of all files |
| Extension Classification | Auto-sort into Video/Audio/Image/Document/PDF/Other |
| Magic Number Detection | Binary header detection (PDF, JPEG, PNG, GIF, BMP, RIFF, MKV, MP4, ID3, FLAC, OGG, OLE, ZIP, etc.) |
| Mismatch Warning | Highlights when extension doesn't match actual content |
| Selective Batch Convert | Check files then one-click batch convert |
| Select All / Deselect All | Batch selection controls |
| Re-detect | Reset and rescan |
| Auto-add to Panels | Detection results auto-distributed to respective panels |

---

### 🖼 Image Crop Presets — Details

| Setting | Options |
|---------|---------|
| Preset Sizes | Social media standards (1:1 1080×1080, 4:5, 16:9, etc.) |
| Crop Mode | Cover (crop to fill) / Fit (scale to fit) |
| Output Dir | Same as source / Custom directory |

---

### 📊 Task System

| Feature | Description |
|---------|-------------|
| Task Queue | FIFO serial processing, polls every 500ms |
| Task States | waiting → processing → success / failed |
| Progress Display | Treeview table + progress bar + status text |
| Task Clear | Clear all completed tasks |
| Cancel Conversion | Terminate current task immediately |

---

### 📝 Log System

| Feature | Description |
|---------|-------------|
| Real-time Logs | Bottom Notebook panel, max 50 lines |
| Log Levels | success (green), error (red), warning (yellow), info (blue) |
| Log Clear | Clear all log entries |
| Double-click Copy | Copy single log line to clipboard |

---

### ⚙️ User Preferences

| Feature | Description |
|---------|-------------|
| Panel Settings Save | Auto-saves all settings when switching panels |
| Panel Settings Restore | Restores last settings when returning |
| Persistent Storage | `%APPDATA%/FormatMaster/data/user_prefs.json` |

---

### 🔄 Update Check

| Feature | Description |
|---------|-------------|
| Auto-check on Launch | Background thread checks GitHub releases |
| Manual Check | Trigger from About window |
| Update Notification | Top blue banner with download link |
| Version Comparison | Semantic versioning support |

---

### 🚀 Quick Start

#### Download

Download the latest release from [Releases](https://github.com/Gu-0312/FormatMaster-EN/releases/tag/v1.3.1) page — no installation required, just double-click `格式大师.exe`.

#### Build from Source

```bash
# Clone the repository
git clone https://github.com/Gujh/FormatMaster.git
cd FormatMaster

# Install dependencies
pip install -r requirements.txt

# Run the application
python main_qt.py

# Build executable
python build.py
```

### 📡 REST API

> **已移除**：旧的 Flask REST API（`api_server.py`）已随 v1.3.x 的 PySide6 迁移删除（Flask 依赖已不在 requirements 中）。

### 🛠 Tech Stack

- **GUI**: PySide6 + qfluentwidgets (Fluent Widgets, Prism design system)
- **Video/Audio**: FFmpeg (auto-download or system PATH)
- **Image**: Pillow
- **Document**: python-docx, openpyxl, python-pptx, pypdf, pdf2docx, reportlab, PyMuPDF
- **Word → PDF**: Microsoft Word COM automation
- **PPT → PDF**: Microsoft PowerPoint COM automation
- **Video Download**: yt-dlp
- **Packaging**: PyInstaller

### 📁 Project Structure

```
FormatMaster/
├── main_qt.py           # Application entry point (PySide6 GUI)
├── build.py             # PyInstaller build script
├── requirements.txt     # Python dependencies
├── assets/
│   └── icon.ico         # Application icon
├── gui_qt/              # PySide6 + Fluent Widgets UI
│   ├── app.py           # MainWindow (FluentWindow + Mica)
│   ├── nav_registry.py  # Navigation registry (single source of truth)
│   ├── services.py      # QtServices container
│   ├── task_manager.py  # Task queue (signal-driven, FIFO)
│   ├── pages/           # Home / Tasks / History / Settings / About
│   ├── panels/          # Feature panels (video, audio, pdf, ocr, ...)
│   └── components/      # Sidebar, theme manager, design system
├── core/                # Business logic, no UI dependency
│   ├── video_converter.py   # Video conversion (FFmpeg)
│   ├── audio_converter.py   # Audio conversion (FFmpeg)
│   ├── image_converter.py   # Image conversion (Pillow)
│   ├── doc_converter.py     # Document conversion (168+ combos)
│   ├── video_downloader.py  # Video download (yt-dlp)
│   ├── pdf_editor.py        # PDF editing
│   ├── ocr_tool.py          # OCR via RapidOCR
│   └── tools.py             # PDF merge/split/encrypt/compress, image compress, batch rename
├── utils/
│   ├── config.py            # Configuration & format definitions
│   ├── ffmpeg_manager.py    # FFmpeg download & management
│   ├── hardware_accel.py    # NVENC / QSV / AMF detection
│   └── format_helpers.py    # Format helpers
└── app/
    ├── theme.py             # Theme colors
    └── exceptions.py        # EX_HINT Chinese error mapping
```

### 🖥 Technical Features

| Feature | Implementation |
|---------|---------------|
| DPI Awareness | `SetProcessDpiAwareness(2)` for high-DPI displays |
| Double Buffering | DWM API for flicker-free rendering |
| Black Border Fix | Forced redraw on window map events |
| Chinese Error Mapping | 20+ exception types → user-friendly Chinese messages |
| Window Sizing | 80% of screen, min 880×620 |
| Thread Safety | All heavy operations on background threads, UI updates via `root.after()` |
| Drag & Drop | ctypes (primary) + windnd (fallback) support |

---

## 中文

### ✨ 功能总览

| 模块 | 说明 |
|------|------|
| 🎬 视频转换 | MP4、AVI、MKV、WMV、MOV、FLV、WEBM、TS、MPEG、3GP |
| 🎵 音频转换 | MP3、WAV、WMA、AAC、FLAC、OGG、M4A、AMR、OPUS |
| 🖼 图片转换 | JPG、PNG、BMP、GIF、TIFF、WEBP、ICO、TGA |
| 📄 文档转换 | PDF ↔ Word ↔ Excel ↔ PPT ↔ WPS ↔ TXT ↔ HTML ↔ 图片（168+种组合） |
| ↓ 提取音频 | 从视频文件中提取音轨为独立音频文件 |
| 📦 视频压缩 | 高/中/低质量预设，支持分辨率限制 |
| ⊙ 视频转GIF | 自定义宽度、帧率、起始时间、时长 |
| ⊞ PDF合并/拆分 | 多个PDF合并为一个，按页码范围拆分 |
| 🔒 PDF加密/解密 | AES-256/AES-128加密，密码历史记录 |
| 🗜 PDF压缩 | 降低PDF体积，支持DPI和图片质量控制 |
| ⊡ 图片压缩 | 质量控制、最大分辨率限制、显示压缩节省比例 |
| ✏ 批量重命名 | 模板支持 `{n}` 序号、`{name}` 原名、`{date}` 日期占位符 |
| 🔊 音频音量调节 | 支持 20%-200% 输出音量调整 |
| 🏷 图片水印添加 | 自定义水印文字，支持5种位置选择 |
| 🖼 预设裁剪 | 社交媒体尺寸预设（1:1、4:5、16:9等） |
| 🔍 格式检测 | 批量扫描文件夹，按格式自动分类，支持文件头魔数检测 |
| 📥 视频下载 | 支持 B站/YouTube/微博/Instagram 等数百个平台（基于yt-dlp） |
| 📊 底部状态流面板 | 实时进度日志、自动滚动、错误标红 |
| ✂ 视频处理 | 剪辑片段、多文件合并、字幕烧录、变速（0.5x-2.0x） |
| 👁 画质增强 | AI 4 倍超分（Real-ESRGAN ONNX，本地推理） |
| ☐ 表格识别 | 图片表格 OCR → CSV / Excel 输出 |
| 📁 文件夹监视 | 监视目录自动转换新文件（视频→MP4 / 音频→MP3 / 图片→PNG） |
| 🖱 文件右键菜单 | Windows 右键「用格式大师转换」一键打开 |
| 🌐 中英双语 | 简体中文 / English 界面语言切换 |

---

### 🎬 视频转换 — 详细说明

**支持格式**：MP4、AVI、MKV、WMV、MOV、FLV、WEBM、TS、MPEG、3GP

| 设置项 | 选项 |
|--------|------|
| 目标格式 | MP4、AVI、MKV、WMV、MOV、FLV、WEBM、TS、MPEG、3GP |
| 视频编码 | 默认、H.264、H.265/HEVC、VP9、MPEG4 |
| 画质预设 | 原始质量、高质量(大文件)、中等质量、低质量(小文件)、手机、网络分享 |
| 分辨率 | 原始、4K (3840×2160)、2K (2560×1440)、1080p、720p、480p、360p |
| 帧率 | 原始帧率、24、25、30、60 fps |
| 码率 | 自动、1M、2M、5M、8M、10M、20M |
| 仅转封装(无损) | 开/关 — 仅重封装不重编码（仅限 MP4/MKV/TS/FLV/MOV） |
| 快速预设 | 自定义 + 用户预设模板 |
| 输出目录 | 与源文件同目录 / 自定义目录 |

**特殊能力**：
- **流选择**：可选择性保留/移除音视频流
- **编码兼容性校验**：自动检测无损模式下的编码兼容性（如 H.265→FLV）
- **自动重命名**：输出文件与输入同名时自动加 `_1` 后缀

---

### 🎵 音频转换 — 详细说明

**支持格式**：MP3、WAV、WMA、AAC、FLAC、OGG、M4A、AMR、OPUS

| 设置项 | 选项 |
|--------|------|
| 目标格式 | MP3、WAV、WMA、AAC、FLAC、OGG、M4A、AMR、OPUS |
| 比特率 | 128k、192k、256k、320k |
| 采样率 | 原始、22050、44100、48000、96000 |
| 声道 | 原始、单声道、立体声 |
| 音量调节 | 20% ~ 200%（滑块控制） |
| 输出目录 | 与源文件同目录 / 自定义目录 |

---

### 🖼 图片转换 — 详细说明

**支持格式**：JPG、PNG、BMP、GIF、TIFF、WEBP、ICO、TGA

| 设置项 | 选项 |
|--------|------|
| 目标格式 | JPG、PNG、BMP、GIF、TIFF、WEBP、ICO、TGA |
| 质量 | 100(无损)、95(高质量)、85(中等)、70(低质量)、50(压缩) |
| 缩放 | 原始大小、50%、25%、200% |
| 旋转 | 0°、90°、180°、270° |
| 裁剪 | 原始比例、裁剪为正方形 |
| 灰度 | 开/关 — 转为黑白 |
| 水印文字 | 自定义输入 |
| 水印位置 | 右下角、左下角、右上角、左上角、居中 |
| 输出目录 | 与源文件同目录 / 自定义目录 |

---

### 📄 文档转换 — 详细说明

**支持格式**：PDF、DOCX、DOC、WPS、XLSX、XLS、ET、CSV、PPTX、PPT、DPS、TXT、HTML、HTM、MD、EPUB、RTF、ODT、JPG、JPEG、PNG、BMP、TIFF、WEBP

**168+ 种转换组合**：

| 源格式 | 可转目标 |
|--------|----------|
| PDF | DOCX、DOC、TXT、JPG、PNG、HTML、PPTX、XLSX |
| DOCX | PDF、TXT、HTML、JPG、PNG、PPTX、MD、DOC、WPS |
| DOC | PDF、TXT、DOCX、HTML、MD |
| WPS | DOCX、PDF、TXT、HTML、MD |
| XLSX | PDF、CSV、TXT、JPG、PNG、HTML、MD、ET |
| XLS | XLSX、PDF、CSV、TXT、JPG、PNG、HTML、MD |
| CSV | XLSX、PDF、TXT、HTML、MD |
| PPTX | PDF、TXT、JPG、PNG、PPT、DPS、DOCX、HTML、MD |
| PPT | PPTX、PDF、TXT |
| TXT | PDF、XLSX、DOCX、PPTX、HTML、MD |
| HTML | PDF、DOCX、TXT、XLSX、MD |
| MD | HTML、PDF、DOCX、TXT |
| EPUB | PDF、TXT、HTML、DOCX |
| RTF | TXT、PDF、DOCX |
| ODT | PDF、DOCX、TXT |
| 图片 | PDF、DOCX |

**特殊能力**：
- **格式检测**：自动识别源文件格式并列出可转换目标
- **Word转PDF**：通过 Microsoft Word COM 自动化
- **PPT转PDF**：通过 Microsoft PowerPoint COM 自动化
- **格式兼容性实时提示**：显示当前源/目标格式是否兼容

---

### ⊙ 视频转GIF — 详细说明

| 设置项 | 选项 |
|--------|------|
| 宽度 | 原始、640、480、320、240 |
| 帧率 | 10、15、20、24、30 fps |
| 开始时间(秒) | 0 |
| 时长(秒) | 5、10、15、30、60、全部 |
| 输出目录 | 与源文件同目录 / 自定义目录 |

---

### 🔒 PDF工具 — 详细说明

**5种操作模式**：

| 模式 | 功能 | 参数 |
|------|------|------|
| 合并（多个→一个） | 多PDF合并 | — |
| 拆分（一个→多个） | 按页码范围拆分 | 页码范围：`1-3,5,7-10` |
| 加密（设置密码） | PDF加密 | 打开密码、权限密码、加密方式(AES-256/AES-128) |
| 解密（移除密码） | PDF解密 | 输入密码 |
| 压缩 | 降低PDF体积 | 目标分辨率(72/100/150/200dpi)、图片质量(60-90) |

**附加功能**：
- **密码历史记录**：保存最近10条密码，支持复用
- **密码显示/隐藏切换**：点击眼睛图标切换

---

### 📥 视频下载 — 详细说明

**支持平台**：B站、YouTube、微博、Instagram 等数百个平台（基于 yt-dlp）

| 功能 | 说明 |
|------|------|
| URL解析 | 自动提取有效URL，过滤中文等非ASCII字符 |
| 格式获取 | 列出所有可用格式（分辨率、大小、格式ID） |
| 格式选择 | 从列表中选择目标格式 |
| 保存目录 | 默认 ~/Downloads，可自定义 |
| 抖音/TikTok提示 | 检测到抖音链接时显示平台限制警告 |
| yt-dlp版本检测 | 侧边栏显示版本，有新版本时提示更新 |

---

### 🔍 格式检测 — 详细说明

| 功能 | 说明 |
|------|------|
| 文件夹扫描 | 递归遍历所有文件 |
| 扩展名分类 | 按视频/音频/图片/文档/PDF/其他自动分类 |
| 文件头魔数检测 | 通过二进制头识别真实格式（PDF、JPEG、PNG、GIF、BMP、RIFF、MKV、MP4、ID3、FLAC、OGG、OLE、ZIP等） |
| 格式不匹配警告 | 扩展名与内容不符时标红提示 |
| 选择性批量转换 | 勾选文件后一键批量转换 |
| 全选/取消全选 | 批量操作控制 |
| 重新检测 | 重置并重新扫描 |
| 自动添加到对应面板 | 检测结果自动分发到各功能面板 |

---

### 🖼 预设裁剪 — 详细说明

| 设置项 | 选项 |
|--------|------|
| 预设尺寸 | 社交媒体标准尺寸（1:1 1080×1080 等） |
| 裁剪模式 | cover（裁剪填充）/ fit（等比适应） |
| 输出目录 | 与源文件同目录 / 自定义目录 |

---

### 📊 任务系统

| 功能 | 说明 |
|------|------|
| 任务队列 | FIFO串行处理，每500ms轮询 |
| 任务状态 | waiting → processing → success / failed |
| 进度显示 | Treeview表格 + 进度条 + 状态文本 |
| 任务清空 | 清空所有已完成任务 |
| 取消转换 | 立即终止当前任务 |

---

### 📝 日志系统

| 功能 | 说明 |
|------|------|
| 实时日志 | 底部Notebook面板，最多保留50行 |
| 日志级别 | success(绿)、error(红)、warning(黄)、info(蓝) |
| 日志清空 | 清空所有日志 |
| 双击复制 | 双击单行日志复制到剪贴板 |

---

### ⚙️ 用户偏好

| 功能 | 说明 |
|------|------|
| 面板参数保存 | 切换面板时自动保存所有设置 |
| 面板参数恢复 | 切换回来时恢复上次设置 |
| 持久化存储 | `%APPDATA%/FormatMaster/data/user_prefs.json` |

---

### 🔄 更新检查

| 功能 | 说明 |
|------|------|
| 启动自动检查 | 后台线程检查GitHub releases |
| 手动检查 | 关于窗口中可手动触发 |
| 更新通知 | 顶部蓝色横幅，点击跳转下载页 |
| 版本比较 | 支持语义化版本 |

---

### 🚀 快速开始

#### 下载使用

从 [Releases](https://github.com/Gu-0312/FormatMaster-EN/releases/tag/v1.3.1) 页面下载最新版本，解压后双击 `格式大师.exe` 即可使用。

#### 从源码运行

```bash
# 克隆仓库
git clone https://github.com/Gujh/FormatMaster.git
cd FormatMaster

# 安装依赖
pip install -r requirements.txt

# 运行应用
python main_qt.py

# 打包为exe
python build.py
```

### 🛠 技术栈

- **界面**: Python PySide6 + qfluentwidgets（Fluent Widgets，Prism 设计系统）
- **视频/音频**: FFmpeg（自动下载或使用系统PATH）
- **图片**: Pillow
- **文档**: python-docx、openpyxl、python-pptx、pypdf、pdf2docx、reportlab、PyMuPDF
- **Word转PDF**: 调用本地 Microsoft Word COM 自动化
- **PPT转PDF**: 调用本地 Microsoft PowerPoint COM 自动化
- **视频下载**: yt-dlp
- **打包**: PyInstaller

### 📁 项目结构

```
FormatMaster/
├── main_qt.py           # 主程序入口（PySide6 界面）
├── build.py             # PyInstaller打包脚本
├── requirements.txt     # Python依赖
├── assets/
│   └── icon.ico         # 应用图标
├── gui_qt/              # PySide6 + Fluent Widgets 界面
│   ├── app.py           # MainWindow（FluentWindow + Mica）
│   ├── nav_registry.py  # 导航注册真源
│   ├── services.py      # QtServices 服务容器
│   ├── task_manager.py  # 任务队列（信号驱动，FIFO）
│   ├── pages/           # 首页/任务/历史/设置/关于
│   ├── panels/          # 功能面板（视频、音频、PDF、OCR 等）
│   └── components/      # 侧边栏、主题管理、设计系统
├── core/                # 业务逻辑（无 UI 依赖）
│   ├── video_converter.py   # 视频转换（FFmpeg）
│   ├── audio_converter.py   # 音频转换（FFmpeg）
│   ├── image_converter.py   # 图片转换（Pillow）
│   ├── doc_converter.py     # 文档转换（168+种组合）
│   ├── video_downloader.py  # 视频下载（yt-dlp）
│   ├── pdf_editor.py        # PDF编辑
│   ├── ocr_tool.py          # OCR识别（RapidOCR）
│   └── tools.py             # PDF合并/拆分/加密/压缩、图片压缩、批量重命名
├── utils/
│   ├── config.py            # 配置与格式定义
│   ├── ffmpeg_manager.py    # FFmpeg下载管理
│   ├── hardware_accel.py    # NVENC / QSV / AMF 硬件加速检测
│   └── format_helpers.py    # 格式辅助工具
└── app/
    ├── theme.py             # 主题颜色
    └── exceptions.py        # EX_HINT 异常中文映射
```

### 🖥 技术特性

| 特性 | 实现方式 |
|------|----------|
| DPI高分屏适配 | `SetProcessDpiAwareness(2)` |
| 双缓冲渲染 | DWM API，消除界面闪烁 |
| 黑边修复 | 窗口映射事件触发强制重绘 |
| 异常中文映射 | 20+种异常→中文用户提示 |
| 窗口自适应 | 80%屏幕，最小880×620 |
| 线程安全 | 所有耗时操作在子线程，UI更新通过 `root.after()` |
| 拖拽支持 | ctypes（优先）+ windnd（降级）双重支持 |

---

### 📝 更新日志

#### v1.3.1 (2026-08-03)
- 🏗  架构重构：16 个功能面板 DI 化迁移至独立模块，main.py 瘦身
- 🔧 接入 app.exceptions/app.theme/utils.format_helpers 公共模块，消除内联重复
- 🐛 修复批量重命名大小写转换误改扩展名问题（`photo.jpg` → `PHOTO.JPG` → `PHOTO.jpg`）
- 🧪 新增 pytest 单元测试套件（72 测试覆盖纯函数与 _fmt_n 回归）
- ⚡ 新增硬件加速支持（NVIDIA NVENC / Intel QSV / AMD AMF）
- 🔧 FFmpeg 下载失败增强 UX（重试 + 错误详情 + 手动选择 + 下载页）
- 📦 PyInstaller 打包配置增强（onedir + collect-all fitz/PIL/rapidocr）

#### v1.3.0 (2026-07-23)
- 📥 新增视频下载功能（基于yt-dlp，支持数百个平台）
- 🎬 新增视频快速预设（一键应用常用配置组合）
- 🔒 新增PDF密码历史记录（保存最近10条密码，支持一键复用）
- 🔍 格式检测新增文件头魔数识别（通过二进制头判断真实格式，不受扩展名误导）
- 📄 文档格式兼容性实时提示（自动判断源/目标格式是否可转换）
- 🖼  文件属性预览（选中文件后异步显示时长、分辨率、编码信息）
- 🔒 新增PDF加密/解密功能（AES-256/AES-128）
- 🗜  新增PDF压缩功能（DPI + 质量控制）
- 🔄 启动自动更新检查（后台检测GitHub最新版本，发现新版本顶部横幅通知）
- 🖼  新增图像预设裁剪功能（社交媒体尺寸）
- 🐛 修复输出文件与输入同名时自动重命名（加 `_1` 后缀避免覆盖）

#### v1.1.0 (2026-07-16)
- 🔊 新增音频音量调节功能（20%-200%）
- 🏷  新增图片水印添加功能（支持5种位置）
- 📊 新增底部状态流面板（实时进度日志、自动滚动、错误标红）
- 🔍 新增格式检测功能（批量扫描文件夹，按格式自动分类）
- 📋 新增关于窗口（包含GitHub链接和免责声明）
- 🐛 修复拖拽功能、进度条卡顿等已知问题

#### v1.0.0 (2026-05-31)
- 🎉 首次发布
- 视频/音频/图片/文档格式转换
- 提取音频、视频压缩、视频转GIF
- PDF合并/拆分、图片压缩、批量重命名
- 内置REST API接口
- 白色主题UI + DPI高分屏适配

---

<div align="center">

**Made with ❤️ by [Gujh](https://github.com/Gujh)**

</div>
