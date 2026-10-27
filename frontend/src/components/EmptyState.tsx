import type { ReactNode } from 'react'

export type Illustration = 'books' | 'pencil' | 'chart'

/** Flat illustrations (style A): the `ia-*` classes take their colours from the theme tokens. */
function Art({ name }: { name: Illustration }) {
  return (
    <svg className="empty-state__art" viewBox="0 0 200 125" aria-hidden="true" focusable="false">
      <ellipse className="ia-blob" cx="100" cy="66" rx="86" ry="52" />
      {name === 'books' && (
        <>
          <rect className="ia-1" x="62" y="40" width="22" height="58" rx="3" />
          <rect className="ia-2" x="88" y="34" width="22" height="64" rx="3" />
          <rect className="ia-3" x="114" y="46" width="22" height="52" rx="3" />
          <rect className="ia-paper" x="68" y="50" width="10" height="3" rx="1.5" />
          <rect className="ia-paper" x="94" y="44" width="10" height="3" rx="1.5" />
          <path className="ia-leaf" d="M142 98c0-14 6-22 16-26-1 12-6 21-16 26z" />
        </>
      )}
      {name === 'pencil' && (
        <>
          <rect className="ia-paper" x="64" y="30" width="62" height="72" rx="5" />
          <path className="ia-line" d="M74 48h42M74 60h42M74 72h26" strokeWidth="3" strokeLinecap="round" />
          <path className="ia-acc" d="M120 96l4-16 26-26 12 12-26 26z" />
          <path className="ia-2" d="M150 54l6-6 12 12-6 6z" />
        </>
      )}
      {name === 'chart' && (
        <>
          <rect className="ia-paper" x="60" y="32" width="84" height="66" rx="5" />
          <rect className="ia-3" x="72" y="68" width="12" height="22" rx="2" />
          <rect className="ia-1" x="92" y="52" width="12" height="38" rx="2" />
          <rect className="ia-2" x="112" y="42" width="12" height="48" rx="2" />
          <circle className="ia-acc" cx="134" cy="40" r="5" />
        </>
      )}
    </svg>
  )
}

/** What a list shows when it has nothing yet: an illustration, an invitation, and the action that fills it. */
export function EmptyState({
  illustration,
  title,
  text,
  children,
}: {
  illustration: Illustration
  title: string
  text?: string
  children?: ReactNode
}) {
  return (
    <div className="empty-state">
      <Art name={illustration} />
      <h2 className="empty-state__title">{title}</h2>
      {text !== undefined && <p className="empty-state__text">{text}</p>}
      {children}
    </div>
  )
}
