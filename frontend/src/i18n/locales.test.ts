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

  // French typography (M10.c1, D-322): a no-break space before : ; ! ? and inside « », before a
  // unit (5 s, 10 Mo, 12 %); a typographic apostrophe; no space before a comma or a full stop.
  describe('French typography', () => {
    const rules: [string, RegExp][] = [
      ['a straight apostrophe (use ’)', /\p{L}'\p{L}/u],
      ['an ordinary space before : ; ! ?', /[^\s ] [:;!?](?=\s|$|[”»)])/],
      ['no space before : ; ! ?', /[^\s \d/][:;!?](?=\s|$)/],
      ['a « » without a no-break space', /«(?! )|(?<! )»/],
      ['an ordinary space before a unit', /(\}\}|\d) (s|min|h|Mo|Ko|Go|%)(?!\p{L})/u],
      ['three dots (use …)', /\.\.\./],
      ['a space before a comma', / ,/],
    ]
    for (const [name, rule] of rules) {
      it(`has no value with ${name}`, () => {
        const bad = [...frKeys].filter(([, value]) => rule.test(value)).map(([key]) => key)
        expect(bad).toEqual([])
      })
    }

    it('uses one apostrophe only: the typographic one', () => {
      const values = [...frKeys.values()]
      expect(values.some((value) => value.includes('’'))).toBe(true)
      expect(values.some((value) => /\p{L}'/u.test(value))).toBe(false)
    })
  })
})
