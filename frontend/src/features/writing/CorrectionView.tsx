import { type MouseEvent, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { categoryLabels, type ErrorOut, labelOf, useErrorCategories } from '../../api/errors'
import type { Feedback, ProductionTarget, ProposedCategory } from '../../api/productions'
import {
  type CorrectionModel,
  type ErrorEntry,
  readFeedback,
  type TargetEntry,
} from './correction'

type Level = 2 | 3

function Heading({ level, children, id }: { level: Level; children: string; id?: string }) {
  return level === 2 ? <h2 id={id}>{children}</h2> : <h3 id={id}>{children}</h3>
}

/** Moves the focus to an element of the view (anchors scroll, but do not move the focus). */
function goTo(id: string) {
  return (event: MouseEvent) => {
    event.preventDefault()
    const target = document.getElementById(id)
    if (target === null) return
    target.focus()
    target.scrollIntoView?.({ block: 'center' })
  }
}

function FrenchExplanation({ text }: { text: string }) {
  const { t } = useTranslation()
  const [shown, setShown] = useState(false)
  const id = useId()
  return (
    <div className="correction-french">
      <button
        type="button"
        className="button button--small"
        aria-expanded={shown}
        aria-controls={id}
        onClick={() => setShown(!shown)}
      >
        {shown ? t('correction.hideFrench') : t('correction.showFrench')}
      </button>
      {shown && (
        <p id={id} lang="fr">
          {text}
        </p>
      )}
    </div>
  )
}

function CategoryName({ code, label }: { code: string; label: string | null }) {
  return (
    <>
      {label !== null && <>{label} </>}
      <code className="category-code">{code}</code>
    </>
  )
}

function ErrorItem({
  entry,
  uid,
  markId,
  categoryLabel,
  term,
}: {
  entry: ErrorEntry
  uid: string
  markId: string | null
  categoryLabel: string | null
  term: { id: number; term: string } | null
}) {
  const { t } = useTranslation()
  return (
    <li id={`${uid}-error-${entry.number}`} tabIndex={-1} className="correction-error">
      <p className="correction-error__head">
        <strong className="correction-error__number">
          {t('correction.errorNumber', { n: entry.number })}
        </strong>
        {markId !== null && (
          <>
            {' '}
            <a href={`#${markId}`} onClick={goTo(markId)}>
              {t('correction.backToText')}
            </a>
          </>
        )}
      </p>
      <p lang="en" className="correction-change">
        <span className="visually-hidden">{t('correction.wrong')}: </span>
        <del className="correction-wrong">{entry.wrong}</del>
        <span aria-hidden="true"> → </span>
        <span className="visually-hidden">{t('correction.right')}: </span>
        <ins className="correction-right">{entry.correction}</ins>
      </p>
      {entry.alternatives.length > 0 && (
        <p>
          {t('correction.alternatives')}:{' '}
          <span lang="en">{entry.alternatives.join(' · ')}</span>
        </p>
      )}
      <p className="muted">
        {t('correction.category')}: <CategoryName code={entry.categoryCode} label={categoryLabel} />
      </p>
      <p lang="en">{entry.explanationEn}</p>
      {entry.explanationFr !== null && entry.explanationFr.trim() !== '' && (
        <FrenchExplanation text={entry.explanationFr} />
      )}
      {term !== null && (
        <p>
          {t('correction.term')}: <Link to={`/library/items/${term.id}`}>{term.term}</Link>
        </p>
      )}
    </li>
  )
}

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation()
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setState('copied')
    } catch {
      setState('failed')
    }
  }
  return (
    <>
      <button type="button" className="button button--small" onClick={() => void copy()}>
        {t('correction.copy')}
      </button>
      <span role="status" className="muted correction-copy-status">
        {state === 'copied' && t('correction.copied')}
        {state === 'failed' && t('correction.copyFailed')}
      </span>
    </>
  )
}

function Targets({ targets, level }: { targets: TargetEntry[]; level: Level }) {
  const { t } = useTranslation()
  if (targets.length === 0) return null
  const verdict = (target: TargetEntry) =>
    target.used !== true
      ? t('correction.targetNotUsed')
      : target.usedCorrectly === true
        ? t('correction.targetUsedCorrectly')
        : target.usedCorrectly === false
          ? t('correction.targetUsedWrong')
          : t('correction.targetUsed')
  return (
    <section className="correction-section">
      <Heading level={level}>{t('correction.targetsTitle')}</Heading>
      <ul>
        {targets.map((target) => (
          <li key={target.itemId}>
            <Link to={`/library/items/${target.itemId}`} lang="en">
              {target.term || `#${target.itemId}`}
            </Link>
            : {verdict(target)}
            {target.comment !== null && target.comment.trim() !== '' && (
              <>
                {' '}
                <span lang="en">{target.comment}</span>
              </>
            )}
            {target.disagreement && (
              <>
                {' '}
                <span className="muted">{t('correction.targetDisagreement')}</span>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Body({
  model,
  uid,
  level,
  compact,
  logged,
  targets,
}: {
  model: CorrectionModel
  uid: string
  level: Level
  compact: boolean
  logged: boolean
  targets: ProductionTarget[]
}) {
  const { t, i18n } = useTranslation()
  // The category tree gives labels for errors that are not logged rows (only needed then).
  const tree = useErrorCategories(!logged)
  const byCode = tree.data !== undefined ? categoryLabels(tree.data) : null
  const markOf = (index: number) => {
    const range = model.ranges.findIndex((r) => r.errors.includes(index))
    return range >= 0 ? `${uid}-mark-${range}` : null
  }
  // "Sentence n" for a text, "Your turn n" for a transcript.
  const unitName = (n: number) =>
    model.kind === 'transcript' ? t('correction.turn', { n }) : t('correction.sentence', { n })
  const labelFor = (entry: ErrorEntry) => {
    const category = entry.logged?.category ?? byCode?.get(entry.categoryCode)
    return category !== undefined ? labelOf(category, i18n.language) : null
  }
  const termFor = (entry: ErrorEntry) => {
    if (entry.logged?.term != null) return entry.logged.term
    if (entry.targetItemId === null) return null
    const known = targets.find((target) => target.lexical_item_id === entry.targetItemId)
    return { id: entry.targetItemId, term: known?.term ?? `#${entry.targetItemId}` }
  }

  return (
    <>
      {model.overall !== '' && (
        <section className="correction-section">
          <Heading level={level}>{t('correction.overall')}</Heading>
          <p lang="en">{model.overall}</p>
        </section>
      )}

      <section className="correction-section">
        <Heading level={level}>
          {model.kind === 'transcript' ? t('correction.yourTurns') : t('correction.yourText')}
        </Heading>
        {model.contextSent !== null && (
          <p className="muted">
            {model.contextSent ? t('correction.contextSent') : t('correction.contextNotSent')}
          </p>
        )}
        <p lang="en" className="correction-text">
          {model.segments.map((part, index) =>
            part.kind === 'text' ? (
              <span key={index}>{part.text}</span>
            ) : (
              <mark
                key={index}
                id={`${uid}-mark-${model.ranges.findIndex((r) => r.errors[0] === part.errors[0])}`}
                tabIndex={-1}
                className="correction-mark"
              >
                {part.text}
                <sup className="correction-mark__numbers">
                  {part.errors.map((error, i) => (
                    <span key={error}>
                      {i > 0 && ','}
                      <a
                        href={`#${uid}-error-${error + 1}`}
                        onClick={goTo(`${uid}-error-${error + 1}`)}
                        aria-label={t('correction.goToError', { n: error + 1 })}
                      >
                        {error + 1}
                      </a>
                    </span>
                  ))}
                </sup>
              </mark>
            ),
          )}
        </p>
        {model.entries.length === 0 && (
          <p className="form-message form-message--ok" role="status">
            {model.kind === 'transcript'
              ? t('correction.noErrorsTurns')
              : model.sentenceCount === 1
                ? t('correction.sentenceCorrect')
                : t('correction.noErrors')}
          </p>
        )}
      </section>

      {model.entries.length > 0 && (
        <section className="correction-section">
          <Heading level={level}>{t('correction.errorsTitle')}</Heading>
          {model.groups.map((group) => (
            <div key={group.number} className="correction-group">
              <p className="correction-group__title">
                <strong>{unitName(group.number)}</strong>
              </p>
              <ul className="correction-errors">
                {group.errors.map((entry) => (
                  <ErrorItem
                    key={entry.number}
                    entry={entry}
                    uid={uid}
                    markId={markOf(entry.number - 1)}
                    categoryLabel={labelFor(entry)}
                    term={termFor(entry)}
                  />
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      {model.notes.length > 0 && (
        <section className="correction-section">
          <Heading level={level}>{t('correction.naturalnessTitle')}</Heading>
          <p className="muted">{t('correction.naturalnessIntro')}</p>
          <ul className="correction-notes">
            {model.notes.map((note, index) => (
              <li key={index}>
                <strong>{unitName(model.numberOf(note.sentence_index))}</strong>:{' '}
                <span lang="en">“{note.text}”</span> · {t('correction.suggestion')}:{' '}
                <span lang="en">“{note.suggestion}”</span>
                {note.note.trim() !== '' && (
                  <>
                    {' '}
                    <span lang="en" className="muted">
                      {note.note}
                    </span>
                  </>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {model.correctedText !== '' && (
        <section className="correction-section">
          <Heading level={level}>{t('correction.correctedTitle')}</Heading>
          <p lang="en" className="correction-text">
            {model.correctedText}
          </p>
          {!compact && <CopyButton text={model.correctedText} />}
        </section>
      )}

      {!compact && model.naturalText !== null && model.naturalText.trim() !== '' && (
        <section className="correction-section">
          <Heading level={level}>{t('correction.naturalTitle')}</Heading>
          <p lang="en" className="correction-text">
            {model.naturalText}
          </p>
          <CopyButton text={model.naturalText} />
        </section>
      )}

      {!compact && <Targets targets={model.targets} level={level} />}
    </>
  )
}

/**
 * A stored correction: the original text with numbered, underlined marks, the errors grouped by
 * sentence, naturalness remarks, the corrected and the more natural versions. Marks are never
 * shown by colour alone (underline and a number). Reused by the transcript analysis in M5.c
 * through `readFeedback`, which is the only part that knows the stored format.
 *
 * `compact` (a review or a discovery sentence) leaves out the natural version, the copy buttons
 * and the target terms: the page around it already deals with the term.
 */
export function CorrectionView({
  text,
  feedback,
  errors,
  targets = [],
  proposedCategories = [],
  compact = false,
  level = 2,
}: {
  text: string
  feedback: Feedback | null
  /** The logged errors of this correction (labels, term and edited explanation). */
  errors?: ErrorOut[]
  targets?: ProductionTarget[]
  proposedCategories?: ProposedCategory[]
  compact?: boolean
  /** Heading level of the sections (2 on a page, 3 inside a step). */
  level?: Level
}) {
  const { t, i18n } = useTranslation()
  const uid = useId()
  const model = readFeedback({ text, feedback, errors, targets })

  if (model === null) {
    return (
      <div className="correction">
        <p lang="en" className="correction-text">
          {text}
        </p>
        <p className="muted" role="status">
          {t('correction.notCorrected')}
        </p>
      </div>
    )
  }

  return (
    <div className="correction">
      <Body
        model={model}
        uid={uid}
        level={level}
        compact={compact}
        logged={model.entries.every((entry) => entry.logged !== null)}
        targets={targets}
      />
      {proposedCategories.length > 0 && (
        <div className="form-message form-message--warn correction-proposed" role="status">
          <p>
            <strong>{t('correction.proposedTitle')}</strong>
          </p>
          <ul>
            {proposedCategories.map((category) => (
              <li key={category.id}>
                {t('correction.proposedBody', {
                  label: labelOf(category, i18n.language),
                  code: category.code,
                })}
              </li>
            ))}
          </ul>
          <p>
            <Link to="/errors/categories">{t('correction.proposedLink')}</Link>
          </p>
        </div>
      )}
    </div>
  )
}
