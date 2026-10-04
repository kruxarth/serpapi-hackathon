// Side panel: shows the current place's analysis, or its estimated cost and budget with a
// "Run analysis" button. Nothing is ever searched without that click (Rule 7).
import { backend, getSettings, lookupPlace, post, tabKey, type Lookup, type Summary, type TabPlace } from './shared'

const app = document.getElementById('app') as HTMLElement
let tabId: number | null = null
let running: EventSource | null = null

const esc = (s: unknown) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)

function levelClass(level: string) {
  return level === 'Not enough history' ? 'NotEnough' : level
}

async function activeTab(): Promise<chrome.tabs.Tab | undefined> {
  // ?tab=<id> lets the panel be opened as a normal page for a given tab (testing, or browsers without side panels).
  const forced = new URLSearchParams(location.search).get('tab')
  if (forced) return chrome.tabs.get(Number(forced))
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  return tab
}

async function render() {
  if (running) return
  const tab = await activeTab()
  tabId = tab?.id ?? null
  if (tabId === null) return
  const stored = (await chrome.storage.session.get(tabKey(tabId)))[tabKey(tabId)] as TabPlace | undefined
  if (!stored) {
    app.innerHTML = `<div class="box">Open a place on Google Maps to check its reviews.</div>`
    return
  }
  const lookup = await lookupPlace(stored.url) // refresh: an analysis may have finished since
  show(stored.url, lookup)
}

function show(url: string, lookup: Lookup) {
  switch (lookup.state) {
    case 'down':
      app.innerHTML = `<div class="box"><strong>Backend not running.</strong>
        <p class="secondary">Start it in the <code>backend</code> folder with:</p><pre>uv run reviewring serve</pre>
        <button id="retry">Try again</button></div>`
      document.getElementById('retry')!.onclick = render
      return
    case 'no_place':
      app.innerHTML = `<div class="box">Open a single place on Google Maps to check its reviews.</div>`
      return
    case 'demo':
      getSettings().then((s) => {
        app.innerHTML = `<div class="box"><strong>The backend is in demo mode.</strong>
          <p class="secondary">Demo mode uses prepared, pseudonymized examples, so it can't match real Google Maps pages.</p>
          <a href="${esc(s.backendUrl)}/" target="_blank">Open the demo in the web app</a></div>`
      })
      return
    case 'found':
      summary(lookup.summary, lookup.analysisId, lookup.ageDays, url)
      return
    case 'none':
      offer(url)
  }
}

async function summary(s: Summary, analysisId: string, ageDays: number, url: string) {
  const { backendUrl } = await getSettings()
  const age = ageDays < 1 ? 'today' : `${Math.floor(ageDays)} days ago`
  app.innerHTML = `
    <div class="box">
      ${s.title ? `<div class="secondary small">${esc(s.title)}</div>` : ''}
      <span class="level ${levelClass(s.level)}">${esc(s.level)}</span>
      ${s.headline ? `<div class="secondary" style="margin-top:6px">Main finding: <strong>${esc(s.headline)}</strong></div>` : ''}
      ${s.adjusted != null && s.sample_mean != null && Math.abs(s.adjusted - s.sample_mean) >= 0.01
        ? `<p><span class="big">${s.sample_mean.toFixed(2)}★ → ${s.adjusted.toFixed(2)}★</span><br>
           <span class="secondary small">latest ${s.examined} reviews, excluding linked reviewers</span></p>`
        : `<p><span class="big">Shows ${s.rating ?? '–'}★</span><br>
           <span class="secondary small">its latest ${s.examined} reviews average ${s.sample_mean?.toFixed(2) ?? '–'}★</span></p>`}
      <p class="small">${s.rings} ring-like group${s.rings === 1 ? '' : 's'} found · analysed ${age}</p>
      ${s.evidence.length ? `<ul>${s.evidence.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}
      <p><a href="${esc(backendUrl)}/analysis/${encodeURIComponent(analysisId)}" target="_blank">Open full report</a></p>
    </div>
    <p class="muted small">A pattern, not proof. A business can be targeted without its knowledge.</p>
    <button id="again">Analyse again…</button>`
  document.getElementById('again')!.onclick = () => offer(url)
}

async function offer(url: string) {
  app.innerHTML = `<div class="box muted">Estimating cost…</div>`
  try {
    const [est, budget] = await Promise.all([
      post<{ estimate: { min: number; max: number; lines: string[] }; needs_confirmation?: boolean }>('/api/resolve', { input: url }),
      backend<{ month_remaining: number; hour_remaining: number; mode: string }>('/api/budget'),
    ])
    const e = est.estimate
    const offline = budget.mode === 'offline'
    const tooMuch = !offline && e.max > budget.month_remaining
    app.innerHTML = `
      <div class="box">
        <strong>This place hasn't been analysed.</strong>
        <p>Estimated cost: <span class="big">${e.min}–${e.max}</span> searches</p>
        <ul class="small secondary">${e.lines.map((l) => `<li>${esc(l)}</li>`).join('')}</ul>
        <p class="small">Budget left: <strong>${budget.month_remaining}</strong> this month · <strong>${budget.hour_remaining}</strong> this hour</p>
        ${tooMuch ? `<p class="small" style="color:var(--critical)">Not enough searches left this month.</p>` : ''}
        <button class="primary" id="run" ${tooMuch ? 'disabled' : ''}>${offline ? 'Analyse from cache' : `Run analysis (up to ${e.max} searches)`}</button>
      </div>`
    document.getElementById('run')!.onclick = () => run(url)
  } catch (err) {
    app.innerHTML = `<div class="box">${esc((err as Error).message)}</div>`
  }
}

async function run(url: string) {
  const { backendUrl } = await getSettings()
  app.innerHTML = `<div class="box">Starting…</div>`
  let id: string
  try {
    id = (await post<{ analysis_id: string }>('/api/analyses', { input: url })).analysis_id
  } catch (err) {
    app.innerHTML = `<div class="box">${esc((err as Error).message)}</div>`
    return
  }
  running = new EventSource(`${backendUrl}/api/analyses/${encodeURIComponent(id)}/events`)
  running.onmessage = async (m) => {
    const e = JSON.parse(m.data)
    const done = Number(e.data?.done ?? 0)
    const total = Number(e.data?.total ?? 0)
    app.innerHTML = `<div class="box"><strong>${esc(e.message)}</strong>
      <p class="small secondary">Searches used: ${e.searches_used}</p>
      ${total ? `<div class="bar"><div style="width:${(100 * done) / total}%"></div></div>` : ''}
      <p><button id="cancel">Cancel</button></p></div>`
    document.getElementById('cancel')?.addEventListener('click', () => post(`/api/analyses/${encodeURIComponent(id)}/cancel`, {}))
    if (['done', 'cancelled', 'error', 'paused', 'needs_input'].includes(e.type)) {
      running?.close()
      running = null
      if (e.type === 'done') show(url, await lookupPlace(url))
      else if (e.type === 'paused') {
        app.innerHTML = `<div class="box"><strong>Paused: waiting for the hourly search limit.</strong>
          <p class="secondary">Resume it from the <a href="${esc(backendUrl)}/analysis/${encodeURIComponent(id)}" target="_blank">web app</a>. Nothing already fetched is requested again.</p></div>`
      } else {
        app.innerHTML = `<div class="box">${esc(e.message)}<p><a href="${esc(backendUrl)}/analysis/${encodeURIComponent(id)}" target="_blank">Open in the web app</a></p></div>`
      }
    }
  }
  running.onerror = () => {
    running?.close()
    running = null
    app.innerHTML = `<div class="box">Lost contact with the backend. <button id="retry">Refresh</button></div>`
    document.getElementById('retry')!.onclick = render
  }
}

chrome.tabs.onActivated.addListener(render)
chrome.storage.session.onChanged.addListener((changes) => {
  if (tabId !== null && changes[tabKey(tabId)]) render()
})
render()
