import type { ReactNode } from 'react'

import { Icon } from './Icon'

/**
 * A mistake and its fix: the wrong fragment on the coral tint with a wavy underline, then the
 * correction on the green tint. Never the colour alone: the wavy underline, the arrow and (when
 * `labels` is given) the hidden words "Wrong" and "Right" say it too. Without a correction it is
 * only the wrong fragment.
 */
export function CorrectionMark({
  wrong,
  correction,
  labels,
}: {
  wrong: ReactNode
  correction?: string
  /** Hidden words read before each part by a screen reader; the arrow is then hidden. */
  labels?: { wrong: string; right: string }
}) {
  return (
    <>
      {labels !== undefined && <span className="visually-hidden">{labels.wrong}: </span>}
      <del className="correction-wrong">{wrong}</del>
      {correction !== undefined && (
        <>
          {labels === undefined ? (
            <> → </>
          ) : (
            <span className="correction-arrow" aria-hidden="true">
              <Icon name="arrow" size={16} />
            </span>
          )}
          {labels !== undefined && <span className="visually-hidden">{labels.right}: </span>}
          <ins className="correction-right">{correction}</ins>
        </>
      )}
    </>
  )
}
