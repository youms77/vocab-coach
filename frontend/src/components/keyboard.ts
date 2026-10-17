/**
 * Page shortcuts (triage keys, review keys) are ignored while the user types in a field. Radios,
 * checkboxes and buttons do not take text, so shortcuts still work when they have the focus.
 */
export function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  // `isContentEditable` is not implemented by jsdom: the attribute is read as well.
  const editable = target.closest('[contenteditable]:not([contenteditable="false"])') !== null
  if (target.isContentEditable || editable) return true
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true
  if (target instanceof HTMLInputElement) return !['radio', 'checkbox', 'button'].includes(target.type)
  return false
}

/** Ctrl, Alt or Meta held: the key belongs to the browser or the system, not to the page. */
export function hasCommandModifier(event: KeyboardEvent): boolean {
  return event.ctrlKey || event.altKey || event.metaKey
}
