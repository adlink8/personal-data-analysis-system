import {
  AssistantRuntimeProvider,
  type AppendMessage,
  type ThreadMessageLike,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import {
  type PropsWithChildren,
  useCallback,
  useMemo,
  useRef,
  useState,
} from "react";

export const HARNESS_ADAPTER_SCHEMA = "harness-assistant-ui-adapter-v1";

export type SafeEvidenceRow = Record<string, string | number | boolean | null>;

export type SafeEvidenceReceipt = {
  receiptId: string;
  databaseId: string;
  queryId: "conversation.evidence_messages.v1";
  descriptorVersion: "1.0.0";
  statementDisplay: "conversation.evidence_messages.v1(session_id, after, limit)";
  queryChecksum: string;
  parameterNames: readonly ["after", "limit", "session_id"];
  status: string;
  rows: SafeEvidenceRow[];
  rowCount: number;
  durationMs: number | null;
  truncated: boolean;
};

export type SafeCandidate = {
  candidateId: string;
  title: string;
  summary: string;
  status: "pending_review" | "accepted" | "ignored";
  version: number;
  checksum: string | null;
};

export type HarnessRuntimeMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: string;
  status?: "complete" | "incomplete";
  receipt?: SafeEvidenceReceipt;
};

export type HarnessBridge = {
  sendTurn(payload: {
    conversationId: string;
    text: string;
    projectScopeId?: string;
    skillId?: string;
  }): Promise<unknown> | unknown;
  cancelTurn(payload: { taskId: string }): Promise<unknown> | unknown;
};

export type AdapterEvent = {
  type:
    | "turn_started"
    | "turn_completed"
    | "turn_rejected"
    | "cancel_routed"
    | "cancel_unavailable";
  at: string;
  code?: string;
  taskId?: string;
};

type HarnessRuntimeProviderProps = PropsWithChildren<{
  bridge: HarnessBridge;
  conversationId: string;
  projectScopeId?: string;
  initialMessages: readonly HarnessRuntimeMessage[];
  onReceipts?: (receipts: readonly SafeEvidenceReceipt[]) => void;
  onCandidate?: (candidate: SafeCandidate | null) => void;
  onAdapterEvent?: (event: AdapterEvent) => void;
}>;

const APPROVED_QUERY = Object.freeze({
  queryId: "conversation.evidence_messages.v1",
  version: "1.0.0",
  parameterNames: Object.freeze(["after", "limit", "session_id"]),
  statementDisplay: "conversation.evidence_messages.v1(session_id, after, limit)",
});

const FORBIDDEN_FIELD_RE =
  /^(?:thinking|thoughts|reasoning|thought|chain_of_thought|chain-of-thought|raw|raw_body|rawBody|body|content|prompt|completion|input_json|inputJson|provider_body|providerBody|provider|tool_body|toolBody|tool_call|toolCall|tool_result|toolResult|trace|stack|stack_trace|diagnostic|diagnostics|credential|credentials|secret|secrets|token|password|api_key|apiKey|endpoint|url|uri|path|command|sql|statement|query|parameter_values|parameterValues|params|hidden|internal|model_output|modelOutput|response_body|responseBody|request_body|requestBody|receipt_body|receiptBody|session_trajectory|trajectory|output|result|response|reply|answer)$/i;

const FORBIDDEN_BRIDGE_METHOD_RE = /^(?:fetch|request|invoke|send|execute|query|sql|executeSql|querySql|open|openFile|read|readFile|write|writeFile)$/i;
const ID_RE = /^[A-Za-z][A-Za-z0-9._:/-]{1,255}$/;
const SHA256_RE = /^[a-f0-9]{64}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function containsForbiddenFields(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsForbiddenFields);
  if (!isRecord(value)) return false;
  return Object.entries(value).some(
    ([key, child]) => FORBIDDEN_FIELD_RE.test(key) || containsForbiddenFields(child),
  );
}

export function assertNamedBridgeOnly(bridge: HarnessBridge): HarnessBridge {
  if (!isRecord(bridge)) throw new TypeError("invalid_bridge");
  if (typeof bridge.sendTurn !== "function" || typeof bridge.cancelTurn !== "function") {
    throw new TypeError("missing_named_bridge_method");
  }
  if (Object.keys(bridge).some((key) => FORBIDDEN_BRIDGE_METHOD_RE.test(key))) {
    throw new TypeError("generic_bridge_surface_rejected");
  }
  return bridge;
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function sha256Hex(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalJson(value));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function receiptChecksumBinding(receipt: {
  query_id: string;
  version?: string;
  descriptor_version?: string;
  parameter_names: readonly string[];
  statement_display: string;
}): Promise<string> {
  return sha256Hex({
    query_id: receipt.query_id,
    version: receipt.version ?? receipt.descriptor_version,
    parameter_names: [...receipt.parameter_names].sort(),
    statement_display: receipt.statement_display,
  });
}

function safeRows(value: unknown): SafeEvidenceRow[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 100).map((row) => {
    if (!isRecord(row)) return {};
    const safe: SafeEvidenceRow = {};
    for (const [key, child] of Object.entries(row)) {
      if (
        !FORBIDDEN_FIELD_RE.test(key) &&
        (child === null || ["string", "number", "boolean"].includes(typeof child))
      ) {
        safe[key] = child as string | number | boolean | null;
      }
    }
    return safe;
  });
}

export async function normalizeEvidenceReceipt(value: unknown): Promise<SafeEvidenceReceipt | null> {
  if (!isRecord(value) || containsForbiddenFields(value)) return null;
  const version = typeof value.version === "string" ? value.version : value.descriptor_version;
  const names = Array.isArray(value.parameter_names) ? [...value.parameter_names].sort() : [];
  if (
    value.query_id !== APPROVED_QUERY.queryId ||
    version !== APPROVED_QUERY.version ||
    names.join(",") !== APPROVED_QUERY.parameterNames.join(",") ||
    value.statement_display !== APPROVED_QUERY.statementDisplay ||
    typeof value.query_checksum !== "string" ||
    !SHA256_RE.test(value.query_checksum)
  ) {
    return null;
  }
  const checksum = await receiptChecksumBinding({
    query_id: value.query_id,
    version,
    parameter_names: names,
    statement_display: value.statement_display,
  });
  if (checksum !== value.query_checksum) return null;
  const rows = safeRows(value.rows);
  return {
    receiptId: typeof value.receipt_id === "string" && ID_RE.test(value.receipt_id) ? value.receipt_id : "receipt_redacted",
    databaseId: typeof value.database_id === "string" && ID_RE.test(value.database_id) ? value.database_id : "database_redacted",
    queryId: APPROVED_QUERY.queryId,
    descriptorVersion: APPROVED_QUERY.version,
    statementDisplay: APPROVED_QUERY.statementDisplay,
    queryChecksum: checksum,
    parameterNames: ["after", "limit", "session_id"],
    status: typeof value.status === "string" ? value.status : "ok",
    rows,
    rowCount: Number.isInteger(value.row_count) ? Number(value.row_count) : rows.length,
    durationMs: typeof value.duration_ms === "number" ? value.duration_ms : null,
    truncated: value.truncated === true,
  };
}

function normalizeCandidate(value: unknown): SafeCandidate | null {
  if (!isRecord(value) || containsForbiddenFields(value)) return null;
  if (typeof value.candidateId !== "string" || !value.candidateId.startsWith("candidate_")) return null;
  const status = value.status;
  if (status !== "pending_review" && status !== "accepted" && status !== "ignored") return null;
  return {
    candidateId: value.candidateId,
    title: typeof value.title === "string" ? value.title.slice(0, 160) : "待审核建议",
    summary: typeof value.summary === "string" ? value.summary.slice(0, 1000) : "",
    status,
    version: Number.isInteger(value.version) ? Number(value.version) : 0,
    checksum: typeof value.checksum === "string" && SHA256_RE.test(value.checksum) ? value.checksum : null,
  };
}

function assistantFailure(code: string, now: () => string): HarnessRuntimeMessage {
  return {
    id: `assistant_error_${Date.now()}`,
    role: "assistant",
    text: "本轮没有完成，也没有发生未授权变更。请重试或查看系统状态。",
    createdAt: now(),
    status: "incomplete",
  };
}

export async function normalizeTurnEnvelope(
  envelope: unknown,
  now: () => string = () => new Date().toISOString(),
): Promise<{
  messages: HarnessRuntimeMessage[];
  receipts: SafeEvidenceReceipt[];
  candidate: SafeCandidate | null;
  taskId: string | null;
  code: string | null;
}> {
  if (!isRecord(envelope) || envelope.ok !== true || !isRecord(envelope.data)) {
    return { messages: [assistantFailure("bridge_error", now)], receipts: [], candidate: null, taskId: null, code: "bridge_error" };
  }
  if (containsForbiddenFields(envelope.data)) {
    return { messages: [assistantFailure("forbidden_response_field", now)], receipts: [], candidate: null, taskId: null, code: "forbidden_response_field" };
  }

  const data = envelope.data;
  const receiptValues = Array.isArray(data.receipts)
    ? data.receipts
    : isRecord(data.toolRow) && Array.isArray(data.toolRow.receipts)
      ? data.toolRow.receipts
      : [];
  const receipts = (await Promise.all(receiptValues.map(normalizeEvidenceReceipt))).filter(
    (receipt): receipt is SafeEvidenceReceipt => receipt !== null,
  );
  const messageValues = Array.isArray(data.messages) ? data.messages : [];
  const messages = messageValues
    .filter(isRecord)
    .map((message, index): HarnessRuntimeMessage | null => {
      if (message.role !== "assistant" || typeof message.displayText !== "string") return null;
      return {
        id: typeof message.messageId === "string" ? message.messageId : `assistant_${Date.now()}_${index}`,
        role: "assistant",
        text: message.displayText.slice(0, 16000),
        createdAt: typeof message.createdAt === "string" ? message.createdAt : now(),
        status: "complete",
        receipt: receipts[index] ?? (index === 0 ? receipts[0] : undefined),
      };
    })
    .filter((message): message is HarnessRuntimeMessage => message !== null);

  if (messages.length === 0 && typeof data.displayText === "string") {
    messages.push({
      id: `assistant_${Date.now()}`,
      role: "assistant",
      text: data.displayText.slice(0, 16000),
      createdAt: now(),
      status: "complete",
      receipt: receipts[0],
    });
  }
  if (messages.length === 0) {
    return { messages: [assistantFailure("missing_display_message", now)], receipts: [], candidate: null, taskId: null, code: "missing_display_message" };
  }
  return {
    messages,
    receipts,
    candidate: normalizeCandidate(data.candidate),
    taskId: typeof data.taskId === "string" && data.taskId.startsWith("pi_task_") ? data.taskId : null,
    code: null,
  };
}

export async function dispatchHarnessTurn(
  bridge: HarnessBridge,
  payload: { conversationId: string; text: string; projectScopeId?: string; skillId?: string },
) {
  const namedBridge = assertNamedBridgeOnly(bridge);
  const envelope = await Promise.resolve(namedBridge.sendTurn(payload));
  return normalizeTurnEnvelope(envelope);
}

export async function cancelHarnessTurn(bridge: HarnessBridge, taskId: string | null): Promise<boolean> {
  if (!taskId) return false;
  const namedBridge = assertNamedBridgeOnly(bridge);
  await Promise.resolve(namedBridge.cancelTurn({ taskId }));
  return true;
}

function appendText(message: AppendMessage): string {
  if (message.role !== "user") throw new TypeError("only_user_messages_supported");
  if (message.content.some((part) => part.type !== "text")) {
    throw new TypeError("only_text_parts_supported");
  }
  const text = message.content.map((part) => part.type === "text" ? part.text : "").join("").trim();
  if (text.length < 1 || text.length > 16000) throw new TypeError("invalid_text");
  return text;
}

export function toThreadMessage(message: HarnessRuntimeMessage): ThreadMessageLike {
  const content: ThreadMessageLike["content"] = message.receipt
    ? [
        { type: "text", text: message.text },
        { type: "data-tool-receipt", data: message.receipt },
      ]
    : [{ type: "text", text: message.text }];
  return {
    id: message.id,
    role: message.role,
    content,
    createdAt: new Date(message.createdAt),
    status:
      message.role === "assistant"
        ? message.status === "incomplete"
          ? { type: "incomplete", reason: "error" }
          : { type: "complete", reason: "stop" }
        : undefined,
    metadata: { custom: { schema: HARNESS_ADAPTER_SCHEMA } },
  };
}

export function HarnessRuntimeProvider({
  bridge,
  conversationId,
  projectScopeId,
  initialMessages,
  onReceipts,
  onCandidate,
  onAdapterEvent,
  children,
}: HarnessRuntimeProviderProps) {
  const namedBridge = useMemo(() => assertNamedBridgeOnly(bridge), [bridge]);
  const [messages, setMessages] = useState<HarnessRuntimeMessage[]>(() => [...initialMessages]);
  const [isRunning, setIsRunning] = useState(false);
  const activeTaskId = useRef<string | null>(null);
  const sequence = useRef(0);
  const emit = useCallback(
    (event: Omit<AdapterEvent, "at">) => onAdapterEvent?.({ ...event, at: new Date().toISOString() }),
    [onAdapterEvent],
  );

  const onNew = useCallback(
    async (message: AppendMessage) => {
      if (isRunning) throw new TypeError("turn_already_running");
      const text = appendText(message);
      sequence.current += 1;
      const id = sequence.current;
      setMessages((current) => [
        ...current,
        { id: `user_local_${id}`, role: "user", text, createdAt: new Date().toISOString() },
      ]);
      setIsRunning(true);
      emit({ type: "turn_started" });
      try {
        const normalized = await dispatchHarnessTurn(namedBridge, {
          conversationId,
          text,
          ...(projectScopeId ? { projectScopeId } : {}),
        });
        activeTaskId.current = normalized.taskId;
        setMessages((current) => [...current, ...normalized.messages]);
        onReceipts?.(normalized.receipts);
        onCandidate?.(normalized.candidate);
        emit(
          normalized.code
            ? { type: "turn_rejected", code: normalized.code }
            : { type: "turn_completed", ...(normalized.taskId ? { taskId: normalized.taskId } : {}) },
        );
      } catch {
        setMessages((current) => [...current, assistantFailure("bridge_exception", () => new Date().toISOString())]);
        emit({ type: "turn_rejected", code: "bridge_exception" });
      } finally {
        setIsRunning(false);
        activeTaskId.current = null;
      }
    },
    [conversationId, emit, isRunning, namedBridge, onCandidate, onReceipts, projectScopeId],
  );

  const onCancel = useCallback(async () => {
    const taskId = activeTaskId.current;
    if (!taskId) {
      emit({ type: "cancel_unavailable", code: "task_id_not_available_during_request" });
      return;
    }
    await cancelHarnessTurn(namedBridge, taskId);
    emit({ type: "cancel_routed", taskId });
  }, [emit, namedBridge]);

  const runtime = useExternalStoreRuntime({
    messages,
    convertMessage: toThreadMessage,
    isRunning,
    isSendDisabled: isRunning,
    onNew,
    onCancel,
  });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
