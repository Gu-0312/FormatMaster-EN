"""nav_registry — 导航注册真源（一次性规划全部 20+ 功能）。

每个条目：key / 显示名 / FluentIcon / 页面工厂 factory(window, services)。
已迁移的指向真实页面；未迁移的指向 PlaceholderPage（「即将上线」空态），
后续批次只需把 factory 替换为真实页面即可，不动导航结构。
"""
from qfluentwidgets import FluentIcon

from gui_qt.i18n import tr

# 条目英文名（中英双语；key → English label）
EN_TEXTS = {
    "home": "Home", "video": "Video Convert", "audio": "Audio Convert",
    "image": "Image Convert", "document": "Document Convert",
    "gif": "GIF Convert", "pdf": "PDF Tools", "pdf_editor": "PDF Editor",
    "video_edit": "Crop Cover", "video_tools": "Video Tools",
    "audio_edit": "Audio Trim", "image_compress": "Image Compress",
    "watermark": "Watermark", "ocr": "OCR",
    "table_ocr": "Table OCR",
    "format_detect": "Format Detect", "thumbnails": "Thumbnails",
    "qrcode": "QR Code", "hash": "Hash Check",
    "batch_rename": "Batch Rename", "monitor": "Folder Watch",
    "download": "Video Download", "m3u8": "M3U8 Download",
    "tasks": "Tasks", "history": "History",
    "settings": "Settings", "about": "About",
}

# 分组英文名
GROUP_EN = {
    "首页": "Home", "转换中心": "Convert", "编辑处理": "Edit",
    "智能工具": "Tools", "网络下载": "Download", "管理中心": "Manage",
}


def label(item):
    """条目显示名（按当前语言）。"""
    en = EN_TEXTS.get(item["key"])
    return tr(item["text"], en) if en else item["text"]


def group_label(group):
    """分组显示名（按当前语言）。"""
    en = GROUP_EN.get(group)
    return tr(group, en) if en else group


def _ph(name):
    """未迁移功能的占位页工厂。"""
    def factory(window, services):
        from gui_qt.pages.placeholder_page import PlaceholderPage
        return PlaceholderPage(name, window, services)
    return factory


def _page(mod, cls):
    """真实页面工厂（延迟导入，避免循环依赖）。"""
    def factory(window, services):
        import importlib
        return getattr(importlib.import_module(mod), cls)(window, services)
    return factory


# 分组顺序即导航顺序；分组名会作为侧边栏小标题渲染
NAV_GROUPS = [
    ("首页", [
        dict(key="home", text="首页", icon=FluentIcon.HOME,
             factory=_page("gui_qt.pages.home_page", "HomePage")),
    ]),
    ("转换中心", [
        dict(key="video", text="视频转换", icon=FluentIcon.VIDEO,
             factory=_page("gui_qt.panels.video_panel", "VideoPanelPage")),
        dict(key="audio", text="音频转换", icon=FluentIcon.MUSIC,
             factory=_page("gui_qt.panels.audio_panel", "AudioPanelPage")),
        dict(key="image", text="图片转换", icon=FluentIcon.PHOTO,
             factory=_page("gui_qt.panels.image_panel", "ImagePanelPage")),
        dict(key="document", text="文档转换", icon=FluentIcon.DOCUMENT,
             factory=_page("gui_qt.panels.doc_panel", "DocPanelPage")),
        dict(key="gif", text="GIF转换", icon=FluentIcon.MOVIE,
             factory=_page("gui_qt.panels.gif_panel", "GifPanelPage")),
    ]),
    ("编辑处理", [
        dict(key="pdf", text="PDF处理", icon=FluentIcon.SCROLL,
             factory=_page("gui_qt.panels.pdf_panel", "PdfPanelPage")),
        dict(key="pdf_editor", text="PDF编辑", icon=FluentIcon.LIBRARY,
             factory=_page("gui_qt.panels.pdf_editor_panel", "PdfEditorPanelPage")),
        dict(key="video_edit", text="封面裁剪", icon=FluentIcon.EDIT,
             factory=_page("gui_qt.panels.crop_panel", "CropPanelPage")),
        dict(key="video_tools", text="视频处理", icon=FluentIcon.SCROLL,
             factory=_page("gui_qt.panels.video_edit_panel", "VideoToolsPanelPage")),
        dict(key="audio_edit", text="音频处理", icon=FluentIcon.MICROPHONE,
             factory=_page("gui_qt.panels.audio_trim_panel", "AudioTrimPanelPage")),
        dict(key="image_compress", text="图片压缩", icon=FluentIcon.ZIP_FOLDER,
             factory=_page("gui_qt.panels.compress_img_panel", "CompressImgPanelPage")),
        dict(key="watermark", text="水印处理", icon=FluentIcon.BRUSH,
             factory=_page("gui_qt.panels.watermark_panel", "WatermarkPanelPage")),
    ]),
    ("智能工具", [
        dict(key="ocr", text="OCR识别", icon=FluentIcon.FONT,
             factory=_page("gui_qt.panels.ocr_panel", "OcrPanelPage")),
        dict(key="table_ocr", text="表格识别", icon=FluentIcon.TILES,
             factory=_page("gui_qt.panels.table_ocr_panel", "TableOcrPanelPage")),
        dict(key="format_detect", text="格式检测", icon=FluentIcon.SEARCH,
             factory=_page("gui_qt.panels.detect_panel", "DetectPanelPage")),
        dict(key="thumbnails", text="视频缩略图", icon=FluentIcon.TILES,
             factory=_page("gui_qt.panels.thumbnail_panel", "ThumbnailPanelPage")),
        dict(key="qrcode", text="二维码生成", icon=FluentIcon.QRCODE,
             factory=_page("gui_qt.panels.qrcode_panel", "QrcodePanelPage")),
        dict(key="hash", text="哈希校验", icon=FluentIcon.FINGERPRINT,
             factory=_page("gui_qt.panels.hash_panel", "HashPanelPage")),
        dict(key="batch_rename", text="批量重命名", icon=FluentIcon.EDIT,
             factory=_page("gui_qt.panels.batch_rename_panel", "BatchRenamePanelPage")),
        dict(key="monitor", text="文件夹监视", icon=FluentIcon.TILES,
             factory=_page("gui_qt.panels.monitor_panel", "MonitorPanelPage")),
    ]),
    ("网络下载", [
        dict(key="download", text="视频下载", icon=FluentIcon.DOWNLOAD,
             factory=_page("gui_qt.panels.download_panel", "DownloadPanelPage")),
        dict(key="m3u8", text="M3U8下载", icon=FluentIcon.LINK,
             factory=_page("gui_qt.panels.m3u8_panel", "M3u8PanelPage")),
    ]),
    ("管理中心", [
        dict(key="tasks", text="任务中心", icon=FluentIcon.CHECKBOX,
             factory=_page("gui_qt.pages.task_page", "TaskPage")),
        dict(key="history", text="转换历史", icon=FluentIcon.HISTORY,
             factory=_page("gui_qt.pages.history_page", "HistoryPage")),
        dict(key="settings", text="设置", icon=FluentIcon.SETTING,
             factory=_page("gui_qt.pages.settings_page", "SettingsPage")),
        dict(key="about", text="关于", icon=FluentIcon.INFO,
             factory=_page("gui_qt.pages.about_page", "AboutPage")),
    ]),
]


def all_items():
    """扁平化全部条目。"""
    for _, items in NAV_GROUPS:
        yield from items


def find_item(key):
    for item in all_items():
        if item["key"] == key:
            return item
    return None
