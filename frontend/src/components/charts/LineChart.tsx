import { useId } from 'react'
import { useTranslation } from 'react-i18next'

export interface LineSeries {
  id: string
  label: string
  /** One value per x label; null is a gap (no data), never a zero. */
  values: (number | null)[]
  dashed?: boolean
}

interface LineChartProps {
  title: string
  /** One label per point: the first column of the table. */
  xLabels: string[]
  /** Shorter labels for the axis (the table keeps the long ones); defaults to `xLabels`. */
  axisLabels?: string[]
  series: LineSeries[]
  /** Text of a value, for the axis and the table. */
  format: (value: number) => string
  /** Lower and upper bounds of the axis; the data decides when omitted. */
  min?: number
  max?: number
}

const WIDTH = 480
const HEIGHT = 220
const LEFT = 44
const RIGHT = 12
const TOP = 12
const BOTTOM = 28
const TICKS = 4
const MAX_X_LABELS = 4
const COLORS = 5

/** Runs of consecutive non-null points: a gap in the data breaks the line. */
function runs(points: (readonly [number, number] | null)[]) {
  const out: (readonly [number, number])[][] = []
  let current: (readonly [number, number])[] = []
  for (const point of points) {
    if (point === null) {
      if (current.length > 0) out.push(current)
      current = []
    } else {
      current.push(point)
    }
  }
  if (current.length > 0) out.push(current)
  return out
}

/**
 * A line chart in plain SVG (no library, D-279): scales with its container through the viewBox,
 * colours come from CSS tokens, and the same numbers are in a table under the chart, which is the
 * text alternative of the picture.
 */
export function LineChart({ title, xLabels, axisLabels, series, format, min, max }: LineChartProps) {
  const { t } = useTranslation()
  const titleId = useId()
  const all = series.flatMap((s) => s.values).filter((v): v is number => v !== null)
  const low = min ?? Math.min(0, ...all)
  const highData = all.length > 0 ? Math.max(...all) : 1
  const high = max ?? (highData > low ? highData : low + 1)
  const plotWidth = WIDTH - LEFT - RIGHT
  const plotHeight = HEIGHT - TOP - BOTTOM
  const x = (index: number) =>
    LEFT + (xLabels.length <= 1 ? plotWidth / 2 : (index / (xLabels.length - 1)) * plotWidth)
  const y = (value: number) => TOP + plotHeight - ((value - low) / (high - low)) * plotHeight
  const step = Math.max(1, Math.ceil(xLabels.length / MAX_X_LABELS))

  return (
    <figure className="chart">
      <figcaption id={titleId} className="chart__title">
        {title}
      </figcaption>
      {all.length === 0 ? (
        <p className="muted">{t('stats.chart.noPoints')}</p>
      ) : (
        <svg
          className="chart__svg"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-labelledby={titleId}
        >
          {Array.from({ length: TICKS + 1 }, (_, i) => {
            const value = low + ((high - low) * i) / TICKS
            return (
              <g key={i}>
                <line className="chart__grid" x1={LEFT} x2={WIDTH - RIGHT} y1={y(value)} y2={y(value)} />
                <text className="chart__tick" x={LEFT - 6} y={y(value)} textAnchor="end" dy="0.32em">
                  {format(value)}
                </text>
              </g>
            )
          })}
          {(axisLabels ?? xLabels).map((label, i) =>
            i % step === 0 ? (
              <text
                key={`${label}-${i}`}
                className="chart__tick"
                x={x(i)}
                y={HEIGHT - 8}
                textAnchor="middle"
              >
                {label}
              </text>
            ) : null,
          )}
          {series.map((s, index) => {
            const points = s.values.map((v, i) => (v === null ? null : ([x(i), y(v)] as const)))
            return (
              <g key={s.id} className={`chart__series chart__series--${index % COLORS}`}>
                {runs(points).map((run, r) => (
                  <polyline
                    key={r}
                    className={s.dashed === true ? 'chart__line chart__line--dashed' : 'chart__line'}
                    points={run.map(([px, py]) => `${px},${py}`).join(' ')}
                  />
                ))}
                {points.map((point, i) =>
                  point === null ? null : (
                    <circle key={i} className="chart__dot" cx={point[0]} cy={point[1]} r="3" />
                  ),
                )}
              </g>
            )
          })}
        </svg>
      )}
      <ul className="chart__legend">
        {series.map((s, index) => (
          <li key={s.id}>
            <span
              className={`chart__swatch chart__series--${index % COLORS}${s.dashed === true ? ' chart__swatch--dashed' : ''}`}
              aria-hidden="true"
            />
            {s.label}
          </li>
        ))}
      </ul>
      <details className="chart__data">
        <summary>{t('stats.chart.showData')}</summary>
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">{title}</caption>
            <thead>
              <tr>
                <th scope="col">{t('stats.chart.period')}</th>
                {series.map((s) => (
                  <th key={s.id} scope="col">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {xLabels.map((label, i) => (
                <tr key={`${label}-${i}`}>
                  <th scope="row">{label}</th>
                  {series.map((s) => {
                    const value = s.values[i]
                    return (
                      <td key={s.id}>
                        {value === null || value === undefined
                          ? t('stats.chart.noValue')
                          : format(value)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  )
}
