import { useQuery } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { api } from '../api'
import { EASE, Reveal } from '../motion'

type Cell = string | number | null
interface Row { [k: string]: Cell }
interface Evaluation {
  summary: Record<string, string | number>
  charts: { file: string; title: string }[]
  tables: { title: string; rows: Row[] }[]
}

/** "83.0% (249/300); almost every loss…" → ["83.0%", "(249/300); almost every loss…"]. The text is the backend's. */
function split(v: string | number): [string, string] {
  const s = String(v)
  const m = s.match(/^([\d.,/]+%?)\s*(.*)$/)
  return m ? [m[1], m[2]] : [s, '']
}

export function EvaluationPage() {
  const q = useQuery({ queryKey: ['evaluation'], queryFn: api.evaluation })
  if (q.isLoading) return <div className="skeleton" style={{ height: 300 }} />
  if (!q.data?.available) {
    return (
      <div className="panel pad">
        <h2>Evaluation</h2>
        <p className="muted" style={{ marginTop: 8 }}>No results yet. Run <code>uv run reviewring evaluate</code> in the backend folder.</p>
      </div>
    )
  }
  const d = q.data as unknown as Evaluation
  const entries = Object.entries(d.summary)
  const leadKey = entries.find(([k]) => k.toLowerCase().includes('harder'))?.[0]
  const lead = leadKey ? split(d.summary[leadKey]) : null
  const rest = entries.filter(([k]) => k !== leadKey && k !== 'Bases')

  return (
    <div className="col" style={{ gap: 28, maxWidth: 1120 }}>
      <div>
        <div className="eyebrow">Evaluation on planted synthetic rings</div>
        {lead && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ ease: EASE, duration: 0.7 }} style={{ marginTop: 16 }}>
            <div className="row" style={{ alignItems: 'baseline', gap: 18 }}>
              <span className="num" style={{ fontSize: '6rem', fontWeight: 680, letterSpacing: '-0.06em', lineHeight: 1 }}>{lead[0]}</span>
              <span style={{ fontSize: '1.4rem', fontWeight: 600, letterSpacing: '-0.02em', maxWidth: 520 }}>{leadKey}</span>
            </div>
            <p className="secondary" style={{ marginTop: 10 }}>{lead[1]}</p>
          </motion.div>
        )}
        <p className="secondary small" style={{ marginTop: 14, maxWidth: 760 }}>
          Rings are planted into synthetic businesses. Rings shaped like our own model make recall optimistic, so the harder rings
          (aged accounts, photos, unique texts, spread timing) come first. Negative scenarios check that trips and friend circles aren't flagged.
        </p>
        {d.summary.Bases && <p className="muted small" style={{ marginTop: 6 }}>Bases: {String(d.summary.Bases)}</p>}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {rest.map(([k, v], i) => {
          const [big, note] = split(v)
          return (
            <motion.div key={k} className="panel pad" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ease: EASE, delay: 0.2 + i * 0.05 }}>
              <div className="big-num num" style={{ fontSize: '2rem' }}>{big}</div>
              <div style={{ marginTop: 8, fontWeight: 560 }}>{k}</div>
              {note && <div className="muted small" style={{ marginTop: 4 }}>{note}</div>}
            </motion.div>
          )
        })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
        {d.tables.map((t) => (
          <Reveal key={t.title}>
            <div className="panel pad">
              <h3 style={{ marginBottom: 12 }}>{t.title}</h3>
              <table className="small">
                <thead><tr>{Object.keys(t.rows[0] ?? {}).map((k) => <th key={k}>{k}</th>)}</tr></thead>
                <tbody>
                  {t.rows.map((r, i) => (
                    <tr key={i}>
                      {Object.entries(r).map(([k, v]) => (
                        <td key={k} className="num">
                          {k === 'recall' && typeof v === 'number' ? (
                            <span className="row" style={{ gap: 10 }}>
                              <span className="bar-track" style={{ width: 90, height: 6 }}><span className="bar-fill" style={{ display: 'block', width: `${v * 100}%` }} /></span>
                              {v}
                            </span>
                          ) : v ?? '–'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Reveal>
        ))}
      </div>
      {d.charts.length > 0 && <p className="muted small">Charts: {d.charts.map((c) => c.title).join(', ')} are in <code>docs/evaluation/</code>.</p>}
    </div>
  )
}
