// A heading whose letters arrive out of order, each sharpening from a blur, once it scrolls into view.

import { motion, useInView, useReducedMotion } from 'motion/react'
import { Fragment, useMemo, useRef } from 'react'

const rand = (i: number) => {
  const x = Math.sin(i * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

export function RevealText({ text, as: Tag = 'h2', className }: { text: string; as?: 'h1' | 'h2' | 'h3'; className?: string }) {
  const ref = useRef<HTMLHeadingElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -15% 0px' })
  const reduce = useReducedMotion()
  const words = useMemo(() => text.split(' '), [text])
  let n = 0
  return (
    <Tag ref={ref} className={className} aria-label={text}>
      {words.map((w, wi) => (
        <Fragment key={wi}>
        <span className="reveal-word" aria-hidden>
          {[...w].map((ch) => {
            const i = n++
            return (
              <motion.span key={i} className="reveal-ch"
                initial={reduce ? false : { opacity: 0, filter: 'blur(8px)' }}
                animate={inView ? { opacity: 1, filter: 'blur(0px)' } : undefined}
                transition={{ duration: 0.5, delay: rand(i + text.length) * 0.7 }}>
                {ch}
              </motion.span>
            )
          })}
        </span>
        {wi < words.length - 1 && ' '}
        </Fragment>
      ))}
    </Tag>
  )
}
