"""Tests for the GLM-first cascade in call_claude().

Verifies that GLM (BigModel) is tried first when GLM_API_KEY is set, and that
the Anthropic/Kimi fallbacks are NOT reached on a successful GLM call. Uses
monkeypatch on httpx.AsyncClient (imported inside call_claude) to avoid real
network calls.
"""
import asyncio
import os
from types import SimpleNamespace

import pytest


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def call_claude_fn(monkeypatch):
    """Import call_claude fresh and force-reimport httpx inside it via env.

    call_claude does `import httpx` inside the function body, so we can't
    monkeypatch the module symbol directly. Instead we inject a fake httpx
    module into sys.modules before the call, capturing which providers were hit.
    """
    import sys

    calls = {"providers_hit": []}

    class _FakeResponse:
        def __init__(self, payload, status=200):
            self._payload = payload
            self.status_code = status
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")
        def json(self):
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, **kw):
            # Record which provider endpoint was hit.
            if "open.bigmodel.cn" in url:
                calls["providers_hit"].append("glm")
                # Echo a choices-style payload.
                return _FakeResponse({"choices": [{"message": {"content": "GLM-ответ"}}]})
            if "api.anthropic.com" in url:
                calls["providers_hit"].append("anthropic")
                return _FakeResponse({"content": [{"text": "Claude-ответ"}]})
            if "api.cloudflare.com" in url:
                calls["providers_hit"].append("kimi")
                return _FakeResponse({"result": {"response": "Kimi-ответ"}})
            calls["providers_hit"].append("unknown:" + url)
            return _FakeResponse({}, status=500)

    import types
    fake_httpx = types.SimpleNamespace(AsyncClient=_FakeAsyncClient)
    # Force the inner `import httpx` to pick up our fake.
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    # Import after setting sys.modules so the function picks it up at call time.
    from routes.ai_claude_agent import call_claude
    return call_claude, calls


def test_glm_is_tried_first_when_key_set(call_claude_fn, monkeypatch):
    """With GLM_API_KEY set, call_claude hits GLM and returns its answer; no fallback."""
    call_claude, calls = call_claude_fn
    monkeypatch.setenv("GLM_API_KEY", "test-glm-key")
    monkeypatch.setenv("GLM_MODEL", "glm-4.5-flash")
    # Also set fallback keys to prove they're NOT used.
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-anthropic")
    monkeypatch.setenv("CF_API_TOKEN", "test-cf")
    monkeypatch.setenv("CF_ACCOUNT_ID", "test-cf-id")

    result = _run(call_claude("test prompt"))
    assert result == "GLM-ответ"
    assert calls["providers_hit"] == ["glm"], f"expected only GLM, got {calls['providers_hit']}"


def test_falls_back_to_anthropic_when_glm_fails(call_claude_fn, monkeypatch):
    """If GLM raises, the cascade should continue to the next provider."""
    import sys
    call_claude, calls = call_claude_fn
    monkeypatch.setenv("GLM_API_KEY", "test-glm-key")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-anthropic")

    # Make GLM endpoint fail by patching the fake client's post for bigmodel.
    fake_httpx = sys.modules["httpx"]

    original_post = fake_httpx.AsyncClient.post

    class _FailingClient(fake_httpx.AsyncClient):
        async def post(self, url, **kw):
            if "open.bigmodel.cn" in url:
                calls["providers_hit"].append("glm-failed")
                raise RuntimeError("GLM down")
            return await original_post(self, url, **kw)

    fake_httpx.AsyncClient = _FailingClient

    result = _run(call_claude("test prompt"))
    assert result == "Claude-ответ"
    assert "glm-failed" in calls["providers_hit"]
    assert "anthropic" in calls["providers_hit"]


def test_no_keys_returns_500(call_claude_fn, monkeypatch):
    """With no provider keys configured, call_claude raises HTTPException 500."""
    from fastapi import HTTPException
    call_claude, calls = call_claude_fn
    # Clear all AI keys.
    for k in ("GLM_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY",
              "CF_API_TOKEN", "CLOUDFLARE_API_TOKEN", "CF_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(HTTPException) as exc_info:
        _run(call_claude("test prompt"))
    assert exc_info.value.status_code == 500
    assert calls["providers_hit"] == [], "no provider should have been hit"
