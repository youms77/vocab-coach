import { useTranslation } from 'react-i18next'

/** The keys the current phase answers to: `[keys, action]`, keys separated by `|` (D-122). */
export function KeyHints({ items }: { items: [string, string][] }) {
  const { t } = useTranslation()
  if (items.length === 0) return null
  return (
    <p className="key-hints">
      <span className="visually-hidden">{t('review.keys.label')}: </span>
      {items.map(([keys, action]) => (
        <span key={keys} className="key-hints__item">
          {keys.split('|').map((key, i) => (
            <span key={key}>
              {i > 0 && ' / '}
              <kbd>{key}</kbd>
            </span>
          ))}{' '}
          {action}
        </span>
      ))}
    </p>
  )
}
