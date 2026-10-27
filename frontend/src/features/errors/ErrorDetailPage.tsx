import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams } from 'react-router'

import {
  type ErrorOut,
  type ErrorPatch,
  MAX_ALTERNATIVES,
  type TermRef,
  useDeleteError,
  useError,
  useErrorCategories,
  usePatchError,
} from '../../api/errors'
import { PageTitle } from '../../components/PageTitle'
import { formatDateTime } from '../session/format'
import { ErrorText } from '../settings/ErrorText'
import { CategorySelect } from './CategorySelect'
import { findFragment, highlightSegments } from './fragment'
import { productionLink } from './logRules'
import { TermPicker } from './TermPicker'
import { Notice } from '../../components/Notice'
import { CorrectionMark } from '../../components/CorrectionMark'

/** The state the list passes to its rows, so the way back keeps the filters. */
function listPath(state: unknown): string {
  const search = (state as { search?: unknown } | null)?.search
  return `/errors${typeof search === 'string' ? search : ''}`
}

/** The original sentence with the incorrect form marked (underlined and bold, not colour only). */
function OriginalSentence({ error }: { error: ErrorOut }) {
  const { t } = useTranslation()
  if (error.original_text.trim() === '') {
    return <p className="muted">{t('errorLog.detail.noOriginal')}</p>
  }
  const located = findFragment(error.original_text, error.erroneous_text) !== null
  return (
    <>
      <p className="correction-text" lang="en">
        {highlightSegments(error.original_text, error.erroneous_text).map((part, index) =>
          part.kind === 'mark' ? (
            <mark key={index} className="correction-mark">
              {part.text}
            </mark>
          ) : (
            <span key={index}>{part.text}</span>
          ),
        )}
      </p>
      {!located && <p className="muted">{t('errorLog.detail.wrongNotFound')}</p>}
    </>
  )
}

/** The fields changed since the stored error: the PATCH sends only these. */
function changesOf(
  error: ErrorOut,
  draft: {
    correction: string
    alternatives: string[]
    explanation: string
    category: string
    term: TermRef | null
  },
): ErrorPatch {
  const patch: ErrorPatch = {}
  const correction = draft.correction.trim()
  if (correction !== error.correction) patch.correction = correction
  const alternatives = draft.alternatives.map((a) => a.trim()).filter((a) => a !== '')
  if (alternatives.join('\n') !== error.alternatives.join('\n')) patch.alternatives = alternatives
  const explanation = draft.explanation.trim()
  if (explanation !== error.explanation) patch.explanation = explanation
  if (draft.category !== error.category.code) patch.category_code = draft.category
  if ((draft.term?.id ?? null) !== (error.term?.id ?? null)) {
    patch.lexical_item_id = draft.term?.id ?? null
  }
  return patch
}

function EditForm({
  error,
  saved,
  onSaved,
}: {
  error: ErrorOut
  saved: boolean
  onSaved: (saved: boolean) => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const categories = useErrorCategories()
  const patch = usePatchError(error.id)
  const [correction, setCorrection] = useState(error.correction)
  const [alternatives, setAlternatives] = useState(error.alternatives)
  const [explanation, setExplanation] = useState(error.explanation)
  const [category, setCategory] = useState(error.category.code)
  const [term, setTerm] = useState<TermRef | null>(error.term)
  const [unchanged, setUnchanged] = useState(false)

  function submit(event: FormEvent) {
    event.preventDefault()
    onSaved(false)
    setUnchanged(false)
    const changes = changesOf(error, { correction, alternatives, explanation, category, term })
    if (Object.keys(changes).length === 0) {
      setUnchanged(true)
      return
    }
    patch.mutate(changes, { onSuccess: () => onSaved(true) })
  }

  const setAlternative = (index: number, value: string) =>
    setAlternatives(alternatives.map((a, i) => (i === index ? value : a)))

  return (
    <form onSubmit={submit} className="library-form">
      <div className="field">
        <label htmlFor={`${id}-correction`}>{t('errorLog.detail.correction')}</label>
        <input
          id={`${id}-correction`}
          lang="en"
          value={correction}
          maxLength={300}
          required
          onChange={(e) => setCorrection(e.target.value)}
        />
      </div>
      {alternatives.map((alternative, index) => (
        <div className="field" key={index}>
          <label htmlFor={`${id}-alt-${index}`}>
            {t('errorLog.detail.alternative', { n: index + 1 })}
          </label>
          <div className="inline-fields">
            <input
              id={`${id}-alt-${index}`}
              lang="en"
              value={alternative}
              maxLength={300}
              onChange={(e) => setAlternative(index, e.target.value)}
            />
            <button
              type="button"
              className="button button--small"
              onClick={() => setAlternatives(alternatives.filter((_, i) => i !== index))}
            >
              {t('errorLog.detail.removeAlternative', { n: index + 1 })}
            </button>
          </div>
        </div>
      ))}
      {alternatives.length < MAX_ALTERNATIVES && (
        <p>
          <button
            type="button"
            className="button button--small"
            onClick={() => setAlternatives([...alternatives, ''])}
          >
            {t('errorLog.detail.addAlternative')}
          </button>
        </p>
      )}
      <div className="field">
        <label htmlFor={`${id}-explanation`}>{t('errorLog.detail.explanation')}</label>
        <textarea
          id={`${id}-explanation`}
          lang="en"
          rows={3}
          maxLength={1000}
          value={explanation}
          onChange={(e) => setExplanation(e.target.value)}
        />
        {error.explanation_fr !== null && (
          <>
            <p className="field-hint muted">
              {t('errorLog.detail.explanationFrench')}: <span lang="fr">{error.explanation_fr}</span>
            </p>
            <p className="field-hint muted">{t('errorLog.detail.explanationNote')}</p>
          </>
        )}
      </div>
      <div className="field">
        <label htmlFor={`${id}-category`}>{t('errorLog.detail.category')}</label>
        <CategorySelect
          id={`${id}-category`}
          tree={categories.data ?? []}
          value={category}
          onChange={setCategory}
          mode="assign"
          current={error.category}
          required
        />
      </div>
      <div className="field">
        <span className="field__label">{t('errorLog.detail.term')}</span>
        <TermPicker id={`${id}-term`} value={term} onChange={setTerm} />
      </div>
      <div>
        <button type="submit" className="button button--primary" disabled={patch.isPending}>
          {patch.isPending ? t('errorLog.detail.saving') : t('errorLog.detail.save')}
        </button>
      </div>
      <div role="status">
        {saved && <Notice tone="success">{t('errorLog.detail.saved')}</Notice>}
        {unchanged && <p className="form-message">{t('errorLog.detail.unchanged')}</p>}
      </div>
      {patch.isError && <ErrorText error={patch.error} />}
    </form>
  )
}

/** Delete with an inline confirmation; focus goes to "Keep it" (D-067). */
function DeleteSection({ error, backTo }: { error: ErrorOut; backTo: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const remove = useDeleteError(error.id)
  const [confirming, setConfirming] = useState(false)
  const keep = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (confirming) keep.current?.focus()
  }, [confirming])

  return (
    <section className="card" aria-labelledby="error-delete-title">
      <h2 id="error-delete-title">{t('errorLog.detail.delete')}</h2>
      {!confirming ? (
        <button type="button" className="button button--danger" onClick={() => setConfirming(true)}>
          {t('errorLog.detail.delete')}
        </button>
      ) : (
        <div className="confirm" role="alertdialog" aria-label={t('errorLog.detail.deleteConfirm')}>
          <p>{t('errorLog.detail.deleteConfirm')}</p>
          <button
            type="button"
            className="button button--danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate(undefined, { onSuccess: () => void navigate(backTo) })}
          >
            {remove.isPending ? t('errorLog.detail.deleting') : t('errorLog.detail.deleteYes')}
          </button>
          <button ref={keep} type="button" className="button" onClick={() => setConfirming(false)}>
            {t('errorLog.detail.deleteKeep')}
          </button>
        </div>
      )}
      {remove.isError && <ErrorText error={remove.error} />}
    </section>
  )
}

export function ErrorDetailPage() {
  const { t, i18n } = useTranslation()
  const params = useParams()
  const location = useLocation()
  const id = Number(params.id)
  const valid = Number.isInteger(id) && id > 0
  const query = useError(valid ? id : 0, valid)
  const [saved, setSaved] = useState(false)
  const backTo = listPath(location.state)
  const error = query.data
  const text = error !== undefined ? productionLink(error) : null

  return (
    <div className="errors-page">
      <section className="hero">
        <PageTitle>{t('errorLog.detail.title')}</PageTitle>
        <p className="link-row">
          <Link to={backTo}>{t('errorLog.back')}</Link>
        </p>
        {error !== undefined && (
          <p className="muted">
            {t('errorLog.detail.meta', {
              source: t(`errorLog.source.${error.source}`),
              date: formatDateTime(error.occurred_at, i18n.language),
            })}
            {text !== null && (
              <>
                {' · '}
                <Link to={text}>
                  {error.source === 'drill' ? t('errorLog.detail.openDrill') : t('errorLog.detail.openText')}
                </Link>
              </>
            )}
          </p>
        )}
      </section>

      {!valid && (
        <Notice tone="danger" role="alert">
          {t('errors.error_not_found')}
        </Notice>
      )}
      {valid && query.isPending && <p className="muted">{t('errorLog.detail.loading')}</p>}
      {valid && query.isError && <ErrorText error={query.error} />}

      {error !== undefined && (
        <>
          <section className="card" aria-labelledby="error-original-title">
            <h2 id="error-original-title">{t('errorLog.detail.original')}</h2>
            <OriginalSentence error={error} />
            <p>
              <strong>{t('errorLog.detail.wrong')}:</strong>{' '}
              <span lang="en">
                <CorrectionMark wrong={error.erroneous_text} />
              </span>
            </p>
          </section>
          <section className="card" aria-labelledby="error-edit-title">
            <h2 id="error-edit-title">{t('errorLog.detail.edit')}</h2>
            <EditForm error={error} saved={saved} onSaved={setSaved} />
          </section>
          <DeleteSection error={error} backTo={backTo} />
        </>
      )}
    </div>
  )
}
