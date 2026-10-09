// The hero's background: a listing's reviews seen from far away, every one a small gold star. Under the cursor
// (a lens) each star shows what it really is: most stay gold, some turn out to come from an account with no other
// reviews, from a burst, to be written like a search ad, or to contain chatbot text. Illustrative, not data. The lens drifts on its own
// until the mouse moves, so the idea also reads in a recording; with reduced motion it stays still.

import { useReducedMotion } from 'motion/react'
import { useEffect, useRef } from 'react'

export type Truth = 'genuine' | 'first' | 'burst' | 'copied' | 'ai'
const CELL = 26
const LENS = 150

function hash(x: number, y: number) {
  const h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453
  return h - Math.floor(h)
}
/** Smooth noise, so bursts and copies come in clumps the way they do in a timeline. */
function noise(x: number, y: number) {
  const xi = Math.floor(x), yi = Math.floor(y)
  const xf = x - xi, yf = y - yi
  const s = (t: number) => t * t * (3 - 2 * t)
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1)
  return a + (b - a) * s(xf) + (c - a) * s(yf) + (a - b - c + d) * s(xf) * s(yf)
}
function truthAt(cx: number, cy: number): Truth {
  if (noise(cx / 6.5 + 40, cy / 6.5) > 0.74) return 'burst'
  const r = hash(cx + 7, cy + 3)
  if (r < 0.15) return 'first'
  if (r < 0.19) return 'copied'
  if (r < 0.24) return 'ai'
  return 'genuine'
}

function starPath(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.beginPath()
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5
    const rr = i % 2 ? r * 0.45 : r
    ctx.lineTo(x + rr * Math.cos(a), y + rr * Math.sin(a))
  }
  ctx.closePath()
}

interface Palette { gold: string; blue: string; muted: string }
function palette(): Palette {
  const css = getComputedStyle(document.documentElement)
  const v = (n: string, f: string) => css.getPropertyValue(n).trim() || f
  return { gold: v('--gold', '#e3a008'), blue: v('--label-suspicious', '#2a78d6'), muted: v('--muted', '#7d879a') }
}

/** One sprite per kind of star, drawn once at the screen's pixel ratio. */
function sprites(p: Palette, dpr: number) {
  const size = 22
  const make = (draw: (c: CanvasRenderingContext2D, m: number) => void) => {
    const cv = document.createElement('canvas')
    cv.width = cv.height = size * dpr
    const c = cv.getContext('2d')!
    c.scale(dpr, dpr)
    draw(c, size / 2)
    return cv
  }
  return {
    surface: make((c, m) => { starPath(c, m, m, 5.2); c.fillStyle = p.gold; c.fill() }),
    genuine: make((c, m) => { starPath(c, m, m, 7.5); c.fillStyle = p.gold; c.fill() }),
    first: make((c, m) => { starPath(c, m, m, 7); c.strokeStyle = p.muted; c.lineWidth = 1.4; c.stroke() }),
    burst: make((c, m) => { starPath(c, m, m, 7.5); c.fillStyle = p.blue; c.fill() }),
    copied: make((c, m) => {
      starPath(c, m - 2.5, m - 2, 6); c.strokeStyle = p.blue; c.lineWidth = 1.3; c.stroke()
      starPath(c, m + 2.5, m + 2, 6); c.fillStyle = p.blue; c.fill()
    }),
    ai: make((c, m) => { starPath(c, m, m, 7.5); c.setLineDash([2, 2]); c.strokeStyle = p.blue; c.lineWidth = 1.4; c.stroke() }),
  }
}

export function StarField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const reduce = useReducedMotion()

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    let W = 0, H = 0
    let sp = sprites(palette(), dpr)
    let cells: { x: number; y: number; t: Truth; tw: number }[] = []

    const resize = () => {
      const r = canvas.getBoundingClientRect()
      W = r.width; H = r.height
      canvas.width = W * dpr; canvas.height = H * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      cells = []
      for (let gy = 0; gy * CELL < H + CELL; gy++) {
        for (let gx = 0; gx * CELL < W + CELL; gx++) {
          const jx = (hash(gx, gy + 99) - 0.5) * 8, jy = (hash(gx + 5, gy) - 0.5) * 8
          cells.push({ x: gx * CELL + CELL / 2 + jx, y: gy * CELL + CELL / 2 + jy, t: truthAt(gx, gy), tw: hash(gx + 13, gy + 17) * Math.PI * 2 })
        }
      }
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)
    // Colours follow the theme.
    const mo = new MutationObserver(() => { sp = sprites(palette(), dpr) })
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-scheme', 'data-theme'] })

    const lens = { x: W * 0.72, y: H * 0.45, tx: W * 0.72, ty: H * 0.45 }
    let lastMove = -1e9
    const onMove = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect()
      lens.tx = e.clientX - r.left
      lens.ty = e.clientY - r.top
      lastMove = performance.now()
    }
    window.addEventListener('pointermove', onMove, { passive: true })

    let visible = true
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting })
    io.observe(canvas)

    let raf = 0
    const draw = (now: number) => {
      raf = requestAnimationFrame(draw)
      if (!visible || document.hidden) return
      if (!reduce && now - lastMove > 2500) {
        const t = now / 1000
        lens.tx = W * (0.68 + 0.18 * Math.sin(t * 0.31)) // drift through the right half when nobody is pointing
        lens.ty = H * (0.45 + 0.25 * Math.sin(t * 0.47 + 1))
      }
      const k = reduce ? 1 : 0.12
      lens.x += (lens.tx - lens.x) * k
      lens.y += (lens.ty - lens.y) * k
      ctx.clearRect(0, 0, W, H)
      const t = now / 1000
      for (const c of cells) {
        // Quieter behind the headline, so the text stays easy to read.
        const calm = Math.min(1, Math.max(0.22, (c.x / W - 0.16) / 0.34))
        const d = Math.hypot(c.x - lens.x, c.y - lens.y)
        const w = d >= LENS ? 0 : (1 - d / LENS) ** 1.6
        const tw = reduce ? 0.8 : 0.72 + 0.28 * Math.sin(t * 1.3 + c.tw)
        if (w < 0.98) {
          ctx.globalAlpha = 0.3 * tw * calm * (1 - w)
          ctx.drawImage(sp.surface, c.x - 11, c.y - 11, 22, 22)
        }
        if (w > 0.02) {
          const s = 22 * (0.8 + 0.35 * w)
          ctx.globalAlpha = Math.min(1, w * 1.25) * (0.55 + 0.45 * calm)
          ctx.drawImage(sp[c.t], c.x - s / 2, c.y - s / 2, s, s)
        }
      }
      ctx.globalAlpha = 1
    }
    raf = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      mo.disconnect()
      io.disconnect()
      window.removeEventListener('pointermove', onMove)
    }
  }, [reduce])

  return <canvas ref={ref} className={className} aria-hidden />
}

/** The key under the hero: what each kind of star means once the lens reveals it. */
export function StarKey() {
  const item = (cls: string, text: string) => (
    <span><svg width="16" height="16" viewBox="0 0 22 22" className={`key-star ${cls}`} aria-hidden><path d="M11 3.5l2.06 4.6 5 .5-3.75 3.35 1.07 4.92L11 14.35l-4.38 2.52 1.07-4.92L3.94 8.6l5-.5z" /></svg>{text}</span>
  )
  return (
    <div className="star-key">
      {item('genuine', 'a review')}
      {item('first', 'from an account with no other reviews')}
      {item('burst', 'posted in a burst')}
      {item('copied', 'written like a search ad')}
      {item('ai', 'contains chatbot text')}
    </div>
  )
}
