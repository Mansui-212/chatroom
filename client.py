import asyncio

from protocol import (
    encode_message,
    read_message,
)


class ChatClient:

    def __init__(
        self,
        host="127.0.0.1",
        port=8765,
    ):
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


        print(
            f"已连接服务器 {self.host}:{self.port}"
        )



    async def send(
        self,
        message: dict,
    ):

        data = encode_message(
            message
        )

        self.writer.write(data)

        await self.writer.drain()



    async def receive_loop(self):
        """
        持续接收服务器消息
        """

        try:

            while self.running:

                message = await read_message(
                    self.reader
                )


                if message is None:

                    print(
                        "服务器已断开"
                    )

                    break



                self.display(
                    message
                )


        except Exception as e:

            print(
                "接收异常:",
                e
            )


        finally:

            self.running = False



    def display(
        self,
        message: dict,
    ):

        msg_type = message.get(
            "type"
        )


        if msg_type == "chat":

            print(
                f"{message.get('sender')}: {message.get('content')}"
            )


        elif msg_type == "system":

            print(
                f"[系统] {message.get('content')}"
            )


        else:

            print(
                message
            )



    async def input_loop(self):
        """
        读取终端输入
        """

        while self.running:

            text = await asyncio.to_thread(
                input,
                "> "
            )


            text = text.strip()

            text = (
                text.encode(
                    "utf-8",
                    errors="ignore",
                ).decode("utf-8")
            )


            if not text:

                continue



            # 注册昵称

            if text.startswith(
                "/nick "
            ):

                nickname = text[6:].strip()


                await self.send(
                    {
                        "type":"nick",
                        "name":nickname,
                    }
                )


            # 退出

            elif text == "/quit":

                await self.send(
                    {
                        "type":"quit"
                    }
                )


                self.running = False


                break



            # 普通聊天

            else:

                await self.send(
                    {
                        "type":"chat",
                        "content":text,
                    }
                )



    async def close(self):

        if self.writer:

            self.writer.close()

            await self.writer.wait_closed()



async def main():

    client = ChatClient()


    await client.connect()


    receive_task = asyncio.create_task(
        client.receive_loop()
    )


    input_task = asyncio.create_task(
        client.input_loop()
    )


    await asyncio.wait(
        [
            receive_task,
            input_task,
        ],
        return_when=asyncio.FIRST_COMPLETED
    )


    await client.close()



if __name__ == "__main__":

    asyncio.run(main())
