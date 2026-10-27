import type { ReactNode } from 'react'

import { useActiveTheme } from '../useActiveTheme'

/**
 * The tinted block that opens a section landing page: eyebrow, title, one sentence, the section's
 * actions as buttons (one primary, the others secondary) and an optional illustration. Working
 * screens never use it. `illustration` holds one image per theme; the one of the active theme loads.
 */
export function SectionHeader({
  eyebrow,
  title,
  description,
  actions,
  illustration,
}: {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
  illustration?: { light: string; dark: string }
}) {
  const theme = useActiveTheme()
  return (
    <header className="section-header">
      <div className="section-header__body">
        <span className="section-header__eyebrow">{eyebrow}</span>
        <h1 className="section-header__title">{title}</h1>
        <p className="section-header__text">{description}</p>
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
