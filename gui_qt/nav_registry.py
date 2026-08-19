"""nav_registry — 导航注册真源（一次性规划全部 20+ 功能）。

每个条目：key / 显示名 / FluentIcon / 页面工厂 factory(window, services)。
已迁移的指向真实页面；未迁移的指向 PlaceholderPage（「即将上线」空态），
后续批次只需把 factory 替换为真实页面即可，不动导航结构。

双语约定（2026-08-19 修订）：
- NAV_GROUPS / GROUP_EN 统一存「中文原文」，渲染时经 label()/group_label()
  翻译——避免模块 import 时按语言固化（切语言后侧边栏不刷新）。
- EN_TEXTS 是侧边栏英文的唯一真源，key 与 NAV_GROUPS 完全同步。
"""
from qfluentwidgets import FluentIcon

from gui_qt.i18n import tr

# 条目英文名（key → English label；须与 NAV_GROUPS 中文一一对应）
EN_TEXTS = {
    "home": "Home", "video": "Video Convert", "audio": "Audio Convert",
    "image": "Image Convert", "document": "Document Convert",
    "gif": "GIF Convert", "pdf": "PDF tools", "pdf_editor": "PDF Editor",
    "ebook": "Ebook Convert",
    "video_edit": "Cover crop", "video_tools": "Video Tools",
    "video_compress": "Video Compress", "frame_extract": "Extract frames",
    "subtitle": "Subtitle", "video_unwarp": "Unwarp Video",
    "audio_edit": "Audio Tools", "audio_enhance": "Audio Enhance",
    "image_compress": "Image Compress", "watermark": "Watermark Tools",
    "id_photo": "ID Photo", "image_merge": "Image Merge",
    "ocr": "Advanced OCR", "table_ocr": "Table OCR",
    "format_detect": "Format Detect", "mediainfo": "Media Info",
    "qrcode": "QR Generate", "batch_rename": "Batch Rename",
    "monitor": "Folder Watch", "file_security": "File Security",
    "lan_transfer": "LAN Service", "plugins": "Plugins",
    "download": "Video Download", "m3u8": "M3U8 Download",
    "history": "History", "settings": "Settings",
}

# 分组英文名（中文原文 → English；渲染时按当前语言翻译）
GROUP_EN = {
    "首页": "Home", "转换中心": "Convert", "PDF工具": "PDF Tools",
    "视频工具": "Video Tools", "音频工具": "Audio Tools",
    "图片工具": "Image Tools", "识别工具": "Recognition",
    "实用工具": "Utilities", "网络下载": "Download", "管理中心": "Manage",
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


# 分组顺序即导航顺序；分组名会作为侧边栏小标题渲染（存中文原文，渲染时翻译）
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
        dict(key="ebook", text="电子书互转", icon=FluentIcon.LIBRARY,
             factory=_page("gui_qt.panels.ebook_panel", "EbookPanelPage")),
    ]),
    ("PDF工具", [
        dict(key="pdf", text="PDF处理", icon=FluentIcon.SCROLL,
             factory=_page("gui_qt.panels.pdf_panel", "PdfPanelPage")),
        dict(key="pdf_editor", text="PDF编辑", icon=FluentIcon.LIBRARY,
             factory=_page("gui_qt.panels.pdf_editor_panel", "PdfEditorPanelPage")),
    ]),
    ("视频工具", [
        dict(key="video_edit", text="封面裁剪", icon=FluentIcon.EDIT,
             factory=_page("gui_qt.panels.crop_panel", "CropPanelPage")),
        dict(key="video_tools", text="视频处理", icon=FluentIcon.SCROLL,
             factory=_page("gui_qt.panels.video_edit_panel", "VideoToolsPanelPage")),
        dict(key="video_compress", text="视频压缩", icon=FluentIcon.ZIP_FOLDER,
             factory=_page("gui_qt.panels.video_compress_panel", "VideoCompressPanelPage")),
        dict(key="frame_extract", text="视频抽帧", icon=FluentIcon.CAMERA,
             factory=_page("gui_qt.panels.video_frame_panel", "VideoFramePanelPage")),
        dict(key="subtitle", text="字幕提取", icon=FluentIcon.LANGUAGE,
             factory=_page("gui_qt.panels.subtitle_panel", "SubtitlePanelPage")),
        dict(key="video_unwarp", text="视频反挤压", icon=FluentIcon.MEDIA,
             factory=_page("gui_qt.panels.video_unwarp_panel", "VideoUnwarpPanelPage")),
    ]),
    ("音频工具", [
        dict(key="audio_edit", text="音频处理", icon=FluentIcon.MICROPHONE,
             factory=_page("gui_qt.panels.audio_trim_panel", "AudioTrimPanelPage")),
        dict(key="audio_enhance", text="音频增强", icon=FluentIcon.SPEAKERS,
             factory=_page("gui_qt.panels.audio_enhance_panel", "AudioEnhancePanelPage")),
    ]),
    ("图片工具", [
        dict(key="image_compress", text="图片压缩", icon=FluentIcon.ZIP_FOLDER,
             factory=_page("gui_qt.panels.compress_img_panel", "CompressImgPanelPage")),
        dict(key="watermark", text="水印处理", icon=FluentIcon.BRUSH,
             factory=_page("gui_qt.panels.watermark_panel", "WatermarkPanelPage")),
        dict(key="id_photo", text="证件照换底色", icon=FluentIcon.PEOPLE,
             factory=_page("gui_qt.panels.id_photo_panel", "IdPhotoPanelPage")),
        dict(key="image_merge", text="图片拼接", icon=FluentIcon.ALBUM,
             factory=_page("gui_qt.panels.image_merge_panel", "ImageMergePanelPage")),
    ]),
    ("识别工具", [
        dict(key="ocr", text="高级OCR", icon=FluentIcon.FONT,
             factory=_page("gui_qt.panels.ocr_panel", "OcrPanelPage")),
        dict(key="table_ocr", text="表格识别", icon=FluentIcon.TILES,
             factory=_page("gui_qt.panels.table_ocr_panel", "TableOcrPanelPage")),
        dict(key="format_detect", text="格式检测", icon=FluentIcon.SEARCH,
             factory=_page("gui_qt.panels.detect_panel", "DetectPanelPage")),
        dict(key="mediainfo", text="媒体信息", icon=FluentIcon.INFO,
             factory=_page("gui_qt.panels.mediainfo_panel", "MediaInfoPanelPage")),
    ]),
    ("实用工具", [
        dict(key="qrcode", text="二维码生成", icon=FluentIcon.QRCODE,
             factory=_page("gui_qt.panels.qrcode_panel", "QrcodePanelPage")),
        dict(key="batch_rename", text="批量重命名", icon=FluentIcon.EDIT,
             factory=_page("gui_qt.panels.batch_rename_panel", "BatchRenamePanelPage")),
        dict(key="monitor", text="文件夹监视", icon=FluentIcon.TILES,
             factory=_page("gui_qt.panels.monitor_panel", "MonitorPanelPage")),
        dict(key="file_security", text="文件安全工具", icon=FluentIcon.CERTIFICATE,
             factory=_page("gui_qt.panels.file_security_panel", "FileSecurityPanelPage")),
        dict(key="lan_transfer", text="局域网服务", icon=FluentIcon.SHARE,
             factory=_page("gui_qt.panels.lan_transfer_panel", "LanTransferPanelPage")),
        dict(key="plugins", text="插件中心", icon=FluentIcon.DEVELOPER_TOOLS,
             factory=_page("gui_qt.panels.plugin_panel", "PluginPanelPage")),
    ]),
    ("网络下载", [
        dict(key="download", text="视频下载", icon=FluentIcon.DOWNLOAD,
             factory=_page("gui_qt.panels.download_panel", "DownloadPanelPage")),
        dict(key="m3u8", text="M3U8下载", icon=FluentIcon.LINK,
             factory=_page("gui_qt.panels.m3u8_panel", "M3u8PanelPage")),
    ]),
    ("管理中心", [
        dict(key="history", text="转换历史", icon=FluentIcon.HISTORY,
             factory=_page("gui_qt.pages.history_page", "HistoryPage")),
        dict(key="settings", text="设置", icon=FluentIcon.SETTING,
             factory=_page("gui_qt.pages.settings_page", "SettingsPage")),
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
