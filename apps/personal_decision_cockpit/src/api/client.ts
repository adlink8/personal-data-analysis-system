import type { z } from 'zod';

/**
 * 规范化 API 错误：只保留 code/message。
 * 不携带、不打印响应 payload（spec §15.4：浏览器日志禁止输出完整 payload / PII）。
 */
export class ApiError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
  }
}

function toApiError(code: string, message: string): ApiError {
  return new ApiError(code, message);
}

/** 只读 GET：相对路径同源调用，响应经 Zod 校验后才进入 UI。 */
export async function apiGet<S extends z.ZodTypeAny>(path: string, schema: S): Promise<z.infer<S>> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { Accept: 'application/json' } });
  } catch {
    throw toApiError('network_error', '无法连接后端服务，请确认 rag-api 是否在 127.0.0.1:8000 运行');
  }

  if (!response.ok) {
    throw toApiError(`http_${response.status}`, `后端返回 HTTP ${response.status}`);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw toApiError('invalid_json', '响应不是合法 JSON');
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw toApiError('schema_mismatch', '响应格式与投影契约 decision_cockpit_projection_v1 不一致');
  }
  return parsed.data as z.infer<S>;
}

/** Same-origin guarded POST; only the typed metadata envelope enters UI state. */
export async function apiPost<S extends z.ZodTypeAny>(path: string, payload: unknown, schema: S): Promise<z.infer<S>> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    throw toApiError('network_error', '无法连接后端服务');
  }
  let body: unknown;
  try { body = await response.json(); } catch { throw toApiError('invalid_json', '响应不是合法 JSON'); }
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw toApiError(`http_${response.status}`, '运行时控制响应格式无效');
  return parsed.data as z.infer<S>;
}
