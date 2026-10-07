import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, Search, SlidersHorizontal } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type StartOptions } from '../api'
import { BudgetDetail } from '../components/BudgetWidget'
import { illustrationDots, RatingUnpacked } from '../components/RatingUnpacked'
import { LevelBadge } from '../components/ui'
import { ageText, fmt } from '../labels'
import { EASE } from '../motion'
import { usePresentation } from '../presentation'
import type { AnalysisListItem, Candidate, ResolveResult } from '../types'

const CHECKS = ['Bursts of single-use accounts', 'Chatbot or template text', 'Ratings carried by old reviews', 'Linked reviewer groups', 'Innocent explanations']

const rise = (i: number) => ({
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.7, ease: EASE, delay: 0.08 * i },
})

export function HomePage() {
  const pres = usePresentation()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const list = useQuery({ queryKey: ['analyses', pres.on], queryFn: () => api.list(pres.on), refetchInterval: 10000 })
  const demo = health.data?.mode === 'demo'

  return (
    <div>
      <section className="home-hero">
        <div>
          <motion.h1 {...rise(0)}>A Google rating is a number.</motion.h1>
          <motion.p className="hero-sub" {...rise(1)}>ReviewRing shows where it comes from.</motion.p>
          <motion.p className="lede" {...rise(2)}>
            Paste a Google Maps link. ReviewRing reads the newest reviews, opens the histories of the most unusual reviewers,
            and tells you how much of the rating to trust, with the evidence for every claim.
          </motion.p>
          <motion.div {...rise(3)}>
            {demo ? (
              <div className="notice" style={{ marginTop: 28 }}>
                <CircleAlert size={16} /> Demo mode can't analyse new places. Open one of the prepared, synthetic examples below.
              </div>
            ) : (
              <Analyse mode={health.data?.mode} />
            )}
          </motion.div>
          <motion.div className="checks" {...rise(4)}>
            {CHECKS.map((c) => <span key={c} className="chip">{c}</span>)}
          </motion.div>
        </div>
        <HeroIllustration />
      </section>

      <section>
        <div className="section-title">
          <h2>{demo ? 'Prepared examples' : 'Recent analyses'}</h2>
          {demo && <span className="muted">Synthetic businesses, made to show each kind of finding</span>}
        </div>
        {list.isLoading && <div className="analysis-list">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 76 }} />)}</div>}
        {list.isError && <p className="muted">{(list.error as Error).message}</p>}
        {list.data?.length === 0 && (
          <p className="muted">{demo ? 'No demo fixtures found in fixtures/.' : 'No analyses yet. Paste a Google Maps link above.'}</p>
        )}
        <div className="analysis-list">
          {list.data?.map((a, i) => (
            <motion.div key={a.id} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE, delay: 0.3 + i * 0.06 }}>
              <AnalysisRow a={a} />
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  )
}

const DEMO = illustrationDots()

/** The product's own visual, on invented reviews: a rating, its reviews, and a burst of single-use accounts lifted out. */
function HeroIllustration() {
  return (
    <motion.div className="hero-ill panel" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, ease: EASE, delay: 0.35 }} aria-label="Illustration with invented reviews">
      <RatingUnpacked dots={DEMO.dots} shown={DEMO.shown} mean={DEMO.mean} adjusted={DEMO.adjusted} height={270} loop />
      <p className="muted tiny" style={{ marginTop: 10 }}>Illustration with invented reviews.</p>
    </motion.div>
  )
}

function AnalysisRow({ a }: { a: AnalysisListItem }) {
  const shifted = a.adjusted != null && a.sample_mean != null && a.adjusted !== a.sample_mean
  return (
    <Link to={`/analysis/${a.id}`} className="analysis-row">
      <div>
        <div className="row" style={{ gap: 10 }}>
          <span className="name">{a.title ?? a.type ?? 'Place'}</span>
          {a.synthetic && <span className="chip accent">Synthetic</span>}
        </div>
        <div className="muted small">{[a.type, a.area].filter(Boolean).join(', ') || '–'}</div>
      </div>
      <div>{a.level ? <LevelBadge level={a.level} /> : <span className="chip">{a.status}</span>}</div>
      <div>
        {a.sample_mean != null ? (
          <>
            <span className="fig" style={{ fontSize: '1.35rem' }}>{fmt(a.sample_mean, 2)}<span style={{ color: 'var(--gold)' }}>★</span></span>
            {shifted && <span className="num secondary"> → {fmt(a.adjusted, 2)}★</span>}
            <div className="muted tiny">{shifted ? 'latest reviews → without linked reviewers' : 'average of the latest reviews'}</div>
          </>
        ) : <span className="muted">–</span>}
      </div>
      <div className="small secondary">
        <span className="num">{a.searches_used}</span> searches
        <div className="muted tiny">{a.finished_at ? ageText(a.finished_at) : a.stage ?? ''}</div>
      </div>
    </Link>
  )
}

function Analyse({ mode }: { mode: string | undefined }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [input, setInput] = useState('')
  const [opts, setOpts] = useState<StartOptions>({})
  const [showOpts, setShowOpts] = useState(false)
  const [resolved, setResolved] = useState<ResolveResult | null>(null)
  const [pick, setPick] = useState<string | undefined>()
  const [error, setError] = useState<string | null>(null)
  const offline = mode === 'offline'
  const withPick = { ...opts, pick }

  const resolve = useMutation({
    mutationFn: (confirm: boolean) => api.resolve(input, { ...withPick, confirm_lookup: confirm }),
    onSuccess: (r) => {
      setResolved(r)
      setError(null)
      qc.invalidateQueries({ queryKey: ['budget'] })
      if (r.candidates?.length === 1) setPick(r.candidates[0].data_id ?? undefined)
    },
    onError: (e: Error) => {
      setResolved(null)
      setError(e.message)
    },
  })
  const start = useMutation({
    mutationFn: () => api.start(input, withPick),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['analyses'] })
      navigate(`/analysis/${r.analysis_id}`)
    },
    onError: (e: Error) => setError(e.message),
  })

  const needsPick = (resolved?.candidates?.length ?? 0) > 1 && !pick
  const est = resolved && !resolved.needs_confirmation ? resolved.estimate : null
  const num = (k: keyof StartOptions, v: string) => setOpts({ ...opts, [k]: v ? Number(v) : undefined })

  return (
    <div>
      <form
        className="search-box"
        onSubmit={(e) => {
          e.preventDefault()
          setPick(undefined)
          if (input.trim()) resolve.mutate(false)
        }}
      >
        <Search size={18} className="muted" style={{ alignSelf: 'center', marginLeft: 8 }} />
        <input
          placeholder="Paste a Google Maps link, or type a name and city"
          value={input}
          onChange={(e) => {
            setInput(e.target.value)
            setResolved(null)
          }}
          aria-label="Google Maps link or business name and city"
        />
        <button type="button" className="btn ghost sm" style={{ alignSelf: 'center' }} onClick={() => setShowOpts(!showOpts)} aria-expanded={showOpts} aria-label="Options">
          <SlidersHorizontal size={15} />
        </button>
        <button className="btn primary" type="submit" disabled={!input.trim() || resolve.isPending}>
          {resolve.isPending ? 'Checking…' : 'Check cost'}
        </button>
      </form>
      <p className="muted small" style={{ marginTop: 10 }}>You'll see the cost in searches before anything is spent. <code>maps.app.goo.gl</code> links work too.</p>

      <AnimatePresence>
        {showOpts && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: 'hidden' }}>
            <div className="row wrap small" style={{ gap: 18, paddingTop: 14 }}>
              <label className="row" style={{ gap: 8 }}>Newest reviews <input type="number" className="input" style={{ width: 80, height: 34 }} min={8} max={208} placeholder="88" value={opts.n ?? ''} onChange={(e) => num('n', e.target.value)} /></label>
              <label className="row" style={{ gap: 8 }}>Round-1 reviewers <input type="number" className="input" style={{ width: 70, height: 34 }} min={1} max={30} placeholder="8" value={opts.k1 ?? ''} onChange={(e) => num('k1', e.target.value)} /></label>
              <label className="row" style={{ gap: 8 }}>Round-2 reviewers <input type="number" className="input" style={{ width: 70, height: 34 }} min={0} max={40} placeholder="15" value={opts.k2 ?? ''} onChange={(e) => num('k2', e.target.value)} /></label>
              <label className="row" style={{ gap: 8 }}><input type="checkbox" checked={!!opts.stop_after_round1} onChange={(e) => setOpts({ ...opts, stop_after_round1: e.target.checked })} /> Stop after round 1</label>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence mode="popLayout">
        {error && (
          <motion.div key="err" className="notice error" style={{ marginTop: 14 }} initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <CircleAlert size={16} /> {error}
          </motion.div>
        )}
        {resolved?.needs_confirmation && (
          <motion.div key="confirm" className="panel pad" style={{ marginTop: 16 }} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <p>Finding this place costs <strong>1 search</strong> ({resolved.resolved.kind === 'name' ? 'a name search' : 'a place lookup'}).</p>
            <div className="row" style={{ marginTop: 14 }}>
              <button className="btn" onClick={() => resolve.mutate(true)} disabled={resolve.isPending || offline}>Spend 1 search to find it</button>
              {offline && <span className="muted small">Not available in offline mode.</span>}
            </div>
          </motion.div>
        )}
        {resolved?.candidates && resolved.candidates.length > 1 && (
          <motion.div key="cands" style={{ marginTop: 16 }} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: 10 }}>Which place?</h3>
            <CandidatePicker candidates={resolved.candidates} picked={pick} onPick={setPick} />
          </motion.div>
        )}
        {est && (
          <motion.div key="est" className="panel estimate" initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.5, ease: EASE }}>
            <div>
              <div className="secondary">Estimated cost</div>
              <div className="row" style={{ alignItems: 'baseline', gap: 8, marginTop: 10 }}>
                <span className="big-num num">{est.min}–{est.max}</span><span className="secondary">searches</span>
              </div>
              <ul className="small secondary" style={{ paddingLeft: 16, margin: '12px 0 0' }}>
                {est.lines.map((l) => <li key={l}>{l}</li>)}
              </ul>
            </div>
            <div className="col" style={{ justifyContent: 'space-between', gap: 16 }}>
              <div>
                <div className="secondary" style={{ marginBottom: 10 }}>Your budget</div>
                <BudgetDetail />
              </div>
              <div>
                <button className="btn primary lg" style={{ width: '100%' }} disabled={needsPick || start.isPending} onClick={() => start.mutate()}>
                  {offline ? 'Analyse from cache (0 searches)' : `Run analysis (up to ${est.max} searches)`}
                </button>
                {needsPick && <div className="muted small" style={{ marginTop: 6 }}>Pick a place first.</div>}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function CandidatePicker({ candidates, picked, onPick, disabled }: { candidates: Candidate[]; picked?: string; onPick: (id: string | undefined) => void; disabled?: boolean }) {
  return (
    <div className="analysis-list">
      {candidates.map((c) => (
        <button key={c.data_id ?? c.title} type="button" disabled={disabled || !c.data_id}
          className={`group-chip ${picked === c.data_id ? 'on' : ''}`} style={{ width: '100%' }}
          onClick={() => onPick(c.data_id ?? undefined)}>
          <span className="col" style={{ flex: 1 }}>
            <strong>{c.title ?? 'Unnamed place'}</strong>
            <span className="muted small">{[c.type, c.address].filter(Boolean).join(', ')}</span>
          </span>
          <span className="num secondary">{c.rating ?? '–'}★ <span className="muted">({c.reviews?.toLocaleString() ?? '?'})</span></span>
        </button>
      ))}
    </div>
  )
}
