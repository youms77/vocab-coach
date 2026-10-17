import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'

import {
  ITEM_TYPES,
  useChangeStatus,
  useDeleteItem,
  useItem,
  useMergeItem,
  usePatchItem,
  type ItemDetail,
  type ItemType,
} from '../../api/library'
import { ErrorText } from '../settings/ErrorText'

function EditForm({ item }: { item: ItemDetail }) {
  const { t } = useTranslation()
  const id = useId()
  const patch = usePatchItem(item.id)
  const [term, setTerm] = useState(item.term)
  const [sentence, setSentence] = useState(item.origin_sentence ?? '')
  const [itemType, setItemType] = useState<ItemType>(item.item_type)
  const [pos, setPos] = useState(item.part_of_speech ?? '')
  const [notes, setNotes] = useState(item.notes ?? '')
  const [saved, setSaved] = useState(false)

  function submit(event: FormEvent) {
    event.preventDefault()
    setSaved(false)
    patch.mutate(
      {
        term: term.trim(),
        origin_sentence: sentence.trim() === '' ? null : sentence.trim(),
        item_type: itemType,
        part_of_speech: pos.trim() === '' ? null : pos.trim(),
        notes: notes.trim() === '' ? null : notes.trim(),
      },
      { onSuccess: () => setSaved(true) },
    )
  }

  return (
    <form onSubmit={submit} className="library-form">
      <div className="field">
        <label htmlFor={`${id}-term`}>{t('library.quickAdd.term')}</label>
        <input id={`${id}-term`} value={term} onChange={(e) => setTerm(e.target.value)} required />
      </div>
      <div className="field">
        <label htmlFor={`${id}-sentence`}>{t('library.item.sentence')}</label>
        <input
          id={`${id}-sentence`}
          value={sentence}
          onChange={(e) => setSentence(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-type`}>{t('library.filters.type')}</label>
        <select
          id={`${id}-type`}
          value={itemType}
          onChange={(e) => setItemType(e.target.value as ItemType)}
        >
          {ITEM_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(`library.type.${type}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${id}-pos`}>{t('library.item.partOfSpeech')}</label>
        <input id={`${id}-pos`} value={pos} onChange={(e) => setPos(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`${id}-notes`}>{t('library.item.notes')}</label>
        <textarea
          id={`${id}-notes`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
        />
      </div>
      <button type="submit" className="button button--primary" disabled={patch.isPending}>
        {t('library.save')}
      </button>
      {saved && (
        <p className="form-message form-message--ok" role="status">
          {t('library.saved')}
        </p>
      )}
      {patch.isError && <ErrorText error={patch.error} />}
    </form>
  )
}

function Actions({ item }: { item: ItemDetail }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const status = useChangeStatus(item.id)
  const remove = useDeleteItem(item.id)
  const merge = useMergeItem(item.id)
  const [confirming, setConfirming] = useState(false)

  const archived = item.status === 'archived'

  return (
    <section className="card" aria-labelledby="actions-title">
      <h2 id="actions-title">{t('library.item.actions')}</h2>
      <div className="confirm">
        <button
          type="button"
          className="button"
          disabled={status.isPending}
          onClick={() => status.mutate(archived ? 'queued' : 'archived')}
        >
          {archived ? t('library.item.unarchive') : t('library.item.archive')}
        </button>
        {!confirming && (
          <button type="button" className="button button--danger" onClick={() => setConfirming(true)}>
            {t('library.item.delete')}
          </button>
        )}
      </div>
      {status.isError && <ErrorText error={status.error} />}
      {confirming && (
        <div className="confirm" role="alertdialog" aria-label={t('library.item.deleteConfirm')}>
          <p>{t('library.item.deleteConfirm', { term: item.term })}</p>
          <button
            type="button"
            className="button button--danger"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(undefined, { onSuccess: () => void navigate('/library') })
            }
          >
            {t('library.item.deleteYes')}
          </button>
          <button type="button" className="button" onClick={() => setConfirming(false)}>
            {t('library.cancel')}
          </button>
        </div>
      )}
      {remove.isError && <ErrorText error={remove.error} />}
      {item.duplicates.length > 0 && (
        <>
          <h3>{t('library.item.duplicates')}</h3>
          <ul>
            {item.duplicates.map((c) => (
              <li key={c.id}>
                <Link to={`/library/items/${c.id}`}>{c.term}</Link> ({t(`library.match.${c.match}`)}
                , {t(`library.status.${c.status}`)}){' '}
                <button
                  type="button"
                  className="button"
                  disabled={merge.isPending}
                  onClick={() =>
                    merge.mutate(c.id, {
                      onSuccess: (result) => void navigate(`/library/items/${result.kept_id}`),
                    })
                  }
                >
                  {t('library.item.mergeInto')}
                </button>
              </li>
            ))}
          </ul>
          {merge.isError && <ErrorText error={merge.error} />}
        </>
      )}
    </section>
  )
}

export function ItemDetailPage() {
  const { t } = useTranslation()
  const params = useParams()
  const itemId = Number(params.id)
  const item = useItem(itemId)

  return (
    <div className="library-page">
      <p>
        <Link to="/library">{t('library.back')}</Link>
      </p>
      {item.isPending && <p className="muted">{t('library.loading')}</p>}
      {item.isError && <ErrorText error={item.error} />}
      {item.isSuccess && (
        <>
          <section className="hero">
            <h1>{item.data.term}</h1>
            <p className="muted">
              {t(`library.type.${item.data.item_type}`)} · {t(`library.status.${item.data.status}`)}{' '}
              · {t('library.item.sheetIs', { state: t(`library.sheet.${item.data.sheet_status}`) })}
            </p>
          </section>
          <section className="card" aria-labelledby="edit-title">
            <h2 id="edit-title">{t('library.item.edit')}</h2>
            <EditForm key={item.data.updated_at} item={item.data} />
          </section>
          <section className="card" aria-labelledby="decks-title">
            <h2 id="decks-title">{t('library.terms.decks')}</h2>
            {item.data.deck_links.length === 0 ? (
              <p className="muted">{t('library.item.noDecks')}</p>
            ) : (
              <ul>
                {item.data.deck_links.map((link) => (
                  <li key={link.deck_id}>
                    <strong>{link.deck_name}</strong>
                    {link.context_sentence !== null && <> — {link.context_sentence}</>}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <Actions item={item.data} />
        </>
      )}
    </div>
  )
}
