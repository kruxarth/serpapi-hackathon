// One visual per evidence kind. Every number shown here is read from the report; nothing is re-scored.

import { ArrowRight, Check, CircleSlash, Copy, Dices, Minus, Network, Quote } from 'lucide-react'
import { motion, useInView } from 'motion/react'
import { useRef, type ReactNode } from 'react'
import { day, dayCount, fmt, pct, VERDICT_TEXT } from '../labels'
import { CountUp, EASE, Reveal } from '../motion'
import type { Namer } from '../names'
import type { Burst, Evidence, Group, Report, SingleUseBurst } from '../types'
import { Timeline } from './Timeline'
import { Stars } from './ui'

const KIND: Record<string, { text: string; tone: string }> = {
  rating_gap: { text: 'Rating carried by older reviews', tone: 'var(--status-serious)' },
  top_rated: { text: 'Highest-rated reviews cluster in time', tone: 'var(--label-suspicious)' },
  generated_text: { text: 'Chatbot or template text', tone: 'var(--label-suspicious)' },
  single_use_burst: { text: 'Burst of single-use accounts', tone: 'var(--label-suspicious)' },
  burst: { text: 'Review burst', tone: 'var(--ink-2)' },
  ring: { text: 'Ring-like group of linked reviewers', tone: 'var(--label-ring)' },
  possible_ring: { text: 'Possible ring-like group', tone: 'var(--label-ring)' },
  possible_ring_trip: { text: 'Possible ring-like group, trip-like', tone: 'var(--label-ring)' },
  ruled_out_trip: { text: 'Set aside: consistent with a group trip', tone: 'var(--label-trip)' },
  social_circle: { text: 'Set aside: consistent with friends or family', tone: 'var(--label-trip)' },
  duplicates: { text: 'Near-identical texts', tone: 'var(--ink-2)' },
  baseline: { text: 'Random baseline', tone: 'var(--ink-2)' },
}
const QUIET = new Set(['duplicates', 'baseline'])

interface Ctx {
  report: Report
  namer: Namer
  onShowGroup: (g: string) => void
}

/** Pair each burst-type evidence item with its signal, in the order the backend lists them. */
export function pairEvidence(report: Report) {
  const bursts = [...report.signals.T1.bursts]
  const single = (report.signals.T6?.single_use_bursts ?? []).filter((b) => b.flagged)
  let si = 0
  return report.evidence.map((e) => {
    if (e.kind === 'burst') {
      const lead = Number(e.text.match(/^(\d+) of/)?.[1])
      const i = bursts.findIndex((b) => b.count === lead)
      return { e, burst: bursts.splice(i >= 0 ? i : 0, 1)[0] }
    }
    if (e.kind === 'single_use_burst') return { e, single: single[si++] }
    return { e }
  })
}

export function Finding({ index, e, burst, single, ctx }: { index: number; e: Evidence; burst?: Burst; single?: SingleUseBurst; ctx: Ctx }) {
  const k = KIND[e.kind] ?? { text: e.kind.replace(/_/g, ' '), tone: 'var(--ink-2)' }
  const group = e.group ? ctx.report.groups.find((g) => g.group_id === e.group) : undefined
  const quiet = QUIET.has(e.kind)
  const setAside = e.kind === 'ruled_out_trip' || e.kind === 'social_circle'
  return (
    <Reveal>
      <article className={`panel finding ${quiet ? 'quiet' : ''} ${setAside ? 'setaside' : ''}`} style={{ ['--tone' as string]: k.tone }}>
        <div className="finding-index">{String(index + 1).padStart(2, '0')}</div>
        <div>
          <div className="finding-kind">
            {quiet ? (e.kind === 'duplicates' ? <Copy size={14} /> : <Dices size={14} />) : setAside ? <CircleSlash size={14} /> : <span className="swatch" style={{ background: k.tone }} />}
            {k.text}{e.group ? ` · ${e.group}` : ''}
          </div>
          <h3>{e.text}</h3>
        </div>
        {!quiet && (
          <div className="visual">
            {e.kind === 'rating_gap' && <RatingGapVisual report={ctx.report} />}
            {e.kind === 'top_rated' && <TopRatedVisual report={ctx.report} />}
            {e.kind === 'generated_text' && <GeneratedVisual report={ctx.report} text={e.text} />}
            {e.kind === 'single_use_burst' && single && <SingleUseVisual report={ctx.report} b={single} />}
            {e.kind === 'burst' && burst && <BurstVisual report={ctx.report} b={burst} />}
            {group && ['ring', 'possible_ring', 'possible_ring_trip'].includes(e.kind) && <GroupVisual g={group} onShow={() => ctx.onShowGroup(group.group_id)} />}
            {group && setAside && <SetAsideVisual g={group} />}
          </div>
        )}
      </article>
    </Reveal>
  )
}

/* ---------- rating_gap: displayed vs latest vs implied older ---------- */

function RatingGapVisual({ report }: { report: Report }) {
  const t = report.signals.T7
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -60px 0px' })
  if (!t?.available) return null
  // Bars run on the 1–5 star scale, with the axis labelled.
  const w = (v: number) => `${((v - 1) / 4) * 100}%`
  const rows = [
    { label: 'Listing shows', sub: `${(report.pseudonymized ? report.place.total_reviews ?? t.total : t.total).toLocaleString('en-IN')} reviews, as displayed`, v: t.displayed, fill: 'var(--ink-2)', digits: 1 },
    { label: `Latest ${t.recent_count} average`, sub: 'what recent customers say', v: t.recent_mean, fill: 'var(--status-serious)', digits: 2 },
    { label: 'Older reviews must average', sub: report.pseudonymized ? 'all the others, implied' : `${t.older_count.toLocaleString('en-IN')} reviews, implied`, v: t.older_implied_mean, fill: 'repeating-linear-gradient(45deg, var(--ink-2) 0 4px, color-mix(in srgb, var(--ink-2) 40%, transparent) 4px 8px)', digits: 2 },
  ]
  return (
    <div ref={ref}>
      <div className="gap-rows">
        {rows.map((r, i) => (
          <div key={r.label} className="gap-row">
            <div className="lab"><strong>{r.label}</strong><span className="muted">{r.sub}</span></div>
            <div className="gap-track">
              <motion.div className="gap-bar" style={{ background: r.fill }} initial={{ width: 0 }} animate={inView ? { width: w(r.v) } : {}}
                transition={{ duration: 1.1, ease: EASE, delay: 0.15 + i * 0.35 }} />
            </div>
            <div className="gap-val num"><CountUp value={r.v} from={1} digits={r.digits} delay={0.15 + i * 0.35} duration={1.1} />★</div>
          </div>
        ))}
        <div className="gap-axis"><div /><div><span>1★</span><span>2★</span><span>3★</span><span>4★</span><span>5★</span></div><div /></div>
      </div>
      <motion.div className="row" style={{ marginTop: 18, gap: 10 }} initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : {}} transition={{ delay: 1.5 }}>
        <span className="chip" style={{ color: 'var(--status-serious)' }}>Gap of {fmt(t.gap, 2)}★ between the listing and its latest reviews</span>
      </motion.div>
    </div>
  )
}

/* ---------- top_rated: how many of the sampled top-rated reviews fall in one window ---------- */

function TopRatedVisual({ report }: { report: Report }) {
  const t = report.signals.T8
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -60px 0px' })
  if (!t?.available) return null
  return (
    <div ref={ref} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 40, alignItems: 'start' }}>
      <div>
        <div className="dotgrid" role="img" aria-label={`${t.window_count} of ${t.count} in the window`}>
          {Array.from({ length: t.count }, (_, i) => (
            <motion.i key={i} className={i < t.window_count ? 'on' : ''} initial={{ scale: 0, opacity: 0 }} animate={inView ? { scale: 1, opacity: 1 } : {}}
              transition={{ type: 'spring', stiffness: 300, damping: 20, delay: i * 0.025 }} />
          ))}
        </div>
        <div className="legend" style={{ marginTop: 14 }}>
          <span><i className="swatch suspicious" style={{ borderRadius: 3 }} /> posted {day(t.window_start)} → {day(t.window_end)}</span>
          <span><i className="swatch" style={{ background: 'var(--surface-3)', borderRadius: 3 }} /> posted at other times</span>
        </div>
      </div>
      <div className="col" style={{ gap: 16 }}>
        <div className="row" style={{ alignItems: 'baseline', gap: 10 }}>
          <span className="big-num num"><CountUp value={t.window_count} /></span>
          <span className="secondary">of {t.count} highest-rated reviews sampled fall in one {t.window_months}-month window</span>
        </div>
        <Meter label="From accounts with at most one review" share={t.single_use_share} inView={inView} delay={0.6} hatch />
        <Meter label="Without photos" share={t.no_photo_share} inView={inView} delay={0.8} />
      </div>
    </div>
  )
}

function Meter({ label, share, inView, delay, hatch }: { label: string; share: number; inView: boolean; delay: number; hatch?: boolean }) {
  return (
    <div className="meter-row">
      <span className="secondary">{label}</span>
      <div className="bar-track" style={{ height: 10 }}>
        <motion.div className={`bar-fill ${hatch ? 'seg-hatch' : ''}`} style={{ background: hatch ? undefined : 'var(--label-none)' }}
          initial={{ width: 0 }} animate={inView ? { width: pct(share) } : {}} transition={{ duration: 1, ease: EASE, delay }} />
      </div>
      <strong className="num" style={{ textAlign: 'right' }}>{pct(share)}</strong>
    </div>
  )
}

/* ---------- generated_text: the marker phrase as a pull quote ---------- */

function GeneratedVisual({ report, text }: { report: Report; text: string }) {
  const hits = report.signals.T8?.available ? report.signals.T8.generated : []
  const fromRows = report.reviews.filter((r) => r.generated_marker).map((r) => ({
    review_id: r.review_id, rating: r.rating, day: r.day, marker: r.generated_marker as string, reviewer_reviews: r.reviewer_reviews,
  }))
  const all = [...hits, ...fromRows.filter((r) => !hits.some((h) => h.review_id === r.review_id))]
  const quoted = text.match(/"([^"]+)"/)?.[1]
  if (!all.length && quoted) all.push({ review_id: 'q', rating: null, day: null, marker: quoted, reviewer_reviews: null })
  return (
    <div className="col" style={{ gap: 14 }}>
      {all.map((h) => {
        const full = report.reviews.find((r) => r.review_id === h.review_id)?.text
        return <PullQuote key={h.review_id} marker={h.marker} full={full ?? null} rating={h.rating} date={h.day} reviews={h.reviewer_reviews} />
      })}
    </div>
  )
}

function PullQuote({ marker, full, rating, date, reviews }: { marker: string; full: string | null; rating: number | null; date: string | null; reviews: number | null }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -60px 0px' })
  const at = full ? full.toLowerCase().indexOf(marker.toLowerCase()) : -1
  const hl = (
    <motion.span className="mark-hl" initial={{ backgroundSize: '0% 100%' }} animate={inView ? { backgroundSize: '100% 100%' } : {}} transition={{ duration: 0.9, ease: EASE, delay: 0.4 }}>
      {at >= 0 && full ? full.slice(at, at + marker.length) : marker}
    </motion.span>
  )
  return (
    <div ref={ref} className="quote">
      <Quote className="qmark" size={34} />
      <blockquote>
        {at >= 0 && full ? <>{full.slice(0, at)}{hl}{full.slice(at + marker.length)}</> : <>…{hl}…</>}
      </blockquote>
      <div className="row small" style={{ marginTop: 16, gap: 14 }}>
        <Stars rating={rating} />
        {date && <span className="secondary">{day(date)}</span>}
        {reviews != null && <span className="muted">from an account with {reviews} review{reviews === 1 ? '' : 's'}</span>}
        {!full && <span className="muted">· full text not included</span>}
      </div>
    </div>
  )
}

/* ---------- bursts ---------- */

function SingleUseVisual({ report, b }: { report: Report; b: SingleUseBurst }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -60px 0px' })
  return (
    <div ref={ref} className="col" style={{ gap: 22 }}>
      <div>
        <div className="row" style={{ alignItems: 'baseline', gap: 10, marginBottom: 12 }}>
          <span className="big-num num"><CountUp value={b.single_use} /></span>
          <span className="secondary">of <strong className="num">{b.count}</strong> reviews in {dayCount(b.start, b.end)} days came from single-use accounts</span>
        </div>
        <div className="propbar" role="img" aria-label={`${b.single_use} of ${b.count}`}>
          <motion.div className="seg-hatch" initial={{ width: 0 }} animate={inView ? { width: `${(b.single_use / b.count) * 100}%` } : {}} transition={{ duration: 1.2, ease: EASE, delay: 0.2 }} />
        </div>
        <div className="legend" style={{ marginTop: 10 }}>
          <span><i className="swatch single_use_burst" /> accounts that have reviewed nothing else</span>
          <span><i className="swatch" style={{ background: 'var(--surface-3)' }} /> other accounts</span>
        </div>
      </div>
      <Timeline report={report} height={170} legend={false}
        highlights={[{ start: b.start, end: b.end, text: `${b.count} in ${dayCount(b.start, b.end)} days`, tone: 'suspicious' }]} />
    </div>
  )
}

function BurstVisual({ report, b }: { report: Report; b: Burst }) {
  return (
    <Timeline report={report} height={170} legend={false} zoom
      highlights={[{ start: b.start, end: b.end, text: `${b.count} in ${dayCount(b.start, b.end)} days`, tone: 'neutral' }]} />
  )
}

/* ---------- groups ---------- */

function GroupVisual({ g, onShow }: { g: Group; onShow: () => void }) {
  const m = g.metrics
  const stats: [number, string][] = [
    [m.size, 'linked accounts'],
    [m.core_places, 'other places in common'],
    [m.far_area_count, 'distant cities'],
    [Math.round(m.span_km), 'km apart at most'],
  ]
  return (
    <div className="col" style={{ gap: 20 }}>
      <div className="stat-strip">
        {stats.map(([v, l], i) => (
          <div key={l}><div className="v num"><CountUp value={v} delay={i * 0.1} /></div><div className="muted small">{l}</div></div>
        ))}
      </div>
      {m.far_areas.length > 0 && (
        <div className="row wrap" style={{ gap: 6 }}>
          <span className="muted small">Cities:</span>
          {m.far_areas.map((a) => <span key={a} className="chip">{a}</span>)}
        </div>
      )}
      {g.confidence != null && <Strength g={g} />}
      <div>
        <button className="btn" onClick={onShow}><Network size={15} /> Show this group on the graph and map <ArrowRight size={15} /></button>
      </div>
    </div>
  )
}

export function Strength({ g }: { g: Group }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -40px 0px' })
  return (
    <div ref={ref}>
      <div className="row" style={{ alignItems: 'baseline', gap: 10 }}>
        <strong>Evidence strength <span className="num">{g.confidence?.toFixed(2)}</span></strong>
        <span className="muted small">a weighted sum of the parts below, from 0 to 1; not a probability</span>
      </div>
      <div className="col" style={{ gap: 8, marginTop: 12 }}>
        {g.confidence_parts.map((p, i) => (
          <div key={p.part} className="meter-row" style={{ gridTemplateColumns: '150px 1fr 120px', opacity: p.used ? 1 : 0.5 }}>
            <span className="secondary">{p.part}</span>
            <div className="bar-track" style={{ height: 8 }}>
              <motion.div className="bar-fill" style={{ background: 'var(--label-ring)' }} initial={{ width: 0 }}
                animate={inView ? { width: `${(p.value ?? 0) * 100}%` } : {}} transition={{ duration: 0.9, ease: EASE, delay: i * 0.08 }} />
            </div>
            <span className="num small secondary" style={{ textAlign: 'right' }}>
              {p.value == null ? 'unknown, left out' : `${p.value.toFixed(2)} × ${p.weight.toFixed(2)}`}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SetAsideVisual({ g }: { g: Group }) {
  const m = g.metrics
  const items: [boolean, ReactNode][] = g.verdict === 'social_circle'
    ? [
        [true, <>{pct(m.home_member_share)} of the {g.members.length} reviewers live in {m.home_area ?? 'one area'}</>],
        [true, <>{pct(m.core_near_home_share)} of the places they share are near there</>],
      ]
    : [
        [g.trip.indicators.one_episode, 'One visit window'],
        [g.trip.indicators.low_concentration, 'Histories are mostly personal places'],
        [g.trip.indicators.varied_ratings, 'Ratings are varied, not all 5★'],
        [!!g.trip.positive_evidence?.shared_home, <>Most live in one home area{m.home_area ? ` (${m.home_area})` : ''}</>],
        [!!g.trip.positive_evidence?.travel_party, 'Hotel reviews mention family or friends'],
      ]
  return (
    <div className="col" style={{ gap: 12 }}>
      <div className="eyebrow">{VERDICT_TEXT[g.verdict]} · {g.members.length} reviewers · {m.core_places} shared places within {Math.round(m.span_km)} km</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 28px' }}>
        {items.map(([ok, text], i) => (
          <motion.div key={i} className="indicator" initial={{ opacity: 0, x: -8 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.08 }}
            style={{ color: ok ? 'var(--ink)' : 'var(--muted)' }}>
            {ok ? <Check size={16} style={{ color: 'var(--label-trip)' }} /> : <Minus size={16} />}{text}
          </motion.div>
        ))}
      </div>
      <p className="small secondary">Not counted towards the level or the adjusted rating.</p>
    </div>
  )
}
