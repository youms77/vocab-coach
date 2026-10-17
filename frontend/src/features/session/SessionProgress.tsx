import { useTranslation } from 'react-i18next'

import type { Progress } from '../../api/session'
import { minutesOf } from './format'

/** Reviews and new terms done / left and the time left, from the latest `next` answer. */
export function SessionProgress({ progress }: { progress: Progress }) {
  const { t } = useTranslation()
  const done = progress.reviews_done + progress.new_done
  const total = done + progress.reviews_remaining + progress.new_remaining

  return (
    <section className="session-progress" aria-label={t('session.progress.label')}>
      <progress value={done} max={Math.max(total, 1)} aria-label={t('session.progress.bar', { done, total })} />
      <ul aria-live="polite">
        <li>
          {t('session.progress.reviews', {
            done: progress.reviews_done,
            remaining: progress.reviews_remaining,
          })}
        </li>
        <li>
          {t('session.progress.newItems', {
            done: progress.new_done,
            remaining: progress.new_remaining,
          })}
        </li>
        <li>
          {t('session.progress.time', { minutes: minutesOf(progress.estimated_seconds_remaining) })}
        </li>
      </ul>
    </section>
  )
}
