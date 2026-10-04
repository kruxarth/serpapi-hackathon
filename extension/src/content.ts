// Runs on Google Maps. Watches for the place (data_id) changing, not the URL: Maps rewrites the
// viewport part of the URL every time the map moves. Draws a small badge in a Shadow DOM so
// Google's styles can't leak in. Never calls the backend itself; the service worker does.

const DATA_ID = /0x[0-9a-f]+:0x[0-9a-f]+/gi

function currentDataId(): string | null {
  let href = window.location.href
  try {
    href = decodeURIComponent(decodeURIComponent(href))
  } catch {
    /* keep the raw URL */
  }
  const ids = [...new Set((href.match(DATA_ID) ?? []).map((s) => s.toLowerCase()))]
  return ids.length === 1 ? ids[0] : null
}

let lastId: string | null | undefined
let host: HTMLDivElement | null = null
let button: HTMLButtonElement | null = null

function ensureBadge(): HTMLButtonElement {
  if (button && host?.isConnected) return button
  host = document.createElement('div')
  host.style.cssText = 'position:fixed;top:76px;right:72px;z-index:2147483000;'
  const root = host.attachShadow({ mode: 'closed' })
  root.innerHTML = `
    <style>
      button { all: initial; font: 600 13px/1.3 system-ui, -apple-system, 'Segoe UI', sans-serif; cursor: pointer;
        display: inline-flex; gap: 8px; align-items: center; padding: 7px 12px; border-radius: 999px;
        background: #fcfcfb; color: #0b0b0b; border: 2px solid #c3c2b7; box-shadow: 0 2px 10px rgba(0,0,0,.18); }
      button:focus-visible { outline: 2px solid #2a78d6; outline-offset: 2px; }
      .dot { width: 10px; height: 10px; border-radius: 50%; border: 2px solid #52514e; box-sizing: border-box; }
      /* Deliberately neutral: no red badge on a business's own Maps page. The level is in the text. */
      .sub { font-weight: 400; color: #52514e; }
    </style>
    <button type="button" aria-label="ReviewRing"><span class="dot"></span><span class="text">ReviewRing</span></button>`
  button = root.querySelector('button')!
  button.addEventListener('click', async () => {
    const res = await chrome.runtime.sendMessage({ type: 'openPanel' }).catch(() => ({ ok: false }))
    if (!res?.ok) setBadge('', 'Click the ReviewRing icon for details')
  })
  document.documentElement.appendChild(host)
  return button
}

function setBadge(cls: string, text: string, sub = '') {
  const b = ensureBadge()
  b.className = cls
  const t = b.querySelector('.text') as HTMLSpanElement
  t.innerHTML = ''
  t.append(document.createTextNode(text))
  if (sub) {
    const s = document.createElement('span')
    s.className = 'sub'
    s.textContent = ` · ${sub}`
    t.append(s)
  }
}

function hideBadge() {
  host?.remove()
  host = null
  button = null
}

async function check() {
  const id = currentDataId()
  if (id === lastId) return
  lastId = id
  if (!id) {
    hideBadge()
    return
  }
  setBadge('', 'ReviewRing', 'checking…')
  const res = await chrome.runtime.sendMessage({ type: 'placeChanged', url: window.location.href }).catch(() => null)
  if (id !== lastId) return // the user moved on meanwhile
  const lookup = res?.lookup
  if (!lookup || lookup.state === 'down') setBadge('', 'Backend not running')
  else if (lookup.state === 'found') {
    const s = lookup.summary
    const age = lookup.ageDays < 1 ? 'today' : `${Math.floor(lookup.ageDays)}d ago`
    const reason = s.headline ?? (s.level === 'Low' ? 'no linked groups found' : '')
    setBadge('', `Reviews checked: ${s.level}`, [reason, age].filter(Boolean).join(' · '))
  } else if (lookup.state === 'demo') setBadge('', 'ReviewRing', 'demo mode')
  else setBadge('', 'Check reviews')
}

setInterval(check, 800)
window.addEventListener('popstate', check)
check()
