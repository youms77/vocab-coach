import { Fragment } from 'react'

/** A category code such as `grammar.preposition`: it breaks after a dot, never inside a word. */
export function CategoryCode({ code }: { code: string }) {
  const parts = code.split('.')
  return (
    <code className="category-code">
      {parts.map((part, index) => (
        <Fragment key={index}>
          {index > 0 && <wbr />}
          {index < parts.length - 1 ? `${part}.` : part}
        </Fragment>
      ))}
    </code>
  )
}
