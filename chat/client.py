"""同时使用 TCP 群聊和 UDP 点对点私聊的命令行客户端。"""

from __future__ import annotations

import asyncio

from chat.commands import CommandError, parse_client_command
from chat.config import HOST, PORT, UDP_HOST, UDP_PORT
from chat.message import create_message
from chat.peer import PeerNode
from chat.protocol import encode_message, read_message


class ChatClient:
    """TCP 负责聊天室业务；UDP ``PeerNode`` 负责局域网私聊。"""

    def __init__(
        self,
        host: str = HOST,
        port: int = PORT,
        udp_host: str = UDP_HOST,
        udp_port: int = UDP_PORT,
        *,
        udp_ack_timeout: float | None = None,
        udp_max_retries: int | None = None,
    ):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.running = True
        self._lookup_futures: dict[str, asyncio.Future] = {}

        peer_options = {"host": udp_host, "port": udp_port}
        if udp_ack_timeout is not None:
            peer_options["ack_timeout"] = udp_ack_timeout
        if udp_max_retries is not None:
            peer_options["max_retries"] = udp_max_retries
        self.peer = PeerNode(
            self._handle_udp_private_message,
            self._handle_udp_delivery_failed,
            **peer_options,
        )
        # 私聊历史只保存在本客户端，不发送给 TCP 服务端。
        self.local_history = self.peer.local_history

    @property
    def udp_address(self) -> tuple[str, int]:
        return self.peer.address

    async def connect(self) -> None:
        """启动 UDP 监听，连接 TCP 后登记实际绑定的 UDP 端口。"""

        udp_address = await self.peer.start()
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.host,
                self.port,
            )
            await self.send(create_message("udp_register", {"port": udp_address[1]}))
        except Exception:
            await self.peer.close()
            raise
        print(
            f"已连接服务器 {self.host}:{self.port}；"
            f"UDP 监听 {udp_address[0]}:{udp_address[1]}"
        )

    async def start(self) -> None:
        """启动 TCP 收发循环，结束时同时释放 TCP 和 UDP 资源。"""

        receive_task = asyncio.create_task(self.receive_loop())
        input_task = asyncio.create_task(self.input_loop())
        done, pending = await asyncio.wait(
            [receive_task, input_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        # 读取任务可能因服务器断开结束；若输入任务结束则无需额外处理结果。
        for task in done:
            if task.cancelled():
                continue
            task.exception()
        await self.close()

    async def send(self, message: dict) -> None:
        if self.writer is None:
            raise ConnectionError("尚未连接 TCP 服务端")
        self.writer.write(encode_message(message))
        await self.writer.drain()

    async def receive_loop(self) -> None:
        """持续接收 TCP 房间事件和 UDP 地址查询结果。"""

        if self.reader is None:
            raise ConnectionError("尚未连接 TCP 服务端")

        try:
            while self.running:
                message = await read_message(self.reader)
                if message is None:
                    print("服务器已断开")
                    break

                if message.get("type") == "user_found":
                    self._resolve_user_lookup(message.get("data", {}))
                    continue
                self.display(message)
        except (ConnectionError, OSError) as error:
            print("接收异常:", error)
        finally:
            self.running = False

    def display(self, message: dict) -> None:
        """按 TCP 消息类型显示服务端事件。"""

        msg_type = message.get("type")
        data = message.get("data", {})

        if msg_type == "chat":
            print(f"{data.get('sender')}: {data.get('content')}")
        elif msg_type == "system":
            print(f"[系统] {data.get('content')}")
        elif msg_type == "rooms":
            print(data.get("content", "房间列表为空"))
        elif msg_type == "history":
            room = data.get("room")
            print(f"最近聊天（{room}）：")
            for history_message in data.get("messages", []):
                history_data = history_message.get("data", {})
                print(
                    f"{history_data.get('sender')}: "
                    f"{history_data.get('content')}"
                )
        else:
            print(message)

    async def input_loop(self) -> None:
        """读取终端输入并分派 TCP 命令、群聊或 UDP 私聊。"""

        while self.running:
            try:
                text = await asyncio.to_thread(input, "> ")
            except EOFError:
                self.running = False
                break
            text = text.strip()
            if not text:
                continue

            if text.startswith("/"):
                try:
                    message = parse_client_command(text)
                except CommandError as error:
                    print(f"[系统] {error}")
                    continue

                if message["type"] == "pmsg":
                    await self.send_peer_message(message["data"])
                else:
                    await self.send(message)
                if message["type"] == "quit":
                    self.running = False
                    break
            else:
                await self.send(create_message("chat", {"content": text}))

    async def send_peer_message(self, data: dict) -> int | None:
        """通过 TCP 查询地址，再用 UDP 将正文直接发送给目标。"""

        target = data.get("target")
        content = data.get("content")
        if not isinstance(target, str) or not isinstance(content, str):
            print("[系统] 私聊参数错误")
            return None

        result = await self.find_user(target)
        address_data = result.get("udp")
        error = result.get("error")
        if error:
            print(f"[系统] {error}")
            return None
        if (
            not isinstance(address_data, list)
            or len(address_data) != 2
            or not isinstance(address_data[0], str)
            or isinstance(address_data[1], bool)
            or not isinstance(address_data[1], int)
        ):
            print(f"[系统] 用户 {target} 的 UDP 地址无效")
            return None

        sender = result.get("requester")
        if not isinstance(sender, str) or not sender:
            print("[系统] 当前昵称未注册")
            return None

        message_id = await self.peer.send_private(
            sender,
            target,
            content,
            (address_data[0], address_data[1]),
        )
        print(f"[系统] UDP 私聊已发送给 {target}，等待确认（#{message_id}）")
        return message_id

    async def find_user(self, target: str) -> dict:
        """向 TCP 服务端查询在线用户的 UDP 地址。"""

        if target in self._lookup_futures:
            return await asyncio.shield(self._lookup_futures[target])

        future = asyncio.get_running_loop().create_future()
        self._lookup_futures[target] = future
        try:
            await self.send(create_message("find_user", {"name": target}))
            return await asyncio.wait_for(asyncio.shield(future), timeout=3)
        except asyncio.TimeoutError:
            return {
                "name": target,
                "udp": None,
                "error": "查询 UDP 地址超时",
            }
        finally:
            if self._lookup_futures.get(target) is future:
                self._lookup_futures.pop(target, None)

    def _resolve_user_lookup(self, data: dict) -> None:
        target = data.get("name")
        future = self._lookup_futures.get(target)
        if future is not None and not future.done():
            future.set_result(data)

    async def _handle_udp_private_message(
        self,
        message: dict,
        _address: tuple[str, int],
    ) -> None:
        print(f"[UDP私聊] {message['from']}: {message['content']}")

    async def _handle_udp_delivery_failed(self, message: dict) -> None:
        target = message.get("to", "目标用户")
        print(f"[系统] UDP 私聊发送失败：未收到 {target} 的确认")

    async def close(self) -> None:
        self.running = False
        for future in self._lookup_futures.values():
            if not future.done():
                future.cancel()
        self._lookup_futures.clear()

        if self.writer is not None:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self.writer = None
        await self.peer.close()
