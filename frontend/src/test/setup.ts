import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from './mocks/server'
import { resetAllStores } from './stores'

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

afterEach(() => {
  cleanup()
  server.resetHandlers()
  resetAllStores()
})

afterAll(() => {
  server.close()
})

if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'location', {
    writable: true,
    value: { ...window.location, host: 'localhost:5173', protocol: 'http:' },
  })
}

// ReactFlow uses ResizeObserver + DOMMatrix + getBoundingClientRect
// dimensions that JSDOM doesn't implement. Provide minimal shims so
// any component embedding @xyflow/react (e.g. AnalysisBuilder's
// ghost graph) doesn't blow up the test runner.
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  ;(globalThis as { ResizeObserver?: typeof ResizeObserver }).ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver
}

if (typeof globalThis.DOMMatrixReadOnly === 'undefined') {
  class DOMMatrixReadOnlyStub {
    m22 = 1
    constructor(_init?: string) {}
  }
  ;(globalThis as { DOMMatrixReadOnly?: typeof DOMMatrixReadOnly }).DOMMatrixReadOnly =
    DOMMatrixReadOnlyStub as unknown as typeof DOMMatrixReadOnly
}
