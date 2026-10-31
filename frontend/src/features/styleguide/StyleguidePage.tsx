import { type CSSProperties, type ReactNode } from 'react'

import { ActionTile } from '../../components/ActionTile'
import { Badge, type Tone } from '../../components/Badge'
import { LineChart } from '../../components/charts/LineChart'
import { EmptyState } from '../../components/EmptyState'
import { HomeHero } from '../../components/HomeHero'
import { Icon } from '../../components/Icon'
import { ICON_NAMES } from '../../components/iconPaths'
import { Notice, type NoticeTone } from '../../components/Notice'
import { SectionHeader } from '../../components/SectionHeader'
import { type NavGroup, Sidebar } from '../../components/Sidebar'
import { StatTile } from '../../components/StatTile'
import './styleguide.css'

// Development only: this page is mounted when `import.meta.env.DEV` is true and is absent from the
// production build. Its texts stay in English, outside i18n (D-291).
// Witness string searched for in dist/ after a build: STYLEGUIDE-WITNESS-7f3a91

const COLOURS = [
  'bg',
  'surface',
  'surface-sunken',
  'border',
  'border-strong',
  'ink',
  'ink-muted',
  'ink-subtle',
  'brand',
  'brand-hover',
  'on-brand',
  'brand-strong',
  'brand-tint',
  'brand-tint-border',
  'focus-ring',
  'sidebar',
  'sidebar-ink',
  'sidebar-active',
  'accent',
  'accent-tint',
  'success',
  'success-tint',
  'warning',
  'warning-tint',
  'danger',
  'danger-tint',
  'chart-1',
  'chart-2',
  'chart-3',
  'chart-4',
  'chart-5',
  'illus-blob',
  'illus-paper',
  'illus-light',
  'illus-leaf',
]

const TYPE_SCALE = [
  ['display', 'Ready for 25 minutes?'],
  ['title-1', 'Library'],
  ['term', 'to hedge'],
  ['title-2', 'Do you remember?'],
  ['title-3', 'Continue'],
  ['body', 'Write a short paragraph in English. The AI corrects it.'],
  ['body-sm', '48 reviews due, 1 new term'],
  ['stat', '48'],
  ['eyebrow', 'SECTION'],
  ['caption', 'Space / Enter shows the answer'],
] as const

const TONES: Tone[] = ['brand', 'success', 'warning', 'danger', 'neutral']
const NOTICES: NoticeTone[] = ['info', 'warning', 'danger', 'success']

const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      { to: '/', icon: 'home', label: 'Home', end: true },
      { to: '/session', icon: 'today', label: 'Today' },
    ],
  },
  { title: 'Vocabulary', items: [{ to: '/library', icon: 'library', label: 'Library', count: 9 }] },
  {
    title: 'Practice',
    items: [
      { to: '/writing', icon: 'writing', label: 'Writing' },
      { to: '/speaking', icon: 'speaking', label: 'Speaking' },
    ],
  },
]

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card styleguide__section">
      <h2>{title}</h2>
      {children}
    </section>
  )
}

function Swatches() {
  return (
    <div className="styleguide__themes">
      {(['light', 'dark'] as const).map((scheme) => (
        <div key={scheme} className="styleguide__theme" style={{ colorScheme: scheme }}>
          <h3>{scheme}</h3>
          <div className="styleguide__swatches">
            {COLOURS.map((name) => (
              <div key={name} className="styleguide__swatch">
                <span className="styleguide__chip" style={{ background: `var(--${name})` }} />
                <code>{name}</code>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function StyleguidePage() {
  return (
    <div className="styleguide">
      <h1>Style guide</h1>
      <p className="muted">
        Development only. Tokens, type, icons and every base component in each state, in both themes
        (use the Theme selector; the colour panels show both at once).
      </p>

      <Section title="Colour tokens">
        <Swatches />
      </Section>

      <Section title="Type scale">
        {TYPE_SCALE.map(([name, sample]) => (
          <div key={name} className="styleguide__type-row">
            <code>{name}</code>
            <span
              style={
                {
                  fontSize: `var(--fs-${name})`,
                  lineHeight: `var(--lh-${name})`,
                  fontWeight: name === 'display' || name === 'title-1' || name === 'stat' ? 700 : 400,
                } as CSSProperties
              }
            >
              {sample}
            </span>
          </div>
        ))}
      </Section>

      <Section title="Icons (20px)">
        <ul className="styleguide__icons">
          {ICON_NAMES.map((name) => (
            <li key={name}>
              <Icon name={name} size={20} />
              <code>{name}</code>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Buttons">
        <div className="button-row">
          <button type="button" className="button button--primary">
            Primary
          </button>
          <button type="button" className="button">
            Secondary
          </button>
          <button type="button" className="button button--ghost">
            Ghost
          </button>
          <button type="button" className="button button--danger">
            Danger
          </button>
          <button type="button" className="button button--primary" disabled>
            Disabled
          </button>
          <button type="button" className="button" aria-busy="true">
            Busy
          </button>
        </div>
        <div className="button-row">
          <button type="button" className="button button--small">
            Small
          </button>
          <button type="button" className="button">
            Normal
          </button>
          <button type="button" className="button button--large">
            Large
          </button>
          <button type="button" className="button button--icon" aria-label="Copy">
            <Icon name="copy" size={18} />
          </button>
          <button type="button" className="button">
            <Icon name="import" size={18} />
            Import a list
          </button>
          <button type="button" className="button">
            Sort new terms <span className="count">9</span>
          </button>
          <button type="button" className="button button--primary">
            Start <span className="count">48</span>
          </button>
        </div>
        <div className="styleguide__on-photo">
          <button type="button" className="button button--hero">
            Start the session
          </button>
        </div>
      </Section>

      <Section title="Fields">
        <div className="styleguide__fields">
          <div className="field">
            <label htmlFor="sg-text">Term</label>
            <input id="sg-text" type="text" placeholder="to hedge" />
            <p className="field-hint">An example, never the label.</p>
          </div>
          <div className="field">
            <label htmlFor="sg-error">With an error</label>
            <input id="sg-error" type="text" aria-invalid="true" defaultValue="hedg" />
            <p className="field-hint form-message--error">Write the whole word.</p>
          </div>
          <div className="field">
            <label htmlFor="sg-select">Select</label>
            <select id="sg-select" defaultValue="b">
              <option value="a">Any</option>
              <option value="b">Queued</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="sg-disabled">Disabled</label>
            <input id="sg-disabled" type="text" disabled defaultValue="Locked" />
          </div>
        </div>
        <div className="field">
          <label htmlFor="sg-area">Text area</label>
          <textarea id="sg-area" rows={3} placeholder="Write a short paragraph in English." />
        </div>
        <div className="button-row">
          <label className="checkbox-row">
            <input type="checkbox" defaultChecked /> Checkbox
          </label>
          <label className="checkbox-row">
            <input type="radio" name="sg-radio" defaultChecked /> Radio
          </label>
          <label className="checkbox-row">
            <input type="radio" name="sg-radio" /> Radio
          </label>
        </div>
      </Section>

      <Section title="Badges, notices, key hints">
        <div className="button-row">
          {TONES.map((tone) => (
            <Badge key={tone} tone={tone}>
              {tone}
            </Badge>
          ))}
        </div>
        <div className="styleguide__stack">
          {NOTICES.map((tone) => (
            <Notice key={tone} tone={tone}>
              A {tone} notice: an icon and words, never the colour alone. <a href="#sg">A link</a>
            </Notice>
          ))}
        </div>
        <p className="key-hints">
          <span>
            <kbd>Space</kbd> shows the answer
          </span>
          <span>
            <kbd>1</kbd>-<kbd>4</kbd> rate
          </span>
        </p>
      </Section>

      <Section title="Stat tiles and action tiles">
        <div className="styleguide__tiles">
          <StatTile value="48" label="reviews due" />
          <StatTile value="12" label="new terms" />
          <StatTile value="18 / 45 min" label="of today's budget" progress={0.4} />
        </div>
        <div className="styleguide__tiles">
            <ActionTile to="/errors" icon="target" title="Practise" text="Past simple, 15 errors" />
            <ActionTile to="/speaking" icon="speaking" title="Speak" text="1 shadowing waiting" />
            <ActionTile to="/library" icon="library" title="Sort" text="4 terms to sort" />
        </div>
      </Section>

      <Section title="Section header">
        <SectionHeader
          eyebrow="Section"
          title="Library"
          description="Every word and expression you want to learn."
          actions={
            <>
              <button type="button" className="button button--primary">
                <Icon name="plus" size={18} />
                Import a list
              </button>
              <button type="button" className="button">
                Sort new terms <span className="count">9</span>
              </button>
              <button type="button" className="button">
                Duplicates
              </button>
            </>
          }
        />
      </Section>

      <Section title="Home hero">
        <HomeHero
          date="Tuesday, October 27"
          title="Ready for 25 minutes?"
          text="48 reviews and 1 new term are waiting."
        >
          <button type="button" className="button button--hero">
            Start the session
          </button>
        </HomeHero>
      </Section>

      <Section title="Empty states">
        <div className="styleguide__tiles">
          <EmptyState illustration="books" title="No terms yet" text="Import a list to begin.">
            <button type="button" className="button button--primary">
              Import a list
            </button>
          </EmptyState>
          <EmptyState illustration="pencil" title="No errors logged yet" text="Write a paragraph." />
          <EmptyState illustration="chart" title="Nothing to chart yet" />
        </div>
      </Section>

      <Section title="Table">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Term</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">
                  Reviews
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>confounder</td>
                <td>
                  <Badge tone="success">Learning</Badge>
                </td>
                <td className="num">128</td>
              </tr>
              <tr>
                <td>off the top of my head</td>
                <td>
                  <Badge tone="warning">To sort</Badge>
                </td>
                <td className="num">4</td>
              </tr>
            </tbody>
          </table>
        </div>
        <details>
          <summary>A disclosure</summary>
          <p>Hidden until opened.</p>
        </details>
      </Section>

      <Section title="Sidebar, expanded and folded">
        <div className="styleguide__sidebars">
            <div className="styleguide__sidebar-demo">
              <Sidebar
                id="sg-sidebar-open"
                appName="vocab-coach"
                navLabel="Expanded"
                groups={NAV_GROUPS}
                bottom={[{ to: '/settings', icon: 'settings', label: 'Settings' }]}
                collapsed={false}
                open={false}
              />
            </div>
            <div className="styleguide__sidebar-demo styleguide__sidebar-demo--folded">
              <Sidebar
                id="sg-sidebar-folded"
                appName="vocab-coach"
                navLabel="Folded"
                groups={NAV_GROUPS}
                bottom={[{ to: '/settings', icon: 'settings', label: 'Settings' }]}
                collapsed
                open={false}
              />
            </div>
        </div>
      </Section>

      <Section title="Chart">
        <LineChart
          title="Reviews per day"
          xLabels={DAYS}
          series={[
            { id: 'done', label: 'Done', values: [12, 18, 9, null, 22, 30, 25] },
            { id: 'due', label: 'Due', values: [14, 16, 12, 10, 20, 28, 24], dashed: true },
          ]}
          format={(value) => String(Math.round(value))}
        />
      </Section>
    </div>
  )
}
