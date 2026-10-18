import { useTranslation } from 'react-i18next'

import { categoryLabels, labelOf, useErrorCategories } from '../../api/errors'

/**
 * A function from a category code to its label in the interface language. While the tree is
 * loading, or when the request fails or the code is unknown, the code itself is returned.
 */
export function useCategoryName(): (code: string) => string {
  const { i18n } = useTranslation()
  const tree = useErrorCategories()
  const byCode = tree.data !== undefined ? categoryLabels(tree.data) : null
  return (code) => {
    const node = byCode?.get(code)
    return node !== undefined ? labelOf(node, i18n.language) : code
  }
}
