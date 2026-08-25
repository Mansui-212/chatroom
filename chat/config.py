"""聊天室的运行配置。"""

HOST = "127.0.0.1"
PORT = 8765

MAX_MESSAGE_SIZE = 1024 * 1024
ENCODING = "utf-8"
HISTORY_LIMIT = 100

# UDP 默认使用系统分配的可用端口，便于同一台主机运行多个客户端。
UDP_HOST = "0.0.0.0"
UDP_PORT = 0
UDP_ACK_TIMEOUT = 3.0
UDP_MAX_RETRIES = 3
MAX_UDP_MESSAGE_SIZE = 64 * 1024

# 没有身份认证前，管理员名单通过部署配置显式指定，默认不授予任何人管理员权限。
ADMIN_NICKNAMES: frozenset[str] = frozenset()
