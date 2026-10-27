import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { type Period, type PracticeStats, useStatsPractice } from '../../api/stats'
import { BarList } from '../../components/charts/BarList'
import { LineChart } from '../../components/charts/LineChart'
import { bucketAxisLabel, bucketLabel } from './bucketLabels'
import { formatFullDay, formatNumber } from './format'
import { StatsSection } from './StatsSection'

const SPEECH_KINDS = [
  'writing',
  'speaking',
  'consolidation',
  'transcript_analysis',
  'drill',
  'shadowing',
] as const

function kindLabel(t: TFunction, kind: string): string {
  return (SPEECH_KINDS as readonly string[]).includes(kind)
    ? t(`stats.practice.kind.${kind as (typeof SPEECH_KINDS)[number]}`)
    : kind
}

function Content({ data }: { data: PracticeStats }) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const minutes = (seconds: number) => formatNumber(language, seconds / 60, 1)
  const count = (value: number) => formatNumber(language, value, 0)
  const { study_time: study, streaks } = data
  const speechMax = Math.max(1, ...Object.values(data.speech_by_kind))
  const kinds = Object.entries(data.speech_by_kind)

  return (
    <>
      <h3>{t('stats.practice.studyTitle')}</h3>
      <p className="stats-total">
        <strong>{t('stats.practice.studyTotal', { minutes: minutes(study.seconds) })}</strong>{' '}
        <span className="muted">
          {t('stats.practice.activeDays', { count: study.active_days })}
        </span>
      </p>
      <p className="muted field-hint">{t('stats.practice.studyNote')}</p>
      <LineChart
        title={t('stats.practice.studyChart')}
        xLabels={study.buckets.map((b) => bucketLabel(t, language, data.granularity, b))}
        axisLabels={study.buckets.map((b) => bucketAxisLabel(language, b))}
        series={[
          {
            id: 'study',
            label: t('stats.practice.studySeries'),
            values: study.buckets.map((b) => b.seconds / 60),
          },
          {
            id: 'session',
            label: t('stats.practice.sessionSeries'),
            values: study.buckets.map((b) => b.session_seconds / 60),
            dashed: true,
          },
        ]}
        format={(v) => formatNumber(language, v, 1)}
        min={0}
      />

      <h3>{t('stats.practice.streakTitle')}</h3>
      <ul className="stats-list">
        <li>{t('stats.practice.currentStreak', { count: streaks.current })}</li>
        <li>
          {t('stats.practice.longestStreak', { count: streaks.longest })}
          {streaks.longest_end !== null &&
            ` (${t('stats.practice.endedOn', { date: formatFullDay(language, streaks.longest_end) })})`}
        </li>
        <li>{t('stats.practice.activeLast30', { count: streaks.active_days_last_30 })}</li>
      </ul>

      <h3>{t('stats.practice.wordsTitle')}</h3>
      <p className="stats-total">
        <strong>{t('stats.practice.wordsWritten', { count: data.words_written })}</strong>
        {' · '}
        <strong>{t('stats.practice.wordsOral', { count: data.words_oral })}</strong>
      </p>
      <p className="muted field-hint">{t('stats.practice.wordsNote')}</p>
      <LineChart
        title={t('stats.practice.wordsChart')}
        xLabels={data.words.map((b) => bucketLabel(t, language, data.granularity, b))}
        axisLabels={data.words.map((b) => bucketAxisLabel(language, b))}
        series={[
          { id: 'written', label: t('stats.practice.writtenSeries'), values: data.words.map((b) => b.written) },
          { id: 'oral', label: t('stats.practice.oralSeries'), values: data.words.map((b) => b.oral) },
        ]}
        format={count}
        min={0}
      />

      <h3>{t('stats.practice.speechTitle')}</h3>
      <p className="stats-total">
        <strong>{t('stats.practice.speechTotal', { minutes: minutes(data.speech_seconds) })}</strong>
      </p>
      {kinds.length === 0 ? (
        <p className="muted">{t('stats.practice.speechEmpty')}</p>
      ) : (
        <BarList
          items={kinds.map(([kind, seconds]) => ({
            id: kind,
            label: kindLabel(t, kind),
            fraction: seconds / speechMax,
            text: t('stats.practice.minutes', { value: minutes(seconds) }),
          }))}
        />
      )}
      <LineChart
        title={t('stats.practice.speechChart')}
        xLabels={data.speech.map((b) => bucketLabel(t, language, data.granularity, b))}
        axisLabels={data.speech.map((b) => bucketAxisLabel(language, b))}
        series={[
          {
            id: 'speech',
            label: t('stats.practice.speechSeries'),
            values: data.speech.map((b) => b.seconds / 60),
          },
        ]}
        format={(v) => formatNumber(language, v, 1)}
        min={0}
      />
    </>
  )
}

export function PracticeSection({ period }: { period: Period | null }) {
  const { t } = useTranslation()
  const practice = useStatsPractice(period)
  return (
    <StatsSection
      id="practice"
      title={t('stats.practice.title')}
      intro={t('stats.practice.intro')}
      query={practice}
    >
      {(data) => <Content data={data} />}
    </StatsSection>
  )
}
