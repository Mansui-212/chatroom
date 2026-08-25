"""客户端命令解析和服务端命令分发。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chat.message import create_message

if TYPE_CHECKING:
    from chat.server import ChatServer, ClientSession


class CommandError(ValueError):
    """用户输入的命令格式不正确。"""


class Command:
    """命令的客户端编码和服务端执行接口。"""

    name = ""
    usage = ""

    def build_message(self, arguments: str) -> dict:
        raise NotImplementedError

    async def execute(
        self,
        server: ChatServer,
        session: ClientSession,
        data: dict,
    ) -> None:
        raise NotImplementedError

    def _require_no_arguments(self, arguments: str) -> None:
        if arguments.strip():
            raise CommandError(f"用法：{self.usage}")


class NickCommand(Command):
    name = "nick"
    usage = "/nick <昵称>"

    def build_message(self, arguments: str) -> dict:
        nickname = arguments.strip()
        if not nickname:
            raise CommandError(f"用法：{self.usage}")
        return create_message(self.name, {"name": nickname})

    async def execute(self, server, session, data) -> None:
        await server.handle_nick(session, data)


class RoomsCommand(Command):
    name = "rooms"
    usage = "/rooms"

    def build_message(self, arguments: str) -> dict:
        self._require_no_arguments(arguments)
        return create_message(self.name, {})

    async def execute(self, server, session, data) -> None:
        await server.handle_rooms(session)


class JoinCommand(Command):
    name = "join"
    usage = "/join <房间名>"

    def build_message(self, arguments: str) -> dict:
        room = arguments.strip()
        if not room:
            raise CommandError(f"用法：{self.usage}")
        return create_message(self.name, {"room": room})

    async def execute(self, server, session, data) -> None:
        await server.handle_join(session, data)


class LeaveCommand(Command):
    name = "leave"
    usage = "/leave"

    def build_message(self, arguments: str) -> dict:
        self._require_no_arguments(arguments)
        return create_message(self.name, {})

    async def execute(self, server, session, data) -> None:
        await server.handle_leave(session)


class PmsgCommand(Command):
    name = "pmsg"
    usage = "/pmsg <用户> <内容>"

    def build_message(self, arguments: str) -> dict:
        target, separator, content = arguments.strip().partition(" ")
        content = content.strip()
        if not target or not separator or not content:
            raise CommandError(f"用法：{self.usage}")
        return create_message(
            self.name,
            {"target": target, "content": content},
        )

    async def execute(self, server, session, data) -> None:
        # 正常客户端不会把内容发给 TCP 服务端；该分支只防止旧客户端误用。
        await server.handle_pmsg(session)


class QuitCommand(Command):
    name = "quit"
    usage = "/quit"

    def build_message(self, arguments: str) -> dict:
        self._require_no_arguments(arguments)
        return create_message(self.name, {})

    async def execute(self, server, session, data) -> None:
        await session.close()


class KickCommand(Command):
    name = "kick"
    usage = "/kick <用户>"

    def build_message(self, arguments: str) -> dict:
        target = arguments.strip()
        if not target:
            raise CommandError(f"用法：{self.usage}")
        return create_message(self.name, {"target": target})

    async def execute(self, server, session, data) -> None:
        await server.handle_kick(session, data)


COMMANDS: dict[str, Command] = {
    command.name: command
    for command in (
        NickCommand(),
        RoomsCommand(),
        JoinCommand(),
        LeaveCommand(),
        PmsgCommand(),
        QuitCommand(),
        KickCommand(),
    )
}


def parse_client_command(text: str) -> dict:
    """将 ``/命令 参数`` 转为统一协议消息。"""

    command_name, _, arguments = text[1:].partition(" ")
    command = COMMANDS.get(command_name.lower())
    if command is None:
        raise CommandError(f"未知命令：/{command_name}")
    return command.build_message(arguments)


async def dispatch_command(
    name: str,
    server: ChatServer,
    session: ClientSession,
    data: dict,
) -> bool:
    """按消息类型执行命令；返回是否找到该命令。"""

    command = COMMANDS.get(name)
    if command is None:
        return False
    await command.execute(server, session, data)
    return True
