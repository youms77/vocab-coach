import { useId } from 'react'
import { useTranslation } from 'react-i18next'

import { RATINGS, type Rating } from '../../api/reviews'

const RATING_NAMES = { 1: 'again', 2: 'hard', 3: 'good', 4: 'easy' } as const

/**
 * Again / Hard / Good / Easy with their key. The proposed rating (1 to 3: Easy is never proposed,
 * D-102) carries a "Suggested" text, not only a colour; self-graded types get four neutral buttons.
 */
export function RatingButtons({
  proposed,
  selfGraded,
  pending,
  onRate,
}: {
  proposed: Rating | null
  selfGraded: boolean
  pending: Rating | null
  onRate: (rating: Rating) => void
}) {
  const { t } = useTranslation()
  const titleId = useId()
  return (
    <div className="rating-block">
      <p id={titleId} className="rating-block__title">
        {t('review.rate.title')}
      </p>
      <p className="muted">
        {proposed !== null
          ? t('review.rate.proposed', { rating: t(`review.rate.${RATING_NAMES[proposed]}`) })
          : selfGraded
            ? t('review.rate.selfGraded')
            : t('review.rate.choose')}
      </p>
      <div role="group" aria-labelledby={titleId} className="rating">
        {RATINGS.map((rating) => {
          const suggested = rating === proposed
          return (
            <button
              key={rating}
              type="button"
              className={`button rating__button rating__button--${RATING_NAMES[rating]}${suggested ? ' rating__button--suggested' : ''}`}
              onClick={() => onRate(rating)}
              disabled={pending !== null}
            >
              <kbd>{rating}</kbd> {t(`review.rate.${RATING_NAMES[rating]}`)}
              {suggested && (
                <>
                  {' '}
                  <span className="badge rating__badge">{t('review.rate.suggested')}</span>
                </>
              )}
              {pending === rating && <span className="visually-hidden"> {t('review.saving')}</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
