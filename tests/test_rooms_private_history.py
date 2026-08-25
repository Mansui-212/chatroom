import asyncio
import unittest

from chat.message import create_message
from chat.protocol import encode_message, read_message
from chat.server import ChatServer


class TestRoomsPrivateAndHistory(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ChatServer(host="127.0.0.1", port=0)
        self.async_server = await asyncio.start_server(
            self.server.handle_client,
            self.server.host,
            self.server.port,
        )
        self.port = self.async_server.sockets[0].getsockname()[1]
        self.server_task = asyncio.create_task(self.async_server.serve_forever())
        self.writers = []

    async def asyncTearDown(self):
        for writer in self.writers:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()

        self.async_server.close()
        await self.async_server.wait_closed()
        self.server_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.server_task

    async def connect_client(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        self.writers.append(writer)
        await read_message(reader)  # 欢迎消息
        return reader, writer

    async def send(self, writer, message):
        writer.write(encode_message(message))
        await writer.drain()

    async def read_until(self, reader, predicate):
        for _ in range(20):
            message = await asyncio.wait_for(read_message(reader), timeout=1)
            if predicate(message):
                return message
        self.fail("未在预期消息数内收到目标消息")

    async def register_all(self, clients):
        for nickname, reader, writer in clients:
            await self.send(writer, create_message("nick", {"name": nickname}))
            for _, other_reader, _ in clients:
                await self.read_until(
                    other_reader,
                    lambda message, name=nickname: (
                        message["type"] == "system"
                        and message["data"]["content"] == f"{name} 加入大厅"
                    ),
                )

    async def test_room_chat_is_isolated(self):
        reader_a, writer_a = await self.connect_client()
        reader_b, writer_b = await self.connect_client()
        await self.register_all(
            [
                ("A", reader_a, writer_a),
                ("B", reader_b, writer_b),
            ]
        )

        await self.send(writer_a, create_message("join", {"room": "game"}))
        await self.read_until(
            reader_a,
            lambda message: (
                message["type"] == "system"
                and message["data"]["content"] == "A进入game房间"
            ),
        )
        await self.read_until(
            reader_b,
            lambda message: (
                message["type"] == "system"
                and message["data"]["content"] == "A 离开大厅"
            ),
        )

        await self.send(writer_b, create_message("rooms", {}))
        rooms = await self.read_until(
            reader_b,
            lambda message: message["type"] == "rooms",
        )
        self.assertEqual(rooms["data"]["rooms"], ["game", "lobby"])

        await self.send(writer_b, create_message("join", {"room": "music"}))
        await self.read_until(
            reader_b,
            lambda message: (
                message["type"] == "system"
                and message["data"]["content"] == "B进入music房间"
            ),
        )

        await self.send(writer_a, create_message("chat", {"content": "hello game"}))
        received = await self.read_until(
            reader_a,
            lambda message: message["type"] == "chat",
        )
        self.assertEqual(received["data"]["room"], "game")
        self.assertEqual(received["data"]["content"], "hello game")

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(read_message(reader_b), timeout=0.1)

    async def test_tcp_does_not_forward_pmsg_content(self):
        reader_a, writer_a = await self.connect_client()
        reader_b, writer_b = await self.connect_client()
        await self.register_all(
            [
                ("A", reader_a, writer_a),
                ("B", reader_b, writer_b),
            ]
        )

        await self.send(
            writer_a,
            create_message("pmsg", {"target": "B", "content": "你好"}),
        )
        message = await self.read_until(
            reader_a,
            lambda received: (
                received["type"] == "system"
                and received["data"]["content"]
                == "请使用支持 UDP 的客户端发送 /pmsg"
            ),
        )
        self.assertEqual(message["type"], "system")

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(read_message(reader_b), timeout=0.1)

    async def test_join_receives_only_latest_100_history_messages(self):
        reader_a, writer_a = await self.connect_client()
        await self.register_all([("A", reader_a, writer_a)])

        for number in range(101):
            await self.send(
                writer_a,
                create_message("chat", {"content": f"message-{number}"}),
            )
            await self.read_until(
                reader_a,
                lambda message: message["type"] == "chat",
            )

        reader_b, writer_b = await self.connect_client()
        await self.send(writer_b, create_message("nick", {"name": "B"}))
        history = await self.read_until(
            reader_b,
            lambda message: message["type"] == "history",
        )

        messages = history["data"]["messages"]
        self.assertEqual(len(messages), 100)
        self.assertEqual(messages[0]["data"]["content"], "message-1")
        self.assertEqual(messages[-1]["data"]["content"], "message-100")
