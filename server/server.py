#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCP 文件传输服务器：多线程并发、身份验证、分块文件读写。"""

import os  # 导入 os 模块，用于路径拼接与目录创建
import socket  # 导入 socket 模块，提供 TCP 网络编程能力
import struct  # 导入 struct 模块，用于二进制报文头的打包与解包
import threading  # 导入 threading 模块，实现多客户端并发处理
from typing import Optional, Tuple  # 导入类型注解，提升代码可读性

import database  # SQLite 用户凭证与文件元数据持久化
from http_handler import handle_http_connection  # 浏览器 HTTP 请求处理
from prefixed_socket import PrefixedSocket  # 带前缀缓冲的 Socket 包装器

# ===================== 协议常量定义 =====================
MAGIC = b"FTCP"  # 魔数标识，用于校验是否为合法协议帧
VERSION = 1  # 协议版本号，便于后续扩展
HEADER_SIZE = 10  # 固定报文头长度：4+1+1+4=10 字节
CHUNK_SIZE = 4096  # 分块读写缓存大小，对齐实验要求的 4096 字节 Buffer

# 命令字定义：区分登录、列表、上传、下载等操作类型
CMD_LOGIN = 0x01  # 客户端发起登录验证
CMD_LOGIN_RESP = 0x02  # 服务器返回登录结果
CMD_LIST = 0x03  # 客户端请求远端文件列表
CMD_LIST_RESP = 0x04  # 服务器返回文件列表
CMD_UPLOAD = 0x05  # 客户端发起文件上传
CMD_DOWNLOAD = 0x06  # 客户端发起文件下载
CMD_ERROR = 0x07  # 服务器返回通用错误信息
CMD_UPLOAD_ACK = 0x08  # 服务器确认上传完成
CMD_DELETE = 0x09  # 客户端请求删除远端文件
CMD_DELETE_RESP = 0x0A  # 服务器返回删除结果

# 登录结果状态码：必须细分用户名错误与密码错误
AUTH_OK = 0  # 验证成功
AUTH_USER_ERR = 1  # 用户名不存在
AUTH_PASS_ERR = 2  # 密码不匹配

# 服务器监听地址与端口（实验要求公网可访问）
HOST = "0.0.0.0"  # 绑定所有网卡，允许公网连接
PORT = 8082  # 监听端口 8082

# 当前脚本所在目录，用于定位 users.json 与 storage 目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 获取 server.py 所在绝对路径
STORAGE_DIR = os.path.join(BASE_DIR, "storage")  # 服务端文件存储目录路径


def ensure_storage_dir() -> None:
    """若 storage 目录不存在则自动创建。"""
    os.makedirs(STORAGE_DIR, exist_ok=True)  # exist_ok=True 避免目录已存在时报错


def recv_exact(conn: socket.socket, size: int) -> bytes:
    """
    精确接收 size 字节，解决 TCP 粘包/半包问题。
    循环 recv 直到凑满指定长度或连接断开。
    """
    chunks = []  # 存放每次 recv 得到的字节片段
    received = 0  # 已累计接收的字节数
    while received < size:  # 未收满则继续循环读取
        part = conn.recv(size - received)  # 从内核接收缓存读取剩余所需字节
        if not part:  # 对端关闭连接时 recv 返回空字节
            raise ConnectionError("连接已关闭，无法继续接收数据")  # 抛出异常终止当前会话
        chunks.append(part)  # 将本次读到的片段追加到列表
        received += len(part)  # 更新已接收总长度
    return b"".join(chunks)  # 拼接所有片段为完整字节串


def send_frame(conn: socket.socket, cmd: int, payload: bytes = b"") -> None:
    """发送一帧完整报文：固定头 + 变长 payload。"""
    header = struct.pack("!4sBBI", MAGIC, VERSION, cmd, len(payload))  # 大端序打包报文头
    conn.sendall(header + payload)  # sendall 保证整帧数据全部写入发送缓存


def parse_header(conn: socket.socket) -> Tuple[int, bytes]:
    """接收并解析固定长度报文头，返回 (命令字, payload)。"""
    header = recv_exact(conn, HEADER_SIZE)  # 先精确读取 10 字节固定头
    magic, version, cmd, payload_len = struct.unpack("!4sBBI", header)  # 解包得到各字段
    if magic != MAGIC:  # 魔数不匹配说明非本协议数据
        raise ValueError("非法协议魔数，拒绝处理")  # 抛出异常断开异常连接
    if version != VERSION:  # 版本不一致时拒绝服务
        raise ValueError(f"不支持的协议版本: {version}")  # 提示版本错误
    payload = recv_exact(conn, payload_len) if payload_len > 0 else b""  # 按长度读取 payload
    return cmd, payload  # 返回命令字与负载数据


def send_login_response(conn: socket.socket, status: int, message: str) -> None:
    """向客户端发送登录验证结果（含细分错误信息）。"""
    msg_bytes = message.encode("utf-8")  # 将中文提示转为 UTF-8 字节
    body = struct.pack("!BH", status, len(msg_bytes)) + msg_bytes  # 状态码+消息长度+消息体
    send_frame(conn, CMD_LOGIN_RESP, body)  # 封装为 LOGIN_RESP 帧发送


def send_error(conn: socket.socket, message: str) -> None:
    """发送通用错误帧。"""
    msg_bytes = message.encode("utf-8")  # 错误信息 UTF-8 编码
    body = struct.pack("!I", len(msg_bytes)) + msg_bytes  # 4 字节长度 + 消息
    send_frame(conn, CMD_ERROR, body)  # 以 ERROR 命令发送


def handle_login(conn: socket.socket, payload: bytes) -> Tuple[bool, Optional[str]]:
    """
    处理登录请求，返回 (是否验证成功, 用户名或 None)。

    传输安全：payload 中 password 字段为客户端预计算的 SHA-256 哈希（非明文），
    服务端直接做零知识比对，抓包无法获得原始密码。

    payload 格式：username_len(2) + username + password_hash_len(2) + password_hash
    """
    offset = 0  # payload 解析偏移量
    user_len = struct.unpack("!H", payload[offset : offset + 2])[0]  # 读取用户名长度（2 字节）
    offset += 2  # 偏移前进 2 字节
    username = payload[offset : offset + user_len].decode("utf-8")  # 截取并解码用户名
    offset += user_len  # 偏移跳过用户名字节
    pass_len = struct.unpack("!H", payload[offset : offset + 2])[0]  # 读取哈希字符串长度
    offset += 2  # 偏移前进 2 字节
    password_hash = payload[offset : offset + pass_len].decode("utf-8")  # 客户端预哈希，非明文

    # 零知识比对：client_hash == stored_hash，服务端永不接触明文密码
    ok, message = database.authenticate(username, password_hash)
    if not ok:
        # 根据错误消息映射到 FTCP 协议状态码，保持与旧版客户端兼容
        if message == "用户名错误":
            send_login_response(conn, AUTH_USER_ERR, message)
        else:
            send_login_response(conn, AUTH_PASS_ERR, message)
        return False, None  # 登录失败，无有效用户名

    send_login_response(conn, AUTH_OK, "登录成功")  # 验证通过，返回成功状态
    return True, username  # 登录成功，返回用户名供后续上传记录 uploader


def parse_file_meta(payload: bytes) -> Tuple[str, int]:
    """从 payload 解析文件名与文件总大小。格式：name_len(4) + file_size(8) + filename。"""
    name_len = struct.unpack("!I", payload[0:4])[0]  # 前 4 字节为文件名长度
    file_size = struct.unpack("!Q", payload[4:12])[0]  # 紧随其后的 8 字节为文件总大小
    filename = payload[12 : 12 + name_len].decode("utf-8")  # 再后为 UTF-8 文件名
    return filename, file_size  # 返回元数据元组


def handle_upload(conn: socket.socket, payload: bytes, uploader: str) -> None:
    """
    处理文件上传：先写入 .tmp 临时文件，完整接收后再 rename 为正式文件。

    断点异常处理（残缺文件清理）设计要点：
    1. 接收过程中一律写入 storage/filename.tmp，避免半成品污染正式目录。
    2. recv_exact 在 ConnectionResetError / ConnectionError 等断线时会抛出异常。
    3. except 块立即 os.remove(tmp_path)，释放磁盘空间，防止残缺文件堆积。
    4. 仅当全部字节收齐并成功发送 CMD_UPLOAD_ACK 前，才 rename + 写 SQLite。
    """
    filename, file_size = parse_file_meta(payload)  # 从报文头 payload 解析文件名与大小
    safe_name = os.path.basename(filename)  # 仅保留 basename，防止路径穿越攻击
    save_path = os.path.join(STORAGE_DIR, safe_name)  # 正式文件最终路径
    tmp_path = save_path + ".tmp"  # 临时文件路径，上传未完成前仅写此处

    received = 0  # 已接收文件字节计数
    try:
        with open(tmp_path, "wb") as fp:  # 以二进制写模式打开临时文件
            while received < file_size:  # 循环直到收满 file_size 字节
                to_read = min(CHUNK_SIZE, file_size - received)  # 末块可能不足 4096 字节
                chunk = recv_exact(conn, to_read)  # 断线时此处抛出 ConnectionError 等
                fp.write(chunk)  # 实时写入临时文件
                received += len(chunk)  # 累加已接收字节数

        # 全部字节接收完毕：原子 rename 将 .tmp 转为正式文件（同目录下为原子操作）
        os.rename(tmp_path, save_path)

        # 写入 SQLite 文件元数据（上传者、时间、大小）
        database.insert_file_meta(safe_name, uploader, file_size)

        print(f"[上传完成] {safe_name} ({file_size} 字节) 上传者: {uploader}")

        # 上传 ACK 响应帧 payload：status(1) + file_size(8) + name_len(4) + filename
        name_bytes = safe_name.encode("utf-8")
        ack_body = struct.pack("!BQI", 0, file_size, len(name_bytes)) + name_bytes
        send_frame(conn, CMD_UPLOAD_ACK, ack_body)  # 向客户端发送上传完成确认帧

    except (ConnectionError, ConnectionResetError, BrokenPipeError, OSError) as exc:
        # 断线或 I/O 异常：清理 .tmp 残留，避免占用硬盘
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)  # 删除未完成的临时文件
                print(f"[上传中断] 已清理残缺临时文件: {tmp_path} ({exc})")
            except OSError as rm_err:
                print(f"[上传中断] 清理临时文件失败: {tmp_path} -> {rm_err}")
        raise  # 重新抛出，由 client_handler 外层统一记录断开日志


def handle_download(conn: socket.socket, payload: bytes) -> None:
    """
    处理文件下载：读取本地文件，先发元数据帧，再分块 send 文件内容。
    """
    filename, _ = parse_file_meta(payload)  # 解析客户端请求的文件名（size 字段此处可忽略）
    safe_name = os.path.basename(filename)  # 安全化文件名
    file_path = os.path.join(STORAGE_DIR, safe_name)  # 服务端文件绝对路径

    if not os.path.isfile(file_path):  # 文件不存在
        send_error(conn, f"文件不存在: {safe_name}")  # 返回错误帧
        return  # 结束下载处理

    file_size = os.path.getsize(file_path)  # 获取本地文件总大小
    name_bytes = safe_name.encode("utf-8")  # 文件名 UTF-8 编码
    meta = struct.pack("!IQ", len(name_bytes), file_size) + name_bytes  # 打包元数据 payload
    send_frame(conn, CMD_DOWNLOAD, meta)  # 先发送 DOWNLOAD 响应帧（含文件元信息）

    sent = 0  # 已发送字节计数
    with open(file_path, "rb") as fp:  # 以二进制只读打开本地文件
        while sent < file_size:  # 循环直到发完整个文件
            chunk = fp.read(CHUNK_SIZE)  # 从本地文件读取 4096 字节到 Buffer
            if not chunk:  # 意外 EOF 保护
                break  # 跳出循环
            conn.sendall(chunk)  # 将缓存数据写入 Socket 发送队列
            sent += len(chunk)  # 累加已发送字节数

    print(f"[下载完成] {safe_name} ({file_size} 字节)")  # 控制台记录下载日志


def handle_list(conn: socket.socket) -> None:
    """从 SQLite files_meta 表读取文件列表并返回（不再扫描纯文件系统）。"""
    records = database.list_files()  # 查询数据库中的文件元数据
    body = struct.pack("!I", len(records))  # 前 4 字节为文件数量
    for item in records:  # 逐个序列化文件条目
        name = item["name"]
        size = item["size"]
        name_bytes = name.encode("utf-8")  # 文件名转字节
        body += struct.pack("!IQ", len(name_bytes), size) + name_bytes  # 长度+大小+名称

    send_frame(conn, CMD_LIST_RESP, body)  # 发送 LIST_RESP 帧


def handle_delete(conn: socket.socket, payload: bytes) -> None:
    """删除 storage 目录中的指定文件，并同步移除 SQLite 元数据记录。"""
    filename, _ = parse_file_meta(payload)  # 解析要删除的文件名
    safe_name = os.path.basename(filename)  # 安全化文件名，防止路径穿越
    file_path = os.path.join(STORAGE_DIR, safe_name)  # 服务端文件完整路径

    # 以数据库记录为准判断文件是否存在（与 list 接口保持一致）
    if database.get_file_meta(safe_name) is None and not os.path.isfile(file_path):
        send_error(conn, f"文件不存在: {safe_name}")  # 返回错误帧
        return  # 结束删除

    if os.path.isfile(file_path):
        os.remove(file_path)  # 从磁盘删除文件
    database.delete_file_meta(safe_name)  # 删除数据库元数据（即使磁盘已无文件也清理记录）
    print(f"[删除完成] {safe_name}")  # 控制台记录删除日志

    msg_bytes = f"已删除: {safe_name}".encode("utf-8")  # 成功消息 UTF-8 编码
    body = struct.pack("!BH", 0, len(msg_bytes)) + msg_bytes  # status(0)+消息长度+消息
    send_frame(conn, CMD_DELETE_RESP, body)  # 发送 DELETE_RESP 确认帧


def client_handler(conn: socket.socket, addr: Tuple[str, int]) -> None:
    """单个 FTCP 客户端连接的处理线程入口。"""
    print(f"[FTCP连接] {addr[0]}:{addr[1]} 已接入")  # 打印客户端地址

    # 死连接防范：120 秒内无任何 recv/send 活动则抛 socket.timeout，避免线程永久阻塞
    # 理论意义：异常离线客户端若不设超时，parse_header 的 recv 将无限挂起，耗尽线程池
    conn.settimeout(120.0)

    authenticated = False  # 当前连接是否已通过身份验证
    current_user: Optional[str] = None  # 登录成功后记录用户名，供上传时写入 uploader 字段

    try:
        while True:  # 持续处理该客户端的多条命令
            cmd, payload = parse_header(conn)  # 解析一帧完整报文

            if cmd == CMD_LOGIN:  # 登录命令
                authenticated, current_user = handle_login(conn, payload)  # 哈希验证并更新状态
                continue  # 继续等待下一条命令

            if not authenticated:  # 未登录则拒绝文件类操作
                send_error(conn, "请先登录后再进行文件操作")  # 返回未授权错误
                continue  # 不断开连接，允许用户重新登录

            if cmd == CMD_LIST:  # 列表命令
                handle_list(conn)  # 从 SQLite 返回文件列表
            elif cmd == CMD_UPLOAD:  # 上传命令
                handle_upload(conn, payload, current_user or "unknown")  # .tmp 安全上传
            elif cmd == CMD_DOWNLOAD:  # 下载命令
                handle_download(conn, payload)  # 发送文件流给客户端
            elif cmd == CMD_DELETE:  # 删除命令
                handle_delete(conn, payload)  # 删除 storage 中的文件
            else:  # 未知命令字
                send_error(conn, f"未知命令: {cmd}")  # 返回错误提示

    except socket.timeout:  # 120s 无活动：主动释放线程与 Socket，防止资源枯竭
        print(f"[超时] {addr[0]}:{addr[1]} 120s 无活动，主动断开")
    except (ConnectionError, ConnectionResetError, BrokenPipeError):  # 客户端正常或异常断开
        print(f"[断开] {addr[0]}:{addr[1]} 连接关闭")  # 记录断开日志
    except Exception as exc:  # 捕获其他未预期异常
        print(f"[异常] {addr[0]}:{addr[1]} -> {exc}")  # 打印异常信息
    finally:
        try:
            conn.close()  # 无论何种情况都关闭 Socket 释放资源
        except OSError:
            pass  # 忽略重复关闭时的异常


def _is_http_peek(peek: bytes) -> bool:
    """根据连接首 4 字节判断是否为浏览器 HTTP 请求。"""
    if not peek or len(peek) < 4:  # 数据不足则无法判断
        return False  # 默认按 FTCP 处理
    http_methods = (b"GET ", b"POST", b"HEAD", b"PUT ", b"DELE", b"OPTI")  # 常见 HTTP 方法前缀
    return any(peek.startswith(m) for m in http_methods)  # 匹配任一 HTTP 前缀


def dispatch_connection(client_conn: socket.socket, client_addr: Tuple[str, int]) -> None:
    """
    协议分流：同一 8082 端口同时支持 FTCP 客户端与浏览器 HTTP。
    通过 MSG_PEEK 窥探首 4 字节，FTCP 魔数为 FTCP，浏览器为 GET/POST 等。
    """
    try:
        peek = client_conn.recv(4, socket.MSG_PEEK)  # 窥探首 4 字节，不消耗接收缓冲
    except OSError:  # 连接异常或已关闭
        client_conn.close()  # 关闭无效连接
        return  # 结束分流

    if not peek:  # 对端直接关闭
        client_conn.close()  # 关闭连接
        return  # 结束

    if _is_http_peek(peek):  # 识别为 HTTP 浏览器请求
        worker = threading.Thread(  # 独立线程处理 HTTP
            target=handle_http_connection,  # HTTP 处理函数
            args=(client_conn, client_addr),  # 传入连接与地址
            daemon=True,  # 守护线程
        )
        worker.start()  # 启动 HTTP 工作线程
        return  # 分流完成

    if peek == MAGIC:  # FTCP 自定义协议魔数
        wrapped = PrefixedSocket(client_conn)  # 包装 Socket（窥探未消耗，可直接读）
        worker = threading.Thread(  # 独立线程处理 FTCP
            target=client_handler,  # FTCP 客户端处理函数
            args=(wrapped, client_addr),  # 传入包装后的连接
            daemon=True,  # 守护线程
        )
        worker.start()  # 启动 FTCP 工作线程
        return  # 分流完成

    print(f"[拒绝] {client_addr[0]}:{client_addr[1]} 未知协议首包: {peek!r}")  # 非法连接
    client_conn.close()  # 关闭未知协议连接


def main() -> None:
    """服务器主函数：创建监听 Socket 并派生工作线程。"""
    ensure_storage_dir()  # 确保 storage 目录存在
    database.init_db()  # 初始化 SQLite 表结构
    synced = database.sync_storage_files(STORAGE_DIR)  # 将已有 storage 文件补录入库
    if synced:
        print(f"[数据库] 已从 storage 同步 {synced} 个历史文件到 files_meta 表")
    user_count = len(database.get_all_users())
    if user_count == 0:
        print("[警告] 数据库中无用户，请先运行: python3 migrate_users.py")
    else:
        print(f"[数据库] 已加载 {user_count} 个用户（密码为 SHA-256 哈希存储）")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建 TCP Socket
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 允许端口快速重用
    server_sock.bind((HOST, PORT))  # 绑定 0.0.0.0:8082
    server_sock.listen(128)  # 进入监听状态， backlog 128 支持较多并发排队

    print(f"TCP 文件传输服务器已启动 -> {HOST}:{PORT}")  # 启动成功提示
    print(f"Web 控制台访问 -> http://<公网IP>:{PORT}/")  # 提示浏览器访问地址
    print(f"文件存储目录: {STORAGE_DIR}")  # 显示存储路径

    try:
        while True:  # 主循环：接受新连接
            client_conn, client_addr = server_sock.accept()  # 阻塞等待客户端连接
            dispatch_connection(client_conn, client_addr)  # 按协议分流到 HTTP 或 FTCP
    except KeyboardInterrupt:  # Ctrl+C 优雅退出
        print("\n服务器正在关闭...")  # 提示正在关闭
    finally:
        server_sock.close()  # 关闭监听 Socket


if __name__ == "__main__":  # 脚本直接运行时进入 main
    main()  # 启动服务器
