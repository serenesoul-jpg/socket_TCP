# TCP 文件传输系统

基于 Python 3 的 TCP 文件传输实验项目，包含多线程并发服务器、自定义 FTCP 应用层协议、4096 字节分块缓存读写、**浏览器 Web 控制台**（简约商务风），以及 CustomTkinter 桌面客户端。

---

## 运行环境要求

- **Python**：3.8 及以上
- **依赖库**：
  - `customtkinter`（仅桌面客户端需要，Web 访问无需安装）
  - Python 标准库：`socket`、`threading`、`struct`、`json`、`os`、`http.server`

```bash
pip install customtkinter   # 仅运行 client_ui.py 时需要
```

---

## 项目结构

```
socket_TCP/
├── server/
│   ├── server.py           # 主程序：FTCP + HTTP 协议分流，0.0.0.0:8082
│   ├── http_handler.py     # Web REST API（登录/列表/上传/下载/删除）
│   ├── prefixed_socket.py  # Socket 前缀缓冲（协议分流辅助）
│   ├── web/index.html      # Web 控制台（简约商务 UI）
│   ├── users.json          # 用户凭证
│   └── storage/            # 服务端文件存储（自动创建）
├── client/
│   ├── client_ui.py        # 桌面 GUI
│   ├── tcp_client.py       # FTCP 通信核心（子线程网络 I/O）
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
| 文件列表 | ✅ | ✅ |
| 文件上传（进度显示） | ✅ | ✅ |
| 文件下载 | ✅ | ✅ |
| **文件删除** | ✅ | ✅ |
| 上传 ACK 确认（FTCP） | — | ✅ |
| 实验理论日志 | ✅ | — |
| 日志面板拖拽调整高度 | ✅ | — |

---

## 公网访问

服务端监听 **`0.0.0.0:8082`**，同一端口自动识别 HTTP 与 FTCP：

| 访问方式 | 地址示例 | 协议 |
|----------|----------|------|
| **浏览器 Web** | `http://8.134.97.118:8082/` | HTTP |
| **桌面客户端** | IP `8.134.97.118`，端口 `8082` | FTCP |

> 将 `8.134.97.118` 替换为你的公网 IP。

### 部署与启动

```bash
cd server
python3 server.py
```

启动成功示例：

```
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

> 若 `features` 中无 `"delete"`，说明服务端仍是旧进程，需**重启** `python3 server.py`。

### 更新代码后重启（重要）

修改 `server.py` / `http_handler.py` 后必须重启服务，否则 Web 页面已更新但 API 仍是旧版：

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

登录失败时返回 **「用户名错误」** 或 **「密码错误」**（Web Toast / 桌面弹窗）。

---

## 操作指南

### Web 控制台

1. 浏览器打开 `http://<公网IP>:8082/`
2. 左侧 **登录** → 输入账号密码
3. 左侧 **上传**：点击虚线区域选择文件 →「上传到服务器」
4. 右侧 **文件列表**：「↻ 刷新列表」→ 点击「下载」或「删除」（删除需确认）
5. 底部 **运行日志**：含 `[理论]` / `[操作]` 标签；**拖动日志区上边缘**可调整高度（类似终端）

**界面风格**（右上角）：简约商务 · 浅色 / 简约商务 · 深色

### 桌面客户端

```bash
cd client
python3 client_ui.py
```

1. 填写服务器 IP（公网或 `127.0.0.1`）和端口 `8082` → **连接**
2. **登录验证**
3. **刷新远端列表** → 选中文件 → **上传 / 下载 / 删除**
4. 界面风格可在连接栏右侧切换（默认：清新浅色-绿）

---

## Web HTTP API

| 方法 | 路径 | 说明 | 需登录 |
|------|------|------|:------:|
| GET | `/` | Web 主页 | — |
| GET | `/api/version` | 服务版本与功能列表 | — |
| POST | `/api/login` | 登录，JSON `{username, password}` | — |
| POST | `/api/logout` | 退出 | — |
| GET | `/api/files` | 文件列表 | ✅ |
| GET | `/api/download?name=xxx` | 下载文件 | ✅ |
| POST | `/api/upload` | 上传（multipart/form-data） | ✅ |
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
| CMD_LOGIN | 0x01 | 登录请求 |
| CMD_LOGIN_RESP | 0x02 | 登录响应 |
| CMD_LIST | 0x03 | 文件列表 |
| CMD_LIST_RESP | 0x04 | 列表响应 |
| CMD_UPLOAD | 0x05 | 上传 |
| CMD_DOWNLOAD | 0x06 | 下载 |
| CMD_ERROR | 0x07 | 错误 |
| CMD_UPLOAD_ACK | 0x08 | 上传完成确认 |
| CMD_DELETE | 0x09 | 删除文件 |
| CMD_DELETE_RESP | 0x0A | 删除响应 |

**防粘包**：`recv_exact(n)` 循环读满 n 字节；文件元数据为 `filename_len(4) + file_size(8) + filename`；文件体按 **4096 字节** 分块 `read/send` 或 `recv/write`。

**协议分流**：连接首 4 字节为 `GET `/`POST` 等 → HTTP；为 `FTCP` → FTCP 客户端。

---

## 技术要点

- **多线程并发**：每个客户端连接独立 `threading.Thread`
- **身份验证**：文件操作前强制登录，`users.json` 校验
- **分块缓存**：4096 字节 Buffer，支持任意二进制文件
- **上传 ACK**：FTCP 上传后服务端发 `CMD_UPLOAD_ACK`，客户端确认成功
- **GUI 不阻塞**：桌面客户端 Socket 在子线程，进度回调更新 UI
- **Web 理论日志**：操作时自动输出 TCP/Socket/粘包/命令字等实验要点，便于写报告

---

## 常见问题

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 浏览器无法打开 | 服务未启动 / 端口未放行 | 启动 `server.py`，检查安全组 8082 |
| 删除失败「接口不存在」 | 服务端未重启，仍是旧代码 | `pkill -f server.py` 后重新启动 |
| `/api/version` 无 delete | 同上 | 同步最新代码并重启 |
| 登录失败 | 账号错误 | 对照 `users.json` |
| 下载/删除「文件不存在」 | storage 中无该文件 | 先上传或刷新列表 |
| 桌面客户端连不上 | IP/端口错误 | 确认 `8082` 与公网 IP |
| 缺少 customtkinter | 未安装依赖 | `pip install customtkinter` |

---

## 桌面客户端界面风格

| 预设 | 说明 |
|------|------|
| 清新浅色-绿（默认） | 浅色 + 绿色强调 |
| 清新浅色-蓝 | 浅色 + 蓝色强调 |
| 暖色深色-蓝 | 深色 + 蓝色强调 |
| 深色-绿 | 深色 + 绿色强调 |
| 跟随系统-蓝 | 跟随 OS 主题 |
