import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import type { Mode, Settings } from '../types'

export function SettingsPage() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const save = useMutation({
    mutationFn: (c: Partial<Settings>) => api.saveSettings(c),
    onSuccess: () => qc.invalidateQueries(),
  })
  if (!q.data) return <p className="muted">{q.isError ? (q.error as Error).message : 'Loading…'}</p>
  const s = q.data
  return (
    <div className="stack" style={{ maxWidth: 720 }}>
      <section className="card">
        <h2>Run mode</h2>
        {(['live', 'offline', 'demo'] as Mode[]).map((m) => (
          <label key={m} className="toggle" style={{ display: 'flex', margin: '6px 0' }}>
            <input type="radio" name="mode" checked={s.mode === m} disabled={m === 'live' && !s.serpapi_key_set}
              onChange={() => save.mutate({ mode: m })} />
            <span>
              <strong>{m === 'live' ? 'Live' : m === 'offline' ? 'Offline' : 'Demo'}</strong>{' '}
              <span className="muted small">
                {m === 'live' && 'Cache first, then SerpApi within the budget.'}
                {m === 'offline' && 'Local cache only. Missing data is reported with its cost.'}
                {m === 'demo' && 'Prepared pseudonymized examples. No keys, no network.'}
              </span>
            </span>
          </label>
        ))}
        {!s.serpapi_key_set && <p className="small muted">Live mode needs SERPAPI_API_KEY in the backend's .env file.</p>}
      </section>
      <section className="card">
        <h2>Search caps</h2>
        <div className="row">
          {(['monthly_cap', 'hourly_cap', 'per_analysis_cap'] as const).map((k) => (
            <label key={k} className="small">
              {k.replace('_cap', '').replace('_', ' ')}{' '}
              <input className="input" type="number" min={0} style={{ width: 90 }} defaultValue={s[k]}
                onBlur={(e) => save.mutate({ [k]: Number(e.target.value) })} />
            </label>
          ))}
        </div>
        <p className="small muted">The stricter of these caps and SerpApi's own account numbers always applies.</p>
      </section>
      <section className="card">
        <h2>Keys</h2>
        <p>SerpApi key: <strong>{s.serpapi_key_set ? 'set' : 'not set'}</strong> · DeepSeek key: <strong>{s.deepseek_key_set ? 'set' : 'not set'}</strong></p>
        <p className="small muted">Keys live only in the backend's .env file and are never shown here.</p>
        <label className="toggle">
          <input type="checkbox" checked={s.paraphrase_signal} onChange={(e) => save.mutate({ paraphrase_signal: e.target.checked })} />
          AI reworded-template signal (A8). Sends scrubbed review texts to DeepSeek; context only, never decides.
        </label>
      </section>
      {save.isError && <div className="notice error">{(save.error as Error).message}</div>}
    </div>
  )
}
