# TCP 文件传输系统

基于 Python 3 的 TCP 文件传输实验项目，包含多线程并发服务器、自定义 FTCP 应用层协议、4096 字节分块缓存读写、**浏览器 Web 控制台**（简约商务风），以及 **CustomTkinter 桌面客户端**（与 Web 统一的靛蓝商务主题）。

服务端已集成 **SQLite 持久化**、**SHA-256 密码哈希**、**`.tmp` 断点容错**、**Socket 超时防死线程** 与 **客户端预哈希防抓包** 等加固特性。

---

## 运行环境要求

| 组件 | Python | 依赖 | 运行位置 |
|------|--------|------|----------|
| **服务端** | 3.6+（推荐 3.8+） | 标准库即可（`sqlite3`、`hashlib` 等） | 本机 / 云服务器 |
| **Web 控制台** | — | 现代浏览器（支持 Web Crypto API） | 任意设备浏览器 |
| **桌面客户端** | **3.8 及以上** | `customtkinter` | **须在本地电脑运行**（需图形界面） |

```bash
pip install customtkinter   # 仅运行 client_ui.py 时需要
```

> **桌面客户端无法在纯命令行云服务器上直接启动**：需要 Python 3.8+、图形界面（Windows / macOS / 带桌面的 Linux）及 `customtkinter`。实验复现时，请在本机同时运行服务端与桌面端，通过 `127.0.0.1` 连接，**无需公网服务器**。

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
│   ├── client_ui.py        # 桌面 GUI（简约商务风，本地运行）
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
| 浅色 / 深色主题切换 | ✅（太阳/月亮） | ✅（简约浅色/深色/跟随系统） |

---

## 本机实验复现（推荐）

实验报告要求验证 **身份认证、文件上传/下载、分块传输、异常处理** 等功能时，在本机即可完成，无需部署公网服务器。

### 1. 启动服务端

```bash
cd server
python migrate_users.py   # 首次运行：将 users.json 明文密码哈希写入 ftcp.db
python server.py          # Windows 下也可用 python3
```

启动成功示例：

```
[数据库] 已加载 2 个用户（密码为 SHA-256 哈希存储）
TCP 文件传输服务器已启动 -> 0.0.0.0:8082
Web 控制台访问 -> http://<公网IP>:8082/
文件存储目录: .../server/storage
```

### 2. 启动桌面客户端

另开一个终端：

```bash
cd client
pip install customtkinter
python client_ui.py
```

### 3. 操作步骤

1. 服务器 IP 填 **`127.0.0.1`**，端口 **`8082`**（默认已填好）→ 点击 **连接**
2. 输入账号密码 → 点击 **登录**（界面输入明文，程序自动哈希后发送）
3. 点击 **↻ 刷新列表** 查看远端文件
4. **浏览本地文件** 选择待上传文件 → **↑ 上传**
5. 在远端列表中点击选中文件 → **↓ 下载** 或 **删除**

下载的文件保存在 `client/downloads/` 目录。

### 4. 实验测试建议（对应实验报告）

| 测试项 | 操作 | 预期结果 |
|--------|------|----------|
| 正确登录 | `admin` / `admin123` | 状态显示「已登录」，弹窗提示成功 |
| 密码错误 | 正确用户名 + 错误密码 | 弹窗「密码错误」 |
| 用户名错误 | 不存在的用户名 | 弹窗「用户名错误」 |
| 小文件上传 | 上传约 10KB 文本文件 | 进度条走完，列表中出现新文件 |
| 大文件分块 | 上传较大文件（如 PDF） | 进度条实时更新，上传完成后收到 ACK |
| 文件下载 | 选中远端文件 → 下载 | `client/downloads/` 中出现完整文件 |

### 5. 可选：Web 控制台

浏览器访问 **`http://127.0.0.1:8082/`**，可在同一服务端上通过 HTTP 完成相同操作，底部日志区含 `[理论]` 实验要点说明。

---

## 预置测试账号

| 用户名 | 密码 |
|--------|------|
| admin | admin123 |
| student | tcp2026 |

登录时界面仍输入**明文密码**；客户端 / 浏览器会在本地完成 SHA-256 加盐哈希后再发送，服务端数据库中存储的是哈希值。

登录失败时返回 **「用户名错误」** 或 **「密码错误」**（Web Toast / 桌面弹窗）。

> 若 `migrate_users.py` 提示迁移了错误用户，请先从 `users.json.bak` 恢复 `users.json`，再重新执行迁移。

---

## 操作指南

### 桌面客户端

界面采用与 Web 控制台一致的**简约商务风**（靛蓝主色、卡片分区、状态徽章）：

- **顶部导航**：品牌栏 + 连接状态（● 已连接 / 未连接）+ 主题切换
- **连接设置**：服务器 IP / 端口 / 连接 / 断开
- **身份验证**：用户名 / 密码 / 登录，右侧显示登录状态徽章
- **文件管理**：可点击的远端文件列表 + 本地文件选择区 + 操作按钮
- **传输进度**：细进度条 + 百分比与描述
- **运行日志**：等宽字体操作记录

**主题预设**（右上角下拉）：

| 预设 | 说明 |
|------|------|
| 简约浅色（默认） | 浅灰背景 + 靛蓝强调，与 Web 控制台一致 |
| 简约深色 | 深蓝灰背景 + 浅靛蓝强调 |
| 跟随系统 | 跟随操作系统浅/深色模式 |

### Web 控制台

1. 浏览器打开 `http://127.0.0.1:8082/`（本机）或 `http://<公网IP>:8082/`（部署后）
2. 左侧 **登录** → 输入账号密码
3. 左侧 **上传**：点击虚线区域选择文件 →「上传到服务器」
4. 右侧 **文件列表**：「↻ 刷新列表」→ 点击「下载」或「删除」（删除需确认）
5. 底部 **运行日志**：含 `[理论]` / `[操作]` 标签；**拖动日志区上边缘**可调整高度

**主题切换**（右上角）：点击 **太阳 / 月亮** 滑动开关，在浅色与深色模式间切换。

---

## 公网部署（可选）

如需从外网访问，服务端监听 **`0.0.0.0:8082`**，同一端口自动识别 HTTP 与 FTCP：

| 访问方式 | 地址示例 | 协议 |
|----------|----------|------|
| **浏览器 Web** | `http://<公网IP>:8082/` | HTTP |
| **桌面客户端** | IP `<公网IP>`，端口 `8082` | FTCP |

### 首次部署

```bash
cd server
python3 migrate_users.py
python3 server.py
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

### 更新代码后重启

修改 `server.py` / `http_handler.py` / `database.py` / `web/index.html` 后需重启服务；静态页面可强制刷新浏览器（`Ctrl+Shift+R`）：

```bash
pkill -f "python3.*server.py"
cd server && python3 server.py
```

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

**协议分流**：连接首 4 字节为 `GET `/`POST` 等 → HTTP；为 `FTCP` → FTCP 客户端。分流逻辑在独立线程中执行，避免阻塞新连接接入。

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

- **多线程并发**：每个客户端连接独立 `threading.Thread`；协议分流亦在独立线程中处理
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
| 桌面端连接成功但登录失败 / 断连 | 服务端未启动、端口被占用、或连错 IP | 确认 `server.py` 已运行；IP 用 `127.0.0.1`；检查 8082 端口冲突 |
| 登录失败 | 账号错误 / 未迁移用户 | 运行 `python migrate_users.py`（必要时从 `users.json.bak` 恢复） |
| 登录失败（升级后） | 客户端仍为旧版明文发送 | 更新客户端代码并重启 `client_ui.py` |
| 浏览器无法打开 | 服务未启动 | 启动 `server.py` |
| 删除失败「接口不存在」 | 服务端未重启 | 重启 `server.py` |
| 下载/删除「文件不存在」 | 数据库无记录 | 先上传或刷新列表 |
| 8082 端口被占用 | 旧进程未退出 / 其他程序占用 | Windows：`netstat -ano \| findstr :8082` 查 PID 后结束；或换端口 |
| 服务器上无法运行 client_ui | 无 GUI | 在本机 Python 3.8+ 环境运行桌面端 |
| `ModuleNotFoundError: customtkinter` | 未安装依赖 | `pip install customtkinter` |
| `database is locked` | 旧版全局连接 | 更新至最新 `database.py` 并重启 |
| Web 主题切换无变化 | 浏览器缓存 | 强制刷新 `Ctrl+Shift+R` |
