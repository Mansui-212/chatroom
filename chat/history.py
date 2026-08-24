"""房间聊天历史。"""

from __future__ import annotations

class MessageHistory:
    """仅保留最近若干条消息的内存历史。"""

    def __init__(self, limit: int = 100):
        if limit <= 0:
            raise ValueError("history limit must be positive")

        self.limit = limit
        self.messages: list[dict] = []

    def add(self, message: dict) -> None:
        """记录一条消息的快照，避免调用方随后修改原字典影响历史。"""

        self.messages.append(dict(message))
        if len(self.messages) > self.limit:
            del self.messages[: len(self.messages) - self.limit]

    def get_recent(self, limit: int | None = None) -> list[dict]:
        """按时间顺序返回最近消息的副本。"""

        messages = self.messages
        if limit is not None:
            messages = messages[-limit:]
        return [dict(message) for message in messages]
