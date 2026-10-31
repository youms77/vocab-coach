import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

import { MAX_TEXT_CHARS, useCreateProduction } from '../../api/productions'
import { ErrorText } from '../settings/ErrorText'
import { clearDraft, countText, loadDraft, saveDraft } from './draft'
import { TopicPicker } from './TopicPicker'
import { Notice } from '../../components/Notice'
import { Icon } from '../../components/Icon'
import { SectionHeader } from '../../components/SectionHeader'
import { sectionArt } from '../../components/sectionArt'

/**
 * Free writing: pick a topic (or your own), write, send. The text is saved first, then the page
 * of that production (`/writing/:id`, history replaced so a reload never creates it again) runs
 * the AI correction and shows it.
 */
export function WritingPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const create = useCreateProduction()
  const [text, setText] = useState(loadDraft)
  const [prompt, setPrompt] = useState<string | null>(null)
  const fieldId = useId()
  const countId = useId()

  const { words, chars } = countText(text)
  const tooLong = chars > MAX_TEXT_CHARS
  const empty = text.trim() === ''
  const sending = create.isPending || create.isSuccess

  function change(value: string) {
    setText(value)
    saveDraft(value)
  }

  function submit() {
    if (empty || tooLong || sending) return
    create.mutate(
      { kind: 'writing', text, prompt, target_item_ids: [], study_session_id: null },
      {
        onSuccess: (created) => {
          clearDraft()
          navigate(`/writing/${created.id}`, { replace: true, state: { autoCorrect: true } })
        },
      },
    )
  }

  return (
    <div className="writing-page">
      <SectionHeader
        eyebrow={`${t('nav.section')} · ${t('nav.groups.practice')}`}
        title={t('writing.title')}
        description={t('writing.intro')}
        illustration={sectionArt('writing')}
        actions={
          <>
            <Link to="/writing/history" className="button">
              <Icon name="history" size={18} />
              {t('writing.historyLink')}
            </Link>
            <Link to="/transcripts" className="button">
              {t('writing.transcriptLink')}
            </Link>
          </>
        }
      />

      <TopicPicker value={prompt} onChange={setPrompt} />

      <form
        className="card writing-form"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <div className="field">
          <label htmlFor={fieldId}>{t('writing.text.label')}</label>
          <textarea
            id={fieldId}
            lang="en"
            rows={10}
            value={text}
            onChange={(event) => change(event.target.value)}
            readOnly={sending}
            aria-describedby={countId}
            aria-invalid={tooLong}
          />
          <p id={countId} className={`field-hint${tooLong ? ' field-hint--error' : ''}`}>
            {t('writing.text.words', { count: words })} ·{' '}
            {t('writing.text.chars', { chars, max: MAX_TEXT_CHARS })}
          </p>
          {tooLong && (
            <Notice tone="danger" role="alert">
              {t('writing.text.tooLong', { chars, max: MAX_TEXT_CHARS })}
            </Notice>
          )}
        </div>
        <p>
          <button type="submit" className="button button--primary" disabled={empty || tooLong || sending}>
            {sending ? t('writing.saving') : t('writing.submit')}
          </button>
        </p>
        <p className="muted field-hint">{t('writing.submitHint')}</p>
        {create.isError && <ErrorText error={create.error} />}
      </form>
    </div>
  )
}
