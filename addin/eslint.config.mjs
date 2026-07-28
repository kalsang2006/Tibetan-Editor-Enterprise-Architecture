// @ts-check
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import jest from 'eslint-plugin-jest';

/**
 * ESLint configuration for the TEEA task pane.
 *
 * Kept close to each plugin's own recommended preset rather than hand-picking
 * rules: the project's real discipline is `tsconfig.json`'s `strict` mode,
 * already enforced by `tsc --noEmit`. ESLint's job here is the layer type
 * checking cannot cover -- React hook dependency correctness and JSX
 * accessibility -- which is why `react-hooks` and `jsx-a11y` are the two
 * plugins actually configured beyond the defaults.
 */
export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}', 'test/**/*.{ts,tsx}'],
    plugins: {
      react,
      'react-hooks': reactHooks,
      'jsx-a11y': jsxA11y,
    },
    languageOptions: {
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: '18.3' },
    },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      // The project targets React 18's automatic JSX runtime; no file needs
      // `React` in scope just to write JSX.
      'react/react-in-jsx-scope': 'off',
      // Every prop in this codebase is typed by a TS interface; PropTypes are
      // a JS-era convention this project does not use.
      'react/prop-types': 'off',
      // The rule's default only treats ARIA "widget" roles as tabIndex-worthy,
      // but a `region` with no other focusable content and real overflow
      // scroll needs `tabIndex={0}` to be keyboard-operable at all -- the
      // WAI-ARIA Authoring Practices' own "scrollable region" pattern.
      // `VirtualizedList`'s viewport is the one real use of it in this
      // codebase; nothing else should reach for this combination without the
      // same justification.
      'jsx-a11y/no-noninteractive-tabindex': ['error', { roles: ['region'] }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  {
    files: ['test/**/*.{ts,tsx}'],
    plugins: { jest },
    languageOptions: {
      globals: { ...jest.environments.globals.globals },
    },
    rules: {
      ...jest.configs.recommended.rules,
    },
  },
);
