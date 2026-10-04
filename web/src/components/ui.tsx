import { CircleCheck, CircleDashed, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'
import { motion } from 'motion/react'
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
      <Icon size={size === 'big' ? 19 : 14} strokeWidth={2.2} aria-hidden />
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

/** The mark: reviewers on a ring, one of them linked across it. It turns slowly; reduced motion stops it. */
export function Logo({ size = 26 }: { size?: number }) {
  const dots = Array.from({ length: 8 }, (_, i) => {
    const a = (i / 8) * Math.PI * 2 - Math.PI / 2
    return { x: 16 + 11 * Math.cos(a), y: 16 + 11 * Math.sin(a) }
  })
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <motion.g style={{ originX: '16px', originY: '16px' }} animate={{ rotate: 360 }} transition={{ duration: 40, repeat: Infinity, ease: 'linear' }}>
        <circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" strokeOpacity="0.18" strokeWidth="1.5" />
        <line x1={dots[1].x} y1={dots[1].y} x2={dots[5].x} y2={dots[5].y} stroke="var(--accent)" strokeWidth="1.6" />
        <line x1={dots[1].x} y1={dots[1].y} x2={dots[3].x} y2={dots[3].y} stroke="var(--accent)" strokeWidth="1.6" />
        <line x1={dots[3].x} y1={dots[3].y} x2={dots[5].x} y2={dots[5].y} stroke="var(--accent)" strokeWidth="1.6" />
        {dots.map((d, i) => (
          <circle key={i} cx={d.x} cy={d.y} r={i % 2 ? 2.6 : 1.8} fill={i % 2 ? 'var(--accent)' : 'currentColor'} fillOpacity={i % 2 ? 1 : 0.35} />
        ))}
      </motion.g>
    </svg>
  )
}
