import { type ReactNode, useEffect, useRef } from 'react'

/** A step's title. Focus moves to it when the step appears, so screen readers announce it. */
export function StepHeading({ children, level = 2 }: { children: ReactNode; level?: 2 | 3 }) {
  const ref = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    ref.current?.focus()
  }, [])
  const Tag = level === 2 ? 'h2' : 'h3'
  return (
    <Tag ref={ref} tabIndex={-1} className="step-title">
      {children}
    </Tag>
  )
}
