# Chatroom

一个基于 Python `asyncio`、TCP 长连接和命令行的多人聊天室。项目只使用 Python 标准库；目前提供默认 `lobby` 大厅、昵称注册、群聊、断线清理、日志和优雅关闭。

## 已实现能力

- TCP 长连接与多客户端并发处理；
- 4 字节长度前缀 + UTF-8 JSON 的流协议，正确处理粘包和半包；
- `/nick <昵称>` 注册昵称、普通文本大厅群聊、`/quit` 主动退出；
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

之后直接输入任意文本即可向 `lobby` 大厅广播。输入 `/quit` 可主动断开；服务端按 `Ctrl+C` 会向客户端发送“服务器正在关闭”通知并关闭连接。

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
│   └── message.py          # 统一消息构造器
├── tests/
│   ├── test_protocol.py
│   ├── test_integration.py
│   ├── test_nickname.py
│   ├── test_chat_permission.py
│   └── test_disconnect.py
├── logs/
│   └── chat.log            # 运行时生成，未纳入 Git
└── README.md
```

## 测试

运行全部自动化测试：

```bash
python3 -m unittest discover tests
```

当前测试覆盖协议编解码、半包、连续消息、非法 Unicode 清理、双客户端群聊、重复昵称、未注册聊天和异常断开。

## 日志

服务端日志同时输出至终端和 `logs/chat.log`。日志文件是运行产物，已由 `.gitignore` 排除。

## 后续方向

后续可在现有消息格式和服务端业务层上增加多房间、私聊、身份认证、持久化以及 WebSocket 网关，以供 Vue 前端接入。
