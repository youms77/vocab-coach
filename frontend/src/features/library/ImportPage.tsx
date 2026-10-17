import { useId, useState, type ChangeEvent, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { ApiError } from '../../api/client'
import {
  MAX_IMPORT_CHARS,
  useCommit,
  usePreview,
  type CommitBody,
  type ImportHeader,
  type ImportSummary,
  type Preview,
} from '../../api/import'
import { useDecks } from '../../api/library'
import { ErrorText } from '../settings/ErrorText'
import { ImportRows, ProblemText } from './ImportRows'
import { commitRow, initialRows, willImport, type RowState } from './importReview'

const HEADER_FIELDS = ['deck', 'domain', 'source', 'context', 'deadline'] as const

function HeaderSummary({ header }: { header: ImportHeader }) {
  const { t } = useTranslation()
  const present = HEADER_FIELDS.filter((key) => header[key] !== null && header[key] !== '')
  if (present.length === 0) return <p className="muted">{t('import.header.none')}</p>
  return (
    <dl className="import-header">
      {present.map((key) => (
        <div key={key}>
          <dt>{t(`import.header.${key}`)}</dt>
          <dd>{header[key]}</dd>
        </div>
      ))}
    </dl>
  )
}

function Summary({
  summary,
  intake,
  onAgain,
}: {
  summary: ImportSummary
  intake: CommitBody['intake']
  onAgain: () => void
}) {
  const { t } = useTranslation()
  return (
    <section className="card" aria-labelledby="import-done-title">
      <h2 id="import-done-title">{t('import.summary.title')}</h2>
      <ul role="status">
        <li>{t('import.summary.imported', { count: summary.imported })}</li>
        <li>{t('import.summary.attached', { count: summary.attached })}</li>
        <li>{t('import.summary.skipped', { count: summary.skipped })}</li>
        <li>{t('import.summary.ambiguous', { count: summary.ambiguous })}</li>
      </ul>
      {summary.created_deck && <p className="muted">{t('import.summary.createdDeck')}</p>}
      <p className="link-row">
        {intake === 'triage' && summary.imported > 0 && (
          <Link to={`/triage?deck=${summary.deck_id}`}>{t('import.summary.toTriage')}</Link>
        )}
        <Link to={`/library?deck=${summary.deck_id}`}>{t('import.summary.toDeck')}</Link>
        <button type="button" className="button" onClick={onAgain}>
          {t('import.summary.again')}
        </button>
      </p>
    </section>
  )
}

function rejectedLine(error: unknown): number | null {
  if (error instanceof ApiError && error.code === 'row_rejected') {
    const line = error.detail.line
    if (typeof line === 'number') return line
  }
  return null
}

function Review({
  preview,
  onDone,
}: {
  preview: Preview
  onDone: (summary: ImportSummary, intake: CommitBody['intake']) => void
}) {
  const { t } = useTranslation()
  const ids = { deck: useId(), name: useId() }
  const decks = useDecks()
  const commit = useCommit()
  const [rows, setRows] = useState<RowState[]>(() => initialRows(preview))
  const [targetKind, setTargetKind] = useState<'new' | 'existing'>('new')
  const [newName, setNewName] = useState(preview.header.deck ?? '')
  const [deckId, setDeckId] = useState('')
  const [intake, setIntake] = useState<CommitBody['intake']>('triage')
  const selected = rows.filter(willImport).length
  const targetMissing = targetKind === 'new' ? newName.trim() === '' : deckId === ''
  const failedLine = rejectedLine(commit.error)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (targetMissing || selected === 0) return
    const body: CommitBody = {
      header: preview.header,
      rows: rows.map(commitRow),
      target: targetKind === 'new' ? { new_deck_name: newName.trim() } : { deck_id: Number(deckId) },
      intake,
    }
    commit.mutate(body, { onSuccess: (summary) => onDone(summary, intake) })
  }

  return (
    <form onSubmit={submit} className="import-review">
      <section className="card" aria-labelledby="import-rows-title">
        <h2 id="import-rows-title">{t('import.rows.title')}</h2>
        <p className="muted">{t('import.rows.hint')}</p>
        <ImportRows
          rows={rows}
          onChange={(index, next) => setRows(rows.map((row, i) => (i === index ? next : row)))}
        />
      </section>

      <section className="card" aria-labelledby="import-target-title">
        <h2 id="import-target-title">{t('import.target.title')}</h2>
        <fieldset>
          <legend>{t('import.target.deck')}</legend>
          <label className="checkbox-line">
            <input
              type="radio"
              name="target"
              checked={targetKind === 'new'}
              onChange={() => setTargetKind('new')}
            />
            {t('import.target.new')}
          </label>
          {targetKind === 'new' && (
            <div className="field">
              <label htmlFor={ids.name}>{t('import.target.newName')}</label>
              <input
                id={ids.name}
                value={newName}
                maxLength={300}
                onChange={(e) => setNewName(e.target.value)}
              />
            </div>
          )}
          <label className="checkbox-line">
            <input
              type="radio"
              name="target"
              checked={targetKind === 'existing'}
              onChange={() => setTargetKind('existing')}
            />
            {t('import.target.existing')}
          </label>
          {targetKind === 'existing' && (
            <div className="field">
              <label htmlFor={ids.deck}>{t('import.target.pick')}</label>
              <select id={ids.deck} value={deckId} onChange={(e) => setDeckId(e.target.value)}>
                <option value="">{t('import.target.choose')}</option>
                {decks.data?.map((deck) => (
                  <option key={deck.id} value={deck.id}>
                    {deck.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </fieldset>
        <fieldset>
          <legend>{t('import.intake.title')}</legend>
          <label className="checkbox-line">
            <input
              type="radio"
              name="intake"
              checked={intake === 'triage'}
              onChange={() => setIntake('triage')}
            />
            {t('import.intake.triage')}
          </label>
          <label className="checkbox-line">
            <input
              type="radio"
              name="intake"
              checked={intake === 'queued'}
              onChange={() => setIntake('queued')}
            />
            {t('import.intake.queued')}
          </label>
        </fieldset>
        <p className="muted" role="status">
          {t('import.selected', { count: selected })}
        </p>
        {targetMissing && <p className="muted">{t('import.target.missing')}</p>}
        <button
          type="submit"
          className="button button--primary"
          disabled={commit.isPending || targetMissing || selected === 0}
        >
          {commit.isPending ? t('import.importing') : t('import.submit')}
        </button>
        {commit.isError && <ErrorText error={commit.error} />}
        {failedLine !== null && (
          <p className="form-message form-message--error">{t('import.line', { line: failedLine })}</p>
        )}
      </section>
    </form>
  )
}

export function ImportPage() {
  const { t, i18n } = useTranslation()
  // The app's language, never the browser's: 300,000 or 300 000.
  const max = new Intl.NumberFormat(i18n.language).format(MAX_IMPORT_CHARS)
  const ids = { text: useId(), file: useId() }
  const preview = usePreview()
  const [text, setText] = useState('')
  const [tooLarge, setTooLarge] = useState(false)
  const [fileError, setFileError] = useState(false)
  // A new key for each preview resets the review (rows, target) to that preview.
  const [run, setRun] = useState(0)
  const [done, setDone] = useState<{ summary: ImportSummary; intake: CommitBody['intake'] } | null>(
    null,
  )

  async function readFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    setFileError(false)
    if (file === undefined) return
    try {
      const content = await file.text()
      if (content.length > MAX_IMPORT_CHARS) {
        setTooLarge(true)
        return
      }
      setTooLarge(false)
      setText(content)
    } catch {
      setFileError(true)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (text.trim() === '') return
    if (text.length > MAX_IMPORT_CHARS) {
      setTooLarge(true)
      return
    }
    setTooLarge(false)
    setDone(null)
    preview.mutate({ text }, { onSuccess: () => setRun(run + 1) })
  }

  function again() {
    setDone(null)
    setText('')
    preview.reset()
  }

  const data = preview.data
  const globalProblems = data?.problems ?? []

  return (
    <div className="library-page">
      <section className="hero">
        <h1>{t('import.title')}</h1>
        <p className="muted">{t('import.intro')}</p>
        <p>
          <Link to="/library">{t('library.back')}</Link>
        </p>
      </section>

      {done !== null ? (
        <Summary summary={done.summary} intake={done.intake} onAgain={again} />
      ) : (
        <>
          <section className="card" aria-labelledby="import-input-title">
            <h2 id="import-input-title">{t('import.input.title')}</h2>
            <form onSubmit={submit} className="library-form import-input">
              <div className="field">
                <label htmlFor={ids.file}>{t('import.input.file')}</label>
                <input
                  id={ids.file}
                  type="file"
                  accept=".md,.txt,.markdown,text/markdown,text/plain"
                  onChange={(e) => void readFile(e)}
                />
              </div>
              <div className="field">
                <label htmlFor={ids.text}>{t('import.input.text')}</label>
                <textarea
                  id={ids.text}
                  rows={12}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  spellCheck={false}
                />
                <p className="field-hint">
                  {t('import.input.hint', { max })}
                </p>
              </div>
              {tooLarge && (
                <p className="form-message form-message--error" role="alert">
                  {t('import.input.tooLarge', { max })}
                </p>
              )}
              {fileError && (
                <p className="form-message form-message--error" role="alert">
                  {t('import.input.fileError')}
                </p>
              )}
              <button
                type="submit"
                className="button button--primary"
                disabled={preview.isPending || text.trim() === ''}
              >
                {preview.isPending ? t('import.input.previewing') : t('import.input.preview')}
              </button>
              {preview.isError && <ErrorText error={preview.error} />}
            </form>
          </section>

          {data !== undefined && (
            <>
              <section className="card" aria-labelledby="import-preview-title">
                <h2 id="import-preview-title">{t('import.preview.title')}</h2>
                <HeaderSummary header={data.header} />
                <p role="status">
                  {t('import.preview.counts', {
                    lines: data.lines_read,
                    importable: data.importable,
                    ambiguous: data.ambiguous,
                    duplicates: data.with_duplicates,
                  })}
                </p>
                {globalProblems.length > 0 && (
                  <ul className="problem-list">
                    {globalProblems.map((problem, index) => (
                      <li key={index}>
                        <ProblemText problem={problem} showLine />
                      </li>
                    ))}
                  </ul>
                )}
                {data.rejected && (
                  <p className="form-message form-message--error" role="alert">
                    {t('import.preview.rejected')}
                  </p>
                )}
                {!data.rejected && data.rows.length === 0 && (
                  <p className="muted">{t('import.preview.noRows')}</p>
                )}
              </section>
              {!data.rejected && data.rows.length > 0 && (
                <Review
                  key={run}
                  preview={data}
                  onDone={(summary, intake) => setDone({ summary, intake })}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
