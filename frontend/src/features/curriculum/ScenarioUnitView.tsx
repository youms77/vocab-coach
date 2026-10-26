import { type ReactNode, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { type Scenario, type Unit, type UnitStep, UNIT_STEPS, useTrackSlice } from '../../api/curriculum'
import { PageTitle } from '../../components/PageTitle'
import { DialogueStep } from './DialogueStep'
import { FinalTaskStep } from './FinalTaskStep'
import { FormulasStep } from './FormulasStep'
import { ShadowingStep } from './ShadowingStep'
import { neighbours, stepsDone, unitTitle } from './unitRules'

/** One of the four steps: its number, its state in words and, if it is the next one, a mark. */
export function StepCard({
  step,
  scenario,
  children,
}: {
  step: UnitStep
  scenario: Scenario
  children: ReactNode
}) {
  const { t } = useTranslation()
  const done = scenario.steps[step]
  const next = scenario.next_step === step
  const number = UNIT_STEPS.indexOf(step) + 1
  return (
    <section
      className={`card unit-step${next ? ' unit-step--next' : ''}`}
      aria-labelledby={`step-${step}`}
    >
      <h2 id={`step-${step}`}>{t(`curriculum.steps.${step}`, { number })}</h2>
      <p className="unit-step__state">
        <strong>{done ? t('curriculum.stepState.done') : t('curriculum.stepState.todo')}</strong>
        {next && <span className="badge">{t('curriculum.stepState.next')}</span>}
      </p>
      {children}
    </section>
  )
}

/** A speaking scenario unit: header, the four steps (advised order, not enforced), completion. */
export function ScenarioUnitView({ unit, scenario }: { unit: Unit; scenario: Scenario }) {
  const { t, i18n } = useTranslation()
  // The unit has no `title_fr` and no neighbour: its row and the next one come from the track.
  const rows = useTrackSlice(unit.track_code, 2, unit.number - 1)
  const { current, next } = neighbours(rows.data?.units, unit.number)
  const title = current !== null ? unitTitle(current, i18n.language) : unit.title

  // "Unit completed" is announced once, when this page sees the unit become done.
  const seen = useRef(unit.progress)
  const [announcement, setAnnouncement] = useState('')
  useEffect(() => {
    if (seen.current !== 'done' && unit.progress === 'done') {
      setAnnouncement(t('curriculum.unit.completedAnnouncement'))
    }
    seen.current = unit.progress
  }, [unit.progress, t])

  const done = stepsDone(scenario.steps)
  return (
    <div className="curriculum-page">
      <section className="hero">
        <PageTitle>{title}</PageTitle>
        <p className="muted">
          {scenario.level !== null && `${t('curriculum.unit.level', { level: scenario.level })} · `}
          {t('curriculum.unit.stepsOf', { done, total: UNIT_STEPS.length })} ·{' '}
          {t(`curriculum.progress.${unit.progress}`)}
        </p>
        {scenario.next_step !== null && (
          <p>
            {t('curriculum.unit.nextStep', {
              step: t(`curriculum.stepNames.${scenario.next_step}`),
            })}
          </p>
        )}
        <p className="link-row">
          <Link to={`/curriculum/${unit.track_code}`}>{t('curriculum.backToTrack')}</Link>
          {unit.deck_id !== null && (
            <Link to={`/library?deck=${unit.deck_id}`}>{t('curriculum.deckLink')}</Link>
          )}
        </p>
        <div className="visually-hidden" role="status" aria-live="polite">
          {announcement}
        </div>
        {unit.progress === 'done' && (
          <div className="form-message form-message--ok unit-completed">
            <p>
              <strong>{t('curriculum.unit.completed')}</strong>
            </p>
            {next !== null && (
              <p>
                <Link
                  to={next.unit_id !== null ? `/curriculum/units/${next.unit_id}` : `/curriculum/${unit.track_code}`}
                >
                  {t('curriculum.unit.nextUnit', { title: unitTitle(next, i18n.language) })}
                </Link>
              </p>
            )}
          </div>
        )}
      </section>

      <StepCard step="formulas" scenario={scenario}>
        <FormulasStep unit={unit} scenario={scenario} />
      </StepCard>
      <StepCard step="dialogue" scenario={scenario}>
        <DialogueStep unit={unit} scenario={scenario} />
      </StepCard>
      <StepCard step="shadowing" scenario={scenario}>
        <ShadowingStep unit={unit} scenario={scenario} />
      </StepCard>
      <StepCard step="final_task" scenario={scenario}>
        <FinalTaskStep unit={unit} scenario={scenario} />
      </StepCard>
    </div>
  )
}
