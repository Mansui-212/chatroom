import asyncio

from chat.server import ChatServer



async def main():

    server = ChatServer(
        host="127.0.0.1",
        port=8765,
    )

    await server.start()



if __name__ == "__main__":

    asyncio.run(main())
