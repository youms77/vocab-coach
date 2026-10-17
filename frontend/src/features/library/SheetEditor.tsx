import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import {
  EXAMPLE_KINDS,
  REGISTERS,
  useSaveSheet,
  type ExampleKind,
  type Register,
  type SheetVersion,
} from '../../api/enrichment'
import { ErrorText } from '../settings/ErrorText'
import { FieldErrors } from './FieldErrors'
import {
  EMPTY_ROW,
  LIST_MAX,
  fromSheet,
  hasMeaning,
  toSheet,
  type ListField,
  type SheetDraft,
} from './sheetForm'

type Column =
  | 'definition'
  | 'translation_fr'
  | 'pattern'
  | 'example'
  | 'sentence'
  | 'kind'
  | 'form'
  | 'part_of_speech'
  | 'wrong'
  | 'right'
  | 'explanation'
  | 'term'
  | 'difference'

type ObjectField = Exclude<ListField, 'translation_fr'>

const COLUMNS: Record<ObjectField, Column[]> = {
  other_meanings: ['definition', 'translation_fr'],
  collocations: ['pattern', 'example'],
  examples: ['sentence', 'kind'],
  word_family: ['form', 'part_of_speech'],
  french_speaker_pitfalls: ['wrong', 'right', 'explanation'],
  confusables: ['term', 'difference'],
}

type Row = Record<string, string>

function RowsEditor({
  field,
  rows,
  onChange,
}: {
  field: ObjectField
  rows: Row[]
  onChange: (rows: Row[]) => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const label = t(`sheet.fields.${field}`)
  const set = (index: number, column: Column, value: string) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, [column]: value } : row)))

  return (
    <fieldset className="sheet-list">
      <legend>{label}</legend>
      {rows.map((row, index) => (
        <div
          key={index}
          className="sheet-row"
          role="group"
          aria-label={t('sheet.row', { field: label, n: index + 1 })}
        >
          {COLUMNS[field].map((column) => {
            const inputId = `${id}-${index}-${column}`
            return (
              <div className="field" key={column}>
                <label htmlFor={inputId}>{t(`sheet.columns.${column}`)}</label>
                {column === 'kind' ? (
                  <select
                    id={inputId}
                    value={row[column]}
                    onChange={(e) => set(index, column, e.target.value)}
                  >
                    {EXAMPLE_KINDS.map((kind) => (
                      <option key={kind} value={kind}>
                        {t(`sheet.kind.${kind}`)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={inputId}
                    type="text"
                    value={row[column]}
                    onChange={(e) => set(index, column, e.target.value)}
                  />
                )}
              </div>
            )
          })}
          <button
            type="button"
            className="button button--small"
            aria-label={t('sheet.removeRow', { field: label, n: index + 1 })}
            onClick={() => onChange(rows.filter((_, i) => i !== index))}
          >
            {t('sheet.remove')}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="button button--small"
        disabled={rows.length >= LIST_MAX[field]}
        onClick={() => onChange([...rows, { ...EMPTY_ROW[field] }])}
      >
        {t('sheet.addRow', { field: label })}
      </button>
    </fieldset>
  )
}

function TranslationsEditor({
  values,
  onChange,
}: {
  values: string[]
  onChange: (values: string[]) => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const label = t('sheet.fields.translation_fr')
  return (
    <fieldset className="sheet-list">
      <legend>{label}</legend>
      {values.map((value, index) => (
        <div key={index} className="sheet-row">
          <div className="field">
            <label htmlFor={`${id}-${index}`}>{t('sheet.row', { field: label, n: index + 1 })}</label>
            <input
              id={`${id}-${index}`}
              type="text"
              lang="fr"
              value={value}
              onChange={(e) => onChange(values.map((v, i) => (i === index ? e.target.value : v)))}
            />
          </div>
          <button
            type="button"
            className="button button--small"
            aria-label={t('sheet.removeRow', { field: label, n: index + 1 })}
            onClick={() => onChange(values.filter((_, i) => i !== index))}
          >
            {t('sheet.remove')}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="button button--small"
        disabled={values.length >= LIST_MAX.translation_fr}
        onClick={() => onChange([...values, ''])}
      >
        {t('sheet.addRow', { field: label })}
      </button>
    </fieldset>
  )
}

type TextField =
  | 'meaning_in_context'
  | 'definition_simple'
  | 'usage_notes'
  | 'part_of_speech'
  | 'register_note'

/**
 * Edits a sheet, or types one by hand (`base` null: manual entry, the degraded mode). The version
 * the user started from is sent as `base_enrichment_id`: if the sheet changed meanwhile, the save is
 * refused (409 `sheet_changed`) and the edits stay on screen until the user chooses to reload.
 */
export function SheetEditor({
  itemId,
  base,
  partOfSpeech,
  onSaved,
  onCancel,
  onReload,
}: {
  itemId: number
  base: SheetVersion | null
  partOfSpeech: string | null
  onSaved: () => void
  onCancel: () => void
  onReload: () => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const save = useSaveSheet(itemId)
  const [draft, setDraft] = useState<SheetDraft>(() =>
    fromSheet(base?.content ?? null, partOfSpeech),
  )
  const [missingMeaning, setMissingMeaning] = useState(false)
  const [confirmReload, setConfirmReload] = useState(false)

  const set = <K extends keyof SheetDraft>(key: K, value: SheetDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))
  const stale = save.error instanceof ApiError && save.error.code === 'sheet_changed'

  function submit(event: FormEvent) {
    event.preventDefault()
    const sheet = toSheet(draft)
    setMissingMeaning(!hasMeaning(sheet))
    if (!hasMeaning(sheet)) return
    save.mutate(
      { content: sheet, base_enrichment_id: base?.enrichment_id ?? null },
      { onSuccess: onSaved },
    )
  }

  const textField = (key: TextField, long = false) => (
    <div className="field">
      <label htmlFor={`${id}-${key}`}>{t(`sheet.fields.${key}`)}</label>
      {long ? (
        <textarea
          id={`${id}-${key}`}
          rows={3}
          value={draft[key]}
          onChange={(e) => set(key, e.target.value)}
        />
      ) : (
        <input
          id={`${id}-${key}`}
          type="text"
          value={draft[key]}
          onChange={(e) => set(key, e.target.value)}
        />
      )}
    </div>
  )

  return (
    <form className="sheet-editor" onSubmit={submit} aria-label={t('sheet.editorLabel')}>
      <p className="muted">{t('sheet.editorHint')}</p>
      {textField('meaning_in_context', true)}
      {textField('definition_simple', true)}
      <TranslationsEditor
        values={draft.translation_fr}
        onChange={(values) => set('translation_fr', values)}
      />
      <div className="inline-fields">
        {textField('part_of_speech')}
        <div className="field">
          <label htmlFor={`${id}-register`}>{t('sheet.fields.register_level')}</label>
          <select
            id={`${id}-register`}
            value={draft.register_level}
            onChange={(e) => set('register_level', e.target.value as Register | '')}
          >
            <option value="">{t('sheet.register.none')}</option>
            {REGISTERS.map((r) => (
              <option key={r} value={r}>
                {t(`sheet.register.${r}`)}
              </option>
            ))}
          </select>
        </div>
      </div>
      {textField('register_note')}
      {textField('usage_notes', true)}
      {(Object.keys(COLUMNS) as ObjectField[]).map((field) => (
        <RowsEditor
          key={field}
          field={field}
          rows={draft[field] as Row[]}
          onChange={(rows) =>
            setDraft((d) => ({
              ...d,
              [field]:
                field === 'examples'
                  ? rows.map((r) => ({ ...r, kind: r.kind as ExampleKind }))
                  : rows,
            }))
          }
        />
      ))}
      <fieldset className="sheet-list">
        <legend>{t('sheet.fields.pronunciation')}</legend>
        <div className="inline-fields">
          {(['ipa_us', 'stressed_syllable', 'note'] as const).map((key) => (
            <div className="field" key={key}>
              <label htmlFor={`${id}-pron-${key}`}>{t(`sheet.pronunciation.${key}`)}</label>
              <input
                id={`${id}-pron-${key}`}
                type="text"
                value={draft.pronunciation[key]}
                onChange={(e) =>
                  set('pronunciation', { ...draft.pronunciation, [key]: e.target.value })
                }
              />
            </div>
          ))}
        </div>
      </fieldset>
      {missingMeaning && (
        <p className="form-message form-message--error" role="alert">
          {t('sheet.needsMeaning')}
        </p>
      )}
      <div className="confirm">
        <button type="submit" className="button button--primary" disabled={save.isPending}>
          {t('sheet.save')}
        </button>
        <button type="button" className="button" onClick={onCancel}>
          {t('library.cancel')}
        </button>
      </div>
      {save.isError && <ErrorText error={save.error} />}
      {save.isError && <FieldErrors error={save.error} />}
      {stale && !confirmReload && (
        <div className="confirm">
          <p>{t('sheet.staleHint')}</p>
          <button type="button" className="button" onClick={() => setConfirmReload(true)}>
            {t('sheet.reload')}
          </button>
        </div>
      )}
      {stale && confirmReload && (
        <div className="confirm" role="alertdialog" aria-label={t('sheet.reloadConfirm')}>
          <p>{t('sheet.reloadConfirm')}</p>
          <button type="button" className="button button--danger" onClick={onReload}>
            {t('sheet.reloadYes')}
          </button>
          <button type="button" className="button" onClick={() => setConfirmReload(false)}>
            {t('sheet.keepEditing')}
          </button>
        </div>
      )}
    </form>
  )
}
