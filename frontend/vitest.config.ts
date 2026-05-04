import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/__tests__/**/*.test.{ts,tsx}'],
    exclude: ['node_modules', 'dist', 'e2e/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/__tests__/**',
        'src/test/**',
        'src/main.tsx',
        'src/**/*.d.ts',
      ],
      // Floor thresholds: prevent regressions while we extend coverage view
      // by view. Bump as more views/components land tests (target in
      // devdocs/proposals/infrastructure/frontend-testing-plan.md is 70%+).
      thresholds: {
        lines: 13,
        statements: 13,
        functions: 60,
        branches: 70,
      },
    },
  },
})
