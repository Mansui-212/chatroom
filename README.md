# Chatroom

一个基于 Python `asyncio`、TCP 长连接和命令行的多人聊天室。项目只使用 Python 标准库，支持默认 `lobby` 大厅、动态房间、私聊和最近消息历史。

## 已实现能力

- TCP 长连接与多客户端并发处理；
- 4 字节长度前缀 + UTF-8 JSON 的流协议，正确处理粘包和半包；
- `User` 将昵称、当前房间、角色和网络会话分离，便于后续增加用户等级、状态和权限；
- 默认 `lobby` 大厅与动态创建的多房间；同一房间内才会收到普通群聊；
- `/rooms` 查看房间、`/join <房间名>` 加入/创建房间、`/leave` 返回大厅；
- `/msg <用户> <内容>` 私聊指定在线用户，不会向旁观者广播；
- 每个房间独立保留最近 100 条普通聊天，新用户进入时自动收到该房间历史；
- 集中命令表支持 `/nick`、`/rooms`、`/join`、`/leave`、`/msg`、`/quit`，并为管理员 `/kick` 预留权限校验；
- 重复昵称与未注册聊天的服务端提示；
- 客户端异常断开后的会话清理和离线通知；
- 集中配置、文件日志和 `Ctrl+C` 优雅关闭；
- 针对协议、群聊、重复昵称、未注册聊天和断开的自动化测试。

## 环境要求

- Python 3.10 或更高版本；
- 不需要安装第三方包。

默认监听地址为 `127.0.0.1:8765`，可在 [chat/config.py](chat/config.py) 中修改。

## 快速开始

在项目根目录打开三个终端。

第一个终端启动服务端：

```bash
python3 main_server.py
```

第二、三个终端分别启动客户端：

```bash
python3 main_client.py
```

在两个客户端中分别输入：

```text
/nick 张三
/nick 李四
```

之后直接输入任意文本即可向当前房间广播。常用命令：

```text
/rooms                 # 查看 lobby 和已创建房间
/join game             # 加入（不存在则创建）game 房间
/leave                 # 返回 lobby
/msg 李四 今天开黑吗    # 向李四发送私聊
/quit                  # 主动退出
```

`/join game` 后，只有 `game` 房间成员会收到随后发送的普通消息；该房间已有聊天记录时，进入者会先看到“最近聊天”。服务端按 `Ctrl+C` 会向客户端发送“服务器正在关闭”通知并关闭连接。

管理员通过 `chat/config.py` 的 `ADMIN_NICKNAMES` 显式配置；管理员可使用 `/kick <用户>`，普通用户会收到无权限提示。

## 通信协议

TCP 是字节流，因此每条应用消息采用以下帧格式：

```text
┌──────────────────────┬──────────────────────────┐
│ 4-byte uint32 (BE)   │ UTF-8 encoded JSON body  │
└──────────────────────┴──────────────────────────┘
```

- 长度字段使用网络字节序，表示 JSON 正文的字节数；
- 最大单帧为 1 MiB；
- 发送前会清理无法编码为 UTF-8 的 surrogate 字符，避免终端输入造成编码中断。

所有聊天室消息使用统一格式：

```json
{
  "type": "chat",
  "timestamp": 1780000000,
  "data": {
    "sender": "张三",
    "content": "你好李四"
  }
}
```

## 项目结构

```text
chatroom/
├── main_server.py          # 服务端启动入口
├── main_client.py          # 客户端启动入口
├── chat/
│   ├── __init__.py
│   ├── server.py           # 服务端核心与会话管理
│   ├── client.py           # 命令行客户端核心
│   ├── protocol.py         # TCP 分帧与 JSON 编解码
│   ├── config.py           # 主机、端口、编码和帧大小配置
│   ├── logger.py           # 文件与终端日志配置
│   ├── message.py          # 统一消息构造器
│   ├── user.py             # 用户信息与角色
│   ├── room.py             # 房间成员与独立历史
│   ├── history.py          # 最近 100 条消息的有界历史
│   └── commands.py         # 命令解析与服务端分发
├── tests/
│   ├── test_protocol.py
│   ├── test_integration.py
│   ├── test_nickname.py
│   ├── test_chat_permission.py
│   ├── test_disconnect.py
│   └── test_rooms_private_history.py
├── logs/
│   └── chat.log            # 运行时生成，未纳入 Git
└── README.md
```

## 测试

运行全部自动化测试：

```bash
python3 -m unittest discover tests
```

当前测试覆盖协议编解码、半包、连续消息、非法 Unicode 清理、双客户端群聊、重复昵称、未注册聊天、异常断开、跨房间隔离、私聊隔离和 100 条历史限制。

## 日志

服务端日志同时输出至终端和 `logs/chat.log`。日志文件是运行产物，已由 `.gitignore` 排除。

## 后续方向

后续可在现有用户角色和命令体系上实现管理员初始化、`/ban`、持久化历史及 WebSocket 网关，以供 Vue 前端接入。
