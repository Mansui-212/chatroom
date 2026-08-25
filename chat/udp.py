"""UDP 数据报的监听、发送和 JSON 编解码。"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable

from chat.config import ENCODING, MAX_UDP_MESSAGE_SIZE, UDP_HOST, UDP_PORT

UdpAddress = tuple[str, int]
MessageHandler = Callable[[dict, UdpAddress], Awaitable[None] | None]
ErrorHandler = Callable[[Exception], None]


class UDPError(Exception):
    """UDP 消息或传输层错误。"""


def _clean_utf8(value):
    """删除无法写入 UTF-8 JSON 的 surrogate 字符。"""

    if isinstance(value, str):
        return value.encode(ENCODING, errors="ignore").decode(ENCODING)
    if isinstance(value, list):
        return [_clean_utf8(item) for item in value]
    if isinstance(value, dict):
        return {_clean_utf8(key): _clean_utf8(item) for key, item in value.items()}
    return value


class _DatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_message: MessageHandler, on_error: ErrorHandler | None):
        self.on_message = on_message
        self.on_error = on_error
        self.loop: asyncio.AbstractEventLoop | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.loop = asyncio.get_running_loop()

    def datagram_received(self, data: bytes, address) -> None:
        try:
            message = json.loads(data.decode(ENCODING))
            if not isinstance(message, dict):
                raise UDPError("UDP 消息必须是 JSON 对象")
            host, port = address[0], address[1]
            result = self.on_message(message, (host, port))
            if inspect.isawaitable(result) and self.loop is not None:
                self.loop.create_task(result)
        except (UnicodeDecodeError, json.JSONDecodeError, UDPError) as error:
            if self.on_error is not None:
                self.on_error(error)

    def error_received(self, exception: Exception) -> None:
        if self.on_error is not None:
            self.on_error(exception)


class UDPTransport:
    """在单个 UDP socket 上收发 JSON 消息。"""

    def __init__(
        self,
        on_message: MessageHandler,
        host: str = UDP_HOST,
        port: int = UDP_PORT,
        on_error: ErrorHandler | None = None,
    ):
        self.on_message = on_message
        self.host = host
        self.port = port
        self.on_error = on_error
        self.transport: asyncio.DatagramTransport | None = None

    @property
    def address(self) -> UdpAddress:
        if self.transport is None:
            raise UDPError("UDP 尚未启动")
        address = self.transport.get_extra_info("sockname")
        return address[0], address[1]

    async def start(self) -> UdpAddress:
        if self.transport is not None:
            return self.address

        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _DatagramProtocol(self.on_message, self.on_error),
            local_addr=(self.host, self.port),
        )
        self.transport = transport
        return self.address

    def send(self, message: dict, address: UdpAddress) -> None:
        if self.transport is None:
            raise UDPError("UDP 尚未启动")

        try:
            data = json.dumps(
                _clean_utf8(message),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode(ENCODING)
        except (TypeError, ValueError) as error:
            raise UDPError(f"UDP 消息编码失败：{error}") from error

        if len(data) > MAX_UDP_MESSAGE_SIZE:
            raise UDPError("UDP 消息过大")
        self.transport.sendto(data, address)

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()
            self.transport = None
