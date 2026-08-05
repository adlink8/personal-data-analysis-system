# warehouse.failed_batch_recovery

Entry: recover a declared failed batch within a logical authority scope.
Steps: list failed batches, prepare an exact ingestion preview, quarantine or commit only the approved candidate, then verify.
Stop: missing batch, stale preview, outcome unknown, binding drift, or failed verification.
Checkpoint: canonical correction remains a human-confirmed separate operation.
