"""Tests for chat Redis helpers: ws-ticket (atomic GETDEL) + rate limit."""
import pytest

from services.chat_redis import issue_ws_ticket, consume_ws_ticket, allow_message


class FakeRedis:
    """In-memory fake of the subset of redis.Redis we use: setex/getdel/incr/expire."""
    def __init__(self):
        self._store = {}
        self._ttls = {}
    def setex(self, key, ttl, val):
        self._store[key] = val
        self._ttls[key] = ttl
    def getdel(self, key):
        return self._store.pop(key, None)
    def incr(self, key):
        self._store[key] = int(self._store.get(key, 0)) + 1
        return self._store[key]
    def expire(self, key, ttl):
        self._ttls[key] = ttl


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    import services.chat_redis as mod
    monkeypatch.setattr(mod, "_get_redis", lambda: fake)
    return fake


def test_ws_ticket_roundtrip(fake_redis):
    ticket = issue_ws_ticket(user_id=7)
    assert consume_ws_ticket(ticket) == "7"
    # одноразовый — повторное потребление возвращает None
    assert consume_ws_ticket(ticket) is None


def test_consume_unknown_ticket_returns_none(fake_redis):
    assert consume_ws_ticket("bogus") is None


def test_rate_limit_allows_under_cap(fake_redis):
    assert all(allow_message(7) for _ in range(20))


def test_rate_limit_blocks_above_cap(fake_redis):
    for _ in range(20):
        allow_message(7)
    assert allow_message(7) is False


def test_rate_limit_per_user(fake_redis):
    for _ in range(20):
        allow_message(7)
    # другой юзер имеет свой счётчик
    assert allow_message(8) is True
