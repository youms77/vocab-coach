import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CategoryCode } from './CategoryCode'
import { CorrectionMark } from './CorrectionMark'

describe('CategoryCode', () => {
  it('offers a line break after each dot and keeps the code readable as one text', () => {
    const { container } = render(<CategoryCode code="grammar.tense.past_simple_vs_present_perfect" />)
    const code = container.querySelector('code')
    expect(code?.textContent).toBe('grammar.tense.past_simple_vs_present_perfect')
    expect(code?.querySelectorAll('wbr')).toHaveLength(2)
  })

  it('leaves a code without a dot alone', () => {
    const { container } = render(<CategoryCode code="grammar" />)
    expect(container.querySelectorAll('wbr')).toHaveLength(0)
  })
})

describe('CorrectionMark', () => {
  it('shows the wrong fragment, an arrow and the fix, with words for a screen reader', () => {
    const { container } = render(
      <CorrectionMark wrong="I work" correction="I have been working" labels={{ wrong: 'Wrong', right: 'Right' }} />,
    )
    expect(container.querySelector('del')).toHaveTextContent('I work')
    expect(container.querySelector('ins')).toHaveTextContent('I have been working')
    expect(container.querySelectorAll('.visually-hidden')).toHaveLength(2)
  })

  it('shows only the wrong fragment when there is no fix', () => {
    const { container } = render(<CorrectionMark wrong="I work" />)
    expect(container.querySelector('ins')).toBeNull()
    expect(container.querySelector('del')).toHaveTextContent('I work')
  })
})
