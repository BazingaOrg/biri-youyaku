module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // 主题完全跟随系统：让 dark: 变体响应 prefers-color-scheme，无需在 html 加 class。
  darkMode: 'media',
  theme: {
    extend: {
      colors: {
        canvas: 'var(--color-bg)',
        ink: 'var(--color-fg)',
        muted: 'var(--color-fg-muted)',
        line: 'var(--color-border)',
        panel: 'var(--color-bg-elevated)',
        lift: 'var(--color-bg-sunken)',
        brand: 'var(--color-brand)',
        brandSoft: 'var(--color-brand-soft)',
        success: 'var(--color-success)',
        warning: 'var(--color-warning)',
        danger: 'var(--color-danger)',
      },
      fontFamily: {
        sans: [
          '"Inter"',
          '"PingFang SC"',
          '"Hiragino Sans"',
          '"Noto Sans CJK SC"',
          'ui-sans-serif',
          'system-ui',
          'sans-serif',
        ],
        serif: [
          '"Noto Serif JP"',
          '"Source Han Serif SC"',
          '"Songti SC"',
          'ui-serif',
          'Georgia',
          'serif',
        ],
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        cardHover: 'var(--shadow-card-hover)',
      },
      keyframes: {
        pop: {
          '0%': {opacity: '0', transform: 'translateY(-6px) scale(0.98)'},
          '100%': {opacity: '1', transform: 'translateY(0) scale(1)'},
        },
      },
      animation: {
        pop: 'pop 180ms ease-out',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
