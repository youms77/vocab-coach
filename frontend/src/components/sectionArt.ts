/**
 * The illustration of a section landing page, one image per theme, exported from Canva as
 * `src/assets/sections/header-<section>-<light|dark>.png`. The files are found at build time: a
 * section whose two images are not there simply has a header without an illustration.
 */
const files = import.meta.glob<string>('../assets/sections/header-*-*.png', {
  eager: true,
  query: '?url',
  import: 'default',
})

export type ArtSection = 'library' | 'writing' | 'speaking' | 'errors'

export function sectionArt(section: ArtSection): { light: string; dark: string } | undefined {
  const light = files[`../assets/sections/header-${section}-light.png`]
  const dark = files[`../assets/sections/header-${section}-dark.png`]
  return light !== undefined && dark !== undefined ? { light, dark } : undefined
}
