import { Link } from 'react-router'

import { Icon, type IconName } from './Icon'

/** A clickable tile that points to a secondary task; the line of text is live data. */
export function ActionTile({
  to,
  icon,
  title,
  text,
}: {
  to: string
  icon: IconName
  title: string
  text: string
}) {
  return (
    <Link className="action-tile" to={to}>
      <span className="action-tile__icon">
        <Icon name={icon} size={20} />
      </span>
      <span className="action-tile__title">{title}</span>
      <span className="action-tile__text">{text}</span>
    </Link>
  )
}
