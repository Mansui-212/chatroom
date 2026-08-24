"""聊天室应用层消息的统一格式。"""

from datetime import datetime


def create_message(msg_type: str, data: dict) -> dict:
    """创建一条可通过协议层传输的聊天室消息。"""

    return {
        "type": msg_type,
        "timestamp": int(datetime.now().timestamp()),
        "data": data,
    }
