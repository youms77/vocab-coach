/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { contrastRatio, parseHex, parseTokens, type Theme } from './contrast'

// The stylesheet itself is the input: the test reads the real tokens, not a copy. (A `?raw` import of a
// .css file is empty under Vitest, which does not process CSS.)
const css = readFileSync(join(import.meta.dirname, 'tokens.css'), 'utf8')
const tokens = parseTokens(css)
const THEMES: Theme[] = ['light', 'dark']

function ratio(theme: Theme, foreground: string, background: string): number {
  const fg = parseHex(tokens[theme][foreground] ?? '')
  const bg = parseHex(tokens[theme][background] ?? '')
  if (fg === null || bg === null) {
    throw new Error(`${theme}: --${foreground} or --${background} is missing or not a #hex colour`)
  }
  return contrastRatio(fg, bg)
}

/** One row per theme and pair, so a failure names the exact token and theme. */
function cases(foregrounds: string[], backgrounds: string[], minimum: number) {
  return THEMES.flatMap((theme) =>
    foregrounds.flatMap((fg) => backgrounds.map((bg) => [theme, fg, bg, minimum] as const)),
  )
}

const TEXT_ON_SURFACES = cases(
  ['ink', 'ink-muted', 'brand-strong'],
  ['bg', 'surface', 'surface-sunken', 'brand-tint'],
  4.5,
)

const PAIRS = [
  ...TEXT_ON_SURFACES,
  ...cases(['ink-subtle'], ['surface'], 4.5),
  ...cases(['on-brand'], ['brand'], 4.5),
  ...cases(['sidebar-ink', 'sidebar-ink-active'], ['sidebar'], 4.5),
  ...THEMES.flatMap((theme) =>
    (['success', 'warning', 'danger', 'accent'] as const).map(
      (status) => [theme, status, `${status}-tint`, 4.5] as const,
    ),
  ),
  ...cases(['border-strong', 'focus-ring'], ['bg', 'surface'], 3),
  ...cases(['chart-1', 'chart-2', 'chart-3', 'chart-4', 'chart-5'], ['surface'], 3),
  // The series colours also sit on the page background (a chart outside a card).
  ...cases(['chart-1', 'chart-2', 'chart-3', 'chart-4', 'chart-5'], ['bg'], 3),
]

describe('theme tokens', () => {
  it('defines both sides of every colour in tokens.css', () => {
    for (const name of ['ink', 'brand', 'border-strong', 'accent', 'chart-5', 'sidebar']) {
      expect(tokens.light[name], `light --${name}`).toBeDefined()
      expect(tokens.dark[name], `dark --${name}`).toBeDefined()
    }
  })

  it.each(PAIRS)('%s: --%s on --%s is at least %s:1', (theme, fg, bg, minimum) => {
    expect(ratio(theme, fg, bg)).toBeGreaterThanOrEqual(minimum)
  })

  it('finds the values computed for the redesign brief', () => {
    expect(ratio('light', 'border-strong', 'surface')).toBeCloseTo(3.65, 1)
    expect(ratio('dark', 'border-strong', 'surface')).toBeCloseTo(3.65, 1)
    expect(ratio('light', 'accent', 'accent-tint')).toBeCloseTo(5.16, 1)
  })

  it('keeps the chart series readable on the page background (4.2:1)', () => {
    for (const theme of THEMES) {
      for (const n of [1, 2, 3, 4, 5]) {
        expect(ratio(theme, `chart-${n}`, 'bg')).toBeGreaterThanOrEqual(4.2)
      }
    }
  })
})
