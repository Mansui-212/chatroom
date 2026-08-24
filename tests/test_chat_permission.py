import asyncio
import unittest

from chat.message import create_message
from chat.protocol import encode_message, read_message
from chat.server import ChatServer


class TestChatPermission(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ChatServer(host="127.0.0.1", port=0)
        self.async_server = await asyncio.start_server(
            self.server.handle_client,
            self.server.host,
            self.server.port,
        )
        self.port = self.async_server.sockets[0].getsockname()[1]
        self.task = asyncio.create_task(self.async_server.serve_forever())

    async def asyncTearDown(self):
        self.async_server.close()
        await self.async_server.wait_closed()
        self.task.cancel()

        try:
            await self.task
        except asyncio.CancelledError:
            pass

    async def test_chat_requires_nickname(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        await read_message(reader)

        writer.write(
            encode_message(
                create_message("chat", {"content": "hello"})
            )
        )
        await writer.drain()

        message = await read_message(reader)

        self.assertEqual(message["type"], "system")
        self.assertEqual(
            message["data"]["content"],
            "请先使用 /nick 注册昵称",
        )

        writer.close()
        await writer.wait_closed()
