import { Link } from 'react-router-dom';
import type { ApiError } from '../../api/client';
import { useWikiTopicList } from '../../api/hooks';
import type { WikiTopicCard } from '../../api/schemas';
import { FreshnessBadge } from '../../components/feedback/FreshnessBadge';
import { StatePanel } from '../../components/feedback/StatePanel';

function topicLabel(topic: WikiTopicCard): string {
  return topic.display_label ?? `${topic.topic_type} topic`;
}

function projectionStatus(value: string | null | undefined): string {
  return value === 'fresh' ? 'fresh' : value === 'stale' ? 'stale' : value === 'partial' ? 'partial' : value === 'missing' ? 'missing' : value === 'unavailable' ? 'unavailable' : 'unknown';
}

function errorPanel(query: ReturnType<typeof useWikiTopicList>) {
  const error = query.error as ApiError | undefined;
  const offline = error?.code === 'network_error';
  return (
    <StatePanel
      variant={offline ? 'offline' : 'error'}
      title={offline ? '知识目录服务不可达' : '知识目录加载失败'}
      errorMessage={error?.message ?? '无法确认 Wiki 目录状态'}
      onRetry={() => void query.refetch()}
    />
  );
}

export function KnowledgeDirectoryPage() {
  const query = useWikiTopicList();

  if (query.isPending) return <StatePanel variant="loading" />;
  if (query.isError || !query.data) return errorPanel(query);

  const envelope = query.data;
  if (!envelope.ok || envelope.status === 'unavailable' || !envelope.data) {
    return (
      <StatePanel
        variant="error"
        title="Wiki 目录暂不可用"
        errorMessage={envelope.error ?? '服务器未发布可用的 Wiki 目录'}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const topics = envelope.data.items;
  return (
    <div className="section-stack">
      <header className="card">
        <h1 className="text-lg font-semibold">知识与证据</h1>
        <p className="mt-2 text-sm text-muted">
          这里只浏览服务器已发布的 Project、Goal、Decision 只读投影；页面不是新的事实库，也不提供确认或行动写入。
        </p>
      </header>

      {envelope.partial || envelope.status === 'partial' ? (
        <StatePanel
          variant="partial"
          title="目录部分可用"
          description={envelope.limitations.join('；') || '部分 Authority 暂不可用，列表不代表完整目录。'}
          unavailableAuthorities={Object.entries(envelope.authorities).filter(([, value]) => value === 'error').map(([key]) => key)}
        />
      ) : null}

      {topics.length === 0 ? (
        <StatePanel
          variant="empty"
          title="暂时没有已发布主题"
          description="这表示当前 Authority 没有可证明的 P0 Topic，不等于数据已被清空。"
          nextStep="稍后刷新或从个人状态、决策中心进入已有对象。"
        />
      ) : (
        <section aria-labelledby="wiki-topic-directory-title">
          <h2 id="wiki-topic-directory-title" className="sr-only">P0 主题目录</h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {topics.map((topic) => (
              <Link
                key={topic.topic_id}
                to={`/knowledge/${topic.topic_type}/${encodeURIComponent(topic.topic_id)}`}
                className="card block min-w-0 transition-colors hover:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
                aria-label={`打开${topicLabel(topic)}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs uppercase tracking-wide text-muted">{topic.topic_type}</p>
                    <h3 className="mt-1 break-words font-medium">{topicLabel(topic)}</h3>
                  </div>
                  <span className="badge shrink-0 border-line bg-panel text-muted">只读</span>
                </div>
                <p className="mt-3 break-all text-xs text-muted">opaque id：{topic.topic_id}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <FreshnessBadge asOf={envelope.generated_at} />
                  <span className="badge border-line bg-panel text-muted">投影：{projectionStatus(topic.freshness ?? envelope.freshness.state)}</span>
                  <span className="text-xs text-muted">authority：{topic.authority ?? 'unknown'}</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      <p className="text-xs text-muted">
        证据仍通过既有只读 Evidence 路径查看：<Link className="text-primary hover:underline" to="/evidence">打开证据中心</Link>。
      </p>
    </div>
  );
}
