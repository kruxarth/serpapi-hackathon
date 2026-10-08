import { ArrowLeft, ChevronRight, Info, Network, Play, RotateCcw, ShieldAlert, Sparkles, Undo2, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Finding, pairEvidence, Strength } from '../components/Findings'
import { eventsFromReport, Investigation, usePlayback } from '../components/Investigation'
import { MapView } from '../components/MapView'
import { CheckedGrid, ReviewerProvider } from '../components/Reviewer'
import { BranchTabs, ReviewList } from '../components/ReviewList'
import { RingGraph } from '../components/RingGraph'
import { type Branch, SieveGraph, type SieveState, useSieve } from '../components/Sieve'
import { ClientTable, ReviewsTable } from '../components/Tables'
import { Timeline } from '../components/Timeline'
import { LevelBadge, StarBar } from '../components/ui'
import { ageText, day, FLAGGED_VERDICTS, fmt, levelClass, VERDICT_TEXT } from '../labels'
import { makeNamer } from '../names'
import { usePresentation } from '../presentation'
import type { AnalysisDetail, ProgressEvent, Report } from '../types'

const CHAPTERS = [
  ['verdict', 'Verdict'],
  ['reviews', 'Sort the reviews'],
  ['findings', 'Findings'],
  ['timeline', 'Timeline'],
  ['linked', 'Reviewers'],
  ['checked', 'What was checked'],
] as const

export function ReportView({ detail }: { detail: AnalysisDetail }) {
  const report = detail.report as Report
  const pres = usePresentation()
  const namer = useMemo(() => makeNamer(report), [report])
  const [selected, setSelected] = useState<string | null>(null)
  const select = useCallback((g: string | null) => setSelected(g), [])
  const showGroup = (g: string) => {
    setSelected(g)
    document.getElementById('linked')?.scrollIntoView({ behavior: 'smooth' })
  }
  const findings = useMemo(() => pairEvidence(report), [report])
  const [replay, setReplay] = useState(false)
  const sieve = useSieve(report)

  return (
    <ReviewerProvider report={report} namer={namer}>
    <div className="report">
      <Rail />
      <div>
        <Verdict report={report} detail={detail} sieve={sieve} onReplay={() => setReplay(true)} />

        {report.sieve
          ? <Sorting report={report} state={sieve} namer={namer} presentation={pres.on || !!report.pseudonymized} />
          : (
            <section id="reviews" className="chapter">
              <ChapterHead title="Reviews examined" />
              <div className="notice small" style={{ marginBottom: 16 }}><Info size={15} />This report predates warning signs. Re-run it from the cache to sort its reviews: <code>uv run reviewring analyze {report.analysis?.id ?? '<id>'}</code></div>
              <div className="panel pad"><ReviewsTable report={report} namer={namer} selectedGroup={selected} /></div>
            </section>
          )}

        <section id="findings" className="chapter">
          <ChapterHead title="What we found" note={report.evidence.length > 1 ? 'Strongest first' : undefined} />
          {report.evidence.length === 0 && <div className="empty-line"><Info size={18} /> Nothing crossed a reporting threshold.</div>}
          {findings.map((f, i) => <Finding key={`${f.e.kind}-${i}`} {...f} ctx={{ report, namer, onShowGroup: showGroup }} />)}
          {report.ai_summary && (
            
              <details className="summary-ai">
                <summary><ChevronRight size={16} className="chev" /><Sparkles size={15} /> Plain-language summary written by AI from the facts above</summary>
                <div className="secondary" style={{ padding: '0 0 22px 26px', display: 'grid', gap: 10, maxWidth: '72ch' }}>
                  {report.ai_summary.paragraphs.map((p) => <p key={p}>{p}</p>)}
                  <p className="muted small">
                    {report.ai_summary.source === 'llm'
                      ? `Written by ${report.ai_summary.model} (prompt ${report.ai_summary.prompt_version}) from numbered facts; every number, name and place was filled in by ReviewRing, not the AI.`
                      : 'Written from fixed templates (no AI key set, or the AI draft failed validation).'}
                  </p>
                </div>
              </details>
            
          )}
        </section>

        <section id="timeline" className="chapter">
          <ChapterHead title="Timeline of the newest reviews" note={`${report.sample.examined} reviews, ${day(report.sample.first)} to ${day(report.sample.last)}`} />
          <div className="panel pad"><Timeline report={report} selectedGroup={selected} /></div>
        </section>

        <Linked report={report} namer={namer} selected={selected} select={select} presentation={pres.on || !!report.pseudonymized} />

        <Checked report={report} detail={detail} />
      </div>
    </div>
    <AnimatePresence>{replay && <Replay report={report} onClose={() => setReplay(false)} />}</AnimatePresence>
    </ReviewerProvider>
  )
}

function ChapterHead({ title, note }: { title: string; note?: string }) {
  return (
    <div className="chapter-head">
      <h2>{title}</h2>
      {note && <span className="muted">{note}</span>}
    </div>
  )
}

/** Sticky chapter list that follows the scroll position. */
function Rail() {
  const [active, setActive] = useState<string>('verdict')
  useEffect(() => {
    const seen = new Map<string, number>()
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => seen.set(e.target.id, e.isIntersecting ? e.intersectionRatio : 0))
      const best = CHAPTERS.map(([id]) => id).find((id) => (seen.get(id) ?? 0) > 0)
      if (best) setActive(best)
    }, { rootMargin: '-90px 0px -55% 0px', threshold: [0, 0.01] })
    CHAPTERS.forEach(([id]) => {
      const el = document.getElementById(id)
      if (el) io.observe(el)
    })
    return () => io.disconnect()
  }, [])
  return (
    <nav className="rail" aria-label="Report sections">
      <Link to="/" className="row muted" style={{ gap: 6, marginBottom: 18, paddingLeft: 16, textDecoration: 'none' }}><ArrowLeft size={14} /> All analyses</Link>
      {CHAPTERS.map(([id, text]) => (
        <a key={id} href={`#${id}`} className={active === id ? 'on' : ''}
          onClick={(e) => {
            e.preventDefault()
            document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
          }}>
          {active === id && <motion.span layoutId="rail-mark" className="rail-mark" transition={{ type: 'spring', stiffness: 400, damping: 34 }} />}
          {text}
        </a>
      ))}
    </nav>
  )
}

/* ---------- 1. Verdict ---------- */

function Verdict({ report, detail, sieve, onReplay }: { report: Report; detail: AnalysisDetail; sieve: SieveState; onReplay: () => void }) {
  const r = report.ratings
  const p = report.place
  const stale = detail.finished_at && Date.now() - Date.parse(detail.finished_at) > 7 * 86_400_000
  const lv = report.level.level
  const where = [p.type, p.area].filter(Boolean)
  const kept = report.sieve ? sieve.keptMean : r.without_ring_and_suspicious
  const keptN = report.sieve ? sieve.keptCount : r.examined
  return (
    <section id="verdict" className={`chapter verdict ${levelClass(lv)}`}>
      <div className="verdict-top">
        <span>{where.length === 2 ? `${where[0]} in ${where[1]}` : where[0] ?? 'Place'}</span>
        {detail.synthetic && <span className="chip accent">Synthetic example</span>}
        {report.pseudonymized && !detail.synthetic && <span className="chip">Pseudonymized</span>}
        {report.dates_shifted && <span className="chip" title="All dates moved by the same hidden offset; intervals are unchanged">Dates shifted</span>}
        <span className="spacer" />
        {detail.finished_at && <span className="muted small">Analysed {ageText(detail.finished_at)}</span>}
      </div>
      <h1>{p.title ?? 'This business'}</h1>

      <div className="verdict-stage">
        <div className="panel ladder">
          {p.rating != null && (
            <LadderRow label="Google shows" value={p.rating} note={p.total_reviews ? `from ${p.total_reviews.toLocaleString('en-IN')} reviews` : undefined} />
          )}
          <LadderRow label={`The newest ${r.examined}`} value={r.sample_mean} note={report.sample.first ? `${day(report.sample.first)} to ${day(report.sample.last)}` : undefined} />
          <LadderRow label="After setting aside" value={kept} strong
            note={keptN === r.examined ? 'nothing set aside' : `${keptN} of ${r.examined} reviews kept`} />
          {r.overall && (
            <p className="small muted" style={{ marginTop: 6 }}>
              Across all {r.overall.total_as_displayed.toLocaleString('en-IN')} reviews, without the linked reviewers:{' '}
              {r.overall.no_visible_change
                ? 'no visible change; the effect is concentrated in recent reviews.'
                : <><strong className="num">{r.overall.low.toFixed(2)}–{r.overall.high.toFixed(2)}★</strong> instead of {r.overall.displayed}★.</>}
            </p>
          )}
        </div>

        <div className="why">
          <LevelBadge level={lv} size="big" />
          <ul>{report.level.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
          <div className="col" style={{ gap: 10, marginTop: 18 }}>
            {report.warnings.map((w) => <div key={w} className="notice warn small"><ShieldAlert size={15} />{w}</div>)}
            {stale && <div className="notice small"><Info size={15} />Analysed {ageText(detail.finished_at)}. Reviews may have changed since.</div>}
          </div>
          {report.sample.expanded > 0 && (
            <button className="replay-cta" onClick={onReplay}>
              <span className="replay-icon"><Play size={16} fill="currentColor" /></span>
              <span className="col" style={{ alignItems: 'flex-start' }}>
                <strong>Watch the investigation</strong>
                <span className="muted small">{report.sample.examined} reviews read, {report.sample.expanded} reviewer histories opened</span>
              </span>
            </button>
          )}
          <div className="caveat-strip">
            <Info size={16} className="muted" />
            A pattern, not proof. A business can be targeted without its knowledge.
          </div>
        </div>
      </div>
    </section>
  )
}

function LadderRow({ label, value, note, strong }: { label: string; value: number | null | undefined; note?: string; strong?: boolean }) {
  return (
    <div className={`ladder-row ${strong ? 'strong' : ''}`}>
      <div className="col">
        <span className="ladder-label">{label}</span>
        {note && <span className="tiny muted">{note}</span>}
      </div>
      {value != null && <StarBar value={value} duration={1.2} className="ladder-stars" />}
      <span className="fig ladder-fig">{fmt(value, 2)}</span>
    </div>
  )
}

/* ---------- 2. Sorting the reviews ---------- */

function Sorting({ report, state, namer, presentation }: { report: Report; state: SieveState; namer: ReturnType<typeof makeNamer>; presentation: boolean }) {
  const sieve = report.sieve!
  const [branch, setBranch] = useState<Branch>('kept')
  const select = (b: Branch) => {
    setBranch(b)
    document.getElementById('review-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  // A branch that empties (its sign was kept) falls back to the kept reviews.
  const shown: Branch = branch !== 'kept' && !(state.aside.has(branch) && (state.groups[branch]?.length ?? 0) > 0) ? 'kept' : branch
  const none = sieve.order.filter((k) => sieve.signs[k].count === 0)
  const ai = sieve.ai
  return (
    <section id="reviews" className="chapter">
      <ChapterHead title={`Sort the newest ${sieve.examined} reviews`} />
      <p className="chapter-lede">
        Each dot is a review, coloured by its stars. A review leaves the line at the first warning sign you set aside;
        the rest are kept. Switch a sign off to keep those reviews, or on to set them aside.
      </p>
      <div className="panel pad sieve-panel">
        <SieveGraph report={report} state={state} selected={shown} onSelect={select} />
        <div className="sieve-foot">
          <div className="legend">
            <span><i className="swatch" style={{ background: 'var(--label-suspicious)' }} /> Near-certain signs, set aside at first</span>
            <span><i className="swatch dashed" style={{ ['--tone' as string]: 'var(--label-suspicious)' }} /> An AI model's opinion</span>
            <span><i className="swatch" style={{ background: 'var(--label-none)' }} /> True of many real customers too</span>
            {!state.isDefault && <button className="btn ghost sm" onClick={state.reset}><Undo2 size={14} /> Back to the defaults</button>}
          </div>
          <div className="small secondary col" style={{ gap: 4 }}>
            {none.length > 0 && <span>Also checked, none found: {none.map((k) => sieve.signs[k].short.charAt(0).toLowerCase() + sieve.signs[k].short.slice(1)).join(', ')}.</span>}
            {ai.judged > 0
              ? <span>An AI model read the {ai.judged} review{ai.judged === 1 ? '' : 's'} with at least {ai.min_words} words for AI-written style; {ai.too_short} {ai.too_short === 1 ? 'was' : 'were'} too short to judge.</span>
              : ai.eligible > 0
                ? <span>The AI-written check didn't run for this analysis (no AI key was set). {ai.eligible} reviews are long enough to judge.</span>
                : <span>No review is long enough ({ai.min_words}+ words) for the AI-written check.</span>}
          </div>
        </div>
      </div>
      <div id="review-list" style={{ marginTop: 34, scrollMarginTop: 90 }}>
        <BranchTabs report={report} state={state} selected={shown} onSelect={setBranch} />
        <ReviewList key={shown} report={report} state={state} branch={shown} namer={namer} presentation={presentation} />
      </div>
    </section>
  )
}

/** The investigation again, rebuilt from the report: costs nothing, good for recordings. */
function Replay({ report, onClose }: { report: Report; onClose: () => void }) {
  const events = useMemo(() => eventsFromReport(report), [report])
  const [run, setRun] = useState(0)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])
  return (
    <motion.div className="replay" role="dialog" aria-modal="true" aria-label="Investigation replay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="replay-inner">
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 18 }}>
          <div>
            <div className="muted small">Replay, rebuilt from the report</div>
            <h2 style={{ fontSize: '2.2rem' }}>{report.place.title ?? 'This business'}</h2>
          </div>
          <div className="row">
            <button className="btn sm" onClick={() => setRun((x) => x + 1)}><RotateCcw size={14} /> Restart</button>
            <button className="icon-btn" onClick={onClose} aria-label="Close replay"><X size={16} /></button>
          </div>
        </div>
        <ReplayPlayer key={run} events={events} onDone={onClose} />
      </div>
    </motion.div>
  )
}

function ReplayPlayer({ events, onDone }: { events: ProgressEvent[]; onDone: () => void }) {
  const { state } = usePlayback(events)
  return (
    <div className="panel pad">
      <Investigation state={state} />
      {state.finished && (
        <motion.div className="row" style={{ marginTop: 18, justifyContent: 'flex-end' }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
          <button className="btn primary" onClick={onDone}>See the evidence <ChevronRight size={16} /></button>
        </motion.div>
      )}
    </div>
  )
}

/* ---------- 4. Linked reviewers ---------- */

function Linked({ report, namer, selected, select, presentation }: {
  report: Report; namer: ReturnType<typeof makeNamer>; selected: string | null; select: (g: string | null) => void; presentation: boolean
}) {
  const shown = report.groups.filter((g) => g.verdict !== 'none')
  const flagged = shown.filter((g) => FLAGGED_VERDICTS.includes(g.verdict))
  const checked = report.graph.nodes.length
  const hasMap = Object.values(report.client_lists).some((rows) => rows.some((r) => r.lat != null))
  const clientGroup = selected && report.client_lists[selected] ? selected : flagged.find((g) => report.client_lists[g.group_id])?.group_id ?? null

  if (!shown.length || !report.graph.edges.length) {
    return (
      <section id="linked" className="chapter">
        <ChapterHead title="Reviewers opened" note={checked ? 'Select one to see their history' : undefined} />
        {checked ? (
          <>
            <p className="chapter-lede">
              ReviewRing opened the full public history of <strong className="num">{checked}</strong> reviewers. <strong>None of them share another place</strong>, so there is no linked group: a clean result, and evidence too.
            </p>
            <CheckedGrid report={report} namer={namer} />
            <StripKey />
          </>
        ) : (
          <div className="empty-line"><Network size={20} className="muted" /><span>No reviewer histories were checked.</span></div>
        )}
      </section>
    )
  }
  return (
    <section id="linked" className="chapter">
      <ChapterHead title="Linked reviewers" note="Select a group to highlight it in the graph, map, timeline and table." />
      
        <div className="row wrap" style={{ gap: 10, marginBottom: 16 }}>
          {shown.map((g) => {
            const kind = g.verdict === 'possible_ring_trip' ? 'possible_ring_trip' : FLAGGED_VERDICTS.includes(g.verdict) ? 'ring' : 'group_trip'
            return (
              <button key={g.group_id} className={`group-chip ${selected === g.group_id ? 'on' : ''}`} aria-pressed={selected === g.group_id}
                onClick={() => select(selected === g.group_id ? null : g.group_id)}>
                <i className={`swatch ${kind}`} />
                <span className="col">
                  <strong>{g.group_id}: {VERDICT_TEXT[g.verdict]}</strong>
                  <span className="muted small">{g.metrics.size} accounts, {g.metrics.core_places} shared places{g.confidence != null && <>, evidence strength <span className="num">{g.confidence.toFixed(2)}</span></>}</span>
                </span>
              </button>
            )
          })}
          {selected && <button className="btn ghost sm" onClick={() => select(null)}>Clear selection</button>}
        </div>
      
      
        <div className="linked-grid" style={hasMap ? undefined : { gridTemplateColumns: '1fr' }}>
          <div className="panel pad"><RingGraph report={report} namer={namer} selectedGroup={selected} onSelectGroup={select} /></div>
          {hasMap && <div className="panel pad"><MapView report={report} namer={namer} selectedGroup={selected} presentation={presentation} /></div>}
        </div>
      
      {clientGroup && (
        
          <div className="panel pad" style={{ marginTop: 18 }}>
            <div className="row" style={{ alignItems: 'baseline', marginBottom: 6 }}>
              <h3 style={{ fontSize: '1.1rem' }}>Other places this group reviewed</h3><span className="chip">{clientGroup}</span>
            </div>
            <p className="secondary small" style={{ marginBottom: 14 }}>From the reviewer histories already opened.</p>
            <ClientTable rows={report.client_lists[clientGroup] ?? []} namer={namer} />
          </div>
        
      )}
      <div style={{ marginTop: 40 }}>
        <div className="chapter-head" style={{ marginBottom: 14 }}><h3 style={{ fontSize: '1.35rem' }}>Every reviewer opened</h3><span className="muted">Select one to see their history</span></div>
        <CheckedGrid report={report} namer={namer} />
        <StripKey />
      </div>
    </section>
  )
}

function StripKey() {
  return (
    <div className="legend" style={{ marginTop: 12 }}>
      <span><span style={{ color: 'var(--gold)' }}>★</span> this business</span>
      <span><i className="swatch" style={{ background: 'var(--gold)' }} /> 5★ … <i className="swatch" style={{ background: 'var(--star-empty)' }} /> 1★</span>
      <span className="muted">Each line is one reviewer's history, oldest left; higher dots are farther from this business.</span>
    </div>
  )
}

/* ---------- 6. What was checked ---------- */

function Checked({ report, detail }: { report: Report; detail: AnalysisDetail }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const a = report.analysis
  const scored = report.groups.filter((g) => g.confidence != null)
  return (
    <section id="checked" className="chapter">
      <ChapterHead title="What was checked, and how" />
      
        <div className="panel pad" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 40 }}>
          <div className="col" style={{ gap: 22 }}>
            <dl className="kv">
              <dt>Reviews examined</dt><dd>The newest {report.sample.examined} ({day(report.sample.first)} to {day(report.sample.last)})</dd>
              <dt>Reviewer histories</dt><dd>{report.sample.expanded} opened ({report.sample.histories_ok} usable), incl. {report.sample.baseline.length} chosen at random as a baseline</dd>
              <dt>Not opened</dt><dd>{report.sample.not_checked_high_priority} other reviewers</dd>
              {a?.early_stop && <><dt>Stopped early</dt><dd>{a.early_stop.reason === 'no_overlap' ? 'The first reviewers opened shared no other places, so no more were opened' : 'Stopped after the first round on request'}</dd></>}
              {report.sieve && report.sieve.ai.judged > 0 && <><dt>AI-written check</dt><dd>{report.sieve.ai.judged} reviews read by {report.sieve.ai.model ?? 'an AI model'}</dd></>}
            </dl>
            <p className="small secondary">
              Labels, groups, levels and ratings come from fixed rules; no AI decides any of them. Two accounts are linked only when they
              reviewed at least two of the same unrelated places, weighted by distance from this business and by how unusual the place type is.
            </p>
            <details className="dev-details small">
              <summary className="secondary">For developers</summary>
              <dl className="kv" style={{ marginTop: 12 }}>
                <dt>Searches used</dt><dd className="num">{a?.mode === 'demo' ? '0 (demo)' : a?.searches_used ?? detail.searches_used}</dd>
                {a?.early_stop && <><dt>Saved by stopping early</dt><dd className="num">{a.early_stop.searches_saved}</dd></>}
                {Object.keys(a?.missing ?? {}).length > 0 && <><dt>Not in the cache</dt><dd>{Object.entries(a!.missing).map(([k, v]) => `${k} (${v})`).join(', ')}</dd></>}
                <dt>Algorithm</dt><dd>version {report.algorithm_version}</dd>
              </dl>
            </details>
            {a?.mode !== 'demo' && (
              <div className="row">
                <button className="btn sm" disabled={busy} onClick={async () => {
                  setBusy(true)
                  try { setMsg(`Wrote fixtures/${(await api.exportFixture(detail.id)).fixture} (pseudonymized, leak-checked).`) }
                  catch (e) { setMsg((e as Error).message) } finally { setBusy(false) }
                }}>Export pseudonymized fixture</button>
                {msg && <span className="small secondary">{msg}</span>}
              </div>
            )}
          </div>
          <div className="col" style={{ gap: 22 }}>
            <div>
              <h3 style={{ fontSize: '1.15rem', marginBottom: 10 }}>What this can't know</h3>
              <ul className="secondary small" style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6 }}>{report.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
            </div>
            {scored.map((g) => (
              <div key={g.group_id}>
                <h3 style={{ fontSize: '1.15rem', marginBottom: 12 }}>{g.group_id}: {VERDICT_TEXT[g.verdict]}</h3>
                <Strength g={g} />
              </div>
            ))}
          </div>
        </div>
      
    </section>
  )
}
