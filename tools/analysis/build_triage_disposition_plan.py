"""Assemble the Phase 43 dry-run disposition ledger without DB writes."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--triage',type=Path,required=True); p.add_argument('--promote',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    d=json.loads(a.triage.read_text(encoding='utf-8')); promote=json.loads(a.promote.read_text(encoding='utf-8'))
    dup=len(d.get('unit_ids',{}).get('duplicate',[])); noise=len(d.get('unit_ids',{}).get('noise_candidate',[])); true=len(d.get('unit_ids',{}).get('suspected_true_knowledge',[]))
    out={
        'version':'v1','mode':'dry-run','db_write':False,'source_report':str(a.triage),
        'counts':{'duplicate':dup,'noise_candidate':noise,'suspected_true_knowledge':true},
        'batch_size':50,'batch_counts':{'supersede':(dup+49)//50,'deprecate':(noise+49)//50,'promote':true},
        'proposal_glob':'var/reports/analysis/triage_*_batch_*.json',
        'supersede':{'skipped_reason':'historical snapshot IDs are no longer staging; no manifest registered','batch_count':(dup+49)//50},
        'deprecate':{'unit_self_evidence_refs':True,'batch_count':(noise+49)//50},
        'promote':{'report':str(a.promote),'plans':promote.get('plans',[]),'rematch_failed':promote.get('rematch_failed',0)},
        'human_review_required':True,
        'notes':['Historical 2026-07-25 snapshot reproduces 11,163 eligible-excluded staging rows, within the 11,008 +/-5% baseline.','Current unified DB has already transitioned these IDs out of staging; this ledger intentionally does not apply stale proposals.'],
    }
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'output':str(a.output),'batch_counts':out['batch_counts'],'db_write':False},ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
