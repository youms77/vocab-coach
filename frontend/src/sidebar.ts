export const SIDEBAR_STORAGE_KEY = 'vocab-coach.sidebar'

/** The sidebar is expanded unless the user folded it (the choice is kept per browser). */
export function readSidebarCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'collapsed'
  } catch {
    return false
  }
}

export function storeSidebarCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? 'collapsed' : 'expanded')
  } catch {
    // Storage can be unavailable (private mode); the sidebar still folds for this visit.
  }
}
