// Side panel: check a place's reviews and read the ones worth reading. The place comes from the Google Maps tab, or
// from a link pasted at the top. Nothing is fetched without the "Check reviews" click (Rule 7). The reader chooses
// which warning signs to set aside; the rating and the list of kept reviews follow that choice.
import { backend, getSettings, lookupPlace, post, tabKey, type Lookup, type TabPlace } from './shared'

const app = document.getElementById('app') as HTMLElement
const form = document.getElementById('link-form') as HTMLFormElement
const linkInput = document.getElementById('link') as HTMLInputElement
let tabId: number | null = null
let running: EventSource | null = null
let pasted: string | null = null // a link the reader pasted wins over the tab until they clear it

const esc = (s: unknown) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)

const stars = (n: number | null) =>
  n == null ? '' : `<span class="stars">${'★'.repeat(n)}<span class="off">${'★'.repeat(Math.max(0, 5 - n))}</span></span>`

const fmt = (v: number | null | undefined, d = 2) => (v == null ? '–' : v.toFixed(d))

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
  if (pasted) {
    show(pasted, await lookupPlace(pasted))
    return
  }
  const tab = await activeTab()
  tabId = tab?.id ?? null
  if (tabId === null) return
  const stored = (await chrome.storage.session.get(tabKey(tabId)))[tabKey(tabId)] as TabPlace | undefined
  if (!stored) {
    app.innerHTML = `<div class="box muted">Open a place on Google Maps, or paste a link above, to check its reviews.</div>`
    return
  }
  show(stored.url, await lookupPlace(stored.url)) // refresh: an analysis may have finished since
}

function show(url: string, lookup: Lookup) {
  switch (lookup.state) {
    case 'down':
      app.innerHTML = `<div class="box"><strong>The ReviewRing app isn't running.</strong>
        <p class="secondary">Start it in the <code>backend</code> folder with:</p><pre>uv run reviewring serve</pre>
        <button id="retry">Try again</button></div>`
      document.getElementById('retry')!.onclick = render
      return
    case 'no_place':
      app.innerHTML = `<div class="box">That isn't a single place. Open one place on Google Maps, or paste its link.</div>`
      return
    case 'demo':
      getSettings().then((s) => {
        app.innerHTML = `<div class="box"><strong>The app is in demo mode.</strong>
          <p class="secondary">Demo mode shows prepared examples, so it can't check real places.</p>
          <a href="${esc(s.backendUrl)}/" target="_blank">Open the examples</a></div>`
      })
      return
    case 'found':
      reviews(lookup.analysisId, lookup.ageDays, url)
      return
    case 'none':
      offer(url)
  }
}

interface Row {
  review_id: string
  contributor_id: string | null
  display_name?: string
  rating: number | null
  day: string | null
  text: string | null
  excerpt?: string | null
  reviewer_reviews: number | null
  signs?: string[]
  ai?: { verdict: string; cues: string[] } | null
  generated_marker?: string | null
}
interface SignInfo { name: string; short: string; strength: string; explain: string; count: number }
interface FullReport {
  place: { title: string | null; rating: number | null; total_reviews: number | null }
  level: { level: string; reasons: string[] }
  reviews: Row[]
  names?: Record<string, string>
  pseudonymized?: boolean
  sieve?: { order: string[]; set_aside_by_default: string[]; signs: Record<string, SignInfo>; all: { mean: number | null }; ai: { judged: number } }
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const day = (iso: string | null) => (iso ? `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}` : '')

/** The text with the phrases an AI model quoted (and any chatbot phrase) underlined. */
function marked(text: string, marks: string[]): string {
  const low = text.toLowerCase()
  const spans = marks.map((m) => [low.indexOf(m.toLowerCase()), m.length] as const).filter(([i]) => i >= 0).sort((a, b) => a[0] - b[0])
  let out = ''
  let pos = 0
  for (const [i, n] of spans) {
    if (i < pos) continue
    out += esc(text.slice(pos, i)) + `<mark class="cue">${esc(text.slice(i, i + n))}</mark>`
    pos = i + n
  }
  return out + esc(text.slice(pos))
}

async function reviews(analysisId: string, ageDays: number, url: string) {
  const { backendUrl, presentation } = await getSettings()
  let report: FullReport
  try {
    const detail = await backend<{ report: FullReport | null }>(`/api/analyses/${encodeURIComponent(analysisId)}?presentation=${presentation ? 1 : 0}`)
    if (!detail.report) throw new Error('This analysis has no report yet.')
    report = detail.report
  } catch (err) {
    app.innerHTML = `<div class="box">${esc((err as Error).message)}</div>`
    return
  }
  const sieve = report.sieve
  const full = `${esc(backendUrl)}/analysis/${encodeURIComponent(analysisId)}`
  const age = ageDays < 1 ? 'today' : `${Math.floor(ageDays)} days ago`
  if (!sieve) {
    app.innerHTML = `<div class="box"><span class="level ${levelClass(report.level.level)}">${esc(report.level.level)}</span>
      <p class="secondary">This check predates warning signs. <button id="again">Check again</button></p>
      <p><a href="${full}" target="_blank">Open the full report</a></p></div>`
    document.getElementById('again')!.onclick = () => run(url)
    return
  }
  const aside = new Set(sieve.set_aside_by_default)
  const signs = sieve.order.filter((k) => sieve.signs[k].count > 0)
  const name = (r: Row) => r.display_name ?? report.names?.[r.contributor_id ?? ''] ?? 'A reviewer'
  let shown = 10

  const draw = () => {
    const kept = report.reviews.filter((r) => !(r.signs ?? []).some((s) => aside.has(s)))
    const rated = kept.map((r) => r.rating).filter((x): x is number => x != null)
    const mean = rated.length ? rated.reduce((a, b) => a + b, 0) / rated.length : null
    app.innerHTML = `
      <div class="box">
        ${report.place.title ? `<div class="secondary small">${esc(report.place.title)}</div>` : ''}
        <div class="kept-line"><span class="big">${fmt(mean)}<span class="gold">★</span></span>
          <span class="secondary small">from the ${kept.length} of ${report.reviews.length} newest reviews you kept</span></div>
        <div class="small secondary">Google shows ${report.place.rating ?? '–'}★. All ${report.reviews.length} newest average ${fmt(sieve.all.mean)}★.</div>
        <div style="margin-top:8px"><span class="level ${levelClass(report.level.level)}">${esc(report.level.level)}</span>
          <span class="muted small">checked ${age}</span></div>
      </div>
      <div class="box">
        <strong>Set aside reviews with</strong>
        ${signs.length ? signs.map((k) => {
          const s = sieve.signs[k]
          return `<label class="sign ${esc(s.strength)}" title="${esc(s.explain)}">
            <input type="checkbox" data-sign="${esc(k)}" ${aside.has(k) ? 'checked' : ''} />
            <span class="sign-name">${esc(s.name)}</span><span class="num muted">${s.count}</span></label>`
        }).join('') : '<p class="secondary small">No warning signs among these reviews.</p>'}
        <p class="muted small">Solid signs are near-certain. "Reads as AI-written" is an AI model's opinion, and first-time accounts are often real customers, so those start kept.</p>
      </div>
      <div class="list-head"><strong>Reviews you kept</strong> <span class="muted small">${kept.length}</span></div>
      ${kept.slice(0, shown).map((r) => {
        const text = r.text ?? r.excerpt
        const marks = [...(r.ai?.verdict === 'ai_style' ? r.ai.cues : []), ...(r.generated_marker ? [r.generated_marker] : [])]
        const acct = r.reviewer_reviews == null ? '' : r.reviewer_reviews <= 1 ? 'no other reviews' : `${r.reviewer_reviews} reviews`
        const other = (r.signs ?? []).map((s) => sieve.signs[s]?.short).filter(Boolean)
        return `<article class="rev">
          <div class="rev-head"><span>${stars(r.rating)}</span><span class="muted small">${esc(day(r.day))}</span></div>
          <div class="small secondary">${esc(name(r))}${acct ? ` · ${esc(acct)}` : ''}</div>
          <p class="rev-text">${text ? marked(text, marks) : `<span class="muted">${report.pseudonymized ? 'Text hidden in presentation mode.' : 'No text, only stars.'}</span>`}</p>
          ${other.length ? `<div class="muted small">Also: ${other.map(esc).join(', ')}</div>` : ''}
        </article>`
      }).join('')}
      ${kept.length > shown ? `<button id="more">Show more (${kept.length - shown} left)</button>` : ''}
      <p><a href="${full}" target="_blank">Open the full report</a> · <button id="again" class="link">Check again</button></p>
      <p class="muted small">A pattern, not proof. A business can be targeted without its knowledge.</p>`
    app.querySelectorAll<HTMLInputElement>('input[data-sign]').forEach((el) => {
      el.onchange = () => {
        if (el.checked) aside.add(el.dataset.sign!)
        else aside.delete(el.dataset.sign!)
        draw()
      }
    })
    document.getElementById('more')?.addEventListener('click', () => {
      shown += 20
      draw()
    })
    document.getElementById('again')!.onclick = () => run(url)
  }
  draw()
}

function offer(url: string) {
  app.innerHTML = `
    <div class="box">
      <strong>This place hasn't been checked yet.</strong>
      <p class="secondary small">ReviewRing reads its newest 100 reviews and the histories of the most unusual reviewers. It takes about a minute.</p>
      <button class="primary" id="run">Check reviews</button>
    </div>`
  document.getElementById('run')!.onclick = () => run(url)
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
  const full = `${esc(backendUrl)}/analysis/${encodeURIComponent(id)}`
  running = new EventSource(`${backendUrl}/api/analyses/${encodeURIComponent(id)}/events`)
  running.onmessage = async (m) => {
    const e = JSON.parse(m.data)
    const done = Number(e.data?.done ?? 0)
    const total = Number(e.data?.total ?? 0)
    if (e.type !== 'history' && e.type !== 'picks' && e.type !== 'links' && e.type !== 'reviews_loaded') {
      app.innerHTML = `<div class="box"><strong>${esc(e.message)}</strong>
        ${total ? `<div class="bar"><div style="width:${(100 * done) / total}%"></div></div>` : ''}
        <p class="small"><a href="${full}" target="_blank">Watch it in the app</a></p>
        <p><button id="cancel">Cancel</button></p></div>`
      document.getElementById('cancel')?.addEventListener('click', () => post(`/api/analyses/${encodeURIComponent(id)}/cancel`, {}))
    }
    if (['done', 'cancelled', 'error', 'paused', 'needs_input'].includes(e.type)) {
      running?.close()
      running = null
      if (e.type === 'done') show(url, await lookupPlace(url))
      else if (e.type === 'paused') {
        app.innerHTML = `<div class="box"><strong>Paused: too many checks this hour.</strong>
          <p class="secondary">Resume it from the <a href="${full}" target="_blank">app</a>. Nothing already fetched is fetched again.</p></div>`
      } else if (e.type === 'needs_input') {
        app.innerHTML = `<div class="box">Several places match. <a href="${full}" target="_blank">Pick one in the app</a>.</div>`
      } else {
        app.innerHTML = `<div class="box">${esc(e.message)}<p><a href="${full}" target="_blank">Open in the app</a></p></div>`
      }
    }
  }
  running.onerror = () => {
    running?.close()
    running = null
    app.innerHTML = `<div class="box">Lost contact with the ReviewRing app. <button id="retry">Refresh</button></div>`
    document.getElementById('retry')!.onclick = render
  }
}

form.onsubmit = (ev) => {
  ev.preventDefault()
  const v = linkInput.value.trim()
  pasted = v || null
  render()
}
linkInput.oninput = () => {
  if (!linkInput.value.trim() && pasted) {
    pasted = null
    render()
  }
}

chrome.tabs.onActivated.addListener(() => {
  if (!pasted) render()
})
chrome.storage.session.onChanged.addListener((changes) => {
  if (!pasted && tabId !== null && changes[tabKey(tabId)]) render()
})
render()
