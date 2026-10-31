import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useParams } from 'react-router'

import { ApiError } from '../../api/client'
import { type Drill, useDrill } from '../../api/drills'
import { labelOf } from '../../api/errors'
import { PageTitle } from '../../components/PageTitle'
import { formatDateTime } from '../session/format'
import { ErrorText } from '../settings/ErrorText'
import { DrillItemPlayer } from './DrillItemPlayer'
import { firstUnanswered } from './drillRules'
import { DrillSummary } from './DrillSummary'
import { fromSessionOf } from './fromSession'
import { Notice } from '../../components/Notice'
import { CategoryCode } from '../../components/CategoryCode'

/**
 * The rule and the items of a loaded drill. It resumes at the first item not answered. The item
 * shown is this component's own state: answering updates the cached drill, but the result stays
 * in front of the user until they ask for the next item.
 */
function DrillRun({
  drill,
  fromSession,
  onReload,
}: {
  drill: Drill
  fromSession: number | null
  /** Read the drill again; resolves to the fresh drill. */
  onReload: () => Promise<Drill | undefined>
}) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(() => firstUnanswered(drill))
  // Bumped when the drill is loaded again, so the item starts fresh.
  const [epoch, setEpoch] = useState(0)
  // The user has gone through an item: the field of the next one takes the focus.
  const [worked, setWorked] = useState(false)
  const [french, setFrench] = useState(false)
  const items = drill.items

  // Finished: the summary takes the focus.
  const summaryRef = useRef<HTMLDivElement>(null)
  const finished = index >= items.length
  useEffect(() => {
    if (finished) summaryRef.current?.focus()
  }, [finished])

  async function reload() {
    const fresh = await onReload()
    if (fresh !== undefined) {
      setIndex(firstUnanswered(fresh))
      setEpoch((n) => n + 1)
    }
  }

  return (
    <>
      <section className="card drill-rule" aria-labelledby="drill-rule-title">
        <h2 id="drill-rule-title">{t('drills.player.rule')}</h2>
        <p lang="en">{drill.rule_en}</p>
        <p>
          <button
            type="button"
            className="button button--small"
            aria-expanded={french}
            onClick={() => setFrench(!french)}
          >
            {french ? t('drills.player.hideFrench') : t('drills.player.showFrench')}
          </button>
        </p>
        {french && <p lang="fr">{drill.rule_fr}</p>}
      </section>

      {!finished && (
        <section className="card" aria-label={t('drills.player.item', { n: index + 1, total: items.length })}>
          <DrillItemPlayer
            key={`${drill.id}:${index}:${epoch}`}
            drillId={drill.id}
            item={items[index]}
            total={items.length}
            isLast={index === items.length - 1}
            focusInput={worked}
            onNext={() => {
              setWorked(true)
              // Relative to the item that was answered: a late second call changes nothing.
              setIndex((n) => (n === items[index].index ? n + 1 : n))
            }}
            onReload={() => void reload()}
          />
        </section>
      )}

      {finished && <DrillSummary ref={summaryRef} drill={drill} fromSession={fromSession} />}
    </>
  )
}

/** `/drills/:id`: the rule from the start, then one item at a time (D-103, D-136). */
export function DrillPage() {
  const { t, i18n } = useTranslation()
  const params = useParams()
  const location = useLocation()
  const id = Number(params.id)
  const valid = Number.isInteger(id) && id > 0
  const query = useDrill(valid ? id : 0, valid)
  const drill = query.data
  const fromSession = fromSessionOf(location.state)

  const notFound =
    !valid || (query.isError && query.error instanceof ApiError && query.error.status === 404)
  if (notFound) {
    return (
      <div className="drills-page">
        <PageTitle>{t('drills.player.title')}</PageTitle>
        <Notice tone="danger" role="alert">
          {t('errors.drill_not_found')}
        </Notice>
        <p>
          <Link to="/drills">{t('drills.player.back')}</Link>
        </p>
      </div>
    )
  }

  return (
    <div className="drills-page">
      <section className="hero">
        <PageTitle>
          {drill !== undefined ? labelOf(drill.category, i18n.language) : t('drills.player.title')}
        </PageTitle>
        {drill !== undefined && (
          <p className="muted">
            <CategoryCode code={drill.category.code} /> ·{' '}
            {formatDateTime(drill.created_at, i18n.language)}
          </p>
        )}
        <p className="link-row">
          <Link to="/drills">{t('drills.player.back')}</Link>
        </p>
      </section>

      {query.isPending && valid && <p className="muted">{t('drills.player.loading')}</p>}
      {query.isError && <ErrorText error={query.error} />}

      {drill !== undefined && (
        <DrillRun
          drill={drill}
          fromSession={fromSession}
          onReload={async () => (await query.refetch()).data}
        />
      )}
    </div>
  )
}
