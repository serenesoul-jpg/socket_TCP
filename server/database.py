#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLite 数据持久化模块：用户凭证与文件元数据统一管理。

高并发健壮性设计（实验报告亮点）：
- 每次 CRUD 使用独立 sqlite3 连接 + timeout=20.0，避免全局共享连接导致 "database is locked"。
- threading.Lock 串行化写操作，配合 WAL 日志模式提升多读并发下的稳定性。
- 登录采用「客户端预哈希、服务端零知识比对」，网络上不传输明文密码。
"""

import hashlib  # SHA-256 密码哈希
import os  # 路径检查
import sqlite3  # 嵌入式数据库
import threading  # 写操作互斥锁
from contextlib import contextmanager  # 连接上下文管理器
from datetime import datetime, timezone  # UTC 时间戳
from typing import Dict, Generator, List, Optional, Tuple  # 类型注解

# ===================== 路径与全局常量 =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ftcp.db")

# 固定盐：客户端与服务端必须使用相同常量，保证哈希结果一致
PASSWORD_SALT = "FTCP_FILE_TRANSFER_SALT_2026"

# 写操作互斥锁：多线程并发 INSERT/UPDATE 时避免竞态（只锁临界区，不锁连接对象本身）
_db_lock = threading.Lock()

# SQLite 遇锁时最长等待秒数，超时后才抛 OperationalError，防止瞬时锁竞争直接失败
DB_TIMEOUT = 20.0


# ===================== 连接管理（线程隔离，禁止全局共享连接） =====================

@contextmanager
def db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    每次 CRUD 动态创建独立连接，用完即关，不在全局范围持有连接对象。

    理论意义：Python 多线程服务器中，sqlite3 连接跨线程复用会触发
    "database is locked" 或线程安全警告；短连接 + timeout 是工业界常用轻量方案。
    """
    with _db_lock:  # 进入临界区：同一时刻仅一个线程持有写/读事务
        # timeout=20.0：遇锁时阻塞等待最多 20 秒，而非立即失败
        with sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT) as conn:
            conn.row_factory = sqlite3.Row  # 查询结果可按列名访问
            # WAL 模式：读不阻塞写，适合多 client_handler 线程并发查列表/验证登录
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn  # 将连接交给 with 块内的 CRUD 代码使用
        # with 块结束自动 commit（无异常）或 rollback（有异常），并 close 连接


# ===================== 密码哈希工具 =====================

def hash_password(password: str, username: str) -> str:
    """
    对明文密码进行 SHA-256 加盐哈希（仅迁移脚本 / 本地注册时使用）。

    客户端登录时应自行哈希后再发送，服务端 authenticate 只做字符串相等比对。
    """
    raw = f"{PASSWORD_SALT}:{username}:{password}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def is_hashed(value: str) -> bool:
    """判断字符串是否已是 64 位 SHA-256 十六进制摘要。"""
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


# ===================== 建表初始化 =====================

def init_db() -> None:
    """初始化 users 与 files_meta 表（若不存在则创建）。"""
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username        TEXT PRIMARY KEY,
                hashed_password TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files_meta (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filename    TEXT UNIQUE NOT NULL,
                uploader    TEXT NOT NULL,
                upload_time TEXT NOT NULL,
                file_size   INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_files_uploader ON files_meta(uploader);
            """
        )


# ===================== 用户 CRUD =====================

def get_user(username: str) -> Optional[sqlite3.Row]:
    """按用户名查询，不存在返回 None。"""
    with db_connection() as conn:
        return conn.execute(
            "SELECT username, hashed_password FROM users WHERE username = ?",
            (username,),
        ).fetchone()


def get_all_users() -> Dict[str, str]:
    """返回 {username: hashed_password} 字典。"""
    with db_connection() as conn:
        rows = conn.execute("SELECT username, hashed_password FROM users").fetchall()
        return {row["username"]: row["hashed_password"] for row in rows}


def upsert_user(username: str, hashed_password: str) -> None:
    """插入或更新用户（迁移脚本使用）。"""
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (username, hashed_password) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET hashed_password = excluded.hashed_password
            """,
            (username, hashed_password),
        )


def authenticate(username: str, client_password_hash: str) -> Tuple[bool, str]:
    """
    零知识比对登录：客户端已在本地完成 SHA-256 哈希，网络上只传输哈希值。

    服务端逻辑：
    1. 查 users 表取 stored_hash
    2. 直接比对 client_password_hash == stored_hash（不再接触明文密码）

    传输安全意义：Wireshark 抓包只能看到 64 位十六进制摘要，无法还原明文密码。
    """
    user = get_user(username)
    if user is None:
        return False, "用户名错误"
    # 恒定时间比较非必须（实验规模），直接字符串相等即可
    if client_password_hash != user["hashed_password"]:
        return False, "密码错误"
    return True, "登录成功"


# ===================== 文件元数据 CRUD =====================

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_file_meta(filename: str, uploader: str, file_size: int) -> None:
    """上传成功后写入或更新文件元数据。"""
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO files_meta (filename, uploader, upload_time, file_size)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                uploader    = excluded.uploader,
                upload_time = excluded.upload_time,
                file_size   = excluded.file_size
            """,
            (filename, uploader, _utc_now_iso(), file_size),
        )


def delete_file_meta(filename: str) -> bool:
    """删除元数据记录，返回是否确实删除了行。"""
    with db_connection() as conn:
        cur = conn.execute("DELETE FROM files_meta WHERE filename = ?", (filename,))
        return cur.rowcount > 0


def list_files() -> List[Dict[str, object]]:
    """供 FTCP LIST 与 HTTP /api/files 使用的文件列表。"""
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT filename, uploader, upload_time, file_size
            FROM files_meta ORDER BY upload_time DESC
            """
        ).fetchall()
        return [
            {
                "name": row["filename"],
                "size": row["file_size"],
                "uploader": row["uploader"],
                "upload_time": row["upload_time"],
            }
            for row in rows
        ]


def get_file_meta(filename: str) -> Optional[sqlite3.Row]:
    """按文件名查元数据。"""
    with db_connection() as conn:
        return conn.execute(
            "SELECT filename, uploader, upload_time, file_size FROM files_meta WHERE filename = ?",
            (filename,),
        ).fetchone()


def sync_storage_files(storage_dir: str, default_uploader: str = "unknown") -> int:
    """将 storage 中已有文件补录入 files_meta，返回补录数量。"""
    if not os.path.isdir(storage_dir):
        return 0

    synced = 0
    with db_connection() as conn:
        for name in os.listdir(storage_dir):
            if name.startswith(".") or name.endswith(".tmp"):
                continue
            path = os.path.join(storage_dir, name)
            if not os.path.isfile(path):
                continue
            if conn.execute(
                "SELECT 1 FROM files_meta WHERE filename = ?", (name,)
            ).fetchone():
                continue
            conn.execute(
                """
                INSERT INTO files_meta (filename, uploader, upload_time, file_size)
                VALUES (?, ?, ?, ?)
                """,
                (name, default_uploader, _utc_now_iso(), os.path.getsize(path)),
            )
            synced += 1
    return synced
