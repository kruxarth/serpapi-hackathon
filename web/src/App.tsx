import { useQuery } from '@tanstack/react-query'
import { CircleX, EyeOff, FlaskConical, Moon, Sun } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api'
import { StatusChip } from './components/BudgetWidget'
import { Logo } from './components/ui'
import { EASE } from './motion'
import { usePresentation } from './presentation'
import { useTheme } from './theme'
import { AnalysisPage } from './views/AnalysisPage'
import { EvaluationPage } from './views/EvaluationPage'
import { HomePage } from './views/HomePage'
import { SettingsPage } from './views/SettingsPage'

const NAV = [
  { to: '/', text: 'Analyse', end: true },
  { to: '/evaluation', text: 'Evaluation', end: false },
  { to: '/settings', text: 'Settings', end: false },
]

export default function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15000 })
  const pres = usePresentation()
  const theme = useTheme()
  const location = useLocation()
  const mode = health.data?.mode

  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="ReviewRing home">
          <Logo /> ReviewRing
        </NavLink>
        <nav className="nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}>
              {({ isActive }) => (
                <>
                  {isActive && <motion.span layoutId="nav-pill" className="nav-pill" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
                  {n.text}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="spacer" />
        <StatusChip mode={mode} />
        <label className="switch" title="Pseudonymize names, round locations and hide review texts, for recordings">
          <input type="checkbox" className="sr-only" checked={pres.on} onChange={(e) => pres.set(e.target.checked)} />
          <span className={`switch-track ${pres.on ? 'on' : ''}`}>
            <motion.span className="switch-thumb" animate={{ x: pres.on ? 14 : 0 }} transition={{ type: 'spring', stiffness: 500, damping: 32 }} />
          </span>
          {pres.on && <EyeOff size={14} aria-hidden />}
          Presentation
        </label>
        <button className="icon-btn" onClick={theme.toggle} aria-label={`Switch to ${theme.scheme === 'dark' ? 'light' : 'dark'} mode`}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.span key={theme.scheme} initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.25 }} style={{ display: 'grid' }}>
              {theme.scheme === 'dark' ? <Moon size={15} /> : <Sun size={15} />}
            </motion.span>
          </AnimatePresence>
        </button>
      </header>

      <AnimatePresence initial={false}>
        {health.isError && (
          <motion.div key="down" className="banner danger" role="alert" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
            <CircleX size={16} /> The ReviewRing backend isn't running. Start it with <code>uv run reviewring serve</code> in the <code>backend</code> folder.
          </motion.div>
        )}
        {mode === 'demo' && !health.isError && (
          <motion.div key="demo" className="banner" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
            <FlaskConical size={16} style={{ color: 'var(--gold)' }} />
            Demo mode: prepared, synthetic, pseudonymized analyses. Nothing is fetched. Add a SerpApi key and switch to live mode to analyse a real place.
          </motion.div>
        )}
      </AnimatePresence>

      <main className="main">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: EASE }}
          >
            <Routes location={location}>
              <Route path="/" element={<HomePage />} />
              <Route path="/analysis/:id" element={<AnalysisPage />} />
              <Route path="/evaluation" element={<EvaluationPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}
