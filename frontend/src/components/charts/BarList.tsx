export interface BarItem {
  id: string
  label: string
  /** 0..1 share of the full bar; null draws no bar (no data). */
  fraction: number | null
  /** The value as text: what a screen reader reads, and what is shown next to the bar. */
  text: string
}

/** Horizontal bars as a list: the label and the value are text, the bar only repeats them. */
export function BarList({ items }: { items: BarItem[] }) {
  return (
    <ul className="bar-list">
      {items.map((item) => (
        <li key={item.id} className="bar-list__row">
          <span className="bar-list__label">{item.label}</span>
          <span className="bar-list__track" aria-hidden="true">
            {item.fraction !== null && (
              <span
                className="bar-list__bar"
                style={{ width: `${Math.round(Math.min(1, Math.max(0, item.fraction)) * 100)}%` }}
              />
            )}
          </span>
          <span className="bar-list__value">{item.text}</span>
        </li>
      ))}
    </ul>
  )
}
