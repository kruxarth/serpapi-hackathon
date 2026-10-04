import { motion } from 'motion/react'

/** Home illustration: a business at the centre, reviewers orbiting it, and one linked group lighting up. */
export function Orbit() {
  const rings = [
    { r: 92, n: 7, dur: 60, linked: [] as number[] },
    { r: 148, n: 11, dur: 90, linked: [1, 4, 8] },
    { r: 204, n: 15, dur: 130, linked: [] as number[] },
  ]
  return (
    <svg viewBox="-240 -240 480 480" className="ring-orbit" aria-hidden>
      <defs>
        <radialGradient id="orbit-core">
          <stop offset="0" stopColor="var(--accent)" stopOpacity="0.35" />
          <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
        </radialGradient>
      </defs>
      <motion.circle r="80" fill="url(#orbit-core)" animate={{ scale: [1, 1.15, 1] }} transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }} />
      {rings.map((ring, ri) => {
        const pts = Array.from({ length: ring.n }, (_, i) => {
          const a = (i / ring.n) * Math.PI * 2 + ri
          return { x: ring.r * Math.cos(a), y: ring.r * Math.sin(a) }
        })
        const linked = ring.linked.map((i) => pts[i])
        return (
          <motion.g key={ri} animate={{ rotate: ri % 2 ? -360 : 360 }} transition={{ duration: ring.dur, repeat: Infinity, ease: 'linear' }}>
            <motion.circle r={ring.r} fill="none" stroke="var(--line-strong)" strokeDasharray="2 6"
              initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 1 }} transition={{ duration: 1.6, delay: 0.2 + ri * 0.2 }} />
            {linked.length > 1 && (
              <motion.polygon points={linked.map((p) => `${p.x},${p.y}`).join(' ')} fill="color-mix(in srgb, var(--label-ring) 10%, transparent)"
                stroke="var(--label-ring)" strokeWidth="1.5" strokeLinejoin="round"
                initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: [0, 1, 1, 0.5, 1] }}
                transition={{ pathLength: { duration: 1.4, delay: 1.4 }, opacity: { duration: 6, delay: 1.4, repeat: Infinity } }} />
            )}
            {pts.map((p, i) => {
              const hot = ring.linked.includes(i)
              return (
                <motion.circle key={i} cx={p.x} cy={p.y} r={hot ? 7 : 4.5}
                  fill={hot ? 'var(--label-ring)' : 'var(--label-none)'} fillOpacity={hot ? 1 : 0.45}
                  initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 260, damping: 18, delay: 0.4 + ri * 0.15 + i * 0.03 }} />
              )
            })}
          </motion.g>
        )
      })}
      <motion.g initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 200, damping: 14, delay: 0.2 }}>
        <circle r="26" fill="var(--surface)" stroke="var(--line-strong)" />
        <text textAnchor="middle" dy="7" fontSize="20" fontWeight="700" fill="var(--ink)">★</text>
      </motion.g>
    </svg>
  )
}
