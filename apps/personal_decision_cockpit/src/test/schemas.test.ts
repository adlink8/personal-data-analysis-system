import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiGet } from '../api/client';
import {
  OverviewEnvelopeSchema,
  SystemStatusEnvelopeSchema,
  evidenceResolveEnvelopeSchema,
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
            current_value_checksum: 'csum_20260719_goal_career_01',
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
        fact_checksum: 'efc_20260719_aaaa1111bbbb',
        subject: 'mohrss_policy',
        predicate: 'social_insurance_rate_change',
        region: 'CN',
        valid_from: '2026-07-20T00:00:00+00:00',
        valid_to: '2026-12-31T00:00:00+00:00',
        source_quality: 0.95,
        fact_confidence: 0.9,
        source_ids: ['src_mohrss_policy'],
        lifecycle: 'current',
        conflict: false,
        freshness: { level: 'valid', reason: null },
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
    expect(parsed.data?.domains['career']?.assertions[0]?.current_value_checksum).toBe(
      'csum_20260719_goal_career_01',
    );
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

  it('断言缺少 current_value_checksum 时整体 parse 失败（fail closed，EVID-01 稳定引用三元组）', () => {
    const missingChecksum = {
      ...FULL_PERSONAL_STATE,
      data: {
        ...FULL_PERSONAL_STATE.data,
        domains: {
          ...FULL_PERSONAL_STATE.data.domains,
          career: {
            ...FULL_PERSONAL_STATE.data.domains.career,
            assertions: [
              (() => {
                const { current_value_checksum: _c, ...rest } =
                  FULL_PERSONAL_STATE.data.domains.career.assertions[0];
                return rest;
              })(),
            ],
          },
        },
      },
    };
    expect(personalStateEnvelopeSchema.safeParse(missingChecksum).success).toBe(false);
  });
});

describe('externalDeltaEnvelopeSchema', () => {
  it('解析完整 external_delta.get 样例', () => {
    const parsed = externalDeltaEnvelopeSchema.parse(FULL_EXTERNAL_DELTA);
    expect(parsed.operation).toBe('external_delta.get');
    expect(parsed.data?.snapshot?.snapshot_id).toBe('es_20260718_f6e5d4c3b2a1');
    expect(parsed.data?.facts[0]?.subject).toBe('mohrss_policy');
    expect(parsed.data?.facts[0]?.predicate).toBe('social_insurance_rate_change');
    expect(parsed.data?.facts[0]?.fact_checksum).toBe('efc_20260719_aaaa1111bbbb');
    expect(parsed.data?.facts[0]?.freshness?.level).toBe('valid');
    expect(parsed.data?.delta?.new).toContain('ef_20260719_aaaa1111bbbb');
    expect(parsed.data?.counts?.conflicts).toBe(0);
    expect(parsed.data?.sources[0]?.source_id).toBe('src_mohrss_policy');
  });

  it('宽松解析：canonical 字段可为 null、source_ids/freshness 缺省，未知字段透传', () => {
    const lenient = {
      ...FULL_EXTERNAL_DELTA,
      data: {
        ...FULL_EXTERNAL_DELTA.data,
        facts: [
          {
            fact_id: 'ef_20260718_cccc2222dddd',
            fact_checksum: 'efc_20260718_cccc2222dddd',
            subject: 'nodejs',
            predicate: 'release.lts',
            region: 'global',
            valid_from: '2026-07-10T00:00:00+00:00',
            valid_to: null,
            source_quality: 0.99,
            fact_confidence: 0.99,
            lifecycle: 'current',
            conflict: false,
            // source_ids/freshness 未提供 → 走 default([]/null)；未知字段透传
            future_nested: { score: 0.5 },
          },
        ],
      },
    };
    const parsed = externalDeltaEnvelopeSchema.parse(lenient);
    const fact = parsed.data?.facts[0];
    expect(fact?.fact_id).toBe('ef_20260718_cccc2222dddd');
    expect(fact?.valid_to).toBeNull();
    expect(fact?.source_ids).toEqual([]);
    expect(fact?.freshness).toBeNull();
    expect(fact?.['future_nested']).toEqual({ score: 0.5 });
  });

  it('External fact 缺少 canonical 字段（subject）时整体 parse 失败（fail closed，D-37-02）', () => {
    const malformed = {
      ...FULL_EXTERNAL_DELTA,
      data: {
        ...FULL_EXTERNAL_DELTA.data,
        facts: [
          (() => {
            const { subject: _subject, ...rest } = FULL_EXTERNAL_DELTA.data.facts[0];
            return rest;
          })(),
        ],
      },
    };
    expect(externalDeltaEnvelopeSchema.safeParse(malformed).success).toBe(false);
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

/* ---------------- evidence_resolve.get（Phase 37：EVID-01） ---------------- */

const EVIDENCE_ENVELOPE_BASE = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'evidence_resolve.get',
  ok: true,
  generated_at: '2026-07-26T08:00:00+00:00',
  snapshot_bindings: { personal: null, external: 'exs_20260718_aaaa', serving: null },
  freshness: {},
  authorities: { evidence: 'ok' },
  partial: false,
  limitations: ['allowlisted public metadata only', 'external facts never become personal facts'],
};

// 成功路径：external_fact
const OK_EXTERNAL_FACT_RESOLVE = {
  ...EVIDENCE_ENVELOPE_BASE,
  data: {
    status: 'ok',
    reference: {
      subject_type: 'external_fact',
      stable_id: 'ef_20260718_aaaa1111bbbb',
      snapshot_id: 'exs_20260718_aaaa',
      checksum: 'efc_20260718_aaaa1111bbbb',
    },
    result: {
      subject_type: 'external_fact',
      stable_id: 'ef_20260718_aaaa1111bbbb',
      snapshot_id: 'exs_20260718_aaaa',
      checksum: 'efc_20260718_aaaa1111bbbb',
      subject: 'nodejs',
      predicate: 'release.lts',
      region: 'global',
      valid_from: '2026-01-13T00:00:00+00:00',
      valid_to: null,
      source_quality: 0.99,
      fact_confidence: 0.99,
      lifecycle: 'current',
    },
    next_actions: ['inspect another fact', 'inspect the active snapshot'],
  },
};

// 成功路径：personal_state（authorities/snapshot_bindings 与 subject_type 对应轴一致）
const OK_PERSONAL_STATE_RESOLVE = {
  ...EVIDENCE_ENVELOPE_BASE,
  snapshot_bindings: { personal: 'ss_20260718_aaaa', external: null, serving: null },
  limitations: [],
  data: {
    status: 'ok',
    reference: {
      subject_type: 'personal_state',
      stable_id: 'psa_20260718_aaaa',
      snapshot_id: 'ss_20260718_aaaa',
      checksum: 'csum_20260718_aaaa',
      assertion_kind: 'goal',
      subject: 'user',
      domain: 'career',
      scope: 'current',
      predicate: 'target_role',
    },
    result: {
      subject_type: 'personal_state',
      stable_id: 'psa_20260718_aaaa',
      snapshot_id: 'ss_20260718_aaaa',
      checksum: 'csum_20260718_aaaa',
      key: {
        assertion_kind: 'goal', subject: 'user', domain: 'career',
        scope: 'current', predicate: 'target_role',
      },
      record_lifecycle: 'current',
      provenance_class: 'fact',
      confidence: 0.9,
      as_of: '2026-07-18T00:00:00+00:00',
      evidence: [
        { ref: 'ev_aaaa', artifact_type: 'message', status: 'ok', eligible: true, privacy_class: 'metadata_only' },
      ],
      uncertainty: [],
    },
    next_actions: [],
  },
};

// mismatch：篡改后的 checksum 已不匹配当前记录，result 恒为 null（不得回退到"最新记录"）
const MISMATCH_EXTERNAL_FACT_RESOLVE = {
  ...EVIDENCE_ENVELOPE_BASE,
  limitations: [],
  data: {
    status: 'mismatch',
    reference: {
      subject_type: 'external_fact',
      stable_id: 'ef_20260718_aaaa1111bbbb',
      snapshot_id: 'exs_20260718_aaaa',
      checksum: 'stale_checksum_deadbeef',
    },
    result: null,
    next_actions: ['刷新 External 页面后重新下钻'],
  },
};

// abstain：personal_state evidence 暂不满足可用性判定，仍返回可用元数据（result 非 null）
const ABSTAIN_PERSONAL_STATE_RESOLVE = {
  ...EVIDENCE_ENVELOPE_BASE,
  snapshot_bindings: { personal: 'ss_20260718_aaaa', external: null, serving: null },
  limitations: [],
  data: {
    status: 'abstain',
    reference: OK_PERSONAL_STATE_RESOLVE.data.reference,
    result: {
      ...OK_PERSONAL_STATE_RESOLVE.data.result,
      uncertainty: ['evidence_unavailable_or_ineligible'],
    },
    next_actions: ['evidence 暂不满足可用性判定，可稍后重试或改看其它断言'],
  },
};

// authority_unavailable：单 authority 意外故障，隔离为 partial（不是异常穿透/500）
const AUTHORITY_UNAVAILABLE_DECISION_RESOLVE = {
  ...EVIDENCE_ENVELOPE_BASE,
  authorities: { evidence: 'error' },
  partial: true,
  limitations: ['decision explain 读取失败(authority_read_failed)'],
  data: {
    status: 'authority_unavailable',
    reference: {
      subject_type: 'decision',
      stable_id: 'drec_20260718_aaaa',
      snapshot_id: 'ss_20260718_aaaa',
      checksum: 'csum_20260718_aaaa',
    },
    result: null,
    next_actions: ['稍后重试，或返回状态/External/决策页重新进入下钻'],
  },
};

describe('evidenceResolveEnvelopeSchema', () => {
  it('解析 external_fact 成功样例：result 携带 canonical 字段，不含 raw value', () => {
    const parsed = evidenceResolveEnvelopeSchema.parse(OK_EXTERNAL_FACT_RESOLVE);
    expect(parsed.operation).toBe('evidence_resolve.get');
    expect(parsed.data.status).toBe('ok');
    expect(parsed.data.result?.subject).toBe('nodejs');
    expect(parsed.data.result?.checksum).toBe('efc_20260718_aaaa1111bbbb');
    expect((parsed.data.result as Record<string, unknown>)?.['value']).toBeUndefined();
  });

  it('解析 personal_state 成功样例：reference 携带完整 state key，evidence 只有元数据字段', () => {
    const parsed = evidenceResolveEnvelopeSchema.parse(OK_PERSONAL_STATE_RESOLVE);
    expect(parsed.data.reference.subject_type).toBe('personal_state');
    expect((parsed.data.reference as Record<string, unknown>)['predicate']).toBe('target_role');
    expect(parsed.data.result?.evidence[0]).toEqual({
      ref: 'ev_aaaa', artifact_type: 'message', status: 'ok', eligible: true, privacy_class: 'metadata_only',
    });
  });

  it('解析 mismatch 样例：result 恒为 null，不回退到最新记录', () => {
    const parsed = evidenceResolveEnvelopeSchema.parse(MISMATCH_EXTERNAL_FACT_RESOLVE);
    expect(parsed.data.status).toBe('mismatch');
    expect(parsed.data.result).toBeNull();
    expect(parsed.data.next_actions.length).toBeGreaterThan(0);
  });

  it('解析 abstain 样例：仍返回可用元数据（result 非 null）与 uncertainty', () => {
    const parsed = evidenceResolveEnvelopeSchema.parse(ABSTAIN_PERSONAL_STATE_RESOLVE);
    expect(parsed.data.status).toBe('abstain');
    expect(parsed.data.result).not.toBeNull();
    expect(parsed.data.result?.uncertainty).toContain('evidence_unavailable_or_ineligible');
  });

  it('解析 authority_unavailable 样例：partial=true 且 authorities.evidence=error', () => {
    const parsed = evidenceResolveEnvelopeSchema.parse(AUTHORITY_UNAVAILABLE_DECISION_RESOLVE);
    expect(parsed.data.status).toBe('authority_unavailable');
    expect(parsed.partial).toBe(true);
    expect(parsed.authorities.evidence).toBe('error');
    expect(parsed.data.result).toBeNull();
  });

  it('拒绝未知 status（不在固定词表内的值不能被当作合法降级渲染）', () => {
    const bogus = {
      ...OK_EXTERNAL_FACT_RESOLVE,
      data: { ...OK_EXTERNAL_FACT_RESOLVE.data, status: 'made_up_status' },
    };
    expect(evidenceResolveEnvelopeSchema.safeParse(bogus).success).toBe(false);
  });

  it('拒绝错误的 schema_version 或 operation', () => {
    expect(
      evidenceResolveEnvelopeSchema.safeParse({
        ...OK_EXTERNAL_FACT_RESOLVE,
        schema_version: 'decision_cockpit_projection_v2',
      }).success,
    ).toBe(false);
    expect(
      evidenceResolveEnvelopeSchema.safeParse({ ...OK_EXTERNAL_FACT_RESOLVE, operation: 'external_delta.get' })
        .success,
    ).toBe(false);
  });

  it('拒绝其他端点的合法 payload（external_delta.get 不能当作 evidence_resolve.get 渲染）', () => {
    expect(evidenceResolveEnvelopeSchema.safeParse(FULL_EXTERNAL_DELTA).success).toBe(false);
  });
});
