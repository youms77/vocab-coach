/**
 * The icon set (D-289): outline icons on a 24x24 grid, stroke 1.75, drawn with `currentColor`, no
 * library. Sizes in use: 20 in navigation and tiles, 18 in buttons, 16 in small buttons.
 * Icons are decorative (`aria-hidden`): the label next to them, or the `aria-label` of an
 * icon-only button, carries the meaning.
 */
export const ICON_PATHS = {
  home: 'M4 11l8-7 8 7M6 10v9a1 1 0 0 0 1 1h3v-5h4v5h3a1 1 0 0 0 1-1v-9',
  today: 'M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM8 9h8M8 13h5',
  library: 'M3 4h4v16H3zM9 4h4v16H9zM15 5.2l3.8-1 3 14.8-3.8 1z',
  writing: 'M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19zM14.5 6.5l3 3',
  speaking: 'M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4M9 21h6',
  tracks: 'M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM8 17h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6',
  consolidation: 'M12 4l8 4-8 4-8-4zM4 12l8 4 8-4M4 16l8 4 8-4',
  errors: 'M12 4l9 16H3zM12 10v4M12 17.5v.01',
  stats: 'M5 20V12M12 20V5M19 20v-9',
  settings: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4',
  plus: 'M12 5v14M5 12h14',
  import: 'M12 4v10M8 10l4 4 4-4M5 19h14',
  filter: 'M4 5h16l-6 7v6l-4 2v-8z',
  sparkles: 'M12 4l1.8 4.7 4.7 1.8-4.7 1.8L12 17l-1.8-4.7L5.5 10.5l4.7-1.8zM18 16v4M16 18h4',
  copy: 'M9 8h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1zM5 16V5a1 1 0 0 1 1-1h10',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  target: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 12v.01',
  speaker: 'M4 10v4h4l5 4V6l-5 4zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11',
  history: 'M4 12a8 8 0 1 0 2.5-5.8M4 5v4h4M12 8v4l3 2',
  info: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 11v5M12 8v.01',
  check: 'M5 12.5l4.5 4.5L19 7',
  repeat: 'M4 11V9a3 3 0 0 1 3-3h12M16 3l3 3-3 3M20 13v2a3 3 0 0 1-3 3H5M8 21l-3-3 3-3',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'M6 6l12 12M18 6L6 18',
  'sidebar-collapse': 'M4 5h16v14H4zM9 5v14M16 10l-2 2 2 2',
  'sidebar-expand': 'M4 5h16v14H4zM9 5v14M14 10l2 2-2 2',
  'circle-alert': 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 8v5M12 16v.01',
  'circle-x': 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM9.5 9.5l5 5M14.5 9.5l-5 5',
  'circle-check': 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM8.5 12.5l2.5 2.5 4.5-5',
} as const

export type IconName = keyof typeof ICON_PATHS
export const ICON_NAMES = Object.keys(ICON_PATHS) as IconName[]

