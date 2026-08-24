import asyncio
import unittest

from chat.message import create_message
from chat.protocol import (
    encode_message,
    read_message,
)
from chat.server import ChatServer


class TestChatIntegration(
    unittest.IsolatedAsyncioTestCase
):


    async def asyncSetUp(self):

        # 使用随机端口，避免占用8765
        self.server = ChatServer(
            host="127.0.0.1",
            port=0,
        )


        self.async_server = await asyncio.start_server(
            self.server.handle_client,
            self.server.host,
            self.server.port,
        )


        socket = self.async_server.sockets[0]

        self.port = socket.getsockname()[1]


        self.task = asyncio.create_task(
            self.async_server.serve_forever()
        )



    async def asyncTearDown(self):

        self.async_server.close()

        await self.async_server.wait_closed()


        self.task.cancel()


        try:

            await self.task

        except asyncio.CancelledError:

            pass



    async def connect_client(self):

        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            self.port,
        )


        # 清理欢迎消息
        await read_message(reader)


        return reader, writer



    async def send(
        self,
        writer,
        message,
    ):

        writer.write(
            encode_message(message)
        )

        await writer.drain()



    async def test_two_clients_chat(self):


        # 客户端A
        reader_a, writer_a = await self.connect_client()


        # 客户端B
        reader_b, writer_b = await self.connect_client()



        # A注册
        await self.send(
            writer_a,
            create_message(
                "nick",
                {"name": "张三"},
            )
        )


        # A收到自己的加入广播
        await read_message(reader_a)


        # B注册
        await self.send(
            writer_b,
            create_message(
                "nick",
                {"name": "李四"},
            )
        )


        # 消耗加入大厅系统消息

        while True:
            msg = await read_message(reader_a)

            if msg["type"] == "system":
                break


        while True:
            msg = await read_message(reader_b)

            if msg["type"] == "system":
                break



        # A发送聊天
        await self.send(
            writer_a,
            create_message(
                "chat",
                {"content": "你好李四"},
            )
        )


        # B等待聊天消息
        while True:

            message = await read_message(
                reader_b
            )

            if message["type"] == "chat":
                break


        self.assertEqual(
            message["data"]["sender"],
            "张三"
        )


        self.assertEqual(
            message["data"]["content"],
            "你好李四"
        )



        # A退出
        await self.send(
            writer_a,
            create_message("quit", {})
        )


        writer_a.close()

        await writer_a.wait_closed()



        # 等待服务端清理
        await asyncio.sleep(
            0.1
        )


        # B仍然可用
        await self.send(
            writer_b,
            create_message(
                "chat",
                {"content": "张三退出后继续聊天"},
            )
        )


        while True:

            message = await read_message(
                reader_b
            )

            if message["type"] == "chat":
                break


        self.assertEqual(
            message["type"],
            "chat"
        )


        self.assertEqual(
            message["data"]["content"],
            "张三退出后继续聊天"
        )



        writer_b.close()

        await writer_b.wait_closed()
