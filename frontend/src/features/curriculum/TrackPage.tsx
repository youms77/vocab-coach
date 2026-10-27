import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import {
  TRACK_PAGE_SIZE,
  type TrackSummary,
  type UnitRow,
  useOpenUnit,
  useStartTrack,
  useTrack,
} from '../../api/curriculum'
import { PageTitle } from '../../components/PageTitle'
import { ErrorText } from '../settings/ErrorText'
import { GenerateUnitButton } from './GenerateUnitButton'
import { labelIn } from './labels'
import { pageFromParam, unitTitle } from './unitRules'

function WordUnitAction({ code, row }: { code: string; row: UnitRow }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const open = useOpenUnit()
  const label = t('curriculum.openNamed', { number: row.number })
  if (row.unit_id !== null) {
    return (
      <Link to={`/curriculum/units/${row.unit_id}`} className="button" aria-label={label}>
        {t('curriculum.open')}
      </Link>
    )
  }
  return (
    <>
      <button
        type="button"
        className="button button--primary"
        aria-label={label}
        disabled={open.isPending}
        onClick={() =>
          open.mutate(
            { code, number: row.number },
            { onSuccess: (result) => void navigate(`/curriculum/units/${result.unit.id}`) },
          )
        }
      >
        {t('curriculum.open')}
      </button>
      {open.isError && <ErrorText error={open.error} />}
    </>
  )
}

function UnitItem({ track, row }: { track: TrackSummary; row: UnitRow }) {
  const { t, i18n } = useTranslation()
  const scenarios = track.kind === 'scenarios'
  const headingId = `unit-${track.code}-${row.number}`
  return (
    <li className="card unit-row">
      <div className="unit-row__main">
        <h3 id={headingId}>
          <span className="unit-row__number">
            {t('curriculum.unitNumber', { number: row.number })}
          </span>{' '}
          {unitTitle(row, i18n.language)}
        </h3>
        <p className="muted">
          {scenarios
            ? row.unit_id === null
              ? t('curriculum.notWritten')
              : t(`curriculum.progress.${row.progress}`)
            : t(`curriculum.state.${row.state}`)}
          {!scenarios &&
            row.word_count !== null &&
            ` · ${t('curriculum.words', { count: row.word_count })}`}
        </p>
      </div>
      {track.started && (
        <div className="unit-row__action">
          {scenarios && row.unit_id === null ? (
            <GenerateUnitButton code={track.code} number={row.number} describedBy={headingId} />
          ) : scenarios ? (
            <Link
              to={`/curriculum/units/${row.unit_id}`}
              className="button"
              aria-label={t('curriculum.openNamed', { number: row.number })}
            >
              {t('curriculum.open')}
            </Link>
          ) : (
            <WordUnitAction code={track.code} row={row} />
          )}
        </div>
      )}
    </li>
  )
}

/** `/curriculum/:code`: the units of a track, 25 per page (the page is in the URL). */
export function TrackPage() {
  const { t, i18n } = useTranslation()
  const { code = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const page = pageFromParam(params.get('page'))
  const track = useTrack(code, page)
  const start = useStartTrack()
  const detail = track.data
  const pages = Math.max(1, Math.ceil((detail?.total_units ?? 0) / TRACK_PAGE_SIZE))

  const goTo = (next: number) => setParams(next > 0 ? { page: String(next + 1) } : {})

  return (
    <div className="curriculum-page">
      <section className="hero">
        <PageTitle>
          {detail !== undefined
            ? labelIn(detail.track.title, i18n.language)
            : t('curriculum.trackTitle')}
        </PageTitle>
        {detail !== undefined && (
          <p className="muted">{labelIn(detail.track.description, i18n.language)}</p>
        )}
        <p className="link-row">
          <Link to="/curriculum">{t('curriculum.allTracks')}</Link>
          {detail?.track.started === true && detail.track.deck_id !== null && (
            <Link to={`/library?deck=${detail.track.deck_id}`}>{t('curriculum.deckLink')}</Link>
          )}
        </p>
      </section>

      {track.isPending && <p className="muted">{t('curriculum.loading')}</p>}
      {track.isError && <ErrorText error={track.error} />}

      {detail !== undefined && (
        <>
          {!detail.track.started && (
            <section className="card" aria-labelledby="track-start">
              <h2 id="track-start">{t('curriculum.notStartedTitle')}</h2>
              <p>{t('curriculum.notStarted')}</p>
              {!detail.track.available && (
                <p className="form-message form-message--warn" role="note">
                  {t('curriculum.wordlistMissing')}
                </p>
              )}
              <p>
                <button
                  type="button"
                  className="button button--primary"
                  disabled={!detail.track.available || start.isPending}
                  onClick={() => start.mutate(code)}
                >
                  {t('curriculum.startThis')}
                </button>
              </p>
              {start.isError && <ErrorText error={start.error} />}
            </section>
          )}

          <section aria-labelledby="track-units">
            <h2 id="track-units">{t('curriculum.unitsHeading', { count: detail.total_units })}</h2>
            <ul className="deck-list">
              {detail.units.map((row) => (
                <UnitItem key={row.number} track={detail.track} row={row} />
              ))}
            </ul>
            {pages > 1 && (
              <nav className="pager" aria-label={t('library.pager.label')}>
                <button
                  type="button"
                  className="button"
                  disabled={page === 0}
                  onClick={() => goTo(page - 1)}
                >
                  {t('library.pager.previous')}
                </button>
                <span>{t('library.pager.page', { page: page + 1, pages })}</span>
                <button
                  type="button"
                  className="button"
                  disabled={page + 1 >= pages}
                  onClick={() => goTo(page + 1)}
                >
                  {t('library.pager.next')}
                </button>
              </nav>
            )}
          </section>
        </>
      )}
    </div>
  )
}
