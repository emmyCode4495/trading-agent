import clsx from 'clsx'
import type { Direction, PositionStatus } from '../types'

export function DirectionBadge({ direction }: { direction: Direction }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium font-[var(--font-mono)] border',
        direction === 'LONG' && 'text-[var(--color-bull)] border-[var(--color-bull)]/40 bg-[var(--color-bull)]/10',
        direction === 'SHORT' && 'text-[var(--color-bear)] border-[var(--color-bear)]/40 bg-[var(--color-bear)]/10',
        direction === 'WAIT' && 'text-[var(--color-amber)] border-[var(--color-amber)]/40 bg-[var(--color-amber)]/10'
      )}
    >
      {direction}
    </span>
  )
}

export function StatusBadge({ status }: { status: PositionStatus }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium font-[var(--font-mono)]',
        status === 'open' && 'text-sky-400 bg-sky-400/10',
        status === 'win' && 'text-[var(--color-bull)] bg-[var(--color-bull)]/10',
        status === 'loss' && 'text-[var(--color-bear)] bg-[var(--color-bear)]/10',
        status === 'expired' && 'text-[var(--color-text-dim)] bg-white/5'
      )}
    >
      {status.toUpperCase()}
    </span>
  )
}

export function LiveDot({ live }: { live: boolean }) {
  return (
    <span className="relative flex h-2.5 w-2.5">
      {live && (
        <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--color-bull)] opacity-60 animate-ping" />
      )}
      <span
        className={clsx(
          'relative inline-flex rounded-full h-2.5 w-2.5',
          live ? 'bg-[var(--color-bull)]' : 'bg-[var(--color-text-dim)]'
        )}
      />
    </span>
  )
}
