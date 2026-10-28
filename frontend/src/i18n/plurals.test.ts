import i18next from 'i18next'
import { describe, expect, it } from 'vitest'

import en from './locales/en.json'
import fr from './locales/fr.json'

// M10.c1: every text with a number uses i18next's plural forms (`_one` / `_other`), in both
// languages. French counts 0 as singular ("0 terme"); English as plural ("0 terms").

type Tree = { [key: string]: string | Tree }

function flatten(tree: Tree, prefix = '', out = new Map<string, string>()): Map<string, string> {
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') out.set(path, value)
    else flatten(value, path, out)
  }
  return out
}

const FORM = /_(zero|one|two|few|many|other)$/
const bases = (keys: Map<string, string>) =>
  new Set([...keys.keys()].filter((k) => FORM.test(k)).map((k) => k.replace(FORM, '')))

const enKeys = flatten(en)
const frKeys = flatten(fr)
const forms = (keys: Map<string, string>, base: string) =>
  [...keys.keys()].filter((k) => k.startsWith(`${base}_`) && FORM.test(k)).map((k) => k.slice(base.length + 1))

const keys = (lng: string) => [...(lng === 'en' ? enKeys : frKeys).keys()]

describe('plural keys', () => {
  it('exist in both languages, with the same base keys', () => {
    expect([...bases(frKeys)].sort()).toEqual([...bases(enKeys)].sort())
  })

  it('always have _one and _other in both languages', () => {
    for (const base of bases(enKeys)) {
      for (const keys of [enKeys, frKeys]) {
        expect(forms(keys, base), base).toEqual(expect.arrayContaining(['one', 'other']))
      }
    }
  })

  it('never use the "(s)" shortcut', () => {
    for (const [key, value] of [...enKeys, ...frKeys]) expect(value, key).not.toMatch(/\(s\)|\(x\)/)
  })

  it('render a real sentence for 0, 1, 2 and 1000', async () => {
    const instance = i18next.createInstance()
    await instance.init({
      lng: 'en',
      resources: { en: { translation: en }, fr: { translation: fr } },
      interpolation: { escapeValue: false },
    })
    for (const lng of ['en', 'fr']) {
      const t = instance.getFixedT(lng)
      for (const base of bases(enKeys)) {
        for (const count of [0, 1, 2, 1000]) {
          // Any other placeholder gets a stand-in, so that only a missing form shows.
          const options: Record<string, unknown> = { count }
          for (const key of keys(lng)) {
            if (key.startsWith(`${base}_`)) {
              for (const m of (lng === 'en' ? enKeys : frKeys).get(key)!.matchAll(/{{\s*(\w+)\s*}}/g)) {
                if (m[1] !== 'count') options[m[1]!] = 'x'
              }
            }
          }
          const text = (t as (key: string, options: object) => string)(base, options)
          expect(text, `${lng} ${base} ${count}`).not.toBe(base)
          expect(text, `${lng} ${base} ${count}`).not.toMatch(/\{\{/)
        }
      }
    }
  })

  it('French reads 0 as singular and English as plural', async () => {
    const instance = i18next.createInstance()
    await instance.init({
      lng: 'en',
      resources: { en: { translation: en }, fr: { translation: fr } },
    })
    const say = (lng: string, key: string, count: number) =>
      (instance.getFixedT(lng) as (key: string, options: object) => string)(key, { count })
    const pluralOf = (lng: string, count: number) => new Intl.PluralRules(lng).select(count)
    expect(pluralOf('fr', 0)).toBe('one')
    expect(pluralOf('fr', 1)).toBe('one')
    expect(pluralOf('fr', 2)).toBe('other')
    expect(pluralOf('en', 0)).toBe('other')
    // The rendered text agrees: 0 takes the singular sentence in French, the plural one in English.
    const key = 'consolidation.summary.effectActive'
    expect(say('fr', key, 0)).toBe(say('fr', key, 1).replace('1', '0'))
    expect(say('fr', key, 0)).toBe('0 terme est devenu actif.')
    expect(say('en', key, 0)).toBe('0 terms became active.')
    expect(say('fr', key, 1000)).toBe('1000 termes sont devenus actifs.')
  })
})
