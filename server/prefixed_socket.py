#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""带前缀缓冲的 Socket 包装器，供协议分流后复用已读字节。"""

import socket  # 导入 socket 模块
from typing import Optional  # 类型注解


class PrefixedSocket:
    """在 recv 时优先返回预读缓冲，保证 FTCP 协议解析不丢失首包字节。"""

    def __init__(self, sock: socket.socket, prefix: bytes = b"") -> None:
        self._sock = sock  # 底层真实 Socket 对象
        self._buffer = prefix  # 分流时已读取的前缀字节

    def recv(self, bufsize: int, flags: int = 0) -> bytes:
        """模拟 socket.recv，先从缓冲取数据，不足再读底层 Socket。"""
        if self._buffer:  # 缓冲中仍有数据
            if len(self._buffer) <= bufsize:  # 缓冲不超过本次请求长度
                data = self._buffer  # 取出全部缓冲
                self._buffer = b""  # 清空缓冲
                need = bufsize - len(data)  # 计算仍需读取的字节数
                if need > 0:  # 若还需要更多数据
                    chunk = self._sock.recv(need, flags)  # 从底层 Socket 继续读
                    return data + chunk  # 拼接后返回
                return data  # 缓冲已足够则直接返回
            chunk = self._buffer[:bufsize]  # 从缓冲截取所需长度
            self._buffer = self._buffer[bufsize:]  # 保留剩余缓冲
            return chunk  # 返回截取片段
        return self._sock.recv(bufsize, flags)  # 缓冲为空则直接读 Socket

    def sendall(self, data: bytes) -> None:
        """转发 sendall 到底层 Socket。"""
        self._sock.sendall(data)  # 保证整段数据发送完毕

    def close(self) -> None:
        """关闭底层 Socket 连接。"""
        self._sock.close()  # 释放连接资源

    def settimeout(self, value: Optional[float]) -> None:
        """设置底层 Socket 超时时间。"""
        self._sock.settimeout(value)  # 转发超时配置

    def __getattr__(self, name: str):
        """未显式实现的方法/属性转发到底层 Socket。"""
        return getattr(self._sock, name)  # 兼容 send、getpeername 等调用
