import { useEffect, useRef } from 'react'

import { prefersReducedMotion } from '../../lib/motion'

const COLORS = ['#7c5cff', '#ff7ab6', '#22c7a9', '#ffb020', '#4cc2ff', '#ff5d73']
const DURATION_MS = 3200

interface Piece {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  spin: number
  angle: number
  color: string
  round: boolean
}

/**
 * A one-shot confetti burst on a full-screen canvas (no library). Decorative only: hidden
 * from assistive technology and skipped when reduced motion is requested.
 */
export function Confetti({ burst }: { burst: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (burst === 0 || !canvas || prefersReducedMotion()) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const ratio = window.devicePixelRatio || 1
    const width = window.innerWidth
    const height = window.innerHeight
    canvas.width = width * ratio
    canvas.height = height * ratio
    ctx.scale(ratio, ratio)

    // Two fountains from the lower corners plus a shower from the center (the open chest).
    const pieces: Piece[] = Array.from({ length: 170 }, (_, i) => {
      const source = i % 3
      const x = source === 0 ? width * 0.1 : source === 1 ? width * 0.9 : width / 2
      const angle =
        source === 0 ? -Math.PI / 3 : source === 1 ? (-2 * Math.PI) / 3 : -Math.PI / 2 + (Math.random() - 0.5)
      const speed = 9 + Math.random() * 9
      return {
        x,
        y: source === 2 ? height * 0.45 : height,
        vx: Math.cos(angle) * speed + (Math.random() - 0.5) * 3,
        vy: Math.sin(angle) * speed,
        size: 6 + Math.random() * 7,
        spin: (Math.random() - 0.5) * 0.3,
        angle: Math.random() * Math.PI,
        color: COLORS[i % COLORS.length] ?? '#7c5cff',
        round: Math.random() < 0.3,
      }
    })

    const start = performance.now()
    let frame = 0
    const draw = (now: number) => {
      const elapsed = now - start
      ctx.clearRect(0, 0, width, height)
      ctx.globalAlpha = Math.max(0, 1 - Math.max(0, elapsed - DURATION_MS * 0.6) / (DURATION_MS * 0.4))
      for (const p of pieces) {
        p.vy += 0.32
        p.vx *= 0.99
        p.x += p.vx
        p.y += p.vy
        p.angle += p.spin
        ctx.save()
        ctx.translate(p.x, p.y)
        ctx.rotate(p.angle)
        ctx.fillStyle = p.color
        if (p.round) {
          ctx.beginPath()
          ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2)
          ctx.fill()
        } else {
          ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2)
        }
        ctx.restore()
      }
      if (elapsed < DURATION_MS) frame = requestAnimationFrame(draw)
      else ctx.clearRect(0, 0, width, height)
    }
    frame = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(frame)
    }
  }, [burst])

  return <canvas ref={canvasRef} className="confetti" aria-hidden="true" />
}
