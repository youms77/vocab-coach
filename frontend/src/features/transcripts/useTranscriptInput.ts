import { useRef, useState } from 'react'

import {
  codePoints,
  MAX_PASTED_CHARS,
  type TranscriptPreview,
  type UserDesignation,
  usePreviewTranscript,
} from '../../api/transcripts'

/**
 * The paste, its preview and the choice of "which turns are mine", shared by the paste page and
 * the "paste again" panel of the detail page. Nothing is stored: the text lives in this state.
 *
 * The preview belongs to the text it was made from: editing the text hides it (and the choice),
 * so what is saved or sent is always what was previewed.
 */
export function useTranscriptInput() {
  const [text, setTextState] = useState('')
  const [shown, setShown] = useState<{ text: string; preview: TranscriptPreview } | null>(null)
  const [chosen, setChosen] = useState<UserDesignation | null>(null)
  const mutation = usePreviewTranscript()
  const latest = useRef(0)

  const chars = codePoints(text)
  const tooLong = chars > MAX_PASTED_CHARS
  const empty = text.trim() === ''
  const preview = shown !== null && shown.text === text ? shown.preview : null
  const stale = shown !== null && preview === null

  function run(user?: UserDesignation) {
    if (empty || tooLong) return
    const sent = text
    latest.current += 1
    const request = latest.current
    mutation.mutate(user !== undefined ? { text: sent, user } : { text: sent }, {
      // An older answer must not overwrite a newer one.
      onSuccess: (data) => {
        if (latest.current === request) setShown({ text: sent, preview: data })
      },
    })
  }

  /** What the user (or the parser's suggestion) designated; null until there is a choice. */
  const user: UserDesignation | null = preview !== null ? (chosen ?? preview.designation) : null
  const blocked = preview?.problems.some((problem) => problem.severity === 'error') ?? false

  return {
    text,
    setText(value: string) {
      if (value !== text) setChosen(null)
      setTextState(value)
    },
    chars,
    tooLong,
    empty,
    preview,
    stale,
    pending: mutation.isPending,
    error: mutation.isError ? mutation.error : null,
    user,
    blocked,
    /** A preview of this very text, a designation and no blocking problem. */
    ready: preview !== null && user !== null && !blocked,
    /** "Preview": a first look, without a choice (the parser suggests a label when it can). */
    showPreview: () => {
      setChosen(null)
      run()
    },
    /** Changing the designation reads the text again with it. */
    choose(designation: UserDesignation) {
      setChosen(designation)
      run(designation)
    },
  }
}

export type TranscriptInput = ReturnType<typeof useTranscriptInput>
