import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'

export interface Health {
  status: string
  version: string
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => apiGet<Health>('/health', { signal }),
    refetchInterval: 30_000,
  })
}
