// Shared motion: counters that settle on the report's exact number, and a width hook for SVG charts.
// MotionConfig in main.tsx honours the viewer's reduced-motion setting for all of these.

import { animate, useInView, useReducedMotion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

const format = (v: number, digits: number) => v.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export const EASE = [0.22, 1, 0.36, 1] as const

/** Counts from `from` to `value` when scrolled into view, then shows `value` formatted exactly as given. */
export function CountUp({ value, from = 0, digits = 0, duration = 1.4, delay = 0 }: { value: number; from?: number; digits?: number; duration?: number; delay?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const reduce = useReducedMotion()
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (reduce) {
      el.textContent = format(value, digits)
      return
    }
    if (!inView) {
      el.textContent = format(from, digits)
      return
    }
    const c = animate(from, value, { duration, delay, ease: EASE, onUpdate: (v) => (el.textContent = format(v, digits)) })
    return () => c.stop()
  }, [inView, value, from, digits, duration, delay, reduce])
  return <span ref={ref} className="num">{format(reduce ? value : from, digits)}</span>
}

export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(el)
    setWidth(el.getBoundingClientRect().width)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}
