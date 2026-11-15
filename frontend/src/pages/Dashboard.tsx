import { useEffect, useState } from 'react'
import { RefreshCw, Play, TrendingUp, Target, AlertTriangle } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import type { ScanLatest, Status, Calibration, Position } from '../types'
import { DirectionBadge, LiveDot } from '../components/StatusBadge'
import { formatPrice, formatPct, relativeTime } from '../lib/format'
import clsx from 'clsx'
import { supabase } from '../lib/supabase'
import { AuthPanel } from '../components/AuthPanel'

export function Dashboard() {
  const token = useAuth(s => s.token)
  const user = useAuth(s => s.user)
  const [status, setStatus] = useState<Status | null>(null)
  const [scan, setScan] = useState<ScanLatest | null>(null)
  const [calibration, setCalibration] = useState<Calibration | null>(null)
  const [positions, setPositions] = useState<{ open: Position[]; recent: Position[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      setError(null)
      const [s, sc, cal, pos] = await Promise.all([
        api.status(),
        api.latestScan(),
        api.calibration().catch(() => null),
        api.positions().catch(() => null),
      ])
      setStatus(s)
      setScan(sc)
      setCalibration(cal)
      setPositions(pos)
    } catch (e: any) {
      setError(e.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!token) { setLoading(false); return }
    setLoading(true)
    load()
    const id = setInterval(load, 30_000)
    if (supabase) {
      const channel = supabase.channel('agent-scans').on('postgres_changes',
        {event:'INSERT', schema:'public', table:'agent_events'}, () => { void load() }).subscribe()
      return () => { clearInterval(id); void supabase.removeChannel(channel) }
    }
    const stream = new EventSource(`${import.meta.env.VITE_API_URL || ''}/api/stream`)
    stream.addEventListener('update', () => { void load() })
    return () => { clearInterval(id); stream.close() }
  }, [token])

  const runScan = async () => {
    if (!token) { setError('Sign in under Connections to start a scan.'); return }
    setScanning(true)
    try {
      const result = await api.runScan()
      setScan(result)
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setScanning(false)
    }
  }

  if (!token) return <div className="p-6 md:p-10 max-w-5xl mx-auto space-y-8"><div className="text-center space-y-3"><p className="text-xs uppercase tracking-[.2em] text-[#bfd4f0]">Aether / Overview</p><h1 className="text-3xl font-semibold">Your trading intelligence workspace</h1><p className="text-[var(--color-text-mid)] max-w-2xl mx-auto">Register or sign in to access your account. Market intelligence, automated demo execution, and subscriptions are available only according to your account permissions.</p></div><AuthPanel/></div>

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-text-dim)]">
        Loading dashboard…
      </div>
    )
  }

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Trading overview</h1>
          <p className="text-sm text-[var(--color-text-mid)] mt-0.5">
            {user?.display_name || user?.email} · Market intelligence / multi-exchange signal monitoring
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-[var(--color-text-mid)]">
            <LiveDot live={!!status?.scanner_running} />
            <span>{status?.scanner_running ? 'Scanner live' : 'Scanner idle'}</span>
            {status?.last_scan_at && (
              <span className="text-[var(--color-text-dim)]">· {relativeTime(status.last_scan_at)}</span>
            )}
          </div>
          <button
            onClick={runScan}
            disabled={scanning}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-[var(--color-accent)]/15 text-[var(--color-accent)] text-sm font-medium hover:bg-[var(--color-accent)]/25 disabled:opacity-50 transition"
          >
            {scanning ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Run scan
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-[var(--color-bear)]/40 bg-[var(--color-bear)]/10 px-4 py-3 text-sm text-[var(--color-bear)]">
          {error}
        </div>
      )}

      {scan?.error && <div role="alert" className="rounded-lg border border-[var(--color-amber)]/30 bg-[var(--color-amber)]/10 px-4 py-3 text-sm text-[var(--color-amber)]">Latest scan reported an issue: {scan.error}</div>}
      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Win rate"
          value={calibration ? `${(calibration.win_rate * 100).toFixed(1)}%` : '—'}
          sub={calibration ? `${calibration.wins}W / ${calibration.losses}L` : undefined}
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <StatCard
          label="Open positions"
          value={String(positions?.open?.length ?? status?.open_positions_count ?? 0)}
          icon={<Target className="w-4 h-4" />}
        />
        <StatCard
          label="Last scan analyzed"
          value={String(Array.isArray(scan?.symbols_analyzed) ? scan.symbols_analyzed.length : (scan?.symbols_analyzed ?? '—'))}
          sub={scan?.markets_discovered ? `${scan.markets_discovered} discovered` : undefined}
          icon={<ActivityIcon />}
        />
        <StatCard
          label="Opportunities"
          value={String(scan?.opportunities?.length ?? 0)}
          icon={<AlertTriangle className="w-4 h-4" />}
        />
      </div>

      {/* Opportunities table */}
      <section className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] overflow-hidden">
        <div className="px-5 py-3.5 border-b border-[var(--color-panel-border)] flex items-center justify-between">
          <h2 className="text-sm font-medium">Top opportunities</h2>
          <span className="text-xs text-[var(--color-text-dim)]">
            Ranked by confidence · analytical signals only
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-dim)] border-b border-[var(--color-panel-border)]">
                <th className="px-5 py-2.5 font-medium">Symbol</th>
                <th className="px-4 py-2.5 font-medium">Direction</th>
                <th className="px-4 py-2.5 font-medium">Confidence</th>
                <th className="px-4 py-2.5 font-medium">Entry</th>
                <th className="px-4 py-2.5 font-medium">Target</th>
                <th className="px-4 py-2.5 font-medium">Invalidation</th>
                <th className="px-4 py-2.5 font-medium">Regime</th>
              </tr>
            </thead>
            <tbody>
              {(scan?.opportunities ?? []).length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-5 py-10 text-center text-[var(--color-text-dim)]">
                    No opportunities yet. Run a scan or wait for the background cycle.
                  </td>
                </tr>
              ) : (
                scan!.opportunities.map((op, i) => (
                  <tr
                    key={`${op.symbol}-${i}`}
                    className="border-b border-[var(--color-panel-border)]/60 hover:bg-white/[0.02]"
                  >
                    <td className="px-5 py-3 font-[var(--font-mono)] font-medium">{op.symbol}</td>
                    <td className="px-4 py-3">
                      <DirectionBadge direction={op.direction} />
                    </td>
                    <td className="px-4 py-3">
                      <ConfidenceBar value={op.confidence} />
                    </td>
                    <td className="px-4 py-3 font-[var(--font-mono)] text-[var(--color-text-mid)]">
                      {formatPrice(op.entry_price)}
                    </td>
                    <td className="px-4 py-3 font-[var(--font-mono)] text-[var(--color-bull)]">
                      {formatPrice(op.target_price)}
                    </td>
                    <td className="px-4 py-3 font-[var(--font-mono)] text-[var(--color-bear)]">
                      {formatPrice(op.invalidation_price)}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-text-dim)] capitalize">
                      {op.market_regime ?? '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Open positions preview */}
      {positions && positions.open.length > 0 && (
        <section className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] overflow-hidden">
          <div className="px-5 py-3.5 border-b border-[var(--color-panel-border)]">
            <h2 className="text-sm font-medium">Open positions</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-dim)] border-b border-[var(--color-panel-border)]">
                  <th className="px-5 py-2.5 font-medium">Symbol</th>
                  <th className="px-4 py-2.5 font-medium">Dir</th>
                  <th className="px-4 py-2.5 font-medium">Entry</th>
                  <th className="px-4 py-2.5 font-medium">Current</th>
                  <th className="px-4 py-2.5 font-medium">P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.open.map((p) => (
                  <tr key={p.id} className="border-b border-[var(--color-panel-border)]/60">
                    <td className="px-5 py-3 font-[var(--font-mono)]">{p.symbol}</td>
                    <td className="px-4 py-3">
                      <DirectionBadge direction={p.direction} />
                    </td>
                    <td className="px-4 py-3 font-[var(--font-mono)] text-[var(--color-text-mid)]">
                      {formatPrice(p.entry_price)}
                    </td>
                    <td className="px-4 py-3 font-[var(--font-mono)]">
                      {formatPrice(p.current_price)}
                    </td>
                    <td
                      className={clsx(
                        'px-4 py-3 font-[var(--font-mono)] font-medium',
                        (p.pnl_pct ?? 0) >= 0 ? 'text-[var(--color-bull)]' : 'text-[var(--color-bear)]'
                      )}
                    >
                      {formatPct(p.pnl_pct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

function StatCard({
  label,
  value,
  sub,
  icon,
}: {
  label: string
  value: string
  sub?: string
  icon: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] px-4 py-3.5">
      <div className="flex items-center justify-between text-[var(--color-text-dim)]">
        <span className="text-xs uppercase tracking-wider">{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight font-[var(--font-mono)]">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-[var(--color-text-mid)]">{sub}</div>}
    </div>
  )
}

function ConfidenceBar({ value }: { value: number }) {
  const color =
    value >= 75 ? 'bg-[var(--color-bull)]' : value >= 60 ? 'bg-[var(--color-amber)]' : 'bg-[var(--color-text-dim)]'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
      <span className="font-[var(--font-mono)] text-xs text-[var(--color-text-mid)]">{value}</span>
    </div>
  )
}

function ActivityIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
    </svg>
  )
}
