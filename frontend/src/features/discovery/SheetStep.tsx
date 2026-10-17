import { useTranslation } from 'react-i18next'

import { useSheet } from '../../api/enrichment'
import { SpeakButton } from '../../speech/SpeakButton'
import { SheetView } from '../library/SheetView'
import { StepHeading } from '../session/StepHeading'
import { ErrorText } from '../settings/ErrorText'

/**
 * Step 3: the guess recalled, then the sheet read-only with the pronunciation and audio. The user
 * judges for themself: nothing is sent here (the guess goes with `complete`). Mounted only after
 * the guess, so the sheet is never requested before it.
 */
export function SheetStep({
  itemId,
  term,
  guess,
  onContinue,
}: {
  itemId: number
  term: string
  guess: string | null
  onContinue: () => void
}) {
  const { t } = useTranslation()
  const sheet = useSheet(itemId)

  return (
    <>
      <StepHeading>{t('discovery.sheet.title')}</StepHeading>
      <p className="discovery-guess">
        {guess !== null ? t('discovery.sheet.yourGuess', { guess }) : t('discovery.sheet.noGuess')}
      </p>
      <p className="muted">{t('discovery.sheet.compare')}</p>
      <p className="discovery-term">
        <strong lang="en">{term}</strong> <SpeakButton text={term} label={t('discovery.sheet.termLabel')} />
      </p>
      {sheet.isPending && <p className="muted">{t('discovery.sheet.loading')}</p>}
      {sheet.isError && <ErrorText error={sheet.error} />}
      {sheet.isSuccess &&
        (sheet.data !== null ? (
          <SheetView sheet={sheet.data.content} audio />
        ) : (
          <p className="muted">{t('discovery.sheet.missing')}</p>
        ))}
      <button type="button" className="button button--primary" onClick={onContinue}>
        {t('discovery.sheet.continue')}
      </button>
    </>
  )
}
