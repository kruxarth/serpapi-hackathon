// A pinned scene: a tall section whose content stays on screen while scrolling plays it. Scroll position is the
// timeline, so scrolling back plays the scene in reverse.

import { motion, useScroll, type MotionValue } from 'motion/react'
import { useRef, type ReactNode } from 'react'

export function Pinned({ id, screens, children, label }: {
  id: string; screens: number; label: string; children: (progress: MotionValue<number>) => ReactNode
}) {
  const ref = useRef<HTMLElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] })
  return (
    <section ref={ref} id={id} className="scene" style={{ height: `${screens * 100}vh` }} aria-label={label}>
      <div className="scene-sticky">{children(scrollYProgress)}</div>
    </section>
  )
}

/** Step captions on the left of a scene: the current one is full strength, the rest recede. */
export function Captions({ step, items }: { step: number; items: ReactNode[] }) {
  return (
    <ol className="captions">
      {items.map((c, i) => (
        <motion.li key={i} animate={{ opacity: i === step ? 1 : i < step ? 0.32 : 0.14 }} transition={{ duration: 0.4 }}
          className={i === step ? 'on' : ''} aria-current={i === step ? 'step' : undefined}>
          {c}
        </motion.li>
      ))}
    </ol>
  )
}
