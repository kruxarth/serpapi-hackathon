import { ArrowLeft, ChevronRight, Info, Network, ShieldAlert, Sparkles } from 'lucide-react'
import { motion } from 'motion/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Finding, pairEvidence, Strength } from '../components/Findings'
import { MapView } from '../components/MapView'
import { RingGraph } from '../components/RingGraph'
import { ClientTable, ReviewsTable } from '../components/Tables'
import { Timeline } from '../components/Timeline'
import { LevelBadge, StarBar } from '../components/ui'
import { ageText, day, FLAGGED_VERDICTS, fmt, levelClass, VERDICT_TEXT } from '../labels'
import { makeNamer } from '../names'
import { usePresentation } from '../presentation'
import type { AnalysisDetail, Report } from '../types'

const CHAPTERS = [
  ['verdict', 'Verdict'],
  ['findings', 'Findings'],
  ['timeline', 'Timeline'],
  ['linked', 'Linked reviewers'],
  ['reviews', 'Reviews'],
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

  return (
    <div className="report">
      <Rail />
      <div>
        <Verdict report={report} detail={detail} />

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

        <section id="reviews" className="chapter">
          <ChapterHead title="Reviews examined" />
          <div className="panel pad"><ReviewsTable report={report} namer={namer} selectedGroup={selected} /></div>
        </section>

        <Checked report={report} detail={detail} />
      </div>
    </div>
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

function Verdict({ report, detail }: { report: Report; detail: AnalysisDetail }) {
  const r = report.ratings
  const p = report.place
  const demo = report.analysis?.mode === 'demo'
  const stale = detail.finished_at && Date.now() - Date.parse(detail.finished_at) > 7 * 86_400_000
  const lv = report.level.level
  const ring = r.ring_reviews > 0
  // The key number, straight from the report: without linked reviewers, or the latest reviews' average.
  const value = (ring ? r.without_ring : r.sample_mean) ?? 0
  const from = ring ? r.sample_mean ?? undefined : p.rating ?? undefined
  const fig = useRef<HTMLSpanElement>(null)
  const follow = useCallback((v: number) => {
    if (fig.current) fig.current.textContent = v.toFixed(2)
  }, [])
  const where = [p.type, p.area].filter(Boolean)
  return (
    <section id="verdict" className={`chapter verdict ${levelClass(lv)}`}>
      <div className="verdict-top">
        <span>{where.length === 2 ? `${where[0]} in ${where[1]}` : where[0] ?? 'Place'}</span>
        {detail.synthetic && <span className="chip accent">Synthetic example</span>}
        {report.pseudonymized && !detail.synthetic && <span className="chip">Pseudonymized</span>}
        {report.dates_shifted && <span className="chip" title="All dates moved by the same hidden offset; intervals are unchanged">Dates shifted</span>}
        <span className="spacer" />
        <span className="muted small">{demo ? 'Demo, no searches used' : `${report.analysis?.searches_used ?? detail.searches_used} searches, analysed ${ageText(detail.finished_at ?? report.analysis?.finished_at)}`}</span>
      </div>
      <h1>{p.title ?? 'This business'}</h1>

      <div className="verdict-stage">
        <div className="panel meter">
          {p.rating != null && (
            <div className="secondary">Google shows <strong className="num" style={{ color: 'var(--ink)' }}>{p.rating}★</strong> from {p.total_reviews?.toLocaleString('en-IN') ?? '?'} reviews</div>
          )}
          <div style={{ marginTop: 14 }}>
            <StarBar className="meter-stars" value={value} from={from} delay={0.5} onValue={follow} />
          </div>
          <div className="meter-row">
            <span className="fig meter-fig"><span ref={fig}>{value.toFixed(2)}</span><span className="star">★</span></span>
            <span className="secondary" style={{ paddingBottom: 10, maxWidth: '24ch', lineHeight: 1.35 }}>
              {ring
                ? <>the latest {r.examined} reviews without linked reviewers, down from <strong className="num">{fmt(r.sample_mean, 2)}★</strong></>
                : <>is what the latest {r.examined} reviews average</>}
            </span>
          </div>
          {ring && (
            <p className="secondary small" style={{ marginTop: 16 }}>
              {r.ring_reviews} review{r.ring_reviews === 1 ? '' : 's'} from ring-like groups set aside. {fmt(r.without_ring_and_suspicious, 2)}★ also excluding suspicious and possible-group reviews.
            </p>
          )}
          {!ring && r.without_ring_and_suspicious != null && r.without_ring_and_suspicious !== r.sample_mean && (
            <p className="secondary small" style={{ marginTop: 16 }}>{fmt(r.without_ring_and_suspicious, 2)}★ excluding suspicious reviews.</p>
          )}
          {r.overall && (
            <p className="small muted" style={{ marginTop: 8 }}>
              Across all {r.overall.total_as_displayed.toLocaleString('en-IN')} reviews as displayed:{' '}
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
          <div className="caveat-strip">
            <Info size={16} className="muted" />
            A pattern, not proof. A business can be targeted without its knowledge.
          </div>
        </div>
      </div>
    </section>
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
        <ChapterHead title="Linked reviewers" />
        
          <div className="empty-line">
            <Network size={20} className="muted" />
            {checked
              ? <span>None of the <strong className="num">{checked}</strong> reviewers checked share any other places, so there is no linked group to show.</span>
              : <span>No reviewer histories were checked.</span>}
          </div>
        
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
            <p className="secondary small" style={{ marginBottom: 14 }}>From the reviewer histories already fetched; no extra searches.</p>
            <ClientTable rows={report.client_lists[clientGroup] ?? []} namer={namer} />
          </div>
        
      )}
    </section>
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
              <dt>Reviewer histories</dt><dd>{report.sample.expanded} fetched ({report.sample.histories_ok} usable), incl. {report.sample.baseline.length} chosen at random as a baseline</dd>
              <dt>Not checked</dt><dd>{report.sample.not_checked_high_priority} high-priority reviewers (budget)</dd>
              <dt>Searches used</dt><dd className="num">{a?.mode === 'demo' ? '0 (demo)' : a?.searches_used ?? detail.searches_used}</dd>
              {a?.early_stop && <><dt>Early stop</dt><dd>{a.early_stop.reason === 'no_overlap' ? `Round-1 reviewers shared nothing, so round 2 was skipped (${a.early_stop.searches_saved} searches saved)` : 'Stopped after round 1 on request'}</dd></>}
              <dt>Algorithm</dt><dd>version {report.algorithm_version}</dd>
            </dl>
            <p className="small secondary">
              Labels, groups, levels and ratings come from fixed rules; no AI decides any of them. Two accounts are linked only when they
              reviewed at least two of the same unrelated places, weighted by distance from this business and by how unusual the place type is.
            </p>
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
