"""自定义 Combobox 下拉列表样式 - Hover 深蓝 + Active 橙色"""
import tkinter as tk


# ── 下拉列表配色 ──
_POPUP_BG = "#FFFFFF"
_POPUP_FG = "#1A1A2E"
_HOVER_BG = "#1e40af"
_HOVER_FG = "#FFFFFF"
_ACTIVE_BG = "#ea580c"
_ACTIVE_FG = "#FFFFFF"
_FONT = ("Microsoft YaHei UI", 10)


def style_combobox(combobox):
    """给 ttk.Combobox 绑定自定义下拉列表，支持 Hover 深蓝 + Active 橙色"""

    _popup = [None]
    _listbox = [None]
    _active_idx = [-1]
    _values = [list(combobox.cget("values")) if combobox.cget("values") else []]

    def _open(e=None):
        _close()
        vals = combobox.cget("values")
        if not vals:
            return
        _values[0] = list(vals)

        # 计算位置
        x = combobox.winfo_rootx()
        y = combobox.winfo_rooty() + combobox.winfo_height()
        w = combobox.winfo_width()

        # 限制高度
        n = len(_values[0])
        row_h = 28
        max_h = min(n * row_h + 4, 400)

        # 超出屏幕底部则向上弹出
        screen_h = combobox.winfo_screenheight()
        if y + max_h > screen_h - 60:
            y = combobox.winfo_rooty() - max_h

        pop = tk.Toplevel(combobox)
        pop.wm_overrideredirect(True)
        pop.wm_geometry(f"{w}x{max_h}+{x}+{y}")
        pop.configure(bg="#D1D5DB", bd=0, highlightthickness=0)

        lb = tk.Listbox(pop, font=_FONT, bg=_POPUP_BG, fg=_POPUP_FG,
                         selectbackground=_ACTIVE_BG, selectforeground=_ACTIVE_FG,
                         activestyle="none", relief="flat", bd=0,
                         highlightthickness=0, selectborderwidth=0)
        lb.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        for v in _values[0]:
            lb.insert(tk.END, v)

        # 选中当前值
        cur = combobox.get()
        if cur in _values[0]:
            idx = _values[0].index(cur)
            lb.selection_set(idx)
            lb.see(idx)

        _popup[0] = pop
        _listbox[0] = lb
        _active_idx[0] = -1

        lb.bind("<Motion>", _on_hover)
        lb.bind("<ButtonRelease-1>", _on_select)
        lb.bind("<Leave>", _on_leave)
        pop.bind("<Escape>", lambda e: _close())

        # 延迟绑定全局关闭，避免自身点击触发关闭
        pop.after(50, lambda: combobox.bind_all("<Button-1>", _global_close))

    def _close():
        if _popup[0] and _popup[0].winfo_exists():
            _popup[0].destroy()
        _popup[0] = None
        _listbox[0] = None
        _active_idx[0] = -1
        try:
            combobox.unbind_all("<Button-1>")
        except Exception:
            pass

    def _global_close(event):
        w = event.widget
        try:
            if _popup[0] and _popup[0].winfo_exists():
                w_str = str(w)
                p_str = str(_popup[0])
                if w != _popup[0] and w != _listbox[0] and not w_str.startswith(p_str):
                    _close()
        except Exception:
            _close()

    def _on_hover(event):
        lb = _listbox[0]
        if not lb:
            return
        idx = lb.nearest(event.y)
        if idx == _active_idx[0]:
            return
        # 恢复上一个
        old = _active_idx[0]
        if 0 <= old < len(_values[0]):
            lb.itemconfig(old, bg=_POPUP_BG, fg=_POPUP_FG)
        # 悬停项 → 深蓝
        if 0 <= idx < len(_values[0]):
            lb.itemconfig(idx, bg=_HOVER_BG, fg=_HOVER_FG)
            _active_idx[0] = idx

    def _on_leave(event):
        lb = _listbox[0]
        if not lb:
            return
        old = _active_idx[0]
        if 0 <= old < len(_values[0]):
            lb.itemconfig(old, bg=_POPUP_BG, fg=_POPUP_FG)
        _active_idx[0] = -1

    def _on_select(event):
        lb = _listbox[0]
        if not lb:
            return
        idx = lb.nearest(event.y)
        if 0 <= idx < len(_values[0]):
            combobox.set(_values[0][idx])
            # 触发 ComboboxSelected 事件
            combobox.event_generate("<<ComboboxSelected>>")
        _close()

    # 替换原生下拉：移除 Tcl 级绑定，绑定自定义弹出
    try:
        combobox.tk.call('bind', combobox._w, '<Button-1>', '')
    except Exception:
        pass
    combobox.bind("<Button-1>", _open)
    combobox.bind("<Return>", _open)
    combobox.bind("<space>", _open)
    combobox.bind("<Escape>", lambda e: _close())

    # 暴露关闭方法
    combobox._styled_close = _close
