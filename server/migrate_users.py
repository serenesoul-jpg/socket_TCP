#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
users.json 明文密码 → SQLite 哈希密码 一次性迁移脚本。

用法（在 server 目录下执行）:
    python3 migrate_users.py

行为说明：
1. 读取 users.json 中的用户名与密码（可能是明文或已哈希）
2. 对明文密码调用 hash_password() 转为 SHA-256 摘要
3. 写入 ftcp.db 的 users 表
4. 可选：将 users.json 备份为 users.json.bak，并写入占位提示（不存明文）

实验报告可引用：本脚本实现了「密码哈希加密增强」的数据迁移环节。
"""

import json  # 读取旧版 users.json
import os  # 路径与文件备份
import shutil  # 复制备份文件
import sys  # 退出码

from database import (  # 复用 database 模块的哈希与建表逻辑
    DB_PATH,
    hash_password,
    init_db,
    is_hashed,
    upsert_user,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
USERS_BACKUP = os.path.join(BASE_DIR, "users.json.bak")


def migrate() -> None:
    """执行迁移主流程。"""
    if not os.path.isfile(USERS_FILE):
        print(f"[错误] 未找到 {USERS_FILE}，无法迁移。")
        sys.exit(1)

    # 先确保数据库表结构存在
    init_db()

    with open(USERS_FILE, "r", encoding="utf-8") as fp:
        users: dict = json.load(fp)

    if not users:
        print("[警告] users.json 为空，无用户可迁移。")
        return

    migrated = 0
    skipped = 0

    for username, password_or_hash in users.items():
        if is_hashed(password_or_hash):
            # 已是 64 位十六进制摘要，直接入库（可能来自上次迁移）
            stored = password_or_hash
            skipped += 1
            print(f"  [跳过哈希] {username} — 字段已是 SHA-256 格式")
        else:
            # 明文密码 → SHA-256 加盐哈希
            stored = hash_password(password_or_hash, username)
            migrated += 1
            print(f"  [已哈希]   {username} — 明文已转换为 SHA-256")

        upsert_user(username, stored)

    # 备份原始 users.json，避免误用明文文件
    if not os.path.isfile(USERS_BACKUP):
        shutil.copy2(USERS_FILE, USERS_BACKUP)
        print(f"\n[备份] 原 users.json 已复制到 {USERS_BACKUP}")

    # 写入说明性占位 JSON（不再包含可用明文密码）
    placeholder = {
        "_notice": "用户凭证已迁移至 ftcp.db（SQLite），请使用 migrate_users.py 管理。",
        "_users_in_db": list(users.keys()),
    }
    with open(USERS_FILE, "w", encoding="utf-8") as fp:
        json.dump(placeholder, fp, ensure_ascii=False, indent=2)

    print(f"\n[完成] 共处理 {len(users)} 个用户：新哈希 {migrated} 个，已是哈希 {skipped} 个。")
    print(f"[完成] 数据库路径: {DB_PATH}")
    print("[提示] 请重启 server.py 使新凭证生效。")


if __name__ == "__main__":
    print("=== FTCP 用户密码迁移工具（明文 → SHA-256 哈希）===\n")
    migrate()
