import { useQuery } from '@tanstack/react-query'
import { NavLink, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { BudgetWidget } from './components/BudgetWidget'
import { usePresentation } from './presentation'
import { AnalysisPage } from './views/AnalysisPage'
import { EvaluationPage } from './views/EvaluationPage'
import { HomePage } from './views/HomePage'
import { SettingsPage } from './views/SettingsPage'

const MODE_TEXT = { live: 'Live', offline: 'Offline (cache only)', demo: 'Demo (prepared examples)' }

export default function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15000 })
  const pres = usePresentation()
  const mode = health.data?.mode

  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="ReviewRing home">
          <img src="/favicon.svg" width={22} height={22} alt="" /> ReviewRing
        </NavLink>
        <nav className="nav">
          <NavLink to="/" end>Analyse</NavLink>
          <NavLink to="/evaluation">Evaluation</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="spacer" />
        {mode && (
          <span className="pill" title="Run mode">
            Mode: <strong>{MODE_TEXT[mode]}</strong>
          </span>
        )}
        <BudgetWidget compact />
        <label className="toggle" title="Pseudonymize names, round locations and hide review text, for recordings">
          <input type="checkbox" checked={pres.on} onChange={(e) => pres.set(e.target.checked)} />
          Presentation mode
        </label>
      </header>
      {health.isError && (
        <div className="banner" role="alert">
          The ReviewRing backend is not running. Start it with <code>uv run reviewring serve</code> in the{' '}
          <code>backend</code> folder.
        </div>
      )}
      {mode === 'demo' && !health.isError && (
        <div className="banner">
          Demo mode: prepared, pseudonymized analyses. Nothing is fetched. Add a SerpApi key and switch to live mode to
          analyse a place.
        </div>
      )}
      {!mode && !health.isError && <div />}
      <main className="main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/analysis/:id" element={<AnalysisPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}
