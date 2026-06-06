#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCP 客户端通信核心：Socket 连接、自定义协议、分块传输与状态回调。"""

import hashlib  # SHA-256：登录前本地哈希，网络上不传输明文密码
import os  # 导入 os 模块，处理路径与目录
import socket  # 导入 socket 模块，建立 TCP 连接
import struct  # 导入 struct 模块，打包/解包二进制报文头
import threading  # 导入 threading 模块，在子线程中执行网络 I/O
from typing import Callable, Dict, List, Optional, Tuple  # 类型注解

# 须与 server/database.py 中 PASSWORD_SALT 保持完全一致，否则哈希无法匹配
PASSWORD_SALT = "FTCP_FILE_TRANSFER_SALT_2026"

# ===================== 协议常量（与服务端保持一致） =====================
MAGIC = b"FTCP"  # 协议魔数
VERSION = 1  # 协议版本
HEADER_SIZE = 10  # 固定报文头 10 字节
CHUNK_SIZE = 4096  # 分块缓存 4096 字节

CMD_LOGIN = 0x01  # 登录
CMD_LOGIN_RESP = 0x02  # 登录响应
CMD_LIST = 0x03  # 请求列表
CMD_LIST_RESP = 0x04  # 列表响应
CMD_UPLOAD = 0x05  # 上传
CMD_DOWNLOAD = 0x06  # 下载
CMD_ERROR = 0x07  # 错误
CMD_UPLOAD_ACK = 0x08  # 上传完成确认
CMD_DELETE = 0x09  # 删除
CMD_DELETE_RESP = 0x0A  # 删除响应

AUTH_OK = 0  # 登录成功
AUTH_USER_ERR = 1  # 用户名错误
AUTH_PASS_ERR = 2  # 密码错误

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # client 目录绝对路径
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")  # 客户端下载保存目录


def ensure_download_dir() -> None:
    """若 downloads 目录不存在则自动创建。"""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)  # 递归创建目录


def hash_password(password: str, username: str) -> str:
    """
    客户端本地 SHA-256 加盐哈希，与 server/database.py 算法一致。

    传输安全：明文密码仅在 GUI 内存中存在，send 前即转为 64 位十六进制摘要，
    Wireshark 抓包无法还原原始密码（零知识传输思路，无 TLS 下的折中方案）。
    """
    raw = f"{PASSWORD_SALT}:{username}:{password}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def recv_exact(sock: socket.socket, size: int) -> bytes:
    """精确接收 size 字节，防止 TCP 粘包导致的数据不完整。"""
    chunks = []  # 缓存各次 recv 片段
    received = 0  # 已收字节数
    while received < size:  # 循环直到收满
        part = sock.recv(size - received)  # 从接收缓存读取
        if not part:  # 连接关闭
            raise ConnectionError("连接已关闭")  # 抛出异常
        chunks.append(part)  # 追加片段
        received += len(part)  # 更新计数
    return b"".join(chunks)  # 拼接返回


def send_frame(sock: socket.socket, cmd: int, payload: bytes = b"") -> None:
    """发送完整协议帧。"""
    header = struct.pack("!4sBBI", MAGIC, VERSION, cmd, len(payload))  # 打包固定头
    sock.sendall(header + payload)  # 一次性发送头+体


def parse_header(sock: socket.socket) -> Tuple[int, bytes]:
    """接收并解析报文头。"""
    header = recv_exact(sock, HEADER_SIZE)  # 精确读 10 字节头
    magic, version, cmd, payload_len = struct.unpack("!4sBBI", header)  # 解包
    if magic != MAGIC:  # 校验魔数
        raise ValueError("非法协议魔数")  # 协议错误
    if version != VERSION:  # 校验版本
        raise ValueError("协议版本不匹配")  # 版本错误
    payload = recv_exact(sock, payload_len) if payload_len else b""  # 读 payload
    return cmd, payload  # 返回命令与负载


class TcpFileClient:
    """
    TCP 文件传输客户端。
    所有阻塞型 Socket 操作通过 run_in_thread 在子线程执行，避免阻塞 GUI。
    """

    def __init__(
        self,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_auth_result: Optional[Callable[[bool, str], None]] = None,
        on_file_list: Optional[Callable[[List[Dict[str, int]]], None]] = None,
        on_transfer_done: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """初始化客户端及各类 UI 回调函数。"""
        ensure_download_dir()  # 确保下载目录存在
        self._sock: Optional[socket.socket] = None  # TCP Socket 对象，未连接时为 None
        self._lock = threading.Lock()  # 线程锁，保护 Socket 并发访问
        self._logged_in = False  # 是否已通过身份验证
        self._on_log = on_log or (lambda _m: None)  # 日志回调
        self._on_progress = on_progress or (lambda _p, _m: None)  # 进度回调 (0~100, 描述)
        self._on_auth_result = on_auth_result or (lambda _ok, _msg: None)  # 登录结果回调
        self._on_file_list = on_file_list or (lambda _files: None)  # 文件列表回调
        self._on_transfer_done = on_transfer_done or (lambda _m: None)  # 传输完成回调
        self._on_error = on_error or (lambda _m: None)  # 错误回调

    @property
    def is_connected(self) -> bool:
        """当前是否已建立 TCP 连接。"""
        return self._sock is not None  # Socket 非空即视为已连接

    @property
    def is_logged_in(self) -> bool:
        """当前是否已登录成功。"""
        return self._logged_in  # 返回登录状态

    def _log(self, message: str) -> None:
        """写日志到 UI 控制台。"""
        self._on_log(message)  # 触发日志回调

    def connect(self, host: str, port: int) -> None:
        """连接到服务器（可在子线程调用）。"""
        with self._lock:  # 加锁防止并发 connect/disconnect
            if self._sock:  # 若已有连接则先关闭
                try:
                    self._sock.close()  # 关闭旧连接
                except OSError:
                    pass  # 忽略关闭异常
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建 TCP Socket
            sock.settimeout(30)  # 设置超时，避免永久阻塞
            sock.connect((host, port))  # 连接服务器 IP 与端口
            self._sock = sock  # 保存 Socket 引用
            self._logged_in = False  # 新连接需重新登录
        self._log(f"已连接服务器 {host}:{port}")  # 记录连接成功

    def disconnect(self) -> None:
        """断开与服务器的连接。"""
        with self._lock:  # 加锁
            if self._sock:  # 若存在 Socket
                try:
                    self._sock.close()  # 关闭连接
                except OSError:
                    pass  # 忽略异常
                self._sock = None  # 清空引用
            self._logged_in = False  # 重置登录状态
        self._log("已断开服务器连接")  # 记录断开

    def _require_socket(self) -> socket.socket:
        """获取当前 Socket，未连接时抛出异常。"""
        if not self._sock:  # 未连接
            raise ConnectionError("尚未连接服务器")  # 提示先连接
        return self._sock  # 返回 Socket

    def login(self, username: str, password: str) -> None:
        """发送登录请求并处理服务器响应（password 为 GUI 明文，发送前本地哈希）。"""
        sock = self._require_socket()  # 获取 Socket
        user_b = username.encode("utf-8")  # 用户名 UTF-8 编码
        # 本地哈希后再发送：网络上只传输 SHA-256 摘要，不传输明文密码
        pass_hash = hash_password(password, username)
        pass_b = pass_hash.encode("utf-8")  # 64 字节十六进制哈希字符串
        payload = struct.pack("!H", len(user_b)) + user_b  # 用户名长度+用户名
        payload += struct.pack("!H", len(pass_b)) + pass_b  # 哈希长度+哈希值
        with self._lock:  # 加锁发送
            send_frame(sock, CMD_LOGIN, payload)  # 发送 LOGIN 帧
            cmd, body = parse_header(sock)  # 等待 LOGIN_RESP

        if cmd != CMD_LOGIN_RESP:  # 响应类型不符
            raise ValueError("登录响应格式错误")  # 抛出异常

        status = body[0]  # 第 1 字节为状态码
        msg_len = struct.unpack("!H", body[1:3])[0]  # 2 字节消息长度
        message = body[3 : 3 + msg_len].decode("utf-8")  # 解码消息文本

        if status == AUTH_OK:  # 登录成功
            self._logged_in = True  # 更新登录状态
            self._log(f"登录成功: {username}")  # 写日志
            self._on_auth_result(True, message)  # 通知 UI 成功
        elif status == AUTH_USER_ERR:  # 用户名错误
            self._logged_in = False  # 保持未登录
            self._on_auth_result(False, "用户名错误")  # UI 弹窗提示
        elif status == AUTH_PASS_ERR:  # 密码错误
            self._logged_in = False  # 保持未登录
            self._on_auth_result(False, "密码错误")  # UI 弹窗提示
        else:  # 未知状态
            self._logged_in = False  # 未登录
            self._on_auth_result(False, message)  # 透传服务器消息

    def list_files(self) -> None:
        """请求服务器文件列表。"""
        if not self._logged_in:  # 必须先登录
            raise PermissionError("请先登录")  # 权限错误
        sock = self._require_socket()  # 获取 Socket
        with self._lock:  # 加锁
            send_frame(sock, CMD_LIST)  # 发送 LIST 命令（无 payload）
            cmd, body = parse_header(sock)  # 等待 LIST_RESP

        if cmd == CMD_ERROR:  # 服务器返回错误
            msg_len = struct.unpack("!I", body[0:4])[0]  # 错误消息长度
            err = body[4 : 4 + msg_len].decode("utf-8")  # 解码错误
            raise RuntimeError(err)  # 抛出给 UI 处理

        if cmd != CMD_LIST_RESP:  # 响应类型错误
            raise ValueError("列表响应格式错误")  # 异常

        count = struct.unpack("!I", body[0:4])[0]  # 文件数量
        offset = 4  # 解析偏移
        files: List[Dict[str, int]] = []  # 结果列表
        for _ in range(count):  # 遍历每个文件条目
            name_len = struct.unpack("!I", body[offset : offset + 4])[0]  # 名长
            offset += 4  # 偏移 +4
            size = struct.unpack("!Q", body[offset : offset + 8])[0]  # 8 字节大小
            offset += 8  # 偏移 +8
            name = body[offset : offset + name_len].decode("utf-8")  # 解码文件名
            offset += name_len  # 偏移跳过名称
            files.append({"name": name, "size": size})  # 追加到列表

        self._log(f"获取远端文件列表，共 {len(files)} 个文件")  # 日志
        self._on_file_list(files)  # 回调 UI 刷新列表

    def upload_file(self, local_path: str) -> None:
        """
        上传本地文件：先发 UPLOAD 元数据帧，再循环 read(4096)+send。
        """
        if not self._logged_in:  # 必须先登录
            raise PermissionError("请先登录后再上传")  # 权限检查
        if not os.path.isfile(local_path):  # 本地文件必须存在
            raise FileNotFoundError(f"本地文件不存在: {local_path}")  # 文件不存在

        filename = os.path.basename(local_path)  # 取文件名作为远端保存名
        file_size = os.path.getsize(local_path)  # 本地文件总大小
        name_b = filename.encode("utf-8")  # 文件名编码
        meta = struct.pack("!IQ", len(name_b), file_size) + name_b  # 打包元数据

        sock = self._require_socket()  # 获取 Socket
        with self._lock:  # 加锁保证发送原子性
            send_frame(sock, CMD_UPLOAD, meta)  # 发送 UPLOAD 头（含文件名与大小）

            sent = 0  # 已发送字节计数
            with open(local_path, "rb") as fp:  # 二进制只读打开本地文件
                while sent < file_size:  # 循环分块发送
                    chunk = fp.read(CHUNK_SIZE)  # 从文件读取 4096 字节到 Buffer
                    if not chunk:  # EOF 保护
                        break  # 退出循环
                    sock.sendall(chunk)  # 将 Buffer 写入 Socket 发送缓存
                    sent += len(chunk)  # 累加已发送量
                    percent = (sent / file_size) * 100.0  # 计算上传进度百分比
                    self._on_progress(percent, f"上传中: {filename}")  # 回调 UI 更新进度条

            cmd, body = parse_header(sock)  # 等待服务器上传完成 ACK 响应帧

        if cmd == CMD_ERROR:  # 服务器返回上传失败错误
            msg_len = struct.unpack("!I", body[0:4])[0]  # 解析错误消息长度
            err = body[4 : 4 + msg_len].decode("utf-8")  # 解码错误文本
            raise RuntimeError(err)  # 抛出异常，由 run_in_thread 通知 UI

        if cmd != CMD_UPLOAD_ACK:  # 响应类型必须为 UPLOAD_ACK
            raise ValueError("上传响应格式错误")  # 协议不一致时终止

        ack_status = body[0]  # ACK 第 1 字节为状态码，0 表示成功
        if ack_status != 0:  # 非 0 表示服务端保存失败
            raise RuntimeError("服务器保存文件失败")  # 向上层报告失败

        self._on_progress(100.0, f"上传完成: {filename}")  # 收到 ACK 后进度置 100%
        self._log(f"上传成功: {filename} ({file_size} 字节)")  # 写日志
        self._on_transfer_done(f"上传完成: {filename}")  # 通知 UI

    def download_file(self, remote_name: str) -> None:
        """
        下载远端文件：发 DOWNLOAD 请求，收元数据帧，再循环 recv(4096)+write。
        """
        if not self._logged_in:  # 必须先登录
            raise PermissionError("请先登录后再下载")  # 权限检查

        name_b = remote_name.encode("utf-8")  # 远端文件名编码
        meta = struct.pack("!IQ", len(name_b), 0) + name_b  # 请求时 size 填 0
        sock = self._require_socket()  # 获取 Socket

        with self._lock:  # 加锁
            send_frame(sock, CMD_DOWNLOAD, meta)  # 发送 DOWNLOAD 请求
            cmd, body = parse_header(sock)  # 接收服务器响应头

        if cmd == CMD_ERROR:  # 下载失败（如文件不存在）
            msg_len = struct.unpack("!I", body[0:4])[0]  # 错误消息长度
            err = body[4 : 4 + msg_len].decode("utf-8")  # 解码
            raise RuntimeError(err)  # 抛给 UI

        if cmd != CMD_DOWNLOAD:  # 响应类型应为 DOWNLOAD（含文件元数据）
            raise ValueError("下载响应格式错误")  # 格式错误

        name_len = struct.unpack("!I", body[0:4])[0]  # 文件名长度
        file_size = struct.unpack("!Q", body[4:12])[0]  # 文件总大小
        filename = body[12 : 12 + name_len].decode("utf-8")  # 解码文件名
        save_path = os.path.join(DOWNLOAD_DIR, os.path.basename(filename))  # 正式文件路径
        tmp_path = save_path + ".tmp"  # 下载未完成前只写临时文件，与服务端上传 .tmp 对称

        received = 0  # 已接收字节计数
        try:
            with self._lock:  # 加锁接收文件流
                with open(tmp_path, "wb") as fp:  # 先写入 .tmp，避免半成品污染 downloads
                    while received < file_size:  # 循环直到收满
                        to_read = min(CHUNK_SIZE, file_size - received)  # 末块大小
                        chunk = recv_exact(sock, to_read)  # 断线时抛出 ConnectionError
                        fp.write(chunk)  # 实时写入临时文件
                        received += len(chunk)  # 累加已接收量
                        percent = (received / file_size) * 100.0  # 计算下载进度
                        self._on_progress(percent, f"下载中: {filename}")  # 更新进度条
                # 全部字节收齐后原子 rename，与服务器 upload 完成策略一致
                os.rename(tmp_path, save_path)

        except (ConnectionError, ConnectionResetError, BrokenPipeError, OSError):
            # 下载中断：立即清理残缺 .tmp，防止 downloads 目录堆积垃圾文件
            if os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                    self._log(f"下载中断，已清理临时文件: {tmp_path}")
                except OSError:
                    pass
            raise  # 重新抛出，由 run_in_thread 通知 UI

        self._on_progress(100.0, f"下载完成: {filename}")  # 进度 100%
        self._log(f"下载成功: {filename} -> {save_path}")  # 写日志
        self._on_transfer_done(f"下载完成: {save_path}")  # 通知 UI

    def delete_file(self, remote_name: str) -> None:
        """请求服务器删除远端文件。"""
        if not self._logged_in:  # 必须先登录
            raise PermissionError("请先登录后再删除")  # 权限检查

        name_b = remote_name.encode("utf-8")  # 文件名 UTF-8 编码
        meta = struct.pack("!IQ", len(name_b), 0) + name_b  # 请求元数据（size 填 0）
        sock = self._require_socket()  # 获取 Socket

        with self._lock:  # 加锁发送删除请求
            send_frame(sock, CMD_DELETE, meta)  # 发送 DELETE 命令帧
            cmd, body = parse_header(sock)  # 等待 DELETE_RESP 或 ERROR

        if cmd == CMD_ERROR:  # 删除失败
            msg_len = struct.unpack("!I", body[0:4])[0]  # 错误消息长度
            err = body[4 : 4 + msg_len].decode("utf-8")  # 解码错误文本
            raise RuntimeError(err)  # 抛给 UI 处理

        if cmd != CMD_DELETE_RESP:  # 响应类型错误
            raise ValueError("删除响应格式错误")  # 格式异常

        status = body[0]  # 第 1 字节为状态码，0 表示成功
        msg_len = struct.unpack("!H", body[1:3])[0]  # 2 字节消息长度
        message = body[3 : 3 + msg_len].decode("utf-8")  # 解码消息
        if status != 0:  # 非 0 表示失败
            raise RuntimeError(message or "删除失败")  # 抛出异常

        self._log(message)  # 写日志
        self._on_transfer_done(message)  # 通知 UI 刷新列表

    def run_in_thread(self, target: Callable[[], None], task_name: str = "任务") -> None:
        """
        在独立守护子线程中执行阻塞网络任务，确保 GUI 主线程不被阻塞。
        """

        def wrapper() -> None:
            """线程包装器：捕获异常并通过回调通知 UI。"""
            try:
                target()  # 执行实际任务函数
            except Exception as exc:  # 捕获所有异常
                msg = f"{task_name}失败: {exc}"  # 组装错误信息
                self._log(msg)  # 写日志
                self._on_error(msg)  # 触发错误回调（UI 弹窗）

        thread = threading.Thread(target=wrapper, daemon=True)  # 创建守护线程
        thread.start()  # 启动子线程，主线程立即返回
