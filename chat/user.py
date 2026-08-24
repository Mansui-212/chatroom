"""聊天室中的用户领域对象。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat.server import ClientSession


class User:
    """独立于网络连接的用户信息。

    ``session`` 仍然指向当前在线连接，方便服务端投递消息；以后增加
    等级、权限或在线状态时不需要让 ``ClientSession`` 承担这些职责。
    """

    def __init__(
        self,
        id: int,
        nickname: str | None = None,
        current_room: str = "lobby",
        session: ClientSession | None = None,
        role: str = "user",
    ):
        self.id = id
        self.nickname = nickname
        self.current_room = current_room
        self.session = session
        self.role = role

