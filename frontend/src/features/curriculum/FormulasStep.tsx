import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { type Scenario, type Unit, useAddUnitTerms, useMarkStep } from '../../api/curriculum'
import { SpeakButton } from '../../speech/SpeakButton'
import { ErrorText } from '../settings/ErrorText'

function toggled(set: ReadonlySet<number>, value: number): Set<number> {
  const next = new Set(set)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}

/**
 * Step 1: the formulas (function in English, French on demand, each one can be listened to), "I
 * have read them", and "Add to my library" for the ones the learner picks (all by default).
 */
export function FormulasStep({ unit, scenario }: { unit: Unit; scenario: Scenario }) {
  const { t } = useTranslation()
  const mark = useMarkStep()
  const add = useAddUnitTerms()
  const [unchecked, setUnchecked] = useState<ReadonlySet<number>>(new Set())
  const [french, setFrench] = useState<ReadonlySet<number>>(new Set())

  const selected = scenario.formulas
    .filter((formula) => formula.item_id === null && !unchecked.has(formula.index))
    .map((formula) => formula.index)
  const inLibrary = scenario.formulas.some((formula) => formula.item_id !== null)

  return (
    <>
      <ul className="unit-formulas">
        {scenario.formulas.map((formula) => (
          <li key={formula.index} className="unit-formula">
            <p className="unit-formula__text" lang="en">
              <strong>{formula.text}</strong>
            </p>
            <p className="muted">
              {t(`library.type.${formula.item_type}`)} · {formula.register}
            </p>
            <p lang="en">{formula.function_en}</p>
            <p>
              <button
                type="button"
                className="button button--small"
                aria-expanded={french.has(formula.index)}
                aria-label={t('curriculum.formulas.frenchNamed', { text: formula.text })}
                onClick={() => setFrench(toggled(french, formula.index))}
              >
                {t('curriculum.formulas.french')}
              </button>
            </p>
            {french.has(formula.index) && <p lang="fr">{formula.function_fr}</p>}
            <p className="unit-formula__actions">
              <SpeakButton text={formula.text} />
              {formula.item_id !== null ? (
                <Link to={`/library/items/${formula.item_id}`}>{t('curriculum.formulas.inLibrary')}</Link>
              ) : (
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={!unchecked.has(formula.index)}
                    aria-label={t('curriculum.formulas.addOneNamed', { text: formula.text })}
                    onChange={() => setUnchecked(toggled(unchecked, formula.index))}
                  />
                  {t('curriculum.formulas.addOne')}
                </label>
              )}
            </p>
          </li>
        ))}
      </ul>

      <div className="unit-step__actions">
        <p className="muted field-hint">
          {t('curriculum.formulas.selected', { count: selected.length })}
        </p>
        <p>
          <button
            type="button"
            className="button button--primary"
            disabled={selected.length === 0 || add.isPending}
            onClick={() => add.mutate({ unitId: unit.id, indices: selected })}
          >
            {t('curriculum.formulas.add')}
          </button>
        </p>
        <div role="status">
          {add.isSuccess && (
            <p>
              {t('curriculum.formulas.added', {
                imported: add.data.imported,
                attached: add.data.attached,
                skipped: add.data.skipped,
              })}
            </p>
          )}
        </div>
        {add.isError && <ErrorText error={add.error} />}
        {unit.deck_id !== null && inLibrary && (
          <p>
            <Link to={`/triage?deck=${unit.deck_id}`}>{t('curriculum.formulas.toTriage')}</Link>
          </p>
        )}
        {!scenario.steps.formulas && (
          <p>
            <button
              type="button"
              className="button"
              disabled={mark.isPending}
              onClick={() => mark.mutate({ unitId: unit.id, step: 'formulas' })}
            >
              {t('curriculum.formulas.markRead')}
            </button>
          </p>
        )}
        {mark.isError && <ErrorText error={mark.error} />}
      </div>
    </>
  )
}
