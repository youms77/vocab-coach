import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { useUnit } from '../../api/curriculum'
import { PageTitle } from '../../components/PageTitle'
import { ErrorText } from '../settings/ErrorText'
import { ScenarioUnitView } from './ScenarioUnitView'
import { WordUnitView } from './WordUnitView'
import { Notice } from '../../components/Notice'

/** `/curriculum/units/:id`: a word unit (its 25 terms) or a speaking scenario unit (four steps). */
export function UnitPage() {
  const { t } = useTranslation()
  const params = useParams()
  const id = Number(params.id)
  const valid = Number.isInteger(id) && id > 0
  const unit = useUnit(valid ? id : 0)

  if (unit.data !== undefined) {
    // Keyed by the unit: moving to the next unit starts the page afresh.
    return unit.data.scenario === null ? (
      <WordUnitView key={unit.data.id} unit={unit.data} />
    ) : (
      <ScenarioUnitView key={unit.data.id} unit={unit.data} scenario={unit.data.scenario} />
    )
  }
  return (
    <div className="curriculum-page">
      <PageTitle>{t('curriculum.unitTitle')}</PageTitle>
      {unit.isPending && valid && <p className="muted">{t('curriculum.loading')}</p>}
      {!valid && (
        <Notice tone="danger" role="alert">
          {t('errors.unit_not_found')}
        </Notice>
      )}
      {unit.isError && <ErrorText error={unit.error} />}
      <p>
        <Link to="/curriculum">{t('curriculum.allTracks')}</Link>
      </p>
    </div>
  )
}
