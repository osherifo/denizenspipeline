import { describe, it, expect } from 'vitest'
import {
  DARK_STATUS,
  LIGHT_STATUS,
  forLight,
  identityColor,
  nodeColors,
  runningNodeStyle,
  statusPalette,
} from '../status-colors'

/** WCAG relative luminance / contrast, computed independently of the module. */
function luminance(hex: string): number {
  const h = hex.replace('#', '')
  const ch = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  const [r, g, b] = ch.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const la = luminance(a)
  const lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

// The two light-mode surfaces text can land on (page and card).
const LIGHT_SURFACES = ['#e8ebf2', '#ffffff']

describe('light-mode legibility', () => {
  it('every light status colour clears AA on both light surfaces', () => {
    for (const [status, hex] of Object.entries(LIGHT_STATUS)) {
      for (const bg of LIGHT_SURFACES) {
        expect(contrast(hex, bg), `${status} (${hex}) on ${bg}`).toBeGreaterThanOrEqual(4.5)
      }
    }
  })

  it('covers every status key the dark table defines', () => {
    expect(Object.keys(LIGHT_STATUS).sort()).toEqual(Object.keys(DARK_STATUS).sort())
  })

  it('darkens identity colours until they are legible, preserving hue', () => {
    // The neon/stage palette used across the graph, composer and error browser.
    const identities = [
      '#00e5ff', '#e040fb', '#ffd600', '#00e676', '#448aff', '#ff1744',
      '#ff9100', '#69f0ae', '#3b82f6', '#10b981', '#14b8a6', '#ef4444',
      '#ffb86c', '#22c55e', '#52c98f',
    ]
    for (const hex of identities) {
      const out = forLight(hex)
      for (const bg of LIGHT_SURFACES) {
        expect(contrast(out, bg), `${hex} -> ${out} on ${bg}`).toBeGreaterThanOrEqual(4.5)
      }
      // Hue is the identity — it must survive the darkening.
      expect(out).not.toBe(hex)
    }
  })

  it('keeps achromatic identity colours neutral instead of tinting them', () => {
    const out = forLight('#ffffff')
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(out.replace('#', '').slice(i - 1, i + 1), 16))
    expect(Math.max(r, g, b) - Math.min(r, g, b)).toBeLessThanOrEqual(2)
  })
})

describe('dark mode is untouched', () => {
  it('passes identity colours through unchanged', () => {
    expect(identityColor('#00e5ff', 'dark')).toBe('#00e5ff')
  })

  it('keeps the original node fill/border alpha suffixes', () => {
    expect(nodeColors('dark', 'failed')).toMatchObject({
      color: '#ff1744',
      bg: '#ff174422',
      border: '#ff1744aa',
      borderWidth: 1,
      running: false,
      glow: '',
    })
  })
})

describe('running nodes are emphasised', () => {
  for (const mode of ['dark', 'light'] as const) {
    it(`gives a running node a heavier edge, stronger fill and a glow (${mode})`, () => {
      const run = nodeColors(mode, 'running')
      const done = nodeColors(mode, 'done')

      expect(run.running).toBe(true)
      expect(done.running).toBe(false)

      // Heavier edge, at full opacity rather than the resting alpha.
      expect(run.borderWidth).toBeGreaterThan(done.borderWidth)
      expect(run.border).toBe(run.color)

      // Stronger fill: compare the trailing alpha byte of the two tints.
      const alpha = (hex: string) => parseInt(hex.slice(7, 9), 16)
      expect(alpha(run.bg)).toBeGreaterThan(alpha(done.bg))

      expect(run.glow).not.toBe('')
      expect(done.glow).toBe('')
    })
  }

  it('attaches the shared pulse only while running', () => {
    const run = runningNodeStyle(nodeColors('dark', 'running'))
    expect(run.animation).toContain('fmriflow-running-pulse')
    // The keyframes are colour-agnostic; each node supplies its own --pulse.
    expect((run as Record<string, string>)['--pulse']).toBe(nodeColors('dark', 'running').color)

    expect(runningNodeStyle(nodeColors('dark', 'done'))).toEqual({})
  })

  it('returns the neon table', () => {
    expect(statusPalette('dark')).toBe(DARK_STATUS)
    expect(statusPalette('light')).toBe(LIGHT_STATUS)
  })
})
