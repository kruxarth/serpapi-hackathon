// One visual per evidence kind. Every number shown here is read from the report; nothing is re-scored.

import { Bot, Check, CircleSlash, Copy, Dices, Minus, Network, RotateCcw, User } from 'lucide-react'
import { motion, useInView, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { day, dayCount, fmt, pct } from '../labels'
import { CountUp, EASE } from '../motion'
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

export function Finding({ e, burst, single, ctx }: { e: Evidence; burst?: Burst; single?: SingleUseBurst; ctx: Ctx }) {
  const k = KIND[e.kind] ?? { text: e.kind.replace(/_/g, ' '), tone: 'var(--ink-2)' }
  const group = e.group ? ctx.report.groups.find((g) => g.group_id === e.group) : undefined
  const quiet = QUIET.has(e.kind)
  const setAside = e.kind === 'ruled_out_trip' || e.kind === 'social_circle'
  return (
    <article className={`finding ${quiet ? 'quiet' : ''} ${setAside ? 'setaside' : ''}`} style={{ ['--tone' as string]: k.tone }}>
      <div>
        <div className="finding-kind">
          {quiet ? (e.kind === 'duplicates' ? <Copy size={15} /> : <Dices size={15} />) : setAside ? <CircleSlash size={15} /> : <span className="swatch" style={{ background: k.tone }} />}
          {k.text}{e.group ? `, group ${e.group}` : ''}
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
    { label: 'Listing shows', sub: `${(report.pseudonymized ? report.place.total_reviews ?? t.total : t.total).toLocaleString('en-IN')} reviews, as displayed`, v: t.displayed, fill: 'var(--gold)', digits: 1 },
    { label: `Latest ${t.recent_count} average`, sub: 'what recent customers say', v: t.recent_mean, fill: 'var(--ink)', digits: 2 },
    { label: 'Older reviews must average', sub: report.pseudonymized ? 'all the others, implied' : `${t.older_count.toLocaleString('en-IN')} reviews, implied`, v: t.older_implied_mean, fill: 'repeating-linear-gradient(45deg, var(--gold) 0 4px, color-mix(in srgb, var(--gold) 35%, transparent) 4px 8px)', digits: 2 },
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
    <div ref={ref} className="col" style={{ gap: 24 }}>
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
          <span className="secondary">of the {t.count} highest-rated reviews sampled fall in one {t.window_months}-month window</span>
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

/* ---------- generated_text: the review itself, typed out, with the giveaway highlighted ---------- */

function GeneratedVisual({ report, text }: { report: Report; text: string }) {
  const hits = report.signals.T8?.available ? report.signals.T8.generated : []
  const fromRows = report.reviews.filter((r) => r.generated_marker).map((r) => ({
    review_id: r.review_id, rating: r.rating, day: r.day, marker: r.generated_marker as string, reviewer_reviews: r.reviewer_reviews,
    excerpt: r.excerpt ?? r.text,
  }))
  const all = [...hits, ...fromRows.filter((r) => !hits.some((h) => h.review_id === r.review_id))]
  const quoted = text.match(/"([^"]+)"/)?.[1]
  if (!all.length && quoted) all.push({ review_id: 'q', rating: null, day: null, marker: quoted, reviewer_reviews: null, excerpt: null })
  return (
    <div className="col" style={{ gap: 14 }}>
      {all.map((h) => <ReviewCard key={h.review_id} marker={h.marker} text={h.excerpt ?? null} rating={h.rating} date={h.day} reviews={h.reviewer_reviews} />)}
    </div>
  )
}

function ReviewCard({ marker, text, rating, date, reviews }: { marker: string; text: string | null; rating: number | null; date: string | null; reviews: number | null }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -80px 0px' })
  const reduce = useReducedMotion()
  const body = text ?? `…${marker}…`
  const [n, setN] = useState(0)
  const [run, setRun] = useState(0)
  useEffect(() => {
    if (!inView) return
    if (reduce) {
      setN(body.length)
      return
    }
    setN(0)
    let raf = 0
    const dur = Math.min(3600, Math.max(900, body.length * 30))
    const t0 = performance.now() + 450
    const tick = () => {
      const k = Math.max(0, Math.min(body.length, Math.round(((performance.now() - t0) / dur) * body.length)))
      setN(k)
      if (k < body.length) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [inView, body, reduce, run])
  const at = Math.max(0, body.toLowerCase().indexOf(marker.toLowerCase()))
  const end = at + marker.length
  const typing = n < body.length
  return (
    <div ref={ref} className="review-card">
      <div className="row" style={{ gap: 12 }}>
        <span className="avatar" aria-hidden><User size={18} /></span>
        <div className="col">
          <strong style={{ fontSize: '0.95rem' }}>A reviewer</strong>
          <span className="muted tiny">{reviews != null ? `${reviews} review${reviews === 1 ? '' : 's'} on the profile` : 'profile not checked'}</span>
        </div>
      </div>
      <div className="row small" style={{ gap: 10, margin: '14px 0 10px' }}>
        <Stars rating={rating} />{date && <span className="muted">{day(date)}</span>}
      </div>
      <blockquote aria-label={body}>
        <span aria-hidden>
          {body.slice(0, Math.min(n, at))}
          {n > at && (
            <motion.span className="mark-hl" initial={{ backgroundSize: '0% 100%' }} animate={n >= end ? { backgroundSize: '100% 100%' } : {}} transition={{ duration: 0.6, ease: EASE }}>
              {body.slice(at, Math.min(n, end))}
            </motion.span>
          )}
          {n > end && body.slice(end, n)}
          {typing && <span className="caret" />}
        </span>
      </blockquote>
      <motion.div className="row wrap small" style={{ marginTop: 16, gap: '6px 14px', justifyContent: 'space-between' }} initial={{ opacity: 0 }} animate={!typing && inView ? { opacity: 1 } : {}}>
        <span className="giveaway"><Bot size={15} /> "{marker}" is what a chatbot replies, not what a customer writes</span>
        <button className="btn ghost sm" onClick={() => setRun((x) => x + 1)}><RotateCcw size={13} /> Again</button>
      </motion.div>
      {!text && <div className="muted tiny" style={{ marginTop: 8 }}>Only the giveaway phrase is kept for this review.</div>}
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
          <span className="muted small">Distant cities</span>
          {m.far_areas.map((a) => <span key={a} className="chip">{a}</span>)}
        </div>
      )}
      {g.confidence != null && <Strength g={g} />}
      <div>
        <button className="btn" onClick={onShow}><Network size={15} /> Show this group on the graph and map</button>
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
        <span className="muted small">a weighted sum from 0 to 1, not a probability</span>
      </div>
      <div className="col" style={{ gap: 8, marginTop: 12 }}>
        {g.confidence_parts.map((p, i) => (
          <div key={p.part} className="meter-row" style={{ gridTemplateColumns: '130px 1fr 112px', opacity: p.used ? 1 : 0.5 }}>
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
      <strong>{g.members.length} reviewers, {m.core_places} shared places within {Math.round(m.span_km)} km</strong>
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
