/**
 * Jest configuration for the TEEA task pane.
 *
 * The Office.js host is mocked wholesale in `test/officeMock.ts`: the real
 * `Office` and `Word` globals only exist inside a Word host process, so a suite
 * that needed them could never run in CI. Every test therefore exercises the
 * add-in's own logic against a scripted document, which is where the offset
 * arithmetic that actually breaks lives.
 */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/src', '<rootDir>/test'],
  setupFilesAfterEnv: ['<rootDir>/test/setup.ts'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  transform: {
    '^.+\\.tsx?$': [
      'ts-jest',
      {
        tsconfig: {
          jsx: 'react-jsx',
          // The production build type-checks with `noUnusedLocals`; a test file
          // that shadows an unused binding should not fail the suite for it.
          noUnusedLocals: false,
          noUnusedParameters: false,
        },
      },
    ],
  },
  collectCoverageFrom: [
    'src/taskpane/**/*.{ts,tsx}',
    '!src/taskpane/index.tsx',
  ],
  // A plain regex, not `testMatch`'s glob. This repository's worktree path
  // contains a directory that starts with a dot (`.claude`), and Jest's glob
  // engine escapes literal dots in the substituted `<rootDir>` prefix as `\.`,
  // which Windows then reads as a path separator followed by a literal dot,
  // matching zero files. `testRegex` is applied directly against the resolved
  // path with no such rewriting.
  testRegex: '[\\\\/]test[\\\\/].*\\.test\\.tsx?$',
};
