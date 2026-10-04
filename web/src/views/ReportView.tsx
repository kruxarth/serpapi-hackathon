import { useCallback, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { LevelBadge } from '../components/LevelBadge'
import { MapView } from '../components/MapView'
import { RingGraph } from '../components/RingGraph'
import { ClientTable, ReviewsTable } from '../components/Tables'
import { Timeline } from '../components/Timeline'
import { ageText, fmt, VERDICT_TEXT } from '../labels'
import { makeNamer } from '../names'
import { usePresentation } from '../presentation'
import type { AnalysisDetail, Group, Report } from '../types'

export function ReportView({ detail }: { detail: AnalysisDetail }) {
  const report = detail.report as Report
  const pres = usePresentation()
  const namer = useMemo(() => makeNamer(report), [report])
  const flagged = report.groups.filter((g) => ['ring', 'possible_ring', 'possible_ring_trip'].includes(g.verdict))
  const ruledOut = report.groups.filter((g) => g.verdict === 'ruled_out_trip' || g.verdict === 'social_circle')
  const [selected, setSelected] = useState<string | null>(null)
  const select = useCallback((g: string | null) => setSelected(g), [])
  const refs = { graph: useRef<HTMLElement>(null), timeline: useRef<HTMLElement>(null), reviews: useRef<HTMLElement>(null),
    map: useRef<HTMLElement>(null), ruled_out: useRef<HTMLElement>(null) }
  const clientGroup = selected && report.client_lists[selected] ? selected : flagged[0]?.group_id ?? null
  const demo = report.analysis?.mode === 'demo'
  const r = report.ratings

  const jump = (visual: string, group?: string) => {
    if (group) setSelected(group)
    const target = refs[visual as keyof typeof refs] ?? refs.graph
    target.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="stack">
      <Link to="/">← Back</Link>

      {/* Header */}
      <section className="card">
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div style={{ flex: 1 }}>
            <div className="row">
              <h1 style={{ fontSize: '1.5rem' }}>{namer.place(report.place.place_key)}</h1>
              {detail.synthetic && <span className="pill">synthetic example</span>}
              {report.pseudonymized && !detail.synthetic && <span className="pill">pseudonymized</span>}
              {report.dates_shifted && <span className="pill" title="All dates moved by the same hidden offset; intervals are unchanged">dates shifted</span>}
            </div>
            <div className="secondary">
              {[report.place.type, report.place.area].filter(Boolean).join(' · ')}
              {report.place.rating != null && (
                <> · shows <strong>{report.place.rating}★</strong> from {report.place.total_reviews?.toLocaleString() ?? '?'} reviews (as displayed)</>
              )}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <LevelBadge level={report.level.level} />
            <div className="muted small" style={{ marginTop: 6 }}>
              {demo ? 'Demo · 0 searches' : `${report.analysis?.searches_used ?? detail.searches_used} searches · ${ageText(detail.finished_at ?? report.analysis?.finished_at)}`}
            </div>
          </div>
        </div>

        <div className="grid-2" style={{ marginTop: 16 }}>
          <div>
            <div className="muted small">Latest {r.examined} reviews</div>
            {r.ring_reviews > 0 ? (
              <div className="hero">
                <span className="big num">{fmt(r.sample_mean, 2)}★</span>
                <span className="arrow">→</span>
                <span className="big num">{fmt(r.without_ring, 2)}★</span>
                <span className="secondary">excluding linked reviewers</span>
              </div>
            ) : (
              <div className="hero">
                <span className="big num">{fmt(r.sample_mean, 2)}★</span>
                <span className="secondary">average of the latest {r.examined}{report.place.rating != null && <> (the listing shows {report.place.rating}★)</>}</span>
              </div>
            )}
            <div className="secondary small">
              {fmt(r.without_ring_and_suspicious, 2)}★ also excluding suspicious and possible-group reviews ·{' '}
              {r.ring_reviews} review{r.ring_reviews === 1 ? '' : 's'} from ring-like groups set aside
            </div>
            {r.overall && (
              <div className="small" style={{ marginTop: 6 }}>
                Overall ({r.overall.total_as_displayed.toLocaleString()} reviews, as displayed):{' '}
                {r.overall.no_visible_change
                  ? <>no visible change at the overall level; the effect is concentrated in recent reviews.</>
                  : <><strong className="num">{r.overall.low.toFixed(2)}–{r.overall.high.toFixed(2)}★</strong> instead of {r.overall.displayed}★.</>}
                <span className="muted"> Google's displayed rating may not be a simple average, and its count may include ratings without text.</span>
              </div>
            )}
          </div>
          <div>
            <h3>Why {report.level.level.toLowerCase()}</h3>
            <ul style={{ margin: '4px 0', paddingLeft: 18 }}>
              {report.level.reasons.map((x) => <li key={x}>{x}</li>)}
            </ul>
            {report.warnings.map((w) => <div key={w} className="notice warn small" style={{ marginTop: 6 }}>{w}</div>)}
            {detail.finished_at && Date.now() - Date.parse(detail.finished_at) > 7 * 86400000 && (
              <div className="notice small" style={{ marginTop: 6 }}>Analysed {ageText(detail.finished_at)}. Reviews may have changed since.</div>
            )}
          </div>
        </div>
      </section>

      {/* Evidence */}
      <section className="card">
        <h2>Evidence</h2>
        {report.evidence.length === 0 && <p className="muted">Nothing crossed a reporting threshold.</p>}
        <div className="evidence-list">
          {report.evidence.map((e) => (
            <button key={e.text} className="evidence" onClick={() => jump(e.visual, e.group)}>
              <span aria-hidden style={{ fontSize: '1.1rem' }}>{e.kind === 'ruled_out_trip' ? '○' : e.kind === 'baseline' ? '◇' : '●'}</span>
              <span>
                <div className="tag">{e.kind.replace(/_/g, ' ')}{e.group ? ` · ${e.group}` : ''} · see {e.visual.replace('_', ' ')}</div>
                {e.text}
              </span>
            </button>
          ))}
        </div>
        {report.ai_summary && (
          <details style={{ marginTop: 14 }}>
            <summary>Plain-language summary written by AI from the facts above</summary>
            <div className="secondary" style={{ marginTop: 8 }}>
              {report.ai_summary.paragraphs.map((p) => <p key={p}>{p}</p>)}
              <p className="muted small">
                {report.ai_summary.source === 'llm' ? `Written by ${report.ai_summary.model} (prompt ${report.ai_summary.prompt_version}) from numbered facts; every number, name and place was filled in by ReviewRing, not the AI.` : 'Written from fixed templates (no AI key set, or the AI draft failed validation).'}
              </p>
            </div>
          </details>
        )}
      </section>

      {/* Groups selector */}
      {flagged.length > 0 && (
        <section className="card">
          <div className="row">
            <h2 style={{ margin: 0 }}>Groups found</h2>
            <span className="muted small">Select one to highlight it everywhere.</span>
            <div className="spacer" />
            {selected && <button className="btn small" onClick={() => setSelected(null)}>Clear selection</button>}
          </div>
          <div className="grid-3" style={{ marginTop: 10 }}>
            {flagged.map((g) => <GroupCard key={g.group_id} g={g} active={selected === g.group_id} onClick={() => setSelected(selected === g.group_id ? null : g.group_id)} />)}
          </div>
        </section>
      )}

      <div className="grid-2">
        <section className="card" ref={refs.graph}>
          <h2>Linked reviewers</h2>
          <RingGraph report={report} namer={namer} selectedGroup={selected} onSelectGroup={select} />
        </section>
        <section className="card" ref={refs.map}>
          <h2>Where the group's other reviews are</h2>
          <MapView report={report} namer={namer} selectedGroup={selected} presentation={pres.on || !!report.pseudonymized} />
        </section>
      </div>

      <section className="card" ref={refs.timeline}>
        <h2>Timeline of the latest reviews</h2>
        <Timeline report={report} selectedGroup={selected} />
      </section>

      {clientGroup && (
        <section className="card">
          <h2>Other places this group reviewed <span className="muted small">({clientGroup})</span></h2>
          <p className="secondary small" style={{ marginTop: 0 }}>Other businesses the same accounts reviewed. Costs no extra searches: it comes from the histories already fetched.</p>
          <ClientTable rows={report.client_lists[clientGroup] ?? []} namer={namer} />
        </section>
      )}

      <section className="card" ref={refs.reviews}>
        <h2>Reviews examined</h2>
        <ReviewsTable report={report} namer={namer} selectedGroup={selected} />
      </section>

      <section className="card" ref={refs.ruled_out}>
        <h2>Groups that were ruled out</h2>
        {ruledOut.length === 0 && <p className="muted">None. ReviewRing sets aside groups that look like friends or family (most share a home area, near the places they share) and group trips with positive evidence (a shared home, or hotel reviews saying family or friends).</p>}
        {ruledOut.filter((g) => g.verdict === 'social_circle').map((g) => (
          <div key={g.group_id} className="notice" style={{ marginBottom: 8 }}>
            <strong>{g.group_id}: {VERDICT_TEXT[g.verdict]}</strong> — {Math.round(g.metrics.home_member_share * 100)}% of the{' '}
            {g.members.length} reviewers live in {g.metrics.home_area}, and {Math.round(g.metrics.core_near_home_share * 100)}% of the places
            they share are near there. Not counted.
          </div>
        ))}
        {ruledOut.filter((g) => g.verdict === 'ruled_out_trip').map((g) => (
          <div key={g.group_id} className="notice" style={{ marginBottom: 8 }}>
            <strong>{g.group_id}: {VERDICT_TEXT[g.verdict]}</strong> — {g.members.length} reviewers shared {g.metrics.core_places} travel businesses
            within {Math.round(g.metrics.span_km)} km ({g.metrics.far_areas.join(', ') || 'one region'}).
            <div className="small secondary">
              Trip indicators met: {g.trip.indicators_met} of 3 —{' '}
              {g.trip.indicators.one_episode ? 'one visit window ✓' : 'one visit window ✗'},{' '}
              {g.trip.indicators.low_concentration ? 'histories mostly personal places ✓' : 'histories mostly shared places ✗'},{' '}
              {g.trip.indicators.varied_ratings ? 'varied ratings ✓' : 'nearly all 5★ ✗'}. Positive evidence:{' '}
              {[g.trip.positive_evidence?.shared_home && `most live in ${g.metrics.home_area}`, g.trip.positive_evidence?.travel_party && 'hotel reviews say family or friends'].filter(Boolean).join('; ') || 'none'}. Not counted.
            </div>
          </div>
        ))}
      </section>

      <Methodology report={report} detail={detail} />
    </div>
  )
}

function GroupCard({ g, active, onClick }: { g: Group; active: boolean; onClick: () => void }) {
  const m = g.metrics
  return (
    <button className="evidence" onClick={onClick} style={active ? { borderColor: 'var(--accent)' } : undefined} aria-pressed={active}>
      <i className={`swatch ${g.verdict === 'possible_ring_trip' ? 'possible_ring_trip' : 'ring'}`} style={{ marginTop: 4 }} />
      <span>
        <div><strong>{g.group_id} · {VERDICT_TEXT[g.verdict]}</strong></div>
        <div className="small secondary">
          {m.size} accounts · {m.core_places} shared places · {m.far_area_count} distant cities
          {g.confidence != null && <> · evidence strength <strong className="num">{g.confidence.toFixed(2)}</strong></>}
        </div>
        <div className="small muted">{m.far_areas.join(', ')}</div>
      </span>
    </button>
  )
}

function Methodology({ report, detail }: { report: Report; detail: AnalysisDetail }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const a = report.analysis
  const rings = report.groups.filter((g) => g.confidence != null)
  return (
    <section className="card">
      <h2>What was checked, and how</h2>
      <div className="grid-2">
        <div>
          <dl className="kv small">
            <dt>Reviews examined</dt><dd>The newest {report.sample.examined} ({report.sample.first} to {report.sample.last})</dd>
            <dt>Reviewer histories</dt><dd>{report.sample.expanded} fetched ({report.sample.histories_ok} usable), incl. {report.sample.baseline.length} chosen at random as a baseline</dd>
            <dt>Not checked</dt><dd>{report.sample.not_checked_high_priority} reviewers weren't checked (budget)</dd>
            <dt>Searches used</dt><dd>{a?.mode === 'demo' ? '0 (demo)' : a?.searches_used}</dd>
            {a?.early_stop && <><dt>Early stop</dt><dd>{a.early_stop.reason === 'no_overlap' ? `Round-1 reviewers shared nothing, so round 2 was skipped (${a.early_stop.searches_saved} searches saved)` : 'Stopped after round 1 on request'}</dd></>}
            <dt>Algorithm</dt><dd>version {report.algorithm_version}</dd>
          </dl>
          <h3 style={{ marginTop: 14 }}>What this can't know</h3>
          <ul className="small secondary" style={{ paddingLeft: 18 }}>{report.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
          <p className="small secondary">
            Labels, groups, levels and ratings are computed by fixed rules; no AI decides any of them. Two accounts are linked only
            when they reviewed at least two of the same unrelated places, weighted by distance from this business and by how
            unusual the place type is.
          </p>
          {a?.mode !== 'demo' && (
            <div className="row">
              <button className="btn small" disabled={busy} onClick={async () => {
                setBusy(true)
                try { setMsg(`Wrote fixtures/${(await api.exportFixture(detail.id)).fixture} (pseudonymized, leak-checked).`) }
                catch (e) { setMsg((e as Error).message) } finally { setBusy(false) }
              }}>Export pseudonymized fixture</button>
              {msg && <span className="small secondary">{msg}</span>}
            </div>
          )}
        </div>
        <div>
          {rings.map((g) => (
            <div key={g.group_id} style={{ marginBottom: 12 }}>
              <h3>{g.group_id} evidence strength {g.confidence?.toFixed(2)} <span className="muted small">(not a probability)</span></h3>
              <table className="small">
                <thead><tr><th>Part</th><th>Value</th><th>Weight</th></tr></thead>
                <tbody>
                  {g.confidence_parts.map((p) => (
                    <tr key={p.part} className={p.used ? '' : 'muted'}>
                      <td>{p.part}</td><td className="num">{p.value == null ? 'unknown (left out)' : p.value.toFixed(2)}</td><td className="num">{p.weight.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
