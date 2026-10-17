import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import { useDecks, useQuickAdd, type Candidate, type QuickAddBody } from '../../api/library'
import { ErrorText } from '../settings/ErrorText'

function candidatesOf(error: unknown): Candidate[] {
  if (error instanceof ApiError && error.code === 'duplicate_term') {
    const list = error.detail.candidates
    if (Array.isArray(list)) return list as Candidate[]
  }
  return []
}

/** Adds one term. A possible duplicate is never blocking: the user picks attach or new. */
export function QuickAdd() {
  const { t } = useTranslation()
  const ids = { term: useId(), sentence: useId(), deck: useId() }
  const decks = useDecks()
  const quickAdd = useQuickAdd()
  const [term, setTerm] = useState('')
  const [sentence, setSentence] = useState('')
  const [deckId, setDeckId] = useState('')
  const [added, setAdded] = useState<string | null>(null)
  const [pending, setPending] = useState<QuickAddBody | null>(null)
  const candidates = pending === null ? [] : candidatesOf(quickAdd.error)

  function body(): QuickAddBody {
    const result: QuickAddBody = { term: term.trim() }
    if (sentence.trim() !== '') result.sentence = sentence.trim()
    if (deckId !== '') result.deck_id = Number(deckId)
    return result
  }

  function send(request: QuickAddBody) {
    setAdded(null)
    quickAdd.mutate(request, {
      onSuccess: (result) => {
        setAdded(result.item.term)
        setPending(null)
        setTerm('')
        setSentence('')
      },
      onError: () => setPending(request),
    })
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (term.trim() === '') return
    send(body())
  }

  return (
    <section className="card" aria-labelledby="quick-add-title">
      <h2 id="quick-add-title">{t('library.quickAdd.title')}</h2>
      <form onSubmit={submit} className="library-form">
        <div className="field">
          <label htmlFor={ids.term}>{t('library.quickAdd.term')}</label>
          <input
            id={ids.term}
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            maxLength={200}
            required
          />
        </div>
        <div className="field">
          <label htmlFor={ids.sentence}>{t('library.quickAdd.sentence')}</label>
          <input
            id={ids.sentence}
            value={sentence}
            onChange={(e) => setSentence(e.target.value)}
            maxLength={600}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.deck}>{t('library.quickAdd.deck')}</label>
          <select id={ids.deck} value={deckId} onChange={(e) => setDeckId(e.target.value)}>
            <option value="">{t('library.quickAdd.noDeck')}</option>
            {decks.data?.map((deck) => (
              <option key={deck.id} value={deck.id}>
                {deck.name}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="button button--primary" disabled={quickAdd.isPending}>
          {t('library.quickAdd.submit')}
        </button>
      </form>
      {added !== null && (
        <p className="form-message form-message--ok" role="status">
          {t('library.quickAdd.added', { term: added })}
        </p>
      )}
      {quickAdd.isError && candidates.length === 0 && <ErrorText error={quickAdd.error} />}
      {candidates.length > 0 && pending !== null && (
        <div className="form-message form-message--warn" role="alert">
          <p>{t('library.quickAdd.duplicates')}</p>
          <ul>
            {candidates.map((c) => (
              <li key={c.id}>
                <strong>{c.term}</strong> ({t(`library.match.${c.match}`)},{' '}
                {t(`library.status.${c.status}`)})
                {c.decks.length > 0 && <> — {c.decks.map((d) => d.name).join(', ')}</>}{' '}
                <button
                  type="button"
                  className="button"
                  onClick={() => send({ ...pending, on_duplicate: 'attach', attach_to: c.id })}
                >
                  {t('library.quickAdd.attach')}
                </button>
              </li>
            ))}
          </ul>
          <div className="confirm">
            <button
              type="button"
              className="button"
              onClick={() => send({ ...pending, on_duplicate: 'new' })}
            >
              {t('library.quickAdd.addAnyway')}
            </button>
            <button type="button" className="button" onClick={() => setPending(null)}>
              {t('library.cancel')}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
