#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCP 文件传输客户端 GUI：CustomTkinter 现代化界面，网络 I/O 运行于子线程。"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk

from tcp_client import TcpFileClient

# 与 Web 控制台 business-light / business-dark 对齐的配色
_PALETTE = {
    "light": {
        "bg": "#f1f5f9",
        "surface": "#ffffff",
        "surface2": "#f8fafc",
        "border": "#e2e8f0",
        "text": "#0f172a",
        "muted": "#64748b",
        "primary": "#4f46e5",
        "primary_hover": "#4338ca",
        "primary_soft": "#eef2ff",
        "success": "#059669",
        "success_soft": "#ecfdf5",
        "warn": "#d97706",
        "warn_soft": "#fffbeb",
        "danger": "#dc2626",
        "danger_soft": "#fef2f2",
        "row_hover": "#f8fafc",
    },
    "dark": {
        "bg": "#0f172a",
        "surface": "#1e293b",
        "surface2": "#334155",
        "border": "#334155",
        "text": "#f1f5f9",
        "muted": "#94a3b8",
        "primary": "#818cf8",
        "primary_hover": "#a5b4fc",
        "primary_soft": "#312e81",
        "success": "#34d399",
        "success_soft": "#064e3b",
        "warn": "#fbbf24",
        "warn_soft": "#78350f",
        "danger": "#f87171",
        "danger_soft": "#7f1d1d",
        "row_hover": "#334155",
    },
}


class FileTransferApp(ctk.CTk):
    """主窗口：简约商务风布局，网络 I/O 在子线程执行。"""

    def __init__(self) -> None:
        super().__init__()

        self._appearance = "light"
        self._remote_files: List[Dict[str, int]] = []
        self._selected_local: str = ""
        self._selected_remote: str = ""
        self._selected_remote_idx: Optional[int] = None
        self._file_row_frames: List[ctk.CTkFrame] = []

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title("TCP 文件传输客户端")
        self.geometry("1040x780")
        self.minsize(920, 680)

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

    # ── 主题与样式 ──────────────────────────────────────────────

    def _palette(self) -> Dict[str, str]:
        return _PALETTE[self._appearance]

    def _font_title(self) -> ctk.CTkFont:
        return ctk.CTkFont(family="Microsoft YaHei UI", size=16, weight="bold")

    def _font_section(self) -> ctk.CTkFont:
        return ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold")

    def _font_body(self) -> ctk.CTkFont:
        return ctk.CTkFont(family="Microsoft YaHei UI", size=12)

    def _font_mono(self) -> ctk.CTkFont:
        return ctk.CTkFont(family="Consolas", size=11)

    def _is_dark(self) -> bool:
        if self._appearance == "dark":
            return True
        if self._appearance == "system":
            return ctk.get_appearance_mode() == "Dark"
        return False

    def _apply_theme(self) -> None:
        p = self._palette()
        self.configure(fg_color=p["bg"])
        for frame in (
            self._header,
            self._conn_card,
            self._login_card,
            self._file_card,
            self._progress_card,
            self._log_card,
        ):
            frame.configure(fg_color=p["surface"], border_color=p["border"])
        self._brand_icon.configure(fg_color=p["primary"])
        self._subtitle.configure(text_color=p["muted"])
        self._local_drop.configure(
            fg_color=p["surface2"],
            border_color=p["border"],
        )
        self._refresh_file_row_styles()
        self._update_status_badges()

    def _run_on_ui(self, func) -> None:
        self.after(0, func)

    def _card(self, parent, row: int, *, pady: Tuple[int, int] = (0, 10)) -> ctk.CTkFrame:
        p = self._palette()
        card = ctk.CTkFrame(
            parent,
            corner_radius=14,
            fg_color=p["surface"],
            border_width=1,
            border_color=p["border"],
        )
        card.grid(row=row, column=0, padx=20, pady=pady, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        return card

    def _section_title(self, parent, row: int, text: str, subtitle: str = "") -> None:
        p = self._palette()
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid(row=row, column=0, padx=16, pady=(14, 8), sticky="ew")
        ctk.CTkLabel(wrap, text=text, font=self._font_section(), text_color=p["text"]).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(
                wrap, text=subtitle, font=self._font_body(), text_color=p["muted"]
            ).pack(anchor="w", pady=(2, 0))

    def _primary_btn(self, parent, text: str, command, width: int = 100) -> ctk.CTkButton:
        p = self._palette()
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=34,
            corner_radius=8,
            font=self._font_body(),
            fg_color=p["primary"],
            hover_color=p["primary_hover"],
        )

    def _ghost_btn(self, parent, text: str, command, width: int = 100) -> ctk.CTkButton:
        p = self._palette()
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=34,
            corner_radius=8,
            font=self._font_body(),
            fg_color=p["surface2"],
            hover_color=p["border"],
            text_color=p["text"],
            border_width=1,
            border_color=p["border"],
        )

    def _danger_btn(self, parent, text: str, command, width: int = 100) -> ctk.CTkButton:
        p = self._palette()
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=34,
            corner_radius=8,
            font=self._font_body(),
            fg_color=p["danger"],
            hover_color="#b91c1c",
        )

    # ── 界面构建 ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=2)

        self._build_header()
        self._build_conn_card()
        self._build_login_card()
        self._build_file_card()
        self._build_progress_card()
        self._build_log_card()

        self._append_log("客户端已启动。请连接本机服务器 127.0.0.1:8082 并登录。")

    def _build_header(self) -> None:
        p = _PALETTE["light"]
        self._header = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color=p["surface"],
            border_width=0,
            height=64,
        )
        self._header.grid(row=0, column=0, sticky="ew")
        self._header.grid_columnconfigure(1, weight=1)

        brand = ctk.CTkFrame(self._header, fg_color="transparent")
        brand.grid(row=0, column=0, padx=20, pady=12, sticky="w")

        self._brand_icon = ctk.CTkLabel(
            brand,
            text="FT",
            width=40,
            height=40,
            corner_radius=10,
            fg_color=p["primary"],
            text_color="#ffffff",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._brand_icon.pack(side="left")

        title_wrap = ctk.CTkFrame(brand, fg_color="transparent")
        title_wrap.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(
            title_wrap,
            text="TCP 文件传输客户端",
            font=self._font_title(),
            text_color=p["text"],
        ).pack(anchor="w")
        self._subtitle = ctk.CTkLabel(
            title_wrap,
            text="FTCP 协议 · 本机实验复现",
            font=self._font_body(),
            text_color=p["muted"],
        )
        self._subtitle.pack(anchor="w")

        actions = ctk.CTkFrame(self._header, fg_color="transparent")
        actions.grid(row=0, column=2, padx=20, pady=12, sticky="e")

        self._lbl_conn_status = ctk.CTkLabel(
            actions,
            text="● 未连接",
            font=self._font_body(),
            text_color=p["muted"],
        )
        self._lbl_conn_status.pack(side="left", padx=(0, 16))

        self._ui_styles = {
            "简约浅色": "light",
            "简约深色": "dark",
            "跟随系统": "system",
        }
        self._style_menu = ctk.CTkOptionMenu(
            actions,
            values=list(self._ui_styles.keys()),
            command=self._on_ui_style_change,
            width=120,
            height=32,
            corner_radius=8,
            font=self._font_body(),
        )
        self._style_menu.pack(side="left")
        self._style_menu.set("简约浅色")

    def _build_conn_card(self) -> None:
        self._conn_card = self._card(self, 1, pady=(12, 8))
        self._section_title(self._conn_card, 0, "连接设置", "填写服务器地址后点击连接")

        row = ctk.CTkFrame(self._conn_card, fg_color="transparent")
        row.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text="服务器 IP", font=self._font_body()).grid(row=0, column=0, padx=(0, 8))
        self.entry_host = ctk.CTkEntry(
            row, placeholder_text="127.0.0.1", height=34, corner_radius=8, font=self._font_body()
        )
        self.entry_host.grid(row=0, column=1, padx=4, sticky="ew")
        self.entry_host.insert(0, "127.0.0.1")

        ctk.CTkLabel(row, text="端口", font=self._font_body()).grid(row=0, column=2, padx=(12, 8))
        self.entry_port = ctk.CTkEntry(row, width=80, height=34, corner_radius=8, font=self._font_body())
        self.entry_port.grid(row=0, column=3, padx=4)
        self.entry_port.insert(0, "8082")

        self.btn_connect = self._primary_btn(row, "连接", self._on_connect, 88)
        self.btn_connect.grid(row=0, column=4, padx=(12, 4))
        self.btn_disconnect = self._danger_btn(row, "断开", self._on_disconnect, 88)
        self.btn_disconnect.grid(row=0, column=5, padx=4)

    def _build_login_card(self) -> None:
        self._login_card = self._card(self, 2, pady=8)
        self._section_title(self._login_card, 0, "身份验证", "登录后方可上传、下载与删除文件")

        row = ctk.CTkFrame(self._login_card, fg_color="transparent")
        row.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="ew")
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(row, text="用户名", font=self._font_body()).grid(row=0, column=0, padx=(0, 8))
        self.entry_user = ctk.CTkEntry(
            row, placeholder_text="admin", height=34, corner_radius=8, font=self._font_body()
        )
        self.entry_user.grid(row=0, column=1, padx=4, sticky="ew")

        ctk.CTkLabel(row, text="密码", font=self._font_body()).grid(row=0, column=2, padx=(12, 8))
        self.entry_pass = ctk.CTkEntry(
            row, placeholder_text="admin123", show="*", height=34, corner_radius=8, font=self._font_body()
        )
        self.entry_pass.grid(row=0, column=3, padx=4, sticky="ew")

        self.btn_login = self._primary_btn(row, "登录", self._on_login, 88)
        self.btn_login.grid(row=0, column=4, padx=(12, 8))

        self.lbl_auth = ctk.CTkLabel(
            row,
            text="未登录",
            font=self._font_body(),
            text_color=_PALETTE["light"]["warn"],
            fg_color=_PALETTE["light"]["warn_soft"],
            corner_radius=16,
            width=88,
            height=30,
        )
        self.lbl_auth.grid(row=0, column=5, padx=4)

    def _build_file_card(self) -> None:
        self._file_card = self._card(self, 3, pady=8)
        self._file_card.grid_rowconfigure(1, weight=1)
        self._file_card.grid_columnconfigure(0, weight=1)
        self._file_card.grid_columnconfigure(1, weight=1)

        headers = ctk.CTkFrame(self._file_card, fg_color="transparent")
        headers.grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 6), sticky="ew")
        headers.grid_columnconfigure(0, weight=1)
        headers.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(headers, text="远端文件", font=self._font_section()).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(headers, text="本地文件", font=self._font_section()).grid(row=0, column=1, sticky="w", padx=(12, 0))

        self._remote_scroll = ctk.CTkScrollableFrame(
            self._file_card,
            height=220,
            corner_radius=10,
            fg_color=_PALETTE["light"]["surface2"],
            border_width=1,
            border_color=_PALETTE["light"]["border"],
        )
        self._remote_scroll.grid(row=1, column=0, padx=(16, 8), pady=4, sticky="nsew")
        self._remote_scroll.grid_columnconfigure(0, weight=1)

        self._remote_empty = ctk.CTkLabel(
            self._remote_scroll,
            text="登录后点击「刷新列表」加载文件",
            font=self._font_body(),
            text_color=_PALETTE["light"]["muted"],
        )
        self._remote_empty.grid(row=0, column=0, pady=40)

        local_wrap = ctk.CTkFrame(self._file_card, fg_color="transparent")
        local_wrap.grid(row=1, column=1, padx=(8, 16), pady=4, sticky="nsew")
        local_wrap.grid_rowconfigure(0, weight=1)
        local_wrap.grid_columnconfigure(0, weight=1)

        self._local_drop = ctk.CTkFrame(
            local_wrap,
            corner_radius=10,
            fg_color=_PALETTE["light"]["surface2"],
            border_width=1,
            border_color=_PALETTE["light"]["border"],
        )
        self._local_drop.grid(row=0, column=0, sticky="nsew")
        self._local_drop.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._local_drop,
            text="📁",
            font=ctk.CTkFont(size=28),
        ).grid(row=0, column=0, pady=(28, 4))
        self.lbl_local = ctk.CTkLabel(
            self._local_drop,
            text="点击选择要上传的本地文件",
            font=self._font_body(),
            text_color=_PALETTE["light"]["muted"],
            wraplength=320,
            justify="center",
        )
        self.lbl_local.grid(row=1, column=0, padx=16, pady=4)
        ctk.CTkButton(
            self._local_drop,
            text="浏览本地文件",
            command=self._on_browse_local,
            height=32,
            corner_radius=8,
            font=self._font_body(),
            fg_color=_PALETTE["light"]["primary"],
            hover_color=_PALETTE["light"]["primary_hover"],
        ).grid(row=2, column=0, pady=(8, 24))

        btn_row = ctk.CTkFrame(self._file_card, fg_color="transparent")
        btn_row.grid(row=2, column=0, columnspan=2, padx=16, pady=(8, 14), sticky="ew")

        self.btn_refresh = self._ghost_btn(btn_row, "↻ 刷新列表", self._on_refresh_list, 120)
        self.btn_refresh.pack(side="left", padx=(0, 8))
        self.btn_upload = self._primary_btn(btn_row, "↑ 上传", self._on_upload, 100)
        self.btn_upload.pack(side="left", padx=4)
        self.btn_download = ctk.CTkButton(
            btn_row,
            text="↓ 下载",
            command=self._on_download,
            width=100,
            height=34,
            corner_radius=8,
            font=self._font_body(),
            fg_color="#0ea5e9",
            hover_color="#0284c7",
        )
        self.btn_download.pack(side="left", padx=4)
        self.btn_delete = self._danger_btn(btn_row, "删除", self._on_delete, 88)
        self.btn_delete.pack(side="left", padx=4)

    def _build_progress_card(self) -> None:
        self._progress_card = self._card(self, 4, pady=8)
        self._section_title(self._progress_card, 0, "传输进度")

        self.lbl_progress = ctk.CTkLabel(
            self._progress_card,
            text="等待传输任务…",
            font=self._font_body(),
            text_color=_PALETTE["light"]["muted"],
        )
        self.lbl_progress.grid(row=1, column=0, padx=16, pady=(0, 6), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(
            self._progress_card,
            height=10,
            corner_radius=5,
            progress_color=_PALETTE["light"]["primary"],
        )
        self.progress_bar.grid(row=2, column=0, padx=16, pady=(0, 14), sticky="ew")
        self.progress_bar.set(0)

    def _build_log_card(self) -> None:
        self._log_card = self._card(self, 5, pady=(8, 16))
        self._log_card.grid_rowconfigure(1, weight=1)
        self._section_title(self._log_card, 0, "运行日志", "记录连接、登录与传输操作")

        self.txt_log = ctk.CTkTextbox(
            self._log_card,
            height=140,
            font=self._font_mono(),
            corner_radius=10,
            fg_color=_PALETTE["light"]["surface2"],
            border_width=1,
            border_color=_PALETTE["light"]["border"],
        )
        self.txt_log.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="nsew")
        self.txt_log.configure(state="disabled")

    # ── 文件列表（可点击行） ────────────────────────────────────

    def _clear_remote_list(self) -> None:
        for row in self._file_row_frames:
            row.destroy()
        self._file_row_frames.clear()
        self._selected_remote_idx = None
        self._selected_remote = ""

    def _refresh_file_row_styles(self) -> None:
        p = self._palette()
        self._remote_scroll.configure(fg_color=p["surface2"], border_color=p["border"])
        for idx, row in enumerate(self._file_row_frames):
            selected = idx == self._selected_remote_idx
            row.configure(fg_color=p["primary_soft"] if selected else "transparent")
            for child in row.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    child.configure(
                        text_color=p["primary"] if selected else p["text"],
                    )

    def _select_remote_idx(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._remote_files):
            return
        self._selected_remote_idx = idx
        self._selected_remote = self._remote_files[idx]["name"]
        self._refresh_file_row_styles()

    def _render_remote_files(self, files: List[Dict[str, int]]) -> None:
        self._clear_remote_list()
        self._remote_empty.grid_remove()

        if not files:
            self._remote_empty.configure(text="远端暂无文件")
            self._remote_empty.grid()
            return

        p = self._palette()
        for idx, item in enumerate(files):
            name = item["name"]
            size_kb = item["size"] / 1024.0

            row = ctk.CTkFrame(self._remote_scroll, fg_color="transparent", corner_radius=8, height=40)
            row.grid(row=idx, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(1, weight=1)
            self._file_row_frames.append(row)

            icon = "📄" if size_kb < 1024 else "📦"
            ctk.CTkLabel(row, text=icon, width=28, font=self._font_body()).grid(row=0, column=0, padx=(8, 4))
            ctk.CTkLabel(
                row,
                text=name,
                font=self._font_body(),
                anchor="w",
                text_color=p["text"],
            ).grid(row=0, column=1, sticky="ew")
            ctk.CTkLabel(
                row,
                text=f"{size_kb:.1f} KB",
                font=self._font_body(),
                text_color=p["muted"],
            ).grid(row=0, column=2, padx=(4, 10))

            def bind_click(widget, i=idx):
                widget.bind("<Button-1>", lambda _e, j=i: self._select_remote_idx(j))

            bind_click(row)
            for child in row.winfo_children():
                bind_click(child)

        self._refresh_file_row_styles()

    # ── 状态徽章 ──────────────────────────────────────────────

    def _update_status_badges(self) -> None:
        p = self._palette()
        if self.client.is_connected:
            self._lbl_conn_status.configure(text="● 已连接", text_color=p["success"])
        else:
            self._lbl_conn_status.configure(text="● 未连接", text_color=p["muted"])

        if self.client.is_logged_in:
            self.lbl_auth.configure(
                text="已登录",
                text_color=p["success"],
                fg_color=p["success_soft"],
            )
        else:
            self.lbl_auth.configure(
                text="未登录",
                text_color=p["warn"],
                fg_color=p["warn_soft"],
            )

    def _on_ui_style_change(self, style_name: str) -> None:
        mode = self._ui_styles.get(style_name, "light")
        self._appearance = "light" if mode == "light" else ("dark" if mode == "dark" else "system")
        ctk.set_appearance_mode(mode)
        self._apply_theme()
        self._append_log(f"已切换主题：{style_name}")

    def _on_theme_change(self, mode: str) -> None:
        self._appearance = mode
        ctk.set_appearance_mode(mode)
        self._apply_theme()

    # ── 日志与进度 ──────────────────────────────────────────────

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
            value = max(0.0, min(1.0, percent / 100.0))
            self.progress_bar.set(value)
            p = self._palette()
            self.lbl_progress.configure(
                text=f"{percent:.1f}%  ·  {desc}",
                text_color=p["text"] if percent > 0 else p["muted"],
            )

        self._run_on_ui(_ui)

    # ── 客户端回调 ──────────────────────────────────────────────

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
            messagebox.showinfo("传输完成", message)
            if self.client.is_logged_in:
                self._on_refresh_list()

        self._run_on_ui(_ui)

    def _on_error(self, message: str) -> None:
        def _ui() -> None:
            messagebox.showerror("操作错误", message)

        self._run_on_ui(_ui)

    # ── 用户操作 ──────────────────────────────────────────────

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

    def _on_connect(self) -> None:
        try:
            host, port = self._get_host_port()
        except ValueError as exc:
            messagebox.showwarning("输入错误", str(exc))
            return

        def _task() -> None:
            self.client.connect(host, port)
            self._run_on_ui(self._update_status_badges)

        self.client.run_in_thread(_task, "连接")

    def _on_disconnect(self) -> None:
        self.client.run_in_thread(self.client.disconnect, "断开")
        self._update_status_badges()

    def _on_login(self) -> None:
        if not self.client.is_connected:
            messagebox.showwarning("提示", "请先连接服务器")
            return
        username = self.entry_user.get().strip()
        password = self.entry_pass.get()
        if not username or not password:
            messagebox.showwarning("提示", "请输入用户名和密码")
            return
        self.client.run_in_thread(lambda: self.client.login(username, password), "登录")

    def _on_refresh_list(self) -> None:
        if not self.client.is_logged_in:
            messagebox.showwarning("提示", "请先登录后再查看远端文件列表")
            return
        self.client.run_in_thread(self.client.list_files, "获取文件列表")

    def _on_browse_local(self) -> None:
        path = filedialog.askopenfilename(title="选择要上传的文件")
        if path:
            self._selected_local = path
            name = os.path.basename(path)
            size_kb = os.path.getsize(path) / 1024.0
            p = self._palette()
            self.lbl_local.configure(
                text=f"{name}\n{size_kb:.1f} KB",
                text_color=p["text"],
            )

    def _on_remote_select(self, _event=None) -> None:
        pass  # 已由 _select_remote_idx 处理

    def _on_upload(self) -> None:
        if not self.client.is_logged_in:
            messagebox.showwarning("需要登录", "请先登录后再上传文件")
            return
        if not self._selected_local:
            messagebox.showwarning("提示", "请先选择要上传的本地文件")
            return
        path = self._selected_local
        self.progress_bar.set(0)
        self.client.run_in_thread(lambda: self.client.upload_file(path), "上传")

    def _on_download(self) -> None:
        if not self.client.is_logged_in:
            messagebox.showwarning("需要登录", "请先登录后再下载文件")
            return
        if not self._selected_remote:
            messagebox.showwarning("提示", "请先在远端列表中选择要下载的文件")
            return
        name = self._selected_remote
        self.progress_bar.set(0)
        self.client.run_in_thread(lambda: self.client.download_file(name), "下载")

    def _on_delete(self) -> None:
        if not self.client.is_logged_in:
            messagebox.showwarning("需要登录", "请先登录后再删除文件")
            return
        if not self._selected_remote:
            messagebox.showwarning("提示", "请先在远端列表中选择要删除的文件")
            return
        name = self._selected_remote
        if not messagebox.askyesno("确认删除", f"确定要删除服务器上的文件吗？\n\n{name}"):
            return
        self.client.run_in_thread(lambda: self.client.delete_file(name), "删除")


def main() -> None:
    app = FileTransferApp()
    app.mainloop()


if __name__ == "__main__":
    main()
