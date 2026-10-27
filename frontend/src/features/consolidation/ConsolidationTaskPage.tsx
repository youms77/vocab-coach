import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams } from 'react-router'

import { ApiError, apiDownload } from '../../api/client'
import {
  type ConsolidationTask,
  MAX_WRITTEN_CHARS,
  type TaskStatus,
  useConsolidationTask,
  useSpokenAttempt,
  useTaskStatus,
  useWrittenAttempt,
} from '../../api/consolidation'
import { PageTitle } from '../../components/PageTitle'
import { Recorder } from '../../speech/RecorderPanel'
import { formatDateTime } from '../session/format'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { countText } from '../writing/draft'
import { inLanguage, loadTaskDraft, otherLanguage, saveTaskDraft } from './text'

type NextStatus = Exclude<TaskStatus, 'proposed'>
type Confirmed = 'completed' | 'dismissed'

/** The moves the backend allows (`TRANSITIONS`, app/domain/consolidation.py). */
const MOVES: Record<TaskStatus, NextStatus[]> = {
  proposed: ['accepted', 'dismissed'],
  accepted: ['completed', 'dismissed'],
  completed: [],
  dismissed: [],
}

const isOpen = (task: ConsolidationTask) => task.status === 'proposed' || task.status === 'accepted'

/** The text in the interface language; with `both`, the other language follows it, muted. */
function Bilingual({ text, both }: { text: { en: string; fr: string }; both: boolean }) {
  const { i18n } = useTranslation()
  const lang = i18n.language.startsWith('fr') ? 'fr' : 'en'
  const other = otherLanguage(i18n.language)
  return (
    <>
      <span lang={lang}>{text[lang]}</span>
      {both && (
        <>
          <br />
          <span lang={other} className="muted">
            {text[other]}
          </span>
        </>
      )}
    </>
  )
}

function StatusActions({ task }: { task: ConsolidationTask }) {
  const { t } = useTranslation()
  const change = useTaskStatus(task.id)
  const [asking, setAsking] = useState<Confirmed | null>(null)
  const moves = MOVES[task.status]
  if (moves.length === 0) return <p className="muted">{t(`consolidation.task.final.${task.status as Confirmed}`)}</p>

  const confirm = (to: NextStatus) => {
    change.mutate(to, { onSettled: () => setAsking(null) })
  }
  return (
    <div>
      <p className="today-actions">
        {moves.map((to) => (
          <button
            key={to}
            type="button"
            className={`button${to === 'accepted' ? ' button--primary' : ''}`}
            disabled={change.isPending}
            onClick={() => (to === 'accepted' ? confirm(to) : setAsking(to))}
          >
            {t(`consolidation.task.actions.${to}`)}
          </button>
        ))}
      </p>
      {asking !== null && (
        <div className="form-message form-message--warn" role="alertdialog" aria-label={t('consolidation.task.confirmLabel')}>
          <p>{t(`consolidation.task.confirm.${asking}`)}</p>
          <p className="today-actions">
            <button
              type="button"
              className="button button--primary"
              disabled={change.isPending}
              onClick={() => confirm(asking)}
            >
              {t(`consolidation.task.actions.${asking}Yes`)}
            </button>
            <button type="button" className="button" onClick={() => setAsking(null)}>
              {t('consolidation.task.cancel')}
            </button>
          </p>
        </div>
      )}
      {change.isError && <ErrorText error={change.error} />}
    </div>
  )
}

function ExportButtons({ task }: { task: ConsolidationTask }) {
  const { t } = useTranslation()
  const [failure, setFailure] = useState<unknown>(null)
  const download = (lang: 'en' | 'fr') => {
    setFailure(null)
    apiDownload(
      `/consolidation/tasks/${task.id}/export?lang=${lang}`,
      `consolidation-task-${task.id}-${lang}.md`,
    ).catch((error: unknown) => setFailure(error))
  }
  return (
    <section className="card" aria-labelledby="task-export">
      <h2 id="task-export">{t('consolidation.export.title')}</h2>
      <p className="muted">{t('consolidation.export.intro')}</p>
      <p className="today-actions">
        <button type="button" className="button" onClick={() => download('en')}>
          {t('consolidation.export.en')}
        </button>
        <button type="button" className="button" onClick={() => download('fr')}>
          {t('consolidation.export.fr')}
        </button>
      </p>
      {failure !== null && <ErrorText error={failure} />}
    </section>
  )
}

function WrittenForm({ task }: { task: ConsolidationTask }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const attempt = useWrittenAttempt(task.id)
  const [text, setText] = useState(() => loadTaskDraft(task.id))
  const fieldId = useId()
  const countId = useId()
  const { words, chars } = countText(text)
  const tooLong = chars > MAX_WRITTEN_CHARS
  const empty = text.trim() === ''
  const sending = attempt.isPending || attempt.isSuccess

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (empty || tooLong || sending) return
        attempt.mutate(text, {
          onSuccess: (created) => {
            saveTaskDraft(task.id, '')
            navigate(`/consolidation/attempts/${created.id}?task=${task.id}`, {
              replace: true,
              state: { autoCorrect: true },
            })
          },
        })
      }}
    >
      <div className="field">
        <label htmlFor={fieldId}>{t('consolidation.write.label')}</label>
        <textarea
          id={fieldId}
          lang="en"
          rows={12}
          value={text}
          onChange={(event) => {
            setText(event.target.value)
            saveTaskDraft(task.id, event.target.value)
          }}
          readOnly={sending}
          aria-describedby={countId}
          aria-invalid={tooLong}
        />
        <p id={countId} className={`field-hint${tooLong ? ' field-hint--error' : ''}`}>
          {t('writing.text.words', { count: words })} ·{' '}
          {t('writing.text.chars', { chars, max: MAX_WRITTEN_CHARS })}
        </p>
        {tooLong && (
          <p className="form-message form-message--error" role="alert">
            {t('writing.text.tooLong', { chars, max: MAX_WRITTEN_CHARS })}
          </p>
        )}
      </div>
      <p>
        <button type="submit" className="button button--primary" disabled={empty || tooLong || sending}>
          {sending ? t('consolidation.write.saving') : t('consolidation.write.submit')}
        </button>
      </p>
      <p className="muted field-hint">{t('consolidation.write.hint')}</p>
      {attempt.isError && <ErrorText error={attempt.error} />}
    </form>
  )
}

function SpokenForm({ task }: { task: ConsolidationTask }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const attempt = useSpokenAttempt(task.id)
  const sending = attempt.isPending || attempt.isSuccess
  return (
    <div>
      <Recorder
        use="consolidation"
        sending={sending}
        sendingLabel={t('consolidation.speak.sending')}
        onSend={(clip) =>
          attempt.mutate(
            { blob: clip.blob, durationS: clip.durationS },
            {
              onSuccess: (result) => {
                const unavailable =
                  result.transcription.status === 'unavailable'
                    ? { unavailableReason: result.transcription.reason ?? 'all_failed' }
                    : {}
                navigate(`/consolidation/attempts/${result.production_id}?task=${task.id}`, {
                  replace: true,
                  state: { autoCorrect: true, ...unavailable },
                })
              },
            },
          )
        }
      />
      {attempt.isError && <ErrorText error={attempt.error} />}
      <p className="muted field-hint">{t('consolidation.speak.hint')}</p>
      <p className="muted field-hint">{t('speaking.privacy')}</p>
    </div>
  )
}

function Production({ task }: { task: ConsolidationTask }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'written' | 'spoken'>('written')
  return (
    <section className="card" aria-labelledby="task-produce">
      <h2 id="task-produce">{t('consolidation.produce.title')}</h2>
      <p className="muted">{t('consolidation.produce.intro')}</p>
      <div role="group" aria-label={t('consolidation.produce.mode')} className="today-actions">
        {(['written', 'spoken'] as const).map((value) => (
          <button
            key={value}
            type="button"
            className={`button${mode === value ? ' button--primary' : ''}`}
            aria-pressed={mode === value}
            onClick={() => setMode(value)}
          >
            {t(`consolidation.produce.${value}`)}
          </button>
        ))}
      </div>
      {mode === 'written' ? <WrittenForm task={task} /> : <SpokenForm task={task} />}
    </section>
  )
}

function TaskView({ task }: { task: ConsolidationTask }) {
  const { t, i18n } = useTranslation()
  const location = useLocation()
  const [both, setBoth] = useState(false)
  const state = location.state as { templateReason?: string | null } | null
  const templateReason = typeof state?.templateReason === 'string' ? state.templateReason : null
  const other = otherLanguage(i18n.language)
  const termOf = new Map(task.targets.map((target) => [target.item_id, target.term]))
  return (
    <div className="consolidation-page">
      <section className="hero">
        <PageTitle>{inLanguage(task.title, i18n.language)}</PageTitle>
        <p className="muted">
          {task.deck.name} · {t(`consolidation.types.${task.task_type}`)} ·{' '}
          {t('consolidation.task.minutes', { count: task.target_minutes })}
          <span className="badge">{t(`consolidation.status.${task.status}`)}</span>
          <span className="badge">{t(`consolidation.source.${task.source}`)}</span>
        </p>
        {task.source === 'template' && (
          <p className="form-message form-message--warn">
            {t('consolidation.task.templateNote')}{' '}
            {templateReason !== null && t('consolidation.task.templateReason', { reason: aiReasonText(t, templateReason) })}
          </p>
        )}
        <p className="link-row">
          <Link to="/consolidation">{t('consolidation.task.all')}</Link>
        </p>
      </section>

      <section className="card" aria-labelledby="task-brief">
        <h2 id="task-brief">{t('consolidation.task.brief')}</h2>
        <p>
          <button
            type="button"
            className="button"
            aria-pressed={both}
            onClick={() => setBoth(!both)}
          >
            {t(both ? 'consolidation.task.hideOther' : 'consolidation.task.showOther', {
              language: t(`consolidation.languages.${other}`),
            })}
          </button>
        </p>
        <p className="consolidation-prompt">
          <Bilingual text={task.prompt} both={both} />
        </p>
        <p>
          <strong>{t('consolidation.task.audience')}</strong>{' '}
          <Bilingual text={task.audience} both={both} />
        </p>
        <h3>{t('consolidation.task.structure')}</h3>
        <ol>
          {task.sections.map((section, index) => (
            <li key={index}>
              <strong>
                <Bilingual text={section.heading} both={both} />
              </strong>
              <br />
              <Bilingual text={section.guidance} both={both} />
              {section.item_ids.length > 0 && (
                <span className="muted">
                  {' '}
                  (
                  {section.item_ids
                    .map((id) => termOf.get(id))
                    .filter((term) => term !== undefined)
                    .join(', ')}
                  )
                </span>
              )}
            </li>
          ))}
        </ol>
        <h3>{t('consolidation.task.terms')}</h3>
        <ul className="consolidation-terms">
          {task.targets.map((target) => (
            <li key={target.item_id}>
              <Link to={`/library/items/${target.item_id}`} lang="en">
                {target.term}
              </Link>
              <span className="badge">{t(`library.status.${target.item_status as 'active'}`, { defaultValue: target.item_status })}</span>
            </li>
          ))}
        </ul>
        <StatusActions task={task} />
      </section>

      {isOpen(task) && <Production task={task} />}

      <section className="card" aria-labelledby="task-attempts">
        <h2 id="task-attempts">{t('consolidation.attempts.title')}</h2>
        {task.attempts.length === 0 ? (
          <p className="muted">{t('consolidation.attempts.none')}</p>
        ) : (
          <ul>
            {task.attempts.map((attempt) => (
              <li key={attempt.production_id}>
                <Link to={`/consolidation/attempts/${attempt.production_id}?task=${task.id}`}>
                  {formatDateTime(attempt.created_at, i18n.language)}
                </Link>{' '}
                · {t(attempt.modality === 'oral' ? 'consolidation.attempts.oral' : 'consolidation.attempts.written')}{' '}
                ·{' '}
                {attempt.corrected
                  ? t('consolidation.attempts.corrected')
                  : t('consolidation.attempts.notCorrected')}
              </li>
            ))}
          </ul>
        )}
      </section>

      <ExportButtons task={task} />
    </div>
  )
}

export function ConsolidationTaskPage() {
  const { t } = useTranslation()
  const id = Number(useParams().id)
  const valid = Number.isInteger(id) && id > 0
  const query = useConsolidationTask(valid ? id : 0)
  const missing =
    !valid || (query.error instanceof ApiError && query.error.status === 404)

  if (missing) {
    return (
      <div className="consolidation-page">
        <PageTitle>{t('consolidation.task.title')}</PageTitle>
        <p className="form-message form-message--error" role="alert">
          {t('errors.task_not_found')}
        </p>
        <p>
          <Link to="/consolidation">{t('consolidation.task.all')}</Link>
        </p>
      </div>
    )
  }
  if (query.isPending) return <p className="muted">{t('consolidation.loading')}</p>
  if (query.isError) return <ErrorText error={query.error} />
  // Keyed by the task: moving to another one starts the page afresh (draft, recorder, mutations).
  return <TaskView key={query.data.id} task={query.data} />
}
