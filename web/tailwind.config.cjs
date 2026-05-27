module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f7f8fb',
        ink: '#18191c',
        muted: '#6d757a',
        line: '#ffd6e7',
        panel: '#ffffff',
        lift: '#f6f7fb',
        accent: '#fb7299',
        accentSoft: '#fff0f6',
        pink: '#fb7299',
        danger: 'oklch(0.53 0.16 28)',
      },
      fontFamily: {
        sans: ['Avenir Next', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        surface: '0 1px 3px rgba(32, 43, 36, 0.12), 0 16px 48px rgba(32, 43, 36, 0.08)',
        bili: '0 10px 34px rgba(251, 114, 153, 0.12), 0 2px 8px rgba(0, 174, 236, 0.08)',
        biliHover: '0 16px 44px rgba(251, 114, 153, 0.16), 0 4px 14px rgba(0, 174, 236, 0.12)',
        pinkGlow: '0 0 0 1px rgba(251, 114, 153, 0.42), 0 0 26px rgba(251, 114, 153, 0.28)',
        pinkGlowStrong: '0 0 0 1px rgba(251, 114, 153, 0.58), 0 0 34px rgba(251, 114, 153, 0.38)',
      },
      keyframes: {
        pop: {
          '0%': {opacity: '0', transform: 'translateY(-6px) scale(0.98)'},
          '100%': {opacity: '1', transform: 'translateY(0) scale(1)'},
        },
        glowPulse: {
          '0%, 100%': {
            boxShadow: '0 0 0 1px rgba(251, 114, 153, 0.34), 0 0 18px rgba(251, 114, 153, 0.18)',
          },
          '50%': {
            boxShadow: '0 0 0 1px rgba(251, 114, 153, 0.62), 0 0 34px rgba(251, 114, 153, 0.36)',
          },
        },
      },
      animation: {
        pop: 'pop 180ms ease-out',
        glowPulse: 'glowPulse 2.8s ease-in-out infinite',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
