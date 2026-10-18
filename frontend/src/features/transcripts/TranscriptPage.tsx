import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

import { useToday } from '../../api/session'
import { CONTEXT_CHARS, codePoints, MAX_TITLE_CHARS, useCreateTranscript } from '../../api/transcripts'
import { PageTitle } from '../../components/PageTitle'
import { localDay } from '../queue/queueOrder'
import { ErrorText } from '../settings/ErrorText'
import { remember } from './transcriptMemory'
import { TranscriptInputForm } from './TranscriptInputForm'
import { useTranscriptInput } from './useTranscriptInput'

/**
 * Paste a conversation, say which turns are yours, then "Save and analyse". The server keeps your
 * turns only; the whole paste stays in memory (`transcriptMemory`) just long enough for the
 * analysis page to send it again as context. No draft is stored anywhere (D-151).
 */
export function TranscriptPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const create = useCreateTranscript()
  const input = useTranscriptInput()
  const [title, setTitle] = useState('')
  const [day, setDay] = useState('')
  const titleId = useId()
  const dayId = useId()
  const today = useToday()

  // The server refuses a date after the *study* day (timezone and day start), not the browser's
  // calendar day: the plan knows it; the local day only stands in while it loads (D-151).
  const maxDay = today.data?.plan.study_day ?? localDay()
  const titleChars = codePoints(title)
  const titleTooLong = titleChars > MAX_TITLE_CHARS
  const future = day !== '' && day > maxDay
  const sending = create.isPending || create.isSuccess
  const canSave = input.ready && !titleTooLong && !future && !sending

  function save() {
    if (!canSave || input.user === null) return
    const body = { text: input.text, user: input.user }
    create.mutate(
      {
        ...body,
        title: title.trim() === '' ? null : title.trim(),
        occurred_on: day === '' ? null : day,
        study_session_id: null,
      },
      {
        onSuccess: (created) => {
          remember(created.id, body)
          // Only the flag goes in the router state, which is written to `history.state`.
          navigate(`/transcripts/${created.id}`, { replace: true, state: { autoAnalyse: true } })
        },
      },
    )
  }

  return (
    <div className="transcript-page">
      <section className="hero">
        <PageTitle>{t('transcripts.title')}</PageTitle>
        <p className="muted">{t('transcripts.intro')}</p>
        <p className="link-row">
          <Link to="/transcripts/history">{t('transcripts.historyLink')}</Link>
          <Link to="/writing">{t('transcripts.writingLink')}</Link>
        </p>
      </section>

      <form
        className="card transcript-form"
        onSubmit={(event) => {
          event.preventDefault()
          save()
        }}
      >
        <TranscriptInputForm input={input} readOnly={sending} />

        <fieldset className="transcript-meta">
          <legend>{t('transcripts.meta.title')}</legend>
          <div className="field">
            <label htmlFor={titleId}>{t('transcripts.meta.titleLabel')}</label>
            <input
              id={titleId}
              type="text"
              lang="en"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              aria-invalid={titleTooLong}
            />
            <p className={`field-hint${titleTooLong ? ' field-hint--error' : ''}`}>
              {t('transcripts.meta.titleChars', { chars: titleChars, max: MAX_TITLE_CHARS })}
            </p>
          </div>
          <div className="field">
            <label htmlFor={dayId}>{t('transcripts.meta.date')}</label>
            <input
              id={dayId}
              type="date"
              value={day}
              max={maxDay}
              onChange={(event) => setDay(event.target.value)}
              aria-invalid={future}
            />
            <p className={`field-hint${future ? ' field-hint--error' : ''}`}>
              {future ? t('transcripts.meta.dateFuture') : t('transcripts.meta.dateHint')}
            </p>
          </div>
        </fieldset>

        <section className="form-message form-message--warn transcript-privacy" aria-labelledby="privacy-title">
          <p id="privacy-title">
            <strong>{t('transcripts.privacy.title')}</strong>
          </p>
          <p>{t('transcripts.privacy.body', { chars: CONTEXT_CHARS })}</p>
        </section>

        <p>
          <button type="submit" className="button button--primary" disabled={!canSave}>
            {sending ? t('transcripts.saving') : t('transcripts.save')}
          </button>
        </p>
        {!input.ready && <p className="muted field-hint">{t('transcripts.saveHint')}</p>}
        {create.isError && <ErrorText error={create.error} />}
      </form>
    </div>
  )
}
