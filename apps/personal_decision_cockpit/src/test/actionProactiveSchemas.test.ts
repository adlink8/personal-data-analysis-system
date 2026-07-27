import { describe, expect, it } from 'vitest';
import {
  actionsRecentEnvelopeSchema,
  calibrationOverviewEnvelopeSchema,
  proactiveSummaryEnvelopeSchema,
} from '../api/schemas';
import {
  ACTIONS_RECENT_ENVELOPE,
  ACTIONS_RECENT_ITEM_ERROR_ENVELOPE,
  CALIBRATION_OVERVIEW_ENVELOPE,
  PROACTIVE_SUMMARY_ENVELOPE,
} from './mockData';

/**
 * Phase 39 契约测试（spec §17.2）：
 * actions_recent.get / proactive_summary.get / calibration_overview.get 信封
 * （完整样例 + 单条 error 样例 + 节为 null 样例 + 未知字段宽松样例）。
 */

describe('actionsRecentEnvelopeSchema', () => {
  it('解析完整 actions_recent.get 样例：六阶段时间线 + outcome/effectiveness 保留', () => {
    const parsed = actionsRecentEnvelopeSchema.parse(ACTIONS_RECENT_ENVELOPE);
    expect(parsed.operation).toBe('actions_recent.get');
    expect(parsed.partial).toBe(false);
    expect(parsed.data.total_available).toBe(2);
    expect(parsed.data.with_outcome).toBe(1);
    expect(parsed.data.awaiting_outcome).toBe(1);
    const first = parsed.data.items[0];
    expect(first?.recommendation_id).toBe('rec_done_005');
    expect(first?.timeline).toHaveLength(6);
    expect(first?.timeline.map((stage) => stage.stage)).toEqual([
      'recommendation',
      'decision',
      'action_start',
      'action_complete',
      'outcome',
      'effectiveness',
    ]);
    expect(first?.timeline[5]?.checksum).toBe('f'.repeat(64));
    expect(first?.outcomes[0]?.['actual_time_minutes']).toBe(45);
    expect(first?.outcomes[0]?.causal_claim).toBe(false);
    expect(first?.effectiveness[0]?.verdict).toBe('inconclusive');
    // 未达成节点字段为 null
    const second = parsed.data.items[1];
    expect(second?.timeline[4]?.present).toBe(false);
    expect(second?.timeline[4]?.event_id).toBeNull();
    expect(second?.timeline[4]?.sequence).toBeNull();
  });

  it('解析单条 error 样例：该条降级字段保留，信封 partial 透传', () => {
    const parsed = actionsRecentEnvelopeSchema.parse(ACTIONS_RECENT_ITEM_ERROR_ENVELOPE);
    expect(parsed.partial).toBe(true);
    expect(parsed.limitations).toHaveLength(1);
    const item = parsed.data.items[0];
    expect(item?.recommendation_id).toBe('rec_broken_007');
    expect(item?.error).toBe('recommendation history unavailable');
    expect(item?.timeline).toHaveLength(0);
    expect(item?.domain).toBeNull();
  });

  it('容忍 outcome 缺字段与未知字段（宽松透传）', () => {
    const lenient = {
      ...ACTIONS_RECENT_ENVELOPE,
      data: {
        ...ACTIONS_RECENT_ENVELOPE.data,
        items: [
          {
            recommendation_id: 'rec_lenient_001',
            timeline: [{ stage: 'recommendation', present: true }],
            outcomes: [{ future_field: { nested: true } }],
            effectiveness: [],
          },
        ],
      },
    };
    const parsed = actionsRecentEnvelopeSchema.parse(lenient);
    const item = parsed.data.items[0];
    // 缺省字段给默认值/undefined，不抛错
    expect(item?.domain).toBeUndefined();
    expect(item?.outcomes).toHaveLength(1);
    expect(item?.outcomes[0]?.['future_field']).toEqual({ nested: true });
    expect(item?.timeline).toHaveLength(1);
    expect(item?.timeline[0]?.event_id).toBeUndefined();
  });
});

describe('proactiveSummaryEnvelopeSchema', () => {
  it('解析完整 proactive_summary.get 样例：两组 + metrics + notes', () => {
    const parsed = proactiveSummaryEnvelopeSchema.parse(PROACTIVE_SUMMARY_ENVELOPE);
    expect(parsed.operation).toBe('proactive_summary.get');
    expect(parsed.data.total_available).toBe(2);
    const now = parsed.data.groups?.now ?? [];
    const deferrable = parsed.data.groups?.deferrable ?? [];
    expect(now).toHaveLength(1);
    expect(deferrable).toHaveLength(1);
    expect(now[0]?.candidate_id).toBe('cand_20260719_now000001aa');
    expect(now[0]?.importance['final_score']).toBe(0.83);
    expect(now[0]?.reason_codes).toContain('deadline_approaching');
    expect(now[0]?.current_control_eligible).toBe(true);
    expect(deferrable[0]?.current_control_reason_codes).toContain('snoozed_recently');
    expect(parsed.data.metrics?.['noise_budget_remaining']).toBe(3);
    expect(parsed.data.notes).toHaveLength(1);
  });

  it('解析节为 null 样例：groups/metrics 为 null、partial 透传', () => {
    const partial = {
      ...PROACTIVE_SUMMARY_ENVELOPE,
      authorities: { proactive: 'error' },
      partial: true,
      limitations: ['proactive Authority 暂不可用，候选分组未包含在本次投影中。'],
      data: { total_available: 0, groups: null, metrics: null, notes: [] },
    };
    const parsed = proactiveSummaryEnvelopeSchema.parse(partial);
    expect(parsed.partial).toBe(true);
    expect(parsed.data.groups).toBeNull();
    expect(parsed.data.metrics).toBeNull();
    expect(parsed.authorities.proactive).toBe('error');
  });

  it('容忍候选未知字段（passthrough）', () => {
    const withExtra = {
      ...PROACTIVE_SUMMARY_ENVELOPE,
      data: {
        ...PROACTIVE_SUMMARY_ENVELOPE.data,
        groups: {
          now: [{ candidate_id: 'cand_x', future_field: { nested: true } }],
          deferrable: [],
        },
      },
    };
    const parsed = proactiveSummaryEnvelopeSchema.parse(withExtra);
    expect(parsed.data.groups?.now[0]?.['future_field']).toEqual({ nested: true });
  });
});

describe('calibrationOverviewEnvelopeSchema', () => {
  it('解析完整 calibration_overview.get 样例：协议关键字段保留', () => {
    const parsed = calibrationOverviewEnvelopeSchema.parse(CALIBRATION_OVERVIEW_ENVELOPE);
    expect(parsed.operation).toBe('calibration_overview.get');
    expect(parsed.data.total).toBe(2);
    const [concluded, inconclusive] = parsed.data.protocols;
    expect(concluded?.protocol_id).toBe('cal_weekly_hours_v1');
    expect(concluded?.sample_size).toBe(12);
    expect(concluded?.causal_claim).toBe(false);
    expect(concluded?.summary_limitations).toHaveLength(1);
    expect(inconclusive?.status).toBe('inconclusive');
    expect(inconclusive?.inconclusive_reasons).toContain('sample_below_minimum');
  });

  it('解析单条协议 error 样例：只降级该条', () => {
    const degraded = {
      ...CALIBRATION_OVERVIEW_ENVELOPE,
      partial: true,
      data: {
        total: 1,
        shown: 1,
        protocols: [
          {
            protocol_id: 'cal_broken_v9',
            status: null,
            verdict: null,
            error: 'protocol runs unavailable',
          },
        ],
      },
    };
    const parsed = calibrationOverviewEnvelopeSchema.parse(degraded);
    const protocol = parsed.data.protocols[0];
    expect(protocol?.error).toBe('protocol runs unavailable');
    expect(protocol?.inconclusive_reasons).toEqual([]);
    expect(protocol?.summary_limitations).toEqual([]);
    expect(protocol?.sample_size).toBeUndefined();
  });
});
