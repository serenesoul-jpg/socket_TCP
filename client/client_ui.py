#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCP 文件传输 GUI：CustomTkinter 界面，网络 I/O 运行于子线程。"""

import os
import threading
from tkinter import filedialog, messagebox
from typing import Dict, List, Optional

import customtkinter as ctk

from tcp_client import TcpFileClient

_PALETTE = {
    "light": {
        "bg": "#eef2f7",
        "surface": "#ffffff",
        "panel": "#f8fafc",
        "border": "#e2e8f0",
        "text": "#0f172a",
        "muted": "#94a3b8",
        "primary": "#4f46e5",
        "primary_hover": "#4338ca",
        "primary_soft": "#eef2ff",
        "success": "#10b981",
        "success_soft": "#ecfdf5",
        "warn": "#f59e0b",
        "warn_soft": "#fffbeb",
        "danger": "#ef4444",
        "danger_soft": "#fef2f2",
        "track": "#e2e8f0",
    },
    "dark": {
        "bg": "#0f172a",
        "surface": "#1e293b",
        "panel": "#273449",
        "border": "#334155",
        "text": "#f1f5f9",
        "muted": "#94a3b8",
        "primary": "#818cf8",
        "primary_hover": "#a5b4fc",
        "primary_soft": "#3730a3",
        "success": "#34d399",
        "success_soft": "#064e3b",
        "warn": "#fbbf24",
        "warn_soft": "#78350f",
        "danger": "#f87171",
        "danger_soft": "#7f1d1d",
        "track": "#334155",
    },
}


class FileTransferApp(ctk.CTk):
    """主窗口：简约商务风，网络 I/O 在子线程执行。"""

    def __init__(self) -> None:
        super().__init__()

        self._appearance = "light"
        self._remote_files: List[Dict[str, int]] = []
        self._selected_local: str = ""
        self._selected_remote: str = ""
        self._selected_remote_idx: Optional[int] = None
        self._file_row_frames: List[ctk.CTkFrame] = []
        self._busy = False

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title("TCP 文件传输")
        self.geometry("1020x680")
        self.minsize(900, 580)

        self.client = TcpFileClient(
            on_log=self._append_log,
            on_progress=self._update_progress,
            on_auth_result=self._on_auth_result,
            on_file_list=self._on_file_list,
            on_transfer_done=self._on_transfer_done,
            on_error=self._on_error,
        )

        self._build_ui()
        self._apply_theme()

    def _palette(self) -> Dict[str, str]:
        key = self._appearance
        if key == "system":
            key = "dark" if ctk.get_appearance_mode() == "Dark" else "light"
        return _PALETTE[key]

    def _font_title(self) -> ctk.CTkFont:
        return ctk.CTkFont(family="Microsoft YaHei UI", size=16, weight="bold")

    def _font_caption(self) -> ctk.CTkFont:
        return ctk.CTkFont(family="Microsoft YaHei UI", size=11)

    def _font_body(self) -> ctk.CTkFont:
        return ctk.CTkFont(family="Microsoft YaHei UI", size=12)

    def _font_log(self) -> ctk.CTkFont:
        # 日志以中文为主，用雅黑比等宽英文字体更易读
        return ctk.CTkFont(family="Microsoft YaHei UI", size=12)

    def _fmt_size(self, size: int) -> str:
        if size < 1024:
            return f"{size} B"
        kb = size / 1024
        if kb < 1024:
            return f"{kb:.1f} KB"
        return f"{kb / 1024:.2f} MB"

    def _run_on_ui(self, func) -> None:
        self.after(0, func)

    def _panel(self, parent, **kw) -> ctk.CTkFrame:
        p = self._palette()
        defaults = dict(
            corner_radius=10,
            fg_color=p["panel"],
            border_width=1,
            border_color=p["border"],
        )
        defaults.update(kw)
        return ctk.CTkFrame(parent, **defaults)

    def _field_label(self, parent, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent, text=text, font=self._font_caption(),
            text_color=self._palette()["muted"], width=44, anchor="e",
        )

    def _entry(self, parent, **kw) -> ctk.CTkEntry:
        p = self._palette()
        defaults = dict(
            height=34, corner_radius=8, font=self._font_body(),
            border_width=1, border_color=p["border"],
            fg_color=p["surface"],
        )
        defaults.update(kw)
        return ctk.CTkEntry(parent, **defaults)

    def _btn_primary(self, parent, text: str, cmd, width: int = 76) -> ctk.CTkButton:
        p = self._palette()
        return ctk.CTkButton(
            parent, text=text, command=cmd, width=width, height=34,
            corner_radius=8, font=self._font_body(),
            fg_color=p["primary"], hover_color=p["primary_hover"],
        )

    def _btn_secondary(self, parent, text: str, cmd, width: int = 76) -> ctk.CTkButton:
        p = self._palette()
        return ctk.CTkButton(
            parent, text=text, command=cmd, width=width, height=34,
            corner_radius=8, font=self._font_body(),
            fg_color="transparent", hover_color=p["border"],
            text_color=p["text"], border_width=1, border_color=p["border"],
        )

    def _btn_danger_outline(self, parent, text: str, cmd, width: int = 76) -> ctk.CTkButton:
        p = self._palette()
        return ctk.CTkButton(
            parent, text=text, command=cmd, width=width, height=34,
            corner_radius=8, font=self._font_body(),
            fg_color="transparent", hover_color=p["danger_soft"],
            text_color=p["danger"], border_width=1, border_color=p["danger"],
        )

    def _badge(self, parent, text: str) -> ctk.CTkLabel:
        p = self._palette()
        return ctk.CTkLabel(
            parent, text=text, font=self._font_caption(),
            text_color=p["muted"], fg_color=p["panel"],
            corner_radius=12, height=26, padx=10,
        )

    # ── 构建界面 ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=3)
        self.grid_rowconfigure(5, weight=2)

        self._build_header()
        self._build_session_bar()
        self._build_file_area()
        self._build_progress_strip()
        self._build_log_area()

        self._append_log("已启动 · 连接 127.0.0.1:8082 后登录")

    def _build_header(self) -> None:
        p = _PALETTE["light"]
        self._header = ctk.CTkFrame(self, fg_color=p["surface"], corner_radius=0, height=56)
        self._header.grid(row=0, column=0, sticky="ew")
        self._header.grid_columnconfigure(1, weight=1)
        self._header.grid_propagate(False)

        left = ctk.CTkFrame(self._header, fg_color="transparent")
        left.grid(row=0, column=0, padx=20, sticky="w")

        self._brand_icon = ctk.CTkLabel(
            left, text="FT", width=38, height=38, corner_radius=10,
            fg_color=p["primary"], text_color="#fff",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._brand_icon.grid(row=0, column=0, rowspan=2, padx=(0, 12))

        self._title_lbl = ctk.CTkLabel(
            left, text="TCP 文件传输", font=self._font_title(), text_color=p["text"],
        )
        self._title_lbl.grid(row=0, column=1, sticky="sw")
        self._port_hint = ctk.CTkLabel(
            left, text="Socket · FTCP · 8082", font=self._font_caption(), text_color=p["muted"],
        )
        self._port_hint.grid(row=1, column=1, sticky="nw")

        right = ctk.CTkFrame(self._header, fg_color="transparent")
        right.grid(row=0, column=2, padx=20, sticky="e")

        self._lbl_conn_status = self._badge(right, "未连接")
        self._lbl_conn_status.pack(side="left", padx=(0, 8))
        self._lbl_auth_status = self._badge(right, "未登录")
        self._lbl_auth_status.pack(side="left", padx=(0, 14))

        self._theme_seg = ctk.CTkSegmentedButton(
            right, values=["浅色", "深色"],
            command=self._on_theme_seg, height=30, corner_radius=8,
            font=self._font_caption(),
        )
        self._theme_seg.pack(side="left")
        self._theme_seg.set("浅色")

        self._header_line = ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=p["border"])
        self._header_line.grid(row=1, column=0, sticky="ew")

    def _build_session_bar(self) -> None:
        self._session_bar = ctk.CTkFrame(self, fg_color="transparent")
        self._session_bar.grid(row=2, column=0, padx=20, pady=(14, 10), sticky="ew")
        self._session_bar.grid_columnconfigure(5, weight=1)
        self._session_bar.grid_columnconfigure(11, weight=1)

        # 连接区
        self._field_label(self._session_bar, "IP").grid(row=0, column=0, padx=(0, 6))
        self.entry_host = self._entry(self._session_bar)
        self.entry_host.grid(row=0, column=1, sticky="ew")
        self.entry_host.insert(0, "127.0.0.1")

        self._field_label(self._session_bar, "端口").grid(row=0, column=2, padx=(12, 6))
        self.entry_port = self._entry(self._session_bar, width=68)
        self.entry_port.grid(row=0, column=3)
        self.entry_port.insert(0, "8082")

        self.btn_connect = self._btn_primary(self._session_bar, "连接", self._on_connect)
        self.btn_connect.grid(row=0, column=4, padx=(12, 4))
        self.btn_disconnect = self._btn_secondary(self._session_bar, "断开", self._on_disconnect)
        self.btn_disconnect.grid(row=0, column=5, padx=4, sticky="w")

        ctk.CTkFrame(self._session_bar, width=1, height=28, fg_color=_PALETTE["light"]["border"]).grid(
            row=0, column=6, padx=16
        )

        # 登录区
        self._field_label(self._session_bar, "用户名").grid(row=0, column=7, padx=(0, 6))
        self.entry_user = self._entry(self._session_bar)
        self.entry_user.grid(row=0, column=8, sticky="ew")
        self.entry_user.insert(0, "admin")

        self._field_label(self._session_bar, "密码").grid(row=0, column=9, padx=(12, 6))
        self.entry_pass = self._entry(self._session_bar, show="*")
        self.entry_pass.grid(row=0, column=10, sticky="ew")
        self.entry_pass.insert(0, "admin123")

        self.btn_login = self._btn_primary(self._session_bar, "登录", self._on_login)
        self.btn_login.grid(row=0, column=11, padx=(12, 0), sticky="e")

    def _build_file_area(self) -> None:
        self._file_outer = ctk.CTkFrame(self, fg_color="transparent")
        self._file_outer.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="nsew")
        self._file_outer.grid_columnconfigure(0, weight=3)
        self._file_outer.grid_columnconfigure(1, weight=2)
        self._file_outer.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(self._file_outer, fg_color="transparent")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._file_title = ctk.CTkLabel(
            toolbar, text="文件", font=self._font_body(), text_color=self._palette()["text"],
        )
        self._file_title.pack(side="left")

        btns = ctk.CTkFrame(toolbar, fg_color="transparent")
        btns.pack(side="right")
        self.btn_refresh = self._btn_secondary(btns, "刷新", self._on_refresh_list, 68)
        self.btn_refresh.pack(side="left", padx=(0, 6))
        self.btn_upload = self._btn_primary(btns, "上传", self._on_upload, 68)
        self.btn_upload.pack(side="left", padx=3)
        self.btn_download = self._btn_secondary(btns, "下载", self._on_download, 68)
        self.btn_download.pack(side="left", padx=3)
        self.btn_delete = self._btn_danger_outline(btns, "删除", self._on_delete, 68)
        self.btn_delete.pack(side="left", padx=3)

        # 远端列表
        self._remote_panel = self._panel(self._file_outer)
        self._remote_panel.grid(row=1, column=0, padx=(0, 6), sticky="nsew")
        self._remote_panel.grid_columnconfigure(0, weight=1)
        self._remote_panel.grid_rowconfigure(1, weight=1)

        self._remote_hdr = ctk.CTkLabel(
            self._remote_panel, text="远端", font=self._font_caption(),
            text_color=self._palette()["muted"], anchor="w",
        )
        self._remote_hdr.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self._remote_scroll = ctk.CTkScrollableFrame(
            self._remote_panel, fg_color="transparent", corner_radius=0,
        )
        self._remote_scroll.grid(row=1, column=0, padx=6, pady=(0, 8), sticky="nsew")
        self._remote_scroll.grid_columnconfigure(0, weight=1)

        self._remote_empty_icon = ctk.CTkLabel(
            self._remote_scroll, text="☁", font=ctk.CTkFont(size=26),
            text_color=self._palette()["muted"],
        )
        self._remote_empty_icon.grid(row=0, column=0, pady=(28, 4))
        self._remote_empty = ctk.CTkLabel(
            self._remote_scroll, text="登录后刷新列表",
            font=self._font_caption(), text_color=self._palette()["muted"],
        )
        self._remote_empty.grid(row=1, column=0)

        # 本地选择
        self._local_panel = self._panel(self._file_outer)
        self._local_panel.grid(row=1, column=1, padx=(6, 0), sticky="nsew")
        self._local_panel.grid_columnconfigure(0, weight=1)
        self._local_panel.grid_rowconfigure(1, weight=1)

        self._local_hdr = ctk.CTkLabel(
            self._local_panel, text="本地", font=self._font_caption(),
            text_color=self._palette()["muted"], anchor="w",
        )
        self._local_hdr.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self._local_inner = ctk.CTkFrame(self._local_panel, fg_color="transparent")
        self._local_inner.grid(row=1, column=0, padx=12, pady=(4, 12), sticky="nsew")
        self._local_inner.grid_columnconfigure(0, weight=1)

        self._local_icon = ctk.CTkLabel(
            self._local_inner, text="📄", font=ctk.CTkFont(size=30),
            text_color=self._palette()["muted"],
        )
        self._local_icon.grid(row=0, column=0, pady=(20, 6))
        self.lbl_local = ctk.CTkLabel(
            self._local_inner, text="选择要上传的文件",
            font=self._font_body(), text_color=self._palette()["muted"],
            wraplength=240, justify="center",
        )
        self.lbl_local.grid(row=1, column=0)
        self._local_size = ctk.CTkLabel(
            self._local_inner, text="",
            font=self._font_caption(), text_color=self._palette()["muted"],
        )
        self._local_size.grid(row=2, column=0, pady=(4, 10))
        self.btn_browse = self._btn_secondary(self._local_inner, "选择文件", self._on_browse_local, 100)
        self.btn_browse.grid(row=3, column=0, pady=(0, 16))

    def _build_progress_strip(self) -> None:
        p = self._palette()
        self._progress_outer = self._panel(self)
        self._progress_outer.grid(row=4, column=0, padx=20, pady=(0, 8), sticky="ew")
        self._progress_outer.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(self._progress_outer, fg_color="transparent")
        head.grid(row=0, column=0, padx=12, pady=(10, 6), sticky="ew")
        head.grid_columnconfigure(1, weight=1)

        self._progress_lbl = ctk.CTkLabel(
            head, text="传输进度", font=self._font_caption(),
            text_color=p["muted"], anchor="w",
        )
        self._progress_lbl.grid(row=0, column=0, sticky="w")

        self.lbl_progress = ctk.CTkLabel(
            head, text="空闲", font=self._font_caption(),
            text_color=p["muted"], anchor="e",
        )
        self.lbl_progress.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(
            self._progress_outer, height=10, corner_radius=5,
            progress_color=p["primary"], fg_color=p["track"],
        )
        self.progress_bar.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.progress_bar.set(0)

    def _build_log_area(self) -> None:
        self._log_panel = self._panel(self)
        self._log_panel.grid(row=5, column=0, padx=20, pady=(0, 16), sticky="nsew")
        self._log_panel.grid_columnconfigure(0, weight=1)
        self._log_panel.grid_rowconfigure(1, weight=1)

        self._log_hdr = ctk.CTkLabel(
            self._log_panel, text="日志", font=self._font_caption(),
            text_color=self._palette()["muted"], anchor="w",
        )
        self._log_hdr.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        self.txt_log = ctk.CTkTextbox(
            self._log_panel, font=self._font_log(), corner_radius=8,
            fg_color="transparent", border_width=0, activate_scrollbars=True,
            wrap="word", spacing1=2, spacing2=2,
        )
        self.txt_log.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.txt_log.configure(state="disabled")

    # ── 主题 ──────────────────────────────────────────────

    def _apply_theme(self) -> None:
        p = self._palette()
        self.configure(fg_color=p["bg"])
        self._header.configure(fg_color=p["surface"])
        self._header_line.configure(fg_color=p["border"])
        self._title_lbl.configure(text_color=p["text"])
        self._port_hint.configure(text_color=p["muted"])
        self._brand_icon.configure(fg_color=p["primary"])
        self._file_title.configure(text_color=p["text"])

        for panel in (self._remote_panel, self._local_panel, self._progress_outer, self._log_panel):
            panel.configure(fg_color=p["panel"], border_color=p["border"])

        for hdr in (self._remote_hdr, self._local_hdr, self._log_hdr, self._progress_lbl):
            hdr.configure(text_color=p["muted"])

        self.progress_bar.configure(progress_color=p["primary"], fg_color=p["track"])

        for entry in (self.entry_host, self.entry_port, self.entry_user, self.entry_pass):
            entry.configure(fg_color=p["surface"], border_color=p["border"])

        self._remote_empty_icon.configure(text_color=p["muted"])
        self._remote_empty.configure(text_color=p["muted"])
        self._local_icon.configure(text_color=p["muted"])
        if not self._selected_local:
            self.lbl_local.configure(text_color=p["muted"])
        self._local_size.configure(text_color=p["muted"])

        self._refresh_file_row_styles()
        self._update_status_badges()

    def _on_theme_seg(self, value: str) -> None:
        mode = "dark" if value == "深色" else "light"
        self._appearance = mode
        ctk.set_appearance_mode(mode)
        self._apply_theme()

    def _on_ui_style_change(self, style_name: str) -> None:
        pass  # 兼容旧接口

    def _on_theme_change(self, mode: str) -> None:
        self._appearance = mode
        ctk.set_appearance_mode(mode)
        self._apply_theme()

    # ── 文件列表 ──────────────────────────────────────────────

    def _clear_remote_list(self) -> None:
        for row in self._file_row_frames:
            row.destroy()
        self._file_row_frames.clear()
        self._selected_remote_idx = None
        self._selected_remote = ""

    def _refresh_file_row_styles(self) -> None:
        p = self._palette()
        for idx, row in enumerate(self._file_row_frames):
            selected = idx == self._selected_remote_idx
            row.configure(fg_color=p["primary_soft"] if selected else "transparent")
            children = row.winfo_children()
            if len(children) >= 2:
                children[0].configure(text_color=p["primary"] if selected else p["text"])
                children[1].configure(text_color=p["muted"])

    def _select_remote_idx(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._remote_files):
            return
        self._selected_remote_idx = idx
        self._selected_remote = self._remote_files[idx]["name"]
        self._refresh_file_row_styles()

    def _show_remote_empty(self, text: str) -> None:
        self._remote_empty_icon.grid()
        self._remote_empty.configure(text=text)
        self._remote_empty.grid()

    def _hide_remote_empty(self) -> None:
        self._remote_empty_icon.grid_remove()
        self._remote_empty.grid_remove()

    def _render_remote_files(self, files: List[Dict[str, int]]) -> None:
        self._clear_remote_list()
        if not files:
            self._show_remote_empty("暂无文件")
            return

        self._hide_remote_empty()
        p = self._palette()

        for idx, item in enumerate(files):
            name = item["name"]
            size_txt = self._fmt_size(item["size"])

            row = ctk.CTkFrame(self._remote_scroll, fg_color="transparent", corner_radius=6, height=36)
            row.grid(row=idx, column=0, sticky="ew", pady=1)
            row.grid_columnconfigure(0, weight=1)
            self._file_row_frames.append(row)

            name_lbl = ctk.CTkLabel(
                row, text=name, font=self._font_body(), anchor="w",
                text_color=p["text"],
            )
            name_lbl.grid(row=0, column=0, padx=(10, 4), sticky="ew")
            size_lbl = ctk.CTkLabel(
                row, text=size_txt, font=self._font_caption(),
                text_color=p["muted"], width=72, anchor="e",
            )
            size_lbl.grid(row=0, column=1, padx=(0, 10))

            def bind_click(widget, i=idx):
                widget.bind("<Button-1>", lambda _e, j=i: self._select_remote_idx(j))

            for w in (row, name_lbl, size_lbl):
                bind_click(w)

        self._refresh_file_row_styles()

    # ── 状态 ──────────────────────────────────────────────

    def _set_badge(self, lbl: ctk.CTkLabel, text: str, *, kind: str) -> None:
        p = self._palette()
        styles = {
            "ok": (p["success"], p["success_soft"]),
            "warn": (p["warn"], p["warn_soft"]),
            "muted": (p["muted"], p["panel"]),
        }
        fg, bg = styles.get(kind, styles["muted"])
        lbl.configure(text=text, text_color=fg, fg_color=bg)

    def _update_status_badges(self) -> None:
        if self.client.is_connected:
            self._set_badge(self._lbl_conn_status, "已连接", kind="ok")
        else:
            self._set_badge(self._lbl_conn_status, "未连接", kind="muted")

        if self.client.is_logged_in:
            self._set_badge(self._lbl_auth_status, "已登录", kind="ok")
        else:
            self._set_badge(self._lbl_auth_status, "未登录", kind="warn")

    # ── 回调 ──────────────────────────────────────────────

    def _append_log(self, message: str) -> None:
        def _write() -> None:
            self.txt_log.configure(state="normal")
            self.txt_log.insert("end", message + "\n")
            self.txt_log.see("end")
            self.txt_log.configure(state="disabled")

        if threading.current_thread() is threading.main_thread():
            _write()
        else:
            self._run_on_ui(_write)

    def _update_progress(self, percent: float, desc: str) -> None:
        def _ui() -> None:
            self.progress_bar.set(max(0.0, min(1.0, percent / 100.0)))
            p = self._palette()
            if percent > 0:
                self.lbl_progress.configure(text=f"{percent:.0f}%  {desc}", text_color=p["text"])
            else:
                self.lbl_progress.configure(text="空闲", text_color=p["muted"])

        self._run_on_ui(_ui)

    def _on_auth_result(self, success: bool, message: str) -> None:
        def _ui() -> None:
            self._update_status_badges()
            if success:
                messagebox.showinfo("登录成功", message)
            else:
                messagebox.showerror("登录失败", message)

        self._run_on_ui(_ui)

    def _on_file_list(self, files: List[Dict[str, int]]) -> None:
        def _ui() -> None:
            self._remote_files = files
            self._render_remote_files(files)

        self._run_on_ui(_ui)

    def _on_transfer_done(self, message: str) -> None:
        def _ui() -> None:
            messagebox.showinfo("完成", message)
            if self.client.is_logged_in:
                self._on_refresh_list()

        self._run_on_ui(_ui)

    def _on_error(self, message: str) -> None:
        def _ui() -> None:
            messagebox.showerror("错误", message)

        self._run_on_ui(_ui)

    # ── 操作 ──────────────────────────────────────────────

    def _get_host_port(self) -> tuple:
        host = self.entry_host.get().strip()
        port_str = self.entry_port.get().strip()
        if not host:
            raise ValueError("请输入服务器 IP")
        try:
            port = int(port_str)
        except ValueError as exc:
            raise ValueError("端口必须是数字") from exc
        return host, port

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in (
            self.btn_connect,
            self.btn_disconnect,
            self.btn_login,
            self.btn_refresh,
            self.btn_upload,
            self.btn_download,
            self.btn_delete,
            self.btn_browse,
        ):
            btn.configure(state=state)

    def _run_task(self, task, task_name: str, *, on_done=None) -> None:
        if self._busy:
            return

        def _ui_busy(v: bool) -> None:
            self._set_busy(v)

        self._run_on_ui(lambda: _ui_busy(True))

        def wrapper() -> None:
            try:
                task()
                if on_done:
                    self._run_on_ui(on_done)
            except Exception as exc:
                msg = f"{task_name}失败: {exc}"
                self._append_log(msg)
                self._run_on_ui(lambda: messagebox.showerror("错误", msg))
                if on_done:
                    self._run_on_ui(on_done)
            finally:
                self._run_on_ui(lambda: _ui_busy(False))

        threading.Thread(target=wrapper, daemon=True).start()

    def _on_connect(self) -> None:
        try:
            host, port = self._get_host_port()
        except ValueError as exc:
            messagebox.showwarning("输入错误", str(exc))
            return

        def _task() -> None:
            self.client.connect(host, port)

        self._run_task(_task, "连接", on_done=self._update_status_badges)

    def _on_disconnect(self) -> None:
        def _task() -> None:
            self.client.disconnect()

        self._run_task(_task, "断开", on_done=self._update_status_badges)

    def _on_login(self) -> None:
        username = self.entry_user.get().strip()
        password = self.entry_pass.get()
        if not username or not password:
            messagebox.showwarning("提示", "请输入用户名和密码")
            return
        try:
            host, port = self._get_host_port()
        except ValueError as exc:
            messagebox.showwarning("输入错误", str(exc))
            return

        def _task() -> None:
            # 未连接时自动连服务器，避免「先点连接、马上点登录」的竞态
            if not self.client.is_connected:
                self.client.connect(host, port)
            self.client.login(username, password)

        self._run_task(_task, "登录", on_done=self._update_status_badges)

    def _on_refresh_list(self) -> None:
        if not self.client.is_logged_in:
            messagebox.showwarning("提示", "请先登录")
            return
        self.client.run_in_thread(self.client.list_files, "获取文件列表")

    def _on_browse_local(self) -> None:
        path = filedialog.askopenfilename(title="选择要上传的文件")
        if path:
            self._selected_local = path
            name = os.path.basename(path)
            size = os.path.getsize(path)
            p = self._palette()
            self.lbl_local.configure(text=name, text_color=p["text"])
            self._local_size.configure(text=self._fmt_size(size))

    def _on_upload(self) -> None:
        if not self.client.is_logged_in:
            messagebox.showwarning("提示", "请先登录")
            return
        if not self._selected_local:
            messagebox.showwarning("提示", "请先选择文件")
            return
        self.progress_bar.set(0)
        self.client.run_in_thread(lambda: self.client.upload_file(self._selected_local), "上传")

    def _on_download(self) -> None:
        if not self.client.is_logged_in:
            messagebox.showwarning("提示", "请先登录")
            return
        if not self._selected_remote:
            messagebox.showwarning("提示", "请先选择远端文件")
            return
        self.progress_bar.set(0)
        self.client.run_in_thread(lambda: self.client.download_file(self._selected_remote), "下载")

    def _on_delete(self) -> None:
        if not self.client.is_logged_in:
            messagebox.showwarning("提示", "请先登录")
            return
        if not self._selected_remote:
            messagebox.showwarning("提示", "请先选择远端文件")
            return
        if not messagebox.askyesno("确认删除", f"确定删除？\n\n{self._selected_remote}"):
            return
        self.client.run_in_thread(lambda: self.client.delete_file(self._selected_remote), "删除")


def main() -> None:
    app = FileTransferApp()
    app.mainloop()


if __name__ == "__main__":
    main()
