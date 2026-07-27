/**
 * Guarded Orchestration 写操作 client（Phase 38，spec §5.3 / §13）。
 *
 * 契约要点（与后端 orchestration_service / agent_contract 对齐）：
 * - 所有写操作 POST JSON 到 `/agent/session/*`，读会话用 GET `/agent/session/resume`；
 * - 响应为 compact 信封（agent_compact_envelope_v1，16KB 预算）：
 *   ok/status/summary/data/error{code,category,message,retryable,recovery_actions}；
 * - 所有时间戳必须 Z 结尾（`new Date().toISOString()`）；execute 类请求 now 必填；
 * - 每跳 transition 严格线性：先 preview 再带幂等键 execute，禁止"一键完成全部阶段"。
 *
 * 安全约束（spec §15.4）：错误只保留 code/category/message/retryable/recovery_actions，
 * 不携带、不打印请求或响应 payload。
 */

/* ---------------- 类型 ---------------- */

/** exact preview（服务端返回的 Preview 字典，回传时必须原样） */
export interface OrchestrationPreview {
  session_id: string;
  operation: string;
  actor_identity_hash?: string;
  expected_sequence: number;
  payload: Record<string, unknown>;
  issued_at: string;
  preview_checksum: string;
  [key: string]: unknown;
}

/** 写入成功的 OperationResult */
export interface OperationResult {
  session_id: string;
  operation: string;
  state: string;
  sequence: number;
  event_id: string;
  event_checksum: string;
  replayed: boolean;
  references?: Record<string, unknown>;
  [key: string]: unknown;
}

/** GET /agent/session/resume 的 data */
export interface SessionResume {
  session_id: string;
  state: string;
  sequence: number;
  last_event_checksum: string;
  manifest: Record<string, unknown>;
  binding: Record<string, unknown>;
  [key: string]: unknown;
}

/** 规范化写入错误：与 TypedRecoveryPanel 的分类渲染一一对应 */
export class OrchestrationError extends Error {
  readonly code: string;
  readonly category: string;
  readonly retryable: boolean;
  readonly recoveryActions: string[];

  constructor(init: {
    code: string;
    category?: string;
    message: string;
    retryable?: boolean;
    recoveryActions?: string[];
  }) {
    super(init.message);
    this.name = 'OrchestrationError';
    this.code = init.code;
    this.category = init.category ?? 'runtime';
    this.retryable = init.retryable ?? false;
    this.recoveryActions = init.recoveryActions ?? [];
  }
}

/**
 * 安全重试边界（Phase 38-02 收口，T-38-06/T-38-07/T-38-08）：
 * 服务端 `error.retryable` 只表示"该类别整体不是致命的"，不等于"原样重发同一个 preview +
 * 同一个幂等键是安全或正确的恢复动作"——`stale`/`confirmation`/`sequence`/`conflict` 等类别的
 * 唯一合法恢复路径是 resume 拿到最新状态后重新 prepare/preview，而不是静默重试一个已经过期、
 * 已被消费或绑定漂移的 Preview（RESEARCH.md「Typed Recovery Matrix」明确列为禁止行为）。
 * 因此 UI 不能只看 `retryable`：
 * - `canRetrySamePreview`：仅当服务端明确给出 `retry_when_ready`（目前只出现于 runtime 类别，
 *   例如本地密钥/生成器暂未就绪）时，才允许调用方复用同一 preview + 同一幂等键重新提交；
 *   `actor_identity_mismatch` 无论服务端如何归类都强制返回 false——页面刷新后的旧会话绝不能
 *   被 UI 暗示"重试即可继续写入"（防止把身份轮换误当作可恢复的暂时性故障）。
 * - `canResumeSession`：服务端建议先 `resume_session` 时返回 true，调用方应丢弃本地已持有的
 *   preview/幂等键并重新拉取只读 resume，而不是复用旧状态推进。
 * 两者都是纯函数，只读 compact 错误的 code/recoveryActions 字段，不发起任何请求、
 * 不铸造 confirmation/HMAC、不替调用方决定下一跳。
 */
export function canRetrySamePreview(error: Pick<OrchestrationError, 'code' | 'recoveryActions'>): boolean {
  if (error.code === 'actor_identity_mismatch') return false;
  return error.recoveryActions.includes('retry_when_ready');
}

export function canResumeSession(error: Pick<OrchestrationError, 'recoveryActions'>): boolean {
  return error.recoveryActions.includes('resume_session');
}

/* ---------------- transition 词表（严格线性，spec §5.3） ---------------- */

export type TransitionKey =
  | 'confirm'
  | 'generate'
  | 'publish'
  | 'decide'
  | 'preregister'
  | 'action_start'
  | 'action_complete'
  | 'observe'
  | 'calibrate';

export interface TransitionMeta {
  key: TransitionKey;
  label: string;
  /** execute 路由别名（preview.operation 必须与路由后缀一致，否则 route_operation_mismatch） */
  route: string;
  /** 该跳将追加的事件说明 */
  eventDescription: string;
}

export const TRANSITION_CHAIN: ReadonlyArray<TransitionMeta> = [
  { key: 'confirm', label: '确认会话', route: '/agent/session/confirm', eventDescription: '创建会话并写入第一条 confirm 事件' },
  { key: 'generate', label: '生成分析', route: '/agent/session/generate', eventDescription: '写入 generate 事件：生成决策分析候选' },
  { key: 'publish', label: '发布候选', route: '/agent/session/publish', eventDescription: '写入 publish 事件：候选进入 Pilot 权威案例' },
  { key: 'decide', label: '记录决策', route: '/agent/session/decide', eventDescription: '写入 decide 事件：决策确认写入 Pilot 权威案例' },
  { key: 'preregister', label: '预注册结果', route: '/agent/session/preregister', eventDescription: '写入 preregister 事件：预注册结果度量口径' },
  { key: 'action_start', label: '记录行动开始', route: '/agent/session/action-start', eventDescription: '写入 action_start 事件：标记行动开始' },
  { key: 'action_complete', label: '记录行动完成', route: '/agent/session/action-complete', eventDescription: '写入 action_complete 事件：标记行动完成' },
  { key: 'observe', label: '记录结果观察', route: '/agent/session/observe', eventDescription: '写入 observe 事件：记录真实结果观察' },
  { key: 'calibrate', label: '校准评估', route: '/agent/session/calibrate', eventDescription: '写入 calibrate 事件：非因果校准评估' },
];

/** 会话当前 state → 唯一合法下一跳（与后端 TRANSITIONS 对齐；null = 链已走完） */
export const NEXT_TRANSITION_BY_STATE: Record<string, TransitionKey | null> = {
  confirmed: 'generate',
  generated: 'publish',
  published: 'decide',
  decided: 'preregister',
  preregistered: 'action_start',
  action_started: 'action_complete',
  action_completed: 'observe',
  observed: 'calibrate',
  calibrated: null,
};

export function transitionMeta(key: string): TransitionMeta | undefined {
  return TRANSITION_CHAIN.find((meta) => meta.key === key);
}

/* ---------------- 工具 ---------------- */

/** Z 结尾时间戳（后端 _utc 强制要求） */
export function nowIso(): string {
  return new Date().toISOString();
}

function randomUuid(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  // 退化路径：getRandomValues 拼 UUID 形态（幂等键只需唯一，服务端按不透明字符串处理）
  if (c && typeof c.getRandomValues === 'function') {
    const bytes = c.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6]! & 0x0f) | 0x40;
    bytes[8] = (bytes[8]! & 0x3f) | 0x80;
    const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0'));
    return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`;
  }
  return `fallback-${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 14)}`;
}

/** 幂等键：`ui-<op>-<uuid>`；同一次写入尝试重试时复用同一键（exact replay 保护） */
export function newIdempotencyKey(operation: string): string {
  return `ui-${operation}-${randomUuid()}`;
}

/**
 * actor_identity_hash：恰好 64 位小写 hex（SubtleCrypto SHA-256）。
 * 对每次页面运行生成的本地随机串派生，不含真实用户标识、不持久化（spec §15）。
 * 整个 JS 运行期共享同一 hash（模块级缓存）：同一会话内可连续推进；
 * 页面刷新后旧会话只能只读 resume，无法继续推进（服务端 actor 绑定，fail closed）。
 */
let cachedActorHash: string | null = null;

export async function deriveActorIdentityHash(): Promise<string> {
  if (cachedActorHash) return cachedActorHash;
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    throw new OrchestrationError({
      code: 'subtlecrypto_unavailable',
      category: 'runtime',
      message: '当前浏览器不支持 SubtleCrypto，无法派生操作者身份哈希',
    });
  }
  const seed = `cockpit-actor-${randomUuid()}`;
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(seed));
  cachedActorHash = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
  return cachedActorHash;
}

/* ---------------- compact 信封处理 ---------------- */

interface CompactErrorBody {
  code?: unknown;
  category?: unknown;
  message?: unknown;
  retryable?: unknown;
  recovery_actions?: unknown;
}

interface CompactEnvelope {
  ok?: unknown;
  summary?: unknown;
  data?: unknown;
  error?: CompactErrorBody;
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

async function readEnvelope(path: string, init: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
    });
  } catch {
    throw new OrchestrationError({
      code: 'network_error',
      category: 'runtime',
      message: '无法连接后端服务，请确认 rag-api 是否在 127.0.0.1:8000 运行',
      retryable: true,
      recoveryActions: ['check_runtime', 'retry_when_ready'],
    });
  }

  let body: CompactEnvelope;
  try {
    body = (await response.json()) as CompactEnvelope;
  } catch {
    throw new OrchestrationError({
      code: 'invalid_json',
      category: 'runtime',
      message: `响应不是合法 JSON（HTTP ${response.status}）`,
      retryable: true,
      recoveryActions: ['check_runtime', 'retry_when_ready'],
    });
  }

  if (body?.ok === true) return body.data;

  // compact 错误信封：code/category/message/retryable/recovery_actions
  const err = body?.error ?? {};
  throw new OrchestrationError({
    code: typeof err.code === 'string' && err.code ? err.code : `http_${response.status}`,
    category: typeof err.category === 'string' && err.category ? err.category : 'runtime',
    message:
      (typeof err.message === 'string' && err.message) ||
      (typeof body?.summary === 'string' && body.summary) ||
      `后端返回 HTTP ${response.status}`,
    retryable: err.retryable === true,
    recoveryActions: asStringList(err.recovery_actions),
  });
}

function post(path: string, payload: unknown): Promise<unknown> {
  return readEnvelope(path, { method: 'POST', body: JSON.stringify(payload) });
}

/* ---------------- 会话写操作 ---------------- */

export interface PrepareInput {
  goal: string;
  constraints: string[];
  weights: Record<string, number>;
  actor_identity_hash: string;
  domain: 'project';
  risk_budget: 'low';
}

/** POST /agent/session/prepare → Preview P0（operation=confirm, expected_sequence=0） */
export async function sessionPrepare(input: PrepareInput): Promise<OrchestrationPreview> {
  const data = await post('/agent/session/prepare', { ...input, now: nowIso() });
  return data as OrchestrationPreview;
}

/**
 * POST /agent/session/confirm：preview 必须原样回传（checksum 绑定），
 * confirmed:true 由服务端换发 confirmation_token 后立即消费。
 */
export async function sessionConfirm(
  preview: OrchestrationPreview,
  idempotencyKey: string,
): Promise<OperationResult> {
  const data = await post('/agent/session/confirm', {
    preview,
    confirmed: true,
    idempotency_key: idempotencyKey,
    now: nowIso(),
  });
  return data as OperationResult;
}

export interface PreviewInput {
  session_id: string;
  transition: TransitionKey;
  /** transition payload.input（服务端包装为 {input, binding_hash}） */
  payload: Record<string, unknown>;
  actor_identity_hash: string;
  /** 上一步 OperationResult.sequence（或 resume 的 sequence） */
  expected_sequence: number;
}

/** POST /agent/session/preview → 下一跳的 exact preview */
export async function sessionPreview(input: PreviewInput): Promise<OrchestrationPreview> {
  const data = await post('/agent/session/preview', { ...input, now: nowIso() });
  return data as OrchestrationPreview;
}

/**
 * POST /agent/session/<别名>：execute 类请求 now 必填（服务端 timestamp_required）。
 * transition → 路由别名：generate→/generate … action_start→/action-start …
 */
export async function sessionExecute(
  transition: TransitionKey,
  preview: OrchestrationPreview,
  idempotencyKey: string,
): Promise<OperationResult> {
  const meta = transitionMeta(transition);
  if (!meta || transition === 'confirm') {
    throw new OrchestrationError({
      code: 'operation_unknown',
      category: 'runtime',
      message: `未知的 execute transition：${transition}`,
    });
  }
  const data = await post(meta.route, {
    preview,
    confirmed: true,
    idempotency_key: idempotencyKey,
    now: nowIso(),
  });
  return data as OperationResult;
}

/** GET /agent/session/resume?session_id=X（只读：恢复会话，决定下一合法 transition） */
export async function sessionResume(sessionId: string): Promise<SessionResume> {
  const data = await readEnvelope(
    `/agent/session/resume?session_id=${encodeURIComponent(sessionId)}`,
    { method: 'GET' },
  );
  return data as SessionResume;
}
