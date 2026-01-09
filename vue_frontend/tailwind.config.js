/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{vue,js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                // 自定义颜色，与现有 CSS 变量保持一致
                'bg-primary': '#0d0d14',
                'bg-secondary': '#12121a',
                'text-primary': '#f4f4f5',
                'text-secondary': '#a1a1aa',
                'text-muted': '#71717a',
                'accent-primary': '#ff6b6b',
                'accent-secondary': '#ff9f43',
                'accent-tertiary': '#4ecdc4',
            },
            borderColor: {
                DEFAULT: 'rgba(255, 255, 255, 0.08)',
            },
            boxShadow: {
                'sm': '0 1px 2px rgba(0, 0, 0, 0.2)',
                'md': '0 4px 6px rgba(0, 0, 0, 0.3)',
                'lg': '0 10px 15px rgba(0, 0, 0, 0.4)',
            },
            fontFamily: {
                sans: ['TheWriteRight', 'Mplus2', 'ZenKakuGothicNew', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
                mono: ['TheWriteRight', 'monospace'],
            },
        },
    },
    plugins: [],
}
