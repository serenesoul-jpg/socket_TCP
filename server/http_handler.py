#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP Web 界面：浏览器访问 8082 端口，与 FTCP 共用 storage 与 SQLite 数据库。"""

import json  # JSON 编解码
import os  # 路径与文件操作
import secrets  # 生成安全 Session Token
import threading  # Session 字典线程锁
import urllib.parse  # URL 解码文件名等参数
from http.server import BaseHTTPRequestHandler  # HTTP 请求处理基类
from typing import Dict, Optional, Tuple  # 类型注解

import database  # SQLite 用户与文件元数据（与 FTCP 共用）

CHUNK_SIZE = 4096  # 与 TCP 服务一致的分块大小
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # server 目录
WEB_DIR = os.path.join(BASE_DIR, "web")  # 网页静态资源目录
INDEX_FILE = os.path.join(WEB_DIR, "index.html")  # 主页面文件

_sessions: Dict[str, str] = {}  # session_token -> username 映射表
_session_lock = threading.Lock()  # 保护 _sessions 的并发访问锁


def _verify_login(username: str, password_hash: str) -> Tuple[bool, str]:
    """
    验证登录：password_hash 为客户端预计算的 SHA-256 摘要（非明文）。
    委托 database.authenticate 做零知识字符串比对。
    """
    return database.authenticate(username, password_hash)


def _create_session(username: str) -> str:
    """创建 Session 并返回 Token。"""
    token = secrets.token_hex(16)  # 生成 32 位十六进制随机 Token
    with _session_lock:  # 加锁写入 Session 表
        _sessions[token] = username  # 绑定 Token 与用户名
    return token  # 返回 Token 供 Set-Cookie 使用


def _get_session_user(cookie_header: str) -> Optional[str]:
    """从 Cookie 头解析 Session 并返回用户名。"""
    if not cookie_header:  # 无 Cookie 则未登录
        return None  # 返回空
    for part in cookie_header.split(";"):  # 拆分多个 Cookie 项
        part = part.strip()  # 去掉首尾空格
        if part.startswith("session="):  # 找到 session Cookie
            token = part.split("=", 1)[1].strip()  # 提取 Token 值
            with _session_lock:  # 加锁读取 Session 表
                return _sessions.get(token)  # 返回对应用户名或 None
    return None  # 未找到有效 Session


def _list_storage_files():
    """
    从 SQLite files_meta 表读取文件列表（与 FTCP handle_list 数据源一致）。
    Web 端仅展示 name 与 size，uploader/upload_time 可按需扩展至前端。
    """
    records = database.list_files()
    return [{"name": r["name"], "size": r["size"]} for r in records]


def _normalize_path(raw_path: str) -> str:
    """规范化请求路径，去除 query 与末尾斜杠。"""
    path = urllib.parse.urlparse(raw_path).path  # 仅保留路径部分
    path = path.rstrip("/")  # 去掉末尾 /
    return path or "/"  # 根路径兜底


def _delete_storage_file(storage_dir: str, name: str) -> Tuple[bool, str, Optional[str]]:
    """
    删除 storage 中文件并同步移除 SQLite 元数据。
    先查数据库再删磁盘，保证 list 与 delete 语义一致。
    """
    safe_name = os.path.basename(str(name).strip())  # 安全化文件名
    if not safe_name:  # 文件名为空
        return False, "文件名不能为空", None  # 参数错误

    meta = database.get_file_meta(safe_name)
    file_path = os.path.join(storage_dir, safe_name)
    if meta is None and not os.path.isfile(file_path):
        return False, "文件不存在", safe_name  # 库与磁盘均无此文件

    if os.path.isfile(file_path):
        os.remove(file_path)  # 删除磁盘文件
    database.delete_file_meta(safe_name)  # 删除数据库记录
    print(f"[HTTP删除] {safe_name}")  # 控制台日志
    return True, "删除成功", safe_name  # 删除成功


API_VERSION = "1.1.0"  # API 版本（含删除接口）


def _read_index_html() -> bytes:
    """读取主页 HTML 内容。"""
    with open(INDEX_FILE, "rb") as fp:  # 二进制读取 HTML
        return fp.read()  # 返回字节内容


class WebHTTPHandler(BaseHTTPRequestHandler):
    """处理浏览器 HTTP 请求，提供页面与 REST API。"""

    storage_dir = STORAGE_DIR = os.path.join(BASE_DIR, "storage")  # 文件存储目录

    def log_message(self, format: str, *args) -> None:
        """将 HTTP 访问日志输出到控制台。"""
        print(f"[HTTP] {self.address_string()} - {format % args}")  # 打印访问记录

    def _send_json(self, code: int, payload: dict) -> None:
        """发送 JSON 响应。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")  # 序列化为 UTF-8 JSON
        self.send_response(code)  # 发送 HTTP 状态码
        self.send_header("Content-Type", "application/json; charset=utf-8")  # 声明 JSON 类型
        self.send_header("Content-Length", str(len(body)))  # 设置内容长度
        self.end_headers()  # 结束响应头
        self.wfile.write(body)  # 写入响应体

    def _send_html(self, code: int, body: bytes) -> None:
        """发送 HTML 页面响应。"""
        self.send_response(code)  # HTTP 状态码
        self.send_header("Content-Type", "text/html; charset=utf-8")  # HTML 类型
        self.send_header("Content-Length", str(len(body)))  # 内容长度
        self.end_headers()  # 结束响应头
        self.wfile.write(body)  # 写入页面内容

    def _require_user(self) -> Optional[str]:
        """校验登录态，未登录则返回 401 JSON。"""
        user = _get_session_user(self.headers.get("Cookie", ""))  # 从 Cookie 取用户
        if not user:  # 未登录
            self._send_json(401, {"ok": False, "message": "请先登录"})  # 返回 401
            return None  # 终止后续处理
        return user  # 返回已登录用户名

    def _read_body(self) -> bytes:
        """读取 POST/DELETE 请求体。"""
        length = int(self.headers.get("Content-Length", "0") or "0")  # 内容长度
        return self.rfile.read(length) if length > 0 else b""  # 读取字节

    def _handle_delete_api(self, name: str) -> None:
        """统一处理删除文件 API。"""
        if not self._require_user():  # 必须登录
            return  # 未登录
        ok, message, safe_name = _delete_storage_file(self.storage_dir, name)  # 执行删除
        if not ok:  # 删除失败
            code = 404 if message == "文件不存在" else 400  # 选择 HTTP 状态码
            self._send_json(code, {"ok": False, "message": message})  # 返回错误
            return  # 结束
        self._send_json(200, {"ok": True, "message": message, "name": safe_name})  # 返回成功

    def do_GET(self) -> None:
        """处理 GET 请求：主页、文件列表、文件下载、版本检查。"""
        parsed = urllib.parse.urlparse(self.path)  # 解析 URL
        path = _normalize_path(parsed.path)  # 规范化路径

        if path in ("/", "/index.html"):  # 访问首页
            self._send_html(200, _read_index_html())  # 返回 Web 界面
            return  # 结束处理

        if path == "/api/version":  # API 版本（用于确认服务端已更新）
            self._send_json(200, {"ok": True, "version": API_VERSION, "features": ["login", "upload", "download", "delete", "list"]})
            return  # 结束

        if path == "/api/files":  # 获取远端文件列表 API
            if not self._require_user():  # 需要登录
                return  # 未登录已返回 401
            files = _list_storage_files()  # 从 SQLite 查询文件列表
            self._send_json(200, {"ok": True, "files": files})  # 返回 JSON 列表
            return  # 结束

        if path == "/api/download":  # 文件下载 API
            if not self._require_user():  # 需要登录
                return  # 未登录
            query = urllib.parse.parse_qs(parsed.query)  # 解析查询参数
            name = query.get("name", [""])[0]  # 取 name 参数
            safe_name = os.path.basename(name)  # 安全化文件名
            file_path = os.path.join(self.storage_dir, safe_name)  # 本地路径
            # 下载前校验：数据库有记录且磁盘文件存在
            if database.get_file_meta(safe_name) is None or not os.path.isfile(file_path):
                self._send_json(404, {"ok": False, "message": "文件不存在"})  # 404
                return  # 结束
            size = os.path.getsize(file_path)  # 文件大小
            self.send_response(200)  # 200 OK
            self.send_header("Content-Type", "application/octet-stream")  # 二进制流
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{urllib.parse.quote(safe_name)}"',
            )  # 触发浏览器下载
            self.send_header("Content-Length", str(size))  # 内容长度
            self.end_headers()  # 结束响应头
            with open(file_path, "rb") as fp:  # 打开本地文件
                sent = 0  # 已发送计数
                while sent < size:  # 循环分块发送
                    chunk = fp.read(CHUNK_SIZE)  # 读取 4096 字节 Buffer
                    if not chunk:  # EOF 保护
                        break  # 退出
                    self.wfile.write(chunk)  # 写入 HTTP 响应体
                    sent += len(chunk)  # 累加已发送字节
            print(f"[HTTP下载] {safe_name} ({size} 字节)")  # 控制台日志
            return  # 结束

        self._send_json(404, {"ok": False, "message": "接口不存在"})  # 未知路径

    def do_POST(self) -> None:
        """处理 POST 请求：登录、上传、删除、退出。"""
        path = _normalize_path(self.path)  # 规范化路径
        body = self._read_body()  # 读取请求体

        if path == "/api/login":  # 登录 API
            try:
                data = json.loads(body.decode("utf-8"))  # 解析 JSON 请求体
            except json.JSONDecodeError:  # JSON 格式错误
                self._send_json(400, {"ok": False, "message": "请求格式错误"})  # 400
                return  # 结束
            username = str(data.get("username", "")).strip()  # 取用户名
            password_hash = str(data.get("password", ""))  # 客户端预哈希，非明文
            ok, message = _verify_login(username, password_hash)  # 零知识比对
            if not ok:  # 登录失败
                self._send_json(401, {"ok": False, "message": message})  # 返回具体错误
                return  # 结束
            token = _create_session(username)  # 创建 Session
            self.send_response(200)  # 200 OK
            self.send_header("Content-Type", "application/json; charset=utf-8")  # JSON 类型
            self.send_header("Set-Cookie", f"session={token}; Path=/; HttpOnly; SameSite=Lax")  # 写 Cookie
            resp = json.dumps({"ok": True, "message": message}, ensure_ascii=False).encode("utf-8")  # 响应体
            self.send_header("Content-Length", str(len(resp)))  # 长度
            self.end_headers()  # 结束头
            self.wfile.write(resp)  # 发送 JSON
            print(f"[HTTP登录] 用户 {username} 登录成功")  # 日志
            return  # 结束

        if path == "/api/upload":  # 上传 API
            if not self._require_user():  # 必须登录
                return  # 未登录
            uploader = _get_session_user(self.headers.get("Cookie", "")) or "unknown"
            content_type = self.headers.get("Content-Type", "")  # 获取 Content-Type
            if "multipart/form-data" not in content_type:  # 必须是 multipart 表单
                self._send_json(400, {"ok": False, "message": "请使用 multipart 上传"})  # 400
                return  # 结束
            boundary = content_type.split("boundary=", 1)[1].strip()  # 提取 boundary
            filename, file_data = _parse_multipart(body, boundary.encode("utf-8"))  # 解析文件
            if not filename or file_data is None:  # 未解析到文件
                self._send_json(400, {"ok": False, "message": "未找到上传文件"})  # 400
                return  # 结束
            safe_name = os.path.basename(filename)  # 安全文件名
            save_path = os.path.join(self.storage_dir, safe_name)  # 正式文件路径
            tmp_path = save_path + ".tmp"  # HTTP 上传同样先写临时文件，成功后 rename

            try:
                with open(tmp_path, "wb") as fp:  # 写入临时文件
                    fp.write(file_data)
                os.rename(tmp_path, save_path)  # 完整写入后原子重命名
                database.insert_file_meta(safe_name, uploader, len(file_data))  # 写入 SQLite
            except OSError as exc:
                # 写入失败时清理 .tmp，与 FTCP 断线清理策略一致
                if os.path.isfile(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                self._send_json(500, {"ok": False, "message": f"保存文件失败: {exc}"})
                return

            print(f"[HTTP上传] {safe_name} ({len(file_data)} 字节) 上传者: {uploader}")  # 日志
            self._send_json(200, {"ok": True, "message": "上传完成", "name": safe_name, "size": len(file_data)})  # ACK
            return  # 结束

        if path == "/api/delete":  # 删除文件 API（POST JSON）
            try:
                data = json.loads(body.decode("utf-8") or "{}")  # 解析 JSON
            except json.JSONDecodeError:
                self._send_json(400, {"ok": False, "message": "请求格式错误"})
                return
            self._handle_delete_api(str(data.get("name", "")))  # 调用统一删除逻辑
            return  # 结束

        if path == "/api/logout":  # 退出登录
            cookie = self.headers.get("Cookie", "")  # 读取 Cookie
            for part in cookie.split(";"):  # 遍历 Cookie
                part = part.strip()  # 去空格
                if part.startswith("session="):  # 找到 session
                    token = part.split("=", 1)[1].strip()  # Token 值
                    with _session_lock:  # 加锁删除 Session
                        _sessions.pop(token, None)  # 移除 Session
            self.send_response(200)  # 200 OK
            self.send_header("Set-Cookie", "session=; Path=/; Max-Age=0")  # 清除 Cookie
            self.send_header("Content-Type", "application/json; charset=utf-8")  # JSON
            resp = json.dumps({"ok": True, "message": "已退出"}, ensure_ascii=False).encode("utf-8")  # 响应体
            self.send_header("Content-Length", str(len(resp)))  # 长度
            self.end_headers()  # 结束头
            self.wfile.write(resp)  # 发送
            return  # 结束

        self._send_json(404, {"ok": False, "message": "接口不存在", "path": path})  # 未知 POST 路径

    def do_DELETE(self) -> None:
        """处理 DELETE 请求：/api/delete?name=xxx（兼容部分客户端/代理）。"""
        parsed = urllib.parse.urlparse(self.path)  # 解析 URL
        path = _normalize_path(parsed.path)  # 规范化路径
        if path != "/api/delete":  # 非删除路径
            self._send_json(404, {"ok": False, "message": "接口不存在", "path": path})
            return  # 结束
        query = urllib.parse.parse_qs(parsed.query)  # 解析查询参数
        name = query.get("name", [""])[0]  # 取文件名
        if not name:  # 尝试从 body 读取
            try:
                body = self._read_body()
                data = json.loads(body.decode("utf-8") or "{}")
                name = str(data.get("name", ""))
            except (json.JSONDecodeError, UnicodeDecodeError):
                name = ""
        self._handle_delete_api(name)  # 统一删除逻辑


def _parse_multipart(body: bytes, boundary: bytes) -> Tuple[str, Optional[bytes]]:
    """简易 multipart/form-data 解析，提取第一个文件字段。"""
    delimiter = b"--" + boundary  # multipart 分隔符
    parts = body.split(delimiter)  # 按分隔符切块
    for part in parts:  # 遍历每个 part
        if b"filename=" not in part:  # 跳过非文件字段
            continue  # 下一个
        header_block, _, content = part.partition(b"\r\n\r\n")  # 分离头与内容
        if not content:  # 无内容
            continue  # 下一个
        header_text = header_block.decode("utf-8", errors="ignore")  # 解码头部
        filename = ""  # 初始化文件名
        for line in header_text.split("\r\n"):  # 逐行解析头
            if "filename=" in line:  # Content-Disposition 行
                filename = line.split("filename=", 1)[1].strip().strip('"')  # 提取文件名
                break  # 找到即停
        file_data = content.rstrip(b"\r\n--")  # 去掉尾部边界残留
        if file_data.endswith(b"\r\n"):  # 去掉末尾换行
            file_data = file_data[:-2]  # 移除 \r\n
        return filename, file_data  # 返回文件名与二进制内容
    return "", None  # 未找到文件


def handle_http_connection(conn, addr: Tuple[str, int]) -> None:
    """在已 accept 的连接上处理 HTTP 请求。"""
    print(f"[HTTP连接] {addr[0]}:{addr[1]} 浏览器接入")  # 记录 HTTP 连接
    try:
        conn.settimeout(60)  # 设置读写超时，避免僵死连接
        handler = WebHTTPHandler(conn, addr, None)  # 基于已有 Socket 构造 HTTP 处理器
        handler.handle()  # 解析请求并生成响应
    except Exception as exc:  # 捕获 HTTP 处理异常
        print(f"[HTTP异常] {addr[0]}:{addr[1]} -> {exc}")  # 打印错误
    finally:
        try:
            conn.close()  # 关闭连接
        except OSError:
            pass  # 忽略关闭异常
