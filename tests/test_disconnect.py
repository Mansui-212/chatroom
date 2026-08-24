import asyncio
import unittest

from chat.message import create_message
from chat.protocol import encode_message, read_message
from chat.server import ChatServer


class TestDisconnect(unittest.IsolatedAsyncioTestCase):
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

    async def connect_client(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        await read_message(reader)
        return reader, writer

    async def send(self, writer, message):
        writer.write(encode_message(message))
        await writer.drain()

    async def test_disconnect_removes_session_and_notifies_peers(self):
        reader_a, writer_a = await self.connect_client()
        reader_b, writer_b = await self.connect_client()

        await self.send(
            writer_a,
            create_message("nick", {"name": "张三"}),
        )
        await read_message(reader_a)

        await self.send(
            writer_b,
            create_message("nick", {"name": "李四"}),
        )
        await read_message(reader_a)
        await read_message(reader_b)

        writer_a.close()
        await writer_a.wait_closed()

        while True:
            message = await asyncio.wait_for(read_message(reader_b), timeout=1)
            if (
                message["type"] == "system"
                and message["data"]["content"] == "张三 离开大厅"
            ):
                break

        self.assertFalse(
            any(session.nickname == "张三" for session in self.server.sessions)
        )

        writer_b.close()
        await writer_b.wait_closed()
