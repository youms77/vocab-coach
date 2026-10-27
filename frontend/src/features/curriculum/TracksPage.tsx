import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

import { type TrackSummary, useStartTrack, useTracks } from '../../api/curriculum'
import { PageTitle } from '../../components/PageTitle'
import { ErrorText } from '../settings/ErrorText'
import { labelIn } from './labels'

const LICENCE_URL = 'https://www.newgeneralservicelist.com'

function TrackCard({ track }: { track: TrackSummary }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const start = useStartTrack()
  const title = labelIn(track.title, i18n.language)
  const scenarios = track.kind === 'scenarios'

  return (
    <li className="card track-card">
      <h2>{title}</h2>
      <p className="muted">{t(`curriculum.kind.${track.kind}`)}</p>
      <p>{labelIn(track.description, i18n.language)}</p>
      <p className="track-card__counts">
        {t('curriculum.units', { count: track.unit_count })}
        {track.started && (
          <>
            {' · '}
            {scenarios
              ? t('curriculum.writtenCount', { count: track.opened_units })
              : t('curriculum.openedCount', {
                  opened: track.opened_units,
                  triaged: track.triaged_units,
                })}
          </>
        )}
      </p>
      {!track.available && (
        <p className="form-message form-message--warn" role="note">
          {t('curriculum.wordlistMissing')}
        </p>
      )}
      <p className="link-row">
        {track.started ? (
          <Link
            to={`/curriculum/${track.code}`}
            className="button button--primary"
            aria-label={t('curriculum.continueNamed', { title })}
          >
            {t('curriculum.continue')}
          </Link>
        ) : (
          <button
            type="button"
            className="button button--primary"
            disabled={!track.available || start.isPending}
            aria-label={t('curriculum.startNamed', { title })}
            onClick={() =>
              start.mutate(track.code, {
                onSuccess: () => void navigate(`/curriculum/${track.code}`),
              })
            }
          >
            {t('curriculum.start')}
          </button>
        )}
        {track.started && track.deck_id !== null && (
          <Link to={`/library?deck=${track.deck_id}`}>{t('curriculum.deckLink')}</Link>
        )}
      </p>
      {start.isError && <ErrorText error={start.error} />}
    </li>
  )
}

/** `/curriculum`: one card per general English track (module H). */
export function TracksPage() {
  const { t } = useTranslation()
  const tracks = useTracks()
  const hasWordlists = tracks.data?.some((track) => track.source !== null) ?? false

  return (
    <div className="curriculum-page">
      <section className="hero">
        <PageTitle>{t('curriculum.title')}</PageTitle>
        <p className="muted">{t('curriculum.intro')}</p>
      </section>
      {tracks.isPending && <p className="muted">{t('curriculum.loading')}</p>}
      {tracks.isError && <ErrorText error={tracks.error} />}
      {tracks.data !== undefined && (
        <ul className="track-list">
          {tracks.data.map((track) => (
            <TrackCard key={track.code} track={track} />
          ))}
        </ul>
      )}
      {hasWordlists && (
        <p className="muted field-hint">
          {t('curriculum.licence')}{' '}
          <a href={LICENCE_URL} target="_blank" rel="noreferrer noopener">
            newgeneralservicelist.com
          </a>
        </p>
      )}
    </div>
  )
}
