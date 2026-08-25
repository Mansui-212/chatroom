"""UDP 点对点私聊、ACK 确认和超时重发。"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from chat.config import UDP_ACK_TIMEOUT, UDP_MAX_RETRIES
from chat.udp import UDPError, UDPTransport, UdpAddress

PrivateMessageHandler = Callable[[dict, UdpAddress], Awaitable[None] | None]
DeliveryFailureHandler = Callable[[dict], Awaitable[None] | None]


@dataclass
class PendingDelivery:
    message: dict
    address: UdpAddress
    target: str
    retries: int = 0
    task: asyncio.Task | None = None


class PeerNode:
    """管理客户端 UDP 节点及其可靠私聊投递状态。"""

    def __init__(
        self,
        on_private_message: PrivateMessageHandler,
        on_delivery_failed: DeliveryFailureHandler | None = None,
        host: str | None = None,
        port: int | None = None,
        ack_timeout: float = UDP_ACK_TIMEOUT,
        max_retries: int = UDP_MAX_RETRIES,
    ):
        if ack_timeout <= 0:
            raise ValueError("ack_timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")

        transport_kwargs = {}
        if host is not None:
            transport_kwargs["host"] = host
        if port is not None:
            transport_kwargs["port"] = port
        self.udp = UDPTransport(self._handle_datagram, **transport_kwargs)
        self.on_private_message = on_private_message
        self.on_delivery_failed = on_delivery_failed
        self.ack_timeout = ack_timeout
        self.max_retries = max_retries

        self.pending: dict[int, PendingDelivery] = {}
        self.local_history: list[dict] = []
        self._next_message_id = int(time.time() * 1000)
        self._received: set[tuple[UdpAddress, int]] = set()
        self._received_order: deque[tuple[UdpAddress, int]] = deque(maxlen=1000)

    @property
    def address(self) -> UdpAddress:
        return self.udp.address

    async def start(self) -> UdpAddress:
        return await self.udp.start()

    async def send_private(
        self,
        sender: str,
        target: str,
        content: str,
        address: UdpAddress,
    ) -> int:
        """直接向目标 UDP 地址发送私聊，并开始等待 ACK。"""

        if not sender:
            raise ValueError("发送者不能为空")
        if not content:
            raise ValueError("私聊内容不能为空")

        message_id = self._next_message_id
        self._next_message_id += 1
        message = {
            "type": "private",
            "id": message_id,
            "from": sender,
            "content": content,
            "time": int(time.time()),
        }
        delivery = PendingDelivery(message=message, address=address, target=target)
        self.pending[message_id] = delivery
        self.local_history.append(
            {
                **message,
                "to": target,
                "direction": "outgoing",
            }
        )

        try:
            self.udp.send(message, address)
        except (OSError, UDPError):
            self.pending.pop(message_id, None)
            await self._notify_delivery_failed({**message, "to": target})
            return message_id

        delivery.task = asyncio.create_task(self._retry_until_ack(message_id))
        return message_id

    async def _retry_until_ack(self, message_id: int) -> None:
        try:
            while message_id in self.pending:
                await asyncio.sleep(self.ack_timeout)
                delivery = self.pending.get(message_id)
                if delivery is None:
                    return
                if delivery.retries >= self.max_retries:
                    self.pending.pop(message_id, None)
                    await self._notify_delivery_failed(
                        {**delivery.message, "to": delivery.target}
                    )
                    return

                delivery.retries += 1
                try:
                    self.udp.send(delivery.message, delivery.address)
                except (OSError, UDPError):
                    self.pending.pop(message_id, None)
                    await self._notify_delivery_failed(
                        {**delivery.message, "to": delivery.target}
                    )
                    return
        except asyncio.CancelledError:
            raise

    async def _handle_datagram(self, message: dict, address: UdpAddress) -> None:
        message_type = message.get("type")
        if message_type == "ack":
            self._handle_ack(message, address)
            return
        if message_type != "private":
            return

        message_id = message.get("id")
        sender = message.get("from")
        content = message.get("content")
        if not isinstance(message_id, int):
            return
        if not isinstance(sender, str) or not isinstance(content, str):
            return

        # 无论是否为重传包都确认，发送方才能停止重试。
        self.udp.send({"type": "ack", "id": message_id}, address)
        received_key = (address, message_id)
        if received_key in self._received:
            return
        if len(self._received_order) == self._received_order.maxlen:
            oldest = self._received_order.popleft()
            self._received.discard(oldest)
        self._received.add(received_key)
        self._received_order.append(received_key)

        history_message = {**message, "direction": "incoming", "address": address}
        self.local_history.append(history_message)
        result = self.on_private_message(message, address)
        if asyncio.iscoroutine(result):
            await result

    def _handle_ack(self, message: dict, address: UdpAddress) -> None:
        message_id = message.get("id")
        if not isinstance(message_id, int):
            return
        delivery = self.pending.get(message_id)
        if delivery is None or delivery.address != address:
            return
        self.pending.pop(message_id, None)
        if delivery.task is not None:
            delivery.task.cancel()

    async def _notify_delivery_failed(self, message: dict) -> None:
        if self.on_delivery_failed is None:
            return
        result = self.on_delivery_failed(message)
        if asyncio.iscoroutine(result):
            await result

    async def close(self) -> None:
        for delivery in self.pending.values():
            if delivery.task is not None:
                delivery.task.cancel()
        self.pending.clear()
        self.udp.close()
