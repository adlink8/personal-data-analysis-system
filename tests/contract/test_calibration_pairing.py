from __future__ import annotations

from pathlib import Path

import pytest

from personal_knowledge.intelligence.analysis.providers import ReplayProvider
from personal_knowledge.intelligence.calibration.paired import (
    CalibrationPairError, build_paired_requests, execute_frozen_arm, freeze_arm_assignments,
)
from tests.integration.test_calibration_authority import setup_protocol


def test_arms_have_exact_parity_except_personal_context(tmp_path: Path) -> None:
    env,db,protocol=setup_protocol(tmp_path); from personal_knowledge.intelligence.calibration.protocols import freeze_protocol
    freeze_protocol(db,env["pilot"],protocol,write=True)
    import sqlite3
    con=sqlite3.connect(db); member=con.execute("SELECT member_id FROM calibration_cohort_members").fetchone()[0]; con.close()
    arms=build_paired_requests(db,protocol.protocol_id,member_id=member,
        external_context={"python":"3.14.2","node":"24.13.0"},personal_context={"delivery_method":"evidence-gated"})
    p={k:v for k,v in arms["personalized"].items() if k not in {"personal_context","blind_label","request_checksum"}}
    g={k:v for k,v in arms["generic"].items() if k not in {"personal_context","blind_label","request_checksum"}}
    assert p==g and arms["generic"]["personal_context"] is None
    ids=freeze_arm_assignments(db,protocol.protocol_id,member_id=member,arms=arms,created_at="2026-07-18T13:01:00Z")
    for kind in ("personalized","generic"):
        response={"protocol_checksum":protocol.payload_checksum,"blind_label":arms[kind]["blind_label"],
                  "status":"candidate","recommendation":"validate then adopt","rationale":["bounded"],
                  "limitations":["single case"],"confidence":.6}
        provider=ReplayProvider(response)
        receipt=execute_frozen_arm(db,arm_id=ids[kind],provider=provider)
        assert receipt["receipt"]["cost_amount"]==0
        assert execute_frozen_arm(db,arm_id=ids[kind],provider=provider)["existing"]
        assert provider.calls==1


def test_generic_personal_leakage_and_generation_drift_fail_closed(tmp_path: Path) -> None:
    env,db,protocol=setup_protocol(tmp_path); from personal_knowledge.intelligence.calibration.protocols import freeze_protocol
    freeze_protocol(db,env["pilot"],protocol,write=True)
    import sqlite3
    con=sqlite3.connect(db); member=con.execute("SELECT member_id FROM calibration_cohort_members").fetchone()[0]; con.close()
    with pytest.raises(CalibrationPairError,match="generic_personal_leakage"):
        build_paired_requests(db,protocol.protocol_id,member_id=member,
            external_context={"note":"personal_history should not appear"},personal_context={"x":1})
    arms=build_paired_requests(db,protocol.protocol_id,member_id=member,external_context={"x":1},personal_context={"y":2})
    arms["generic"]["generation"]={**arms["generic"]["generation"],"max_output_tokens":1}
    with pytest.raises(CalibrationPairError,match="arm_parity_invalid"):
        freeze_arm_assignments(db,protocol.protocol_id,member_id=member,arms=arms,created_at="2026-07-18T13:01:00Z")


def test_replay_provider_cannot_bypass_response_schema(tmp_path: Path) -> None:
    env,db,protocol=setup_protocol(tmp_path); from personal_knowledge.intelligence.calibration.protocols import freeze_protocol
    freeze_protocol(db,env["pilot"],protocol,write=True)
    import sqlite3
    con=sqlite3.connect(db); member=con.execute("SELECT member_id FROM calibration_cohort_members").fetchone()[0]; con.close()
    arms=build_paired_requests(db,protocol.protocol_id,member_id=member,external_context={"x":1},personal_context={"y":2})
    ids=freeze_arm_assignments(db,protocol.protocol_id,member_id=member,arms=arms,created_at="2026-07-18T13:01:00Z")
    bad={"protocol_checksum":protocol.payload_checksum,"blind_label":"arm_a","status":"candidate"}
    with pytest.raises(CalibrationPairError,match="arm_response_schema_invalid"):
        execute_frozen_arm(db,arm_id=ids["generic"],provider=ReplayProvider(bad))
