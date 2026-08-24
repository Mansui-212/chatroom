import asyncio

from protocol import (
    encode_message,
    read_message,
    ProtocolError,
)


class ClientSession:
    """
    一个客户端连接
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        server,
    ):
        self.reader = reader
        self.writer = writer
        self.server = server

        self.nickname = None
        self.room = "lobby"


    async def send(
        self,
        message: dict
    ):
        """
        发送消息
        """

        data = encode_message(
            message
        )

        self.writer.write(data)

        await self.writer.drain()



    async def close(self):

        try:
            self.writer.close()

            await self.writer.wait_closed()

        except Exception:
            pass



class ChatServer:

    def __init__(
        self,
        host="127.0.0.1",
        port=8765,
    ):

        self.host = host
        self.port = port

        self.sessions = set()



    async def start(self):

        server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port,
        )


        print(
            f"Chat server started on {self.host}:{self.port}"
        )


        async with server:

            await server.serve_forever()



    async def handle_client(
        self,
        reader,
        writer,
    ):

        session = ClientSession(
            reader,
            writer,
            self,
        )


        self.sessions.add(session)


        addr = writer.get_extra_info(
            "peername"
        )


        print(
            f"client connected: {addr}"
        )


        await session.send(
            {
                "type":"system",
                "content":
                "欢迎进入 lobby，请使用 /nick 注册昵称"
            }
        )


        try:

            while True:

                message = await read_message(
                    reader
                )


                if message is None:

                    break


                await self.handle_message(
                    session,
                    message
                )


        except (
            ConnectionResetError,
            ProtocolError,
        ):

            pass


        finally:

            await self.remove_session(
                session
            )



    async def handle_message(
        self,
        session,
        message,
    ):


        msg_type = message.get(
            "type"
        )


        if msg_type == "nick":

            await self.handle_nick(
                session,
                message
            )


        elif msg_type == "chat":

            await self.handle_chat(
                session,
                message
            )


        elif msg_type == "quit":

            await session.close()



    async def handle_nick(
        self,
        session,
        message,
    ):

        nickname = message.get(
            "name"
        )


        if not nickname:

            await session.send(
                {
                    "type":"system",
                    "content":
                    "昵称不能为空"
                }
            )

            return



        for s in self.sessions:

            if s.nickname == nickname:

                await session.send(
                    {
                        "type":"system",
                        "content":
                        "昵称已存在"
                    }
                )

                return



        session.nickname = nickname



        await self.broadcast(
            {
                "type":"system",
                "content":
                f"{nickname} 加入大厅"
            }
        )



    async def handle_chat(
        self,
        session,
        message,
    ):

        if not session.nickname:

            await session.send(
                {
                    "type":"system",
                    "content":
                    "请先使用 /nick 注册昵称"
                }
            )

            return



        content = message.get(
            "content"
        )


        await self.broadcast(
            {
                "type":"chat",
                "sender":
                    session.nickname,
                "content":
                    content,
            }
        )



    async def broadcast(
        self,
        message:dict,
    ):

        dead = []


        for session in list(
            self.sessions
        ):

            try:

                await session.send(
                    message
                )

            except Exception:

                dead.append(
                    session
                )



        for session in dead:

            await self.remove_session(
                session
            )



    async def remove_session(
        self,
        session,
    ):

        if session not in self.sessions:

            return


        self.sessions.remove(
            session
        )


        nickname = session.nickname


        await session.close()



        if nickname:

            await self.broadcast(
                {
                    "type":"system",
                    "content":
                    f"{nickname} 离开大厅"
                }
            )
