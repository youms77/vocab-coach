import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router'

import {
  type ErrorOut,
  MAX_ALTERNATIVES,
  type TermRef,
  useCreateError,
  useErrorCategories,
} from '../../api/errors'
import { PageTitle } from '../../components/PageTitle'
import { ErrorText } from '../settings/ErrorText'
import { CategorySelect } from './CategorySelect'
import { problemOf } from './logRules'
import { type ManualErrorPrefill, readPrefill } from './prefill'
import { TermPicker } from './TermPicker'

function ManualForm({
  onAdded,
  initial,
}: {
  onAdded: (error: ErrorOut) => void
  /** What a shadowing proposes (D-198): the form shows it, the user validates. */
  initial: ManualErrorPrefill | null
}) {
  const { t } = useTranslation()
  const id = useId()
  const categories = useErrorCategories()
  const create = useCreateError()
  const [original, setOriginal] = useState(initial?.original_text ?? '')
  const [wrong, setWrong] = useState(initial?.erroneous_text ?? '')
  const [correction, setCorrection] = useState(initial?.correction ?? '')
  const [alternatives, setAlternatives] = useState<string[]>([])
  const [category, setCategory] = useState(initial?.category_code ?? '')
  const [explanation, setExplanation] = useState(initial?.explanation ?? '')
  const [term, setTerm] = useState<TermRef | null>(null)
  const [attempted, setAttempted] = useState(false)
  const problem = problemOf(original, wrong, correction)

  function submit(event: FormEvent) {
    event.preventDefault()
    setAttempted(true)
    if (problem !== null) return
    create.mutate(
      {
        original_text: original.trim() === '' ? null : original.trim(),
        erroneous_text: wrong.trim(),
        correction: correction.trim(),
        alternatives: alternatives.map((a) => a.trim()).filter((a) => a !== ''),
        category_code: category,
        explanation: explanation.trim(),
        lexical_item_id: term?.id ?? null,
      },
      { onSuccess: onAdded },
    )
  }

  const setAlternative = (index: number, value: string) =>
    setAlternatives(alternatives.map((a, i) => (i === index ? value : a)))
  const showProblem = attempted && problem !== null

  return (
    <form onSubmit={submit} className="library-form">
      <div className="field">
        <label htmlFor={`${id}-original`}>{t('errorLog.manual.original')}</label>
        <textarea
          id={`${id}-original`}
          lang="en"
          rows={3}
          maxLength={1000}
          value={original}
          onChange={(e) => setOriginal(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-wrong`}>{t('errorLog.manual.wrong')}</label>
        <input
          id={`${id}-wrong`}
          lang="en"
          value={wrong}
          maxLength={300}
          required
          aria-invalid={showProblem && problem === 'wrongNotInOriginal'}
          aria-describedby={showProblem ? `${id}-problem` : undefined}
          onChange={(e) => setWrong(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-correction`}>{t('errorLog.manual.correction')}</label>
        <input
          id={`${id}-correction`}
          lang="en"
          value={correction}
          maxLength={300}
          required
          aria-invalid={showProblem && problem === 'sameAsCorrection'}
          aria-describedby={showProblem ? `${id}-problem` : undefined}
          onChange={(e) => setCorrection(e.target.value)}
        />
      </div>
      <div role="status" id={`${id}-problem`}>
        {showProblem && (
          <p className="field-hint field-hint--error">{t(`errorLog.manual.${problem}`)}</p>
        )}
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
        <label htmlFor={`${id}-category`}>{t('errorLog.manual.category')}</label>
        <CategorySelect
          id={`${id}-category`}
          tree={categories.data ?? []}
          value={category}
          onChange={setCategory}
          mode="assign"
          required
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-explanation`}>{t('errorLog.manual.explanation')}</label>
        <textarea
          id={`${id}-explanation`}
          lang="en"
          rows={2}
          maxLength={1000}
          value={explanation}
          onChange={(e) => setExplanation(e.target.value)}
        />
      </div>
      <div className="field">
        <span className="field__label">{t('errorLog.manual.term')}</span>
        <TermPicker id={`${id}-term`} value={term} onChange={setTerm} />
      </div>
      <div>
        <button type="submit" className="button button--primary" disabled={create.isPending}>
          {create.isPending ? t('errorLog.manual.saving') : t('errorLog.manual.submit')}
        </button>
      </div>
      {create.isError && <ErrorText error={create.error} />}
    </form>
  )
}

/** Adds an error typed by hand (source `manual`). The form empties after each success. */
export function ManualErrorPage() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const [added, setAdded] = useState<ErrorOut | null>(null)
  const [round, setRound] = useState(0)
  // The proposal of a shadowing is read once, then the router state is cleared: a reload (the
  // browser keeps the state) must not fill the form again. Only the first form shows it.
  const [prefill] = useState(() => readPrefill(location.state))
  const consumed = useRef(false)
  useEffect(() => {
    if (consumed.current || location.state === null || location.state === undefined) return
    consumed.current = true
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [location.state, location.pathname, location.search, navigate])
  const initial = round === 0 ? prefill : null

  return (
    <div className="errors-page">
      <section className="hero">
        <PageTitle>{t('errorLog.manual.title')}</PageTitle>
        <p className="muted">{t('errorLog.manual.intro')}</p>
        {initial !== null && (
          <p className="form-message form-message--warn">{t('errorLog.manual.prefilled')}</p>
        )}
        <p className="link-row">
          <Link to="/errors">{t('errorLog.back')}</Link>
        </p>
      </section>
      <div role="status">
        {added !== null && (
          <p className="form-message form-message--ok">
            {t('errorLog.manual.added')} <Link to={`/errors/${added.id}`}>{t('errorLog.manual.open')}</Link>
          </p>
        )}
      </div>
      <section className="card" aria-labelledby="manual-title">
        <h2 id="manual-title" className="visually-hidden">
          {t('errorLog.manual.title')}
        </h2>
        <ManualForm
          key={round}
          initial={initial}
          onAdded={(error) => {
            setAdded(error)
            setRound(round + 1)
          }}
        />
      </section>
    </div>
  )
}
