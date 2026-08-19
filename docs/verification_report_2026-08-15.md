# 格式大师 v1.3.7 全功能验证报告

验证日期:2026-08-15 | 验证环境:Windows 10 x64, Python 3.11.0 (venv)

---

## 一、结论摘要

| 验证项 | 结果 |
|---|---|
| 单元测试回归(原 116 用例) | ✅ 通过 |
| 新增 GUI 面板冒烟(41 导航入口 + 38 面板) | ✅ 通过 |
| 新增真实 FFmpeg 转换链路(19 用例) | ✅ 通过 |
| 插件中心 32 个插件激活 | ✅ 全部成功 |
| 全量回归(137 用例) | ✅ 全部通过 |
| 打包(onedir) + 产物启动 + CLI 链路 | ✅ 通过 |
| **他人可用性(依赖完整性)** | ⚠️ 已发现并修复 5 个缺失依赖 |

**总评:核心功能全部正常;发现并修复 1 个会影响他人使用的关键问题(依赖缺失),修复后重新打包验证通过。**

---

## 二、发现并修复的关键问题

### 🔴 问题:requirements.txt 缺失 5 个被代码引用的依赖

| 缺失依赖 | 受影响功能 | 修复前实测结果 |
|---|---|---|
| `striprtf` | RTF→TXT/PDF/DOCX | ❌ ModuleNotFoundError |
| `odfpy` | ODT→TXT/DOCX/PDF | ❌ ModuleNotFoundError |
| `xlrd` | XLS(Excel97)→XLSX/PDF | ❌ ModuleNotFoundError |
| `chardet` | 非 UTF-8 编码文本读取(GBK 等) | ❌ ModuleNotFoundError |
| `psutil` | 系统信息内存采集(ctypes 失败时降级) | ⚠️ 缺失(有 ctypes 主路径兜底) |

**根因**:这些依赖在 `core/doc_converter.py`、`core/doc_excel.py`、`core/doc_misc.py` 等模块中以**函数内延迟导入**方式引用,启动时不报错,只有实际执行转换才暴露。

**修复**:
1. `requirements.txt` 补充 5 个依赖声明(他人 pip install 后可用);
2. `build.py` 补充对应 `--hidden-import`(PyInstaller 打包时收录);
3. venv 已安装,重新打包验证收录成功。

**修复后重测**:RTF×3、ODT×3、GBK 文本读取全部通过。

---

## 三、测试覆盖明细

### 1. 原有单元测试(116 用例)— 全部通过
覆盖:格式辅助、错误映射、设置功能(代理/临时清理)、工具更新器、应用更新器、冒烟(文档/图片/音频/视频/OCR/哈希/二维码/文件安全/任务链路/局域网服务)。

### 2. 新增 GUI 面板冒烟(2 用例)— 通过
- **41 个导航入口全部可构建**(offscreen 模式,含 4 个页面 + 38 个面板);
- **38 个面板控件属性遍历**:遍历每个面板的 ComboBox 全部选项、CheckBox、Slider、SpinBox、LineEdit,并验证 `collect_params()` / `collect_prefs()` / `apply_prefs()` 往返无异常。
- 文件:`tests/test_panel_smoke.py`

### 3. 新增真实 FFmpeg 转换链路(19 用例)— 通过
- **视频**:6 种容器格式(AVI/MKV/MOV/TS/FLV/WebM)、分辨率 360p、帧率 24fps、流复制无损、剪辑、变速 2x、去水印、抽帧、合并、反挤压、压缩
- **音频**:裁剪、降噪、响度标准化、音量 150%
- **PDF**:加密/解密、合并/拆分、压缩、水印、页码
- **场景化转换**:8 个场景全部执行成功
- 文件:`tests/test_real_conversion.py`

### 4. 插件中心(32 个)— 全部激活成功
ASCII画/进制/Base64/取色/CSV/编码转换/EXIF清理/查找替换/哈希/HTML预览/身份证解析/IP查询/JSON/JWT/URL/摩斯/九宫格/正则/字幕转换/SQL/文本对比/排序/时间戳/Unicode/UUID/网页转PDF/字数/简繁/YAML 等。

---

## 四、打包验证

| 项目 | 结果 |
|---|---|
| PyInstaller 6.21.0 onedir 打包 | ✅ 成功(79s) |
| 产物位置 | `D:\格式大师\FormatMaster_dist\dist\格式大师\格式大师.exe` |
| 产物大小 | 844MB(onedir,含 FFmpeg/yt-dlp/OCR 模型等) |
| FFmpeg/ffprobe/yt-dlp | ✅ 已收录 `_internal/bin/` |
| 新增 5 依赖收录 | ✅ PYZ 归档确认(striprtf/odf/xlrd/chardet/psutil 全部在内) |
| 文档转换依赖 | ✅ docx(150)/openpyxl(176)/pptx(101)/pypdf(51)/pdf2docx(55)/reportlab(97)/PyMuPDF 全部收录 |
| GUI 启动 | ✅ 进程持续运行 136s(内存 479MB,无崩溃) |
| CLI 链路 `--quick-convert` | ✅ 视频 → MP4 转换成功,输出文件生成 |
| 单实例锁 | ✅ 二次启动正确退出(锁生效) |

**注意**:`--onefile` 单文件模式尚未测试,如需发布单文件版需单独验证。

---

## 五、遗留风险与建议

1. **Word/PPT→PDF 依赖本机 Office COM**:打包不包含 Word/PPT,目标机未装 Office 时该 2 个转换方向不可用(代码已有 COM 失败提示,属预期)。
2. **网络功能**(视频下载/M3U8/更新检查/局域网)依赖运行时网络与 yt-dlp 版本,本次验证了本地逻辑与 yt-dlp 可执行性,未做真实下载测试。
3. **OCR 需要首次加载模型**(约 1-2s 冷启动,已有进度提示)。
4. **建议**:发布前在全新 Windows 环境(无 Python)实机跑一遍 GUI,确认体验。可考虑 `--onefile` 单文件版发布(当前 onedir 844MB)。
5. 修复的 5 个依赖已提交到 requirements.txt 与 build.py,**记得一起发布**(否则他人安装/打包仍会缺失)。

---

## 六、新增/修改文件清单

| 文件 | 变更 |
|---|---|
| `requirements.txt` | +5 依赖声明(striprtf/odfpy/xlrd/chardet/psutil) |
| `build.py` | +5 hidden-import |
| `tests/test_panel_smoke.py` | 新增(2 用例) |
| `tests/test_real_conversion.py` | 新增(19 用例) |
| venv | +5 依赖包 |
