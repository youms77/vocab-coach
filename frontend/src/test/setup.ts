import '@testing-library/jest-dom/vitest'
import '../i18n'

import { cleanup, configure } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'

import i18n from '../i18n'
import { cancelSpeech } from '../speech/useSpeech'
import { uninstallFakeRecorder } from './fakeRecorder'
import { uninstallFakeSpeech } from './fakeSpeech'

// Pages load on demand (routes.tsx): the first import of a page is transformed by Vitest, which
// can exceed the 1 s default when many test files run at once.
configure({ asyncUtilTimeout: 5000 })

beforeEach(async () => {
  window.localStorage.clear()
  await i18n.changeLanguage('en')
})

afterEach(() => {
  cleanup()
  cancelSpeech()
  uninstallFakeSpeech()
  uninstallFakeRecorder()
})
