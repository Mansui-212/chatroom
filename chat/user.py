"""聊天室中的用户领域对象。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat.server import ClientSession


class User:
    """独立于网络连接的用户信息。

    TCP 会话和 UDP 地址都归属用户模型；聊天室业务不再需要把用户状态
    混入 ``ClientSession``。
    """

    def __init__(
        self,
        id: int = 0,
        nickname: str | None = None,
        room: str = "lobby",
        tcp_session: ClientSession | None = None,
        udp_address: tuple[str, int] | None = None,
        role: str = "user",
        # 兼容此前公开的构造参数。
        current_room: str | None = None,
        session: ClientSession | None = None,
    ):
        self.id = id
        self.nickname = nickname
        self.room = current_room if current_room is not None else room
        self.tcp_session = tcp_session if tcp_session is not None else session
        self.udp_address = udp_address
        self.role = role

    @property
    def current_room(self) -> str:
        """此前房间字段的兼容别名。"""

        return self.room

    @current_room.setter
    def current_room(self, value: str) -> None:
        self.room = value

    @property
    def session(self) -> ClientSession | None:
        """此前 TCP 会话字段的兼容别名。"""

        return self.tcp_session

    @session.setter
    def session(self, value: ClientSession | None) -> None:
        self.tcp_session = value
