import type { ReactNode } from 'react'

export type Tone = 'brand' | 'success' | 'warning' | 'danger' | 'neutral'

/** A short status label. Always a word: the colour only repeats it (D-087). */
export function Badge({ tone = 'brand', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge badge--${tone}`}>{children}</span>
}
