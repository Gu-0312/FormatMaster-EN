"""i18n — 轻量中英双语（无外部依赖，字典式 tr）。

语言由设置页偏好（services pref "language"，值 zh/en）控制，
重启应用后生效。核心界面（导航/新增面板/设置/首页）走 tr() 双语，
其余面板可渐进迁移。
"""
_LANG = "zh"


def set_language(lang):
    """设置当前语言（"zhtr(" 或 ", " or ")en"）。"""
    global _LANG
    _LANG = "en" if str(lang or "").lower().startswith("en") else "zh"


def current():
    return _LANG


def is_en():
    return _LANG == "en"


def tr(zh, en):
    """按当前语言返回 zh / en 文案。"""
    return en if _LANG == "en" else zh
