/** @type {import('tailwindcss').Config} */
// 语义色全部指向 tokens.css 中的 CSS 变量，深色模式通过 .dark 覆盖变量实现。
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: 'var(--color-primary)',
        'primary-soft': 'var(--color-primary-soft)',
        verified: 'var(--color-verified)',
        'verified-soft': 'var(--color-verified-soft)',
        uncertainty: 'var(--color-uncertainty)',
        'uncertainty-soft': 'var(--color-uncertainty-soft)',
        risk: 'var(--color-risk)',
        'risk-soft': 'var(--color-risk-soft)',
        candidate: 'var(--color-llm-candidate)',
        'candidate-soft': 'var(--color-llm-candidate-soft)',
        external: 'var(--color-external)',
        'external-soft': 'var(--color-external-soft)',
        ink: 'var(--color-text)',
        muted: 'var(--color-text-muted)',
        line: 'var(--color-border)',
        surface: 'var(--color-surface)',
        panel: 'var(--color-surface-raised)',
      },
      fontFamily: {
        // 本地系统字体栈，禁止外部字体 CDN（spec §9.3）
        sans: ['Inter', '"Noto Sans SC"', '"PingFang SC"', '"Microsoft YaHei"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SFMono-Regular"', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
