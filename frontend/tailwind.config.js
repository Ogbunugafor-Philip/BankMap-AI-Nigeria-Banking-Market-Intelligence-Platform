/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#f0f9ff',
          100: '#e0f2fe',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          900: '#0c4a6e',
        },
        surface: {
          900: '#0a0f1e',
          800: '#0d1526',
          700: '#111827',
          600: '#1a2236',
          500: '#1e2d45',
          400: '#243352',
        },
        green:  { DEFAULT: '#10b981', light: '#d1fae5', dark: '#065f46' },
        amber:  { DEFAULT: '#f59e0b', light: '#fef3c7', dark: '#92400e' },
        red:    { DEFAULT: '#ef4444', light: '#fee2e2', dark: '#7f1d1d' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'fade-in':    'fadeIn 0.3s ease-in-out',
        'slide-in':   'slideIn 0.3s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4,0,0.6,1) infinite',
      },
      keyframes: {
        fadeIn:  { '0%': { opacity: '0' },              '100%': { opacity: '1' } },
        slideIn: { '0%': { transform: 'translateX(20px)', opacity: '0' },
                   '100%': { transform: 'translateX(0)',   opacity: '1' } },
      },
    },
  },
  plugins: [],
}
