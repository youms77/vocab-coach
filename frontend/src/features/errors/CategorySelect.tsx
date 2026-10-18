import { useTranslation } from 'react-i18next'

import { type CategoryNode, labelOf } from '../../api/errors'

interface Option {
  code: string
  label: string
  depth: number
  status: string
}

/** The tree flattened, parents before children. `keep` filters the nodes (and so their subtrees). */
function flatten(
  nodes: CategoryNode[],
  keep: (node: CategoryNode) => boolean,
  language: string,
  depth = 0,
): Option[] {
  const out: Option[] = []
  for (const node of nodes) {
    if (!keep(node)) continue
    out.push({ code: node.code, label: labelOf(node, language), depth, status: node.status })
    out.push(...flatten(node.children, keep, language, depth + 1))
  }
  return out
}

const INDENT = '   '

/**
 * A native `<select>` of the error categories, the tree flattened and indented.
 *
 * `filter`: active and proposed categories (a rejected one holds no error) and a first option for
 * "all"; a top-level category stands for all of its subcategories (the backend filters by code
 * prefix). `assign`: active categories only, which is what the backend accepts; `current` keeps
 * the category of an error visible even when it is only proposed, so the form can show it.
 */
export function CategorySelect({
  id,
  tree,
  value,
  onChange,
  mode,
  current,
  required = false,
  placeholder,
}: {
  id: string
  tree: CategoryNode[]
  value: string
  onChange: (code: string) => void
  mode: 'filter' | 'assign'
  current?: { code: string; label_en: string; label_fr: string; status: string }
  required?: boolean
  /** The text of the empty option, when it is not "All categories" / "Choose a category". */
  placeholder?: string
}) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const options = flatten(
    tree,
    mode === 'filter' ? (n) => n.status !== 'rejected' : (n) => n.status === 'active',
    language,
  )
  const known = options.some((option) => option.code === value)

  function text(option: Option): string {
    const indent = INDENT.repeat(option.depth)
    if (mode === 'filter') {
      if (option.depth === 0) return t('errorLog.filters.wholeCategory', { label: option.label })
      if (option.status === 'proposed') {
        return `${indent}${t('errorLog.filters.proposed', { label: option.label })}`
      }
    }
    return `${indent}${option.label}`
  }

  return (
    <select
      id={id}
      value={value}
      required={required}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">
        {placeholder ??
          (mode === 'filter'
            ? t('errorLog.filters.allCategories')
            : t('errorLog.manual.chooseCategory'))}
      </option>
      {/* A category that is not in the list (proposed, or not loaded yet) stays selectable as is. */}
      {!known && value !== '' && (
        <option value={value}>
          {current !== undefined && current.code === value ? labelOf(current, language) : value}
        </option>
      )}
      {options.map((option) => (
        <option key={option.code} value={option.code}>
          {text(option)}
        </option>
      ))}
    </select>
  )
}
