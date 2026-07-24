import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/**
 * 本地 UI 偏好：主题 + 密度。
 * localStorage 只允许 cockpit.theme / cockpit.density 两个键（spec §15.5），
 * 不持久化任何业务数据。
 */
type Theme = 'light' | 'dark';
type Density = 'comfortable' | 'compact';

interface UiPrefs {
  theme: Theme;
  density: Density;
  toggleTheme: () => void;
  toggleDensity: () => void;
}

const THEME_KEY = 'cockpit.theme';
const DENSITY_KEY = 'cockpit.density';

const UiPrefsContext = createContext<UiPrefs | null>(null);

function readTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light'; // 默认浅色（spec §9.2）
  }
}

function readDensity(): Density {
  try {
    return localStorage.getItem(DENSITY_KEY) === 'compact' ? 'compact' : 'comfortable';
  } catch {
    return 'comfortable';
  }
}

const queryClient = new QueryClient();

export function AppProviders({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [density, setDensity] = useState<Density>(readDensity);

  // 主题/密度通过 <html> 上的 class 驱动 tokens.css 中的变量覆盖
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    root.classList.toggle('density-compact', density === 'compact');
    try {
      localStorage.setItem(THEME_KEY, theme);
      localStorage.setItem(DENSITY_KEY, density);
    } catch {
      // 隐私模式等写入失败场景：忽略，偏好仅本次会话有效
    }
  }, [theme, density]);

  const value = useMemo<UiPrefs>(
    () => ({
      theme,
      density,
      toggleTheme: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
      toggleDensity: () => setDensity((d) => (d === 'compact' ? 'comfortable' : 'compact')),
    }),
    [theme, density],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <UiPrefsContext.Provider value={value}>{children}</UiPrefsContext.Provider>
    </QueryClientProvider>
  );
}

export function useUiPrefs(): UiPrefs {
  const ctx = useContext(UiPrefsContext);
  if (!ctx) throw new Error('useUiPrefs 必须在 AppProviders 内使用');
  return ctx;
}
