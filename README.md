<div align="center">

# 🔄 FormatMaster / 格式大师

**All-in-one format converter for video, audio, image & documents.**
**全能格式转换工具 — 视频、音频、图片、文档一站式转换**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Release](https://img.shields.io/badge/Release-v1.0.0-orange.svg)]()

---

[English](#english) · [中文](#中文)

</div>

---

## English

### ✨ Features

| Module | Supported Formats |
|--------|-------------------|
| 🎬 Video Convert | MP4, AVI, MKV, WMV, MOV, FLV, WEBM, TS, MPEG, 3GP |
| 🎵 Audio Convert | MP3, WAV, WMA, AAC, FLAC, OGG, M4A, AMR, OPUS |
| 🖼 Image Convert | JPG, PNG, BMP, GIF, TIFF, WEBP, ICO, TGA |
| 📄 Document Convert | PDF ↔ Word ↔ Excel ↔ PPT ↔ WPS ↔ TXT ↔ HTML ↔ Image |
| ↓ Extract Audio | Extract audio track from video files |
| 📦 Video Compress | High / Medium / Low quality presets with resolution limit |
| ⊙ Video to GIF | Custom width, fps, start time, duration |
| ⊞ PDF Merge / Split | Merge multiple PDFs, split by page ranges |
| ⊡ Image Compress | Quality control, max resolution, save percentage display |
| ✏ Batch Rename | Templates with `{n}` serial, `{name}`, `{date}` placeholders |

### 🚀 Quick Start

#### Download

Download the latest release from [Releases](https://github.com/Gujh/FormatMaster/releases) page — no installation required, just double-click `格式大师.exe`.

#### Build from Source

```bash
# Clone the repository
git clone https://github.com/Gujh/FormatMaster.git
cd FormatMaster

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py

# Build executable
python build.py
```

### 📡 API Server

FormatMaster includes a REST API for Postman / frontend integration:

```bash
# Start the API server
python api_server.py

# Server runs on http://localhost:5000
```

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Server status |
| `GET` | `/api/formats` | Supported format list |
| `POST` | `/api/video/convert` | Video conversion |
| `POST` | `/api/audio/convert` | Audio conversion |
| `POST` | `/api/image/convert` | Image conversion |
| `POST` | `/api/doc/convert` | Document conversion |
| `POST` | `/api/extract/audio` | Extract audio from video |
| `POST` | `/api/video/compress` | Video compression |
| `POST` | `/api/video/gif` | Video to GIF |
| `POST` | `/api/pdf/merge` | Merge PDFs |
| `POST` | `/api/pdf/split` | Split PDF |
| `POST` | `/api/image/compress` | Image compression |

> All `POST` endpoints accept `multipart/form-data` with a `file` field and format parameters.

### 🛠 Tech Stack

- **GUI**: Python tkinter + ttk
- **Video/Audio**: FFmpeg (auto-download or system PATH)
- **Image**: Pillow
- **Document**: python-docx, openpyxl, python-pptx, pypdf, pdf2docx, reportlab, PyMuPDF
- **Word → PDF**: Microsoft Word COM automation
- **API**: Flask
- **Packaging**: PyInstaller

### 📁 Project Structure

```
FormatMaster/
├── main.py              # Application entry point (GUI)
├── api_server.py        # REST API server
├── build.py             # PyInstaller build script
├── requirements.txt     # Python dependencies
├── assets/
│   └── icon.ico         # Application icon
├── core/
│   ├── video_converter.py   # Video conversion (FFmpeg)
│   ├── audio_converter.py   # Audio conversion (FFmpeg)
│   ├── image_converter.py   # Image conversion (Pillow)
│   ├── doc_converter.py     # Document conversion
│   └── tools.py             # PDF merge/split, image compress, batch rename
└── utils/
    ├── config.py            # Configuration & format definitions
    ├── ffmpeg_manager.py    # FFmpeg download & management
    └── dnd.py               # Drag-and-drop support
```

---

## 中文

### ✨ 功能特性

| 模块 | 支持格式 |
|------|----------|
| 🎬 视频转换 | MP4、AVI、MKV、WMV、MOV、FLV、WEBM、TS、MPEG、3GP |
| 🎵 音频转换 | MP3、WAV、WMA、AAC、FLAC、OGG、M4A、AMR、OPUS |
| 🖼 图片转换 | JPG、PNG、BMP、GIF、TIFF、WEBP、ICO、TGA |
| 📄 文档转换 | PDF ↔ Word ↔ Excel ↔ PPT ↔ WPS ↔ TXT ↔ HTML ↔ 图片 |
| ↓ 提取音频 | 从视频文件中提取音轨为独立音频文件 |
| 📦 视频压缩 | 高/中/低质量预设，支持分辨率限制 |
| ⊙ 视频转GIF | 自定义宽度、帧率、起始时间、时长 |
| ⊞ PDF合并/拆分 | 多个PDF合并为一个，按页码范围拆分 |
| ⊡ 图片压缩 | 质量控制、最大分辨率限制、显示压缩节省比例 |
| ✏ 批量重命名 | 模板支持 `{n}` 序号、`{name}` 原名、`{date}` 日期占位符 |

### 🚀 快速开始

#### 下载使用

从 [Releases](https://github.com/Gujh/FormatMaster/releases) 页面下载最新版本，解压后双击 `格式大师.exe` 即可使用。

#### 从源码运行

```bash
# 克隆仓库
git clone https://github.com/Gujh/FormatMaster.git
cd FormatMaster

# 安装依赖
pip install -r requirements.txt

# 运行应用
python main.py

# 打包为exe
python build.py
```

### 📡 API 接口

格式大师内置 REST API，可用 Postman 或前端调用：

```bash
# 启动API服务器
python api_server.py

# 服务运行在 http://localhost:5000
```

#### 接口列表

| 方法 | 接口 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 服务器状态 |
| `GET` | `/api/formats` | 支持格式列表 |
| `POST` | `/api/video/convert` | 视频转换 |
| `POST` | `/api/audio/convert` | 音频转换 |
| `POST` | `/api/image/convert` | 图片转换 |
| `POST` | `/api/doc/convert` | 文档转换 |
| `POST` | `/api/extract/audio` | 从视频提取音频 |
| `POST` | `/api/video/compress` | 视频压缩 |
| `POST` | `/api/video/gif` | 视频转GIF |
| `POST` | `/api/pdf/merge` | PDF合并 |
| `POST` | `/api/pdf/split` | PDF拆分 |
| `POST` | `/api/image/compress` | 图片压缩 |

> 所有 `POST` 接口使用 `multipart/form-data`，包含 `file` 文件字段和对应参数。

### 🛠 技术栈

- **界面**: Python tkinter + ttk
- **视频/音频**: FFmpeg（自动下载或使用系统PATH）
- **图片**: Pillow
- **文档**: python-docx、openpyxl、python-pptx、pypdf、pdf2docx、reportlab、PyMuPDF
- **Word转PDF**: 调用本地 Microsoft Word COM 自动化
- **API**: Flask
- **打包**: PyInstaller

### 📁 项目结构

```
FormatMaster/
├── main.py              # 主程序入口（GUI界面）
├── api_server.py        # REST API服务器
├── build.py             # PyInstaller打包脚本
├── requirements.txt     # Python依赖
├── assets/
│   └── icon.ico         # 应用图标
├── core/
│   ├── video_converter.py   # 视频转换（FFmpeg）
│   ├── audio_converter.py   # 音频转换（FFmpeg）
│   ├── image_converter.py   # 图片转换（Pillow）
│   ├── doc_converter.py     # 文档转换
│   └── tools.py             # PDF合并拆分、图片压缩、批量重命名
└── utils/
    ├── config.py            # 配置与格式定义
    ├── ffmpeg_manager.py    # FFmpeg下载管理
    └── dnd.py               # 拖拽支持
```

### 📝 更新日志

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
