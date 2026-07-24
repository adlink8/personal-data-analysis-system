import type { SystemStatusData } from '../../api/schemas';
import { fmtNumber } from '../../utils/format';

// 系统健康横条（spec §8 SystemHealthStrip）：三个端口 + 知识服务运行态。
// 状态点配文字，不只靠颜色。

function PortItem({ name, up, port }: { name: string; up: boolean; port: number }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm">
      <span
        className={`h-2.5 w-2.5 rounded-full ${up ? 'bg-verified' : 'bg-risk'}`}
        aria-hidden="true"
      />
      <span className="font-medium">{name}</span>
      <span className="font-mono text-xs text-muted">:{port}</span>
      <span className={up ? 'text-verified' : 'text-risk'}>{up ? '运行中' : '离线'}</span>
    </span>
  );
}

export function SystemHealthStrip({ data }: { data: SystemStatusData }) {
  const knowledgeOk = data.knowledge.available === true;
  return (
    <div
      className="card flex flex-wrap items-center gap-x-6 gap-y-2"
      role="status"
      aria-label="系统健康横条"
    >
      <PortItem name="REST" up={data.ports.rest.up} port={data.ports.rest.port} />
      <PortItem name="MCP" up={data.ports.mcp.up} port={data.ports.mcp.port} />
      <PortItem name="Tunnel" up={data.ports.tunnel.up} port={data.ports.tunnel.port} />
      <span className="inline-flex items-center gap-2 text-sm">
        <span
          className={`h-2.5 w-2.5 rounded-full ${knowledgeOk ? 'bg-verified' : 'bg-risk'}`}
          aria-hidden="true"
        />
        <span className="font-medium">知识库</span>
        <span className={knowledgeOk ? 'text-verified' : 'text-risk'}>
          {knowledgeOk ? '可用' : '不可用'}
        </span>
        <span className="text-muted">{fmtNumber(data.knowledge.unit_count)} 单元</span>
      </span>
    </div>
  );
}
