import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// vitest globals:false 时 RTL 不会自动清理，显式注册，避免跨用例 DOM 残留
afterEach(() => {
  cleanup();
});
