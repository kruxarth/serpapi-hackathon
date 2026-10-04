import { motion } from 'motion/react'
import { StarBar } from './ui'

const DOTS = 34
const LINKED = [5, 11, 19, 26, 30]

/**
 * Home illustration (no data): five stars fill, the reviews behind them line up, and a few of them turn out to be
 * linked. It plays once.
 */
export function HeroStars() {
  const x = (i: number) => 10 + i * (400 / (DOTS - 1))
  return (
    <div className="hero-stars" aria-hidden>
      <StarBar value={5} className="hero-starbar" duration={1.4} delay={0.3} />
      <svg viewBox="0 0 420 150" width="420" height="150" style={{ display: 'block', marginTop: 18, overflow: 'visible' }}>
        {LINKED.slice(1).map((d, i) => {
          const a = x(LINKED[i])
          const b = x(d)
          return (
            <motion.path key={d} d={`M ${a} 40 Q ${(a + b) / 2} ${130 - i * 6} ${b} 40`} fill="none" stroke="var(--label-ring)" strokeWidth="2"
              initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 1 }} transition={{ duration: 0.8, delay: 2.9 + i * 0.25, ease: 'easeInOut' }} />
          )
        })}
        {Array.from({ length: DOTS }, (_, i) => {
          const hot = LINKED.includes(i)
          return (
            <motion.circle key={i} cx={x(i)} cy={40} r={hot ? 6 : 4.5}
              initial={{ opacity: 0, cy: 0, fill: 'var(--label-none)' }}
              animate={{ opacity: hot ? 1 : 0.55, cy: 40, fill: hot ? 'var(--label-ring)' : 'var(--label-none)' }}
              transition={{ opacity: { delay: 1.5 + i * 0.025 }, cy: { type: 'spring', stiffness: 220, damping: 14, delay: 1.5 + i * 0.025 }, fill: { delay: hot ? 2.7 : 0, duration: 0.4 } }} />
          )
        })}
      </svg>
      <motion.p className="muted small" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 3.9 }} style={{ marginTop: 6 }}>
        Behind every star: reviews, and the people who wrote them.
      </motion.p>
    </div>
  )
}
