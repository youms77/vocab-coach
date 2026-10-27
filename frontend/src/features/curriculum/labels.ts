import type { Labels } from '../../api/curriculum'

/** The label in the interface language (the backend always sends both). */
export function labelIn(labels: Labels, language: string): string {
  return language.startsWith('fr') ? labels.fr : labels.en
}
