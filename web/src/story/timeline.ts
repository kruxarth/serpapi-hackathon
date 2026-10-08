// Turning a scene's scroll progress (0 to 1) into what it draws.

import { useMotionValueEvent, type MotionValue } from 'motion/react'
import { useState } from 'react'

/** The progress as React state, for scenes that draw many elements from it. */
export function useProgress(progress: MotionValue<number>) {
  const [p, setP] = useState(progress.get())
  useMotionValueEvent(progress, 'change', setP)
  return p
}

/** Which step a progress value is in, given the start of each step after the first. */
export function stepOf(p: number, starts: number[]) {
  let s = 0
  starts.forEach((x, i) => { if (p >= x) s = i + 1 })
  return s
}

export const clamp01 = (x: number) => Math.max(0, Math.min(1, x))
/** 0 before a, 1 after b, eased in between. */
export const span = (p: number, a: number, b: number) => {
  const t = clamp01((p - a) / (b - a))
  return t * t * (3 - 2 * t)
}
