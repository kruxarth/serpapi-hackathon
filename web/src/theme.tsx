// Light / dark: follows the system unless the viewer picks one (remembered per browser). The resolved scheme is
// exposed so canvas-based views (graph, map) can re-read the CSS colours when it changes.

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

type Pref = 'system' | 'light' | 'dark'
type Scheme = 'light' | 'dark'
const KEY = 'reviewring.theme'

function readPref(): Pref {
  try {
    const v = window.localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

const media = () => window.matchMedia('(prefers-color-scheme: dark)')

const Ctx = createContext<{ scheme: Scheme; toggle: () => void }>({ scheme: 'light', toggle: () => {} })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPref] = useState<Pref>(readPref)
  const [system, setSystem] = useState<Scheme>(() => (media().matches ? 'dark' : 'light'))
  const scheme: Scheme = pref === 'system' ? system : pref

  useEffect(() => {
    const m = media()
    const on = () => setSystem(m.matches ? 'dark' : 'light')
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    if (pref === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', pref)
    root.setAttribute('data-scheme', scheme)
  }, [pref, scheme])

  const toggle = () => {
    const next: Scheme = scheme === 'dark' ? 'light' : 'dark'
    setPref(next)
    try {
      window.localStorage.setItem(KEY, next)
    } catch {
      /* storage unavailable: the choice lasts for this page */
    }
  }
  return <Ctx.Provider value={{ scheme, toggle }}>{children}</Ctx.Provider>
}

export const useTheme = () => useContext(Ctx)
