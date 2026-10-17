import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { aiStatusKey } from './ai'
import { apiGet, apiSend } from './client'

export type SettingValue = number | string | string[]

export interface SettingInfo {
  value: SettingValue
  default: SettingValue
  is_default: boolean
  type: 'int' | 'float' | 'str' | 'list'
  minimum: number | null
  maximum: number | null
  choices: string[] | null
  item_choices: string[] | null
}

export type SettingsMap = Record<string, SettingInfo>

export const settingsKey = ['settings'] as const

export function useSettings() {
  return useQuery({
    queryKey: settingsKey,
    queryFn: ({ signal }) => apiGet<SettingsMap>('/settings', { signal }),
  })
}

/** Changes several settings at once; the backend applies all of them or none. */
export function useSettingsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: Record<string, SettingValue>) =>
      apiSend<SettingsMap>('PATCH', '/settings', changes),
    onSuccess: (settings, changes) => {
      queryClient.setQueryData(settingsKey, settings)
      if ('ai_provider_order' in changes) {
        return queryClient.invalidateQueries({ queryKey: aiStatusKey })
      }
    },
  })
}
