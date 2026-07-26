"""999.5 单人评审台路由契约测试(/ui/review + /ui/review/labels)。

覆盖:
- POST /ui/review/labels 的 Origin gate 先于 body 解析:跨源请求 403,
  零委派、零文件写入,响应不回显 Origin/payload。
- 合法 payload → 200,labels 落在(monkeypatch 后的)private_evals 临时目录,
  文件为 append-only 新文件且内容含判定。
- 非法判定值(gold/judge)→ 400,且不产生任何文件。
- GET /ui/review 返回 text/html 且 Cache-Control: no-store(页面含私有评审数据)。
- 页面装配异常 → 固定安全错误 review_console_error,不回显异常文本/路径。

全部使用合成数据:CANDIDATE_SUITE / JUDGE_PACKET / PRIVATE_EVALS_DIR 均
monkeypatch 到 tmp_path,绝不读取真实 private_evals。
测试基座与 test_cockpit_transport_security.py 一致:真实 ThreadingHTTPServer。
"""

from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

import personal_knowledge.services.api_server as api_server
import personal_knowledge.services.eval_review as eval_review
from personal_knowledge.services.api_server import Handler

FAKE_ORIGIN = "http://evil.example.com"
FAKE_PATH_HINT = "C:\\Users\\someone\\secret-path\\private_evals\\leak.json"


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


@pytest.fixture()
def isolated_evals(monkeypatch, tmp_path):
    """把评审台的私有数据面全部隔离到 tmp:不读真实 private_evals,不写真实目录。"""
    private_dir = tmp_path / "private_evals"
    monkeypatch.setattr(eval_review, "PRIVATE_EVALS_DIR", private_dir)
    # 缺失文件 → 走空数据分支,页面仍可装配
    monkeypatch.setattr(eval_review, "CANDIDATE_SUITE", tmp_path / "missing_suite.jsonl")
    monkeypatch.setattr(eval_review, "JUDGE_PACKET", tmp_path / "missing_packet.json")
    return private_dir


def _request(server, method, path, *, origin=None, body=None, raw_body=None):
    host, port = server.server_address[0], server.server_address[1]
    conn = http.client.HTTPConnection(host, port, timeout=5)
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    payload = raw_body
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


def _written_files(private_dir):
    return sorted(private_dir.glob("*")) if private_dir.exists() else []


# --- POST /ui/review/labels: Origin gate 先于解析与写入 ----------------------


def test_cross_origin_labels_rejected_without_any_write(live_server, monkeypatch, isolated_evals):
    calls: list[dict] = []
    real_save = eval_review.save_review_labels

    def spy(payload):
        calls.append(payload)
        return real_save(payload)

    monkeypatch.setattr(eval_review, "save_review_labels", spy)

    resp = _request(
        live_server, "POST", "/ui/review/labels",
        origin=FAKE_ORIGIN,
        body={"gold_labels": {"case-1": "对"}, "judge_labels": {}},
    )
    assert resp["status"] == 403
    payload = json.loads(resp["body"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "origin_not_allowed"
    body_text = resp["body"].decode("utf-8")
    assert FAKE_ORIGIN not in body_text
    assert "Access-Control-Allow-Origin" not in resp["headers"]
    assert calls == [], "跨源请求不得触达 save_review_labels"
    assert _written_files(isolated_evals) == [], "跨源请求不得产生任何文件写入"


def test_valid_labels_payload_saved_to_private_evals(live_server, isolated_evals):
    resp = _request(
        live_server, "POST", "/ui/review/labels",
        body={
            "gold_labels": {"case-1": "对", "case-2": "删"},
            "judge_labels": {"case-9": {"hybrid": 2, "raw": 0}},
        },
    )
    assert resp["status"] == 200
    payload = json.loads(resp["body"])
    assert payload["ok"] is True
    assert payload["data"]["gold_labeled"] == 2

    files = _written_files(isolated_evals)
    assert len(files) == 1
    assert files[0].name.startswith("review_labels_")
    assert files[0].name == payload["data"]["saved"]
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert record["gold_labels"] == {"case-1": "对", "case-2": "删"}
    assert record["judge_labels"] == {"case-9": {"hybrid": 2, "raw": 0}}
    assert record["source"] == "ui_review"


def test_invalid_gold_value_returns_400_without_write(live_server, isolated_evals):
    resp = _request(
        live_server, "POST", "/ui/review/labels",
        body={"gold_labels": {"case-1": "也许"}, "judge_labels": {}},
    )
    assert resp["status"] == 400
    payload = json.loads(resp["body"])
    assert payload["ok"] is False
    assert _written_files(isolated_evals) == []


def test_invalid_judge_score_returns_400_without_write(live_server, isolated_evals):
    resp = _request(
        live_server, "POST", "/ui/review/labels",
        body={"gold_labels": {}, "judge_labels": {"case-9": {"hybrid": 7}}},
    )
    assert resp["status"] == 400
    payload = json.loads(resp["body"])
    assert payload["ok"] is False
    assert _written_files(isolated_evals) == []


# --- GET /ui/review: 私有页面传输契约 ---------------------------------------


def test_review_page_html_with_no_store(live_server, isolated_evals):
    resp = _request(live_server, "GET", "/ui/review")
    assert resp["status"] == 200
    assert resp["headers"].get("Content-Type", "").startswith("text/html")
    assert resp["headers"].get("Cache-Control") == "no-store"
    text = resp["body"].decode("utf-8")
    assert "<!DOCTYPE html>" in text
    # 空数据分支:合成环境下页面仍可用,且不含真实评审内容
    assert '"gold": []' in text or '"gold":[]' in text


def test_review_page_build_failure_returns_safe_error(live_server, monkeypatch, isolated_evals):
    def boom():
        raise RuntimeError(f"leak-check path={FAKE_PATH_HINT}")

    monkeypatch.setattr(eval_review, "build_review_page", boom)
    resp = _request(live_server, "GET", "/ui/review")
    assert resp["status"] == 500
    body_text = resp["body"].decode("utf-8")
    assert FAKE_PATH_HINT not in body_text
    assert "RuntimeError" not in body_text
    payload = json.loads(resp["body"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "review_console_error"
