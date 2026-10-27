import type { ReactNode } from 'react'

import { ICON_PATHS, type IconName } from './iconPaths'

export type { IconName }

export interface IconProps {
  name: IconName
  /** Pixel size of the square: 20 (navigation, tiles), 18 (buttons), 16 (small buttons). */
  size?: 16 | 18 | 20 | 24
  className?: string
}

export function Icon({ name, size = 20, className }: IconProps): ReactNode {
  return (
    <svg
      className={className === undefined ? 'icon' : `icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  )
}
