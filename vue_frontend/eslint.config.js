// eslint.config.js
import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'
import globals from 'globals'

export default [
  // 忽略文件
  {
    ignores: ['node_modules', 'dist', '*.min.js'],
  },

  // 基础 JS 配置
  js.configs.recommended,

  // Vue 推荐配置
  ...vue.configs['flat/recommended'],

  {
    files: ['**/*.vue', '**/*.js'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },

    rules: {
      // 通用规则
      'no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      'no-console': 'off',

      // Vue 规则
      'vue/multi-word-component-names': 'off',
      'vue/no-unused-vars': 'off',
      'vue/html-indent': ['error', 2],
    },
  },
]
