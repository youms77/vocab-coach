import type { UseQueryResult } from '@tanstack/react-query'
import type { TFunction } from 'i18next'

import { TOPIC_TAGS, type TopicTag, useWritingTopics } from '../../api/productions'

/** A suggested topic: the English text is what is sent, the French one is shown on demand. */
interface SuggestedTopic {
  id: string
  en: string
  fr: string
}

/** The translated strings of a picker: the writing page's and the speaking page's. */
export type PickerNamespace = 'writing.topics' | 'speaking.topics'

/** What differs between the writing page and the speaking page. */
export interface TopicSource {
  ns: PickerNamespace
  tags: readonly string[]
  tagLabel: (t: TFunction, tag: string) => string
  /** A hook: called on every render, so it must always be the same function. */
  useTopics: (tag: string) => UseQueryResult<SuggestedTopic[]>
}

export const WRITING_TOPICS: TopicSource = {
  ns: 'writing.topics',
  tags: TOPIC_TAGS,
  tagLabel: (t, tag) => t(`writing.topics.tags.${tag as TopicTag}`),
  useTopics: (tag) => useWritingTopics(tag as TopicTag | ''),
}

