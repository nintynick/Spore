"""Tests for gossip protocol — message encoding, server communication."""

import asyncio
import json
from test.conftest import make_record

import pytest

from spore.gossip import (
    GossipServer,
    MessageType,
    encode_message,
    read_message,
)


class TestMessageEncoding:
    def test_encode_decode_roundtrip(self):
        payload = {"key": "value", "number": 42}
        encoded = encode_message("test_type", payload)

        async def _decode():
            reader = asyncio.StreamReader()
            reader.feed_data(encoded)
            return await read_message(reader)

        msg = asyncio.run(_decode())
        assert msg["type"] == "test_type"
        assert msg["payload"]["key"] == "value"
        assert msg["payload"]["number"] == 42

    def test_encode_experiment_record(self, keypair):
        record = make_record(keypair)
        payload = json.loads(record.to_json())
        encoded = encode_message(MessageType.EXPERIMENT, payload)
        assert len(encoded) > 0

    def test_encode_sync_request(self):
        encoded = encode_message(MessageType.SYNC_REQUEST, {"since": 1000})
        assert len(encoded) > 0


class TestGossipServer:
    @pytest.fixture
    def event_loop_policy(self):
        return asyncio.DefaultEventLoopPolicy()

    @pytest.mark.asyncio
    async def test_server_starts_and_stops(self):
        server = GossipServer(host="127.0.0.1", port=0)
        await server.start()
        assert server._server is not None
        await server.stop()

    @pytest.mark.asyncio
    async def test_peer_connection(self):
        received = []

        def on_experiment(record):
            received.append(record)

        server = GossipServer(host="127.0.0.1", port=17470, on_experiment=on_experiment)
        await server.start()

        client = GossipServer(host="127.0.0.1", port=17471)
        await client.start()

        connected = await client.connect_to_peer("127.0.0.1", 17470)
        assert connected

        await asyncio.sleep(0.1)

        await server.stop()
        await client.stop()

    @pytest.mark.asyncio
    async def test_broadcast_and_receive(self, keypair):
        received = []

        def on_experiment(record):
            received.append(record)

        server = GossipServer(host="127.0.0.1", port=17472, on_experiment=on_experiment)
        await server.start()

        client = GossipServer(host="127.0.0.1", port=17473)
        await client.start()
        await client.connect_to_peer("127.0.0.1", 17472)
        await asyncio.sleep(0.1)

        # Broadcast an experiment
        record = make_record(keypair, val_bpb=0.95, description="test broadcast")
        await client.broadcast_experiment(record)
        await asyncio.sleep(0.2)

        assert len(received) == 1
        assert received[0].val_bpb == 0.95
        assert received[0].description == "test broadcast"

        await server.stop()
        await client.stop()

    @pytest.mark.asyncio
    async def test_dedup_prevents_rebroadcast(self, keypair):
        received = []

        def on_experiment(record):
            received.append(record)

        server = GossipServer(host="127.0.0.1", port=17474, on_experiment=on_experiment)
        await server.start()

        client = GossipServer(host="127.0.0.1", port=17475)
        await client.start()
        await client.connect_to_peer("127.0.0.1", 17474)
        await asyncio.sleep(0.1)

        # Broadcast same record twice
        record = make_record(keypair, description="dedup test")
        await client.broadcast_experiment(record)
        await client.broadcast_experiment(record)  # Should be deduped
        await asyncio.sleep(0.2)

        # Server should only receive once
        assert len(received) == 1

        await server.stop()
        await client.stop()

    @pytest.mark.asyncio
    async def test_invalid_signature_dropped(self, keypair, second_keypair):
        received = []

        def on_experiment(record):
            received.append(record)

        server = GossipServer(host="127.0.0.1", port=17476, on_experiment=on_experiment)
        await server.start()

        client = GossipServer(host="127.0.0.1", port=17477)
        await client.start()
        await client.connect_to_peer("127.0.0.1", 17476)
        await asyncio.sleep(0.1)

        # Create a record and tamper with it
        record = make_record(keypair, description="tampered")
        record.description = "changed after signing"
        # Don't re-sign — CID will be wrong

        # Manually send it (bypass client dedup by giving it a fresh CID)
        msg = encode_message(MessageType.EXPERIMENT, json.loads(record.to_json()))
        for _, (_, writer) in client.peers.items():
            writer.write(msg)
            await writer.drain()

        await asyncio.sleep(0.2)

        # Server should drop it (invalid CID)
        assert len(received) == 0

        await server.stop()
        await client.stop()

    @pytest.mark.asyncio
    async def test_sync_request_handler(self, keypair):
        """Test that sync_request returns experiments from the handler."""
        sync_records = [
            make_record(keypair, val_bpb=0.95, description="sync exp 1"),
            make_record(keypair, val_bpb=0.90, description="sync exp 2"),
        ]
        received = []

        def on_sync_request(since: int):
            return sync_records

        def on_experiment(record):
            received.append(record)

        server = GossipServer(
            host="127.0.0.1",
            port=17478,
            on_experiment=lambda r: None,
            on_sync_request=on_sync_request,
        )
        await server.start()

        client = GossipServer(
            host="127.0.0.1",
            port=17479,
            on_experiment=on_experiment,
        )
        await client.start()
        await client.connect_to_peer("127.0.0.1", 17478)
        await asyncio.sleep(0.1)

        # Request sync
        await client.request_sync("127.0.0.1:17478", since_timestamp=0)
        await asyncio.sleep(0.3)

        assert len(received) == 2

        await server.stop()
        await client.stop()
