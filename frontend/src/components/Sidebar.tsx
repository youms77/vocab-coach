import { Link, NavLink } from 'react-router'

import { Icon, type IconName } from './Icon'

export interface NavItem {
  to: string
  icon: IconName
  label: string
  /** Matches the path exactly (Home). */
  end?: boolean
  /** Work waiting behind this link; shown as a counter, or a dot on the icon when folded. */
  count?: number
}

export interface NavGroup {
  /** No title: the group is not announced (Home and Today). */
  title?: string
  items: NavItem[]
}

/**
 * The navigation. One `<nav>` for every width: CSS turns it into the left sidebar (expanded, or
 * folded to an icon rail) from 960px, and into a panel opened by the Menu button below. A folded
 * item keeps its label in the markup, hidden visually, and gets a `title`.
 */
export function Sidebar({
  id,
  appName,
  navLabel,
  groups,
  bottom,
  collapsed,
  open,
}: {
  id: string
  appName: string
  navLabel: string
  groups: NavGroup[]
  bottom: NavItem[]
  collapsed: boolean
  open: boolean
}) {
  const classes = ['sidebar']
  if (collapsed) classes.push('sidebar--collapsed')
  if (open) classes.push('sidebar--open')

  const link = (item: NavItem) => (
    <NavLink key={item.to} to={item.to} end={item.end} className="nav-item" title={collapsed ? item.label : undefined}>
      <Icon name={item.icon} size={20} />
      <span className="nav-item__label">{item.label}</span>
      {item.count !== undefined && item.count > 0 && <span className="count">{item.count}</span>}
    </NavLink>
  )

  return (
    <aside id={id} className={classes.join(' ')}>
      <Link className="sidebar__brand" to="/">
        <span className="sidebar__mark" aria-hidden="true">
          v
        </span>
        <span className="sidebar__name">{appName}</span>
      </Link>
      <nav aria-label={navLabel} className="sidebar__nav">
        {groups.map((group, index) => (
          <div
            key={group.title ?? index}
            className="sidebar__group"
            role={group.title === undefined ? undefined : 'group'}
            aria-label={group.title}
          >
            {group.title !== undefined && <span className="sidebar__group-title">{group.title}</span>}
            {group.items.map(link)}
          </div>
        ))}
        <div className="sidebar__bottom">{bottom.map(link)}</div>
      </nav>
    </aside>
  )
}
