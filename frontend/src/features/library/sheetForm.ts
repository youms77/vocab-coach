import type { ExampleKind, Register, UsageSheet } from '../../api/enrichment'

/**
 * The sheet editor's state: the stored sheet with every text as a string ('' = empty), so inputs
 * stay controlled. `toSheet` turns it back into what `PUT /items/{id}/sheet` accepts: trimmed text,
 * `null` for an empty field, list rows left blank dropped.
 */
export interface SheetDraft {
  part_of_speech: string
  register_level: Register | ''
  register_note: string
  meaning_in_context: string
  definition_simple: string
  translation_fr: string[]
  other_meanings: { definition: string; translation_fr: string }[]
  usage_notes: string
  collocations: { pattern: string; example: string }[]
  examples: { sentence: string; kind: ExampleKind }[]
  word_family: { form: string; part_of_speech: string }[]
  pronunciation: { ipa_us: string; stressed_syllable: string; note: string }
  french_speaker_pitfalls: { wrong: string; right: string; explanation: string }[]
  confusables: { term: string; difference: string }[]
}

export type ListField =
  | 'translation_fr'
  | 'other_meanings'
  | 'collocations'
  | 'examples'
  | 'word_family'
  | 'french_speaker_pitfalls'
  | 'confusables'

// Maximum rows per list, as in the backend schema (`UsageSheet`).
export const LIST_MAX: Record<ListField, number> = {
  translation_fr: 3,
  other_meanings: 3,
  collocations: 8,
  examples: 5,
  word_family: 6,
  french_speaker_pitfalls: 4,
  confusables: 3,
}

export const EMPTY_ROW = {
  translation_fr: '',
  other_meanings: { definition: '', translation_fr: '' },
  collocations: { pattern: '', example: '' },
  examples: { sentence: '', kind: 'general' as ExampleKind },
  word_family: { form: '', part_of_speech: '' },
  french_speaker_pitfalls: { wrong: '', right: '', explanation: '' },
  confusables: { term: '', difference: '' },
} satisfies { [K in ListField]: SheetDraft[K][number] }

const text = (value: string | null | undefined) => value ?? ''
const clean = (value: string) => (value.trim() === '' ? null : value.trim())

export function fromSheet(sheet: UsageSheet | null, partOfSpeech: string | null = null): SheetDraft {
  return {
    part_of_speech: text(sheet?.part_of_speech ?? partOfSpeech),
    register_level: sheet?.register_level ?? '',
    register_note: text(sheet?.register_note),
    meaning_in_context: text(sheet?.meaning_in_context),
    definition_simple: text(sheet?.definition_simple),
    translation_fr: [...(sheet?.translation_fr ?? [])],
    other_meanings: (sheet?.other_meanings ?? []).map((m) => ({ ...m })),
    usage_notes: text(sheet?.usage_notes),
    collocations: (sheet?.collocations ?? []).map((c) => ({
      pattern: c.pattern,
      example: text(c.example),
    })),
    examples: (sheet?.examples ?? []).map((e) => ({ ...e })),
    word_family: (sheet?.word_family ?? []).map((w) => ({ ...w })),
    pronunciation: {
      ipa_us: text(sheet?.pronunciation?.ipa_us),
      stressed_syllable: text(sheet?.pronunciation?.stressed_syllable),
      note: text(sheet?.pronunciation?.note),
    },
    french_speaker_pitfalls: (sheet?.french_speaker_pitfalls ?? []).map((p) => ({ ...p })),
    confusables: (sheet?.confusables ?? []).map((c) => ({ ...c })),
  }
}

/** Keeps the rows whose required texts are all filled, trimmed. */
function rows<T extends Record<string, string>>(list: T[], required: (keyof T)[]): T[] {
  return list
    .map((row) => {
      const out = { ...row }
      for (const key of Object.keys(out) as (keyof T)[]) {
        out[key] = (out[key] as string).trim() as T[keyof T]
      }
      return out
    })
    .filter((row) => required.every((key) => row[key] !== ''))
}

export function toSheet(draft: SheetDraft): UsageSheet {
  const pronunciation = {
    ipa_us: clean(draft.pronunciation.ipa_us),
    stressed_syllable: clean(draft.pronunciation.stressed_syllable),
    note: clean(draft.pronunciation.note),
  }
  const hasPronunciation = Object.values(pronunciation).some((v) => v !== null)
  return {
    schema_version: 1,
    part_of_speech: clean(draft.part_of_speech),
    register_level: draft.register_level === '' ? null : draft.register_level,
    register_note: clean(draft.register_note),
    meaning_in_context: clean(draft.meaning_in_context),
    definition_simple: clean(draft.definition_simple),
    translation_fr: draft.translation_fr.map((v) => v.trim()).filter((v) => v !== ''),
    other_meanings: rows(draft.other_meanings, ['definition', 'translation_fr']),
    usage_notes: clean(draft.usage_notes),
    collocations: rows(draft.collocations, ['pattern']).map((c) => ({
      pattern: c.pattern,
      example: c.example === '' ? null : c.example,
    })),
    examples: draft.examples
      .map((e) => ({ sentence: e.sentence.trim(), kind: e.kind }))
      .filter((e) => e.sentence !== ''),
    word_family: rows(draft.word_family, ['form', 'part_of_speech']),
    pronunciation: hasPronunciation ? pronunciation : null,
    french_speaker_pitfalls: rows(draft.french_speaker_pitfalls, ['wrong', 'right', 'explanation']),
    confusables: rows(draft.confusables, ['term', 'difference']),
  }
}

/** The backend's one content rule for a saved sheet: a simple definition or a French translation. */
export function hasMeaning(sheet: UsageSheet): boolean {
  return sheet.definition_simple !== null || sheet.translation_fr.length > 0
}
