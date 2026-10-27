import { SPEAKING_TAGS, type SpeakingTag, useSpeakingTopics } from '../../api/speech'
import type { TopicSource } from '../writing/topicSource'

/** The speaking page's suggested subjects: its own themes (with "presenting") and wording. */
export const SPEAKING_TOPICS: TopicSource = {
  ns: 'speaking.topics',
  tags: SPEAKING_TAGS,
  tagLabel: (t, tag) => t(`speaking.topics.tags.${tag as SpeakingTag}`),
  useTopics: (tag) => useSpeakingTopics(tag as SpeakingTag | ''),
}
