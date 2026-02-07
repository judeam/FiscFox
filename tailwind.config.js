/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/web/templates/**/*.html"],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        forest: { DEFAULT: '#1a3a2f', light: '#2d5a4a', dark: '#0f2219' },
        amber: { DEFAULT: '#d4a853', light: '#e8c87a', dark: '#b8923d' },
        cream: { DEFAULT: '#faf8f5', dark: '#f0ede8' },
        charcoal: '#2c2c2c',
        slate: '#64748b',
        sage: '#4a7c59',
        terracotta: '#c4634d',
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    }
  },
  plugins: [],
}
