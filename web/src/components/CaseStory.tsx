// The story of one check, told from its own report: the place you asked about, its newest reviews, each thing worth
// flagging with its evidence, and what is left once those are set aside. Built in the browser from the report, so
// every check gets its own, instantly and at no cost. The newest reviews stay on screen as a strip of dots that
// light up for each finding and fall away when set aside. Same words as everywhere: reviews are "set aside" or
// "kept", opinions and context are labelled as such, and nothing is called fake.

import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw, X } from 'lucide-react'
import { AnimatePresence, animate, motion, useMotionValue, useTransform, type MotionValue } from 'motion/react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { burstWhen, day, FLAGGED_VERDICTS, fmt, paceText, spanText } from '../labels'
import { EASE, useWidth } from '../motion'
import type { Namer } from '../names'
import type { Level, Report, ReviewRow, SignKey } from '../types'
import { phraseSpan } from '../text'
import { BurstZoom } from './BurstZoom'
import { Marked, Shared } from './ReviewList'
import { HistoryStrip, newestDay, starFill, stripPoints } from './Reviewer'
import { LevelBadge, StarBar } from './ui'

/* ---------------------------------------------------------------- scenes from a report */

interface Scene {
  key: string
  ms: number
  eyebrow: string
  title: string
  sub?: ReactNode
  visual?: ReactNode
  /** The dot strip: hidden on the title card, then highlighting `hot` in `tone`, with `gone` set aside. */
  dots: boolean
  hot?: Set<string>
  gone?: Set<string>
  tone?: string
}

const TONE = { strong: 'var(--label-suspicious)', ring: 'var(--label-ring)', opinion: 'var(--label-suspicious)', context: 'var(--ink-2)' }
const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString('en-IN')} ${n === 1 ? one : many}`
const VERDICT_LINE: Record<Level, string> = {
  High: 'Strong signs of coordinated reviews.',
  Elevated: 'Some of these reviews deserve a second look.',
  Low: 'The newest reviews hold up.',
  'Not enough history': 'Too little history to judge.',
}

const ids = (rows: ReviewRow[]) => new Set(rows.map((r) => r.review_id))
const withSign = (report: Report, k: SignKey) => report.reviews.filter((r) => r.signs?.includes(k))
/** Readable examples first: texts long enough to say something, short enough to read in a few seconds. */
const examples = (rows: ReviewRow[], n: number) =>
  [...rows].filter((r) => r.text).sort((a, b) => Math.abs((a.text!.length) - 150) - Math.abs((b.text!.length) - 150)).slice(0, n)

/** Up to `width` characters of the text around a phrase, with ellipses where it was cut. */
function around(text: string, at: [number, number] | null, width = 170): string {
  if (text.length <= width || !at) return text.length <= width ? text : `${text.slice(0, width).trimEnd()}…`
  const pad = Math.max(0, Math.floor((width - (at[1] - at[0])) / 2))
  const s = Math.max(0, at[0] - pad)
  const e = Math.min(text.length, s + width)
  return `${s > 0 ? '…' : ''}${text.slice(s, e).trim()}${e < text.length ? '…' : ''}`
}

function Quote({ r, namer, children }: { r: ReviewRow; namer: Namer; children: ReactNode }) {
  return (
    <figure className="sp-quote">
      <blockquote>{children}</blockquote>
      <figcaption className="tiny muted">
        <span style={{ color: 'var(--gold)' }}>{'★'.repeat(r.rating ?? 0)}</span> {namer.reviewer(r.contributor_id)}
        {r.reviewer_reviews != null && <> · {r.reviewer_reviews <= 1 ? 'no other reviews' : plural(r.reviewer_reviews, 'review')}</>} · {day(r.day)}
      </figcaption>
    </figure>
  )
}

function Hidden() {
  return <p className="secondary small">Review texts are hidden in presentation mode.</p>
}

function buildScenes(report: Report, namer: Namer): Scene[] {
  const sieve = report.sieve!
  const p = report.place
  const n = report.reviews.length
  const out: Scene[] = []
  const where = [p.type, p.area].filter(Boolean).join(' in ')

  out.push({
    key: 'intro', ms: 5200, dots: false, eyebrow: 'You asked about', title: p.title ?? 'This business',
    sub: where || undefined,
    visual: p.rating != null && (
      <div className="sp-big-rating">
        <span className="sp-fig">{fmt(p.rating, 1)}<span style={{ color: 'var(--gold)' }}>★</span></span>
        <StarBar value={p.rating} duration={1.4} className="sp-starbar" />
        <span className="secondary">on Google{p.total_reviews ? `, from ${plural(p.total_reviews, 'review')}` : ''}</span>
      </div>
    ),
  })

  const firstTime = report.reviews.filter((r) => r.reviewer_reviews != null && r.reviewer_reviews <= 1).length
  out.push({
    key: 'sample', ms: 7200, dots: true, eyebrow: 'What we read', title: `We read its newest ${n} reviews.`,
    sub: <>From {day(report.sample.first)} to {day(report.sample.last)}. Below, each dot is one review in date order, coloured by its stars. Hollow dots come from accounts with no other reviews: {firstTime} here, and many real customers are like that.</>,
    visual: (
      <div className="sp-tiles">
        <div><span className="sp-fig">{n}</span><span className="muted small">newest reviews</span></div>
        <div><span className="sp-fig">{fmt(sieve.all.mean, 2)}<span style={{ color: 'var(--gold)' }}>★</span></span><span className="muted small">their average</span></div>
        <div><span className="sp-fig">{firstTime}</span><span className="muted small">from first-time accounts</span></div>
      </div>
    ),
  })

  const gap = report.signals.T7
  if (gap?.available && gap.flagged) {
    out.push({
      key: 'gap', ms: 8200, dots: true, eyebrow: 'The rating', title: 'The rating rests on older reviews.', tone: TONE.strong,
      sub: <>Google shows {gap.displayed}★, but the newest {gap.recent_count} average {fmt(gap.recent_mean, 2)}★. For {gap.displayed}★ to hold, the other {plural(gap.older_count, 'review')} would have to average {fmt(gap.older_implied_mean, 2)}★.</>,
      visual: (
        <div className="sp-ladder">
          <div><span className="small secondary">Google shows</span><StarBar value={gap.displayed} duration={1.2} className="sp-starbar" /><span className="sp-fig sm">{fmt(gap.displayed, 1)}</span></div>
          <div><span className="small secondary">The newest {gap.recent_count}</span><StarBar value={gap.recent_mean} delay={0.6} duration={1.2} className="sp-starbar" /><span className="sp-fig sm">{fmt(gap.recent_mean, 2)}</span></div>
        </div>
      ),
    })
  }

  const top = report.signals.T8
  if (top?.available && (top.generated.length > 0 || report.evidence.some((e) => e.kind === 'top_rated'))) {
    const hit = top.generated.find((g) => g.excerpt)
    out.push({
      key: 'top', ms: 9000, dots: true, eyebrow: 'Its most-shown reviews', tone: TONE.strong,
      title: hit ? 'One of its top reviews is a pasted chatbot reply.' : 'Its top-ranked praise arrived all at once.',
      sub: <>{top.window_count} of the {top.count} 5★ reviews Google ranks first were posted within {top.window_months} months, {Math.round(top.single_use_share * 100)}% from accounts with no other reviews.</>,
      visual: hit && (
        <figure className="sp-quote chatbot">
          <blockquote><Marked text={around(hit.excerpt!, phraseSpan(hit.excerpt!, hit.marker), 260)} marks={[hit.marker]} /></blockquote>
          <figcaption className="tiny muted">A 5★ review from {hit.reviewer_reviews != null && hit.reviewer_reviews <= 1 ? 'an account with no other reviews' : 'Google’s top-ranked reviews'} · {day(hit.day)}</figcaption>
        </figure>
      ),
    })
  }

  const aside = new Set(sieve.set_aside_by_default)
  for (const k of sieve.order) {
    const rows = withSign(report, k)
    if (!rows.length || !aside.has(k)) continue
    out.push(signScene(report, k, rows, namer))
  }

  if (report.sample.expanded > 0) {
    const pairs = report.graph.edges.length
    const newest = newestDay(report)
    const others = (cid: string) => report.histories?.[cid]?.items.filter((x) => !x.this).length ?? 0
    const alone = report.reviewers.filter((r) => r.status === 'ok' && others(r.contributor_id) === 0).length
    // Strips only say something for reviewers with a history; the rest are counted.
    const shown = report.reviewers.filter((r) => others(r.contributor_id) >= 2).sort((a, b) => others(b.contributor_id) - others(a.contributor_id)).slice(0, 4)
    out.push({
      key: 'histories', ms: 7200, dots: true, eyebrow: 'Who wrote them', title: `We opened ${plural(report.sample.expanded, 'reviewer')}' full histories.`,
      hot: ids(report.reviews.filter((r) => report.reviewers.some((x) => x.contributor_id === r.contributor_id))), tone: 'var(--ink)',
      sub: pairs
        ? <>{plural(pairs, 'pair')} of them reviewed the same unrelated places, far from here.</>
        : <>The most unusual reviewers, plus a few at random. None of them reviewed the same unrelated places, so there is no linked group.</>,
      visual: (
        <>
          <div className="sp-tiles">
            <div><span className="sp-fig">{report.sample.expanded}</span><span className="muted small">histories opened</span></div>
            <div><span className="sp-fig">{alone}</span><span className="muted small">had reviewed nothing else</span></div>
            <div><span className="sp-fig">{pairs}</span><span className="muted small">linked pairs</span></div>
          </div>
          {shown.length > 0 && (
            <div className="sp-strips">
              {shown.map((r) => <div key={r.contributor_id}><span className="tiny muted">{namer.reviewer(r.contributor_id)} · {plural(others(r.contributor_id), 'other review')}</span><HistoryStrip points={stripPoints(report.histories![r.contributor_id], newest)} width={420} height={30} /></div>)}
              <span className="tiny muted">Each line is one reviewer&rsquo;s public history, oldest left; ★ marks this business.</span>
            </div>
          )}
        </>
      ),
    })
  }

  for (const k of sieve.order) {
    const rows = withSign(report, k)
    if (!rows.length || aside.has(k) || !['ai_style', 'review_spree'].includes(k)) continue
    out.push(signScene(report, k, rows, namer))
  }

  const gone = ids(report.reviews.filter((r) => r.signs?.some((s) => aside.has(s))))
  const kept = sieve.kept
  const moved = Math.abs((kept.mean ?? 0) - (sieve.all.mean ?? 0))
  // The reader's other choice, when a listing names itself with its area over and over.
  const named = sieve.signs.names_area?.count ?? 0
  const stricter = report.reviews.filter((r) => !r.signs?.some((s) => aside.has(s) || s === 'names_area') && r.rating != null)
  const stricterMean = stricter.length ? stricter.reduce((a, r) => a + r.rating!, 0) / stricter.length : null
  out.push({
    key: 'kept', ms: 8200, dots: true, gone, eyebrow: 'What is left',
    title: gone.size ? `Set the ${gone.size} flagged reviews aside, and ${kept.count} remain.` : 'Nothing needed setting aside.',
    sub: gone.size
      ? <>{moved < 0.1 ? 'The rating barely moves: they' : 'They'} average {fmt(kept.mean, 2)}★, against {fmt(sieve.all.mean, 2)}★ for all {n}{p.rating != null ? ` and the ${p.rating}★ Google shows` : ''}.{named >= 5 && stricterMean != null
          ? <> Set aside the {named} that name the business with its area too, and {stricter.length} remain at {fmt(stricterMean, 2)}★. Your call, in the report.</>
          : ' In the report you choose what to set aside; these are the defaults.'}</>
      : <>The newest {n} average {fmt(sieve.all.mean, 2)}★, and nothing near-certain was found among them.</>,
    visual: (
      <div className="sp-ladder">
        <div className={gone.size ? '' : 'strong'}><span className="small secondary">All {n} newest</span><StarBar value={sieve.all.mean ?? 0} duration={1} className="sp-starbar" /><span className="sp-fig sm">{fmt(sieve.all.mean, 2)}</span></div>
        {gone.size > 0 && <div className="strong"><span className="small secondary">The {kept.count} kept</span><StarBar value={kept.mean ?? 0} from={sieve.all.mean ?? undefined} delay={0.8} duration={1.1} className="sp-starbar" /><span className="sp-fig sm">{fmt(kept.mean, 2)}</span></div>}
        {gone.size > 0 && named >= 5 && stricterMean != null && (
          <div><span className="small secondary">Also without the {named}</span><StarBar value={stricterMean} delay={1.6} duration={1.1} className="sp-starbar" /><span className="sp-fig sm">{fmt(stricterMean, 2)}</span></div>
        )}
      </div>
    ),
  })

  const lv = report.level.level
  out.push({
    key: 'verdict', ms: 9000, dots: true, gone, eyebrow: 'In short', title: VERDICT_LINE[lv],
    visual: (
      <div className="sp-verdict">
        <LevelBadge level={lv} size="big" />
        <ul>{report.level.reasons.slice(0, 3).map((x) => <li key={x}>{x}</li>)}</ul>
        <p className="small muted">A pattern, not proof. A business can be targeted without its knowledge.</p>
      </div>
    ),
  })
  return out
}

function signScene(report: Report, k: SignKey, rows: ReviewRow[], namer: Namer): Scene {
  const sieve = report.sieve!
  const info = sieve.signs[k]
  const base = { key: k, ms: 8600, dots: true, hot: ids(rows), tone: info.strength === 'strong' ? TONE.strong : TONE.context }
  const n = rows.length
  const texts = rows.some((r) => r.text)
  switch (k) {
    case 'chatbot_text': {
      const r = rows.find((x) => x.excerpt || x.text)
      const t = r?.excerpt ?? r?.text ?? ''
      return {
        ...base, eyebrow: 'Worth flagging', title: `${plural(n, 'review')} ${n === 1 ? 'contains' : 'contain'} chatbot text.`,
        sub: 'A phrase only a chatbot or an unfilled template produces, pasted in as a customer review.',
        visual: r && <Quote r={r} namer={namer}><Marked text={around(t, r.generated_marker ? phraseSpan(t, r.generated_marker) : null, 240)} marks={r.generated_marker ? [r.generated_marker] : []} /></Quote>,
      }
    }
    case 'copied_text': {
      const a = rows.find((r) => r.text && r.copied_with?.length)
      const b = a ? report.reviews.find((x) => x.review_id === a.copied_with![0]) : undefined
      return {
        ...base, eyebrow: 'Worth flagging', title: `${n} reviews are near copies of each other.`,
        sub: 'Different accounts, nearly the same words, often with the same mistakes. The shared wording is underlined.',
        visual: a && b?.text ? (
          <div className="sp-pair">
            <Quote r={a} namer={namer}><Shared text={around(a.text!, null, 220)} other={b.text} /></Quote>
            <Quote r={b} namer={namer}><Shared text={around(b.text, null, 220)} other={a.text!} /></Quote>
          </div>
        ) : !texts ? <Hidden /> : undefined,
      }
    }
    case 'keyword_style': {
      const named = sieve.signs.names_area?.count ?? 0
      return {
        ...base, eyebrow: 'Worth flagging', title: `${n} reviews read like search ads.`,
        sub: <>The bare search term with the area, or the name and area again and again: how search-ranking copy is written.{named > 0 && <> Another {named} only name the business with its area, as customers also do. Those are kept.</>}</>,
        visual: texts ? (
          <div className="sp-quotes">
            {examples(rows, 3).map((r) => (
              <Quote key={r.review_id} r={r} namer={namer}>
                <Marked text={around(r.text!, r.keyword_phrase ? phraseSpan(r.text!, r.keyword_phrase) : null, 150)} marks={[]} keyword={r.keyword_phrase} />
              </Quote>
            ))}
          </div>
        ) : <div className="sp-quotes">{rows.slice(0, 3).filter((r) => r.keyword_phrase).map((r) => <div key={r.review_id} className="phrase">&ldquo;{r.keyword_phrase}&rdquo;</div>)}</div>,
      }
    }
    case 'review_burst': {
      const c = (report.signals.T11?.clusters ?? []).filter((x) => x.flagged).sort((a, b) => b.count - a.count)[0]
      if (!c) return { ...base, eyebrow: 'Worth flagging', title: `${n} reviews came in a burst.` }
      const star = c.stars === 5 ? 'five-star' : 'one-star'
      const tighter = c.core.count < c.count && c.core.minutes < c.minutes * 0.6
      return {
        ...base, ms: 9600, eyebrow: 'Worth flagging', tone: c.stars === 5 ? TONE.strong : TONE.ring,
        title: `${c.count} ${star} reviews in ${spanText(c.minutes)}.`,
        sub: <>{burstWhen(c.start, c.end).replace(/^./, (x) => x.toUpperCase())}{tighter ? `, ${c.core.count} of them within ${spanText(c.core.minutes)}` : ''}. That&rsquo;s {Math.round(c.share * 100)}% of its newest reviews; it usually gets {paceText(c.usual_per_day)}.{c.first_time > 0 && <> {c.first_time} came from accounts with no other reviews.</>}{c.stars === 1 && <> A wave of one-star reviews can also be an attack on the business.</>}</>,
        visual: <BurstZoom report={report} burst={c} tone={c.stars === 5 ? TONE.strong : TONE.ring} />,
      }
    }
    case 'linked_group': {
      const groups = report.groups.filter((g) => FLAGGED_VERDICTS.includes(g.verdict)).slice(0, 2)
      return {
        ...base, tone: TONE.ring, eyebrow: 'Worth flagging', title: `${n} reviews come from a linked group of accounts.`,
        sub: 'Accounts that reviewed the same unrelated businesses in distant cities, more often than chance allows.',
        visual: (
          <div className="sp-tiles">
            {groups.map((g) => (
              <div key={g.group_id}><span className="sp-fig">{g.metrics.size}</span><span className="muted small">accounts sharing {plural(g.metrics.core_places, 'unrelated place')}{g.confidence != null ? `, strength ${g.confidence.toFixed(2)}` : ''}</span></div>
            ))}
          </div>
        ),
      }
    }
    case 'ai_style': {
      const r = examples(rows.filter((x) => x.ai?.cues.length), 1)[0]
      return {
        ...base, ms: 7600, tone: TONE.opinion, eyebrow: 'An opinion, kept', title: `An AI model thinks ${n} ${n === 1 ? 'reads' : 'read'} as AI-written.`,
        sub: 'It quotes the phrases why. Real customers polish honest reviews with AI too, so these stay unless you choose otherwise.',
        visual: r ? <Quote r={r} namer={namer}><Marked text={around(r.text!, phraseSpan(r.text!, r.ai!.cues[0]), 240)} marks={r.ai!.cues} /></Quote> : undefined,
      }
    }
    default:
      return {
        ...base, ms: 6400, eyebrow: 'Context, kept', title: `${plural(n, 'reviewer')} went on a reviewing spree.`,
        sub: 'Many unrelated businesses in several cities within a month, nearly all 5★: the shape of “rate and earn” tasks, though some travellers review this way too.',
      }
  }
}

/* ---------------------------------------------------------------- the reviews, as dots */

/** The newest reviews as a grid of dots in date order, oldest first, read like text. Motion only moves a dot in or
 * out; its colour, dimming and ring are plain styles eased by CSS, since motion can't interpolate CSS colours. */
function Field({ report, scene }: { report: Report; scene: Scene }) {
  const [box, W] = useWidth<HTMLDivElement>()
  const rows = useMemo(() => [...report.reviews].sort((a, b) => (a.day ?? '').localeCompare(b.day ?? '')), [report])
  const cols = W >= 820 ? 50 : 25
  const cell = W > 0 ? Math.min(24, W / cols) : 0
  const lines = Math.ceil(rows.length / cols)
  const hot = scene.hot
  return (
    <div ref={box} className={`sp-field ${scene.dots ? 'on' : ''}`}>
      {W > 0 && (
        <svg width={cols * cell} height={lines * cell} style={{ overflow: 'visible' }}>
          {rows.map((r, i) => {
            const cx = (i % cols + 0.5) * cell
            const cy = (Math.floor(i / cols) + 0.5) * cell
            const first = r.reviewer_reviews != null && r.reviewer_reviews <= 1
            const isHot = !!hot?.has(r.review_id)
            const gone = !!scene.gone?.has(r.review_id)
            return (
              <motion.g key={r.review_id} initial={{ opacity: 0, y: -14 }} animate={{ opacity: scene.dots ? 1 : 0, y: scene.dots ? 0 : -14 }}
                transition={{ duration: 0.5, ease: EASE, delay: scene.dots ? (i / rows.length) * 0.7 : 0 }}>
                <circle cx={cx} cy={cy} r={cell * 0.36} className="sp-dot"
                  style={{
                    fill: first ? 'var(--bg)' : starFill(r.rating),
                    stroke: isHot ? scene.tone : first ? starFill(r.rating === 5 ? 5 : r.rating) : 'transparent',
                    strokeWidth: isHot ? 3 : first ? 1.8 : 0,
                    opacity: gone ? 0.08 : hot && !isHot ? 0.2 : 1,
                    transform: gone ? `translateY(${cell * 0.5}px)` : 'none',
                  }} />
              </motion.g>
            )
          })}
        </svg>
      )}
      <div className="sp-field-axis tiny muted" style={{ width: cols * cell || undefined }}>
        <span>{day(rows[0]?.day)}, oldest</span>
        <span className="sp-key"><i className="full" /> rating <i className="hollow" /> account with no other reviews</span>
        <span>newest, {day(rows[rows.length - 1]?.day)}</span>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- the player */

function Segments({ count, at, progress }: { count: number; at: number; progress: MotionValue<number> }) {
  const width = useTransform(progress, (v) => `${v * 100}%`)
  return (
    <div className="sp-segments" aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <span key={i}>{i < at ? <i style={{ width: '100%' }} /> : i === at ? <motion.i style={{ width }} /> : null}</span>
      ))}
    </div>
  )
}

export function CaseStory({ report, namer, synthetic, onClose, onRead }: {
  report: Report; namer: Namer; synthetic?: boolean; onClose: () => void; onRead: () => void
}) {
  // Presentation mode keeps only the start of a few texts: mark the cut so a quote doesn't stop mid-word.
  const view = useMemo(() => (report.pseudonymized
    ? { ...report, reviews: report.reviews.map((r) => (r.text && r.text.length >= 58 ? { ...r, text: `${r.text}…` } : r)) }
    : report), [report])
  const scenes = useMemo(() => buildScenes(view, namer), [view, namer])
  const [at, setAt] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [chrome, setChrome] = useState(true)
  const progress = useMotionValue(0)
  const last = scenes.length - 1
  const scene = scenes[at]

  const go = useCallback((i: number) => {
    progress.set(0)
    setAt(Math.max(0, Math.min(last, i)))
  }, [last, progress])

  useEffect(() => {
    if (!playing) return
    const left = (1 - progress.get()) * scene.ms
    const c = animate(progress, 1, {
      duration: left / 1000, ease: 'linear',
      onComplete: () => (at < last ? go(at + 1) : setPlaying(false)),
    })
    return () => c.stop()
  }, [at, playing, scene.ms, last, go, progress])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === ' ') { e.preventDefault(); setPlaying((x) => !x) }
      else if (e.key === 'ArrowRight') go(at + 1)
      else if (e.key === 'ArrowLeft') go(at - 1)
      else if (e.key === 'h' || e.key === 'H') setChrome((x) => !x)
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [at, go, onClose])

  const ended = at === last && !playing
  return (
    <motion.div className={`story-player ${chrome ? '' : 'bare'}`} role="dialog" aria-modal="true" aria-label={`What we found: ${report.place.title ?? 'this business'}`}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="sp-top">
        <Segments count={scenes.length} at={at} progress={progress} />
        <div className="sp-topline">
          <span className="small muted">ReviewRing · {report.place.title ?? 'This business'}{synthetic && <span className="chip accent" style={{ marginLeft: 8 }}>Synthetic example</span>}</span>
          <button className="icon-btn sp-chrome" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
      </div>

      <div className="sp-stage" onClick={(e) => { if ((e.target as HTMLElement).closest('button, a')) return; go(at + 1) }}>
        <AnimatePresence mode="wait">
          <motion.div key={scene.key} className="sp-scene" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={{ duration: 0.45, ease: EASE }}>
            <div className="sp-copy">
              <div className="sp-eyebrow">{scene.eyebrow}</div>
              <h2 className={`sp-title ${scene.key === 'intro' ? 'hero' : ''}`}>{scene.title}</h2>
              {scene.sub && <motion.p className="sp-sub" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5, duration: 0.6 }}>{scene.sub}</motion.p>}
              {scene.key === 'verdict' && (
                <motion.div className="row wrap" style={{ gap: 10, marginTop: 22 }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1 }}>
                  <button className="btn primary" onClick={onRead}>Read the kept reviews <ChevronRight size={16} /></button>
                  <button className="btn" onClick={() => { go(0); setPlaying(true) }}><RotateCcw size={14} /> Watch again</button>
                </motion.div>
              )}
            </div>
            <motion.div className="sp-visual" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.25, duration: 0.6, ease: EASE }}>
              {scene.visual}
            </motion.div>
          </motion.div>
        </AnimatePresence>
        <Field report={view} scene={scene} />
      </div>

      <div className="sp-controls sp-chrome">
        <button className="icon-btn" onClick={() => go(at - 1)} disabled={at === 0} aria-label="Previous"><ChevronLeft size={18} /></button>
        <button className="icon-btn" onClick={() => (ended ? (go(0), setPlaying(true)) : setPlaying((x) => !x))} aria-label={playing ? 'Pause' : 'Play'}>
          {ended ? <RotateCcw size={16} /> : playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button className="icon-btn" onClick={() => go(at + 1)} disabled={at === last} aria-label="Next"><ChevronRight size={18} /></button>
        <span className="tiny muted">{at + 1} / {scenes.length} · Space pauses · ← → skip · H hides these controls</span>
      </div>
    </motion.div>
  )
}
