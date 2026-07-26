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
from personal_knowledge.services.api_server import Handler, SESSION_WRITE_ROUTES

FAKE_ORIGIN = "http://evil.example.com"
FAKE_TOKEN = "fake-confirmation-token-should-never-appear-9f3c1a"
FAKE_HMAC = "fake-hmac-deadbeefcafebabe-should-never-appear"
FAKE_PATH_HINT = "C:\\Users\\someone\\secret-path\\credentials.json"


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


# --- Task 2: session 写路由 Origin gate 必须先于 delegation -----------------


def test_cross_origin_mutation_never_delegates_and_never_leaks(live_server, monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_orchestration_rest_contract(operation, params, *, service=None):
        calls.append((operation, params))
        return {"ok": True, "data": {}}

    monkeypatch.setattr(api_server, "orchestration_rest_contract", fake_orchestration_rest_contract)

    for route in SESSION_WRITE_ROUTES:
        resp = _request(
            live_server,
            "POST",
            route,
            origin=FAKE_ORIGIN,
            body={
                "confirmation_token": FAKE_TOKEN,
                "hmac": FAKE_HMAC,
                "path_hint": FAKE_PATH_HINT,
                "preview": {"operation": route.rsplit("/", 1)[-1].replace("-", "_")},
            },
        )
        assert resp["status"] in (401, 403), f"{route} did not reject cross-origin mutation"
        assert "Access-Control-Allow-Origin" not in resp["headers"]
        body_text = resp["body"].decode("utf-8")
        assert FAKE_ORIGIN not in body_text
        assert FAKE_TOKEN not in body_text
        assert FAKE_HMAC not in body_text
        assert FAKE_PATH_HINT not in body_text
        payload = json.loads(resp["body"])
        assert payload["ok"] is False
        assert payload["error"]["code"] == "origin_not_allowed"

    assert calls == [], "orchestration_rest_contract must never be invoked for rejected cross-origin mutation"


def test_same_origin_mutation_still_reaches_orchestration(live_server, monkeypatch):
    calls: list[str] = []

    def fake(operation, params, *, service=None):
        calls.append(operation)
        return {"ok": True, "data": {}}

    monkeypatch.setattr(api_server, "orchestration_rest_contract", fake)
    resp = _request(
        live_server, "POST", "/agent/session/prepare",
        origin=_same_origin_header(live_server), body={"goal": "local validation"},
    )
    assert resp["status"] == 200
    assert calls == ["session.prepare"]


def test_no_origin_mutation_still_reaches_orchestration(live_server, monkeypatch):
    calls: list[str] = []

    def fake(operation, params, *, service=None):
        calls.append(operation)
        return {"ok": True, "data": {}}

    monkeypatch.setattr(api_server, "orchestration_rest_contract", fake)
    resp = _request(live_server, "POST", "/agent/session/prepare", body={"goal": "local validation"})
    assert resp["status"] == 200
    assert calls == ["session.prepare"]


def test_dev_origin_mutation_still_reaches_orchestration(live_server, monkeypatch):
    calls: list[str] = []

    def fake(operation, params, *, service=None):
        calls.append(operation)
        return {"ok": True, "data": {}}

    monkeypatch.setattr(api_server, "orchestration_rest_contract", fake)
    resp = _request(
        live_server, "POST", "/agent/session/prepare",
        origin="http://127.0.0.1:5173", body={"goal": "local validation"},
    )
    assert resp["status"] == 200
    assert calls == ["session.prepare"]
    assert resp["headers"].get("Access-Control-Allow-Origin") == "http://127.0.0.1:5173"


# --- Task 3: 静态 Cockpit 与 transport 错误的安全公开信息 --------------------


def test_missing_cockpit_asset_returns_safe_error_without_path_echo(live_server, monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(api_server, "COCKPIT_DIST", dist)

    resp = _request(live_server, "GET", "/app/does-not-exist-1234.js")
    assert resp["status"] == 404
    payload = json.loads(resp["body"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "cockpit_asset_not_found"
    assert "does-not-exist-1234.js" not in resp["body"].decode("utf-8")


def test_cockpit_not_built_returns_safe_error(live_server, monkeypatch, tmp_path):
    monkeypatch.setattr(api_server, "COCKPIT_DIST", tmp_path / "missing-dist")
    resp = _request(live_server, "GET", "/app/anything.js")
    assert resp["status"] == 404
    payload = json.loads(resp["body"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "cockpit_not_built"


def test_internal_error_never_echoes_exception_text(live_server, monkeypatch):
    def boom_stats():
        raise RuntimeError(f"leak-check secret={FAKE_TOKEN} path={FAKE_PATH_HINT}")

    monkeypatch.setattr(api_server.backend, "stats", boom_stats)
    resp = _request(live_server, "GET", "/stats")
    assert resp["status"] == 500
    body_text = resp["body"].decode("utf-8")
    assert FAKE_TOKEN not in body_text
    assert FAKE_PATH_HINT not in body_text
    payload = json.loads(resp["body"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "internal_error"


def test_safe_error_codes_are_allowlisted_and_static():
    # code 只能来自模块内固定字面量,message 与 code 一一对应且不含动态内容
    for code, message in api_server._SAFE_ERRORS.items():
        body, _status = api_server._safe_error(code, 400)
        payload = json.loads(body)
        assert payload == {"ok": False, "error": {"code": code, "message": message}}
