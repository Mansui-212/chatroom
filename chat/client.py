"""命令行聊天室客户端核心。"""

import asyncio

from chat.commands import CommandError, parse_client_command
from chat.config import HOST, PORT, ENCODING
from chat.message import create_message
from chat.protocol import encode_message, read_message


class ChatClient:
    """通过 TCP 长连接与聊天室服务端通信。"""

    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.running = True

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(
            self.host,
            self.port,
        )
        print(f"已连接服务器 {self.host}:{self.port}")

    async def start(self):
        """启动收发循环，任一循环结束时关闭连接。"""

        receive_task = asyncio.create_task(self.receive_loop())
        input_task = asyncio.create_task(self.input_loop())

        await asyncio.wait(
            [receive_task, input_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        await self.close()

    async def send(self, message: dict):
        data = encode_message(message)
        self.writer.write(data)
        await self.writer.drain()

    async def receive_loop(self):
        """持续接收并显示服务端消息。"""

        try:
            while self.running:
                message = await read_message(self.reader)

                if message is None:
                    print("服务器已断开")
                    break

                self.display(message)
        except Exception as error:
            print("接收异常:", error)
        finally:
            self.running = False

    def display(self, message: dict):
        """按消息类型显示服务端事件。"""

        msg_type = message.get("type")
        data = message.get("data", {})

        if msg_type == "chat":
            print(f"{data.get('sender')}: {data.get('content')}")
        elif msg_type == "system":
            print(f"[系统] {data.get('content')}")
        elif msg_type == "private":
            print(f"[私聊] {data.get('sender')}: {data.get('content')}")
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

    async def input_loop(self):
        """读取终端输入并转换成聊天消息。"""

        while self.running:
            try:
                text = await asyncio.to_thread(input, "> ")
            except EOFError:
                self.running = False
                break
            text = text.strip()
            text = text.encode(ENCODING, errors="ignore").decode(ENCODING)

            if not text:
                continue

            if text.startswith("/"):
                try:
                    message = parse_client_command(text)
                except CommandError as error:
                    print(f"[系统] {error}")
                    continue

                await self.send(message)
                if message["type"] == "quit":
                    self.running = False
                    break
            else:
                await self.send(create_message("chat", {"content": text}))

    async def close(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
