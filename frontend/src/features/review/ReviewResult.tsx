import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { GradeResult as Result, SheetSummary } from '../../api/reviews'
import type { ReviewStep } from '../../api/session'
import { SpeakButton } from '../../speech/SpeakButton'
import { GradeResult } from '../discovery/GradeResult'
import { describeError } from '../settings/errorMessage'
import { aiReasonText } from '../settings/aiReason'
import { CorrectionView } from '../writing/CorrectionView'
import type { CheckNotice, ProductionCheck, SpokenCheck } from './reviewMachine'
import { text } from './stepText'

const CHOICE_TYPES = ['recognition_in_sentence', 'listening_comprehension']

function Summary({ summary, itemId }: { summary: SheetSummary; itemId: number }) {
  const { t } = useTranslation()
  const pronunciation = summary.pronunciation
  return (
    <section className="review-summary" aria-label={t('review.summary.label', { term: summary.term })}>
      <p className="review-term">
        <strong lang="en">{summary.term}</strong>
        {summary.part_of_speech !== null && <span className="muted"> · {summary.part_of_speech}</span>}
        {pronunciation?.ipa_us != null && <span lang="en"> · {pronunciation.ipa_us}</span>}{' '}
        <SpeakButton text={summary.term} label={t('review.termLabel')} />
      </p>
      {pronunciation?.stressed_syllable != null && (
        <p className="muted">{t('review.summary.stress', { syllable: pronunciation.stressed_syllable })}</p>
      )}
      {summary.definition_simple !== null && <p>{summary.definition_simple}</p>}
      {summary.translation_fr.length > 0 && (
        <p lang="fr">{t('review.cueFr', { cue: summary.translation_fr.join(', ') })}</p>
      )}
      {summary.examples.length > 0 && (
        <ul className="review-summary__examples">
          {summary.examples.map((example) => (
            <li key={example}>
              <span lang="en">{example}</span>{' '}
              <SpeakButton text={example} label={t('sheet.exampleLabel')} />
            </li>
          ))}
        </ul>
      )}
      <p>
        <Link to={`/library/items/${itemId}`} target="_blank" rel="noopener">
          {t('review.summary.fullSheet')}
        </Link>
      </p>
    </section>
  )
}

function NoticeText({ notice }: { notice: CheckNotice }) {
  const { t } = useTranslation()
  let message: string
  switch (notice.kind) {
    case 'unavailable':
      message = t('review.aiCheck.notice.unavailable', { reason: aiReasonText(t, notice.reason) })
      break
    case 'incomplete':
      message = t('review.aiCheck.notice.incomplete')
      break
    case 'skipped':
      message = t('review.aiCheck.notice.skipped')
      break
    case 'failed':
      message = t('review.aiCheck.notice.failed', { error: describeError(t, notice.error).text })
      break
    case 'spoken_skipped':
      message = t('review.spoken.notice.skipped')
      break
    case 'spoken_failed':
      message = t('review.spoken.notice.failed', { error: describeError(t, notice.error).text })
      break
  }
  return <p className="form-message form-message--warn">{message}</p>
}

/** What the recogniser heard, then the AI's correction of it (or why there is none). */
function SpokenCheckView({ spoken, result }: { spoken: SpokenCheck; result: Result }) {
  const { t } = useTranslation()
  const { transcription } = spoken
  const heard = text(transcription.text)
  if (transcription.status === 'silence' || spoken.reason === 'silence') {
    return <p className="form-message form-message--warn">{t('review.spoken.silence')}</p>
  }
  if (transcription.status !== 'ok' || heard === null) {
    return (
      <p className="form-message form-message--warn">
        {t('review.spoken.unavailable', { reason: aiReasonText(t, transcription.reason) })}
      </p>
    )
  }
  return (
    <div className="review-check">
      {/* The correction view titles the text as what the recognition heard. */}
      <CorrectionView
        compact
        level={3}
        text={heard}
        feedback={spoken.status === 'ok' ? spoken.feedback : null}
        errors={spoken.errors}
      />
      {spoken.status !== 'ok' && (
        <p className="form-message form-message--warn">
          {t('review.spoken.correctionFailed', { reason: aiReasonText(t, spoken.reason) })}
        </p>
      )}
      {result.warnings.includes('term_not_heard') && (
        <p className="form-message form-message--warn">{t('review.result.term_not_heard')}</p>
      )}
    </div>
  )
}

/**
 * The correction, shown only after `grade`, `reveal` or the AI check: the outcome (a sign and a text), then the
 * solution of the exercise type and the summary of the sheet.
 */
export function ReviewResult({
  review,
  result,
  answer,
  check = null,
  spoken = null,
  notice = null,
}: {
  review: ReviewStep
  result: Result
  answer: string
  /** The AI's correction of the typed sentence (sentence production, status ok). */
  check?: ProductionCheck | null
  /** What was heard of the spoken answer and how it was checked (status of `review-answer`). */
  spoken?: SpokenCheck | null
  /** Why the AI check was not used, when the sentence was self-graded instead. */
  notice?: CheckNotice | null
}) {
  const { t } = useTranslation()
  const solution = result.solution
  const sentence = text(solution.sentence)
  const type = review.exercise_type

  let body
  if (CHOICE_TYPES.includes(type)) {
    body = (
      <>
        <GradeResult result={{ ...result, expected: null }} />
        {text(solution.meaning) !== null && (
          <p>{t('review.result.meaning', { meaning: solution.meaning })}</p>
        )}
        {text(solution.meaning_fr) !== null && (
          <p lang="fr">{t('review.cueFr', { cue: solution.meaning_fr })}</p>
        )}
        {sentence !== null && (
          <p>
            {type === 'listening_comprehension'
              ? t('review.result.heard')
              : t('review.result.sentence')}{' '}
            <span lang="en" className="review-sentence-inline">
              {sentence}
            </span>{' '}
            <SpeakButton text={sentence} label={t('review.sentenceLabel')} />
          </p>
        )}
      </>
    )
  } else if (type === 'typed_recall' || type === 'gap_fill') {
    body = (
      <>
        <GradeResult result={result} />
        {type === 'gap_fill' && sentence !== null && (
          <p>
            {t('review.result.sentence')}{' '}
            <span lang="en" className="review-sentence-inline">
              {sentence}
            </span>{' '}
            <SpeakButton text={sentence} label={t('review.sentenceLabel')} />
          </p>
        )}
      </>
    )
  } else if (type === 'sentence_production' || type === 'spoken_answer') {
    const example = text(solution.example_answer)
    body = (
      <div className="grade-result" role="status">
        {notice !== null && <NoticeText notice={notice} />}
        {type === 'sentence_production' && answer.trim() === '' && (
          <p className="muted">{t('review.result.noSentence')}</p>
        )}
        {result.warnings.includes('term_missing') && (
          <p className="form-message form-message--warn">{t('review.result.term_missing')}</p>
        )}
        {spoken !== null && <SpokenCheckView spoken={spoken} result={result} />}
        {check !== null && (
          <div className="review-check">
            <h3>{t('review.aiCheck.found')}</h3>
            <CorrectionView
              compact
              level={3}
              text={answer}
              feedback={check.feedback}
              errors={check.errors}
            />
          </div>
        )}
        {example !== null && (
          <p>
            {t('review.result.example')}{' '}
            <span lang="en" className="review-sentence-inline">
              {example}
            </span>{' '}
            <SpeakButton text={example} label={t('review.result.exampleLabel')} />
          </p>
        )}
        {(type === 'sentence_production' || result.proposed_rating === null) && (
          <p className="muted">{t('review.result.compare')}</p>
        )}
      </div>
    )
  } else {
    // self_assessment: the meaning; a productive card also reveals the term and the full
    // sentence (a receptive one already showed both in its prompt).
    const productive = review.direction === 'productive'
    const term = productive ? text(solution.term) : null
    body = (
      <div className="grade-result" role="status">
        {term !== null && (
          <p className="review-term">
            {t('review.result.answerIs')} <strong lang="en">{term}</strong>{' '}
            <SpeakButton text={term} label={t('review.termLabel')} />
          </p>
        )}
        {text(solution.definition_simple) !== null && <p>{solution.definition_simple}</p>}
        {(solution.translation_fr ?? []).length > 0 && (
          <p lang="fr">{t('review.cueFr', { cue: (solution.translation_fr ?? []).join(', ') })}</p>
        )}
        {productive && sentence !== null && (
          <p>
            <span lang="en" className="review-sentence-inline">
              {sentence}
            </span>{' '}
            <SpeakButton text={sentence} label={t('review.sentenceLabel')} />
          </p>
        )}
        <p className="muted">{t('review.result.compare')}</p>
      </div>
    )
  }

  return (
    <>
      {body}
      {result.sheet_summary !== null && (
        <Summary summary={result.sheet_summary} itemId={review.lexical_item_id} />
      )}
    </>
  )
}
