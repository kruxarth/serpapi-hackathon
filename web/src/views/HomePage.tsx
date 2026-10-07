import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, Search } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { illustrationDots, RatingUnpacked } from '../components/RatingUnpacked'
import { LevelBadge } from '../components/ui'
import { ageText, fmt } from '../labels'
import { EASE } from '../motion'
import { usePresentation } from '../presentation'
import type { AnalysisListItem, Candidate, ResolveResult } from '../types'

const CHECKS = ['Bursts of first-time accounts', 'Chatbot and AI-written text', 'Copied text', 'Ratings carried by old reviews', 'Linked reviewer groups']

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
            Paste a Google Maps link. ReviewRing reads the newest 100 reviews, marks the ones with warning signs, and shows
            you the rating without them. You choose what to set aside; every sign comes with its evidence.
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
  const after = a.kept_mean ?? a.adjusted
  const shifted = after != null && a.sample_mean != null && Math.abs(after - a.sample_mean) >= 0.005
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
            {shifted && <span className="num secondary"> → {fmt(after, 2)}★</span>}
            <div className="muted tiny">{shifted ? `newest ${a.examined ?? ''} → after setting aside${a.kept_count != null ? ` (${a.kept_count} kept)` : ''}` : `average of the newest ${a.examined ?? ''}`}</div>
          </>
        ) : <span className="muted">–</span>}
      </div>
      <div className="small secondary">
        {a.finished_at ? ageText(a.finished_at) : a.stage ?? ''}
      </div>
    </Link>
  )
}

function Analyse({ mode }: { mode: string | undefined }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [input, setInput] = useState('')
  const [candidates, setCandidates] = useState<Candidate[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const offline = mode === 'offline'

  const start = useMutation({
    mutationFn: (pick?: string) => api.start(input, { pick }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['analyses'] })
      navigate(`/analysis/${r.analysis_id}`)
    },
    onError: (e: Error) => setError(e.message),
  })
  // Find the place (a name or a short ID may need one lookup), ask which one if several match, then start.
  const check = useMutation({
    mutationFn: async () => {
      let r: ResolveResult = await api.resolve(input, {})
      if (r.needs_confirmation) r = await api.resolve(input, { confirm_lookup: true })
      return r
    },
    onSuccess: (r) => {
      setError(null)
      if ((r.candidates?.length ?? 0) > 1) setCandidates(r.candidates!)
      else start.mutate(r.candidates?.[0]?.data_id ?? undefined)
    },
    onError: (e: Error) => setError(e.message),
  })
  const busy = check.isPending || start.isPending

  return (
    <div>
      <form
        className="search-box"
        onSubmit={(e) => {
          e.preventDefault()
          setCandidates(null)
          if (input.trim()) check.mutate()
        }}
      >
        <Search size={18} className="muted" style={{ alignSelf: 'center', marginLeft: 8 }} />
        <input
          placeholder="Paste a Google Maps link, or type a name and city"
          value={input}
          onChange={(e) => {
            setInput(e.target.value)
            setCandidates(null)
          }}
          aria-label="Google Maps link or business name and city"
        />
        <button className="btn primary" type="submit" disabled={!input.trim() || busy}>
          {busy ? 'Starting…' : 'Check reviews'}
        </button>
      </form>
      <p className="muted small" style={{ marginTop: 10 }}>
        {offline ? 'Offline mode: only places already fetched can be checked.' : <>Share links (<code>maps.app.goo.gl</code>) work too. Places checked before open instantly.</>}
      </p>

      <AnimatePresence mode="popLayout">
        {error && (
          <motion.div key="err" className="notice error" style={{ marginTop: 14 }} initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <CircleAlert size={16} /> {error}
          </motion.div>
        )}
        {candidates && (
          <motion.div key="cands" style={{ marginTop: 16 }} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ ease: EASE }}>
            <h3 style={{ fontSize: '1.2rem', marginBottom: 10 }}>Which place?</h3>
            <CandidatePicker candidates={candidates} disabled={busy} onPick={(id) => id && start.mutate(id)} />
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
