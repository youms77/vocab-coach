/**
 * Translation values that are text meant for a chatbot, copied as written and not interface
 * wording: they are exempt from the French typography and register checks (straight quotes and
 * apostrophes, "tu", a plain space before a colon, the header field `deck:`...). The text is
 * tested by its own test (features/about/AboutPage.test.tsx).
 */
export const VERBATIM_KEYS: ReadonlySet<string> = new Set(['about.prompt.text'])
