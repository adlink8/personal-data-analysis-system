/**
 * 实时数据契约回归测试：fixtures 为 9 个 /ui/* 端点的真实后端响应
 * （2026-07-19 从本机 rag-api 抓取，仅元数据，无私有正文）。
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
});
