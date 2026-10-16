import { describe, expect, it } from 'vitest'

import en from './locales/en.json'
import fr from './locales/fr.json'

type Tree = { [key: string]: string | Tree }

function flatten(tree: Tree, prefix = ''): Map<string, string> {
  const out = new Map<string, string>()
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') {
      out.set(path, value)
    } else {
      for (const [k, v] of flatten(value, path)) out.set(k, v)
    }
  }
  return out
}

const interpolations = (text: string) => [...text.matchAll(/{{\s*(\w+)\s*}}/g)].map((m) => m[1]).sort()

describe('translation files', () => {
  const enKeys = flatten(en)
  const frKeys = flatten(fr)

  it('French has exactly the same keys as English', () => {
    expect([...frKeys.keys()].sort()).toEqual([...enKeys.keys()].sort())
  })

  it('no translation is empty', () => {
    for (const [key, value] of [...enKeys, ...frKeys]) {
      expect(value.trim(), key).not.toBe('')
    }
  })

  it('French keeps the same {{placeholders}} as English', () => {
    for (const [key, value] of enKeys) {
      expect(interpolations(frKeys.get(key) ?? ''), key).toEqual(interpolations(value))
    }
  })
})
