import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'

import { ApiError } from '../../api/client'
import {
  useRegenerateSheet,
  useRunEnrichment,
  useSheet,
  useSheetVersions,
  type RunReport,
  type SheetVersion,
} from '../../api/enrichment'
import type { ItemDetail, ItemStatus } from '../../api/library'
import { ErrorText } from '../settings/ErrorText'
import { ExercisesPanel } from './ExercisesPanel'
import { SheetEditor } from './SheetEditor'
import { ShadowLink, SheetView } from './SheetView'
import { Notice } from '../../components/Notice'

// Before discovery (module B), the sheet is the answer the user is asked to guess.
const UNDISCOVERED: readonly ItemStatus[] = ['draft', 'triage', 'queued']

function formatDate(iso: string, language: string): string {
  return new Intl.DateTimeFormat(language, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  )
}

type Tone = 'ok' | 'warn'

/** What a run (generation or regeneration) did to this one term. */
function runMessage(t: TFunction, report: RunReport, regenerate: boolean) {
  const reason = t(`aiReasons.${report.reason ?? 'all_failed'}`)
  let text: string
  let tone: Tone = 'warn'
  if (report.generated > 0) {
    text = regenerate ? t('sheet.regenerated') : t('sheet.generated')
    tone = 'ok'
  } else if (report.superseded > 0) {
    text = t('sheet.superseded')
  } else if (report.needs_completion > 0) {
    text = t('sheet.skeleton')
  } else if (regenerate || report.status === 'unavailable') {
    text = regenerate ? t('sheet.regenerateFailed', { reason }) : t('sheet.aiUnavailable', { reason })
  } else {
    text = t('sheet.nothingToDo')
  }
  return { text, tone }
}

function RunMessage({ report, regenerate }: { report: RunReport; regenerate: boolean }) {
  const { t } = useTranslation()
  const { text, tone } = runMessage(t, report, regenerate)
  return (
    <p className={`form-message form-message--${tone}`} role="status">
      {text}
    </p>
  )
}

function Provenance({ sheet }: { sheet: SheetVersion }) {
  const { t, i18n } = useTranslation()
  const date = formatDate(sheet.edited_at ?? sheet.created_at, i18n.language)
  if (sheet.edited_by_user) return <>{t('sheet.editedOn', { date })}</>
  if (sheet.provider === null) return <>{t('sheet.manualOn', { date })}</>
  return (
    <>
      {t('sheet.madeBy', {
        provider: sheet.provider,
        model: sheet.model ?? '?',
        prompt: sheet.prompt_version ?? '?',
        date,
      })}
    </>
  )
}

/** Regeneration, with the user's explicit consent when the sheet was edited (409 `sheet_edited`). */
function Regenerate({ itemId }: { itemId: number }) {
  const { t } = useTranslation()
  const regenerate = useRegenerateSheet(itemId)
  const [consent, setConsent] = useState(false)
  const needsConsent =
    regenerate.error instanceof ApiError && regenerate.error.code === 'sheet_edited'

  return (
    <>
      {!consent && (
        <button
          type="button"
          className="button"
          disabled={regenerate.isPending}
          onClick={() => regenerate.mutate(false)}
        >
          {regenerate.isPending ? t('sheet.working') : t('sheet.regenerate')}
        </button>
      )}
      {needsConsent && !consent && (
        <div className="confirm" role="alertdialog" aria-label={t('sheet.consentTitle')}>
          <p>{t('sheet.consent')}</p>
          <button
            type="button"
            className="button button--danger"
            onClick={() => {
              setConsent(true)
              regenerate.mutate(true, { onSettled: () => setConsent(false) })
            }}
          >
            {t('sheet.consentYes')}
          </button>
          <button type="button" className="button" onClick={() => regenerate.reset()}>
            {t('sheet.consentNo')}
          </button>
        </div>
      )}
      {consent && <p className="muted">{t('sheet.working')}</p>}
      {regenerate.isError && !needsConsent && <ErrorText error={regenerate.error} />}
      {regenerate.isSuccess && <RunMessage report={regenerate.data} regenerate />}
    </>
  )
}

/** Generation for a term without a complete sheet (`POST /enrichment/run {item_ids}`). */
function Generate({ itemId, again }: { itemId: number; again: boolean }) {
  const { t } = useTranslation()
  const run = useRunEnrichment()
  return (
    <>
      <button
        type="button"
        className="button"
        disabled={run.isPending}
        onClick={() => run.mutate({ item_ids: [itemId] })}
      >
        {run.isPending ? t('sheet.working') : again ? t('sheet.tryAgain') : t('sheet.generate')}
      </button>
      {run.isError && <ErrorText error={run.error} />}
      {run.isSuccess && <RunMessage report={run.data} regenerate={false} />}
    </>
  )
}

function Versions({ itemId }: { itemId: number }) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const [shown, setShown] = useState<number | null>(null)
  const versions = useSheetVersions(itemId, open)

  return (
    <div className="sheet-versions">
      <button
        type="button"
        className="button button--small"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? t('sheet.versions.hide') : t('sheet.versions.show')}
      </button>
      {open && versions.isPending && <p className="muted">{t('library.loading')}</p>}
      {open && versions.isError && <ErrorText error={versions.error} />}
      {open && versions.isSuccess && (
        <ul className="version-list">
          {versions.data.map((v) => (
            <li key={v.enrichment_id}>
              <p>
                <strong>{t('sheet.versions.version', { version: v.version })}</strong> ·{' '}
                {formatDate(v.created_at, i18n.language)} ·{' '}
                {v.edited_by_user ? t('sheet.versions.byYou') : t('sheet.versions.byAi')}
                {v.is_current && <span className="badge">{t('sheet.versions.current')}</span>}{' '}
                <button
                  type="button"
                  className="button button--small"
                  aria-expanded={shown === v.enrichment_id}
                  onClick={() => setShown(shown === v.enrichment_id ? null : v.enrichment_id)}
                >
                  {shown === v.enrichment_id
                    ? t('sheet.versions.close')
                    : t('sheet.versions.open', { version: v.version })}
                </button>
              </p>
              {shown === v.enrichment_id && <SheetView sheet={v.content} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

type Mode = { kind: 'view' } | { kind: 'edit'; base: SheetVersion | null; key: number }

function SheetBody({ item }: { item: ItemDetail }) {
  const { t } = useTranslation()
  const sheet = useSheet(item.id)
  const [mode, setMode] = useState<Mode>({ kind: 'view' })
  const [saved, setSaved] = useState(false)

  if (sheet.isPending) return <p className="muted">{t('library.loading')}</p>
  if (sheet.isError) return <ErrorText error={sheet.error} />

  // The editor keeps the version it started from, even if the sheet is refetched meanwhile.
  const edit = (base: SheetVersion | null) => {
    setSaved(false)
    setMode({ kind: 'edit', base, key: Date.now() })
  }
  if (mode.kind === 'edit') {
    return (
      <SheetEditor
        key={mode.key}
        itemId={item.id}
        base={mode.base}
        partOfSpeech={item.part_of_speech}
        onSaved={() => {
          setSaved(true)
          setMode({ kind: 'view' })
        }}
        onCancel={() => setMode({ kind: 'view' })}
        onReload={() => void sheet.refetch().then((fresh) => edit(fresh.data ?? null))}
      />
    )
  }

  const current = sheet.data
  if (current === null) {
    return (
      <>
        <p>{t('sheet.none')}</p>
        <div className="confirm">
          <button type="button" className="button button--primary" onClick={() => edit(null)}>
            {t('sheet.writeByHand')}
          </button>
          <Generate itemId={item.id} again={false} />
        </div>
      </>
    )
  }

  const incomplete = current.sheet_status === 'needs_completion'
  return (
    <>
      <p className="muted">
        <span className="badge">{t(`library.sheet.${current.sheet_status}`)}</span>{' '}
        {t('sheet.versions.version', { version: current.version })} · <Provenance sheet={current} />
      </p>
      {saved && (
        <Notice tone="success" role="status">
          {t('sheet.saved')}
        </Notice>
      )}
      {incomplete && <Notice tone="warning">{t('sheet.needsCompletion')}</Notice>}
      {item.origin_sentence !== null && item.origin_sentence.trim() !== '' && (
        <p className="sheet-origin">
          <strong>{t('sheet.originSentence')}</strong> <span lang="en">“{item.origin_sentence}”</span>{' '}
          <ShadowLink
            sentence={item.origin_sentence.trim()}
            itemId={item.id}
            what={t('sheet.originLabel')}
          />
        </p>
      )}
      <SheetView sheet={current.content} shadowItemId={item.id} />
      <div className="confirm">
        <button type="button" className="button button--primary" onClick={() => edit(current)}>
          {incomplete ? t('sheet.complete') : t('sheet.edit')}
        </button>
        {incomplete ? <Generate itemId={item.id} again /> : <Regenerate itemId={item.id} />}
      </div>
      <Versions itemId={item.id} />
    </>
  )
}

/**
 * The usage sheet and exercises of a term, hidden until the user asks (owner's decision, M3.c3):
 * before discovery the sheet gives away the answer of module B.
 */
export function SheetCard({ item }: { item: ItemDetail }) {
  const { t } = useTranslation()
  const [shown, setShown] = useState(false)
  const undiscovered = UNDISCOVERED.includes(item.status)

  return (
    <section className="card" aria-labelledby="sheet-title">
      <h2 id="sheet-title">{t('sheet.title')}</h2>
      {!shown && (
        <>
          <p className="muted">{t('sheet.hidden')}</p>
          {undiscovered && (
            <Notice tone="warning">{t('sheet.spoiler')}</Notice>
          )}
        </>
      )}
      <button
        type="button"
        className="button"
        aria-expanded={shown}
        onClick={() => setShown(!shown)}
      >
        {shown ? t('sheet.hide') : t('sheet.show')}
      </button>
      {shown && (
        <>
          <SheetBody item={item} />
          <ExercisesPanel itemId={item.id} />
        </>
      )}
    </section>
  )
}
