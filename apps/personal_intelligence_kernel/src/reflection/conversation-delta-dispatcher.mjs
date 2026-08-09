// Plan 61-06: durable replay dispatcher for committed conversation deltas.
//
// The sole consumer path for `conversation.delta.committed`: replays committed
// events after the persisted named consumer checkpoint, validates type/source/
// authority/snapshot/checksum/watermark bindings, delivers only metadata
// (event_id + canonical_checksum + watermark + rule_version) to the injected
// guarded staging seam, and appends a durable checkpoint only after that seam
// succeeds. A failed or divergent dispatch never advances the cursor.
//
// This module never stages a Candidate itself: Candidate staging is reachable
// only through the injected `stage` callback owned by the caller.

import { PiKernelJournalError } from "../events/journal.mjs";
import { CONVERSATION_DELTA_TYPE } from "../events/schema.mjs";

export const CONVERSATION_REFLECTION_CONSUMER = "conversation-reflection-v1";
export const CONVERSATION_DELTA_AUTHORITY = "canonical.sync";
export const CONVERSATION_DELTA_SOURCES = Object.freeze(["pk-sync", "conversation.close"]);

const SHA256_HEX = /^[a-f0-9]{64}$/;
const SNAPSHOT_PATTERN = /^agentsview@[a-f0-9]{64}$/;
// ref encodes `canonical.conversation@<watermark>#<publication_version>`.
const DELTA_REF_PATTERN = /^canonical\.conversation@([a-f0-9]{64})#/;

function extractDeltaMetadata(event) {
  if (event.type !== CONVERSATION_DELTA_TYPE) throw new PiKernelJournalError("delta_type_invalid");
  if (!CONVERSATION_DELTA_SOURCES.includes(event.source)) throw new PiKernelJournalError("delta_source_invalid");
  if (event.authority !== CONVERSATION_DELTA_AUTHORITY) throw new PiKernelJournalError("delta_authority_invalid");
  if (typeof event.snapshot !== "string" || !SNAPSHOT_PATTERN.test(event.snapshot)) throw new PiKernelJournalError("delta_snapshot_invalid");
  const payloadRef = event.payload_ref;
  if (!payloadRef || payloadRef.kind !== "artifact" || typeof payloadRef.checksum !== "string" || !SHA256_HEX.test(payloadRef.checksum)) {
    throw new PiKernelJournalError("delta_checksum_invalid");
  }
  const match = DELTA_REF_PATTERN.exec(payloadRef.ref || "");
  if (!match) throw new PiKernelJournalError("delta_ref_invalid");
  // The committed watermark embedded in the ref must equal the canonical checksum.
  if (match[1] !== payloadRef.checksum) throw new PiKernelJournalError("delta_watermark_mismatch");
  return {
    event_id: event.event_id,
    canonical_checksum: payloadRef.checksum,
    watermark: match[1],
  };
}

export function createConversationDeltaDispatcher({ journal, consumerName, ruleVersion, stage }) {
  if (!journal || typeof journal.consumerCheckpoint !== "function") throw new TypeError("journal is required");
  if (typeof consumerName !== "string" || !consumerName) throw new TypeError("consumerName is required");
  if (typeof ruleVersion !== "string" || !ruleVersion) throw new TypeError("ruleVersion is required");
  if (typeof stage !== "function") throw new TypeError("guarded staging seam (stage) is required");

  return {
    async run({ limit = 100 } = {}) {
      const checkpoint = journal.consumerCheckpoint(consumerName);
      const after = checkpoint ? checkpoint.sequence : 0;
      const replay = journal.replay(after, limit);
      let dispatched = 0;
      let failures = 0;
      let cursor = after;
      for (const row of replay.events) {
        const { event, sequence, canonical_checksum: rowChecksum } = row;
        let metadata;
        try {
          metadata = extractDeltaMetadata(event);
        } catch (error) {
          failures += 1;
          break; // fail closed: a divergent/invalid replay never advances the cursor
        }
        const callbackMetadata = {
          event_id: metadata.event_id,
          canonical_checksum: metadata.canonical_checksum,
          watermark: metadata.watermark,
          rule_version: ruleVersion,
        };
        try {
          await stage(callbackMetadata);
        } catch (error) {
          failures += 1;
          break; // guarded staging failed: cursor must not advance past it
        }
        journal.checkpointAppend(consumerName, sequence, { checksum: rowChecksum });
        dispatched += 1;
        cursor = sequence;
      }
      return { dispatched, failures, cursor };
    },
  };
}

/** One-shot convenience runner (exact replay is duplicate-safe via the cursor). */
export async function run(journal, { consumerName, ruleVersion, stage, limit = 100 } = {}) {
  return createConversationDeltaDispatcher({ journal, consumerName, ruleVersion, stage }).run({ limit });
}

/** Read the persisted cursor for a named consumer (0 when fresh). */
export function cursor(journal, consumerName) {
  const checkpoint = journal.consumerCheckpoint(consumerName);
  return checkpoint ? checkpoint.sequence : 0;
}
