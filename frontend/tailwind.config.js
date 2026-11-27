/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        base: '#070A10',
        panel: '#0C121A',
        raised: '#111A26',
        line: '#1A2432',
        'line-strong': '#263244',
        ink: {
          DEFAULT: '#E7EEF7',
          muted: '#93A1B5',
          dim: '#64748B',
        },
        brand: {
          DEFAULT: '#38BDF8',
          soft: '#0EA5E9',
          dim: '#0B7EA8',
        },
        violet: '#A78BFA',
        ok: '#34D399',
        warn: '#FBBF24',
        bad: '#F87171',
        info: '#60A5FA',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -16px rgba(0,0,0,0.9)',
        pop: '0 12px 40px -12px rgba(0,0,0,0.75)',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-400px 0' },
          '100%': { backgroundPosition: '400px 0' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.4s linear infinite',
      },
    },
  },
  plugins: [],
};
