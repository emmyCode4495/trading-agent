import { useEffect, useState, useMemo } from 'react'
import { Search, ArrowUpDown } from 'lucide-react'
import { api } from '../api/client'
import type { Market } from '../types'
import { formatPrice, formatVolume, formatPct } from '../lib/format'
import clsx from 'clsx'

export function Markets() {
  const [markets, setMarkets] = useState<Market[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<'volume' | 'change'>('volume')

  useEffect(() => {
    api
      .markets('USDT')
      .then(setMarkets)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    let list = markets
    if (query.trim()) {
      const q = query.toUpperCase()
      list = list.filter(
        (m) =>
          m.symbol.includes(q) ||
          m.base_asset.includes(q) ||
          (m.exchange || '').toUpperCase().includes(q)
      )
    }
    return [...list].sort((a, b) => {
      if (sort === 'volume') return (b.quote_volume_24h || 0) - (a.quote_volume_24h || 0)
      return (b.price_change_pct_24h || 0) - (a.price_change_pct_24h || 0)
    })
  }, [markets, query, sort])

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-5">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Markets</h1>
          <p className="text-sm text-[var(--color-text-mid)] mt-0.5">
            Unified pairs from Bybit, MEXC & Binance
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-dim)]" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search symbol or exchange…"
              className="pl-9 pr-3 py-2 w-64 rounded-md bg-[var(--color-panel)] border border-[var(--color-panel-border)] text-sm placeholder:text-[var(--color-text-dim)] focus:outline-none focus:border-[var(--color-accent)]/50"
            />
          </div>
          <button
            onClick={() => setSort(sort === 'volume' ? 'change' : 'volume')}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-[var(--color-panel-border)] text-sm text-[var(--color-text-mid)] hover:bg-white/5"
          >
            <ArrowUpDown className="w-3.5 h-3.5" />
            {sort === 'volume' ? 'Volume' : '24h %'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-[var(--color-bear)]/40 bg-[var(--color-bear)]/10 px-4 py-3 text-sm text-[var(--color-bear)]">
          {error}
        </div>
      )}

      <div className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-dim)] border-b border-[var(--color-panel-border)]">
                <th className="px-5 py-2.5 font-medium">Symbol</th>
                <th className="px-4 py-2.5 font-medium">Exchange</th>
                <th className="px-4 py-2.5 font-medium text-right">Price</th>
                <th className="px-4 py-2.5 font-medium text-right">24h %</th>
                <th className="px-4 py-2.5 font-medium text-right">Volume (USDT)</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-[var(--color-text-dim)]">
                    Loading markets…
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-[var(--color-text-dim)]">
                    No markets match your filter.
                  </td>
                </tr>
              ) : (
                filtered.slice(0, 150).map((m) => (
                  <tr
                    key={`${m.exchange || 'cex'}-${m.symbol}`}
                    className="border-b border-[var(--color-panel-border)]/50 hover:bg-white/[0.02]"
                  >
                    <td className="px-5 py-2.5 font-[var(--font-mono)] font-medium">{m.symbol}</td>
                    <td className="px-4 py-2.5">
                      <span className="text-xs px-2 py-0.5 rounded bg-white/5 text-[var(--color-text-mid)] capitalize">
                        {m.exchange || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right font-[var(--font-mono)]">
                      {formatPrice(m.last_price)}
                    </td>
                    <td
                      className={clsx(
                        'px-4 py-2.5 text-right font-[var(--font-mono)]',
                        (m.price_change_pct_24h || 0) >= 0
                          ? 'text-[var(--color-bull)]'
                          : 'text-[var(--color-bear)]'
                      )}
                    >
                      {formatPct(m.price_change_pct_24h)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-[var(--font-mono)] text-[var(--color-text-mid)]">
                      {formatVolume(m.quote_volume_24h)}
                    </td>
                    <td className="px-4 py-2.5 text-[var(--color-text-dim)] text-xs">{m.status}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {!loading && filtered.length > 150 && (
          <div className="px-5 py-2.5 text-xs text-[var(--color-text-dim)] border-t border-[var(--color-panel-border)]">
            Showing top 150 of {filtered.length} pairs
          </div>
        )}
      </div>
    </div>
  )
}
