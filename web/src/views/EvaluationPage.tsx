import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

interface Row { [k: string]: string | number | null }

export function EvaluationPage() {
  const q = useQuery({ queryKey: ['evaluation'], queryFn: api.evaluation })
  if (q.isLoading) return <p className="muted">Loading…</p>
  if (!q.data?.available) {
    return (
      <section className="card">
        <h2>Evaluation</h2>
        <p className="muted">No results yet. Run <code>uv run reviewring evaluate</code> in the backend folder.</p>
      </section>
    )
  }
  const d = q.data as unknown as {
    summary: Record<string, string | number>
    charts: { file: string; title: string }[]
    tables: { title: string; rows: Row[] }[]
  }
  return (
    <div className="stack">
      <section className="card">
        <h2>Evaluation on planted synthetic rings</h2>
        <p className="secondary small">Rings follow our own model of a ring, so recall here is optimistic. Negative scenarios check that trips and friend circles aren't flagged.</p>
        <dl className="kv">
          {Object.entries(d.summary).map(([k, v]) => <><dt key={`${k}-k`}>{k}</dt><dd key={`${k}-v`}>{v}</dd></>)}
        </dl>
      </section>
      {d.tables.map((t) => (
        <section className="card" key={t.title}>
          <h2>{t.title}</h2>
          <table className="small">
            <thead><tr>{Object.keys(t.rows[0] ?? {}).map((k) => <th key={k}>{k}</th>)}</tr></thead>
            <tbody>{t.rows.map((r, i) => <tr key={i}>{Object.values(r).map((v, j) => <td key={j} className="num">{v ?? '–'}</td>)}</tr>)}</tbody>
          </table>
        </section>
      ))}
    </div>
  )
}
