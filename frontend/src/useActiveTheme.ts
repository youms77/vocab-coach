import { useSyncExternalStore } from 'react'

const DARK_QUERY = '(prefers-color-scheme: dark)'

/** The theme in effect: the one picked in the selector, else the operating system's (D-007). */
function read(): 'light' | 'dark' {
  const picked = document.documentElement.dataset.theme
  if (picked === 'light' || picked === 'dark') return picked
  return typeof window.matchMedia === 'function' && window.matchMedia(DARK_QUERY).matches
    ? 'dark'
    : 'light'
}

function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  const query = typeof window.matchMedia === 'function' ? window.matchMedia(DARK_QUERY) : null
  query?.addEventListener('change', onChange)
  return () => {
    observer.disconnect()
    query?.removeEventListener('change', onChange)
  }
}

/** For what CSS cannot switch by itself, such as which illustration to load. */
export function useActiveTheme(): 'light' | 'dark' {
  return useSyncExternalStore(subscribe, read, () => 'light')
}
