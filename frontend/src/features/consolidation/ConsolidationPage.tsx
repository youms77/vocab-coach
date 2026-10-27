import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'

import {
  type ConsolidationDeck,
  DEFAULT_TERMS,
  MAX_TERMS,
  MIN_TERMS,
  TASK_TYPES,
  type TaskStatus,
  type TaskType,
  TASKS_PAGE_SIZE,
  useConsolidationDecks,
  useConsolidationTasks,
  useCreateTask,
} from '../../api/consolidation'
import { ApiError } from '../../api/client'
import { PageTitle } from '../../components/PageTitle'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { formatShortDate } from '../session/format'
import { ErrorText } from '../settings/ErrorText'
import { inLanguage } from './text'

const STATUSES: TaskStatus[] = ['proposed', 'accepted', 'completed', 'dismissed']

function percent(value: number, language: string) {
  return new Intl.NumberFormat(language, { style: 'percent', maximumFractionDigits: 0 }).format(
    value,
  )
}

function ReadyDeck({ deck }: { deck: ConsolidationDeck }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const create = useCreateTask()
  const typeId = useId()
  const countId = useId()
  const [taskType, setTaskType] = useState<TaskType>('talk')
  const [count, setCount] = useState(String(Math.min(DEFAULT_TERMS, deck.candidates)))
  const waited = useElapsedSeconds(create.isPending, create.submittedAt)

  const max = Math.min(MAX_TERMS, deck.candidates)
  const number = Number(count)
  const valid = Number.isInteger(number) && number >= MIN_TERMS && number <= max
  const conflict = create.error instanceof ApiError ? create.error : null

  return (
    <li className="card consolidation-deck">
      <h3>{deck.name}</h3>
      <p className="muted">
        {t('consolidation.decks.readyLine', {
          ratio: percent(deck.ratio, i18n.language),
          threshold: percent(deck.threshold_ratio, i18n.language),
          days: deck.min_stability_days,
          count: deck.candidates,
        })}
      </p>
      <form
        className="consolidation-create"
        onSubmit={(event) => {
          event.preventDefault()
          if (!valid || create.isPending) return
          create.mutate(
            { deck_id: deck.deck_id, task_type: taskType, term_count: number },
            {
              onSuccess: (created) =>
                // The reason the AI did not make it (a template instead) is told on the task page.
                navigate(`/consolidation/tasks/${created.task.id}`, {
                  state: { templateReason: created.source === 'template' ? (created.reason ?? 'all_failed') : null },
                }),
            },
          )
        }}
      >
        <div className="field">
          <label htmlFor={typeId}>{t('consolidation.create.type')}</label>
          <select
            id={typeId}
            value={taskType}
            onChange={(event) => setTaskType(event.target.value as TaskType)}
          >
            {TASK_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`consolidation.types.${type}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor={countId}>{t('consolidation.create.count')}</label>
          <input
            id={countId}
            type="number"
            inputMode="numeric"
            min={MIN_TERMS}
            max={max}
            value={count}
            onChange={(event) => setCount(event.target.value)}
            aria-invalid={!valid || undefined}
          />
          <p className="muted field-hint">
            {t('consolidation.create.countHint', { min: MIN_TERMS, max })}
          </p>
        </div>
        <p>
          <button
            type="submit"
            className="button button--primary"
            disabled={!valid || create.isPending || create.isSuccess}
          >
            {create.isPending
              ? t('consolidation.create.making', { seconds: waited })
              : t('consolidation.create.submit')}
          </button>
        </p>
        <div role="status">
          {create.isPending && <p className="muted">{t('consolidation.create.wait')}</p>}
        </div>
        {conflict?.code === 'task_open' && (
          <p className="form-message form-message--warn" role="alert">
            {t('errors.task_open')}{' '}
            {typeof conflict.detail.task_id === 'number' && (
              <Link to={`/consolidation/tasks/${conflict.detail.task_id}`}>
                {t('consolidation.decks.openTask')}
              </Link>
            )}
          </p>
        )}
        {conflict?.code === 'not_ready' && (
          <p className="form-message form-message--warn" role="alert">
            {t('errors.not_ready')}{' '}
            {typeof conflict.detail.reason === 'string' &&
              t(`consolidation.reasons.${conflict.detail.reason}`, { defaultValue: '' })}
          </p>
        )}
        {create.isError && conflict?.code !== 'task_open' && conflict?.code !== 'not_ready' && (
          <ErrorText error={create.error} />
        )}
      </form>
    </li>
  )
}

function WaitingDeck({ deck }: { deck: ConsolidationDeck }) {
  const { t, i18n } = useTranslation()
  const reason = deck.reason ?? 'not_enough_candidates'
  return (
    <li>
      <strong>{deck.name}</strong>
      {' — '}
      {t(`consolidation.reasons.${reason}`, {
        ratio: percent(deck.ratio, i18n.language),
        threshold: percent(deck.threshold_ratio, i18n.language),
        days: deck.min_stability_days,
        count: deck.candidates,
      })}{' '}
      {reason === 'task_open' && deck.open_task_id !== null && (
        <Link to={`/consolidation/tasks/${deck.open_task_id}`}>
          {t('consolidation.decks.openTask')}
        </Link>
      )}
    </li>
  )
}

function Decks() {
  const { t } = useTranslation()
  const decks = useConsolidationDecks()
  const ready = decks.data?.filter((deck) => deck.ready) ?? []
  const waiting = decks.data?.filter((deck) => !deck.ready) ?? []
  return (
    <>
      <section aria-labelledby="consolidation-ready">
        <h2 id="consolidation-ready">{t('consolidation.decks.ready')}</h2>
        {decks.isPending && <p className="muted">{t('consolidation.loading')}</p>}
        {decks.isError && <ErrorText error={decks.error} />}
        {decks.isSuccess && ready.length === 0 && (
          <p className="muted">{t('consolidation.decks.noneReady')}</p>
        )}
        {ready.length > 0 && (
          <ul className="deck-list">
            {ready.map((deck) => (
              <ReadyDeck key={deck.deck_id} deck={deck} />
            ))}
          </ul>
        )}
      </section>
      {waiting.length > 0 && (
        <section className="card" aria-labelledby="consolidation-waiting">
          <h2 id="consolidation-waiting">{t('consolidation.decks.waiting')}</h2>
          <ul>
            {waiting.map((deck) => (
              <WaitingDeck key={deck.deck_id} deck={deck} />
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

function Tasks() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const requested = Number(params.get('page'))
  const page = Number.isInteger(requested) && requested > 1 ? requested - 1 : 0
  const rawStatus = params.get('status')
  const status = STATUSES.find((value) => value === rawStatus) ?? ''
  const tasks = useConsolidationTasks(page, status)
  const filterId = useId()
  const total = tasks.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / TASKS_PAGE_SIZE))

  const update = (next: { status?: string; page?: number }) => {
    const search = new URLSearchParams()
    const nextStatus = next.status ?? status
    if (nextStatus !== '') search.set('status', nextStatus)
    const nextPage = next.page ?? page
    if (nextPage > 0) search.set('page', String(nextPage + 1))
    setParams(search)
  }

  return (
    <section className="card" aria-labelledby="consolidation-tasks">
      <h2 id="consolidation-tasks">{t('consolidation.tasks.title')}</h2>
      <div className="field">
        <label htmlFor={filterId}>{t('consolidation.tasks.filter')}</label>
        <select
          id={filterId}
          value={status}
          onChange={(event) => update({ status: event.target.value, page: 0 })}
        >
          <option value="">{t('consolidation.tasks.all')}</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {t(`consolidation.status.${value}`)}
            </option>
          ))}
        </select>
      </div>
      {tasks.isPending && <p className="muted">{t('consolidation.loading')}</p>}
      {tasks.isError && <ErrorText error={tasks.error} />}
      {tasks.isSuccess && tasks.data.items.length === 0 && (
        <p className="muted">{t('consolidation.tasks.empty')}</p>
      )}
      {tasks.isSuccess && tasks.data.items.length > 0 && (
        <>
          <p className="muted" role="status">
            {t('consolidation.tasks.count', { count: total })}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t('consolidation.tasks.date')}</th>
                  <th scope="col">{t('consolidation.tasks.task')}</th>
                  <th scope="col">{t('consolidation.tasks.deck')}</th>
                  <th scope="col">{t('consolidation.tasks.statusColumn')}</th>
                </tr>
              </thead>
              <tbody>
                {tasks.data.items.map((task) => (
                  <tr key={task.id}>
                    <td>{formatShortDate(task.created_at, i18n.language)}</td>
                    <td>
                      <Link to={`/consolidation/tasks/${task.id}`}>
                        {inLanguage(task.title, i18n.language)}
                      </Link>
                    </td>
                    <td>{task.deck.name}</td>
                    <td>{t(`consolidation.status.${task.status}`)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <nav className="pager" aria-label={t('library.pager.label')}>
              <button
                type="button"
                className="button"
                disabled={page === 0}
                onClick={() => update({ page: page - 1 })}
              >
                {t('library.pager.previous')}
              </button>
              <span>{t('library.pager.page', { page: page + 1, pages })}</span>
              <button
                type="button"
                className="button"
                disabled={page + 1 >= pages}
                onClick={() => update({ page: page + 1 })}
              >
                {t('library.pager.next')}
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  )
}

/**
 * Module G: the decks that are consolidated enough for a talk, speech or interview answer (and
 * why the others are not yet), the creation of a task, and the tasks made so far.
 */
export function ConsolidationPage() {
  const { t } = useTranslation()
  return (
    <div className="consolidation-page">
      <section className="hero">
        <PageTitle>{t('consolidation.title')}</PageTitle>
        <p className="muted">{t('consolidation.intro')}</p>
      </section>
      <Decks />
      <Tasks />
    </div>
  )
}
