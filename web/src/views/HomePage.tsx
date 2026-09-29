import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError, type StartOptions } from '../api'
import { BudgetWidget } from '../components/BudgetWidget'
import { LevelBadge } from '../components/LevelBadge'
import { ageText, fmt } from '../labels'
import { usePresentation } from '../presentation'
import type { ResolveResult } from '../types'

export function HomePage() {
  const pres = usePresentation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const list = useQuery({ queryKey: ['analyses', pres.on], queryFn: () => api.list(pres.on), refetchInterval: 10000 })
  const [input, setInput] = useState('')
  const [opts, setOpts] = useState<StartOptions>({})
  const [resolved, setResolved] = useState<ResolveResult | null>(null)
  const [pick, setPick] = useState<string | undefined>()
  const [error, setError] = useState<string | null>(null)

  const demo = health.data?.mode === 'demo'
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
  const est = resolved?.estimate
  const offline = health.data?.mode === 'offline'

  return (
    <div className="stack">
      {!demo && (
        <section className="card">
          <h2>Check a Google Maps listing</h2>
          <p className="secondary small">
            Paste a place link from Google Maps (a <code>maps.app.goo.gl</code> short link works too), or type a
            business name and city. You'll see the cost before anything is searched.
          </p>
          <form
            className="row"
            onSubmit={(e) => {
              e.preventDefault()
              setPick(undefined)
              if (input.trim()) resolve.mutate(false)
            }}
          >
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="https://www.google.com/maps/place/…  or  Sunrise Dental Clinic, Pune"
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                setResolved(null)
              }}
              aria-label="Google Maps link or business name and city"
            />
            <button className="btn" type="submit" disabled={!input.trim() || resolve.isPending}>
              {resolve.isPending ? 'Checking…' : 'Check cost'}
            </button>
          </form>
          <details style={{ marginTop: 10 }}>
            <summary className="small">Options</summary>
            <div className="row small" style={{ marginTop: 8 }}>
              <label>
                Newest reviews{' '}
                <input type="number" className="input" style={{ width: 80 }} min={8} max={208} placeholder="88"
                  value={opts.n ?? ''} onChange={(e) => setOpts({ ...opts, n: e.target.value ? +e.target.value : undefined })} />
              </label>
              <label>
                Round-1 reviewers{' '}
                <input type="number" className="input" style={{ width: 70 }} min={1} max={30} placeholder="8"
                  value={opts.k1 ?? ''} onChange={(e) => setOpts({ ...opts, k1: e.target.value ? +e.target.value : undefined })} />
              </label>
              <label>
                Round-2 reviewers{' '}
                <input type="number" className="input" style={{ width: 70 }} min={0} max={40} placeholder="15"
                  value={opts.k2 ?? ''} onChange={(e) => setOpts({ ...opts, k2: e.target.value ? +e.target.value : undefined })} />
              </label>
              <label className="toggle">
                <input type="checkbox" checked={!!opts.stop_after_round1}
                  onChange={(e) => setOpts({ ...opts, stop_after_round1: e.target.checked })} />
                Stop after round 1
              </label>
            </div>
          </details>

          {error && <div className="notice error" style={{ marginTop: 12 }}>{error}</div>}

          {resolved?.needs_confirmation && (
            <div className="notice" style={{ marginTop: 12 }}>
              <p style={{ marginTop: 0 }}>
                Finding this place costs <strong>1 search</strong> ({resolved.resolved.kind === 'name' ? 'a name search' : 'a place lookup'}).
              </p>
              <button className="btn" onClick={() => resolve.mutate(true)} disabled={resolve.isPending || offline}>
                Spend 1 search to find it
              </button>
              {offline && <span className="muted small"> Not available in offline mode.</span>}
            </div>
          )}

          {resolved?.candidates && resolved.candidates.length > 1 && (
            <div style={{ marginTop: 12 }}>
              <h3>Which place?</h3>
              <table>
                <tbody>
                  {resolved.candidates.map((c) => (
                    <tr key={c.data_id ?? c.title} className={`clickable ${pick === c.data_id ? 'selected' : ''}`}
                      onClick={() => {
                        setPick(c.data_id ?? undefined)
                      }}>
                      <td><input type="radio" readOnly checked={pick === c.data_id} aria-label="pick" /></td>
                      <td><strong>{c.title}</strong><div className="muted small">{c.address}</div></td>
                      <td>{c.type}</td>
                      <td className="num">{c.rating ?? '–'}★ ({c.reviews ?? '?'})</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {est && !resolved?.needs_confirmation && (
            <div className="grid-2" style={{ marginTop: 14 }}>
              <div className="notice">
                <h3>Estimated cost</h3>
                <div className="hero"><span className="big num">{est.min}–{est.max}</span> searches</div>
                <ul className="small secondary" style={{ paddingLeft: 18, margin: '6px 0 0' }}>
                  {est.lines.map((l) => <li key={l}>{l}</li>)}
                </ul>
              </div>
              <div className="notice">
                <h3>Budget</h3>
                <BudgetWidget />
                <div style={{ marginTop: 12 }}>
                  <button className="btn primary" disabled={needsPick || start.isPending}
                    onClick={() => start.mutate()}>
                    {offline ? 'Analyse from cache (0 searches)' : `Run analysis (up to ${est.max} searches)`}
                  </button>
                  {needsPick && <div className="muted small">Pick a place first.</div>}
                </div>
              </div>
            </div>
          )}
        </section>
      )}

      <section className="card">
        <h2>{demo ? 'Prepared analyses' : 'Recent analyses'}</h2>
        {list.isLoading && <p className="muted">Loading…</p>}
        {list.isError && <p className="muted">{(list.error as ApiError).message}</p>}
        {list.data && list.data.length === 0 && (
          <p className="muted">
            {demo ? 'No demo fixtures found in fixtures/.' : 'No analyses yet. Paste a Google Maps link above.'}
          </p>
        )}
        {list.data && list.data.length > 0 && (
          <table>
            <thead>
              <tr><th>Place</th><th>Level</th><th>Rating (latest reviews → without ring)</th><th>Searches</th><th>Status</th><th /></tr>
            </thead>
            <tbody>
              {list.data.map((a) => (
                <tr key={a.id} className="clickable" onClick={() => navigate(`/analysis/${a.id}`)}>
                  <td>
                    <strong>{a.title ?? a.type ?? 'Place'}</strong>
                    {a.synthetic && <span className="pill small" style={{ marginLeft: 8 }}>synthetic</span>}
                    <div className="muted small">{[a.type, a.area].filter(Boolean).join(' · ')}</div>
                  </td>
                  <td>{a.level ? <LevelBadge level={a.level} small /> : <span className="muted">–</span>}</td>
                  <td className="num">{a.sample_mean != null ? `${fmt(a.sample_mean, 2)} → ${fmt(a.adjusted, 2)}` : '–'}</td>
                  <td className="num">{a.searches_used}</td>
                  <td className="small">{a.status}{a.finished_at ? ` · ${ageText(a.finished_at)}` : ''}</td>
                  <td><Link to={`/analysis/${a.id}`} onClick={(e) => e.stopPropagation()}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
