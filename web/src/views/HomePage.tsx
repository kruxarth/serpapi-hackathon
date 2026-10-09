import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Lenis from 'lenis'
import 'lenis/dist/lenis.css'
import { ChevronDown, CircleAlert, Search } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { SieveGraph, useSieve } from '../components/Sieve'
import { LevelBadge } from '../components/ui'
import { exampleSource } from '../example'
import { ageText, fmt } from '../labels'
import { EASE } from '../motion'
import { usePresentation } from '../presentation'
import { RevealText } from '../story/RevealText'
import { HotelScene, SieveScene, StackScene, WritingScene } from '../story/Scenes'
import { StarField, StarKey } from '../story/StarField'
import type { AnalysisListItem, Candidate, ResolveResult } from '../types'


const rise = (i: number) => ({
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.7, ease: EASE, delay: 0.08 * i },
})

const CHAPTERS = [
  ['top', 'Look closer'],
  ['hotel', 'A rating, unpacked'],
  ['sort', 'Sort the reviews'],
  ['writing', 'Read the writing'],
  ['how', 'How it works'],
  ['check', 'Check a place'],
] as const

let smooth: Lenis | null = null
/** Scroll to a chapter through the smooth scroller when it runs, so the two never fight. */
function jumpTo(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  if (smooth) smooth.scrollTo(el)
  else el.scrollIntoView({ behavior: 'smooth' })
}

/** The home page is the story: real findings told scene by scene, then the search. */
export function HomePage() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const mode = health.data?.mode
  const reduce = useReducedMotion()

  useEffect(() => {
    if (reduce) return
    const lenis = new Lenis({ autoRaf: true, lerp: 0.11 })
    smooth = lenis
    return () => {
      lenis.destroy()
      smooth = null
    }
  }, [reduce])

  return (
    <div className="story">
      <StoryNav />
      <Hero mode={mode} />
      <HotelScene />
      <SieveScene />
      <WritingScene />
      <StackScene />
      <CheckScene mode={mode} />
    </div>
  )
}

/* ---------- 1. the hero: a field of stars and a lens ---------- */

function Hero({ mode }: { mode: string | undefined }) {
  return (
    <section id="top" className="hero-scene" aria-label="ReviewRing">
      <StarField className="star-field" />
      <div className="hero-copy">
        <motion.h1 {...rise(0)}>A Google rating is a number.</motion.h1>
        <motion.p className="hero-sub" {...rise(1)}>Look closer.</motion.p>
        <motion.p className="lede" {...rise(2)}>
          ReviewRing reads a listing's newest 100 reviews, marks the ones with warning signs, and shows you the rating without
          them. You choose what to set aside; every sign comes with its evidence.
        </motion.p>
        <motion.div {...rise(3)}>
          {mode === 'demo' ? <DemoNote /> : <Analyse mode={mode} />}
        </motion.div>
      </div>
      <motion.div className="hero-foot" {...rise(5)}>
        <div>
          <div className="tiny muted" style={{ marginBottom: 6 }}>Move your cursor over the stars. Under it:</div>
          <StarKey />
        </div>
        <a href="#hotel" className="scroll-cue" onClick={(e) => { e.preventDefault(); jumpTo('hotel') }}>
          <ChevronDown size={16} /> Scroll for a real case
        </a>
      </motion.div>
    </section>
  )
}

function DemoNote() {
  return (
    <div className="notice" style={{ marginTop: 28 }}>
      <CircleAlert size={16} /> Demo mode can't check new places. The prepared, synthetic examples are at the end of this page.
    </div>
  )
}

/** Chapter dots on the right edge: where you are in the story, and a way to jump. */
function StoryNav() {
  const [active, setActive] = useState<string>('top')
  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) setActive(e.target.id) })
    }, { rootMargin: '-45% 0px -45% 0px' })
    CHAPTERS.forEach(([id]) => { const el = document.getElementById(id); if (el) io.observe(el) })
    return () => io.disconnect()
  }, [])
  return (
    <nav className="story-nav" aria-label="Story chapters">
      {CHAPTERS.map(([id, text]) => (
        <a key={id} href={`#${id}`} className={active === id ? 'on' : ''} aria-current={active === id ? 'true' : undefined}
          onClick={(e) => { e.preventDefault(); jumpTo(id) }}>
          <span className="story-nav-label">{text}</span><i />
        </a>
      ))}
    </nav>
  )
}

/* ---------- 6. check a place ---------- */

function CheckScene({ mode }: { mode: string | undefined }) {
  const pres = usePresentation()
  const list = useQuery({ queryKey: ['analyses', pres.on, 'per-place'], queryFn: () => api.list(pres.on, true), refetchInterval: 10000 })
  const demo = mode === 'demo'
  return (
    <section id="check" className="check-scene">
      <div className="check-grid">
        <div>
          <RevealText text="Check a place." className="scene-title big" />
          <p className="lede">
            Paste a Google Maps link, or a name and city. A check takes about a minute; places checked before open instantly.
          </p>
          {demo ? <DemoNote /> : <Analyse mode={mode} />}
          <p className="small secondary" style={{ marginTop: 22, maxWidth: '58ch' }}>
            Or use the Chrome extension: open a place on Google Maps, or paste a link into its side panel, and set signs aside
            right there. It also checks whether a rating is carried by old reviews, and whether reviewers belong to linked
            groups that review the same unrelated businesses across cities.
          </p>
        </div>
        <HeroIllustration />
      </div>

      <div className="section-title" style={{ marginTop: 96 }}>
        <h2>{demo ? 'Prepared examples' : 'Recent checks'}</h2>
        {demo && <span className="muted">Synthetic businesses, made to show each kind of finding</span>}
      </div>
      {list.isLoading && <div className="analysis-list">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 76 }} />)}</div>}
      {list.isError && <p className="muted">{(list.error as Error).message}</p>}
      {list.data?.length === 0 && (
        <p className="muted">{demo ? 'No demo fixtures found in fixtures/.' : 'No checks yet. Paste a Google Maps link above.'}</p>
      )}
      <div className="analysis-list">
        {list.data?.map((a) => <AnalysisRow key={a.id} a={a} />)}
      </div>
    </section>
  )
}

const EXAMPLE = exampleSource()

/** The product's own graph on invented reviews: switch a sign and watch its reviews move. */
function HeroIllustration() {
  const state = useSieve(EXAMPLE)
  return (
    <motion.div className="hero-ill panel" initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.9, ease: EASE }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
        <strong>Try it on invented reviews</strong>
        <span className="small secondary">Google shows <span className="num">{EXAMPLE.shown}</span><span style={{ color: 'var(--gold)' }}>★</span></span>
      </div>
      <SieveGraph report={EXAMPLE} state={state} compact />
      <p className="muted tiny" style={{ marginTop: 12 }}>Invented reviews. Each dot is one review, coloured by its stars.</p>
    </motion.div>
  )
}

function AnalysisRow({ a }: { a: AnalysisListItem }) {
  const after = a.kept_mean ?? null
  const setAside = a.kept_count != null && a.examined != null && a.kept_count < a.examined
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
            {setAside && after != null && <span className="num secondary"> → {fmt(after, 2)}★</span>}
            <div className="muted tiny">
              {a.examined == null
                ? 'average of the newest reviews'
                : setAside ? `newest ${a.examined}, then the ${a.kept_count} kept` : `newest ${a.examined}, no strong signs`}
            </div>
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
          placeholder="Google Maps link, or a name and city"
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
        {offline ? 'Offline mode: only places already fetched can be checked.' : <>Share links (<code>maps.app.goo.gl</code>, <code>share.google</code>) work too. Places checked before open instantly.</>}
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
