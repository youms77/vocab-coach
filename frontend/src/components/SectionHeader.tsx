import type { ReactNode } from 'react'

import { useActiveTheme } from '../useActiveTheme'
import { PageTitle } from './PageTitle'

/**
 * The tinted block that opens a section landing page: eyebrow, title, one sentence, the section's
 * actions as buttons (one primary, the others secondary) and an optional illustration. Working
 * screens never use it. The title takes the focus on arrival, like every page title. `illustration` holds one image per theme; the one of the active theme loads.
 */
export function SectionHeader({
  eyebrow,
  title,
  description,
  note,
  actions,
  illustration,
}: {
  eyebrow: string
  title: string
  description: string
  /** Extra lines under the sentence (the demo flag, the date of the figures...). */
  note?: ReactNode
  actions?: ReactNode
  illustration?: { light: string; dark: string }
}) {
  const theme = useActiveTheme()
  return (
    <header className="section-header">
      <div className="section-header__body">
        <span className="section-header__eyebrow">{eyebrow}</span>
        <PageTitle className="section-header__title">{title}</PageTitle>
        <p className="section-header__text">{description}</p>
        {note}
        {actions !== undefined && <div className="section-header__actions">{actions}</div>}
      </div>
      {illustration !== undefined && (
        <div className="section-header__art">
          <img src={illustration[theme]} alt="" />
        </div>
      )}
    </header>
  )
}
