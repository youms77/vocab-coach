import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { useExercises, usePatchExercise, type Exercise } from '../../api/enrichment'
import { ErrorText } from '../settings/ErrorText'
import { FieldErrors } from './FieldErrors'
import { Notice } from '../../components/Notice'

type FieldName =
  | 'sentence'
  | 'answer'
  | 'accepted'
  | 'cue_fr'
  | 'cue_definition'
  | 'meaning'
  | 'meaning_fr'
  | 'distractors'
  | 'situation'
  | 'question'
  | 'example_answer'

// `list`: one entry per line; `optional`: an empty text is sent as null.
interface FieldDef {
  name: FieldName
  kind: 'text' | 'long' | 'list'
  optional?: boolean
}

const RECOGNITION: FieldDef[] = [
  { name: 'sentence', kind: 'long' },
  { name: 'meaning', kind: 'long' },
  { name: 'meaning_fr', kind: 'long' },
  { name: 'distractors', kind: 'list' },
]

// The content shapes of backend/app/domain/exercises.py.
const FIELDS: Record<string, FieldDef[]> = {
  gap_fill: [
    { name: 'sentence', kind: 'long' },
    { name: 'answer', kind: 'text' },
    { name: 'accepted', kind: 'list' },
  ],
  typed_recall: [
    { name: 'cue_fr', kind: 'text', optional: true },
    { name: 'cue_definition', kind: 'long', optional: true },
    { name: 'answer', kind: 'text' },
    { name: 'accepted', kind: 'list' },
  ],
  recognition_in_sentence: RECOGNITION,
  listening_comprehension: RECOGNITION,
  sentence_production: [
    { name: 'situation', kind: 'long' },
    { name: 'example_answer', kind: 'long' },
  ],
  spoken_answer: [
    { name: 'question', kind: 'long' },
    { name: 'example_answer', kind: 'long' },
  ],
}

const KNOWN_TYPES = [
  'gap_fill',
  'typed_recall',
  'recognition_in_sentence',
  'listening_comprehension',
  'sentence_production',
  'spoken_answer',
] as const
type KnownType = (typeof KNOWN_TYPES)[number]

const isKnown = (type: string): type is KnownType => (KNOWN_TYPES as readonly string[]).includes(type)

const GAP = '___'

function toText(value: unknown, kind: FieldDef['kind']): string {
  if (kind === 'list') return Array.isArray(value) ? value.map(String).join('\n') : ''
  return typeof value === 'string' ? value : ''
}

function fromText(value: string, field: FieldDef): unknown {
  if (field.kind === 'list') {
    return value
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line !== '')
  }
  const trimmed = value.trim()
  return field.optional && trimmed === '' ? null : trimmed
}

function ExerciseForm({ exercise, onDone }: { exercise: Exercise; onDone: () => void }) {
  const { t } = useTranslation()
  const id = useId()
  const patch = usePatchExercise(exercise)
  const fields = FIELDS[exercise.exercise_type]
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.name, toText(exercise.content[f.name], f.kind)])),
  )
  const gapCount = exercise.exercise_type === 'gap_fill' ? values.sentence.split(GAP).length - 1 : 1

  function submit(event: FormEvent) {
    event.preventDefault()
    // The whole content is sent: the backend validates it for its type (422 invalid_exercise).
    const content = Object.fromEntries(fields.map((f) => [f.name, fromText(values[f.name], f)]))
    patch.mutate(content, { onSuccess: onDone })
  }

  return (
    <form className="library-form" onSubmit={submit}>
      {fields.map((field) => {
        const inputId = `${id}-${field.name}`
        const value = values[field.name]
        const onChange = (next: string) => setValues((v) => ({ ...v, [field.name]: next }))
        return (
          <div className="field" key={field.name}>
            <label htmlFor={inputId}>{t(`exercises.fields.${field.name}`)}</label>
            {field.kind === 'text' ? (
              <input
                id={inputId}
                type="text"
                value={value}
                onChange={(e) => onChange(e.target.value)}
              />
            ) : (
              <textarea
                id={inputId}
                rows={field.kind === 'list' ? 3 : 2}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                aria-describedby={field.kind === 'list' ? `${inputId}-hint` : undefined}
              />
            )}
            {field.kind === 'list' && (
              <p className="field-hint" id={`${inputId}-hint`}>
                {field.name === 'distractors'
                  ? t('exercises.distractorsHint')
                  : t('exercises.listHint')}
              </p>
            )}
          </div>
        )
      })}
      {gapCount !== 1 && (
        <Notice tone="warning" role="status">
          {t('exercises.gapHint', { gap: GAP })}
        </Notice>
      )}
      <div className="confirm">
        <button type="submit" className="button button--primary" disabled={patch.isPending}>
          {t('library.save')}
        </button>
        <button type="button" className="button" onClick={onDone}>
          {t('library.cancel')}
        </button>
      </div>
      {patch.isError && <ErrorText error={patch.error} />}
      {patch.isError && <FieldErrors error={patch.error} />}
    </form>
  )
}

function ExerciseContent({ exercise }: { exercise: Exercise }) {
  const { t } = useTranslation()
  const fields = FIELDS[exercise.exercise_type]
  return (
    <dl className="sheet-view">
      {fields.map((field) => {
        const value = exercise.content[field.name]
        if (value === null || value === undefined || (Array.isArray(value) && value.length === 0)) {
          return null
        }
        return (
          <div className="sheet-entry" key={field.name}>
            <dt>{t(`exercises.fields.${field.name}`)}</dt>
            <dd>{Array.isArray(value) ? value.map(String).join(' · ') : String(value)}</dd>
          </div>
        )
      })}
    </dl>
  )
}

function ExerciseBlock({ exercise }: { exercise: Exercise }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)
  const type = exercise.exercise_type
  const known = isKnown(type)
  const label = isKnown(type) ? t(`exercises.types.${type}`) : type

  return (
    <li className="exercise" aria-label={label}>
      <h4>
        {label}{' '}
        {exercise.direction === 'productive' || exercise.direction === 'receptive' ? (
          <span className="muted">· {t(`exercises.direction.${exercise.direction}`)}</span>
        ) : null}
        {exercise.edited_by_user && <span className="badge">{t('exercises.edited')}</span>}
      </h4>
      {!known && (
        <>
          <p className="muted">{t('exercises.unknownType')}</p>
          <pre className="exercise-json">{JSON.stringify(exercise.content, null, 2)}</pre>
        </>
      )}
      {known && !editing && (
        <>
          <ExerciseContent exercise={exercise} />
          {saved && (
            <Notice tone="success" role="status">
              {t('library.saved')}
            </Notice>
          )}
          <button
            type="button"
            className="button button--small"
            onClick={() => {
              setSaved(false)
              setEditing(true)
            }}
          >
            {t('exercises.edit')}
          </button>
        </>
      )}
      {known && editing && (
        <ExerciseForm
          exercise={exercise}
          onDone={() => {
            setEditing(false)
            setSaved(true)
          }}
        />
      )}
    </li>
  )
}

/** The exercise templates stored with the sheet. Editing them is not a drill: answers are shown. */
export function ExercisesPanel({ itemId }: { itemId: number }) {
  const { t } = useTranslation()
  const exercises = useExercises(itemId)

  return (
    <div className="exercises">
      <h3>{t('exercises.title')}</h3>
      {exercises.isPending && <p className="muted">{t('library.loading')}</p>}
      {exercises.isError && <ErrorText error={exercises.error} />}
      {exercises.isSuccess && exercises.data.length === 0 && (
        <p className="muted">{t('exercises.empty')}</p>
      )}
      {exercises.isSuccess && exercises.data.length > 0 && (
        <ul className="exercise-list">
          {exercises.data.map((exercise) => (
            <ExerciseBlock key={exercise.id} exercise={exercise} />
          ))}
        </ul>
      )}
    </div>
  )
}
