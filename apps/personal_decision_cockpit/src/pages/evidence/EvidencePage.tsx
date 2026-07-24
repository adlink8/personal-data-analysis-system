// 证据中心（spec §7.7）：复用现有 MCP Widget，而不是重写一套数据浏览器。
// Widget 由 MCP 服务（127.0.0.1:8789）托管，正式数据接线属于后续证据中心阶段。

const WIDGET_BASE = 'http://127.0.0.1:8789/widgets';

const WIDGETS = [
  {
    file: 'data-browser-widget.html',
    title: '数据浏览器',
    description: '浏览个人数据条目与证据记录，支持单条下钻。',
    warning: null,
  },
  {
    file: 'memory-graph-widget.html',
    title: 'Memory Graph',
    description: '旧关系层探索工具，用于查看历史关系图。',
    // spec §7.7：不把旧 Memory Graph 宣称为当前 Personal State 图
    warning: 'Memory Graph 是旧关系层探索工具，不代表当前 Personal State。',
  },
  {
    file: 'relation-review-widget.html',
    title: 'Relation Review',
    description: '关系治理审核工具，用于检查关系变更与冲突。',
    warning: null,
  },
] as const;

export function EvidencePage() {
  return (
    <div className="section-stack">
      <header className="card">
        <h1 className="text-lg font-semibold">证据中心</h1>
        <p className="mt-1 text-sm text-muted">
          以下 Widget 由 MCP 服务（127.0.0.1:8789）托管；与后端权威的正式数据接线属于后续证据中心阶段。
          若 MCP 服务未启动，嵌入区域将显示空白，可使用“在新窗口打开”确认服务状态。
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {WIDGETS.map((widget) => {
          const url = `${WIDGET_BASE}/${widget.file}`;
          return (
            <section key={widget.file} className="card flex flex-col gap-2" aria-labelledby={`widget-${widget.file}`}>
              <div className="flex items-start justify-between gap-2">
                <h2 id={`widget-${widget.file}`} className="font-medium">
                  {widget.title}
                </h2>
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 text-sm text-primary hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  在新窗口打开
                </a>
              </div>
              <p className="text-sm text-muted">{widget.description}</p>
              {widget.warning ? (
                <p className="rounded-md border border-uncertainty bg-uncertainty-soft px-2 py-1.5 text-xs text-uncertainty">
                  {widget.warning}
                </p>
              ) : null}
              <iframe
                src={url}
                title={widget.title}
                loading="lazy"
                className="h-96 w-full rounded-md border border-line bg-white"
              />
            </section>
          );
        })}
      </div>
    </div>
  );
}
