import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'

export interface Health {
  status: string
  version: string
  /** True when the backend serves the generated demo database. */
  demo?: boolean
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => apiGet<Health>('/health', { signal }),
    refetchInterval: 30_000,
  })
}
