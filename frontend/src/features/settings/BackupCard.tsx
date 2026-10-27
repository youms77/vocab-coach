import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  useBackupDownload,
  useBackupStatus,
  useRunAutoBackup,
  type BackupStatus,
} from '../../api/backup'
import { ApiError } from '../../api/client'
import { type SettingsMap, useSettings, useSettingsMutation } from '../../api/settings'
import { Notice } from '../../components/Notice'
import { ErrorText } from './ErrorText'

const RESTORE_COMMANDS = [
  'cd backend',
  'uv run python -m app backup verify <backup.zip>',
  'uv run python -m app backup restore <backup.zip>',
  'uv run python -m app backup restore <backup.zip> --replace --yes',
]

function When({ iso }: { iso: string | null }) {
  const { t, i18n } = useTranslation()
  if (iso === null) return <>{t('settings.backup.never')}</>
  const format = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeStyle: 'short' })
  return <time dateTime={iso}>{format.format(new Date(iso))}</time>
}

function Status({ status }: { status: BackupStatus }) {
  const { t } = useTranslation()
  return (
    <div aria-live="polite">
      <dl className="backup-status">
        <dt>{t('settings.backup.lastAuto')}</dt>
        <dd>
          <When iso={status.last_auto_at} />
        </dd>
        <dt>{t('settings.backup.lastManual')}</dt>
        <dd>
          <When iso={status.last_manual_at} />
        </dd>
      </dl>
      {status.last_auto_error !== null && (
        <Notice tone="warning">
          {t('settings.backup.lastError', {
            reason: t(`settings.backup.errors.${status.last_auto_error}`, {
              defaultValue: t('settings.backup.errors.unknown'),
            }),
          })}
        </Notice>
      )}
    </div>
  )
}

function AutoForm({ settings, locked }: { settings: SettingsMap; locked: boolean }) {
  const { t } = useTranslation()
  const mutation = useSettingsMutation()
  const stored = {
    folder: String(settings.backup_auto_folder.value),
    keep: String(settings.backup_auto_keep.value),
  }
  const [folder, setFolder] = useState(stored.folder)
  const [keep, setKeep] = useState(stored.keep)
  const [saved, setSaved] = useState(false)
  const info = settings.backup_auto_keep

  const keepNumber = Number(keep)
  const keepOk =
    /^\d+$/.test(keep.trim()) &&
    keepNumber >= (info.minimum ?? 1) &&
    keepNumber <= (info.maximum ?? 60)
  const changed = folder.trim() !== stored.folder || keep.trim() !== stored.keep
  const reason =
    mutation.error instanceof ApiError && mutation.error.code === 'invalid_setting'
      ? mutation.error.detail.reason
      : undefined

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!keepOk || !changed) return
    setSaved(false)
    mutation.mutate(
      { backup_auto_folder: folder.trim(), backup_auto_keep: keepNumber },
      { onSuccess: () => setSaved(true) },
    )
  }

  return (
    <form className="settings-group" onSubmit={submit} noValidate>
      <fieldset disabled={locked}>
        <legend>{t('settings.backup.autoTitle')}</legend>
        <div className="field">
          <label htmlFor="backup-folder">{t('settings.backup.folder')}</label>
          <input
            id="backup-folder"
            type="text"
            value={folder}
            onChange={(event) => {
              setFolder(event.target.value)
              setSaved(false)
            }}
            spellCheck={false}
            autoComplete="off"
            aria-describedby="backup-folder-hint"
          />
          <p id="backup-folder-hint" className="muted field-hint">
            {t('settings.backup.folderHint')}
          </p>
          {typeof reason === 'string' && (
            <p className="form-message form-message--error">
              {t(`settings.backup.reasons.${reason}`, { defaultValue: t('errors.invalid_setting') })}
            </p>
          )}
        </div>
        <div className="field">
          <label htmlFor="backup-keep">{t('settings.backup.keep')}</label>
          <input
            id="backup-keep"
            type="number"
            inputMode="numeric"
            min={info.minimum ?? 1}
            max={info.maximum ?? 60}
            step={1}
            value={keep}
            onChange={(event) => {
              setKeep(event.target.value)
              setSaved(false)
            }}
            aria-invalid={!keepOk || undefined}
          />
          <p className="muted field-hint">
            {t('settings.general.range', { min: info.minimum ?? 1, max: info.maximum ?? 60 })}
          </p>
        </div>
      </fieldset>
      <button
        type="submit"
        className="button button--primary"
        disabled={locked || !changed || !keepOk || mutation.isPending}
      >
        {t('settings.general.save')}
      </button>
      <div aria-live="polite">
        {saved && !changed && <Notice tone="success">{t('settings.saved')}</Notice>}
      </div>
      {mutation.isError && typeof reason !== 'string' && <ErrorText error={mutation.error} />}
    </form>
  )
}

/** Module J: download a full backup, set the automatic copy, and how to restore (D-309). */
export function BackupCard() {
  const { t } = useTranslation()
  const status = useBackupStatus()
  const settings = useSettings()
  const download = useBackupDownload()
  const run = useRunAutoBackup()
  const demo = status.data?.demo === true

  return (
    <section className="card" aria-labelledby="backup-title" id="backup">
      <h2 id="backup-title">{t('settings.backup.title')}</h2>
      <p className="muted">{t('settings.backup.intro')}</p>
      <Notice tone="warning">{t('settings.backup.warning')}</Notice>
      <div className="link-row">
        <button
          type="button"
          className="button button--primary"
          disabled={download.isPending}
          onClick={() => download.mutate()}
        >
          {download.isPending ? t('settings.backup.downloading') : t('settings.backup.download')}
        </button>
      </div>
      {download.isError && <ErrorText error={download.error} />}

      {status.isPending && <p className="muted">{t('settings.loading')}</p>}
      {status.isError && (
        <>
          <Notice tone="danger">{t('settings.backup.loadError')}</Notice>
          <ErrorText error={status.error} />
        </>
      )}
      {status.isSuccess && (
        <>
          {demo && <Notice tone="info">{t('settings.backup.demoNote')}</Notice>}
          {settings.isSuccess && 'backup_auto_folder' in settings.data && (
            <AutoForm settings={settings.data} locked={demo} />
          )}
          <Status status={status.data} />
          <div className="link-row">
            <button
              type="button"
              className="button"
              disabled={demo || !status.data.auto_folder_configured || run.isPending}
              onClick={() => run.mutate()}
            >
              {run.isPending ? t('settings.backup.copying') : t('settings.backup.copyNow')}
            </button>
          </div>
          {run.isError && <ErrorText error={run.error} />}
        </>
      )}

      <h3>{t('settings.backup.restoreTitle')}</h3>
      <p>{t('settings.backup.restoreIntro')}</p>
      <Notice tone="warning">{t('settings.backup.restoreStop')}</Notice>
      <pre className="code-block" lang="en">
        <code>{RESTORE_COMMANDS.join('\n')}</code>
      </pre>
      <p className="muted">{t('settings.backup.restoreKeys')}</p>
    </section>
  )
}
