/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#fef2f2', 100: '#fee2e2', 200: '#fecaca', 300: '#fca5a5',
          400: '#f87171', 500: '#ef4444', 600: '#C8102E', 700: '#8B0A20', 800: '#7f1d1d', 900: '#450a0a',
        },
        hhb: { DEFAULT: '#C8102E', dark: '#8B0A20', light: '#FF3A56' },
        ink: { 900: '#0B0D10', 800: '#14171C', 700: '#1F242C', 500: '#6B7280' },
      },
      fontFamily: {
        sans: ['Jost', 'system-ui', 'sans-serif'],
        bebas: ['Bebas Neue', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
