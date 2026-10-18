import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { MAX_PROMPT_CHARS, TOPIC_TAGS, type TopicTag, useWritingTopics } from '../../api/productions'
import { ErrorText } from '../settings/ErrorText'

function Topic({
  id,
  en,
  fr,
  chosen,
  onChoose,
}: {
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
          {chosen ? t('writing.topics.chosen') : t('writing.topics.use')}
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
 * with the text: the English text of the topic, or what the user typed.
 */
export function TopicPicker({
  value,
  onChange,
}: {
  value: string | null
  onChange: (prompt: string | null) => void
}) {
  const { t } = useTranslation()
  const [tag, setTag] = useState<TopicTag | ''>('')
  const [own, setOwn] = useState(false)
  const [ownText, setOwnText] = useState('')
  const topics = useWritingTopics(tag)
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
      <h2 id={`${tagId}-title`}>{t('writing.topics.title')}</h2>
      <p className="muted">{t('writing.topics.intro')}</p>
      <div className="field">
        <label htmlFor={tagId}>{t('writing.topics.theme')}</label>
        <select id={tagId} value={tag} onChange={(event) => setTag(event.target.value as TopicTag | '')}>
          <option value="">{t('writing.topics.allThemes')}</option>
          {TOPIC_TAGS.map((name) => (
            <option key={name} value={name}>
              {t(`writing.topics.tags.${name}`)}
            </option>
          ))}
        </select>
      </div>
      {topics.isPending && <p className="muted">{t('writing.topics.loading')}</p>}
      {topics.isError && <ErrorText error={topics.error} />}
      {topics.isSuccess && topics.data.length === 0 && (
        <p className="muted">{t('writing.topics.empty')}</p>
      )}
      {topics.isSuccess && topics.data.length > 0 && (
        <ul className="topics">
          {topics.data.map((topic) => (
            <Topic
              key={topic.id}
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
          {t('writing.topics.own')}
        </button>
      </p>
      {own && (
        <div className="field">
          <label htmlFor={ownId}>{t('writing.topics.ownLabel', { max: MAX_PROMPT_CHARS })}</label>
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
          <strong>{t('writing.topics.current')}</strong> <span lang="en">{value}</span>{' '}
          <button
            type="button"
            className="button button--small"
            onClick={() => {
              setOwn(false)
              setOwnText('')
              onChange(null)
            }}
          >
            {t('writing.topics.clear')}
          </button>
        </p>
      )}
    </section>
  )
}
