// 证据中心（spec §7.7，Phase 37 Plan 03 Task 3，D-37-05/D-37-06）：
// current-object Evidence Drawer（Personal/External/决策工作区的"查看证据"入口）是唯一
// 权威的只读证据下钻路径；本页只负责说明这一点，并把遗留 MCP Widget（Data Browser、
// Memory Graph、Relation Review）收口到显式的"诊断 / 历史集成"区域——它们是受限的
// 只读辅助工具，不是当前 Personal State SSOT，Widget 加载失败或超时也不会被静默为空白页。
import type { ApiError } from '../../api/client';
import { useSystemStatus } from '../../api/hooks';
import { WidgetDiagnosticCard } from '../../components/evidence/WidgetDiagnosticCard';
import { StatePanel } from '../../components/feedback/StatePanel';
import { IconInfo, IconSearch } from '../../components/icons';

const WIDGETS = [
  {
    file: 'data-browser-widget.html',
    title: '数据浏览器',
    description: '浏览个人数据条目与证据记录，支持单条下钻（历史诊断视图）。',
    historicalNote: null,
  },
  {
    file: 'memory-graph-widget.html',
    title: 'Memory Graph',
    description: '旧关系层探索工具，用于查看历史关系图。',
    // D-37-05：不把旧 Memory Graph 宣称为当前 Personal State 图
    historicalNote: 'Memory Graph 是旧关系层探索工具，代表历史关系记录，不是当前 Personal State SSOT。',
  },
  {
    file: 'relation-review-widget.html',
    title: 'Relation Review',
    description: '关系治理审核工具，用于检查关系变更与冲突（历史诊断视图）。',
    historicalNote: null,
  },
] as const;

export function EvidencePage() {
  const systemQuery = useSystemStatus();
  // system status 本身 pending/error 时按"未知"处理（不视为已确认不可达，也不视为已确认可达）
  const mcpAvailable = systemQuery.data ? systemQuery.data.data.ports.mcp.up : null;

  return (
    <div className="section-stack">
      <header className="card">
        <h1 className="text-lg font-semibold">证据中心</h1>
        <p className="mt-2 flex items-start gap-2 text-sm text-ink">
          <IconSearch className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <span>
            权威的只读证据下钻路径是<strong>当前对象的"查看证据"</strong>：在个人状态、外部环境或决策工作区页面上，
            点击某条断言 / 事实 / 建议旁的"查看证据"，会打开同一个 Evidence Drawer，展示该对象绑定的 authority、
            snapshot、checksum、freshness 与证据状态。本页面下方的 Widget 只是受限的诊断 / 历史集成，不承担这一权威角色。
          </span>
        </p>
      </header>

      <section aria-labelledby="diagnostic-integrations-title">
        <h2 id="diagnostic-integrations-title" className="px-1 font-semibold">
          诊断 / 历史集成
        </h2>
        <p className="mt-0.5 px-1 text-sm text-muted">
          以下 Widget 由本地 MCP 服务托管，仅用于历史数据浏览与治理审核辅助；
          它们不是当前 Personal State 的权威读取路径，加载失败或服务未启动时会显示明确的恢复说明，不会呈现为空白成功。
        </p>

        {systemQuery.isError ? (
          <div className="mt-3">
            <StatePanel
              variant="partial"
              title="无法确认 MCP 服务运行状态"
              description={`系统状态查询失败（${(systemQuery.error as ApiError).message}）：以下 Widget 仍会尝试加载，若长时间空白请手动确认服务状态。`}
            />
          </div>
        ) : null}

        <div className="mt-3 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {WIDGETS.map((widget) => (
            <WidgetDiagnosticCard
              key={widget.file}
              file={widget.file}
              title={widget.title}
              description={widget.description}
              historicalNote={widget.historicalNote}
              mcpAvailable={systemQuery.isError ? null : mcpAvailable}
            />
          ))}
        </div>
      </section>

      <p className="flex items-start gap-1.5 px-1 text-xs text-muted">
        <IconInfo className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Phase 37 只收口只读证据语义：不新增写入能力，也不改变既有 guarded 决策/行动流程；Phase 38 负责对这些入口实施 truth gate。
      </p>
    </div>
  );
}
