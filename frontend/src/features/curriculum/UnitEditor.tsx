import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import { type Scenario, type Unit, useEditUnitContent } from '../../api/curriculum'
import { ErrorText } from '../settings/ErrorText'
import { FieldErrors } from '../library/FieldErrors'
import {
  clientProblems,
  emptyFormula,
  emptyLine,
  FORMULA_TYPES,
  type FormulaType,
  fieldPaths,
  fromScenario,
  locateProblem,
  moved,
  type Problem,
  removed,
  toEdit,
  type UnitDraft,
  words,
} from './unitForm'
import { UNIT_LIMITS as LIMITS } from './unitRules'

const slug = (path: string) => path.replace(/[^a-zA-Z0-9]+/g, '-')

/**
 * Edits a scenario unit on a local draft (D-092): nothing is written before "Save", only the parts
 * that changed are sent with the revision the draft started from, and a refusal (409
 * `unit_changed`, 422 `invalid_content`) leaves every edit on screen.
 */
export function UnitEditor({
  unit,
  scenario,
  onClose,
}: {
  unit: Unit
  /** The live version of the unit: it may be newer than the one the draft started from. */
  scenario: Scenario
  onClose: (saved: boolean) => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const save = useEditUnitContent()
  const [base, setBase] = useState(scenario)
  const [draft, setDraft] = useState<UnitDraft>(() => fromScenario(scenario))
  const [showProblems, setShowProblems] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [confirmReload, setConfirmReload] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  const summaryRef = useRef<HTMLDivElement>(null)
  const [focusWanted, setFocusWanted] = useState<string[] | null>(null)

  useEffect(() => titleRef.current?.focus(), [])

  // After a move, an add or a remove the focus stays where the user was working.
  useEffect(() => {
    if (focusWanted === null) return
    for (const name of focusWanted) {
      const el = formRef.current?.querySelector<HTMLElement>(`[data-focus="${name}"]`)
      if (el && !(el as HTMLButtonElement).disabled) {
        el.focus()
        break
      }
    }
  }, [focusWanted])

  const error = save.error
  const stale = error instanceof ApiError && error.code === 'unit_changed'
  const invalid = error instanceof ApiError && error.code === 'invalid_content'
  const otherError = save.isError && !stale && !invalid

  const paths = fieldPaths(draft)
  const own: Problem[] = showProblems ? clientProblems(draft) : []
  const serverProblems = invalid && Array.isArray(error.detail.problems)
    ? error.detail.problems.filter((p): p is string => typeof p === 'string')
    : []
  const located = serverProblems.map((p) => locateProblem(p, draft))
  const atField = (path: string) => located.filter((p) => p.path === path)
  const unlocated = located.filter((p) => p.path === null || !paths.has(p.path))
  const problemCount = own.length + located.length

  // A failed attempt moves the focus to the first field in error, else to the summary.
  useEffect(() => {
    if (attempt === 0) return
    const first = formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')
    ;(first ?? summaryRef.current)?.focus()
  }, [attempt])

  const want = (names: string[]) => setFocusWanted(names)
  const edit = (change: (d: UnitDraft) => UnitDraft, structural = false) => {
    setDraft(change)
    if (structural && invalid) save.reset()
  }
  const formulaAt = (i: number, patch: Partial<UnitDraft['formulas'][number]>) =>
    edit((d) => ({ ...d, formulas: d.formulas.map((f, j) => (j === i ? { ...f, ...patch } : f)) }))
  const lineAt = (i: number, patch: Partial<UnitDraft['lines'][number]>) =>
    edit((d) => ({ ...d, lines: d.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)) }))

  const changed = toEdit(draft, base, base.revision) !== null

  function submit(event: FormEvent) {
    event.preventDefault()
    if (clientProblems(draft).length > 0) {
      setShowProblems(true)
      setAttempt((n) => n + 1)
      return
    }
    const payload = toEdit(draft, base, base.revision)
    if (payload === null) return
    setShowProblems(false)
    save.mutate(
      { unitId: unit.id, edit: payload },
      {
        onSuccess: () => onClose(true),
        onError: (e) => {
          if (e instanceof ApiError && e.code === 'invalid_content') setAttempt((n) => n + 1)
        },
      },
    )
  }

  function loadLatest() {
    setBase(scenario)
    setDraft(fromScenario(scenario))
    setConfirmReload(false)
    setShowProblems(false)
    save.reset()
    want(['title'])
  }

  // --- Small pieces ------------------------------------------------------------------------------

  const describe = (path: string) => {
    const has = own.some((p) => p.path === path) || atField(path).length > 0
    return has ? { 'aria-invalid': true, 'aria-describedby': `${id}-err-${slug(path)}` } : {}
  }

  const fieldProblems = (path: string) => {
    const mine = own.filter((p) => p.path === path)
    const theirs = atField(path)
    if (mine.length === 0 && theirs.length === 0) return null
    return (
      <ul className="field-errors" id={`${id}-err-${slug(path)}`}>
        {mine.map((p) => (
          <li key={p.key}>{t(`curriculum.edit.problems.${p.key}`, p.values)}</li>
        ))}
        {theirs.map((p) => (
          <li key={p.message} lang="en">
            {p.message}
          </li>
        ))}
      </ul>
    )
  }

  const text = (
    path: string,
    label: string,
    value: string,
    onChange: (value: string) => void,
    max: number,
    options: { long?: boolean; focus?: string } = {},
  ) => (
    <div className="field">
      <label htmlFor={`${id}-${slug(path)}`}>{label}</label>
      {options.long ? (
        <textarea
          id={`${id}-${slug(path)}`}
          rows={2}
          maxLength={max}
          value={value}
          data-focus={options.focus}
          onChange={(e) => onChange(e.target.value)}
          {...describe(path)}
        />
      ) : (
        <input
          id={`${id}-${slug(path)}`}
          type="text"
          maxLength={max}
          value={value}
          data-focus={options.focus}
          onChange={(e) => onChange(e.target.value)}
          {...describe(path)}
        />
      )}
      {fieldProblems(path)}
    </div>
  )

  const rowButtons = (
    name: string,
    key: number,
    prefix: string,
    index: number,
    length: number,
    move: (by: -1 | 1) => void,
    remove: () => void,
  ) => (
    <div className="unit-edit-row__actions">
      <button
        type="button"
        className="button button--small"
        data-focus={`${prefix}-${key}-up`}
        disabled={index === 0}
        aria-label={t('curriculum.edit.rowUp', { name })}
        onClick={() => {
          want([`${prefix}-${key}-up`, `${prefix}-${key}-down`])
          move(-1)
        }}
      >
        ↑
      </button>
      <button
        type="button"
        className="button button--small"
        data-focus={`${prefix}-${key}-down`}
        disabled={index === length - 1}
        aria-label={t('curriculum.edit.rowDown', { name })}
        onClick={() => {
          want([`${prefix}-${key}-down`, `${prefix}-${key}-up`])
          move(1)
        }}
      >
        ↓
      </button>
      <button
        type="button"
        className="button button--small button--danger"
        aria-label={t('curriculum.edit.rowRemove', { name })}
        onClick={remove}
      >
        ✕
      </button>
    </div>
  )

  const speakerName = (index: 0 | 1) =>
    draft.speakers[index].trim() === '' ? String(index + 1) : draft.speakers[index]
  const shadowCount = draft.lines.filter((line) => line.shadow).length
  const taskCount = draft.formulas.filter((formula) => formula.inTask).length

  // --- Render ------------------------------------------------------------------------------------

  return (
    <form
      className="card unit-editor"
      ref={formRef}
      onSubmit={submit}
      aria-labelledby={`${id}-title`}
    >
      <h2 id={`${id}-title`} tabIndex={-1} ref={titleRef} data-focus="title">
        {t('curriculum.edit.title')}
      </h2>
      <p className="muted">{t('curriculum.edit.intro')}</p>

      {(problemCount > 0 || unlocated.length > 0) && (
        <div className="form-message form-message--error" role="alert" tabIndex={-1} ref={summaryRef}>
          <p>{t('curriculum.edit.summary', { count: problemCount })}</p>
          {unlocated.length > 0 && (
            <>
              <p>{t('curriculum.edit.unlocated')}</p>
              <ul lang="en">
                {unlocated.map((p) => (
                  <li key={`${p.path}${p.message}`}>{p.message}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <fieldset className="sheet-list">
        <legend>{t('curriculum.edit.formulas.legend')}</legend>
        <p className="muted">
          {t('curriculum.edit.formulas.count', { count: draft.formulas.length, ...LIMITS.formulas })}
        </p>
        <p className="muted">{t('curriculum.edit.libraryNote')}</p>
        {fieldProblems('formulas')}
        <ol className="unit-edit-list">
          {draft.formulas.map((f, i) => {
            const name = t('curriculum.edit.formulas.name', { number: i + 1 })
            return (
              <li key={f.key}>
                <fieldset className="unit-edit-row">
                  <legend>{name}</legend>
                  <div className="unit-edit-grid">
                    {text(
                      `formulas[${i}].text`,
                      t('curriculum.edit.formulas.text'),
                      f.text,
                      (v) => formulaAt(i, { text: v }),
                      LIMITS.max.formula,
                      { focus: `f-${f.key}-text` },
                    )}
                    <div className="field">
                      <label htmlFor={`${id}-ftype-${f.key}`}>{t('curriculum.edit.formulas.type')}</label>
                      <select
                        id={`${id}-ftype-${f.key}`}
                        value={f.item_type}
                        onChange={(e) => formulaAt(i, { item_type: e.target.value as FormulaType })}
                      >
                        {FORMULA_TYPES.map((type) => (
                          <option key={type} value={type}>
                            {t(`library.type.${type}`)}
                          </option>
                        ))}
                      </select>
                    </div>
                    {text(
                      `formulas[${i}].function_en`,
                      t('curriculum.edit.formulas.functionEn'),
                      f.function_en,
                      (v) => formulaAt(i, { function_en: v }),
                      LIMITS.max.function,
                    )}
                    {text(
                      `formulas[${i}].function_fr`,
                      t('curriculum.edit.formulas.functionFr'),
                      f.function_fr,
                      (v) => formulaAt(i, { function_fr: v }),
                      LIMITS.max.function,
                    )}
                    {text(
                      `formulas[${i}].register`,
                      t('curriculum.edit.formulas.register'),
                      f.register,
                      (v) => formulaAt(i, { register: v }),
                      LIMITS.max.register,
                    )}
                  </div>
                  {rowButtons(
                    name,
                    f.key,
                    'f',
                    i,
                    draft.formulas.length,
                    (by) => edit((d) => ({ ...d, formulas: moved(d.formulas, i, by) }), true),
                    () => {
                      want(['add-formula'])
                      edit((d) => ({ ...d, formulas: removed(d.formulas, i) }), true)
                    },
                  )}
                </fieldset>
              </li>
            )
          })}
        </ol>
        <button
          type="button"
          className="button"
          data-focus="add-formula"
          disabled={draft.formulas.length >= LIMITS.formulas.max}
          onClick={() => {
            const row = emptyFormula()
            want([`f-${row.key}-text`])
            edit((d) => ({ ...d, formulas: [...d.formulas, row] }), true)
          }}
        >
          {t('curriculum.edit.formulas.add')}
        </button>
      </fieldset>

      <fieldset className="sheet-list">
        <legend>{t('curriculum.edit.dialogue.legend')}</legend>
        <div className="unit-edit-grid">
          {text(
            'dialogue.setting_en',
            t('curriculum.edit.dialogue.settingEn'),
            draft.setting_en,
            (v) => edit((d) => ({ ...d, setting_en: v })),
            LIMITS.max.setting,
            { long: true },
          )}
          {text(
            'dialogue.setting_fr',
            t('curriculum.edit.dialogue.settingFr'),
            draft.setting_fr,
            (v) => edit((d) => ({ ...d, setting_fr: v })),
            LIMITS.max.setting,
            { long: true },
          )}
          {([0, 1] as const).map((n) => (
            <div className="field" key={n}>
              <label htmlFor={`${id}-speaker-${n}`}>
                {t('curriculum.edit.dialogue.speakerName', { number: n + 1 })}
              </label>
              <input
                id={`${id}-speaker-${n}`}
                type="text"
                maxLength={LIMITS.max.name}
                value={draft.speakers[n]}
                onChange={(e) =>
                  edit((d) => {
                    const speakers: [string, string] = [...d.speakers]
                    speakers[n] = e.target.value
                    return { ...d, speakers }
                  })
                }
                {...describe('dialogue.speakers')}
              />
            </div>
          ))}
        </div>
        {fieldProblems('dialogue.speakers')}
        <p className="muted">
          {t('curriculum.edit.dialogue.count', { count: draft.lines.length, ...LIMITS.lines })}
        </p>
        {fieldProblems('dialogue.lines')}
        <ol className="unit-edit-list">
          {draft.lines.map((line, i) => {
            const name = t('curriculum.edit.dialogue.name', { number: i + 1 })
            return (
              <li key={line.key}>
                <fieldset className="unit-edit-row">
                  <legend>{name}</legend>
                  <div className="unit-edit-grid unit-edit-grid--line">
                    <div className="field">
                      <label htmlFor={`${id}-lspeaker-${line.key}`}>
                        {t('curriculum.edit.dialogue.speaker', { number: i + 1 })}
                      </label>
                      <select
                        id={`${id}-lspeaker-${line.key}`}
                        value={line.speaker}
                        onChange={(e) => lineAt(i, { speaker: e.target.value === '1' ? 1 : 0 })}
                      >
                        <option value={0}>{speakerName(0)}</option>
                        <option value={1}>{speakerName(1)}</option>
                      </select>
                    </div>
                    {text(
                      `dialogue.lines[${i}].text`,
                      t('curriculum.edit.dialogue.text', { number: i + 1 }),
                      line.text,
                      (v) => lineAt(i, { text: v }),
                      LIMITS.max.line,
                      { long: true, focus: `l-${line.key}-text` },
                    )}
                  </div>
                  {rowButtons(
                    name,
                    line.key,
                    'l',
                    i,
                    draft.lines.length,
                    (by) => edit((d) => ({ ...d, lines: moved(d.lines, i, by) }), true),
                    () => {
                      want(['add-line'])
                      edit((d) => ({ ...d, lines: removed(d.lines, i) }), true)
                    },
                  )}
                </fieldset>
              </li>
            )
          })}
        </ol>
        <button
          type="button"
          className="button"
          data-focus="add-line"
          disabled={draft.lines.length >= LIMITS.lines.max}
          onClick={() => {
            const row = emptyLine(draft.lines.length % 2 === 0 ? 0 : 1)
            want([`l-${row.key}-text`])
            edit((d) => ({ ...d, lines: [...d.lines, row] }), true)
          }}
        >
          {t('curriculum.edit.dialogue.add')}
        </button>
      </fieldset>

      <fieldset className="sheet-list">
        <legend>{t('curriculum.edit.shadowing.legend')}</legend>
        <p className="muted">{t('curriculum.edit.shadowing.hint')}</p>
        <p className="form-message form-message--warn">{t('curriculum.edit.shadowWarning')}</p>
        <p className="muted">
          {t('curriculum.edit.shadowing.count', { count: shadowCount, ...LIMITS.shadowing })}
        </p>
        {fieldProblems('shadowing')}
        <ul className="unit-edit-list">
          {draft.lines.map((line, i) => (
            <li key={line.key}>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={line.shadow}
                  onChange={() => lineAt(i, { shadow: !line.shadow })}
                  {...describe(`dialogue.lines[${i}].shadow`)}
                />
                <span lang="en">
                  <strong>{i + 1}.</strong> {line.text.trim() === '' ? '…' : line.text}{' '}
                  <span className="muted">
                    ({t('curriculum.edit.shadowing.words', { count: words(line.text) })})
                  </span>
                </span>
              </label>
              {fieldProblems(`dialogue.lines[${i}].shadow`)}
            </li>
          ))}
        </ul>
      </fieldset>

      <fieldset className="sheet-list">
        <legend>{t('curriculum.edit.finalTask.legend')}</legend>
        <div className="unit-edit-grid">
          {text(
            'final_task.prompt_en',
            t('curriculum.edit.finalTask.promptEn'),
            draft.prompt_en,
            (v) => edit((d) => ({ ...d, prompt_en: v })),
            LIMITS.max.prompt,
            { long: true },
          )}
          {text(
            'final_task.prompt_fr',
            t('curriculum.edit.finalTask.promptFr'),
            draft.prompt_fr,
            (v) => edit((d) => ({ ...d, prompt_fr: v })),
            LIMITS.max.prompt,
            { long: true },
          )}
          <div className="field">
            <label htmlFor={`${id}-minutes`}>{t('curriculum.edit.finalTask.minutes')}</label>
            <select
              id={`${id}-minutes`}
              value={draft.minutes}
              onChange={(e) => edit((d) => ({ ...d, minutes: e.target.value === '2' ? 2 : 1 }))}
            >
              {LIMITS.minutes.map((m) => (
                <option key={m} value={m}>
                  {t('curriculum.edit.finalTask.minutesOption', { count: m })}
                </option>
              ))}
            </select>
          </div>
        </div>
        <p>
          <strong>{t('curriculum.edit.finalTask.formulas')}</strong>
        </p>
        <p className="muted">
          {t('curriculum.edit.finalTask.count', { count: taskCount, min: LIMITS.finalRefsMin })}
        </p>
        {fieldProblems('final_task.formula_refs')}
        <ul className="unit-edit-list">
          {draft.formulas.map((f, i) => (
            <li key={f.key}>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={f.inTask}
                  onChange={() => formulaAt(i, { inTask: !f.inTask })}
                  {...describe(`formulas[${i}].inTask`)}
                />
                <span lang="en">
                  <strong>{i + 1}.</strong> {f.text.trim() === '' ? '…' : f.text}
                </span>
              </label>
              {fieldProblems(`formulas[${i}].inTask`)}
            </li>
          ))}
        </ul>
      </fieldset>

      <div className="confirm">
        <button
          type="submit"
          className="button button--primary"
          disabled={save.isPending || !changed}
        >
          {save.isPending ? t('curriculum.edit.saving') : t('curriculum.edit.save')}
        </button>
        <button type="button" className="button" onClick={() => onClose(false)}>
          {t('curriculum.edit.cancel')}
        </button>
        {!changed && <span className="muted">{t('curriculum.edit.nothingChanged')}</span>}
      </div>

      {otherError && <ErrorText error={error} />}
      {otherError && <FieldErrors error={error} />}
      {stale && !confirmReload && (
        <div className="form-message form-message--warn" role="alert">
          <p>{t('curriculum.edit.stale.hint')}</p>
          <button
            type="button"
            className="button"
            disabled={scenario.revision === base.revision}
            onClick={() => setConfirmReload(true)}
          >
            {scenario.revision === base.revision
              ? t('curriculum.edit.stale.loading')
              : t('curriculum.edit.stale.load')}
          </button>
        </div>
      )}
      {stale && confirmReload && (
        <div className="confirm" role="alertdialog" aria-label={t('curriculum.edit.stale.confirm')}>
          <p>{t('curriculum.edit.stale.confirm')}</p>
          <button type="button" className="button button--danger" onClick={loadLatest}>
            {t('curriculum.edit.stale.yes')}
          </button>
          <button type="button" className="button" onClick={() => setConfirmReload(false)}>
            {t('curriculum.edit.stale.keep')}
          </button>
        </div>
      )}
    </form>
  )
}
