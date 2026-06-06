#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCP 文件传输客户端 GUI：CustomTkinter 现代化界面，网络 I/O 运行于子线程。"""

import os  # 导入 os 模块，处理文件路径
import threading  # 导入 threading，配合 tcp_client 子线程机制
import tkinter as tk  # 导入 tkinter，用于 messagebox 与 filedialog
from tkinter import filedialog, messagebox  # 文件选择与弹窗组件
from typing import Dict, List  # 类型注解

import customtkinter as ctk  # 导入 CustomTkinter，构建现代化 UI

from tcp_client import TcpFileClient  # 导入 TCP 通信核心类


class FileTransferApp(ctk.CTk):
    """主窗口类：深色/浅色主题、连接配置、登录、文件列表、进度条与日志。"""

    def __init__(self) -> None:
        """初始化界面布局与 TCP 客户端回调绑定。"""
        super().__init__()  # 调用 CTk 父类构造函数

        ctk.set_appearance_mode("system")  # 跟随系统深色/浅色主题
        ctk.set_default_color_theme("blue")  # 默认蓝色科技风配色

        self.title("TCP 文件传输客户端")  # 窗口标题
        self.geometry("980x720")  # 初始窗口大小
        self.minsize(860, 640)  # 最小尺寸，防止布局挤压

        self._remote_files: List[Dict[str, int]] = []  # 缓存远端文件列表
        self._selected_local: str = ""  # 当前选中的本地文件路径
        self._selected_remote: str = ""  # 当前选中的远端文件名

        # 创建 TCP 客户端，注册各类 UI 回调（回调内用 after 切回主线程）
        self.client = TcpFileClient(
            on_log=self._append_log,  # 日志输出
            on_progress=self._update_progress,  # 进度条更新
            on_auth_result=self._on_auth_result,  # 登录结果弹窗
            on_file_list=self._on_file_list,  # 刷新远端列表
            on_transfer_done=self._on_transfer_done,  # 传输完成提示
            on_error=self._on_error,  # 错误弹窗
        )

        self._build_ui()  # 构建界面控件

    def _run_on_ui(self, func) -> None:
        """将回调调度到 Tk 主线程执行，避免跨线程直接操作控件。"""
        self.after(0, func)  # after(0) 在事件循环空闲时于主线程调用

    def _build_ui(self) -> None:
        """构建全部界面分区。"""
        self.grid_columnconfigure(0, weight=1)  # 主列可伸缩
        self.grid_rowconfigure(3, weight=1)  # 日志区可纵向扩展

        # ---------- 顶部：连接配置区 ----------
        conn_frame = ctk.CTkFrame(self, corner_radius=12)  # 圆角卡片容器
        conn_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")  # 网格布局
        conn_frame.grid_columnconfigure(1, weight=1)  # IP 输入框可拉伸

        ctk.CTkLabel(conn_frame, text="服务器 IP", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=12, pady=12
        )  # IP 标签
        self.entry_host = ctk.CTkEntry(conn_frame, placeholder_text="例如 127.0.0.1 或公网 IP")  # IP 输入
        self.entry_host.grid(row=0, column=1, padx=8, pady=12, sticky="ew")  # 放置输入框
        self.entry_host.insert(0, "127.0.0.1")  # 默认本机地址

        ctk.CTkLabel(conn_frame, text="端口", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=2, padx=8, pady=12
        )  # 端口标签
        self.entry_port = ctk.CTkEntry(conn_frame, width=90, placeholder_text="8082")  # 端口输入
        self.entry_port.grid(row=0, column=3, padx=8, pady=12)  # 放置端口框
        self.entry_port.insert(0, "8082")  # 默认实验端口

        self.btn_connect = ctk.CTkButton(conn_frame, text="连接", command=self._on_connect, width=90)  # 连接按钮
        self.btn_connect.grid(row=0, column=4, padx=8, pady=12)  # 放置连接按钮
        self.btn_disconnect = ctk.CTkButton(
            conn_frame, text="断开", command=self._on_disconnect, width=90, fg_color="#8B3A3A", hover_color="#6E2E2E"
        )  # 断开按钮（红色系）
        self.btn_disconnect.grid(row=0, column=5, padx=(0, 12), pady=12)  # 放置断开按钮

        theme_menu = ctk.CTkOptionMenu(
            conn_frame, values=["system", "dark", "light"], command=self._on_theme_change, width=100
        )  # 主题切换下拉
        theme_menu.grid(row=0, column=6, padx=(0, 12), pady=12)  # 放置主题菜单
        theme_menu.set("system")  # 默认跟随系统

        # ---------- 登录面板 ----------
        login_frame = ctk.CTkFrame(self, corner_radius=12)  # 登录区容器
        login_frame.grid(row=1, column=0, padx=16, pady=8, sticky="ew")  # 第二行
        login_frame.grid_columnconfigure(1, weight=1)  # 用户名框可拉伸

        ctk.CTkLabel(login_frame, text="用户登录", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=6, padx=12, pady=(12, 4), sticky="w"
        )  # 登录标题

        ctk.CTkLabel(login_frame, text="用户名").grid(row=1, column=0, padx=12, pady=8)  # 用户名标签
        self.entry_user = ctk.CTkEntry(login_frame, placeholder_text="admin")  # 用户名输入
        self.entry_user.grid(row=1, column=1, padx=8, pady=8, sticky="ew")  # 放置

        ctk.CTkLabel(login_frame, text="密码").grid(row=1, column=2, padx=8, pady=8)  # 密码标签
        self.entry_pass = ctk.CTkEntry(login_frame, placeholder_text="admin123", show="*")  # 密码掩码输入
        self.entry_pass.grid(row=1, column=3, padx=8, pady=8, sticky="ew")  # 放置

        self.btn_login = ctk.CTkButton(login_frame, text="登录验证", command=self._on_login, width=110)  # 登录按钮
        self.btn_login.grid(row=1, column=4, padx=8, pady=8)  # 放置

        self.lbl_auth = ctk.CTkLabel(login_frame, text="状态: 未登录", text_color="#FFAA00")  # 登录状态标签
        self.lbl_auth.grid(row=1, column=5, padx=(0, 12), pady=8)  # 放置状态

        # ---------- 中部：文件操作区 ----------
        file_frame = ctk.CTkFrame(self, corner_radius=12)  # 文件操作容器
        file_frame.grid(row=2, column=0, padx=16, pady=8, sticky="nsew")  # 第三行
        file_frame.grid_columnconfigure(0, weight=1)  # 左列伸缩
        file_frame.grid_columnconfigure(1, weight=1)  # 右列伸缩
        file_frame.grid_rowconfigure(1, weight=1)  # 列表区伸缩

        ctk.CTkLabel(file_frame, text="远端文件列表", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 4), sticky="w"
        )  # 远端列表标题
        ctk.CTkLabel(file_frame, text="本地文件选择", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=1, padx=12, pady=(12, 4), sticky="w"
        )  # 本地选择标题

        self.list_remote = tk.Listbox(
            file_frame,
            height=10,
            bg="#2B2B2B" if ctk.get_appearance_mode() == "Dark" else "#F0F0F0",
            fg="#FFFFFF" if ctk.get_appearance_mode() == "Dark" else "#1A1A1A",
            selectbackground="#1F6AA5",
            borderwidth=0,
            highlightthickness=1,
        )  # 远端文件 Listbox（支持双击选择）
        self.list_remote.grid(row=1, column=0, padx=12, pady=8, sticky="nsew")  # 放置列表
        self.list_remote.bind("<<ListboxSelect>>", self._on_remote_select)  # 选中事件

        local_panel = ctk.CTkFrame(file_frame, fg_color="transparent")  # 本地文件面板
        local_panel.grid(row=1, column=1, padx=12, pady=8, sticky="nsew")  # 右列
        local_panel.grid_columnconfigure(0, weight=1)  # 路径框可拉伸

        self.lbl_local = ctk.CTkLabel(
            local_panel, text="未选择本地文件", wraplength=360, justify="left"
        )  # 显示已选本地路径
        self.lbl_local.grid(row=0, column=0, columnspan=2, padx=4, pady=8, sticky="ew")  # 放置

        ctk.CTkButton(local_panel, text="浏览本地文件...", command=self._on_browse_local).grid(
            row=1, column=0, padx=4, pady=4, sticky="w"
        )  # 本地文件选择按钮

        btn_row = ctk.CTkFrame(file_frame, fg_color="transparent")  # 操作按钮行
        btn_row.grid(row=2, column=0, columnspan=2, padx=12, pady=(4, 8), sticky="ew")  # 底部

        self.btn_refresh = ctk.CTkButton(btn_row, text="刷新远端列表", command=self._on_refresh_list, width=130)  # 刷新
        self.btn_refresh.grid(row=0, column=0, padx=4, pady=4)  # 放置

        self.btn_upload = ctk.CTkButton(
            btn_row, text="上传文件", command=self._on_upload, width=120, fg_color="#1A7F4B", hover_color="#14663C"
        )  # 上传按钮
        self.btn_upload.grid(row=0, column=1, padx=4, pady=4)  # 放置

        self.btn_download = ctk.CTkButton(
            btn_row, text="下载文件", command=self._on_download, width=120, fg_color="#1F6AA5", hover_color="#185580"
        )  # 下载按钮
        self.btn_download.grid(row=0, column=2, padx=4, pady=4)  # 放置

        # ---------- 进度条 ----------
        progress_frame = ctk.CTkFrame(self, corner_radius=12)  # 进度区
        progress_frame.grid(row=3, column=0, padx=16, pady=8, sticky="ew")  # 第四行
        progress_frame.grid_columnconfigure(0, weight=1)  # 进度条可拉伸

        self.lbl_progress = ctk.CTkLabel(progress_frame, text="传输进度: 0.0%")  # 百分比文字
        self.lbl_progress.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")  # 放置

        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=18)  # 进度条控件
        self.progress_bar.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")  # 放置
        self.progress_bar.set(0)  # 初始 0%

        # ---------- 日志控制台 ----------
        log_frame = ctk.CTkFrame(self, corner_radius=12)  # 日志区容器
        log_frame.grid(row=4, column=0, padx=16, pady=(8, 16), sticky="nsew")  # 第五行
        log_frame.grid_columnconfigure(0, weight=1)  # 文本框可拉伸
        log_frame.grid_rowconfigure(1, weight=1)  # 日志文本可纵向扩展
        self.grid_rowconfigure(4, weight=2)  # 主窗口给日志更多空间

        ctk.CTkLabel(log_frame, text="运行日志", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 4), sticky="w"
        )  # 日志标题

        self.txt_log = ctk.CTkTextbox(log_frame, height=160, font=ctk.CTkFont(family="Consolas", size=12))  # 日志文本框
        self.txt_log.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")  # 放置
        self.txt_log.configure(state="disabled")  # 默认只读

        self._append_log("客户端已启动，请先连接服务器并登录。")  # 初始日志

    def _on_theme_change(self, mode: str) -> None:
        """切换深色/浅色/跟随系统主题。"""
        ctk.set_appearance_mode(mode)  # 应用主题
        dark = mode == "dark" or (mode == "system" and ctk.get_appearance_mode() == "Dark")  # 判断是否深色
        self.list_remote.configure(
            bg="#2B2B2B" if dark else "#F0F0F0", fg="#FFFFFF" if dark else "#1A1A1A"
        )  # 同步 Listbox 配色

    def _append_log(self, message: str) -> None:
        """线程安全地向日志区追加一行文本。"""

        def _write() -> None:
            self.txt_log.configure(state="normal")  # 临时允许写入
            self.txt_log.insert("end", message + "\n")  # 追加日志行
            self.txt_log.see("end")  # 滚动到底部
            self.txt_log.configure(state="disabled")  # 恢复只读

        if threading.current_thread() is threading.main_thread():  # 已在主线程
            _write()  # 直接写
        else:  # 在子线程回调中
            self._run_on_ui(_write)  # 调度到主线程

    def _update_progress(self, percent: float, desc: str) -> None:
        """更新进度条与百分比标签（线程安全）。"""

        def _ui() -> None:
            value = max(0.0, min(1.0, percent / 100.0))  # CTk 进度条取值 0~1
            self.progress_bar.set(value)  # 设置进度条
            self.lbl_progress.configure(text=f"传输进度: {percent:.1f}%  |  {desc}")  # 更新文字

        self._run_on_ui(_ui)  # 主线程更新 UI

    def _on_auth_result(self, success: bool, message: str) -> None:
        """登录结果：成功更新状态，失败弹窗提示。"""

        def _ui() -> None:
            if success:  # 登录成功
                self.lbl_auth.configure(text="状态: 已登录", text_color="#4CD964")  # 绿色状态
                messagebox.showinfo("登录成功", message)  # 成功提示框
            else:  # 登录失败
                self.lbl_auth.configure(text="状态: 未登录", text_color="#FF453A")  # 红色状态
                messagebox.showerror("登录失败", message)  # 错误弹窗（用户名错误/密码错误）

        self._run_on_ui(_ui)  # 主线程弹窗

    def _on_file_list(self, files: List[Dict[str, int]]) -> None:
        """刷新远端文件 Listbox。"""

        def _ui() -> None:
            self._remote_files = files  # 缓存列表数据
            self.list_remote.delete(0, "end")  # 清空 Listbox
            for item in files:  # 遍历文件
                size_kb = item["size"] / 1024.0  # 字节转 KB 显示
                line = f"{item['name']}  ({size_kb:.1f} KB)"  # 格式化行
                self.list_remote.insert("end", line)  # 插入一行

        self._run_on_ui(_ui)  # 主线程刷新

    def _on_transfer_done(self, message: str) -> None:
        """传输完成后的 UI 反馈。"""

        def _ui() -> None:
            messagebox.showinfo("传输完成", message)  # 完成弹窗
            if self.client.is_logged_in:  # 若仍在线则自动刷新列表
                self._on_refresh_list()  # 刷新远端文件

        self._run_on_ui(_ui)  # 主线程执行

    def _on_error(self, message: str) -> None:
        """网络错误弹窗。"""

        def _ui() -> None:
            messagebox.showerror("操作错误", message)  # 错误弹窗

        self._run_on_ui(_ui)  # 主线程弹窗

    def _get_host_port(self) -> tuple:
        """从输入框解析 IP 与端口。"""
        host = self.entry_host.get().strip()  # 读取 IP
        port_str = self.entry_port.get().strip()  # 读取端口字符串
        if not host:  # IP 不能为空
            raise ValueError("请输入服务器 IP")  # 校验
        try:
            port = int(port_str)  # 端口转整数
        except ValueError as exc:
            raise ValueError("端口必须是数字") from exc  # 端口格式错误
        return host, port  # 返回元组

    def _on_connect(self) -> None:
        """连接按钮：子线程执行 connect，不阻塞 GUI。"""
        try:
            host, port = self._get_host_port()  # 解析配置
        except ValueError as exc:
            messagebox.showwarning("输入错误", str(exc))  # 弹窗提示
            return  # 终止

        self.client.run_in_thread(lambda: self.client.connect(host, port), "连接")  # 子线程连接

    def _on_disconnect(self) -> None:
        """断开连接。"""
        self.client.run_in_thread(self.client.disconnect, "断开")  # 子线程断开
        self.lbl_auth.configure(text="状态: 未登录", text_color="#FFAA00")  # 重置状态

    def _on_login(self) -> None:
        """登录按钮：必须先连接，再在子线程验证。"""
        if not self.client.is_connected:  # 未连接
            messagebox.showwarning("提示", "请先连接服务器")  # 警告
            return  # 终止
        username = self.entry_user.get().strip()  # 读取用户名
        password = self.entry_pass.get()  # 读取密码
        if not username or not password:  # 非空校验
            messagebox.showwarning("提示", "请输入用户名和密码")  # 警告
            return  # 终止
        self.client.run_in_thread(lambda: self.client.login(username, password), "登录")  # 子线程登录

    def _on_refresh_list(self) -> None:
        """刷新远端文件列表（需已登录）。"""
        if not self.client.is_logged_in:  # 未登录
            messagebox.showwarning("提示", "请先登录后再查看远端文件列表")  # 警告
            return  # 终止
        self.client.run_in_thread(self.client.list_files, "获取文件列表")  # 子线程请求列表

    def _on_browse_local(self) -> None:
        """打开本地文件选择对话框。"""
        path = filedialog.askopenfilename(title="选择要上传的文件")  # 系统文件对话框
        if path:  # 用户选择了文件
            self._selected_local = path  # 保存路径
            self.lbl_local.configure(text=f"已选: {path}")  # 更新标签

    def _on_remote_select(self, _event=None) -> None:
        """Listbox 选中项时记录远端文件名。"""
        sel = self.list_remote.curselection()  # 获取选中索引
        if not sel:  # 无选中
            return  # 忽略
        idx = sel[0]  # 第一个选中索引
        if 0 <= idx < len(self._remote_files):  # 边界检查
            self._selected_remote = self._remote_files[idx]["name"]  # 记录文件名

    def _on_upload(self) -> None:
        """上传：强制登录校验后在子线程传输。"""
        if not self.client.is_logged_in:  # 未登录禁止上传
            messagebox.showwarning("需要登录", "请先登录后再上传文件")  # 弹窗
            return  # 终止
        if not self._selected_local:  # 未选本地文件
            messagebox.showwarning("提示", "请先选择要上传的本地文件")  # 警告
            return  # 终止
        path = self._selected_local  # 捕获路径供闭包使用
        self.progress_bar.set(0)  # 重置进度条
        self.client.run_in_thread(lambda: self.client.upload_file(path), "上传")  # 子线程上传

    def _on_download(self) -> None:
        """下载：强制登录校验后在子线程传输。"""
        if not self.client.is_logged_in:  # 未登录禁止下载
            messagebox.showwarning("需要登录", "请先登录后再下载文件")  # 弹窗
            return  # 终止
        if not self._selected_remote:  # 未选远端文件
            messagebox.showwarning("提示", "请先在远端列表中选择要下载的文件")  # 警告
            return  # 终止
        name = self._selected_remote  # 捕获文件名
        self.progress_bar.set(0)  # 重置进度条
        self.client.run_in_thread(lambda: self.client.download_file(name), "下载")  # 子线程下载


def main() -> None:
    """程序入口。"""
    app = FileTransferApp()  # 创建主窗口
    app.mainloop()  # 进入 Tk 事件循环（GUI 主线程）


if __name__ == "__main__":  # 直接运行本脚本
    main()  # 启动客户端
