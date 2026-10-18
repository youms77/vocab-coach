import { type ReactNode, useEffect, useRef } from 'react'

/** The title of a new screen. Focus moves to it on arrival, so screen readers announce the screen. */
export function PageTitle({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    ref.current?.focus()
  }, [])
  return (
    <h1 ref={ref} tabIndex={-1} className="page-title">
      {children}
    </h1>
  )
}
