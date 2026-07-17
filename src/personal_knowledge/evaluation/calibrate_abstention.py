"""Calibrate retrieval abstention thresholds on the private development set only."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from personal_knowledge.core.project_paths import ROOT
from personal_knowledge.evaluation.eval_contracts import load_cases_jsonl
from personal_knowledge.evaluation.knowledge_eval_metrics import CaseScore
from personal_knowledge.evaluation.run_knowledge_eval import load_config, stage_retrieval

DEV_SET = ROOT / "var" / "runtime" / "private_evals" / "abstention_dev_v1.private.jsonl"
CONFIG = ROOT / "assets" / "evals" / "knowledge_units" / "eval_v1.yaml"
WORK_DIR = ROOT / "var" / "runtime" / "private_evals" / "abstention_calibration_v1"
REPORT = ROOT / "var" / "reports" / "analysis" / "evaluations" / "abstention_calibration_v1.json"


@dataclass
class ThresholdResult:
    threshold: float | None
    positive_n: int
    negative_n: int
    positive_retention: float | None
    negative_fp_rate: float | None
    passed: bool


def select_threshold(
    scores: Sequence[CaseScore],
    *,
    max_negative_fp: float = 0.10,
    min_positive_retention: float = 0.80,
) -> ThresholdResult:
    positives = [
        float(score.top_score)
        for score in scores
        if not score.expected_abstain and score.top_score is not None
    ]
    negatives = [
        float(score.top_score)
        for score in scores
        if score.expected_abstain and score.top_score is not None
    ]
    if not positives or not negatives:
        return ThresholdResult(None, len(positives), len(negatives), None, None, False)
    candidates = sorted(set(positives + negatives))
    candidates.append(max(candidates) + 1e-9)
    feasible: list[tuple[float, float, float]] = []
    for threshold in candidates:
        positive_retention = sum(value >= threshold for value in positives) / len(positives)
        negative_fp = sum(value >= threshold for value in negatives) / len(negatives)
        if negative_fp <= max_negative_fp:
            feasible.append((positive_retention, -threshold, negative_fp))
    if not feasible:
        return ThresholdResult(None, len(positives), len(negatives), 0.0, 1.0, False)
    positive_retention, negative_threshold, negative_fp = max(feasible)
    threshold = -negative_threshold
    return ThresholdResult(
        threshold=threshold,
        positive_n=len(positives),
        negative_n=len(negatives),
        positive_retention=positive_retention,
        negative_fp_rate=negative_fp,
        passed=positive_retention >= min_positive_retention,
    )


def run() -> dict:
    cases = load_cases_jsonl(DEV_SET)
    cfg = load_config(CONFIG)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    retrieval = stage_retrieval(cases, cfg, WORK_DIR, offline=False)
    modes = {
        mode: asdict(select_threshold(scores))
        for mode, scores in (retrieval.get("mode_scores") or {}).items()
    }
    result = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset": "private:abstention_dev_v1",
        "case_count": len(cases),
        "constraints": {"max_negative_fp": 0.10, "min_positive_retention": 0.80},
        "modes": modes,
        "passed": bool(modes) and all(value["passed"] for value in modes.values()),
        "note": "Development-only calibration; frozen/private full-suite thresholds were not used.",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
