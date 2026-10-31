import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { BackupStatus } from '../../api/backup'
import type { SettingsMap } from '../../api/settings'
import { apiErrorResponse, mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

function setting(value: number | string, extra: Partial<SettingsMap[string]> = {}) {
  return {
    value,
    default: typeof value === 'string' ? '' : 10,
    is_default: true,
    type: typeof value === 'string' ? 'str' : 'int',
    minimum: null,
    maximum: null,
    choices: null,
    item_choices: null,
    ...extra,
  } as SettingsMap[string]
}

const settings: SettingsMap = {
  backup_auto_folder: setting(''),
  backup_auto_keep: setting(10, { minimum: 1, maximum: 60 }),
}

function status(overrides: Partial<BackupStatus> = {}): BackupStatus {
  return {
    auto_folder_configured: false,
    last_auto_at: null,
    last_auto_error: null,
    last_manual_at: null,
    keep: 10,
    demo: false,
    ...overrides,
  }
}

function routes(current: BackupStatus, extra: Record<string, object | (() => Response)> = {}) {
  return {
    'GET /health': { status: 'ok', version: '0.1.0', demo: current.demo },
    'GET /ai/status': { ai_off: false, degraded: false, demo: current.demo, order: [], providers: [] },
    'GET /ai/usage': { days: [] },
    'GET /settings': settings,
    'GET /backup/status': current,
    ...extra,
  }
}

/** The card, once its status and the settings are loaded (the form and the copy button are there). */
async function card() {
  const backup = await screen.findByRole('region', { name: 'Backup' })
  await within(backup).findByRole('button', { name: 'Make a copy now' })
  await within(backup).findByLabelText('Folder for automatic copies')
  return backup
}

afterEach(() => vi.restoreAllMocks())

describe('BackupCard', () => {
  it('warns that the archive holds personal data and no key, and shows the restore commands', async () => {
    mockApi(routes(status()))
    renderApp('/settings')
    const backup = await card()
    expect(within(backup).getByText(/no AI key/)).toBeInTheDocument()
    expect(within(backup).getByText(/Stop the app first/)).toBeInTheDocument()
    expect(backup).toHaveTextContent('backup restore <backup.zip> --replace --yes')
    expect(within(backup).getByRole('button', { name: 'Make a copy now' })).toBeDisabled()
  })

  it('downloads a backup with a POST and keeps the server file name', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    URL.createObjectURL = vi.fn(() => 'blob:test')
    URL.revokeObjectURL = vi.fn()
    const calls = mockApi(
      routes(status(), {
        'POST /backup': () =>
          new Response('zip', {
            headers: {
              'Content-Type': 'application/zip',
              'Content-Disposition': 'attachment; filename="vocab-coach-backup-20261027-120000.zip"',
            },
          }),
      }),
    )
    renderApp('/settings')
    const backup = await card()
    await userEvent.click(within(backup).getByRole('button', { name: 'Download a backup' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    expect(calls.some((c) => c.method === 'POST' && c.path === '/backup')).toBe(true)
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('saves the folder and the number of copies, and says why a folder is refused', async () => {
    const calls = mockApi(
      routes(status(), {
        'PATCH /settings': () => apiErrorResponse(422, 'invalid_setting', 'no', {
          key: 'backup_auto_folder',
          reason: 'not_found',
        }),
      }),
    )
    renderApp('/settings')
    const backup = await card()
    const save = within(backup).getByRole('button', { name: 'Save' })
    expect(save).toBeDisabled()
    await userEvent.type(within(backup).getByLabelText('Folder for automatic copies'), 'C:/nowhere')
    await userEvent.clear(within(backup).getByLabelText('Copies to keep'))
    await userEvent.type(within(backup).getByLabelText('Copies to keep'), '5')
    await userEvent.click(save)
    expect(await within(backup).findByText('This folder does not exist.')).toBeInTheDocument()
    const patch = calls.find((c) => c.method === 'PATCH')
    expect(patch?.body).toEqual({ backup_auto_folder: 'C:/nowhere', backup_auto_keep: 5 })
  })

  it('refuses a number of copies out of range without calling the server', async () => {
    const calls = mockApi(routes(status()))
    renderApp('/settings')
    const backup = await card()
    await userEvent.type(within(backup).getByLabelText('Folder for automatic copies'), 'C:/x')
    await userEvent.clear(within(backup).getByLabelText('Copies to keep'))
    await userEvent.type(within(backup).getByLabelText('Copies to keep'), '99')
    expect(within(backup).getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
  })

  it('shows the last copy and the last error in words, and runs a copy now', async () => {
    const configured = status({
      auto_folder_configured: true,
      last_auto_at: '2026-10-27T10:00:00.000000Z',
      last_auto_error: 'file_locked',
    })
    const after = status({ auto_folder_configured: true, last_auto_at: '2026-10-27T11:00:00.000000Z' })
    const calls = mockApi(routes(configured, { 'POST /backup/auto/run': after }))
    renderApp('/settings')
    const backup = await card()
    expect(await within(backup).findByText(/another program/)).toBeInTheDocument()
    expect(backup.textContent).not.toContain('file_locked')
    await userEvent.click(within(backup).getByRole('button', { name: 'Make a copy now' }))
    await waitFor(() => expect(within(backup).queryByText(/another program/)).toBeNull())
    expect(calls.some((c) => c.method === 'POST' && c.path === '/backup/auto/run')).toBe(true)
  })

  it('locks the automatic copy on the demo database', async () => {
    mockApi(routes(status({ demo: true, auto_folder_configured: true })))
    renderApp('/settings')
    const backup = await card()
    expect(await within(backup).findByText(/Demo database: the automatic copy is off/)).toBeInTheDocument()
    expect(within(backup).getByLabelText('Folder for automatic copies')).toBeDisabled()
    expect(within(backup).getByRole('button', { name: 'Make a copy now' })).toBeDisabled()
    expect(within(backup).getByRole('button', { name: 'Download a backup' })).toBeEnabled()
  })
})
