import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'

export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{js,mjs,cjs,vue}'],
    languageOptions: {
      globals: {
        // 浏览器环境全局变量
        console: 'readonly',
        document: 'readonly',
        window: 'readonly',
        navigator: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        confirm: 'readonly',
        alert: 'readonly',
        URL: 'readonly',
        Blob: 'readonly',
        IntersectionObserver: 'readonly',
        fetch: 'readonly',
        WebSocket: 'readonly',
        URLSearchParams: 'readonly',
        // Node.js 环境
        process: 'readonly',
      },
    },
    rules: {
      // 自定义规则
      'vue/multi-word-component-names': 'off', // 允许单词组件名
      'no-unused-vars': ['warn', {
        argsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_'
      }], // 未使用变量警告
      'vue/no-unused-vars': ['warn', { ignorePattern: '^_' }], // Vue 未使用变量警告
      'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off', // 生产环境警告 console
      'no-debugger': process.env.NODE_ENV === 'production' ? 'error' : 'off', // 生产环境禁止 debugger
      'no-empty': 'error',
      'no-useless-catch': 'error',

      // Vue 模板格式规则 - 放宽限制
      'vue/html-indent': ['error', 'tab'],
      'vue/max-attributes-per-line': 'off', // 允许多个属性在同一行
      'vue/first-attribute-linebreak': 'off', // 不强制第一个属性换行
      'vue/html-closing-bracket-newline': 'off', // 强制闭合括号换行
      'vue/singleline-html-element-content-newline': 'warn', // 允许单行元素内容
      'vue/multiline-html-element-content-newline': 'error', // 允许多行元素内容不换行
      'vue/html-self-closing': 'warn', // 不强制自闭合标签
      'vue/html-closing-bracket-spacing': 'off', // 不强制闭合括号空格
      'vue/attributes-order': 'warn', // 不强制属性顺序
      'vue/attribute-hyphenation': 'off', // 不强制属性连字符
      'vue/v-on-event-hyphenation': 'off', // 不强制事件名连字符
      'vue/require-explicit-emits': 'warn', // emit 事件声明改为警告
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**', '*.config.js'],
  },
]
