import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { useDuplicates, type DuplicateGroup, type GroupItem } from '../../api/duplicates'
import { useMergeItem } from '../../api/library'
import { ErrorText } from '../settings/ErrorText'

interface Merged {
  kept: string
  removed: string
  inverted: boolean
}

function MergeButton({
  item,
  into,
  onMerged,
}: {
  item: GroupItem
  into: GroupItem
  onMerged: (merged: Merged) => void
}) {
  const { t } = useTranslation()
  const merge = useMergeItem(item.id)
  return (
    <>
      <button
        type="button"
        className="button"
        disabled={merge.isPending}
        onClick={() =>
          merge.mutate(into.id, {
            onSuccess: (result) => {
              const inverted = result.inverted
              onMerged({
                kept: inverted ? item.term : into.term,
                removed: inverted ? into.term : item.term,
                inverted,
              })
            },
          })
        }
      >
        {t('duplicates.mergeInto', { term: into.term })}
      </button>
      {merge.isError && <ErrorText error={merge.error} />}
    </>
  )
}

/** The term with review cards is the natural one to keep (the backend keeps it anyway). */
function defaultKept(group: DuplicateGroup): number {
  return (group.items.find((i) => i.has_cards) ?? group.items[0]!).id
}

function Group({ group, onMerged }: { group: DuplicateGroup; onMerged: (m: Merged) => void }) {
  const { t } = useTranslation()
  const [keptId, setKeptId] = useState(() => defaultKept(group))
  const kept = group.items.find((i) => i.id === keptId) ?? group.items[0]!
  const name = `keep-${group.match}-${group.key}`

  return (
    <li className="card duplicate-group">
      <h2>
        {group.key}{' '}
        <span className="muted">({t(`duplicates.match.${group.match}`)})</span>
      </h2>
      <fieldset>
        <legend>{t('duplicates.keep')}</legend>
        <ul className="duplicate-items">
          {group.items.map((item) => (
            <li key={item.id}>
              <label className="checkbox-line">
                <input
                  type="radio"
                  name={name}
                  checked={item.id === kept.id}
                  onChange={() => setKeptId(item.id)}
                />
                <strong>{item.term}</strong>
              </label>
              <span className="muted">
                {t(`library.status.${item.status}`)}
                {item.has_cards && <> · {t('duplicates.hasCards')}</>}
                {item.decks.length > 0 && <> · {item.decks.map((d) => d.name).join(', ')}</>}
              </span>{' '}
              <Link to={`/library/items/${item.id}`}>{t('duplicates.open')}</Link>
              {item.id !== kept.id && <MergeButton item={item} into={kept} onMerged={onMerged} />}
            </li>
          ))}
        </ul>
      </fieldset>
    </li>
  )
}

export function DuplicatesPage() {
  const { t } = useTranslation()
  const groups = useDuplicates()
  const [merged, setMerged] = useState<Merged | null>(null)

  return (
    <div className="library-page">
      <section className="hero">
        <h1>{t('duplicates.title')}</h1>
        <p className="muted">{t('duplicates.intro')}</p>
        <p>
          <Link to="/library">{t('library.back')}</Link>
        </p>
      </section>
      {merged !== null && (
        <p className="form-message form-message--ok" role="status">
          {t('duplicates.merged', { kept: merged.kept, removed: merged.removed })}
          {merged.inverted && <> {t('duplicates.inverted')}</>}
        </p>
      )}
      {groups.isPending && <p className="muted">{t('library.loading')}</p>}
      {groups.isError && <ErrorText error={groups.error} />}
      {groups.isSuccess && groups.data.length === 0 && (
        <p className="muted">{t('duplicates.empty')}</p>
      )}
      {groups.isSuccess && groups.data.length > 0 && (
        <>
          <p className="muted">{t('duplicates.conflictHint')}</p>
          <ul className="deck-list">
            {groups.data.map((group) => (
              <Group key={`${group.match}-${group.key}`} group={group} onMerged={setMerged} />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
