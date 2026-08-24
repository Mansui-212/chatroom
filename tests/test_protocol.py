import asyncio
import unittest

from chat.message import create_message
from chat.protocol import encode_message, read_message



class TestProtocol(
    unittest.IsolatedAsyncioTestCase
):


    async def test_encode_decode(self):

        msg = create_message(
            "chat",
            {"content": "hello"},
        )


        data = encode_message(msg)


        reader = asyncio.StreamReader()

        reader.feed_data(data)

        reader.feed_eof()


        result = await read_message(reader)


        self.assertEqual(
            msg,
            result
        )



    async def test_half_packet(self):

        msg = create_message(
            "chat",
            {"content": "半包测试"},
        )


        data = encode_message(msg)


        reader = asyncio.StreamReader()


        reader.feed_data(
            data[:3]
        )


        reader.feed_data(
            data[3:]
        )


        reader.feed_eof()


        result = await read_message(reader)


        self.assertEqual(
            msg,
            result
        )



    async def test_two_messages(self):

        msg1 = create_message(
            "system",
            {"id": 1},
        )

        msg2 = create_message(
            "system",
            {"id": 2},
        )


        reader = asyncio.StreamReader()


        reader.feed_data(
            encode_message(msg1)
            +
            encode_message(msg2)
        )


        reader.feed_eof()



        result1 = await read_message(reader)

        result2 = await read_message(reader)



        self.assertEqual(
            result1,
            msg1
        )

        self.assertEqual(
            result2,
            msg2
        )


    async def test_surrogate_characters_are_removed(self):

        msg = create_message(
            "chat",
            {"content": f"你{chr(0xDCE6)}好"},
        )


        data = encode_message(msg)


        reader = asyncio.StreamReader()

        reader.feed_data(data)

        reader.feed_eof()


        result = await read_message(reader)


        self.assertEqual(
            result["data"]["content"],
            "你好"
        )
