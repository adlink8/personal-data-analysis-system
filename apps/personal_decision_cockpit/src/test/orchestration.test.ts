import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  newIdempotencyKey,
  OrchestrationError,
  sessionConfirm,
  sessionExecute,
  sessionPrepare,
  type OperationResult,
  type OrchestrationPreview,
} from '../api/orchestration';

/**
 * orchestration client 测试（spec §5.3 / §17.2）：
 * - confirm 请求体把 preview 原样回传（fetch mock 断言）；
 * - execute 走别名路由且 now 为 Z 结尾；
 * - compact 错误信封规范化为 OrchestrationError；
 * - 幂等键与 actor hash 形态。
 */

const PREVIEW: OrchestrationPreview = {
  session_id: 'ors_20260719_test_session_0001',
  operation: 'confirm',
  actor_identity_hash: 'a'.repeat(64),
  expected_sequence: 0,
  payload: { schema_version: 'guarded_orchestration_v1', goal: '测试目标' },
  issued_at: '2026-07-19T08:00:00Z',
  preview_checksum: 'abcd1234'.repeat(8),
};

const RESULT: OperationResult = {
  session_id: PREVIEW.session_id,
  operation: 'confirm',
  state: 'confirmed',
  sequence: 1,
  event_id: 'ore_20260719_event0001',
  event_checksum: 'efgh5678'.repeat(8),
  replayed: false,
  references: {},
};

function envelope(data: unknown) {
  return {
    schema_version: 'agent_compact_envelope_v1',
    operation: 'session.confirm',
    ok: true,
    status: 'success',
    summary: 'Confirm completed; 1 stable reference(s) available.',
    ids: [],
    limitations: [],
    next_actions: [],
    evidence_links: [],
    data,
    truncated: false,
    budget: { limit_bytes: 16384, used_bytes: 128 },
  };
}

function mockFetchOnce(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('orchestration client', () => {
  it('sessionConfirm：preview 原样回传 + confirmed + idempotency_key + Z 结尾 now', async () => {
    const fetchMock = mockFetchOnce(envelope(RESULT));
    const result = await sessionConfirm(PREVIEW, 'ui-confirm-key-1');

    expect(result.event_id).toBe(RESULT.event_id);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/agent/session/confirm');
    expect(init.method).toBe('POST');
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    // preview 原样回传（深相等，不增删字段）
    expect(body['preview']).toEqual(PREVIEW);
    expect(body['confirmed']).toBe(true);
    expect(body['idempotency_key']).toBe('ui-confirm-key-1');
    expect(String(body['now'])).toMatch(/Z$/);
  });

  it('sessionExecute：action_start 走 /agent/session/action-start 别名路由', async () => {
    const fetchMock = mockFetchOnce(envelope({ ...RESULT, operation: 'action_start', sequence: 6 }));
    const actionPreview = { ...PREVIEW, operation: 'action_start', expected_sequence: 5 };
    await sessionExecute('action_start', actionPreview, 'ui-action_start-key-2');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/agent/session/action-start');
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body['preview']).toEqual(actionPreview);
    expect(body['idempotency_key']).toBe('ui-action_start-key-2');
    expect(String(body['now'])).toMatch(/Z$/);
  });

  it('sessionPrepare：请求体含 goal/constraints/weights/actor/domain/risk_budget', async () => {
    const fetchMock = mockFetchOnce(envelope(PREVIEW));
    await sessionPrepare({
      goal: '未来 8 周如何分配时间',
      constraints: ['每周不超过 30 小时'],
      weights: { career: 0.6, learning: 0.4 },
      actor_identity_hash: 'a'.repeat(64),
      domain: 'project',
      risk_budget: 'low',
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/agent/session/prepare');
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body['goal']).toBe('未来 8 周如何分配时间');
    expect(body['constraints']).toEqual(['每周不超过 30 小时']);
    expect(body['weights']).toEqual({ career: 0.6, learning: 0.4 });
    expect(body['actor_identity_hash']).toBe('a'.repeat(64));
    expect(body['domain']).toBe('project');
    expect(body['risk_budget']).toBe('low');
  });

  it('compact 错误信封 → OrchestrationError（code/category/retryable/recovery_actions）', async () => {
    mockFetchOnce(
      {
        schema_version: 'agent_compact_envelope_v1',
        operation: 'session.confirm',
        ok: false,
        status: 'error',
        summary: 'The request conflicts with an existing immutable record.',
        ids: [],
        limitations: [],
        next_actions: [],
        evidence_links: [],
        data: null,
        truncated: false,
        error: {
          code: 'idempotency_conflict',
          category: 'conflict',
          message: 'The request conflicts with an existing immutable record.',
          retryable: false,
          recovery_actions: ['resume_session', 'use_original_idempotency_key', 'manual_review'],
        },
        budget: { limit_bytes: 16384, used_bytes: 128 },
      },
      400,
    );
    const error = await sessionConfirm(PREVIEW, 'ui-confirm-key-3').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(OrchestrationError);
    const orchError = error as OrchestrationError;
    expect(orchError.code).toBe('idempotency_conflict');
    expect(orchError.category).toBe('conflict');
    expect(orchError.retryable).toBe(false);
    expect(orchError.recoveryActions).toContain('resume_session');
  });

  it('网络失败 → network_error 且 retryable', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('fetch failed'));
    vi.stubGlobal('fetch', fetchMock);
    const error = await sessionConfirm(PREVIEW, 'ui-confirm-key-4').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(OrchestrationError);
    expect((error as OrchestrationError).code).toBe('network_error');
    expect((error as OrchestrationError).retryable).toBe(true);
  });

  it('newIdempotencyKey 形态为 ui-<op>-<uuid>', () => {
    const key = newIdempotencyKey('decide');
    expect(key.startsWith('ui-decide-')).toBe(true);
    expect(key.length).toBeGreaterThan('ui-decide-'.length + 20);
  });

  it('deriveActorIdentityHash 派生恰好 64 位小写 hex（SubtleCrypto SHA-256）', async () => {
    // jsdom 无 SubtleCrypto：stub 32 字节 digest，验证 hex 转换、算法名与模块级缓存
    const digest = vi.fn().mockResolvedValue(new Uint8Array(32).fill(7).buffer);
    vi.stubGlobal('crypto', {
      subtle: { digest },
      randomUUID: () => '11111111-2222-4333-8444-555555555555',
    });
    vi.resetModules();
    const { deriveActorIdentityHash } = await import('../api/orchestration');
    const hash = await deriveActorIdentityHash();
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
    const [algorithm, data] = digest.mock.calls[0] as [string, Uint8Array];
    expect(algorithm).toBe('SHA-256');
    // seed 为本地随机串（cockpit-actor-<uuid>），不含真实用户标识
    expect(new TextDecoder().decode(data).startsWith('cockpit-actor-')).toBe(true);
    // 模块级缓存：同一运行期返回同一 hash（不再调 digest）
    expect(await deriveActorIdentityHash()).toBe(hash);
    expect(digest).toHaveBeenCalledTimes(1);
  });
});
