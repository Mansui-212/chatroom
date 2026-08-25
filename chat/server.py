"""支持用户、房间、私聊和命令分发的聊天室服务端。"""

from __future__ import annotations

import asyncio

from chat.commands import dispatch_command
from chat.config import ADMIN_NICKNAMES
from chat.logger import logger
from chat.message import create_message
from chat.protocol import ProtocolError, encode_message, read_message
from chat.room import Room
from chat.user import User


class ClientSession:
    """一个 TCP 客户端连接，只保存网络相关状态和所属用户。"""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        server: ChatServer,
        user_id: int = 0,
    ):
        self.reader = reader
        self.writer = writer
        self.server = server
        self.user = User(id=user_id, tcp_session=self)

    # 保留旧属性的兼容入口，业务代码统一使用 session.user。
    @property
    def nickname(self) -> str | None:
        return self.user.nickname

    @nickname.setter
    def nickname(self, value: str | None) -> None:
        self.user.nickname = value

    @property
    def room(self) -> str:
        return self.user.current_room

    @room.setter
    def room(self, value: str) -> None:
        self.user.current_room = value

    async def send(self, message: dict) -> None:
        """将一条应用层消息写入连接。"""

        data = encode_message(message)
        self.writer.write(data)
        await self.writer.drain()

    async def close(self) -> None:
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except (ConnectionError, OSError, RuntimeError):
            # 连接已经被对端关闭时，清理仍应继续。
            pass


class ChatServer:
    """聊天室业务协调器。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port

        self.sessions: set[ClientSession] = set()
        self.users: dict[str, User] = {}
        self.rooms: dict[str, Room] = {"lobby": Room("lobby")}

        self._next_user_id = 1
        self._server: asyncio.AbstractServer | None = None
        self._is_shutting_down = False

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port,
        )
        logger.info("Chat server started on %s:%s", self.host, self.port)

        async with self._server:
            await self._server.serve_forever()

    async def shutdown(self) -> None:
        """通知在线用户、关闭连接并停止监听。"""

        if self._is_shutting_down:
            return

        self._is_shutting_down = True
        logger.info("Chat server is shutting down")
        await self.broadcast(create_message("system", {"content": "服务器正在关闭"}))

        for session in list(self.sessions):
            await self.remove_session(session, notify=False)

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        session = ClientSession(reader, writer, self, self._next_user_id)
        self._next_user_id += 1
        self.sessions.add(session)
        self.rooms["lobby"].add_member(session.user)

        addr = writer.get_extra_info("peername")
        logger.info("client connected: %s", addr)

        try:
            await session.send(
                create_message(
                    "system",
                    {"content": "欢迎进入 lobby，请使用 /nick 注册昵称"},
                )
            )
            while True:
                message = await read_message(reader)
                if message is None:
                    break
                await self.handle_message(session, message)
        except (ConnectionError, ProtocolError):
            pass
        finally:
            await self.remove_session(session)

    async def handle_message(self, session: ClientSession, message: dict) -> None:
        """验证消息，然后交给统一命令表或普通聊天处理。"""

        if not isinstance(message, dict):
            await self.send_system(session, "消息格式错误")
            return

        msg_type = message.get("type")
        data = message.get("data", {})
        if not isinstance(msg_type, str) or not isinstance(data, dict):
            await self.send_system(session, "消息格式错误")
            return

        if msg_type == "udp_register":
            await self.handle_udp_register(session, data)
            return
        if msg_type == "find_user":
            await self.handle_find_user(session, data)
            return
        if await dispatch_command(msg_type, self, session, data):
            return

        if msg_type == "chat":
            await self.handle_chat(session, data)
            return

        await self.send_system(session, "未知消息类型")

    async def handle_nick(self, session: ClientSession, message: dict) -> None:
        nickname = message.get("name")
        if not isinstance(nickname, str) or not (nickname := nickname.strip()):
            await self.send_system(session, "昵称不能为空")
            return

        if session.user.nickname:
            await self.send_system(session, "昵称已经注册")
            return

        if nickname in self.users:
            await self.send_system(session, "昵称已存在")
            return

        session.user.nickname = nickname
        if nickname in ADMIN_NICKNAMES:
            session.user.role = "admin"
        self.users[nickname] = session.user

        await self.send_room_history(session, self.rooms[session.user.current_room])
        await self.broadcast_to_room(
            self.rooms[session.user.current_room],
            create_message("system", {"content": f"{nickname} 加入大厅"}),
        )

    async def handle_chat(self, session: ClientSession, message: dict) -> None:
        if not await self.require_registered(session):
            return

        content = message.get("content")
        if not isinstance(content, str) or not (content := content.strip()):
            await self.send_system(session, "消息不能为空")
            return

        room = self.rooms[session.user.current_room]
        chat_message = create_message(
            "chat",
            {
                "sender": session.user.nickname,
                "content": content,
                "room": room.name,
            },
        )
        room.history.add(chat_message)
        await self.broadcast_to_room(room, chat_message)

    async def handle_rooms(self, session: ClientSession) -> None:
        room_names = sorted(self.rooms)
        await session.send(
            create_message(
                "rooms",
                {
                    "rooms": room_names,
                    "content": "房间列表：\n" + "\n".join(room_names),
                },
            )
        )

    async def handle_join(self, session: ClientSession, message: dict) -> None:
        if not await self.require_registered(session):
            return

        room_name = message.get("room")
        if not isinstance(room_name, str) or not (room_name := room_name.strip()):
            await self.send_system(session, "房间名不能为空")
            return
        if len(room_name) > 64:
            await self.send_system(session, "房间名不能超过 64 个字符")
            return

        if room_name == session.user.current_room:
            await self.send_system(session, f"你已经在 {self.room_label(room_name)}")
            return

        old_room = self.rooms[session.user.current_room]
        old_room.remove_member(session.user)
        await self.broadcast_to_room(
            old_room,
            create_message(
                "system",
                {
                    "content": self.left_room_content(
                        session.user.nickname,
                        old_room.name,
                    )
                },
            ),
        )

        new_room = self.rooms.setdefault(room_name, Room(room_name))
        new_room.add_member(session.user)
        session.user.current_room = room_name

        await self.send_room_history(session, new_room)
        await self.broadcast_to_room(
            new_room,
            create_message(
                "system",
                {
                    "content": self.entered_room_content(
                        session.user.nickname,
                        new_room.name,
                    )
                },
            ),
        )

    async def handle_leave(self, session: ClientSession) -> None:
        if not await self.require_registered(session):
            return

        if session.user.current_room == "lobby":
            await self.send_system(session, "你已经在大厅")
            return

        await self.handle_join(session, {"room": "lobby"})

    async def handle_udp_register(
        self,
        session: ClientSession,
        message: dict,
    ) -> None:
        """登记客户端 UDP 端口，IP 使用 TCP 连接的对端地址。"""

        port = message.get("port")
        if isinstance(port, bool) or not isinstance(port, int):
            await self.send_system(session, "UDP 端口格式错误")
            return
        if not 1 <= port <= 65535:
            await self.send_system(session, "UDP 端口范围错误")
            return

        peername = session.writer.get_extra_info("peername")
        if not peername:
            await self.send_system(session, "无法获取 UDP 地址")
            return

        session.user.udp_address = (peername[0], port)
        logger.info(
            "UDP registered: user=%s address=%s:%s",
            session.user.nickname or f"#{session.user.id}",
            peername[0],
            port,
        )

    async def handle_find_user(
        self,
        session: ClientSession,
        message: dict,
    ) -> None:
        """仅返回目标 UDP 地址，绝不通过 TCP 转发私聊正文。"""

        target_name = message.get("name")
        if not isinstance(target_name, str) or not (target_name := target_name.strip()):
            await session.send(
                create_message(
                    "user_found",
                    {"name": "", "udp": None, "error": "用户不能为空"},
                )
            )
            return

        if not session.user.nickname:
            await session.send(
                create_message(
                    "user_found",
                    {
                        "name": target_name,
                        "udp": None,
                        "error": "请先使用 /nick 注册昵称",
                    },
                )
            )
            return

        target = self.users.get(target_name)
        if target is None or target.tcp_session not in self.sessions:
            await session.send(
                create_message(
                    "user_found",
                    {
                        "name": target_name,
                        "udp": None,
                        "error": f"用户 {target_name} 不在线",
                    },
                )
            )
            return
        if target.udp_address is None:
            await session.send(
                create_message(
                    "user_found",
                    {
                        "name": target_name,
                        "udp": None,
                        "error": f"用户 {target_name} 未启用 UDP 私聊",
                    },
                )
            )
            return

        host, port = target.udp_address
        await session.send(
            create_message(
                "user_found",
                {
                    "name": target_name,
                    "udp": [host, port],
                    "requester": session.user.nickname,
                },
            )
        )
        logger.info("UDP peer lookup: %s -> %s", session.user.nickname, target_name)

    async def handle_pmsg(self, session: ClientSession) -> None:
        """拒绝经 TCP 传来的私聊正文，防止服务端退化为转发节点。"""

        if await self.require_registered(session):
            await self.send_system(session, "请使用支持 UDP 的客户端发送 /pmsg")

    async def handle_kick(self, session: ClientSession, message: dict) -> None:
        """管理员预留命令：普通用户无法移除其他用户。"""

        if not await self.require_registered(session):
            return
        if session.user.role != "admin":
            await self.send_system(session, "无权限执行 /kick")
            return

        target_name = message.get("target")
        if not isinstance(target_name, str) or not (target_name := target_name.strip()):
            await self.send_system(session, "踢出目标不能为空")
            return

        target = self.users.get(target_name)
        if target is None or target.tcp_session not in self.sessions:
            await self.send_system(session, f"用户 {target_name} 不在线")
            return
        if target is session.user:
            await self.send_system(session, "不能踢出自己")
            return

        target_session = target.tcp_session
        if target_session is None:
            await self.send_system(session, f"用户 {target_name} 不在线")
            return
        await self.send_system(target_session, "你已被管理员移出聊天室")
        await self.remove_session(target_session)

    async def require_registered(self, session: ClientSession) -> bool:
        if session.user.nickname:
            return True
        await self.send_system(session, "请先使用 /nick 注册昵称")
        return False

    async def send_system(self, session: ClientSession, content: str) -> None:
        await session.send(create_message("system", {"content": content}))

    async def send_room_history(self, session: ClientSession, room: Room) -> None:
        """只向刚进入房间的用户发送该房间最近 100 条聊天记录。"""

        messages = room.history.get_recent()
        if not messages:
            return
        await session.send(
            create_message(
                "history",
                {"room": room.name, "messages": messages},
            )
        )

    async def broadcast_to_room(self, room: Room, message: dict) -> None:
        """仅向指定房间的成员广播，并清理失效连接。"""

        dead_sessions: list[ClientSession] = []
        for user in list(room.members):
            session = user.tcp_session
            if session is None or session not in self.sessions:
                continue
            try:
                await session.send(message)
            except (ConnectionError, OSError, RuntimeError):
                dead_sessions.append(session)

        for dead_session in dead_sessions:
            await self.remove_session(dead_session)

    async def broadcast(self, message: dict) -> None:
        """向所有在线连接广播，用于服务端级事件。"""

        dead_sessions: list[ClientSession] = []
        for session in list(self.sessions):
            try:
                await session.send(message)
            except (ConnectionError, OSError, RuntimeError):
                dead_sessions.append(session)

        for dead_session in dead_sessions:
            await self.remove_session(dead_session)

    async def remove_session(
        self,
        session: ClientSession,
        notify: bool = True,
    ) -> None:
        """从会话、用户索引和房间成员中清理连接。"""

        if session not in self.sessions:
            return

        self.sessions.remove(session)
        user = session.user
        room = self.rooms.get(user.current_room)
        if room is not None:
            room.remove_member(user)

        nickname = user.nickname
        if nickname and self.users.get(nickname) is user:
            del self.users[nickname]
        user.tcp_session = None
        user.udp_address = None

        await session.close()

        if nickname and room is not None and notify:
            await self.broadcast_to_room(
                room,
                create_message(
                    "system",
                    {"content": self.left_room_content(nickname, room.name)},
                ),
            )

    @staticmethod
    def room_label(room_name: str) -> str:
        return "大厅" if room_name == "lobby" else f"{room_name} 房间"

    @staticmethod
    def entered_room_content(nickname: str, room_name: str) -> str:
        return (
            f"{nickname} 进入大厅"
            if room_name == "lobby"
            else f"{nickname}进入{room_name}房间"
        )

    @staticmethod
    def left_room_content(nickname: str, room_name: str) -> str:
        return (
            f"{nickname} 离开大厅"
            if room_name == "lobby"
            else f"{nickname}离开{room_name}房间"
        )
