import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { MAX_PROMPT_CHARS } from '../../api/productions'
import { ErrorText } from '../settings/ErrorText'
import { type PickerNamespace, type TopicSource, WRITING_TOPICS } from './topicSource'

function Topic({
  ns,
  id,
  en,
  fr,
  chosen,
  onChoose,
}: {
  ns: PickerNamespace
  id: string
  en: string
  fr: string
  chosen: boolean
  onChoose: () => void
}) {
  const { t } = useTranslation()
  const [french, setFrench] = useState(false)
  const frenchId = useId()
  return (
    <li className={`topic${chosen ? ' topic--chosen' : ''}`} data-topic={id}>
      <p lang="en" className="topic__text">
        {en}
      </p>
      {french && (
        <p lang="fr" id={frenchId} className="muted">
          {fr}
        </p>
      )}
      <div className="topic__actions">
        <button type="button" className="button button--small" aria-pressed={chosen} onClick={onChoose}>
          {chosen ? t(`${ns}.chosen`) : t(`${ns}.use`)}
        </button>
        <button
          type="button"
          className="button button--small"
          aria-expanded={french}
          aria-controls={french ? frenchId : undefined}
          onClick={() => setFrench(!french)}
        >
          {french ? t('correction.hideFrench') : t('correction.showFrench')}
        </button>
      </div>
    </li>
  )
}

/**
 * Today's suggested topics (the same all day) or the user's own. The value is the prompt sent
 * with the text (or the recording): the English text of the topic, or what the user typed.
 * `source` says which topics and which wording: the writing page's (the default) or the speaking
 * page's.
 */
export function TopicPicker({
  value,
  onChange,
  source = WRITING_TOPICS,
}: {
  value: string | null
  onChange: (prompt: string | null) => void
  source?: TopicSource
}) {
  const { t } = useTranslation()
  const { ns } = source
  const [tag, setTag] = useState('')
  const [own, setOwn] = useState(false)
  const [ownText, setOwnText] = useState('')
  const topics = source.useTopics(tag)
  const tagId = useId()
  const ownId = useId()

  function toggleOwn() {
    if (own) {
      setOwn(false)
      setOwnText('')
      onChange(null)
    } else {
      setOwn(true)
      onChange(ownText.trim() === '' ? null : ownText.trim())
    }
  }

  return (
    <section className="card" aria-labelledby={`${tagId}-title`}>
      <h2 id={`${tagId}-title`}>{t(`${ns}.title`)}</h2>
      <p className="muted">{t(`${ns}.intro`)}</p>
      <div className="field">
        <label htmlFor={tagId}>{t(`${ns}.theme`)}</label>
        <select id={tagId} value={tag} onChange={(event) => setTag(event.target.value)}>
          <option value="">{t(`${ns}.allThemes`)}</option>
          {source.tags.map((name) => (
            <option key={name} value={name}>
              {source.tagLabel(t, name)}
            </option>
          ))}
        </select>
      </div>
      {topics.isPending && <p className="muted">{t(`${ns}.loading`)}</p>}
      {topics.isError && <ErrorText error={topics.error} />}
      {topics.isSuccess && topics.data.length === 0 && (
        <p className="muted">{t(`${ns}.empty`)}</p>
      )}
      {topics.isSuccess && topics.data.length > 0 && (
        <ul className="topics">
          {topics.data.map((topic) => (
            <Topic
              key={topic.id}
              ns={ns}
              id={topic.id}
              en={topic.en}
              fr={topic.fr}
              chosen={!own && value === topic.en}
              onChoose={() => {
                setOwn(false)
                onChange(value === topic.en ? null : topic.en)
              }}
            />
          ))}
        </ul>
      )}
      <p>
        <button type="button" className="button" aria-expanded={own} onClick={toggleOwn}>
          {t(`${ns}.own`)}
        </button>
      </p>
      {own && (
        <div className="field">
          <label htmlFor={ownId}>{t(`${ns}.ownLabel`, { max: MAX_PROMPT_CHARS })}</label>
          <input
            id={ownId}
            type="text"
            lang="en"
            maxLength={MAX_PROMPT_CHARS}
            value={ownText}
            onChange={(event) => {
              setOwnText(event.target.value)
              onChange(event.target.value.trim() === '' ? null : event.target.value.trim())
            }}
          />
        </div>
      )}
      {value !== null && (
        <p role="status" className="topic-chosen">
          <strong>{t(`${ns}.current`)}</strong> <span lang="en">{value}</span>{' '}
          <button
            type="button"
            className="button button--small"
            onClick={() => {
              setOwn(false)
              setOwnText('')
              onChange(null)
            }}
          >
            {t(`${ns}.clear`)}
          </button>
        </p>
      )}
    </section>
  )
}
