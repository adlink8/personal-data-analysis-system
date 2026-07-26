"""Phase 36-01: REST `/app` 同源 transport 与跨 Origin mutation 防护契约测试。

覆盖 D-36-03/D-36-06:
- 源码不存在无条件 wildcard CORS。
- 生产同源(Origin == 请求自身 Host)与无 Origin(既有本地非浏览器调用)放行,不下发 CORS header。
- 显式开发 Origin allowlist 获得专属(非 wildcard)CORS 响应头;未知 Origin 得不到 ACAO。
- 未知 Origin 的预检(OPTIONS)返回安全拒绝,不回显 Origin。

用真实 `ThreadingHTTPServer` 起本地临时端口测试,贴近浏览器实际 fetch 行为。
"""

from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import personal_knowledge.services.api_server as api_server
from personal_knowledge.services.api_server import Handler

FAKE_ORIGIN = "http://evil.example.com"


@pytest.fixture()
def live_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(server, method, path, *, origin=None, body=None):
    host, port = server.server_address[0], server.server_address[1]
    conn = http.client.HTTPConnection(host, port, timeout=5)
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    payload = None
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        return {"status": resp.status, "headers": dict(resp.getheaders()), "body": data}
    finally:
        conn.close()


def _same_origin_header(server) -> str:
    host, port = server.server_address[0], server.server_address[1]
    return f"http://{host}:{port}"


# --- Task 1: 无条件 wildcard CORS 已移除 ------------------------------------


def test_no_wildcard_cors_in_source():
    source = Path(api_server.__file__).read_text(encoding="utf-8")
    assert 'Access-Control-Allow-Origin", "*"' not in source


def test_send_only_emits_cors_header_conditionally():
    import inspect

    source = inspect.getsource(api_server.Handler._send)
    assert '"*"' not in source


# --- Task 1: same-origin / no-origin / dev-origin / unknown-origin ---------


def test_no_origin_request_gets_no_cors_header(live_server):
    resp = _request(live_server, "GET", "/health")
    assert resp["status"] == 200
    assert "Access-Control-Allow-Origin" not in resp["headers"]


def test_same_origin_request_gets_no_cors_header(live_server):
    resp = _request(live_server, "GET", "/health", origin=_same_origin_header(live_server))
    assert resp["status"] == 200
    assert "Access-Control-Allow-Origin" not in resp["headers"]


def test_dev_origin_gets_scoped_cors_header(live_server):
    resp = _request(live_server, "GET", "/health", origin="http://127.0.0.1:5173")
    assert resp["status"] == 200
    assert resp["headers"].get("Access-Control-Allow-Origin") == "http://127.0.0.1:5173"
    assert resp["headers"].get("Vary") == "Origin"


def test_dev_origin_allowlist_extensible_via_env(live_server, monkeypatch):
    monkeypatch.setenv("PK_COCKPIT_DEV_ORIGINS", "http://localhost:4000")
    resp = _request(live_server, "GET", "/health", origin="http://localhost:4000")
    assert resp["headers"].get("Access-Control-Allow-Origin") == "http://localhost:4000"


def test_unknown_origin_gets_no_cors_header(live_server):
    resp = _request(live_server, "GET", "/health", origin=FAKE_ORIGIN)
    assert resp["status"] == 200  # 只读 GET 仍照常响应,只是不下发 ACAO
    assert "Access-Control-Allow-Origin" not in resp["headers"]
    assert FAKE_ORIGIN.encode() not in resp["body"]


def test_options_preflight_dev_origin_gets_headers(live_server):
    resp = _request(live_server, "OPTIONS", "/agent/session/prepare", origin="http://127.0.0.1:5173")
    assert resp["status"] == 204
    assert resp["headers"].get("Access-Control-Allow-Origin") == "http://127.0.0.1:5173"
    assert "Access-Control-Allow-Methods" in resp["headers"]
    assert "Access-Control-Allow-Headers" in resp["headers"]


def test_options_preflight_unknown_origin_rejected_safely(live_server):
    resp = _request(live_server, "OPTIONS", "/agent/session/prepare", origin=FAKE_ORIGIN)
    assert resp["status"] == 403
    assert "Access-Control-Allow-Origin" not in resp["headers"]
    assert FAKE_ORIGIN.encode() not in resp["body"]
    payload = json.loads(resp["body"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "origin_not_allowed"


def test_options_preflight_no_origin_still_allowed(live_server):
    # 既有本地非浏览器调用(无 Origin)保持兼容
    resp = _request(live_server, "OPTIONS", "/agent/session/prepare")
    assert resp["status"] == 204
    assert "Access-Control-Allow-Origin" not in resp["headers"]
