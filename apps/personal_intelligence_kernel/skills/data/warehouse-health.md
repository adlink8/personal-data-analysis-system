# warehouse.health

Entry: inspect bounded warehouse health.
Steps: inspect schema, lineage, quality, freshness, integrity and failed batches.
Stop: any unsafe input, authority mismatch, or completed receipt.
Checkpoint: read-only; no ingestion or repair.
