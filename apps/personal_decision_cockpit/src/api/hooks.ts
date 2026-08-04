import { useMutation, useQuery } from '@tanstack/react-query';
import { apiGet, apiPost } from './client';
import { fetchProactiveCandidateExplain, fetchProactiveControlsStatus } from './proactive';
import {
  OverviewEnvelopeSchema,
  SystemStatusEnvelopeSchema,
  actionsRecentEnvelopeSchema,
  calibrationOverviewEnvelopeSchema,
  decisionQueueEnvelopeSchema,
  decisionWorkspaceEnvelopeSchema,
  evidenceResolveEnvelopeSchema,
  externalDeltaEnvelopeSchema,
  personalStateEnvelopeSchema,
  proactiveSummaryEnvelopeSchema,
  type EvidenceSubjectType,
  wikiTopicBacklinksEnvelopeSchema,
  wikiTopicGetEnvelopeSchema,
  wikiTopicListEnvelopeSchema,
  wikiTopicResolveEnvelopeSchema,
  type WikiTopicType,
  piRuntimeStatusSchema,
  piRuntimeTasksSchema,
  piRuntimeMutationSchema,
} from './schemas';

// 只读投影的通用节奏：30s 内不算 stale，失败只重试 1 次，每分钟后台刷新一次。
const PROJECTION_QUERY_OPTIONS = {
  staleTime: 30_000,
  retry: 1,
  refetchInterval: 60_000,
} as const;

/** 今日总览投影：GET /ui/overview */
export function useOverview() {
  return useQuery({
    queryKey: ['ui', 'overview'],
    queryFn: () => apiGet('/ui/overview', OverviewEnvelopeSchema),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** 系统状态投影：GET /ui/system/status */
export function useSystemStatus() {
  return useQuery({
    queryKey: ['ui', 'system-status'],
    queryFn: () => apiGet('/ui/system/status', SystemStatusEnvelopeSchema),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** 个人状态投影：GET /ui/personal-state */
export function usePersonalState() {
  return useQuery({
    queryKey: ['ui', 'personal-state'],
    queryFn: () => apiGet('/ui/personal-state', personalStateEnvelopeSchema),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** 外部环境增量投影：GET /ui/external/delta */
export function useExternalDelta() {
  return useQuery({
    queryKey: ['ui', 'external-delta'],
    queryFn: () => apiGet('/ui/external/delta', externalDeltaEnvelopeSchema),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** 决策队列投影：GET /ui/decision-queue（六组看板，Phase 38） */
export function useDecisionQueue() {
  return useQuery({
    queryKey: ['ui', 'decision-queue'],
    queryFn: () => apiGet('/ui/decision-queue', decisionQueueEnvelopeSchema),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** 决策工作区投影：GET /ui/decision/workspace?recommendation_id=<id>（节级降级，Phase 38） */
export function useDecisionWorkspace(recommendationId: string | undefined) {
  return useQuery({
    queryKey: ['ui', 'decision-workspace', recommendationId ?? ''],
    queryFn: () =>
      apiGet(
        `/ui/decision/workspace?recommendation_id=${encodeURIComponent(recommendationId ?? '')}`,
        decisionWorkspaceEnvelopeSchema,
      ),
    enabled: Boolean(recommendationId),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** 行动与结果投影：GET /ui/actions/recent（六阶段时间线 + outcome/effectiveness，Phase 39）。
 *  可选 cursor 触发分页(加载更早记录);GET-only,无副作用。 */
export function useActionsRecent(cursor?: string | null) {
  const path = cursor ? `/ui/actions/recent?cursor=${encodeURIComponent(cursor)}` : '/ui/actions/recent';
  return useQuery({
    queryKey: ['ui', 'actions-recent', cursor ?? 'first'],
    queryFn: () => apiGet(path, actionsRecentEnvelopeSchema),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** 主动提醒摘要投影：GET /ui/proactive/summary（eligible 候选分组，Phase 39） */
export function useProactiveSummary() {
  return useQuery({
    queryKey: ['ui', 'proactive-summary'],
    queryFn: () => apiGet('/ui/proactive/summary', proactiveSummaryEnvelopeSchema),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** 校准总览投影：GET /ui/calibration/overview（非因果协议评估，Phase 39） */
export function useCalibrationOverview() {
  return useQuery({
    queryKey: ['ui', 'calibration-overview'],
    queryFn: () => apiGet('/ui/calibration/overview', calibrationOverviewEnvelopeSchema),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/**
 * 只读证据下钻的稳定引用（Phase 37：EVID-01）。三个字段全部来自服务端上一次
 * Projection 响应（current_assertion_id/current_value_checksum、fact_id/
 * fact_checksum、recommendation_id/recommendation_checksum），页面不得自行推导
 * 或伪造；personal_state 额外需要完整 state key。
 */
export interface EvidenceReferenceInput {
  subjectType: EvidenceSubjectType;
  stableId: string;
  snapshotId: string;
  checksum: string;
  stateKey?: {
    assertion_kind: string;
    subject: string;
    domain: string;
    scope: string;
    predicate: string;
  };
}

function evidenceResolvePath(reference: EvidenceReferenceInput): string {
  const params = new URLSearchParams({
    subject_type: reference.subjectType,
    stable_id: reference.stableId,
    snapshot_id: reference.snapshotId,
    checksum: reference.checksum,
  });
  if (reference.stateKey) {
    params.set('assertion_kind', reference.stateKey.assertion_kind);
    params.set('subject', reference.stateKey.subject);
    params.set('domain', reference.stateKey.domain);
    params.set('scope', reference.stateKey.scope);
    params.set('predicate', reference.stateKey.predicate);
  }
  return `/ui/evidence/resolve?${params.toString()}`;
}

function evidenceReferenceReady(reference: EvidenceReferenceInput | null): boolean {
  if (!reference) return false;
  if (!reference.stableId || !reference.snapshotId || !reference.checksum) return false;
  if (reference.subjectType !== 'personal_state') return true;
  const key = reference.stateKey;
  return Boolean(
    key && key.assertion_kind && key.subject && key.domain && key.scope && key.predicate,
  );
}

/**
 * 只读证据下钻：GET /ui/evidence/resolve（stable_id+snapshot+checksum 校验，
 * 服务端解析 mismatch/expired/abstain/not_found，Phase 37 EVID-01）。
 * 仅 GET，不携带任何可写 payload；reference 为 null 或字段不全时不发起请求。
 */
export function useEvidenceResolve(reference: EvidenceReferenceInput | null) {
  const ready = evidenceReferenceReady(reference);
  return useQuery({
    queryKey: ['ui', 'evidence-resolve', ready && reference ? evidenceResolvePath(reference) : ''],
    queryFn: () => apiGet(evidenceResolvePath(reference as EvidenceReferenceInput), evidenceResolveEnvelopeSchema),
    enabled: ready,
    staleTime: 30_000,
    retry: 1,
  });
}

/** Wiki P0 目录：仅同源 GET，服务端发布的 opaque topic_id 才进入页面。 */
export function useWikiTopicList() {
  return useQuery({
    queryKey: ['wiki', 'personal_wiki_projection_v1', 'topic.list'],
    queryFn: () => apiGet('/ui/topics?limit=50', wikiTopicListEnvelopeSchema),
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** Wiki P0 主题页：缺少 typed type/id 时不发请求。 */
export function useWikiTopic(topicType: WikiTopicType | undefined, topicId: string | undefined) {
  const enabled = Boolean(topicType && topicId);
  const path = enabled
    ? `/ui/topic?topic_type=${encodeURIComponent(topicType as string)}&topic_id=${encodeURIComponent(topicId as string)}`
    : '';
  return useQuery({
    queryKey: ['wiki', 'personal_wiki_projection_v1', 'topic.get', topicType ?? '', topicId ?? ''],
    queryFn: () => apiGet(path, wikiTopicGetEnvelopeSchema),
    enabled,
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** Wiki P0 显式反链：关系词表由服务端锁定。 */
export function useWikiTopicBacklinks(topicType: WikiTopicType | undefined, topicId: string | undefined) {
  const enabled = Boolean(topicType && topicId);
  const path = enabled
    ? `/ui/topic/backlinks?topic_type=${encodeURIComponent(topicType as string)}&topic_id=${encodeURIComponent(topicId as string)}`
    : '';
  return useQuery({
    queryKey: ['wiki', 'personal_wiki_projection_v1', 'topic.backlinks', topicType ?? '', topicId ?? ''],
    queryFn: () => apiGet(path, wikiTopicBacklinksEnvelopeSchema),
    enabled,
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** Wiki-first/fallback read verdict：客户端只显示服务端选定来源，不计算 freshness。 */
export function useWikiTopicResolve(topicKey: string | undefined, query?: string) {
  const enabled = Boolean(topicKey || query);
  const params = new URLSearchParams();
  if (topicKey) params.set('topic_key', topicKey);
  if (query) params.set('query', query);
  const path = enabled ? `/ui/topic/resolve?${params.toString()}` : '';
  return useQuery({
    queryKey: ['wiki', 'personal_wiki_projection_v1', 'topic.resolve', topicKey ?? '', query ?? ''],
    queryFn: () => apiGet(path, wikiTopicResolveEnvelopeSchema),
    enabled,
    ...PROJECTION_QUERY_OPTIONS,
  });
}

/** 候选解释直读：GET /proactive/candidate/explain?candidate_id=X（compact 信封，按需触发） */
export function useProactiveCandidateExplain(candidateId: string | null) {
  return useQuery({
    queryKey: ['proactive', 'candidate-explain', candidateId ?? ''],
    queryFn: () => fetchProactiveCandidateExplain(candidateId ?? ''),
    enabled: Boolean(candidateId),
    staleTime: 60_000,
    retry: 1,
  });
}

/** 控制状态直读：GET /proactive/controls/status?candidate_id=X（compact 信封，按需触发） */
export function useProactiveControlStatus(candidateId: string | null) {
  return useQuery({
    queryKey: ['proactive', 'controls-status', candidateId ?? ''],
    queryFn: () => fetchProactiveControlsStatus(candidateId ?? ''),
    enabled: Boolean(candidateId),
    staleTime: 30_000,
    retry: 1,
  });
}

/** Pi runtime is same-origin only; the browser never opens 8790 directly. */
export function usePiRuntimeStatus() {
  return useQuery({ queryKey: ['pi', 'runtime-status'], queryFn: () => apiGet('/api/pi/status', piRuntimeStatusSchema), ...PROJECTION_QUERY_OPTIONS });
}

export function usePiRuntimeTasks() {
  return useQuery({ queryKey: ['pi', 'runtime-tasks'], queryFn: () => apiGet('/api/pi/tasks', piRuntimeTasksSchema), ...PROJECTION_QUERY_OPTIONS });
}

export function usePiRuntimeMutation(action: 'cancel' | 'resume') {
  return useMutation({
    mutationFn: (payload: { task_id: string; expected_version: number; idempotency_key: string; state?: 'failed'; error_code?: string }) =>
      apiPost(`/api/pi/${action}`, payload, piRuntimeMutationSchema),
  });
}
