import { describe, expect, it } from 'vitest';
import { decisionQueueEnvelopeSchema, decisionWorkspaceEnvelopeSchema } from '../api/schemas';
import { DECISION_QUEUE_ENVELOPE, DECISION_WORKSPACE_ENVELOPE } from './mockData';

/**
 * Phase 38 契约测试（spec §17.2）：
 * decision_queue.get / decision_workspace.get 信封（完整 + partial + 缺 id 400 样例）。
 */

describe('decisionQueueEnvelopeSchema', () => {
  it('解析完整 decision_queue.get 样例：六键恒在 + 卡片关键字段保留', () => {
    const parsed = decisionQueueEnvelopeSchema.parse(DECISION_QUEUE_ENVELOPE);
    expect(parsed.operation).toBe('decision_queue.get');
    expect(parsed.partial).toBe(false);
    expect(Object.keys(parsed.data.stages)).toHaveLength(6);
    expect(parsed.data.stage_counts['needs_attention']).toBe(1);
    const card = parsed.data.stages['needs_attention']?.[0];
    expect(card?.recommendation_id).toBe('rec_attn_001');
    expect(card?.confirmation_state).toBe('proposed');
    expect(card?.action_state).toBeNull();
    expect(card?.current_sequence).toBe(1);
    expect(parsed.data.stages['closed']?.[0]?.confirmation_state).toBe('rejected');
  });

  it('解析 partial 样例：decision Authority 失败 → 全零看板 + limitations 透传', () => {
    const partial = {
      ...DECISION_QUEUE_ENVELOPE,
      authorities: { decision: 'error' },
      partial: true,
      limitations: ['决策 Authority 暂不可用，看板退化为全零。'],
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
    const parsed = decisionQueueEnvelopeSchema.parse(partial);
    expect(parsed.partial).toBe(true);
    expect(parsed.authorities.decision).toBe('error');
    expect(parsed.data.total_available).toBe(0);
    expect(parsed.limitations).toHaveLength(1);
  });

  it('容忍卡片未知字段（passthrough）', () => {
    const withExtra = {
      ...DECISION_QUEUE_ENVELOPE,
      data: {
        ...DECISION_QUEUE_ENVELOPE.data,
        stages: {
          ...DECISION_QUEUE_ENVELOPE.data.stages,
          closed: [{ ...DECISION_QUEUE_ENVELOPE.data.stages.closed[0], future_field: { nested: true } }],
        },
      },
    };
    const parsed = decisionQueueEnvelopeSchema.parse(withExtra);
    expect(parsed.data.stages['closed']?.[0]?.['future_field']).toEqual({ nested: true });
  });
});

describe('decisionWorkspaceEnvelopeSchema', () => {
  it('解析完整 decision_workspace.get 样例：四节 + linked_analysis_run_id', () => {
    const parsed = decisionWorkspaceEnvelopeSchema.parse(DECISION_WORKSPACE_ENVELOPE);
    expect(parsed.operation).toBe('decision_workspace.get');
    const recommendation = parsed.data.recommendation;
    expect(recommendation?.recommendation_id).toBe('rec_attn_001');
    expect(recommendation?.policy_id).toBe('policy_time_allocation_v2');
    expect(recommendation?.rationale_codes).toContain('goal_misaligned');
    expect(recommendation?.support).toHaveLength(2);
    expect(recommendation?.support[0]?.authority_id).toBe('a.personal_change');
    expect(parsed.data.history).toHaveLength(3);
    expect(parsed.data.history[0]?.previous_event_checksum).toBe('GENESIS');
    expect(parsed.data.outcomes[0]?.causal_claim).toBe(false);
    expect(parsed.data.effectiveness[0]?.verdict).toBe('inconclusive');
    expect(parsed.data.linked_analysis_run_id).toBe('ar_20260719_source0001ff');
  });

  it('解析节级降级样例：recommendation 为 null、authorities 标记 error', () => {
    const degraded = {
      ...DECISION_WORKSPACE_ENVELOPE,
      authorities: { recommendation: 'error', history: 'ok', outcomes: 'ok', effectiveness: 'ok' },
      partial: true,
      limitations: ['recommendation Authority 暂不可用。'],
      data: { ...DECISION_WORKSPACE_ENVELOPE.data, recommendation: null },
    };
    const parsed = decisionWorkspaceEnvelopeSchema.parse(degraded);
    expect(parsed.partial).toBe(true);
    expect(parsed.data.recommendation).toBeNull();
    expect(parsed.authorities.recommendation).toBe('error');
    // 其余节不受影响
    expect(parsed.data.history).toHaveLength(3);
  });

  it('缺 id 的 400 错误样例不被信封 schema 接受（页面走 error 态）', () => {
    const errorBody = {
      schema_version: 'decision_cockpit_projection_v1',
      operation: 'decision_workspace.get',
      ok: false,
      error: { code: 'invalid_input', detail: 'recommendation_id 必填' },
    };
    const parsed = decisionWorkspaceEnvelopeSchema.safeParse(errorBody);
    expect(parsed.success).toBe(false);
  });
});
