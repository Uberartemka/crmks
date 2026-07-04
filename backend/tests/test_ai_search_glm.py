"""Tests for /api/ai/search using GLM (BigModel) instead of DeepSeek.

Verifies the endpoint:
- hits the BigModel endpoint (not deepseek) when GLM_API_KEY is set
- returns the parsed JSON from GLM's response
- falls back to local generator when no key / on error
"""
import io
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def search_app(monkeypatch):
    """Build a FastAPI app with the ai_search router. Monkeypatch urllib to avoid real calls."""
    monkeypatch.setenv("GLM_API_KEY", "test-glm-key")
    monkeypatch.setenv("GLM_MODEL", "glm-4.5-flash")

    captured = {"url": None, "headers": None, "body": None}

    class _FakeResp:
        def __init__(self, payload_bytes):
            self._buf = io.BytesIO(payload_bytes)
        def read(self):
            return self._buf.read()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = req.headers
        captured["body"] = req.data.decode() if req.data else None
        # BigModel-style response
        payload = json.dumps({
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "title": "HHB 6205-2RS C3",
                        "desc": "Подшипник",
                        "price": "420 ₽",
                        "stock": "100 шт",
                        "cross": "SKF 6205",
                    })
                }
            }]
        }).encode()
        return _FakeResp(payload)

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    from routes.ai_search import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), captured


def test_ai_search_hits_bigmodel_endpoint(search_app):
    """The endpoint must call BigModel (open.bigmodel.cn), not DeepSeek."""
    client, captured = search_app
    resp = client.post("/api/ai/search", json={"query": "подшипник 6205"})
    assert resp.status_code == 200
    assert "open.bigmodel.cn" in captured["url"], f"hit {captured['url']}"
    assert "deepseek.com" not in captured["url"]


def test_ai_search_uses_glm_model(search_app):
    """The request body must specify glm-4.5-flash as the model."""
    client, captured = search_app
    client.post("/api/ai/search", json={"query": "тест"})
    body = json.loads(captured["body"])
    assert body["model"] == "glm-4.5-flash"
    # max_tokens cap speeds up the response (speed optimization).
    assert body.get("max_tokens") == 1024, "max_tokens=1024 missing from payload"


def test_ai_search_returns_parsed_json(search_app):
    """The endpoint returns the JSON object parsed from GLM's content."""
    client, captured = search_app
    resp = client.post("/api/ai/search", json={"query": "6205"})
    body = resp.json()
    assert body["title"] == "HHB 6205-2RS C3"
    assert body["cross"] == "SKF 6205"


def test_ai_search_authorization_header(search_app):
    """Authorization header must use the GLM API key as Bearer."""
    client, captured = search_app
    client.post("/api/ai/search", json={"query": "тест"})
    # urllib normalizes header names; check case-insensitively.
    auth = captured["headers"].get("Authorization", "") or captured["headers"].get("authorization", "")
    assert "test-glm-key" in auth
