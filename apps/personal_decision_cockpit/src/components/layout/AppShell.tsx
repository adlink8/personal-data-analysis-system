import { NavLink, Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';
import { MobileNav } from './MobileNav';

// 桌面端八项主导航（spec §6.1），中文主标签 + 英文小字
export const NAV_ITEMS: ReadonlyArray<{ to: string; zh: string; en: string; end?: boolean }> = [
  { to: '/', zh: '今日总览', en: 'Overview', end: true },
  { to: '/state', zh: '个人状态', en: 'Personal State' },
  { to: '/decisions', zh: '决策中心', en: 'Decisions' },
  { to: '/actions', zh: '行动与结果', en: 'Actions & Outcomes' },
  { to: '/external', zh: '外部环境', en: 'External Context' },
  { to: '/proactive', zh: '主动提醒', en: 'Proactive Inbox' },
  { to: '/evidence', zh: '证据中心', en: 'Evidence' },
  { to: '/system', zh: '系统状态', en: 'System' },
];

/**
 * 应用壳：
 * - 1024+：左侧固定导航；
 * - 768–1023：顶栏下方横向可滚导航条（中间断点不崩、无导航真空）；
 * - <768：底部五栏（见 MobileNav）。
 */
export function AppShell() {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <TopBar />

      {/* 桌面侧栏：1024+ */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 border-r border-line bg-panel pt-14 lg:block">
        <nav className="flex flex-col gap-1 overflow-y-auto p-3" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                  isActive ? 'bg-primary-soft font-medium text-primary' : 'text-muted hover:bg-surface'
                }`
              }
            >
              <span className="block">{item.zh}</span>
              <span className="block text-xs opacity-70">{item.en}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* 平板横向导航：768–1023 */}
      <nav
        className="sticky top-14 z-20 hidden gap-1 overflow-x-auto border-b border-line bg-panel px-3 py-2 md:flex lg:hidden"
        aria-label="主导航"
      >
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                isActive ? 'bg-primary-soft font-medium text-primary' : 'text-muted hover:bg-surface'
              }`
            }
          >
            {item.zh}
          </NavLink>
        ))}
      </nav>

      {/* 主内容：移动端给底栏留 pb，桌面给侧栏留 pl */}
      <main className="px-4 pb-24 pt-4 md:pb-8 lg:pl-60 lg:pr-6">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>

      <MobileNav />
    </div>
  );
}
