import type { ReactNode } from 'react'

/**
 * Learning content (a term, an example sentence, a text to correct) is English whatever the
 * interface language is: `lang="en"` lets a screen reader pronounce it in English (M10.c1, D-326).
 */
export function English({ children }: { children: ReactNode }) {
  return <span lang="en">{children}</span>
}
