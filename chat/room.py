"""聊天室房间模型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chat.config import HISTORY_LIMIT
from chat.history import MessageHistory

if TYPE_CHECKING:
    from chat.user import User


class Room:
    """一个拥有成员集合和独立消息历史的聊天房间。"""

    def __init__(self, name: str, history_limit: int = HISTORY_LIMIT):
        self.name = name
        self.members: set[User] = set()
        self.history = MessageHistory(history_limit)

    def add_member(self, user: User) -> None:
        self.members.add(user)

    def remove_member(self, user: User) -> None:
        self.members.discard(user)
