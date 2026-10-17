import type { CommitRow, OnDuplicate, Preview, PreviewRow } from '../../api/import'

/** Row state of the import review, kept apart from the components (pure, easy to test). */

// Ambiguities the backend accepts with `confirmed: true`; the others must be corrected.
const CONFIRMABLE = new Set(['looks_like_definition', 'looks_like_sentence'])

/** One preview row as the user reviews it. Sent as it is to the commit. */
export interface RowState {
  row: PreviewRow
  term: string
  include: boolean
  confirmed: boolean
  /** "attach:<id>", "new" or "skip"; null when the row has no duplicate. */
  duplicateChoice: string | null
}

export function initialRows(preview: Preview): RowState[] {
  return preview.rows.map((row) => {
    let duplicateChoice: string | null = null
    const first = row.duplicates[0]
    if (first !== undefined) {
      duplicateChoice = row.default_on_duplicate === 'attach' ? `attach:${first.id}` : 'new'
    }
    // An ambiguous row is never imported unless the user corrects or confirms it.
    return {
      row,
      term: row.term,
      include: row.include && !row.ambiguous,
      confirmed: false,
      duplicateChoice,
    }
  })
}

export function isEdited(state: RowState): boolean {
  return state.term.trim() !== state.row.term
}

/** The row still needs the user's confirmation (ambiguous, and its term was not corrected). */
export function needsConfirmation(state: RowState): boolean {
  return state.row.ambiguous && !isEdited(state)
}

export function confirmable(row: PreviewRow): boolean {
  return row.problems
    .filter((p) => p.severity === 'ambiguous')
    .every((p) => CONFIRMABLE.has(p.code))
}

export function commitRow(state: RowState): CommitRow {
  const { row } = state
  const include = needsConfirmation(state) ? state.confirmed : state.include
  const result: CommitRow = {
    line: row.line,
    term: state.term.trim(),
    sentence: row.sentence,
    item_type: row.item_type,
    include,
    confirmed: include && needsConfirmation(state),
  }
  // A corrected term may have other duplicates: let the backend pick its default.
  if (state.duplicateChoice !== null && !isEdited(state)) {
    if (state.duplicateChoice.startsWith('attach:')) {
      result.on_duplicate = 'attach'
      result.attach_to = Number(state.duplicateChoice.slice('attach:'.length))
    } else {
      result.on_duplicate = state.duplicateChoice as OnDuplicate
    }
  }
  return result
}

export function willImport(state: RowState): boolean {
  return commitRow(state).include
}
