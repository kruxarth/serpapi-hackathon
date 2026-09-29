import { LEVEL_ICON, levelClass } from '../labels'
import type { Level } from '../types'

export function LevelBadge({ level, small = false }: { level: Level; small?: boolean }) {
  return (
    <span className={`level ${levelClass(level)}`} style={small ? { padding: '1px 10px', fontSize: '0.85rem' } : undefined}>
      <span aria-hidden>{LEVEL_ICON[level]}</span> {level}
    </span>
  )
}
