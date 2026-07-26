/**
 * 实时数据契约回归测试：fixtures 为 10 个 /ui/* 端点的真实后端响应
 * （2026-07-19 从本机 rag-api 抓取；personal-state/external-delta/evidence-resolve
 * 于 2026-07-26 随 Phase 37 canonical DTO 结算重新抓取/补充，仅元数据，无私有正文）。
 * 用途：防止前端 Zod 契约与后端真实字段漂移（本测试即为三页
 * "加载失败"事故的回归守卫——schema 再紧一档、后端字段再改名都会在此变红）。
 * 更新方式：重新 curl 覆盖 src/test/fixtures/*.json。
 * 说明：用静态 JSON import（resolveJsonModule），避免 node:fs/@types/node 依赖。
 */
import { describe, expect, it } from 'vitest';
import type { z } from 'zod';
import {
  OverviewEnvelopeSchema,
  SystemStatusEnvelopeSchema,
  personalStateEnvelopeSchema,
  externalDeltaEnvelopeSchema,
  decisionQueueEnvelopeSchema,
  decisionWorkspaceEnvelopeSchema,
  actionsRecentEnvelopeSchema,
  proactiveSummaryEnvelopeSchema,
  calibrationOverviewEnvelopeSchema,
  evidenceResolveEnvelopeSchema,
} from '../api/schemas';

import overview from './fixtures/overview.json';
import systemStatus from './fixtures/system-status.json';
import personalState from './fixtures/personal-state.json';
import externalDelta from './fixtures/external-delta.json';
import decisionQueue from './fixtures/decision-queue.json';
import decisionWorkspace from './fixtures/decision-workspace.json';
import actionsRecent from './fixtures/actions-recent.json';
import proactiveSummary from './fixtures/proactive-summary.json';
import calibrationOverview from './fixtures/calibration-overview.json';
import evidenceResolve from './fixtures/evidence-resolve.json';

const CASES: Array<[string, z.ZodTypeAny, unknown]> = [
  ['overview', OverviewEnvelopeSchema, overview],
  ['system-status', SystemStatusEnvelopeSchema, systemStatus],
  ['personal-state', personalStateEnvelopeSchema, personalState],
  ['external-delta', externalDeltaEnvelopeSchema, externalDelta],
  ['decision-queue', decisionQueueEnvelopeSchema, decisionQueue],
  ['decision-workspace', decisionWorkspaceEnvelopeSchema, decisionWorkspace],
  ['actions-recent', actionsRecentEnvelopeSchema, actionsRecent],
  ['proactive-summary', proactiveSummaryEnvelopeSchema, proactiveSummary],
  ['calibration-overview', calibrationOverviewEnvelopeSchema, calibrationOverview],
  ['evidence-resolve', evidenceResolveEnvelopeSchema, evidenceResolve],
];

describe('实时后端响应 × 前端契约（fixtures 为真实抓取）', () => {
  for (const [name, schema, body] of CASES) {
    it(`${name} 通过 schema 解析`, () => {
      const result = schema.safeParse(body);
      if (!result.success) {
        // 打印前几条 issue 便于定位漂移字段
        console.error(name, result.error.issues.slice(0, 5));
      }
      expect(result.success).toBe(true);
    });
  }
});

/**
 * T-36-07 回归：每个真实 fixture 一旦 schema_version 或 operation 被篡改，
 * 对应端点 schema 必须拒绝——防止宽松 envelope 把错版本/错 operation 的响应
 * 当作当前 decision 状态渲染。
 */
describe('版本/operation 篡改回归（九个 fixture 全覆盖）', () => {
  for (const [name, schema, body] of CASES) {
    it(`${name}：篡改 schema_version 后 parse 失败`, () => {
      const tampered = { ...(body as Record<string, unknown>), schema_version: 'decision_cockpit_projection_v2' };
      expect(schema.safeParse(tampered).success).toBe(false);
    });

    it(`${name}：篡改 operation 后 parse 失败`, () => {
      const tampered = { ...(body as Record<string, unknown>), operation: 'not_a_real_operation' };
      expect(schema.safeParse(tampered).success).toBe(false);
    });
  }
});

/**
 * D-36-05 回归：OverviewPage 的 Now Stack 派生（真实 confirmation_state 词表 +
 * importance.final_score）依赖的字段必须真实存在于后端捕获的 overview.get fixture 里，
 * 而不是页面代码单方面假设的旧字段（confirmed / importance.score）。
 */
describe('overview fixture 携带 OverviewPage Now Stack 依赖的真实字段', () => {
  it('decision.items[].confirmation_state 属于已发布词表，且不是旧的 confirmed', () => {
    const parsed = OverviewEnvelopeSchema.parse(overview);
    const knownStates = new Set(['proposed', 'accepted', 'rejected', 'deferred', 'revoked']);
    for (const item of parsed.data.decision?.items ?? []) {
      expect(item.confirmation_state).not.toBe('confirmed');
      if (item.confirmation_state) {
        expect(knownStates.has(item.confirmation_state)).toBe(true);
      }
    }
  });

  it('proactive.items[].importance 暴露 final_score（数值），不是旧的 score/level', () => {
    const parsed = OverviewEnvelopeSchema.parse(overview);
    for (const item of parsed.data.proactive?.items ?? []) {
      const finalScore = item.importance['final_score'];
      expect(typeof finalScore).toBe('number');
    }
  });
});

/** 端点 schema 互斥：某端点真实 fixture 不能被另一个端点的 schema 接受。 */
describe('跨端点 payload 互斥', () => {
  it('decision-queue fixture 不能被 personal_state.get schema 接受', () => {
    expect(personalStateEnvelopeSchema.safeParse(decisionQueue).success).toBe(false);
  });

  it('proactive-summary fixture 不能被 actions_recent.get schema 接受', () => {
    expect(actionsRecentEnvelopeSchema.safeParse(proactiveSummary).success).toBe(false);
  });

  it('overview fixture 不能被 system.status.get schema 接受', () => {
    expect(SystemStatusEnvelopeSchema.safeParse(overview).success).toBe(false);
  });

  it('external-delta fixture 不能被 evidence_resolve.get schema 接受', () => {
    expect(evidenceResolveEnvelopeSchema.safeParse(externalDelta).success).toBe(false);
  });

  it('evidence-resolve fixture 不能被 external_delta.get schema 接受', () => {
    expect(externalDeltaEnvelopeSchema.safeParse(evidenceResolve).success).toBe(false);
  });
});

/**
 * Phase 37（EVID-01）回归：真实 evidence-resolve fixture 必须携带 evidence.resolve
 * 稳定引用三元组（stable_id/snapshot_id/checksum），且 External 分支不泄露 raw value
 * （与 external_delta.get 同一隐私边界）。
 */
describe('evidence-resolve fixture 携带稳定引用三元组，不含 raw value', () => {
  it('data.reference 与 data.result 的 stable_id/snapshot_id/checksum 三者一致', () => {
    const parsed = evidenceResolveEnvelopeSchema.parse(evidenceResolve);
    expect(parsed.data.status).toBe('ok');
    expect(parsed.data.result?.stable_id).toBe(parsed.data.reference.stable_id);
    expect(parsed.data.result?.snapshot_id).toBe(parsed.data.reference.snapshot_id);
    expect(parsed.data.result?.checksum).toBe(parsed.data.reference.checksum);
  });

  it('result 不含 value 字段（external_fact 分支 metadata-only）', () => {
    const parsed = evidenceResolveEnvelopeSchema.parse(evidenceResolve);
    expect((parsed.data.result as Record<string, unknown> | null)?.['value']).toBeUndefined();
  });
});
