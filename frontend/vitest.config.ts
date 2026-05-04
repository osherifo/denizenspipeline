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
      // Floor thresholds — intentionally asymmetric:
      //   lines/statements (~14% overall): diluted by many files that have no
      //   tests yet; the per-file numbers are much higher for covered files.
      //   functions/branches reflect coverage quality inside tested files.
      // Bump all values as more views/components land tests
      // (target: devdocs/proposals/infrastructure/frontend-testing-plan.md → 70%+).
      thresholds: {
        lines: 13,
        statements: 13,
        functions: 65,
        branches: 75,
      },
    },
  },
})
