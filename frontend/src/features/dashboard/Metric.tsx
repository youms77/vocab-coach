import type { ReactNode } from 'react'

/** One headline figure: a label, a value and, under it, the count or comparison behind it. */
export function Metric({
  label,
  children,
  detail,
}: {
  label: string
  children: ReactNode
  detail?: ReactNode
}) {
  return (
    <div className="stat">
      <dt className="stat__label">{label}</dt>
      <dd className="stat__value">{children}</dd>
      {detail !== undefined && <dd className="stat__detail muted">{detail}</dd>}
    </div>
  )
}
