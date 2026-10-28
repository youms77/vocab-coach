import { describe, expect, it } from 'vitest'

import en from './locales/en.json'
import fr from './locales/fr.json'

// M10.c1: a French value identical to the English one is either a leftover (not translated) or a
// word that is the same in both languages. The second kind is listed here, with its reason. A new
// identical value fails the test until it is translated or listed.

type Tree = { [key: string]: string | Tree }

function flatten(tree: Tree, prefix = '', out = new Map<string, string>()): Map<string, string> {
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') out.set(path, value)
    else flatten(value, path, out)
  }
  return out
}

/** Values that are the same in French, and why. */
export const SAME_IN_FRENCH: ReadonlyMap<string, string> = new Map([
  ['vocab-coach', 'the name of the application'],
  ['Google Gemini', 'a product name'],
  ['Groq', 'a product name'],
  ['Microsoft Azure AI Speech', 'a product name'],
  ['http://127.0.0.1:11434', 'a web address (Ollama default)'],
  ['westeurope', 'an Azure region code'],
  ['OK', 'the same word in French'],
  ['NGSL / NAWL 1.2, Browne, Culligan & Phillips, CC BY-SA 4.0', 'a licence citation'],
  ['Consolidation', 'a French word, same spelling (glossary: consolidation)'],
  ['Menu', 'a French word, same spelling'],
  ['Section', 'a French word, same spelling'],
  ['Transcription', 'a French word, same spelling'],
  ['Audio', 'a French word, same spelling'],
  ['Source', 'a French word, same spelling'],
  ['Type', 'a French word, same spelling'],
  ['Collocation', 'a French linguistic term, same spelling'],
  ['Pages', 'a French word, same spelling'],
  ['Notes', 'a French word, same spelling'],
  ['Actions', 'a French word, same spelling'],
  ['Situation', 'a French word, same spelling'],
  ['Question', 'a French word, same spelling'],
  ['Campus', 'a French word, same spelling'],
  ['Correction', 'a French word, same spelling'],
  ['Date', 'a French word, same spelling'],
  ['Correct', 'a French word, same spelling'],
  ['Incorrect', 'a French word, same spelling'],
  ['Structure', 'a French word, same spelling'],
  ['Suggestions', 'a French word, same spelling'],
  ['active', 'a French word (feminine), same spelling'],
  ['Score', 'a French word, same spelling'],
  ['Export', 'a French word, same spelling'],
  ['Dialogue', 'a French word, same spelling'],
  ['dialogue', 'a French word, same spelling'],
  ['Stable', 'a French word, same spelling'],
  ['Production', 'a French word, same spelling'],
  ['Version {{version}}', 'a French word, same spelling'],
  ['Shadowing', 'the technique keeps its English name (glossary: shadowing)'],
  ['shadowing', 'the technique keeps its English name (glossary: shadowing)'],
  ['{{count}} shadowing', 'the technique keeps its English name (glossary: shadowing)'],
  ['{{count}} shadowings', 'the technique keeps its English name (glossary: shadowing)'],
  ['{{count}} conversation', 'a French word, same spelling'],
  ['{{count}} conversations', 'a French word, same spelling'],
  ['{{count}} minute', 'a French word, same spelling'],
  ['{{count}} minutes', 'a French word, same spelling'],
  ['{{minutes}} minutes', 'a French word, same spelling'],
  ['{{value}} ms', 'a unit symbol'],
])

describe('French values identical to English', () => {
  const enKeys = flatten(en)
  const frKeys = flatten(fr)

  it('are only words that really are the same, listed with a reason', () => {
    const leftovers: string[] = []
    for (const [key, value] of enKeys) {
      if (frKeys.get(key) !== value) continue
      const words = value.replace(/\{\{[^}]*\}\}/g, '').match(/\p{L}{3,}/gu)
      if (words === null) continue // numbers, units and placeholders only
      if (!SAME_IN_FRENCH.has(value)) leftovers.push(`${key} = ${value}`)
    }
    expect(leftovers).toEqual([])
  })

  it('has no stale entry in the list', () => {
    const used = new Set<string>()
    for (const [key, value] of enKeys) if (frKeys.get(key) === value) used.add(value)
    expect([...SAME_IN_FRENCH.keys()].filter((value) => !used.has(value))).toEqual([])
  })

  it('addresses the user as "vous", never "tu"', () => {
    const informal =
      /(?<![\p{L}’-])(tu|toi|ton|ta|tes|t’|te|as-tu|es-tu|peux-tu|veux-tu|saisis|choisis|clique|ajoute)(?![\p{L}-])/iu
    const bad = [...frKeys]
      .filter(([, value]) => informal.test(value.replace(/\{\{[^}]*\}\}/g, '')))
      .map(([key]) => key)
    expect(bad).toEqual([])
  })

  it('does not leave the English word "deck" where the glossary says "paquet"', () => {
    const bad = [...frKeys]
      .filter(([, value]) => /\bdecks?\b/i.test(value.replace(/\{\{[^}]*\}\}/g, '')))
      .map(([key]) => key)
    expect(bad).toEqual([])
  })
})
