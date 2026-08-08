import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { ApiError } from '../../api/client';
import type { EvidenceReferenceInput } from '../../api/hooks';
import { useWikiTopic, useWikiTopicBacklinks, useWikiTopicResolve } from '../../api/hooks';
import type { WikiClaim, WikiTopicType } from '../../api/schemas';
import { EvidenceDrawer } from '../../components/evidence/EvidenceDrawer';
import { FreshnessBadge } from '../../components/feedback/FreshnessBadge';
import { StatePanel } from '../../components/feedback/StatePanel';

const TOPIC_TYPES: readonly WikiTopicType[] = ['project', 'goal', 'decision'];

function claimTitle(claim: WikiClaim): string {
  if (claim.recommendation_id) return `Recommendation ${claim.recommendation_id}`;
  if (claim.key?.predicate) return claim.key.predicate;
  return claim.claim_type ?? '未命名记录';
}

function claimEvidenceReference(claim: WikiClaim): EvidenceReferenceInput | null {
  const ref = claim.authority_ref;
  if (!ref?.record_id || !ref.snapshot_id || !ref.checksum) return null;
  if (ref.authority_id === 'a.personal_state') {
    const key = claim.key;
    if (!key?.assertion_kind || !key.subject || !key.domain || !key.scope || !key.predicate) return null;
    return {
      subjectType: 'personal_state',
      stableId: ref.record_id,
      snapshotId: ref.snapshot_id,
      checksum: ref.checksum,
      stateKey: {
        assertion_kind: key.assertion_kind,
        subject: key.subject,
        domain: key.domain,
        scope: key.scope,
        predicate: key.predicate,
      },
    };
  }
  if (ref.authority_id === 'a.external_context') {
    return { subjectType: 'external_fact', stableId: ref.record_id, snapshotId: ref.snapshot_id, checksum: ref.checksum };
  }
  if (ref.authority_id === 'a.decision_feedback') {
    if (claim.claim_type !== 'recommendation') return null;
    return { subjectType: 'decision', stableId: ref.record_id, snapshotId: ref.snapshot_id, checksum: ref.checksum };
  }
  return null;
}

function ClaimList({ title, claims, description, onOpenEvidence }: { title: string; claims: WikiClaim[]; description: string; onOpenEvidence: (reference: EvidenceReferenceInput, label: string) => void }) {
  return (
    <section className="card" aria-labelledby={`claims-${title}`}>
      <h2 id={`claims-${title}`} className="font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-muted">{description}</p>
      {claims.length === 0 ? (
        <p className="mt-3 text-sm text-muted">暂无可证明记录。</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {claims.map((claim, index) => (
            <li key={`${claim.authority_ref?.record_id ?? claimTitle(claim)}-${index}`} className="rounded-md border border-line bg-surface p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="break-words font-medium">{claimTitle(claim)}</p>
                <span className="badge border-line bg-panel text-muted">{claim.status ?? claim.claim_type ?? '未分类'}</span>
              </div>
              <dl className="mt-2 grid gap-1 text-xs text-muted sm:grid-cols-2">
                {claim.authority_ref ? <div><dt className="inline">authority： </dt><dd className="inline">{claim.authority_ref.authority_id}</dd></div> : null}
                {claim.authority_ref?.snapshot_id ? <div><dt className="inline">snapshot： </dt><dd className="inline break-all">{claim.authority_ref.snapshot_id}</dd></div> : null}
                {claim.authority_ref?.checksum ? <div><dt className="inline">checksum： </dt><dd className="inline break-all">{claim.authority_ref.checksum}</dd></div> : null}
                {claim.confidence !== null && claim.confidence !== undefined ? <div><dt className="inline">confidence： </dt><dd className="inline">{String(claim.confidence)}</dd></div> : null}
              </dl>
              {claim.uncertainty.length > 0 ? <p className="mt-2 text-xs text-uncertainty">限制：{claim.uncertainty.join('；')}</p> : null}
              {claim.evidence_refs.length > 0 ? <Link to="/evidence" className="mt-2 mr-3 inline-block text-xs text-primary hover:underline">查看受限证据引用</Link> : null}
              {(() => {
                const reference = claimEvidenceReference(claim);
                return reference ? <button type="button" className="mt-2 text-xs text-primary hover:underline" onClick={() => onOpenEvidence(reference, claimTitle(claim))}>打开只读证据抽屉</button> : null;
              })()}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function TopicPage() {
  const params = useParams<{ topicType: string; topicId: string }>();
  const topicType = TOPIC_TYPES.includes(params.topicType as WikiTopicType) ? params.topicType as WikiTopicType : undefined;
  const topicId = params.topicId;
  const query = useWikiTopic(topicType, topicId);
  const backlinks = useWikiTopicBacklinks(topicType, topicId);
  const resolveQuery = useWikiTopicResolve(query.data?.data?.topic.canonical_key);
  const [openEvidence, setOpenEvidence] = useState<{ reference: EvidenceReferenceInput; label: string } | null>(null);

  if (!topicType) return <StatePanel variant="error" title="主题类型无效" errorMessage="路由不是受支持的 Project、Goal 或 Decision 类型。" />;
  if (query.isPending) return <StatePanel variant="loading" />;
  if (query.isError || !query.data) {
    const error = query.error as ApiError | undefined;
    return <StatePanel variant={error?.code === 'network_error' ? 'offline' : 'error'} title="主题投影不可用" errorMessage={error?.message} onRetry={() => void query.refetch()} />;
  }
  if (!query.data.ok || !query.data.data) {
    return <StatePanel variant="error" title="主题投影不可用" errorMessage={query.data.error ?? '服务器未返回主题内容'} onRetry={() => void query.refetch()} />;
  }

  const { topic, claims } = query.data.data;
  const resolveData = resolveQuery.data?.ok && resolveQuery.data.data ? resolveQuery.data.data : null;
  const projectionState = query.data.status ?? query.data.freshness.state ?? 'unavailable';
  const isPartial = query.data.partial || query.data.status === 'partial';
  return (
    <div className="section-stack">
      <p><Link to="/knowledge" className="text-sm text-primary hover:underline">← 返回知识目录</Link></p>
      <header className="card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wide text-muted">{topic.topic_type}</p>
            <h1 className="mt-1 break-all text-lg font-semibold">{topic.display_label ?? topic.canonical_key}</h1>
            <p className="mt-2 break-all text-xs text-muted">opaque id：{topic.topic_id}</p>
          </div>
          <FreshnessBadge asOf={query.data.generated_at} />
        </div>
        <p className="mt-3 text-sm text-muted">projection checksum：<span className="break-all">{query.data.projection_checksum ?? '未提供'}</span></p>
        {resolveData ? <p className="mt-2 text-sm text-muted">本次读取来源：<span className="font-medium text-ink">{resolveData.selected_source}</span>{resolveData.fallback_reason ? `（${resolveData.fallback_reason}）` : ''}</p> : null}
      </header>

      {projectionState === 'stale' ? <StatePanel variant="stale" title="主题投影已偏旧" description={query.data.limitations.join('；') || 'serving snapshot 已变化；当前页面不会把旧投影标为 fresh。'} /> : null}
      {isPartial ? <StatePanel variant="partial" title="主题部分可用" description={query.data.limitations.join('；')} /> : null}

      <ClaimList title="当前上下文" claims={claims.current} description="只呈现当前 authority 中可重建的元数据，不展开原始正文。" onOpenEvidence={(reference, label) => setOpenEvidence({ reference, label })} />
      <ClaimList title="观察与不确定性" claims={[...claims.observations, ...claims.inferences]} description="观察、推断和不确定性不会被提升为确定事实。" onOpenEvidence={(reference, label) => setOpenEvidence({ reference, label })} />
      <ClaimList title="建议与决策反馈" claims={[...claims.recommendations, ...claims.decision_feedback]} description="Decision 反馈保留 non-causal 限制；Wiki 不提供确认、行动或结果录入。" onOpenEvidence={(reference, label) => setOpenEvidence({ reference, label })} />
      <ClaimList title="历史与冲突" claims={[...claims.historical, ...claims.conflicts]} description="历史和冲突只被陈述，不自动选择结论。" onOpenEvidence={(reference, label) => setOpenEvidence({ reference, label })} />
      <ClaimList title="External context" claims={claims.external} description="External 事实保持独立，不写入 Personal 区域。" onOpenEvidence={(reference, label) => setOpenEvidence({ reference, label })} />

      <section className="card" aria-labelledby="topic-backlinks-title">
        <h2 id="topic-backlinks-title" className="font-semibold">显式关联</h2>
        {backlinks.isPending ? <p className="mt-2 text-sm text-muted">正在读取关联…</p> : backlinks.data?.ok && backlinks.data.data ? (
          backlinks.data.data.links.length === 0 ? <p className="mt-2 text-sm text-muted">没有可证明的显式关联。</p> : (
            <ul className="mt-3 space-y-2 text-sm">{backlinks.data.data.links.map((link, index) => <li key={`${link.relation_type}-${index}`} className="rounded-md border border-line p-2"><span className="font-medium">{link.relation_type}</span><span className="ml-2 text-muted">依据：{link.join_basis}</span></li>)}</ul>
          )
        ) : <p className="mt-2 text-sm text-muted">关联暂不可用，未用相似度或模型推断补齐。</p>}
      </section>

      <p className="text-xs text-muted">需要执行决策操作时，请返回既有决策中心；本 Wiki 页面没有确认或写入入口。<Link to="/decisions" className="ml-1 text-primary hover:underline">打开决策中心</Link> · <Link to="/evidence" className="text-primary hover:underline">打开证据中心</Link></p>
      {openEvidence ? <EvidenceDrawer reference={openEvidence.reference} subjectLabel={openEvidence.label} onClose={() => setOpenEvidence(null)} /> : null}
    </div>
  );
}
