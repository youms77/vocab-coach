/** WCAG 2.x contrast helpers (pure). Used by `contrast.test.ts` to keep the theme tokens readable. */

export interface Rgb {
  r: number
  g: number
  b: number
}

/** Parses `#rgb` or `#rrggbb`. Returns null for anything else (rgba(), named colours, var()). */
export function parseHex(value: string): Rgb | null {
  const match = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(value.trim())
  if (match === null) return null
  const hex =
    match[1].length === 3
      ? match[1]
          .split('')
          .map((c) => c + c)
          .join('')
      : match[1]
  return {
    r: parseInt(hex.slice(0, 2), 16),
    g: parseInt(hex.slice(2, 4), 16),
    b: parseInt(hex.slice(4, 6), 16),
  }
}

function channel(value: number): number {
  const c = value / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

/** Relative luminance, 0 (black) to 1 (white). */
export function luminance({ r, g, b }: Rgb): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

/** Contrast ratio between two opaque colours, 1 to 21. */
export function contrastRatio(a: Rgb, b: Rgb): number {
  const la = luminance(a)
  const lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

export type Theme = 'light' | 'dark'
export type Tokens = Record<Theme, Record<string, string>>

/**
 * Reads `--name: light-dark(<light>, <dark>);` lines from the tokens stylesheet. A colour that
 * contains a comma (rgba()) is kept whole on each side.
 */
export function parseTokens(css: string): Tokens {
  const tokens: Tokens = { light: {}, dark: {} }
  const line = /^\s*--([a-z0-9-]+):\s*light-dark\(\s*(.+?)\s*,\s*(#[0-9a-f]{3,8}|rgba?\([^)]*\))\s*\);\s*$/gim
  for (const match of css.matchAll(line)) {
    tokens.light[match[1]] = match[2]
    tokens.dark[match[1]] = match[3]
  }
  return tokens
}
