import asyncio
import unittest

from chat.client import ChatClient
from chat.message import create_message
from chat.peer import PeerNode
from chat.server import ChatServer


async def wait_until(predicate, timeout=1):
    async def condition():
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(condition(), timeout=timeout)


class TestPeerNode(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.nodes = []

    async def asyncTearDown(self):
        for node in self.nodes:
            await node.close()

    async def create_node(self, received, failures):
        async def on_private(message, address):
            received.append((message, address))

        async def on_failed(message):
            failures.append(message)

        node = PeerNode(
            on_private,
            on_failed,
            host="127.0.0.1",
            port=0,
            ack_timeout=0.03,
            max_retries=1,
        )
        self.nodes.append(node)
        await node.start()
        return node

    async def test_udp_private_message_is_received_and_acknowledged(self):
        received_a, failures_a = [], []
        received_b, failures_b = [], []
        peer_a = await self.create_node(received_a, failures_a)
        peer_b = await self.create_node(received_b, failures_b)

        message_id = await peer_a.send_private(
            "A",
            "B",
            "hello",
            peer_b.address,
        )
        await wait_until(lambda: len(received_b) == 1)
        await wait_until(lambda: message_id not in peer_a.pending)

        self.assertEqual(received_b[0][0]["from"], "A")
        self.assertEqual(received_b[0][0]["content"], "hello")
        self.assertEqual(failures_a, [])
        self.assertEqual(failures_b, [])

    async def test_udp_delivery_failure_after_ack_timeouts(self):
        received, failures = [], []
        peer = await self.create_node(received, failures)

        # 端口未监听，因此不会返回 ACK；初次发送后只重试一次。
        message_id = await peer.send_private(
            "A",
            "B",
            "will fail",
            ("127.0.0.1", 59999),
        )
        await wait_until(lambda: len(failures) == 1, timeout=0.5)

        self.assertNotIn(message_id, peer.pending)
        self.assertEqual(failures[0]["to"], "B")
        self.assertEqual(received, [])


class TestTcpDiscoveryAndP2PPrivateMessage(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ChatServer(host="127.0.0.1", port=0)
        self.async_server = await asyncio.start_server(
            self.server.handle_client,
            self.server.host,
            self.server.port,
        )
        self.port = self.async_server.sockets[0].getsockname()[1]
        self.server_task = asyncio.create_task(self.async_server.serve_forever())
        self.clients = []
        self.receive_tasks = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        for task in self.receive_tasks:
            task.cancel()
        await asyncio.gather(*self.receive_tasks, return_exceptions=True)

        self.async_server.close()
        await self.async_server.wait_closed()
        self.server_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.server_task

    async def create_client(self):
        client = ChatClient(
            host="127.0.0.1",
            port=self.port,
            udp_host="127.0.0.1",
            udp_port=0,
            udp_ack_timeout=0.03,
            udp_max_retries=1,
        )
        await client.connect()
        self.clients.append(client)
        self.receive_tasks.append(asyncio.create_task(client.receive_loop()))
        return client

    async def register(self, client, nickname):
        await client.send(create_message("nick", {"name": nickname}))
        await wait_until(lambda: nickname in self.server.users)

    async def test_pmsg_queries_tcp_but_delivers_only_by_udp(self):
        client_a = await self.create_client()
        client_b = await self.create_client()
        client_c = await self.create_client()
        await self.register(client_a, "A")
        await self.register(client_b, "B")
        await self.register(client_c, "C")

        message_id = await client_a.send_peer_message(
            {"target": "B", "content": "hello"}
        )
        self.assertIsNotNone(message_id)
        await wait_until(
            lambda: any(
                message.get("direction") == "incoming"
                and message.get("content") == "hello"
                for message in client_b.local_history
            )
        )
        await wait_until(lambda: message_id not in client_a.peer.pending)

        self.assertEqual(client_c.local_history, [])
        self.assertEqual(client_b.local_history[-1]["from"], "A")
        self.assertEqual(self.server.users["B"].udp_address[0], "127.0.0.1")
