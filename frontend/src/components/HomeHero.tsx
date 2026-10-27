import type { ReactNode } from 'react'

/**
 * The top of the home page: the photo (set in the stylesheet) under an indigo gradient, the date,
 * a greeting, one sentence and the single action. Only the home page uses it.
 */
export function HomeHero({
  date,
  title,
  text,
  children,
}: {
  date: string
  title: string
  text: string
  children?: ReactNode
}) {
  return (
    <section className="home-hero" aria-labelledby="home-hero-title">
      <div className="home-hero__content">
        <span className="home-hero__date">{date}</span>
        <h1 id="home-hero-title" className="home-hero__title">
          {title}
        </h1>
        <p className="home-hero__text">{text}</p>
        {children}
      </div>
    </section>
  )
}
