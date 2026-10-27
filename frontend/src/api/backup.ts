import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiDownload, apiSend, apiGet } from './client'

export interface BackupStatus {
  auto_folder_configured: boolean
  last_auto_at: string | null
  last_auto_error: string | null
  last_manual_at: string | null
  keep: number
  demo: boolean
}

export const backupStatusKey = ['backup', 'status'] as const

export function useBackupStatus() {
  return useQuery({
    queryKey: backupStatusKey,
    queryFn: ({ signal }) => apiGet<BackupStatus>('/backup/status', { signal }),
  })
}

/** Downloads a full backup (`POST /api/backup`, the file name comes from the server). */
export function useBackupDownload() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiDownload('/backup', 'vocab-coach-backup.zip', 'POST'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: backupStatusKey }),
  })
}

/** Makes the automatic copy now; the answer is the new status (a failed copy is in it). */
export function useRunAutoBackup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<BackupStatus>('POST', '/backup/auto/run'),
    onSuccess: (status) => queryClient.setQueryData(backupStatusKey, status),
  })
}
