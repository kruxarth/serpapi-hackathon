import { getSettings } from './shared'

const url = document.getElementById('url') as HTMLInputElement
const pres = document.getElementById('pres') as HTMLInputElement
const status = document.getElementById('status') as HTMLSpanElement

getSettings().then((s) => {
  url.value = s.backendUrl
  pres.checked = s.presentation
})

document.getElementById('save')!.addEventListener('click', async () => {
  let parsed: URL
  try {
    parsed = new URL(url.value)
  } catch {
    status.textContent = 'That is not a valid URL.'
    return
  }
  if (!['127.0.0.1', 'localhost'].includes(parsed.hostname) || parsed.protocol !== 'http:') {
    status.textContent = 'Use http://127.0.0.1:<port> or http://localhost:<port>.'
    return
  }
  await chrome.storage.local.set({ backendUrl: parsed.origin, presentation: pres.checked })
  status.textContent = 'Saved.'
})
