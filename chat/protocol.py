"""TCP 分帧协议：4 字节长度前缀加 UTF-8 JSON 正文。"""

import json
import struct
from asyncio import StreamReader

from chat.config import ENCODING, MAX_MESSAGE_SIZE


class ProtocolError(Exception):
    """收到或发送了不符合协议的消息。"""


def _clean_utf8(value):
    """移除无法编码为 UTF-8 的 surrogate 字符。"""

    if isinstance(value, str):
        return value.encode(ENCODING, errors="ignore").decode(ENCODING)

    if isinstance(value, list):
        return [_clean_utf8(item) for item in value]

    if isinstance(value, dict):
        return {
            _clean_utf8(key): _clean_utf8(item)
            for key, item in value.items()
        }

    return value


def encode_message(message: dict) -> bytes:
    """将消息编码为一帧 TCP 数据。"""

    try:
        body = json.dumps(
            _clean_utf8(message),
            ensure_ascii=False,
        ).encode(ENCODING)
    except Exception as error:
        raise ProtocolError(f"json encode failed: {error}") from error

    if len(body) > MAX_MESSAGE_SIZE:
        raise ProtocolError("message too large")

    header = struct.pack(">I", len(body))
    return header + body


async def read_message(reader: StreamReader) -> dict | None:
    """从字节流读取并解码一条完整消息。"""

    try:
        header = await reader.readexactly(4)
    except EOFError:
        return None
    except Exception:
        return None

    length = struct.unpack(">I", header)[0]

    if length > MAX_MESSAGE_SIZE:
        raise ProtocolError("message too large")

    body = await reader.readexactly(length)

    try:
        return json.loads(body.decode(ENCODING))
    except Exception as error:
        raise ProtocolError(f"invalid message: {error}") from error
