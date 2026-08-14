module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // 主题由 html[data-theme] 驱动（见 ThemeToggle），dark: 变体跟随它。
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        canvas: 'rgb(var(--color-bg-rgb) / <alpha-value>)',
        ink: 'rgb(var(--color-fg-rgb) / <alpha-value>)',
        muted: 'rgb(var(--color-fg-muted-rgb) / <alpha-value>)',
        line: 'rgb(var(--color-border-rgb) / <alpha-value>)',
        panel: 'rgb(var(--color-bg-elevated-rgb) / <alpha-value>)',
        lift: 'rgb(var(--color-bg-sunken-rgb) / <alpha-value>)',
        brand: 'rgb(var(--color-brand-rgb) / <alpha-value>)',
        brandSolid: 'rgb(var(--color-brand-solid-rgb) / <alpha-value>)',
        onBrand: 'rgb(var(--color-on-brand-rgb) / <alpha-value>)',
        brandSoft: 'rgb(var(--color-brand-soft-rgb) / <alpha-value>)',
        success: 'rgb(var(--color-success-rgb) / <alpha-value>)',
        warning: 'rgb(var(--color-warning-rgb) / <alpha-value>)',
        danger: 'rgb(var(--color-danger-rgb) / <alpha-value>)',
        dangerSolid: 'rgb(var(--color-danger-solid-rgb) / <alpha-value>)',
        onDanger: 'rgb(var(--color-on-danger-rgb) / <alpha-value>)',
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
        'pop-out': {
          '0%': {opacity: '1', transform: 'translateY(0) scale(1)'},
          '100%': {opacity: '0', transform: 'translateY(-6px) scale(0.98)'},
        },
        'fade-in-up': {
          '0%': {opacity: '0', transform: 'translateY(8px)'},
          '100%': {opacity: '1', transform: 'translateY(0)'},
        },
      },
      animation: {
        pop: 'pop 180ms ease-out',
        'pop-out': 'pop-out 150ms ease-out',
        'fade-in-up': 'fade-in-up 200ms ease-out',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
