import type { ReactNode } from 'react'

import { Icon, type IconName } from './Icon'

export type NoticeTone = 'info' | 'warning' | 'danger' | 'success'

const ICONS: Record<NoticeTone, IconName> = {
  info: 'info',
  warning: 'errors',
  danger: 'circle-x',
  success: 'circle-check',
}

/** A message inside a page. The icon and the words carry the meaning, not the colour alone. */
export function Notice({
  tone = 'info',
  role,
  children,
}: {
  tone?: NoticeTone
  role?: 'status' | 'alert'
  children: ReactNode
}) {
  return (
    <div className={`notice notice--${tone}`} role={role}>
      <Icon name={ICONS[tone]} size={18} />
      <div className="notice__body">{children}</div>
    </div>
  )
}
