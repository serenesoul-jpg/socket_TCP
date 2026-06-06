# TCP 文件传输系统

基于 Python 3 的 TCP 文件传输实验项目，包含多线程并发服务器、自定义 FTCP 应用层协议、4096 字节分块缓存读写、**浏览器 Web 控制台**（简约商务风），以及 CustomTkinter 桌面客户端。

服务端已集成 **SQLite 持久化**、**SHA-256 密码哈希**、**`.tmp` 断点容错**、**Socket 超时防死线程** 与 **客户端预哈希防抓包** 等工业级加固特性。

---

## 运行环境要求

| 组件 | Python | 依赖 | 运行位置 |
|------|--------|------|----------|
| **服务端** | 3.6+（推荐 3.8+） | 标准库即可（`sqlite3`、`hashlib` 等） | 云服务器 / 本机 |
| **Web 控制台** | — | 现代浏览器（支持 Web Crypto API） | 任意设备浏览器 |
| **桌面客户端** | **3.8 及以上** | `customtkinter` | **须在本地电脑运行**（见下方说明） |

```bash
pip install customtkinter   # 仅运行 client_ui.py 时需要
```

> **桌面客户端无法在纯命令行云服务器上直接启动**：需要 Python 3.8+、图形界面（`DISPLAY`）及 `customtkinter`。请将 `client/` 目录同步到本机后运行 `python3 client_ui.py`，通过公网 IP 连接服务端。

---

## 项目结构

```
socket_TCP/
├── server/
│   ├── server.py           # 主程序：FTCP + HTTP 分流，Socket 超时，.tmp 上传
│   ├── database.py         # SQLite 用户凭证与文件元数据（ftcp.db）
│   ├── migrate_users.py    # 一次性迁移：users.json 明文 → 哈希入库
│   ├── http_handler.py     # Web REST API（登录/列表/上传/下载/删除）
│   ├── prefixed_socket.py  # Socket 前缀缓冲（协议分流辅助）
│   ├── web/index.html      # Web 控制台（太阳/月亮主题切换）
│   ├── ftcp.db             # SQLite 数据库（首次启动或迁移后生成）
│   ├── users.json.bak      # 迁移前的用户凭证备份
│   └── storage/            # 服务端文件存储（自动创建）
├── client/
│   ├── client_ui.py        # 桌面 GUI（本地运行）
│   ├── tcp_client.py       # FTCP 通信核心（预哈希登录、.tmp 下载）
│   ├── requirements.txt
│   └── downloads/          # 客户端下载目录（自动创建）
├── .gitignore
└── README.md
```

---

## 功能一览

| 功能 | Web 控制台 | 桌面客户端（FTCP） |
|------|:----------:|:------------------:|
| 用户登录（用户名/密码错误细分） | ✅ | ✅ |
| 登录密码预哈希（防抓包） | ✅ | ✅ |
| 文件列表（SQLite 元数据） | ✅ | ✅ |
| 文件上传（进度显示 + .tmp 容错） | ✅ | ✅ |
| 文件下载（客户端 .tmp 容错） | ✅ | ✅ |
| **文件删除** | ✅ | ✅ |
| 上传 ACK 确认（FTCP） | — | ✅ |
| 实验理论日志 | ✅ | — |
| 日志面板拖拽调整高度 | ✅ | — |
| 太阳/月亮主题切换 | ✅ | — |

---

## 公网访问

服务端监听 **`0.0.0.0:8082`**，同一端口自动识别 HTTP 与 FTCP：

| 访问方式 | 地址示例 | 协议 |
|----------|----------|------|
| **浏览器 Web** | `http://8.134.97.118:8082/` | HTTP |
| **桌面客户端** | IP `8.134.97.118`，端口 `8082` | FTCP |

> 将 `8.134.97.118` 替换为你的公网 IP。

### 首次部署

```bash
cd server
python3 migrate_users.py   # 首次部署：将 users.json 明文密码哈希写入 ftcp.db
python3 server.py
```

启动成功示例：

```
[数据库] 已加载 2 个用户（密码为 SHA-256 哈希存储）
TCP 文件传输服务器已启动 -> 0.0.0.0:8082
Web 控制台访问 -> http://<公网IP>:8082/
文件存储目录: .../server/storage
```

**放行端口**：云安全组 + 系统防火墙均需开放 **TCP 8082**。

```bash
# firewalld
sudo firewall-cmd --add-port=8082/tcp --permanent && sudo firewall-cmd --reload

# ufw
sudo ufw allow 8082/tcp
```

**验证**：

```bash
curl -I http://你的公网IP:8082/
curl http://你的公网IP:8082/api/version
```

`/api/version` 正常应返回：

```json
{"ok": true, "version": "1.1.0", "features": ["login", "upload", "download", "delete", "list"]}
```

### 更新代码后重启（重要）

修改 `server.py` / `http_handler.py` / `database.py` / `web/index.html` 后需重启服务；静态页面可强制刷新浏览器（`Ctrl+Shift+R`）：

```bash
pkill -f "python3.*server.py"
cd server && python3 server.py
```

---

## 预置测试账号

| 用户名 | 密码 |
|--------|------|
| admin | admin123 |
| student | tcp2026 |

登录时界面仍输入**明文密码**；客户端 / 浏览器会在本地完成 SHA-256 加盐哈希后再发送，服务端数据库中存储的是哈希值。

登录失败时返回 **「用户名错误」** 或 **「密码错误」**（Web Toast / 桌面弹窗）。

---

## 操作指南

### Web 控制台

1. 浏览器打开 `http://<公网IP>:8082/`
2. 左侧 **登录** → 输入账号密码
3. 左侧 **上传**：点击虚线区域选择文件 →「上传到服务器」
4. 右侧 **文件列表**：「↻ 刷新列表」→ 点击「下载」或「删除」（删除需确认）
5. 底部 **运行日志**：含 `[理论]` / `[操作]` 标签；**拖动日志区上边缘**可调整高度

**主题切换**（右上角）：点击 **太阳 / 月亮** 滑动开关，在浅色与深色模式间切换。

### 桌面客户端（本地运行）

在**本机**（Windows / macOS / 带桌面的 Linux）执行：

```bash
cd client
pip install customtkinter   # Python 3.8+
python3 client_ui.py
```

1. 填写**服务器公网 IP** 和端口 `8082` → **连接**
2. **登录验证**（输入明文密码，程序自动哈希后发送）
3. **刷新远端列表** → 选中文件 → **上传 / 下载 / 删除**
4. 界面风格可在连接栏右侧切换（默认：清新浅色-绿）

---

## Web HTTP API

| 方法 | 路径 | 说明 | 需登录 |
|------|------|------|:------:|
| GET | `/` | Web 主页 | — |
| GET | `/api/version` | 服务版本与功能列表 | — |
| POST | `/api/login` | 登录，JSON `{username, password}`（`password` 为客户端预哈希） | — |
| POST | `/api/logout` | 退出 | — |
| GET | `/api/files` | 文件列表（来自 SQLite） | ✅ |
| GET | `/api/download?name=xxx` | 下载文件 | ✅ |
| POST | `/api/upload` | 上传（multipart/form-data，.tmp 容错） | ✅ |
| POST | `/api/delete` | 删除，JSON `{name: "文件名"}` | ✅ |
| DELETE | `/api/delete?name=xxx` | 删除（兼容写法） | ✅ |

---

## FTCP 自定义协议（防粘包）

每帧：**固定 10 字节报文头** + **变长 Payload**

| 字段 | 长度 | 说明 |
|------|------|------|
| Magic | 4 字节 | 固定 `FTCP` |
| Version | 1 字节 | `0x01` |
| Command | 1 字节 | 命令字（见下表） |
| PayloadLen | 4 字节 | Payload 字节数（大端 uint32） |

**命令字**：

| 命令 | 值 | 说明 |
|------|-----|------|
| CMD_LOGIN | 0x01 | 登录请求（password 字段为 SHA-256 哈希） |
| CMD_LOGIN_RESP | 0x02 | 登录响应 |
| CMD_LIST | 0x03 | 文件列表 |
| CMD_LIST_RESP | 0x04 | 列表响应 |
| CMD_UPLOAD | 0x05 | 上传 |
| CMD_DOWNLOAD | 0x06 | 下载 |
| CMD_ERROR | 0x07 | 错误 |
| CMD_UPLOAD_ACK | 0x08 | 上传完成确认 |
| CMD_DELETE | 0x09 | 删除文件 |
| CMD_DELETE_RESP | 0x0A | 删除响应 |

**防粘包**：`recv_exact(n)` 循环读满 n 字节；文件元数据为 `filename_len(4) + file_size(8) + filename`；文件体按 **4096 字节** 分块传输。

**协议分流**：连接首 4 字节为 `GET `/`POST` 等 → HTTP；为 `FTCP` → FTCP 客户端。

---

## 安全与健壮性设计

### 1. SQLite 多线程安全（`database.py`）

- 每次 CRUD **独立创建** `sqlite3` 连接，不在全局共享连接对象
- `timeout=20.0`：遇锁等待而非立即抛出 `database is locked`
- `PRAGMA journal_mode=WAL`：提升多读并发稳定性
- `threading.Lock` 串行化写操作临界区

### 2. 密码哈希与防抓包

- 数据库存储 **SHA-256(盐 + 用户名 + 明文密码)**，不存明文
- Web / FTCP 客户端在**本地**完成哈希，网络上传输 64 位十六进制摘要
- 服务端 `authenticate()` 直接比对哈希，零知识验证思路（无 TLS 下的折中方案）

### 3. `.tmp` 断点容错（上传 / 下载对称）

| 端 | 行为 |
|----|------|
| **服务端上传** | 先写 `storage/文件名.tmp` → 收齐后 `rename` → 写 SQLite |
| **服务端 HTTP 上传** | 同上 |
| **客户端下载** | 先写 `downloads/文件名.tmp` → 收齐后 `rename` |
| **断线异常** | `except` 块立即 `os.remove(.tmp)`，防止残缺文件占盘 |

### 4. 死连接清理（`server.py`）

- 每个 FTCP 连接设置 `conn.settimeout(120.0)`（2 分钟无活动超时）
- 捕获 `socket.timeout` 后优雅关闭 Socket，释放工作线程，防止资源枯竭

---

## 技术要点

- **多线程并发**：每个客户端连接独立 `threading.Thread`
- **身份验证**：文件操作前强制登录，SQLite `users` 表校验
- **文件元数据**：`files_meta` 表记录 filename、uploader、upload_time、file_size
- **分块缓存**：4096 字节 Buffer，支持任意二进制文件
- **上传 ACK**：FTCP 上传后服务端发 `CMD_UPLOAD_ACK`，客户端确认成功
- **GUI 不阻塞**：桌面客户端 Socket 在子线程，进度回调更新 UI
- **Web 理论日志**：操作时自动输出 TCP/Socket/粘包/安全设计等实验要点

---

## 常见问题

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 浏览器无法打开 | 服务未启动 / 端口未放行 | 启动 `server.py`，检查安全组 8082 |
| 删除失败「接口不存在」 | 服务端未重启 | `pkill -f server.py` 后重新启动 |
| 登录失败 | 账号错误 / 未迁移用户 | 运行 `python3 migrate_users.py` |
| 登录失败（升级后） | 客户端仍为旧版明文发送 | 更新客户端代码并重启 `client_ui.py` |
| 下载/删除「文件不存在」 | 数据库无记录 | 先上传或刷新列表 |
| 桌面客户端连不上 | IP/端口错误 | 确认 `8082` 与公网 IP |
| 服务器上无法运行 client_ui | 无 GUI / Python 3.6 | 在本机 Python 3.8+ 环境运行 |
| `ModuleNotFoundError: customtkinter` | 未安装依赖 | `pip install customtkinter` |
| `database is locked` | 旧版全局连接 | 更新至最新 `database.py` 并重启 |
| Web 主题切换无变化 | 浏览器缓存 | 强制刷新 `Ctrl+Shift+R` |

---

## 桌面客户端界面风格

| 预设 | 说明 |
|------|------|
| 清新浅色-绿（默认） | 浅色 + 绿色强调 |
| 清新浅色-蓝 | 浅色 + 蓝色强调 |
| 暖色深色-蓝 | 深色 + 蓝色强调 |
| 深色-绿 | 深色 + 绿色强调 |
| 跟随系统-蓝 | 跟随 OS 主题 |
