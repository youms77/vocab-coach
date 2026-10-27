import type { ReactNode } from 'react'

import { widthPercent } from './widthRef'

/** A big number with its label; the optional bar shows a share (0 to 1) of a budget or quota. */
export function StatTile({
  value,
  label,
  progress,
}: {
  value: ReactNode
  label: string
  progress?: number
}) {
  const percent =
    progress === undefined ? null : Math.round(Math.min(1, Math.max(0, progress)) * 100)
  return (
    <div className="stat-tile">
      <span className="stat-tile__value">{value}</span>
      <span className="stat-tile__label">{label}</span>
      {percent !== null && (
        <div
          className="progress-bar"
          role="progressbar"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
        >
          <div className="progress-bar__fill" ref={widthPercent(percent)} />
        </div>
      )}
    </div>
  )
}
