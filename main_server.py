"""聊天室服务端启动入口。"""

import asyncio
import signal

from chat.config import HOST, PORT
from chat.server import ChatServer


async def main():
    server = ChatServer(HOST, PORT)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    server_task = asyncio.create_task(server.start())
    stop_task = asyncio.create_task(stop_event.wait())

    done, _ = await asyncio.wait(
        [server_task, stop_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    if stop_task in done:
        await server.shutdown()
        await server_task
    else:
        stop_task.cancel()
        await server_task


if __name__ == "__main__":
    asyncio.run(main())
