import { CircleCheck, CircleDashed, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { useEffect, useRef } from 'react'
import { levelClass } from '../labels'
import type { Level } from '../types'

const LEVEL_ICON: Record<Level, LucideIcon> = {
  High: OctagonAlert,
  Elevated: TriangleAlert,
  Low: CircleCheck,
  'Not enough history': CircleDashed,
}

export function LevelBadge({ level, size = 'pill' }: { level: Level; size?: 'pill' | 'big' }) {
  const Icon = LEVEL_ICON[level]
  return (
    <span className={`level level-${size} ${levelClass(level)}`}>
      <Icon size={size === 'big' ? 24 : 15} strokeWidth={2.4} aria-hidden />
      {level}
    </span>
  )
}

export function Stars({ rating }: { rating: number | null }) {
  if (rating == null) return <span className="muted">–</span>
  return (
    <span className="stars" aria-label={`${rating} stars`}>
      {'★'.repeat(rating)}
      <span className="off">{'★'.repeat(Math.max(0, 5 - rating))}</span>
    </span>
  )
}

/**
 * Five stars filled to a rating. With `from`, the fill first reaches `from` and then settles on `value`: the
 * report's own "listing shows X, recent reviews give Y" told as one motion. `onValue` lets a figure follow the fill.
 */
export function StarBar({ value, from, delay = 0, duration = 1.8, className, onValue }: {
  value: number; from?: number; delay?: number; duration?: number; className?: string; onValue?: (v: number) => void
}) {
  const reduce = useReducedMotion()
  const v = useMotionValue(reduce ? value : 0)
  const follow = useRef(onValue)
  follow.current = onValue
  const width = useTransform(v, (x) => `${(Math.max(0, Math.min(5, x)) / 5) * 100}%`)
  useEffect(() => {
    if (reduce) {
      v.set(value)
      follow.current?.(value)
      return
    }
    // With `from`: fill to what the listing shows, hold, then settle on the value.
    const keys = from != null && from !== value ? [0, from, from, value] : [0, value]
    const c = animate(v, keys, {
      duration: from != null ? duration * 1.8 : duration, delay, ease: 'easeInOut',
      times: keys.length === 4 ? [0, 0.4, 0.55, 1] : undefined,
      onUpdate: (x) => follow.current?.(x),
    })
    return () => c.stop()
  }, [value, from, delay, duration, reduce, v])
  return (
    <span className={`starbar ${className ?? ''}`} role="img" aria-label={`${value} out of 5 stars`}>
      <span className="empty">★★★★★</span>
      <motion.span className="full" style={{ width }}>★★★★★</motion.span>
    </span>
  )
}

/** The mark: a star with a ring of reviewers around it. */
export function Logo({ size = 28 }: { size?: number }) {
  const dots = Array.from({ length: 10 }, (_, i) => {
    const a = (i / 10) * Math.PI * 2
    return { x: 16 + 13 * Math.cos(a), y: 16 + 13 * Math.sin(a) }
  })
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <path d="M16 8.5l2.2 4.6 5 .6-3.7 3.4 1 5-4.5-2.5-4.5 2.5 1-5-3.7-3.4 5-.6z" fill="var(--gold)" />
      {dots.map((d, i) => <circle key={i} cx={d.x} cy={d.y} r={i % 3 === 0 ? 1.9 : 1.3} fill={i % 3 === 0 ? 'var(--label-ring)' : 'currentColor'} fillOpacity={i % 3 === 0 ? 1 : 0.4} />)}
    </svg>
  )
}
