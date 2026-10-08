// The home page's pinned scenes, told with real findings (numbers only; the listings stay unnamed).
// 2. A hotel's 4.9 breaks into its newest 100 reviews.  3. A mover's reviews, sorted as you scroll.
// 4. One reviewer's route across cities.  5. How it works, as a stack of layers.

import { motion, type MotionValue } from 'motion/react'
import { useMemo } from 'react'
import { SieveGraph, useSieve } from '../components/Sieve'
import { starFill } from '../components/Reviewer'
import { sourceFrom } from '../example'
import { fmt } from '../labels'
import type { SignKey } from '../types'
import { STORY } from './data'
import { Captions, Pinned } from './Pinned'
import { span, stepOf, useProgress } from './timeline'
import { RevealText } from './RevealText'

const H = STORY.hotel
const M = STORY.mover
const C = STORY.clean
const nf = (n: number) => n.toLocaleString('en-IN')

/* ---------------------------------------------------------------- 2. the hotel's rating */

export function HotelScene() {
  return (
    <Pinned id="hotel" screens={4.2} label="A hotel's rating, broken into its newest reviews">
      {(progress) => <HotelStage progress={progress} />}
    </Pinned>
  )
}

const STAR_X = (v: number) => 120 + (v - 1) * 130
function HotelStage({ progress }: { progress: MotionValue<number> }) {
  const p = useProgress(progress)
  const step = stepOf(p, [0.16, 0.4, 0.62, 0.78])
  const ratings = H.ratings
  const counts = [1, 2, 3, 4, 5].map((s) => ratings.filter((r) => r === s).length)
  // Each review's place: hidden in the number, then a grid of the newest 100, then stacked on its star.
  const dots = useMemo(() => {
    const seen = [0, 0, 0, 0, 0, 0]
    return ratings.map((r, i) => {
      const k = seen[r]++
      const jitter = (n: number) => Math.sin(i * 91.7 + n) * 0.5
      return {
        r,
        num: { x: 380 + jitter(1) * 120, y: 190 + jitter(2) * 70 },
        grid: { x: 380 - 9.5 * 24 + (i % 20) * 24, y: 110 + Math.floor(i / 20) * 24 },
        bar: { x: STAR_X(r) - 4 * 11 + (k % 9) * 11, y: 352 - Math.floor(k / 9) * 11 },
        lag: (i % 20) / 20,
      }
    })
  }, [ratings])
  const toGrid = span(p, 0.16, 0.36)
  const toBar = span(p, 0.4, 0.58)
  const lerp = (a: number, b: number, t: number) => a + (b - a) * t
  const meanX = lerp(STAR_X(H.shown), STAR_X(H.mean), span(p, 0.48, 0.62))
  const quote = H.chatbot
  const typed = Math.round(quote.length * span(p, 0.82, 0.97))
  return (
    <div className="scene-grid">
      <div className="scene-copy">
        <RevealText text="A rating is an average of reviews you never see." className="scene-title" />
        <Captions step={step} items={[
          <>A hotel in {H.area} shows <b>{H.shown}★</b>, from about {nf(H.total_approx)} reviews.</>,
          <>ReviewRing reads its newest 100.</>,
          <>By stars, they average <b>{fmt(H.mean, 2)}★</b>: {counts[4]} are five-star and {counts[0]} are one-star.</>,
          <>For {H.shown} to hold, the thousands of older reviews must average <b>{fmt(H.older_mean, 2)}★</b>. The rating rests on them.</>,
          <>Of its {H.top.count} highest-rated reviews, {H.top.window} were posted within {H.top.months} months, a third by accounts with one review or none. One of them reads:</>,
        ]} />
      </div>
      <div className="scene-stage">
        <svg viewBox="0 0 760 460" className="stage-svg" style={{ opacity: 1 - 0.7 * span(p, 0.79, 0.85) }} role="img" aria-label={`${H.shown} stars shown; the newest 100 reviews average ${H.mean}`}>
          <g style={{ opacity: 1 - span(p, 0.14, 0.3) }}>
            <text x={380} y={250} textAnchor="middle" className="giant-num">{H.shown}<tspan className="giant-star">★</tspan></text>
            <text x={380} y={300} textAnchor="middle" className="giant-cap">Google, {nf(H.total_approx)}+ reviews</text>
          </g>
          <g style={{ opacity: span(p, 0.42, 0.52) }}>
            <line x1={70} x2={690} y1={378} y2={378} className="axis" />
            {[1, 2, 3, 4, 5].map((s) => (
              <g key={s}>
                <text x={STAR_X(s)} y={400} textAnchor="middle" className="axis-label">{s}<tspan fill="var(--gold)">★</tspan></text>
                <text x={STAR_X(s)} y={352 - Math.ceil(counts[s - 1] / 9) * 11 - 8} textAnchor="middle" className="axis-count">{counts[s - 1]}</text>
              </g>
            ))}
            <g transform={`translate(${STAR_X(H.shown)} 0)`}>
              <line y1={60} y2={378} className="marker gold" />
              <text y={50} textAnchor="middle" className="marker-label gold">Google {H.shown}</text>
            </g>
            <g transform={`translate(${meanX} 0)`} style={{ opacity: span(p, 0.46, 0.5) }}>
              <line y1={84} y2={378} className="marker ink" />
              <text y={76} textAnchor="middle" className="marker-label">newest 100: {fmt(lerp(H.shown, H.mean, span(p, 0.48, 0.62)), 2)}</text>
            </g>
          </g>
          <g style={{ opacity: span(p, 0.64, 0.72) }}>
            <text x={STAR_X(H.older_mean) + 8} y={446} textAnchor="end" className="marker-label gold">older reviews must average {fmt(H.older_mean, 2)}</text>
            <path d={`M ${STAR_X(H.older_mean)} 408 L ${STAR_X(H.older_mean)} 430`} className="marker gold dashed" />
          </g>
          {dots.map((d, i) => {
            const tg = Math.min(1, Math.max(0, toGrid * 1.6 - d.lag * 0.6))
            const tb = Math.min(1, Math.max(0, toBar * 1.6 - d.lag * 0.6))
            const x = lerp(lerp(d.num.x, d.grid.x, tg), d.bar.x, tb)
            const y = lerp(lerp(d.num.y, d.grid.y, tg), d.bar.y, tb)
            return <circle key={i} cx={x} cy={y} r={tb > 0.5 ? 4.3 : 7} fill={starFill(d.r)} style={{ opacity: span(p, 0.15, 0.22) }} />
          })}
        </svg>
        <motion.blockquote className="quote-card" style={{ opacity: span(p, 0.79, 0.84), y: (1 - span(p, 0.79, 0.86)) * 24 }} aria-label={quote}>
          <div className="quote-meta"><span className="stars-gold">★★★★★</span> a 5★ review, pasted as written</div>
          <pre aria-hidden>{quote.slice(0, typed)}{typed < quote.length && <span className="caret" />}</pre>
        </motion.blockquote>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- 3. the mover, sorted */

const MOVER_SOURCE = sourceFrom(M.reviews)
const STEPS_ASIDE: SignKey[][] = [[], ['first_time_burst'], ['first_time_burst', 'ai_style'], ['first_time_burst', 'ai_style'], ['first_time_burst']]

export function SieveScene() {
  return (
    <Pinned id="sort" screens={5} label="A mover's newest reviews, sorted by warning signs">
      {(progress) => <SieveStage progress={progress} />}
    </Pinned>
  )
}

function SieveStage({ progress }: { progress: MotionValue<number> }) {
  const p = useProgress(progress)
  const step = stepOf(p, [0.18, 0.4, 0.6, 0.8])
  const state = useSieve(MOVER_SOURCE, STEPS_ASIDE[step])
  const spread = Math.round(Math.max(...M.days) / 365 * 10) / 10
  return (
    <div className="scene-grid">
      <div className="scene-copy">
        <RevealText text="Now sort a listing's reviews by what they show." className="scene-title" />
        <Captions step={step} items={[
          <>A mover in {M.area} shows <b>{M.shown.toFixed(1)}★</b>. Its newest 100 reviews average <b>{fmt(M.mean, 2)}★</b>. Every dot is one of them.</>,
          <>
            <b>{M.burst.count}</b> of them arrived within {M.burst.days} days, and {M.burst.first_time} came from accounts that had never reviewed anything else. The other {100 - M.burst.count} took almost {Math.round(spread)} years.
            {step === 1 && <BurstStrip />}
          </>,
          <>{M.ai.ai_style} of its {M.ai.judged} longer reviews read as AI-written to an AI model: all five-star, all from new accounts. At the {H.area} hotel, {H.ai.ratings.filter((r) => r <= 3).length} of the {H.ai.ai_style} it flagged were complaints. Same signal, different meaning, so it's your call.</>,
          <>{M.first_time_accounts} came from first-time accounts. Most real customers review only once, so on its own that isn't a warning sign. It stays kept.</>,
          <>With only the strong signs set aside: <b>{M.kept}</b> reviews, averaging <b>{fmt(M.kept_mean, 2)}★</b>. The number barely moves; which reviews you can trust does. Busy isn't the same as bought: another {C.area} mover's reviews also arrive in waves, yet {C.voice_same} of the {C.voice_compared} reviewers compared write that way everywhere.</>,
        ]} />
      </div>
      <div className="scene-stage sieve-stage">
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
          <span className="small secondary">The newest 100 reviews of a real listing</span>
          <span className="small secondary">Google shows {M.shown.toFixed(1)}<span style={{ color: 'var(--gold)' }}>★</span></span>
        </div>
        <SieveGraph report={MOVER_SOURCE} state={state} compact selected={step === 3 ? 'first_time_account' : undefined} />
      </div>
    </div>
  )
}

/** The newest 100 reviews on a time axis, binned: the burst stands up as one column. */
function BurstStrip() {
  const max = Math.max(...M.days)
  const bins = new Map<number, { burst: boolean; r: number }[]>()
  M.days.forEach((d, i) => {
    const b = Math.round(((max - d) / max) * 60)
    const list = bins.get(b) ?? []
    list.push({ burst: M.reviews[i].signs.includes('first_time_burst'), r: M.reviews[i].rating })
    bins.set(b, list)
  })
  return (
    <svg viewBox="0 0 330 150" className="burst-strip" role="img" aria-label="Reviews over time; one column holds the burst">
      <line x1={0} x2={330} y1={140} y2={140} className="axis" />
      {[...bins.entries()].flatMap(([b, list]) => list.map((d, k) => (
        <circle key={`${b}-${k}`} cx={5 + b * 5.3} cy={136 - k * 3.1} r={1.6} fill={d.burst ? 'var(--label-suspicious)' : starFill(d.r)} />
      )))}
      <text x={0} y={150} className="axis-label small-axis">oldest</text>
      <text x={330} y={150} textAnchor="end" className="axis-label small-axis">newest</text>
    </svg>
  )
}

/* ---------------------------------------------------------------- 4. read the writing */

const S = STORY.scripted
const RES = STORY.research

export function WritingScene() {
  return (
    <Pinned id="writing" screens={4.4} label="Reviews written like search ads, and not in their authors' voice">
      {(progress) => <WritingStage progress={progress} />}
    </Pinned>
  )
}

function WritingStage({ progress }: { progress: MotionValue<number> }) {
  const p = useProgress(progress)
  const step = stepOf(p, [0.24, 0.5, 0.76])
  return (
    <div className="scene-grid">
      <div className="scene-copy">
        <RevealText text="The accounts look real. Read the writing." className="scene-title" />
        <Captions step={step} items={[
          <>A mover in {S.area} shows <b>{S.shown}★</b>. In its newest 100 reviews, <b>{S.keyword_accounts}</b> accounts wrote the same kind of sentence: the business, then its neighbourhood and city.</>,
          <>Customers write &ldquo;the team&rdquo;. Search-ranking copy writes the search phrase. Across nine movers in three cities, two listings do it and seven don't.</>,
          <>We opened the authors' own other reviews. {S.voice.different} of the {S.voice.compared} compared write very differently everywhere else, like this pair. An AI model compares; you see both and decide.</>,
          <>Set those reviews aside and <b>{S.kept}</b> of 100 remain, averaging <b>{fmt(S.kept_mean, 1)}★</b> instead of {fmt(S.mean, 2)}★.</>,
        ]} />
      </div>
      <div className="scene-stage writing-stage">
        <motion.div className="phrase-stack" animate={{ opacity: step === 0 ? 1 : 0, y: step === 0 ? 0 : -20 }} transition={{ duration: 0.5 }}>
          {S.phrases.map((ph, i) => (
            <motion.div key={ph} className="phrase" initial={false} animate={{ opacity: span(p, 0.02 + i * 0.03, 0.06 + i * 0.03), x: 0 }}>
              &ldquo;{ph}&rdquo;
            </motion.div>
          ))}
          <div className="tiny muted" style={{ marginTop: 10 }}>The phrases, with the business's name and neighbourhood replaced</div>
        </motion.div>

        <motion.div className="keyword-bars" animate={{ opacity: step === 1 ? 1 : 0 }} transition={{ duration: 0.5 }} aria-hidden={step !== 1}>
          <div className="small secondary" style={{ marginBottom: 14 }}>Reviews written like a search ad, newest 45–48 reviews of nine movers</div>
          {RES.map((r) => {
            const share = r.with_text ? r.keyword_accounts / r.with_text : 0
            return (
              <div key={r.label} className="kbar">
                <span className="kbar-label">{r.city}</span>
                <span className="kbar-track"><motion.span className="kbar-fill" animate={{ width: `${Math.max(share * 100, 0.6)}%` }} transition={{ duration: 0.8 }} /></span>
                <span className="num kbar-v">{r.keyword_accounts} of {r.with_text}</span>
              </div>
            )
          })}
        </motion.div>

        <motion.div className="voice-pair" animate={{ opacity: step === 2 ? 1 : 0 }} transition={{ duration: 0.5 }} aria-hidden={step !== 2}>
          <div className="voice-card">
            <div className="tiny muted">The same account, reviewing other places</div>
            <p>&ldquo;{S.voice.elsewhere}&hellip;&rdquo;</p>
          </div>
          <div className="voice-arrow" aria-hidden>→</div>
          <div className="voice-card here">
            <div className="tiny muted">Its review of this mover</div>
            <p>&ldquo;&hellip;<mark className="cue">{S.voice.here}</mark>&hellip;&rdquo;</p>
          </div>
        </motion.div>

        <motion.div className="writing-result" animate={{ opacity: step === 3 ? 1 : 0 }} transition={{ duration: 0.5 }} aria-hidden={step !== 3}>
          <div><span className="fig big-fig">100</span><span className="muted"> reviews</span></div>
          <div className="result-arrow">→</div>
          <div><span className="fig big-fig">{S.kept}</span><span className="muted"> kept, averaging </span><span className="fig">{fmt(S.kept_mean, 1)}<span style={{ color: 'var(--gold)' }}>★</span></span></div>
          <div className="small secondary" style={{ gridColumn: '1 / -1', marginTop: 10 }}>
            Set aside: {S.signs.keyword_style} written like search ads, {S.signs.copied_text} copied, {S.signs.voice_mismatch} not in their author's voice (reviews can carry several).
          </div>
        </motion.div>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- 5. how it works */

const LAYERS = [
  { n: 1, title: 'The newest reviews', api: 'SerpApi · Google Maps Reviews API', text: 'The newest 100 reviews in six searches: stars, exact dates, text, and how many reviews each account has written.' },
  { n: 2, title: 'Reviewer histories', api: 'SerpApi · Google Maps Contributor Reviews API', text: "Each unusual reviewer's whole public history in one search: what else they reviewed, where and when. Google's own Places API has no reviewer histories." },
  { n: 3, title: 'Warning signs', api: 'Fixed rules, plus AI comparisons', text: 'Search-ad phrasing, chatbot and copied text, bursts of first-time accounts, and reviews not in their author\u2019s own voice, each shown with its evidence: the phrase, the burst, or both texts side by side.' },
  { n: 4, title: 'Your choice', api: 'The rating, recomputed', text: 'You set aside what you don’t trust and read the rest, with the rating they give. Nothing is called fake.' },
]

export function StackScene() {
  return (
    <Pinned id="how" screens={3.4} label="How ReviewRing works">
      {(progress) => <StackStage progress={progress} />}
    </Pinned>
  )
}

function StackStage({ progress }: { progress: MotionValue<number> }) {
  const p = useProgress(progress)
  const step = stepOf(p, [0.3, 0.5, 0.7])
  const gap = 16 + 84 * span(p, 0.04, 0.3)
  return (
    <div className="scene-grid stack-grid">
      <div className="stack-wrap" aria-hidden>
        <div className="stack">
          {LAYERS.map((l, i) => (
            <div key={l.n} className={`layer layer-${l.n} ${i <= step ? 'lit' : ''} ${i === step ? 'current' : ''}`} style={{ transform: `translateZ(${i * gap}px)` }}>
              <span className="layer-n">{l.n}</span>
              <LayerArt n={l.n} />
            </div>
          ))}
        </div>
      </div>
      <div className="scene-copy">
        <RevealText text="How it works" className="scene-title" />
        <ol className="callouts">
          {LAYERS.map((l, i) => (
            <motion.li key={l.n} animate={{ opacity: i <= step ? 1 : 0.18, x: i <= step ? 0 : 12 }} transition={{ duration: 0.45 }} className={i === step ? 'on' : ''}>
              <div className="row" style={{ gap: 10, alignItems: 'baseline' }}><span className="callout-n">{l.n}</span><strong>{l.title}</strong></div>
              <div className="tiny callout-api">{l.api}</div>
              <p className="small secondary">{l.text}</p>
            </motion.li>
          ))}
        </ol>
      </div>
    </div>
  )
}

function LayerArt({ n }: { n: number }) {
  if (n === 1) {
    return <div className="layer-dots">{M.reviews.map((r, i) => <i key={i} style={{ background: starFill(r.rating) }} />)}</div>
  }
  if (n === 2) {
    return (
      <div className="layer-strips">
        {[14, 9, 18, 6, 12, 16].map((len, r) => (
          <div key={r}>{Array.from({ length: len }, (_, k) => <i key={k} style={{ background: starFill(((r * 7 + k * 3) % 5) + 1), marginLeft: k ? ((r + k) % 3) * 3 : 0 }} />)}</div>
        ))}
      </div>
    )
  }
  if (n === 3) {
    return (
      <div className="layer-chips">
        {['Search-ad phrasing', 'Not their own voice', 'Chatbot text', 'Copied text', 'Burst of first-time accounts', 'Reads as AI-written'].map((c, i) => (
          <span key={c} className={i === 5 ? 'opinion' : ''}>{c}</span>
        ))}
      </div>
    )
  }
  return (
    <div className="layer-choice">
      {[['Burst of first-time accounts', true], ['Reads as AI-written', false]].map(([t, on]) => (
        <div key={String(t)}><span className={`switch-track ${on ? 'on' : ''}`}><span className="switch-thumb" /></span>{t}</div>
      ))}
      <div className="layer-kept"><span className="fig">{fmt(M.kept_mean, 2)}</span><span style={{ color: 'var(--gold)' }}>★</span> kept</div>
    </div>
  )
}
