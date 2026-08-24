"""聊天室命令行客户端启动入口。"""

import asyncio

from chat.client import ChatClient


async def main():
    client = ChatClient()
    await client.connect()
    await client.start()


if __name__ == "__main__":
    asyncio.run(main())
