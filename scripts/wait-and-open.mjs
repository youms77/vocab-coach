// Opens the browser once the app can really be used (D-036). Node >= 22, no dependency.
//
// Run by `npm run dev` as a third `concurrently` process. It polls the API's `/api/health` until
// it answers `status: "ok"`, then the Vite page, every 500 ms for at most 90 s, and opens the
// default browser. It always exits with code 0, so it never stops the servers, even on timeout.
// Does nothing unless VOCAB_OPEN_BROWSER=1 (set by start.ps1 / start.sh without -NoBrowser).

import { spawn } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { setTimeout as sleep } from 'node:timers/promises'

const POLL_MS = 500
const TIMEOUT_MS = 90_000
const REQUEST_TIMEOUT_MS = 2_000

if (process.env.VOCAB_OPEN_BROWSER !== '1') {
  console.log('Browser opening is off.')
  process.exit(0)
}

// Same addresses as the Vite dev server and its /api proxy (frontend/vite.config.ts reads this
// file too, and honours the same VOCAB_BACKEND_URL override).
const devServer = JSON.parse(
  await readFile(new URL('../frontend/dev-server.json', import.meta.url), 'utf8'),
)
const backendUrl = process.env.VOCAB_BACKEND_URL ?? devServer.backendUrl
// Use mode (M10.b): the backend serves the page itself, on its own port.
const useMode = process.env.VOCAB_USE_MODE === '1'
const appUrl = useMode ? new URL('/', backendUrl).href : `http://${devServer.host}:${devServer.port}/`
const healthUrl = new URL('/api/health', backendUrl).href

async function answers(url, accept) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) })
    return response.ok && (await accept(response))
  } catch {
    return false // not listening yet
  }
}

async function waitFor(url, accept, deadline) {
  while (Date.now() < deadline) {
    if (await answers(url, accept)) return true
    await sleep(POLL_MS)
  }
  return false
}

function openBrowser(url) {
  const [command, args, options] =
    process.platform === 'win32'
      ? // `start` is a cmd.exe built-in; the empty string is the window title.
        ['cmd.exe', ['/d', '/s', '/c', `start "" "${url}"`], { windowsVerbatimArguments: true }]
      : [process.platform === 'darwin' ? 'open' : 'xdg-open', [url], {}]
  const child = spawn(command, args, { ...options, detached: true, stdio: 'ignore' })
  child.on('error', () => console.log(`Could not open a browser. Open ${url} yourself.`))
  child.unref()
}

const deadline = Date.now() + TIMEOUT_MS
const apiReady = await waitFor(
  healthUrl,
  async (response) => (await response.json()).status === 'ok',
  deadline,
)
const pageReady =
  apiReady &&
  (await waitFor(
    appUrl,
    async (response) => (response.headers.get('content-type') ?? '').includes('text/html'),
    deadline,
  ))

if (pageReady) {
  console.log(`App ready: opening ${appUrl}`)
  openBrowser(appUrl)
} else {
  console.log(
    `The app did not answer within ${TIMEOUT_MS / 1000} s, so no browser was opened. ` +
      `The servers keep running: check the api and web logs, then open ${appUrl} yourself.`,
  )
}
