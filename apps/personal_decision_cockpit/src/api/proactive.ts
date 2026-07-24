/**
 * Proactive 直读端点 client（Phase 39，spec §7.6 / §11.1）。
 * GET /proactive/candidate/explain 与 GET /proactive/controls/status 返回
 * compact 信封（agent_compact_envelope_v1：ok/summary/data/error{code,category,message,…}）。
 * 真实字段以后端为准：data 按 record 宽松透传，页面尽力解析、缺字段显"未提供"。
 * 错误规范化为 ApiError（只保留 code/message），不携带、不打印 payload（spec §15.4）。
 */
import { z } from 'zod';
import { ApiError } from './client';

const CompactDataSchema = z.record(z.unknown());
export type ProactiveCompactData = z.infer<typeof CompactDataSchema>;

interface CompactErrorBody {
  code?: unknown;
  message?: unknown;
}

interface CompactEnvelope {
  ok?: unknown;
  summary?: unknown;
  data?: unknown;
  error?: CompactErrorBody;
}

async function readCompact(path: string): Promise<ProactiveCompactData> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { Accept: 'application/json' } });
  } catch {
    throw new ApiError('network_error', '无法连接后端服务，请确认 rag-api 是否在 127.0.0.1:8000 运行');
  }

  let body: CompactEnvelope;
  try {
    body = (await response.json()) as CompactEnvelope;
  } catch {
    throw new ApiError('invalid_json', `响应不是合法 JSON（HTTP ${response.status}）`);
  }

  if (body?.ok === true) {
    const parsed = CompactDataSchema.safeParse(body.data);
    if (!parsed.success) {
      throw new ApiError('schema_mismatch', '响应 data 不是对象，与 compact 信封契约不一致');
    }
    return parsed.data;
  }

  // compact 错误信封：只取 code/message（category 等不在 UI 投影层使用）
  const err = body?.error ?? {};
  throw new ApiError(
    typeof err.code === 'string' && err.code ? err.code : `http_${response.status}`,
    (typeof err.message === 'string' && err.message) ||
      (typeof body?.summary === 'string' && body.summary) ||
      `后端返回 HTTP ${response.status}`,
  );
}

/** GET /proactive/candidate/explain?candidate_id=X：候选解释 + evidence（只读） */
export function fetchProactiveCandidateExplain(candidateId: string): Promise<ProactiveCompactData> {
  return readCompact(`/proactive/candidate/explain?candidate_id=${encodeURIComponent(candidateId)}`);
}

/** GET /proactive/controls/status?candidate_id=X：suppress/snooze/cooldown 状态（只读） */
export function fetchProactiveControlsStatus(candidateId: string): Promise<ProactiveCompactData> {
  return readCompact(`/proactive/controls/status?candidate_id=${encodeURIComponent(candidateId)}`);
}
