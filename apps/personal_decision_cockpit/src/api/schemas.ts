import { z } from 'zod';

/**
 * UI 投影统一信封（spec §11.2）：decision_cockpit_projection_v1。
 * 所有 schema 用 .passthrough() 容忍未知字段；
 * 数值/字符串允许 null——后端某个 Authority 部分失败时对应节为 null。
 */

const SnapshotBindingsSchema = z
  .object({
    personal: z.string().nullable(),
    external: z.string().nullable(),
    serving: z.string().nullable(),
  })
  .passthrough();

const FreshnessSchema = z
  .object({
    personal_as_of: z.string().nullish(),
    knowledge_unit_count: z.number().nullish(),
  })
  .passthrough()
  .nullish();

/**
 * 统一信封工厂（D-36-05/T-36-07）：schema_version 固定字面量
 * `decision_cockpit_projection_v1`，operation 固定为调用方传入的该端点专属字面量。
 * 错误版本或错误 operation（含被其他端点合法 payload 误用）一律 parse 失败，
 * 不允许任意字符串通过并被当作当前 decision 状态渲染。
 */
function envelope<Op extends string, D extends z.ZodTypeAny>(operation: Op, dataSchema: D) {
  return z
    .object({
      schema_version: z.literal('decision_cockpit_projection_v1'),
      operation: z.literal(operation),
      ok: z.boolean(),
      generated_at: z.string(),
      snapshot_bindings: SnapshotBindingsSchema,
      freshness: FreshnessSchema,
      authorities: z.record(z.string()).default({}),
      partial: z.boolean().default(false),
      limitations: z.array(z.string()).default([]),
      data: dataSchema,
    })
    .passthrough();
}

/* ---------------- overview.get ---------------- */

const AssertionKeySchema = z
  .object({
    assertion_kind: z.string().nullable(),
    subject: z.string().nullable(),
    domain: z.string().nullable(),
    scope: z.string().nullable(),
    predicate: z.string().nullable(),
  })
  .passthrough();

const PersonalSectionSchema = z
  .object({
    snapshot_id: z.string().nullable(),
    as_of: z.string().nullable(),
    total_available: z.number().nullable(),
    domains: z.record(z.number()).default({}),
    status_counts: z.record(z.number()).default({}),
    top_items: z
      .array(
        z
          .object({
            key: AssertionKeySchema,
            status: z.string().nullable(),
            confidence: z.union([z.number(), z.string()]).nullable(),
            provenance_class: z.string().nullable(),
          })
          .passthrough(),
      )
      .default([]),
  })
  .passthrough()
  .nullable()
  .default(null);

const DecisionItemSchema = z
  .object({
    recommendation_id: z.string().nullable(),
    domain: z.string().nullable(),
    recommendation_kind: z.string().nullable(),
    horizon: z.string().nullable(),
    confidence: z.union([z.number(), z.string()]).nullable(),
    confirmation_state: z.string().nullable(),
    action_state: z.string().nullable(),
    expires_at: z.string().nullable(),
  })
  .passthrough();

const DecisionSectionSchema = z
  .object({
    total_available: z.number().nullable(),
    queue: z.record(z.number()).default({}),
    items: z.array(DecisionItemSchema).default([]),
  })
  .passthrough()
  .nullable()
  .default(null);

const ProactiveItemSchema = z
  .object({
    candidate_id: z.string().nullable(),
    domains: z.array(z.string()).default([]),
    importance: z.record(z.unknown()).default({}),
    candidate_class: z.string().nullable(),
    expires_at: z.string().nullable(),
    reason_codes: z.array(z.string()).default([]),
  })
  .passthrough();

const ProactiveSectionSchema = z
  .object({
    total_available: z.number().nullable(),
    items: z.array(ProactiveItemSchema).default([]),
  })
  .passthrough()
  .nullable()
  .default(null);

const ExternalSectionSchema = z
  .object({
    snapshot_id: z.string().nullable(),
    sources_count: z.number().nullable(),
    facts_count: z.number().nullable(),
  })
  .passthrough()
  .nullable()
  .default(null);

const KnowledgeSectionSchema = z
  .object({
    active_collection: z.string().nullable(),
    unit_count: z.number().nullable(),
    serving_snapshot_id: z.string().nullable(),
  })
  .passthrough()
  .nullable()
  .default(null);

export const OverviewDataSchema = z
  .object({
    personal: PersonalSectionSchema,
    decision: DecisionSectionSchema,
    proactive: ProactiveSectionSchema,
    external: ExternalSectionSchema,
    knowledge: KnowledgeSectionSchema,
  })
  .passthrough();

export const OverviewEnvelopeSchema = envelope('overview.get', OverviewDataSchema);
export type OverviewEnvelope = z.infer<typeof OverviewEnvelopeSchema>;
export type OverviewData = z.infer<typeof OverviewDataSchema>;

/* ---------------- system.status.get ---------------- */

const PortSchema = z
  .object({
    up: z.boolean(),
    port: z.number(),
  })
  .passthrough();

const SystemKnowledgeSchema = z
  .object({
    available: z.boolean().nullable(),
    active_collection: z.string().nullable(),
    unit_count: z.number().nullable(),
    serving_snapshot_id: z.string().nullable(),
    snapshot_hash: z.string().nullable(),
    snapshot_drift: z.union([z.boolean(), z.array(z.unknown())]).nullable(), // 真实返回为漂移条目数组（空数组=无漂移）
    pointer_exists: z.boolean().nullable(),
  })
  .passthrough();

const AuthorityDbSchema = z
  .object({
    path: z.string(),
    exists: z.boolean(),
    readable: z.boolean(),
  })
  .passthrough();

export const SystemStatusDataSchema = z
  .object({
    ports: z
      .object({
        rest: PortSchema,
        mcp: PortSchema,
        tunnel: PortSchema,
      })
      .passthrough(),
    knowledge: SystemKnowledgeSchema,
    authority_dbs: z.record(AuthorityDbSchema).default({}),
  })
  .passthrough();

export const SystemStatusEnvelopeSchema = envelope('system.status.get', SystemStatusDataSchema);
export type SystemStatusEnvelope = z.infer<typeof SystemStatusEnvelopeSchema>;
export type SystemStatusData = z.infer<typeof SystemStatusDataSchema>;

/* ---------------- personal_state.get（Phase 37） ---------------- */

const AssertionKindCountsSchema = z
  .object({
    goal: z.number().nullish(),
    constraint: z.number().nullish(),
    observation: z.number().nullish(),
    state: z.number().nullish(),
  })
  .passthrough();

const ProvenanceCountsSchema = z
  .object({
    fact: z.number().nullish(),
    observation: z.number().nullish(),
    inference: z.number().nullish(),
  })
  .passthrough();

/**
 * 单条断言：值只有 checksum，页面只展示元数据（隐私封存，spec §15）。
 * current_value_checksum 与 current_assertion_id + 所属 domains 的 data.snapshot_id
 * 一起构成 evidence.resolve 的稳定引用三元组（Phase 37：EVID-01），后端恒定暴露该键
 * （无当前断言时为 null），不用 nullish 掩盖两者本应同时存在。
 */
const PersonalAssertionSchema = z
  .object({
    key: AssertionKeySchema,
    provenance_class: z.string().nullable(),
    status: z.string().nullable(),
    confidence: z.union([z.number(), z.string()]).nullable(),
    current_assertion_id: z.string().nullable(),
    current_value_checksum: z.string().nullable(),
    evidence_count: z.number().nullable(),
  })
  .passthrough();

const PersonalStateDomainSchema = z
  .object({
    total: z.number().nullish(),
    by_kind: AssertionKindCountsSchema.nullable().default(null),
    by_provenance: ProvenanceCountsSchema.nullable().default(null),
    conflicts: z.number().nullish(),
    assertions: z.array(PersonalAssertionSchema).default([]),
  })
  .passthrough();

const LifecycleCountsSchema = z
  .object({
    current: z.number().nullish(),
    stale: z.number().nullish(),
    conflict: z.number().nullish(),
    resolved: z.number().nullish(),
    expired: z.number().nullish(),
  })
  .passthrough();

const RecentChangeSchema = z
  .object({
    // 后端真实字段为 record_id/record_type/effective_at；change_type/observed_at 为兼容旧名。
    // 一律 nullish（键可缺省），页面按 record_type/effective_at 优先回退渲染。
    record_id: z.string().nullish(),
    record_type: z.string().nullish(),
    effective_at: z.string().nullish(),
    change_type: z.string().nullish(),
    domain: z.string().nullish(),
    subject: z.string().nullish(),
    observed_at: z.string().nullish(),
    status: z.string().nullish(),
  })
  .passthrough();

export const PersonalStateDataSchema = z
  .object({
    snapshot_id: z.string().nullable(),
    as_of: z.string().nullable(),
    total_available: z.number().nullable(),
    // 八领域键恒在；单领域失败时该领域值为 null（节级降级，不拖垮整页）
    domains: z.record(PersonalStateDomainSchema.nullable()).default({}),
    lifecycle_counts: LifecycleCountsSchema.nullable().default(null),
    recent_changes: z.array(RecentChangeSchema).default([]),
  })
  .passthrough();

// data 整体为 null = 个人状态 Authority 失败，页面按 partial 降级
export const personalStateEnvelopeSchema = envelope(
  'personal_state.get',
  PersonalStateDataSchema.nullable().default(null),
);
export type PersonalStateEnvelope = z.infer<typeof personalStateEnvelopeSchema>;
export type PersonalStateData = z.infer<typeof PersonalStateDataSchema>;
export type PersonalStateDomain = z.infer<typeof PersonalStateDomainSchema>;
export type PersonalAssertion = z.infer<typeof PersonalAssertionSchema>;
export type RecentChange = z.infer<typeof RecentChangeSchema>;

/* ---------------- external_delta.get（Phase 37） ---------------- */

const ExternalSnapshotSchema = z
  .object({
    snapshot_id: z.string().nullish(),
    generated_at: z.string().nullish(),
  })
  .passthrough();

// 来源对象字段以后端真实数据为准：只锚定 source_id，其余宽松透传
const ExternalSourceSchema = z
  .object({
    source_id: z.string().nullish(),
  })
  .passthrough();

// freshness 是相对 snapshot.activated_at 派生的独立到期判断（服务端计算，
// 客户端只能格式化，不得用本地时钟重新推断）；与 lifecycle（External 权威自身
// 发布的记录状态）是两条独立轴，不合并成同一个客户端颜色字段（D-37-02）。
const ExternalFactFreshnessSchema = z
  .object({
    level: z.enum(['unknown', 'valid', 'expiring_soon', 'expired']),
    reason: z.string().nullable(),
  })
  .passthrough();

/**
 * canonical External fact DTO（Phase 37：D-37-02，锚定 `_external_delta_section`
 * 真实字段）：subject/predicate 命名轴 + 固定 来源/地区/有效期/quality/confidence/
 * lifecycle/conflict/freshness 字段；不再与 fact_type/observed_at/source_id 两套
 * 互相冲突的字段并存——安全关键字段一律 `.nullable()`（键恒在，可为 null），
 * 而不是用 `.nullish()`/`.passthrough()` 掩盖 producer/consumer 漂移（D-37 教训）。
 * fact_checksum 与 fact_id + 所属 data.snapshot.snapshot_id 一起构成
 * evidence.resolve 的稳定引用三元组（EVID-01）。
 */
const ExternalFactSchema = z
  .object({
    fact_id: z.string().nullable(),
    fact_checksum: z.string().nullable(),
    subject: z.string().nullable(),
    predicate: z.string().nullable(),
    region: z.string().nullable(),
    valid_from: z.string().nullable(),
    valid_to: z.string().nullable(),
    source_quality: z.union([z.number(), z.string()]).nullable(), // 真实数据为数值（如 0.99）
    fact_confidence: z.union([z.number(), z.string()]).nullable(),
    source_ids: z.array(z.string()).default([]),
    lifecycle: z.string().nullable(),
    conflict: z.boolean().nullable(),
    freshness: ExternalFactFreshnessSchema.nullable().default(null),
  })
  .passthrough();

const ExternalDeltaGroupsSchema = z
  .object({
    new: z.array(z.string()).default([]),
    updated: z.array(z.string()).default([]),
    expiring: z.array(z.string()).default([]),
    conflicts: z.array(z.string()).default([]),
  })
  .passthrough();

const ExternalCountsSchema = z
  .object({
    sources: z.number().nullish(),
    facts: z.number().nullish(),
    conflicts: z.number().nullish(),
  })
  .passthrough();

export const ExternalDeltaDataSchema = z
  .object({
    snapshot: ExternalSnapshotSchema.nullable().default(null),
    sources: z.array(ExternalSourceSchema).default([]),
    facts: z.array(ExternalFactSchema).default([]),
    delta: ExternalDeltaGroupsSchema.nullable().default(null),
    counts: ExternalCountsSchema.nullable().default(null),
  })
  .passthrough();

// data 整体为 null = 外部环境 Authority 失败，页面按 partial 降级
export const externalDeltaEnvelopeSchema = envelope(
  'external_delta.get',
  ExternalDeltaDataSchema.nullable().default(null),
);
export type ExternalDeltaEnvelope = z.infer<typeof externalDeltaEnvelopeSchema>;
export type ExternalDeltaData = z.infer<typeof ExternalDeltaDataSchema>;
export type ExternalFact = z.infer<typeof ExternalFactSchema>;
export type ExternalSource = z.infer<typeof ExternalSourceSchema>;

/* ---------------- decision_queue.get（Phase 38） ---------------- */

/** 六组看板键（与后端 _STAGE_KEYS 一致，恒在） */
export const DECISION_STAGE_KEYS = [
  'needs_attention',
  'awaiting_confirmation',
  'in_progress',
  'awaiting_outcome',
  'completed',
  'closed',
] as const;
export type DecisionStageKey = (typeof DECISION_STAGE_KEYS)[number];

// 队列卡片：锚定后端 _QUEUE_CARD_KEYS 真实字段名，宽松透传未知字段
const DecisionCardSchema = z
  .object({
    recommendation_id: z.string().nullable(),
    domain: z.string().nullable(),
    recommendation_kind: z.string().nullable(),
    horizon: z.string().nullable(),
    confidence: z.union([z.number(), z.string()]).nullable(),
    confirmation_state: z.string().nullable(),
    action_state: z.string().nullable(),
    expires_at: z.string().nullable(),
    current_sequence: z.number().nullable(),
    snapshot_id: z.string().nullable(),
  })
  .passthrough();

// 后端保证 data 恒为完整看板形状（decision 节失败时退化为全零 + partial/limitations 表达降级）
export const DecisionQueueDataSchema = z
  .object({
    total_available: z.number().nullable(),
    stage_counts: z.record(z.number()).default({}),
    stages: z.record(z.array(DecisionCardSchema)).default({}),
  })
  .passthrough();

export const decisionQueueEnvelopeSchema = envelope('decision_queue.get', DecisionQueueDataSchema);
export type DecisionQueueEnvelope = z.infer<typeof decisionQueueEnvelopeSchema>;
export type DecisionQueueData = z.infer<typeof DecisionQueueDataSchema>;
export type DecisionCard = z.infer<typeof DecisionCardSchema>;

/* ---------------- decision_workspace.get（Phase 38） ---------------- */

// support[] 证据引用：锚定 recommendations.get 真实暴露的键，宽松透传
const SupportEntrySchema = z
  .object({
    authority_id: z.string().nullish(),
    record_id: z.string().nullish(),
    source_run_id: z.string().nullish(),
    source_run_checksum: z.string().nullish(),
    snapshot_id: z.string().nullish(),
    cognitive_type: z.string().nullish(),
    provenance_class: z.string().nullish(),
    evidence_status: z.string().nullish(),
    uncertainty: z.union([z.string(), z.number(), z.array(z.string())]).nullish(), // 智能层 uncertainty 为列表语义
    record_checksum: z.string().nullish(),
  })
  .passthrough();

// 完整单条 recommendation：字段宽进宽出（nullish），缺字段由页面显式"未提供"
const RecommendationDetailSchema = z
  .object({
    recommendation_id: z.string().nullish(),
    recommendation_checksum: z.string().nullish(),
    run_id: z.string().nullish(),
    source_run_id: z.string().nullish(),
    snapshot_id: z.string().nullish(),
    policy_id: z.string().nullish(),
    subject: z.string().nullish(),
    domain: z.string().nullish(),
    scope: z.string().nullish(),
    recommendation_kind: z.string().nullish(),
    horizon: z.string().nullish(),
    confidence: z.union([z.number(), z.string()]).nullish(),
    uncertainty: z.union([z.string(), z.number(), z.array(z.string())]).nullish(), // 智能层 uncertainty 为列表语义
    expires_at: z.string().nullish(),
    rationale_codes: z.array(z.string()).default([]),
    support: z.array(SupportEntrySchema).default([]),
    confirmation_state: z.string().nullish(),
    action_state: z.string().nullish(),
    current_sequence: z.number().nullish(),
  })
  .passthrough();

// history 仅含链上校验字段（后端不暴露事件时间戳/status，见 envelope limitations）
const HistoryEventSchema = z
  .object({
    event_id: z.string().nullish(),
    sequence: z.number().nullish(),
    event_type: z.string().nullish(),
    typed_record_id: z.string().nullish(),
    previous_event_checksum: z.string().nullish(),
    payload_checksum: z.string().nullish(),
  })
  .passthrough();

// outcomes / effectiveness 同为 typed rows（字段集合一致），宽松锚定常用键
const TypedRecordSchema = z
  .object({
    causal_claim: z.boolean().nullish(),
    verdict: z.string().nullish(),
    rule_id: z.string().nullish(),
    rule_version: z.string().nullish(),
    record_type: z.string().nullish(),
    cognitive_type: z.string().nullish(),
    metric: z.union([z.string(), z.number()]).nullish(),
    unit: z.string().nullish(),
    adherence_status: z.string().nullish(),
    uncertainty: z.union([z.string(), z.number(), z.array(z.string())]).nullish(), // 真实返回为原因码数组
    payload_checksum: z.string().nullish(),
  })
  .passthrough();

// 节级降级：recommendation 可 null；数组节失败时后端给 [] + authorities 标记 error
export const DecisionWorkspaceDataSchema = z
  .object({
    recommendation: RecommendationDetailSchema.nullable().default(null),
    history: z.array(HistoryEventSchema).default([]),
    outcomes: z.array(TypedRecordSchema).default([]),
    effectiveness: z.array(TypedRecordSchema).default([]),
    linked_analysis_run_id: z.string().nullable().default(null),
  })
  .passthrough();

export const decisionWorkspaceEnvelopeSchema = envelope('decision_workspace.get', DecisionWorkspaceDataSchema);
export type DecisionWorkspaceEnvelope = z.infer<typeof decisionWorkspaceEnvelopeSchema>;
export type DecisionWorkspaceData = z.infer<typeof DecisionWorkspaceDataSchema>;
export type RecommendationDetail = z.infer<typeof RecommendationDetailSchema>;
export type SupportEntry = z.infer<typeof SupportEntrySchema>;
export type HistoryEvent = z.infer<typeof HistoryEventSchema>;
export type TypedRecord = z.infer<typeof TypedRecordSchema>;

/* ---------------- actions_recent.get（Phase 39） ---------------- */

/** 时间线六阶段键（与后端契约一致，恒在）；页面按此固定顺序渲染 */
export const ACTION_TIMELINE_STAGES = [
  'recommendation',
  'decision',
  'action_start',
  'action_complete',
  'outcome',
  'effectiveness',
] as const;
export type ActionTimelineStageKey = (typeof ACTION_TIMELINE_STAGES)[number];

const TimelineStageSchema = z
  .object({
    stage: z.string().nullish(),
    present: z.boolean().nullish(),
    event_id: z.string().nullish(),
    sequence: z.number().nullish(),
    checksum: z.string().nullish(),
  })
  .passthrough();

// outcome 真实字段不确定：宽松透传，缺字段由页面显式"未提供"
const ActionOutcomeRecordSchema = z
  .object({
    causal_claim: z.boolean().nullish(),
    verdict: z.string().nullish(),
  })
  .passthrough();

// effectiveness：锚定 causal_claim/verdict（非因果标注硬性需要），其余宽松透传
const ActionEffectivenessRecordSchema = z
  .object({
    causal_claim: z.boolean().nullish(),
    verdict: z.string().nullish(),
  })
  .passthrough();

// 单条组装失败时 error 存在，页面只降级该条
const ActionItemSchema = z
  .object({
    recommendation_id: z.string().nullish(),
    domain: z.string().nullish(),
    recommendation_kind: z.string().nullish(),
    confirmation_state: z.string().nullish(),
    action_state: z.string().nullish(),
    expires_at: z.string().nullish(),
    timeline: z.array(TimelineStageSchema).default([]),
    outcomes: z.array(ActionOutcomeRecordSchema).default([]),
    effectiveness: z.array(ActionEffectivenessRecordSchema).default([]),
    error: z.string().nullish(),
  })
  .passthrough();

export const ActionsRecentDataSchema = z
  .object({
    total_available: z.number().nullable(),
    shown: z.number().nullable(),
    with_outcome: z.number().nullable(),
    awaiting_outcome: z.number().nullable(),
    items: z.array(ActionItemSchema).default([]),
  })
  .passthrough();

export const actionsRecentEnvelopeSchema = envelope('actions_recent.get', ActionsRecentDataSchema);
export type ActionsRecentEnvelope = z.infer<typeof actionsRecentEnvelopeSchema>;
export type ActionsRecentData = z.infer<typeof ActionsRecentDataSchema>;
export type ActionItem = z.infer<typeof ActionItemSchema>;
export type ActionTimelineStage = z.infer<typeof TimelineStageSchema>;
export type ActionOutcomeRecord = z.infer<typeof ActionOutcomeRecordSchema>;
export type ActionEffectivenessRecord = z.infer<typeof ActionEffectivenessRecordSchema>;

/* ---------------- proactive_summary.get（Phase 39） ---------------- */

// 候选卡：锚定契约真实字段名，宽松透传未知字段；importance 结构不定，页面尽力解析
const ProactiveSummaryCardSchema = z
  .object({
    candidate_id: z.string().nullish(),
    domains: z.array(z.string()).default([]),
    candidate_class: z.string().nullish(),
    presentation_kind: z.string().nullish(),
    importance: z.record(z.unknown()).default({}),
    expires_at: z.string().nullish(),
    valid_from: z.string().nullish(),
    reason_codes: z.array(z.string()).default([]),
    current_control_eligible: z.boolean().nullish(),
    current_control_reason_codes: z.array(z.string()).default([]),
  })
  .passthrough();

// 已抑制/冷却中/历史不列入 eligible inbox：groups 只有 now/deferrable 两键
const ProactiveGroupsSchema = z
  .object({
    now: z.array(ProactiveSummaryCardSchema).default([]),
    deferrable: z.array(ProactiveSummaryCardSchema).default([]),
  })
  .passthrough();

export const ProactiveSummaryDataSchema = z
  .object({
    total_available: z.number().nullable(),
    // 节可 null：proactive Authority 部分失败时 groups/metrics 为 null，页面按节降级
    groups: ProactiveGroupsSchema.nullable().default(null),
    metrics: z.record(z.unknown()).nullable().default(null),
    notes: z.array(z.string()).default([]),
  })
  .passthrough();

export const proactiveSummaryEnvelopeSchema = envelope('proactive_summary.get', ProactiveSummaryDataSchema);
export type ProactiveSummaryEnvelope = z.infer<typeof proactiveSummaryEnvelopeSchema>;
export type ProactiveSummaryData = z.infer<typeof ProactiveSummaryDataSchema>;
export type ProactiveSummaryCard = z.infer<typeof ProactiveSummaryCardSchema>;

/* ---------------- calibration_overview.get（Phase 39） ---------------- */

// 单条协议组装失败时 error 存在，页面只降级该条
const CalibrationProtocolSchema = z
  .object({
    protocol_id: z.string().nullish(),
    status: z.string().nullish(),
    verdict: z.string().nullish(),
    causal_claim: z.boolean().nullish(),
    inconclusive_reasons: z.array(z.string()).default([]),
    sample_size: z.number().nullish(),
    summary_limitations: z.array(z.string()).default([]),
    error: z.string().nullish(),
  })
  .passthrough();

export const CalibrationOverviewDataSchema = z
  .object({
    total: z.number().nullable(),
    shown: z.number().nullable(),
    protocols: z.array(CalibrationProtocolSchema).default([]),
  })
  .passthrough();

export const calibrationOverviewEnvelopeSchema = envelope(
  'calibration_overview.get',
  CalibrationOverviewDataSchema,
);
export type CalibrationOverviewEnvelope = z.infer<typeof calibrationOverviewEnvelopeSchema>;
export type CalibrationOverviewData = z.infer<typeof CalibrationOverviewDataSchema>;
export type CalibrationProtocol = z.infer<typeof CalibrationProtocolSchema>;

/* ---------------- evidence_resolve.get（Phase 37：EVID-01） ---------------- */

/** 三种类型化引用，与后端 `_EVIDENCE_SUBJECT_TYPES` 一致（唯一只读证据下钻入口） */
export const EVIDENCE_SUBJECT_TYPES = ['personal_state', 'external_fact', 'decision'] as const;
export type EvidenceSubjectType = (typeof EVIDENCE_SUBJECT_TYPES)[number];

/**
 * 解析结果的固定 status 词表（与后端 `_EVIDENCE_RESULT_STATUSES` 一致）：
 * mismatch/expired/abstain/not_found/authority_unavailable 都是可区分的安全降级，
 * 绝不是"回退到最新记录"或未分类的通用错误。
 */
export const EVIDENCE_RESOLVE_STATUSES = [
  'ok',
  'mismatch',
  'expired',
  'abstain',
  'not_found',
  'authority_unavailable',
] as const;
export type EvidenceResolveStatus = (typeof EVIDENCE_RESOLVE_STATUSES)[number];

// 回显的引用：服务端结构校验后原样带回，供前端关联请求与响应（不作为渲染真值来源）
const EvidenceReferenceSchema = z
  .object({
    subject_type: z.string().nullable(),
    stable_id: z.string().nullable(),
    snapshot_id: z.string().nullable(),
    checksum: z.string().nullable(),
  })
  .passthrough();

// 证据条目：只有 ref/artifact_type/status/eligible/privacy_class，不含明文值
const EvidenceItemStatusSchema = z
  .object({
    ref: z.string().nullish(),
    artifact_type: z.string().nullish(),
    status: z.string().nullish(),
    eligible: z.boolean().nullish(),
    privacy_class: z.string().nullish(),
  })
  .passthrough();

/**
 * 三种 subject 的 result 字段并集：所有字段 nullish（哪些字段出现取决于
 * reference.subject_type），页面按 subject_type 判别取用对应字段，不臆造缺失轴。
 * status !== 'ok'/'abstain' 时 result 为 null（见 EvidenceResolveDataSchema）。
 */
const EvidenceResultSchema = z
  .object({
    subject_type: z.string().nullish(),
    stable_id: z.string().nullish(),
    snapshot_id: z.string().nullish(),
    checksum: z.string().nullish(),
    // personal_state
    key: AssertionKeySchema.nullish(),
    record_lifecycle: z.string().nullish(),
    provenance_class: z.string().nullish(),
    confidence: z.union([z.number(), z.string()]).nullish(),
    as_of: z.string().nullish(),
    evidence: z.array(EvidenceItemStatusSchema).default([]),
    uncertainty: z.array(z.string()).default([]),
    // external_fact（与 ExternalFactSchema 同一隐私边界，不含 raw value）
    subject: z.string().nullish(),
    predicate: z.string().nullish(),
    region: z.string().nullish(),
    valid_from: z.string().nullish(),
    valid_to: z.string().nullish(),
    source_quality: z.union([z.number(), z.string()]).nullish(),
    fact_confidence: z.union([z.number(), z.string()]).nullish(),
    lifecycle: z.string().nullish(),
    // decision
    confirmation_state: z.string().nullish(),
    action_state: z.string().nullish(),
    recommendation_kind: z.string().nullish(),
    domain: z.string().nullish(),
    rationale_codes: z.array(z.string()).default([]),
    support: z.array(SupportEntrySchema).default([]),
  })
  .passthrough();

export const EvidenceResolveDataSchema = z
  .object({
    status: z.enum(EVIDENCE_RESOLVE_STATUSES),
    reference: EvidenceReferenceSchema,
    // ok/abstain 才有 result；mismatch/expired/not_found/authority_unavailable 恒为 null
    result: EvidenceResultSchema.nullable().default(null),
    next_actions: z.array(z.string()).default([]),
  })
  .passthrough();

export const evidenceResolveEnvelopeSchema = envelope('evidence_resolve.get', EvidenceResolveDataSchema);
export type EvidenceResolveEnvelope = z.infer<typeof evidenceResolveEnvelopeSchema>;
export type EvidenceResolveData = z.infer<typeof EvidenceResolveDataSchema>;
export type EvidenceResult = z.infer<typeof EvidenceResultSchema>;
export type EvidenceReference = z.infer<typeof EvidenceReferenceSchema>;
