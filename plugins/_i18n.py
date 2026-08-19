# -*- coding: utf-8 -*-
"""plugins/_i18n — 插件共享中英双语翻译表。

插件单文件加载（importlib spec_from_file_location），统一从这里取翻译：
    from plugins._i18n import t
    btn.setText(t("计算"))          # 中文模式返回"计算"，英文模式查表返回英文

数据类内容（简繁字库、身份证省市表等）不属于 UI 文案，不参与翻译。
"""
try:
    from gui_qt.i18n import tr
except Exception:  # noqa: BLE001 - 独立运行（无 GUI）时退化为原样返回
    tr = lambda zh, en: zh


def t(zh):
    """按当前语言返回文案：查表得到英文，未收录的键回退中文。"""
    return tr(zh, _EN.get(zh, zh))


_EN = {
    # ── 通用 ─────────────────────────────────────
    "文本": "Text",
    "文件": "File",
    "编码": "Encode",
    "解码": "Decode",
    "转换": "Convert",
    "选择文件": "Choose file",
    "复制结果": "Copy result",
    "打开输出文件夹": "Open output folder",
    "输出目录不存在": "Output folder does not exist",
    "选择图片": "Choose image",
    "宽度": "Width",
    "生成": "Generate",
    "保存": "Save",
    "格式": "Format",
    "浏览": "Browse",
    "数量": "Count",
    "长度": "Length",
    "类型": "Type",
    "验证": "Verify",
    "计算": "Calculate",
    "读取失败：{e}": "Read failed: {e}",
    "保存为文件": "Save as file",
    "请先选择文件（或直接粘贴文件路径）": "Choose a file first (or paste a file path)",
    "解码失败：{e}": "Decode failed: {e}",
    "请先编码或粘贴 Base64 到输入框再解码": "Encode first, or paste Base64 into the input to decode",
    "不是有效的编码：{e}": "Not valid encoded data: {e}",
    "已保存：{path}": "Saved: {path}",
    "转换失败：{e}": "Convert failed: {e}",
    "另存为": "Save as",
    "已转换保存：{out_path}": "Converted and saved: {out_path}",
    "请先选择文件": "Choose a file first",
    "已选择：{path}": "Selected: {path}",
    "请先选择图片": "Choose an image first",
    "生成失败：{e}": "Generate failed: {e}",
    "保存为 txt": "Save as txt",
    "文本 (*.txt)": "Text (*.txt)",

    # ── ascii_art ────────────────────────────────
    "反色": "Invert",
    "生成字符画": "Generate ASCII art",
    "保存 txt": "Save txt",

    # ── base64_tool ──────────────────────────────
    "输入要处理的文本或 Base64…": "Enter text or Base64…",
    "选择文件": "Choose file",
    "保存为文件": "Save as file",
    "请先选择文件（或直接粘贴文件路径）": "Choose a file first (or paste a file path)",

    # ── base_convert ─────────────────────────────
    "进制转换": "Base converter",
    "数字": "Number",
    "如 255、0xFF、11111111、-128…": "e.g. 255, 0xFF, 11111111, -128…",
    "源进制": "Source base",
    "自动识别": "Auto detect",
    "目标进制": "Target base",
    "大写": "Upper case",
    "大写 A-F": "Upper A-F",
    "小写 a-f": "Lower a-f",
    "自动": "Auto",
    "十进制 DEC：{n}\n": "Decimal DEC: {n}\n",

    # ── color_picker ─────────────────────────────
    "颜色选择器": "Color picker",
    "打开拾色器": "Open picker",
    "输入 HEX（如 #4F6EF7）": "Enter HEX (e.g. #4F6EF7)",
    "解析": "Parse",
    "选择颜色": "Choose color",
    "无效 HEX": "Invalid HEX",

    # ── csv_viewer ───────────────────────────────
    "选择 CSV 文件": "Choose CSV file",
    "选择 CSV": "Choose CSV",
    "空文件": "Empty file",
    "列 {i+1}": "Col {i+1}",
    "编码 {used}{note}": "Encoding {used}{note}",

    # ── encoding_convert ─────────────────────────
    "文本编码转换": "Text encoding converter",
    "源编码": "Source encoding",
    "目标编码": "Target encoding",
    "选择文本文件": "Choose text file",
    "已按 {enc} 读取": "Read as {enc}",
    "输入文本，或切换到「文件」模式选择文件（只读预览）…": "Enter text, or switch to File mode to pick a file (read-only preview)…",

    # ── example_plugin ───────────────────────────
    "文本反转": "Text reverse",
    "输入要反转的文本…": "Enter text to reverse…",
    "反转": "Reverse",

    # ── exif_cleaner ─────────────────────────────
    "图片信息清理": "Image info cleaner",
    "拍摄时间": "Date taken",
    "相机厂商": "Camera maker",
    "相机型号": "Camera model",
    "软件": "Software",
    "镜头型号": "Lens model",
    "曝光时间": "Exposure",
    "光圈": "Aperture",
    "焦距": "Focal length",
    "方向": "Orientation",
    "作者": "Author",
    "版权": "Copyright",
    "白平衡": "White balance",
    "闪光灯": "Flash",
    "清理并另存": "Clean & save as",
    "该图片没有 EXIF 信息（或格式不支持）": "No EXIF data found (or unsupported format)",
    "另存为（已清理 EXIF）": "Save as (EXIF cleaned)",
    "图片 (*{ext})": "Image (*{ext})",
    "清理失败：{e}": "Clean failed: {e}",

    # ── find_replace ─────────────────────────────
    "批量查找替换": "Find & replace",
    "输入要处理的文本…": "Enter text to process…",
    "查找": "Find",
    "替换为": "Replace with",
    "正则": "Regex",
    "替换": "Replace",
    "替换 {n} 处": "Replaced {n} occurrence(s)",
    "正则错误：{e}": "Regex error: {e}",

    # ── hash_calc ────────────────────────────────
    "哈希校验": "Hash calculator",
    "算法": "Algorithm",
    "输入文本，或切换到「文件」模式选择文件…": "Enter text, or switch to File mode to pick a file…",
    "验证哈希": "Verify hash",
    "粘贴期望的哈希值进行比对": "Paste the expected hash to compare",
    "请先选择文件": "Choose a file first",
    "文本哈希": "Text hash",
    "请输入期望哈希值": "Enter the expected hash",
    "请先计算哈希": "Calculate a hash first",

    # ── html_preview / markdown_preview ──────────
    "导入 HTML 文件": "Import HTML file",
    "导入 Markdown 文件": "Import Markdown file",
    "新建": "New",
    "输入 HTML，或导入 .html 文件…": "Enter HTML, or import an .html file…",
    "输入 Markdown，或导入 .md 文件…": "Enter Markdown, or import an .md file…",
    "选择 HTML 文件": "Choose HTML file",
    "选择 Markdown 文件": "Choose Markdown file",

    # ── id_card（仅 UI 文案；省市地名数据不翻译）──
    "身份证解析": "ID card parser",
    "长度必须为 18 位": "Length must be 18 digits",
    "格式错误：前 17 位数字，末位数字或 X": "Invalid format: 17 digits + digit or X",
    "校验失败：末位应为 {expect}": "Checksum failed: last digit should be {expect}",
    "出生日期无效": "Invalid birth date",
    "未知省": "Unknown province",
    "女": "Female",
    "男": "Male",
    "校验：✓ 通过（末位 {expect}）": "Checksum: ✓ passed (last {expect})",
    "地区：{region}（{card[:6]}）": "Region: {region} ({card[:6]})",
    "性别：{gender}": "Gender: {gender}",
    "摩羯": "Capricorn",
    "水瓶": "Aquarius",
    "双鱼": "Pisces",
    "白羊": "Aries",
    "金牛": "Taurus",
    "双子": "Gemini",
    "巨蟹": "Cancer",
    "狮子": "Leo",
    "处女": "Virgo",
    "天秤": "Libra",
    "天蝎": "Scorpio",
    "射手": "Sagittarius",
    "座": "",
    "输入 18 位身份证号码…": "Enter an 18-digit ID number…",

    # ── ip_lookup ────────────────────────────────
    "请输入域名或 IP 地址": "Enter a domain or IP address",
    "解析失败：{e}": "Resolve failed: {e}",
    "公网 IP：{ip}": "Public IP: {ip}",
    "查询失败：无法访问公网（检查网络连接）": "Query failed: cannot reach the Internet (check your connection)",
    "本机 IP": "Local IP",
    "查询公网 IP": "Query public IP",
    "输入域名（如 example.com）或 IP 地址查询…": "Enter a domain (e.g. example.com) or IP to query…",
    "查询": "Query",
    "本机局域网 IP：\n": "Local LAN IP:\n",
    "查询中…": "Querying…",

    # ── json_format ──────────────────────────────
    "美化": "Beautify",
    "压缩": "Minify",
    "校验": "Validate",
    "树形视图": "Tree view",
    "键": "Key",
    "值": "Value",
    "文本视图": "Text view",
    "输入 JSON…\n例如：{\"a\": 1, \"b\": [1, 2]}": "Enter JSON…\ne.g. {\"a\": 1, \"b\": [1, 2]}",

    # ── jwt_decode ───────────────────────────────
    "已过期 {abs(left)}": "Expired {abs(left)}",
    "剩余 {left}": "Remaining {left}",
    "粘贴 JWT token…\n格式：xxxxx.yyyyy.zzzzz": "Paste a JWT token…\nFormat: xxxxx.yyyyy.zzzzz",

    # ── money_upper ──────────────────────────────
    "数字大写": "Number to Chinese uppercase",
    "无效数字": "Invalid number",
    "零元整": "Zero yuan",
    "元": "yuan",
    "整": "exact",
    "角": "jiao",
    "分": "fen",
    "负": "negative ",
    "输入金额，如 123456.78 或 10005": "Enter an amount, e.g. 123456.78 or 10005",
    "转大写": "Convert",

    # ── morse_code ───────────────────────────────
    "摩斯电码": "Morse code",
    "输入文本或摩斯电码…\n文本：SOS  hello\n摩斯：... --- ...": "Enter text or Morse…\nText: SOS  hello\nMorse: ... --- ...",
    "转摩斯": "To Morse",
    "转文本": "To text",

    # ── nine_grid ────────────────────────────────
    "九宫格切图": "Nine-grid cutter",
    "图片太小，无法切九宫格": "Image too small for nine-grid",
    "切图失败：{e}": "Cut failed: {e}",
    "选择输出文件夹": "Choose output folder",
    "开始切图": "Start cutting",
    "输出目录：{path}": "Output folder: {path}",

    # ── regex_tester ─────────────────────────────
    "正则测试器": "Regex tester",
    "例如：\\d+ 或 [a-z]+": "e.g. \\d+ or [a-z]+",
    "测试": "Test",
    "输入要匹配的文本…": "Enter text to match…",
    "匹配 {len(matches)} 处": "Matched {len(matches)} occurrence(s)",

    # ── sql_format ───────────────────────────────
    "粘贴 SQL…\n如：select a,b from t where x=1 and y=2": "Paste SQL…\ne.g. select a,b from t where x=1 and y=2",
    "格式化": "Format",

    # ── subtitle_convert ─────────────────────────
    "字幕格式互转": "Subtitle format converter",
    "选择字幕文件（自动识别 SRT/ASS/VTT）…": "Choose a subtitle file (SRT/ASS/VTT auto-detected)…",
    "输出目录": "Output folder",
    "默认与源文件同目录": "Same folder as source by default",
    "选择目录": "Choose folder",
    "转换为": "Convert to",
    "选择字幕文件": "Choose subtitle file",
    "选择输出目录": "Choose output folder",
    "输出目录不存在，请重新选择": "Output folder does not exist, please re-choose",
    "请先选择字幕文件": "Choose a subtitle file first",

    # ── text_diff ─────────────────────────────────
    "文本对比": "Text diff",
    "文本 A…": "Text A…",
    "文本 B…": "Text B…",
    "对比": "Compare",
    "差异：删除 {dels} 行 · 新增 {adds} 行": "Diff: {dels} deleted · {adds} added",

    # ── text_sort ────────────────────────────────
    "文本去重排序": "Text sort & dedupe",
    "输入文本（每行一条）…": "Enter text (one line each)…",
    "操作": "Action",
    "去重（保持顺序）": "Dedupe (keep order)",
    "去重 + 排序": "Dedupe + sort",
    "排序（升序）": "Sort (ascending)",
    "排序（降序）": "Sort (descending)",
    "按长度排序": "Sort by length",
    "反转行顺序": "Reverse lines",
    "忽略空行": "Skip empty lines",
    "执行": "Run",

    # ── timestamp_convert ────────────────────────
    "时间戳转换": "Timestamp converter",
    "输入时间戳（如 1700000000）或日期（如 2023-11-15 10:00:00）": "Enter a timestamp (e.g. 1700000000) or a date (e.g. 2023-11-15 10:00:00)",
    "时间戳 → 日期": "Timestamp → Date",
    "日期 → 时间戳": "Date → Timestamp",
    "无法解析：{raw!r} 不是数字": "Cannot parse: {raw!r} is not a number",
    "请输入日期": "Enter a date",
    "无法解析日期：{raw!r}": "Cannot parse date: {raw!r}",
    "秒级时间戳：{int(ts)}\n": "Seconds timestamp: {int(ts)}\n",

    # ── unicode_codec ────────────────────────────
    "输入文本或 \\uXXXX 转义序列…\n如：你好 / \\u4f60\\u597d": "Enter text or \\uXXXX escapes…\ne.g. 你好 / \\u4f60\\u597d",

    # ── url_codec ────────────────────────────────
    "输入要编码/解码的文本…": "Enter text to encode/decode…",
    "空格用 + 表示": "Space is shown as +",

    # ── uuid_generator ───────────────────────────
    "随机密码": "Random password",
    "移除连字符": "Remove hyphens",

    # ── web_to_pdf ───────────────────────────────
    "网页转 PDF": "Web to PDF",
    "输入网页地址，加载后整页渲染预览，一键导出 PDF：": "Enter a URL, preview the full-page render, then export to PDF:",
    "输入网页 URL，如 https://example.com": "Enter a URL, e.g. https://example.com",
    "加载网页": "Load page",
    "导出 PDF": "Export PDF",
    "缺少 QtWebEngine 组件，无法渲染网页": "QtWebEngine missing — cannot render the page",
    "请先输入网页地址": "Enter a URL first",
    "正在加载网页…（首次启动稍慢）": "Loading page… (slower on first launch)",
    "网页已加载，可导出 PDF（整页渲染）": "Page loaded — export PDF (full-page render)",
    "网页加载失败（检查地址或网络）": "Page load failed (check the URL or network)",
    "保存 PDF": "Save PDF",
    "正在导出 PDF…": "Exporting PDF…",

    # ── word_count ───────────────────────────────
    "字数统计": "Word count",
    "总字符": "Total chars",
    "去空白字符": "No whitespace",
    "汉字": "Chinese chars",
    "英文/数字词": "Words (EN/digits)",
    "标点": "Punctuation",
    "行数": "Lines",
    "段落": "Paragraphs",
    "粘贴或输入文本，自动实时统计…": "Paste or type text — counted in real time…",
    "统计": "Count",

    # ── yaml_convert ─────────────────────────────
    "输入 JSON 或 YAML…": "Enter JSON or YAML…",
    "自动识别转换": "Auto-detect & convert",
    "缺少 pyyaml 模块（pip install pyyam": "pyyaml missing (pip install pyyam",

    # ── zh_convert（UI 按钮已 tr 化，此处备用）──
    "简体 → 繁体": "Simplified → Traditional",
    "繁体 → 简体": "Traditional → Simplified",
    "输入要转换的文本…": "Enter text to convert…",

    # ── 插件中心卡片（name / description）─────────
    # 供 plugin_panel 渲染卡片时翻译插件名与简介；未收录的自定义插件回退原文。
    "文本反转": "Text reverse",
    "把输入的每一行文本反转（示例插件）": "Reverse each line of input text (sample plugin)",
    "CSV 表格查看": "CSV viewer",
    "CSV 文件表格化查看（UTF-8 / GBK 自动识别）": "View CSV as a table (UTF-8 / GBK auto-detected)",
    "ASCII 字符画": "ASCII art",
    "图片转 ASCII 字符画": "Convert an image to ASCII art",
    "拾色器 + HEX / RGB / HSL 互转": "Color picker + HEX / RGB / HSL conversion",
    "Base64 工具": "Base64 tool",
    "文本/文件 Base64 / URL-safe / Base32 / Base16 编解码": "Encode/decode text or files: Base64 / URL-safe / Base32 / Base16",
    "18 位身份证校验、出生日期、性别、地区": "Validate 18-digit Chinese ID: checksum, birth date, gender, region",
    "文本批量查找替换，可选正则表达式": "Batch find & replace in text, with optional regex",
    "HTML 预览": "HTML preview",
    "HTML 实时预览，支持导入 .html 文件": "Live HTML preview, import .html files",
    "查看 / 清理 EXIF 隐私信息（拍摄时间、位置等）": "View / remove EXIF privacy data (date taken, location, etc.)",
    "MD5 / SHA1 / SHA2 / SHA3 / BLAKE2 / CRC32 计算与对比验证": "MD5 / SHA1 / SHA2 / SHA3 / BLAKE2 / CRC32 compute & verify",
    "2-36 任意进制互转（自动识别前缀 / 手动指定源进制）": "Convert between bases 2-36 (auto-detect prefix / manual source base)",
    "UTF-8 / GBK / BIG5 / Shift-JIS 等编码互转": "Convert between UTF-8 / GBK / BIG5 / Shift-JIS and more",
    "Markdown 预览": "Markdown preview",
    "Markdown 实时预览，支持导入 .md 文件": "Live Markdown preview, import .md files",
    "一张图切成 3x3 九张，带预览与打开输出目录": "Cut one image into a 3x3 grid, with preview & open output folder",
    "金额 / 数字转人民币大写": "Convert amounts / numbers to Chinese RMB uppercase",
    "JWT 解码器": "JWT decoder",
    "解析 JWT 的 Header / Payload（含过期时间）": "Parse JWT Header / Payload (incl. expiry)",
    "SQL 格式化": "SQL formatter",
    "美化 SQL：关键字换行缩进": "Beautify SQL: keyword line breaks & indentation",
    "左右对比两段文本，高亮差异行": "Compare two texts side by side, highlight changed lines",
    "时间戳与日期互转，支持秒/毫秒": "Timestamp ↔ date, seconds / milliseconds",
    "文本 ↔ 摩斯电码（字母/数字/标点）互转": "Text ↔ Morse code (letters / digits / punctuation)",
    "SRT / ASS / VTT 三向转换，自动识别源格式": "SRT / ASS / VTT cross-conversion, auto source detection",
    "实时测试正则表达式，高亮匹配结果": "Test regex live, highlight matches",
    "Unicode 编解码": "Unicode codec",
    "文本 ↔ \\uXXXX 转义（如 中 → \\u4e2d）": "Text ↔ \\uXXXX escapes (e.g. 中 → \\u4e2d)",
    "UUID 生成器": "UUID generator",
    "批量生成 UUID v1/v3/v4/v5 或随机密码（可选移除连字符）": "Batch UUID v1/v3/v4/v5 or random passwords (hyphens optional)",
    "IP 地址查询": "IP lookup",
    "本机 / 公网 IP，域名解析与反查（不卡界面）": "Local / public IP, DNS lookup & reverse (non-blocking)",
    "浏览器级渲染整页，导出所见即所得的 PDF": "Browser-level full-page render, export WYSIWYG PDF",
    "JSON YAML 转换": "JSON ↔ YAML converter",
    "JSON ↔ YAML 双向转换": "Convert between JSON and YAML both ways",
    "简繁转换": "Simplified ↔ Traditional",
    "简体 ↔ 繁体互转（opencc 词汇级 + 2314 常用字表）": "Convert between Simplified and Traditional (opencc word-level + 2314 common chars)",
    "字符 / 汉字 / 单词 / 行数 / 段落统计": "Chars / Chinese chars / words / lines / paragraphs",
    "URL 编解码": "URL codec",
    "URL / 文本编码解码（quote / unquote）": "Encode / decode URLs and text (quote / unquote)",
    "JSON 格式化": "JSON formatter",
    "JSON 美化 / 压缩 / 校验 / 树形视图": "JSON beautify / minify / validate / tree view",
    "按行去重 / 排序 / 忽略空行": "Dedupe lines / sort / skip empty lines",

    # ── 补充（拆段/新增文案）─────────────────────
    "已选择：": "Selected: ",
    "列 {n}": "Col {n}",
    "进制": "base",
    "无法解析（支持 2-36 进制，可带 0x/0b/0o 前缀）": "Cannot parse (bases 2-36, 0x/0b/0o prefixes allowed)",
    "✓ 哈希匹配！": "✓ Hash matched!",
    "✗ 不匹配": "✗ Not matched",
    "已过期": "Expired",
    "格式错误：JWT 应为三段 header.payload.signature": "Invalid format: JWT must be header.payload.signature",
    "GPS 信息": "GPS info",
    "X 分辨率": "X resolution",
    "Y 分辨率": "Y resolution",
    "ISO": "ISO",
    "（需密钥验证，此处仅解码展示）": "(requires the secret key, decoded for display only)",
    "解码成功": "Decoded",
    "文本一致": "Texts are identical",
    "文本完全一致": "Texts are completely identical",
    "已生成 PDF：{path}": "PDF generated: {path}",
    "PDF 生成失败": "PDF generation failed",
    "缺少 Pillow（pip install Pillow）": "Pillow missing (pip install Pillow)",
    "✓ 合法 JSON": "✓ Valid JSON",
    "JSON 解析失败：第 {lineno} 行 {msg}": "JSON parse failed: line {lineno} {msg}",
    "YAML 解析失败：{e}": "YAML parse failed: {e}",
    "已转换 {len(subs)} 条字幕 → {name}": "Converted {len(subs)} subtitles → {name}",
    "检测到 {fmt} 格式 · {count} 条字幕 · ": "Detected {fmt} · {count} subtitles · ",
    "· 文本一致": "· Texts are identical",
    "（文本完全一致）": "(texts are completely identical)",
}
