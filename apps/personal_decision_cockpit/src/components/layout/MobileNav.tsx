import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { IconDots } from '../icons';

// 移动端底部五栏（spec §6.2）：四个高频入口 + “更多”展开其余四项
const MOBILE_ITEMS = [
  { to: '/', zh: '总览', end: true },
  { to: '/decisions', zh: '决策' },
  { to: '/actions', zh: '行动' },
  { to: '/proactive', zh: '提醒' },
] as const;

const MORE_ITEMS = [
  { to: '/state', zh: '个人状态' },
  { to: '/external', zh: '外部环境' },
  { to: '/evidence', zh: '证据中心' },
  { to: '/system', zh: '系统状态' },
] as const;

export function MobileNav() {
  const [moreOpen, setMoreOpen] = useState(false);
  const location = useLocation();

  // 路由变化后收起“更多”面板
  useEffect(() => {
    setMoreOpen(false);
  }, [location.pathname]);

  return (
    <>
      {moreOpen ? (
        <div className="fixed inset-x-0 bottom-16 z-40 border-t border-line bg-panel p-3 md:hidden">
          <div className="grid grid-cols-2 gap-2">
            {MORE_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-center text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                    isActive ? 'bg-primary-soft font-medium text-primary' : 'text-muted hover:bg-surface'
                  }`
                }
              >
                {item.zh}
              </NavLink>
            ))}
          </div>
        </div>
      ) : null}

      <nav
        className="fixed inset-x-0 bottom-0 z-40 grid h-16 grid-cols-5 border-t border-line bg-panel md:hidden"
        aria-label="移动端主导航"
      >
        {MOBILE_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={'end' in item ? item.end : undefined}
            className={({ isActive }) =>
              `flex items-center justify-center text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary ${
                isActive ? 'font-medium text-primary' : 'text-muted'
              }`
            }
          >
            {item.zh}
          </NavLink>
        ))}
        <button
          type="button"
          onClick={() => setMoreOpen((open) => !open)}
          aria-expanded={moreOpen}
          className={`flex items-center justify-center gap-1 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary ${
            moreOpen ? 'font-medium text-primary' : 'text-muted'
          }`}
        >
          <IconDots />
          更多
        </button>
      </nav>
    </>
  );
}
