import { useState } from 'react';
import { useOverview, useSystemStatus } from '../../api/hooks';
import { useUiPrefs } from '../../app/providers';
import { SnapshotChip } from '../authority/SnapshotChip';
import { NewSessionDialog } from '../decision/NewSessionDialog';
import { FreshnessBadge } from '../feedback/FreshnessBadge';
import { IconDensity, IconMoon, IconPlus, IconSun } from '../icons';

type HealthLevel = 'ok' | 'warn' | 'down' | 'checking';

interface Health {
  level: HealthLevel;
  label: string;
  dotClass: string;
}

/** 由系统状态投影推导顶栏健康点：REST 离线=红，部分 Authority 异常=黄，全好=绿 */
function deriveHealth(status: ReturnType<typeof useSystemStatus>): Health {
  if (status.isPending) return { level: 'checking', label: '检查中', dotClass: 'bg-muted' };
  if (status.isError || !status.data) return { level: 'down', label: '异常', dotClass: 'bg-risk' };
  const env = status.data;
  if (!env.data.ports.rest.up) return { level: 'down', label: '异常', dotClass: 'bg-risk' };
  const hasAuthorityError = Object.values(env.authorities).some((a) => a === 'error');
  if (!env.ok || env.partial || hasAuthorityError) {
    return { level: 'warn', label: '部分可用', dotClass: 'bg-uncertainty' };
  }
  return { level: 'ok', label: '正常', dotClass: 'bg-verified' };
}

/** 全局顶栏（spec §6.3）：快照、新鲜度、系统状态、主题/密度切换、新建决策入口 */
export function TopBar() {
  const overview = useOverview();
  const status = useSystemStatus();
  const { theme, density, toggleTheme, toggleDensity } = useUiPrefs();
  const health = deriveHealth(status);
  const [sessionDialogOpen, setSessionDialogOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-panel">
      <div className="flex h-14 items-center gap-3 px-4">
        <div className="min-w-0 shrink-0">
          <div className="truncate text-sm font-semibold">Personal Decision Cockpit</div>
          <div className="truncate text-xs text-muted">个人决策驾驶舱</div>
        </div>

        {/* 右侧状态区：空间不足时区内横向滚动，不撑破页面 */}
        <div className="ml-auto flex min-w-0 items-center gap-2 overflow-x-auto">
          <SnapshotChip label="Personal" snapshotId={overview.data?.snapshot_bindings.personal ?? null} />
          <SnapshotChip label="External" snapshotId={overview.data?.snapshot_bindings.external ?? null} />
          <FreshnessBadge asOf={overview.data?.freshness?.personal_as_of ?? null} />

          <span
            className="badge border-line bg-panel text-ink"
            title={`系统状态：${health.label}`}
            role="status"
          >
            <span className={`h-2.5 w-2.5 rounded-full ${health.dotClass}`} aria-hidden="true" />
            {health.label}
          </span>

          <button
            type="button"
            onClick={toggleTheme}
            title={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
            aria-label={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
            className="rounded-md border border-line p-1.5 text-muted transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
          >
            {theme === 'dark' ? <IconSun /> : <IconMoon />}
          </button>

          <button
            type="button"
            onClick={toggleDensity}
            title={density === 'compact' ? '切换到舒适密度' : '切换到紧凑密度'}
            aria-label={density === 'compact' ? '切换到舒适密度' : '切换到紧凑密度'}
            className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1.5 text-sm text-muted transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <IconDensity />
            {density === 'compact' ? '紧凑' : '舒适'}
          </button>

          {/* 新建决策：打开会话对话框（Guarded 写流程，Phase 38） */}
          <button
            type="button"
            onClick={() => setSessionDialogOpen(true)}
            title="新建决策会话（prepare → exact preview → 显式 confirm）"
            className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white transition-colors hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <IconPlus className="h-3.5 w-3.5" />
            新建决策
          </button>
        </div>
      </div>
      <NewSessionDialog open={sessionDialogOpen} onClose={() => setSessionDialogOpen(false)} />
    </header>
  );
}
