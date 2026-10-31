/**
 * A ref callback that sets the width of a bar through the CSSOM. The strict Content-Security-Policy
 * of the use mode (`style-src 'self'`, D-311) blocks a `style="..."` attribute, not a property set
 * from a script, so the bars keep their dynamic width without `'unsafe-inline'`.
 */
export function widthPercent(percent: number) {
  return (element: HTMLElement | null) => {
    if (element) element.style.width = `${percent}%`
  }
}
