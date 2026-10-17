import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import {
  useCreateDeck,
  useDecks,
  useDeleteDeck,
  usePatchDeck,
  type Deck,
} from '../../api/library'
import { ErrorText } from '../settings/ErrorText'
import { ExtensionPanel } from './ExtensionPanel'

function NewDeck() {
  const { t } = useTranslation()
  const id = useId()
  const create = useCreateDeck()
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      { name: name.trim(), domain: domain.trim() === '' ? null : domain.trim() },
      {
        onSuccess: () => {
          setName('')
          setDomain('')
        },
      },
    )
  }

  return (
    <section className="card" aria-labelledby="new-deck-title">
      <h2 id="new-deck-title">{t('library.decks.new')}</h2>
      <form onSubmit={submit} className="library-form">
        <div className="field">
          <label htmlFor={`${id}-name`}>{t('library.decks.name')}</label>
          <input
            id={`${id}-name`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor={`${id}-domain`}>{t('library.filters.domain')}</label>
          <input id={`${id}-domain`} value={domain} onChange={(e) => setDomain(e.target.value)} />
        </div>
        <button type="submit" className="button button--primary" disabled={create.isPending}>
          {t('library.decks.create')}
        </button>
      </form>
      {create.isError && <ErrorText error={create.error} />}
    </section>
  )
}

function DeckRow({ deck }: { deck: Deck }) {
  const { t } = useTranslation()
  const patch = usePatchDeck(deck.id)
  const remove = useDeleteDeck(deck.id)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(deck.name)
  const [confirming, setConfirming] = useState(false)
  const nameId = useId()

  return (
    <li className="deck-row">
      {editing ? (
        <form
          className="inline-fields"
          onSubmit={(e) => {
            e.preventDefault()
            patch.mutate({ name: name.trim() }, { onSuccess: () => setEditing(false) })
          }}
        >
          <label htmlFor={nameId} className="visually-hidden">
            {t('library.decks.name')}
          </label>
          <input id={nameId} value={name} onChange={(e) => setName(e.target.value)} required />
          <button type="submit" className="button button--primary" disabled={patch.isPending}>
            {t('library.save')}
          </button>
          <button type="button" className="button" onClick={() => setEditing(false)}>
            {t('library.cancel')}
          </button>
        </form>
      ) : (
        <div className="deck-row__main">
          <h3>
            <Link to={`/library?deck=${deck.id}`}>{deck.name}</Link>
          </h3>
          <p className="muted">
            {t('library.decks.count', { count: deck.item_count })}
            {deck.domain !== null && <> · {deck.domain}</>}
          </p>
          <div className="confirm">
            <button type="button" className="button" onClick={() => setEditing(true)}>
              {t('library.decks.rename')}
            </button>
            <ExtensionPanel deck={deck} />
            {!confirming && (
              <button
                type="button"
                className="button button--danger"
                onClick={() => setConfirming(true)}
              >
                {t('library.decks.delete')}
              </button>
            )}
          </div>
        </div>
      )}
      {confirming && (
        <div className="confirm" role="alertdialog" aria-label={t('library.decks.deleteConfirm')}>
          <p>{t('library.decks.deleteConfirm', { name: deck.name })}</p>
          <button
            type="button"
            className="button button--danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate(undefined, { onSuccess: () => setConfirming(false) })}
          >
            {t('library.decks.deleteYes')}
          </button>
          <button type="button" className="button" onClick={() => setConfirming(false)}>
            {t('library.cancel')}
          </button>
        </div>
      )}
      {patch.isError && <ErrorText error={patch.error} />}
      {remove.isError && <ErrorText error={remove.error} />}
    </li>
  )
}

export function DecksPage() {
  const { t } = useTranslation()
  const decks = useDecks()

  return (
    <div className="library-page">
      <p>
        <Link to="/library">{t('library.back')}</Link>
      </p>
      <section className="hero">
        <h1>{t('library.decks.title')}</h1>
        <p className="muted">{t('library.decks.intro')}</p>
      </section>
      <NewDeck />
      <section className="card" aria-labelledby="deck-list-title">
        <h2 id="deck-list-title">{t('library.decks.list')}</h2>
        {decks.isPending && <p className="muted">{t('library.loading')}</p>}
        {decks.isError && <ErrorText error={decks.error} />}
        {decks.isSuccess && decks.data.length === 0 && (
          <p className="muted">{t('library.decks.empty')}</p>
        )}
        {decks.isSuccess && decks.data.length > 0 && (
          <ul className="deck-list">
            {decks.data.map((deck) => (
              <DeckRow key={deck.id} deck={deck} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
