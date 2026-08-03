"""Design Tokens - Modern Flat Style

主题色彩令牌与字体常量，从 main.py 提取。
D 为可变字典，运行时会被暗色主题代码覆盖（D[k] = v）。
"""

D = {
    "page":         "#F5F6FA",
    "card":         "#FFFFFF",
    "card_alt":     "#FAFBFC",
    "sidebar":      "#FFFFFF",
    "sidebar_sel":  "#F0F1F5",
    "accent":       "#F05A42",
    "accent_soft":  "#FF7B69",
    "accent_pale":  "#FFF1EF",
    "accent_deep":  "#D04532",
    "ink":          "#1A1A2E",
    "ink_sec":      "#6B7280",
    "ink_dis":      "#9CA3AF",
    "ink_inv":      "#FFFFFF",
    "border":       "#E5E7EB",
    "border_hi":    "#D1D5DB",
    "divider":      "#F3F4F6",
    "ok":           "#10B981",
    "warn":         "#F59E0B",
    "err":          "#EF4444",
    "input_bg":     "#FFFFFF",
    "input_bd":     "#E5E7EB",
    "input_focus":  "#F05A42",
    "prog_trough":  "#E5E7EB",
    "prog_fill":    "#F05A42",
    "select_bg":    "#FDDBD6",
    "select_fg":    "#C0392B",
    "select_bold":  "#A83228",
}

D_LIGHT = dict(D)

D_DARK = {
    "page":         "#1E1E2E",
    "card":         "#2A2A3C",
    "card_alt":     "#323248",
    "sidebar":      "#252536",
    "sidebar_sel":  "#323248",
    "accent":       "#F05A42",
    "accent_soft":  "#FF7B69",
    "accent_pale":  "#3D2A28",
    "accent_deep":  "#D04532",
    "ink":          "#E4E4E7",
    "ink_sec":      "#A1A1AA",
    "ink_dis":      "#71717A",
    "ink_inv":      "#FFFFFF",
    "border":       "#3F3F50",
    "border_hi":    "#525266",
    "divider":      "#323248",
    "ok":           "#22C55E",
    "warn":         "#F59E0B",
    "err":          "#EF4444",
    "input_bg":     "#1A1A2E",
    "input_bd":     "#3F3F50",
    "input_focus":  "#F05A42",
    "prog_trough":  "#3F3F50",
    "prog_fill":    "#F05A42",
    "select_bg":    "#3D2A28",
    "select_fg":    "#FF7B69",
    "select_bold":  "#FF7B69",
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
