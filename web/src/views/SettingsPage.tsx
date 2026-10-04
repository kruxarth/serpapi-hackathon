import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, KeyRound } from 'lucide-react'
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { api } from '../api'
import type { Mode, Settings } from '../types'

const MODES: { m: Mode; title: string; text: string }[] = [
  { m: 'live', title: 'Live', text: 'Cache first, then SerpApi within the budget.' },
  { m: 'offline', title: 'Offline', text: 'Local cache only. Missing data is reported with its cost.' },
  { m: 'demo', title: 'Demo', text: 'Prepared, pseudonymized synthetic examples. No keys, no network.' },
]

export function SettingsPage() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const save = useMutation({
    mutationFn: (c: Partial<Settings>) => api.saveSettings(c),
    onSuccess: () => qc.invalidateQueries(),
  })
  if (!q.data) return q.isError ? <div className="notice error"><CircleAlert size={16} />{(q.error as Error).message}</div> : <div className="skeleton" style={{ height: 300, maxWidth: 760 }} />
  const s = q.data
  return (
    <div className="col" style={{ gap: 18, maxWidth: 760 }}>
      <h1 style={{ fontSize: '2.2rem', letterSpacing: '-0.04em' }}>Settings</h1>
      <Section title="Run mode">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, position: 'relative' }}>
          {MODES.map(({ m, title, text }) => {
            const disabled = m === 'live' && !s.serpapi_key_set
            return (
              <button key={m} className={`group-chip ${s.mode === m ? 'on' : ''}`} disabled={disabled} aria-pressed={s.mode === m}
                style={{ flexDirection: 'column', alignItems: 'flex-start', opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}
                onClick={() => save.mutate({ mode: m })}>
                <strong>{title}</strong>
                <span className="muted small">{text}</span>
              </button>
            )
          })}
        </div>
        {!s.serpapi_key_set && <p className="small muted" style={{ marginTop: 10 }}>Live mode needs SERPAPI_API_KEY in the backend's .env file.</p>}
      </Section>
      <Section title="Search caps">
        <div className="row" style={{ gap: 18 }}>
          {(['monthly_cap', 'hourly_cap', 'per_analysis_cap'] as const).map((k) => (
            <label key={k} className="col small secondary" style={{ gap: 6 }}>
              {k === 'per_analysis_cap' ? 'Per analysis' : k === 'monthly_cap' ? 'Monthly' : 'Hourly'}
              <input className="input num" type="number" min={0} style={{ width: 130 }} defaultValue={s[k]} onBlur={(e) => save.mutate({ [k]: Number(e.target.value) })} />
            </label>
          ))}
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>The stricter of these caps and SerpApi's own account numbers always applies.</p>
      </Section>
      <Section title="Keys">
        <div className="row" style={{ gap: 10 }}>
          <KeyState name="SerpApi" set={s.serpapi_key_set} />
          <KeyState name="DeepSeek" set={s.deepseek_key_set} />
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>Keys live only in the backend's .env file and are never shown here.</p>
        <label className="row" style={{ marginTop: 16, gap: 10, cursor: 'pointer', alignItems: 'flex-start' }}>
          <input type="checkbox" checked={s.paraphrase_signal} onChange={(e) => save.mutate({ paraphrase_signal: e.target.checked })} style={{ marginTop: 4 }} />
          <span>
            <strong>AI reworded-template signal (A8)</strong>
            <span className="muted small" style={{ display: 'block' }}>Sends scrubbed review texts to DeepSeek. Context only; it never decides a label or level.</span>
          </span>
        </label>
      </Section>
      {save.isError && <div className="notice error"><CircleAlert size={16} />{(save.error as Error).message}</div>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <motion.section className="panel pad" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <h2 style={{ fontSize: '1.35rem', marginBottom: 14 }}>{title}</h2>
      {children}
    </motion.section>
  )
}

function KeyState({ name, set }: { name: string; set: boolean }) {
  return (
    <span className="chip" style={{ height: 30, color: set ? 'var(--status-good)' : 'var(--muted)' }}>
      <KeyRound size={13} /> {name}: <strong>{set ? 'set' : 'not set'}</strong>
    </span>
  )
}
