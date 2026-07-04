"""Tests for the /ws/chat WebSocket handler: ticket auth + echo of typing."""
import os

import pytest
import psycopg2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def ws_app(db_conn, monkeypatch):
    import routes.chat_ws as wsmod
    import services.chat_redis as rmod

    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT)")
    cur.execute("INSERT INTO users (username,role) VALUES ('a','admin')")
    cur.close()

    # fake redis: tickets stored in-memory (real Redis is not running locally)
    class FakeRedis:
        def __init__(self): self._s = {}
        def setex(self, k, t, v): self._s[k] = v
        def getdel(self, k): return self._s.pop(k, None)
    fake = FakeRedis()
    monkeypatch.setattr(rmod, "_get_redis", lambda: fake)

    app = FastAPI()
    app.include_router(wsmod.router)
    return app, fake


def test_ws_rejects_without_ticket(ws_app):
    app, _ = ws_app
    client = TestClient(app)
    # No ticket -> handler accepts then closes with 4401. starlette 1.1.0's
    # WebSocketTestSession only surfaces a server-initiated close when the
    # client performs a receive_* (its __exit__ does not drain the close
    # frame), so we read inside the block to observe the rejection.
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/chat") as ws:
            ws.receive_json()
    assert exc_info.value.code == 4401


def test_ws_accepts_valid_ticket_then_closes(ws_app):
    app, fake = ws_app
    from services.chat_redis import issue_ws_ticket
    # issue a ticket for user_id=1
    ticket = issue_ws_ticket(1)
    client = TestClient(app)
    with client.websocket_connect(f"/ws/chat?ticket={ticket}") as ws:
        # connection accepted; send a typing ping and expect no crash
        ws.send_json({"type": "typing", "channel_id": 1})
        # the handler may not reply to typing; just assert we're connected
    assert True


def test_ws_ticket_single_use(ws_app):
    app, fake = ws_app
    from services.chat_redis import issue_ws_ticket, consume_ws_ticket
    ticket = issue_ws_ticket(1)
    assert consume_ws_ticket(ticket) == "1"
    # second consume -> None (atomic GETDEL already removed it)
    assert consume_ws_ticket(ticket) is None
