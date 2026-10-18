import { type FormEvent, type RefObject, useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'

import {
  DEFAULT_DRILL_ITEMS,
  DRILLS_PAGE_SIZE,
  MAX_DRILL_ITEMS,
  MIN_DRILL_ITEMS,
  useCreateDrill,
  useDrills,
} from '../../api/drills'
import { categoryLabels, labelOf, useErrorCategories } from '../../api/errors'
import { PageTitle } from '../../components/PageTitle'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { CategorySelect } from '../errors/CategorySelect'
import { formatShortDate } from '../session/format'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { isDrillableCode, isDrillableNode, progressOf } from './drillRules'
import { fromSessionOf } from './fromSession'

/** "New drill": a category, a number of items, and the wait for the AI (a few seconds). */
function NewDrillForm({
  preset,
  fromSession,
  formRef,
}: {
  preset: string
  fromSession: number | null
  formRef: RefObject<HTMLFormElement | null>
}) {
  const { t } = useTranslation()
  const id = useId()
  const navigate = useNavigate()
  const categories = useErrorCategories()
  const create = useCreateDrill()
  const seconds = useElapsedSeconds(create.isPending, create.submittedAt)
  // The user's own choice; until then, the category of the link (if it can be drilled).
  const [chosen, setChosen] = useState<string | null>(null)
  const [count, setCount] = useState(String(DEFAULT_DRILL_ITEMS))
  // Set synchronously: two clicks before React re-renders still send one request.
  const sending = useRef(false)

  const tree = categories.data ?? []
  const byCode = categoryLabels(tree)
  // Once the tree is known it decides (a proposed category is refused); until then the code does.
  const presetNode = byCode.get(preset)
  const presetOk =
    preset !== '' &&
    (categories.isSuccess
      ? presetNode !== undefined && isDrillableNode(presetNode)
      : isDrillableCode(preset))
  const category = chosen ?? (presetOk ? preset : '')
  const number = Number(count)
  const countValid = Number.isInteger(number) && number >= MIN_DRILL_ITEMS && number <= MAX_DRILL_ITEMS
  const nothingToDrill = categories.isSuccess && ![...byCode.values()].some(isDrillableNode)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current || category === '' || !countValid) return
    sending.current = true
    create.mutate(
      {
        category_code: category,
        count: number,
        ...(fromSession !== null ? { study_session_id: fromSession } : {}),
      },
      {
        onSuccess: (created) => {
          if (created.drill !== null) {
            void navigate(`/drills/${created.drill.id}`, {
              state: fromSession !== null ? { fromSession } : null,
            })
          }
        },
        onSettled: () => {
          sending.current = false
        },
      },
    )
  }

  const failure = create.data !== undefined && create.data.drill === null ? create.data : null
  let failureText = ''
  if (failure !== null) {
    failureText =
      failure.status === 'incomplete'
        ? t('drills.form.incomplete')
        : t('drills.form.unavailable', { reason: aiReasonText(t, failure.reason) })
  }

  return (
    <form ref={formRef} className="drill-form" onSubmit={submit} aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{t('drills.form.title')}</h2>
      {fromSession !== null && <p className="muted">{t('drills.form.fromSession')}</p>}
      {nothingToDrill ? (
        <p className="muted">{t('drills.form.noCategories')}</p>
      ) : (
        <>
          <div className="field">
            <label htmlFor={`${id}-category`}>{t('drills.form.category')}</label>
            <CategorySelect
              id={`${id}-category`}
              tree={tree}
              value={category}
              onChange={setChosen}
              mode="drill"
              required
            />
          </div>
          <div className="field">
            <label htmlFor={`${id}-count`}>{t('drills.form.count')}</label>
            <input
              id={`${id}-count`}
              type="number"
              inputMode="numeric"
              min={MIN_DRILL_ITEMS}
              max={MAX_DRILL_ITEMS}
              step={1}
              value={count}
              aria-invalid={!countValid}
              aria-describedby={`${id}-count-hint`}
              onChange={(e) => setCount(e.target.value)}
            />
            <p
              id={`${id}-count-hint`}
              className={`field-hint ${countValid ? 'muted' : 'field-hint--error'}`}
            >
              {countValid ? t('drills.form.countHint') : t('drills.form.countInvalid')}
            </p>
          </div>
          <div>
            <button
              type="submit"
              className="button button--primary"
              disabled={create.isPending || category === '' || !countValid}
            >
              {create.isPending ? t('drills.form.preparing', { seconds }) : t('drills.form.create')}
            </button>
          </div>
        </>
      )}
      <div role="status">
        {create.isPending && (
          <>
            <p className="visually-hidden">{t('drills.form.preparingStatus')}</p>
            <p className="muted">{t('drills.form.preparingHint')}</p>
          </>
        )}
        {failure !== null && !create.isPending && (
          <p className="form-message form-message--warn">{failureText}</p>
        )}
      </div>
      {create.isError && !create.isPending && <ErrorText error={create.error} />}
    </form>
  )
}

/** The drills already made, newest first, 20 per page; the category and the page are in the URL. */
function DrillList({ category, page }: { category: string; page: number }) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const [, setParams] = useSearchParams()
  const categories = useErrorCategories()
  const drills = useDrills(category, page)
  const total = drills.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / DRILLS_PAGE_SIZE))

  const goTo = (next: { category?: string; page?: number }) => {
    const target = next.category ?? category
    const pageNumber = (next.page ?? page) + 1
    const params = new URLSearchParams()
    if (target !== '') params.set('category', target)
    if (pageNumber > 1) params.set('page', String(pageNumber))
    setParams(params)
  }

  return (
    <section className="card" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{t('drills.list.title')}</h2>
      <div className="field drill-filter">
        <label htmlFor={`${id}-filter`}>{t('drills.list.filter')}</label>
        <CategorySelect
          id={`${id}-filter`}
          tree={categories.data ?? []}
          value={category}
          onChange={(next) => goTo({ category: next, page: 0 })}
          mode="filter"
          placeholder={t('drills.list.all')}
        />
      </div>
      {drills.isPending && <p className="muted">{t('drills.list.loading')}</p>}
      {drills.isError && <ErrorText error={drills.error} />}
      {drills.isSuccess && drills.data.items.length === 0 && (
        <p className="muted">{category === '' ? t('drills.list.empty') : t('drills.list.emptyFiltered')}</p>
      )}
      {drills.isSuccess && drills.data.items.length > 0 && (
        <>
          <p className="muted" role="status">
            {t('drills.list.count', { count: total })}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t('drills.list.date')}</th>
                  <th scope="col">{t('drills.list.category')}</th>
                  <th scope="col">{t('drills.list.score')}</th>
                  <th scope="col">{t('drills.list.state')}</th>
                </tr>
              </thead>
              <tbody>
                {drills.data.items.map((drill) => {
                  const progress = progressOf(drill)
                  return (
                    <tr key={drill.id}>
                      <th scope="row">
                        <Link to={`/drills/${drill.id}`}>{formatShortDate(drill.created_at, i18n.language)}</Link>
                      </th>
                      <td>
                        {labelOf(drill.category, i18n.language)}{' '}
                        <code className="category-code">{drill.category.code}</code>
                      </td>
                      <td>
                        {drill.score.answered === 0
                          ? '—'
                          : t('drills.list.scoreValue', {
                              correct: drill.score.correct,
                              total: drill.score.total,
                            })}
                      </td>
                      <td>
                        {progress === 'inProgress'
                          ? t('drills.list.inProgress', {
                              answered: drill.score.answered,
                              total: drill.score.total,
                            })
                          : t(`drills.list.${progress}`)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <nav className="pager" aria-label={t('library.pager.label')}>
            <button type="button" className="button" disabled={page === 0} onClick={() => goTo({ page: page - 1 })}>
              {t('library.pager.previous')}
            </button>
            <span>{t('library.pager.page', { page: page + 1, pages })}</span>
            <button
              type="button"
              className="button"
              disabled={page + 1 >= pages}
              onClick={() => goTo({ page: page + 1 })}
            >
              {t('library.pager.next')}
            </button>
          </nav>
        </>
      )}
    </section>
  )
}

/**
 * `/drills`: create a drill and see the ones already made. `?category=code` filters the list and
 * preselects the form's category when it can be drilled, then scrolls to the form; nothing starts
 * without a click. `{fromSession}` in the navigation state links the drill to today's session.
 */
export function DrillsPage() {
  const { t } = useTranslation()
  const location = useLocation()
  const [params] = useSearchParams()
  const category = params.get('category') ?? ''
  const requested = Number(params.get('page'))
  const page = Number.isInteger(requested) && requested > 1 ? requested - 1 : 0
  const fromSession = fromSessionOf(location.state)
  const formRef = useRef<HTMLFormElement>(null)

  // Arriving with a category (a "Practise" link): bring the form into view, once.
  const arrivedWith = useRef(category)
  useEffect(() => {
    if (arrivedWith.current !== '') formRef.current?.scrollIntoView?.({ block: 'start' })
  }, [])

  return (
    <div className="drills-page">
      <section className="hero">
        <PageTitle>{t('drills.title')}</PageTitle>
        <p className="muted">{t('drills.intro')}</p>
        <p className="link-row">
          <Link to="/errors">{t('drills.errorLogLink')}</Link>
        </p>
      </section>
      <section className="card">
        <NewDrillForm preset={category} fromSession={fromSession} formRef={formRef} />
      </section>
      <DrillList category={category} page={page} />
    </div>
  )
}
