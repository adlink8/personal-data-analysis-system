import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiGet } from '../api/client';
import {
  OverviewEnvelopeSchema,
  SystemStatusEnvelopeSchema,
  externalDeltaEnvelopeSchema,
  personalStateEnvelopeSchema,
} from '../api/schemas';

/**
 * 契约测试（spec §17.2）：Zod schema 与投影信封一致。
 * 样例按后端契约（decision_cockpit_projection_v1）手工构造。
 */

// 完整 overview.get 样例：五节全部有数据
const FULL_OVERVIEW = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'overview.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00+00:00',
  snapshot_bindings: {
    personal: 'ps_20260719_a1b2c3d4e5f6',
    external: 'es_20260718_f6e5d4c3b2a1',
    serving: 'ss_20260719_001122334455',
  },
  freshness: { personal_as_of: '2026-07-19T07:30:00+00:00', knowledge_unit_count: 32181 },
  authorities: { personal: 'ok', decision: 'ok', proactive: 'ok', external: 'ok', knowledge: 'ok' },
  partial: false,
  limitations: [],
  data: {
    personal: {
      snapshot_id: 'ps_20260719_a1b2c3d4e5f6',
      as_of: '2026-07-19T07:30:00+00:00',
      total_available: 214,
      domains: { career: 40, project: 55, learning: 30, health: 12 },
      status_counts: { active: 180, superseded: 30, conflict: 4 },
      top_items: [
        {
          key: {
            assertion_kind: 'fact',
            subject: 'me',
            domain: 'career',
            scope: 'current',
            predicate: 'target_role',
          },
          status: 'active',
          confidence: 0.9,
          provenance_class: 'user_confirmed',
        },
      ],
    },
    decision: {
      total_available: 5,
      queue: { draft: 1, analyzing: 1, awaiting_confirmation: 2, executing: 1 },
      items: [
        {
          recommendation_id: 'rec_20260719_aaaa1111bbbb',
          domain: 'career',
          recommendation_kind: 'time_allocation',
          horizon: '8w',
          confidence: 0.72,
          confirmation_state: 'pending',
          action_state: 'not_started',
          expires_at: '2026-07-26T00:00:00+00:00',
        },
      ],
    },
    proactive: {
      total_available: 3,
      items: [
        {
          candidate_id: 'cand_20260719_cccc2222dddd',
          domains: ['career', 'learning'],
          importance: { level: 'high', score: 0.83 },
          candidate_class: 'opportunity',
          expires_at: '2026-07-21T00:00:00+00:00',
          reason_codes: ['deadline_approaching', 'goal_misaligned'],
        },
      ],
    },
    external: {
      snapshot_id: 'es_20260718_f6e5d4c3b2a1',
      sources_count: 6,
      facts_count: 128,
    },
    knowledge: {
      active_collection: 'ku_active_v3',
      unit_count: 32181,
      serving_snapshot_id: 'ss_20260719_001122334455',
    },
  },
};

// partial 样例：proactive Authority 故障 → 该节为 null，partial=true
const PARTIAL_OVERVIEW = {
  ...FULL_OVERVIEW,
  ok: true,
  authorities: { personal: 'ok', decision: 'ok', proactive: 'error', external: 'ok', knowledge: 'ok' },
  partial: true,
  limitations: ['主动提醒 Authority 暂不可用，候选列表未包含在本次投影中。'],
  data: {
    ...FULL_OVERVIEW.data,
    proactive: null,
  },
};

// 完整 system.status.get 样例
const FULL_SYSTEM_STATUS = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'system.status.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00+00:00',
  snapshot_bindings: {
    personal: 'ps_20260719_a1b2c3d4e5f6',
    external: 'es_20260718_f6e5d4c3b2a1',
    serving: 'ss_20260719_001122334455',
  },
  freshness: { personal_as_of: '2026-07-19T07:30:00+00:00', knowledge_unit_count: 32181 },
  authorities: { personal: 'ok', decision: 'ok', proactive: 'ok', external: 'ok', knowledge: 'ok' },
  partial: false,
  limitations: [],
  data: {
    ports: {
      rest: { up: true, port: 8000 },
      mcp: { up: true, port: 8789 },
      tunnel: { up: false, port: 8081 },
    },
    knowledge: {
      available: true,
      active_collection: 'ku_active_v3',
      unit_count: 32181,
      serving_snapshot_id: 'ss_20260719_001122334455',
      snapshot_hash: '9f86d081884c7d659a2feaa0c55ad015',
      snapshot_drift: false,
      pointer_exists: true,
    },
    authority_dbs: {
      external: { path: 'var/db/external.sqlite', exists: true, readable: true },
      decision_analysis: { path: 'var/db/decision_analysis.sqlite', exists: true, readable: true },
      project_pilot: { path: 'var/db/project_pilot.sqlite', exists: true, readable: false },
      recommendation_calibration: {
        path: 'var/db/recommendation_calibration.sqlite',
        exists: false,
        readable: false,
      },
    },
  },
};

describe('OverviewEnvelopeSchema', () => {
  it('解析完整 overview.get 样例并保留关键字段', () => {
    const parsed = OverviewEnvelopeSchema.parse(FULL_OVERVIEW);
    expect(parsed.schema_version).toBe('decision_cockpit_projection_v1');
    expect(parsed.operation).toBe('overview.get');
    expect(parsed.partial).toBe(false);
    expect(parsed.snapshot_bindings.personal).toBe('ps_20260719_a1b2c3d4e5f6');
    expect(parsed.data.personal?.total_available).toBe(214);
    expect(parsed.data.decision?.items[0]?.recommendation_id).toBe('rec_20260719_aaaa1111bbbb');
    expect(parsed.data.proactive?.items[0]?.reason_codes).toContain('deadline_approaching');
    expect(parsed.data.external?.facts_count).toBe(128);
    expect(parsed.data.knowledge?.unit_count).toBe(32181);
  });

  it('解析 partial 样例：某节为 null、limitations 透传', () => {
    const parsed = OverviewEnvelopeSchema.parse(PARTIAL_OVERVIEW);
    expect(parsed.partial).toBe(true);
    expect(parsed.authorities.proactive).toBe('error');
    expect(parsed.data.proactive).toBeNull();
    expect(parsed.limitations).toHaveLength(1);
    // 其余节不受影响
    expect(parsed.data.decision?.total_available).toBe(5);
  });

  it('容忍未知字段（passthrough）', () => {
    const withExtra = {
      ...FULL_OVERVIEW,
      future_field: { nested: true },
      data: { ...FULL_OVERVIEW.data, future_section: [1, 2, 3] },
    };
    expect(() => OverviewEnvelopeSchema.parse(withExtra)).not.toThrow();
  });

  // T-36-07：错误版本/错误 operation 不能被 parse 成有效 Cockpit 数据
  it('拒绝错误的 schema_version', () => {
    const wrongVersion = { ...FULL_OVERVIEW, schema_version: 'decision_cockpit_projection_v2' };
    expect(OverviewEnvelopeSchema.safeParse(wrongVersion).success).toBe(false);
  });

  it('拒绝错误的 operation（含被其他端点合法值冒充）', () => {
    const wrongOperation = { ...FULL_OVERVIEW, operation: 'system.status.get' };
    expect(OverviewEnvelopeSchema.safeParse(wrongOperation).success).toBe(false);
  });

  it('拒绝其他端点的合法 payload（system.status.get 不能当作 overview.get 渲染）', () => {
    expect(OverviewEnvelopeSchema.safeParse(FULL_SYSTEM_STATUS).success).toBe(false);
  });
});

describe('SystemStatusEnvelopeSchema', () => {
  it('解析完整 system.status.get 样例', () => {
    const parsed = SystemStatusEnvelopeSchema.parse(FULL_SYSTEM_STATUS);
    expect(parsed.operation).toBe('system.status.get');
    expect(parsed.data.ports.rest.up).toBe(true);
    expect(parsed.data.ports.tunnel.port).toBe(8081);
    expect(parsed.data.knowledge.snapshot_drift).toBe(false);
    expect(parsed.data.authority_dbs['project_pilot']?.readable).toBe(false);
    expect(parsed.data.authority_dbs['recommendation_calibration']?.exists).toBe(false);
  });

  it('拒绝结构错误的载荷（缺 ports）', () => {
    const broken = {
      ...FULL_SYSTEM_STATUS,
      data: { knowledge: FULL_SYSTEM_STATUS.data.knowledge },
    };
    expect(SystemStatusEnvelopeSchema.safeParse(broken).success).toBe(false);
  });

  it('拒绝错误的 schema_version', () => {
    const wrongVersion = { ...FULL_SYSTEM_STATUS, schema_version: 'decision_cockpit_projection_v2' };
    expect(SystemStatusEnvelopeSchema.safeParse(wrongVersion).success).toBe(false);
  });

  it('拒绝错误的 operation（含被其他端点合法值冒充）', () => {
    const wrongOperation = { ...FULL_SYSTEM_STATUS, operation: 'overview.get' };
    expect(SystemStatusEnvelopeSchema.safeParse(wrongOperation).success).toBe(false);
  });

  it('拒绝其他端点的合法 payload（overview.get 不能当作 system.status.get 渲染）', () => {
    expect(SystemStatusEnvelopeSchema.safeParse(FULL_OVERVIEW).success).toBe(false);
  });
});

/* ---------------- Phase 37：personal_state.get / external_delta.get ---------------- */

// 完整 personal_state.get 样例：八领域键恒在
const FULL_PERSONAL_STATE = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'personal_state.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00+00:00',
  snapshot_bindings: {
    personal: 'ps_20260719_a1b2c3d4e5f6',
    external: 'es_20260718_f6e5d4c3b2a1',
    serving: 'ss_20260719_001122334455',
  },
  freshness: { personal_as_of: '2026-07-19T07:30:00+00:00' },
  authorities: { personal: 'ok' },
  partial: false,
  limitations: [],
  data: {
    snapshot_id: 'ps_20260719_a1b2c3d4e5f6',
    as_of: '2026-07-19T07:30:00+00:00',
    total_available: 42,
    domains: {
      learning: {
        total: 8,
        by_kind: { goal: 2, constraint: 1, observation: 4, state: 1 },
        by_provenance: { fact: 3, observation: 4, inference: 1 },
        conflicts: 0,
        assertions: [],
      },
      career: {
        total: 12,
        by_kind: { goal: 3, constraint: 2, observation: 5, state: 2 },
        by_provenance: { fact: 6, observation: 4, inference: 2 },
        conflicts: 2,
        assertions: [
          {
            key: { assertion_kind: 'goal', subject: 'me', domain: 'career', scope: 'current', predicate: 'target_role' },
            provenance_class: 'fact',
            status: 'current',
            confidence: 0.9,
            current_assertion_id: 'pa_20260719_goal_career_01',
            evidence_count: 5,
          },
        ],
      },
      project: { total: 9, by_kind: { goal: 2, constraint: 2, observation: 4, state: 1 }, by_provenance: { fact: 4, observation: 4, inference: 1 }, conflicts: 0, assertions: [] },
      health: { total: 3, by_kind: { goal: 1, constraint: 0, observation: 2, state: 0 }, by_provenance: { fact: 1, observation: 2, inference: 0 }, conflicts: 0, assertions: [] },
      finance: { total: 4, by_kind: { goal: 1, constraint: 1, observation: 2, state: 0 }, by_provenance: { fact: 2, observation: 2, inference: 0 }, conflicts: 0, assertions: [] },
      relationship: { total: 2, by_kind: { goal: 0, constraint: 0, observation: 2, state: 0 }, by_provenance: { fact: 1, observation: 1, inference: 0 }, conflicts: 0, assertions: [] },
      time: { total: 3, by_kind: { goal: 1, constraint: 1, observation: 1, state: 0 }, by_provenance: { fact: 1, observation: 2, inference: 0 }, conflicts: 0, assertions: [] },
      energy: { total: 1, by_kind: { goal: 0, constraint: 0, observation: 1, state: 0 }, by_provenance: { fact: 0, observation: 1, inference: 0 }, conflicts: 0, assertions: [] },
    },
    lifecycle_counts: { current: 30, stale: 5, conflict: 2, resolved: 3, expired: 2 },
    recent_changes: [
      { change_type: 'supersede', domain: 'career', subject: 'me', observed_at: '2026-07-19T06:00:00+00:00', status: 'current' },
    ],
  },
};

// 完整 external_delta.get 样例
const FULL_EXTERNAL_DELTA = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'external_delta.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00+00:00',
  snapshot_bindings: {
    personal: 'ps_20260719_a1b2c3d4e5f6',
    external: 'es_20260718_f6e5d4c3b2a1',
    serving: 'ss_20260719_001122334455',
  },
  freshness: {},
  authorities: { external: 'ok' },
  partial: false,
  limitations: [],
  data: {
    snapshot: { snapshot_id: 'es_20260718_f6e5d4c3b2a1', generated_at: '2026-07-19T07:00:00+00:00' },
    sources: [{ source_id: 'src_mohrss_policy', name: '人社部政策发布', allowlisted: true }],
    facts: [
      {
        fact_id: 'ef_20260719_aaaa1111bbbb',
        fact_type: 'policy_change',
        region: 'CN',
        observed_at: '2026-07-19T06:30:00+00:00',
        valid_from: '2026-07-20T00:00:00+00:00',
        valid_to: '2026-12-31T00:00:00+00:00',
        source_id: 'src_mohrss_policy',
        source_quality: 'official',
        lifecycle: 'active',
        conflict: false,
      },
    ],
    delta: { new: ['ef_20260719_aaaa1111bbbb'], updated: [], expiring: [], conflicts: [] },
    counts: { sources: 1, facts: 1, conflicts: 0 },
  },
};

describe('personalStateEnvelopeSchema', () => {
  it('解析完整 personal_state.get 样例并保留八领域与断言字段', () => {
    const parsed = personalStateEnvelopeSchema.parse(FULL_PERSONAL_STATE);
    expect(parsed.operation).toBe('personal_state.get');
    expect(parsed.partial).toBe(false);
    expect(Object.keys(parsed.data?.domains ?? {})).toHaveLength(8);
    expect(parsed.data?.domains['career']?.conflicts).toBe(2);
    expect(parsed.data?.domains['career']?.assertions[0]?.key.predicate).toBe('target_role');
    expect(parsed.data?.domains['career']?.assertions[0]?.evidence_count).toBe(5);
    expect(parsed.data?.lifecycle_counts?.current).toBe(30);
    expect(parsed.data?.recent_changes[0]?.change_type).toBe('supersede');
  });

  it('解析 partial 样例：data 为 null、limitations 透传', () => {
    const partial = {
      ...FULL_PERSONAL_STATE,
      authorities: { personal: 'error' },
      partial: true,
      limitations: ['个人状态 Authority 暂不可用，本页数据未包含在本次投影中。'],
      data: null,
    };
    const parsed = personalStateEnvelopeSchema.parse(partial);
    expect(parsed.partial).toBe(true);
    expect(parsed.data).toBeNull();
    expect(parsed.authorities.personal).toBe('error');
    expect(parsed.limitations).toHaveLength(1);
  });

  it('容忍单领域失败（领域值为 null）与未知字段', () => {
    const degraded = {
      ...FULL_PERSONAL_STATE,
      future_field: 'tolerated',
      data: {
        ...FULL_PERSONAL_STATE.data,
        domains: { ...FULL_PERSONAL_STATE.data.domains, health: null },
      },
    };
    const parsed = personalStateEnvelopeSchema.parse(degraded);
    expect(parsed.data?.domains['health']).toBeNull();
    expect(parsed.data?.domains['career']?.total).toBe(12);
  });

  it('拒绝错误的 schema_version 或 operation', () => {
    expect(
      personalStateEnvelopeSchema.safeParse({
        ...FULL_PERSONAL_STATE,
        schema_version: 'decision_cockpit_projection_v2',
      }).success,
    ).toBe(false);
    expect(
      personalStateEnvelopeSchema.safeParse({ ...FULL_PERSONAL_STATE, operation: 'external_delta.get' }).success,
    ).toBe(false);
  });

  it('拒绝其他端点的合法 payload（external_delta.get 不能当作 personal_state.get 渲染）', () => {
    expect(personalStateEnvelopeSchema.safeParse(FULL_EXTERNAL_DELTA).success).toBe(false);
  });
});

describe('externalDeltaEnvelopeSchema', () => {
  it('解析完整 external_delta.get 样例', () => {
    const parsed = externalDeltaEnvelopeSchema.parse(FULL_EXTERNAL_DELTA);
    expect(parsed.operation).toBe('external_delta.get');
    expect(parsed.data?.snapshot?.snapshot_id).toBe('es_20260718_f6e5d4c3b2a1');
    expect(parsed.data?.facts[0]?.fact_type).toBe('policy_change');
    expect(parsed.data?.delta?.new).toContain('ef_20260719_aaaa1111bbbb');
    expect(parsed.data?.counts?.conflicts).toBe(0);
    expect(parsed.data?.sources[0]?.source_id).toBe('src_mohrss_policy');
  });

  it('宽松解析缺失字段的事实：缺 region/valid_to，valid_at 与未知字段透传', () => {
    const lenient = {
      ...FULL_EXTERNAL_DELTA,
      data: {
        ...FULL_EXTERNAL_DELTA.data,
        facts: [
          {
            fact_id: 'ef_20260718_cccc2222dddd',
            fact_type: 'job_market',
            observed_at: '2026-07-10T00:00:00+00:00',
            source_id: 'src_job_board_iot',
            // 后端可能用 valid_at 代替 valid_to；另带一个未来新增字段
            valid_at: '2026-09-30T00:00:00+00:00',
            future_nested: { score: 0.5 },
          },
        ],
      },
    };
    const parsed = externalDeltaEnvelopeSchema.parse(lenient);
    const fact = parsed.data?.facts[0];
    expect(fact?.fact_id).toBe('ef_20260718_cccc2222dddd');
    expect(fact?.region).toBeUndefined();
    expect(fact?.valid_to).toBeUndefined();
    expect(fact?.['valid_at']).toBe('2026-09-30T00:00:00+00:00');
    expect(fact?.['future_nested']).toEqual({ score: 0.5 });
  });

  it('解析 partial 样例：data 为 null、limitations 透传', () => {
    const partial = {
      ...FULL_EXTERNAL_DELTA,
      authorities: { external: 'error' },
      partial: true,
      limitations: ['外部环境 Authority 暂不可用，Delta 未包含在本次投影中。'],
      data: null,
    };
    const parsed = externalDeltaEnvelopeSchema.parse(partial);
    expect(parsed.partial).toBe(true);
    expect(parsed.data).toBeNull();
    expect(parsed.limitations[0]).toContain('外部环境');
  });

  it('拒绝错误的 schema_version 或 operation', () => {
    expect(
      externalDeltaEnvelopeSchema.safeParse({
        ...FULL_EXTERNAL_DELTA,
        schema_version: 'decision_cockpit_projection_v2',
      }).success,
    ).toBe(false);
    expect(
      externalDeltaEnvelopeSchema.safeParse({ ...FULL_EXTERNAL_DELTA, operation: 'personal_state.get' }).success,
    ).toBe(false);
  });

  it('拒绝其他端点的合法 payload（personal_state.get 不能当作 external_delta.get 渲染）', () => {
    expect(externalDeltaEnvelopeSchema.safeParse(FULL_PERSONAL_STATE).success).toBe(false);
  });
});

/* ---------------- apiGet（client.ts）：相对同源 + 安全错误映射（D-36-06） ---------------- */

/** 含 poisoned 片段的响应体：验证 ApiError 与 console 都不会把它们带出去。 */
const POISONED_BODY = {
  path: 'C:\\secret\\personal.sqlite',
  token: 'confirmation_token=abcd1234',
  hmac: 'HMAC-SHA256=deadbeef',
  detail: 'sk-test-poisoned-secret-value',
};

function mockFetch(impl: (path: string) => { ok: boolean; status: number; json: () => Promise<unknown> } | never) {
  const fetchMock = vi.fn(async (path: string) => impl(path));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function spyConsole() {
  return {
    log: vi.spyOn(console, 'log').mockImplementation(() => undefined),
    error: vi.spyOn(console, 'error').mockImplementation(() => undefined),
    warn: vi.spyOn(console, 'warn').mockImplementation(() => undefined),
  };
}

describe('apiGet（client.ts）：相对路径请求 + 安全 ApiError 映射', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('请求 URL 保持相对路径（不拼绝对 origin/host）', async () => {
    const fetchMock = mockFetch(() => ({ ok: true, status: 200, json: async () => FULL_OVERVIEW }));
    await apiGet('/ui/overview', OverviewEnvelopeSchema);
    const [calledPath] = fetchMock.mock.calls[0] as [string];
    expect(calledPath).toBe('/ui/overview');
    expect(calledPath.startsWith('/')).toBe(true);
    expect(calledPath).not.toMatch(/^https?:\/\//);
  });

  it('network 失败 → ApiError(network_error)，安全消息不含异常细节', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('poisoned network detail: ' + POISONED_BODY.detail));
    vi.stubGlobal('fetch', fetchMock);
    const consoleSpies = spyConsole();
    await expect(apiGet('/ui/overview', OverviewEnvelopeSchema)).rejects.toMatchObject({
      code: 'network_error',
    } satisfies Partial<ApiError>);
    try {
      await apiGet('/ui/overview', OverviewEnvelopeSchema);
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).message).not.toContain(POISONED_BODY.detail);
    }
    expect(consoleSpies.log).not.toHaveBeenCalled();
    expect(consoleSpies.error).not.toHaveBeenCalled();
    expect(consoleSpies.warn).not.toHaveBeenCalled();
  });

  it('非 2xx → ApiError(http_<status>)，响应 body 不进入 message/console', async () => {
    mockFetch(() => ({ ok: false, status: 503, json: async () => POISONED_BODY }));
    const consoleSpies = spyConsole();
    let caught: ApiError | undefined;
    try {
      await apiGet('/ui/overview', OverviewEnvelopeSchema);
    } catch (err) {
      caught = err as ApiError;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught?.code).toBe('http_503');
    for (const fragment of Object.values(POISONED_BODY)) {
      expect(caught?.message).not.toContain(fragment);
    }
    expect(consoleSpies.log).not.toHaveBeenCalled();
    expect(consoleSpies.error).not.toHaveBeenCalled();
    expect(consoleSpies.warn).not.toHaveBeenCalled();
  });

  it('响应不是合法 JSON → ApiError(invalid_json)', async () => {
    mockFetch(() => ({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError('Unexpected token');
      },
    }));
    await expect(apiGet('/ui/overview', OverviewEnvelopeSchema)).rejects.toMatchObject({
      code: 'invalid_json',
    } satisfies Partial<ApiError>);
  });

  it('Zod parse 失败（错误版本/operation/结构）→ ApiError(schema_mismatch)，不泄露 body 内容', async () => {
    mockFetch(() => ({
      ok: true,
      status: 200,
      json: async () => ({ ...POISONED_BODY, schema_version: 'wrong', operation: 'overview.get' }),
    }));
    const consoleSpies = spyConsole();
    let caught: ApiError | undefined;
    try {
      await apiGet('/ui/overview', OverviewEnvelopeSchema);
    } catch (err) {
      caught = err as ApiError;
    }
    expect(caught?.code).toBe('schema_mismatch');
    for (const fragment of Object.values(POISONED_BODY)) {
      expect(caught?.message).not.toContain(fragment);
    }
    expect(consoleSpies.log).not.toHaveBeenCalled();
    expect(consoleSpies.error).not.toHaveBeenCalled();
    expect(consoleSpies.warn).not.toHaveBeenCalled();
  });

  it('成功路径：解析后的数据经 Zod 校验，非 any（保留 operation/data 字段）', async () => {
    mockFetch(() => ({ ok: true, status: 200, json: async () => FULL_OVERVIEW }));
    const data = await apiGet('/ui/overview', OverviewEnvelopeSchema);
    expect(data.operation).toBe('overview.get');
    expect(data.data.personal?.total_available).toBe(214);
  });
});
