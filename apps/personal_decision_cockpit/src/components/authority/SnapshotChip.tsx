// 快照徽标：只显示短 ID（前 12 字符），完整 ID 放 title 悬浮查看（spec §6.3）。

/** 长 ID 截断为短码，保持布局不被长 ID 撑破 */
export function shortId(id: string, head = 12): string {
  return id.length <= head ? id : `${id.slice(0, head)}…`;
}

interface SnapshotChipProps {
  /** Personal / External / Serving */
  label: string;
  snapshotId: string | null;
}

export function SnapshotChip({ label, snapshotId }: SnapshotChipProps) {
  if (!snapshotId) {
    return (
      <span className="badge border-line text-muted" title={`${label} 快照未绑定`}>
        {label} · 未绑定
      </span>
    );
  }
  return (
    <span className="badge border-line bg-panel text-ink" title={`${label} 快照完整 ID：${snapshotId}`}>
      <span className="text-muted">{label}</span>
      <span className="font-mono">{shortId(snapshotId)}</span>
    </span>
  );
}
