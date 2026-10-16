import '@testing-library/jest-dom/vitest'
import '../i18n'

import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'

import i18n from '../i18n'

beforeEach(async () => {
  window.localStorage.clear()
  await i18n.changeLanguage('en')
})

afterEach(() => {
  cleanup()
})
