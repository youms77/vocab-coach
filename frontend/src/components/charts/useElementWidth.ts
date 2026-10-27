import { type RefObject, useEffect, useState } from 'react'

/**
 * The rendered width of an element, kept up to date (ResizeObserver). A chart drawn at this width
 * is not scaled by the browser, so its labels keep their real size on a phone (D-293). Where the
 * observer does not exist (tests), `fallback` is used.
 */
export function useElementWidth(ref: RefObject<HTMLElement | null>, fallback: number): number {
  const [width, setWidth] = useState(fallback)

  useEffect(() => {
    const element = ref.current
    if (element === null || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0)
      if (next > 0) setWidth(next)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])

  return width
}
