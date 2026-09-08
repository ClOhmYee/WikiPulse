import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';

export default [
  { ignores: ['dist/**', 'node_modules/**', 'test-results/**', 'playwright-report/**'] },
  {
    files: ['src/app/**/*.{js,jsx}', 'src/pages/**/*.{js,jsx}', 'src/features/**/*.{js,jsx}', 'src/components/**/*.{js,jsx}'],
    rules: {
      'no-restricted-imports': ['error', { patterns: [{ group: ['**/data/mock/**', '**/fixtures/**'], message: '화면은 fixture 대신 공통 데이터 조회 계층을 사용하세요.' }] }],
    },
  },
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: Object.fromEntries([
        'window', 'document', 'localStorage', 'performance', 'requestAnimationFrame',
        'cancelAnimationFrame', 'ResizeObserver', 'Element', 'WheelEvent', 'URLSearchParams',
        'Float32Array', 'Math', 'Number', 'Array', 'Object', 'String', 'Boolean', 'JSON',
        'globalThis', 'Promise', 'structuredClone', 'AbortController', 'Set', 'Map', 'Intl', 'console', 'Uint8Array', 'URL', 'Error',
      ].map(name => [name, 'readonly'])),
    },
    plugins: { react, 'react-hooks': reactHooks, 'jsx-a11y': jsxA11y },
    settings: { react: { version: '19.2' } },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-unreachable': 'error',
      'no-constant-condition': 'error',
      'react/jsx-uses-react': 'error',
      'react/jsx-uses-vars': 'error',
      'react/jsx-key': 'error',
      'react/jsx-no-duplicate-props': 'error',
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'jsx-a11y/alt-text': 'error',
      'jsx-a11y/anchor-has-content': 'error',
      'jsx-a11y/aria-props': 'error',
      'jsx-a11y/aria-proptypes': 'error',
      'jsx-a11y/aria-role': 'error',
      'jsx-a11y/role-has-required-aria-props': 'error',
    },
  },
];
