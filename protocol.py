import json
import struct
from asyncio import StreamReader


MAX_MESSAGE_SIZE = 1024 * 1024


class ProtocolError(Exception):
    pass


def _clean_utf8(value):
    """移除无法编码为 UTF-8 的 surrogate 字符。"""

    if isinstance(value, str):
        return value.encode(
            "utf-8",
            errors="ignore",
        ).decode("utf-8")

    if isinstance(value, list):
        return [_clean_utf8(item) for item in value]

    if isinstance(value, dict):
        return {
            _clean_utf8(key): _clean_utf8(item)
            for key, item in value.items()
        }

    return value


def encode_message(message: dict) -> bytes:
    """
    JSON编码:
    4字节长度 + JSON正文
    """

    try:
        body = json.dumps(
            _clean_utf8(message),
            ensure_ascii=False
        ).encode("utf-8")

    except Exception as e:
        raise ProtocolError(
            f"json encode failed: {e}"
        )

    if len(body) > MAX_MESSAGE_SIZE:
        raise ProtocolError(
            "message too large"
        )

    header = struct.pack(
        ">I",
        len(body)
    )

    return header + body



async def read_message(
    reader: StreamReader
) -> dict | None:
    """
    读取一条完整消息

    TCP:
    半包:
        readexactly自动等待

    粘包:
        根据长度切割
    """

    try:
        header = await reader.readexactly(4)

    except EOFError:
        return None

    except Exception:
        return None


    length = struct.unpack(
        ">I",
        header
    )[0]


    if length > MAX_MESSAGE_SIZE:
        raise ProtocolError(
            "message too large"
        )


    body = await reader.readexactly(
        length
    )


    try:
        text = body.decode(
            "utf-8"
        )

        return json.loads(text)

    except Exception as e:
        raise ProtocolError(
            f"invalid message: {e}"
        )
