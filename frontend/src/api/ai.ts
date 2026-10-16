import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './client'

/** Provider names, in the order the backend always lists them. */
export type ProviderName = 'gemini' | 'groq' | 'ollama'

/** Why a provider failed last (D-039 kinds). */
export type ProviderErrorKind =
  | 'rate_limited'
  | 'quota_exhausted'
  | 'transient'
  | 'network'
  | 'auth'
  | 'bad_request'
  | 'invalid_output'

export interface ProviderState {
  name: ProviderName
  capabilities: string[]
  configured: boolean
  /** In the provider order (a provider left out of the order is disabled). */
  enabled: boolean
  available: boolean
  cooldown_until: string | null
  misconfigured: boolean
  last_error: ProviderErrorKind | null
  models: Record<string, string>
  credential_source: 'env_file' | 'environment' | 'none'
  credential_kind: 'api_key' | 'base_url'
}

export interface AiStatus {
  ai_off: boolean
  degraded: boolean
  demo: boolean
  order: ProviderName[]
  providers: ProviderState[]
}

export type UnavailableReason =
  | 'no_provider_configured'
  | 'network'
  | 'quota'
  | 'auth'
  | 'timeout'
  | 'all_failed'

export interface ConnectionTestResult {
  provider: ProviderName
  status: 'ok' | 'incomplete' | 'unavailable'
  reason: UnavailableReason | null
  model: string | null
  elapsed_ms: number
  input_tokens: number | null
  output_tokens: number | null
  error_code: string | null
  http_status: number | null
  /** English, masked by the backend. */
  message: string | null
  detail_kind: 'none' | 'provider' | 'schema'
}

export interface UsageRow {
  provider: string
  model: string
  requests: number
  successes: number
  errors: Record<string, number>
  input_tokens: number
  output_tokens: number
  avg_duration_ms: number | null
}

export interface UsageDay {
  day: string
  requests: number
  successes: number
  input_tokens: number
  output_tokens: number
  rows: UsageRow[]
}

export interface AiUsage {
  /** Today first, empty days included. */
  days: UsageDay[]
}

export const aiStatusKey = ['ai', 'status'] as const
export const aiUsageKey = ['ai', 'usage'] as const

export function useAiStatus() {
  return useQuery({
    queryKey: aiStatusKey,
    queryFn: ({ signal }) => apiGet<AiStatus>('/ai/status', { signal }),
    // Cooldowns end on their own: keep the banner and the cards roughly current.
    refetchInterval: 30_000,
  })
}

export function useAiUsage(days = 7) {
  return useQuery({
    queryKey: [...aiUsageKey, days],
    queryFn: ({ signal }) => apiGet<AiUsage>(`/ai/usage?days=${days}`, { signal }),
  })
}

/** Saves (value) or removes (null) a provider's key or address in `.env`. */
export function useCredentialMutation(provider: ProviderName) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (value: string | null) =>
      value === null
        ? apiSend<ProviderState>('DELETE', `/ai/providers/${provider}/credential`)
        : apiSend<ProviderState>('PUT', `/ai/providers/${provider}/credential`, { value }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: aiStatusKey }),
  })
}

export function useConnectionTest(provider: ProviderName) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['ai', 'test', provider],
    mutationFn: () => apiSend<ConnectionTestResult>('POST', '/ai/test', { provider }),
    // A test changes health (cooldown, last error) and adds call-log rows.
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: aiStatusKey }),
        queryClient.invalidateQueries({ queryKey: aiUsageKey }),
      ]),
  })
}
