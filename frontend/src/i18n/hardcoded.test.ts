/// <reference types="node" />
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

// M10.c1: every user-visible string goes through i18n (CLAUDE.md). This test reads the sources
// with the TypeScript compiler (already a dev dependency) and reports:
//   - JSX text that contains a letter;
//   - string literals in the accessible attributes (aria-label, title, placeholder, alt, label...);
//   - literals passed to announce(), confirm(), alert() or assigned to document.title;
//   - a hand-built `Intl.*` / `toLocale*String` outside src/i18n/format.ts (the one formatting module);
//   - plurals decided by hand (`count === 1 ? ...`) instead of i18next's `_one` / `_other`.
// Tests, fixtures and the style guide (development only, D-291) are not scanned.

const SRC = join(import.meta.dirname, '..')

const ATTRIBUTES = new Set([
  'aria-label',
  'aria-description',
  'aria-placeholder',
  'aria-roledescription',
  'title',
  'placeholder',
  'alt',
  'label',
])
const CALLS = new Set(['announce', 'confirm', 'alert', 'window.confirm', 'window.alert'])

/** Text that is not translatable, with the reason. Matched on the trimmed text. */
export const ALLOWED_TEXT: ReadonlyMap<string, string> = new Map([
  ['v', 'the "v" before the version number (v1.0.0): a symbol, not a word'],
  ['newgeneralservicelist.com', 'a web address shown as the source of the word list'],
])

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (!/^(styleguide|test|fixtures|node_modules)$/.test(entry.name)) sourceFiles(path, out)
    } else if (/\.tsx?$/.test(entry.name) && !/\.(test|d)\.tsx?$/.test(entry.name)) {
      out.push(path)
    }
  }
  return out
}

const hasLetter = (text: string) => /\p{L}/u.test(text)

const isLiteral = (node: ts.Node): node is ts.StringLiteral | ts.NoSubstitutionTemplateLiteral =>
  ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)

/** Every finding of one source text, as "line kind: text". */
export function findHardcoded(file: string, source: string): string[] {
  const sf = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    true,
    file.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  )
  const found: string[] = []
  const report = (node: ts.Node, kind: string, text: string) => {
    if (ALLOWED_TEXT.has(text.trim())) return
    const line = sf.getLineAndCharacterOfPosition(node.getStart()).line + 1
    found.push(`${line} ${kind}: ${text.replace(/\s+/g, ' ').trim().slice(0, 70)}`)
  }
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node) && hasLetter(node.text)) report(node, 'JSX text', node.text)
    if (ts.isJsxAttribute(node) && ATTRIBUTES.has(node.name.getText()) && node.initializer) {
      const value = ts.isJsxExpression(node.initializer)
        ? node.initializer.expression
        : node.initializer
      if (value !== undefined && isLiteral(value) && hasLetter(value.text)) {
        report(node, `attribute ${node.name.getText()}`, value.text)
      }
    }
    if (ts.isCallExpression(node) && CALLS.has(node.expression.getText())) {
      const first = node.arguments[0]
      if (first !== undefined && (isLiteral(first) || ts.isTemplateExpression(first))) {
        report(node, `${node.expression.getText()}()`, first.getText())
      }
    }
    if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      node.left.getText() === 'document.title' &&
      (isLiteral(node.right) || ts.isTemplateExpression(node.right))
    ) {
      report(node, 'document.title', node.right.getText())
    }
    if (ts.isNewExpression(node) && /^Intl\./.test(node.expression.getText())) {
      report(node, 'hand-built Intl formatter (use i18n/format.ts)', node.getText())
    }
    if (
      ts.isCallExpression(node) &&
      ts.isPropertyAccessExpression(node.expression) &&
      /^toLocale(Date|Time)?String$/.test(node.expression.name.text)
    ) {
      report(node, 'toLocale*String (use i18n/format.ts)', node.getText())
    }
    // A plural decided by hand: `count === 1 ? ... : ...` where a branch is a string literal.
    if (ts.isConditionalExpression(node)) {
      const test = node.condition.getText()
      if (
        /\b(count|n|total)\s*===?\s*1\b/.test(test) &&
        (isLiteral(node.whenTrue) || isLiteral(node.whenFalse))
      ) {
        report(node, 'plural by hand (use _one / _other)', node.getText())
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return found
}

describe('no hard-coded user-visible string', () => {
  it('finds none in the sources', { timeout: 60_000 }, () => {
    const problems: string[] = []
    for (const file of sourceFiles(SRC)) {
      if (file.endsWith(join('i18n', 'format.ts'))) continue // the one place that builds Intl formatters
      const rel = relative(SRC, file).split(sep).join('/')
      for (const finding of findHardcoded(file, readFileSync(file, 'utf8'))) {
        problems.push(`${rel}:${finding}`)
      }
    }
    expect(problems).toEqual([])
  })

  // The detector itself must see what it is for.
  it('sees a string written in JSX, in an attribute and in announce()', () => {
    const found = findHardcoded(
      'Case.tsx',
      `export const A = () => <button aria-label="Close the panel" title={'Close'}>Save it</button>
       announce('Saved')
       document.title = 'Home'
       const f = new Intl.NumberFormat('en')
       const x = count === 1 ? 'term' : 'terms'`,
    )
    expect(found.map((f) => f.split(':')[0]?.split(' ').slice(1).join(' '))).toEqual([
      'attribute aria-label',
      'attribute title',
      'JSX text',
      'announce()',
      'document.title',
      'hand-built Intl formatter (use i18n/format.ts)',
      'plural by hand (use _one / _other)',
    ])
  })

  it('lets translated text and non-words through', () => {
    expect(
      findHardcoded(
        'Fine.tsx',
        `export const A = () => <button aria-label={t('a.b')}>{t('c.d')} · 12 / 40 →</button>`,
      ),
    ).toEqual([])
  })
})
