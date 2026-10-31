import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router'

import { PageTitle } from '../../components/PageTitle'

const MODULES = [
  'library',
  'sheets',
  'discovery',
  'reviews',
  'errors',
  'writing',
  'speaking',
  'transcripts',
  'drills',
  'consolidation',
  'tracks',
  'stats',
  'backup',
] as const

const PRINCIPLES = ['local', 'free', 'degraded', 'recall'] as const

const HEADER_FIELDS = ['deck', 'domain', 'source', 'context', 'deadline']

const MARKDOWN_EXAMPLE = [
  '---',
  'deck: Causal inference reading',
  'domain: econometrics',
  'source: "Angrist & Pischke, Mostly Harmless Econometrics, ch. 3"',
  'context: "Reading for my M2 report on policy evaluation"',
  'deadline: 2026-11-20',
  '---',
  '- heteroskedasticity',
  '- to account for | We account for regional fixed effects in all specifications.',
  '- shed light on',
].join('\n')

/** The anchor of the "Bring your words in" section: the Import page links to it. */
export const BRING_ANCHOR = 'bring-your-words'

function CopyPrompt({ text }: { text: string }) {
  const { t } = useTranslation()
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setState('copied')
    } catch {
      setState('failed')
    }
  }
  return (
    <div className="about-copy">
      <button type="button" className="button" onClick={() => void copy()}>
        {t('about.prompt.copy')}
      </button>
      <span role="status" className="muted">
        {state === 'copied' && t('about.prompt.copied')}
        {state === 'failed' && t('about.prompt.copyFailed')}
      </span>
    </div>
  )
}

export function AboutPage() {
  const { t } = useTranslation()
  const { hash } = useLocation()

  // A link to `/about#bring-your-words` lands on the section (the router does not scroll by itself).
  useEffect(() => {
    if (hash === '') return
    document.getElementById(hash.slice(1))?.scrollIntoView?.()
  }, [hash])

  const prompt = t('about.prompt.text')

  return (
    <div className="about-page">
      <section className="hero">
        <PageTitle>{t('about.title')}</PageTitle>
        <p className="muted">{t('about.lede')}</p>
      </section>

      <section className="card" aria-labelledby="about-purpose-title">
        <h2 id="about-purpose-title">{t('about.purpose.title')}</h2>
        <p>{t('about.purpose.text')}</p>
        <h3>{t('about.principles.title')}</h3>
        <ul>
          {PRINCIPLES.map((key) => (
            <li key={key}>{t(`about.principles.${key}`)}</li>
          ))}
        </ul>
      </section>

      <section className="card" aria-labelledby="about-modules-title">
        <h2 id="about-modules-title">{t('about.modules.title')}</h2>
        <ul className="about-modules">
          {MODULES.map((key) => (
            <li key={key}>
              <strong>{t(`about.modules.${key}.name`)}</strong>
              {' — '}
              {t(`about.modules.${key}.text`)}
            </li>
          ))}
        </ul>
      </section>

      <section className="card" aria-labelledby={`${BRING_ANCHOR}-title`} id={BRING_ANCHOR}>
        <h2 id={`${BRING_ANCHOR}-title`}>{t('about.bring.title')}</h2>
        <p>{t('about.bring.intro')}</p>
        <dl className="about-formats">
          <div>
            <dt>{t('about.bring.markdown.title')}</dt>
            <dd>
              {t('about.bring.markdown.text')}{' '}
              <span>{t('about.bring.markdown.fields')}</span>{' '}
              <code lang="en">{HEADER_FIELDS.join(', ')}</code>
            </dd>
          </div>
          <div>
            <dt>{t('about.bring.text.title')}</dt>
            <dd>{t('about.bring.text.text')}</dd>
          </div>
          <div>
            <dt>{t('about.bring.table.title')}</dt>
            <dd>{t('about.bring.table.text')}</dd>
          </div>
          <div>
            <dt>{t('about.bring.other.title')}</dt>
            <dd>{t('about.bring.other.text')}</dd>
          </div>
        </dl>
        <h3>{t('about.bring.exampleLabel')}</h3>
        <pre className="code-block" lang="en">
          <code>{MARKDOWN_EXAMPLE}</code>
        </pre>
        <p>
          <Link to="/import">{t('about.bring.import')}</Link>
        </p>
      </section>

      <section className="card" aria-labelledby="about-prompt-title">
        <h2 id="about-prompt-title">{t('about.prompt.title')}</h2>
        <p>{t('about.prompt.intro')}</p>
        <CopyPrompt text={prompt} />
        <pre className="code-block about-prompt" role="group" aria-label={t('about.prompt.label')}>
          <code>{prompt}</code>
        </pre>
        <p className="muted">{t('about.prompt.limits')}</p>
      </section>
    </div>
  )
}
