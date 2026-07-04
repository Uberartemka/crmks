"""Tests for the in-memory CONNECTIONS registry and _fanout."""
import asyncio
import pytest

from services.chat_connections import (
    CONNECTIONS,
    add_connection,
    remove_connection,
    fanout,
)


class FakeWS:
    """Minimal stand-in for starlette WebSocket with send_json/close."""
    def __init__(self):
        self.sent = []
        self.closed = False
    async def send_json(self, payload):
        self.sent.append(payload)
    async def close(self, code=1000):
        self.closed = True


@pytest.fixture(autouse=True)
def _clear_registry():
    CONNECTIONS.clear()
    yield
    CONNECTIONS.clear()


def test_add_and_remove_connection():
    ws = FakeWS()
    add_connection(7, ws)
    assert ws in CONNECTIONS[7]
    remove_connection(7, ws)
    assert 7 not in CONNECTIONS or ws not in CONNECTIONS[7]


def test_multi_tab_same_user():
    ws1, ws2 = FakeWS(), FakeWS()
    add_connection(7, ws1)
    add_connection(7, ws2)
    assert len(CONNECTIONS[7]) == 2


def _run(coro):
    return asyncio.run(coro)


def test_fanout_delivers_to_online_members():
    ws_online = FakeWS()
    add_connection(5, ws_online)
    _run(fanout(channel_id=1, payload={"type": "message"}, members=lambda c: [5, 6]))
    assert ws_online.sent == [{"type": "message"}]


def test_fanout_excludes_author():
    ws_author = FakeWS()
    add_connection(5, ws_author)
    _run(fanout(
        channel_id=1,
        payload={"type": "message"},
        members=lambda c: [5],
        exclude_user=5,
    ))
    assert ws_author.sent == []


def test_fanout_swallows_dead_socket():
    class DeadWS(FakeWS):
        async def send_json(self, payload):
            raise RuntimeError("disconnected")
    add_connection(5, DeadWS())
    _run(fanout(channel_id=1, payload={"type": "x"}, members=lambda c: [5]))
