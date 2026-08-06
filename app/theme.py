"""Design Tokens - Soft Boutique SaaS Style

主题色彩令牌与字体常量，从 main.py 提取。
D 为可变字典，运行时会被暗色主题代码覆盖（D[k] = v）。
设计方向：柔和精品 SaaS 风 —— 暖白底 + 白色描边卡片 + 电光蓝点缀，
参考 Notion / Stripe 后台的现代轻量视觉语言（8pt 网格、大圆角、呼吸感留白）。
"""

D = {
    "page":         "#FAFAFA",
    "card":         "#FFFFFF",
    "card_alt":     "#F5F7FA",
    "sidebar":      "#FFFFFF",
    "sidebar_sel":  "#EEF4FF",
    "accent":       "#0052FF",
    "accent_soft":  "#4D7CFF",
    "accent_pale":  "#EEF4FF",
    "accent_deep":  "#0040CC",
    "ink":          "#0F172A",
    "ink_sec":      "#64748B",
    "ink_dis":      "#94A3B8",
    "ink_inv":      "#FFFFFF",
    "border":       "#E2E8F0",
    "border_hi":    "#CBD5E1",
    "divider":      "#F1F5F9",
    "ok":           "#22C55E",
    "warn":         "#F59E0B",
    "err":          "#EF4444",
    "success":      "#22C55E",
    "error":        "#DC2626",
    "toast_success":"#16A34A",
    "toast_error":  "#DC2626",
    "input_bg":     "#FFFFFF",
    "input_bd":     "#E2E8F0",
    "input_focus":  "#0052FF",
    "prog_trough":  "#F1F5F9",
    "prog_fill":    "#0052FF",
    "select_bg":    "#EEF4FF",
    "select_fg":    "#0047E0",
    "select_bold":  "#0033A8",
    # ── Soft UI / Bento Grid 扩展令牌 ──
    "card_hover":     "#F8FAFF",   # 卡片 hover 态（比 card 略带蓝调）
    "card_active":    "#EEF4FF",   # 卡片点击态
    "shadow_outer":   "#EDF1F8",   # 柔和外层边框（比 border 更淡）
    "shadow_inner":   "#F8FAFC",   # 柔和内层背景
    "hero_gradient":  "#EEF4FF",   # Hero 卡片浅蓝底
    # Bento 分组色系（色块标记 + hover 高亮）
    "group_media":    "#0052FF",   # 格式转换组（电光蓝）
    "group_media_bg": "#EEF4FF",
    "group_edit":     "#7C3AED",   # 编辑处理组（紫）
    "group_edit_bg":  "#F3E8FF",
    "group_tool":     "#059669",   # 智能工具组（青绿）
    "group_tool_bg":  "#D1FAE5",
    "group_net":      "#EA580C",   # 网络下载组（橙）
    "group_net_bg":   "#FFF3E0",
}

D_LIGHT = dict(D)

D_DARK = {
    "page":         "#0D1220",
    "card":         "#151B2E",
    "card_alt":     "#1B2340",
    "sidebar":      "#111728",
    "sidebar_sel":  "#1A2444",
    "accent":       "#4D7CFF",
    "accent_soft":  "#6B93FF",
    "accent_pale":  "#1D2A52",
    "accent_deep":  "#2F5FE0",
    "ink":          "#E7ECF6",
    "ink_sec":      "#9AA7C0",
    "ink_dis":      "#5E6C88",
    "ink_inv":      "#FFFFFF",
    "border":       "#232D4E",
    "border_hi":    "#33406B",
    "divider":      "#1B2340",
    "ok":           "#22C55E",
    "warn":         "#F59E0B",
    "err":          "#EF4444",
    "success":      "#22C55E",
    "error":        "#F87171",
    "toast_success":"#16A34A",
    "toast_error":  "#DC2626",
    "input_bg":     "#101628",
    "input_bd":     "#26314F",
    "input_focus":  "#4D7CFF",
    "prog_trough":  "#232D4E",
    "prog_fill":    "#4D7CFF",
    "select_bg":    "#1D2A52",
    "select_fg":    "#8FA9FF",
    "select_bold":  "#B3C6FF",
    # ── Soft UI / Bento Grid 扩展令牌 ──
    "card_hover":     "#1A2340",
    "card_active":    "#1D2A52",
    "shadow_outer":   "#1B2340",
    "shadow_inner":   "#111728",
    "hero_gradient":  "#1D2A52",
    "group_media":    "#4D7CFF",
    "group_media_bg": "#1D2A52",
    "group_edit":     "#A78BFA",
    "group_edit_bg":  "#2A2050",
    "group_tool":     "#34D399",
    "group_tool_bg":  "#0D2A20",
    "group_net":      "#FB923C",
    "group_net_bg":   "#2A1A0A",
}

# 字体
FT  = "Microsoft YaHei UI"
DISPLAY = (FT, 22, "bold")
H2      = (FT, 14, "bold")
BODY    = (FT, 10)
BODY_B  = (FT, 10, "bold")
SM      = (FT, 9)
XS      = (FT, 8)
NAV     = (FT, 10)
NAV_B   = (FT, 10, "bold")
BTN     = (FT, 10, "bold")

# 字体字典（供统一按名引用）
FONTS = {
    "display":  DISPLAY,
    "h2":       H2,
    "card_hdr": (FT, 11, "bold"),
    "body":     BODY,
    "nav":      NAV,
    "nav_b":    NAV_B,
    "btn":      BTN,
    "small":    SM,
    "caption":  XS,
    "badge":    (FT, 8, "bold"),
    # ── Bento Grid 扩展字号 ──
    "hero_title":   (FT, 24, "bold"),
    "stat_value":   (FT, 28, "bold"),
    "bento_label":  (FT, 11, "bold"),
}

# 间距令牌（8pt 网格，柔和 SaaS 风：更大留白与圆角）
SPACING = {
    "xs":          4,
    "sm":          8,
    "md":          12,
    "lg":          24,
    "card_pad_x":  20,
    "card_pad_y":  16,
    "card_radius": 12,
    "col_gap":     16,
    "row_gap":     12,
    "section_gap": 16,
    "bento_pad_x":   12,    # Bento 卡片内边距
    "bento_pad_y":   14,
    "bento_gap":     8,     # Bento 网格间距
    # 底部任务/日志/历史 Dock 统一间距
    "dock_pad_x":      12,
    "dock_head_pad_y": 6,
    "dock_inner_pad_y": 12,
}
