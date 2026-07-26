"""evidence_resolve.get 契约测试(Phase 37:EVID-01)。

覆盖三种 subject_type(personal_state / external_fact / decision)的稳定引用
解析:成功路径的 stable_id/snapshot_id/checksum 三元组闭环、mismatch/expired/
abstain/not_found 的可区分 typed status、单 authority 意外故障隔离为 partial
(而非 500)、结构非法输入的 400、绝不回退到"最新记录"、绝不泄露 sealed value /
异常细节,以及 GET-only + 零 mutation 的物理只读边界。
"""
import json
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import personal_knowledge.services.api_server as api_server
from personal_knowledge.core.project_paths import EXTERNAL_CONTEXT_DB, UNIFIED_DB
from personal_knowledge.intelligence.decision.service import DecisionFeedbackService
from personal_knowledge.intelligence.service import IntelligenceService
from personal_knowledge.services.api_server import ui_rest_contract
from personal_knowledge.services.decision_intelligence_reads import (
    DecisionIntelligenceReadService,
)
from personal_knowledge.services.ui_projection import (
    INTERFACE_SCHEMA_VERSION,
    CockpitProjectionService,
)

# 注入含路径/密钥/Bearer/provider JSON/confirmation-HMAC 字样的异常文本,
# 验证公开 envelope(D-36-06)绝不回显这些片段——只允许 allowlisted safe code/message。
_POISON_MESSAGE = (
    r'path=C:\secret\x key=sk-test-1234567890 auth=Bearer abcdef123 '
    r'provider_body={"provider": "openai", "choices": []} '
    r'confirmation_token=deadbeef1234 hmac=HMAC-SHA256:cafebabe'
)
_POISON_FRAGMENTS = (
    r"C:\secret\x",
    "sk-test-1234567890",
    "Bearer abcdef123",
    '"provider": "openai"',
    "confirmation_token=deadbeef1234",
    "HMAC-SHA256:cafebabe",
    "RuntimeError",
)

_ENVELOPE_TOP_KEYS = {
    "schema_version", "operation", "ok", "generated_at", "snapshot_bindings",
    "freshness", "authorities", "partial", "limitations", "data",
}
_DATA_KEYS = {"status", "reference", "result", "next_actions"}
_REFERENCE_KEYS = {"subject_type", "stable_id", "snapshot_id", "checksum"}
_STATUS_VALUES = {"ok", "mismatch", "expired", "abstain", "not_found", "authority_unavailable"}


def _real_external_fact():
    """从真实 external_delta.get 取一条带完整字段的 fact,用于成功路径断言。"""
    result = CockpitProjectionService().invoke("external_delta.get")
    data = result["data"]
    if not data or not data["facts"]:
        return None, None
    return data["facts"][0], data["snapshot"]["snapshot_id"]


def _real_recommendation():
    """从真实 recommendations.list 取一条,用于 decision 成功路径断言。"""
    result = DecisionFeedbackService(UNIFIED_DB).invoke("recommendations.list", limit=1)
    if not result.get("ok"):
        return None
    items = result["data"].get("items") or []
    if not items:
        return None
    return DecisionFeedbackService(UNIFIED_DB).invoke(
        "recommendations.get", recommendation_id=items[0]["recommendation_id"],
    )["data"]


def _envelope_shape_ok(result, status_subset=_STATUS_VALUES):
    assert result["schema_version"] == INTERFACE_SCHEMA_VERSION
    assert result["operation"] == "evidence_resolve.get"
    assert result["ok"] is True
    assert set(result["data"]) == _DATA_KEYS
    # personal_state 引用额外携带完整 state key(5 字段),故用子集校验
    assert _REFERENCE_KEYS <= set(result["data"]["reference"])
    assert result["data"]["status"] in status_subset
    assert set(result["authorities"]) == {"evidence"}
    assert set(result["authorities"].values()) <= {"ok", "empty", "error"}
    assert isinstance(result["data"]["next_actions"], list)
    assert isinstance(result["limitations"], list)


# --- 结构非法输入:400,不进入任何 resolver 分支 ------------------------------


def test_invalid_input_missing_subject_type():
    result = CockpitProjectionService().invoke("evidence_resolve.get")
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_invalid_input_unknown_subject_type():
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="memory_graph", stable_id="x",
        snapshot_id="y", checksum="z",
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_invalid_input_missing_stable_id_or_snapshot_or_checksum():
    for missing in ("stable_id", "snapshot_id", "checksum"):
        params = {
            "subject_type": "external_fact", "stable_id": "f", "snapshot_id": "s", "checksum": "c",
        }
        params[missing] = ""
        result = CockpitProjectionService().invoke("evidence_resolve.get", **params)
        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_input"


def test_invalid_input_personal_state_missing_state_key():
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="personal_state",
        stable_id="psa_x", snapshot_id="ss_x", checksum="csum_x",
        # 缺 domain/scope/predicate
        assertion_kind="goal", subject="user",
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


# --- external_fact --------------------------------------------------------


def test_external_fact_resolve_ok_roundtrips_real_projection_reference():
    fact, snapshot_id = _real_external_fact()
    if fact is None:
        pytest.skip("当前环境无可用 External fact")
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="external_fact",
        stable_id=fact["fact_id"], snapshot_id=snapshot_id, checksum=fact["fact_checksum"],
    )
    _envelope_shape_ok(result, {"ok"})
    assert result["data"]["status"] == "ok"
    assert result["snapshot_bindings"]["external"] == snapshot_id
    assert result["snapshot_bindings"]["personal"] is None
    payload = result["data"]["result"]
    assert payload["stable_id"] == fact["fact_id"]
    assert payload["snapshot_id"] == snapshot_id
    assert payload["checksum"] == fact["fact_checksum"]
    assert payload["subject"] == fact["subject"]
    assert payload["predicate"] == fact["predicate"]
    # 绝不泄露 raw fact value(与 external_delta.get 同一隐私边界,metadata-only)
    assert "value" not in payload
    serialized = json.dumps(result, ensure_ascii=False, default=str)
    assert '"value"' not in serialized


def test_external_fact_resolve_mismatch_on_stale_checksum():
    fact, snapshot_id = _real_external_fact()
    if fact is None:
        pytest.skip("当前环境无可用 External fact")
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="external_fact",
        stable_id=fact["fact_id"], snapshot_id=snapshot_id, checksum="stale_checksum_deadbeef",
    )
    _envelope_shape_ok(result, {"mismatch"})
    assert result["data"]["status"] == "mismatch"
    assert result["data"]["result"] is None
    # mismatch 绝不回退到"最新记录"——result 必须为 None,不是重新查出的真实 fact
    assert result["partial"] is False


def test_external_fact_resolve_mismatch_on_stale_snapshot_id():
    fact, snapshot_id = _real_external_fact()
    if fact is None:
        pytest.skip("当前环境无可用 External fact")
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="external_fact",
        stable_id=fact["fact_id"], snapshot_id="exs_not_the_active_one",
        checksum=fact["fact_checksum"],
    )
    assert result["data"]["status"] == "mismatch"


def test_external_fact_resolve_unknown_fact_id_is_not_ok():
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="external_fact",
        stable_id="ef_never_existed_0000", snapshot_id="exs_x", checksum="x",
    )
    # 未知 fact_id 在当前 active snapshot manifest 里必然缺席 → not_found/expired 两者之一,
    # 但绝不能是 "ok"(伪造出一条记录)
    assert result["data"]["status"] in {"not_found", "expired"}
    assert result["data"]["result"] is None


# --- decision ---------------------------------------------------------------


def test_decision_resolve_ok_roundtrips_real_recommendation():
    rec = _real_recommendation()
    if rec is None:
        pytest.skip("当前环境无可用 decision recommendation")
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="decision",
        stable_id=rec["recommendation_id"], snapshot_id=rec["snapshot_id"],
        checksum=rec["recommendation_checksum"],
    )
    _envelope_shape_ok(result, {"ok"})
    assert result["data"]["status"] == "ok"
    payload = result["data"]["result"]
    assert payload["stable_id"] == rec["recommendation_id"]
    assert payload["confirmation_state"] == rec["confirmation_state"]
    assert payload["support"] == rec["support"]
    # support[] 已是既有 metadata-only 形状(record_id/checksum/authority_id 等),
    # 不含任意正文/URL/provider 字段
    for entry in payload["support"] or []:
        assert "value" not in entry
        assert "body" not in entry


def test_decision_resolve_mismatch_on_stale_checksum():
    rec = _real_recommendation()
    if rec is None:
        pytest.skip("当前环境无可用 decision recommendation")
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="decision",
        stable_id=rec["recommendation_id"], snapshot_id=rec["snapshot_id"],
        checksum="stale_checksum_deadbeef",
    )
    assert result["data"]["status"] == "mismatch"
    assert result["data"]["result"] is None


def test_decision_resolve_not_found_for_unknown_recommendation_id():
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="decision",
        stable_id="drec_never_existed_0000", snapshot_id="ss_x", checksum="x",
    )
    assert result["data"]["status"] == "not_found"
    assert result["authorities"]["evidence"] == "empty"
    assert result["data"]["result"] is None


def test_decision_resolve_authority_error_isolated_as_partial_not_500(monkeypatch):
    """recommendation_missing 以外的 DecisionServiceError(如链路 checksum 校验失败)
    是真实 authority 完整性问题,必须与"引用只是过期/不匹配"区分,归为 partial
    的 authority_unavailable,而不是让异常穿透或伪装成 mismatch。"""

    def boom(self, operation, **params):
        if operation == "recommendations.get":
            return {
                "ok": False,
                "error": {"code": "recommendation_checksum_mismatch", "detail": "rid"},
            }
        raise AssertionError("unexpected operation")

    monkeypatch.setattr(DecisionFeedbackService, "invoke", boom)
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="decision",
        stable_id="drec_x", snapshot_id="ss_x", checksum="csum_x",
    )
    assert result["ok"] is True
    assert result["partial"] is True
    assert result["authorities"]["evidence"] == "error"
    assert result["data"]["status"] == "authority_unavailable"
    assert result["data"]["result"] is None
    assert any("decision" in item for item in result["limitations"])


def test_decision_resolve_authority_failure_never_leaks_exception_detail(monkeypatch):
    def boom(self, operation, **params):
        raise RuntimeError(_POISON_MESSAGE)

    monkeypatch.setattr(DecisionFeedbackService, "invoke", boom)
    result = CockpitProjectionService().invoke(
        "evidence_resolve.get", subject_type="decision",
        stable_id="drec_x", snapshot_id="ss_x", checksum="csum_x",
    )
    assert result["data"]["status"] == "authority_unavailable"
    serialized = json.dumps(result, ensure_ascii=False, default=str)
    for fragment in _POISON_FRAGMENTS:
        assert fragment not in serialized


# --- personal_state（真实环境可能无已提交 run，全部走受控 monkeypatch）---------


_FAKE_STATE_KEY = {
    "assertion_kind": "goal", "subject": "user",
    "domain": "project", "scope": "s", "predicate": "p",
}
_FAKE_EXPLAIN_DATA = {
    "schema_version": "personal_state_explanation_v1",
    "snapshot_id": "ss_fixture", "snapshot_hash": "hash_fixture",
    "run_id": "psr_fixture", "run_checksum": "runc_fixture",
    "as_of": "2026-01-01T00:00:00Z", "key": _FAKE_STATE_KEY, "state_status": "current",
    "current_assertion_id": "psa_fixture0001", "current_value_checksum": "csum_fixture_abc123",
    "provenance_class": "fact", "confidence": 0.9,
    "formation_path": [], "lifecycle_path": [],
    "evidence": [
        {
            "ref": "ev_fixture0001", "artifact_type": "message", "status": "ok",
            "eligible": True, "source_version": "v1", "serving_role": "primary",
            "expected_version": "v1", "privacy_class": "metadata_only",
            "evidence_checksum": "evc_fixture",
        },
    ],
    "uncertainty": [], "abstained": False, "explanation_checksum": "expc_fixture",
}


def _patch_state_explain(monkeypatch, data=None, ok=True, code=None):
    def guarded(self, operation, **params):
        if operation == "state.explain":
            if ok:
                return {"ok": True, "data": data or _FAKE_EXPLAIN_DATA}
            return {"ok": False, "error": {"code": code, "detail": ""}}
        raise AssertionError(f"unexpected operation {operation}")

    monkeypatch.setattr(IntelligenceService, "invoke", guarded)


def _resolve_personal(**overrides):
    params = {
        "subject_type": "personal_state",
        "stable_id": "psa_fixture0001", "snapshot_id": "ss_fixture", "checksum": "csum_fixture_abc123",
        **_FAKE_STATE_KEY,
    }
    params.update(overrides)
    return CockpitProjectionService().invoke("evidence_resolve.get", **params)


def test_personal_state_resolve_ok_roundtrips_stable_reference(monkeypatch):
    _patch_state_explain(monkeypatch)
    result = _resolve_personal()
    _envelope_shape_ok(result, {"ok"})
    assert result["data"]["status"] == "ok"
    assert result["snapshot_bindings"]["personal"] == "ss_fixture"
    payload = result["data"]["result"]
    assert payload["stable_id"] == "psa_fixture0001"
    assert payload["checksum"] == "csum_fixture_abc123"
    assert payload["key"] == _FAKE_STATE_KEY
    # 只暴露证据元数据(ref/artifact_type/status/eligible/privacy_class),
    # 不含 source_version/expected_version/serving_role/evidence_checksum
    assert set(payload["evidence"][0]) == {"ref", "artifact_type", "status", "eligible", "privacy_class"}
    # 绝不含 sealed assertion 明文值
    serialized = json.dumps(result, ensure_ascii=False, default=str)
    assert '"value"' not in serialized


def test_personal_state_resolve_mismatch_on_changed_assertion_id(monkeypatch):
    _patch_state_explain(monkeypatch, data={**_FAKE_EXPLAIN_DATA, "current_assertion_id": "psa_ROTATED"})
    result = _resolve_personal()
    assert result["data"]["status"] == "mismatch"
    assert result["data"]["result"] is None


def test_personal_state_resolve_mismatch_on_changed_checksum(monkeypatch):
    _patch_state_explain(monkeypatch, data={**_FAKE_EXPLAIN_DATA, "current_value_checksum": "csum_ROTATED"})
    result = _resolve_personal()
    assert result["data"]["status"] == "mismatch"
    assert result["data"]["result"] is None


def test_personal_state_resolve_abstain_when_evidence_ineligible(monkeypatch):
    _patch_state_explain(monkeypatch, data={
        **_FAKE_EXPLAIN_DATA, "abstained": True, "uncertainty": ["evidence_unavailable_or_ineligible"],
    })
    result = _resolve_personal()
    assert result["data"]["status"] == "abstain"
    # abstain 仍返回可用元数据(不是 None),但带 uncertainty/next_actions 说明降级原因
    assert result["data"]["result"] is not None
    assert result["data"]["result"]["uncertainty"] == ["evidence_unavailable_or_ineligible"]
    assert result["data"]["next_actions"]


def test_personal_state_resolve_not_found_when_state_key_missing(monkeypatch):
    _patch_state_explain(monkeypatch, ok=False, code="state_key_missing")
    result = _resolve_personal()
    assert result["data"]["status"] == "not_found"
    assert result["authorities"]["evidence"] == "empty"


@pytest.mark.parametrize("code", ["snapshot_missing", "snapshot_not_validated", "run_missing"])
def test_personal_state_resolve_expired_when_snapshot_binding_stale(monkeypatch, code):
    _patch_state_explain(monkeypatch, ok=False, code=code)
    result = _resolve_personal()
    assert result["data"]["status"] == "expired"
    assert result["data"]["result"] is None


def test_personal_state_resolve_authority_unavailable_never_leaks_exception_detail(monkeypatch):
    def guarded(self, operation, **params):
        raise RuntimeError(_POISON_MESSAGE)

    monkeypatch.setattr(IntelligenceService, "invoke", guarded)
    result = _resolve_personal()
    assert result["ok"] is True
    assert result["partial"] is True
    assert result["data"]["status"] == "authority_unavailable"
    serialized = json.dumps(result, ensure_ascii=False, default=str)
    for fragment in _POISON_FRAGMENTS:
        assert fragment not in serialized


# --- REST adapter / route wiring --------------------------------------------


def test_rest_adapter_parity_for_evidence_resolve():
    fact, snapshot_id = _real_external_fact()
    if fact is None:
        pytest.skip("当前环境无可用 External fact")
    service = CockpitProjectionService()
    params = {
        "subject_type": "external_fact", "stable_id": fact["fact_id"],
        "snapshot_id": snapshot_id, "checksum": fact["fact_checksum"],
    }
    rest = ui_rest_contract("evidence_resolve.get", params, service=service)
    direct = service.invoke("evidence_resolve.get", **params)
    for envelope in (rest, direct):
        envelope.pop("generated_at")
        envelope["freshness"].pop("generated_at")
    assert rest == direct


def test_ui_route_serves_evidence_resolve_and_rejects_post():
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        port = server.server_address[1]
        with opener.open(
            f"http://127.0.0.1:{port}/ui/evidence/resolve"
            f"?subject_type=external_fact&stable_id=x&snapshot_id=y&checksum=z"
        ) as resp:
            body = json.loads(resp.read())
        assert resp.status == 200
        assert body["ok"] is True
        assert body["operation"] == "evidence_resolve.get"
        assert body["schema_version"] == INTERFACE_SCHEMA_VERSION
        # 未知 fact_id → 结构上合法但不可解析(not_found/expired),绝不是 500
        assert body["data"]["status"] in {"not_found", "expired"}

        # GET-only:没有任何 POST /ui/evidence/resolve 路由,POST 必须落到未知路径 404,
        # 不得触达 ui_rest_contract/evidence resolver(零写入路径)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/ui/evidence/resolve", data=b"{}", method="POST",
        )
        try:
            opener.open(req)
            raised = False
        except urllib.error.HTTPError as exc:
            raised = True
            assert exc.code == 404
        assert raised
    finally:
        server.shutdown()
        server.server_close()


# --- 物理只读边界(D-36-01/D-36-02 的既有先例,应用到新 resolver) -----------------


def _table_fingerprint(con, tables):
    return {
        table: con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in tables
    }


def _ro_connect(path):
    con = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


# 只锚定 evidence_resolve.get 实际可能触达的表;不用全库表名扫描,避免与
# 并发运行的 pk-ku extract(持续写 knowledge_units/evidence/cache 等无关表)
# 产生假阳性(见 36-VERIFICATION.md 的既有先例)。
_UNIFIED_RELEVANT_TABLES = (
    "personal_state_runs", "personal_state_assertions", "personal_state_publications",
    "decision_recommendations", "decision_runs", "decision_support_refs",
)


def test_evidence_resolve_is_physically_read_only(monkeypatch):
    unified_con = _ro_connect(UNIFIED_DB)
    external_con = _ro_connect(EXTERNAL_CONTEXT_DB)
    try:
        before_unified = _table_fingerprint(unified_con, _UNIFIED_RELEVANT_TABLES)
        before_external = _table_fingerprint(
            external_con, ("external_facts", "external_fact_support", "external_observations"),
        )
    finally:
        unified_con.close()
        external_con.close()

    service = CockpitProjectionService()
    fact, snapshot_id = _real_external_fact()
    if fact is not None:
        service.invoke(
            "evidence_resolve.get", subject_type="external_fact",
            stable_id=fact["fact_id"], snapshot_id=snapshot_id, checksum=fact["fact_checksum"],
        )
    rec = _real_recommendation()
    if rec is not None:
        service.invoke(
            "evidence_resolve.get", subject_type="decision",
            stable_id=rec["recommendation_id"], snapshot_id=rec["snapshot_id"],
            checksum=rec["recommendation_checksum"],
        )
    _patch_state_explain(monkeypatch)
    service.invoke("evidence_resolve.get", subject_type="personal_state", **{
        "stable_id": "psa_fixture0001", "snapshot_id": "ss_fixture",
        "checksum": "csum_fixture_abc123", **_FAKE_STATE_KEY,
    })

    unified_con = _ro_connect(UNIFIED_DB)
    external_con = _ro_connect(EXTERNAL_CONTEXT_DB)
    try:
        after_unified = _table_fingerprint(unified_con, _UNIFIED_RELEVANT_TABLES)
        after_external = _table_fingerprint(
            external_con, ("external_facts", "external_fact_support", "external_observations"),
        )
    finally:
        unified_con.close()
        external_con.close()

    assert before_unified == after_unified
    assert before_external == after_external


def test_evidence_resolve_readonly_connection_rejects_write():
    """CockpitProjectionService._external_fact_source_ids 等新读取路径复用既有
    mode=ro+query_only=ON 连接方式;在同样打开方式下写语句必须被 SQLite 拒绝
    (D-36-02 物理只读边界,应用到本 plan 新增的 External 一次性聚合查询)。"""
    con = sqlite3.connect(f"file:{EXTERNAL_CONTEXT_DB.resolve().as_posix()}?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only=ON")
        with pytest.raises(sqlite3.OperationalError):
            con.execute("CREATE TABLE evidence_resolve_write_probe_37_01 (id INTEGER)")
    finally:
        con.close()
