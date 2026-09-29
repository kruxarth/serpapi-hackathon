// Presentation mode: remembered per browser. Reports are pseudonymized on the server when it's on,
// so real names never reach the page during a recording.

import { createContext, useContext, useState, type ReactNode } from 'react'

const KEY = 'reviewring.presentation'

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

const Ctx = createContext<{ on: boolean; set: (v: boolean) => void }>({ on: false, set: () => {} })

export function PresentationProvider({ children }: { children: ReactNode }) {
  const [on, setOn] = useState(read)
  const set = (v: boolean) => {
    setOn(v)
    try {
      window.localStorage.setItem(KEY, v ? '1' : '0')
    } catch {
      /* storage unavailable: the toggle still works for this page */
    }
  }
  return <Ctx.Provider value={{ on, set }}>{children}</Ctx.Provider>
}

export const usePresentation = () => useContext(Ctx)
