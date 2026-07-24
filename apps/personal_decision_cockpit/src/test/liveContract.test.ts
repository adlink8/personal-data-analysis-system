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
