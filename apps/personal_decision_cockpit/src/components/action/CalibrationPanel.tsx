import type { CalibrationOverviewData, CalibrationProtocol } from '../../api/schemas';
import { fmtNumber } from '../../utils/format';
import { shortId } from '../authority/SnapshotChip';
import { StatePanel } from '../feedback/StatePanel';
import { IconAlertTriangle } from '../icons';

/**
 * CalibrationPanel（spec §7.4 / §8）：校准协议总览。
 * 协议卡：protocol_id、verdict/status、sample_size、causal_claim==false 的"非因果评估"标注、
 * INCONCLUSIVE 时展示 inconclusive_reasons 与"样本不足或协议偏离"说明、summary_limitations 列表。
 * 单条协议组装失败（error）只降级该条。
 */

/** status/verdict 词表以后端为准：只对 inconclusive 做特判（大小写不敏感），其余原样展示 */
function isInconclusive(protocol: CalibrationProtocol): boolean {
  return [protocol.status, protocol.verdict].some(
    (value) => typeof value === 'string' && value.toLowerCase().includes('inconclusive'),
  );
}

function ProtocolCard({ protocol }: { protocol: CalibrationProtocol }) {
  if (protocol.error) {
    return (
      <li>
        <StatePanel
          variant="partial"
          title={`协议 ${protocol.protocol_id ? shortId(protocol.protocol_id, 24) : '（无 ID）'} 组装失败`}
          description={`后端返回错误：${protocol.error}（其余协议不受影响）`}
        />
      </li>
    );
  }
  const inconclusive = isInconclusive(protocol);
  return (
    <li className="section-stack rounded-lg border border-line bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm break-all" title={protocol.protocol_id ?? undefined}>
          {protocol.protocol_id ? shortId(protocol.protocol_id, 24) : '（无 ID）'}
        </span>
        {protocol.status ? (
          <span
            className={`badge ${
              inconclusive ? 'border-uncertainty bg-uncertainty-soft text-uncertainty' : 'border-line bg-panel text-muted'
            }`}
          >
            {inconclusive ? <IconAlertTriangle className="h-3.5 w-3.5" /> : null}
            {protocol.status}
          </span>
        ) : null}
        {protocol.verdict ? <span className="badge border-line bg-panel text-ink">{protocol.verdict}</span> : null}
        {protocol.causal_claim === false ? (
          <span className="badge border-uncertainty bg-uncertainty-soft text-uncertainty">
            <IconAlertTriangle className="h-3.5 w-3.5" />
            非因果评估
          </span>
        ) : null}
      </div>
      <p className="text-sm text-muted">
        样本量{' '}
        <span className="font-mono">
          {protocol.sample_size === null || protocol.sample_size === undefined ? '未提供' : fmtNumber(protocol.sample_size)}
        </span>
      </p>
      <div className="flex flex-wrap gap-1.5 text-xs">
        <span className="badge border-uncertainty bg-uncertainty-soft text-uncertainty">不自动 promotion</span>
        <span className="badge border-uncertainty bg-uncertainty-soft text-uncertainty">不执行 external action</span>
        {protocol.promotion_available === false ? <span className="badge border-line bg-panel text-muted">promotion_available=false</span> : null}
        {protocol.external_action_available === false ? <span className="badge border-line bg-panel text-muted">external_action_available=false</span> : null}
      </div>
      {inconclusive ? (
        <div className="rounded-lg border border-uncertainty bg-uncertainty-soft p-3" role="note">
          <p className="flex items-start gap-1.5 text-sm text-uncertainty">
            <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            样本不足或协议偏离：该协议结论不可用（INCONCLUSIVE），不能作为建议有效性的依据。
          </p>
          {protocol.inconclusive_reasons.length > 0 ? (
            <ul className="mt-2 flex flex-wrap gap-1.5 pl-6">
              {protocol.inconclusive_reasons.map((code) => (
                <li key={code} className="badge border-line bg-panel font-mono text-xs text-muted">
                  {code}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {protocol.summary_limitations.length > 0 ? (
        <div>
          <h3 className="text-sm font-medium">限制</h3>
          <ul className="mt-1 list-disc pl-5 text-sm text-muted">
            {protocol.summary_limitations.map((limitation, i) => (
              <li key={i}>{limitation}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </li>
  );
}

export function CalibrationPanel({ data }: { data: CalibrationOverviewData }) {
  return (
    <section className="card section-stack" aria-labelledby="calibration-panel-title">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="calibration-panel-title" className="font-semibold">
            校准总览
          </h2>
          <span className="badge border-line bg-panel text-muted">共 {fmtNumber(data.total)} 个协议</span>
          <span className="badge border-line bg-panel text-muted">本次展示 {fmtNumber(data.shown)} 个</span>
        </div>
        <p className="mt-1 text-sm text-muted">
          推荐校准协议的评估结论；校准为非因果评估，不证明建议导致了结果，也不会自动 promote 任何建议。
        </p>
      </div>
      {data.protocols.length === 0 ? (
        <StatePanel
          variant="empty"
          title="暂无校准协议"
          description="当前没有校准协议评估结果；会话链推进到 calibrate 后结论会显示在这里。"
        />
      ) : (
        <ul className="section-stack">
          {data.protocols.map((protocol, index) => (
            <ProtocolCard key={protocol.protocol_id ?? `protocol-${index}`} protocol={protocol} />
          ))}
        </ul>
      )}
    </section>
  );
}
