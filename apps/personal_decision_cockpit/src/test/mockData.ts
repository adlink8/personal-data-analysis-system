/**
 * Phase 37 页面测试样例：结构与 decision_cockpit_projection_v1 信封一致，数据为手工虚构。
 * 仅用于组件渲染测试（mock hooks 返回值），不经过网络。
 */

export const PERSONAL_STATE_ENVELOPE = {
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
            current_value_checksum: 'c'.repeat(64),
            evidence_count: 5,
          },
          {
            key: { assertion_kind: 'observation', subject: 'me', domain: 'career', scope: 'current', predicate: 'weekly_hours' },
            provenance_class: 'observation',
            status: 'stale',
            confidence: 'medium',
            current_assertion_id: 'pa_20260710_obs_career_02',
            // 有意省略 current_value_checksum：验证缺失稳定引用三元组时不渲染"查看证据"（不构造伪 evidence）
            current_value_checksum: null,
            evidence_count: 2,
          },
          {
            key: { assertion_kind: 'state', subject: 'me', domain: 'career', scope: 'current', predicate: 'job_search_window' },
            provenance_class: 'inference',
            status: 'conflict',
            confidence: null,
            current_assertion_id: 'pa_20260718_inf_career_03',
            current_value_checksum: 'e'.repeat(64),
            evidence_count: 3,
          },
        ],
      },
      project: {
        total: 9,
        by_kind: { goal: 2, constraint: 2, observation: 4, state: 1 },
        by_provenance: { fact: 4, observation: 4, inference: 1 },
        conflicts: 0,
        assertions: [],
      },
      health: {
        total: 3,
        by_kind: { goal: 1, constraint: 0, observation: 2, state: 0 },
        by_provenance: { fact: 1, observation: 2, inference: 0 },
        conflicts: 0,
        assertions: [],
      },
      finance: {
        total: 4,
        by_kind: { goal: 1, constraint: 1, observation: 2, state: 0 },
        by_provenance: { fact: 2, observation: 2, inference: 0 },
        conflicts: 0,
        assertions: [],
      },
      relationship: {
        total: 2,
        by_kind: { goal: 0, constraint: 0, observation: 2, state: 0 },
        by_provenance: { fact: 1, observation: 1, inference: 0 },
        conflicts: 0,
        assertions: [],
      },
      time: {
        total: 3,
        by_kind: { goal: 1, constraint: 1, observation: 1, state: 0 },
        by_provenance: { fact: 1, observation: 2, inference: 0 },
        conflicts: 0,
        assertions: [],
      },
      energy: {
        total: 1,
        by_kind: { goal: 0, constraint: 0, observation: 1, state: 0 },
        by_provenance: { fact: 0, observation: 1, inference: 0 },
        conflicts: 0,
        assertions: [],
      },
    },
    lifecycle_counts: { current: 30, stale: 5, conflict: 2, resolved: 3, expired: 2 },
    recent_changes: [
      { change_type: 'supersede', domain: 'career', subject: 'me', observed_at: '2026-07-19T06:00:00+00:00', status: 'current' },
      { change_type: 'new_assertion', domain: 'learning', subject: 'me', observed_at: '2026-07-18T21:00:00+00:00', status: 'stale' },
    ],
  },
};

export const EXTERNAL_DELTA_ENVELOPE = {
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
    sources: [
      { source_id: 'src_mohrss_policy', name: '人社部政策发布', allowlisted: true },
      { source_id: 'src_job_board_iot' },
    ],
    // canonical External fact DTO（Phase 37：D-37-02）：subject/predicate 命名轴 +
    // 固定 来源/地区/有效期/quality/confidence/lifecycle/conflict/freshness 字段
    facts: [
      {
        fact_id: 'ef_20260719_aaaa1111bbbb',
        fact_checksum: 'efc_20260719_aaaa1111bbbb',
        subject: 'mohrss_policy',
        predicate: 'policy_change',
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
      {
        // 宽松样例：缺 region / valid_from / valid_to / source_quality / lifecycle / freshness，页面应显式"未提供"
        fact_id: 'ef_20260718_cccc2222dddd',
        fact_checksum: 'efc_20260718_cccc2222dddd',
        subject: 'job_board_iot',
        predicate: 'job_market',
        source_ids: ['src_job_board_iot'],
        conflict: false,
      },
      {
        fact_id: 'ef_20260717_eeee3333ffff',
        fact_checksum: 'efc_20260717_eeee3333ffff',
        subject: 'job_board_iot',
        predicate: 'job_market',
        region: 'CN-Shanghai',
        valid_from: '2026-07-17T00:00:00+00:00',
        valid_to: '2026-09-30T00:00:00+00:00',
        source_quality: 0.8,
        fact_confidence: 0.75,
        source_ids: ['src_job_board_iot'],
        lifecycle: 'current',
        conflict: true,
        freshness: { level: 'expiring_soon', reason: 'valid_to 距 snapshot 参考时间不足 7 天' },
      },
    ],
    delta: {
      new: ['ef_20260719_aaaa1111bbbb'],
      updated: [],
      expiring: ['ef_20260718_cccc2222dddd'],
      conflicts: ['ef_20260717_eeee3333ffff'],
    },
    counts: { sources: 2, facts: 3, conflicts: 1 },
  },
};

/* ---------------- Phase 38：decision_queue.get / decision_workspace.get ---------------- */

const SNAPSHOT_BINDINGS = {
  personal: 'ps_20260719_a1b2c3d4e5f6',
  external: 'es_20260718_f6e5d4c3b2a1',
  serving: 'ss_20260719_001122334455',
};

// 六组各 1 条卡片（分组由后端投影给出，前端不重算）
export const DECISION_QUEUE_ENVELOPE = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'decision_queue.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00Z',
  snapshot_bindings: { personal: null, external: null, serving: null },
  freshness: { personal_as_of: null, knowledge_unit_count: null, generated_at: '2026-07-19T08:00:00Z' },
  authorities: { decision: 'ok' },
  partial: false,
  limitations: [],
  data: {
    total_available: 6,
    stage_counts: {
      needs_attention: 1,
      awaiting_confirmation: 1,
      in_progress: 1,
      awaiting_outcome: 1,
      completed: 1,
      closed: 1,
    },
    stages: {
      needs_attention: [
        {
          recommendation_id: 'rec_attn_001',
          domain: 'career',
          recommendation_kind: 'time_allocation',
          horizon: '8w',
          confidence: 0.72,
          confirmation_state: 'proposed',
          action_state: null,
          expires_at: '2026-07-18T00:00:00Z',
          current_sequence: 1,
          snapshot_id: SNAPSHOT_BINDINGS.personal,
        },
      ],
      awaiting_confirmation: [
        {
          recommendation_id: 'rec_wait_002',
          domain: 'project',
          recommendation_kind: 'phase_planning',
          horizon: '4w',
          confidence: 'medium',
          confirmation_state: 'proposed',
          action_state: null,
          expires_at: '2099-01-01T00:00:00Z',
          current_sequence: 1,
          snapshot_id: SNAPSHOT_BINDINGS.personal,
        },
      ],
      in_progress: [
        {
          recommendation_id: 'rec_prog_003',
          domain: 'learning',
          recommendation_kind: 'habit_change',
          horizon: '12w',
          confidence: 0.66,
          confirmation_state: 'accepted',
          action_state: 'started',
          expires_at: '2099-01-01T00:00:00Z',
          current_sequence: 4,
          snapshot_id: SNAPSHOT_BINDINGS.personal,
        },
      ],
      awaiting_outcome: [
        {
          recommendation_id: 'rec_outc_004',
          domain: 'project',
          recommendation_kind: 'scope_control',
          horizon: '2w',
          confidence: 0.81,
          confirmation_state: 'accepted',
          action_state: 'completed',
          expires_at: '2099-01-01T00:00:00Z',
          current_sequence: 6,
          snapshot_id: SNAPSHOT_BINDINGS.personal,
        },
      ],
      completed: [
        {
          recommendation_id: 'rec_done_005',
          domain: 'time',
          recommendation_kind: 'schedule',
          horizon: '1w',
          confidence: 0.9,
          confirmation_state: 'accepted',
          action_state: 'completed',
          expires_at: '2026-06-01T00:00:00Z',
          current_sequence: 8,
          snapshot_id: SNAPSHOT_BINDINGS.personal,
        },
      ],
      closed: [
        {
          recommendation_id: 'rec_clsd_006',
          domain: 'career',
          recommendation_kind: 'job_change',
          horizon: '26w',
          confidence: 0.4,
          confirmation_state: 'rejected',
          action_state: 'not_taken',
          expires_at: '2026-05-01T00:00:00Z',
          current_sequence: 3,
          snapshot_id: SNAPSHOT_BINDINGS.personal,
        },
      ],
    },
  },
};

export const DECISION_QUEUE_EMPTY_ENVELOPE = {
  ...DECISION_QUEUE_ENVELOPE,
  data: {
    total_available: 0,
    stage_counts: {
      needs_attention: 0,
      awaiting_confirmation: 0,
      in_progress: 0,
      awaiting_outcome: 0,
      completed: 0,
      closed: 0,
    },
    stages: {
      needs_attention: [],
      awaiting_confirmation: [],
      in_progress: [],
      awaiting_outcome: [],
      completed: [],
      closed: [],
    },
  },
};

// 完整工作区：recommendation 全字段 + support 两条 + history 三条 + outcomes/effectiveness 各一条
export const DECISION_WORKSPACE_ENVELOPE = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'decision_workspace.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00Z',
  snapshot_bindings: { personal: SNAPSHOT_BINDINGS.personal, external: null, serving: null },
  freshness: { personal_as_of: null, knowledge_unit_count: null, generated_at: '2026-07-19T08:00:00Z' },
  authorities: { recommendation: 'ok', history: 'ok', outcomes: 'ok', effectiveness: 'ok' },
  partial: false,
  limitations: ['recommendations.history 不暴露事件时间戳/status,history 仅含链上校验字段'],
  data: {
    recommendation: {
      recommendation_id: 'rec_attn_001',
      recommendation_checksum: 'c'.repeat(64),
      cognitive_type: 'recommendation',
      run_id: 'run_20260719_dddd4444eeee',
      source_run_id: 'ar_20260719_source0001ff',
      snapshot_id: SNAPSHOT_BINDINGS.personal,
      policy_id: 'policy_time_allocation_v2',
      subject: 'me',
      // Phase 38：domain=project 才是唯一开放受控会话入口的样例（D-38-03），
      // 与其余 stage 卡片示例（career/learning 等）区分：本 fixture 用于演示
      // "完整 DEC-01 比较 + 可发起会话" 的合格样例。
      domain: 'project',
      scope: 'current',
      recommendation_kind: 'time_allocation',
      // DEC-01（Phase 38）：target/expected_benefit/costs_constraints/assumptions/
      // contraindications 锚定真实 intelligence/decision/schema.py::Recommendation
      // 字段名，用于演示"投影补齐后"的完整决策比较；当前真实 recommendations.get
      // 尚未透出这些字段（见 schemas.ts 注释），故另在下方提供不含这五个字段的
      // DECISION_WORKSPACE_FIELDS_MISSING_ENVELOPE 变体演示真实现状。
      target: '把英语学习、项目投入与求职准备的每周工时重新分配到未来 8 周窗口内',
      expected_benefit: '在不影响项目交付的前提下为求职留出可持续的准备时间',
      costs_constraints: ['每周总投入不超过 30 小时', '项目里程碑不可推迟', '英语学习每周至少 5 小时'],
      assumptions: ['未来 8 周项目范围不再扩大', '当前求职市场窗口保持开放'],
      contraindications: ['若项目风险评级上升为 high，本建议应重新评估后再确认'],
      horizon: '8w',
      confidence: 0.72,
      uncertainty: 'medium',
      // 固定为远期日期，避免 fixture 随真实时钟推移而"过期"（原值为写死的过去
      // 相对日期，会在系统时钟越过该日期后使 Task 3 的到期门禁样例意外触发）。
      expires_at: '2099-01-01T00:00:00Z',
      rationale_codes: ['goal_misaligned', 'deadline_approaching'],
      support: [
        {
          authority_id: 'a.personal_change',
          record_id: 'pa_20260719_goal_career_01',
          source_run_id: 'ar_20260719_source0001ff',
          cognitive_type: 'fact',
          provenance_class: 'fact',
          evidence_status: 'verified',
          record_checksum: 'd'.repeat(64),
        },
        {
          authority_id: 'a.personal_change',
          record_id: 'pa_20260710_obs_career_02',
          source_run_id: 'ar_20260719_source0001ff',
          cognitive_type: 'observation',
          provenance_class: 'observation',
          evidence_status: 'current',
          record_checksum: 'e'.repeat(64),
        },
      ],
      confirmation_state: 'proposed',
      action_state: null,
      current_sequence: 3,
    },
    history: [
      {
        event_id: 'evt_20260719_0001aaaa0001',
        sequence: 1,
        event_type: 'recommendation_proposed',
        typed_record_id: 'rec_attn_001',
        previous_event_checksum: 'GENESIS',
        payload_checksum: 'a'.repeat(64),
      },
      {
        event_id: 'evt_20260719_0002bbbb0002',
        sequence: 2,
        event_type: 'support_attached',
        typed_record_id: 'pa_20260719_goal_career_01',
        previous_event_checksum: 'a'.repeat(64),
        payload_checksum: 'b'.repeat(64),
      },
      {
        event_id: 'evt_20260719_0003cccc0003',
        sequence: 3,
        event_type: 'recommendation_refreshed',
        typed_record_id: 'rec_attn_001',
        previous_event_checksum: 'b'.repeat(64),
        payload_checksum: 'c'.repeat(64),
      },
    ],
    outcomes: [
      {
        outcome_id: 'out_20260719_0001dddd',
        recommendation_id: 'rec_attn_001',
        payload_checksum: 'f'.repeat(64),
        record_type: 'outcome',
        cognitive_type: 'observation',
        causal_claim: false,
        metric: 12.5,
        unit: 'hours',
        adherence_status: 'met',
        verdict: 'met',
        uncertainty: 'low',
      },
    ],
    effectiveness: [
      {
        assessment_id: 'eff_20260719_0001eeee',
        recommendation_id: 'rec_attn_001',
        payload_checksum: '0'.repeat(64),
        record_type: 'effectiveness',
        cognitive_type: 'inference',
        causal_claim: false,
        metric: 'weekly_hours',
        unit: 'hours',
        rule_id: 'r_weekly_hours_delta',
        rule_version: '1.2',
        verdict: 'inconclusive',
        uncertainty: 'high',
      },
    ],
    linked_analysis_run_id: 'ar_20260719_source0001ff',
  },
};

/**
 * Phase 38 Task 3（fail-closed 资格门）样例集：每个变体只改动触发单一阻断
 * 原因所需的字段，其余保持 DECISION_WORKSPACE_ENVELOPE 的合格基线，便于测试
 * 逐条断言只有对应原因出现，不互相污染。
 */

// 真实现状样例：recommendations.get 当前不透出 target/expected_benefit/
// costs_constraints/assumptions/contraindications（见 schemas.ts 注释），
// 五个字段一律缺失，页面应对 DEC-01 对应行显式渲染"未提供"而非留空或崩溃。
export const DECISION_WORKSPACE_FIELDS_MISSING_ENVELOPE = {
  ...DECISION_WORKSPACE_ENVELOPE,
  data: {
    ...DECISION_WORKSPACE_ENVELOPE.data,
    recommendation: {
      ...DECISION_WORKSPACE_ENVELOPE.data.recommendation,
      target: null,
      expected_benefit: null,
      costs_constraints: [],
      assumptions: [],
      contraindications: [],
    },
  },
};

// 到期样例：expires_at 已过 → 资格门必须阻断，不允许发起受控会话
export const DECISION_WORKSPACE_EXPIRED_ENVELOPE = {
  ...DECISION_WORKSPACE_ENVELOPE,
  data: {
    ...DECISION_WORKSPACE_ENVELOPE.data,
    recommendation: { ...DECISION_WORKSPACE_ENVELOPE.data.recommendation, expires_at: '2020-01-01T00:00:00Z' },
  },
};

// 已关闭样例：confirmation_state=rejected → 资格门必须阻断
export const DECISION_WORKSPACE_CLOSED_ENVELOPE = {
  ...DECISION_WORKSPACE_ENVELOPE,
  data: {
    ...DECISION_WORKSPACE_ENVELOPE.data,
    recommendation: { ...DECISION_WORKSPACE_ENVELOPE.data.recommendation, confirmation_state: 'rejected' },
  },
};

// 非 project 域样例：Phase 38 只开放 project 域的受控会话（D-38-03）
export const DECISION_WORKSPACE_NON_PROJECT_ENVELOPE = {
  ...DECISION_WORKSPACE_ENVELOPE,
  data: {
    ...DECISION_WORKSPACE_ENVELOPE.data,
    recommendation: { ...DECISION_WORKSPACE_ENVELOPE.data.recommendation, domain: 'career' },
  },
};

// 证据不足样例：support 为空 → 资格门必须阻断（与既有"信息不足"提示一致）
export const DECISION_WORKSPACE_NO_EVIDENCE_ENVELOPE = {
  ...DECISION_WORKSPACE_ENVELOPE,
  data: {
    ...DECISION_WORKSPACE_ENVELOPE.data,
    recommendation: { ...DECISION_WORKSPACE_ENVELOPE.data.recommendation, support: [] },
  },
};

// 缺少 Personal snapshot 绑定样例：snapshot_id 缺失 → 资格门必须阻断
export const DECISION_WORKSPACE_UNBOUND_ENVELOPE = {
  ...DECISION_WORKSPACE_ENVELOPE,
  data: {
    ...DECISION_WORKSPACE_ENVELOPE.data,
    recommendation: { ...DECISION_WORKSPACE_ENVELOPE.data.recommendation, snapshot_id: null },
  },
};

// 投影部分可用样例：envelope.partial=true（如 history 节失败）→ 资格门必须阻断
export const DECISION_WORKSPACE_PARTIAL_ENVELOPE = {
  ...DECISION_WORKSPACE_ENVELOPE,
  authorities: { ...DECISION_WORKSPACE_ENVELOPE.authorities, history: 'error' },
  partial: true,
  limitations: [...DECISION_WORKSPACE_ENVELOPE.limitations, 'history Authority 本次未返回数据。'],
};

/* ---------------- Phase 39：actions_recent.get / proactive_summary.get / calibration_overview.get ---------------- */

// 两条推荐：一条六阶段全部达成（含 outcome/effectiveness），一条停在 action_complete 等待结果
export const ACTIONS_RECENT_ENVELOPE = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'actions_recent.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00Z',
  snapshot_bindings: { personal: SNAPSHOT_BINDINGS.personal, external: null, serving: null },
  freshness: {},
  authorities: { decision: 'ok', calibration: 'ok' },
  partial: false,
  limitations: [],
  data: {
    total_available: 2,
    shown: 2,
    with_outcome: 1,
    awaiting_outcome: 1,
    items: [
      {
        recommendation_id: 'rec_done_005',
        domain: 'time',
        recommendation_kind: 'schedule',
        confirmation_state: 'accepted',
        action_state: 'completed',
        expires_at: '2026-06-01T00:00:00Z',
        timeline: [
          { stage: 'recommendation', present: true, event_id: 'evt_20260601_0001aaaa0001', sequence: 1, checksum: 'a'.repeat(64) },
          { stage: 'decision', present: true, event_id: 'evt_20260601_0002bbbb0002', sequence: 2, checksum: 'b'.repeat(64) },
          { stage: 'action_start', present: true, event_id: 'evt_20260601_0003cccc0003', sequence: 3, checksum: 'c'.repeat(64) },
          { stage: 'action_complete', present: true, event_id: 'evt_20260601_0004dddd0004', sequence: 4, checksum: 'd'.repeat(64) },
          { stage: 'outcome', present: true, event_id: 'evt_20260601_0005eeee0005', sequence: 5, checksum: 'e'.repeat(64) },
          { stage: 'effectiveness', present: true, event_id: 'evt_20260601_0006ffff0006', sequence: 6, checksum: 'f'.repeat(64) },
        ],
        outcomes: [
          {
            outcome_id: 'out_20260601_0001gggg',
            completion: 'complete',
            observed_value: 12.5,
            actual_time_minutes: 45,
            actual_cost: 0,
            satisfaction: 0.8,
            side_effects: ['轻微加班'],
            source: 'manual_log',
            observed_at: '2026-06-08T10:00:00Z',
            causal_claim: false,
            verdict: 'met',
          },
        ],
        effectiveness: [
          {
            assessment_id: 'eff_20260608_0001hhhh',
            verdict: 'inconclusive',
            causal_claim: false,
            rule_id: 'r_weekly_hours_delta',
            rule_version: '1.2',
          },
        ],
      },
      {
        recommendation_id: 'rec_outc_004',
        domain: 'project',
        recommendation_kind: 'scope_control',
        confirmation_state: 'accepted',
        action_state: 'completed',
        expires_at: '2099-01-01T00:00:00Z',
        timeline: [
          { stage: 'recommendation', present: true, event_id: 'evt_20260710_0001aaaa0001', sequence: 1, checksum: '1'.repeat(64) },
          { stage: 'decision', present: true, event_id: 'evt_20260710_0002bbbb0002', sequence: 2, checksum: '2'.repeat(64) },
          { stage: 'action_start', present: true, event_id: 'evt_20260710_0003cccc0003', sequence: 3, checksum: '3'.repeat(64) },
          { stage: 'action_complete', present: true, event_id: 'evt_20260710_0004dddd0004', sequence: 4, checksum: '4'.repeat(64) },
          { stage: 'outcome', present: false, event_id: null, sequence: null, checksum: null },
          { stage: 'effectiveness', present: false, event_id: null, sequence: null, checksum: null },
        ],
        outcomes: [],
        effectiveness: [],
      },
    ],
  },
};

// 单条组装失败样例：error 存在，其余字段退化，页面只降级该条
export const ACTIONS_RECENT_ITEM_ERROR_ENVELOPE = {
  ...ACTIONS_RECENT_ENVELOPE,
  partial: true,
  limitations: ['1 条推荐组装失败，已单独降级。'],
  data: {
    total_available: 1,
    shown: 1,
    with_outcome: 0,
    awaiting_outcome: 0,
    items: [
      {
        recommendation_id: 'rec_broken_007',
        domain: null,
        recommendation_kind: null,
        confirmation_state: null,
        action_state: null,
        expires_at: null,
        timeline: [],
        outcomes: [],
        effectiveness: [],
        error: 'recommendation history unavailable',
      },
    ],
  },
};

export const PROACTIVE_SUMMARY_ENVELOPE = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'proactive_summary.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00Z',
  snapshot_bindings: { personal: SNAPSHOT_BINDINGS.personal, external: null, serving: null },
  freshness: {},
  authorities: { proactive: 'ok' },
  partial: false,
  limitations: [],
  data: {
    total_available: 2,
    groups: {
      now: [
        {
          candidate_id: 'cand_20260719_now000001aa',
          domains: ['career', 'learning'],
          candidate_class: 'opportunity',
          presentation_kind: 'card',
          importance: { level: 'high', final_score: 0.83 },
          valid_from: '2026-07-19T00:00:00Z',
          expires_at: '2026-07-21T00:00:00Z',
          reason_codes: ['deadline_approaching', 'goal_misaligned'],
          current_control_eligible: true,
          current_control_reason_codes: [],
          control_as_of: '9999-12-31T23:59:59Z',
          control_history: [
            { event_id: 'evt_suppress_1', sequence: 1, operation: 'suppress', reason_code: 'manual_review' },
            { event_id: 'evt_restore_1', sequence: 2, operation: 'restore', reason_code: 'review_complete' },
          ],
        },
      ],
      deferrable: [
        {
          candidate_id: 'cand_20260718_def000002bb',
          domains: ['project'],
          candidate_class: 'maintenance',
          presentation_kind: 'digest',
          importance: { level: 'low', final_score: 0.42 },
          valid_from: null,
          expires_at: '2026-08-01T00:00:00Z',
          reason_codes: ['novelty_below_threshold'],
          current_control_eligible: false,
          current_control_reason_codes: ['snoozed_recently'],
          control_as_of: '9999-12-31T23:59:59Z',
          control_history: [],
        },
      ],
    },
    metrics: { noise_budget_remaining: 3, noise_budget_daily: 5, candidates_suppressed: 12 },
    notes: ['仅展示当前 eligible 候选；已抑制与冷却中的候选不列入本页。'],
  },
};

export const CALIBRATION_OVERVIEW_ENVELOPE = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'calibration_overview.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00Z',
  snapshot_bindings: { personal: null, external: null, serving: null },
  freshness: {},
  authorities: { calibration: 'ok' },
  partial: false,
  limitations: [],
  data: {
    total: 2,
    shown: 2,
    protocols: [
      {
        protocol_id: 'cal_weekly_hours_v1',
        status: 'concluded',
        verdict: 'met',
        causal_claim: false,
        inconclusive_reasons: [],
        sample_size: 12,
        summary_limitations: ['单用户观察性数据，不能作因果解释。'],
      },
      {
        protocol_id: 'cal_job_search_v2',
        status: 'inconclusive',
        verdict: 'inconclusive',
        causal_claim: false,
        inconclusive_reasons: ['sample_below_minimum', 'protocol_deviation'],
        sample_size: 2,
        summary_limitations: [],
      },
    ],
  },
};

/* ---------------- Phase 40：overview.get / system_status.get（冒烟测试用） ---------------- */

export const OVERVIEW_ENVELOPE = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'overview.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00Z',
  snapshot_bindings: SNAPSHOT_BINDINGS,
  freshness: { personal_as_of: '2026-07-19T07:30:00Z', knowledge_unit_count: 1234 },
  authorities: { personal: 'ok', decision: 'ok', proactive: 'ok', external: 'ok', knowledge: 'ok' },
  partial: false,
  limitations: [],
  data: {
    personal: {
      snapshot_id: SNAPSHOT_BINDINGS.personal,
      as_of: '2026-07-19T07:30:00Z',
      total_available: 42,
      domains: { career: 12, learning: 8, project: 9 },
      status_counts: { current: 30, stale: 5, conflict: 2 },
      top_items: [],
    },
    decision: {
      total_available: 1,
      queue: { proposed: 1 },
      items: [
        {
          recommendation_id: 'rec_attn_001',
          domain: 'career',
          recommendation_kind: 'time_allocation',
          horizon: '8w',
          confidence: 0.72,
          confirmation_state: 'proposed',
          action_state: null,
          expires_at: '2026-07-26T00:00:00Z',
        },
      ],
    },
    proactive: {
      total_available: 1,
      items: [
        {
          candidate_id: 'cand_20260719_now000001aa',
          domains: ['career'],
          importance: { level: 'high', final_score: 0.83 },
          candidate_class: 'opportunity',
          expires_at: '2026-07-21T00:00:00Z',
          reason_codes: ['deadline_approaching'],
        },
      ],
    },
    external: {
      snapshot_id: SNAPSHOT_BINDINGS.external,
      sources_count: 2,
      facts_count: 3,
    },
    knowledge: {
      active_collection: 'ku_20260719',
      unit_count: 1234,
      serving_snapshot_id: SNAPSHOT_BINDINGS.serving,
    },
  },
};

export const SYSTEM_STATUS_ENVELOPE = {
  schema_version: 'decision_cockpit_projection_v1',
  operation: 'system_status.get',
  ok: true,
  generated_at: '2026-07-19T08:00:00Z',
  snapshot_bindings: SNAPSHOT_BINDINGS,
  freshness: {},
  authorities: { knowledge: 'ok' },
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
      active_collection: 'ku_20260719',
      unit_count: 1234,
      serving_snapshot_id: SNAPSHOT_BINDINGS.serving,
      snapshot_hash: 'f'.repeat(64),
      snapshot_drift: false,
      pointer_exists: true,
    },
    authority_dbs: {
      external: { path: 'var/db/external.sqlite', exists: true, readable: true },
      decision_analysis: { path: 'var/db/decision_analysis.sqlite', exists: true, readable: true },
      project_pilot: { path: 'var/db/project_pilot.sqlite', exists: true, readable: true },
      recommendation_calibration: { path: 'var/db/recommendation_calibration.sqlite', exists: true, readable: true },
    },
  },
};
