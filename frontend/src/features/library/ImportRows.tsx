import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { isProblemCode, type PreviewRow, type Problem } from '../../api/import'
import type { Candidate } from '../../api/library'
import { confirmable, isEdited, needsConfirmation, type RowState } from './importReview'

/** A problem in the user's language; the backend's English text for an unknown code. */
export function ProblemText({ problem, showLine }: { problem: Problem; showLine: boolean }) {
  const { t } = useTranslation()
  // Suggestions carry the values some messages name (`key`, `kept_line`).
  const values = { key: '?', kept_line: '?', ...problem.suggestion }
  const text = isProblemCode(problem.code) ? (
    t(`import.problem.${problem.code}`, values)
  ) : (
    <span lang="en">{problem.message}</span>
  )
  return (
    <span className={`problem problem--${problem.severity}`}>
      <span className="problem__severity">
        {problem.severity === 'ambiguous' || problem.severity === 'error' ? '⚠ ' : ''}
        {t(`import.severity.${problem.severity}`)}
      </span>
      {showLine && problem.line !== null && <> · {t('import.line', { line: problem.line })}</>}
      {' — '}
      {text}
    </span>
  )
}

function suggestedTerm(row: PreviewRow): string | null {
  for (const problem of row.problems) {
    const term = problem.suggestion?.term
    if (problem.code === 'looks_like_definition' && typeof term === 'string') return term
  }
  return null
}

function candidateLabel(c: Candidate, t: TFunction): string {
  const decks = c.decks.length > 0 ? ` — ${c.decks.map((d) => d.name).join(', ')}` : ''
  return t('import.rows.attachTo', {
    term: c.term,
    match: t(`library.match.${c.match}`),
    status: t(`library.status.${c.status}`),
  }) + decks
}

function Row({ state, onChange }: { state: RowState; onChange: (next: RowState) => void }) {
  const { t } = useTranslation()
  const { row } = state
  const suggestion = suggestedTerm(row)
  const waiting = needsConfirmation(state)

  return (
    <tr className={row.ambiguous ? 'import-row import-row--ambiguous' : 'import-row'}>
      <td data-label={t('import.rows.line')}>{row.line}</td>
      <td data-label={t('import.rows.include')} className="import-row__include">
        {waiting ? (
          confirmable(row) ? (
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={state.confirmed}
                onChange={(e) => onChange({ ...state, confirmed: e.target.checked })}
                aria-describedby={`row-${row.line}-problems`}
              />
              {t('import.rows.importAnyway')}
            </label>
          ) : (
            <span className="muted">{t('import.rows.mustCorrect')}</span>
          )
        ) : (
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={state.include}
              onChange={(e) => onChange({ ...state, include: e.target.checked })}
            />
            <span className="visually-hidden">{t('import.rows.includeLabel', { line: row.line })}</span>
          </label>
        )}
      </td>
      <td data-label={t('import.rows.term')} className="import-row__term">
        <input
          aria-label={t('import.rows.termLabel', { line: row.line })}
          value={state.term}
          maxLength={300}
          onChange={(e) => {
            const term = e.target.value
            const next = { ...state, term }
            // Correcting an ambiguous term includes it (the backend checks it again).
            if (row.ambiguous && term.trim() !== row.term) next.include = true
            onChange(next)
          }}
        />
        {suggestion !== null && state.term !== suggestion && (
          <button
            type="button"
            className="button button--small"
            onClick={() => onChange({ ...state, term: suggestion, include: true })}
          >
            {t('import.rows.useSuggestion', { term: suggestion })}
          </button>
        )}
      </td>
      <td data-label={t('import.rows.sentence')} className="import-row__wrap">{row.sentence ?? '—'}</td>
      <td data-label={t('import.rows.type')}>{t(`library.type.${row.item_type}`)}</td>
      <td data-label={t('import.rows.problems')} className="import-row__wrap" id={`row-${row.line}-problems`}>
        {row.problems.length === 0 ? (
          <span className="muted">{t('import.rows.ok')}</span>
        ) : (
          <ul className="problem-list">
            {row.problems.map((problem, index) => (
              <li key={index}>
                <ProblemText problem={problem} showLine={false} />
              </li>
            ))}
          </ul>
        )}
      </td>
      <td data-label={t('import.rows.duplicates')}>
        {state.duplicateChoice === null ? (
          <span className="muted">—</span>
        ) : isEdited(state) ? (
          <span className="muted">{t('import.rows.checkedAgain')}</span>
        ) : (
          <select
            aria-label={t('import.rows.duplicateLabel', { line: row.line })}
            value={state.duplicateChoice}
            onChange={(e) => onChange({ ...state, duplicateChoice: e.target.value })}
          >
            {row.duplicates.map((c) => (
              <option key={c.id} value={`attach:${c.id}`}>
                {candidateLabel(c, t)}
              </option>
            ))}
            <option value="new">{t('import.rows.new')}</option>
            <option value="skip">{t('import.rows.skip')}</option>
          </select>
        )}
      </td>
    </tr>
  )
}

export function ImportRows({
  rows,
  onChange,
}: {
  rows: RowState[]
  onChange: (index: number, next: RowState) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="table-wrap">
      <table className="import-table">
        <caption className="visually-hidden">{t('import.rows.caption')}</caption>
        <thead>
          <tr>
            <th scope="col">{t('import.rows.line')}</th>
            <th scope="col">{t('import.rows.include')}</th>
            <th scope="col">{t('import.rows.term')}</th>
            <th scope="col">{t('import.rows.sentence')}</th>
            <th scope="col">{t('import.rows.type')}</th>
            <th scope="col">{t('import.rows.problems')}</th>
            <th scope="col">{t('import.rows.duplicates')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((state, index) => (
            <Row key={state.row.line} state={state} onChange={(next) => onChange(index, next)} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
