import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import {
  type CategoryNode,
  categoryLabels,
  labelOf,
  SLUG_PATTERN,
  useCreateCategory,
  useErrorCategories,
  useResolveCategory,
} from '../../api/errors'
import { PageTitle } from '../../components/PageTitle'
import { isDrillableNode } from '../drills/drillRules'
import { ErrorText } from '../settings/ErrorText'
import { CategorySelect } from './CategorySelect'
import { Notice } from '../../components/Notice'

function errorsHref(code: string): string {
  return `/errors?${new URLSearchParams({ category: code }).toString()}`
}

function Counts({ node }: { node: CategoryNode }) {
  const { t } = useTranslation()
  return (
    <>
      {t('errorLog.categories.errorsCount', { count: node.count })}
      {node.count > 0 && <> · {t('errorLog.categories.recent', { count: node.count_recent })}</>}
    </>
  )
}

/** One category proposed by the AI: accept (with an optional rename) or reject (explained first). */
function Proposal({
  node,
  parent,
  onDone,
  onFailed,
}: {
  node: CategoryNode
  parent: CategoryNode | undefined
  onDone: (message: string) => void
  onFailed: (error: unknown) => void
}) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const resolve = useResolveCategory(node.id)
  const label = labelOf(node, i18n.language)
  const [labelEn, setLabelEn] = useState(node.label_en)
  const [labelFr, setLabelFr] = useState(node.label_fr)
  const [rejecting, setRejecting] = useState(false)
  const cancel = useRef<HTMLButtonElement>(null)
  const french = i18n.language.startsWith('fr')
  const description = french ? node.description_fr : node.description_en

  // The "Reject" button is replaced by its confirmation: focus goes to the safe choice (D-067).
  useEffect(() => {
    if (rejecting) cancel.current?.focus()
  }, [rejecting])

  function accept() {
    const body: { decision: 'accept'; label_en?: string; label_fr?: string } = { decision: 'accept' }
    if (labelEn.trim() !== '' && labelEn.trim() !== node.label_en) body.label_en = labelEn.trim()
    if (labelFr.trim() !== '' && labelFr.trim() !== node.label_fr) body.label_fr = labelFr.trim()
    resolve.mutate(body, {
      onSuccess: (result) =>
        onDone(
          t('errorLog.categories.accepted', { label: labelOf(result.category, i18n.language) }),
        ),
      onError: onFailed,
    })
  }

  function reject() {
    resolve.mutate(
      { decision: 'reject' },
      {
        onError: onFailed,
        onSuccess: (result) => {
          const count = result.reassigned_error_ids.length
          onDone(
            count === 0
              ? t('errorLog.categories.rejectedNone', { label })
              : t('errorLog.categories.rejected', { label, count }),
          )
        },
      },
    )
  }

  return (
    <li className="proposal">
      <p className="proposal__title">
        <strong>{label}</strong> <code className="category-code">{node.code}</code>
      </p>
      <p className="muted">
        {parent !== undefined &&
          `${t('errorLog.categories.under', { parent: labelOf(parent, i18n.language) })} · `}
        <Counts node={node} />
      </p>
      {description !== '' && <p lang={french ? 'fr' : 'en'}>{description}</p>}
      <details className="proposal__rename">
        <summary>{t('errorLog.categories.rename')}</summary>
        <div className="field">
          <label htmlFor={`${id}-en`}>{t('errorLog.categories.labelEn')}</label>
          <input
            id={`${id}-en`}
            lang="en"
            value={labelEn}
            maxLength={200}
            onChange={(e) => setLabelEn(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={`${id}-fr`}>{t('errorLog.categories.labelFr')}</label>
          <input
            id={`${id}-fr`}
            lang="fr"
            value={labelFr}
            maxLength={200}
            onChange={(e) => setLabelFr(e.target.value)}
          />
        </div>
      </details>
      {!rejecting ? (
        <div className="confirm">
          <button
            type="button"
            className="button button--primary"
            disabled={resolve.isPending}
            aria-label={t('errorLog.categories.acceptNamed', { label })}
            onClick={accept}
          >
            {t('errorLog.categories.accept')}
          </button>
          <button
            type="button"
            className="button"
            disabled={resolve.isPending}
            aria-label={t('errorLog.categories.rejectNamed', { label })}
            onClick={() => setRejecting(true)}
          >
            {t('errorLog.categories.reject')}
          </button>
        </div>
      ) : (
        <div
          className="confirm"
          role="alertdialog"
          aria-label={t('errorLog.categories.rejectConfirm', { label })}
        >
          <p>{t('errorLog.categories.rejectConfirm', { label })}</p>
          <button
            type="button"
            className="button button--danger"
            disabled={resolve.isPending}
            onClick={reject}
          >
            {t('errorLog.categories.rejectYes')}
          </button>
          <button
            ref={cancel}
            type="button"
            className="button"
            onClick={() => setRejecting(false)}
          >
            {t('errorLog.categories.rejectCancel')}
          </button>
        </div>
      )}
    </li>
  )
}

function TreeNodes({ nodes }: { nodes: CategoryNode[] }) {
  const { t, i18n } = useTranslation()
  const shown = nodes.filter((node) => node.status !== 'rejected')
  if (shown.length === 0) return null
  return (
    <ul className="category-tree">
      {shown.map((node) => (
        <li key={node.code}>
          <p className="category-tree__row">
            <strong>{labelOf(node, i18n.language)}</strong>{' '}
            <code className="category-code">{node.code}</code>
            <span className="muted">
              {' '}
              · {t(`errorLog.categories.status.${node.status}`)} ·{' '}
              {t(`errorLog.categories.origin.${node.origin}`)} · <Counts node={node} />
            </span>
            {node.count > 0 && (
              <>
                {' '}
                <Link to={errorsHref(node.code)}>{t('errorLog.categories.errorsLink')}</Link>
              </>
            )}
            {/* The server stays the judge (`not_drillable`); this is the same rule on the code. */}
            {isDrillableNode(node) && (
              <>
                {' '}
                <Link
                  to={`/drills?${new URLSearchParams({ category: node.code }).toString()}`}
                  aria-label={t('errorLog.categories.practiseNamed', {
                    label: labelOf(node, i18n.language),
                  })}
                >
                  {t('errorLog.categories.practise')}
                </Link>
              </>
            )}
          </p>
          <TreeNodes nodes={node.children} />
        </li>
      ))}
    </ul>
  )
}

function CreateForm({ tree, onDone }: { tree: CategoryNode[]; onDone: (message: string) => void }) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const create = useCreateCategory()
  const [parent, setParent] = useState<string | null>(null)
  const [slug, setSlug] = useState('')
  const [labelEn, setLabelEn] = useState('')
  const [labelFr, setLabelFr] = useState('')
  const [descriptionEn, setDescriptionEn] = useState('')
  const [descriptionFr, setDescriptionFr] = useState('')
  // Until the user chooses, the first top-level category is the parent (a top-level one is explicit).
  const parentCode = parent ?? tree.find((node) => node.status === 'active')?.code ?? ''
  const slugInvalid = slug !== '' && !SLUG_PATTERN.test(slug)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!SLUG_PATTERN.test(slug)) return
    create.mutate(
      {
        parent_code: parentCode === '' ? null : parentCode,
        slug,
        label_en: labelEn.trim(),
        label_fr: labelFr.trim(),
        description_en: descriptionEn.trim(),
        description_fr: descriptionFr.trim(),
      },
      {
        onSuccess: (node) => {
          onDone(
            t('errorLog.categories.created', {
              label: labelOf(node, i18n.language),
              code: node.code,
            }),
          )
          setSlug('')
          setLabelEn('')
          setLabelFr('')
          setDescriptionEn('')
          setDescriptionFr('')
        },
      },
    )
  }

  return (
    <form onSubmit={submit} className="library-form">
      <div className="field">
        <label htmlFor={`${id}-parent`}>{t('errorLog.categories.parent')}</label>
        <CategorySelect
          id={`${id}-parent`}
          tree={tree}
          value={parentCode}
          onChange={setParent}
          mode="assign"
          placeholder={t('errorLog.categories.topLevel')}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-slug`}>{t('errorLog.categories.slug')}</label>
        <input
          id={`${id}-slug`}
          value={slug}
          maxLength={41}
          required
          autoComplete="off"
          aria-invalid={slugInvalid}
          aria-describedby={`${id}-slug-hint`}
          onChange={(e) => setSlug(e.target.value)}
        />
        <p
          id={`${id}-slug-hint`}
          className={`field-hint ${slugInvalid ? 'field-hint--error' : 'muted'}`}
        >
          {slugInvalid ? `${t('errorLog.categories.slugInvalid')} ` : ''}
          {t('errorLog.categories.slugHint')}
        </p>
      </div>
      <div className="field">
        <label htmlFor={`${id}-en`}>{t('errorLog.categories.labelEn')}</label>
        <input
          id={`${id}-en`}
          lang="en"
          value={labelEn}
          maxLength={200}
          required
          onChange={(e) => setLabelEn(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-fr`}>{t('errorLog.categories.labelFr')}</label>
        <input
          id={`${id}-fr`}
          lang="fr"
          value={labelFr}
          maxLength={200}
          required
          onChange={(e) => setLabelFr(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-den`}>{t('errorLog.categories.descriptionEn')}</label>
        <textarea
          id={`${id}-den`}
          lang="en"
          rows={2}
          maxLength={1000}
          value={descriptionEn}
          onChange={(e) => setDescriptionEn(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-dfr`}>{t('errorLog.categories.descriptionFr')}</label>
        <textarea
          id={`${id}-dfr`}
          lang="fr"
          rows={2}
          maxLength={1000}
          value={descriptionFr}
          onChange={(e) => setDescriptionFr(e.target.value)}
        />
      </div>
      <div>
        <button
          type="submit"
          className="button button--primary"
          disabled={create.isPending || slugInvalid}
        >
          {create.isPending ? t('errorLog.categories.creating') : t('errorLog.categories.create')}
        </button>
      </div>
      {create.isError && <ErrorText error={create.error} />}
    </form>
  )
}

/** The error taxonomy: the AI's proposals to decide on, the tree with its counts, and creation. */
export function CategoriesPage() {
  const { t, i18n } = useTranslation()
  const categories = useErrorCategories()
  const [message, setMessage] = useState('')
  // A refused decision is shown here, not in the proposal: the reloaded tree may drop its card.
  const [failure, setFailure] = useState<unknown>(null)
  const done = (text: string) => {
    setFailure(null)
    setMessage(text)
  }
  const failed = (error: unknown) => {
    setMessage('')
    setFailure(error)
  }
  const tree = categories.data ?? []
  const byCode = categoryLabels(tree)
  const all = [...byCode.values()]
  const proposals = all.filter((node) => node.status === 'proposed')
  const rejected = all.filter((node) => node.status === 'rejected')

  return (
    <div className="errors-page">
      <section className="hero">
        <PageTitle>{t('errorLog.categories.title')}</PageTitle>
        <p className="muted">{t('errorLog.categories.intro')}</p>
        <p className="link-row">
          <Link to="/errors">{t('errorLog.back')}</Link>
        </p>
      </section>

      <div role="status" aria-live="polite">
        {message !== '' && <Notice tone="success">{message}</Notice>}
      </div>
      {failure !== null && <ErrorText error={failure} />}

      {categories.isPending && <p className="muted">{t('errorLog.categories.loading')}</p>}
      {categories.isError && <ErrorText error={categories.error} />}

      {categories.isSuccess && (
        <>
          <section className="card" aria-labelledby="proposals-title">
            <h2 id="proposals-title">{t('errorLog.categories.proposalsTitle')}</h2>
            {proposals.length === 0 ? (
              <p className="muted">{t('errorLog.categories.noProposals')}</p>
            ) : (
              <>
                <p className="muted">{t('errorLog.categories.proposalsIntro')}</p>
                <ul className="proposals">
                  {proposals.map((node) => (
                    <Proposal
                      key={node.id}
                      node={node}
                      parent={node.parent_code !== null ? byCode.get(node.parent_code) : undefined}
                      onDone={done}
                      onFailed={failed}
                    />
                  ))}
                </ul>
              </>
            )}
          </section>

          <section className="card" aria-labelledby="tree-title">
            <h2 id="tree-title">{t('errorLog.categories.treeTitle')}</h2>
            <TreeNodes nodes={tree} />
            {rejected.length > 0 && (
              <details className="category-rejected">
                <summary>{t('errorLog.categories.rejectedFold', { count: rejected.length })}</summary>
                <ul>
                  {rejected.map((node) => (
                    <li key={node.code}>
                      {labelOf(node, i18n.language)}{' '}
                      <code className="category-code">{node.code}</code>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>

          <section className="card" aria-labelledby="create-title">
            <h2 id="create-title">{t('errorLog.categories.createTitle')}</h2>
            <CreateForm tree={tree} onDone={done} />
          </section>
        </>
      )}
    </div>
  )
}
