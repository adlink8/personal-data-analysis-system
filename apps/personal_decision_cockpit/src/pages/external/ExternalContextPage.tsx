import { useMemo, useState } from 'react';
import type { ApiError } from '../../api/client';
import { useExternalDelta } from '../../api/hooks';
import type { ExternalDeltaData, ExternalDeltaEnvelope, ExternalFact, ExternalSource } from '../../api/schemas';
import { SnapshotChip, shortId } from '../../components/authority/SnapshotChip';
import { FreshnessBadge } from '../../components/feedback/FreshnessBadge';
import { StatePanel } from '../../components/feedback/StatePanel';
import { IconAlertTriangle, IconArrowLeftRight, IconClock, IconInfo, IconRefresh } from '../../components/icons';
import { fmtNumber, fmtTime } from '../../utils/format';

/**
 * 外部环境（spec §7.5）：Active External Snapshot、Delta 四组（新增/更新/即将过期/冲突）、
 * 来源 Allowlist 列表与地区/类型客户端筛选（只读，不打 API）。
 * 硬性要求：显著提示"外部事实不会自动成为个人事实。"；
 * 事实字段宽松渲染，缺失一律显式"未提供"，不崩。
 */

type IconComponent = typeof IconInfo;

/* ---------------- Delta 分组元数据（颜色一律配文字 + 图标，spec §9.2） ---------------- */

interface DeltaGroupMeta {
  key: 'new' | 'updated' | 'expiring' | 'conflicts';
  label: string;
  description: string;
  textClass: string;
  Icon: IconComponent;
}

const DELTA_GROUPS: ReadonlyArray<DeltaGroupMeta> = [
  { key: 'new', label: '新增', description: '本次快照新出现的外部事实', textClass: 'text-external', Icon: IconInfo },
  { key: 'updated', label: '更新', description: '相对上一快照内容有更新', textClass: 'text-primary', Icon: IconRefresh },
  { key: 'expiring', label: '即将过期', description: '有效期临近，需关注是否仍然有效', textClass: 'text-uncertainty', Icon: IconClock },
  { key: 'conflicts', label: '冲突', description: '来源间存在冲突，系统不会自动选边', textClass: 'text-risk', Icon: IconArrowLeftRight },
];

/* ---------------- 字段读取辅助（后端字段名可能微调） ---------------- */

function pickString(obj: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === 'string' && value !== '') return value;
  }
  return null;
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.filter((v): v is string => typeof v === 'string' && v !== ''))].sort();
}

function errorAuthorities(envelope: ExternalDeltaEnvelope): string[] {
  return Object.entries(envelope.authorities)
    .filter(([, value]) => value === 'error')
    .map(([name]) => name);
}

/* ---------------- 事实卡 ---------------- */

function FactField({ label, value, mono }: { label: string; value: string | number | null | undefined; mono?: boolean }) {
  return (
    <div className="break-words">
      <dt className="inline text-muted">{label}：</dt>
      <dd className={`inline ${mono ? 'font-mono' : ''}`}>{value ?? '未提供'}</dd>
    </div>
  );
}

function validRangeText(from: string | null | undefined, to: string | null): string {
  if (!from && !to) return '未提供';
  return `${from ? fmtTime(from) : '—'} ~ ${to ? fmtTime(to) : '—'}`;
}

function ExternalFactCard({ fact }: { fact: ExternalFact }) {
  // valid_to 与 valid_at 两种命名都接受（后端并行开发，字段名可能微调）
  const validTo = fact.valid_to ?? pickString(fact, ['valid_at']);
  return (
    <li className="rounded-lg border border-line bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm" title={fact.fact_id ?? undefined}>
          {fact.fact_id ? shortId(fact.fact_id) : '（无 ID）'}
        </span>
        {/* canonical DTO 用 subject/predicate 命名轴（Phase 37：D-37-02），
            不再有独立 fact_type 字段;predicate 承担同样的"类型"展示作用 */}
        <span className="badge border-line bg-panel text-muted">{fact.predicate ?? '未提供'}</span>
        {fact.lifecycle ? (
          <span className="badge border-line bg-panel text-muted">{fact.lifecycle}</span>
        ) : null}
        {fact.conflict ? (
          <span className="badge border-risk bg-risk-soft text-risk">
            <IconArrowLeftRight className="h-3.5 w-3.5" />
            冲突
          </span>
        ) : null}
        {/* 未来（37-02）应改为直接渲染服务端 fact.freshness.level/reason，
            而非本组件当前的本地时钟推断;此处先接入 valid_from 保持可编译 */}
        <FreshnessBadge asOf={fact.valid_from ?? null} />
      </div>
      <dl className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
        <FactField label="主体" value={fact.subject} mono />
        <FactField label="地区" value={fact.region} />
        <FactField label="来源" value={fact.source_ids?.[0] ?? null} mono />
        <FactField label="来源质量" value={fact.source_quality} />
        <FactField label="事实置信度" value={fact.fact_confidence} />
        <div>
          <dt className="inline text-muted">有效期：</dt>
          <dd className="inline">{validRangeText(fact.valid_from, validTo)}</dd>
        </div>
      </dl>
    </li>
  );
}

/* ---------------- Delta 分组 ---------------- */

function DeltaGroupSection({
  meta,
  ids,
  factById,
}: {
  meta: DeltaGroupMeta;
  ids: string[];
  factById: Map<string, ExternalFact>;
}) {
  const Icon = meta.Icon;
  return (
    <section className="card" aria-labelledby={`delta-${meta.key}-title`}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 id={`delta-${meta.key}-title`} className={`flex items-center gap-1.5 font-semibold ${meta.textClass}`}>
          <Icon className="h-4 w-4" />
          {meta.label}
        </h2>
        <span className="badge border-line bg-panel text-muted">{ids.length} 条</span>
      </div>
      <p className="mt-0.5 text-sm text-muted">{meta.description}</p>
      {ids.length === 0 ? (
        <p className="mt-3 text-sm text-muted">无</p>
      ) : (
        <ul className="section-stack mt-3">
          {ids.map((id) => {
            const fact = factById.get(id);
            return fact ? (
              <ExternalFactCard key={id} fact={fact} />
            ) : (
              <li key={id} className="rounded-lg border border-line bg-surface p-3 text-sm text-muted">
                事实 <span className="font-mono">{shortId(id)}</span>{' '}
                的详情未包含在本次投影中（或已被当前筛选条件排除）。
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/* ---------------- 来源列表 ---------------- */

function sourceName(source: ExternalSource): string {
  return pickString(source, ['name', 'title', 'display_name']) ?? '未提供';
}

function allowlistText(source: ExternalSource): string {
  const status = pickString(source, ['allowlist_status', 'status']);
  if (status) return status;
  for (const key of ['allowlisted', 'allowed']) {
    const value = source[key];
    if (typeof value === 'boolean') return value ? '已允许' : '未允许';
  }
  return '未提供';
}

function SourcesCard({ sources }: { sources: ExternalSource[] }) {
  return (
    <section className="card" aria-labelledby="sources-title">
      <h2 id="sources-title" className="font-semibold">
        来源列表
      </h2>
      <p className="mt-0.5 text-sm text-muted">Allowlist 内的外部来源；未在列表中的来源不会进入快照。</p>
      {sources.length === 0 ? (
        <div className="mt-3">
          <StatePanel variant="empty" title="暂无来源信息" description="本次投影未返回任何外部来源。" />
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full border-collapse text-sm">
            <caption className="sr-only">外部环境来源与 Allowlist 状态</caption>
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th scope="col" className="py-2 pr-4 font-medium">
                  来源 ID
                </th>
                <th scope="col" className="py-2 pr-4 font-medium">
                  名称
                </th>
                <th scope="col" className="py-2 pr-4 font-medium">
                  Allowlist 状态
                </th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source, index) => (
                <tr key={source.source_id ?? `source-${index}`} className="border-b border-line last:border-0">
                  <td className="py-2 pr-4 font-mono">{source.source_id ?? '未提供'}</td>
                  <td className="py-2 pr-4">{sourceName(source)}</td>
                  <td className="py-2 pr-4">{allowlistText(source)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/* ---------------- 页面主体 ---------------- */

function ExternalBody({
  data,
  region,
  factType,
  onRegionChange,
  onFactTypeChange,
}: {
  data: ExternalDeltaData;
  region: string;
  factType: string;
  onRegionChange: (value: string) => void;
  onFactTypeChange: (value: string) => void;
}) {
  const facts = data.facts;

  const regionOptions = useMemo(() => uniqueStrings(facts.map((f) => f.region)), [facts]);
  // canonical DTO 无独立 fact_type;predicate 承担同样的"类型"筛选维度（Phase 37：D-37-02）
  const typeOptions = useMemo(() => uniqueStrings(facts.map((f) => f.predicate)), [facts]);

  // 纯客户端筛选（spec §13.1：筛选不写入、不打 API）
  const filteredFacts = useMemo(
    () =>
      facts.filter(
        (f) => (region === 'all' || f.region === region) && (factType === 'all' || f.predicate === factType),
      ),
    [facts, region, factType],
  );

  const factById = useMemo(() => {
    const map = new Map<string, ExternalFact>();
    for (const fact of filteredFacts) {
      if (fact.fact_id) map.set(fact.fact_id, fact);
    }
    return map;
  }, [filteredFacts]);

  const conflictCount = data.counts?.conflicts ?? 0;
  const isFiltering = region !== 'all' || factType !== 'all';

  return (
    <>
      <header className="card">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold">外部环境</h1>
          <SnapshotChip label="External" snapshotId={data.snapshot?.snapshot_id ?? null} />
          <FreshnessBadge asOf={data.snapshot?.generated_at ?? null} />
        </div>
        <p className="mt-2 text-sm text-muted">快照生成于 {fmtTime(data.snapshot?.generated_at)}</p>
        <ul className="mt-3 flex flex-wrap gap-2" aria-label="快照计数">
          <li className="badge border-line bg-panel text-ink">
            来源 <span className="font-medium">{fmtNumber(data.counts?.sources)}</span>
          </li>
          <li className="badge border-line bg-panel text-ink">
            事实 <span className="font-medium">{fmtNumber(data.counts?.facts)}</span>
          </li>
          <li
            className={`badge ${conflictCount > 0 ? 'border-risk bg-risk-soft text-risk' : 'border-line bg-panel text-ink'}`}
          >
            <IconArrowLeftRight className="h-3.5 w-3.5" />
            冲突 <span className="font-medium">{fmtNumber(data.counts?.conflicts)}</span>
          </li>
        </ul>
      </header>

      {/* spec §7.5 硬性要求：外部与个人事实明确隔离 */}
      <div className="card border-external bg-external-soft" role="note">
        <p className="flex items-center gap-2 text-sm font-medium text-external">
          <IconInfo className="h-4 w-4 shrink-0" />
          外部事实不会自动成为个人事实。
        </p>
      </div>

      <section className="card" aria-label="事实筛选">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex items-center gap-2">
            <label htmlFor="region-filter" className="text-sm font-medium">
              地区
            </label>
            <select
              id="region-filter"
              value={region}
              onChange={(event) => onRegionChange(event.target.value)}
              className="rounded-md border border-line bg-panel px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="all">全部地区</option>
              {regionOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="fact-type-filter" className="text-sm font-medium">
              类型
            </label>
            <select
              id="fact-type-filter"
              value={factType}
              onChange={(event) => onFactTypeChange(event.target.value)}
              className="rounded-md border border-line bg-panel px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="all">全部类型</option>
              {typeOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          {isFiltering ? (
            <button
              type="button"
              onClick={() => {
                onRegionChange('all');
                onFactTypeChange('all');
              }}
              className="text-sm text-primary transition-colors hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
            >
              清除筛选
            </button>
          ) : null}
        </div>
      </section>

      <p className="px-1 text-xs text-muted">
        Delta 视图仅展示本次快照中新增、更新、即将过期或冲突的事实；快照全量事实数见顶部计数。
      </p>

      {data.delta === null ? (
        <section className="card" aria-labelledby="delta-fallback-title">
          <h2 id="delta-fallback-title" className="font-semibold">
            全部事实
          </h2>
          <p className="mt-0.5 text-sm text-muted">本次投影未提供 Delta 分组，以下为筛选后的全部事实。</p>
          {filteredFacts.length === 0 ? (
            <div className="mt-3">
              <StatePanel
                variant="empty"
                title="没有符合筛选条件的事实"
                description="当前快照没有外部事实，或筛选条件过严。"
              />
            </div>
          ) : (
            <ul className="section-stack mt-3">
              {filteredFacts.map((fact, index) => (
                <ExternalFactCard key={fact.fact_id ?? `fact-${index}`} fact={fact} />
              ))}
            </ul>
          )}
        </section>
      ) : (
        DELTA_GROUPS.map((meta) => (
          <DeltaGroupSection key={meta.key} meta={meta} ids={data.delta?.[meta.key] ?? []} factById={factById} />
        ))
      )}

      <SourcesCard sources={data.sources} />
    </>
  );
}

export function ExternalContextPage() {
  const query = useExternalDelta();
  const [region, setRegion] = useState('all');
  const [factType, setFactType] = useState('all');

  if (query.isPending) {
    return (
      <div className="section-stack" aria-label="外部环境加载中">
        <StatePanel variant="loading" />
        <StatePanel variant="loading" />
        <StatePanel variant="loading" />
      </div>
    );
  }

  if (query.isError) {
    const err = query.error as ApiError;
    return (
      <StatePanel
        variant="error"
        title="外部环境加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const envelope = query.data;
  const { data } = envelope;

  return (
    <div className="section-stack">
      {/* 部分失败提示条：不伪装完整成功（spec §11.3） */}
      {envelope.partial || envelope.limitations.length > 0 ? (
        <div className="card border-uncertainty bg-uncertainty-soft" role="status">
          <p className="flex items-center gap-2 text-sm font-medium text-uncertainty">
            <IconAlertTriangle />
            本次投影为部分可用
          </p>
          {envelope.limitations.length > 0 ? (
            <ul className="mt-1 list-disc pl-8 text-sm text-muted">
              {envelope.limitations.map((limitation, i) => (
                <li key={i}>{limitation}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {data === null ? (
        <StatePanel
          variant="partial"
          title="外部环境暂不可用"
          unavailableAuthorities={errorAuthorities(envelope)}
          description="外部环境 Authority 本次未返回数据，其余页面不受影响。"
        />
      ) : (
        <ExternalBody
          data={data}
          region={region}
          factType={factType}
          onRegionChange={setRegion}
          onFactTypeChange={setFactType}
        />
      )}
    </div>
  );
}
