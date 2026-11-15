import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Position } from '../types'
import { DirectionBadge, StatusBadge } from '../components/StatusBadge'
import { formatPrice, formatPct, relativeTime } from '../lib/format'
import clsx from 'clsx'

export function Positions() {
  const [data, setData] = useState<{ open: Position[]; recent: Position[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .positions()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-text-dim)]">
        Loading positions…
      </div>
    )
  }

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Positions</h1>
        <p className="text-sm text-[var(--color-text-mid)] mt-0.5">
          Live and recently resolved recommendations
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-[var(--color-bear)]/40 bg-[var(--color-bear)]/10 px-4 py-3 text-sm text-[var(--color-bear)]">
          {error}
        </div>
      )}

      <PositionTable title="Open" rows={data?.open ?? []} empty="No open positions" />
      <PositionTable title="Recently resolved" rows={data?.recent ?? []} empty="No recent resolutions" />
    </div>
  )
}

function PositionTable({
  title,
  rows,
  empty,
}: {
  title: string
  rows: Position[]
  empty: string
}) {
  return (
    <section className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] overflow-hidden">
      <div className="px-5 py-3.5 border-b border-[var(--color-panel-border)]">
        <h2 className="text-sm font-medium">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-dim)] border-b border-[var(--color-panel-border)]">
              <th className="px-5 py-2.5 font-medium">Symbol</th>
              <th className="px-4 py-2.5 font-medium">Dir</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium text-right">Entry</th>
              <th className="px-4 py-2.5 font-medium text-right">Current / Exit</th>
              <th className="px-4 py-2.5 font-medium text-right">P&L</th>
              <th className="px-4 py-2.5 font-medium">Opened</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-5 py-10 text-center text-[var(--color-text-dim)]">
                  {empty}
                </td>
              </tr>
            ) : (
              rows.map((p) => (
                <tr key={p.id} className="border-b border-[var(--color-panel-border)]/50 hover:bg-white/[0.02]">
                  <td className="px-5 py-3 font-[var(--font-mono)] font-medium">{p.symbol}</td>
                  <td className="px-4 py-3">
                    <DirectionBadge direction={p.direction} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="px-4 py-3 text-right font-[var(--font-mono)] text-[var(--color-text-mid)]">
                    {formatPrice(p.entry_price)}
                  </td>
                  <td className="px-4 py-3 text-right font-[var(--font-mono)]">
                    {formatPrice(p.current_price)}
                  </td>
                  <td
                    className={clsx(
                      'px-4 py-3 text-right font-[var(--font-mono)] font-medium',
                      (p.pnl_pct ?? 0) >= 0 ? 'text-[var(--color-bull)]' : 'text-[var(--color-bear)]'
                    )}
                  >
                    {formatPct(p.pnl_pct)}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-dim)] text-xs">
                    {relativeTime(p.created_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
